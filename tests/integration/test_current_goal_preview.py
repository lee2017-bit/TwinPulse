# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Goal contracts and actual planner/control loop, synthetic observations only."""
from copy import deepcopy
from dataclasses import replace
import math
import unittest
from twinpulse_core.current_goal_preview import goal_preview,check_preview
from twinpulse_core.observed_mission import ObservedMission
from twinpulse_core.local_navigation import LocalPose,LocalScan
from tests.integration.test_scene_changes import room_source


def evidence():
    return {'project_id':'goal_room','source_revision':'e'*64,'epoch':1,
        'room_revision':'b'*64,'map_revision':'c'*64,'alignment_revision':'d'*64,
        'room_from_map':[0.,0.,0.],'pose_map':[0.,-1.8,0.],'sample_s':1.,
        'state':'TRACKING_CANDIDATE','alignment_status':'ALIGNMENT_CANDIDATE',
        'bounds':[-3.,3.,-3.,3.],'cells':[[x/10+.05,y/10+.05,'free',1,0,1,'a'*64]
            for x in range(-30,30) for y in range(-30,30)]}


class CurrentGoalPreviewTests(unittest.TestCase):
    def setUp(self):
        self.scene=room_source().site.scene;self.current=evidence()
        self.context={k:self.current[k] for k in ('project_id','source_revision','epoch')}

    def preview(self,text='Go x=.15 y=-1.8',**kwargs):
        return goal_preview(self.scene,text,self.current,self.context,1.,**kwargs)

    def test_exact_coordinate_plan_has_physical_guard_profile_and_no_authority(self):
        plan=self.preview()['plan']
        self.assertEqual(plan['start'],[0.,-1.8]);self.assertEqual(plan['goal'],[.15,-1.8])
        self.assertEqual(plan['max_linear_mps'],.03);self.assertEqual(plan['max_angular_rps'],.2)
        self.assertFalse(plan['physical_authority']);self.assertEqual(plan['mode'],'REAL_CANDIDATE')
        self.assertEqual(check_preview(plan,self.current,self.context,1.,plan['goal_contract']),plan)

    def test_semantic_approach_outside_nominal_object_and_ambiguity(self):
        review=self.preview('Go to bed')
        self.assertEqual(review['target']['id'],'bed')
        goal=review['plan']['goal'];self.assertFalse(-1.6<goal[0]<-.4 and -.9<goal[1]<.9)
        desk=next(o for o in self.scene.objects if o.id=='desk')
        self.scene=replace(self.scene,objects=self.scene.objects+(replace(desk,id='desk_two',
            transform=replace(desk.transform,position_m=(1.,1.5,.35))),))
        review=self.preview('Go to desk',furniture={'desk':'desk','desk_two':'desk'})
        self.assertIsNone(review['plan']);self.assertEqual(len(review['choices']),2)
        selected=self.preview('Go to desk',furniture={'desk':'desk','desk_two':'desk'},selection='desk_two')
        self.assertEqual(selected['target']['id'],'desk_two')

    def test_photo_obstacle_cannot_be_driven_into_even_if_grid_claims_free(self):
        for text in ('Go x=-1 y=0','Go x=5 y=0','Go to Mars','Go from x=0 y=0 to x=.2 y=0'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.preview(text)

    def test_rejects_missing_stale_lost_frame_alignment_and_source(self):
        for change in ({'sample_s':.8},{'sample_s':2.},{'state':'LOST'},
                       {'pose_map':None},{'alignment_status':'AMBIGUOUS'},
                       {'room_from_map':None},{'source_revision':'f'*64},{'footprint_radius_m':2.}):
            with self.subTest(change=change):
                self.current=evidence();self.current.update(change)
                with self.assertRaises(ValueError):self.preview()

    def test_stale_confirmation_rejects_hand_move_new_grid_transform_epoch(self):
        plan=self.preview()['plan']
        for kind in ('pose','yaw','room','map','alignment','epoch','transform','unversioned_grid'):
            self.current=evidence()
            if kind=='pose':self.current['pose_map'][0]+=.01
            if kind=='yaw':self.current['pose_map'][2]+=.01
            if kind=='room':self.current['room_revision']='f'*64
            if kind=='map':self.current['map_revision']='f'*64
            if kind=='alignment':self.current['alignment_revision']='f'*64
            if kind=='epoch':self.current['epoch']=2
            if kind=='transform':self.current['room_from_map'][0]+=.01
            if kind=='unversioned_grid':self.current['cells'][0][2]='occupied'
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                check_preview(plan,self.current,self.context,1.,plan['goal_contract'])
        self.current=evidence();self.current['cells'][0][3]+=1
        self.assertEqual(check_preview(plan,self.current,self.context,1.,plan['goal_contract']),plan)

    def test_unknown_conflicting_and_blocked_goal_never_become_free(self):
        for state in ('unknown','occupied','missing','conflict'):
            self.current=evidence()
            cell=next(r for r in self.current['cells'] if abs(r[0]-.15)<.01 and abs(r[1]+1.85)<.01)
            if state=='missing':self.current['cells'].remove(cell)
            elif state=='conflict':self.current['cells'].append([*cell[:2],'occupied',*cell[3:]])
            else:cell[2]=state
            with self.subTest(state=state),self.assertRaises(ValueError):self.preview()

    def mission(self,plan):
        return ObservedMission(plan['goal_contract'],1.,provider=lambda p,t:self.current,
            provenance='synthetic_raycast',frame_id='synthetic_room',context=self.context,approved_preview=plan)

    def step(self,mission,t):
        self.current['sample_s']=t
        pose=LocalPose(tuple(self.current['pose_map']),t,'synthetic_room','synthetic_model','synthetic_raycast')
        return mission.step(pose,LocalScan((3.,)*120,t,'base_link','synthetic_model','synthetic_raycast'),t,command_created_s=t)

    def test_change_between_confirm_and_first_tick_publishes_zero(self):
        for kind in ('hand_move','new_obstacle','route_tamper'):
            self.current=evidence();plan=self.preview()['plan'];mission=self.mission(plan)
            if kind=='hand_move':self.current['pose_map'][0]+=.1
            if kind=='new_obstacle':self.current['cells'][0][2]='occupied'
            if kind=='route_tamper':mission.approved_preview['route'][0][0]+=.1
            result=self.step(mission,1.)
            with self.subTest(kind=kind):
                self.assertFalse(result['allowed']);self.assertEqual(result['linear_m_s'],0.)
                self.assertEqual(result['angular_rad_s'],0.);self.assertFalse(mission.preview_consumed)

    def test_same_confirm_reactive_closed_loop_arrives_multiple_starts(self):
        for x,yaw in ((0.,0.),(-.1,.2)):
            self.current=evidence();self.current['pose_map']=[x,-1.8,yaw]
            plan=self.preview()['plan'];mission=self.mission(plan)
            for n in range(850):
                result=self.step(mission,1.+n*.05);v,w=result['linear_m_s'],result['angular_rad_s']
                self.current['pose_map'][0]+=v*.05*math.cos(self.current['pose_map'][2])
                self.current['pose_map'][1]+=v*.05*math.sin(self.current['pose_map'][2])
                self.current['pose_map'][2]+=w*.05
                if mission.phase=='ARRIVED':break
            self.assertEqual(mission.phase,'ARRIVED',result)
            self.assertTrue(mission.preview_consumed);self.assertLess(math.dist(self.current['pose_map'][:2],[.15,-1.8]),.02)
            self.assertEqual(self.step(mission,1.+(n+1)*.05)['linear_m_s'],0.)

    def test_no_plan_before_fresh_observation_after_manual_reposition(self):
        first=self.preview()['plan'];self.current['pose_map']=[-.3,-1.8,.3]
        next_plan=self.preview()['plan'];self.assertNotEqual(first['plan_id'],next_plan['plan_id'])
        self.assertEqual(next_plan['start'],[-.3,-1.8])


if __name__=='__main__':unittest.main()
