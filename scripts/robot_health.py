# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded health collection for the current Burger profile; no motion actions.

The optional backend is a manifest-verified permanent PING/READ executable,
invoked through the managed-operation lease. A report never grants motion permission.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

DEPLOYMENT = Path('/home/twinpulse/.local/share/twinpulse/robot/current')
BOARD_HELPER = DEPLOYMENT / 'bin/opencr_readonly'
GUARD_PATH = DEPLOYMENT / 'bin/turtlebot3_ros'
GUARD_SHA256 = '403b148b2bdbf0e4c6fc0540888768f9a5eddd38649b1d20883e61fb7fcdc042'


def read_text_or_none(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def digest(path):
    try:
        with Path(path).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    except AttributeError:  # Pi Python3.10
        h = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()


def parse_board_snapshot(output):
    expected = {0: 9, 18: 1, 42: 4, 128: 16, 149: 1, 150: 24}
    ranges = {}
    for line in output.splitlines():
        match = re.fullmatch(r'READ \w+ addr=(\d+) len=(\d+) comm=0 error=0 bytes=([0-9A-Fa-f]+)', line)
        if match:
            addr, length = int(match[1]), int(match[2])
            data = bytes.fromhex(match[3])
            if addr in ranges or expected.get(addr) != length or len(data) != length:
                raise ValueError('Invalid or duplicate register range')
            ranges[addr] = data
    if set(ranges) != set(expected):
        raise ValueError('Incomplete successful board reads')
    if 'PING id=200 comm=0 error=0 model=20480 ' not in output:
        raise ValueError('Unexpected board identity')
    if not re.search(r'^RESTORE termios=0 modem=0 modem_saved=[01]$', output, re.M):
        raise ValueError('Port restoration not confirmed')
    ident = ranges[0]
    if struct.unpack('<H', ident[:2])[0] != 20480 or struct.unpack('<I', ident[2:6])[0] != 1 or ident[6] != 5 or ident[7] != 200:
        raise ValueError('Not the qualified Burger FW5 control table')
    if ranges[149][0] not in (0, 1):
        raise ValueError('Invalid torque value')
    centivolts = struct.unpack('<I', ranges[42])[0]
    if not 350 <= centivolts <= 1300:
        raise ValueError('Invalid supply voltage')
    lv, rv, le, re_ = struct.unpack('<iiii', ranges[128])
    return {'status': 'OBSERVED', 'source': 'opencr_ping_read',
            'observed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'voltage_v': centivolts / 100, 'estimated_percent': round(max(0, min(100, (centivolts - 1050) / 1.8)), 1),
            'estimate_method': 'public_vendor_voltage_mapping_not_calibrated_capacity',
            'charge_requested': centivolts <= 1086,
            'near_board_protection': centivolts <= 1110,
            'torque_enabled': bool(ranges[149][0]), 'wheel_velocity_raw': [lv, rv],
            'encoders': [le, re_], 'command_bytes_zero': not any(ranges[150]),
            'firmware_version': ident[6], 'port_restored': True}


def deployment():
    release = DEPLOYMENT.resolve(strict=True)
    if release.parent != DEPLOYMENT.parent / 'releases' or not re.fullmatch('[a-f0-9]{64}', release.name):
        raise ValueError('Invalid release target')
    manifest = json.loads((release / 'manifest.json').read_text())
    if (manifest.get('schema_version') != 'robot-release-1.0'
            or manifest.get('profile') != 'twinpulse-burger'
            or manifest.get('source_id') != release.name
            or manifest.get('motion_enabled') is not False):
        raise ValueError('Invalid release manifest')
    files = manifest['files']
    if not {'runtime.py', 'robot_health.py', 'bin/opencr_readonly', 'bin/turtlebot3_ros', 'profile.json', 'burger.yaml'}.issubset(files):
        raise ValueError('Incomplete release')
    for name, expected in files.items():
        path = release / name
        if path.is_symlink() or not path.resolve().is_relative_to(release) or digest(path) != expected:
            raise ValueError('Release artifact changed')
    if files['bin/turtlebot3_ros'] != GUARD_SHA256:
        raise ValueError('Guard qualification changed')
    return {'status': 'VERIFIED', 'release_id': release.name, 'manifest_sha256': digest(release / 'manifest.json')}


def board_snapshot():
    if os.environ.get('TWINPULSE_BOARD_SNAPSHOT') != '1':
        return {'status': 'NOT_REQUESTED'}
    try:
        deployment()
        result = subprocess.run(['python3', '-B', str(DEPLOYMENT / 'runtime.py'), 'read-board'],
                                capture_output=True, timeout=20, check=False)
        if result.returncode:
            if b'BUSY:' in result.stdout:
                return {'status': 'BUSY', 'reason': 'managed_operation_or_serial_owned'}
            return {'status': 'UNKNOWN', 'reason': 'board_read_failed', 'exit_code': result.returncode}
        return parse_board_snapshot(result.stdout.decode('utf-8', errors='replace'))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        return {'status': 'UNKNOWN', 'reason': 'board_snapshot_unavailable', 'error_type': type(exc).__name__}


SESSION_EVIDENCE_DIR = Path.home() / '.local/share/twinpulse/fleet/sessions'
STORAGE_LOW_GIB = 1.0  # below this the pre-session check reports NEEDS_ATTENTION (fleet worker refuses under 512 MiB)


def storage_snapshot(usage=None, sessions_dir=SESSION_EVIDENCE_DIR, limit_s=5.0):
    """Read-only free-space and session-evidence totals; never deletes. Bounded walk time."""
    started = time.monotonic()
    usage = usage or shutil.disk_usage('/')
    count = total = 0; complete = True
    try:
        if sessions_dir.is_dir():
            for entry in sorted(sessions_dir.iterdir()):
                if not entry.is_dir() or entry.is_symlink():
                    continue
                count += 1
                for root, dirs, files in os.walk(entry):
                    for name in files:
                        try:
                            total += (Path(root) / name).stat().st_size
                        except OSError:
                            pass
                    if time.monotonic() - started > limit_s:
                        complete = False; break
                if not complete:
                    break
    except OSError:
        complete = False
    free_gib = round(usage.free / 1024**3, 2)
    return {'root_free_gib': free_gib, 'root_total_gib': round(usage.total / 1024**3, 2),
            'state': 'LOW' if free_gib < STORAGE_LOW_GIB else 'OK',
            'sessions_dir': str(sessions_dir), 'sessions_count': count,
            'sessions_gib': round(total / 1024**3, 2), 'sessions_walk_complete': complete}


def health_snapshot(board=None):
    started = time.monotonic()
    processes = []
    for path in Path('/proc').glob('[0-9]*/comm'):
        name = read_text_or_none(path)
        if name in {'turtlebot3_ros', 'stop_probe', 'stop_probe_fake', 'coin_d4_driver', 'ld08_driver'}:
            row = {'pid': int(path.parent.name), 'name': name, 'guard_verified': False}
            if name == 'turtlebot3_ros':
                try:
                    row['guard_verified'] = digest(path.parent / 'exe') == GUARD_SHA256
                except OSError:
                    row['executable_unreadable'] = True
            processes.append(row)
    temperature = read_text_or_none('/sys/class/thermal/thermal_zone0/temp')
    try:
        temperature = float(temperature) / 1000 if temperature else None
    except ValueError:
        temperature = None
    usage = shutil.disk_usage('/')
    storage = storage_snapshot(usage)
    try:
        installed = deployment()
    except (OSError, ValueError, KeyError, TypeError):
        installed = {'status': 'MISSING_OR_CHANGED'}
    guard_installed = installed['status'] == 'VERIFIED'
    data = {'schema_version': 'robot-health-1.0',
            'observed_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'boot_id': read_text_or_none('/proc/sys/kernel/random/boot_id'),
            'uptime': read_text_or_none('/proc/uptime'), 'cpu_temperature_c': temperature,
            'root_free_gib': round(usage.free / 1024**3, 2), 'storage': storage,
            'serial_devices': sorted(p.name for p in Path('/dev').glob('ttyACM*')) + sorted(p.name for p in Path('/dev').glob('ttyUSB*')),
            'processes': processes, 'guard_artifact_verified': guard_installed, 'deployment': installed,
            'board': board_snapshot() if board is None else board, 'motion_authorized': False,
            'capability_checks': {'physical_stop_qualification': 'INCOMPLETE',
                                  'lidar_rotation_stop': 'UNVERIFIED',
                                  'tf_chain': 'NOT_CHECKED', 'navigation': 'NOT_CHECKED'},
            'limitations': ['Snapshot does not certify stopping or authorize motion.',
                            'Managed operations share an exclusive lease; legacy direct launches do not.',
                            'Existing unmanaged serial owners are refused; a new unmanaged opener can race.',
                            'Prepared software and fresh session are not authorization to move.']}
    data['collection_seconds'] = round(time.monotonic() - started, 3)
    return data


def summarize_health(health):
    board = health['board']
    issues = []
    if board.get('status') != 'OBSERVED':
        issues.append('Board state unavailable: ' + board.get('reason', board['status']))
    else:
        if board['charge_requested']:
            issues.append('Charge requested: estimated battery <=20%.')
        elif board['near_board_protection']:
            issues.append('Voltage is near the independent board protection range.')
        if board['torque_enabled'] or any(board['wheel_velocity_raw']) or not board['command_bytes_zero']:
            issues.append('Board is not confirmed idle with motors disabled.')
    for process in health['processes']:
        if process['name'] == 'turtlebot3_ros' and not process['guard_verified']:
            issues.append('Running base executable is not the qualified guarded build.')
    if not health['guard_artifact_verified']:
        issues.append('Qualified guarded executable is unavailable or changed.')
    storage = health.get('storage') or {}
    if storage.get('state') == 'LOW':
        issues.append('Robot disk low: %s GiB free; move or prune old session evidence before a session (Prune-Robot-Sessions).' % storage.get('root_free_gib'))
    health['issues'] = issues
    health['status'] = 'NEEDS_ATTENTION' if issues else 'IDLE_SNAPSHOT_OK'
    if health['status'] == 'IDLE_SNAPSHOT_OK' and health['processes']:
        health['status'] = 'SNAPSHOT_COLLECTED'
    return health
