# SPDX-License-Identifier: Apache-2.0
"""Pure immutable provenance, never authorization or calibrated localization."""
from copy import deepcopy
import hashlib
import json
import math
import re


def _identity(value, nullable=False):
    return value is None and nullable or isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value) is not None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def twin_context(project_id, conversation_session_id, engine, *, kind='physical', anchor=None):
    snapshot = engine.get('snapshot') or {}
    current = engine.get('engine_connected') is True and bool(snapshot.get('applied_revision'))
    alignment = dict(frame_id='isaac_world' if kind == 'sim' else 'native_sensor',
                     status='SIM_WORLD' if kind == 'sim' else 'UNALIGNED', aligned=kind == 'sim', anchor=None)
    if kind == 'physical' and anchor is not None:
        alignment.update(status='OPERATOR_ESTIMATE_NOT_LOCALIZED', anchor=deepcopy(anchor))
    value = dict(schema='robot-twin-context-1.0', project_id=project_id,
                 conversation_session_id=conversation_session_id,
                 scene_revision=snapshot.get('applied_revision') if current else None,
                 engine_session_id=engine.get('engine_session_id') if current else None,
                 stage_epoch=engine.get('stage_epoch') if current else None,
                 association='TWIN_REFERENCE' if current else 'NO_CURRENT_TWIN', alignment=alignment)
    value['context_id'] = _digest(value)
    return checked_twin_context(value, project_id=project_id)


def checked_twin_context(value, *, project_id=None):
    keys = {'schema', 'context_id', 'project_id', 'conversation_session_id', 'scene_revision',
            'engine_session_id', 'stage_epoch', 'association', 'alignment'}
    if not isinstance(value, dict) or set(value) != keys or value['schema'] != 'robot-twin-context-1.0':
        raise ValueError('TWIN_CONTEXT_SHAPE')
    if (not _identity(value['project_id']) or project_id is not None and value['project_id'] != project_id
            or not _identity(value['conversation_session_id'], nullable=True)):
        raise ValueError('TWIN_CONTEXT_PROJECT_OR_CONVERSATION')
    present = value['association'] == 'TWIN_REFERENCE'
    if value['association'] not in {'TWIN_REFERENCE', 'NO_CURRENT_TWIN'} or any(
            not _identity(value[k]) if present else value[k] is not None
            for k in ('scene_revision', 'engine_session_id', 'stage_epoch')):
        raise ValueError('TWIN_CONTEXT_SCENE')
    alignment = value['alignment']
    if (not isinstance(alignment, dict) or set(alignment) != {'frame_id', 'status', 'aligned', 'anchor'}
            or alignment['status'] not in {'SIM_WORLD', 'UNALIGNED', 'OPERATOR_ESTIMATE_NOT_LOCALIZED'}
            or type(alignment['aligned']) is not bool
            or alignment['aligned'] != (alignment['status'] == 'SIM_WORLD')
            or alignment['frame_id'] != ('isaac_world' if alignment['aligned'] else 'native_sensor')):
        raise ValueError('TWIN_CONTEXT_ALIGNMENT')
    anchor = alignment['anchor']
    if alignment['status'] == 'OPERATOR_ESTIMATE_NOT_LOCALIZED':
        if (not isinstance(anchor, dict) or set(anchor) != {'position_m', 'source', 'scene_revision', 'frame_id', 'aligned', 'visual_epoch'}
                or anchor['source'] != 'operator_estimate_not_localized' or anchor['aligned'] is not False
                or anchor['frame_id'] != 'isaac_world' or not _identity(anchor['visual_epoch'])
                or not _identity(anchor['scene_revision']) or not isinstance(anchor['position_m'], list)
                or len(anchor['position_m']) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in anchor['position_m'])):
            raise ValueError('TWIN_CONTEXT_ANCHOR')
    elif anchor is not None:
        raise ValueError('TWIN_CONTEXT_ANCHOR')
    unsigned = {k: v for k, v in value.items() if k != 'context_id'}
    if value['context_id'] != _digest(unsigned):
        raise ValueError('TWIN_CONTEXT_SHA')
    return deepcopy(value)


def context_relation(source, current):
    if source is None:
        return 'LEGACY_UNKNOWN'
    if source['project_id'] != current['project_id']:
        return 'OTHER_PROJECT'
    if source['association'] == 'NO_CURRENT_TWIN':
        return 'NO_TWIN_AT_CONNECTION'
    if current['association'] != 'TWIN_REFERENCE':
        return 'CURRENT_TWIN_UNAVAILABLE'
    if source['scene_revision'] != current['scene_revision']:
        return 'DIFFERENT_TWIN_REVISION'
    if (source['engine_session_id'], source['stage_epoch']) != (current['engine_session_id'], current['stage_epoch']):
        return 'SAME_REVISION_DIFFERENT_ENGINE'
    return 'SAME_TWIN_REFERENCE_NOT_ALIGNMENT_PROOF'
