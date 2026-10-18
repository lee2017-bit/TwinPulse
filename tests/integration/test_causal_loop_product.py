# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual App causal mapping/store on a declared synthetic recorded loop.

The fixed differential-drive sequence generates the private recording, not an
autonomous controller result. No future frame or evaluator truth is provided
to AutomaticMapping. Frontend revisit is explicitly NOT pose-graph SLAM.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_core.observation_stream import ObservationWindow
from twinpulse_core.automatic_mapping import AutomaticMapping
from twinpulse_core.room_localization import compose,inverse,angle
from packages.twinpulse_core.tests.test_room_localization import scan_points,pose
from tests.integration import test_automatic_photo_service as fixture

ROOT=Path(__file__).resolve().parents[2]
DT=.1
# Fixed before evaluating: four 0.3 m sides, four90-degree turns, no teleport.
COMMANDS=[command for _ in range(4) for command in
          [( .025,0.)]*120+[(0.,math.pi/(2*79*DT))]*79]
DRIFT=(.002,.0015,.0005)


class LoopRecording:
    def __init__(self,identity,outline):
        self.context={**fixture.CONTEXT,'project_id':identity,'source_revision':'c'*64,
                      'session_id':'synthetic-loop','boot_id':'synthetic-loop-boot'}
        self.window=ObservationWindow(self.context);self.outline=outline
        self.truth=[];self.raw=[];self.initial=[0.,-.6,.35]
    def __iter__(self):
        world=list(self.initial);anchor=inverse(world)
        for index,command in enumerate([(0.,0.)]+COMMANDS):
            if index:world=compose(world,[command[0]*DT,0.,command[1]*DT])
            elapsed=index*DT;odom=compose(anchor,world)
            for axis,rate in enumerate(DRIFT):odom[axis]+=rate*elapsed
            stamp=1_000_000_000+index*100_000_000
            self.truth.append({'stamp_ns':stamp,'pose_local':compose(anchor,world),'odom_local':odom,
                               'recording_command':command})
            points=scan_points(self.outline,world)
            scan={'stamp_ns':stamp,'frame_id':'base_scan','ranges_m':[math.hypot(*p) for p in points],
                  'angle_min':0.,'angle_max':119*math.tau/120,'angle_increment':math.tau/120,
                  'time_increment':0.,'scan_time':DT,'range_min':.05,'range_max':100.}
            for topic,data in (('odom',pose(stamp,*odom)),('scan',scan)):
                event=self.window.receive(topic,data,2*index+(topic=='scan'),stamp)
                self.raw.append(copy.deepcopy(event));yield event


class CausalLoopProductTests(unittest.TestCase):
    def test_two_recorded_loops_drift_revisit_save_reopen_no_pose_graph_claim(self):
        name=os.environ.get('TWINPULSE_LOOP_EVIDENCE')
        if name:self.assertRegex(name,'^[a-z0-9-]{1,100}$')
        outcomes=[];passed=[]
        for number,scale in ((1,1.),(2,1.2)):
            identity=f'loop_room{number}'
            with self.subTest(case=identity),TemporaryDirectory() as directory:
                root=Path(directory);outline,_=fixture.recipe(root,identity,scale);sources=[];current_evaluation=[]
                def source_factory(*_):
                    source=LoopRecording(identity,outline);sources.append(source);return source
                class ObservedMapping(AutomaticMapping):
                    def consume(self,event):
                        # Observation-only hook AFTER the unchanged consumer.
                        # Includes predicted poses on skipped derived updates,
                        # not just the half-second matched trajectory samples.
                        super().consume(event)
                        if event['topic']!='scan' or self.state!='TRACKING_CANDIDATE' or self.pose is None:return
                        truth=sources[0].truth[-1]
                        if truth['stamp_ns']!=event['data']['stamp_ns']:raise AssertionError('evaluator timestamp mismatch')
                        actual=list(self.snapshot()['pose_candidate']);reference=truth['pose_local']
                        current_evaluation.append({'stamp_ns':truth['stamp_ns'],'observed':actual,
                            'truth':reference,'xy_error_m':math.dist(actual[:2],reference[:2]),
                            'yaw_error_rad':abs(angle(actual[2]-reference[2]))})
                service=AutomaticDemoService(root,identity,source_factory=source_factory,
                                             geometry_loader=lambda:fixture.GEOMETRY)
                try:
                    with patch('twinpulse_app.automatic_demo_service.AutomaticMapping',ObservedMapping):
                        service.start('owner','a'*32,photo_policy='disabled');service.worker.join(90)
                    finished=not service.worker.is_alive()
                    if not finished:
                        service.control('owner',service.job['job_id'],'cancel');service.worker.join(10)
                    job=service.snapshot('owner')['job'];source=sources[0];result=job.get('result') or {}
                    truth={r['stamp_ns']:r for r in source.truth};evaluation=[]
                    for row in result.get('trajectory',[]):
                        if row['state']!='TRACKING_CANDIDATE':continue
                        reference=truth[row['stamp_ns']]['pose_local']
                        evaluation.append({'stamp_ns':row['stamp_ns'],'observed':row['corrected_pose'],
                            'truth':reference,'xy_error_m':math.dist(row['corrected_pose'][:2],reference[:2]),
                            'yaw_error_rad':abs(angle(row['corrected_pose'][2]-reference[2]))})
                    derived_evaluation=evaluation;evaluation=current_evaluation
                    accurate=sum(r['xy_error_m']<=.10 and r['yaw_error_rad']<=math.radians(5) for r in evaluation)
                    final=truth[max(truth)]
                    end_error=math.dist(result['pose_candidate'][:2],final['pose_local'][:2]) if result.get('pose_candidate') else None
                    raw_error=math.dist(final['odom_local'][:2],final['pose_local'][:2])
                    outcome={'case':identity,'state':job['state'],'reason':job.get('error'),'complete':finished,
                        'recorded_frames':len(source.truth),'tracking_samples':len(evaluation),
                        'within_fraction':accurate/len(evaluation) if evaluation else 0.,
                        'maximum_xy_error_m':max((r['xy_error_m'] for r in evaluation),default=None),
                        'maximum_yaw_error_rad':max((r['yaw_error_rad'] for r in evaluation),default=None),
                        'corrected_end_error_m':end_error,'raw_end_error_m':raw_error,
                        'private_world_loop_gap_m':math.hypot(*final['pose_local'][:2]),
                        'loop_status':result.get('loop_status'),'derived_tracking_samples':len(derived_evaluation),
                        'reference_eligible':result.get('reference_eligible'),
                        'physical_validation':'NOT_RUN','source_basis':'PRESCRIPTED_SYNTHETIC_RECORDED_LOOP_NOT_MISSION'}
                    outcomes.append(outcome)
                    if name:
                        folder=ROOT/'artifacts'/name/identity;folder.mkdir(parents=True,exist_ok=False)
                        for filename,value in (('outcome.json',outcome),('original-observations.json',source.raw),
                            ('private-evaluation-source.json',source.truth),('tracking-evaluation.json',evaluation),
                            ('derived-tracking-evaluation.json',derived_evaluation),('job.json',job)):
                            (folder/filename).write_text(json.dumps(value,allow_nan=False),encoding='utf-8')
                    self.assertTrue(finished,outcome);self.assertEqual(job['state'],'COMPLETED',outcome)
                    self.assertEqual(result['counts']['scans_seen'],len(COMMANDS)+1)
                    self.assertGreaterEqual(len(evaluation),20,outcome)
                    self.assertGreaterEqual(outcome['within_fraction'],.95,outcome)
                    self.assertLess(outcome['private_world_loop_gap_m'],1e-8)
                    self.assertLess(end_error,raw_error,outcome)
                    self.assertEqual(result['loop_status'],'FRONTEND_REVISIT_SUPPORTED_NOT_POSE_GRAPH',outcome)
                    self.assertTrue(result['reference_eligible'],outcome)
                    saved=service.store.load(job['map_id']);service.close()
                    reopened_service=AutomaticDemoService(root,identity)
                    try:
                        reopened=reopened_service.reopen('reader',job['map_id'])
                        self.assertEqual(reopened['map'],saved);self.assertIsNone(reopened['pose_candidate'])
                        self.assertFalse(reopened['motion_authorized']);self.assertFalse(reopened['physical_demo_ready'])
                        if name:(folder/'reopened.json').write_text(json.dumps(reopened,allow_nan=False),encoding='utf-8')
                    finally:reopened_service.close()
                    passed.append(identity)
                finally:service.close()
        if name:
            folder=ROOT/'artifacts'/name
            sources=('tests/integration/test_causal_loop_product.py','tests/integration/test_automatic_photo_service.py',
                'packages/twinpulse_core/tests/test_room_localization.py',
                'packages/twinpulse_core/tests/test_automatic_mapping.py',
                'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
                'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/observation_stream.py',
                'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_demo_service.py',
                'packages/twinpulse_app/src/twinpulse_app/project_store.py')
            (folder/'verification.json').write_text(json.dumps({'status':'PASS' if len(passed)==2 else 'FAILED',
                'cases':outcomes,'robot_connections':0,'physical_validation':'NOT_RUN','browser_isaac':'NOT_RUN_FOR_THIS_MATRIX',
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                'artifact_sha256':{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in folder.rglob('*.json')}},indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
