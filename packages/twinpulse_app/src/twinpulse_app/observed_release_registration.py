# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Trusted local review record; no HTTP/browser field can register a release.

Robot-local admission still independently checks this boot's qualification,
release, measured calibration, acquisition evidence, ownership and fresh input.
"""
import json
from pathlib import Path
import re
from twinpulse_core.adaptive_mission_contract import adaptive_scope


class ObservedReleaseRegistration:
    def __init__(self, root, project_id, room_revision, *, source_root=None):
        self.root = Path(root); self.project_id = project_id; self.room_revision = room_revision
        self.source_root = Path(source_root) if source_root is not None else self.root

    def __call__(self, scope):
        scope = adaptive_scope(scope)
        path = self.root/'artifacts/robot-admission'/self.project_id/'observed-release.json'
        if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file():
            raise ValueError('REVIEWED_OBSERVED_RELEASE_NOT_REGISTERED')
        if path.stat().st_size>8192:raise ValueError('OBSERVED_REGISTRATION_BUDGET')
        def unique(pairs):
            value={}
            for k,v in pairs:
                if k in value:raise ValueError('OBSERVED_REGISTRATION_DUPLICATE')
                value[k]=v
            return value
        value=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique,
                         parse_constant=lambda _:(_ for _ in ()).throw(ValueError('OBSERVED_REGISTRATION_NONFINITE')))
        keys={'schema','project_id','room_revision','source_id','calibration_sha256','qualification_sha256','target_evidence_sha256'}
        if (set(value)!=keys or value['schema']!='reviewed-observed-release-1.0'
                or value['project_id']!=self.project_id or value['room_revision']!=self.room_revision
                or scope['project_id']!=self.project_id or scope['goal']['room_revision']!=self.room_revision
                or any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{64}',value[k])
                       for k in keys-{'schema','project_id'})):
            raise ValueError('OBSERVED_REGISTRATION_CONTEXT')
        import sys
        scripts=str(self.source_root/'scripts')
        if scripts not in sys.path:sys.path.insert(0,scripts)
        from robot_source_identity import source_id
        if value['source_id']!=source_id(self.source_root):raise ValueError('OBSERVED_REGISTERED_SOURCE_CHANGED')
        # Review records only bind bytes; no invented calibration is generated.
        import hashlib
        package=self.source_root/'packages/twinpulse_robot_safety'
        for name,key in (('navigation-calibration.json','calibration_sha256'),
                         ('adaptive-qualification.json','qualification_sha256'),
                         ('adaptive-sensor-evidence.json','target_evidence_sha256')):
            member=package/name
            if member.is_symlink() or not member.is_file() or member.stat().st_size>16384:
                raise ValueError('OBSERVED_REVIEWED_EVIDENCE_MISSING')
            if hashlib.sha256(member.read_bytes()).hexdigest()!=value[key]:
                raise ValueError('OBSERVED_REVIEWED_EVIDENCE_CHANGED')
        return dict(value)
