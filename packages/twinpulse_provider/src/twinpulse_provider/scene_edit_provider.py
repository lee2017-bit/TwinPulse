# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Structured, cost-free-to-construct provider boundary for saved-scene edits.

The caller must submit the returned proposal to the App's current-scene preview
gate. This module neither writes a project nor invokes a provider on import.
"""

from __future__ import annotations

import asyncio
import json
import math
from copy import deepcopy
from typing import Any, Mapping, Protocol

from twinpulse_core import canonical_sha256
from twinpulse_core.furniture import furniture_kinds, expand_furniture
from twinpulse_core.model_library import library_for_request
from twinpulse_core.tool_catalog import furniture_call_schema

from .contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderResponse
from .errors import GenerationCancelledError, InvalidProviderResponseError, ProviderTimeoutError

FEEDBACK_VERSION='scene-edit-proposal-1.1'
FEEDBACK_ATOMIC_EDIT_RULE=(
    'Within this patch, each target_id appears exactly once: emit one atomic final edit per object, '
    'not a sequence of intermediate edits or a second edit to preserve unchanged placement. '
    'For move/resize use one change with the complete final tool_call; unchanged placement and fields remain preserved implicitly. '
    'For resize plus reparent use one reparent edit with both the final tool_call and placement. '
    'Different explicit targets may share a patch. The same target may be edited again in a later reviewed revision.')


def feedback_proposal_json_schema(context=None):
    from twinpulse_core.tool_catalog import tool_call_schemas
    schemas=[s for s in tool_call_schemas('2.2') if s['properties']['tool'].get('const') not in
        {'place_predefined_agv','create_navigation_task'}]
    calls={'anyOf':schemas}
    text={'type':'string'};nullable={'anyOf':[text,{'type':'null'}]}
    placement=dict(type='object',additionalProperties=False,required=['id','relation','parent_id','part','anchor','elevation_m'],
        properties=dict(id=text,relation=dict(type='string',enum=['floor','surface','drape','wall','ceiling']),
            parent_id=nullable,part=nullable,anchor=dict(type='string',enum=['centre','front','left','right','rear']),
            elevation_m={'anyOf':[{'type':'number'},{'type':'null'}]}))
    edits=[]
    for action in ('change','add','restore','room','reparent','defer','remove'):
        fields=dict(action={'type':'string','enum':[action]},target_id={**text,
            'description':'Object identity: tool_call.arguments.id / inventory.id, NEVER tool_call.call_id.'},reason=text)
        if action in ('change','add','restore','room'):fields['tool_call']=calls
        if action in ('add','restore','reparent'):fields['placement']=placement
        edits.append(dict(type='object',additionalProperties=False,properties=fields,required=list(fields)))
        if action=='reparent':
            extra={**fields,'tool_call':calls}
            edits.append(dict(type='object',additionalProperties=False,properties=extra,required=list(extra)))
    if context is not None:
        # Host-owned identities are exact schema values, not strings the model
        # has to copy from prose. This does not repair or authorize its output.
        feedback_generation_request(context,'feedback-schema')
        current={c['arguments']['id']:c for c in context['current_plan']['calls']
            if c['tool'] not in {'place_predefined_agv','create_navigation_task'}}
        inventory={r['id']:r for r in context['inventory']}

        def bound_calls(identity,old=None,kind=None):
            variants=[]
            for original in schemas:
                tool=original['properties']['tool']['const']
                if old is not None and tool!=old['tool']:continue
                if old is None and tool in {'create_floor','create_wall'}:continue
                call=deepcopy(original);args=call['properties']['arguments']
                branches=args.get('anyOf',[args]);bound=[]
                for branch in branches:
                    props=branch['properties'];kind_schema=props.get('kind')
                    if kind is not None:
                        if kind_schema is None and old is None:continue
                        if kind_schema is not None:
                            allowed=kind_schema.get('enum',[kind_schema.get('const')])
                            if kind not in allowed:continue
                    branch=deepcopy(branch);branch['properties']['id']={'type':'string','enum':[identity]}
                    if kind_schema is not None and kind is not None:
                        branch['properties']['kind']={'type':'string','enum':[kind]}
                    bound.append(branch)
                if not bound:continue
                call['properties']['arguments']=bound[0] if len(bound)==1 else {'anyOf':bound}
                if old is not None:call['properties']['call_id']={'type':'string','enum':[old['call_id']]}
                variants.append(call)
            if not variants:raise ValueError('feedback target has no supported tool schema')
            return variants[0] if len(variants)==1 else {'anyOf':variants}

        edits=[]
        for action in ('change','restore','room','reparent','defer','remove'):
            targets=(sorted(i for i,c in current.items() if c['tool'] in {'create_floor','create_wall'})
                if action=='room' else sorted(i for i,r in inventory.items()
                    if (action in {'defer','remove'} or
                        action=='restore' and r['status']!='render_pending' or
                        action in {'change','reparent'} and r['status']=='render_pending' and i in current and
                            (action!='reparent' or current[i]['tool']=='place_room_item'))))
            for identity in targets:
                old=current.get(identity) or inventory.get(identity,{}).get('tool_call')
                kind=old['arguments'].get('kind') if old else inventory[identity]['kind']
                fields=dict(action={'type':'string','enum':[action]},target_id={'type':'string','enum':[identity],
                    'description':'Exact object ID, not the saved call_id.'},reason=text)
                if action in {'change','restore','room'}:fields['tool_call']=bound_calls(identity,old,kind)
                if action in {'restore','reparent'}:
                    fields['placement']=deepcopy(placement)
                    fields['placement']['properties']['id']={'type':'string','enum':[identity]}
                edits.append(dict(type='object',additionalProperties=False,properties=fields,required=list(fields)))
                if action=='reparent':
                    extra={**fields,'tool_call':bound_calls(identity,old,kind)}
                    edits.append(dict(type='object',additionalProperties=False,properties=extra,required=list(extra)))
        # New additions keep their separate new-identity contract. The App
        # still checks ID collisions, placement, geometry and dependency scope.
        fields=dict(action={'type':'string','enum':['add']},target_id={**text,
            'description':'New object ID equal to tool_call.arguments.id and placement.id; never call_id.'},reason=text,
            tool_call={'anyOf':[s for s in schemas if s['properties']['tool']['const'] not in {'create_floor','create_wall'}]},
            placement=placement)
        edits.append(dict(type='object',additionalProperties=False,properties=fields,required=list(fields)))
    patch=dict(type='object',additionalProperties=False,required=['patch_version','edits'],properties=dict(
        patch_version={'type':'string','enum':['scene-dependency-patch-1.0']},
        edits=dict(type='array',minItems=1,maxItems=16,description=FEEDBACK_ATOMIC_EDIT_RULE,items={'anyOf':edits})))
    return dict(type='object',additionalProperties=False,required=['schema_version','context_sha256','mode','explanation','patch'],
        properties=dict(schema_version={'type':'string','enum':[FEEDBACK_VERSION]},
            context_sha256={'type':'string','enum':[context['context_sha256']]} if context is not None else text,
            mode={'type':'string','enum':['clarify','dependency']},explanation=text,
            patch={'anyOf':[patch,{'type':'null'}]}))


def feedback_generation_request(context,request_id):
    from twinpulse_core.site_tools import SiteToolPlan
    keys={'schema_version','project_id','source_scene_revision','current_scene_revision','current_state_sha256',
        'request_text','original_user_intent','selected_call_id','current_plan','placement_contract','inventory','unresolved',
        'measurement_constraints','boundary','context_sha256'}
    if (not isinstance(context,Mapping) or set(context)!=keys or context['schema_version']!='scene-edit-context-1.2' or
            context['context_sha256']!=canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'}) or
            not isinstance(context['request_text'],str) or not 1<=len(context['request_text'].strip())<=4000 or
            not isinstance(request_id,str) or not request_id):raise ValueError('feedback context invalid')
    SiteToolPlan.from_dict(context['current_plan'])
    if context['placement_contract'] is not None:
        from twinpulse_core.photo_placement import checked_placement_contract
        checked_placement_contract(context['placement_contract'])
    prompt=json.dumps({**context,'environment_model_library':library_for_request(context['request_text'])},
        ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if len(prompt.encode('utf-8'))>128000:raise ValueError('feedback context too large')
    return GenerationRequest(request_id,prompt,schema_version=FEEDBACK_VERSION)


SCENE_EDIT_PROPOSAL_VERSION = "scene-edit-proposal-1.0"
SCENE_EDIT_CONTEXT_VERSION = "scene-edit-context-1.0"
_CONTEXT_KEYS = {"schema_version", "project_id", "source_scene_revision", "current_scene_revision",
                 "request_text", "selected_call_id", "furniture_calls", "scene_objects", "boundary",
                 "context_sha256"}
_PROPOSAL_KEYS = {"schema_version", "context_sha256", "mode", "explanation", "target_call_id", "tool_call"}


def scene_edit_proposal_json_schema() -> dict[str, Any]:
    """Strict output shape; the App remains the geometry and identity authority."""
    nullable_text = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    tool_call = furniture_call_schema(True)
    return {
        "type": "object", "additionalProperties": False,
        "required": sorted(_PROPOSAL_KEYS),
        "properties": {
            "schema_version": {"type": "string", "enum": [SCENE_EDIT_PROPOSAL_VERSION]},
            "context_sha256": {"type": "string"},
            "mode": {"type": "string", "enum": ["clarify", "add_furniture", "change_furniture"]},
            "explanation": {"type": "string"},
            "target_call_id": nullable_text,
            "tool_call": {"anyOf": [tool_call, {"type": "null"}]},
        },
    }


def scene_edit_generation_request(context: Mapping[str, Any], request_id: str) -> GenerationRequest:
    """Bind a current App context as untrusted JSON data, without source image bytes."""
    if isinstance(context,Mapping) and context.get('schema_version')=='scene-edit-context-1.2':
        return feedback_generation_request(context,request_id)
    extended=isinstance(context,Mapping) and context.get('schema_version')=='scene-edit-context-1.1'
    if not isinstance(context, Mapping) or set(context) != (_CONTEXT_KEYS|{'placement_contract'} if extended else _CONTEXT_KEYS):
        raise ValueError("scene edit context shape is unsupported")
    if context["schema_version"] not in (SCENE_EDIT_CONTEXT_VERSION,'scene-edit-context-1.1'):
        raise ValueError("scene edit context version is unsupported")
    if extended:
        from twinpulse_core.photo_placement import checked_placement_contract
        checked_placement_contract(context['placement_contract'])
    if (not all(isinstance(context[key], str) and context[key] for key in
                ("project_id", "source_scene_revision", "current_scene_revision", "boundary"))
            or not isinstance(context["request_text"], str)
            or not 1 <= len(context["request_text"].strip()) <= 2000
            or (context["selected_call_id"] is not None and not isinstance(context["selected_call_id"], str))):
        raise ValueError("scene edit context fields are invalid")
    calls, objects = context["furniture_calls"], context["scene_objects"]
    if not isinstance(calls, list) or not isinstance(objects, list) or len(calls) > 64 or len(objects) > 64:
        raise ValueError("scene edit context lists are invalid")
    for call in calls:
        if (not isinstance(call, dict) or set(call) != {"call_id", "tool", "arguments"}
                or not isinstance(call["call_id"], str) or call["tool"] != "place_furniture"
                or not isinstance(call["arguments"], dict)
                ):
            raise ValueError("scene edit furniture context is invalid")
        args = call["arguments"]
        center = args["center_m"]
        if (not isinstance(args["id"], str) or args["kind"] not in furniture_kinds()
                or not isinstance(center, list) or len(center) != 2
                or not all(type(number) in (int, float) and math.isfinite(number) for number in center)
                or type(args["yaw_deg"]) not in (int, float) or not math.isfinite(args["yaw_deg"])):
            raise ValueError("scene edit furniture arguments are invalid")
        expand_furniture(args)
    for item in objects:
        if (not isinstance(item, dict) or set(item) != {"id", "kind", "position_m", "dimensions_m"}
                or not isinstance(item["id"], str) or not isinstance(item["kind"], str)
                or not all(isinstance(item[key], list) and len(item[key]) == 3 and
                           all(type(number) in (int, float) and math.isfinite(number) for number in item[key])
                           for key in ("position_m", "dimensions_m"))):
            raise ValueError("scene edit object context is invalid")
    if context["context_sha256"] != canonical_sha256({key: value for key, value in context.items()
                                                        if key != "context_sha256"}):
        raise ValueError("scene edit context digest does not match")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("scene edit request id is required")
    prompt = json.dumps({**context,'environment_model_library':library_for_request(context['request_text']),
        'library_instructions':'Resize the whole selected model using furniture-parametric-1.0 dimensions_m, variant and finish. '
            'A legacy furniture-blocks-1.0 model may explicitly upgrade without changing id or kind. '
            'Proposals require preview/apply and cannot authorize physical motion.'},
        ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(prompt.encode("utf-8")) > 32_000:
        raise ValueError("scene edit context is too large")
    return GenerationRequest(request_id=request_id, prompt=prompt, schema_version=SCENE_EDIT_PROPOSAL_VERSION)


class SceneEditProvider(Protocol):
    async def generate(self, request: GenerationRequest, token: CancellationToken,
                       config: ProviderConfig) -> ProviderResponse: ...


class SceneEditProposalService:
    """One bounded call; never save, preview, Build, or retry on its own."""

    def __init__(self, provider: SceneEditProvider, config: ProviderConfig) -> None:
        self._provider = provider
        self._config = config

    async def propose(self, context: Mapping[str, Any], request_id: str, *, inference_scope=None,diagnostics=None,token=None) -> dict[str, Any]:
        from dataclasses import replace
        request = scene_edit_generation_request(context, request_id)
        request=replace(request,inference_scope=inference_scope,diagnostics=diagnostics)
        token = token or CancellationToken();token.diagnostics=diagnostics
        try:
            response = await asyncio.wait_for(self._provider.generate(request, token, self._config),
                                              timeout=self._config.timeout_s)
        except TimeoutError as error:
            token.cancel()
            raise ProviderTimeoutError("scene edit provider timed out") from error
        if token.is_cancelled or response.request_id != request_id:
            raise GenerationCancelledError("late or mismatched scene edit response was ignored")
        value = response.payload
        feedback=request.schema_version==FEEDBACK_VERSION
        keys={'schema_version','context_sha256','mode','explanation','patch'} if feedback else _PROPOSAL_KEYS
        if not isinstance(value, Mapping) or set(value) != keys:
            raise InvalidProviderResponseError("scene edit response shape is unsupported")
        if (value["schema_version"] != (FEEDBACK_VERSION if feedback else SCENE_EDIT_PROPOSAL_VERSION)
                or value["context_sha256"] != context["context_sha256"]):
            raise InvalidProviderResponseError("scene edit response belongs to a different context")
        # The App's checked_furniture_proposal and scene preview are still the
        # only authorities for target identity, valid geometry, and no-op edits.
        return dict(value)
