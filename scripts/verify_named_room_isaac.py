# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isolated named-project Burger visual check in actual Isaac; no timeline Run."""

import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
sys.path.insert(0, str(ROOT / "extensions/twinpulse.extension"))
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state_root = output / "isolated-state"
    result = {"status": "FAIL", "project_id": "room_one", "source": "synthetic_photo_room",
              "physical_validation": "NOT_RUN", "physics_run": "NOT_RUN",
              "browser_ui": "NOT_RUN", "robot_connections": 0, "provider_calls": 0,
              "checks": []}
    sim = None
    try:
        from tests.integration.test_a2_room_recipe import write_recipe
        from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectStore
        from twinpulse_app.room_recipe import (checked_project_room_descriptor,
                                               import_project_room_recipe, prepare_project_burger_visual)
        from twinpulse_core import SimulationSnapshot
        from tests.integration.test_a2_room_recipe import NoGateway

        write_recipe(state_root, "room_one", "red", 2.8)
        recipe = state_root / "projects" / "room_one" / "room_recipe.json"
        original_recipe = recipe.read_bytes()
        manifest = prepare_project_burger_visual(state_root, "room_one", (0.0, -0.65, 0.002), 90.0)
        draft = import_project_room_recipe(state_root, "room_one")
        app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(state_root, "room_one"),
                                 project_id="room_one")
        broker = CommandBroker(project_id="room_one")
        workflow = ProductWorkflow(app, broker, mode="simulation_offline",
                                   generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
        assert workflow.snapshot()["build_allowed"] is False
        workflow.continue_room_recipe()
        artifact = next(iter(broker._site_scenes.values()))
        descriptor = artifact.visual_preview
        checked_project_room_descriptor(descriptor, artifact.scene, state_root, "room_one")
        assert recipe.read_bytes() != original_recipe
        assert (recipe.parent / "room_recipe.before-burger.json").read_bytes() == original_recipe
        result["checks"].append("synthetic named room imported and reviewed without Build authority")

        from isaacsim import SimulationApp
        sim = SimulationApp({"headless": True, "width": 960, "height": 720})
        import omni.timeline
        import omni.usd
        from pxr import Gf, Usd, UsdGeom, UsdPhysics
        from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
        from twinpulse.extension.bedroom_preview import PREVIEW_PATH
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.runtime import TwinPulseRuntime

        omni.usd.get_context().new_stage()
        for _ in range(10):
            sim.update()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim().SetCustomDataByKey("marker", "preserve")
        runtime = TwinPulseRuntime()
        adapter = IsaacSimulationAdapter(runtime, project_id="room_one", project_state_root=state_root)
        broker.register_engine(adapter.engine_session_id, adapter.stage_epoch)
        lease = broker.acquire_lease("product")
        adapter.update_control_lease(lease["control_lease_id"], True)
        broker.record_snapshot(SimulationSnapshot(
            engine_session_id=adapter.engine_session_id, stage_epoch=adapter.stage_epoch,
            project_id="room_one", applied_revision=None, run_id=None, sequence=1,
            runtime_state="idle", safety_state=None, safety_reason=None,
            permitted_commands=("build_site_scene", "get_state"),
            capabilities=adapter.snapshot().capabilities, telemetry_available=False))
        broker.submit("product", {"client_request_id": "named-isolated-build",
                                  "command_type": "build_site_scene", "artifact_id": artifact.artifact_id,
                                  "expected_applied_revision": artifact.revision})
        command = broker.claim(adapter.engine_session_id, adapter.stage_epoch)
        assert command.payload["visual_preview"] == descriptor
        receipt = adapter.execute(command)
        result["receipt_status"] = receipt.status
        result["receipt_error"] = receipt.error_code
        assert receipt.status == "succeeded", receipt.message
        assert runtime.compiler.matches_site_scene(draft.site.scene)
        marker = stage.GetPrimAtPath(PREVIEW_PATH)
        assert marker.IsValid()
        assert marker.GetCustomDataByKey("twinpulseManifestSha256") == manifest["manifest_sha256"]
        assert marker.GetCustomDataByKey("motionAuthorized") is False
        assert marker.GetCustomDataByKey("worldAlignmentVerified") is False
        assert stage.GetPrimAtPath(PREVIEW_PATH + "/Model").GetVariantSet("Physics").GetVariantSelection() == "none"
        model_prims = list(Usd.PrimRange(stage.GetPrimAtPath(PREVIEW_PATH + "/Model"),
                                         Usd.TraverseInstanceProxies()))
        meshes = sum(prim.IsA(UsdGeom.Mesh) for prim in model_prims)
        assert meshes == 4
        assert not any(prim.HasAPI(UsdPhysics.RigidBodyAPI) or prim.HasAPI(UsdPhysics.CollisionAPI)
                       or prim.HasAPI(UsdPhysics.ArticulationRootAPI) for prim in model_prims)
        assert not stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
        assert not stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid()
        assert stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("marker") == "preserve"
        assert not omni.timeline.get_timeline_interface().is_playing()
        assert "run" not in adapter.snapshot().permitted_commands
        result["checks"].append("broker command rendered 4 visual Burger meshes in actual Isaac; no physics or Run")

        camera = UsdGeom.Camera(stage.GetPrimAtPath("/World/TwinPulse/Presentation/Camera"))
        camera.ClearXformOpOrder()
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(3.7, -5.9, 5.1), Gf.Vec3d(0, 0.15, 0.35),
            Gf.Vec3d(0, 0, 1)).GetInverse())
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100))
        camera.CreateFocalLengthAttr(30)
        UsdGeom.Imageable(stage.GetPrimAtPath(
            "/World/TwinPulse/Environment/wall_right")).MakeInvisible()
        viewport = get_active_viewport()
        viewport.set_active_camera(str(camera.GetPath()))
        for _ in range(45):
            sim.update()
        capture = output / "named-room-actual-Isaac.png"
        capture_viewport_to_file(viewport, str(capture))
        for _ in range(45):
            sim.update()
        assert capture.is_file() and capture.stat().st_size > 1000
        result["checks"].append("actual Isaac viewport capture written")

        stage.GetRootLayer().Export(str(output / "named-room-stage.usda"))
        saved = Usd.Stage.Open(str(output / "named-room-stage.usda"))
        assert saved.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey("twinpulseManifestSha256") == manifest["manifest_sha256"]
        assert saved.GetPrimAtPath("/ExternalKeep").IsValid()
        result["checks"].append("saved USD reopened with project manifest and external prim intact")
        result.update(status="PASS", visual_mesh_count=meshes,
                      scene_revision=draft.site.scene.revision,
                      manifest_sha256=manifest["manifest_sha256"])
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("NAMED_ROOM_ISAAC=" + result["status"], flush=True)
        if sim is not None:
            sim.close()
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
