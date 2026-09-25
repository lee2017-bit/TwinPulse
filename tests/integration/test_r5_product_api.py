"""R5 Product API, upload validation, draft acknowledgement, and static serving."""

from __future__ import annotations

import base64
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen
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
    CommandBroker,
    JsonProviderSettingsStore,
    LocalApiServer,
    ProductWorkflow,
    ProjectStore,
)
from twinpulse_core import InputArtifactStore  # noqa: E402
from twinpulse_provider import GenerationService, MockProvider, ProviderCapabilities, ProviderConfig  # noqa: E402


def png(width: int = 2, height: int = 3) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", len(data)) + b"IHDR" + data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\x20\x40\x60" * width for _ in range(height))
    compressed = zlib.compress(rows)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed
    idat += struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    return signature + ihdr + idat + b"\x00\x00\x00\x00IEND\xaeB`\x82"


class R5ProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = os.environ.get("TWINPULSE_TEST_TMP")
        if configured:
            static = Path(configured) / f"r5-{uuid.uuid4().hex}"
            static.mkdir(parents=True)
            self.temporary = None
        else:
            self.temporary = tempfile.TemporaryDirectory()
            static = Path(self.temporary.name)
        self.static = static
        (static / "index.html").write_text("<main>TwinPulse</main>", encoding="utf-8")
        (static / "app.js").write_text("console.log('safe')", encoding="utf-8")
        self.broker = CommandBroker()
        def gateway() -> GenerationService:
            return GenerationService(
                MockProvider(delay_s=0.05),
                ProviderConfig(
                    base_url="https://fixture.invalid/v1/", endpoint_path="responses",
                    model_id="twinpulse-explicit-fixture", api_key_env="TWINPULSE_UNUSED_FIXTURE_KEY",
                    capabilities=ProviderCapabilities(True, True, 1, ("image/png", "image/jpeg", "image/webp")),
                    timeout_s=2.0, max_attempts=1,
                ),
            )
        self.workflow = ProductWorkflow(
            ApplicationService(
                gateway(), project_store=ProjectStore(static / "active_project.json"),
                artifact_store=InputArtifactStore(static / "inputs"),
            ), self.broker, mode="explicit_fixture",
            generation_settings_getter=lambda: {
                "base_url": "https://fixture.invalid/v1/", "model_id": "twinpulse-explicit-fixture",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            },
            provider_state_getter=lambda: {"configured": True, "label": "Explicit deterministic fixture"},
            gateway_factory=gateway,
        )
        self.product_secret = "p" * 43
        self.credentials = _MemoryCredentialStore()
        self.settings_store = JsonProviderSettingsStore(static / "provider_settings.json")
        self.supervisor_status = static / "supervisor.json"
        self.supervisor_status.write_text(json.dumps({
            "schema_version": "1.0", "status": "error", "phase": "engine_exited",
            "message": "engine exited with code 7", "secret": "must-not-leak",
            "backend": {"owned": True, "state": "running", "pid": 123, "path": "private"},
            "engine": {"owned": True, "state": "exited", "exit_code": 7},
            "browser": {"launched": True, "url": "private"},
        }), encoding="utf-8")
        self.server = LocalApiServer(
            self.broker,
            product_bootstrap_secret=self.product_secret,
            engine_bootstrap_secret="e" * 43,
            product_workflow=self.workflow,
            static_root=static,
            supervisor_status_file=self.supervisor_status,
            provider_settings_store=self.settings_store,
            credential_store=self.credentials,
        )
        self.server.start()
        status, result, headers = self.request(
            "/v1/bootstrap", {"role": "product", "secret": self.product_secret},
        )
        self.assertEqual(status, 200)
        self.cookie = headers.get("Set-Cookie").split(";", 1)[0]
        self.csrf = result["csrf_token"]

    def tearDown(self) -> None:
        self.server.stop()
        if self.temporary is not None:
            self.temporary.cleanup()
        else:
            shutil.rmtree(self.static, ignore_errors=True)

    def request(
        self, path: str, body: object | None = None, *, headers: dict[str, str] | None = None,
    ) -> tuple[int, object, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        selected = dict(headers or {})
        if data is not None:
            selected["Content-Type"] = "application/json"
        request = Request(self.server.base_url + path, data=data, headers=selected)
        try:
            with urlopen(request, timeout=3.0) as response:
                content = response.read()
                if response.headers.get_content_type() == "application/json":
                    return response.status, json.loads(content), response.headers
                return response.status, content, response.headers
        except HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    @property
    def product_headers(self) -> dict[str, str]:
        return {"Cookie": self.cookie, "X-TwinPulse-CSRF": self.csrf}

    def select_text(self, prompt: str = "Create a compact warehouse") -> dict[str, object]:
        status, result, _ = self.request(
            "/v1/product/input",
            {
                "name": None, "input_kind": "auto", "prompt": prompt,
                "media_type": None, "content_base64": None,
                "sidecar_name": None, "sidecar_content_base64": None,
            },
            headers=self.product_headers,
        )
        self.assertEqual(status, 200)
        return result

    def test_deterministic_generation_requires_revision_acknowledgement_before_build(self) -> None:
        selected = self.select_text()
        self.assertEqual(selected["phase"], "input_ready")
        status, generated, _ = self.request(
            "/v1/product/generation", {}, headers=self.product_headers,
        )
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 2.0
        while generated["phase"] == "generating" and time.monotonic() < deadline:
            time.sleep(0.02)
            generated = self.workflow.snapshot()
        self.assertEqual(generated["mode"], "explicit_fixture")
        self.assertFalse(generated["provider"]["connected"])
        revision = generated["draft"]["revision"]
        status, rejected, _ = self.request(
            "/v1/product/commands",
            {
                "client_request_id": "before-ack", "command_type": "build_scene",
                "artifact_id": generated["draft"]["artifact_id"],
                "expected_applied_revision": revision,
            },
            headers=self.product_headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(rejected["error"]["code"], "draft_acknowledgement_required")
        status, acknowledged, _ = self.request(
            "/v1/product/draft/acknowledge", {"revision": revision},
            headers=self.product_headers,
        )
        self.assertEqual(status, 200)
        self.assertTrue(acknowledged["build_allowed"])

    def test_new_input_invalidates_previous_acknowledgement(self) -> None:
        self.select_text("first")
        status, generated, _ = self.request("/v1/product/generation", {}, headers=self.product_headers)
        self.assertEqual(status, 202)
        deadline = time.monotonic() + 2.0
        while generated["phase"] == "generating" and time.monotonic() < deadline:
            time.sleep(0.02)
            generated = self.workflow.snapshot()
        revision = generated["draft"]["revision"]
        self.request(
            "/v1/product/draft/acknowledge", {"revision": revision}, headers=self.product_headers,
        )
        changed = self.select_text("second")
        self.assertFalse(changed["build_allowed"])
        self.assertIsNone(changed["draft"])

    def test_generation_job_can_be_cancelled_without_late_draft(self) -> None:
        self.select_text("cancel this fixture job")
        status, generating, _ = self.request(
            "/v1/product/generation", {}, headers=self.product_headers,
        )
        self.assertEqual(status, 202)
        self.assertEqual(generating["phase"], "generating")
        status, cancelled, _ = self.request(
            "/v1/product/generation/cancel", {}, headers=self.product_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["phase"], "cancelled")
        time.sleep(0.2)
        self.assertEqual(self.workflow.snapshot()["phase"], "cancelled")

    def test_optional_measurement_sidecar_is_strict_and_bound_to_image(self) -> None:
        sidecar = {
            "schema_version": "1.0",
            "source_image": "plan.png",
            "measurement_constraints": [{
                "constraint_id": "floor_width", "tool": "create_floor",
                "argument_path": "size_m.0", "expected": 8.0, "tolerance": 0.01,
            }],
        }
        valid = {
            "name": "plan.png", "input_kind": "drawing", "prompt": "Use measured width",
            "media_type": "image/png", "content_base64": base64.b64encode(png()).decode("ascii"),
            "sidecar_name": "plan.measurements.json",
            "sidecar_content_base64": base64.b64encode(
                json.dumps(sidecar).encode("utf-8"),
            ).decode("ascii"),
        }
        status, result, _ = self.request("/v1/product/input", valid, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(result["input"]["measurement_count"], 1)
        mismatch = dict(valid)
        mismatch["sidecar_content_base64"] = base64.b64encode(
            json.dumps({**sidecar, "source_image": "other.png"}).encode("utf-8"),
        ).decode("ascii")
        status, result, _ = self.request("/v1/product/input", mismatch, headers=self.product_headers)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "sidecar_invalid")

    def test_upload_sniffs_content_dimensions_and_rejects_path_or_type_spoofing(self) -> None:
        encoded = base64.b64encode(png()).decode("ascii")
        valid = {
            "name": "plan.png", "input_kind": "drawing", "prompt": "Use the aisle",
            "media_type": "image/png", "content_base64": encoded,
            "sidecar_name": None, "sidecar_content_base64": None,
        }
        status, result, _ = self.request("/v1/product/input", valid, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual((result["input"]["width"], result["input"]["height"]), (2, 3))
        invalid = dict(valid, name="../plan.png")
        status, result, _ = self.request("/v1/product/input", invalid, headers=self.product_headers)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "image_name_invalid")
        invalid = dict(valid, media_type="image/jpeg")
        status, result, _ = self.request("/v1/product/input", invalid, headers=self.product_headers)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "image_type_mismatch")
        invalid = dict(valid, content_base64=base64.b64encode(b"not-an-image").decode("ascii"))
        status, result, _ = self.request("/v1/product/input", invalid, headers=self.product_headers)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "image_content_invalid")

    def test_static_ui_is_same_origin_hardened_and_path_traversal_is_rejected(self) -> None:
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"TwinPulse", body)
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy"))
        status, result, _ = self.request("/../README.md")
        self.assertEqual(status, 404)
        self.assertEqual(result["error"]["code"], "asset_not_found")

    def test_workflow_state_requires_product_session(self) -> None:
        status, result, _ = self.request("/v1/product/workflow")
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "session_rejected")

    def test_runtime_status_is_authenticated_and_strictly_sanitized(self) -> None:
        status, result, _ = self.request("/v1/product/runtime", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200)
        self.assertEqual(result["phase"], "engine_exited")
        self.assertEqual(result["engine"]["exit_code"], 7)
        serialized = json.dumps(result)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("private", serialized)
        status, result, _ = self.request("/v1/product/runtime")
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "session_rejected")

    def test_provider_settings_persist_nonsecret_values_without_echoing_key(self) -> None:
        status, initial, _ = self.request(
            "/v1/product/provider-settings", headers={"Cookie": self.cookie},
        )
        self.assertEqual(status, 200)
        self.assertFalse(initial["credential_configured"])
        secret = "credential-test-never-serialize"
        status, saved, _ = self.request(
            "/v1/product/provider-settings",
            {
                "base_url": "https://api.openai.com/v1/", "model_id": "gpt-test",
                "reasoning_effort": "medium", "api_key": secret,
            },
            headers=self.product_headers,
        )
        self.assertEqual(status, 200)
        self.assertTrue(saved["credential_configured"])
        self.assertEqual(saved["model_id"], "gpt-test")
        self.assertNotIn(secret, json.dumps(saved))
        self.assertNotIn(secret, self.settings_store.path.read_text(encoding="utf-8"))
        self.assertEqual(self.credentials.secret, secret)

        status, kept, _ = self.request(
            "/v1/product/provider-settings",
            {
                "base_url": "https://api.openai.com/v1/", "model_id": "gpt-test-2",
                "reasoning_effort": "low", "api_key": "",
            },
            headers=self.product_headers,
        )
        self.assertEqual(status, 200)
        self.assertTrue(kept["credential_configured"])
        self.assertEqual(self.credentials.secret, secret)


class _MemoryCredentialStore:
    def __init__(self) -> None:
        self.secret: str | None = None

    @property
    def target_name(self) -> str:
        return "TwinPulse/OpenAIResponsesAPI"

    def save(self, secret: str) -> None:
        self.secret = secret

    def load(self) -> str | None:
        return self.secret

    def is_configured(self) -> bool:
        return self.secret is not None

    def delete(self) -> None:
        self.secret = None


if __name__ == "__main__":
    unittest.main()
