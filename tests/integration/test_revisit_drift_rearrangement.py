# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual saved App map reopen, changed raycast objects and measured odom drift.

Evaluator truth is private to the simulator and accuracy checker. Neither a
current pose, matcher success nor a prescribed arrival enters product code.
"""
import copy
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
from tests.integration import test_automatic_mission_service as fixture

ROOT=Path(__file__).resolve().parents[2]
SOURCES=('tests/integration/test_revisit_drift_rearrangement.py',
    'tests/integration/test_automatic_mission_service.py',
    'tests/integration/test_automatic_photo_service.py',
    'packages/twinpulse_core/tests/test_room_localization.py',
    'packages/twinpulse_core/tests/test_automatic_mapping.py',
    'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
    'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
    'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
    'packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
    'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py')


def rectangle(x0,y0,x1,y1):
    vertices=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
    return [[vertices[i],vertices[(i+1)%4]] for i in range(4)]


class RevisitAdapter(fixture.RaycastAdapter):
    def __init__(self,*args,rates,**kwargs):
        super().__init__(*args,**kwargs);self.rates=rates;self.tracking=[];self.decisions=[]
    def spin(self,dt):
        super().spin(dt)
        # Sensor fault model only: continuously drifting odom measurement.
        # The private world and LiDAR raycast do NOT move with this error.
        for i,rate in enumerate(self.rates):self.anchor[i]+=rate*dt
    def observed_decision(self,mission,result):
        visual=mission.visual('a'*32);observed=visual['pose_room']
        self.decisions.append({'t':self.t,'decision':copy.deepcopy(result),'visual':visual})
        if observed is not None and mission.current_pose_valid:
            self.tracking.append({'t':self.t,'observed':observed,'truth':list(self.world),
                'xy_error_m':math.dist(observed[:2],self.world[:2]),
                'yaw_error_rad':abs(angle(observed[2]-self.world[2]))})


class RevisitDriftRearrangementTests(unittest.TestCase):
    def test_reopen_current_drift_and_changed_objects_not_old_pose_or_free_space(self):
        name=os.environ.get('TWINPULSE_REVISIT_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        with TemporaryDirectory() as directory:
            root=Path(directory);outline,_=fixture.recipe(root,'revisit_room',1.)
            sources=[]
            class LoggedSource(fixture.RaycastSource):
                def __init__(self):super().__init__('revisit_room',outline);self.raw=[]
                def __iter__(self):
                    for event in super().__iter__():self.raw.append(copy.deepcopy(event));yield event
            def source_factory(*_):
                value=LoggedSource();sources.append(value);return value
            automatic=AutomaticDemoService(root,'revisit_room',source_factory=source_factory,
                                           geometry_loader=lambda:fixture.GEOMETRY)
            try:
                automatic.start('owner','a'*32,photo_policy='align_only');automatic.worker.join(30)
                self.assertFalse(automatic.worker.is_alive())
                prior_job=automatic.snapshot('owner')['job'];self.assertEqual(prior_job['state'],'COMPLETED',prior_job)
                self.assertEqual(prior_job['result']['photo_alignment']['status'],'ALIGNMENT_CANDIDATE')
                map_id=prior_job['map_id'];prior=automatic.reopen('owner',map_id)
                # The verified store path belongs to the existing store, not a
                # guessed external fixture or a hand-authored prior map.
                immutable=automatic.store.load(map_id)
                prior_revision=immutable['revision'];recipe_before=(root/'projects/revisit_room/room_recipe.json').read_bytes()
                if name:
                    folder=ROOT/'artifacts'/name;folder.mkdir(parents=True,exist_ok=False)
                    (folder/'prior.json').write_text(json.dumps(prior,allow_nan=False),encoding='utf-8')
                    (folder/'prior-raw.json').write_text(json.dumps(sources[0].raw,allow_nan=False),encoding='utf-8')
            finally:automatic.close()
            cases=(
                ('drift',[0.,-.6,0.],[.6,-.6],(.008,.003,.002),[],True),
                ('heading_drift',[-.3,-.4,.4],[-.3+.5*math.cos(.4),-.4+.5*math.sin(.4)],(.006,.003,.0015),[],True),
                ('rearranged',[.1,-.6,0.],[.4,-.6],(0.,0.,0.),rectangle(-.5,.1,-.15,.4),True),
                ('rearranged_blocked',[0.,-.6,0.],[.3,-.6],(0.,0.,0.),rectangle(.2,-.68,.4,-.52),False))
            for identity,start,target,rates,objects,should_arrive in cases:
                with self.subTest(case=identity):
                    # Actually close/reopen the App services between cases.
                    automatic=AutomaticDemoService(root,'revisit_room')
                    service=AutomaticMissionService(automatic);adapters=[]
                    current_outline=copy.deepcopy(outline);current_outline['segments']+=objects
                    def factory(prior,room,effective,goal):
                        adapter=RevisitAdapter(prior,room,effective,goal,outline=current_outline,start=start,rates=rates)
                        adapters.append(adapter);return adapter
                    service.adapter_factory=factory
                    goal={'mode':'NAVIGATE_TWIN_GOAL','xy':target,'duration_s':45.,
                          'room_revision':service.readiness(map_id)['room_revision']}
                    try:
                        self.assertIsNone(automatic.reopen('owner',map_id)['pose_candidate'])
                        service.start('owner',map_id,goal);service.worker.join(180)
                        complete=not service.worker.is_alive()
                        if not complete:
                            service.stop('owner',service.job['job_id'],force=True);service.worker.join(10)
                        job=service.snapshot('owner')['job'];adapter=adapters[0]
                        path=root/'artifacts/automatic-mission/revisit_room'/f"{job['job_id']}.json"
                        report=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
                        accurate=sum(row['xy_error_m']<=.10 and row['yaw_error_rad']<=math.radians(5) for row in adapter.tracking)
                        outcome={'case':identity,'state':job['state'],'reason':job.get('error'),'complete':complete,
                            'start':start,'goal':goal,'odom_drift_per_s':rates,'changed_segments':objects,
                            'first_odom':adapter.raw[0]['odom'],'tracking_samples':len(adapter.tracking),
                            'within_fraction':accurate/len(adapter.tracking) if adapter.tracking else None,
                            'maximum_xy_error_m':max((r['xy_error_m'] for r in adapter.tracking),default=None),
                            'maximum_yaw_error_rad':max((r['yaw_error_rad'] for r in adapter.tracking),default=None),
                            'minimum_true_scan_range_m':min(min(r['ranges']) for r in adapter.raw),
                            'source_end_s':adapter.t,'final_world':adapter.world,'final_velocity':adapter.velocity,
                            'truth_goal_error_m':math.dist(adapter.world[:2],target),
                            'physical_validation':'NOT_RUN','source_basis':'SYNTHETIC_RAYCAST_ODOMETRY_DRIFT'}
                        outcomes.append(outcome)
                        if name:
                            folder=ROOT/'artifacts'/name/identity;folder.mkdir()
                            (folder/'outcome.json').write_text(json.dumps(outcome,allow_nan=False,indent=2),encoding='utf-8')
                            (folder/'synthetic-raw.json').write_text(json.dumps({'complete':not service.worker.is_alive(),
                                'observations':adapter.raw,'commands':adapter.sent,'decisions':adapter.decisions},allow_nan=False),encoding='utf-8')
                            (folder/'tracking-evaluation.json').write_text(json.dumps(adapter.tracking,allow_nan=False),encoding='utf-8')
                            if path.exists():(folder/'mission-report.json').write_bytes(path.read_bytes())
                        self.assertTrue(complete,outcome);self.assertEqual(adapter.velocity,(0.,0.))
                        self.assertTrue(all(abs(v)<1e-10 for v in adapter.raw[0]['odom']))
                        self.assertFalse(job['physical_demo_ready']);self.assertEqual(job['goal'],goal)
                        self.assertEqual(automatic.store.load(map_id),immutable)
                        self.assertEqual((root/'projects/revisit_room/room_recipe.json').read_bytes(),recipe_before)
                        self.assertGreaterEqual(outcome['minimum_true_scan_range_m'],.18,outcome)
                        self.assertTrue(all(abs(v)<=.03 and abs(w)<=.2 for _,v,w in adapter.sent))
                        if should_arrive:
                            self.assertEqual(job['state'],'MISSION_ARRIVED',outcome)
                            self.assertLess(outcome['truth_goal_error_m'],.10,outcome)
                            self.assertGreaterEqual(len(adapter.tracking),3,outcome)
                            self.assertGreaterEqual(outcome['within_fraction'],.95,outcome)
                        else:
                            self.assertEqual(job['state'],'FAILED',outcome)
                            self.assertEqual(job['error'],'OBSERVED_PATH_START_OR_GOAL_BLOCKED',outcome)
                            visual=report.get('visual') or {}
                            self.assertIsNone(visual.get('pose_room'));self.assertFalse(visual.get('scan_room'))
                            self.assertFalse(any(v or w for _,v,w in adapter.sent),outcome)
                        passed.append(identity)
                    finally:service.close();automatic.close()
        if name:
            folder=ROOT/'artifacts'/name
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==4 else 'FAILED',
                'cases':outcomes,'prior_revision':prior_revision,'robot_connections':0,'physical_validation':'NOT_RUN',
                'browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
