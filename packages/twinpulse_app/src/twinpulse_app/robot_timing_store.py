# SPDX-License-Identifier: Apache-2.0
"""Local per-instance sidecars; old registry readers remain compatible."""
from copy import deepcopy
import json
import re
from twinpulse_core.robot_timing_profile import profile, checked_profile, checked_measurement, digest, recommendation, FIELDS
from .release_contract import atomic_json


class RobotTimingStore:
    def __init__(self, root):
        self.root=root/'robot-timing-profiles'

    def _path(self, robot_id):
        if not re.fullmatch('[a-f0-9]{32}',str(robot_id)):raise ValueError('TIMING_ROBOT_INVALID')
        if self.root.is_symlink():raise ValueError('TIMING_STORAGE_INVALID')
        return self.root/(robot_id+'.json')

    def read(self, robot_id, binding_sha256):
        path=self._path(robot_id)
        if path.is_symlink():raise ValueError('TIMING_STORAGE_INVALID')
        if not path.exists():
            p=profile(robot_id,binding_sha256)
            return dict(profile=p,profile_sha256=digest(p),measurement=None,recommendation=None,
                apply_policy='NEXT_EXPLICIT_CONNECTION_ONLY',last_measurement_origin=None,
                measurement_operation_id=None,measurement_sha256=None,recommendation_origin=None,recommendation_sha256=None)
        if path.stat().st_size>262144:raise ValueError('TIMING_STORAGE_INVALID')
        value=json.loads(path.read_text(encoding='utf-8'))
        checked_profile(value['profile'],robot_id=robot_id,binding_sha256=binding_sha256)
        if value['profile_sha256']!=digest(value['profile']):raise ValueError('TIMING_STORAGE_DIGEST')
        # Preserve old recommendations, but never recalculate them on read.
        # Recover old measurement provenance only when its original digest matches.
        rec=value.get('recommendation');e=(rec or {}).get('profile',{}).get('evidence') or {}
        if 'measurement_operation_id' not in value:
            value['measurement_operation_id']=(e.get('operation_id') if value.get('measurement') is not None
                and e.get('measurement_sha256')==digest(value['measurement']) else None)
        value.setdefault('recommendation_origin','LEGACY_AUTOMATIC' if rec else None)
        value['recommendation_sha256']=digest(rec) if rec else None
        value['measurement_sha256']=digest(value['measurement']) if value.get('measurement') is not None else None
        return value

    def write(self,value):
        p=checked_profile(value['profile'])
        value=dict(deepcopy(value),profile_sha256=digest(p),apply_policy='NEXT_EXPLICIT_CONNECTION_ONLY')
        value['recommendation_sha256']=digest(value['recommendation']) if value.get('recommendation') else None
        value['measurement_sha256']=digest(value['measurement']) if value.get('measurement') is not None else None
        version=self.root/p['robot_id']/(value['profile_sha256']+'.json')
        if any(q.is_symlink() for q in (version,version.parent,self.root)):raise ValueError('TIMING_STORAGE_INVALID')
        if version.exists():
            if version.stat().st_size>65536 or json.loads(version.read_text(encoding='utf-8'))!=p:raise ValueError('TIMING_VERSION_CHANGED')
        else:atomic_json(version,p)
        atomic_json(self._path(p['robot_id']),value)
        return value

    def record(self,robot_id,binding_sha256,operation_id,measurement,*,origin):
        current=self.read(robot_id,binding_sha256)
        if not isinstance(operation_id,str) or not re.fullmatch('[a-f0-9]{32}',operation_id):raise ValueError('TIMING_EVIDENCE_SHAPE')
        measurement=checked_measurement(measurement)
        # Only initial registration may calculate and register a baseline
        # automatically. Once initialized (or manually edited), observations
        # update neither registered values nor the last explicit recommendation.
        if current['profile']['mode']=='unmeasured':
            rec=recommendation(measurement,robot_id,binding_sha256,operation_id)
            if not rec['capped_fields'] and not rec['invalid_metrics']:
                current['profile']=rec['profile']
        current.update(measurement=measurement,measurement_operation_id=operation_id,last_measurement_origin=origin)
        return self.write(current)

    def recalculate(self,robot_id,binding_sha256):
        current=self.read(robot_id,binding_sha256)
        if current.get('measurement') is None or not current.get('measurement_operation_id'):
            raise ValueError('TIMING_MEASUREMENT_REQUIRED')
        current['recommendation']=recommendation(current['measurement'],robot_id,binding_sha256,current['measurement_operation_id'])
        current['recommendation_origin']='MANUAL_RECALCULATION'
        return self.write(current)

    def edit(self,robot_id,binding_sha256,values,mode,expected_sha256,expected_recommendation_sha256=None):
        current=self.read(robot_id,binding_sha256)
        if current['profile_sha256']!=expected_sha256:raise ValueError('ROBOT_REGISTRY_CHANGED')
        if mode=='measured_default':
            rec=current.get('recommendation')
            if not rec or rec['capped_fields'] or rec.get('invalid_metrics'):raise ValueError('TIMING_MEASUREMENT_REQUIRED')
            if digest(rec)!=expected_recommendation_sha256:raise ValueError('ROBOT_REGISTRY_CHANGED')
            current['profile']=checked_profile(rec['profile'],robot_id=robot_id,binding_sha256=binding_sha256)
        elif mode=='custom':
            current['profile']=profile(robot_id,binding_sha256,values=values,mode='custom',evidence=current['profile']['evidence'])
        else:raise ValueError('TIMING_MODE')
        return self.write(current)

    @staticmethod
    def fields():
        return {k:dict(minimum_ms=v[0],maximum_ms=v[1],preset_ms=v[2],label=v[3]) for k,v in FIELDS.items()}
