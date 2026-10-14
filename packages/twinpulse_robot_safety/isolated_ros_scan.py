# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fixed isolated COIN D4 driver lifetime within one owned robot session.

This module does not install a driver or grant wheel authority. The caller owns
the robot lease and must reap this child before final independent board READ.
"""
import hashlib
import os
from pathlib import Path
import signal
import subprocess


from coin_driver_identity import (CANDIDATE, BINARY, BINARY_SHA256, DRIVER_LIB,
                                  DRIVER_LIB_SHA256, DEVICE, description)


def driver_environment():
    env = os.environ.copy()
    env.pop('LD_PRELOAD', None)
    env.pop('LD_AUDIT', None)
    paths = [str(DRIVER_LIB.parent), '/opt/ros/humble/lib']
    if env.get('LD_LIBRARY_PATH'):
        paths.append(env['LD_LIBRARY_PATH'])
    env['LD_LIBRARY_PATH'] = os.pathsep.join(paths)
    return env


def driver_artifact_identity():
    """No sensor access or startup: inspect owned artifacts and loader resolution."""
    for path,digest,label in ((BINARY,BINARY_SHA256,'BINARY'),(DRIVER_LIB,DRIVER_LIB_SHA256,'LIBRARY')):
        if any(p.is_symlink() for p in (path,*path.parents)):
            raise RuntimeError('ISOLATED_DRIVER_'+label+'_SYMLINK')
        if not path.is_file():
            raise RuntimeError('ISOLATED_DRIVER_'+label+'_MISSING')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('ISOLATED_DRIVER_'+label+'_SHA_MISMATCH')
        if (len(data)<20 or data[:6]!=b'\x7fELF\x02\x01'
                or int.from_bytes(data[18:20],'little')!=183):
            raise RuntimeError('ISOLATED_DRIVER_'+label+'_NOT_ARM64_ELF')
    try:
        linked = subprocess.run(['ldd', str(BINARY)], capture_output=True, timeout=3,
                                check=False, env=driver_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('ISOLATED_DRIVER_LIBRARY_PREFLIGHT_FAILED') from exc
    if linked.returncode or b'not found' in linked.stdout or b'not found' in linked.stderr:
        missing = '\n'.join(line for line in (linked.stdout+linked.stderr).decode('utf-8','replace').splitlines()
                            if 'not found' in line)[:200]
        raise RuntimeError('ISOLATED_DRIVER_LIBRARY_UNRESOLVED:'+missing)
    if str(DRIVER_LIB).encode() not in linked.stdout:
        raise RuntimeError('ISOLATED_DRIVER_LIBRARY_RESOLVED_TO_DIFFERENT_PATH')
    return {**description(),'artifact_checks':'PASS_NO_SENSOR_ACCESS'}


def binary_identity():
    identity=driver_artifact_identity()
    if os.path.realpath(DEVICE) != '/dev/ttyUSB0':
        raise RuntimeError('ISOLATED_SENSOR_DEVICE_IDENTITY_MISMATCH')
    busy = subprocess.run(['fuser', '/dev/ttyUSB0'], capture_output=True, timeout=3, check=False)
    if busy.returncode != 1 or busy.stderr.strip():
        raise RuntimeError('SENSOR_PORT_BUSY_OR_UNKNOWN')
    return identity


def reap_owned(child):
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
    result = {'write_complete': False, 'quiet_after_1s': False, 'port_restored': False}
    try:
        channel.configure()
        with channel.cleanup():
            for attempt in range(2):
                written = channel.write(STOP)
                channel.drain(2.0)
                residual = channel.drain(1.0)
                result.update(attempts=attempt + 1, write_complete=written == len(STOP),
                              bytes_after_settle_1s=residual)
                if result['write_complete'] and residual == 0:
                    result['quiet_after_1s'] = True
                    break
            result['port_restored'] = channel.restore()
    finally:
        channel.close()
    return result


class IsolatedRosScan:
    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self.child = None
        self.stream = None
        self.stopped = False

    def start(self):
        if self.child is not None:
            raise RuntimeError('DRIVER_ALREADY_STARTED')
        binary_identity()
        command = [str(BINARY), '--ros-args', '-p', 'port:=' + DEVICE,
                   '-p', 'frame_id:=base_scan', '-p', 'baudrate:=230400',
                   '-p', 'version:=4', '-p', 'topic_name:=scan', '-p', 'warmup_time:=0']
        self.stream = self.log_path.open('xb')
        try:
            self.child = subprocess.Popen(command, stdout=self.stream, stderr=subprocess.STDOUT,
                                          start_new_session=True, env=driver_environment())
        except BaseException:
            self.stream.close()
            self.stream = None
            raise

    def running(self):
        return self.child is not None and self.child.poll() is None

    def stop(self):
        if self.stopped:
            raise RuntimeError('DRIVER_STOP_ALREADY_ATTEMPTED')
        self.stopped = True
        result = {'driver': {'status': 'NOT_STARTED'}, 'sensor_stop': {'status': 'NOT_RUN'},
                  'physical_rotor_stopped': 'UNCONFIRMED'}
        try:
            if self.child is not None:
                result['driver'] = reap_owned(self.child)
                # Never compete with a child that still holds the serial port.
                if self.child.poll() is not None:
                    result['sensor_stop'] = explicit_sensor_stop()
        except BaseException as exc:
            result['error'] = type(exc).__name__ + ':' + str(exc)[:160]
        finally:
            if self.stream is not None:
                self.stream.close()
        return result


if __name__ == '__main__':
    import json
    import sys
    if sys.argv[1:] != ['--artifact-preflight']:
        raise SystemExit('Only --artifact-preflight is accepted; it never starts a sensor')
    try:
        print(json.dumps(driver_artifact_identity()), flush=True)
    except Exception as error:
        print(json.dumps({'status':'DRIVER_ARTIFACT_PREFLIGHT_FAILED',
                          'reason':type(error).__name__+':'+str(error)}), flush=True)
        raise SystemExit(2)
