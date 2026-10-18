# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Typed review of one frozen current Isaac frame, never execution authority."""
import base64
from copy import deepcopy
import hashlib
import math

from twinpulse_core import canonical_sha256
from twinpulse_core.geometry_diagnostics import geometry_issue
from .errors import ProviderConfigurationError
from .semantic_scene import revision, _shape_issues
from .scene_contract import SceneContractError, report
from .stage_transport import explicit_json_contract
from .observation_alignment import ALIGNMENT_INSTRUCTIONS
from .assembly_evidence import INSTRUCTIONS as ASSEMBLY_INSTRUCTIONS,recipe_descriptor

RENDER_REVIEW_REVISION = 'current-render-review-1.3'
ASPECTS = ('layout', 'support', 'appearance')


def finite_flash_options(model):
    """Model-bound finite classification, not a generic reasoning override.

    Nebius exposes reasoning_effort=none; DeepSeek documents non-thinking mode.
    Used only for a compact initial room summary and a frozen-frame critic.
    Detailed inventory, planner and repair retain their independent settings.
    https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion
    https://api-docs.deepseek.com/api/create-chat-completion/
    """
    return {'reasoning_effort':'none'} if model=='deepseek-ai/DeepSeek-V4.1-Flash' else {}


def compiled_geometry(plan):
    """Compact actual envelopes/axes, not source measurements or LiDAR surfaces."""
    rows=[]
    for call in plan['calls']:
        args=call['arguments'];value={k:deepcopy(v) for k,v in args.items() if k!='recipe'}
        row=dict(tool=call['tool'],arguments=value)
        size=args.get('dimensions_m',args.get('size_m'))
        if call['tool']=='place_model_recipe':
            size=[args['parameters'][k] for k in ('width','depth','height')]
            row['assembly_geometry']=recipe_descriptor(args['recipe'],args['parameters'],
                yaw_deg=args['yaw_deg'],centre_xy=args['center_m'])
        centre=args.get('center_m',args.get('position_m'))
        if size and centre and len(size)>=2:
            sx,sy=size[:2];yaw=math.radians(args.get('yaw_deg',0));c,s=math.cos(yaw),math.sin(yaw)
            row['world_footprint_xy_m']=[[round(centre[0]+c*x-s*y,6),round(centre[1]+s*x+c*y,6)]
                for x,y in ((-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2))]
            row['horizontal_long_axis_xy']=(None if abs(sx-sy)<1e-6 else
                [round(v,6) for v in ((c,s) if sx>sy else (-s,c))])
        rows.append(row)
    return dict(plan_sha256=canonical_sha256(plan),calls=rows,
        world_axes='X right, Y rear, Z up; source camera registration unverified',
        basis='actual checked compiled envelopes; not measured source poses or sensor-height surfaces')


def repair_geometry_context(plan, target_ids):
    """Bounded current compiled facts, never extra edit permission.

    The previous repair prompt repeated declarations but not the actual pose
    selected by the packing compiler. Keep targets and nearest blockers in the
    same coordinate system; their editable slots still come from repair_scope.
    """
    if plan is None:return None
    facts=compiled_geometry(plan);targets=set(target_ids)
    calls=facts.pop('calls');selected=[r for r in calls if r['arguments'].get('id') in targets]
    def centre(row):
        a=row['arguments'];return a.get('center_m',a.get('position_m',[0,0]))[:2]
    neighbours=sorted((r for r in calls if r not in selected),key=lambda row:
        min((math.dist(centre(row),centre(t)) for t in selected),default=0))[:12]
    return {**facts,'target_calls':selected,'nearby_read_only_calls':neighbours,
        'permission':'Read-only compiled facts. Only schema repair_scope slots authorize changes.',
        'assembly_interpretation':ASSEMBLY_INSTRUCTIONS}


def review_candidate(draft):
    """Semantic identity/support without copying all recipe expression trees.

    Exact recipes remain in the frozen plan/evidence. The reviewer receives
    actual compiled envelopes and the render, not duplicate authoring code.
    """
    return {k:deepcopy(v) for k,v in draft.items() if k in {'schema_version','room','inventory','objects'}}


def spatial_prior(draft, assessments, observation_quality):
    """Relative layout evidence, not metric accuracy or robot authority."""
    # Root assemblies are selected by dependency, not a photo/category list.
    roots=[i for i,v in draft['objects'].items()
        if v.get('placement',{}).get('relation') in ('floor','wall','ceiling')]
    deferred=sorted(set(draft['objects'])-set(assessments))
    checked_roots=[i for i in roots if i in assessments]
    contradictions=[i for i in checked_roots if assessments[i]['layout']['status']=='contradiction'
        and assessments[i]['layout']['confidence']>=.8]
    uncertain=[i for i in checked_roots if assessments[i]['layout']['status']!='consistent'
        or assessments[i]['layout']['confidence']<.8]
    source_conflicts=any(r.get('code') in ('PHOTO_RELATIVE_ORDER_CONTRADICTION',
        'PHOTO_OBSERVED_REGION_CONTRADICTION') for r in observation_quality.get('issues',[]))
    status=('needs_revision' if contradictions or source_conflicts else
        'uncertain' if not checked_roots or uncertain or set(roots)&set(deferred) else
        'consistent_materialized_anchors')
    return dict(schema_version='relative-layout-prior-1.0',status=status,
        anchor_ids=roots,reviewed_anchor_ids=checked_roots,contradicted_anchor_ids=contradictions,
        uncertain_anchor_ids=uncertain,deferred_object_ids=deferred,
        metric_scale='estimated_not_measured',sensor_alignment='not_run',
        semantic_sensor_correspondence='not_run',motion_authorized=False,physical_authority=False)


def binding(draft, plan, capture):
    metadata, data = capture['metadata'], capture['jpeg']
    if (not isinstance(data, bytes) or not data or len(data) > 180000
            or metadata.get('sha256') != hashlib.sha256(data).hexdigest()
            or metadata.get('plan_sha256') != canonical_sha256(plan)
            or metadata.get('candidate_revision') != revision(draft)
            or not metadata.get('scene_revision')
            or metadata.get('applied_revision') != metadata['scene_revision']
            or not metadata.get('engine_session_id') or not metadata.get('stage_epoch')
            or not metadata.get('command_id')):
        raise ProviderConfigurationError('RENDER_CAPTURE_IDENTITY_INVALID')
    return canonical_sha256(metadata)


def schema(draft, frame_key, plan=None):
    assessment = {'type': 'object', 'additionalProperties': False,
        'required': ['status', 'confidence', 'reason'], 'properties': {
            'status': {'enum': ['consistent', 'contradiction', 'uncertain']},
            'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
            'reason': {'type': 'string', 'minLength': 1, 'maxLength': 400}}}
    ids=set(draft['objects']) if plan is None else {c['arguments']['id'] for c in plan['calls']}
    properties = {identity: {'type': 'object', 'additionalProperties': False,
        'required': list(ASPECTS), 'properties': {aspect: deepcopy(assessment) for aspect in ASPECTS}}
        for identity in draft['objects'] if identity in ids}
    return {'type': 'object', 'additionalProperties': False,
        'required': ['review_version', 'frame_key', 'objects'], 'properties': {
            'review_version': {'const': RENDER_REVIEW_REVISION}, 'frame_key': {'const': frame_key},
            'objects': {'type': 'object', 'additionalProperties': False,
                'required': list(properties), 'properties': properties}}}


def body(request, draft, observation, capture, *, model, cap):
    from .image_payload import image_payload
    key = binding(draft, capture['plan'], capture)
    content = {'user_request': request.prompt, 'candidate': review_candidate(draft),
        'compiled_geometry':compiled_geometry(capture['plan']),
        'observation': observation.to_dict(), 'capture': capture['metadata'],
        'frame_key': key, 'metric_scale': 'estimated_not_measured',
        'deferred_object_ids':sorted(set(draft['objects'])-
            {c['arguments']['id'] for c in capture['plan']['calls']})}
    reference=([{'type':'image_url','image_url':{'url':'data:'+image_payload(request.images[0])[0]+';base64,'+
        base64.b64encode(image_payload(request.images[0])[1]).decode('ascii'),'detail':request.image_detail}}]
        if request.images else [])
    comparison=('Compare image 1 (source photo) with image 2 (frozen current Isaac render). '
        if request.images else 'Compare the explicit user request with image 1 (frozen current Isaac render). '
        'Check requested shape constraints including number, width, orientation and support of actual panels; '
        'do not substitute an ordinary rack/bookcase for an explicitly different multi-part shape. ')
    # Reviewed Flash-specific finite classification policy, not a generic model
    # default. Actual critic 0fa639... spent all 40k tokens on hidden reasoning
    # and returned no final JSON. Nebius advertises reasoning_effort=none and
    # DeepSeek documents it as non-thinking mode. Keep every aspect/ID and the
    # unchanged output cap, geometry and current-frame validation. Other
    # observation stages/models retain their own reasoning behavior.
    # https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion
    # https://api-docs.deepseek.com/guides/thinking_mode/
    reasoning = finite_flash_options(model)
    return explicit_json_contract({'model': model, 'temperature': 0, 'max_tokens': cap, **reasoning,
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'twinpulse_render_review', 'strict': True, 'schema': schema(draft, key,capture['plan'])}},
        'messages': [{'role': 'system', 'content':
            comparison+
            'Review every schema-listed materialized object: relative layout, support relationship and recognizable shape. '
            'First establish the room/view orientation, then compare large furniture assemblies: left/right and '
            'front/rear order, long-axis orientation, wall adjacency, doors and the gap between large obstacles. '
            'A bed or desk rotated across a passage is a layout contradiction even when its object ID exists. '
            'Report that under layout, not only appearance. Evaluate a parent and its supported children '
            'as one assembly; count completion alone is never layout evidence. '
            'Images may have different viewpoints. Occlusion or hidden surfaces are uncertain, not missing objects. '
            'Use compiled_geometry to identify each rendered assembly and its ACTUAL position, dimensions '
            'and yaw; the compiler may move an object away from its declared region to avoid a collision. '
            'Separate what is visible in the source from what is numerically known in the render plan. '
            'For layout reasons name the object pair/wall, source long-axis or adjacency, and compiled '
            'long-axis or adjacency; do not confuse the model origin with a measured source position. '
            +ALIGNMENT_INSTRUCTIONS+ASSEMBLY_INSTRUCTIONS+
            'When wall-relative source evidence exists, compare that specific object/wall relationship '
            'against the compiled footprint and visible render. If wall/view correspondence is unresolved, '
            'report uncertain, not consistent by default. Source confidence is not proof of correctness. '
            'Observer front/middle/rear region labels describe image regions, not calibrated world '
            'footprint centres. Their mismatch with a synthetic world grid is an unverified hypothesis, '
            'not proof of a misplaced object. Compare visible assembly relationships instead. '
            'Only report contradiction with direct visible evidence; explain that evidence. '
            'Room size is an unmeasured estimate, not a failure. Do not infer absolute dimensions from pixels. '
            'Deferred IDs remain unresolved and were intentionally not rendered. Review only schema-listed '
            'materialized IDs; never claim full inventory or deferred-object validation. '
            'A consistent check is limited visual evidence, not measured accuracy or robot readiness. '
            'Return the exact frame_key and all object IDs. No patch, tools, executable code or movement. '
            'Use one concise evidence clause per reason (prefer at most 96 characters). '
            'For consistent aspects do not repeat the whole room description. '
            'For uncertain aspects name the visibility limitation; for contradictions name the actual conflicting pair/axis. '
            'Complete the finite per-object table, not an exhaustive reconstruction essay.'},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': __import__('json').dumps(content, ensure_ascii=False,separators=(',',':'))},
                *reference,
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+
                    base64.b64encode(capture['jpeg']).decode('ascii'), 'detail': request.image_detail}}]}]})


def checked(value, draft, plan, capture, observation_quality):
    key = binding(draft, plan, capture)
    errors = _shape_issues(value, schema(draft, key,plan))
    if errors:
        raise SceneContractError(report(errors))
    # A visual model cannot erase existing deterministic source/pose conflicts.
    # Both tracks refer to this exact current candidate and remain actionable.
    issues = deepcopy(observation_quality.get('issues',[]))
    uncertain = False
    hypotheses=[]
    for identity, assessments in value['objects'].items():
        for aspect, assessment in assessments.items():
            if assessment['status'] == 'contradiction' and assessment['confidence'] >= .8:
                issues.append(geometry_issue('RENDER_'+aspect.upper()+'_MISMATCH', identity,
                    actual={'render_assessment': deepcopy(assessment), 'frame_key': key},
                    expected={'source': observation_quality.get('comparison_source','source_photo_and_current_render'), 'aspect': aspect},
                    related_ids=(observation_quality.get('layout_dependency_ids',{}).get(identity,[])
                        if aspect=='layout' else [])))
            elif assessment['status'] != 'consistent' or assessment['confidence'] < .8:
                uncertain = True
                if aspect=='layout' and assessment['status']=='contradiction' and assessment['confidence']>0:
                    hypotheses.append(dict(target_id=identity,assessment=deepcopy(assessment),
                        frame_key=key,basis='unconfirmed_visual_hypothesis',verified=False))
    return {**deepcopy(observation_quality), 'schema_version': RENDER_REVIEW_REVISION,
        'review_scope':'materialized_subset' if set(draft['objects'])-set(value['objects']) else 'complete_candidate',
        'deferred_object_ids':sorted(set(draft['objects'])-set(value['objects'])),
        'candidate_revision': revision(draft), 'plan_sha256': canonical_sha256(plan),
        'status': 'needs_revision' if issues else 'uncertain' if uncertain else 'consistent',
        'issues': issues, 'render_comparison': 'reviewed', 'frame_key': key,
        'capture': deepcopy(capture['metadata']), 'assessments': deepcopy(value['objects']),
        'layout_hypotheses':hypotheses,
        'relative_layout':spatial_prior(draft,value['objects'],observation_quality),
        'metric_scale': 'estimated_not_measured', 'physical_authority': False}
