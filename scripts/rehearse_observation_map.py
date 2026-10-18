# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real production Web/API + preserved real ROS data; no engine or robot.

Launches only an owned loopback server and headless browser. No credential
lookup, robot adapters, external requests, fake scan responses or installations.
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
from twinpulse_app import LocalApiServer, JsonProviderSettingsStore
from tests.integration.test_derived_review_selection import selection_fixture
from rehearse_offline_app import NoCredentials


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path,help='New exclusive evidence directory')
    args=parser.parse_args();output=args.output.resolve()
    chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
    node=shutil.which('node')
    if not node or not chrome.is_file():parser.error('Existing Node and Chrome required')
    output.mkdir(parents=True,exist_ok=False)
    # Fixture scaffolds an isolated empty workflow, NOT the ROS data or API.
    app,workflow,broker,_,_,_=selection_fixture(output/'isolated-state')
    before=app._project_store.path.read_bytes()
    source_paths=[ROOT/name for name in ('packages/twinpulse_core/src/twinpulse_core/scan_observation.py',
        'packages/twinpulse_core/src/twinpulse_core/observation_model_comparison.py',
        'packages/twinpulse_app/src/twinpulse_app/room_localization_review.py',
        'apps/twinpulse-web/src/ObservationMap.tsx','apps/twinpulse-web/src/App.tsx')]
    source_paths.append(ROOT/'apps/twinpulse-web/src/ModelComparison.tsx')
    source_paths.extend(ROOT/name for name in (
        'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
        'packages/twinpulse_core/src/twinpulse_core/sensor_photo_link.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py',
        'apps/twinpulse-web/src/SensorPhotoLink.tsx',
        'apps/twinpulse-web/src/SensorMapLocalization.tsx','apps/twinpulse-web/src/api.ts'))
    source_paths.extend(p for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file())
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    bootstrap=secrets.token_urlsafe(32)
    server=LocalApiServer(broker,product_bootstrap_secret=bootstrap,engine_bootstrap_secret=secrets.token_urlsafe(32),
        product_workflow=workflow,static_root=ROOT/'apps/twinpulse-web/dist',session_history_root=ROOT,
        provider_settings_store=JsonProviderSettingsStore(output/'isolated-state/settings.json'),credential_store=NoCredentials())
    result={'status':'FAIL','data':'PRESERVED_REAL_ROS_RECORDING','engine':'NOT_RUN','robot_connections':0,
            'provider_calls':0,'physical_demo_ready':False,'source_sha256':hashes}
    try:
        server.start()
        env=dict(os.environ,TWINPULSE_REHEARSAL_URL=server.base_url,TWINPULSE_REHEARSAL_BOOTSTRAP=bootstrap,
            TWINPULSE_REHEARSAL_OUTPUT=str(output),TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child=subprocess.run([node,str(ROOT/'apps/twinpulse-web/e2e/observation-map-real.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=env,capture_output=True,text=True,timeout=160,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if child.returncode:raise RuntimeError('BROWSER_CHECK_FAILED_SEE_STAGE_RECORD')
        browser=json.loads((output/'browser-result.json').read_text())
        if browser['status']!='PASS':raise RuntimeError('BROWSER_ACCEPTANCE_FAILED')
        if app._project_store.path.read_bytes()!=before or broker._operations:
            raise RuntimeError('UNEXPECTED_PROJECT_OR_ENGINE_MUTATION')
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p.relative_to(ROOT))] for p in source_paths):
            raise RuntimeError('SOURCE_OR_BUILD_CHANGED_DURING_REHEARSAL')
        result.update(status='PASS',browser=browser,active_project_changed=False)
    except Exception as exc:result.update(error_type=type(exc).__name__,reason=str(exc)[:160])
    finally:
        server.stop()
        with (output/'verification.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:result[k] for k in ('status','data','robot_connections','engine','physical_demo_ready')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
