# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""S0 audit regressions that intentionally expose the pre-fix product defects.

These tests define the desired boundary behavior.  They are expected to be RED
at the S0 checkpoint and must turn GREEN only in their assigned repair steps.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
import unittest
import uuid
import zlib


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import (  # noqa: E402
    ApplicationService,
    BrokerError,
    CommandBroker,
    ProcessManagerError,
    ProductWorkflow,
    ProjectStore,
    TwinPulseProcessManager,
)
from twinpulse_core import InputArtifactStore, SceneToolPlan, SceneToolRegistry, demo_warehouse_tool_plan  # noqa: E402
from twinpulse_provider import GenerationResult  # noqa: E402


class _InputDependentGateway:
    def cancel_active(self) -> None:
        pass

    async def generate(self, request):
        suffix = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()[:10]
        payload = demo_warehouse_tool_plan().to_dict()
        payload["scene_id"] = f"audit_{suffix}"
        payload["summary"] = f"Audit input {suffix}"
        plan = SceneToolPlan.from_dict(payload)
        return GenerationResult(
            request.request_id, "audit-fake", "audit-model", len(request.images),
            plan, SceneToolRegistry().execute(plan), len(request.measurement_constraints), 0,
        )


def png_without_pixel_data(width: int = 1, height: int = 1) -> bytes:
    """Return a checksum-valid PNG header and IEND with no IDAT pixels."""

    signature = b"\x89PNG\r\n\x1a\n"
    data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", len(data)) + b"IHDR" + data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + data) & 0xFFFFFFFF)
    return signature + ihdr + b"\x00\x00\x00\x00IEND\xaeB`\x82"


class S0AuditRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflows: list[ProductWorkflow] = []
        configured = os.environ.get("TWINPULSE_TEST_TMP")
        if configured:
            self.root = Path(configured) / f"s0-{uuid.uuid4().hex}"
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

    @staticmethod
    def _select_text(workflow: ProductWorkflow, prompt: str) -> dict[str, object]:
        return workflow.select_input({
            "name": None,
            "input_kind": "auto",
            "prompt": prompt,
            "media_type": None,
            "content_base64": None,
            "sidecar_name": None,
            "sidecar_content_base64": None,
        })

    @staticmethod
    def _generate(workflow: ProductWorkflow) -> dict[str, object]:
        workflow.start_generation()
        deadline = time.monotonic() + 1.0
        snapshot = workflow.snapshot()
        while snapshot["phase"] == "generating" and time.monotonic() < deadline:
            time.sleep(0.005)
            snapshot = workflow.snapshot()
        if snapshot["phase"] != "draft_ready":
            raise AssertionError(f"fixture generation did not complete: {snapshot['phase']}")
        return snapshot

    def _workflow(self) -> ProductWorkflow:
        workflow = ProductWorkflow(
            ApplicationService(
                _InputDependentGateway(), project_store=ProjectStore(self.root / "active_project.json"),
                artifact_store=InputArtifactStore(self.root / "inputs"),
            ), CommandBroker(), mode="explicit_fixture",
            generation_settings_getter=lambda: {
                "base_url": "https://fixture.invalid/v1/", "model_id": "audit-model",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
        )
        self.workflows.append(workflow)
        return workflow

    def test_a01_distinct_inputs_do_not_collapse_to_the_same_draft(self) -> None:
        workflow = self._workflow()

        first_input = self._select_text(workflow, "two narrow rack rows and one loading lane")
        first_draft = self._generate(workflow)["draft"]
        second_input = self._select_text(workflow, "one open hall with four isolated work cells")
        second_draft = self._generate(workflow)["draft"]

        self.assertNotEqual(first_input["input"]["revision"], second_input["input"]["revision"])
        self.assertNotEqual(
            first_draft,
            second_draft,
            "A-01: distinct user inputs currently collapse to the fixed fixture draft",
        )

    def test_a02_non_owner_stop_does_not_signal_the_owner_runtime(self) -> None:
        state = self.root / "state"
        state.mkdir()
        lock = state / "launcher.lock"
        lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        manager = TwinPulseProcessManager(
            repo_root=ROOT,
            state_dir=state,
            python_executable=Path(sys.executable),
            isaac_python=ROOT / "not-used-python.bat",
        )

        with self.assertRaisesRegex(ProcessManagerError, "no process was terminated"):
            manager._acquire_lock()
        self.assertFalse(manager._lock_owned)
        self.assertEqual(manager._owned, {})

        manager.stop()

        self.assertTrue(lock.is_file(), "the existing owner's lock must remain untouched")
        self.assertFalse(
            manager.engine_stop_file.exists(),
            "A-02: a rejected non-owner currently creates the shared engine stop signal",
        )

    def test_a04_png_without_decodable_pixels_is_rejected(self) -> None:
        workflow = self._workflow()
        content = png_without_pixel_data()

        with self.assertRaisesRegex(BrokerError, "image content|decod"):
            workflow.select_input({
                "name": "header-only.png",
                "input_kind": "photo",
                "prompt": "inspect this image",
                "media_type": "image/png",
                "content_base64": base64.b64encode(content).decode("ascii"),
                "sidecar_name": None,
                "sidecar_content_base64": None,
            })


if __name__ == "__main__":
    unittest.main()
