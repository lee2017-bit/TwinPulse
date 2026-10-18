# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded single-engine command broker for the local TwinPulse bridge."""

from __future__ import annotations

from collections import OrderedDict, deque
from copy import deepcopy
from dataclasses import dataclass, field
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
    SceneRevision,
    bundle_digest,
    evaluate_engine_feature,
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


@dataclass(frozen=True, slots=True)
class RegisteredSiteScene:
    artifact_id: str
    revision: str
    scene: SceneRevision
    visual_preview: dict | None = None
    presentation: dict | None = None


@dataclass(slots=True)
class _Operation:
    command: CommandEnvelope
    request_hash: str
    product_session_id: str
    status: str = "accepted"
    receipt: CommandReceipt | None = None
    diagnostics: object = field(default=None, repr=False)
    claim_trace: object = field(default=None, repr=False)
    frame_trace: object = field(default=None, repr=False)
    frame_started_at: float | None = None
    frame_seen: tuple | None = None
    view_status: str | None = None
    view_error_code: str | None = None
    view_execution_id: str | None = None

    def public(self) -> dict[str, object]:
        return {
            "execution_id": self.diagnostics.execution_id if self.diagnostics is not None else None,
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
        first_frame_timeout_s: float = 15.0,
        clock=time.monotonic,
    ) -> None:
        if queue_limit < 1 or operation_limit < queue_limit:
            raise ValueError("broker limits are invalid")
        self.project_id = project_id
        self.queue_limit = queue_limit
        self.operation_limit = operation_limit
        self.lease_ttl_s = float(lease_ttl_s)
        self.engine_timeout_s = float(engine_timeout_s)
        import math
        if not math.isfinite(first_frame_timeout_s) or not 1 <= first_frame_timeout_s <= 60:
            raise ValueError("first frame timeout must be between 1 and 60 seconds")
        self.first_frame_timeout_s = float(first_frame_timeout_s)
        self._clock = clock
        self._lock = RLock()
        self._artifacts: dict[str, RegisteredArtifact] = {}
        self._site_scenes: dict[str, RegisteredSiteScene] = {}
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
        self._simulation_plans: OrderedDict[str, dict] = OrderedDict()
        self.diagnostics = None
        self._diagnostic_artifacts = {}
        self._diagnostic_revisions = OrderedDict()
        self._runtime_command_id = None
        self._snapshot_diagnostic_key = None
        self._snapshot_execution_id = None
        self._view_command_id = None
        self.scene_mutation_guard = None

    def artifact_diagnostic_refs(self, artifact_id):
        """A detached read of optional references, never control admission."""
        with self._lock:
            return dict(self._diagnostic_artifacts.get(artifact_id,{}))

    def bind_artifact_diagnostics(self, artifact_id, **values):
        from twinpulse_core.execution_diagnostics import metadata
        with self._lock:
            values={**self._diagnostic_artifacts.get(artifact_id,{}),**metadata(values)}
            self._diagnostic_artifacts[artifact_id] = values
            artifact=self._artifacts.get(artifact_id) or self._site_scenes.get(artifact_id)
            if artifact is not None:
                self._diagnostic_revisions[artifact.revision]=metadata(values)
                self._diagnostic_revisions.move_to_end(artifact.revision)
                while len(self._diagnostic_revisions)>256:self._diagnostic_revisions.popitem(last=False)
            while len(self._diagnostic_artifacts)>256:
                self._diagnostic_artifacts.pop(next(iter(self._diagnostic_artifacts)))

    def register_simulation_plan(self, scene: SceneRevision, plan: dict) -> dict:
        from twinpulse_core.site_simulation import checked_plan
        checked = checked_plan(scene, plan)
        with self._lock:
            self._simulation_plans[checked['plan_id']] = deepcopy(checked)
            self._simulation_plans.move_to_end(checked['plan_id'])
            while len(self._simulation_plans) > 32:
                self._simulation_plans.popitem(last=False)
        return checked

    def register_artifact(self, artifact_id: str, bundle: SpecBundle) -> RegisteredArtifact:
        if not artifact_id or len(artifact_id) > 128:
            raise ValueError("artifact_id is invalid")
        checked = SpecBundle.from_dict(bundle.to_dict())
        artifact = RegisteredArtifact(artifact_id, bundle_digest(checked), checked)
        with self._lock:
            self._artifacts[artifact_id] = artifact
        return artifact

    def register_site_scene(self, artifact_id: str, scene: SceneRevision, *, visual_preview=None,
                            presentation=None) -> RegisteredSiteScene:
        if not artifact_id or len(artifact_id) > 128:
            raise ValueError("artifact_id is invalid")
        checked = SceneRevision.from_dict(scene.to_dict())
        if isinstance(visual_preview, dict) and visual_preview.get('kind') == 'generation_room_visual_v1':
            from twinpulse_core.generation_visual import checked_generation_visual
            checked_generation_visual(visual_preview, checked, self.project_id)
            visual_preview = deepcopy(visual_preview)
        elif visual_preview is not None:
            if (type(visual_preview) is not dict or set(visual_preview) not in (
                    {"kind", "manifest_sha256"}, {"kind", "manifest_sha256", "replay"},
                    {"kind", "manifest_sha256", "scene_change_revision"}, {"kind", "manifest_sha256", "localization"},
                    {"kind", "manifest_sha256", "mission_id"})
                    or visual_preview["kind"] not in {"bedroom_visual_v1", "project_room_visual_v1", "automatic_mission_visual_v1", "current_inspection_visual_v1"}
                    or (visual_preview['kind'] in {'automatic_mission_visual_v1','current_inspection_visual_v1'} and
                        (set(visual_preview)!={'kind','manifest_sha256','mission_id'} or
                         not isinstance(visual_preview['mission_id'],str) or len(visual_preview['mission_id'])!=32 or
                         any(c not in '0123456789abcdef' for c in visual_preview['mission_id'])))
                    or (visual_preview['kind'] not in {'automatic_mission_visual_v1','current_inspection_visual_v1'} and 'mission_id' in visual_preview)
                    or (visual_preview["kind"] == "project_room_visual_v1" and
                        (self.project_id == "default" or "replay" in visual_preview or "localization" in visual_preview))
                    or (visual_preview["kind"] == "bedroom_visual_v1" and
                        (self.project_id != "default" or "scene_change_revision" in visual_preview))
                    or ("scene_change_revision" in visual_preview and
                        visual_preview["scene_change_revision"] != checked.revision)
                    or not isinstance(visual_preview["manifest_sha256"], str)
                    or len(visual_preview["manifest_sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in visual_preview["manifest_sha256"])):
                raise ValueError("Unsupported visual preview descriptor")
            visual_preview = dict(visual_preview)
            if 'replay' in visual_preview:
                from .bedroom_review import checked_bedroom_descriptor
                checked_bedroom_descriptor(visual_preview, checked)
                visual_preview['replay'] = dict(visual_preview['replay'])
            if 'localization' in visual_preview:
                from .bedroom_review import checked_bedroom_descriptor
                checked_bedroom_descriptor(visual_preview, checked)
                visual_preview['localization']=dict(visual_preview['localization'])
        if presentation is not None:
            from twinpulse_core.presentation import checked_presentation
            presentation = checked_presentation(presentation)
        artifact = RegisteredSiteScene(artifact_id, checked.revision, checked, visual_preview, presentation)
        with self._lock:
            self._site_scenes[artifact_id] = artifact
        return artifact

    def site_scene_capable(self) -> bool:
        with self._lock:
            return self._feature_readiness("site_scene_build_v2").ready

    def request_outcome(self, product_session_id: str, request_id: str) -> dict:
        with self._lock:
            record = self._request_ids.get(request_id)
            operation = self._operations.get(record[1]) if record else None
            if operation is None or operation.product_session_id != product_session_id:
                raise BrokerError('command_unknown', 'No owned request receipt is visible', status=404)
            return operation.public()

    def register_engine(self, engine_session_id: str, stage_epoch: str) -> None:
        if not engine_session_id or not stage_epoch:
            raise BrokerError("engine_identity_invalid", "Engine identity is required", status=400)
        with self._lock:
            if self._engine_session_id != engine_session_id:
                self._expire_engine_operations("engine_session_replaced")
                self._snapshot = None
                self._runtime_command_id = self._snapshot_diagnostic_key = self._snapshot_execution_id = None
                self._view_command_id = None
            elif self._stage_epoch is not None and self._stage_epoch != stage_epoch:
                self._expire_engine_operations("stage_epoch_changed")
                self._snapshot = None
                self._runtime_command_id = self._snapshot_diagnostic_key = self._snapshot_execution_id = None
                self._view_command_id = None
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
        expected_shape = base_shape | ({"artifact_id"} if command_type in {"build_scene", "build_site_scene"} else set())
        if command_type in {'run', 'build_site_scene'} and 'simulation_id' in value:
            expected_shape |= {'simulation_id'}
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
            if self.scene_mutation_guard is not None:
                self.scene_mutation_guard(command_type)
            self._assert_product_control(product_session_id)
            self._assert_engine_connected()
            if len(self._queue) >= self.queue_limit:
                raise BrokerError("command_queue_full", "Command queue is full", status=429)
            if self._inflight is not None or self._queue:
                raise BrokerError("mutating_command_busy", "Another command is pending or running")
            snapshot = self._snapshot
            if command_type == "run" and 'simulation_id' not in value and snapshot is not None and any(
                item.revision == snapshot.applied_revision for item in self._site_scenes.values()
            ):
                raise BrokerError("site_scene_run_forbidden", "A site scene has no authorized robot mission")
            if command_type in {"build_scene", "build_site_scene", "reset"} and snapshot is not None and snapshot.runtime_state == "running":
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
            elif command_type == "build_site_scene":
                if not self._feature_readiness("site_scene_build_v2").ready:
                    raise BrokerError("site_scene_capability_missing", "Connected Isaac engine cannot build site scenes")
                artifact_id = value.get("artifact_id")
                if not isinstance(artifact_id, str) or artifact_id not in self._site_scenes:
                    raise BrokerError("artifact_unknown", "Site scene artifact is not registered", status=404)
                site_artifact = self._site_scenes[artifact_id]
                if site_artifact.scene.library_assets and (self._snapshot is None or
                        'library_mesh_v1' not in self._snapshot.capabilities):
                    raise BrokerError('library_asset_capability_missing','Updated Isaac adapter is required for pinned Library meshes')
                if expected is not None and expected != site_artifact.revision:
                    raise BrokerError("revision_mismatch", "Site scene revision does not match the request")
                expected = site_artifact.revision
                payload = {
                    "artifact_id": site_artifact.artifact_id,
                    "scene_revision": site_artifact.revision,
                    "scene": site_artifact.scene.to_dict(),
                }
                if 'simulation_id' in value:
                    if self._snapshot is None or 'site_simulation_preview_v1' not in self._snapshot.capabilities:
                        raise BrokerError('simulation_preview_capability_missing', 'Updated Isaac adapter is required for the pre-Run Burger preview')
                    simulation_id = value['simulation_id']
                    plan = self._simulation_plans.get(simulation_id) if isinstance(simulation_id, str) else None
                    if plan is None:
                        raise BrokerError('simulation_plan_unknown', 'Review a simulation path first')
                    if plan['scene_revision'] != expected:
                        raise BrokerError('revision_mismatch', 'SIM preview belongs to a different room revision')
                    if site_artifact.visual_preview is not None:
                        raise BrokerError('simulation_preview_conflict', 'A saved room visual and a generated SIM preview cannot be combined')
                    payload['simulation_preview'] = deepcopy(plan)
                if site_artifact.visual_preview is not None:
                    feature = site_artifact.visual_preview["kind"]
                    if not self._feature_readiness(feature).ready:
                        raise BrokerError("bedroom_capability_missing", "Restart updated Isaac adapter for room/Burger preview")
                    payload["visual_preview"] = deepcopy(site_artifact.visual_preview)
                    if 'replay' in site_artifact.visual_preview and not self._feature_readiness("bedroom_replay_v1").ready:
                        raise BrokerError('preview_unavailable', 'Updated synthetic replay engine required')
                    if 'localization' in site_artifact.visual_preview and not self._feature_readiness('room_scan_replay_v1').ready:
                        raise BrokerError('preview_unavailable','Updated saved scan preview engine required')
                if site_artifact.presentation is not None:
                    if self._snapshot is None or "presentation_preset_v1" not in self._snapshot.capabilities:
                        raise BrokerError("presentation_capability_missing", "Updated Isaac adapter required for saved camera and lighting presets")
                    payload["presentation"] = dict(site_artifact.presentation)
            elif command_type == 'run' and 'simulation_id' in value:
                simulation_id = value['simulation_id']
                if not isinstance(simulation_id, str):
                    raise BrokerError('simulation_id_invalid', 'Simulation ID must be a string', status=400)
                plan = self._simulation_plans.get(simulation_id)
                if plan is None:
                    raise BrokerError('simulation_plan_unknown', 'Review a simulation path first')
                if (snapshot is None or 'site_simulation_v1' not in snapshot.capabilities
                        or snapshot.runtime_state not in {'built', 'paused', 'completed'} or snapshot.safety_state is not None
                        or expected != snapshot.applied_revision or expected != plan['scene_revision']):
                    raise BrokerError('simulation_not_ready', 'Current scene, idle engine and SIM capability are required')
                if (plan.get('schema_version')=='site-goal-demonstration-1.0'
                        and 'exact_goal_demonstration_v1' not in snapshot.capabilities):
                    raise BrokerError('goal_demonstration_capability_missing','Updated Isaac adapter is required for an exact reviewed route')
                payload = {'site_simulation': deepcopy(plan)}
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
                ttl_s=120.0 if command_type in {"build_scene", "build_site_scene"} else 10.0,
            )
            operation = _Operation(command, request_hash, product_session_id)
            if self.diagnostics is not None:
                refs = self._diagnostic_artifacts.get(value.get('artifact_id'),
                    self._diagnostic_revisions.get(expected, {}))
                # Restored refs include the generation request/revision. The
                # new command owns these keys; evidence IDs preserve origins.
                # Merge once, rather than raising on duplicate keyword args.
                trace_values={**refs, 'command_id':command.command_id, 'request_id':request_id,
                    'engine_session_id':command.engine_session_id,'draft_revision':expected,
                    'plan_id':value.get('simulation_id'),'stage':'engine_command_'+command_type,
                    'durable':False,'component':'broker'}
                operation.diagnostics = self.diagnostics.begin(**trace_values)
                operation.claim_trace = operation.diagnostics.child('engine_queue')
            self._operations[command.command_id] = operation
            self._request_ids[request_id] = (request_hash, command.command_id)
            self._queue.append(command.command_id)
            self._trim_operations()
            return operation.public()

    def claim(self, engine_session_id: str, stage_epoch: str) -> CommandEnvelope | None:
        with self._lock:
            self._assert_engine(engine_session_id, stage_epoch)
            self._engine_heartbeat_at = self._clock()
            self._expire_unclaimed_operations()
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
                    self._finish_diagnostics(operation, 'failed', 'command_expired')
                    continue
                operation.status = "running"
                if operation.claim_trace is not None:
                    operation.claim_trace.finish()
                    operation.claim_trace = operation.diagnostics.child('engine_execution_and_receipt_wait')
                self._inflight = command_id
                if operation.command.command_type == 'run':
                    self._runtime_command_id = command_id
                elif operation.command.command_type in {'build_scene','build_site_scene','reset'}:
                    self._runtime_command_id = None
                    for previous in self._operations.values():
                        if previous.view_status == 'waiting':
                            self._finish_frame_wait(previous, 'unknown', 'frame_wait_superseded')
                    self._view_command_id = command_id if operation.command.command_type != 'reset' else None
                return operation.command
            return None

    def command_execution_identity(self, command):
        """Read-only correlation for an already authenticated engine claim."""
        with self._lock:
            operation=self._operations.get(command.command_id)
            if operation is None or operation.command!=command:return None
            return operation.diagnostics.execution_id if operation.diagnostics else None

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
            self._finish_diagnostics(operation, 'cancelled', 'cancelled_by_product')
            return operation.public()

    def record_receipt(self, receipt: CommandReceipt, *, diagnostics=None) -> None:
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
            if (command.command_type in {"build_scene", "build_site_scene"} and checked.status == "succeeded"
                    and checked.applied_revision != command.expected_applied_revision):
                raise BrokerError("receipt_revision_mismatch", "Build receipt revision does not match command")
            operation.receipt = checked
            operation.status = checked.status
            self._record_engine_timing(operation, diagnostics)
            if command.command_type in {'build_scene','build_site_scene'} and checked.status=='succeeded':
                operation.frame_started_at = self._clock()
                operation.view_status = 'waiting'
                try:
                    if operation.diagnostics is not None:
                        operation.frame_trace=operation.diagnostics.child('first_current_frame_after_receipt',
                            measurement_source='backend_local_elapsed',draft_revision=checked.applied_revision)
                except (OSError, ValueError, TypeError):
                    if self.diagnostics is not None:self.diagnostics.note_storage_error()
                # An authenticated current frame can precede its command receipt.
                # Only a frame accepted after this exact Build was claimed counts.
                if operation.frame_seen is not None:
                    self._finish_frame_wait(operation, 'succeeded', None, *operation.frame_seen)
            self._finish_diagnostics(operation,
                checked.status if checked.status in {'succeeded','failed','cancelled','unknown'} else 'failed',
                checked.error_code)
            if (checked.status != 'succeeded' and self._runtime_command_id == checked.command_id
                    or checked.status == 'succeeded' and command.command_type == 'pause'):
                self._runtime_command_id = None
            if self._inflight == checked.command_id:
                self._inflight = None

    def _record_engine_timing(self, operation, value):
        """Optional receipt sidecar. It cannot change receipt acceptance or authority.

        Elapsed values are measured entirely inside one engine clock instance;
        no backend/engine timestamp subtraction or network-latency inference.
        """
        if operation.diagnostics is None or value is None:
            return
        import math
        import re
        fields={'clock_instance_id','kit_queue_s','adapter_execute_s','receipt_queue_s','dropped_receipts'}
        valid=(isinstance(value,dict) and set(value)==fields and
            isinstance(value.get('clock_instance_id'),str) and re.fullmatch('[a-f0-9]{32}',value['clock_instance_id']) and
            all(type(value.get(key)) in (int,float) and math.isfinite(value[key]) and 0<=value[key]<=86400
                for key in ('kit_queue_s','adapter_execute_s','receipt_queue_s')) and
            type(value.get('dropped_receipts')) is int and 0<=value['dropped_receipts']<=1000000)
        if not valid:
            operation.diagnostics.child('engine_timing_unavailable').finish('skipped',
                error_code='engine_timing_invalid',role='storage')
            return
        for key,stage in (('kit_queue_s','engine_kit_queue'),('adapter_execute_s','engine_adapter_execute'),
                          ('receipt_queue_s','engine_receipt_queue')):
            child=operation.diagnostics.child(stage,component='engine',elapsed_s=value[key],timer_basis='wall',
                reported_clock_instance_id=value['clock_instance_id'],measurement_source='engine_local_elapsed')
            child.finish('succeeded')
        if value['dropped_receipts']:
            operation.diagnostics.child('engine_receipt_delivery').finish('unknown',
                error_code='engine_receipt_queue_dropped',role='storage')

    def record_current_frame(self, engine_id, stage_epoch, revision, frame_id, digest):
        with self._lock:
            self._expire_if_disconnected()
            for operation in self._operations.values():
                command=operation.command
                if (command.command_id == self._view_command_id and command.command_type in {'build_scene','build_site_scene'} and
                        operation.status in {'running','succeeded'} and command.engine_session_id==engine_id and
                        command.stage_epoch==stage_epoch and command.expected_applied_revision==revision):
                    operation.frame_seen = (frame_id, digest)
                    if operation.view_status in {'waiting','failed','unknown'}:
                        self._finish_frame_wait(operation, 'succeeded', None, frame_id, digest)

    def _finish_frame_wait(self, operation, status, code, frame_id=None, digest=None):
        """Display observation, never a rewrite of the engine's apply receipt.

        No frame is a bounded backend observation, not proof of a GPU, network,
        or capture exception. Optional diagnostics cannot reject a valid frame.
        """
        operation.view_status, operation.view_error_code = status, code
        child, operation.frame_trace = operation.frame_trace, None
        try:
            if child is not None:
                child.finish(status, error_code=code, frame_id=frame_id, frame_sha256=digest)
            if status != 'succeeded' and self.diagnostics is not None:
                command = operation.command
                trace = self.diagnostics.begin('engine_view_observation', durable=False,
                    command_id=command.command_id,
                    command_execution_id=operation.diagnostics.execution_id if operation.diagnostics else None,
                    engine_session_id=command.engine_session_id, stage_epoch=command.stage_epoch,
                    draft_revision=command.expected_applied_revision, measurement_source='backend_local_elapsed')
                trace.child('first_current_frame_deadline', elapsed_s=max(0.,self._clock()-operation.frame_started_at),
                    timer_basis='wall', measurement_source='backend_local_elapsed').finish(status, error_code=code)
                trace.finish(status, error_code=code)
                operation.view_execution_id = trace.execution_id
        except (OSError, ValueError, TypeError):
            if self.diagnostics is not None:self.diagnostics.note_storage_error()

    def _view_observation(self):
        operation = self._operations.get(self._view_command_id)
        if operation is None:return None
        command = operation.command
        if operation.receipt is not None and operation.receipt.status != 'succeeded':
            return dict(command_id=command.command_id, engine_session_id=command.engine_session_id,
                        stage_epoch=command.stage_epoch, applied_revision=command.expected_applied_revision,
                        phase='apply', status='unknown' if operation.receipt.status=='unknown' else 'failed',
                        error_code=operation.receipt.error_code, message=operation.receipt.message,
                        execution_id=operation.diagnostics.execution_id if operation.diagnostics else None)
        if operation.view_status is None:return None
        return dict(command_id=command.command_id, engine_session_id=command.engine_session_id,
                    stage_epoch=command.stage_epoch, applied_revision=command.expected_applied_revision,
                    phase='frame', status=operation.view_status, error_code=operation.view_error_code,
                    command_execution_id=operation.diagnostics.execution_id if operation.diagnostics else None,
                    execution_id=operation.view_execution_id)

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
            previous = self._snapshot
            self._snapshot = checked
            self._engine_heartbeat_at = self._clock()
            try:
                self._record_runtime_observation(checked, previous)
            except (OSError, ValueError, TypeError):
                self._snapshot_execution_id = None
                if self.diagnostics is not None:
                    self.diagnostics.note_storage_error()

    def _record_runtime_observation(self, snapshot, previous):
        """Record a fault transition, not telemetry samples or command success.

        The authenticated snapshot remains authoritative even if this optional
        non-durable trace cannot be saved. Never subtract engine/backend clocks
        or infer a command from the plan's reusable run_id alone.
        """
        failed = snapshot.runtime_state in {'error','unstable','off_route','stage_invalid'} or bool(snapshot.safety_state)
        if not failed:
            self._snapshot_diagnostic_key = self._snapshot_execution_id = None
            return
        operation = self._operations.get(self._runtime_command_id)
        if operation is not None:
            command = operation.command
            observed_revision = snapshot.applied_revision
            # Stage invalidation intentionally clears identity; only the prior
            # accepted snapshot of this same engine/epoch can supply it.
            if (observed_revision is None and snapshot.runtime_state == 'stage_invalid' and previous is not None
                    and previous.engine_session_id == snapshot.engine_session_id and previous.stage_epoch == snapshot.stage_epoch):
                observed_revision = previous.applied_revision
            plan = command.payload.get('site_simulation', {})
            if (command.engine_session_id != snapshot.engine_session_id or command.stage_epoch != snapshot.stage_epoch
                    or command.expected_applied_revision != observed_revision
                    or plan and snapshot.run_id is not None and plan.get('plan_id') != snapshot.run_id):
                operation = None
        key = (snapshot.engine_session_id, snapshot.stage_epoch, snapshot.applied_revision, snapshot.run_id,
               snapshot.runtime_state, snapshot.safety_state,
               operation.command.command_id if operation else None)
        if key == self._snapshot_diagnostic_key:
            return
        self._snapshot_diagnostic_key = key
        self._snapshot_execution_id = None
        if self.diagnostics is None:
            return
        import re
        # Preserve only a fixed diagnostic token/type, never exception prose,
        # paths, prompt text or credentials from safety_reason.
        def cause(value, fallback):
            match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]{0,63}): ([A-Z][A-Z0-9_]{0,95})', value.strip())
            known = {'SIM_STAGE_CHANGED','SIM_POSE_UNSTABLE','SIM_TIME_LIMIT_EXCEEDED','SIM_PROGRESS_STALLED',
                     'SIM_TEST_POSE_LOST','SIM_TEST_CLEANUP_FAILED'}
            return ({'error_type':match[1], 'error_code':match[2]} if match and
                    match[1] in {'RuntimeError','ValueError','OSError'} and match[2] in known
                    else {'error_code':fallback})
        primary, separator, cleanup = (snapshot.safety_reason or '').partition('; cleanup: ')
        refs = dict(engine_session_id=snapshot.engine_session_id, stage_epoch=snapshot.stage_epoch,
                    draft_revision=snapshot.applied_revision, run_id=snapshot.run_id,
                    snapshot_sequence=snapshot.sequence, runtime_state=snapshot.runtime_state,
                    safety_state=snapshot.safety_state, measurement_source='authenticated_engine_snapshot')
        if operation is not None:
            refs.update(command_id=operation.command.command_id,
                        command_execution_id=operation.diagnostics.execution_id if operation.diagnostics else None)
        trace = self.diagnostics.begin('engine_runtime_observation', durable=False, **refs)
        trace.child('engine_runtime_fault').finish('failed', **cause(primary, 'engine_runtime_fault'))
        if separator:
            trace.child('engine_runtime_cleanup').finish('failed', role='cleanup',
                **cause(cleanup, 'engine_runtime_cleanup_failed'))
        trace.finish('failed', error_code='engine_runtime_fault')
        self._snapshot_execution_id = trace.execution_id

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
                "snapshot_execution_id": self._snapshot_execution_id if self._engine_connected() else None,
                "build_view": self._view_observation(),
                "engine_readiness": {
                    feature: self._feature_readiness(feature).to_dict()
                    for feature in ("legacy_scene_build", "site_scene_build_v2", "bedroom_visual_v1",
                                    "bedroom_replay_v1", "automatic_mission_visual_v1", "current_inspection_visual_v1")
                },
                "operations": operations,
                "artifacts": [
                    {"artifact_id": item.artifact_id, "revision": item.revision}
                    for item in self._artifacts.values()
                ] + [
                    {"artifact_id": item.artifact_id, "revision": item.revision}
                    for item in self._site_scenes.values()
                ],
            }

    def execution_receipt_state(self,product_session_id: str) -> dict[str,object]:
        """Same lease/engine snapshot gate without constructing the UI report.

        In-process only. No operation submission or authority is granted here.
        All fields used by the goal execution guard are captured atomically.
        """
        with self._lock:
            self._expire_if_disconnected();s=self._snapshot
            return {'engine_connected':self._engine_connected(),
                'engine_session_id':self._engine_session_id,'stage_epoch':self._stage_epoch,
                'lease_owned':self._lease_valid() and self._lease_owner==product_session_id,
                'snapshot':None if s is None else {
                    'run_id':s.run_id,'applied_revision':s.applied_revision,'runtime_state':s.runtime_state,
                    'safety_state':s.safety_state,'telemetry_available':s.telemetry_available,
                    'sequence':s.sequence,'position_m':list(s.position_m) if s.position_m is not None else None}}

    def has_pending_operations(self) -> bool:
        """A project transition may not interrupt an accepted or running scene command."""
        with self._lock:
            self._expire_if_disconnected()
            return any(item.receipt is None for item in self._operations.values())

    def supervisor_state(self) -> dict[str, object]:
        """Return secret-free engine readiness for the local process supervisor.

        This is intentionally an in-process API, not an unauthenticated HTTP
        endpoint.  The backend serializes it to an owner-only runtime file so
        the launcher can distinguish a live PID from an authenticated engine
        handshake and a usable stage snapshot.
        """
        with self._lock:
            self._expire_if_disconnected()
            return {
                "engine_connected": self._engine_connected(),
                "engine_session_id": self._engine_session_id,
                "stage_epoch": self._stage_epoch,
                "snapshot": self._snapshot.to_dict() if self._snapshot is not None else None,
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

    def _feature_readiness(self, feature: str):
        return evaluate_engine_feature(
            feature, snapshot=self._snapshot, connected=self._engine_connected(),
            engine_session_id=self._engine_session_id, stage_epoch=self._stage_epoch,
        )

    def _lease_valid(self) -> bool:
        return bool(self._lease_id and self._clock() < self._lease_expires_at)

    def _expire_if_disconnected(self) -> None:
        if self._engine_session_id and not self._engine_connected():
            self._expire_engine_operations("engine_disconnected")
        else:
            self._expire_unclaimed_operations()
            for operation in self._operations.values():
                if operation.view_status == 'waiting' and self._clock()-operation.frame_started_at >= self.first_frame_timeout_s:
                    self._finish_frame_wait(operation, 'failed', 'first_current_frame_timeout')

    def _expire_unclaimed_operations(self):
        # An expired lease cannot be resurrected by a later acquisition.
        # Only never-claimed commands receive this terminal receipt. Running
        # commands retain their real receipt/unknown policy, never replayed.
        keep=deque()
        for command_id in self._queue:
            operation=self._operations[command_id]
            if operation.receipt is not None:continue
            command=operation.command
            code=('command_expired' if command.expired() else
                  'control_lease_expired' if not self._lease_valid() or command.control_lease_id!=self._lease_id else None)
            if code is None:
                keep.append(command_id);continue
            operation.status='expired'
            operation.receipt=CommandReceipt(command_id=command.command_id,command_type=command.command_type,
                project_id=command.project_id,engine_session_id=command.engine_session_id,stage_epoch=command.stage_epoch,
                status='expired',error_code=code,
                message='Not executed: command or control lease expired before engine claim. Acquire scene control and review a new request explicitly.')
            self._finish_diagnostics(operation,'failed',code)
        self._queue=keep

    def _expire_engine_operations(self, code: str) -> None:
        # A recovered heartbeat cannot revive the old control generation.
        self._lease_id=None;self._lease_owner=None;self._lease_expires_at=0.
        for operation in self._operations.values():
            if operation.view_status == 'waiting':
                self._finish_frame_wait(operation, 'unknown', code)
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
            self._finish_diagnostics(operation, 'unknown' if operation.status == 'unknown' else 'failed', code)
        self._queue.clear()
        self._inflight = None

    @staticmethod
    def _finish_diagnostics(operation, status, code):
        if operation.diagnostics is not None:
            if operation.claim_trace is not None:
                operation.claim_trace.finish(status, error_code=code)
            operation.diagnostics.finish(status, error_code=code)

    def _trim_operations(self) -> None:
        while len(self._operations) > self.operation_limit:
            command_id, operation = next(iter(self._operations.items()))
            if command_id == self._inflight or command_id in self._queue:
                break
            if operation.view_status == 'waiting':
                self._finish_frame_wait(operation, 'unknown', 'frame_wait_evicted')
            self._operations.popitem(last=False)
            for request_id, (_digest, mapped_id) in list(self._request_ids.items()):
                if mapped_id == command_id:
                    del self._request_ids[request_id]
