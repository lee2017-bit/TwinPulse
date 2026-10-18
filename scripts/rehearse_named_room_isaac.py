# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Named room through actual React/API/production bridge/Isaac. No Run."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
sys.path.insert(0, str(ROOT / "extensions/twinpulse.extension"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preserved-bedroom", action="store_true",
                        help="Use the reviewed local bedroom photo, not the synthetic room fixture")
    parser.add_argument("--manual-room", action="store_true",
                        help="Create a second user-dimensioned photo room with pinned visual Burger")
    parser.add_argument("--synthetic-warehouse", action="store_true",
                        help="Create a static warehouse fixture via the same saved-scene product path")
    parser.add_argument("--capture-viewport", action="store_true",
                        help="Capture the authored camera unchanged for a visible room-view review")
    parser.add_argument("--edit-scene", action="store_true",
                        help="Use the browser to Add, Change and Undo before building the saved revision")
    parser.add_argument("--edit-furniture", action="store_true",
                        help="Use the browser to add, change and undo a catalog furniture preset")
    parser.add_argument("--furniture-request", action="store_true",
                        help="Interpret a narrow offline furniture request before the normal preview/apply path")
    parser.add_argument("--furniture-staging", action="store_true",
                        help="Drag two staged furniture pieces and save one reviewed revision")
    parser.add_argument("--fake-edit-proposal", action="store_true",
                        help="Preview a context-bound fake furniture proposal with visible error/loading feedback")
    parser.add_argument("--reopen-state", type=Path,
                        help="Copy a prior isolated rehearsal state and reopen it in a new Isaac process")
    parser.add_argument("--existing-state", type=Path,
                        help="Open a browser-created saved room in a fresh Isaac process")
    parser.add_argument("--project-id", default="room_one",
                        help="Saved project ID when using --existing-state")
    parser.add_argument("--expected-edit-revision", default="",
                        help="Require this saved scene-edit revision when reopening")
    parser.add_argument("--inject-visual-failure", action="store_true",
                        help="After a successful Build, fail a later visual composition and verify stage rollback")
    parser.add_argument("--presentation", choices=("top:soft", "back:bright", "left:balanced"),
                        help="Save and inspect an explicit camera/lighting preset")
    parser.add_argument("--presentation-reopen", action="store_true",
                        help="Use a previously saved presentation without saving it again")
    args = parser.parse_args()
    if args.synthetic_warehouse and (args.manual_room or args.preserved_bedroom or args.reopen_state
                                     or args.existing_state or args.edit_scene or args.edit_furniture
                                     or args.furniture_request or args.furniture_staging or args.fake_edit_proposal):
        parser.error("Synthetic warehouse is a distinct initial review scenario")
    if args.manual_room and (args.preserved_bedroom or args.reopen_state or args.existing_state or args.edit_scene
                             or args.edit_furniture or args.furniture_request or args.furniture_staging or args.fake_edit_proposal):
        parser.error("Manual room creation is a distinct initial review scenario")
    if args.reopen_state and (not args.expected_edit_revision or args.edit_scene or args.edit_furniture
                              or args.furniture_request or args.furniture_staging or args.fake_edit_proposal):
        parser.error("Reopen requires an expected edit revision and cannot edit the copied state again")
    if args.expected_edit_revision and not (args.reopen_state or args.existing_state):
        parser.error("Expected edit revision requires saved state")
    if args.existing_state and (args.reopen_state or args.preserved_bedroom or args.edit_scene):
        parser.error("An existing saved room is a distinct review scenario")
    if (args.edit_furniture or args.furniture_request or args.furniture_staging or args.fake_edit_proposal) and (
            not args.existing_state or args.expected_edit_revision or
            sum((args.edit_furniture, args.furniture_request, args.furniture_staging, args.fake_edit_proposal)) != 1):
        parser.error("Furniture editing requires one mode and an existing saved room")
    if not args.existing_state and args.project_id != "room_one":
        parser.error("Custom project ID requires --existing-state")
    if args.presentation_reopen and (not args.existing_state or not args.presentation):
        parser.error("Presentation reopen requires existing state and an expected preset")
    from twinpulse_app.project_store import checked_project_id
    project_id = checked_project_id(args.project_id)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    node = shutil.which("node")
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    if not node or not chrome.is_file():
        parser.error("Existing Node/Chrome required")
    result = {"status": "FAIL", "source": "browser_created_saved_room" if args.existing_state else
              "user_photo_manual_dimensions" if args.manual_room else
              "synthetic_warehouse_fixture" if args.synthetic_warehouse else
              "preserved_bedroom_photo" if args.preserved_bedroom else "synthetic_photo_room", "project_id": project_id,
              "physical_validation": "NOT_RUN", "physics_run": "NOT_RUN", "robot_connections": 0,
              "provider_calls": 0, "checks": []}
    sim = server = bridge = child = None
    try:
        from tests.integration.test_a2_room_recipe import write_recipe, write_synthetic_warehouse_recipe, NoGateway
        from rehearse_offline_app import NoCredentials
        from twinpulse_app import (ApplicationService, CommandBroker, JsonProviderSettingsStore,
                                   LocalApiServer, ProductWorkflow, ProjectStore)
        from twinpulse_app.room_recipe import import_project_room_recipe, prepare_project_burger_visual, load_project_room_visual
        from twinpulse_app.project_catalog import ProjectCatalog
        state_root = output / "isolated-state"
        if args.existing_state:
            shutil.copytree(args.existing_state.resolve(), state_root)
            draft = ProjectStore.for_project(state_root, project_id).load().site_draft
            manifest, _ = load_project_room_visual(state_root, project_id, draft)
        elif args.reopen_state:
            shutil.copytree(args.reopen_state.resolve(), state_root)
            draft = ProjectStore.for_project(state_root, "room_one").load().site_draft
            manifest, _ = load_project_room_visual(state_root, "room_one", draft)
        elif args.preserved_bedroom:
            ProjectCatalog(state_root, "default").create_from_preserved_bedroom("room_one")
            draft = ProjectStore.for_project(state_root, "room_one").load().site_draft
            manifest, _ = load_project_room_visual(state_root, "room_one", draft)
        elif args.manual_room:
            from tests.integration.test_manual_room_creation import photo
            from uuid import uuid4
            ProjectCatalog(state_root, "default").create_from_manual_room(
                "room_one", prompt="User entered 3.2 by 4.4 metre room; photo not interpreted",
                photo=photo("blue"), media_type="image/png", width_m=3.2, length_m=4.4,
                wall_height_m=2.4, include_burger_visual=True, request_id=str(uuid4()))
            draft = ProjectStore.for_project(state_root, "room_one").load().site_draft
            manifest, _ = load_project_room_visual(state_root, "room_one", draft)
        elif args.synthetic_warehouse:
            write_synthetic_warehouse_recipe(state_root, "room_one")
            manifest = prepare_project_burger_visual(state_root, "room_one", (-1.0, 0.0, 0.002), 90.0)
            draft = import_project_room_recipe(state_root, "room_one")
        else:
            write_recipe(state_root, "room_one", "red", 2.8)
            manifest = prepare_project_burger_visual(state_root, "room_one", (0., -.65, .002), 90.)
            draft = import_project_room_recipe(state_root, "room_one")
        project_store = ProjectStore.for_project(state_root, project_id)
        recipe_path = state_root / "projects" / project_id / "room_recipe.json"
        before_recipe = recipe_path.read_bytes()
        app = ApplicationService(NoGateway(), project_store=project_store, project_id=project_id)
        broker = CommandBroker(project_id=project_id)
        workflow = ProductWorkflow(app, broker, mode="simulation_offline",
                                   generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
        assert workflow.snapshot()["phase"] == "restore_review_required"
        from isaacsim import SimulationApp
        sim = SimulationApp({"headless": True, "width": 960, "height": 720})
        import omni.usd
        import omni.timeline
        from pxr import Usd, UsdGeom, UsdPhysics
        from twinpulse.extension.bedroom_preview import PREVIEW_PATH
        from twinpulse.extension.scene_compiler import CAMERA_PATH, DOME_LIGHT_PATH, PRESENTATION_PATH, SUN_LIGHT_PATH
        from twinpulse.extension.bridge_client import BridgeClient
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.runtime import TwinPulseRuntime
        omni.usd.get_context().new_stage()
        for _ in range(10):
            sim.update()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim().SetCustomDataByKey("marker", "preserve")
        runtime = TwinPulseRuntime()
        adapter = IsaacSimulationAdapter(runtime, project_id=project_id, project_state_root=state_root)
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret,
                                engine_bootstrap_secret=engine_secret, product_workflow=workflow,
                                static_root=ROOT / "apps/twinpulse-web/dist",
                                provider_settings_store=JsonProviderSettingsStore(state_root / "settings.json"),
                                credential_store=NoCredentials())
        server.start()
        bridge = BridgeClient(adapter, base_url=server.base_url, bootstrap_secret=engine_secret)
        bridge.start()
        environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
                           TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                           TWINPULSE_REHEARSAL_OUTPUT=str(output),
                           TWINPULSE_REHEARSAL_CHROME=str(chrome),
                           TWINPULSE_REHEARSAL_PROJECT=project_id,
                           TWINPULSE_REHEARSAL_ENVIRONMENT="warehouse" if args.synthetic_warehouse else "room",
                           TWINPULSE_REHEARSAL_EDIT_SCENE="1" if args.edit_scene else "0",
                           TWINPULSE_REHEARSAL_EDIT_FURNITURE="1" if args.edit_furniture else "0",
                           TWINPULSE_REHEARSAL_FURNITURE_REQUEST="1" if args.furniture_request else "0",
                           TWINPULSE_REHEARSAL_FURNITURE_STAGING="1" if args.furniture_staging else "0",
                           TWINPULSE_REHEARSAL_FAKE_EDIT_PROPOSAL="1" if args.fake_edit_proposal else "0",
                           TWINPULSE_REHEARSAL_PRESENTATION=args.presentation or "",
                           TWINPULSE_REHEARSAL_PRESENTATION_REOPEN="1" if args.presentation_reopen else "0")
        child = subprocess.Popen([node, str(ROOT / "apps/twinpulse-web/e2e/named-room-isaac-real.mjs")],
                                 cwd=ROOT / "apps/twinpulse-web", env=environment,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + 150
        while child.poll() is None and time.monotonic() < deadline:
            sim.update()
            bridge.update()
            assert not omni.timeline.get_timeline_interface().is_playing()
            time.sleep(.005)
        if child.poll() is None:
            raise TimeoutError("Owned browser deadline exceeded")
        browser = json.loads((output / "browser-result.json").read_text(encoding="utf-8"))
        result["browser"] = browser
        assert child.returncode == 0 and browser["status"] == "PASS", "Browser checks failed"
        assert len(broker._operations) == 1
        operation = next(iter(broker._operations.values()))
        assert operation.status == "succeeded"
        result["build_payload_presentation"] = operation.command.payload.get("presentation")
        edited_history = app.scene_change_store().load()
        reviewed_plan, reviewed_site = edited_history.replay(draft)
        reviewed_scene = reviewed_site.scene
        if args.synthetic_warehouse:
            assert [call.tool for call in reviewed_plan.calls] == ["create_floor", "create_rack_row", "create_rack_row"]
            assert len([obj for obj in reviewed_scene.objects if obj.id.startswith("rack_")]) >= 4
            assert stage.GetPrimAtPath("/World/TwinPulse/Environment/rack_left_post_0_a/geometry").IsValid()
            result["checks"].append("synthetic warehouse racks built through saved-scene path; no photo inference")
        assert bool(edited_history.operations) == bool(args.edit_scene or args.edit_furniture or args.furniture_request or args.furniture_staging or args.fake_edit_proposal or
                                                      args.reopen_state or args.expected_edit_revision)
        if args.expected_edit_revision:
            assert reviewed_scene.revision == args.expected_edit_revision
        assert runtime.compiler.matches_site_scene(reviewed_scene)
        furniture_calls = [call for call in reviewed_plan.calls if call.tool == "place_furniture"]
        if furniture_calls:
            assert reviewed_plan.plan_version == "2.1"
            authored_colors = set()
            for item in reviewed_scene.objects:
                if not item.id.startswith("furn_"):
                    continue
                part = stage.GetPrimAtPath(f"/World/TwinPulse/Environment/{item.id}/geometry")
                assert part.IsValid() and part.HasAPI(UsdPhysics.CollisionAPI)
                color = UsdGeom.Gprim(part).GetDisplayColorAttr().Get()
                assert color and len(color) == 1
                authored_colors.add(tuple(round(float(channel), 3) for channel in color[0]))
            assert len(authored_colors) >= min(2, len(furniture_calls))
        if args.edit_scene or args.reopen_state:
            assert len(edited_history.operations) == 4
            assert stage.GetPrimAtPath("/World/TwinPulse/Environment/sofa/geometry").IsValid()
            assert next(item for item in reviewed_scene.objects if item.id == "bed").transform.position_m[0] == -0.4
            assert next(item for item in reviewed_scene.objects if item.id == "desk") == next(
                item for item in draft.site.scene.objects if item.id == "desk")
        if args.edit_furniture or (args.expected_edit_revision and args.existing_state):
            assert len(edited_history.operations) == 3
            assert len(furniture_calls) == 3
            assert stage.GetPrimAtPath("/World/TwinPulse/Environment/furn_3_chair_seat/geometry").IsValid()
            assert not stage.GetPrimAtPath("/World/TwinPulse/Environment/furn_3_storage_body/geometry").IsValid()
            assert len([call for call in draft.plan.calls if call.tool == "place_furniture"]) == 2
        if args.furniture_request:
            assert len(edited_history.operations) == 1
            assert len(furniture_calls) == 3
            chair = next(call for call in furniture_calls if call.arguments["kind"] == "chair")
            assert tuple(chair.arguments["center_m"]) == (0.9, -1.4)
            assert stage.GetPrimAtPath(
                f"/World/TwinPulse/Environment/{chair.arguments['id']}_seat/geometry").IsValid()
        if args.fake_edit_proposal:
            assert len(edited_history.operations) == 1
            assert len(furniture_calls) == 2
            bed = next(call for call in furniture_calls if call.arguments["kind"] == "bed")
            assert tuple(bed.arguments["center_m"]) == (-.7, .8)
        if args.furniture_staging:
            assert len(edited_history.operations) == 1
            assert edited_history.operations[0].mode == "add_many"
            assert len(furniture_calls) == 4
            for kind, x in (("bed", -.85), ("chair", .9)):
                call = next(call for call in furniture_calls[2:] if call.arguments["kind"] == kind)
                assert call.arguments["yaw_deg"] == (180 if kind == "bed" else -90)
                assert abs(call.arguments["center_m"][0] - x) < .03
                assert abs(call.arguments["center_m"][1] + 1.4) < .03
                suffix = "base" if kind == "bed" else "seat"
                assert stage.GetPrimAtPath(
                    f"/World/TwinPulse/Environment/{call.arguments['id']}_{suffix}/geometry").IsValid()
        if args.inject_visual_failure:
            from unittest.mock import patch
            from twinpulse_core import CommandEnvelope
            failed_command = CommandEnvelope(
                command_id="injected-visual-failure", command_type="build_site_scene",
                project_id=project_id, engine_session_id=adapter.engine_session_id,
                stage_epoch=adapter.stage_epoch, control_lease_id="isolated-test-lease",
                expected_applied_revision=draft.site.scene.revision,
                payload={"artifact_id": "isolated-original", "scene_revision": draft.site.scene.revision,
                         "scene": draft.site.scene.to_dict(),
                         "visual_preview": app.room_visual_descriptor(draft)},
            )
            with patch("twinpulse.extension.bedroom_preview.compose_bedroom_preview",
                       side_effect=RuntimeError("injected post-geometry visual failure")):
                try:
                    adapter._build_site_scene(failed_command)
                except RuntimeError as error:
                    assert "injected post-geometry visual failure" in str(error)
                else:
                    raise AssertionError("injected visual failure did not fail the Build")
            assert runtime.compiler.matches_site_scene(reviewed_scene)
            assert adapter.snapshot().applied_revision == reviewed_scene.revision
            assert stage.GetPrimAtPath("/World/TwinPulse/Presentation/BurgerPhotoPreview").IsValid()
            assert stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("marker") == "preserve"
        expected_view, expected_lighting = args.presentation.split(":") if args.presentation else ("auto", "balanced")
        expected_preset = "fit-open-side-v1" if expected_view == "auto" else f"user-{expected_view}-v1"
        result["presentation_observed"] = stage.GetPrimAtPath(PRESENTATION_PATH).GetCustomData()
        result["broker_presentation"] = next(iter(broker._site_scenes.values())).presentation
        assert stage.GetPrimAtPath(PRESENTATION_PATH).GetCustomDataByKey("twinpulseViewPreset") == expected_preset
        if args.presentation:
            assert stage.GetPrimAtPath(PRESENTATION_PATH).GetCustomDataByKey("twinpulsePresentation") == {
                "schema_version": 1, "view": expected_view, "lighting": expected_lighting}
        dome_expected, sun_expected = {"balanced": (400.0, 650.0), "soft": (550.0, 250.0),
                                         "bright": (650.0, 900.0)}[expected_lighting]
        assert float(stage.GetPrimAtPath(DOME_LIGHT_PATH).GetAttribute("inputs:intensity").Get()) == dome_expected
        assert float(stage.GetPrimAtPath(SUN_LIGHT_PATH).GetAttribute("inputs:intensity").Get()) == sun_expected
        camera_matrix = stage.GetPrimAtPath(CAMERA_PATH).GetAttribute("xformOp:transform").Get()
        assert camera_matrix is not None and camera_matrix.ExtractTranslation()[2] < 10.0
        camera_side = stage.GetPrimAtPath(PRESENTATION_PATH).GetCustomDataByKey("twinpulseCameraSide")
        assert camera_side in {"-y", "+y", "-x", "+x", "top"}
        if expected_view == "top":
            assert camera_side == "top" and abs(camera_matrix.ExtractTranslation()[1]) < 1.0
        if args.preserved_bedroom:
            assert camera_side == "-y" and camera_matrix.ExtractTranslation()[1] < -2.1
        if args.capture_viewport:
            from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
            viewport = get_active_viewport()
            viewport.set_active_camera(str(CAMERA_PATH))
            for _ in range(45): sim.update()
            capture_viewport_to_file(viewport, str(output / "authored-camera-viewport.png"))
            for _ in range(45): sim.update()
            assert (output / "authored-camera-viewport.png").stat().st_size > 1000
        marker = stage.GetPrimAtPath(PREVIEW_PATH)
        assert marker.IsValid() and marker.GetCustomDataByKey("twinpulseManifestSha256") == manifest["manifest_sha256"]
        assert marker.GetCustomDataByKey("motionAuthorized") is False
        assert marker.GetCustomDataByKey("worldAlignmentVerified") is False
        assert stage.GetPrimAtPath(PREVIEW_PATH + "/Model").GetVariantSet("Physics").GetVariantSelection() == "none"
        prims = list(Usd.PrimRange(stage.GetPrimAtPath(PREVIEW_PATH + "/Model"), Usd.TraverseInstanceProxies()))
        meshes = sum(prim.IsA(UsdGeom.Mesh) for prim in prims)
        assert meshes == 4
        assert not any(prim.HasAPI(UsdPhysics.RigidBodyAPI) or prim.HasAPI(UsdPhysics.CollisionAPI)
                       or prim.HasAPI(UsdPhysics.ArticulationRootAPI) for prim in prims)
        assert not stage.GetPrimAtPath("/World/TwinPulse/Robot").IsValid()
        assert not stage.GetPrimAtPath("/World/TwinPulse/Task").IsValid()
        assert stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("marker") == "preserve"
        assert not omni.timeline.get_timeline_interface().is_playing()
        assert "run" not in adapter.snapshot().permitted_commands
        # The explicit review/acknowledgement legitimately updates project state;
        # the source recipe and imported draft must remain the same.
        assert recipe_path.read_bytes() == before_recipe
        restored = project_store.load()
        assert restored.site_draft == draft and restored.latest_input == draft.input_revision
        stage.GetRootLayer().Export(str(output / "named-room-browser-stage.usda"))
        saved = Usd.Stage.Open(str(output / "named-room-browser-stage.usda"))
        assert saved.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey("twinpulseManifestSha256") == manifest["manifest_sha256"]
        result.update(status="PASS", visual_mesh_count=meshes,
                      furniture_types=[call.arguments["kind"] for call in furniture_calls],
                      scene_edit_revision=reviewed_scene.revision if edited_history.operations else None,
                      view_preset=expected_preset, camera_side=camera_side,
                      lighting_preset=expected_lighting,
                      manifest_sha256=manifest["manifest_sha256"],
                      checks=result["checks"] + ["actual browser/API/bridge/Isaac named scene Build with one explicit review and no Run",
                              "visual-only pinned Burger and saved USD; recipe and imported draft preserved",
                              "new Isaac process reopened the saved edited scene without prior approval"
                              if args.reopen_state else "scene edits saved to a separate validated sidecar",
                              "failed later visual Build restored prior stage and applied revision"
                              if args.inject_visual_failure else "no visual failure injected",
                              "room-floor fitted camera and bounded authored light values; GUI readability requires image review"
                              if not args.capture_viewport else "authored camera viewport captured for separate visual review"])
    except Exception as error:
        traceback.print_exc()
        result.update(error_type=type(error).__name__, error=str(error)[:500],
                      failure_line=traceback.extract_tb(error.__traceback__)[-1].lineno)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        if bridge:
            bridge.stop()
        if server:
            server.stop()
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("NAMED_ROOM_PRODUCT_ISAAC=" + result["status"], flush=True)
        if sim:
            sim.close()
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
