# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reopen exact accepted current-room survey evidence, never its old pose.

The opaque key names a hash-bound report, not a filesystem path. All selected
keyframes/tracking endpoints are preserved; this is not a free-space map.
"""
from copy import deepcopy
import re
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.mission_evidence_contract import checked_survey_map
from twinpulse_core.adaptive_mission_contract import nominal_room
from twinpulse_core.local_navigation import finite
from .chat_inspection_visual import KIND,checked_inspection_report


def reference_key(descriptor):
    from .chat_inspection_visual import checked_descriptor
    value=checked_descriptor(descriptor)
    return 'survey:'+value['mission_id']+':'+value['manifest_sha256']


def reference_descriptor(key):
    if not isinstance(key,str) or not re.fullmatch('survey:[a-f0-9]{32}:[a-f0-9]{64}',key):
        raise ValueError('SURVEY_REFERENCE_KEY_INVALID')
    _,identity,digest=key.split(':')
    return {'kind':KIND,'mission_id':identity,'manifest_sha256':digest}


def load_survey_reference(root,project_id,key,*,current_source=None,height_m=.182):
    report,_,effective=checked_inspection_report(root,project_id,reference_descriptor(key),current_source=current_source)
    # Full map's context is bound by the report digest, then validated again.
    saved=report.get('survey_map')
    if type(saved) is not dict:raise ValueError('SURVEY_REFERENCE_FULL_MAP_REQUIRED')
    context={'project_id':project_id,'source_revision':saved.get('source_revision')}
    saved=checked_survey_map(saved,context)
    if len(saved['tracking_endpoints'])<24:raise ValueError('SURVEY_REFERENCE_ENDPOINTS_REQUIRED')
    fit=report.get('photo_alignment')
    if (type(fit) is not dict or fit.get('schema')!='automatic-photo-alignment-1.0'
            or fit.get('status')!='ALIGNMENT_CANDIDATE'
            or fit.get('source_map_revision')!=saved['revision']
            or fit.get('report_revision')!=canonical_sha256({k:v for k,v in fit.items() if k!='report_revision'})
            or any(fit.get(k) is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready'))):
        raise ValueError('SURVEY_REFERENCE_ALIGNMENT_INVALID')
    transform=fit.get('room_from_map')
    if type(transform) is not list or len(transform)!=3 or any(not finite(v) or abs(v)>20 for v in transform):
        raise ValueError('SURVEY_REFERENCE_TRANSFORM_INVALID')
    original=nominal_room(report['room_source']['room']['objects'],height_m,report['room_base_revision'])
    structural=nominal_room(effective['objects'],height_m,effective['effective_revision'])
    if (fit.get('photo_outer_objects')!=original['objects']
            or fit.get('scene_revision_before')!=canonical_sha256(original['objects'])
            or (fit.get('sensor_section') or {}).get('height_m')!=height_m):
        raise ValueError('SURVEY_REFERENCE_NOMINAL_CHANGED')
    sequences={f['sequence'] for f in saved['keyframes']}
    selected=fit.get('fit_sequences');held=fit.get('validation_sequences')
    if (type(selected) is not list or type(held) is not list or not selected or not held
            or any(type(n) is not int or n not in sequences for n in selected+held)
            or selected!=sorted(set(selected)) or held!=sorted(set(held)) or max(selected)>=min(held)):
        raise ValueError('SURVEY_REFERENCE_HELD_OUT_REQUIRED')
    expected=fit.get('corrected_objects') if report.get('photo_correction') else fit.get('photo_outer_objects')
    if expected!=structural['objects']:raise ValueError('SURVEY_REFERENCE_EFFECTIVE_GEOMETRY_CHANGED')
    # Existing mission validation expects current effective room metadata.
    # These fields describe a checked reference; they do not upgrade the fit.
    alignment={**deepcopy(fit),'source_report_revision':fit['report_revision'],
               'room_base_revision':report['room_base_revision'],
               'effective_objects':deepcopy(effective['objects'])}
    alignment['report_revision']=canonical_sha256({k:v for k,v in alignment.items() if k!='report_revision'})
    return {'map_id':key,'map':saved,'photo_alignment':alignment,
            'reference_report_revision':report['revision'],'reference_kind':'accepted-survey-reference-1.0',
            'pose_candidate':None,'motion_authorized':False,'physical_demo_ready':False}
