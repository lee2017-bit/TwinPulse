"""Validated SceneSpec to USD/PhysX compiler for the M1 fixed scene."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

COMPILER_VERSION = "r2.1"
ASSET_CATALOG_VERSION = "r2.1"
_OWNER = "TwinPulse"


@dataclass(frozen=True, slots=True)
class StageBuildReceipt:
    """Identity proof emitted only after the authored stage passes validation."""

    fingerprint: str
    stage_identifier: str
    compiler_version: str
    asset_catalog_version: str
    prim_count: int


def _number_close(actual: object, expected: float, *, tolerance: float = 1e-6) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def _vector_close(actual: object, expected: tuple[float, ...], *, tolerance: float = 1e-6) -> bool:
    try:
        values = tuple(float(value) for value in actual)
    except (TypeError, ValueError):
        return False
    return len(values) == len(expected) and all(
        _number_close(value, target, tolerance=tolerance) for value, target in zip(values, expected, strict=True)
    )


class SceneCompiler:
    """Compile only TwinPulse-owned prims, preserving all other stage content."""

    def __init__(self) -> None:
        self._stage: Usd.Stage | None = None
        self._bundle: SpecBundle | None = None
        self._build_receipt: StageBuildReceipt | None = None

    @property
    def bundle(self) -> "SpecBundle | None":
        return self._bundle

    @property
    def stage(self) -> Usd.Stage | None:
        return self._stage

    @property
    def build_receipt(self) -> StageBuildReceipt | None:
        return self._build_receipt

    def invalidate_stage(self) -> None:
        """Forget stale Python bindings without mutating any stage."""
        self._stage = None
        self._bundle = None
        self._build_receipt = None

    @staticmethod
    def build_fingerprint(bundle: "SpecBundle") -> str:
        from twinpulse_core import bundle_digest, canonical_sha256

        return canonical_sha256({
            "bundle_sha256": bundle_digest(bundle),
            "compiler_version": COMPILER_VERSION,
            "asset_catalog_version": ASSET_CATALOG_VERSION,
            "robot_profile_id": bundle.robot.id,
            "robot_profile_schema_version": bundle.robot.schema_version,
            "robot_profile_sha256": canonical_sha256(asdict(bundle.robot)),
        })

    def compile(self, bundle: "SpecBundle") -> int:
        from twinpulse_core import validate_bundle

        validate_bundle(bundle)
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage is open")
        self._assert_or_initialize_stage_units(stage)
        if self._stage is not stage:
            self._bundle = None
            self._build_receipt = None
        self._stage = stage

        world = stage.GetPrimAtPath("/World")
        if not world.IsValid():
            UsdGeom.Xform.Define(stage, "/World")
        existing_root = stage.GetPrimAtPath(OWNED_ROOT)
        if existing_root.IsValid():
            if not self._is_owned_root(existing_root):
                raise RuntimeError("Existing /World/TwinPulse content lacks valid TwinPulse ownership metadata")
            if self.matches_stage(bundle, stage=stage):
                self._bundle = bundle
                return self._record_build_receipt(bundle).prim_count
            if stage.GetPrimAtPath(PHYSICS_SCENE_PATH).IsValid():
                return self.replace(bundle)
            if existing_root.GetCustomDataByKey("twinpulseOwner") == _OWNER:
                return self._rebuild_owned_root(bundle)
            raise RuntimeError("Legacy TwinPulse root lacks PhysicsScene; refusing an unverified full-root replacement")

        try:
            root = UsdGeom.Xform.Define(stage, OWNED_ROOT)
            root.GetPrim().SetCustomDataByKey("twinpulseSceneId", bundle.scene.id)
            root.GetPrim().SetCustomDataByKey("twinpulseRobotProfileId", bundle.robot.id)
            root.GetPrim().SetCustomDataByKey("twinpulseOwner", _OWNER)
            UsdGeom.Xform.Define(stage, ENVIRONMENT_PATH)
            physics_scene = UsdPhysics.Scene.Define(stage, PHYSICS_SCENE_PATH)
            physics_scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
            physics_scene.CreateGravityMagnitudeAttr(9.81)

            for item in bundle.scene.objects:
                self._create_scene_object(item)
            self._create_robot(bundle.robot, bundle.task.start.position_m)
            self._bundle = bundle
            self._ensure_presentation(bundle)
            self._write_identity_metadata(bundle)
            return self._record_build_receipt(bundle).prim_count
        except Exception:
            if stage.GetPrimAtPath(OWNED_ROOT).IsValid():
                stage.RemovePrim(OWNED_ROOT)
            self._bundle = None
            self._build_receipt = None
            raise

    @staticmethod
    def _assert_or_initialize_stage_units(stage: Usd.Stage) -> None:
        up = UsdGeom.GetStageUpAxis(stage)
        meters = UsdGeom.GetStageMetersPerUnit(stage)
        root = stage.GetPrimAtPath(OWNED_ROOT)
        has_verified_owned_root = root.IsValid() and SceneCompiler._is_owned_root(root)
        external_physics_scenes = [
            prim.GetPath() for prim in stage.Traverse()
            if prim.IsA(UsdPhysics.Scene)
            and not (has_verified_owned_root and prim.GetPath() == PHYSICS_SCENE_PATH)
        ]
        if external_physics_scenes:
            raise RuntimeError(
                "Stage already contains a PhysicsScene outside the verified TwinPulse root; "
                "open a dedicated stage instead"
            )
        if up == UsdGeom.Tokens.z and math.isclose(meters, 1.0, abs_tol=1e-12):
            return
        outside = [prim.GetPath() for prim in stage.Traverse()
                   if prim.GetPath() != Sdf.Path("/World")
                   and not (has_verified_owned_root and prim.GetPath().HasPrefix(OWNED_ROOT))]
        if outside:
            raise RuntimeError(
                f"Stage units are incompatible ({up}-up, {meters:g} m/unit); "
                "open a dedicated empty Z-up/meter stage instead of changing existing user content"
            )
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    @staticmethod
    def _is_owned_root(root: Usd.Prim) -> bool:
        marker = root.GetCustomDataByKey("twinpulseOwner")
        if marker == _OWNER:
            return bool(root.GetCustomDataByKey("twinpulseSceneId"))
        # Older locally authored roots have no explicit owner marker. Their
        # scene/profile tags and physics path are required before a narrow replace.
        return (marker is None and bool(root.GetCustomDataByKey("twinpulseSceneId"))
                and bool(root.GetCustomDataByKey("twinpulseRobotProfileId"))
                and root.GetStage().GetPrimAtPath(PHYSICS_SCENE_PATH).IsValid())

    def matches_stage(self, bundle: "SpecBundle", *, stage: Usd.Stage | None = None) -> bool:
        active = omni.usd.get_context().get_stage()
        stage = stage or active
        if stage is None or stage is not active:
            return False
        root = stage.GetPrimAtPath(OWNED_ROOT)
        if not root.IsValid() or not self._is_owned_root(root):
            return False
        if (root.GetCustomDataByKey("twinpulseBuildFingerprint") != self.build_fingerprint(bundle)
                or root.GetCustomDataByKey("twinpulseCompilerVersion") != COMPILER_VERSION
                or root.GetCustomDataByKey("twinpulseAssetCatalogVersion") != ASSET_CATALOG_VERSION):
            return False
        if not self._authored_content_matches(bundle, stage):
            return False
        from twinpulse_core import canonical_sha256

        try:
            return root.GetCustomDataByKey("twinpulseStaticDigest") == canonical_sha256(
                self._stage_static_manifest(bundle, stage)
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _authored_content_matches(bundle: "SpecBundle", stage: Usd.Stage) -> bool:
        env = stage.GetPrimAtPath(ENVIRONMENT_PATH)
        robot = stage.GetPrimAtPath(ROBOT_PATH)
        physics = stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
        if not env.IsValid() or not robot.IsValid() or not physics.IsA(UsdPhysics.Scene):
            return False
        if {child.GetName() for child in env.GetChildren()} != {item.id for item in bundle.scene.objects}:
            return False
        if (not _vector_close(physics.GetAttribute("physics:gravityDirection").Get(), (0.0, 0.0, -1.0))
                or not _number_close(physics.GetAttribute("physics:gravityMagnitude").Get(), 9.81)):
            return False
        for item in bundle.scene.objects:
            path = ENVIRONMENT_PATH.AppendChild(item.id)
            obj = stage.GetPrimAtPath(path)
            geom = stage.GetPrimAtPath(path.AppendChild("geometry"))
            if not obj.IsA(UsdGeom.Xform) or not geom.IsValid():
                return False
            if {child.GetName() for child in obj.GetChildren()} != {"geometry"}:
                return False
            if (not _vector_close(obj.GetAttribute("xformOp:translate").Get(), item.transform.position_m)
                    or not _vector_close(obj.GetAttribute("xformOp:rotateXYZ").Get(), item.transform.rotation_rpy_deg)):
                return False
            if geom.HasAPI(UsdPhysics.CollisionAPI) != item.collision or obj.HasAPI(UsdPhysics.RigidBodyAPI) != item.dynamic:
                return False
            if item.dynamic and not _number_close(obj.GetAttribute("physics:mass").Get(), item.mass_kg):
                return False
            if item.kind == "floor" and item.shape.type == "box":
                if not geom.IsA(UsdGeom.Mesh):
                    return False
                dx, dy, dz = item.shape.dimensions_m
                hx, hy, hz = dx / 2.0, dy / 2.0, dz / 2.0
                expected_points = [Gf.Vec3f(*xyz) for xyz in (
                    (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
                    (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz))]
                points = geom.GetAttribute("points").Get()
                if points is None or len(points) != len(expected_points) or any(
                    not _vector_close(actual, tuple(expected))
                    for actual, expected in zip(points, expected_points, strict=True)
                ):
                    return False
            elif item.shape.type == "box":
                if (not geom.IsA(UsdGeom.Cube) or not _number_close(geom.GetAttribute("size").Get(), 1.0)
                        or not _vector_close(geom.GetAttribute("xformOp:scale").Get(), item.shape.dimensions_m)):
                    return False
            elif item.shape.type == "cylinder":
                if (not geom.IsA(UsdGeom.Cylinder)
                        or not _number_close(geom.GetAttribute("radius").Get(), item.shape.dimensions_m[0])
                        or not _number_close(geom.GetAttribute("height").Get(), item.shape.dimensions_m[1])):
                    return False
            else:
                return False
        profile = bundle.robot
        chassis = stage.GetPrimAtPath(ROBOT_PATH.AppendChild("chassis"))
        chassis_geom = stage.GetPrimAtPath(ROBOT_PATH.AppendChild("chassis").AppendChild("geometry"))
        if (not chassis.IsValid() or not chassis_geom.IsA(UsdGeom.Cube)
                or not _vector_close(chassis_geom.GetAttribute("xformOp:scale").Get(), profile.chassis_dimensions_m)
                or not _number_close(chassis.GetAttribute("physics:mass").Get(), profile.mass_kg)):
            return False
        for side in ("left", "right"):
            wheel = stage.GetPrimAtPath(ROBOT_PATH.AppendChild(f"{side}_wheel"))
            joint = stage.GetPrimAtPath(ROBOT_PATH.AppendChild(f"{side}_wheel_joint"))
            if (not wheel.IsA(UsdGeom.Cylinder) or not joint.IsA(UsdPhysics.RevoluteJoint)
                    or not _number_close(wheel.GetAttribute("radius").Get(), profile.wheel_radius_m)
                    or not _number_close(wheel.GetAttribute("height").Get(), profile.wheel_width_m)):
                return False
        for support in profile.support_wheels:
            caster = stage.GetPrimAtPath(ROBOT_PATH.AppendChild(support.id))
            joint = stage.GetPrimAtPath(ROBOT_PATH.AppendChild(f"{support.id}_joint"))
            if (not caster.IsA(UsdGeom.Sphere) or not joint.IsA(UsdPhysics.SphericalJoint)
                    or not _number_close(caster.GetAttribute("radius").Get(), support.radius_m)):
                return False
        goal = stage.GetPrimAtPath(GOAL_PATH)
        return (goal.IsA(UsdGeom.Cylinder)
                and _vector_close(goal.GetAttribute("xformOp:translate").Get(),
                                  (bundle.task.goal.position_m[0], bundle.task.goal.position_m[1], 0.015))
                and all(stage.GetPrimAtPath(path).IsValid()
                        for path in (PRESENTATION_PATH, CAMERA_PATH, DOME_LIGHT_PATH, SUN_LIGHT_PATH, TASK_PATH)))

    @staticmethod
    def _stage_static_manifest(bundle: "SpecBundle", stage: Usd.Stage) -> dict[str, object]:
        """Capture authored values, excluding live robot pose and drive commands."""
        items = []
        for item in sorted(bundle.scene.objects, key=lambda value: value.id):
            path = ENVIRONMENT_PATH.AppendChild(item.id)
            obj = stage.GetPrimAtPath(path)
            geom = stage.GetPrimAtPath(path.AppendChild("geometry"))
            value = {
                "id": item.id, "type": geom.GetTypeName(),
                "position": list(obj.GetAttribute("xformOp:translate").Get()),
                "rotation": list(geom.GetParent().GetAttribute("xformOp:rotateXYZ").Get()),
                "collision": geom.HasAPI(UsdPhysics.CollisionAPI),
                "dynamic": obj.HasAPI(UsdPhysics.RigidBodyAPI),
            }
            if geom.IsA(UsdGeom.Mesh):
                value["points"] = [list(point) for point in geom.GetAttribute("points").Get()]
            elif geom.IsA(UsdGeom.Cube):
                value["scale"] = list(geom.GetAttribute("xformOp:scale").Get())
            elif geom.IsA(UsdGeom.Cylinder):
                value["radius"] = geom.GetAttribute("radius").Get()
                value["height"] = geom.GetAttribute("height").Get()
            items.append(value)
        return {
            "objects": items,
            "robot_profile_id": bundle.robot.id,
            "robot_chassis_scale": list(stage.GetPrimAtPath(ROBOT_PATH.AppendChild("chassis").AppendChild("geometry"))
                                        .GetAttribute("xformOp:scale").Get()),
            "goal_position": list(stage.GetPrimAtPath(GOAL_PATH).GetAttribute("xformOp:translate").Get()),
            "gravity": list(stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
                            .GetAttribute("physics:gravityDirection").Get()),
            "gravity_magnitude": stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
                                 .GetAttribute("physics:gravityMagnitude").Get(),
        }

    def _write_identity_metadata(self, bundle: "SpecBundle") -> None:
        if self._stage is None or not self._authored_content_matches(bundle, self._stage):
            raise RuntimeError("Authored static content does not match the validated bundle")
        from twinpulse_core import canonical_sha256

        root = self._stage.GetPrimAtPath(OWNED_ROOT)
        root.SetCustomDataByKey("twinpulseOwner", _OWNER)
        root.SetCustomDataByKey("twinpulseBuildFingerprint", self.build_fingerprint(bundle))
        root.SetCustomDataByKey("twinpulseCompilerVersion", COMPILER_VERSION)
        root.SetCustomDataByKey("twinpulseAssetCatalogVersion", ASSET_CATALOG_VERSION)
        root.SetCustomDataByKey("twinpulseStaticDigest", canonical_sha256(
            self._stage_static_manifest(bundle, self._stage)))

    def _record_build_receipt(self, bundle: "SpecBundle") -> StageBuildReceipt:
        """Publish the in-memory receipt only after identity metadata is durable."""
        if self._stage is None or not self.matches_stage(bundle, stage=self._stage):
            raise RuntimeError("Cannot issue a build receipt for an unmatched stage")
        receipt = StageBuildReceipt(
            fingerprint=self.build_fingerprint(bundle),
            stage_identifier=self._stage.GetRootLayer().identifier,
            compiler_version=COMPILER_VERSION,
            asset_catalog_version=ASSET_CATALOG_VERSION,
            prim_count=self.owned_prim_count(),
        )
        self._build_receipt = receipt
        return receipt

    def ensure_presentation(self) -> int:
        """Create or refresh the TwinPulse-owned camera, lighting, and goal marker."""
        if self._stage is None or self._bundle is None:
            raise RuntimeError("Scene has not been compiled")
        self._ensure_presentation(self._bundle)
        return self.owned_prim_count()

    def clear_owned(self) -> None:
        """Remove only the Extension-owned root and forget the compiled bundle."""
        stage = omni.usd.get_context().get_stage()
        if stage is not None:
            root = stage.GetPrimAtPath(OWNED_ROOT)
            if root.IsValid():
                if not self._is_owned_root(root):
                    raise RuntimeError("Refusing to clear an unowned /World/TwinPulse root")
                stage.RemovePrim(OWNED_ROOT)
        self._stage = stage
        self._bundle = None
        self._build_receipt = None

    def replace(self, bundle: "SpecBundle") -> int:
        """Replace generated content atomically while keeping the live PhysicsScene stable."""
        from twinpulse_core import validate_bundle

        validate_bundle(bundle)
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage is open")
        self._assert_or_initialize_stage_units(stage)
        if self._stage is not stage:
            self._bundle = None
            self._build_receipt = None
        root = stage.GetPrimAtPath(OWNED_ROOT)
        physics_scene = stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
        if not root.IsValid() or not physics_scene.IsValid():
            raise RuntimeError("TwinPulse scene is not available for replacement")
        if not self._is_owned_root(root):
            raise RuntimeError("Refusing to replace a TwinPulse root without ownership metadata")

        self._stage = stage
        previous_bundle = self._bundle
        previous_receipt = self._build_receipt
        previous_custom_data = root.GetCustomData()
        gravity_direction = physics_scene.GetAttribute("physics:gravityDirection")
        gravity_magnitude = physics_scene.GetAttribute("physics:gravityMagnitude")
        previous_gravity_direction = gravity_direction.Get()
        previous_gravity_magnitude = gravity_magnitude.Get()
        edit_layer = stage.GetEditTarget().GetLayer()
        backup_layer = Sdf.Layer.CreateAnonymous("twinpulse-replace-backup.usda")
        Sdf.CreatePrimInLayer(backup_layer, "/World")
        Sdf.CreatePrimInLayer(backup_layer, OWNED_ROOT)
        mutable_paths = (ENVIRONMENT_PATH, ROBOT_PATH, PRESENTATION_PATH, TASK_PATH)
        for path in mutable_paths:
            if stage.GetPrimAtPath(path).IsValid():
                if edit_layer.GetPrimAtPath(path) is None:
                    raise RuntimeError(f"Cannot safely replace composed TwinPulse path {path} outside the current edit layer")
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
            gravity_direction.Set(Gf.Vec3f(0.0, 0.0, -1.0))
            gravity_magnitude.Set(9.81)
            self._write_identity_metadata(bundle)
            return self._record_build_receipt(bundle).prim_count
        except Exception as replacement_error:
            try:
                for path in mutable_paths:
                    if stage.GetPrimAtPath(path).IsValid():
                        stage.RemovePrim(path)
                    if backup_layer.GetPrimAtPath(path) is not None:
                        if not Sdf.CopySpec(backup_layer, path, edit_layer, path):
                            raise RuntimeError(f"Rollback failed for {path}")
                restored = stage.GetPrimAtPath(OWNED_ROOT)
                if not restored.IsValid():
                    raise RuntimeError("Rollback lost the TwinPulse root")
                restored.SetCustomData(previous_custom_data)
                gravity_direction.Set(previous_gravity_direction)
                gravity_magnitude.Set(previous_gravity_magnitude)
                self._bundle = previous_bundle
                self._build_receipt = previous_receipt
            except Exception as rollback_error:
                self.invalidate_stage()
                raise RuntimeError(f"Scene replacement failed and rollback FAILED: {rollback_error}") from replacement_error
            raise RuntimeError("Scene replacement failed; previous geometry and identity restored") from replacement_error

    def _rebuild_owned_root(self, bundle: "SpecBundle") -> int:
        """Full-root recovery only for roots bearing the new explicit owner marker."""
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage is open")
        root = stage.GetPrimAtPath(OWNED_ROOT)
        if root.GetCustomDataByKey("twinpulseOwner") != _OWNER:
            raise RuntimeError("Full-root recovery requires explicit TwinPulse ownership")
        edit_layer = stage.GetEditTarget().GetLayer()
        if edit_layer.GetPrimAtPath(OWNED_ROOT) is None:
            raise RuntimeError("Cannot safely rebuild composed TwinPulse content outside the current edit layer")
        backup = Sdf.Layer.CreateAnonymous("twinpulse-root-rebuild-backup.usda")
        Sdf.CreatePrimInLayer(backup, "/World")
        if not Sdf.CopySpec(edit_layer, OWNED_ROOT, backup, OWNED_ROOT):
            raise RuntimeError("Unable to snapshot TwinPulse root before rebuilding")
        previous_bundle = self._bundle
        previous_receipt = self._build_receipt
        stage.RemovePrim(OWNED_ROOT)
        try:
            return self.compile(bundle)
        except Exception as replacement_error:
            try:
                if stage.GetPrimAtPath(OWNED_ROOT).IsValid():
                    stage.RemovePrim(OWNED_ROOT)
                if not Sdf.CopySpec(backup, OWNED_ROOT, edit_layer, OWNED_ROOT):
                    raise RuntimeError("Full-root rollback copy failed")
                self._stage = stage
                self._bundle = previous_bundle
                self._build_receipt = previous_receipt
            except Exception as rollback_error:
                self.invalidate_stage()
                raise RuntimeError(f"Scene rebuild failed and rollback FAILED: {rollback_error}") from replacement_error
            raise RuntimeError("Scene rebuild failed; previous root restored") from replacement_error

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
