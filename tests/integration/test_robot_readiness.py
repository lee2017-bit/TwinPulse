# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device orchestration tests: subprocesses are fakes, not an SSH transport."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import run_robot_readiness as readiness
import rehearse_robot_demo_offline as rehearsal

OFFLINE_PASS = lambda: {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'}


class ReadinessTests(unittest.TestCase):
    def test_matched_pc_receipt_skips_test_rerun(self):
        receipt = {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED', 'pc_cache': 'MATCHED'}
        with patch.object(rehearsal, 'cached_collection_preflight', return_value=receipt), \
                patch.object(rehearsal, 'prepare_collection_preflight') as prepare:
            self.assertIs(readiness._offline_preflight(), receipt)
            prepare.assert_not_called()

    def test_missing_pc_receipt_runs_local_tests(self):
        receipt = {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED', 'pc_cache': 'NEWLY_CHECKED'}
        with patch.object(rehearsal, 'cached_collection_preflight', return_value=None), \
                patch.object(rehearsal, 'prepare_collection_preflight', return_value=receipt) as prepare:
            self.assertIs(readiness._offline_preflight(), receipt)
            prepare.assert_called_once_with()

    def test_source_change_after_pc_check_stops_before_client(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock()
            with patch.object(readiness, '_offline_preflight', return_value={
                    'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED',
                    'pc_fingerprint': 'before'}), \
                    patch.object(rehearsal, 'collection_fingerprint', return_value='after'):
                result, _ = readiness.collect(run=True, output_root=Path(directory), runner=client)
            self.assertEqual(result['status'], 'STOPPED_AT_OFFLINE_PREFLIGHT')
            self.assertIn('changed', result['reason'])
            client.assert_not_called()

    def fake_runner(self, root, reports, calls):
        def run(command, **kwargs):
            calls.append(command)
            report = reports[len(calls) - 1]
            out = root / 'robot-preparation' / ('fake-%d' % len(calls)) / 'result'
            out.mkdir(parents=True)
            (out / 'report.json').write_text(json.dumps(report), encoding='utf-8')
            (out / 'report.html').write_text('fake', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0 if report['status'] in (
                'SOFTWARE_PREPARED_IDLE', 'STATIONARY_CHECK_PASS') else 2,
                ('Status: ' + report['status'] + '\nReport: ' + str(out / 'report.html')).encode(), b'')
        return run

    @staticmethod
    def prepared(**changes):
        return {'schema_version': 'robot-prepare-1.0', 'motion_authorized': False,
                'status': 'SOFTWARE_PREPARED_IDLE', 'boot_id': 'boot-a',
                'release_id': 'release-a', **changes}

    @staticmethod
    def stationary(**changes):
        return {'schema_version': 'robot-prepare-1.0', 'motion_authorized': False,
                'status': 'STATIONARY_CHECK_PASS', 'boot_id': 'boot-a',
                'release_id': 'release-a', 'stationary': {'observation': {
                    'passive_ros': {'status': {'odom': 'REJECTED', 'scan': 'NOT_RECEIVED'},
                                    'missing_reason': {'scan': 'NO_PUBLISHER'},
                                    'fault_counts': {'odom': {'FRAME_ID': 3}},
                                    'tf_status': 'NOT_RECEIVED', 'tf_static_status': 'NOT_RECEIVED'}}},
                **changes}

    def test_offline_default_never_calls_transport(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(readiness, 'ROOT', Path(directory)):
            with patch.object(readiness, 'bundle', return_value='digest') as bundle:
                result, path = readiness.collect(output_root=Path(directory), runner=lambda *_a, **_k: self.fail('transport'))
            self.assertEqual(result['status'], 'OFFLINE_ONLY')
            self.assertFalse(result['motion_authorized'])
            bundle.assert_called_once()
            self.assertTrue(path.is_dir())

    def test_one_run_collects_sequentially_and_keeps_missing_scan_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            with patch.object(readiness, 'ROOT', root):
                result, out = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [self.prepared(), self.stationary()], calls),
                    offline_preflight=OFFLINE_PASS)
            self.assertEqual(len(calls), 2)
            self.assertIn('prepare', calls[0])
            self.assertIn('stationary', calls[1])
            self.assertEqual(result['status'], 'EVIDENCE_GAPS')
            self.assertEqual(result['evidence']['scan']['reason'], 'NO_PUBLISHER')
            self.assertEqual(result['evidence']['odom']['fault_counts']['FRAME_ID'], 3)
            self.assertEqual(result['evidence']['room_alignment'], 'NOT_VERIFIED')
            self.assertFalse(result['demo_ready'])
            self.assertEqual(result['remaining_gates']['scoped_autonomous_mission'], 'LOCKED')
            self.assertIn('odom=REJECTED', result['steps']['evidence_review']['reason'])
            page = readiness.save(result, out)
            self.assertTrue(page.is_file())
            self.assertIn('Passive sensor/frame diagnosis', page.read_text(encoding='utf-8'))
            self.assertIn('NO_PUBLISHER', page.read_text(encoding='utf-8'))

    def test_prepare_failure_stops_before_stationary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            bad = self.prepared(status='PREPARED_NEEDS_ATTENTION', reason='Torque ON')
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [bad], calls), offline_preflight=OFFLINE_PASS)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['status'], 'STOPPED_AT_SOURCE_AND_IDLE')
            self.assertEqual(result['reason'], 'Torque ON')
            self.assertEqual(result['steps']['stationary_collection']['status'], 'NOT_RUN')

    def test_prepare_health_issue_is_visible_without_remote_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            bad = self.prepared(status='PREPARED_NEEDS_ATTENTION')
            bad['health'] = {'issues': ['Board is not confirmed idle with motors disabled.']}
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [bad], calls), offline_preflight=OFFLINE_PASS)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['status'], 'STOPPED_AT_SOURCE_AND_IDLE')
            self.assertEqual(result['reason'], 'Board is not confirmed idle with motors disabled.')
            self.assertEqual(result['steps']['stationary_collection']['status'], 'NOT_RUN')

    def test_export_failure_names_missing_file_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            bad = self.stationary()
            bad['status'] = 'EVIDENCE_EXPORT_INCOMPLETE'
            bad['evidence_export'] = {'status':'INCOMPLETE','files': {
                'report.json': {'status': 'COPIED'},
                'operation.log': {'status': 'MISSING_OR_TRANSFER_FAILED'}}}
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [self.prepared(), bad], calls),
                    offline_preflight=OFFLINE_PASS)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result['status'], 'STOPPED_AT_STATIONARY_COLLECTION')
            self.assertIn('operation.log=MISSING_OR_TRANSFER_FAILED', result['reason'])
            self.assertEqual(result['steps']['evidence_review']['status'], 'EVIDENCE_GAPS')
            self.assertEqual(result['evidence']['odom']['status'],'REJECTED')
            self.assertEqual(result['evidence_export']['status'],'INCOMPLETE')

    def test_boot_change_refuses_evidence_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [self.prepared(), self.stationary(boot_id='boot-b')], calls),
                    offline_preflight=OFFLINE_PASS)
            self.assertEqual(result['status'], 'BOOT_OR_RELEASE_CHANGED')
            self.assertNotIn('evidence', result)

    def test_stationary_failure_surfaces_nested_reason_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            failed = self.stationary(status='FAILED', stationary={
                'status': 'FAILED', 'reason': 'Observer rejected state',
                'diagnostics': {'observer': {'lines': ['invalid frame']}}})
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root,
                    runner=self.fake_runner(root, [self.prepared(), failed], calls),
                    offline_preflight=OFFLINE_PASS)
            self.assertEqual(result['status'], 'STOPPED_AT_STATIONARY_COLLECTION')
            self.assertEqual(result['reason'], 'Observer rejected state')
            self.assertEqual(result['steps']['stationary_collection']['failure_diagnostics']
                             ['observer']['lines'], ['invalid frame'])

    def test_torque_off_never_implicit(self):
        with self.assertRaisesRegex(ValueError, 'TORQUE_OFF_REQUIRES_EXPLICIT'):
            readiness.collect(run=True, allow_torque_off=True, runner=lambda *_a, **_k: self.fail('transport'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            with patch.object(readiness, 'ROOT', root):
                readiness.collect(run=True, allow_torque_off=True, flat_clear_confirmed=True,
                    output_root=root, runner=self.fake_runner(root, [self.prepared(), self.stationary()], calls),
                    offline_preflight=OFFLINE_PASS)
            self.assertIn('--disable-torque', calls[0])
            self.assertNotIn('--disable-torque', calls[1])

    def test_timeout_is_unknown_remote_state_and_does_not_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            def timeout(command, **_kwargs):
                calls.append(command)
                raise subprocess.TimeoutExpired(command, 360)
            with patch.object(readiness, 'ROOT', root):
                result, _ = readiness.collect(run=True, output_root=root, runner=timeout,
                                              offline_preflight=OFFLINE_PASS)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['status'], 'REMOTE_STATE_UNKNOWN')
            self.assertEqual(result['steps']['stationary_collection']['status'], 'NOT_RUN')

    def test_failed_offline_preflight_never_contacts_robot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, _ = readiness.collect(run=True, output_root=root,
                offline_preflight=lambda: {'status': 'OFFLINE_REVIEW_REQUIRED'},
                runner=lambda *_a, **_k: self.fail('no transport after local failure'))
            self.assertEqual(result['status'], 'STOPPED_AT_OFFLINE_PREFLIGHT')

    def test_frame_diagnostic_distinguishes_rejected_and_absent_sources(self):
        passive = {'status': {'odom': 'REJECTED', 'scan': 'NOT_RECEIVED'},
                   'fault_counts': {'odom': {'FRAME_ID': 3}},
                   'examples_by_fault': {'odom': {'FRAME_ID': {
                       'frame_id': '/odom', 'child_frame_id': '/base_footprint', 'stamp_sec': 9}}},
                   'endpoints': {'odom': {'publisher_count': 1}, 'scan': {'publisher_count': 0},
                                 'tf': {'publisher_count': 1}, 'tf_static': {'publisher_count': 0}},
                   'tf_first': []}
        result = readiness._frame_diagnostic(passive)
        self.assertEqual(result['odom']['cause'], 'ALL_CAPTURED_SAMPLES_REJECTED')
        self.assertEqual(result['odom']['examples_by_fault']['FRAME_ID']['frame_id'], '/odom')
        self.assertEqual(result['scan']['cause'], 'NO_PUBLISHER')
        self.assertEqual(result['tf']['interpretation'], 'NOT_OBSERVED_IN_BOUNDED_SAMPLE')
        self.assertFalse(result['alignment_verified'])

    def test_bounded_tf_sample_does_not_grant_alignment(self):
        passive = {'status': {'odom': 'SAMPLES_ACCEPTED_UNALIGNED',
                              'scan': 'SAMPLES_ACCEPTED_UNALIGNED'},
                   'latest': {'odom': {'fault': 'NONE', 'frame_id': 'odom',
                                       'child_frame_id': 'base_footprint'},
                              'scan': {'fault': 'NONE', 'frame_id': 'base_scan'}},
                   'tf_status': 'RECEIVED_UNVALIDATED', 'tf_static_status': 'NOT_RECEIVED',
                   'tf_first': [{'frame_id': 'odom', 'child_frame_id': 'base_footprint',
                                 'topic': '/tf'}]}
        result = readiness._frame_diagnostic(passive)
        self.assertEqual(result['odom']['observed_child_frame_id'], 'base_footprint')
        self.assertEqual(result['scan']['observed_frame_id'], 'base_scan')
        self.assertEqual(result['tf']['interpretation'], 'OBSERVED_UNVALIDATED_NOT_CALIBRATION')
        self.assertEqual(result['room_to_odom'], 'NOT_CAPTURED')
        self.assertFalse(result['alignment_verified'])


if __name__ == '__main__':
    unittest.main()
