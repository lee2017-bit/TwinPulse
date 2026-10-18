# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Manual, scan-informed XY draft edits, never automatic alignment or authority.

The reviewer identifies SAME stationary object landmarks and original scan beams.
This limited translation-only fit checks internal consistency; it cannot prove the
association, TF calibration, or stationary capture. App/Isaac execution is separate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math

from .revisions import canonical_sha256
from .scan_recording import ScanRecording
from .site_contracts import SitePlan

POLICY_ID = "offline_manual_xy_translation_v1"
MAX_TRANSLATION_M = .5
MAX_RESIDUAL_M = .03
MIN_LANDMARK_SPAN_M = .05


def plan_revision(plan: SitePlan) -> str:
    return canonical_sha256(plan.to_dict())


@dataclass(frozen=True)
class LandmarkPair:
    frame_index: int
    beam_index: int
    # Local XY on the selected box perimeter, not its centre or robot returns.
    object_local_xy_m: tuple[float, float]

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or self.frame_index < 0 or type(self.beam_index) is not int or self.beam_index < 0:
            raise ValueError("landmark indices must be nonnegative integers")
        if (type(self.object_local_xy_m) is not tuple or len(self.object_local_xy_m) != 2
                or any(type(v) not in (int, float) or not -100 <= v <= 100 for v in self.object_local_xy_m)):
            raise ValueError("landmark must be a finite immutable local XY pair")


@dataclass(frozen=True)
class CorrectionProposal:
    parent_plan_revision: str
    parent_scene_revision: str
    recording_revision: str
    provenance: str
    object_id: str
    pairs: tuple[LandmarkPair, ...]
    delta_xy_m: tuple[float, float]
    max_residual_m: float
    policy_id: str = POLICY_ID

    @property
    def revision(self) -> str:
        return canonical_sha256(asdict(self))

    def preview(self) -> dict:
        return {**asdict(self), "revision": self.revision,
                "mode": "manual_offline_draft_proposal", "source_verified": False,
                "alignment_verified": False, "motion_authorized": False, "demo_ready": False,
                "physical_validation": "NOT_RUN",
                "invalidates_on_apply": ["navigation_map", "mission", "prior_review", "prior_build_identity"],
                "limits": "Translation consistency only. Reviewer associations, TF and stationary capture remain unverified."}


def propose_xy_correction(plan: SitePlan, recording: ScanRecording, *, object_id: str,
                          pairs: tuple[LandmarkPair, ...]) -> CorrectionProposal:
    if not isinstance(plan, SitePlan) or not isinstance(recording, ScanRecording):
        raise ValueError("typed site and recording required")
    # Reject typed drafts whose digest would change on the existing persistence
    # parser (for example noncanonical integer-valued float geometry).
    SitePlan.from_dict(plan.to_dict())
    if plan.robot is None:
        raise ValueError("explicit robot-profile binding required")
    if (recording.site_id != plan.scene.id or recording.scene_revision != plan.scene.revision
            or recording.robot_profile_digest != plan.robot.profile_digest):
        raise ValueError("recording does not match the current site/scene/profile")
    if not isinstance(object_id, str):
        raise ValueError("explicit stable object id required")
    obj = next((item for item in plan.scene.objects if item.id == object_id), None)
    if (obj is None or obj.kind not in {"wall", "rack", "box", "equipment"}
            or obj.dynamic or not obj.collision or obj.shape.type != "box"):
        raise ValueError("only existing static collidable boxes may be translated")
    if any(abs(v) > 1e-9 for v in obj.transform.rotation_rpy_deg[:2]):
        raise ValueError("tilted objects require a 3D review, not planar translation")
    if type(pairs) is not tuple or not 2 <= len(pairs) <= 16 or any(not isinstance(p, LandmarkPair) for p in pairs):
        raise ValueError("2..16 explicit immutable landmark correspondences required")
    if len({p.frame_index for p in pairs}) != 1:
        raise ValueError("correspondences must use one stationary snapshot")
    if len({p.beam_index for p in pairs}) != len(pairs) or len({p.object_local_xy_m for p in pairs}) != len(pairs):
        raise ValueError("duplicate beams or model landmarks are ambiguous")
    yaw = math.radians(obj.transform.rotation_rpy_deg[2])
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    hx, hy = (v / 2 for v in obj.shape.dimensions_m[:2])
    model_points, observed_points, offsets = [], [], []
    for pair in pairs:
        if pair.frame_index >= len(recording.frames):
            raise ValueError("unknown frame index")
        lx, ly = pair.object_local_xy_m
        if (abs(lx) > hx + 1e-9 or abs(ly) > hy + 1e-9
                or min(abs(abs(lx) - hx), abs(abs(ly) - hy)) > 1e-9):
            raise ValueError("model landmark must lie on the selected box XY perimeter")
        observed = recording.frames[pair.frame_index].world_point(pair.beam_index)
        model = (obj.transform.position_m[0] + cos_yaw * lx - sin_yaw * ly,
                 obj.transform.position_m[1] + sin_yaw * lx + cos_yaw * ly)
        model_points.append(model)
        observed_points.append(observed)
        offsets.append((observed[0] - model[0], observed[1] - model[1]))
    for points in (model_points, observed_points):
        span = max(math.dist(a, b) for a in points for b in points)
        if span < MIN_LANDMARK_SPAN_M:
            raise ValueError("landmark span is insufficient")
    delta = tuple(sum(offset[axis] for offset in offsets) / len(offsets) for axis in (0, 1))
    residual = max(math.dist(offset, delta) for offset in offsets)
    if residual > MAX_RESIDUAL_M:
        raise ValueError("correspondences do not support a consistent translation")
    if math.hypot(*delta) > MAX_TRANSLATION_M or math.hypot(*delta) < 1e-6:
        raise ValueError("translation is zero or exceeds offline draft policy")
    proposal = CorrectionProposal(plan_revision(plan), plan.scene.revision, recording.revision,
                                  recording.provenance, obj.id, pairs, delta, residual)
    _translated_plan(plan, proposal)  # Revalidate geometry before presenting a proposal.
    return proposal


def _translated_plan(plan: SitePlan, proposal: CorrectionProposal) -> SitePlan:
    objects = []
    for obj in plan.scene.objects:
        if obj.id == proposal.object_id:
            x, y, z = obj.transform.position_m
            obj = replace(obj, transform=replace(obj.transform, position_m=(
                x + proposal.delta_xy_m[0], y + proposal.delta_xy_m[1], z)))
        objects.append(obj)
    # A manually reviewed inference, not a claim of authenticated scan geometry.
    scene = replace(plan.scene, objects=tuple(objects), source="manual",
                    source_ref=proposal.revision, parent_revision=plan.scene.revision)
    return replace(plan, scene=scene, navigation_map=None, mission=None, review_required=True)


@dataclass(frozen=True)
class AppliedCorrection:
    before: SitePlan
    after: SitePlan
    proposal: CorrectionProposal

    @property
    def revision(self) -> str:
        return canonical_sha256({"before": plan_revision(self.before), "after": plan_revision(self.after),
                                 "proposal": self.proposal.revision})


def apply_xy_correction(plan: SitePlan, recording: ScanRecording, proposal: CorrectionProposal,
                        *, reviewed_proposal_revision: str) -> AppliedCorrection:
    """Pure draft change. The digest binds a UI review, but is not authentication."""
    if not isinstance(proposal, CorrectionProposal) or reviewed_proposal_revision != proposal.revision:
        raise ValueError("review of this exact correction proposal required")
    if proposal.parent_plan_revision != plan_revision(plan):
        raise ValueError("stale correction: site plan changed after proposal")
    fresh = propose_xy_correction(plan, recording, object_id=proposal.object_id, pairs=proposal.pairs)
    if fresh.revision != proposal.revision:
        raise ValueError("correction changed or recording no longer matches")
    return AppliedCorrection(plan, _translated_plan(plan, fresh), fresh)


def undo_xy_correction(current: SitePlan, applied: AppliedCorrection, *, reviewed_edit_revision: str) -> SitePlan:
    """Restore geometry as a NEW child revision, never old map/mission/approval."""
    if not isinstance(applied, AppliedCorrection) or reviewed_edit_revision != applied.revision:
        raise ValueError("review of this exact applied edit required")
    if plan_revision(current) != plan_revision(applied.after):
        raise ValueError("stale undo: site plan changed after correction")
    if _translated_plan(applied.before, applied.proposal) != applied.after:
        raise ValueError("inconsistent applied correction receipt")
    restored = replace(applied.before.scene, source="manual", source_ref=applied.revision,
                       parent_revision=current.scene.revision)
    return replace(current, scene=restored, navigation_map=None, mission=None, review_required=True)
