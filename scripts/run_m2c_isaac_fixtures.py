"""Build and drive every successful generated provider fixture in one headless Isaac run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
        "width": 1280,
        "height": 720,
    }
)


def _planar_distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second, strict=True)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--usd-output-dir", type=Path)
    parser.add_argument("--max-frames", type=int, default=2400)
    args = parser.parse_args()

    result: dict[str, object] = {
        "schema_version": "1.0",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_report": str(args.provider_report),
        "fixtures": [],
        "status": "FAIL",
    }
    manager = None
    extension = None
    try:
        core_src = REPO_ROOT / "packages" / "twinpulse_core" / "src"
        provider_src = REPO_ROOT / "packages" / "twinpulse_provider" / "src"
        sys.path.insert(0, str(core_src))
        sys.path.insert(0, str(provider_src))

        import omni.kit.app
        import omni.usd
        from twinpulse_core import EpisodeSample, assess_episode, bundle_from_json

        context = omni.usd.get_context()
        context.new_stage()
        for _ in range(10):
            APP.update()

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.add_path(str(REPO_ROOT / "extensions"))
        manager.set_extension_enabled_immediate("twinpulse.extension", True)
        for _ in range(10):
            APP.update()
        import twinpulse.extension as extension_module

        extension = extension_module.get_extension()
        if extension is None:
            raise RuntimeError("Extension manager did not create TwinPulseExtension")

        provider_report = json.loads(args.provider_report.read_text(encoding="utf-8"))
        if provider_report.get("status") != "PASS":
            raise RuntimeError("provider report must contain only successful fixtures")
        provider_fixtures = provider_report.get("fixtures", [])
        if not provider_fixtures:
            raise RuntimeError("provider report contains no fixtures")
        total = len(provider_fixtures)

        for index, fixture in enumerate(provider_fixtures, start=1):
            fixture_id = str(fixture["fixture_id"])
            measurement_count = int(fixture.get("measurement_constraint_count", 0))
            if measurement_count:
                if fixture.get("measurement_validation_status") != "PASS":
                    raise RuntimeError(f"{fixture_id}: measurement validation did not pass")
                if int(fixture.get("measurement_checked_value_count", 0)) < measurement_count:
                    raise RuntimeError(f"{fixture_id}: measurement validation evidence is incomplete")
            print(f"fixture={index}/{total} id={fixture_id} physics=BUILDING", flush=True)
            bundle = bundle_from_json(json.dumps(fixture["bundle"]))
            prim_count = extension.runtime.build_scene(bundle)
            extension.runtime.compiler.set_build_metadata(
                source=str(provider_report.get("evaluation_id", "generated_fixture_tool_plan")),
                request_id=str(fixture["request_id"]),
                image_count=1,
                plan_sha256=hashlib.sha256(
                    json.dumps(
                        fixture["plan"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
            )
            extension.runtime.reset()
            for _ in range(20):
                APP.update()
            start_position = extension.runtime.robot_position()
            extension.runtime.run()
            samples: list[EpisodeSample] = []
            path_distance_m = 0.0
            previous_position = start_position
            frame_count = 0
            for frame in range(args.max_frames):
                APP.update()
                frame_count = frame + 1
                if frame >= 20:
                    position, attitude = extension.runtime.robot_pose_3d()
                    samples.append(EpisodeSample(frame / 60.0, position, attitude))
                    path_distance_m += _planar_distance(previous_position, position)
                    previous_position = position
                if extension.runtime.state in {"completed", "off_route", "unstable"}:
                    break
            if not samples:
                raise RuntimeError(f"{fixture_id}: no physics samples collected")
            final_state = extension.runtime.state
            stage = omni.usd.get_context().get_stage()
            support_paths = [f"/World/TwinPulse/Robot/{item.id}" for item in bundle.robot.support_wheels]
            observed_support_wheels = sum(stage.GetPrimAtPath(path).IsValid() for path in support_paths)
            assessment = assess_episode(
                bundle,
                samples,
                final_state=final_state,
                observed_support_wheels=observed_support_wheels,
            )

            extension.runtime.pause()
            paused_before = extension.runtime.robot_position()
            for _ in range(15):
                APP.update()
            paused_after = extension.runtime.robot_position()
            pause_drift_m = _distance(paused_before, paused_after)

            extension.runtime.reset()
            for _ in range(20):
                APP.update()
            reset_position = extension.runtime.robot_position()
            reset_error_m = _distance(start_position, reset_position)
            usd_stage_path = None
            if args.usd_output_dir is not None:
                args.usd_output_dir.mkdir(parents=True, exist_ok=True)
                safe_fixture_id = "".join(
                    character if character.isalnum() or character in "-_" else "_"
                    for character in fixture_id
                )
                usd_path = args.usd_output_dir / f"{safe_fixture_id}.usda"
                if not stage.GetRootLayer().Export(str(usd_path)):
                    raise RuntimeError(f"{fixture_id}: failed to export generated USD stage")
                usd_stage_path = str(usd_path)
            passed = bool(
                assessment.passed
                and pause_drift_m < 0.001
                and reset_error_m < 0.02
                and frame_count < args.max_frames
            )
            item = {
                "fixture_id": fixture_id,
                "scene_id": bundle.scene.id,
                "request_id": fixture["request_id"],
                "prim_count": prim_count,
                "frame_count": frame_count,
                "simulated_elapsed_s": samples[-1].elapsed_s,
                "path_distance_m": path_distance_m,
                "start_position_m": start_position,
                "end_position_m": samples[-1].position_m,
                "pause_drift_m": pause_drift_m,
                "reset_error_m": reset_error_m,
                "usd_stage": usd_stage_path,
                "episode_assessment": assessment.to_dict(),
                "passed": passed,
            }
            result["fixtures"].append(item)
            print(
                f"fixture={index}/{total} id={fixture_id} physics={'PASS' if passed else 'FAIL'} "
                f"state={final_state} goal_error_m={assessment.goal_error_m:.4f} "
                f"collisions={assessment.geometric_collision_samples}",
                flush=True,
            )

        result["status"] = (
            "PASS"
            if len(result["fixtures"]) == total and all(item["passed"] for item in result["fixtures"])
            else "FAIL"
        )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
    finally:
        if extension is not None:
            extension.runtime.shutdown()
        if manager is not None:
            manager.set_extension_enabled_immediate("twinpulse.extension", False)
            for _ in range(5):
                APP.update()
        result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report={args.output}")
        print(f"status={result['status']}")
        APP.close()
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
