# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One command: versioned no-motion Burger preparation and saved report.

Uses existing ROS/SDK/SSH keys only. Never installs system packages. Default
prepare does not start drivers; stationary mode explicitly checks a disarmed base.
The qualified guard binary is imported once from its verified staging
location. This is a migration tool, not a clean-OS installer.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid
import webbrowser

from check_robot_connection import ROOT, endpoint, write_report
from robot_source_identity import bundle_files

PACKAGE = ROOT / 'packages/twinpulse_robot_safety'
sys.path.insert(0, str(PACKAGE))
from raw_ros_record import inspect_recording
REMOTE = '/home/twinpulse/.local/share/twinpulse/robot'
MARKER = 'TWINPULSE_PREPARE_REPORT='
STATIONARY_FILES = ('report.json', 'operation.log', 'telemetry.json',
                    'base.log', 'observer.log', 'before-board.log', 'after-board.log',
                    'ros-messages.raw', 'ros-messages.raw.footer.json')


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def export_stationary_files(report, out, *, scp, options, target, runner=subprocess.run):
    """Fetch only named evidence files; never run or restart the robot on retry."""
    run_id = report.get('run_id')
    if not isinstance(run_id, str) or not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', run_id):
        raise ValueError('REMOTE_REPORT_ID_INVALID')
    out = Path(out)
    destination = out / 'robot-evidence'
    if out.is_symlink() or destination.is_symlink():
        raise ValueError('EVIDENCE_DESTINATION_SYMLINK')
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('EVIDENCE_DESTINATION_SYMLINK')
    receipt_path = destination / 'export.json'
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError('EVIDENCE_RECEIPT_PATH_UNSAFE')
    cached = {}
    try:
        previous = json.loads(receipt_path.read_text(encoding='utf-8'))
        saved_report = json.loads((destination / 'report.json').read_text(encoding='utf-8'))
        if (previous.get('run_id') == run_id and saved_report.get('run_id') == run_id
                and isinstance(previous.get('files'), dict)):
            cached = previous['files']
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    files = {}
    for name in STATIONARY_FILES:
        limit = 80 * 1024 * 1024 if name == 'ros-messages.raw' else 16 * 1024 * 1024
        final = destination / name
        local = destination / (name + '.part')
        if (final.is_symlink() or local.is_symlink()
                or local.exists() and not local.is_file()):
            files[name] = {'status': 'LOCAL_PATH_UNSAFE_OR_STALE'}
            continue
        prior = cached.get(name)
        if (isinstance(prior, dict) and prior.get('status') == 'COPIED'
                and final.is_file() and not final.is_symlink() and final.stat().st_size <= limit
                and prior.get('bytes') == final.stat().st_size
                and prior.get('sha256') == _file_sha256(final)):
            files[name] = dict(prior)
            continue
        remote = target + ':' + REMOTE + '/reports/' + run_id + '/' + name
        discarded_partial = local.is_file()
        if discarded_partial:
            try:
                local.unlink()  # Exact generated partial only; never a completed evidence file.
            except OSError:
                files[name] = {'status': 'STALE_PARTIAL_UNREMOVABLE'}
                continue
        try:
            transfer = runner([scp, *options, remote, str(local)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=45, check=False)
            if local.is_symlink() or local.exists() and not local.is_file():
                files[name] = {'status': 'LOCAL_PATH_UNSAFE_OR_STALE'}
                continue
            if transfer.returncode != 0 or not local.is_file():
                files[name] = {'status': 'MISSING_OR_TRANSFER_FAILED',
                               'exit_code': transfer.returncode}
                continue
            size = local.stat().st_size
            if size > limit:
                files[name] = {'status': 'SIZE_LIMIT_EXCEEDED', 'bytes': size}
                continue
            local.replace(final)
            files[name] = {'status': 'COPIED', 'bytes': size,
                           'sha256': _file_sha256(final),
                           'stale_partial_discarded': discarded_partial}
        except (OSError, subprocess.TimeoutExpired) as exc:
            files[name] = {'status': 'TRANSFER_ERROR', 'error_type': type(exc).__name__}
        finally:
            if local.is_file() and not local.is_symlink():
                local.unlink()
    replay = {'status': 'NOT_AVAILABLE'}
    raw_path = destination / 'ros-messages.raw'
    if raw_path.is_file() and raw_path.with_suffix('.raw.footer.json').is_file():
        try:
            frames = inspect_recording(raw_path)
            replay = {'status': 'VERIFIED_OFFLINE', 'message_count': len(frames)}
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            replay = {'status': 'REJECTED', 'reason': type(exc).__name__ + ':' + str(exc)[:120]}
    binding = {'status': 'NOT_AVAILABLE'}
    if replay['status'] == 'VERIFIED_OFFLINE' and all(
            files[name]['status'] == 'COPIED' for name in ('report.json', 'telemetry.json')):
        try:
            remote_report = json.loads((destination / 'report.json').read_text(encoding='utf-8'))
            telemetry = json.loads((destination / 'telemetry.json').read_text(encoding='utf-8'))
            captured = telemetry['raw_ros']
            footer = json.loads(raw_path.with_suffix('.raw.footer.json').read_text(encoding='utf-8'))
            if (remote_report['run_id'] != run_id
                    or any(report.get(field) is not None
                           and remote_report.get(field) != report[field]
                           for field in ('boot_id', 'release_id'))
                    or captured['sha256'] != footer['sha256']
                    or captured['counts'] != footer['counts'] or captured['complete'] is not True):
                raise ValueError('ROBOT_REPORT_RAW_BINDING_MISMATCH')
            binding = {'status': 'VERIFIED_SAME_RUN'}
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            binding = {'status': 'REJECTED', 'reason': type(exc).__name__ + ':' + str(exc)[:120]}
    receipt = {'schema_version': 'robot-evidence-export-1', 'run_id': run_id,
               'robot_originals_retained': True, 'files': files,
               'raw_replay': replay, 'report_binding': binding,
               'status': 'COMPLETE' if all(value['status'] == 'COPIED' for value in files.values())
                        and replay['status'] == 'VERIFIED_OFFLINE' and binding['status'] == 'VERIFIED_SAME_RUN'
                        else 'INCOMPLETE'}
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError('EVIDENCE_RECEIPT_PATH_UNSAFE')
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


def bundle(output):
    files = bundle_files(ROOT)
    # Deterministic archive members, no symlinks or paths supplied by the robot.
    with tarfile.open(output, 'w') as archive:
        for name, content in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(content), 0o644, 0
            archive.addfile(member, io.BytesIO(content))
    return hashlib.sha256(output.read_bytes()).hexdigest()


def parse_prepare(output):
    records = [line[len(MARKER):] for line in output.decode('utf-8', errors='replace').splitlines()
               if line.startswith(MARKER)]
    if len(records) != 1:
        raise ValueError('No unique prepare report')
    data = json.loads(records[0])
    if data.get('schema_version') != 'robot-prepare-1.0' or data.get('motion_authorized') is not False:
        raise ValueError('Invalid prepare report')
    return data


def resume_saved_stationary_export(saved_report, *, scp, options, target,
                                   runner=subprocess.run, output_root=None):
    """Retry data transfer for one saved stationary run, never repeat the check."""
    path = Path(saved_report)
    base = ((output_root or ROOT / 'artifacts') / 'robot-preparation').resolve()
    resolved = path.resolve(strict=True)
    parts = resolved.relative_to(base).parts
    if (len(parts) != 3 or not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', parts[0])
            or parts[1:] != ('result', 'report.json') or path.is_symlink()
            or resolved.stat().st_size > 16 * 1024 * 1024):
        raise ValueError('SAVED_STATIONARY_REPORT_PATH_INVALID')
    report = json.loads(resolved.read_text(encoding='utf-8'))
    if (report.get('schema_version') != 'robot-prepare-1.0'
            or report.get('action') != 'stationary'
            or report.get('motion_authorized') is not False
            or report.get('status') not in {'STATIONARY_CHECK_PASS', 'EVIDENCE_EXPORT_INCOMPLETE'}
            or not all(isinstance(report.get(field), str) and report[field]
                       for field in ('run_id', 'boot_id', 'release_id'))):
        raise ValueError('SAVED_STATIONARY_REPORT_INVALID')
    # out is the existing client run directory, not the robot's different run ID.
    return export_stationary_files(report, resolved.parent.parent, scp=scp,
                                   options=options, target=target, runner=runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.35.139')
    parser.add_argument('--user', default='twinpulse', choices=['twinpulse'])
    parser.add_argument('--identity-file', type=Path,
                        default=Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation')
    parser.add_argument('--open-report', action='store_true')
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--candidate', type=Path,
                        help='Checked frozen source, only prepare/stationary; never rebuilds the archive')
    parser.add_argument('--mode', choices=['prepare', 'offline', 'stationary', 'resume-evidence'], default='prepare',
                        help='offline never connects; stationary explicitly runs a bounded disarmed check')
    parser.add_argument('--saved-report', type=Path,
                        help='Existing stationary result/report.json for transfer-only resume')
    parser.add_argument('--disable-torque', action='store_true',
                        help='Explicit OFF-only preparation; never enables torque or drives')
    parser.add_argument('--operator-confirmed-flat-clear-floor', action='store_true')
    args = parser.parse_args()
    frozen = None
    if args.candidate:
        if args.mode not in {'prepare', 'stationary'}:
            parser.error('candidate requires prepare or stationary mode')
        from robot_field_candidate import checked
        try:
            frozen = checked(ROOT, args.candidate)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print('Candidate rejected before robot contact: ' + type(exc).__name__ + ':' + str(exc))
            return 2
    if args.disable_torque != args.operator_confirmed_flat_clear_floor or (args.disable_torque and args.mode != 'prepare'):
        parser.error('OFF requires prepare mode plus both explicit OFF and flat-floor flags')
    if (args.mode == 'resume-evidence') != (args.saved_report is not None):
        parser.error('resume-evidence requires --saved-report, only in that mode')
    target = endpoint(args.host, args.user)
    if args.mode == 'resume-evidence':
        scp = shutil.which('scp.exe' if sys.platform == 'win32' else 'scp')
        if not scp or not args.identity_file.is_file():
            print('Existing OpenSSH/key missing; no robot command attempted.', flush=True)
            return 2
        options = ['-i', str(args.identity_file), '-o', 'IdentitiesOnly=yes',
                   '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5',
                   '-o', 'ServerAliveCountMax=2', '-o', 'ForwardAgent=no',
                   '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no']
        try:
            receipt = resume_saved_stationary_export(
                args.saved_report, scp=scp, options=options, target=target, output_root=args.output_root)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print('Evidence resume rejected: ' + type(exc).__name__ + ':' + str(exc), flush=True)
            return 2
        print('Evidence transfer only: ' + receipt['status'], flush=True)
        print('Receipt: ' + str(args.saved_report.resolve().parent.parent / 'robot-evidence/export.json'), flush=True)
        return 0 if receipt['status'] == 'COMPLETE' else 2
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = (args.output_root or ROOT / 'artifacts') / 'robot-preparation' / run_id
    out.mkdir(parents=True)
    result = {'schema_version': 'robot-prepare-client-1.0', 'status': 'STARTED',
              'run_id': run_id, 'motion_authorized': False}
    (out / 'started.json').write_text(json.dumps(result))
    options = ['-i', str(args.identity_file), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5',
               '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
               '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no']
    ssh = shutil.which('ssh.exe' if sys.platform == 'win32' else 'ssh')
    scp = shutil.which('scp.exe' if sys.platform == 'win32' else 'scp')

    def execute(command, seconds=30):
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=seconds)
        with (out / 'transport.log').open('ab') as log:
            log.write(process.stdout + process.stderr)
        if process.returncode:
            # A remote attention report is still useful, even with nonzero exit.
            if MARKER.encode() in process.stdout:
                return process.stdout
            raise RuntimeError('Transfer or remote command failed; see transport.log')
        return process.stdout

    try:
        if args.mode == 'offline':
            archive = out / 'source.tar'
            result.update(status='OFFLINE_BUNDLE_READY', bundle_sha256=bundle(archive),
                          bundle_path=str(archive), actual_robot_validation='NOT_RUN',
                          motion_runner='NOT_ENABLED')
        elif not ssh or not scp or not args.identity_file.is_file():
            raise RuntimeError('Existing OpenSSH/key missing; no component installed')
        elif args.mode == 'stationary':
            print('Explicit stationary check: no motor enable or drive command.', flush=True)
            result = parse_prepare(execute([ssh, *options, target,
                'exec python3 -B ' + REMOTE + '/current/runtime.py stationary'], seconds=75))
            export = export_stationary_files(result, out, scp=scp, options=options, target=target)
            result['evidence_export'] = export
            if export['status'] != 'COMPLETE':
                result['stationary_status'] = result['status']
                result['status'] = 'EVIDENCE_EXPORT_INCOMPLETE'
        else:
            if frozen is not None:
                archive = Path(frozen['archive'])
                bundle_id = frozen['archive_sha256']
            else:
                archive = out / 'source.tar'
                bundle_id = bundle(archive)
            incoming = REMOTE + '/incoming/' + bundle_id
            print('1/3 Packaging and transferring reviewed sources. No driver startup.', flush=True)
            execute([ssh, *options, target, 'mkdir -p ' + incoming])
            execute([scp, *options, str(archive), target + ':' + incoming + '/source.tar'])
            print('2/3 Verifying/caching artifacts and running device-free checks.', flush=True)
            # All remote path components are constants or locally computed SHA256.
            command = ('cd ' + incoming + ' && echo ' + bundle_id + ' source.tar | sha256sum -c - && tar -xf source.tar && '
                       'exec python3 -B runtime.py prepare')
            if args.disable_torque:
                command += ' --disable-torque --operator-confirmed-flat-clear-floor'
            result = parse_prepare(execute([ssh, *options, target, command], seconds=300))
            print('3/3 Idle board snapshot and saved report: ' + result['status'], flush=True)
        if (frozen is not None and result.get('status') in {'SOFTWARE_PREPARED_IDLE', 'STATIONARY_CHECK_PASS'}
                and result.get('release_id') != frozen['source_id']):
            result.update(status='CANDIDATE_RELEASE_MISMATCH', motion_authorized=False,
                          reason='Remote prepare/stationary release differs from frozen source')
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'PREPARATION_FAILED',
                      reason=str(exc), error_type=type(exc).__name__)
    page = write_report(result, out / 'result')
    print('Status: ' + result['status'], flush=True)
    print('Report: ' + str(page), flush=True)
    if args.open_report:
        webbrowser.open(page.as_uri())
    return 0 if result['status'] in {'SOFTWARE_PREPARED_IDLE', 'OFFLINE_BUNDLE_READY', 'STATIONARY_CHECK_PASS'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
