# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite local wire evidence, no HTTP/keys; original request remains unchanged."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from twinpulse_provider.reliability import InferenceEvidence, MAX_STRUCTURED_EVIDENCE_BYTES


class StructuredEvidenceBudgetTests(unittest.TestCase):
    def test_large_typed_repair_request_retains_tail_and_hash(self):
        with TemporaryDirectory() as directory:
            body = dict(schema='x' * 273841, tail='typed-final-reference')
            original = json.dumps(body, ensure_ascii=False)
            evidence = InferenceEvidence(Path(directory))
            evidence.started('a' * 32, {}, request_body=body)
            record = json.loads((Path(directory) / 'dispatches' / ('a' * 32 + '.json')).read_text(encoding='utf-8'))
            self.assertFalse(record['request_truncated'])
            self.assertEqual(json.loads(record['request_redacted']), body)
            self.assertEqual(record['stored_request_sha256'], hashlib.sha256(original.encode()).hexdigest())
            self.assertEqual(json.dumps(body, ensure_ascii=False), original)

    def test_large_validation_preserves_contract_tail(self):
        with TemporaryDirectory() as directory:
            evidence = InferenceEvidence(Path(directory))
            data = dict(payload='x' * 300000, tail='current-revision-contract')
            evidence.validation('a' * 32, 'semantic_compile', data)
            record = json.loads((Path(directory) / 'validations' / ('a' * 32 + '-semantic_compile.json')).read_text(encoding='utf-8'))
            self.assertFalse(record['record_truncated'])
            self.assertEqual(json.loads(record['record_redacted']), data)
            self.assertEqual(record['captured_record_byte_count'], len(record['record_redacted'].encode()))

    def test_utf8_evidence_is_byte_bounded_and_still_marks_truncation(self):
        with TemporaryDirectory() as directory:
            evidence = InferenceEvidence(Path(directory))
            evidence.started('a' * 32, {}, request_body=dict(text='방' * MAX_STRUCTURED_EVIDENCE_BYTES))
            record = json.loads((Path(directory) / 'dispatches' / ('a' * 32 + '.json')).read_text(encoding='utf-8'))
            self.assertTrue(record['request_truncated'])
            self.assertLessEqual(record['captured_request_byte_count'], MAX_STRUCTURED_EVIDENCE_BYTES)
            self.assertNotIn('\ufffd', record['request_redacted'])

    def test_secret_and_image_redaction_precedes_capture_of_tail(self):
        with TemporaryDirectory() as directory:
            evidence = InferenceEvidence(Path(directory))
            body = dict(schema='x' * 300000, api_key='canary-only',
                image='data:image/png;base64,YWJj', authorization='Bearer canary-only')
            evidence.started('a' * 32, {}, request_body=body, secret='canary-only')
            record = json.loads((Path(directory) / 'dispatches' / ('a' * 32 + '.json')).read_text(encoding='utf-8'))
            self.assertFalse(record['request_truncated'])
            self.assertNotIn('canary-only', record['request_redacted'])
            self.assertNotIn('YWJj', record['request_redacted'])
            self.assertIn('[IMAGE_REMOVED]', record['request_redacted'])
            self.assertEqual(record['access_scope'], 'local_only')

    def test_original_attempt_is_never_overwritten(self):
        with TemporaryDirectory() as directory:
            evidence = InferenceEvidence(Path(directory))
            evidence.started('a' * 32, {}, request_body=dict(body='original'))
            path = Path(directory) / 'dispatches' / ('a' * 32 + '.json')
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                evidence.started('a' * 32, {}, request_body=dict(body='replacement'))
            self.assertEqual(path.read_bytes(), original)
