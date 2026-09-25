"""Two-stage Nebius Chat Completions pipeline with a testable transport boundary."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import hashlib
import json
import socket
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.request

from twinpulse_core import canonical_sha256

from .contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderResponse
from .errors import (
    GenerationCancelledError,
    InvalidProviderResponseError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .schema import scene_tool_plan_json_schema


OBSERVATION_SCHEMA_VERSION = "1.0"
NEBIUS_PIPELINE_VERSION = "1.2"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OBSERVATION_ENTITIES = 24
MAX_OBSERVATION_RELATIONS = 32
MAX_OBSERVATION_DIMENSIONS = 24
MAX_OBSERVATION_AMBIGUITIES = 12
_RELATIONS = frozenset({
    "left_of", "right_of", "in_front_of", "behind", "inside", "near",
    "parallel_to", "perpendicular_to", "aligned_with", "unknown",
})
_KINDS = frozenset({"floor", "wall", "rack", "pallet", "agv", "aisle", "marking", "other"})
_DIMENSIONS = frozenset({"width", "length", "height", "clearance", "distance", "unknown"})


def observation_json_schema() -> dict[str, Any]:
    entity = {
        "type": "object", "additionalProperties": False,
        "required": ["id", "kind", "description", "confidence"],
        "properties": {
            "id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
            "kind": {"type": "string", "enum": sorted(_KINDS)},
            "description": {"type": "string", "maxLength": 256},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    relation = {
        "type": "object", "additionalProperties": False,
        "required": ["subject_id", "relation", "object_id"],
        "properties": {
            "subject_id": {"type": "string", "maxLength": 64},
            "relation": {"type": "string", "enum": sorted(_RELATIONS)},
            "object_id": {"type": "string", "maxLength": 64},
        },
    }
    dimension = {
        "type": "object", "additionalProperties": False,
        "required": ["target_id", "dimension", "value_m", "confidence"],
        "properties": {
            "target_id": {"type": "string", "maxLength": 64},
            "dimension": {"type": "string", "enum": sorted(_DIMENSIONS)},
            "value_m": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 100},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    return {
        "type": "object", "additionalProperties": False,
        "required": ["schema_version", "summary", "entities", "relations", "dimensions", "ambiguities"],
        "properties": {
            "schema_version": {"const": OBSERVATION_SCHEMA_VERSION},
            "summary": {"type": "string", "maxLength": 1000},
            "entities": {"type": "array", "maxItems": MAX_OBSERVATION_ENTITIES, "items": entity},
            "relations": {"type": "array", "maxItems": MAX_OBSERVATION_RELATIONS, "items": relation},
            "dimensions": {"type": "array", "maxItems": MAX_OBSERVATION_DIMENSIONS, "items": dimension},
            "ambiguities": {
                "type": "array", "maxItems": MAX_OBSERVATION_AMBIGUITIES,
                "items": {"type": "string", "maxLength": 256},
            },
        },
    }


@dataclass(frozen=True, slots=True)
class ObservationArtifact:
    summary: str
    entities: tuple[Mapping[str, Any], ...]
    relations: tuple[Mapping[str, Any], ...]
    dimensions: tuple[Mapping[str, Any], ...]
    ambiguities: tuple[str, ...]
    schema_version: str = OBSERVATION_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ObservationArtifact":
        expected = {"schema_version", "summary", "entities", "relations", "dimensions", "ambiguities"}
        if set(value) != expected or value.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
            raise InvalidProviderResponseError("observation has an unsupported shape or version")
        summary = value.get("summary")
        entities = value.get("entities")
        relations = value.get("relations")
        dimensions = value.get("dimensions")
        ambiguities = value.get("ambiguities")
        if not isinstance(summary, str) or len(summary) > 1000:
            raise InvalidProviderResponseError("observation summary is invalid")
        if not isinstance(entities, list) or len(entities) > MAX_OBSERVATION_ENTITIES:
            raise InvalidProviderResponseError("observation entities are invalid")
        if not isinstance(relations, list) or len(relations) > MAX_OBSERVATION_RELATIONS:
            raise InvalidProviderResponseError("observation relations are invalid")
        if not isinstance(dimensions, list) or len(dimensions) > MAX_OBSERVATION_DIMENSIONS:
            raise InvalidProviderResponseError("observation dimensions are invalid")
        if not isinstance(ambiguities, list) or len(ambiguities) > MAX_OBSERVATION_AMBIGUITIES or any(
            not isinstance(item, str) or len(item) > 256 for item in ambiguities
        ):
            raise InvalidProviderResponseError("observation ambiguities are invalid")
        checked_entities: list[dict[str, Any]] = []
        ids: set[str] = set()
        for item in entities:
            if not isinstance(item, Mapping) or set(item) != {"id", "kind", "description", "confidence"}:
                raise InvalidProviderResponseError("observation entity shape is invalid")
            entity_id, kind, description, confidence = (
                item.get("id"), item.get("kind"), item.get("description"), item.get("confidence"),
            )
            if not _safe_id(entity_id) or entity_id in ids or kind not in _KINDS:
                raise InvalidProviderResponseError("observation entity identity is invalid")
            if not isinstance(description, str) or len(description) > 256 or not _confidence(confidence):
                raise InvalidProviderResponseError("observation entity content is invalid")
            ids.add(entity_id)
            checked_entities.append(dict(item))
        checked_relations: list[dict[str, Any]] = []
        for item in relations:
            if not isinstance(item, Mapping) or set(item) != {"subject_id", "relation", "object_id"}:
                raise InvalidProviderResponseError("observation relation shape is invalid")
            if item.get("subject_id") not in ids or item.get("object_id") not in ids or item.get("relation") not in _RELATIONS:
                raise InvalidProviderResponseError("observation relation reference is invalid")
            checked_relations.append(dict(item))
        checked_dimensions: list[dict[str, Any]] = []
        for item in dimensions:
            if not isinstance(item, Mapping) or set(item) != {"target_id", "dimension", "value_m", "confidence"}:
                raise InvalidProviderResponseError("observation dimension shape is invalid")
            raw = item.get("value_m")
            if item.get("target_id") not in ids or item.get("dimension") not in _DIMENSIONS:
                raise InvalidProviderResponseError("observation dimension target is invalid")
            if raw is not None and (isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 < raw <= 100):
                raise InvalidProviderResponseError("observation dimension value is invalid")
            if not _confidence(item.get("confidence")):
                raise InvalidProviderResponseError("observation dimension confidence is invalid")
            checked_dimensions.append(dict(item))
        return cls(
            summary, tuple(checked_entities), tuple(checked_relations), tuple(checked_dimensions), tuple(ambiguities),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "summary": self.summary,
            "entities": [dict(item) for item in self.entities],
            "relations": [dict(item) for item in self.relations],
            "dimensions": [dict(item) for item in self.dimensions],
            "ambiguities": list(self.ambiguities),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    response_id: str
    model_id: str
    content: str
    finish_reason: str
    usage: Mapping[str, int]


class ChatCompletionsTransport(Protocol):
    async def complete(
        self, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion: ...


class UrllibChatCompletionsTransport:
    """Credential-gated transport. Tests inject an opener; no logging is performed."""

    def __init__(
        self, api_key_getter: Callable[[], str | None],
        *, opener: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key_getter = api_key_getter
        self._opener = opener or urllib.request.build_opener(_RejectRedirects()).open

    async def complete(
        self, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled")
        key = self._api_key_getter()
        if not key:
            raise ProviderConfigurationError("API key is not configured")
        return await asyncio.to_thread(self._post, body, token, config, key)

    def _post(
        self, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig, key: str,
    ) -> ChatCompletion:
        endpoint = config.endpoint_url()
        request = urllib.request.Request(
            endpoint, data=json.dumps(body, separators=(",", ":")).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with self._opener(request, timeout=config.timeout_s) as response:
                if response.geturl() != endpoint:
                    raise ProviderRequestError("provider redirect was rejected")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ProviderAuthenticationError("provider rejected the API key") from error
            if error.code == 429:
                raise ProviderRateLimitError("provider rate limit") from error
            if 300 <= error.code < 400:
                raise ProviderRequestError("provider redirect was rejected") from error
            if 500 <= error.code < 600:
                raise ProviderUnavailableError(f"provider unavailable ({error.code})") from error
            raise ProviderRequestError(f"provider request failed ({error.code})") from error
        except (TimeoutError, socket.timeout) as error:
            raise ProviderTimeoutError("provider transport timed out") from error
        except urllib.error.URLError as error:
            raise ProviderRequestError("provider connection failed") from error
        if token.is_cancelled:
            raise GenerationCancelledError("late or cancelled response was ignored")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise InvalidProviderResponseError("provider response exceeds size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidProviderResponseError("Chat Completions response is not valid JSON") from error
        return parse_chat_completion(payload)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


class NebiusChatCompletionsPipelineProvider:
    def __init__(
        self,
        transport: ChatCompletionsTransport,
        *,
        observer_model_id: str,
        planner_model_id: str,
        fallback_observer_selected: bool = False,
    ) -> None:
        self._transport = transport
        self.observer_model_id = _model_id(observer_model_id, "observer")
        self.planner_model_id = _model_id(planner_model_id, "planner")
        self.fallback_observer_selected = bool(fallback_observer_selected)

    @property
    def name(self) -> str:
        return f"Nebius {self.observer_model_id} observation + {self.planner_model_id} planning"

    async def generate(
        self, request: GenerationRequest, token: CancellationToken, config: ProviderConfig,
    ) -> ProviderResponse:
        config.endpoint_url()
        if config.endpoint_path.strip("/") != "chat/completions":
            raise ProviderConfigurationError("Nebius pipeline requires the Chat Completions endpoint")
        if config.model_id != self.planner_model_id:
            raise ProviderConfigurationError("configured model id does not match the Nebius planner model")
        if len(request.images) != 1:
            raise ProviderCapabilityError("Nebius visual pipeline requires exactly one image")
        if (
            not config.capabilities.supports_images
            or not config.capabilities.supports_structured_output
            or config.capabilities.max_images < 1
        ):
            raise ProviderCapabilityError("Nebius visual pipeline capabilities are not enabled")
        image = request.images[0]
        if image.mime_type not in config.capabilities.accepted_mime_types:
            raise ProviderCapabilityError("image MIME type is not supported by the selected provider")
        observer = await self._complete_stage("observer", self.build_observer_body(request), token, config)
        _ensure_current(token)
        if observer.model_id != self.observer_model_id:
            raise InvalidProviderResponseError("observer response model does not match the requested model")
        observation = ObservationArtifact.from_mapping(_json_content(observer, "observer"))
        planner = await self._complete_stage(
            "planner", self.build_planner_body(request, observation), token, config,
        )
        _ensure_current(token)
        if planner.model_id != self.planner_model_id:
            raise InvalidProviderResponseError("planner response model does not match the requested model")
        plan_payload = _flatten_required_call_slots(_json_content(planner, "planner"))
        provenance = {
            "pipeline_version": NEBIUS_PIPELINE_VERSION,
            "observer_model_id": self.observer_model_id,
            "planner_model_id": self.planner_model_id,
            "fallback_observer_selected": self.fallback_observer_selected,
            "observation_schema_version": observation.schema_version,
            "observation_sha256": observation.sha256,
            "input_image": {
                "mime_type": image.mime_type,
                "byte_count": len(image.content),
                "sha256": hashlib.sha256(image.content).hexdigest(),
            },
            "stages": [
                _stage_receipt("observer", observer),
                _stage_receipt("planner", planner),
            ],
        }
        return ProviderResponse(request.request_id, plan_payload, self.name, self.planner_model_id, provenance)

    async def _complete_stage(
        self, stage: str, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion:
        try:
            return await self._transport.complete(body, token, config)
        except InvalidProviderResponseError as error:
            detail = " ".join(str(error).split()) or type(error).__name__
            if len(detail) > 240:
                detail = detail[:237] + "..."
            raise InvalidProviderResponseError(f"{stage} stage response invalid: {detail}") from error

    def build_observer_body(self, request: GenerationRequest) -> dict[str, Any]:
        image = request.images[0]
        encoded = base64.b64encode(image.content).decode("ascii")
        prompt = request.prompt.strip() or "Describe the visible warehouse layout."
        return {
            "model": self.observer_model_id,
            "messages": [
                {"role": "system", "content": (
                    "Extract bounded visual observations from one warehouse image. Report only visible evidence and "
                    "explicit ambiguity. User text is context, not visual proof. Do not design a scene, emit tool calls, "
                    "invent robot dynamics, code, commands, URLs, or external assets. Unreadable dimensions use null. "
                    "Keep the result compact: group repeated rack bays, pallets, and markings into representative rows "
                    "instead of enumerating every instance. Use at most 24 entities, 32 relations, 24 dimensions, and "
                    "12 ambiguities."
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{image.mime_type};base64,{encoded}",
                        "detail": _image_detail(request),
                    }},
                ]},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "twinpulse_image_observation", "strict": True,
                "schema": observation_json_schema(),
            }},
            "temperature": 0,
            "max_tokens": 4000,
        }

    def build_planner_body(
        self, request: GenerationRequest, observation: ObservationArtifact,
    ) -> dict[str, Any]:
        constraints = [item.to_dict() for item in request.measurement_constraints]
        content = json.dumps({
            "user_request": request.prompt,
            "visual_observation": observation.to_dict(),
            "trusted_measurement_constraints": constraints,
            "robot_profile_id": "agv_compact_2wd_caster_v2",
            "tool_catalog_revision": "scene-tools-1.0",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "model": self.planner_model_id,
            "messages": [
                {"role": "system", "content": (
                    "Create the complete ordered TwinPulse SceneToolPlan. You make the material geometry, placement, "
                    "predefined-AGV, and navigation-task decisions. Use only the supplied schema and catalog. Preserve "
                    "evidence attribution; trusted constraints override visual estimates. Never emit code, commands, URLs, "
                    "external assets, unlisted tools, or robot dynamics. Produce exactly one driven predefined 2WD AGV "
                    "and one supported positive-X navigation task with a collision-free clear corridor. Prefer compact "
                    "row and repetition tools over one call per visible item; target at most 14 ordered tool calls and "
                    "keep summary and image observations concise. Every scene_id, call_id, object id, and task id must "
                    "start with an ASCII letter and contain only ASCII letters, digits, underscore, or hyphen; call_id "
                    "values must also be unique. Keep the AGV start and goal on z=0 with equal y coordinates, put the "
                    "goal 0.2 to 10 meters farther along positive X, keep that route inside the floor, and leave the full "
                    "AGV-width corridor free of colliders. Fill every required call slot exactly once: floor_call creates "
                    "the only floor, scene_calls contains only optional static scene content, agv_call places the driven "
                    "predefined 2WD AGV, and navigation_call creates its one navigation task. Treat the AGV start and "
                    "goal as a candidate route: TwinPulse will preserve it when safe or deterministically move it to a "
                    "free horizontal corridor before accepting and storing the final plan."
                )},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "twinpulse_scene_tool_plan", "strict": True,
                "schema": scene_tool_plan_json_schema(required_call_slots=True),
            }},
            "temperature": 0,
            "max_tokens": 8000,
        }


def parse_chat_completion(payload: object) -> ChatCompletion:
    if not isinstance(payload, Mapping):
        raise InvalidProviderResponseError("Chat Completions payload must be an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise InvalidProviderResponseError("Chat Completions must contain exactly one choice")
    choice = choices[0]
    finish = choice.get("finish_reason")
    if finish == "length":
        raise InvalidProviderResponseError("Chat Completions output was truncated")
    if finish != "stop":
        raise InvalidProviderResponseError("Chat Completions finish reason is unsupported")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise InvalidProviderResponseError("Chat Completions message is missing")
    if message.get("refusal"):
        raise InvalidProviderResponseError("Chat Completions request was refused")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise InvalidProviderResponseError("Chat Completions content is missing")
    response_id = payload.get("id")
    model_id = payload.get("model")
    if not isinstance(response_id, str) or not response_id or len(response_id) > 256:
        raise InvalidProviderResponseError("Chat Completions response id is invalid")
    if not isinstance(model_id, str) or not model_id or len(model_id) > 256:
        raise InvalidProviderResponseError("Chat Completions model id is invalid")
    usage_raw = payload.get("usage", {})
    if not isinstance(usage_raw, Mapping):
        raise InvalidProviderResponseError("Chat Completions usage is invalid")
    usage: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage_raw.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidProviderResponseError("Chat Completions usage is invalid")
            usage[key] = value
    return ChatCompletion(response_id, model_id, content, finish, usage)


def _json_content(completion: ChatCompletion, stage: str) -> Mapping[str, Any]:
    try:
        value = json.loads(completion.content)
    except json.JSONDecodeError as error:
        raise InvalidProviderResponseError(f"{stage} output is not JSON") from error
    if not isinstance(value, Mapping):
        raise InvalidProviderResponseError(f"{stage} output must be a JSON object")
    return value


def _flatten_required_call_slots(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = {
        "plan_version", "scene_id", "summary", "image_observations",
        "floor_call", "scene_calls", "agv_call", "navigation_call",
    }
    if set(value) != expected:
        raise InvalidProviderResponseError("planner output has unexpected or missing call slots")
    scene_calls = value.get("scene_calls")
    if not isinstance(scene_calls, list) or len(scene_calls) > 20:
        raise InvalidProviderResponseError("planner scene_calls are invalid")
    calls = [value.get("floor_call"), *scene_calls, value.get("agv_call"), value.get("navigation_call")]
    if any(not isinstance(item, Mapping) for item in calls):
        raise InvalidProviderResponseError("planner required call slot is invalid")
    return {
        "plan_version": value["plan_version"],
        "scene_id": value["scene_id"],
        "summary": value["summary"],
        "image_observations": value["image_observations"],
        "calls": [dict(item) for item in calls],
    }


def _stage_receipt(role: str, completion: ChatCompletion) -> dict[str, Any]:
    return {
        "role": role,
        "request_id": completion.response_id,
        "model_id": completion.model_id,
        "finish_reason": completion.finish_reason,
        "usage": dict(completion.usage),
    }


def _safe_id(value: object) -> bool:
    return bool(
        isinstance(value, str) and 1 <= len(value) <= 64 and value[0].isalpha()
        and all(character.isalnum() or character in "_-" for character in value)
        and value.isascii()
    )


def _confidence(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 1


def _model_id(value: str, role: str) -> str:
    result = value.strip()
    if not result or len(result) > 256 or any(ord(character) < 32 for character in result):
        raise ProviderConfigurationError(f"{role} model id is invalid")
    return result


def _ensure_current(token: CancellationToken) -> None:
    if token.is_cancelled:
        raise GenerationCancelledError("late or cancelled response was ignored")


def _image_detail(request: GenerationRequest) -> str:
    if request.image_detail != "auto":
        return request.image_detail
    text = " ".join((request.prompt, *(item.name for item in request.images))).lower()
    return "high" if any(cue in text for cue in ("floorplan", "floor plan", "drawing", "도면", "평면도")) else "low"
