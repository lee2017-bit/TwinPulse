# SPDX-License-Identifier: Apache-2.0
"""Explicit negative evidence-gate tests, never App/model result replacements."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import argparse

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suffix',default='');parser.add_argument('--attempt',default='12');args=parser.parse_args()
    if args.suffix not in ('','b'):raise ValueError('EXPLICIT_NEGATIVE_ATTEMPT_SUFFIX')
    if len(args.attempt)!=2 or not args.attempt.isascii() or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
    a=args.attempt+args.suffix
    original=OUT/f'ui-{args.attempt}/result.json';digest=sha256(original.read_bytes()).hexdigest()
    if read(OUT/f'gate-result{args.attempt}.json')['status']!='READY_FOR_SUPERVISED_POWERED_TEST':raise ValueError('CURRENT_PASS_REQUIRED_FIRST')
    base=read(OUT/f'evidence-manifest{args.attempt}.json');rows=[]
    for kind in ('missing-step','missing-motion-review','wrong-release','missing-shutdown','downgraded-shutdown',
                 'reproduction-missing-bed','reproduction-missing-chair','reproduction-wrong-phase','reproduction-missing-stop-ack',
                 'reproduction-join-alive','reproduction-join-unknown','reproduction-wrong-launch','original19-native-aborts'):
        manifest=deepcopy(base);manifest['classification']='EXPLICIT_GATE_NEGATIVE_NOT_APP_OUTPUT:'+kind
        if kind=='missing-step':
            run=read(original);name='All four normal pointer directions without injected delay'
            run['steps']=[s for s in run['steps'] if s['name']!=name]
            run['classification']='EXPLICIT_DERIVED_GATE_NEGATIVE_MISSING_REQUIRED_STEP_NOT_ACTUAL_APP_RUN'
            target=OUT/('gate-negative-missing-step-fresh'+a+'.json');write(target,run)
            for entry in manifest['evidence']:
                if entry['role']=='fresh':entry.update(path=target.relative_to(OUT).as_posix(),sha256=sha256(target.read_bytes()).hexdigest())
            expected='MISSING_OR_FAILED_STEP:fresh:'+name
        elif kind=='missing-motion-review':
            entry=next(e for e in manifest['evidence'] if e['role']=='lineage_cold')
            run=read(OUT/entry['path']);name='Saved physical motion review cold reopens without Analyze or restored authority'
            run['steps']=[s for s in run['steps'] if s['name']!=name]
            run['classification']='EXPLICIT_GATE_NEGATIVE_NOT_APP_OUTPUT'
            target=OUT/('gate-negative-missing-motion-review-history'+a+'.json');write(target,run)
            entry.update(path=target.relative_to(OUT).as_posix(),sha256=sha256(target.read_bytes()).hexdigest())
            expected='MISSING_OR_FAILED_STEP:lineage_cold:'+name
        elif kind=='wrong-release':
            manifest['release_id']='EXPLICIT_NEGATIVE_NOT_ACTIVE_INSTALLED_RELEASE';expected='NOT_ACTIVE_INSTALLED_RELEASE'
        elif kind=='missing-shutdown':
            manifest['physical_readiness_review'].pop('shutdown_contract',None);expected='SHUTDOWN_CONTRACT_UNREADABLE_OR_SHA_MISMATCH'
        elif kind=='downgraded-shutdown':
            manifest['physical_readiness_review']['schema']='physical-readiness-review-1.1';expected='CURRENT_SHUTDOWN_CONTRACT_REQUIRED'
        elif kind in ('reproduction-missing-bed','reproduction-missing-chair','reproduction-wrong-phase','reproduction-missing-stop-ack'):
            review=manifest['physical_readiness_review'];run=read(OUT/review['reproduction']['path'])
            if kind=='reproduction-wrong-phase':run['phase']='fresh';expected='REPRODUCTION_NOT_WHOLE_PASS'
            elif kind=='reproduction-missing-stop-ack':
                run.pop('final_fault_recovery',None);run['fleet_requests']=[]
                expected='REPRODUCTION_FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN'
            else:
                name='Actual panel nearest bed destination reaches scene-derived approach with visible receipt' if kind.endswith('bed') else 'Actual main-chat nearest chair destination reaches scene-derived approach with visible receipt'
                run['steps']=[s for s in run['steps'] if s['name']!=name]
                expected='REPRODUCTION_MISSING_OR_FAILED_STEP:'+name
            target=OUT/('gate-negative-'+kind+'-ui'+a+'.json');write(target,run)
            review['reproduction']=dict(path=target.relative_to(OUT).as_posix(),sha256=sha256(target.read_bytes()).hexdigest())
        elif kind.startswith('reproduction-'):
            review=manifest['physical_readiness_review'];contract=read(OUT/review['shutdown_contract']['path'])
            engine=read(OUT/contract['branches']['reproduction']['engine_result']['path'])
            if kind=='reproduction-wrong-launch':
                engine['launch_id']='EXPLICIT_OTHER_LAUNCH';expected='SHUTDOWN_LAUNCH_BINDING_INVALID:reproduction'
            else:
                engine['viewport_phase_diagnostics']['join_status']['diagnostic_alive']=True if kind.endswith('alive') else None
                expected='SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:reproduction'
            engine_path=OUT/('gate-negative-'+kind+'-engine'+a+'.json');write(engine_path,engine)
            contract['branches']['reproduction']['engine_result']=dict(path=engine_path.relative_to(OUT).as_posix(),sha256=sha256(engine_path.read_bytes()).hexdigest())
            contract_path=OUT/('gate-negative-'+kind+'-contract'+a+'.json');write(contract_path,contract)
            review['shutdown_contract']=dict(path=contract_path.relative_to(OUT).as_posix(),sha256=sha256(contract_path.read_bytes()).hexdigest())
        else:
            target=OUT/'ui-19/result.json'
            for entry in manifest['evidence']:
                if entry['role']=='fresh':entry.update(path=target.relative_to(OUT).as_posix(),sha256=sha256(target.read_bytes()).hexdigest())
            expected='UNCLASSIFIED_REQUEST_FAILURE:fresh'
        source=OUT/('gate-negative-'+kind+'-manifest'+a+'.json');write(source,manifest)
        target=OUT/('gate-negative-'+kind+'-result'+a+'.json')
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/verify_robot_focus_gate.py'),'--manifest',str(source),'--output',str(target)],
            cwd=ROOT,capture_output=True,text=True)
        (OUT/('gate-negative-'+kind+'-run'+a+'.log')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
        value=read(target)
        okay=proc.returncode==1 and value['status']=='NOT_READY' and expected in value['issues']
        rows.append(dict(kind=kind,status='PASS_NEGATIVE_REJECTED' if okay else 'FAIL',expected=expected,actual_issues=value['issues'],
            manifest_sha256=sha256(source.read_bytes()).hexdigest(),result_sha256=sha256(target.read_bytes()).hexdigest()))
    value=dict(classification='GATE_TESTS_NOT_APP_OR_HARDWARE_ACCEPTANCE',status='PASS' if all(r['status']=='PASS_NEGATIVE_REJECTED' for r in rows) else 'FAIL',
        original_app_result_unchanged=sha256(original.read_bytes()).hexdigest()==digest,tests=rows)
    write(OUT/('gate-additional-negatives'+a+'.json'),value);print(json.dumps(value))
    return 0 if value['status']=='PASS' and value['original_app_result_unchanged'] else 1
if __name__=='__main__':raise SystemExit(main())
