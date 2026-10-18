# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Session-local offline review sandbox. Never writes a project draft or broker.

Receipts remain server-owned. Import/export files are unverified evidence, not
build artifacts. Explicit archives replay bounded operations into a new isolated
workspace; they never restore execution approval or change an active project.
"""
import json
import hashlib
from dataclasses import asdict, replace
from threading import RLock
from uuid import uuid4

from twinpulse_core.scan_correction import (LandmarkPair, apply_xy_correction,
    plan_revision, propose_xy_correction, undo_xy_correction)
from twinpulse_core.scan_recording import ScanRecording
from twinpulse_core.site_contracts import SitePlan
from twinpulse_core.robot_profiles import resolve_robot_profile
from twinpulse_core.route_comparison import RouteCandidate, compare_routes, comparison_conditions
from twinpulse_core.map_refresh import propose_map_refresh, apply_map_refresh, undo_refreshed_correction
from twinpulse_core.revisions import canonical_sha256

MAX_BUNDLE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_ACTIONS = 16


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("unsupported offline review fields")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate offline review field")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("nonfinite JSON constant")


class ScanReview:
    def __init__(self):
        self._lock = RLock()
        self._revision = uuid4().hex
        self._base = self._plan = self._recording = self._preview = None
        self._proposal = self._applied = None
        self._comparison = None
        self._map_proposal = self._map_applied = None
        self._actions = []

    def _check(self, revision):
        if self._plan is None or revision != self._revision:
            raise ValueError("offline workspace changed; refresh and review again")

    def import_bundle(self, text):
        if type(text) is not str or len(text) > MAX_BUNDLE_BYTES or len(text.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise ValueError("offline bundle exceeds 5 MiB or is not JSON text")
        try:
            value = json.loads(text, object_pairs_hook=_unique, parse_constant=_nonfinite)
        except (RecursionError, OverflowError) as exc:
            raise ValueError("invalid offline bundle nesting") from exc
        _exact(value, ("schema_version", "site_plan", "recording"))
        if value["schema_version"] != "offline-scan-bundle-1.0":
            raise ValueError("unsupported offline bundle version")
        plan = replace(SitePlan.from_dict(value["site_plan"]), review_required=True)
        recording = ScanRecording.from_dict(value["recording"])
        if plan.robot is None:
            raise ValueError("bundle requires an explicit robot profile binding")
        preview = recording.replay(site_id=plan.scene.id, scene_revision=plan.scene.revision,
                                   robot_profile_digest=plan.robot.profile_digest)
        with self._lock:
            self._base = self._plan = plan
            self._recording, self._preview = recording, preview
            self._proposal = self._applied = None
            self._comparison = None
            self._map_proposal = self._map_applied = None
            self._actions = []
            self._revision = uuid4().hex
            return self.snapshot()

    def propose(self, revision, object_id, pairs):
        if type(pairs) is not list or not 2 <= len(pairs) <= 16:
            raise ValueError("provide 2..16 explicit landmark pairs")
        checked = []
        for pair in pairs:
            _exact(pair, ("frame_index", "beam_index", "object_local_xy_m"))
            if type(pair["object_local_xy_m"]) is not list:
                raise ValueError("local landmark coordinates must be a JSON array")
            checked.append(LandmarkPair(pair["frame_index"], pair["beam_index"], tuple(pair["object_local_xy_m"])))
        with self._lock:
            self._check(revision)
            proposed = propose_xy_correction(self._plan, self._recording, object_id=object_id, pairs=tuple(checked))
            self._proposal = proposed
            self._comparison = None
            self._map_proposal = None
            self._revision = uuid4().hex
            return self.snapshot()

    def apply(self, revision, proposal_revision):
        with self._lock:
            self._check(revision)
            self._check_history_capacity()
            if self._proposal is None:
                raise ValueError("no pending offline proposal")
            applied = apply_xy_correction(self._plan, self._recording, self._proposal,
                                          reviewed_proposal_revision=proposal_revision)
            self._actions.append({"action": "correction", "object_id": self._proposal.object_id,
                "pairs": [asdict(pair) for pair in self._proposal.pairs],
                "proposal_revision": self._proposal.revision, "result_plan_revision": plan_revision(applied.after)})
            self._plan, self._applied = applied.after, applied
            self._proposal = None
            self._comparison = None
            self._map_proposal = self._map_applied = None
            self._revision = uuid4().hex
            return self.snapshot()

    def undo(self, revision, edit_revision):
        with self._lock:
            self._check(revision)
            self._check_history_capacity()
            if self._applied is None:
                raise ValueError("no server-owned edit to undo")
            restored = (undo_refreshed_correction(self._plan, self._applied, self._map_applied,
                                                  reviewed_edit_revision=edit_revision) if self._map_applied else
                        undo_xy_correction(self._plan, self._applied, reviewed_edit_revision=edit_revision))
            self._actions.append({"action": "undo", "edit_revision": edit_revision,
                                  "result_plan_revision": plan_revision(restored)})
            self._plan = restored
            self._proposal = self._applied = None
            self._comparison = None
            self._map_proposal = self._map_applied = None
            self._revision = uuid4().hex
            return self.snapshot()

    def _profile(self):
        if self._plan is None or self._plan.robot is None:
            raise ValueError("import a plan with a registered robot profile first")
        try:
            return resolve_robot_profile(self._plan.robot.profile_id)
        except KeyError as exc:
            raise ValueError("imported robot profile is not in the application registry") from exc

    def _route_conditions(self):
        profile = self._profile()
        return profile, comparison_conditions(self._plan, profile)

    def propose_map(self, revision):
        with self._lock:
            self._check(revision)
            if self._applied is None or self._map_applied is not None:
                raise ValueError("one pending corrected scratch scene required")
            proposal = propose_map_refresh(self._plan, self._applied, self._recording, self._profile())
            self._map_proposal = proposal
            self._comparison = None
            self._revision = uuid4().hex
            return self.snapshot()

    def apply_map(self, revision, proposal_revision):
        with self._lock:
            self._check(revision)
            self._check_history_capacity()
            if self._map_proposal is None:
                raise ValueError("no server-owned map overlay proposal")
            plan = apply_map_refresh(self._plan, self._applied, self._recording, self._profile(),
                                     self._map_proposal, reviewed_revision=proposal_revision)
            self._actions.append({"action": "map_overlay", "proposal_revision": proposal_revision,
                                  "result_plan_revision": plan_revision(plan)})
            self._plan, self._map_applied = plan, self._map_proposal
            self._map_proposal = self._comparison = None
            self._revision = uuid4().hex
            return self.snapshot()

    def compare(self, revision, conditions_revision, baseline, candidate):
        def checked(value):
            _exact(value, ("id", "points_xy_m", "provenance"))
            points = value["points_xy_m"]
            if type(points) is not list or any(type(p) is not list for p in points):
                raise ValueError("route points must be JSON arrays")
            return RouteCandidate(value["id"], conditions_revision, tuple(tuple(p) for p in points), value["provenance"])
        before, after = checked(baseline), checked(candidate)
        with self._lock:
            self._check(revision)
            profile, _ = self._route_conditions()
            result = compare_routes(self._plan, profile, before, after)
            self._comparison = result
            self._revision = uuid4().hex
            return self.snapshot()

    def snapshot(self):
        with self._lock:
            result = {"schema_version": "scan-review-1.0", "workspace_revision": self._revision,
                      "mode": "isolated_offline_review", "source_verified": False,
                      "motion_authorized": False, "demo_ready": False, "physical_validation": "NOT_RUN",
                      "active_project_changed": False, "scene": None, "before_scene": None,
                      "scan": None, "proposal": None, "edit_revision": None, "review_required": True,
                      "map_present": False, "mission_present": False,
                      "route_conditions": None, "route_unavailable_reason": None,
                      "route_comparison": self._comparison,
                      "map_refresh_available": self._applied is not None and self._map_applied is None,
                      "map_proposal": self._map_proposal.preview() if self._map_proposal else None,
                      "map_overlay": self._map_applied.preview() if self._map_applied else None,
                      "archive_action_count": len(self._actions),
                      "notice": "Offline scratch draft only. No project, Isaac or robot changes. Save a replay archive before restart to restore geometry by explicit import; proposals, comparisons and approvals are not restored."}
            if self._plan is not None:
                result.update(scene=self._plan.scene.to_dict(), before_scene=self._base.scene.to_dict(),
                              scan=self._preview, proposal=self._proposal.preview() if self._proposal else None,
                              edit_revision=self._applied.revision if self._applied else None,
                              map_present=self._plan.navigation_map is not None,
                              mission_present=self._plan.mission is not None)
            try:
                _, result["route_conditions"] = self._route_conditions()
            except ValueError as exc:
                result["route_unavailable_reason"] = str(exc)
            return json.loads(json.dumps(result, allow_nan=False))

    def export_review(self):
        with self._lock:
            if self._plan is None:
                raise ValueError("no offline review to export")
            return {"schema_version": "scan-review-export-1.0", "execution_authority": False,
                    "restore_supported": False, "snapshot": self.snapshot(),
                    "source_plan_revision": plan_revision(self._base),
                    "recording_revision": self._recording.revision,
                    "reviewed_site_plan": self._plan.to_dict()}

    def _check_history_capacity(self):
        if len(self._actions) >= MAX_ARCHIVE_ACTIONS:
            raise ValueError("offline archive action budget exceeded")

    def export_archive(self, revision):
        with self._lock:
            self._check(revision)
            content = {"schema_version": "scan-review-archive-1.0", "execution_authority": False,
                "source_verified": False, "base_plan": self._base.to_dict(),
                "recording": self._recording.to_dict(), "actions": self._actions,
                "result_plan_revision": plan_revision(self._plan)}
            archive = {**content, "archive_digest": canonical_sha256(content)}
            text = json.dumps(archive, allow_nan=False)
            if len(text.encode("utf-8")) > MAX_ARCHIVE_BYTES:
                raise ValueError("offline archive exceeds 10 MiB")
            return json.loads(text)

    def import_archive(self, revision, text):
        # Validate/recompute in a private workspace first, then atomically install
        # it only if this workspace has not changed. Imported hashes are integrity
        # bindings, not proof that a reviewer, sensor or real-world TF is trusted.
        with self._lock:
            if revision != self._revision:
                raise ValueError("offline workspace changed; refresh before archive import")
        if type(text) is not str or len(text) > MAX_ARCHIVE_BYTES or len(text.encode("utf-8")) > MAX_ARCHIVE_BYTES:
            raise ValueError("offline archive exceeds 10 MiB or is not JSON text")
        try:
            archive = json.loads(text, object_pairs_hook=_unique, parse_constant=_nonfinite)
        except (RecursionError, OverflowError) as exc:
            raise ValueError("invalid offline archive nesting") from exc
        _exact(archive, ("schema_version", "execution_authority", "source_verified", "base_plan",
                         "recording", "actions", "result_plan_revision", "archive_digest"))
        if (archive["schema_version"] != "scan-review-archive-1.0" or archive["execution_authority"] is not False
                or archive["source_verified"] is not False):
            raise ValueError("archive must be unverified and have no execution authority")
        content = {key: value for key, value in archive.items() if key != "archive_digest"}
        if canonical_sha256(content) != archive["archive_digest"]:
            raise ValueError("archive digest does not match its contents")
        if type(archive["actions"]) is not list or len(archive["actions"]) > MAX_ARCHIVE_ACTIONS:
            raise ValueError("invalid offline archive action budget")
        restored = ScanReview()
        restored.import_bundle(json.dumps({"schema_version": "offline-scan-bundle-1.0",
            "site_plan": archive["base_plan"], "recording": archive["recording"]}, allow_nan=False))
        if canonical_sha256(restored._base.to_dict()) != canonical_sha256(archive["base_plan"]):
            raise ValueError("archive base must be canonical and require review")
        for action in archive["actions"]:
            if type(action) is not dict:
                raise ValueError("invalid archive action")
            kind = action.get("action")
            if kind == "correction":
                _exact(action, ("action", "object_id", "pairs", "proposal_revision", "result_plan_revision"))
                state = restored.propose(restored._revision, action["object_id"], action["pairs"])
                restored.apply(state["workspace_revision"], action["proposal_revision"])
            elif kind == "map_overlay":
                _exact(action, ("action", "proposal_revision", "result_plan_revision"))
                state = restored.propose_map(restored._revision)
                restored.apply_map(state["workspace_revision"], action["proposal_revision"])
            elif kind == "undo":
                _exact(action, ("action", "edit_revision", "result_plan_revision"))
                restored.undo(restored._revision, action["edit_revision"])
            else:
                raise ValueError("unsupported archive action")
            if plan_revision(restored._plan) != action["result_plan_revision"]:
                raise ValueError("archive action result does not match replay")
        if plan_revision(restored._plan) != archive["result_plan_revision"]:
            raise ValueError("archive final plan does not match replay")
        with self._lock:
            if revision != self._revision:
                raise ValueError("offline workspace changed during archive validation")
            for key in ("_base", "_plan", "_recording", "_preview", "_applied", "_map_applied", "_actions"):
                setattr(self, key, getattr(restored, key))
            self._proposal = self._map_proposal = self._comparison = None
            self._revision = uuid4().hex
            return self.snapshot()

    def download_archive(self, revision):
        # Keep Python's exact numeric representation across the JS transport.
        # JSON.parse/stringify would turn 0.0 into 0 and invalidate core digests.
        archive = self.export_archive(revision)
        text = json.dumps(archive, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return {"filename": "offline-scan-archive.json", "archive_text": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
