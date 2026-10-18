# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Built Web/authenticated API/actual shared mission under report disk-full.

Synthetic raycast only. Existing local runtimes; no robot, paid provider,
Isaac or physical safety claim. Report fault injection stays in this verifier.
"""
import argparse
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=False)
    from tests.integration.test_automatic_mission_service import AutomaticMissionTests
    from tests.integration.test_a2_room_recipe import NoGateway
    from rehearse_offline_app import NoCredentials
    from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
    helper=AutomaticMissionTests();server=None
    result={'status':'FAIL','robot_connections':0,'provider_calls':0,'isaac':'NOT_RUN','physical_validation':'NOT_RUN'}
    secret=secrets.token_urlsafe(32);engine_secret=secrets.token_urlsafe(32)
    paths=[ROOT/p for p in ('scripts/verify_mission_storage_browser.py',
        'apps/twinpulse-web/e2e/mission-storage-failure.mjs','apps/twinpulse-web/src/AutomaticMission.tsx',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py','tests/integration/test_automatic_mission_service.py')]
    paths+=[p for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()]
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    try:
        helper.setUp();helper.configure([0.,-.6,0.]);pid='mission_room'
        broker=CommandBroker(project_id=pid)
        app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(helper.root,pid),project_id=pid)
        workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
        server=LocalApiServer(broker,product_bootstrap_secret=secret,engine_bootstrap_secret=engine_secret,
            product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=helper.root,
            credential_store=NoCredentials())
        server.automatic_mission.close();server.automatic_demo.close()
        server.automatic_mission=helper.service;server.automatic_demo=helper.automatic;server.start()
        node=shutil.which('node');chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
        if not node or not chrome.is_file():raise ValueError('EXISTING_BROWSER_RUNTIME_REQUIRED')
        environment=dict(os.environ,TWINPULSE_REHEARSAL_URL=server.base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=secret,
            TWINPULSE_REHEARSAL_OUTPUT=str(folder),TWINPULSE_REHEARSAL_CHROME=str(chrome),TWINPULSE_REHEARSAL_MAP=helper.map_id)
        original_open=Path.open
        def failing_report(path,*args,**kwargs):
            mode=args[0] if args else kwargs.get('mode','r')
            if 'automatic-mission' in path.parts and mode=='x':raise OSError(errno.ENOSPC,'SECRET_CANARY private path')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',failing_report):
            child=subprocess.run([node,str(ROOT/'apps/twinpulse-web/e2e/mission-storage-failure.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for name,data in (('stdout',child.stdout),('stderr',child.stderr)):
            (folder/f'browser-{name}.log').write_text(data.decode('utf-8',errors='replace').replace(secret,'[REDACTED]')[:128*1024],encoding='utf-8')
        browser=json.loads((folder/'browser-result.json').read_text(encoding='utf-8'));result['browser']=browser
        if child.returncode or browser['status']!='PASS':raise ValueError('BROWSER_STORAGE_ACCEPTANCE_FAILED')
        helper.service.worker.join(5)
        # The authenticated browser owns this job, not the fixture's old map
        # creator. Evaluate retained state without bypassing the public owner gate.
        with helper.service.lock:job=copy.deepcopy(helper.service.job)
        adapter=helper.adapters[-1]
        assert not helper.service.worker.is_alive() and adapter.velocity==(0.,0.) and adapter.halted>0
        assert job['report_status']=='FAILED' and job['report_errno']==28 and job['visual']['pose_room'] is None
        assert not job['physical_demo_ready'] and 'SECRET_CANARY' not in json.dumps(job)
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[p.relative_to(ROOT).as_posix()] for p in paths)
        result.update(status='PASS',checks=['built_Web_auth_API_actual_worker_typed_disk_full',
            'independent_final_halt_no_current_pose_or_saved_3D','reload_no_new_start_no_authority'])
    except Exception as exc:result.update(error_type=type(exc).__name__,reason=str(exc).replace(secret,'[REDACTED]')[:180])
    finally:
        if server:server.stop()
        if getattr(helper,'service',None):
            job=helper.service.job;adapter=helper.adapters[-1] if helper.adapters else None
            (folder/'job.json').write_text(json.dumps(job,allow_nan=False),encoding='utf-8')
            if adapter:(folder/'synthetic-raw.json').write_text(json.dumps({'complete':not helper.service.worker.is_alive(),
                'observations':adapter.raw,'commands':adapter.sent,'final_velocity':adapter.velocity},allow_nan=False),encoding='utf-8')
        helper.doCleanups();result['source_sha256']=hashes
        result['artifact_sha256']={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}
        (folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:result.get(k) for k in ('status','reason','robot_connections','physical_validation')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
