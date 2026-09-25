"""Authenticated loopback-only HTTP/JSON API for the R4 bridge."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import math
from pathlib import Path
import secrets
from threading import RLock, Thread
import time
from typing import Mapping
from urllib.parse import urlsplit

from twinpulse_core import CommandReceipt, SimulationSnapshot

from .command_broker import BrokerError, CommandBroker
from .credentials import CredentialStore
from .product_workflow_service import ProductWorkflow
from .settings import (
    DEFAULT_PROVIDER_PROFILE,
    JsonProviderSettingsStore,
    ProviderSettings,
    provider_settings_preset,
)


MAX_JSON_BYTES = 256 * 1024
MAX_UPLOAD_JSON_BYTES = 14 * 1024 * 1024
PRODUCT_COOKIE = "twinpulse_product"


@dataclass(slots=True)
class _Session:
    session_id: str
    role: str
    csrf: str | None
    idle_expires_at: float
    absolute_expires_at: float
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
        session_idle_ttl_s: float = 1800.0,
        session_absolute_ttl_s: float = 28800.0,
        product_workflow: ProductWorkflow | None = None,
        static_root: Path | None = None,
        supervisor_status_file: Path | None = None,
        provider_settings_store: JsonProviderSettingsStore | None = None,
        credential_store: CredentialStore | None = None,
        clock=time.monotonic,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("TwinPulse local API may bind only to 127.0.0.1")
        if len(product_bootstrap_secret) < 32 or len(engine_bootstrap_secret) < 32:
            raise ValueError("Bootstrap secrets must contain at least 256 bits of material")
        if bootstrap_ttl_s <= 0 or session_idle_ttl_s <= 0 or session_absolute_ttl_s <= 0:
            raise ValueError("Authentication lifetimes must be positive")
        self.broker = broker
        self.product_workflow = product_workflow
        self._static_root = static_root.resolve() if static_root is not None else None
        self._supervisor_status_file = (
            supervisor_status_file.resolve() if supervisor_status_file is not None else None
        )
        self._provider_settings_store = provider_settings_store
        self._credential_store = credential_store
        self._provider_settings_lock = RLock()
        self._clock = clock
        self._bootstrap_ttl_s = bootstrap_ttl_s
        self._product_owner_secret = product_bootstrap_secret
        bootstrap_expires_at = clock() + bootstrap_ttl_s
        self._bootstrap_expires_at = {
            "product": bootstrap_expires_at,
            "engine": bootstrap_expires_at,
        }
        self._bootstrap: dict[str, str | None] = {
            "product": product_bootstrap_secret,
            "engine": engine_bootstrap_secret,
        }
        self._session_idle_ttl_s = session_idle_ttl_s
        self._session_absolute_ttl_s = session_absolute_ttl_s
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
        if self.product_workflow is not None:
            self.product_workflow.shutdown()
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
            if request.command == "GET" and not parsed.path.startswith("/v1/"):
                return self._serve_static(request, parsed.path)
            if request.command == "POST" and parsed.path == "/v1/bootstrap/product/issue":
                return self._issue_product_bootstrap(request, self._read_json(request))
            if request.command == "POST" and parsed.path == "/v1/bootstrap":
                return self._bootstrap_session(request, self._read_json(request))
            if parsed.path.startswith("/v1/product/"):
                session = self._authenticate_product(request, require_csrf=request.command == "POST")
                if request.command == "GET" and parsed.path == "/v1/product/session":
                    return self._json(request, 200, self._session_metadata(session))
                if request.command == "GET" and parsed.path == "/v1/product/state":
                    return self._json(request, 200, self.broker.public_state(session.session_id))
                if request.command == "GET" and parsed.path == "/v1/product/workflow":
                    return self._json(request, 200, self._workflow().snapshot())
                if request.command == "GET" and parsed.path == "/v1/product/runtime":
                    return self._json(request, 200, self._supervisor_status())
                if request.command == "GET" and parsed.path == "/v1/product/provider-settings":
                    return self._json(request, 200, self._provider_settings())
                body = self._read_json(
                    request,
                    maximum=MAX_UPLOAD_JSON_BYTES if parsed.path == "/v1/product/input" else MAX_JSON_BYTES,
                )
                if parsed.path == "/v1/product/input":
                    return self._json(request, 200, self._workflow().select_input(body))
                if parsed.path == "/v1/product/generation":
                    self._require_shape(body, set())
                    return self._json(request, 202, self._workflow().start_generation())
                if parsed.path == "/v1/product/provider-settings":
                    return self._json(request, 200, self._save_provider_settings(body))
                if parsed.path == "/v1/product/generation/cancel":
                    self._require_shape(body, set())
                    return self._json(request, 200, self._workflow().cancel())
                if parsed.path == "/v1/product/draft/acknowledge":
                    self._require_shape(body, {"revision"})
                    return self._json(
                        request, 200,
                        self._workflow().acknowledge(self._string(body, "revision")),
                    )
                if parsed.path == "/v1/product/lease":
                    self._require_shape(body, set())
                    return self._json(request, 200, self.broker.acquire_lease(session.session_id))
                if parsed.path == "/v1/product/lease/renew":
                    self._require_shape(body, {"control_lease_id"})
                    return self._json(request, 200, self.broker.renew_lease(
                        session.session_id, self._string(body, "control_lease_id"),
                    ))
                if parsed.path == "/v1/product/commands":
                    if body.get("command_type") == "build_scene" and self.product_workflow is not None:
                        self.product_workflow.assert_build_allowed(
                            body.get("artifact_id"), body.get("expected_applied_revision"),
                        )
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

    def _workflow(self) -> ProductWorkflow:
        if self.product_workflow is None:
            raise BrokerError("workflow_unavailable", "Product workflow is not configured", status=503)
        return self.product_workflow

    def _provider_settings(self) -> dict[str, object]:
        if self._provider_settings_store is None or self._credential_store is None:
            raise BrokerError("provider_settings_unavailable", "Provider settings are not configured", status=503)
        try:
            value = self._provider_settings_store.load().validated()
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            raise BrokerError(
                "provider_settings_corrupt",
                "Provider settings could not be read; the original file was preserved for review",
                status=500,
            ) from None
        try:
            credential_configured = self._credential_store.is_configured()
        except Exception:
            raise BrokerError(
                "credential_status_failed", "Credential status could not be read securely", status=500,
            ) from None
        provider_connected = False
        if self.product_workflow is not None:
            snapshot = self.product_workflow.snapshot()
            provider = snapshot.get("provider")
            provider_connected = bool(
                snapshot.get("mode") == "live_provider"
                and isinstance(provider, Mapping)
                and provider.get("connected")
            )
        return {
            "schema_version": "3.0",
            "base_url": value.base_url,
            "model_id": value.model_id,
            "reasoning_effort": value.reasoning_effort,
            "adapter_kind": value.adapter_kind,
            "provider_profile": value.provider_profile,
            "endpoint_path": value.endpoint_path,
            "credential_ref": value.credential_ref,
            "observer_model_id": value.observer_model_id,
            "fallback_observer_model_id": value.fallback_observer_model_id,
            "capabilities": {
                "supports_images": value.supports_images,
                "supports_structured_output": value.supports_structured_output,
                "max_images": value.max_images,
                "accepted_mime_types": list(value.accepted_mime_types),
            },
            "settings_saved": self._provider_settings_store.exists(),
            "capability_checked": value.provider_profile == DEFAULT_PROVIDER_PROFILE or provider_connected,
            "credential_configured": credential_configured,
            "live_request_succeeded": provider_connected,
        }

    def _save_provider_settings(self, body: Mapping[str, object]) -> dict[str, object]:
        if self._provider_settings_store is None or self._credential_store is None:
            raise BrokerError("provider_settings_unavailable", "Provider settings are not configured", status=503)
        legacy_shape = {"base_url", "model_id", "reasoning_effort", "api_key"}
        current_shape = legacy_shape | {"credential_reapproval"}
        profile_shape = current_shape | {"provider_profile"}
        if frozenset(body) not in {
            frozenset(legacy_shape), frozenset(current_shape), frozenset(profile_shape),
        }:
            raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)
        api_key = body.get("api_key")
        if not isinstance(api_key, str) or len(api_key) > 8192:
            raise BrokerError("request_value_invalid", "api_key is invalid", status=400)
        reapproval = body.get("credential_reapproval", False)
        if not isinstance(reapproval, bool):
            raise BrokerError("request_value_invalid", "credential_reapproval is invalid", status=400)
        with self._provider_settings_lock:
            try:
                previous = self._provider_settings_store.load().validated()
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                raise BrokerError(
                    "provider_settings_corrupt",
                    "Provider settings could not be read; the original file was preserved for review",
                    status=500,
                ) from None
            selected_profile = body.get("provider_profile", previous.provider_profile)
            if not isinstance(selected_profile, str):
                raise BrokerError("request_value_invalid", "provider_profile is invalid", status=400)
            try:
                preset = provider_settings_preset(selected_profile, credential_ref=previous.credential_ref)
                if preset.provider_profile == DEFAULT_PROVIDER_PROFILE:
                    value = ProviderSettings(
                        self._string(body, "base_url"),
                        self._string(body, "model_id"),
                        self._string(body, "reasoning_effort"),
                        preset.adapter_kind,
                        preset.provider_profile,
                        preset.endpoint_path,
                        preset.credential_ref,
                        preset.supports_images,
                        preset.supports_structured_output,
                        preset.max_images,
                        preset.accepted_mime_types,
                        preset.observer_model_id,
                        preset.fallback_observer_model_id,
                    ).validated()
                else:
                    requested = (
                        self._string(body, "base_url"), self._string(body, "model_id"),
                        self._string(body, "reasoning_effort"),
                    )
                    expected = (preset.base_url, preset.model_id, preset.reasoning_effort)
                    if requested != expected:
                        raise BrokerError(
                            "provider_preset_mismatch",
                            "Nebius uses the reviewed S3a endpoint and model pipeline",
                            status=400,
                        )
                    value = preset
            except ValueError as error:
                raise BrokerError("provider_settings_invalid", str(error), status=400) from None
            store_target = getattr(self._credential_store, "target_name", value.credential_ref)
            if store_target != value.credential_ref:
                raise BrokerError(
                    "credential_reference_mismatch",
                    "The active credential store does not match the selected provider profile",
                    status=409,
                )
            binding_changed = value.binding_identity != previous.binding_identity
            profile_changed = (
                value.adapter_kind != previous.adapter_kind
                or value.provider_profile != previous.provider_profile
                or value.credential_ref != previous.credential_ref
            )
            has_new_key = bool(api_key.strip())
            if binding_changed and not has_new_key:
                try:
                    credential_configured = self._credential_store.is_configured()
                except Exception:
                    raise BrokerError(
                        "credential_status_failed", "Credential status could not be read securely", status=500,
                    ) from None
                if profile_changed or not reapproval or not credential_configured:
                    raise BrokerError(
                        "credential_rebind_required",
                        "Endpoint or provider identity changed; enter a new key or explicitly reapprove the existing key",
                        status=409,
                    )
            old_secret: str | None = None
            if has_new_key:
                try:
                    old_secret = self._credential_store.load()
                    self._credential_store.save(api_key)
                except Exception:
                    raise BrokerError(
                        "credential_save_failed", "The credential could not be stored securely", status=500,
                    ) from None
            try:
                self._provider_settings_store.save(value)
            except Exception:
                if has_new_key:
                    try:
                        if old_secret:
                            self._credential_store.save(old_secret)
                        else:
                            self._credential_store.delete()
                    except Exception:
                        raise BrokerError(
                            "settings_transaction_rollback_failed",
                            "Settings were not saved and credential rollback requires manual review",
                            status=500,
                        ) from None
                raise BrokerError(
                    "provider_settings_save_failed", "Provider settings could not be saved", status=500,
                ) from None
        if self.product_workflow is not None:
            self.product_workflow.provider_settings_changed()
        return self._provider_settings()

    def _supervisor_status(self) -> dict[str, object]:
        path = self._supervisor_status_file
        if path is None:
            return {
                "schema_version": "1.0", "status": "unmanaged", "phase": "standalone",
                "message": "Started without the TwinPulse process manager",
                "backend": {"owned": False, "state": "running"},
                "engine": {"owned": False, "state": "unknown"},
                "browser": {"launched": False},
            }
        try:
            if path.stat().st_size > 64 * 1024:
                raise ValueError("status file exceeds limit")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError("status must be an object")
            return _sanitize_supervisor_status(value)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            return {
                "schema_version": "1.0", "status": "error", "phase": "status_unavailable",
                "message": str(error)[:240],
                "backend": {"owned": True, "state": "running"},
                "engine": {"owned": True, "state": "unknown"},
                "browser": {"launched": False},
            }

    def _serve_static(self, request: BaseHTTPRequestHandler, path: str) -> None:
        root = self._static_root
        if root is None:
            return self._error(request, 404, "static_unavailable", "Product UI is not configured")
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        if not relative or "\\" in relative or any(part in {"", ".", ".."} for part in relative.split("/")):
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        if not target.is_file():
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        suffix = target.suffix.lower()
        media_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".json": "application/json; charset=utf-8",
        }.get(suffix)
        if media_type is None:
            return self._error(request, 415, "asset_type_forbidden", "Static asset type is forbidden")
        payload = target.read_bytes()
        request.send_response(200)
        request.send_header("Content-Type", media_type)
        request.send_header("Content-Length", str(len(payload)))
        request.send_header("Cache-Control", "no-store" if suffix == ".html" else "public, max-age=31536000, immutable")
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Referrer-Policy", "no-referrer")
        request.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        request.end_headers()
        request.wfile.write(payload)

    def _bootstrap_session(self, request: BaseHTTPRequestHandler, body: Mapping[str, object]) -> None:
        allowed = {"role", "secret", "engine_session_id", "stage_epoch"}
        if set(body) - allowed:
            raise BrokerError("bootstrap_shape_invalid", "Bootstrap request shape is invalid", status=400)
        role = self._string(body, "role")
        supplied = self._string(body, "secret")
        with self._session_lock:
            expected = self._bootstrap.get(role)
            if (expected is None or self._clock() >= self._bootstrap_expires_at.get(role, 0.0)
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
            now = self._clock()
            absolute_expires_at = now + self._session_absolute_ttl_s
            self._sessions[session_id] = _Session(
                session_id=session_id,
                role=role,
                csrf=csrf,
                idle_expires_at=min(now + self._session_idle_ttl_s, absolute_expires_at),
                absolute_expires_at=absolute_expires_at,
                engine_session_id=engine_id,
                stage_epoch=stage_epoch,
            )
        headers = None
        session = self._sessions[session_id]
        result = self._session_metadata(session)
        if role == "product":
            headers = {"Set-Cookie": (
                f"{PRODUCT_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/; "
                f"Max-Age={math.ceil(self._session_absolute_ttl_s)}"
            )}
        else:
            result["session_token"] = session_id
        self._json(request, 200, result, headers=headers)

    def _issue_product_bootstrap(
        self, request: BaseHTTPRequestHandler, body: Mapping[str, object],
    ) -> None:
        self._require_shape(body, {"owner_secret"})
        supplied = self._string(body, "owner_secret")
        if not hmac.compare_digest(self._product_owner_secret, supplied):
            raise BrokerError(
                "bootstrap_owner_rejected",
                "Product bootstrap owner credential is invalid",
                status=401,
            )
        with self._session_lock:
            bootstrap_secret = secrets.token_urlsafe(32)
            self._bootstrap["product"] = bootstrap_secret
            self._bootstrap_expires_at["product"] = self._clock() + self._bootstrap_ttl_s
        self._json(request, 200, {
            "role": "product",
            "bootstrap_secret": bootstrap_secret,
            "expires_in_s": self._bootstrap_ttl_s,
        })

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
            now = self._clock()
            if (session is None or session.role != role
                    or now >= session.idle_expires_at or now >= session.absolute_expires_at):
                if session is not None and (
                    now >= session.idle_expires_at or now >= session.absolute_expires_at
                ):
                    self._sessions.pop(session.session_id, None)
                raise BrokerError("session_rejected", "Session is invalid, expired, or has the wrong role", status=401)
            session.idle_expires_at = min(
                now + self._session_idle_ttl_s,
                session.absolute_expires_at,
            )
            return session

    def _session_metadata(self, session: _Session) -> dict[str, object]:
        now = self._clock()
        result: dict[str, object] = {
            "role": session.role,
            "idle_expires_in_s": max(0, math.ceil(session.idle_expires_at - now)),
            "absolute_expires_in_s": max(0, math.ceil(session.absolute_expires_at - now)),
        }
        if session.role == "product":
            result["csrf_token"] = session.csrf or ""
        return result

    def _read_json(
        self, request: BaseHTTPRequestHandler, *, maximum: int = MAX_JSON_BYTES,
    ) -> Mapping[str, object]:
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise BrokerError("content_type_invalid", "Content-Type must be application/json", status=415)
        raw_length = request.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            raise BrokerError("content_length_required", "Content-Length is required", status=411)
        length = int(raw_length)
        if length > maximum:
            # Drain only a tightly bounded overflow so Windows can deliver the
            # 413 response without resetting a socket that still has body data.
            if length <= maximum * 2:
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


def _sanitize_supervisor_status(value: Mapping[str, object]) -> dict[str, object]:
    def text(name: str, default: str = "") -> str:
        item = value.get(name, default)
        return str(item)[:240]

    def component(name: str) -> dict[str, object]:
        raw = value.get(name)
        if not isinstance(raw, Mapping):
            raw = {}
        result: dict[str, object] = {
            "owned": bool(raw.get("owned", False)),
            "state": str(raw.get("state", "unknown"))[:64],
        }
        if isinstance(raw.get("pid"), int) and int(raw["pid"]) > 0:
            result["pid"] = int(raw["pid"])
        if isinstance(raw.get("exit_code"), int):
            result["exit_code"] = int(raw["exit_code"])
        return result

    browser_raw = value.get("browser")
    browser = browser_raw if isinstance(browser_raw, Mapping) else {}
    return {
        "schema_version": "1.0",
        "status": text("status", "unknown"),
        "phase": text("phase", "unknown"),
        "message": text("message"),
        "started_at_utc": text("started_at_utc") or None,
        "updated_at_utc": text("updated_at_utc") or None,
        "backend": component("backend"),
        "engine": component("engine"),
        "browser": {"launched": bool(browser.get("launched", False))},
    }
