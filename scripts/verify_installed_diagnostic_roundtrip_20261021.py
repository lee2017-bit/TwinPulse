# SPDX-License-Identifier: Apache-2.0
"""Read actual UI-downloaded SIM logs. No data injection or product API call."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.fleet_diagnostics import checked_work,checked_fault


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def ref(path):return dict(path=path.relative_to(OUT).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='31');parser.add_argument('--reproduction-attempt',default='32');args=parser.parse_args()
    if any(len(v)!=2 or not v.isascii() or not v.isdecimal() for v in (args.attempt,args.reproduction_attempt)):raise ValueError('TWO_DIGIT_ATTEMPTS_REQUIRED')
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    evidence=[];issues=[]
    for folder in (f'ui-{args.attempt}',f'ui-reproduction-{args.reproduction_attempt}'):
        ui=read(OUT/folder/'result.json')
        if ui.get('status')!='PASS' or ui.get('desktop',{}).get('engine',{}).get('release_id')!=active['release_id']:issues.append('UI_NOT_CURRENT_PASS:'+folder)
        path=OUT/folder/'final-fault-alpha-operation.json';operation=read(path)
        cpu=[];slow=[];faults=[];empty=[]
        for event in operation['events']:
            if 'runtime_work' not in event:continue
            work=event['runtime_work']
            if work is None:empty.append(event['event_sequence']);continue
            if checked_work(work)!=work:issues.append('INVALID_WORK:'+folder+':'+str(event['event_sequence']));continue
            host=work.get('host') or {}
            if 'thread_cpu_s' in host and 'process_cpu_s' in host:
                cpu.append(dict(event_sequence=event['event_sequence'],utc=event['utc'],host=host))
                if 'before_resources' in host:slow.append(cpu[-1])
            fault=event.get('runtime_fault')
            if fault is not None:
                if checked_fault(fault)!=fault:issues.append('INVALID_FAULT:'+folder+':'+str(event['event_sequence']))
                faults.append(dict(event_sequence=event['event_sequence'],fault=fault))
        if not cpu:issues.append('NO_ACTUAL_CPU_HOST_ROUNDTRIP:'+folder)
        evidence.append(dict(folder=folder,ui=ref(OUT/folder/'result.json'),operation=ref(path),operation_id=operation['operation_id'],project_id=operation['project_id'],
            cpu_host_event_count=len(cpu),slow_host_event_count=len(slow),fault_event_count=len(faults),optional_empty_sequences=empty,
            first_cpu=cpu[:1],last_cpu=cpu[-1:],slow_examples=slow[:2],fault_examples=faults[:1],
            fault_branch='ACTUAL_FAULT_PRESENT' if faults else 'NOT_RUN_NO_NATURAL_HOST_STALL_IN_THIS_UI_JOURNEY'))
    value=dict(schema='installed-host-diagnostic-roundtrip-1.0',status='PASS' if not issues else 'FAIL',issues=issues,
        release_id=active['release_id'],source_sha256=active['source_manifest_sha256'],evidence=evidence,
        limits='Actual current UI export proves CPU/resource host transport. A synthetic producer/fault/operation roundtrip is separately supplementary; absence of a natural host stall is not a successful physical-failure test. Original29 null data remains unavailable.')
    with (OUT/f'diagnostic-installed-roundtrip{args.attempt}.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(dict(status=value['status'],issues=issues,counts=[dict(folder=e['folder'],cpu=e['cpu_host_event_count'],slow=e['slow_host_event_count'],fault=e['fault_event_count']) for e in evidence])))
    return 0 if value['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
