# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Changed raycast world -> actual App/matcher/planner/control; no pose injection.

Truth is confined to raycasting and evaluation. Fixed scenarios are not field
qualification, physics simulation, or full O2--O4 acceptance.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import time
import unittest
from tests.integration import test_automatic_mission_service as fixture
from tests.integration.test_expanded_cold_goals import clearance
from packages.twinpulse_core.tests.test_room_localization import scan_points

ROOT=Path(__file__).resolve().parents[2]
BLOCK=[[-.025,-.625],[.025,-.625],[.025,-.575],[-.025,-.575]]
SIDE_BLOCK=[[.025,-.425],[.075,-.425],[.075,-.375],[.025,-.375]]
SCENARIOS=('detour','detour_budget','actuation_deadline','occluded_goal','blocked_goal','temporary_loss','reposition')


class ChangingAdapter(fixture.RaycastAdapter):
    def __init__(self,*args,scenario,**kwargs):
        super().__init__(*args,**kwargs);self.scenario=scenario;self.decisions=[];self.environments=[];self.matches=[]
    def spin(self,dt):
        if self.scenario=='actuation_deadline':
            # Deliberately nonresponding actuator fault in PRIVATE dynamics.
            # Odom/scan still come from the actual raycast pipeline; no supplied
            # pose, success or reason is substituted in the product matcher.
            self.t+=dt
        else:super().spin(dt)
    def current(self,pose,now):
        started=time.perf_counter()
        result=super().current(pose,now)
        self.latest_evidence=result
        self.matches.append({'t':now,'state':result['state'],'pose':result['pose_map'],
                             'wall_time_s':time.perf_counter()-started,
                             'match':copy.deepcopy(result['match'])})
        return result
    def observation_points(self):
        outline=copy.deepcopy(self.outline);segments=[]
        if self.scenario in ('detour','detour_budget','occluded_goal','blocked_goal') and self.t>=20.5:
            vertices=SIDE_BLOCK if self.scenario.startswith('detour') else BLOCK if self.scenario=='occluded_goal' else [[.15,-.85],[.65,-.85],[.65,-.35],[.15,-.35]]
            segments=[[vertices[i],vertices[(i+1)%4]] for i in range(4)]
            outline['segments']+=segments
        if self.scenario in ('temporary_loss','reposition') and 21.<=self.t<21.3:
            outline['segments']=[[[1.4*x,1.4*y] for x,y in pair] for pair in outline['segments']]
        if self.scenario=='reposition' and self.t>=21.3 and not getattr(self,'repositioned',False):
            # Physical relocation in private truth, not a supplied matcher pose.
            self.world[0]+=.6;self.repositioned=True
        self.environments.append({'t':self.t,'world':list(self.world),'obstacle_segments':segments})
        return scan_points(outline,self.world,beam_count=720 if self.scenario.startswith('detour') else 120)
    def observed_decision(self,mission,result):
        self.decisions.append({'t':self.t,'decision':copy.deepcopy(result),
            'phase':mission.phase,'plan_count':mission.plan_count,'visual':mission.visual('a'*32)})


class ChangingEnvironmentTests(unittest.TestCase):
    def test_fixed_environment_matrix_actual_app(self):
        helper=fixture.AutomaticMissionTests();helper.setUp();self.addCleanup(helper.doCleanups)
        name=os.environ.get('TWINPULSE_CHANGING_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        selected=os.environ.get('TWINPULSE_CHANGING_CASE')
        if selected:self.assertIn(selected,SCENARIOS)
        for scenario in ((selected,) if selected else SCENARIOS):
            with self.subTest(scenario=scenario):
                start=[0.,-.6,0.] if scenario=='actuation_deadline' else [-.4,-.6,.7 if scenario.startswith('detour') else 0.]
                # The ORIGINAL detour_budget goal is unchanged. Continuous
                # matching now reaches it under45 s; preserve that improvement
                # instead of forcing a fake expiry. The first additional far
                # goals lost observed goal-footprint coverage and correctly
                # stopped BEFORE expiry (both failed artifacts kept). Deadline
                # acceptance instead uses the existing covered short goal with
                # an explicitly nonresponding actuator, not relaxed coverage.
                target=[.05,.025] if scenario=='detour' else [.1,.05] if scenario=='detour_budget' else [.15,-.6] if scenario=='actuation_deadline' else [.4,-.6] if scenario=='blocked_goal' else [.3,-.6]
                adapters=[]
                def factory(prior,room,effective,goal):
                    a=ChangingAdapter(prior,room,effective,goal,outline=helper.outline,start=start,scenario=scenario)
                    adapters.append(a);return a
                helper.service.adapter_factory=factory
                started=time.perf_counter()
                helper.service.start('owner',helper.map_id,helper.goal(target))
                helper.service.worker.join(70)
                at70={'alive':helper.service.worker.is_alive(),'source_clock_s':adapters[0].t}
                # Diagnostic wall wait only. The unchanged worker source clock
                # still expires at20+45 s; do not abort a slow CPU fixture at70.
                helper.service.worker.join(110)
                if helper.service.worker.is_alive():
                    if name:
                        folder=ROOT/'artifacts'/name/(scenario+'-incomplete');folder.mkdir(parents=True,exist_ok=False)
                        (folder/'diagnosis.json').write_text(json.dumps({'status':'HARNESS_WALL_TIMEOUT',
                            'complete':False,'at70':at70,'snapshot':helper.service.snapshot('owner'),
                            'source_clock_s':adapters[0].t,'raw':adapters[0].raw,'commands':adapters[0].sent},
                            allow_nan=False),encoding='utf-8')
                    job=helper.service.snapshot('owner')['job']
                    helper.service.stop('owner',job['job_id'],force=True);helper.service.worker.join(10)
                    self.fail('HARNESS_WALL_TIMEOUT: unchanged45s source budget; raw saved and owned Force STOP requested')
                job=helper.service.snapshot('owner')['job'];adapter=adapters[0]
                report=json.loads((helper.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json").read_text())
                distances=[clearance(row['world'][:2],a,b) for row in adapter.environments
                    for a,b in helper.outline['segments']+row['obstacle_segments']]
                outcome={'scenario':scenario,'state':job['state'],'reason':job.get('error'),
                    'target':target,'start':start,'final_world':adapter.world,'error_m':math.dist(adapter.world[:2],target),
                    'minimum_truth_clearance_m':min(distances),'maximum_plan_count':max(d['plan_count'] for d in adapter.decisions),
                    'decision_reasons':sorted({d['decision']['reason'] for d in adapter.decisions}),
                    'match_states':sorted({m['state'] for m in adapter.matches}),
                    'final_velocity':list(adapter.velocity),'physical_validation':'NOT_RUN',
                    'source_basis':'SYNTHETIC_RAYCAST_NONRESPONDING_ACTUATOR_FAULT' if scenario=='actuation_deadline' else 'OUTPUT_REACTIVE_SYNTHETIC_RAYCAST','mission_budget_s':45.,
                    'harness_wall_time_s':time.perf_counter()-started,'at70':at70,
                    'match_wall_time_max_s':max(m['wall_time_s'] for m in adapter.matches),
                    'source_clock_at_end_s':adapter.t}
                if scenario.startswith('detour') and job['state']=='FAILED':
                    from twinpulse_core.bounded_grid_plan import plan_bounded_grid
                    from twinpulse_core.room_localization import compose,inverse
                    evidence=adapter.latest_evidence
                    for label,point in (('start',evidence['pose_map'][:2]),
                                        ('goal',compose(inverse(evidence['room_from_map']),[*target,0.])[:2])):
                        try:plan_bounded_grid(point,point,evidence['bounds'],resolution=.1,clearance=.266,observed_cells=evidence['cells'])
                        except ValueError as exc:outcome[label+'_endpoint']=str(exc)
                        else:outcome[label+'_endpoint']='OBSERVED_FREE'
                outcomes.append(outcome)
                if name:
                    folder=ROOT/'artifacts'/name/scenario;folder.mkdir(parents=True,exist_ok=False)
                    (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False,indent=2))
                    (folder/'mission-report.json').write_text(json.dumps(report,allow_nan=False))
                    (folder/'synthetic-raw.json').write_text(json.dumps({'observations':adapter.raw,'commands':adapter.sent,
                        'environments':adapter.environments,'matches':adapter.matches,'decisions':adapter.decisions,
                        'last_evidence':adapter.latest_evidence},allow_nan=False))
                self.assertEqual(adapter.velocity,(0.,0.));self.assertEqual(adapter.consumed,1)
                self.assertFalse(report['physical_demo_ready']);self.assertEqual(job['goal']['duration_s'],45.)
                self.assertEqual(job['goal']['xy'],target)
                self.assertTrue(all(abs(v)<=.03 and abs(w)<=.2 for _,v,w in adapter.sent))
                self.assertGreaterEqual(outcome['minimum_truth_clearance_m'],.18,outcome)
                if scenario in ('detour','detour_budget','temporary_loss'):
                    self.assertEqual(job['state'],'MISSION_ARRIVED',outcome);self.assertLess(outcome['error_m'],.10,outcome)
                else:
                    self.assertEqual(job['state'],'FAILED',outcome)
                    expected='MISSION_EXPIRED' if scenario=='actuation_deadline' else 'POSE_JUMP_REQUIRES_NEW_SESSION' if scenario=='reposition' else 'OBSERVED_PATH_START_OR_GOAL_BLOCKED'
                    self.assertEqual(job['error'],expected,outcome)
                    self.assertIsNone(report['visual']['pose_room']);self.assertFalse(report['visual']['scan_room'])
                    if scenario=='actuation_deadline':
                        self.assertEqual(adapter.world,start)
                        self.assertTrue(any(v or w for _,v,w in adapter.sent))
                        self.assertGreaterEqual(adapter.t,65.)
                        self.assertTrue(all(t<65. or not(v or w) for t,v,w in adapter.sent))
                if scenario.startswith('detour'):
                    self.assertIn('REVISION_CHANGED_STOP_BEFORE_REPLAN',outcome['decision_reasons'])
                    self.assertGreaterEqual(outcome['maximum_plan_count'],2)
                    # A newly planned route must actually differ from the old
                    # straight line, not merely rebuild an identical route.
                    routes=[d['visual']['route_room'] for d in adapter.decisions if d['plan_count']>=2]
                    self.assertTrue(any(len(r)>1 for r in routes),outcome)
                if scenario in ('temporary_loss','reposition'):
                    loss=[d for d in adapter.decisions if d['decision']['reason']=='CURRENT_LOCALIZATION_REQUIRED']
                    self.assertTrue(loss,outcome)
                    for row in loss:
                        self.assertEqual(row['decision']['linear_m_s'],0.);self.assertEqual(row['decision']['angular_rad_s'],0.)
                        self.assertIsNone(row['visual']['pose_room']);self.assertFalse(row['visual']['scan_room']);self.assertFalse(row['visual']['route_room'])
                passed.append(scenario)
        if name and len(passed)==len(SCENARIOS):
            folder=ROOT/'artifacts'/name
            paths=('packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
                'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
                'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
                'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                'packages/twinpulse_core/tests/test_room_localization.py',
                'tests/integration/test_automatic_mission_service.py','tests/integration/test_changing_mission_environment.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS','cases':outcomes,
                'physical_validation':'NOT_RUN','browser_isaac':'NOT_RUN_FOR_THIS_MATRIX','robot_connections':0,
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2))


if __name__=='__main__':unittest.main()
