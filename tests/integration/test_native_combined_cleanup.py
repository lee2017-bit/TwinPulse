# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Original native fault plus failing ROS halt: no real devices or clock waits."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from packages.twinpulse_robot_safety.tests import mission_test as fixture
from tests.fixtures.combined_fault_evidence import save


class CombinedCleanupTests(unittest.TestCase):
    def run_combined(self,fault):
        original=fixture.RosLink.navigation_step
        observations=[]
        def step(link,*args,**kwargs):
            if not getattr(link,'combined_cleanup_test',False):
                halt=link.halt
                def failed_halt():
                    halt();raise ValueError('STOP_READBACK_UNCONFIRMED')
                link.halt=failed_halt;link.combined_cleanup_test=True
            # The stale-sensor fixture deliberately stops updating rows. Use
            # its current clock, not the last row's historical receipt time,
            # so diagnostic sampling cannot create a backwards-clock fault.
            from teleop_ros import time as robot_time
            observations.append(deepcopy(link.navigation.snapshot(robot_time.monotonic())))
            return original(link,*args,**kwargs)
        with patch.object(fixture.RosLink,'navigation_step',step):
            result=fixture.MissionTests().run_fixture(fault=fault)
        status,error,sent,events,*_=result
        save('native-'+(fault or 'halt-only').replace('_','-'),{'result':status,'primary_cause':str(error),
            'native_cleanup_errors':getattr(error,'mission_cleanup_errors',[]),
            'published_commands':sent,'events':events,'observations':observations,
            'clock_policy':'EXPLICIT_ACCELERATED_TEST_CLOCK_NOT_SOAK',
            'raw_basis':'GENERATED_NATIVE_ODOM_SCAN_SNAPSHOTS_NOT_PHYSICAL_ROSBAG'})
        return result

    def test_disconnect_and_failed_halt_keep_original_reason(self):
        _,error,*_=self.run_combined('disconnect')
        self.assertEqual(str(error),'INPUT_CLOSED_OR_OVERFLOW')
        self.assertEqual(error.mission_cleanup_errors[0]['code'],'STOP_READBACK_UNCONFIRMED')
        self.assertEqual(error.mission_cleanup_errors[0]['stage'],'mission_halt')

    def test_sensor_obstacle_input_expiry_disk_and_deadline_with_failed_halt(self):
        for fault,code in [('lost_heartbeat','INPUT_DEADLINE_EXPIRED'),('stale_scan','NAVIGATION_OBSERVATION_MISSING'),
                           ('obstacle','OBSTACLE_IN_SWEPT_ENVELOPE'),('journal_failed','JOURNAL_WRITE_FAILED'),
                           ('deadline','MISSION_EXPIRED')]:
            with self.subTest(fault=fault):
                result,error,sent,events,*_=self.run_combined(fault)
                self.assertIsNone(result);self.assertEqual(str(error),code)
                self.assertTrue(error.mission_cleanup_errors)
                self.assertTrue(all(row['code']=='STOP_READBACK_UNCONFIRMED' for row in error.mission_cleanup_errors))
                self.assertFalse(any(e['kind']=='mission_finished' and e['data']['status']=='MISSION_ARRIVED' for e in events))

    def test_halt_only_failure_is_not_logged_as_success_and_stop_force_do_not_resume(self):
        for fault in (None,'finish_stop','force_stop'):
            with self.subTest(fault=fault):
                result,error,sent,events,*_=self.run_combined(fault)
                self.assertIsNone(result);self.assertEqual(str(error),'STOP_READBACK_UNCONFIRMED')
                finished=[e['data']['status'] for e in events if e['kind']=='mission_finished']
                self.assertEqual(finished,['FAILED'])

    def test_cleanup_details_are_bounded_and_do_not_copy_arbitrary_exception_text(self):
        from twinpulse_core.cleanup_diagnostics import retain_cleanup,checked_notes
        primary=ValueError('INPUT_DEADLINE_EXPIRED')
        for _ in range(20):retain_cleanup(primary,'mission_halt',OSError('SECRET_CANARY private/path'))
        self.assertEqual(str(primary),'INPUT_DEADLINE_EXPIRED');self.assertEqual(len(primary.mission_cleanup_errors),8)
        self.assertTrue(all(r['code']=='NATIVE_CLEANUP_FAILED' for r in primary.mission_cleanup_errors))
        self.assertEqual(checked_notes(primary.mission_cleanup_errors),primary.mission_cleanup_errors)
        self.assertEqual(checked_notes([{'stage':'mission_halt','code':'BAD','error_type':'Error','authorized':True}]),[])
        for stage in ([],{},None,12):
            self.assertEqual(checked_notes([{'stage':stage,'code':'BAD','error_type':'Error'}]),[])

    def test_fixed_worker_report_keeps_primary_native_and_independent_off_failures(self):
        from packages.twinpulse_robot_safety.tests import teleop_test
        from twinpulse_core.cleanup_diagnostics import retain_cleanup
        primary=ValueError('INPUT_DEADLINE_EXPIRED')
        retain_cleanup(primary,'mission_halt',ValueError('STOP_READBACK_UNCONFIRMED'))
        report,events,_=teleop_test.LifecycleTests().exercise('mission',qualified=True,
            mission_failure=primary,ros_stop_ok=False,off_final_ok=False)
        self.assertEqual(report['first_failure']['code'],'INPUT_DEADLINE_EXPIRED')
        self.assertEqual(report['reason'],'INPUT_DEADLINE_EXPIRED')
        self.assertEqual(report['status'],'FINAL_IDLE_UNCONFIRMED')
        codes={row['code'] for row in report['cleanup_errors']}
        self.assertTrue({'STOP_READBACK_UNCONFIRMED','ROS_STOP_FAILED','FINAL_IDLE_UNCONFIRMED'}<=codes)
        self.assertFalse(report['cleanup_confirmed']);self.assertIn('base_reaped',events)
        self.assertIn('off',events)
        save('worker-independent-off',{'report':report,'lifecycle_events':events,
            'basis':'DEVICE_INTERFACES_MOCKED_FIXED_WORKER_MAIN'})


if __name__=='__main__':unittest.main()
