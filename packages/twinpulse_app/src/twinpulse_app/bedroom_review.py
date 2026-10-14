# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit local photo-room review → existing broker, no active-project writes."""
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock

from twinpulse_core.revisions import canonical_sha256
from .bedroom_twin import bedroom_draft, bedroom_manifest, saved_bedroom_manifest
from .command_broker import BrokerError
from .bedroom_rehearsal import rehearse_bedroom, checked_replay, compare_rehearsals
from .evaluation_report import evaluate_bedroom_comparison
from .robot_geometry_evidence import load_geometry_evidence
from twinpulse_core.room_goal import room_goal_preview

from .runtime_paths import resource_root
ROOT = resource_root()
ASSET_RELATIVE = "assets/simulation/turtlebot3_burger/usd"


def load_bedroom_source(root=ROOT):
    root = Path(root).resolve()
    photo_dir = root / "artifacts/photo-scan-review-20260927"
    asset_root = root / ASSET_RELATIVE
    # Fixed catalogue only; no client path or remotely fetched USD.
    if not asset_root.resolve().is_relative_to(root):
        raise ValueError("Burger asset must remain inside repository")
    photo = (photo_dir / "room.jpg").read_bytes()
    top = (photo_dir / "top-view-window-up.jpg").read_bytes()
    if sha256(top).hexdigest() != saved_bedroom_manifest(root)["direction_photo_sha256"]:
        raise ValueError("Direction photo differs from preserved source")
    draft = bedroom_draft(photo, root)
    files = sorted(p for p in asset_root.rglob("*") if p.is_file())
    if not (asset_root / "turtlebot3_burger.usda").is_file() or not files:
        raise ValueError("Existing local Burger asset unavailable")
    if any(not p.resolve().is_relative_to(asset_root.resolve()) for p in files):
        raise ValueError("Asset dependency leaves local catalogue")
    hashes = {p.relative_to(asset_root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files}
    return draft, bedroom_manifest(draft, hashes, root), asset_root


def checked_bedroom_descriptor(descriptor, scene, root=ROOT):
    draft, manifest, asset_root = load_bedroom_source(root)
    expected = {"kind": "bedroom_visual_v1", "manifest_sha256": manifest["manifest_sha256"]}
    base = {k:v for k,v in descriptor.items() if k not in {'replay','localization'}}
    if base != expected or canonical_sha256(scene.to_dict()) != canonical_sha256(draft.site.scene.to_dict()):
        raise ValueError("Bedroom preview does not match current photo, scene and asset bytes")
    if 'replay' in descriptor:
        checked_replay(draft, manifest, descriptor['replay'])
    if 'localization' in descriptor:
        if 'replay' in descriptor:raise ValueError('Only one visual replay source is allowed')
        from .room_localization_review import checked_localization_visual
        checked_localization_visual(descriptor['localization'],draft,root=root)
    return draft, manifest, asset_root


class BedroomReview:
    def __init__(self, broker, source_loader=load_bedroom_source):
        self.broker = broker
        self._load = source_loader
        self._lock = RLock()
        self._revision = None

    def geometry_evidence(self):
        try:return load_geometry_evidence()
        except (OSError,ValueError,KeyError) as exc:
            raise BrokerError('geometry_evidence_unavailable','Saved model/scan evidence is missing or changed',status=409) from exc

    def goal_preview(self, revision, evidence_revision, goal, reference):
        with self._lock:
            if not self._revision or revision!=self._revision:
                raise BrokerError('bedroom_review_required','Prepare the current room first',status=409)
            draft,manifest,_=self._load()
            if manifest['manifest_sha256']!=revision:
                self._revision=None
                raise BrokerError('bedroom_review_stale','Room source changed',status=409)
            evidence=self.geometry_evidence()
            if evidence['revision']!=evidence_revision:
                raise BrokerError('geometry_evidence_stale','Refresh model/scan evidence',status=409)
            try:
                result=room_goal_preview(goal,reference,scene_revision=draft.site.scene.revision,
                                         evidence_revision=evidence_revision)
                floor=next(c.arguments for c in draft.plan.calls if c.tool=='create_floor')
                centre,size=floor['center_m'],floor['size_m']
                if not all(abs(goal[i]-centre[i])<=size[i]/2 for i in (0,1)):
                    raise ValueError('OUTSIDE_DRAFT_FLOOR')
            except ValueError as exc:
                raise BrokerError('goal_reference_invalid','Metric reference/goal invalid, stale or inconsistent',status=400) from exc
            return {**result,'revision':revision,'missing':evidence['missing'],
                    'geometry_status':'PHOTO_APPROXIMATION_NOT_SURVEYED','mission_request':None}

    def prepare(self):
        with self._lock:
            self._revision = None  # failed preparation revokes any old review
            try:
                draft, manifest, _ = self._load()
            except (OSError, ValueError) as exc:
                raise BrokerError("bedroom_source_unavailable", "Local room photo or Burger source unavailable/changed") from exc
            self._revision = manifest["manifest_sha256"]
            return {"revision": self._revision, "scene_revision": draft.site.scene.revision,
                    "summary": draft.plan.summary, "objects": draft.site.scene.to_dict()["objects"],
                    "robot_placement": manifest["robot_placement"], "limits": manifest["limitations"],
                    "physical_validation": "NOT_RUN", "alignment_verified": False,
                    "active_project_changed": False, "motion_authorized": False}

    def build(self, session_id, revision, acknowledged, request_id, replay=None, localization=None):
        with self._lock:
            if type(acknowledged) is not bool or not acknowledged or revision != self._revision or not self._revision:
                raise BrokerError("bedroom_review_required", "Review the current approximate room before preview Build")
            try:
                draft, manifest, _ = self._load()
            except (OSError, ValueError) as exc:
                self._revision = None
                raise BrokerError("bedroom_source_unavailable", "Room source must be prepared again") from exc
            if revision != manifest["manifest_sha256"]:
                self._revision = None
                raise BrokerError("bedroom_review_stale", "Photo, scene or asset changed; prepare again")
            descriptor = {"kind": "bedroom_visual_v1", "manifest_sha256": revision}
            if replay is not None:
                checked_replay(draft, manifest, replay)
                descriptor['replay'] = dict(replay)
            if localization is not None:
                descriptor['localization']=dict(localization)
                checked_bedroom_descriptor(descriptor,draft.site.scene)
            artifact_id = "bedroom-" + canonical_sha256(descriptor)
            self.broker.register_site_scene(artifact_id, draft.site.scene,
                visual_preview=descriptor)
            return self.broker.submit(session_id, {
                "client_request_id": request_id, "command_type": "build_site_scene",
                "artifact_id": artifact_id, "expected_applied_revision": draft.site.scene.revision})

    def rehearse(self, revision, scenario, acknowledged):
        with self._lock:
            if acknowledged is not True or not self._revision or revision!=self._revision:
                raise BrokerError('bedroom_review_required','Review the current room and acknowledge synthetic rehearsal',status=409)
            if scenario not in {'route','direct','blocked','stale_scan','detour','detour_no_path'}:
                raise BrokerError('rehearsal_scenario','Only fixed offline scenarios are supported',status=400)
            try:draft,manifest,_=self._load()
            except (OSError,ValueError) as exc:
                self._revision=None
                raise BrokerError('bedroom_source_unavailable','Room source changed or missing',status=409) from exc
            if manifest['manifest_sha256']!=revision:
                self._revision=None
                raise BrokerError('bedroom_review_stale','Room source changed; review again',status=409)
            return rehearse_bedroom(draft,manifest,scenario)

    def compare(self, revision, acknowledged):
        with self._lock:
            # Same locked review, fixed controller and sensor model. No arbitrary uploaded traces.
            return compare_rehearsals(self.rehearse(revision,'route',acknowledged),
                                     self.rehearse(revision,'direct',acknowledged))

    def offline_acceptance(self, revision, acknowledged):
        """One read-only product operation for the fixed synthetic mission/fault suite.

        It is deliberately not a robot qualification or a substitute for measured
        scan, odom, TF, room alignment, Isaac physics, or a field session.
        """
        with self._lock:
            route = self.rehearse(revision, 'route', acknowledged)
            direct = self.rehearse(revision, 'direct', acknowledged)
            detour = self.rehearse(revision, 'detour', acknowledged)
            no_path = self.rehearse(revision, 'detour_no_path', acknowledged)
            stale = self.rehearse(revision, 'stale_scan', acknowledged)
            comparison = compare_rehearsals(route, direct)
            evaluation = evaluate_bedroom_comparison(comparison)
            checks = {
                'route_arrived': route['status'] == 'ARRIVED',
                'direct_arrived': direct['status'] == 'ARRIVED',
                'detour_arrived_after_zero_output': (detour['status'] == 'ARRIVED'
                    and len(detour.get('replan_events', [])) == 1
                    and detour['replan_events'][0]['output_zero'] is True),
                'no_path_stopped': (no_path['status'] == 'NO_PATH'
                    and len(no_path.get('replan_events', [])) == 1
                    and no_path['replan_events'][0]['output_zero'] is True),
                'stale_scan_stopped': stale['status'] == 'SCAN_STALE',
                'same_condition_comparison': (comparison['eligible_for_efficiency_comparison'] is True
                    and evaluation['physical_validation'] == 'NOT_RUN'),
            }
            body = {'schema': 'bedroom-offline-acceptance-1.0', 'scene_revision': route['scene_revision'],
                    'source_revision': revision, 'provenance': 'SYNTHETIC_PHOTO_APPROXIMATION',
                    'physical_validation': 'NOT_RUN', 'motion_authorized': False,
                    'robot_connection': False, 'isaac_run': False, 'checks': checks,
                    'status': 'SYNTHETIC_PASS' if all(checks.values()) else 'SYNTHETIC_FAIL',
                    'records': {'route': route, 'direct': direct, 'detour': detour,
                                'detour_no_path': no_path, 'stale_scan': stale},
                    'comparison': comparison, 'evaluation': evaluation}
            return {**body, 'revision': canonical_sha256(body)}

    def export_offline_acceptance(self, revision, acknowledged, acceptance_revision):
        report = self.offline_acceptance(revision, acknowledged)
        if report['revision'] != acceptance_revision:
            raise BrokerError('bedroom_acceptance_stale', 'Offline record changed; run it again', status=409)
        text = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return {'acceptance_revision': acceptance_revision, 'json_text': text,
                'sha256': sha256(text.encode('utf-8')).hexdigest()}

    def reopen_offline_acceptance(self, revision, acknowledged, bundle_text):
        """Read-only import of this pinned fixture, checked against current sources.

        Never uses uploaded commands or geometry as execution input.
        """
        if type(bundle_text) is not str or not 0 < len(bundle_text.encode('utf-8')) <= 4 * 1024 * 1024:
            raise BrokerError('bedroom_acceptance_file_invalid', 'Synthetic record size is invalid', status=400)
        try:
            supplied = json.loads(bundle_text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            if type(supplied) is not dict:
                raise ValueError('object required')
            supplied_revision = supplied.pop('revision')
            if (type(supplied_revision) is not str or
                    canonical_sha256(supplied) != supplied_revision):
                raise ValueError('content hash differs')
            current = self.offline_acceptance(revision, acknowledged)
            # JSON arrays reload as lists whereas in-memory waypoint tuples are
            # still tuples. Both canonical hashes cover the same serialized body.
            if supplied_revision != current['revision']:
                raise ValueError('saved record differs from current source')
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise BrokerError('bedroom_acceptance_file_invalid',
                              'Saved synthetic record is changed, incomplete, or stale', status=409) from exc
        return current

    def evaluate(self, revision, acknowledged):
        """Evaluate the same explicitly reviewed, freshly recomputed comparison."""
        return evaluate_bedroom_comparison(self.compare(revision, acknowledged))

    def export_comparison(self, revision, acknowledged, comparison_revision):
        """Return Python-serialized bytes; JS numeric roundtrips lose canonical identity."""
        comparison = self.compare(revision, acknowledged)
        if comparison["revision"] != comparison_revision:
            raise BrokerError("bedroom_comparison_stale", "Comparison changed; compare again", status=409)
        evaluate_bedroom_comparison(comparison)
        text = json.dumps(comparison, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
        return {"comparison_revision": comparison_revision, "json_text": text,
                "sha256": sha256(text.encode("utf-8")).hexdigest()}

    def export_rehearsal(self, revision, scenario, acknowledged, record_revision):
        """Export a fresh fixed synthetic record without JS number re-serialization."""
        record = self.rehearse(revision, scenario, acknowledged)
        if record["revision"] != record_revision:
            raise BrokerError("bedroom_rehearsal_stale", "Rehearsal changed; run it again", status=409)
        body = {key: value for key, value in record.items() if key != "revision"}
        if (canonical_sha256(body) != record_revision or record["motion_authorized"] is not False
                or record["physical_validation"] != "NOT_RUN" or record["isaac_run"] is not False):
            raise ValueError("Invalid synthetic rehearsal identity")
        text = json.dumps(record, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
        return {"record_revision": record_revision, "json_text": text,
                "sha256": sha256(text.encode("utf-8")).hexdigest()}


class UnavailableBedroomReview:
    """Do not expose the preserved default-room fixture under another project ID."""

    def __getattr__(self, name):
        raise BrokerError("default_room_project_mismatch",
                          "Default bedroom preview belongs only to the default project", status=409)
