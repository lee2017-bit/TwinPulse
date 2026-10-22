# SPDX-License-Identifier: Apache-2.0
"""Original current-source failure and actual collector-origin evidence."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def main():
    ui_path=OUT/'ui-35/result.json';ui=read(ui_path);launch=ui['desktop']['engine']['launch_id']
    folder=OUT/'runtime-final35'/launch;engine_path=folder/'engine-result.json';engine=read(engine_path)
    operation_path=next((OUT/'failed-ui35-original-logs').glob('*-56354787ff6d4cacbcce14ddd6a92f4a.json'))
    operation=read(operation_path)
    failed=next(e for e in operation['events'] if e.get('reason')=='ISAAC_UPDATE_STALLED' and e['kind']=='motion_result')
    fault_at=failed['runtime_fault']['observed_monotonic_s']
    cycles=engine['host_phase_diagnostics']['gc_cycles']
    cycle=min((c for c in cycles['recent_slow'] if c['ended_monotonic_s']<=fault_at),key=lambda c:fault_at-c['ended_monotonic_s'])
    assert ui['status']=='FAIL' and cycle['generation']==2 and cycle['pairing']=='MATCHED'
    assert cycle['collector_thread_name']=='TwinPulseSimRaycast' and cycle['collector_thread_cpu_s']>.7
    assert cycle['stack'][0]['file']=='lidar_geometry.py' and cycle['stack'][0]['function']=='visit'
    samples_path=OUT/'memory-final35/samples.jsonl';receipt_path=OUT/'memory-final35/receipt.json'
    assert sha256(samples_path.read_bytes()).hexdigest()==read(receipt_path)['samples_sha256']
    value=dict(schema='original-sim-gc-origin-failure-1.0',status='FAIL_RAYCAST_GC_TRIGGER_AND_CLOSURE_CYCLE_CONFIRMED',
        release_id=ui['desktop']['engine']['release_id'],launch_id=launch,project_id=ui['project'],
        operation_id=operation['operation_id'],command_id=failed['command_id'],scene_revision=failed['twin_context']['scene_revision'],
        input_sha256=ui['input_sha256'],failed_original_event=failed,collector_cycle=cycle,
        collector_end_to_failed_tick_s=fault_at-cycle['ended_monotonic_s'],
        preceding_pass_steps=sum(s['status']=='PASS' for s in ui['steps']),
        interpretation=[
            'Actual735ms generation2 collection in TwinPulseSimRaycast consumed734.375ms collector-thread CPU in visit/cast/scan; the following tick828ms exceeded the unchanged500ms watchdog.',
            'The old nested recursive visit creates one function/closure-cell reference cycle per cast, not per visited node. The old nested builder creates one per index.',
            'The collected1856 objects are not all attributed to these closures; the full735ms is not proven solely due to this defect. All-GC removal and physical success are not claimed.',
            'No supplementary replay/tests overlapped this actual UI session. This reproduces without the earlier concurrent replay confounder.',
            'Original first-fault, later normal cleanup and incomplete whole journey remain separate.'],
        actual_cleanup=read(folder/'cleanup-receipt.json'),
        fix_scope='Module-level stable builder and explicit left-first DFS remove repeated closure cycles without GC/safety/deadline/geometry changes. New installed whole-condition acceptance remains required.',
        source_review=dict(agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
            recorded_by='Main from actual source/artifact review',conclusion='Cycle confirmed; minimal iterative design preserves semantics. Additional confirmed blocking source defect not found in reviewed fix.'),
        references=[ref(p) for p in (ui_path,engine_path,operation_path,OUT/'runtime-final35/receipt.json',
            OUT/'failed-ui35-original-logs/receipt.json',receipt_path,samples_path,OUT/'budget-final35.json',
            OUT/'raycast-cycle-red37-isolated.log',OUT/'raycast-cycle-green37-final.log')])
    with (OUT/'gc-failure-review35.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(status=value['status'],operation_id=value['operation_id'],collector_cpu_s=cycle['collector_thread_cpu_s'],wall_s=cycle['elapsed_s'],failed_dt_s=failed['runtime_timing']['elapsed_s'])))
if __name__=='__main__':main()
