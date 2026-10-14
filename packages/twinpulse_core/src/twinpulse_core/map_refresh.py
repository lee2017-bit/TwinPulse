# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Conservative scratch-grid overlay after one reviewed XY edit.

Never frees cells or infers free space from missing rays. Adds all supplied static
box AABBs before AND after the edit. This is not SLAM or a complete map rebuild.
"""
from dataclasses import dataclass, replace
import math

from .revisions import canonical_sha256
from .route_comparison import comparison_conditions
from .scan_correction import apply_xy_correction, plan_revision, undo_xy_correction
from .site_contracts import SitePlan

POLICY = "conservative_static_box_overlay_v1"
MAX_CELL_WRITES = 200_000
EPS = 1e-9


def _bounds(obj):
    if obj.dynamic or obj.shape.type != "box" or any(abs(v) > EPS for v in obj.transform.rotation_rpy_deg[:2]):
        raise ValueError("map overlay supports static upright boxes only")
    x, y, _ = obj.transform.position_m
    hx, hy = (v / 2 for v in obj.shape.dimensions_m[:2])
    yaw = math.radians(obj.transform.rotation_rpy_deg[2])
    dx = abs(math.cos(yaw)) * hx + abs(math.sin(yaw)) * hy
    dy = abs(math.sin(yaw)) * hx + abs(math.cos(yaw)) * hy
    return x - dx, y - dy, x + dx, y + dy


@dataclass(frozen=True)
class MapRefreshProposal:
    parent_plan_revision: str
    edit_revision: str
    prior_map_revision: str
    prior_mission_revision: str
    candidate: SitePlan
    added_occupied_cells: int
    checked_cells: int

    @property
    def revision(self):
        return canonical_sha256({"policy": POLICY, "parent": self.parent_plan_revision,
            "edit": self.edit_revision, "prior_map": self.prior_map_revision,
            "prior_mission": self.prior_mission_revision, "candidate": plan_revision(self.candidate),
            "added_occupied_cells": self.added_occupied_cells, "checked_cells": self.checked_cells})

    def preview(self):
        grid, mission = self.candidate.navigation_map, self.candidate.mission
        return {"revision": self.revision, "policy": POLICY, "scene_revision": self.candidate.scene.revision,
                "map_revision": grid.revision, "mission_revision": mission.revision,
                "prior_map_revision": self.prior_map_revision, "added_occupied_cells": self.added_occupied_cells,
                "free_cells": grid.cells.count(0), "unknown_cells": grid.cells.count(-1),
                "occupied_cells": grid.cells.count(100), "start_xy_m": mission.start.position_m[:2],
                "goal_xy_m": mission.goal.position_m[:2], "freed_cells": 0,
                "source_verified": False, "execution_authorized": False, "review_required": True,
                "notice": "Conservative overlay only. Old obstacles retained, no free-space inference. Same endpoints rebound for offline geometry, not execution."}


def propose_map_refresh(current, applied, recording, profile):
    SitePlan.from_dict(current.to_dict())
    if plan_revision(current) != plan_revision(applied.after):
        raise ValueError("map overlay requires the exact corrected scratch plan")
    fresh = apply_xy_correction(applied.before, recording, applied.proposal,
                               reviewed_proposal_revision=applied.proposal.revision)
    if fresh.revision != applied.revision:
        raise ValueError("inconsistent correction receipt")
    comparison_conditions(applied.before, profile)  # Validate original bindings and planar mission.
    grid, mission = applied.before.navigation_map, applied.before.mission
    floors = [obj for obj in current.scene.objects if obj.kind == "floor"]
    if len(floors) != 1 or any(abs(v) > EPS for v in floors[0].transform.rotation_rpy_deg):
        raise ValueError("one axis-aligned floor required for map overlay")
    fx0, fy0, fx1, fy1 = _bounds(floors[0])
    ox, oy = grid.origin_xy_m
    resolution = grid.resolution_m
    if (ox < fx0 - EPS or oy < fy0 - EPS or ox + grid.width * resolution > fx1 + EPS
            or oy + grid.height * resolution > fy1 + EPS):
        raise ValueError("supplied grid extends beyond floor bounds")
    cells = list(grid.cells)
    checked = 0
    # Deduplicate identical footprints; retain both locations of the edited object.
    bounds = sorted({_bounds(obj) for scene in (applied.before.scene, current.scene)
                     for obj in scene.objects if obj.kind != "floor" and obj.collision})
    for x0, y0, x1, y1 in bounds:
        c0 = max(0, math.floor((x0 - ox - EPS) / resolution))
        c1 = min(grid.width - 1, math.floor((x1 - ox + EPS) / resolution))
        r0 = max(0, math.floor((y0 - oy - EPS) / resolution))
        r1 = min(grid.height - 1, math.floor((y1 - oy + EPS) / resolution))
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                checked += 1
                if checked > MAX_CELL_WRITES:
                    raise ValueError("map overlay cell budget exceeded")
                cells[row * grid.width + col] = 100
    overlay = replace(grid, scene_revision=current.scene.revision, cells=tuple(cells), source="scene",
                      source_ref=canonical_sha256({"policy": POLICY, "prior_map": grid.revision, "edit": applied.revision}))
    rebound = replace(mission, scene_revision=current.scene.revision, map_revision=overlay.revision)
    candidate = replace(current, navigation_map=overlay, mission=rebound, review_required=True)
    comparison_conditions(candidate, profile)
    added = sum(old != 100 and new == 100 for old, new in zip(grid.cells, cells))
    return MapRefreshProposal(plan_revision(current), applied.revision, grid.revision, mission.revision,
                              candidate, added, checked)


def apply_map_refresh(current, applied, recording, profile, proposal, *, reviewed_revision):
    if not isinstance(proposal, MapRefreshProposal) or reviewed_revision != proposal.revision:
        raise ValueError("review of the exact map and mission overlay required")
    fresh = propose_map_refresh(current, applied, recording, profile)
    if proposal.revision != fresh.revision:
        raise ValueError("map overlay proposal changed")
    return fresh.candidate


def undo_refreshed_correction(current, applied, refreshed, *, reviewed_edit_revision):
    if (plan_revision(current) != plan_revision(refreshed.candidate)
            or refreshed.parent_plan_revision != plan_revision(applied.after)
            or refreshed.edit_revision != applied.revision):
        raise ValueError("stale refreshed correction undo")
    # Discard only this server-owned overlay; ordinary undo validates all geometry
    # and emits a NEW scene revision without map/mission/previous approvals.
    return undo_xy_correction(replace(current, navigation_map=None, mission=None, review_required=True),
                              applied, reviewed_edit_revision=reviewed_edit_revision)
