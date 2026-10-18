# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary temporary-directory ENOSPC injection; no user runtime faults."""
import errno
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('backend_status_test',
    Path(__file__).resolve().parents[2]/'scripts/twinpulse_backend.py')
backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)


class BackendStatusStorageTests(unittest.TestCase):
    def test_optional_status_failure_is_counted_and_later_write_recovers(self):
        diagnostics=SimpleNamespace(note_storage_error=Mock())
        broker=SimpleNamespace(diagnostics=diagnostics,supervisor_state=lambda:{'engine_session_id':'fixture'})
        with TemporaryDirectory() as root:
            path=Path(root)/'status.json'
            with patch.object(backend,'_write_json_atomic',side_effect=OSError(errno.ENOSPC,'fixture only')):
                self.assertFalse(backend._publish_engine_status(path,broker))
            diagnostics.note_storage_error.assert_called_once_with()
            self.assertTrue(backend._publish_engine_status(path,broker))
            self.assertEqual(json.loads(path.read_text())['engine_session_id'],'fixture')

    def test_failed_atomic_write_preserves_last_status_and_cleans_own_temp(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'status.json';path.write_text('{"last":"kept"}')
            before=path.read_bytes()
            with patch.object(Path,'write_text',side_effect=OSError(errno.ENOSPC,'fixture only')):
                with self.assertRaises(OSError):backend._write_json_atomic(path,{'next':'not saved'})
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual([p.name for p in Path(root).iterdir()],['status.json'])
