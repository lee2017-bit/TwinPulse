# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The demo inventory may never report PC readiness from a symbol-only audit."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.demo_contract import OPERATIONS, audit, operation_for_action
import twinpulse_core.demo_contract as demo_contract
from twinpulse_core.demo_operation_manifest import CONTRACTS, FIELDS


class DemoContractTests(unittest.TestCase):
    def test_ids_are_unique_and_required_gaps_are_visible(self):
        ids = [row[0] for row in OPERATIONS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 17)
        self.assertTrue({'forward_motion','reverse_motion','left_turn','right_turn','saved_evidence_resume'} <= set(ids))
        report = audit(ROOT)
        self.assertFalse(report['pc_demo_ready'])
        self.assertFalse(report['offline_inventory_complete'])
        self.assertEqual([row['operation_id'] for row in report['operations']], ids)
        self.assertTrue(any('NOT_IMPLEMENTED' in row['reasons'] for row in report['operations']))
        self.assertFalse(report['manifest_mapped'])
        self.assertEqual(report['test_execution'], 'NOT_RUN_BY_AUDIT')
        self.assertEqual(set(CONTRACTS), set(ids))
        self.assertTrue(all(len(row) == len(FIELDS) for row in CONTRACTS.values()))
        self.assertIn('PRODUCT_ENTRY_UNMAPPED', next(row for row in report['operations']
            if row['operation_id'] == 'autonomous_mission')['contract_reasons'])
        self.assertEqual(['PHYSICAL_TEST_UNMAPPED'], next(row for row in report['operations']
            if row['operation_id'] == 'saved_evidence_resume')['contract_reasons'])

    def test_missing_source_and_test_are_not_reported_as_covered(self):
        with tempfile.TemporaryDirectory() as directory:
            report = audit(directory)
        self.assertFalse(report['pc_demo_ready'])
        for row in report['operations']:
            self.assertIn('SOURCE_MISSING', row['reasons'])
            self.assertIn('TEST_MISSING', row['reasons'])
        self.assertFalse(report['manifest_mapped'])

    def test_new_operation_or_missing_mapping_cannot_silently_pass(self):
        with patch.object(demo_contract, 'OPERATIONS', OPERATIONS + (
            ('new_required_demo_action', *OPERATIONS[0][1:]),)):
            report = audit(ROOT)
        added = report['operations'][-1]
        self.assertIn('CONTRACT_MISSING_OR_MALFORMED', added['contract_reasons'])
        self.assertFalse(report['manifest_mapped'])

    def test_bad_product_route_or_test_symbol_is_a_mapping_gap(self):
        original = CONTRACTS['saved_evidence_resume']
        broken = dict(CONTRACTS)
        broken['saved_evidence_resume'] = ('POST /v1/product/not-a-route', *original[1:-2],
            'tests/integration/test_robot_evidence_recovery.py#test_not_present', None)
        with patch.object(demo_contract, 'CONTRACTS', broken):
            report = audit(ROOT)
        row = next(item for item in report['operations'] if item['operation_id'] == 'saved_evidence_resume')
        self.assertIn('PRODUCT_ENTRY_UNMAPPED', row['contract_reasons'])
        self.assertIn('INTEGRATION_TEST_UNMAPPED', row['contract_reasons'])
        self.assertFalse(report['manifest_mapped'])

    def test_wire_action_mapping_does_not_confuse_release_with_terminal_stop(self):
        expected={'forward':'forward_motion','backward':'reverse_motion',
                  'left':'left_turn','right':'right_turn',
                  'finish_stop':'graceful_stop','force_stop':'force_stop'}
        for action, operation_id in expected.items():
            self.assertEqual(operation_for_action(action), operation_id)
        for action in ('stop','close','watch','qualify',None,[]):
            self.assertIsNone(operation_for_action(action))

    def test_manual_actions_have_distinct_app_http_fake_transport_integration_ids(self):
        report = audit(ROOT)
        expected = {'forward_motion': 'forward', 'reverse_motion': 'reverse',
                    'left_turn': 'left', 'right_turn': 'right',
                    'graceful_stop': 'graceful_stop', 'force_stop': 'force_stop'}
        for row in report['operations']:
            if row['operation_id'] not in expected:
                continue
            self.assertEqual(row['contract']['integration_test_id'],
                'tests/integration/test_physical_controller.py#test_http_' +
                expected[row['operation_id']] + '_input_reaches_fake_owned_pipe'
                if row['operation_id'] in {'forward_motion','reverse_motion','left_turn','right_turn'}
                else 'tests/integration/test_physical_controller.py#test_http_' +
                expected[row['operation_id']] + '_reaches_fake_owned_pipe')
            self.assertNotIn('INTEGRATION_TEST_UNMAPPED', row['contract_reasons'])
            self.assertIn('PHYSICAL_TEST_UNMAPPED', row['contract_reasons'])


if __name__ == '__main__':
    unittest.main()
