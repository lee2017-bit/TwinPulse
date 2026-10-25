# SPDX-License-Identifier: Apache-2.0
"""Derived stationary-pair eligibility from original recorded native/CDR bytes.

Reconstructed callback rows are NOT original link rows or a live task packet.
No robot, authority, USD alignment, noise qualification or body-motion claim.
"""
import argparse
import base64
from collections import Counter,deque
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'packages/twinpulse_robot_safety')]
from twinpulse_core.physical_task_observation import StationaryTaskCollector,checked_observation
from twinpulse_core.robot_timing_profile import values_of
from native_stream import NativeDecoder,NativeStream
from field_tests import frame_points
from verify_powered_input_stop_replay import decode_sensor

parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
out=ROOT/'outputs/physical-task-preparation-20261025-01'/('original-replay'+args.attempt);out.mkdir(parents=True,exist_ok=False)
source=ROOT/'outputs/robot-auto-charged-20261024-01/raw/db929f4ad15e418e88ddd71a85ea55f6'
receipt=json.loads((source/'receipt.json').read_bytes());first=None;collector=None;now=[0.]
sensors=deque(maxlen=512);streams={};counts=Counter();rejections=Counter();examples=[];source_files=[]

class ReplayNative(NativeStream):
    def __init__(self,identity):
        super().__init__(out/'unused-no-device',lambda *_:None,clock=lambda:now[0]);self.stream_id=identity;self.frames=deque(maxlen=128)
    def _frame(self,*a,**kw):
        super()._frame(*a,**kw);self.frames.append(self.latest_frame())

for segment in receipt['segments']:
    path=source/segment['path']
    if path.is_symlink() or path.resolve().parent!=source.resolve():raise ValueError('ORIGINAL_MEMBER_PATH')
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        for line in stream:
            h.update(line);size+=len(line);counts['events']+=1
            e=json.loads(line);d=e.get('data') or {};kind=e.get('kind');now[0]=e.get('robot_monotonic_s',now[0])
            if first is None:
                first=e
                if first.get('operation_id')!=source.name:raise ValueError('ORIGINAL_OPERATION')
                continue
            if not str(e.get('schema','')).startswith('physical-live-event-'):continue
            if any(e.get(k)!=first.get(k) for k in ('operation_id','robot_id','project_id','connection_epoch')):raise ValueError('ORIGINAL_EVENT_IDENTITY')
            if kind=='raw':
                raw=base64.b64decode(d['base64'],validate=True)
                if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('ORIGINAL_RAW_SHA')
                if d.get('source')=='serialized_ros_message':
                    if d.get('topic')=='sensor_state':
                        try:
                            value=decode_sensor(raw);age=d.get('callback_timing',{}).get('source_age_at_receipt_s')
                            if type(age) not in (int,float) or age<0:raise ValueError('ORIGINAL_SENSOR_SOURCE_AGE_UNKNOWN')
                            sensors.append(dict(t=d['receipt_start_s'],source_age_s=age,encoders=value['encoders']))
                            counts['decoded_sensor_cdr']+=1
                        except (ValueError,KeyError) as exc:rejections[str(exc)]+=1
                    continue
                identity=d['stream_id']
                if identity not in streams:streams[identity]=(ReplayNative(identity),NativeDecoder(),0)
                native,decoder,offset=streams[identity]
                if d['offset']!=offset:raise ValueError('ORIGINAL_NATIVE_BYTE_GAP')
                packets=decoder.feed(raw,d['receipt_end_s']);native._accept_packets(packets)
                streams[identity]=(native,decoder,offset+len(raw));counts['native_chunks']+=1
            if kind!='heartbeat':continue
            counts['heartbeats']+=1
            config=(d.get('field') or {}).get('config');native_observation=(d.get('field') or {}).get('native_observation') or {}
            if not config or not d.get('pose'):continue
            if collector is None:
                ctx={**{k:first[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},**{k:d[k] for k in ('boot_id','release_id','worker_sha256')}}
                collector=StationaryTaskCollector(ctx)
            try:
                timing=values_of(d.get('timing_values'));collector.check_pose(d['pose'],now[0],timing)
                native=streams[native_observation['stream_id']][0]
                frame=next(f for f in reversed(native.frames) if f['raw_sha256']==native_observation['raw_sha256'] and f['frame_sequence']==native_observation['frame_sequence'])
                points=frame_points(frame,config,now[0],timing_values=timing)
                command=d.get('command') or {}
                disabled=d.get('control_state')=='PAUSED' and command.get('state')=='COMPLETED' and command.get('stop_readback_confirmed') is True
                packet=collector.sample(d['pose'],frame,points,list(sensors),config,now[0],d.get('applied_motion_epoch'),
                    disabled=disabled,timing_values=timing,stop_generation=d.get('motion_generation',0))
                checked_observation(packet);counts['eligible_stationary_pairs']+=1
                if len(examples)<3:
                    name='derived-pair-%02d.json'%(len(examples)+1)
                    (out/name).write_text(json.dumps(dict(original_event_sequence=e['sequence'],original_segment=segment['path'],derived_packet=packet,
                        scope='OFFLINE_RECONSTRUCTED_CALLBACK_ROWS_NOT_AN_ORIGINAL_OR_LIVE_TASK_PACKET'),indent=2),encoding='utf-8')
                    examples.append(name)
            except (ValueError,KeyError,StopIteration) as exc:rejections[str(exc) or type(exc).__name__]+=1
    if h.hexdigest()!=segment['sha256'] or size!=segment['bytes']:raise ValueError('ORIGINAL_SEGMENT_SHA')
    source_files.append(dict(path=str(path.relative_to(ROOT)),bytes=size,sha256=h.hexdigest()))
value=dict(status='REPLAYED_WITH_LIMITS',scope='OFFLINE_ORIGINAL_INPUT_ELIGIBILITY_NOT_LIVE_TASK_OR_HARDWARE_ACCEPTANCE',
    counts=dict(counts),rejections=dict(rejections),examples=examples,originals=source_files,
    receipt_sha256=hashlib.sha256((source/'receipt.json').read_bytes()).hexdigest(),
    original_error=receipt.get('error'),original_complete=receipt.get('complete'),
    callback_row_basis='ORIGINAL_RAW_CALLBACK_RECEIPT_AND_SOURCE_AGE_NOT_EXACT_LINK_ROW_T',
    body_motion='UNQUALIFIED_UNKNOWN',world_aligned=False,authority_restored=False,physical_actions=0)
(out/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in value.items() if k not in {'originals','examples'}}))
