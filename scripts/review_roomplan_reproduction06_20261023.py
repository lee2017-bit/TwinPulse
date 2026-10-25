# SPDX-License-Identifier: Apache-2.0
"""Preserve the accidentally selected older-scene failure, not a passing retest."""
from hashlib import sha256
import argparse
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-roomplan-ready-20261023'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', choices=('06', '07'), default='06')
    a = parser.parse_args().attempt
    project = 'chat_mvh1ol39_b80cd487' if a == '06' else 'chat_mvh8rm7k_4dafa4c1'
    revision = ('2344370ae58f16d394c6e4af2e4d9763c8e3e03a6abfffc9d407d3496e53c3d8'
                if a == '06' else '37ba75c8f38889ac556d49af289203e42e3376a2c6822be8cf31ecf93459453e')
    run = read(OUT / f'ui-reproduction-{a}/result.json')
    if run.get('status') != 'FAIL' or run.get('project') != project:
        raise ValueError('Original failed older-scene run required')
    row = next(r for r in run['samples'][-1]['robots'] if r['label'] == 'Alpha')
    if (row['command']['reason'] != 'NAVIGATION_NO_REACHABLE_APPROACH'
            or row['source_twin_context']['scene_revision'] != revision):
        raise ValueError('Exact failed command/context required')
    source = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/projects' / project / 'project.json'
    stored = read(source)
    scene = stored['site_draft']['site']['scene']
    # Preserve only scene data, not generation settings, credentials or auth owners.
    frozen = OUT / f'reproduction{a}-original-scene.json'
    write(frozen, scene)
    leg = next(o for o in scene['objects'] if o['id'] == 'chair1_leg_fl')
    t = leg['transform']; size = leg['shape']['dimensions_m']
    if leg['shape']['type'] != 'box' or t['rotation_rpy_deg'] != [0., 0., 0.]:
        raise ValueError('This explicit source-derived calculation needs an unrotated box')
    cx, cy, cz = t['position_m']; dx, dy, dz = size
    if not cz - dz/2 <= .18 <= cz + dz/2:
        raise ValueError('Primitive is not in the unchanged navigation slice')
    bounds = [cx-dx/2, cy-dy/2, cx+dx/2, cy+dy/2]
    start = row['pose']['position_m']
    gap = math.hypot(max(bounds[0]-start[0], 0., start[0]-bounds[2]),
                     max(bounds[1]-start[1], 0., start[1]-bounds[3]))
    if gap >= .25:
        raise ValueError('Claimed unchanged planner start blockage not reproduced')
    runtime_project = source.parent
    operation_refs = []
    for robot in run['samples'][-1]['robots']:
        if robot.get('kind') != 'sim' or not robot.get('operation_id'):
            continue
        path = runtime_project / 'robot-operations' / (robot['operation_id'] + '.json')
        raw = path.read_bytes()
        target = OUT / (f'reproduction{a}-' + robot['label'].lower() + '-final-operation.json')
        with target.open('xb') as stream:
            stream.write(raw)
        operation_refs.append(dict(path=target.name, sha256=sha256(raw).hexdigest()))
    historical = ROOT / 'outputs/robot-continuous-repair-20261021/physical-readiness-review57.json'
    old = read(historical)['reproduction_expected']
    write(OUT / f'reproduction{a}-diagnosis.json', dict(
        status='ORIGINAL_WHOLE_FAIL_PRESERVED_NOT_ACCEPTANCE',
        classification=('STALE_WRAPPER_DEFAULT_SELECTED_OTHER_OLDER_GEOMETRY' if a == '06'
                        else 'PERSISTED_POSE_ENTERED_PLANNER_ENVELOPE_DURING_MANUAL_STEPS'),
        run_sha256=sha256((OUT / f'ui-reproduction-{a}/result.json').read_bytes()).hexdigest(),
        original_project=project, original_revision=revision,
        original_command=row['command'], original_pose=start,
        stored_project_sha256=sha256(source.read_bytes()).hexdigest(),
        frozen_scene=dict(path=frozen.name, sha256=sha256(frozen.read_bytes()).hexdigest()),
        source_derived_primitive=leg, source_derived_slice_bounds=bounds,
        source_derived_start_gap_m=gap, existing_planner_clearance_m=.25,
        calculation_scope='Saved primitive/compiler contract, not an actual engine BBox observation',
        interpretation='Original start falls inside the unchanged planner envelope; rejected before cancellable travel. No timing-failure inference or relaxed guard.',
        whole_pass=False, completed_steps=sum(s['status']=='PASS' for s in run['steps']),
        remainder='NOT_RUN', cleanup='Separate Stop and normal exit, exact launch archived before next Start',
        operations=operation_refs,
        next_explicit_reproduction=old,
        next_scope=('Same latest historical failure geometry and unchanged full criteria; not a replacement PASS for this older-scene failure' if a == '06'
                    else 'Predeclare explicit visible SIM open-floor start preparation, Stop/applied/current-frame, then new unchanged whole journey; never resume this failed run'),
        historical_expected_sha256=sha256(historical.read_bytes()).hexdigest(),
        review_basis='Actual independent Astra read-only review and main source/raw-data recheck',
        device_actions=0,
    ))
    print(json.dumps(dict(status='PRESERVED', gap_m=gap, original_whole='FAIL', next=old)))


if __name__ == '__main__':
    main()
