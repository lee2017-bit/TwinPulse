# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Idle native sampling safety; existing ROS windows, no physical devices."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from twinpulse_core.current_mission_evidence import IdleCurrentEvidence
from packages.twinpulse_core.tests.test_current_mission_evidence import CurrentEvidenceTests


class IdleCurrentTests(unittest.TestCase):
    def test_native_factory_samples_new_observations_without_motor_enable(self):
        from pathlib import Path
        import sys,time
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/twinpulse_robot_safety'))
        from observed_runtime import RobotObservedFactory
        from tests.fixtures.observed_robot_process import ObservedLink
        from twinpulse_core.navigation_binding import PlanarBinding
        from packages.twinpulse_core.tests.test_room_localization import scan_points
        context={'project_id':'idle_room','session_id':'offline-idle','boot_id':'fake-boot',
            'release_id':'c'*64,'source_revision':'c'*64,'origin':'live_ros'}
        vertices=[[-2.,-2.],[2.,-2.],[2.,1.],[-1.,1.],[-1.,2.],[-2.,2.]]
        outline={'segments':[[vertices[i],vertices[(i+1)%len(vertices)]] for i in range(len(vertices))]}
        reference={'revision':'a'*64,'endpoint_cells':scan_points(outline,[0.,0.,0.],beam_count=480)}
        scope={'schema':'observed-mission-scope-1.0','project_id':'idle_room',
            'goal':{'mode':'NAVIGATE_TWIN_GOAL','xy':[.1,-.6],'room_revision':'b'*64,'duration_s':45.},
            'reference':reference,'alignment':{'status':'ALIGNMENT_CANDIDATE',
                'room_from_map':[0.,0.,0.],'report_revision':'d'*64}}
        link=ObservedLink(context,world={'vertices':vertices,'start':[-.1,-.6,.1]})
        request={'adaptive_scope':scope,'binding':PlanarBinding('base_footprint','base_scan',
            (.02,0.,0.),(.1,0.,0.),.18,'e'*64),'mission_id':'f'*32,'request_sha256':'a'*64}
        output=[];factory=RobotObservedFactory(link,request,output=output.append,clock=time.monotonic)
        factory.prepare()
        # New callback receipts, same checked source; no old report-pose input.
        link.spin(.01);value=factory.preview_current()
        self.assertEqual(value['state'],'TRACKING_CANDIDATE');self.assertFalse(link.enabled)
        self.assertLess(time.monotonic()-value['sample_s'],.2)
        self.assertTrue(value['cells']);self.assertFalse(value['motion_authorized'])
        self.assertFalse(any(e.get('linear_m_s',0) or e.get('angular_rad_s',0) for e in link.events))
        link.enabled=True
        with self.assertRaisesRegex(ValueError,'WHEELS_NOT_DISABLED'):factory.preview_current()
        self.assertIsNone(factory.idle_evidence.last)

    def test_idle_handoff_drops_preview_and_cannot_mutate_active_matching_seed(self):
        sampler,tracker,_,_=self.fixture();tracker.transform=[1.,2.,3.]
        sampler.last={'pose_map':[1.,2.,3.]};sampler.handoff()
        with self.assertRaisesRegex(ValueError,'CLOSED'):sampler.sample()
        self.assertEqual(tracker.transform,[1.,2.,3.]);self.assertIsNone(sampler.last)
        sampler.close();self.assertIsNone(tracker.transform)

    def fixture(self):
        tracker,window,snapshot,binding=CurrentEvidenceTests().fixture()
        self.t=20.02;self.off=True
        sampler=IdleCurrentEvidence(tracker,window,binding,snapshot=lambda:deepcopy(snapshot),
            disabled=lambda:self.off,clock=lambda:self.t)
        return sampler,tracker,window,snapshot

    def test_actual_window_rejected_without_alignment_and_no_prior_pose_retained(self):
        sampler,tracker,_,_=self.fixture()
        with self.assertRaisesRegex(ValueError,'SESSION_LOCAL_OBSERVED'):sampler.sample()
        self.assertIsNone(sampler.last);self.assertIsNone(tracker.transform)
        self.assertFalse(self.off is False)

    def test_processing_clock_age_disabled_and_close_are_rechecked(self):
        for fault in ('slow','backwards','enabled','source','lost','error','closed'):
            with self.subTest(fault=fault):
                sampler,tracker,window,_=self.fixture()
                def sample(*args):
                    tracker.transform=[1.,2.,3.]
                    if fault=='slow':self.t+=.21
                    if fault=='backwards':self.t-=.001
                    if fault=='enabled':self.off=False
                    if fault=='source':window.context['source_revision']='f'*64
                    if fault=='error':raise ValueError('SOURCE_MISSING')
                    return {'state':'LOST' if fault=='lost' else 'TRACKING_CANDIDATE','sample_s':20.02,
                            'pose_map':[1.,2.,3.],'cells':[]}
                if fault=='closed':sampler.close()
                with patch.object(tracker,'update_window',side_effect=sample):
                    with self.assertRaises(ValueError):sampler.sample()
                self.assertIsNone(sampler.last);self.assertIsNone(tracker.transform)

    def test_qualified_fixture_keeps_source_age_not_processing_entry_stamp(self):
        sampler,tracker,_,snapshot=self.fixture();snapshot['scan']['sample_s']=20.
        value={'state':'TRACKING_CANDIDATE','sample_s':20.02,'pose_map':[0.,0.,0.],
               'cells':[],'motion_authorized':False,'physical_demo_ready':False}
        with patch.object(tracker,'update_window',return_value=value):result=sampler.sample()
        self.assertEqual(result['sample_s'],20.);self.assertFalse(result['motion_authorized'])
        result['pose_map'][0]=9.;self.assertEqual(sampler.last['pose_map'][0],0.)
        sampler.close();self.assertIsNone(sampler.last)
