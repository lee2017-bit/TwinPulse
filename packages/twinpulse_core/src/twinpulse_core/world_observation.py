# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Source-bound observation references, never world alignment or motion grants.

This envelope is deliberately outside the existing model observation 1.0 and
native scan 1.0 serialization. It does not reinterpret image estimates as
metric measurements or host scan windows as beam acquisition timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .revisions import canonical_sha256


_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_RULES = {
    "model_photo": ("image_unregistered", "none", "photo_estimate_only"),
    "saved_native_scan": ("native_scan_unregistered", "host_window_not_beam_time",
                          "sensor_ranges_unregistered"),
}


@dataclass(frozen=True, slots=True)
class WorldObservationRef:
    kind: str
    artifact_sha256: str
    source_sha256: str
    evidence_ids: tuple[str, ...]
    coordinate_frame: str
    time_basis: str
    metric_status: str
    schema_version: str = "world-observation-ref-1.0"
    alignment_verified: bool = False
    motion_authorized: bool = False

    def __post_init__(self) -> None:
        # Direct dataclass construction must not bypass the fail-closed parser.
        if (type(self.kind) is not str or self.kind not in _RULES
                or self.schema_version != "world-observation-ref-1.0"
                or type(self.artifact_sha256) is not str or not _HEX.fullmatch(self.artifact_sha256)
                or type(self.source_sha256) is not str or not _HEX.fullmatch(self.source_sha256)
                or type(self.evidence_ids) is not tuple or len(self.evidence_ids) > 24
                or any(type(item) is not str or not _ID.fullmatch(item) for item in self.evidence_ids)
                or len(set(self.evidence_ids)) != len(self.evidence_ids)
                or (self.kind == "saved_native_scan" and self.evidence_ids)
                or (self.coordinate_frame, self.time_basis, self.metric_status) != _RULES[self.kind]
                or self.alignment_verified is not False or self.motion_authorized is not False):
            raise ValueError("world observation reference cannot assert unsupported evidence or authority")

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "WorldObservationRef":
        fields = {"schema_version", "kind", "artifact_sha256", "source_sha256", "evidence_ids",
                  "coordinate_frame", "time_basis", "metric_status", "alignment_verified",
                  "motion_authorized"}
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ValueError("world observation reference shape is invalid")
        kind = value["kind"]
        if type(kind) is not str or kind not in _RULES or value["schema_version"] != "world-observation-ref-1.0":
            raise ValueError("world observation reference kind or version is invalid")
        if (type(value["artifact_sha256"]) is not str or not _HEX.fullmatch(value["artifact_sha256"])
                or type(value["source_sha256"]) is not str or not _HEX.fullmatch(value["source_sha256"])):
            raise ValueError("world observation source digest is invalid")
        ids = value["evidence_ids"]
        if (type(ids) is not list or len(ids) > 24
                or any(type(item) is not str or not _ID.fullmatch(item) for item in ids)
                or len(ids) != len(set(ids))
                or (kind == "saved_native_scan" and ids)):
            raise ValueError("world observation evidence IDs are invalid")
        if ((value["coordinate_frame"], value["time_basis"], value["metric_status"]) != _RULES[kind]
                or value["alignment_verified"] is not False or value["motion_authorized"] is not False):
            raise ValueError("observation reference cannot assert alignment or motion authority")
        return cls(kind=kind, artifact_sha256=value["artifact_sha256"],
                   source_sha256=value["source_sha256"], evidence_ids=tuple(ids),
                   coordinate_frame=value["coordinate_frame"], time_basis=value["time_basis"],
                   metric_status=value["metric_status"])

    @classmethod
    def for_model_photo(cls, observation_sha256: str, image_sha256: str,
                        evidence_ids: tuple[str, ...]) -> "WorldObservationRef":
        return cls.from_dict(dict(schema_version="world-observation-ref-1.0", kind="model_photo",
                                 artifact_sha256=observation_sha256, source_sha256=image_sha256,
                                 evidence_ids=list(evidence_ids),
                                 coordinate_frame="image_unregistered", time_basis="none",
                                 metric_status="photo_estimate_only", alignment_verified=False,
                                 motion_authorized=False))

    @classmethod
    def for_native_scan(cls, bundle) -> "WorldObservationRef":
        from .native_scan import NativeScanBundle
        if not isinstance(bundle, NativeScanBundle):
            raise ValueError("validated native scan bundle required")
        # Re-validate even a directly instantiated dataclass before deriving a ref.
        checked = NativeScanBundle.from_dict(bundle.to_dict())
        return cls.from_dict(dict(schema_version="world-observation-ref-1.0",
                                 kind="saved_native_scan", artifact_sha256=checked.digest,
                                 source_sha256=checked.to_dict()["source"]["raw_sha256"], evidence_ids=[],
                                 coordinate_frame="native_scan_unregistered",
                                 time_basis="host_window_not_beam_time",
                                 metric_status="sensor_ranges_unregistered",
                                 alignment_verified=False, motion_authorized=False))

    def require_visual_ids(self, ids: object) -> None:
        if (self.kind != "model_photo" or type(ids) is not list
                or any(type(item) is not str or item not in self.evidence_ids for item in ids)):
            raise ValueError("unobserved visual entity reference")

    def to_dict(self) -> dict[str, object]:
        return dict(schema_version=self.schema_version, kind=self.kind,
                    artifact_sha256=self.artifact_sha256, source_sha256=self.source_sha256,
                    evidence_ids=list(self.evidence_ids), coordinate_frame=self.coordinate_frame,
                    time_basis=self.time_basis, metric_status=self.metric_status,
                    alignment_verified=self.alignment_verified, motion_authorized=self.motion_authorized)

    @property
    def digest(self) -> str:
        return canonical_sha256(self.to_dict())
