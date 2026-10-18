# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No paid call: the structured edit adapter is exercised with a local fake."""

import asyncio
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
for name in ("twinpulse_core", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_core import canonical_sha256
from twinpulse_provider import (GenerationCancelledError, InvalidProviderResponseError,
                                OpenAIResponsesProvider, ProviderCapabilities, ProviderConfig,
                                ProviderResponse, ProviderTimeoutError, SceneEditProposalService,
                                scene_edit_generation_request)


def context():
    value = {
        "schema_version": "scene-edit-context-1.0", "project_id": "bedroom",
        "source_scene_revision": "a" * 64, "current_scene_revision": "b" * 64,
        "request_text": "Move the selected bed to X -0.7 m",
        "selected_call_id": "bed_call",
        "furniture_calls": [{"call_id": "bed_call", "tool": "place_furniture",
                             "arguments": {"id": "bed", "kind": "bed", "catalog_version": "furniture-blocks-1.0",
                                           "center_m": [-0.8, 0.7], "yaw_deg": 0}}],
        "scene_objects": [], "boundary": "Proposal only. Explicit preview/apply is required.",
    }
    return {**value, "context_sha256": canonical_sha256(value)}


def config(timeout=1):
    return ProviderConfig(base_url="https://example.invalid/v1/", endpoint_path="responses", model_id="fake",
                          api_key_env="UNUSED", capabilities=ProviderCapabilities(False, True), timeout_s=timeout)


def proposal(value):
    return {"schema_version": "scene-edit-proposal-1.0", "context_sha256": value["context_sha256"],
            "mode": "change_furniture", "explanation": "Move the selected bed only.",
            "target_call_id": "bed_call", "tool_call": {**value["furniture_calls"][0],
                "arguments": {**value["furniture_calls"][0]["arguments"], "center_m": [-0.7, 0.7]}}}


class FakeProvider:
    def __init__(self, output, *, delay=0):
        self.output = output
        self.delay = delay
        self.calls = []

    async def generate(self, request, token, settings):
        self.calls.append(request)
        await asyncio.sleep(self.delay)
        return ProviderResponse(request.request_id, self.output, "offline-fake", settings.model_id)


class SceneEditProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_context_bound_single_response_and_real_responses_body(self):
        current = context()
        fake = FakeProvider(proposal(current))
        actual = await SceneEditProposalService(fake, config()).propose(current, "edit-1")
        self.assertEqual(actual["target_call_id"], "bed_call")
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse(fake.calls[0].images)
        self.assertEqual(json.loads(fake.calls[0].prompt)["context_sha256"], current["context_sha256"])
        adapter = OpenAIResponsesProvider(lambda: None)
        body = adapter.build_request_body(fake.calls[0], config())
        self.assertEqual(body["text"]["format"]["name"], "twinpulse_scene_edit_proposal")
        self.assertEqual(body["text"]["format"]["schema"]["properties"]["mode"]["enum"],
                         ["clarify", "add_furniture", "change_furniture"])
        self.assertEqual(body["store"], False)
        self.assertNotIn("data:image", json.dumps(body))
        self.assertIn("English by default", body["instructions"])

    async def test_invalid_or_stale_input_never_calls_provider(self):
        current = context()
        fake = FakeProvider(proposal(current))
        service = SceneEditProposalService(fake, config())
        with self.assertRaises(ValueError):
            await service.propose({**current, "request_text": "different"}, "edit-1")
        with self.assertRaises(ValueError):
            await service.propose({**current, "api_key": "never send"}, "edit-1")
        injected = {**current, "furniture_calls": [{**current["furniture_calls"][0],
                      "authorization": "never send"}]}
        injected["context_sha256"] = canonical_sha256({key: value for key, value in injected.items()
                                                         if key != "context_sha256"})
        with self.assertRaises(ValueError):
            await service.propose(injected, "edit-1")
        self.assertEqual(fake.calls, [])
        with self.assertRaises(ValueError):
            scene_edit_generation_request(current, "")

    async def test_wrong_context_and_extra_output_are_rejected(self):
        current = context()
        for response in ({**proposal(current), "context_sha256": "0" * 64},
                         {**proposal(current), "scene": {"replace": True}}):
            with self.subTest(response=response):
                with self.assertRaises(InvalidProviderResponseError):
                    await SceneEditProposalService(FakeProvider(response), config()).propose(current, "edit-1")

    async def test_timeout_cancels_one_call_without_retry(self):
        current = context()
        fake = FakeProvider(proposal(current), delay=0.05)
        with self.assertRaises(ProviderTimeoutError):
            await SceneEditProposalService(fake, config(0.005)).propose(current, "edit-1")
        self.assertEqual(len(fake.calls), 1)

    async def test_wrong_request_id_is_rejected(self):
        current = context()

        class WrongId(FakeProvider):
            async def generate(self, request, token, settings):
                return ProviderResponse("another-request", self.output, "offline-fake", settings.model_id)

        with self.assertRaises(GenerationCancelledError):
            await SceneEditProposalService(WrongId(proposal(current)), config()).propose(current, "edit-1")


if __name__ == "__main__":
    unittest.main()
