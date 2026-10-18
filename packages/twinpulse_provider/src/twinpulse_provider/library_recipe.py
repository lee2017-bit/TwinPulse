# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Library-only authoring using the ordinary audited stage transport/budget."""
import asyncio
import base64
from copy import deepcopy
import json

from .generation_policy import ExecutionBudget
from .errors import InvalidProviderResponseError,ProviderConfigurationError
from .model_recipe_authoring import proportional_schema,compile_authoring
from .model_recipe_planning import MODEL_RECIPE_AUTHORING_INSTRUCTIONS
from .nebius_pipeline import _json_content,_ensure_current
from .stage_transport import explicit_json_contract


async def generate_recipe(provider,request,token,config):
    if request.inference_scope is None:raise ProviderConfigurationError('LIBRARY_REQUEST_SCOPE_REQUIRED')
    financial=request.inference_scope.bind(request,provider.policy,provider.route_sha256)
    budget=ExecutionBudget(provider.policy,financial_owner=financial);provider._budget=budget
    token.generation_budget=budget;token.generation_role='initial';token.diagnostics=request.diagnostics
    provider._diagnostic=dict(request_id=request.request_id,status='running',sequence=0,attempts=[],
        input_kind='asset_reference' if request.images else 'asset_text',repair_count=0,max_repairs=provider.policy.max_repairs)
    source=None
    if request.images:
        image=request.images[0]
        schema=dict(type='object',additionalProperties=False,required=['description','visible_parts','uncertainties'],
            properties=dict(description=dict(type='string',maxLength=1000),
                visible_parts=dict(type='array',items=dict(type='string',maxLength=200),maxItems=48),
                uncertainties=dict(type='array',items=dict(type='string',maxLength=200),maxItems=16)))
        body=explicit_json_contract(dict(model=provider.observer_model_id,temperature=0,
            max_tokens=provider.stage_output_token_caps['observer'],response_format=dict(type='json_schema',json_schema=dict(
                name='twinpulse_asset_observation',strict=True,schema=schema)),messages=[
                dict(role='system',content='Describe only the requested single Library asset in this reference image. '
                    'List visible parts, openings, supports and uncertainty. No room layout, measurements, code or commands.'),
                dict(role='user',content=[dict(type='text',text=request.prompt),dict(type='image_url',image_url=dict(
                    url='data:'+image.mime_type+';base64,'+base64.b64encode(image.content).decode(),detail=request.image_detail))])]))
        completion=await asyncio.wait_for(provider._complete_stage('observer',body,token,config),budget.timeout_for('initial'))
        source=_json_content(completion,'asset_observation')
        from .semantic_scene import _shape_issues
        if _shape_issues(source,schema):raise InvalidProviderResponseError('LIBRARY_OBSERVATION_CONTRACT_INVALID')
    previous=None;failure=None;seen=set()
    while True:
        content=dict(purpose='asset_create_only',user_request=request.prompt,reference_observation=source,
            scope='One reusable data-only asset; no room, placement, motion or automatic registration.',
            previous_authoring=previous,validation_error=failure)
        body=provider.body('twinpulse_library_recipe',proportional_schema(),
            'Create ONE Library asset as a finite proportional box assembly. '
            'Use the most appropriate allowed kind, or unknown for equipment. '
            'All sizes are explicitly estimated unless the user supplies measurements. '
            'Keep the shape recognizable and preserve openings/supports. Do not create a full room. '
            +MODEL_RECIPE_AUTHORING_INSTRUCTIONS,content)
        completion=await asyncio.wait_for(provider._complete_stage('models',body,token,config),
            budget.timeout_for(token.generation_role))
        _ensure_current(token)
        if completion.model_id!=provider.planner_model_id or completion.finish_reason!='stop':
            raise InvalidProviderResponseError('LIBRARY_RECIPE_OUTPUT_INCOMPLETE')
        value=_json_content(completion,'library_recipe')
        try:
            from .semantic_scene import _shape_issues
            from twinpulse_core.model_recipe import recipe_reuse_problem
            issues=_shape_issues(value,proportional_schema())
            if issues:raise ValueError(str(issues)[:2500])
            recipe=compile_authoring(value);problem=recipe_reuse_problem(recipe)
            if problem:raise ValueError(problem)
            provider._diagnostic['status']='asset_ready';budget.stop('LIBRARY_ASSET_READY')
            recorder=getattr(provider._transport,'record_validation',None)
            if recorder and completion.attempt_id:recorder('library_recipe',completion.attempt_id,
                dict(validation='passed',recipe=recipe,scope='unregistered_asset_only'))
            return recipe
        except (ValueError,InvalidProviderResponseError) as error:
            from twinpulse_core import canonical_sha256
            signature=canonical_sha256(value)
            if signature in seen or budget.repairs>=provider.policy.max_repairs:
                raise InvalidProviderResponseError('LIBRARY_RECIPE_NO_VALID_PROGRESS: '+str(error)[:500]) from error
            seen.add(signature);previous=deepcopy(value);failure=str(error)[:2500]
            token.generation_role='repair'
