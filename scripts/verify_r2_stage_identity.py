"""R2 actual-Isaac regression for same scene ID with changed static geometry."""

from __future__ import annotations

from dataclasses import replace
import math
import os
from pathlib import Path
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
STATE = tempfile.TemporaryDirectory(prefix="tmp-r2-kit-", dir=os.environ.get("TWINPULSE_TEST_TMP"))
os.environ["TWINPULSE_STATE_DIR"] = STATE.name

from isaacsim import SimulationApp  # noqa: E402

APP = SimulationApp({"headless": True, "renderer": "MinimalRendering",
                     "disable_viewport_updates": True, "width": 640, "height": 480})

try:
    import omni.kit.app
    import omni.usd
    from pxr import UsdGeom, UsdPhysics

    omni.usd.get_context().new_stage()
    for _ in range(10):
        APP.update()
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(ROOT / "extensions"))
    manager.set_extension_enabled_immediate("twinpulse.extension", True)
    for _ in range(5):
        APP.update()

    from twinpulse_core import fixed_warehouse_bundle
    from twinpulse.extension.scene_compiler import OWNED_ROOT, SceneCompiler
    from twinpulse.extension.runtime import TwinPulseRuntime
    print("R2 STEP: imports ready", flush=True)

    a = fixed_warehouse_bundle()
    objects = list(a.scene.objects)
    index = next(i for i, item in enumerate(objects) if item.id == "rack_north")
    rack = objects[index]
    objects[index] = replace(rack, transform=replace(rack.transform, position_m=(1.2, 1.6, 0.9)),
                             shape=replace(rack.shape, dimensions_m=(2.0, 0.6, 1.8)))
    b = replace(a, scene=replace(a.scene, objects=tuple(objects)))
    assert a.scene.id == b.scene.id and a != b
    first = SceneCompiler()
    first.compile(a)
    print("R2 STEP: first compile complete", flush=True)
    stage = omni.usd.get_context().get_stage()
    path = "/World/TwinPulse/Environment/rack_north/geometry"
    old_scale = tuple(stage.GetPrimAtPath(path).GetAttribute("xformOp:scale").Get())
    print(f"R2 STEP: old_scale={old_scale}", flush=True)
    fresh = SceneCompiler()
    fresh.compile(b)
    print("R2 STEP: fresh second compile complete", flush=True)
    receipt = fresh.build_receipt
    if (receipt is None or receipt.fingerprint != fresh.build_fingerprint(b)
            or receipt.prim_count != fresh.owned_prim_count()):
        raise AssertionError("successful build did not emit a matching receipt")
    new_scale = tuple(stage.GetPrimAtPath(path).GetAttribute("xformOp:scale").Get())
    print(f"R2 STEP: new_scale={new_scale}", flush=True)
    if old_scale == new_scale:
        raise AssertionError("F4 reproduced: fresh compiler treated changed bundle with same scene ID as already built")
    if len(new_scale) != 3 or any(not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)
                                  for actual, expected in zip(new_scale, (2.0, 0.6, 1.8), strict=True)):
        raise AssertionError(f"changed rack scale was not authored: {new_scale}")
    print("R2 F4 PASS: same scene ID with changed rack dimension authored in actual USD")

    count = fresh.owned_prim_count()
    fingerprint = stage.GetPrimAtPath(OWNED_ROOT).GetCustomDataByKey("twinpulseBuildFingerprint")
    if fresh.compile(b) != count or fresh.owned_prim_count() != count:
        raise AssertionError("identical build was not idempotent")
    if stage.GetPrimAtPath(OWNED_ROOT).GetCustomDataByKey("twinpulseBuildFingerprint") != fingerprint:
        raise AssertionError("identical build changed its fingerprint")

    geometry = stage.GetPrimAtPath(path)
    geometry.GetAttribute("xformOp:scale").Set((2.0, 0.6, 9.0))
    if fresh.matches_stage(b):
        raise AssertionError("manual static geometry damage was accepted")
    fresh.compile(b)
    repaired = tuple(stage.GetPrimAtPath(path).GetAttribute("xformOp:scale").Get())
    if not math.isclose(repaired[2], 1.8, rel_tol=0.0, abs_tol=1e-6):
        raise AssertionError("manual geometry damage was not rebuilt")
    stage.RemovePrim("/World/TwinPulse/Environment/box_demo")
    fresh.compile(b)
    if not stage.GetPrimAtPath("/World/TwinPulse/Environment/box_demo").IsValid():
        raise AssertionError("missing owned prim was not rebuilt")
    stage.GetPrimAtPath(OWNED_ROOT).SetCustomDataByKey("twinpulseBuildFingerprint", "corrupt")
    fresh.compile(b)
    if not fresh.matches_stage(b):
        raise AssertionError("corrupt identity metadata was not repaired")
    stage.GetPrimAtPath("/World/TwinPulse/PhysicsScene").GetAttribute(
        "physics:gravityMagnitude").Set(1.0)
    fresh.compile(b)
    if not math.isclose(
            stage.GetPrimAtPath("/World/TwinPulse/PhysicsScene").GetAttribute(
                "physics:gravityMagnitude").Get(), 9.81, abs_tol=1e-6):
        raise AssertionError("damaged PhysicsScene metadata was not repaired")
    print("R2 IDENTITY PASS: idempotent, manual damage, missing prim, corrupt metadata")

    external = UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim()
    external.SetCustomDataByKey("marker", "preserve")
    rollback = SceneCompiler()
    rollback.compile(a)
    before_identity = stage.GetPrimAtPath(OWNED_ROOT).GetCustomData()
    before_scale = tuple(stage.GetPrimAtPath(path).GetAttribute("xformOp:scale").Get())
    before_receipt = rollback.build_receipt
    original_create = rollback._create_scene_object
    calls = [0]

    def fail_during_replace(item):
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("intentional replacement failure")
        original_create(item)

    rollback._create_scene_object = fail_during_replace
    try:
        rollback.compile(b)
        raise AssertionError("intentional replacement failure did not fail")
    except RuntimeError as error:
        if "previous geometry and identity restored" not in str(error):
            raise
    finally:
        rollback._create_scene_object = original_create
    after_scale = tuple(stage.GetPrimAtPath(path).GetAttribute("xformOp:scale").Get())
    if (before_scale != after_scale or stage.GetPrimAtPath(OWNED_ROOT).GetCustomData() != before_identity
            or rollback.bundle != a or rollback.build_receipt != before_receipt
            or not rollback.matches_stage(a)):
        raise AssertionError("replacement rollback did not restore previous scene and identity")
    if external.GetCustomDataByKey("marker") != "preserve":
        raise AssertionError("external prim changed during TwinPulse replacement")
    print("R2 ROLLBACK PASS: previous scene/binding and external prim preserved")

    context = omni.usd.get_context()
    context.new_stage()
    for _ in range(3):
        APP.update()
    dedicated = SceneCompiler()
    dedicated.compile(b)
    new_stage = context.get_stage()
    if not dedicated.matches_stage(b, stage=new_stage):
        raise AssertionError("new dedicated stage was mistaken for a prior stage")
    if UsdGeom.GetStageUpAxis(new_stage) != UsdGeom.Tokens.z or not math.isclose(
            UsdGeom.GetStageMetersPerUnit(new_stage), 1.0, abs_tol=1e-12):
        raise AssertionError("dedicated TwinPulse stage is not Z-up/meters")

    dedicated_count = dedicated.owned_prim_count()
    reload_path = Path(STATE.name) / "r2-reload.usda"
    if not new_stage.GetRootLayer().Export(str(reload_path)):
        raise AssertionError("could not export the R2 reload fixture")
    context.open_stage(str(reload_path))
    for _ in range(3):
        APP.update()
    reloaded_stage = context.get_stage()
    reloaded = SceneCompiler()
    reloaded_count = reloaded.compile(b)
    if (not reloaded.matches_stage(b, stage=reloaded_stage)
            or reloaded_count != dedicated_count
            or reloaded.build_receipt is None):
        raise AssertionError("reloaded stage identity was misclassified")

    context.new_stage()
    for _ in range(3):
        APP.update()
    incompatible = context.get_stage()
    UsdGeom.SetStageUpAxis(incompatible, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(incompatible, 0.01)
    keep = UsdGeom.Xform.Define(incompatible, "/UserContent").GetPrim()
    keep.SetCustomDataByKey("marker", "untouched")
    try:
        SceneCompiler().compile(a)
        raise AssertionError("incompatible user stage was silently changed")
    except RuntimeError as error:
        if "incompatible" not in str(error):
            raise
    if (not keep.IsValid() or keep.GetCustomDataByKey("marker") != "untouched"
            or incompatible.GetPrimAtPath(OWNED_ROOT).IsValid()
            or UsdGeom.GetStageUpAxis(incompatible) != UsdGeom.Tokens.y
            or not math.isclose(UsdGeom.GetStageMetersPerUnit(incompatible), 0.01, abs_tol=1e-12)):
        raise AssertionError("incompatible user stage was mutated")

    context.new_stage()
    for _ in range(3):
        APP.update()
    unowned = context.get_stage()
    UsdGeom.SetStageUpAxis(unowned, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(unowned, 0.01)
    foreign_root = UsdGeom.Xform.Define(unowned, OWNED_ROOT).GetPrim()
    foreign_root.SetCustomDataByKey("marker", "foreign")
    try:
        SceneCompiler().compile(a)
        raise AssertionError("unowned /World/TwinPulse was silently adopted")
    except RuntimeError as error:
        if "incompatible" not in str(error):
            raise
    if (foreign_root.GetCustomDataByKey("marker") != "foreign"
            or UsdGeom.GetStageUpAxis(unowned) != UsdGeom.Tokens.y
            or not math.isclose(UsdGeom.GetStageMetersPerUnit(unowned), 0.01, abs_tol=1e-12)):
        raise AssertionError("unowned root or its stage units were mutated")

    context.new_stage()
    for _ in range(3):
        APP.update()
    multi_physics = context.get_stage()
    UsdGeom.SetStageUpAxis(multi_physics, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(multi_physics, 1.0)
    user_physics = UsdPhysics.Scene.Define(multi_physics, "/UserPhysics").GetPrim()
    user_physics.SetCustomDataByKey("marker", "foreign")
    try:
        SceneCompiler().compile(a)
        raise AssertionError("stage with an external PhysicsScene was silently accepted")
    except RuntimeError as error:
        if "PhysicsScene" not in str(error):
            raise
    if (user_physics.GetCustomDataByKey("marker") != "foreign"
            or multi_physics.GetPrimAtPath(OWNED_ROOT).IsValid()):
        raise AssertionError("external PhysicsScene stage was mutated")
    print("R2 STAGE PASS: new stage identity, Z-up/meters, incompatible user stage preserved")

    context.new_stage()
    for _ in range(3):
        APP.update()
    runtime = TwinPulseRuntime()
    runtime.build_scene(a)

    class FakeRobot:
        def apply_wheel_actions(self, _actions):
            return None

    class FakeController:
        def forward(self, command):
            return command

    runtime._robot = FakeRobot()
    runtime._controller = FakeController()
    runtime._physics_steps = 21
    runtime._state = "running"
    runtime.robot_pose_3d = lambda: ((0.0, 2.0, 0.12), (0.0, 0.0, 0.0))
    runtime._on_physics_step(1.0 / 60.0, None)
    if runtime.safety_latch != "off_route" or runtime.state != "off_route":
        raise AssertionError("off-route telemetry did not latch")
    runtime.pause()
    try:
        runtime.run()
        raise AssertionError("Pause bypassed off-route safety latch")
    except RuntimeError as error:
        if "Reset is required" not in str(error):
            raise
    runtime.reset()
    if runtime.safety_latch is not None or runtime.state != "ready":
        raise AssertionError("Reset did not clear the safety latch")

    runtime._robot = FakeRobot()
    runtime._controller = FakeController()
    runtime._physics_steps = 21
    runtime._state = "running"
    runtime.robot_pose_3d = lambda: ((0.0, 0.0, 0.12), (math.radians(20.0), 0.0, 0.0))
    runtime._on_physics_step(1.0 / 60.0, None)
    if runtime.safety_latch != "unstable":
        raise AssertionError("unstable telemetry did not latch")
    runtime.pause()
    try:
        runtime.run()
        raise AssertionError("Pause bypassed unstable safety latch")
    except RuntimeError as error:
        if "Reset is required" not in str(error):
            raise
    runtime.reset()
    context.new_stage()
    for _ in range(3):
        APP.update()
    try:
        runtime.run()
        raise AssertionError("stage change left old Run command valid")
    except RuntimeError:
        pass
    if runtime.compiler.bundle is not None or runtime.has_active_subscription:
        raise AssertionError("stage change did not invalidate runtime bindings")
    runtime.shutdown()
    print("R2 SAFETY PASS: off-route/unstable latch, Reset gate, stage-change invalidation")
    first = fresh = None
    manager.set_extension_enabled_immediate("twinpulse.extension", False)
    for _ in range(5):
        APP.update()
except BaseException as error:
    print(f"R2 ERROR: {type(error).__name__}: {error}", flush=True)
    print("R2 TRACE: " + traceback.format_exc().replace("\n", " | "), flush=True)
    FAILURE = error
finally:
    APP.close()
    STATE.cleanup()

if "FAILURE" in globals():
    raise SystemExit(1)
