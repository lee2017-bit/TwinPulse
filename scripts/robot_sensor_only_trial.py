# SPDX-License-Identifier: Apache-2.0
"""Supervised 12s LiDAR-only observation; never starts a base or writes wheels.

Unlike a deenergized motion qualification, this permits torque ON while fixed
READs independently establish zero command/velocity and stable wheel encoders.
It does not grant navigation/drive authority or certify a physical stop.
"""
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import uuid

HOME = Path('/home/twinpulse/.local/share/twinpulse/robot')
EXPECTED_RELEASE = '1cede5493f5a4ade3c46c49049dc9752a8fef3476b76f5a0cc214e16e9ade1ba'
SECONDS = 12.0


class SensorWindowEnded(BaseException):
    pass


def require_sensor_stationary(board, baseline=None):
    if (board.get('status') != 'OBSERVED' or board.get('port_restored') is not True
            or type(board.get('torque_enabled')) is not bool
            or board.get('wheel_velocity_raw') != [0, 0]
            or board.get('command_bytes_zero') is not True
            or board.get('near_board_protection') is not False):
        raise ValueError('SENSOR_ONLY_STATIONARY_READ_REQUIRED')
    enc = board.get('encoders')
    if not isinstance(enc, list) or len(enc) != 2 or any(type(v) is not int for v in enc):
        raise ValueError('ENCODERS_UNAVAILABLE')
    if baseline is not None and any(abs(a-b) > 2 for a,b in zip(enc, baseline['encoders'])):
        raise ValueError('ENCODER_DISPLACEMENT_DURING_SENSOR_ONLY_SESSION')


def trial_success(report):
    stop = report.get('cleanup', {}).get('sensor_stop', {})
    return (not any(k in report for k in ('error', 'after_error', 'cleanup_error'))
            and 'error' not in report.get('cleanup', {})
            and report.get('final_stationary_checked') is True
            and report.get('scan_count', 0) >= 3
            and report.get('finite_valid_beams', 0) > 0
            and report.get('raw_ros', {}).get('complete') is True
            and stop.get('write_complete') is True
            and stop.get('quiet_after_1s') is True
            and stop.get('port_restored') is True)


def main():
    from runtime import ownership, read_board, verify_release, write_json
    from robot_health import parse_board_snapshot
    from raw_ros_record import RawRosRecorder
    from isolated_ros_scan import IsolatedRosScan, binary_identity
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import LaserScan
    release = (HOME/'current').resolve(strict=True)
    if release.name != EXPECTED_RELEASE:
        raise ValueError('CURRENT_RELEASE_CHANGED_NO_ACTIVATION')
    manifest = verify_release(release)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    run_id = 'sensor-only-'+time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'-'+uuid.uuid4().hex[:8]
    out = HOME/'reports'/run_id
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version='twinpulse-sensor-only-trial-1.0',run_id=run_id,status='STARTED',
                  boot_id=boot,release_id=manifest['source_id'],report_directory=str(out),
                  wheel_commands_sent=0,torque_writes_sent=0,base_started=False,
                  drive_authority=False,physical_rotor_stopped='UNCONFIRMED',
                  scan_count=0,finite_valid_beams=0,scans=[],board_samples=[])
    driver=IsolatedRosScan(out/'driver.log')
    recorder=None;node=None;ros_started=False
    started=None
    def interrupted(signum, _frame):
        if signum==signal.SIGALRM and started is not None:
            raise SensorWindowEnded()
        raise KeyboardInterrupt('SENSOR_ONLY_SIGNAL_'+str(signum))
    for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):
        signal.signal(signum,interrupted)
    # Parent SSH loss requests cleanup; the alarm also bounds an orphan session.
    import ctypes
    parent=os.getppid()
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGHUP,0,0,0)!=0 or os.getppid()!=parent:
        raise RuntimeError('PARENT_DEATH_BINDING_FAILED')
    signal.alarm(55)
    with ownership() as lease:
        def snapshot(label):
            if (HOME/'current').resolve(strict=True)!=release:
                raise ValueError('RELEASE_CHANGED')
            if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=boot:
                raise ValueError('BOOT_CHANGED')
            log=out/(label+'-board.log')
            read_board(release,log,lease.fileno())
            value=parse_board_snapshot(log.read_text())
            require_sensor_stationary(value,report.get('before'))
            report['board_samples'].append(value)
            return value
        try:
            report['before']=snapshot('before')
            time.sleep(.5)
            report['preflight_second']=snapshot('preflight-second')
            report['driver_identity']=binary_identity()
            write_json(out/'report.json',report)
            rclpy.init();ros_started=True
            node=rclpy.create_node('twinpulse_sensor_only_trial',namespace='/tp_sensor_only')
            recorder=RawRosRecorder(out/'ros-messages.raw',serializer=serialize_message,max_bytes=8*1024*1024)
            def on_scan(msg):
                recorder.record('scan',msg)
                report['scan_count']+=1
                ranges=[float(x) if math.isfinite(x) else None for x in msg.ranges]
                valid=sum(x is not None and msg.range_min<=x<=msg.range_max for x in ranges)
                report['finite_valid_beams']+=valid
                row=dict(frame_id=msg.header.frame_id,stamp_sec=msg.header.stamp.sec,
                         stamp_nanosec=msg.header.stamp.nanosec,angle_min=msg.angle_min,
                         angle_max=msg.angle_max,angle_increment=msg.angle_increment,
                         range_min=msg.range_min,range_max=msg.range_max,
                         scan_time=msg.scan_time,time_increment=msg.time_increment,ranges=ranges,
                         host_receipt_monotonic_ns=time.monotonic_ns())
                report['scans']=(report['scans']+[row])[-8:]
            node.create_subscription(LaserScan,'/scan',on_scan,qos_profile_sensor_data)
            driver.start(lease_fd=lease.fileno())
            started=time.monotonic();last_board=started
            # Interrupt blocking READ as well as spin_once at the acquisition
            # deadline; driver reaping/independent STOP then run in finally.
            signal.setitimer(signal.ITIMER_REAL,SECONDS)
            while time.monotonic()-started<SECONDS:
                rclpy.spin_once(node,timeout_sec=.1)
                if not driver.running():raise RuntimeError('DRIVER_EARLY_EXIT')
                if time.monotonic()-last_board>=2:
                    snapshot('during-'+str(len(report['board_samples'])))
                    last_board=time.monotonic()
            report['capture_seconds']=round(time.monotonic()-started,3)
        except SensorWindowEnded:
            report['capture_seconds']=round(time.monotonic()-started,3)
            report['acquisition_deadline_reached']=True
        except BaseException as exc:
            report['error']=type(exc).__name__+':'+str(exc)[:240]
        finally:
            signal.alarm(0)
            for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):
                signal.signal(signum,signal.SIG_IGN)
            report['cleanup']=driver.stop()
            for label,cleanup in (
                ('raw_ros',recorder.close if recorder is not None else None),
                ('node',node.destroy_node if node is not None else None),
                ('ros',rclpy.shutdown if ros_started else None)):
                if cleanup is not None:
                    try:
                        value=cleanup()
                        if label=='raw_ros':report[label]=value
                    except BaseException as exc:
                        report['cleanup_error']=label+':'+type(exc).__name__+':'+str(exc)[:160]
            if driver.child is not None and driver.child.poll() is None:
                report['cleanup_error']='CHILD_NOT_REAPED_NO_COMPETING_BOARD_READ'
            else:
                try:
                    report['after']=snapshot('after')
                    report['final_stationary_checked']=True
                except BaseException as exc:
                    report['after_error']=type(exc).__name__+':'+str(exc)[:240]
            report['status']='SCAN_OBSERVED_STATIONARY_DATA_QUIET' if trial_success(report) else 'NEEDS_REVIEW'
            report['finished_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            write_json(out/'report.json',report)
            print(json.dumps(report,allow_nan=False),flush=True)
    return 0 if trial_success(report) else 2


if __name__=='__main__':
    raise SystemExit(main())
