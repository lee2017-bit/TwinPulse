# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Additive worker diagnostics. Never an admission or sensor freshness receipt."""
from copy import deepcopy
import math
import re
from .revisions import canonical_sha256
from .observation_stream import checked_context
from .room_localization import compose

POLICY = 'OBSERVED_PROGRESS_3S_V1'
# Display receipt only; the source/control guards remain strictly <200ms.
DISPLAY_RECEIPT_S = 1.


def number(value, limit=1e12):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= limit


def telemetry(mission, identity, scope, resources, now):
    battery = None
    if (isinstance(resources, dict) and resources.get('schema') == 'task-resources-1.0'
            and number(resources.get('sample_s')) and resources['sample_s'] >= 0 and 0 <= now-resources['sample_s'] < .2
            and number(resources.get('source_age_s')) and 0 <= resources['source_age_s'] < .2
            and number(resources.get('voltage_v'), 30) and resources['voltage_v'] > 0):
        voltage = resources['voltage_v']
        battery = {'sample_s': resources['sample_s'], 'source_age_s': resources['source_age_s'],
                   'voltage_v': voltage, 'estimated_percent': round(max(0., min(100., (voltage-10.5)/1.8*100)), 1),
                   'measured_capacity': False}
    waypoint = None
    evidence = mission.last_evidence or {}
    index = mission.mission.index
    if (mission.current_pose_valid and not mission.pending and mission.mission.status == 'RUNNING'
            and evidence.get('room_from_map') and index < len(mission.route_map)
            and number(evidence.get('sample_s')) and evidence['sample_s'] >= 0 and 0 <= now-evidence['sample_s'] < .2):
        waypoint = {'sample_s': evidence['sample_s'], 'index': index,
                    'count': len(mission.route_map),
                    'xy_room': compose(evidence['room_from_map'], [*mission.route_map[index], 0.])[:2]}
    body = {'schema': 'mission-telemetry-1.0', 'session_id': identity,
            'scope_sha256': canonical_sha256(scope), 'context': deepcopy(mission.context),
            'emitted_s': now, 'battery': battery, 'next_waypoint': waypoint,
            'progress_policy': POLICY, 'motor_load': 'UNSUPPORTED',
            'motion_authorized': False, 'physical_demo_ready': False}
    return {**body, 'revision': canonical_sha256(body)}


def checked_telemetry(value, identity, scope, context=None):
    keys = {'schema', 'session_id', 'scope_sha256', 'context', 'emitted_s', 'battery',
            'next_waypoint', 'progress_policy', 'motor_load', 'motion_authorized',
            'physical_demo_ready', 'revision'}
    if (not isinstance(value, dict) or set(value) != keys or value['schema'] != 'mission-telemetry-1.0'
            or value['session_id'] != identity or value['scope_sha256'] != canonical_sha256(scope)
            or value['progress_policy'] != POLICY or value['motor_load'] != 'UNSUPPORTED'
            or value['motion_authorized'] is not False or value['physical_demo_ready'] is not False
            or not number(value['emitted_s']) or value['emitted_s'] < 0):
        raise ValueError('MISSION_TELEMETRY_CONTEXT')
    source = checked_context(value['context'])
    if (source['origin'] != 'live_ros' or source['project_id'] != scope['project_id']
            or source['source_revision'] != source['release_id']
            or context and any(source[k] != v for k, v in context.items())):
        raise ValueError('MISSION_TELEMETRY_SOURCE')
    for row, keys in ((value['battery'], {'sample_s', 'source_age_s', 'voltage_v', 'estimated_percent', 'measured_capacity'}),
                      (value['next_waypoint'], {'sample_s', 'index', 'count', 'xy_room'})):
        if row is None: continue
        if (not isinstance(row, dict) or set(row) != keys or not number(row['sample_s']) or row['sample_s'] < 0
                or not 0 <= value['emitted_s']-row['sample_s'] < .2):
            raise ValueError('MISSION_TELEMETRY_SAMPLE')
    battery = value['battery']
    if battery is not None:
        if (not number(battery['source_age_s']) or not 0 <= battery['source_age_s'] < .2
                or not number(battery['voltage_v'], 30) or battery['voltage_v'] <= 0
                or not number(battery['estimated_percent'], 100) or battery['measured_capacity'] is not False
                or battery['estimated_percent'] != round(max(0., min(100., (battery['voltage_v']-10.5)/1.8*100)), 1)):
            raise ValueError('MISSION_TELEMETRY_BATTERY')
    waypoint = value['next_waypoint']
    if waypoint is not None:
        if (type(waypoint['index']) is not int or type(waypoint['count']) is not int
                or not 0 <= waypoint['index'] < waypoint['count'] <= 16
                or type(waypoint['xy_room']) is not list or len(waypoint['xy_room']) != 2
                or any(not number(x, 20) for x in waypoint['xy_room'])):
            raise ValueError('MISSION_TELEMETRY_WAYPOINT')
    if (type(value['revision']) is not str or re.fullmatch('[a-f0-9]{64}', value['revision']) is None
            or value['revision'] != canonical_sha256({k:v for k,v in value.items() if k != 'revision'})):
        raise ValueError('MISSION_TELEMETRY_HASH')
    return deepcopy(value)
