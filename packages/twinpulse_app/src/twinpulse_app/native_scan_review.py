# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only saved-native evidence, isolated from the active project and broker."""
from threading import RLock
from uuid import uuid4
from copy import deepcopy

from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core import WorldObservationRef
from twinpulse_core.native_scan_quality import analyze_native_scan
from twinpulse_core.native_scan_3d import export_native_frame_3d
from twinpulse_core.native_registration import propose_native_registration
from twinpulse_core.native_scan import _pairs, _constant
import json


class NativeScanReview:
    def __init__(self):
        self._lock = RLock()
        self._bundle = None
        self._analysis = None
        self._registration = None
        self._revision = uuid4().hex

    def import_bundle(self, text):
        bundle = NativeScanBundle.from_text(text)
        analysis = analyze_native_scan(bundle)
        with self._lock:
            self._bundle = bundle
            self._analysis = analysis
            self._registration = None
            self._revision = uuid4().hex
            return self.snapshot()

    def snapshot(self, frame_index=None, workspace_revision=None):
        with self._lock:
            if workspace_revision is not None and workspace_revision != self._revision:
                raise ValueError("native evidence changed; reload the review")
            result = {"schema_version": "native-scan-review-1.0", "workspace_revision": self._revision,
                      "mode": "saved_native_evidence_only", "source_bytes_verified": False,
                      "active_project_changed": False, "motion_authorized": False,
                      "demo_ready": False, "world_tf": None, "robot_heading": None,
                      "handedness_verified": False, "physical_validation": "NOT_RUN",
                      "notice": "Historical imported evidence. Native angles preserved. Missing returns are UNKNOWN. Display hypotheses are not TF or navigation maps."}
            if self._bundle is None:
                if frame_index is not None:
                    raise ValueError("import native evidence first")
                return {**result, "bundle": None, "frame": None, "analysis": None, "registration": None}
            data = self._bundle.to_dict()
            frame_index = len(data["frames"]) - 1 if frame_index is None else frame_index
            return {**result, "bundle": {"digest": self._bundle.digest, "source": data["source"],
                    "frame_count": len(data["frames"]), "sample_count": sum(len(f["beams"]) for f in data["frames"]),
                    "photos": data["photos"], "display_hypotheses": data["display_hypotheses"]},
                    "frame": self._bundle.frame_preview(frame_index), "analysis": deepcopy(self._analysis),
                    "registration": deepcopy(self._registration) if self._registration and self._registration['frame_index'] == frame_index else None}

    def export_bundle(self):
        with self._lock:
            if self._bundle is None:
                raise ValueError("import native evidence first")
            return self._bundle.to_dict()

    def world_reference(self):
        """Return source identity only; no transform, metric alignment or motion grant."""
        with self._lock:
            return {"workspace_revision": self._revision,
                    "reference": (WorldObservationRef.for_native_scan(self._bundle).to_dict()
                                  if self._bundle is not None else None)}

    def select_frame(self, frame_index, workspace_revision):
        if type(frame_index) is not int or type(workspace_revision) is not str:
            raise ValueError("explicit integer frame and workspace revision required")
        return self.snapshot(frame_index, workspace_revision)

    def export_3d(self, frame_index, workspace_revision):
        with self._lock:
            self.select_frame(frame_index, workspace_revision)
            return export_native_frame_3d(self._bundle, frame_index)

    def propose_registration(self, workspace_revision, frame_index, reference_text):
        if type(reference_text) is not str or len(reference_text.encode('utf-8')) > 65536:
            raise ValueError('reference JSON must be at most 64 KiB')
        try:
            request = json.loads(reference_text, object_pairs_hook=_pairs, parse_constant=_constant)
        except (RecursionError, OverflowError) as exc:
            raise ValueError('invalid reference JSON') from exc
        with self._lock:
            self.select_frame(frame_index, workspace_revision)
            proposal = propose_native_registration(self._bundle, request)
            if proposal['frame_index'] != frame_index:
                raise ValueError('reference does not match the selected native frame')
            self._registration = proposal
            self._revision = uuid4().hex
            return self.snapshot(frame_index)
