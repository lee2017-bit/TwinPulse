# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from analyze_robot_stop import analyze


class StopAnalysisTests(unittest.TestCase):
    def test_recorded_physical_failure_is_preserved(self):
        text = (ROOT / 'docs/verification/robot-policy20-motion-20260927.md').read_text(encoding='utf-8')
        result = analyze(text)
        self.assertEqual(result['timeout_receipt_after_last_send_ms'], 421)
        self.assertEqual(result['last_anchor_reset_t_ms'], 1361)
        self.assertEqual(result['reconstructed_stable_age_at_window_end_ms'], 122)
        self.assertFalse(result['reconstructed_settling_pass'])

    def test_no_timeout_cannot_be_declared_pass(self):
        with self.assertRaises(ValueError):
            analyze('SENSOR t=1 left=0 right=0\nSENSOR t=2 left=0 right=0')

    def test_unordered_samples_rejected(self):
        with self.assertRaises(ValueError):
            analyze('INPUT_SILENT t=2\nTIMEOUT_OBSERVED after_last_send_ms=400\n'
                    'SENSOR t=10 left=0 right=0\nSENSOR t=9 left=0 right=0')

    def test_fixed_anchor_detects_slow_accumulating_drift(self):
        text = 'INPUT_SILENT t=0\nTIMEOUT_OBSERVED after_last_send_ms=400\n'
        text += '\n'.join(f'SENSOR t={t} left={i} right={i}' for i, t in enumerate(range(400, 901, 50)))
        result = analyze(text)
        self.assertFalse(result['reconstructed_settling_pass'])

    def test_missing_tail_or_long_gap_cannot_report_stability(self):
        prefix = 'INPUT_SILENT t=0\nTIMEOUT_OBSERVED after_last_send_ms=400\n'
        for times in [(300, 400), (300, 400, 450), (300, 400, 850, 900)]:
            text = prefix + '\n'.join(f'SENSOR t={t} left=0 right=0' for t in times)
            result = analyze(text)
            self.assertFalse(result['sample_coverage_sufficient'])
            self.assertIsNone(result['reconstructed_settling_pass'])


if __name__ == '__main__':
    unittest.main()
