# SPDX-License-Identifier: Apache-2.0
"""Full preserved raw chronology. No robot/App API/ROS/model calls."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from native_stream import NativeDecoder,NativeStream
from field_tests import control_observation,tracking_observation,FieldGuard


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    folder=ROOT/'outputs/robot-retest-20261018/analysis'
    raw=(folder/'native-original.raw').read_bytes();sha=hashlib.sha256(raw).hexdigest()
    assert sha=='7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522'
    chunks=json.loads((folder/'native-chunks.json').read_text());now=[0.]
    config=dict(angle_sign=1,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.,footprint_radius_m=.12,
        wheel_separation_m=.16,wheel_metres_per_tick=2*3.141592653589793*.033/4096)
    rows=[];directions=collections.defaultdict(collections.Counter);began=time.perf_counter()
    class Replay(NativeStream):
        def _frame(self,*args,**kwargs):
            super()._frame(*args,**kwargs);frame=self.latest_frame()
            row=dict(frame=frame['frame_sequence'],raw_complete=frame['complete'],raw_sha256=frame['raw_sha256'],
                nodes_sha256=frame['nodes_sha256'],unknown_bytes=frame['quality']['unframed_bytes'])
            try:
                selected,_,partial,_=control_observation(self,config,now[0])
                row.update(observation='CURRENT_STRICT' if partial is None else 'LAST_STRICT_ORIGINAL_AGE_WITH_CURRENT_STOP_VETO',
                    used_frame=selected['frame_sequence'],used_age_s=now[0]-selected['timing']['receipt_end_s'])
            except ValueError as exc:row.update(observation='REJECTED',reason=str(exc))
            try:
                observation=tracking_observation(self,config,now[0])
                row['tracking_input']='COMPLETE_ONLY' if observation is not None else 'SKIPPED_UNKNOWN_NO_POSE_TIME_RENEWAL'
            except ValueError as exc:row['tracking_input']='REJECTED:'+str(exc)
            for name,v,w in [('forward',.03,0),('backward',-.03,0),('left',0,.2),('right',0,-.2)]:
                link=SimpleNamespace(sensor_t=now[0],sensor=SimpleNamespace(left_encoder=0,right_encoder=0))
                guard=FieldGuard(config,self,link,lambda:True,clock=lambda:now[0])
                try:guard(v,w,now[0]);decision='OBSERVATION_ACCEPTED'
                except ValueError as exc:decision=str(exc)
                directions[name][decision]+=1
            rows.append(row)
    stream=Replay('.',lambda *_:None,clock=lambda:now[0]);stream.stream_id='offline-original-not-hardware'
    stream.state['lidar_state']='STREAMING';decoder=NativeDecoder()
    for chunk in chunks:
        data=raw[chunk['offset']:chunk['offset']+chunk['length']]
        assert hashlib.sha256(data).hexdigest()==chunk['sha256'];now[0]=chunk['receipt_end_s']
        stream._accept_packets(decoder.feed(data,now[0]))
    incomplete=[r for r in rows if not r['raw_complete']]
    held=[r for r in incomplete if r['observation']=='LAST_STRICT_ORIGINAL_AGE_WITH_CURRENT_STOP_VETO']
    sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'packages/twinpulse_robot_safety/native_stream.py','packages/twinpulse_robot_safety/field_tests.py','packages/twinpulse_robot_safety/fleet_control.py')}
    result=dict(schema='control-observation-replay-1.0',classification='OFFLINE_SAVED_INPUT_NOT_PI_OR_PHYSICAL_ACCEPTANCE',
        status='PASS' if (len(rows)==6081 and len(incomplete)==202 and len(held)==201 and decoder.errors==0
            and sum(r['tracking_input']=='SKIPPED_UNKNOWN_NO_POSE_TIME_RENEWAL' for r in rows)==201
            and not any(not r['raw_complete'] and r['tracking_input']=='COMPLETE_ONLY' for r in rows)) else 'FAIL',
        raw_sha256=sha,raw_bytes=len(raw),chunks=len(chunks),frames=len(rows),strict_incomplete=len(incomplete),
        unknown_bytes=decoder.noise_bytes,checksum_errors=decoder.errors,pending_bytes=len(decoder.buffer),
        retained_complete_observations=len(held),rejected_incomplete=[r for r in incomplete if r not in held],
        tracking_inputs=dict(collections.Counter(r['tracking_input'] for r in rows)),
        held_age_max_ms=max((r['used_age_s'] for r in held),default=0)*1000,
        held_age_mean_ms=statistics.mean(r['used_age_s'] for r in held)*1000 if held else None,
        directions=dict(directions),rows=rows,source_sha256=sources,elapsed_s=time.perf_counter()-began,
        limits='No Pi load, DDS, physical braking or movement claim. Current unknown rings remain incomplete. Directional unknown/proximity reasons remain real rejections, not counted as successful driving.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','source_sha256')},indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
