# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded 2-D candidate planning for explicitly synthetic or verified maps.

This module only returns geometric waypoints. It never arms or commands a robot.
An unknown cell must be represented as blocked by the caller; this planner
cannot establish whether a photo-derived room is physically traversable.
"""
import heapq
import math


class NoBoundedPath(ValueError):
    pass


def route_footprint_cells(start,route,*,clearance=.266,cell_size_m=.10):
    """Fixed dependency set for an already checked, bounded route.

    Unknown/occupied changes in any intersecting cell invalidate the route.
    Unrelated far ray-raster changes cannot affect its swept footprint.
    """
    if not _finite_pair(start) or not 1<=len(route)<=16 or any(not _finite_pair(p) for p in route):
        raise ValueError('ROUTE_DEPENDENCY_SHAPE')
    result=set();a=start
    for b in route:
        steps=max(1,math.ceil(math.dist(a,b)/.025))
        if steps>1000:raise ValueError('ROUTE_DEPENDENCY_BUDGET')
        for n in range(steps+1):
            x=a[0]+(b[0]-a[0])*n/steps;y=a[1]+(b[1]-a[1])*n/steps
            for ix in range(math.floor((x-clearance)/cell_size_m),math.floor((x+clearance)/cell_size_m)+1):
                for iy in range(math.floor((y-clearance)/cell_size_m),math.floor((y+clearance)/cell_size_m)+1):
                    dx=max(ix*cell_size_m-x,0.,x-(ix+1)*cell_size_m)
                    dy=max(iy*cell_size_m-y,0.,y-(iy+1)*cell_size_m)
                    if math.hypot(dx,dy)<=clearance:result.add((ix,iy))
            if len(result)>18000:raise ValueError('ROUTE_DEPENDENCY_BUDGET')
        a=b
    return tuple(sorted(result))


def observed_dependency_revision(dependencies,rows,cell_size_m=.10):
    from .revisions import canonical_sha256
    states={}
    for row in rows:
        cell=tuple(math.floor(v/cell_size_m) for v in row[:2])
        states[cell]=row[2] if cell not in states or states[cell]==row[2] else 'unknown'
    return canonical_sha256([[*cell,states.get(cell,'unknown')] for cell in dependencies])


def _finite_pair(value):
    return (type(value) in (tuple, list) and len(value) == 2
            and all(type(item) in (int, float) and math.isfinite(item) for item in value))


def plan_bounded_grid(start, goal, bounds, boxes=(), discs=(), *, resolution=.05,
                      clearance=.30, max_cells=10000, max_expansions=8000,
                      max_waypoints=16, observed_cells=None, cell_size_m=.10, checked_route=None,
                      allow_direct_over_grid_budget=False):
    """A* with inflated obstacles, fixed budgets and collision-checked segments.

    Boxes are (cx, cy, half_x, half_y, yaw_rad); discs are (cx, cy, radius).
    The returned tuple excludes start and includes the exact goal. A diagonal
    never cuts across a blocked corner. No path is a terminal, explicit result.
    """
    if (not _finite_pair(start) or not _finite_pair(goal)
            or type(bounds) not in (tuple, list) or len(bounds) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds)
            or not all(type(v) in (int, float) and math.isfinite(v) for v in (resolution, clearance))
            or not .02 <= resolution <= .20 or not .10 <= clearance <= 1.
            or type(max_cells) is not int or not 1 <= max_cells <= 10000
            or type(max_expansions) is not int or not 1 <= max_expansions <= 10000
            or type(max_waypoints) is not int or not 1 <= max_waypoints <= 16
            or type(allow_direct_over_grid_budget) is not bool):
        raise ValueError('GRID_PLAN_INPUT_INVALID')
    xmin, xmax, ymin, ymax = bounds
    if not xmin < xmax or not ymin < ymax:
        raise ValueError('GRID_PLAN_BOUNDS_INVALID')
    if (type(boxes) not in (tuple, list) or len(boxes) > 128
            or type(discs) not in (tuple, list) or len(discs) > 128):
        raise ValueError('GRID_PLAN_OBSTACLES_INVALID')
    for box in boxes:
        if (type(box) not in (tuple, list) or len(box) != 5
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                or min(box[2:4]) <= 0):
            raise ValueError('GRID_PLAN_BOX_INVALID')
    for disc in discs:
        if (type(disc) not in (tuple, list) or len(disc) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in disc)
                or disc[2] < 0):
            raise ValueError('GRID_PLAN_DISC_INVALID')
    nx = math.ceil((xmax - xmin) / resolution) + 1
    ny = math.ceil((ymax - ymin) / resolution) + 1
    over_grid_budget = nx * ny > max_cells
    if over_grid_budget and not allow_direct_over_grid_budget:
        raise NoBoundedPath('GRID_BUDGET_EXCEEDED')
    known = None
    if observed_cells is not None:
        if (not isinstance(observed_cells, list) or len(observed_cells)>18000
                or type(cell_size_m) not in (int,float) or not math.isfinite(cell_size_m)
                or not .02<=cell_size_m<=.20):raise ValueError('OBSERVED_GRID_INVALID')
        known={}
        for row in observed_cells:
            if (not isinstance(row,list) or len(row)!=7 or not _finite_pair(row[:2])
                    or row[2] not in {'free','occupied','unknown'}):raise ValueError('OBSERVED_GRID_INVALID')
            key=tuple(math.floor(v/cell_size_m) for v in row[:2])
            if key in known and known[key]!=row[2]:known[key]='unknown'
            else:known[key]=row[2]

    def clear(point):
        x, y = point
        if not (xmin + clearance <= x <= xmax - clearance
                and ymin + clearance <= y <= ymax - clearance):
            return False
        if known is not None:
            # Require the entire conservative envelope to be observed free.
            # A cell touching the circle is included; absent/conflicting=blocked.
            for ix in range(math.floor((x-clearance)/cell_size_m),math.floor((x+clearance)/cell_size_m)+1):
                for iy in range(math.floor((y-clearance)/cell_size_m),math.floor((y+clearance)/cell_size_m)+1):
                    dx=max(ix*cell_size_m-x,0.,x-(ix+1)*cell_size_m)
                    dy=max(iy*cell_size_m-y,0.,y-(iy+1)*cell_size_m)
                    if math.hypot(dx,dy)<=clearance and known.get((ix,iy))!='free':return False
        for cx, cy, hx, hy, yaw in boxes:
            co, si = math.cos(yaw), math.sin(yaw)
            dx, dy = x - cx, y - cy
            local_x, local_y = co * dx + si * dy, -si * dx + co * dy
            gap_x = max(abs(local_x) - hx, 0.)
            gap_y = max(abs(local_y) - hy, 0.)
            if math.hypot(gap_x, gap_y) <= clearance:
                return False
        # Escape corridor (2026-10-26 physical recovery): after a proximity stop the
        # robot backs off only 25 cm, so its own position is still inside the keepout
        # disc's clearance band and no path could start. Within one clearance of the
        # start, a keepout disc blocks only its own radius (plus 5 cm); walls, boxes
        # and unknown cells keep the full clearance.
        margin = clearance if math.hypot(x - start[0], y - start[1]) > clearance else .05
        return all(math.hypot(x - cx, y - cy) > radius + margin
                   for cx, cy, radius in discs)

    def line_clear(a, b):
        count = max(1, math.ceil(math.dist(a, b) / (resolution / 2)))
        if count > 10000:
            raise NoBoundedPath('SEGMENT_CHECK_BUDGET_EXCEEDED')
        return all(clear((a[0] + (b[0] - a[0]) * i / count,
                          a[1] + (b[1] - a[1]) * i / count))
                   for i in range(count + 1))

    if not clear(start) or not clear(goal):
        raise NoBoundedPath('START_OR_GOAL_BLOCKED')
    if checked_route is not None:
        # Validate immutable reviewed waypoints using the SAME inflated
        # envelope/unknown rules. Never substitute a newly searched route.
        if (type(checked_route) not in (list,tuple) or not 1<=len(checked_route)<=max_waypoints
                or any(not _finite_pair(p) for p in checked_route)
                or math.dist(checked_route[-1],goal)>1e-12):
            raise ValueError('REVIEWED_ROUTE_INVALID')
        previous=start
        for point in checked_route:
            if not line_clear(previous,point):raise NoBoundedPath('REVIEWED_ROUTE_BLOCKED')
            previous=point
        # Rigid-transform round trips can differ at floating-point precision.
        # Check even that final numerical gap; never alter reviewed waypoints
        # or admit a geometrically different endpoint.
        if not line_clear(previous,goal):raise NoBoundedPath('REVIEWED_ROUTE_BLOCKED')
        return tuple(tuple(p) for p in checked_route)
    if line_clear(start, goal):
        return (tuple(goal),)
    # Explicit SIM callers may validate a direct segment on a large estimated
    # floor without allocating/searching its grid. Full floor, obstacles and
    # unknown-cell rules above still apply. Never expand the A* budget, crop
    # away obstacles, or change the default used by physical planning.
    if over_grid_budget:
        raise NoBoundedPath('GRID_BUDGET_EXCEEDED')

    def cell(point):
        return (round((point[0] - xmin) / resolution),
                round((point[1] - ymin) / resolution))

    def xy(index):
        return (xmin + index[0] * resolution, ymin + index[1] * resolution)

    def connectors(point):
        # A clear exact endpoint need not have a clear nearest grid cell. The
        # fixed 3x3 neighborhood is checked using the SAME inflated/unknown
        # envelope and endpoint segment predicate, never an unchecked snap.
        nearest = cell(point)
        candidates = ((nearest[0]+dx, nearest[1]+dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        return {index:math.dist(point, xy(index)) for index in candidates
            if 0<=index[0]<nx and 0<=index[1]<ny and clear(xy(index)) and line_clear(point, xy(index))}

    origins, targets = connectors(start), connectors(goal)
    if not origins or not targets:
        raise NoBoundedPath('SNAPPED_ENDPOINT_BLOCKED')
    # One multi-source search shares the original global expansion budget;
    # there is no per-entry/exit retry or 81-fold search allowance.
    frontier = [(cost+math.dist(xy(origin), goal), cost, origin) for origin,cost in origins.items()]
    heapq.heapify(frontier)
    best = dict(origins)
    previous = {}
    expansions = 0
    target = None
    directions = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
    while frontier:
        _, cost, current = heapq.heappop(frontier)
        if cost != best.get(current):
            continue
        if current in targets:
            target = current
            break
        expansions += 1
        if expansions > max_expansions:
            raise NoBoundedPath('SEARCH_BUDGET_EXCEEDED')
        for dx, dy in directions:
            neighbor = current[0] + dx, current[1] + dy
            if not (0 <= neighbor[0] < nx and 0 <= neighbor[1] < ny and clear(xy(neighbor))):
                continue
            if dx and dy and (not clear(xy((current[0] + dx, current[1])))
                              or not clear(xy((current[0], current[1] + dy)))):
                continue
            proposed = cost + math.hypot(dx, dy) * resolution
            if proposed < best.get(neighbor, math.inf):
                best[neighbor] = proposed
                previous[neighbor] = current
                heapq.heappush(frontier, (proposed + math.dist(xy(neighbor), goal),
                                          proposed, neighbor))
    if target is None:
        raise NoBoundedPath('NO_PATH')
    cells = [target]
    while cells[-1] in previous:
        cells.append(previous[cells[-1]])
    points = [tuple(start), *map(xy, reversed(cells)), tuple(goal)]
    compact = []
    index = 0
    while index < len(points) - 1:
        if not line_clear(points[index], points[index + 1]):
            raise NoBoundedPath('GRID_EDGE_BLOCKED')
        farthest = index + 1
        for candidate in range(index + 2, len(points)):
            if line_clear(points[index], points[candidate]):
                farthest = candidate
        compact.append(points[farthest])
        index = farthest
        if len(compact) > max_waypoints:
            raise NoBoundedPath('WAYPOINT_BUDGET_EXCEEDED')
    return tuple(compact)
