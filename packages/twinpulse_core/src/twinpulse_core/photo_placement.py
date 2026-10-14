# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Estimated placement sidecar for new photo drafts; never motion authority.

Ordinary Site2.2 geometry/wire contracts are unchanged. This bounded, explicit
sidecar lets save/reopen/edit validate relationships without importing providers.
Legacy drafts without it keep their original semantics and hashes.
"""
from copy import deepcopy
from math import cos, sin, radians, isfinite
import re

from .photo_quality import support_geometry, support_surface
from .warehouse_models import support_parts, parent_kind, parent_yaw

PLACEMENT_VERSION='photo-placement-contract-1.0'
_ID=re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,31}\Z')
_FIELDS={'id','relation','parent_id','part','anchor','elevation_m'}


def placement_contract_from_trace(trace):
    if not isinstance(trace,dict) or trace.get('contract') not in ('photo-layout-1.2','photo-layout-1.3'):return None
    rows=trace.get('model_parameters')
    if not isinstance(rows,list):raise ValueError('PHOTO_PLACEMENT_TRACE_INVALID')
    return dict(schema_version=PLACEMENT_VERSION,relations=[dict(id=i['id'],**i['placement']) for i in rows])


def checked_placement_contract(value):
    from .scene_resources import check_scene_payload
    check_scene_payload(value)
    if (not isinstance(value,dict) or set(value)!={'schema_version','relations'}
            or value['schema_version'] not in {PLACEMENT_VERSION,'photo-placement-contract-1.1'} or not isinstance(value['relations'],list)
            or len(value['relations'])<(0 if value['schema_version']=='photo-placement-contract-1.1' else 1)):raise ValueError('PHOTO_PLACEMENT_CONTRACT_INVALID')
    identities=set()
    for row in value['relations']:
        if (not isinstance(row,dict) or set(row)!=_FIELDS or not isinstance(row['id'],str)
                or not _ID.fullmatch(row['id']) or row['id'] in identities
                or not isinstance(row['relation'],str) or row['relation'] not in {'floor','surface','drape','wall','ceiling'}
                or not isinstance(row['anchor'],str) or row['anchor'] not in {'centre','front','left','right','rear'}
                or any(v is not None and (not isinstance(v,str) or not _ID.fullmatch(v))
                       for v in (row['parent_id'],row['part']))
                or row['elevation_m'] is not None and (type(row['elevation_m']) not in (int,float)
                    or not isfinite(row['elevation_m']) or not 0<=row['elevation_m']<=4)):
            raise ValueError('PHOTO_PLACEMENT_RELATION_INVALID')
        identities.add(row['id'])
    rows={r['id']:r for r in value['relations']}
    for identity,row in rows.items():
        if row['relation'] in {'surface','drape'} and row['parent_id'] not in rows:
            raise ValueError('PHOTO_PLACEMENT_PARENT_MISSING')
        seen={identity};parent=row['parent_id']
        while parent in rows:
            if parent in seen:raise ValueError('PHOTO_PLACEMENT_CYCLE')
            seen.add(parent);parent=rows[parent]['parent_id']
        if (value['schema_version']==PLACEMENT_VERSION and row['parent_id'] in rows
                and rows[row['parent_id']]['relation']!='floor'):
            raise ValueError('PHOTO_PLACEMENT_NESTED_PARENT_UNSUPPORTED')
    return deepcopy(value)


def _parent_surface(parent,part):
    if 'center_m' in parent or parent.get('kind') in {'pallet','box','tabletop_item'}:
        surface=support_surface(parent,part)
        if surface is None:raise ValueError('PHOTO_PLACEMENT_PARENT_PART_MISSING')
        return (*surface.transform.position_m,*surface.shape.dimensions_m,parent_yaw(parent))
    if parent.get('kind') not in {'clothes_rack','office_chair'} or part!='body':
        raise ValueError('PHOTO_PLACEMENT_PARENT_PART_UNSUPPORTED')
    return (*parent['position_m'],*parent['dimensions_m'],parent['yaw_deg'])


def drape_anchor_xy(parent,part,anchor):
    """Shared horizontal anchor, independent of the child's height validation."""
    px,py,pz,w,d,h,yaw=_parent_surface(parent,part)
    lx=ly=0
    if anchor in {'left','right'}:lx=(-1 if anchor=='left' else 1)*w/2
    elif anchor in {'front','rear'}:ly=(-1 if anchor=='front' else 1)*d/2
    else:raise ValueError('PHOTO_PLACEMENT_DRAPE_ANCHOR_INVALID')
    angle=radians(yaw);co,si=cos(angle),sin(angle)
    return [px+lx*co-ly*si,py+lx*si+ly*co],yaw


def drape_pose(parent,part,anchor,size,*,identity=None,placement=None):
    px,py,pz,w,d,h,yaw=_parent_surface(parent,part)
    xy,yaw=drape_anchor_xy(parent,part,anchor)
    z=pz+h/2-size[2]/2
    if size[2]-(pz+h/2)>1e-6:
        from .geometry_diagnostics import GeometryValidationError, geometry_issue
        support_top=pz+h/2
        raise GeometryValidationError([geometry_issue('PHOTO_PLACEMENT_DRAPE_BELOW_FLOOR',identity,
            path='$.objects.'+identity+'.dimensions_m[2]' if identity else '$',
            actual={'height_m':size[2],'support_top_m':support_top,'bottom_m':support_top-size[2],
                    'placement':deepcopy(placement)},
            expected={'max_height_m':support_top,'min_bottom_m':0,'unit':'m',
                      'depends_on':['child.dimensions_m[2]','parent.dimensions_m','parent.variant','placement.part'],
                      'repair_options':['estimated_child_height','estimated_parent_height','supported_parent_part']},
            related_ids=[parent.get('id')],violation=size[2]-support_top,
            repairable=identity is not None)])
    return [*xy,z],yaw


def validate_placement_plan(plan,contract):
    """Validate each independent child and retain semantic IDs in all errors."""
    if contract is None:return
    from .geometry_diagnostics import GeometryValidationError, geometry_issue
    contract=checked_placement_contract(contract)
    calls={c.arguments['id']:c for c in plan.calls}
    walls=[c.arguments for c in plan.calls if c.tool=='create_wall']
    ceiling=min((w['dimensions_m'][2] for w in walls),default=None)
    issues=[];supported={}
    rows=contract['relations']
    if not rows:
        _validate_placement_plan_first(plan,contract)
    for row in rows:
        identity=row['id'];parent_id=row['parent_id']
        child=calls.get(identity);parent=calls.get(parent_id)
        actual=deepcopy(child.arguments) if child else None
        expected={'placement':row,'parent':deepcopy(parent.arguments) if parent else None,
                  'ceiling_m':ceiling,'unit':'m'}
        try:
            _validate_placement_plan_first(plan,{**contract,'relations':[row]},_contract_checked=True)
        except ValueError as error:
            if isinstance(error,GeometryValidationError):
                issues.extend(deepcopy(error.contract_report['issues']))
                continue
            code=str(error).split(':')[0]
            violation=None
            if actual and ceiling is not None and code=='PHOTO_PLACEMENT_ABOVE_CEILING':
                violation=actual['position_m'][2]+actual['dimensions_m'][2]/2-ceiling-.02
                expected['max_top_m']=ceiling+.02
            issues.append(geometry_issue(code,identity,actual=actual,expected=expected,
                related_ids=[parent_id],violation=violation))
            continue
        if row['relation']=='surface' and child and parent:
            result=support_geometry(child.arguments,parent.arguments,row['part'])
            if result['status']=='PASS':
                bounds=result['support_bounds_xy_m'];key=(parent_id,row['part'])
                previous=supported.setdefault(key,[])
                collisions=[other for other,old in previous if bounds[0]<old[1]-1e-6 and old[0]<bounds[1]-1e-6
                    and bounds[2]<old[3]-1e-6 and old[2]<bounds[3]-1e-6]
                if collisions:
                    issues.append(geometry_issue('PHOTO_PLACEMENT_SURFACE_SIBLINGS_OVERLAP',identity,
                        actual={'bounds_xy_m':bounds},expected={'nonoverlapping_siblings':True},
                        related_ids=[parent_id,*collisions]))
                previous.append((identity,bounds))
    if issues:raise GeometryValidationError(issues)


def _validate_placement_plan_first(plan,contract,*,_contract_checked=False):
    if contract is None:return
    if not _contract_checked:contract=checked_placement_contract(contract)
    calls={c.arguments['id']:c for c in plan.calls}
    floors=[c.arguments for c in plan.calls if c.tool=='create_floor']
    walls=[c.arguments for c in plan.calls if c.tool=='create_wall']
    if len(floors)!=1 or not walls:raise ValueError('PHOTO_PLACEMENT_ROOM_MISSING')
    ceiling=min(w['dimensions_m'][2] for w in walls)
    siblings={}
    for row in contract['relations']:
        call=calls.get(row['id'])
        if call is None or call.tool not in {'place_furniture','place_room_item','create_rack_row','place_pallet_stack'}:
            raise ValueError('PHOTO_PLACEMENT_ITEM_MISSING')
        child=call.arguments;kind=row['relation'];parent_id=row['parent_id'];part=row['part']
        from .room_item_catalog import REQUIRED_ROOM_RELATIONS
        required=REQUIRED_ROOM_RELATIONS.get(child.get('kind'))
        if required and kind!=required:raise ValueError('PHOTO_PLACEMENT_MODEL_RELATION_MISMATCH')
        if kind=='floor':
            if parent_id is not None or part is not None or row['anchor']!='centre' or row['elevation_m'] is not None:
                raise ValueError('PHOTO_PLACEMENT_FLOOR_INVALID')
            if call.tool=='place_room_item' and abs(child['position_m'][2]-child['dimensions_m'][2]/2)>.02:
                raise ValueError('PHOTO_PLACEMENT_FLOOR_HEIGHT_CHANGED')
            continue
        if call.tool!='place_room_item':raise ValueError('PHOTO_PLACEMENT_FURNITURE_ATTACHMENT_UNSUPPORTED')
        size=child['dimensions_m'];position=child['position_m']
        if position[2]+size[2]/2>ceiling+.02:raise ValueError('PHOTO_PLACEMENT_ABOVE_CEILING')
        if kind in {'surface','drape'}:
            parent_call=calls.get(parent_id)
            if parent_call is None:raise ValueError('PHOTO_PLACEMENT_PARENT_MISSING')
            parent=parent_call.arguments
            valid_parts=support_parts(parent_kind(parent),kind,
                {'level_count':parent['level_count']} if 'level_count' in parent else None)
            if part not in valid_parts or row['elevation_m'] is not None:
                raise ValueError('PHOTO_PLACEMENT_PARENT_PART_UNSUPPORTED')
            if kind=='surface':
                if row['anchor']!='centre':raise ValueError('PHOTO_PLACEMENT_SURFACE_ANCHOR_INVALID')
                report=support_geometry(child,parent,part)
                if report['status']!='PASS':raise ValueError('PHOTO_PLACEMENT_SURFACE_CHANGED: '+row['id'])
                bounds=report['support_bounds_xy_m'];previous=siblings.setdefault((parent_id,part),[])
                if any(bounds[0]<old[1]-1e-6 and old[0]<bounds[1]-1e-6 and
                       bounds[2]<old[3]-1e-6 and old[2]<bounds[3]-1e-6 for old in previous):
                    raise ValueError('PHOTO_PLACEMENT_SURFACE_SIBLINGS_OVERLAP')
                previous.append(bounds)
            else:
                if child['kind'] not in {'hanging_clothes','bedding_overhang','clothing_pile'}:
                    raise ValueError('PHOTO_PLACEMENT_DRAPE_KIND_UNSUPPORTED')
                expected,yaw=drape_pose(parent,part,row['anchor'],size,identity=row['id'],placement=row)
                if max(abs(a-b) for a,b in zip(position,expected))>.02 or abs((child['yaw_deg']-yaw+180)%360-180)>.01:
                    raise ValueError('PHOTO_PLACEMENT_DRAPE_CHANGED: '+row['id'])
        elif kind=='wall':
            from .room_item_catalog import WALL_ITEMS
            wall=calls.get(parent_id)
            if (child['kind'] not in WALL_ITEMS or parent_id not in {'left_wall','right_wall','rear_wall'}
                    or wall is None or wall.tool!='create_wall' or part is not None
                    or row['anchor']!='centre' or row['elevation_m'] is None):
                raise ValueError('PHOTO_PLACEMENT_WALL_UNSUPPORTED')
            wa=wall.arguments;axis=1 if parent_id=='rear_wall' else 0
            if abs(wa['yaw_deg'])>1e-8:raise ValueError('PHOTO_PLACEMENT_WALL_ROTATION_UNSUPPORTED')
            sign=1 if parent_id!='left_wall' else -1
            expected=wa['position_m'][axis]-sign*(wa['dimensions_m'][axis]/2+size[1]/2+.002)
            yaw=0 if axis==1 else 90
            if (abs(position[axis]-expected)>.02 or abs(position[2]-row['elevation_m'])>.02
                    or abs((child['yaw_deg']-yaw+180)%360-180)>.01):
                raise ValueError('PHOTO_PLACEMENT_WALL_CHANGED: '+row['id'])
        elif kind=='ceiling':
            from .room_item_catalog import CEILING_ITEMS
            if (child['kind'] not in CEILING_ITEMS or parent_id!='ceiling' or part is not None
                    or row['anchor']!='centre' or row['elevation_m'] is not None
                    or abs(position[2]+size[2]/2-(ceiling-.002))>.02):
                raise ValueError('PHOTO_PLACEMENT_CEILING_CHANGED: '+row['id'])


def relocate_attached_children(old_plan,new_plan,contract,target_call_id):
    """Pure atomic parent edit; only explicitly declared direct children change.

    Surface children keep local normalized offsets/yaw and top contact. Invalid
    resize (too-small support, sibling overlap, floor/ceiling) rejects the whole
    preview; no clamp, packing retry, source mutation or robot authority.
    """
    if contract is None:return new_plan
    from dataclasses import replace
    from .scene_tools import SceneToolCall
    old={c.arguments['id']:c for c in old_plan.calls};new={c.arguments['id']:c for c in new_plan.calls}
    target=next(c.arguments['id'] for c in old_plan.calls if c.call_id==target_call_id)
    replacements={}
    for row in checked_placement_contract(contract)['relations']:
        if row['parent_id']!=target:continue
        child=dict(new[row['id']].arguments);old_parent=old[target].arguments;new_parent=new[target].arguments
        if row['relation']=='drape':
            child['position_m'],child['yaw_deg']=drape_pose(new_parent,row['part'],row['anchor'],child['dimensions_m'],
                identity=row['id'],placement=row)
        elif row['relation']=='surface':
            opx,opy,opz,ow,od,oh,oyaw=_parent_surface(old_parent,row['part'])
            npx,npy,npz,nw,nd,nh,nyaw=_parent_surface(new_parent,row['part'])
            dx,dy=child['position_m'][0]-opx,child['position_m'][1]-opy
            angle=radians(oyaw);co,si=cos(angle),sin(angle)
            lx=(co*dx+si*dy)*nw/ow;ly=(-si*dx+co*dy)*nd/od
            angle=radians(nyaw);co,si=cos(angle),sin(angle)
            child['position_m']=[npx+lx*co-ly*si,npy+lx*si+ly*co,npz+nh/2+child['dimensions_m'][2]/2]
            child['yaw_deg']=(child['yaw_deg']+nyaw-oyaw+180)%360-180
        elif row['relation']=='wall':
            axis=1 if target=='rear_wall' else 0;sign=1 if target!='left_wall' else -1
            child['position_m']=list(child['position_m'])
            child['position_m'][axis]=new_parent['position_m'][axis]-sign*(new_parent['dimensions_m'][axis]/2+child['dimensions_m'][1]/2+.002)
        else:continue
        previous=new[row['id']];replacements[previous.call_id]=SceneToolCall(previous.call_id,previous.tool,child)
    return replace(new_plan,calls=tuple(replacements.get(c.call_id,c) for c in new_plan.calls))
