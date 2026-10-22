# SPDX-License-Identifier: Apache-2.0
"""Read-only replay of preserved real sensor/odometry; no robot/model calls."""
from pathlib import Path
from statistics import median
import hashlib
import json
import math
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/robot-powered-20261020-guard05'
OUT=ROOT/'outputs/robot-powered-20261021-report'
for directory in ('packages/twinpulse_robot_safety','packages/twinpulse_core/src'):
    sys.path.insert(0,str(ROOT/directory))
from field_tests import register_pair

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def degrees(radians):return math.degrees(math.remainder(radians,math.tau))
def fit(before,after):
    evidence=dict(before_frame=before['frame_sequence'],after_frame=after['frame_sequence'],
        before_sha256=before['raw_sha256'],after_sha256=after['raw_sha256'],
        before_receipt_s=before['timing']['receipt_end_s'],after_receipt_s=after['timing']['receipt_end_s'],
        method='Existing unseeded register_pair, original complete sensor-local points; offline PC replay',
        accuracy='UNQUALIFIED_NOT_MEASURED_BODY_DISPLACEMENT')
    try:
        result=register_pair(before['points'],after['points'],deadline=time.monotonic()+.08)
        dx,dy,yaw=result['delta']
        evidence.update(status='ESTIMATED',dx_mm=dx*1000,dy_mm=dy*1000,
            translation_mm=math.hypot(dx,dy)*1000,yaw_deg=degrees(yaw),residual_mm=result['residual_m']*1000)
    except ValueError as error:evidence.update(status='INCONCLUSIVE',reason=str(error))
    return evidence

def pose_between(poses,start,end):
    values=[p for p in poses if start<=p['sample_s']<=end]
    if not values:return None
    if len({p['frame_id'] for p in values})!=1:return None
    return dict(x=median(p['x'] for p in values),y=median(p['y'] for p in values),
        yaw=median(p['yaw'] for p in values),samples=len(values),
        first_sample_s=values[0]['sample_s'],last_sample_s=values[-1]['sample_s'],frame_id=values[0]['frame_id'])

def main():
    receipt=read(SOURCE/'receipt.json');poses={};scans={};publications=[];pauses=[];inputs=[]
    for member in receipt['segments']:
        raw=(SOURCE/member['path']).read_bytes()
        assert len(raw)==member['bytes'] and hashlib.sha256(raw).hexdigest()==member['sha256']
        for line in raw.splitlines():
            event=json.loads(line);data=event.get('data',{});kind=event.get('kind');at=event.get('robot_monotonic_s')
            if kind=='heartbeat':
                pose=data.get('pose')
                if pose and pose.get('sample_s') is not None:poses[pose['sample_s']]=pose
            elif kind=='scan' and data.get('complete') is True:
                scans[(data['stream_id'],data['frame_sequence'])]=data
            elif kind=='command' and data.get('status')=='PUBLISHED' and data.get('direction'):
                publications.append(dict(sequence=event['sequence'],at=at,**data))
            elif kind=='control_pause':pauses.append(dict(sequence=event['sequence'],at=at,**data))
            if event.get('schema','').startswith('physical-live-pc-command') and event.get('action')=='drive':inputs.append(event)
    poses=sorted(poses.values(),key=lambda p:p['sample_s'])
    scans=sorted(scans.values(),key=lambda s:s['timing']['receipt_end_s'])
    rows=[]
    for direction in ('forward','backward','left','right'):
        pubs=[p for p in publications if p['direction']==direction]
        if not pubs:
            rows.append(dict(direction=direction,status='NO_PUBLISHED_COMMAND_EVIDENCE'));continue
        first,last=pubs[0]['at'],pubs[-1]['at']
        stop=next((p for p in pauses if p['at']>=last),None)
        if stop is None:raise ValueError('Missing original stop')
        before=pose_between(poses,first-.45,first-.02)
        after=pose_between(poses,stop['at']+.15,stop['at']+.65)
        row=dict(direction=direction,first_publish_s=first,last_publish_s=last,
            publication_count=len(pubs),published_span_ms=(last-first)*1000,
            pause_sequence=stop['sequence'],pause_reason=stop['reason'],pause_after_release_s=stop['at'],
            zero_off_readback_confirmed=stop['zero_off_readback_confirmed'],
            pose_before=before,pose_after=after,
            commanded_linear_m_s=pubs[0].get('linear_m_s'),commanded_angular_rad_s=pubs[0].get('angular_rad_s'))
        if before and after and before['frame_id']==after['frame_id']:
            dx,dy=after['x']-before['x'],after['y']-before['y']
            row['wheel_odometry']=dict(dx_mm=dx*1000,dy_mm=dy*1000,translation_mm=math.hypot(dx,dy)*1000,
                signed_forward_mm=(dx*math.cos(before['yaw'])+dy*math.sin(before['yaw']))*1000,
                yaw_deg=degrees(after['yaw']-before['yaw']),scope='WHEEL_ODOM_ESTIMATE_NOT_INDEPENDENT_CHASSIS_MEASUREMENT')
        before_scan=next((s for s in reversed(scans) if s['timing']['receipt_end_s']<=first-.05),None)
        after_scan=next((s for s in scans if s['timing']['receipt_start_s']>=stop['at']+.15),None)
        if before_scan and after_scan and before_scan['stream_id']==after_scan['stream_id']:
            row['lidar_pair']=fit(before_scan,after_scan)
        rows.append(row)
    trials=read(SOURCE/'exported-sources/field-trials.json')['trials']
    stationary=next(t for t in trials if t['case']=='stationary')
    baseline=[]
    for offset in (.3,1.2,2.1,3.,3.9,4.8):
        before=next(s for s in scans if s['timing']['receipt_start_s']>=stationary['started_s']+offset)
        after=next(s for s in scans if s['timing']['receipt_start_s']>=before['timing']['receipt_end_s']+1.2)
        if after['timing']['receipt_end_s']<=stationary['ended_s']:baseline.append(fit(before,after))
    stationary_poses=[p for p in poses if stationary['started_s']<=p['sample_s']<=stationary['ended_s']]
    good=[r for r in baseline if r['status']=='ESTIMATED']
    result=dict(schema='saved-sensor-motion-analysis-1.0',operation_id='65fe078b1975404886704c2df728a33f',
        raw_receipt_sha256=hashlib.sha256((SOURCE/'receipt.json').read_bytes()).hexdigest(),
        source_archive_verified=True,records_saved=receipt['saved'],poses=len(poses),complete_scan_frames=len(scans),
        motion_windows=rows,stationary_lidar_pairs=baseline,
        stationary_lidar_median_translation_mm=median(r['translation_mm'] for r in good) if good else None,
        stationary_lidar_max_translation_mm=max((r['translation_mm'] for r in good),default=None),
        stationary_wheel_position_span_mm=(math.hypot(max(p['x'] for p in stationary_poses)-min(p['x'] for p in stationary_poses),
            max(p['y'] for p in stationary_poses)-min(p['y'] for p in stationary_poses))*1000 if stationary_poses else None),
        interpretation='Changed scan bytes do not alone prove body motion. Wheel odometry and unseeded LiDAR fit are separate evidence; low/noisy small motion remains inconclusive. No new robot connection, SDK or cloud call.')
    OUT.mkdir(exist_ok=True)
    (OUT/'sensor-motion-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(windows=[{k:r.get(k) for k in ('direction','publication_count','published_span_ms','pause_reason','wheel_odometry','lidar_pair')} for r in rows],
        baseline_median_mm=result['stationary_lidar_median_translation_mm'],baseline_max_mm=result['stationary_lidar_max_translation_mm'],stationary_wheel_span_mm=result['stationary_wheel_position_span_mm']),ensure_ascii=False))

if __name__=='__main__':main()
