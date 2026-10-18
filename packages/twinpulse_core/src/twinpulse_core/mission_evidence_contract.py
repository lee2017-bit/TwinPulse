# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Full historical survey evidence, separate from the bounded control channel.

No current pose, input lease, execution permission or device access. Original
keyframes/endpoints are retained; a display cloud cannot substitute for a map.
"""
from copy import deepcopy
import hashlib
import json
import re
from .adaptive_mission_contract import adaptive_scope
from .observation_stream import checked_context
from .local_navigation import finite
from .revisions import canonical_sha256
from .room_localization import compose

FILE_NAME = 'mission-evidence.json'
MAX_BYTES = 4 * 1024 * 1024


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{'+str(size)+'}', value) is not None


def _tree(value, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if counter[0] > 240000 or depth > 14:
        raise ValueError('MISSION_EVIDENCE_TREE_BUDGET')
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if not finite(value): raise ValueError('MISSION_EVIDENCE_NONFINITE')
    elif isinstance(value, str):
        if not re.fullmatch('[A-Za-z0-9_. -]{1,160}', value):
            raise ValueError('MISSION_EVIDENCE_TEXT')
    elif type(value) is list:
        if len(value) > 18000: raise ValueError('MISSION_EVIDENCE_LIST_BUDGET')
        for item in value: _tree(item, depth+1, counter)
    elif type(value) is dict:
        for key, item in value.items():
            _tree(key, depth+1, counter); _tree(item, depth+1, counter)
    else:
        raise ValueError('MISSION_EVIDENCE_SHAPE')


def checked_survey_map(value, context):
    keys = {'schema','project_id','source_revision','endpoint_cells','tracking_endpoints',
            'tracking_endpoint_basis','keyframes','reference_eligible','mapping_method',
            'alignment_verified','motion_authorized','physical_demo_ready','revision'}
    if (not isinstance(value, dict) or set(value) != keys
            or value['schema'] != 'session-survey-map-1.0'
            or value['project_id'] != context['project_id']
            or value['source_revision'] != context['source_revision']
            or value['reference_eligible'] is not False
            or any(value[k] is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready'))
            or value['tracking_endpoint_basis'] != 'ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED'
            or value['mapping_method'] != 'CAUSAL_DESKEWED_ODOMETRY_PROJECTION_NOT_GLOBAL_SLAM'):
        raise ValueError('MISSION_EVIDENCE_MAP_CONTEXT')
    def points(rows, limit, size):
        return (type(rows) is list and len(rows) <= limit and all(
            type(p) is list and len(p) == size and all(finite(x) and abs(x) <= 20 for x in p) for p in rows))
    if not points(value['endpoint_cells'],18000,2) or not points(value['tracking_endpoints'],18000,2):
        raise ValueError('MISSION_EVIDENCE_MAP_POINTS')
    frames = value['keyframes']
    if type(frames) is not list or not 1 <= len(frames) <= 128:
        raise ValueError('MISSION_EVIDENCE_KEYFRAME_BUDGET')
    previous = (0,0)
    for frame in frames:
        if (not isinstance(frame,dict) or set(frame) != {'sequence','stamp_ns','pose','points','origins'}
                or type(frame['sequence']) is not int or type(frame['stamp_ns']) is not int
                or frame['sequence'] <= previous[0] or frame['stamp_ns'] <= previous[1]
                or not points([frame['pose']],1,3) or not points(frame['points'],160,2)
                or not points(frame['origins'],160,2) or not frame['points']
                or len(frame['points']) != len(frame['origins'])):
            raise ValueError('MISSION_EVIDENCE_KEYFRAME_INVALID')
        previous = (frame['sequence'],frame['stamp_ns'])
    projected = [compose(f['pose'],[*p,0.])[:2] for f in frames for p in f['points']]
    step = max(1, (len(projected)+17999)//18000)
    if value['tracking_endpoints'] != projected[::step]:
        raise ValueError('MISSION_EVIDENCE_TRACKING_POINTS_CHANGED')
    if value['revision'] != canonical_sha256({k:v for k,v in value.items() if k!='revision'}):
        raise ValueError('MISSION_EVIDENCE_MAP_HASH')
    return deepcopy(value)


def checked_mission_evidence(value, scope, mission_id, request_sha256, context):
    scope = adaptive_scope(scope); context = checked_context(context)
    keys = {'schema','mission_id','request_sha256','scope','scope_sha256','context','survey_map',
            'photo_alignment','current_pose_valid','motion_authorized','physical_demo_ready','revision'}
    if (not isinstance(value,dict) or set(value)!=keys or value['schema']!='mission-evidence-1.0'
            or not _hex(mission_id,32) or not _hex(request_sha256,64)
            or value['mission_id']!=mission_id or value['request_sha256']!=request_sha256
            or value['scope']!=scope or value['scope_sha256']!=canonical_sha256(scope) or value['context']!=context
            or context['project_id']!=scope['project_id'] or context['origin']!='live_ros'
            or context['source_revision']!=context['release_id']
            or scope['goal']['mode'] not in {'SURVEY_ONLY','SURVEY_THEN_NAVIGATE'}
            or any(value[k] is not False for k in ('current_pose_valid','motion_authorized','physical_demo_ready'))):
        raise ValueError('MISSION_EVIDENCE_CONTEXT')
    _tree(value)
    if len(json.dumps(value,allow_nan=False).encode()) > MAX_BYTES:
        raise ValueError('MISSION_EVIDENCE_BYTES')
    saved = checked_survey_map(value['survey_map'],context)
    fit = value['photo_alignment']
    if fit is not None:
        if (not isinstance(fit,dict) or fit.get('schema')!='automatic-photo-alignment-1.0'
                or fit.get('status') not in {'ALIGNMENT_CANDIDATE','INSUFFICIENT_EVIDENCE','MODEL_MISMATCH','AMBIGUOUS','VALIDATION_REJECTED'}
                or fit.get('source_map_revision')!=saved['revision']
                or fit.get('scene_revision_before')!=canonical_sha256(scope['nominal']['objects'])
                or fit.get('photo_outer_objects')!=scope['nominal']['objects']
                or fit.get('policy')!=('correct_walls' if scope['schema'] in {'observed-mission-scope-3.0','observed-mission-scope-5.0'} else 'align_only')
                or any(fit.get(k) is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready'))
                or fit.get('report_revision')!=canonical_sha256({k:v for k,v in fit.items() if k!='report_revision'})):
            raise ValueError('MISSION_EVIDENCE_FIT_CONTEXT')
        sequences = {f['sequence'] for f in saved['keyframes']}
        fit_sequences=fit.get('fit_sequences',[]); held=fit.get('validation_sequences',[])
        if (type(fit_sequences) is not list or type(held) is not list
                or any(type(n) is not int or n not in sequences for n in fit_sequences+held)
                or fit_sequences!=sorted(set(fit_sequences)) or held!=sorted(set(held))
                or fit_sequences and held and max(fit_sequences)>=min(held)):
            raise ValueError('MISSION_EVIDENCE_FIT_SEQUENCE')
        if fit['status']=='ALIGNMENT_CANDIDATE':
            pose=fit.get('room_from_map')
            if (type(pose) is not list or len(pose)!=3 or any(not finite(x) or abs(x)>20 for x in pose)
                    or not fit_sequences or not held):
                raise ValueError('MISSION_EVIDENCE_FIT_CANDIDATE')
        elif fit.get('room_from_map') is not None:
            raise ValueError('MISSION_EVIDENCE_REJECTED_POSE')
    if value['revision']!=canonical_sha256({k:v for k,v in value.items() if k!='revision'}):
        raise ValueError('MISSION_EVIDENCE_HASH')
    return deepcopy(value)


def mission_evidence(scope, mission_id, request_sha256, context, saved_map, fit):
    body = {'schema':'mission-evidence-1.0','mission_id':mission_id,'request_sha256':request_sha256,
            'scope':deepcopy(scope),'scope_sha256':canonical_sha256(scope),'context':deepcopy(context),
            'survey_map':deepcopy(saved_map),'photo_alignment':deepcopy(fit),
            'current_pose_valid':False,'motion_authorized':False,'physical_demo_ready':False}
    return checked_mission_evidence({**body,'revision':canonical_sha256(body)},scope,mission_id,request_sha256,context)


def checked_descriptor(value):
    if (not isinstance(value,dict) or set(value)!={'schema','file','bytes','sha256','revision'}
            or value['schema']!='mission-evidence-file-1.0' or value['file']!=FILE_NAME
            or type(value['bytes']) is not int or not 0<value['bytes']<=MAX_BYTES
            or not _hex(value['sha256'],64) or not _hex(value['revision'],64)):
        raise ValueError('MISSION_EVIDENCE_DESCRIPTOR')
    return deepcopy(value)


def evidence_bytes(value):
    data = json.dumps(value,sort_keys=True,allow_nan=False).encode('utf-8')
    if len(data)>MAX_BYTES: raise ValueError('MISSION_EVIDENCE_BYTES')
    return data, checked_descriptor({'schema':'mission-evidence-file-1.0','file':FILE_NAME,
        'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'revision':value['revision']})


def decode_evidence(data):
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:
        raise ValueError('MISSION_EVIDENCE_BYTES')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('MISSION_EVIDENCE_DUPLICATE_KEY')
            result[key]=value
        return result
    return json.loads(data.decode('utf-8'),object_pairs_hook=unique)


def replay_mission_evidence(value, scope, mission_id, request_sha256, context):
    """Recompute the same fit from historical original frames; no fresh pose.

    Run outside control/heartbeat threads. A matching rejected fit stays
    rejected; this comparison neither applies a correction nor grants motion.
    """
    from .automatic_photo_alignment import align_photo_map
    value=checked_mission_evidence(value,scope,mission_id,request_sha256,context)
    original=value['photo_alignment']
    if original is None:
        return {'status':'NOT_RUN','reason':'PHOTO_FIT_NOT_RECORDED','current_pose_valid':False,
                'motion_authorized':False,'physical_demo_ready':False}
    nominal=scope['nominal']
    recomputed=align_photo_map(value['survey_map'],nominal['objects'],
        height_m=nominal['height_m'],policy=original['policy'])
    comparison={k:v for k,v in original.items() if k not in {'report_revision','goal_binding'}}
    return {'status':'MATCH' if recomputed==comparison else 'MISMATCH',
        'alignment_status':recomputed['status'],'reason':recomputed.get('reason'),
        'source_map_revision':value['survey_map']['revision'],'recomputed_revision':canonical_sha256(recomputed),
        'current_pose_valid':False,'motion_authorized':False,'physical_demo_ready':False}
