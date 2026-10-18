# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from unittest.mock import patch
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.navigation_binding import PlanarBinding
from twinpulse_core.observation_stream import ObservationWindow,from_ros_message
from twinpulse_core.ros_observations import RosObservations
from packages.twinpulse_core.tests.test_ros_observations import message


class CurrentEvidenceTests(unittest.TestCase):
    def test_dense_display_is_bounded_without_reducing_grid_or_raw_rays(self):
        from twinpulse_core.automatic_mapping import EvidenceGrid
        from twinpulse_core.local_navigation import LocalPose,LocalScan
        from twinpulse_core.room_localization import compose
        from packages.twinpulse_core.tests.test_room_localization import fixture,scan_points
        reference={'endpoint_cells':scan_points(fixture(),[0.,0.,0.],beam_count=720)}
        context={'project_id':'room','source_revision':'b'*64,'epoch':1}
        photo={'room_from_map':[.1,.2,0.],'report_revision':'d'*64,'status':'ALIGNMENT_CANDIDATE'}
        tracker=CurrentMissionEvidence(reference,photo,context,'c'*64)
        for count in (120,160,161,720):
            with self.subTest(beams=count):
                points=scan_points(fixture(),[0.,0.,0.],beam_count=count)
                scan=LocalScan(tuple(math.hypot(*p) for p in points),20.,'base_link','synthetic_model','synthetic_raycast')
                pose=LocalPose((0.,0.,0.),20.,'test','synthetic_model','synthetic_raycast')
                value=tracker.update(pose,scan,20.)
                self.assertEqual(value['state'],'TRACKING_CANDIDATE',value['match'])
                self.assertTrue(0<len(value['scan_room'])<=160)
                self.assertEqual(len(tracker.capture['points']),count)
                rays=[(value['pose_map'][:2],compose(value['pose_map'],[*p,0.])[:2]) for p in tracker.capture['points']]
                grid=EvidenceGrid();grid.insert(rays,20_000_000_000,context['source_revision'])
                self.assertEqual(value['cells'],grid.rows())
                selected=rays[::max(1,math.ceil(count/160))]
                self.assertEqual(value['scan_room'],[compose(photo['room_from_map'],[*end,0.])[:2] for _,end in selected])
                self.assertFalse(value['motion_authorized']);self.assertFalse(value['physical_demo_ready'])

    def fixture(self):
        context={'project_id':'default','session_id':'synthetic','boot_id':'fake','release_id':'a'*64,'source_revision':'b'*64,'origin':'live_ros'}
        window=ObservationWindow(context);ros=RosObservations()
        for i,kind in enumerate(('odom','scan')):
            msg=message(kind,1_000_000_000)
            if kind=='scan':msg.time_increment=0.;msg.scan_time=.1
            ros.receive(kind,msg,1_020_000_000,20.02,1)
            value=from_ros_message(kind,msg);window.receive(kind,value,i,20_020_000_000,ros_now_ns=1_020_000_000)
        tracker=CurrentMissionEvidence({},None,{'project_id':'default','source_revision':'b'*64,'epoch':1},'c'*64,local_survey=True)
        binding=PlanarBinding('base_footprint','base_scan',(.02,0,0),(.1,0,0),.18,'d'*64)
        return tracker,window,ros.snapshot(20.02),binding
    def test_reviewed_offset_keeps_ray_origins_not_fake_uniform_base_rays(self):
        from twinpulse_core.automatic_mapping import EvidenceGrid
        tracker,window,snapshot,binding=self.fixture();saved=[];original=EvidenceGrid.insert
        def capture(grid,rays,*a):saved.extend(rays);return original(grid,rays,*a)
        with patch.object(EvidenceGrid,'insert',capture):value=tracker.update_window(window,snapshot,binding,20.02)
        self.assertEqual(value['state'],'SESSION_LOCAL_OBSERVED');self.assertFalse(value['motion_authorized'])
        self.assertAlmostEqual(saved[0][0][0],.1);self.assertAlmostEqual(saved[0][0][1],0.)
        self.assertNotEqual(saved[0][0],[0.,0.])
    def test_stamps_sources_frames_and_full_scan_bracketing_not_bypassed(self):
        for fault in ('source','stamp','stale','frame','rolling'):
            tracker,window,snapshot,binding=self.fixture()
            if fault=='source':window.context['source_revision']='e'*64
            if fault=='stamp':window.latest['scan']['data']['stamp_ns']+=1
            if fault=='frame':snapshot['scan']['frame_id']='other'
            if fault=='rolling':window.latest['scan']['data']['time_increment']=.0001
            with self.assertRaises(ValueError):tracker.update_window(window,snapshot,binding,20.5 if fault=='stale' else 20.02)
