# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded data-only goal bootstrap for the shared robot-local mission loop."""
from copy import deepcopy
import json
import re
from .observed_mission import checked_goal
from .local_navigation import finite
from .mission_contract import valid_context, document_hash


def checked_nominal(value,room_revision):
    if (not isinstance(value,dict) or set(value)!={'objects','height_m','room_revision'}
            or value['room_revision']!=room_revision or not finite(value['height_m'])
            or not .05<=value['height_m']<=1 or not isinstance(value['objects'],list)
            or not 4<=len(value['objects'])<=13):raise ValueError('ADAPTIVE_NOMINAL_SHAPE')
    ids=set()
    for obj in value['objects']:
        if (not isinstance(obj,dict) or set(obj)!={'id','kind','transform','shape'}
                or not isinstance(obj['id'],str) or not re.fullmatch('[A-Za-z0-9_.-]{1,128}',obj['id'])
                or obj['id'] in ids or obj['kind'] not in {'floor','wall'}
                or not isinstance(obj['shape'],dict) or set(obj['shape'])!={'dimensions_m'}
                or not isinstance(obj['transform'],dict) or set(obj['transform'])!={'position_m','rotation_rpy_deg'}):
            raise ValueError('ADAPTIVE_NOMINAL_OBJECT')
        ids.add(obj['id'])
        for key,rows,limit,positive in (('dimensions',obj['shape']['dimensions_m'],12,True),
                ('position',obj['transform']['position_m'],12,False),
                ('rotation',obj['transform']['rotation_rpy_deg'],360,False)):
            if type(rows) is not list or len(rows)!=3 or any(not finite(x) or abs(x)>limit or (positive and x<=0) for x in rows):
                raise ValueError('ADAPTIVE_NOMINAL_GEOMETRY')
    if sum(o['kind']=='floor' for o in value['objects'])!=1:raise ValueError('ADAPTIVE_NOMINAL_FLOOR')
    from .automatic_photo_alignment import structural_section
    structural_section(value['objects'],value['height_m'])
    return deepcopy(value)


def nominal_room(objects,height_m,room_revision):
    """Server-side structural subset; photo furniture is not a scanned surface."""
    rows=[{'id':o['id'],'kind':o['kind'],'shape':{'dimensions_m':list(o['shape']['dimensions_m'])},
        'transform':{'position_m':list(o['transform']['position_m']),
                     'rotation_rpy_deg':list(o['transform'].get('rotation_rpy_deg',[0,0,0]))}}
        for o in objects if o['kind'] in {'floor','wall'} and o.get('dynamic') is not True]
    return checked_nominal({'objects':rows,'height_m':height_m,'room_revision':room_revision},room_revision)


def adaptive_scope(value):
    handoff=isinstance(value,dict) and value.get('schema')=='observed-mission-scope-7.0'
    idle=isinstance(value,dict) and value.get('schema')=='observed-mission-scope-6.0'
    survey=isinstance(value,dict) and value.get('schema') in {'observed-mission-scope-4.0','observed-mission-scope-5.0'}
    correction=isinstance(value,dict) and value.get('schema') in {'observed-mission-scope-3.0','observed-mission-scope-5.0'}
    cold=isinstance(value,dict) and value.get('schema') in {'observed-mission-scope-2.0','observed-mission-scope-3.0','observed-mission-scope-4.0','observed-mission-scope-5.0'}
    keys={'schema', 'project_id', 'goal', 'reference', 'alignment'}|({'nominal'} if cold else set())|({'photo_policy'} if correction else set())|({'phase'} if idle or handoff else set())
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('ADAPTIVE_SCOPE_SHAPE')
    if value['schema'] not in {'observed-mission-scope-1.0','observed-mission-scope-2.0','observed-mission-scope-3.0','observed-mission-scope-4.0','observed-mission-scope-5.0','observed-mission-scope-6.0','observed-mission-scope-7.0'} or not isinstance(value['project_id'], str) or not re.fullmatch('[A-Za-z0-9_.-]{1,128}', value['project_id']):
        raise ValueError('ADAPTIVE_SCOPE_CONTEXT')
    goal = checked_goal(value['goal'])
    reference = value['reference']; alignment = value['alignment']
    if idle and (value['phase']!='IDLE_LOCALIZATION_ONLY' or goal['mode']!='NAVIGATE_TWIN_GOAL'):
        raise ValueError('ADAPTIVE_IDLE_REFERENCE_SCOPE')
    if handoff and (value['phase']!='REVIEWED_GOAL_EXECUTION' or goal['mode']!='NAVIGATE_TWIN_GOAL'):
        raise ValueError('ADAPTIVE_HANDOFF_SCOPE')
    if cold:
        if goal['mode']!=('SURVEY_ONLY' if survey else 'SURVEY_THEN_NAVIGATE') or reference is not None or alignment is not None:
            raise ValueError('ADAPTIVE_COLD_SCOPE')
        checked_nominal(value['nominal'],goal['room_revision'])
        if correction and value['photo_policy']!='idle-bounded-wall-ack-1.0':
            raise ValueError('ADAPTIVE_CORRECTION_POLICY')
    elif goal['mode'] in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:raise ValueError('ADAPTIVE_COLD_SCOPE_REQUIRED')
    elif goal['mode'] == 'SURVEY_LOCAL':
        if reference is not None or alignment is not None or sum(x*x for x in goal['xy']) > .5**2:
            raise ValueError('ADAPTIVE_SURVEY_SCOPE')
    elif idle or handoff:
        from .reference_transport import checked_descriptor,hex_id
        if (goal['mode']!='NAVIGATE_TWIN_GOAL'
                or idle and goal['xy']!=[0.,0.] or type(reference) is not dict
                or set(reference)!={'kind','revision','payload'}
                or reference['kind']!='accepted-survey-reference-1.0' or not hex_id(reference['revision'],64)):
            raise ValueError('ADAPTIVE_IDLE_REFERENCE_SCOPE')
        checked_descriptor(reference['payload'])
        if (type(alignment) is not dict or set(alignment)!={'status','room_from_map','report_revision'}
                or alignment['status']!='ALIGNMENT_CANDIDATE' or not hex_id(alignment['report_revision'],64)
                or type(alignment['room_from_map']) is not list or len(alignment['room_from_map'])!=3
                or any(not finite(v) or abs(v)>20 for v in alignment['room_from_map'])):
            raise ValueError('ADAPTIVE_ALIGNMENT_REQUIRED')
    else:
        if (not isinstance(reference, dict) or set(reference) != {'revision', 'endpoint_cells'}
                or not isinstance(reference['revision'], str) or not re.fullmatch('[a-f0-9]{64}', reference['revision'])
                or not isinstance(reference['endpoint_cells'], list) or not 24 <= len(reference['endpoint_cells']) <= 512):
            raise ValueError('ADAPTIVE_REFERENCE_BUDGET')
        if any(type(p) is not list or len(p) != 2 or any(not finite(x) or abs(x)>12 for x in p) for p in reference['endpoint_cells']):
            raise ValueError('ADAPTIVE_REFERENCE_GEOMETRY')
        if (not isinstance(alignment, dict) or set(alignment) != {'status', 'room_from_map', 'report_revision'}
                or alignment['status'] != 'ALIGNMENT_CANDIDATE'
                or not isinstance(alignment['report_revision'], str) or not re.fullmatch('[a-f0-9]{64}', alignment['report_revision'])
                or type(alignment['room_from_map']) is not list or len(alignment['room_from_map']) != 3
                or any(not finite(x) or abs(x)>20 for x in alignment['room_from_map'])):
            raise ValueError('ADAPTIVE_ALIGNMENT_REQUIRED')
    # Size is checked before transmission as well as by the fixed stdin parser.
    if len(json.dumps(value, allow_nan=False, separators=(',', ':')).encode()) > 16384:
        raise ValueError('ADAPTIVE_SCOPE_BYTES')
    return deepcopy({**value, 'goal': goal})


def adaptive_bootstrap(context, mission_id, scope):
    if not valid_context(context) or not isinstance(mission_id, str) or not re.fullmatch('[a-f0-9]{32}', mission_id):
        raise ValueError('MISSION_CONTEXT_INVALID')
    scope = adaptive_scope(scope)
    # This phase is reachable only by an owned idle worker's checked transfer.
    if scope['schema']=='observed-mission-scope-7.0':raise ValueError('ADAPTIVE_HANDOFF_REQUIRES_IDLE_WORKER')
    request = {'schema': 'robot-observed-mission-request-1.0', 'mission_id': mission_id,
        'boot_id': context['boot_id'], 'release_id': context['release_id'],
        'calibration_sha256': context['calibration_sha256'], 'created_s': context['issued_s'],
        'expires_s': context['issued_s'] + 90., 'duration_s': scope['goal']['duration_s'],
        'adaptive_scope': scope, 'scope_sha256': document_hash(scope)}
    packet = {'action': 'mission_request', 'nonce': context['nonce'], 'request': request}
    if len(json.dumps(packet, allow_nan=False).encode()) > 16384:
        raise ValueError('ADAPTIVE_BOOTSTRAP_BYTES')
    return packet
