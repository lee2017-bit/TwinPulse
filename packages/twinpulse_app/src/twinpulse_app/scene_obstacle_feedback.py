# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable obstacle observations and sensor-bound ordinary scene edits."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import os
import re
from pathlib import Path
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core.obstacle_feedback import checked_observation, finite, project_observation, propose_translation
from .command_broker import BrokerError


def checked_obstacle_binding(value):
    from .scene_sensor_review import checked_context
    fields={'schema_version','policy','context','observation_id','observation_sha256','target_id',
        'translation_xy_m','mode','preview_sha256','execution_id','physical_authority'}
    if (not isinstance(value,dict) or set(value)!=fields or value.get('schema_version')!='scene-obstacle-binding-1.0'
            or value.get('policy')!='correct_obstacles' or value.get('physical_authority') is not False
            or value.get('mode') not in {'manual_estimate','surface_candidate'}):
        raise ValueError('OBSTACLE_BINDING_INVALID')
    checked_context(value['context'])
    for key,length in (('observation_id',32),('observation_sha256',64),('preview_sha256',64),('execution_id',32)):
        if not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',value[key]):
            raise ValueError('OBSTACLE_BINDING_INVALID')
    if not isinstance(value['target_id'],str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',value['target_id']):
        raise ValueError('OBSTACLE_BINDING_TARGET_INVALID')
    delta=value['translation_xy_m']
    if not isinstance(delta,list) or len(delta)!=2:raise ValueError('OBSTACLE_TRANSLATION_INVALID')
    for v in delta:finite(v,-10,10)
    return deepcopy(value)


class SceneObstacleFeedback:
    def __init__(self,review,*,root=None):
        self.review=review;self.workflow=review.workflow
        # New observations belong to writable user data, never an immutable
        # packaged source/archive root. Existing legacy map readers are separate.
        self.root=Path(root if root is not None else review.root).resolve()

    def _folder(self,context):
        folder=self.root/'artifacts/obstacle-feedback'/context['project_id']/context['input_revision']
        if any(p.is_symlink() for p in (folder,*folder.parents)):
            raise ValueError('OBSTACLE_STORE_PATH_INVALID')
        return folder

    def _load(self,identity,context):
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('OBSTACLE_ID_INVALID')
        path=self._folder(context)/(identity+'.json')
        if path.is_symlink() or path.stat().st_size>4*1024*1024:raise ValueError('OBSTACLE_STORE_INVALID')
        value=json.loads(path.read_text(encoding='utf-8'))
        if (value.get('id')!=identity or value.get('sha256')!=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
                or value['context']['input_revision']!=context['input_revision']
                or value['context']['source_sha256']!=context['source_sha256']):
            raise ValueError('OBSTACLE_RECORD_CHANGED')
        # Rebuild the projection from the preserved sensor values, never trust a
        # client-supplied or persisted endpoint list as source measurements.
        projection=project_observation(value['source'],value['sensor_pose_m'],value['scan_height_m'])
        if any(value.get(k)!=v for k,v in projection.items()):raise ValueError('OBSTACLE_PROJECTION_CHANGED')
        return value

    def snapshot(self):
        # Capture context and targets from the SAME checked state exactly once.
        # Replaying the history again for each metadata field held the common
        # workflow lock beyond the renderer's ordinary 3 s read deadline.
        # This point-in-time catalog grants no write authority: preview/Apply
        # recapture context and verify the immutable evidence independently.
        context,calls=self.review.read_state()
        folder=self._folder(context);paths=sorted(folder.glob('*.json')) if folder.exists() else []
        if len(paths)>256:raise ValueError('OBSTACLE_RECORD_CATALOG_BUDGET')
        records=[self._load(p.stem,context) for p in paths]
        records.sort(key=lambda r:r['received_at_utc'])
        targets=[]
        for call in calls:
            a=call['arguments']
            if call['tool'] in {'place_furniture','place_model_recipe','place_library_asset','place_room_item','create_box_obstacle'}:
                pos=a.get('center_m',a.get('position_m'))
                if isinstance(pos,(list,tuple)) and len(pos)>=2:
                    targets.append(dict(id=a['id'],label=a.get('label',a['id']),center_m=list(pos[:2])))
        return dict(schema_version='obstacle-feedback-1.0',context=context,targets=targets,
            observations=[{k:v for k,v in r.items() if k not in {'source','context'}} for r in records],physical_authority=False)

    def _current(self,body):
        context=self.review.context()
        if (body.get('expected_scene_revision')!=context['current_scene_revision'] or
                body.get('expected_state_sha256')!=context['current_state_sha256']):
            raise BrokerError('obstacle_scene_changed','The current Twin changed. Refresh the obstacle review.',status=409)
        return context

    def import_observation(self,body,owner):
        context=self._current(body)
        trace=self.workflow._edit_trace('obstacle_observation_import','obstacle_'+uuid4().hex)
        try:
            supplied=body['observation'];file_sha=None
            if isinstance(supplied,dict) and set(supplied)=={'json_text'}:
                text=supplied['json_text']
                if not isinstance(text,str) or len(text.encode('utf-8'))>2*1024*1024:
                    raise ValueError('OBSTACLE_SOURCE_BYTES_INVALID')
                file_sha=hashlib.sha256(text.encode('utf-8')).hexdigest()
                supplied=json.loads(text)
            source=checked_observation(supplied)
            projected=project_observation(source,body['sensor_pose_m'],body['scan_height_m'])
            identity=canonical_sha256(dict(source=source,context={k:context[k] for k in
                ('project_id','input_revision','source_sha256')},sensor_pose_m=projected['sensor_pose_m'],
                scan_height_m=projected['scan_height_m'],source_file_sha256=file_sha))[:32]
            with self.workflow.scene_edit_transaction.admission(owner),self.workflow._lock:
                if self.review.context()!=context:raise ValueError('OBSTACLE_SCENE_CHANGED')
                folder=self._folder(context);folder.mkdir(parents=True,exist_ok=True);path=folder/(identity+'.json')
                if path.exists():self._load(identity,context)
                else:
                    if len(list(folder.glob('*.json')))>=256:raise ValueError('OBSTACLE_RECORD_CATALOG_BUDGET')
                    value=dict(id=identity,source=source,context=context,provenance=source['provenance'],
                        source_attribution=source.get('source_attribution'),
                        source_file_sha256=file_sha,
                        execution_id=trace.execution_id,received_at_utc=datetime.now(timezone.utc).isoformat(),**projected)
                    value['sha256']=canonical_sha256(value)
                    temporary=folder/('.tmp-'+uuid4().hex)
                    try:
                        with temporary.open('xb') as stream:
                            stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'));stream.flush();os.fsync(stream.fileno())
                        temporary.replace(path)
                    finally:
                        if temporary.exists():temporary.unlink()
            trace.bind(observation_id=identity,persisted=True,physical_authority=False)
            if source.get('source_attribution'):
                trace.bind(sensor_execution_id=source['source_attribution']['source_execution_id'],
                    sensor_raw_sha256=source['source_attribution']['export_sha256'])
            trace.finish('succeeded');return self.snapshot()
        except Exception as error:
            trace.finish('failed',error=error);raise

    @staticmethod
    def _patch(state,target,delta):
        old=next((c for c in state.plan.calls if c.arguments['id']==target),None)
        if old is None or old.tool not in {'place_furniture','place_model_recipe','place_library_asset','place_room_item','create_box_obstacle'}:
            raise ValueError('OBSTACLE_TARGET_NOT_EDITABLE')
        call=old.to_dict();key='center_m' if 'center_m' in call['arguments'] else 'position_m'
        call['arguments'][key]=list(call['arguments'][key])
        for i in range(2):call['arguments'][key][i]+=delta[i]
        from .dependency_patch import PATCH_VERSION
        return dict(patch_version=PATCH_VERSION,edits=[dict(action='change',target_id=target,
            reason='Sensor-informed draft translation; object correspondence and room pose are estimates',tool_call=call)])

    def preview(self,body):
        context,store,history,state=self.review.capture_state()
        if (body.get('expected_scene_revision')!=context['current_scene_revision'] or
                body.get('expected_state_sha256')!=context['current_state_sha256']):
            raise BrokerError('obstacle_scene_changed','The current Twin changed. Refresh the obstacle review.',status=409)
        trace=self.workflow._edit_trace('obstacle_correction_preview','obstacle_'+uuid4().hex)
        result=dict(status='HELD',reason='',execution_id=trace.execution_id,observation_id=body['observation_id'],
            observation_sha256=body['observation_sha256'],apply_version='scene-edit-apply-2.0')
        try:
            evidence=self._load(body['observation_id'],context)
            if evidence['sha256']!=body['observation_sha256']:raise ValueError('OBSTACLE_RECORD_CHANGED')
            # Immutable captured state: fitting never holds the common status,
            # project-switch or command-admission lock.
            delta=body['translation_xy_m'];mode='manual_estimate';fit=None
            if delta is None:
                from .scene_changes import _emitted_ids
                call=next((c for c in state.plan.calls if c.arguments['id']==body['target_id']),None)
                if call is None:raise ValueError('OBSTACLE_TARGET_NOT_EDITABLE')
                ids=_emitted_ids(call)
                fit=propose_translation(evidence,[o for o in state.site.scene.to_dict()['objects'] if o['id'] in ids])
                if fit['status']!='candidate':
                    trace.finish('succeeded',sensor_status='HELD')
                    return {**result,'reason':fit['reason'],'fit':fit}
                delta=fit['translation_xy_m'];mode='surface_candidate'
            if not isinstance(delta,list) or len(delta)!=2:raise ValueError('OBSTACLE_TRANSLATION_INVALID')
            delta=[finite(v,-10,10) for v in delta]
            if abs(delta[0])+abs(delta[1])<1e-6:raise ValueError('OBSTACLE_TRANSLATION_UNCHANGED')
            # Pure candidate compilation can be slow for a large edit history.
            # Keep status/connection reads available while it runs. The exact
            # captured state remains bound to the proof, then is recaptured
            # strictly before publishing; Apply validates it independently.
            patch=self._patch(state,body['target_id'],delta)
            preview=history.preview(store.source,operation_id='sensor_'+uuid4().hex,mode='dependency',tool_call=patch)
            binding=checked_obstacle_binding(dict(schema_version='scene-obstacle-binding-1.0',policy='correct_obstacles',
                context=context,observation_id=body['observation_id'],observation_sha256=evidence['sha256'],
                target_id=body['target_id'],translation_xy_m=delta,mode=mode,preview_sha256=preview['preview_digest'],
                execution_id=trace.execution_id,physical_authority=False))
            if self.review.context()!=context:raise ValueError('OBSTACLE_SCENE_CHANGED')
            # A server-written immutable proof prevents a caller from relabeling
            # manual edits as an automatic fit or inventing the execution link.
            folder=self._folder(context)/'proposals';folder.mkdir(parents=True,exist_ok=True)
            proof=dict(binding=binding,operation=preview['operation'])
            proof['sha256']=canonical_sha256(proof)
            with (folder/(trace.execution_id+'.json')).open('x',encoding='utf-8') as stream:
                json.dump(proof,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            trace.bind(observation_id=body['observation_id'],preview_sha256=preview['preview_digest'],physical_authority=False)
            trace.finish('succeeded',sensor_status='preview')
            return {**result,**preview,'status':'preview','reason':'Editable sensor-informed candidate; correspondence and coordinates remain estimates',
                'translation_xy_m':delta,'fit':fit,'sensor_binding':binding}
        except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
            trace.finish('failed',error=error);return {**result,'reason':str(error)[:300]}

    def validate_apply(self,binding,operation,store,history):
        binding=checked_obstacle_binding(binding);context=self.review.context(store,history)
        if binding['context']!=context or binding['preview_sha256']!=canonical_sha256(operation):
            raise ValueError('OBSTACLE_APPLY_CONTEXT_CHANGED')
        evidence=self._load(binding['observation_id'],context)
        if evidence['sha256']!=binding['observation_sha256']:raise ValueError('OBSTACLE_RECORD_CHANGED')
        path=self._folder(context)/'proposals'/(binding['execution_id']+'.json')
        if any(p.is_symlink() for p in (path,*path.parents)) or path.stat().st_size>4*1024*1024:
            raise ValueError('OBSTACLE_PREVIEW_PROOF_INVALID')
        proof=json.loads(path.read_text(encoding='utf-8'))
        if (proof.get('sha256')!=canonical_sha256({k:v for k,v in proof.items() if k!='sha256'})
                or proof.get('binding')!=binding or proof.get('operation')!=operation):
            raise ValueError('OBSTACLE_PREVIEW_PROOF_CHANGED')
        state=history.effective(store.source)
        expected=self._patch(state,binding['target_id'],binding['translation_xy_m'])
        if operation.get('mode')!='dependency' or operation.get('dependency_patch')!=expected:
            raise ValueError('OBSTACLE_APPLY_PATCH_CHANGED')

    def pinned_preview(self,execution_id,digest):
        """Apply the exact host-side numbers; JS JSON round trips are lossy."""
        if not isinstance(execution_id,str) or not re.fullmatch('[a-f0-9]{32}',execution_id):
            raise ValueError('OBSTACLE_PREVIEW_ID_INVALID')
        context=self.review.context();path=self._folder(context)/'proposals'/(execution_id+'.json')
        if any(p.is_symlink() for p in (path,*path.parents)) or path.stat().st_size>4*1024*1024:
            raise ValueError('OBSTACLE_PREVIEW_PROOF_INVALID')
        proof=json.loads(path.read_text(encoding='utf-8'));binding=checked_obstacle_binding(proof['binding'])
        if proof.get('sha256')!=canonical_sha256({k:v for k,v in proof.items() if k!='sha256'}) or binding['preview_sha256']!=digest:
            raise ValueError('OBSTACLE_PREVIEW_PROOF_CHANGED')
        if binding['execution_id']!=execution_id or canonical_sha256(proof['operation'])!=digest:
            raise ValueError('OBSTACLE_PREVIEW_PROOF_CHANGED')
        # The common transaction first returns an exact duplicate's durable
        # result, then validates current evidence/context for a NEW operation.
        # Revalidating here would reject a successful retry after its revision
        # changed and bypass that existing idempotency contract.
        return proof['operation'],digest,binding
