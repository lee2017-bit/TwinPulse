# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Report storage fault on actual App/shared mission, independent final halt."""
import errno
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.integration import test_automatic_mission_service as fixture

ROOT=Path(__file__).resolve().parents[2]


class MissionReportStorageTests(unittest.TestCase):
    def test_full_and_denied_storage_keep_first_cause_clear_pose_and_safe_errno(self):
        name=os.environ.get('TWINPULSE_STORAGE_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        helper=fixture.AutomaticMissionTests();self.addCleanup(helper.doCleanups);helper.setUp()
        original_open=Path.open
        for identity,primary,number,expected in (
            ('full_after_arrival',None,errno.ENOSPC,'MISSION_REPORT_STORAGE_FULL'),
            ('denied_after_primary','battery',errno.EACCES,'MISSION_REPORT_PERMISSION_DENIED')):
            with self.subTest(case=identity):
                helper.configure([0.,-.6,0.],primary)
                def rejected_report(path,*args,**kwargs):
                    mode=args[0] if args else kwargs.get('mode','r')
                    if 'automatic-mission' in path.parts and mode=='x':
                        raise OSError(number,'credential=SECRET_CANARY host=C:/private')
                    return original_open(path,*args,**kwargs)
                with patch.object(Path,'open',rejected_report):
                    helper.service.start('owner',helper.map_id,helper.goal([.05,-.6]))
                    helper.service.worker.join(45)
                complete=not helper.service.worker.is_alive()
                if not complete:
                    helper.service.stop('owner',helper.service.job['job_id'],force=True);helper.service.worker.join(10)
                job=helper.service.snapshot('owner')['job'];adapter=helper.adapters[-1]
                outcome={'case':identity,'complete':complete,'job':job,'final_velocity':adapter.velocity,
                    'expected_errno':number,'physical_validation':'NOT_RUN'};outcomes.append(outcome)
                if name:
                    folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                    (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False),encoding='utf-8')
                    (folder/'synthetic-raw.json').write_text(json.dumps({'complete':complete,
                        'observations':adapter.raw,'commands':adapter.sent},allow_nan=False),encoding='utf-8')
                self.assertTrue(complete);self.assertEqual(adapter.velocity,(0.,0.));self.assertGreater(adapter.halted,0)
                self.assertEqual(job['state'],'FAILED');self.assertEqual(job['report_status'],'FAILED')
                visual=job.get('visual') or {}
                self.assertIsNone(visual.get('pose_room'),{k:job.get(k) for k in ('state','error','report_error')})
                self.assertFalse(visual.get('scan_room'))
                self.assertFalse(visual.get('route_room'));self.assertFalse(job['physical_demo_ready'])
                self.assertEqual(job['report_error'],expected);self.assertEqual(job['report_stage'],'REPORT_SAVE')
                self.assertEqual(job['report_error_type'],type(OSError(number,'' )).__name__)
                self.assertEqual(job['report_errno'],number)
                self.assertEqual(job['error'],'BATTERY_BUTTON_OR_SOURCE_AGE' if primary else expected)
                self.assertEqual(job['error_stage'],'RUN_CURRENT_MISSION' if primary else 'REPORT_SAVE')
                self.assertNotIn('SECRET_CANARY',json.dumps(job));self.assertNotIn('C:/private',json.dumps(job))
                self.assertTrue(job['error_record_failed']);self.assertFalse(job.get('report_revision'))
                self.assertEqual(helper.service.active_visual('engine','epoch',job['objects_revision'])['code'],'NO_ACTIVE_MISSION')
                passed.append(identity)
        if name:
            folder=ROOT/'artifacts'/name
            sources=('tests/integration/test_mission_report_storage_failure.py',
                'tests/integration/test_automatic_mission_service.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==2 else 'FAILED',
                'cases':[r['case'] for r in outcomes],'robot_connections':0,'physical_validation':'NOT_RUN',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
