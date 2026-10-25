# SPDX-License-Identifier: Apache-2.0
"""Scope-aware evidence/replay gate. Never sends controls or model requests."""
import argparse
from copy import deepcopy
import hashlib
import html
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-task-20261025-01'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parser=argparse.ArgumentParser();parser.add_argument('--tests',action='store_true');parser.add_argument('--test-attempt',default='01');parser.add_argument('--extended',action='store_true');args=parser.parse_args()
sys.path.insert(0,str(ROOT))

if args.tests:
    if len(args.test_attempt)!=2 or not args.test_attempt.isdecimal():raise ValueError('Test attempt requires two digits')
    folder=OUT/('focused-final'+args.test_attempt);folder.mkdir(exist_ok=False)
    suite=unittest.defaultTestLoader.loadTestsFromNames([
        'tests.integration.test_robot_tasks','tests.integration.test_chat_conversation','tests.integration.test_robot_fleet',
        'tests.integration.test_sim_fleet_navigation','tests.integration.test_environment_model_move'])
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (folder/'console.txt').write_text(stream.getvalue(),encoding='utf-8')
    value=dict(scope='SUPPLEMENTARY_FAKE_ENGINE_MODEL_NO_HARDWARE',status='PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))
    (folder/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value));sys.exit(0 if result.wasSuccessful() else 1)

for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_package import verify_package
from twinpulse_core import canonical_sha256
from scripts.roomplan_runtime_copy_gate import check_runtime_copy
active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
release=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'/Path(active['exe']).parent
verified=verify_package(release)
composition=read(OUT/'compose02/result.json');failed=read(OUT/'compose01/result.json');survey=read(OUT/'ui03/result.json');cold=read(OUT/'cold01/result.json')
required=['Select existing registered TurtleBot3 SIM only','Explicit SIM Connect Prepare with current engine epoch',
    'Camera frames the actual robot body before the task','Natural goal through Robot command waits three seconds before Enter',
    'One approved text-only configured planner request','Explicit exact-plan Run uses measured child results and observations',
    'Final exact Stop LiDAR OFF Disconnect without physical calls']
def steps(value,names):return value['status']=='PASS_SCOPED' and set(names)<={s['name'] for s in value['steps'] if s['status']=='PASS'}
job=composition['final_task'];events=job['events'];starts={e['request_id']:e for e in events if e['kind']=='child_started'}
children=[e for e in events if e['kind']=='child_completed'];returned=next(e for e in events if e['kind']=='return_verified')
task_root=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1/robot-tasks'
task_ids={composition['final_task']['task_id'],failed['final_task']['task_id'],survey['final_task']['task_id']}
if args.extended:
    final_survey=read(OUT/'survey04/result.json');cancel=read(OUT/'cancel05/result.json')
    task_ids.update((final_survey['final_task']['task_id'],cancel['cancelled']['task_id']))
copies=[];usages=[];records=[]
for identity in sorted(task_ids):
    source=task_root/identity;target=OUT/'task-originals'/identity;target.mkdir(parents=True,exist_ok=True)
    paths=[source/n for n in ('task.json','request.json','proposal.json','usage.ledger.json','observed-grid.json')]
    paths+=sorted(source.glob('observation-*.json'))+sorted(source.glob('navigation-*.json'))
    for path in paths:
        if not path.is_file():continue
        raw=path.read_bytes();dest=target/path.name
        if dest.exists() and dest.read_bytes()!=raw:raise ValueError('FROZEN_TASK_ORIGINAL_CHANGED')
        if not dest.exists():dest.write_bytes(raw)
        copies.append(dict(task_id=identity,name=path.name,bytes=len(raw),sha256=sha(path)))
    record=read(source/'task.json');digest=record.pop('record_sha256')
    records.append(dict(task_id=identity,valid=canonical_sha256(record)==digest))
    usage=read(source/'usage.ledger.json');usages+=usage['requests']

# Fresh isolated interpreter: only installed pure-core source, no repository
# sys.path bootstrap, cached peers, robot worker, SDK or bytecode writes.
payload=OUT/'compose01/result.json'
code="""import sys,json
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
from twinpulse_core.robot_task_plan import checked_plan
value=json.load(open(sys.argv[2],encoding='utf-8'))
try:checked_plan(value['proposal']['plan'],request_text=value['proposal']['text'])
except ValueError as e:
 assert 'REQUESTED_CAPABILITY_MISSING' in str(e)
 print(json.dumps({'status':'REJECTED_ORIGINAL_BAD_PLAN_BEFORE_RUN','reason':str(e),'module':sys.modules['twinpulse_core.robot_task_plan'].__file__}))
else:raise SystemExit('Original bad model response was accepted')
"""
replayed=subprocess.run([sys.executable,'-I','-B','-c',code,str(release/'_internal/resources/packages/twinpulse_core/src'),str(payload)],capture_output=True,text=True,check=True)
replay=json.loads(replayed.stdout)
checks=dict(
    final_package_verified=verified['files']==1698,
    final_composition=steps(composition,required),
    missing_step_negative=not steps({**composition,'steps':composition['steps'][:-1]},required),
    same_current_release=composition['versions']['engine']['release_id']==cold['versions']['engine']['release_id']==verified['build_id'],
    task_completed_with_explicit_return=job['state']=='COMPLETED' and any(s['op']=='return_to_start' for s in job['plan']['steps']),
    all_child_receipts=len(children)==5 and all(e['request_id'] in starts and e['new_motion_epoch']==e['applied_motion_epoch'] and e['new_motion_epoch']!=starts[e['request_id']]['motion_epoch'] for e in children),
    return_xy_yaw_checked=returned['position_error_m']<.04 and returned['yaw_error_rad']<.04 and returned['position_basis']=='ISAAC_KINEMATIC_NOT_PHYSICAL',
    final_stop=not job.get('stop_error') and any(e['kind']=='stop_confirmed' for e in events) and composition['stop']['robot']['motion_epoch']==composition['stop']['robot']['applied_motion_epoch'],
    old_failure_retained=failed['status']=='FAIL' and failed['final_task']['state']=='COMPLETED' and not any(s['op']=='return_to_start' for s in failed['proposal']['plan']['steps']),
    original_bad_plan_rejected_in_installed_code=replay['status']=='REJECTED_ORIGINAL_BAD_PLAN_BEFORE_RUN',
    no_whole_room_claim=job['whole_room_coverage_verified'] is False and job['measured_coverage']['model_prior_is_measurement'] is False,
    actual_scan_records=job['measured_coverage']['observations']>=3 and all(r['valid'] for r in records),
    earlier_survey_limited=survey['status']=='PASS_SCOPED' and survey['final_task']['state']=='PARTIAL' and not survey['final_task']['whole_room_coverage_verified'],
    old_survey_not_promoted_to_current_release=survey['versions']['engine']['release_id']!=verified['build_id'],
    cold_no_resume=steps(cold,['Select existing registered TurtleBot3 SIM only','Cold history does not resume a task or connection']) and not cold['task_snapshots'],
    calls_within_approved_grants=len(usages)==(5 if args.extended else 3) and len(list((OUT/'call-claims').glob('*.json')))==(5 if args.extended else 3),
    no_physical_actions=all(v['physical_actions']==0 for v in (composition,failed,survey,cold)),
    focused_regressions=read(OUT/'focused-final01/result.json')['status']=='PASS',
    original_usd_unchanged=sha(Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd'))=='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b',
)
launches=[('runtime-copiesruntime-copies01','ae70462e7cab4c74832ab20feee7d4a2'),('runtime-copies02','e7c7bd571800471aa7de2e13ad2f4047'),('runtime-copies03','78db6bf55b534096818eb74e1b898f72')]
if args.extended:
    extra=read(OUT/'approval-additional01.json');sj=final_survey['final_task'];ce=cancel['cancelled']
    sc=[e for e in sj['events'] if e['kind']=='child_completed'];ss={e['request_id']:e for e in sj['events'] if e['kind']=='child_started'}
    sr=[e for e in sj['events'] if e['kind']=='return_verified']
    checks.update(
        explicit_additional_grant=extra['additional_max_requests']==2 and extra['cumulative_max_requests']==5 and extra['physical_operation_allowed'] is False,
        final_survey_ui=steps(final_survey,required),
        final_survey_missing_step_negative=not steps({**final_survey,'steps':final_survey['steps'][:-1]},required),
        final_survey_current_release=final_survey['versions']['engine']['release_id']==verified['build_id'],
        final_survey_partial_actual_observations=sj['state']=='PARTIAL' and sj['measured_coverage']['observations']>=3 and sj['distance_m']>.5 and sj['whole_room_coverage_verified'] is False,
        final_survey_child_epochs=len(sc)>=2 and all(e['request_id'] in ss and e['new_motion_epoch']==e['applied_motion_epoch'] and e['new_motion_epoch']!=ss[e['request_id']]['motion_epoch'] for e in sc),
        final_survey_return_and_stop=len(sr)==1 and sr[0]['position_error_m']<.04 and sr[0]['yaw_error_rad']<.04 and not sj.get('stop_error') and any(e['kind']=='stop_confirmed' for e in sj['events']),
        actual_planning_stop=steps(cancel,[*required[:3],required[3],required[4],'Stop after planner submission prevents late execution',required[-1]]) and cancel['cancel_at_state']=='PLANNING' and cancel['cancel_worker_active'] is True,
        cancelled_no_late_execution=ce['state']=='CANCELLED' and ce['segments']==0 and ce['worker_active'] is False and ce['plan'] is None,
        cancel_current_release=cancel['versions']['engine']['release_id']==verified['build_id'],
        additional_no_physical_actions=final_survey['physical_actions']==cancel['physical_actions']==0)
    launches.append(('runtime-copies04','9513563d548741c381fab558cabf004d'))
runtime_copies=[]
for folder,identity in launches:
    path=OUT/folder/identity;receipt=read(path/'copy-receipt.json');exit_record=read(path/'owned-exit-observations.json');cleanup=read(path/'cleanup-receipt.json')
    issues=check_runtime_copy(path,identity,receipt)
    checks['frozen_'+identity]=not issues
    runtime_copies.append(dict(launch_id=identity,issues=issues,
        exact_copies=sum(row['status']=='EXACT_COPY' for row in receipt['files']),
        unavailable=[row['name'] for row in receipt['files'] if row['status']=='ORIGINAL_UNAVAILABLE']))
    checks['normal_roots_'+identity]=exit_record['evidence_complete'] and cleanup['exit_evidence_complete'] and all(exit_record['roles'][role]['return_code']==0 and exit_record['roles'][role]['root_disposition']=='EXITED_DURING_GRACE' for role in ('backend','engine'))
value=dict(status=('PASS_SCOPED_TASK_COMPOSITION_BOUNDED_SURVEY_CANCEL_AND_COLD' if args.extended else 'PASS_SCOPED_COMPOSITION_RETURN_AND_COLD') if all(checks.values()) else 'FAIL',scope='NOT_WHOLE_ROOM_OR_PHYSICAL_READINESS',
    build_id=verified['build_id'],checks=checks,passed=sum(checks.values()),total=len(checks),model_calls=len(usages),total_tokens=sum((u.get('usage') or {}).get('total_tokens',0) for u in usages),unknown_usage_requests=sum(not bool(u.get('usage')) for u in usages),
    original_bad_plan_replay=replay,task_copies=copies,runtime_copies=runtime_copies,physical_task_ready=False,current_release_whole_survey='NOT_RUN_CALL_BUDGET_EXHAUSTED',
    provider_inflight_cancel='NOT_RUN_CALL_BUDGET_EXHAUSTED_SUPPLEMENTARY_STOP_TESTS_ONLY')
if args.extended:value.update(current_release_whole_survey='SCOPED_BOUNDED_SURVEY_PARTIAL_NOT_WHOLE_ROOM',provider_inflight_cancel='PLANNING_STOP_CANCELLED_NO_LATE_EXECUTION')
target=OUT/('acceptance03.json' if args.extended else 'acceptance02.json')
if target.exists():raise ValueError('Preserve previous gate result; use a fresh evidence attempt')
target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in value.items() if k not in {'task_copies','checks'}},ensure_ascii=False))
if value['status']=='FAIL':raise SystemExit('Evidence gate failed: '+', '.join(k for k,v in checks.items() if not v))
