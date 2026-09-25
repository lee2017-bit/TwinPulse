from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectStore
from twinpulse_app.replay import ReplayOnlyGateway, load_replay_fixture
from twinpulse_core import InputArtifactStore, SceneToolRegistry, demo_warehouse_tool_plan


TEST_TMP = Path(os.environ.get("TWINPULSE_TEST_TMP", ROOT / "artifacts" / "test-tmp"))
TEST_TMP.mkdir(parents=True, exist_ok=True)


class S2dManagedReplayTests(unittest.TestCase):
    @staticmethod
    def report() -> dict[str, object]:
        plan = demo_warehouse_tool_plan()
        bundle = SceneToolRegistry().execute(plan)
        return {
            "schema_version": "1.0",
            "status": "PASS",
            "provider": "Stored Provider",
            "model_id": "stored-model",
            "reasoning_effort": "low",
            "fixtures": [{
                "fixture_id": "stored-one",
                "status": "PASS",
                "request_id": "stored-request",
                "image_filename": "warehouse.jpg",
                "image_sha256": "a" * 64,
                "prompt": "replay this stored warehouse",
                "tool_call_count": len(plan.calls),
                "expanded_object_count": len(bundle.scene.objects),
                "plan": plan.to_dict(),
                "bundle": bundle.to_dict(),
            }],
        }

    def write_report(self, root: Path, value: dict[str, object] | None = None) -> Path:
        path = root / "provider-results.json"
        path.write_text(json.dumps(value or self.report()), encoding="utf-8")
        return path

    def test_loader_preserves_provenance_and_revalidates_plan_bundle(self) -> None:
        with TemporaryDirectory(prefix="s2d-", dir=TEST_TMP) as directory:
            replay = load_replay_fixture(self.write_report(Path(directory)), "stored-one")
        self.assertEqual(replay.source, "replay")
        self.assertEqual(replay.image_sha256, "a" * 64)
        self.assertEqual(replay.record.request_id, "stored-request")
        self.assertEqual(replay.record.provider_name, "Stored Provider")
        self.assertEqual(replay.record.model_id, "stored-model")
        self.assertEqual(len(replay.record.plan.calls), replay.tool_count)
        self.assertEqual(len(replay.record.bundle.scene.objects), replay.object_count)
        self.assertTrue(replay.record.build_allowed_for(replay.input_revision))

    def test_tampered_stored_bundle_is_rejected(self) -> None:
        with TemporaryDirectory(prefix="s2d-", dir=TEST_TMP) as directory:
            value = self.report()
            fixture = value["fixtures"][0]
            fixture["bundle"]["scene"]["id"] = "tampered"
            with self.assertRaisesRegex(ValueError, "bundle"):
                load_replay_fixture(self.write_report(Path(directory), value), "stored-one")

    def test_workflow_registers_replay_without_generation(self) -> None:
        with TemporaryDirectory(prefix="s2d-", dir=TEST_TMP) as directory:
            root = Path(directory)
            replay = load_replay_fixture(self.write_report(root), "stored-one")
            gateway = ReplayOnlyGateway()
            service = ApplicationService(
                gateway,
                project_store=ProjectStore(root / "project.json"),
                artifact_store=InputArtifactStore(root / "inputs"),
            )
            broker = CommandBroker()
            workflow = ProductWorkflow(
                service, broker, mode="replay",
                generation_settings_getter=lambda: {},
                provider_state_getter=lambda: {"configured": False, "label": "Stored replay"},
            )
            state = workflow.load_replay(replay)
            self.assertEqual(state["phase"], "draft_ready")
            self.assertEqual(state["draft"]["source"], "replay")
            self.assertEqual(state["input"]["image_sha256"], "a" * 64)
            self.assertFalse(state["provider"]["connected"])
            self.assertEqual(gateway.generate_calls, 0)
            self.assertEqual(len(broker.public_state("none")["artifacts"]), 1)


if __name__ == "__main__":
    unittest.main()
