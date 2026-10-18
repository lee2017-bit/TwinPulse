# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen local source for the existing field suite, never a motion approval.

No SSH, ROS, device access, credential reads, installation or calibration
generation. The prepare client consumes these exact archive bytes. Local
contracts and runner fingerprints expire independently of physical evidence.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

from robot_source_identity import bundle_files
from rehearse_robot_demo_offline import collection_fingerprint, COLLECTION_CACHE_MAX_AGE_S

SCHEMA = 'robot-field-candidate-1.0'
RUNNERS = ('scripts/run_robot_field_suite.py', 'scripts/robot_field_candidate.py',
           'scripts/prepare_coin_time_candidate.py',
           'scripts/build_coin_target.py', 'tests/integration/test_coin_target_build.py',
           'scripts/run_supervised_odom_qualification.py', 'scripts/run_ros_scan_client.py',
           'tests/integration/test_robot_field_candidate.py')
MAX_ARCHIVE = 32 * 1024 * 1024
SENSOR_SOURCE = 'artifacts/coin-d4-ad1-time-candidate-20261006-r2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(members):
    return sha(json.dumps({name: sha(data) for name, data in members.items()},
                          sort_keys=True).encode())


def safe_path(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('FIELD_CANDIDATE_SYMLINK')
    return path


def runner_hashes(root):
    return {name: sha(safe_path(root / name).read_bytes()) for name in RUNNERS}


def source_members(root):
    # The identity helper is shared with runtime.prepare; reject indirect inputs
    # before it reads a package file. No identity/key/host record enters this set.
    package = safe_path(root / 'packages/twinpulse_robot_safety')
    for path in package.rglob('*'):
        if path.is_symlink():
            raise ValueError('FIELD_CANDIDATE_SOURCE_SYMLINK')
    safe_path(root / 'scripts/robot_health.py')
    core = safe_path(root / 'packages/twinpulse_core/src/twinpulse_core')
    for path in core.glob('*.py'):
        safe_path(path)
    return bundle_files(root)


def pc_checks():
    """Presence only: never open identity or known_hosts contents."""
    return {'ssh_executable': bool(shutil.which('ssh.exe' if sys.platform == 'win32' else 'ssh')),
            'scp_executable': bool(shutil.which('scp.exe' if sys.platform == 'win32' else 'scp')),
            'existing_identity': (Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation').is_file(),
            'existing_host_record': (Path.home()/'.ssh/known_hosts').is_file()}


def autonomous_gaps(root, members):
    profile = json.loads(members['profile.json'])
    gaps = []
    if profile.get('autonomous_control_policy') != 'qualified_session_reviewed_planar_frames_v1':
        gaps.append('AUTONOMOUS_PROFILE_NOT_REVIEWED')
    for name in ('navigation-calibration.json', 'adaptive-qualification.json',
                 'adaptive-sensor-evidence.json'):
        if name not in members:
            gaps.append('MISSING_' + name)
    # Presence alone is never an admission receipt. The existing App and local
    # worker still validate reviewed bytes, room revision and current boot.
    return gaps


def sensor_target(root, output=None):
    """Preserve existing reviewed patch source, not a compiled/deployed driver."""
    source = safe_path(root/SENSOR_SOURCE)
    receipt = source/'twinpulse-candidate.json'
    if not receipt.is_file():
        return {'status': 'CORRECTED_DRIVER_SOURCE_MISSING', 'target_build': 'NOT_RUN'}
    review = json.loads(safe_path(receipt).read_bytes())
    if (review.get('upstream_commit') != '8277b288902f28b37948b42e1bb80ba59afbba60'
            or review.get('schema') != 'coin-timing-candidate-1.0'
            or review.get('deployed') is not False or review.get('motion_authorized') is not False):
        raise ValueError('SENSOR_TARGET_REVIEW_CONTEXT')
    patches = review.get('patches')
    if not isinstance(patches, dict) or set(patches) != {
            'coin-d4-parser-bounds-20260926.patch', 'coin-d4-lifecycle-20260930.patch',
            'coin-d4-stop-order-20260930.patch', 'coin-d4-time-order-20261004.patch',
            'coin-d4-humble-time-api-20261006.patch'}:
        raise ValueError('SENSOR_TARGET_PATCH_SET')
    for name, digest in patches.items():
        if sha(safe_path(root/'docs/verification'/name).read_bytes()) != digest:
            raise ValueError('SENSOR_TARGET_PATCH_CHANGED')
    members = {}
    for path in source.rglob('*'):
        safe_path(path)
        if path.is_file() and '.github' not in path.relative_to(source).parts:
            if path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('SENSOR_TARGET_MEMBER_BUDGET')
            members[path.relative_to(source).as_posix()] = path.read_bytes()
    if len(members) > 512 or sum(map(len, members.values())) > MAX_ARCHIVE:
        raise ValueError('SENSOR_TARGET_BUDGET')
    required = {'CMakeLists.txt', 'package.xml', 'offline_tests/scan_clock_test.cpp',
                'include/coin_d4_driver/scan_clock_contract.hpp'}
    if not required.issubset(members):
        raise ValueError('SENSOR_TARGET_SOURCE_INCOMPLETE')
    # Upstream CI files are excluded from the target archive; all included
    # source bytes must match the post-application receipt, not just markers.
    reviewed = review.get('source_files')
    if not isinstance(reviewed, dict):
        raise ValueError('SENSOR_TARGET_SOURCE_RECEIPT_MISSING')
    included = {name:digest for name,digest in reviewed.items() if '.github' not in name.split('/')}
    if (review.get('patch_application') != 'ISOLATED_NON_REPOSITORY_CHANGED_FILES_AND_REVERSE_CHECK'
            or included != {name:sha(data) for name,data in members.items() if name != 'twinpulse-candidate.json'}):
        raise ValueError('SENSOR_TARGET_SOURCE_RECEIPT_CHANGED')
    original_harness=members['offline_tests/scan_clock_test.cpp']
    current_harness=safe_path(root/'packages/twinpulse_robot_safety/tests/scan_clock_test.cpp').read_bytes()
    harness_provenance=None
    if original_harness != current_harness:
        prefix=(b'// SPDX-FileCopyrightText: 2026 Jaewon Lee\n'
                b'// SPDX-License-Identifier: Apache-2.0\n'
                b'// Source: https://github.com/lee2017-bit/TwinPulse\n')
        old_sha='012e83cee1d6549b4092f0c9ffe2b8b1c7b8b76c033beaf1ca4c43696209ce2b'
        new_sha='d0d2ee81a8f5b22565e9030cb798b08d8e2142d06672a8d893454aceefda0724'
        if sha(original_harness)!=old_sha or sha(current_harness)!=new_sha or prefix+original_harness!=current_harness:
            raise ValueError('SENSOR_TARGET_HARNESS_CHANGED')
        harness_provenance=dict(kind='EXACT_LICENSE_SOURCE_PREFIX_ONLY',original_sha256=old_sha,
            current_sha256=new_sha,prefix_bytes=len(prefix),compiled_source_identity_unchanged=True)
    if output is not None:
        with (output/'sensor-target.tar').open('xb') as stream, tarfile.open(fileobj=stream, mode='w') as tar:
            for name, data in sorted(members.items()):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
                tar.addfile(entry, io.BytesIO(data))
    compiled = None
    pointer = root/'artifacts/coin-target-build/compiled-source.json'
    if pointer.is_file():
        build = json.loads(safe_path(pointer).read_bytes())
        if build.get('source_sha256') == identity(members):
            from build_coin_target import verify_export
            target = safe_path(root/build['target'])
            if (build.get('schema') != 'coin-compiled-source-1.0'
                    or build.get('activation_authorized') is not False
                    or not target.is_relative_to(root/'artifacts/coin-target-build')
                    or sha((target/'report.json').read_bytes()) != build['report_sha256']):
                raise ValueError('SENSOR_TARGET_BUILD_RECEIPT')
            result = verify_export(target, build['archive_sha256'])
            if (result['status'] != 'TARGET_BUILD_PASS_NOT_ACTIVATED'
                    or result['source_files'] != included):
                raise ValueError('SENSOR_TARGET_BUILD_SOURCE_MISMATCH')
            compiled = {'receipt':pointer.relative_to(root).as_posix(),
                        'target':build['target'],'artifacts':result['artifacts']}
    return {'status': ('CORRECTED_DRIVER_SOURCE_FROZEN_BUILD_VERIFIED_NOT_ACTIVATED' if compiled
                       else 'CORRECTED_DRIVER_SOURCE_FROZEN_NOT_BUILT'),
            'target_build': 'PASS_NOT_ACTIVATED' if compiled else 'NOT_RUN',
            'compiled_source': compiled,
            'harness_provenance_compatibility':harness_provenance,
            'source_sha256': identity(members), 'members': len(members), 'patches': patches,
            'timing_basis': 'HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY',
            'existing_owned_driver': 'OLDER_DIGEST_PINNED_BINARY_UNCHANGED',
            'build_requirements': ['Linux ARM64', 'g++', 'cmake', 'ROS Humble ament/rclcpp libraries'],
            'build_plan_not_executed': [
                ['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', 'include',
                 'offline_tests/scan_clock_test.cpp', '-o', 'scan_clock_test'],
                ['./scan_clock_test'],
                ['cmake', '-S', '.', '-B', 'build', '-DCMAKE_PREFIX_PATH=/opt/ros/humble'],
                ['cmake', '--build', 'build', '--target', 'single_coin_d4_node', '--parallel', '2']],
            'deployment_authorized': False}


def prepare(root, *, preflight, output=None, runner=subprocess.run, presence=pc_checks):
    root = Path(root).resolve()
    members = source_members(root)
    fingerprint = collection_fingerprint(root)
    runners = runner_hashes(root)
    out = safe_path(output or root/'artifacts/robot-field-candidates'/uuid.uuid4().hex)
    if not out.is_relative_to(root/'artifacts/robot-field-candidates'):
        raise ValueError('FIELD_CANDIDATE_OUTPUT_ROOT')
    out.mkdir(parents=True, exist_ok=False)
    sensor = sensor_target(root, out)
    checks = {}
    try:
        for name, data in members.items():
            if name.endswith('.py'):
                compile(data, name, 'exec')
            elif name.endswith('.json'):
                json.loads(data)
        checks['syntax'] = {'status': 'PASS_LOCAL_ONLY'}
    except (SyntaxError, ValueError, TypeError) as exc:
        checks['syntax'] = {'status': 'FAILED', 'error_type': type(exc).__name__}
    archive = out/'source.tar'
    with archive.open('xb') as stream, tarfile.open(fileobj=stream, mode='w') as tar:
        for name, data in sorted(members.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
            tar.addfile(entry, io.BytesIO(data))
    # Device-free import of actual bundled modules, outside the checkout. ROS
    # and serial imports must remain lazy; no fake module replaces dependencies.
    stage = out/'import-check'
    stage.mkdir()
    for name, data in members.items():
        if name.endswith('.py'):
            path = stage/name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
    code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'import mission_runtime,teleop_ros,observed_runtime;'
            'from twinpulse_core.navigation_binding import PlanarBinding;'
            'assert mission_runtime.PlanarBinding is PlanarBinding;'
            'assert "rclpy" not in sys.modules;assert "serial" not in sys.modules;'
            'print("FIELD_CANDIDATE_IMPORT_PASS")')
    try:
        done = runner([sys.executable, '-I', '-B', '-c', code, str(stage)], cwd=stage,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, check=False)
        checks['isolated_import'] = {'status': 'PASS_LOCAL_ONLY' if done.returncode == 0
            and b'FIELD_CANDIDATE_IMPORT_PASS' in done.stdout else 'FAILED',
            'exit_code': done.returncode}
        (out/'import.stdout').write_bytes(done.stdout[:32768])
        (out/'import.stderr').write_bytes(done.stderr[:32768])
    except (OSError, subprocess.TimeoutExpired) as exc:
        checks['isolated_import'] = {'status': 'FAILED', 'error_type': type(exc).__name__}
    try:
        contract = preflight()
    except (OSError, ValueError, RuntimeError) as exc:
        contract = {'status': 'FAILED', 'error_type': type(exc).__name__}
    checks['contracts'] = {'status': 'PASS_LOCAL_ONLY' if
        contract.get('status') == 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED' and
        contract.get('field_suite_contracts', {}).get('status') == 'PASS' else 'FAILED'}
    with (out/'preflight.json').open('x', encoding='utf-8') as stream:
        json.dump(contract, stream, allow_nan=False, indent=2)
    unchanged = (identity(source_members(root)) == identity(members) and
                 collection_fingerprint(root) == fingerprint and runner_hashes(root) == runners
                 and sensor_target(root) == sensor)
    checks['unchanged_inputs'] = {'status': 'PASS_LOCAL_ONLY' if unchanged else 'FAILED'}
    pc = presence()
    passed = all(value['status'] == 'PASS_LOCAL_ONLY' for value in checks.values())
    manifest = {'schema': SCHEMA, 'source_id': identity(members),
                'archive_sha256': sha(archive.read_bytes()),
                'files': {name: sha(data) for name, data in members.items()},
                'collection_fingerprint': fingerprint, 'runner_sha256': runners,
                'preflight_sha256': sha((out/'preflight.json').read_bytes()),
                'sensor_target': sensor,
                'sensor_archive_sha256': (sha((out/'sensor-target.tar').read_bytes())
                                           if (out/'sensor-target.tar').is_file() else None),
                'created_unix_s': time.time(), 'contracts_passed': passed,
                'motion_authorized': False, 'robot_contacted': False}
    with (out/'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, allow_nan=False, indent=2, sort_keys=True)
    profile = json.loads(members['profile.json'])
    report = {'schema': SCHEMA, 'status': 'FIELD_COLLECTION_CANDIDATE_PREPARED' if passed
              and all(pc.values()) else 'LOCAL_PREPARATION_NEEDS_ATTENTION',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'checks': checks,
              'pc_presence': pc, 'source_id': manifest['source_id'], 'members': len(members),
              'manifest': str(out/'manifest.json'), 'autonomous_gaps': autonomous_gaps(root, members),
              'sensor_target': sensor,
              'blocking_autonomous_preparation': ([('CORRECTED_DRIVER_BUILT_NOT_ACTIVATED'
                  if sensor.get('target_build') == 'PASS_NOT_ACTIVATED' else 'CORRECTED_DRIVER_TARGET_BUILD_NOT_RUN'),
                  'ACQUISITION_TIMING_UNVERIFIED', 'MEASURED_EXTRINSIC_AND_FOOTPRINT_UNVERIFIED',
                  'REVIEWED_RELEASE_NOT_REGISTERED']),
              'remote_requirements': {'architecture': profile['architecture'], 'ros': profile['ros_distro'],
                  'qualified_guard_sha256': profile['guard_sha256'],
                  'reviewed_params_sha256': profile['import_params_sha256'],
                  'compiler_sdk_and_ros_checks': 'VERIFIED_ON_TARGET_BY_EXISTING_PREPARE_NOT_PC',
                  'guard_origin': 'EXISTING_DIGEST_PINNED_BINARY_NOT_A_NEW_TARGET_BUILD'},
              'field_sequence': ['current_board_battery', 'frozen_source_prepare_and_stationary_raw',
                  'fresh_same_boot_release', 'one_fixed_stop_and_scan_odom_tf',
                  'independent_safe_diagnostics', 'cleanup_and_raw_export'],
              'target_verified': False, 'autonomous_demo_ready': False,
              'robot_contacted': False, 'motion_authorized': False,
              'next_field_command_requires_new_on_site_approval': [sys.executable, '-B',
                  str(root/'scripts/run_robot_field_suite.py'), '--field-run', '--candidate',
                  str(out/'manifest.json'), '--operator-watching', '--clear-floor',
                  '--allow-torque-off', '--allow-fixed-motion-and-scan']}
    with (out/'report.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, allow_nan=False, indent=2)
    return report, out


def checked(root, manifest_path, *, now=None):
    """Revalidate before any field contact; never extract or execute tar input."""
    root = Path(root).resolve()
    path = safe_path(manifest_path)
    if path.name != 'manifest.json' or not path.is_relative_to(root/'artifacts/robot-field-candidates'):
        raise ValueError('FIELD_CANDIDATE_MANIFEST_ROOT')
    if path.stat().st_size > 256 * 1024:
        raise ValueError('FIELD_CANDIDATE_MANIFEST_BUDGET')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('FIELD_CANDIDATE_DUPLICATE_KEY')
            result[key] = value
        return result
    manifest = json.loads(path.read_bytes(), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('FIELD_CANDIDATE_NONFINITE')))
    keys = {'schema', 'source_id', 'archive_sha256', 'files', 'collection_fingerprint',
            'runner_sha256', 'preflight_sha256', 'created_unix_s', 'contracts_passed',
            'motion_authorized', 'robot_contacted', 'sensor_target', 'sensor_archive_sha256'}
    if (not isinstance(manifest, dict) or set(manifest) != keys or manifest['schema'] != SCHEMA
            or manifest['contracts_passed'] is not True or manifest['motion_authorized'] is not False
            or manifest['robot_contacted'] is not False):
        raise ValueError('FIELD_CANDIDATE_CONTRACT')
    created = manifest['created_unix_s']
    if (type(created) not in (int, float) or not 0 <= (time.time() if now is None else now)-created
            <= COLLECTION_CACHE_MAX_AGE_S):
        raise ValueError('FIELD_CANDIDATE_PC_CHECK_EXPIRED')
    members = source_members(root)
    if (manifest['source_id'] != identity(members) or manifest['files'] !=
            {name: sha(data) for name, data in members.items()} or
            manifest['collection_fingerprint'] != collection_fingerprint(root) or
            manifest['runner_sha256'] != runner_hashes(root)):
        raise ValueError('FIELD_CANDIDATE_SOURCE_OR_RUNNER_CHANGED')
    if manifest['sensor_target'] != sensor_target(root):
        raise ValueError('FIELD_CANDIDATE_SENSOR_SOURCE_CHANGED')
    sensor_archive = safe_path(path.parent/'sensor-target.tar')
    if manifest['sensor_archive_sha256'] is not None:
        if (sensor_archive.stat().st_size > MAX_ARCHIVE or
                sha(sensor_archive.read_bytes()) != manifest['sensor_archive_sha256']):
            raise ValueError('FIELD_CANDIDATE_SENSOR_ARCHIVE_CHANGED')
    receipt = safe_path(path.parent/'preflight.json')
    if receipt.stat().st_size > 256 * 1024 or sha(receipt.read_bytes()) != manifest['preflight_sha256']:
        raise ValueError('FIELD_CANDIDATE_PREFLIGHT_CHANGED')
    preflight = json.loads(receipt.read_bytes())
    if (preflight.get('status') != 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED' or
            preflight.get('field_suite_contracts', {}).get('status') != 'PASS'):
        raise ValueError('FIELD_CANDIDATE_PREFLIGHT_FAILED')
    archive = safe_path(path.parent/'source.tar')
    if archive.stat().st_size > MAX_ARCHIVE or sha(archive.read_bytes()) != manifest['archive_sha256']:
        raise ValueError('FIELD_CANDIDATE_ARCHIVE_CHANGED')
    with tarfile.open(archive, 'r:') as tar:
        entries = tar.getmembers()
        if len(entries) != len(members) or len({entry.name for entry in entries}) != len(entries):
            raise ValueError('FIELD_CANDIDATE_ARCHIVE_MEMBERS')
        for entry in entries:
            if (not entry.isfile() or entry.name not in members or entry.size != len(members[entry.name])
                    or tar.extractfile(entry).read() != members[entry.name]):
                raise ValueError('FIELD_CANDIDATE_ARCHIVE_MEMBER_CHANGED')
    return {**manifest, 'archive': str(archive), 'preflight': preflight}
