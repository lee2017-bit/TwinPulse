# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Symmetric room -> actual cold App/fit rejection, never manual pairing."""
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.room_recipe import import_project_room_recipe
from tests.integration import test_cold_start_mission as fixture

ROOT=Path(__file__).resolve().parents[2]


def square_recipe(root,identity):
    fixture.recipe(root,identity,1.,import_now=False)
    path=root/'projects'/identity/'room_recipe.json'
    value=json.loads(path.read_text(encoding='utf-8'))
    vertices=[[-1.5,-1.5],[1.5,-1.5],[1.5,1.5],[-1.5,1.5]]
    segments=[[vertices[i],vertices[(i+1)%4]] for i in range(4)]
    calls=[{'call_id':'floor','tool':'create_floor',
            'arguments':{'id':'floor','center_m':[0,0],'size_m':[3,3]}}]
    for i,(a,b) in enumerate(segments):
        identity_wall=f'wall_{i}'
        calls.append({'call_id':identity_wall,'tool':'create_wall','arguments':{
            'id':identity_wall,'position_m':[(a[0]+b[0])/2,(a[1]+b[1])/2,1.2],
            'dimensions_m':[3,.04,2.4],
            'yaw_deg':math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))}})
    value['plan']['calls']=calls
    value['plan']['call_evidence']=[{'call_id':c['call_id'],'observation_ids':[],
        'basis':'inferred','note':'Symmetric synthetic regression, not a measured room'} for c in calls]
    path.write_text(json.dumps(value),encoding='utf-8');import_project_room_recipe(root,identity)
    return {'bounds_m':[-1.5,1.5,-1.5,1.5],'segments':segments}


class ColdSymmetryRejectionTests(unittest.TestCase):
    def test_two_changed_start_headings_reject_ambiguous_photo_before_goal_navigation(self):
        name=os.environ.get('TWINPULSE_SYMMETRY_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        for index,start in enumerate(([0.,-.6,.1],[-.2,-.5,1.])):
            identity=f'symmetric_{index}'
            with self.subTest(case=identity),TemporaryDirectory() as directory:
                root=Path(directory);outline=square_recipe(root,identity)
                original=(root/'projects'/identity/'room_recipe.json').read_bytes()
                automatic=AutomaticDemoService(root,identity,geometry_loader=lambda:fixture.GEOMETRY)
                service=AutomaticMissionService(automatic);adapters=[];decisions=[]
                def factory(prior,room,effective,goal):
                    adapter=fixture.ColdAdapter(prior,room,effective,goal,outline=outline,start=start)
                    def observe(mission,result):
                        decisions.append({'source_s':adapter.t,'stage':mission.stage,'decision':result,
                            'world':list(adapter.world)})
                    adapter.observed_decision=observe;adapters.append(adapter);return adapter
                factory.supports_local_correction=True;service.adapter_factory=factory
                goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[.15,-.6],'duration_s':45.,
                      'room_revision':service.readiness(None)['room_revision']}
                try:
                    service.start('owner',None,goal,'correct_walls');service.worker.join(180)
                    complete=not service.worker.is_alive()
                    if not complete:
                        service.stop('owner',service.job['job_id'],force=True);service.worker.join(10)
                    job=service.snapshot('owner')['job'];adapter=adapters[0]
                    path=root/'artifacts/automatic-mission'/identity/f"{job['job_id']}.json"
                    report=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
                    outcome={'case':identity,'start':start,'state':job['state'],'reason':job.get('error'),
                        'cold_start':job.get('cold_start'),'complete':complete,
                        'navigation_ticks':sum(row['stage']=='NAVIGATE' for row in decisions),
                        'final_velocity':adapter.velocity,'physical_validation':'NOT_RUN',
                        'source_basis':'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST'}
                    outcomes.append(outcome)
                    if name:
                        folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                        (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False,indent=2),encoding='utf-8')
                        (folder/'synthetic-raw.json').write_text(json.dumps({'complete':not service.worker.is_alive(),
                            'observations':adapter.raw,'commands':adapter.sent,'decisions':decisions},allow_nan=False),encoding='utf-8')
                        if path.exists():(folder/'mission-report.json').write_bytes(path.read_bytes())
                    self.assertTrue(complete,outcome);self.assertEqual(job['state'],'FAILED',outcome)
                    self.assertEqual(job['error'],'COLD_START_PHOTO_AMBIGUOUS',outcome)
                    self.assertEqual(outcome['navigation_ticks'],0)
                    self.assertEqual(adapter.velocity,(0.,0.));self.assertTrue(adapter.raw)
                    self.assertIsNone(report['visual']['pose_room']);self.assertFalse(report['visual']['scan_room'])
                    self.assertFalse(report['physical_demo_ready']);self.assertEqual(job['goal'],goal)
                    self.assertNotIn('photo_correction',report)
                    self.assertTrue(all(not(row['decision']['linear_m_s'] or row['decision']['angular_rad_s'])
                        for row in decisions if row['stage']=='ALIGN'))
                    self.assertEqual((root/'projects'/identity/'room_recipe.json').read_bytes(),original)
                    passed.append(identity)
                finally:service.close();automatic.close()
        if name:
            folder=ROOT/'artifacts'/name
            sources=('tests/integration/test_cold_symmetry_rejection.py',
                'tests/integration/test_cold_start_mission.py','tests/integration/test_automatic_mission_service.py',
                'tests/integration/test_automatic_photo_service.py','packages/twinpulse_core/tests/test_room_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
                'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
                'packages/twinpulse_core/src/twinpulse_core/automatic_photo_alignment.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                'packages/twinpulse_app/src/twinpulse_app/mission_photo_correction.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==2 else 'FAILED',
                'cases':outcomes,'robot_connections':0,'physical_validation':'NOT_RUN',
                'browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
