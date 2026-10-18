# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H3b photo-to-physical-track evidence contract; no scan or robot permission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Mapping

from .revisions import InputRevision, canonical_sha256


PHOTO_TRACK_VERSION = "1.0"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{label} shape is unsupported")


@dataclass(frozen=True, slots=True)
class TrackMeasurement:
    """A human-measured horizontal span, never a monocular estimate."""

    axis: str
    length_m: float
    uncertainty_m: float
    method: str

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"} or self.method not in {"tape", "laser", "survey"}:
            raise ValueError("measurement axis or method is unsupported")
        for name, value in (("length", self.length_m), ("uncertainty", self.uncertainty_m)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"measurement {name} must be finite")
        if not 0 < self.length_m <= 100 or not 0 <= self.uncertainty_m < self.length_m:
            raise ValueError("measurement length or uncertainty is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrackMeasurement":
        _exact(value, {"axis", "length_m", "uncertainty_m", "method"}, "track measurement")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class PhotoTrackManifest:
    """Bind one photo input to one actual TurtleBot test site for human review.

    A same-site declaration is not proof of geometry, scan alignment, or safe motion.
    Pixel-to-metre scale is deliberately absent.
    """

    site_id: str
    photo_input_digest: str | None = None
    photo_sha256: str | None = None
    photo_site_confirmed: bool = False
    measurements: tuple[TrackMeasurement, ...] = ()
    origin_marker: str | None = None
    positive_x_marker: str | None = None
    relationship: str = "same_physical_site"
    schema_version: str = PHOTO_TRACK_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.site_id, str) or not _ID.fullmatch(self.site_id):
            raise ValueError("site id is invalid")
        if self.schema_version != PHOTO_TRACK_VERSION or self.relationship != "same_physical_site":
            raise ValueError("photo-track version or relationship is unsupported")
        if (self.photo_input_digest is None) != (self.photo_sha256 is None):
            raise ValueError("photo digest and image hash must be supplied together")
        for label, value in (("photo input", self.photo_input_digest), ("photo image", self.photo_sha256)):
            if value is not None and (not isinstance(value, str) or not _SHA256.fullmatch(value)):
                raise ValueError(f"{label} must be a SHA-256 digest")
        if type(self.photo_site_confirmed) is not bool or (self.photo_site_confirmed and self.photo_input_digest is None):
            raise ValueError("photo-site confirmation requires a bound photo")
        if not isinstance(self.measurements, tuple) or any(not isinstance(m, TrackMeasurement) for m in self.measurements):
            raise ValueError("measurements must be immutable records")
        axes = [m.axis for m in self.measurements]
        if len(axes) != len(set(axes)):
            raise ValueError("measurement axes must be unique")
        for label, value in (("origin", self.origin_marker), ("positive x", self.positive_x_marker)):
            if value is not None and (not isinstance(value, str) or not _ID.fullmatch(value)):
                raise ValueError(f"{label} marker is invalid")
        if self.origin_marker is not None and self.origin_marker == self.positive_x_marker:
            raise ValueError("coordinate markers must be distinct")

    def verify_input(self, revision: InputRevision) -> None:
        """Reject a stale, text-only, drawing, or different-photo input."""
        validated = InputRevision.from_dict(revision.to_dict())
        if (validated.input_kind != "photo" or len(validated.images) != 1
                or validated.digest != self.photo_input_digest
                or validated.images[0]["sha256"] != self.photo_sha256):
            raise ValueError("photo-track manifest does not match the photo input revision")

    @property
    def review_gaps(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if self.photo_input_digest is None:
            gaps.append("actual_site_photo")
        if not self.photo_site_confirmed:
            gaps.append("same_site_confirmation")
        axes = {m.axis for m in self.measurements}
        for axis in ("x", "y"):
            if axis not in axes:
                gaps.append(f"measured_{axis}_span")
        if self.origin_marker is None:
            gaps.append("origin_marker")
        if self.positive_x_marker is None:
            gaps.append("positive_x_marker")
        return tuple(gaps)

    @property
    def ready_for_photo_review(self) -> bool:
        """Photo/site binding only; manual dimensions are not a generation prerequisite."""
        return self.photo_input_digest is not None and self.photo_site_confirmed

    @property
    def ready_for_manual_alignment_review(self) -> bool:
        """Optional manual-evidence route; not required for connection or scan collection."""
        return not self.review_gaps

    @property
    def ready_for_alignment_review(self) -> bool:
        """Compatibility alias for manual evidence completeness, not a global gate."""
        return self.ready_for_manual_alignment_review

    def _body(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "site_id": self.site_id,
                "relationship": self.relationship, "photo_input_digest": self.photo_input_digest,
                "photo_sha256": self.photo_sha256, "photo_site_confirmed": self.photo_site_confirmed,
                "measurements": [asdict(m) for m in self.measurements],
                "origin_marker": self.origin_marker, "positive_x_marker": self.positive_x_marker}

    @property
    def revision(self) -> str:
        return canonical_sha256(self._body())

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "revision": self.revision}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PhotoTrackManifest":
        _exact(value, {"schema_version", "site_id", "relationship", "photo_input_digest",
                       "photo_sha256", "photo_site_confirmed", "measurements", "origin_marker",
                       "positive_x_marker", "revision"}, "photo-track manifest")
        if not isinstance(value["measurements"], list):
            raise ValueError("measurements must be an array")
        manifest = cls(site_id=value["site_id"], relationship=value["relationship"],
                       photo_input_digest=value["photo_input_digest"], photo_sha256=value["photo_sha256"],
                       photo_site_confirmed=value["photo_site_confirmed"],
                       measurements=tuple(TrackMeasurement.from_dict(m) for m in value["measurements"]),
                       origin_marker=value["origin_marker"], positive_x_marker=value["positive_x_marker"],
                       schema_version=value["schema_version"])
        if value["revision"] != manifest.revision:
            raise ValueError("photo-track manifest digest mismatch")
        return manifest
