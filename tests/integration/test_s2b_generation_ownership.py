"""S2b generation ownership, stale-result, acknowledgement, and restore gates."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Event
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = os.environ.get("TWINPULSE_TEST_TMP")
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ApplicationService, CommandBroker, ProductWorkflow, ProjectStore  # noqa: E402
from twinpulse_core import InputArtifactStore, SceneToolPlan, SceneToolRegistry, demo_warehouse_tool_plan  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    GenerationResult,
    GenerationService,
    InvalidProviderResponseError,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderConfig,
)


class InputDependentGateway:
    def __init__(self) -> None:
        self.wait: Event | None = None
        self.error: Exception | None = None
        self.cancel_count = 0

    def cancel_active(self) -> None:
        self.cancel_count += 1

    async def generate(self, request):
        if self.wait is not None:
            await asyncio.to_thread(self.wait.wait)
        if self.error is not None:
            raise self.error
        suffix = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()[:10]
        payload = demo_warehouse_tool_plan().to_dict()
        payload["scene_id"] = f"scene_{suffix}"
        payload["summary"] = f"Generated for {suffix}"
        payload["image_observations"] = f"input={suffix}; images={len(request.images)}"
        plan = SceneToolPlan.from_dict(payload)
        return GenerationResult(
            request.request_id, "input-dependent-fake", "fake-model", len(request.images),
            plan, SceneToolRegistry().execute(plan), len(request.measurement_constraints), 0,
        )


class S2bGenerationOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflows: list[ProductWorkflow] = []
        if TEST_TMP:
            self.root = Path(TEST_TMP) / f"s2b-{uuid.uuid4().hex}"
            self.root.mkdir(parents=True)
            self.temporary = None
        else:
            self.temporary = tempfile.TemporaryDirectory()
            self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        for workflow in self.workflows:
            workflow.shutdown()
        if self.temporary is not None:
            self.temporary.cleanup()
        else:
            shutil.rmtree(self.root, ignore_errors=True)

    def make_workflow(self, gateway: InputDependentGateway | None = None):
        selected = gateway or InputDependentGateway()
        broker = CommandBroker()
        service = ApplicationService(
            selected,
            project_store=ProjectStore(self.root / "active_project.json"),
            artifact_store=InputArtifactStore(self.root / "inputs"),
        )
        workflow = ProductWorkflow(
            service, broker, mode="live_provider",
            generation_settings_getter=lambda: {
                "base_url": "https://example.test/v1/", "model_id": "fake-model",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
            provider_state_getter=lambda: {"configured": True, "label": "fake-model"},
            gateway_factory=lambda: selected,
        )
        self.workflows.append(workflow)
        return workflow, service, broker, selected

    @staticmethod
    def select(workflow: ProductWorkflow, prompt: str) -> dict[str, object]:
        return workflow.select_input({
            "name": None, "input_kind": "auto", "prompt": prompt,
            "media_type": None, "content_base64": None,
            "sidecar_name": None, "sidecar_content_base64": None,
        })

    @staticmethod
    def generate(workflow: ProductWorkflow) -> dict[str, object]:
        workflow.start_generation()
        deadline = time.monotonic() + 2.0
        state = workflow.snapshot()
        while state["phase"] == "generating" and time.monotonic() < deadline:
            time.sleep(0.01)
            state = workflow.snapshot()
        return state

    def test_distinct_inputs_create_distinct_validated_broker_artifacts(self) -> None:
        workflow, _service, broker, _gateway = self.make_workflow()
        first_input = self.select(workflow, "two narrow rack rows")
        first = self.generate(workflow)
        second_input = self.select(workflow, "one open hall with work cells")
        second = self.generate(workflow)
        self.assertEqual(first["phase"], "draft_ready")
        self.assertEqual(second["phase"], "draft_ready")
        self.assertNotEqual(first_input["input"]["revision"], second_input["input"]["revision"])
        self.assertNotEqual(first["draft"]["plan_sha256"], second["draft"]["plan_sha256"])
        self.assertNotEqual(first["draft"]["artifact_id"], second["draft"]["artifact_id"])
        self.assertEqual(len(broker.public_state("nobody")["artifacts"]), 2)

    def test_input_change_and_cancel_discard_late_success(self) -> None:
        gateway = InputDependentGateway()
        gateway.wait = Event()
        workflow, service, _broker, _ = self.make_workflow(gateway)
        self.select(workflow, "old input")
        workflow.start_generation()
        self.select(workflow, "new input")
        with self.assertRaisesRegex(Exception, "already running"):
            workflow.start_generation()
        gateway.wait.set()
        time.sleep(0.1)
        self.assertEqual(workflow.snapshot()["phase"], "input_ready")
        self.assertIsNone(workflow.snapshot()["draft"])
        self.assertFalse(workflow.snapshot()["build_allowed"])
        self.assertIsNone(service.record)

        gateway.wait = Event()
        workflow.start_generation()
        cancelled = workflow.cancel()
        gateway.wait.set()
        self.assertEqual(cancelled["phase"], "cancelled")
        self.assertFalse(cancelled["build_allowed"])

    def test_invalid_provider_result_is_structured_and_previous_draft_is_not_replaced(self) -> None:
        workflow, service, _broker, gateway = self.make_workflow()
        self.select(workflow, "valid first")
        first = self.generate(workflow)
        original = service.record
        self.assertEqual(first["phase"], "draft_ready")
        self.select(workflow, "invalid second")
        gateway.error = InvalidProviderResponseError("unsupported tool evil_exec")
        failed = self.generate(workflow)
        self.assertEqual(failed["phase"], "generation_failed")
        self.assertEqual(failed["error"]["code"], "provider_response_invalid")
        self.assertFalse(failed["build_allowed"])
        self.assertEqual(service.record, original)

    def test_acknowledgement_is_bound_to_both_input_and_draft(self) -> None:
        workflow, _service, _broker, _gateway = self.make_workflow()
        self.select(workflow, "ack this")
        ready = self.generate(workflow)
        acknowledged = workflow.acknowledge(ready["draft"]["revision"])
        self.assertTrue(acknowledged["build_allowed"])
        self.select(workflow, "changed input")
        self.assertFalse(workflow.snapshot()["build_allowed"])
        with self.assertRaisesRegex(Exception, "Acknowledge"):
            workflow.assert_build_allowed(
                ready["draft"]["artifact_id"], ready["draft"]["revision"],
            )

    def test_restart_requires_reselection_and_review_before_build(self) -> None:
        workflow, _service, broker, _gateway = self.make_workflow()
        self.select(workflow, "persist me")
        ready = self.generate(workflow)
        self.assertEqual(ready["phase"], "draft_ready")

        restored_service = ApplicationService(
            InputDependentGateway(),
            project_store=ProjectStore(self.root / "active_project.json"),
            artifact_store=InputArtifactStore(self.root / "inputs"),
        )
        restored = ProductWorkflow(
            restored_service, broker, mode="live_provider",
            generation_settings_getter=lambda: {
                "base_url": "https://example.test/v1/", "model_id": "fake-model",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
        )
        self.workflows.append(restored)
        state = restored.snapshot()
        self.assertEqual(state["phase"], "restore_review_required")
        self.assertFalse(state["build_allowed"])
        self.assertEqual(state["draft"]["input_revision"], ready["input"]["revision"])
        reselected = self.select(restored, "persist me")
        self.assertEqual(reselected["phase"], "draft_ready")
        self.assertFalse(reselected["build_allowed"])

    def test_corrupt_restore_is_explicit_and_never_enables_build(self) -> None:
        path = self.root / "active_project.json"
        path.write_text('{"schema_version":"broken"}', encoding="utf-8")
        service = ApplicationService(
            InputDependentGateway(), project_store=ProjectStore(path),
            artifact_store=InputArtifactStore(self.root / "inputs"),
            allow_invalid_restore=True,
        )
        broker = CommandBroker()
        workflow = ProductWorkflow(
            service, broker, mode="live_provider",
            generation_settings_getter=lambda: {
                "base_url": "https://example.test/v1/", "model_id": "fake-model",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
        )
        self.workflows.append(workflow)
        state = workflow.snapshot()
        self.assertEqual(state["phase"], "restore_review_required")
        self.assertEqual(state["error"]["code"], "project_restore_invalid")
        self.assertIsNone(state["draft"])
        self.assertFalse(state["build_allowed"])
        self.assertEqual(path.read_text(encoding="utf-8"), '{"schema_version":"broken"}')

    def test_live_mode_without_credential_fails_instead_of_using_fixture(self) -> None:
        gateway = GenerationService(
            OpenAIResponsesProvider(lambda: None),
            ProviderConfig(
                base_url="https://provider.example/v1/", endpoint_path="responses",
                model_id="unconfigured-live-model", api_key_env="TWINPULSE_TEST_MISSING_KEY",
                capabilities=ProviderCapabilities(True, True, 1, ("image/png", "image/jpeg", "image/webp")),
                timeout_s=1.0, max_attempts=1,
            ),
        )
        service = ApplicationService(
            gateway, project_store=ProjectStore(self.root / "live-project.json"),
            artifact_store=InputArtifactStore(self.root / "live-inputs"),
        )
        broker = CommandBroker()
        workflow = ProductWorkflow(
            service, broker, mode="live_provider",
            generation_settings_getter=lambda: {
                "base_url": "https://provider.example/v1/", "model_id": "unconfigured-live-model",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
            provider_state_getter=lambda: {"configured": False, "label": "unconfigured-live-model"},
        )
        self.workflows.append(workflow)
        self.select(workflow, "do not fall back")
        state = self.generate(workflow)
        self.assertEqual(state["phase"], "generation_failed")
        self.assertEqual(state["error"]["code"], "provider_not_configured")
        self.assertIsNone(state["draft"])
        self.assertEqual(broker.public_state("nobody")["artifacts"], [])


if __name__ == "__main__":
    unittest.main()
