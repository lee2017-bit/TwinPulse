# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned actual Isaac host + built chat viewer. No provider, robot or physics Run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from scripts.verify_project_switch_isaac import _request as owner_request, _session
from twinpulse_app.process_manager import TwinPulseProcessManager


def _request(base,path,**kwargs):
    try:return owner_request(base,path,**kwargs)
    except HTTPError as exc:
        detail=json.loads(exc.read()).get('error',{})
        raise RuntimeError(f"{path}: HTTP {exc.code} / {detail.get('code','unknown')}: {detail.get('message','no reason')}") from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','isaac':'actual_local_owned_engine','scene':'synthetic saved room',
            'physics':'NOT_RUN','provider_calls':0,'robot_connections':0,'checks':[]}
    manager=None
    try:
        from tests.integration.test_a2_room_recipe import write_recipe
        from twinpulse_app.room_recipe import import_project_room_recipe,prepare_project_burger_visual
        state=output/'runtime'
        write_recipe(state,'viewer_room','blue',3.5)
        prepare_project_burger_visual(state,'viewer_room',(-.3,0,.002),0)
        draft=import_project_room_recipe(state,'viewer_room')
        manager=TwinPulseProcessManager(repo_root=ROOT,state_dir=state,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,fixture_mode=True,
            ready_timeout_s=180.,project_id='viewer_room')
        manager.start(open_browser=False)
        base,cookie,csrf=_session(manager)
        _,conversation,_=_request(base,'/v1/product/conversation',body={'action':'resume','request_id':'viewer-reopen',
            'expected_scene_revision':draft.site.scene.revision,'expected_input_revision':draft.input_revision.digest},cookie=cookie,csrf=csrf)
        result['conversation']=conversation
        _,workflow,_=_request(base,'/v1/product/workflow',cookie=cookie)
        summary=workflow['site_draft']
        result['workflow_before_build']=workflow
        _request(base,'/v1/product/draft/acknowledge',body={'revision':summary['revision']},cookie=cookie,csrf=csrf)
        _request(base,'/v1/product/lease',body={},cookie=cookie,csrf=csrf)
        # The lease reaches Kit on its next heartbeat; do not send Build before
        # an actual snapshot advertises the permitted command.
        deadline=time.monotonic()+6.
        while time.monotonic()<deadline:
            _,state_view,_=_request(base,'/v1/product/state',cookie=cookie)
            if state_view['engine_readiness']['site_scene_build_v2']['ready']:break
            time.sleep(.1)
        else:raise RuntimeError('Build permit not observed after acquiring the owned engine lease')
        _,operation,_=_request(base,'/v1/product/commands',body={'client_request_id':'viewer-build',
            'command_type':'build_site_scene','expected_applied_revision':summary['revision'],
            'artifact_id':summary['artifact_id']},cookie=cookie,csrf=csrf)
        deadline=time.monotonic()+45.
        while time.monotonic()<deadline:
            _,view,_=_request(base,'/v1/product/viewport',cookie=cookie)
            if view['frame']:break
            time.sleep(.2)
        else:raise TimeoutError('Actual owned renderer did not publish a fresh viewport')
        result['first_view']=view
        browser_base,ticket=manager.product_bootstrap()
        env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,'TWINPULSE_VIEW_OUTPUT':str(output)}
        completed=subprocess.run(['node',str(ROOT/'apps/twinpulse-web/e2e/live-viewport.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=env,timeout=70,check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        browser=json.loads((output/'browser.json').read_text(encoding='utf-8'));result['browser']=browser
        if completed.returncode or browser['status']!='PASS':raise RuntimeError('Actual viewer browser acceptance failed')
        _,product,_=_request(base,'/v1/product/state',cookie=cookie)
        result['engine_state']=product
        assert not any(op['command_type']=='run' for op in product['operations'])
        assert product['snapshot']['applied_revision']==summary['revision']
        result['checks'].extend(['actual native buffer → separate authenticated I/O → bounded memory API → built chat',
            'camera changes acknowledged by actual Isaac; no Run or robot command',
            'fold/reload preserve scene; no frame archive per tick; stale frames removed'])
        result['status']='PASS'
    except Exception as exc:
        result.update(error_type=type(exc).__name__,error=str(exc)[:500])
    finally:
        if manager:
            manager.stop()
            host=manager.engine_result_file
            if host.is_file():result['host']=json.loads(host.read_text(encoding='utf-8'))
        files=('scripts/twinpulse_engine_host.py','scripts/twinpulse_live_viewport.py',
            'packages/twinpulse_app/src/twinpulse_app/viewport_service.py','packages/twinpulse_app/src/twinpulse_app/api.py',
            'apps/twinpulse-web/src/TwinViewport.tsx','apps/twinpulse-web/src/viewport-types.ts',
            'apps/twinpulse-web/src/api.ts','apps/twinpulse-web/src/ChatWorkspace.tsx','apps/twinpulse-web/src/chat.css',
            'scripts/verify_live_viewport.py','apps/twinpulse-web/e2e/live-viewport.mjs')
        result['source_sha256']={file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in files}
        result['web_sha256']={str(file.relative_to(ROOT)):hashlib.sha256(file.read_bytes()).hexdigest()
            for file in (ROOT/'apps/twinpulse-web/dist').rglob('*') if file.is_file()}
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('LIVE_VIEWPORT='+result['status'],flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
