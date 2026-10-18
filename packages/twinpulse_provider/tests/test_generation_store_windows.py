# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary storage fault tests; not model/user acceptance."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from twinpulse_core import canonical_sha256
from twinpulse_provider.generation_store import GenerationStore


class CheckpointReplaceTests(unittest.TestCase):
    def test_transient_same_local_replace_keeps_history_and_payload(self):
        with TemporaryDirectory() as folder:
            store = GenerationStore(folder)
            key = 'a' * 64
            store.save('checkpoint', key, {'phase': 'before'})
            original_replace = os.replace
            attempts = []
            denied = PermissionError('Supplementary transient Windows reader')
            denied.winerror = 5

            def replace(source, destination):
                attempts.append((source, destination, Path(source).read_bytes()))
                if len(attempts) < 3:
                    raise denied
                original_replace(source, destination)

            with patch('twinpulse_provider.generation_store._WINDOWS', True), \
                    patch('twinpulse_provider.generation_store.os.replace', side_effect=replace), \
                    patch('twinpulse_provider.generation_store.time.sleep') as sleep:
                store.save('checkpoint', key, {'phase': 'after'})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(len(set(attempts)), 1)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [.025, .05])
            self.assertEqual(store.read('checkpoint', key), {'phase': 'after'})
            self.assertEqual(len(list((Path(folder)/'checkpoint-history'/key).glob('*.json'))), 2)

    def test_persistent_denial_keeps_old_pointer_and_both_immutable_versions(self):
        with TemporaryDirectory() as folder:
            store = GenerationStore(folder)
            key = 'b' * 64
            before, after = {'phase': 'before'}, {'phase': 'after'}
            store.save('checkpoint', key, before)
            denied = PermissionError('Supplementary persistent denial')
            denied.winerror = 5
            with patch('twinpulse_provider.generation_store._WINDOWS', True), \
                    patch('twinpulse_provider.generation_store.os.replace', side_effect=denied) as replace, \
                    patch('twinpulse_provider.generation_store.time.sleep') as sleep:
                with self.assertRaises(PermissionError) as raised:
                    store.save('checkpoint', key, after)
            self.assertIs(raised.exception, denied)
            self.assertEqual(replace.call_count, 7)
            self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list), 1.575)
            self.assertEqual(store.read('checkpoint', key), before)
            history = Path(folder)/'checkpoint-history'/key/(canonical_sha256(after)+'.json')
            self.assertEqual(json.loads(history.read_text())['payload'], after)

    def test_other_errors_fail_immediately(self):
        for error in (PermissionError('POSIX denial'), OSError(28, 'disk full')):
            with self.subTest(error=error), TemporaryDirectory() as folder:
                with patch('twinpulse_provider.generation_store._WINDOWS', True), \
                        patch('twinpulse_provider.generation_store.os.replace', side_effect=error) as replace, \
                        patch('twinpulse_provider.generation_store.time.sleep') as sleep:
                    with self.assertRaises(OSError):
                        GenerationStore(folder).save('checkpoint', 'c'*64, {'phase': 'new'})
                self.assertEqual(replace.call_count, 1)
                sleep.assert_not_called()

    def test_cleanup_error_does_not_mask_the_primary_failure(self):
        with TemporaryDirectory() as folder:
            primary = OSError(28, 'disk full at replace')
            cleanup = PermissionError('temporary cleanup denied')
            with patch('twinpulse_provider.generation_store.os.replace', side_effect=primary), \
                    patch.object(Path, 'unlink', side_effect=cleanup):
                with self.assertRaises(OSError) as raised:
                    GenerationStore(folder).save('checkpoint', 'e'*64, {'phase': 'new'})
            self.assertIs(raised.exception, primary)
            self.assertIn('cleanup also failed', raised.exception.__notes__[0])
            self.assertEqual(len(list(Path(folder).rglob('*.tmp'))), 1)

    def test_non_checkpoint_storage_is_not_retried(self):
        with TemporaryDirectory() as folder:
            denied = PermissionError('observation write denied')
            denied.winerror = 5
            with patch('twinpulse_provider.generation_store._WINDOWS', True), \
                    patch('twinpulse_provider.generation_store.os.replace', side_effect=denied) as replace, \
                    patch('twinpulse_provider.generation_store.time.sleep') as sleep:
                with self.assertRaises(PermissionError):
                    GenerationStore(folder).save('observation', 'f'*64, {'phase': 'new'})
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Actual Win32 sharing semantics required')
    def test_actual_windows_reader_release_allows_atomic_replacement(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with TemporaryDirectory() as folder:
            store = GenerationStore(folder)
            key = 'd' * 64
            store.save('checkpoint', key, {'phase': 'before'})
            destination = Path(folder)/'checkpoint'/(key+'.json')
            handle = kernel.CreateFileW(str(destination), 0x80000000, 1, None, 3, 128, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            probe = Path(folder)/'probe.tmp'
            probe.write_bytes(b'not a checkpoint')
            try:
                with self.assertRaises(OSError) as denied:
                    os.replace(probe, destination)
                self.assertIn(denied.exception.winerror, (5, 32, 33))
                release = threading.Timer(.08, lambda: kernel.CloseHandle(handle))
                release.start()
                try:
                    store.save('checkpoint', key, {'phase': 'after'})
                finally:
                    release.join()
                    handle = None
                self.assertEqual(store.read('checkpoint', key), {'phase': 'after'})
                self.assertEqual(len(list((Path(folder)/'checkpoint-history'/key).glob('*.json'))), 2)
            finally:
                if handle is not None:
                    kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
