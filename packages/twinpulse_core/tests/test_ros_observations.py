# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
from types import SimpleNamespace as NS
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from twinpulse_core.ros_observations import RosObservations, valid_snapshot, scan_preview, valid_scan_preview


def message(kind='odom',stamp=9_950_000_000):
    header=NS(frame_id='odom' if kind=='odom' else 'base_scan',stamp=NS(sec=stamp//10**9,nanosec=stamp%10**9))
    if kind=='odom':return NS(header=header,child_frame_id='base_footprint',pose=NS(pose=NS(
        position=NS(x=.1,y=.2,z=0.),orientation=NS(x=0.,y=0.,z=0.,w=1.))))
    return NS(header=header,ranges=[1.]*72,angle_min=0.,angle_max=71*math.tau/72,
              angle_increment=math.tau/72,range_min=.05,range_max=10.,time_increment=.0005)


class RosObservationTests(unittest.TestCase):
    def test_coin_d4_exclusive_endpoint_and_100m_metadata_display_only(self):
        msg=message('scan');msg.ranges=[1.]*394
        msg.angle_increment=.015906797721982002
        msg.angle_max=6.2831854820251465;msg.range_min=.10000000149;msg.range_max=100.
        diagnostic={};preview=scan_preview(msg,10**10,20.,diagnostic=diagnostic)
        self.assertTrue(valid_scan_preview(preview));self.assertEqual(diagnostic['reason'],'NONE')
        self.assertEqual(len(preview['ranges_m']),394)
        self.assertEqual(preview['range_max_m'],100.)
        strict=RosObservations();strict.receive('scan',msg,10**10,20.,1)
        self.assertIsNone(strict.snapshot(20.)['scan'])
        msg.angle_max+=.2
        self.assertIsNone(scan_preview(msg,10**10,20.,diagnostic=diagnostic))
        self.assertEqual(diagnostic['reason'],'ANGLE_ENDPOINT')
        msg.angle_max=6.2831854820251465;msg.range_max=float('inf')
        self.assertIsNone(scan_preview(msg,10**10,20.,diagnostic=diagnostic))
        self.assertEqual(diagnostic['reason'],'DISPLAY_METADATA')

    def test_display_scan_preserves_missing_rays_without_relaxing_navigation(self):
        msg=message('scan');msg.ranges[:4]=[float('inf'),float('nan'),0.,20.]
        preview=scan_preview(msg,10**10,20.)
        self.assertTrue(valid_scan_preview(preview))
        self.assertEqual(preview['ranges_m'][:5],[None,None,None,None,1.])
        self.assertTrue(preview['display_only']);self.assertFalse(preview['alignment_verified'])
        r=RosObservations();r.receive('scan',msg,10**10,20.,1)
        self.assertIsNone(r.snapshot(20.)['scan'])
        self.assertEqual(r.snapshot(20.)['faults']['scan'],'SCAN_RANGES')
        self.assertFalse(valid_scan_preview({**preview,'alignment_verified':True}))

    def test_display_rejects_bad_geometry_timestamp_and_unbounded_rays(self):
        for change in ('angle','stamp','size','frame'):
            msg=message('scan')
            if change=='angle':msg.angle_max+=1.
            if change=='stamp':msg.header.stamp.nanosec=-1
            if change=='size':msg.ranges*=11
            if change=='frame':msg.header.frame_id='<script>'
            self.assertIsNone(scan_preview(msg,10**10,20.))
        self.assertIsNone(scan_preview(message('scan'),13*10**9,20.))

    def test_age_and_raw_frames_preserved_no_transform_or_authority(self):
        r=RosObservations()
        for kind in ('odom','scan'):r.receive(kind,message(kind),10**10,20.,1)
        value=r.snapshot(20.01)
        self.assertTrue(valid_snapshot(value));self.assertAlmostEqual(value['odom']['sample_s'],19.95)
        self.assertEqual(value['odom']['child_frame_id'],'base_footprint')
        self.assertEqual(value['scan']['frame_id'],'base_scan')
        self.assertFalse(value['alignment_verified']);self.assertFalse(value['motion_authorized'])
        value['scan']['ranges_m'][0]=0.
        self.assertEqual(r.snapshot(20.01)['scan']['ranges_m'][0],1.)
        self.assertEqual(r.snapshot(20.2)['faults'],{'odom':'STALE','scan':'STALE'})
        with self.assertRaises(ValueError):r.snapshot(20.01)

    def test_future_stale_duplicate_and_out_of_order_clear_old_value(self):
        for stamp in (10_010_000_000,9_700_000_000,9_950_000_000,9_940_000_000):
            r=RosObservations();r.receive('odom',message(),10**10,20.,1)
            r.receive('odom',message(stamp=stamp),10_010_000_000,20.01,1)
            # At exactly reception time a future source for the previous call is not future here.
            if stamp==10_010_000_000:
                r.receive('odom',message(stamp=10_020_000_000),10_010_000_000,20.01,1)
            self.assertIsNone(r.snapshot(20.01)['odom'])
            self.assertEqual(r.snapshot(20.01)['faults']['odom'],'SOURCE_TIME')

    def test_invalid_endpoints_and_message_fields(self):
        for count in (0,2,True):
            r=RosObservations();r.receive('odom',message(),10**10,20.,count)
            self.assertEqual(r.snapshot(20.)['faults']['odom'],'ENDPOINT_COUNT')
        for mutate in (lambda m:setattr(m.header,'frame_id','../secret'),
                       lambda m:setattr(m.header.stamp,'nanosec',10**9),
                       lambda m:setattr(m.pose.pose.position,'x',float('nan')),
                       lambda m:setattr(m.pose.pose.orientation,'w',.5)):
            r=RosObservations();m=message();mutate(m);r.receive('odom',m,10**10,20.,1)
            self.assertIsNone(r.snapshot(20.)['odom'])

    def test_old_slash_prefixed_vendor_frame_is_rejected_not_silently_relabelled(self):
        r=RosObservations();m=message();m.header.frame_id='/tp_guard_stationary/odom'
        m.child_frame_id='/tp_guard_stationary/base_footprint'
        r.receive('odom',m,10**10,20.,1)
        self.assertEqual(r.snapshot(20.)['faults']['odom'],'FRAME_ID')
        self.assertIsNone(r.snapshot(20.)['odom'])

    def test_rejected_odom_has_bounded_diagnostic_without_pose_or_authority(self):
        cases=(('FRAME_ID',lambda m:setattr(m.header,'frame_id','../secret')),
               ('STAMP_FORMAT',lambda m:setattr(m.header.stamp,'nanosec',10**9)),
               ('ODOM_POSITION',lambda m:setattr(m.pose.pose.position,'x',float('nan'))),
               ('ODOM_ORIENTATION',lambda m:setattr(m.pose.pose.orientation,'w',.5)),
               ('MESSAGE_SHAPE',lambda m:delattr(m,'pose')))
        for reason,mutate in cases:
            with self.subTest(reason=reason):
                r=RosObservations();m=message();mutate(m)
                r.receive('odom',m,10**10,20.,1)
                snapshot=r.snapshot(20.)
                self.assertTrue(valid_snapshot(snapshot))
                self.assertIsNone(snapshot['odom'])
                self.assertEqual(snapshot['faults']['odom'],reason)
                self.assertFalse(snapshot['alignment_verified'])
                self.assertFalse(snapshot['motion_authorized'])
                self.assertEqual(set(snapshot),{'schema','t','odom','scan','faults',
                                                'alignment_verified','motion_authorized'})

    def test_diagnostic_does_not_accept_or_reuse_rejected_odom(self):
        r=RosObservations();r.receive('odom',message(),10**10,20.,1)
        bad=message(stamp=9_960_000_000);bad.pose.pose.orientation.w=.5
        r.receive('odom',bad,10_010_000_000,20.01,1)
        self.assertEqual(r.snapshot(20.01)['faults']['odom'],'ODOM_ORIENTATION')
        self.assertIsNone(r.snapshot(20.01)['odom'])
        r.receive('odom',message(stamp=9_970_000_000),10_020_000_000,20.02,1)
        self.assertEqual(r.snapshot(20.02)['faults']['odom'],'NONE')
        self.assertEqual(r.snapshot(20.02)['odom']['source_stamp_ns'],9_970_000_000)

    def test_scan_missing_rays_geometry_and_unfinished_sweep_not_filled(self):
        for mutate in (lambda m:setattr(m,'ranges',[1.]*721),
                       lambda m:setattr(m,'ranges',[1.]*71),
                       lambda m:m.ranges.__setitem__(1,float('inf')),
                       lambda m:m.ranges.__setitem__(1,0.),
                       lambda m:setattr(m,'angle_max',1.),
                       lambda m:setattr(m,'angle_increment',.05),
                       lambda m:setattr(m,'time_increment',.002)):
            r=RosObservations();m=message('scan');mutate(m);r.receive('scan',m,10**10,20.,1)
            self.assertIsNone(r.snapshot(20.)['scan'])

    def test_clock_jump_latches_both_topics(self):
        for ros,mono in ((10_100_000_000,20.),(10**10,19.9),(0,20.)):
            r=RosObservations();r.receive('odom',message(),10**10,20.,1)
            r.receive('scan',message('scan'),ros,mono,1)
            self.assertEqual(r.snapshot(20.)['faults'],{'odom':'CLOCK_FAULT','scan':'CLOCK_FAULT'})
            r.receive('odom',message(),10**10,20.,1)
            self.assertIsNone(r.snapshot(20.)['odom'])

    def test_pc_contract_rejects_authority_extra_fields_and_inconsistent_state(self):
        r=RosObservations();r.receive('odom',message(),10**10,20.,1)
        value=r.snapshot(20.)
        for key,val in (('motion_authorized',True),('alignment_verified',True),('t',False),('extra','x')):
            bad=copy.deepcopy(value);bad[key]=val;self.assertFalse(valid_snapshot(bad))
        bad=copy.deepcopy(value);bad['faults']['odom']='STALE';self.assertFalse(valid_snapshot(bad))


if __name__=='__main__':unittest.main()
