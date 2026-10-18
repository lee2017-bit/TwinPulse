# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Replay the three stored M2-C results through the owned App/Isaac boundary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.client import HTTPResponse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import traceback
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import TwinPulseProcessManager, load_replay_fixture  # noqa: E402


TERMINAL_OPERATION_STATES = {"succeeded", "failed", "cancelled", "expired", "unknown"}


class ProductClient:
    def __init__(self, base_url: str, bootstrap: str) -> None:
        self.base_url = base_url
        status, body, response = self.request(
            "/v1/bootstrap", {"role": "product", "secret": bootstrap}, authenticated=False,
        )
        if status != 200:
            raise RuntimeError(f"Product bootstrap failed: {body}")
        self.cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
        self.csrf = str(body["csrf_token"])
        self.lease_id: str | None = None
        self.renew_at = 0.0

    def request(
        self, path: str, body: Mapping[str, object] | None = None, *, authenticated: bool = True,
    ) -> tuple[int, dict[str, object], HTTPResponse]:
        headers = {"Accept": "application/json", "Origin": self.base_url}
        payload = None
        if body is not None:
            payload = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["Cookie"] = self.cookie
            if body is not None:
                headers["X-TwinPulse-CSRF"] = self.csrf
        request = Request(
            self.base_url + path, data=payload, headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            response = urlopen(request, timeout=5.0)
            return response.status, json.loads(response.read().decode("utf-8")), response
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8")), error

    def acquire_lease(self) -> None:
        status, body, _ = self.request("/v1/product/lease", {})
        if status != 200:
            raise RuntimeError(f"Lease acquisition failed: {body}")
        self.lease_id = str(body["control_lease_id"])
        self.renew_at = time.monotonic() + 1.0

    def renew_if_due(self) -> None:
        if self.lease_id is None or time.monotonic() < self.renew_at:
            return
        status, body, _ = self.request(
            "/v1/product/lease/renew", {"control_lease_id": self.lease_id},
        )
        if status != 200:
            raise RuntimeError(f"Lease renewal failed: {body}")
        self.renew_at = time.monotonic() + 1.0

    def state(self) -> dict[str, object]:
        status, body, _ = self.request("/v1/product/state")
        if status != 200:
            raise RuntimeError(f"State request failed: {body}")
        return body

    def workflow(self) -> dict[str, object]:
        status, body, _ = self.request("/v1/product/workflow")
        if status != 200:
            raise RuntimeError(f"Workflow request failed: {body}")
        return body

    def acknowledge(self, revision: str) -> None:
        status, body, _ = self.request("/v1/product/draft/acknowledge", {"revision": revision})
        if status != 200 or body.get("build_allowed") is not True:
            raise RuntimeError(f"Replay acknowledgement failed: {body}")

    def command(
        self, request_id: str, command_type: str, *, artifact_id: str | None = None,
        revision: str | None = None,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "client_request_id": request_id,
            "command_type": command_type,
            "expected_applied_revision": revision,
        }
        if artifact_id is not None:
            body["artifact_id"] = artifact_id
        status, result, _ = self.request("/v1/product/commands", body)
        if status != 202:
            raise RuntimeError(f"{command_type} submission failed: {result}")
        return result


def wait_until(
    client: ProductClient, predicate: Callable[[dict[str, object]], object], *, timeout_s: float,
) -> object:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        client.renew_if_due()
        state = client.state()
        value = predicate(state)
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for managed replay state")


def wait_operation(client: ProductClient, command_id: str, *, timeout_s: float = 90.0) -> dict[str, object]:
    def completed(state: dict[str, object]) -> dict[str, object] | None:
        for operation in state.get("operations", []):
            if operation.get("command_id") == command_id and operation.get("status") in TERMINAL_OPERATION_STATES:
                return operation
        return None

    operation = wait_until(client, completed, timeout_s=timeout_s)
    if not isinstance(operation, dict) or operation.get("status") != "succeeded":
        raise RuntimeError(f"Managed replay command failed: {operation}")
    return operation


def snapshot_when(
    client: ProductClient, predicate: Callable[[dict[str, object]], bool], *, timeout_s: float,
) -> dict[str, object]:
    def selected(state: dict[str, object]) -> dict[str, object] | None:
        snapshot = state.get("snapshot")
        return snapshot if isinstance(snapshot, dict) and predicate(snapshot) else None

    snapshot = wait_until(client, selected, timeout_s=timeout_s)
    assert isinstance(snapshot, dict)
    return snapshot


def position(snapshot: Mapping[str, object]) -> tuple[float, float, float]:
    value = snapshot.get("position_m")
    if not isinstance(value, list) or len(value) != 3:
        raise RuntimeError("Replay snapshot has no 3D position")
    return tuple(float(item) for item in value)


def distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second, strict=True)))


def run_fixture(
    *, report: Path, fixture_id: str, artifact_dir: Path, isaac_root: Path, timeout_s: float,
    visible_isaac: bool,
) -> dict[str, object]:
    replay = load_replay_fixture(report, fixture_id)
    fixture_dir = artifact_dir / fixture_id
    manager = TwinPulseProcessManager(
        repo_root=ROOT,
        state_dir=fixture_dir / "runtime",
        python_executable=Path(sys.executable),
        isaac_python=isaac_root / "python.bat",
        headless=not visible_isaac,
        ready_timeout_s=min(timeout_s, 180.0),
        credential_target=f"TwinPulse/S2dReplay/{fixture_id}",
        replay_report=report,
        replay_fixture_id=fixture_id,
    )
    item: dict[str, object] = {
        "fixture_id": fixture_id,
        "source": "replay",
        "provider_requests": 0,
        "report_sha256": replay.report_sha256,
        "image_sha256": replay.image_sha256,
        "input_revision": replay.input_revision.digest,
        "plan_sha256": replay.plan_sha256,
        "bundle_sha256": replay.bundle_sha256,
        "scene_id": replay.record.plan.scene_id,
        "request_id": replay.record.request_id,
        "provider_name": replay.record.provider_name,
        "model_id": replay.record.model_id,
        "tool_count": replay.tool_count,
        "object_count": replay.object_count,
        "visible_isaac": visible_isaac,
        "control_status": "NOT_RUN",
        "status": "FAIL",
    }
    receipts: list[dict[str, object]] = []
    failure: Exception | None = None
    failure_traceback: str | None = None
    try:
        launch = manager.start(open_browser=False)
        base_url, bootstrap = manager.product_bootstrap()
        client = ProductClient(base_url, bootstrap)
        workflow = client.workflow()
        draft = workflow.get("draft")
        if workflow.get("mode") != "replay" or not isinstance(draft, dict) or draft.get("source") != "replay":
            raise RuntimeError(f"Backend did not expose a replay draft: {workflow}")
        if draft.get("plan_sha256") != replay.record.plan_sha256:
            raise RuntimeError("Replay workflow plan identity changed")
        # The endpoint must reject Generate before any provider adapter can run.
        generation_status, generation_body, _ = client.request("/v1/product/generation", {})
        if generation_status != 409 or generation_body.get("error", {}).get("code") != "replay_generation_forbidden":
            raise RuntimeError(f"Replay generation guard failed: {generation_status} {generation_body}")
        revision = str(draft["revision"])
        artifact_id = str(draft["artifact_id"])
        client.acknowledge(revision)
        client.acquire_lease()

        build = client.command(f"{fixture_id}-build", "build_scene", artifact_id=artifact_id, revision=revision)
        receipts.append(wait_operation(client, str(build["command_id"]), timeout_s=timeout_s))
        built = snapshot_when(
            client,
            lambda value: value.get("applied_revision") == revision and value.get("runtime_state") == "built",
            timeout_s=30.0,
        )
        start_position = position(built)

        first_run = client.command(f"{fixture_id}-run-mid", "run", revision=revision)
        receipts.append(wait_operation(client, str(first_run["command_id"])))
        moving = snapshot_when(
            client,
            lambda value: value.get("runtime_state") == "running"
            and value.get("position_m") is not None
            and distance(start_position, position(value)) > 0.15,
            timeout_s=30.0,
        )
        movement_before_reset = distance(start_position, position(moving))
        pause = client.command(f"{fixture_id}-pause", "pause", revision=revision)
        receipts.append(wait_operation(client, str(pause["command_id"])))
        paused = snapshot_when(client, lambda value: value.get("runtime_state") == "paused", timeout_s=10.0)
        paused_position = position(paused)
        time.sleep(0.5)
        client.renew_if_due()
        pause_drift = distance(paused_position, position(client.state()["snapshot"]))

        mid_reset = client.command(f"{fixture_id}-reset-mid", "reset", revision=revision)
        receipts.append(wait_operation(client, str(mid_reset["command_id"])))
        reset_snapshot = snapshot_when(
            client, lambda value: value.get("runtime_state") == "built", timeout_s=10.0,
        )
        mid_reset_error = distance(start_position, position(reset_snapshot))

        completion_run = client.command(f"{fixture_id}-run-complete", "run", revision=revision)
        receipts.append(wait_operation(client, str(completion_run["command_id"])))
        completed = snapshot_when(
            client, lambda value: value.get("runtime_state") == "completed", timeout_s=timeout_s,
        )
        completion_position = position(completed)
        completion_reset = client.command(f"{fixture_id}-reset-complete", "reset", revision=revision)
        receipts.append(wait_operation(client, str(completion_reset["command_id"])))
        final_reset = snapshot_when(
            client, lambda value: value.get("runtime_state") == "built", timeout_s=10.0,
        )
        completion_reset_error = distance(start_position, position(final_reset))
        if pause_drift >= 0.002 or mid_reset_error >= 0.03 or completion_reset_error >= 0.03:
            raise RuntimeError(
                f"Replay control tolerance failed: pause={pause_drift}, mid={mid_reset_error}, complete={completion_reset_error}"
            )
        item.update({
            "launch_id": launch.launch_id,
            "stage_epoch": launch.stage_epoch,
            "applied_revision": completed.get("applied_revision"),
            "movement_before_mid_reset_m": movement_before_reset,
            "pause_drift_m": pause_drift,
            "mid_reset_error_m": mid_reset_error,
            "completion_position_m": list(completion_position),
            "completion_goal_error_m": completed.get("distance_to_goal_m"),
            "completion_cross_track_error_m": completed.get("cross_track_error_m"),
            "completion_reset_error_m": completion_reset_error,
            "receipts": receipts,
            "control_status": "PASS",
        })
    except Exception as error:
        failure = error
        failure_traceback = traceback.format_exc()
    finally:
        manager.stop()

    engine_result: dict[str, object] = {}
    if manager.engine_result_file.is_file():
        engine_result = json.loads(manager.engine_result_file.read_text(encoding="utf-8"))
    capture = engine_result.get("capture")
    capture_passed = (
        isinstance(capture, dict)
        and capture.get("status") == "PASS"
        and manager.viewport_capture_file.is_file()
    )
    item.update(
        {
            "prim_count": engine_result.get("prim_count"),
            "observed_states": engine_result.get("observed_states"),
            "capture": capture,
            "viewport_capture": str(manager.viewport_capture_file),
            "viewport_capture_exists": manager.viewport_capture_file.is_file(),
            "engine_result": str(manager.engine_result_file),
        }
    )
    if failure is None and engine_result.get("status") == "PASS" and capture_passed:
        item["status"] = "PASS"
    else:
        if failure is None:
            failure = RuntimeError(f"Replay engine capture failed: {capture}")
            failure_traceback = ""
        item["error"] = f"{type(failure).__name__}: {failure}"
        item["traceback"] = failure_traceback
    (fixture_dir / "fixture-result.json").write_text(
        json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-report", type=Path, required=True)
    parser.add_argument("--isaac-root", type=Path, default=Path(r"C:\isaacsim"))
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument(
        "--visible-isaac", action="store_true",
        help="Launch Isaac with a visible viewport so official screenshot capture can be verified.",
    )
    args = parser.parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-s2d-replay"
    artifact_dir = (args.artifact_dir or ROOT / "artifacts" / "runs" / run_id).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stored_report = artifact_dir / "stored-provider-results.json"
    result: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "replay",
        "provider_requests": 0,
        "status": "FAIL",
        "fixtures": [],
    }
    try:
        shutil.copy2(args.provider_report.resolve(), stored_report)
        payload = json.loads(stored_report.read_text(encoding="utf-8"))
        fixture_ids = [str(item["fixture_id"]) for item in payload.get("fixtures", [])]
        if len(fixture_ids) != 3 or len(set(fixture_ids)) != 3:
            raise ValueError("S2d requires exactly three distinct stored fixtures")
        for index, fixture_id in enumerate(fixture_ids, start=1):
            print(f"S2D_REPLAY fixture={index}/3 id={fixture_id} phase=START", flush=True)
            item = run_fixture(
                report=stored_report,
                fixture_id=fixture_id,
                artifact_dir=artifact_dir,
                isaac_root=args.isaac_root.resolve(),
                timeout_s=args.timeout_s,
                visible_isaac=args.visible_isaac,
            )
            result["fixtures"].append(item)
            if item.get("status") != "PASS":
                raise RuntimeError(f"Fixture {fixture_id} failed: {item.get('error')}")
            print(f"S2D_REPLAY fixture={index}/3 id={fixture_id} phase=PASS", flush=True)
        fixtures = result["fixtures"]
        assert isinstance(fixtures, list)
        unique_scenes = len({item["scene_id"] for item in fixtures})
        unique_plans = len({item["plan_sha256"] for item in fixtures})
        unique_layout_counts = len({(item["tool_count"], item["object_count"]) for item in fixtures})
        if unique_scenes != 3 or unique_plans != 3 or unique_layout_counts < 2:
            raise RuntimeError("Stored replay scenes do not preserve the required layout diversity")
        result["diversity"] = {
            "unique_scene_ids": unique_scenes,
            "unique_plan_hashes": unique_plans,
            "unique_tool_object_count_pairs": unique_layout_counts,
        }
        result["stored_report"] = str(stored_report)
        result["stored_report_sha256"] = hashlib.sha256(stored_report.read_bytes()).hexdigest()
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
    result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    result_path = artifact_dir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TWINPULSE_S2D_RESULT={result['status']} artifact_dir={artifact_dir}", flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
