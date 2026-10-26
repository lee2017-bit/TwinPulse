# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The build refuses to start without a fresh Verify-Sprint PASS for the exact committed tree (P0-8)."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_windows_exe as build


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,text=True).stdout.strip()


class SprintGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        git(self.root,'init','-q');git(self.root,'config','user.email','t@example.invalid');git(self.root,'config','user.name','t')
        (self.root/'tracked.txt').write_text('a');git(self.root,'add','tracked.txt');git(self.root,'commit','-q','-m','one')
        self.head=git(self.root,'rev-parse','HEAD')

    def receipt(self,**changes):
        value=dict(schema='twinpulse-sprint-gate-1.0',run_id='r1',head=self.head,dirty=False,
            finished_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),status='PASS',steps=[])
        value.update(changes)
        path=self.root/'outputs/verify-sprint/latest.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('\ufeff'+json.dumps(value),encoding='utf-8')  # PowerShell UTF8 writes a BOM
        return value

    def test_missing_failed_stale_or_dirty_receipts_refuse_the_build(self):
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_RECEIPT_MISSING'):build.sprint_gate_receipt(self.root)
        self.receipt(status='FAIL')
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_FAILED'):build.sprint_gate_receipt(self.root)
        self.receipt(head='0'*40)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_STALE_COMMIT'):build.sprint_gate_receipt(self.root)
        self.receipt(dirty=True)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_DIRTY_TREE'):build.sprint_gate_receipt(self.root)
        old=(datetime.now(timezone.utc)-timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.receipt(finished_utc=old)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_STALE_TIME'):build.sprint_gate_receipt(self.root)
        self.receipt()
        (self.root/'tracked.txt').write_text('edited after the gate')
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_DIRTY_TREE'):build.sprint_gate_receipt(self.root)

    def test_fresh_pass_on_the_committed_head_is_accepted_and_untracked_files_do_not_matter(self):
        expected=self.receipt()
        (self.root/'scratch.txt').write_text('untracked')  # e.g. outputs/ or a local note
        self.assertEqual(build.sprint_gate_receipt(self.root)['run_id'],expected['run_id'])
        self.assertEqual(build.sprint_gate_receipt(self.root,max_age_s=60)['status'],'PASS')

    def test_build_main_checks_the_gate_before_tool_versions_unless_skipped(self):
        out=self.root/'never-created'
        with patch.object(build,'ROOT',self.root), patch.object(sys,'argv',['build','--output-dir',str(out)]):
            with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_RECEIPT_MISSING'):build.main()
        self.assertFalse(out.exists())
        with patch.object(build,'ROOT',self.root), patch.object(sys,'argv',['build','--output-dir',str(out),'--skip-sprint-gate']), \
                patch.object(build,'version',return_value='0.0'):
            with self.assertRaisesRegex(ValueError,'^BUILD_TOOL_VERSION_MISMATCH$'):build.main()


if __name__=='__main__':unittest.main()
