# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""R4 loopback API, security, deduplication, and broker acceptance."""

from __future__ import annotations

import json
import os
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

from twinpulse_app import BrokerError, CommandBroker, LocalApiServer  # noqa: E402
from twinpulse_core import (  # noqa: E402
    CommandReceipt,
    ENGINE_SCHEMA_VERSION,
    SimulationSnapshot,
    fixed_warehouse_bundle,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class R4ApiTests(unittest.TestCase):
    def test_local_transport_accepts_bursts_without_expanding_bind_or_authority(self):
        self.assertEqual(self.server._httpd.request_queue_size,64)
        self.assertEqual(self.server._httpd.server_address[0],'127.0.0.1')
        self.assertEqual(self.request('/v1/product/state')[0],401)

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.broker = CommandBroker(clock=self.clock)
        self.artifact = self.broker.register_artifact("fixed_warehouse_v1", fixed_warehouse_bundle())
        self.product_secret = "p" * 43
        self.engine_secret = "e" * 43
        self.server = LocalApiServer(
            self.broker,
            product_bootstrap_secret=self.product_secret,
            engine_bootstrap_secret=self.engine_secret,
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
        method: str | None = None,
        raw: bytes | None = None,
    ) -> tuple[int, dict[str, object], object]:
        data = raw if raw is not None else (
            json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        )
        selected = {"Accept": "application/json"}
        if data is not None:
            selected["Content-Type"] = "application/json"
        if headers:
            selected.update(headers)
        request = Request(
            self.server.base_url + path, data=data, headers=selected,
            method=method or ("POST" if data is not None else "GET"),
        )
        try:
            with urlopen(request, timeout=3.0) as response:
                return response.status, json.loads(response.read()), response.headers
        except HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def bootstrap(self) -> tuple[str, str, str]:
        status, product, headers = self.request(
            "/v1/bootstrap", {"role": "product", "secret": self.product_secret},
        )
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie").split(";", 1)[0]
        csrf = product["csrf_token"]
        status, engine, _ = self.request(
            "/v1/bootstrap",
            {
                "role": "engine", "secret": self.engine_secret,
                "engine_session_id": "engine-1", "stage_epoch": "stage-1",
            },
        )
        self.assertEqual(status, 200)
        return cookie, csrf, engine["session_token"]

    def test_secure_bootstrap_roles_host_origin_csrf_and_single_use(self) -> None:
        status, result, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": self.product_secret},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"]["code"], "origin_forbidden")

        cookie, csrf, engine_token = self.bootstrap()
        status, result, _ = self.request(
            "/v1/bootstrap", {"role": "product", "secret": self.product_secret},
        )
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "bootstrap_rejected")

        status, result, _ = self.request(
            "/v1/product/lease", {}, headers={"Cookie": cookie},
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"]["code"], "csrf_rejected")
        status, _result, _ = self.request(
            "/v1/product/lease", {},
            headers={"Authorization": f"Bearer {engine_token}", "X-TwinPulse-CSRF": csrf},
        )
        self.assertEqual(status, 401)
        status, result, _ = self.request(
            "/v1/product/state", headers={"Cookie": cookie, "Host": "evil.example"}, method="GET",
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"]["code"], "host_forbidden")

    def test_command_dedup_revision_receipt_snapshot_and_state(self) -> None:
        cookie, csrf, engine_token = self.bootstrap()
        product_headers = {"Cookie": cookie, "X-TwinPulse-CSRF": csrf}
        engine_headers = {"Authorization": f"Bearer {engine_token}"}
        status, lease, _ = self.request("/v1/product/lease", {}, headers=product_headers)
        self.assertEqual(status, 200)
        status, heartbeat, _ = self.request(
            "/v1/engine/heartbeat",
            {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 200)
        self.assertTrue(heartbeat["lease_valid"])
        self.assertEqual(heartbeat["control_lease_id"], lease["control_lease_id"])

        request = {
            "client_request_id": "build-1", "command_type": "build_scene",
            "artifact_id": "fixed_warehouse_v1",
            "expected_applied_revision": self.artifact.revision,
        }
        status, first, _ = self.request("/v1/product/commands", request, headers=product_headers)
        self.assertEqual(status, 202)
        status, duplicate, _ = self.request("/v1/product/commands", request, headers=product_headers)
        self.assertEqual(status, 202)
        self.assertEqual(first["command_id"], duplicate["command_id"])
        conflict = dict(request)
        conflict["expected_applied_revision"] = "f" * 64
        status, result, _ = self.request("/v1/product/commands", conflict, headers=product_headers)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "duplicate_request_conflict")

        status, claimed, _ = self.request(
            "/v1/engine/claim", {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 200)
        command = claimed["command"]
        self.assertEqual(command["schema_version"], ENGINE_SCHEMA_VERSION)
        self.assertEqual(command["payload"]["bundle_sha256"], self.artifact.revision)
        receipt = CommandReceipt(
            command_id=command["command_id"], command_type="build_scene",
            project_id="default", engine_session_id="engine-1", stage_epoch="stage-1",
            status="succeeded", applied_revision=self.artifact.revision,
            build_fingerprint="b" * 64,
        )
        status, _result, _ = self.request(
            "/v1/engine/receipt", {"receipt": receipt.to_dict()}, headers=engine_headers,
        )
        self.assertEqual(status, 200)
        status, _result, _ = self.request(
            "/v1/engine/receipt", {"receipt": receipt.to_dict()}, headers=engine_headers,
        )
        self.assertEqual(status, 200)
        snapshot = SimulationSnapshot(
            engine_session_id="engine-1", stage_epoch="stage-1", project_id="default",
            applied_revision=self.artifact.revision, run_id=None, sequence=1,
            runtime_state="built", safety_state=None, safety_reason=None,
            permitted_commands=("build_scene", "run", "reset", "get_state"),
            capabilities=("simulation",), telemetry_available=False,
        )
        status, _result, _ = self.request(
            "/v1/engine/snapshot", {"snapshot": snapshot.to_dict()}, headers=engine_headers,
        )
        self.assertEqual(status, 200)
        status, _result, _ = self.request(
            "/v1/engine/snapshot", {"snapshot": snapshot.to_dict()}, headers=engine_headers,
        )
        self.assertEqual(status, 200)
        status, state, _ = self.request("/v1/product/state", headers={"Cookie": cookie}, method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(state["snapshot"]["applied_revision"], self.artifact.revision)
        self.assertEqual(state["engine_readiness"]["legacy_scene_build"]["code"], "ready")
        self.assertEqual(state["engine_readiness"]["site_scene_build_v2"]["code"],
                         "capability_unavailable")
        self.assertEqual(state["operations"][0]["status"], "succeeded")

    def test_lease_conflict_expiry_old_session_and_stage_transition(self) -> None:
        cookie, csrf, engine_token = self.bootstrap()
        headers = {"Cookie": cookie, "X-TwinPulse-CSRF": csrf}
        status, lease, _ = self.request("/v1/product/lease", {}, headers=headers)
        self.assertEqual(status, 200)
        with self.assertRaisesRegex(BrokerError, "Another product session"):
            self.broker.acquire_lease("second-writer")
        self.clock.advance(3.1)
        with self.assertRaisesRegex(BrokerError, "invalid or expired"):
            self.broker.renew_lease("ignored", lease["control_lease_id"])

        engine_headers = {"Authorization": f"Bearer {engine_token}"}
        status, result, _ = self.request(
            "/v1/engine/stage",
            {
                "engine_session_id": "engine-1", "current_stage_epoch": "stage-1",
                "new_stage_epoch": "stage-2",
            }, headers=engine_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["stage_epoch"], "stage-2")
        status, result, _ = self.request(
            "/v1/engine/heartbeat",
            {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "engine_identity_mismatch")
        self.broker.register_engine("engine-2", "stage-new")
        with self.assertRaisesRegex(BrokerError, "not current"):
            self.broker.engine_heartbeat("engine-1", "stage-2")

    def test_queued_command_can_be_cancelled_but_claimed_command_cannot(self) -> None:
        cookie, csrf, engine_token = self.bootstrap()
        product_headers = {"Cookie": cookie, "X-TwinPulse-CSRF": csrf}
        engine_headers = {"Authorization": f"Bearer {engine_token}"}
        status, _lease, _ = self.request("/v1/product/lease", {}, headers=product_headers)
        self.assertEqual(status, 200)
        command_request = {
            "client_request_id": "pause-cancel", "command_type": "pause",
            "expected_applied_revision": None,
        }
        status, queued, _ = self.request(
            "/v1/product/commands", command_request, headers=product_headers,
        )
        self.assertEqual(status, 202)
        status, cancelled, _ = self.request(
            "/v1/product/commands/cancel", {"command_id": queued["command_id"]},
            headers=product_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "cancelled")
        status, claimed, _ = self.request(
            "/v1/engine/claim", {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 200)
        self.assertIsNone(claimed["command"])

        command_request["client_request_id"] = "pause-running"
        status, queued, _ = self.request(
            "/v1/product/commands", command_request, headers=product_headers,
        )
        self.assertEqual(status, 202)
        status, claimed, _ = self.request(
            "/v1/engine/claim", {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(claimed["command"]["command_id"], queued["command_id"])
        status, result, _ = self.request(
            "/v1/product/commands/cancel", {"command_id": queued["command_id"]},
            headers=product_headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "command_already_running")

    def test_unknown_fields_and_oversized_payload_are_rejected(self) -> None:
        cookie, csrf, engine_token = self.bootstrap()
        headers = {"Cookie": cookie, "X-TwinPulse-CSRF": csrf}
        status, result, _ = self.request(
            "/v1/product/lease", {"unknown": True}, headers=headers,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "request_shape_invalid")
        status, _lease, _ = self.request("/v1/product/lease", {}, headers=headers)
        self.assertEqual(status, 200)
        status, result, _ = self.request(
            "/v1/product/commands",
            {
                "client_request_id": "bad-revision", "command_type": "build_scene",
                "artifact_id": "fixed_warehouse_v1", "expected_applied_revision": "f" * 64,
            }, headers=headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["error"]["code"], "revision_mismatch")
        status, result, _ = self.request(
            "/v1/product/commands",
            {
                "client_request_id": "extra-artifact", "command_type": "run",
                "artifact_id": "fixed_warehouse_v1", "expected_applied_revision": None,
            }, headers=headers,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "command_shape_invalid")
        invalid_snapshot = SimulationSnapshot(
            engine_session_id="engine-1", stage_epoch="stage-1", project_id="default",
            applied_revision=None, run_id=None, sequence=1, runtime_state="idle",
            safety_state=None, safety_reason=None, permitted_commands=("get_state",),
            capabilities=("simulation",), telemetry_available=False,
        ).to_dict()
        invalid_snapshot["schema_version"] = "0.0"
        status, result, _ = self.request(
            "/v1/engine/snapshot", {"snapshot": invalid_snapshot},
            headers={"Authorization": f"Bearer {engine_token}"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "request_invalid")
        status, result, _ = self.request(
            "/v1/product/commands", raw=b"{" + b" " * (300 * 1024), headers=headers,
        )
        self.assertEqual(status, 413)
        self.assertEqual(result["error"]["code"], "payload_too_large")

    def test_inflight_command_becomes_unknown_after_engine_timeout(self) -> None:
        cookie, csrf, engine_token = self.bootstrap()
        product_headers = {"Cookie": cookie, "X-TwinPulse-CSRF": csrf}
        engine_headers = {"Authorization": f"Bearer {engine_token}"}
        status, _lease, _ = self.request("/v1/product/lease", {}, headers=product_headers)
        self.assertEqual(status, 200)
        status, submitted, _ = self.request(
            "/v1/product/commands",
            {
                "client_request_id": "crash-run", "command_type": "run",
                "expected_applied_revision": None,
            }, headers=product_headers,
        )
        self.assertEqual(status, 202)
        status, claimed, _ = self.request(
            "/v1/engine/claim", {"engine_session_id": "engine-1", "stage_epoch": "stage-1"},
            headers=engine_headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(claimed["command"]["command_id"], submitted["command_id"])
        self.clock.advance(3.1)
        status, state, _ = self.request("/v1/product/state", headers={"Cookie": cookie}, method="GET")
        self.assertEqual(status, 200)
        self.assertFalse(state["engine_connected"])
        self.assertEqual(state["operations"][0]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
