# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No subprocess/network/key access; diagnostic cannot settle financial holds."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.run_ordinary_staged_live_ten import RunnerPhaseTrace


class RunnerTraceTests(unittest.TestCase):
    def test_preparation_failure_keeps_exact_phase_and_is_not_a_refund(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)/'case';output.mkdir()
            trace=RunnerPhaseTrace(output,case_id='text-warehouse',config_id='flash-super')
            trace.mark('SETTINGS_ISOLATION');trace.mark('ROUTE_SAVE_READBACK')
            value=trace.finish('FAIL',error_type='BrokerError')
            self.assertEqual(value['terminal_phase'],'ROUTE_SAVE_READBACK')
            self.assertEqual(value['inference_status'],'NOT_ENTERED_JOURNEY')
            self.assertFalse(value['financial_settlement_authority'])
            self.assertEqual(json.loads((output/'runner-terminal.json').read_text()),value)
            self.assertNotIn('cost_by_provider',value)
            self.assertNotIn('error_message',value)

    def test_child_intent_is_unknown_even_if_launch_itself_raises(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)/'case';output.mkdir()
            trace=RunnerPhaseTrace(output);trace.mark('JOURNEY_DISPATCH_INTENT')
            value=trace.finish('FAIL',error_type='OSError')
            self.assertTrue(value['journey_dispatch_intent'])
            self.assertEqual(value['inference_status'],'UNKNOWN_AUDIT_REQUIRED')
            self.assertFalse(value['financial_settlement_authority'])

    def test_before_output_creation_uses_sibling_and_never_creates_case(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)/'case';trace=RunnerPhaseTrace(output)
            trace.finish('FAIL',error_type='ValueError')
            self.assertFalse(output.exists())
            self.assertTrue((Path(temp)/'case.preflight.json').is_file())

    def test_original_trace_cannot_be_overwritten(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)/'case';output.mkdir()
            trace=RunnerPhaseTrace(output);trace.finish('FAIL',error_type='ValueError')
            original=(output/'runner-terminal.json').read_bytes()
            with self.assertRaises(FileExistsError):trace.finish('FAIL',error_type='OSError')
            self.assertEqual((output/'runner-terminal.json').read_bytes(),original)
