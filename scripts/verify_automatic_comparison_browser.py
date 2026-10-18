# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual built Web/API/shared pair with private synthetic evaluation truth."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
for p in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/p/'src'))
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))


def verify(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'artifacts'):raise ValueError('OWNED_ARTIFACT_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','robot_connections':0,'paid_calls':0,'physical_validation':'NOT_RUN','isaac':'NOT_RUN'}
    sources=[p for d in ('packages/twinpulse_core/src','packages/twinpulse_app/src','apps/twinpulse-web/dist') for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.css','.html'}]
    runner=ROOT/'apps/twinpulse-web/e2e/automatic-comparison-real.mjs';sources.extend([Path(__file__),runner])
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    secret=secrets.token_urlsafe(32);server=None
    try:
        from tests.integration.test_automatic_photo_service import recipe
        from tests.integration.test_automatic_demo_service import GEOMETRY
        from tests.integration.test_a2_room_recipe import NoGateway
        from rehearse_offline_app import NoCredentials
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore,LocalApiServer
        from twinpulse_app.automatic_demo_service import AutomaticDemoService
        from twinpulse_app.automatic_comparison_service import AutomaticComparisonService
        with TemporaryDirectory(prefix='tp-comparison-browser-') as directory,ExitStack() as cleanup:
            root=Path(directory);pid='comparison_room';outline,_=recipe(root,pid,1.)
            broker=CommandBroker(project_id=pid)
            app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(root,pid),project_id=pid)
            workflow=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
            workflow.continue_room_recipe()
            server=LocalApiServer(broker,product_bootstrap_secret=secret,engine_bootstrap_secret=secrets.token_urlsafe(32),
                product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=root,credential_store=NoCredentials())
            cleanup.callback(server.stop)
            server.automatic_comparison.close()
            automatic=AutomaticDemoService(root,pid,geometry_loader=lambda:GEOMETRY)
            cleanup.callback(automatic.close)
            server.automatic_comparison=AutomaticComparisonService(automatic,world_loader=lambda *_:outline)
            def preserve_pair():
                service=server.automatic_comparison
                service.close()
                if service.worker:service.worker.join(5)
                if service.job:
                    result['worker_complete']=not service.worker or not service.worker.is_alive()
                    folder=root/'artifacts/automatic-comparison'/service.job['job_id']
                    if folder.is_dir():shutil.copytree(folder,output/'executed-pair')
                    snapshot={k:v for k,v in service.job.items() if k!='owner'}
                    (output/'job.json').write_text(json.dumps(snapshot,allow_nan=False),encoding='utf-8')
            cleanup.callback(preserve_pair)
            server.start()
            node=shutil.which('node');chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            if not node or not chrome.is_file():raise ValueError('EXISTING_BROWSER_RUNTIME_REQUIRED')
            env=dict(os.environ,TWINPULSE_REHEARSAL_URL=server.base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=secret,
                TWINPULSE_REHEARSAL_OUTPUT=str(output),TWINPULSE_REHEARSAL_CHROME=str(chrome))
            child=subprocess.run([node,str(runner)],cwd=runner.parent,env=env,capture_output=True,timeout=190)
            for name,data in (('stdout',child.stdout),('stderr',child.stderr)):
                (output/(name+'.log')).write_text(data.decode('utf-8',errors='replace').replace(secret,'[REDACTED]')[:65536],encoding='utf-8')
            browser=json.loads((output/'browser-result.json').read_text());result['browser']=browser
            service=server.automatic_comparison
            service.worker.join(5);job=service.job
            result['job_state']=job['state'];result['pair_id']=job['job_id']
            if child.returncode or browser['status']!='PASS':raise ValueError('COMPARISON_BROWSER_FAILED')
            if service.worker.is_alive() or job['state']!='COMPLETED':raise ValueError('COMPARISON_WORKER_NOT_COMPLETE')
            result['source_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
            if not result['source_unchanged']:raise ValueError('VERIFICATION_SOURCE_CHANGED')
            result['status']='PASS'
        server=None
    except Exception as exc:result.update(reason=str(exc).replace(secret,'[REDACTED]')[:180],error_type=type(exc).__name__)
    finally:
        if server:server.stop()
        result['source_sha256']=hashes
        result['artifact_sha256']={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
        (output/'verification.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({k:result.get(k) for k in ('status','reason','job_state','robot_connections')}))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    raise SystemExit(0 if verify(args.output)['status']=='PASS' else 2)
