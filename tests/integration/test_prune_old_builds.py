# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prune-Old-Builds keeps the active, protected and newest releases and removes nothing without --delete and DELETE."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import prune_old_builds as prune


class PruneOldBuildsTests(unittest.TestCase):
    IDS=['20261025T120155Z-cb02064b5674','20261026T010000Z-aaaaaaaaaaaa','20261026T020000Z-bbbbbbbbbbbb',
         '20261026T030000Z-cccccccccccc','20261026T040000Z-dddddddddddd','20261026T050000Z-eeeeeeeeeeee']

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in self.IDS+['.stage-abc','not-a-release']:
            (self.root/'releases'/name).mkdir(parents=True);(self.root/'releases'/name/'TwinPulse.exe').write_bytes(b'x'*10)
        (self.root/'active-release.json').write_text(json.dumps({'release_id':self.IDS[1],'exe':'releases/%s/TwinPulse.exe'%self.IDS[1]}))

    def test_plan_keeps_active_protected_and_newest_and_ignores_other_directories(self):
        candidates,kept=prune.plan(self.root,active=self.IDS[1],keep_newest=2)
        self.assertEqual([c for c,_ in candidates],[self.IDS[2],self.IDS[3]])
        self.assertEqual(dict(kept),{self.IDS[0]:'protected evidence build',self.IDS[1]:'active release',
                                     self.IDS[4]:'newest 2',self.IDS[5]:'newest 2'})
        for name in prune.PROTECTED:self.assertRegex(name,prune.RELEASE_ID)

    def test_dry_run_is_the_default_and_delete_needs_the_word(self):
        out=io.StringIO()
        with redirect_stdout(out):code=prune.main(['--root',str(self.root),'--keep-newest','2'])
        self.assertEqual(code,0);self.assertIn('dry run',out.getvalue())
        self.assertTrue(all((self.root/'releases'/name).is_dir() for name in self.IDS))
        with redirect_stdout(io.StringIO()),patch.object(prune,'twinpulse_running',return_value=False),patch('builtins.input',return_value='yes'):
            self.assertEqual(prune.main(['--root',str(self.root),'--keep-newest','2','--delete']),1)
        self.assertTrue(all((self.root/'releases'/name).is_dir() for name in self.IDS))
        with redirect_stdout(io.StringIO()),patch.object(prune,'twinpulse_running',return_value=True),patch('builtins.input',return_value='DELETE'):
            self.assertEqual(prune.main(['--root',str(self.root),'--delete']),2)
        with redirect_stdout(io.StringIO()),patch.object(prune,'twinpulse_running',return_value=False),patch('builtins.input',return_value='DELETE'):
            self.assertEqual(prune.main(['--root',str(self.root),'--keep-newest','2','--delete']),0)
        remaining=sorted(p.name for p in (self.root/'releases').iterdir())
        self.assertEqual(remaining,sorted(['.stage-abc','not-a-release',self.IDS[0],self.IDS[1],self.IDS[4],self.IDS[5]]))
        self.assertTrue((self.root/'active-release.json').is_file())


if __name__=='__main__':unittest.main()
