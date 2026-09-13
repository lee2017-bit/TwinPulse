"""Validated SceneSpec to USD/PhysX compiler for the M1 fixed scene."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics

if TYPE_CHECKING:
    from twinpulse_core import RobotProfile, SceneObject, SpecBundle


OWNED_ROOT = Sdf.Path("/World/TwinPulse")
ROBOT_PATH = Sdf.Path("/World/TwinPulse/Robot")
ENVIRONMENT_PATH = Sdf.Path("/World/TwinPulse/Environment")
PHYSICS_SCENE_PATH = Sdf.Path("/World/TwinPulse/PhysicsScene")
PRESENTATION_PATH = Sdf.Path("/World/TwinPulse/Presentation")
CAMERA_PATH = Sdf.Path("/World/TwinPulse/Presentation/Camera")
DOME_LIGHT_PATH = Sdf.Path("/World/TwinPulse/Presentation/DomeLight")
SUN_LIGHT_PATH = Sdf.Path("/World/TwinPulse/Presentation/SunLight")
TASK_PATH = Sdf.Path("/World/TwinPulse/Task")
GOAL_PATH = Sdf.Path("/World/TwinPulse/Task/Goal")

_COLORS = {
    "floor": Gf.Vec3f(0.18, 0.20, 0.23),
    "wall": Gf.Vec3f(0.52, 0.56, 0.62),
    "rack": Gf.Vec3f(0.18, 0.36, 0.64),
    "box": Gf.Vec3f(0.76, 0.48, 0.16),
    "equipment": Gf.Vec3f(0.30, 0.46, 0.42),
}


class SceneCompiler:
    """Compile only TwinPulse-owned prims, preserving all other stage content."""

    def __init__(self) -> None:
        self._stage: Usd.Stage | None = None
        self._bundle: SpecBundle | None = None

    @property
    def bundle(self) -> "SpecBundle | None":
        return self._bundle

    def compile(self, bundle: "SpecBundle") -> int:
        from twinpulse_core import validate_bundle

        validate_bundle(bundle)
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage is open")
        self._stage = stage
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)

        world = stage.GetPrimAtPath("/World")
        if not world.IsValid():
            UsdGeom.Xform.Define(stage, "/World")
        existing_root = stage.GetPrimAtPath(OWNED_ROOT)
        if existing_root.IsValid():
            same_fixture = (
                existing_root.GetCustomDataByKey("twinpulseSceneId") == bundle.scene.id
                and existing_root.GetCustomDataByKey("twinpulseRobotProfileId") == bundle.robot.id
            )
            required_prims = all(
                stage.GetPrimAtPath(path).IsValid()
                for path in (ENVIRONMENT_PATH, PHYSICS_SCENE_PATH, ROBOT_PATH)
            )
            if same_fixture and required_prims:
                # Safely upgrade an M1 scene created before presentation prims
                # were added. Only TwinPulse-owned paths are touched.
                self._bundle = bundle
                self._ensure_presentation(bundle)
                return self.owned_prim_count()
            if existing_root.GetCustomDataByKey("twinpulseSceneId") and required_prims:
                # The root is explicitly TwinPulse-owned. This path is required
                # after an Extension reload, when the USD stage survives but the
                # Python compiler instance no longer remembers the prior bundle.
                return self.replace(bundle)
            raise RuntimeError("Existing /World/TwinPulse content lacks valid TwinPulse ownership metadata")

        try:
            root = UsdGeom.Xform.Define(stage, OWNED_ROOT)
            root.GetPrim().SetCustomDataByKey("twinpulseSceneId", bundle.scene.id)
            root.GetPrim().SetCustomDataByKey("twinpulseRobotProfileId", bundle.robot.id)
            UsdGeom.Xform.Define(stage, ENVIRONMENT_PATH)
            physics_scene = UsdPhysics.Scene.Define(stage, PHYSICS_SCENE_PATH)
            physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
            physics_scene.CreateGravityMagnitudeAttr(9.81)

            for item in bundle.scene.objects:
                self._create_scene_object(item)
            self._create_robot(bundle.robot, bundle.task.start.position_m)
            self._bundle = bundle
            self._ensure_presentation(bundle)
            return self.owned_prim_count()
        except Exception:
            if stage.GetPrimAtPath(OWNED_ROOT).IsValid():
                stage.RemovePrim(OWNED_ROOT)
            self._bundle = None
            raise

    def ensure_presentation(self) -> int:
        """Create or refresh the TwinPulse-owned camera, lighting, and goal marker."""
        if self._stage is None or self._bundle is None:
            raise RuntimeError("Scene has not been compiled")
        self._ensure_presentation(self._bundle)
        return self.owned_prim_count()

    def clear_owned(self) -> None:
        """Remove only the Extension-owned root and forget the compiled bundle."""
        stage = self._stage or omni.usd.get_context().get_stage()
        if stage is not None and stage.GetPrimAtPath(OWNED_ROOT).IsValid():
            stage.RemovePrim(OWNED_ROOT)
        self._stage = stage
        self._bundle = None

    def replace(self, bundle: "SpecBundle") -> int:
        """Replace generated content atomically while keeping the live PhysicsScene stable."""
        from twinpulse_core import validate_bundle

        validate_bundle(bundle)
        stage = self._stage or omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage is open")
        root = stage.GetPrimAtPath(OWNED_ROOT)
        physics_scene = stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
        if not root.IsValid() or not physics_scene.IsValid():
            raise RuntimeError("TwinPulse scene is not available for replacement")
        if not root.GetCustomDataByKey("twinpulseSceneId"):
            raise RuntimeError("Refusing to replace a TwinPulse root without ownership metadata")

        self._stage = stage
        previous_bundle = self._bundle
        previous_scene_id = root.GetCustomDataByKey("twinpulseSceneId")
        previous_profile_id = root.GetCustomDataByKey("twinpulseRobotProfileId")
        edit_layer = stage.GetEditTarget().GetLayer()
        backup_layer = Sdf.Layer.CreateAnonymous("twinpulse-replace-backup.usda")
        Sdf.CreatePrimInLayer(backup_layer, "/World")
        Sdf.CreatePrimInLayer(backup_layer, OWNED_ROOT)
        mutable_paths = (ENVIRONMENT_PATH, ROBOT_PATH, PRESENTATION_PATH, TASK_PATH)
        for path in mutable_paths:
            if stage.GetPrimAtPath(path).IsValid():
                Sdf.CopySpec(edit_layer, path, backup_layer, path)
                if backup_layer.GetPrimAtPath(path) is None:
                    raise RuntimeError(f"Unable to snapshot TwinPulse-owned scene path {path}")

        try:
            for path in mutable_paths:
                if stage.GetPrimAtPath(path).IsValid():
                    stage.RemovePrim(path)
            root.SetCustomDataByKey("twinpulseSceneId", bundle.scene.id)
            root.SetCustomDataByKey("twinpulseRobotProfileId", bundle.robot.id)
            UsdGeom.Xform.Define(stage, ENVIRONMENT_PATH)
            for item in bundle.scene.objects:
                self._create_scene_object(item)
            self._create_robot(bundle.robot, bundle.task.start.position_m)
            self._bundle = bundle
            self._ensure_presentation(bundle)
            return self.owned_prim_count()
        except Exception:
            for path in mutable_paths:
                if stage.GetPrimAtPath(path).IsValid():
                    stage.RemovePrim(path)
                if backup_layer.GetPrimAtPath(path) is not None:
                    Sdf.CopySpec(backup_layer, path, edit_layer, path)
            root = stage.GetPrimAtPath(OWNED_ROOT)
            if root.IsValid():
                root.SetCustomDataByKey("twinpulseSceneId", previous_scene_id)
                root.SetCustomDataByKey("twinpulseRobotProfileId", previous_profile_id)
            self._bundle = previous_bundle
            raise

    def _ensure_presentation(self, bundle: "SpecBundle") -> None:
        assert self._stage is not None
        UsdGeom.Xform.Define(self._stage, PRESENTATION_PATH)

        camera = UsdGeom.Camera.Define(self._stage, CAMERA_PATH)
        camera.CreateFocalLengthAttr(20.0)
        camera.CreateHorizontalApertureAttr(24.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 1000.0))
        camera_xform = UsdGeom.Xformable(camera)
        camera_xform.ClearXformOpOrder()
        camera_xform.AddTransformOp().Set(
            Gf.Matrix4d(1.0)
            .SetLookAt(
                Gf.Vec3d(8.5, -9.5, 7.0),
                Gf.Vec3d(0.0, 0.0, 0.35),
                Gf.Vec3d(0.0, 0.0, 1.0),
            )
            .GetInverse()
        )

        dome = UsdLux.DomeLight.Define(self._stage, DOME_LIGHT_PATH)
        dome.CreateIntensityAttr(650.0)
        dome.CreateColorAttr(Gf.Vec3f(0.78, 0.84, 1.0))

        sun = UsdLux.DistantLight.Define(self._stage, SUN_LIGHT_PATH)
        sun.CreateIntensityAttr(2500.0)
        sun.CreateAngleAttr(1.0)
        sun_xform = UsdGeom.Xformable(sun)
        sun_xform.ClearXformOpOrder()
        sun_xform.AddRotateXYZOp().Set(Gf.Vec3f(45.0, -30.0, 25.0))

        UsdGeom.Xform.Define(self._stage, TASK_PATH)
        goal = UsdGeom.Cylinder.Define(self._stage, GOAL_PATH)
        goal.CreateAxisAttr("Z")
        goal.CreateRadiusAttr(0.16)
        goal.CreateHeightAttr(0.025)
        goal.CreateDisplayColorAttr([Gf.Vec3f(0.12, 0.88, 0.28)])
        goal_xform = UsdGeom.Xformable(goal)
        goal_xform.ClearXformOpOrder()
        goal_xform.AddTranslateOp().Set(
            Gf.Vec3d(
                bundle.task.goal.position_m[0],
                bundle.task.goal.position_m[1],
                0.015,
            )
        )

    def _create_scene_object(self, item: "SceneObject") -> None:
        assert self._stage is not None
        object_path = ENVIRONMENT_PATH.AppendChild(item.id)
        root = UsdGeom.Xform.Define(self._stage, object_path)
        root.AddTranslateOp().Set(Gf.Vec3d(*item.transform.position_m))
        root.AddRotateXYZOp().Set(Gf.Vec3f(*item.transform.rotation_rpy_deg))

        geometry_path = object_path.AppendChild("geometry")
        if item.kind == "floor" and item.shape.type == "box":
            # Large, very thin floors represented as non-uniformly scaled cubes
            # produced asymmetric wheel contact in PhysX. Author the actual box
            # vertices instead so collision geometry has an identity scale.
            dx, dy, dz = item.shape.dimensions_m
            hx, hy, hz = dx / 2.0, dy / 2.0, dz / 2.0
            geometry = UsdGeom.Mesh.Define(self._stage, geometry_path)
            geometry.CreatePointsAttr(
                [
                    Gf.Vec3f(-hx, -hy, -hz),
                    Gf.Vec3f(hx, -hy, -hz),
                    Gf.Vec3f(hx, hy, -hz),
                    Gf.Vec3f(-hx, hy, -hz),
                    Gf.Vec3f(-hx, -hy, hz),
                    Gf.Vec3f(hx, -hy, hz),
                    Gf.Vec3f(hx, hy, hz),
                    Gf.Vec3f(-hx, hy, hz),
                ]
            )
            geometry.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
            geometry.CreateFaceVertexIndicesAttr(
                [0, 3, 2, 1, 4, 5, 6, 7, 0, 1, 5, 4, 3, 7, 6, 2, 0, 4, 7, 3, 1, 2, 6, 5]
            )
            geometry.CreateSubdivisionSchemeAttr("none")
            geometry.CreateExtentAttr([Gf.Vec3f(-hx, -hy, -hz), Gf.Vec3f(hx, hy, hz)])
        elif item.shape.type == "box":
            geometry = UsdGeom.Cube.Define(self._stage, geometry_path)
            geometry.CreateSizeAttr(1.0)
            geometry.AddScaleOp().Set(Gf.Vec3f(*item.shape.dimensions_m))
        elif item.shape.type == "cylinder":
            radius, height = item.shape.dimensions_m
            geometry = UsdGeom.Cylinder.Define(self._stage, geometry_path)
            geometry.CreateAxisAttr("Z")
            geometry.CreateRadiusAttr(radius)
            geometry.CreateHeightAttr(height)
        else:
            raise ValueError(f"Unsupported validated shape: {item.shape.type}")
        geometry.CreateDisplayColorAttr([_COLORS[item.kind]])
        if item.collision:
            UsdPhysics.CollisionAPI.Apply(geometry.GetPrim())
        if item.dynamic:
            UsdPhysics.RigidBodyAPI.Apply(root.GetPrim())
            UsdPhysics.MassAPI.Apply(root.GetPrim()).CreateMassAttr(item.mass_kg)

    def _create_robot(self, profile: "RobotProfile", start_position: tuple[float, float, float]) -> None:
        assert self._stage is not None
        robot_root = UsdGeom.Xform.Define(self._stage, ROBOT_PATH)
        robot_root.AddTranslateOp().Set(Gf.Vec3d(*start_position))
        UsdPhysics.ArticulationRootAPI.Apply(robot_root.GetPrim())

        chassis_height = profile.chassis_dimensions_m[2]
        chassis_path = ROBOT_PATH.AppendChild("chassis")
        chassis = UsdGeom.Xform.Define(self._stage, chassis_path)
        chassis.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, profile.wheel_radius_m + chassis_height / 2.0))
        UsdPhysics.RigidBodyAPI.Apply(chassis.GetPrim())
        chassis_mass = UsdPhysics.MassAPI.Apply(chassis.GetPrim())
        chassis_mass.CreateMassAttr(profile.mass_kg)
        chassis_mass.CreateCenterOfMassAttr(Gf.Vec3f(*profile.center_of_mass_m))
        chassis_mass.CreateDiagonalInertiaAttr(Gf.Vec3f(*profile.diagonal_inertia_kg_m2))
        chassis_geometry = UsdGeom.Cube.Define(self._stage, chassis_path.AppendChild("geometry"))
        chassis_geometry.CreateSizeAttr(1.0)
        chassis_geometry.AddScaleOp().Set(Gf.Vec3f(*profile.chassis_dimensions_m))
        chassis_geometry.CreateDisplayColorAttr([Gf.Vec3f(0.08, 0.62, 0.76)])
        UsdPhysics.CollisionAPI.Apply(chassis_geometry.GetPrim())

        for side, y in (("left", profile.wheel_track_m / 2.0), ("right", -profile.wheel_track_m / 2.0)):
            wheel_path = ROBOT_PATH.AppendChild(f"{side}_wheel")
            wheel = UsdGeom.Cylinder.Define(self._stage, wheel_path)
            wheel.CreateAxisAttr("Y")
            wheel.CreateRadiusAttr(profile.wheel_radius_m)
            wheel.CreateHeightAttr(profile.wheel_width_m)
            wheel.AddTranslateOp().Set(Gf.Vec3d(0.0, y, profile.wheel_radius_m))
            wheel.CreateDisplayColorAttr([Gf.Vec3f(0.04, 0.04, 0.04)])
            UsdPhysics.CollisionAPI.Apply(wheel.GetPrim())
            UsdPhysics.RigidBodyAPI.Apply(wheel.GetPrim())
            UsdPhysics.MassAPI.Apply(wheel.GetPrim()).CreateMassAttr(1.0)

            joint_path = ROBOT_PATH.AppendChild(f"{side}_wheel_joint")
            joint = UsdPhysics.RevoluteJoint.Define(self._stage, joint_path)
            joint.CreateAxisAttr("Y")
            joint.CreateBody0Rel().SetTargets([chassis_path])
            joint.CreateBody1Rel().SetTargets([wheel_path])
            joint.CreateLocalPos0Attr().Set(Gf.Vec3f(0.0, y, -chassis_height / 2.0))
            joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
            drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
            drive.CreateTypeAttr("force")
            drive.CreateStiffnessAttr(0.0)
            drive.CreateDampingAttr(100.0)
            drive.CreateMaxForceAttr(1000.0)
            drive.CreateTargetVelocityAttr(0.0)

        for support in profile.support_wheels:
            support_path = ROBOT_PATH.AppendChild(support.id)
            caster = UsdGeom.Sphere.Define(self._stage, support_path)
            caster.CreateRadiusAttr(support.radius_m)
            caster.AddTranslateOp().Set(
                Gf.Vec3d(support.position_xy_m[0], support.position_xy_m[1], support.radius_m)
            )
            caster.CreateDisplayColorAttr([Gf.Vec3f(0.10, 0.10, 0.12)])
            UsdPhysics.CollisionAPI.Apply(caster.GetPrim())
            UsdPhysics.RigidBodyAPI.Apply(caster.GetPrim())
            UsdPhysics.MassAPI.Apply(caster.GetPrim()).CreateMassAttr(support.mass_kg)

            joint_path = ROBOT_PATH.AppendChild(f"{support.id}_joint")
            joint = UsdPhysics.SphericalJoint.Define(self._stage, joint_path)
            joint.CreateBody0Rel().SetTargets([chassis_path])
            joint.CreateBody1Rel().SetTargets([support_path])
            joint.CreateLocalPos0Attr().Set(
                Gf.Vec3f(
                    support.position_xy_m[0],
                    support.position_xy_m[1],
                    -chassis_height / 2.0 - (profile.wheel_radius_m - support.radius_m),
                )
            )
            joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))

    def set_drive_velocity(self, linear_mps: float, angular_rps: float) -> None:
        if self._stage is None or self._bundle is None:
            raise RuntimeError("Scene has not been compiled")
        profile = self._bundle.robot
        linear = max(-profile.max_linear_speed_mps, min(profile.max_linear_speed_mps, linear_mps))
        angular = max(-profile.max_angular_speed_rps, min(profile.max_angular_speed_rps, angular_rps))
        left_rad_s = (linear - angular * profile.wheel_track_m / 2.0) / profile.wheel_radius_m
        right_rad_s = (linear + angular * profile.wheel_track_m / 2.0) / profile.wheel_radius_m
        for side, velocity in (("left", left_rad_s), ("right", right_rad_s)):
            joint = self._stage.GetPrimAtPath(ROBOT_PATH.AppendChild(f"{side}_wheel_joint"))
            attribute = joint.GetAttribute("drive:angular:physics:targetVelocity")
            if not attribute.IsValid():
                raise RuntimeError(f"Wheel drive is missing for {side}")
            attribute.Set(math.degrees(velocity))

    def robot_position(self) -> tuple[float, float, float]:
        if self._stage is None:
            raise RuntimeError("Scene has not been compiled")
        robot = self._stage.GetPrimAtPath(ROBOT_PATH)
        if not robot.IsValid():
            raise RuntimeError("TwinPulse robot prim is missing")
        matrix = UsdGeom.Xformable(robot).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        value = matrix.ExtractTranslation()
        return float(value[0]), float(value[1]), float(value[2])

    def owned_prim_count(self) -> int:
        if self._stage is None:
            return 0
        root = self._stage.GetPrimAtPath(OWNED_ROOT)
        if not root.IsValid():
            return 0
        return 1 + sum(1 for _ in Usd.PrimRange(root) if _.GetPath() != OWNED_ROOT)

    def set_build_metadata(
        self,
        *,
        source: str,
        image_count: int,
        request_id: str = "",
        plan_sha256: str = "",
    ) -> None:
        if self._stage is None:
            raise RuntimeError("Scene has not been compiled")
        root = self._stage.GetPrimAtPath(OWNED_ROOT)
        if not root.IsValid() or not root.GetCustomDataByKey("twinpulseSceneId"):
            raise RuntimeError("TwinPulse-owned root is unavailable")
        root.SetCustomDataByKey("twinpulseBuildSource", source)
        root.SetCustomDataByKey("twinpulseImageCount", int(image_count))
        root.SetCustomDataByKey("twinpulseRequestId", request_id)
        root.SetCustomDataByKey("twinpulsePlanSha256", plan_sha256)
