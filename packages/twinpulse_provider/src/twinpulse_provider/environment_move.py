# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""One audited planner call for a selected object's relative XY intention.

No source file, mesh, layout, photo, label or measured geometry is transmitted.
Only the user's text and selected opaque ID are in the request. No Apply here.
"""
import asyncio
import json
import math
from .generation_policy import ExecutionBudget
from .errors import InvalidProviderResponseError,ProviderConfigurationError
from .nebius_pipeline import _json_content,_ensure_current


VERSION='environment-move-1.0'


async def generate_environment_move(provider,request,token,config):
    if request.images or request.inference_scope is None or request.schema_version!=VERSION:
        raise ProviderConfigurationError('ENVIRONMENT_MOVE_SCOPE_REQUIRED')
    data=json.loads(request.prompt)
    if (not isinstance(data,dict) or set(data)!={'object_id','text'} or not isinstance(data['object_id'],str)
            or not isinstance(data['text'],str) or not 1<=len(data['text'].strip())<=1000):
        raise ValueError('ENVIRONMENT_MOVE_REQUEST_INVALID')
    financial=request.inference_scope.bind(request,provider.policy,provider.route_sha256)
    budget=ExecutionBudget(provider.policy,financial_owner=financial);provider._budget=budget
    token.generation_budget=budget;token.generation_role='initial';token.diagnostics=request.diagnostics
    provider._diagnostic=dict(request_id=request.request_id,status='running',sequence=0,attempts=[],
        input_kind='selected_object_move_text_only',repair_count=0,max_repairs=0)
    schema=dict(type='object',additionalProperties=False,required=['schema_version','mode','object_id','translation_m','explanation'],
        properties=dict(schema_version={'const':VERSION},mode={'enum':['move','clarify']},object_id={'const':data['object_id']},
            translation_m={'anyOf':[dict(type='array',minItems=3,maxItems=3,items=dict(type='number',minimum=-2,maximum=2)),{'type':'null'}]},
            explanation=dict(type='string',minLength=1,maxLength=500)))
    body=provider.body('twinpulse_environment_move',schema,
        'Interpret ONLY a relative XY move of the selected object. Output English JSON, not code. '
        'World +X is right, -X left, +Y rear, -Y front; units metres. Convert explicit centimetres/millimetres. '
        'The third translation component must be zero. Maximum absolute delta is 2m. '
        'No scene, camera pose, obstacle map or measurements are supplied. Do not infer them. '
        'For ambiguous extent/direction, camera-relative requests, another target, rotation, deletion, resizing, '
        'code or robot commands use clarify and translation_m=null. Preserve the exact selected object_id. '
        'No move is executed; a host validates the proposal and the user reviews and Applies it.',data)
    try:
        completion=await asyncio.wait_for(provider._complete_stage('models',body,token,config),budget.timeout_for('initial'))
        _ensure_current(token)
        if completion.model_id!=provider.planner_model_id or completion.finish_reason!='stop':
            raise InvalidProviderResponseError('ENVIRONMENT_MOVE_OUTPUT_INCOMPLETE')
        value=_json_content(completion,'environment_move')
        if (not isinstance(value,dict) or set(value)!=set(schema['required']) or value.get('schema_version')!=VERSION
                or value.get('mode') not in {'move','clarify'} or value.get('object_id')!=data['object_id']
                or not isinstance(value.get('explanation'),str) or not 1<=len(value['explanation'])<=500):
            raise InvalidProviderResponseError('ENVIRONMENT_MOVE_OUTPUT_INVALID')
        delta=value['translation_m']
        if value['mode']=='move':
            if (not isinstance(delta,list) or len(delta)!=3 or delta[2]!=0 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>2 for v in delta)
                    or not any(delta)):
                raise InvalidProviderResponseError('ENVIRONMENT_MOVE_DELTA_INVALID')
        elif delta is not None:raise InvalidProviderResponseError('ENVIRONMENT_MOVE_CLARIFY_INVALID')
        recorder=getattr(provider._transport,'record_validation',None)
        if recorder and completion.attempt_id:recorder('environment_move',completion.attempt_id,
            dict(validation='passed',proposal=value,scope='selected_object_intent_only_not_applied'))
        provider._diagnostic['status']='proposal_ready';budget.stop('ENVIRONMENT_MOVE_PROPOSAL_READY')
        return value
    except BaseException:
        budget.stop('ENVIRONMENT_MOVE_FAILED')
        raise  # Only the owner/shutdown cancels; invalid output remains failed.
