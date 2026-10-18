# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual chat UI/API/owned Isaac project round trip, without generation/motion.

Only the initial saved v2 room is an explicit local fixture. Lifecycle uses
production start/monitor/stop methods; a browser bootstrap replaces new windows.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))


def main():
    from twinpulse_app.process_manager import TwinPulseProcessManager, PROJECT_SWITCH_REQUESTED
    from twinpulse_app.project_store import ProjectStore, ProjectRecord
    from twinpulse_core import InputArtifactStore
    from tests.integration.test_scene_changes import furnished_source
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--build-round-trip',action='store_true',help='Display the saved Twin before switching and after secure reopen')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    state=output/'runtime';record=furnished_source()
    store=ProjectStore.for_project(state,'default')
    InputArtifactStore(store.input_root()).save(record.input_revision,())
    store.save(ProjectRecord(project_id='default',latest_input=record.input_revision,site_draft=record))
    original=(state/'active_project.json').read_bytes()
    paths=['scripts/verify_chat_project_switch.py','apps/twinpulse-web/e2e/chat-project-switch.mjs',
        'packages/twinpulse_app/src/twinpulse_app/process_manager.py',
        'packages/twinpulse_app/src/twinpulse_app/startup_checks.py',
        'packages/twinpulse_app/src/twinpulse_app/simulation_assets.py','packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/project_store.py','packages/twinpulse_app/src/twinpulse_app/project_catalog.py',
        'packages/twinpulse_app/src/twinpulse_app/conversation_service.py','packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'packages/twinpulse_app/src/twinpulse_app/command_broker.py','packages/twinpulse_app/src/twinpulse_app/application.py',
        'apps/twinpulse-web/src/ChatWorkspace.tsx','apps/twinpulse-web/src/ChatProjects.tsx',
        'apps/twinpulse-web/src/types.ts','apps/twinpulse-web/src/api.ts',
        'apps/twinpulse-web/vite.config.ts','scripts/twinpulse_backend.py','scripts/twinpulse_engine_host.py',
        'tests/integration/test_scene_changes.py']
    def hashes():
        return ({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()})
    initial_source,initial_web=hashes()
    result=dict(status='FAIL',saved_room='explicit_v2_fixture',provider_calls=0,robot_connections=0,
                physics_motion='NOT_RUN',phases=[],launches=[])
    result['build_round_trip']=args.build_round_trip
    manager=None
    try:
        for phase, project, target in [('create_switch','default','room_two'),('switch_back','room_two','default'),('reopen','default',None)]:
            manager=TwinPulseProcessManager(repo_root=ROOT,state_dir=state,python_executable=Path(sys.executable),
                isaac_python=Path('C:/isaacsim/python.bat'),headless=True,fixture_mode=True,ready_timeout_s=180.) if project=='default' else \
                TwinPulseProcessManager(repo_root=ROOT,state_dir=state,python_executable=Path(sys.executable),
                isaac_python=Path('C:/isaacsim/python.bat'),headless=True,fixture_mode=True,ready_timeout_s=180.,project_id=project)
            launch=manager.start(open_browser=False)
            base,ticket=manager.product_bootstrap()
            environment={**os.environ,'TWINPULSE_SWITCH_URL':base,'TWINPULSE_SWITCH_BOOTSTRAP':ticket,
                'TWINPULSE_SWITCH_OUTPUT':str(output),'TWINPULSE_SWITCH_PHASE':phase,
                'TWINPULSE_SWITCH_BUILD':'1' if args.build_round_trip else '0',
                'TWINPULSE_SWITCH_PREVIOUS_FRAME':json.dumps(result['phases'][0].get('current_frame')) if result['phases'] else 'null'}
            child=subprocess.run(['node',str(ROOT/'apps/twinpulse-web/e2e/chat-project-switch.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=environment,timeout=70,check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            browser=json.loads((output/(phase+'.json')).read_text(encoding='utf-8'))
            result['phases'].append(browser)
            if child.returncode or browser['status']!='PASS': raise RuntimeError(browser.get('error','Browser failed'))
            if target:
                if manager.monitor(poll_s=.1)!=PROJECT_SWITCH_REQUESTED or manager.requested_project_id!=target:
                    raise RuntimeError('Owned monitor did not consume exact project switch')
            manager.stop()
            supervisor=json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))
            host=json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            if supervisor['status']!='stopped' or manager._owned or manager.lock_file.exists():raise RuntimeError('Owned cleanup was not complete')
            # Legacy host verdict requires a built scene/capture; this rehearsal
            # deliberately sends no Build. Preserve FAIL rather than fabricate
            # a scene PASS, and check only the startup/idle scope requested here.
            if args.build_round_trip and project=='default':
                if (host.get('status')!='PASS' or host.get('prim_count',0)<=0
                        or host.get('live_viewport',{}).get('sent',0)<=0
                        or host.get('applied_revision')!=browser['current_frame']['applied_revision']
                        or host.get('max_movement_m')!=0):
                    raise RuntimeError('Saved Twin was not actually built and rendered in this secure session')
            elif (host.get('engine_connected') is not True or host.get('runtime_state')!='idle'
                    or host.get('prim_count')!=0 or host.get('max_movement_m')!=0
                    or host.get('capture',{}).get('status')!='NOT_RUN' or host.get('error_type')):
                raise RuntimeError('No-build idle host scope was not observed')
            result['launches'].append(dict(project=project,launch_id=launch.launch_id,stage_epoch=launch.stage_epoch,
                supervisor=supervisor,host_scene_verdict=host['status'],host_startup_idle_observed=project!='default' or not args.build_round_trip))
            if any(r['state']!='ready' for r in supervisor['startup_checks']):raise RuntimeError('Static prerequisite checklist contains a gap')
            manager=None
            if (state/'active_project.json').read_bytes()!=original:raise RuntimeError('Original saved project changed')
        if len({r['launch_id'] for r in result['launches']})!=3:raise RuntimeError('Launch identity reused')
        result.update(status='PASS',original_project_unchanged=True,original_sha256=hashlib.sha256(original).hexdigest())
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:1200])
    finally:
        if manager:
            manager.stop()
            result['failed_supervisor']=json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))
        final_source,final_web=hashes()
        result['source_sha256']=initial_source;result['web_sha256']=initial_web
        result['source_and_build_unchanged']=initial_source==final_source and initial_web==final_web
        if not result['source_and_build_unchanged']:result.update(status='FAIL',error='Test source or Web build changed during execution')
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('CHAT_PROJECT_SWITCH='+result['status'],flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
