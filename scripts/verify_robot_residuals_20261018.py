# SPDX-License-Identifier: Apache-2.0
"""OFFLINE replay of original failed stream; no transport, ROS or device I/O."""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
for p in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/p/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
import native_stream as current
from field_tests import register_pair,frame_points
from twinpulse_app.physical_live_history import recover_live_history

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module

def metric(samples):
    samples=sorted(samples)
    return dict(n=len(samples),median_ms=statistics.median(samples)*1000,
                p95_ms=samples[min(len(samples)-1,math.ceil(len(samples)*.95)-1)]*1000,max_ms=max(samples)*1000)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    directory=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-live/55e28197e6ca4f3195d69293f606acc7'
    old_root=ROOT/'artifacts/robot-powered-ui-20261018/build08/staging/resources/packages/twinpulse_robot_safety'
    old=load('residual_old_native',old_root/'native_stream.py');old_field=load('residual_old_field',old_root/'field_tests.py')
    receipt=json.loads((directory/'receipt.json').read_text(encoding='utf-8'))
    events=[json.loads(line) for segment in receipt['segments'] for line in (directory/segment['path']).read_text(encoding='utf-8').splitlines()]
    start=events[0];identity={k:start[k] for k in ('operation_id','project_id','robot_id','connection_epoch','binding_sha256','source_twin_context')}
    recovered=recover_live_history(directory,receipt,**identity)
    raw=[e['data'] for e in events if e.get('kind')=='raw'];frames=[];times={};digests={}
    for name,module in [('before',old),('after',current)]:
        decoder=module.NativeDecoder();packets=[];complete=False;clock=[0.];build=[];read=[];hashes=[];last=None
        stream=module.NativeStream(Path(tempfile.gettempdir())/'unused-offline-path',lambda *_:None,clock=lambda:clock[0]);stream.stream_id='offline-original'
        for chunk in raw:
            data=base64.b64decode(chunk['base64'],validate=True)
            assert hashlib.sha256(data).hexdigest()==chunk['sha256']
            clock[0]=chunk['receipt_end_s']
            for packet in decoder.feed(data,clock[0]):
                if packet['nodes'][0]['ring_start']:
                    if packets:
                        began=time.perf_counter();stream._frame(packets,complete);build.append(time.perf_counter()-began)
                        frame=stream.latest_frame();hashes.append((frame['raw_sha256'],frame['nodes_sha256'],frame['complete'],dict(frame['timing'])))
                        if name=='after' and frame['complete']:frames.append(frame)
                        last=frame
                    packets=[];complete=True
                packets.append(packet)
        assert last is not None
        for _ in range(1000):
            began=time.perf_counter();stream.latest_frame();read.append(time.perf_counter()-began)
        times[name]=dict(frame_build=metric(build),frame_read=metric(read),checksum_errors=decoder.errors,frames=len(hashes))
        digests[name]=hashes
    assert digests['before']==digests['after'],'Original bytes/nodes/timing changed'
    config=dict(angle_sign=1,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.)
    points=[frame_points(f,config,f['timing']['receipt_end_s']) for f in frames]
    results=[];icp={'before':[],'after':[]};deadline_over={'before':0,'after':0}
    # Uniformly cover the saved acquisition, not only successful/low-cost pairs.
    indices=list(range(1,len(points),max(1,len(points)//60)))
    for i in indices:
        pair=[]
        for name,fn in [('before',old_field.register_pair),('after',register_pair)]:
            began=time.perf_counter()
            try:value=fn(points[i-1],points[i],deadline=began+5.)
            except ValueError as exc:value=dict(error=str(exc))
            elapsed=time.perf_counter()-began;icp[name].append(elapsed)
            deadline_over[name]+=int(elapsed>.08);pair.append(value)
        assert pair[0]==pair[1],('Correspondence/result changed',i,pair)
        results.append(dict(frame=i,result=pair[0]))
    raw_sha=hashlib.sha256(b''.join(base64.b64decode(c['base64']) for c in raw)).hexdigest()
    result=dict(schema='robot-residual-offline-replay-1.0',operation_id=start['operation_id'],raw_sha256=raw_sha,
        raw_chunks=len(raw),raw_bytes=sum(c['length'] for c in raw),original_segment_sha256=receipt['segments'],
        history=dict(summaries=len(recovered['events']),cleanup_confirmed=recovered['cleanup_confirmed'],
            source_files=len(recovered['worker_sources'] or {}),source_provenance=recovered['worker_sources_provenance'],
            runtime_event_count=recovered['runtime_event_count']),native=times,native_identity_exact=True,
        icp={k:dict(**metric(v),over_original_80ms_deadline=deadline_over[k]) for k,v in icp.items()},
        icp_results_exact=True,icp_results=results,hardware_test='NOT_RUN',
        limitations='Windows saved-byte replay; not Raspberry Pi throughput or real ROS/source-age acceptance',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT/'packages/twinpulse_robot_safety/native_stream.py',ROOT/'packages/twinpulse_robot_safety/field_tests.py']})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'icp_results','original_segment_sha256','source_sha256'}},indent=2))

if __name__=='__main__':main()
