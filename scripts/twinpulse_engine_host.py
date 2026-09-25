"""Owned Isaac Sim host for the R6 local product launcher."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from twinpulse_capture_contract import CaptureAttempt  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--viewport-capture", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--maximum-runtime-s", type=float, default=24 * 60 * 60)
    return parser.parse_args()


ARGS = _arguments()

from isaacsim import SimulationApp  # noqa: E402


APP = SimulationApp({
    "headless": ARGS.headless,
    "renderer": "RaytracedLighting",
    "disable_viewport_updates": False,
    "width": 960,
    "height": 640,
})


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


async def _capture(path: Path) -> bool:
    import omni.kit.app
    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

    viewport = get_active_viewport()
    if viewport is None:
        return False
    viewport.resolution = (960, 640)
    await omni.kit.app.get_app().next_update_async()
    capture = capture_viewport_to_file(viewport, file_path=str(path), is_hdr=False)
    await capture.wait_for_result(completion_frames=5)
    return path.is_file() and path.stat().st_size > 0


def _active_camera_name() -> str:
    from omni.kit.viewport.utility import get_active_viewport

    viewport = get_active_viewport()
    if viewport is None:
        return "viewport_unavailable"
    for name in ("camera_path", "cameraPath"):
        value = getattr(viewport, name, None)
        if value:
            return str(value)
    return "active_viewport"


def _attempt_path(final_path: Path, attempt: int) -> Path:
    return final_path.with_name(f"{final_path.stem}.attempt-{attempt}{final_path.suffix}")


def _inspect_capture(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "FAIL", "reason": "capture_missing"}
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stats = ImageStat.Stat(rgb)
            extrema = rgb.getextrema()
            dynamic_range = max(high - low for low, high in extrema)
            mean = sum(stats.mean) / len(stats.mean)
            black = dynamic_range < 4 or mean < 2.0
            width, height = rgb.size
    except Exception as error:
        return {"status": "FAIL", "reason": f"capture_inspection_failed: {error}"}
    return {
        "status": "PASS" if not black else "FAIL",
        "reason": None if not black else "black_or_constant_frame",
        "path": str(path.resolve()), "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "width": width, "height": height, "dynamic_range": dynamic_range,
        "mean_luma_approx": mean,
    }


def main() -> int:
    result: dict[str, object] = {
        "schema_version": "1.0", "status": "FAIL", "capture": {"status": "NOT_RUN"},
        "trajectory": [], "observed_states": [], "max_movement_m": 0.0,
    }
    manager = extension = None
    capture_task: asyncio.Task[bool] | None = None
    capture_attempt: CaptureAttempt | None = None
    capture_attempts: list[dict[str, object]] = []
    capture_finished = False
    capture_requested_frame: int | None = None
    latest_snapshot = None
    shutdown_started: float | None = None
    frame = 0
    start_position: tuple[float, float, float] | None = None
    observed_states: set[str] = set()
    trajectory: list[dict[str, object]] = []
    maximum_movement = 0.0

    def capture_report(current: dict[str, object], *, final_path: Path | None = None) -> dict[str, object]:
        report = dict(current)
        report["max_attempts"] = 2
        report["attempts"] = [dict(item) for item in capture_attempts]
        if final_path is not None:
            report["path"] = str(final_path.resolve())
            decoded = report.get("decoded")
            if isinstance(decoded, dict):
                for name, value in decoded.items():
                    if name not in {"status", "path"}:
                        report[name] = value
        return report

    def start_capture(snapshot: object, requested_frame: int) -> None:
        nonlocal capture_task, capture_attempt
        attempt_number = len(capture_attempts) + 1
        path = _attempt_path(ARGS.viewport_capture, attempt_number)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        if attempt_number == 1:
            ARGS.viewport_capture.unlink(missing_ok=True)
        capture_attempt = CaptureAttempt(
            output_path=path,
            attempt=attempt_number,
            requested_frame=requested_frame,
            stage_epoch=str(snapshot.stage_epoch),
            applied_revision=str(snapshot.applied_revision),
            camera=_active_camera_name(),
            timeout_s=15.0,
            settle_s=0.25,
        )
        capture_task = asyncio.ensure_future(_capture(path))
        result["capture"] = capture_report(capture_attempt.public())

    def update_capture(snapshot: object, *, allow_retry: bool) -> None:
        nonlocal capture_task, capture_attempt, capture_finished
        if capture_attempt is None or capture_finished:
            return
        if capture_task is not None and capture_task.done() and not capture_attempt.public()["task_returned"]:
            try:
                succeeded = capture_task.result()
            except asyncio.CancelledError as error:
                capture_attempt.mark_task_exception(error)
            except Exception as error:
                capture_attempt.mark_task_exception(error)
            else:
                capture_attempt.mark_task_returned(
                    bool(succeeded), reason=None if succeeded else "viewport_missing",
                )
        current = capture_attempt.poll(
            str(snapshot.stage_epoch),
            str(snapshot.applied_revision) if snapshot.applied_revision is not None else None,
            _inspect_capture,
        )
        result["capture"] = capture_report(current)
        if not capture_attempt.terminal:
            return

        capture_attempts.append(current)
        if current["status"] == "PASS":
            capture_attempt.output_path.replace(ARGS.viewport_capture)
            result["capture"] = capture_report(current, final_path=ARGS.viewport_capture)
            capture_finished = True
            capture_task = None
            return
        if allow_retry and capture_attempt.retry_allowed(max_attempts=2):
            if capture_task is not None and not capture_task.done():
                capture_task.cancel()
            capture_task = None
            capture_attempt = None
            start_capture(snapshot, frame)
            return
        if capture_task is not None and not capture_task.done():
            capture_task.cancel()
        capture_task = None
        capture_finished = True
        result["capture"] = capture_report(current)

    try:
        import omni.kit.app
        import omni.usd

        context = omni.usd.get_context()
        context.new_stage()
        for _ in range(8):
            APP.update()

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.add_path(str(ROOT / "extensions"))
        manager.set_extension_enabled_immediate("twinpulse.extension", True)
        for _ in range(12):
            APP.update()
            time.sleep(0.01)

        import twinpulse.extension as extension_module

        extension = extension_module.get_extension()
        if extension is None or extension._bridge_client is None or not extension._managed_mode:
            raise RuntimeError("Managed TwinPulse Extension did not start")
        bridge = extension._bridge_client
        deadline = time.monotonic() + 90.0
        while not bridge.connected and time.monotonic() < deadline:
            APP.update()
            time.sleep(0.02)
        if not bridge.connected:
            raise TimeoutError("Managed bridge did not authenticate before timeout")

        started = time.monotonic()
        while True:
            stop_requested = ARGS.stop_file.exists()
            if stop_requested and shutdown_started is None:
                shutdown_started = time.monotonic()
            if stop_requested and (capture_attempt is None or capture_finished):
                break
            if (
                shutdown_started is not None
                and time.monotonic() - shutdown_started >= 15.0
                and capture_attempt is not None
                and not capture_attempt.terminal
            ):
                capture_attempt.force_timeout()
                if latest_snapshot is not None:
                    update_capture(latest_snapshot, allow_retry=False)
                break
            if time.monotonic() - started > ARGS.maximum_runtime_s:
                raise TimeoutError("Owned Isaac host exceeded its finite maximum runtime")
            APP.update()
            frame += 1
            state = extension.runtime.state
            observed_states.add(state)
            try:
                position: tuple[float, float, float] | None = extension.runtime.robot_position()
            except RuntimeError as error:
                if str(error) != "Scene has not been compiled":
                    raise
                position = None
            if state == "running" and start_position is None and position is not None:
                start_position = position
            if start_position is not None and position is not None:
                movement = math.hypot(position[0] - start_position[0], position[1] - start_position[1])
                maximum_movement = max(maximum_movement, movement)
            if frame % 10 == 0 and len(trajectory) < 2_000:
                snapshot = bridge.adapter.snapshot()
                latest_snapshot = snapshot
                trajectory.append({
                    "sequence": snapshot.sequence, "runtime_state": snapshot.runtime_state,
                    "sim_time_s": snapshot.sim_time_s,
                    "position_m": list(position) if position is not None else None,
                    "distance_to_goal_m": snapshot.distance_to_goal_m,
                    "cross_track_error_m": snapshot.cross_track_error_m,
                    "applied_revision": snapshot.applied_revision,
                })
                if (
                    snapshot.applied_revision is not None and capture_attempt is None
                    and not capture_finished and not stop_requested
                    and result["capture"] == {"status": "NOT_RUN"}
                    and capture_requested_frame is None
                ):
                    capture_requested_frame = frame
                if (
                    capture_requested_frame is not None
                    and frame - capture_requested_frame >= 30
                    and not stop_requested
                ):
                    start_capture(snapshot, frame)
                    capture_requested_frame = None
            if capture_attempt is not None and latest_snapshot is not None:
                update_capture(latest_snapshot, allow_retry=not stop_requested)
            time.sleep(0.005)

        for _ in range(10):
            APP.update()
        snapshot = bridge.adapter.snapshot()
        result.update({
            "status": "PASS" if result["capture"].get("status") == "PASS" else "FAIL",
            "engine_connected": bridge.connected,
            "engine_session_id": snapshot.engine_session_id,
            "stage_epoch": snapshot.stage_epoch,
            "applied_revision": snapshot.applied_revision,
            "runtime_state": snapshot.runtime_state,
            "prim_count": extension.runtime.compiler.owned_prim_count(),
            "max_movement_m": maximum_movement,
            "observed_states": sorted(observed_states),
            "trajectory": trajectory,
        })
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
    finally:
        try:
            if manager is not None:
                extension = None
                manager.set_extension_enabled_immediate("twinpulse.extension", False)
                for _ in range(8):
                    APP.update()
        except Exception:
            pass
        _write_json_atomic(ARGS.result_file, result)
        print("TWINPULSE_ENGINE_HOST_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        APP.close()
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
