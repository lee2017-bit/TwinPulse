# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
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
APP = None


def _mission_visual_marker(stage):
    # No scene may have been built when generation/registration fails. Do not
    # replace that primary cause with an unrelated shutdown-report exception.
    if stage is None:
        return None
    prim=stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission')
    return prim.GetCustomData() if prim else None


def _room_display_marker(stage):
    """Bounded actual USD evidence; catalog visuals do not establish photo fidelity."""
    if stage is None:
        return None
    prim=stage.GetPrimAtPath('/World/TwinPulse/Presentation/RoomModels')
    if not prim:
        return None
    from pxr import Usd, UsdGeom, UsdPhysics
    members=list(Usd.PrimRange(prim))
    groups=[p for p in prim.GetChildren() if p.GetName().startswith('Item_')]
    return dict(catalog_version=prim.GetCustomDataByKey('catalogVersion'),
        scene_revision=prim.GetCustomDataByKey('sceneRevision'),
        appearance_status=prim.GetCustomDataByKey('appearanceStatus'),
        motion_authorized=prim.GetCustomDataByKey('motionAuthorized'),
        groups=len(groups),kinds=sorted({p.GetCustomDataByKey('catalogKind') for p in groups}),
        mesh_count=sum(p.IsA(UsdGeom.Mesh) for p in members),
        physics_schema_count=sum(p.HasAPI(api) for p in members
            for api in (UsdPhysics.CollisionAPI,UsdPhysics.RigidBodyAPI,UsdPhysics.ArticulationRootAPI)))


def _startup_profile() -> dict[str, object]:
    """Bounded native-package provenance without importing another dependency.

    A failing Isaac import may leave NumPy/SciPy only partially initialized;
    the observed module, not a separately imported candidate, is what matters.
    Paths are classified and fingerprinted, never copied into the report.
    """
    packages: dict[str, object] = {}
    for name in ("numpy", "scipy"):
        module = sys.modules.get(name)
        origin = getattr(module, "__file__", None) if module is not None else None
        version = getattr(module, "__version__", None) if module is not None else None
        if not isinstance(origin, str) or not origin:
            packages[name] = {"loaded": module is not None, "origin_class": "unknown",
                              "origin_sha256": None, "version": None}
            continue
        normalized = origin.replace("\\", "/").lower()
        origin_class = ("extension_prebundle" if "pip_prebundle" in normalized
                        else "isaac_kit_python" if "/kit/python/" in normalized
                        else "other_local_path")
        packages[name] = {
            "loaded": True, "origin_class": origin_class,
            "origin_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "version": version[:48] if isinstance(version, str) else None,
        }
    return {"schema_version": "engine-startup-profile-1.0",
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "packages": packages}


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _start_simulation_app() -> bool:
    """Record failures that occur before main() can write its result file."""
    global APP
    phase = "isaac_import"
    try:
        from isaacsim import SimulationApp

        phase = "simulation_app_init"
        APP = SimulationApp({
            "headless": ARGS.headless,
            "renderer": "RaytracedLighting",
            "disable_viewport_updates": False,
            "width": 960,
            "height": 640,
        })
        return True
    except Exception as error:
        result = {
            "schema_version": "1.0", "status": "FAIL",
            "startup_phase": phase, "error_type": type(error).__name__,
            "startup_profile": _startup_profile(),
            "error": f"{type(error).__name__}: {error}",
            "traceback": traceback.format_exc(),
            "capture": {"status": "NOT_RUN"}, "trajectory": [],
            "observed_states": [], "max_movement_m": 0.0,
        }
        try:
            _write_json_atomic(ARGS.result_file, result)
        except OSError:
            pass
        print(f"TWINPULSE_ENGINE_STARTUP_FAILED phase={phase} type={type(error).__name__}", flush=True)
        return False


async def _capture(path: Path, *, ready_timeout_s: float = 15.0) -> bool:
    import omni.kit.app
    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

    viewport = get_active_viewport()
    deadline=time.monotonic()+ready_timeout_s
    while viewport is None:
        if time.monotonic()>=deadline:return False
        # The first scene ACK can precede the active viewport. Yield Kit
        # updates within the existing attempt deadline, not two instant retries.
        # CaptureAttempt still checks stage/revision and cancels timed-out work.
        await omni.kit.app.get_app().next_update_async()
        viewport=get_active_viewport()
    viewport.resolution = (960, 640)
    await omni.kit.app.get_app().next_update_async()
    capture = capture_viewport_to_file(viewport, file_path=str(path), is_hdr=False)
    await capture.wait_for_result(completion_frames=5)
    # GPU completion is not async file-writer completion. CaptureAttempt
    # separately waits for nonempty, stable, decoded bytes within 15 seconds
    # and rejects identity changes. Returning False here prematurely labels
    # a late writer as viewport_missing and consumes both retries instantly.
    return True


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
    preview_observations = []
    last_preview_identity = None
    mission_visual_observations = []
    last_mission_visual_identity = None
    maximum_movement = 0.0
    live_viewport = None
    from twinpulse_update_probe import UpdateProbe
    update_probe=UpdateProbe()

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
            if bridge.last_error == 'BridgeProtocolError: Backend rejected request: bootstrap_rejected':
                break  # This worker already terminated; do not idle for another90s.
            time.sleep(0.02)
        if not bridge.connected:
            # Never persist bootstrap/authentication material or raw error text.
            import re
            last_error=bridge.last_error or ''
            error_type=last_error.split(':',1)[0]
            status=re.search(r'HTTP Error (\d{3})\b',last_error)
            result['bridge_diagnostic']={'connected':False,
                'error_type':error_type if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,60}',error_type) else 'UNCLASSIFIED',
                'http_status':int(status.group(1)) if status else None,
                'error_code':'bootstrap_rejected' if last_error == 'BridgeProtocolError: Backend rejected request: bootstrap_rejected' else None}
            raise TimeoutError("Managed bridge did not authenticate before timeout")
        from twinpulse_live_viewport import LiveViewportPublisher
        live_viewport = LiveViewportPublisher(bridge)
        live_viewport.start()

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
            update_probe.begin();app_update_started=time.monotonic()
            APP.update()
            app_update_elapsed=time.monotonic()-app_update_started
            update_diagnostic=update_probe.finish(app_update_elapsed)
            frame += 1
            viewport_started=time.monotonic()
            try:
                # Planned-but-not-yet-scheduled initial capture is pending too.
                live_viewport.fleet_runtime.snapshot_capture_pending=bool(ARGS.viewport_capture) and not capture_finished
                prior_host=live_viewport.fleet_runtime.host_timing
                live_viewport.fleet_runtime.host_timing=dict(app_update_s=app_update_elapsed,
                    previous_viewport_s=prior_host.get('_viewport_s',0.),previous_tail_s=prior_host.get('_tail_s',0.),**update_diagnostic)
                live_viewport.update(bridge.adapter.snapshot())
            except Exception as error:
                live_viewport.last_error = "viewport_update_" + type(error).__name__[:60]
            viewport_elapsed=time.monotonic()-viewport_started
            tail_started=time.monotonic()
            state = extension.runtime.state
            observed_states.add(state)
            # Inspect only owned visual content. It is not robot telemetry and
            # must never make the timeline play or create a driven articulation.
            from pxr import Usd, UsdGeom, UsdPhysics
            preview_stage = extension.runtime.compiler.stage
            active = preview_stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission') if preview_stage else None
            if active:
                active_identity = (active.GetCustomDataByKey('displayStatus'),
                                   str(UsdGeom.Imageable(active).ComputeVisibility()))
                if active_identity != last_mission_visual_identity and len(mission_visual_observations) < 64:
                    last_mission_visual_identity = active_identity
                    mission_visual_observations.append({'status':active_identity[0], 'visibility':active_identity[1],
                        'cursor':getattr(bridge.adapter,'_mission_visual_cursor',None)})
            preview = preview_stage.GetPrimAtPath('/World/TwinPulse/Presentation/BurgerPhotoPreview') if preview_stage else None
            if preview and preview.GetCustomDataByKey('simulationPlanId'):
                visible = str(UsdGeom.Imageable(preview).ComputeVisibility())
                identity = (preview.GetCustomDataByKey('simulationPlanId'), visible,
                            bool(extension.runtime.site_plan), state)
                if identity != last_preview_identity and len(preview_observations) < 32:
                    last_preview_identity = identity
                    prims = list(Usd.PrimRange(preview, Usd.TraverseInstanceProxies()))
                    preview_observations.append({
                        'plan_id':identity[0], 'visibility':visible, 'runtime_state':state,
                        'timeline_playing':extension.runtime._timeline.is_playing(),
                        'site_plan_present':identity[2],
                        'sim_burger_present':bool(preview_stage.GetPrimAtPath('/World/TwinPulse/SimBurger')),
                        'position_m':list(preview.GetAttribute('xformOp:translate').Get()),
                        'scene_revision':preview.GetCustomDataByKey('sceneRevision'),
                        'motion_authorized':preview.GetCustomDataByKey('motionAuthorized'),
                        'mesh_count':sum(p.IsA(UsdGeom.Mesh) for p in prims),
                        'physics_schema_count':sum(p.HasAPI(UsdPhysics.CollisionAPI) or p.HasAPI(UsdPhysics.RigidBodyAPI)
                            or p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in prims),
                    })
            try:
                # v2 room builds intentionally have no driven Robot prim. The
                # visual Burger is not physical position telemetry. Still fail
                # loudly for a missing robot in a compiled v1 driven scene.
                position: tuple[float, float, float] | None = (
                    extension.runtime.robot_position()
                    if extension.runtime.compiler.bundle is not None or extension.runtime.site_plan is not None else None
                )
            except RuntimeError as error:
                if str(error) != "Scene has not been compiled":
                    raise
                position = None
            if state == "running" and start_position is None and position is not None:
                start_position = position
            if start_position is not None and position is not None:
                movement = math.hypot(position[0] - start_position[0], position[1] - start_position[1])
                maximum_movement = max(maximum_movement, movement)
            if frame % 10 == 0:
                snapshot = bridge.adapter.snapshot()
                latest_snapshot = snapshot
                # Bounded diagnostic history must not disable capture lifecycle
                # or leave every later robot permanently waiting for warmup.
                if len(trajectory) < 2_000:
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
            live_viewport.fleet_runtime.host_timing.update(_viewport_s=viewport_elapsed,_tail_s=time.monotonic()-tail_started)

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
            "simulation_preview_observations": preview_observations,
            "mission_visual_observations": mission_visual_observations,
            "mission_visual_status": bridge.mission_visual_status,
            "mission_visual_error": bridge.mission_visual_error,
            "mission_visual_cursor": getattr(bridge.adapter,'_mission_visual_cursor',None),
            "mission_visual_marker": _mission_visual_marker(extension.runtime.compiler.stage),
            "room_display_marker": _room_display_marker(extension.runtime.compiler.stage),
        })
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
    finally:
        update_probe.close()
        if live_viewport is not None:
            live_viewport.stop()
            result['live_viewport'] = {'sent':live_viewport.sent,'dropped':live_viewport.dropped,
                                       'capture_timeouts':live_viewport.capture_timeouts,
                                       'capture_recoveries':live_viewport.capture_recoveries,
                                       'error':live_viewport.last_error or live_viewport.transport_error}
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
    raise SystemExit(main() if _start_simulation_app() else 1)
