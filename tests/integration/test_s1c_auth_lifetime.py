# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""S1c authentication lifetime and safe browser reopen acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import CommandBroker, LocalApiServer, TwinPulseProcessManager  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class S1cAuthLifetimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.server = LocalApiServer(
            CommandBroker(clock=self.clock),
            product_bootstrap_secret="p" * 43,
            engine_bootstrap_secret="e" * 43,
            bootstrap_ttl_s=30.0,
            session_idle_ttl_s=10.0,
            session_absolute_ttl_s=25.0,
            clock=self.clock,
        )
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def request(
        self,
        path: str,
        body: object | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], object]:
        data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
        selected = {"Accept": "application/json"}
        if data is not None:
            selected["Content-Type"] = "application/json"
        if headers:
            selected.update(headers)
        request = Request(
            self.server.base_url + path,
            data=data,
            headers=selected,
            method="POST" if data is not None else "GET",
        )
        try:
            with urlopen(request, timeout=3.0) as response:
                return response.status, json.loads(response.read()), response.headers
        except HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def bootstrap_product(self) -> tuple[str, str, object]:
        status, result, headers = self.request(
            "/v1/bootstrap", {"role": "product", "secret": "p" * 43},
        )
        self.assertEqual(status, 200)
        return headers.get("Set-Cookie").split(";", 1)[0], str(result["csrf_token"]), headers

    def test_active_session_renews_idle_but_never_crosses_absolute_lifetime(self) -> None:
        cookie, csrf, headers = self.bootstrap_product()
        self.assertIn("Max-Age=25", headers.get("Set-Cookie"))

        self.clock.advance(9.0)
        status, first, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(first["csrf_token"], csrf)
        self.assertEqual(first["idle_expires_in_s"], 10)
        self.assertEqual(first["absolute_expires_in_s"], 16)

        self.clock.advance(9.0)
        status, second, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(second["idle_expires_in_s"], 7)
        self.assertEqual(second["absolute_expires_in_s"], 7)

        self.clock.advance(7.0)
        status, result, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "session_rejected")

    def test_new_tab_can_recover_csrf_from_http_only_cookie_without_reusing_bootstrap(self) -> None:
        cookie, csrf, _ = self.bootstrap_product()
        status, reopened, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(reopened["role"], "product")
        self.assertEqual(reopened["csrf_token"], csrf)

        status, replay, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": "p" * 43},
        )
        self.assertEqual(status, 401)
        self.assertEqual(replay["error"]["code"], "bootstrap_rejected")

    def test_idle_expiry_rejects_reopen_and_post_still_requires_csrf(self) -> None:
        cookie, csrf, _ = self.bootstrap_product()
        status, result, _ = self.request(
            "/v1/product/lease", {}, headers={"Cookie": cookie},
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"]["code"], "csrf_rejected")

        status, _result, _ = self.request(
            "/v1/product/lease", {},
            headers={"Cookie": cookie, "X-TwinPulse-CSRF": csrf},
        )
        self.assertEqual(status, 200)

        self.clock.advance(11.0)
        status, result, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "session_rejected")

    def test_owner_can_mint_a_replacement_one_time_bootstrap_after_expiry(self) -> None:
        cookie, _csrf, _ = self.bootstrap_product()
        self.clock.advance(11.0)
        status, _expired, _ = self.request("/v1/product/session", headers={"Cookie": cookie})
        self.assertEqual(status, 401)

        status, issued, _ = self.request(
            "/v1/bootstrap/product/issue", {"owner_secret": "p" * 43},
        )
        self.assertEqual(status, 200)
        ticket = str(issued["bootstrap_secret"])
        self.assertNotEqual(ticket, "p" * 43)

        status, _new_session, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": ticket},
        )
        self.assertEqual(status, 200)
        status, replay, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": ticket},
        )
        self.assertEqual(status, 401)
        self.assertEqual(replay["error"]["code"], "bootstrap_rejected")

    def test_process_owner_mints_ticket_without_putting_owner_secret_in_url(self) -> None:
        manager = TwinPulseProcessManager(
            repo_root=ROOT,
            state_dir=ROOT / "artifacts" / "s1c-manager-test-unused",
            python_executable=Path(sys.executable),
            isaac_python=Path(sys.executable),
        )
        manager._product_secret = "p" * 43
        ticket = manager._issue_product_bootstrap(self.server.base_url)
        self.assertNotEqual(ticket, manager._product_secret)

        status, _new_session, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": ticket},
        )
        self.assertEqual(status, 200)

    def test_reopening_same_app_preserves_other_tabs_csrf_and_absolute_expiry(self) -> None:
        cookie, csrf, _ = self.bootstrap_product()
        self.clock.advance(4)
        status, issued, _ = self.request('/v1/bootstrap/product/issue', {'owner_secret': 'p'*43})
        self.assertEqual(status, 200)
        ticket = issued['bootstrap_secret']
        status, result, headers = self.request('/v1/bootstrap', {'role': 'product', 'secret': ticket}, headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Set-Cookie').split(';',1)[0], cookie)
        self.assertEqual(result['csrf_token'], csrf)
        self.assertIn('Max-Age=21', headers.get('Set-Cookie'))
        status, _, _ = self.request('/v1/product/lease', {}, headers={'Cookie':cookie,'X-TwinPulse-CSRF':csrf})
        self.assertEqual(status, 200)
        status, _, _ = self.request('/v1/bootstrap', {'role':'product','secret':ticket}, headers={'Cookie':cookie})
        self.assertEqual(status, 401)

    def test_expired_cookie_is_not_reused_when_reopening(self) -> None:
        cookie, csrf, _ = self.bootstrap_product(); self.clock.advance(11)
        _, issued, _ = self.request('/v1/bootstrap/product/issue', {'owner_secret':'p'*43})
        status, result, headers = self.request('/v1/bootstrap', {'role':'product','secret':issued['bootstrap_secret']}, headers={'Cookie':cookie})
        self.assertEqual(status, 200)
        self.assertNotEqual(headers.get('Set-Cookie').split(';',1)[0], cookie)
        self.assertNotEqual(result['csrf_token'], csrf)

    def test_two_pending_window_tickets_are_independent_and_each_one_use(self) -> None:
        _, first, _ = self.request('/v1/bootstrap/product/issue', {'owner_secret':'p'*43})
        _, second, _ = self.request('/v1/bootstrap/product/issue', {'owner_secret':'p'*43})
        status, result, headers = self.request('/v1/bootstrap', {'role':'product','secret':first['bootstrap_secret']})
        self.assertEqual(status, 200)
        cookie=headers.get('Set-Cookie').split(';',1)[0]
        status, reopened, _ = self.request('/v1/bootstrap', {'role':'product','secret':second['bootstrap_secret']}, headers={'Cookie':cookie})
        self.assertEqual(status, 200); self.assertEqual(reopened['csrf_token'], result['csrf_token'])
        for ticket in (first['bootstrap_secret'],second['bootstrap_secret']):
            status, _, _ = self.request('/v1/bootstrap', {'role':'product','secret':ticket}, headers={'Cookie':cookie})
            self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
