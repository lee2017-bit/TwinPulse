# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Stored typed sensor feedback through the ordinary App and actual Isaac.

The positive transport is explicitly synthetic, decoded/mapped normally. Three
selected original robot recordings are copied unchanged and reviewed separately.
No model call, robot connection, live sensor, motor or physics Run is permitted.
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
from scripts.progressive_functional_scope import source_freeze
from twinpulse_app.process_manager import TwinPulseProcessManager
from twinpulse_app.project_store import ProjectRecord, ProjectStore
from twinpulse_app.scene_changes import SceneChangeStore
from twinpulse_core import InputArtifactStore
from twinpulse_core.simulation_goal import preview_review
from twinpulse_app.simulation_assets import burger_inventory
from tests.fixtures.progressive_sensor_saved import build_test_sensor_history

REAL_JOBS = ('4493be87ef7643ababb661b4a12f0180',
             'b6cf346718da44b99e7bffe6f7919bbf',
             '1a7f033af112437699ca67aef3438ecb')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--import-survey', action='store_true',
                        help='Use an explicitly synthetic completed survey through the ordinary import UI')
    parser.add_argument('--replan', action='store_true',
                        help='Verify ordinary SIM goal invalidation/replanning across sensor Apply and Undo; no Run')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    state = output / 'runtime'
    state.mkdir()
    history_root = output / 'stored-sensor-history'
    packet = build_test_sensor_history(history_root, project_id='default',
        real_history_root=ROOT, real_job_ids=REAL_JOBS)
    source = packet['source_record']
    project = ProjectStore(state / 'active_project.json')
    project.save(ProjectRecord('default', source.input_revision, site_draft=source))
    InputArtifactStore(project.input_root()).save(source.input_revision, ())
    originals = {str(path): sha for path, sha in packet['fingerprints'].items()}
    originals[str(project.path)] = digest(project.path)
    original_sensors = json.loads((ROOT / 'outputs/progressive-twin-overnight-20261012/'
                                  'saved-sensor-original-fingerprints.json').read_text(encoding='utf-8'))
    for row in original_sensors['rows']:
        originals[str(ROOT / row['path'])] = row['sha256']
    readiness = ROOT / 'artifacts/robot-readiness-app/current.json'
    originals[str(readiness)] = digest(readiness)
    visible_packet = {key: value for key, value in packet.items()
                      if key not in ('source_record', 'fingerprints')}
    visible_packet.update(source_revision=source.site.scene.revision,
                          input_revision=source.input_revision.digest,
                          physical_authority=False,
                          import_survey_requested=args.import_survey)
    if args.import_survey and not visible_packet.get('survey'):
        raise ValueError('EXPLICIT_SYNTHETIC_SURVEY_REQUIRED')
    if args.replan:
        illustrative=preview_review(source.site.scene,burger_inventory())['plan']
        visible_packet['sim_goal_revalidation']={key:illustrative[key] for key in ('start','goal')}
    with (output / 'fixture-provenance.json').open('x', encoding='utf-8') as stream:
        json.dump(visible_packet, stream, ensure_ascii=False, indent=2)
    frozen = source_freeze(ROOT)
    result = dict(status='FAIL', provider_calls=0, physical_robot_connections=0,
                  physics_run='NOT_RUN', positive_transport='SYNTHETIC_TRANSPORT',
                  actual_runtime='ordinary App/API/Chrome/local Isaac/common edit transaction',
                  survey_import_requested=args.import_survey,
                  sim_goal_revalidation_requested=args.replan,
                  original_recordings='Copied raw recordings; not live qualification',
                  source_revision=source.site.scene.revision,
                  original_project_sha256=originals[str(project.path)])
    manager = None

    def make_manager():
        return TwinPulseProcessManager(repo_root=ROOT, state_dir=state,
            python_executable=Path(sys.executable), isaac_python=Path('C:/isaacsim/python.bat'),
            browser_executable=None, headless=True, fixture_mode=True,
            session_history_root=history_root, ready_timeout_s=180.)

    def browser_run(phase):
        base, ticket = manager.product_bootstrap()
        environment = {**os.environ, 'TWINPULSE_VIEW_URL': base,
            'TWINPULSE_VIEW_BOOTSTRAP': ticket, 'TWINPULSE_VIEW_OUTPUT': str(output),
            'TWINPULSE_SENSOR_PACKET': json.dumps(visible_packet),
            'TWINPULSE_SENSOR_PHASE': phase}
        with (output / (phase + '-driver.log')).open('x', encoding='utf-8') as log:
            process = subprocess.run([str(args.node), str(ROOT / 'apps/twinpulse-web/e2e/'
                'progressive-sensor-journey.mjs')], cwd=ROOT / 'apps/twinpulse-web',
                env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=660,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        evidence = json.loads((output / (phase + '-browser.json')).read_text(encoding='utf-8'))
        result[phase] = evidence
        if process.returncode or evidence['status'] != 'PASS':
            raise RuntimeError('Stored sensor ' + phase + ' failed; original evidence retained')

    try:
        manager = make_manager()
        manager.start(open_browser=False)
        browser_run('sensor')
        if args.restart:
            manager.stop()
            result['first_engine'] = json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            manager = make_manager()
            manager.start(open_browser=False)
            browser_run('restart')
        result['status'] = 'PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error)[:500])
    finally:
        if manager:
            manager.stop()
            if manager.engine_result_file.is_file():
                result['engine'] = json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
            result['supervisor'] = json.loads(manager.supervisor_status_file.read_text(encoding='utf-8'))
        result['source_and_build_unchanged'] = source_freeze(ROOT) == frozen
        result['originals_unchanged'] = all(digest(path) == sha for path, sha in originals.items())
        result['new_provider_artifacts'] = len(list((state / 'ordinary-generation').glob('*.ledger.json')))
        if result.get('sensor', {}).get('final_revision'):
            store = SceneChangeStore(state / 'active_project.scene-changes.json',
                                     project_id='default', source=source)
            history = store.load()
            effective = history.effective(source)
            result['closed_storage'] = dict(revision=history.current_scene_revision,
                state_sha256=history.state_sha256(effective), entries=len(history.operations))
            if (history.current_scene_revision != result['sensor']['final_revision'] or
                history.state_sha256(effective) != result['sensor']['final_state_sha256']):
                result.update(status='FAIL', audit_error='CLOSED_SENSOR_STATE_MISMATCH')
        if (not result['source_and_build_unchanged'] or not result['originals_unchanged'] or
                result['new_provider_artifacts'] or any(result.get('supervisor', {}).get(key, {}).get('owned')
                                                       for key in ('backend', 'engine'))):
            result.update(status='FAIL', audit_error='SOURCE_FINANCE_OR_OWNER_CHANGED')
        with (output / 'result.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=result['status'], error=result.get('error'),
                         provider_calls=0, physical_robot_connections=0)))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
