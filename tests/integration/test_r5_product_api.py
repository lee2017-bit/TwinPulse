# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""R5 Product API, upload validation, draft acknowledgement, and static serving."""

from __future__ import annotations

import base64
import asyncio
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
from unittest.mock import Mock, patch
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
from twinpulse_app.project_catalog import ProjectCatalog  # noqa: E402


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
    def test_catalog_optional_probe_failure_preserves_success_and_typed_error(self):
        from twinpulse_app.command_broker import BrokerError
        for hook in ('begin','finish'):
            with self.subTest(hook=hook),patch.object(self.server._request_latency,hook,side_effect=OSError('optional probe')):
                self.assertEqual(self.request('/v1/product/projects',headers=self.product_headers)[0],200)
                with patch.object(self.server.project_catalog,'snapshot',side_effect=BrokerError('original_catalog_failure','original',status=409)):
                    status,value,_=self.request('/v1/product/projects',headers=self.product_headers)
                self.assertEqual(status,409)
                self.assertEqual(value['error']['code'],'original_catalog_failure')
                # Reading the HTTP body precedes the server handler's finally
                # block. Observe that original cleanup, not client receipt as
                # if it were a server-thread completion barrier.
                deadline=time.monotonic()+1.
                while time.monotonic()<deadline:
                    with self.server._request_latency.lock:
                        empty=not self.server._request_latency.requests
                    if empty:break
                    time.sleep(.005)
                self.assertEqual(self.server._request_latency.requests,{})

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
        self.launcher_retry_file = static / "launcher-retry.request"
        self.launcher_project_switch_file = static / "launcher-project-switch.request"
        self.launcher_cancel_file = static / "launcher-startup-cancel.request"
        self.engine_result_file = static / "engine-result.json"
        self.supervisor_status.write_text(json.dumps({
            "schema_version": "1.0", "status": "ready", "phase": "engine_exited",
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
            launcher_retry_file=self.launcher_retry_file,
            launcher_project_switch_file=self.launcher_project_switch_file,
            launcher_cancel_file=self.launcher_cancel_file,
            engine_result_file=self.engine_result_file,
            launcher_retry_remaining=3,
            project_catalog=ProjectCatalog(static, "default"),
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

    def test_empty_input_uses_site_neutral_guidance_without_changing_error_code(self) -> None:
        status, rejected, _ = self.request(
            "/v1/product/input",
            {
                "name": None, "input_kind": "auto", "prompt": "",
                "media_type": None, "content_base64": None,
                "sidecar_name": None, "sidecar_content_base64": None,
            },
            headers=self.product_headers,
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["error"]["code"], "input_empty")
        self.assertEqual(rejected["error"]["message"], "Attach a site image or describe the scene")

    def test_robot_report_review_requires_auth_and_csrf_and_never_grants_lease(self):
        from tests.integration.test_robot_reports import report
        path = '/v1/product/robot/report'
        status, _, _ = self.request(path)
        self.assertEqual(status, 401)
        status, _, _ = self.request(path, {'report': report()}, headers={'Cookie': self.cookie})
        self.assertEqual(status, 403)
        status, result, _ = self.request(path, {'report': report()}, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertFalse(result['motion_authorized'])
        self.assertFalse(result['demo_ready'])
        status, snapshot, _ = self.request(path, headers=self.product_headers)
        self.assertEqual(snapshot['record']['report_sha256'], result['record']['report_sha256'])
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertFalse(product['lease_owned'])
        self.assertEqual(product['operations'], [])

    def test_robot_report_rejects_path_and_motion_fields(self):
        status, _, _ = self.request('/v1/product/robot/report', {'path': 'C:/private'}, headers=self.product_headers)
        self.assertEqual(status, 400)
        status, _, _ = self.request('/v1/product/robot/report', {'report': {'motion_authorized': True}}, headers=self.product_headers)
        self.assertEqual(status, 400)

    def test_native_scan_review_auth_frames_export_and_project_isolation(self):
        from tests.integration.test_native_scan_review import fixture
        text = json.dumps(fixture())
        path = '/v1/product/native-scan'
        before = (self.static / 'active_project.json').read_bytes()
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request(path + '/reference')[0], 401)
        self.assertEqual(self.request(path + '/export')[0], 401)
        self.assertEqual(self.request(path + '/import', {'bundle_text': text}, headers={'Cookie': self.cookie})[0], 403)
        status, state, _ = self.request(path + '/import', {'bundle_text': text}, headers=self.product_headers)
        self.assertEqual(status, 200)
        status, reference, _ = self.request(path + '/reference', headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(reference['workspace_revision'], state['workspace_revision'])
        self.assertEqual(reference['reference']['artifact_sha256'], state['bundle']['digest'])
        self.assertEqual(reference['reference']['source_sha256'], fixture()['source']['raw_sha256'])
        self.assertFalse(reference['reference']['alignment_verified'])
        self.assertFalse(reference['reference']['motion_authorized'])
        body = {'workspace_revision': state['workspace_revision'], 'frame_index': 0}
        self.assertEqual(self.request(path + '/frame', body, headers={'Cookie': self.cookie})[0], 403)
        status, frame, _ = self.request(path + '/frame', body, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(len(frame['frame']['points']), 2)
        self.assertEqual(self.request(path + '/frame', dict(body, workspace_revision='old'), headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/frame', dict(body, frame_index=True), headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/frame', dict(body, frame_index=None), headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/frame', dict(body, workspace_revision=None), headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/import', {'path': 'C:/private'}, headers=self.product_headers)[0], 400)
        status, exported, _ = self.request(path + '/export', headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(exported, fixture())
        self.assertEqual(self.request(path + '/3d-export', body)[0], 401)
        self.assertEqual(self.request(path + '/3d-export', body, headers={'Cookie': self.cookie})[0], 403)
        status, exported_3d, _ = self.request(path + '/3d-export', body, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(exported_3d['point_count'], 2)
        self.assertEqual(exported_3d['bundle_digest'], state['bundle']['digest'])
        for extra in ({'world_tf': {}}, {'output_path': 'C:/private'}, {'workspace_revision': 'old'}, {'frame_index': True}):
            self.assertEqual(self.request(path + '/3d-export', dict(body, **extra), headers=self.product_headers)[0], 400)
        self.assertEqual(before, (self.static / 'active_project.json').read_bytes())
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertEqual(product['operations'], [])
        self.assertFalse(product['lease_owned'])
        self.assertFalse(frame['motion_authorized'])
        self.assertFalse(frame['source_bytes_verified'])
        self.assertIsNone(self.workflow._application.site_draft)

    def test_native_registration_http_synthetic_only_no_motion_or_project_mutation(self):
        from tests.integration.test_native_scan_review import registration_fixture
        bundle, reference = registration_fixture(-1)
        path = '/v1/product/native-scan'
        before = (self.static / 'active_project.json').read_bytes()
        status, state, _ = self.request(path + '/import', {'bundle_text': json.dumps(bundle.to_dict())}, headers=self.product_headers)
        self.assertEqual(status, 200)
        body = dict(workspace_revision=state['workspace_revision'], frame_index=0, reference_text=json.dumps(reference))
        self.assertEqual(self.request(path + '/registration', body)[0], 401)
        self.assertEqual(self.request(path + '/registration', body, headers={'Cookie': self.cookie})[0], 403)
        status, fitted, _ = self.request(path + '/registration', body, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(fitted['registration']['candidate_native_y_sign'], -1)
        self.assertFalse(fitted['registration']['world_alignment_verified'])
        self.assertFalse(fitted['motion_authorized'])
        self.assertEqual(self.request(path + '/registration', body, headers=self.product_headers)[0], 400)
        self.assertEqual(before, (self.static / 'active_project.json').read_bytes())
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertEqual(product['operations'], [])
        self.assertFalse(product['lease_owned'])

    def test_scan_review_auth_review_binding_and_no_active_project_effect(self):
        from tests.integration.test_scan_review import bundle
        text, pairs = bundle()
        path = '/v1/product/scan-review'
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request(path + '/import', {'bundle_text': text}, headers={'Cookie': self.cookie})[0], 403)
        status, imported, _ = self.request(path + '/import', {'bundle_text': text}, headers=self.product_headers)
        self.assertEqual(status, 200)
        status, proposed, _ = self.request(path + '/propose', {'workspace_revision': imported['workspace_revision'],
            'object_id': 'observed_box', 'pairs': pairs}, headers=self.product_headers)
        self.assertEqual(status, 200)
        status, applied, _ = self.request(path + '/apply', {'workspace_revision': proposed['workspace_revision'],
            'proposal_revision': proposed['proposal']['revision']}, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertFalse(applied['active_project_changed'])
        self.assertFalse(applied['map_present'])
        self.assertFalse(applied['motion_authorized'])
        self.assertEqual(self.request(path + '/apply', {'workspace_revision': proposed['workspace_revision'],
            'proposal_revision': proposed['proposal']['revision']}, headers=self.product_headers)[0], 400)
        status, exported, _ = self.request(path + '/export', headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertFalse(exported['execution_authority'])
        status, undone, _ = self.request(path + '/undo', {'workspace_revision': applied['workspace_revision'],
            'edit_revision': applied['edit_revision']}, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(undone['scene']['objects'], imported['scene']['objects'])
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertEqual(product['operations'], [])
        self.assertFalse(product['lease_owned'])
        self.assertIsNone(self.workflow._application.site_draft)

    def test_scan_review_rejects_commands_and_forged_receipts(self):
        path = '/v1/product/scan-review'
        self.assertEqual(self.request(path + '/import', {'path': 'C:/private'}, headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/undo', {'workspace_revision': 'x', 'edit_revision': 'x',
            'receipt': {}}, headers=self.product_headers)[0], 400)
        self.assertEqual(self.request(path + '/execute', {}, headers=self.product_headers)[0], 400)

    def test_scan_archive_http_auth_stale_restore_no_active_project_effect(self):
        from tests.integration.test_scan_archive import archive_fixture
        _, _, archive = archive_fixture()
        path = '/v1/product/scan-review'
        _, before, _ = self.request(path, headers=self.product_headers)
        body = {'workspace_revision': before['workspace_revision'], 'archive_text': json.dumps(archive)}
        self.assertEqual(self.request(path + '/archive-import', body)[0], 401)
        self.assertEqual(self.request(path + '/archive-import', body, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(self.request(path + '/archive-import', dict(body, path='local'), headers=self.product_headers)[0], 400)
        status, restored, _ = self.request(path + '/archive-import', body, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(restored['archive_action_count'], 2)
        self.assertFalse(restored['motion_authorized'])
        self.assertFalse(restored['active_project_changed'])
        self.assertEqual(self.request(path + '/archive-import', body, headers=self.product_headers)[0], 400)
        export_body = {'workspace_revision': restored['workspace_revision']}
        self.assertEqual(self.request(path + '/archive-export', export_body, headers={'Cookie': self.cookie})[0], 403)
        status, exported, _ = self.request(path + '/archive-export', export_body, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(exported['archive_text']), archive)
        self.assertEqual(hashlib.sha256(exported['archive_text'].encode('utf-8')).hexdigest(), exported['sha256'])
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertEqual(product['operations'], [])
        self.assertFalse(product['lease_owned'])
        self.assertIsNone(self.workflow._application.site_draft)

    def test_offline_route_comparison_http_contract(self):
        from tests.integration.test_scan_review import route_bundle
        text, before, after, _ = route_bundle()
        path = '/v1/product/scan-review'
        status, state, _ = self.request(path + '/import', {'bundle_text': text}, headers=self.product_headers)
        self.assertEqual(status, 200)
        payload = dict(workspace_revision=state['workspace_revision'], conditions_revision=state['route_conditions']['revision'],
                       baseline=before, candidate=after)
        self.assertEqual(self.request(path + '/compare', payload)[0], 401)
        self.assertEqual(self.request(path + '/compare', payload, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(self.request(path + '/compare', dict(payload, command='run'), headers=self.product_headers)[0], 400)
        status, compared, _ = self.request(path + '/compare', payload, headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertTrue(compared['route_comparison']['comparable'])
        self.assertFalse(compared['route_comparison']['execution_authorized'])
        self.assertEqual(self.request(path + '/compare', payload, headers=self.product_headers)[0], 400)
        _, product, _ = self.request('/v1/product/state', headers=self.product_headers)
        self.assertEqual(product['operations'], [])
        self.assertFalse(product['lease_owned'])
        self.assertIsNone(self.workflow._application.site_draft)

    def test_map_overlay_http_exact_review_and_no_execute(self):
        from tests.integration.test_scan_review import route_bundle
        text, _, _, pairs = route_bundle()
        path = '/v1/product/scan-review'
        def post(action, body):
            return self.request(path + '/' + action, body, headers=self.product_headers)
        _, state, _ = post('import', {'bundle_text': text})
        _, state, _ = post('propose', {'workspace_revision': state['workspace_revision'], 'object_id': 'obstacle', 'pairs': pairs})
        _, state, _ = post('apply', {'workspace_revision': state['workspace_revision'], 'proposal_revision': state['proposal']['revision']})
        status, state, _ = post('map-propose', {'workspace_revision': state['workspace_revision']})
        self.assertEqual(status, 200)
        self.assertEqual(post('map-apply', {'workspace_revision': state['workspace_revision'], 'proposal_revision': 'wrong'})[0], 400)
        body = {'workspace_revision': state['workspace_revision'], 'proposal_revision': state['map_proposal']['revision']}
        self.assertEqual(self.request(path + '/map-apply', body, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(post('map-apply', dict(body, approve_motion=True))[0], 400)
        status, state, _ = post('map-apply', body)
        self.assertEqual(status, 200)
        self.assertTrue(state['map_present'])
        self.assertFalse(state['motion_authorized'])
        self.assertFalse(state['map_overlay']['execution_authorized'])
        self.assertIsNone(self.workflow._application.site_draft)

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

    def test_product_mutations_are_blocked_until_launcher_ready(self) -> None:
        for state, expected_code in (("starting", "runtime_not_ready"), ("error", "runtime_start_failed")):
            with self.subTest(state=state):
                current = json.loads(self.supervisor_status.read_text(encoding="utf-8"))
                current["status"] = state
                self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
                status, result, _ = self.request("/v1/product/runtime", headers={"Cookie": self.cookie})
                self.assertEqual(status, 200)
                self.assertEqual(result["status"], state)
                status, result, _ = self.request(
                    "/v1/product/input", {"prompt": "Create a room"}, headers=self.product_headers,
                )
                self.assertEqual(status, 409)
                self.assertEqual(result["error"]["code"], expected_code)

    def test_only_data_only_robot_settings_can_save_before_isaac_is_ready(self):
        from twinpulse_app.workspace_devices import WorkspaceDevices
        from twinpulse_app.robot_registry import RobotEndpoint
        from twinpulse_app.robot_registry_service import RobotRegistryService
        from twinpulse_core.robot_battery import battery_display_config
        devices=WorkspaceDevices();service=RobotRegistryService(devices,self.static/'battery-settings')
        devices.registry_service=service;self.server.workspace_devices=devices
        row=service.registry.register(label='Offline settings',adapter_id='turtlebot3_burger_v1',adapter_version='burger-reviewed-1.0',
            endpoint=RobotEndpoint('robot.invalid','twinpulse'),expected_revision=0)
        for phase in ('starting','error'):
            self.supervisor_status.write_text(json.dumps({'status':phase}),encoding='utf-8')
            state=service.snapshot('owner');saved=state['robots'][0]
            body=dict(action='set_battery_display',id=row['id'],config=battery_display_config(),
                expected_revision=state['revision'],expected_display_sha256=saved['battery_display_sha256'])
            status,result,_=self.request('/v1/product/robots',body,headers=self.product_headers)
            self.assertEqual(status,200);self.assertEqual(result['robots'][0]['battery_display']['mode'],'voltage_only')
            timing=result['robots'][0]['timing_settings']
            timing_body=dict(action='set_timing_profile',id=row['id'],values=timing['profile']['values'],mode='custom',
                expected_revision=result['revision'],expected_timing_sha256=timing['profile_sha256'])
            status,result,_=self.request('/v1/product/robots',timing_body,headers=self.product_headers)
            self.assertEqual(status,200);self.assertEqual(result['robots'][0]['timing_settings']['profile']['mode'],'custom')
            from twinpulse_core.robot_timing_profile import TimingAccumulator
            from twinpulse_app.robot_adapters import instance_binding
            samples=TimingAccumulator();samples.observe('odom_interval_ms',350,1,'base')
            service.registry.record_timing_measurement(row['id'],instance_binding(row)['sha256'],'a'*32,samples.snapshot())
            state=service.snapshot('owner');timing=state['robots'][0]['timing_settings']
            if phase=='starting':self.assertIsNone(timing['recommendation'])
            registered=timing['profile']
            recalc=dict(action='recalculate_timing_profile',id=row['id'],expected_revision=state['revision'],expected_timing_sha256=timing['profile_sha256'])
            status,result,_=self.request('/v1/product/robots',recalc,headers=self.product_headers)
            self.assertEqual(status,200);timing=result['robots'][0]['timing_settings']
            self.assertEqual(timing['profile'],registered);self.assertEqual(timing['recommendation_origin'],'MANUAL_RECALCULATION')
            apply=dict(action='apply_timing_recommendation',id=row['id'],expected_revision=result['revision'],expected_timing_sha256=timing['profile_sha256'],expected_recommendation_sha256=timing['recommendation_sha256'])
            status,_,_=self.request('/v1/product/robots',dict(apply,expected_recommendation_sha256='f'*64),headers=self.product_headers)
            self.assertEqual(status,409)
            status,result,_=self.request('/v1/product/robots',apply,headers=self.product_headers)
            self.assertEqual(status,200);self.assertEqual(result['robots'][0]['timing_settings']['profile'],timing['recommendation']['profile'])
            for metadata_action in (recalc,apply):
                status,_,_=self.request('/v1/product/robots',dict(metadata_action,extra='connect'),headers=self.product_headers)
                self.assertEqual(status,400)
                status,_,_=self.request('/v1/product/robots',metadata_action,headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':'invalid'})
                self.assertEqual(status,403)
            # Only the data-only action is exempt: credentials/shape/connection
            # admission remain enforced, not a generic robots-route bypass.
            status,_,_=self.request('/v1/product/robots',dict(timing_body,extra='connect'),headers=self.product_headers)
            self.assertEqual(status,400)
            for action in ('connect','prepare','discover','select'):
                status,_,_=self.request('/v1/product/robots',dict(action=action,expected_revision=result['revision']),headers=self.product_headers)
                self.assertEqual(status,409)
            status,_,_=self.request('/v1/product/robots',dict(action=['set_timing_profile']),headers=self.product_headers)
            self.assertEqual(status,409) # no unhashable-action500 or metadata bypass
            status,_,_=self.request('/v1/product/robots',dict(body,action='set_battery_display',extra='connect'),headers=self.product_headers)
            self.assertEqual(status,400)
            status,_,_=self.request('/v1/product/robots',body,headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':'invalid'})
            self.assertEqual(status,403)

    def test_owned_stop_reaches_controller_during_launcher_failure(self) -> None:
        controller = Mock()
        controller.input.return_value = {"state": "STOPPING", "physical_verified": False}
        self.server.physical_controller = controller
        for state in ("ready", "starting", "error", "missing"):
            for action in ("finish_stop", "force_stop"):
                with self.subTest(state=state, action=action):
                    if state == "missing":
                        self.supervisor_status.unlink(missing_ok=True)
                    else:
                        self.supervisor_status.write_text(json.dumps({"status": state}), encoding="utf-8")
                    body = {"job_id": "owned-job", "sequence": 1, "action": action, "expires_at_ms": 0}
                    before = controller.input.call_count
                    status, result, _ = self.request(
                        "/v1/product/robot/physical/input", body, headers=self.product_headers,
                    )
                    self.assertEqual(status, 200)
                    self.assertFalse(result["physical_verified"])
                    self.assertEqual(controller.input.call_count, before + 1)
                    self.assertEqual(controller.input.call_args.args[1:4], ("owned-job", 1, action))
        self.launcher_project_switch_file.write_text("{}", encoding="utf-8")
        status, _, _ = self.request("/v1/product/robot/physical/input", body, headers=self.product_headers)
        self.assertEqual(status, 200)
        for action in ("forward", "watch", "qualify", "lidar_start"):
            body["action"] = action
            before = controller.input.call_count
            status, result, _ = self.request(
                "/v1/product/robot/physical/input", body, headers=self.product_headers,
            )
            self.assertEqual(status, 409)
            self.assertEqual(controller.input.call_count, before)
        body["action"] = "force_stop"
        status, _, _ = self.request("/v1/product/robot/physical/input", body,
                                    headers={"Cookie": self.cookie, "X-TwinPulse-CSRF": "invalid"})
        self.assertEqual(status, 403)

    def test_saved_v2_scene_reopens_via_authenticated_api_without_provider_call(self) -> None:
        from tests.integration.test_h2b2_site_review import SiteGateway
        for image in (False, True):
            with self.subTest(image=image):
                store = ProjectStore(self.static / f"saved_{image}.json")
                archive = InputArtifactStore(self.static / f"inputs_{image}")
                app = ApplicationService(SiteGateway(), project_store=store, artifact_store=archive)
                from twinpulse_provider import ImageInput
                images = (ImageInput("room.png", "image/png", png()),) if image else ()
                prepared = app.prepare_input(prompt="Saved room", images=images, measurement_constraints=(),
                                             generation_settings={"model_id": "original"})
                app.select_input(prepared)
                outcome = asyncio.run(app.generate())
                scene = outcome.record.site.scene.revision
                original_project = store.path.read_bytes()
                self.workflow.shutdown()
                restored = ApplicationService(SiteGateway(), project_store=store, artifact_store=archive)
                self.workflow = ProductWorkflow(restored, self.broker, mode="live_provider",
                    generation_settings_getter=lambda: {"model_id": "changed"},
                    gateway_factory=SiteGateway)
                self.server.product_workflow = self.workflow
                status, before, _ = self.request("/v1/product/workflow", headers={"Cookie": self.cookie})
                self.assertEqual((status, before["phase"]), (200, "restore_review_required"))
                self.assertEqual(self.workflow.provider_settings_changed()["phase"], "restore_review_required")
                body = {"project_id": "default", "expected_scene_revision": scene,
                        "expected_input_revision": prepared.revision.digest}
                status, resumed, _ = self.request("/v1/product/project/resume-scene", body,
                                                   headers=self.product_headers)
                self.assertEqual((status, resumed["phase"]), (200, "draft_ready"))
                self.assertIsNone(resumed["acknowledged_revision"])
                self.assertFalse(resumed["build_allowed"])
                self.assertEqual(resumed["input"]["revision"], prepared.revision.digest)
                self.assertEqual(store.path.read_bytes(), original_project)
                body["expected_scene_revision"] = "0" * 64
                status, rejected, _ = self.request("/v1/product/project/resume-scene", body,
                                                    headers=self.product_headers)
                self.assertEqual((status, rejected["error"]["code"]), (409, "saved_scene_stale"))
                body["expected_scene_revision"] = scene
                archived = archive.root / prepared.revision.digest
                missing = (archived / f"{prepared.revision.images[0]['sha256']}.bin" if image else
                           archived / "revision.json")
                missing.unlink()
                self.workflow.shutdown()
                self.workflow = ProductWorkflow(
                    ApplicationService(SiteGateway(), project_store=store, artifact_store=archive),
                    self.broker, mode="live_provider",
                    generation_settings_getter=lambda: {"model_id": "later"})
                self.server.product_workflow = self.workflow
                status, rejected, _ = self.request("/v1/product/project/resume-scene", body,
                                                    headers=self.product_headers)
                self.assertEqual((status, rejected["error"]["code"]), (409, "saved_input_missing"))
                reattach = {**body, "name": "room.png" if image else None,
                            "media_type": "image/png" if image else None,
                            "content_base64": base64.b64encode(png()).decode() if image else None}
                if image:
                    status, rejected, _ = self.request("/v1/product/project/reattach-source",
                        {**reattach, "content_base64": base64.b64encode(b"wrong image").decode()},
                        headers=self.product_headers)
                    self.assertNotEqual(status, 200)
                status, reopened, _ = self.request("/v1/product/project/reattach-source", reattach,
                                                   headers=self.product_headers)
                self.assertEqual((status, reopened["phase"]), (200, "draft_ready"))
                self.assertEqual(store.path.read_bytes(), original_project)
                (archived / "revision.json").write_text("{}", encoding="utf-8")
                status, rejected, _ = self.request("/v1/product/project/resume-scene", body,
                                                    headers=self.product_headers)
                self.assertEqual((status, rejected["error"]["code"]),
                                 (409, "saved_scene_restore_invalid"))
                self.assertEqual(store.path.read_bytes(), original_project)


    def test_retry_requires_stopped_failed_engine_and_is_one_shot(self) -> None:
        status, result, _ = self.request("/v1/product/runtime/retry", {}, headers=self.product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "launcher_retry_unavailable")
        current = json.loads(self.supervisor_status.read_text(encoding="utf-8"))
        current["status"] = "error"
        current["engine"]["state"] = "running"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        self.assertEqual(self.request("/v1/product/runtime/retry", {}, headers=self.product_headers)[0], 409)
        current["engine"]["state"] = "exited"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        status, result, _ = self.request("/v1/product/runtime/retry", {}, headers=self.product_headers)
        self.assertEqual(status, 202)
        self.assertTrue(result["new_session_required"])
        self.assertEqual(json.loads(self.launcher_retry_file.read_text(encoding="utf-8")),
                         {"schema_version": "1.0", "action": "retry"})
        status, result, _ = self.request("/v1/product/runtime/retry", {}, headers=self.product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "launcher_retry_pending")

    def test_runtime_diagnostics_allowlist_never_exports_raw_exception_or_path(self) -> None:
        self.engine_result_file.write_text(json.dumps({
            "status": "FAIL", "startup_phase": "isaac_import", "error_type": "ImportError",
            "error": "PRIVATE-KEY at C:/company/photo.jpg", "traceback": "SECRET-TRACE",
            "startup_profile": {"schema_version": "engine-startup-profile-1.0", "python": "3.12.13",
                "packages": {"numpy": {"loaded": True, "origin_class": "extension_prebundle",
                                       "origin_sha256": "a" * 64, "version": "2.3.1",
                                       "private_path": "C:/company/photo.jpg"},
                             "scipy": {"loaded": False, "origin_class": "SECRET-TRACE",
                                       "origin_sha256": None, "version": "PRIVATE-KEY"}}},
        }), encoding="utf-8")
        current = json.loads(self.supervisor_status.read_text(encoding="utf-8"))
        current["message"] = "PRIVATE-KEY from another source"
        current["phase"] = "SECRET-TRACE"
        current["started_at_utc"] = "PRIVATE-KEY"
        current["updated_at_utc"] = "C:/company/photo.jpg"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        with patch.dict(os.environ,{'TWINPULSE_RELEASE_ID':'20261014T120000Z-review',
                'TWINPULSE_RELEASE_VERSION':'0.1.0a1','TWINPULSE_SIM_ONLY':'1'}):
            status, result, _ = self.request("/v1/product/runtime/diagnostics", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200)
        self.assertEqual(result['release'],{'build_id':'20261014T120000Z-review',
            'product_version':'0.1.0a1','simulation_only':True})
        self.assertEqual(result["engine_startup"]["error_type"], "ImportError")
        self.assertEqual(result["engine_runtime_profile"]["packages"]["numpy"]["origin_class"],
                         "extension_prebundle")
        self.assertEqual(result["engine_runtime_profile"]["packages"]["scipy"]["origin_class"], "unknown")
        self.assertEqual(result["runtime"]["phase"], "unknown")
        self.assertIsNone(result["runtime"]["started_at_utc"])
        self.assertIsNone(result["runtime"]["updated_at_utc"])
        encoded = json.dumps(result)
        self.assertNotIn("PRIVATE-KEY", encoded)
        self.assertNotIn("company", encoded)
        self.assertNotIn("SECRET-TRACE", encoded)
        self.assertNotIn(str(self.static), encoded)
        self.assertEqual(self.request("/v1/product/runtime/diagnostics")[0], 401)

    def test_startup_cancel_is_explicit_one_shot_and_not_available_when_ready(self) -> None:
        self.assertEqual(self.request("/v1/product/runtime/cancel", {}, headers=self.product_headers)[0], 409)
        current = json.loads(self.supervisor_status.read_text(encoding="utf-8"))
        current["status"] = "starting"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        status, result, _ = self.request("/v1/product/runtime/cancel", {}, headers=self.product_headers)
        self.assertEqual((status, result["status"]), (202, "requested"))
        self.assertEqual(json.loads(self.launcher_cancel_file.read_text(encoding="utf-8")),
                         {"schema_version": "1.0", "action": "cancel_startup"})
        status, result, _ = self.request("/v1/product/runtime/cancel", {}, headers=self.product_headers)
        self.assertEqual((status, result["error"]["code"]), (409, "startup_cancel_pending"))

    def test_project_switch_requires_saved_target_and_idle_ready_runtime(self) -> None:
        catalog = self.server.project_catalog
        catalog.create_empty("room_two")
        status, result, _ = self.request("/v1/product/projects/switch", {"project_id": "missing"},
                                         headers=self.product_headers)
        self.assertEqual((status, result["error"]["code"]), (409, "project_source_unavailable"))
        self.assertFalse(self.launcher_project_switch_file.exists())
        current = json.loads(self.supervisor_status.read_text(encoding="utf-8"))
        current["status"] = "error"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        self.assertEqual(self.request("/v1/product/projects/switch", {"project_id": "room_two"},
                                      headers=self.product_headers)[0], 409)
        current["status"] = "ready"
        current["engine"]["state"] = "running"
        self.supervisor_status.write_text(json.dumps(current), encoding="utf-8")
        status, result, _ = self.request("/v1/product/projects/switch", {"project_id": "room_two"},
                                         headers=self.product_headers)
        self.assertEqual((status, result["project_id"]), (202, "room_two"))
        self.assertEqual(json.loads(self.launcher_project_switch_file.read_text(encoding="utf-8")),
                         {"schema_version": "1.0", "action": "switch_project", "project_id": "room_two"})
        self.assertEqual(self.request("/v1/product/projects/switch", {"project_id": "room_two"},
                                      headers=self.product_headers)[0], 409)
        status, result, _ = self.request("/v1/product/projects/create", {"project_id": "too_late"},
                                         headers=self.product_headers)
        self.assertEqual((status, result["error"]["code"]), (409, "project_switch_pending"))
        self.assertFalse((self.static / "projects" / "too_late").exists())
        self.assertEqual(self.request("/v1/product/projects", headers={"Cookie": self.cookie})[0], 200)
        self.assertEqual(catalog.active_project_id, "default")

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
