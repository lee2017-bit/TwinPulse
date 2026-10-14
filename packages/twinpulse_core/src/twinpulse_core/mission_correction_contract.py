# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Data-only idle correction exchange. Never renews input or mission deadlines.

v1/v2 bootstrap bytes are unchanged. v3 expressly permits one bounded proposal
and one immutable revision binding; the original goal, source and scope stay
signed. Nonces are transient protocol identity, not saved execution evidence.
"""
from copy import deepcopy
import json
import re
from .adaptive_mission_contract import adaptive_scope, checked_nominal
from .observed_mission import checked_goal
from .revisions import canonical_sha256
from .local_navigation import finite
from .mission_contract import document_hash


def _hex(value,size):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{'+str(size)+'}',value) is not None


def checked_fit(value,nominal):
    keys={'schema','policy','status','source_map_revision','scene_revision_before','room_from_map',
          'proposals','corrected_objects','alignment_verified','motion_authorized','physical_demo_ready',
          'validation_basis','height_material_scale_changed','goal_revalidation_required','sensor_section',
          'photo_outer_objects','fit_sequences','validation_sequences','fit_interval_ns','validation_interval_ns',
          'fit_structures','validation_structures','alternatives','alternative_margin_m','fit_error_m',
          'additional_evidence','validation_before_m','reason','geometry_rejections','geometry_status',
          'validation_after_m','target_validation_before_m','target_validation_after_m','scene_revision_after'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('CORRECTION_FIT_SHAPE')
    if (value['schema']!='automatic-photo-alignment-1.0' or value['policy']!='correct_walls'
            or value['status']!='ALIGNMENT_CANDIDATE' or value['geometry_status']!='BOUNDED_WALL_PROPOSAL_VALIDATED'
            or value['scene_revision_before']!=canonical_sha256(nominal['objects'])
            or value['photo_outer_objects']!=nominal['objects']
            or not _hex(value['source_map_revision'],64)
            or any(value[k] is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready',
                'height_material_scale_changed','goal_revalidation_required'))):
        raise ValueError('CORRECTION_FIT_CONTEXT')
    # Bound every nested field before trusting a remote report or saving it.
    count=0
    def tree(row,depth=0):
        nonlocal count
        count+=1
        if count>8192 or depth>9:raise ValueError('CORRECTION_FIT_BUDGET')
        if row is None or type(row) is bool:return
        if type(row) in (int,float):
            if not finite(row):raise ValueError('CORRECTION_FIT_NONFINITE')
        elif isinstance(row,str):
            if not re.fullmatch('[A-Za-z0-9_. -]{1,160}',row):raise ValueError('CORRECTION_FIT_TEXT')
        elif type(row) is list:
            if len(row)>160:raise ValueError('CORRECTION_FIT_BUDGET')
            for item in row:tree(item,depth+1)
        elif type(row) is dict:
            for key,item in row.items():tree(key,depth+1);tree(item,depth+1)
        else:raise ValueError('CORRECTION_FIT_SHAPE')
    tree(value)
    if len(json.dumps(value,allow_nan=False).encode())>32768:raise ValueError('CORRECTION_FIT_BYTES')
    checked_nominal({**nominal,'objects':value['corrected_objects']},nominal['room_revision'])
    if canonical_sha256(value['corrected_objects'])!=value['scene_revision_after']:raise ValueError('CORRECTION_FIT_HASH')
    fit=value['fit_sequences'];held=value['validation_sequences']
    if (not fit or not held or any(type(n) is not int or n<=0 for n in fit+held)
            or fit!=sorted(set(fit)) or held!=sorted(set(held)) or max(fit)>=min(held)):
        raise ValueError('CORRECTION_FIT_HELD_OUT_ORDER')
    if not 1<=len(value['proposals'])<=2:raise ValueError('CORRECTION_FIT_WALL_COUNT')
    return deepcopy(value)


def correction_proposal(scope,mission_id,request_sha256,nonce,result,issued_s):
    scope=adaptive_scope(scope)
    if scope['schema'] not in {'observed-mission-scope-3.0','observed-mission-scope-5.0'}:raise ValueError('CORRECTION_POLICY_NOT_SCOPED')
    if not _hex(mission_id,32) or not _hex(request_sha256,64) or not _hex(nonce,24) or not finite(issued_s) or issued_s<0:
        raise ValueError('CORRECTION_PROPOSAL_CONTEXT')
    body={'schema':'idle-wall-proposal-1.0','mission_id':mission_id,'request_sha256':request_sha256,
          'scope_sha256':document_hash(scope),'nonce':nonce,'issued_s':issued_s,'expires_s':issued_s+2.,
          'fit':checked_fit(result,scope['nominal'])}
    return {**body,'revision':canonical_sha256(body)}


def checked_proposal(value,scope,mission_id,request_sha256):
    keys={'schema','mission_id','request_sha256','scope_sha256','nonce','issued_s','expires_s','fit','revision'}
    if not isinstance(value,dict) or set(value)!=keys:raise ValueError('CORRECTION_PROPOSAL_SHAPE')
    expected=correction_proposal(scope,mission_id,request_sha256,value['nonce'],value['fit'],value['issued_s'])
    if expected!=value:raise ValueError('CORRECTION_PROPOSAL_HASH_OR_SCOPE')
    return expected


def correction_reply(proposal,scope,binding=None,*,reason=None):
    scope=adaptive_scope(scope)
    if reason is not None:
        if not isinstance(reason,str) or not re.fullmatch('[A-Z0-9_]{1,120}',reason):raise ValueError('CORRECTION_REJECTION_CODE')
        if binding is not None:raise ValueError('CORRECTION_REPLY_SHAPE')
    else:
        if (not isinstance(binding,dict) or set(binding)!={'schema','goal','applied_revision'}
                or binding['schema']!='mission-photo-binding-1.0' or not _hex(binding['applied_revision'],64)):
            raise ValueError('CORRECTION_BINDING_SHAPE')
        goal=checked_goal(binding['goal']);original=scope['goal']
        if any(goal[k]!=original[k] for k in ('xy','mode','duration_s')) or goal['room_revision']==original['room_revision']:
            raise ValueError('CORRECTION_BINDING_CHANGED_SCOPE')
    body={'action':'correction_reply','schema':'idle-wall-reply-1.0','mission_id':proposal['mission_id'],
          'scope_sha256':proposal['scope_sha256'],'proposal_revision':proposal['revision'],'nonce':proposal['nonce'],
          'binding':deepcopy(binding),'reason':reason}
    return {**body,'revision':canonical_sha256(body)}


def checked_reply(value,proposal,scope,now):
    if not finite(now) or not proposal['issued_s']<=now<proposal['expires_s']:raise ValueError('CORRECTION_ACK_EXPIRED')
    if (not isinstance(value,dict) or set(value)!={'action','schema','mission_id','scope_sha256','proposal_revision','nonce','binding','reason','revision'}
            or value!=correction_reply(proposal,scope,value.get('binding'),reason=value.get('reason'))):
        raise ValueError('CORRECTION_ACK_CONTEXT_OR_HASH')
    return deepcopy(value)
