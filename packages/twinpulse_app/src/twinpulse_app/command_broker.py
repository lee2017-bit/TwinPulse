"""Bounded single-engine command broker for the local TwinPulse bridge."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
import hashlib
import json
import secrets
from threading import RLock
import time
from typing import Any, Mapping
from uuid import uuid4

from twinpulse_core import (
    CommandEnvelope,
    CommandReceipt,
    SimulationSnapshot,
    SpecBundle,
    bundle_digest,
)


class BrokerError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class RegisteredArtifact:
    artifact_id: str
    revision: str
    bundle: SpecBundle


@dataclass(slots=True)
class _Operation:
    command: CommandEnvelope
    request_hash: str
    product_session_id: str
    status: str = "accepted"
    receipt: CommandReceipt | None = None

    def public(self) -> dict[str, object]:
        return {
            "command_id": self.command.command_id,
            "command_type": self.command.command_type,
            "project_id": self.command.project_id,
            "engine_session_id": self.command.engine_session_id,
            "stage_epoch": self.command.stage_epoch,
            "expected_applied_revision": self.command.expected_applied_revision,
            "status": self.receipt.status if self.receipt is not None else self.status,
            "receipt": self.receipt.to_dict() if self.receipt is not None else None,
        }


def _canonical_hash(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CommandBroker:
    """Serializes one product writer against one connected Isaac engine."""

    def __init__(
        self,
        *,
        project_id: str = "default",
        queue_limit: int = 32,
        operation_limit: int = 256,
        lease_ttl_s: float = 3.0,
        engine_timeout_s: float = 3.0,
        clock=time.monotonic,
    ) -> None:
        if queue_limit < 1 or operation_limit < queue_limit:
            raise ValueError("broker limits are invalid")
        self.project_id = project_id
        self.queue_limit = queue_limit
        self.operation_limit = operation_limit
        self.lease_ttl_s = float(lease_ttl_s)
        self.engine_timeout_s = float(engine_timeout_s)
        self._clock = clock
        self._lock = RLock()
        self._artifacts: dict[str, RegisteredArtifact] = {}
        self._engine_session_id: str | None = None
        self._stage_epoch: str | None = None
        self._engine_heartbeat_at = 0.0
        self._lease_id: str | None = None
        self._lease_owner: str | None = None
        self._lease_expires_at = 0.0
        self._queue: deque[str] = deque()
        self._inflight: str | None = None
        self._operations: OrderedDict[str, _Operation] = OrderedDict()
        self._request_ids: dict[str, tuple[str, str]] = {}
        self._snapshot: SimulationSnapshot | None = None

    def register_artifact(self, artifact_id: str, bundle: SpecBundle) -> RegisteredArtifact:
        if not artifact_id or len(artifact_id) > 128:
            raise ValueError("artifact_id is invalid")
        checked = SpecBundle.from_dict(bundle.to_dict())
        artifact = RegisteredArtifact(artifact_id, bundle_digest(checked), checked)
        with self._lock:
            self._artifacts[artifact_id] = artifact
        return artifact

    def register_engine(self, engine_session_id: str, stage_epoch: str) -> None:
        if not engine_session_id or not stage_epoch:
            raise BrokerError("engine_identity_invalid", "Engine identity is required", status=400)
        with self._lock:
            if self._engine_session_id != engine_session_id:
                self._expire_engine_operations("engine_session_replaced")
                self._snapshot = None
            elif self._stage_epoch is not None and self._stage_epoch != stage_epoch:
                self._expire_engine_operations("stage_epoch_changed")
                self._snapshot = None
            self._engine_session_id = engine_session_id
            self._stage_epoch = stage_epoch
            self._engine_heartbeat_at = self._clock()

    def engine_heartbeat(self, engine_session_id: str, stage_epoch: str) -> dict[str, object]:
        with self._lock:
            self._assert_engine(engine_session_id, stage_epoch)
            self._engine_heartbeat_at = self._clock()
            return {
                "lease_valid": self._lease_valid(),
                "control_lease_id": self._lease_id if self._lease_valid() else None,
                "lease_ttl_s": self.lease_ttl_s,
            }

    def acquire_lease(self, product_session_id: str) -> dict[str, object]:
        now = self._clock()
        with self._lock:
            if self._lease_valid() and self._lease_owner != product_session_id:
                raise BrokerError("control_lease_conflict", "Another product session owns control")
            if not self._lease_valid():
                self._lease_id = secrets.token_urlsafe(24)
                self._lease_owner = product_session_id
            self._lease_expires_at = now + self.lease_ttl_s
            return {"control_lease_id": self._lease_id, "ttl_s": self.lease_ttl_s}

    def renew_lease(self, product_session_id: str, control_lease_id: str) -> dict[str, object]:
        with self._lock:
            if (not self._lease_valid() or self._lease_owner != product_session_id
                    or not secrets.compare_digest(self._lease_id or "", control_lease_id)):
                raise BrokerError("control_lease_invalid", "Control lease is invalid or expired")
            self._lease_expires_at = self._clock() + self.lease_ttl_s
            return {"control_lease_id": self._lease_id, "ttl_s": self.lease_ttl_s}

    def submit(self, product_session_id: str, value: Mapping[str, object]) -> dict[str, object]:
        base_shape = {"client_request_id", "command_type", "expected_applied_revision"}
        command_type = value.get("command_type")
        expected_shape = base_shape | ({"artifact_id"} if command_type == "build_scene" else set())
        if set(value) != expected_shape or not isinstance(value.get("client_request_id"), str):
            raise BrokerError("command_shape_invalid", "Command request shape is invalid", status=400)
        request_id = value["client_request_id"]
        if not request_id or len(request_id) > 128 or not isinstance(command_type, str):
            raise BrokerError("command_shape_invalid", "Command identity is invalid", status=400)
        request_hash = _canonical_hash(dict(value))
        with self._lock:
            existing = self._request_ids.get(request_id)
            if existing is not None:
                previous_hash, command_id = existing
                if previous_hash != request_hash:
                    raise BrokerError("duplicate_request_conflict", "Request ID was reused with different content")
                return self._operations[command_id].public()
            self._assert_product_control(product_session_id)
            self._assert_engine_connected()
            if len(self._queue) >= self.queue_limit:
                raise BrokerError("command_queue_full", "Command queue is full", status=429)
            if self._inflight is not None or self._queue:
                raise BrokerError("mutating_command_busy", "Another command is pending or running")
            snapshot = self._snapshot
            if command_type in {"build_scene", "reset"} and snapshot is not None and snapshot.runtime_state == "running":
                raise BrokerError("runtime_running", "Pause the simulation before Build or Reset")

            payload: dict[str, Any] = {}
            expected = value.get("expected_applied_revision")
            if expected is not None and not isinstance(expected, str):
                raise BrokerError("revision_invalid", "Expected revision must be a string or null", status=400)
            if command_type == "build_scene":
                artifact_id = value.get("artifact_id")
                if not isinstance(artifact_id, str) or artifact_id not in self._artifacts:
                    raise BrokerError("artifact_unknown", "Build artifact is not registered", status=404)
                artifact = self._artifacts[artifact_id]
                if expected is not None and expected != artifact.revision:
                    raise BrokerError("revision_mismatch", "Build artifact revision does not match the request")
                expected = artifact.revision
                payload = {
                    "artifact_id": artifact.artifact_id,
                    "bundle_sha256": artifact.revision,
                    "bundle": artifact.bundle.to_dict(),
                }
            elif command_type not in {"run", "pause", "reset", "focus_scene", "get_state"}:
                raise BrokerError("command_type_invalid", "Command type is unsupported", status=400)
            elif expected is None and snapshot is not None:
                expected = snapshot.applied_revision

            command = CommandEnvelope(
                command_id=str(uuid4()), command_type=command_type,
                project_id=self.project_id,
                engine_session_id=self._engine_session_id or "",
                stage_epoch=self._stage_epoch or "",
                control_lease_id=self._lease_id or "",
                expected_applied_revision=expected,
                payload=payload,
                ttl_s=120.0 if command_type == "build_scene" else 10.0,
            )
            operation = _Operation(command, request_hash, product_session_id)
            self._operations[command.command_id] = operation
            self._request_ids[request_id] = (request_hash, command.command_id)
            self._queue.append(command.command_id)
            self._trim_operations()
            return operation.public()

    def claim(self, engine_session_id: str, stage_epoch: str) -> CommandEnvelope | None:
        with self._lock:
            self._assert_engine(engine_session_id, stage_epoch)
            self._engine_heartbeat_at = self._clock()
            if not self._lease_valid() or self._inflight is not None:
                return None
            while self._queue:
                command_id = self._queue.popleft()
                operation = self._operations[command_id]
                if operation.command.expired():
                    operation.status = "expired"
                    operation.receipt = CommandReceipt(
                        command_id=operation.command.command_id,
                        command_type=operation.command.command_type,
                        project_id=operation.command.project_id,
                        engine_session_id=operation.command.engine_session_id,
                        stage_epoch=operation.command.stage_epoch,
                        status="expired", error_code="command_expired",
                        message="Command expired before engine claim",
                    )
                    continue
                operation.status = "running"
                self._inflight = command_id
                return operation.command
            return None

    def cancel(self, product_session_id: str, command_id: str) -> dict[str, object]:
        """Cancel an accepted command before the engine claims it."""
        with self._lock:
            operation = self._operations.get(command_id)
            if operation is None or operation.product_session_id != product_session_id:
                raise BrokerError("command_unknown", "Command does not exist", status=404)
            if operation.receipt is not None:
                return operation.public()
            if self._inflight == command_id or operation.status == "running":
                raise BrokerError("command_already_running", "A running command cannot be cancelled")
            try:
                self._queue.remove(command_id)
            except ValueError as error:
                raise BrokerError("command_not_cancellable", "Command is not queued") from error
            command = operation.command
            operation.status = "cancelled"
            operation.receipt = CommandReceipt(
                command_id=command.command_id,
                command_type=command.command_type,
                project_id=command.project_id,
                engine_session_id=command.engine_session_id,
                stage_epoch=command.stage_epoch,
                status="cancelled",
                error_code="cancelled_by_product",
                message="Command cancelled before engine claim",
            )
            return operation.public()

    def record_receipt(self, receipt: CommandReceipt) -> None:
        checked = CommandReceipt.from_dict(receipt.to_dict())
        with self._lock:
            operation = self._operations.get(checked.command_id)
            if operation is None:
                raise BrokerError("receipt_unknown", "Receipt command is unknown", status=404)
            if operation.receipt is not None:
                if operation.receipt.to_dict() == checked.to_dict():
                    return
                raise BrokerError("receipt_duplicate_conflict", "Final receipt content changed")
            command = operation.command
            if any((
                checked.command_type != command.command_type,
                checked.project_id != command.project_id,
                checked.engine_session_id != command.engine_session_id,
                checked.stage_epoch != command.stage_epoch,
            )):
                raise BrokerError("receipt_identity_mismatch", "Receipt identity does not match command")
            if (command.command_type == "build_scene" and checked.status == "succeeded"
                    and checked.applied_revision != command.expected_applied_revision):
                raise BrokerError("receipt_revision_mismatch", "Build receipt revision does not match command")
            operation.receipt = checked
            operation.status = checked.status
            if self._inflight == checked.command_id:
                self._inflight = None

    def record_snapshot(self, snapshot: SimulationSnapshot) -> None:
        checked = SimulationSnapshot.from_dict(snapshot.to_dict())
        with self._lock:
            self._assert_engine(checked.engine_session_id, checked.stage_epoch)
            if checked.project_id != self.project_id:
                raise BrokerError("snapshot_project_mismatch", "Snapshot project is invalid")
            if self._snapshot is not None and checked.sequence <= self._snapshot.sequence:
                if self._snapshot.to_dict() == checked.to_dict():
                    return
                raise BrokerError("snapshot_sequence_stale", "Snapshot sequence must increase")
            self._snapshot = checked
            self._engine_heartbeat_at = self._clock()

    def public_state(self, product_session_id: str) -> dict[str, object]:
        with self._lock:
            self._expire_if_disconnected()
            operations = [item.public() for item in self._operations.values()
                          if item.product_session_id == product_session_id]
            return {
                "project_id": self.project_id,
                "engine_connected": self._engine_connected(),
                "engine_session_id": self._engine_session_id,
                "stage_epoch": self._stage_epoch,
                "lease_owned": self._lease_valid() and self._lease_owner == product_session_id,
                "control_lease_id": self._lease_id if self._lease_owner == product_session_id else None,
                "snapshot": self._snapshot.to_dict() if self._snapshot is not None else None,
                "operations": operations,
                "artifacts": [
                    {"artifact_id": item.artifact_id, "revision": item.revision}
                    for item in self._artifacts.values()
                ],
            }

    def _assert_product_control(self, product_session_id: str) -> None:
        if not self._lease_valid() or self._lease_owner != product_session_id:
            raise BrokerError("control_lease_required", "An active control lease is required")

    def _assert_engine(self, engine_session_id: str, stage_epoch: str) -> None:
        if self._engine_session_id != engine_session_id:
            raise BrokerError("engine_session_stale", "Engine session is not current", status=401)
        if self._stage_epoch != stage_epoch:
            raise BrokerError("stage_epoch_stale", "Stage epoch is not current")

    def _assert_engine_connected(self) -> None:
        if not self._engine_connected():
            raise BrokerError("engine_disconnected", "Isaac engine is not connected", status=503)

    def _engine_connected(self) -> bool:
        return bool(self._engine_session_id and self._clock() - self._engine_heartbeat_at <= self.engine_timeout_s)

    def _lease_valid(self) -> bool:
        return bool(self._lease_id and self._clock() < self._lease_expires_at)

    def _expire_if_disconnected(self) -> None:
        if self._engine_session_id and not self._engine_connected():
            self._expire_engine_operations("engine_disconnected")

    def _expire_engine_operations(self, code: str) -> None:
        for command_id in list(self._queue) + ([self._inflight] if self._inflight else []):
            if command_id is None:
                continue
            operation = self._operations.get(command_id)
            if operation is None or operation.receipt is not None:
                continue
            command = operation.command
            operation.status = "unknown" if command_id == self._inflight else "expired"
            operation.receipt = CommandReceipt(
                command_id=command.command_id, command_type=command.command_type,
                project_id=command.project_id, engine_session_id=command.engine_session_id,
                stage_epoch=command.stage_epoch, status=operation.status,
                error_code=code, message="Engine identity changed before a final receipt",
            )
        self._queue.clear()
        self._inflight = None

    def _trim_operations(self) -> None:
        while len(self._operations) > self.operation_limit:
            command_id, operation = next(iter(self._operations.items()))
            if command_id == self._inflight or command_id in self._queue:
                break
            self._operations.popitem(last=False)
            for request_id, (_digest, mapped_id) in list(self._request_ids.items()):
                if mapped_id == command_id:
                    del self._request_ids[request_id]
