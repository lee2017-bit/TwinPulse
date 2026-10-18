# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ordinary App/Chrome/Isaac flow; real saved Flash/Super, no response fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.process_manager import TwinPulseProcessManager
from scripts.verify_chat_sim_journey import copy_ordinary_settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--smoke-only',action='store_true',help='Actual idle project switches, zero model calls')
    parser.add_argument('--cases',type=int,default=6,choices=range(1,7))
    parser.add_argument('--authorization',type=Path)
    parser.add_argument('--saved-project',type=Path,help='Owned earlier live scene; smoke reopens it without model calls')
    parser.add_argument('--resume-saved',action='store_true',help='Continue the approved same saved job; never repeat observation or finished batches')
    parser.add_argument('--feedback-saved',action='store_true',help='Approved planner feedback, Cancel/Apply/Undo on earlier real text scene')
    parser.add_argument('--expected-revision')
    parser.add_argument('--expected-state-sha')
    parser.add_argument('--offset',type=int,default=0,choices=range(6))
    parser.add_argument('--case-ids',nargs='+',choices=('text-01','text-02','image-01','image-02','mixed-01','mixed-02'))
    parser.add_argument('--user-default', action='store_true', help='Start from a local copy of the actual default/history; never transmit its photos')
    parser.add_argument('--case-file', type=Path, help='Host-selected public input cases; supplied separately from copied user history')
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'outputs/product-flow-20261013'):
        raise ValueError('Named product acceptance output only')
    output.mkdir(parents=True,exist_ok=False)
    runtime=output/'runtime'
    original=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/provider_settings.json'
    copy_ordinary_settings(original,runtime)
    if not args.smoke_only:
        if args.authorization is None:raise ValueError('Explicit live test authorization required')
        scope=json.loads(args.authorization.read_text(encoding='utf-8'))
        os.environ['TWINPULSE_AGENT_TEST_SCOPE']=str(args.authorization.resolve())
        os.environ['TWINPULSE_BENCHMARK_EXPIRES_AT']=scope['expires_at']
    photographs=ROOT/'outputs/benchmark-overnight-20261011'
    cases=[dict(id='text-01',prompt='Create an estimated 6 by 5 metre bedroom with a bed, wardrobe, desk and chair.',image=None),
           dict(id='image-01',prompt='Create an editable approximate digital twin from this room photo. Keep uncertain dimensions explicit.',image=str(photographs/'public-bedroom-1280.jpg')),
           dict(id='mixed-01',prompt='Reconstruct this dining room approximately. Include the visible dining table and chairs, and keep dimensions estimated.',image=str(photographs/'public-dining.jpg')),
           dict(id='text-02',prompt='Create an estimated 10 by 8 metre warehouse with two shelf racks, a pallet, a box and a clear central aisle.',image=None),
           dict(id='image-02',prompt='Create an editable approximate twin of this living room. Preserve visible furniture and uncertain observations.',image=str(photographs/'public-living.jpg')),
           dict(id='mixed-02',prompt='Create this bedroom approximately and include a desk and a chair if visible. Keep hidden areas and scale unverified.',image=str(photographs/'public-bedroom-1280.jpg'))]
    cases=([case for case in cases if case['id'] in args.case_ids] if args.case_ids else cases[args.offset:args.offset+args.cases])
    if args.case_file:
        cases=json.loads(args.case_file.read_text(encoding='utf-8'))
        if not isinstance(cases,list) or not cases or any(set(case)!={'id','prompt','image'} for case in cases):
            raise ValueError('Invalid host public test cases')
        if args.case_ids:
            cases=[case for case in cases if case['id'] in args.case_ids]
    initial_project='flow_start'
    if args.user_default:
        import shutil
        initial_project='default'
        for name in ('active_project.json','active_project.conversation.json'):
            source=original.parent/name
            if source.is_file():shutil.copy2(source,runtime/name)
        if (original.parent/'inputs').is_dir():shutil.copytree(original.parent/'inputs',runtime/'inputs')
    if args.saved_project:
        import shutil
        source=args.saved_project.resolve()
        if not source.is_relative_to(ROOT/'outputs/product-flow-20261013'):raise ValueError('Owned earlier scene only')
        initial_project=source.name
        shutil.copytree(source,runtime/'projects'/initial_project)
        if args.resume_saved:
            for name in ('ordinary-generation','provider-evidence'):
                shutil.copytree(source.parent.parent/name,runtime/name)
    result=dict(status='FAIL',scope='real ordinary product acceptance, not comparative benchmark',
        physical_robot_connections=0,provider='saved production Flash/Super',input_cases=cases,
        smoke_only=args.smoke_only)
    carried_ids={r['attempt_id'] for p in (runtime/'ordinary-generation').glob('*.ledger.json')
        for r in json.loads(p.read_text())['requests']}
    source={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('packages/twinpulse_app/src','packages/twinpulse_provider/src','packages/twinpulse_core/src','extensions/twinpulse.extension','apps/twinpulse-web/dist')
            for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    result['source_sha256']=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
    manager=None
    try:
        manager=TwinPulseProcessManager(repo_root=ROOT,state_dir=runtime,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,
            ready_timeout_s=180.,project_id=initial_project)
        launch=manager.start(open_browser=False);base,ticket=manager.product_bootstrap()
        result['launch']=dict(launch_id=launch.launch_id,base_url=base,backend_pid=launch.backend_pid,engine_pid=launch.engine_pid)
        env={**os.environ,'TWINPULSE_FLOW_URL':base,'TWINPULSE_FLOW_BOOTSTRAP':ticket,
             'TWINPULSE_FLOW_OUTPUT':str(output),'TWINPULSE_FLOW_CASES':json.dumps(cases),
             'TWINPULSE_FLOW_SMOKE':'1' if args.smoke_only else '0',
             'TWINPULSE_FLOW_SAVED':'1' if args.saved_project else '0'}
        env['TWINPULSE_FLOW_USER_DEFAULT']='1' if args.user_default else '0'
        env['TWINPULSE_FLOW_RESUME']='1' if args.resume_saved else '0'
        env['TWINPULSE_FLOW_FEEDBACK']='1' if args.feedback_saved else '0'
        env['TWINPULSE_FLOW_EXPECTED_REVISION']=args.expected_revision or ''
        env['TWINPULSE_FLOW_EXPECTED_STATE']=args.expected_state_sha or ''
        node=Path('C:/Users/jaewo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
        with (output/'browser.log').open('x',encoding='utf-8') as stream:
            child=subprocess.run([str(node),str(ROOT/'apps/twinpulse-web/e2e/product-flow-live.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=env,stdout=stream,stderr=subprocess.STDOUT,
                timeout=7200,creationflags=subprocess.CREATE_NO_WINDOW)
        result['browser']=json.loads((output/'browser.json').read_text(encoding='utf-8'))
        result['status']=result['browser']['status'];result['browser_exit_code']=child.returncode
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:800])
    finally:
        # A timed-out HTTP worker may still settle: keep its backend alive while draining.
        deadline=time.monotonic()+310
        while list((runtime/'ordinary-generation').glob('*.dispatch-lock')) and time.monotonic()<deadline:
            time.sleep(.25)
        if manager:
            manager.stop()
            if manager.engine_result_file.exists():result['engine']=json.loads(manager.engine_result_file.read_text())
            if manager.supervisor_status_file.exists():result['supervisor']=json.loads(manager.supervisor_status_file.read_text())
        ledgers=[json.loads(p.read_text()) for p in (runtime/'ordinary-generation').glob('*.ledger.json')]
        rows=[r for ledger in ledgers for r in ledger['requests']]
        result['usage']=dict(requests=len(rows),prompt_tokens=sum(r.get('usage',{}).get('prompt_tokens',0) for r in rows),
            completion_tokens=sum(r.get('usage',{}).get('completion_tokens',0) for r in rows),
            unknown=sum(r['status']=='outcome_unknown' for r in rows),missing_usage=sum(not r.get('usage') for r in rows),
            monetary_limit=None,estimated_usd=None,invoice_verified=False,rows=rows)
        result['usage']['new_requests']=sum(r['attempt_id'] not in carried_ids for r in rows)
        result['usage']['carried_requests']=len(carried_ids)
        if args.authorization:
            result['agent_test_accounting']=json.loads(args.authorization.with_name('agent-test.ledger.json').read_text())
        result['source_unchanged']=all((ROOT/p).exists() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in source.items())
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(status=result['status'],requests=len(rows),output=str(output)),ensure_ascii=False),flush=True)
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
