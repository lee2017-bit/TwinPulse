# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Project-scoped, append-only derived photo revisions. Originals never change.

An effective scene is a recorded candidate, NOT an Isaac stage edit or a goal
authorization. A changed room base starts a distinct ledger; old evidence stays.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from twinpulse_core.revisions import canonical_sha256
from .project_store import ProjectStore, checked_project_id


def load_automatic_room(root,project_id):
    if project_id=='default':
        from .bedroom_review import load_bedroom_source
        draft,manifest,_=load_bedroom_source()
        provenance={'adapter':'preserved-bedroom','photo_revision':manifest['photo_sha256']}
    else:
        from .room_recipe import load_project_room_recipe
        draft,_=load_project_room_recipe(Path(root),project_id)
        provenance={'adapter':'room-recipe-1.0','photo_revision':draft.input_revision.images[0]['sha256']}
    from .scene_changes import SceneChangeStore
    history=SceneChangeStore(ProjectStore.for_project(Path(root),project_id).path.with_suffix('.scene-changes.json'),
                             project_id=project_id,source=draft).load()
    scene=history.replay(draft)[1].scene if history.operations else draft.site.scene
    body={'project_id':project_id,'input_revision':draft.input_revision.digest,
          'scene_revision':scene.revision,'objects':json.loads(json.dumps(scene.to_dict()['objects'])),**provenance}
    return {**body,'revision':canonical_sha256(body)}


def _wall_change(before,after):
    if len(before)!=len(after) or len(before)>256:raise ValueError('PHOTO_CORRECTION_OBJECT_BUDGET')
    changed=0
    for a,b in zip(before,after):
        if a==b:continue
        if a['kind']!='wall' or b['kind']!='wall':raise ValueError('PHOTO_CORRECTION_NOT_WALL')
        expected=deepcopy(a)
        pa=a['transform']['position_m'];pb=b['transform']['position_m']
        if len(pb)!=3 or pa[2]!=pb[2] or sum((pa[j]-pb[j])**2 for j in range(2))>.200001**2:
            raise ValueError('PHOTO_CORRECTION_TRANSLATION_BUDGET')
        expected['transform']['position_m'][:2]=pb[:2]
        if expected!=b:raise ValueError('PHOTO_CORRECTION_CHANGED_UNOBSERVED_FIELDS')
        changed+=1
    if not 1<=changed<=2:raise ValueError('PHOTO_CORRECTION_WALL_COUNT')


class AutomaticPhotoStore:
    def __init__(self,root,project_id):
        self.root=Path(root).resolve();self.project_id=checked_project_id(project_id)
        self.folder=self.root/'artifacts'/'automatic-photo-alignment'/self.project_id

    def _safe(self,path):
        if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents) if p!=self.root.parent):
            raise ValueError('PHOTO_LEDGER_PATH_UNSAFE')
        if not path.is_relative_to(self.root):raise ValueError('PHOTO_LEDGER_PATH_UNSAFE')
        return path

    def _ledger(self,room):
        if room['project_id']!=self.project_id or re.fullmatch('[a-f0-9]{64}',room['revision']) is None:
            raise ValueError('PHOTO_LEDGER_ROOM_INVALID')
        body={k:v for k,v in room.items() if k!='revision'}
        if canonical_sha256(body)!=room['revision']:raise ValueError('PHOTO_ROOM_HASH_CHANGED')
        return self._safe(self.folder/'revisions'/room['revision'])

    def current(self,room):
        folder=self._ledger(room);events=[]
        if folder.exists():
            files=sorted(folder.glob('*.json'))
            if len(files)>128:raise ValueError('PHOTO_LEDGER_CAPACITY')
            previous=None;objects=deepcopy(room['objects'])
            for index,path in enumerate(files):
                self._safe(path)
                if path.name!=f'{index:04d}.json' or path.stat().st_size>512*1024:raise ValueError('PHOTO_LEDGER_INVALID')
                event=json.loads(path.read_text(encoding='utf-8'))
                revision=event.pop('revision',None)
                if (canonical_sha256(event)!=revision or event['project_id']!=self.project_id
                    or event['base_revision']!=room['revision'] or event['parent']!=previous
                    or event['before_objects']!=objects or event['motion_authorized'] is not False):
                    raise ValueError('PHOTO_LEDGER_HASH_OR_CHAIN_CHANGED')
                if event['action']=='apply':_wall_change(objects,event['objects'])
                elif event['action']=='rollback':
                    if not events or events[-1]['action']!='apply' or event['objects']!=events[-1]['before_objects']:
                        raise ValueError('PHOTO_ROLLBACK_INVALID')
                else:raise ValueError('PHOTO_LEDGER_ACTION_INVALID')
                event['revision']=revision;events.append(event);previous=revision;objects=event['objects']
        else:objects=deepcopy(room['objects'])
        return {'objects':deepcopy(objects),'head':events[-1]['revision'] if events else None,'events':events,
                'base_revision':room['revision'],'effective_revision':canonical_sha256(objects)}

    def append(self,room,expected_head,after,*,action,job_id,map_revision):
        current=self.current(room)
        if current['head']!=expected_head:raise ValueError('PHOTO_LEDGER_HEAD_CHANGED')
        if re.fullmatch('[a-f0-9]{32}',job_id) is None:raise ValueError('PHOTO_JOB_INVALID')
        if action=='apply':_wall_change(current['objects'],after)
        elif action=='rollback':
            if not current['events'] or current['events'][-1]['action']!='apply' or after!=current['events'][-1]['before_objects']:
                raise ValueError('PHOTO_ROLLBACK_INVALID')
        else:raise ValueError('PHOTO_LEDGER_ACTION_INVALID')
        folder=self._ledger(room);folder.mkdir(parents=True,exist_ok=True)
        index=len(current['events'])
        if index>=128:raise ValueError('PHOTO_LEDGER_CAPACITY')
        body={'schema':'automatic-photo-revision-1.0','project_id':self.project_id,'base_revision':room['revision'],
              'parent':expected_head,'action':action,'job_id':job_id,'source_map_revision':map_revision,
              'before_objects':current['objects'],'objects':deepcopy(after),'motion_authorized':False,
              'physical_demo_ready':False,'goal_revalidation_required':True}
        body['revision']=canonical_sha256(body)
        self._write(self._safe(folder/f'{index:04d}.json'),body)
        return body

    def _write(self,path,value):
        # Exclusive append is also the cross-process compare-and-append lock.
        encoded=json.dumps(value,sort_keys=True,allow_nan=False)
        if len(encoded.encode('utf-8'))>512*1024:raise ValueError('PHOTO_REPORT_SIZE_BUDGET')
        path.parent.mkdir(parents=True,exist_ok=True);self._safe(path)
        with path.open('x',encoding='utf-8') as f:f.write(encoded)

    def save_report(self,job_id,value):
        if re.fullmatch('[a-f0-9]{32}',job_id) is None:raise ValueError('PHOTO_JOB_INVALID')
        body={**value,'project_id':self.project_id,'job_id':job_id}
        body['report_revision']=canonical_sha256(body)
        self._write(self._safe(self.folder/'reports'/f'{job_id}.json'),body)
        return body

    def report(self,job_id):
        if re.fullmatch('[a-f0-9]{32}',job_id) is None:raise ValueError('PHOTO_JOB_INVALID')
        path=self._safe(self.folder/'reports'/f'{job_id}.json')
        if path.stat().st_size>512*1024:raise ValueError('PHOTO_REPORT_SIZE_BUDGET')
        value=json.loads(path.read_text(encoding='utf-8'));revision=value.pop('report_revision')
        if canonical_sha256(value)!=revision or value['project_id']!=self.project_id or value['job_id']!=job_id:
            raise ValueError('PHOTO_REPORT_HASH_CHANGED')
        return {**value,'report_revision':revision}
