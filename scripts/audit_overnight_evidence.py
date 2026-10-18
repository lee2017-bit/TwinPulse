# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only consistency audit of the Sep28 local rehearsal evidence, not acceptance.

No subprocess, network, robot, installation or runtime authority. Reports already
recorded outcomes; does not rerun tests or authenticate the evidence's authorship.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ISAAC = 'artifacts/room-goal-isaac-20260928-r3/result.json'
FAKE = 'artifacts/room-goal-browser-20260928-r2/result.json'
REGRESSION = 'artifacts/room-goal-regression-20260928-r1/manifest.json'
REQUIRED = {
    ISAAC: {'status': 'PASS', 'robot_connections': 0, 'provider_calls': 0,
            'physics_run': 'NOT_RUN', 'physical_validation': 'NOT_RUN',
            'alignment_verified': False, 'original_project_changed': False,
            'external_prim_preserved': True, 'robot_physics_enabled': False,
            'saved_replay_stage_reopened': True, 'tampered_replay_no_stage_mutation': True},
    FAKE: {'status': 'PASS', 'data': 'synthetic_transport_fixture', 'robot': 'NOT_RUN',
           'isaac': 'NOT_RUN', 'session_evidence': 'SYNTHETIC_ONLY_NOT_FLOOR_MOTION',
           'original_project_changed': False, 'all_four_directions_at_fake_output': True},
    REGRESSION: {'status': 'PASS', 'isaac': 'NOT_RUN'},
}
ESSENTIAL = {
    ISAAC: {'apps/twinpulse-web/src/BedroomTwin.tsx',
            'apps/twinpulse-web/src/BedroomGoalReview.tsx',
            'packages/twinpulse_core/src/twinpulse_core/room_goal.py',
            'packages/twinpulse_app/src/twinpulse_app/robot_geometry_evidence.py',
            'packages/twinpulse_app/src/twinpulse_app/bedroom_rehearsal.py',
            'extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py',
            'apps/twinpulse-web/dist/index.html'},
    FAKE: {'packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
           'packages/twinpulse_robot_safety/teleop_worker.py',
           'packages/twinpulse_core/src/twinpulse_core/ros_observations.py',
           'packages/twinpulse_core/src/twinpulse_core/navigation_binding.py',
           'packages/twinpulse_core/src/twinpulse_core/mission_contract.py',
           'packages/twinpulse_robot_safety/mission_runtime.py',
           'apps/twinpulse-web/dist/index.html'},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def collect(root):
    root = root.resolve()
    errors, reports, bound = [], {}, {}
    for name, expected in REQUIRED.items():
        try:
            raw = (root/name).read_bytes()
            report = json.loads(raw, object_pairs_hook=unique_object)
            if not isinstance(report, dict):
                raise ValueError('Report is not an object')
            reports[name] = hashlib.sha256(raw).hexdigest()
            for key, value in expected.items():
                actual = report.get(key)
                if type(actual) is not type(value) or actual != value:
                    errors.append(f'{name}: unexpected {key}')
            if name not in ESSENTIAL:
                continue
            hashes = report.get('source_and_build_sha256')
            if not isinstance(hashes, dict) or not ESSENTIAL[name] <= hashes.keys():
                raise ValueError('Missing source/build coverage')
            dist = {p.relative_to(root).as_posix() for p in (root/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
            recorded_dist = {p for p in hashes if p.startswith('apps/twinpulse-web/dist/')}
            if not dist or dist != recorded_dist:
                errors.append(f'{name}: dist inventory differs')
            for relative, wanted in hashes.items():
                path = PurePosixPath(relative)
                target = (root/relative).resolve()
                if path.is_absolute() or '..' in path.parts or not target.is_relative_to(root):
                    raise ValueError('Source path outside root')
                if not isinstance(wanted, str) or len(wanted) != 64 or any(c not in '0123456789abcdef' for c in wanted):
                    raise ValueError('Invalid digest')
                if relative in bound and bound[relative] != wanted:
                    errors.append(f'{relative}: rehearsals disagree')
                bound[relative] = wanted
                if not target.is_file() or digest(target) != wanted:
                    errors.append(f'{relative}: current content differs or missing')
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
    return {
        'schema': 'overnight-evidence-audit-1.0',
        'observed_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'FAIL' if errors else 'PASS',
        'meaning': 'RECORDED_EVIDENCE_AND_CURRENT_LISTED_FILES_CONSISTENT_ONLY',
        'report_sha256': reports, 'bound_file_count': len(bound),
        'source_and_build_sha256': bound, 'errors': sorted(set(errors)),
        'tests_rerun': False, 'robot_connections': 0, 'deployment': 'NOT_RUN',
        'physical_validation': 'NOT_RUN', 'autonomous_robot_ready': False,
        'limitations': ['Selected reported files, not complete repository provenance',
                       'Regression manifest reports PASS but has no source-hash binding',
                       'Artifact consistency is not independent authenticity or runtime acceptance'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional new JSON file; never overwrite')
    args = parser.parse_args()
    result = collect(ROOT)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text+'\n')
    print(text)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
