# SPDX-License-Identifier: Apache-2.0
"""Stationary native-ring/wheel pairing; never independent body localization.

No devices, transport, model or execution. Receipt-bracketed field observations
retain unqualified acquisition timing and reviewed nominal sensor extrinsics.
"""
from copy import deepcopy
import math
import re
from uuid import uuid4
from .revisions import canonical_sha256

SCHEMA='physical-task-observation-1.0'
BASIS='SUPERVISED_STATIONARY_NATIVE_RECEIPT_WHEEL_ESTIMATE'


def number(v):return type(v) in (int,float) and math.isfinite(v)


def wheel_se2(pose):
    if (not isinstance(pose,dict) or pose.get('source')!='wheel_odom' or pose.get('independent_body') is not False
            or not isinstance(pose.get('position_m'),list) or len(pose['position_m'])!=3
            or not all(number(v) and abs(v)<1000 for v in pose['position_m'])
            or not number(pose.get('yaw_rad')) or not number(pose.get('sample_s'))
            or not isinstance(pose.get('frame_id'),str) or not pose['frame_id']):
        raise ValueError('TASK_WHEEL_SE2_REQUIRED')
    return [*pose['position_m'][:2],pose['yaw_rad']]


class StationaryTaskCollector:
    def __init__(self,context):
        self.context=deepcopy(context);self.epoch=uuid4().hex
        self.previous=None;self.fault=None;self.zero_since=None;self.zero_epoch=None;self.pose_valid=False

    def status(self):return dict(pose_epoch=self.epoch,fault=self.fault,pose_basis=BASIS,independent_body=False,pose_valid=self.pose_valid)

    def check_pose(self,pose,now,timing_values):
        self.pose_valid=False
        if self.fault:raise ValueError(self.fault)
        current=wheel_se2(pose)
        if not 0<=now-pose['sample_s']<=timing_values['odom_source_ms']/1000:
            raise ValueError('TASK_ODOM_STALE')
        if self.previous:
            old=self.previous;dt=pose['sample_s']-old['sample_s'];prior=wheel_se2(old)
            turn=abs(math.atan2(math.sin(current[2]-prior[2]),math.cos(current[2]-prior[2])))
            if (pose['frame_id']!=old['frame_id'] or dt<0
                    or math.dist(current[:2],prior[:2])>.03+.06*max(dt,0)
                    or turn>.05+.4*max(dt,0)):
                self.fault='TASK_ODOM_FRAME_OR_ORIGIN_CHANGED';raise ValueError(self.fault)
        self.previous=deepcopy(pose)
        self.pose_valid=True

    def sample(self,pose,frame,points,rows,config,now,motion_epoch,*,disabled,timing_values,stop_generation=0):
        self.check_pose(pose,now,timing_values)
        if not disabled:
            self.zero_since=None;self.zero_epoch=None
            raise ValueError('TASK_STATIONARY_STOP_REQUIRED')
        if self.zero_since is None or self.zero_epoch!=(motion_epoch,stop_generation):
            self.zero_since=now;self.zero_epoch=(motion_epoch,stop_generation)
        if not frame or not frame.get('complete') or frame.get('interval_fallback'):
            raise ValueError('TASK_COMPLETE_RING_REQUIRED')
        start,end=(frame['timing'][k] for k in ('receipt_start_s','receipt_end_s'))
        if not self.zero_since+.2<=start<=end<=now:
            raise ValueError('TASK_POST_STOP_RING_PENDING')
        # Caller validated complete original ring, source SHA, valid packet,
        # positive quality and its unchanged native-receipt age with frame_points.
        if len(points)<24 or len(points)>4096:raise ValueError('TASK_VALID_RETURNS_REQUIRED')
        observed=[]
        for row in rows:
            t=row.get('t');age=row.get('source_age_s');enc=row.get('encoders')
            if (not number(t) or not number(age) or age<0 or not isinstance(enc,(list,tuple))
                    or len(enc)!=2 or any(type(v) is not int for v in enc)):continue
            stamp=t-age
            if self.zero_since<=stamp<=now:observed.append((stamp,list(enc)))
        before=[r for r in observed if r[0]<=start];after=[r for r in observed if r[0]>=max(end,pose['sample_s'])]
        if not before or not after:raise ValueError('TASK_WHEEL_RING_BRACKETS_PENDING')
        a=max(before);b=min(after);window=[r for r in observed if a[0]<=r[0]<=b[0]]
        if (len(window)<2 or any(r[1]!=a[1] for r in window)
                or any(not 0<y[0]-x[0]<=timing_values['wheel_interval_ms']/1000 for x,y in zip(window,window[1:]))
                or pose['sample_s']<end):raise ValueError('TASK_WHEELS_NOT_STATIONARY_OVER_RING')
        stride=max(1,math.ceil(len(points)/512));selected=points[::stride]
        data=dict(schema=SCHEMA,scope=BASIS,context={k:self.context[k] for k in
            ('operation_id','robot_id','project_id','connection_epoch','boot_id','release_id','worker_sha256')},
            pose_epoch=self.epoch,motion_epoch=motion_epoch,stop_generation=stop_generation,produced_monotonic_s=now,
            pose=deepcopy(pose),scan=dict(stream_id=frame['stream_id'],frame_sequence=frame['frame_sequence'],
                raw_sha256=frame['raw_sha256'],nodes_sha256=frame['nodes_sha256'],timing=deepcopy(frame['timing']),
                source_byte_span=deepcopy(frame['source_byte_span']),complete=True),
            points_base=[list(p) for p in selected],native_valid_return_count=len(points),selected_return_stride=stride,
            sensor_origin_base=[config['sensor_x_m'],config['sensor_y_m']],
            config_sha256=canonical_sha256(config),config=deepcopy(config),
            timing_limits={k:timing_values[k] for k in ('native_receipt_ms','odom_source_ms','wheel_interval_ms')},
            stationary_wheels=dict(bracket_start_s=a[0],bracket_end_s=b[0],encoders=a[1],samples=len(window),rows=[[t,*enc] for t,enc in window]),
            independent_body=False,world_aligned=False,deskewed=False)
        data['sha256']=canonical_sha256(data)
        return data


def checked_observation(value):
    if not isinstance(value,dict):raise ValueError('TASK_OBSERVATION_REQUIRED')
    result=deepcopy(value);digest=result.pop('sha256',None)
    if (digest!=canonical_sha256(result) or result.get('schema')!=SCHEMA or result.get('scope')!=BASIS
            or any(result.get(k) is not False for k in ('independent_body','world_aligned','deskewed'))):
        raise ValueError('TASK_OBSERVATION_BINDING_INVALID')
    wheel_se2(result.get('pose'))
    points=result.get('points_base')
    if (not isinstance(points,list) or not 24<=len(points)<=4096
            or any(not isinstance(p,list) or len(p)!=2 or any(not number(v) or abs(v)>100 for v in p) for p in points)):
        raise ValueError('TASK_OBSERVATION_POINTS_INVALID')
    if canonical_sha256(result.get('config'))!=result.get('config_sha256'):
        raise ValueError('TASK_OBSERVATION_CONFIG_CHANGED')
    try:
        scan=result['scan'];timing=scan['timing'];start,end=timing['receipt_start_s'],timing['receipt_end_s']
        now=result['produced_monotonic_s'];sample=result['pose']['sample_s'];limits=result['timing_limits'];wheels=result['stationary_wheels']
        rows=wheels['rows'];native_count=result['native_valid_return_count'];stride=result['selected_return_stride']
        if (scan['complete'] is not True or not isinstance(scan['stream_id'],str) or not 1<=len(scan['stream_id'])<=128
                or type(scan['frame_sequence']) is not int or scan['frame_sequence']<1
                or any(not re.fullmatch('[a-f0-9]{64}',scan[k]) for k in ('raw_sha256','nodes_sha256'))
                or not all(number(v) for v in (start,end,now,sample)) or not 0<=start<=end<=sample<=now
                or any(type(limits[k]) is not int or not 50<=limits[k]<=1500 for k in ('native_receipt_ms','odom_source_ms','wheel_interval_ms'))
                or now-end>limits['native_receipt_ms']/1000 or now-sample>limits['odom_source_ms']/1000
                or type(native_count) is not int or not 24<=native_count<=4096 or type(stride) is not int
                or stride!=max(1,math.ceil(native_count/512)) or len(points)!=math.ceil(native_count/stride)
                or result['sensor_origin_base']!=[result['config']['sensor_x_m'],result['config']['sensor_y_m']]
                or type(result['stop_generation']) is not int or result['stop_generation']<0
                or not isinstance(rows,list) or not 2<=len(rows)<=1024 or wheels['samples']!=len(rows)
                or any(not isinstance(r,list) or len(r)!=3 or not number(r[0]) or any(type(v) is not int for v in r[1:]) or r[1:]!=wheels['encoders'] for r in rows)
                or not rows[0][0]==wheels['bracket_start_s']<=start<=end<=sample<=wheels['bracket_end_s']==rows[-1][0]<=now
                or any(not 0<b[0]-a[0]<=limits['wheel_interval_ms']/1000 for a,b in zip(rows,rows[1:]))):
            raise ValueError('TASK_OBSERVATION_NATIVE_PAIR_INVALID')
    except (KeyError,TypeError):raise ValueError('TASK_OBSERVATION_NATIVE_PAIR_INVALID') from None
    return dict(result,sha256=digest)
