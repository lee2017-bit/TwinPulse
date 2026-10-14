# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Checked saved mission -> derived scene/visual descriptor. No device authority."""
from dataclasses import replace
import json
import re
import math
from pathlib import Path
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.models import SceneObject
from .automatic_photo_store import AutomaticPhotoStore,load_automatic_room


def checked_mission_geometry(root,project_id,descriptor):
    """Reopen an exact immutable owned correction; never consume a live pose."""
    from .project_store import checked_project_id
    project_id=checked_project_id(project_id)
    fields={'kind','mission_id','correction_revision','previous_objects_revision','objects_revision'}
    if not isinstance(descriptor,dict) or set(descriptor)!=fields or descriptor['kind']!='active_mission_geometry_v1':
        raise ValueError('ACTIVE_GEOMETRY_DESCRIPTOR')
    for key,size in (('mission_id',32),('correction_revision',64),('previous_objects_revision',64),('objects_revision',64)):
        if not isinstance(descriptor[key],str) or not re.fullmatch('[a-f0-9]{'+str(size)+'}',descriptor[key]):
            raise ValueError('ACTIVE_GEOMETRY_DESCRIPTOR')
    room=load_automatic_room(root,project_id);effective=AutomaticPhotoStore(root,project_id).current(room)
    if not effective['events']:raise ValueError('ACTIVE_GEOMETRY_CORRECTION_MISSING')
    event=effective['events'][-1]
    if (event['action']!='apply' or event['job_id']!=descriptor['mission_id']
            or event['revision']!=descriptor['correction_revision']
            or canonical_sha256(event['before_objects'])!=descriptor['previous_objects_revision']
            or effective['effective_revision']!=descriptor['objects_revision']
            or event['physical_demo_ready'] is not False or event['goal_revalidation_required'] is not True):
        raise ValueError('ACTIVE_GEOMETRY_CORRECTION_CHANGED')
    if project_id=='default':
        from .bedroom_review import load_bedroom_source
        draft,manifest,assets=load_bedroom_source()
    else:
        from .room_recipe import load_project_room_recipe,load_project_room_visual
        draft,_=load_project_room_recipe(Path(root),project_id)
        loaded=load_project_room_visual(Path(root),project_id,draft)
        if loaded is None:raise ValueError('ACTIVE_VISUAL_BURGER_REQUIRED')
        manifest,assets=loaded
    scene=replace(draft.site.scene,objects=tuple(SceneObject.from_dict(o) for o in effective['objects']),
                  parent_revision=draft.site.scene.revision)
    return draft,manifest,assets,scene


def checked_mission_visual(root,project_id,descriptor):
    from .project_store import checked_project_id
    project_id=checked_project_id(project_id)
    if (not isinstance(descriptor,dict) or set(descriptor)!={'kind','manifest_sha256','mission_id'}
            or descriptor['kind']!='automatic_mission_visual_v1'
            or not isinstance(descriptor['mission_id'],str)
            or re.fullmatch('[a-f0-9]{32}',descriptor['mission_id']) is None):raise ValueError('MISSION_VISUAL_DESCRIPTOR')
    path=Path(root).resolve()/'artifacts'/'automatic-mission'/project_id/f"{descriptor['mission_id']}.json"
    if path.resolve()!=path or any(p.is_symlink() for p in path.parents) or path.stat().st_size>4*1024*1024:
        raise ValueError('MISSION_VISUAL_PATH_OR_BUDGET')
    report=json.loads(path.read_text(encoding='utf-8'));revision=report.pop('revision')
    if canonical_sha256(report)!=revision or revision!=descriptor['manifest_sha256']:
        raise ValueError('MISSION_VISUAL_REPORT_HASH_CHANGED')
    if report['project_id']!=project_id or report['job_id']!=descriptor['mission_id']:
        raise ValueError('MISSION_VISUAL_PROJECT_CHANGED')
    if report['motion_authorized'] is not False or report['physical_demo_ready'] is not False:
        raise ValueError('MISSION_VISUAL_AUTHORITY')
    room=load_automatic_room(root,project_id);effective=AutomaticPhotoStore(root,project_id).current(room)
    if report['room_base_revision']!=room['revision'] or report['goal']['room_revision']!=effective['effective_revision']:
        raise ValueError('MISSION_VISUAL_ROOM_CHANGED')
    visual=report['visual']
    if not visual or visual['pose_room'] is None:raise ValueError('MISSION_VISUAL_POSE_UNAVAILABLE')
    body={k:v for k,v in visual.items() if k!='revision'}
    if canonical_sha256(body)!=visual['revision'] or visual['session_id']!=descriptor['mission_id']:
        raise ValueError('MISSION_VISUAL_SNAPSHOT_CHANGED')
    if (len(visual['scan_room'])>720 or len(visual['trajectory_room'])>512 or len(visual['route_room'])>16):
        raise ValueError('MISSION_VISUAL_GEOMETRY_BUDGET')
    for rows,count in (([visual['pose_room']],3),([visual['goal_room']] if visual.get('goal_room') is not None else [],2),(visual['scan_room'],2),
                       (visual['trajectory_room'],3),(visual['route_room'],2)):
        for p in rows:
            if (not isinstance(p,list) or len(p)!=count or any(type(v) not in (int,float)
                    or not math.isfinite(v) or abs(v)>12.1 for v in p)):
                raise ValueError('MISSION_VISUAL_GEOMETRY_INVALID')
    if visual.get('motion_authorized') is not False or visual.get('physical_demo_ready') is not False:
        raise ValueError('MISSION_VISUAL_AUTHORITY')
    if project_id=='default':
        from .bedroom_review import load_bedroom_source
        draft,manifest,assets=load_bedroom_source()
    else:
        from .room_recipe import load_project_room_recipe,load_project_room_visual
        draft,_=load_project_room_recipe(Path(root),project_id)
        loaded=load_project_room_visual(Path(root),project_id,draft)
        if loaded is None:raise ValueError('MISSION_VISUAL_BURGER_ASSET_REQUIRED')
        manifest,assets=loaded
    scene=replace(draft.site.scene,objects=tuple(SceneObject.from_dict(o) for o in effective['objects']),
                  parent_revision=draft.site.scene.revision)
    return draft,manifest,assets,scene,visual
