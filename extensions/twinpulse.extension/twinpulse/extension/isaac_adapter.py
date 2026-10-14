# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Main-thread-only adapter from pure R4 commands to the Isaac runtime."""

from __future__ import annotations

from collections import OrderedDict
import math
from pathlib import Path
from uuid import uuid4

import omni.usd
from pxr import Sdf,UsdGeom

from twinpulse_core import (
    CommandEnvelope,
    CommandReceipt,
    SimulationSnapshot,
    SpecBundle,
    SceneRevision,
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
        project_state_root: Path | None = None,
        session_history_root: Path | None = None,
        engine_session_id: str | None = None,
        receipt_cache_limit: int = 256,
    ) -> None:
        self.runtime = runtime
        self.project_id = project_id
        self.project_state_root = project_state_root
        self.session_history_root = session_history_root if session_history_root is not None else project_state_root
        self.engine_session_id = engine_session_id or str(uuid4())
        self.stage_epoch = str(uuid4())
        self._stage_marker = self._active_stage_marker()
        self._applied_revision: str | None = None
        self.display_build_id = None  # Local capture invalidation, not motion/scene authority.
        self._control_lease_id: str | None = None
        self._lease_valid = False
        self._snapshot_sequence = 0
        self._receipt_cache_limit = receipt_cache_limit
        self._receipts: OrderedDict[str, tuple[str, CommandReceipt]] = OrderedDict()
        self._transport_safety_reason: str | None = None
        self._mission_visual_cursor=None
        self._mission_visual_jobs=[]
        self._mission_geometry_receipts=[]
        self.mission_visual_status='NOT_STARTED'

    def refresh_stage_epoch(self) -> bool:
        marker = self._active_stage_marker()
        if marker == self._stage_marker:
            return False
        self._stage_marker = marker
        self.stage_epoch = str(uuid4())
        self._applied_revision = None
        self.display_build_id = None
        self._receipts.clear()
        self._mission_visual_cursor=None
        self._mission_visual_jobs=[]
        return True

    def rebind_project(self, ticket):
        """Recoverable project switch; preserve current owned USD before clearing."""
        from twinpulse_app.project_store import checked_project_id
        from hashlib import sha256
        project_id=checked_project_id(ticket['project_id'])
        if self.runtime.state=='running':raise ValueError('PROJECT_SWITCH_SIM_RUNNING')
        stage=omni.usd.get_context().get_stage()
        backup=None
        if stage and stage.GetPrimAtPath('/World/TwinPulse'):
            if not self.runtime.compiler._is_owned_root(stage.GetPrimAtPath('/World/TwinPulse')):
                raise ValueError('PROJECT_SWITCH_FOREIGN_ROOT')
            if self.project_state_root is None:raise ValueError('PROJECT_SWITCH_BACKUP_ROOT_REQUIRED')
            root=self.project_state_root.resolve()
            folder=root/'projects'/checked_project_id(self.project_id)/'scene-switch-checkpoints'
            folder.mkdir(parents=True,exist_ok=True)
            if not folder.resolve().is_relative_to(root):raise ValueError('PROJECT_SWITCH_BACKUP_PATH_INVALID')
            identity=str(uuid4())
            path=folder/(identity+'.usda')
            backup=Sdf.Layer.CreateAnonymous('TwinPulseProjectCheckpoint.usda')
            Sdf.CreatePrimInLayer(backup,'/World')
            if not Sdf.CopySpec(stage.Flatten(),'/World/TwinPulse',backup,'/World/TwinPulse'):
                raise ValueError('PROJECT_SWITCH_CHECKPOINT_FAILED')
            if not backup.Export(str(path)):raise ValueError('PROJECT_SWITCH_CHECKPOINT_FAILED')
            verified_layer=Sdf.Layer.FindOrOpen(str(path))
            if verified_layer is None or not verified_layer.GetPrimAtPath('/World/TwinPulse'):
                raise ValueError('PROJECT_SWITCH_CHECKPOINT_VERIFY_FAILED')
            self.last_project_checkpoint={'project_id':self.project_id,'file':str(path),
                'sha256':sha256(path.read_bytes()).hexdigest(),'applied_revision':self._applied_revision}
        try:
            self._project_rebind_started=True
            self.runtime.clear_project()
        except Exception:
            current=stage.GetPrimAtPath('/World/TwinPulse') if stage else None
            if backup and stage and (not current or self.runtime.compiler._is_owned_root(current)):
                Sdf.CopySpec(backup,'/World/TwinPulse',stage.GetRootLayer(),'/World/TwinPulse')
            raise
        self.project_id=project_id;self.stage_epoch=ticket['new_stage_epoch']
        self._stage_marker=self._active_stage_marker()
        self._applied_revision=None;self.display_build_id=None
        self._control_lease_id=None;self._lease_valid=False;self._receipts.clear()
        self._transport_safety_reason=None;self._snapshot_sequence=0
        self._mission_visual_cursor=None;self._mission_visual_jobs=[];self._mission_geometry_receipts=[]
        self.mission_visual_status='NOT_STARTED'
        result=self.snapshot()
        self._project_rebind_started=False
        return result

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

    def mission_objects_revision(self):
        scene=self.runtime.compiler.site_scene
        return canonical_sha256(scene.to_dict()['objects']) if scene else None

    def update_mission_geometry(self,value):
        """Compose immutable corrected geometry only, never a transported pose."""
        from twinpulse_core.active_mission_visual import checked_active_geometry
        geometry=checked_active_geometry(value)
        if not self._lease_valid or self.runtime.state=='running':raise ValueError('ACTIVE_VISUAL_LEASE_OR_TIMELINE')
        if (geometry['engine_session_id']!=self.engine_session_id or geometry['stage_epoch']!=self.stage_epoch
                or geometry['project_id']!=self.project_id
                or geometry['previous_objects_revision']!=self.mission_objects_revision()):
            raise ValueError('ACTIVE_VISUAL_ENGINE_OR_ROOM_CHANGED')
        if self.project_state_root is None:raise ValueError('ACTIVE_GEOMETRY_STATE_ROOT_REQUIRED')
        compiler=self.runtime.compiler;root=compiler.stage.GetPrimAtPath('/World/TwinPulse')
        if not root or not compiler._is_owned_root(root):raise ValueError('ACTIVE_VISUAL_UNOWNED_ROOT')
        if (self._mission_visual_cursor and self._mission_visual_cursor[0]!=geometry['job_id']
                and geometry['job_id'] in self._mission_visual_jobs):raise ValueError('ACTIVE_VISUAL_OUT_OF_ORDER')
        descriptor={'kind':'active_mission_geometry_v1','mission_id':geometry['job_id'],
                    'correction_revision':geometry['correction_revision'],
                    'previous_objects_revision':geometry['previous_objects_revision'],'objects_revision':geometry['objects_revision']}
        from twinpulse_app.automatic_mission_visual import checked_mission_geometry
        _,_,_,scene=checked_mission_geometry(self.project_state_root,self.project_id,descriptor)
        # Reuse the existing owned-root transactional Build and rollback path.
        # This fixed engine-side payload cannot contain code or a live pose.
        presentation_prim=compiler.stage.GetPrimAtPath('/World/TwinPulse/Presentation')
        presentation=presentation_prim.GetCustomDataByKey('twinpulsePresentation') if presentation_prim.IsValid() else None
        payload={'artifact_id':'active-geometry-'+geometry['revision'],'scene_revision':scene.revision,
                 'scene':scene.to_dict(),'visual_preview':descriptor}
        if presentation is not None:payload['presentation']=presentation
        command=CommandEnvelope(command_id=str(uuid4()),command_type='build_site_scene',project_id=self.project_id,
            engine_session_id=self.engine_session_id,stage_epoch=self.stage_epoch,control_lease_id=self._control_lease_id,
            expected_applied_revision=scene.revision,payload=payload,ttl_s=1.)
        self._validate_identity(command)
        self._build_site_scene(command)
        if self.mission_objects_revision()!=geometry['objects_revision']:raise ValueError('ACTIVE_GEOMETRY_BUILD_NOT_CONFIRMED')
        from .bedroom_preview import PREVIEW_PATH
        compiler.stage.GetPrimAtPath(PREVIEW_PATH).SetCustomDataByKey('poseStatus','STATIC_PREVIEW_NOT_CURRENT')
        self._mission_geometry_receipts=(self._mission_geometry_receipts+[geometry])[-32:]
        self.mission_visual_status='ACTIVE_GEOMETRY_COMPOSED_NOT_CURRENT'

    def update_mission_visual(self,value):
        from twinpulse_core.active_mission_visual import checked_active_frame
        frame=checked_active_frame(value)
        if not self._lease_valid or self.runtime.state=='running':raise ValueError('ACTIVE_VISUAL_LEASE_OR_TIMELINE')
        if (frame['engine_session_id']!=self.engine_session_id or frame['stage_epoch']!=self.stage_epoch
            or frame['project_id']!=self.project_id or frame['objects_revision']!=self.mission_objects_revision()):
            raise ValueError('ACTIVE_VISUAL_ENGINE_OR_ROOM_CHANGED')
        cursor=(frame['job_id'],frame['sequence'])
        if self._mission_visual_cursor and cursor[0]!=self._mission_visual_cursor[0] and cursor[0] in self._mission_visual_jobs:
            raise ValueError('ACTIVE_VISUAL_OUT_OF_ORDER')
        if self._mission_visual_cursor and self._mission_visual_cursor[0]==cursor[0] and cursor[1]<=self._mission_visual_cursor[1]:
            raise ValueError('ACTIVE_VISUAL_OUT_OF_ORDER')
        compiler=self.runtime.compiler;root=compiler.stage.GetPrimAtPath('/World/TwinPulse')
        if not root or not compiler._is_owned_root(root):raise ValueError('ACTIVE_VISUAL_UNOWNED_ROOT')
        from twinpulse_app.project_store import named_project_state_path
        legacy_default=(self.project_id=='default' and (self.project_state_root is None
            or not named_project_state_path(self.project_state_root,self.project_id).exists()))
        if legacy_default:
            from twinpulse_app.bedroom_review import load_bedroom_source
            _,manifest,_=load_bedroom_source()
        else:
            recipe=self.project_state_root/'projects'/self.project_id/'room_recipe.json'
            manifest=None
            if recipe.exists():
                from twinpulse_app.room_recipe import load_project_room_recipe,load_project_room_visual
                draft,_=load_project_room_recipe(self.project_state_root,self.project_id)
                loaded=load_project_room_visual(self.project_state_root,self.project_id,draft)
                if loaded is not None:manifest,_=loaded
            if manifest is None:
                # Current chat/imported rooms need not pre-copy a legacy Burger
                # visual. Check the saved draft and derived revision before the
                # pinned asset; invalid legacy recipe/assets still raise above.
                from twinpulse_app.chat_inspection_visual import active_chat_placement
                manifest=active_chat_placement(self.project_state_root,self.project_id,compiler.site_scene)
                from .bedroom_preview import PREVIEW_PATH,_compose_fixed_burger
                marker=compiler.stage.GetPrimAtPath(PREVIEW_PATH)
                if not marker or marker.GetCustomDataByKey('activeChatSceneRevision')!=compiler.site_scene.revision:
                    _compose_fixed_burger(compiler,frame['visual']['pose_room'],manifest['robot_placement']['position_m'][2],
                        {'activeChatSceneRevision':compiler.site_scene.revision,'poseStatus':'STATIC_PREVIEW_NOT_CURRENT'})
        from .bedroom_preview import compose_automatic_mission_visual
        compose_automatic_mission_visual(compiler,manifest,frame['visual'])
        marker=compiler.stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission')
        marker.SetCustomDataByKey('displayStatus','ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED')
        UsdGeom.Imageable(marker).MakeVisible()
        from .bedroom_preview import PREVIEW_PATH
        compiler.stage.GetPrimAtPath(PREVIEW_PATH).SetCustomDataByKey('poseStatus','ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED')
        UsdGeom.Imageable(compiler.stage.GetPrimAtPath(PREVIEW_PATH)).MakeVisible()
        if cursor[0] not in self._mission_visual_jobs:self._mission_visual_jobs=(self._mission_visual_jobs+[cursor[0]])[-32:]
        self._mission_visual_cursor=cursor;self.mission_visual_status='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED'

    def mark_mission_visual_inactive(self,reason):
        # Preserve raw history, but hide formerly active pose/cloud after the
        # stream, mission or lease ends. Static saved report displays are separate.
        from .bedroom_preview import PREVIEW_PATH
        stage=self.runtime.compiler.stage
        if stage is None:
            self.mission_visual_status=reason
            return
        for path,key in (('/World/TwinPulse/Presentation/AutomaticMission','displayStatus'),(PREVIEW_PATH,'poseStatus')):
            marker=stage.GetPrimAtPath(path)
            if marker and marker.GetCustomDataByKey(key)=='ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED':
                marker.SetCustomDataByKey(key,'LAST_OBSERVATION_NOT_CURRENT')
                UsdGeom.Imageable(marker).MakeInvisible()
        self.mission_visual_status=reason

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
            elif checked.command_type == "build_site_scene":
                receipt = self._build_site_scene(checked)
            elif checked.command_type == "run":
                if set(checked.payload) == {'site_simulation'}:
                    self._require_applied_revision(checked)
                    self.runtime.run_site_simulation(checked.payload['site_simulation'])
                elif checked.payload:
                    raise ValueError('Run payload shape is invalid')
                elif self.runtime.compiler.bundle is None:
                    raise RuntimeError("Site scene has no validated robot mission; Run is unavailable")
                else:
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
        safety_reason = self._transport_safety_reason or getattr(self.runtime, 'site_error', None)
        telemetry_available = False
        position = attitude = None
        distance = cross_track = None
        bundle = self.runtime.compiler.bundle
        site_plan = getattr(self.runtime, 'site_plan', None)
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
        elif site_plan is not None and runtime_state in {'running', 'paused', 'completed'}:
            try:
                position, attitude = self.runtime.robot_pose_3d()
                distance = math.dist(position[:2], site_plan['goal'])
                cross_track = None
                telemetry_available = True
            except Exception:
                position = attitude = None
        permitted = self._permitted(runtime_state)
        return SimulationSnapshot(
            engine_session_id=self.engine_session_id,
            stage_epoch=self.stage_epoch,
            project_id=self.project_id,
            applied_revision=self._applied_revision,
            run_id=site_plan['plan_id'] if site_plan else None,
            sequence=self._snapshot_sequence,
            runtime_state=runtime_state,
            safety_state=safety_state or ("bridge_disconnected" if safety_reason else None),
            safety_reason=safety_reason,
            permitted_commands=permitted,
            capabilities=("project_rebind_v1", "simulation", "build", "telemetry", "watchdog", "site_scene_build_v2", "generation_room_visual_v1", "bedroom_visual_v1", "bedroom_replay_v1", "room_scan_replay_v1", "project_room_visual_v1", "presentation_preset_v1", "automatic_mission_visual_v1", "current_inspection_visual_v1", "site_simulation_v1", "site_simulation_preview_v1", "exact_goal_demonstration_v1"),
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
        self.display_build_id = command.command_id
        return self._receipt(
            command, "succeeded", message=f"Built {count} TwinPulse prims",
            applied_revision=revision, build_fingerprint=build_receipt.fingerprint,
        )

    def _build_site_scene(self, command: CommandEnvelope) -> CommandReceipt:
        if self.runtime.state == "running":
            raise RuntimeError("Pause the simulation before Build")
        fields = {"artifact_id", "scene_revision", "scene"}
        if set(command.payload) not in (fields, fields | {"visual_preview"}, fields | {"presentation"},
                                        fields | {"visual_preview", "presentation"}, fields | {'simulation_preview'},
                                        fields | {'simulation_preview', 'presentation'}):
            raise ValueError("Site Build payload shape is invalid")
        from twinpulse_core.presentation import checked_presentation
        presentation = (checked_presentation(command.payload["presentation"])
                        if "presentation" in command.payload else None)
        scene_value = command.payload["scene"]
        if not isinstance(scene_value, dict):
            raise ValueError("Site scene must be an object")
        scene = SceneRevision.from_dict(scene_value)
        if (command.payload["scene_revision"] != scene.revision
                or command.expected_applied_revision != scene.revision):
            raise ValueError("Site scene revision is invalid")
        # Typed appearance comes from a checked project or exact ephemeral plan, not IDs
        # guessed from a generic scene or executable provider-supplied assets.
        room_plan = None
        if self.project_state_root is not None:
            from twinpulse_app.project_store import ProjectStore
            store = ProjectStore.for_project(self.project_state_root, self.project_id)
            record = store.load()
            if record is not None and record.site_draft is not None:
                # Derived scenes retain original provenance; visual_bindings
                # additionally proves each CURRENT member's shape and pose.
                source = record.site_draft.site.scene
                if scene.source_ref == source.source_ref and scene.id == source.id:
                    room_plan = record.site_draft.plan
                    from twinpulse_app.scene_changes import SceneChangeStore
                    edited_plan, edited_site = SceneChangeStore(store.path.with_suffix('.scene-changes.json'),
                        project_id=self.project_id, source=record.site_draft).load().replay(record.site_draft)
                    if edited_site.scene.revision == scene.revision:
                        room_plan = edited_plan
        descriptor = command.payload.get('visual_preview', {})
        generation_preview = descriptor.get('kind') == 'generation_room_visual_v1'
        if generation_preview:
            from twinpulse_core.generation_visual import checked_generation_visual
            # The ephemeral candidate takes precedence over an older saved plan.
            room_plan = checked_generation_visual(descriptor, scene, self.project_id)
        room_visual_result = None
        has_preview = "visual_preview" in command.payload or 'simulation_preview' in command.payload
        if has_preview or room_plan is not None:
            from .bedroom_preview import compose_bedroom_preview
            descriptor = command.payload.get("visual_preview", {})
            mission_visual=None
            inspection_visual=None
            sim_preview = command.payload.get('simulation_preview')
            if not has_preview or generation_preview:
                pass
            elif sim_preview is not None:
                from twinpulse_core.site_simulation import checked_plan
                from twinpulse_app.simulation_assets import burger_inventory
                sim_preview = checked_plan(scene, sim_preview)
                if sim_preview['asset_files'] != burger_inventory():
                    raise ValueError('SIM_ASSET_BYTES_CHANGED')
            elif descriptor.get('kind')=='current_inspection_visual_v1':
                if self.project_state_root is None:raise ValueError('INSPECTION_DISPLAY_STATE_UNAVAILABLE')
                from twinpulse_app.chat_inspection_visual import checked_inspection_visual
                expected,inspection_visual=checked_inspection_visual(self.session_history_root,self.project_id,descriptor,
                    source_root=self.project_state_root)
                if scene.revision!=expected.revision:raise ValueError('INSPECTION_DISPLAY_SCENE_CHANGED')
            elif descriptor.get('kind')=='active_mission_geometry_v1':
                from twinpulse_app.automatic_mission_visual import checked_mission_geometry
                draft,manifest,asset_root,expected=checked_mission_geometry(self.project_state_root,self.project_id,descriptor)
                if scene.revision!=expected.revision:raise ValueError('ACTIVE_GEOMETRY_SCENE_CHANGED')
            elif descriptor.get('kind')=='automatic_mission_visual_v1':
                if self.project_state_root is None:raise ValueError('Mission visual state root unavailable')
                from twinpulse_app.automatic_mission_visual import checked_mission_visual
                draft,manifest,asset_root,expected,mission_visual=checked_mission_visual(
                    self.project_state_root,self.project_id,descriptor)
                if scene.revision!=expected.revision:raise ValueError('Mission visual scene revision changed')
            elif descriptor.get("kind") == "project_room_visual_v1":
                if self.project_state_root is None or self.project_id == "default":
                    raise ValueError("Named project visual root is unavailable")
                from twinpulse_app.room_recipe import checked_project_room_descriptor
                draft, manifest, asset_root = checked_project_room_descriptor(
                    descriptor, scene, self.project_state_root, self.project_id)
            else:
                if self.project_id != "default":
                    raise ValueError("Default bedroom preview cannot render under a named project")
                from twinpulse_app.bedroom_review import checked_bedroom_descriptor
                draft, manifest, asset_root = checked_bedroom_descriptor(descriptor, scene)
            # Geometry compilation rolls itself back, but the subsequent visual
            # composition is a second mutating step. Save only our owned root so
            # a failed visual cannot leave the user's last good stage replaced.
            stage = omni.usd.get_context().get_stage()
            if stage is None:
                raise RuntimeError("No USD stage is open")
            root = stage.GetPrimAtPath("/World/TwinPulse")
            had_root = root.IsValid()
            if had_root and not self.runtime.compiler._is_owned_root(root):
                raise RuntimeError("Existing TwinPulse root is not owned by this extension")
            layer = stage.GetEditTarget().GetLayer()
            backup = None
            if had_root:
                if layer.GetPrimAtPath("/World/TwinPulse") is None:
                    raise RuntimeError("Cannot safely snapshot composed TwinPulse content")
                backup = Sdf.Layer.CreateAnonymous("twinpulse-visual-build-backup.usda")
                Sdf.CreatePrimInLayer(backup, "/World")
                if not Sdf.CopySpec(layer, "/World/TwinPulse", backup, "/World/TwinPulse"):
                    raise RuntimeError("Could not snapshot last good TwinPulse scene")
            old_scene = self.runtime.compiler.site_scene
            old_bundle = self.runtime.compiler.bundle
            old_receipt = self.runtime.compiler.build_receipt
            old_applied = self._applied_revision
            try:
                # Stop runtime control and validate ownership before authoring preview prims.
                count = self.runtime.build_site_scene(scene, presentation=presentation)
                if sim_preview is not None:
                    from .bedroom_preview import compose_simulation_preview
                    compose_simulation_preview(self.runtime.compiler, sim_preview)
                elif inspection_visual is not None:
                    from .bedroom_preview import compose_inspection_preview
                    compose_inspection_preview(self.runtime.compiler,inspection_visual)
                elif has_preview and not generation_preview:
                    compose_bedroom_preview(self.runtime.compiler, draft, manifest, asset_root,
                                            pinned_project_visual=self.project_id!='default',
                                            reviewed_scene=scene, presentation=presentation)
                else:
                    stage.RemovePrim('/World/TwinPulse/Presentation/BurgerPhotoPreview')
                    stage.RemovePrim('/World/TwinPulse/Presentation/BedroomTrace')
                if mission_visual is not None:
                    from .bedroom_preview import compose_automatic_mission_visual
                    compose_automatic_mission_visual(self.runtime.compiler,manifest,mission_visual)
                if 'replay' in descriptor:
                    from .bedroom_preview import compose_bedroom_replay
                    compose_bedroom_replay(self.runtime.compiler, draft, manifest, command.payload['visual_preview']['replay'])
                if 'localization' in descriptor:
                    from .bedroom_preview import compose_saved_scan_preview
                    compose_saved_scan_preview(self.runtime.compiler,draft,manifest,descriptor['localization'])
                from .room_visuals import compose_room_visuals, clear_room_visuals
                if room_plan is not None:
                    room_visual_result = compose_room_visuals(self.runtime.compiler, scene, room_plan)
                elif sim_preview is None and inspection_visual is None:
                    compose_room_visuals(self.runtime.compiler, scene, draft.plan)
                else:
                    clear_room_visuals(stage)
            except Exception as build_error:
                try:
                    if stage is not omni.usd.get_context().get_stage():
                        raise RuntimeError("Stage changed during failed visual Build")
                    current_root = stage.GetPrimAtPath("/World/TwinPulse")
                    if current_root.IsValid():
                        if not self.runtime.compiler._is_owned_root(current_root):
                            raise RuntimeError("Owned root changed during failed visual Build")
                        # Copy over the existing owned root. Removing its
                        # PhysicsScene first expires SimulationManager handles
                        # even when the same USD bytes are recreated afterward.
                        if backup is None:
                            stage.RemovePrim("/World/TwinPulse")
                    if backup is not None and not Sdf.CopySpec(
                            backup, "/World/TwinPulse", layer, "/World/TwinPulse"):
                        raise RuntimeError("Last good TwinPulse scene could not be restored")
                    if backup is not None:
                        # CopySpec preserves existing child positions in the
                        # destination layer. A rebuilt Environment otherwise
                        # moves behind PhysicsScene, changing the saved USD even
                        # though geometry is equal. Restore authored order only;
                        # keep the live PhysicsScene prim and its handles intact.
                        pending = [(backup.GetPrimAtPath('/World/TwinPulse'),
                                    layer.GetPrimAtPath('/World/TwinPulse'))]
                        while pending:
                            source_spec, restored_spec = pending.pop()
                            names = list(source_spec.nameChildren.keys())
                            if set(names) != set(restored_spec.nameChildren.keys()):
                                raise RuntimeError('Restored owned child set differs from backup')
                            restored_spec.nameChildren[:] = [restored_spec.nameChildren[name] for name in names]
                            pending.extend((source_spec.nameChildren[name], restored_spec.nameChildren[name])
                                           for name in names)
                    self.runtime.compiler.bind_restored_scene(stage, old_bundle, old_scene, old_receipt)
                    # Restore display/identity, never a prior execution permit or
                    # an articulation handle bound to the removed USD prims.
                    self.runtime.site_plan = None
                    self.runtime._robot = self.runtime._controller = None
                    self.runtime._physics_steps = 0
                    self.runtime._state = 'ready' if old_receipt is not None else 'idle'
                    self.runtime._bound_stage_identifier = self.runtime._stage_key(stage) if old_receipt is not None else None
                    self._applied_revision = old_applied
                except Exception as rollback_error:
                    self._applied_revision = None
                    self.runtime.compiler.invalidate_stage()
                    self.runtime._state = 'stage_invalid'
                    self.runtime.site_error = 'VISUAL_BUILD_ROLLBACK_FAILED'
                    raise RuntimeError(f"Visual Build failed and stage rollback FAILED: {rollback_error}") from build_error
                raise
        else:
            count = self.runtime.build_site_scene(scene, presentation=presentation)
            # An ordinary scene-only build must not retain a prior visual robot.
            stage = omni.usd.get_context().get_stage()
            if stage is not None:
                stage.RemovePrim("/World/TwinPulse/Presentation/BurgerPhotoPreview")
                stage.RemovePrim('/World/TwinPulse/Presentation/BedroomTrace')
                from .room_visuals import clear_room_visuals
                clear_room_visuals(stage)
        receipt = self.runtime.compiler.build_receipt
        if receipt is None or not self.runtime.compiler.matches_site_scene(scene):
            raise RuntimeError("Isaac compiler did not prove the site scene Build")
        self._applied_revision = scene.revision
        self.display_build_id = command.command_id
        visual_message = (f"; catalog groups={room_visual_result['groups']} meshes={room_visual_result['meshes']}"
                          if generation_preview and room_visual_result is not None else '')
        return self._receipt(
            command, "succeeded", message=f"Built {count} site prims; visual preview only, no driven robot or mission{visual_message}",
            applied_revision=scene.revision, build_fingerprint=receipt.fingerprint,
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
        commands.insert(0, "build_site_scene")
        commands.insert(0, "build_scene")
        if (self._applied_revision is not None and self.runtime.compiler.bundle is not None
                and runtime_state in {"built", "paused", "completed"}):
            commands.insert(1, "run")
            commands.insert(2, "reset")
        elif (self._applied_revision is not None and self.runtime.compiler.site_scene is not None
              and runtime_state in {"built", "paused", "completed", "error"}):
            commands.insert(1, "reset")
        return tuple(commands)

    @staticmethod
    def _active_stage_marker() -> tuple[int, str] | None:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return None
        return id(stage), stage.GetRootLayer().identifier
