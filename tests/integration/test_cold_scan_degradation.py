# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual cold App runner with fixed ray density/noise and unknown returns.

NaN is absent evidence, not free space. Positive fixtures keep their original
goal and guards; evaluator truth never enters localization or navigation.
"""
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from packages.twinpulse_core.tests.test_room_localization import scan_points
from tests.integration import test_cold_start_mission as fixture

ROOT=Path(__file__).resolve().parents[2]
CASES=(('minimum_72',72,False),('dense_noise_240',240,False),
       ('insufficient_71',71,False),('unknown_sector_120',120,True))
SOURCES=('tests/integration/test_cold_scan_degradation.py',
    'tests/integration/test_cold_start_mission.py','tests/integration/test_automatic_mission_service.py',
    'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
    'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
    'packages/twinpulse_core/src/twinpulse_core/local_navigation.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py')


class ColdScanDegradationTests(unittest.TestCase):
    def test_density_and_noise_positive_unknown_coverage_rejected_before_motion(self):
        name=os.environ.get('TWINPULSE_DEGRADED_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        for identity,count,unknown in CASES:
            with self.subTest(case=identity),TemporaryDirectory() as directory:
                root=Path(directory);outline,_=fixture.recipe(root,identity,1.)
                automatic=AutomaticDemoService(root,identity,geometry_loader=lambda:fixture.GEOMETRY)
                service=AutomaticMissionService(automatic);adapters=[]
                def factory(prior,room,effective,goal):
                    adapter=fixture.ColdAdapter(prior,room,effective,goal,outline=outline,start=[0.,-.6,0.])
                    def points():
                        values=scan_points(outline,adapter.world,beam_count=count)
                        if unknown:
                            for i in range(20,35):values[i]=[float('nan'),float('nan')]
                        elif count==240:
                            # Predetermined bounded radial measurement noise;
                            # no pose or outcome-dependent filtering.
                            for i,p in enumerate(values):
                                r=math.hypot(*p);factor=1+.002*math.sin(i*1.7)/r
                                values[i]=[p[0]*factor,p[1]*factor]
                        return values
                    adapter.observation_points=points;adapters.append(adapter);return adapter
                factory.supports_local_correction=True;service.adapter_factory=factory
                goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],
                      'room_revision':service.readiness(None)['room_revision'],'duration_s':45.}
                try:
                    service.start('owner',None,goal,'correct_walls');service.worker.join(180)
                    complete=not service.worker.is_alive()
                    if not complete:service.stop('owner',service.job['job_id'],force=True);service.worker.join(10)
                    job=service.snapshot('owner')['job'];adapter=adapters[0]
                    outcome={'case':identity,'beams':count,'unknown_sector':unknown,'complete':complete,
                        'state':job['state'],'error':job.get('error'),'cold_start':job.get('cold_start'),
                        'final_world':adapter.world,'goal':goal,'truth_error_m':math.dist(adapter.world[:2],goal['xy']),
                        'final_velocity':adapter.velocity,'physical_validation':'NOT_RUN'};outcomes.append(outcome)
                    if name:
                        folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                        (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False),encoding='utf-8')
                        # NaN raw is intentionally retained as fixture input,
                        # not an accepted JSON observation/derived map value.
                        (folder/'synthetic-raw.json').write_text(json.dumps({'complete':complete,
                            'observations':adapter.raw,'commands':adapter.sent}),encoding='utf-8')
                        path=root/'artifacts/automatic-mission'/identity/f"{job['job_id']}.json"
                        if path.exists():(folder/'mission-report.json').write_bytes(path.read_bytes())
                    self.assertTrue(complete,outcome);self.assertEqual(adapter.velocity,(0.,0.))
                    self.assertFalse(job['physical_demo_ready']);self.assertEqual(job['original_goal'],goal)
                    if count>=72 and not unknown:
                        self.assertEqual(job['state'],'MISSION_ARRIVED',outcome);self.assertLess(outcome['truth_error_m'],.10)
                        self.assertLess(adapter.t,65.)
                    else:
                        self.assertEqual(job['state'],'FAILED',outcome);self.assertEqual(job['error'],'SCAN_COVERAGE_UNKNOWN')
                        self.assertFalse(any(v or w for _,v,w in adapter.sent));self.assertNotIn('photo_correction',job)
                        self.assertIsNone((job.get('visual') or {}).get('pose_room'))
                    passed.append(identity)
                finally:service.close();automatic.close()
        if name:
            folder=ROOT/'artifacts'/name
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==4 else 'FAILED',
                'validated_cases':passed,'cases':outcomes,'robot_connections':0,'physical_validation':'NOT_RUN',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
