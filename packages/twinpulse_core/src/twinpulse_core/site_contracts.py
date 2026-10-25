# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2a pure contracts. No App, Isaac, ROS, provider, or runtime migration is wired here.

Version 2 is additive: the version-1 SpecBundle remains on its existing path.
Only a reviewed, versioned H2b adapter may promote these records to execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Mapping

from .engine_contracts import CommandReceipt, SimulationSnapshot
from .models import RobotProfile, SceneObject, SceneSpec, SpecBundle, TaskSpec, Transform
from .revisions import bundle_digest, canonical_sha256
from .validation import (SpecValidationError, validate_bundle, validate_current_controller_route,
                         validate_robot_profile, validate_scene_geometry)


SITE_SCHEMA_VERSION = "2.0"
STRAIGHT_CONTROLLER_CAPABILITY = "straight_positive_x_v1"
DEMO_SAFETY_POLICY_ID = "demo_safety_v1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _exact(value: Mapping[str, Any], fields: set[str], name: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{name} shape is unsupported")


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{name} is invalid")


def _digest(value: str | None, name: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 digest")


def _pose(pose: Transform, name: str) -> None:
    if not all(math.isfinite(value) and abs(value) <= 100 for value in pose.position_m) or not all(
        math.isfinite(value) and abs(value) <= 360 for value in pose.rotation_rpy_deg
    ):
        raise ValueError(f"{name} contains an invalid coordinate")


@dataclass(frozen=True, slots=True)
class ObservationBinding:
    """One observed entity has one role; detailed provenance is H3a work."""

    observation_id: str
    scene_object_id: str
    role: str = "static_obstacle"

    def __post_init__(self) -> None:
        _id(self.observation_id, "observation id")
        _id(self.scene_object_id, "scene object id")
        if self.role not in {"static_obstacle", "scene_object"}:
            raise ValueError("observation role is unsupported")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObservationBinding":
        _exact(value, {"observation_id", "scene_object_id", "role"}, "observation binding")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class SceneRevision:
    id: str
    objects: tuple[SceneObject, ...]
    source: str
    source_ref: str | None = None
    parent_revision: str | None = None
    observation_bindings: tuple[ObservationBinding, ...] = ()
    frame_id: str = "world"
    schema_version: str = SITE_SCHEMA_VERSION
    library_assets: tuple = ()
    environment: dict | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SITE_SCHEMA_VERSION or self.frame_id != "world":
            raise ValueError("scene version or frame is unsupported")
        if self.source not in {"photo", "drawing", "scan", "manual", "legacy"}:
            raise ValueError("scene source is unsupported")
        _digest(self.source_ref, "source_ref", optional=True)
        _digest(self.parent_revision, "parent_revision", optional=True)
        if self.source != "manual" and self.source_ref is None:
            raise ValueError("non-manual scenes require source provenance")
        if not isinstance(self.objects, tuple) or not isinstance(self.observation_bindings, tuple):
            raise ValueError("scene objects and bindings must be immutable tuples")
        from .validation import ValidationLimits
        from .library_assets import MeshAsset
        if not isinstance(self.library_assets,tuple) or any(not isinstance(a,MeshAsset) for a in self.library_assets):
            raise ValueError('LIBRARY_SCENE_ASSETS_INVALID')
        assets={a.asset_ref:MeshAsset.from_dict(a.to_dict()) for a in self.library_assets}
        if len(assets)!=len(self.library_assets):raise ValueError('LIBRARY_SCENE_ASSET_DUPLICATE')
        if set(assets)!={o.asset_id for o in self.objects if o.asset_id is not None}:
            raise ValueError('LIBRARY_SCENE_ASSET_COVERAGE_INVALID')
        if any(o.asset_id is not None and (o.shape.type!='box' or o.dynamic or not o.collision or
                tuple(o.shape.dimensions_m)!=assets[o.asset_id].dimensions_m) for o in self.objects):
            raise ValueError('LIBRARY_SCENE_COLLIDER_MISMATCH')
        validate_scene_geometry(self.id, self.objects, ValidationLimits(max_objects=None,allowed_asset_ids=frozenset(assets)))
        if self.environment is not None:
            from .environment_source import checked_environment, environment_objects
            environment=checked_environment(self.environment)
            if self.library_assets or self.objects!=environment_objects(environment):
                raise ValueError('ENVIRONMENT_SCENE_METADATA_MISMATCH')
        object_ids = {item.id for item in self.objects}
        binding_pairs = [(item.observation_id, item.scene_object_id) for item in self.observation_bindings]
        if len(binding_pairs) != len(set(binding_pairs)) or any(
            item.scene_object_id not in object_ids for item in self.observation_bindings
        ):
            raise ValueError("observation binding pairs must be unique and reference scene objects")

    @property
    def revision(self) -> str:
        return canonical_sha256(self._body())

    def _body(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id,
                "objects": [asdict(item) for item in self.objects], "source": self.source,
                "source_ref": self.source_ref, "parent_revision": self.parent_revision,
                "observation_bindings": [asdict(item) for item in self.observation_bindings],
                "frame_id": self.frame_id,
                **({'library_assets':[a.to_dict() for a in self.library_assets]} if self.library_assets else {}),
                **({'environment':self.environment} if self.environment is not None else {})}

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "revision": self.revision}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SceneRevision":
        _exact(value, {"schema_version", "id", "objects", "source", "source_ref",
                       "parent_revision", "observation_bindings", "frame_id", "revision"} |
                       ({'library_assets'} if 'library_assets' in value else set()) |
                       ({'environment'} if 'environment' in value else set()), "scene revision")
        from .library_assets import MeshAsset
        if 'library_assets' in value and not isinstance(value['library_assets'],list):raise ValueError('LIBRARY_SCENE_ASSETS_INVALID')
        if not isinstance(value["objects"], list):
            raise ValueError("scene objects must be an array")
        if not isinstance(value["observation_bindings"], list):
            raise ValueError("observation bindings must be an array")
        for item in value["objects"]:
            _exact(item, {"id", "kind", "transform", "shape", "collision", "dynamic", "mass_kg", "asset_id"}, "scene object")
            _exact(item["transform"], {"position_m", "rotation_rpy_deg"}, "object transform")
            _exact(item["shape"], {"type", "dimensions_m"}, "object shape")
        scene = cls(id=value["id"], objects=tuple(SceneObject.from_dict(item) for item in value["objects"]),
                    source=value["source"], source_ref=value["source_ref"],
                    parent_revision=value["parent_revision"], frame_id=value["frame_id"],
                    observation_bindings=tuple(ObservationBinding.from_dict(item) for item in value["observation_bindings"]),
                    schema_version=value["schema_version"],library_assets=tuple(MeshAsset.from_dict(a) for a in value.get('library_assets',[])),
                    environment=value.get('environment'))
        if value["revision"] != scene.revision:
            raise ValueError("scene revision digest mismatch")
        return scene


@dataclass(frozen=True, slots=True)
class NavigationMapRevision:
    id: str
    scene_revision: str
    width: int
    height: int
    resolution_m: float
    origin_xy_m: tuple[float, float]
    cells: tuple[int, ...]  # row-major, y ascending: -1 unknown, 0 free, 100 occupied
    source: str
    source_ref: str | None = None
    frame_id: str = "world"
    schema_version: str = SITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _id(self.id, "map id")
        _digest(self.scene_revision, "scene_revision")
        _digest(self.source_ref, "source_ref", optional=True)
        if self.schema_version != SITE_SCHEMA_VERSION or self.frame_id != "world":
            raise ValueError("map version or frame is unsupported")
        if self.source not in {"scene", "scan", "slam"} or (self.source != "scene" and self.source_ref is None):
            raise ValueError("map source provenance is invalid")
        if not isinstance(self.origin_xy_m, tuple) or not isinstance(self.cells, tuple) or isinstance(self.resolution_m, bool):
            raise ValueError("map coordinates and cells must be immutable numeric tuples")
        if (type(self.width) is not int or type(self.height) is not int or self.width < 1 or self.height < 1
                or self.width * self.height > 262_144):
            raise ValueError("map dimensions are invalid")
        if not math.isfinite(self.resolution_m) or not 0.001 <= self.resolution_m <= 2.0:
            raise ValueError("map resolution is invalid")
        if len(self.origin_xy_m) != 2 or not all(math.isfinite(item) and abs(item) <= 100 for item in self.origin_xy_m):
            raise ValueError("map origin is invalid")
        if len(self.cells) != self.width * self.height or any(type(item) is not int or item not in {-1, 0, 100} for item in self.cells):
            raise ValueError("map cells must explicitly distinguish free, occupied, and unknown")

    @property
    def revision(self) -> str:
        return canonical_sha256(self._body())

    def _body(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "scene_revision": self.scene_revision,
                "width": self.width, "height": self.height, "resolution_m": self.resolution_m,
                "origin_xy_m": self.origin_xy_m, "cells": self.cells, "source": self.source,
                "source_ref": self.source_ref, "frame_id": self.frame_id}

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "revision": self.revision}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NavigationMapRevision":
        _exact(value, {"schema_version", "id", "scene_revision", "width", "height", "resolution_m",
                       "origin_xy_m", "cells", "source", "source_ref", "frame_id", "revision"}, "map revision")
        if not isinstance(value["origin_xy_m"], list | tuple) or not isinstance(value["cells"], list | tuple):
            raise ValueError("map origin and cells must be arrays")
        result = cls(id=value["id"], scene_revision=value["scene_revision"], width=value["width"],
                     height=value["height"], resolution_m=value["resolution_m"],
                     origin_xy_m=tuple(value["origin_xy_m"]), cells=tuple(value["cells"]),
                     source=value["source"], source_ref=value["source_ref"], frame_id=value["frame_id"],
                     schema_version=value["schema_version"])
        if value["revision"] != result.revision:
            raise ValueError("map revision digest mismatch")
        return result

    def cell_at(self, x_m: float, y_m: float) -> int:
        x = math.floor((x_m - self.origin_xy_m[0]) / self.resolution_m)
        y = math.floor((y_m - self.origin_xy_m[1]) / self.resolution_m)
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return -1  # out of bounds is never silently free
        return self.cells[y * self.width + x]


@dataclass(frozen=True, slots=True)
class RobotInstance:
    id: str
    profile_id: str
    profile_digest: str
    initial_pose: Transform
    observation_id: str | None = None
    schema_version: str = SITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SITE_SCHEMA_VERSION:
            raise ValueError("robot instance version is unsupported")
        _id(self.id, "robot instance id")
        _id(self.profile_id, "robot profile id")
        _digest(self.profile_digest, "profile_digest")
        if self.observation_id is not None:
            _id(self.observation_id, "observation id")
        _pose(self.initial_pose, "initial_pose")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RobotInstance":
        _exact(value, {"schema_version", "id", "profile_id", "profile_digest", "initial_pose", "observation_id"}, "robot instance")
        _exact(value["initial_pose"], {"position_m", "rotation_rpy_deg"}, "robot initial pose")
        return cls(id=value["id"], profile_id=value["profile_id"], profile_digest=value["profile_digest"],
                   initial_pose=Transform.from_dict(value["initial_pose"]), observation_id=value["observation_id"],
                   schema_version=value["schema_version"])


@dataclass(frozen=True, slots=True)
class MissionSpecV2:
    id: str
    scene_revision: str
    robot_instance_id: str
    map_revision: str | None
    start: Transform
    goal: Transform
    waypoints: tuple[Transform, ...] = ()
    position_tolerance_m: float = 0.05
    intent: str = "navigate"
    schema_version: str = SITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SITE_SCHEMA_VERSION or self.intent != "navigate":
            raise ValueError("mission version or intent is unsupported")
        _id(self.id, "mission id")
        _id(self.robot_instance_id, "robot instance id")
        _digest(self.scene_revision, "scene_revision")
        _digest(self.map_revision, "map_revision", optional=True)
        if not isinstance(self.waypoints, tuple):
            raise ValueError("mission waypoints must be an immutable tuple")
        if (len(self.waypoints) > 64 or isinstance(self.position_tolerance_m, bool)
                or not math.isfinite(self.position_tolerance_m) or not 0 < self.position_tolerance_m <= 2):
            raise ValueError("mission waypoint count or tolerance is invalid")
        for name, pose in (("start", self.start), ("goal", self.goal),
                           *((f"waypoint_{index}", item) for index, item in enumerate(self.waypoints))):
            _pose(pose, name)

    @property
    def revision(self) -> str:
        return canonical_sha256(self._body())

    def _body(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id,
                "scene_revision": self.scene_revision, "robot_instance_id": self.robot_instance_id,
                "map_revision": self.map_revision, "start": asdict(self.start), "goal": asdict(self.goal),
                "waypoints": [asdict(item) for item in self.waypoints],
                "position_tolerance_m": self.position_tolerance_m, "intent": self.intent}

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "revision": self.revision}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MissionSpecV2":
        _exact(value, {"schema_version", "id", "scene_revision", "robot_instance_id", "map_revision",
                       "start", "goal", "waypoints", "position_tolerance_m", "intent", "revision"}, "mission")
        if not isinstance(value["waypoints"], list):
            raise ValueError("mission waypoints must be an array")
        _exact(value["start"], {"position_m", "rotation_rpy_deg"}, "mission start")
        _exact(value["goal"], {"position_m", "rotation_rpy_deg"}, "mission goal")
        for item in value["waypoints"]:
            _exact(item, {"position_m", "rotation_rpy_deg"}, "mission waypoint")
        result = cls(id=value["id"], scene_revision=value["scene_revision"],
                     robot_instance_id=value["robot_instance_id"], map_revision=value["map_revision"],
                     start=Transform.from_dict(value["start"]), goal=Transform.from_dict(value["goal"]),
                     waypoints=tuple(Transform.from_dict(item) for item in value["waypoints"]),
                     position_tolerance_m=value["position_tolerance_m"], intent=value["intent"],
                     schema_version=value["schema_version"])
        if value["revision"] != result.revision:
            raise ValueError("mission revision digest mismatch")
        return result


@dataclass(frozen=True, slots=True)
class RunIntent:
    """Immutable proposed run identity; never a claim that hardware or simulation moved."""

    id: str
    scene_revision: str
    map_revision: str
    robot_instance_id: str
    mission_revision: str
    controller_capability: str
    safety_policy_id: str
    schema_version: str = SITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SITE_SCHEMA_VERSION:
            raise ValueError("run intent version is unsupported")
        _id(self.id, "run intent id")
        _id(self.robot_instance_id, "robot instance id")
        _id(self.controller_capability, "controller capability")
        _id(self.safety_policy_id, "safety policy id")
        for name in ("scene_revision", "map_revision", "mission_revision"):
            _digest(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunIntent":
        _exact(value, {"schema_version", "id", "scene_revision", "map_revision", "robot_instance_id",
                       "mission_revision", "controller_capability", "safety_policy_id"}, "run intent")
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class SitePlan:
    scene: SceneRevision
    navigation_map: NavigationMapRevision | None = None
    robot: RobotInstance | None = None
    mission: MissionSpecV2 | None = None
    review_required: bool = True
    schema_version: str = SITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SITE_SCHEMA_VERSION or type(self.review_required) is not bool:
            raise ValueError("site plan version or review flag is invalid")
        if self.robot is not None and self.robot.observation_id is not None and self.robot.observation_id in {
            item.observation_id for item in self.scene.observation_bindings
        }:
            raise ValueError("one observation cannot be both the mobile robot and a scene object")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "scene": self.scene.to_dict(),
                "navigation_map": self.navigation_map.to_dict() if self.navigation_map else None,
                "robot": self.robot.to_dict() if self.robot else None,
                "mission": self.mission.to_dict() if self.mission else None,
                "review_required": self.review_required}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SitePlan":
        _exact(value, {"schema_version", "scene", "navigation_map", "robot", "mission", "review_required"}, "site plan")
        return cls(scene=SceneRevision.from_dict(value["scene"]),
                   navigation_map=None if value["navigation_map"] is None else NavigationMapRevision.from_dict(value["navigation_map"]),
                   robot=None if value["robot"] is None else RobotInstance.from_dict(value["robot"]),
                   mission=None if value["mission"] is None else MissionSpecV2.from_dict(value["mission"]),
                   review_required=value["review_required"], schema_version=value["schema_version"])


@dataclass(frozen=True, slots=True)
class SiteGateReport:
    scene_valid: bool
    robot_compatible: bool
    mission_supported: bool
    run_allowed: bool
    reasons: tuple[str, ...]


def _straight_corridor_free(navigation_map: NavigationMapRevision, mission: MissionSpecV2,
                            profile: RobotProfile) -> bool:
    """Conservatively cover each map cell touched by the old +X robot corridor."""

    sx, sy, _ = mission.start.position_m
    gx, _, _ = mission.goal.position_m
    margin_x = profile.chassis_dimensions_m[0] / 2 + 0.05
    margin_y = profile.chassis_dimensions_m[1] / 2 + 0.05
    x0 = math.floor((sx - margin_x - navigation_map.origin_xy_m[0]) / navigation_map.resolution_m)
    x1 = math.floor((gx + margin_x - navigation_map.origin_xy_m[0]) / navigation_map.resolution_m)
    y0 = math.floor((sy - margin_y - navigation_map.origin_xy_m[1]) / navigation_map.resolution_m)
    y1 = math.floor((sy + margin_y - navigation_map.origin_xy_m[1]) / navigation_map.resolution_m)
    if x0 < 0 or y0 < 0 or x1 >= navigation_map.width or y1 >= navigation_map.height:
        return False
    return all(navigation_map.cells[y * navigation_map.width + x] == 0
               for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))


def evaluate_site_plan(plan: SitePlan, *, profile: RobotProfile | None = None,
                       run_intent: RunIntent | None = None, build_receipt: CommandReceipt | None = None,
                       snapshot: SimulationSnapshot | None = None, engine_connected: bool = False,
                       engine_session_id: str | None = None, stage_epoch: str | None = None,
                       controller_capabilities: frozenset[str] = frozenset()) -> SiteGateReport:
    """Independent gates. A valid scene never implies a drivable mission."""

    reasons: list[str] = []
    try:
        from .validation import ValidationLimits
        validate_scene_geometry(plan.scene.id, plan.scene.objects, ValidationLimits(max_objects=None))
        scene_valid = True
    except SpecValidationError:
        scene_valid = False
        reasons.append("scene_invalid")

    robot_compatible = False
    if plan.robot is None or profile is None:
        reasons.append("robot_missing")
    else:
        try:
            validate_robot_profile(profile)
            robot_compatible = (plan.robot.profile_id == profile.id and
                                plan.robot.profile_digest == canonical_sha256(asdict(profile)))
        except SpecValidationError:
            pass
        if not robot_compatible:
            reasons.append("robot_profile_mismatch")

    map_valid = plan.navigation_map is not None and plan.navigation_map.scene_revision == plan.scene.revision
    if not map_valid:
        reasons.append("map_missing_or_stale")

    mission_supported = False
    mission = plan.mission
    if mission is None:
        reasons.append("mission_missing")
    elif not (robot_compatible and map_valid and plan.robot and profile):
        reasons.append("mission_dependencies_unavailable")
    elif (mission.scene_revision != plan.scene.revision or mission.map_revision != plan.navigation_map.revision
          or mission.robot_instance_id != plan.robot.id or mission.start != plan.robot.initial_pose):
        reasons.append("mission_identity_mismatch")
    elif any(plan.navigation_map.cell_at(pose.position_m[0], pose.position_m[1]) != 0
             for pose in (mission.start, *mission.waypoints, mission.goal)):
        reasons.append("mission_blocked_or_unknown")
    elif mission.waypoints:
        reasons.append("controller_route_unsupported")
    else:
        legacy_view = SpecBundle(
            scene=SceneSpec(id=plan.scene.id, objects=plan.scene.objects, robot_profile_id=profile.id),
            robot=profile,
            task=TaskSpec(id=mission.id, robot_profile_id=profile.id, start=mission.start,
                          goal=mission.goal, position_tolerance_m=mission.position_tolerance_m),
        )
        try:
            validate_current_controller_route(legacy_view)
            mission_supported = _straight_corridor_free(plan.navigation_map, mission, profile)
        except SpecValidationError:
            pass
        if not mission_supported:
            reasons.append("controller_route_unsupported_or_blocked")

    run_allowed = False
    if plan.review_required:
        reasons.append("review_required")
    if run_intent is None or build_receipt is None or snapshot is None or not engine_connected:
        reasons.append("run_evidence_missing")
    elif (scene_valid and robot_compatible and mission_supported and not plan.review_required and
          run_intent.scene_revision == plan.scene.revision and
          run_intent.map_revision == plan.navigation_map.revision and
          run_intent.robot_instance_id == plan.robot.id and
          run_intent.mission_revision == mission.revision and
          run_intent.controller_capability == STRAIGHT_CONTROLLER_CAPABILITY and
          run_intent.safety_policy_id == DEMO_SAFETY_POLICY_ID and
          run_intent.controller_capability in controller_capabilities and
          build_receipt.command_type == "build_scene" and build_receipt.status == "succeeded" and
          build_receipt.applied_revision == plan.scene.revision and
          build_receipt.build_fingerprint is not None and
          build_receipt.engine_session_id == engine_session_id and build_receipt.stage_epoch == stage_epoch and
          snapshot.engine_session_id == engine_session_id and snapshot.stage_epoch == stage_epoch and
          snapshot.project_id == build_receipt.project_id and snapshot.applied_revision == plan.scene.revision and
          snapshot.frame_id == plan.scene.frame_id and snapshot.safety_state is None and
          "run" in snapshot.permitted_commands):
        run_allowed = True
    else:
        reasons.append("run_identity_or_capability_unconfirmed")
    return SiteGateReport(scene_valid, robot_compatible, mission_supported, run_allowed, tuple(reasons))


def import_legacy_bundle(bundle: SpecBundle) -> SitePlan:
    """Explicit, review-required pure adapter; never carries an old approval/receipt."""

    validate_bundle(bundle)
    scene = SceneRevision(bundle.scene.id, bundle.scene.objects, "legacy", source_ref=bundle_digest(bundle))
    robot = RobotInstance("legacy_robot", bundle.robot.id, canonical_sha256(asdict(bundle.robot)), bundle.task.start)
    mission = MissionSpecV2(bundle.task.id, scene.revision, robot.id, None, bundle.task.start,
                            bundle.task.goal, position_tolerance_m=bundle.task.position_tolerance_m)
    return SitePlan(scene=scene, robot=robot, mission=mission, review_required=True)
