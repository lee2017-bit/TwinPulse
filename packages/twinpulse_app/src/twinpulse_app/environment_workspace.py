# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Project-scoped local environment inspection and explicit adoption."""
import base64
from copy import deepcopy
from collections import OrderedDict
import hashlib
import json
import io
import os
import math
from pathlib import Path
import re
import time
from threading import RLock,Thread
from uuid import uuid4

from twinpulse_core import InputRevision,canonical_sha256
from twinpulse_core.scene_tools import SceneToolCall
from twinpulse_core.site_tools import SiteToolPlan
from twinpulse_core.environment_source import checked_environment,move_environment,object_bounds
from twinpulse_core.environment_overlays import add_overlay,remove_overlay
from twinpulse_core.room_item_catalog import room_item_catalog_version
from twinpulse_core.room_items import room_item_risk
from twinpulse_provider import CancellationToken
from .command_broker import BrokerError
from .library_asset_store import atomic_json
from .library_process import run_finite
from .runtime_paths import resource_root


class EnvironmentWorkspace:
    def __init__(self,workflow,registry=None):
        workflow._application._project_store._check_location()
        self.workflow=workflow;self.root=(workflow._application._project_store.path.parent/'environment-imports').resolve()
        self.lock=RLock();self.job=None;self.thread=None;self.token=None;self.build_command=None;self.build_owner=None
        self.previews=OrderedDict()
        self.registry=registry;self.proposal=None;self.proposal_token=None;self.proposal_thread=None;self.closed=False
        from .environment_photo_review import EnvironmentPhotoReview
        self.photos=EnvironmentPhotoReview(self)

    def active(self):return self.photos.active() or any(t is not None and t.is_alive() for t in (self.thread,self.proposal_thread))

    def shutdown(self):
        self.closed=True
        if self.token:self.token.cancel()
        if self.proposal_token:self.proposal_token.cancel()
        self.photos.shutdown()

    def pinned_environment_operation(self,identity,digest,session_id,*,claim=False):
        # The renderer returns only this review identity. Mesh coordinates and
        # their exact JSON number representation never round-trip through JS.
        # Transaction.start still owns duplicate/current-revision admission.
        with self.workflow._lock,self.lock:
            item=self.previews.get(identity) if isinstance(identity,str) else None
            if (item is None or item['owner']!=session_id or not isinstance(digest,str) or
                    item['preview']['preview_digest']!=digest or
                    canonical_sha256(item['preview']['operation'])!=digest):
                raise BrokerError('environment_preview_unavailable','Review this space edit again before Apply.',status=409)
            if item.get('_proposal_job'):
                self._proposal_current(self.proposal,self.proposal_token,session_id)
                if self.proposal['job_id']!=item['_proposal_job'] or self.proposal['status']!='ready':
                    raise BrokerError('environment_preview_unavailable','Review a current suggestion before Apply.',status=409)
                if claim:self.proposal['_apply_admitted']=True
            call=item['preview']['operation'].get('tool_call')
            if call and call.get('tool')=='import_environment':
                self._verify_overlay_photos(call['arguments']['environment'])
            if item.get('_photo_reference'):self.photos.verify_preview(item['_photo_reference'],item['preview'],claim=claim)
            return deepcopy(item['preview']['operation']),digest

    def snapshot(self,session_id=None,**extra):
        operation=None
        if self.build_command and session_id==self.build_owner:
            operation=next((op for op in self.workflow._broker.public_state(session_id)['operations']
                if op['command_id']==self.build_command),None)
        # Display the already published review, not a disk replay on every poll.
        # All actions still validate saved data at their admission/commit boundary.
        # Lock order is workflow -> environment, including duplicate Inspect.
        with self.workflow._lock,self.lock:
            job=deepcopy(self.job);source=self.workflow._application.site_draft
            environment=source.site.scene.environment if source is not None else None
            revision=None;review_error=None
            if environment is not None:
                try:environment,revision=self._current_review(source)
                except BrokerError as error:
                    environment=None;review_error=str(error)
            if environment is None and job and job.get('environment') is not None:environment=job['environment']
            objects=[];floor_triangles=[]
            if environment:
                for m in environment['meshes']:
                    lo,hi=object_bounds(m)
                    objects.append(dict(id=m['id'],label=m['label'],category=m['category'],
                        position_m=[(a+b)/2 for a,b in zip(lo,hi)],
                        dimensions_m=[b-a for a,b in zip(lo,hi)]))
                    if m['category']=='floor':
                        floor_triangles.extend([[[m['points_m'][i][axis]+m['translation_m'][axis] for axis in (0,1)] for i in t]
                            for t in m['triangles'] if all(abs(m['points_m'][i][2]+m['translation_m'][2])<1e-4 for i in t)])
                for overlay in environment.get('overlays',[]):
                    item=overlay['item']
                    objects.append(dict(id=item['id'],label=item['label'],category=item['kind'],
                        position_m=item['position_m'],dimensions_m=item['dimensions_m'],added=True,
                        uncertainty_m=overlay['uncertainty_m'],evidence=overlay['evidence'],risk=room_item_risk(item)))
            return dict(project_id=self.workflow._broker.project_id,status='failed' if review_error else 'imported' if revision else
                job['status'] if job else 'empty',job_id=job['job_id'] if job else None,
                error=review_error or (job.get('error') if job else None),source_name=environment['source_name'] if environment else None,
                source_sha256=environment['source_sha256'] if environment else None,
                units_basis=environment['units_basis'] if environment else None,objects=objects,floor_triangles_xy=floor_triangles,
                scene_revision=revision,metadata_basis='current_review_not_disk_validation' if revision else None,
                photo_proposal=self.photos.snapshot(environment),
                **({'proposal':{k:deepcopy(v) for k,v in self.proposal.items() if not k.startswith('_')}} if self.proposal and session_id==self.proposal.get('_owner') else {}),
                **({'operation':operation} if operation else {}),**extra)

    def _current_review(self,source):
        """Caller holds workflow lock. This is metadata, never Build permission."""
        workflow=self.workflow;artifact=workflow._site_artifact;history=workflow._scene_changes
        environment=artifact.scene.environment if artifact is not None else None
        if (workflow._phase!='draft_ready' or workflow._derived_revision is not None or workflow._input is None
                or source is None or source.site.scene.environment is None or environment is None or history is None
                or source.input_revision.digest!=workflow._input.revision
                or artifact.scene.source_ref!=workflow._input.revision
                or history.project_id!=workflow._broker.project_id or history.input_revision!=workflow._input.revision
                or history.current_scene_revision!=artifact.revision
                or environment['source_sha256']!=source.site.scene.environment['source_sha256']):
            raise BrokerError('environment_review_unavailable','Reopen the saved space for current review.',status=409)
        return environment,artifact.revision

    def _validate_saved_build(self,source):
        """Explicit Build only: fresh original, input archive and edit journal."""
        _,revision=self._current_review(source)
        app=self.workflow._application
        try:
            project=app._project_store.load()
            if (project is None or project.project_id!=self.workflow._broker.project_id or project.site_draft!=source
                    or project.latest_input is None or project.latest_input.digest!=source.input_revision.digest):
                raise ValueError('ENVIRONMENT_SAVED_PROJECT_CHANGED')
            prepared=app.restored_saved_input()
            history=app.scene_change_store().load()
            _,site=history.replay(source)
            self._verify_overlay_photos(site.scene.environment)
            if (prepared.revision.digest!=source.input_revision.digest or history!=self.workflow._scene_changes
                    or site.scene.revision!=revision):raise ValueError('ENVIRONMENT_SAVED_REVIEW_CHANGED')
        except (OSError,UnicodeError,ValueError) as error:
            raise BrokerError('environment_saved_review_changed',
                'Saved space changed or failed validation. Reopen it before Build.',status=409) from error

    def action(self,body,session_id):
        action=body.get('action');request=body.get('request_id')
        if not isinstance(request,str) or not re.fullmatch('[A-Za-z0-9:_-]{1,100}',request):
            raise ValueError('ENVIRONMENT_REQUEST_ID_INVALID')
        if action=='model_cancel':
            if set(body)!={'action','request_id','job_id'}:raise ValueError('ENVIRONMENT_CANCEL_SHAPE')
            with self.lock:
                if not self.proposal or self.proposal['_owner']!=session_id or self.proposal['job_id']!=body['job_id']:
                    raise ValueError('ENVIRONMENT_PROPOSAL_OWNER_CHANGED')
                if self.proposal.get('_apply_admitted'):
                    raise BrokerError('environment_apply_admitted','Apply was already admitted. Check its transaction status; cancellation cannot retract it.',status=409)
                if self.proposal_token:self.proposal_token.cancel()
                self.proposal.update(status='cancelled',error='Cancelled. Nothing was applied.')
                for key in list(self.previews):
                    if self.previews[key].get('_proposal_job')==body['job_id']:self.previews.pop(key)
                self.proposal.pop('preview',None)
            return self.snapshot(session_id)
        if action=='inspect':
            if set(body)!={'action','request_id','attachment','units'}:raise ValueError('ENVIRONMENT_INSPECT_SHAPE')
            file=body['attachment']
            if not isinstance(file,dict) or set(file)!={'name','bytes_base64'}:raise ValueError('ENVIRONMENT_ATTACHMENT_INVALID')
            name=file['name']
            if (not isinstance(name,str) or Path(name).name!=name or any(c in name for c in '/\\\0&|<>^%\r\n') or
                    not 1<=len(name)<=180 or Path(name).suffix.lower() not in {'.usd','.usda','.usdc'}):
                raise ValueError('ENVIRONMENT_SOURCE_NAME_INVALID')
            if body['units'] not in {None,'m','cm','mm'}:raise ValueError('ENVIRONMENT_UNITS_INVALID')
            if not isinstance(file['bytes_base64'],str) or len(file['bytes_base64'])>14000000:raise ValueError('ENVIRONMENT_FILE_LIMIT')
            raw=base64.b64decode(file['bytes_base64'],validate=True)
            if not raw or len(raw)>10*1024*1024:raise ValueError('ENVIRONMENT_FILE_LIMIT')
            with self.lock:
                if self.active():raise ValueError('ENVIRONMENT_INSPECTION_BUSY')
                if not self.job or self.job['request_id']!=request:
                    folder=self.root/uuid4().hex;folder.mkdir(parents=True)
                    source=folder/name
                    with source.open('xb') as stream:stream.write(raw)
                    self.job=dict(job_id=folder.name,request_id=request,status='inspecting',source_sha256=hashlib.sha256(raw).hexdigest(),
                        error=None,source_name=name,environment=None)
                    trace=self.workflow._application.diagnostics.begin('environment_inspection',component='app',
                        request_id=request,operation_id=folder.name)
                    self.job['execution_id']=trace.execution_id
                    atomic_json(folder/'job.json',self.job);self.token=CancellationToken()
                    self.thread=Thread(target=self._inspect,args=(folder,source,body['units'],self.job,self.token,trace),daemon=True,
                        name='environment-inspection')
                    self.thread.start()
            return self.snapshot()
        with self.workflow._lock:
            if self.workflow._workers or self.workflow._broker.has_pending_operations():raise ValueError('ENVIRONMENT_WORKFLOW_BUSY')
            if action=='adopt':
                if set(body)!={'action','request_id','job_id'}:raise ValueError('ENVIRONMENT_ADOPT_SHAPE')
                with self.lock:
                    job=self.job
                    if not job or job['status']!='ready' or job['job_id']!=body['job_id']:raise ValueError('ENVIRONMENT_REVIEW_REQUIRED')
                    environment=checked_environment(job['environment'])
                    path=self.root/job['job_id']/job['source_name']
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=environment['source_sha256']:
                        raise ValueError('ENVIRONMENT_SOURCE_CHANGED')
                revision=InputRevision.create(prompt='Import local space '+environment['source_name']+' SHA256 '+environment['source_sha256']+
                    '; units '+str(environment['meters_per_unit'])+' '+environment['units_basis'],images=(),
                    measurement_constraints=(),profile_id=self.workflow._profile_id,generation_settings={'request_schema':'environment-static-1.0'})
                plan=SiteToolPlan('ImportedSpace','Imported static space; dimensions and real alignment require review',
                    'Local USD geometry, not photo reconstruction',
                    (SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)),),plan_version='2.4')
                draft=self.workflow._application.import_environment(plan,revision,request,path.read_bytes())
                workflow=self.workflow.resume_saved_scene(self.workflow._broker.project_id,draft.site.scene.revision,revision.digest)
                return self.snapshot(workflow=workflow)
            source=self.workflow._application.site_draft
            if source is None or source.site.scene.environment is None:raise ValueError('ENVIRONMENT_IMPORT_REQUIRED')
            if self.workflow._phase!='draft_ready':
                self.workflow.resume_saved_scene(self.workflow._broker.project_id,source.site.scene.revision,source.input_revision.digest)
            if action in {'photo_analyze','photo_cancel'}:
                with self.lock:return self.photos.action(body,session_id)
            if action=='model_move_preview':
                if set(body)!={'action','request_id','object_id','text','expected_scene_revision'}:raise ValueError('ENVIRONMENT_MODEL_SHAPE')
                env,revision=self._current_review(source)
                if revision!=body['expected_scene_revision']:raise ValueError('ENVIRONMENT_SCENE_CHANGED')
                selected=next((m for m in env['meshes'] if m['id']==body['object_id']),None)
                added=next((o['item'] for o in env.get('overlays',[]) if o['item']['id']==body['object_id']),None)
                from twinpulse_core.environment_source import MOVABLE
                if added:selected=dict(id=added['id'])
                elif selected is None or selected['category'] not in MOVABLE:raise ValueError('ENVIRONMENT_OBJECT_READ_ONLY')
                if not isinstance(body['text'],str) or not 1<=len(body['text'].strip())<=1000:raise ValueError('ENVIRONMENT_MODEL_TEXT_REQUIRED')
                if self.registry is None:raise ValueError('ENVIRONMENT_CONFIGURED_MODEL_REQUIRED')
                with self.lock:
                    if self.closed or self.photos.active() or self.proposal_thread is not None and self.proposal_thread.is_alive():raise ValueError('ENVIRONMENT_MODEL_BUSY')
                    job=dict(job_id=uuid4().hex,request_id=request,status='running',source_revision=revision,
                        model_id=None,error=None,_owner=session_id,_project=self.workflow._broker.project_id,
                        _source_sha256=env['source_sha256'],_input=source.input_revision.digest,
                        _object_id=selected['id'],_text=body['text'])
                    self.proposal=job;self.proposal_token=CancellationToken()
                    self.proposal_thread=Thread(target=self._model_move,args=(job,self.proposal_token),daemon=True,name='environment-model-move')
                    self.proposal_thread.start()
                return self.snapshot(session_id)
            if action=='model_review':
                if set(body)!={'action','request_id','job_id','expected_scene_revision'}:raise ValueError('ENVIRONMENT_MODEL_REVIEW_SHAPE')
                with self.lock:
                    job=self.proposal;self._proposal_current(job,self.proposal_token,session_id)
                    if job.get('_apply_admitted'):raise ValueError('ENVIRONMENT_APPLY_ALREADY_ADMITTED')
                    if job['job_id']!=body['job_id'] or job['status']!='ready' or body['expected_scene_revision']!=job['source_revision']:
                        raise ValueError('ENVIRONMENT_PROPOSAL_NOT_READY')
                    suggestion=deepcopy(job.get('suggestion'))
                if not suggestion:raise ValueError('ENVIRONMENT_PROPOSAL_NOT_READY')
                with self.lock:
                    self._proposal_current(job,self.proposal_token,session_id)
                    # Cancel cannot interleave between creating and tagging the
                    # server-pinned review capability. Both locks are reentrant.
                    reply=self.action(dict(action='move_preview',request_id='model_'+job['job_id'],object_id=job['_object_id'],
                        translation_m=suggestion['translation_m'],expected_scene_revision=job['source_revision']),session_id)
                    job['preview']=deepcopy(reply['preview'])
                    key='environment_edit_'+hashlib.sha256(('model_'+job['job_id']).encode('utf-8')).hexdigest()[:32]
                    self.previews[key]['_proposal_job']=job['job_id']
                return self.snapshot(session_id,preview=reply['preview'])
            if action=='build':
                if set(body)!={'action','request_id'}:raise ValueError('ENVIRONMENT_BUILD_SHAPE')
                artifact=self.workflow._site_artifact
                broker=self.workflow._broker
                # Full cold-history replay and photo hashing may exceed the
                # three-second engine-control lease. Validate the unchanged
                # saved review while holding the workflow lock BEFORE asking
                # for that lease. Never relax expiry or bypass permission.
                self._validate_saved_build(source)
                self.workflow.acknowledge(artifact.revision)
                identity=broker.supervisor_state()
                lease=broker.acquire_lease(session_id)
                deadline=time.monotonic()+6.
                # The idle adapter advertises Build only after observing this
                # lease in its next exchange. Capability is not permission.
                while not broker.site_scene_capable():
                    current=broker.supervisor_state()
                    if (not current['engine_connected'] or
                            (current['engine_session_id'],current['stage_epoch'])!=
                            (identity['engine_session_id'],identity['stage_epoch'])):
                        raise BrokerError('environment_engine_changed','Isaac changed before Build; inspect the current scene.',status=409)
                    if time.monotonic()>=deadline:
                        raise BrokerError('environment_build_permit_timeout','Isaac did not permit Build; no command was sent.',status=409)
                    broker.renew_lease(session_id,lease['control_lease_id'])
                    time.sleep(.05)
                self.workflow.assert_site_build_allowed(artifact.artifact_id,artifact.revision)
                operation=self.workflow._broker.submit(session_id,dict(client_request_id=request,command_type='build_site_scene',
                    artifact_id=artifact.artifact_id,expected_applied_revision=artifact.revision))
                self.build_command=operation['command_id'];self.build_owner=session_id
                return self.snapshot(workflow=self.workflow.snapshot(),operation=operation)
            if action=='lidar_route_preview':
                # Server-side only (route-candidate card): unknown obstacles from the
                # declared-route LiDAR record, bound to that record's SHA-256.
                if set(body)!={'action','request_id','obstacles','evidence'}:raise ValueError('ENVIRONMENT_EDIT_SHAPE')
                history=self.workflow._application.scene_change_store().load();plan,site=history.replay(source)
                environment=site.scene.environment;evidence=dict(basis='lidar_estimate',alignment_verified=False,
                    source_name=body['evidence']['source_name'],sha256=body['evidence']['sha256'])
                for index,obstacle in enumerate(body['obstacles'][:8]):
                    xy=obstacle['position_xy_m'];size=obstacle['dimensions_m']
                    identity='Added_'+hashlib.sha256((request+':%d'%index).encode('utf-8')).hexdigest()[:20]
                    item=dict(id=identity,kind='unknown',label=obstacle['label'],catalog_version=room_item_catalog_version('unknown'),
                        position_m=[*xy,size[2]/2],dimensions_m=size,yaw_deg=0.,observation_time_utc=None)
                    environment=add_overlay(environment,dict(item=item,uncertainty_m=obstacle['uncertainty_m'],evidence=dict(evidence)))
                call=SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)).to_dict()
                operation_id='environment_edit_'+hashlib.sha256(request.encode('utf-8')).hexdigest()[:32]
                preview=self.workflow.preview_scene_edit(operation_id=operation_id,mode='change',target_call_id='imported_space',tool_call=call)
                with self.lock:
                    self.previews[operation_id]=dict(owner=session_id,preview=deepcopy(preview))
                    while len(self.previews)>8:self.previews.popitem(last=False)
                return self.snapshot(preview=preview)
            if action in {'move_preview','undo_preview','add_overlay_preview','remove_overlay_preview','photo_candidate_preview'}:
                expected={'action','request_id','expected_scene_revision'}|(
                    {'object_id','translation_m'} if action=='move_preview' else
                    {'obstacle','photo'} if action=='add_overlay_preview' else
                    {'obstacle','candidate_ref','duplicate_reviewed'} if action=='photo_candidate_preview' else
                    {'object_id'} if action=='remove_overlay_preview' else set())
                if set(body)!=expected:raise ValueError('ENVIRONMENT_EDIT_SHAPE')
                history=self.workflow._application.scene_change_store().load();plan,site=history.replay(source)
                if body['expected_scene_revision']!=site.scene.revision:raise ValueError('ENVIRONMENT_SCENE_CHANGED')
                call=None;photo_reference=None;original_environment=site.scene.environment
                if action=='move_preview':
                    environment=move_environment(site.scene.environment,body['object_id'],body['translation_m'])
                    call=SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)).to_dict()
                elif action in {'add_overlay_preview','photo_candidate_preview'}:
                    obstacle=body['obstacle']
                    if not isinstance(obstacle,dict) or set(obstacle)!={'kind','label','position_xy_m','dimensions_m','yaw_deg','uncertainty_m'}:
                        raise ValueError('ENVIRONMENT_OBSTACLE_SHAPE')
                    xy=obstacle['position_xy_m'];size=obstacle['dimensions_m']
                    if (not isinstance(xy,list) or len(xy)!=2 or not isinstance(size,list) or len(size)!=3 or
                            any(type(n) not in (int,float) or not math.isfinite(n) for n in xy+size) or
                            not isinstance(obstacle['kind'],str)):
                        raise ValueError('ENVIRONMENT_OBSTACLE_COORDINATES')
                    identity='Added_'+hashlib.sha256(request.encode('utf-8')).hexdigest()[:20]
                    item=dict(id=identity,kind=obstacle['kind'],label=obstacle['label'],
                        catalog_version=room_item_catalog_version(obstacle['kind']),position_m=[*xy,size[2]/2],
                        dimensions_m=size,yaw_deg=obstacle['yaw_deg'],observation_time_utc=None)
                    # Validate numeric/catalog/footprint before accepting/storing
                    # the optional image. A local estimate is not measured pose.
                    overlay=dict(item=item,uncertainty_m=obstacle['uncertainty_m'],evidence=dict(
                        basis='manual_estimate',source_name=None,sha256=None,alignment_verified=False))
                    environment=add_overlay(site.scene.environment,overlay)
                    if action=='photo_candidate_preview':
                        if body['duplicate_reviewed'] is not True:raise ValueError('PHOTO_DUPLICATE_REVIEW_REQUIRED')
                        job,candidate=self.photos.reference(body['candidate_ref'],original_environment)
                        if candidate['kind']!=item['kind']:raise ValueError('PHOTO_CANDIDATE_KIND_CHANGED')
                        overlay['evidence']=job['photo'];environment=add_overlay(original_environment,overlay)
                        photo_reference=body['candidate_ref']
                    elif body['photo'] is not None:
                        overlay['evidence']=self._store_overlay_photo(body['photo'])
                        environment=add_overlay(site.scene.environment,overlay)
                    call=SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)).to_dict()
                elif action=='remove_overlay_preview':
                    environment=remove_overlay(site.scene.environment,body['object_id'])
                    call=SceneToolCall('imported_space','import_environment',dict(id='imported_space',environment=environment)).to_dict()
                # HTTP request IDs may be UUIDs beginning with a digit. The
                # existing journal requires a letter-led bounded operation ID.
                operation_id='environment_edit_'+hashlib.sha256(request.encode('utf-8')).hexdigest()[:32]
                preview=self.workflow.preview_scene_edit(operation_id=operation_id,mode='change' if call else 'undo',
                    target_call_id='imported_space' if call else None,tool_call=call)
                with self.lock:
                    reference=self.photos.record_preview(photo_reference,preview,identity,original_environment) if photo_reference else None
                    self.previews[operation_id]=dict(owner=session_id,preview=deepcopy(preview))
                    if reference:self.previews[operation_id]['_photo_reference']=reference
                    while len(self.previews)>8:self.previews.popitem(last=False)
                return self.snapshot(preview=preview)
            raise ValueError('ENVIRONMENT_ACTION_UNSUPPORTED')

    def _store_overlay_photo(self,file):
        """Immutable local evidence only. No model request, EXIF pose or upload."""
        if not isinstance(file,dict) or set(file)!={'name','bytes_base64'}:raise ValueError('ENVIRONMENT_PHOTO_SHAPE')
        name=file['name'];encoded=file['bytes_base64']
        if (not isinstance(name,str) or not 1<=len(name)<=180 or any(c in name for c in '/\\\0\r\n') or
                Path(name).suffix.lower() not in {'.jpg','.jpeg','.png','.webp'} or
                not isinstance(encoded,str) or len(encoded)>7_000_000):raise ValueError('ENVIRONMENT_PHOTO_INVALID')
        raw=base64.b64decode(encoded,validate=True)
        if not raw or len(raw)>5*1024*1024:raise ValueError('ENVIRONMENT_PHOTO_LIMIT')
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {'JPEG','PNG','WEBP'} or max(image.size)>8000 or image.width*image.height>24_000_000:
                raise ValueError('ENVIRONMENT_PHOTO_DIMENSIONS')
            image.verify()
        sha=hashlib.sha256(raw).hexdigest();folder=self.root/'overlay-photos'/sha
        folder.mkdir(parents=True,exist_ok=True);path=folder/'source.image'
        if any(p.is_symlink() for p in (path,folder,folder.parent,self.root)):raise ValueError('ENVIRONMENT_PHOTO_STORAGE_INVALID')
        if not path.exists():
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('ENVIRONMENT_PHOTO_CHANGED')
        return dict(basis='photo_estimate',source_name=name,sha256=sha,alignment_verified=False)

    def _verify_overlay_photos(self,environment):
        from .environment_evidence import verify_overlay_photos
        verify_overlay_photos(self.root,environment)

    def _proposal_current(self,job,token,owner):
        if (not job or self.closed or token is None or token.is_cancelled or self.proposal is not job
                or job['_owner']!=owner or self.workflow._broker.project_id!=job['_project']):
            raise ValueError('ENVIRONMENT_PROPOSAL_CANCELLED_OR_CHANGED')
        source=self.workflow._application.site_draft
        env,revision=self._current_review(source)
        if (revision!=job['source_revision'] or env['source_sha256']!=job['_source_sha256']
                or source.input_revision.digest!=job['_input']):raise ValueError('ENVIRONMENT_PROPOSAL_SCENE_CHANGED')

    def _model_move(self,job,token):
        folder=self.root/'model-proposals'/job['job_id']
        provider=None;trace=None;suggestion=None;primary=None;storage_errors=[]
        try:
            import asyncio
            from dataclasses import replace
            from .stage_routing import build_configured_stage_service,StageRoutingSettings
            from .product_inference import ProductInferenceScope
            from twinpulse_provider import GenerationRequest
            from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
            from twinpulse_provider.generation_store import input_digest
            from twinpulse_provider.environment_move import generate_environment_move,VERSION
            folder.mkdir(parents=True)
            trace=self.workflow._application.diagnostics.begin('environment_model_move',request_id=job['request_id'],
                operation_id=job['job_id'],scene_edit_revision=job['source_revision'])
            with self.workflow._lock,self.lock:self._proposal_current(job,token,job['_owner'])
            service=build_configured_stage_service(self.registry)
            if service is None or not isinstance(service._provider,BudgetedPipeline):raise ValueError('ENVIRONMENT_BUDGETED_ROUTE_REQUIRED')
            provider=service._provider;route=StageRoutingSettings(self.registry).load()
            request=GenerationRequest(job['request_id'],json.dumps(dict(object_id=job['_object_id'],text=job['_text']),
                ensure_ascii=False,separators=(',',':')),schema_version=VERSION,diagnostics=trace)
            state_root=self.workflow.model_recipe_store.root.parent
            scope=ProductInferenceScope('ordinary-generation:'+uuid4().hex,input_digest(request),canonical_sha256(route),
                provider.policy.sha256,state_root/'ordinary-generation'/(uuid4().hex+'.ledger.json'),job['_project'])
            request=replace(request,inference_scope=scope)
            atomic_json(folder/'request.json',dict(project_id=job['_project'],source_sha256=job['_source_sha256'],
                scene_revision=job['source_revision'],request_id=request.request_id,prompt=json.loads(request.prompt),
                images_sent=0,mesh_sent=False,model_id=provider.planner_model_id))
            with self.workflow._lock,self.lock:
                self._proposal_current(job,token,job['_owner']);job['model_id']=provider.planner_model_id
            value=asyncio.run(generate_environment_move(provider,request,token,service._config))
            atomic_json(folder/'result.json',value)
            with self.workflow._lock,self.lock:
                self._proposal_current(job,token,job['_owner'])
                if value['mode']!='move':raise ValueError('Clarification required: '+value['explanation'])
                suggestion=dict(translation_m=value['translation_m'],explanation=value['explanation'])
        except Exception as error:
            primary=error
        finally:
            # Independent diagnostic failures must not hide the original error
            # or publish an incomplete success. No ready state before persistence.
            if provider is not None:
                try:atomic_json(folder/'provider-diagnostic.json',provider.diagnostic_for(job['request_id']))
                except Exception as error:storage_errors.append(str(error)[:300])
            with self.workflow._lock,self.lock:
                try:self._proposal_current(job,token,job['_owner'])
                except Exception as error:
                    if primary is None:primary=error
                candidate={k:deepcopy(v) for k,v in job.items() if k not in {'preview','suggestion'}}
                failed=primary is not None or bool(storage_errors)
                candidate.update(status='cancelled' if token.is_cancelled else 'failed' if failed else 'ready',
                    error=str(primary)[:700] if primary is not None else 'Diagnostic storage failed.' if storage_errors else None)
                if not failed and not token.is_cancelled:candidate['suggestion']=suggestion
                if storage_errors:candidate['diagnostic_storage_errors']=storage_errors
                # _owner is the live authenticated cookie, not provenance.
                # It stays only in memory and must never enter saved evidence.
                saved={k:v for k,v in candidate.items() if k!='_owner'}
                try:atomic_json(folder/'job.json',saved)
                except Exception as error:
                    storage_errors.append(str(error)[:300]);candidate.update(status='failed',
                        error=candidate['error'] or 'Diagnostic storage failed.',diagnostic_storage_errors=storage_errors)
                    candidate.pop('suggestion',None)
                if trace is not None:
                    try:
                        trace.finish('succeeded' if candidate['status']=='ready' else candidate['status'],error=primary)
                        diagnostics=self.workflow._application.diagnostics
                        if not diagnostics.flush(timeout=2.) or diagnostics.health['diagnostics_degraded']:
                            raise OSError('ENVIRONMENT_DIAGNOSTIC_STORAGE_INCOMPLETE')
                    except Exception as error:
                        storage_errors.append(str(error)[:300]);candidate.update(status='failed',
                            error=candidate['error'] or 'Diagnostic storage failed.',diagnostic_storage_errors=storage_errors)
                        candidate.pop('suggestion',None)
                if storage_errors:
                    try:atomic_json(folder/'job.json',{k:v for k,v in candidate.items() if k!='_owner'})
                    except Exception:pass  # Sticky in-memory failure still exposed.
                if self.proposal is job:job.clear();job.update(candidate)

    def _inspect(self,folder,source,unit,job,token,trace):
        try:
            from .desktop_settings import read_settings
            import os
            runtime=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'TwinPulse'/'runtime'
            python=Path(read_settings(runtime).get('isaac_root',r'C:\isaacsim'))/'python.bat'
            output=folder/'inspection.json'
            # The verified installation is immutable. Peer-module imports must
            # never create an unmanifested __pycache__ beside packaged scripts.
            command=[str(python),'-B',str(resource_root()/'scripts'/'twinpulse_environment_worker.py'),'--input',str(source),'--output',str(output)]
            if unit:command+=['--units',unit]
            if any(any(c in p for c in '&|<>^%\n\r') for p in command):raise ValueError('ENVIRONMENT_WORKER_PATH_INVALID')
            run_finite(command,folder,token,timeout=90)
            if not output.is_file() or output.stat().st_size>2*1024*1024:raise ValueError('ENVIRONMENT_RESULT_MISSING_OR_LARGE')
            environment=checked_environment(json.loads(output.read_text(encoding='utf-8')))
            if environment['source_sha256']!=job['source_sha256']:raise ValueError('ENVIRONMENT_SOURCE_MISMATCH')
            with self.lock:job.update(status='ready',environment=environment);atomic_json(folder/'job.json',job)
            trace.finish('succeeded')
        except Exception as error:
            with self.lock:
                job.update(status='failed',error=str(error)[-500:]);atomic_json(folder/'job.json',job)
            trace.finish('failed')
