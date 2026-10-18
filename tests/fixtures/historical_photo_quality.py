# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Archived v349 test reference. NEVER import from product generation code.
"""Evidence-bound geometry checks, not model self-acceptance or measured fidelity.

The reviewed constraints are additive: old inventory, Site2.2 and raw response
contracts are unchanged. Unknown photos get UNVERIFIED, never borrowed P01 rules.
"""
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
import re

from twinpulse_core.furniture import expand_furniture, furniture_kinds
from twinpulse_core.room_item_catalog import ROOM_ITEM_KINDS
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.room_items import expand_room_item
from tests.fixtures.historical_room_photo_inventory import PHOTO_ITEMS, PHOTO_SHA256
from twinpulse_core.site_tools import SiteToolPlan, execute_site_tool_plan

QUALITY_REVISION = 'photo-geometry-quality-1.0'
XY_TOLERANCE_M = .015
Z_TOLERANCE_M = .02


@dataclass(frozen=True)
class PhotoGeometryConstraints:
    image_sha256: str
    required_items: tuple[tuple[str, str], ...]
    positions: tuple[tuple[str, str, str], ...]
    supports: tuple[tuple[str, str, str], ...]
    uncovered_relations: tuple[str, ...]
    source: str = 'human_review_of_user_photo'
    max_estimated_area_m2: float | None = None
    floor_items: tuple[str, ...] = ()
    attachments: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()

    def to_dict(self):
        result = dict(schema_version='reviewed-photo-geometry-1.0',
            image_sha256=self.image_sha256, source=self.source,
            coordinate_frame='entry_view_x_right_y_rear_z_up',
            required_items=[dict(id=i, kind=k) for i, k in self.required_items],
            positions=[dict(id=i, axis=a, expected=s) for i, a, s in self.positions],
            supports=[dict(id=i, parent=p, part=s) for i, p, s in self.supports],
            uncovered_relations=list(self.uncovered_relations),
            metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS')
        if self.max_estimated_area_m2 is not None or self.floor_items or self.attachments:
            result.update(schema_version='reviewed-photo-geometry-1.1',
                review_revision='photo-semantic-review-1.0',
                estimated_area_review_limit_m2=self.max_estimated_area_m2,
                scale_basis='unmeasured_photo_plausibility_review_not_a_measurement',
                floor_items=list(self.floor_items),
                attachments=[dict(id=i, relation='drape',
                    allowed_parents=[dict(parent=p, part=s) for p,s in choices])
                    for i,choices in self.attachments])
        return result


from twinpulse_core.photo_quality import PhotoGeometryConstraints


def reviewed_photo_constraints(image_sha256, *, semantic_review=False):
    if image_sha256 != PHOTO_SHA256:
        return None
    constraints = PhotoGeometryConstraints(PHOTO_SHA256,
        tuple((i, k) for i, _, k, _, _ in PHOTO_ITEMS),
        (('bed', 'x', 'right'), ('desk', 'x', 'left'),
         ('desk', 'y', 'rear'), ('wardrobe', 'y', 'rear')),
        (('top_storage', 'wardrobe', 'body'), ('monitor', 'desk', 'top'),
         ('tabletop_items', 'desk', 'top')),
        ('hanging clothing attachment', 'open door hinge', 'bedding attachment',
         'uncertain small floor objects', 'hidden surfaces', 'bed depth'))
    if not semantic_review:
        return constraints
    from dataclasses import replace
    return replace(constraints,
        positions=(*constraints.positions, ('wardrobe', 'x', 'right'),
            ('wood_frame','x','left'),('floor_fan','x','left'),
            ('office_chair','x','left'),('office_chair','y','rear'),
            ('entry_door','x','left'),('entry_door','y','front'),
            ('cables','x','right'),('cables','y','front'),
            ('power_adapter','x','right'),('power_adapter','y','front'),
            ('basket','x','left'),('basket','y','front')),
        # This is a conservative review threshold, NOT a measured room size.
        # Explicit trusted dimensions are handled separately by the provider.
        max_estimated_area_m2=30.,
        floor_items=('clothing_pile','floor_bags','underdesk_bag','boxes','basket',
                     'cables','power_adapter','power_strip','small_equipment'),
        attachments=(('bedding_overhang', (('bed','mattress'),)),
            ('hanging_clothes', (('wardrobe','body'),('wood_frame','body'),('office_chair','body')))),
        uncovered_relations=('exact clothing distribution and fabric shape', 'open door hinge',
                            'uncertain small floor objects', 'hidden surfaces', 'bed depth',
                            'fine relative distances and unmeasured metric scale'))


def checked_constraints(constraints, image_sha256):
    """Only host-supplied reviewed constraints may enter; never LLM verdicts."""
    if not isinstance(constraints, PhotoGeometryConstraints):
        raise ValueError('PHOTO_CONSTRAINTS_INVALID')
    if (constraints.image_sha256 != image_sha256
            or not re.fullmatch('[0-9a-f]{64}', image_sha256)
            or constraints.source != 'human_review_of_user_photo'):
        raise ValueError('PHOTO_CONSTRAINTS_EVIDENCE_MISMATCH')
    ids = [i for i, _ in constraints.required_items]
    if not ids or len(ids) > 32 or len(set(ids)) != len(ids):
        raise ValueError('PHOTO_CONSTRAINTS_ITEMS_INVALID')
    for identity, kind in constraints.required_items:
        if (not isinstance(identity, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,31}', identity)
                or kind not in (*furniture_kinds(), *ROOM_ITEM_KINDS)):
            raise ValueError('PHOTO_CONSTRAINTS_ITEMS_INVALID')
    if (len(constraints.uncovered_relations) > 12 or any(not isinstance(s, str) or len(s) > 120
            for s in constraints.uncovered_relations)):
        raise ValueError('PHOTO_CONSTRAINTS_UNCERTAINTY_INVALID')
    if len(constraints.positions) > 32 or len(constraints.supports) > 32:
        raise ValueError('PHOTO_CONSTRAINTS_LIMIT')
    for i, axis, expected in constraints.positions:
        if i not in ids or (axis, expected) not in {('x', 'left'), ('x', 'right'),
                                                   ('y', 'front'), ('y', 'rear')}:
            raise ValueError('PHOTO_CONSTRAINTS_POSITION_INVALID')
    children = set()
    for child, parent, part in constraints.supports:
        if (child not in ids or parent not in ids or child == parent or child in children
                or parent in {c for c, _, _ in constraints.supports}
                or not re.fullmatch('[a-z_]{1,32}', part)):
            raise ValueError('PHOTO_CONSTRAINTS_SUPPORT_GRAPH_INVALID')
        children.add(child)
    area=constraints.max_estimated_area_m2
    if area is not None and (type(area) not in (int,float) or not isfinite(area) or not 0<area<=200):
        raise ValueError('PHOTO_CONSTRAINTS_SCALE_INVALID')
    if (len(constraints.floor_items)>32 or len(set(constraints.floor_items))!=len(constraints.floor_items)
            or any(i not in ids for i in constraints.floor_items) or len(constraints.attachments)>16):
        raise ValueError('PHOTO_CONSTRAINTS_SEMANTIC_INVALID')
    attached=set()
    for child,choices in constraints.attachments:
        if (child not in ids or child in attached or child in constraints.floor_items
                or not choices or len(choices)>8):
            raise ValueError('PHOTO_CONSTRAINTS_SEMANTIC_INVALID')
        for parent,part in choices:
            if parent not in ids or parent==child or not re.fullmatch('[a-z_]{1,32}',part):
                raise ValueError('PHOTO_CONSTRAINTS_SEMANTIC_INVALID')
        attached.add(child)
    return constraints


def support_surface(parent, part):
    return next((o for o in expand_furniture(parent) if o.id == parent['id']+'_'+part), None)


def support_geometry(child, parent, part):
    """Check every emitted child part in the parent's rotated support frame."""
    surface = support_surface(parent, part)
    if surface is None:
        raise ValueError('PHOTO_SUPPORT_SURFACE_MISSING')
    pieces = [o for o in expand_room_item(dict(child)) if not o.id.endswith('_keepout')]
    px, py, pz = surface.transform.position_m
    sx, sy, sz = surface.shape.dimensions_m
    parent_yaw = surface.transform.rotation_rpy_deg[2]
    angle = radians(parent_yaw); co, si = cos(angle), sin(angle)
    inside = True
    bounds = []
    for piece in pieces:
        x, y, _ = piece.transform.position_m
        dx, dy, _ = piece.shape.dimensions_m
        local_x, local_y = co*(x-px)+si*(y-py), -si*(x-px)+co*(y-py)
        relative = radians(piece.transform.rotation_rpy_deg[2]-parent_yaw)
        hx = (abs(cos(relative))*dx+abs(sin(relative))*dy)/2
        hy = (abs(sin(relative))*dx+abs(cos(relative))*dy)/2
        bounds.append((local_x-hx, local_x+hx, local_y-hy, local_y+hy))
        inside &= (abs(local_x)+hx <= sx/2+XY_TOLERANCE_M
                   and abs(local_y)+hy <= sy/2+XY_TOLERANCE_M)
    bottom = min(o.transform.position_m[2]-o.shape.dimensions_m[2]/2 for o in pieces)
    gap = bottom-(pz+sz/2)
    return dict(xy_contained=bool(inside), bottom_to_support_top_gap_m=round(gap, 6),
                support_bounds_xy_m=[min(b[0] for b in bounds), max(b[1] for b in bounds),
                                     min(b[2] for b in bounds), max(b[3] for b in bounds)],
                status='PASS' if inside and abs(gap) <= Z_TOLERANCE_M else 'FAIL')


def inspect_photo_geometry(payload, image_sha256, constraints=None, *, support_repairable=False):
    """Full local diagnostic. PASS applies only to explicitly checked relations.

    Plan execution validates finite geometry/IDs/bounds first. It is pure core
    execution, not Isaac or physical execution. Model descriptions are ignored.
    """
    plan = SiteToolPlan.from_dict(payload)
    draft = execute_site_tool_plan(plan, source='photo', source_ref=image_sha256)
    floor = next(c.arguments for c in plan.calls if c.tool == 'create_floor')
    report = dict(schema_version=QUALITY_REVISION, photo_sha256=image_sha256,
        plan_sha256=canonical_sha256(payload), status='UNVERIFIED',
        checked_relation_status='UNVERIFIED', metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS',
        full_photo_reconstruction='UNVERIFIED', physical_validation='NOT_RUN',
        room_estimate_m=list(floor['size_m']), room_center_m=list(floor['center_m']),
        estimated_area_m2=float(floor['size_m'][0]*floor['size_m'][1]),
        large_room_scale_warning=floor['size_m'][0]*floor['size_m'][1] > 30,
        issues=[], checks=[], uncovered_relations=[], repairable=False,
        generation_allowed=True, source='NO_REVIEWED_REFERENCE')
    constraints = constraints or reviewed_photo_constraints(image_sha256)
    if constraints is None:
        return report
    checked_constraints(constraints, image_sha256)
    report.update(source=constraints.source, constraints_sha256=canonical_sha256(constraints.to_dict()),
                  uncovered_relations=list(constraints.uncovered_relations))
    objects = {c.arguments['id']: dict(c.arguments) for c in plan.calls
               if c.tool in {'place_furniture', 'place_room_item'}}

    def add(code, identity, repairable, **detail):
        report['issues'].append(dict(code=code, id=identity, repairable=repairable, **detail))

    if constraints.max_estimated_area_m2 is not None or constraints.floor_items or constraints.attachments:
        report['review_revision']='photo-semantic-review-1.0'
        report['scale_review_limit_m2']=constraints.max_estimated_area_m2
    if constraints.max_estimated_area_m2 is not None:
        valid=report['estimated_area_m2']<=constraints.max_estimated_area_m2
        report['checks'].append(dict(id='floor',status='PASS' if valid else 'FAIL',
            estimated_area_m2=report['estimated_area_m2'],review_limit_m2=constraints.max_estimated_area_m2))
        if not valid:
            add('PHOTO_SCALE_REVIEW_REQUIRED','floor',True,
                estimated_area_m2=report['estimated_area_m2'],review_limit_m2=constraints.max_estimated_area_m2)

    for identity, kind in constraints.required_items:
        if identity not in objects:
            add('PHOTO_OBJECT_MISSING', identity, True, expected=kind)
        elif objects[identity]['kind'] != kind:
            add('PHOTO_KIND_MISMATCH', identity, support_repairable, expected=kind)
    for identity, axis, expected in constraints.positions:
        item = objects.get(identity)
        index = int(axis == 'y')
        value = (item.get('center_m', item.get('position_m'))[index]-floor['center_m'][index] if item else None)
        positive = expected in {'right', 'rear'}
        valid = value is not None and (value > 0 if positive else value < 0)
        report['checks'].append(dict(id=identity, axis=axis, expected=expected,
            actual_coordinate_m=value, status='PASS' if valid else 'FAIL'))
        if not valid:
            add('PHOTO_POSITION_MISMATCH', identity, True, axis=axis, expected=expected,
                actual_coordinate_m=value)
    supported_bounds = {}
    for identity in constraints.floor_items:
        child=objects.get(identity)
        valid=bool(child and 'position_m' in child and
                   abs(child['position_m'][2]-child['dimensions_m'][2]/2)<=Z_TOLERANCE_M)
        report['checks'].append(dict(id=identity,relation='floor',status='PASS' if valid else 'FAIL'))
        if not valid:add('PHOTO_FLOOR_SEMANTIC_MISMATCH',identity,True)
    if constraints.attachments:
        from twinpulse_core.photo_placement import drape_pose
        for identity,choices in constraints.attachments:
            child=objects.get(identity);valid=False
            for parent,part in choices:
                p=objects.get(parent)
                if child is None or p is None or 'position_m' not in child:continue
                for anchor in ('front','left','right','rear'):
                    try:position,yaw=drape_pose(p,part,anchor,child['dimensions_m'])
                    except ValueError:continue
                    if (max(abs(a-b) for a,b in zip(child['position_m'],position))<=Z_TOLERANCE_M
                            and abs((child['yaw_deg']-yaw+180)%360-180)<=.01):
                        valid=True
            report['checks'].append(dict(id=identity,relation='drape',status='PASS' if valid else 'FAIL'))
            if not valid:add('PHOTO_ATTACHMENT_SEMANTIC_MISMATCH',identity,True)
    for child, parent, part in constraints.supports:
        c, p = objects.get(child), objects.get(parent)
        row = dict(id=child, parent=parent, part=part, status='FAIL')
        if c and p and 'position_m' in c and 'center_m' in p:
            row.update(support_geometry(c, p, part))
            bounds = row['support_bounds_xy_m']
            previous = supported_bounds.setdefault((parent, part), [])
            for other, old in previous:
                if (bounds[0] < old[1]-1e-6 and old[0] < bounds[1]-1e-6
                        and bounds[2] < old[3]-1e-6 and old[2] < bounds[3]-1e-6):
                    row.update(status='FAIL', overlaps_sibling=other)
            previous.append((child, bounds))
        report['checks'].append(row)
        if row['status'] != 'PASS':
            # Current compact contract cannot express arbitrary height/parent.
            # The host compiler handles reviewed supports; don't burn a retry
            # if that compiler dependency is missing or defective.
            add('PHOTO_SUPPORT_MISMATCH', child, support_repairable,
                **{k: v for k, v in row.items() if k != 'id'})
    heights = [c.arguments['dimensions_m'][2] for c in plan.calls if c.tool == 'create_wall']
    if heights:
        ceiling = min(heights)
        for obj in draft.scene.objects:
            if obj.kind == 'floor' or obj.id.endswith('_wall'):
                continue
            if obj.transform.position_m[2]+obj.shape.dimensions_m[2]/2 > ceiling+Z_TOLERANCE_M:
                add('PHOTO_CEILING_INTERSECTION', obj.id, True, expected_height_m=ceiling)
    report['checked_relation_status'] = 'FAIL' if report['issues'] else 'PASS'
    report['status'] = 'FAIL' if report['issues'] else 'PARTIAL'
    report['generation_allowed'] = not report['issues']
    report['repairable'] = bool(report['issues']) and all(i['repairable'] for i in report['issues'])
    return report


def public_photo_quality(report):
    """Bounded whitelist for product failure journals; no arbitrary provider text."""
    if not isinstance(report, dict) or report.get('schema_version') != QUALITY_REVISION:
        return {}
    result = {'schema_version': QUALITY_REVISION}
    if report.get('review_revision')=='photo-semantic-review-1.0':
        result['review_revision']='photo-semantic-review-1.0'
        value=report.get('scale_review_limit_m2')
        if value is None or type(value) in (int,float) and isfinite(value) and 0<value<=200:
            result['scale_review_limit_m2']=value
    enums = dict(status={'FAIL', 'PARTIAL', 'UNVERIFIED'}, checked_relation_status={'FAIL', 'PASS', 'UNVERIFIED'},
        metric_scale_validation={'UNVERIFIED_NO_MEASUREMENTS'}, full_photo_reconstruction={'UNVERIFIED'},
        physical_validation={'NOT_RUN'}, source={'human_review_of_user_photo', 'NO_REVIEWED_REFERENCE'})
    for key, choices in enums.items():
        if isinstance(report.get(key), str) and report[key] in choices:
            result[key] = report[key]
    for key in ('photo_sha256', 'plan_sha256', 'constraints_sha256'):
        if isinstance(report.get(key), str) and re.fullmatch('[0-9a-f]{64}', report[key]):
            result[key] = report[key]
    for key in ('generation_allowed', 'repairable', 'large_room_scale_warning'):
        if type(report.get(key)) is bool:
            result[key] = report[key]
    dimensions=report.get('room_estimate_m')
    if (isinstance(dimensions, list) and len(dimensions)==2
            and all(type(v) in (float, int) and isfinite(v) and 0 < v <= 1e6 for v in dimensions)):
        result['room_estimate_m']=list(dimensions)
    area=report.get('estimated_area_m2')
    if type(area) in (float, int) and isfinite(area) and 0 < area <= 1e12:
        result['estimated_area_m2']=area
    for key in ('issues', 'checks'):
        rows = []
        for item in report.get(key, [])[:128] if isinstance(report.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            row = {}
            for field in ('id', 'parent', 'part', 'overlaps_sibling'):
                value = item.get(field)
                known={i for i, _, _, _, _ in PHOTO_ITEMS}
                suffixes={'base', 'mattress', 'headboard', 'body', 'door_left', 'door_right', 'top',
                          'leg_fl', 'leg_fr', 'leg_bl', 'leg_br', 'keepout', 'visual_0', 'visual_1', 'visual_2', 'visual_3'}
                safe_ids=known | {'floor'} | {i+'_'+s for i in known for s in suffixes}
                if isinstance(value, str) and value in (suffixes if field=='part' else safe_ids):
                    row[field] = value
            for field, choices in dict(code={'PHOTO_OBJECT_MISSING', 'PHOTO_KIND_MISMATCH',
                    'PHOTO_POSITION_MISMATCH', 'PHOTO_SUPPORT_MISMATCH', 'PHOTO_CEILING_INTERSECTION',
                    'PHOTO_REPAIR_ROOM_FRAME_CHANGED','PHOTO_SCALE_REVIEW_REQUIRED',
                    'PHOTO_FLOOR_SEMANTIC_MISMATCH','PHOTO_ATTACHMENT_SEMANTIC_MISMATCH'},
                    status={'PASS', 'FAIL'}, axis={'x', 'y'}, expected={k for _, _, k, _, _ in PHOTO_ITEMS}
                    | {'left', 'right', 'front', 'rear'}).items():
                if isinstance(item.get(field), str) and item[field] in choices:
                    row[field] = item[field]
            if item.get('relation') in {'floor','drape'}:row['relation']=item['relation']
            for field in ('actual_coordinate_m', 'bottom_to_support_top_gap_m', 'expected_height_m',
                          'estimated_area_m2','review_limit_m2'):
                value = item.get(field)
                if type(value) in (float, int) and isfinite(value):
                    row[field] = value
            for field in ('xy_contained', 'repairable'):
                if type(item.get(field)) is bool:
                    row[field] = item[field]
            for field in ('expected_size_m', 'actual_size_m', 'expected_center_m', 'actual_center_m'):
                value=item.get(field)
                if (isinstance(value,list) and len(value)==2
                        and all(type(v) in (int,float) and isfinite(v) for v in value)):
                    row[field]=list(value)
            if row:
                rows.append(row)
        result[key] = rows
    return result
