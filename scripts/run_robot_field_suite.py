# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Single entry for offline checks and one explicitly scoped robot field session.

Default is robot-OFF analysis. --field-run permits only the reviewed, bounded
existing preparation, stationary, fixed qualification and isolated ROS scan.
No autonomous mission, retry, threshold relaxation, or silent PASS promotion.
Independent read-only/evidence checks continue after a dependent stage fails.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_robot_connection import ROOT, collect_readonly

REPORT_SCHEMA = 'robot-field-suite-1.0'
STAGES = ('offline_contracts', 'saved_evidence', 'initial_health', 'prepare_stationary',
          'pre_motion_health', 'qualification', 'same_window_capture',
          'post_motion_health', 'ros_scan', 'final_health')


def board_safe_for_sensor(health):
    board = health.get('health', {}).get('board', {})
    voltage = board.get('voltage_v')
    return (type(voltage) in (int, float) and math.isfinite(voltage)
            and board.get('status') == 'OBSERVED' and voltage > 11.1
            and board.get('torque_enabled') is False
            and board.get('wheel_velocity_raw') == [0, 0]
            and board.get('command_bytes_zero') is True)


def board_safe_for_motion(health):
    board = health.get('health', {}).get('board', {})
    # User reserve uses the public OpenCR display mapping. Do not reintroduce
    # the superseded arbitrary 11.4V (~50%) margin. The >11.1V source guard
    # remains independent and takes priority before the estimated 20% reserve.
    return (board_safe_for_sensor(health)
            and max(0.,min(100.,(board['voltage_v']-10.5)/1.8*100))>20)


def same_boot_release(health, binding):
    observed = health.get('health', {})
    deployment = observed.get('deployment')
    return (isinstance(binding.get('boot_id'), str) and
            observed.get('boot_id') == binding['boot_id'] and
            isinstance(deployment, dict) and
            deployment.get('release_id') == binding.get('release_id'))


def inspect_saved(paths):
    sys.path.insert(0, str(ROOT / 'packages/twinpulse_robot_safety'))
    from raw_ros_record import inspect_recording
    rows = []
    for path in paths:
        raw = Path(path).resolve()
        row = {'path': str(raw), 'status': 'FAILED'}
        try:
            if raw.name != 'ros-messages.raw' or raw.is_symlink():
                raise ValueError('EXPECTED_NAMED_RAW_FILE')
            frames = inspect_recording(raw)
            row.update(status='RAW_BYTES_VERIFIED_NOT_PHYSICAL', frames=len(frames),
                       topics={name: sum(meta['topic'] == name for meta, _ in frames)
                               for name in ('odom', 'scan', '/tf', '/tf_static')})
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            row['reason'] = type(exc).__name__ + ':' + str(exc)[:160]
        rows.append(row)
    return rows


def _preflight():
    from run_robot_readiness import _offline_preflight
    base = _offline_preflight()
    # The older collection preflight does not exercise the newly combined
    # driver/qualification/export path. Fail before SSH if that path regresses.
    environment = dict(os.environ)
    environment['PYTHONPATH'] = os.pathsep.join((
        str(ROOT / 'packages/twinpulse_app/src'),
        str(ROOT / 'packages/twinpulse_core/src'),
        str(ROOT / 'packages/twinpulse_provider/src'),
        environment.get('PYTHONPATH', '')))
    command = [sys.executable, '-B', '-m', 'unittest', '-q',
               'tests.integration.test_same_window_ros',
               'tests.integration.test_robot_field_suite',
               'tests.integration.test_robot_field_candidate',
               'tests.integration.test_coin_target_build',
               'tests.integration.test_ros_scan_client',
               'tests.integration.test_physical_controller',
               'packages.twinpulse_robot_safety.tests.teleop_test',
               'packages.twinpulse_robot_safety.tests.test_isolated_ros_scan',
               'packages.twinpulse_robot_safety.tests.test_raw_ros_record']
    try:
        check = subprocess.run(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=120, check=False)
        tail = (check.stdout + check.stderr).decode('utf-8', 'replace')[-2500:]
        focused = {'status': 'PASS' if check.returncode == 0 and 'Ran ' in tail else 'FAILED',
                   'exit_code': check.returncode, 'diagnostic_tail': tail}
    except (OSError, subprocess.TimeoutExpired) as exc:
        focused = {'status': 'FAILED', 'reason': type(exc).__name__ + ':' + str(exc)[:160]}
    return {**base, 'field_suite_contracts': focused,
            'status': ('COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'
                       if base.get('status') == 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'
                       and focused['status'] == 'PASS' else 'COLLECTION_REVIEW_REQUIRED')}


def _stationary(host, key, allow_off, candidate=None):
    from run_robot_readiness import collect, save
    result, out = collect(run=True, host=host, identity_file=key,
                          allow_torque_off=allow_off, flat_clear_confirmed=allow_off,
                          candidate=candidate)
    save(result, out)
    return result, out


def _qualification(output=None):
    command = [sys.executable, '-B', str(ROOT / 'scripts/run_supervised_odom_qualification.py')]
    def retain(stdout, stderr):
        if output is None:
            return {}
        kept = {}
        for name, data in (('stdout', stdout), ('stderr', stderr)):
            value = data or b''
            path = Path(output) / ('qualification.' + name)
            path.write_bytes(value[:2 * 1024 * 1024])
            kept[name + '_path'] = str(path)
            kept[name + '_bytes'] = len(value)
            kept[name + '_truncated'] = len(value) > 2 * 1024 * 1024
        return kept
    try:
        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=300, check=False)
    except subprocess.TimeoutExpired as exc:
        return {'status': 'REMOTE_STATE_UNKNOWN',
                'reason': 'QUALIFICATION_PC_PROCESS_TIMEOUT_REMOTE_STATE_UNKNOWN',
                **retain(exc.stdout, exc.stderr)}
    transport = retain(completed.stdout, completed.stderr)
    lines = [line for line in completed.stdout.decode('utf-8', 'replace').splitlines()
             if line.startswith('{') and '"job_id"' in line]
    if len(lines) != 1:
        return {'status': 'REMOTE_STATE_UNKNOWN' if completed.returncode else 'FAILED',
                'reason': 'QUALIFICATION_REPORT_MISSING_OR_AMBIGUOUS',
                'exit_code': completed.returncode, **transport}
    data = json.loads(lines[0])
    diagnosis = {}
    robot_boot = None
    robot_release = None
    job = data.get('job_id')
    if isinstance(job, str) and len(job) == 32 and all(c in '0123456789abcdef' for c in job):
        saved = ROOT / 'artifacts/manual-control' / job / 'robot-report.json'
        try:
            robot = json.loads(saved.read_text(encoding='utf-8'))
            if robot.get('mode') == 'qualify_scan' and isinstance(robot.get('telemetry_tail'), list):
                robot_boot, robot_release = robot.get('boot_id'), robot.get('release_id')
                rows = [row for row in robot['telemetry_tail'] if isinstance(row, dict)]
                voltages = [row['voltage_v'] for row in rows
                            if type(row.get('voltage_v')) in (int, float)
                            and math.isfinite(row['voltage_v'])]
                ages = [row['source_age_s'] for row in rows
                        if type(row.get('source_age_s')) in (int, float)
                        and math.isfinite(row['source_age_s'])]
                diagnosis = {'robot_report_path': str(saved),
                             'robot_reason': robot.get('reason'),
                             'minimum_recorded_voltage_v': min(voltages) if voltages else None,
                             'maximum_recorded_source_age_s': max(ages) if ages else None,
                             'voltage_guard_crossed_in_saved_tail': bool(voltages and min(voltages) <= 11.1),
                             'button_state_from_tail': 'NOT_RECORDED'}
                from inspect_same_window_ros import inspect as inspect_same_window
                export_path = saved.parent / 'robot-evidence' / 'export.json'
                try:
                    receipt = json.loads(export_path.read_text(encoding='utf-8'))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    receipt = {}
                diagnosis['same_window'] = inspect_same_window(
                    robot, saved.parent / 'robot-evidence' / 'ros-messages.raw', receipt)
                diagnosis['scan_driver_cleanup'] = robot.get('scan_driver_cleanup')
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            diagnosis = {'robot_report_path': str(saved), 'status': 'UNAVAILABLE_OR_INVALID'}
    return {'status': 'QUALIFIED' if completed.returncode == 0 and
            data.get('state') == 'FINISHED' and data.get('result') == 'QUALIFIED' and
            data.get('cleanup_confirmed') is True else 'FAILED',
            'exit_code': completed.returncode, 'result': data,
            'reason': data.get('reason') or data.get('result'), 'diagnosis': diagnosis,
            'robot_boot_id': robot_boot, 'robot_release_id': robot_release,
            **transport}


def run_suite(*, field_run=False, operator_watching=False, clear_floor=False,
              allow_torque_off=False, allow_fixed_motion_and_scan=False,
              host='192.168.35.139', identity_file=None, saved_raw=(),
              output=None, preflight=_preflight, health=collect_readonly,
              stationary=_stationary, qualification=_qualification,
              scan=None, candidate=None):
    if field_run and (not operator_watching or not clear_floor):
        raise ValueError('FIELD_RUN_REQUIRES_CURRENT_OPERATOR_AND_CLEAR_FLOOR')
    if (allow_torque_off or allow_fixed_motion_and_scan) and not field_run:
        raise ValueError('PHYSICAL_SCOPE_REQUIRES_FIELD_RUN')
    if allow_fixed_motion_and_scan and (host != '192.168.35.139' or identity_file is not None):
        raise ValueError('FIXED_QUALIFICATION_TARGET_AND_KEY_CANNOT_BE_OVERRIDDEN')
    # The readiness/scan/qualification paths already use this pinned key.  The
    # first read-only board check must use the same identity, or an otherwise
    # valid field session stops at passwordless SSH before collecting anything.
    field_identity = identity_file or Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation'
    out = Path(output or ROOT / 'artifacts/robot-field-suite' /
               (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]))
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': REPORT_SCHEMA, 'status': 'STARTED', 'demo_ready': False,
              'autonomous_motion_authorized': False, 'field_run': field_run,
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'unresolved_demo_gates': {
                  'same_window_moving_scan_odom_tf': 'OFFLINE_IMPLEMENTED_LIVE_UNVERIFIED',
                  'sensor_to_base_and_room_to_odom': 'NOT_VERIFIED',
                  'physical_lidar_rotor_stop': 'NOT_MACHINE_VERIFIED',
                  'live_collision_guard_and_autonomous_mission': 'LOCKED'},
              'stages': {name: {'status': 'NOT_RUN'} for name in STAGES}}

    def save():
        (out / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                     allow_nan=False), encoding='utf-8')

    def put(name, status, **detail):
        result['stages'][name] = {'status': status, **detail}
        save()

    def health_check(name):
        try:
            observed = health(host, 'twinpulse', identity_file=field_identity, batch=True)
            put(name, 'OBSERVED' if observed.get('health', {}).get('board', {}).get('status') ==
                'OBSERVED' else 'FAILED', reason=observed.get('reason') or observed.get('status'),
                observation=observed)
            return observed
        except (Exception, KeyboardInterrupt) as exc:
            put(name, 'FAILED', reason=type(exc).__name__ + ':' + str(exc)[:160])
            return {}

    save()
    try:
        # Local evidence validation is independent, including when preflight fails.
        rows = inspect_saved(saved_raw)
        put('saved_evidence', 'NOT_REQUESTED' if not rows else
            'VERIFIED' if all(row['status'].startswith('RAW_BYTES_VERIFIED')
                              for row in rows) else 'FAILED', files=rows)
        try:
            if candidate is not None:
                from robot_field_candidate import checked
                frozen = checked(ROOT, candidate)
                result['candidate'] = {'manifest': str(candidate), 'source_id': frozen['source_id']}
                offline = frozen['preflight']
            else:
                offline = preflight()
            put('offline_contracts', 'PASS' if offline.get('status') ==
                'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED' else 'FAILED', result=offline)
        except (Exception, KeyboardInterrupt) as exc:
            put('offline_contracts', 'FAILED', reason=type(exc).__name__ + ':' + str(exc)[:160])
        if not field_run:
            for name in STAGES[2:]:
                put(name, 'SKIPPED', reason='ROBOT_OFF_OFFLINE_MODE')
            result['status'] = 'OFFLINE_REVIEW_DEMO_LOCKED'
            return result, out
        if result['stages']['offline_contracts']['status'] != 'PASS':
            for name in STAGES[2:]:
                put(name, 'SKIPPED', reason='PC_CONTRACTS_FAILED_BEFORE_SSH')
            result['status'] = 'FIELD_BLOCKED_PC_PREFLIGHT'
            return result, out

        first = health_check('initial_health')
        board = first.get('health', {}).get('board', {})
        voltage = board.get('voltage_v')
        wheels = board.get('wheel_velocity_raw')
        if (board.get('status') != 'OBSERVED' or wheels != [0, 0] or
                board.get('command_bytes_zero') is not True or
                type(board.get('torque_enabled')) is not bool):
            put('prepare_stationary', 'SKIPPED', reason='BOARD_UNKNOWN_OR_NONZERO_COMMAND')
        elif type(voltage) not in (int, float) or not math.isfinite(voltage) or voltage <= 11.1:
            put('prepare_stationary', 'SKIPPED', reason='VOLTAGE_AT_OR_BELOW_EXISTING_GUARD')
        elif board.get('torque_enabled') and not allow_torque_off:
            put('prepare_stationary', 'SKIPPED', reason='TORQUE_ON_OFF_NOT_IN_APPROVED_SCOPE')
        else:
            try:
                off = allow_torque_off and board.get('torque_enabled') is True
                prepared, child_dir = (stationary(host, identity_file, off, candidate=candidate)
                    if candidate is not None and stationary is _stationary else
                    stationary(host, identity_file, off))
                steps = prepared.get('steps', {})
                stage_ok = (steps.get('source_and_idle', {}).get('status') == 'SOFTWARE_PREPARED_IDLE'
                            and steps.get('stationary_collection', {}).get('status') == 'STATIONARY_CHECK_PASS'
                            and prepared.get('boot_id') and prepared.get('release_id')
                            and (candidate is None or prepared.get('release_id') == frozen['source_id']))
                put('prepare_stationary', 'PASS' if stage_ok else 'FAILED',
                    report_path=str(child_dir / 'report.json'), result=prepared)
            except (Exception, KeyboardInterrupt) as exc:
                put('prepare_stationary', 'REMOTE_STATE_UNKNOWN' if isinstance(exc, subprocess.TimeoutExpired)
                    else 'FAILED', reason=type(exc).__name__ + ':' + str(exc)[:160])

        prepared = result['stages']['prepare_stationary']
        binding = prepared.get('result', {})
        can_act = (prepared['status'] == 'PASS' and allow_fixed_motion_and_scan)
        if can_act:
            mid = health_check('pre_motion_health')
        else:
            mid = {}
            put('pre_motion_health', 'SKIPPED', reason='NO_PREPARED_SCOPED_ACTION')
        if can_act and board_safe_for_motion(mid) and same_boot_release(mid, binding):
            try:
                if candidate is not None:
                    from robot_field_candidate import checked
                    checked(ROOT, candidate)
                qualified = qualification(out) if qualification is _qualification else qualification()
                if (qualified.get('status') == 'QUALIFIED' and
                        (qualified.get('robot_boot_id') != binding['boot_id'] or
                         qualified.get('robot_release_id') != binding['release_id'])):
                    qualified = dict(qualified, status='FAILED', reason='QUALIFICATION_BOOT_RELEASE_MISMATCH')
                put('qualification', qualified['status'], result=qualified)
            except (Exception, KeyboardInterrupt) as exc:
                put('qualification', 'REMOTE_STATE_UNKNOWN' if isinstance(exc, subprocess.TimeoutExpired)
                    else 'FAILED', reason=type(exc).__name__ + ':' + str(exc)[:160])
        else:
            put('qualification', 'SKIPPED', reason='PREP_SCOPE_FRESH_11_4V_OR_BOOT_RELEASE_NOT_MET')
        same_window = result['stages']['qualification'].get('result', {}).get('diagnosis', {}).get('same_window')
        if isinstance(same_window, dict):
            put('same_window_capture', same_window['status'], result=same_window,
                reason=same_window.get('reason'))
            if same_window['status'] == 'COMMAND_WINDOW_RAW_CAPTURED_UNALIGNED':
                result['unresolved_demo_gates']['same_window_moving_scan_odom_tf'] = (
                    'COMMAND_WINDOW_RAW_CAPTURED_NOT_FLOOR_MOTION_OR_CALIBRATION')
        else:
            put('same_window_capture', 'SKIPPED', reason='NO_COMBINED_QUALIFICATION_EVIDENCE')

        # A fresh read is required after an attempted motion, but do not re-query
        # unchanged state merely to fill a report column.
        if result['stages']['qualification']['status'] != 'SKIPPED':
            post = health_check('post_motion_health')
        else:
            post = mid
            put('post_motion_health', 'SKIPPED', reason='NO_MOTION_ATTEMPT_REUSE_PREMOTION_READ')
        qual = result['stages']['qualification']
        scan_cleanup = qual.get('result', {}).get('diagnosis', {}).get('scan_driver_cleanup')
        if isinstance(scan_cleanup, dict):
            captured = same_window.get('full_session_counts', {}).get('scan', 0) if isinstance(same_window, dict) else 0
            stop = scan_cleanup.get('sensor_stop', {})
            stop_ok = (stop.get('write_complete') is True and stop.get('quiet_after_1s') is True
                       and stop.get('port_restored') is True)
            put('ros_scan', 'SAME_SESSION_RAW_CAPTURED' if captured and stop_ok else 'NEEDS_REVIEW',
                reason='NO_AUTOMATIC_SECOND_DRIVER_RUN' if captured and stop_ok else
                       'SCAN_MISSING_OR_DRIVER_STOP_UNCONFIRMED_NO_RETRY',
                result={'scan_frames': captured, 'scan_driver_cleanup': scan_cleanup})
        elif qual['status'] == 'REMOTE_STATE_UNKNOWN':
            put('ros_scan', 'SKIPPED', reason='QUALIFICATION_REMOTE_STATE_UNKNOWN')
        elif (qual['status'] != 'SKIPPED' and
              (qual.get('result', {}).get('robot_boot_id') != binding.get('boot_id') or
               qual.get('result', {}).get('robot_release_id') != binding.get('release_id'))):
            put('ros_scan', 'SKIPPED', reason='QUALIFICATION_BOOT_RELEASE_MISMATCH')
        elif (qual['status'] == 'FAILED' and
              qual.get('result', {}).get('result', {}).get('cleanup_confirmed') is not True):
            put('ros_scan', 'SKIPPED', reason='QUALIFICATION_CLEANUP_NOT_CONFIRMED')
        elif (qual.get('result', {}).get('diagnosis', {}).get('voltage_guard_crossed_in_saved_tail')
              or qual.get('result', {}).get('reason') == 'BATTERY_BUTTON_OR_SOURCE_AGE'):
            put('ros_scan', 'SKIPPED', reason='QUALIFICATION_BATTERY_OR_SENSOR_FRESHNESS_FAILURE')
        elif can_act and board_safe_for_sensor(post) and same_boot_release(post, binding) and scan is not None:
            try:
                scan_receipt, scan_dir = scan(host=host, identity_file=identity_file,
                                              expected_boot=binding['boot_id'],
                                              expected_release=binding['release_id'])
                put('ros_scan', scan_receipt['status'], report_path=str(scan_dir / 'receipt.json'),
                    result=scan_receipt)
            except (Exception, KeyboardInterrupt) as exc:
                put('ros_scan', 'REMOTE_STATE_UNKNOWN' if isinstance(exc, subprocess.TimeoutExpired)
                    else 'FAILED', reason=type(exc).__name__ + ':' + str(exc)[:160])
        else:
            put('ros_scan', 'SKIPPED', reason='PREP_SCOPE_BOARD_IDLE_VOLTAGE_OR_SCAN_CLIENT_NOT_READY')
        if prepared['status'] == 'SKIPPED':
            put('final_health', 'SKIPPED', reason='NO_STATE_CHANGING_STAGE_NO_AUTO_RETRY')
        else:
            health_check('final_health')
        result['status'] = 'FIELD_PARTIAL_DEMO_LOCKED'
        return result, out
    finally:
        # A control failure does not erase completed independent diagnostics.
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        result['issues'] = [{'stage': name, 'status': item['status'],
                             'reason': item.get('reason') or item.get('result', {}).get('reason')}
                            for name, item in result['stages'].items()
                            if item['status'] in {'FAILED', 'REMOTE_STATE_UNKNOWN', 'NEEDS_REVIEW', 'INCOMPLETE'}
                            or (field_run and item['status'] == 'SKIPPED')]
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field-run', action='store_true', help='One explicit field session; default robot OFF')
    parser.add_argument('--prepare-field-candidate', action='store_true',
                        help='Robot-OFF: check local contracts and freeze source for one later field session')
    parser.add_argument('--candidate', type=Path,
                        help='Prepared manifest; changed/expired inputs are rejected before SSH')
    parser.add_argument('--operator-watching', action='store_true')
    parser.add_argument('--clear-floor', action='store_true')
    parser.add_argument('--allow-torque-off', action='store_true')
    parser.add_argument('--allow-fixed-motion-and-scan', action='store_true',
                        help='One existing fixed qualification and one bounded isolated ROS scan; no retries')
    parser.add_argument('--host', default='192.168.35.139')
    parser.add_argument('--identity-file', type=Path)
    parser.add_argument('--saved-raw', type=Path, action='append', default=[])
    parser.add_argument('--adaptive-preflight', action='store_true',
                        help='Offline-only deployable source and adaptive admission audit; never connects')
    parser.add_argument('--project-id', default='default')
    parser.add_argument('--demo-preflight', action='store_true',
                        help='One robot-OFF automatic demo report: originals, shared map/photo, current fixed product contracts and blockers')
    args = parser.parse_args()
    if args.prepare_field_candidate:
        if (args.field_run or args.adaptive_preflight or args.demo_preflight or args.candidate
                or args.allow_torque_off or args.allow_fixed_motion_and_scan):
            parser.error('candidate preparation is separate, robot-OFF only')
        from robot_field_candidate import prepare
        report, out = prepare(ROOT, preflight=_preflight)
        print(json.dumps(report, allow_nan=False))
        return 0 if report['status'] == 'FIELD_COLLECTION_CANDIDATE_PREPARED' else 2
    if args.candidate and (not args.field_run or args.adaptive_preflight or args.demo_preflight):
        parser.error('--candidate requires --field-run only')
    if args.demo_preflight:
        if args.field_run or args.adaptive_preflight:
            parser.error('--demo-preflight is a separate robot-OFF mode')
        if args.project_id!='default':
            parser.error('--demo-preflight audits the preserved default room recordings, not another project')
        from run_demo_preflight import run
        report,out=run(ROOT,admission_audit=lambda root:inspect_adaptive_preparation(root,args.project_id))
        print(json.dumps({'status':report['status'],'report':str(out/'report.json'),
            'checks_completed':report['checks_completed'],'stages':{k:v['status'] for k,v in report['stages'].items()},
            'blockers':report['blockers'],'robot_contacted':False,'physical_demo_ready':False},allow_nan=False))
        return 2 if report['blockers'] else 0
    if args.adaptive_preflight:
        if args.field_run:
            parser.error('--adaptive-preflight is robot-OFF only')
        report = inspect_adaptive_preparation(ROOT, args.project_id)
        out = ROOT/'artifacts/robot-field-suite'/('adaptive-preflight-'+uuid.uuid4().hex)
        out.mkdir(parents=True, exist_ok=False)
        with (out/'report.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, allow_nan=False, indent=2)
        print(json.dumps({**report, 'report': str(out/'report.json')}, allow_nan=False))
        return 0 if report['status']=='OFFLINE_PACKAGE_REVIEWED_FIELD_CHECK_REQUIRED' else 2
    from run_ros_scan_client import run as scan_client
    try:
        report, out = run_suite(field_run=args.field_run, operator_watching=args.operator_watching,
                                clear_floor=args.clear_floor, allow_torque_off=args.allow_torque_off,
                                allow_fixed_motion_and_scan=args.allow_fixed_motion_and_scan,
                                host=args.host, identity_file=args.identity_file,
                                saved_raw=args.saved_raw, scan=scan_client, candidate=args.candidate)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'status': report['status'], 'report': str(out / 'report.json'),
                      'stages': {name: {'status': item['status'],
                                        'reason': item.get('reason') or
                                                  item.get('result', {}).get('reason')}
                                 for name, item in report['stages'].items()}},
                     ensure_ascii=False, allow_nan=False))
    return 0 if (not args.field_run and report['stages']['offline_contracts']['status'] == 'PASS'
                 and report['stages']['saved_evidence']['status'] in {'VERIFIED', 'NOT_REQUESTED'}) else 2


def inspect_adaptive_preparation(root, project_id='default'):
    """Collect independent local blockers once; not a physical admission receipt."""
    root=Path(root)
    # The documented one-file entry works without the developer PYTHONPATH.
    for source in (root/'packages/twinpulse_core/src',root/'packages/twinpulse_app/src',
                   root/'packages/twinpulse_provider/src'):
        if str(source) not in sys.path:sys.path.insert(0,str(source))
    if not isinstance(project_id,str) or not __import__('re').fullmatch('[A-Za-z0-9_-]{1,80}',project_id):
        raise ValueError('ADAPTIVE_PROJECT_ID')
    checks={}
    def check(name, action):
        try:
            detail=action()
            checks[name]={'status':'PASS_LOCAL_ONLY','detail':detail}
        except (ValueError, OSError, TypeError, KeyError, SyntaxError, ImportError) as exc:
            checks[name]={'status':'BLOCKED','reason':str(exc)[:160],'error_type':type(exc).__name__}
    def bundle():
        from robot_source_identity import bundle_files,source_id
        members=bundle_files(root)
        for name,data in members.items():
            if name.endswith('.py'):compile(data,name,'exec')
        return {'source_id':source_id(root),'members':len(members),'python_compiled':True,
                'target_binary_built':False}
    check('deployable_source',bundle)
    package=root/'packages/twinpulse_robot_safety'
    def document(name):
        path=package/name
        if not path.is_file() or path.is_symlink():raise ValueError('MISSING_'+name.upper().replace('.','_').replace('-','_'))
        if path.stat().st_size>16384:raise ValueError('EVIDENCE_BUDGET')
        return json.loads(path.read_text(encoding='utf-8'))
    def policy():
        profile=document('profile.json')
        if profile.get('autonomous_control_policy')!='qualified_session_reviewed_planar_frames_v1':
            raise ValueError('AUTONOMOUS_PROFILE_NOT_REVIEWED')
        return 'CURRENT_BOOT_STOP_AND_SENSOR_ADMISSION_STILL_REQUIRED'
    check('autonomous_profile',policy)
    for name in ('navigation-calibration.json','adaptive-qualification.json','adaptive-sensor-evidence.json'):
        check(name,lambda name=name: {'schema':document(name).get('schema'),'present_not_physical_verification':True})
    def registration():
        from twinpulse_app.automatic_photo_store import load_automatic_room,AutomaticPhotoStore
        from twinpulse_app.observed_release_registration import ObservedReleaseRegistration
        room=load_automatic_room(root,project_id)
        revision=AutomaticPhotoStore(root,project_id).current(room)['effective_revision']
        scope={'schema':'observed-mission-scope-1.0','project_id':project_id,
            'goal':{'mode':'SURVEY_LOCAL','xy':[0.,0.],'room_revision':revision,'duration_s':45},
            'reference':None,'alignment':None}
        value=ObservedReleaseRegistration(root,project_id,revision)(scope)
        return {'source_id':value['source_id'],'room_revision':revision}
    check('reviewed_release_registration',registration)
    return {'schema':'adaptive-preparation-audit-1.0','project_id':project_id,
            'status':('OFFLINE_PACKAGE_REVIEWED_FIELD_CHECK_REQUIRED' if all(v['status']=='PASS_LOCAL_ONLY' for v in checks.values())
                      else 'NOT_READY_BEFORE_ROBOT_CONNECTION'), 'checks':checks,
            'robot_contacted':False,'motion_authorized':False,'physical_demo_ready':False,
            'field_checks':['current_boot_release_battery_stop','fresh_scan_odom_tf_and_measured_mount',
                            'bounded_mission_and_cleanup'],
            'not_covered':['cold_start_survey_alignment_mission_one_start','active_isaac_updates','full_dynamic_obstacle_acceptance']}


if __name__ == '__main__':
    raise SystemExit(main())
