# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One robot-OFF pre-demo report using existing services and fixed local tests.

No SSH/ROS/serial imports, motor commands, deployment or automatic retry.
Missing physical evidence does not suppress independent offline checks.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from twinpulse_core.demo_operation_manifest import AUTOMATIC_OPERATIONS
from verify_ad2_automatic_mapping import JOBS,run_batch,failure

# Explicit no-device allowlist. Manifest descriptions never become commands.
CASES={
    'cold_start_revision_goal':('tests.integration.test_cold_start_mission',),
    'revision_ack':('tests.integration.test_mission_photo_correction',
                    'tests.integration.test_remote_correction_guard','tests.integration.test_remote_mission_correction'),
    'loss_stop_cleanup_storage':('tests.integration.test_mission_observation_boundaries',
        'tests.integration.test_mission_cleanup_wall_time','tests.integration.test_mission_report_storage_failure',
        'tests.integration.test_active_mission_display'),
    'driver_transport':('tests.integration.test_same_window_ros','tests.integration.test_ros_scan_client',
        'packages.twinpulse_robot_safety.tests.teleop_test'),
    'package_contracts':('tests.integration.test_packaged_automatic_demo',),
    'same_condition_mission_comparison':('tests.integration.test_automatic_comparison',),
}
NOT_RUN={
    'active_isaac_runtime':'FRESH_WEB_API_ISAAC_RECEIPT_REQUIRED',
    'physical_mission':'ROBOT_OFF_NEW_FIELD_APPROVAL_AND_REVIEWED_TARGET_REQUIRED',
}


def write_json(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False)


def execute_contracts(root,out,name,modules):
    environment=dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE']='1'
    environment['PYTHONIOENCODING']='utf-8'
    environment['PYTHONPATH']=os.pathsep.join([str(root),*[str(p/'src') for p in
        (root/'packages').iterdir() if (p/'src').is_dir()]])
    # Existing actual shared-worker fixtures persist their synthetic raw/report
    # in this run's owned folder; these are not robot observations.
    environment['TWINPULSE_PREFLIGHT_EVIDENCE']=str(out/name)
    log=out/(name+'.log');started=time.monotonic()
    with log.open('xb') as stream:
        try:
            result=subprocess.run([sys.executable,'-B','-m','unittest','-q',*modules],cwd=root,
                env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=600,check=False)
            exit_code=result.returncode
        except subprocess.TimeoutExpired:
            return {'status':'FAIL','reason':'CONTRACT_PROCESS_TIMEOUT','log':log.name,'seconds':time.monotonic()-started}
    text=log.read_text(encoding='utf-8',errors='replace')
    counts=re.findall(r'Ran (\d+) tests?',text)
    passed=exit_code==0 and bool(counts) and int(counts[-1])>0 and not re.search(r'skipped=|unexpected successes=',text)
    return {'status':'PASS' if passed else 'FAIL','scope':'FIXED_NO_DEVICE_SHARED_PRODUCT_CONTRACTS',
        'tests':int(counts[-1]) if counts else 0,'exit_code':exit_code,'log':log.name,
        'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'seconds':time.monotonic()-started,
        'physical_validation':'NOT_RUN'}


def run(root=ROOT, *, admission_audit=None, execute=execute_contracts, mapping=run_batch):
    root=Path(root).resolve()
    if set(AUTOMATIC_OPERATIONS)!=set(CASES)|set(NOT_RUN)|{'raw_integrity','recorded_mapping_photo'}:
        raise ValueError('AUTOMATIC_OPERATION_MATRIX_MISMATCH')
    out=root/'artifacts/demo-preflight'/uuid4().hex;out.mkdir(parents=True,exist_ok=False)
    # Hash source/build files only, not private keys, credentials or whole user folders.
    paths=[*sorted((root/'packages').glob('*/src/**/*.py')),*sorted((root/'packages').glob('*/tests/*.py')),
           *sorted((root/'packages/twinpulse_robot_safety').glob('*.py')),*sorted((root/'scripts').glob('*.py')),
           *sorted((root/'tests/integration').glob('*.py')),*sorted((root/'apps/twinpulse-web/dist/assets').glob('*')),
           *sorted((root/'apps/twinpulse-web/src').glob('*.ts')),*sorted((root/'apps/twinpulse-web/src').glob('*.tsx'))]
    source_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    report={'schema':'automatic-demo-preflight-1.0','robot_contacted':False,'motion_authorized':False,
        'physical_demo_ready':False,'offline_implementation_ready':False,'stages':{},'source_sha256':source_hashes,
        'operation_contracts':{k:{'entry':v[0],'dependencies':v[1],'acceptance_scope':v[2]}
                               for k,v in AUTOMATIC_OPERATIONS.items()}}
    # Checkpoints are atomically replaced within this newly owned output only.
    def checkpoint():
        temporary=out/'report.pending.json'
        with temporary.open('w',encoding='utf-8') as stream:json.dump(report,stream,sort_keys=True,indent=2,allow_nan=False)
        temporary.replace(out/'report.json')
    def stage(name,action):
        started=time.monotonic()
        report['stages'][name]={'status':'RUNNING'};checkpoint()
        print(json.dumps({'stage':name,'status':'RUNNING'}),file=sys.stderr,flush=True)
        try:row=action()
        except Exception as exc:row=failure(exc,name)
        row.setdefault('seconds',time.monotonic()-started)
        report['stages'][name]=row;checkpoint();return row
    if admission_audit:
        stage('admission_prerequisites',lambda:admission_audit(root))
    else:stage('admission_prerequisites',lambda:{'status':'NOT_RUN','reason':'ADMISSION_AUDITOR_REQUIRED'})
    def originals():
        from run_robot_field_suite import inspect_saved
        rows=inspect_saved([root/'artifacts/manual-control'/job/'robot-evidence/ros-messages.raw' for job in JOBS])
        write_json(out/'raw-integrity.json',rows)
        return {'status':'PASS' if all(r['status']=='RAW_BYTES_VERIFIED_NOT_PHYSICAL' for r in rows) else 'FAIL',
            'sessions':rows,'artifact':'raw-integrity.json'}
    stage('raw_integrity',originals)
    def recorded():
        # Each session re-verifies its own source. One corrupt recording cannot
        # suppress processing the other independent recordings.
        value=mapping(root,photo_policy='align_only');write_json(out/'recorded-mapping.json',value)
        return {'status':value['status'],'artifact':'recorded-mapping.json','sessions':[
            {k:r.get(k) for k in ('source_job_id','status','reason','originals_unchanged','photo_alignment')} for r in value['sessions']],
            'saved_real_alignment_supported':value['SAVED_REAL_ALIGNMENT_SUPPORTED']}
    stage('recorded_mapping_photo',recorded)
    for name,modules in CASES.items():stage(name,lambda name=name,modules=modules:execute(root,out,name,modules))
    for name,reason in NOT_RUN.items():
        dependencies=AUTOMATIC_OPERATIONS[name][1]
        blocked=[d for d in dependencies if report['stages'][d]['status']!='PASS']
        stage(name,lambda reason=reason,blocked=blocked:{'status':'SKIPPED_DEPENDENCY' if blocked else 'NOT_RUN',
            'reason':reason,'blocked_by':blocked})
    changed=[p for p,digest in source_hashes.items() if not (root/p).is_file() or hashlib.sha256((root/p).read_bytes()).hexdigest()!=digest]
    report['verification_sources_unchanged']=not changed;report['changed_sources']=changed
    report['checks_completed']=True
    report['status']='NEEDS_ATTENTION'
    failures=[{'stage':k,'reason':v.get('reason') or v['status']} for k,v in report['stages'].items() if v['status'] not in
        {'PASS','OFFLINE_PACKAGE_REVIEWED_FIELD_CHECK_REQUIRED'}]
    if changed:failures.insert(0,{'stage':'source_binding','reason':'VERIFICATION_SOURCE_CHANGED'})
    if not report['stages'].get('recorded_mapping_photo',{}).get('saved_real_alignment_supported',False):
        failures.append({'stage':'photo_alignment','reason':'SAVED_REAL_ALIGNMENT_UNSUPPORTED'})
    report['blockers']=failures;report['first_blocker']=failures[0] if failures else None
    checkpoint()
    return report,out
