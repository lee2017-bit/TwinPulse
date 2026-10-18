# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reviewed, data-only robot adapters and immutable instance pins."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import re

from .command_broker import BrokerError
from .robot_registry import RobotEndpoint

ADAPTER_ID = 'turtlebot3_burger_v1'
ADAPTER_VERSION = 'burger-reviewed-1.0'
CREDENTIAL_REF = 'openssh/twinpulse-burger/automation'
ADAPTERS = (
    {'id': ADAPTER_ID, 'label': 'TurtleBot3 Burger · reviewed adapter', 'supported': True,
     'version': ADAPTER_VERSION, 'robot_profile_id': None},
    {'id': 'unreviewed', 'label': 'Unreviewed hardware', 'supported': False,
     'version': 'unreviewed-1.0', 'robot_profile_id': None},
)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def instance_binding(row):
    if row is None:
        return None
    adapter = next((a for a in ADAPTERS if a['id'] == row['adapter_id']), None)
    if adapter is None:
        raise ValueError('ROBOT_ADAPTER_UNKNOWN')
    endpoint = asdict(RobotEndpoint(**row['endpoint']).checked())
    value = {'schema_version': 'robot-instance-binding-1.0', 'instance_id': row['id'],
             'adapter_id': row['adapter_id'], 'adapter_version': row.get('adapter_version', adapter['version']),
             'endpoint': endpoint, 'credential_ref': row.get('credential_ref') or CREDENTIAL_REF,
             'host_identity_ref': row.get('host_identity_ref', 'openssh-known-hosts'),
             'robot_profile_id': row.get('robot_profile_id', adapter['robot_profile_id']),
             'calibration_ref': row.get('calibration_ref')}
    value['sha256'] = _digest(value)
    return checked_binding(value)


def checked_binding(value):
    keys = {'schema_version', 'instance_id', 'adapter_id', 'adapter_version', 'endpoint',
            'credential_ref', 'host_identity_ref', 'robot_profile_id', 'calibration_ref', 'sha256'}
    if (not isinstance(value, dict) or set(value) != keys
            or value['schema_version'] != 'robot-instance-binding-1.0'
            or not isinstance(value['instance_id'], str)
            or not re.fullmatch('[a-f0-9]{32}', value['instance_id'])
            or value['adapter_id'] not in {a['id'] for a in ADAPTERS}
            or value['credential_ref'] != CREDENTIAL_REF
            or value['host_identity_ref'] != 'openssh-known-hosts'
            or value['calibration_ref'] is not None
            or value['robot_profile_id'] is not None):
        raise ValueError('ROBOT_BINDING_INVALID')
    adapter = next(a for a in ADAPTERS if a['id'] == value['adapter_id'])
    if value['adapter_version'] != adapter['version']:
        raise ValueError('ROBOT_ADAPTER_VERSION_UNSUPPORTED')
    if not isinstance(value['endpoint'], dict) or set(value['endpoint']) != {'host', 'user', 'port', 'ros_domain_id'}:
        raise ValueError('ROBOT_ENDPOINT_INVALID')
    RobotEndpoint(**value['endpoint']).checked()
    if value['sha256'] != _digest({k: v for k, v in value.items() if k != 'sha256'}):
        raise ValueError('ROBOT_BINDING_CHANGED')
    return deepcopy(value)


def legacy_binding():
    return instance_binding({'id': '0' * 32, 'adapter_id': ADAPTER_ID,
                             'endpoint': {'host': '192.168.35.139', 'user': 'twinpulse', 'port': 22, 'ros_domain_id': 86}})


def require_adapter(value, *, operation='observation'):
    if value is None:
        raise BrokerError('robot_selection_required', 'Select a registered robot first.', status=409)
    value = checked_binding(value)
    if value['adapter_id'] != ADAPTER_ID:
        raise BrokerError('robot_adapter_unreviewed', 'This hardware needs a reviewed adapter before connection or preparation.', status=409)
    endpoint = RobotEndpoint(**value['endpoint']).checked()
    if operation != 'observation' and (endpoint.user, endpoint.port, endpoint.ros_domain_id) != ('twinpulse', 22, 86):
        raise BrokerError('robot_endpoint_not_supported',
                          'The reviewed preparation/control adapter requires SSH user twinpulse, port 22 and ROS domain 86. Host selection is supported.', status=409)
    return endpoint
