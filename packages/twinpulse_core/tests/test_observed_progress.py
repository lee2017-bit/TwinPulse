# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import unittest
from twinpulse_core.observed_progress import ObservedProgressGuard
from packages.twinpulse_core.tests import test_observed_mission as fixture


class ProgressTests(unittest.TestCase):
    def test_without_publication_long_planning_is_not_a_stall(self):
        g=ObservedProgressGuard();g.check(20.,[0.,0.,0.],[0.,0.,0.])
        self.assertIsNone(g.kind)

    def exercise(self,v,w,pose):
        g=ObservedProgressGuard()
        for tick in range(61):
            now=tick*.05;odom,mapped=pose(now)
            g.check(now,odom,mapped);g.published(now,v,w,odom,mapped)
        return g

    def test_stalled_translation_rotation_or_disagreeing_odom_and_map_stop(self):
        for v,w,poses in ((.03,0.,lambda t:([0.,0.,0.],[0.,0.,0.])),
                          (0.,.2,lambda t:([0.,0.,0.],[0.,0.,0.])),
                          (.03,0.,lambda t:([t*.03,0.,0.],[0.,0.,0.])),
                          (.03,0.,lambda t:([0.,0.,0.],[t*.03,0.,0.]))):
            with self.subTest(v=v,w=w),self.assertRaisesRegex(ValueError,'OBSERVED_PROGRESS_STALLED'):
                self.exercise(v,w,poses)

    def test_normal_forward_reverse_and_turn_progress(self):
        for v,w in ((.03,0.),(-.03,0.),(0.,.2),(0.,-.2)):
            self.exercise(v,w,lambda t:([v*t,0.,w*t],[v*t,0.,w*t]))

    def test_zero_gap_replan_and_command_kind_changes_reset_anchor(self):
        for reset in ('zero','gap','turn'):
            g=ObservedProgressGuard();g.published(0.,.03,0.,[0.,0.,0.],[0.,0.,0.])
            if reset=='zero':g.published(.1,0.,0.,[0.,0.,0.],[0.,0.,0.])
            if reset=='gap':g.check(.3,[0.,0.,0.],[0.,0.,0.])
            if reset=='turn':g.published(.1,0.,.2,[0.,0.,0.],[0.,0.,0.])
            g.check(.15,[0.,0.,0.],[0.,0.,0.])
            self.assertTrue(g.kind is None or g.kind[0]=='ROTATION')

    def test_existing_mission_stops_before_next_output_and_drops_current_visual(self):
        helper=fixture.ObservedMissionTests();mission=helper.setup_mission()
        for tick in range(61):
            now=tick*.05;result=helper.step(mission,now)
            if tick<60:
                self.assertTrue(result['allowed']);mission.note_output(now,result['linear_m_s'],result['angular_rad_s'])
        self.assertEqual(result['reason'],'OBSERVED_PROGRESS_STALLED');self.assertFalse(result['allowed'])
        self.assertEqual(result['linear_m_s'],0.)
        self.assertIsNone(mission.visual('a'*32)['pose_room'])

    def test_alignment_failure_keeps_original_cause_before_stall_diagnosis(self):
        helper=fixture.ObservedMissionTests();mission=helper.setup_mission()
        for tick in range(60):
            now=tick*.05;result=helper.step(mission,now)
            mission.note_output(now,result['linear_m_s'],result['angular_rad_s'])
        helper.evidence['alignment_status']='MODEL_MISMATCH'
        result=helper.step(mission,3.)
        self.assertEqual(result['reason'],'CURRENT_PHOTO_ALIGNMENT_REQUIRED')
        self.assertFalse(result['allowed'])
