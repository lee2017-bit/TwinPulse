# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline fake-provider edit proposals use the real product preview/apply boundary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_app import ApplicationService, CommandBroker, LocalApiServer, ProductWorkflow, ProjectStore  # noqa: E402
from twinpulse_app.project_catalog import ProjectCatalog  # noqa: E402
from twinpulse_provider import (ProviderCapabilities, ProviderConfig, ProviderResponse,
                                SceneEditProposalService)  # noqa: E402
from tests.integration.test_a2_room_recipe import NoGateway  # noqa: E402
from tests.integration.test_manual_room_creation import photo  # noqa: E402


class SceneEditProposalTests(unittest.TestCase):
    def test_fake_response_is_preview_only_and_bound_to_selected_saved_furniture(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ProjectCatalog(root, "default").create_from_manual_room(
                "furnished", prompt="Two pieces explicitly selected", photo=photo("blue"),
                media_type="image/png", width_m=3.6, length_m=5.2, wall_height_m=2.6,
                include_burger_visual=False, request_id=str(uuid4()),
                furniture=[{"kind": "bed", "center_m": [-0.8, 0.7], "yaw_deg": 0},
                           {"kind": "desk", "center_m": [0.8, 0.7], "yaw_deg": 0}],
            )
            project = ProjectStore.for_project(root, "furnished")
            original = project.path.read_bytes()
            broker = CommandBroker(project_id="furnished")
            workflow = ProductWorkflow(
                ApplicationService(NoGateway(), project_store=project, project_id="furnished"),
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
                prompt = "선택한 침대를 조금 이동"
                self.assertEqual(post("/v1/product/scene-edit/context", {
                    "request_text": prompt, "selected_call_id": None}, auth)[0], 409)
                opened = post("/v1/product/project/continue-room", {}, auth)[1]
                bed = next(call for call in opened["site_draft"]["editable_calls"]
                           if call["tool"] == "place_furniture" and call["arguments"]["kind"] == "bed")
                selected = bed["call_id"]
                context_body = {"request_text": prompt, "selected_call_id": selected}
                status, context, _ = post("/v1/product/scene-edit/context", context_body, auth)
                self.assertEqual(status, 200)
                self.assertEqual(context["current_scene_revision"], opened["site_draft"]["revision"])
                self.assertEqual(len(context["furniture_calls"]), 2)
                self.assertNotIn("photo", context)
                self.assertNotIn("image_base64", json.dumps(context))
                self.assertEqual(post("/v1/product/scene-edit/context", {
                    "request_text": prompt, "selected_call_id": "unknown"}, auth)[0], 409)
                base = {"schema_version": "scene-edit-proposal-1.0",
                        "context_sha256": context["context_sha256"],
                        "explanation": "선택한 침대의 위치만 조정합니다.",
                        "mode": "change_furniture", "target_call_id": selected}
                changed = {**bed, "arguments": {**bed["arguments"], "center_m": [-0.7, 0.7]}}
                class OfflineEditProvider:
                    calls = 0

                    async def generate(self, provider_request, token, provider_config):
                        self.calls += 1
                        self.assert_context = json.loads(provider_request.prompt)
                        return ProviderResponse(provider_request.request_id,
                                                {**base, "tool_call": changed},
                                                "offline-edit-fixture", provider_config.model_id)

                fake_provider = OfflineEditProvider()
                candidate = asyncio.run(SceneEditProposalService(fake_provider, ProviderConfig(
                    base_url="https://fixture.invalid/v1/", endpoint_path="responses",
                    model_id="offline-fixture", api_key_env="UNUSED",
                    capabilities=ProviderCapabilities(False, True), timeout_s=1,
                )).propose(context, "fake-provider-edit"))
                self.assertEqual(fake_provider.calls, 1)
                self.assertEqual(fake_provider.assert_context["current_scene_revision"], context["current_scene_revision"])
                request = {**context_body, "expected_revision": context["current_scene_revision"],
                           "operation_id": "fake_selected_move", "proposal": candidate}
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "scene": {"replace": True}, "tool_call": changed}}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "target_call_id": "other", "tool_call": changed}}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "tool_call": {**changed, "arguments": {
                        **changed["arguments"], "kind": "sofa"}}}}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "tool_call": {**changed, "tool": "create_floor"}}}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "context_sha256": "0" * 64, "tool_call": changed}}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "request_text": "다른 요청"}, auth)[0], 409)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "tool_call": bed}}, auth)[0], 409)
                status, clarify, _ = post("/v1/product/scene-edit/proposal-preview", {
                    **request, "proposal": {**base, "mode": "clarify", "target_call_id": None,
                                              "tool_call": None}}, auth)
                self.assertEqual(status, 200)
                self.assertIsNone(clarify["preview"])
                self.assertFalse(project.path.with_suffix(".scene-changes.json").exists())
                status, proposed, _ = post("/v1/product/scene-edit/proposal-preview", request, auth)
                self.assertEqual(status, 200)
                self.assertEqual(proposed["status"], "preview")
                preview = proposed["preview"]
                self.assertEqual(preview["parent_revision"], context["current_scene_revision"])
                self.assertFalse(project.path.with_suffix(".scene-changes.json").exists())
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", {
                    **request, "expected_revision": "0" * 64}, auth)[0], 409)
                status, applied, _ = post("/v1/product/scene-edit/apply", {
                    "operation": preview["operation"], "preview_digest": preview["preview_digest"]}, auth)
                self.assertEqual(status, 200)
                self.assertEqual(applied["site_draft"]["scene_edit_count"], 1)
                self.assertIsNone(applied["acknowledged_revision"])
                desk_id = next(call["arguments"]["id"] for call in context["furniture_calls"]
                               if call["arguments"]["kind"] == "desk")
                self.assertEqual(
                    [item for item in opened["site_draft"]["objects"] if item["id"].startswith(desk_id + "_")],
                    [item for item in applied["site_draft"]["objects"] if item["id"].startswith(desk_id + "_")],
                )
                self.assertEqual(project.path.read_bytes(), original)
                self.assertEqual(post("/v1/product/scene-edit/proposal-preview", request, auth)[0], 409)
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
