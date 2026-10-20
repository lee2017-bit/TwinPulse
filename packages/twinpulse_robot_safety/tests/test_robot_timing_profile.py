# SPDX-License-Identifier: Apache-2.0
"""No-device timing configuration, isolation, real original-clock boundary tests."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from twinpulse_core.robot_timing_profile import DEFAULTS, FIELDS, TimingAccumulator, profile, recommendation, checked_values, digest,runtime_policy
from teleop_contract import InputGate
from fleet_worker import checked_context
from teleop_ros import RosLink


class TimingProfileTests(unittest.TestCase):
    def test_bounds_and_inconsistent_clock_budgets_rejected(self):
        for key,(low,high,_,_) in FIELDS.items():
            for bad in [0,low-1,high+1,float('nan'),True]:
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):checked_values(dict(DEFAULTS,**{key:bad}))
        for edit in [dict(output_timeout_ms=350),dict(input_renewal_ms=200),dict(operator_presence_ms=400)]:
            with self.assertRaises(ValueError):checked_values(dict(DEFAULTS,**edit))

    def test_independent_instances_use_original_source_time(self):
        now=[0.];v=dict(DEFAULTS,input_ttl_ms=500,output_timeout_ms=600,operator_presence_ms=700)
        a=InputGate(lambda:now[0],timing_values=v);b=InputGate(lambda:now[0])
        na,nb=a.challenge(),b.challenge();now[0]=.4
        a.accept(dict(sequence=1,action='forward',challenge=na,age_ms=0))
        self.assertEqual(a.deadline,.5);self.assertEqual(a.source_created,0)
        with self.assertRaisesRegex(ValueError,'INPUT_EXPIRED'):b.accept(dict(sequence=1,action='forward',challenge=nb,age_ms=0))
        a.accept(dict(sequence=2,action='stop',challenge=None,age_ms=0))
        with self.assertRaisesRegex(ValueError,'INPUT_CHALLENGE'):a.accept(dict(sequence=3,action='forward',challenge=na,age_ms=0))

    def test_tail_margin_preserves_loads_invalid_counts_and_unknowns(self):
        probe=TimingAccumulator()
        for i in range(30):
            probe.observe('input_pressure_ms',254.149 if i==29 else 100.,i*.1,'lidar')
            probe.observe('odom_interval_ms',207.091 if i==29 else 100.,i*.1,'lidar')
            probe.observe('sensor_source_ms',108.104 if i==29 else 30.,i*.1,'lidar')
        probe.observe('odom_interval_ms',-1.,3.,'base')
        m=probe.snapshot();r=recommendation(m,'a'*32,'b'*64,'c'*32)
        self.assertEqual(r['profile']['values']['input_ttl_ms'],350)
        self.assertEqual(r['profile']['values']['odom_interval_ms'],300)
        self.assertEqual(r['profile']['values']['sensor_source_ms'],200)
        self.assertEqual(r['profile']['values']['output_timeout_ms'],450)
        self.assertEqual(r['coverage'],'PROVISIONAL');self.assertEqual(m['metrics']['base:odom_interval_ms']['invalid'],1)
        self.assertEqual(r['reasons']['wheel_interval_ms']['reason'],'NOT_MEASURED_PRESET_RETAINED')
        self.assertFalse(r['profile']['adaptive'])

    def test_context_policy_identity_bound_before_transport(self):
        context=dict(schema='physical-live-start-1.0',operation_id='c'*32,robot_id='a'*32,project_id='chat',connection_epoch='d'*32,
            binding_sha256='b'*64,worker_sha256='e'*64)
        p=profile('a'*32,'b'*64);context.update(timing_profile=p,timing_profile_sha256=digest(p))
        self.assertEqual(checked_context(context),context)
        context['timing_profile']['values']['input_ttl_ms']=300
        with self.assertRaisesRegex(ValueError,'START_TIMING_DIGEST'):checked_context(context)

    def test_no_automatic_motion_or_braking_claim(self):
        p=profile('a'*32,'b'*64)
        self.assertEqual(p['mode'],'unmeasured');self.assertIsNone(p['evidence'])
        self.assertIn('NOT_BRAKING',p['qualification'])
        actual=runtime_policy(dict(DEFAULTS,output_timeout_ms=450,wheel_interval_ms=225))
        self.assertEqual(actual['limits']['cpp_output_guard']['seconds'],.45)
        self.assertEqual(actual['limits']['wheel_sample_interval']['seconds'],.225)

    def test_sensor_and_guard_freshness_use_their_own_pinned_limits(self):
        link=RosLink.__new__(RosLink);link.timing_values=dict(DEFAULTS,sensor_source_ms=300,sensor_receipt_ms=300)
        link.sensor=S(header=S(stamp=S(sec=10,nanosec=0)),battery=11.8,button=0)
        link.sensor_t=10.;link.guard_t=10.24
        link.node=S(get_clock=lambda:S(now=lambda:S(nanoseconds=10_250_000_000)),count_publishers=lambda t:0 if t=='cmd_vel' else 1)
        link.pub=S(get_subscription_count=lambda:1)
        with patch('teleop_ros.time.monotonic',return_value=10.25):link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'CURRENT')
        link.guard_t=10.
        with patch('teleop_ros.time.monotonic',return_value=10.25),self.assertRaisesRegex(ValueError,'TELEMETRY_STALE'):link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'GUARD_RECEIPT_STALE')

if __name__=='__main__':unittest.main()
