# SPDX-License-Identifier: Apache-2.0
"""Photo-space candidates only. No metric position, navigation or Apply rights."""
from copy import deepcopy
import math
import re
from .environment_navigation import convex_overlap_area
from .environment_overlays import KINDS as OVERLAY_KINDS,checked_overlay_floor,footprint,overlay_objects
from .environment_source import MOVABLE,mesh_points
from .furniture import furniture_kinds
from .room_item_catalog import ROOM_ITEM_KINDS,WALL_ITEMS,CEILING_ITEMS
from .warehouse_models import WAREHOUSE_KINDS

VERSION='environment-photo-candidates-1.2'
MAX_CANDIDATES=6
# The model-library vocabulary (34 names, equal to photo_layout.KINDS), not only the 10 overlay kinds.
PHOTO_KINDS=(*furniture_kinds(),*ROOM_ITEM_KINDS,*WAREHOUSE_KINDS)
# Recognised but never added: an overlay is a floor-resting box (z=h/2).
NOT_ADDABLE=frozenset((*WALL_ITEMS,*CEILING_ITEMS,'surface_covering','door_leaf'))
# The only kind enum a fresh call may use: overlay kinds first, then kinds added as a labelled unknown box.
PROPOSABLE_KINDS=(*OVERLAY_KINDS,*(k for k in PHOTO_KINDS if k not in OVERLAY_KINDS and k not in NOT_ADDABLE))
# Per saved version: (max candidates, kinds, id pattern, rows name a 'near' anchor). Saved 1.0/1.1 jobs stay readable with their own limits.
LIMITS={'environment-photo-candidates-1.0':(3,OVERLAY_KINDS,'Candidate_[1-3]',False),
    'environment-photo-candidates-1.1':(6,PHOTO_KINDS,'Candidate_[1-6]',False),VERSION:(6,PHOTO_KINDS,'Candidate_[1-6]',True)}
SCANNED_CONTEXT_LIMIT=64
CATALOG_SIZES={'floor_fan':(.4,.4,1.1),'basket':(.35,.3,.4),'bag':(.3,.25,.35),'box':(.3,.3,.3),
    'clothing_pile':(.35,.25,.15),'cable_bundle':(.3,.2,.04),'power_adapter':(.12,.08,.05),
    'power_strip':(.3,.08,.05),'small_equipment':(.3,.3,.3),'unknown':(.3,.3,.3),
    # model_library.FURNITURE_MODELS defaults
    'bed':(1.4,2.,.9),'wardrobe':(1.2,.645,1.9),'desk':(1.2,.6,.74),'chair':(.46,.44,.93),'sofa':(1.6,.8,.85),
    'dining_table':(1.4,.8,.77),'storage':(.8,.445,.9),
    # photo_layout.SIZES planner defaults
    'office_chair':(.6,.6,.9),'clothes_rack':(.7,.45,1.5),'door_leaf':(.08,.65,1.9),'hanging_clothes':(.35,.2,.7),
    'bedding_overhang':(.4,.18,.15),'monitor':(.45,.15,.35),'tabletop_item':(.2,.2,.2),'window_blind':(.8,.08,.8),
    'ceiling_light':(.3,.3,.12),'pallet':(1.2,.8,.12),'floor_covering':(1.2,.8,.02),'surface_covering':(1.,.7,.03),
    'wall_fixture':(.3,.05,.3),'ceiling_fixture':(.4,.4,.05),'wall_storage':(1.2,.35,.6),
    # no library default (warehouse_models.RANGES only): editable placeholders
    'rack':(1.2,.6,2.),'pallet_stack':(1.2,.8,1.2)}
# Scan categories/prim names (RoomPlan "Bed0" is category unknown) that may already be the recognised kind.
SCAN_NAMES={'bed':{'bed'},'chair':{'chair'},'office_chair':{'chair'},'sofa':{'sofa'},'desk':{'table'},'dining_table':{'table'},
    'storage':{'storage','refrigerator'},'wardrobe':{'storage','refrigerator'},'rack':{'storage'},'monitor':{'television'}}
NOT_CONTEXT={'floor','wall','door','window','opening'}
# Local anchor placement: gaps from the anchor footprint, box clearance to every other object (below the smallest gap).
SUGGESTION_GAPS_M=(.05,.10,.20,.30,.40)
SUGGESTION_CLEARANCE_M=.03
DOORWAYS={'door','opening'}
DOOR_CLEAR_M=.8  # suggestions only: the passage in front of a door or opening is never a suggested spot
NOT_SUGGESTED=frozenset(('floor_covering','surface_covering'))  # a covering would become a keepout box over walkable floor


def overlay_kind_for(kind):
    """Overlay kind an adopted candidate becomes; None = recognised only. Never widens overlay KINDS."""
    if kind in OVERLAY_KINDS:return kind
    return None if kind not in PHOTO_KINDS or kind in NOT_ADDABLE else 'unknown'


def _name(label):return ''.join(c for c in label if not c.isdigit()).lower()


def photo_context(environment,receipts):
    """Names/types only, no geometry, coordinates or colours. receipts: {overlay_id: recognised kind}."""
    meshes=[m for m in environment['meshes'] if m['category'] not in NOT_CONTEXT and _name(m['label']) not in NOT_CONTEXT]
    meshes=[m for m in meshes if m['category'] in MOVABLE]+[m for m in meshes if m['category'] not in MOVABLE]
    return dict(existing_props=[dict(kind=receipts.get(o['item']['id'],o['item']['kind']),label=o['item']['label'][:80])
            for o in environment.get('overlays',[])][:32],
        scanned_objects=[dict(category=m['category'],label=m['label'][:80]) for m in meshes][:SCANNED_CONTEXT_LIMIT])


def possible_duplicates(kind,environment,receipts):
    """Labels that may already be this object, strongest first: a hint for the required human check, never identity."""
    overlays=environment.get('overlays',[]);target=overlay_kind_for(kind)
    if kind=='unknown':labels=[o['item']['label'] for o in overlays if o['item']['kind']=='unknown']
    else:
        names=SCAN_NAMES.get(kind,set());added=lambda match:[o['item']['label'] for o in overlays if match(o)]
        # Same recognised kind, then same overlay kind, then scanned names; anonymous LiDAR outlines only fill what is left of the 8.
        labels=[*added(lambda o:receipts.get(o['item']['id'])==kind),*added(lambda o:target not in (None,'unknown') and o['item']['kind']==target),
            *(m['label'] for m in environment['meshes'] if m['category'] in names or _name(m['label']) in names),
            *added(lambda o:target=='unknown' and o['evidence']['basis']=='lidar_estimate')]
    return list(dict.fromkeys(labels))[:8]


def context_labels(context):
    """The only names a fresh reply may give as 'near': exactly the labels that were sent, in order, once each."""
    return list(dict.fromkeys(r['label'] for key in ('scanned_objects','existing_props') for r in context[key]))


def checked_photo_candidates(value,*,fresh=False,context=None):
    """fresh: a new model reply, which must be exactly VERSION with a proposable kind, checked against the context that was
    sent (required): 'near' is one of its labels or null. A saved job is read with its own version's limits."""
    if fresh and context is None:raise ValueError('PHOTO_CANDIDATE_CONTEXT_REQUIRED')
    limits=LIMITS.get(value.get('schema_version')) if isinstance(value,dict) and isinstance(value.get('schema_version'),str) else None
    if (not isinstance(value,dict) or set(value)!={'schema_version','candidates','explanation'} or
            limits is None or fresh and value['schema_version']!=VERSION or not isinstance(value['explanation'],str) or not 1<=len(value['explanation'])<=600 or
            not isinstance(value['candidates'],list) or len(value['candidates'])>limits[0]):raise ValueError('PHOTO_CANDIDATES_INVALID')
    ids=set();kinds=PROPOSABLE_KINDS if fresh else limits[1];anchors=set(context_labels(context)) if fresh else None
    fields={'id','kind','label','confidence','bbox','description'}|({'near'} if limits[3] else set())
    for row in value['candidates']:
        if (not isinstance(row,dict) or set(row)!=fields or
                not isinstance(row['id'],str) or not re.fullmatch(limits[2],row['id']) or row['id'] in ids or
                not isinstance(row['kind'],str) or row['kind'] not in kinds or
                not isinstance(row['label'],str) or not 1<=len(row['label'].strip())<=80 or
                not isinstance(row['description'],str) or not 1<=len(row['description'])<=300):raise ValueError('PHOTO_CANDIDATE_INVALID')
        ids.add(row['id']);box=row['bbox'];confidence=row['confidence']
        if (type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1 or
                not isinstance(box,list) or len(box)!=4 or
                any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in box) or
                box[0]>=box[2] or box[1]>=box[3]):raise ValueError('PHOTO_CANDIDATE_IMAGE_REGION_INVALID')
        if limits[3] and row['near'] is not None and (not isinstance(row['near'],str) or not 1<=len(row['near'])<=120 or
                anchors is not None and row['near'] not in anchors):raise ValueError('PHOTO_CANDIDATE_ANCHOR_INVALID')
    return deepcopy(value)


def photo_candidate_schema(context=None):
    """context: the names that were sent; 'near' can only repeat one of them, or be null. Never a position."""
    near={'enum':[*context_labels(context),None]} if context is not None else {'type':['string','null'],'minLength':1,'maxLength':120}
    return dict(type='object',additionalProperties=False,required=['schema_version','candidates','explanation'],properties=dict(
        schema_version={'const':VERSION},explanation=dict(type='string',minLength=1,maxLength=600),
        candidates=dict(type='array',maxItems=MAX_CANDIDATES,items=dict(type='object',additionalProperties=False,
            required=['id','kind','label','confidence','bbox','description','near'],properties=dict(
                id={'enum':['Candidate_%d'%i for i in range(1,MAX_CANDIDATES+1)]},kind={'enum':list(PROPOSABLE_KINDS)},near=near,
                label=dict(type='string',minLength=1,maxLength=80),description=dict(type='string',minLength=1,maxLength=300),
                confidence=dict(type='number',minimum=0,maximum=1),
                bbox=dict(type='array',minItems=4,maxItems=4,items=dict(type='number',minimum=0,maximum=1)))))))


def _hull(points):
    points=sorted({(round(x,9),round(y,9)) for x,y in points})
    def half(rows):
        out=[]
        for p in rows:
            while len(out)>=2 and (out[-1][0]-out[-2][0])*(p[1]-out[-2][1])-(out[-1][1]-out[-2][1])*(p[0]-out[-2][0])<=0:out.pop()
            out.append(p)
        return out
    return points if len(points)<3 else half(points)[:-1]+half(points[::-1])[:-1]


def _rectangle(points,yaw=None):
    """(centre_xy,half_extents,yaw_deg) of the minimum-area rectangle over the xy points (yaw in [-45,45), 0.01 deg)."""
    hull=_hull(points)
    def frame(angle):
        c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        u=[x*c+y*s for x,y in hull];v=[-x*s+y*c for x,y in hull];mu,mv=(min(u)+max(u))/2,(min(v)+max(v))/2
        return (mu*c-mv*s,mu*s+mv*c),((max(u)-min(u))/2,(max(v)-min(v))/2),angle
    if yaw is None:
        yaw=0.;best=None
        for a,b in zip(hull,hull[1:]+hull[:1]):
            if a==b:continue
            angle=round((math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))+45)%90-45,2)
            if angle>=45:angle-=90
            _,(hu,hv),_=frame(angle)
            if best is None or hu*hv<best-1e-9:best=hu*hv;yaw=angle
    return frame(yaw)


def _corners(centre,half,yaw):
    c,s=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    return [[centre[0]+a*c-b*s,centre[1]+a*s+b*c] for a,b in ((-half[0],-half[1]),(half[0],-half[1]),(half[0],half[1]),(-half[0],half[1]))]


def _crosses(segment,centre,half,yaw):
    """Does the xy segment meet the rectangle? Liang-Barsky in the rectangle frame."""
    c,s=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    (x0,y0),(x1,y1)=[((x-centre[0])*c+(y-centre[1])*s,-(x-centre[0])*s+(y-centre[1])*c) for x,y in segment];t0,t1=0.,1.
    for p,q in ((x0-x1,x0+half[0]),(x1-x0,half[0]-x0),(y0-y1,y0+half[1]),(y1-y0,half[1]-y0)):
        if abs(p)<1e-12:
            if q<0:return False
        elif p<0:t0=max(t0,q/p)
        else:t1=min(t1,q/p)
        if t0>t1:return False
    return True


def _inside(point,polygon,*,edge=False):
    """Is the xy point inside the convex polygon (either winding)? edge: a point on its boundary counts."""
    sides=[(b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])];e=-1e-9 if edge else 1e-9
    return all(v>e for v in sides) or all(v<-e for v in sides)


def suggest_position(kind,near,environment,*,uncertainty_m=.05,taken=()):
    """A free floor spot beside the scanned or added object the photo model named. Pure, deterministic, local.

    Returns (placement, None) or (None, reason). The anchor footprint is the minimum-area rectangle of its floor
    projection (exact for box furniture, conservative for L shapes). The photo does not say which side, so the side is a
    rule, never a measurement: the short ends of an anchor at least 1 m long and 1.5 times longer than wide come first
    (beside a sofa, not in its legroom; beside a wardrobe, not before its doors), then the side with the most free floor
    within 0.8 m (sampled locally, never the whole-scene centre). The candidate turns with that side (its long edge along
    the anchor edge, so the result follows the anchor, not the room axes), then gaps .05-.40 m and three slides along it.
    A spot must pass the exact add-time floor check with the real envelope (+0.10 m for unknown/entanglement) and keep
    the box clear of every other object reaching its height (a planar mesh counts as 1 cm thick), the 0.8 m in front of
    each door or opening, every added envelope (the anchor's own box, not its keepout) and every taken envelope_xy
    (earlier suggestions). A partition wall blocks by its edges only, so where the scanned floor continues past it the
    keepout may reach the next room, as the add contract allows. Still an estimate (photo_estimate, alignment
    unverified): the robot LiDAR corrects small offsets later, not a wrong side.
    """
    from .room_item_catalog import room_item_catalog_version
    target=overlay_kind_for(kind)
    if target is None:return None,'NOT_ADDABLE'
    if kind in NOT_SUGGESTED:return None,'COVERING_NOT_SUGGESTED'
    if near is None:return None,'NO_ANCHOR'
    meshes=[m for m in environment['meshes'] if m['category'] not in NOT_CONTEXT and _name(m['label']) not in NOT_CONTEXT and m['label'][:80]==near]
    props=[o for o in environment.get('overlays',[]) if o['item']['label'][:80]==near]
    if not meshes and not props:return None,'ANCHOR_NOT_FOUND'
    if len(meshes)+len(props)>1:return None,'ANCHOR_AMBIGUOUS'
    if meshes:(cx,cy),(A,B),yaw=_rectangle([p[:2] for p in mesh_points(meshes[0])])
    else:
        item=props[0]['item'];(cx,cy),(A,B),yaw=_rectangle(_corners(item['position_m'][:2],[v/2 for v in item['dimensions_m'][:2]],item['yaw_deg']))
    w,d,h=CATALOG_SIZES[kind];cl=SUGGESTION_CLEARANCE_M
    # An added anchor blocks by its box: its keepout is an uncertainty, and a box beside it may share that margin.
    rects=[_corners(o['item']['position_m'][:2],[v/2 for v in o['item']['dimensions_m'][:2]],o['item']['yaw_deg']) if props and o is props[0] else [p[:2] for p in footprint(overlay_objects(o)[-1])] for o in environment.get('overlays',[])]
    rects+=[list(t) for t in taken];segments=set();floors=[]
    for mesh in environment['meshes']:
        points=mesh_points(mesh)
        if mesh['category']=='floor':floors+=[[points[i][:2] for i in t] for t in mesh['triangles'] if max(abs(points[i][2]) for i in t)<=1e-4]
        elif mesh['category'] in DOORWAYS or _name(mesh['label']) in DOORWAYS:
            # The passage through a door or opening stays clear: its width by DOOR_CLEAR_M on both sides of the wall.
            centre,(hu,hv),angle=_rectangle([p[:2] for p in points])
            rects.append(_corners(centre,(hu,hv+DOOR_CLEAR_M) if hu>=hv else (hu+DOOR_CLEAR_M,hv),angle))
        elif min(p[2] for p in points)<h-1e-6 and max(p[2] for p in points)>1e-6:
            # A whole-room wall mesh would cover the floor as a rectangle, so walls block by their projected edges.
            if mesh['category']=='wall':segments|={tuple(sorted((tuple(points[i][:2]),tuple(points[j][:2])))) for t in mesh['triangles'] for i,j in zip(t,t[1:]+t[:1])}
            else:
                centre,(hu,hv),angle=_rectangle([p[:2] for p in points])
                rects.append(_corners(centre,(max(hu,.005),max(hv,.005)),angle))
    if not floors:return None,'NO_FREE_FLOOR_NEAR_ANCHOR'
    c,s=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    def at(du,dv):return [round(cx+du*c-dv*s,3),round(cy+du*s+dv*c,3)]
    def walled(p,q):  # does the xy segment p-q cross a wall edge? (the segment as a thin rectangle)
        mid=((p[0]+q[0])/2,(p[1]+q[1])/2);length=math.hypot(q[0]-p[0],q[1]-p[1])
        return any(_crosses(e,mid,(length/2,1e-6),math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))) for e in segments)
    def free(axis,sign):
        """Shares of floor sample points beyond this side that are on flat floor, unblocked and not behind a wall:
        (within 0.8 m, 1.0-1.6 m for a tie, the +along half and the -along half within 0.8 m)."""
        span=(B,A)[axis];reach=(A,B)[axis];k=int(math.floor((span+.2)/.2+1e-9));hits=dict(near=0,far=0,pos=0,neg=0)
        for along in (i*.2 for i in range(-k,k+1)):  # symmetric about the side centre, so a mirrored room samples the same points
            edge=at(*((sign*reach,along) if axis==0 else (along,sign*reach)))
            for depth in (.2,.4,.6,.8,1.,1.2,1.4,1.6):
                p=at(*((sign*(reach+depth),along) if axis==0 else (along,sign*(reach+depth))))
                if any(_inside(p,t,edge=True) for t in floors) and not any(_inside(p,r) for r in rects) and not walled(edge,p):
                    hits['near' if depth<.9 else 'far']+=1
                    if depth<.9 and abs(along)>1e-9:hits['pos' if along>0 else 'neg']+=1
        n=4*(2*k+1);return tuple(round(hits[key]/(n if key in ('near','far') else max(4*k,1)),6) for key in ('near','far','pos','neg'))
    long_axis=0 if A>=B else 1;elongated=2*max(A,B)>=1. and max(A,B)>=1.5*min(A,B)
    sides=sorted((0 if elongated and axis==long_axis else 1,-share[0],-share[1],index,axis,sign,share)
        for index,(axis,sign) in enumerate(((0,1),(0,-1),(1,1),(1,-1))) for share in [free(axis,sign)])
    for *_,index,axis,sign,share in sides:
        # The candidate's long edge runs along the anchor edge first (an end of axis 0 runs along v), then turned 90 degrees.
        turns=[90.,0.] if (w>=d)==(axis==0) else [0.,90.]
        for turn in (turns if abs(w-d)>1e-9 else [0.]):
            au,av=(d/2,w/2) if turn else (w/2,d/2);clear=(au+cl,av+cl);reach=(A+au,B+av)[axis];room=(B-av,A-au)[axis]
            offset=lambda gap,slide:(sign*(reach+gap),slide) if axis==0 else (slide,sign*(reach+gap))
            for gap in SUGGESTION_GAPS_M:
                # Along a long side of a long anchor the corners come first (beside it, not before its middle), freer half first.
                slides=[abs(room),-abs(room)] if share[2]>=share[3] else [-abs(room),abs(room)]
                slides=[0.] if abs(room)<=.005 else slides+[0.] if elongated and axis!=long_axis else [0.,*slides]
                for slide in slides:
                    x,y=at(*offset(gap,slide));body=_corners((x,y),clear,yaw)
                    # Walls are tested over the box swept back to the anchor edge: a spot beyond a wall is not beside the anchor.
                    sweep=(clear[0]+gap/2,clear[1]) if axis==0 else (clear[0],clear[1]+gap/2)
                    if any(convex_overlap_area(body,r)>1e-9 for r in rects) or any(_crosses(e,at(*offset(gap/2,slide)),sweep,yaw) for e in segments):continue
                    item_yaw=round(yaw+turn,2)
                    overlay=dict(item=dict(id='Added_'+'0'*20,kind=target,label='Suggested placement',catalog_version=room_item_catalog_version(target),
                        position_m=[x,y,h/2],dimensions_m=[w,d,h],yaw_deg=item_yaw,observation_time_utc=None),uncertainty_m=uncertainty_m,
                        evidence=dict(basis='photo_estimate',source_name='suggestion',sha256='0'*64,alignment_verified=False))
                    try:checked_overlay_floor(overlay,environment['meshes'])
                    except ValueError:continue
                    return dict(position_m=[x,y,h/2],yaw_deg=item_yaw,dimensions_m=[w,d,h],uncertainty_m=uncertainty_m,anchor=near,gap_m=gap,
                        side=('+x','-x','+y','-y')[index],at_end=axis==long_axis and elongated,basis='photo_near_anchor',alignment_verified=False,
                        envelope_xy=[p[:2] for p in footprint(overlay_objects(overlay)[-1])]),None
    return None,'NO_FREE_FLOOR_NEAR_ANCHOR'
