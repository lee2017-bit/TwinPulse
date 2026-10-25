# SPDX-License-Identifier: Apache-2.0
"""Verify preserved sensor-only acquisition; never connects or controls hardware."""
import collections
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-data-priority-20261025-01'
OP='26d7df336660467eb6168ab12215a8d7'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
RAW=RUNTIME/'devices/local/physical-live'/OP
read=lambda p:json.loads(p.read_bytes())
receipt=read(RAW/'receipt.json');kinds=collections.Counter();actions=collections.Counter();parts=[]
heartbeat_count=0;pose_count=0;latest_cleanup=None;scan_times=[];scan_counts=[]
for part in receipt['segments']:
    path=RAW/part['path'];digest=hashlib.sha256();size=0;count=0
    with path.open('rb') as stream:
        for line in stream:
            count+=1;size+=len(line);digest.update(line);event=json.loads(line)
            kind=event.get('kind');kinds[kind]+=1;data=event.get('data') or {}
            if event.get('schema','').startswith('physical-live-pc-command'):
                actions[event.get('action')]+=1
            if kind=='heartbeat':
                heartbeat_count+=1
                if data.get('pose'):pose_count+=1
            if kind=='scan':
                scan_times.append(event.get('robot_monotonic_s'))
                scan=data.get('scan',data);scan_counts.append(len(scan.get('points') or []))
            if kind=='cleanup' and data.get('subsystem')=='session':latest_cleanup=data
    parts.append(dict(path=part['path'],events=count,bytes=size,sha256=digest.hexdigest(),
        exact=count==part['events'] and size==part['bytes'] and digest.hexdigest()==part['sha256']))
ui=read(OUT/'ui-actions01.json');final=read(OUT/'final-fleet01.json')
robot=next(r for r in final['robots'] if r['robot_id']=='2bf518f09a234dd5b65c312febda8841')
launch=read(OUT/'runtime-copies01/afc3786f48dc4a9e92a106189190c5f0/cleanup-receipt.json')
checks=dict(original_complete=receipt['complete'] and receipt['accepted']==receipt['saved']==receipt['event_count']==sum(r['events'] for r in parts),
    all_segments_exact=all(r['exact'] for r in parts),no_motion_requests=not any(actions[k] for k in ('prepare','field_arm','field_test','drive','task')),
    only_sensor_ui_actions=all(e['request']['action'] in {'connect','stop','lidar','disconnect'} for e in ui['events']),
    sensor_off_disconnected=robot['connection_state']=='DISCONNECTED' and robot['lidar_state']=='OFF',
    normal_owned_exit=launch['owned_processes_stopped'])
times=[x for x in scan_times if isinstance(x,(int,float))]
value=dict(status='PASS_STATIONARY_ACQUISITION_ONLY' if all(checks.values()) else 'FAIL',checks=checks,
    scope='REAL_NATIVE_SENSOR_ONLY_NOT_MOVING_SURVEY_ODOMETRY_CALIBRATION_OR_STOP_QUALIFICATION',operation_id=OP,
    original_directory=str(RAW),original_receipt_sha256=hashlib.sha256((RAW/'receipt.json').read_bytes()).hexdigest(),
    events=receipt['event_count'],bytes=sum(r['bytes'] for r in parts),segments=parts,kinds=dict(kinds),pc_actions=dict(actions),
    heartbeat_count=heartbeat_count,heartbeats_with_pose=pose_count,scan_event_count=len(scan_times),
    scan_span_s=max(times)-min(times) if times else None,maximum_points=max(scan_counts,default=0),
    cleanup=latest_cleanup,
    limitations=['No Prepare/Arm or wheel command was issued. New wheel odometry is not implied by a LiDAR stream.',
        'Explicit Stop on the unprepared controller reported TASK_STOP_READBACK_UNCONFIRMED; not promoted to qualified Stop.',
        'Stationary data cannot supply whole-room moving coverage. Earlier moving/failed-session data remains separate.'])
(OUT/'data-result01.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps({k:value[k] for k in ('status','checks','events','bytes','heartbeat_count','heartbeats_with_pose','scan_event_count','scan_span_s','maximum_points')}))
