# SPDX-License-Identifier: Apache-2.0
"""Read saved original48 data only. No App, transport, authority or pose mutation."""
from collections import Counter
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core import sim_fleet_navigation as nav

OUT = ROOT / 'outputs/robot-continuous-repair-20261021'
PROJECT = 'chat_mvh8rm7k_4dafa4c1'
REQUEST = '368cb27d-d4c8-420e-ac0e-2c87bc28fbc0'
OPERATION = '5fd611ca1b4f428d852e285e5ab72e97'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=sha256(path.read_bytes()).hexdigest())


def main():
    source = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/projects' / PROJECT / 'project.json'
    original = OUT / f'failed-ui-reproduction48-original-logs/13-{OPERATION}.json'
    result_file = OUT / 'ui-reproduction-48/result.json'
    project, operation, result = map(read, (source, original, result_file))
    scene = project['site_draft']['site']['scene']
    assert scene['revision'] == '37ba75c8f38889ac556d49af289203e42e3376a2c6822be8cf31ecf93459453e'
    event = next(e for e in operation['events'] if e['kind'] == 'motion_result' and e.get('command_id') == REQUEST)
    assert event['reason'] == 'NAVIGATION_NO_REACHABLE_APPROACH'
    pose = event['position_m']
    sample = next(s for s in reversed(result['samples']) if any(r.get('operation_id') == OPERATION for r in s['robots']))
    others = [(*r['pose']['position_m'][:2], .105) for r in sample['robots']
              if r.get('kind') == 'sim' and r.get('operation_id') != OPERATION]
    boxes, all_bounds, floors = [], {}, []
    for row in scene['objects']:
        assert row['shape']['type'] == 'box' and row['transform']['rotation_rpy_deg'] == [0, 0, 0]
        x, y, z = row['transform']['position_m']
        w, d, h = row['shape']['dimensions_m']
        bounds = [x-w/2, y-d/2, x+w/2, y+d/2]
        all_bounds[row['id']] = bounds
        if z+h/2 <= .08 and w > 1 and d > 1:
            floors.append(bounds)
        if z-h/2 <= .18 <= z+h/2 and z+h/2 > .08:
            gap = math.hypot(max(bounds[0]-pose[0], 0, pose[0]-bounds[2]),
                             max(bounds[1]-pose[1], 0, pose[1]-bounds[3]))
            boxes.append(dict(id=row['id'], bounds=bounds, start_distance_m=gap))
    floor = max(floors, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
    targets = []
    for call in project['site_draft']['plan']['calls']:
        if call['tool'] != 'place_furniture':
            continue
        args = call['arguments']
        members = [v for k, v in all_bounds.items() if k.startswith(args['id']+'_')]
        targets.append(dict(id=args['id'], kind=args['kind'], label=args['kind']+' '+args['id'],
                            bounds=[min(b[0] for b in members), min(b[1] for b in members),
                                    max(b[2] for b in members), max(b[3] for b in members)]))
    original_grid = nav.plan_bounded_grid
    trials = []
    def observe(*args, **kwargs):
        try:
            route = original_grid(*args, **kwargs)
        except nav.NoBoundedPath as exc:
            trials.append(dict(goal=list(args[1]), rejection=str(exc)))
            raise
        trials.append(dict(goal=list(args[1]), route=route))
        return route
    with patch.object(nav, 'plan_bounded_grid', observe):
        try:
            nav.approach_plan(pose, 'bed', targets, floor, [r['bounds'] for r in boxes], others)
        except ValueError as exc:
            replay_error = str(exc)
        else:
            raise AssertionError('Original rejection did not reproduce')
    nearest = min(boxes, key=lambda r: r['start_distance_m'])
    assert replay_error == event['reason']
    assert len(trials) == 20 and Counter(r.get('rejection') for r in trials) == {'START_OR_GOAL_BLOCKED': 20}
    assert .2075 < nearest['start_distance_m'] < .25
    # Preserve the exact source bytes as evidence before any later UI activity.
    preserved = OUT / 'navigation48-original-project.json'
    with preserved.open('xb') as handle:
        handle.write(source.read_bytes())
    value = dict(classification='OFFLINE_SAVED_COMPILED_GEOMETRY_RECONSTRUCTION_NOT_LIVE_USD_OR_PHYSICAL_PROOF',
                 operation_id=OPERATION, request_id=REQUEST, scene_revision=scene['revision'],
                 sources=[digest(source), digest(original), digest(result_file), digest(preserved)],
                 original_event_sequence=event['event_sequence'], original_position_m=pose,
                 floor_bounds=floor, other_robot_discs=others, nearest_static_box=nearest,
                 manual_existing_center_limit_m=.105+.1025, navigation_existing_clearance_m=.25,
                 reconstructed_rejection=replay_error, candidate_rejections=trials,
                 original_stop_clicked=False, original_stop_cancel_branch='NOT_REACHED',
                 limitations=['Actual original USD BBox cache was not retained; this reconstruction uses the exact saved zero-yaw compiled boxes, not new measured geometry.',
                              'Original FAIL is preserved. This is not a Stop PASS, route success, UI retest or permission to move.',
                              'No clearance, geometry, target, original pose or output policy was changed.'])
    output = OUT / 'navigation-failure48-review.json'
    with output.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
    print(json.dumps(dict(output=str(output), nearest=nearest, rejections=Counter(r['rejection'] for r in trials))))


if __name__ == '__main__':
    main()
