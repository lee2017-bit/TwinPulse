# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free protocol/cleanup tests. Never imports Linux serial libraries."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('lidar_capture', Path(__file__).parents[1] / 'lidar_capture.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Fake:
    def __init__(self, fault=None, quiet=(0,)):
        self.fault, self.quiet, self.commands = fault, iter(quiet), []
        self.closed = self.restored = False
        self.clock = 0
        self.cleanup = nullcontext
    def now(self):
        self.clock += .1
        return self.clock
    def configure(self):
        if self.fault == 'configure':
            raise RuntimeError('configure')
    def write(self, data):
        self.commands.append(data)
        if data == m.START and self.fault == 'write':
            raise RuntimeError('partial write')
        return len(data)
    def read(self, _):
        if self.fault == 'read':
            raise RuntimeError('read')
        if self.fault == 'interrupt':
            raise KeyboardInterrupt()
        return b'a' * (m.MAX_BYTES + 1 if self.fault == 'budget' else 10)
    def drain(self, seconds):
        return next(self.quiet) if seconds == 1 else 5
    def restore(self):
        self.restored = True
        if self.fault == 'restore':
            raise RuntimeError('restore')
        return True
    def close(self):
        self.closed = True


class CaptureTest(unittest.TestCase):
    def test_explicit_longer_window_keeps_default_and_cleanup(self):
        f=Fake(); report={}
        data,chunks=m.acquire(f,report,now=f.now,capture_seconds=12.,max_bytes=1024*1024)
        self.assertEqual(m.CAPTURE_SECONDS,8.)
        self.assertEqual(m.MAX_BYTES,512*1024)
        self.assertTrue(report['port_restored'] and report['data_quiet_after_stop'])
        self.assertIn('capture_begin_monotonic_s',report)
        self.assertEqual(sum(x['length'] for x in chunks),len(data))

    def test_invalid_window_rejected_before_serial_access(self):
        for seconds,budget in ((0,1),(46,1),(float('nan'),1),(True,1),(8,0),(8,1024*1024+1)):
            f=Fake()
            with self.assertRaises(ValueError):m.acquire(f,{},capture_seconds=seconds,max_bytes=budget)
            self.assertEqual(f.commands,[])
    def test_operator_cancel_still_stops_and_restores(self):
        f=Fake(); report={}
        data,_=m.acquire(f,report,now=f.now,cancel=lambda:True)
        self.assertEqual(data,b'')
        self.assertTrue(report['operator_cancelled'])
        self.assertEqual(f.commands,[m.START,m.STOP])
        self.assertTrue(f.closed and f.restored)
    def run_case(self, channel):
        report = {}
        data, chunks = m.acquire(channel, report, now=channel.now)
        self.assertTrue(channel.closed)
        self.assertTrue(channel.restored)
        self.assertEqual(report['physical_rotor_stopped'], 'UNCONFIRMED')
        self.assertLessEqual(len(data), m.MAX_BYTES)
        return report, data, chunks
    def test_normal(self):
        f = Fake()
        r, data, chunks = self.run_case(f)
        self.assertEqual(f.commands, [m.START, m.STOP])
        self.assertTrue(r['data_quiet_after_stop'])
        self.assertEqual(sum(c['length'] for c in chunks), len(data))
    def test_failure_cleanup(self):
        for fault in ('write', 'read', 'interrupt', 'budget'):
            with self.subTest(fault=fault):
                f = Fake(fault)
                r, _, _ = self.run_case(f)
                self.assertIn('acquisition_error', r)
                self.assertEqual(f.commands, [m.START, m.STOP])
    def test_no_start_after_config_failure(self):
        f = Fake('configure')
        self.run_case(f)
        self.assertEqual(f.commands, [])
    def test_stop_retry_no_restart(self):
        f = Fake(quiet=(30, 0))
        r, _, _ = self.run_case(f)
        self.assertEqual(f.commands, [m.START, m.STOP, m.STOP])
        self.assertTrue(r['data_quiet_after_stop'])
    def test_unconfirmed_stop(self):
        f = Fake(quiet=(30, 20))
        r, _, _ = self.run_case(f)
        self.assertNotIn('data_quiet_after_stop', r)
        self.assertEqual(len(r['stop_attempts']), 2)
    def test_restore_failure_still_closes(self):
        r, _, _ = self.run_case(Fake('restore'))
        self.assertIn('restore_error', r)


if __name__ == '__main__':
    unittest.main()
