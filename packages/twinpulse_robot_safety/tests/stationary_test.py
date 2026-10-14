# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure/fake-process tests. No ROS import, network or serial access."""
import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'twinpulse_core' / 'src'))
import stationary as s
import ros_preflight
from stationary_observer import IdleWatch, PassiveEvidence
from trial_session import Binding, TrialSession


def board():
    return {'status': 'OBSERVED', 'torque_enabled': False, 'wheel_velocity_raw': [0, 0],
            'command_bytes_zero': True, 'near_board_protection': False, 'encoders': [100, 200]}


def message(stamp=9_950_000_000):
    """Self-contained fake odometry for the robot's source-only CTest bundle."""
    return NS(header=NS(frame_id='odom', stamp=NS(sec=stamp // 10**9, nanosec=stamp % 10**9)),
              child_frame_id='base_footprint',
              pose=NS(pose=NS(position=NS(x=.1, y=.2, z=0.),
                              orientation=NS(x=0., y=0., z=0., w=1.))))


class StationaryTests(unittest.TestCase):
    def test_error_excerpt_is_bounded_and_redacts_sensitive_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'base.log'
            path.write_text('ordinary startup\nERROR invalid ROS parameter namespace\n'
                            'Authorization token failed: do not export\n'
                            'Exception: serial port unavailable\n')
            value=s.bounded_error_lines(path)
        self.assertEqual(value['status'],'RECORDED')
        self.assertIn('ERROR invalid ROS parameter namespace',value['lines'])
        self.assertIn('[REDACTED]',value['lines'])
        self.assertNotIn('do not export',repr(value))

    def test_precheck_rejects_before_start(self):
        for field, value in [('status', 'UNKNOWN'), ('torque_enabled', True),
                             ('command_bytes_zero', False), ('wheel_velocity_raw', [1, 0]),
                             ('near_board_protection', True)]:
            with self.subTest(field=field):
                data = board(); data[field] = value
                with patch.object(s.subprocess, 'Popen') as start:
                    result = s.lifecycle(lambda: data, start, lambda _: {}, board)
                    self.assertEqual(result['status'], 'FAILED')
                    start.assert_not_called()

    def test_success_order_and_failure_cleanup(self):
        for failure in [None, ValueError('telemetry stale'), KeyboardInterrupt()]:
            order = []
            def observe(_):
                order.append('observe')
                if failure is not None:
                    raise failure
                return {'status': 'STATIONARY_OBSERVED'}
            def stop(_):
                order.append('reaped')
                return {'exit_code': 0, 'escalation': 'interrupt'}
            def post():
                order.append('read_after'); return board()
            with patch.object(s, 'stop_child', side_effect=stop):
                result = s.lifecycle(board, lambda: object(), observe, post)
            self.assertEqual(order, ['observe', 'reaped', 'read_after'])
            self.assertEqual(result['status'], 'STATIONARY_CHECK_PASS' if failure is None else
                             'INTERRUPTED' if isinstance(failure, KeyboardInterrupt) else 'FAILED')
            self.assertFalse(result['motion_authorized'])

    def test_unreaped_child_prevents_independent_read(self):
        with patch.object(s, 'stop_child', side_effect=RuntimeError('still alive')), \
             patch.object(s, 'require_idle') as idle:
            result = s.lifecycle(board, lambda: object(), lambda _: {'status': 'STATIONARY_OBSERVED'},
                                 lambda: self.fail('serial read before process exit'))
        self.assertEqual(result['status'], 'CLEANUP_UNCONFIRMED')
        self.assertEqual(idle.call_count, 1)

    def test_post_movement_or_missing_state_is_not_pass(self):
        for after in [dict(board(), encoders=[110, 200]), dict(board(), status='UNKNOWN')]:
            with patch.object(s, 'stop_child', return_value={'exit_code': 0, 'escalation': 'interrupt'}):
                result = s.lifecycle(board, lambda: object(), lambda _: {'status': 'STATIONARY_OBSERVED'}, lambda: after)
            self.assertEqual(result['status'], 'FINAL_IDLE_UNCONFIRMED')

    def watch(self):
        watch = IdleWatch()
        for i in range(10):
            watch.sensor(1, [100, 200], False, 12, 0, .01)
        watch.status(1, 'explicit_stop')
        return watch

    def test_observer_accepts_only_fresh_disarmed_no_publisher(self):
        watch = self.watch()
        watch.verify(1.1, 0)
        with self.assertRaises(ValueError): watch.verify(1.1, 0, sensor_publishers=2)
        with self.assertRaises(ValueError): watch.verify(1.1, 0, guard_publishers=0)
        for now, count in [(1.3, 0), (1.1, 1)]:
            with self.assertRaises(ValueError): watch.verify(now, count)
        watch.status(1.1, 'active')
        with self.assertRaises(ValueError): watch.verify(1.15, 0)

    def test_observer_sensor_faults_latch(self):
        for enc, torque, volts, button, age in [([103, 200], False, 12, 0, .01),
                                              ([100, 200], True, 12, 0, .01),
                                              ([100, 200], False, 11.0, 0, .01),
                                              ([100, 200], False, float('nan'), 0, .01),
                                              ([100, 200], False, 12, 1, .01),
                                              ([100, 200], False, 12, 0, -.01),
                                              ([100, 200], False, 12, 0, .3)]:
            watch = self.watch()
            watch.sensor(1.1, enc, torque, volts, button, age)
            watch.sensor(1.11, [100, 200], False, 12, 0, .01)
            with self.assertRaises(ValueError): watch.verify(1.15, 0)

    def test_observer_never_publishes_or_calls_services(self):
        tree = ast.parse(Path(s.__file__).with_name('stationary_observer.py').read_text())
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn('create_publisher', calls)
        self.assertNotIn('create_client', calls)
        source = Path(s.__file__).with_name('stationary_observer.py').read_text()
        for topic in ("'odom'", "'scan'", "'/tf'", "'/tf_static'"):
            self.assertIn(topic, source)
        self.assertIn('passive_ros=passive.report()', source)

    def test_base_topics_namespaced_but_vendor_odometry_frames_unprefixed(self):
        script = Path(s.__file__).with_name('stationary.sh').read_text()
        vendor_path = (Path(s.__file__).resolve().parents[2] / 'artifacts/robot-models/turtlebot3-source'
                       / 'turtlebot3_node/src/odometry.cpp')
        self.assertIn('-r __ns:=/tp_guard_stationary', script)
        self.assertIn("-p 'namespace:=\"\"'", script)
        self.assertIn("'namespace:=\"\"'", Path(ros_preflight.__file__).read_text())
        self.assertNotIn('-p namespace:=/tp_guard_stationary', script)
        if vendor_path.is_file():
            vendor = vendor_path.read_text()
            self.assertIn('frame_id_of_odometry_ = name_space_ + "/" + frame_id_of_odometry_', vendor)
            self.assertIn('child_frame_id_of_odometry_ = name_space_ + "/" + child_frame_id_of_odometry_', vendor)

    def test_ros_argument_preflight_has_no_publishers_or_device_calls(self):
        from types import SimpleNamespace as NS
        calls=[]
        class FakeNode:
            def get_namespace(self):return '/tp_guard_stationary'
            def declare_parameter(self, name):
                self.name=name
                return NS(value='')
            def destroy_node(self):calls.append('destroy')
        fake=NS(init=lambda args:calls.append(('init',args)),
                create_node=lambda name:FakeNode(), shutdown=lambda:calls.append('shutdown'))
        result=ros_preflight.check(fake)
        self.assertEqual(result['status'],'ROS_ARGUMENTS_VERIFIED')
        self.assertFalse(result['motion_authorized'])
        self.assertEqual(calls[-2:],['destroy','shutdown'])
        self.assertEqual(calls[0][1][-1],'namespace:=""')
        text=Path(ros_preflight.__file__).read_text()
        for forbidden in ('create_publisher','create_client','serial.Serial','/dev/tty'):
            self.assertNotIn(forbidden,text)

    def test_passive_capture_keeps_bounded_invalid_odom_and_no_motion_authority(self):
        evidence = PassiveEvidence()
        invalid = message();invalid.pose.pose.orientation.w = .5
        evidence.message('odom', invalid, 10**10, 20., 1)
        evidence.message('odom', message(stamp=9_960_000_000), 10_010_000_000, 20.01, 1)
        for n in range(8):
            evidence.message('odom', message(stamp=9_970_000_000+n*10_000_000),
                             10_020_000_000+n*10_000_000, 20.02+n*.01, 1)
        transform = NS(header=NS(frame_id='odom', stamp=NS(sec=9,nanosec=950_000_000)),
                       child_frame_id='base_footprint',
                       transform=NS(translation=NS(x=0.,y=0.,z=0.),
                                    rotation=NS(x=0.,y=0.,z=0.,w=1.)))
        evidence.tf_message(NS(transforms=[transform]*10))
        report = evidence.report()
        self.assertEqual(report['counts'], {'odom':10,'scan':0,'tf':10,'tf_static':0})
        self.assertEqual(report['status'], {'odom':'SAMPLES_ACCEPTED_UNALIGNED','scan':'NOT_RECEIVED'})
        self.assertEqual(report['tf_status'],'RECEIVED_UNVALIDATED')
        self.assertEqual(report['fault_counts']['odom']['ODOM_ORIENTATION'],1)
        self.assertEqual(report['fault_counts']['odom']['NONE'],9)
        self.assertEqual(report['first']['odom'][0]['quaternion_xyzw'][-1],.5)
        self.assertEqual(len(report['first']['odom']),3)
        self.assertEqual(len(report['tf_first']),1)
        self.assertEqual(report['tf_first'][0]['quaternion_xyzw'],[0.,0.,0.,1.])
        self.assertEqual(report['examples_by_fault']['odom']['ODOM_ORIENTATION']['quaternion_xyzw'][-1],.5)
        self.assertIsNone(report['latest']['scan'])
        self.assertFalse(report['motion_authorized'])

    def test_static_tf_and_missing_topic_reasons_are_bounded(self):
        from types import SimpleNamespace as NS
        evidence = PassiveEvidence()
        transform = NS(header=NS(frame_id='base_footprint',stamp=NS(sec=1,nanosec=2)),
                       child_frame_id='base_link', transform=NS(
                           translation=NS(x=0.,y=0.,z=0.),rotation=NS(x=0.,y=0.,z=0.,w=1.)))
        evidence.tf_message(NS(transforms=[transform]), 'tf_static')
        class Discovery:
            def count_publishers(self, topic):
                return {'odom':1,'scan':0,'/tf':1,'/tf_static':1}[topic]
        evidence.endpoint_snapshot(Discovery())
        report=evidence.report()
        self.assertEqual(report['tf_static_status'],'RECEIVED_UNVALIDATED')
        self.assertEqual(report['tf_first'][0]['topic'],'/tf_static')
        self.assertEqual(report['endpoints']['scan']['diagnosis'],'NO_PUBLISHER')
        self.assertEqual(report['missing_reason']['scan'],'NO_PUBLISHER')
        self.assertEqual(report['endpoints']['odom']['diagnosis'],'PUBLISHER_PRESENT')
        self.assertEqual(report['missing_reason']['odom'],'NO_MESSAGE_WITH_PUBLISHER')
        self.assertFalse(report['motion_authorized'])

    def test_shape_failure_retains_reason_even_if_raw_extraction_fails(self):
        evidence=PassiveEvidence();bad=message();del bad.pose
        evidence.message('odom',bad,10**10,20.,1)
        report=evidence.report()
        self.assertEqual(report['fault_counts']['odom']['MESSAGE_SHAPE'],1)
        self.assertIn('RAW_EXTRACTION_ODOM_AttributeError',report['capture_errors'])
        self.assertFalse(report['motion_authorized'])

    def test_passive_capture_sanitizes_untrusted_frame_and_nonfinite_fields(self):
        evidence = PassiveEvidence();invalid = message()
        invalid.header.frame_id = '../not-a-frame'
        invalid.pose.pose.position.x = float('nan')
        evidence.message('odom', invalid, 10**10, 20., 1)
        sample = evidence.report()['latest']['odom']
        self.assertEqual(evidence.report()['status']['odom'],'REJECTED')
        self.assertEqual(sample['frame_id'],'INVALID_FRAME')
        self.assertEqual(sample['position_m'][0],'NONFINITE_OR_NONNUMERIC')
        self.assertEqual(sample['fault'],'FRAME_ID')
        json.dumps(evidence.report(),allow_nan=False)

    def test_passive_capture_retains_later_fault_after_first_samples_are_valid(self):
        evidence = PassiveEvidence()
        for n in range(3):
            evidence.message('odom', message(stamp=9_950_000_000+n*10_000_000),
                             10_000_000_000+n*10_000_000, 20.+n*.01, 1)
        bad = message(stamp=9_980_000_000);bad.pose.pose.orientation.w = .5
        evidence.message('odom', bad, 10_030_000_000, 20.03, 1)
        report = evidence.report()
        self.assertTrue(all(sample['fault']=='NONE' for sample in report['first']['odom']))
        self.assertEqual(report['examples_by_fault']['odom']['ODOM_ORIENTATION']['quaternion_xyzw'][-1],.5)
        self.assertFalse(report['motion_authorized'])

    def test_cleanup_signal_handlers_restored(self):
        original = signal.getsignal(signal.SIGINT)
        try:
            with s.cleanup_signals():
                self.assertEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)
                raise ValueError('cleanup exception')
        except ValueError:
            pass
        self.assertEqual(signal.getsignal(signal.SIGINT), original)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux owned process')
    def test_actual_child_reaped_and_inherited_lease(self):
        import runtime
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with runtime.ownership(root) as lease:
                child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'],
                                         start_new_session=True, pass_fds=(lease.fileno(),),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    with self.assertRaises(RuntimeError):
                        with runtime.ownership(root): self.fail('duplicate owner')
                finally:
                    result = s.stop_child(child)
                self.assertEqual(result['escalation'], 'interrupt')
                self.assertIsNotNone(child.poll())
            with runtime.ownership(root): pass

    @unittest.skipUnless(sys.platform == 'linux', 'Linux parent death signal')
    def test_parent_death_terminates_fixed_role_and_releases_lease(self):
        import runtime
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'owned_exec.py').write_text(Path(s.__file__).with_name('owned_exec.py').read_text())
            # Replace ONLY the test directory's shell target; no ROS or real device.
            (root / 'stationary.sh').write_text('exec python3 "' + str(root / 'fake.py') + '"\n')
            (root / 'fake.py').write_text(
                'import pathlib,signal,time,sys\n'
                'root=pathlib.Path(__file__).parent\n'
                'def stop(*_):\n root.joinpath("stopped").touch()\n sys.exit(0)\n'
                'signal.signal(signal.SIGTERM,stop)\nroot.joinpath("ready").touch()\ntime.sleep(20)\n')
            (root / 'parent.py').write_text(
                'import sys,pathlib,subprocess,os,time\n'
                'sys.path.insert(0,' + repr(str(Path(s.__file__).parent)) + ')\n'
                'import runtime\nroot=pathlib.Path(__file__).parent\n'
                'with runtime.ownership(root) as lease:\n'
                ' p=subprocess.Popen([sys.executable,str(root/"owned_exec.py"),"base",str(os.getpid())],'
                'start_new_session=True,pass_fds=(lease.fileno(),))\n'
                ' root.joinpath("childpid").write_text(str(p.pid))\n time.sleep(20)\n')
            parent = subprocess.Popen([sys.executable, str(root / 'parent.py')], start_new_session=True)
            try:
                end = time.monotonic() + 4
                while not (root / 'ready').exists() and time.monotonic() < end:
                    time.sleep(.02)
                self.assertTrue((root / 'ready').exists())
                with self.assertRaises(RuntimeError):
                    with runtime.ownership(root): self.fail('duplicate owner')
                parent.kill(); parent.wait(timeout=2)
                end = time.monotonic() + 4
                while not (root / 'stopped').exists() and time.monotonic() < end:
                    time.sleep(.02)
                self.assertTrue((root / 'stopped').exists())
                # Let the child finish closing inherited lease FD after its marker.
                time.sleep(.05)
                with runtime.ownership(root): pass
            finally:
                if parent.poll() is None: parent.kill(); parent.wait()
                if (root / 'childpid').exists():
                    try: os.killpg(int((root / 'childpid').read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass

    @unittest.skipUnless(sys.platform == 'linux', 'Linux inherited flock')
    def test_parent_context_close_cannot_unlock_living_child(self):
        import runtime
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with runtime.ownership(root) as lease:
                child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'],
                                         start_new_session=True, pass_fds=(lease.fileno(),),
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                with self.assertRaises(RuntimeError):
                    with runtime.ownership(root): self.fail('parent unlocked surviving child')
            finally:
                s.stop_child(child)
            with runtime.ownership(root): pass


class TrialSessionTests(unittest.TestCase):
    def setUp(self):
        self.binding = Binding('boot1', 'release1', 'session1', 'trial1')
        self.session = TrialSession(self.binding)

    def prepared(self):
        self.session.ready(1, artifacts_verified=True, fake_tests_passed=True)

    def approved(self):
        self.prepared()
        self.session.approve_operator(2, self.binding, watching=True, area_clear=True)

    def test_prepare_never_approves(self):
        self.prepared()
        with self.assertRaises(ValueError):
            self.session.consume_dry_run(2, self.binding, fresh_idle=True, preflight_age_s=.1)

    def test_exact_trial_and_once_only(self):
        self.approved()
        result = self.session.consume_dry_run(3, self.binding, fresh_idle=True, preflight_age_s=.1)
        self.assertTrue(result['would_allow_fixed_trial'])
        self.assertFalse(result['motion_authorized'])
        self.assertEqual(result['stationary_required_ms'], 200)
        self.assertEqual(result['publish_window_ms'], 600)
        with self.assertRaises(ValueError):
            self.session.consume_dry_run(3.1, self.binding, fresh_idle=True, preflight_age_s=.1)

    def test_boot_release_session_or_trial_change_blocks(self):
        for field in vars(self.binding):
            self.setUp(); self.approved()
            values = vars(self.binding).copy(); values[field] = 'changed'
            result = self.session.consume_dry_run(3, Binding(**values), fresh_idle=True, preflight_age_s=.1)
            self.assertFalse(result['would_allow_fixed_trial'])

    def test_expired_or_bad_preflight_consumes_approval(self):
        for now, idle, age in [(18, True, .1), (3, False, .1), (3, True, 1.1), (3, True, float('nan'))]:
            self.setUp(); self.approved()
            result = self.session.consume_dry_run(now, self.binding, fresh_idle=idle, preflight_age_s=age)
            self.assertFalse(result['would_allow_fixed_trial'])
            self.assertEqual(self.session.state, 'CONSUMED')

    def test_operator_required_and_cancel_terminal(self):
        self.prepared()
        with self.assertRaises(ValueError):
            self.session.approve_operator(2, self.binding, watching=False, area_clear=True)
        self.session.cancel(3)
        with self.assertRaises(ValueError):
            self.session.approve_operator(4, self.binding, watching=True, area_clear=True)

    def test_clock_and_old_readiness(self):
        self.prepared()
        with self.assertRaises(ValueError): self.session.cancel(.5)
        with self.assertRaises(ValueError): self.session.cancel(float('nan'))
        with self.assertRaises(ValueError):
            self.session.approve_operator(302, self.binding, watching=True, area_clear=True)


if __name__ == '__main__':
    unittest.main()
