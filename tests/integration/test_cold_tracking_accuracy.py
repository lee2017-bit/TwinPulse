# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual cold App tracking against private evaluator truth, not pose injection.

Two fixed scaled recipe geometries, five changed XY/yaw starts each. This is
one O2 accuracy slice, not drift/loop, arbitrary-room or physical acceptance.
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
from twinpulse_core.room_localization import angle
from tests.integration import test_cold_start_mission as fixture

ROOT=Path(__file__).resolve().parents[2]
STARTS=((0.,-.6,0.),(.1,-.6,math.pi/2),(.2,-.4,math.pi),
        (-.2,-.6,.25),(.3,-.6,3*math.pi/4))
SOURCES=('tests/integration/test_cold_tracking_accuracy.py',
    'tests/integration/test_cold_start_mission.py',
    'tests/integration/test_automatic_mission_service.py',
    'tests/integration/test_automatic_photo_service.py',
    'packages/twinpulse_core/tests/test_room_localization.py',
    'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
    'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
    'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
    'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
    'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
    'packages/twinpulse_app/src/twinpulse_app/mission_photo_correction.py')


class ColdTrackingAccuracyTests(unittest.TestCase):
    def test_two_recipes_five_starts_tracking_accuracy_not_only_terminal_arrival(self):
        name=os.environ.get('TWINPULSE_ACCURACY_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        selected=os.environ.get('TWINPULSE_ACCURACY_CASE')
        identities={f'room{room}_start{i}' for room in (1,2) for i in range(5)}
        if selected:self.assertIn(selected,identities)
        outcomes=[];passed=[]
        for number,scale in ((1,1.),(2,1.2)):
            for index,start in enumerate(STARTS):
                identity=f'room{number}_start{index}'
                if selected and selected!=identity:continue
                with self.subTest(case=identity),TemporaryDirectory() as directory:
                    root=Path(directory);outline,_=fixture.recipe(root,identity,scale)
                    automatic=AutomaticDemoService(root,identity,geometry_loader=lambda:fixture.GEOMETRY)
                    service=AutomaticMissionService(automatic);adapters=[];observations=[]
                    # The goal is fixed before seeing any outcome, along the
                    # original heading. Truth is used ONLY by raycast/evaluator.
                    target=[start[0]+.15*math.cos(start[2]),start[1]+.15*math.sin(start[2])]
                    def factory(prior,room,effective,goal):
                        adapter=fixture.ColdAdapter(prior,room,effective,goal,outline=outline,start=start)
                        def observe(mission,result):
                            if mission.stage!='NAVIGATE':return
                            evidence=mission.last_evidence
                            if not evidence or evidence['state']!='TRACKING_CANDIDATE':return
                            observed=mission.visual('a'*32)['pose_room']
                            if observed is None:return
                            observations.append({'source_s':adapter.t,'observed':observed,
                                'truth':list(adapter.world),'xy_error_m':math.dist(observed[:2],adapter.world[:2]),
                                'yaw_error_rad':abs(angle(observed[2]-adapter.world[2]))})
                        adapter.observed_decision=observe;adapters.append(adapter);return adapter
                    factory.supports_local_correction=True;service.adapter_factory=factory
                    goal={'mode':'SURVEY_THEN_NAVIGATE','xy':target,'duration_s':45.,
                          'room_revision':service.readiness(None)['room_revision']}
                    try:
                        service.start('owner',None,goal,'correct_walls');service.worker.join(180)
                        finished=not service.worker.is_alive()
                        if not finished:
                            service.stop('owner',service.job['job_id'],force=True);service.worker.join(10)
                        job=service.snapshot('owner')['job'];adapter=adapters[0]
                        hits=sum(row['xy_error_m']<=.10 and row['yaw_error_rad']<=math.radians(5)
                                 for row in observations)
                        outcome={'case':identity,'scale':scale,'start':start,'goal':goal,
                            'state':job['state'],'reason':job.get('error'),'harness_finished':finished,
                            'tracking_samples':len(observations),'within_xy10cm_yaw5deg':hits,
                            'within_fraction':hits/len(observations) if observations else 0.,
                            'maximum_xy_error_m':max((r['xy_error_m'] for r in observations),default=None),
                            'maximum_yaw_error_rad':max((r['yaw_error_rad'] for r in observations),default=None),
                            'source_clock_at_end_s':adapter.t,'final_velocity':adapter.velocity,
                            'physical_validation':'NOT_RUN','source_basis':'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST'}
                        outcomes.append(outcome)
                        if name:
                            folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                            (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False,indent=2),encoding='utf-8')
                            (folder/'tracking-evaluation.json').write_text(json.dumps(observations,allow_nan=False),encoding='utf-8')
                            (folder/'synthetic-raw.json').write_text(json.dumps({'complete':not service.worker.is_alive(),
                                'observations':adapter.raw,'commands':adapter.sent},allow_nan=False),encoding='utf-8')
                            path=root/'artifacts/automatic-mission'/identity/f"{job['job_id']}.json"
                            if path.exists():(folder/'mission-report.json').write_bytes(path.read_bytes())
                        self.assertTrue(finished,outcome);self.assertEqual(job['state'],'MISSION_ARRIVED',outcome)
                        self.assertEqual(job['original_goal'],goal);self.assertEqual(job['goal']['xy'],target)
                        self.assertEqual(adapter.velocity,(0.,0.));self.assertFalse(job['physical_demo_ready'])
                        self.assertTrue(all(abs(v)<=.03 and abs(w)<=.2 for _,v,w in adapter.sent))
                        self.assertLess(adapter.t,65.);self.assertGreaterEqual(len(observations),3,outcome)
                        # Plan's pre-existing O2 criterion; no result-dependent
                        # threshold, dropped outliers or terminal-only accuracy.
                        self.assertGreaterEqual(outcome['within_fraction'],.95,outcome)
                        passed.append(identity)
                    finally:service.close();automatic.close()
        if name:
            folder=ROOT/'artifacts'/name
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==10 else 'PARTIAL_OR_FAILED',
                'expected_cases':10,'validated_cases':len(passed),'cases':outcomes,
                'criterion':{'xy_m':.10,'yaw_deg':5,'minimum_fraction':.95},
                'robot_connections':0,'physical_validation':'NOT_RUN','browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
