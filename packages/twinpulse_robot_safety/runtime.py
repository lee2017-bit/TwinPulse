# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned Burger package installer/idle reader. No motion entry point in D1.

Managed operations share a kernel flock held for the entire child lifetime.
Legacy launch/direct SDK users do not honor it; fuser detects existing owners,
but is not protection against an unmanaged process racing to open the port.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
import shutil

ROOT = Path(__file__).resolve().parent
HOME = Path.home() / '.local/share/twinpulse/robot'
DEVICE = '/dev/ttyACM0'
MARKER = 'TWINPULSE_PREPARE_REPORT='


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.new')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


@contextmanager
def ownership(home=HOME):
    import fcntl
    state = home / 'state'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never unlink the lock inode: concurrent waiters must refer to the same file.
    with (state / 'opencr.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('BUSY: another managed robot operation owns OpenCR') from exc
        # Closing this parent's FD releases ownership only after inherited child
        # FDs are also closed. Explicit LOCK_UN would unlock a still-living child.
        yield lock


def idle_port():
    result = subprocess.run(['fuser', DEVICE], capture_output=True, timeout=3)
    if result.returncode == 0:
        raise RuntimeError('BUSY: serial already opened; no device access attempted')
    if result.returncode != 1 or result.stderr.strip():
        raise RuntimeError('UNKNOWN: serial ownership check failed')


def run_logged(command, log, timeout=120, pass_fds=()):
    # Regular-file log avoids pipe deadlock. Process group is reaped before lease release.
    with log.open('ab') as stream:
        child = subprocess.Popen(command, stdout=stream, stderr=stream, start_new_session=True, pass_fds=pass_fds)
        try:
            code = child.wait(timeout=timeout)
        except BaseException:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise
    if code:
        raise RuntimeError(f'Child failed: {Path(command[0]).name}, exit={code}; see log')


def verify_release(release):
    manifest = json.loads((release / 'manifest.json').read_text())
    if (manifest.get('schema_version') != 'robot-release-1.0'
            or manifest.get('profile') != 'twinpulse-burger'
            or not re.fullmatch('[a-f0-9]{64}', manifest.get('source_id', ''))
            or manifest.get('motion_enabled') is not False):
        raise ValueError('Unsupported deployment manifest')
    required = {'runtime.py', 'robot_health.py', 'bin/opencr_readonly',
                'bin/turtlebot3_ros', 'burger.yaml', 'profile.json', 'stationary.py',
                'stationary.sh', 'stationary_observer.py', 'owned_exec.py'}
    files = manifest['files']
    if not required.issubset(files):
        raise ValueError('Incomplete deployment manifest')
    for name, expected in files.items():
        path = release / name
        if not path.resolve().is_relative_to(release.resolve()) or path.is_symlink():
            raise ValueError('Artifact escapes release')
        if digest(path) != expected:
            raise ValueError('Artifact changed: ' + name)
    profile = json.loads((release / 'profile.json').read_text())
    if digest(release / 'bin/turtlebot3_ros') != profile['guard_sha256']:
        raise ValueError('Guard qualification hash mismatch')
    return manifest


def prepare(source, home, log):
    profile = json.loads((source / 'profile.json').read_text())
    if platform.machine() != profile['architecture'] or Path.home().name != 'twinpulse':
        raise RuntimeError('This migration profile requires the qualified Burger ARM64 user')
    # Bundle digest binds every shipped source byte, including recipe and health code.
    source_files = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*'))
                    if p.is_file() and '__pycache__' not in p.parts and p.name != 'source.tar'}
    source_id = hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest()
    release = home / 'releases' / source_id
    cached = release.exists()
    if cached:
        verify_release(release)  # Never rebuild over a changed release.
    else:
        imported = Path(profile['import_guard'])
        if digest(imported) != profile['guard_sha256']:
            raise ValueError('Qualified migration guard missing or changed; no automatic replacement')
        imported_params = Path(profile['import_params'])
        if not imported_params.is_file():
            raise ValueError('IMPORTED_PARAMS_MISSING: reviewed Burger ROS parameters unavailable')
        if digest(imported_params) != profile['import_params_sha256']:
            raise ValueError('IMPORTED_PARAMS_DIGEST_MISMATCH: reviewed Burger ROS parameters changed')
        run_logged(['/bin/bash', str(source / 'ros_preflight.sh')], log, timeout=15)
        staging = home / 'releases' / (source_id + '.staging-' + uuid.uuid4().hex)
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns('__pycache__', 'source.tar'))
        (staging / 'bin').mkdir()
        shutil.copy2(imported, staging / 'bin/turtlebot3_ros')
        shutil.copy2(imported_params, staging / 'burger.yaml')
        run_logged(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I/opt/ros/humble/include', str(staging / 'src/opencr_readonly_check.cpp'),
                    '-L/opt/ros/humble/lib', '-Wl,-rpath,/opt/ros/humble/lib',
                    '-ldynamixel_sdk', '-o', str(staging / 'bin/opencr_readonly')], log)
        run_logged(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I/opt/ros/humble/include', str(staging / 'src/opencr_torque_off.cpp'),
                    '-L/opt/ros/humble/lib', '-Wl,-rpath,/opt/ros/humble/lib',
                    '-ldynamixel_sdk', '-o', str(staging / 'bin/opencr_torque_off')], log)
        # Device-free source checks only; the real trial is NOT built or run.
        run_logged(['cmake', '-S', str(staging), '-B', str(staging / 'checks'),
                    '-DBUILD_ROS_TESTS=OFF'], log)
        run_logged(['cmake', '--build', str(staging / 'checks'), '-j2'], log)
        run_logged(['ctest', '--test-dir', str(staging / 'checks'), '--output-on-failure'], log)
        run_logged(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    str(staging / 'trial/battery_policy_test.cpp'), '-o', str(staging / 'bin/battery_policy_test')], log)
        run_logged([str(staging / 'bin/battery_policy_test')], log)
        # Build directories are retained for evidence, not loaded as runtime artifacts.
        files = {p.relative_to(staging).as_posix(): digest(p) for p in sorted(staging.rglob('*'))
                 if p.is_file() and 'checks' not in p.relative_to(staging).parts and '__pycache__' not in p.parts}
        manifest = {'schema_version': 'robot-release-1.0', 'profile': 'twinpulse-burger',
                    'source_id': source_id, 'source_files': source_files, 'files': files,
                    'motion_enabled': False, 'vendor_commit': profile['vendor_commit'],
                    'guard_origin': 'digest-pinned qualified binary migration; not rebuilt',
                    'created_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        write_json(staging / 'manifest.json', manifest)
        verify_release(staging)
        staging.rename(release)
    # Verify the compiled dependency again even for a cached project release,
    # before selecting it. This subprocess does not open a serial port or launch
    # the driver. Source-only fixtures without the scan adapter stay supported.
    if 'isolated_ros_scan.py' in source_files:
        if 'coin_driver_identity.py' not in source_files:
            raise ValueError('ISOLATED_DRIVER_IDENTITY_SOURCE_MISSING')
        run_logged([sys.executable, '-B', str(release / 'isolated_ros_scan.py'),
                    '--artifact-preflight'], log, timeout=12)
    current = home / 'current'
    if current.exists() and not current.is_symlink():
        raise ValueError('Refusing to replace a non-symlink current path')
    link = home / ('current.' + uuid.uuid4().hex + '.new')
    link.symlink_to(release, target_is_directory=True)
    link.replace(current)
    return release, cached


def read_board(release, log, lease_fd):
    verify_release(release)
    idle_port()
    run_logged([sys.executable, '-B', str(release / 'owned_exec.py'), 'read-board', str(os.getpid())],
               log, timeout=8, pass_fds=(lease_fd,))


def disarm_board(release, log, lease_fd, operator_confirmed=False):
    """Explicit OFF-only maintenance, never implied by a read/check/prepare."""
    if operator_confirmed is not True:
        raise ValueError('Torque OFF requires explicit flat-floor confirmation')
    manifest = verify_release(release)
    if 'bin/opencr_torque_off' not in manifest['files']:
        raise ValueError('This release has no verified OFF helper; prepare the current sources first')
    idle_port()
    run_logged([sys.executable, '-B', str(release / 'owned_exec.py'), 'torque-off', str(os.getpid())],
               log, timeout=8, pass_fds=(lease_fd,))


def create_operation_log(report_dir):
    """Keep an exact log even when stationary needs no operation subprocess."""
    log = report_dir / 'operation.log'
    log.touch(exist_ok=False)
    return log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'read-board', 'verify', 'stationary'])
    parser.add_argument('--disable-torque', action='store_true')
    parser.add_argument('--operator-confirmed-flat-clear-floor', action='store_true')
    args = parser.parse_args()
    if args.disable_torque != args.operator_confirmed_flat_clear_floor or (args.disable_torque and args.action != 'prepare'):
        parser.error('OFF requires prepare plus both explicit OFF and flat-floor flags')
    run_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8]
    report_dir = HOME / 'reports' / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 'robot-prepare-1.0', 'run_id': run_id,
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'action': args.action, 'motion_authorized': False, 'status': 'STARTED'}
    log = create_operation_log(report_dir)
    write_json(report_dir / 'report.json', report)
    try:
        with ownership() as lease:
            if args.action == 'prepare':
                release, cached = prepare(ROOT, HOME, log)
                report.update(release=str(release), build_cached=cached)
            else:
                release = (HOME / 'current').resolve(strict=True)
            manifest = verify_release(release)
            report['release_id'] = manifest['source_id']
            if args.action == 'stationary':
                sys.path.insert(0, str(release))
                from stationary import run as run_stationary
                from robot_health import parse_board_snapshot

                def snapshot(label):
                    path = report_dir / (label + '-board.log')
                    read_board(release, path, lease.fileno())
                    return parse_board_snapshot(path.read_text())

                report['stationary'] = run_stationary(release, report_dir, snapshot, lease.fileno())
                report['status'] = report['stationary']['status']
            elif args.action in {'prepare', 'read-board'}:
                board_log = report_dir / 'board.log'
                off_error = None
                if args.disable_torque:
                    report['torque_off_requested'] = True
                    try:
                        disarm_board(release, log, lease.fileno(), operator_confirmed=True)
                        report['torque_off_command'] = 'OFF_HELPER_COMPLETED'
                    except (Exception, KeyboardInterrupt) as exc:
                        off_error = exc
                        report['torque_off_command'] = 'FAILED_OR_INTERRUPTED'
                # Also read after a failed OFF, without retrying the control action.
                read_board(release, board_log, lease.fileno())
                sys.path.insert(0, str(release))
                from robot_health import parse_board_snapshot, health_snapshot, summarize_health
                board = parse_board_snapshot(board_log.read_text())
                report['board'] = board
                # Reuse this one fresh board observation; do not recursively acquire the lease.
                report['health'] = summarize_health(health_snapshot(board))
                report['sensor_streams'] = 'NOT_CHECKED: preparation does not start ROS drivers'
                if args.action == 'read-board':
                    print(board_log.read_text(), end='')
                idle = not board['torque_enabled'] and not any(board['wheel_velocity_raw']) and board['command_bytes_zero']
                report['status'] = ('SOFTWARE_PREPARED_IDLE' if idle and not board['near_board_protection']
                                    and report['health']['status'] == 'IDLE_SNAPSHOT_OK'
                                    else 'PREPARED_NEEDS_ATTENTION')
                if off_error is not None:
                    raise off_error
            else:
                report['status'] = 'ARTIFACTS_VERIFIED_ONLY'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                      error_type=type(exc).__name__, reason=str(exc))
        from stationary import bounded_error_lines
        report['failure_diagnostics'] = {'operation': bounded_error_lines(log),
                                         'robot_log_dir': str(report_dir)}
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_json(report_dir / 'report.json', report)
    print(MARKER + json.dumps(report))
    return 0 if (report['status'] in {'SOFTWARE_PREPARED_IDLE', 'ARTIFACTS_VERIFIED_ONLY', 'STATIONARY_CHECK_PASS'}
                 or args.action == 'read-board' and report['status'] == 'PREPARED_NEEDS_ATTENTION') else 2


def interrupt_handler(*_):
    raise KeyboardInterrupt('Operation interrupted; active child cleanup requested')


if __name__ == '__main__':
    for name in ('SIGTERM', 'SIGHUP'):  # SIGHUP does not exist on Windows, where only the argument checks run (tests)
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupt_handler)
    raise SystemExit(main())
