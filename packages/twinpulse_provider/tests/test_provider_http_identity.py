# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Honest User-Agent and bounded provider error summaries; injected openers, no network."""
from __future__ import annotations

import email.message
import io
import json
import os
from pathlib import Path
import ssl
import sys
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_core" / "src"))
sys.path.insert(0, str(PACKAGE_ROOT / "twinpulse_provider" / "src"))

from twinpulse_provider import (  # noqa: E402
    CancellationToken,
    GenerationRequest,
    OpenAIResponsesProvider,
    ProviderAuthenticationError,
    ProviderCapabilities,
    ProviderConfig,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
    StructuredJsonHttpProvider,
    UrllibChatCompletionsTransport,
)
from twinpulse_provider.http_identity import json_headers, user_agent  # noqa: E402
from twinpulse_provider.reliability import (  # noqa: E402
    provider_connection_error, provider_error_summary, provider_http_error, public_provider_error)


KEY = "sk-proj-" + "Q7" * 20  # synthetic credential shape, never a real key
TOKEN = "tok_live_" + "Z9" * 12
BLOCK_PAGE = ("<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"UTF-8\"/>\n<title>외부사이트 차단</title>\n"
              "<style>body{color:red}</style>\n</head>\n<body><p>Blocked for user user0042 at 10.1.2.3</p>"
              "<script>var policy='internal';</script></body>\n</html>\n").encode("utf-8")


def http_error(status, body=b"", content_type="application/json"):
    headers = email.message.Message()
    headers["Content-Type"] = content_type
    return urllib.error.HTTPError("https://provider.example.invalid/v1/x", status, "failed", headers, io.BytesIO(body))


def openai_error(message, *, kind="invalid_request_error", code=None, param=None):
    return json.dumps({"error": {"message": message, "type": kind, "code": code, "param": param}}).encode()


def config(endpoint="chat/completions"):
    return ProviderConfig(base_url="https://provider.example.invalid/v1/", endpoint_path=endpoint,
        model_id="fixture-model", api_key_env="TWINPULSE_FIXTURE_PROVIDER_KEY",
        capabilities=ProviderCapabilities(True, True, 1), timeout_s=1.0)


class UserAgentTests(unittest.TestCase):
    def test_release_version_or_dev_and_never_a_browser_or_machine_identity(self):
        with patch.dict(os.environ, {"TWINPULSE_RELEASE_VERSION": "0.1.0a1"}):
            self.assertEqual(user_agent(), "TwinPulse/0.1.0a1")
        with patch.dict(os.environ, {"TWINPULSE_RELEASE_VERSION": "1.2.3+local-4"}):
            self.assertEqual(user_agent(), "TwinPulse/1.2.3+local-4")
        for bad in ("", "1.0 (Windows NT 10.0; user0042)", "Mozilla/5.0", "1.0\n", "v" * 41, "1.0;host=PC-B"):
            with self.subTest(version=bad), patch.dict(os.environ, {"TWINPULSE_RELEASE_VERSION": bad}):
                self.assertEqual(user_agent(), "TwinPulse/dev")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(user_agent(), "TwinPulse/dev")
        self.assertEqual(json_headers(), {"User-Agent": user_agent(), "Accept": "application/json"})

    def check(self, request):
        self.assertTrue(request.get_header("User-agent").startswith("TwinPulse/"))
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
        # The real opener keeps it: urllib adds its Python-urllib default only when no User-Agent is set.
        handler = next(h for h in urllib.request.build_opener().handlers if isinstance(h, urllib.request.HTTPSHandler))
        prepared = handler.do_request_(request)
        self.assertTrue(prepared.get_header("User-agent").startswith("TwinPulse/"))
        self.assertNotIn("Python-urllib", json.dumps(prepared.header_items()))

    def test_chat_completions_request_names_twinpulse_and_accepts_json(self):
        seen = []
        def opener(request, timeout):
            seen.append(request)
            raise http_error(503)
        transport = UrllibChatCompletionsTransport(lambda: KEY, opener=opener)
        with self.assertRaises(ProviderUnavailableError):
            transport._post({"model": "fixture-model"}, CancellationToken(), config(), KEY)
        self.check(seen[0])

    def test_both_providers_py_paths_name_twinpulse_and_never_redirect_the_key(self):
        seen = []
        def urlopen(request, timeout):
            seen.append(request)
            raise http_error(503)
        with patch.dict(os.environ, {"TWINPULSE_FIXTURE_PROVIDER_KEY": KEY}), \
                patch("twinpulse_provider.providers.urllib.request.urlopen", side_effect=urlopen):
            import asyncio
            with self.assertRaises(urllib.error.HTTPError):  # this gateway keeps its own status mapping
                asyncio.run(StructuredJsonHttpProvider().generate(GenerationRequest("r1", "Scene"),
                                                                  CancellationToken(), config("generate")))
            with self.assertRaises(ProviderUnavailableError):
                asyncio.run(OpenAIResponsesProvider(lambda: KEY).generate(GenerationRequest("r2", "Scene"),
                                                                          CancellationToken(), config("responses")))
        self.assertEqual(len(seen), 2)
        for request in seen:
            with self.subTest(url=request.full_url):
                self.check(request)
                redirected = urllib.request.HTTPRedirectHandler().redirect_request(
                    request, None, 302, "Found", {}, "https://elsewhere.example.invalid/")
                self.assertIsNone(redirected.get_header("Authorization"))
                self.assertTrue(redirected.get_header("User-agent").startswith("TwinPulse/"))


class ProviderErrorSummaryTests(unittest.TestCase):
    def test_openai_json_400_shows_reason_without_key_or_bearer_token(self):
        body = openai_error("Invalid schema for response_format 'plan': 'additionalProperties' is required to be "
                            f"supplied and to be false. Key {KEY}; Authorization: Bearer {TOKEN}; other sk-abcdefgh12345678",
                            param="response_format")
        failure = provider_http_error(http_error(400, body), secret=KEY)
        self.assertIs(type(failure), ProviderRequestError)
        self.assertEqual(failure.http_status, 400)
        text = str(failure)
        self.assertTrue(text.startswith("provider request failed (400): invalid_request_error: Invalid schema"))
        self.assertLessEqual(len(text), len("provider request failed (400): ") + 200)
        for secret in (KEY, TOKEN, "sk-abcdefgh12345678"):
            self.assertNotIn(secret, text)
            self.assertNotIn(secret, json.dumps(failure.provider_error))
        self.assertEqual({k: failure.provider_error[k] for k in ("kind", "type", "param")},
                         {"kind": "json_error", "type": "invalid_request_error", "param": "response_format"})
        self.assertNotIn("code", failure.provider_error)  # null code is omitted
        self.assertLessEqual(len(failure.provider_error["message"]), 300)
        self.assertEqual(failure.raw_error_body, body)  # private evidence keeps the complete body

    def test_html_503_block_page_shows_only_its_title(self):
        failure = provider_http_error(http_error(503, BLOCK_PAGE, "text/html; charset=UTF-8"), secret=KEY)
        self.assertIs(type(failure), ProviderUnavailableError)
        self.assertEqual(str(failure), "provider unavailable (503): HTML page '외부사이트 차단'")
        self.assertEqual(failure.provider_error, {"kind": "html_page", "title": "외부사이트 차단"})
        self.assertNotIn("user0042", str(failure) + json.dumps(failure.provider_error, ensure_ascii=False))

    def test_html_401_or_403_is_not_an_api_key_rejection_but_json_is(self):
        for status in (401, 403):
            with self.subTest(status=status):
                failure = provider_http_error(http_error(status, BLOCK_PAGE, "text/html"), secret=KEY)
                self.assertIs(type(failure), ProviderRequestError)
                self.assertNotIsInstance(failure, ProviderAuthenticationError)
                self.assertEqual(failure.http_status, status)
                self.assertEqual(str(failure), f"provider request failed ({status}): HTML page '외부사이트 차단'")
                rejected = provider_http_error(http_error(status, openai_error(
                    "Incorrect API key provided.", code="invalid_api_key")), secret=KEY)
                self.assertIs(type(rejected), ProviderAuthenticationError)
                self.assertIn("invalid_request_error/invalid_api_key: Incorrect API key provided.", str(rejected))

    def test_empty_bodies_keep_their_types_and_rate_limits_explain_quota(self):
        for status, expected in ((401, ProviderAuthenticationError), (429, ProviderRateLimitError),
                                 (503, ProviderUnavailableError), (302, ProviderRequestError), (400, ProviderRequestError)):
            with self.subTest(status=status):
                failure = provider_http_error(urllib.error.HTTPError("u", status, "x", {}, None))
                self.assertIs(type(failure), expected)
                self.assertTrue(str(failure).endswith(f"({status})"))
                self.assertEqual(failure.provider_error, {"kind": "unparsed", "bytes": 0})
        quota = provider_http_error(http_error(429, openai_error("You exceeded your current quota.",
            kind="insufficient_quota", code="insufficient_quota")))
        self.assertEqual(str(quota), "provider rate limit (429): insufficient_quota: You exceeded your current quota.")

    def test_fallbacks_never_echo_the_request_and_unknown_bodies_are_only_counted(self):
        fastapi = json.dumps({"detail": [{"type": "missing", "loc": ["body", "prompt"], "msg": "Field required",
                                          "input": {"prompt": "PRIVATE USER PROMPT"}}]}).encode()
        self.assertEqual(provider_error_summary(fastapi), {"kind": "json_error", "message": "Field required"})
        self.assertEqual(provider_error_summary(b'{"detail":"Not authenticated"}'),
                         {"kind": "json_error", "message": "Not authenticated"})
        plain = b"upstream connect error PRIVATE"
        self.assertEqual(provider_error_summary(plain), {"kind": "unparsed", "bytes": len(plain)})
        self.assertEqual(provider_error_summary(b"{}"), {"kind": "unparsed", "bytes": 2})
        failure = provider_http_error(http_error(502, plain, "text/plain"))
        self.assertEqual(str(failure), f"provider unavailable (502): unrecognized body ({len(plain)} bytes)")

    def test_declared_charset_decodes_a_non_utf8_block_page_title(self):
        page = "<html><head><title>접근 차단 &amp; 안내</title></head></html>".encode("euc-kr")
        self.assertEqual(provider_error_summary(page, content_type="text/html; charset=euc-kr"),
                         {"kind": "html_page", "title": "접근 차단 & 안내"})
        meta = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=euc-kr">' + \
            "<title>차단</title>".encode("euc-kr")
        self.assertEqual(provider_error_summary(meta)["title"], "차단")

    def test_public_copy_revalidates_typed_fields_and_caps_text(self):
        public = public_provider_error({"kind": "json_error", "code": "C" * 81, "type": "bad type!",
            "param": "messages[0].content", "message": "m " * 400 + KEY, "raw": "PRIVATE", "title": "x"})
        self.assertEqual(set(public), {"kind", "param", "message"})
        self.assertLessEqual(len(public["message"]), 300)
        self.assertEqual(public_provider_error({"kind": "html_page", "title": "Bearer abc " + "t" * 300,
                                                "message": "PRIVATE"}), {"kind": "html_page", "title": (
            "Bearer [REDACTED] " + "t" * 300)[:117] + "..."})
        self.assertEqual(public_provider_error({"kind": "unparsed", "bytes": True}), {"kind": "unparsed"})
        for invalid in (None, "html_page", {"kind": "request"}, {"title": "x"}):
            self.assertIsNone(public_provider_error(invalid))

    def test_connection_failure_names_the_reason_type_with_a_short_redacted_reason(self):
        failure = provider_connection_error(urllib.error.URLError(ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate")))
        self.assertIs(type(failure), ProviderRequestError)
        self.assertIn("provider connection failed (SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]", str(failure))
        long = provider_connection_error(urllib.error.URLError(OSError("proxy https://user:pw@proxy.invalid " + KEY + " x" * 200)),
                                         secret=KEY)
        reason = str(long).split("(OSError: ", 1)[1][:-1]
        self.assertLessEqual(len(reason), 160)
        self.assertNotIn(KEY, str(long))
        self.assertNotIn("user:pw", str(long))
        self.assertEqual(str(provider_connection_error(urllib.error.URLError("unknown url type: ftp"))),
                         "provider connection failed (URLError: unknown url type: ftp)")

    def test_chat_transport_maps_errors_once_and_an_unreadable_body_is_tolerated(self):
        class Broken(io.BytesIO):
            def read(self, *args):
                raise OSError("connection reset while reading the error body")
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 400, "failed", {}, Broken())
        transport = UrllibChatCompletionsTransport(lambda: KEY, opener=opener)
        with self.assertRaises(ProviderRequestError) as caught:
            transport._post({"model": "fixture-model"}, CancellationToken(), config(), KEY)
        self.assertEqual(str(caught.exception), "provider request failed (400)")
        self.assertEqual((caught.exception.raw_error_body, caught.exception.http_status), (b"", 400))
        def refused(request, timeout):
            raise urllib.error.URLError(ConnectionRefusedError(10061, "actively refused"))
        with self.assertRaisesRegex(ProviderRequestError, r"^provider connection failed \(ConnectionRefusedError: "):
            UrllibChatCompletionsTransport(lambda: KEY, opener=refused)._post(
                {"model": "fixture-model"}, CancellationToken(), config(), KEY)


if __name__ == "__main__":
    unittest.main()
