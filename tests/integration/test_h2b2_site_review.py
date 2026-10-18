# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2b-2: v2 draft persists for review and cannot inherit v1 Build authority."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
for source in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / source / "src"))

from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectRecord, ProjectStore, SiteDraftRecord
from twinpulse_core import (CommandReceipt, InputArtifactStore, SiteToolPlan, SimulationSnapshot,
                            demo_warehouse_tool_plan)
from twinpulse_provider import SiteGenerationResult


class SiteGateway:
    def cancel_active(self) -> None:
        pass

    async def generate(self, request):
        plan = SiteToolPlan("review_site", "A scene-only proposal", "Local fixture",
                            tuple(demo_warehouse_tool_plan().calls[:1]))
        return SiteGenerationResult(request.request_id, "fake", "fake-model", len(request.images), plan)


def make_app(root: Path) -> ApplicationService:
    return ApplicationService(SiteGateway(), project_store=ProjectStore(root / "project.json"),
                              artifact_store=InputArtifactStore(root / "inputs"))


class H2b2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_site_cannot_be_replaced_by_full_scene_regeneration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = make_app(root)
            original = app.prepare_input(prompt="Original site", images=(), measurement_constraints=(),
                                         generation_settings={"model_id": "fake"})
            app.select_input(original)
            await app.generate()
            prior_bytes = (root / "project.json").read_bytes()
            workflow = ProductWorkflow(app, CommandBroker(), mode="live_provider",
                                       generation_settings_getter=lambda: {"model_id": "fake"})
            try:
                self.assertTrue(workflow.snapshot()["saved_site_scene_protected"])
                provenance = workflow.snapshot()["site_draft"]["review_provenance"]
                self.assertEqual(provenance["source_class"], "saved_provider_or_fixture_plan")
                self.assertEqual(provenance["photo_interpretation_evidence"], "not_verified_by_saved_plan")
                self.assertTrue(all(item["basis"] == "unprovided" for item in provenance["calls"]))
                with self.assertRaisesRegex(Exception, "cannot be replaced"):
                    workflow.start_generation()
                self.assertEqual((root / "project.json").read_bytes(), prior_bytes)
                self.assertEqual(app.site_draft.input_revision.digest, original.revision.digest)
            finally:
                workflow.shutdown()

    async def test_v2_broker_requires_engine_capability_and_preserves_scene_revision(self):
        with TemporaryDirectory() as directory:
            app = make_app(Path(directory))
            prepared = app.prepare_input(prompt="Scene only", images=(), measurement_constraints=(),
                                         generation_settings={"model_id": "fake"})
            app.select_input(prepared)
            outcome = await app.generate()
            scene = outcome.record.site.scene
            broker = CommandBroker()
            artifact = broker.register_site_scene("site-test", scene)
            broker.register_engine("engine", "stage")
            broker.acquire_lease("product")
            request = {"client_request_id": "request-v2", "command_type": "build_site_scene",
                       "expected_applied_revision": scene.revision, "artifact_id": artifact.artifact_id}
            with self.assertRaisesRegex(Exception, "cannot build site scenes"):
                broker.submit("product", request)
            broker.record_snapshot(SimulationSnapshot(
                engine_session_id="engine", stage_epoch="stage", project_id="default",
                applied_revision=None, run_id=None, sequence=1, runtime_state="idle",
                safety_state=None, safety_reason=None,
                permitted_commands=("build_site_scene", "get_state"),
                capabilities=("simulation", "site_scene_build_v2"), telemetry_available=False,
            ))
            operation = broker.submit("product", request)
            command = broker.claim("engine", "stage")
            self.assertEqual(operation["expected_applied_revision"], scene.revision)
            self.assertEqual(command.payload["scene_revision"], scene.revision)
            self.assertEqual(command.payload["scene"]["schema_version"], "2.0")
            self.assertNotIn("robot", command.payload)
            self.assertNotIn("mission", command.payload)
            wrong = CommandReceipt(
                command_id=command.command_id, command_type=command.command_type,
                project_id="default", engine_session_id="engine", stage_epoch="stage",
                status="succeeded", applied_revision="0" * 64,
            )
            with self.assertRaisesRegex(Exception, "revision does not match"):
                broker.record_receipt(wrong)
            broker.record_receipt(CommandReceipt(
                command_id=command.command_id, command_type=command.command_type,
                project_id="default", engine_session_id="engine", stage_epoch="stage",
                status="succeeded", applied_revision=scene.revision,
                build_fingerprint="a" * 64,
            ))
            broker.record_snapshot(SimulationSnapshot(
                engine_session_id="engine", stage_epoch="stage", project_id="default",
                applied_revision=scene.revision, run_id=None, sequence=2, runtime_state="built",
                safety_state=None, safety_reason=None,
                permitted_commands=("build_site_scene", "run", "get_state"),
                capabilities=("simulation", "site_scene_build_v2"), telemetry_available=False,
            ))
            with self.assertRaisesRegex(Exception, "no authorized robot mission"):
                broker.submit("product", {"client_request_id": "bad-run", "command_type": "run",
                                          "expected_applied_revision": scene.revision})

    async def test_optional_robot_mission_roundtrip_preserves_goal_without_run_authority(self):
        with TemporaryDirectory() as directory:
            app = make_app(Path(directory))
            prepared = app.prepare_input(prompt="A site with a robot and task", images=(),
                                         measurement_constraints=(), generation_settings={"model_id": "fake"})
            demo = demo_warehouse_tool_plan()
            plan = SiteToolPlan("site_robot", "Robot proposal", "Fixture",
                                (demo.calls[0], demo.calls[-2], demo.calls[-1]))
            record = SiteDraftRecord.create(request_id="request", provider_name="fake", model_id="fake",
                                            image_count=0, input_revision=prepared.revision, plan=plan)
            checked = SiteDraftRecord.from_dict(json.loads(json.dumps(record.to_dict())))
            self.assertIsNotNone(checked.site.robot)
            self.assertEqual(checked.site.mission.goal, record.site.mission.goal)
            self.assertIsNone(checked.site.navigation_map)
            self.assertTrue(checked.site.review_required)

    async def test_single_owner_persists_review_only_and_rejects_tampering(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = make_app(root)
            prepared = app.prepare_input(prompt="Describe this site", images=(),
                                         measurement_constraints=(),
                                         generation_settings={"model_id": "fake"})
            app.select_input(prepared)
            outcome = await app.generate()
            self.assertTrue(outcome.persisted)
            self.assertIsNone(app.record)
            self.assertEqual(app.site_draft.site.robot, None)
            self.assertEqual(app.site_draft.site.mission, None)
            self.assertFalse(app.snapshot(prepared.revision).build_allowed)
            with self.assertRaisesRegex(RuntimeError, "No validated"):
                app.build_candidate(prepared.revision)
            stored = json.loads((root / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], "2.0")
            self.assertIsNone(stored["draft"])
            self.assertEqual(stored["site_draft"]["input_revision"]["digest"], prepared.revision.digest)
            restored = make_app(root)
            self.assertIsNotNone(restored.site_draft)
            self.assertFalse(restored.snapshot(prepared.revision).build_allowed)
            replay = ProductWorkflow(restored, CommandBroker(), mode="live_provider",
                generation_settings_getter=lambda: {"model_id": "fake"})
            self.assertEqual(replay.snapshot()["phase"], "restore_review_required")
            self.assertIsNotNone(replay.snapshot()["site_draft"])
            selected = replay.select_input({"name": None, "input_kind": "auto", "prompt": "Describe this site",
                                            "media_type": None, "content_base64": None,
                                            "sidecar_name": None, "sidecar_content_base64": None})
            self.assertEqual(selected["phase"], "draft_ready")
            self.assertIsNotNone(selected["site_draft"])
            self.assertFalse(selected["build_allowed"])
            replay.shutdown()
            stored["site_draft"]["site"]["scene"]["source"] = "photo"
            with self.assertRaises(ValueError):
                ProjectRecord.from_dict(stored)

    async def test_legacy_reader_does_not_gain_v2_authority(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            old = {"schema_version": "1.0", "project_id": "default", "latest_input": None,
                   "draft": None, "updated_at_utc": ""}
            path.write_text(json.dumps(old), encoding="utf-8")
            app = make_app(path.parent)
            self.assertIsNone(app.site_draft)
            self.assertFalse(app.snapshot().build_allowed)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), old)

    async def test_product_api_state_requires_capability_after_acknowledgement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = make_app(root)
            broker = CommandBroker()
            workflow = ProductWorkflow(app, broker, mode="live_provider",
                generation_settings_getter=lambda: {"model_id": "fake"},
                provider_state_getter=lambda: {"configured": True, "label": "fake"})
            try:
                workflow.select_input({"name": None, "input_kind": "auto", "prompt": "Describe site",
                                       "media_type": None, "content_base64": None,
                                       "sidecar_name": None, "sidecar_content_base64": None})
                workflow.start_generation()
                for _ in range(100):
                    state = workflow.snapshot()
                    if state["phase"] != "generating":
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(state["phase"], "draft_ready")
                self.assertIsNone(state["draft"])
                self.assertEqual(state["site_draft"]["schema_version"], "2.0")
                self.assertFalse(state["build_allowed"])
                self.assertFalse(state["site_draft"]["run_allowed"])
                self.assertIsNotNone(state["site_draft"]["artifact_id"])
                acknowledged = workflow.acknowledge(state["site_draft"]["revision"])
                self.assertEqual(acknowledged["acknowledged_revision"], state["site_draft"]["revision"])
                self.assertFalse(acknowledged["site_draft"]["build_allowed"])
                with self.assertRaisesRegex(Exception, "Acknowledge"):
                    workflow.assert_build_allowed("any", state["site_draft"]["revision"])
                with self.assertRaisesRegex(Exception, "cannot build site scenes"):
                    workflow.assert_site_build_allowed(state["site_draft"]["artifact_id"],
                                                       state["site_draft"]["revision"])
                with self.assertRaisesRegex(Exception, "review-only"):
                    workflow.assert_run_not_site_draft()
            finally:
                workflow.shutdown()
