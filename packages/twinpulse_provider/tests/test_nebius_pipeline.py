# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
import urllib.error


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_core" / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_provider" / "src"))

from twinpulse_core import current_controller_route_prompt, demo_warehouse_tool_plan  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    CancellationToken,
    ChatCompletion,
    GenerationCancelledError,
    GenerationRequest,
    GenerationService,
    ImageInput,
    MeasurementConstraint,
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
    async def test_v2_unsupported_measurement_fails_without_paid_transport(self) -> None:
        transport = ScriptedTransport()
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        constrained = replace(request(), measurement_constraints=(
            MeasurementConstraint("floor_width", "create_floor", "size_m.0", 4.0, 0.1),
        ))
        with self.assertRaisesRegex(ValueError, "does not yet support"):
            await GenerationService(provider, config(), plan_version="2.0").generate(constrained)
        self.assertEqual(transport.bodies, [])

    async def test_explicit_v2_profile_requests_scene_only_without_fake_robot(self) -> None:
        plan = demo_warehouse_tool_plan().to_dict()
        plan["plan_version"] = "2.0"
        plan["calls"] = [item for item in plan["calls"] if item["tool"] == "create_floor"]
        plan["call_evidence"] = [{"call_id": "floor", "observation_ids": [],
                                  "basis": "inferred", "note": "Approximate ground"}]
        transport = ScriptedTransport(
            completion("obs-site", OBSERVER_MODEL, observation()),
            completion("plan-site", PLANNER_MODEL, plan),
        )
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        result = await GenerationService(provider, config(), plan_version="2.0").generate(request())
        self.assertEqual(result.plan.plan_version, "2.0")
        self.assertEqual(len(result.plan.calls), 1)
        self.assertNotIn("bundle", result.__dataclass_fields__)
        observer, planner = transport.bodies
        self.assertIn("site image", observer["messages"][0]["content"])
        self.assertIn("optional", planner["messages"][0]["content"])
        self.assertEqual(planner["response_format"]["json_schema"]["schema"]["properties"]["plan_version"]["const"], "2.0")

    async def test_v2_rejects_fabricated_visual_reference_before_accepting_plan(self) -> None:
        plan = demo_warehouse_tool_plan().to_dict()
        plan["plan_version"] = "2.0"
        plan["calls"] = [item for item in plan["calls"] if item["tool"] == "create_floor"]
        plan["call_evidence"] = [{"call_id": "floor", "observation_ids": ["invented"],
                                  "basis": "visual", "note": "Claimed ground"}]
        transport = ScriptedTransport(completion("obs-site", OBSERVER_MODEL, observation()),
                                      completion("plan-site", PLANNER_MODEL, plan))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "unobserved visual entity"):
            await GenerationService(provider, config(), plan_version="2.0").generate(request())

    async def test_v2_nonwarehouse_site_plan_uses_generic_obstacle_and_evidence(self) -> None:
        observed = {
            "schema_version": "1.0", "summary": "A floor and freestanding barrier on a test track.",
            "entities": [
                {"id": "ground", "kind": "floor", "description": "visible ground", "confidence": 0.8},
                {"id": "barrier_seen", "kind": "static_obstacle", "description": "box barrier", "confidence": 0.9},
                {"id": "robot_seen", "kind": "robot_candidate", "description": "small wheeled robot", "confidence": 0.6},
                {"id": "hidden_corner", "kind": "unknown", "description": "occluded corner", "confidence": 0.9},
            ], "relations": [], "dimensions": [], "ambiguities": ["Robot identity is unconfirmed."],
        }
        plan = {
            "plan_version": "2.0", "scene_id": "test_track", "summary": "Approximate test track",
            "image_observations": "Freestanding barrier; hidden corner remains unknown.",
            "calls": [
                {"call_id": "ground_call", "tool": "create_floor",
                 "arguments": {"id": "ground_mesh", "center_m": [0, 0], "size_m": [6, 4]}},
                {"call_id": "barrier_call", "tool": "create_box_obstacle",
                 "arguments": {"id": "barrier", "center_m": [1, 0],
                               "dimensions_m": [0.8, 0.4, 1.0], "yaw_deg": 0}},
            ],
            "call_evidence": [
                {"call_id": "ground_call", "observation_ids": ["ground"],
                 "basis": "visual", "note": "Visible ground; size approximate"},
                {"call_id": "barrier_call", "observation_ids": ["barrier_seen"],
                 "basis": "visual", "note": "Visible barrier; size approximate"},
            ],
        }
        transport = ScriptedTransport(completion("obs-track", OBSERVER_MODEL, observed),
                                      completion("plan-track", PLANNER_MODEL, plan))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        result = await GenerationService(provider, config(), plan_version="2.0").generate(request())
        self.assertEqual(result.plan.scene_id, "test_track")
        self.assertEqual(result.plan.calls[1].tool, "create_box_obstacle")
        self.assertFalse(any(call.tool == "place_predefined_agv" for call in result.plan.calls))
        self.assertEqual(result.plan.call_evidence[1].observation_ids, ("barrier_seen",))

    async def test_v2_unknown_region_cannot_be_visual_ground_evidence(self) -> None:
        observed = observation()
        observed["entities"].append({"id": "occluded_floor", "kind": "unknown",
                                     "description": "floor behind shelf not seen", "confidence": 0.9})
        plan = demo_warehouse_tool_plan().to_dict()
        plan["plan_version"] = "2.0"
        plan["calls"] = [item for item in plan["calls"] if item["tool"] == "create_floor"]
        plan["call_evidence"] = [{"call_id": plan["calls"][0]["call_id"],
                                  "observation_ids": ["occluded_floor"], "basis": "visual",
                                  "note": "Claims unseen floor is visible"}]
        transport = ScriptedTransport(completion("obs-unknown", OBSERVER_MODEL, observed),
                                      completion("plan-unknown", PLANNER_MODEL, plan))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "unknown region"):
            await GenerationService(provider, config(), plan_version="2.0").generate(request())

    async def test_v2_visual_basis_without_observation_id_fails(self) -> None:
        plan = demo_warehouse_tool_plan().to_dict()
        plan["plan_version"] = "2.0"
        plan["calls"] = [item for item in plan["calls"] if item["tool"] == "create_floor"]
        plan["call_evidence"] = [{"call_id": plan["calls"][0]["call_id"],
                                  "observation_ids": [], "basis": "visual",
                                  "note": "Claimed image observation without ID"}]
        transport = ScriptedTransport(completion("obs-no-id", OBSERVER_MODEL, observation()),
                                      completion("plan-no-id", PLANNER_MODEL, plan))
        provider = NebiusChatCompletionsPipelineProvider(
            transport, observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "requires an observed entity"):
            await GenerationService(provider, config(), plan_version="2.0").generate(request())

    def test_v2_catalog_and_observer_are_site_generic(self) -> None:
        provider = NebiusChatCompletionsPipelineProvider(
            ScriptedTransport(), observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL,
            site_plan_version="2.0",
        )
        observer = provider.build_observer_body(request())
        planner = provider.build_planner_body(request(), ObservationArtifact.from_mapping(observation()))
        kinds = observer["response_format"]["json_schema"]["schema"]["properties"]["entities"]["items"]["properties"]["kind"]["enum"]
        tools = [item["properties"]["tool"]["const"] for item in
                 planner["response_format"]["json_schema"]["schema"]["properties"]["calls"]["items"]["anyOf"]]
        self.assertIn("robot_candidate", kinds)
        self.assertIn("free_space", kinds)
        self.assertIn("unknown", kinds)
        self.assertIn("create_box_obstacle", tools)
        self.assertIn("call_evidence", planner["response_format"]["json_schema"]["schema"]["required"])
        self.assertIn("not proof of the predefined drive profile", planner["messages"][0]["content"])

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
        for name in ('entities','relations','dimensions','ambiguities'):
            self.assertNotIn('maxItems',properties[name])
        from twinpulse_provider.nebius_pipeline import MAX_RESPONSE_BYTES
        self.assertEqual(MAX_RESPONSE_BYTES,2*1024*1024)
        self.assertIn("group repeated rack bays", observer_body["messages"][0]["content"])
        planner_body = provider.build_planner_body(
            request(), ObservationArtifact.from_mapping(observation()),
        )
        self.assertIn("at most 14 ordered tool calls", planner_body["messages"][0]["content"])
        self.assertIn(current_controller_route_prompt(), planner_body["messages"][0]["content"])
        self.assertIn("more than 0.2 and no more than 10", current_controller_route_prompt())
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
