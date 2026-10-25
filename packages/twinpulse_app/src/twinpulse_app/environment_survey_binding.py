# SPDX-License-Identifier: Apache-2.0
"""Immutable collection-to-edit receipt, checked on admission AND after ACK."""
from copy import deepcopy
import hashlib,json,re
from twinpulse_core.revisions import canonical_sha256

FIELDS={'schema_version','policy','job_id','context','collection_sha256','result_sha256',
        'candidate_id','preview_sha256','physical_authority'}

def checked_survey_binding(value):
    from .scene_sensor_review import checked_context
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema_version']!='environment-survey-binding-1.0'
            or value['policy']!='review_survey_obstacle' or value['physical_authority'] is not False):
        raise ValueError('SURVEY_BINDING_INVALID')
    checked_context(value['context'])
    for key in ('collection_sha256','result_sha256','preview_sha256'):
        if not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{64}',value[key]):raise ValueError('SURVEY_BINDING_SHA')
    if not re.fullmatch('[a-f0-9]{32}',str(value['job_id'])) or not re.fullmatch('Residual_[a-f0-9]{20}',str(value['candidate_id'])):
        raise ValueError('SURVEY_BINDING_ID')
    return deepcopy(value)

def validate_survey_apply(adapter,binding,operation,store,history):
    binding=checked_survey_binding(binding)
    if binding['context']!=adapter.context(store,history) or binding['preview_sha256']!=canonical_sha256(operation):
        raise ValueError('SURVEY_APPLY_CONTEXT_CHANGED')
    root=store.path.parent/'environment-imports'/'survey-reviews'
    folder=root/binding['job_id']
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (folder,*folder.parents)):
        raise ValueError('SURVEY_APPLY_PATH')
    def read(name,expected):
        path=folder/name
        if path.is_symlink() or path.stat().st_size>32*1024*1024:raise ValueError('SURVEY_APPLY_FILE')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('SURVEY_APPLY_SOURCE_CHANGED')
        return json.loads(raw)
    result=read('result.json',binding['result_sha256']);collection=read('collection.json',binding['collection_sha256'])
    if (folder/'revoked.json').exists() or result['status']!='GEOMETRIC_REVIEW' or result['context']['scene_revision']!=binding['context']['current_scene_revision']:
        raise ValueError('SURVEY_APPLY_REVIEW_REVOKED')
    if collection['robot_kind'] not in {'sim','physical'} or result['frames_sha256']!=canonical_sha256(collection['frames']):
        raise ValueError('SURVEY_APPLY_FRAMES_CHANGED')
    # Re-read every original task/observation and sealed native segment. A
    # saved derived JSON is not a replacement for the user's source recording.
    from .task_collection import TaskCollection
    if result['source']=='TASK':
        original=TaskCollection(store.path.parent/'robot-tasks',history.project_id,
            physical_root=result.get('physical_state_root')).load(collection['task_id'])
        if original!=collection:raise ValueError('SURVEY_APPLY_ORIGINAL_COLLECTION_CHANGED')
    else:raise ValueError('SURVEY_APPLY_SAVED_COLLECTION_REQUIRED')
    candidate=next((c for c in result['obstacle_candidates'] if c['candidate_id']==binding['candidate_id']),None)
    if candidate is None:raise ValueError('SURVEY_APPLY_CANDIDATE_MISSING')
    env=history.effective(store.source).site.scene.environment
    if canonical_sha256(env)!=result['context']['environment_sha256']:raise ValueError('SURVEY_APPLY_ENVIRONMENT_CHANGED')
    call=operation.get('tool_call') or {};after=(call.get('arguments') or {}).get('environment')
    if call.get('tool')!='import_environment' or not isinstance(after,dict):raise ValueError('SURVEY_APPLY_OPERATION')
    old={o['item']['id']:o for o in env.get('overlays',[])};new={o['item']['id']:o for o in after.get('overlays',[])}
    added=set(new)-set(old)
    if len(added)!=1 or any(new.get(k)!=v for k,v in old.items()):raise ValueError('SURVEY_APPLY_OVERLAY_DELTA')
    overlay=new[next(iter(added))];item=overlay['item']
    if (item['position_m'][:2]!=candidate['position_xy_m'] or item['dimensions_m'][:2]!=candidate['observed_extent_xy_m']
            or overlay['uncertainty_m']<candidate['uncertainty_m']):raise ValueError('SURVEY_APPLY_CANDIDATE_CHANGED')
    unchanged=deepcopy(after)
    unchanged['schema_version']=env['schema_version']
    if 'overlays' in env:unchanged['overlays']=deepcopy(env['overlays'])
    else:unchanged.pop('overlays',None)
    if unchanged!=env:raise ValueError('SURVEY_APPLY_SOURCE_GEOMETRY_CHANGED')
