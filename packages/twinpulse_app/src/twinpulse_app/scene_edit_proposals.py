# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded, read-only context and untrusted furniture edit proposal contract.

This module never calls a provider or writes a scene. A candidate must still go
through the existing scene-change preview and explicit apply path.
"""

from __future__ import annotations

from typing import Any, Mapping
from copy import deepcopy

from twinpulse_core import canonical_sha256
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.furniture import expand_furniture
from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION

from .scene_changes import SceneChangeHistory
from .site_draft import SiteDraftRecord


CONTEXT_VERSION = "scene-edit-context-1.0"
PROPOSAL_VERSION = "scene-edit-proposal-1.0"
_FURNITURE_ARGUMENTS = {"id", "kind", "catalog_version", "center_m", "yaw_deg"}


def feedback_edit_context(project_id,source,history,request_text,selected_call_id=None):
    if not isinstance(request_text,str) or not 1<=len(request_text.strip())<=4000:
        raise ValueError('feedback text must be bounded and nonempty')
    state=history.effective(source)
    if selected_call_id is not None and selected_call_id not in {c.call_id for c in state.plan.calls}:
        raise ValueError('selected call is absent from the current scene')
    context=dict(schema_version='scene-edit-context-1.2',project_id=project_id,
        source_scene_revision=source.site.scene.revision,current_scene_revision=state.site.scene.revision,
        current_state_sha256=history.state_sha256(state),request_text=request_text.strip(),
        original_user_intent=source.input_revision.prompt,
        selected_call_id=selected_call_id,current_plan=state.plan.to_dict(),
        placement_contract=deepcopy(state.placement),inventory=list(deepcopy(state.inventory).values()),
        unresolved=deepcopy((state.progressive(source) or {}).get('unresolved',[])),
        measurement_constraints=deepcopy(list(source.input_revision.measurement_constraints)),
        boundary='Untrusted feedback proposal only. Keep source IDs, object kinds, measured constraints and all non-target objects. '
            'Use one dependency patch, not full-scene replacement. Parent edits move checked descendants atomically. '
            'Each target_id appears exactly once in this patch, using one atomic final edit. '
            'Unchanged placement and unrelated fields are preserved implicitly, not repeated as another change. '
            'Resize plus reparent uses one reparent edit with both tool_call and placement; later revisions may edit the same target again. '
            'Restore/add requires an explicit checked placement relation. Defer/remove retains source inventory and blocks unresolved tasks. '
            'Ambiguous target, relation or metric extent: ask exactly one question. No photo has been re-observed, '
            'no physical alignment or motion is approved. Preview/Apply/Undo require fresh state checks.')
    return {**context,'context_sha256':canonical_sha256(context)}


def checked_feedback_proposal(context,value):
    if (not isinstance(value,Mapping) or set(value)!={'schema_version','context_sha256','mode','explanation','patch'}
            or value['schema_version']!='scene-edit-proposal-1.1' or value['context_sha256']!=context['context_sha256']):
        raise ValueError('feedback proposal shape or current context changed')
    explanation=value['explanation']
    if not isinstance(explanation,str) or not 1<=len(explanation.strip())<=300:
        raise ValueError('feedback proposal requires a short explanation')
    if value['mode']=='clarify':
        if value['patch'] is not None or explanation.count('?')+explanation.count('？')>1:
            raise ValueError('clarification must ask one question without a patch')
        return 'clarify',None,None,explanation.strip()
    if value['mode']!='dependency':raise ValueError('feedback mode unsupported')
    from .dependency_patch import checked_patch
    from twinpulse_provider.scene_edit_provider import normalized_feedback_patch
    patch=checked_patch(normalized_feedback_patch(context,value['patch']))
    return 'dependency',None,patch,explanation.strip()


def furniture_edit_context(project_id: str, source: SiteDraftRecord,
                           history: SceneChangeHistory, request_text: str,
                           selected_call_id: str | None) -> dict[str, Any]:
    if not isinstance(request_text, str) or not 1 <= len(request_text.strip()) <= 2000:
        raise ValueError("edit request text is required and must be at most 2000 characters")
    if selected_call_id is not None and not isinstance(selected_call_id, str):
        raise ValueError("selected call id must be text or null")
    plan, site = history.replay(source)
    furniture = [call for call in plan.calls if call.tool == "place_furniture"]
    if selected_call_id is not None and selected_call_id not in {call.call_id for call in furniture}:
        raise ValueError("selected furniture is absent from the current saved revision")
    context = {
        "schema_version": 'scene-edit-context-1.1' if source.placement_contract is not None else CONTEXT_VERSION,
        "project_id": project_id,
        "source_scene_revision": source.site.scene.revision,
        "current_scene_revision": site.scene.revision,
        "request_text": request_text.strip(),
        "selected_call_id": selected_call_id,
        "furniture_calls": [call.to_dict() for call in furniture],
        "scene_objects": [{"id": item.id, "kind": item.kind,
                           "position_m": list(item.transform.position_m),
                           "dimensions_m": list(item.shape.dimensions_m)}
                          for item in site.scene.objects],
        **({'placement_contract':deepcopy(source.placement_contract)} if source.placement_contract is not None else {}),
        "boundary": ("Proposal only. An explicitly declared support/attachment follows a parent edit atomically; "
                    "do not detach its children or shrink a parent below their fit. " if source.placement_contract is not None else 'Proposal only. ')+
                    "Do not replace the full scene, floor, robot or mission; "
                    "do not infer measurements from an unexamined photo. Explicit preview/apply is required.",
    }
    return {**context, "context_sha256": canonical_sha256(context)}


def checked_furniture_proposal(context: Mapping[str, Any], value: Mapping[str, Any]) -> tuple[str, str | None, dict | None, str]:
    """Return scene-change preview arguments; reject full-scene or wrong-target output."""
    if not isinstance(value, Mapping) or set(value) != {
            "schema_version", "context_sha256", "mode", "explanation", "target_call_id", "tool_call"}:
        raise ValueError("edit proposal shape is unsupported")
    if value["schema_version"] != PROPOSAL_VERSION or value["context_sha256"] != context["context_sha256"]:
        raise ValueError("edit proposal belongs to a different context")
    explanation = value["explanation"]
    if not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 300:
        raise ValueError("edit proposal needs a short explanation")
    mode, target, raw = value["mode"], value["target_call_id"], value["tool_call"]
    if mode == "clarify":
        if target is not None or raw is not None:
            raise ValueError("clarification cannot contain a scene change")
        return "clarify", None, None, explanation.strip()
    if mode not in {"add_furniture", "change_furniture"} or not isinstance(raw, Mapping):
        raise ValueError("only one furniture add or change is supported")
    call = SceneToolCall.from_dict(raw)
    if call.tool != "place_furniture":
        raise ValueError("proposal must be one catalog furniture call")
    expand_furniture(call.arguments)
    furniture = {item["call_id"]: item for item in context["furniture_calls"]}
    if mode == "add_furniture":
        if target is not None or call.call_id in furniture:
            raise ValueError("added furniture requires a new call and no target")
        return "add", None, call.to_dict(), explanation.strip()
    selected = context["selected_call_id"]
    if selected is None or target != selected or target not in furniture or call.call_id != target:
        raise ValueError("change must address the explicitly selected saved furniture")
    old = furniture[target]["arguments"]
    upgrading = old['catalog_version']=='furniture-blocks-1.0' and call.arguments['catalog_version']==PARAMETRIC_FURNITURE_VERSION
    if (any(call.arguments[key] != old[key] for key in ("id", "kind")) or
            (call.arguments['catalog_version'] != old['catalog_version'] and not upgrading)):
        raise ValueError("change may move or rotate the selected furniture, not replace its identity")
    return "change", target, call.to_dict(), explanation.strip()
