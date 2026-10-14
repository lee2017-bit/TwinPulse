# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compact photo intent -> validated Site2.2. Estimated geometry, never a map.

The model selects categories/regions, not arithmetic or executable tools. The
strict compiler never omits objects. Explicit progressive mode retains failed
supported props in a pending ledger. Every emitted call passes the executor.
"""
from __future__ import annotations

import json
import copy
import hashlib
import math
import re
import time
from typing import Mapping

from twinpulse_core import SiteToolPlan, canonical_sha256, execute_site_tool_plan
from twinpulse_core.furniture import furniture_footprint, furniture_kinds
from twinpulse_core.room_item_catalog import ROOM_ITEM_KINDS, WALL_ITEMS, CEILING_ITEMS, room_item_catalog_version
from twinpulse_core.model_library import library_for_request
from twinpulse_core.warehouse_models import (WAREHOUSE_KINDS, PARAMETERS as WAREHOUSE_PARAMETERS,
    support_parts, warehouse_arguments, warehouse_parts, parent_yaw)
from .scene_contract import GROUNDING_REVISION, ground_layout, source_schema, role_of

REVISION = 'photo-layout-1.1'
LEGACY_REVISION = 'photo-layout-1.0'
RELATION_COMPILER_REVISION = 'photo-layout-compiler-1.2'
PARAMETRIC_REVISION = 'photo-layout-1.2'
PARAMETRIC_COMPILER_REVISION = 'photo-layout-compiler-1.3'
SUPPORT_COMPILER_REVISION = 'photo-layout-compiler-1.7'
SIGNED_PACKING_COMPILER_REVISION = 'photo-layout-compiler-1.8'
BOUNDARY_PACKING_COMPILER_REVISION = 'photo-layout-compiler-1.9'
REGIONS = tuple(f'{row}_{col}' for row in ('front','middle','rear') for col in ('left','centre','right'))
SIZES = {
    'floor_covering': (1.2,.8,.02), 'wall_fixture': (.3,.05,.3),
    'ceiling_fixture': (.4,.4,.05), 'wall_storage': (1.2,.35,.6),
    'office_chair':(.6,.6,.9),'floor_fan':(.4,.4,1.1),'clothes_rack':(.7,.45,1.5),
    'door_leaf':(.08,.65,1.9),'bag':(.3,.25,.35),'box':(.35,.3,.3),'basket':(.35,.3,.4),
    'clothing_pile':(.35,.25,.15),'hanging_clothes':(.35,.2,.7),'bedding_overhang':(.4,.18,.15),
    'cable_bundle':(.3,.2,.04),'power_adapter':(.18,.12,.08),'power_strip':(.25,.12,.08),
    'small_equipment':(.2,.2,.15),'monitor':(.45,.15,.35),'tabletop_item':(.2,.2,.2),
    'window_blind':(.8,.08,.8),'ceiling_light':(.3,.3,.12),'unknown':(.3,.3,.3),
    'pallet':(1.2,.8,.12),
}
KINDS = (*furniture_kinds(), *ROOM_ITEM_KINDS, *WAREHOUSE_KINDS)
_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')


class PhotoLayoutPackingError(ValueError):
    """Bounded occupied-proxy conflict evidence for the existing repair path."""
    def __init__(self, identity, region, report):
        super().__init__('PHOTO_LAYOUT_REGION_FULL: '+identity+' in '+region+
            '; keep identities and explicit measured constraints; inspect estimated assembly bounds, dimensions and placement; '
            'request eligible atomic scope before modifying placed blockers')
        self.packing_report=report
        from twinpulse_core.geometry_diagnostics import geometry_issue, geometry_report
        conflicts=report.get('conflict_set',{}).get('conflicts',[])
        issues=[]
        for failed in conflicts or [dict(id=identity,region=region,dependency_ids=[])] :
            target=failed['id']
            issues.append(geometry_issue('PHOTO_LAYOUT_REGION_FULL', target,
                path='$.objects.'+target+'.region',
                actual={'region':failed['region'],**({'packing':report} if target==identity else {'conflict':failed})},
                expected={'room_size_m':report.get('room_size_m'),
                    'constraint':'nonoverlapping occupied assemblies inside requested region',
                    'scope':'bounded search failure, not proof of global infeasibility'},
                # Blockers are repair-scope OPTIONS, not automatic edit authority.
                related_ids=report.get('unplaced_ids',report.get('remaining_ids',[]))+failed.get('dependency_ids',[])+['$room']))
        self.contract_report=geometry_report(issues)
        self.code='PHOTO_LAYOUT_REGION_FULL'


def _checked_packing_bounds(value):
    if (not isinstance(value,(tuple,list)) or len(value)!=4 or
            any(type(v) not in (float,int) or not math.isfinite(v) for v in value) or
            value[0]>=value[1] or value[2]>=value[3]):
        raise ValueError('PHOTO_LAYOUT_PACKING_BOUNDS_INVALID')
    return tuple(value)


def _floor_domain(bounds,width,length):
    # Parent anchor translation, not an occupied-AABB centre. Keep the same
    # wall margin and arithmetic/order for the existing symmetric footprint.
    return (-width/2-bounds[0]+.11,width/2-bounds[1]-.11,
            -length/2-bounds[2]+.11,length/2-bounds[3]-.11)


def _packing_separated(a,x,y,b,px,py):
    if a[0]==-a[1] and a[2]==-a[3] and b[0]==-b[1] and b[2]==-b[3]:
        return abs(x-px)>=a[1]+b[1]+.03 or abs(y-py)>=a[3]+b[3]+.03
    return (x+a[1]+.03<=px+b[0] or px+b[1]+.03<=x+a[0] or
            y+a[3]+.03<=py+b[2] or py+b[3]+.03<=y+a[2])


def _floor_assembly_bounds(item,rows,relations,*,parametric):
    """Conservative occupied union relative to the unchanged parent anchor.

    The parent keeps its former proxy. Expanded children include the SAME
    catalogue's synthetic keepouts; only the absent mirrored empty half is no
    longer added. This is a packing proxy, not sensed or measured free space.
    """
    if item['kind'] in WAREHOUSE_KINDS:
        parts=warehouse_parts(item)
        sx,sy=(2*max(abs(p.transform.position_m[i])+p.shape.dimensions_m[i]/2 for p in parts) for i in (0,1))
    else:
        sx,sy=(item['dimensions_m'][:2] if parametric else furniture_footprint(item['kind'])
            if item['kind'] in furniture_kinds() else SIZES[item['kind']][:2])
    if item['kind'] in {'clothing_pile','hanging_clothes','bedding_overhang','cable_bundle','unknown','floor_covering'}:
        sx+=.2;sy+=.2
    if abs(item['yaw_deg'])==90:sx,sy=sy,sx
    bounds=[-sx/2,sx/2,-sy/2,sy/2];parent_proxy=list(bounds);children=[]
    if parametric and relations[item['id']]['relation']=='floor':
        from twinpulse_core.photo_placement import drape_anchor_xy
        from twinpulse_core.room_items import expand_room_item
        from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION
        parent=dict(id=item['id'],kind=item['kind'],yaw_deg=item['yaw_deg'],
            dimensions_m=list(item['dimensions_m']),variant=item['variant'],finish=item['finish'])
        if item['kind'] in furniture_kinds():
            parent.update(center_m=[0,0],catalog_version=PARAMETRIC_FURNITURE_VERSION)
        else:parent['position_m']=[0,0,item['dimensions_m'][2]/2]
        for child in rows:
            relation=relations[child['id']]
            if relation['relation']!='drape' or relation['parent_id']!=item['id']:continue
            xy,yaw=drape_anchor_xy(parent,relation['part'],relation['anchor'])
            parts=expand_room_item(dict(id=child['id'],kind=child['kind'],label=child['kind'],
                catalog_version='room-items-1.0',position_m=[*xy,child['dimensions_m'][2]/2],
                dimensions_m=list(child['dimensions_m']),yaw_deg=yaw,observation_time_utc=None))
            part_bounds=[]
            for part in parts:
                dx,dy,_=part.shape.dimensions_m;angle=math.radians(part.transform.rotation_rpy_deg[2])
                hx=(abs(math.cos(angle))*dx+abs(math.sin(angle))*dy)/2
                hy=(abs(math.sin(angle))*dx+abs(math.cos(angle))*dy)/2
                x,y,_=part.transform.position_m;box=(x-hx,x+hx,y-hy,y+hy)
                bounds=[min(bounds[0],box[0]),max(bounds[1],box[1]),min(bounds[2],box[2]),max(bounds[3],box[3])]
                part_bounds.append(dict(id=part.id,local_xy_bounds_m=list(box),synthetic_keepout=part.id.endswith('_keepout')))
            children.append(dict(id=child['id'],part=relation['part'],anchor=relation['anchor'],
                dimensions_m=list(child['dimensions_m']),parts=part_bounds))
    checked=_checked_packing_bounds(bounds)
    return checked,dict(schema_version='photo-floor-assembly-1.0',parent_id=item['id'],parent_kind=item['kind'],
        parent_yaw_deg=item['yaw_deg'],coordinate_frame='parent_anchor_room_xy_axes',
        parent_dimensions_m=list(item['dimensions_m']) if parametric else None,parent_proxy_xy_bounds_m=parent_proxy,
        local_xy_bounds_m=list(checked),occupied_size_m=[checked[1]-checked[0],checked[3]-checked[2]],
        conservative_symmetric_footprint_m=[2*max(abs(checked[0]),abs(checked[1])),2*max(abs(checked[2]),abs(checked[3]))],
        contributing_children=children,physical_authority=False)


def _assembly_domain_diagnostic(item,bounds,diagnostic,width,length):
    floor=list(_floor_domain(bounds,width,length));region=list(floor)
    row,col=item['region'].split('_')
    if col=='left':region[1]=min(region[1],-.05)
    elif col=='right':region[0]=max(region[0],.05)
    else:region[0]=max(region[0],-width/6);region[1]=min(region[1],width/6)
    if row=='front':region[3]=min(region[3],-.05)
    elif row=='rear':region[2]=max(region[2],.05)
    else:region[2]=max(region[2],-length/6);region[3]=min(region[3],length/6)
    return {**diagnostic,'floor_margin_m':.11,'assembly_gap_m':.03,'grid_spacing_m':.1,
        'parent_floor_domain_xy_m':floor,'parent_region_domain_xy_m':region,
        'empty_floor_axes':[axis for axis,i in (('x',0),('y',2)) if floor[i]>floor[i+1]],
        'empty_region_axes':[axis for axis,i in (('x',0),('y',2)) if region[i]>region[i+1]]}


def _bounded_region_repack(items,footprint,width,length,*,max_nodes=512,timeout_s=2.,
                           branch_cap=32,clock=None,local_bounds=None):
    """Fallback only: grid plus boundary candidates, same margins and inventory.

    Minimum remaining values avoids treating one greedy ordering as impossible.
    Search exhaustion is still failure, never evidence of global infeasibility.
    """
    if (type(max_nodes) is not int or max_nodes<0 or type(branch_cap) is not int or branch_cap<1
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or timeout_s<0):
        raise ValueError('PHOTO_LAYOUT_SEARCH_BUDGET_INVALID')
    clock=clock or time.perf_counter
    started=clock();deadline=started+timeout_s;nodes=0;domains={};sizes={};ticks=0
    halt=None;phase='domain_generation';branches_truncated=0;pruned=0;dead_ends=0
    domains_complete=False
    def report(found,termination):
        return dict(schema_version='photo-layout-bounded-search-1.0',
            status='FOUND' if found else 'BUDGET_EXHAUSTED' if phase=='domain_generation'
                and termination=='TIME_BUDGET_EXHAUSTED' else 'BOUNDED_SEARCH_FAILED',
            termination_code=termination,phase=phase,nodes=nodes,max_nodes=max_nodes,
            timeout_s=timeout_s,branch_cap=branch_cap,elapsed_s=max(0.,clock()-started),
            candidate_checks=ticks,overlap_pruned=pruned,dead_ends=dead_ends,
            branches_truncated=branches_truncated,domain_generation_complete=domains_complete,
            domain_counts={identity:len(points) for identity,points in domains.items()},
            grid_search_exhaustive=not found and termination in {'EMPTY_DOMAIN','GRID_SEARCH_EXHAUSTED'},
            global_infeasibility_proved=False,
            candidate_policy='grid_then_domain_and_contact_boundaries-1.0',
            scope='SYNTHETIC_SAME_REGION_CANDIDATES_NOT_MEASURED_FREE_SPACE',physical_authority=False)
    for item in items:
        sx,sy=footprint(item);identity=item['id']
        bounds=_checked_packing_bounds(local_bounds(item) if local_bounds else (-sx/2,sx/2,-sy/2,sy/2))
        sizes[identity]=bounds;xmin,xmax,ymin,ymax=_floor_domain(bounds,width,length)
        row,col=item['region'].split('_');cx={'left':-1,'centre':0,'right':1}[col]*width/3
        cy={'front':-1,'middle':0,'rear':1}[row]*length/3;points=[]
        from .packing_candidates import floor_candidates
        for priority,x,y in floor_candidates(bounds,width,length,item['region']):
            ticks+=1
            if ticks%128==0 and clock()>deadline:
                return None,report(False,'TIME_BUDGET_EXHAUSTED')
            points.append((priority,(x-cx)**2+(y-cy)**2,x,y))
        domains[identity]=[(x,y) for _,_,x,y in sorted(points)]
    domains_complete=True
    if any(not points for points in domains.values()):
        return None,report(False,'EMPTY_DOMAIN')
    phase='backtracking'
    def budget_expired():
        nonlocal halt
        if clock()>deadline:halt='TIME_BUDGET_EXHAUSTED'
        elif nodes>=max_nodes:halt='NODE_BUDGET_EXHAUSTED'
        return halt is not None
    def search(remaining,chosen):
        nonlocal nodes,ticks,halt,branches_truncated,pruned,dead_ends
        if not remaining:return chosen
        if budget_expired():return None
        nodes+=1;options=[]
        for identity in remaining:
            bounds=sizes[identity];available=[]
            item=next(row for row in items if row['id']==identity)
            rr,cc=item['region'].split('_')
            cx={'left':-1,'centre':0,'right':1}[cc]*width/3
            cy={'front':-1,'middle':0,'rear':1}[rr]*length/3
            blockers=[(other,px,py,sizes[other]) for other,(px,py) in chosen.items()]
            candidates=[]
            try:
                for priority,x,y in floor_candidates(bounds,width,length,item['region'],blockers):
                    ticks+=1
                    if ticks%128==0 and clock()>deadline:
                        halt='TIME_BUDGET_EXHAUSTED';return None
                    candidates.append((priority,(x-cx)**2+(y-cy)**2,x,y))
            except ValueError as error:
                if str(error)!='PHOTO_LAYOUT_CANDIDATE_BUDGET_EXHAUSTED':raise
                halt='CANDIDATE_BUDGET_EXHAUSTED';return None
            candidates.sort()
            for _,_,x,y in candidates:
                ticks+=1
                if ticks%128==0 and clock()>deadline:
                    halt='TIME_BUDGET_EXHAUSTED';return None
                if all(_packing_separated(bounds,x,y,sizes[other],px,py)
                       for other,(px,py) in chosen.items()):available.append((x,y))
                else:pruned+=1
            if not available:
                dead_ends+=1;return None
            options.append((len(available),-(bounds[1]-bounds[0])*(bounds[3]-bounds[2])/4,identity,available))
        _,_,identity,available=min(options)
        if len(available)>branch_cap:branches_truncated+=1
        # A prefix of centre-biased candidates can miss the only feasible
        # boundary/contact position while leaving almost all budget unused.
        # Preserve near-centre choices and sample the whole ranked domain.
        if len(available)>branch_cap:
            head=min(8,max(1,branch_cap//4))
            indexes=list(range(head))
            slots=branch_cap-head
            indexes += [head+round(i*(len(available)-1-head)/max(1,slots-1)) for i in range(slots)]
            choices=[available[i] for i in dict.fromkeys(indexes)]
        else:choices=available
        for point in choices:
            found=search(tuple(i for i in remaining if i!=identity),{**chosen,identity:point})
            if found is not None:return found
            if halt is not None:break
        return None
    found=search(tuple(sorted(domains)),{})
    termination=('FOUND' if found is not None else halt or
                 ('BRANCH_BUDGET_EXHAUSTED' if branches_truncated else 'GRID_SEARCH_EXHAUSTED'))
    return found,report(found is not None,termination)


def requested_size(prompt):
    # Only an unambiguous explicit width-by-length pair. Other descriptions
    # remain estimated, never silently promoted to trusted measurements.
    pairs=list(re.finditer(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(?:metres?|meters?|미터|m)?\s*(?:by|x|×)\s*'
        r'(\d+(?:\.\d+)?)\s*(?:metres?|meters?|미터|m)?(?![\d.])',prompt,re.I))
    room_nouns={'bedroom','living room','dining room','room','space','workspace','workshop',
        'shop','office','kitchen','studio','warehouse','garage','classroom','laboratory',
        'bathroom','study','home office','lounge','hallway','corridor','meeting room','nursery',
        '침실','거실','방','공간','작업실','사무실','매장','창고','주방','서재','복도','회의실','아이방'}
    object_nouns={kind.replace('_',' ') for kind in KINDS} | {
        'bed','desk','table','wardrobe','chair','cabinet','storage cabinet','kitchen cabinet',
        'dining table','shelf','shelving','object','침대','책상','탁자','옷장','의자','선반','책장','수납장'}
    # Korean owners are commonly followed by grammatical particles (서재를,
    # 방의). Match the canonical noun separately; a particle is not a new
    # dimension owner, and a longer unknown word must still not match.
    nouns=re.compile(r'(?<!\w)(?P<owner>'+ '|'.join(re.escape(noun).replace(r'\ ',r'\s+')
        for noun in sorted(room_nouns | object_nouns,key=lambda noun:(-len(noun),noun)))
        +r')(?P<particle>에서|으로|의|은|는|이|가|을|를|에|로|도|만|과|와)?(?!\w)',re.I)
    # Do not borrow a room noun across a sentence or arbitrary object/clause.
    # Both adjective order ("6 by 8 metre office") and labelled order
    # ("office dimensions: 6 by 8") use the same bounded owner vocabulary.
    gap=re.compile(r"[\s,:=(]*(?:(?:is|are|measures?|measuring|of|size|dimensions?|"
        r"width|length|approximately|approximate|about|estimated|roughly)\b[\s,:=()-]*|"
        r"(?:추정|대략|약|크기|규격|너비|가로|세로|길이|치수)(?:은|는|이|가)?[\s,:=()-]*)*",re.I)
    # '6×5m의 서재' owns the pair just as '6 by 5 metre study' does.
    # No arbitrary clause or intervening furniture is consumed here.
    owner_prefix=re.compile(r'\s*(?:의\s+)?')
    matches=[]
    for pair in pairs:
        before=list(nouns.finditer(prompt[:pair.start()]))
        preceding=(before[-1] if before
            and before[-1].group('particle') not in {'에','에서','로','으로','과','와'}
            and gap.fullmatch(prompt[before[-1].end():pair.start()]) else None)
        suffix=prompt[pair.end():]
        following=nouns.match(suffix,owner_prefix.match(suffix).end())
        normalize=lambda noun:re.sub(r'\s+',' ',noun.group('owner').lower())
        next_owner=nouns.search(suffix,following.end()) if following else None
        if preceding and len(before)>1 and (re.fullmatch(r'\s*(?:and|or|/|&|과|와|및|또는)\s*',
                prompt[before[-2].end():preceding.start()],re.I)
                or before[-2].group('particle') in {'과','와'}
                and re.fullmatch(r'\s*',prompt[before[-2].end():preceding.start()])):
            raise ValueError('PHOTO_LAYOUT_AMBIGUOUS_DIMENSIONS: more than one possible dimension owner')
        if next_owner and (re.fullmatch(r'\s*(?:and|or|/|&|과|와|및|또는)\s*',suffix[following.end():next_owner.start()],re.I)
                or following.group('particle') in {'과','와'}
                and re.fullmatch(r'\s*',suffix[following.end():next_owner.start()])):
            raise ValueError('PHOTO_LAYOUT_AMBIGUOUS_DIMENSIONS: more than one possible dimension owner')
        if preceding and following and normalize(preceding)!=normalize(following):
            raise ValueError('PHOTO_LAYOUT_AMBIGUOUS_DIMENSIONS: conflicting room or object owners')
        owner=normalize(following or preceding) if following or preceding else None
        if owner in room_nouns:
            matches.append((float(pair[1]),float(pair[2])))
        elif owner is None:
            raise ValueError('PHOTO_LAYOUT_UNQUALIFIED_DIMENSIONS: identify the room or object for this pair')
    if len(matches)>1:raise ValueError('PHOTO_LAYOUT_AMBIGUOUS_DIMENSIONS: more than one room width-by-length pair')
    return matches[0] if matches else None


def _checked_model_relations(rows,height,reviewed_supports,quality_constraints=None):
    from twinpulse_core.geometry_diagnostics import validate_model_relations
    return validate_model_relations(rows,height,reviewed_supports,quality_constraints)


def _place_attachments(rows,relations,calls,evidence,placements,reviewed,width,length,height):
    from twinpulse_core.photo_placement import drape_pose
    from twinpulse_core.geometry_diagnostics import GeometryValidationError
    issues=[]
    parents={c['arguments']['id']:c['arguments'] for c in calls
             if c['tool'] in {'place_furniture','place_room_item'}}
    for item in rows:
        relation=relations[item['id']];kind=relation['relation']
        if kind not in {'wall','ceiling','drape'}:continue
        size=item['dimensions_m'];sx,sy,sz=size;yaw=item['yaw_deg']
        row,col=item['region'].split('_')
        x={'left':-1,'centre':0,'right':1}[col]*width/3
        y={'front':-1,'middle':0,'rear':1}[row]*length/3
        parent_id=relation['parent_id']
        if kind=='wall':
            z=relation['elevation_m']
            if parent_id=='rear_wall':y=length/2-.04-sy/2-.002;yaw=0
            else:x=(-1 if parent_id=='left_wall' else 1)*(width/2-.04-sy/2-.002);yaw=90
            # Regional centres are coarse intent, not a valid geometric pose.
            # Keep the full tangential extent inside the selected wall; never
            # resize the source object or the room to fit a particular photo.
            span=width if parent_id=='rear_wall' else length
            lower,upper=-span/2+sx/2+.002,span/2-sx/2-.002
            if lower>upper:
                from twinpulse_core.geometry_diagnostics import geometry_issue
                issues.append(geometry_issue('PHOTO_WALL_SPAN_EXCEEDED',item['id'],
                    path='$.objects.'+item['id']+'.dimensions_m[0]',actual=sx,
                    expected={'max_m':span-.004,'parent_id':parent_id,'unit':'m'},
                    related_ids=['$room'],violation=sx-(span-.004)))
                continue
            if parent_id=='rear_wall':x=min(upper,max(lower,x))
            else:y=min(upper,max(lower,y))
        elif kind=='ceiling':z=height-sz/2-.002
        else:
            parent=parents[parent_id]
            # Fabric touches/overhangs a selected parent edge, rather than being
            # independently packed elsewhere. The existing floor keepout stays.
            try:
                (x,y,z),yaw=drape_pose(parent,relation['part'],relation['anchor'],size,
                    identity=item['id'], placement=relation)
            except GeometryValidationError as error:
                issues.extend(error.contract_report['issues'])
                continue
        args=dict(id=item['id'],kind=item['kind'],label=reviewed.get(item['id'],{}).get('label',item['kind'].replace('_',' ')),
            catalog_version=room_item_catalog_version(item['kind']),position_m=[x,y,z],dimensions_m=list(size),
            yaw_deg=yaw,observation_time_utc=None)
        call_id='obj_'+item['id'];calls.append(dict(call_id=call_id,tool='place_room_item',arguments=args))
        evidence.append(dict(call_id=call_id,basis='inferred',observation_ids=item['observation_ids'],
            note='Estimated '+kind+' relationship; derived from selected parent, not a measured attachment'))
        placements.append(dict(id=item['id'],region=item['region'],centre_xy_m=[x,y],
            parent=parent_id,relation=kind,part=relation['part'],applied_yaw_deg=yaw))
    if issues:raise GeometryValidationError(issues)


def reviewed_region_choices(reference, quality_constraints):
    """Compile only evidence-bound host review into legal region choices.

    This is assisted generation, not new visual perception or coordinate repair.
    The independent executor/quality gate still checks actual emitted geometry.
    """
    # Only literal directions already in the reviewed label are constraints.
    # This does not guess aliases/coordinates or treat an observer ID as a pose.
    choices={}
    if reference:
        for item in reference['items']:
            label=item.get('label','').lower()
            left=bool(re.search(r'\bleft\b',label))
            right=bool(re.search(r'\bright\b',label))
            if left and right:
                raise ValueError('PHOTO_INVENTORY_LABEL_DIRECTION_CONFLICT: '+item['id'])
            if left or right:
                choices[item['id']]=[r for r in REGIONS if r.split('_')[1]==('left' if left else 'right')]
    if quality_constraints is None:
        return choices
    from twinpulse_core.photo_quality import checked_constraints
    if not reference:
        raise ValueError('PHOTO_CONSTRAINTS_INVENTORY_MISMATCH')
    checked_constraints(quality_constraints, reference['image_sha256'])
    if dict(quality_constraints.required_items) != {i['id']:i['kind'] for i in reference['items']}:
        raise ValueError('PHOTO_CONSTRAINTS_INVENTORY_MISMATCH')
    for identity,axis,expected in quality_constraints.positions:
        regions=choices.get(identity,list(REGIONS))
        choices[identity]=[r for r in regions if r.split('_')[1 if axis=='x' else 0]==expected]
        if not choices[identity]:
            raise ValueError('PHOTO_CONSTRAINTS_POSITION_CONFLICT: '+identity)
    return choices


def _model_fields(kind=None, *, reviewed_support=None, allowed_parents=None):
    from twinpulse_core.model_library import library_models
    models=[m for m in library_models() if m['kind'] in KINDS and (kind is None or m['kind']==kind)]
    placement=dict(relation={'enum':['floor','surface','drape','wall','ceiling']},
        parent_id={'type':['string','null'],'maxLength':32},
        part={'type':['string','null'],'maxLength':32},
        anchor={'enum':['centre','front','left','right','rear']},
        elevation_m={'type':['number','null'],'minimum':0,'maximum':4})
    # Prevent known-invalid output in the grammar, not by rewriting a rejected
    # response. The compiler independently enforces these same relationships.
    if kind in (*furniture_kinds(),'office_chair','floor_fan','clothes_rack','door_leaf','pallet','floor_covering',*WAREHOUSE_KINDS):
        placement=dict(relation={'enum':['floor']},parent_id={'type':'null'},
            part={'type':'null'},anchor={'enum':['centre']},elevation_m={'type':'null'})
        if reviewed_support is not None:
            raise ValueError('PHOTO_RELATION_UNSUPPORTED: furniture must be floor-standing: '+kind)
    elif reviewed_support is not None:
        parent,part=reviewed_support
        placement=dict(relation={'enum':['surface']},parent_id={'enum':[parent]},
            part={'enum':[part]},anchor={'enum':['centre']},elevation_m={'type':'null'})
    elif kind in WALL_ITEMS:
        placement=dict(relation={'enum':['wall']},
            parent_id={'enum':['left_wall','right_wall','rear_wall']},part={'type':'null'},
            anchor={'enum':['centre']},elevation_m={'type':'number','minimum':.001,'maximum':4})
    elif kind in CEILING_ITEMS:
        placement=dict(relation={'enum':['ceiling']},parent_id={'enum':['ceiling']},
            part={'type':'null'},anchor={'enum':['centre']},elevation_m={'type':'null'})
    placement_schema={'type':'object','additionalProperties':False,
        'required':['relation','parent_id','part','anchor','elevation_m'],'properties':placement}
    floor_kinds=(*furniture_kinds(),'office_chair','floor_fan','clothes_rack','door_leaf','pallet','floor_covering',*WAREHOUSE_KINDS)
    if (kind in KINDS and kind not in (*floor_kinds,*WALL_ITEMS,*CEILING_ITEMS)
            and reviewed_support is None and allowed_parents is not None):
        # Each branch binds a parent ID to its actual library parts. A union of
        # independent parent/part enums would still permit e.g. bed/body.
        def branch(properties):
            return dict(type='object',additionalProperties=False,
                required=list(properties),properties=properties)
        branches=[branch(dict(relation={'enum':['floor']},parent_id={'type':'null'},
            part={'type':'null'},anchor={'enum':['centre']},elevation_m={'type':'null'}))]
        for parent,parent_kind in allowed_parents.items():
            for relation in ('surface','drape'):
                if relation=='drape' and kind not in {'hanging_clothes','bedding_overhang','clothing_pile'}:continue
                parts=list(support_parts(parent_kind, relation))
                if not parts:continue
                branches.append(branch(dict(relation={'enum':[relation]},parent_id={'enum':[parent]},
                    part={'enum':parts},anchor={'enum':['centre'] if relation=='surface' else ['front','left','right','rear']},
                    elevation_m={'type':'null'})))
        placement_schema={'anyOf':branches}
    fields=dict(model_id={'enum':[m['model_id'] for m in models]},
        dimensions_m={'type':'array','minItems':3,'maxItems':3,
                      'items':{'type':'number','minimum':.001,'maximum':10}},
        variant={'enum':sorted({v for m in models for v in m['variants']})},
        finish={'enum':sorted({v for m in models for v in m['finishes']})},
        placement=placement_schema)
    if kind in WAREHOUSE_KINDS:
        fields['warehouse_parameters']=dict(type='object',additionalProperties=False,
            required=list(WAREHOUSE_PARAMETERS[kind]),properties={key:dict(type='integer',minimum=low,maximum=high)
                for key,(low,high) in WAREHOUSE_PARAMETERS[kind].items()})
    return fields


def layout_schema(prompt, reference=None, observation=None, *, quality_constraints=None, revision=REVISION):
    if revision not in (REVISION,PARAMETRIC_REVISION,GROUNDING_REVISION):raise ValueError('PHOTO_LAYOUT_SCHEMA_VERSION_INVALID')
    allowed_kinds=KINDS if revision in (PARAMETRIC_REVISION,GROUNDING_REVISION) else tuple(k for k in KINDS if k not in WAREHOUSE_KINDS)
    size=requested_size(prompt)
    dimension=lambda index: {'type':'number','minimum':2,'maximum':12,
        **({'const':size[index]} if size else {})}
    refs={'type':'array','maxItems':3,'items':{'type':'string','maxLength':64}}
    if observation is not None:
        observed=[e['id'] for e in observation.entities]
        if observed:refs['items']['enum']=observed
        else:refs['maxItems']=0
    fields={'region':{'enum':list(REGIONS)},'yaw_deg':{'enum':[0,90,-90,180]},'observation_ids':refs}
    reviewed_regions=reviewed_region_choices(reference,quality_constraints)
    if reference:
        # Fixed required keys prevent a model from replacing the reviewed
        # inventory with its smaller observation list. IDs/kinds come from
        # reviewed evidence, not alias guessing or post-hoc model normalization.
        slots={item['id']:{'type':'object','additionalProperties':False,
            'required':list(fields),'properties':copy.deepcopy(fields)} for item in reference['items']}
        for identity,regions in reviewed_regions.items():
            slots[identity]['properties']['region']['enum']=regions
        if revision in (PARAMETRIC_REVISION,GROUNDING_REVISION):
            supports={c:(p,s) for c,p,s in quality_constraints.supports} if quality_constraints else {}
            for item in reference['items']:
                slot=slots[item['id']];slot['properties'].update(_model_fields(item['kind'],
                    reviewed_support=supports.get(item['id']),
                    allowed_parents={i['id']:i['kind'] for i in reference['items'] if i['id']!=item['id']}))
                if item['kind'] in WAREHOUSE_KINDS:slot['properties']['yaw_deg']['enum']=[0]
                slot['required']=list(slot['properties'])
                if quality_constraints and item['id'] in quality_constraints.floor_items:
                    slot['properties']['placement']=dict(type='object',additionalProperties=False,
                        required=['relation','parent_id','part','anchor','elevation_m'],properties=dict(
                            relation={'enum':['floor']},parent_id={'type':'null'},part={'type':'null'},
                            anchor={'enum':['centre']},elevation_m={'type':'null'}))
                choices=dict(quality_constraints.attachments).get(item['id']) if quality_constraints else None
                if choices:
                    slot['properties']['placement']={'anyOf':[dict(type='object',additionalProperties=False,
                        required=['relation','parent_id','part','anchor','elevation_m'],properties=dict(
                            relation={'enum':['drape']},parent_id={'enum':[parent]},part={'enum':[part]},
                            anchor={'enum':['front','left','right','rear']},elevation_m={'type':'null'}))
                        for parent,part in choices]}
        objects={'type':'object','additionalProperties':False,'required':list(slots),'properties':slots}
    else:
        objects={'type':'array','minItems':1,'items':{'type':'object',
            'additionalProperties':False,'required':['id','kind',*fields],
            'properties':{'id':{'type':'string','pattern':_ID.pattern},'kind':{'enum':list(allowed_kinds)},**fields}}}
        if revision in (PARAMETRIC_REVISION,GROUNDING_REVISION):
            objects['items']['properties'].update(_model_fields())
            objects['items']['required']=list(objects['items']['properties'])
        if revision==GROUNDING_REVISION:
            objects['items']['properties'].pop('observation_ids')
            objects['items']['properties']['source']=source_schema(observation)
            objects['items']['required']=list(objects['items']['properties'])
        if revision in (PARAMETRIC_REVISION,GROUNDING_REVISION):
            # Bind parameters to the selected kind without changing home rows.
            from dataclasses import replace
            branches=[]
            for kind in KINDS:
                props=copy.deepcopy(objects['items']['properties'])
                props.pop('warehouse_parameters',None)
                props['kind']={'enum':[kind]}
                props.update(_model_fields(kind))
                if kind in WAREHOUSE_KINDS:props['yaw_deg']['enum']=[0]
                if revision==GROUNDING_REVISION and observation is not None:
                    matching=replace(observation,entities=tuple(e for e in observation.entities
                        if role_of(e) in {'object','unknown'} and e.get('category') in {kind,'unknown'}))
                    props['source']=source_schema(matching)
                branches.append(dict(type='object',additionalProperties=False,
                    required=list(props),properties=props))
            # Exact alternatives avoid optional fields in a strict object
            # schema. Existing home objects do not acquire warehouse fields.
            objects['items']={'anyOf':branches}
    return {'type':'object','additionalProperties':False,
        'required':['layout_version','summary','room','objects'], 'properties':{
        'layout_version':{'const':revision},'summary':{'type':'string','minLength':1,'maxLength':240},
        'room':{'type':'object','additionalProperties':False,'required':['width_m','length_m','height_m'],
            'properties':{'width_m':dimension(0),'length_m':dimension(1),
                'height_m':{'type':'number','minimum':1.8,'maximum':4}}},
        # Actual Nano grammar rejects uniqueItems; compile_layout still checks it.
        'objects':objects}}


def build_layout_body(request, observation, planner_model, reference, *, quality_constraints=None):
    return {'model':planner_model,'temperature':0,'max_tokens':8000,
        'response_format':{'type':'json_schema','json_schema':{
            'name':'twinpulse_compact_photo_layout','strict':True,
            'schema':layout_schema(request.prompt,reference,observation,quality_constraints=quality_constraints,
                                  revision=PARAMETRIC_REVISION if reference else GROUNDING_REVISION)}},
        'messages':[{'role':'system','content':
            'Return a compact illustrative photo-room layout, not tool calls or code. '
            'Emit compact JSON without indentation or trailing whitespace, then end immediately after the final root brace. '
            'Select library model_id, estimated xyz dimensions_m, variant and finish. '
            'Do not calculate world coordinates or collisions: a checked local compiler does that. '
            'Select ONLY observed or explicitly requested objects, never all available kinds. '
            'Preserve every reviewed inventory ID and kind if supplied, including small floor hazards and optional decor. '
            'When reviewed inventory is supplied, objects is a fixed-key object: fill EVERY required entry '
            'with all schema fields; do not emit a shorter array or extra id/kind fields. '
            'Object IDs and evidence IDs have separate roles; reuse a visual entity ID only when citing that actual entity. '
            'For photo-layout-1.3 every object has source: basis visual or inferred requires nonempty observation_ids '
            'and null user_quote; basis user requires empty observation_ids and an exact nonempty quote from user_request. '
            'If a user-requested object is also visible in observations, cite its own visual observation IDs; '
            'being mentioned by the user does not replace coverage of visible evidence. '
            'Reserve user-only source for requested objects absent from the visual observations. '
            'Never cite a bed as evidence for a desk, or a floor/free_space/wall/opening as a physical room object. '
            'Use the observation category to select the model; unknown identity uses inferred source and unknown category. '
            'For legacy reviewed slots only, user-supported objects have observation_ids=[]. '
            'Do not invent hidden objects, measurements, free space, timestamps, robot profiles or missions. '
            'Regions are image-relative: front=near camera/entry, rear=far side; left/right as viewed from entry. '
            'Choose each inventory item independently using its label and evidence. '
            'An observation ID is evidence of identity, NOT a command to copy the region of another object. '
            'Keep each rough region based on the individual evidence, not another object identity. '
            'Choose rough regions, yaw and library parameters; preserve per-model ranges. '
            'placement describes floor, surface (on named parent part), drape (fabric attached at a parent edge), '
            'wall (parent left_wall/right_wall/rear_wall), or ceiling (parent ceiling). '
            'Furniture bed, wardrobe, desk, chair, sofa, dining_table and storage MUST be floor-standing; '
            'never put furniture on another furniture object. '
            'office_chair, floor_fan, clothes_rack, door_leaf, pallet, rack and pallet_stack also stand on the floor. '
            'Use warehouse.pallet for an empty pallet; warehouse.pallet_stack already includes cargo. '
            'Rack and pallet_stack require warehouse_parameters and yaw_deg=0, per the typed schema. '
            'Rack supports are shelf_1 through its selected level_count; pallet supports deck; '
            'loaded pallet supports only stack_top, never its occupied base. '
            'All three dimensions_m are positive metres, never zero. The prop defaults are unmeasured '
            'library estimates: use them as a starting point and adjust only with visual/user support. '
            'Use parent_id/part=null, anchor=centre, elevation_m=null for floor. '
            'Surface uses a furniture parent ID and named top/body/mattress/seat part, centre anchor and null elevation. '
            'Drape uses a named furniture part or clothes_rack/office_chair body with front/left/right/rear anchor; '
            'only hanging_clothes/bedding_overhang/clothing_pile are supported. '
            'A drape anchor places the CHILD CENTRE at the selected parent part edge. '
            'Its width/depth extend on both sides of that edge; bedding_overhang represents '
            'the hanging portion, not an automatically centred full duvet. Use surface for '
            'a supported item when permitted by its typed kind. '
            'Valid parent parts: bed base/mattress/headboard (NEVER body); desk/dining_table top; '
            'wardrobe/storage body; chair seat/back; sofa seat/back; clothes_rack/office_chair body for drape only. '
            'Wall is only window_blind, part=null, centre anchor, estimated centre elevation_m; '
            'ceiling is only ceiling_light, part=null, centre anchor, null elevation. '
            'Do not duplicate attached objects as separate floor items. Keep room dimensions approximate unless stated explicitly by the user; '
            'A supplied estimated_area_review_limit_m2 is an unmeasured photo plausibility limit, not a measured size. '
            'Choose width_m * length_m within it unless the user explicitly specifies room dimensions. '
            'Unmeasured room dimensions, poses and regions may be revised together when packing fails. '
            'Keep explicit user measurements fixed. Follow any supplied reviewed floor_items and allowed drape parents/parts. '
            'Reviewed per-object region enums are mandatory host constraints, not measured coordinates. '
            'preserve explicit width-by-length dimensions. Unknown physical objects use kind=unknown. '
            'Mention uncertainty in a short English summary. The separate Burger asset is NOT a room object.'},
            {'role':'user','content':json.dumps({'user_request':request.prompt,
                'observations':observation.to_dict(),
                'reviewed_inventory':reference['items'] if reference else None,
                'reviewed_label_region_choices':reviewed_region_choices(reference,quality_constraints),
                'model_library':library_for_request(request.prompt),
                'estimated_prop_dimensions_m':{k:list(v) for k,v in SIZES.items()
                    if not reference or k in {i['kind'] for i in reference['items']}},
                **({'reviewed_geometry_constraints':quality_constraints.to_dict(),
                    'geometry_instructions':'Respect reviewed x=right/y=rear positions. Reviewed supported objects '
                        'are placed on the named parent surface by the host, not as separate floor objects. '
                        'Their region is advisory; emit the required surface parent/part, not world coordinates.'}
                   if quality_constraints else {}),
                **({'available_kinds':KINDS} if not reference else {})},ensure_ascii=False,separators=(',',':'))}]}


def compile_layout(value, observation, request, reference, *, quality_constraints=None, check_observer=None,
                   progressive=False):
    def mark(check, status):
        if check_observer is not None:check_observer(check,status)
    mark('input_contract','running')
    source_contract=value.get('layout_version') if isinstance(value,Mapping) else None
    original_value=value
    unresolved=[]
    deferred_ids=set()
    value,grounded_sources,grounding_report=ground_layout(value,observation,request)
    if (not isinstance(value,Mapping) or set(value)!={'layout_version','summary','room','objects'}
            or value['layout_version'] not in (REVISION,LEGACY_REVISION,PARAMETRIC_REVISION) or not isinstance(value['summary'],str)
            or not 1<=len(value['summary'])<=240):raise ValueError('PHOTO_LAYOUT_SHAPE_INVALID')
    room=value['room']
    if not isinstance(room,Mapping) or set(room)!={'width_m','length_m','height_m'}:
        raise ValueError('PHOTO_LAYOUT_ROOM_INVALID')
    width,length,height=(room[k] for k in ('width_m','length_m','height_m'))
    if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (width,length,height))
            or not 2<=width<=12 or not 2<=length<=12 or not 1.8<=height<=4):
        raise ValueError('PHOTO_LAYOUT_DIMENSIONS_INVALID')
    explicit=requested_size(request.prompt)
    if explicit and (width,length)!=explicit:raise ValueError('PHOTO_LAYOUT_USER_DIMENSIONS_CHANGED')
    objects=value['objects']; observed={e['id'] for e in observation.entities}
    unknown_ids={e['id'] for e in observation.entities if e['kind']=='unknown' or role_of(e)=='unknown'}
    reviewed={i['id']:i for i in reference['items']} if reference else {}
    if quality_constraints is not None:
        from twinpulse_core.photo_quality import checked_constraints
        digest=hashlib.sha256(request.images[0].content).hexdigest() if len(request.images)==1 else ''
        checked_constraints(quality_constraints,digest)
        if (not reference or reference['image_sha256']!=digest
                or dict(quality_constraints.required_items)!={i:k['kind'] for i,k in reviewed.items()}):
            raise ValueError('PHOTO_CONSTRAINTS_INVENTORY_MISMATCH')
    supports={c:(p,s) for c,p,s in quality_constraints.supports} if quality_constraints else {}
    parametric=value['layout_version']==PARAMETRIC_REVISION
    extra=set(_model_fields()) if parametric else set()
    # Preserve the independent post-compile quality gate for position/support
    # failures. Literal inventory labels alone are also a local input contract.
    legal_regions=reviewed_region_choices(reference,None)
    if reviewed and value['layout_version'] in (REVISION,PARAMETRIC_REVISION):
        if not isinstance(objects,Mapping):raise ValueError('PHOTO_LAYOUT_REVIEWED_SLOTS_REQUIRED')
        if set(objects)!=set(reviewed):
            raise ValueError('PHOTO_LAYOUT_REVIEWED_ITEMS_MISSING_OR_EXTRA: missing='+
                ','.join(sorted(set(reviewed)-set(objects)))[:240])
        normalized=[]
        for identity,item in objects.items():
            expected_extra=set(_model_fields(reviewed[identity]['kind'])) if parametric else set()
            if not isinstance(item,Mapping) or set(item)!={'region','yaw_deg','observation_ids'}|expected_extra:
                raise ValueError('PHOTO_LAYOUT_REVIEWED_SLOT_SHAPE_INVALID: '+identity)
            normalized.append(dict(id=identity,kind=reviewed[identity]['kind'],**item))
        objects=normalized
    if not isinstance(objects,list) or not objects:raise ValueError('PHOTO_LAYOUT_OBJECTS_INVALID')
    from .scene_capacity import SEMANTIC_PAYLOAD_BYTES, checked_payload_bytes
    checked_payload_bytes(objects, SEMANTIC_PAYLOAD_BYTES, 'SEMANTIC_PAYLOAD_BUDGET_REACHED')
    ids=set();represented=set(); rows=[]
    for item in objects:
        expected_extra=set(_model_fields(item.get('kind'))) if parametric and isinstance(item,Mapping) else extra
        if (not isinstance(item,Mapping) or set(item)!={'id','kind','region','yaw_deg','observation_ids'}|expected_extra
                or not isinstance(item['id'],str) or not _ID.fullmatch(item['id']) or item['id'] in ids
                or not isinstance(item['kind'],str) or item['kind'] not in KINDS
                or not parametric and item['kind'] in WAREHOUSE_KINDS
                or not isinstance(item['region'],str) or item['region'] not in REGIONS
                or type(item['yaw_deg']) not in (int,float) or item['yaw_deg'] not in (0,90,-90,180)
                or not isinstance(item['observation_ids'],list) or len(item['observation_ids'])>3
                or any(not isinstance(x,str) for x in item['observation_ids'])
                or len(set(item['observation_ids']))!=len(item['observation_ids'])):
            raise ValueError('PHOTO_LAYOUT_OBJECT_INVALID: category, region, unique ID or observed references')
        invalid=set(item['observation_ids'])-observed
        if invalid:raise ValueError('PHOTO_LAYOUT_UNOBSERVED_REFERENCES: object='+item['id']+
            ', invalid='+','.join(sorted(invalid))[:200]+'; reviewed IDs are not visual evidence IDs')
        ids.add(item['id']);represented.update(item['observation_ids'])
        if item['id'] in reviewed and item['kind']!=reviewed[item['id']]['kind']:
            raise ValueError('PHOTO_LAYOUT_REVIEWED_KIND_CHANGED: '+item['id'])
        if item['id'] in legal_regions and item['region'] not in legal_regions[item['id']]:
            raise ValueError('PHOTO_LAYOUT_REVIEWED_POSITION_INVALID: '+item['id'])
        if item['id'] not in reviewed and not item['observation_ids'] and item['id'] not in grounded_sources:
            raise ValueError('PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE: '+item['id'])
        rows.append(dict(item))
    missing=set(reviewed)-ids
    if missing:raise ValueError('PHOTO_LAYOUT_REVIEWED_ITEMS_MISSING: '+','.join(sorted(missing)))
    required={e['id'] for e in observation.entities if role_of(e) in {'object','unknown'}}
    if not reference and required-represented:
        raise ValueError('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING: '+','.join(sorted(required-represented)))
    mark('input_contract','passed')
    mark('model_relations','running')
    relations=_checked_model_relations(rows,height,supports,quality_constraints) if parametric else {}
    mark('model_relations','passed')
    if parametric:
        supports={i:(r['parent_id'],r['part']) for i,r in relations.items() if r['relation']=='surface'}
    calls=[dict(call_id='floor',tool='create_floor',arguments=dict(id='floor',center_m=[0,0],size_m=[width,length]))]
    evidence=[dict(call_id='floor',basis='user' if explicit else 'inferred',observation_ids=[],
        note='User dimensions' if explicit else 'Estimated room dimensions; not measured')]
    for name,x,y,sx,sy in (('left',-width/2,0,.08,length),('right',width/2,0,.08,length),('rear',0,length/2,width,.08)):
        calls.append(dict(call_id=name+'_wall',tool='create_wall',arguments=dict(id=name+'_wall',
            position_m=[x,y,height/2],dimensions_m=[sx,sy,height],yaw_deg=0)))
        evidence.append(dict(call_id=name+'_wall',basis='inferred',observation_ids=[],note='Estimated open-front rectangular shell'))
    mark('floor_packing','running')
    placed=[]; placements=[]; packing_failures=[]; packing_search=None;footprints={};assemblies={}
    def footprint(item):
        if item['id'] in footprints:return footprints[item['id']]
        bounds,diagnostic=_floor_assembly_bounds(item,rows,relations,parametric=parametric)
        assemblies[item['id']]=(bounds,_assembly_domain_diagnostic(item,bounds,diagnostic,width,length))
        sx,sy=bounds[1]-bounds[0],bounds[3]-bounds[2]
        footprints[item['id']]=(sx,sy)
        return sx,sy
    def local_bounds(item):
        footprint(item)
        return assemblies[item['id']][0]
    def emit_floor(item,x,y):
        call_id='obj_'+item['id'];kind=item['kind']
        if kind in WAREHOUSE_KINDS:
            tool,args=warehouse_arguments(item,[x,y])
        elif kind in furniture_kinds():
            args=dict(id=item['id'],kind=kind,catalog_version='furniture-blocks-1.0',center_m=[x,y],yaw_deg=item['yaw_deg'])
            if parametric:
                from twinpulse_core.model_library import PARAMETRIC_FURNITURE_VERSION
                args.update(catalog_version=PARAMETRIC_FURNITURE_VERSION,dimensions_m=list(item['dimensions_m']),
                            variant=item['variant'],finish=item['finish'])
            tool='place_furniture'
        else:
            size=item['dimensions_m'] if parametric else SIZES[kind];z=size[2]/2
            if not parametric:
                if kind in {'monitor','tabletop_item'}:z+=.75
                if kind=='window_blind':z+=1
                if kind=='ceiling_light':z=height-size[2]/2
            args=dict(id=item['id'],kind=kind,label=reviewed.get(item['id'],{}).get('label',kind.replace('_',' ')),
                catalog_version=room_item_catalog_version(kind),position_m=[x,y,z],dimensions_m=list(size),
                yaw_deg=item['yaw_deg'],observation_time_utc=None)
            tool='place_room_item'
        calls.append(dict(call_id=call_id,tool=tool,arguments=args))
        evidence.append(dict(call_id=call_id,basis='inferred' if set(item['observation_ids']) & unknown_ids else
            'visual' if item['observation_ids'] else 'user' if item['id'] in reviewed or item['id'] in grounded_sources else 'inferred',
            observation_ids=item['observation_ids'],note='Object evidence only; grid placement and dimensions estimated, not measured'))
        placements.append(dict(id=item['id'],region=item['region'],centre_xy_m=[x,y]))
    # Large footprints first, stable by ID; every selected object must fit.
    coverings={item['id'] for item in rows if item['kind']=='floor_covering'}
    attached=({i for i,r in relations.items() if r['relation']!='floor'} if parametric else set(supports))|coverings
    from .packing_candidates import floor_candidates
    greedy_diagnostics=[]
    for item in sorted((i for i in rows if i['id'] not in attached),
                       key=lambda i:(-math.prod(footprint(i)),i['id'])):
        bounds=local_bounds(item);xmin,xmax,ymin,ymax=_floor_domain(bounds,width,length)
        row,col=item['region'].split('_');cx={'left':-1,'centre':0,'right':1}[col]*width/3
        cy={'front':-1,'middle':0,'rear':1}[row]*length/3
        candidates=[];domain_count=0;overlap_pruned=0;blocked_by={}
        for priority,x,y in floor_candidates(bounds,width,length,item['region'],placed):
            if priority and candidates:
                break  # A valid old grid choice needs no additional contacts.
            domain_count+=1
            collisions=[other_id for other_id,px,py,other in placed
                if not _packing_separated(bounds,x,y,other,px,py)]
            if not collisions:
                candidates.append((priority,(x-cx)**2+(y-cy)**2,x,y))
            else:
                overlap_pruned+=1
                for other_id in collisions:blocked_by[other_id]=blocked_by.get(other_id,0)+1
        greedy_diagnostics.append(dict(id=item['id'],domain_count=domain_count,
            available_count=len(candidates),overlap_pruned=overlap_pruned))
        if not candidates:
            # Offer counts, not an automatically applied coordinate correction.
            # These are conservative synthetic proxy slots, never sensed free space.
            counts={region:0 for region in REGIONS}
            for ix in range(math.ceil(xmin*10),math.floor(xmax*10)+1):
                x=ix/10
                for iy in range(math.ceil(ymin*10),math.floor(ymax*10)+1):
                    y=iy/10
                    if not all(_packing_separated(bounds,x,y,other,px,py) for _,px,py,other in placed):
                        continue
                    for region in REGIONS:
                        rr,cc=region.split('_')
                        if ((cc=='left' and x>-.05) or (cc=='right' and x<.05)
                                or (cc=='centre' and abs(x)>width/6)
                                or (rr=='front' and y>-.05) or (rr=='rear' and y<.05)
                                or (rr=='middle' and abs(y)>length/6)):
                            continue
                        counts[region]+=1
            permitted=reviewed_region_choices(reference,quality_constraints).get(item['id'],list(REGIONS))
            report=dict(schema_version='photo-layout-packing-diagnostic-1.0',
                geometry_status='SYNTHETIC_PROXY_NOT_MEASURED_FREE_SPACE',
                failed_id=item['id'],failed_region=item['region'],room_size_m=[width,length],
                floor_must_not_expand=bool(explicit or any(c.tool=='create_floor' and c.argument_path.split('.')[0]=='size_m' for c in request.measurement_constraints)),inventory_must_not_shrink=True,
                remaining_ids=[r['id'] for r in rows if r['id'] not in {p['id'] for p in placements}
                    and r['id'] not in attached],
                region_counts={region:sum(r['region']==region and r['id'] not in attached for r in rows)
                    for region in REGIONS},
                inventory_regions=[dict(id=r['id'],kind=r['kind'],region=r['region'],
                    footprint_m=list(footprint(r))) for r in rows if r['id'] not in attached],
                failed_assembly=copy.deepcopy(assemblies[item['id']][1]),
                failed_grid=dict(domain_count=domain_count,available_count=0,blocked_candidate_count=overlap_pruned),
                placed_blockers=[dict(id=other_id,blocked_candidate_count=blocked_by[other_id],centre_xy_m=[px,py],
                    translated_proxy_xy_bounds_m=[px+other[0],px+other[1],py+other[2],py+other[3]],
                    dependency_ids=[child['id'] for child in assemblies[other_id][1]['contributing_children']])
                    for other_id,px,py,other in placed if other_id in blocked_by],
                failed_item_alternative_region_slot_counts={r:n for r,n in counts.items() if r in permitted},
                note='Counts consider the already placed proxies only; they do not guarantee all remaining objects fit. '
                    'Revise crowded assignments for all remaining items, obey reviewed enums and photo relations. '
                    'An empty floor axis cannot be fixed by changing region alone: inspect the typed parent/child/anchor estimates, '
                    'A placed blocker may need an atomic request_scope plus parent/child update; region-only changes may not resolve the occupied assembly. '
                    'keep measured values, keepouts and margins unchanged. '
                    'Do not repeat the identical failed regions or claim these candidates are robot-safe.')
            packing_failures.append(report)
            continue
        _,_,x,y=min(candidates);placed.append((item['id'],x,y,bounds))
        emit_floor(item,x,y)
    if packing_failures:
        floor_rows=[i for i in rows if i['id'] not in attached]
        centres,packing_search=_bounded_region_repack(floor_rows,footprint,width,length,local_bounds=local_bounds)
        if centres is None and packing_search['termination_code'] in ('BRANCH_BUDGET_EXHAUSTED','NODE_BUDGET_EXHAUSTED'):
            first_search=packing_search
            centres,packing_search=_bounded_region_repack(floor_rows,footprint,width,length,
                local_bounds=local_bounds,max_nodes=2048,branch_cap=96,timeout_s=2.)
            packing_search['previous_search']=first_search
            packing_search['search_attempts']=2
        if centres is not None:
            if set(centres)!={i['id'] for i in floor_rows}:raise ValueError('PHOTO_LAYOUT_SEARCH_INVENTORY_CHANGED')
            # Discard only this compile's temporary emitted calls, never source
            # data, room dimensions, model parameters, regions or saved history.
            calls=calls[:4];evidence=evidence[:4];placements=[];packing_failures=[]
            for item in sorted(floor_rows,key=lambda i:(-math.prod(footprint(i)),i['id'])):
                emit_floor(item,*centres[item['id']])
    if packing_failures:
        report=packing_failures[0]
        if packing_search is not None:report['bounded_search']=packing_search
        report['packing_failures']=[dict(id=f['failed_id'],region=f['failed_region'],
            alternative_region_slot_counts=f['failed_item_alternative_region_slot_counts'])
            for f in packing_failures]
        report['unplaced_ids']=[f['failed_id'] for f in packing_failures]
        report['greedy_attempts']=greedy_diagnostics
        conflicts=[dict(id=f['failed_id'],region=f['failed_region'],grid=f['failed_grid'],
            assembly=f['failed_assembly'],placed_blockers=f['placed_blockers'],
            dependency_ids=[child['id'] for child in f['failed_assembly']['contributing_children']])
            for f in packing_failures]
        report['conflict_set']=dict(schema_version='photo-packing-conflict-set-1.0',failed_ids=sorted(f['id'] for f in conflicts),
            conflicts=conflicts[:32],complete=len(conflicts)<=32,physical_authority=False,
            placed_assemblies=[dict(id=identity,centre_xy_m=[x,y],
                translated_proxy_xy_bounds_m=[x+b[0],x+b[1],y+b[2],y+b[3]],assembly=assemblies[identity][1])
                for identity,x,y,b in placed[:32]],
            evidence_basis='GREEDY_OCCUPIED_PROXY_GRID_NOT_GLOBAL_INFEASIBILITY',
            comparison='Floor packing remains failed; failed counts or first-target changes are not checked progress/regression')
        report['feasibility_scope']='BOUNDED_GREEDY_AND_SAME_REGION_GRID_NOT_GLOBAL_INFEASIBILITY_PROOF'
        raise PhotoLayoutPackingError(report['failed_id'],report['failed_region'],report)
    # A declared floor covering is a layer, not another floor-standing piece
    # of furniture. Its bounds and original conservative motion keepout remain
    # checked/emitted; overlapping it does not make a route robot-safe.
    for item in (row for row in rows if row['id'] in coverings):
        bounds=local_bounds(item)
        candidates=list(floor_candidates(bounds,width,length,item['region']))
        if not candidates:
            raise ValueError('PHOTO_LAYOUT_FLOOR_COVERING_OUTSIDE_ROOM: '+item['id'])
        rr,cc=item['region'].split('_')
        cx={'left':-1,'centre':0,'right':1}[cc]*width/3
        cy={'front':-1,'middle':0,'rear':1}[rr]*length/3
        _,x,y=min(candidates,key=lambda point:(point[0],(point[1]-cx)**2+(point[2]-cy)**2))
        emit_floor(item,x,y)
    mark('floor_packing','passed')
    mark('support_packing','running')
    support_searches=[]
    if supports:
        from twinpulse_core.photo_quality import support_surface, support_geometry
        from .support_packing import grid_indices, bounded_support_repack
        row_by_id={i['id']:i for i in rows}
        parents={c['arguments']['id']:c['arguments'] for c in calls
            if c['tool'] in {'place_furniture','create_rack_row','place_pallet_stack'} or
                c['tool']=='place_room_item' and c['arguments']['kind']=='pallet'}
        occupied={}
        occupied_ids={}
        support_issues=[]
        def collect_support_error(error):
            support_issues.extend(error.contract_report['issues'])
        def support_failure(identity, parent_id, part, reason, item, parent):
            from twinpulse_core.geometry_diagnostics import GeometryValidationError, geometry_issue
            alternatives = []
            for candidate_id, candidate_parent in sorted(parents.items()):
                if candidate_id == identity:
                    continue
                parent_kind = row_by_id[candidate_id]['kind']
                for candidate_part in support_parts(parent_kind,
                        parameters=row_by_id[candidate_id].get('parameters')):
                    candidate_surface = support_surface(candidate_parent, candidate_part)
                    if candidate_surface is None:
                        continue
                    dims = candidate_surface.shape.dimensions_m
                    child_size = item.get('dimensions_m')
                    if child_size is None:
                        continue
                    angle = math.radians(item['yaw_deg'] - parent_yaw(candidate_parent))
                    footprint = [abs(math.cos(angle))*child_size[0]+abs(math.sin(angle))*child_size[1],
                                 abs(math.sin(angle))*child_size[0]+abs(math.cos(angle))*child_size[1]]
                    alternatives.append(dict(parent_id=candidate_id, part=candidate_part,
                        surface_size_m=list(dims[:2]), rotated_footprint_m=footprint,
                        footprint_fits=all(footprint[i]+.02 <= dims[i] for i in range(2)),
                        clearance_and_photo_relation='requires_revalidation'))
            return GeometryValidationError([geometry_issue('PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',identity,
                actual={'child':item,'parent':parent,'reason':reason},
                expected={'parent_id':parent_id,'part':part,'constraint':'all children fit a valid support surface',
                    'reason_code':reason,'unit':'m','support_options':alternatives,
                    'repair_note':'Choose a photo-consistent named surface with sufficient footprint; '
                        'a thin vertical panel top is not a shelf. Options describe geometry only, '
                        'not photo truth or scope authority. Change the parent/part or a supported model '
                        'estimate explicitly; preserve inventory and recheck all children.'},
                related_ids=[parent_id,*occupied_ids.get((parent_id,part),[])])])
        def emit_supported(identity,args,parent_id,part):
            args={**args,'label':reviewed.get(identity,{}).get('label',row_by_id[identity]['kind'].replace('_',' '))}
            call_id='obj_'+identity
            calls.append(dict(call_id=call_id,tool='place_room_item',arguments=args))
            evidence.append(dict(call_id=call_id,basis='inferred' if set(row_by_id[identity]['observation_ids']) & unknown_ids else
                'visual' if row_by_id[identity]['observation_ids'] else 'user',
                observation_ids=row_by_id[identity]['observation_ids'],
                note='Selected parent support; catalogue surface and child placement estimated, not measured'))
            placements.append(dict(id=identity,region=row_by_id[parent_id]['region'],
                requested_region=row_by_id[identity]['region'],centre_xy_m=args['position_m'][:2],parent=parent_id,support_part=part))
        for identity,(parent_id,part) in sorted(supports.items()):
            item=row_by_id[identity];parent=parents.get(parent_id)
            if parent is None or item['kind'] in furniture_kinds():
                collect_support_error(support_failure(identity,parent_id,part,'PARENT_MODEL_UNAVAILABLE',item,parent))
                continue
            surface=support_surface(parent,part)
            if surface is None:
                collect_support_error(support_failure(identity,parent_id,part,'SUPPORT_SURFACE_UNAVAILABLE',item,parent))
                continue
            size=item['dimensions_m'] if parametric else SIZES[item['kind']];px,py,pz=surface.transform.position_m
            sx,sy,sz=surface.shape.dimensions_m
            angle=math.radians(parent_yaw(parent));co,si=math.cos(angle),math.sin(angle)
            relative=math.radians(item['yaw_deg']-parent_yaw(parent))
            hx=(abs(math.cos(relative))*size[0]+abs(math.sin(relative))*size[1])/2
            hy=(abs(math.sin(relative))*size[0]+abs(math.cos(relative))*size[1])/2
            previous=occupied.setdefault((parent_id,part),[])
            candidates=[]
            blocked_parent_parts=set()
            for ix in grid_indices(-sx/2+hx+.01,sx/2-hx-.01):
                for iy in grid_indices(-sy/2+hy+.01,sy/2-hy-.01):
                    lx,ly=ix/20,iy/20
                    if all(abs(lx-x)>=hx+ox+.025 or abs(ly-y)>=hy+oy+.025 for x,y,ox,oy in previous):
                        probe=dict(id=identity,kind=item['kind'],label=item['kind'],catalog_version='room-items-1.0',
                            position_m=[px+lx*co-ly*si,py+lx*si+ly*co,pz+sz/2+size[2]/2],
                            dimensions_m=list(size),yaw_deg=item['yaw_deg'],observation_time_utc=None)
                        geometry=support_geometry(probe,parent,part)
                        blocked_parent_parts.update(geometry.get('parent_collision_ids',[]))
                        if geometry['status']=='PASS':
                            candidates.append((lx*lx+ly*ly,lx,ly))
            if not candidates:
                collect_support_error(support_failure(identity,parent_id,part,
                    'SUPPORT_CLEARANCE_EXCEEDED' if blocked_parent_parts else 'SURFACE_CAPACITY_EXCEEDED',
                    {**item,'rotated_footprint_m':[2*hx,2*hy],'surface_size_m':[sx,sy],
                     'surface_top_m':pz+sz/2,'rejected_parent_parts':sorted(blocked_parent_parts)},parent))
                continue
            _,lx,ly=min(candidates);previous.append((lx,ly,hx,hy))
            occupied_ids.setdefault((parent_id,part),[]).append(identity)
            args=dict(id=identity,kind=item['kind'],label=reviewed.get(identity,{}).get('label',item['kind'].replace('_',' ')),
                catalog_version='room-items-1.0',position_m=[px+lx*co-ly*si,py+lx*si+ly*co,pz+sz/2+size[2]/2],
                dimensions_m=list(size),yaw_deg=item['yaw_deg'],observation_time_utc=None)
            if support_geometry(args,parent,part)['status']!='PASS':
                collect_support_error(support_failure(identity,parent_id,part,'DERIVED_SUPPORT_GEOMETRY_FAILED',args,parent))
                continue
            emit_supported(identity,args,parent_id,part)
        # Reconsider earlier temporary placements on each failed support group.
        # Never relocate to another parent, resize/drop an item or edit saved history.
        failed_groups={(issue['expected']['parent_id'],issue['expected']['part']) for issue in support_issues
            if issue['actual']['reason'] in {'SURFACE_CAPACITY_EXCEEDED','SUPPORT_CLEARANCE_EXCEEDED'}}
        for parent_id,part in sorted(failed_groups):
            group=[{**row_by_id[identity],'dimensions_m':list(row_by_id[identity]['dimensions_m']
                    if parametric else SIZES[row_by_id[identity]['kind']])}
                for identity,key in supports.items() if key==(parent_id,part)]
            found,search=bounded_support_repack(group,parents[parent_id],part)
            support_searches.append(search)
            if found is None:
                for issue in support_issues:
                    if (issue['expected']['parent_id'],issue['expected']['part'])==(parent_id,part):
                        issue['expected']['bounded_search']=search
                continue
            identities={item['id'] for item in group};call_ids={'obj_'+identity for identity in identities}
            calls[:]=[call for call in calls if call['arguments']['id'] not in identities]
            evidence[:]=[entry for entry in evidence if entry['call_id'] not in call_ids]
            placements[:]=[entry for entry in placements if entry['id'] not in identities]
            for identity,args in sorted(found.items()):emit_supported(identity,args,parent_id,part)
            support_issues[:]=[issue for issue in support_issues
                if (issue['expected']['parent_id'],issue['expected']['part'])!=(parent_id,part)]
        if support_issues:
            from twinpulse_core.geometry_diagnostics import GeometryValidationError
            # Parent/structural/invalid input/internal checker errors stay hard.
            if not progressive or not parametric or any(issue['actual']['reason'] not in
                    {'SURFACE_CAPACITY_EXCEEDED','SUPPORT_CLEARANCE_EXCEEDED'} for issue in support_issues):
                raise GeometryValidationError(support_issues)
            from twinpulse_core.progressive_twin import pending_support_geometry,pending_support_eligible
            pending=[]
            for issue in support_issues:
                identity=issue['target_ids'][0]
                item=row_by_id[identity]
                parent_id,part=supports[identity]
                if not pending_support_eligible(item):raise GeometryValidationError(support_issues)
                # A native supported room prop may remain draft-only pending;
                # this does not make its omitted hazard safe for any task.
                # Furniture/floor/invalid parent/model cases are never eligible.
                hazard,bounds=pending_support_geometry(item,parents[parent_id],part)
                pending.append(dict(id=identity,parent_id=parent_id,part=part,code=issue['code'],
                    reason=issue['actual']['reason'],status='deferred',
                    hazard=hazard,bounds_z_m=bounds,impact='task_context_required',
                    uncertainty='estimated_support_not_world_verified',source=copy.deepcopy(grounded_sources.get(identity,{})),
                    evidence=copy.deepcopy(issue)))
            unresolved.extend(pending)
            deferred_ids.update(item['id'] for item in pending)
    mark('support_packing','partial' if unresolved else 'passed')
    mark('attachment_placement','running')
    if parametric:
        _place_attachments(rows,relations,calls,evidence,placements,reviewed,width,length,height)
    mark('attachment_placement','passed')
    mark('tool_executor','running')
    # Keep the validated source basis when lowering the new wire contract.
    # In particular, user-described supported items are not visual observations.
    for entry in evidence:
        identity=entry['call_id'].removeprefix('obj_')
        if identity in grounded_sources:
            entry['basis']=grounded_sources[identity]['basis']
    plan=SiteToolPlan.from_dict(dict(plan_version='2.2',scene_id='photo_room',
        summary=(value['summary']+(' Reviewed parent supports are derived from catalogue geometry; '
            'other placement/attachment remains approximate, not a reconstructed room.' if supports else
            ' Separate regional inventory proxies, not a reconstructed room. '
            'Coordinates and sizes are estimated; support/attachment relationships are not reconstructed.'))[:500],
        image_observations=(observation.summary+' '+value['layout_version']+': synthetic region-constrained spacing; unknown areas are not verified free space.')[:1000],
        calls=calls,call_evidence=evidence))
    execute_site_tool_plan(plan,source='photo',source_ref=canonical_sha256(value))
    mark('tool_executor','passed')
    mark('placement_validation','running')
    if parametric:
        from twinpulse_core.photo_placement import validate_placement_plan, PLACEMENT_VERSION
        validate_placement_plan(plan,dict(schema_version=PLACEMENT_VERSION,
            relations=[dict(id=i['id'],**i['placement']) for i in rows if i['id'] not in deferred_ids]))
    mark('placement_validation','passed')
    from twinpulse_core.progressive_twin import envelope, checked_envelope
    progressive_record=(checked_envelope(envelope(plan.to_dict(),rows,unresolved,canonical_sha256(original_value)),
        plan.to_dict()) if progressive else None)
    return plan.to_dict(),dict(contract=source_contract,compiler_revision=BOUNDARY_PACKING_COMPILER_REVISION, prior_recipe_revision=SIGNED_PACKING_COMPILER_REVISION if any(
        value[1]['contributing_children'] for value in assemblies.values()) else SUPPORT_COMPILER_REVISION if supports else 'photo-layout-compiler-1.6' if any(i['kind'] in (*WAREHOUSE_KINDS,'pallet') for i in rows) else 'photo-layout-compiler-1.5' if grounding_report else 'photo-layout-compiler-1.4' if packing_search else PARAMETRIC_COMPILER_REVISION if parametric else REVISION,
        **({'progressive_twin':progressive_record} if progressive_record else {}),
        geometry_status='ESTIMATED_NOT_MEASURED',
        layout_sha256=canonical_sha256(original_value),placements=placements,
        floor_assemblies=[copy.deepcopy(assemblies[identity][1]) for identity in sorted(assemblies)],
        **({'grounding':grounding_report,'coordinate_frame':'photo_view_right_rear'} if grounding_report else {}),
        placement_relationships='MODEL_RELATIONS_ESTIMATED' if parametric else 'REVIEWED_SUPPORTS_ESTIMATED' if supports else 'NOT_RECONSTRUCTED',
        **({'bounded_packing_search':packing_search} if packing_search is not None else {}),
        **({'bounded_support_searches':support_searches} if support_searches else {}),
        **({'model_parameters':[dict(id=i['id'],model_id=i['model_id'],dimensions_m=list(i['dimensions_m']),
              variant=i['variant'],finish=i['finish'],placement=dict(i['placement']),
              **({'warehouse_parameters':dict(i['warehouse_parameters'])} if i['kind'] in WAREHOUSE_KINDS else {})) for i in rows if i['id'] not in deferred_ids]} if parametric else {}),
        production_default=False,physical_authority=False)
