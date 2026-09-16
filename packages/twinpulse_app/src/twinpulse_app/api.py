"""Authenticated loopback-only HTTP/JSON API for the R4 bridge."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
from threading import RLock, Thread
import time
from typing import Mapping
from urllib.parse import urlsplit

from twinpulse_core import CommandReceipt, SimulationSnapshot

from .command_broker import BrokerError, CommandBroker


MAX_JSON_BYTES = 256 * 1024
PRODUCT_COOKIE = "twinpulse_product"


@dataclass(slots=True)
class _Session:
    session_id: str
    role: str
    csrf: str | None
    expires_at: float
    engine_session_id: str | None = None
    stage_epoch: str | None = None


class LocalApiServer:
    """One-process local API. It deliberately has no CORS or remote-bind mode."""

    def __init__(
        self,
        broker: CommandBroker,
        *,
        product_bootstrap_secret: str,
        engine_bootstrap_secret: str,
        host: str = "127.0.0.1",
        port: int = 0,
        bootstrap_ttl_s: float = 30.0,
        session_ttl_s: float = 1800.0,
        clock=time.monotonic,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("TwinPulse local API may bind only to 127.0.0.1")
        if len(product_bootstrap_secret) < 32 or len(engine_bootstrap_secret) < 32:
            raise ValueError("Bootstrap secrets must contain at least 256 bits of material")
        self.broker = broker
        self._clock = clock
        self._bootstrap_expires_at = clock() + bootstrap_ttl_s
        self._bootstrap: dict[str, str | None] = {
            "product": product_bootstrap_secret,
            "engine": engine_bootstrap_secret,
        }
        self._session_ttl_s = session_ttl_s
        self._sessions: dict[str, _Session] = {}
        self._session_lock = RLock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "TwinPulseLocal/1.0"
            sys_version = ""

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                owner._handle(self)

            def do_POST(self) -> None:  # noqa: N802
                owner._handle(self)

            def do_OPTIONS(self) -> None:  # noqa: N802
                owner._error(self, 405, "method_not_allowed", "Cross-origin preflight is not supported")

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        self._thread: Thread | None = None

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._httpd.serve_forever, name="TwinPulseLocalApi", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)
        self._thread = None

    def _handle(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlsplit(request.path)
        if parsed.query or parsed.fragment:
            return self._error(request, 400, "url_data_forbidden", "Query and fragment data are forbidden")
        if not self._host_allowed(request.headers.get("Host", "")):
            return self._error(request, 403, "host_forbidden", "Host header is not allowed")
        if request.headers.get("Origin") not in (None, self.base_url, f"http://localhost:{self.port}"):
            return self._error(request, 403, "origin_forbidden", "Origin is not allowed")
        try:
            if request.command == "POST" and parsed.path == "/v1/bootstrap":
                return self._bootstrap_session(request, self._read_json(request))
            if parsed.path.startswith("/v1/product/"):
                session = self._authenticate_product(request, require_csrf=request.command == "POST")
                if request.command == "GET" and parsed.path == "/v1/product/state":
                    return self._json(request, 200, self.broker.public_state(session.session_id))
                body = self._read_json(request)
                if parsed.path == "/v1/product/lease":
                    self._require_shape(body, set())
                    return self._json(request, 200, self.broker.acquire_lease(session.session_id))
                if parsed.path == "/v1/product/lease/renew":
                    self._require_shape(body, {"control_lease_id"})
                    return self._json(request, 200, self.broker.renew_lease(
                        session.session_id, self._string(body, "control_lease_id"),
                    ))
                if parsed.path == "/v1/product/commands":
                    return self._json(request, 202, self.broker.submit(session.session_id, body))
                if parsed.path == "/v1/product/commands/cancel":
                    self._require_shape(body, {"command_id"})
                    return self._json(request, 200, self.broker.cancel(
                        session.session_id, self._string(body, "command_id"),
                    ))
            if parsed.path.startswith("/v1/engine/"):
                session = self._authenticate_engine(request)
                body = self._read_json(request)
                engine_id = session.engine_session_id or ""
                stage_epoch = session.stage_epoch or ""
                if parsed.path == "/v1/engine/stage":
                    self._require_shape(
                        body, {"engine_session_id", "current_stage_epoch", "new_stage_epoch"},
                    )
                    if (body.get("engine_session_id") != engine_id
                            or body.get("current_stage_epoch") != stage_epoch):
                        raise BrokerError("engine_identity_mismatch", "Engine stage transition is invalid", status=401)
                    new_stage_epoch = self._string(body, "new_stage_epoch")
                    self.broker.register_engine(engine_id, new_stage_epoch)
                    session.stage_epoch = new_stage_epoch
                    return self._json(request, 200, {"stage_epoch": new_stage_epoch})
                if parsed.path == "/v1/engine/heartbeat":
                    self._require_shape(body, {"engine_session_id", "stage_epoch"})
                    self._assert_body_engine(body, session)
                    return self._json(request, 200, self.broker.engine_heartbeat(engine_id, stage_epoch))
                if parsed.path == "/v1/engine/claim":
                    self._require_shape(body, {"engine_session_id", "stage_epoch"})
                    self._assert_body_engine(body, session)
                    command = self.broker.claim(engine_id, stage_epoch)
                    return self._json(request, 200, {"command": command.to_dict() if command else None})
                if parsed.path == "/v1/engine/receipt":
                    self._require_shape(body, {"receipt"})
                    receipt_value = body["receipt"]
                    if not isinstance(receipt_value, Mapping):
                        raise BrokerError("receipt_shape_invalid", "Receipt must be an object", status=400)
                    receipt = CommandReceipt.from_dict(receipt_value)
                    if receipt.engine_session_id != engine_id or receipt.stage_epoch != stage_epoch:
                        raise BrokerError("engine_identity_mismatch", "Receipt engine identity is invalid")
                    self.broker.record_receipt(receipt)
                    return self._json(request, 200, {"accepted": True})
                if parsed.path == "/v1/engine/snapshot":
                    self._require_shape(body, {"snapshot"})
                    snapshot_value = body["snapshot"]
                    if not isinstance(snapshot_value, Mapping):
                        raise BrokerError("snapshot_shape_invalid", "Snapshot must be an object", status=400)
                    snapshot = SimulationSnapshot.from_dict(snapshot_value)
                    if snapshot.engine_session_id != engine_id or snapshot.stage_epoch != stage_epoch:
                        raise BrokerError("engine_identity_mismatch", "Snapshot engine identity is invalid")
                    self.broker.record_snapshot(snapshot)
                    return self._json(request, 200, {"accepted": True})
            return self._error(request, 404, "endpoint_not_found", "Endpoint does not exist")
        except BrokerError as error:
            return self._error(request, error.status, error.code, str(error))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return self._error(request, 400, "request_invalid", str(error)[:240])

    def _bootstrap_session(self, request: BaseHTTPRequestHandler, body: Mapping[str, object]) -> None:
        allowed = {"role", "secret", "engine_session_id", "stage_epoch"}
        if set(body) - allowed:
            raise BrokerError("bootstrap_shape_invalid", "Bootstrap request shape is invalid", status=400)
        role = self._string(body, "role")
        supplied = self._string(body, "secret")
        with self._session_lock:
            expected = self._bootstrap.get(role)
            if (expected is None or self._clock() >= self._bootstrap_expires_at
                    or not hmac.compare_digest(expected, supplied)):
                raise BrokerError("bootstrap_rejected", "Bootstrap credential is invalid or expired", status=401)
            engine_id = stage_epoch = None
            if role == "engine":
                engine_id = self._string(body, "engine_session_id")
                stage_epoch = self._string(body, "stage_epoch")
                self.broker.register_engine(engine_id, stage_epoch)
            elif role != "product":
                raise BrokerError("bootstrap_role_invalid", "Bootstrap role is unsupported", status=400)
            self._bootstrap[role] = None
            session_id = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24) if role == "product" else None
            self._sessions[session_id] = _Session(
                session_id, role, csrf, self._clock() + self._session_ttl_s, engine_id, stage_epoch,
            )
        headers = None
        result: dict[str, object] = {"role": role, "expires_in_s": self._session_ttl_s}
        if role == "product":
            result["csrf_token"] = csrf
            headers = {"Set-Cookie": (
                f"{PRODUCT_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/; "
                f"Max-Age={int(self._session_ttl_s)}"
            )}
        else:
            result["session_token"] = session_id
        self._json(request, 200, result, headers=headers)

    def _authenticate_product(self, request: BaseHTTPRequestHandler, *, require_csrf: bool) -> _Session:
        cookies = self._parse_cookies(request.headers.get("Cookie", ""))
        session = self._session(cookies.get(PRODUCT_COOKIE), "product")
        if require_csrf and not hmac.compare_digest(request.headers.get("X-TwinPulse-CSRF", ""), session.csrf or ""):
            raise BrokerError("csrf_rejected", "CSRF token is invalid", status=403)
        return session

    def _authenticate_engine(self, request: BaseHTTPRequestHandler) -> _Session:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise BrokerError("engine_auth_required", "Engine authorization is required", status=401)
        return self._session(authorization[7:], "engine")

    def _session(self, session_id: str | None, role: str) -> _Session:
        with self._session_lock:
            session = self._sessions.get(session_id or "")
            if session is None or session.role != role or self._clock() >= session.expires_at:
                raise BrokerError("session_rejected", "Session is invalid, expired, or has the wrong role", status=401)
            session.expires_at = self._clock() + self._session_ttl_s
            return session

    def _read_json(self, request: BaseHTTPRequestHandler) -> Mapping[str, object]:
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise BrokerError("content_type_invalid", "Content-Type must be application/json", status=415)
        raw_length = request.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            raise BrokerError("content_length_required", "Content-Length is required", status=411)
        length = int(raw_length)
        if length > MAX_JSON_BYTES:
            # Drain only a tightly bounded overflow so Windows can deliver the
            # 413 response without resetting a socket that still has body data.
            if length <= MAX_JSON_BYTES * 2:
                request.rfile.read(length)
            else:
                request.close_connection = True
            raise BrokerError("payload_too_large", "JSON payload exceeds the limit", status=413)
        value = json.loads(request.rfile.read(length).decode("utf-8"))
        if not isinstance(value, Mapping):
            raise BrokerError("json_object_required", "JSON body must be an object", status=400)
        return value

    @staticmethod
    def _require_shape(value: Mapping[str, object], expected: set[str]) -> None:
        if set(value) != expected:
            raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)

    @staticmethod
    def _string(value: Mapping[str, object], name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item or len(item) > 512:
            raise BrokerError("request_value_invalid", f"{name} is invalid", status=400)
        return item

    @staticmethod
    def _parse_cookies(value: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in value.split(";"):
            name, separator, content = item.strip().partition("=")
            if separator:
                result[name] = content
        return result

    @staticmethod
    def _assert_body_engine(value: Mapping[str, object], session: _Session) -> None:
        if (value.get("engine_session_id") != session.engine_session_id
                or value.get("stage_epoch") != session.stage_epoch):
            raise BrokerError("engine_identity_mismatch", "Engine body identity is invalid", status=401)

    def _host_allowed(self, value: str) -> bool:
        return value in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    @staticmethod
    def _json(
        request: BaseHTTPRequestHandler,
        status: int,
        value: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        request.send_response(status)
        request.send_header("Content-Type", "application/json; charset=utf-8")
        request.send_header("Content-Length", str(len(payload)))
        request.send_header("Cache-Control", "no-store")
        request.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for name, content in headers.items():
                request.send_header(name, content)
        request.end_headers()
        request.wfile.write(payload)

    @classmethod
    def _error(cls, request: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
        cls._json(request, status, {"error": {"code": code, "message": message}})
