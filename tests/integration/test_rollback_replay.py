# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable response replay of the actual five model failures, zero endpoints."""
import asyncio
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.replay_rollback_failures import replay, SavedResponseTransport
from twinpulse_provider.generation_policy import GenerationBudgetError


class RollbackReplayTests(unittest.TestCase):
    def test_actual_five_reenter_quality_with_sources_and_budget_preserved(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('Offline replay attempted a socket connection')
        # Initialize only the Windows asyncio wakeup pair before the guard.
        loop = asyncio.new_event_loop()
        try:
            with TemporaryDirectory() as folder, patch.object(socket, 'create_connection', forbidden), \
                    patch.object(socket.socket, 'connect', forbidden):
                report, path = loop.run_until_complete(replay(
                    ROOT/'outputs/model-role-comparison-20261010', Path(folder)))
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')), report)
                self.assertEqual(report['status'], 'PASS')
                self.assertTrue(report['original_evidence_unchanged'])
                self.assertEqual(len(report['cases']), 5)
                for case in report['cases']:
                    self.assertEqual(case['replay_stop'], 'SAVED_RESPONSES_EXHAUSTED')
                    self.assertFalse(case['generation_pass'])
                    self.assertEqual(case['HTTP'], 0)
                    self.assertTrue(case['regression_pass'])
        finally:
            loop.close()

    def test_exhausted_replay_never_reserves_or_calls_an_endpoint(self):
        transport = SavedResponseTransport({}, [])
        body = {'response_format':{'json_schema':{'name':'twinpulse_semantic_patch'}}}
        with self.assertRaisesRegex(GenerationBudgetError, 'SAVED_RESPONSES_EXHAUSTED'):
            asyncio.run(transport.complete(body, SimpleNamespace(), None))
        self.assertEqual(transport.used, [])
        self.assertEqual(transport.next_request, body)


if __name__ == '__main__':
    unittest.main()
