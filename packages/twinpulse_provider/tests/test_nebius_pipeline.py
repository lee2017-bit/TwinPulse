from __future__ import annotations

import asyncio
from collections.abc import Mapping
import json
from pathlib import Path
import sys
import unittest
import urllib.error


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_core" / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_provider" / "src"))

from twinpulse_core import demo_warehouse_tool_plan  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    CancellationToken,
    ChatCompletion,
    GenerationCancelledError,
    GenerationRequest,
    GenerationService,
    ImageInput,
    InvalidProviderResponseError,
    NebiusChatCompletionsPipelineProvider,
    ObservationArtifact,
    ProviderAuthenticationError,
    ProviderCapabilities,
    ProviderConfig,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UrllibChatCompletionsTransport,
    parse_chat_completion,
)


OBSERVER_MODEL = "google/gemma-3-27b-it"
PLANNER_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def config(*, timeout_s: float = 1.0) -> ProviderConfig:
    return ProviderConfig(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        endpoint_path="chat/completions",
        model_id=PLANNER_MODEL,
        api_key_env="TWINPULSE_UNUSED_NEBIUS_KEY",
        capabilities=ProviderCapabilities(
            supports_images=True,
            supports_structured_output=True,
            max_images=1,
            accepted_mime_types=("image/png", "image/jpeg", "image/webp"),
        ),
        timeout_s=timeout_s,
        max_attempts=1,
    )


def request() -> GenerationRequest:
    return GenerationRequest(
        "request-1",
        "Build a warehouse aisle from the attached photo.",
        (ImageInput("warehouse.png", "image/png", b"not-a-real-image-but-transport-is-fake"),),
    )


def observation() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "summary": "Two parallel rack rows bound a clear center aisle.",
        "entities": [
            {"id": "rack_left", "kind": "rack", "description": "left rack row", "confidence": 0.95},
            {"id": "rack_right", "kind": "rack", "description": "right rack row", "confidence": 0.94},
            {"id": "aisle_center", "kind": "aisle", "description": "center aisle", "confidence": 0.9},
        ],
        "relations": [
            {"subject_id": "rack_left", "relation": "parallel_to", "object_id": "rack_right"},
            {"subject_id": "aisle_center", "relation": "inside", "object_id": "rack_left"},
        ],
        "dimensions": [
            {"target_id": "aisle_center", "dimension": "width", "value_m": None, "confidence": 0.2},
        ],
        "ambiguities": ["Absolute scale is not visible."],
    }


class ScriptedTransport:
    def __init__(self, *responses: ChatCompletion | Exception, delay_s: float = 0.0) -> None:
        self.responses = list(responses)
        self.delay_s = delay_s
        self.bodies: list[Mapping[str, object]] = []

    async def complete(self, body, token, provider_config):  # noqa: ANN001, ANN201
        self.bodies.append(body)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def completion(response_id: str, model_id: str, value: object) -> ChatCompletion:
    return ChatCompletion(
        response_id,
        model_id,
        json.dumps(value, ensure_ascii=False),
        "stop",
        {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )


def slotted_plan() -> dict[str, object]:
    plan = demo_warehouse_tool_plan().to_dict()
    calls = list(plan.pop("calls"))
    floor_call = next(item for item in calls if item["tool"] == "create_floor")
    agv_call = next(item for item in calls if item["tool"] == "place_predefined_agv")
    navigation_call = next(item for item in calls if item["tool"] == "create_navigation_task")
    scene_calls = [
        item for item in calls
        if item["tool"] not in {"create_floor", "place_predefined_agv", "create_navigation_task"}
    ]
    return {
        **plan,
        "floor_call": floor_call,
        "scene_calls": scene_calls,
        "agv_call": agv_call,
        "navigation_call": navigation_call,
    }


class NebiusPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_stage_pipeline_is_image_first_and_returns_validated_plan(self) -> None:
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            completion("plan-1", PLANNER_MODEL, slotted_plan()),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )

        result = await GenerationService(provider, config()).generate(request())

        self.assertEqual(result.bundle.scene.id, "warehouse_tool_demo_v1")
        self.assertEqual(len(transport.bodies), 2)
        observer_body, planner_body = transport.bodies
        self.assertEqual(observer_body["model"], OBSERVER_MODEL)
        self.assertEqual(planner_body["model"], PLANNER_MODEL)
        self.assertTrue(observer_body["response_format"]["json_schema"]["strict"])
        self.assertTrue(planner_body["response_format"]["json_schema"]["strict"])
        serialized_observer = json.dumps(observer_body)
        serialized_planner = json.dumps(planner_body)
        self.assertIn("data:image/png;base64,", serialized_observer)
        self.assertNotIn("data:image", serialized_planner)
        self.assertIn("visual_observation", serialized_planner)
        provenance = result.provider_provenance
        self.assertEqual(provenance["observer_model_id"], OBSERVER_MODEL)
        self.assertEqual(provenance["planner_model_id"], PLANNER_MODEL)
        self.assertEqual(provenance["input_image"]["byte_count"], len(request().images[0].content))
        self.assertEqual(len(provenance["input_image"]["sha256"]), 64)
        self.assertEqual([item["role"] for item in provenance["stages"]], ["observer", "planner"])
        serialized_provenance = json.dumps(provenance).lower()
        self.assertNotIn("base64,", serialized_provenance)
        self.assertNotIn("bearer ", serialized_provenance)

    async def test_invalid_observation_stops_before_planner(self) -> None:
        invalid = observation()
        invalid["entities"] = [{"id": "bad id", "kind": "rack", "description": "rack", "confidence": 1}]
        transport = ScriptedTransport(completion("obs-1", OBSERVER_MODEL, invalid))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "observation entity identity"):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 1)

    async def test_response_model_mismatch_is_rejected_before_next_stage(self) -> None:
        transport = ScriptedTransport(completion("obs-1", "unexpected/model", observation()))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "observer response model"):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 1)

    async def test_observer_invalid_response_names_stage_and_stops_before_planner(self) -> None:
        transport = ScriptedTransport(InvalidProviderResponseError("Chat Completions output was truncated"))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        with self.assertRaisesRegex(
            InvalidProviderResponseError,
            "observer stage response invalid: Chat Completions output was truncated",
        ):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 1)

    async def test_planner_invalid_response_names_stage_after_observer(self) -> None:
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            InvalidProviderResponseError("Chat Completions output was truncated"),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        with self.assertRaisesRegex(
            InvalidProviderResponseError,
            "planner stage response invalid: Chat Completions output was truncated",
        ):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 2)

    async def test_missing_required_planner_slot_is_rejected_locally(self) -> None:
        invalid = slotted_plan()
        invalid.pop("agv_call")
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            completion("plan-1", PLANNER_MODEL, invalid),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        with self.assertRaisesRegex(
            InvalidProviderResponseError, "planner output has unexpected or missing call slots",
        ):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 2)

    async def test_blocked_planner_route_is_resolved_locally_and_recorded(self) -> None:
        value = slotted_plan()
        value["agv_call"]["arguments"]["start_position_m"] = [0.0, 1.6, 0.0]
        value["navigation_call"]["arguments"]["goal_position_m"] = [1.5, 1.6, 0.0]
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            completion("plan-1", PLANNER_MODEL, value),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )

        result = await GenerationService(provider, config()).generate(request())

        start_call = next(call for call in result.plan.calls if call.tool == "place_predefined_agv")
        task_call = next(call for call in result.plan.calls if call.tool == "create_navigation_task")
        self.assertNotEqual(start_call.arguments["start_position_m"][1], 1.6)
        self.assertEqual(
            start_call.arguments["start_position_m"][1],
            task_call.arguments["goal_position_m"][1],
        )
        self.assertEqual(
            result.provider_provenance["local_route_resolution"]["revision"],
            "straight-x-aabb-v1",
        )

    async def test_planner_agv_height_is_projected_to_floor_before_validation(self) -> None:
        value = slotted_plan()
        value["agv_call"]["arguments"]["start_position_m"] = [0.0, 0.0, 0.35]
        value["navigation_call"]["arguments"]["goal_position_m"] = [1.5, 0.0, 0.35]
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            completion("plan-1", PLANNER_MODEL, value),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )

        result = await GenerationService(provider, config()).generate(request())

        self.assertEqual(result.bundle.task.start.position_m[2], 0.0)
        self.assertEqual(result.bundle.task.goal.position_m[2], 0.0)
        self.assertTrue(result.provider_provenance["local_route_resolution"]["applied"])

    def test_pipeline_prompts_and_observation_schema_bound_output_growth(self) -> None:
        provider = NebiusChatCompletionsPipelineProvider(
            ScriptedTransport(), observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
        )
        observer_body = provider.build_observer_body(request())
        schema = observer_body["response_format"]["json_schema"]["schema"]
        properties = schema["properties"]
        self.assertEqual(properties["entities"]["maxItems"], 24)
        self.assertEqual(properties["relations"]["maxItems"], 32)
        self.assertEqual(properties["dimensions"]["maxItems"], 24)
        self.assertEqual(properties["ambiguities"]["maxItems"], 12)
        self.assertIn("group repeated rack bays", observer_body["messages"][0]["content"])
        planner_body = provider.build_planner_body(
            request(), ObservationArtifact.from_mapping(observation()),
        )
        self.assertIn("at most 14 ordered tool calls", planner_body["messages"][0]["content"])
        self.assertIn("call_id values must also be unique", planner_body["messages"][0]["content"])
        self.assertIn("Fill every required call slot exactly once", planner_body["messages"][0]["content"])
        self.assertIn("deterministically move it", planner_body["messages"][0]["content"])
        plan_schema = planner_body["response_format"]["json_schema"]["schema"]
        identifier_pattern = "^[A-Za-z][A-Za-z0-9_-]{0,63}$"
        self.assertEqual(plan_schema["properties"]["scene_id"]["pattern"], identifier_pattern)
        self.assertEqual(
            plan_schema["required"],
            [
                "plan_version", "scene_id", "summary", "image_observations",
                "floor_call", "scene_calls", "agv_call", "navigation_call",
            ],
        )
        call_schemas = [
            plan_schema["properties"]["floor_call"],
            *plan_schema["properties"]["scene_calls"]["items"]["anyOf"],
            plan_schema["properties"]["agv_call"],
            plan_schema["properties"]["navigation_call"],
        ]
        for call_schema in call_schemas:
            self.assertEqual(call_schema["properties"]["call_id"]["pattern"], identifier_pattern)
            argument_id = call_schema["properties"]["arguments"]["properties"].get("id")
            if argument_id is not None:
                self.assertEqual(argument_id["pattern"], identifier_pattern)

    async def test_manual_fallback_is_not_an_automatic_retry(self) -> None:
        transport = ScriptedTransport(ProviderRateLimitError("limited"))
        provider = NebiusChatCompletionsPipelineProvider(
            transport,
            observer_model_id="openbmb/MiniCPM-V-4_5",
            planner_model_id=PLANNER_MODEL,
            fallback_observer_selected=True,
        )
        with self.assertRaises(ProviderRateLimitError):
            await GenerationService(provider, config()).generate(request())
        self.assertEqual(len(transport.bodies), 1)

    async def test_late_observer_response_is_cancelled_without_planner_call(self) -> None:
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()),
            completion("plan-1", PLANNER_MODEL, demo_warehouse_tool_plan().to_dict()),
            delay_s=0.03,
        )
        service = GenerationService(
            NebiusChatCompletionsPipelineProvider(
                transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            ),
            config(),
        )
        task = asyncio.create_task(service.generate(request()))
        await asyncio.sleep(0.005)
        service.cancel_active()
        with self.assertRaises(GenerationCancelledError):
            await task
        self.assertEqual(len(transport.bodies), 1)

    async def test_pipeline_timeout_is_typed_and_does_not_retry(self) -> None:
        transport = ScriptedTransport(
            completion("obs-1", OBSERVER_MODEL, observation()), delay_s=0.05,
        )
        service = GenerationService(
            NebiusChatCompletionsPipelineProvider(
                transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            ),
            config(timeout_s=0.01),
        )
        with self.assertRaises(ProviderTimeoutError):
            await service.generate(request())
        self.assertEqual(len(transport.bodies), 1)

    def test_chat_parser_rejects_truncation_refusal_and_tool_only_finish(self) -> None:
        base = {
            "id": "x", "model": OBSERVER_MODEL,
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        }
        for mutation in (
            {"finish_reason": "length", "message": {"content": "{}"}},
            {"finish_reason": "stop", "message": {"content": "{}", "refusal": "no"}},
            {"finish_reason": "tool_calls", "message": {"content": "{}"}},
        ):
            value = dict(base)
            value["choices"] = [mutation]
            with self.assertRaises(InvalidProviderResponseError):
                parse_chat_completion(value)


class NebiusHttpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_statuses_are_typed_and_secret_is_not_exposed(self) -> None:
        cases = (
            (401, ProviderAuthenticationError),
            (429, ProviderRateLimitError),
            (503, ProviderUnavailableError),
            (302, ProviderRequestError),
        )
        for status, expected in cases:
            def opener(request, timeout, *, code=status):  # noqa: ANN001, ANN202
                raise urllib.error.HTTPError(request.full_url, code, "failed", {}, None)

            transport = UrllibChatCompletionsTransport(lambda: "super-secret-token", opener=opener)
            with self.subTest(status=status):
                with self.assertRaises(expected) as raised:
                    await transport.complete({"model": OBSERVER_MODEL}, CancellationToken(), config())
                self.assertNotIn("super-secret-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
