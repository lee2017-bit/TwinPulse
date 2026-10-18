# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite Isaac Sim 6.0.1 acceptance test for TwinPulse M1."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import traceback

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ["TWINPULSE_STATE_DIR"] = str(REPO_ROOT / ".nonexistent-runtime-test-state")

from isaacsim import SimulationApp


APP = SimulationApp(
    {
        "headless": True,
        "renderer": "MinimalRendering",
        "disable_viewport_updates": True,
        "width": 640,
        "height": 480,
    }
)

EXTENSIONS_PATH = REPO_ROOT / "extensions"
RESULT = {
    "status": "FAIL",
    "isaac_root": "C:/isaacsim",
    "extension": "twinpulse.extension",
    "owned_root": "/World/TwinPulse",
    "run_reset_cycles": [],
    "lifecycle_cycles": [],
    "visual_contract": {},
    "m2b_contract": {},
    "long_route_contract": {},
    "robot_dynamics_contract": {},
    "artifact_contract": {},
}


def distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second, strict=True)))


def planar_distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def exercise_enabled_extension(manager: object, lifecycle_cycle: int) -> tuple[bool, object, int, int]:
    """Exercise an enabled instance, then return without retaining it in this frame."""
    enabled = manager.set_extension_enabled_immediate("twinpulse.extension", True)
    for _ in range(5):
        APP.update()
    import twinpulse.extension as extension_module

    extension = extension_module.get_extension()
    if extension is None:
        raise RuntimeError("Extension manager did not create TwinPulseExtension")

    first_count = extension.runtime.build_sample_scene()
    second_count = extension.runtime.build_sample_scene()
    if first_count != second_count:
        raise AssertionError(f"Idempotent compile failed: {first_count} != {second_count}")

    if lifecycle_cycle == 1:
        from pxr import UsdGeom, UsdLux

        stage = omni.usd.get_context().get_stage()
        camera = stage.GetPrimAtPath("/World/TwinPulse/Presentation/Camera")
        dome = stage.GetPrimAtPath("/World/TwinPulse/Presentation/DomeLight")
        sun = stage.GetPrimAtPath("/World/TwinPulse/Presentation/SunLight")
        goal = stage.GetPrimAtPath("/World/TwinPulse/Task/Goal")
        visual_contract = {
            "camera": bool(camera.IsValid() and camera.IsA(UsdGeom.Camera)),
            "dome_light": bool(dome.IsValid() and dome.IsA(UsdLux.DomeLight)),
            "sun_light": bool(sun.IsValid() and sun.IsA(UsdLux.DistantLight)),
            "goal_marker": bool(goal.IsValid() and goal.IsA(UsdGeom.Cylinder)),
        }
        visual_contract["passed"] = all(visual_contract.values())
        RESULT["visual_contract"] = visual_contract

    if lifecycle_cycle == 1:
        extension._open_settings()
        settings_visible = bool(extension._settings_window and extension._settings_window.visible)
        extension._close_settings()
        extension._show_approximation_warning()
        warning_visible = bool(extension._warning_window and extension._warning_window.visible)
        extension._close_warning()
        RESULT["m2b_contract"]["settings_window"] = settings_visible
        RESULT["m2b_contract"]["warning_window"] = warning_visible
        fixed = extension.runtime.compiler.bundle
        if fixed is None:
            raise AssertionError("sample fixture bundle is unavailable")
        from twinpulse_core import EpisodeSample, assess_episode

        stage = omni.usd.get_context().get_stage()
        support_paths = [f"/World/TwinPulse/Robot/{item.id}" for item in fixed.robot.support_wheels]
        support_joint_paths = [f"{path}_joint" for path in support_paths]
        observed_support_wheels = sum(stage.GetPrimAtPath(path).IsValid() for path in support_paths)
        support_structure = {
            "profile_id": fixed.robot.id,
            "profile_metadata": stage.GetPrimAtPath("/World/TwinPulse").GetCustomDataByKey(
                "twinpulseRobotProfileId"
            ),
            "drive_wheel_count": fixed.robot.drive_wheel_count,
            "expected_support_wheels": len(fixed.robot.support_wheels),
            "observed_support_wheels": observed_support_wheels,
            "support_prims": support_paths,
            "support_joints_valid": all(stage.GetPrimAtPath(path).IsValid() for path in support_joint_paths),
        }
        support_structure["passed"] = bool(
            support_structure["drive_wheel_count"] == 2
            and support_structure["profile_metadata"] == fixed.robot.id
            and observed_support_wheels == len(fixed.robot.support_wheels)
            and support_structure["support_joints_valid"]
        )
        RESULT["robot_dynamics_contract"]["support_structure"] = support_structure

        for run_cycle in range(1, 4):
            extension.reset()
            for _ in range(20):
                APP.update()
            start = extension.runtime.robot_position()
            extension.run()
            samples = []
            for frame in range(540):
                APP.update()
                if frame >= 20:
                    position, attitude = extension.runtime.robot_pose_3d()
                    samples.append(EpisodeSample(frame / 60.0, position, attitude))
            end = samples[-1].position_m
            moved = planar_distance(start, end)
            goal_error = planar_distance(end, extension.runtime.compiler.bundle.task.goal.position_m)

            runtime_state_before_pause = extension.runtime.state
            assessment = assess_episode(
                fixed,
                samples,
                final_state=runtime_state_before_pause,
                observed_support_wheels=observed_support_wheels,
            )
            extension.pause()
            physics_steps = extension.runtime.physics_steps
            paused_before = extension.runtime.robot_position()
            for _ in range(15):
                APP.update()
            paused_after = extension.runtime.robot_position()
            pause_drift = distance(paused_before, paused_after)

            runtime_state_before_reset = extension.runtime.state
            extension.reset()
            for _ in range(20):
                APP.update()
            reset = extension.runtime.robot_position()
            reset_error = distance(start, reset)
            passed = (
                moved > 0.05
                and goal_error <= extension.runtime.compiler.bundle.task.position_tolerance_m
                and runtime_state_before_pause == "completed"
                and assessment.passed
                and 0.0 < end[2] < 0.30
                and pause_drift < 0.001
                and reset_error < 0.02
            )
            RESULT["run_reset_cycles"].append(
                {
                    "cycle": run_cycle,
                    "start_position_m": start,
                    "end_position_m": end,
                    "moved_m": moved,
                    "goal_error_m": goal_error,
                    "ground_contact_height_ok": 0.0 < end[2] < 0.30,
                    "pause_drift_m": pause_drift,
                    "physics_steps": physics_steps,
                    "reset_error_m": reset_error,
                    "runtime_state_before_reset": runtime_state_before_reset,
                    "runtime_state_before_pause": runtime_state_before_pause,
                    "episode_assessment": assessment.to_dict(),
                    "passed": passed,
                }
            )

        # Reproduce the image-generated scene's long center-aisle drive.  The old
        # open-loop controller accumulated enough yaw error over ~6.9 m to enter a
        # rack; the feedback controller must remain tightly centered end-to-end.
        from twinpulse_core import ShapeSpec, Transform

        long_objects = tuple(
            replace(
                item,
                transform=Transform((3.45, item.transform.position_m[1], item.transform.position_m[2])),
                # The 18 x 12 m floor is a regression for the generated scene
                # that became unstable when compiled as one scaled cube.
                shape=ShapeSpec(
                    "box",
                    (18.0, 12.0, item.shape.dimensions_m[2])
                    if item.id == "floor_main"
                    else (8.0, *item.shape.dimensions_m[1:]),
                ),
            )
            if item.id in {"floor_main", "wall_left", "wall_right"}
            else item
            for item in fixed.scene.objects
        )
        long_bundle = replace(
            fixed,
            scene=replace(fixed.scene, id="warehouse_long_route_v1", objects=long_objects),
            task=replace(
                fixed.task,
                id="long_route_v1",
                goal=replace(fixed.task.goal, position_m=(6.9, 0.0, 0.0)),
            ),
        )
        extension.runtime.build_scene(long_bundle)
        floor_geometry = stage.GetPrimAtPath("/World/TwinPulse/Environment/floor_main/geometry")
        large_floor_mesh = bool(
            floor_geometry.IsValid()
            and floor_geometry.GetTypeName() == "Mesh"
            and not floor_geometry.GetAttribute("xformOp:scale").IsValid()
        )
        extension.reset()
        for _ in range(20):
            APP.update()
        extension.run()
        long_samples = []
        for frame in range(2100):
            APP.update()
            if frame >= 20:
                position, attitude = extension.runtime.robot_pose_3d()
                long_samples.append(EpisodeSample(frame / 60.0, position, attitude))
            if extension.runtime.state in {"completed", "off_route", "unstable"}:
                break
        long_end = extension.runtime.robot_position()
        long_goal_error = planar_distance(long_end, long_bundle.task.goal.position_m)
        long_assessment = assess_episode(
            long_bundle,
            long_samples,
            final_state=extension.runtime.state,
            observed_support_wheels=observed_support_wheels,
        )
        RESULT["long_route_contract"] = {
            "end_position_m": long_end,
            "goal_error_m": long_goal_error,
            "maximum_cross_track_error_m": long_assessment.maximum_cross_track_error_m,
            "runtime_state": extension.runtime.state,
            "large_floor_mesh": large_floor_mesh,
            "episode_assessment": long_assessment.to_dict(),
            "passed": long_assessment.passed and large_floor_mesh,
        }
        extension.reset()

        from twinpulse_core import SceneToolRegistry, demo_warehouse_tool_plan, fixed_warehouse_bundle

        fixed = fixed_warehouse_bundle()
        extension.runtime.build_sample_scene()
        generated = SceneToolRegistry().execute(demo_warehouse_tool_plan())
        stage = omni.usd.get_context().get_stage()
        before_failed_replace_id = stage.GetPrimAtPath("/World/TwinPulse").GetCustomDataByKey(
            "twinpulseSceneId"
        )
        before_failed_replace_count = extension.runtime.compiler.owned_prim_count()
        before_failed_replace_receipt = extension.runtime.compiler.build_receipt
        original_create_scene_object = extension.runtime.compiler._create_scene_object

        def fail_scene_object(_item: object) -> None:
            raise RuntimeError("intentional replacement failure")

        extension.runtime.compiler._create_scene_object = fail_scene_object
        failed_replace_raised = False
        try:
            extension.runtime.build_scene(generated)
        except RuntimeError as error:
            failed_replace_raised = "previous geometry and identity restored" in str(error)
        finally:
            extension.runtime.compiler._create_scene_object = original_create_scene_object
        after_failed_replace_id = stage.GetPrimAtPath("/World/TwinPulse").GetCustomDataByKey(
            "twinpulseSceneId"
        )
        failed_replace_preserved = bool(
            failed_replace_raised
            and before_failed_replace_id == after_failed_replace_id
            and before_failed_replace_count == extension.runtime.compiler.owned_prim_count()
            and before_failed_replace_receipt == extension.runtime.compiler.build_receipt
            and extension.runtime.compiler.bundle == fixed
        )

        generated_count = extension.runtime.build_scene(generated)
        generated_id = stage.GetPrimAtPath("/World/TwinPulse").GetCustomDataByKey("twinpulseSceneId")
        generated_applied = generated_id == generated.scene.id and extension.runtime.compiler.bundle == generated
        extension.runtime.build_sample_scene()
        fallback_rejected = False
        try:
            extension.runtime.build_scene(None)
        except RuntimeError:
            fallback_rejected = True
        RESULT["m2b_contract"]["generated_bundle_applied"] = generated_applied
        RESULT["m2b_contract"]["generated_prim_count"] = generated_count
        RESULT["m2b_contract"]["failed_replace_preserved"] = failed_replace_preserved
        RESULT["m2b_contract"]["implicit_sample_fallback_rejected"] = fallback_rejected
        RESULT["m2b_contract"]["passed"] = all(
            (settings_visible, warning_visible, generated_applied, failed_replace_preserved, fallback_rejected)
        )

    runtime = extension.runtime
    runtime._status_callback = None
    return bool(enabled), runtime, first_count, second_count


try:
    import omni.kit.app
    import omni.usd

    context = omni.usd.get_context()
    context.new_stage()
    for _ in range(10):
        APP.update()

    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(EXTENSIONS_PATH))

    for lifecycle_cycle in range(1, 4):
        enabled, runtime, first_count, second_count = exercise_enabled_extension(manager, lifecycle_cycle)
        manager.set_extension_enabled_immediate("twinpulse.extension", False)
        for _ in range(5):
            APP.update()
        lifecycle_passed = runtime.shutdown_complete and not runtime.has_active_subscription
        RESULT["lifecycle_cycles"].append(
            {
                "cycle": lifecycle_cycle,
                "manager_enable_return": bool(enabled),
                "prim_count_first": first_count,
                "prim_count_second": second_count,
                "shutdown_complete": runtime.shutdown_complete,
                "active_subscription_after_shutdown": runtime.has_active_subscription,
                "passed": lifecycle_passed and first_count == second_count,
            }
        )
    RESULT["status"] = "PASS" if (
        len(RESULT["run_reset_cycles"]) == 3
        and all(item["passed"] for item in RESULT["run_reset_cycles"])
        and len(RESULT["lifecycle_cycles"]) == 3
        and all(item["passed"] for item in RESULT["lifecycle_cycles"])
        and RESULT["visual_contract"].get("passed") is True
        and RESULT["m2b_contract"].get("passed") is True
        and RESULT["long_route_contract"].get("passed") is True
        and RESULT["robot_dynamics_contract"].get("support_structure", {}).get("passed") is True
    ) else "FAIL"
except Exception as exc:
    RESULT["error"] = f"{type(exc).__name__}: {exc}"
    RESULT["traceback"] = traceback.format_exc()
finally:
    artifact_override = os.environ.get("TWINPULSE_ARTIFACT_DIR")
    if artifact_override:
        artifact_dir = Path(artifact_override)
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        artifact_dir = REPO_ROOT / "artifacts" / "runs" / f"isaac-{run_id}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "isaac-result.json"
    RESULT["artifact_contract"] = {
        "artifact_dir": str(artifact_dir),
        "result_json": str(result_path),
        "screenshot_capture": "NOT_RUN_MINIMAL_RENDERING",
    }
    serialized = json.dumps(RESULT, ensure_ascii=False, indent=2, sort_keys=True)
    result_path.write_text(serialized, encoding="utf-8")
    print("TWINPULSE_M1_RESULT=" + json.dumps(RESULT, ensure_ascii=False, sort_keys=True))
    APP.close()

sys.exit(0 if RESULT["status"] == "PASS" else 1)
