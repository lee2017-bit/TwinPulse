# SPDX-License-Identifier: Apache-2.0
"""Original/retest pose and timing comparison; no App/device or data rewrite."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def step(v,name):return next((s for s in v.get('steps',[]) if s.get('name')==name),{})
def poses(v):return {r['label']:r.get('pose',{}).get('position_m') for r in v if r.get('kind')=='sim'}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
    records=[]
    for name in ('ui-08','ui-12','ui-reproduction-12','ui-reproduction-'+args.attempt):
        p=OUT/name/'result.json'
        if not p.is_file():continue
        v=read(p)
        connected=step(v,'Two simultaneous real Isaac SIM connections and independent scan').get('evidence',[])
        bed=step(v,'Actual panel nearest bed destination reaches scene-derived approach with visible receipt')
        before=bed.get('evidence',{}).get('before') or step(v,'Destination Stop cancels planning or travel and never replays old route').get('evidence',{}).get('after')
        row=dict(directory=name,result=ref(p),status=v['status'],project=v.get('project'),initial_poses=poses(connected),
            bed_step_status=bed.get('status','NOT_RUN'),bed_entry_pose=before.get('pose',{}).get('position_m') if before else None,
            bed_entry_source='Actual destination before' if bed.get('evidence',{}).get('before') else 'Immediately preceding cancelled destination after' if before else 'NOT_RUN')
        observations=[]
        for path in (OUT/name).glob('*operation.json'):
            op=read(path)
            for e in op.get('events',[]):
                work=e.get('runtime_work') or {}
                if work.get('scan_worker'):
                    observations.append(dict(operation_id=op.get('operation_id'),event_sequence=e.get('event_sequence'),
                        utc=e.get('utc'),worker=work['scan_worker'],prepare=work.get('scan_prepare'),update_s=work.get('update_s')))
        observations=list({(e['operation_id'],e['event_sequence']):e for e in observations}.values())
        if observations:
            row['new_scan_samples']=len(observations)
            row['worst_worker_wall']=max(observations,key=lambda e:e['worker'].get('wall_s',0))
            row['worst_update']=max(observations,key=lambda e:e.get('update_s',0))
        records.append(row)
    # The rejected tool run used +world-X while a restored robot faced west.
    p=OUT/'failed-ui-reproduction12-original-logs/09-19361736f07f4e29b1dfd553c0da5183.json'
    op=read(p);observed=[e for e in op['events'] if e.get('position_m')]
    a=poses(step(read(OUT/'ui-reproduction-12/result.json'),'Two simultaneous real Isaac SIM connections and independent scan')['evidence'])['Alpha']
    b=observed[-1]['position_m'];dx,dy=b[0]-a[0],b[1]-a[1]
    value=dict(classification='SEPARATE_SAVED_GEOMETRY_RETEST_NOT_FRESH_OR_EXACT_INITIAL_POSE_REPLAY',records=records,
        original_reproduction12_tool_failure=dict(original=ref(p),initial=a,after=b,world_dx_m=dx,
            body_forward_m=dx*math.cos(a[2])+dy*math.sin(a[2]),body_lateral_m=-dx*math.sin(a[2])+dy*math.cos(a[2]),
            false_assumption='Forward always increases world X; actual saved heading was west',
            criterion='Same 0.04m minimum, measured along original body heading for reproduction only; fresh branch unchanged',
            frozen_driver=ref(OUT/'verify_robot_fleet_ui-before-reproduction-fix.mjs')),
        interpretation='All original FAILs remain FAIL. Same geometry is not an exact timing/pose replay; initial and bed-entry poses are shown. New clean runs do not prove sole historical causality or physical readiness.')
    target=OUT/('sim-retest-analysis'+args.attempt+'.json')
    with target.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(path=str(target),records=len(records))))
if __name__=='__main__':main()
