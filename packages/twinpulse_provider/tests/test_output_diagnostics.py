# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No HTTP: response-pattern metrics and original saved-failure regressions."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from twinpulse_provider.output_diagnostics import output_diagnostics
from twinpulse_provider.reliability import InferenceEvidence
from twinpulse_core.execution_diagnostics import metadata


def wire(content, finish='stop', reasoning='', reasoning_tokens=None):
    return dict(choices=[dict(finish_reason=finish, message=dict(
        content=content, reasoning_content=reasoning))], usage=dict(
            completion_tokens=20000, completion_tokens_details=dict(reasoning_tokens=reasoning_tokens)))


class OutputDiagnosticsTests(unittest.TestCase):
    def test_empty_final_reasoning_and_visible_whitespace_are_distinct(self):
        hidden=output_diagnostics(wire('', 'length', 'private reasoning', 20000))
        self.assertEqual(hidden['output_pattern'],'hidden_reasoning_without_final_at_limit')
        self.assertTrue(hidden['final_empty']);self.assertEqual(hidden['reasoning_tokens'],20000)
        visible=output_diagnostics(wire('{"x":'+' '*10000,'length'))
        self.assertEqual(visible['output_pattern'],'visible_whitespace_dominated_at_limit')
        self.assertEqual(visible['visible_trailing_whitespace_chars'],10000)
        self.assertEqual(visible['visible_nonwhitespace_chars'],5)
        self.assertNotIn('private reasoning',json.dumps(hidden))

    def test_stop_at_requested_count_is_not_truncation_or_a_quality_pass(self):
        value=output_diagnostics(wire('{"x":1}'))
        self.assertEqual(value['output_pattern'],'final_output_present')
        self.assertEqual(value['finish_reason'],'stop')
        self.assertNotIn('quality',value);self.assertNotIn('status',value)

    def test_malformed_envelopes_and_token_counters_are_non_authoritative(self):
        for value in (None,[],{},dict(choices=None),dict(choices=[{}]),dict(choices=[{},{}])):
            self.assertEqual(output_diagnostics(value),{})
        for tokens in (True,-1,'20000',None):
            self.assertNotIn('reasoning_tokens',output_diagnostics(wire('',reasoning_tokens=tokens)))
        self.assertEqual(output_diagnostics(wire(''))['output_pattern'],'empty_final_without_length')

    def test_diagnostic_fields_are_allowed_but_content_remains_private(self):
        values=output_diagnostics(wire('{', 'length'))
        self.assertEqual(metadata(values),values)
        self.assertNotIn('content',metadata({**values,'content':'private prompt'}))

    def test_capture_keeps_larger_reasoning_raw_and_redacts_secret_and_image(self):
        with TemporaryDirectory() as directory:
            raw=json.dumps(dict(reasoning='x'*300000,api_key='canary',
                image='data:image/jpeg;base64,YWJj')).encode()
            evidence=InferenceEvidence(Path(directory))
            evidence.save('a'*32,{},raw,secret='canary')
            item=json.loads((Path(directory)/('a'*32+'.json')).read_text())
            self.assertFalse(item['response_truncated'])
            self.assertEqual(item['captured_byte_count'],len(raw))
            self.assertNotIn('canary',item['response_redacted'])
            self.assertNotIn('YWJj',item['response_redacted'])
            self.assertEqual(item['response_sha256'],hashlib.sha256(raw).hexdigest())

    def test_capture_remains_bounded(self):
        from twinpulse_provider.nebius_pipeline import MAX_RESPONSE_BYTES
        with TemporaryDirectory() as directory:
            evidence=InferenceEvidence(Path(directory));raw=b'x'*(MAX_RESPONSE_BYTES+1)
            evidence.save('a'*32,{},raw)
            item=json.loads((Path(directory)/('a'*32+'.json')).read_text())
            self.assertTrue(item['response_truncated'])
            self.assertEqual(item['captured_byte_count'],MAX_RESPONSE_BYTES)

    def test_saved_actual_failures_have_distinct_patterns_without_mutation(self):
        root=Path(__file__).resolve().parents[3]
        paths=[root/'outputs/model-role-comparison-20261010/cases/planner-nebius-5b5610a7004a-r2/evidence/66b6df05fbd64b3c9d856a5d3a9b7023.json',
            root/'outputs/benchmark-overnight-20261011/campaign-407/86cc4651fc36cb753bb312f9c3e02691/run-1/runtime/provider-evidence/464510ccd47640fb845c20d70656feec.json']
        if not all(p.is_file() for p in paths):self.skipTest('Historical private evidence not in portable package')
        expected=['visible_whitespace_dominated_at_limit','hidden_reasoning_without_final_at_limit']
        for path,pattern in zip(paths,expected):
            original=path.read_bytes();record=json.loads(original)
            self.assertFalse(record['response_truncated'])
            result=output_diagnostics(json.loads(record['response_redacted']))
            self.assertEqual(result['output_pattern'],pattern)
            self.assertEqual(result['finish_reason'],'length')
            self.assertEqual(path.read_bytes(),original)
