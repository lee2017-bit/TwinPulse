# SPDX-License-Identifier: Apache-2.0
"""Photo-space candidates only. No metric position, navigation or Apply rights."""
from copy import deepcopy
import math
import re
from .environment_overlays import KINDS

VERSION='environment-photo-candidates-1.0'
CATALOG_SIZES={'floor_fan':(.4,.4,1.1),'basket':(.35,.3,.4),'bag':(.3,.25,.35),'box':(.3,.3,.3),
    'clothing_pile':(.35,.25,.15),'cable_bundle':(.3,.2,.04),'power_adapter':(.12,.08,.05),
    'power_strip':(.3,.08,.05),'small_equipment':(.3,.3,.3),'unknown':(.3,.3,.3)}


def checked_photo_candidates(value):
    if (not isinstance(value,dict) or set(value)!={'schema_version','candidates','explanation'} or
            value['schema_version']!=VERSION or not isinstance(value['explanation'],str) or not 1<=len(value['explanation'])<=600 or
            not isinstance(value['candidates'],list) or len(value['candidates'])>3):raise ValueError('PHOTO_CANDIDATES_INVALID')
    ids=set()
    for row in value['candidates']:
        if (not isinstance(row,dict) or set(row)!={'id','kind','label','confidence','bbox','description'} or
                not isinstance(row['id'],str) or not re.fullmatch('Candidate_[1-3]',row['id']) or row['id'] in ids or
                not isinstance(row['kind'],str) or row['kind'] not in KINDS or
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
        candidates=dict(type='array',maxItems=3,items=dict(type='object',additionalProperties=False,
            required=['id','kind','label','confidence','bbox','description'],properties=dict(
                id={'enum':['Candidate_1','Candidate_2','Candidate_3']},kind={'enum':list(KINDS)},
                label=dict(type='string',minLength=1,maxLength=80),description=dict(type='string',minLength=1,maxLength=300),
                confidence=dict(type='number',minimum=0,maximum=1),
                bbox=dict(type='array',minItems=4,maxItems=4,items=dict(type='number',minimum=0,maximum=1)))))))
