# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current localization field sampling, not physical calibration evidence."""
import math
import unittest
from twinpulse_core.automatic_mapping import local_match
from twinpulse_core.sensor_map_localization import EndpointMatcher
from twinpulse_core.room_localization import RoomMatcher


class EndpointFieldScoreTests(unittest.TestCase):
    def matcher(self, *, interpolate):
        # Exact small field makes interpolation independently checkable.
        # No match/pose/arrival outcome is injected into a mission.
        value=EndpointMatcher.__new__(EndpointMatcher)
        value.x0=value.y0=0.;value.cell=.06;value.nx=value.ny=2
        value.field=[0.,.06,.12,.18];value.interpolate=interpolate
        return value

    def test_continuous_current_field_and_legacy_default_are_distinct(self):
        current=self.matcher(interpolate=True);legacy=self.matcher(interpolate=False)
        for x,y,expected in ((0.,0.,0.),(.015,.015,.045),(.03,.03,.09),(.06,.06,.18)):
            error,hits=current.score([[x,y]],[0.,0.,0.])
            self.assertAlmostEqual(error,expected)
            self.assertEqual(hits,float(expected<=.15))
        self.assertEqual(legacy.score([[.015,.015]],[0.,0.,0.]),(0.,1.))
        # A nearest-cell seam used to turn tiny displacement into a full-cell
        # score jump. Both sides now use the same original field corners.
        a=current.score([[.03-1e-6,.01]],[0.,0.,0.])[0]
        b=current.score([[.03+1e-6,.01]],[0.,0.,0.])[0]
        self.assertAlmostEqual(b-a,2e-6)
        self.assertAlmostEqual(legacy.score([[.03+1e-6,.01]],[0.,0.,0.])[0]
            -legacy.score([[.03-1e-6,.01]],[0.,0.,0.])[0],.06)

    def test_current_score_still_counts_every_return_caps_and_rejects_outside_field(self):
        current=self.matcher(interpolate=True)
        error,hits=current.score([[0.,0.],[.06,.06],[-.001,0.],[.061,.06]],[0.,0.,0.])
        self.assertAlmostEqual(error,(0.+.18+.5+.5)/4)
        self.assertEqual(hits,.25)
        # Actual field nodes remain exactly original distances, not fitted
        # endpoints or fabricated free-space evidence.
        for i,value in enumerate(current.field):
            self.assertAlmostEqual(current.score([[(i%2)*.06,(i//2)*.06]],[0.,0.,0.])[0],value)

    def test_actual_field_build_and_legacy_scores_are_unchanged(self):
        reference={'endpoint_cells':[[i*.02,0.] for i in range(24)],'bounds_m':[0.,.46,-.1,.1]}
        legacy=EndpointMatcher(reference);current=EndpointMatcher(reference,interpolate=True)
        self.assertFalse(legacy.interpolate);self.assertTrue(current.interpolate)
        self.assertEqual(current.field,legacy.field)
        self.assertEqual((current.cell,current.nx,current.ny),(legacy.cell,legacy.nx,legacy.ny))
        for pose in ([0.,0.,0.],[.01,.02,.1],[2.,2.,0.]):
            self.assertEqual(legacy.score(reference['endpoint_cells'],pose),
                RoomMatcher.score(legacy,reference['endpoint_cells'],pose))
        for bad in ('yes',1,None):
            with self.assertRaisesRegex(ValueError,'SENSOR_MAP_FIELD_SAMPLING_INVALID'):
                EndpointMatcher(reference,interpolate=bad)

    def test_subcell_search_improves_resolution_without_weakening_original_gates(self):
        # Independently defined analytic cost checks the optimizer itself, not
        # a fabricated match/pose/success supplied to an application mission.
        points=[[math.cos(i*math.tau/32),math.sin(i*math.tau/32)] for i in range(32)]
        class AnalyticField:
            def __init__(self,target=(.037,-.029,.021),offset=0.,hits=1.,flat=False):
                self.target=target;self.offset=offset;self.hits=hits;self.flat=flat
            def possible(self,pose):return all(abs(p)<=1 for p in pose)
            def score(self,points,pose):
                count=2 if self.flat else 3
                return self.offset+sum((pose[i]-self.target[i])**2 for i in range(count)),self.hits
        field=AnalyticField();legacy=local_match(field,points,[0.,0.,0.])
        current=local_match(field,points,[0.,0.,0.],refine_subcell=True)
        self.assertEqual(legacy['status'],'TRACKING_CANDIDATE')
        self.assertEqual(current['status'],'TRACKING_CANDIDATE')
        self.assertLess(current['mean_error_m'],legacy['mean_error_m'])
        self.assertLess(math.dist(current['pose'],field.target),.003)
        self.assertNotIn('current_refinement_step_m',legacy)
        self.assertEqual(current['current_refinement_step_m'],.003125)
        for field,expected in ((AnalyticField(offset=.2),'LOST'),(AnalyticField(hits=.69),'LOST'),
                (AnalyticField(flat=True),'AMBIGUOUS'),(AnalyticField(target=(.35,.35,.3)),'INNOVATION_REJECTED')):
            self.assertEqual(local_match(field,points,[0.,0.,0.],refine_subcell=True)['status'],expected)
        with self.assertRaisesRegex(ValueError,'LOCAL_MATCH_REFINEMENT_INVALID'):
            local_match(AnalyticField(),points,[0.,0.,0.],refine_subcell='yes')


if __name__=='__main__':unittest.main()
