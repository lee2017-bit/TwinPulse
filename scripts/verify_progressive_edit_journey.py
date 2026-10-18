# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit partial-draft fixture through ordinary App/API and actual Isaac.

The fixture is NOT fresh photo recognition. Product code, the owned engine,
authenticated browser, dependency editing and closed storage replay are real.
No provider credential, physical robot, sensor or physics Run is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app', 'twinpulse_robot'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))
sys.path.insert(0, str(ROOT / 'packages/twinpulse_provider/tests'))

from twinpulse_app.process_manager import TwinPulseProcessManager
from twinpulse_app.project_store import ProjectRecord, ProjectStore
from twinpulse_app.scene_changes import SceneChangeStore
from twinpulse_core import InputArtifactStore
from tests.integration.test_dependency_scene_changes import partial_source
from twinpulse_app.dependency_patch import initial_state, public_progressive
from twinpulse_core.draft_refinement import public_refinement


def build_source(native_pending_refinement=False, full_geometry_refinement=False):
    """Compile an explicit scripted fixture; never inject a checked result/ACK."""
    if native_pending_refinement and full_geometry_refinement:
        raise ValueError('Choose exactly one explicit refinement fixture')
    if not native_pending_refinement and not full_geometry_refinement:
        return partial_source(), (), None
    from test_valid_refinement_draft import subset_result_case, result_case, record_for, synthetic_image
    request, result, _, transport = result_case() if full_geometry_refinement else subset_result_case()
    source = record_for(request, result)
    effective = initial_state(source)
    progressive = public_progressive(source, effective)
    refinement = public_refinement(source.draft_refinement, effective.plan.to_dict(), pending_context_current=True)
    if (source.schema_version != '2.3' or source.progressive_twin['schema_version'] != 'progressive-twin-1.0'
            or progressive['schema_version'] != 'progressive-twin-1.1'
            or refinement['quality_review']['status'] != 'needs_revision' or len(transport.bodies) != 5):
        raise ValueError('Explicit refinement fixture did not pass its normal typed compiler boundary')
    if full_geometry_refinement:
        if (refinement['schema_version'] != 'draft-refinement-1.0'
                or refinement['acceptance'] != 'GEOMETRY_VALID_REFINEMENT_INCOMPLETE'
                or progressive['unresolved'] or refinement['geometry_checks']['checks_complete'] is not True
                or len(refinement['geometry_checks']['checks']) != 8
                or any(row['status'] != 'passed' for row in refinement['geometry_checks']['checks'])):
            raise ValueError('Full geometry refinement fixture is not independently geometry-valid')
    elif (refinement['acceptance'] != 'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE'
            or progressive['unresolved'][0]['hazard'] != 'entanglement'
            or progressive['unresolved'][0]['bounds_z_m'][0] != 0.):
        raise ValueError('Explicit native pending hazard was not retained')
    packet = dict(provenance='EXPLICIT_SYNTHETIC_IMAGE_AND_SCRIPTED_PLANNER', scripted_responses=len(transport.bodies),
        external_provider_calls=0, live_photo_quality='NOT_RUN', physics_run='NOT_RUN',
        site_schema_version=source.schema_version, source_progressive_schema_version=source.progressive_twin['schema_version'],
        progressive_twin=progressive, draft_refinement=refinement,
        source_inventory=source.progressive_twin['inventory'])
    return source, (('fixture.jpg', synthetic_image()),), packet


def hashes():
    paths = [*list((ROOT / 'packages').glob('*/src/**/*.py')),
             *list((ROOT / 'extensions/twinpulse.extension/twinpulse').rglob('*.py')),
             *list((ROOT / 'apps/twinpulse-web/src').rglob('*')),
             *list((ROOT / 'apps/twinpulse-web/dist').rglob('*')),
             Path(__file__), ROOT / 'scripts/progressive_fixture_backend.py',
             ROOT / 'scripts/twinpulse_backend.py',ROOT / 'scripts/twinpulse_engine_host.py',
             ROOT / 'apps/twinpulse-web/e2e/progressive-edit-journey.mjs',
             ROOT / 'packages/twinpulse_provider/tests/test_valid_refinement_draft.py',
             ROOT / 'packages/twinpulse_provider/tests/test_scope_quality_loop.py',
             ROOT / 'packages/twinpulse_provider/tests/test_budgeted_generation.py',
             ROOT / 'tests/integration/test_dependency_scene_changes.py']
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--feedback',action='store_true',help='Explicit scripted proposal, not fresh LLM acceptance')
    parser.add_argument('--fault',choices=('commit','ack'),help='One isolated storage/ACK fault, actual engine recovery')
    parser.add_argument('--restart',action='store_true',help='Close owned backend/Isaac, reopen storage and build current Twin again')
    parser.add_argument('--slow-undo',action='store_true',help='Explicit four-second local pre-dispatch delay, unchanged control TTL')
    parser.add_argument('--native-pending-refinement', action='store_true',
        help='Explicit synthetic native support hazard plus incomplete quality; not fresh photo/physics acceptance')
    parser.add_argument('--full-geometry-refinement', action='store_true',
        help='Explicit synthetic geometry-valid refinement1.0; not fresh photo/physics acceptance')
    args = parser.parse_args()
    if args.slow_undo and not args.feedback:parser.error('--slow-undo requires --feedback')
    if ((args.native_pending_refinement or args.full_geometry_refinement) and (args.feedback or args.fault)
            or args.native_pending_refinement and args.full_geometry_refinement):
        parser.error('Choose one refinement fixture without feedback/fault injection')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state = output / 'runtime'
    state.mkdir()
    source, images, native_packet = build_source(args.native_pending_refinement, args.full_geometry_refinement)
    project = ProjectStore(state / 'active_project.json')
    project.save(ProjectRecord('default', source.input_revision, site_draft=source))
    InputArtifactStore(project.input_root()).save(source.input_revision, images)
    original_project = project.path.read_bytes()
    before = hashes()
    result = dict(status='FAIL', fixture='explicit synthetic partial support graph',
                  actual_runtime='ordinary App/API/browser/local Isaac', provider_calls=0,
                  physical_robot_connections=0, live_photo_quality='NOT_RUN', physics_run='NOT_RUN',
                  source_plan_sha256=source.plan_sha256, source_sha256=hashlib.sha256(original_project).hexdigest())
    if native_packet:
        result.update(fixture='explicit synthetic geometry-valid incomplete visual refinement' if args.full_geometry_refinement else
            'explicit synthetic native support hazard and incomplete quality')
        result['full_refinement_fixture' if args.full_geometry_refinement else 'native_fixture'] = native_packet
    result['controlled_slow_undo_s']=4 if args.slow_undo else 0
    manager = None
    class FixtureManager(TwinPulseProcessManager):
        def _backend_command(self):
            command=super()._backend_command()
            if args.feedback or args.fault:command[1]=str(ROOT/'scripts/progressive_fixture_backend.py')
            return command
    def make_manager():
        return FixtureManager(repo_root=ROOT,state_dir=state,python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'),browser_executable=None,headless=True,
            fixture_mode=True,ready_timeout_s=180.)
    def browser_run(manager,phase='edit'):
        base,ticket=manager.product_bootstrap()
        env={**os.environ,'TWINPULSE_VIEW_URL':base,'TWINPULSE_VIEW_BOOTSTRAP':ticket,
            'TWINPULSE_VIEW_OUTPUT':str(output),'TWINPULSE_EDIT_PHASE':phase,
            'TWINPULSE_EDIT_FEEDBACK':'1' if args.feedback else '0',
            'TWINPULSE_EDIT_FAULT':args.fault or '',
            'TWINPULSE_EDIT_SOURCE_JSON':json.dumps(dict(scene_revision=source.site.scene.revision,
                input_revision=source.input_revision.digest,
                native_pending_refinement=None if args.full_geometry_refinement else native_packet,
                full_geometry_refinement=native_packet if args.full_geometry_refinement else None))}
        with (output/('browser-driver.log' if phase=='edit' else 'restart-driver.log')).open('x',encoding='utf-8') as log:
            completed=subprocess.run([str(args.node),str(ROOT/'apps/twinpulse-web/e2e/progressive-edit-journey.mjs')],
                cwd=ROOT/'apps/twinpulse-web',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=480,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        evidence=json.loads((output/('browser.json' if phase=='edit' else 'restart-browser.json')).read_text(encoding='utf-8'))
        if completed.returncode or evidence['status']!='PASS':
            raise RuntimeError('Actual progressive '+phase+' journey failed; first failure is preserved')
        return evidence
    try:
        if args.feedback:os.environ['TWINPULSE_EXPLICIT_FEEDBACK_EVIDENCE']=str(output/'explicit-feedback.jsonl')
        if args.slow_undo:os.environ['TWINPULSE_EXPLICIT_SLOW_UNDO_S']='4'
        if args.fault:os.environ['TWINPULSE_EXPLICIT_EDIT_FAULT']=args.fault
        manager=make_manager()
        manager.start(open_browser=False)
        try:result['browser']=browser_run(manager)
        except Exception:
            if (output/'browser.json').is_file():result['browser']=json.loads((output/'browser.json').read_text(encoding='utf-8'))
            raise
        if args.feedback:
            calls=[json.loads(line) for line in (output/'explicit-feedback.jsonl').read_text(encoding='utf-8').splitlines()]
            if len(calls)!=4 or any(call['external_api'] or call['context']['schema_version']!='scene-edit-context-1.2'
                    or not call['context']['current_state_sha256'] or not call['context']['unresolved'] for call in calls):
                raise RuntimeError('Scripted context did not retain current unresolved/state identities')
            result['scripted_feedback']={ 'calls':len(calls),'external_api_calls':0,
                'context_sha256':[call['context']['context_sha256'] for call in calls],
                'state_sha256':[call['context']['current_state_sha256'] for call in calls],
                'unresolved_preserved':True,'not_fresh_llm_quality':True}
        if args.restart:
            manager.stop()
            result['first_engine']=json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            os.environ.pop('TWINPULSE_EXPLICIT_EDIT_FAULT',None)
            manager=make_manager();manager.start(open_browser=False)
            result['closed_runtime_restart']=browser_run(manager,'restart')
            if result['closed_runtime_restart']['final_revision']!=result['browser']['final_revision']:
                raise RuntimeError('Restart displayed a different saved revision')
            if native_packet and any(result['closed_runtime_restart'][key] != result['browser'][key]
                    for key in ('final_state_sha256', 'final_progressive', 'final_refinement')):
                raise RuntimeError('Restart changed exact native pending/refinement metadata')
        result['status'] = 'PASS'
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc)[:500])
    finally:
        if manager:
            manager.stop()
            if manager.engine_result_file.is_file():
                result['engine'] = json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
        result['source_unchanged'] = project.path.read_bytes() == original_project
        after = hashes()
        result['source_and_build_unchanged'] = before == after
        result['source_and_build_sha256'] = before
        if not result['source_unchanged'] or not result['source_and_build_unchanged']:
            result['status'] = 'FAIL'
            result['audit_error'] = 'Source project or frozen product/build changed'
        # Closed-process read, not an inferred promise that restart execution succeeded.
        if result.get('browser', {}).get('final_revision'):
            try:
                path = state / result['browser']['history_path']
                history = SceneChangeStore(path, project_id='default', source=source).load()
                effective = history.effective(source)
                result['closed_storage_replay'] = dict(scene_revision=history.current_scene_revision,
                    state_sha256=history.state_sha256(effective), change_count=len(history.operations),
                    matches_browser=history.current_scene_revision == result['browser']['final_revision'] and
                        history.state_sha256(effective)==result['browser']['final_state_sha256'])
                if not result['closed_storage_replay']['matches_browser']:
                    result['status'] = 'FAIL'
                if native_packet:
                    original = initial_state(source)
                    same_pending = effective.inventory == original.inventory and effective.placement == original.placement
                    progressive = public_progressive(source, effective)
                    refinement = public_refinement(source.draft_refinement,
                        effective.plan.to_dict(), pending_context_current=same_pending)
                    stored_source = ProjectStore(project.path).load().site_draft
                    exact = (stored_source.to_dict() == source.to_dict() and same_pending
                        and effective.plan == source.plan and len(history.operations) == (2 if args.full_geometry_refinement else 4)
                        and progressive == native_packet['progressive_twin'] == result['browser'].get('final_progressive')
                        and refinement == native_packet['draft_refinement'] == result['browser'].get('final_refinement'))
                    result['closed_storage_replay']['full_geometry_refinement_exact' if args.full_geometry_refinement else
                        'native_pending_refinement_exact'] = exact
                    if not exact:result['status'] = 'FAIL'
            except Exception as exc:
                result['status']='FAIL'
                result['closed_storage_replay'] = dict(status='FAIL',error_type=type(exc).__name__,error=str(exc)[:500])
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        os.environ.pop('TWINPULSE_EXPLICIT_FEEDBACK_EVIDENCE',None)
        os.environ.pop('TWINPULSE_EXPLICIT_EDIT_FAULT',None)
        os.environ.pop('TWINPULSE_EXPLICIT_SLOW_UNDO_S',None)
    print(json.dumps({k: result[k] for k in ('status', 'provider_calls', 'physical_robot_connections')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
