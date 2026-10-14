# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One bounded, no-motion robot readiness collection; no demo/motion approval.

Default is offline. --run explicitly permits the existing preparation/deployment
and stationary collector in sequence. It never starts LiDAR or commands motion.
"""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import subprocess
import sys
import uuid
import webbrowser

from check_robot_connection import ROOT
from prepare_robot import bundle


REPORT_PREFIX = 'Report: '
EXPECTED_CLIENT_SCHEMA = 'robot-prepare-1.0'
STEPS = ('offline_collection_preflight', 'source_and_idle', 'stationary_collection', 'evidence_review')


def _offline_preflight():
    from rehearse_robot_demo_offline import cached_collection_preflight, prepare_collection_preflight
    return cached_collection_preflight() or prepare_collection_preflight()


def _invoke(mode, output_root, host, identity_file, allow_torque_off, runner, candidate=None):
    command = [sys.executable, str(ROOT / 'scripts/prepare_robot.py'), '--mode', mode,
               '--host', host, '--identity-file', str(identity_file)]
    if getattr(sys, 'frozen', False):
        from twinpulse_app.runtime_paths import script_command
        command = script_command(ROOT, 'robot-prepare') + ['--mode', mode, '--host', host, '--identity-file', str(identity_file)]
    if output_root.resolve() != (ROOT / 'artifacts').resolve():
        command += ['--output-root', str(output_root)]
    if mode == 'prepare' and allow_torque_off:
        command.extend(('--disable-torque', '--operator-confirmed-flat-clear-floor'))
    if candidate is not None:
        command.extend(('--candidate', str(candidate)))
    completed = runner(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=360 if mode == 'prepare' else 90, check=False)
    stdout = completed.stdout.decode('utf-8', errors='replace')
    paths = [line[len(REPORT_PREFIX):].strip() for line in stdout.splitlines()
             if line.startswith(REPORT_PREFIX)]
    if len(paths) != 1:
        raise ValueError('CLIENT_REPORT_PATH_MISSING_OR_AMBIGUOUS')
    report_path = Path(paths[0]).resolve()
    expected_root = (output_root / 'robot-preparation').resolve()
    if not report_path.is_relative_to(expected_root) or report_path.name != 'report.html':
        raise ValueError('CLIENT_REPORT_PATH_OUTSIDE_EXPECTED_ROOT')
    data = json.loads(report_path.with_name('report.json').read_text(encoding='utf-8'))
    if data.get('schema_version') != EXPECTED_CLIENT_SCHEMA or data.get('motion_authorized') is not False:
        raise ValueError('CLIENT_REPORT_CONTRACT_INVALID')
    return {'exit_code': completed.returncode, 'report': data,
            'report_path': str(report_path.with_name('report.json'))}


def _evidence(stationary):
    observation = stationary.get('stationary', {}).get('observation', {})
    passive = observation.get('passive_ros', {})
    result = {}
    for name in ('odom', 'scan'):
        status = passive.get('status', {}).get(name, 'NOT_RECORDED')
        reason = passive.get('missing_reason', {}).get(name)
        faults = passive.get('fault_counts', {}).get(name, {})
        result[name] = {'status': status, 'reason': reason,
                        'fault_counts': faults,
                        'publisher': passive.get('endpoints', {}).get(name, {})}
    for name in ('tf', 'tf_static'):
        result[name] = {'status': passive.get(name + '_status', 'NOT_RECORDED'),
                        'publisher': passive.get('endpoints', {}).get(name, {})}
    result['capture_errors'] = passive.get('capture_errors', [])
    result['frame_diagnostic'] = _frame_diagnostic(passive)
    result['room_alignment'] = 'NOT_VERIFIED'
    result['ros_lidar_lifecycle'] = 'NOT_RUN: COIN driver is never auto-started'
    result['autonomous_motion'] = 'LOCKED'
    return result


def _frame_diagnostic(passive):
    """Explain the bounded passive sample without granting a TF/calibration claim."""
    status = passive.get('status', {})
    faults = passive.get('fault_counts', {})
    examples = passive.get('examples_by_fault', {})
    endpoints = passive.get('endpoints', {})
    diagnosis = {'alignment_verified': False, 'room_to_odom': 'NOT_CAPTURED',
                 'odom': {}, 'scan': {}, 'tf': {}}
    for kind in ('odom', 'scan'):
        state = status.get(kind, 'NOT_RECORDED')
        publisher = endpoints.get(kind, {}).get('publisher_count')
        item = {'status': state, 'publisher_count': publisher,
                'fault_counts': faults.get(kind, {})}
        if state == 'NOT_RECEIVED':
            item['cause'] = ('NO_PUBLISHER' if publisher == 0 else
                             'NO_MESSAGE_WITH_PUBLISHER' if isinstance(publisher, int) and publisher > 0 else
                             'DISCOVERY_UNAVAILABLE')
        elif state == 'REJECTED':
            item['cause'] = 'ALL_CAPTURED_SAMPLES_REJECTED'
            item['examples_by_fault'] = {code: {'frame_id': sample.get('frame_id'),
                                                'child_frame_id': sample.get('child_frame_id'),
                                                'stamp_sec': sample.get('stamp_sec')}
                                         for code, sample in examples.get(kind, {}).items()
                                         if isinstance(sample, dict)}
        elif state == 'SAMPLES_ACCEPTED_UNALIGNED':
            sample = passive.get('latest', {}).get(kind)
            if isinstance(sample, dict) and sample.get('fault') == 'NONE':
                item['observed_frame_id'] = sample.get('frame_id')
                if kind == 'odom':
                    item['observed_child_frame_id'] = sample.get('child_frame_id')
            item['cause'] = 'SAMPLES_ACCEPTED_BUT_ALIGNMENT_UNVERIFIED'
        diagnosis[kind] = item
    pairs = passive.get('tf_first', [])
    diagnosis['tf'] = {
        'dynamic_status': passive.get('tf_status', 'NOT_RECORDED'),
        'static_status': passive.get('tf_static_status', 'NOT_RECORDED'),
        'dynamic_publisher_count': endpoints.get('tf', {}).get('publisher_count'),
        'static_publisher_count': endpoints.get('tf_static', {}).get('publisher_count'),
        'bounded_pairs': [{'parent': pair.get('frame_id'), 'child': pair.get('child_frame_id'),
                           'topic': pair.get('topic')} for pair in pairs[:8] if isinstance(pair, dict)],
        'interpretation': 'OBSERVED_UNVALIDATED_NOT_CALIBRATION' if pairs else
                          'NO_PUBLISHER' if (endpoints.get('tf', {}).get('publisher_count') == 0 and
                                             endpoints.get('tf_static', {}).get('publisher_count') == 0) else
                          'NOT_OBSERVED_IN_BOUNDED_SAMPLE'}
    return diagnosis


def _gaps(evidence):
    gaps = []
    if evidence['odom']['status'] != 'SAMPLES_ACCEPTED_UNALIGNED':
        gaps.append('odom=' + evidence['odom']['status'])
    if evidence['scan']['status'] != 'SAMPLES_ACCEPTED_UNALIGNED':
        gaps.append('scan=' + evidence['scan']['status'] +
                    (':' + evidence['scan']['reason'] if evidence['scan']['reason'] else ''))
    if evidence['tf']['status'] == 'NOT_RECEIVED' and evidence['tf_static']['status'] == 'NOT_RECEIVED':
        gaps.append('tf=NOT_RECEIVED')
    if evidence['capture_errors']:
        gaps.append('capture_errors=' + ','.join(evidence['capture_errors'][:4]))
    return gaps


def collect(*, run=False, host='192.168.35.139', identity_file=None,
            allow_torque_off=False, flat_clear_confirmed=False,
            output_root=None, runner=subprocess.run, offline_preflight=None, candidate=None):
    """Return one receipt; never retry a failed stage or silently start a device."""
    if allow_torque_off != flat_clear_confirmed:
        raise ValueError('TORQUE_OFF_REQUIRES_EXPLICIT_FLAT_CLEAR_CONFIRMATION')
    if allow_torque_off and not run:
        raise ValueError('TORQUE_OFF_REQUIRES_RUN')
    root = output_root or ROOT / 'artifacts'
    out = root / 'robot-readiness' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                                      + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 'robot-readiness-1.0', 'status': 'STARTED',
              'scope': 'NO_MOTION_COLLECTION', 'motion_authorized': False,
              'run_requested': run, 'steps': {name: {'status': 'NOT_RUN'} for name in STEPS},
              'demo_ready': False,
              'remaining_gates': {
                  'ros_lidar_driver_and_physical_stop': 'NOT_RUN_SEPARATE_APPROVAL',
                  'sensor_chassis_room_alignment': 'NOT_VERIFIED',
                  'local_collision_protection': 'NOT_VERIFIED',
                  'scoped_autonomous_mission': 'LOCKED'}}
    try:
        if not run:
            archive = out / 'source.tar'
            result['steps']['source_and_idle'] = {
                'status': 'OFFLINE_SOURCE_BUNDLED', 'bundle_sha256': bundle(archive)}
            result['status'] = 'OFFLINE_ONLY'
            result['reason'] = 'No robot connection or deployment was requested'
            return result, out
        result['steps']['offline_collection_preflight'] = {'status': 'RUNNING'}
        print('Checking cached collection-only PC preflight before SSH; demo gates remain locked...', flush=True)
        if candidate is not None:
            from robot_field_candidate import checked
            frozen = checked(ROOT, candidate)
            offline = frozen['preflight']
        else:
            offline = (offline_preflight or _offline_preflight)()
        print('PC preflight: ' + offline.get('pc_cache', 'INJECTED') + ' / ' + offline['status'], flush=True)
        result['offline_collection_preflight'] = offline
        result['steps']['offline_collection_preflight'] = {'status': offline['status']}
        if offline['status'] != 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED':
            result['status'] = 'STOPPED_AT_OFFLINE_PREFLIGHT'
            result['reason'] = 'A local code/contract gate failed before robot contact'
            return result, out
        if offline_preflight is None:
            from rehearse_robot_demo_offline import collection_fingerprint
            if offline.get('pc_fingerprint') != collection_fingerprint():
                result['status'] = 'STOPPED_AT_OFFLINE_PREFLIGHT'
                result['reason'] = 'PC source changed after the collection contract check'
                return result, out
        identity_file = identity_file or Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation'
        for mode, step in (('prepare', 'source_and_idle'), ('stationary', 'stationary_collection')):
            result['steps'][step] = {'status': 'RUNNING'}
            print('Running ' + step + ' (bounded, no movement command)...', flush=True)
            receipt = (_invoke(mode, root, host, identity_file, allow_torque_off, runner,
                               candidate=candidate) if candidate is not None else
                       _invoke(mode, root, host, identity_file, allow_torque_off, runner))
            child = receipt['report']
            if (candidate is not None and child.get('status') in {'SOFTWARE_PREPARED_IDLE', 'STATIONARY_CHECK_PASS'}
                    and child.get('release_id') != frozen['source_id']):
                result['status'] = 'CANDIDATE_RELEASE_MISMATCH'
                result['reason'] = 'Prepared robot release differs from the checked candidate'
                result['steps'][step] = {'status': 'FAILED', 'reason': result['reason']}
                return result, out
            nested = child.get('stationary', {})
            reason = child.get('reason') or nested.get('reason') or nested.get('cleanup_error')
            if not reason and child.get('status') == 'PREPARED_NEEDS_ATTENTION':
                issues = child.get('health', {}).get('issues', [])
                if isinstance(issues, list):
                    reason = '; '.join(str(issue)[:160] for issue in issues[:4] if isinstance(issue, str)) or None
            if not reason and child.get('status') == 'EVIDENCE_EXPORT_INCOMPLETE':
                files = child.get('evidence_export', {}).get('files', {})
                if isinstance(files, dict):
                    missing = [str(name)[:80] + '=' + str(item.get('status'))[:80]
                               for name, item in files.items()
                               if isinstance(item, dict) and item.get('status') != 'COPIED']
                    reason = 'Evidence export incomplete: ' + ', '.join(missing[:5]) if missing else None
            result['steps'][step] = {'status': child.get('status', 'UNKNOWN'),
                                     'exit_code': receipt['exit_code'],
                                     'report_path': receipt['report_path'],
                                     'reason': reason,
                                     'failure_diagnostics': child.get('failure_diagnostics') or nested.get('diagnostics')}
            if mode == 'stationary':
                # Transport failure must not hide independently acquired ROS
                # diagnostics. Retain the failed transfer and original verdict.
                result['evidence_export'] = child.get('evidence_export')
                result['stationary_status'] = child.get('stationary_status',child.get('status'))
                if nested.get('observation'):
                    observed = _evidence(child)
                    matched=(child.get('boot_id')==prior.get('boot_id') and child.get('release_id')==prior.get('release_id'))
                    result['evidence' if matched else 'unbound_evidence'] = observed
                    gaps = _gaps(observed)
                    result['steps']['evidence_review'] = {
                        'status': 'REJECTED_IDENTITY' if not matched else 'EVIDENCE_GAPS' if gaps else 'CAPTURED_UNALIGNED',
                        'reason': '; '.join(gaps) if gaps else None}
            if receipt['exit_code'] != 0 or child.get('status') != (
                    'SOFTWARE_PREPARED_IDLE' if mode == 'prepare' else 'STATIONARY_CHECK_PASS'):
                result['status'] = 'STOPPED_AT_' + step.upper()
                result['reason'] = reason or child.get('status', 'UNKNOWN')
                return result, out
            print(step + ': ' + child['status'], flush=True)
            if mode == 'prepare':
                prior = child
                result['boot_id'] = child.get('boot_id')
                result['release_id'] = child.get('release_id')
            else:
                if (not prior.get('boot_id') or not prior.get('release_id')
                        or child.get('boot_id') != prior['boot_id']
                        or child.get('release_id') != prior['release_id']):
                    result['status'] = 'BOOT_OR_RELEASE_CHANGED'
                    result['reason'] = 'Stationary evidence is not bound to the prepared boot/release'
                    return result, out
                result['evidence'] = _evidence(child)
        gaps = _gaps(result['evidence'])
        result['steps']['evidence_review'] = {'status': 'EVIDENCE_GAPS' if gaps else 'CAPTURED_UNALIGNED',
                                               'reason': '; '.join(gaps) if gaps else None}
        result['status'] = 'EVIDENCE_GAPS' if gaps else 'NO_MOTION_COLLECTION_COMPLETE'
        return result, out
    except subprocess.TimeoutExpired:
        result['status'] = 'REMOTE_STATE_UNKNOWN'
        result['reason'] = 'Local timeout; remote cleanup must be verified before another operation'
        return result, out
    except (Exception, KeyboardInterrupt) as exc:
        result['status'] = 'INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'COLLECTION_FAILED'
        result['reason'] = type(exc).__name__ + ': ' + str(exc)[:300]
        return result, out
    finally:
        if run:
            # No unsafe dependent collection after failed preparation. Explain
            # why it was skipped instead of leaving an ambiguous empty result.
            for step in STEPS:
                if result['steps'][step]['status']=='NOT_RUN':
                    result['steps'][step]['reason']='DEPENDENCY_NOT_SATISFIED: '+result['status']


def save(result, out):
    (out / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                               allow_nan=False), encoding='utf-8')
    rows = ''.join('<tr><th>' + html.escape(name) + '</th><td>' +
                   html.escape(step['status']) + '</td><td>' +
                   html.escape(str(step.get('reason') or '')) + '</td></tr>'
                   for name, step in result['steps'].items())
    diagnostic = result.get('evidence', {}).get('frame_diagnostic', {})
    diagnostic_rows = ''.join(
        '<tr><th>' + html.escape(kind) + '</th><td>' +
        html.escape(str(diagnostic.get(kind, {}).get('status') or
                        diagnostic.get(kind, {}).get('interpretation') or 'NOT_RECORDED')) +
        '</td><td>' + html.escape(str(diagnostic.get(kind, {}).get('cause') or
                                     diagnostic.get(kind, {}).get('interpretation') or '')) + '</td></tr>'
        for kind in ('odom', 'scan', 'tf'))
    diagnostic_table = ('<h2>Passive sensor/frame diagnosis (not calibration)</h2>'
                        '<table><tr><th>Source</th><th>Observed</th><th>Likely category</th></tr>' +
                        diagnostic_rows + '</table>') if diagnostic else ''
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Robot readiness</title>'
            '<style>body{font:18px Arial;max-width:960px;margin:32px auto;padding:16px;'
            'background:#101722;color:#e4eef8}table{width:100%;border-collapse:collapse}'
            'td,th{border:1px solid #526476;padding:12px;text-align:left}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1e2c40;padding:16px}</style>'
            '<h1>Robot no-motion readiness collection</h1><p>Status: <strong>' +
            html.escape(result['status']) + '</strong></p><p>Demo ready: NO · Motion locked. '
            'No autonomous movement or ROS LiDAR driver is started. Remaining gates are separate.</p><table>' + rows +
            '</table>' + diagnostic_table + '<pre>' +
            html.escape(json.dumps(result, ensure_ascii=False, indent=2)) +
            '</pre></html>')
    path = out / 'report.html'
    path.write_text(page, encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='One bounded preparation + stationary collection; may deploy reviewed source')
    parser.add_argument('--host', default='192.168.35.139')
    parser.add_argument('--identity-file', type=Path)
    parser.add_argument('--allow-torque-off', action='store_true', help='Explicitly permit one OFF-only action during prepare')
    parser.add_argument('--operator-confirmed-flat-clear-floor', action='store_true')
    parser.add_argument('--open-report', action='store_true')
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    if args.allow_torque_off != args.operator_confirmed_flat_clear_floor or (args.allow_torque_off and not args.run):
        parser.error('Torque OFF requires --run and both explicit OFF/floor flags')
    result, out = collect(run=args.run, host=args.host, identity_file=args.identity_file, output_root=args.output_root,
                          allow_torque_off=args.allow_torque_off,
                          flat_clear_confirmed=args.operator_confirmed_flat_clear_floor)
    page = save(result, out)
    print('Status: ' + result['status'])
    print('Report: ' + str(page))
    if args.open_report:
        webbrowser.open(page.as_uri())
    return 0 if result['status'] in {'OFFLINE_ONLY', 'NO_MOTION_COLLECTION_COMPLETE'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
