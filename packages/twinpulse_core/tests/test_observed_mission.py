# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.observed_mission import ObservedMission
from twinpulse_core.local_navigation import LocalPose,LocalScan
from twinpulse_core.revisions import canonical_sha256


def cells(blocked=()):
    return [[x/10+.05,y/10+.05,'occupied' if (x,y) in blocked else 'free',1,0,1,'a'*64]
            for x in range(-12,13) for y in range(-12,13)]


class ObservedMissionTests(unittest.TestCase):
    def test_position_loss_invalidates_current_visual_and_fresh_recovery_replans(self):
        mission=self.setup_mission(scan_room=[[1.,0.]],trajectory_room=[[0.,0.,0.]])
        self.assertGreater(self.step(mission,0.)['linear_m_s'],0)
        self.evidence.update(state='LOST',pose_map=None,sample_s=.05)
        decision=mission.step(LocalPose((0.,0.,0.),.05,'synthetic_room','synthetic_model','synthetic_raycast'),
            LocalScan(tuple([2.]*120),.05,'base_link','synthetic_model','synthetic_raycast'),.05,command_created_s=.05)
        self.assertEqual(decision['reason'],'CURRENT_LOCALIZATION_REQUIRED');self.assertEqual(decision['linear_m_s'],0)
        visual=mission.visual('e'*32)
        self.assertIsNone(visual['pose_room']);self.assertEqual(visual['scan_room'],[]);self.assertEqual(visual['route_room'],[])
        self.assertEqual(visual['trajectory_room'],[[0.,0.,0.]])
        self.assertEqual(mission.previous_pose,[0.,0.,0.])  # Loss cannot erase the jump guard.
        self.evidence['state']='TRACKING_CANDIDATE'
        self.assertGreater(self.step(mission,.1)['linear_m_s'],0)
        self.assertEqual(mission.plan_count,2);self.assertEqual(mission.visual('e'*32)['pose_room'],[0.,0.,0.])

    def test_invalid_source_tick_cannot_republish_last_valid_scan(self):
        for fault in ('stale','alignment','epoch'):
            with self.subTest(fault=fault):
                mission=self.setup_mission(scan_room=[[1.,0.]])
                self.step(mission,0.)
                if fault=='alignment':self.evidence['alignment_status']='MODEL_MISMATCH'
                if fault=='epoch':self.evidence['epoch']=2
                result=self.step(mission,.5 if fault=='stale' else .05)
                if fault=='stale':
                    # A stale command is rejected even with a fresh sensor row.
                    result=mission.step(LocalPose((0.,0.,0.),.55,'synthetic_room','synthetic_model','synthetic_raycast'),
                        LocalScan(tuple([2.]*120),.55,'base_link','synthetic_model','synthetic_raycast'),.55,command_created_s=0.)
                self.assertFalse(result['allowed']);self.assertIsNone(mission.visual('e'*32)['pose_room'])
                self.assertEqual(mission.visual('e'*32)['scan_room'],[])

    def setup_mission(self,**changes):
        self.evidence={'project_id':'room','source_revision':'a'*64,'epoch':1,'room_revision':'b'*64,
            'map_revision':'c'*64,'alignment_revision':'d'*64,'room_from_map':[0.,0.,0.],
            'pose_map':[0.,0.,0.],'sample_s':0.,'state':'TRACKING_CANDIDATE','cells':cells(),
            'bounds':[-1.2,1.2,-1.2,1.2],'alignment_status':'ALIGNMENT_CANDIDATE'}
        self.evidence.update(changes)
        return ObservedMission({'mode':'NAVIGATE_TWIN_GOAL','xy':[.30,0.],'room_revision':'b'*64,'duration_s':45.},0.,
            provider=lambda p,t:self.evidence,provenance='synthetic_raycast',frame_id='synthetic_room',
            context={'project_id':'room','source_revision':'a'*64,'epoch':1})

    def step(self,mission,t,pose=(0.,0.,0.),ranges=None):
        self.evidence['sample_s']=t;self.evidence['pose_map']=list(pose)
        return mission.step(LocalPose(pose,t,'synthetic_room','synthetic_model','synthetic_raycast'),
            LocalScan(tuple(ranges or [2.]*120),t,'base_link','synthetic_model','synthetic_raycast'),t,command_created_s=t)

    def test_feedback_multiple_starts_goal_transform_and_terminal_no_resume(self):
        for yaw in (0.,.2):
            mission=self.setup_mission();pose=[0.,0.,yaw]
            for i in range(800):
                result=self.step(mission,i*.05,tuple(pose));v,w=result['linear_m_s'],result['angular_rad_s']
                pose[0]+=v*.05*math.cos(pose[2]);pose[1]+=v*.05*math.sin(pose[2]);pose[2]+=w*.05
                if mission.phase=='ARRIVED':break
            self.assertEqual(mission.phase,'ARRIVED');self.assertLess(math.dist(pose[:2],[.3,0]),.02)
            self.assertEqual(self.step(mission,(i+1)*.05,tuple(pose))['linear_m_s'],0)
            self.assertFalse(mission.visual('e'*32)['motion_authorized'])

    def test_revision_zero_then_atomic_replan_unknown_goal_rejected(self):
        mission=self.setup_mission();self.assertGreater(self.step(mission,0.)['linear_m_s'],0)
        self.evidence['map_revision']='e'*64
        result=self.step(mission,.05);self.assertEqual(result['reason'],'REVISION_CHANGED_STOP_BEFORE_REPLAN')
        self.assertEqual(result['linear_m_s'],0);self.step(mission,.1);self.assertEqual(mission.plan_count,2)
        self.evidence['cells']=cells([(3,0)]);self.evidence['map_revision']='f'*64
        self.step(mission,.15);result=self.step(mission,.2)
        self.assertFalse(result['allowed']);self.assertIn('BLOCKED',result['reason'])

    def test_source_pose_jump_alignment_and_freshness_guards(self):
        for fault,reason in [('epoch','MISSION_SOURCE_EPOCH_CHANGED'),('room','GOAL_ROOM_REVISION_CHANGED'),
                ('alignment','CURRENT_PHOTO_ALIGNMENT_REQUIRED'),('jump','POSE_JUMP_REQUIRES_NEW_SESSION')]:
            mission=self.setup_mission();self.step(mission,0.)
            if fault=='epoch':self.evidence['epoch']=2
            if fault=='room':self.evidence['room_revision']='f'*64
            if fault=='alignment':self.evidence['alignment_status']='AMBIGUOUS'
            pose=(.5,0.,0.) if fault=='jump' else (0.,0.,0.)
            result=self.step(mission,.05,pose);self.assertEqual(result['reason'],reason);self.assertFalse(result['allowed'])
        mission=self.setup_mission();result=self.step(mission,0.,ranges=[.2]*120)
        self.assertEqual(result['reason'],'OBSTACLE_STOP_BEFORE_REPLAN');self.assertEqual(result['linear_m_s'],0)

    def test_dynamic_observed_obstacle_replans_nonfixed_path(self):
        mission=self.setup_mission();mission.goal['xy']=[.7,0.];self.step(mission,0.)
        self.evidence['cells']=cells([(3,0)]);self.evidence['map_revision']='e'*64
        self.step(mission,.05);result=self.step(mission,.1)
        self.assertTrue(result['allowed'],result);self.assertGreater(len(mission.route_map),1)
        self.assertTrue(any(abs(p[1])>.25 for p in mission.route_map))

    def test_terminal_path_failure_cannot_label_last_valid_pose_as_current(self):
        mission=self.setup_mission(scan_room=[[1.,0.]])
        self.step(mission,0.)
        self.evidence['cells']=cells([(3,0)]);self.evidence['map_revision']='e'*64
        self.step(mission,.05);result=self.step(mission,.10)
        self.assertFalse(result['allowed']);self.assertIn('BLOCKED',result['reason'])
        visual=mission.visual('e'*32)
        self.assertEqual(visual['state'],'FAILED');self.assertIsNone(visual['pose_room'])
        self.assertEqual(visual['scan_room'],[]);self.assertEqual(visual['route_room'],[])

    def test_fresh_route_dependency_ignores_far_wall_but_not_unknown_or_obstacle(self):
        for changed_state in ('occupied','unknown','missing'):
            with self.subTest(state=changed_state):
                mission=self.setup_mission(planning_revision_policy='FRESH_FOOTPRINT_DEPENDENCY_V1')
                mission.goal['xy']=[.7,0.]
                self.assertGreater(self.step(mission,0.)['linear_m_s'],0.)
                self.evidence['map_revision']='e'*64
                # The far wall is outside the committed swept footprint.
                self.evidence['cells']=cells([(10,10)])
                self.assertGreater(self.step(mission,.05)['linear_m_s'],0.)
                self.assertEqual(mission.plan_count,1)
                for row in self.evidence['cells']:
                    if abs(row[0]-.35)<1e-6 and abs(row[1]-.05)<1e-6:row[2]=changed_state
                if changed_state=='missing':self.evidence['cells']=[r for r in self.evidence['cells'] if r[2]!='missing']
                result=self.step(mission,.1)
                self.assertEqual(result['reason'],'REVISION_CHANGED_STOP_BEFORE_REPLAN')
                self.assertEqual((result['linear_m_s'],result['angular_rad_s']),(0.,0.))
                next_tick=self.step(mission,.15)
                self.assertTrue(next_tick['allowed'],next_tick)
                self.assertGreater(len(mission.route_map),1)
                self.assertEqual(mission.plan_count,2)

    def test_larger_measured_footprint_never_uses_the_smaller_route(self):
        mission=self.setup_mission(planning_revision_policy='FRESH_FOOTPRINT_DEPENDENCY_V1')
        self.evidence['cells']=cells([(0,4)])
        self.assertGreater(self.step(mission,0.)['linear_m_s'],0.)
        self.evidence['footprint_radius_m']=.4
        self.assertEqual(self.step(mission,.05)['reason'],'REVISION_CHANGED_STOP_BEFORE_REPLAN')
        result=self.step(mission,.1)
        self.assertFalse(result['allowed']);self.assertIn('BLOCKED',result['reason'])
