# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Typed semantic adapters to the existing warehouse factories, not new wire tools.

Rack sizes are nominal length/depth/height; actual posts/shelves may extend
beyond them. Pallet-stack height is the existing stack_height_m, above its base.
Packing/ceiling checks use expanded geometry, never only nominal dimensions.
"""
import math

WAREHOUSE_KINDS = ('rack', 'pallet_stack')
PARAMETERS = {'rack': {'bay_count': (1, 8), 'level_count': (1, 5)},
              'pallet_stack': {'stack_levels': (1, 4)}}
RANGES = {'rack': ((.8, .35, .5), (10., 2.5, 6.)),
          'pallet_stack': ((0., 0., .15), (2.5, 2.5, 3.))}


def warehouse_arguments(item, center):
    """Reject unsupported semantics before lowering; no implicit rotation/levels."""
    kind = item['kind']; size = item['dimensions_m']; params = item.get('warehouse_parameters')
    if kind not in WAREHOUSE_KINDS:
        raise ValueError('PHOTO_WAREHOUSE_KIND_UNSUPPORTED')
    low, high = RANGES[kind]
    if (not isinstance(size, list) or len(size) != 3 or any(type(v) not in (int, float)
            or not math.isfinite(v) or not 0 < v <= high[i] or v < low[i] for i, v in enumerate(size))):
        raise ValueError('PHOTO_WAREHOUSE_DIMENSIONS_INVALID')
    if (not isinstance(params, dict) or set(params) != set(PARAMETERS[kind])
            or any(type(params[k]) is not int or not bounds[0] <= params[k] <= bounds[1]
                   for k, bounds in PARAMETERS[kind].items())):
        raise ValueError('PHOTO_WAREHOUSE_PARAMETERS_INVALID')
    if type(item.get('yaw_deg')) not in (int, float) or item['yaw_deg'] != 0:
        raise ValueError('PHOTO_WAREHOUSE_ROTATION_UNSUPPORTED')
    base = dict(id=item['id'], center_m=list(center))
    if kind == 'rack':
        return 'create_rack_row', dict(**base, length_m=size[0], depth_m=size[1],
            height_m=size[2], **params)
    return 'place_pallet_stack', dict(**base, footprint_m=list(size[:2]),
        stack_height_m=size[2], **params)


def warehouse_parts(item, center=(0., 0.)):
    from .scene_tools import SceneToolRegistry
    tool, args = warehouse_arguments(item, center)
    return tuple(SceneToolRegistry().execute_static_tool(tool, args))


def support_parts(kind, relation='surface', parameters=None):
    """Single source for model grammar and saved-plan relationship validation."""
    if relation == 'drape':
        return {'bed': ('base','mattress','headboard'), 'wardrobe': ('body',),
            'storage': ('body',), 'desk': ('top',), 'dining_table': ('top',),
            'chair': ('seat','back'), 'sofa': ('seat','back'),
            'clothes_rack': ('body',), 'office_chair': ('body',)}.get(kind, ())
    if kind == 'rack':
        count = (parameters or {}).get('level_count', 5)
        return tuple('shelf_'+str(i) for i in range(1, count+1))
    if kind == 'pallet_stack':
        # The base is already occupied by this factory's cargo. Only the actual
        # uppermost cargo surface is available; NEVER attach through the cargo.
        return ('stack_top',)
    return {'bed': ('base','mattress','headboard'), 'wardrobe': ('body',),
        'storage': ('body',), 'desk': ('top',), 'dining_table': ('top',),
        'chair': ('seat','back'), 'sofa': ('seat','back'), 'pallet': ('deck',),
        'box': ('top',), 'tabletop_item': ('top',)}.get(kind, ())


def warehouse_surface(parent, part):
    from .scene_tools import SceneToolRegistry
    if 'length_m' in parent:
        tool = 'create_rack_row'; kind = 'rack'; params = {'level_count': parent['level_count']}
        suffix = part
    elif 'stack_height_m' in parent:
        tool = 'place_pallet_stack'; kind = 'pallet_stack'; params = None
        suffix = 'box_'+str(parent['stack_levels']) if part == 'stack_top' else None
    else:
        return None
    if part not in support_parts(kind, parameters=params): return None
    return next((obj for obj in SceneToolRegistry().execute_static_tool(tool, parent)
                 if obj.id == parent['id']+'_'+str(suffix)), None)


def parent_kind(arguments):
    if 'length_m' in arguments and 'level_count' in arguments: return 'rack'
    if 'stack_height_m' in arguments and 'stack_levels' in arguments: return 'pallet_stack'
    return arguments.get('kind')


def parent_yaw(arguments):
    return arguments.get('yaw_deg', 0.)
