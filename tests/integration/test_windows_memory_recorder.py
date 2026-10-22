# SPDX-License-Identifier: Apache-2.0
"""OS counter/identity diagnostics tests; never App/robot acceptance."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('memory_recorder',ROOT/'scripts/record_windows_memory_20261021.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class MemoryRecorderTests(unittest.TestCase):
    def test_reused_parent_pid_does_not_attribute_older_child(self):
        rows=[dict(pid=1,parent_pid=0,name='TwinPulse.exe',created_unix_ms=10000),
            dict(pid=2,parent_pid=1,name='unrelated.exe',created_unix_ms=1000),
            dict(pid=3,parent_pid=1,name='TwinPulseDesktop.exe',created_unix_ms=10001)]
        result=module.classify(rows,dict(owner_pid=1,launch_started_ms=10000))
        self.assertEqual([r['role'] for r in result],['owner','other','owner_child'])

    def test_missing_or_changed_owner_creation_does_not_attribute(self):
        for stamp in (None,-20000,50000):
            rows=[dict(pid=1,parent_pid=0,name='TwinPulse.exe',created_unix_ms=stamp)]
            result=module.classify(rows,dict(owner_pid=1,launch_started_ms=10000))
            self.assertEqual(result[0]['role'],'unattributed_twinpulse')

    def test_actual_windows_counters_keep_physical_commit_and_pagefile_separate(self):
        counters=module.Counters();value=counters.system()
        self.assertGreaterEqual(value['PhysicalTotal_bytes'],value['PhysicalAvailable_bytes'])
        self.assertGreaterEqual(value['CommitLimit_bytes'],value['CommitTotal_bytes'])
        self.assertIsInstance(value['pagefiles'],list)
        rows=counters.processes();own=next(r for r in rows if r['pid']==module.os.getpid())
        self.assertGreater(own['working_set_bytes'],0);self.assertGreater(own['private_committed_bytes'],0)
        self.assertNotIn('command_line',own);json.dumps(rows,allow_nan=False)

    def test_bounded_reader_rejects_large_malformed_and_non_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'value.json'
            for raw in ('[]','invalid','x'*131073):
                path.write_text(raw);self.assertEqual(module.small(path),{})

if __name__=='__main__':unittest.main()
