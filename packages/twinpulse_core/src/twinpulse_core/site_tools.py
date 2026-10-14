# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""H2b-1 versioned, allowlisted site-plan expansion; no engine side effects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Mapping

from .models import SceneObject, ShapeSpec, Transform
from .furniture import expand_furniture, validate_furniture_layout
from .room_items import expand_room_item, validate_room_item_bounds
from .revisions import canonical_sha256
from .robot_profiles import resolve_robot_profile
from .scene_tools import (SceneToolCall, SceneToolPlanError, SceneToolRegistry,
                          _number, _object_id, _positive_vector, _validate_rack_row_overlap, _vector)
from .site_contracts import MissionSpecV2, ObservationBinding, RobotInstance, SceneRevision, SitePlan
from .tool_catalog import static_tool_definitions, tool_names


SITE_TOOL_PLAN_VERSION = "2.0"
SITE_TOOL_CATALOG_REVISION = "site-tools-2.1"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
SITE_TOOL_NAMES = tool_names(SITE_TOOL_PLAN_VERSION)
_STATIC_TOOLS = SITE_TOOL_NAMES - {"place_predefined_agv", "create_navigation_task"}
_STATIC_TOOL_DEFINITIONS = static_tool_definitions(SITE_TOOL_PLAN_VERSION)


@dataclass(frozen=True, slots=True)
class SiteCallEvidence:
    call_id: str
    observation_ids: tuple[str, ...]
    basis: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {"call_id": self.call_id, "observation_ids": list(self.observation_ids),
                "basis": self.basis, "note": self.note}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SiteCallEvidence":
        if (not isinstance(value, Mapping) or set(value) != {"call_id", "observation_ids", "basis", "note"}
                or not isinstance(value["observation_ids"], list)):
            raise SceneToolPlanError("site call evidence shape is unsupported")
        return cls(value["call_id"], tuple(value["observation_ids"]), value["basis"], value["note"])


@dataclass(frozen=True, slots=True)
class SiteToolPlan:
    scene_id: str
    summary: str
    image_observations: str
    calls: tuple[SceneToolCall, ...]
    plan_version: str = SITE_TOOL_PLAN_VERSION
    # None preserves the exact serialization/digest of persisted pre-H3a v2 drafts.
    call_evidence: tuple[SiteCallEvidence, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"plan_version": self.plan_version, "scene_id": self.scene_id,
                "summary": self.summary, "image_observations": self.image_observations,
                "calls": [item.to_dict() for item in self.calls]}
        if self.call_evidence is not None:
            result["call_evidence"] = [item.to_dict() for item in self.call_evidence]
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SiteToolPlan":
        required = {"plan_version", "scene_id", "summary", "image_observations", "calls"}
        if (not isinstance(value, Mapping) or set(value) not in (required, required | {"call_evidence"})
                or not isinstance(value["calls"], list)):
            raise SceneToolPlanError("site tool plan shape is unsupported")
        evidence = value.get("call_evidence")
        if "call_evidence" in value and not isinstance(evidence, list):
            raise SceneToolPlanError("site call evidence must be an array")
        for item in value["calls"]:
            if (not isinstance(item, Mapping) or set(item) != {"call_id", "tool", "arguments"}
                    or not isinstance(item["call_id"], str) or not isinstance(item["tool"], str)
                    or not isinstance(item["arguments"], Mapping)):
                raise SceneToolPlanError("site tool call shape is unsupported")
        return validate_site_tool_plan(cls(
            scene_id=value["scene_id"], summary=value["summary"],
            image_observations=value["image_observations"],
            calls=tuple(SceneToolCall.from_dict(item) for item in value["calls"]),
            plan_version=value["plan_version"],
            call_evidence=None if evidence is None else tuple(SiteCallEvidence.from_dict(item) for item in evidence),
        ))


def site_tool_plan_from_json(payload: str) -> SiteToolPlan:
    value = json.loads(payload)
    if not isinstance(value, Mapping):
        raise SceneToolPlanError("site tool plan must be a JSON object")
    return SiteToolPlan.from_dict(value)


def validate_site_tool_plan(plan: SiteToolPlan) -> SiteToolPlan:
    if plan.plan_version not in {SITE_TOOL_PLAN_VERSION, "2.1", "2.2"}:
        raise SceneToolPlanError("unsupported site tool plan version")
    if not isinstance(plan.scene_id, str) or not _ID.fullmatch(plan.scene_id):
        raise SceneToolPlanError("site scene id is invalid")
    if not isinstance(plan.summary, str) or not 1 <= len(plan.summary.strip()) <= 500:
        raise SceneToolPlanError("site summary is invalid")
    if not isinstance(plan.image_observations, str) or len(plan.image_observations) > 1000:
        raise SceneToolPlanError("site image observations are invalid")
    if not isinstance(plan.calls, tuple) or not plan.calls:
        raise SceneToolPlanError('site plan must contain calls')
    if plan.plan_version != '2.2' and len(plan.calls) > 24:
        raise SceneToolPlanError('legacy site plan must contain 1 to 24 calls')
    ids: set[str] = set()
    counts: dict[str, int] = {}
    for call in plan.calls:
        if not isinstance(call, SceneToolCall) or not isinstance(call.arguments, Mapping):
            raise SceneToolPlanError("site tool call is invalid")
        if not isinstance(call.call_id, str) or not _ID.fullmatch(call.call_id) or call.call_id in ids:
            raise SceneToolPlanError("site call id is invalid or duplicated")
        ids.add(call.call_id)
        if call.tool not in tool_names(plan.plan_version):
            raise SceneToolPlanError("site tool is not allowlisted")
        counts[call.tool] = counts.get(call.tool, 0) + 1
    if plan.plan_version == '2.2':
        import json
        size = 0
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(plan.to_dict()):
            size += len(chunk.encode('utf-8'))
            if size > 2 * 1024 * 1024:
                raise SceneToolPlanError('site plan exceeds serialized memory budget')
    if counts.get("create_floor") != 1 or counts.get("place_predefined_agv", 0) > 1 or counts.get("create_navigation_task", 0) > 1:
        raise SceneToolPlanError("site plan requires one floor and at most one robot and mission")
    if counts.get("create_navigation_task", 0) and not counts.get("place_predefined_agv", 0):
        raise SceneToolPlanError("a navigation task requires an explicit robot")
    if counts.get("place_predefined_agv", 0) and counts.get("place_static_agv", 0):
        raise SceneToolPlanError("an observed AGV cannot also be a static scene object without explicit binding")
    if plan.call_evidence is not None:
        if len(plan.call_evidence) != len(plan.calls):
            raise SceneToolPlanError("site call evidence must cover every call")
        seen: set[str] = set()
        for evidence in plan.call_evidence:
            if (not isinstance(evidence, SiteCallEvidence) or not isinstance(evidence.call_id, str)
                    or evidence.call_id not in ids or evidence.call_id in seen):
                raise SceneToolPlanError("site call evidence has an unknown or duplicate call")
            seen.add(evidence.call_id)
            if evidence.basis not in {"visual", "user", "inferred", "trusted_measurement"}:
                raise SceneToolPlanError("site call evidence basis is unsupported")
            if not isinstance(evidence.note, str) or not 1 <= len(evidence.note.strip()) <= 256:
                raise SceneToolPlanError("site call evidence note is invalid")
            if (not isinstance(evidence.observation_ids, tuple) or len(evidence.observation_ids) > 8
                    or any(not isinstance(item, str) or not _ID.fullmatch(item)
                           for item in evidence.observation_ids)
                    or len(evidence.observation_ids) != len(set(evidence.observation_ids))):
                raise SceneToolPlanError("site call evidence observation ids are invalid")
            if evidence.basis == "visual" and not evidence.observation_ids:
                raise SceneToolPlanError("visual site call evidence requires an observation id")
            tool = next(call.tool for call in plan.calls if call.call_id == evidence.call_id)
            if tool in {"place_predefined_agv", "create_navigation_task"} and evidence.basis != "user":
                raise SceneToolPlanError("driven robot and mission require a user-evidence basis")
    return plan


def execute_site_tool_plan(plan: SiteToolPlan, *, source: str, source_ref: str) -> SitePlan:
    """Build a review-required v2 draft; never move its requested start or goal."""

    validate_site_tool_plan(plan)
    if not isinstance(source_ref, str) or not _DIGEST.fullmatch(source_ref):
        raise SceneToolPlanError("site source reference must be a trusted digest")
    registry = SceneToolRegistry()
    objects: list[SceneObject] = []
    furniture_groups: list[tuple[str, ...]] = []
    room_objects: list[SceneObject] = []
    room_owners: dict[str, str] = {}
    bindings: list[ObservationBinding] = []
    evidence_by_call = {item.call_id: item for item in (plan.call_evidence or ())}
    robot_call = next((item for item in plan.calls if item.tool == "place_predefined_agv"), None)
    robot_profile = None
    if robot_call is not None:
        try:
            robot_profile = resolve_robot_profile(str(robot_call.arguments.get("profile_id", "")))
        except KeyError as error:
            raise SceneToolPlanError("site robot profile is unsupported") from error
    robot = None
    task = None
    for call in plan.calls:
        args = call.arguments
        before = len(objects)
        try:
            if plan.plan_version in {"2.1", "2.2"} and call.tool == "place_furniture":
                if plan.plan_version != '2.2' and args.get('catalog_version') != 'furniture-blocks-1.0':
                    raise SceneToolPlanError('parametric furniture requires SiteToolPlan 2.2')
                parts = expand_furniture(args)
                objects.extend(parts)
                furniture_groups.append(tuple(part.id for part in parts))
            elif plan.plan_version == '2.2' and call.tool == 'place_room_item':
                parts = expand_room_item(dict(args))
                objects.extend(parts)
                room_objects.extend(parts)
                room_owners.update({part.id:args['id'] for part in parts})
            elif call.tool in tool_names(plan.plan_version) - {'place_predefined_agv', 'create_navigation_task'}:
                if call.tool in _STATIC_TOOL_DEFINITIONS:
                    objects.extend(registry.execute_static_tool(call.tool, args))
                elif call.tool == "create_box_obstacle":
                    if set(args) != {"id", "center_m", "dimensions_m", "yaw_deg"}:
                        raise SceneToolPlanError("box obstacle arguments are invalid")
                    object_id = _object_id(args["id"])
                    center = _vector(args["center_m"], 2, "center_m")
                    dimensions = _positive_vector(args["dimensions_m"], 3, "dimensions_m", maximum=20.0)
                    yaw = _number(args["yaw_deg"], "yaw_deg", minimum=-180.0, maximum=180.0)
                    objects.append(SceneObject(object_id, "equipment",
                                               Transform((center[0], center[1], dimensions[2] / 2.0),
                                                         (0.0, 0.0, yaw)), ShapeSpec("box", dimensions)))
            elif call.tool == "place_predefined_agv":
                if robot_profile is None:
                    raise SceneToolPlanError("site robot profile is missing")
                start = registry._place_predefined_agv(args, robot_profile)
                robot = RobotInstance("site_robot", robot_profile.id,
                                      canonical_sha256(asdict(robot_profile)), Transform(start))
            elif call.tool == "create_navigation_task":
                if robot_profile is None:
                    raise SceneToolPlanError("site robot profile is missing")
                task = registry._create_navigation_task(args, robot_profile)
        except (KeyError, TypeError) as error:
            raise SceneToolPlanError(f"site tool arguments are invalid for {call.tool}") from error
        evidence = evidence_by_call.get(call.call_id)
        if evidence is not None and evidence.basis == "visual":
            bindings.extend(ObservationBinding(observation_id, item.id, "scene_object")
                            for observation_id in evidence.observation_ids for item in objects[before:])
        if plan.plan_version != '2.2' and len(objects) > 64:
            raise SceneToolPlanError("site scene exceeds the 64-object limit")
    _validate_rack_row_overlap(plan.calls)
    # Overhanging fabric / tabletop props may intentionally overlap their furniture.
    # Their colliding keepouts still enter the unchanged route geometry checks.
    validate_furniture_layout(tuple(o for o in objects if o not in room_objects), tuple(furniture_groups))
    if room_objects:
        validate_room_item_bounds(room_objects, next(o for o in objects if o.kind == 'floor'),owners=room_owners)
    scene = SceneRevision(plan.scene_id, tuple(objects), source, source_ref=source_ref,
                          observation_bindings=tuple(bindings))
    mission = None
    if task is not None:
        assert robot is not None
        mission = MissionSpecV2(task.id, scene.revision, robot.id, None, robot.initial_pose,
                                task.goal, position_tolerance_m=task.position_tolerance_m)
    return SitePlan(scene=scene, robot=robot, mission=mission, review_required=True)
