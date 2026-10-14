# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Trusted launcher registration, not a browser or saved-PASS unlock switch."""
from copy import deepcopy
import re
from twinpulse_core.local_navigation import finite


class QualifiedMissionAdmission:
    def __init__(self,expected,observe,clock):
        self.expected=deepcopy(expected);self.observe=observe;self.clock=clock
        required={'project_id','boot_id','release_id','calibration_revision','stop_policy_revision','scope_revision'}
        if set(expected)!=required:raise ValueError('MISSION_ADMISSION_CONTEXT')
        for key in required-{'project_id','boot_id'}:
            if not isinstance(expected[key],str) or re.fullmatch('[a-f0-9]{64}',expected[key]) is None:
                raise ValueError('MISSION_ADMISSION_HASH')

    def __call__(self,scope=None):
        value=self.observe();now=self.clock()
        if any(value.get(k)!=v for k,v in self.expected.items()):raise ValueError('MISSION_ADMISSION_CONTEXT_CHANGED')
        if not finite(value.get('sample_s')) or not 0<=now-value['sample_s']<.2:
            raise ValueError('MISSION_ADMISSION_STALE')
        for key in ('release_reviewed','calibration_reviewed','current_stop_qualified','scope_approved',
                    'sensor_owned','output_watchdog_verified','board_idle'):
            if value.get(key) is not True:raise ValueError('MISSION_ADMISSION_'+key.upper())
        if (value.get('origin')!='live_ros' or value.get('timing_basis')!='VERIFIED_ACQUISITION'
                or value.get('transform_basis')!='measured_sensor_extrinsic'):
            raise ValueError('MISSION_ADMISSION_PHYSICAL_EVIDENCE_REQUIRED')
        if not finite(value.get('voltage')) or value['voltage']<=11.1:
            raise ValueError('MISSION_ADMISSION_BATTERY')
        # Integrity scope is supplied by the trusted launcher, not a UI hash.
        if scope is not None:
            from twinpulse_core.mission_contract import document_hash
            if document_hash(scope)!=self.expected['scope_revision']:raise ValueError('MISSION_ADMISSION_SCOPE_CHANGED')
        return deepcopy(value)
