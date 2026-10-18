# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from types import SimpleNamespace as NS
from twinpulse_core.observation_stream import (ObservationWindow, RecordedObservationSource,
    from_ros_message, scan_quality)
from twinpulse_core.room_localization import PoseTimeline, deskew


CONTEXT={'project_id':'default','session_id':'test','boot_id':'boot','release_id':'a'*64,
         'source_revision':'b'*64,'origin':'recorded_ros'}
def odom(ns=1_000_000_000,x=0,yaw=0):
    return {'stamp_ns':ns,'frame_id':'odom','child_frame_id':'base_footprint',
            'position_m':[x,0,0],'quaternion_xyzw':[0,0,math.sin(yaw/2),math.cos(yaw/2)]}
def scan():
    return {'stamp_ns':1_000_000_000,'frame_id':'base_scan','angle_min':0.,
            'angle_max':math.tau,'angle_increment':math.tau/360,'time_increment':.0002,
            'scan_time':.072,'range_min':.1,'range_max':100.,'ranges_m':[1.]*359}


class CommonObservationTests(unittest.TestCase):
    def test_actual_coin_shape_unknowns_and_terminal_gap_are_not_stretched(self):
        value=scan();value['ranges_m'][20]=None;before=copy.deepcopy(value)
        w=ObservationWindow(CONTEXT);event=w.receive('scan',value,0,10)
        self.assertEqual(value,before);self.assertEqual(event['data'],value)
        self.assertEqual(event['quality']['unknown_rays'],1)
        self.assertEqual(event['quality']['control_coverage'],'UNKNOWN')
        self.assertFalse(w.summary()['motion_authorized'])
        self.assertFalse(w.summary()['alignment_verified'])
        self.assertEqual(w.summary()['faults']['/tf_static'],'NOT_RECEIVED')

    def test_signed_angular_order_does_not_reverse_acquisition_time(self):
        value=scan();value.update(angle_increment=-value['angle_increment'],angle_max=-math.tau)
        quality=scan_quality(value)
        self.assertGreater(quality['last_stamp_ns'],value['stamp_ns'])
        value['time_increment']=-.0002
        with self.assertRaisesRegex(ValueError,'GEOMETRY'):scan_quality(value)

    def test_causal_source_does_not_decode_future_and_failed_frame_does_not_stop_others(self):
        seen=[]
        def decode(kind,payload):
            seen.append(payload)
            if payload=='bad':raise ValueError('CDR_FAIL')
            return odom(1_000_000_000+len(seen)*10_000_000)
        source=RecordedObservationSource([
            ({'topic':'odom','type':'nav_msgs/msg/Odometry','sequence':i,'receipt_monotonic_ns':i},p)
            for i,p in enumerate(('first','bad','last'))],decode,CONTEXT)
        it=iter(source);next(it);self.assertEqual(seen,['first'])
        self.assertEqual(next(it)['reason'],'CDR_DECODE_FAILED')
        self.assertEqual(next(it)['data']['stamp_ns'],1_030_000_000)
        self.assertEqual(source.window.summary()['counts'],{'odom':3})

    def test_sequence_receipt_and_ros_jump_latch_all_topics(self):
        for change in ('sequence','receipt','ros'):
            w=ObservationWindow(CONTEXT)
            w.receive('odom',odom(),0,1_000_000_000,ros_now_ns=1_000_000_000,publishers=1)
            w.receive('odom',odom(1_010_000_000),0 if change=='sequence' else 1,
                      900_000_000 if change=='receipt' else 1_010_000_000,
                      ros_now_ns=2_000_000_000 if change=='ros' else 1_010_000_000,publishers=1)
            self.assertTrue(w.clock_fault);self.assertTrue(all(v is None for v in w.latest.values()))
            self.assertIsNone(w.receive('scan',scan(),2,1_020_000_000))

    def test_stale_future_missing_multiple_publishers_and_shape_are_distinct(self):
        for value,now,pubs,reason in ((odom(),1_300_000_000,1,'SOURCE_STALE'),
            (odom(),900_000_000,1,'IN_FUTURE'),(odom(),1_000_000_000,0,'ENDPOINT_MISSING'),
            (odom(),1_000_000_000,2,'MULTIPLE'),(None,1_000_000_000,1,'MESSAGE_SHAPE')):
            w=ObservationWindow(CONTEXT);self.assertIsNone(w.receive('odom',value,0,10,ros_now_ns=now,publishers=pubs))
            self.assertIn(reason,w.faults['odom'])
        w=ObservationWindow(CONTEXT);w.receive('odom',odom(),0,10)
        self.assertEqual(w.health_at(200_000_011)['faults']['odom'],'OBSERVATION_RECEIPT_STALE')

    def test_common_interpolation_waits_for_bracket_without_future_or_extrapolation(self):
        w=ObservationWindow(CONTEXT);w.receive('odom',odom(),0,10)
        with self.assertRaisesRegex(ValueError,'UNBRACKETED'):w.pose_at(1_050_000_000)
        w.receive('odom',odom(1_100_000_000,x=1,yaw=.2),1,20)
        self.assertAlmostEqual(w.pose_at(1_050_000_000)[0],.5)
        self.assertAlmostEqual(w.pose_at(1_050_000_000)[2],.1)
        with self.assertRaisesRegex(ValueError,'UNBRACKETED'):w.pose_at(1_200_000_000)
        w.receive('odom',odom(1_300_000_000),2,30)
        with self.assertRaisesRegex(ValueError,'GAP'):w.pose_at(1_200_000_000)

    def test_frame_change_requires_new_epoch_not_old_interpolation(self):
        w=ObservationWindow(CONTEXT);w.receive('odom',odom(),0,10)
        w.receive('odom',{**odom(1_010_000_000),'child_frame_id':'changed'},1,20)
        self.assertTrue(w.epoch_fault);self.assertEqual(w.faults['odom'],'OBSERVATION_FRAME_CHANGED')
        with self.assertRaisesRegex(ValueError,'FRAME_LATCHED'):w.pose_at(1_000_000_000)
        with self.assertRaisesRegex(ValueError,'FRAME_LATCHED'):w.events_since(-1)

    def test_tf_missing_empty_self_edge_future_and_static_zero_are_distinct(self):
        row={'stamp_ns':0,'frame_id':'base_link','child_frame_id':'base_scan',
             'translation_m':[.017,0,.18],'quaternion_xyzw':[0,0,0,1]}
        w=ObservationWindow(CONTEXT);self.assertIsNotNone(w.receive('/tf_static',{'transforms':[row]},0,0))
        self.assertFalse(w.summary()['alignment_verified'])
        w.receive('/tf',{'transforms':[]},1,1);self.assertEqual(w.faults['/tf'],'TF_EMPTY_MESSAGE')
        w.receive('/tf',{'transforms':[{**row,'stamp_ns':1,'child_frame_id':'base_link'}]},2,2)
        self.assertEqual(w.faults['/tf'],'TF_SELF_EDGE')
        w.receive('/tf',{'transforms':[{**row,'stamp_ns':200}]},3,3,ros_now_ns=100)
        self.assertEqual(w.faults['/tf'],'OBSERVATION_SOURCE_IN_FUTURE')

    def test_rotating_deskew_preserves_ray_time_and_negative_angles(self):
        value=scan();value.update(angle_increment=-math.tau/360,angle_max=-math.tau)
        timeline=PoseTimeline([odom(1_000_000_000),odom(1_100_000_000,yaw=.5)])
        points,_=deskew(value,timeline,[0,0,0],max_points=720)
        i=100;ray=i*value['angle_increment']+.5*(i*.0002/.1)
        self.assertAlmostEqual(points[i][0],math.cos(ray));self.assertAlmostEqual(points[i][1],math.sin(ray))
        with self.assertRaisesRegex(ValueError,'UNBRACKETED'):
            deskew({**value,'stamp_ns':1_090_000_000},timeline,[0,0,0])

    def test_bounded_history_and_detached_payload(self):
        w=ObservationWindow(CONTEXT,capacity=4);value=odom()
        for i in range(6):w.receive('odom',{**value,'stamp_ns':1_000_000_000+i},i,i)
        value['position_m'][0]=99
        self.assertEqual(len(w.history),4);self.assertEqual(w.evicted,2)
        self.assertEqual(w.history[-1]['data']['position_m'][0],0)
        with self.assertRaisesRegex(ValueError,'CONSUMER_OVERRUN'):w.events_since(0)
        events=w.events_since(3);self.assertEqual([e['sequence'] for e in events],[4,5])
        events[-1]['data']['position_m'][0]=100
        self.assertEqual(w.history[-1]['data']['position_m'][0],0)

    def test_live_and_recorded_normalization_share_identical_geometry(self):
        s=scan();message=NS(header=NS(stamp=NS(sec=1,nanosec=0),frame_id='base_scan'),
                           ranges=s['ranges_m'],**{k:v for k,v in s.items() if k not in {'stamp_ns','frame_id','ranges_m'}})
        live=ObservationWindow({**CONTEXT,'origin':'live_ros'});recorded=ObservationWindow(CONTEXT)
        a=live.receive('scan',from_ros_message('scan',message),1,10)
        b=recorded.receive('scan',{**s,'invalid_returns':0},1,10)
        self.assertEqual(a,b)

if __name__=='__main__':unittest.main()
