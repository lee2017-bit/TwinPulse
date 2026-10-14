# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded disarmed base lifecycle. Caller holds the package's exclusive lease.

No publisher, motor enable, arm request or drive trial is reachable here.
Callbacks permit device-free lifecycle tests without substituting fake hardware
into the production command path.
"""
import os
from contextlib import contextmanager
import re
import signal
import subprocess
import sys
import time
import threading


def bounded_error_lines(path):
    """Return a short, redacted clue; retain the exact log file on the robot."""
    try:
        with path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 8192))
            tail = stream.read().decode('utf-8', errors='replace')
    except OSError as exc:
        return {'status': 'UNAVAILABLE_' + type(exc).__name__, 'lines': []}
    lines = []
    for raw in tail.splitlines():
        if not re.search(r'error|exception|failed|invalid|not found|what\(\)|permission denied', raw, re.I):
            continue
        if re.search(r'password|secret|token|private.?key|authorization|bearer', raw, re.I):
            lines.append('[REDACTED]')
            continue
        clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', raw)
        clean = ''.join(c for c in clean if c.isprintable())
        lines.append(clean[:240])
    return {'status': 'RECORDED', 'lines': lines[-3:]}


@contextmanager
def cleanup_signals():
    # A second Ctrl+C must not interrupt reaping/independent final observation.
    saved = {}
    if threading.current_thread() is threading.main_thread():
        for name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
            signum = getattr(signal, name, None)
            if signum is not None:
                saved[signum] = signal.signal(signum, signal.SIG_IGN)
    try:
        yield
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


def require_idle(board):
    if (board.get('status') != 'OBSERVED' or board.get('torque_enabled') is not False
            or board.get('wheel_velocity_raw') != [0, 0]
            or board.get('command_bytes_zero') is not True
            or board.get('near_board_protection') is not False):
        raise RuntimeError('Stationary check requires fresh disabled/zero state and adequate voltage')


def stop_child(child):
    """Reap owned process before serial can be read or the lease released."""
    if child.poll() is not None:
        return {'exit_code': child.returncode, 'escalation': 'already_exited'}
    for signum, label, seconds in [(signal.SIGINT, 'interrupt', 3),
                                   (signal.SIGTERM, 'terminate', 2),
                                   (signal.SIGKILL, 'kill', 2)]:
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
        try:
            code = child.wait(timeout=seconds)
            return {'exit_code': code, 'escalation': label}
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError('Owned process did not exit; serial must not be accessed')


def lifecycle(precheck, start_base, observe, postcheck):
    """Always attempt final independent READ after confirmed process exit."""
    result = {'motion_authorized': False, 'status': 'STARTED', 'events': []}
    child = None
    interrupted = None
    try:
        result['before'] = precheck()
        require_idle(result['before'])
        result['events'].append('idle_precheck')
        child = start_base()
        result['events'].append('base_started_disarmed')
        result['observation'] = observe(child)
        if result['observation'].get('status') != 'STATIONARY_OBSERVED':
            raise RuntimeError('Stationary telemetry qualification failed')
        result['status'] = 'STATIONARY_CHECK_PASS'
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                      reason=str(exc), error_type=type(exc).__name__)
        interrupted = exc
    finally:
        if child is not None:
            with cleanup_signals():
                finish_child(child, result, postcheck)
    if interrupted is not None:
        result['interrupted_or_failed_before_cleanup'] = True
    return result


def finish_child(child, result, postcheck):
    # Keep failures in the receipt rather than claiming cleanup from an ACK alone.
    try:
        result['base_exit'] = stop_child(child)
        result['events'].append('base_reaped')
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='CLEANUP_UNCONFIRMED', cleanup_error=str(exc), operator_cutoff_required=True)
        # Never read the serial device while an owned child may be alive.
        return
    try:
        result['after'] = postcheck()
        require_idle(result['after'])
        result['events'].append('independent_idle_read')
        # Across this no-motion session allow at most the prior 2-tick band.
        if any(abs(a-b) > 2 for a, b in zip(result['before']['encoders'], result['after']['encoders'])):
            raise RuntimeError('Encoder displacement across stationary session')
        if result['base_exit']['escalation'] in {'terminate', 'kill', 'already_exited'}:
            result['status'] = 'STOPPED_NEEDS_REVIEW'
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='FINAL_IDLE_UNCONFIRMED', cleanup_error=str(exc), operator_cutoff_required=True)


def commands(release, report_dir):
    """Only the reviewed constant shell script selects ROS setup/arguments."""
    prefix = [sys.executable, '-B', str(release / 'owned_exec.py')]
    return ([*prefix, 'base', str(os.getpid())],
            [*prefix, 'observe', str(os.getpid()), str(report_dir / 'telemetry.json')])


def run(release, report_dir, snapshot, lease_fd):
    import json
    base_command, observer_command = commands(release, report_dir)
    base_stream = (report_dir / 'base.log').open('ab')

    def observe(base):
        with (report_dir / 'observer.log').open('ab') as stream:
            monitor = subprocess.Popen(observer_command, stdout=stream, stderr=stream,
                                       start_new_session=True, pass_fds=(lease_fd,))
            started = time.monotonic()
            try:
                while monitor.poll() is None:
                    if base.poll() is not None:
                        raise RuntimeError('Base exited during observation')
                    if time.monotonic() - started > 25:
                        raise TimeoutError('Stationary observation deadline')
                    time.sleep(.05)
                if monitor.returncode and not (report_dir / 'telemetry.json').is_file():
                    raise RuntimeError('Observer rejected state; see telemetry/observer log')
                return json.loads((report_dir / 'telemetry.json').read_text())
            finally:
                with cleanup_signals():
                    stop_child(monitor)

    try:
        result = lifecycle(lambda: snapshot('before'),
                           lambda: subprocess.Popen(base_command, stdout=base_stream, stderr=base_stream,
                                                    start_new_session=True, pass_fds=(lease_fd,)),
                           observe, lambda: snapshot('after'))
    finally:
        base_stream.close()
    if result['status'] != 'STATIONARY_CHECK_PASS':
        result['diagnostics'] = {'base': bounded_error_lines(report_dir / 'base.log'),
                                 'observer': bounded_error_lines(report_dir / 'observer.log'),
                                 'robot_log_dir': str(report_dir)}
    return result
