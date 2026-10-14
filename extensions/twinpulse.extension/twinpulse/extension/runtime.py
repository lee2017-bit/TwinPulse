# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Extension runtime state and lifecycle-safe physics controls."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

import isaacsim.core.experimental.utils.app as app_utils
import omni.physics.core
import omni.timeline
import omni.usd
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.experimental.wheeled_robots.controllers import DifferentialController
from isaacsim.robot.experimental.wheeled_robots.robots import WheeledRobot

from .scene_compiler import CAMERA_PATH, ROBOT_PATH, SceneCompiler

if TYPE_CHECKING:
    from twinpulse_core import SpecBundle, SceneRevision


StatusCallback = Callable[[str], None]


class TwinPulseRuntime:
    def __init__(self, status_callback: StatusCallback | None = None) -> None:
        self.compiler = SceneCompiler()
        self._status_callback = status_callback
        self._timeline = omni.timeline.get_timeline_interface()
        self._physics_interface = omni.physics.core.get_physics_simulation_interface()
        self._physics_subscription = None
        self._state = "idle"
        self._shutdown = False
        self._physics_steps = 0
        self._robot = None
        self._controller = None
        self.site_plan = None
        self.site_error = None
        self._site_waypoint = 0
        self._site_stall_steps = 0
        self._site_best_distance = float('inf')
        self._safety_latch: str | None = None
        self._bound_stage_identifier: tuple[int, str] | None = None
        self._stage_subscription = omni.usd.get_context().get_stage_event_stream().create_subscription_to_pop(
            self._on_stage_event, name="TwinPulse stage lifecycle"
        )

    @property
    def state(self) -> str:
        return self._state

    @property
    def has_active_subscription(self) -> bool:
        return self._physics_subscription is not None

    @property
    def shutdown_complete(self) -> bool:
        return (self._shutdown and self._physics_subscription is None
                and self._stage_subscription is None)

    @property
    def physics_steps(self) -> int:
        return self._physics_steps

    @property
    def safety_latch(self) -> str | None:
        return self._safety_latch

    def robot_position(self) -> tuple[float, float, float]:
        """Return the live physics pose, falling back to authored USD before initialization."""
        if self._robot is None:
            return self.compiler.robot_position()
        positions, _ = self._robot.get_world_poses()
        values = positions.numpy() if hasattr(positions, "numpy") else positions
        return tuple(float(value) for value in values[0])

    def robot_pose(self) -> tuple[tuple[float, float, float], float]:
        """Return live position and planar yaw in radians (Isaac WXYZ quaternion convention)."""
        position, (_, _, yaw) = self.robot_pose_3d()
        return position, yaw

    def robot_pose_3d(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Return live position and roll/pitch/yaw in radians."""
        if self._robot is None:
            return self.compiler.robot_position(), (0.0, 0.0, 0.0)
        positions, orientations = self._robot.get_world_poses()
        position_values = positions.numpy() if hasattr(positions, "numpy") else positions
        orientation_values = orientations.numpy() if hasattr(orientations, "numpy") else orientations
        position = tuple(float(value) for value in position_values[0])
        w, x, y, z = (float(value) for value in orientation_values[0])
        roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
        pitch_term = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(pitch_term)
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        return position, (roll, pitch, yaw)

    def _status(self, message: str) -> None:
        if self._status_callback is not None:
            self._status_callback(message)

    def build_scene(self, bundle: "SpecBundle") -> int:
        if bundle is None:
            raise RuntimeError("A validated generated draft is required before Build")
        target = bundle
        self._stop_control()
        self.site_plan = None
        self.site_error = None
        if self._timeline.is_playing():
            app_utils.stop()
        previous = self.compiler.bundle
        previous_state = self._state
        try:
            count = self.compiler.compile(target)
        except Exception:
            self._state = "ready" if previous is not None else previous_state
            if previous is not None:
                self._status("Build failed; previous scene restored and remains stopped")
            raise
        self._configure_robot(target)
        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cpu")
        physics_scenes = SimulationManager.get_physics_scenes()
        if physics_scenes:
            physics_scenes[0].set_enabled_gpu_dynamics(False)
        self._state = "ready"
        self._safety_latch = None
        stage = omni.usd.get_context().get_stage()
        self._bound_stage_identifier = self._stage_key(stage) if stage is not None else None
        self._physics_steps = 0
        self.focus_scene()
        self._status(f"Ready - {count} TwinPulse prims")
        return count

    def build_site_scene(self, scene: "SceneRevision", *, presentation: dict | None = None) -> int:
        """Author scene geometry only. Navigation and robot control remain unavailable."""
        owned_sim=self.site_plan is not None
        self._stop_control()
        self.site_plan = None
        self.site_error = None
        if self._timeline.is_playing():
            app_utils.stop()
        count = self.compiler.compile_site_scene(scene, presentation=presentation)
        # The compiler's same-scene fast path intentionally preserves geometry.
        # A new Build must still discard our previous driven articulation, not
        # clear only its Python plan and leave an unbound SimBurger behind.
        if owned_sim:
            robot=self.compiler.stage.GetPrimAtPath('/World/TwinPulse/SimBurger')
            if robot and robot.GetCustomDataByKey('executionMode')=='SIM_ONLY_NOT_PHYSICAL':
                self.compiler.stage.RemovePrim('/World/TwinPulse/SimBurger')
        self._robot = None
        self._controller = None
        self._state = "ready"
        self._safety_latch = None
        stage = omni.usd.get_context().get_stage()
        self._bound_stage_identifier = self._stage_key(stage) if stage is not None else None
        self._physics_steps = 0
        self.focus_scene()
        self._status(f"Site scene ready - {count} TwinPulse prims; Run unavailable")
        return count

    def run_site_simulation(self, value: dict) -> None:
        """Reference the existing Burger's PhysX variant, never teleport each tick."""
        from pxr import Gf, UsdGeom, UsdPhysics
        from twinpulse_core.site_simulation import checked_plan
        from twinpulse_app.simulation_assets import ASSET_ROOT, burger_inventory
        self._assert_current_site_scene()
        plan = checked_plan(self.compiler.site_scene, value)
        if plan['asset_files'] != burger_inventory():
            raise ValueError('SIM_ASSET_BYTES_CHANGED')
        if self.state not in {'ready', 'paused', 'completed'} or self.safety_latch:
            raise RuntimeError('SIM_IDLE_WITHOUT_SAFETY_LATCH_REQUIRED')
        stage = self.compiler.stage
        path = '/World/TwinPulse/SimBurger'
        if self.site_plan is not None:
            position, yaw = self.robot_pose()
            if math.dist(position[:2], plan['start']) > .08 or abs(math.atan2(math.sin(yaw-plan['yaw_rad']), math.cos(yaw-plan['yaw_rad']))) > .1:
                raise ValueError('SIM_START_POSE_CHANGED')
        else:
            if stage.GetPrimAtPath(path):
                raise RuntimeError('SIM_ROBOT_PATH_ALREADY_EXISTS')
            try:
                root = UsdGeom.Xform.Define(stage, path)
                root.GetPrim().GetReferences().AddReference(str(ASSET_ROOT/'turtlebot3_burger.usda'))
                root.GetPrim().GetVariantSets().GetVariantSet('Physics').SetVariantSelection('physx')
                root.ClearXformOpOrder()
                root.AddTranslateOp().Set(Gf.Vec3d(*plan['start'], plan['spawn_z_m']))
                root.AddRotateZOp().Set(math.degrees(plan['yaw_rad']))
                root.GetPrim().SetCustomDataByKey('executionMode', 'SIM_ONLY_NOT_PHYSICAL')
                articulation_path = path+'/Geometry/base_footprint/base_link'
                articulation = stage.GetPrimAtPath(articulation_path)
                if not articulation or not articulation.HasAPI(UsdPhysics.ArticulationRootAPI):
                    raise RuntimeError('SIM_BURGER_ARTICULATION_MISSING')
                for name in ('wheel_left_joint', 'wheel_right_joint'):
                    joint = stage.GetPrimAtPath(path+'/Physics/'+name)
                    if not joint or not joint.IsA(UsdPhysics.RevoluteJoint):
                        raise RuntimeError('SIM_BURGER_WHEEL_JOINT_MISSING')
                    drive = UsdPhysics.DriveAPI.Apply(joint, 'angular')
                    drive.CreateStiffnessAttr(0.)
                    drive.CreateDampingAttr(100.)
                    drive.CreateMaxForceAttr(5.)
                    drive.CreateTargetVelocityAttr(0.)
                self._robot = WheeledRobot(paths=articulation_path,
                                          wheel_dof_names=['wheel_left_joint', 'wheel_right_joint'])
                self._controller = DifferentialController(wheel_radius=.033, wheel_base=.160)
                SimulationManager.setup_simulation(dt=1./60., device='cpu')
                SimulationManager.enable_gpu_dynamics(False)
            except Exception:
                stage.RemovePrim(path)
                self._robot = self._controller = None
                raise
            # The old visual-only pose is not displayed beside a driven articulation.
            preview = stage.GetPrimAtPath('/World/TwinPulse/Presentation/BurgerPhotoPreview')
            if preview:
                UsdGeom.Imageable(preview).MakeInvisible()
        self.site_plan = plan
        self._site_waypoint = self._site_stall_steps = self._physics_steps = 0
        self._site_best_distance = float('inf')
        if self._physics_subscription is None:
            self._physics_subscription = self._physics_interface.subscribe_physics_on_step_events(
                pre_step=True, order=0, on_update=self._on_physics_step)
        app_utils.play()
        self._state = 'running'
        self._status('SIM Burger Physics running on the reviewed room route')

    def _site_zero(self) -> None:
        from pxr import UsdPhysics
        stage = omni.usd.get_context().get_stage()
        if stage is None or stage is not self.compiler.stage:
            return
        for name in ('wheel_left_joint', 'wheel_right_joint'):
            joint = stage.GetPrimAtPath('/World/TwinPulse/SimBurger/Physics/'+name)
            if joint:
                UsdPhysics.DriveAPI(joint, 'angular').GetTargetVelocityAttr().Set(0.)
        if self._robot is not None and self._controller is not None and self._physics_steps > 20:
            self._robot.apply_wheel_actions(self._controller.forward([0., 0.]))

    def _site_physics_step(self) -> None:
        from twinpulse_core.site_simulation import waypoint_command
        try:
            if self._state != 'running':
                self._site_zero()
                return
            stage = omni.usd.get_context().get_stage()
            if stage is not self.compiler.stage or self._stage_key(stage) != self._bound_stage_identifier:
                raise RuntimeError('SIM_STAGE_CHANGED')
            if self._physics_steps <= 20:
                return
            if self._physics_steps % 60 == 0:
                self._assert_current_site_scene()
            position, attitude = self.robot_pose_3d()
            if (not all(math.isfinite(v) for v in (*position, *attitude))
                    or abs(attitude[0]) > math.radians(15) or abs(attitude[1]) > math.radians(15)):
                raise RuntimeError('SIM_POSE_UNSTABLE')
            plan = self.site_plan
            if self._physics_steps/60. > plan['max_sim_time_s']:
                raise RuntimeError('SIM_TIME_LIMIT_EXCEEDED')
            target = plan['route'][self._site_waypoint]
            linear, angular, arrived = waypoint_command(position[:2], attitude[2], target)
            if arrived:
                self._site_waypoint += 1
                self._site_stall_steps = 0
                self._site_best_distance = float('inf')
                self._site_zero()
                if self._site_waypoint == len(plan['route']):
                    self._state = 'completed'
                    self._status('SIM goal reached from live PhysX pose')
                return
            distance = math.dist(position[:2], target)
            if distance < self._site_best_distance-.005:
                self._site_best_distance = distance
                self._site_stall_steps = 0
            elif linear > 0:
                self._site_stall_steps += 1
            if self._site_stall_steps > 600:
                raise RuntimeError('SIM_PROGRESS_STALLED')
            self._robot.apply_wheel_actions(self._controller.forward([linear, angular]))
        except Exception as error:
            self.site_error = f'{type(error).__name__}: {error}'[:320]
            try:
                self._site_zero()
            except Exception as stop_error:
                self.site_error = f'{self.site_error}; cleanup: {type(stop_error).__name__}: {stop_error}'[:320]
            # A zero drive request is not proof that residual Physics motion
            # stopped. Freeze this owned SIM timeline on every execution fault.
            app_utils.pause()
            self._safety_latch = 'simulation_error'
            self._state = 'error'
            self._status(f'SIM stopped: {type(error).__name__}: {error}')

    def build_sample_scene(self) -> int:
        """Explicit developer/demo action; never used as a generated-scene fallback."""
        from twinpulse_core import fixed_warehouse_bundle

        count = self.build_scene(fixed_warehouse_bundle())
        self.compiler.set_build_metadata(source="sample_fixture", image_count=0)
        return count

    def _configure_robot(self, bundle: "SpecBundle") -> None:
        self._robot = WheeledRobot(
            paths=str(ROBOT_PATH),
            wheel_dof_names=["left_wheel_joint", "right_wheel_joint"],
        )
        self._controller = DifferentialController(
            wheel_radius=bundle.robot.wheel_radius_m,
            wheel_base=bundle.robot.wheel_track_m,
        )

    def focus_scene(self) -> bool:
        """Switch the active interactive viewport to the authored overview camera."""
        try:
            from omni.kit.viewport.utility import get_active_viewport

            viewport = get_active_viewport()
            if viewport is None:
                return False
            previous=str(viewport.camera_path)
            if not previous.startswith('/World/TwinPulse'):
                self._pre_twin_camera_path=previous
            viewport.camera_path = CAMERA_PATH
            return True
        except (ImportError, RuntimeError):
            return False

    def run(self) -> None:
        if self.compiler.bundle is None:
            raise RuntimeError("Build a validated generated scene before Run")
        if self._safety_latch is not None:
            raise RuntimeError(f"Safety latch '{self._safety_latch}' is active; Reset is required before Run")
        self._assert_current_stage()
        if self._physics_subscription is None:
            self._physics_subscription = self._physics_interface.subscribe_physics_on_step_events(
                pre_step=True,
                order=0,
                on_update=self._on_physics_step,
            )
        app_utils.play()
        # Physics/articulation initialization is allowed to settle before the first
        # feedback command; no open-loop impulse is issued here.
        self.compiler.set_drive_velocity(0.0, 0.0)
        self._state = "running"
        self._status("Running toward generated goal")

    def pause(self) -> None:
        if self.site_plan is not None:
            self._assert_current_site_scene()
            self._site_zero()
            app_utils.pause()
            self._state = 'paused'
            self._status('SIM stopped; a new explicit Run is required')
            return
        if self.compiler.site_scene is not None:
            raise RuntimeError("Site scene has no running robot mission to Pause")
        if self.compiler.bundle is not None:
            self._assert_current_stage()
            self.compiler.set_drive_velocity(0.0, 0.0)
        app_utils.pause()
        self._state = "paused"
        self._status("Paused - Reset required before Run" if self._safety_latch else "Paused")

    def reset(self) -> int:
        if self.compiler.bundle is None:
            site_scene = self.compiler.site_scene
            if site_scene is not None:
                self._stop_control()
                self.site_plan = None
                self.site_error = None
                self._robot = self._controller = None
                if self._timeline.is_playing():
                    app_utils.stop()
                self._assert_current_site_scene()
                self.compiler.stage.RemovePrim('/World/TwinPulse/SimBurger')
                from pxr import UsdGeom
                preview = self.compiler.stage.GetPrimAtPath('/World/TwinPulse/Presentation/BurgerPhotoPreview')
                if preview:
                    UsdGeom.Imageable(preview).MakeVisible()
                self._physics_steps = 0
                self._safety_latch = None
                self._state = "ready"
                count = self.compiler.owned_prim_count()
                self._status("Site scene reset complete; Run unavailable")
                return count
            self._status("Nothing to reset - build a generated scene first")
            return 0
        self._stop_control()
        app_utils.stop()
        self._assert_current_stage()
        self._physics_steps = 0
        self._safety_latch = None
        self._state = "ready"
        count = self.compiler.owned_prim_count()
        self._status("Reset complete")
        return count

    def clear_project(self) -> None:
        """Called only after adapter durably checkpoints the owned USD subtree."""
        if self._state=='running':raise ValueError('PROJECT_SWITCH_SIM_RUNNING')
        self._stop_control()
        if self._timeline.is_playing():app_utils.stop()
        # RTX exposure can re-author an active deleted camera and its ancestor
        # prims. Detach viewports BEFORE deleting the checkpointed owned tree;
        # retain the ownership guard rather than claiming the recreated root.
        from omni.kit.viewport.utility import get_active_viewport
        from omni.kit.viewport.window import get_viewport_window_instances
        viewports=[window.viewport_api for window in get_viewport_window_instances()]
        active=get_active_viewport()
        if active is not None and active not in viewports:viewports.append(active)
        previous=getattr(self,'_pre_twin_camera_path','/OmniverseKit_Persp') or '/OmniverseKit_Persp'
        if previous.startswith('/World/TwinPulse'):previous='/OmniverseKit_Persp'
        for viewport in viewports:
            if str(viewport.camera_path).startswith('/World/TwinPulse'):
                viewport.camera_path=previous
                if str(viewport.camera_path).startswith('/World/TwinPulse'):
                    raise RuntimeError('PROJECT_SWITCH_CAMERA_DETACH_FAILED')
        stage=omni.usd.get_context().get_stage()
        if stage and stage.GetPrimAtPath('/World/TwinPulse'):
            root=stage.GetPrimAtPath('/World/TwinPulse')
            if not self.compiler._is_owned_root(root):raise ValueError('PROJECT_SWITCH_FOREIGN_ROOT')
            # Offscreen RTX products may still refer to this camera even after
            # the interactive viewport detaches. Keep the owned presentation
            # identities and physics scene, as the existing hot-build compiler
            # does. This empty shell is NOT an applied scene or a preview.
            from .scene_compiler import PRESENTATION_PATH,PHYSICS_SCENE_PATH,DOME_LIGHT_PATH,SUN_LIGHT_PATH
            for child in list(root.GetChildren()):
                if child.GetPath() in (PRESENTATION_PATH,PHYSICS_SCENE_PATH):continue
                if not stage.RemovePrim(child.GetPath()):raise RuntimeError('PROJECT_SWITCH_CLEAR_FAILED')
            presentation=stage.GetPrimAtPath(PRESENTATION_PATH)
            if presentation:
                for child in list(presentation.GetChildren()):
                    if child.GetPath() not in (CAMERA_PATH,DOME_LIGHT_PATH,SUN_LIGHT_PATH):
                        if not stage.RemovePrim(child.GetPath()):raise RuntimeError('PROJECT_SWITCH_CLEAR_FAILED')
                presentation.SetCustomData({})
            root.SetCustomData({'twinpulseOwner':'TwinPulse','twinpulseSceneId':'empty-project-context'})
        self.compiler.invalidate_stage()
        self.compiler=SceneCompiler()
        self.site_plan=None;self.site_error=None;self._robot=None;self._controller=None
        self._bound_stage_identifier=None;self._safety_latch=None;self._state='idle'
        self._site_waypoint=0;self._site_stall_steps=0;self._site_best_distance=float('inf')

    def shutdown(self) -> None:
        self._stop_control()
        if self._timeline.is_playing():
            app_utils.stop()
        self._state = "shutdown"
        self._shutdown = True
        self._bound_stage_identifier = None
        self.compiler.invalidate_stage()
        self.site_plan = None
        self._robot = None
        self._controller = None
        self._stage_subscription = None
        self._status_callback = None

    def _stop_control(self) -> None:
        self._physics_subscription = None
        if self.site_plan is not None:
            self._site_zero()
        active_stage = omni.usd.get_context().get_stage()
        if (self.compiler.bundle is not None and active_stage is not None
                and self.compiler.stage is active_stage):
            try:
                self.compiler.set_drive_velocity(0.0, 0.0)
            except Exception:
                # A stage-close event can invalidate the USD handle between the
                # identity check and the stop command.  Dropping the subscription
                # remains the fail-safe action; no stale stage may be written.
                pass

    def _assert_current_stage(self) -> None:
        stage = omni.usd.get_context().get_stage()
        bundle = self.compiler.bundle
        if (stage is None or bundle is None or self._bound_stage_identifier != self._stage_key(stage)
                or not self.compiler.matches_stage(bundle, stage=stage)):
            self._invalidate_stage_binding("Stage changed or authored TwinPulse content no longer matches the build")
            raise RuntimeError("Current Isaac stage does not match the validated TwinPulse build; Build again")

    def _assert_current_site_scene(self) -> None:
        stage = omni.usd.get_context().get_stage()
        scene = self.compiler.site_scene
        if (stage is None or scene is None or self._bound_stage_identifier != self._stage_key(stage)
                or not self.compiler.matches_site_scene(scene, stage=stage)):
            self._invalidate_stage_binding("Stage changed or site geometry no longer matches the build")
            raise RuntimeError("Current Isaac stage does not match the reviewed site scene; Build again")

    def _invalidate_stage_binding(self, reason: str) -> None:
        self._stop_control()
        if self._timeline.is_playing():
            app_utils.stop()
        self.compiler.invalidate_stage()
        self.site_plan = None
        self._robot = None
        self._controller = None
        self._bound_stage_identifier = None
        self._state = "stage_invalid"
        self.site_error = reason[:320]
        self._status(reason)

    def _on_stage_event(self, event: object) -> None:
        if self._shutdown or self._bound_stage_identifier is None:
            return
        stage = omni.usd.get_context().get_stage()
        if stage is None or self._stage_key(stage) != self._bound_stage_identifier:
            self._invalidate_stage_binding("Isaac stage changed; TwinPulse commands invalidated")

    @staticmethod
    def _stage_key(stage: object) -> tuple[int, str]:
        return id(stage), stage.GetRootLayer().identifier

    def _on_physics_step(self, step: float, context: object) -> None:
        del step, context
        self._physics_steps += 1
        if self.site_plan is not None:
            self._site_physics_step()
            return
        bundle = self.compiler.bundle
        if bundle is None or self._robot is None or self._controller is None:
            return
        if self._state == "completed":
            self._robot.apply_wheel_actions(self._controller.forward([0.0, 0.0]))
            self.compiler.set_drive_velocity(0.0, 0.0)
            return
        if self._state != "running":
            return
        # Allow PhysX to initialize the freshly compiled articulation before issuing actions.
        if self._physics_steps <= 20:
            return
        from twinpulse_core import straight_route_command

        position, attitude_rad = self.robot_pose_3d()
        roll_rad, pitch_rad, yaw_rad = attitude_rad
        maximum_tilt_rad = math.radians(bundle.robot.max_safe_roll_pitch_deg)
        if abs(roll_rad) > maximum_tilt_rad or abs(pitch_rad) > maximum_tilt_rad:
            self._robot.apply_wheel_actions(self._controller.forward([0.0, 0.0]))
            self.compiler.set_drive_velocity(0.0, 0.0)
            self._safety_latch = "unstable"
            self._state = "unstable"
            self._status(
                f"Safety stop - unstable attitude roll {math.degrees(roll_rad):.1f} deg, "
                f"pitch {math.degrees(pitch_rad):.1f} deg; Reset required"
            )
            return
        start = bundle.task.start.position_m
        goal = bundle.task.goal.position_m
        command = straight_route_command(
            position_xy_m=(position[0], position[1]),
            yaw_rad=yaw_rad,
            start_xy_m=(start[0], start[1]),
            goal_xy_m=(goal[0], goal[1]),
            position_tolerance_m=bundle.task.position_tolerance_m,
            max_linear_speed_mps=bundle.robot.max_linear_speed_mps,
            max_angular_speed_rps=bundle.robot.max_angular_speed_rps,
        )
        if command.completed:
            self._robot.apply_wheel_actions(self._controller.forward([0.0, 0.0]))
            self.compiler.set_drive_velocity(0.0, 0.0)
            self._state = "completed"
            self._status(f"Goal reached - remaining {command.distance_m:.3f} m")
        elif command.off_route:
            self._robot.apply_wheel_actions(self._controller.forward([0.0, 0.0]))
            self.compiler.set_drive_velocity(0.0, 0.0)
            self._safety_latch = "off_route"
            self._state = "off_route"
            self._status(
                f"Safety stop - aisle deviation {command.cross_track_error_m:.3f} m; Reset required"
            )
        else:
            self.compiler.set_drive_velocity(command.linear_mps, command.angular_rps)
            if self._physics_steps % 60 == 0:
                self._status(
                    f"Running - remaining {command.distance_m:.3f} m, "
                    f"aisle error {command.cross_track_error_m:.3f} m"
                )
