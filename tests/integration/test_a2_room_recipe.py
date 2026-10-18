# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A2 project-local room recipes re-open through the existing ApplicationService."""

from __future__ import annotations

from io import BytesIO
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_core import SimulationSnapshot  # noqa: E402
from twinpulse_core.scene_tools import demo_warehouse_tool_plan  # noqa: E402
from twinpulse_core.site_tools import SiteCallEvidence, SiteToolPlan  # noqa: E402
from twinpulse_app import ApplicationService, CommandBroker, LocalApiServer, ProductWorkflow, ProjectStore  # noqa: E402
from twinpulse_app.bedroom_review import load_bedroom_source  # noqa: E402
from twinpulse_app.project_store import ProjectRecord  # noqa: E402
from twinpulse_app.room_recipe import (  # noqa: E402
    checked_project_room_descriptor, import_project_room_recipe, load_project_room_visual,
    prepare_project_burger_visual,
)


class NoGateway:
    def cancel_active(self):
        pass

    async def generate(self, request):
        raise AssertionError("provider must not be called")


def write_recipe(root: Path, project_id: str, color: str, width: float) -> tuple[Path, dict]:
    folder = root / "projects" / project_id
    assets = folder / "assets"
    assets.mkdir(parents=True)
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    photo = buffer.getvalue()
    (assets / "room.png").write_bytes(photo)
    plan = load_bedroom_source()[0].plan.to_dict()
    plan["scene_id"] = project_id
    plan["calls"][0]["arguments"]["size_m"][0] = width
    recipe = {"schema_version": "room-recipe-1.0", "project_id": project_id,
              "prompt": f"Approximate photo room for {project_id}; not measured",
              "photo": {"relative_path": "assets/room.png", "sha256": sha256(photo).hexdigest()},
              "plan": plan}
    (folder / "room_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
    return assets / "room.png", recipe


def write_synthetic_warehouse_recipe(root: Path, project_id: str) -> tuple[Path, dict]:
    """Static warehouse fixture; the placeholder image is never interpreted."""
    photo, recipe = write_recipe(root, project_id, "gray", 8.0)
    calls = demo_warehouse_tool_plan().calls[:3]  # no driven robot or mission
    plan = SiteToolPlan(
        scene_id=project_id,
        summary="Synthetic warehouse fixture with two rack rows; not derived from a photo",
        image_observations="Synthetic placeholder only; no image interpretation or measured geometry",
        calls=calls,
        call_evidence=tuple(SiteCallEvidence(
            call.call_id, (), "inferred", "Deterministic synthetic warehouse fixture, not photo evidence"
        ) for call in calls),
    )
    recipe["prompt"] = "Synthetic warehouse regression fixture; no photo interpretation"
    recipe["plan"] = plan.to_dict()
    (root / "projects" / project_id / "room_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
    return photo, recipe


def add_burger_visual(root: Path, project_id: str, recipe: dict, x: float) -> Path:
    source = load_bedroom_source()[2]
    target = root / "projects" / project_id / "assets" / "burger"
    shutil.copytree(source, target)
    files = {path.relative_to(target).as_posix(): sha256(path.read_bytes()).hexdigest()
             for path in target.rglob("*") if path.is_file()}
    recipe["burger_visual"] = {
        "asset_dir": "assets/burger", "files_sha256": files,
        "position_m": [x, -0.5, 0.002], "yaw_deg": 90.0,
    }
    (target.parent.parent / "room_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
    return target


class ProjectRoomRecipeTests(unittest.TestCase):
    def test_synthetic_warehouse_uses_existing_room_recipe_path_without_robot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, recipe = write_synthetic_warehouse_recipe(root, "warehouse_one")
            before = (root / "projects" / "warehouse_one" / "room_recipe.json").read_bytes()
            draft = import_project_room_recipe(root, "warehouse_one")
            self.assertEqual([call.tool for call in draft.plan.calls],
                             ["create_floor", "create_rack_row", "create_rack_row"])
            self.assertIsNone(draft.site.robot)
            self.assertIsNone(draft.site.mission)
            self.assertEqual(len([obj for obj in draft.site.scene.objects if obj.kind == "rack"]), 16)
            self.assertEqual(len(recipe["plan"]["call_evidence"]), 3)
            self.assertEqual((root / "projects" / "warehouse_one" / "room_recipe.json").read_bytes(), before)

    def test_presentation_is_project_local_and_reopens_without_changing_scene(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            source = import_project_room_recipe(root, "room_one")
            project = ProjectStore.for_project(root, "room_one")
            original = project.path.read_bytes()
            broker = CommandBroker(project_id="room_one")
            workflow = ProductWorkflow(
                ApplicationService(NoGateway(), project_store=project, project_id="room_one"),
                broker, mode="simulation_offline",
                generation_settings_getter=lambda: {"request_schema": "offline-1.0"},
            )
            opened = workflow.continue_room_recipe()
            provenance = opened["site_draft"]["review_provenance"]
            self.assertEqual(provenance["source_class"], "local_recipe")
            self.assertEqual(provenance["photo_interpretation_evidence"], "local_import_not_performed")
            self.assertEqual(provenance["world_alignment"], "NOT_VERIFIED")
            self.assertEqual(provenance["physical_validation"], "NOT_RUN")
            self.assertEqual(provenance["local_edit_count"], 0)
            self.assertEqual(opened["presentation"]["view"], "auto")
            self.assertFalse(opened["presentation"]["saved"])
            revision = source.site.scene.revision
            selected = {"schema_version": 1, "view": "top", "lighting": "soft"}
            saved = workflow.save_presentation(revision, selected)
            self.assertEqual(saved["presentation"]["view"], "top")
            self.assertTrue(saved["presentation"]["saved"])
            self.assertEqual(project.path.read_bytes(), original)
            self.assertEqual(next(iter(broker._site_scenes.values())).presentation, selected)
            sidecar = project.path.with_suffix(".presentation.json")
            original_sidecar = sidecar.read_bytes()
            from twinpulse_app.command_broker import BrokerError
            with self.assertRaises(BrokerError):
                workflow.save_presentation("0" * 64, selected)
            with self.assertRaises(BrokerError):
                workflow.save_presentation(revision, {**selected, "lighting": "unsafe"})
            self.assertEqual(sidecar.read_bytes(), original_sidecar)
            reopened = ProductWorkflow(
                ApplicationService(NoGateway(), project_store=project, project_id="room_one"),
                CommandBroker(project_id="room_one"), mode="simulation_offline",
                generation_settings_getter=lambda: {"request_schema": "offline-1.0"},
            )
            self.assertEqual(reopened.continue_room_recipe()["presentation"]["lighting"], "soft")
            self.assertEqual(project.path.read_bytes(), original)

    def test_scene_edit_api_reopens_same_burger_review_without_mutating_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, recipe = write_recipe(root, "room_one", "red", 2.8)
            add_burger_visual(root, "room_one", recipe, 0.0)
            source = import_project_room_recipe(root, "room_one")
            project = ProjectStore.for_project(root, "room_one")
            original = project.path.read_bytes()
            broker = CommandBroker(project_id="room_one")
            workflow = ProductWorkflow(
                ApplicationService(NoGateway(), project_store=project, project_id="room_one"),
                broker, mode="simulation_offline",
                generation_settings_getter=lambda: {"request_schema": "offline-1.0"},
            )
            server = LocalApiServer(broker, product_bootstrap_secret="p" * 43,
                                    engine_bootstrap_secret="e" * 43, product_workflow=workflow)
            server.start()
            try:
                def post(path, body, headers=None):
                    request = Request(server.base_url + path, data=json.dumps(body).encode(),
                                      headers={"Content-Type": "application/json", **(headers or {})})
                    try:
                        with urlopen(request, timeout=3) as response:
                            return response.status, json.loads(response.read()), response.headers
                    except HTTPError as error:
                        return error.code, json.loads(error.read()), error.headers

                status, session, headers = post("/v1/bootstrap", {"role": "product", "secret": "p" * 43})
                self.assertEqual(status, 200)
                auth = {"Cookie": headers.get("Set-Cookie").split(";", 1)[0],
                        "X-TwinPulse-CSRF": session["csrf_token"]}
                self.assertEqual(post("/v1/product/scene-edit/preview", {}, auth)[0], 400)
                self.assertEqual(post("/v1/product/scene-edit/preview", {
                    "operation_id": "add_sofa", "mode": "add", "target_call_id": None,
                    "tool_call": {"call_id": "sofa", "tool": "create_box_obstacle", "arguments": {
                        "id": "sofa", "center_m": [0.3, 0.2], "dimensions_m": [0.4, 0.5, 0.5],
                        "yaw_deg": 0}},
                }, auth)[0], 409)
                status, opened, _ = post("/v1/product/project/continue-room", {}, auth)
                self.assertEqual(status, 200)
                status, preview, _ = post("/v1/product/scene-edit/preview", {
                    "operation_id": "add_sofa", "mode": "add", "target_call_id": None,
                    "tool_call": {"call_id": "sofa", "tool": "create_box_obstacle", "arguments": {
                        "id": "sofa", "center_m": [0.3, 0.2], "dimensions_m": [0.4, 0.5, 0.5],
                        "yaw_deg": 0}},
                }, auth)
                self.assertEqual(status, 200)
                self.assertEqual(preview["parent_revision"], opened["site_draft"]["revision"])
                project.path.write_bytes(original.replace(b'"room_one"', b'"room_two"', 1))
                try:
                    self.assertEqual(post("/v1/product/scene-edit/apply", {
                        "operation": preview["operation"], "preview_digest": preview["preview_digest"],
                    }, auth)[0], 409)
                    self.assertFalse(project.path.with_suffix(".scene-changes.json").exists())
                finally:
                    project.path.write_bytes(original)
                self.assertEqual(workflow.acknowledge(opened["site_draft"]["revision"])[
                    "acknowledged_revision"], opened["site_draft"]["revision"])
                self.assertEqual(post("/v1/product/scene-edit/apply", {
                    "operation": preview["operation"], "preview_digest": "0" * 64,
                }, auth)[0], 409)
                self.assertEqual(workflow.snapshot()["acknowledged_revision"],
                                 opened["site_draft"]["revision"])
                status, edited, _ = post("/v1/product/scene-edit/apply", {
                    "operation": preview["operation"], "preview_digest": preview["preview_digest"],
                }, auth)
                self.assertEqual(status, 200)
                self.assertEqual(edited["site_draft"]["revision"], preview["result_revision"])
                self.assertEqual(edited["site_draft"]["scene_edit_count"], 1)
                self.assertEqual(edited["site_draft"]["review_provenance"]["local_edit_count"], 1)
                self.assertEqual(next(item for item in edited["site_draft"]["review_provenance"]["calls"]
                                      if item["call_id"] == "sofa")["origin"], "user_local_edit")
                self.assertEqual(next(item for item in edited["site_draft"]["objects"]
                                      if item["id"] == "sofa")["provenance"], "user_local_edit")
                self.assertEqual(next(item for item in edited["site_draft"]["objects"]
                                      if item["id"] == "bed")["provenance"], "local-room-recipe")
                self.assertIsNone(edited["acknowledged_revision"])
                artifact = next(item for item in broker._site_scenes.values()
                                if item.revision == preview["result_revision"])
                self.assertEqual(artifact.visual_preview["scene_change_revision"], preview["result_revision"])
                self.assertIn("sofa", {item.id for item in artifact.scene.objects})
                checked_project_room_descriptor(artifact.visual_preview, artifact.scene, root, "room_one")
                with self.assertRaises(ValueError):
                    checked_project_room_descriptor(artifact.visual_preview, source.site.scene, root, "room_one")
                self.assertEqual(project.path.read_bytes(), original)
                self.assertEqual(post("/v1/product/scene-edit/apply", {
                    "operation": preview["operation"], "preview_digest": "0" * 64,
                }, auth)[0], 409)
            finally:
                server.stop()
            reopened = ProductWorkflow(
                ApplicationService(NoGateway(), project_store=project, project_id="room_one"),
                CommandBroker(project_id="room_one"), mode="simulation_offline",
                generation_settings_getter=lambda: {"request_schema": "offline-1.0"},
            )
            self.assertEqual(reopened.continue_room_recipe()["site_draft"]["revision"], preview["result_revision"])
            self.assertEqual(project.path.read_bytes(), original)

    def test_explicit_cli_prepares_and_imports_without_build(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "import_room_recipe.py"),
                "--state-dir", str(root), "--project-id", "room_one",
                "--include-local-burger-visual", "--visual-x-m", "0.25",
                "--visual-y-m", "-0.5", "--visual-yaw-deg", "90",
            ], capture_output=True, text=True, timeout=20, check=True)
            state = json.loads(result.stdout)
            self.assertTrue(state["burger_visual_prepared"])
            self.assertFalse(state["build_started"])
            self.assertEqual(state["physical_validation"], "NOT_RUN")
            self.assertIsNotNone(ProjectStore.for_project(root, "room_one").load().site_draft)

    def test_visual_cli_refuses_implicit_state_root(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "scripts" / "import_room_recipe.py"),
            "--project-id", "room_one", "--include-local-burger-visual",
            "--visual-x-m", "0", "--visual-y-m", "0", "--visual-yaw-deg", "0",
        ], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit --state-dir", result.stderr)

    def test_explicit_local_burger_preparation_keeps_original_and_imports(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            project = root / "projects" / "room_one"
            original = (project / "room_recipe.json").read_bytes()
            manifest = prepare_project_burger_visual(root, "room_one", (0.25, -0.5, 0.002), 90.0)
            self.assertEqual((project / "room_recipe.before-burger.json").read_bytes(), original)
            self.assertEqual(manifest["robot_placement"]["pose_status"], "ILLUSTRATIVE_NOT_MEASURED")
            draft = import_project_room_recipe(root, "room_one")
            self.assertIsNotNone(load_project_room_visual(root, "room_one", draft))
            with self.assertRaisesRegex(ValueError, "already imported"):
                prepare_project_burger_visual(root, "room_one", (0.0, 0.0, 0.002), 0.0)

    def test_empty_named_project_can_prepare_burger_without_replacing_project_record(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            store = ProjectStore.for_project(root, "room_one")
            store.save(ProjectRecord(project_id="room_one"))
            before = store.path.read_bytes()
            manifest = prepare_project_burger_visual(root, "room_one", (0.25, -0.5, 0.002), 90.0)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertFalse(manifest["execution_authority"])
            imported = import_project_room_recipe(root, "room_one")
            self.assertEqual(imported.input_revision.input_kind, "photo")

    def test_invalid_visual_preparation_does_not_write_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            project = root / "projects" / "room_one"
            original = (project / "room_recipe.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "placement is invalid"):
                prepare_project_burger_visual(root, "room_one", (0.0, 0.0, float("nan")), 90.0)
            self.assertEqual((project / "room_recipe.json").read_bytes(), original)
            self.assertFalse((project / "assets" / "burger").exists())
            self.assertFalse((project / "room_recipe.before-burger.json").exists())

    def test_two_pinned_burger_visuals_continue_in_separate_projects(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            descriptors = []
            for project_id, color, x in (("room_one", "red", -0.3), ("room_two", "blue", 0.5)):
                _, recipe = write_recipe(root, project_id, color, 2.8)
                add_burger_visual(root, project_id, recipe, x)
                draft = import_project_room_recipe(root, project_id)
                app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(root, project_id),
                                         project_id=project_id)
                broker = CommandBroker(project_id=project_id)
                workflow = ProductWorkflow(app, broker, mode="simulation_offline",
                                           generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
                self.assertFalse(workflow.snapshot()["build_allowed"])
                self.assertIsNone(workflow.snapshot()["acknowledged_revision"])
                continued = workflow.continue_room_recipe()
                self.assertFalse(continued["build_allowed"])
                artifact = next(iter(broker._site_scenes.values()))
                descriptor = artifact.visual_preview
                self.assertEqual(descriptor["kind"], "project_room_visual_v1")
                checked_draft, manifest, path = checked_project_room_descriptor(
                    descriptor, artifact.scene, root, project_id)
                self.assertEqual(checked_draft, draft)
                self.assertEqual(manifest["robot_placement"]["position_m"][0], x)
                self.assertTrue(path.is_relative_to(root / "projects" / project_id))
                self.assertFalse(manifest["execution_authority"])
                broker.register_engine("engine", "stage")
                broker.acquire_lease("product")
                broker.record_snapshot(SimulationSnapshot(
                    engine_session_id="engine", stage_epoch="stage", project_id=project_id,
                    applied_revision=None, run_id=None, sequence=1, runtime_state="idle",
                    safety_state=None, safety_reason=None,
                    permitted_commands=("build_site_scene", "get_state"),
                    capabilities=("simulation", "site_scene_build_v2", "project_room_visual_v1"),
                    telemetry_available=False))
                broker.submit("product", {"client_request_id": "project-preview",
                    "command_type": "build_site_scene", "artifact_id": artifact.artifact_id,
                    "expected_applied_revision": artifact.revision})
                command = broker.claim("engine", "stage")
                self.assertEqual(command.payload["visual_preview"], descriptor)
                self.assertNotIn("mission", command.payload)
                descriptors.append(descriptor)
            self.assertNotEqual(descriptors[0], descriptors[1])
            with self.assertRaisesRegex(ValueError, "does not match"):
                checked_project_room_descriptor(descriptors[0], draft.site.scene, root, "room_two")
            with TemporaryDirectory() as copied_dir:
                copied = Path(copied_dir)
                shutil.copytree(root / "projects", copied / "projects")
                restored = ProjectStore.for_project(copied, "room_one").load()
                self.assertIsNotNone(restored.site_draft)
                _, moved_manifest, moved_assets = checked_project_room_descriptor(
                    descriptors[0], restored.site_draft.site.scene, copied, "room_one")
                self.assertEqual(moved_manifest["manifest_sha256"], descriptors[0]["manifest_sha256"])
                self.assertTrue(moved_assets.is_relative_to(copied))

    def test_pinned_visual_changed_or_missing_blocks_saved_project(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, recipe = write_recipe(root, "room_one", "red", 2.8)
            assets = add_burger_visual(root, "room_one", recipe, 0.0)
            import_project_room_recipe(root, "room_one")
            store = ProjectStore.for_project(root, "room_one")
            original = store.path.read_bytes()
            model = assets / "payloads" / "robot.usda"
            saved = model.read_bytes()
            model.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                store.load()
            self.assertEqual(store.path.read_bytes(), original)
            model.write_bytes(saved)
            model.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                store.load()
            self.assertEqual(store.path.read_bytes(), original)

    def test_pinned_visual_rejects_escape_and_false_pose_authority(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, recipe = write_recipe(root, "room_one", "red", 2.8)
            add_burger_visual(root, "room_one", recipe, 0.0)
            path = root / "projects" / "room_one" / "room_recipe.json"
            recipe["burger_visual"]["asset_dir"] = "../burger"
            path.write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest is invalid"):
                import_project_room_recipe(root, "room_one")
            recipe["burger_visual"]["asset_dir"] = "assets/burger"
            recipe["burger_visual"]["position_m"] = [0.0, 0.0, float("nan")]
            path.write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "finite|placement is invalid"):
                import_project_room_recipe(root, "room_one")
            recipe["burger_visual"]["position_m"] = [0.0, 0.0, 0.002]
            changed = root / "projects" / "room_one" / "assets" / "burger" / "payloads" / "robot.usda"
            changed.write_bytes(b"foreign USD content")
            recipe["burger_visual"]["files_sha256"]["payloads/robot.usda"] = sha256(changed.read_bytes()).hexdigest()
            path.write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                import_project_room_recipe(root, "room_one")

    def test_authenticated_continue_endpoint_requires_fresh_review(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            import_project_room_recipe(root, "room_one")
            broker = CommandBroker(project_id="room_one")
            app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(root, "room_one"),
                                     project_id="room_one")
            workflow = ProductWorkflow(app, broker, mode="simulation_offline",
                                       generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
            server = LocalApiServer(broker, product_bootstrap_secret="p" * 43,
                                    engine_bootstrap_secret="e" * 43, product_workflow=workflow)
            server.start()
            try:
                def post(path, body, headers=None):
                    request = Request(server.base_url + path, data=json.dumps(body).encode(),
                                      headers={"Content-Type": "application/json", **(headers or {})})
                    try:
                        with urlopen(request, timeout=3) as response:
                            return response.status, json.loads(response.read()), response.headers
                    except HTTPError as error:
                        return error.code, json.loads(error.read()), error.headers
                self.assertEqual(post("/v1/product/project/continue-room", {})[0], 401)
                status, session, headers = post("/v1/bootstrap", {"role": "product", "secret": "p" * 43})
                self.assertEqual(status, 200)
                cookie = headers.get("Set-Cookie").split(";", 1)[0]
                self.assertNotEqual(post("/v1/product/project/continue-room", {}, {"Cookie": cookie})[0], 200)
                status, result, _ = post("/v1/product/project/continue-room", {},
                                         {"Cookie": cookie, "X-TwinPulse-CSRF": session["csrf_token"]})
                self.assertEqual(status, 200)
                self.assertEqual(result["phase"], "draft_ready")
                self.assertFalse(result["build_allowed"])
                self.assertIsNone(result["acknowledged_revision"])
                self.assertFalse(broker.public_state("unowned")["lease_owned"])
                self.assertEqual(post("/v1/product/bedroom/prepare", {},
                                      {"Cookie": cookie, "X-TwinPulse-CSRF": session["csrf_token"]})[0], 409)
            finally:
                server.stop()

    def test_two_recipes_import_and_reopen_without_build_authority(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_recipe(root, "room_one", "red", 2.8)
            write_recipe(root, "room_two", "blue", 3.3)
            first = import_project_room_recipe(root, "room_one")
            second = import_project_room_recipe(root, "room_two")
            self.assertNotEqual(first.site.scene.revision, second.site.scene.revision)
            for project_id, draft in (("room_one", first), ("room_two", second)):
                app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(root, project_id),
                                         project_id=project_id)
                self.assertEqual(app.site_draft, draft)
                self.assertFalse(app.snapshot().build_allowed)
                self.assertIsNone(app.site_draft.site.robot)
                self.assertIsNone(app.site_draft.site.mission)
                workflow = ProductWorkflow(app, CommandBroker(project_id=project_id),
                                           mode="simulation_offline",
                                           generation_settings_getter=lambda: {"request_schema": "offline-1.0"})
                product = workflow.snapshot()
                self.assertEqual(product["phase"], "restore_review_required")
                self.assertIsNotNone(product["site_draft"])
                self.assertFalse(product["build_allowed"])
                resumed = workflow.continue_room_recipe()
                self.assertEqual(resumed["phase"], "draft_ready")
                self.assertIsNotNone(resumed["site_draft"]["artifact_id"])
                self.assertIsNone(resumed["acknowledged_revision"])
                self.assertFalse(resumed["build_allowed"])
                with self.assertRaisesRegex(ValueError, "already contains"):
                    import_project_room_recipe(root, project_id)

    def test_photo_change_fails_closed_on_reopen_without_rewriting_record(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            photo, recipe = write_recipe(root, "room_one", "red", 2.8)
            original_photo = photo.read_bytes()
            import_project_room_recipe(root, "room_one")
            store = ProjectStore.for_project(root, "room_one")
            saved = store.path.read_bytes()
            photo.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash changed"):
                ApplicationService(NoGateway(), project_store=store, project_id="room_one")
            self.assertEqual(store.path.read_bytes(), saved)
            guarded = ApplicationService(NoGateway(), project_store=store, project_id="room_one",
                                         allow_invalid_restore=True)
            self.assertEqual(guarded.restore_error[0], "project_restore_invalid")
            with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
                guarded.select_input(guarded.prepare_input(prompt="new", images=(),
                    measurement_constraints=(), generation_settings={"request_schema": "1.0"}))
            self.assertEqual(store.path.read_bytes(), saved)
            photo.write_bytes(original_photo)
            recipe["plan"]["calls"][0]["arguments"]["size_m"][0] = 3.1
            (photo.parent.parent / "room_recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                store.load()
            self.assertEqual(store.path.read_bytes(), saved)

    def test_copy_to_another_allowed_root_and_missing_photo(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as copied_dir:
            source = Path(source_dir)
            photo, _ = write_recipe(source, "room_one", "red", 2.8)
            draft = import_project_room_recipe(source, "room_one")
            copied = Path(copied_dir)
            shutil.copytree(source / "projects", copied / "projects")
            app = ApplicationService(NoGateway(), project_store=ProjectStore.for_project(copied, "room_one"),
                                     project_id="room_one")
            self.assertEqual(app.site_draft, draft)
            self.assertFalse(app.snapshot().build_allowed)
            moved_photo = copied / photo.relative_to(source)
            moved_photo.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                ProjectStore.for_project(copied, "room_one").load()

    def test_traversal_measured_claim_and_mission_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, recipe = write_recipe(root, "room_one", "red", 2.8)
            path = root / "projects" / "room_one" / "room_recipe.json"
            recipe["photo"]["relative_path"] = "assets/../outside.png"
            path.write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "project-relative"):
                import_project_room_recipe(root, "room_one")
            recipe["photo"]["relative_path"] = "assets/room.png"
            recipe["plan"]["call_evidence"][0]["basis"] = "trusted_measurement"
            path.write_text(json.dumps(recipe), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot assert measured"):
                import_project_room_recipe(root, "room_one")

    def test_preserved_default_room_golden(self):
        draft, manifest, _ = load_bedroom_source()
        self.assertEqual(draft.plan_sha256, "4345d53d91133f05ea5d8960e808708362a21cc9882605a229f2242edfa198dd")
        self.assertEqual(draft.site.scene.revision, "c18410caf2fd41628b7487de1dabb0ee84b3161ac0a4ac0870f7a7cddf61b8b8")
        self.assertEqual(manifest["manifest_sha256"], "176e0bdc569aeff37b5173a77afbc48f185678efd306dd0ac12e7a6d7a8fefe1")


if __name__ == "__main__":
    unittest.main()
