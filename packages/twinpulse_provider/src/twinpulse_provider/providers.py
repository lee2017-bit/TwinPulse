"""Deterministic mock plus a credential-gated JSON/HTTPS adapter."""

from __future__ import annotations

import asyncio
import base64
from enum import Enum
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

from twinpulse_core import demo_warehouse_tool_plan

from .contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderResponse
from .errors import (
    GenerationCancelledError,
    InvalidProviderResponseError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
)
from .schema import scene_tool_plan_json_schema


class MockMode(str, Enum):
    SUCCESS = "success"
    INVALID_STRUCTURE = "invalid_structure"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    LATE_SUCCESS = "late_success"


class MockProvider:
    name = "TwinPulse Mock"

    def __init__(self, mode: MockMode = MockMode.SUCCESS, delay_s: float = 0.0) -> None:
        self.mode = mode
        self.delay_s = delay_s

    async def generate(
        self, request: GenerationRequest, token: CancellationToken, config: ProviderConfig
    ) -> ProviderResponse:
        if request.images and not config.capabilities.supports_images:
            raise ProviderCapabilityError("selected provider does not support image input")
        if len(request.images) > config.capabilities.max_images:
            raise ProviderCapabilityError("image count exceeds provider capability")
        if self.mode is MockMode.RATE_LIMIT:
            raise ProviderRateLimitError("mock rate limit")
        delay = self.delay_s if self.delay_s else (60.0 if self.mode is MockMode.TIMEOUT else 0.0)
        if delay:
            await asyncio.sleep(delay)
        if token.is_cancelled and self.mode is not MockMode.LATE_SUCCESS:
            raise GenerationCancelledError("generation cancelled")
        payload = {"unexpected": True} if self.mode is MockMode.INVALID_STRUCTURE else demo_warehouse_tool_plan().to_dict()
        return ProviderResponse(request.request_id, payload, self.name, config.model_id)


class StructuredJsonHttpProvider:
    """Real HTTPS transport for an explicitly configured TwinPulse JSON gateway.

    This deliberately does not guess a vendor-specific OpenAI-compatible shape.
    The gateway request/response contract must be verified before it is enabled.
    """

    name = "Structured JSON HTTPS"

    async def generate(
        self, request: GenerationRequest, token: CancellationToken, config: ProviderConfig
    ) -> ProviderResponse:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        if request.images and not config.capabilities.supports_images:
            raise ProviderCapabilityError("selected provider does not support image input")
        if len(request.images) > config.capabilities.max_images:
            raise ProviderCapabilityError("image count exceeds provider capability")
        if any(image.mime_type not in config.capabilities.accepted_mime_types for image in request.images):
            raise ProviderCapabilityError("image MIME type is not supported by the selected provider")
        if not config.capabilities.supports_structured_output:
            raise ProviderCapabilityError("selected provider has no verified structured-output capability")
        key = os.environ.get(config.api_key_env)
        if not key:
            raise ProviderConfigurationError(f"credential is not available in environment variable {config.api_key_env}")
        return await asyncio.to_thread(self._post, request, config, key, token)

    def _post(
        self, request: GenerationRequest, config: ProviderConfig, key: str, token: CancellationToken
    ) -> ProviderResponse:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        body = {
            "model": config.model_id,
            "input": {
                "text": request.prompt,
                "images": [
                    {
                        "name": image.name,
                        "mime_type": image.mime_type,
                        "data_base64": base64.b64encode(image.content).decode("ascii"),
                    }
                    for image in request.images
                ],
            },
            "response_format": {"type": "twinpulse_spec_bundle", "schema_version": request.schema_version},
        }
        raw = json.dumps(body).encode("utf-8")
        http_request = urllib.request.Request(
            config.endpoint_url(),
            data=raw,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=config.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise ProviderRateLimitError("provider rate limit") from error
            raise
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        if not isinstance(payload, dict):
            payload = {"invalid_payload": payload}
        return ProviderResponse(request.request_id, payload, self.name, config.model_id)


class OpenAIResponsesProvider:
    """Modern Responses adapter that asks a multimodal planner for allowlisted tool calls."""

    name = "OpenAI Responses"

    def __init__(self, api_key_getter: Callable[[], str | None], *, reasoning_effort: str = "low") -> None:
        self._api_key_getter = api_key_getter
        self._reasoning_effort = reasoning_effort

    async def generate(
        self, request: GenerationRequest, token: CancellationToken, config: ProviderConfig
    ) -> ProviderResponse:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        if request.images and not config.capabilities.supports_images:
            raise ProviderCapabilityError("selected provider does not support image input")
        if len(request.images) > config.capabilities.max_images:
            raise ProviderCapabilityError("image count exceeds provider capability")
        if any(image.mime_type not in config.capabilities.accepted_mime_types for image in request.images):
            raise ProviderCapabilityError("image MIME type is not supported by the selected provider")
        if not config.capabilities.supports_structured_output:
            raise ProviderCapabilityError("selected provider has no verified structured-output capability")
        key = self._api_key_getter() or os.environ.get(config.api_key_env)
        if not key:
            raise ProviderConfigurationError("API key is not configured")
        return await asyncio.to_thread(self._post, request, config, key, token)

    def build_request_body(self, request: GenerationRequest, config: ProviderConfig) -> dict:
        content: list[dict] = []
        image_detail = _resolve_image_detail(request)
        for image in request.images:
            encoded = base64.b64encode(image.content).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{image.mime_type};base64,{encoded}",
                    "detail": image_detail,
                }
            )
        user_text = request.prompt.strip() or (
            "Analyze the attached warehouse image and create an approximate runnable scene using the available tools."
        )
        content.append({"type": "input_text", "text": user_text})
        return {
            "model": config.model_id,
            "instructions": (
                "Act as a multimodal warehouse scene planner. When an image is present, use visible image structure as "
                "the primary evidence; user text adds explicit constraints and must not silently replace the image. "
                "Return an ordered plan using only these tools: create_floor, create_wall, create_rack_row, "
                "place_pallet_stack, create_aisle_marking, place_static_agv, place_predefined_agv, "
                "create_navigation_task. "
                "Use create_rack_row for visible multi-bay shelving rather than one solid rack box. Never emit code, "
                "commands, URLs, external assets, or unlisted tools. Treat scale as approximate unless dimensions are "
                "provided and keep the scene within 20 by 20 meters with at most 64 expanded objects. Use place_static_agv "
                "for additional AGVs visible in the photo; they are obstacles, not driven robots. Create exactly one driven "
                "agv_compact_2wd_caster_v2 and one navigation task. This vetted profile has two driven wheels and passive "
                "support casters; never invent wheel, caster, mass, inertia, or controller parameters. Plan the driven route "
                "before placing colliders. The current "
                "controller requires start z=0 and goal z=0, with the goal on the same y, 0.2 to 10 meters farther along "
                "positive X. Put that entire route inside one axis-aligned floor. Reserve at least a 0.7 meter wide clear "
                "corridor around it: no wall, rack, pallet, or static AGV may overlap from 0.35 meters before the start to "
                "0.35 meters beyond the goal. If the photographed center aisle is occupied, choose another visible clear "
                "aisle for the driven route. Use stable ASCII identifiers without spaces. Summarize visible evidence "
                "separately in image_observations."
            ),
            "input": [{"role": "user", "content": content}],
            "reasoning": {"effort": self._reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "twinpulse_scene_tool_plan",
                    "strict": True,
                    "schema": scene_tool_plan_json_schema(),
                }
            },
            "max_output_tokens": 8000,
            "store": False,
        }

    @staticmethod
    def parse_response(payload: object) -> dict:
        if not isinstance(payload, dict):
            raise InvalidProviderResponseError("Responses API payload must be an object")
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        try:
                            value = json.loads(text)
                        except json.JSONDecodeError as error:
                            raise InvalidProviderResponseError("Responses API output_text is not JSON") from error
                        if isinstance(value, dict):
                            return value
        raise InvalidProviderResponseError("Responses API returned no structured output_text")

    def _post(
        self, request: GenerationRequest, config: ProviderConfig, key: str, token: CancellationToken
    ) -> ProviderResponse:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        raw = json.dumps(self.build_request_body(request, config)).encode("utf-8")
        http_request = urllib.request.Request(
            config.endpoint_url(),
            data=raw,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=config.timeout_s) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ProviderAuthenticationError("provider rejected the API key") from error
            if error.code == 429:
                raise ProviderRateLimitError("provider rate limit") from error
            raise
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        bundle_payload = self.parse_response(response_payload)
        return ProviderResponse(request.request_id, bundle_payload, self.name, config.model_id)


def _resolve_image_detail(request: GenerationRequest) -> str:
    if request.image_detail != "auto":
        return request.image_detail
    cues = (
        "blueprint",
        "dimensioned",
        "floor plan",
        "floorplan",
        "top-down",
        "technical drawing",
        "도면",
        "평면도",
        "배치도",
    )
    searchable = " ".join((request.prompt, *(image.name for image in request.images))).lower()
    return "high" if any(cue in searchable for cue in cues) else "low"
