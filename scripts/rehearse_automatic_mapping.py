# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual built Web/API + saved ROS causal processing, no robot or engine.

Only the empty project scaffold is a fixture; no scan or API response is mocked.
Original inputs, project bytes and production source/build hashes are preserved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app import LocalApiServer,JsonProviderSettingsStore
from tests.integration.test_derived_review_selection import selection_fixture
from rehearse_offline_app import NoCredentials


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path,help='New exclusive local evidence directory')
    parser.add_argument('--recorded-1x',action='store_true',help='Explicit original receipt-time replay in the existing Web UI')
    args=parser.parse_args();output=args.output.resolve()
    chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
    node=shutil.which('node')
    if not node or not chrome.is_file():parser.error('Existing Node and Chrome required')
    output.mkdir(parents=True,exist_ok=False)
    app,workflow,broker,_,_,_=selection_fixture(output/'isolated-state')
    before=app._project_store.path.read_bytes()
    paths=[ROOT/p for p in (
        'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
        'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
        'packages/twinpulse_app/src/twinpulse_app/recorded_replay.py',
        'packages/twinpulse_app/src/twinpulse_app/saved_mapping_evidence.py',
        'packages/twinpulse_app/src/twinpulse_app/project_store.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py',
        'apps/twinpulse-web/src/AutomaticDemo.tsx','apps/twinpulse-web/src/api.ts','apps/twinpulse-web/src/App.tsx',
        'apps/twinpulse-web/e2e/automatic-mapping-real.mjs','scripts/rehearse_automatic_mapping.py')]
    paths.extend(p for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file())
    paths.extend(p for p in (ROOT/'artifacts/manual-control/1a7f033af112437699ca67aef3438ecb').rglob('*') if p.is_file())
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    bootstrap=secrets.token_urlsafe(32)
    server=LocalApiServer(broker,product_bootstrap_secret=bootstrap,engine_bootstrap_secret=secrets.token_urlsafe(32),
        product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=ROOT,
        provider_settings_store=JsonProviderSettingsStore(output/'isolated-state/settings.json'),credential_store=NoCredentials())
    result={'status':'FAIL','data':'PRESERVED_REAL_ROS_RECORDING','engine':'NOT_RUN','robot_connections':0,
            'provider_calls':0,'physical_demo_ready':False,'source_sha256':hashes}
    try:
        server.start()
        env=dict(os.environ,TWINPULSE_REHEARSAL_URL=server.base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=bootstrap,
            TWINPULSE_REHEARSAL_OUTPUT=str(output),TWINPULSE_REHEARSAL_CHROME=str(chrome),
            TWINPULSE_REPLAY_1X='1' if args.recorded_1x else '0')
        child=subprocess.run([node,str(ROOT/'apps/twinpulse-web/e2e/automatic-mapping-real.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=env,capture_output=True,text=True,timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if child.returncode:raise RuntimeError('BROWSER_CHECK_FAILED_SEE_STAGE_RECORD')
        browser=json.loads((output/'browser-result.json').read_text())
        if browser['status']!='PASS':raise RuntimeError('BROWSER_ACCEPTANCE_FAILED')
        if app._project_store.path.read_bytes()!=before or broker._operations:
            raise RuntimeError('UNEXPECTED_PROJECT_OR_ENGINE_MUTATION')
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.relative_to(ROOT))] for p in paths):
            raise RuntimeError('ORIGINAL_SOURCE_OR_BUILD_CHANGED')
        result.update(status='PASS',browser=browser,active_project_changed=False)
    except Exception as exc:result.update(error_type=type(exc).__name__,reason=str(exc)[:160])
    finally:
        server.stop()
        with (output/'verification.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:result[k] for k in ('status','data','robot_connections','engine','physical_demo_ready')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
