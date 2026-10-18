# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2c actual-Isaac acceptance for reviewed v2 site geometry, without a provider call."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
STATE = tempfile.TemporaryDirectory(prefix="tmp-h2c-kit-", dir=os.environ.get("TWINPULSE_TEST_TMP"))
os.environ["TWINPULSE_STATE_DIR"] = STATE.name

from isaacsim import SimulationApp  # noqa: E402

APP = SimulationApp({"headless": True, "renderer": "MinimalRendering",
                     "disable_viewport_updates": True, "width": 640, "height": 480})


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


try:
    import omni.kit.app
    import omni.usd
    from pxr import UsdGeom

    context = omni.usd.get_context()
    context.new_stage()
    for _ in range(10):
        APP.update()
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(ROOT / "extensions"))
    manager.set_extension_enabled_immediate("twinpulse.extension", True)
    for _ in range(5):
        APP.update()

    from twinpulse_core import (CommandEnvelope, SceneToolCall, SiteToolPlan, bundle_digest,
                                demo_warehouse_tool_plan,
                                execute_site_tool_plan, fixed_warehouse_bundle)
    from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
    from twinpulse.extension.runtime import TwinPulseRuntime
    from twinpulse.extension.scene_compiler import OWNED_ROOT, SceneCompiler

    demo = demo_warehouse_tool_plan()
    plan = SiteToolPlan("site_fixture_h2c", "L-shaped site acceptance fixture", "No model call",
                        (demo.calls[0],
                         SceneToolCall("wall_east", "create_wall",
                                       {"id": "wall_east", "position_m": [2.5, 0.7, 0.8],
                                        "dimensions_m": [2.0, 0.2, 1.6], "yaw_deg": 0.0}),
                         SceneToolCall("wall_north", "create_wall",
                                       {"id": "wall_north", "position_m": [3.5, -0.2, 0.8],
                                        "dimensions_m": [1.8, 0.2, 1.6], "yaw_deg": 90.0}),
                         demo.calls[-2],
                         SceneToolCall("task_blocked", "create_navigation_task",
                                       {"id": "blocked_goal", "goal_position_m": [2.5, 0.7, 0.0],
                                        "position_tolerance_m": 0.05})))
    proposal = execute_site_tool_plan(plan, source="photo", source_ref="a" * 64)
    scene = proposal.scene
    check(proposal.robot is not None and proposal.mission is not None,
          "fixture must contain optional robot and mission proposals")
    check(proposal.mission.goal.position_m == (2.5, 0.7, 0.0),
          "blocked goal was silently relocated")
    runtime = TwinPulseRuntime()
    adapter = IsaacSimulationAdapter(runtime)
    adapter.update_control_lease("h2c-lease", True)

    def command(kind: str, *, number: int, revision: str | None,
                payload: dict | None = None) -> CommandEnvelope:
        return CommandEnvelope(
            command_id=f"h2c-{number}", command_type=kind, project_id="default",
            engine_session_id=adapter.engine_session_id, stage_epoch=adapter.stage_epoch,
            control_lease_id="h2c-lease", expected_applied_revision=revision,
            payload=payload or {},
        )

    initial = adapter.snapshot()
    check("site_scene_build_v2" in initial.capabilities
          and "build_site_scene" in initial.permitted_commands, "site capability not advertised")
    build = command("build_site_scene", number=1, revision=scene.revision,
                    payload={"artifact_id": "h2c-fixture", "scene_revision": scene.revision,
                             "scene": scene.to_dict()})
    receipt = adapter.execute(build)
    check(receipt.status == "succeeded" and receipt.applied_revision == scene.revision,
          f"site Build failed: {receipt.error_code}: {receipt.message}")
    check(receipt.build_fingerprint == SceneCompiler.site_fingerprint(scene),
          "site Build fingerprint differs from reviewed scene")
    stage = context.get_stage()
    root = stage.GetPrimAtPath(OWNED_ROOT)
    count = runtime.compiler.owned_prim_count()
    check(runtime.compiler.matches_site_scene(scene) and count > 0, "actual USD did not match site revision")
    check(not stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
          and not stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid(),
          "site Build created an unapproved Robot or Task")
    check(root.GetCustomDataByKey("twinpulseSiteSceneRevision") == scene.revision,
          "USD root lacks the applied site revision")
    built = adapter.snapshot()
    check(built.applied_revision == scene.revision and built.runtime_state == "built"
          and "run" not in built.permitted_commands and "reset" in built.permitted_commands,
          "site snapshot permits Run or does not permit Reset")
    denied = adapter.execute(command("run", number=2, revision=scene.revision))
    check(denied.status == "failed" and runtime.state == "ready", "site Run was not rejected")
    stale = adapter.execute(command("run", number=20, revision="0" * 64))
    check(stale.status == "failed" and runtime.state == "ready", "stale Run was not rejected")
    bad_build = adapter.execute(command("build_site_scene", number=21, revision="0" * 64,
                                        payload=dict(build.payload)))
    check(bad_build.status == "failed" and runtime.compiler.matches_site_scene(scene),
          "stale site Build replaced the reviewed scene")
    reset = adapter.execute(command("reset", number=3, revision=scene.revision))
    check(reset.status == "succeeded" and runtime.compiler.matches_site_scene(scene)
          and runtime.compiler.owned_prim_count() == count, "site Reset damaged geometry")
    again = adapter.execute(command("build_site_scene", number=4, revision=scene.revision,
                                    payload=dict(build.payload)))
    check(again.status == "succeeded" and again.build_fingerprint == receipt.build_fingerprint
          and runtime.compiler.owned_prim_count() == count, "identical Build was not idempotent")
    print("H2C SITE PASS: receipt, scene-only USD, Run denied, Reset, idempotence", flush=True)

    external = UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim()
    external.SetCustomDataByKey("marker", "h2c-preserved")
    before_root = root.GetCustomData()
    first_wall = next(item for item in scene.objects if item.kind == "wall")
    shifted = replace(first_wall, transform=replace(first_wall.transform,
                                                     position_m=(first_wall.transform.position_m[0] + 0.1,
                                                                 first_wall.transform.position_m[1],
                                                                 first_wall.transform.position_m[2])))
    changed = replace(scene, objects=tuple(shifted if item.id == first_wall.id else item
                                            for item in scene.objects))
    old_position = tuple(stage.GetPrimAtPath(f"/World/TwinPulse/Environment/{first_wall.id}")
                         .GetAttribute("xformOp:translate").Get())
    compiler = runtime.compiler
    original = compiler._create_scene_object
    calls = [0]

    def injected_failure(item):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("intentional H2c compile failure")
        return original(item)

    compiler._create_scene_object = injected_failure
    try:
        compiler.compile_site_scene(changed)
        raise AssertionError("fault injection did not fail")
    except RuntimeError as error:
        check("previous geometry and identity restored" in str(error), f"unexpected rollback error: {error}")
    finally:
        compiler._create_scene_object = original
    stage = context.get_stage()
    check(compiler.matches_site_scene(scene) and compiler.site_scene == scene
          and compiler.build_receipt.fingerprint == receipt.build_fingerprint
          and stage.GetPrimAtPath(OWNED_ROOT).GetCustomData() == before_root
          and tuple(stage.GetPrimAtPath(f"/World/TwinPulse/Environment/{first_wall.id}")
                    .GetAttribute("xformOp:translate").Get()) == old_position
          and stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("marker") == "h2c-preserved",
          "failed replacement did not preserve prior site and external prim")
    print("H2C ROLLBACK PASS: prior scene, receipt, and external prim preserved", flush=True)

    legacy = fixed_warehouse_bundle()
    legacy_revision = bundle_digest(legacy)
    legacy_receipt = adapter.execute(command("build_scene", number=5, revision=legacy_revision,
                                             payload={"artifact_id": "h2c-legacy-fixture",
                                                      "bundle_sha256": legacy_revision,
                                                      "bundle": legacy.to_dict()}))
    check(legacy_receipt.status == "succeeded" and legacy_receipt.applied_revision == legacy_revision,
          f"v1 bridge Build failed: {legacy_receipt.error_code}: {legacy_receipt.message}")
    legacy_count = runtime.compiler.owned_prim_count()
    check(legacy_count > 0 and runtime.compiler.matches_stage(legacy)
          and stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
          and stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid(),
          "v1 Build did not replace the v2 scene")
    check("run" in adapter.snapshot().permitted_commands,
          "v1 bridge did not restore its supported Run capability")
    run_receipt = adapter.execute(command("run", number=6, revision=legacy_revision))
    check(run_receipt.status == "succeeded", f"v1 bridge Run failed: {run_receipt.message}")
    for _ in range(30):
        APP.update()
    check(runtime.state in {"running", "completed"} and runtime.physics_steps > 0,
          "v1 physics controller did not step")
    legacy_steps = runtime.physics_steps
    check(adapter.execute(command("pause", number=7, revision=legacy_revision)).status == "succeeded",
          "v1 bridge Pause failed")
    check(adapter.execute(command("reset", number=8, revision=legacy_revision)).status == "succeeded",
          "v1 bridge Reset failed")
    check(runtime.state == "ready" and runtime.compiler.matches_stage(legacy),
          "v1 Pause/Reset regression after v2 Build")
    print("H2C V1 PASS: legacy Build, physics Run, Pause, Reset", flush=True)

    back_to_site = adapter.execute(command("build_site_scene", number=9, revision=scene.revision,
                                           payload=dict(build.payload)))
    check(back_to_site.status == "succeeded" and runtime.compiler.matches_site_scene(scene)
          and not stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
          and not stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid()
          and "run" not in adapter.snapshot().permitted_commands,
          "v1-to-v2 transition retained a robot, mission, or Run authority")
    reload_path = Path(STATE.name) / "h2c-site-reload.usda"
    check(stage.GetRootLayer().Export(str(reload_path)), "could not export actual Isaac site stage")
    context.open_stage(str(reload_path))
    for _ in range(3):
        APP.update()
    reloaded = SceneCompiler()
    check(reloaded.matches_site_scene(scene), "reloaded USD lost the reviewed site identity")
    check(reloaded.compile_site_scene(scene) == reloaded.owned_prim_count()
          and reloaded.build_receipt.fingerprint == receipt.build_fingerprint,
          "reloaded site scene was not idempotent")
    reloaded_stage = context.get_stage()
    damaged_wall = reloaded_stage.GetPrimAtPath("/World/TwinPulse/Environment/wall_east")
    damaged_wall.GetAttribute("xformOp:translate").Set((9.0, 9.0, 9.0))
    check(not reloaded.matches_site_scene(scene), "manual site geometry damage was accepted")
    reloaded.compile_site_scene(scene)
    check(reloaded.matches_site_scene(scene), "manual site geometry damage was not repaired")
    print("H2C RELOAD PASS: v1-to-v2 transition and USD reopen", flush=True)

    runtime.shutdown()
    context.new_stage()
    for _ in range(3):
        APP.update()
    incompatible = context.get_stage()
    UsdGeom.SetStageUpAxis(incompatible, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(incompatible, 0.01)
    kept = UsdGeom.Xform.Define(incompatible, "/ExternalKeep").GetPrim()
    kept.SetCustomDataByKey("marker", "untouched")
    try:
        SceneCompiler().compile_site_scene(scene)
        raise AssertionError("incompatible user stage was accepted")
    except RuntimeError as error:
        check("incompatible" in str(error), f"unexpected stage rejection: {error}")
    check(not incompatible.GetPrimAtPath(OWNED_ROOT).IsValid()
          and kept.GetCustomDataByKey("marker") == "untouched"
          and UsdGeom.GetStageUpAxis(incompatible) == UsdGeom.Tokens.y,
          "incompatible user stage was modified")
    print("H2C STAGE PASS: damaged geometry repaired; foreign stage preserved", flush=True)
    result = {"status": "PASS", "site_revision": scene.revision,
              "site_fingerprint": receipt.build_fingerprint, "site_prims": count,
              "legacy_prims": legacy_count, "legacy_physics_steps": legacy_steps,
              "provider_calls": 0}
    print("H2C_RESULT=" + json.dumps(result, sort_keys=True), flush=True)
except Exception:
    print("H2C ERROR:", traceback.format_exc(), flush=True)
    raise
finally:
    APP.close()
    STATE.cleanup()
