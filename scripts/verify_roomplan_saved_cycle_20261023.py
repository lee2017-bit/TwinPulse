# SPDX-License-Identifier: Apache-2.0
"""Check actual saved source, finalized UI download and both closed RoomPlan launches."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages' / name / 'src') for name in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider')]
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeHistory
from roomplan_runtime_copy_gate import check_runtime_copy


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    out, a = args.output_root.resolve(), args.attempt
    if len(a) != 2 or not a.isascii() or not a.isdecimal():
        raise ValueError('Two-digit attempt required')
    refs, issues = [], []

    def record(path):
        refs.append(dict(path=path.relative_to(out).as_posix(), sha256=sha256(path.read_bytes()).hexdigest()))
        return read(path)

    active = read(Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed/active-release.json')
    ai, sim, cold, final = [record(out / f'roomplan-{phase}-{a}/result.json') for phase in ('ai-edit', 'sim', 'cold', 'final-log')]
    if any(r.get('status') not in ('PASS', 'PASS_WITH_EXPECTED_STOP_REJECTION') for r in (ai, sim, cold, final)):
        issues.append('WHOLE_UI_NOT_PASS')
    origin, chain = ai['edit_origin'], ai['edit_chain']
    project = origin['project_id']
    if cold.get('selected_project') != project or sim.get('project_id') != project:
        issues.append('PROJECT_MISMATCH')
    runtime = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime'
    folder = runtime / 'projects' / project
    source = SiteDraftRecord.from_dict(read(folder / 'project.json')['site_draft'])
    history = SceneChangeHistory.from_dict(read(folder / 'project.scene-changes.json'), source, project)
    _, restored = history.replay(source)
    raw_history = read(folder / 'project.scene-changes.json')
    operations = raw_history['operations']
    if (restored.scene.environment != source.site.scene.environment or restored.scene.revision != chain['undone_revision']
            or len(operations) != 2 or [o['operation_id'] for o in operations] != chain['operation_ids']
            or [o['mode'] for o in operations] != ['change', 'undo']
            or [o['parent_revision'] for o in operations] != [chain['initial_revision'], chain['moved_revision']]
            or [o['result_revision'] for o in operations] != [chain['moved_revision'], chain['undone_revision']]):
        issues.append('ORIGINAL_GEOMETRY_OR_HISTORY_NOT_RESTORED')
    original = Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd')
    original_sha = sha256(original.read_bytes()).hexdigest()
    archives = list((folder / 'inputs').glob('*/environment-source.bin'))
    if (original_sha != origin['source_sha256'] or original_sha not in [sha256(p.read_bytes()).hexdigest() for p in archives]):
        issues.append('ORIGINAL_SOURCE_BYTES_NOT_PRESERVED')
    earlier = record(out / f'roomplan-sim-{a}' / sim['operation_download'])
    complete = record(out / f'roomplan-final-log-{a}' / final['operation_download'])
    manifest, events = complete.get('manifest', {}), complete.get('events', [])
    registered = sim['registered']
    if (any(complete.get(k) != registered.get(k) for k in ('operation_id', 'robot_id'))
            or complete.get('project_id') != project or manifest.get('source_twin_context') != registered.get('source_twin_context')
            or manifest.get('complete') is not True or manifest.get('completeness') != 'FINALIZED'
            or manifest.get('event_count') != len(events) or manifest.get('missing') != []
            or manifest.get('journal', {}).get('complete') is not True or manifest.get('journal', {}).get('saved') != len(events)
            or not earlier.get('events') or events[:len(earlier['events'])] != earlier['events']):
        issues.append('FINALIZED_ORIGINAL_EXPORT_OR_PREFIX_NOT_BOUND')
    for branch in ('fresh', 'cold'):
        start = record(out / f'start-roomplan-{branch}-{a}.json')
        launch = start['launch_id']
        cleanup = record(out / f'cleanup-roomplan-{branch}-{a}.json')
        copied = out / f'runtime-copiesfinal{a}' / launch
        receipt = record(copied / 'copy-receipt.json')
        issues += [branch + ':' + issue for issue in check_runtime_copy(copied, launch, receipt)]
        end = record(copied / 'cleanup-receipt.json')
        engine = record(copied / 'engine-result.json')
        joins = engine.get('viewport_phase_diagnostics', {}).get('join_status', {})
        if (cleanup.get('status') != 'PASS' or cleanup.get('launch_id') != launch or end.get('launch_id') != launch
                or end.get('exit_evidence_complete') is not True or end.get('owned_processes_stopped') is not True
                or engine.get('launch_id') != launch or engine.get('cleanup_status') != 'PRE_CLOSE_COMPLETE'
                or engine.get('cleanup_errors') != [] or any(joins.get(k) is not False for k in ('viewport_alive', 'fleet_alive', 'diagnostic_alive'))
                or joins.get('scan_worker', {}).get('worker_alive') is not False):
            issues.append(branch + ':INCOMPLETE_SHUTDOWN')
        for role in ('backend', 'engine'):
            observation = end.get('process_exit_observations', {}).get(role, {})
            if (observation.get('root_disposition') != 'EXITED_DURING_GRACE' or observation.get('return_code') != 0
                    or observation.get('evidence_complete') is not True or observation.get('errors') != []):
                issues.append(branch + ':' + role + ':ROOT_EXIT_UNCONFIRMED')
    value = dict(schema='roomplan-saved-cycle-1.0', status='FAIL' if issues else 'PASS', issues=issues,
                 release_id=active['release_id'], source_sha256=active['source_manifest_sha256'], project_id=project,
                 source_usd_sha256=original_sha, final_scene_revision=restored.scene.revision,
                 meshes=len(restored.scene.environment['meshes']), units_basis=restored.scene.environment['units_basis'],
                 finalized_events=len(events), evidence=refs,
                 limitation='Saved geometry and normal software cleanup, not physical sensing, scale, braking or driving.')
    with (out / f'roomplan-saved-cycle{a}.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
    print(json.dumps(dict(status=value['status'], issues=issues, project_id=project)))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
