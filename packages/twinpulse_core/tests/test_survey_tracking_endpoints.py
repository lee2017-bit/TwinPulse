# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import unittest
from twinpulse_core.cold_start_mission import survey_tracking_endpoints
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.room_localization import compose


class SurveyTrackingEndpointTests(unittest.TestCase):
    def test_original_coordinates_not_occupancy_centers(self):
        views=[{'pose':[.137,-.213,.7],'points':[[.231,.423],[-.321,.519]]}]
        before=repr(views)
        self.assertEqual(survey_tracking_endpoints(views),
                         [compose(views[0]['pose'],[*p,0.])[:2] for p in views[0]['points']])
        self.assertEqual(repr(views),before)

    def test_bounded_uniform_selection_only_from_original_returns(self):
        views=[{'pose':[0.,0.,0.],'points':[[i/10000.,.137] for i in range(20480)]}]
        points=survey_tracking_endpoints(views)
        self.assertEqual(points,views[0]['points'][::2])
        self.assertLessEqual(len(points),18000)

    def test_tracking_reference_is_separate_from_free_space_and_legacy(self):
        endpoints=[[.137+i*.02,.213+math.sin(i)*.1] for i in range(30)]
        cells=[[.05+i*.1,.05] for i in range(30)]
        reference={'schema':'session-survey-map-1.0','endpoint_cells':cells,
                   'tracking_endpoints':endpoints,
                   'tracking_endpoint_basis':'ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED'}
        tracker=CurrentMissionEvidence(reference,{}, {},'revision')
        self.assertAlmostEqual(tracker.bounds[0],endpoints[0][0]-.1)
        self.assertEqual(reference['endpoint_cells'],cells)
        reference['tracking_endpoint_basis']='PHOTO_GEOMETRY'
        with self.assertRaisesRegex(ValueError,'MISSION_TRACKING_ENDPOINT_BASIS_INVALID'):
            CurrentMissionEvidence(reference,{}, {},'revision')
        legacy=CurrentMissionEvidence({'endpoint_cells':cells},{}, {},'revision')
        self.assertAlmostEqual(legacy.bounds[0],-.05)


if __name__=='__main__':unittest.main()
