# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Two-stage Nebius Chat Completions pipeline with a testable transport boundary."""

from __future__ import annotations
from contextlib import nullcontext

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
import time
import socket
from threading import BoundedSemaphore
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.request

from twinpulse_core import SITE_TOOL_CATALOG_REVISION, WorldObservationRef, canonical_sha256, current_controller_route_prompt

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
from .schema import scene_tool_plan_json_schema, site_tool_plan_json_schema, site_proposal_json_schema
from .scene_contract import (SceneContractError, report as contract_report, issue as contract_issue,
    ROLES, lower_proposal, preflight_site, preflight_legacy_layout, require_valid, review_photo_relations)
from .reliability import safe_text, utc_now
from .output_diagnostics import MAX_STAGE_OUTPUT_TOKENS


OBSERVATION_SCHEMA_VERSION = "1.0"
NEBIUS_PIPELINE_VERSION = "1.2"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
from .scene_capacity import OBSERVATION_PAYLOAD_BYTES, checked_payload_bytes
MAX_OBSERVATION_ENTITIES = 24  # Historical wire-version marker only; not a count gate.
# Raw rows and expanded physical objects have different budgets. Match the
# existing scene designer's finite inventory without spending shell metadata.
MAX_OBSERVATION_OBJECT_INSTANCES = None  # Kept for historical audit imports.
MAX_DERIVED_OBSERVATION_ENTITIES = None
MAX_OBSERVATION_RELATIONS = 32
MAX_OBSERVATION_DIMENSIONS = 24
MAX_OBSERVATION_AMBIGUITIES = 12
# These workers are not asyncio's default executor: asyncio.run() otherwise
# waits for a cancelled blocking HTTP call before publishing the job timeout.
# Admission is bounded as well as execution; no queue of paid requests forms.
_INFERENCE_WORKERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="twinpulse-inference")
_INFERENCE_SLOTS = BoundedSemaphore(2)
_RELATIONS = frozenset({
    "left_of", "right_of", "in_front_of", "behind", "inside", "near",
    "parallel_to", "perpendicular_to", "aligned_with", "unknown",
})
_KINDS = frozenset({"floor", "wall", "rack", "pallet", "agv", "aisle", "marking", "other",
                    "robot_candidate", "static_obstacle", "free_space", "unknown"})
_DIMENSIONS = frozenset({"width", "length", "height", "clearance", "distance", "unknown"})


def observation_json_schema(version='1.0') -> dict[str, Any]:
    if version not in {'1.0','1.1','1.2'}:raise ValueError('Unsupported observation version')
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
    if version in {'1.1','1.2'}:
        from .photo_layout import KINDS, REGIONS
        entity['required'] += ['role','category','region','spatial_confidence']
        entity['properties'].update(role={'enum':list(ROLES)},
            category={'enum':sorted(set(KINDS)|{'floor','wall','opening','rack','pallet','agv','aisle','marking'})},
            region={'enum':[*REGIONS,'unknown']},spatial_confidence={'type':'number','minimum':0,'maximum':1})
    if version=='1.2':
        entity['required'].append('instance_count')
        entity['properties']['instance_count']={'type':['integer','null'],
            'minimum':1}
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
            "schema_version": {"const": version},
            "summary": {"type": "string", "maxLength": 1000},
            "entities": {"type": "array", "items": entity},
            "relations": {"type": "array", "items": relation},
            "dimensions": {"type": "array", "items": dimension},
            "ambiguities": {
                "type": "array",
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
    def from_mapping(cls, value: Mapping[str, Any], *, allow_derived=False) -> "ObservationArtifact":
        checked_payload_bytes(value, OBSERVATION_PAYLOAD_BYTES, 'OBSERVATION_PAYLOAD_BUDGET_REACHED')
        expected = {"schema_version", "summary", "entities", "relations", "dimensions", "ambiguities"}
        versions={'1.0','1.1','1.2'} | ({'1.3'} if allow_derived is True else set())
        if set(value) != expected or not isinstance(value.get('schema_version'),str) or value.get("schema_version") not in versions:
            raise InvalidProviderResponseError("observation has an unsupported shape or version")
        summary = value.get("summary")
        entities = value.get("entities")
        relations = value.get("relations")
        dimensions = value.get("dimensions")
        ambiguities = value.get("ambiguities")
        if not isinstance(summary, str) or len(summary) > 1000:
            raise InvalidProviderResponseError("observation summary is invalid")
        derived=value['schema_version']=='1.3'
        if not isinstance(entities, list):
            raise InvalidProviderResponseError("observation entities are invalid")
        if not isinstance(relations, list):
            raise InvalidProviderResponseError("observation relations are invalid")
        if not isinstance(dimensions, list):
            raise InvalidProviderResponseError("observation dimensions are invalid")
        if not isinstance(ambiguities, list) or any(
            not isinstance(item, str) or len(item) > 256 for item in ambiguities
        ):
            raise InvalidProviderResponseError("observation ambiguities are invalid")
        checked_entities: list[dict[str, Any]] = []
        ids: set[str] = set()
        # Return every independently recognizable role/category mismatch, not
        # only the first one. Repair must not guess which entity was rejected.
        if value['schema_version'] in {'1.1','1.2','1.3'}:
            semantic_issues=[]
            category_roles={'floor':'structure','wall':'structure','opening':'opening',
                'agv':'robot','aisle':'free_space','marking':'free_space'}
            for index,item in enumerate(entities):
                if not isinstance(item,Mapping) or not isinstance(item.get('category'),str):continue
                category=item['category'];role=item.get('role')
                if category=='unknown':continue
                allowed=(category_roles.get(category,'object'),'unknown')
                if isinstance(role,str) and role in ROLES and role not in allowed:
                    semantic_issues.append(contract_issue('OBSERVER_ROLE_CATEGORY_MISMATCH',
                        f'$.entities[{index}].role',entity_id=item.get('id'),category=category,
                        received_role=role,allowed_roles=list(allowed)))
            if semantic_issues:
                failure=InvalidProviderResponseError('observation role and category disagree')
                failure.code='OBSERVER_ROLE_CATEGORY_MISMATCH'
                failure.contract_report=contract_report(semantic_issues)
                raise failure
        for index, item in enumerate(entities):
            extra={'role','category','region','spatial_confidence'} if value['schema_version'] in {'1.1','1.2','1.3'} else set()
            if value['schema_version']=='1.2':extra=extra|{'instance_count'}
            if not isinstance(item, Mapping) or set(item) != {"id", "kind", "description", "confidence"}|extra:
                raise InvalidProviderResponseError("observation entity shape is invalid")
            if extra:
                from .photo_layout import KINDS, REGIONS
                if (any(not isinstance(item[k],str) for k in ('role','category','region'))
                        or item['role'] not in ROLES or item['category'] not in set(KINDS)|{'floor','wall','opening','rack','pallet','agv','aisle','marking'}
                        or item['region'] not in (*REGIONS,'unknown') or not _confidence(item['spatial_confidence'])):
                    raise InvalidProviderResponseError('observation semantic fields are invalid')
                if ((item['role']=='structure' and item['category'] not in {'floor','wall','unknown'})
                        or (item['role']=='opening' and item['category'] not in {'opening','unknown'})
                        or (item['role']=='free_space' and item['category'] not in {'aisle','marking','unknown'})
                        or (item['role']=='robot' and item['category'] not in {'agv','unknown'})
                        or (item['role']=='object' and item['category'] in {'floor','wall','opening','agv','aisle','marking'})):
                    raise InvalidProviderResponseError('observation role and category disagree')
            entity_id, kind, description, confidence = (
                item.get("id"), item.get("kind"), item.get("description"), item.get("confidence"),
            )
            if not _safe_id(entity_id) or entity_id in ids:
                failure = InvalidProviderResponseError('observation entity identity is invalid')
                failure.code = 'OBSERVER_ENTITY_ID_INVALID'
                failure.contract_report = contract_report([contract_issue(failure.code,f'$.entities[{index}].id')])
                raise failure
            if not isinstance(kind,str) or kind not in _KINDS:
                failure = InvalidProviderResponseError('observation entity kind is invalid')
                failure.code = 'OBSERVER_ENTITY_KIND_INVALID'
                failure.contract_report = contract_report([contract_issue(failure.code,f'$.entities[{index}].kind',
                    allowed=sorted(_KINDS))])
                raise failure
            if not isinstance(description, str) or len(description) > 256 or not _confidence(confidence):
                raise InvalidProviderResponseError("observation entity content is invalid")
            if value['schema_version']=='1.2':
                count=item['instance_count']
                if count is not None and (type(count) is not int or count < 1):
                    failure=InvalidProviderResponseError('OBSERVER_INSTANCE_COUNT_INVALID')
                    failure.code='OBSERVER_INSTANCE_COUNT_INVALID'
                    failure.contract_report=contract_report([contract_issue(failure.code,
                        f'$.entities[{index}].instance_count',expected={'positive_integer_or_unknown':True})])
                    raise failure
                # Counts of openings, markings or structures are observation
                # metadata too. Preserve them; only physical-object roles are
                # expanded into the furniture/obstacle inventory by the host.
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
            summary, tuple(checked_entities), tuple(checked_relations), tuple(checked_dimensions), tuple(ambiguities), value['schema_version'],
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
    attempt_id: str | None = None


class ChatCompletionsTransport(Protocol):
    async def complete(
        self, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion: ...


def _validation_code(error):
    """Bounded local reason code; never export exception text/model content."""
    code=getattr(error,'code',None)
    if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,80}',code):return code
    text=str(error)
    match=re.match(r'^(?:photo layout: |photo geometry: )?(PHOTO_[A-Z0-9_]{1,80})(?=[: ]|$)',text)
    if match:return match.group(1)
    if text=='Chat Completions output was truncated':return 'PROVIDER_OUTPUT_TRUNCATED'
    if 'response model does not match the requested model' in text:return 'PROVIDER_MODEL_MISMATCH'
    if 'not valid JSON' in text:return 'PROVIDER_JSON_INVALID'
    return 'PROVIDER_VALIDATION_FAILED'


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
        if not _INFERENCE_SLOTS.acquire(blocking=False):
            raise ProviderRequestError("Previous inference workers are still finishing; no request was dispatched")
        try:
            pending = _INFERENCE_WORKERS.submit(self._post, body, token, config, key)
        except BaseException:
            _INFERENCE_SLOTS.release()
            raise
        pending.add_done_callback(lambda _: _INFERENCE_SLOTS.release())
        return await asyncio.wrap_future(pending)

    def _post(
        self, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig, key: str,
    ) -> ChatCompletion:
        if token.is_cancelled:
            raise GenerationCancelledError("generation cancelled before dispatch")
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
            failure = ProviderRequestError(f"provider request failed ({error.code})")
            failure.http_status = error.code
            raise failure from error
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
        site_plan_version: str = "1.0",
        max_repairs: int = 0,
        planner_reasoning_effort: str | None = None,
        planner_template_no_thinking: bool = False,
        compact_photo_layout: bool = False,
        output_token_cap: int | None = None,
        stage_output_token_caps: dict[str, int] | None = None,
    ) -> None:
        if site_plan_version not in {"1.0", "2.0", "2.1", "2.2"}:
            raise ProviderConfigurationError("site plan version is unsupported")
        self._transport = transport
        self.observer_model_id = _model_id(observer_model_id, "observer")
        self.planner_model_id = _model_id(planner_model_id, "planner")
        self.fallback_observer_selected = bool(fallback_observer_selected)
        self.site_plan_version = site_plan_version
        if max_repairs not in (0, 1) or (max_repairs and site_plan_version != '2.2'):
            raise ProviderConfigurationError('One bounded repair is supported only for site 2.2')
        self.max_repairs = max_repairs
        if planner_reasoning_effort is not None and (
            planner_reasoning_effort != 'none' or site_plan_version != '2.2'
            or planner_model_id != 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
        ):
            raise ProviderConfigurationError('Explicit reasoning policy is restricted to the reviewed Nano Site2.2 planner')
        self.planner_reasoning_effort = planner_reasoning_effort
        if planner_template_no_thinking and (planner_reasoning_effort is not None
            or site_plan_version != '2.2' or planner_model_id not in
            ('nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B', 'nvidia/Nemotron-3_5-Lightning')):
            raise ProviderConfigurationError('Template policy is restricted to reviewed Nemotron Site2.2 planners')
        self.planner_template_no_thinking = planner_template_no_thinking
        if compact_photo_layout and (site_plan_version != '2.2' or planner_reasoning_effort is not None):
            raise ProviderConfigurationError('Compact photo experiment requires Site2.2 without reasoning_effort override')
        self.compact_photo_layout = compact_photo_layout
        if output_token_cap is not None and (type(output_token_cap) is not int or not 1 <= output_token_cap <= 10000):
            raise ProviderConfigurationError('Host output token cap must be an integer from 1 to 10000')
        self.output_token_cap = output_token_cap
        if stage_output_token_caps is not None and (
                not isinstance(stage_output_token_caps, dict) or set(stage_output_token_caps) != {'observer', 'planner'} or
                any(type(v) is not int or not 1 <= v <= MAX_STAGE_OUTPUT_TOKENS for v in stage_output_token_caps.values())):
            raise ProviderConfigurationError('Stage output limits must be integers from 1 to 40000')
        self.stage_output_token_caps = dict(stage_output_token_caps or {})
        self._diagnostic: dict[str, Any] = {}
        self._stage_started = 0.0

    def diagnostic_for(self, request_id: str) -> dict[str, Any]:
        """Metadata only: no prompts, images, credentials or response bodies."""
        if self._diagnostic.get("request_id") != request_id:
            return {}
        result = json.loads(json.dumps(self._diagnostic))
        if result.get("status") == "running":
            result["elapsed_s"] = round(time.monotonic()-self._stage_started, 3)
        return result

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
        text_only = not request.images and self.site_plan_version in {"2.0", "2.1", "2.2"}
        if len(request.images) != 1 and not text_only:
            raise ProviderCapabilityError("Nebius visual pipeline requires exactly one image")
        if (
            not config.capabilities.supports_structured_output
            or (not text_only and (not config.capabilities.supports_images or config.capabilities.max_images < 1))
        ):
            raise ProviderCapabilityError("Nebius visual pipeline capabilities are not enabled")
        image = request.images[0] if request.images else None
        if image and image.mime_type not in config.capabilities.accepted_mime_types:
            raise ProviderCapabilityError("image MIME type is not supported by the selected provider")
        compact = bool(self.compact_photo_layout and image)
        reference = None
        quality_constraints = None
        # No photo digest lookup, fixed inventory, reviewed pose or area limit.
        # Facts come from this request/observation; estimates may change on repair.
        state = {"request_id": request.request_id, "input_kind": "text" if text_only else "photo",
                 "repair_count": 0, "max_repairs": self.max_repairs, "attempts": [],
                 "started_at": utc_now(), "sequence": 0}
        self._diagnostic = state
        deadline = time.monotonic() + config.timeout_s
        observer = None
        if text_only:
            observation = ObservationArtifact.from_mapping({"schema_version": "1.0",
                "summary": "Text description only. No visual observations or measured geometry supplied.",
                "entities": [], "relations": [], "dimensions": [], "ambiguities": ["Geometry is illustrative, not measured."]})
        else:
            from .observation_instances import checked_observation_instances
            observer, observation = await self._validated_stage('observer', self.build_observer_body(request),
                lambda completion: checked_observation_instances(_json_content(completion, 'observer')),
                token, config, state, deadline)

        from .observation_instances import expand_observation_instances
        observation,instance_grounding=expand_observation_instances(observation)
        state['instance_grounding']=instance_grounding

        layout_provenance = {}

        def validate_planner(completion):
            for key in ('photo_quality','observed_photo_relations','scene_contract','site_proposal'):
                state.pop(key,None)
            layout_provenance.clear()
            raw_plan = _json_content(completion, 'planner')
            proposal = None
            if compact:
                from .photo_layout import compile_layout, PARAMETRIC_REVISION, GROUNDING_REVISION
                parametric=isinstance(raw_plan,Mapping) and raw_plan.get('layout_version') in (PARAMETRIC_REVISION,GROUNDING_REVISION)
                if reference is None:require_valid(preflight_legacy_layout(raw_plan,observation))
                try:
                    raw_plan, trace = compile_layout(raw_plan, observation, request, reference,
                        quality_constraints=quality_constraints)
                except (KeyError, TypeError, ValueError) as error:
                    failure = InvalidProviderResponseError('photo layout: '+safe_text(str(error),limit=400))
                    if getattr(error,'packing_report',None):
                        failure.packing_report=error.packing_report
                    if str(error).startswith('PHOTO_CONSTRAINTS_') or (not parametric and str(error).startswith('PHOTO_SUPPORT_')):
                        failure.repairable = False
                    raise failure from error
                layout_provenance.update(trace)
            elif self.site_plan_version=='2.2':
                raw_plan,proposal=lower_proposal(raw_plan)
                if proposal:state['site_proposal']=proposal
            if self.site_plan_version=='2.2':
                diagnosis=preflight_site(raw_plan,observation,request,proposal)
                state['scene_contract']=diagnosis
                require_valid(diagnosis)
            if self.site_plan_version in {'2.0', '2.1', '2.2'}:
                _validate_site_evidence(raw_plan, observation, request)
            payload = _flatten_required_call_slots(raw_plan) if self.site_plan_version == '1.0' else raw_plan
            if self.max_repairs:
                # The exact pure executor used by SiteDraftRecord must pass before
                # generation succeeds; syntax-only success hides placement faults.
                from twinpulse_core import site_tool_plan_from_json, execute_site_tool_plan
                try:
                    plan = site_tool_plan_from_json(json.dumps(payload))
                    execute_site_tool_plan(plan, source='photo' if image else 'manual',
                        source_ref=canonical_sha256({'prompt': request.prompt,
                            'image_sha256': hashlib.sha256(image.content).hexdigest() if image else None}))
                except (KeyError, TypeError, ValueError) as error:
                    raise InvalidProviderResponseError('calls: ' + safe_text(str(error), limit=400)) from error
            if image and self.site_plan_version == '2.2':
                from twinpulse_core.photo_quality import inspect_photo_geometry
                from .errors import PhotoQualityValidationError
                try:
                    report = inspect_photo_geometry(payload, hashlib.sha256(image.content).hexdigest(),
                        quality_constraints, support_repairable=not compact)
                except (KeyError, TypeError, ValueError) as error:
                    failure = InvalidProviderResponseError('photo geometry: '+safe_text(str(error), limit=400))
                    if str(error).startswith(('PHOTO_SUPPORT_', 'PHOTO_CONSTRAINTS_')):
                        failure.repairable = False
                    raise failure from error
                state['photo_quality'] = report
                if compact:layout_provenance['quality'] = report
                if not report['generation_allowed']:
                    raise PhotoQualityValidationError(report)
                frame=trace.get('coordinate_frame') if compact else proposal.get('coordinate_frame') if proposal else None
                relations=review_photo_relations(payload,observation,frame)
                state['observed_photo_relations']=relations
                if relations['issues']:raise SceneContractError(contract_report(relations['issues']))
                if compact:layout_provenance['observed_photo_relations']=relations
            return payload

        if compact:
            from .photo_layout import build_layout_body
            planner_body = build_layout_body(request, observation, self.planner_model_id, reference,
                quality_constraints=quality_constraints)
            planner_body['max_tokens'] = self.output_token_cap or 8000
            if self.planner_template_no_thinking:
                planner_body['chat_template_kwargs'] = {'enable_thinking': False}
        else:
            planner_body = self.build_planner_body(request, observation)
        planner, plan_payload = await self._validated_stage('planner', planner_body,
            validate_planner, token, config, state, deadline)
        provenance = {
            "pipeline_version": NEBIUS_PIPELINE_VERSION,
            "observer_model_id": self.observer_model_id,
            "planner_model_id": self.planner_model_id,
            "fallback_observer_selected": self.fallback_observer_selected,
            "observation_schema_version": observation.schema_version,
            "observation_sha256": observation.sha256,
            "source_observation_sha256": instance_grounding['source_observation_sha256'],
            "instance_grounding": instance_grounding,
            "input_kind": "text" if text_only else "photo",
            "input_image": {
                "mime_type": image.mime_type,
                "byte_count": len(image.content),
                "sha256": hashlib.sha256(image.content).hexdigest(),
            } if image else None,
            "stages": [
                *([_stage_receipt("observer", observer)] if observer else []),
                _stage_receipt("planner", planner),
            ],
            "reliability": {"repair_count": state['repair_count'], "attempts": state['attempts']},
            **({'photo_geometry_quality':state['photo_quality']} if 'photo_quality' in state else {}),
            **({'photo_layout_compiler':layout_provenance} if compact else {}),
            **({'site_proposal':state['site_proposal']} if 'site_proposal' in state else {}),
            **({'scene_contract':state['scene_contract']} if 'scene_contract' in state else {}),
            **({'observed_photo_relations':state['observed_photo_relations']} if 'observed_photo_relations' in state else {}),
        }
        return ProviderResponse(request.request_id, plan_payload, self.name, self.planner_model_id, provenance)

    async def _validated_stage(self, stage, original_body, validator, token, config, state, deadline):
        body = original_body
        previous_failed_hash=None
        while True:
            _ensure_current(token)
            completion = None
            try:
                completion = await self._complete_stage(stage, body, token, config)
                _ensure_current(token)
                trace=token.diagnostics
                with (trace.span(stage+'_validation',attempt_id=completion.attempt_id,
                                 finish_reason=completion.finish_reason) if trace else nullcontext()):
                    if completion.model_id != body['model']:
                        # Wrong identities must not be normalized or repaired.
                        failure = InvalidProviderResponseError(f'{stage} response model does not match the requested model')
                        failure.repairable = False
                        raise failure
                    if completion.finish_reason != 'stop':
                        failure = InvalidProviderResponseError('Chat Completions output was truncated' if completion.finish_reason=='length'
                                                               else 'Chat Completions finish reason is unsupported')
                        failure.repairable = False
                        if completion.finish_reason == 'length':
                            failure.code = 'PROVIDER_OUTPUT_TRUNCATED'
                        raise failure
                    try:
                        value = validator(completion)
                    except InvalidProviderResponseError as error:
                        error.code=_validation_code(error)
                        raise
                state.update(status='validated', validator='passed', sequence=state['sequence']+1)
                state['attempts'][-1].update(validation='passed')
                if 'photo_quality' in state:
                    state['attempts'][-1]['photo_quality'] = state['photo_quality']
                return completion, value
            except InvalidProviderResponseError as error:
                _ensure_current(token)
                # A length-limited response is rejected by the envelope parser,
                # but retain identity/content/usage as rejected evidence only.
                # Output exhaustion must stop, never trigger another call.
                completion = completion or getattr(error, 'partial_completion', None)
                if completion is not None and completion.model_id != body['model']:
                    error.code = 'PROVIDER_MODEL_MISMATCH'
                    error.repairable = False
                diagnosis=getattr(error,'contract_report',None) or contract_report([
                    contract_issue(_validation_code(error),'$')])
                candidate_hash=None
                if completion is not None:
                    try:candidate_hash=canonical_sha256(json.loads(completion.content))
                    except (ValueError,TypeError):pass
                if candidate_hash and candidate_hash==previous_failed_hash:
                    original_code=_validation_code(error)
                    diagnosis=contract_report([
                        *(diagnosis['issues'] if diagnosis else [contract_issue(original_code,'$')]),
                        contract_issue('REPAIR_NO_PROGRESS','$',candidate_sha256=candidate_hash)],
                        diagnosis.get('blocked_checks',[]) if diagnosis else [])
                    state['repair_no_progress']=True
                if candidate_hash:previous_failed_hash=candidate_hash
                if diagnosis:
                    state['scene_contract']=diagnosis
                    error.contract_report=diagnosis
                detail = safe_text(str(error), limit=400)
                code=_validation_code(error)
                if code == 'PROVIDER_OUTPUT_TRUNCATED':
                    error.repairable = False
                    state['stop_reason'] = 'output_limit_reached'
                state.update(status='validation_failed', validator=detail, validation_code=code,
                             sequence=state['sequence']+1)
                if state['attempts']:
                    state['attempts'][-1].update(validation='failed', validation_error=detail, validation_code=code)
                    if getattr(error, 'quality_report', None):
                        state['attempts'][-1]['photo_quality'] = error.quality_report
                    if getattr(error,'packing_report',None):
                        state['attempts'][-1]['layout_packing']=error.packing_report
                    if diagnosis:state['attempts'][-1]['scene_contract']=diagnosis
                    if candidate_hash:state['attempts'][-1]['candidate_sha256']=candidate_hash
                    if state.get('repair_no_progress'):state['attempts'][-1]['repair_no_progress']=True
                # Refusal/identity/envelope errors aren't repairable content failures.
                repairable = (getattr(error, 'repairable', True)
                              and (completion is not None or 'truncated' in detail or 'not valid JSON' in detail))
                if (not repairable or state.get('repair_no_progress') or state['repair_count'] >= self.max_repairs
                        or deadline-time.monotonic() < 5):
                    raise self._validation_failure(error, state) from error
                state['repair_count'] += 1
                state.update(status='repairing', sequence=state['sequence']+1)
                body = dict(original_body)
                body['messages'] = [*original_body['messages']]
                if completion is not None:
                    body['messages'].append({'role': 'assistant', 'content': safe_text(completion.content, limit=48000)})
                feedback = json.dumps({
                    'repair': 'Return one complete corrected JSON object, not a diff or explanation. This is the only repair attempt.',
                    'validation_error': detail,
                    **({'scene_contract':diagnosis,
                        'contract_repair':('Correct the observation data to the supplied observation schema, not the schema definition. '
                            'This stage observes the image only: no floor_call, tool calls, scene geometry or robot commands. '
                            'kind is the coarse observation enum; category is the reusable object catalogue enum. '
                            'Correct every reported field. Use distinct valid IDs for visible entities and fix their references. '
                            'Do not emit absent objects or change visible evidence just to pass. Keep unreadable metric dimensions null.'
                            if stage=='observer' else 'Correct ALL listed independent errors. Use the required floor_call slot. '
                            'Retain valid object identities; cite their own observed category/IDs, not another object. '
                            'Inventory IDs are object IDs, not observation IDs; use only provided observation identifiers. '
                            'A user-only source needs an exact user_request quote, not a fake visual reference. '
                            'Structure/opening/free_space are not furniture. Keep explicit measurements fixed; '
                            'all unmeasured room estimates and placements can change. '
                            'Checks marked blocked must still run on the corrected candidate. '
                            'Do not return the same failed candidate.')} if diagnosis else {}),
                    **({'layout_packing':error.packing_report,
                        'packing_repair':'Use these synthetic capacity diagnostics to revise crowded object regions. '
                            'Keep every observed object. Unmeasured room width/length and all inferred placements may be revised. '
                            'Reconsider already placed objects, respect explicit user dimensions and image relations. '
                            'This is not measured free space and the host must validate the corrected layout.'}
                       if getattr(error,'packing_report',None) else {}),
                    **({'geometry_quality':error.quality_report,
                        'geometry_repair':'Correct every listed position/height/attachment violation. Keep reviewed supports '
                            'and inventory; preserve explicit user dimensions, not an earlier estimated footprint. '
                            'Unmeasured width/length and centre may change on repair; '
                            'never change explicitly requested dimensions. '
                            'The host will recompile and recheck actual geometry; model self-acceptance has no authority.'}
                       if getattr(error, 'quality_report', None) else {}),
                    'constraints': ('Return only corrected visual observation JSON in the original observation schema. '
                        'Do not design or place a scene. Preserve visible evidence; correct invalid IDs, coarse kinds, '
                        'roles, categories, regions and references. Unknown dimensions stay null; no invented measurements.'
                        if stage=='observer' else
                        'Return the same compact layout schema, not tool calls or world coordinates. Preserve every inventory ID/category and observed ID and explicit user measurements. Unmeasured dimensions, poses and regions may change on repair. Correct invalid library dimensions/styles and explicit placement parent/part as required; retain reviewed supports and conservative floor hazards. No omissions or invented objects.'
                        if original_body.get('response_format',{}).get('json_schema',{}).get('name')=='twinpulse_compact_photo_layout' else
                        'Preserve original user requirements and observed IDs. No invented measurements, tools, robot authority or omitted requested objects. Compact English descriptions. Floor coordinates are centre-based; footprints must fit with 0.1m clearance and not overlap solids. Do not change an explicitly requested goal.')})
                if body['messages'][-1]['role'] == 'user':
                    # No usable response envelope: attach corrective feedback
                    # to the original user turn, preserving image parts. Do
                    # not invent an assistant response or emit user/user.
                    last = dict(body['messages'][-1])
                    content = last['content']
                    last['content'] = ([*content, {'type': 'text', 'text': feedback}]
                                       if isinstance(content, list) else content + '\n' + feedback)
                    body['messages'][-1] = last
                else:
                    body['messages'].append({'role': 'user', 'content': feedback})

    def _validation_failure(self, error: InvalidProviderResponseError, state=None) -> InvalidProviderResponseError:
        """Retain stage metadata when a completed response fails local validation."""
        diagnostic = state if state is not None else self._diagnostic
        diagnostic.update(status="validation_failed")
        failure = InvalidProviderResponseError(f"{diagnostic['stage']} stage response invalid: {error}")
        failure.diagnostics = json.loads(json.dumps(diagnostic))
        failure.code=_validation_code(error)
        if getattr(error,'contract_report',None):failure.contract_report=error.contract_report
        return failure

    async def _complete_stage(
        self, stage: str, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion:
        cap = self.stage_output_token_caps.get('observer' if stage in ('observer', 'render_review') else 'planner')
        if cap is not None:
            body = {**body, 'max_tokens': cap}
        trace = token.diagnostics
        if trace is None:
            return await self._complete_stage_impl(stage, body, token, config)
        with trace.span(stage, component='provider', model_id=body['model'], max_tokens=body['max_tokens']) as child:
            token.diagnostics = child
            try:
                return await self._complete_stage_impl(stage, body, token, config)
            finally:
                token.diagnostics = trace

    async def _complete_stage_impl(
        self, stage: str, body: Mapping[str, Any], token: CancellationToken, config: ProviderConfig,
    ) -> ChatCompletion:
        started = time.monotonic()
        diagnostic = self._diagnostic
        self._stage_started = started
        for key in ("finish_reason", "usage", "elapsed_s", "photo_quality"):
            diagnostic.pop(key, None)
        diagnostic.update(stage=stage, model_id=body["model"], max_tokens=body["max_tokens"], status="running")
        attempt = {"stage":stage,"model_id":body['model'],"max_tokens":body['max_tokens'],
                   "attempt":len(diagnostic.get('attempts',[]))+1, "started_at":utc_now(),
                   "repair": (getattr(token, 'generation_role', None) == 'repair'
                              if hasattr(token, 'generation_role') else bool(diagnostic.get('repair_count',0)))}
        if getattr(token, 'generation_role', None) in {'initial', 'repair', 'final_review'}:
            attempt['role'] = token.generation_role
        diagnostic.setdefault('attempts',[]).append(attempt)
        diagnostic['sequence']=diagnostic.get('sequence',0)+1
        try:
            result = await self._transport.complete(body, token, config)
            # Receipt/accounting exists even when cancellation makes the output
            # unusable. Preserve its identity BEFORE checking the host token.
            attempt.update(status='received', elapsed_s=round(time.monotonic()-started,3),
                           finish_reason=result.finish_reason,usage=dict(result.usage))
            if result.attempt_id:attempt['attempt_id']=result.attempt_id
            diagnostic.update(status="completed", elapsed_s=round(time.monotonic()-started, 3),
                                    finish_reason=result.finish_reason, usage=dict(result.usage))
            _ensure_current(token)
            return result
        except GenerationCancelledError as error:
            diagnostic.update(status='cancelled',elapsed_s=round(time.monotonic()-started,3))
            attempt.update(cancelled=True,ignored_by_host=True,error_type=type(error).__name__)
            if attempt.get('status')!='received':attempt['status']='cancelled'
            if getattr(error,'attempt_id',None):attempt['attempt_id']=error.attempt_id
            failure=GenerationCancelledError(f'{stage} stage cancelled; output ignored')
            if attempt.get('attempt_id'):failure.attempt_id=attempt['attempt_id']
            failure.receipt_known=attempt.get('status')=='received'
            failure.diagnostics=json.loads(json.dumps(diagnostic))
            raise failure from error
        except InvalidProviderResponseError as error:
            detail = " ".join(str(error).split()) or type(error).__name__
            if len(detail) > 240:
                detail = detail[:237] + "..."
            diagnostic.update(status="failed", elapsed_s=round(time.monotonic()-started, 3))
            attempt.update(status='rejected', error_type=type(error).__name__,elapsed_s=round(time.monotonic()-started,3))
            if getattr(error,'attempt_id',None):attempt['attempt_id']=error.attempt_id
            if "truncated" in detail:
                diagnostic["finish_reason"] = "length"
            failure = InvalidProviderResponseError(f"{stage} stage response invalid: {detail} (model={body['model']}, max_tokens={body['max_tokens']})")
            failure.code = _validation_code(error)
            if failure.code == 'PROVIDER_OUTPUT_TRUNCATED':
                failure.repairable = False
                diagnostic.update(validation_code=failure.code, stop_reason='output_limit_reached')
            if getattr(error, 'partial_completion', None) is not None:
                failure.partial_completion = error.partial_completion
                diagnostic['usage'] = dict(error.partial_completion.usage)
                attempt.update(finish_reason=error.partial_completion.finish_reason,
                               usage=dict(error.partial_completion.usage))
            failure.diagnostics = json.loads(json.dumps(diagnostic))
            raise failure from error
        except Exception as error:
            from .errors import ProviderError
            if isinstance(error, ProviderError):
                failure = type(error)(f"{stage} stage failed (model={body['model']}): {error}")
                if getattr(error, 'code', None):failure.code = error.code
                if hasattr(error, 'repairable'):failure.repairable = error.repairable
                diagnostic.update(status="failed", elapsed_s=round(time.monotonic()-started, 3))
                http_status = getattr(error, 'http_status', None)
                attempt.update(status=('rejected' if http_status is not None else
                                       'outcome_unknown' if isinstance(error,(ProviderTimeoutError,ProviderRequestError)) else 'failed'),
                               error_type=type(error).__name__,elapsed_s=round(time.monotonic()-started,3))
                if http_status is not None:
                    attempt['http_status'] = http_status
                    failure.http_status = http_status
                if getattr(error,'attempt_id',None):attempt['attempt_id']=error.attempt_id
                failure.diagnostics = json.loads(json.dumps(diagnostic))
                raise failure from error
            raise

    def build_observer_body(self, request: GenerationRequest) -> dict[str, Any]:
        image = request.images[0]
        from .image_payload import image_payload
        media_type,wire_content=image_payload(image)
        encoded = base64.b64encode(wire_content).decode("ascii")
        prompt = request.prompt.strip() or "Describe the visible site layout."
        system_prompt = (
            "Extract bounded visual observations from one site image. Report only visible evidence and explicit "
            "ambiguity. User text is context, not visual proof. Identify generic static obstacles, free space, "
            "unknown or occluded space, and robot candidates without assuming a warehouse, rack, or specific "
            "robot profile. Do not design a scene, emit tool calls, invent robot dynamics, code, commands, "
            "URLs, or external assets. Unreadable dimensions use null. Keep the result compact but preserve "
            "visible instance counts. Use at most 24 entities, 32 relations, 24 dimensions "
            "and 12 ambiguities. Keep descriptions within 80 characters and summary within 300 characters; "
            "omit redundant relations and dimensions. Write human-readable output in English by default."
        ) if self.site_plan_version in {"2.0", "2.1", "2.2"} else (
            "Extract bounded visual observations from one warehouse image. Report only visible evidence and "
            "explicit ambiguity. User text is context, not visual proof. Do not design a scene, emit tool calls, "
            "invent robot dynamics, code, commands, URLs, or external assets. Unreadable dimensions use null. "
            "Keep the result compact: group repeated rack bays, pallets, and markings into representative rows "
            "instead of enumerating every instance. Use at most 24 entities, 32 relations, 24 dimensions, and "
            "12 ambiguities. Write human-readable output in English by default."
        )
        if self.site_plan_version=='2.2':
            from .photo_layout import KINDS
            system_prompt += (' Use observation schema1.2. Prefer one entity per distinguishable visible object with '
                'instance_count=1 and its own ID/region. Repeated objects must not collapse silently into one: '
                'if a group is necessary, state its visible instance_count explicitly. Never infer a customary '
                'count (such as chairs per table). Unknown count uses null and an ambiguity. The total after '
                'Preserve all visible physical objects and separate structure/opening/free-space/robot metadata. '
                'There is no room-wide object-count quota. Do not reduce a genuine count to fit a processing batch. '
                'Check group counts against visible evidence; do not drop genuine visible objects merely to fit a limit. '
                'role distinguishes object, structure, opening, free_space, robot, unknown. '
                'Floor/walls are structure; a doorway aperture is opening, never door_leaf unless an actual door leaf is visible. '
                'Role/category compatibility: structure uses floor/wall/unknown; opening uses opening/unknown; '
                'free_space uses aisle/marking/unknown; robot uses agv/unknown. All reusable catalogue objects '
                '(including mounted window coverings or lights) use object, not structure or robot. '
                'A wheeled piece of furniture is not a robot merely because it has wheels. '
                'kind is a separate coarse enum, not the object category: ordinary furniture/objects use static_obstacle. '
                'For visible physical objects select category from the supplied reusable catalogue names; unidentified objects use unknown. '
                'Do not classify walls or floor as household objects. region is image-relative front=near camera, rear=far, '
                'left/right as seen by camera. Use unknown for ambiguous regions. spatial_confidence expresses confidence '
                'in region and spatial relations separately from object detection. No measured coordinates. '
                'Available categories: '+','.join(KINDS)+',floor,wall,opening,rack,pallet,agv,aisle,marking.')
        return {
            "model": self.observer_model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{media_type};base64,{encoded}",
                        "detail": _image_detail(request),
                    }},
                ]},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "twinpulse_image_observation", "strict": True,
                "schema": observation_json_schema('1.2' if self.site_plan_version=='2.2' else '1.0'),
            }},
            "temperature": 0,
            "max_tokens": self.output_token_cap or 4000,
        }

    def build_planner_body(
        self, request: GenerationRequest, observation: ObservationArtifact,
    ) -> dict[str, Any]:
        constraints = [item.to_dict() for item in request.measurement_constraints]
        if self.site_plan_version in {"2.0", "2.1", "2.2"}:
            from twinpulse_core.model_library import library_for_request
            content = json.dumps({
                "user_request": request.prompt,
                "visual_observation": observation.to_dict(),
                "trusted_measurement_constraints": constraints,
                **({'environment_model_library':library_for_request(request.prompt)} if self.site_plan_version=='2.2' else {}),
                **({'furniture_dimensions_at_zero_yaw_m':{
                    kind:dict(width_x_m=size[0],depth_y_m=size[1])
                    for kind,size in _furniture_footprints().items()}}
                    if self.site_plan_version=='2.2' else
                    {'furniture_footprints_at_zero_yaw_m':_furniture_footprints() if self.site_plan_version=='2.1' else {}}),
                "tool_catalog_revision": "site-tools-2.2" if self.site_plan_version == '2.2' else SITE_TOOL_CATALOG_REVISION,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return {
                "model": self.planner_model_id,
                "messages": [
                    {"role": "system", "content": (
                        f"Create a TwinPulse SiteToolPlan {self.site_plan_version} from visible evidence and explicit user constraints. "
                        + ("This is text-only input: the visual observation is empty. Build an illustrative approximate space from the description. Use user or inferred call_evidence with empty observation_ids, never visual or trusted_measurement. Estimate missing dimensions conservatively for SIM review, mark them approximate, and do not claim measurements, sensor data or physical safety. " if not request.images else "")
                        + "All catalogue lists and footprint tables are AVAILABLE OPTIONS, not objects in this room. Emit requested objects and visually observed objects only; never populate every catalogue entry. Preserve all explicitly requested objects. Footprint sizes are dimensions, NEVER coordinates for center_m. "
                        + "In call_evidence observation_ids, use ONLY IDs from visual_observation.entities. User-described objects have empty references; inferred objects may cite their uncertain observed identities. Do not invent visual references. "
                        + ('Return site-proposal-1.0 with required floor_call and matching floor_evidence; scene_calls excludes floor. '
                           'Use coordinate_frame photo_view_right_rear for photos (X=photo right,Y=rear), local_xy for text. '
                           'Each evidence has user_quote: user basis needs an exact quote of user_request and no visual references; '
                           'other bases use null user_quote. Visual objects cite their own category/ID, not a different object. '
                           'Inferred sources can cite unknown observed objects while acknowledging uncertainty. '
                           'Keep structure/opening/free_space separate from objects; preserve visible object coverage. '
                           'Unmeasured dimensions and placements may be revised together; retain explicit measurements. '
                           if self.site_plan_version=='2.2' else '')
                        + ("Use place_furniture with the pinned furniture-blocks-1.0 catalog for clearly identified bed, wardrobe, desk, chair, sofa, dining_table, and storage. Use rooms suited to the described home, not warehouse racks by default. Furniture is a parametric approximation, not a fetched photorealistic asset. " if self.site_plan_version in {'2.1','2.2'} else '') +
                        ("For Site2.2 new furniture prefer furniture-parametric-1.0: choose kind from environment_model_library, specify dimensions_m=[width_x,depth_y,height_z], variant and finish within that model's bounds. center_m is footprint centre on the floor; local front=-Y, yaw rotates around +Z. Regenerate whole model parts, never arbitrary mesh code or individual limb scaling. Use explicit user dimensions over defaults; missing dimensions are estimates, not measurements. Families are reusable options: home for household furniture, warehouse for racks/pallets, common for shared props. Preserve requested unusual objects even outside the inferred family. Warehouse rack size/bays/levels use create_rack_row; props use place_room_item dimensions_m. Legacy furniture-blocks-1.0 is fixed size and remains compatible. Never emit model_id as an unknown tool argument: use each entry's declared tool schema. " if self.site_plan_version=='2.2' else '') +
                        ("Use place_room_item with room-items-1.0 for every visible non-furniture object, including office_chair, floor_fan, clothes_rack, door_leaf, bag, box, basket, clothing_pile, hanging_clothes, bedding_overhang, cable_bundle, power_adapter, power_strip, small_equipment, monitor, tabletop_item, window_blind, ceiling_light and unknown. Preserve unknown objects rather than treating them as free space. Uncertain identities remain approximate, not measured. Cable, fabric and unknown objects produce separate conservative keepouts; these are synthetic risk envelopes, not measured geometry or LiDAR returns. Position and size are estimates unless explicit evidence supports them. observation_time_utc must be null unless a real observation timestamp was supplied; never invent freshness. Label objects in English. Inventory and approximate geometry do not authorize physical motion. " if self.site_plan_version=='2.2' else '') +
                        "create_floor center_m is the CENTRE, not the lower-left corner. size_m is X width and Y length. "
                        "For a floor centred at [0,0], positions can be negative: X is within +/-width/2 and Y within +/-length/2. "
                        "Keep complete furniture footprints inside these bounds with 0.1m clearance, account for rotated sizes, and avoid overlapping furniture/solid walls. "
                        "For place_room_item, position_m=[x,y,z] is its geometric centre, not its bottom: z >= dimensions_m[2]/2; a floor-standing item uses z=height/2. dimensions_m must be strictly positive. Cable/fabric/unknown keepouts extend another 0.1m in X and Y and must fit inside the floor. "
                        "Use the supplied catalog footprints, not invented furniture sizes. A chair must be outside a desk footprint, not underneath it. "
                        "Distinct furniture must not all be at [0,0]. Choose actual separate placement coordinates: for aligned boxes require abs(x1-x2) >= halfwidth1+halfwidth2 OR abs(y1-y2) >= halfdepth1+halfdepth2. "
                        "Check every centre arithmetically: abs(x-floor_x)+half_rotated_width+0.1 <= floor_width/2, "
                        "abs(y-floor_y)+half_rotated_depth+0.1 <= floor_depth/2. At yaw 90 swap footprint width/depth. "
                        "The chat product selects the existing Burger SIM asset separately; do not represent it with a marking, box, static object or unsupported profile. "
                        "Use only the schema and allowlisted scene tools. Create exactly one floor. Map each "
                        "tool call to its visual observation IDs or explicitly label user/inferred basis in "
                        "call_evidence; never fabricate an observation ID. For a non-rack obstacle, use "
                        "create_box_obstacle instead of forcing it into a warehouse rack or pallet. Do not model "
                        "unknown or occluded areas as confirmed free space. A photographed robot is only a "
                        "robot_candidate, not proof of the predefined drive profile. The driven robot and "
                        "navigation task are optional: omit both unless the user explicitly selected the demo "
                        "robot and mission. "
                        "Never claim an estimated scale is measured. Never invent a robot, goal, code, external asset, URL, or executable "
                        "command. Do not shift a requested destination. If the image is ambiguous, make a "
                        "conservative approximate scene for review. Keep IDs ASCII and unique, with one "
                        f"ordered calls array and plan_version {self.site_plan_version}. Write summaries, explanations, and other "
                        "human-readable values in English by default."
                    )},
                    {"role": "user", "content": content},
                ],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "twinpulse_site_tool_plan_v2", "strict": True,
                    "schema": site_proposal_json_schema(photo=bool(request.images)) if self.site_plan_version=='2.2' else site_tool_plan_json_schema(self.site_plan_version),
                }},
                "temperature": 0,
                "max_tokens": self.output_token_cap or 8000,
                **({'reasoning_effort':self.planner_reasoning_effort}
                   if self.planner_reasoning_effort is not None else {}),
                **({'chat_template_kwargs':{'enable_thinking':False}}
                   if self.planner_template_no_thinking else {}),
            }
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
                    "keep summary and image observations concise. Write human-readable values in English by default. "
                    "Every scene_id, call_id, object id, and task id must "
                    "start with an ASCII letter and contain only ASCII letters, digits, underscore, or hyphen; call_id "
                    "values must also be unique. "
                    f"{current_controller_route_prompt()}"
                    "Fill every required call slot exactly once: floor_call creates "
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
            "max_tokens": self.output_token_cap or 8000,
        }


def parse_chat_completion(payload: object) -> ChatCompletion:
    if not isinstance(payload, Mapping):
        raise InvalidProviderResponseError("Chat Completions payload must be an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise InvalidProviderResponseError("Chat Completions must contain exactly one choice")
    choice = choices[0]
    finish = choice.get("finish_reason")
    if not isinstance(finish, str) or finish not in {"stop", "length"}:
        raise InvalidProviderResponseError("Chat Completions finish reason is unsupported")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise InvalidProviderResponseError("Chat Completions message is missing")
    if message.get("refusal"):
        raise InvalidProviderResponseError("Chat Completions request was refused")
    content = message.get("content")
    if finish != 'length' and (not isinstance(content, str) or not content.strip()):
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
    completion = ChatCompletion(response_id, model_id, content if isinstance(content, str) else '', finish, usage)
    if finish == 'length':
        failure = InvalidProviderResponseError('Chat Completions output was truncated')
        failure.code = 'PROVIDER_OUTPUT_TRUNCATED'
        failure.repairable = False
        failure.partial_completion = completion
        raise failure
    return completion


def _furniture_footprints():
    from twinpulse_core.furniture import furniture_footprint, furniture_kinds
    # The catalogue origin is not necessarily the AABB centre (wardrobe doors
    # protrude on one side). Symmetric extents conservatively bound both sides.
    return {kind: list(furniture_footprint(kind)) for kind in furniture_kinds()}


def _json_content(completion: ChatCompletion, stage: str) -> Mapping[str, Any]:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                from .scene_contract import report, issue
                error = InvalidProviderResponseError(f'{stage} output repeats JSON key {key!r}')
                error.code = 'PROVIDER_JSON_DUPLICATE_KEY'
                error.duplicate_key = key
                error.contract_report = report([issue(error.code, '$', duplicate_key=key)])
                raise error
            result[key] = value
        return result
    try:
        # A keyed patch is not unique if a normal parser silently keeps the
        # last duplicate key. Reject ambiguity at every nesting level.
        value = json.loads(completion.content, object_pairs_hook=unique_keys)
    except json.JSONDecodeError as error:
        from .scene_contract import report, issue
        failure = InvalidProviderResponseError(f"{stage} output is not JSON at line {error.lineno}, column {error.colno}")
        failure.code = 'PROVIDER_JSON_INVALID'
        failure.contract_report = report([issue(failure.code, '$', line=error.lineno, column=error.colno)])
        raise failure from error
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


def _validate_site_evidence(
    value: Mapping[str, Any], observation: ObservationArtifact, request: GenerationRequest,
) -> None:
    """Reject invented visual references before the untrusted site plan is accepted."""

    evidence = value.get("call_evidence")
    if not isinstance(evidence, list):
        raise InvalidProviderResponseError("site plan is missing call evidence")
    observed_ref = WorldObservationRef.for_model_photo(
        observation.sha256, hashlib.sha256(request.images[0].content).hexdigest(),
        tuple(item["id"] for item in observation.entities),
    ) if request.images else None
    unknown_ids = {item["id"] for item in observation.entities if item["kind"] == "unknown" or item.get('role')=='unknown'}
    for item in evidence:
        if not isinstance(item, Mapping):
            raise InvalidProviderResponseError("site call evidence is invalid")
        refs = item.get("observation_ids")
        if not isinstance(refs, list):
            raise InvalidProviderResponseError("site observation references are invalid")
        try:
            if observed_ref is not None:
                observed_ref.require_visual_ids(refs)
            elif refs:
                raise ValueError("text input contains no visual observations")
        except ValueError as error:
            allowed=[entity['id'] for entity in observation.entities]
            invalid=[ref for ref in refs if ref not in allowed]
            raise InvalidProviderResponseError("site plan references an unobserved visual entity: "
                f"call={item.get('call_id')}, invalid={invalid[:4]}, allowed={allowed[:20]}; "
                "inventory IDs are object IDs, not observation IDs") from error
        if item.get("basis") == "visual":
            if not refs:
                raise InvalidProviderResponseError("visual scene evidence requires an observed entity")
            if any(ref in unknown_ids for ref in refs):
                raise InvalidProviderResponseError("unknown region cannot be cited as visible scene evidence")
        if item.get("basis") == "trusted_measurement" and not request.measurement_constraints:
            raise InvalidProviderResponseError("site plan claims a missing trusted measurement")


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
