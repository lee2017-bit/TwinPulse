# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Two recipe geometries, three fixed cold goals each; no answer injection."""
import hashlib
import json
import math
import os
from pathlib import Path
import unittest
from tests.integration import test_cold_start_mission as fixtures
from twinpulse_core.room_localization import compose

ROOT=Path(__file__).resolve().parents[2]
CASES=(('one_east',1.,[0.,-.6,0.],[.4,-.6]),
       ('one_north',1.,[.1,-.6,math.pi/2],[.1,-.2]),
       ('one_west',1.,[.2,-.4,math.pi],[-.2,-.4]),
       ('two_diagonal',1.2,[-.2,-.6,.25],[-.2+.4*math.cos(.25),-.6+.4*math.sin(.25)]),
       ('two_south',1.2,[.1,-.7,-math.pi/2],[.1,-1.1]),
       ('two_northwest',1.2,[.3,-.6,3*math.pi/4],[.3-.4/math.sqrt(2),-.6+.4/math.sqrt(2)]))


def clearance(p,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1]
    t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.dist(p,[a[0]+t*dx,a[1]+t*dy])


class ExpandedColdGoalTests(unittest.TestCase):
    def test_two_shapes_three_goals_each_changed_start_and_heading(self):
        helper=fixtures.ColdStartTests();helper.setUp();self.addCleanup(helper.doCleanups)
        rows=[];validated=[];name=os.environ.get('TWINPULSE_EXPANDED_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        for identity,scale,start,target in CASES:
            with self.subTest(case=identity):
                job,adapter,report=helper.execute(identity,scale,start,target,photo_policy='correct_walls')
                # World truth is used only by the evaluator, never by the App,
                # matcher, planner or fit callback. Preserve every failure too.
                poses=[compose(start,row['odom']) for row in adapter.raw]
                minimum=min(clearance(p[:2],a,b) for p in poses for a,b in adapter.outline['segments'])
                outcome={'case':identity,'state':job['state'],'reason':job.get('error'),
                    'target':target,'start':start,'final_world':adapter.world,'error_m':math.dist(adapter.world[:2],target),
                    'minimum_truth_wall_clearance_m':minimum,'synthetic_footprint_radius_m':.18,
                    'final_velocity':list(adapter.velocity),'physical_validation':'NOT_RUN',
                    'source_basis':'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST','mission_budget_s':45.}
                rows.append(outcome)
                if name:
                    folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                    (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False,indent=2))
                    (folder/'mission-report.json').write_text(json.dumps(report,allow_nan=False))
                    (folder/'synthetic-raw.json').write_text(json.dumps({'observations':adapter.raw,'commands':adapter.sent},allow_nan=False))
                self.assertEqual(job['state'],'MISSION_ARRIVED',outcome)
                self.assertLess(outcome['error_m'],.10,outcome)
                self.assertGreaterEqual(minimum,.18,outcome)
                self.assertEqual(adapter.velocity,(0.,0.));self.assertEqual(adapter.consumed,1)
                self.assertIsNone(report['prior_map_revision']);self.assertFalse(report['physical_demo_ready'])
                self.assertEqual(job['goal']['duration_s'],45.)
                self.assertEqual(job['goal']['xy'],target);self.assertEqual(job['original_goal']['xy'],target)
                self.assertNotEqual(job['goal']['room_revision'],job['original_goal']['room_revision'])
                self.assertEqual(job['photo_correction']['goal_revalidation'],'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED')
                self.assertEqual(report['photo_alignment']['goal_binding']['goal'],job['goal'])
                validated.append(identity)
        # Only a wholly passed matrix may receive a PASS receipt.
        if name and len(validated)==len(CASES) and all(row['state']=='MISSION_ARRIVED' and row['error_m']<.10 and row['minimum_truth_wall_clearance_m']>=.18 for row in rows):
            folder=ROOT/'artifacts'/name
            selected=('packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
                'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
                'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
                'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                'packages/twinpulse_app/src/twinpulse_app/mission_photo_correction.py',
                'tests/integration/test_cold_start_mission.py','tests/integration/test_expanded_cold_goals.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS','cases':rows,
                'physical_validation':'NOT_RUN','browser_isaac':'NOT_RUN_FOR_THIS_MATRIX','robot_connections':0,
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in selected},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2))


if __name__=='__main__':unittest.main()
