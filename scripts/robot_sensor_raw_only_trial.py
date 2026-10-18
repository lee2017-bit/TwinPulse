# SPDX-License-Identifier: Apache-2.0
"""8s native-angle diagnostic, with sensor-only stationary READ boundaries."""
import base64
import ctypes
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid
from robot_sensor_only_trial import EXPECTED_RELEASE,require_sensor_stationary


def main(*,cancel_after_s=None):
    if cancel_after_s not in (None,2.0):raise ValueError('Only fixed2s cancel trial is supported')
    from runtime import ownership,read_board,verify_release,write_json
    from robot_health import parse_board_snapshot
    from lidar_capture import SerialChannel,acquire
    home=Path('/home/twinpulse/.local/share/twinpulse/robot')
    release=(home/'current').resolve(strict=True)
    if release.name!=EXPECTED_RELEASE:raise ValueError('CURRENT_RELEASE_CHANGED')
    manifest=verify_release(release)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    run_id='sensor-raw-only-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    out=home/'reports'/run_id;out.mkdir(exist_ok=False,parents=True)
    report=dict(schema_version='sensor-raw-only-1.0',run_id=run_id,status='STARTED',
                release_id=manifest['source_id'],boot_id=boot,report_directory=str(out),
                base_started=False,wheel_commands_sent=0,torque_writes_sent=0,drive_authority=False)
    def interrupted(sig,_frame):raise KeyboardInterrupt('SENSOR_RAW_INTERRUPTED_'+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupted)
    parent=os.getppid()
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGHUP,0,0,0)!=0 or os.getppid()!=parent:
        raise RuntimeError('PARENT_DEATH_BINDING_FAILED')
    data=b''
    with ownership() as lease:
        def snap(label):
            if (home/'current').resolve(strict=True)!=release or Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=boot:
                raise ValueError('BOOT_OR_RELEASE_CHANGED')
            log=out/(label+'-board.log');read_board(release,log,lease.fileno())
            value=parse_board_snapshot(log.read_text());require_sensor_stationary(value,report.get('before'))
            return value
        try:
            report['before']=snap('before');time.sleep(.5);report['preflight_second']=snap('second')
            signal.alarm(12)
            began=time.monotonic()
            data,chunks=acquire(SerialChannel(),report,
                cancel=lambda:cancel_after_s is not None and time.monotonic()-began>=cancel_after_s)
            signal.alarm(0)
            (out/'raw.bin').write_bytes(data);write_json(out/'chunks.json',chunks)
        except BaseException as exc:report['error']=type(exc).__name__+':'+str(exc)[:200]
        finally:
            signal.alarm(0)
            for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,signal.SIG_IGN)
            try:
                report['after']=snap('after');report['final_stationary_checked']=True
            except BaseException as exc:report['after_error']=type(exc).__name__+':'+str(exc)[:200]
            good=(not any(k in report for k in ('error','after_error','acquisition_error','restore_error'))
                  and len(data)>0 and report.get('port_restored') is True
                  and report.get('data_quiet_after_stop') is True and report.get('final_stationary_checked') is True)
            report['status']='RAW_OBSERVED_STATIONARY_DATA_QUIET' if good else 'NEEDS_REVIEW'
            if good and cancel_after_s is not None:
                report['status']='OPERATOR_CANCEL_CLEANUP_CONFIRMED' if report.get('operator_cancelled') is True else 'CANCEL_NOT_OBSERVED'
            report['finished_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            write_json(out/'report.json',report)
            # Transport exact bounded raw bytes, not a fabricated LaserScan.
            print(json.dumps(dict(report,raw_base64=base64.b64encode(data).decode()),allow_nan=False),flush=True)
    return 0 if good else 2


if __name__=='__main__':raise SystemExit(main())
