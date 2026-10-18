# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit one-shot PC transport for the isolated, bounded ROS scan trial.

No automatic retry, wheel command, driver installation, or autonomous authority.
The robot-side trial owns and stops its driver; this client preserves its originals.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from check_robot_connection import ROOT, endpoint
sys.path.insert(0, str(ROOT/'packages/twinpulse_robot_safety'))
from coin_driver_identity import CANDIDATE as DRIVER_CANDIDATE, description as driver_description

REMOTE = '/home/twinpulse/.local/share/twinpulse/robot'
CANDIDATE = DRIVER_CANDIDATE.as_posix()
FILES = ('report.json', 'driver.log', 'before-board.log', 'after-board.log',
         'ros-messages.raw', 'ros-messages.raw.footer.json')
RUN_ID = re.compile(r'ros-scan-\d{8}T\d{6}Z-[0-9a-f]{8}\Z')


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(*, host='192.168.35.139', identity_file=None, output=None,
        expected_boot=None, expected_release=None, runner=subprocess.run):
    """Run once and retain a bounded PC receipt even on transport/trial failure."""
    target = endpoint(host, 'twinpulse')
    key = Path(identity_file or Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation')
    out = Path(output or ROOT / 'artifacts/ros-scan-client' / uuid.uuid4().hex)
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'schema_version': 'ros-scan-client-1.0', 'status': 'STARTED',
               'motion_authorized': False, 'files': {}, 'robot_report': None,
               'expected_driver_identity':driver_description()}
    try:
        ssh = shutil.which('ssh.exe' if sys.platform == 'win32' else 'ssh')
        scp = shutil.which('scp.exe' if sys.platform == 'win32' else 'scp')
        source = ROOT / 'scripts/robot_ros_scan_trial.py'
        if not ssh or not scp or not key.is_file() or not source.is_file():
            raise RuntimeError('LOCAL_SSH_SCP_KEY_OR_TRIAL_MISSING')
        options = ['-i', str(key.resolve()), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                   '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5',
                   '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
                   '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
                   '-o', 'PermitLocalCommand=no']
        # Distinct immutable name avoids overwriting the prior candidate script.
        remote_script = CANDIDATE + '/robot_ros_scan_trial_' + _sha(source)[:16] + '.py'
        transfer = runner([scp, *options, str(source), target + ':' + remote_script],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35, check=False)
        if transfer.returncode:
            raise RuntimeError('TRIAL_SCRIPT_TRANSFER_FAILED_EXIT_' + str(transfer.returncode))
        attested = runner([ssh, *options, target, 'sha256sum ' + remote_script],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        if attested.returncode or attested.stdout.decode('ascii', 'replace').split(' ', 1)[0] != _sha(source):
            raise RuntimeError('TRANSFERRED_TRIAL_SCRIPT_HASH_MISMATCH')
        command = ('bash --noprofile --norc -c '
                   "'. /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=86 "
                   'ROS_LOCALHOST_ONLY=1 && exec python3 -B ' + remote_script + "'")
        try:
            completed = runner([ssh, *options, target, command], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=70, check=False)
        except subprocess.TimeoutExpired as exc:
            receipt['status'] = 'REMOTE_STATE_UNKNOWN'
            receipt['reason'] = 'SSH_TIMEOUT_DRIVER_AND_STOP_NOT_CONFIRMED'
            raise RuntimeError(receipt['reason']) from exc
        # Logs are local originals of transport output; never use them to claim motor safety.
        (out / 'transport.stdout').write_bytes(completed.stdout[:2 * 1024 * 1024])
        (out / 'transport.stderr').write_bytes(completed.stderr[:2 * 1024 * 1024])
        lines = [line for line in completed.stdout.decode('utf-8', 'replace').splitlines()
                 if line.startswith('{') and '"schema_version"' in line]
        if len(lines) != 1:
            raise RuntimeError('TRIAL_REPORT_MISSING_OR_AMBIGUOUS')
        report = json.loads(lines[0])
        remote_dir = report.get('report_directory')
        if (report.get('schema_version') != 'twinpulse-ros-scan-trial-1.0'
                or report.get('motion_authorized') is not False
                or not isinstance(remote_dir, str)
                or not RUN_ID.fullmatch(Path(remote_dir).name)
                or remote_dir != REMOTE + '/reports/' + Path(remote_dir).name):
            raise RuntimeError('TRIAL_REPORT_IDENTITY_INVALID')
        receipt['robot_report'] = report
        receipt['remote_exit_code'] = completed.returncode
        receipt['same_boot_release'] = (report.get('boot_id') == expected_boot
                                        and report.get('release_id') == expected_release)
        receipt['same_driver_identity'] = report.get('driver_identity') == driver_description()
        for name in FILES:
            limit = 8 * 1024 * 1024 if name == 'ros-messages.raw' else 1024 * 1024
            part = out / (name + '.part')
            final = out / name
            try:
                copied = runner([scp, *options, target + ':' + remote_dir + '/' + name,
                                 str(part)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=45, check=False)
                if copied.returncode or not part.is_file() or part.stat().st_size > limit:
                    receipt['files'][name] = 'MISSING_TRANSFER_FAILED_OR_TOO_LARGE'
                    continue
                part.replace(final)
                receipt['files'][name] = {'bytes': final.stat().st_size, 'sha256': _sha(final)}
            except (OSError, subprocess.TimeoutExpired):
                receipt['files'][name] = 'TRANSFER_ERROR'
        if any(not isinstance(value, dict) for value in receipt['files'].values()):
            raise RuntimeError('TRIAL_EVIDENCE_INCOMPLETE')
        copied_report = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        if copied_report != report:
            raise RuntimeError('TRIAL_REPORT_TRANSFER_MISMATCH')
        sys.path.insert(0, str(ROOT / 'packages/twinpulse_robot_safety'))
        from raw_ros_record import inspect_recording
        frames = inspect_recording(out / 'ros-messages.raw')
        raw = report.get('raw_ros', {})
        receipt['scan_frames_verified'] = sum(meta['topic'] == 'scan' for meta, _ in frames)
        if (raw.get('sha256') != receipt['files']['ros-messages.raw']['sha256']
                or receipt['scan_frames_verified'] != report.get('scan_count')):
            raise RuntimeError('TRIAL_RAW_REPORT_MISMATCH')
        stop = report.get('sensor_stop', {})
        before, after = report.get('before', {}), report.get('after', {})
        safe_cleanup = (stop.get('write_complete') is True
                        and stop.get('quiet_after_1s') is True
                        and stop.get('port_restored') is True
                        and after.get('torque_enabled') is False
                        and after.get('wheel_velocity_raw') == [0, 0]
                        and after.get('command_bytes_zero') is True
                        and before.get('encoders') == after.get('encoders'))
        receipt['status'] = ('ROS_SCAN_CAPTURED_PHYSICAL_STOP_UNCONFIRMED'
                             if completed.returncode == 0 and report.get('status') ==
                             'ROS_SCAN_OBSERVED_STOP_DATA_QUIET' and safe_cleanup
                             and receipt['same_boot_release'] and receipt['same_driver_identity'] else 'NEEDS_REVIEW')
        if receipt['status'] == 'NEEDS_REVIEW':
            issues = []
            if completed.returncode:
                issues.append('TRIAL_EXIT_' + str(completed.returncode))
            if report.get('status') != 'ROS_SCAN_OBSERVED_STOP_DATA_QUIET':
                issues.append('TRIAL_' + str(report.get('status'))[:50])
            for field in ('write_complete', 'quiet_after_1s', 'port_restored'):
                if stop.get(field) is not True:
                    issues.append('SENSOR_STOP_' + field.upper())
            if not safe_cleanup:
                issues.append('BOARD_OR_ENCODER_CLEANUP_UNCONFIRMED')
            if not receipt['same_boot_release']:
                issues.append('BOOT_RELEASE_MISMATCH')
            if not receipt['same_driver_identity']:
                issues.append('DRIVER_IDENTITY_MISMATCH')
            receipt['issues'] = issues
            receipt['reason'] = ','.join(issues)
    except (Exception, KeyboardInterrupt) as exc:
        if receipt['status'] != 'REMOTE_STATE_UNKNOWN':
            receipt['status'] = 'INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED'
            receipt['reason'] = type(exc).__name__ + ':' + str(exc)[:200]
    finally:
        (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2,
                                                     allow_nan=False), encoding='utf-8')
    return receipt, out


if __name__ == '__main__':
    raise SystemExit('Use run_robot_field_suite.py with one scoped field approval')
