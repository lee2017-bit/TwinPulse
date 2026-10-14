# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Typed review of one frozen current Isaac frame, never execution authority."""
import base64
from copy import deepcopy
import hashlib

from twinpulse_core import canonical_sha256
from twinpulse_core.geometry_diagnostics import geometry_issue
from .errors import ProviderConfigurationError
from .semantic_scene import revision, _shape_issues
from .scene_contract import SceneContractError, report
from .stage_transport import explicit_json_contract

RENDER_REVIEW_REVISION = 'current-render-review-1.0'
ASPECTS = ('layout', 'support', 'appearance')


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
    media_type,wire_photo=image_payload(request.images[0])
    key = binding(draft, capture['plan'], capture)
    content = {'user_request': request.prompt, 'candidate': draft,
        'observation': observation.to_dict(), 'capture': capture['metadata'],
        'frame_key': key, 'metric_scale': 'estimated_not_measured',
        'deferred_object_ids':sorted(set(draft['objects'])-
            {c['arguments']['id'] for c in capture['plan']['calls']})}
    return explicit_json_contract({'model': model, 'temperature': 0, 'max_tokens': cap,
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'twinpulse_render_review', 'strict': True, 'schema': schema(draft, key,capture['plan'])}},
        'messages': [{'role': 'system', 'content':
            'Compare image 1 (source photo) with image 2 (frozen current Isaac render). '
            'Review every schema-listed materialized object: relative layout, support relationship and recognizable shape. '
            'Images may have different viewpoints. Occlusion or hidden surfaces are uncertain, not missing objects. '
            'Only report contradiction with direct visible evidence; explain that evidence. '
            'Room size is an unmeasured estimate, not a failure. Do not infer absolute dimensions from pixels. '
            'Deferred IDs remain unresolved and were intentionally not rendered. Review only schema-listed '
            'materialized IDs; never claim full inventory or deferred-object validation. '
            'A consistent check is limited visual evidence, not measured accuracy or robot readiness. '
            'Return the exact frame_key and all object IDs. No patch, tools, executable code or movement.'},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': __import__('json').dumps(content, ensure_ascii=False)},
                {'type': 'image_url', 'image_url': {'url': 'data:'+media_type+';base64,'+
                    base64.b64encode(wire_photo).decode('ascii'), 'detail': request.image_detail}},
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+
                    base64.b64encode(capture['jpeg']).decode('ascii'), 'detail': request.image_detail}}]}]})


def checked(value, draft, plan, capture, observation_quality):
    key = binding(draft, plan, capture)
    errors = _shape_issues(value, schema(draft, key,plan))
    if errors:
        raise SceneContractError(report(errors))
    issues = []
    uncertain = False
    for identity, assessments in value['objects'].items():
        for aspect, assessment in assessments.items():
            if assessment['status'] == 'contradiction' and assessment['confidence'] >= .8:
                issues.append(geometry_issue('RENDER_'+aspect.upper()+'_MISMATCH', identity,
                    actual={'render_assessment': deepcopy(assessment), 'frame_key': key},
                    expected={'source': 'source_photo_and_current_render', 'aspect': aspect}))
            elif assessment['status'] != 'consistent' or assessment['confidence'] < .8:
                uncertain = True
    return {**deepcopy(observation_quality), 'schema_version': RENDER_REVIEW_REVISION,
        'review_scope':'materialized_subset' if set(draft['objects'])-set(value['objects']) else 'complete_candidate',
        'deferred_object_ids':sorted(set(draft['objects'])-set(value['objects'])),
        'candidate_revision': revision(draft), 'plan_sha256': canonical_sha256(plan),
        'status': 'needs_revision' if issues else 'uncertain' if uncertain else 'consistent',
        'issues': issues, 'render_comparison': 'reviewed', 'frame_key': key,
        'capture': deepcopy(capture['metadata']), 'assessments': deepcopy(value['objects']),
        'metric_scale': 'estimated_not_measured', 'physical_authority': False}
