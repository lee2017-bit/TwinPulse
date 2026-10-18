# SPDX-License-Identifier: Apache-2.0
"""Supplementary observation/fault checks. No device or physical PASS."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety/tests'))
from field_tests import control_observation,frame_points,FieldGuard
from native_stream import NativeDecoder,NativeStream,freeze_frame
from test_field_tests import ring,config
from test_native_parser_quality import packet,UNKNOWN


def pair():
    previous=ring(1.);previous.update(stream_id='stream',frame_sequence=10)
    latest=ring(1.1);latest.update(stream_id='stream',frame_sequence=11,complete=False,
        quality=dict(complete_start=True,packet_contiguous=False,checksum_invalid_packets=0,
            interval_fallback_packets=0,unknown_boundary_policy='GAP_BEFORE_VALID_RING_START_BELONGS_TO_CLOSING_RING',
            unframed_bytes=11,unframed_spans=[dict(start=20,end=31,length=11,classification='UNKNOWN',framing_errors=0,raw_sha256='c'*64)]))
    return latest,previous


class ControlObservationTests(unittest.TestCase):
    def guard(self,latest,previous,now=1.1):
        native=SimpleNamespace(control_frames=lambda:(latest,previous))
        link=SimpleNamespace(sensor_t=now,sensor=SimpleNamespace(left_encoder=0,right_encoder=0))
        return FieldGuard(config(),native,link,lambda:True,clock=lambda:now)

    def test_incomplete_ring_never_promoted_and_original_complete_clock_preserved(self):
        latest,previous=pair();before=deepcopy((latest,previous))
        for v,w in ((.03,0),(-.03,0),(0,.2),(0,-.2)):
            guard=self.guard(latest,previous);guard(v,w,1.1)
            self.assertEqual(guard.last_result['frame_sequence'],10)
            self.assertEqual(guard.last_result['latest_raw_frame_sequence'],11)
            self.assertAlmostEqual(guard.last_result['receipt_age_s'],.1)
            self.assertFalse(guard.last_result['latest_raw_ring_complete'])
        self.assertEqual((latest,previous),before)
        with self.assertRaisesRegex(ValueError,'COMPLETE'):frame_points(latest,config(),1.1)
        with self.assertRaisesRegex(ValueError,'STALE'):self.guard(latest,previous,1.351)(.03,0,1.351)

    def test_newer_obstacle_zero_or_invalid_always_vetoes_old_clear_ring(self):
        for v,w,index in ((.03,0,0),(-.03,0,180),(0,.2,90),(0,-.2,270)):
            for distance,quality,reason in ((.20,100,'PROXIMITY'),(0,100,'COVERAGE'),(1.,0,'COVERAGE')):
                latest,previous=pair();latest['beams'][index].update(distance_m=distance,quality=quality)
                if reason=='COVERAGE':
                    for delta in range(-3,4):latest['beams'][(index+delta)%360].update(distance_m=distance,quality=quality)
                with self.assertRaisesRegex(ValueError,reason):self.guard(latest,previous)(v,w,1.1)
        for key,value in (('angle_deg',math.nan),('distance_m',math.nan),('quality',math.inf),('valid_packet',False)):
            latest,previous=pair();latest['beams'][0][key]=value
            with self.assertRaisesRegex(ValueError,'INVALID'):self.guard(latest,previous)(.03,0,1.1)

    def test_bad_crc_fallback_partial_start_unknown_provenance_and_stream_are_not_cacheable(self):
        for key,value in (('checksum_invalid_packets',1),('interval_fallback_packets',1),('complete_start',False),('unframed_bytes',12)):
            latest,previous=pair();latest['quality'][key]=value
            with self.assertRaisesRegex(ValueError,'COMPLETE'):self.guard(latest,previous)(.03,0,1.1)
        for key,value in (('framing_errors',1),('framing_errors',None),('start',-1),('raw_sha256','bad')):
            latest,previous=pair();latest['quality']['unframed_spans'][0][key]=value
            with self.assertRaisesRegex(ValueError,'COMPLETE'):self.guard(latest,previous)(.03,0,1.1)
        for key,value in (('stream_id','other'),('frame_sequence',12),('complete',False)):
            latest,previous=pair();previous[key]=value
            with self.assertRaisesRegex(ValueError,'COMPLETE'):self.guard(latest,previous)(.03,0,1.1)

    def test_cone_intersection_gap_not_only_midpoint_including_wrap_and_reverse(self):
        for v,begin,end in ((.03,20,70),(.03,290,340),(-.03,200,250),(-.03,110,160)):
            frame=ring(1.1);frame['beams']=[b for b in frame['beams'] if not begin<b['angle_deg']<end]
            native=SimpleNamespace(latest_frame=lambda:frame)
            guard=FieldGuard(config(),native,SimpleNamespace(sensor_t=1.1),lambda:True,clock=lambda:1.1)
            with self.assertRaisesRegex(ValueError,'COVERAGE'):guard(v,0,1.1)

    def test_stop_fault_start_clears_pair_and_cannot_lend_old_stream(self):
        stream=NativeStream('.',lambda *_:None);latest,previous=pair()
        stream.frame,stream.complete_frame=freeze_frame(latest),freeze_frame(previous)
        stream.state['lidar_state']='STREAMING'
        self.assertIsNotNone(stream.control_frames()[1]);stream.stop()
        self.assertEqual(stream.control_frames(),(None,None));self.assertIsNone(stream.latest_frame())
        stream.cancel.clear();stream.frame,stream.complete_frame=latest,previous
        for state in ('STOPPING','OFF','FAULT','STARTING'):
            stream.state['lidar_state']=state;self.assertEqual(stream.control_frames(),(None,None))

    def test_malformed_header_is_distinct_from_unclassified_original_bytes_at_every_split(self):
        bad=b'\xaa\x55\x00\x00'+b'\x01'*6
        for gap,errors in ((UNKNOWN,0),(bad,1),(UNKNOWN+bad+UNKNOWN,1)):
            raw=packet(ring=True)+gap+packet()
            for split in range(1,len(raw)):
                decoder=NativeDecoder();rows=decoder.feed(raw[:split],1.)+decoder.feed(raw[split:],1.1)
                self.assertEqual(rows[-1]['preceding_unframed']['framing_errors'],errors)
                self.assertEqual(rows[-1]['preceding_unframed']['raw_sha256'],hashlib.sha256(gap).hexdigest())

    def test_latest_observed_hazard_during_computation_is_rechecked(self):
        latest,previous=pair();near=deepcopy(latest);near['frame_sequence']=12
        near['beams'][0]['distance_m']=.2
        calls=[]
        def frames():
            calls.append(1);return (latest if len(calls)==1 else near),previous
        guard=self.guard(latest,previous);guard.native=SimpleNamespace(control_frames=frames)
        with self.assertRaisesRegex(ValueError,'PROXIMITY'):guard(.03,0,1.1)
        self.assertEqual(guard.last_result['latest_raw_frame_sequence'],12)

    def test_sparse_no_returns_are_excluded_not_filled_and_wide_unknown_arc_stops(self):
        latest,previous=pair();latest['beams'][180]['distance_m']=0
        previous['beams'][180]['quality']=0
        guard=self.guard(latest,previous);guard(0,.2,1.1)
        self.assertEqual(guard.last_result['valid_return_count'],359)
        self.assertEqual(guard.last_result['latest_valid_return_count'],359)
        for i in range(178,184):latest['beams'][i]['distance_m']=0
        with self.assertRaisesRegex(ValueError,'COVERAGE_GAP'):guard(0,.2,1.1)

    def test_exact_existing_350ms_limit_and_end_of_compute_input_expiry(self):
        latest,previous=pair();previous['timing'].update(receipt_start_s=-.1,receipt_end_s=0.)
        latest['timing'].update(receipt_start_s=0.,receipt_end_s=.1)
        self.guard(latest,previous,.35)(.03,0,.35)
        with self.assertRaisesRegex(ValueError,'STALE'):self.guard(latest,previous,.350001)(.03,0,.350001)
        latest,previous=pair();now=[1.1];guard=self.guard(latest,previous);guard.clock=lambda:now[0]
        guard._progress_check=lambda *_:now.__setitem__(0,1.36)
        with self.assertRaisesRegex(ValueError,'EXPIRED|STALE'):guard(.03,0,1.1)

    def test_stream_disappearing_during_compute_revokes_instead_of_retiming(self):
        latest,previous=pair();calls=[]
        def frames():
            calls.append(1);return (latest,previous) if len(calls)==1 else (None,None)
        guard=self.guard(latest,previous);guard.native=SimpleNamespace(control_frames=frames)
        with self.assertRaisesRegex(ValueError,'STREAM_CHANGED'):guard(.03,0,1.1)

    def test_native_fault_revokes_pair_before_emit_or_cleanup(self):
        observations=[]
        def fail():raise ValueError('TEST_NATIVE_RECORDING_FAILURE')
        with tempfile.TemporaryDirectory() as tmp:
            stream=NativeStream(tmp,lambda kind,value:observations.append((kind,stream.control_frames(),stream.snapshot()['lidar_state'])),channel_factory=fail)
            stream.stream_id='offline-fault';stream.state['lidar_state']='STREAMING'
            stream.frame,stream.complete_frame=pair()
            stream._run()
        fault=next(row for row in observations if row[0]=='fault')
        self.assertEqual(fault[1:],((None,None),'FAULT'))


if __name__=='__main__':unittest.main()
