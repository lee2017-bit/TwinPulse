# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded data-only reference transfer and no-motion observation envelopes.

Legacy bootstrap/line budgets are unchanged. No paths, devices or authority.
"""
import base64
from copy import deepcopy
import hashlib
import json
import re
import zlib
from .revisions import canonical_sha256
from .local_navigation import finite

MAX_REFERENCE=4*1024*1024
CHUNK=6000
OBSERVATION_CHUNK=40000  # Robot stdout 64KiB; PC upload stays below 16KiB.
MAX_OBSERVATION=MAX_REFERENCE


def hex_id(value,n):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{'+str(n)+'}',value) is not None


def encode(value,limit):
    raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode('utf-8')
    if len(raw)>limit:raise ValueError('REFERENCE_TRANSPORT_BYTE_BUDGET')
    return raw


def decode(raw,limit):
    if len(raw)>limit:raise ValueError('REFERENCE_TRANSPORT_BYTE_BUDGET')
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('REFERENCE_TRANSPORT_DUPLICATE_KEY')
            value[key]=item
        return value
    def invalid(_):raise ValueError('REFERENCE_TRANSPORT_NONFINITE')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)


def descriptor(raw):
    return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def checked_descriptor(value):
    if (type(value) is not dict or set(value)!={'sha256','bytes'} or not hex_id(value['sha256'],64)
            or type(value['bytes']) is not int or not 1<=value['bytes']<=MAX_REFERENCE):
        raise ValueError('REFERENCE_TRANSPORT_DESCRIPTOR')
    return deepcopy(value)


class ReferenceSender:
    def __init__(self,value,*,chunk_size=CHUNK):
        if type(chunk_size) is not int or not 1<=chunk_size<=OBSERVATION_CHUNK:
            raise ValueError('REFERENCE_TRANSPORT_CHUNK_BUDGET')
        self.chunk_size=chunk_size
        self.raw=encode(value,MAX_REFERENCE);self.descriptor=descriptor(self.raw);self.index=0

    def chunk(self,nonce,index):
        if not hex_id(nonce,24) or type(index) is not int or index!=self.index or index*self.chunk_size>=len(self.raw):
            raise ValueError('REFERENCE_TRANSPORT_ACK_SEQUENCE')
        start=index*self.chunk_size;self.index+=1
        return {'action':'reference_chunk','nonce':nonce,'index':index,
                'data':base64.b64encode(self.raw[start:start+self.chunk_size]).decode('ascii')}


class ReferenceReceiver:
    def __init__(self,value,nonce,*,chunk_size=CHUNK):
        if type(chunk_size) is not int or not 1<=chunk_size<=OBSERVATION_CHUNK:
            raise ValueError('REFERENCE_TRANSPORT_CHUNK_BUDGET')
        self.chunk_size=chunk_size
        self.descriptor=checked_descriptor(value)
        if not hex_id(nonce,24):raise ValueError('REFERENCE_TRANSPORT_NONCE')
        self.nonce=nonce;self.index=0;self.raw=bytearray();self.done=False

    def accept(self,packet):
        if (self.done or type(packet) is not dict or set(packet)!={'action','nonce','index','data'}
                or packet['action']!='reference_chunk' or packet['nonce']!=self.nonce
                or type(packet['index']) is not int or packet['index']!=self.index
                or not isinstance(packet['data'],str) or len(packet['data'])>4*((self.chunk_size+2)//3)):
            raise ValueError('REFERENCE_TRANSPORT_CHUNK_SEQUENCE')
        try:part=base64.b64decode(packet['data'],validate=True)
        except (ValueError,TypeError) as exc:raise ValueError('REFERENCE_TRANSPORT_CHUNK_ENCODING') from exc
        expected=min(self.chunk_size,self.descriptor['bytes']-len(self.raw))
        if len(part)!=expected:raise ValueError('REFERENCE_TRANSPORT_CHUNK_LENGTH')
        self.raw.extend(part);self.index+=1
        if len(self.raw)==self.descriptor['bytes']:
            if descriptor(self.raw)!=self.descriptor:raise ValueError('REFERENCE_TRANSPORT_HASH')
            self.done=True
            return decode(bytes(self.raw),MAX_REFERENCE)
        return None


def checked_reference(value,scope):
    from .mission_evidence_contract import checked_survey_map
    keys={'map_id','map','photo_alignment','reference_report_revision','reference_kind',
          'pose_candidate','motion_authorized','physical_demo_ready'}
    if (type(value) is not dict or set(value)!=keys
            or value['reference_kind']!='accepted-survey-reference-1.0'
            or not isinstance(value['map_id'],str) or not re.fullmatch('survey:[a-f0-9]{32}:[a-f0-9]{64}',value['map_id'])
            or value['map_id'].split(':')[-1]!=value['reference_report_revision']
            or value['pose_candidate'] is not None
            or any(value[k] is not False for k in ('motion_authorized','physical_demo_ready'))):
        raise ValueError('REFERENCE_TRANSPORT_REFERENCE_CONTEXT')
    saved=value['map'];fit=value['photo_alignment']
    checked_survey_map(saved,{'project_id':scope['project_id'],'source_revision':saved.get('source_revision')})
    if (saved['revision']!=scope['reference']['revision'] or len(saved['tracking_endpoints'])<24
            or type(fit) is not dict or fit.get('status')!='ALIGNMENT_CANDIDATE'
            or fit.get('schema')!='automatic-photo-alignment-1.0'
            or fit.get('source_map_revision')!=saved['revision']
            or fit.get('report_revision')!=canonical_sha256({k:v for k,v in fit.items() if k!='report_revision'})
            or any(fit.get(k) is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready'))
            or any(fit.get(k)!=scope['alignment'][k] for k in ('status','room_from_map','report_revision'))):
        raise ValueError('REFERENCE_TRANSPORT_ALIGNMENT_CONTEXT')
    original={k:v for k,v in fit.items() if k not in {'report_revision','source_report_revision','room_base_revision','effective_objects'}}
    if canonical_sha256(original)!=fit.get('source_report_revision'):
        raise ValueError('REFERENCE_TRANSPORT_ORIGINAL_FIT_CHANGED')
    sequences={f['sequence'] for f in saved['keyframes']};selected=fit.get('fit_sequences');held=fit.get('validation_sequences')
    if (type(selected) is not list or type(held) is not list or not selected or not held
            or any(type(n) is not int or n not in sequences for n in selected+held)
            or selected!=sorted(set(selected)) or held!=sorted(set(held)) or max(selected)>=min(held)):
        raise ValueError('REFERENCE_TRANSPORT_HELD_OUT_REQUIRED')
    if descriptor(encode(value,MAX_REFERENCE))!=scope['reference']['payload']:
        raise ValueError('REFERENCE_TRANSPORT_PAYLOAD_CHANGED')
    return deepcopy(value)


def goal_handoff(scope,mission_id,preview):
    """Immutable reviewed data, not a device command or a restored approval."""
    from .adaptive_mission_contract import adaptive_scope
    scope=adaptive_scope(scope)
    if scope['schema']!='observed-mission-scope-6.0' or not hex_id(mission_id,32):
        raise ValueError('GOAL_HANDOFF_IDLE_CONTEXT')
    if (type(preview) is not dict or preview.get('schema') not in {'current-goal-preview-1.0','current-goal-preview-2.0'}
            or preview.get('plan_id')!=canonical_sha256({k:v for k,v in preview.items() if k!='plan_id'})
            or preview.get('mode')!='REAL_CANDIDATE' or preview.get('physical_authority') is not False
            or preview.get('max_linear_mps')!=.03 or preview.get('max_angular_rps')!=.20
            or preview.get('goal_contract',{}).get('room_revision')!=scope['goal']['room_revision']
            or preview.get('binding',{}).get('context',{}).get('project_id')!=scope['project_id']
            or preview.get('binding',{}).get('alignment_revision')!=scope['alignment']['report_revision']
            or preview.get('binding',{}).get('room_from_map')!=scope['alignment']['room_from_map']):
        raise ValueError('GOAL_HANDOFF_PREVIEW_CHANGED')
    execution=adaptive_scope({**scope,'schema':'observed-mission-scope-7.0',
        'phase':'REVIEWED_GOAL_EXECUTION','goal':preview['goal_contract']})
    value={'schema':'reviewed-goal-handoff-1.0','mission_id':mission_id,
        'idle_scope_sha256':canonical_sha256(scope),'scope':execution,'preview':deepcopy(preview)}
    encode(value,MAX_REFERENCE)
    return value


def checked_goal_handoff(value,scope,mission_id,evidence,context,now):
    from .current_goal_preview import check_preview
    if type(value) is not dict or value!=goal_handoff(scope,mission_id,value.get('preview')):
        raise ValueError('GOAL_HANDOFF_CONTEXT_CHANGED')
    check_preview(value['preview'],evidence,context,now,value['scope']['goal'])
    return deepcopy(value)


def observation_packet(query_id,evidence,issued_s,*,received_s=None):
    if received_s is None:received_s=issued_s
    if (not hex_id(query_id,32) or not finite(issued_s) or not finite(received_s)
            or received_s>issued_s):raise ValueError('IDLE_OBSERVATION_CONTEXT')
    raw=encode(evidence,MAX_OBSERVATION)
    body={'state':'LOCALIZATION_OBSERVATION','query_id':query_id,'issued_s':issued_s,'received_s':received_s,
          'payload':descriptor(raw),'data':base64.b64encode(zlib.compress(raw)).decode('ascii')}
    encode(body,MAX_REFERENCE)
    return body


def checked_observation(packet,query_id):
    if (type(packet) is not dict or set(packet)!={'state','query_id','issued_s','received_s','payload','data'}
            or packet['state']!='LOCALIZATION_OBSERVATION' or packet['query_id']!=query_id
            or not hex_id(query_id,32) or not finite(packet['issued_s']) or not finite(packet['received_s'])
            or packet['received_s']>packet['issued_s']
            or not isinstance(packet['data'],str) or len(packet['data'])>MAX_REFERENCE):
        raise ValueError('IDLE_OBSERVATION_PACKET_CONTEXT')
    expected=checked_descriptor(packet['payload'])
    if expected['bytes']>MAX_OBSERVATION:raise ValueError('IDLE_OBSERVATION_BYTE_BUDGET')
    try:
        packed=base64.b64decode(packet['data'],validate=True);stream=zlib.decompressobj()
        raw=stream.decompress(packed,expected['bytes']+1)
        if (len(raw)!=expected['bytes'] or not stream.eof or stream.unused_data or stream.unconsumed_tail
                or descriptor(raw)!=expected):raise ValueError('IDLE_OBSERVATION_HASH_OR_SIZE')
        return decode(raw,MAX_OBSERVATION)
    except (zlib.error,ValueError,TypeError) as exc:
        raise ValueError('IDLE_OBSERVATION_HASH_OR_SIZE') from exc
