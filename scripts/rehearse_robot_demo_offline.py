# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One PC-only rehearsal of all four robot-demo development gates.

Runs an allowlisted set of existing no-device tests. It does not connect to a
robot or convert fake/stored evidence into physical permission.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.demo_contract import audit as audit_demo_operations
PACKAGE = ROOT / 'packages/twinpulse_robot_safety'
GROUPS = (
    ('1_connection_and_idle', ('-m', 'unittest',
        'tests.integration.test_robot_readiness',
        'tests.integration.test_robot_readiness_app',
        'tests.integration.test_robot_preparation',
        'packages.twinpulse_core.tests.test_ros_observations',
        'packages.twinpulse_robot_safety.tests.stationary_test', '-q')),
    ('2_lidar_lifecycle_and_record', ('-m', 'unittest',
        'packages.twinpulse_robot_safety.tests.test_lidar_capture',
        'tests.integration.test_lidar_recording_review', '-q')),
    ('3_coordinate_evidence', ('-m', 'unittest', 'discover',
        '-s', 'packages/twinpulse_core/tests', '-p', 'test_navigation_binding.py', '-q')),
    ('3_model_geometry_evidence', ('-m', 'unittest',
        'tests.integration.test_robot_geometry_evidence', '-q')),
    ('4_local_safety_and_mission', ('-m', 'unittest',
        'packages.twinpulse_robot_safety.tests.mission_test',
        'packages.twinpulse_core.tests.test_local_navigation',
        'tests.integration.test_physical_controller', '-q')),
)
COLLECTION_GROUPS = GROUPS[:2]
COLLECTION_CACHE_SCHEMA = 'robot-collection-pc-cache-1.0'
COLLECTION_CACHE_MAX_AGE_S = 12 * 60 * 60
COLLECTION_FILES = (
    'scripts/run_robot_readiness.py', 'scripts/rehearse_robot_demo_offline.py',
    'scripts/prepare_robot.py', 'scripts/robot_source_identity.py', 'scripts/check_robot_connection.py',
    'scripts/robot_health.py', 'scripts/turtlebot_probe.py',
    'scripts/review_lidar_recording.py', 'scripts/twinpulse_backend.py',
    'packages/twinpulse_app/src/twinpulse_app/robot_readiness.py',
    'packages/twinpulse_app/src/twinpulse_app/api.py',
    'tests/integration/test_robot_readiness.py',
    'tests/integration/test_robot_readiness_app.py',
    'tests/integration/test_robot_demo_offline_rehearsal.py',
    'tests/integration/test_robot_preparation.py',
    'tests/integration/test_lidar_recording_review.py',
    'packages/twinpulse_core/tests/test_ros_observations.py',
    'packages/twinpulse_robot_safety/tests/stationary_test.py',
    'packages/twinpulse_robot_safety/tests/test_lidar_capture.py',
)


def profile_gate(root=ROOT):
    profile_path = root / 'packages/twinpulse_robot_safety/profile.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    calibration = root / 'packages/twinpulse_robot_safety/navigation-calibration.json'
    return {'source_sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            'motion_enabled': profile.get('motion_enabled'),
            'autonomous_policy_present': 'autonomous_control_policy' in profile,
            'calibration_in_source': calibration.is_file(),
            'status': ('LOCKED_EXPECTED' if profile.get('motion_enabled') is False
                       and 'autonomous_control_policy' not in profile and not calibration.exists()
                       else 'REVIEW_REQUIRED'),
            'note': 'Never enable mission from offline tests or create calibration from a photo.'}


def run_groups(*, python=sys.executable, runner=subprocess.run, groups=GROUPS):
    results = {}
    source_paths = [str(ROOT / 'packages' / package / 'src') for package in
                    ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider')]
    environment = {**os.environ, 'PYTHONPATH': os.pathsep.join(
        [*source_paths, os.environ.get('PYTHONPATH', '')])}
    for name, args in groups:
        command = [python, *args]
        try:
            done = runner(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120, check=False)
            output = (done.stdout + done.stderr).decode('utf-8', errors='replace')
            count = re.search(r'Ran (\d+) tests?', output)
            skipped = re.search(r'skipped=(\d+)', output)
            results[name] = {'status': 'PASS_OFFLINE' if done.returncode == 0 and count else 'FAIL_OFFLINE',
                             'exit_code': done.returncode,
                             'test_count': int(count.group(1)) if count else None,
                             'skipped': int(skipped.group(1)) if skipped else 0,
                             'diagnostic_tail': output[-2500:] if done.returncode else ''}
        except subprocess.TimeoutExpired:
            results[name] = {'status': 'TIMEOUT_OFFLINE', 'test_count': None,
                             'diagnostic_tail': 'Local test exceeded 120 seconds; no robot action was attempted'}
        except OSError as exc:
            results[name] = {'status': 'TOOL_ERROR', 'test_count': None,
                             'diagnostic_tail': type(exc).__name__ + ': ' + str(exc)[:250]}
    return results


def assess_collection(groups, profile):
    """Only license stationary evidence collection, never full demo/motion readiness."""
    expected = {name for name, _ in COLLECTION_GROUPS}
    return {'schema_version': 'robot-collection-offline-preflight-1.0',
            'status': ('COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'
                       if set(groups) == expected
                       and all(item['status'] == 'PASS_OFFLINE' for item in groups.values())
                       and profile['status'] == 'LOCKED_EXPECTED' else 'COLLECTION_REVIEW_REQUIRED'),
            'motion_authorized': False, 'demo_ready': False,
            'hardware_validation': 'NOT_RUN', 'groups': groups, 'release_profile': profile,
            'not_checked_here': ['physical_stop', 'model_geometry', 'room_alignment',
                                 'autonomous_navigation']}


def collection_fingerprint(root=ROOT, *, python=sys.executable):
    """Bind a reusable PC result to exact collector, safety, tests and Python."""
    root = Path(root).resolve()
    paths = [root / name for name in COLLECTION_FILES]
    for subdir in ('packages/twinpulse_app/src', 'packages/twinpulse_core/src',
                   'packages/twinpulse_provider/src', 'packages/twinpulse_robot_safety'):
        folder = root / subdir
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError('COLLECTION_SOURCE_MISSING_OR_UNSAFE: ' + subdir)
        paths.extend(p for p in folder.rglob('*') if p.is_file()
                     and p.suffix in {'.py', '.json', '.cpp', '.hpp', '.txt', '.patch', '.md', '.sh'}
                     and not {'__pycache__', 'checks', 'build'}.intersection(p.relative_to(folder).parts))
    calibration = root / 'packages/twinpulse_robot_safety/navigation-calibration.json'
    digest = hashlib.sha256()
    digest.update(json.dumps({'python': str(Path(python).resolve()), 'version': sys.version,
                              'platform': sys.platform, 'calibration_present': calibration.exists()},
                             sort_keys=True).encode())
    for path in sorted(set(paths)):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('COLLECTION_SOURCE_MISSING_OR_UNSAFE: ' + str(path.relative_to(root)))
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def collection_cache_path(root=ROOT):
    return Path(root) / 'artifacts/robot-collection-pc-cache/current.json'


def cached_collection_preflight(root=ROOT, *, python=sys.executable, now=None):
    """Read a bounded passing PC receipt; never execute a test or contact a robot."""
    path = collection_cache_path(root)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        if (set(value) != {'schema_version', 'fingerprint', 'created_unix_s', 'report'}
                or value['schema_version'] != COLLECTION_CACHE_SCHEMA
                or type(value['created_unix_s']) not in (int, float)
                or not 0 <= (time.time() if now is None else now) - value['created_unix_s'] <= COLLECTION_CACHE_MAX_AGE_S
                or value['fingerprint'] != collection_fingerprint(root, python=python)):
            return None
        report = value['report']
        if (not isinstance(report, dict)
                or report.get('schema_version') != 'robot-collection-offline-preflight-1.0'
                or report.get('status') != 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'
                or report.get('motion_authorized') is not False or report.get('demo_ready') is not False
                or set(report.get('groups', {})) != {name for name, _ in COLLECTION_GROUPS}
                or any(group.get('status') != 'PASS_OFFLINE' for group in report['groups'].values())
                or report.get('release_profile', {}).get('status') != 'LOCKED_EXPECTED'):
            return None
        return {**report, 'pc_cache': 'MATCHED', 'pc_fingerprint': value['fingerprint']}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def prepare_collection_preflight(root=ROOT, *, python=sys.executable, runner=subprocess.run):
    fingerprint_before = collection_fingerprint(root, python=python)
    report = assess_collection(run_groups(python=python, runner=runner, groups=COLLECTION_GROUPS),
                               profile_gate(root))
    fingerprint_after = collection_fingerprint(root, python=python)
    if fingerprint_after != fingerprint_before:
        report = {**report, 'status': 'COLLECTION_REVIEW_REQUIRED',
                  'reason': 'PC source changed during preflight'}
    if report['status'] == 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED':
        path = collection_cache_path(root)
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError('COLLECTION_CACHE_PATH_UNSAFE')
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.json.part')
        if temp.is_symlink():
            raise ValueError('COLLECTION_CACHE_PATH_UNSAFE')
        temp.write_text(json.dumps({'schema_version': COLLECTION_CACHE_SCHEMA,
                                    'fingerprint': fingerprint_after,
                                    'created_unix_s': time.time(), 'report': report},
                                   ensure_ascii=False, allow_nan=False), encoding='utf-8')
        os.replace(temp, path)
    return {**report, 'pc_cache': 'NEWLY_CHECKED', 'pc_fingerprint': fingerprint_after}


def assess(groups, profile):
    return {'schema_version': 'robot-demo-offline-rehearsal-1.0',
            'local_python': str(Path(sys.executable).resolve()),
            'status': ('OFFLINE_CONTRACTS_PASS_PHYSICAL_LOCKED'
                       if set(groups) == {name for name, _ in GROUPS}
                       and all(item['status'] == 'PASS_OFFLINE' for item in groups.values())
                       and profile['status'] == 'LOCKED_EXPECTED' else 'OFFLINE_REVIEW_REQUIRED'),
            'motion_authorized': False, 'demo_ready': False,
            'robot_contact': 'NOT_RUN', 'hardware_validation': 'NOT_RUN',
            'groups': groups, 'release_profile': profile,
            'demo_operation_audit': audit_demo_operations(ROOT),
            'field_sequence': [
                '1. Explicit start: deploy reviewed source, idle board read, passive odom/TF/scan capture.',
                '2. Separate bounded ROS LiDAR lifecycle required; raw scan does not equal LaserScan or rotor-stop proof.',
                '3. Review actual same-boot frame/geometry evidence; no default room-to-odom transform.',
                '4. Only after physical safety gates and scoped approval: local autonomous mission; currently locked.'
            ]}


def save(report, output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                   allow_nan=False), encoding='utf-8')
    rows = ''.join('<tr><td>' + html.escape(name) + '</td><td>' +
                   html.escape(item['status']) + '</td><td>' +
                   html.escape(str(item['test_count'])) + '</td></tr>'
                   for name, item in report['groups'].items())
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline robot rehearsal</title>'
            '<style>body{font:18px Arial;max-width:960px;margin:32px auto;padding:16px;'
            'background:#101722;color:#e4eef8}table{width:100%;border-collapse:collapse}'
            'td,th{border:1px solid #526476;padding:12px;text-align:left}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1e2c40;padding:16px}</style>'
            '<h1>Robot demo · offline four-gate rehearsal</h1><p><strong>' +
            html.escape(report['status']) + '</strong> · Robot contact: NOT RUN · Demo ready: NO</p>'
            '<table><tr><th>Gate</th><th>Local result</th><th>Tests</th></tr>' + rows + '</table>'
            '<p>Live motion remains locked. A passing fake test never grants physical authority.</p><pre>' +
            html.escape(json.dumps(report, indent=2, ensure_ascii=False)) + '</pre></html>')
    path = output / 'report.html'
    path.write_text(page, encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-only', action='store_true',
                        help='PC-only collection contracts; cache passing result for later reuse')
    args = parser.parse_args()
    if args.collection_only:
        report = prepare_collection_preflight()
        print('Status: ' + report['status'])
        print('PC cache: ' + str(collection_cache_path()))
        print('Robot contact: NOT_RUN; motion and demo remain locked')
        return 0 if report['status'] == 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED' else 2
    groups = run_groups()
    report = assess(groups, profile_gate())
    output = ROOT / 'artifacts/robot-demo-offline' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                                                    + '-' + uuid.uuid4().hex[:8])
    page = save(report, output)
    print('Status: ' + report['status'])
    print('Report: ' + str(page))
    return 0 if report['status'] == 'OFFLINE_CONTRACTS_PASS_PHYSICAL_LOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
