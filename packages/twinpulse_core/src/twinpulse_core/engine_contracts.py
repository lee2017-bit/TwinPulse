# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure, versioned application-to-engine contracts.

These records intentionally contain no Isaac, HTTP, or UI objects.  R4 may
serialize them over a loopback bridge without changing the application rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any, Mapping, Protocol, runtime_checkable


ENGINE_SCHEMA_VERSION = "1.1"
COMMAND_TYPES = frozenset({"build_scene", "build_site_scene", "run", "pause", "reset", "focus_scene", "get_state"})
COMMAND_STATUSES = frozenset({"accepted", "running", "succeeded", "failed", "cancelled", "expired", "unknown"})
RUNTIME_STATES = frozenset({
    "disconnected", "idle", "built", "running", "paused", "completed",
    "off_route", "unstable", "stage_invalid", "error",
})


def _text(value: object, name: str, *, maximum: int = 256, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} is invalid")
    return value


def _finite(value: object, name: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _vector3(value: object, name: str, *, optional: bool = False) -> tuple[float, float, float] | None:
    if value is None and optional:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three values")
    return tuple(_finite(item, name) for item in value)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CommandEnvelope:
    command_id: str
    command_type: str
    project_id: str
    engine_session_id: str
    stage_epoch: str
    control_lease_id: str
    expected_applied_revision: str | None
    payload: Mapping[str, Any] = field(default_factory=dict)
    ttl_s: float = 30.0
    issued_at_unix_s: float = field(default_factory=time.time)
    schema_version: str = ENGINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGINE_SCHEMA_VERSION:
            raise ValueError("command schema version is unsupported")
        for value, name in (
            (self.command_id, "command_id"), (self.project_id, "project_id"),
            (self.engine_session_id, "engine_session_id"), (self.stage_epoch, "stage_epoch"),
            (self.control_lease_id, "control_lease_id"),
        ):
            _text(value, name)
        if self.command_type not in COMMAND_TYPES:
            raise ValueError("command_type is unsupported")
        _text(self.expected_applied_revision, "expected_applied_revision", optional=True)
        if not isinstance(self.payload, Mapping) or any(not isinstance(key, str) for key in self.payload):
            raise ValueError("command payload must be an object")
        ttl = _finite(self.ttl_s, "ttl_s")
        if ttl <= 0 or ttl > 300:
            raise ValueError("ttl_s is outside the supported range")
        issued = _finite(self.issued_at_unix_s, "issued_at_unix_s")
        if issued <= 0:
            raise ValueError("issued_at_unix_s is invalid")

    def expired(self, *, now_unix_s: float | None = None) -> bool:
        now = time.time() if now_unix_s is None else _finite(now_unix_s, "now_unix_s")
        return now > self.issued_at_unix_s + self.ttl_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "command_id": self.command_id,
            "command_type": self.command_type, "project_id": self.project_id,
            "engine_session_id": self.engine_session_id, "stage_epoch": self.stage_epoch,
            "control_lease_id": self.control_lease_id,
            "expected_applied_revision": self.expected_applied_revision,
            "payload": dict(self.payload), "ttl_s": self.ttl_s,
            "issued_at_unix_s": self.issued_at_unix_s,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CommandEnvelope":
        expected = {
            "schema_version", "command_id", "command_type", "project_id", "engine_session_id",
            "stage_epoch", "control_lease_id", "expected_applied_revision", "payload", "ttl_s",
            "issued_at_unix_s",
        }
        if set(value) != expected:
            raise ValueError("command envelope shape is unsupported")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    command_id: str
    command_type: str
    project_id: str
    engine_session_id: str
    stage_epoch: str
    status: str
    message: str = ""
    error_code: str | None = None
    applied_revision: str | None = None
    build_fingerprint: str | None = None
    schema_version: str = ENGINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGINE_SCHEMA_VERSION:
            raise ValueError("receipt schema version is unsupported")
        for value, name in (
            (self.command_id, "command_id"), (self.project_id, "project_id"),
            (self.engine_session_id, "engine_session_id"), (self.stage_epoch, "stage_epoch"),
        ):
            _text(value, name)
        if self.command_type not in COMMAND_TYPES or self.status not in COMMAND_STATUSES:
            raise ValueError("receipt command or status is unsupported")
        if not isinstance(self.message, str) or len(self.message) > 320:
            raise ValueError("receipt message is invalid")
        _text(self.error_code, "error_code", optional=True)
        _text(self.applied_revision, "applied_revision", optional=True)
        _text(self.build_fingerprint, "build_fingerprint", optional=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "command_id": self.command_id,
            "command_type": self.command_type, "project_id": self.project_id,
            "engine_session_id": self.engine_session_id, "stage_epoch": self.stage_epoch,
            "status": self.status, "message": self.message, "error_code": self.error_code,
            "applied_revision": self.applied_revision, "build_fingerprint": self.build_fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CommandReceipt":
        expected = {
            "schema_version", "command_id", "command_type", "project_id", "engine_session_id",
            "stage_epoch", "status", "message", "error_code", "applied_revision", "build_fingerprint",
        }
        if set(value) != expected:
            raise ValueError("command receipt shape is unsupported")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    engine_session_id: str
    stage_epoch: str
    project_id: str
    applied_revision: str | None
    run_id: str | None
    sequence: int
    runtime_state: str
    safety_state: str | None
    safety_reason: str | None
    permitted_commands: tuple[str, ...]
    capabilities: tuple[str, ...]
    sim_time_s: float | None = None
    sampled_at_utc: str | None = None
    frame_id: str = "world"
    position_m: tuple[float, float, float] | None = None
    yaw_rad: float | None = None
    roll_rad: float | None = None
    pitch_rad: float | None = None
    linear_speed_mps: float | None = None
    distance_to_goal_m: float | None = None
    cross_track_error_m: float | None = None
    telemetry_available: bool = False
    schema_version: str = ENGINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGINE_SCHEMA_VERSION:
            raise ValueError("snapshot schema version is unsupported")
        for value, name in (
            (self.engine_session_id, "engine_session_id"), (self.stage_epoch, "stage_epoch"),
            (self.project_id, "project_id"), (self.frame_id, "frame_id"),
        ):
            _text(value, name)
        _text(self.applied_revision, "applied_revision", optional=True)
        _text(self.run_id, "run_id", optional=True)
        _text(self.safety_state, "safety_state", optional=True)
        _text(self.safety_reason, "safety_reason", maximum=320, optional=True)
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("snapshot sequence is invalid")
        if self.runtime_state not in RUNTIME_STATES:
            raise ValueError("runtime_state is unsupported")
        if any(command not in COMMAND_TYPES for command in self.permitted_commands):
            raise ValueError("snapshot contains an unsupported permitted command")
        if not all(isinstance(item, str) and item for item in self.capabilities):
            raise ValueError("snapshot capabilities are invalid")
        _vector3(self.position_m, "position_m", optional=True)
        for value, name in (
            (self.sim_time_s, "sim_time_s"), (self.yaw_rad, "yaw_rad"),
            (self.roll_rad, "roll_rad"), (self.pitch_rad, "pitch_rad"),
            (self.linear_speed_mps, "linear_speed_mps"),
            (self.distance_to_goal_m, "distance_to_goal_m"),
            (self.cross_track_error_m, "cross_track_error_m"),
        ):
            _finite(value, name, optional=True)
        if not isinstance(self.telemetry_available, bool):
            raise ValueError("telemetry_available must be boolean")
        if not self.telemetry_available and any(value is not None for value in (
            self.position_m, self.yaw_rad, self.roll_rad, self.pitch_rad, self.linear_speed_mps,
            self.distance_to_goal_m, self.cross_track_error_m,
        )):
            raise ValueError("unavailable telemetry must use null values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "engine_session_id": self.engine_session_id,
            "stage_epoch": self.stage_epoch, "project_id": self.project_id,
            "applied_revision": self.applied_revision, "run_id": self.run_id,
            "sequence": self.sequence, "runtime_state": self.runtime_state,
            "safety_state": self.safety_state, "safety_reason": self.safety_reason,
            "permitted_commands": list(self.permitted_commands), "capabilities": list(self.capabilities),
            "sim_time_s": self.sim_time_s, "sampled_at_utc": self.sampled_at_utc,
            "frame_id": self.frame_id,
            "position_m": list(self.position_m) if self.position_m is not None else None,
            "yaw_rad": self.yaw_rad, "roll_rad": self.roll_rad, "pitch_rad": self.pitch_rad,
            "linear_speed_mps": self.linear_speed_mps,
            "distance_to_goal_m": self.distance_to_goal_m,
            "cross_track_error_m": self.cross_track_error_m,
            "telemetry_available": self.telemetry_available,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SimulationSnapshot":
        expected = {
            "schema_version", "engine_session_id", "stage_epoch", "project_id",
            "applied_revision", "run_id", "sequence", "runtime_state", "safety_state",
            "safety_reason", "permitted_commands", "capabilities", "sim_time_s",
            "sampled_at_utc", "frame_id", "position_m", "yaw_rad", "roll_rad", "pitch_rad",
            "linear_speed_mps", "distance_to_goal_m", "cross_track_error_m", "telemetry_available",
        }
        if set(value) != expected:
            raise ValueError("simulation snapshot shape is unsupported")
        data = dict(value)
        for name in ("permitted_commands", "capabilities"):
            if not isinstance(data[name], list):
                raise ValueError(f"snapshot {name} must be an array")
            data[name] = tuple(data[name])
        if data["position_m"] is not None:
            data["position_m"] = _vector3(data["position_m"], "position_m")
        return cls(**data)


# Implemented features and momentary permission are separate facts.  These
# requirements describe the existing Isaac adapter; they do not authorize a
# physical robot or infer a feature from a model/provider's metadata.
_ENGINE_FEATURE_REQUIREMENTS: dict[str, tuple[frozenset[str], str]] = {
    # Older bridge snapshots exposed "simulation" plus a permitted Build command.
    "legacy_scene_build": (frozenset({"simulation"}), "build_scene"),
    "site_scene_build_v2": (frozenset({"site_scene_build_v2"}), "build_site_scene"),
    "generation_room_visual_v1": (frozenset({"site_scene_build_v2", "generation_room_visual_v1"}), "build_site_scene"),
    "automatic_mission_visual_v1": (frozenset({"site_scene_build_v2", "automatic_mission_visual_v1"}), "build_site_scene"),
    "current_inspection_visual_v1": (frozenset({"site_scene_build_v2", "current_inspection_visual_v1"}), "build_site_scene"),
    "bedroom_visual_v1": (frozenset({"site_scene_build_v2", "bedroom_visual_v1"}), "build_site_scene"),
    "project_room_visual_v1": (frozenset({"site_scene_build_v2", "project_room_visual_v1"}),
                                "build_site_scene"),
    "bedroom_replay_v1": (frozenset({"site_scene_build_v2", "bedroom_visual_v1", "bedroom_replay_v1"}),
                          "build_site_scene"),
    "room_scan_replay_v1": (frozenset({"site_scene_build_v2", "bedroom_visual_v1", "room_scan_replay_v1"}),
                             "build_site_scene"),
}


@dataclass(frozen=True, slots=True)
class EngineFeatureReadiness:
    feature: str
    ready: bool
    code: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"feature": self.feature, "ready": self.ready, "code": self.code}


def evaluate_engine_feature(
    feature: str, *, snapshot: SimulationSnapshot | None, connected: bool,
    engine_session_id: str | None, stage_epoch: str | None,
) -> EngineFeatureReadiness:
    """Classify a requested simulation feature without granting run authority."""
    if feature not in _ENGINE_FEATURE_REQUIREMENTS:
        raise ValueError("engine feature is unsupported")
    if not connected:
        code = "runtime_disconnected"
    elif snapshot is None:
        code = "runtime_snapshot_missing"
    elif (snapshot.engine_session_id != engine_session_id or snapshot.stage_epoch != stage_epoch):
        code = "runtime_identity_stale"
    elif not _ENGINE_FEATURE_REQUIREMENTS[feature][0].issubset(snapshot.capabilities):
        code = "capability_unavailable"
    elif snapshot.safety_state is not None:
        code = "runtime_safety_latched"
    elif _ENGINE_FEATURE_REQUIREMENTS[feature][1] not in snapshot.permitted_commands:
        code = "runtime_command_unavailable"
    else:
        code = "ready"
    return EngineFeatureReadiness(feature, code == "ready", code)


@runtime_checkable
class SimulationPort(Protocol):
    """Application-facing engine port; concrete Isaac objects stay behind it."""

    def execute(self, command: CommandEnvelope) -> CommandReceipt: ...

    def snapshot(self) -> SimulationSnapshot: ...
