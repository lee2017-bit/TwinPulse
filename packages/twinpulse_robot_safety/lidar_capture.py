# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One bounded COIN-D4 raw recording, no ROS/base startup or wheel writes.

Uses the previously reviewed ROBOTIS 8277b288 protocol (230400, DTR low,
AA55F00F start / AA55F50A stop). Data silence is NOT physical rotor feedback.
Existing qualified release supplies independent READ and the OpenCR lease.
"""
import array
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

DEVICE = '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'
START = bytes.fromhex('aa55f00f')
STOP = bytes.fromhex('aa55f50a')
MAX_BYTES = 512 * 1024
CAPTURE_SECONDS = 8.0


def acquire(channel, report, now=time.monotonic, cancel=lambda: False,
            *, capture_seconds=CAPTURE_SECONDS, max_bytes=MAX_BYTES):
    """Testable fixed protocol. Cleanup even after a partial/failed START write."""
    if (type(capture_seconds) not in (int, float) or not math.isfinite(capture_seconds)
            or not 0 < capture_seconds <= 45 or type(max_bytes) is not int
            or not 1 <= max_bytes <= 1024*1024):
        raise ValueError('Invalid bounded capture window')
    data = bytearray()
    chunks = []
    started = False
    try:
        channel.configure()
        started = True
        report['start_attempted'] = True
        if channel.write(START) != len(START):
            raise RuntimeError('Incomplete START write')
        report['start_sent'] = True
        begin = now()
        report['capture_begin_monotonic_s'] = begin
        while now() - begin < capture_seconds:
            if cancel():
                report['operator_cancelled'] = True
                break
            block = channel.read(min(.1, max(0, capture_seconds - (now() - begin))))
            if len(data) + len(block) > max_bytes:
                raise RuntimeError('Capture byte budget exceeded')
            if block:
                chunks.append({'offset': len(data), 'length': len(block), 'receipt_s': now() - begin})
                data.extend(block)
        report['elapsed_seconds'] = now() - begin
    except (Exception, KeyboardInterrupt) as exc:
        report['acquisition_error'] = str(exc)
    finally:
        # Once cleanup begins, repeated interrupts cannot skip STOP/restoration.
        with channel.cleanup():
            report['stop_attempts'] = []
            if started:
                for _ in range(2):
                    attempt = {}
                    report['stop_attempts'].append(attempt)
                    try:
                        attempt['write_complete'] = channel.write(STOP) == len(STOP)
                        # Drain (do not block on tcdrain) for 2s, then observe 1s.
                        channel.drain(2.0)
                        attempt['bytes_after_settle_1s'] = channel.drain(1.0)
                        if attempt['write_complete'] and attempt['bytes_after_settle_1s'] == 0:
                            report['data_quiet_after_stop'] = True
                            break
                    except Exception as exc:
                        attempt['error'] = str(exc)
            try:
                report['port_restored'] = channel.restore()
            except Exception as exc:
                report['restore_error'] = str(exc)
            finally:
                channel.close()
    report.update(bytes_received=len(data), chunk_count=len(chunks),
                  raw_sha256=hashlib.sha256(data).hexdigest(),
                  physical_rotor_stopped='UNCONFIRMED',
                  timestamp_basis='host serial receipt; not beam acquisition time')
    return bytes(data), chunks


class SerialChannel:
    def __init__(self):
        import fcntl
        import termios
        from stationary import cleanup_signals
        self.fcntl, self.t, self.cleanup = fcntl, termios, cleanup_signals
        self.fd, self.saved, self.modem = None, None, None

    def configure(self):
        if os.path.realpath(DEVICE) != '/dev/ttyUSB0':
            raise RuntimeError('Unexpected sensor identity/target')
        p = subprocess.run(['fuser', '/dev/ttyUSB0'], capture_output=True, timeout=3)
        if p.returncode != 1 or p.stderr.strip():
            raise RuntimeError('Sensor port busy or ownership unknown')
        self.fd = os.open(DEVICE, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.fcntl.ioctl(self.fd, self.t.TIOCEXCL)
        self.saved = self.t.tcgetattr(self.fd)
        modem = array.array('i', [0])
        self.fcntl.ioctl(self.fd, self.t.TIOCMGET, modem, True)
        self.modem = modem
        cfg = copy.deepcopy(self.saved)
        cfg[0] = cfg[1] = cfg[3] = 0
        cfg[2] = self.t.CS8 | self.t.CREAD | self.t.CLOCAL
        cfg[4] = cfg[5] = self.t.B230400
        cfg[6][self.t.VMIN] = cfg[6][self.t.VTIME] = 0
        self.t.tcsetattr(self.fd, self.t.TCSANOW, cfg)
        self.fcntl.ioctl(self.fd, self.t.TIOCMBIC, array.array('i', [self.t.TIOCM_DTR]))
        self.t.tcflush(self.fd, self.t.TCIFLUSH)

    def write(self, data):
        if data not in (START, STOP):
            raise ValueError('Unsupported sensor command')
        return os.write(self.fd, data)

    def read(self, seconds):
        if select.select([self.fd], [], [], seconds)[0]:
            return os.read(self.fd, 4096)
        return b''

    def drain(self, seconds):
        end = time.monotonic() + seconds
        count = 0
        while time.monotonic() < end:
            count += len(self.read(min(.05, max(0, end - time.monotonic()))))
        return count

    def restore(self):
        lines_ok = self.modem is None
        config_ok = self.saved is None
        try:
            if self.modem is not None:
                self.fcntl.ioctl(self.fd, self.t.TIOCMSET, self.modem)
                actual = array.array('i', [0])
                self.fcntl.ioctl(self.fd, self.t.TIOCMGET, actual, True)
                mask = self.t.TIOCM_DTR | self.t.TIOCM_RTS
                lines_ok = actual[0] & mask == self.modem[0] & mask
        finally:
            if self.saved is not None:
                self.t.tcsetattr(self.fd, self.t.TCSANOW, self.saved)
                config_ok = self.t.tcgetattr(self.fd) == self.saved
        return lines_ok and config_ok

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def main():
    if sys.argv[1:]:
        raise SystemExit('No runtime overrides accepted')
    home = Path.home() / '.local/share/twinpulse/robot'
    release = (home / 'current').resolve(strict=True)
    sys.path.insert(0, str(release))
    from runtime import ownership, read_board, verify_release, write_json
    from robot_health import parse_board_snapshot
    from stationary import require_idle, cleanup_signals
    manifest = verify_release(release)
    out = home / 'reports' / ('lidar-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 'lidar-raw-capture-1.0', 'status': 'STARTED',
              'motion_authorized': False, 'release_id': manifest['source_id'],
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'report_directory': str(out), 'physical_rotor_stopped': 'UNCONFIRMED'}
    write_json(out / 'report.json', report)

    def interrupt(*_):
        raise KeyboardInterrupt('Capture interrupted/deadline reached')

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
        signal.signal(sig, interrupt)
    try:
        with ownership() as lease:
            def snapshot(label):
                log = out / (label + '-board.log')
                read_board(release, log, lease.fileno())
                return parse_board_snapshot(log.read_text())
            report['before'] = snapshot('before')
            require_idle(report['before'])
            try:
                signal.alarm(12)
                data, chunks = acquire(SerialChannel(), report)
                signal.alarm(0)
                (out / 'raw.bin').write_bytes(data)
                write_json(out / 'chunks.json', chunks)
            finally:
                signal.alarm(0)
                with cleanup_signals():
                    report['after'] = snapshot('after')
                    require_idle(report['after'])
            report['encoder_delta'] = [b-a for a, b in zip(report['before']['encoders'], report['after']['encoders'])]
            okay = (not report.get('acquisition_error') and report.get('bytes_received', 0) > 0
                    and report.get('data_quiet_after_stop') is True and report.get('port_restored') is True
                    and all(abs(v) <= 2 for v in report['encoder_delta']))
            report['status'] = 'RAW_CAPTURED_DATA_QUIET' if okay else 'NEEDS_REVIEW'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='FAILED', error=str(exc))
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_json(out / 'report.json', report)
    print(json.dumps(report), flush=True)
    return 0 if report['status'] == 'RAW_CAPTURED_DATA_QUIET' else 2


if __name__ == '__main__':
    raise SystemExit(main())
