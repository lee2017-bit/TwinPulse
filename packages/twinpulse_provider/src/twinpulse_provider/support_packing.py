# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded repacking on the same selected surface, not a measured safe map."""
import math
import time

from twinpulse_core.photo_quality import support_geometry, support_surface
from twinpulse_core.warehouse_models import parent_yaw


def grid_indices(lower, upper, *, scale=20):
    # Roundoff at an exact grid boundary must not eliminate a valid zero slot.
    # 1e-9 grid units is <= 5e-11m, not extra physical clearance or resizing.
    return range(math.ceil(lower * scale - 1e-9), math.floor(upper * scale + 1e-9) + 1)


def bounded_support_repack(items, parent, part, *, max_nodes=512, timeout_s=2.,
                           branch_cap=32, max_geometry_checks=65536, clock=None):
    """Undo this compile's greedy choices, preserving every size/parent/part.

    Every domain point passes the existing 3D support checker; siblings retain
    the same .025m gap and .01m edge inset. Search limits are explicit and a
    failure never proves global infeasibility. No saved artifact is edited.
    """
    if (type(max_nodes) is not int or max_nodes < 0 or type(branch_cap) is not int or branch_cap < 1
            or type(max_geometry_checks) is not int or max_geometry_checks < 0
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s < 0
            or not isinstance(items, list) or not 1 <= len(items) <= 32
            or len({item['id'] for item in items}) != len(items)):
        raise ValueError('PHOTO_SUPPORT_SEARCH_BUDGET_INVALID')
    clock = clock or time.perf_counter
    started = clock(); deadline = started + timeout_s
    surface = support_surface(parent, part)
    domains = {}; sizes = {}; probes = {}; nodes = ticks = pruned = truncated = 0
    halt = None; phase = 'domain_generation'; complete = False
    def report(found, code):
        return dict(schema_version='photo-support-bounded-search-1.0',
            status='FOUND' if found else 'BOUNDED_SEARCH_FAILED', termination_code=code,
            parent_id=parent['id'], part=part, nodes=nodes, max_nodes=max_nodes,
            geometry_checks=ticks, max_geometry_checks=max_geometry_checks,
            timeout_s=timeout_s, branch_cap=branch_cap, branches_truncated=truncated,
            overlap_pruned=pruned, phase=phase, domain_generation_complete=complete,
            domain_counts={identity: len(points) for identity, points in domains.items()},
            elapsed_s=max(0., clock() - started), global_infeasibility_proved=False,
            scope='SAME_SELECTED_SURFACE_GRID_NOT_MEASURED_FREE_SPACE', physical_authority=False)
    if surface is None:
        return None, report(False, 'SUPPORT_SURFACE_UNAVAILABLE')
    px, py, pz = surface.transform.position_m
    sx, sy, sz = surface.shape.dimensions_m
    angle = math.radians(parent_yaw(parent)); co, si = math.cos(angle), math.sin(angle)
    for item in sorted(items, key=lambda row: row['id']):
        identity = item['id']; size = item['dimensions_m']
        relative = math.radians(item['yaw_deg'] - parent_yaw(parent))
        hx = (abs(math.cos(relative))*size[0] + abs(math.sin(relative))*size[1])/2
        hy = (abs(math.sin(relative))*size[0] + abs(math.cos(relative))*size[1])/2
        sizes[identity] = hx, hy; points = []
        for ix in grid_indices(-sx/2+hx+.01, sx/2-hx-.01):
            for iy in grid_indices(-sy/2+hy+.01, sy/2-hy-.01):
                if ticks >= max_geometry_checks or clock() > deadline:
                    return None, report(False, 'GEOMETRY_CHECK_BUDGET_EXHAUSTED'
                        if ticks >= max_geometry_checks else 'TIME_BUDGET_EXHAUSTED')
                ticks += 1; lx, ly = ix/20, iy/20
                probe = dict(id=identity, kind=item['kind'], label=item['kind'],
                    catalog_version='room-items-1.0', position_m=[px+lx*co-ly*si, py+lx*si+ly*co, pz+sz/2+size[2]/2],
                    dimensions_m=list(size), yaw_deg=item['yaw_deg'], observation_time_utc=None)
                if support_geometry(probe, parent, part)['status'] == 'PASS':
                    # Edge-first fallback avoids the centre-first greedy trap.
                    points.append((-(lx*lx+ly*ly), lx, ly))
                    probes[identity, lx, ly] = probe
        domains[identity] = [(x, y) for _, x, y in sorted(points)]
    complete = True
    if any(not points for points in domains.values()):
        return None, report(False, 'EMPTY_VALID_DOMAIN')
    phase = 'backtracking'
    def search(remaining, chosen):
        nonlocal nodes, halt, pruned, truncated
        if not remaining:
            return chosen
        if clock() > deadline or nodes >= max_nodes:
            halt = 'TIME_BUDGET_EXHAUSTED' if clock() > deadline else 'NODE_BUDGET_EXHAUSTED'
            return None
        nodes += 1; options = []
        for identity in remaining:
            hx, hy = sizes[identity]; available = []
            for x, y in domains[identity]:
                if clock() > deadline:
                    halt = 'TIME_BUDGET_EXHAUSTED'; return None
                if all(abs(x-px) >= hx+sizes[other][0]+.025-1e-9
                       or abs(y-py) >= hy+sizes[other][1]+.025-1e-9
                       for other, (px, py) in chosen.items()):
                    available.append((x, y))
                else:
                    pruned += 1
            if not available:
                return None
            options.append((len(available), -hx*hy, identity, available))
        _, _, identity, available = min(options)
        if len(available) > branch_cap:
            truncated += 1
        for point in available[:branch_cap]:
            found = search(tuple(i for i in remaining if i != identity), {**chosen, identity: point})
            if found is not None:
                return found
            if halt:
                break
        return None
    found = search(tuple(sorted(domains)), {})
    code = 'FOUND' if found is not None else halt or ('BRANCH_BUDGET_EXHAUSTED' if truncated else 'GRID_SEARCH_EXHAUSTED')
    return (None if found is None else {identity: probes[identity, *point] for identity, point in found.items()}), report(found is not None, code)
