# SPDX-License-Identifier: Apache-2.0
"""Actual Win32 immutable-publication sharing; no App or hardware activity."""
import ctypes
import json
import os
from threading import Thread, Event
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.integration.test_engine_loss_probe import ROOT, EngineLossProbe
from twinpulse_app.process_manager import _engine_status_win_api, _read_engine_status_bytes, _read_engine_status


@unittest.skipUnless(os.name == 'nt', 'Actual Win32 file sharing required')
class EngineStatusWindowsReadTests(unittest.TestCase):
    def setUp(self):
        self.parent = ROOT / 'outputs' / 'status-file-fixtures'
        self.parent.mkdir(parents=True, exist_ok=True)
        self.temporary = TemporaryDirectory(dir=self.parent)
        self.folder = Path(self.temporary.name).resolve()
        self.assertTrue(self.folder.is_relative_to(self.parent.resolve()))
        self.path = self.folder / 'status.json'
        self.old = dict(status_sample_id=11, engine_session_id='e', engine_connected=True,
                        physical_runtime_active=False, sampled_at_utc='original-publication-time')
        self.new = dict(self.old, status_sample_id=12)
        self.old_bytes = json.dumps(self.old).encode()
        self.path.write_bytes(self.old_bytes)

    def tearDown(self):
        self.assertTrue(self.folder.is_relative_to(self.parent.resolve()))
        self.temporary.cleanup()

    def test_post_rename_delete_handle_allows_new_reader_but_crt_denies_it(self):
        """Pause after native rename, before its DELETE-capable handle closes.

        This exercises read acquisition, not POSIX overwrite of an open target.
        The latter is NOT guaranteed by ordinary MoveFileEx/os.replace.
        """
        replacement = self.folder / 'replacement.tmp'
        replacement.write_bytes(json.dumps(self.new).encode())
        kernel = _engine_status_win_api()
        handle = kernel.CreateFileW(str(replacement), 0x80000000 | 0x10000, 7, None, 3, 128, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            os.replace(replacement, self.path)
            with self.assertRaises(PermissionError) as caught:
                self.path.read_bytes()
            # CRT reports errno13 but drops native GetLastError (as original11).
            self.assertEqual(caught.exception.errno, 13)
            denied = kernel.CreateFileW(str(self.path), 0x80000000, 3, None, 3, 128, None)
            self.assertEqual(denied, ctypes.c_void_p(-1).value)
            self.assertEqual(ctypes.get_last_error(), 32)
            value, info = _read_engine_status(self.path)
            self.assertEqual(value, self.new)
            self.assertIsNone(info)
            self.assertEqual(value['sampled_at_utc'], 'original-publication-time')
        finally:
            self.assertTrue(kernel.CloseHandle(handle))
        self.assertEqual(json.loads(self.path.read_bytes()), self.new)

    def test_pinned_read_returns_original_bytes_and_closes_handle_once(self):
        kernel = _engine_status_win_api()
        closed = []
        def close(handle):
            closed.append(handle)
            return kernel.CloseHandle(handle)
        api = SimpleNamespace(CreateFileW=kernel.CreateFileW, ReadFile=kernel.ReadFile, CloseHandle=close)
        with patch('twinpulse_app.process_manager._engine_status_win_api', return_value=api):
            observed = _read_engine_status_bytes(self.path, 1024*1024+1)
        self.assertEqual(observed, self.old_bytes)
        self.assertEqual(len(closed), 1)

    def test_ordinary_replace_of_pinned_destination_is_not_promised_by_reader(self):
        replacement = self.folder / 'replacement.tmp'
        replacement.write_bytes(json.dumps(self.new).encode())
        with self.path.open('rb'):
            with self.assertRaises(PermissionError):
                os.replace(replacement, self.path)
        os.replace(replacement, self.path)
        self.assertEqual(json.loads(_read_engine_status_bytes(self.path, 1024*1024+1)), self.new)

    def test_concurrent_original_atomic_writer_and_shared_reader(self):
        # The publisher contract remains same-directory os.replace, 50x10ms.
        import importlib.util
        spec = importlib.util.spec_from_file_location('status_test_backend', ROOT/'scripts/twinpulse_backend.py')
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        done = Event()
        failures = []
        def publish():
            try:
                for sample_id in range(12, 212):
                    backend._write_json_atomic(self.path, dict(self.old, status_sample_id=sample_id))
            except BaseException as error:
                failures.append(repr(error))
            finally:
                done.set()
        writer = Thread(target=publish)
        writer.start()
        observations = []
        try:
            while not done.is_set():
                value, info = _read_engine_status(self.path)
                self.assertIsNotNone(value, info)
                self.assertEqual(value['sampled_at_utc'], 'original-publication-time')
                self.assertFalse(value['physical_runtime_active'])
                observations.append(value['status_sample_id'])
        finally:
            writer.join(10.)
        self.assertFalse(writer.is_alive())
        self.assertEqual(failures, [])
        self.assertGreater(len(observations), 0)
        self.assertEqual(observations, sorted(observations))
        self.assertEqual(_read_engine_status(self.path)[0]['status_sample_id'], 211)

    def test_actual_denied_read_preserves_exact_winerror_and_fails_closed(self):
        kernel = _engine_status_win_api()
        handle = kernel.CreateFileW(str(self.path), 0x80000000, 0, None, 3, 128, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            value, info = _read_engine_status(self.path)
        finally:
            self.assertTrue(kernel.CloseHandle(handle))
        self.assertIsNone(value)
        self.assertEqual(len(info['failures']), 3)
        self.assertTrue(all(f['winerror'] == 32 and f['phase'] == 'open_shared_delete'
                            and f['elapsed_s'] >= 0 for f in info['failures']))
        self.assertEqual(EngineLossProbe(lambda: 0.).observe(value), 'failed')
        self.assertEqual(_read_engine_status(self.path)[0], self.old)

    def test_invalid_oversized_and_frozen_publications_keep_original_rejections(self):
        for raw, reason in ((b'[]', 'non_object_status'), (b'x'*(1024*1024+1), 'oversized_status'),
                            (b'\xff', 'status_read_failed'), (b'{', 'status_read_failed')):
            self.path.write_bytes(raw)
            value, info = _read_engine_status(self.path)
            self.assertIsNone(value)
            self.assertEqual(info['reason'], reason)
        self.path.write_bytes(self.old_bytes)
        now = [0.]
        probe = EngineLossProbe(lambda: now[0])
        self.assertEqual(probe.observe(_read_engine_status(self.path)[0]), 'healthy')
        now[0] = 3.
        self.assertEqual(probe.observe(_read_engine_status(self.path)[0]), 'failed')


if __name__ == '__main__':
    unittest.main()
