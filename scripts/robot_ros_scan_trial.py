# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One supervised, no-wheel ROS LaserScan trial against an isolated COIN-D4 build.

Fixed candidate and duration. Always reap the owned driver and send a separate
sensor STOP after the serial port is released. This does not prove rotor stop.
"""
import hashlib
from contextlib import nullcontext
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

HOME = Path('/home/twinpulse/.local/share/twinpulse/robot')
CAPTURE_SECONDS = 12.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stop_owned(child):
    if child.poll() is not None:
        return {'exit_code': child.returncode, 'signal': 'already_exited'}
    for signum, label, seconds in ((signal.SIGINT, 'SIGINT', 4),
                                   (signal.SIGTERM, 'SIGTERM', 2),
                                   (signal.SIGKILL, 'SIGKILL', 2)):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
        try:
            return {'exit_code': child.wait(timeout=seconds), 'signal': label}
        except subprocess.TimeoutExpired:
            continue
    raise RuntimeError('OWNED_DRIVER_NOT_REAPED')


def explicit_sensor_stop():
    from lidar_capture import SerialChannel, STOP
    channel = SerialChannel()
    result = {'write_complete': False, 'quiet_after_1s': False,
              'port_restored': False}
    try:
        channel.configure()
        with channel.cleanup():
            for attempt in range(2):
                written = channel.write(STOP)
                channel.drain(2.0)
                residual = channel.drain(1.0)
                result['attempts'] = attempt + 1
                result['write_complete'] = written == len(STOP)
                result['bytes_after_settle_1s'] = residual
                if result['write_complete'] and residual == 0:
                    result['quiet_after_1s'] = True
                    break
            result['port_restored'] = channel.restore()
    finally:
        channel.close()
    return result


def main():
    if sys.argv[1:]:
        raise SystemExit('No runtime overrides accepted')
    release = (HOME / 'current').resolve(strict=True)
    sys.path.insert(0, str(release))
    from runtime import ownership, read_board, verify_release, write_json
    from robot_health import parse_board_snapshot
    from stationary import require_idle
    from raw_ros_record import RawRosRecorder
    from coin_driver_identity import BINARY, BINARY_SHA256, DEVICE, description
    from isolated_ros_scan import binary_identity, driver_environment
    from rclpy.serialization import serialize_message
    from rclpy.qos import qos_profile_sensor_data
    import rclpy
    from sensor_msgs.msg import LaserScan

    manifest = verify_release(release)
    out = HOME / 'reports' / ('ros-scan-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
                              + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 'twinpulse-ros-scan-trial-1.0', 'status': 'STARTED',
              'motion_authorized': False, 'physical_rotor_stopped': 'UNCONFIRMED',
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'release_id': manifest['source_id'], 'candidate_binary_sha256': BINARY_SHA256,
              'driver_identity':description(),
              'report_directory': str(out), 'scan_count': 0,
              'sensor_stop': {'status': 'NOT_RUN'}}
    write_json(out / 'report.json', report)
    child = None
    recorder = None
    node = None
    ros_started = False
    lease_scope = ownership()
    lease = None

    def interrupted(signum, _frame):
        raise KeyboardInterrupt('TRIAL_INTERRUPTED_SIGNAL_' + str(signum))

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
        signal.signal(signum, interrupted)
    signal.alarm(45)

    def snapshot(label, lease):
        log = out / (label + '-board.log')
        read_board(release, log, lease.fileno())
        return parse_board_snapshot(log.read_text())

    try:
        lease = lease_scope.__enter__()
        with nullcontext(lease):
            report['before'] = snapshot('before', lease)
            require_idle(report['before'])
            report['driver_artifact_checks'] = binary_identity()
            serial = subprocess.run(['fuser', '/dev/ttyUSB0'], capture_output=True,
                                    timeout=3)
            if serial.returncode != 1 or serial.stderr.strip():
                raise RuntimeError('SENSOR_PORT_BUSY_OR_UNKNOWN')
            recorder = RawRosRecorder(out / 'ros-messages.raw', serializer=serialize_message,
                                      max_bytes=8 * 1024 * 1024)
            rclpy.init()
            ros_started = True
            node = rclpy.create_node('twinpulse_ros_scan_trial', namespace='/tp_trial')

            def on_scan(msg):
                recorder.record('scan', msg)
                report['scan_count'] += 1
                report['last_scan'] = {'frame_id': msg.header.frame_id,
                                       'stamp_sec': msg.header.stamp.sec,
                                       'stamp_nanosec': msg.header.stamp.nanosec,
                                       'ranges': len(msg.ranges),
                                       'angle_increment': msg.angle_increment}

            node.create_subscription(LaserScan, '/scan', on_scan, qos_profile_sensor_data)
            command = [str(BINARY), '--ros-args', '-p', 'port:=' + DEVICE,
                       '-p', 'frame_id:=base_scan', '-p', 'baudrate:=230400',
                       '-p', 'version:=4', '-p', 'topic_name:=scan',
                       '-p', 'warmup_time:=0']
            with (out / 'driver.log').open('wb') as stream:
                child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                         start_new_session=True, env=driver_environment())
                start = time.monotonic()
                while time.monotonic() - start < CAPTURE_SECONDS:
                    rclpy.spin_once(node, timeout_sec=.1)
                    if child.poll() is not None:
                        report['driver_early_exit'] = child.returncode
                        break
                report['elapsed_s'] = round(time.monotonic() - start, 3)
    except BaseException as exc:
        report['error'] = type(exc).__name__ + ':' + str(exc)[:240]
    finally:
        signal.alarm(0)
        # Repeated interrupts must not skip the independent STOP and lease cleanup.
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
            signal.signal(signum, signal.SIG_IGN)
        if child is not None:
            try:
                report['driver_stop'] = stop_owned(child)
            except BaseException as exc:
                report['driver_stop_error'] = type(exc).__name__ + ':' + str(exc)[:160]
        # This independent STOP is required even when the driver's destructor reports success.
        if child is not None and child.poll() is not None:
            try:
                report['sensor_stop'] = explicit_sensor_stop()
            except BaseException as exc:
                report['sensor_stop'] = {'status': 'FAILED',
                                         'error': type(exc).__name__ + ':' + str(exc)[:160]}
        if recorder is not None:
            try:
                report['raw_ros'] = recorder.close()
            except BaseException as exc:
                report['raw_ros'] = {'complete': False, 'error': str(exc)[:160]}
        if node is not None:
            node.destroy_node()
        if ros_started:
            rclpy.shutdown()
        try:
            if lease is not None:
                report['after'] = snapshot('after', lease)
                require_idle(report['after'])
                if any(abs(a-b)>2 for a,b in zip(report['before']['encoders'],report['after']['encoders'])):
                    raise RuntimeError('ENCODER_DISPLACEMENT_ACROSS_TRIAL')
                if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=report['boot_id']:
                    raise RuntimeError('BOOT_CHANGED')
        except BaseException as exc:
            report['after_error'] = type(exc).__name__ + ':' + str(exc)[:160]
        finally:
            if lease is not None:
                lease_scope.__exit__(None, None, None)
        report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        stop = report['sensor_stop']
        good = (report['scan_count'] >= 3 and report.get('last_scan', {}).get('ranges', 0) > 0
                and report.get('raw_ros', {}).get('complete') is True
                and stop.get('write_complete') is True and stop.get('quiet_after_1s') is True
                and stop.get('port_restored') is True and 'after' in report
                and 'error' not in report and 'driver_stop_error' not in report
                and 'after_error' not in report)
        report['status'] = 'ROS_SCAN_OBSERVED_STOP_DATA_QUIET' if good else 'NEEDS_REVIEW'
        write_json(out / 'report.json', report)
        print(json.dumps(report), flush=True)
    return 0 if report['status'] == 'ROS_SCAN_OBSERVED_STOP_DATA_QUIET' else 2


if __name__ == '__main__':
    raise SystemExit(main())
