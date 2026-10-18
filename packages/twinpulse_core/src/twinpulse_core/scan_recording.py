# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, offline, stationary 2D scan replay. No ROS or device transport.

This is an internal interchange contract, NOT a ROS LaserScan decoder. A future
adapter must explicitly normalize units/invalid ranges and establish stationary
capture. Submitted provenance and transforms are claims, not authenticated facts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re

from .revisions import canonical_sha256

MAX_BYTES = 4 * 1024 * 1024
MAX_FRAMES = 32
MAX_BEAMS = 4096
MAX_TF_SKEW_NS = 50_000_000  # Input synchronization bound, not alignment accuracy.
CONVENTION = "right_handed_x_forward_y_left_z_up_metres_radians"


def _fields(value: object, names: str) -> dict:
    if type(value) is not dict or set(value) != set(names.split()):
        raise ValueError("unexpected or missing scan contract fields")
    return value


def _number(value: object, lower: float, upper: float) -> None:
    if type(value) not in (int, float) or not lower <= value <= upper or not math.isfinite(value):
        raise ValueError("scan numeric value outside finite bounds")


def _stamp(value: object) -> None:
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError("timestamp must be positive integer nanoseconds")


def _id(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value) is None:
        raise ValueError("invalid scan identifier")


def _digest(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid revision digest")


@dataclass(frozen=True)
class Transform2D:
    source_frame: str
    target_frame: str
    stamp_ns: int
    clock_id: str
    x_m: float
    y_m: float
    yaw_rad: float

    def __post_init__(self) -> None:
        _id(self.source_frame)
        _id(self.clock_id)
        if self.source_frame == "world" or self.target_frame != "world":
            raise ValueError("transform must map a sensor frame into world")
        _stamp(self.stamp_ns)
        _number(self.x_m, -100, 100)
        _number(self.y_m, -100, 100)
        _number(self.yaw_rad, -math.pi, math.pi)

    @classmethod
    def from_dict(cls, value: dict) -> Transform2D:
        return cls(**_fields(value, "source_frame target_frame stamp_ns clock_id x_m y_m yaw_rad"))


@dataclass(frozen=True)
class ScanFrame:
    stamp_ns: int
    frame_id: str
    clock_id: str
    angle_min_rad: float
    angle_increment_rad: float
    range_min_m: float
    range_max_m: float
    time_increment_ns: int
    ranges_m: tuple[float | None, ...]
    world_from_sensor: Transform2D

    def __post_init__(self) -> None:
        _stamp(self.stamp_ns)
        _id(self.frame_id)
        _id(self.clock_id)
        _number(self.angle_min_rad, -math.pi, math.pi)
        _number(self.angle_increment_rad, 1e-9, math.tau)
        _number(self.range_min_m, .001, 100)
        _number(self.range_max_m, .001, 100)
        if self.range_min_m >= self.range_max_m:
            raise ValueError("range bounds are reversed")
        if type(self.time_increment_ns) is not int or self.time_increment_ns != 0:
            raise ValueError("rolling/moving scans require deskew; unsupported in stationary replay")
        if type(self.ranges_m) is not tuple or not 1 <= len(self.ranges_m) <= MAX_BEAMS:
            raise ValueError("beam count outside bounds")
        if (len(self.ranges_m) - 1) * self.angle_increment_rad > math.tau + 1e-9:
            raise ValueError("scan angular span exceeds one revolution")
        for distance in self.ranges_m:
            if distance is not None:
                _number(distance, self.range_min_m, self.range_max_m)
        tf = self.world_from_sensor
        if not isinstance(tf, Transform2D) or tf.source_frame != self.frame_id or tf.clock_id != self.clock_id:
            raise ValueError("transform frame/clock mismatch")
        if abs(tf.stamp_ns - self.stamp_ns) > MAX_TF_SKEW_NS:
            raise ValueError("transform timestamp outside synchronization bound")

    @classmethod
    def from_dict(cls, value: dict) -> ScanFrame:
        data = dict(_fields(value, "stamp_ns frame_id clock_id angle_min_rad angle_increment_rad range_min_m range_max_m time_increment_ns ranges_m world_from_sensor"))
        if type(data["ranges_m"]) is not list or len(data["ranges_m"]) > MAX_BEAMS:
            raise ValueError("ranges_m must be a bounded JSON array")
        data["ranges_m"] = tuple(data["ranges_m"])
        data["world_from_sensor"] = Transform2D.from_dict(data["world_from_sensor"])
        return cls(**data)

    def world_point(self, beam_index: int) -> tuple[float, float]:
        """Project an original beam, never a downsampled preview index."""
        if type(beam_index) is not int or not 0 <= beam_index < len(self.ranges_m):
            raise ValueError("invalid original beam index")
        distance = self.ranges_m[beam_index]
        if distance is None:
            raise ValueError("missing beam cannot establish a correspondence")
        tf = self.world_from_sensor
        angle = self.angle_min_rad + beam_index * self.angle_increment_rad + tf.yaw_rad
        return tf.x_m + distance * math.cos(angle), tf.y_m + distance * math.sin(angle)


@dataclass(frozen=True)
class ScanRecording:
    site_id: str
    scene_revision: str
    robot_profile_digest: str
    session_id: str
    clock_id: str
    provenance: str
    frames: tuple[ScanFrame, ...]
    capture_mode: str = "stationary_snapshot"
    convention: str = CONVENTION
    schema_version: str = "scan-recording-1.0"

    def __post_init__(self) -> None:
        for value in (self.site_id, self.session_id, self.clock_id):
            _id(value)
        _digest(self.scene_revision)
        _digest(self.robot_profile_digest)
        if self.provenance not in ("synthetic", "simulation", "recorded_sensor"):
            raise ValueError("explicit scan provenance required")
        if self.capture_mode != "stationary_snapshot" or self.convention != CONVENTION or self.schema_version != "scan-recording-1.0":
            raise ValueError("unsupported scan contract/convention/capture mode")
        if type(self.frames) is not tuple or not 1 <= len(self.frames) <= MAX_FRAMES:
            raise ValueError("frame count outside bounds")
        previous = 0
        source = None
        for frame in self.frames:
            if not isinstance(frame, ScanFrame) or frame.clock_id != self.clock_id:
                raise ValueError("scan recording clock mismatch")
            if frame.stamp_ns <= previous:
                raise ValueError("scan timestamps must strictly increase within a session")
            if source is not None and source != frame.frame_id:
                raise ValueError("mixed sensor frames are unsupported")
            previous, source = frame.stamp_ns, frame.frame_id

    def to_dict(self) -> dict:
        # Return independent JSON values, never an alias to mutable input.
        return json.loads(json.dumps(asdict(self), allow_nan=False))

    @property
    def revision(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict) -> ScanRecording:
        data = dict(_fields(value, "site_id scene_revision robot_profile_digest session_id clock_id provenance frames capture_mode convention schema_version"))
        if type(data["frames"]) is not list or len(data["frames"]) > MAX_FRAMES:
            raise ValueError("frames must be a bounded JSON array")
        data["frames"] = tuple(ScanFrame.from_dict(frame) for frame in data["frames"])
        return cls(**data)

    @classmethod
    def from_json(cls, payload: bytes) -> ScanRecording:
        if type(payload) is not bytes or len(payload) > MAX_BYTES:
            raise ValueError("scan recording exceeds byte limit")

        def unique(pairs: list) -> dict:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate scan JSON field")
                result[key] = value
            return result

        def invalid_constant(value: str) -> None:
            raise ValueError("non-finite JSON scan constant")

        try:
            decoded = json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                                 parse_constant=invalid_constant)
            return cls.from_dict(decoded)
        except (UnicodeError, RecursionError, OverflowError) as exc:
            raise ValueError("invalid scan JSON encoding or nesting") from exc

    def replay(self, *, site_id: str, scene_revision: str, robot_profile_digest: str,
               max_points: int = 2048) -> dict:
        """Deterministic bounded review preview, never an occupancy/authority update.

        Invalid or occluded beams contribute no point AND no free-space evidence.
        Frame and beam indices survive sampling for explicit future correspondence.
        Caller must supply the currently reviewed site's immutable identities.
        """
        if (site_id, scene_revision, robot_profile_digest) != (self.site_id, self.scene_revision, self.robot_profile_digest):
            raise ValueError("scan belongs to a different site, scene revision or robot profile")
        if type(max_points) is not int or not 1 <= max_points <= 2048:
            raise ValueError("preview point budget must be 1..2048")
        valid = sum(distance is not None for frame in self.frames for distance in frame.ranges_m)
        stride = max(1, math.ceil(valid / max_points))
        points = []
        ordinal = 0
        for frame_index, frame in enumerate(self.frames):
            for beam_index, distance in enumerate(frame.ranges_m):
                if distance is None:
                    continue
                if ordinal % stride == 0:
                    x_m, y_m = frame.world_point(beam_index)
                    points.append({"frame_index": frame_index, "beam_index": beam_index,
                                   "stamp_ns": frame.stamp_ns,
                                   "x_m": x_m, "y_m": y_m})
                ordinal += 1
        return {"schema_version": "scan-preview-1.0", "recording_revision": self.revision,
                "site_id": self.site_id, "scene_revision": self.scene_revision,
                "robot_profile_digest": self.robot_profile_digest, "session_id": self.session_id,
                "mode": "offline_replay", "provenance": self.provenance,
                "source_verified": False, "alignment_verified": False,
                "physical_validation": "NOT_RUN", "motion_authorized": False, "demo_ready": False,
                "frame_id": "world", "frame_count": len(self.frames),
                "valid_beams": valid, "invalid_beams": sum(len(f.ranges_m) for f in self.frames) - valid,
                "sample_stride": stride, "points": points,
                "limitations": ["Submitted stationary capture and transforms are unverified claims.",
                                "No free-space, height, obstacle deletion or scene correction inferred.",
                                "No automatic alignment, navigation map or live device connection."]}
