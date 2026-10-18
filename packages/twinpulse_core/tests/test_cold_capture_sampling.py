# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Derived fit views stay bounded; current rays/grid keep their original data."""
import math
import unittest
from twinpulse_core.adaptive_mission_contract import nominal_room
from twinpulse_core.automatic_mapping import EvidenceGrid
from twinpulse_core.cold_start_mission import ColdStartMission
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.local_navigation import LocalPose,LocalScan
from twinpulse_core.room_localization import compose
from packages.twinpulse_core.tests.test_automatic_photo_alignment import room
from packages.twinpulse_core.tests.test_room_localization import scan_points


class ColdCaptureSamplingTests(unittest.TestCase):
    def test_full_capture_and_grid_survive_uniform_fit_selection(self):
        outline,objects=room();context={'project_id':'room','source_revision':'b'*64,'epoch':1}
        tracker=CurrentMissionEvidence({},None,context,'c'*64,local_survey=True)
        scans=[]
        def current(value,pose,now):return value.update(pose,scans[-1],now)
        goal={'mode':'SURVEY_THEN_NAVIGATE','xy':[.1,0.],'room_revision':'c'*64,'duration_s':45.}
        mission=ColdStartMission(goal,20.,tracker=tracker,current=current,nominal=nominal_room(objects,.182,'c'*64),
            provenance='synthetic_raycast',frame_id='synthetic_room',context=context)
        expected=EvidenceGrid()
        for count,x,t in ((720,0.,20.),(161,.05,20.05),(120,.10,20.10)):
            points=scan_points(outline,[x,0.,0.],beam_count=count)
            scans.append(LocalScan(tuple(math.hypot(*p) for p in points),t,'base_link','synthetic_model','synthetic_raycast'))
            pose=LocalPose((x,0.,0.),t,'synthetic_room','synthetic_model','synthetic_raycast')
            mission._current(pose,t);capture=tracker.capture;view=mission.views[-1]
            step=max(1,math.ceil(count/160))
            self.assertEqual(len(capture['points']),count)
            self.assertEqual(view['points'],capture['points'][::step])
            self.assertEqual(view['origins'],capture['origins'][::step])
            self.assertEqual(view['stamp_ns'],capture['stamp_ns']);self.assertEqual(view['sequence'],capture['sequence'])
            self.assertTrue(0<len(view['points'])<=160)
            expected.insert([(compose(capture['pose'],[*a,0.])[:2],compose(capture['pose'],[*b,0.])[:2])
                for a,b in zip(capture['origins'],capture['points'])],capture['stamp_ns'],context['source_revision'])
            self.assertEqual(mission.grid.rows(),expected.rows())
        self.assertEqual(len(mission.views),3);mission.close()


if __name__=='__main__':unittest.main()
