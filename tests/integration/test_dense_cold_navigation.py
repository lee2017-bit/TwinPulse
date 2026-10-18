# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Original dense cold goal regression; output-reactive synthetic data only."""
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from tests.integration import test_cold_start_mission as fixture
from packages.twinpulse_core.tests.test_room_localization import scan_points


class DenseColdNavigationTests(unittest.TestCase):
    def test_original_dense_goal_arrives_without_extended_budget_or_arrival_radius(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);outline,_=fixture.recipe(root,'dense_cold',1.)
            automatic=AutomaticDemoService(root,'dense_cold',geometry_loader=lambda:fixture.GEOMETRY)
            service=AutomaticMissionService(automatic);adapters=[];matches=[]
            def factory(prior,room,effective,goal):
                adapter=fixture.ColdAdapter(prior,room,effective,goal,outline=outline,start=[0.,-.6,0.])
                adapter.observation_points=lambda:scan_points(adapter.outline,adapter.world,beam_count=720)
                def observed(mission,result):
                    if (mission.stage=='NAVIGATE' and mission.last_evidence
                            and mission.last_evidence['state']=='TRACKING_CANDIDATE'):
                        matches.append(mission.last_evidence['match'])
                adapter.observed_decision=observed
                adapters.append(adapter);return adapter
            factory.supports_local_correction=True;service.adapter_factory=factory
            goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[.4,-.6],'duration_s':45.,
                'room_revision':service.readiness(None)['room_revision']}
            try:
                service.start('owner',None,goal,'correct_walls')
                service.worker.join(180)  # Wall-time harness, not source mission time.
                self.assertFalse(service.worker.is_alive())
                job=service.snapshot('owner')['job'];adapter=adapters[0]
                self.assertEqual(job['state'],'MISSION_ARRIVED',job.get('error'))
                self.assertEqual(job['original_goal'],goal)
                for key in ('mode','xy','duration_s'):self.assertEqual(job['goal'][key],goal[key])
                self.assertLess(adapter.t,65.)
                self.assertLessEqual(math.dist(job['visual']['pose_room'][:2],goal['xy']),.015)
                self.assertLess(math.dist(adapter.world[:2],goal['xy']),.10)  # Existing synthetic evaluator, not metric calibration.
                self.assertEqual(adapter.velocity,(0.,0.));self.assertGreater(adapter.halted,0)
                self.assertTrue(adapter.raw);self.assertTrue(all(len(r['ranges'])==720 for r in adapter.raw))
                self.assertLessEqual(len(job['visual']['scan_room']),160)
                self.assertTrue(matches)
                self.assertTrue(all(m['field_sampling']=='60MM_BILINEAR_CHAMFER_NOT_METRIC_CALIBRATION' for m in matches))
                self.assertTrue(all(m['current_refinement_step_m']==.003125 for m in matches))
                self.assertTrue(all(abs(v)<=.03 and abs(w)<=.2 for _,v,w in adapter.sent))
                report=json.loads((root/'artifacts/automatic-mission/dense_cold'/f"{job['job_id']}.json").read_text(encoding='utf-8'))
                self.assertFalse(report['physical_demo_ready']);self.assertEqual(report['physical_validation'],'NOT_RUN')
            finally:
                service.close();automatic.close()


if __name__=='__main__':unittest.main()
