# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite floor candidates with the existing margins, regions and object bounds.

Grid choices retain their old ordering. Domain ends and contact boundaries cover
legal narrow intervals between ticks; they do not prove global feasibility.
"""
import math


def floor_candidates(bounds, width, length, region, placed=(), *, max_points=32768):
    xmin, xmax = -width/2-bounds[0]+.11, width/2-bounds[1]-.11
    ymin, ymax = -length/2-bounds[2]+.11, length/2-bounds[3]-.11
    row, col = region.split('_')
    if col == 'left': xmax = min(xmax, -.05)
    elif col == 'right': xmin = max(xmin, .05)
    else: xmin, xmax = max(xmin, -width/6), min(xmax, width/6)
    if row == 'front': ymax = min(ymax, -.05)
    elif row == 'rear': ymin = max(ymin, .05)
    else: ymin, ymax = max(ymin, -length/6), min(ymax, length/6)
    if xmin > xmax or ymin > ymax:
        return
    xs = {i/10 for i in range(math.ceil(xmin*10), math.floor(xmax*10)+1)}
    ys = {i/10 for i in range(math.ceil(ymin*10), math.floor(ymax*10)+1)}
    count=0
    for x in sorted(xs):
        for y in sorted(ys):
            count+=1
            if count>max_points:raise ValueError('PHOTO_LAYOUT_CANDIDATE_BUDGET_EXHAUSTED')
            yield 0, x, y
    extra_x, extra_y = {xmin, xmax}, {ymin, ymax}
    for _, px, py, other in placed:
        # Outward epsilon preserves, rather than subtracts from, the .03 gap.
        extra_x.update((px+other[0]-.03-bounds[1]-1e-9,
                        px+other[1]+.03-bounds[0]+1e-9))
        extra_y.update((py+other[2]-.03-bounds[3]-1e-9,
                        py+other[3]+.03-bounds[2]+1e-9))
    extra_x = {x for x in extra_x if xmin <= x <= xmax}-xs
    extra_y = {y for y in extra_y if ymin <= y <= ymax}-ys
    for x in sorted(xs|extra_x):
        for y in sorted(ys|extra_y):
            if x in extra_x or y in extra_y:
                count+=1
                if count>max_points:raise ValueError('PHOTO_LAYOUT_CANDIDATE_BUDGET_EXHAUSTED')
                yield 1, x, y
