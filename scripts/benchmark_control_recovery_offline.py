# SPDX-License-Identifier: Apache-2.0
"""Stage ablation of preserved bytes on Windows. No ROS/device/App/model calls."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from native_stream import NativeDecoder,NativeStream
from field_tests import NativeTracker,frame_points,register_pair

def stats(rows):
    values=sorted(rows)
    return dict(n=len(values),mean_ms=statistics.mean(values)*1000,sd_ms=statistics.stdev(values)*1000 if len(values)>1 else 0,
        p50_ms=statistics.median(values)*1000,p95_ms=values[math.ceil(len(values)*.95)-1]*1000,
        p99_ms=values[math.ceil(len(values)*.99)-1]*1000,maximum_ms=max(values)*1000)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    folder=ROOT/'outputs/robot-retest-20261018/analysis'
    raw=(folder/'native-original.raw').read_bytes();sha=hashlib.sha256(raw).hexdigest()
    assert sha=='7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522'
    chunks=json.loads((folder/'native-chunks.json').read_text());config=dict(angle_sign=1,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.)
    stages={};pairs=[];clock=[0.]
    class Observed(NativeStream):
        def __init__(self):
            super().__init__('.',lambda *_:None,clock=lambda:clock[0]);self.stream_id='offline-only';self.before=None;self.incomplete=0;self.build=[];self.rows=[]
        def _frame(self,*a,**kw):
            began=time.perf_counter();super()._frame(*a,**kw);self.build.append(time.perf_counter()-began)
            frame=self.latest_frame();self.incomplete+=int(not frame['complete']);self.rows.append((frame['raw_sha256'],frame['nodes_sha256'],frame['complete']))
            if frame['complete'] and self.before is not None and self.before['complete'] and frame['frame_sequence']%100==0:
                pairs.append((self.before,frame))
            self.before=frame
    for mode in ('decode_only','decode_and_frame'):
        decoder=NativeDecoder();stream=Observed() if mode.endswith('frame') else None;times=[];packets=nodes=0;began=time.perf_counter()
        for chunk in chunks:
            data=raw[chunk['offset']:chunk['offset']+chunk['length']];assert hashlib.sha256(data).hexdigest()==chunk['sha256'];clock[0]=chunk['receipt_end_s']
            start=time.perf_counter();rows=decoder.feed(data,clock[0]);packets+=len(rows);nodes+=sum(len(p['nodes']) for p in rows)
            if stream is not None:stream._accept_packets(rows)
            times.append(time.perf_counter()-start)
        stages[mode]=dict(wall_s=time.perf_counter()-began,chunk_processing=stats(times),packets=packets,nodes=nodes,
            packet_bytes=decoder.packet_bytes,unknown_bytes=decoder.noise_bytes,pending_bytes=len(decoder.buffer),checksum_errors=decoder.errors)
        if stream is not None:
            stages[mode].update(frame_build=stats(stream.build),frames=len(stream.rows),incomplete=stream.incomplete,
                frame_identity_sha256=hashlib.sha256(json.dumps(stream.rows,separators=(',',':')).encode()).hexdigest())
    tracker=NativeTracker(SimpleNamespace(latest_frame=lambda:None),config);serial_times=[];child_times=[];delivery_times=[];results=[]
    try:
        time.sleep(.35)
        for before,after in pairs:
            p=frame_points(before,config,before['timing']['receipt_end_s']);q=frame_points(after,config,after['timing']['receipt_end_s'])
            start=time.monotonic()
            try:serial=dict(ok=True,fit=register_pair(p,q,deadline=start+.08))
            except ValueError as exc:serial=dict(ok=False,reason=str(exc))
            serial_times.append(time.monotonic()-start);start=time.monotonic()
            try:child=dict(ok=True,fit=tracker._fit(p,q))
            except ValueError as exc:child=dict(ok=False,reason=str(exc))
            delivery_times.append(time.monotonic()-start);timing=dict(tracker.compute_timing)
            if 'compute_elapsed_s' in timing:child_times.append(timing['compute_elapsed_s'])
            results.append(dict(frame=after['frame_sequence'],serial=serial,child=child,timing=timing,exact=serial==child))
    finally:cleanup=tracker.close()
    result=dict(schema='control-recovery-offline-ablation-1.0',classification='WINDOWS_SAVED_INPUT_ABLATION_NOT_PI_OR_ROS_ACCEPTANCE',
        raw_sha256=sha,raw_bytes=len(raw),chunks=len(chunks),stages=stages,pair_selection='Every 100th adjacent complete original ring; all selected outcomes retained',
        icp_serial=stats(serial_times),icp_child_compute=stats(child_times) if child_times else None,icp_ipc_delivery=stats(delivery_times),
        results=results,cleanup=cleanup,all_pair_results_exact=all(r['exact'] for r in results),
        limits='Original80ms unchanged. Preserved receipt timestamps are not replayed at wall time. No DDS/publisher/ROS scheduling, real archive disk load, or actual Raspberry Pi throughput claim.',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'packages/twinpulse_robot_safety/native_stream.py',ROOT/'packages/twinpulse_robot_safety/field_tests.py']})
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in {'results','source_sha256'}},ensure_ascii=False))

if __name__=='__main__':main()
