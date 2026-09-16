"""Outbound stdlib HTTP bridge worker; no USD/PhysX access occurs here."""

from __future__ import annotations

from collections import deque
import json
from threading import Event, Lock, Thread
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from twinpulse_core import CommandEnvelope, CommandReceipt, SimulationSnapshot

from .isaac_adapter import IsaacSimulationAdapter


class BridgeProtocolError(RuntimeError):
    pass


class BridgeClient:
    """Polls the backend on an I/O thread and executes on explicit main-thread updates."""

    def __init__(
        self,
        adapter: IsaacSimulationAdapter,
        *,
        base_url: str,
        bootstrap_secret: str,
        poll_interval_s: float = 0.1,
        heartbeat_interval_s: float = 1.0,
        watchdog_timeout_s: float = 3.0,
        queue_limit: int = 16,
        clock=time.monotonic,
    ) -> None:
        if not base_url.startswith("http://127.0.0.1:"):
            raise ValueError("Bridge URL must use the 127.0.0.1 loopback origin")
        if len(bootstrap_secret) < 32:
            raise ValueError("Engine bootstrap secret is invalid")
        self.adapter = adapter
        self.base_url = base_url.rstrip("/")
        self._bootstrap_secret: str | None = bootstrap_secret
        self._poll_interval_s = poll_interval_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._watchdog_timeout_s = watchdog_timeout_s
        self._queue_limit = queue_limit
        self._clock = clock
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._incoming: deque[CommandEnvelope] = deque()
        self._outgoing: deque[CommandReceipt] = deque()
        self._latest_snapshot: SimulationSnapshot | None = None
        self._engine_token: str | None = None
        self._shared_stage_epoch = adapter.stage_epoch
        self._remote_stage_epoch: str | None = None
        self._lease_valid = False
        self._lease_id: str | None = None
        self._last_success = clock()
        self._last_snapshot_at = 0.0
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._engine_token is not None and self._clock() - self._last_success <= self._watchdog_timeout_s

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._network_loop, name="TwinPulseBridgeIO", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None

    def update(self) -> None:
        """Run from Kit's update thread; this is the only method touching the adapter."""
        if self.adapter.refresh_stage_epoch():
            with self._lock:
                self._shared_stage_epoch = self.adapter.stage_epoch
        now = self._clock()
        with self._lock:
            lease_valid = self._lease_valid
            lease_id = self._lease_id
            stale = now - self._last_success > self._watchdog_timeout_s
            command = self._incoming.popleft() if self._incoming else None
        self.adapter.update_control_lease(lease_id, lease_valid and not stale)
        if stale:
            # Promote the safety reason once the transport watchdog confirms a
            # backend outage, even if an earlier lease failure already paused.
            self.adapter.fail_safe_pause("Backend connection lost")
        elif not lease_valid and self.adapter.runtime.state == "running":
            self.adapter.fail_safe_pause("Control lease expired")
        if command is not None:
            receipt = self.adapter.execute(command)
            with self._lock:
                if len(self._outgoing) >= self._queue_limit:
                    self._outgoing.popleft()
                self._outgoing.append(receipt)
        if now - self._last_snapshot_at >= 0.1:
            snapshot = self.adapter.snapshot()
            with self._lock:
                self._latest_snapshot = snapshot
            self._last_snapshot_at = now

    def _network_loop(self) -> None:
        next_heartbeat = 0.0
        try:
            self._bootstrap()
            while not self._stop.is_set():
                try:
                    with self._lock:
                        stage_epoch = self._shared_stage_epoch
                        remote_stage_epoch = self._remote_stage_epoch
                    if remote_stage_epoch != stage_epoch:
                        self._transition_stage(remote_stage_epoch or stage_epoch, stage_epoch)
                    now = self._clock()
                    if now >= next_heartbeat:
                        heartbeat = self._post(
                            "/v1/engine/heartbeat",
                            {"engine_session_id": self.adapter.engine_session_id, "stage_epoch": stage_epoch},
                        )
                        with self._lock:
                            self._lease_valid = bool(heartbeat.get("lease_valid"))
                            lease = heartbeat.get("control_lease_id")
                            self._lease_id = lease if isinstance(lease, str) else None
                        next_heartbeat = now + self._heartbeat_interval_s
                    self._flush_receipts()
                    self._flush_snapshot()
                    with self._lock:
                        can_claim = self._lease_valid and len(self._incoming) < self._queue_limit
                    if can_claim:
                        result = self._post(
                            "/v1/engine/claim",
                            {"engine_session_id": self.adapter.engine_session_id, "stage_epoch": stage_epoch},
                        )
                        value = result.get("command")
                        if value is not None:
                            if not isinstance(value, Mapping):
                                raise BridgeProtocolError("Backend command is not an object")
                            command = CommandEnvelope.from_dict(value)
                            with self._lock:
                                self._incoming.append(command)
                    with self._lock:
                        self._last_success = self._clock()
                        self._last_error = None
                except (BridgeProtocolError, HTTPError, URLError, OSError, ValueError) as error:
                    with self._lock:
                        self._last_error = f"{type(error).__name__}: {str(error)[:240]}"
                        self._lease_valid = False
                        self._lease_id = None
                    self._stop.wait(min(0.5, self._poll_interval_s * 5.0))
                    continue
                self._stop.wait(self._poll_interval_s)
        except (BridgeProtocolError, HTTPError, URLError, OSError, ValueError) as error:
            with self._lock:
                self._last_error = f"{type(error).__name__}: {str(error)[:240]}"
                self._lease_valid = False
                self._lease_id = None

    def _bootstrap(self) -> None:
        secret = self._bootstrap_secret
        if secret is None:
            raise BridgeProtocolError("Engine bootstrap secret is unavailable")
        result = self._post(
            "/v1/bootstrap",
            {
                "role": "engine", "secret": secret,
                "engine_session_id": self.adapter.engine_session_id,
                "stage_epoch": self.adapter.stage_epoch,
            },
            authenticated=False,
        )
        token = result.get("session_token")
        if not isinstance(token, str) or not token:
            raise BridgeProtocolError("Backend did not issue an engine session")
        with self._lock:
            self._engine_token = token
            self._remote_stage_epoch = self.adapter.stage_epoch
            self._last_success = self._clock()
        self._bootstrap_secret = None

    def _transition_stage(self, current: str, new: str) -> None:
        result = self._post(
            "/v1/engine/stage",
            {
                "engine_session_id": self.adapter.engine_session_id,
                "current_stage_epoch": current,
                "new_stage_epoch": new,
            },
        )
        if result.get("stage_epoch") != new:
            raise BridgeProtocolError("Backend did not accept the stage transition")
        with self._lock:
            self._remote_stage_epoch = new

    def _flush_receipts(self) -> None:
        while True:
            with self._lock:
                receipt = self._outgoing[0] if self._outgoing else None
            if receipt is None:
                return
            self._post("/v1/engine/receipt", {"receipt": receipt.to_dict()})
            with self._lock:
                if self._outgoing and self._outgoing[0] == receipt:
                    self._outgoing.popleft()

    def _flush_snapshot(self) -> None:
        with self._lock:
            snapshot = self._latest_snapshot
        if snapshot is None:
            return
        self._post("/v1/engine/snapshot", {"snapshot": snapshot.to_dict()})
        with self._lock:
            if self._latest_snapshot == snapshot:
                self._latest_snapshot = None

    def _post(
        self, path: str, body: Mapping[str, Any], *, authenticated: bool = True,
    ) -> Mapping[str, Any]:
        headers = {"Content-Type": "application/json", "Host": self.base_url.removeprefix("http://")}
        if authenticated:
            with self._lock:
                token = self._engine_token
            if token is None:
                raise BridgeProtocolError("Engine session is unavailable")
            headers["Authorization"] = f"Bearer {token}"
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        request = Request(self.base_url + path, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=2.0) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = detail.get("error", {}).get("code", "http_error")
            except Exception:
                message = "http_error"
            raise BridgeProtocolError(f"Backend rejected request: {message}") from error
        if not isinstance(value, Mapping):
            raise BridgeProtocolError("Backend response is not an object")
        return value
