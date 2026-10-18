# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Saved synthetic survey -> actual built chat/API/Isaac. No robot transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from scripts.verify_live_viewport import _request,_session
from twinpulse_app.process_manager import TwinPulseProcessManager

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('source_runtime',type=Path);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','observations':'SAVED_SYNTHETIC_SHARED_SURVEY','robot_connections':0,'provider_calls':0,
            'isaac':'NOT_RUN','physical_validation':'NOT_RUN'};manager=None
    files=['scripts/verify_chat_inspection_browser.py','apps/twinpulse-web/e2e/chat-inspection-saved.mjs',
        'packages/twinpulse_app/src/twinpulse_app/chat_inspection_visual.py','packages/twinpulse_app/src/twinpulse_app/chat_inspection.py',
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py','packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
        'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py','packages/twinpulse_app/src/twinpulse_app/automatic_photo_store.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py','packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'packages/twinpulse_core/src/twinpulse_core/engine_contracts.py','packages/twinpulse_app/src/twinpulse_app/simulation_assets.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py','extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py',
        'apps/twinpulse-web/src/ChatInspectionBuild.tsx','apps/twinpulse-web/src/ChatWorkspace.tsx',
        'apps/twinpulse-web/src/conversation-types.ts','apps/twinpulse-web/src/api.ts','scripts/twinpulse_engine_host.py',
        'scripts/twinpulse_backend.py','packages/twinpulse_app/src/twinpulse_app/process_manager.py',
        'extensions/twinpulse.extension/twinpulse/extension/extension.py']
    before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
    web={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
    try:
        from twinpulse_app.chat_inspection_visual import KIND,checked_inspection_visual
        from twinpulse_app.project_store import ProjectStore
        from twinpulse_app.conversation_service import ConversationService
        state=output/'runtime';shutil.copytree(args.source_runtime.resolve(),state)
        paths=list((state/'artifacts/automatic-mission/current_chat').glob('*.json'))
        if len(paths)!=1:raise ValueError('EXACT_SYNTHETIC_SURVEY_REPORT_REQUIRED')
        report=json.loads(paths[0].read_text(encoding='utf-8'))
        descriptor={'kind':KIND,'mission_id':report['job_id'],'manifest_sha256':report['revision']}
        scene,_=checked_inspection_visual(state,'current_chat',descriptor)
        store=ProjectStore.for_project(state,'current_chat');draft=store.load().site_draft
        history=ConversationService(SimpleNamespace(_broker=SimpleNamespace(project_id='current_chat')),
            store.path.with_suffix('.conversation.json'))
        history._state.update(mode='REAL',robot_id='turtlebot3_burger',inspection_display=descriptor)
        history._message('assistant','Saved synthetic survey. The final pose and scan are historical candidates, not current navigation permission.')
        history._persist()
        original=store.path.read_bytes()
        # Match production's split project/archive roots, without touching real raw files.
        archive=output/'evidence';archive.mkdir();shutil.copytree(state/'artifacts',archive/'artifacts')
        manager=TwinPulseProcessManager(repo_root=ROOT,state_dir=state,session_history_root=archive,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,fixture_mode=True,
            ready_timeout_s=180.,project_id='current_chat')
        manager.start(open_browser=False);result['isaac']='ACTUAL_RUNTIME_STARTED_BROWSER_ACCEPTANCE_PENDING'
        base,cookie,csrf=_session(manager)
        _request(base,'/v1/product/conversation',body={'action':'resume','request_id':'explicit-source-reopen',
            'expected_scene_revision':draft.site.scene.revision,'expected_input_revision':draft.input_revision.digest},cookie=cookie,csrf=csrf)
        _,ticket=manager.product_bootstrap()
        env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,'TWINPULSE_VIEW_OUTPUT':str(output),
            'TWINPULSE_SURVEY_SCENE':scene.revision}
        completed=subprocess.run(['node',str(ROOT/'apps/twinpulse-web/e2e/chat-inspection-saved.mjs')],
            cwd=ROOT/'apps/twinpulse-web',env=env,timeout=100,check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        browser=json.loads((output/'browser.json').read_text(encoding='utf-8'));result['browser']=browser
        if completed.returncode or browser['status']!='PASS':raise RuntimeError(str(browser.get('error')))
        assert store.path.read_bytes()==original
        assert before=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
        assert web=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
        result.update(status='PASS',isaac='ACTUAL_CHAT_API_ISAAC_SAVED_DISPLAY_PASS',source_sha256=before,web_sha256=web)
    except Exception as exc:
        result.update(error_type=type(exc).__name__,error=str(exc)[:1200])
    finally:
        if manager:
            manager.stop()
            if manager.engine_result_file.is_file():result['host']=json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
        (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result.get(k) for k in ('status','isaac','error')}),flush=True)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
