# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned room props and conservative keepouts, not measured geometry."""
from datetime import datetime
from math import cos, radians, sin

from .models import SceneObject, ShapeSpec, Transform
from .scene_tools import SceneToolPlanError, _number, _object_id, _positive_vector, _vector

from .room_item_catalog import room_item_catalog_version, PARTS as _PARTS
_ENTANGLEMENT = {'clothing_pile', 'hanging_clothes', 'bedding_overhang', 'cable_bundle', 'floor_covering','surface_covering'}
_DECOR = {'monitor', 'tabletop_item', 'window_blind', 'ceiling_light'}
KEEP_OUT_MARGIN_M = .10


def room_item_kinds():
    return tuple(_PARTS)


def checked_room_item(args):
    fields = {'id', 'kind', 'label', 'catalog_version', 'position_m', 'dimensions_m',
              'yaw_deg', 'observation_time_utc'}
    # Optional presentation colour (2026-10-26: photo-based upgrade). Display only: it never
    # changes geometry, collision or any hash of items that do not carry it.
    if not isinstance(args, dict) or set(args) - {'display_color'} != fields:
        raise SceneToolPlanError('ROOM_ITEM_ARGUMENTS_INVALID')
    if 'display_color' in args and not _valid_display_color(args['display_color']):
        raise SceneToolPlanError('ROOM_ITEM_DISPLAY_COLOR_INVALID')
    _object_id(args['id'], maximum_length=42)
    if not isinstance(args['kind'], str) or args['kind'] not in _PARTS or args['catalog_version'] != room_item_catalog_version(args['kind']):
        raise SceneToolPlanError('ROOM_ITEM_CATALOG_UNSUPPORTED')
    if not isinstance(args['label'], str) or not 1 <= len(args['label'].strip()) <= 120:
        raise SceneToolPlanError('ROOM_ITEM_LABEL_INVALID')
    position = _vector(args['position_m'], 3, 'position_m')
    size = _positive_vector(args['dimensions_m'], 3, 'dimensions_m', maximum=10.)
    if args['kind']=='surface_covering' and size[2]>min(.20,min(size[:2])*.5):
        raise SceneToolPlanError('ROOM_SURFACE_COVER_NOT_THIN')
    if position[2] - size[2]/2 < -1e-6:
        raise SceneToolPlanError(f"ROOM_ITEM_BELOW_FLOOR: id={args['id']}, "
            f"position_z_m={position[2]}, minimum_centre_z_m={size[2]/2}; "
            "position_m is the geometric centre, not the bottom")
    _number(args['yaw_deg'], 'yaw_deg', minimum=-180., maximum=180.)
    stamp = args['observation_time_utc']
    if stamp is not None:
        if not isinstance(stamp, str) or len(stamp) > 40:
            raise SceneToolPlanError('ROOM_ITEM_TIME_INVALID')
        try:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
                raise ValueError()
        except ValueError as error:
            raise SceneToolPlanError('ROOM_ITEM_TIME_INVALID') from error
    return args


def room_item_risk(args):
    checked_room_item(args)
    kind = args['kind']
    if kind == 'unknown':
        return 'unknown'
    if kind in _ENTANGLEMENT:
        return 'entanglement'
    # A monitor or small prop on the floor must not become non-blocking decoration.
    if kind in _DECOR and args['position_m'][2]-args['dimensions_m'][2]/2 >= .5:
        return 'visual_only'
    return 'collision'


def _valid_display_color(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(v) in (int, float) and 0. <= v <= 1. for v in value))


def display_color_tag(color):
    """Presentation-only colour carried in the optional asset_id slot: 'color:r,g,b' (0-1)."""
    return 'color:%.3f,%.3f,%.3f' % tuple(float(v) for v in color)


def parse_display_color_tag(asset_id):
    if not isinstance(asset_id, str) or not asset_id.startswith('color:'):
        return None
    try:
        parts = [float(v) for v in asset_id[6:].split(',')]
    except ValueError:
        return None
    return tuple(parts) if len(parts) == 3 and all(0. <= v <= 1. for v in parts) else None


def expand_room_item(args):
    checked_room_item(args)
    risk = room_item_risk(args)
    # Validators accept JSON integer numbers too. Persisted SceneObject readers
    # decode geometry as floats; emit that same representation BEFORE hashing.
    # Input/tool-plan bytes and canonical_sha256 are deliberately unchanged.
    sx, sy, sz = _positive_vector(args['dimensions_m'], 3, 'dimensions_m', maximum=10.)
    px, py, pz = _vector(args['position_m'], 3, 'position_m')
    yaw = _number(args['yaw_deg'], 'yaw_deg', minimum=-180., maximum=180.)
    angle = radians(yaw); c, s = cos(angle), sin(angle)
    objects = []
    for i, (x, y, z, dx, dy, dz) in enumerate(_PARTS[args['kind']]):
        x, y = x*sx, y*sy
        objects.append(SceneObject(f"{args['id']}_visual_{i}", 'equipment',
            Transform((px+x*c-y*s, py+x*s+y*c, pz-sz/2+z*sz), (0., 0., yaw)),
            ShapeSpec('box', (dx*sx, dy*sy, dz*sz)), collision=risk == 'collision',
            asset_id=display_color_tag(args['display_color']) if args.get('display_color') else None))
    if risk in {'entanglement', 'unknown'}:
        # Deliberately synthetic blocking envelope, not a scan return or real volume.
        objects.append(SceneObject(f"{args['id']}_keepout", 'equipment',
            Transform((px, py, .175), (0., 0., yaw)),
            ShapeSpec('box', (sx+2*KEEP_OUT_MARGIN_M, sy+2*KEEP_OUT_MARGIN_M, .35))))
    return tuple(objects)


def validate_room_item_bounds(objects, floor, *, owners=None):
    fx, fy, _ = floor.transform.position_m
    fw, fl = floor.shape.dimensions_m[:2]
    for item in objects:
        angle = radians(item.transform.rotation_rpy_deg[2]); sx, sy = item.shape.dimensions_m[:2]
        hx = (abs(cos(angle))*sx+abs(sin(angle))*sy)/2
        hy = (abs(sin(angle))*sx+abs(cos(angle))*sy)/2
        x, y = item.transform.position_m[:2]
        if abs(x-fx)+hx > fw/2+1e-6 or abs(y-fy)+hy > fl/2+1e-6:
            from .geometry_diagnostics import geometry_issue,geometry_report
            error=SceneToolPlanError('ROOM_ITEM_OUTSIDE_FLOOR')
            # Exact expansion ownership, not splitting or guessing source IDs.
            identity=(owners or {}).get(item.id,item.id)
            error.code='ROOM_ITEM_OUTSIDE_FLOOR'
            error.contract_report=geometry_report([geometry_issue(error.code,identity,
                actual={'generated_part_id':item.id,'position_m':list(item.transform.position_m),
                        'dimensions_m':list(item.shape.dimensions_m),'rotated_half_extent_m':[hx,hy]},
                expected={'floor_center_m':[fx,fy],'floor_size_m':[fw,fl],
                    'allowed_center_x_m':[fx-fw/2+hx,fx+fw/2-hx],
                    'allowed_center_y_m':[fy-fl/2+hy,fy+fl/2-hy],'unit':'m'},
                related_ids=['$room'],violation=max(abs(x-fx)+hx-fw/2,abs(y-fy)+hy-fl/2))])
            raise error


def room_inventory(plan, scene):
    """Derive metadata from persisted calls and current geometry, never a live scan."""
    by_id = {o.id: o for o in scene.objects}
    evidence = {e.call_id: e for e in plan.call_evidence or ()}
    rows = []
    for call in plan.calls:
        if call.tool not in {'place_room_item', 'place_furniture','create_rack_row','place_pallet_stack','place_model_recipe'}:
            continue
        args = call.arguments
        from .furniture import expand_furniture
        from .scene_tools import SceneToolRegistry
        from .warehouse_models import parent_kind
        expected = (expand_room_item(dict(args)) if call.tool == 'place_room_item' else expand_furniture(args)
            if call.tool == 'place_furniture' else SceneToolRegistry().execute_static_tool(call.tool,args))
        members = [by_id[o.id] for o in expected if o.id in by_id]
        ev = evidence.get(call.call_id)
        kind=parent_kind(args)
        rows.append(dict(id=args['id'], label=args.get('label',args.get('recipe',{}).get('title',kind.replace('_', ' '))),
            kind=kind, risk=room_item_risk(dict(args)) if call.tool == 'place_room_item' else
                'unknown' if kind=='unknown' else 'collision',
            basis=ev.basis if ev else 'unprovided', observation_ids=list(ev.observation_ids) if ev else [],
            last_observation_utc=args.get('observation_time_utc'),
            placement_status='represented' if len(members) == len(expected) and all(
                by_id[o.id].collision == o.collision for o in expected) else 'missing',
            geometry=[dict(id=o.id, position_m=list(o.transform.position_m), dimensions_m=list(o.shape.dimensions_m),
                           yaw_deg=o.transform.rotation_rpy_deg[2], collision=o.collision,
                           synthetic_keepout=o.id.endswith('_keepout')) for o in members]))
    return dict(schema_version='room-inventory-1.0', scene_revision=scene.revision, source=scene.source,
                source_ref=scene.source_ref, live_observation=False, physical_validation='NOT_RUN', items=rows)
