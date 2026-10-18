# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded native-angle recording for inspection, never a world-aligned map.

No I/O or control dependencies. Hashes are provenance claims until checked against
source bytes. Host observation windows must not become beam acquisition times.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re

MAX_NATIVE_BYTES = 8 * 1024 * 1024
MAX_NATIVE_SAMPLES = 50000


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError("unsupported native scan fields")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("native scan integer outside bounds")


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError("native scan number outside bounds")


def _digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("native scan SHA-256 required")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate native scan field")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonfinite native scan JSON")


def usable_return(beam):
    """Retain the recorded decoder's zero/short-low-quality exclusion rule."""
    return beam["distance_m"] > 0 and not (beam["distance_m"] <= .15 and beam["quality"] <= 65)


@dataclass(frozen=True)
class NativeScanBundle:
    _json: str

    @classmethod
    def from_text(cls, text):
        if type(text) is not str or len(text) > MAX_NATIVE_BYTES or len(text.encode("utf-8")) > MAX_NATIVE_BYTES:
            raise ValueError("native scan bundle exceeds 8 MiB or is not text")
        try:
            value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
            return cls.from_dict(value)
        except (RecursionError, OverflowError) as exc:
            raise ValueError("invalid native scan nesting or number") from exc

    @classmethod
    def from_dict(cls, value):
        _shape(value, "schema_version source frames photos display_hypotheses")
        if value["schema_version"] != "native-scan-bundle-1.0":
            raise ValueError("unsupported native scan version")
        source = value["source"]
        _shape(source, "kind raw_sha256 nodes_sha256 observation_start_utc observation_end_utc timestamp_basis")
        if source["kind"] not in ("saved_sensor_recording", "synthetic_test_fixture"):
            raise ValueError("explicit native scan provenance required")
        for key in ("raw_sha256", "nodes_sha256"):
            _digest(source[key])
        times = []
        for key in ("observation_start_utc", "observation_end_utc"):
            stamp = source[key]
            if type(stamp) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp) is None:
                raise ValueError("UTC observation window required")
            times.append(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
        if not 0 < (times[1] - times[0]).total_seconds() <= 3600:
            raise ValueError("invalid observation window")
        if source["timestamp_basis"] != "host_observation_window_not_beam_time":
            raise ValueError("beam timing is not established")
        frames = value["frames"]
        if type(frames) is not list or not 1 <= len(frames) <= 100:
            raise ValueError("provide 1..100 complete recorded frames")
        previous_node, previous_cursor, count = -1, -1, 0
        for frame_index, frame in enumerate(frames):
            _shape(frame, "index beams")
            _integer(frame["index"], frame_index, frame_index)
            beams = frame["beams"]
            if type(beams) is not list or not 2 <= len(beams) <= 4096:
                raise ValueError("provide 2..4096 native beams per frame")
            count += len(beams)
            if count > MAX_NATIVE_SAMPLES:
                raise ValueError("native sample budget exceeded")
            for beam in beams:
                _shape(beam, "angle_deg distance_m quality node_index source_byte_cursor")
                _number(beam["angle_deg"], 0, 360)
                _number(beam["distance_m"], 0, 65.535)
                _integer(beam["quality"], 0, 255)
                _integer(beam["node_index"], previous_node + 1, 200000)
                _integer(beam["source_byte_cursor"], max(0, previous_cursor), 512 * 1024)
                previous_node, previous_cursor = beam["node_index"], beam["source_byte_cursor"]
        photos = value["photos"]
        if type(photos) is not list or len(photos) > 2:
            raise ValueError("at most two source photo bindings")
        roles = set()
        for photo in photos:
            _shape(photo, "role sha256 media_type same_position_user_declared window_direction")
            if photo["role"] not in ("room", "top_view") or photo["role"] in roles:
                raise ValueError("duplicate or unsupported photo role")
            roles.add(photo["role"])
            _digest(photo["sha256"])
            if photo["media_type"] != "image/jpeg" or type(photo["same_position_user_declared"]) is not bool:
                raise ValueError("invalid source photo binding")
            if photo["window_direction"] not in ("up", "unspecified"):
                raise ValueError("unsupported photo direction declaration")
        hypotheses = value["display_hypotheses"]
        if type(hypotheses) is not list or len(hypotheses) > 8:
            raise ValueError("at most eight display hypotheses")
        ids = set()
        for candidate in hypotheses:
            _shape(candidate, "id rotation_deg mirror_native_y")
            if type(candidate["id"]) is not str or re.fullmatch(r"(?:rotate|mirror)[0-3]", candidate["id"]) is None or candidate["id"] in ids:
                raise ValueError("invalid display hypothesis identity")
            ids.add(candidate["id"])
            _number(candidate["rotation_deg"], 0, 360)
            if type(candidate["mirror_native_y"]) is not bool:
                raise ValueError("invalid display reflection flag")
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_NATIVE_BYTES:
            raise ValueError("native scan bundle exceeds 8 MiB")
        return cls(encoded)

    @property
    def digest(self):
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()

    def to_dict(self):
        return json.loads(self._json)

    def frame_preview(self, frame_index):
        value = self.to_dict()
        _integer(frame_index, 0, len(value["frames"]) - 1)
        frame = value["frames"][frame_index]
        points = []
        for beam in frame["beams"]:
            if usable_return(beam):
                angle = math.radians(beam["angle_deg"])
                points.append({**beam, "x_m": beam["distance_m"] * math.cos(angle),
                               "y_m": beam["distance_m"] * math.sin(angle)})
        return {"index": frame_index, "samples": len(frame["beams"]),
                "invalid_returns": len(frame["beams"]) - len(points), "points": points}
