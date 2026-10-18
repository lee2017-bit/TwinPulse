# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ephemeral typed appearance bound to an exact checked generation scene.

This carries catalog parameters, not code, file paths or motion authority.
Both broker and engine recheck it; a partial scene need not be committed first.
"""
from copy import deepcopy
import json

from .revisions import canonical_sha256
from .site_tools import SiteToolPlan, execute_site_tool_plan

KIND = 'generation_room_visual_v1'


def checked_generation_visual(value, scene, project_id):
    if (type(value) is not dict or set(value) !=
            {'kind', 'project_id', 'scene_revision', 'plan_sha256', 'plan'}
            or value['kind'] != KIND or value['project_id'] != project_id
            or value['scene_revision'] != scene.revision):
        raise ValueError('GENERATION_VISUAL_BINDING_INVALID')
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 2*1024*1024:
        raise ValueError('GENERATION_VISUAL_MEMORY_BUDGET')
    plan = SiteToolPlan.from_dict(value['plan'])
    if canonical_sha256(plan.to_dict()) != value['plan_sha256']:
        raise ValueError('GENERATION_VISUAL_PLAN_CHANGED')
    if any(call.tool in {'place_predefined_agv', 'create_navigation_task'} for call in plan.calls):
        raise ValueError('GENERATION_VISUAL_MOTION_FORBIDDEN')
    expected = execute_site_tool_plan(plan, source=scene.source, source_ref=scene.source_ref).scene
    if expected.to_dict() != scene.to_dict():
        raise ValueError('GENERATION_VISUAL_SCENE_CHANGED')
    return plan


def generation_visual(plan, scene, project_id):
    value = dict(kind=KIND, project_id=project_id, scene_revision=scene.revision,
                 plan_sha256=canonical_sha256(plan.to_dict()), plan=deepcopy(plan.to_dict()))
    checked_generation_visual(value, scene, project_id)
    return value
