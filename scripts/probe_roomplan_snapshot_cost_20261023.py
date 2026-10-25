# SPDX-License-Identifier: Apache-2.0
"""No-device supplementary replay of saved RoomPlan metadata, not installed acceptance."""
import argparse
import cProfile
from hashlib import sha256
import json
import os
from pathlib import Path
import pstats
import re
import statistics
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'packages/twinpulse_robot_safety/tests'),
                *[str(ROOT / 'packages' / name / 'src') for name in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider')]]
from tests.integration.test_scene_state_metadata import SceneStateMetadataTests
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.scene_changes import SceneChangeHistory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--project', default='chat_mvke7dtp_9c78c5d7')
    parser.add_argument('--cold',action='store_true',help='Measure first restore summary too; no resumed history or primed memo.')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('New evidence required')
    if not re.fullmatch(r'chat_[a-zA-Z0-9_]+', args.project):
        raise ValueError('Exact saved chat identity required')
    folder = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/projects' / args.project
    original_paths = [folder / name for name in ('project.json', 'project.scene-changes.json', 'project.scene-edit-transaction.json')]
    raw = [p.read_bytes() for p in original_paths]
    records = [json.loads(value.decode('utf-8-sig')) for value in raw]
    source = SiteDraftRecord.from_dict(records[0]['site_draft'])
    fixture = SceneStateMetadataTests()
    fixture.setUp()
    profiler = cProfile.Profile()
    try:
        archived = folder / 'inputs' / source.input_revision.digest / 'environment-source.bin'
        isolated = fixture.root / 'inputs' / source.input_revision.digest / 'environment-source.bin'
        isolated.parent.mkdir(parents=True)
        shutil.copyfile(archived, isolated)
        if args.cold:
            from twinpulse_app import ProjectStore
            from twinpulse_app.project_store import ProjectRecord
            from twinpulse_core import InputArtifactStore
            store=ProjectStore.for_project(fixture.root,'default')
            InputArtifactStore(store.input_root()).save(source.input_revision,())
            store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            workflow=fixture.product(fixture.root)
        else:
            workflow = fixture.saved_product(source, fixture.root)
        # The isolated test store has a distinct project identity. This derived
        # replay changes only that container identity; original bytes stay put.
        if not args.cold:
            history = {**records[1], 'project_id': 'default'}
            workflow._scene_changes = SceneChangeHistory.from_dict(history, source, 'default')
            workflow._site_artifact = workflow._register_scene_change(source, workflow._scene_changes)
            workflow.scene_edit_transaction.value = records[2]
            workflow.snapshot()  # Populate the existing validated summary memo.
        costs = []
        profiler.enable()
        for _ in range(5):
            began = time.perf_counter()
            workflow.snapshot()
            costs.append((time.perf_counter() - began) * 1000)
        profiler.disable()
        stats = pstats.Stats(profiler)
        hot = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:25]
        result = dict(classification='SUPPLEMENTARY_ISOLATED_METADATA_REPLAY_NOT_INSTALLED_UI_OR_CAUSAL_PROOF',
                      includes_cold_first_summary=args.cold,
                      source_files={str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in
                                    [ROOT / 'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
                                     ROOT / 'packages/twinpulse_app/src/twinpulse_app/scene_edit_transaction.py']},
                      original_files=[dict(name=p.name, bytes=len(value), sha256=sha256(value).hexdigest()) for p, value in zip(original_paths, raw)],
                      original_unchanged=all(p.read_bytes() == value for p, value in zip(original_paths, raw)),
                      snapshot_ms=costs, mean_ms=statistics.mean(costs), max_ms=max(costs),
                      hot=[dict(file=key[0], line=key[1], function=key[2], calls=value[1], own_s=value[2], cumulative_s=value[3]) for key, value in hot])
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps({key: result[key] for key in ('snapshot_ms', 'mean_ms', 'max_ms', 'original_unchanged')}))
    finally:
        profiler.disable()
        fixture.tearDown()


if __name__ == '__main__':
    main()
