# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""R3 application-service, persistence, and pure engine-contract acceptance."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = os.environ.get("TWINPULSE_TEST_TMP")
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import (  # noqa: E402
    ApplicationService,
    JsonProviderSettingsStore,
    ProjectStore,
    ProviderSettings,
    migrate_legacy_settings_once,
)
from twinpulse_core import (  # noqa: E402
    CommandEnvelope,
    CommandReceipt,
    GeneratedDraftStore,
    InputArtifactStore,
    SceneToolRegistry,
    SimulationSnapshot,
    demo_warehouse_tool_plan,
)
from twinpulse_provider import GenerationResult  # noqa: E402


class FakeGateway:
    def __init__(self) -> None:
        self.cancel_count = 0
        self.error: Exception | None = None
        self.wait: asyncio.Event | None = None

    def cancel_active(self) -> None:
        self.cancel_count += 1

    async def generate(self, request):
        if self.wait is not None:
            await self.wait.wait()
        if self.error is not None:
            raise self.error
        plan = demo_warehouse_tool_plan()
        return GenerationResult(
            request.request_id, "fake", "fake-model", len(request.images), plan,
            SceneToolRegistry().execute(plan), len(request.measurement_constraints), 0,
        )


class FakeSimulationPort:
    def __init__(self, *, wrong_revision: bool = False) -> None:
        self.commands: list[CommandEnvelope] = []
        self.wrong_revision = wrong_revision

    def execute(self, command: CommandEnvelope) -> CommandReceipt:
        self.commands.append(command)
        return CommandReceipt(
            command_id=command.command_id, command_type=command.command_type,
            project_id=command.project_id, engine_session_id=command.engine_session_id,
            stage_epoch=command.stage_epoch, status="succeeded",
            applied_revision=("wrong" if self.wrong_revision else command.expected_applied_revision),
            build_fingerprint="f" * 64 if command.command_type == "build_scene" else None,
        )

    def snapshot(self) -> SimulationSnapshot:
        return SimulationSnapshot(
            engine_session_id="engine-1", stage_epoch="stage-1", project_id="default",
            applied_revision=None, run_id=None, sequence=0, runtime_state="idle",
            safety_state=None, safety_reason=None,
            permitted_commands=("build_scene", "get_state"), capabilities=("simulation",),
        )


class R3ApplicationTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, root: Path, gateway: FakeGateway | None = None) -> tuple[ApplicationService, FakeGateway]:
        selected = gateway or FakeGateway()
        project = ProjectStore(root / "active_project.json")
        service = ApplicationService(
            selected, project_store=project,
            artifact_store=InputArtifactStore(root / "inputs"),
            legacy_draft_store=GeneratedDraftStore(root / "legacy.json"),
        )
        return service, selected

    @staticmethod
    def prepared(service: ApplicationService, prompt: str, content: bytes = b""):
        from twinpulse_provider import ImageInput
        images = (ImageInput("warehouse.png", "image/png", content),) if content else ()
        return service.prepare_input(
            prompt=prompt, images=images, measurement_constraints=(),
            generation_settings={"base_url": "https://example.test/v1/", "model_id": "fake",
                                 "reasoning_effort": "low", "image_detail": "auto",
                                 "request_schema": "1.0"},
        )

    async def test_generation_persistence_restore_and_build_candidate(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            root = Path(directory)
            service, _gateway = self.make_service(root)
            prepared = self.prepared(service, "Create an aisle", b"image-a")
            service.select_input(prepared)
            outcome = await service.generate()
            self.assertTrue(outcome.persisted)
            self.assertEqual(outcome.event.code, "draft_ready")
            self.assertTrue(service.snapshot(prepared.revision).build_allowed)
            self.assertEqual(service.build_candidate(prepared.revision).record, outcome.record)
            self.assertTrue((root / "inputs" / prepared.revision.digest / "revision.json").is_file())

            restored, _ = self.make_service(root)
            self.assertIsNotNone(restored.record)
            # Restoring metadata never silently activates old UI input bytes.
            self.assertFalse(restored.snapshot().build_allowed)
            self.assertTrue(restored.snapshot(prepared.revision).build_allowed)
            service.diagnostics.flush();restored.diagnostics.flush()  # both writers drain before TemporaryDirectory removes the tree (WinError 32/145 on Windows)

    async def test_superseded_late_response_never_promotes(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            gateway = FakeGateway()
            gateway.wait = asyncio.Event()
            service, _ = self.make_service(Path(directory), gateway)
            a = self.prepared(service, "A")
            service.select_input(a)
            task = asyncio.create_task(service.generate())
            await asyncio.sleep(0)
            b = self.prepared(service, "B")
            service.select_input(b)
            gateway.wait.set()
            with self.assertRaisesRegex(ValueError, "superseded"):
                await task
            self.assertIsNone(service.record)
            self.assertEqual(service.last_event.code, "superseded_result")
            self.assertFalse(service.snapshot(b.revision).build_allowed)
            service.diagnostics.flush()  # drain the diagnostics writer before TemporaryDirectory removes the tree (WinError 145 on Windows)

    async def test_failure_and_cancel_preserve_prior_draft_but_block_new_input(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            service, gateway = self.make_service(Path(directory))
            a = self.prepared(service, "A")
            service.select_input(a)
            first = await service.generate()
            b = self.prepared(service, "B")
            service.select_input(b)
            gateway.error = RuntimeError("provider unavailable")
            with self.assertRaises(RuntimeError):
                await service.generate()
            self.assertEqual(service.record, first.record)
            with self.assertRaises(RuntimeError):
                service.build_candidate(b.revision)
            self.assertEqual(service.build_candidate(a.revision).record, first.record)
            service.cancel_generation()
            self.assertEqual(service.last_event.code, "cancelled")
            self.assertEqual(service.record, first.record)
            service.diagnostics.flush()  # drain the diagnostics writer before TemporaryDirectory removes the tree (WinError 32/145 on Windows)

    async def test_fake_port_uses_validated_revision_and_rejects_bad_receipt(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            service, _ = self.make_service(Path(directory))
            prepared = self.prepared(service, "Build")
            service.select_input(prepared)
            await service.generate()
            port = FakeSimulationPort()
            receipt = service.dispatch(
                port, "build_scene", engine_session_id="engine-1", stage_epoch="stage-1",
                control_lease_id="lease-1", current_input=prepared.revision,
            )
            self.assertEqual(receipt.status, "succeeded")
            self.assertEqual(receipt.applied_revision, prepared.revision.digest)
            self.assertIn("draft", port.commands[0].payload)
            self.assertIn("bundle", port.commands[0].payload)
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                service.dispatch(
                    FakeSimulationPort(wrong_revision=True), "build_scene",
                    engine_session_id="engine-1", stage_epoch="stage-1",
                    control_lease_id="lease-1", current_input=prepared.revision,
                )
            service.diagnostics.flush()  # drain the diagnostics writer before TemporaryDirectory removes the tree (WinError 145 on Windows)

    async def test_settings_migrate_once_without_secret_or_bidirectional_sync(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            path = Path(directory) / "provider.json"
            store = JsonProviderSettingsStore(path)
            calls = 0

            def legacy() -> ProviderSettings:
                nonlocal calls
                calls += 1
                return ProviderSettings("https://legacy.example/v1/", "legacy-model", "medium")

            first, migrated = migrate_legacy_settings_once(store, legacy)
            self.assertTrue(migrated)
            self.assertEqual(first.model_id, "legacy-model")
            second, migrated = migrate_legacy_settings_once(store, lambda: ProviderSettings(model_id="other"))
            self.assertFalse(migrated)
            self.assertEqual(second, first)
            self.assertEqual(calls, 1)
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("api_key", text)
            self.assertNotIn("secret", text)

    async def test_corrupt_project_is_rejected_without_overwrite(self) -> None:
        with TemporaryDirectory(prefix="case-", dir=TEST_TMP) as directory:
            path = Path(directory) / "active_project.json"
            original = b'{"schema_version":"9.0"}'
            path.write_bytes(original)
            with self.assertRaises(ValueError):
                ApplicationService(FakeGateway(), project_store=ProjectStore(path))
            self.assertEqual(path.read_bytes(), original)

    async def test_contract_roundtrip_and_unknown_fields_rejected(self) -> None:
        command = CommandEnvelope(
            command_id="c1", command_type="get_state", project_id="p1",
            engine_session_id="e1", stage_epoch="s1", control_lease_id="l1",
            expected_applied_revision=None,
        )
        self.assertEqual(CommandEnvelope.from_dict(command.to_dict()), command)
        extra = command.to_dict()
        extra["unknown"] = True
        with self.assertRaises(ValueError):
            CommandEnvelope.from_dict(extra)
        snapshot = FakeSimulationPort().snapshot()
        self.assertEqual(SimulationSnapshot.from_dict(snapshot.to_dict()), snapshot)


class R3PureImportTests(unittest.TestCase):
    def test_package_metadata_declares_pure_layer_dependencies(self) -> None:
        provider = tomllib.loads((ROOT / "packages" / "twinpulse_provider" / "pyproject.toml").read_text(encoding="utf-8"))
        app = tomllib.loads((ROOT / "packages" / "twinpulse_app" / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(provider["project"]["name"], "twinpulse-provider")
        self.assertEqual(provider["project"]["dependencies"], ["twinpulse-core==0.1.0"])
        self.assertEqual(app["project"]["name"], "twinpulse-app")
        self.assertEqual(
            app["project"]["dependencies"],
            ["twinpulse-core==0.1.0", "twinpulse-provider==0.1.0", "Pillow>=12.2,<13"],
        )

    def test_general_python_imports_have_no_kit_modules(self) -> None:
        path_entries = [str(ROOT / "packages" / name / "src") for name in (
            "twinpulse_core", "twinpulse_provider", "twinpulse_app",
        )]
        if os.environ.get("PYTHONPATH"):
            path_entries.append(os.environ["PYTHONPATH"])
        paths = os.pathsep.join(path_entries)
        code = (
            "import json,sys,twinpulse_core,twinpulse_provider,twinpulse_app;"
            "print(json.dumps(sorted(x for x in ('omni','pxr','carb') if x in sys.modules)))"
        )
        env = {**os.environ, "PYTHONPATH": paths}
        result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, env=env)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main()
