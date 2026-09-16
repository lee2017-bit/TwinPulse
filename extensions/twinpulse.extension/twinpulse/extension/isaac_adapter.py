"""Main-thread-only adapter from pure R4 commands to the Isaac runtime."""

from __future__ import annotations

from collections import OrderedDict
import math
from uuid import uuid4

import omni.usd

from twinpulse_core import (
    CommandEnvelope,
    CommandReceipt,
    SimulationSnapshot,
    SpecBundle,
    bundle_digest,
    canonical_sha256,
    straight_route_command,
)

from .runtime import TwinPulseRuntime


class IsaacSimulationAdapter:
    """Executes one validated command at a time on the Kit update thread."""

    def __init__(
        self,
        runtime: TwinPulseRuntime,
        *,
        project_id: str = "default",
        engine_session_id: str | None = None,
        receipt_cache_limit: int = 256,
    ) -> None:
        self.runtime = runtime
        self.project_id = project_id
        self.engine_session_id = engine_session_id or str(uuid4())
        self.stage_epoch = str(uuid4())
        self._stage_marker = self._active_stage_marker()
        self._applied_revision: str | None = None
        self._control_lease_id: str | None = None
        self._lease_valid = False
        self._snapshot_sequence = 0
        self._receipt_cache_limit = receipt_cache_limit
        self._receipts: OrderedDict[str, tuple[str, CommandReceipt]] = OrderedDict()
        self._transport_safety_reason: str | None = None

    def refresh_stage_epoch(self) -> bool:
        marker = self._active_stage_marker()
        if marker == self._stage_marker:
            return False
        self._stage_marker = marker
        self.stage_epoch = str(uuid4())
        self._applied_revision = None
        self._receipts.clear()
        return True

    def update_control_lease(self, control_lease_id: str | None, valid: bool) -> None:
        self._control_lease_id = control_lease_id if valid else None
        self._lease_valid = bool(valid and control_lease_id)
        if self._lease_valid:
            self._transport_safety_reason = None

    def fail_safe_pause(self, reason: str) -> None:
        if self.runtime.state == "running":
            self.runtime.pause()
        self._transport_safety_reason = reason[:320]
        self._lease_valid = False
        self._control_lease_id = None

    def execute(self, command: CommandEnvelope) -> CommandReceipt:
        checked = CommandEnvelope.from_dict(command.to_dict())
        digest = canonical_sha256(checked.to_dict())
        cached = self._receipts.get(checked.command_id)
        if cached is not None:
            previous_digest, receipt = cached
            if previous_digest != digest:
                return self._failure(checked, "duplicate_command_conflict", "Command ID content changed")
            return receipt
        try:
            self._validate_identity(checked)
            if checked.expired():
                receipt = self._receipt(
                    checked, "expired", error_code="command_expired",
                    message="Command expired before Isaac execution",
                )
            elif checked.command_type == "build_scene":
                receipt = self._build(checked)
            elif checked.command_type == "run":
                self._require_applied_revision(checked)
                self.runtime.run()
                receipt = self._receipt(checked, "succeeded", message="Simulation running")
            elif checked.command_type == "pause":
                self._require_applied_revision(checked)
                self.runtime.pause()
                receipt = self._receipt(checked, "succeeded", message="Simulation paused")
            elif checked.command_type == "reset":
                if self.runtime.state == "running":
                    raise RuntimeError("Pause the simulation before Reset")
                self._require_applied_revision(checked)
                self.runtime.reset()
                receipt = self._receipt(checked, "succeeded", message="Simulation reset")
            elif checked.command_type == "focus_scene":
                focused = self.runtime.focus_scene()
                receipt = self._receipt(
                    checked, "succeeded", message="Viewport focused" if focused else "No interactive viewport",
                )
            elif checked.command_type == "get_state":
                receipt = self._receipt(checked, "succeeded", message="State sampled")
            else:
                raise RuntimeError("Unsupported command")
        except Exception as error:
            receipt = self._failure(checked, type(error).__name__, str(error))
        self._remember(checked.command_id, digest, receipt)
        return receipt

    def snapshot(self) -> SimulationSnapshot:
        self._snapshot_sequence += 1
        runtime_state = "built" if self.runtime.state == "ready" else self.runtime.state
        if runtime_state not in {
            "idle", "built", "running", "paused", "completed", "off_route",
            "unstable", "stage_invalid", "error", "disconnected",
        }:
            runtime_state = "error" if runtime_state != "shutdown" else "disconnected"
        safety_state = self.runtime.safety_latch
        safety_reason = self._transport_safety_reason
        telemetry_available = False
        position = attitude = None
        distance = cross_track = None
        bundle = self.runtime.compiler.bundle
        if bundle is not None and runtime_state not in {"stage_invalid", "disconnected", "error"}:
            try:
                position, attitude = self.runtime.robot_pose_3d()
                command = straight_route_command(
                    position_xy_m=(position[0], position[1]), yaw_rad=attitude[2],
                    start_xy_m=bundle.task.start.position_m[:2],
                    goal_xy_m=bundle.task.goal.position_m[:2],
                    position_tolerance_m=bundle.task.position_tolerance_m,
                    max_linear_speed_mps=bundle.robot.max_linear_speed_mps,
                    max_angular_speed_rps=bundle.robot.max_angular_speed_rps,
                )
                distance = command.distance_m
                cross_track = command.cross_track_error_m
                telemetry_available = True
            except Exception:
                position = attitude = None
        permitted = self._permitted(runtime_state)
        return SimulationSnapshot(
            engine_session_id=self.engine_session_id,
            stage_epoch=self.stage_epoch,
            project_id=self.project_id,
            applied_revision=self._applied_revision,
            run_id=None,
            sequence=self._snapshot_sequence,
            runtime_state=runtime_state,
            safety_state=safety_state or ("bridge_disconnected" if safety_reason else None),
            safety_reason=safety_reason,
            permitted_commands=permitted,
            capabilities=("simulation", "build", "telemetry", "watchdog"),
            sim_time_s=self.runtime.physics_steps / 60.0,
            frame_id="world",
            position_m=position,
            yaw_rad=attitude[2] if attitude else None,
            roll_rad=attitude[0] if attitude else None,
            pitch_rad=attitude[1] if attitude else None,
            linear_speed_mps=None,
            distance_to_goal_m=distance,
            cross_track_error_m=cross_track,
            telemetry_available=telemetry_available,
        )

    def _build(self, command: CommandEnvelope) -> CommandReceipt:
        if self.runtime.state == "running":
            raise RuntimeError("Pause the simulation before Build")
        if set(command.payload) != {"artifact_id", "bundle_sha256", "bundle"}:
            raise ValueError("Build payload shape is invalid")
        bundle_value = command.payload["bundle"]
        if not isinstance(bundle_value, dict):
            raise ValueError("Build bundle must be an object")
        bundle = SpecBundle.from_dict(bundle_value)
        revision = bundle_digest(bundle)
        if (command.payload["bundle_sha256"] != revision
                or command.expected_applied_revision != revision):
            raise ValueError("Build bundle revision is invalid")
        count = self.runtime.build_scene(bundle)
        build_receipt = self.runtime.compiler.build_receipt
        if build_receipt is None:
            raise RuntimeError("Isaac compiler did not publish a build receipt")
        self.runtime.compiler.set_build_metadata(
            source="bridge_registered_artifact", image_count=0,
            request_id=str(command.payload["artifact_id"]),
            plan_sha256=revision,
        )
        self._applied_revision = revision
        return self._receipt(
            command, "succeeded", message=f"Built {count} TwinPulse prims",
            applied_revision=revision, build_fingerprint=build_receipt.fingerprint,
        )

    def _validate_identity(self, command: CommandEnvelope) -> None:
        if command.project_id != self.project_id:
            raise RuntimeError("Command project does not match this engine")
        if command.engine_session_id != self.engine_session_id:
            raise RuntimeError("Command engine session is stale")
        if command.stage_epoch != self.stage_epoch:
            raise RuntimeError("Command stage epoch is stale")
        if (not self._lease_valid or self._control_lease_id is None
                or command.control_lease_id != self._control_lease_id):
            raise RuntimeError("Command control lease is invalid or expired")

    def _require_applied_revision(self, command: CommandEnvelope) -> None:
        if self._applied_revision is None:
            raise RuntimeError("No bridge-applied scene is available")
        if command.expected_applied_revision != self._applied_revision:
            raise RuntimeError("Command revision does not match the applied scene")

    def _receipt(
        self,
        command: CommandEnvelope,
        status: str,
        *,
        message: str = "",
        error_code: str | None = None,
        applied_revision: str | None = None,
        build_fingerprint: str | None = None,
    ) -> CommandReceipt:
        return CommandReceipt(
            command_id=command.command_id, command_type=command.command_type,
            project_id=command.project_id, engine_session_id=command.engine_session_id,
            stage_epoch=command.stage_epoch, status=status,
            message=message[:320], error_code=error_code,
            applied_revision=applied_revision if applied_revision is not None else self._applied_revision,
            build_fingerprint=build_fingerprint,
        )

    def _failure(self, command: CommandEnvelope, code: str, message: str) -> CommandReceipt:
        safe_code = "".join(character if character.isalnum() or character == "_" else "_" for character in code)
        return self._receipt(
            command, "failed", error_code=safe_code[:128] or "command_failed",
            message=message[:320] or "Command failed",
        )

    def _remember(self, command_id: str, digest: str, receipt: CommandReceipt) -> None:
        self._receipts[command_id] = (digest, receipt)
        self._receipts.move_to_end(command_id)
        while len(self._receipts) > self._receipt_cache_limit:
            self._receipts.popitem(last=False)

    def _permitted(self, runtime_state: str) -> tuple[str, ...]:
        commands = ["get_state", "focus_scene"]
        if not self._lease_valid:
            return tuple(commands)
        if runtime_state == "running":
            return ("pause", "get_state", "focus_scene")
        if runtime_state in {"off_route", "unstable"}:
            return ("reset", "get_state", "focus_scene")
        commands.insert(0, "build_scene")
        if self._applied_revision is not None and runtime_state in {"built", "paused", "completed"}:
            commands.insert(1, "run")
            commands.insert(2, "reset")
        return tuple(commands)

    @staticmethod
    def _active_stage_marker() -> tuple[int, str] | None:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return None
        return id(stage), stage.GetRootLayer().identifier
