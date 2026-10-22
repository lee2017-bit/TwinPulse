# SPDX-License-Identifier: Apache-2.0
"""Bind the original failed SIM check; does not call a product or device API."""
from hashlib import sha256
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def main():
    ui_path=OUT/'ui-33/result.json';ui=read(ui_path);launch=ui['desktop']['engine']['launch_id']
    engine_path=OUT/'runtime-final33'/launch/'engine-result.json';engine=read(engine_path)
    operation_path=OUT/'failed-ui33-original-logs/10-ec839beedcf647ce9bbddf99d6ea0267.json';operation=read(operation_path)
    failed=next(e for e in operation['events'] if e['event_sequence']==272)
    tail=engine['host_phase_diagnostics']['worst_by_phase']['host_tail']
    idle=next(e for e in tail['child_phases'] if e['phase']=='tail_idle')
    assert ui['status']=='FAIL' and failed['reason']=='ISAAC_UPDATE_STALLED'
    assert abs(failed['runtime_timing']['elapsed_s']-.625)<.001
    assert idle['process_gc_pause_s']>.5 and idle['gc_pause_s']==0 and idle['thread_cpu_s']==0
    samples_path=OUT/'memory-final33/samples.jsonl';receipt_path=OUT/'memory-final33/receipt.json'
    assert sha256(samples_path.read_bytes()).hexdigest()==read(receipt_path)['samples_sha256']
    samples=[json.loads(s) for s in samples_path.open(encoding='utf-8')]
    at=failed['runtime_fault']['observed_at_ms']
    near=min(samples,key=lambda r:abs(r['at_ms']-at))
    value=dict(schema='original-sim-gc-overlap-failure-1.0',status='FAIL_GC_ORIGIN_UNRESOLVED',actual_attempt='33',
        release_id=ui['desktop']['engine']['release_id'],launch_id=launch,project_id=ui['project'],
        operation_id=operation['operation_id'],scene_revision=failed['twin_context']['scene_revision'],
        command_id=failed['command_id'],input_sha256=ui['input_sha256'],failed_step=ui['steps'][-1],
        preceding_pass_steps=sum(s['status']=='PASS' for s in ui['steps']),failed_original_event=failed,
        exact_tail=tail,nearest_system_sample=dict(at_ms=near['at_ms'],offset_ms=near['at_ms']-at,system=near['system']),
        separate_earlier_http409=[r for r in ui['fleet_requests'] if r.get('status')==409],
        interpretation=[
            'The original625ms watchdog rejection remains a failed motion result, not an obstacle-stop PASS.',
            'Host tail577.444ms includes tail_idle570.059ms with process-GC563ms, Kit CPU0 and Kit GC0. This strongly couples a non-Kit collector callback interval with the host delay, but its generation/trigger/thread and pure collector CPU were not recorded.',
            'Same-window FleetIO request-send wall578ms is not proof of socket send, JSON decode or a specific thread causing GC.',
            'The earlier409 is a separate pointer-release epoch rejection; it is not the Beta625ms failure.',
            'Main ran the106.737s supplementary raw replay during this UI trial. That concurrent load is a confounder, not a proven sole cause. Future actual integration must not overlap supplementary calculations.',
            'No timeout/GC/safety/geometry policy was relaxed. Later cleanup does not replace the original motion failure.'],
        actual_cleanup=read(OUT/'runtime-final33'/launch/'cleanup-receipt.json'),
        remaining=['Current cold/lineage/history and original saved geometry34 NOT_RUN after failed fresh33',
            'Actual UI-download/cold diagnostic roundtrip NOT_RUN',
            'Physical robot/Pi load/storage/braking/driving/world alignment NOT_RUN'],
        references=[ref(p) for p in (ui_path,engine_path,operation_path,samples_path,receipt_path,
            OUT/'runtime-final33/receipt.json',OUT/'failed-ui33-original-logs/receipt.json',
            OUT/'normal33/result.json',OUT/'normal33-restart/result.json',OUT/'budget-final33b.json',
            OUT/'dwm-after-ui33.json',OUT/'observation-replay33.json')])
    with (OUT/'gc-failure-review33.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(status=value['status'],operation_id=value['operation_id'],gc_overlap_s=idle['process_gc_pause_s'],available_bytes=near['system']['PhysicalAvailable_bytes'])))

if __name__=='__main__':main()
