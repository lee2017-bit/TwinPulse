# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded search objectives, never visual truth, progress or extra-call authority."""
from copy import deepcopy

from twinpulse_core import canonical_sha256
from .semantic_scene import geometry_repair_context, revision
from .render_review import compiled_geometry
from .scene_contract import SceneContractError, issue, report

EXPERIMENT_REVISION = 'layout-experiment-1.0'
FIELDS = ('region', 'yaw_deg', 'placement')
HARD_LAYOUT_CODES = frozenset({'RENDER_LAYOUT_MISMATCH',
    'PHOTO_RELATIVE_ORDER_CONTRADICTION', 'PHOTO_OBSERVED_REGION_CONTRADICTION'})


def repair_strategy(draft, diagnosis, plan, previous):
    """Schedule one existing repair slot; this grants no mutation or call budget.

    A current major pose conflict must not be starved by a support-model repair.
    Numerical pending evidence is retained and can select capability on a later
    iteration. An unconfirmed objective uses the existing bounded experiment,
    not a relaxed geometry/quality criterion.
    """
    current = (plan is not None and diagnosis.get('status') == 'needs_revision'
        and diagnosis.get('candidate_revision') == revision(draft)
        and diagnosis.get('plan_sha256') == canonical_sha256(plan))
    codes = sorted({row.get('code') for row in diagnosis.get('issues', [])
                    if row.get('code') in HARD_LAYOUT_CODES}) if current else []
    focus = objective(draft, diagnosis, plan, previous) if current and not codes else None
    return dict(strategy=('semantic_layout' if codes else 'focused_layout' if focus
                          else 'capability_first'),
        reason_codes=codes, target_id=focus['target_id'] if focus else None,
        candidate_revision=revision(draft), plan_sha256=canonical_sha256(plan) if plan else None,
        frame_key=diagnosis.get('frame_key'), current_binding=current,
        extra_call_authority=False, physical_authority=False)


def objective(draft, diagnosis, plan, previous):
    """Use one existing quality repair on a not-yet-tried materialized root.

    Hard geometry/high-confidence visual failures retain priority. This only
    schedules exploration while small pending support already requires repair.
    Selection uses checked compiled footprint area, never photo names or IDs.
    """
    if (plan is None or diagnosis.get('status') != 'needs_revision'
            or not diagnosis.get('issues')
            or any(row.get('code') != 'PHOTO_PENDING_SUPPORT_NEEDS_REVISION'
                   for row in diagnosis['issues'])
            or diagnosis.get('plan_sha256') != canonical_sha256(plan)):
        return None
    context = geometry_repair_context(draft, diagnosis)
    eligible = {row['id'] for row in context['targets']
                if 'unconfirmed_current_layout_hypothesis' in row['reasons']}
    tried = {row.get('layout_experiment', row).get('target_id') for row in previous}
    candidates = []
    for row in compiled_geometry(plan)['calls']:
        identity = row['arguments'].get('id')
        value = draft['objects'].get(identity)
        if (identity not in eligible or identity in tried or value is None
                or value['placement']['relation'] != 'floor'):
            continue
        points = row.get('world_footprint_xy_m')
        if not points or len(points) != 4:
            continue
        area = abs(sum(a[0]*b[1]-b[0]*a[1]
                       for a, b in zip(points, points[1:]+points[:1])))/2
        assessment = diagnosis['assessments'][identity]['layout']
        candidates.append((area, assessment['confidence'], identity, row, assessment))
    if not candidates:
        return None
    area, _, identity, geometry, assessment = max(candidates, key=lambda row: row[:3])
    return dict(schema_version=EXPERIMENT_REVISION, target_id=identity,
        base_revision=revision(draft), frame_key=diagnosis['frame_key'],
        plan_sha256=canonical_sha256(plan), compiled_footprint_area_m2=round(area, 6),
        before_geometry=deepcopy(geometry), hypothesis=deepcopy(assessment),
        allowed_fields=list(FIELDS), verified=False, physical_authority=False,
        instruction='Try a source-supported alternative for this root within the existing scope, '
        'or explicitly abstain. This is an unconfirmed search objective, not a mandatory pose '
        'or a measured failure. Changing only props does not fulfil it. No extra call is authorized.')


def response_schema(schema, focus):
    value = deepcopy(schema)
    if focus is not None:
        root=value['properties']['changes']['properties'][focus['target_id']]['anyOf'][1]
        root['properties']={k:v for k,v in root['properties'].items() if k in FIELDS}
        value['properties']['room']={'type':'null'}
        value['required'].append('layout_experiment')
        value['properties']['layout_experiment'] = dict(type='object', additionalProperties=False,
            required=['target_id', 'outcome', 'reason'], properties={
                'target_id': {'const': focus['target_id']},
                'outcome': {'enum': ['trial', 'abstain']},
                'reason': {'type': 'string', 'minLength': 1, 'maxLength': 400}})
    return value


def patch_payload(raw, schema, focus):
    from .semantic_scene import _shape_issues
    errors = _shape_issues(raw, response_schema(schema, focus))
    if errors:
        raise SceneContractError(report(errors))
    return {k: deepcopy(v) for k, v in raw.items() if k != 'layout_experiment'}


def checked_response(raw, schema, focus, before, after):
    """Record intent only; a fresh compile and current critic still decide quality."""
    patch_payload(raw, schema, focus)
    if focus is None:
        return None
    reply = raw['layout_experiment']
    identity = focus['target_id']
    if (before['room'] != after['room'] or any(before['objects'][identity].get(k) != after['objects'][identity].get(k)
            for k in set(before['objects'][identity])|set(after['objects'][identity]) if k not in FIELDS)):
        raise SceneContractError(report([issue('LAYOUT_EXPERIMENT_SCOPE_VIOLATION',
            '$.layout_experiment', target_ids=[identity],
            detail='Focused root model/dimensions and room are unchanged during an unconfirmed layout experiment.')]))
    changed = any(before['objects'][identity].get(k) != after['objects'][identity].get(k) for k in FIELDS)
    if (reply['outcome'] == 'trial') != changed:
        raise SceneContractError(report([issue('LAYOUT_EXPERIMENT_INTENT_MISMATCH',
            '$.layout_experiment', target_ids=[identity],
            detail='A trial changes the focused root, not only props; abstention leaves it unchanged.')]))
    return {**deepcopy(focus), 'intent': deepcopy(reply), 'root_parameters_changed': changed,
            'compiled_effect': 'not_checked', 'quality_outcome': 'not_checked'}


def compile_result(record, plan):
    """An intent/parameter change is not necessarily a compiled pose change."""
    result = deepcopy(record)
    after = next((row for row in compiled_geometry(plan)['calls']
                  if row['arguments'].get('id') == record['target_id']), None)
    before = record['before_geometry']
    fields = ('world_footprint_xy_m', 'horizontal_long_axis_xy')
    changed = (after is not None and (any(before.get(k) != after.get(k) for k in fields)
               or any(before['arguments'].get(k) != after['arguments'].get(k)
                      for k in ('position_m', 'center_m', 'yaw_deg'))))
    result.update(after_geometry=after,
        compiled_effect=('changed_not_quality_proof' if changed else 'unchanged_or_not_rendered'),
        quality_outcome='fresh_current_review_required')
    return result
