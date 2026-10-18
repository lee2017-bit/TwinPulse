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
import time
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


def normalized_feedback_patch(context, patch):
    """One unambiguous final edit, never last-write-wins or a scope expansion.

    Raw model response stays in transport evidence. Combine only the common
    split change+reparent representation using this exact frozen context.
    Other duplicates and conflicting replacement calls still fail closed.
    """
    if not isinstance(patch,dict) or not isinstance(patch.get('edits'),list):return deepcopy(patch)
    patch=deepcopy(patch)
    current={c['arguments']['id']:c for c in context['current_plan']['calls']}
    def same_json(a,b):
        if type(a) in (int,float) and type(b) in (int,float):return math.isfinite(a) and math.isfinite(b) and a==b
        if type(a)!=type(b):return False
        if isinstance(a,dict):return a.keys()==b.keys() and all(same_json(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(same_json(x,y) for x,y in zip(a,b))
        return a==b
    for edit in patch['edits']:
        if not isinstance(edit,dict):continue
        old=current.get(edit.get('target_id'));call=edit.get('tool_call')
        if edit.get('action')=='add' and isinstance(call,dict) and call.get('tool')=='place_library_asset':
            raise InvalidProviderResponseError('FEEDBACK_LIBRARY_ADD_REQUIRES_EXPLICIT_LIBRARY_PLACEMENT')
        if edit.get('action')=='add' and isinstance(call,dict) and call.get('tool')=='place_model_recipe':
            # This is admission of a NEW instance, not pinned historical replay.
            # Old compiler snapshots remain reproducible but cannot bypass the
            # independent default/corner and exact-instance reuse checks here.
            from twinpulse_core.model_recipe import (checked_recipe,recipe_reuse_problem,
                compiled_parts,checked_assembly,ModelRecipeError)
            try:
                args=call.get('arguments',{})
                recipe=checked_recipe(args.get('recipe'))
                problem=recipe_reuse_problem(recipe)
                if problem:raise InvalidProviderResponseError('FEEDBACK_RECIPE_REUSE_INVALID: '+problem)
                checked_assembly(compiled_parts(recipe,args.get('parameters')),args.get('parameters'))
            except ModelRecipeError as error:
                raise InvalidProviderResponseError('FEEDBACK_RECIPE_REUSE_INVALID: '+str(error)) from error
        if old is None and edit.get('action')=='restore':
            retained=next((r for r in context['inventory'] if r['id']==edit.get('target_id')
                and r['status'] in {'deferred','removed'}),None)
            if retained is not None:old=retained.get('tool_call')
        if old and old['tool']=='place_library_asset' and isinstance(call,dict):
            args=call.get('arguments')
            if not isinstance(args,dict):raise InvalidProviderResponseError('FEEDBACK_ASSET_ARGUMENTS_INVALID')
            snapshot=old['arguments']['snapshot']
            if (call.get('tool')!=old['tool'] or call.get('call_id')!=old['call_id'] or
                    args.get('id')!=old['arguments']['id'] or
                    set(args)-{'id','asset_version','snapshot','position_m','yaw_deg'}):
                raise InvalidProviderResponseError('FEEDBACK_ASSET_PIN_CHANGED')
            # Normalization is invoked again by the App before preview. Accept
            # exact pinned host replay idempotently, never a new model snapshot.
            version=args.pop('asset_version',snapshot['version'] if 'snapshot' in args else None)
            if version!=snapshot['version']:raise InvalidProviderResponseError('FEEDBACK_ASSET_PIN_CHANGED')
            if 'snapshot' in args and not same_json(args['snapshot'],snapshot):
                raise InvalidProviderResponseError('FEEDBACK_ASSET_DEFINITION_CHANGED')
            args['snapshot']=deepcopy(snapshot)
            continue
        if not old or old['tool']!='place_model_recipe' or not isinstance(call,dict):continue
        args=call.get('arguments')
        if not isinstance(args,dict):continue
        if (call.get('tool')!=old['tool'] or call.get('call_id')!=old['call_id'] or any(
                args.get(k)!=old['arguments'][k] for k in ('id','kind','model_id','recipe_sha256','interpreter_version'))):
            raise InvalidProviderResponseError('FEEDBACK_RECIPE_PIN_CHANGED')
        if 'recipe' in args and not same_json(args['recipe'],old['arguments']['recipe']):
            raise InvalidProviderResponseError('FEEDBACK_RECIPE_DEFINITION_CHANGED')
        # JSON numbers 3 and 3.0 are schema-equivalent but have different content
        # hashes. Never re-hash a model's copy: bind the already pinned original.
        args['recipe']=deepcopy(old['arguments']['recipe'])
    placements={r['id']:r for r in (context.get('placement_contract') or {}).get('relations',[])}
    grouped={}
    for index,edit in enumerate(patch['edits']):
        if not isinstance(edit,dict) or not isinstance(edit.get('target_id'),str):
            raise InvalidProviderResponseError('Feedback edit identity is invalid')
        grouped.setdefault(edit['target_id'],[]).append((index,edit))
    output=[]
    for identity,entries in grouped.items():
        if len(entries)==1:output.append(deepcopy(entries[0][1]));continue
        if (all(e.get('action')=='change' and set(e)=={'action','target_id','reason','tool_call'}
                and isinstance(e.get('reason'),str) and 1<=len(e['reason'].strip())<=300 for _,e in entries)
                and all(e['tool_call']==entries[0][1]['tool_call'] for _,e in entries)):
            # Exact same final state repeated is idempotent, not contradictory
            # changes or an instruction to move twice. All raw copies survive
            # in inference evidence; the single complete call is still checked.
            output.append(deepcopy(entries[0][1]));continue
        if len(entries)!=2 or {e.get('action') for _,e in entries}!={'change','reparent'} or identity not in current:
            raise InvalidProviderResponseError('FEEDBACK_DUPLICATE_TARGET: conflicting repeated edits for '+identity[:64])
        change=next(e for _,e in entries if e['action']=='change')
        relation=next(e for _,e in entries if e['action']=='reparent')
        if (set(change)!={'action','target_id','reason','tool_call'} or
                set(relation) not in ({'action','target_id','reason','placement'},
                    {'action','target_id','reason','placement','tool_call'})):
            raise InvalidProviderResponseError('FEEDBACK_SPLIT_EDIT_FIELDS_INVALID')
        call=change['tool_call'];other=relation.get('tool_call')
        if any(not isinstance(e.get('reason'),str) or not 1<=len(e['reason'].strip())<=300 for _,e in entries):
            raise InvalidProviderResponseError('FEEDBACK_SPLIT_EDIT_REASON_INVALID')
        old=current[identity]
        if (not isinstance(call,dict) or not isinstance(call.get('arguments'),dict) or
                call.get('tool')!=old['tool'] or call.get('call_id')!=old['call_id'] or
                call['arguments'].get('id')!=identity or
                call['arguments'].get('kind')!=old['arguments'].get('kind')):
            raise InvalidProviderResponseError('FEEDBACK_SPLIT_EDIT_IDENTITY_CHANGED')
        if (not isinstance(relation['placement'],dict) or relation['placement'].get('id')!=identity):
            raise InvalidProviderResponseError('FEEDBACK_SPLIT_EDIT_PLACEMENT_INVALID')
        if other is not None and other!=call:
            raise InvalidProviderResponseError('FEEDBACK_DUPLICATE_TARGET: replacement calls disagree for '+identity[:64])
        if relation['placement']==placements.get(identity):
            output.append(deepcopy(change))
        else:
            if old['tool']!='place_room_item':raise InvalidProviderResponseError('FEEDBACK_REPARENT_UNSUPPORTED')
            combined=deepcopy(relation);combined['tool_call']=deepcopy(call)
            output.append(combined)
    return {**deepcopy(patch),'edits':output}


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
            if old is not None and old['tool']=='place_library_asset':
                call=deepcopy(next(s for s in tool_call_schemas('2.3')
                    if s['properties']['tool'].get('const')=='place_library_asset'))
                call['properties']['call_id']={'type':'string','const':old['call_id']}
                args=call['properties']['arguments'];args['properties'].pop('snapshot');args['required'].remove('snapshot')
                args['properties']['id']={'type':'string','const':identity}
                args['properties']['asset_version']={'type':'string','const':old['arguments']['snapshot']['version']}
                args['required'].append('asset_version')
                return call
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
                    if old is not None and old['tool']=='place_model_recipe':
                        branch['properties'].pop('recipe')
                        branch['required'].remove('recipe')
                        for key in ('model_id','recipe_sha256','interpreter_version'):
                            branch['properties'][key]={'type':'string',
                                'const':deepcopy(old['arguments'][key])}
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


def compact_feedback_context(context):
    """Geometry stays in exact host evidence, not copied into model output.

    Retain all object IDs/versions/transforms and conservative dimensions. This
    is explicitly not an executable plan, geometry inspection or new authority.
    """
    def compact(value):
        if isinstance(value,list):return [compact(v) for v in value]
        if not isinstance(value,dict):return deepcopy(value)
        # Inventory original_parameters also contains a bare snapshot rather
        # than a tool_call wrapper. Preserve its identity/metadata, not geometry.
        if value.get('schema_version')=='library-mesh-1.0' and {'points','triangles','version'}<=value.keys():
            return {**{k:deepcopy(value[k]) for k in ('logical_asset_id','version','title','dimensions_m',
                'units','up_axis','physics_status')},'summary_only':True}
        if value.get('tool')=='place_library_asset' and isinstance(value.get('arguments'),dict):
            result=deepcopy(value);args=result['arguments'];snapshot=args.pop('snapshot')
            args['asset_version']=snapshot['version']
            result['asset_summary']={k:deepcopy(snapshot[k]) for k in
                ('logical_asset_id','version','title','dimensions_m','units','up_axis','physics_status')}
            result['geometry_status']='Pinned static mesh; summary only, no shape editing or measured free-space proof.'
            return result
        if value.get('tool')=='place_model_recipe' and isinstance(value.get('arguments'),dict):
            result=deepcopy(value);result['arguments'].pop('recipe',None)
            return result
        if 'recipe' in value and 'recipe_sha256' in value and 'model_id' in value:
            return {k:compact(v) for k,v in value.items() if k!='recipe'}
        return {k:compact(v) for k,v in value.items()}
    return {**compact(context),'wire_context_kind':'summary_only_full_host_context_sha_bound'}


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
    prompt=json.dumps({**compact_feedback_context(context),'environment_model_library':library_for_request(context['request_text'])},
        ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if len(prompt.encode('utf-8'))>128000:raise ValueError('feedback context too large')
    return GenerationRequest(request_id,prompt,schema_version=FEEDBACK_VERSION,feedback_context=deepcopy(context))


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
    """One bounded service deadline; never save, Build, or Apply on its own."""

    def __init__(self, provider: SceneEditProvider, config: ProviderConfig) -> None:
        self._provider = provider
        self._config = config

    async def propose(self, context: Mapping[str, Any], request_id: str, *, inference_scope=None,diagnostics=None,token=None,feedback_candidate_validator=None) -> dict[str, Any]:
        from dataclasses import replace
        deadline=time.monotonic()+self._config.timeout_s
        request = scene_edit_generation_request(context, request_id)
        request=replace(request,inference_scope=inference_scope,diagnostics=diagnostics,
            feedback_candidate_validator=feedback_candidate_validator,feedback_deadline=deadline)
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
