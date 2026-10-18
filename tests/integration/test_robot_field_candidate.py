# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device frozen candidate and field-consumption regression."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import robot_field_candidate as candidate
import run_robot_field_suite as suite
import run_robot_readiness as readiness


def contract():
    return {'status': 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED',
            'field_suite_contracts': {'status': 'PASS'}}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.members = {'profile.json': json.dumps({'architecture': 'aarch64',
            'ros_distro': 'humble', 'guard_sha256': 'a'*64,
            'import_params_sha256': 'b'*64, 'motion_enabled': False}).encode(),
            'runtime.py': b'"""No device fixture."""\n'}
        for target, value in (('source_members', self.members),
                              ('collection_fingerprint', 'f'*64),
                              ('runner_hashes', {'runner.py': 'e'*64})):
            mock = patch.object(candidate, target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        self.child = Mock(return_value=subprocess.CompletedProcess([], 0,
                    b'FIELD_CANDIDATE_IMPORT_PASS\n', b''))

    def build(self, preflight=contract):
        self.report, self.out = candidate.prepare(self.root, preflight=preflight,
            runner=self.child, presence=lambda: {'identity_presence': True})
        return self.out/'manifest.json'

    def mutate(self, **values):
        path = self.out/'manifest.json'
        data = json.loads(path.read_text())
        data.update(values)
        path.write_text(json.dumps(data))

    def test_prepared_is_only_collection_and_does_not_generate_physical_evidence(self):
        path = self.build()
        frozen = candidate.checked(self.root, path)
        self.assertEqual(frozen['source_id'], candidate.identity(self.members))
        self.assertEqual(self.report['status'], 'FIELD_COLLECTION_CANDIDATE_PREPARED')
        self.assertFalse(self.report['target_verified'])
        self.assertFalse(self.report['autonomous_demo_ready'])
        self.assertFalse(self.report['motion_authorized'])
        self.assertEqual(len(self.report['autonomous_gaps']), 4)
        self.assertFalse((self.root/'packages').exists())
        argv = self.child.call_args.args[0]
        self.assertEqual(argv[1:4], ['-I', '-B', '-c'])
        self.assertNotIn('ssh', argv)

    def test_source_change_is_rejected(self):
        path = self.build()
        self.members['runtime.py'] += b'changed = True\n'
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_RUNNER_CHANGED'):
            candidate.checked(self.root, path)

    def test_runner_or_pc_input_change_is_rejected(self):
        path = self.build()
        for name in ('collection_fingerprint', 'runner_hashes'):
            with self.subTest(name=name), patch.object(candidate, name, return_value='changed'), \
                    self.assertRaisesRegex(ValueError, 'SOURCE_OR_RUNNER_CHANGED'):
                candidate.checked(self.root, path)

    def test_expired_or_future_receipt_rejected(self):
        path = self.build()
        created = json.loads(path.read_text())['created_unix_s']
        for now in (created-1, created+candidate.COLLECTION_CACHE_MAX_AGE_S+1):
            with self.assertRaisesRegex(ValueError, 'EXPIRED'):
                candidate.checked(self.root, path, now=now)

    def test_archive_change_never_extracts(self):
        path = self.build()
        with (self.out/'source.tar').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_CHANGED'):
            candidate.checked(self.root, path)

    def test_preflight_change_rejected(self):
        path = self.build()
        (self.out/'preflight.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'PREFLIGHT_CHANGED'):
            candidate.checked(self.root, path)

    def test_failed_import_or_contract_cannot_be_used(self):
        self.child.return_value = subprocess.CompletedProcess([], 1, b'', b'ImportError')
        path = self.build(lambda: {'status': 'FAILED'})
        self.assertEqual(self.report['status'], 'LOCAL_PREPARATION_NEEDS_ATTENTION')
        with self.assertRaisesRegex(ValueError, 'CONTRACT'):
            candidate.checked(self.root, path)

    def test_unknown_or_duplicate_manifest_fields_rejected(self):
        path = self.build()
        original = path.read_text()
        self.mutate(approved=True)
        with self.assertRaisesRegex(ValueError, 'CONTRACT'):
            candidate.checked(self.root, path)
        path.write_text(original[:-1] + ', "schema": "other"}')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_KEY'):
            candidate.checked(self.root, path)

    def test_output_must_be_generated_under_candidate_root(self):
        with self.assertRaisesRegex(ValueError, 'OUTPUT_ROOT'):
            candidate.prepare(self.root, preflight=contract, output=self.root/'arbitrary',
                              runner=self.child)

    def test_bad_candidate_blocks_field_contact_but_retains_independent_evidence_stage(self):
        contact = Mock()
        with patch.object(candidate, 'checked', side_effect=ValueError('ARCHIVE_CHANGED')):
            report, _ = suite.run_suite(field_run=True, operator_watching=True, clear_floor=True,
                output=self.root/'result', candidate=self.root/'manifest.json', health=contact)
        contact.assert_not_called()
        self.assertEqual(report['status'], 'FIELD_BLOCKED_PC_PREFLIGHT')
        self.assertEqual(report['stages']['saved_evidence']['status'], 'NOT_REQUESTED')
        self.assertIn('ARCHIVE_CHANGED', report['stages']['offline_contracts']['reason'])

    def test_stationary_client_receives_candidate_for_both_modes(self):
        out = self.root/'robot-preparation/run/result'
        out.mkdir(parents=True)
        (out/'report.json').write_text(json.dumps({'schema_version': 'robot-prepare-1.0',
                                                 'motion_authorized': False}))
        runner = Mock(return_value=subprocess.CompletedProcess([], 0,
                        ('Report: '+str(out/'report.html')).encode(), b''))
        manifest = self.root/'manifest.json'
        for mode in ('prepare', 'stationary'):
            readiness._invoke(mode, self.root, '192.168.35.139', Path('not-read'), False,
                              runner, candidate=manifest)
            argv = runner.call_args.args[0]
            self.assertEqual(argv[-2:], ['--candidate', str(manifest)])

    def test_prepare_cli_rejects_bad_candidate_before_any_transport(self):
        import prepare_robot
        with patch.object(sys, 'argv', ['prepare_robot', '--candidate', str(self.root/'bad.json')]), \
                patch.object(candidate, 'checked', side_effect=ValueError('ARCHIVE_CHANGED')), \
                patch.object(prepare_robot.subprocess, 'run') as contact:
            self.assertEqual(prepare_robot.main(), 2)
            contact.assert_not_called()

    def test_field_uses_frozen_preflight_and_same_candidate_without_another_test_run(self):
        from tests.integration.test_robot_field_suite import observed
        frozen = {'source_id': 'release-a', 'preflight': contract()}
        stationary = Mock(return_value=({'boot_id': 'boot-a', 'release_id': 'release-a',
            'steps': {'source_and_idle': {'status': 'SOFTWARE_PREPARED_IDLE'},
                      'stationary_collection': {'status': 'STATIONARY_CHECK_PASS'}}}, self.root))
        qualified = Mock(return_value={'status': 'QUALIFIED', 'robot_boot_id': 'boot-a',
                                       'robot_release_id': 'release-a'})
        manifest = self.root/'manifest.json'
        with patch.object(candidate, 'checked', return_value=frozen), \
                patch.object(suite, '_stationary', stationary):
            # Bind the patched default explicitly so production candidate
            # propagation (not a three-argument fake fallback) is exercised.
            report, _ = suite.run_suite(field_run=True, operator_watching=True, clear_floor=True,
                allow_fixed_motion_and_scan=True, candidate=manifest, output=self.root/'field',
                health=lambda *_a, **_k: observed(), stationary=stationary,
                qualification=qualified, preflight=lambda: self.fail('repeated PC tests'))
        self.assertEqual(report['stages']['qualification']['status'], 'QUALIFIED')
        self.assertEqual(stationary.call_args.kwargs['candidate'], manifest)
        qualified.assert_called_once()
        self.assertFalse(report['demo_ready'])

    def test_readiness_release_mismatch_blocks_stationary_after_source(self):
        client = Mock(return_value={'exit_code': 0, 'report_path': 'synthetic',
            'report': {'status': 'SOFTWARE_PREPARED_IDLE', 'release_id': 'wrong'}})
        with patch.object(candidate, 'checked', return_value={'source_id': 'expected',
                'preflight': contract()}), patch.object(readiness, '_invoke', client):
            report, _ = readiness.collect(run=True, output_root=self.root,
                offline_preflight=contract, candidate=self.root/'manifest.json')
        self.assertEqual(report['status'], 'CANDIDATE_RELEASE_MISMATCH')
        client.assert_called_once()

    def test_missing_target_cause_is_not_overwritten_as_release_mismatch(self):
        client = Mock(return_value={'exit_code': 2, 'report_path': 'synthetic',
            'report': {'status': 'PREPARATION_FAILED', 'reason': 'IMPORTED_PARAMS_MISSING'}})
        with patch.object(candidate, 'checked', return_value={'source_id': 'expected',
                'preflight': contract()}), patch.object(readiness, '_invoke', client):
            report, _ = readiness.collect(run=True, output_root=self.root,
                offline_preflight=contract, candidate=self.root/'manifest.json')
        self.assertEqual(report['status'], 'STOPPED_AT_SOURCE_AND_IDLE')
        self.assertEqual(report['reason'], 'IMPORTED_PARAMS_MISSING')

    def test_sensor_source_or_archive_change_is_rejected(self):
        path = self.build()
        with patch.object(candidate, 'sensor_target', return_value={'status': 'changed'}), \
                self.assertRaisesRegex(ValueError, 'SENSOR_SOURCE_CHANGED'):
            candidate.checked(self.root, path)
        self.mutate(sensor_archive_sha256='a'*64)
        (self.out/'sensor-target.tar').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SENSOR_ARCHIVE_CHANGED'):
            candidate.checked(self.root, path)

    def test_real_source_archive_is_importable_without_ros_and_does_not_change_profile(self):
        # Remove source/fingerprint mocks for one real candidate import. Contract
        # execution is still injected here; actual contracts run in preparation.
        before = (ROOT/'packages/twinpulse_robot_safety/profile.json').read_bytes()
        from robot_source_identity import bundle_files
        members = bundle_files(ROOT)
        with patch.object(candidate, 'source_members', return_value=members):
            report, out = candidate.prepare(ROOT, preflight=contract, presence=lambda: {'pc': True})
            self.assertEqual(report['checks']['isolated_import']['status'], 'PASS_LOCAL_ONLY',
                             (out/'import.stderr').read_text())
        self.assertEqual((ROOT/'packages/twinpulse_robot_safety/profile.json').read_bytes(), before)

    def test_coin_patches_really_apply_inside_ancestor_repository(self):
        import prepare_coin_time_candidate as coin
        source = Path('C:/Users/jaewo/Documents/Codex/2026-09-12/dl/coin-d4-offline-review-20260926')
        if not source.is_dir():
            self.skipTest('pinned local vendor source is not present on this PC')
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as folder:
            output = Path(folder)/'nested-candidate'
            result = coin.prepare(source, output)
            self.assertEqual(result['patch_application'],
                             'ISOLATED_NON_REPOSITORY_CHANGED_FILES_AND_REVERSE_CHECK')
            header = output/'include/coin_d4_driver/scan_clock_contract.hpp'
            self.assertTrue(header.is_file())
            self.assertIn('scan_contract(', header.read_text())
            self.assertIn('clock_gettime(CLOCK_MONOTONIC, &tim)',
                          (output/'src/lidar_sdk/timer.cpp').read_text())
            self.assertNotIn('.to_msg()', (output/'src/coin_d4_base_handler.cpp').read_text())
            self.assertIn('header.stamp = rclcpp::Time(contract.stamp_ns);',
                          (output/'src/coin_d4_base_handler.cpp').read_text())
            for name, digest in result['source_files'].items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(), digest)
            self.assertFalse((output/'.git').exists())
            self.assertEqual(result['target_build'], 'TARGET_BUILD_NOT_RUN')


if __name__ == '__main__':
    unittest.main()
