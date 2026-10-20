# SPDX-License-Identifier: Apache-2.0
"""Hash-checked, device-free examination of the original powered failures.

CDR fields follow ROBOTIS-GIT/turtlebot3_msgs humble/msg/SensorState.msg.
This reads saved bytes only. Missing samples never become a physical Stop PASS.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
SCHEMA_URL='https://raw.githubusercontent.com/ROBOTIS-GIT/turtlebot3_msgs/humble/msg/SensorState.msg'


def decode_sensor(raw):
    if raw[:4]!=b'\0\1\0\0':raise ValueError('CDR_REPRESENTATION')
    length=struct.unpack_from('<I',raw,12)[0]
    if not 1<=length<=4096 or raw[16+length-1]!=0:raise ValueError('CDR_HEADER_STRING')
    pos=16+length+1  # Header, then bumper uint8.
    pos+=(-(pos-4))%4
    pos+=12  # cliff, sonar, illumination float32.
    led,button,torque=struct.unpack_from('<BBB',raw,pos);pos+=3
    if torque not in (0,1):raise ValueError('CDR_BOOL')
    pos+=(-(pos-4))%4
    left,right,voltage=struct.unpack_from('<iif',raw,pos)
    if pos+12!=len(raw):raise ValueError('CDR_SENSOR_TRAILING_BYTES')
    return dict(encoders=[left,right],torque=bool(torque),voltage_v=voltage,button=button)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    attempts=[]
    for number in (1,2,3):
        directory=ROOT/f'outputs/robot-powered-20261019-current{number:02d}'
        receipt=json.loads((directory/'native-original/receipt.json').read_text())
        op=json.loads((directory/'failure-final-operation.json').read_text())['operation_id']
        sensors=[];commands=[];heartbeats=[];sources=[];decode_errors=[]
        for segment in receipt['segments']:
            source=directory/'native-original'/segment['path']
            with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=segment['sha256']:raise ValueError('ORIGINAL_SEGMENT_SHA_CHANGED')
            sources.append(dict(path=str(source),sha256=digest,bytes=source.stat().st_size))
            for line in source.open('rb'):
                event=json.loads(line);data=event.get('data',{});t=event.get('robot_monotonic_s')
                if event.get('kind')=='command':commands.append(dict(t=t,**data))
                if event.get('kind')=='heartbeat':heartbeats.append(dict(t=t,**data))
                if event.get('kind')=='raw' and data.get('topic')=='sensor_state':
                    raw=base64.b64decode(data['base64'],validate=True)
                    if hashlib.sha256(raw).hexdigest()!=data['sha256']:raise ValueError('ORIGINAL_CDR_SHA_CHANGED')
                    try:sensors.append(dict(t=data['receipt_start_s'],**decode_sensor(raw)))
                    except (ValueError,struct.error,IndexError) as exc:decode_errors.append(str(exc))
        trials={c['trial']['trial_id']:c['trial'] for c in commands if c.get('trial',{}).get('case')=='bootstrap_stop'}
        for trial in trials.values():
            start=trial['started_s'];end=trial.get('ended_s',start)
            cleanup=next((h['t'] for h in heartbeats if start<h['t']<=end and h.get('maintenance_phase')=='CLEANUP'),end)
            selected=[s for s in sensors if start<=s['t']<=end]
            anchor=None;changed=None
            for s in sensors:
                if s['t']>end:break
                if anchor is None or any(abs(a-b)>2 for a,b in zip(anchor,s['encoders'])):
                    anchor=s['encoders'];changed=s['t']
            latest=selected[-1] if selected else None
            stable=latest['t']-changed if latest and changed is not None else None
            attempts.append(dict(attempt=number,operation_id=op,trial_id=trial['trial_id'],
                source_manifest=sources,decode_errors=decode_errors,decoded_sensor_count=len(sensors),
                original_result=trial.get('result'),bootstrap_sensors=selected,
                cleanup_first_report_s=cleanup,last_sensor=latest,last_encoder_anchor_change_s=changed,
                stable_at_last_original_sensor_s=stable,
                original_200ms_stability_observed=stable is not None and stable>=.2,
                qualification_watches=[dict(t=c['t'],request_id=c['request_id']) for c in commands
                    if start<=c['t']<cleanup and c.get('action')=='watch' and c.get('status')=='COMPLETED'],
                missing='Original nonce issue/accept/deadline at expiry and later sensor observations are unavailable.',
                verdict='ORIGINAL_INPUT_REPLAY_ONLY_NOT_PHYSICAL_QUALIFICATION'))
    result=dict(schema='powered-input-stop-replay-1.0',status='PASS_ORIGINAL_BYTES_VERIFIED',
        robot_calls=0,source_schema=SCHEMA_URL,attempts=attempts,
        scope='Exact saved CDR and encoder reconstruction. No missing samples extrapolated; no service ACK invented.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=result['status'],attempts=[dict(attempt=a['attempt'],
        sensors=a['decoded_sensor_count'],stable_last_s=a['stable_at_last_original_sensor_s'],
        decode_errors=len(a['decode_errors'])) for a in attempts])))


if __name__=='__main__':main()
