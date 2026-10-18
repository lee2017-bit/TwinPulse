# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Stored map reopen -> fresh sensors -> actual mission and active display.

No saved pose, injected matcher result, robot, or renderer acceptance.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import unittest

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_core.active_mission_visual import checked_active_frame
from tests.integration import test_automatic_mission_service as fixture
from packages.twinpulse_core.tests.test_room_localization import scan_points

ROOT=Path(__file__).resolve().parents[2]


class BoundaryAdapter(fixture.RaycastAdapter):
    def __init__(self,*args,scenario,**kwargs):
        super().__init__(*args,**kwargs);self.scenario=scenario;self.decisions=[]
        self.entered=threading.Event();self.release=threading.Event();self.paused=False
    def spin(self,dt):
        # Pause only after the shared worker has recorded a real decision.
        ready=(self.scenario=='dense' and len(self.sent)>=3 or
               self.scenario=='different_room' and self.decisions)
        if ready and not self.paused:
            self.paused=True;self.entered.set();self.release.wait(20)
        super().spin(dt)
    def observation_points(self):
        outline=copy.deepcopy(self.outline)
        if self.scenario=='different_room':
            outline['segments']=[[[1.4*x,1.4*y] for x,y in pair] for pair in outline['segments']]
        return scan_points(outline,self.world,beam_count=720 if self.scenario=='dense' else 24 if self.scenario=='sparse' else 120)
    def observed_decision(self,mission,result):
        self.decisions.append({'t':self.t,'decision':copy.deepcopy(result),'visual':mission.visual('a'*32)})


class ObservationBoundaryTests(unittest.TestCase):
    def test_reopened_map_never_restores_pose_and_dense_scan_reaches_active_api(self):
        helper=fixture.AutomaticMissionTests();self.addCleanup(helper.doCleanups);helper.setUp()
        helper.service.close();helper.automatic.close()
        name=os.environ.get('TWINPULSE_BOUNDARY_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[]
        for scenario,start,target in (
                ('dense',[0.,-.6,0.],[.05,-.6]),
                ('revisit',[-.3,-.4,.25],[-.14,-.4]),
                ('sparse',[0.,-.6,0.],[.05,-.6]),
                ('different_room',[0.,-.6,0.],[.05,-.6])):
            with self.subTest(scenario=scenario):
                automatic=AutomaticDemoService(helper.root,'mission_room')
                service=AutomaticMissionService(automatic)
                self.addCleanup(automatic.close);self.addCleanup(service.close)
                prior=automatic.reopen('owner',helper.map_id)
                self.assertIsNone(prior['pose_candidate']);self.assertFalse(prior['motion_authorized'])
                adapters=[]
                def factory(prior,room,effective,goal):
                    a=BoundaryAdapter(prior,room,effective,goal,outline=helper.outline,start=start,
                                      scenario=scenario)
                    adapters.append(a);return a
                service.adapter_factory=factory
                goal={'mode':'NAVIGATE_TWIN_GOAL','xy':target,'duration_s':45.,
                      'room_revision':service.readiness(helper.map_id)['room_revision']}
                service.start('owner',helper.map_id,goal);active=None;display_error=None
                try:
                    if scenario in ('dense','different_room'):
                        # Factory runs in the owned worker, so wait on its
                        # actual adapter publication, not a prescribed result.
                        import time
                        deadline=time.monotonic()+20
                        while not adapters and time.monotonic()<deadline:time.sleep(.01)
                        self.assertTrue(adapters,'worker did not create its adapter')
                        self.assertTrue(adapters[0].entered.wait(20),'worker did not record the first bounded observation')
                        try:active=service.active_visual('engine','epoch',service.job['objects_revision'])
                        except ValueError as exc:display_error=str(exc)
                        if scenario=='different_room':service.stop('owner',service.job['job_id'],force=True)
                finally:
                    for a in adapters:a.release.set()
                    service.worker.join(70)
                self.assertFalse(service.worker.is_alive())
                job=service.snapshot('owner')['job'];adapter=adapters[0]
                report=json.loads((helper.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json").read_text())
                outcome={'scenario':scenario,'state':job['state'],'reason':job.get('error'),
                         'start':start,'target':target,'final_world':adapter.world,
                         'truth_error_m':math.dist(adapter.world[:2],target),
                         'first_odom':adapter.raw[0]['odom'],'raw_beams':len(adapter.raw[0]['ranges']),
                         'display_beams':len((report.get('visual') or {}).get('scan_room',[])),
                         'display_error':display_error,
                         'decision_reasons':sorted({d['decision']['reason'] for d in adapter.decisions}),
                         'final_velocity':list(adapter.velocity),'physical_validation':'NOT_RUN'}
                outcomes.append(outcome)
                if name:
                    folder=ROOT/'artifacts'/name/scenario;folder.mkdir(parents=True,exist_ok=False)
                    for filename,value in (('observations.json',adapter.raw),('commands.json',adapter.sent),
                            ('decisions.json',adapter.decisions),('report.json',report),('active.json',active),('outcome.json',outcome)):
                        (folder/filename).write_text(json.dumps(value,indent=2))
                self.assertTrue(all(abs(v)<1e-10 for v in adapter.raw[0]['odom']))
                self.assertEqual(adapter.consumed,1);self.assertEqual(adapter.velocity,(0.,0.))
                self.assertFalse(report['physical_demo_ready'])
                if scenario in ('dense','revisit'):
                    self.assertEqual(job['state'],'MISSION_ARRIVED',outcome)
                    self.assertLess(outcome['truth_error_m'],.10,outcome)
                    self.assertTrue(0<len(report['visual']['scan_room'])<=160,outcome)
                    if scenario=='dense':
                        self.assertIsNone(display_error,outcome)
                        self.assertEqual(active['code'],'CURRENT_VISUAL_CANDIDATE_NOT_CALIBRATED')
                        checked_active_frame(active['frame'])
                        self.assertEqual(len(adapter.tracker.capture['points']),720)
                        self.assertEqual(len(active['frame']['visual']['scan_room']),144)
                else:
                    self.assertEqual(job['state'],'FORCE_STOPPED' if scenario=='different_room' else 'FAILED',outcome)
                    visual=report.get('visual') or {}
                    self.assertIsNone(visual.get('pose_room'));self.assertFalse(visual.get('scan_room'))
                    if scenario=='sparse':self.assertEqual(job['error'],'SCAN_COVERAGE_UNKNOWN')
                    else:
                        self.assertEqual(active['code'],'CURRENT_ROOM_POSE_UNAVAILABLE')
                        self.assertEqual(adapter.decisions[0]['decision']['reason'],'CURRENT_LOCALIZATION_REQUIRED')
                    self.assertFalse(any(v or w for _,v,w in adapter.sent),outcome)
                service.close();automatic.close()
        if name:
            folder=ROOT/'artifacts'/name
            paths=('packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
                   'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
                   'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
                   'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
                   'packages/twinpulse_core/src/twinpulse_core/active_mission_visual.py',
                   'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
                   'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                   'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
                   'tests/integration/test_automatic_mission_service.py',
                   'packages/twinpulse_core/tests/test_room_localization.py',
                   'tests/integration/test_mission_observation_boundaries.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS','cases':outcomes,
                'basis':'OUTPUT_REACTIVE_SYNTHETIC_SENSORS','browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'robot_connections':0,'physical_validation':'NOT_RUN',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in folder.rglob('*.json')}},indent=2))


if __name__=='__main__':unittest.main()
