# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual ordinary generation UI with NO engine. No Isaac/robot/Build/Run/Stop.

Caller supplies isolated reviewed settings and fresh human authorization. Uses
the unchanged production backend, compiled React UI, registered secure keys and
ordinary on-screen approval. Model responses are never mocked or replaced.
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
import time
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--photo',type=Path,required=True)
    parser.add_argument('--settings',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    runtime=output/'runtime';runtime.mkdir()
    for package in ('twinpulse_app','twinpulse_provider','twinpulse_core'):
        sys.path.insert(0,str(ROOT/'packages'/package/'src'))
    from twinpulse_app.settings import JsonProviderSettingsStore
    from twinpulse_app.key_registry import KeyRegistry
    from twinpulse_app.credentials import WindowsCredentialStore
    from twinpulse_app.stage_routing import StageRoutingSettings
    settings=JsonProviderSettingsStore(args.settings)
    registry=KeyRegistry(settings,WindowsCredentialStore())
    paths=(settings.path,registry.path,StageRoutingSettings(registry).path)
    for item in paths:shutil.copyfile(item,runtime/item.name)
    photo=output/args.photo.name;shutil.copyfile(args.photo,photo)
    ready=output/'backend-ready.json'
    owner=secrets.token_urlsafe(32)
    env={**os.environ,'TWINPULSE_PRODUCT_BOOTSTRAP':owner,
         'TWINPULSE_ENGINE_BOOTSTRAP':secrets.token_urlsafe(32)}
    command=[sys.executable,'-B',str(ROOT/'scripts/twinpulse_backend.py'),
        '--port','0','--ready-file',str(ready),
        '--static-root',str(ROOT/'apps/twinpulse-web/dist'),
        '--settings-path',str(runtime/args.settings.name),
        '--session-history-root',str(output),'--bootstrap-ttl-s','180','--profile-generation']
    result={'status':'FAIL','scope':'actual generation-only UI; no engine registered',
            'isaac_started':False,'robot_connections':0,'engine_commands':0}
    backend=None
    try:
        with (output/'backend.log').open('x',encoding='utf-8') as log:
            backend=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        deadline=time.monotonic()+30
        while not ready.is_file():
            if backend.poll() is not None:raise RuntimeError('Owned backend exited before readiness; see backend.log')
            if time.monotonic()>deadline:raise TimeoutError('Owned backend readiness timeout')
            time.sleep(.1)
        base=json.loads(ready.read_text(encoding='utf-8'))['base_url']
        request=Request(base+'/v1/bootstrap/product/issue',data=json.dumps({'owner_secret':owner}).encode(),
                        headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=5) as response:ticket=json.loads(response.read())['bootstrap_secret']
        browser_env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,
                     'TWINPULSE_VIEW_OUTPUT':str(output),'TWINPULSE_JOURNEY_IMAGE':str(photo)}
        with (output/'browser.log').open('x',encoding='utf-8') as log:
            browser=subprocess.run(['node',str(ROOT/'apps/twinpulse-web/e2e/live-generation-screen.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=browser_env,stdout=log,stderr=subprocess.STDOUT,timeout=1020,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        browser_result=json.loads((output/'browser-result.json').read_text(encoding='utf-8'))
        result.update(status=browser_result['status'],browser=browser_result,browser_returncode=browser.returncode)
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:1200])
    finally:
        directory=runtime/'ordinary-generation'
        deadline=time.monotonic()+310
        while any(directory.glob('*.dispatch-lock')) and time.monotonic()<deadline:time.sleep(.5)
        ledgers=[json.loads(p.read_text(encoding='utf-8')) for p in directory.glob('*.ledger.json')]
        rows=[r for v in ledgers for r in v['requests']]
        audit={'approvals':len(ledgers),'requests':len(rows),'max_requests':[v['max_requests'] for v in ledgers],
               'limits_usd':[v['limit_usd'] for v in ledgers], 'statuses':[r['status'] for r in rows],
               'locks_pending':len(list(directory.glob('*.dispatch-lock'))),'rows':[]}
        for row in rows:
            attempt=row['attempt_id'];root=runtime/'provider-evidence'
            raw=json.loads((root/f'{attempt}.json').read_text(encoding='utf-8'))
            dispatch=json.loads((root/'dispatches'/f'{attempt}.json').read_text(encoding='utf-8'))
            validations=[json.loads(p.read_text(encoding='utf-8')) for p in (root/'validations').glob(f'{attempt}-*.json')]
            raw_ok=(hashlib.sha256(raw['response_redacted'].encode()).hexdigest()==raw['stored_response_sha256']
                    and raw.get('usage')==row.get('usage'))
            audit['rows'].append({'attempt_id':attempt,'model_id':raw.get('model_id'),
                'elapsed_s':raw.get('elapsed_s'),'usage':raw.get('usage'),'finish_reason':raw.get('finish_reason'),
                'max_tokens':raw.get('max_tokens'),'raw_ledger_match':raw_ok,
                'execution_id':dispatch.get('execution_id'),'dispatch_saved':True,
                'validation_files':len(validations),
                'dispatch_sha_matches':hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest()==dispatch['stored_request_sha256']})
        result['ordinary_live_audit']=audit
        if len(ledgers)!=1 or len(rows)>10 or audit['locks_pending'] or not all(r['raw_ledger_match'] and r['dispatch_sha_matches'] and r['validation_files'] for r in audit['rows']):
            result.update(status='FAIL',audit_error='Ledger/request/evidence audit failed')
        if backend is not None:
            backend.terminate()
            try:backend.wait(timeout=10)
            except subprocess.TimeoutExpired:backend.kill();backend.wait(timeout=5)
            result['owned_backend_exited']=backend.poll() is not None
        write(output/'result.json',result)
        print(json.dumps({'status':result['status'],'requests':len(rows),'error':result.get('error')},ensure_ascii=True))


if __name__=='__main__':main()
