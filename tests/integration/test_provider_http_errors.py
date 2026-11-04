# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Readable provider and onboarding HTTP errors through real product code; injected HTTP only.

Supplementary: no live provider, network filter, Windows or Isaac run is involved.
"""
import email.message
import http.client
import io
import json
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from tests.integration.test_provider_key_registry import Credential
from packages.twinpulse_provider.tests.test_nebius_pipeline import config, OBSERVER_MODEL, PLANNER_MODEL
from twinpulse_app import CommandBroker, LocalApiServer
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.credentials import DEFAULT_CREDENTIAL_TARGET
from twinpulse_app.key_registry import KeyRegistry, KeyRegistryError
from twinpulse_app.product_workflow_service import _public_generation_diagnostics, _public_generation_error
from twinpulse_app.provider_onboarding import RejectRedirects, configure_first_nebius_key, metadata
from twinpulse_app.settings import JsonProviderSettingsStore, provider_settings_preset
from twinpulse_app.stage_routing import StageRoutingSettings
from twinpulse_provider import (CancellationToken, GenerationRequest, GenerationService, NebiusChatCompletionsPipelineProvider,
    OpenAIResponsesProvider, ProviderRequestError, UrllibChatCompletionsTransport)
from twinpulse_provider.errors import ProviderError
from twinpulse_provider.reliability import AuditedChatTransport, InferenceEvidence

KEY = 'sk-proj-' + 'K3' * 20  # synthetic credential shape, never a real key
TOKEN = 'tok_live_' + 'Z9' * 12
MODELS = 'https://api.tokenfactory.nebius.com/v1/models'
SCHEMA_400 = json.dumps({'error': {'message': "Invalid schema for response_format 'twinpulse_site_tool_plan_v2': "
    "In context=('properties', 'parameters'), 'additionalProperties' is required to be supplied and to be false. "
    f'Request had Authorization: Bearer {TOKEN} and key {KEY}.', 'type': 'invalid_request_error',
    'param': 'response_format', 'code': None}}).encode()
BLOCK_PAGE = ('<!DOCTYPE html>\n<html>\n<head>\n<meta charset="UTF-8"/>\n<title>외부사이트 차단</title>\n<style>p{}</style>\n'
              '</head>\n<body><p>Blocked for user user0042 at 10.1.2.3</p></body>\n</html>\n').encode('utf-8')


def http_error(status, body=b'', content_type='application/json'):
    headers = email.message.Message()
    headers['Content-Type'] = content_type
    return urllib.error.HTTPError('https://provider.example.invalid/v1/x', status, 'failed', headers, io.BytesIO(body))


def raising(error_factory, seen=None):
    def opener(request, timeout):
        if seen is not None: seen.append(request)
        raise error_factory()
    return opener


class StagedProviderErrorTests(unittest.IsolatedAsyncioTestCase):
    async def public_failure(self, opener):
        provider = NebiusChatCompletionsPipelineProvider(UrllibChatCompletionsTransport(lambda: KEY, opener=opener),
            observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL, site_plan_version='2.2')
        with self.assertRaises(ProviderError) as caught:
            await GenerationService(provider, config(timeout_s=10), plan_version='2.2').generate(GenerationRequest('r', 'Bedroom'))
        return _public_generation_error(caught.exception)

    async def test_openai_style_400_reaches_the_public_error_with_its_reason_and_no_secret(self):
        seen = []
        public = await self.public_failure(raising(lambda: http_error(400, SCHEMA_400), seen))
        self.assertEqual(public['code'], 'provider_request_failed')
        self.assertTrue(public['message'].startswith(f'planner stage failed (model={PLANNER_MODEL}): provider request failed '
                                                     "(400): invalid_request_error: Invalid schema for response_format"))
        self.assertIn('additionalProperties', public['message'])
        attempt = public['diagnostics']['attempts'][0]
        self.assertEqual((attempt['status'], attempt['http_status']), ('rejected', 400))
        self.assertEqual({k: attempt['provider_error'][k] for k in ('kind', 'type', 'param')},
                         {'kind': 'json_error', 'type': 'invalid_request_error', 'param': 'response_format'})
        text = json.dumps(public)
        self.assertNotIn(KEY, text)
        self.assertNotIn(TOKEN, text)
        self.assertTrue(seen[0].get_header('User-agent').startswith('TwinPulse/'))

    async def test_filter_pages_report_their_title_not_an_outage_body_or_a_rejected_key(self):
        public = await self.public_failure(raising(lambda: http_error(503, BLOCK_PAGE, 'text/html; charset=UTF-8')))
        self.assertEqual(public['code'], 'provider_unavailable')
        self.assertTrue(public['message'].endswith("provider unavailable (503): HTML page '외부사이트 차단'"))
        self.assertEqual(public['diagnostics']['attempts'][0]['provider_error'], {'kind': 'html_page', 'title': '외부사이트 차단'})
        self.assertNotIn('user0042', json.dumps(public, ensure_ascii=False))
        public = await self.public_failure(raising(lambda: http_error(403, BLOCK_PAGE, 'text/html')))
        self.assertEqual(public['code'], 'provider_request_failed')  # not provider_authentication_failed
        self.assertEqual(public['diagnostics']['attempts'][0]['http_status'], 403)
        self.assertIn("provider request failed (403): HTML page '외부사이트 차단'", public['message'])


class PrivateEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_audited_transport_keeps_the_body_that_the_typed_mapping_already_read(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            transport = AuditedChatTransport(lambda: KEY, InferenceEvidence(root / 'private'),
                                             opener=raising(lambda: http_error(400, SCHEMA_400)))
            with self.assertRaises(ProviderRequestError) as caught:
                await transport.complete(dict(model=PLANNER_MODEL, max_tokens=100, response_format={}), CancellationToken(), config())
            self.assertIn('invalid_request_error', str(caught.exception))
            text = next((root / 'private').glob('*.json')).read_text(encoding='utf-8')
            saved = json.loads(text)
            self.assertEqual((saved['status'], saved['http_status'], saved['response_byte_count']), ('rejected', 400, len(SCHEMA_400)))
            self.assertIn("'additionalProperties' is required", saved['response_redacted'])
            self.assertNotIn(KEY, text)
            self.assertNotIn(TOKEN, text)

    async def audited_failure(self, root, opener):
        provider = NebiusChatCompletionsPipelineProvider(AuditedChatTransport(lambda: KEY, InferenceEvidence(root), opener=opener),
            observer_model_id=OBSERVER_MODEL, planner_model_id=PLANNER_MODEL, site_plan_version='2.2', max_repairs=1)
        with self.assertRaises(ProviderError) as caught:
            await GenerationService(provider, config(timeout_s=10), plan_version='2.2').generate(GenerationRequest('r', 'Bedroom'))
        return _public_generation_error(caught.exception), [json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.json')]

    async def test_a_2xx_filter_page_and_a_reset_stay_typed_through_the_audited_pipeline(self):
        # The charset is only in the HTTP header and the status is a proxy's 203: the audited capture passes both on.
        page_body = '<html><head><title>외부사이트 차단</title></head><body>user0042</body></html>'.encode('euc-kr')
        with TemporaryDirectory() as temp:
            seen = []
            def page(request, timeout):
                seen.append(request)
                response = Response(request.full_url, page_body, 'text/html; charset=euc-kr')
                response.status = 203
                return response
            public, saved = await self.audited_failure(Path(temp) / 'page', page)
            self.assertEqual(len(seen), 1)  # a filter page is not model output: no repair request is sent
            self.assertEqual(public['code'], 'provider_request_failed')
            self.assertTrue(public['message'].endswith("provider request failed (203): HTML page '외부사이트 차단'"))
            attempt = public['diagnostics']['attempts'][0]
            self.assertEqual((attempt['status'], attempt['http_status'], attempt['provider_error']),
                             ('rejected', 203, {'kind': 'html_page', 'title': '외부사이트 차단'}))
            self.assertEqual([(r['status'], r['http_status'], r['response_byte_count']) for r in saved],
                             [('rejected', 203, len(page_body))])
            self.assertNotIn('user0042', json.dumps(public, ensure_ascii=False))  # only the page title is public
            def reset(request, timeout):
                raise http.client.RemoteDisconnected('Remote end closed connection without response')
            public, saved = await self.audited_failure(Path(temp) / 'reset', reset)
            self.assertEqual(public['code'], 'provider_request_failed')  # was generation_failed without an attempt record
            self.assertIn('provider connection failed (RemoteDisconnected: ', public['message'])
            self.assertEqual(public['diagnostics']['attempts'][0]['status'], 'outcome_unknown')
            self.assertEqual([r['status'] for r in saved], ['outcome_unknown'])  # accounting keeps the unknown outcome

    async def test_responses_path_400_is_a_typed_request_failure_with_private_body(self):
        from packages.twinpulse_provider.tests.test_provider import config as responses_config
        with TemporaryDirectory() as temp:
            root = Path(temp)
            provider = OpenAIResponsesProvider(lambda: KEY, evidence=InferenceEvidence(root / 'private'))
            with patch('urllib.request.urlopen', side_effect=raising(lambda: http_error(400, SCHEMA_400))):
                with self.assertRaises(ProviderRequestError) as caught:
                    await provider.generate(GenerationRequest('request-1', 'Scene'), CancellationToken(), responses_config())
            public = _public_generation_error(caught.exception)
            self.assertEqual(public['code'], 'provider_request_failed')  # was a raw HTTPError: generation_failed
            self.assertTrue(public['message'].startswith('provider request failed (400): invalid_request_error: Invalid schema'))
            self.assertNotIn(KEY, json.dumps(public))
            saved = json.loads(next((root / 'private').glob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual((saved['status'], saved['http_status']), ('rejected', 400))
            self.assertIn('additionalProperties', saved['response_redacted'])


class PublicDiagnosticsTests(unittest.TestCase):
    def test_whitelist_keeps_only_typed_bounded_provider_error_fields(self):
        public = _public_generation_diagnostics({'stage': 'planner', 'http_status': 400, 'provider_error': {
                'kind': 'json_error', 'type': 'invalid_request_error', 'code': 'C' * 200, 'param': 'response_format',
                'message': 'bad schema ' + KEY, 'raw_body': 'PRIVATE'},
            'attempts': [{'stage': 'planner', 'http_status': 999, 'provider_error': {'kind': 'html_page', 'title': 'T', 'message': 'PRIVATE'}},
                         {'stage': 'planner', 'http_status': True, 'provider_error': {'kind': 'request', 'body': 'PRIVATE'}},
                         {'stage': 'planner', 'http_status': '400', 'provider_error': 'PRIVATE'}]})
        self.assertEqual(public['http_status'], 400)
        self.assertEqual(public['provider_error'], {'kind': 'json_error', 'type': 'invalid_request_error',
                                                    'param': 'response_format', 'message': 'bad schema [REDACTED]'})
        self.assertEqual(public['attempts'], [{'stage': 'planner', 'provider_error': {'kind': 'html_page', 'title': 'T'}},
                                              {'stage': 'planner'}, {'stage': 'planner'}])
        self.assertNotIn('PRIVATE', json.dumps(public))


class Response:
    def __init__(self, url, body, content_type='application/json'):
        self.url, self.body, self.headers = url, body, email.message.Message()
        self.headers['Content-Type'] = content_type
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, limit): return self.body[:limit]


class OnboardingHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup); Credential.secrets = {}
        self.registry = KeyRegistry(JsonProviderSettingsStore(Path(self.temp.name) / 'settings.json'),
                                    Credential(DEFAULT_CREDENTIAL_TARGET), Credential)
        self.seen = []

    def opener(self, outcome):
        seen = self.seen
        class Opener:
            def open(self, request, timeout):
                seen.append(request)
                if isinstance(outcome, BaseException): raise outcome
                return outcome
        return patch('twinpulse_app.provider_onboarding.urllib.request.build_opener', return_value=Opener())

    def failure(self, outcome):
        with self.opener(outcome), self.assertRaises(KeyRegistryError) as caught:
            metadata(MODELS, SimpleNamespace(load=lambda: KEY))
        self.assertNotIn(KEY, str(caught.exception))
        return caught.exception

    def test_metadata_get_names_twinpulse_and_accepts_json(self):
        with self.opener(Response(MODELS, b'{"data":[]}')):
            value, _ = metadata(MODELS, SimpleNamespace(load=lambda: KEY))
        self.assertEqual(value, {'data': []})
        self.assertTrue(self.seen[0].get_header('User-agent').startswith('TwinPulse/'))
        self.assertEqual(self.seen[0].get_header('Accept'), 'application/json')
        self.assertEqual(self.seen[0].get_header('Authorization'), 'Bearer ' + KEY)

    def test_blocked_503_page_is_reported_as_a_filter_page_and_the_key_is_kept(self):
        key = self.registry.register(dict(name='Nebius', provider_profile='nebius_token_factory',
            model_id=provider_settings_preset('nebius_token_factory').model_id, api_key=KEY))['entries'][-1]['id']
        with self.opener(http_error(503, BLOCK_PAGE, 'text/html; charset=UTF-8')), self.assertRaises(KeyRegistryError) as caught:
            configure_first_nebius_key(self.registry, key, lambda: None)
        self.assertEqual((caught.exception.code, caught.exception.status, caught.exception.metadata_gets), ('provider_blocked_page', 502, 1))
        self.assertIn("HTTP 503, '외부사이트 차단'", str(caught.exception))
        self.assertNotIn('user0042', str(caught.exception))
        self.assertFalse(StageRoutingSettings(self.registry).path.exists())
        self.assertTrue(self.registry.state()['entries'][-1]['configured'])

    def test_other_status_redirect_connection_and_html_200_failures_have_specific_codes(self):
        for outcome, code, status, text in (
                (http_error(500, b'{"detail":"boom"}'), 'provider_http_error', 502, '(HTTP 500).'),
                (http_error(401, b'{"detail":"Invalid token"}'), 'provider_http_error', 502, '키를 확인하세요'),
                (urllib.error.URLError(ConnectionRefusedError(10061, 'refused')), 'provider_unreachable', 503, 'ConnectionRefusedError'),
                (urllib.error.URLError(ssl.SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] x')),
                 'provider_unreachable', 503, 'SSLCertVerificationError'),
                (TimeoutError('timed out'), 'provider_unreachable', 503, 'TimeoutError'),
                (Response(MODELS, BLOCK_PAGE, 'text/html'), 'provider_blocked_page', 502, "HTTP 200, '외부사이트 차단'")):
            with self.subTest(code=code, text=text):
                error = self.failure(outcome)
                self.assertEqual((error.code, error.status), (code, status))
                self.assertIn(text, str(error))
        with self.assertRaises(KeyRegistryError) as caught:
            RejectRedirects().redirect_request(urllib.request.Request(MODELS), None, 302, 'Found', {}, 'https://filter.invalid/')
        self.assertEqual(caught.exception.code, 'provider_http_error')
        self.assertIn('HTTP 302', str(caught.exception))
        with self.opener(Response(MODELS, b'not json')), self.assertRaises(ValueError):  # unchanged generic path
            metadata(MODELS, SimpleNamespace(load=lambda: KEY))

    def test_api_onboarding_paths_show_the_specific_code_and_message(self):
        server = LocalApiServer(CommandBroker(), product_bootstrap_secret='p' * 40, engine_bootstrap_secret='e' * 40,
            provider_settings_store=self.registry.settings, credential_store=Credential(DEFAULT_CREDENTIAL_TARGET),
            key_registry=self.registry)
        self.addCleanup(server._httpd.server_close)
        with self.opener(http_error(503, BLOCK_PAGE, 'text/html; charset=UTF-8')):
            value = server._provider_keys({'action': 'register', 'name': 'Nebius', 'provider_profile': 'nebius_token_factory',
                'model_id': provider_settings_preset('nebius_token_factory').model_id, 'api_key': KEY})
        setup = value['default_setup']
        self.assertEqual((setup['state'], setup['code'], setup['metadata_gets'], value['network_called']),
                         ('unavailable', 'provider_blocked_page', 1, True))
        self.assertIn('외부사이트 차단', setup['message'])
        self.assertNotIn(KEY, json.dumps(value, ensure_ascii=False))
        with self.opener(urllib.error.URLError(ConnectionResetError(10054, 'reset'))), self.assertRaises(BrokerError) as caught:
            server._provider_keys({'action': 'refresh_catalog', 'key_id': value['entries'][-1]['id']})
        self.assertEqual((caught.exception.code, caught.exception.status), ('provider_unreachable', 503))
        self.assertIn('ConnectionResetError', str(caught.exception))  # not the generic key_settings_unavailable text


if __name__ == '__main__':
    unittest.main()
