# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Audited saved fresh draft, ordinary chat and actual Isaac; zero new inference.

This copies the project/input/edit closure, not model responses. Offline gateway
denies generation. A generic checked illustrative spawn supplies the explicit
SIM start; semantic targets still use the normal current-scene resolver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app import ApplicationService
from twinpulse_app.project_store import ProjectStore
from twinpulse_app.process_manager import TwinPulseProcessManager
from twinpulse_app.simulation_assets import burger_inventory
from twinpulse_core.simulation_goal import preview_review
from twinpulse_core.draft_refinement import public_refinement
from twinpulse_core.progressive_twin import checked_envelope, require_task_context
from twinpulse_app.dependency_patch import public_progressive, initial_state
from scripts.benchmark_protocol import source_freeze,file_sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--goal',required=True,help='Predeclared semantic target, e.g. Go to desk')
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--expect-task-blocked',action='store_true',help='Verify retained hazardous pending draft, rejected ordinary goal and closed restart; never Run')
    args=parser.parse_args()
    original=args.source.resolve();output=args.output.resolve()
    allowed=ROOT/'outputs/progressive-twin-overnight-20261012'
    if not original.is_relative_to(allowed) or not output.is_relative_to(allowed):
        raise ValueError('NAMED_OVERNIGHT_PATHS_ONLY')
    if not args.goal.startswith('Go to '):raise ValueError('PREDECLARED_SEMANTIC_GOAL_REQUIRED')
    original_result=json.loads((original/'result.json').read_text(encoding='utf-8'))
    if original_result.get('status')!='PASS' or original_result.get('browser',{}).get('status')!='PASS':
        raise ValueError('SAVED_CURRENT_DRAFT_NOT_ACCEPTED')
    output.mkdir(exist_ok=False);state=output/'runtime';state.mkdir()
    witnesses={}
    files=[original/'runtime/active_project.json',
           *list((original/'runtime').glob('active_project.scene-changes*.json')),
           *[p for p in (original/'runtime/inputs').rglob('*') if p.is_file()]]
    for source in files:
        witnesses[str(source)]=file_sha(source)
        relative=source.relative_to(original/'runtime');target=state/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        if file_sha(target)!=witnesses[str(source)]:raise ValueError('SAVED_COPY_CHANGED')
    app=ApplicationService(None,project_store=ProjectStore(state/'active_project.json'))
    history=app.scene_change_store().load();effective=history.effective(app.site_draft)
    progressive=effective.progressive(app.site_draft)
    if args.expect_task_blocked:
        checked_envelope(app.site_draft.progressive_twin,app.site_draft.plan.to_dict())
        if not any(row['hazard'] in {'entanglement','unknown'} for row in progressive['unresolved']):
            raise ValueError('RETAINED_HAZARDOUS_PENDING_REQUIRED')
        try:require_task_context(progressive)
        except ValueError as error:
            if not str(error).startswith('PROGRESSIVE_TASK_UNRESOLVED:'):raise
        else:raise ValueError('PENDING_TASK_NOT_BLOCKED')
        start=None
    else:
        start=preview_review(effective.site.scene,burger_inventory())['plan']['start']
    packet=dict(revision=history.current_scene_revision,state_sha256=history.state_sha256(effective),
        start=start,goal_text=args.goal,physical_authority=False,expect_task_blocked=args.expect_task_blocked,
        start_policy='NOT_AUTHORIZED_PENDING_HAZARD' if args.expect_task_blocked else 'CURRENT_SCENE_GENERIC_CHECKED_ILLUSTRATIVE_SPAWN')
    if progressive:
        packet['progressive_twin']=public_progressive(app.site_draft,effective)
    if app.site_draft.draft_refinement:
        original_state=initial_state(app.site_draft)
        packet['draft_refinement']=public_refinement(app.site_draft.draft_refinement,effective.site.plan,
            pending_context_current=effective.inventory==original_state.inventory and effective.placement==original_state.placement)
    frozen=source_freeze(ROOT)
    result=dict(status='FAIL',provider_calls=0,physical_robot_connections=0,
        source_result_status=original_result['status'],source_project_sha256=witnesses[str(original/'runtime/active_project.json')],
        acceptance_scope=('Saved fresh hazardous pending draft, ordinary task rejection/current render/closed restart; not motion or full geometry PASS'
            if args.expect_task_blocked else 'Saved fresh source, ordinary semantic SIM motion/Stop/reset/restart; not fresh inference or physical pose'),
        packet=packet)
    manager=None
    def make_manager():
        return TwinPulseProcessManager(repo_root=ROOT,state_dir=state,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,
            fixture_mode=False,offline_mode=True,ready_timeout_s=180.)
    def run_browser(phase):
        base,ticket=manager.product_bootstrap()
        env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,
            'TWINPULSE_VIEW_OUTPUT':str(output),'TWINPULSE_SAVED_SIM_PACKET':json.dumps(packet),
            'TWINPULSE_SAVED_SIM_PHASE':phase}
        with (output/(phase+'-driver.log')).open('x',encoding='utf-8') as log:
            proc=subprocess.run([str(args.node),str(ROOT/'apps/twinpulse-web/e2e/progressive-saved-sim-journey.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        evidence=json.loads((output/(phase+'-browser.json')).read_text(encoding='utf-8'))
        result[phase]=evidence
        if proc.returncode or evidence['status']!='PASS':raise RuntimeError('Saved SIM '+phase+' failed; original browser evidence retained')
    try:
        manager=make_manager();manager.start(open_browser=False);run_browser('blocked' if args.expect_task_blocked else 'motion')
        manager.stop();result['first_engine']=json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
        manager=make_manager();manager.start(open_browser=False);run_browser('restart')
        result['status']='PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:500])
    finally:
        if manager:
            manager.stop()
            if manager.engine_result_file.is_file():result['engine']=json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            result['supervisor']=json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))
        result['source_and_build_unchanged']=source_freeze(ROOT)==frozen
        result['originals_unchanged']=all(file_sha(path)==sha for path,sha in witnesses.items())
        result['new_provider_artifacts']=len(list((state/'ordinary-generation').glob('*.ledger.json')))
        restored=ApplicationService(None,project_store=ProjectStore(state/'active_project.json'))
        restored_history=restored.scene_change_store().load();restored_effective=restored_history.effective(restored.site_draft)
        result['closed_storage']=dict(revision=restored_history.current_scene_revision,
            state_sha256=restored_history.state_sha256(restored_effective))
        if packet.get('progressive_twin'):
            retained_progressive=public_progressive(restored.site_draft,restored_effective)
            result['closed_storage']['progressive_twin']=retained_progressive
            if retained_progressive!=packet['progressive_twin']:
                result.update(status='FAIL',audit_error='PENDING_INVENTORY_CHANGED_AFTER_RESTART')
        if packet.get('draft_refinement'):
            original_state=initial_state(restored.site_draft)
            retained=public_refinement(restored.site_draft.draft_refinement,restored_effective.site.plan,
                pending_context_current=restored_effective.inventory==original_state.inventory and restored_effective.placement==original_state.placement)
            result['closed_storage']['draft_refinement']=retained
            if retained!=packet['draft_refinement']:
                result.update(status='FAIL',audit_error='REFINEMENT_EVIDENCE_CHANGED_AFTER_SIM_OR_RESTART')
        if (not result['source_and_build_unchanged'] or not result['originals_unchanged']
                or result['new_provider_artifacts'] or result['closed_storage']['revision']!=packet['revision']
                or result['closed_storage']['state_sha256']!=packet['state_sha256']
                or any(result.get('supervisor',{}).get(k,{}).get('owned') for k in ('backend','engine'))):
            result.update(status='FAIL',audit_error='SOURCE_FINANCE_STORAGE_OR_OWNER_CHANGED')
        with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=result['status'],provider_calls=0,physical_robot_connections=0,error=result.get('error'))))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
