# SPDX-License-Identifier: Apache-2.0
"""Derive original50 movement without rewriting its failed App result."""
from hashlib import sha256
import json
import math
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())

def main():
    raw=OUT/'failed-ui-reproduction50-original-logs/19-f080a0026e0142ce8d941ad7b52addaa.json'
    operation=read(raw);events=operation['events']
    stopped=next(e for e in events if e['kind']=='motion_result' and e.get('command_id')=='805b2a11-c632-406f-b71e-ff841e88fab7')
    escaped=next(e for e in events if e['kind']=='motion_result' and e.get('command_id')=='7e2f1b79-8a53-4c01-86f0-4fd34e023583')
    accepted=next(e for e in events if e['kind']=='command_accepted' and e.get('command_id')==escaped['command_id'])
    assert stopped['reason']=='OBSTACLE_STOP' and escaped['reason']=='TASK_COMPLETED' and accepted['parameters']['amount']==.1
    p,q=stopped['position_m'],escaped['position_m'];dx,dy=q[0]-p[0],q[1]-p[1]
    forward=dx*math.cos(p[2])+dy*math.sin(p[2]);lateral=-dx*math.sin(p[2])+dy*math.cos(p[2])
    assert p[0]-q[0]<.09 and math.isclose(forward,-.1,abs_tol=1e-12) and abs(lateral)<1e-12
    original=read(OUT/'ui-reproduction-50/result.json');assert original['status']=='FAIL'
    fresh=read(OUT/'ui-47/result.json');checks=runpy.run_path(str(ROOT/'scripts/verify_robot_focus_gate.py'))
    assert checks['body_escape_verified'](fresh)
    value=dict(status='ORIGINAL50_WHOLE_FAIL_PRESERVED_TEST_WORLD_AXIS_ERROR_CONFIRMED',
        operation_id=operation['operation_id'],project_id=operation['project_id'],request_id=escaped['command_id'],
        original_step=original['steps'][-1],original_stop_event=stopped['event_sequence'],original_completed_event=escaped['event_sequence'],
        original_before_position=p,original_after_position=q,world_x_reverse_m=p[0]-q[0],
        original_body_forward_m=forward,original_body_lateral_m=lateral,yaw_change_rad=q[2]-p[2],
        unchanged_minimum_forward_approach_m=.05,unchanged_minimum_reverse_m=.09,
        current_fresh47_derived_body_gate=True,
        note='Original50 remains whole FAIL and later steps NOT_RUN. Derived math is not a new motion trial; actual whole saved-geometry52 remains required. No product/guard/distance/pose changes.',
        references=[ref(OUT/name) for name in ('ui-reproduction-50/result.json',
            'failed-ui-reproduction50-original-logs/19-f080a0026e0142ce8d941ad7b52addaa.json',
            'failed-ui-reproduction50-original-logs/receipt.json','runtime-final50/receipt.json',
            'reproduction50-native-cleanup/shutdown.json','memory-followup49/receipt.json',
            'clearance-preparation49/result.json','cleanup-preparation49.json',
            'body-frame-node52.log','body-frame-gate52.log','ui-47/result.json','memory-final47/metadata.json')])
    output=OUT/'body-frame-failure50-review.json'
    with output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(output=str(output),forward_m=forward,lateral_m=lateral,original_whole_status=original['status'])))

if __name__=='__main__':main()
