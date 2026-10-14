# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded mission consent and transport data; no device or execution authority."""
import hashlib
import json
import re

try:
    from .local_navigation import CheckedMission, finite
except ImportError:
    from local_navigation import CheckedMission, finite


def scope_document(value):
    if (not isinstance(value, dict) or set(value) != {'frame_id', 'waypoints', 'duration_s'}
            or value['frame_id'] != 'odom' or not finite(value['duration_s'])
            or not 0 < value['duration_s'] <= 45 or not isinstance(value['waypoints'], list)
            or any(not isinstance(p, list) for p in value['waypoints'])):
        raise ValueError('MISSION_SCOPE_INVALID')
    points = tuple(tuple(p) for p in value['waypoints'])
    CheckedMission(points, 0., provenance='live_sensor', frame_id='odom', duration_s=value['duration_s'])
    # Deep-copy before the caller can modify the approved scope.
    return {'frame_id': 'odom', 'waypoints': [list(p) for p in points], 'duration_s': value['duration_s']}


def document_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def valid_context(value):
    return (isinstance(value, dict) and set(value) == {'state', 'boot_id', 'release_id',
            'calibration_sha256', 'issued_s', 'nonce'} and value['state'] == 'MISSION_CONTEXT'
        and isinstance(value['boot_id'], str) and re.fullmatch('[A-Za-z0-9-]{1,80}', value['boot_id']) is not None
        and all(isinstance(value[k], str) and re.fullmatch('[a-f0-9]{64}', value[k]) for k in ('release_id', 'calibration_sha256'))
        and isinstance(value['nonce'], str) and re.fullmatch('[a-f0-9]{24}', value['nonce']) is not None
        and finite(value['issued_s']) and value['issued_s'] >= 0)


def bootstrap_packet(context, mission_id, scope):
    if not valid_context(context) or not isinstance(mission_id, str) or not re.fullmatch('[a-f0-9]{32}', mission_id):
        raise ValueError('MISSION_CONTEXT_INVALID')
    scope = scope_document(scope)
    request = {'schema': 'robot-mission-request-1.0', 'mission_id': mission_id,
        'boot_id': context['boot_id'], 'release_id': context['release_id'],
        'calibration_sha256': context['calibration_sha256'], 'created_s': context['issued_s'],
        'expires_s': context['issued_s'] + 90., 'duration_s': scope['duration_s'], 'waypoints': scope['waypoints']}
    return {'action': 'mission_request', 'nonce': context['nonce'], 'request': request}
