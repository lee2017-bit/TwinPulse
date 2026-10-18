# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fresh ordinary App/API/Isaac draft acceptance under one frozen USD10 scope.

Does not weaken task/quality gates or reuse responses. Draft PASS is distinct
from movement, measured reconstruction or physical LiDAR acceptance.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from scripts.progressive_functional_scope import check_scope,reserve,exclusive,update,audit_runtime
from scripts.benchmark_protocol import read_json,source_freeze,canonical_sha,file_sha
from scripts.verify_chat_sim_journey import copy_ordinary_settings
from twinpulse_app.process_manager import TwinPulseProcessManager


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope',type=Path);parser.add_argument('case_id')
    parser.add_argument('--node',type=Path,required=True)
    args=parser.parse_args();scope_path=args.scope.resolve();directory=scope_path.parent
    if not directory.is_relative_to(ROOT/'outputs/progressive-twin-overnight-20261012'):
        raise ValueError('NAMED_OVERNIGHT_SCOPE_ONLY')
    scope=check_scope(scope_path,ROOT);case=next(c for c in scope['cases'] if c['case_id']==args.case_id)
    lock=directory/'functional-owner.lock';lock_fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    os.write(lock_fd,json.dumps(dict(pid=os.getpid(),case_id=args.case_id,scope_sha256=canonical_sha(scope))).encode())
    os.close(lock_fd)
    output=directory/args.case_id;manager=None;reserved=False
    result=dict(status='FAIL',acceptance_scope='ordinary fresh draft/edit, not comparative benchmark or motion',
        case_id=args.case_id,input_mode=case['input_mode'],provider='fresh_actual_HTTP',
        physical_robot_connections=0,physics_run='NOT_RUN',photo_fidelity='UNMEASURED_NOT_CERTIFIED',
        source_scope_sha256=file_sha(scope_path))
    try:
        case=reserve(scope,directory/'functional-finance.json',args.case_id);reserved=True
        output.mkdir(exist_ok=False);runtime=output/'runtime'
        copy_ordinary_settings(scope['settings_path'],runtime)
        if case['image']:
            copied_image=output/'approved-input.jpg'
            shutil.copyfile(case['image']['path'],copied_image)
            if file_sha(copied_image)!=case['image']['sha256']:
                raise ValueError('FUNCTIONAL_INPUT_COPY_SHA_CHANGED')
            case={**case,'image':{**case['image'],'path':str(copied_image)}}
        class ProfiledManager(TwinPulseProcessManager):
            def _backend_command(self):return [*super()._backend_command(),'--profile-generation']
        manager=ProfiledManager(repo_root=ROOT,state_dir=runtime,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,
            fixture_mode=False,ready_timeout_s=180.)
        os.environ['TWINPULSE_BENCHMARK_EXPIRES_AT']=scope['expires_at']
        manager.start(open_browser=False);base,ticket=manager.product_bootstrap()
        env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,
            'TWINPULSE_VIEW_OUTPUT':str(output),'TWINPULSE_FUNCTIONAL_CASE':json.dumps(case),
            'TWINPULSE_FUNCTIONAL_DEADLINE':scope['expires_at']}
        with (output/'browser-driver.log').open('x',encoding='utf-8') as stream:
            completed=subprocess.run([str(args.node),str(ROOT/'apps/twinpulse-web/e2e/progressive-creation-journey.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=2500,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        browser=read_json(output/'browser.json');result['browser']=browser
        result['browser_returncode']=completed.returncode
        if completed.returncode or browser['status']!='PASS':raise RuntimeError('Actual functional journey failed; browser first error preserved')
        result['status']='PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:800])
        if (output/'browser.json').is_file():result['browser']=read_json(output/'browser.json')
    finally:
        if manager:
            dispatch=output/'runtime/ordinary-generation';drain=time.monotonic()+310
            while list(dispatch.glob('*.dispatch-lock')) and time.monotonic()<drain:time.sleep(.5)
            manager.stop()
            if manager.engine_result_file.is_file():result['engine']=read_json(manager.engine_result_file)
            result['supervisor']=read_json(manager.supervisor_status_file)
            if any(result['supervisor'].get(k,{}).get('owned') for k in ('backend','engine')):
                result.update(status='FAIL',cleanup_error='OWNED_PROCESS_STILL_ACTIVE')
        if reserved:
            state=read_json(directory/'functional-finance.json');row=state['runs'][-1]
            try:
                audit=audit_runtime(output/'runtime',request_limit=case['request_limit'],total_limit=case['reservation_usd'])
                result['financial_audit']=audit
                if any(r['model_id'] not in scope['models'].values() for r in audit['rows']):
                    raise ValueError('FUNCTIONAL_MODEL_CHANGED')
                row.update(settled=True,status=result['status'],estimated_usd=audit['estimated_usd'],held_usd=audit['held_usd'],
                    unknown_requests=audit['unknown_requests'],request_count=audit['request_count'])
                if any(r['finish_reason']=='length' for r in audit['rows']):
                    row['stop_reason']='OUTPUT_LENGTH_STOP';state['stop_reason']='OUTPUT_LENGTH_STOP'
            except Exception as error:
                result.update(status='FAIL',financial_audit_error=type(error).__name__,financial_audit_error_code=str(error)[:300])
                row.update(settled=False,status='UNKNOWN',estimated_usd='0',held_usd=case['reservation_usd'],
                    unknown_requests=1,audit_error_type=type(error).__name__)
            row['finished_at']=datetime.now(timezone.utc).isoformat()
            update(directory/'functional-finance.json',state)
        result['source_and_build_unchanged']=source_freeze(ROOT)==scope['source_freeze']
        result['scope_settings_unchanged']=all(file_sha(p)==sha for p,sha in scope['settings_freeze'].items())
        if not result['source_and_build_unchanged'] or not result['scope_settings_unchanged']:
            result.update(status='FAIL',freeze_error='SOURCE_OR_SETTINGS_CHANGED')
        if result['status']=='PASS':
            try:
                from twinpulse_app import ApplicationService
                from twinpulse_app.project_store import ProjectStore
                store=ProjectStore(output/'runtime/active_project.json');before=store.path.read_bytes()
                restored=ApplicationService(None,project_store=store);history=restored.scene_change_store().load()
                effective=history.effective(restored.site_draft)
                expected=result['browser']['final_draft']
                if (history.current_scene_revision!=expected['revision']
                        or history.state_sha256(effective)!=expected['scene_state_sha256']
                        or store.path.read_bytes()!=before):raise ValueError('FUNCTIONAL_CLOSED_STORAGE_CHANGED')
                public_refinement=expected.get('draft_refinement')
                persisted_refinement=restored.site_draft.draft_refinement
                if public_refinement is not None:
                    if (persisted_refinement is None or
                            any(public_refinement.get(key)!=value for key,value in persisted_refinement.items()) or
                            public_refinement.get('quality_review',{}).get('status')!='needs_revision' or
                            public_refinement.get('physical_authority') is not False):
                        raise ValueError('FUNCTIONAL_CLOSED_REFINEMENT_CHANGED')
                    if persisted_refinement['schema_version']=='draft-refinement-1.1':
                        from twinpulse_core.progressive_twin import checked_envelope
                        progressive=checked_envelope(restored.site_draft.progressive_twin,restored.site_draft.plan.to_dict())
                        if (progressive['sha256']!=persisted_refinement['progressive_sha256'] or
                                not progressive['unresolved'] or persisted_refinement['geometry_checks']['checks_complete'] is not False or
                                persisted_refinement['geometry_checks']['materialized_subset_checked'] is not True or
                                persisted_refinement['geometry_checks']['inventory_complete'] is not False):
                            raise ValueError('FUNCTIONAL_CLOSED_SUBSET_REFINEMENT_CHANGED')
                    result['closed_draft_refinement']=dict(status='DURABLE_NEEDS_REVISION_NOT_QUALITY_PASS',
                        sha256=persisted_refinement['sha256'],candidate_revision=persisted_refinement['candidate_revision'],
                        issue_count=len(persisted_refinement['quality_review']['issues']),
                        stop_reason=persisted_refinement['stop_reason'],physical_authority=False)
                elif persisted_refinement is not None:
                    raise ValueError('FUNCTIONAL_CLOSED_REFINEMENT_UNREPORTED')
                result['closed_storage_reopen']=dict(status='PASS',revision=history.current_scene_revision,
                    state_sha256=history.state_sha256(effective),physical_authority=False,
                    engine_restarted=False,claim='Closed loader; actual runtime restart separately checked in G2/G3')
            except Exception as error:result.update(status='FAIL',closed_storage_error=type(error).__name__)
        if reserved:
            state=read_json(directory/'functional-finance.json');row=state['runs'][-1]
            row['product_status']=result['status']
            if row['settled']:row['status']=result['status']
            update(directory/'functional-finance.json',state)
        if output.is_dir():exclusive(output/'result.json',result)
        os.environ.pop('TWINPULSE_BENCHMARK_EXPIRES_AT',None)
        lock.unlink()
    print(json.dumps(dict(status=result['status'],case_id=args.case_id,finance=result.get('financial_audit'),
        error=result.get('error')),ensure_ascii=True))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
