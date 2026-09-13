"""Extension runtime state and lifecycle-safe physics controls."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

import isaacsim.core.experimental.utils.app as app_utils
import omni.physics.core
import omni.timeline
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.robot.experimental.wheeled_robots.controllers import DifferentialController
from isaacsim.robot.experimental.wheeled_robots.robots import WheeledRobot

from .scene_compiler import CAMERA_PATH, ROBOT_PATH, SceneCompiler

if TYPE_CHECKING:
    from twinpulse_core import SpecBundle


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

    @property
    def state(self) -> str:
        return self._state

    @property
    def has_active_subscription(self) -> bool:
        return self._physics_subscription is not None

    @property
    def shutdown_complete(self) -> bool:
        return self._shutdown and self._physics_subscription is None

    @property
    def physics_steps(self) -> int:
        return self._physics_steps

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
        if self.compiler.bundle == target:
            count = self.compiler.ensure_presentation()
            self.focus_scene()
            self._status(f"Ready - {count} TwinPulse prims")
            return count
        self._stop_control()
        if self._timeline.is_playing():
            app_utils.stop()
        previous = self.compiler.bundle
        count = self.compiler.compile(target) if previous is None else self.compiler.replace(target)
        self._configure_robot(target)
        SimulationManager.setup_simulation(dt=1.0 / 60.0, device="cpu")
        physics_scenes = SimulationManager.get_physics_scenes()
        if physics_scenes:
            physics_scenes[0].set_enabled_gpu_dynamics(False)
        self._state = "ready"
        self._physics_steps = 0
        self.focus_scene()
        self._status(f"Ready - {count} TwinPulse prims")
        return count

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
            viewport.camera_path = CAMERA_PATH
            return True
        except (ImportError, RuntimeError):
            return False

    def run(self) -> None:
        if self.compiler.bundle is None:
            raise RuntimeError("Build a validated generated scene before Run")
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
        if self.compiler.bundle is not None:
            self.compiler.set_drive_velocity(0.0, 0.0)
        app_utils.pause()
        self._state = "paused"
        self._status("Paused")

    def reset(self) -> int:
        if self.compiler.bundle is None:
            self._status("Nothing to reset - build a generated scene first")
            return 0
        self._stop_control()
        app_utils.stop()
        self._physics_steps = 0
        self._state = "ready"
        count = self.compiler.owned_prim_count()
        self._status("Reset complete")
        return count

    def shutdown(self) -> None:
        self._stop_control()
        if self._timeline.is_playing():
            app_utils.stop()
        self._state = "shutdown"
        self._shutdown = True
        self._status_callback = None

    def _stop_control(self) -> None:
        if self.compiler.bundle is not None:
            try:
                self.compiler.set_drive_velocity(0.0, 0.0)
            except RuntimeError:
                pass
        self._physics_subscription = None

    def _on_physics_step(self, step: float, context: object) -> None:
        del step, context
        self._physics_steps += 1
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
