# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device coverage for the four-gate offline orchestrator."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import rehearse_robot_demo_offline as r


class OfflineRehearsalTests(unittest.TestCase):
    def test_allowlisted_commands_and_no_remote_actions(self):
        calls = []
        def fake(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, b'', b'Ran 3 tests in 0.01s\nOK')
        groups = r.run_groups(python='fake-python', runner=fake)
        self.assertEqual(len(calls), 5)
        self.assertEqual(set(groups), {name for name, _ in r.GROUPS})
        self.assertTrue(all(g['status'] == 'PASS_OFFLINE' for g in groups.values()))
        for index, (command, kwargs) in enumerate(calls):
            self.assertEqual(command[0], 'fake-python')
            self.assertEqual(tuple(command[1:]), r.GROUPS[index][1])
            self.assertEqual(command[1:3], ['-m', 'unittest'])
            self.assertNotIn('ssh', ' '.join(command).lower())
            self.assertEqual(kwargs['timeout'], 120)

    def test_failure_does_not_become_demo_ready(self):
        groups = {name: {'status': 'PASS_OFFLINE'} for name, _ in r.GROUPS}
        groups['2_lidar_lifecycle_and_record']['status'] = 'FAIL_OFFLINE'
        result = r.assess(groups, {'status': 'LOCKED_EXPECTED'})
        self.assertEqual(result['status'], 'OFFLINE_REVIEW_REQUIRED')
        self.assertFalse(result['motion_authorized'])
        self.assertFalse(result['demo_ready'])

    def test_collection_preflight_is_smaller_and_never_grants_demo(self):
        calls = []
        def fake(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, b'Ran 3 tests in 0.01s\nOK', b'')
        groups = r.run_groups(python='fake-python', runner=fake, groups=r.COLLECTION_GROUPS)
        self.assertEqual(len(calls), 2)
        result = r.assess_collection(groups, {'status': 'LOCKED_EXPECTED'})
        self.assertEqual(result['status'], 'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED')
        self.assertFalse(result['motion_authorized'])
        self.assertFalse(result['demo_ready'])
        self.assertIn('room_alignment', result['not_checked_here'])
        self.assertEqual(r.assess(groups, {'status': 'LOCKED_EXPECTED'})['status'],
                         'OFFLINE_REVIEW_REQUIRED')
        groups['1_connection_and_idle']['status'] = 'FAIL_OFFLINE'
        self.assertEqual(r.assess_collection(groups, {'status': 'LOCKED_EXPECTED'})['status'],
                         'COLLECTION_REVIEW_REQUIRED')

    def test_profile_must_remain_locked(self):
        profile = r.profile_gate()
        self.assertEqual(profile['status'], 'LOCKED_EXPECTED')
        self.assertFalse(profile['motion_enabled'])
        self.assertFalse(profile['autonomous_policy_present'])
        self.assertFalse(profile['calibration_in_source'])

    def test_collection_cache_reuses_only_matching_fresh_passing_receipt(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT / 'artifacts') as directory:
            root = Path(directory)
            runner = Mock(return_value=subprocess.CompletedProcess(
                ['fake-python'], 0, b'Ran 3 tests in 0.01s\nOK', b''))
            with patch.object(r, 'collection_fingerprint', return_value='source-a') as fingerprint, \
                    patch.object(r, 'profile_gate', return_value={'status': 'LOCKED_EXPECTED'}):
                report = r.prepare_collection_preflight(root, python='fake-python', runner=runner)
                self.assertEqual(report['pc_cache'], 'NEWLY_CHECKED')
                self.assertEqual(r.cached_collection_preflight(root, python='fake-python')['pc_cache'], 'MATCHED')
                self.assertEqual(runner.call_count, 2)
                receipt = r.collection_cache_path(root)
                created = json.loads(receipt.read_text(encoding='utf-8'))['created_unix_s']
                self.assertIsNone(r.cached_collection_preflight(root, python='fake-python',
                                                                now=created + r.COLLECTION_CACHE_MAX_AGE_S + 1))
                fingerprint.return_value = 'source-b'
                self.assertIsNone(r.cached_collection_preflight(root, python='fake-python'))

    def test_failed_collection_preflight_is_not_cached(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT / 'artifacts') as directory:
            root = Path(directory)
            runner = Mock(return_value=subprocess.CompletedProcess(
                ['fake-python'], 1, b'Ran 3 tests in 0.01s\nFAILED', b''))
            with patch.object(r, 'collection_fingerprint', return_value='source-a'), \
                    patch.object(r, 'profile_gate', return_value={'status': 'LOCKED_EXPECTED'}):
                report = r.prepare_collection_preflight(root, python='fake-python', runner=runner)
                self.assertEqual(report['status'], 'COLLECTION_REVIEW_REQUIRED')
                self.assertIsNone(r.cached_collection_preflight(root, python='fake-python'))

    def test_source_change_invalidates_fingerprint(self):
        with tempfile.TemporaryDirectory(dir=r.ROOT / 'artifacts') as directory:
            root = Path(directory)
            source = root / 'sample.py'
            source.write_text('a = 1', encoding='utf-8')
            for subdir in ('packages/twinpulse_app/src', 'packages/twinpulse_core/src',
                           'packages/twinpulse_provider/src', 'packages/twinpulse_robot_safety'):
                (root / subdir).mkdir(parents=True)
            with patch.object(r, 'COLLECTION_FILES', ('sample.py',)):
                before = r.collection_fingerprint(root)
                source.write_text('a = 2', encoding='utf-8')
                self.assertNotEqual(before, r.collection_fingerprint(root))


if __name__ == '__main__':
    unittest.main()
