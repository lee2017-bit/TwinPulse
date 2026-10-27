# SPDX-License-Identifier: Apache-2.0
"""Photo-space candidates only. No metric position, navigation or Apply rights."""
from copy import deepcopy
import math
import re
from .environment_overlays import KINDS as OVERLAY_KINDS
from .environment_source import MOVABLE
from .furniture import furniture_kinds
from .room_item_catalog import ROOM_ITEM_KINDS,WALL_ITEMS,CEILING_ITEMS
from .warehouse_models import WAREHOUSE_KINDS

VERSION='environment-photo-candidates-1.1'
MAX_CANDIDATES=6
# The model-library vocabulary (34 names, equal to photo_layout.KINDS), not only the 10 overlay kinds.
PHOTO_KINDS=(*furniture_kinds(),*ROOM_ITEM_KINDS,*WAREHOUSE_KINDS)
# Recognised but never added: an overlay is a floor-resting box (z=h/2).
NOT_ADDABLE=frozenset((*WALL_ITEMS,*CEILING_ITEMS,'surface_covering','door_leaf'))
# The only kind enum a fresh call may use: overlay kinds first, then kinds added as a labelled unknown box.
PROPOSABLE_KINDS=(*OVERLAY_KINDS,*(k for k in PHOTO_KINDS if k not in OVERLAY_KINDS and k not in NOT_ADDABLE))
# Per saved version: (max candidates, kinds, id pattern). A saved 1.0 job stays readable with its own limits.
LIMITS={'environment-photo-candidates-1.0':(3,OVERLAY_KINDS,'Candidate_[1-3]'),VERSION:(6,PHOTO_KINDS,'Candidate_[1-6]')}
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
    """Labels that may already be this object: a hint for the required human check, never identity."""
    overlays=environment.get('overlays',[]);target=overlay_kind_for(kind)
    if kind=='unknown':labels=[o['item']['label'] for o in overlays if o['item']['kind']=='unknown']
    else:
        names=SCAN_NAMES.get(kind,set())
        labels=[m['label'] for m in environment['meshes'] if m['category'] in names or _name(m['label']) in names]+[
            o['item']['label'] for o in overlays if receipts.get(o['item']['id'])==kind or
            target not in (None,'unknown') and o['item']['kind']==target or
            target=='unknown' and o['evidence']['basis']=='lidar_estimate']
    return list(dict.fromkeys(labels))[:8]


def checked_photo_candidates(value,*,fresh=False):
    """fresh: a new model reply, which must be exactly VERSION with a proposable kind."""
    limits=LIMITS.get(value.get('schema_version')) if isinstance(value,dict) and isinstance(value.get('schema_version'),str) else None
    if (not isinstance(value,dict) or set(value)!={'schema_version','candidates','explanation'} or
            limits is None or fresh and value['schema_version']!=VERSION or not isinstance(value['explanation'],str) or not 1<=len(value['explanation'])<=600 or
            not isinstance(value['candidates'],list) or len(value['candidates'])>limits[0]):raise ValueError('PHOTO_CANDIDATES_INVALID')
    ids=set();kinds=PROPOSABLE_KINDS if fresh else limits[1]
    for row in value['candidates']:
        if (not isinstance(row,dict) or set(row)!={'id','kind','label','confidence','bbox','description'} or
                not isinstance(row['id'],str) or not re.fullmatch(limits[2],row['id']) or row['id'] in ids or
                not isinstance(row['kind'],str) or row['kind'] not in kinds or
                not isinstance(row['label'],str) or not 1<=len(row['label'].strip())<=80 or
                not isinstance(row['description'],str) or not 1<=len(row['description'])<=300):raise ValueError('PHOTO_CANDIDATE_INVALID')
        ids.add(row['id']);box=row['bbox'];confidence=row['confidence']
        if (type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1 or
                not isinstance(box,list) or len(box)!=4 or
                any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in box) or
                box[0]>=box[2] or box[1]>=box[3]):raise ValueError('PHOTO_CANDIDATE_IMAGE_REGION_INVALID')
    return deepcopy(value)


def photo_candidate_schema():
    return dict(type='object',additionalProperties=False,required=['schema_version','candidates','explanation'],properties=dict(
        schema_version={'const':VERSION},explanation=dict(type='string',minLength=1,maxLength=600),
        candidates=dict(type='array',maxItems=MAX_CANDIDATES,items=dict(type='object',additionalProperties=False,
            required=['id','kind','label','confidence','bbox','description'],properties=dict(
                id={'enum':['Candidate_%d'%i for i in range(1,MAX_CANDIDATES+1)]},kind={'enum':list(PROPOSABLE_KINDS)},
                label=dict(type='string',minLength=1,maxLength=80),description=dict(type='string',minLength=1,maxLength=300),
                confidence=dict(type='number',minimum=0,maximum=1),
                bbox=dict(type='array',minItems=4,maxItems=4,items=dict(type='number',minimum=0,maximum=1)))))))
