# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit SIM-only execution binding. Does not change v1/v2 scene serialization."""
from __future__ import annotations

import math

from .bounded_grid_plan import plan_bounded_grid
from .revisions import canonical_sha256
from .site_contracts import SceneRevision


def xy(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in value)):
        raise ValueError("SIM_COORDINATE_INVALID")
    return tuple(float(v) for v in value)


def geometry(scene):
    floors = [o for o in scene.objects if o.kind == 'floor']
    if len(floors) != 1 or floors[0].shape.type != 'box' or not floors[0].collision:
        raise ValueError('SIM_SINGLE_COLLIDING_FLOOR_REQUIRED')
    floor = floors[0]
    if any(abs(v) > 1e-6 for v in floor.transform.rotation_rpy_deg):
        raise ValueError('SIM_AXIS_ALIGNED_FLOOR_REQUIRED')
    x, y, z = floor.transform.position_m
    dx, dy, dz = floor.shape.dimensions_m
    bounds = (x-dx/2, x+dx/2, y-dy/2, y+dy/2)
    boxes, discs = [], []
    for obj in scene.objects:
        if obj.dynamic:
            raise ValueError('SIM_DYNAMIC_SCENE_UNSUPPORTED')
        if obj is floor or not obj.collision:
            continue
        if any(abs(v) > 1e-6 for v in obj.transform.rotation_rpy_deg[:2]):
            raise ValueError('SIM_TILTED_OBSTACLE_UNSUPPORTED')
        cx, cy = obj.transform.position_m[:2]
        if obj.shape.type == 'box':
            boxes.append((cx, cy, obj.shape.dimensions_m[0]/2, obj.shape.dimensions_m[1]/2,
                          math.radians(obj.transform.rotation_rpy_deg[2])))
        else:
            discs.append((cx, cy, obj.shape.dimensions_m[0]))
    return bounds, tuple(boxes), tuple(discs), z+dz/2


def make_plan(scene, start, goal, asset_files, *, yaw_rad=0.0):
    scene = SceneRevision.from_dict(scene.to_dict())
    start, goal = xy(start), xy(goal)
    if math.dist(start, goal) < .10:
        raise ValueError('SIM_GOAL_TOO_CLOSE')
    if type(yaw_rad) not in (int, float) or not math.isfinite(yaw_rad) or abs(yaw_rad) > math.pi:
        raise ValueError('SIM_YAW_INVALID')
    if (type(asset_files) is not dict or not asset_files or len(asset_files) > 32
            or any(not isinstance(k, str) or k.startswith('/') or '..' in k.split('/')
                   or not isinstance(v, str) or len(v) != 64
                   or any(c not in '0123456789abcdef' for c in v) for k, v in asset_files.items())):
        raise ValueError('SIM_ASSET_INVENTORY_INVALID')
    bounds, boxes, discs, floor_top = geometry(scene)
    route = plan_bounded_grid(start, goal, bounds=bounds, boxes=boxes, discs=discs,
                             resolution=.10, clearance=.22, max_waypoints=16,
                             allow_direct_over_grid_budget=True)
    body = dict(schema_version='site-simulation-1.0', mode='SIM', scene_revision=scene.revision,
                asset_id='turtlebot3_burger', asset_files=dict(asset_files),
                start=list(start), goal=list(goal), yaw_rad=float(yaw_rad),
                spawn_z_m=floor_top+.002, route=[list(p) for p in route],
                max_linear_mps=.15, max_angular_rps=.6, tolerance_m=.04,
                max_sim_time_s=120., physical_authority=False)
    return {**body, 'plan_id': canonical_sha256(body)}


def checked_plan(scene, value):
    if type(value) is not dict:
        raise ValueError('SIM_PLAN_INVALID')
    if value.get('schema_version')=='site-goal-demonstration-1.0':
        from .goal_simulation import checked_goal_simulation
        return checked_goal_simulation(scene,value)
    expected = make_plan(scene, value.get('start'), value.get('goal'), value.get('asset_files'),
                         yaw_rad=value.get('yaw_rad'))
    if value != expected:
        raise ValueError('SIM_PLAN_CHANGED_OR_STALE')
    return expected


def waypoint_command(position, yaw, target, *, tolerance=.04):
    """Closed-loop rotate then translate. All values are simulation observations."""
    position, target = xy(position), xy(target)
    if not math.isfinite(yaw):
        raise ValueError('SIM_POSE_INVALID')
    distance = math.dist(position, target)
    if distance <= tolerance:
        return 0., 0., True
    error = math.atan2(target[1]-position[1], target[0]-position[0])-yaw
    error = math.atan2(math.sin(error), math.cos(error))
    angular = max(-.6, min(.6, 2.*error))
    linear = min(.15, .8*distance) if abs(error) < .15 else 0.
    return linear, angular, False
