# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free policy tests. Synthetic traces never authorize a real robot."""
import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'twinpulse_core/src'))
from stop_policy import assess_stop, MM_PER_TICK, POLICY_SHA256
from stop_policy import assess_field_stop,field_stop_policy,POLICY
from twinpulse_core.robot_timing_profile import values_of


def trace(fn=lambda t:0):
    return [{'t':round(i*.05,6),'encoders':[round(fn(i*.05)),round(fn(i*.05))],
             'source_age_s':.005,'torque':True} for i in range(18,38)]


class PolicyTests(unittest.TestCase):
    def assess(self,rows):return assess_stop(rows,1.,.6)

    def test_stops_late_in_deceleration_budget_then_observed_separately(self):
        rows=trace(lambda t:min(max(0,t-1)*100,41))
        result=self.assess(rows)
        self.assertEqual(result['status'],'PASS')
        self.assertGreaterEqual(result['metrics']['verification_observed_ms'],299.999)
        self.assertEqual(result['policy_sha256'],POLICY_SHA256)
        self.assertEqual(result['chassis_stop'],'NOT_MEASURED')

    def test_small_jitter_passes_but_slow_drift_does_not(self):
        self.assertEqual(self.assess(trace(lambda t:round(t*20)%2))['status'],'PASS')
        result=self.assess(trace(lambda t:max(0,t-1)*40))
        self.assertEqual(result['reason'],'RESIDUAL_MOTION_EXCEEDED')

    def test_reverse_cannot_cancel_wheel_travel(self):
        rows=trace(lambda t:300*max(0,1-abs(t-1.2)/.2))
        result=self.assess(rows)
        self.assertEqual(result['reason'],'STOP_TRAVEL_EXCEEDED')
        self.assertGreater(result['metrics']['wheel_travel_mm'][0],20)

    def test_oscillation_cannot_cancel_residual_span(self):
        result=self.assess(trace(lambda t:20 if 1.55<=t<=1.65 else 0))
        self.assertEqual(result['reason'],'RESIDUAL_MOTION_EXCEEDED')

    def test_single_bad_wheel_fails(self):
        rows=trace()
        for r in rows:r['encoders'][1]=round(max(0,r['t']-1)*40)
        self.assertEqual(self.assess(rows)['status'],'FAIL')

    def test_late_cutoff_fails_without_using_good_motion_samples(self):
        self.assertEqual(assess_stop(trace(),1.,.2)['reason'],'COMMAND_CUTOFF_LATE')

    def test_old_short_recording_not_relabelled_pass(self):
        self.assertEqual(self.assess(trace()[:14])['status'],'INCOMPLETE')

    def test_off_samples_cannot_complete_torque_on_observation(self):
        rows=trace()
        for r in rows:
            if r['t']>1.55:r['torque']=False
        self.assertEqual(self.assess(rows)['reason'],'OBSERVATION_INTERRUPTED_BY_TORQUE_OFF')

    def test_stale_gaps_duplicates_and_invalid_data_are_not_stability(self):
        cases=[]
        rows=trace();rows[7]['source_age_s']=.3;cases.append(rows)
        rows=trace();del rows[7:10];cases.append(rows)
        rows=trace();rows[7]['t']=rows[6]['t'];cases.append(rows)
        rows=trace();rows[7]['encoders']=[0];cases.append(rows)
        rows=trace();rows[7]['encoders']=[True,0];cases.append(rows)
        rows=trace();rows[7]['t']=float('nan');cases.append(rows)
        rows=trace();rows[7]['source_age_s']=None;cases.append(rows)
        for value in cases:
            with self.subTest(value=value):self.assertEqual(self.assess(value)['status'],'INCOMPLETE')

    def test_residual_limit_is_physical_units_not_sliding_anchor(self):
        self.assertAlmostEqual(MM_PER_TICK,.050621366,places=9)
        # 5 counts = .253mm < .300mm, 6 counts = .304mm > .300mm.
        for ticks,status in ((5,'PASS'),(6,'FAIL')):
            rows=trace(lambda t:ticks if t>=1.7 else 0)
            self.assertEqual(self.assess(rows)['status'],status)

    def test_separate_field_coverage_uses_pinned_wheel_setting_without_rewriting_strict(self):
        values=values_of();values['wheel_interval_ms']=225
        rows=trace();del rows[8:10]
        self.assertEqual(self.assess(rows)['reason'],'SENSOR_COVERAGE_INVALID')
        result=assess_field_stop(rows,1.,.6,values)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['limits']['max_sample_gap_s'],.225)
        self.assertEqual(result['policy_id'],'supervised-field-stop-coverage-1.0')
        self.assertNotEqual(result['policy_sha256'],POLICY_SHA256)
        self.assertEqual(POLICY['max_sample_gap_s'],.1)
        self.assertEqual(self.assess(trace())['policy_sha256'],POLICY_SHA256)
        self.assertEqual(result['chassis_stop'],'NOT_MEASURED')
        for key in POLICY.keys()-{'id','max_sample_gap_s','scope'}:
            self.assertEqual(result['limits'][key],POLICY[key])

    def test_field_coverage_keeps_original_negative_cases_and_selected_setting(self):
        values=values_of();values['wheel_interval_ms']=225
        cases=[]
        rows=trace();del rows[6:11];cases.append(rows)
        rows=trace();rows[8]['source_age_s']=.2;cases.append(rows)
        rows=trace();rows[-2]['torque']=False;cases.append(rows)
        cases.append(trace()[:14]);cases.append(trace(lambda t:300*max(0,1-abs(t-1.2)/.2)))
        cases.append(trace(lambda t:20 if 1.55<=t<=1.65 else 0))
        for rows in cases:
            with self.subTest(rows=rows):self.assertNotEqual(assess_field_stop(rows,1.,.6,values)['status'],'PASS')
        short=dict(values,wheel_interval_ms=100);rows=trace();del rows[8:10]
        self.assertEqual(assess_field_stop(rows,1.,.6,short)['reason'],'SENSOR_COVERAGE_INVALID')
        with self.assertRaisesRegex(ValueError,'FIELD_STOP_SAMPLE_GAP_EXCEEDS_VERIFICATION_WINDOW'):
            field_stop_policy(dict(values,wheel_interval_ms=1000))


if __name__=='__main__':unittest.main()
