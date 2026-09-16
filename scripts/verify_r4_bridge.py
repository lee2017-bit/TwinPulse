"""Finite actual-Isaac acceptance for the authenticated R4 loopback bridge."""

from __future__ import annotations

from http.client import HTTPResponse
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import traceback
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TEMP_PARENT = os.environ.get("TWINPULSE_TEST_TMP")
STATE = TemporaryDirectory(prefix="tmp-r4-bridge-", dir=TEMP_PARENT)
os.environ["TWINPULSE_STATE_DIR"] = str(Path(STATE.name) / "extension-state")

from isaacsim import SimulationApp  # noqa: E402


APP = SimulationApp({
    "headless": True,
    "renderer": "MinimalRendering",
    "disable_viewport_updates": True,
    "width": 640,
    "height": 480,
})

RESULT: dict[str, object] = {
    "status": "FAIL",
    "managed_build_run_pause_reset": {},
    "backend_loss_watchdog": {},
    "lifecycle_cycles": [],
}


class ProductClient:
    def __init__(self, base_url: str, secret: str) -> None:
        self.base_url = base_url
        status, body, response = self.request(
            "/v1/bootstrap", {"role": "product", "secret": secret}, authenticated=False,
        )
        if status != 200:
            raise RuntimeError(f"Product bootstrap failed: {body}")
        self.cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
        self.csrf = str(body["csrf_token"])
        self.lease_id: str | None = None
        self._renew_at = 0.0

    def request(
        self, path: str, body: dict[str, object] | None = None, *, authenticated: bool = True,
    ) -> tuple[int, dict[str, object], HTTPResponse]:
        headers = {"Accept": "application/json", "Origin": self.base_url}
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["Cookie"] = self.cookie
            if body is not None:
                headers["X-TwinPulse-CSRF"] = self.csrf
        request = Request(
            self.base_url + path, data=data, headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            response = urlopen(request, timeout=3.0)
            return response.status, json.loads(response.read().decode("utf-8")), response
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8")), error

    def acquire_lease(self) -> None:
        status, body, _ = self.request("/v1/product/lease", {})
        if status != 200:
            raise RuntimeError(f"Lease acquisition failed: {body}")
        self.lease_id = str(body["control_lease_id"])
        self._renew_at = time.monotonic() + 1.0

    def renew_if_due(self) -> None:
        if self.lease_id is None or time.monotonic() < self._renew_at:
            return
        status, body, _ = self.request(
            "/v1/product/lease/renew", {"control_lease_id": self.lease_id},
        )
        if status != 200:
            raise RuntimeError(f"Lease renewal failed: {body}")
        self._renew_at = time.monotonic() + 1.0

    def state(self) -> dict[str, object]:
        status, body, _ = self.request("/v1/product/state")
        if status != 200:
            raise RuntimeError(f"State request failed: {body}")
        return body

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


def start_backend(directory: Path) -> tuple[subprocess.Popen[str], dict[str, object], str, str]:
    product_secret = secrets.token_urlsafe(32)
    engine_secret = secrets.token_urlsafe(32)
    ready_file = directory / f"backend-{secrets.token_hex(4)}.json"
    environment = os.environ.copy()
    environment["TWINPULSE_PRODUCT_BOOTSTRAP"] = product_secret
    environment["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "twinpulse_backend.py"),
         "--ready-file", str(ready_file)],
        cwd=str(ROOT), env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, creationflags=creationflags,
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"Backend exited before ready: {output[-1000:]}")
        if ready_file.is_file():
            ready = json.loads(ready_file.read_text(encoding="utf-8"))
            return process, ready, product_secret, engine_secret
        time.sleep(0.05)
    process.terminate()
    raise RuntimeError("Backend did not publish its ready file")


def stop_backend(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)


def update_frames(count: int, client: ProductClient | None = None, *, delay_s: float = 0.005) -> None:
    for _ in range(count):
        APP.update()
        if client is not None:
            client.renew_if_due()
        if delay_s:
            time.sleep(delay_s)


def wait_until(
    predicate: Callable[[], object], *, timeout_s: float, client: ProductClient | None = None,
) -> object:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        APP.update()
        if client is not None:
            client.renew_if_due()
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise TimeoutError("Timed out waiting for R4 bridge state")


def wait_operation(client: ProductClient, command_id: str, *, timeout_s: float = 20.0) -> dict[str, object]:
    def find() -> dict[str, object] | None:
        state = client.state()
        for operation in state.get("operations", []):
            if operation.get("command_id") == command_id:
                status = operation.get("status")
                if status in {"succeeded", "failed", "cancelled", "expired", "unknown"}:
                    return operation
        return None

    operation = wait_until(find, timeout_s=timeout_s, client=client)
    assert isinstance(operation, dict)
    if operation.get("status") != "succeeded":
        raise AssertionError(f"Bridge command did not succeed: {operation}")
    return operation


def planar_distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def bridge_threads() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name == "TwinPulseBridgeIO"]


try:
    import omni.kit.app
    import omni.usd

    context = omni.usd.get_context()
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(ROOT / "extensions"))

    for cycle in range(1, 4):
        context.new_stage()
        update_frames(5, delay_s=0.0)
        process, ready, product_secret, engine_secret = start_backend(Path(STATE.name))
        base_url = str(ready["base_url"])
        os.environ["TWINPULSE_BRIDGE_URL"] = base_url
        os.environ["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
        runtime = bridge = None
        cycle_result: dict[str, object] = {"cycle": cycle, "connected": False, "shutdown_clean": False}
        try:
            enabled = manager.set_extension_enabled_immediate("twinpulse.extension", True)
            update_frames(8, delay_s=0.01)
            import twinpulse.extension as extension_module

            extension = extension_module.get_extension()
            if extension is None or extension._bridge_client is None or not extension._managed_mode:
                raise AssertionError("Managed Extension did not start")
            runtime = extension.runtime
            bridge = extension._bridge_client
            wait_until(lambda: bridge.connected, timeout_s=8.0)
            cycle_result["connected"] = True

            if cycle == 1:
                client = ProductClient(base_url, product_secret)
                client.acquire_lease()
                wait_until(
                    lambda: client.state().get("engine_connected")
                    and client.state().get("lease_owned"),
                    timeout_s=8.0, client=client,
                )
                revision = str(ready["revision"])
                artifact_id = str(ready["artifact_id"])

                build = client.command(
                    "r4-build", "build_scene", artifact_id=artifact_id, revision=revision,
                )
                wait_operation(client, str(build["command_id"]), timeout_s=30.0)
                stage = context.get_stage()
                if not stage.GetPrimAtPath("/World/TwinPulse").IsValid():
                    raise AssertionError("Build receipt succeeded without /World/TwinPulse")
                start = runtime.robot_position()

                get_state = client.command("r4-state", "get_state", revision=revision)
                wait_operation(client, str(get_state["command_id"]))
                focus = client.command("r4-focus", "focus_scene", revision=revision)
                wait_operation(client, str(focus["command_id"]))
                run = client.command("r4-run", "run", revision=revision)
                wait_operation(client, str(run["command_id"]))
                update_frames(180, client)
                moved = planar_distance(start, runtime.robot_position())
                if moved <= 0.05:
                    raise AssertionError(f"Managed Run did not move the AGV: {moved}")

                pause = client.command("r4-pause", "pause", revision=revision)
                wait_operation(client, str(pause["command_id"]))
                paused_before = runtime.robot_position()
                update_frames(20, client)
                pause_drift = planar_distance(paused_before, runtime.robot_position())
                if pause_drift >= 0.002:
                    raise AssertionError(f"Managed Pause drifted: {pause_drift}")

                reset = client.command("r4-reset", "reset", revision=revision)
                wait_operation(client, str(reset["command_id"]))
                update_frames(20, client)
                reset_error = planar_distance(start, runtime.robot_position())
                if reset_error >= 0.03:
                    raise AssertionError(f"Managed Reset missed start: {reset_error}")
                RESULT["managed_build_run_pause_reset"] = {
                    "prim_count": runtime.compiler.owned_prim_count(),
                    "moved_m": moved,
                    "pause_drift_m": pause_drift,
                    "reset_error_m": reset_error,
                    "get_state": "PASS",
                    "focus": "PASS",
                    "passed": True,
                }

                watchdog_run = client.command("r4-watchdog-run", "run", revision=revision)
                wait_operation(client, str(watchdog_run["command_id"]))
                update_frames(60, client)
                before_loss = runtime.robot_position()
                stop_backend(process)
                wait_until(lambda: runtime.state != "running", timeout_s=3.5)
                stopped = runtime.robot_position()
                stop_distance = planar_distance(before_loss, stopped)
                update_frames(40, delay_s=0.02)
                post_stop_drift = planar_distance(stopped, runtime.robot_position())
                wait_until(lambda: not bridge.connected, timeout_s=4.0)
                update_frames(5, delay_s=0.02)
                snapshot = bridge.adapter.snapshot()
                watchdog_passed = bool(
                    runtime.state != "running"
                    and snapshot.safety_state == "bridge_disconnected"
                    and snapshot.safety_reason == "Backend connection lost"
                    and not bridge.connected
                    and stop_distance < 1.0
                    and post_stop_drift < 0.002
                )
                RESULT["backend_loss_watchdog"] = {
                    "runtime_state": runtime.state,
                    "safety_state": snapshot.safety_state,
                    "safety_reason": snapshot.safety_reason,
                    "stop_distance_m": stop_distance,
                    "post_stop_drift_m": post_stop_drift,
                    "bridge_connected": bridge.connected,
                    "passed": watchdog_passed,
                }
                if not watchdog_passed:
                    raise AssertionError(f"Backend loss did not fail safe: {RESULT['backend_loss_watchdog']}")
        finally:
            extension = None
            manager.set_extension_enabled_immediate("twinpulse.extension", False)
            update_frames(8, delay_s=0.01)
            stop_backend(process)
            os.environ.pop("TWINPULSE_BRIDGE_URL", None)
            os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", None)
            cycle_result["shutdown_clean"] = bool(
                runtime is not None and runtime.shutdown_complete and not bridge_threads()
            )
            cycle_result["manager_enable_return"] = bool(locals().get("enabled", False))
            cast_cycles = RESULT["lifecycle_cycles"]
            assert isinstance(cast_cycles, list)
            cast_cycles.append(cycle_result)

    lifecycle = RESULT["lifecycle_cycles"]
    assert isinstance(lifecycle, list)
    RESULT["status"] = "PASS" if (
        RESULT["managed_build_run_pause_reset"].get("passed") is True
        and RESULT["backend_loss_watchdog"].get("passed") is True
        and len(lifecycle) == 3
        and all(item.get("connected") and item.get("shutdown_clean") for item in lifecycle)
    ) else "FAIL"
except Exception as error:
    RESULT["error"] = f"{type(error).__name__}: {error}"
    RESULT["traceback"] = traceback.format_exc()
finally:
    os.environ.pop("TWINPULSE_BRIDGE_URL", None)
    os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", None)
    print("TWINPULSE_R4_RESULT=" + json.dumps(RESULT, ensure_ascii=False, sort_keys=True), flush=True)
    APP.close()
    STATE.cleanup()

raise SystemExit(0 if RESULT["status"] == "PASS" else 1)
