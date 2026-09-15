from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_core" / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_provider" / "src"))

from twinpulse_provider import (  # noqa: E402
    GenerationCancelledError,
    GenerationRequest,
    GenerationService,
    ImageInput,
    InvalidProviderResponseError,
    load_measurement_constraints,
    MeasurementConstraint,
    MeasurementConstraintError,
    measurement_sidecar_path,
    MockMode,
    MockProvider,
    OpenAIResponsesProvider,
    ProviderCapabilities,
    ProviderCapabilityError,
    ProviderConfig,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


def config(*, images: bool = True, timeout_s: float = 0.2) -> ProviderConfig:
    return ProviderConfig(
        base_url="https://provider.example.invalid/v1/",
        endpoint_path="generate",
        model_id="mock-structured-v1",
        api_key_env="TWINPULSE_PROVIDER_API_KEY",
        capabilities=ProviderCapabilities(images, True, 2 if images else 0),
        timeout_s=timeout_s,
    )


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_success_returns_validated_bundle(self) -> None:
        result = await GenerationService(MockProvider(), config()).generate(GenerationRequest("ok", "warehouse"))
        self.assertEqual(result.bundle.bundle_version, "1.0")
        self.assertGreater(len(result.plan.calls), 0)

    async def test_external_measurements_accept_matching_plan(self) -> None:
        request = GenerationRequest(
            "measured-ok",
            "warehouse",
            measurement_constraints=(
                MeasurementConstraint("floor_width", "create_floor", "size_m.0", 8.0, 0.01, 0),
                MeasurementConstraint("rack_height", "create_rack_row", "height_m", 1.5, 0.01),
            ),
        )
        result = await GenerationService(MockProvider(), config()).generate(request)
        self.assertEqual(result.measurement_constraint_count, 2)
        self.assertEqual(result.measurement_checked_value_count, 3)

    async def test_external_measurements_block_mismatched_plan(self) -> None:
        request = GenerationRequest(
            "measured-bad",
            "warehouse",
            measurement_constraints=(
                MeasurementConstraint("rack_height", "create_rack_row", "height_m", 3.0, 0.01),
            ),
        )
        with self.assertRaisesRegex(InvalidProviderResponseError, "rack_height:.*expected 3.*got 1.5"):
            await GenerationService(MockProvider(), config()).generate(request)

    def test_measurement_sidecar_loads_and_binds_to_image_name(self) -> None:
        image_path = Path("C:/drawings/plan.png")
        sidecar_path = measurement_sidecar_path(image_path)
        payload = json.dumps(
            {
                "schema_version": "1.0",
                "source_image": "plan.png",
                "measurement_constraints": [
                    {
                        "constraint_id": "floor_size",
                        "tool": "create_floor",
                        "argument_path": "size_m",
                        "expected": [12, 8],
                        "tolerance": 0.1,
                        "occurrence": 0,
                        "source": "trusted_test",
                    }
                ],
            }
        )
        with patch.object(Path, "read_text", return_value=payload):
            constraints = load_measurement_constraints(sidecar_path, image_path=image_path)
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0].expected, (12.0, 8.0))

    def test_measurement_sidecar_rejects_wrong_image_name(self) -> None:
        image_path = Path("C:/drawings/plan.png")
        sidecar_path = measurement_sidecar_path(image_path)
        payload = json.dumps(
            {
                "schema_version": "1.0",
                "source_image": "other.png",
                "measurement_constraints": [
                    {
                        "constraint_id": "floor_size",
                        "tool": "create_floor",
                        "argument_path": "size_m",
                        "expected": [12, 8],
                        "tolerance": 0.1,
                    }
                ],
            }
        )
        with patch.object(Path, "read_text", return_value=payload):
            with self.assertRaisesRegex(MeasurementConstraintError, "other.png, not plan.png"):
                load_measurement_constraints(sidecar_path, image_path=image_path)

    async def test_invalid_structure_is_rejected(self) -> None:
        service = GenerationService(MockProvider(MockMode.INVALID_STRUCTURE), config())
        with self.assertRaisesRegex(InvalidProviderResponseError, "Scene plan rejected:.*unexpected or missing"):
            await service.generate(GenerationRequest("bad", "warehouse"))

    async def test_timeout_is_typed_and_has_no_retry(self) -> None:
        service = GenerationService(MockProvider(MockMode.TIMEOUT), config(timeout_s=0.01))
        with self.assertRaises(ProviderTimeoutError):
            await service.generate(GenerationRequest("slow", "warehouse"))

    async def test_rate_limit_is_typed(self) -> None:
        service = GenerationService(MockProvider(MockMode.RATE_LIMIT), config())
        with self.assertRaises(ProviderRateLimitError):
            await service.generate(GenerationRequest("limited", "warehouse"))

    async def test_unsupported_image_is_rejected(self) -> None:
        request = GenerationRequest("image", "warehouse", (ImageInput("x.png", "image/png", b"x"),))
        with self.assertRaises(ProviderCapabilityError):
            await GenerationService(MockProvider(), config(images=False)).generate(request)

    async def test_cancelled_late_response_is_ignored(self) -> None:
        service = GenerationService(MockProvider(MockMode.LATE_SUCCESS, delay_s=0.03), config())
        task = asyncio.create_task(service.generate(GenerationRequest("late", "warehouse")))
        await asyncio.sleep(0.005)
        service.cancel_active()
        with self.assertRaises(GenerationCancelledError):
            await task

    def test_openai_responses_body_uses_image_and_strict_schema(self) -> None:
        provider = OpenAIResponsesProvider(lambda: "not-used", reasoning_effort="low")
        request = GenerationRequest(
            "request-1",
            "warehouse",
            (ImageInput("warehouse.png", "image/png", b"image-bytes"),),
        )
        body = provider.build_request_body(request, config())
        self.assertFalse(body["store"])
        self.assertEqual(body["reasoning"], {"effort": "low"})
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(body["text"]["format"]["name"], "twinpulse_scene_tool_plan")
        image = body["input"][0]["content"][0]
        self.assertEqual(image["type"], "input_image")
        self.assertTrue(image["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(image["detail"], "low")
        self.assertIn("primary evidence", body["instructions"])
        self.assertIn("0.7 meter wide clear corridor", body["instructions"])
        self.assertIn("passive support casters", body["instructions"])
        robot_schema = next(
            item
            for item in body["text"]["format"]["schema"]["properties"]["calls"]["items"]["anyOf"]
            if item["properties"]["tool"].get("const") == "place_predefined_agv"
        )
        self.assertEqual(
            robot_schema["properties"]["arguments"]["properties"]["profile_id"]["const"],
            "agv_compact_2wd_caster_v2",
        )
        task_schema = next(
            item
            for item in body["text"]["format"]["schema"]["properties"]["calls"]["items"]["anyOf"]
            if item["properties"]["tool"].get("const") == "create_navigation_task"
        )
        tolerance = task_schema["properties"]["arguments"]["properties"]["position_tolerance_m"]
        self.assertEqual(tolerance["minimum"], 0.01)
        self.assertEqual(tolerance["maximum"], 0.25)

    def test_dimensioned_plan_uses_high_image_detail(self) -> None:
        provider = OpenAIResponsesProvider(lambda: "not-used")
        request = GenerationRequest(
            "drawing-1",
            "Read this dimensioned top-down floor plan",
            (ImageInput("warehouse-floorplan.png", "image/png", b"image-bytes"),),
        )
        body = provider.build_request_body(request, config())
        self.assertEqual(body["input"][0]["content"][0]["detail"], "high")

    def test_openai_responses_parser_extracts_structured_json(self) -> None:
        expected = {"scene": {"id": "warehouse"}}
        payload = {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(expected)}]}
            ]
        }
        self.assertEqual(OpenAIResponsesProvider.parse_response(payload), expected)


if __name__ == "__main__":
    unittest.main()
