# SPDX-License-Identifier: Apache-2.0
"""Single text-only configured planner proposal; no devices or executor."""
import asyncio
import json
from twinpulse_core.robot_task_plan import VERSION, CAPABILITIES, checked_plan, plan_schema,explicit_requirements,request_capabilities
from .generation_policy import ExecutionBudget
from .errors import InvalidProviderResponseError, ProviderConfigurationError
from .nebius_pipeline import _json_content, _ensure_current


async def generate_robot_task(provider, request, token, config):
    if request.images or request.inference_scope is None or request.schema_version != VERSION:
        raise ProviderConfigurationError('ROBOT_TASK_TEXT_SCOPE_REQUIRED')
    data = json.loads(request.prompt)
    if (not isinstance(data, dict) or set(data) != {'text','robot_kind','capabilities'}
            or data['robot_kind'] not in {'sim','physical'} or data['capabilities'] != list(CAPABILITIES)
            or not isinstance(data['text'], str) or not 1 <= len(data['text'].strip()) <= 2000):
        raise ValueError('ROBOT_TASK_REQUEST_INVALID')
    financial = request.inference_scope.bind(request, provider.policy, provider.route_sha256)
    budget = ExecutionBudget(provider.policy, financial_owner=financial);provider._budget = budget
    token.generation_budget=budget;token.generation_role='initial';token.diagnostics=request.diagnostics
    provider._diagnostic=dict(request_id=request.request_id,status='running',sequence=0,attempts=[],input_kind='robot_task_text_only',repair_count=0,max_repairs=0)
    allowed=request_capabilities(data['text'])
    planning_input=dict(data,capabilities=list(allowed),mandatory_capabilities=sorted(explicit_requirements(data['text'])))
    body=provider.body('twinpulse_robot_task',plan_schema(capabilities=allowed),
        'Translate the human ROBOT goal into a bounded composition of the supplied capabilities. Output English JSON, never code. '
        'observe collects a fresh stationary LiDAR/pose pair; survey MOVES to different reachable observation locations, not a 360-degree spin. '
        'return_to_start replans a checked route to the original start, not a blind reversal. '
        'move_relative amount is metres (forward/backward) or radians (left/right); one step <=2m or 2pi. '
        'navigate approaches the nearest named object using current geometry. Do not invent coordinates, targets, sensors or evidence. '
        'You may combine, order and explicitly unroll bounded repetitions of these capabilities (max12 steps). '
        'Use survey for inspect/explore/measure a room; include return_to_start only when requested. '
        'For a loop round the room and back use observe,survey,return_to_start,stop. Never substitute an in-place full turn. '
        'The mandatory_capabilities list is a host validation constraint: every listed capability MUST occur in steps. '
        'When survey is mandatory, use the survey operation; do NOT replace it with a rectangular patrol or invented fixed moves. '
        'Do NOT add relative movements around survey merely to implement exploration: survey already chooses and moves to observation locations. '
        'move_relative is available in the schema only if the human separately requested directional actions; a distance limit is not such a request. '
        'left/right are rotations in radians, never lateral metres. The host survey chooses observation positions from current geometry. '
        'Every explicitly requested return and stop MUST appear as actual steps, not only in the explanation. '
        'Example: forward 10cm, left30 degrees, return and stop requires FOUR steps: move_relative(forward,0.1), move_relative(left,0.5235987756), return_to_start, stop. '
        'Limits cap the ENTIRE task including return: <=12m, <=600s, <=128 finite segments. Prefer 8m/300s/96 for a room survey. '
        'When the human supplies bounded total limits, preserve those limits instead of arbitrarily shrinking them. '
        'A return needs extra finite turns and translations, so never reserve segments only for the initial explicit moves. '
        'Safety, completion, coverage, current pose and permission are determined by the host, not by this JSON. '
        'Unsupported or ambiguous goals use clarify with empty steps. No automatic retry or execution follows this proposal.',planning_input)
    try:
        completion=await asyncio.wait_for(provider._complete_stage('models',body,token,config),budget.timeout_for('initial'))
        _ensure_current(token)
        if completion.model_id != provider.planner_model_id or completion.finish_reason != 'stop':
            raise InvalidProviderResponseError('ROBOT_TASK_OUTPUT_INCOMPLETE')
        try:value=checked_plan(_json_content(completion,'robot_task'),request_text=data['text'])
        except ValueError as exc:raise InvalidProviderResponseError(str(exc)) from exc
        recorder=getattr(provider._transport,'record_validation',None)
        if recorder and completion.attempt_id:recorder('robot_task',completion.attempt_id,dict(validation='passed',proposal=value,scope='proposal_only_no_motion'))
        provider._diagnostic['status']='proposal_ready';budget.stop('ROBOT_TASK_PROPOSAL_READY')
        return value
    except BaseException:
        budget.stop('ROBOT_TASK_FAILED');raise
