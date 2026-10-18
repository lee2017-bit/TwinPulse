# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from twinpulse_core.local_navigation import LocalScan, LocalPose, CheckedMission, WaypointMission, guarded_velocity, checked_command


class LocalNavigationTests(unittest.TestCase):
    def test_reverse_requires_explicit_policy_and_same_full_scan_guards(self):
        plain=WaypointMission(((-.3,0.),),0.)
        self.assertEqual(plain.tick((0.,0.,0.),0.),(0.,.2))
        for radius,age,reason in ((2.,0.,'CLEAR_IN_SCAN_ENVELOPE'),(.2,0.,'OBSTACLE_IN_SWEPT_ENVELOPE'),
                                  (2.,.25,'SOURCE_EXPIRED_DURING_ENABLE')):
            mission=CheckedMission(((-.3,0.),),0.,provenance='synthetic_raycast',frame_id='synthetic_room',allow_reverse=True)
            result=mission.step(LocalPose((0.,0.,0.),1.,'synthetic_room','synthetic_model','synthetic_raycast'),
                self.scan(radius),1.,command_created_s=1.-age)
            self.assertEqual(result['reason'],reason)
            self.assertEqual(result['linear_m_s'],-.03 if age==0. and radius==2. else 0.)
        with self.assertRaises(ValueError):WaypointMission(((-.3,0.),),0.,allow_reverse='yes')
    def test_shared_output_command_bounds_and_supervised_is_not_scan_clear(self):
        for age in (-.01,.25,float('nan'),True):
            self.assertFalse(checked_command(.03,0.,age,None,1.,require_scan=False)['allowed'])
        value=checked_command(.03,0.,.1,None,1.,require_scan=False)
        self.assertTrue(value['allowed']);self.assertFalse(value['physical_authority'])
        self.assertEqual(value['reason'],'SUPERVISED_WITHOUT_SCAN_CHECK')
        self.assertFalse(checked_command(.03,0.,.1,self.scan(),1.,provenance='live_sensor')['allowed'])

    def test_checked_live_pose_scan_and_command_failures_latch(self):
        pose=LocalPose((0.,0.,0.),1.,'odom','measured_odometry','live_sensor')
        scan=self.scan(stamp=1.,kind='live_sensor',basis='measured_sensor_extrinsic')
        cases=[(None,scan,1.,'POSE_FRAME_UNVERIFIED'),
               (LocalPose(pose.xy_yaw,.79,'odom','measured_odometry','live_sensor'),scan,1.,'POSE_STALE'),
               (LocalPose(pose.xy_yaw,1.1,'odom','measured_odometry','live_sensor'),scan,1.,'POSE_STALE'),
               (LocalPose(pose.xy_yaw,1.,'odom','photo_hypothesis','live_sensor'),scan,1.,'POSE_FRAME_UNVERIFIED'),
               (pose,self.scan(),1.,'SCAN_SOURCE_MISMATCH'),
               (pose,scan,.7,'SOURCE_EXPIRED_DURING_ENABLE'),
               (pose,self.scan(stamp=.79,kind='live_sensor',basis='measured_sensor_extrinsic'),1.,'SCAN_STALE')]
        for p,s,created,reason in cases:
            m=CheckedMission(((1.,0.),),0.,provenance='live_sensor',frame_id='odom')
            d=m.step(p,s,1.,command_created_s=created)
            self.assertEqual(d['reason'],reason);self.assertEqual((d['linear_m_s'],d['angular_rad_s']),(0.,0.))
            self.assertFalse(m.step(pose,scan,1.,command_created_s=1.)['allowed'])

    def test_mission_lifetime_is_not_manual_hold_and_never_refreshes_old_command(self):
        m=CheckedMission(((1.,0.),),0.,provenance='synthetic_raycast',frame_id='synthetic_room',duration_s=3.)
        def pose(t):return LocalPose((0.,0.,0.),t,'synthetic_room','synthetic_model','synthetic_raycast')
        self.assertTrue(m.step(pose(2.1),self.scan(stamp=2.1),2.1,command_created_s=2.)['allowed'])
        self.assertEqual(m.step(pose(3.),self.scan(stamp=3.),3.,command_created_s=3.)['reason'],'MISSION_EXPIRED')

    def test_checked_mission_arrival_and_clock_fault_without_approval_callback(self):
        for now,xy,reason in [(1.,(1.,0.,0.),'ARRIVED'),(-1.,(0.,0.,0.),'CLOCK_FAULT')]:
            m=CheckedMission(((1.,0.),),0.,provenance='synthetic_raycast',frame_id='synthetic_room')
            pose=LocalPose(xy,now,'synthetic_room','synthetic_model','synthetic_raycast')
            decision=m.step(pose,self.scan(stamp=now),now,command_created_s=now)
            self.assertEqual(m.mission.status,reason);self.assertEqual(decision['linear_m_s'],0.)

    def scan(self,r=2.,stamp=1.,kind='synthetic_raycast',basis='synthetic_model'):
        return LocalScan((r,)*72,stamp,'base_link',basis,kind)

    def test_all_directions_use_full_body_envelope(self):
        for v,w in ((.03,0.),(-.03,0.),(0.,.2),(0.,-.2)):
            self.assertTrue(guarded_velocity(v,w,self.scan(),1.)['allowed'])
            blocked=guarded_velocity(v,w,self.scan(.21),1.)
            self.assertFalse(blocked['allowed']);self.assertEqual(blocked['linear_m_s'],0.)
            self.assertEqual(blocked['angular_rad_s'],0.)

    def test_rear_and_missing_returns_cannot_be_ignored(self):
        for bad in (0.,float('nan'),float('inf'),True):
            rays=[2.]*72;rays[36]=bad
            s=LocalScan(tuple(rays),1.,'base_link','synthetic_model','synthetic_raycast')
            self.assertEqual(guarded_velocity(.03,0.,s,1.)['reason'],'SCAN_COVERAGE_UNKNOWN')
        self.assertFalse(guarded_velocity(.03,0.,LocalScan((2.,)*36,1.,'base_link','synthetic_model','synthetic_raycast'),1.)['allowed'])

    def test_saved_unregistered_stale_future_scans_stop(self):
        for scan in (self.scan(stamp=.79),self.scan(stamp=1.1),self.scan(kind='saved_sensor_recording'),
                     self.scan(basis='photo_hypothesis'),self.scan(kind='live_sensor'),None):
            self.assertFalse(guarded_velocity(.03,0.,scan,1.)['allowed'])
        self.assertTrue(guarded_velocity(0.,0.,None,1.)['allowed'])

    def test_invalid_commands_never_pass(self):
        for v,w in ((float('nan'),0.),(.04,0.),(0.,.21),(True,0.)):
            self.assertFalse(guarded_velocity(v,w,self.scan(),1.)['allowed'])

    def test_translation_budget_is_more_conservative_than_rotation(self):
        self.assertTrue(guarded_velocity(0.,.2,self.scan(.25),1.)['allowed'])
        self.assertFalse(guarded_velocity(.03,0.,self.scan(.25),1.)['allowed'])

    def test_mission_turn_drive_arrive_without_command_approval(self):
        m=WaypointMission(((0.,.1),),0.)
        self.assertEqual(m.tick((0.,0.,0.),0.),(0.,.2))
        self.assertEqual(m.tick((0.,0.,math.pi/2),1.),(.03,0.))
        self.assertEqual(m.tick((0.,.1,math.pi/2),2.),(0.,0.));self.assertEqual(m.status,'ARRIVED')
        self.assertEqual(m.tick((0.,0.,0.),3.),(0.,0.))

    def test_clock_deadline_and_invalid_pose_latch(self):
        for now,pose,reason in ((90.,(0.,0.,0.),'MISSION_EXPIRED'),(-1.,(0.,0.,0.),'CLOCK_FAULT'),
                                (1.,(float('nan'),0.,0.),'POSE_INVALID')):
            m=WaypointMission(((0.,1.),),0.)
            self.assertEqual(m.tick(pose,now),(0.,0.));self.assertEqual(m.status,reason)
            self.assertEqual(m.tick((0.,0.,0.),2.),(0.,0.))

    def test_mission_bounds(self):
        for route in ((),((float('inf'),0.),),((0.,0.),)*17):
            with self.assertRaises(ValueError):WaypointMission(route,0.)


if __name__=='__main__':unittest.main()
