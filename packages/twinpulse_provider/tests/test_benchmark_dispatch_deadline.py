# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline deadline guards; no model, credential, worker or network calls."""
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from unittest.mock import Mock
import asyncio
from pathlib import Path
import unittest
from twinpulse_provider.reliability import check_benchmark_dispatch_deadline
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.reliability import AuditedChatTransport,InferenceEvidence
from twinpulse_provider import CancellationToken
from test_nebius_pipeline import config


class BenchmarkDispatchDeadlineTests(unittest.TestCase):
    def test_expired_deadline_refuses_next_dispatch_not_settlement(self):
        now=datetime(2026,10,10,tzinfo=timezone.utc)
        with patch.dict('os.environ',{'TWINPULSE_BENCHMARK_EXPIRES_AT':now.isoformat()}):
            check_benchmark_dispatch_deadline(now=now-timedelta(microseconds=1))
            with self.assertRaisesRegex(ProviderConfigurationError,'EXPIRED_NO_DISPATCH'):
                check_benchmark_dispatch_deadline(now=now)

    def test_invalid_deadline_fails_closed_absent_does_not_grant(self):
        for value in ('','not-a-time','2026-10-10T00:00:00','2026-10-10T00:00:00+09:00'):
            with self.subTest(value=value),patch.dict('os.environ',{'TWINPULSE_BENCHMARK_EXPIRES_AT':value}):
                with self.assertRaisesRegex(ProviderConfigurationError,'DEADLINE_INVALID'):
                    check_benchmark_dispatch_deadline()
        with patch.dict('os.environ',{},clear=True):check_benchmark_dispatch_deadline()

    def test_actual_admitted_worker_checks_expiry_before_reservation_or_http(self):
        opener=Mock(side_effect=AssertionError('REAL_HTTP_FORBIDDEN'));ledger=Mock()
        transport=AuditedChatTransport(lambda:'SYNTHETIC_NOT_A_SECRET',InferenceEvidence(Path('NEVER_CREATED')),
            ledger,opener=opener)
        with patch.dict('os.environ',{'TWINPULSE_BENCHMARK_EXPIRES_AT':'2000-01-01T00:00:00+00:00'}):
            with self.assertRaisesRegex(ProviderConfigurationError,'EXPIRED_NO_DISPATCH'):
                asyncio.run(transport.complete({'model':config().model_id},CancellationToken(),config()))
        ledger.reserve.assert_not_called();opener.assert_not_called();self.assertEqual(transport.calls,[])


if __name__=='__main__':unittest.main()
