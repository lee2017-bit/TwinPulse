# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Source-bound, review-only edits to a saved v2 site plan.

The original project record and room recipe are never rewritten. Each operation
is replayed through the existing allowlisted site-tool executor on load.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from copy import deepcopy
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from twinpulse_core import canonical_sha256, execute_site_tool_plan
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.site_contracts import SceneRevision, SitePlan
from twinpulse_core.site_tools import SiteCallEvidence, SiteToolPlan

from .site_draft import SiteDraftRecord
from .dependency_patch import (EffectiveScene, initial_state, apply_patch_state,
    checked_patch, with_plan, _compile)


CHANGE_VERSION = "scene-changes-1.0"
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES = 2 * 1024 * 1024
_MAX_OPERATIONS = 128
_IMMUTABLE_TOOLS = {"create_floor", "place_predefined_agv", "create_navigation_task"}


def _process_identity(pid):
    """Read-only process identity; None means definitely dead, not unknown."""
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            if ctypes.get_last_error()==87:return None
            raise ValueError('scene lock process liveness is unknown')
        try:
            exit_code=wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)):raise ValueError('scene lock process status is unknown')
            if exit_code.value!=259:return None
            times=[wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]):raise ValueError('scene lock owner identity is unknown')
            return str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
        finally:kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
    except ProcessLookupError:return None
    except PermissionError:raise ValueError('scene lock process liveness is unknown') from None
    # Linux process birth identity protects against PID reuse.
    return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]




def _edit_plan_version(plan, calls):
    from twinpulse_core.library_assets import edit_plan_version
    return edit_plan_version(plan,calls)


def _scene_from_plan(source: SiteDraftRecord, plan: SiteToolPlan,
                     parent_revision: str | None) -> SitePlan:
    base = execute_site_tool_plan(
        SiteToolPlan.from_dict(plan.to_dict()),
        source=source.site.scene.source,
        source_ref=source.input_revision.digest,
    )
    from twinpulse_core.photo_placement import validate_placement_plan
    validate_placement_plan(plan,source.placement_contract)
    if parent_revision is None:
        return base
    scene = replace(base.scene, parent_revision=parent_revision)
    # Old navigation evidence is bound to the old geometry. It cannot be reused.
    return replace(base, scene=scene, navigation_map=None, mission=None)


def _object_digests(scene: SceneRevision) -> dict[str, str]:
    return {item.id: canonical_sha256(asdict(item)) for item in scene.objects}


def _emitted_ids(call):
    from twinpulse_core.scene_tools import SceneToolRegistry
    if call.tool=='place_library_asset':
        from twinpulse_core.library_assets import expand_library_asset
        return {expand_library_asset(dict(call.arguments)).id}
    if call.tool=='place_model_recipe':
        from twinpulse_core.model_recipe import expand_model_recipe
        return {o.id for o in expand_model_recipe(dict(call.arguments))}
    if call.tool=='place_furniture':
        from twinpulse_core.furniture import expand_furniture
        return {o.id for o in expand_furniture(call.arguments)}
    if call.tool=='place_room_item':
        from twinpulse_core.room_items import expand_room_item
        return {o.id for o in expand_room_item(dict(call.arguments))}
    if call.tool=='create_box_obstacle': return {call.arguments['id']}
    if call.tool in {'place_predefined_agv','create_navigation_task'}: return set()
    return {o.id for o in SceneToolRegistry().execute_static_tool(call.tool,call.arguments)}


def _preserved_geometry(state,affected):
    targets = set().union(*(_emitted_ids(c) for c in state.plan.calls if c.arguments['id'] in affected))
    return {k:v for k,v in _object_digests(state.site.scene).items() if k not in targets}


@dataclass(frozen=True, slots=True)
class SceneChange:
    operation_id: str
    mode: str
    parent_revision: str
    target_call_id: str | None
    tool_call: SceneToolCall | None
    expected_non_target_digests: dict[str, str]
    result_revision: str
    tool_calls: tuple[SceneToolCall, ...] = ()
    dependency_patch: dict | None = None
    parent_state_sha256: str | None = None
    result_state_sha256: str | None = None
    expected_non_target_inventory_digests: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {"operation_id": self.operation_id, "mode": self.mode,
                "parent_revision": self.parent_revision,
                "target_call_id": self.target_call_id,
                "tool_call": self.tool_call.to_dict() if self.tool_call else None,
                "expected_non_target_digests": dict(self.expected_non_target_digests),
                "result_revision": self.result_revision}
        if self.mode == "add_many":
            value["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.mode == 'dependency':
            value.update(dependency_patch=self.dependency_patch,
                parent_state_sha256=self.parent_state_sha256, result_state_sha256=self.result_state_sha256,
                expected_non_target_inventory_digests=self.expected_non_target_inventory_digests)
        elif self.mode=='undo' and self.parent_state_sha256 is not None:
            value.update(parent_state_sha256=self.parent_state_sha256,result_state_sha256=self.result_state_sha256)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SceneChange":
        fields = {"operation_id", "mode", "parent_revision", "target_call_id",
                  "tool_call", "expected_non_target_digests", "result_revision"}
        extras = ({'tool_calls'} if isinstance(value,Mapping) and value.get('mode')=='add_many' else
            {'dependency_patch','parent_state_sha256','result_state_sha256','expected_non_target_inventory_digests'}
            if isinstance(value,Mapping) and value.get('mode')=='dependency' else
            {'parent_state_sha256','result_state_sha256'} if isinstance(value,Mapping) and value.get('mode')=='undo'
                and 'parent_state_sha256' in value else set())
        if not isinstance(value, Mapping) or set(value) != fields | extras:
            raise ValueError("scene change shape is unsupported")
        tool = value["tool_call"]
        if tool is not None and not isinstance(tool, Mapping):
            raise ValueError("tool call is invalid")
        digests = value["expected_non_target_digests"]
        if not isinstance(digests, Mapping) or any(
            not isinstance(key, str) or not _ID.fullmatch(key)
            or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
            for key, digest in digests.items()
        ):
            raise ValueError("non-target digests are invalid")
        raw_calls = value.get("tool_calls", [])
        if not isinstance(raw_calls, list) or any(not isinstance(item, Mapping) for item in raw_calls):
            raise ValueError("batch tool calls are invalid")
        calls = tuple(SceneToolCall.from_dict(item) for item in raw_calls)
        result = cls(value["operation_id"], value["mode"], value["parent_revision"],
                     value["target_call_id"], SceneToolCall.from_dict(tool) if tool else None,
                     dict(digests), value["result_revision"], calls,
                     checked_patch(value['dependency_patch']) if value['mode']=='dependency' else None,
                     value.get('parent_state_sha256'),value.get('result_state_sha256'),
                     value.get('expected_non_target_inventory_digests'))
        if (not isinstance(result.operation_id, str) or not _ID.fullmatch(result.operation_id)
                or result.mode not in {"add", "change", "undo", "add_many", "dependency"}
                or not isinstance(result.parent_revision, str) or not _DIGEST.fullmatch(result.parent_revision)
                or not isinstance(result.result_revision, str) or not _DIGEST.fullmatch(result.result_revision)
                or (result.target_call_id is not None and
                    (not isinstance(result.target_call_id, str) or not _ID.fullmatch(result.target_call_id)))
                or (result.mode == "undo" and (result.tool_call is not None or
                                               result.target_call_id is not None or calls or
                    result.parent_state_sha256 is not None and any(not isinstance(v,str) or not _DIGEST.fullmatch(v)
                        for v in (result.parent_state_sha256,result.result_state_sha256))))
                or (result.mode == 'dependency' and (result.tool_call is not None or result.target_call_id is not None or calls
                    or any(not isinstance(v,str) or not _DIGEST.fullmatch(v) for v in
                           (result.parent_state_sha256,result.result_state_sha256))
                    or not isinstance(result.expected_non_target_inventory_digests,dict)
                    or any(not isinstance(k,str) or not _ID.fullmatch(k) or not isinstance(v,str) or not _DIGEST.fullmatch(v)
                           for k,v in result.expected_non_target_inventory_digests.items())))
                or (result.mode == "add_many" and (result.tool_call is not None or
                                                   result.target_call_id is not None or
                                                   not 2 <= len(calls) <= 3 or
                                                   any(call.tool != "place_furniture" for call in calls) or
                                                   len({call.call_id for call in calls}) != len(calls)))
                or (result.mode in {"add", "change"} and (result.tool_call is None or calls or
                       (result.mode == "change") != (result.target_call_id is not None)))):
            raise ValueError("scene change fields are invalid")
        return result


@dataclass(frozen=True, slots=True)
class SceneChangeHistory:
    project_id: str
    source_sha256: str
    input_revision: str
    source_scene_revision: str
    operations: tuple[SceneChange, ...]
    current_scene_revision: str
    schema_version: str = CHANGE_VERSION

    @classmethod
    def empty(cls, project_id: str, source: SiteDraftRecord) -> "SceneChangeHistory":
        if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
            raise ValueError("project identity is invalid")
        checked = SiteDraftRecord.from_dict(source.to_dict())
        return cls(project_id, canonical_sha256(checked.to_dict()), checked.input_revision.digest,
                   checked.site.scene.revision, (), checked.site.scene.revision,
                   'scene-changes-1.2' if checked.progressive_twin is not None else
                   'scene-changes-1.1' if checked.placement_contract is not None else CHANGE_VERSION)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "project_id": self.project_id,
                "source_sha256": self.source_sha256, "input_revision": self.input_revision,
                "source_scene_revision": self.source_scene_revision,
                "operations": [item.to_dict() for item in self.operations],
                "current_scene_revision": self.current_scene_revision}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], source: SiteDraftRecord,
                  project_id: str) -> "SceneChangeHistory":
        fields = {"schema_version", "project_id", "source_sha256", "input_revision",
                  "source_scene_revision", "operations", "current_scene_revision"}
        if (not isinstance(value, Mapping) or set(value) != fields or value["schema_version"] not in (CHANGE_VERSION,'scene-changes-1.1','scene-changes-1.2')
                or value["project_id"] != project_id or not isinstance(value["operations"], list)
                or len(value["operations"]) > _MAX_OPERATIONS):
            raise ValueError("scene change history shape is unsupported")
        if value['schema_version']=='scene-changes-1.1' and source.placement_contract is None:
            raise ValueError('stack undo requires the explicit placement source contract')
        history = replace(cls.empty(project_id, source),schema_version=value['schema_version'])
        if any(value[key] != getattr(history, key) for key in (
            "source_sha256", "input_revision", "source_scene_revision"
        )):
            raise ValueError("scene change source differs from saved original")
        for raw in value["operations"]:
            operation = SceneChange.from_dict(raw)
            history = history.append(source, operation)
        if history.current_scene_revision != value["current_scene_revision"]:
            raise ValueError("scene change history result differs from replay")
        return history

    def replay(self, source: SiteDraftRecord) -> tuple[SiteToolPlan, SitePlan]:
        if self.schema_version=='scene-changes-1.2':
            state = self.effective(source)
            return state.plan, state.site
        if self.source_sha256 != canonical_sha256(source.to_dict()):
            raise ValueError("scene change source changed")
        plan = source.plan
        site = source.site
        plans = [plan]
        for index,operation in enumerate(self.operations):
            undo_plan=(plans[self._undo_plan_index(self.operations[:index])]
                       if operation.mode=='undo' and self.schema_version=='scene-changes-1.1' else None)
            plan, site = self._apply_one(source, plan, site, plans, operation,undo_plan)
            plans.append(plan)
        if site.scene.revision != self.current_scene_revision:
            raise ValueError("scene change result changed")
        return plan, site

    @staticmethod
    def state_sha256(state):
        return canonical_sha256(dict(plan=state.plan.to_dict(), placement=state.placement,
            inventory=state.inventory, scene_revision=state.site.scene.revision,
            **({'draft_refinement':state.refinement} if state.refinement is not None else {})))

    def effective(self, source):
        """The current plan, relationships and retained inventory share one history."""
        if self.source_sha256 != canonical_sha256(source.to_dict()):
            raise ValueError('scene change source changed')
        if self.schema_version!='scene-changes-1.2':
            plan,site = self.replay(source)
            state = initial_state(source)
            return replace(with_plan(source,state,plan,None),site=site)
        state = initial_state(source)
        states = [state]; active = []
        for operation in self.operations:
            if operation.parent_revision != state.site.scene.revision:
                raise ValueError('scene change parent is stale')
            before = _object_digests(state.site.scene)
            if operation.mode=='dependency':
                if operation.parent_state_sha256 != self.state_sha256(state):
                    raise ValueError('scene change dependency state is stale')
                updated, affected = apply_patch_state(source,state,operation.dependency_patch,state.site.scene.revision)
                preserved_inventory = {k:canonical_sha256(v) for k,v in state.inventory.items() if k not in affected}
                if (preserved_inventory != operation.expected_non_target_inventory_digests or
                        any(updated.inventory.get(k) != state.inventory[k] for k in preserved_inventory)):
                    raise ValueError('non-target scene inventory changed')
                # Determine emitted geometry scope before checking the candidate.
                preserved = _preserved_geometry(state,affected)
                after = _object_digests(updated.site.scene)
                if operation.expected_non_target_digests != preserved or any(after.get(k)!=v for k,v in preserved.items()):
                    raise ValueError('non-target scene object changed')
                if operation.result_state_sha256 != self.state_sha256(updated):
                    raise ValueError('scene change result state differs from replay')
                active.append(len(states)-1)
            elif operation.mode=='undo':
                if operation.parent_state_sha256 is not None and operation.parent_state_sha256!=self.state_sha256(state):
                    raise ValueError('scene change Undo state is stale')
                if not active: raise ValueError('there is no active scene edit to undo')
                old = states[active.pop()]
                updated = EffectiveScene(old.plan,_compile(source,old.plan,old.placement,state.site.scene.revision),
                    deepcopy(old.placement),deepcopy(old.inventory))
                after = _object_digests(updated.site.scene)
                preserved = {k:v for k,v in before.items() if after.get(k)==v}
                if operation.expected_non_target_digests != preserved:
                    raise ValueError('non-target scene object changed')
                if operation.result_state_sha256 is not None and operation.result_state_sha256!=self.state_sha256(updated):
                    raise ValueError('scene change Undo result state differs from replay')
            else:
                # Existing typed changes retain their original validation.
                current_source = replace(source,placement_contract=state.placement)
                plan,site = self._apply_one(current_source,state.plan,state.site,[s.plan for s in states],operation)
                updated = with_plan(source,state,plan,state.site.scene.revision)
                if updated.site.scene.revision != site.scene.revision: raise ValueError('scene change result changed')
                active.append(len(states)-1)
            if updated.site.scene.revision != operation.result_revision:
                raise ValueError('scene change result revision differs from replay')
            state = updated; states.append(state)
        if state.site.scene.revision != self.current_scene_revision:
            raise ValueError('scene change result changed')
        return state

    @staticmethod
    def _undo_plan_index(operations):
        active=[]
        for index,operation in enumerate(operations):
            if operation.mode=='undo':
                if not active:raise ValueError('there is no active scene edit to undo')
                active.pop()
            else:active.append(index)
        if not active:raise ValueError('there is no active scene edit to undo')
        return active[-1]

    @staticmethod
    def _apply_one(source: SiteDraftRecord, plan: SiteToolPlan, site: SitePlan,
                   plans: list[SiteToolPlan], operation: SceneChange,
                   undo_plan: SiteToolPlan | None = None) -> tuple[SiteToolPlan, SitePlan]:
        if operation.parent_revision != site.scene.revision:
            raise ValueError("scene change parent is stale")
        before = _object_digests(site.scene)
        if operation.mode == "undo":
            if len(plans) < 2:
                raise ValueError("there is no scene edit to undo")
            next_plan = undo_plan if undo_plan is not None else plans[-2]
            targets = set()
        elif operation.mode == "add_many":
            calls = operation.tool_calls
            if any(call.call_id in {item.call_id for item in plan.calls} for call in calls):
                raise ValueError("scene edit call id already exists")
            next_calls = plan.calls + calls
            targets = set()
            evidence = None if plan.call_evidence is None else plan.call_evidence + tuple(
                SiteCallEvidence(call.call_id, (), "user", "Explicit local multi-furniture edit") for call in calls)
            next_plan = SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                                     next_calls, plan_version=_edit_plan_version(plan, calls), call_evidence=evidence)
        else:
            call = operation.tool_call
            assert call is not None
            if call.tool in _IMMUTABLE_TOOLS:
                raise ValueError("scene edit cannot change floor, robot or mission")
            if operation.mode == "add":
                if any(existing.call_id == call.call_id for existing in plan.calls):
                    raise ValueError("scene edit call id already exists")
                next_calls = plan.calls + (call,)
                targets = set()
            else:
                target = operation.target_call_id
                old = next((item for item in plan.calls if item.call_id == target), None)
                if old is None or old.tool in _IMMUTABLE_TOOLS or call.call_id != target:
                    raise ValueError("scene edit target is invalid")
                next_calls = tuple(call if item.call_id == target else item for item in plan.calls)
                # Includes every object emitted by the call, not just its first object.
                without = replace(plan, calls=tuple(item for item in plan.calls if item.call_id != target),
                                  call_evidence=(None if plan.call_evidence is None else tuple(
                                      item for item in plan.call_evidence if item.call_id != target)))
                remaining = {item.id for item in execute_site_tool_plan(without,
                    source=source.site.scene.source,source_ref=source.input_revision.digest).scene.objects}
                targets = set(before) - remaining
            if plan.call_evidence is None:
                evidence = None
            else:
                evidence = tuple(item for item in plan.call_evidence if item.call_id != call.call_id) + (
                    SiteCallEvidence(call.call_id, (), "user", "Explicit local scene edit"),)
            next_plan = SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                                     next_calls, plan_version=_edit_plan_version(plan, (call,)), call_evidence=evidence)
            if operation.mode=='change' and source.placement_contract is not None:
                from twinpulse_core.photo_placement import relocate_attached_children
                next_plan=relocate_attached_children(plan,next_plan,source.placement_contract,operation.target_call_id)
                # Only the target's declared children may change atomically.
        next_site = _scene_from_plan(source, next_plan, site.scene.revision)
        after = _object_digests(next_site.scene)
        # Compute the checked result once per operation, not once per object.
        # Repeated full compilation during Undo could exceed the owner lease
        # while merely polling the saved scene. Hashes and checks stay identical.
        if operation.mode=='undo' or (operation.mode=='change' and source.placement_contract is not None):
            targets.update(key for key,value in before.items() if after.get(key)!=value)
        if operation.mode in {"add", "add_many"}:
            targets = set(after) - set(before)
            if not targets:
                raise ValueError("scene edit added no object")
        preserved = {key: value for key, value in before.items() if key not in targets}
        if operation.expected_non_target_digests != preserved or any(after.get(key) != value for key, value in preserved.items()):
            raise ValueError("non-target scene object changed")
        if (site.robot != next_site.robot or
                (site.mission is not None and next_site.mission is not None and
                 (site.mission.start != next_site.mission.start or site.mission.goal != next_site.mission.goal))):
            raise ValueError("scene edit changed the robot or mission")
        if operation.result_revision != next_site.scene.revision:
            raise ValueError("scene edit result revision differs from replay")
        return next_plan, next_site

    def preview(self, source: SiteDraftRecord, *, operation_id: str, mode: str,
                target_call_id: str | None = None,
                tool_call: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if any(item.operation_id == operation_id for item in self.operations):
            raise ValueError("operation id already exists")
        if mode=='dependency' or self.schema_version=='scene-changes-1.2' and mode=='undo':
            return self._dependency_preview(source,operation_id,mode,tool_call,target_call_id)
        plan, site = self.replay(source)
        placement = self.effective(source).placement if self.schema_version=='scene-changes-1.2' else source.placement_contract
        if mode not in {"add", "change", "undo", "add_many"}:
            raise ValueError("edit mode is unsupported")
        if mode == "undo":
            if tool_call is not None or target_call_id is not None or not self.operations:
                raise ValueError("undo requires an earlier edit and no tool call")
            index=self._undo_plan_index(self.operations) if self.schema_version=='scene-changes-1.1' else len(self.operations)-1
            prior = replace(self,operations=self.operations[:index],
                            current_scene_revision=self.operations[index].parent_revision)
            next_plan, _ = prior.replay(source)
        elif mode == "add_many":
            if target_call_id is not None or not isinstance(tool_call, Mapping) or set(tool_call) != {"calls"}:
                raise ValueError("multi-furniture addition requires a list of calls")
            raw_calls = tool_call["calls"]
            if not isinstance(raw_calls, list) or not 2 <= len(raw_calls) <= 3:
                raise ValueError("multi-furniture addition requires two or three calls")
            new_calls = tuple(SceneToolCall.from_dict(item) for item in raw_calls)
            if (any(call.tool != "place_furniture" for call in new_calls)
                    or len({call.call_id for call in new_calls}) != len(new_calls)
                    or any(call.call_id in {item.call_id for item in plan.calls} for call in new_calls)):
                raise ValueError("multi-furniture calls must be new and distinct")
            calls = plan.calls + new_calls
            evidence = None if plan.call_evidence is None else plan.call_evidence + tuple(
                SiteCallEvidence(call.call_id, (), "user", "Explicit local multi-furniture edit")
                for call in new_calls)
            next_plan = SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                                     calls, plan_version=_edit_plan_version(plan, calls), call_evidence=evidence)
        else:
            if not isinstance(tool_call, Mapping):
                raise ValueError("typed tool call is required")
            call = SceneToolCall.from_dict(tool_call)
            if call.tool in _IMMUTABLE_TOOLS:
                raise ValueError("floor, robot and mission calls cannot be edited")
            if mode == "add":
                if target_call_id is not None or any(item.call_id == call.call_id for item in plan.calls):
                    raise ValueError("added call id must be new")
                calls = plan.calls + (call,)
            else:
                old = next((item for item in plan.calls if item.call_id == target_call_id), None)
                if old is None or old.tool in _IMMUTABLE_TOOLS or call.call_id != target_call_id:
                    raise ValueError("change must replace one editable call")
                calls = tuple(call if item.call_id == target_call_id else item for item in plan.calls)
            evidence = None if plan.call_evidence is None else tuple(
                item for item in plan.call_evidence if item.call_id != call.call_id) + (
                SiteCallEvidence(call.call_id, (), "user", "Explicit local scene edit"),)
            next_plan = SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                                     calls, plan_version=_edit_plan_version(plan, (call,)), call_evidence=evidence)
            if mode=='change' and placement is not None:
                from twinpulse_core.photo_placement import relocate_attached_children
                next_plan=relocate_attached_children(plan,next_plan,placement,target_call_id)
        next_site = _scene_from_plan(replace(source,placement_contract=placement), next_plan, site.scene.revision)
        if mode!='undo':
            from twinpulse_core.photo_placement import validate_new_nested_placement
            validate_new_nested_placement(next_plan,placement)
        before = _object_digests(site.scene)
        after = _object_digests(next_site.scene)
        targets = {key for key in before if key not in after or after[key] != before[key]}
        targets.update(set(after) - set(before))
        if mode in {"add", "add_many"} and targets & set(before):
            raise ValueError("add cannot change an existing object")
        if mode == "change" and not targets:
            raise ValueError("change did not alter any object")
        # Include only unchanged existing objects; new/changed/deleted IDs are targets.
        preserved = {key: value for key, value in before.items() if key not in targets}
        operation_value = {
            "operation_id": operation_id, "mode": mode,
            "parent_revision": site.scene.revision, "target_call_id": target_call_id,
            "tool_call": None if mode == "add_many" else tool_call,
            "expected_non_target_digests": preserved,
            "result_revision": next_site.scene.revision,
        }
        if mode == "add_many":
            operation_value["tool_calls"] = tool_call["calls"]
        operation = SceneChange.from_dict(operation_value)
        # Replay from the stored base before presenting a preview.
        self.append(source, operation)
        before_objects = {item.id: item for item in site.scene.objects}
        after_objects = {item.id: item for item in next_site.scene.objects}
        def visible(item: object) -> dict[str, object]:
            return {"position_m": list(item.transform.position_m),
                    "dimensions_m": list(item.shape.dimensions_m), "kind": item.kind}

        return {"operation": operation.to_dict(),
                "preview_digest": canonical_sha256(operation.to_dict()),
                "source_revision": self.source_scene_revision,
                "parent_revision": site.scene.revision,
                "result_revision": next_site.scene.revision,
                "affected_before": {key: visible(before_objects[key]) for key in sorted(targets & set(before))},
                "affected_after": {key: visible(after_objects[key]) for key in sorted(targets & set(after))},
                "preserved_object_count": len(preserved), "review_required": True,
                "physical_validation": "NOT_RUN"}

    def append(self, source: SiteDraftRecord, operation: SceneChange) -> "SceneChangeHistory":
        if len(self.operations) >= _MAX_OPERATIONS or any(
            item.operation_id == operation.operation_id for item in self.operations
        ):
            raise ValueError("scene change history limit or duplicate operation id")
        if self.schema_version=='scene-changes-1.2' or operation.mode=='dependency':
            updated = replace(self,schema_version='scene-changes-1.2',operations=self.operations+(operation,),
                current_scene_revision=operation.result_revision)
            updated.effective(source)
            return updated
        plan, site = self.replay(source)
        plans = [source.plan]
        for index,item in enumerate(self.operations):
            undo_plan=(plans[self._undo_plan_index(self.operations[:index])]
                       if item.mode=='undo' and self.schema_version=='scene-changes-1.1' else None)
            plans.append(self._plan_after(source, plans, item,undo_plan))
        undo_plan=(plans[self._undo_plan_index(self.operations)]
                   if operation.mode=='undo' and self.schema_version=='scene-changes-1.1' else None)
        _, next_site = self._apply_one(source, plan, site, plans, operation,undo_plan)
        return replace(self, operations=self.operations + (operation,),
                       current_scene_revision=next_site.scene.revision)

    def _dependency_preview(self,source,operation_id,mode,raw,target):
        if target is not None or mode=='undo' and raw is not None:
            raise ValueError('dependency patch or Undo requires no legacy target')
        state = self.effective(source)
        if mode=='dependency':
            updated, affected = apply_patch_state(source,state,raw,state.site.scene.revision,candidate_compile=True)
            from twinpulse_core.photo_placement import validate_new_nested_placement
            validate_new_nested_placement(updated.plan,updated.placement)
        else:
            index = self._undo_plan_index(self.operations)
            prior = replace(self,operations=self.operations[:index],
                current_scene_revision=self.operations[index].parent_revision)
            old = prior.effective(source)
            updated = EffectiveScene(old.plan,_compile(source,old.plan,old.placement,state.site.scene.revision),
                deepcopy(old.placement),deepcopy(old.inventory))
            affected = set(state.inventory)
        before,after = _object_digests(state.site.scene),_object_digests(updated.site.scene)
        changed = {k for k in before if before[k]!=after.get(k)} | set(after)-set(before)
        if (state.plan==updated.plan and state.placement==updated.placement and state.inventory==updated.inventory):
            raise ValueError('dependency patch did not alter any state')
        preserved = _preserved_geometry(state,affected) if mode=='dependency' else {k:v for k,v in before.items() if k not in changed}
        value = dict(operation_id=operation_id,mode=mode,parent_revision=state.site.scene.revision,
            target_call_id=None,tool_call=None,expected_non_target_digests=preserved,
            result_revision=updated.site.scene.revision)
        if mode=='dependency':
            value.update(dependency_patch=checked_patch(raw),parent_state_sha256=self.state_sha256(state),
                result_state_sha256=self.state_sha256(updated),expected_non_target_inventory_digests={
                    k:canonical_sha256(v) for k,v in state.inventory.items() if k not in affected})
        else:
            value.update(parent_state_sha256=self.state_sha256(state),result_state_sha256=self.state_sha256(updated))
        operation = SceneChange.from_dict(value)
        self.append(source,operation)
        def visible(items):
            return {o.id:dict(position_m=list(o.transform.position_m),dimensions_m=list(o.shape.dimensions_m),kind=o.kind)
                    for o in items if o.id in changed}
        return dict(operation=operation.to_dict(),preview_digest=canonical_sha256(operation.to_dict()),
            source_revision=self.source_scene_revision,parent_revision=state.site.scene.revision,
            result_revision=updated.site.scene.revision,parent_state_sha256=self.state_sha256(state),
            result_state_sha256=self.state_sha256(updated),affected_before=visible(state.site.scene.objects),
            affected_after=visible(updated.site.scene.objects),preserved_object_count=len(preserved),
            inventory_changes=[dict(id=i,before=deepcopy(state.inventory.get(i)),after=deepcopy(updated.inventory.get(i)))
                for i in sorted(set(state.inventory)|set(updated.inventory)) if state.inventory.get(i)!=updated.inventory.get(i)],
            review_required=True,physical_validation='NOT_RUN')

    @staticmethod
    def _plan_after(source: SiteDraftRecord, plans: list[SiteToolPlan],
                    operation: SceneChange,undo_plan: SiteToolPlan | None = None) -> SiteToolPlan:
        if operation.mode == "undo":
            return undo_plan if undo_plan is not None else plans[-2]
        plan = plans[-1]
        if operation.mode == "add_many":
            evidence = None if plan.call_evidence is None else plan.call_evidence + tuple(
                SiteCallEvidence(call.call_id, (), "user", "Explicit local multi-furniture edit")
                for call in operation.tool_calls)
            return SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                                plan.calls + operation.tool_calls, plan_version=_edit_plan_version(plan, plan.calls + operation.tool_calls), call_evidence=evidence)
        call = operation.tool_call
        assert call is not None
        calls = (plan.calls + (call,) if operation.mode == "add" else tuple(
            call if item.call_id == operation.target_call_id else item for item in plan.calls))
        evidence = None if plan.call_evidence is None else tuple(
            item for item in plan.call_evidence if item.call_id != call.call_id) + (
            SiteCallEvidence(call.call_id, (), "user", "Explicit local scene edit"),)
        result=SiteToolPlan(plan.scene_id, plan.summary, plan.image_observations,
                           calls, plan_version=_edit_plan_version(plan, (call,)), call_evidence=evidence)
        if operation.mode=='change' and source.placement_contract is not None:
            from twinpulse_core.photo_placement import relocate_attached_children
            result=relocate_attached_children(plan,result,source.placement_contract,operation.target_call_id)
        return result


def admit_new_scene_change(source,history,operation):
    """New submission boundary only; old journals/duplicate commits stay replayable."""
    if operation.mode=='undo':return
    from twinpulse_core.photo_placement import validate_new_nested_placement
    state=history.effective(source)
    validate_new_nested_placement(state.plan,state.placement)
    if operation.mode=='dependency':
        added={e['target_id'] for e in operation.dependency_patch['edits'] if e['action']=='add'}
    elif operation.mode=='add':
        added={operation.tool_call.arguments['id']} if operation.tool_call else set()
    elif operation.mode=='add_many':added={c.arguments['id'] for c in operation.tool_calls}
    else:added=set()
    from twinpulse_core.model_recipe import recipe_reuse_problem,checked_assembly,compiled_parts
    for call in state.plan.calls:
        if call.arguments['id'] not in added or call.tool!='place_model_recipe':continue
        args=call.arguments;problem=recipe_reuse_problem(args['recipe'])
        if problem:raise ValueError('SCENE_EDIT_RECIPE_REUSE_INVALID: '+problem)
        checked_assembly(compiled_parts(args['recipe'],args['parameters']),args['parameters'])


class SceneChangeStore:
    """Atomic sidecar with compare-and-swap; original project JSON is untouched."""

    def __init__(self, path: Path, *, project_id: str, source: SiteDraftRecord,
                 project_store: object | None = None):
        self.path = Path(path)
        self.project_id = project_id
        self.source = SiteDraftRecord.from_dict(source.to_dict())
        self.project_store = project_store

    def load(self) -> SceneChangeHistory:
        if self.path.is_symlink():
            raise ValueError("scene change sidecar cannot be a link")
        if not self.path.exists():
            return SceneChangeHistory.empty(self.project_id, self.source)
        with self.path.open("rb") as stream:
            data = stream.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("scene change sidecar exceeds 2 MiB")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
        return SceneChangeHistory.from_dict(value, self.source, self.project_id)

    def apply(self, operation: Mapping[str, Any], preview_digest: str) -> SceneChangeHistory:
        checked = SceneChange.from_dict(operation)
        if preview_digest != canonical_sha256(checked.to_dict()):
            raise ValueError("scene change preview differs from request")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        owner={'schema_version':'scene-change-lock-1.0','project_id':self.project_id,
            'source_sha256':canonical_sha256(self.source.to_dict()),'operation_id':checked.operation_id,
            'preview_digest':preview_digest,'pid':os.getpid(),'process_identity':_process_identity(os.getpid()),
            'owner_nonce':uuid4().hex}
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(json.dumps(owner,separators=(',',':')).encode('utf-8'))
            stream.flush();os.fsync(stream.fileno())
        temporary = self.path.with_name(self.path.name + ".tmp-" + uuid4().hex)
        try:
            if self.project_store is not None:
                current_project = self.project_store.load()
                if (current_project is None or current_project.project_id != self.project_id
                        or current_project.site_draft != self.source):
                    raise ValueError("saved original project changed before scene edit")
            current = self.load()
            for prior in current.operations:
                if prior.operation_id == checked.operation_id:
                    if prior == checked:
                        return current
                    raise ValueError("operation id was used for a different edit")
            updated = current.append(self.source, checked)
            admit_new_scene_change(self.source,updated,checked)
            data = json.dumps(updated.to_dict(), ensure_ascii=False, separators=(",", ":"),
                              allow_nan=False).encode("utf-8")
            if len(data) > _MAX_BYTES:
                raise ValueError("scene change sidecar exceeds 2 MiB")
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            return updated
        finally:
            if temporary.exists():
                temporary.unlink()
            if json.loads(lock.read_text(encoding='utf-8'))!=owner:
                raise ValueError('scene lock owner changed')
            lock.unlink()

    def recover_interrupted_lock(self,operation,preview_digest):
        """Only a journal-matched dead owner may release a crash lock.

        Legacy empty, linked, unknown/live-owner and foreign locks remain intact.
        No timestamp-only expiry or automatic retry is permitted.
        """
        lock=self.path.with_name(self.path.name+'.lock')
        if not lock.exists():return False
        if lock.is_symlink() or lock.stat().st_size>4096:raise ValueError('scene lock cannot be safely recovered')
        raw=lock.read_bytes()
        try:owner=json.loads(raw)
        except ValueError:raise ValueError('legacy or invalid scene lock requires explicit storage repair') from None
        checked=SceneChange.from_dict(operation)
        if (not isinstance(owner,dict) or set(owner)!={'schema_version','project_id','source_sha256',
                'operation_id','preview_digest','pid','process_identity','owner_nonce'} or
                owner['schema_version']!='scene-change-lock-1.0' or owner['project_id']!=self.project_id or
                owner['source_sha256']!=canonical_sha256(self.source.to_dict()) or
                owner['operation_id']!=checked.operation_id or owner['preview_digest']!=preview_digest or
                type(owner['pid']) is not int or owner['pid']<=0 or
                not isinstance(owner['owner_nonce'],str) or len(owner['owner_nonce'])!=32):
            raise ValueError('scene lock does not belong to the retained transaction')
        identity=_process_identity(owner['pid'])
        if identity is not None and identity==owner['process_identity']:
            raise ValueError('scene lock owner is still alive')
        if lock.read_bytes()!=raw:raise ValueError('scene lock changed during recovery')
        lock.unlink()
        return True


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate scene change JSON field")
        result[key] = value
    return result
