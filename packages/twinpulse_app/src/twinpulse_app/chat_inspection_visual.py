# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current-chat saved survey -> immutable historical 3D. No device authority.

No default-bedroom or room-recipe fallback: the exact scene is captured before
admission and bound to the raw report and append-only correction ledger.
"""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import re
from twinpulse_core.models import SceneObject
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.site_contracts import SceneRevision
from .automatic_photo_store import AutomaticPhotoStore
from .project_store import checked_project_id

KIND='current_inspection_visual_v1'

def checked_descriptor(value):
    if (type(value) is not dict or set(value)!={'kind','manifest_sha256','mission_id'}
            or value['kind']!=KIND):raise ValueError('INSPECTION_DISPLAY_DESCRIPTOR')
    for key,size in (('mission_id',32),('manifest_sha256',64)):
        if not isinstance(value[key],str) or re.fullmatch('[a-f0-9]{'+str(size)+'}',value[key]) is None:
            raise ValueError('INSPECTION_DISPLAY_DESCRIPTOR')
    return deepcopy(value)

def checked_source(value,project_id):
    if type(value) is not dict or set(value)!={'room','scene'}:raise ValueError('INSPECTION_SCENE_SOURCE_INVALID')
    room=value['room'];scene=SceneRevision.from_dict(value['scene'])
    if (type(room) is not dict or set(room)!={'project_id','input_revision','scene_revision','objects',
            'adapter','photo_revision','revision'} or room['project_id']!=project_id
            or room['adapter']!='current-chat-room-1.0'
            or room['revision']!=canonical_sha256({k:v for k,v in room.items() if k!='revision'})
            or room['scene_revision']!=scene.revision or canonical_sha256(room['objects'])!=canonical_sha256(scene.to_dict()['objects'])):
        raise ValueError('INSPECTION_SCENE_SOURCE_CHANGED')
    for key in ('input_revision','photo_revision'):
        if room[key] is None and key=='photo_revision':continue
        if not isinstance(room[key],str) or re.fullmatch('[a-f0-9]{64}',room[key]) is None:
            raise ValueError('INSPECTION_SCENE_SOURCE_INVALID')
    return room,scene

def derived_scene(source,effective):
    # An unchanged room keeps its original revision; no invented parent revision.
    if canonical_sha256(source.to_dict()['objects'])==canonical_sha256(effective['objects']):return source
    return replace(source,objects=tuple(SceneObject.from_dict(o) for o in effective['objects']),
                   parent_revision=source.revision)

def load_current_source(root,project_id):
    """Engine-side check against the saved active draft plus reviewed edits."""
    from .project_store import ProjectStore
    from .scene_changes import SceneChangeStore
    store=ProjectStore.for_project(Path(root),project_id);record=store.load()
    draft=record.site_draft if record else None
    if draft is None or record.latest_input is None or record.latest_input.digest!=draft.input_revision.digest:
        raise ValueError('INSPECTION_DISPLAY_CURRENT_ROOM_UNAVAILABLE')
    history=SceneChangeStore(store.path.with_suffix('.scene-changes.json'),project_id=project_id,source=draft).load()
    scene=history.replay(draft)[1].scene if history.operations else draft.site.scene
    body={'project_id':project_id,'input_revision':draft.input_revision.digest,'scene_revision':scene.revision,
          'objects':json.loads(json.dumps(scene.to_dict()['objects'])),'adapter':'current-chat-room-1.0',
          'photo_revision':draft.input_revision.images[0]['sha256'] if draft.input_revision.images else None}
    return {'room':{**body,'revision':canonical_sha256(body)},'scene':json.loads(json.dumps(scene.to_dict()))}


def active_chat_placement(root,project_id,scene):
    """Current saved chat room and derived geometry, fixed visual asset only."""
    room,source=checked_source(load_current_source(root,project_id),project_id)
    effective=AutomaticPhotoStore(root,project_id).current(room)
    if derived_scene(source,effective)!=scene:raise ValueError('ACTIVE_CHAT_ROOM_REVISION_CHANGED')
    floors=[o for o in scene.objects if o.kind=='floor']
    if len(floors)!=1:raise ValueError('ACTIVE_CHAT_FLOOR_REQUIRED')
    from .simulation_assets import burger_inventory
    burger_inventory()
    floor=floors[0];z=floor.transform.position_m[2]+floor.shape.dimensions_m[2]/2+.002
    return {'robot_placement':{'position_m':[0.,0.,z]}}

def checked_inspection_report(root,project_id,descriptor,*,current_source=None,source_root=None):
    project_id=checked_project_id(project_id);descriptor=checked_descriptor(descriptor)
    base=Path(root).resolve()
    path=base/'artifacts'/'automatic-mission'/project_id/(descriptor['mission_id']+'.json')
    if (path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents))
            or not path.is_file() or path.stat().st_size>4*1024*1024):
        raise ValueError('INSPECTION_DISPLAY_PATH_OR_BUDGET')
    report=json.loads(path.read_text(encoding='utf-8'))
    if (type(report) is not dict or report.get('revision')!=descriptor['manifest_sha256']
            or canonical_sha256({k:v for k,v in report.items() if k!='revision'})!=descriptor['manifest_sha256']):
        raise ValueError('INSPECTION_DISPLAY_REPORT_HASH_CHANGED')
    if (report.get('schema')!='automatic-mission-report-1.0' or report.get('project_id')!=project_id
            or report.get('job_id')!=descriptor['mission_id'] or report.get('state')!='MISSION_ARRIVED'
            or report.get('goal',{}).get('mode')!='SURVEY_ONLY'
            or report.get('cold_start',{}).get('stage')!='SURVEY_COMPLETE'
            or report.get('cold_start',{}).get('alignment_status')!='ALIGNMENT_CANDIDATE'
            or any(report.get(k) for k in ('error','cleanup_error','report_error'))
            or report.get('motion_authorized') is not False or report.get('physical_demo_ready') is not False):
        raise ValueError('INSPECTION_DISPLAY_SURVEY_NOT_COMPLETE')
    room,source=checked_source(report.get('room_source'),project_id)
    if current_source is None:current_source=load_current_source(source_root if source_root is not None else base,project_id)
    checked_source(current_source,project_id)
    if current_source!=report['room_source']:raise ValueError('INSPECTION_DISPLAY_CURRENT_ROOM_CHANGED')
    effective=AutomaticPhotoStore(base,project_id).current(room)
    if (report['room_base_revision']!=room['revision']
            or report['goal']['room_revision']!=effective['effective_revision']
            or report.get('objects_revision')!=canonical_sha256(effective['objects'])):
        raise ValueError('INSPECTION_DISPLAY_LEDGER_CHANGED')
    correction=report.get('photo_correction')
    if correction:
        latest=effective['events'][-1] if effective['events'] else {}
        if (latest.get('action')!='apply' or latest.get('job_id')!=descriptor['mission_id']
                or latest.get('revision')!=correction.get('applied_revision')
                or correction.get('effective_revision')!=effective['effective_revision']
                or correction.get('goal_revalidation')!='SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL'):
            raise ValueError('INSPECTION_DISPLAY_CORRECTION_NOT_VERIFIED')
    return report,source,effective


def checked_inspection_visual(root,project_id,descriptor,*,current_source=None,source_root=None):
    report,source,effective=checked_inspection_report(root,project_id,descriptor,
        current_source=current_source,source_root=source_root)
    visual=report.get('visual')
    if (type(visual) is not dict or visual.get('session_id')!=report['job_id']
            or visual.get('revision')!=canonical_sha256({k:v for k,v in visual.items() if k!='revision'})
            or visual.get('room_revision')!=effective['effective_revision']
            or visual.get('pose_room') is None or visual.get('goal_room') is not None
            or visual.get('route_room')!=[] or visual.get('motion_authorized') is not False
            or visual.get('physical_demo_ready') is not False):
        raise ValueError('INSPECTION_DISPLAY_HISTORICAL_VISUAL_INVALID')
    for key,count,budget in (('pose_room',3,1),('scan_room',2,720),('trajectory_room',3,512)):
        rows=[visual[key]] if key=='pose_room' else visual[key]
        if type(rows) is not list or len(rows)>budget:raise ValueError('INSPECTION_DISPLAY_GEOMETRY_BUDGET')
        for row in rows:
            if (type(row) is not list or len(row)!=count
                    or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>12.1 for v in row)):
                raise ValueError('INSPECTION_DISPLAY_GEOMETRY_INVALID')
    return derived_scene(source,effective),deepcopy(visual)
