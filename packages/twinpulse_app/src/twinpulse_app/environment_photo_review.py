# SPDX-License-Identifier: Apache-2.0
"""Project-owned photo candidate job and immutable adoption receipts.

This derived observation sidecar does not change the saved geometry contract.
Candidates confer no metric placement, scene edit or physical authority.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from threading import Thread
from uuid import uuid4
import re

from twinpulse_core import canonical_sha256
from twinpulse_core.environment_photo import VERSION,CATALOG_SIZES,PHOTO_KINDS,checked_photo_candidates,overlay_kind_for,photo_context,possible_duplicates
from twinpulse_provider import CancellationToken,GenerationRequest,ImageInput
from twinpulse_provider.environment_photo import generate_environment_photo
from .library_asset_store import atomic_json
from .single_photo_scope import SinglePhotoScope


PHOTO_CANDIDATE_OUTPUT_TOKENS=16000  # per photo-candidate call, reasoning tokens included; the route cap still bounds it

class EnvironmentPhotoReview:
    def __init__(self,parent):
        self.parent=parent;self.root=parent.root/'photo-proposals';self.job=None;self.thread=None;self.token=None;self.owner=None
        self.apply_admitted=set();self.revoked=set()
        self.load_error=None;self._receipts=None
        try:
            pointer=self.root/'latest.json'
            if pointer.exists():
                value=self._read(pointer);self.job=self._read_job(value['job_id'])
                if self.job['status']=='running':self.job.update(status='failed',error='Interrupted photo request; outcome may be unknown. No automatic retry.')
        except (OSError,ValueError,KeyError,TypeError):self.load_error='Saved photo proposal could not be verified. No automatic retry.'

    def active(self):return self.thread is not None and self.thread.is_alive()
    def shutdown(self):
        if self.token:self.token.cancel()

    def _read(self,path):
        if any(p.is_symlink() for p in (path,path.parent,self.root,self.root.parent)) or path.stat().st_size>256*1024:
            raise ValueError('PHOTO_PROPOSAL_STORAGE_INVALID')
        return json.loads(path.read_text(encoding='utf-8'))

    def _save_job(self,job):
        body=deepcopy(job);body['record_sha256']=canonical_sha256(body)
        atomic_json(self.root/job['job_id']/'job.json',body)

    def _read_job(self,identity):
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('PHOTO_PROPOSAL_ID_INVALID')
        value=self._read(self.root/identity/'job.json')
        fields={'job_id','request_id','status','error','project_id','input_revision','source_sha256','source_revision',
            'photo','model_id','candidates','explanation','response_sha256','record_sha256'}
        if not isinstance(value,dict) or set(value)!=fields:raise ValueError('PHOTO_PROPOSAL_RECORD_INVALID')
        digest=value.pop('record_sha256')
        if canonical_sha256(value)!=digest or value.get('job_id')!=identity:raise ValueError('PHOTO_PROPOSAL_CHANGED')
        if value.get('status') not in {'running','ready','failed','cancelled'}:raise ValueError('PHOTO_PROPOSAL_STATUS_INVALID')
        if value['status']=='ready':
            path=self.root/identity/'result.json';self._read(path)
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=value['response_sha256']:raise ValueError('PHOTO_PROPOSAL_RESPONSE_CHANGED')
            checked=checked_photo_candidates(json.loads(raw))
            if checked['candidates']!=value['candidates'] or checked['explanation']!=value['explanation']:raise ValueError('PHOTO_PROPOSAL_CHANGED')
        return value

    def _current(self,job,*,same_revision=False):
        parent=self.parent;workflow=parent.workflow
        if parent.closed or workflow._broker.project_id!=job['project_id']:raise ValueError('PHOTO_PROPOSAL_PROJECT_CHANGED')
        source=workflow._application.site_draft;environment,revision=parent._current_review(source)
        if (environment['source_sha256']!=job['source_sha256'] or source.input_revision.digest!=job['input_revision'] or
                same_revision and revision!=job['source_revision']):raise ValueError('PHOTO_PROPOSAL_SCENE_CHANGED')
        return environment,revision

    def snapshot(self,environment):
        if self.load_error:return dict(status='failed',error=self.load_error,candidates=[])
        if self.job is None:return None
        job=self.job
        if not environment or job['project_id']!=self.parent.workflow._broker.project_id or job['source_sha256']!=environment['source_sha256']:return None
        receipts=self.adopted_kinds(environment) if job['candidates'] else {}
        return {**deepcopy(job),'candidates':[{**deepcopy(c),'dimensions_m':list(CATALOG_SIZES[c['kind']]),
            'dimensions_basis':'catalog_estimate','overlay_kind':overlay_kind_for(c['kind']),'addable':overlay_kind_for(c['kind']) is not None,
            'possible_duplicates':possible_duplicates(c['kind'],environment,receipts),'duplicate_check_required':True} for c in job['candidates']]}

    def adopted_kinds(self,environment):
        """{overlay_id: recognised kind} of photo boxes from their adoption receipts. A name hint only, never identity."""
        if self._receipts is None:
            rows=[]
            for path in sorted(self.root.glob('*/adoptions/*.json'))[:1024] if self.root.exists() else ():
                if path.parent.parent.is_symlink() or not re.fullmatch('[a-f0-9]{32}',path.parent.parent.name):continue
                try:
                    receipt=self._read(path);kind=receipt['candidate']['kind']
                    if (receipt['project_id']==self.parent.workflow._broker.project_id and kind in PHOTO_KINDS and
                            all(isinstance(receipt[k],str) for k in ('overlay_id','photo_sha256'))):
                        rows.append((receipt['overlay_id'],receipt['photo_sha256'],kind))
                except (OSError,ValueError,KeyError,TypeError):continue
            self._receipts=rows
        photos={o['item']['id']:o['evidence']['sha256'] for o in environment.get('overlays',[]) if o['evidence']['basis']=='photo_estimate'}
        return {identity:kind for identity,sha,kind in self._receipts if photos.get(identity)==sha}

    def action(self,body,owner):
        action=body['action'];parent=self.parent;workflow=parent.workflow
        if action=='photo_cancel':
            if set(body)!={'action','request_id','job_id'}:raise ValueError('PHOTO_CANCEL_SHAPE')
            if self.job is None or self.owner!=owner or body['job_id']!=self.job['job_id']:raise ValueError('PHOTO_PROPOSAL_OWNER_CHANGED')
            if self.job['job_id'] in self.apply_admitted:
                raise ValueError('PHOTO_APPLY_ALREADY_ADMITTED: Check the saved transaction; cancellation cannot retract Apply.')
            self.revoked.add(self.job['job_id'])
            if self.token:self.token.cancel()
            self.job.update(status='cancelled',error='Cancelled. Nothing applied.');self._save_job(self.job)
            return parent.snapshot(owner)
        if action!='photo_analyze' or set(body)!={'action','request_id','photo','expected_scene_revision','consent'}:
            raise ValueError('PHOTO_ANALYZE_SHAPE')
        if body['consent'] is not True:raise ValueError('PHOTO_TRANSMISSION_CONSENT_REQUIRED')
        if parent.active():raise ValueError('ENVIRONMENT_INSPECTION_BUSY')
        source=workflow._application.site_draft;env,revision=parent._current_review(source)
        if revision!=body['expected_scene_revision']:raise ValueError('ENVIRONMENT_SCENE_CHANGED')
        if parent.registry is None:raise ValueError('ENVIRONMENT_CONFIGURED_MODEL_REQUIRED')
        identity=hashlib.sha256(body['request_id'].encode('utf-8')).hexdigest()[:32]
        if (self.root/identity).exists():
            # A repeated delivery must not dispatch again or silently change its
            # attachment/scene after an unknown outcome.
            encoded=body['photo'].get('bytes_base64') if isinstance(body['photo'],dict) else None
            if not isinstance(encoded,str):raise ValueError('PHOTO_REPEATED_REQUEST_CHANGED')
            import base64
            digest=hashlib.sha256(base64.b64decode(encoded,validate=True)).hexdigest()
            existing=self._read_job(identity)
            if (digest!=existing['photo']['sha256'] or body['photo']['name']!=existing['photo']['source_name'] or
                    revision!=existing['source_revision']):raise ValueError('PHOTO_REPEATED_REQUEST_CHANGED')
            if existing['status']=='running':existing.update(status='failed',error='Interrupted request; outcome may be unknown. No automatic retry.')
            self.job=existing
            return parent.snapshot(owner)
        evidence=parent._store_overlay_photo(body['photo']);self._check_photo(evidence)
        job=dict(job_id=identity,request_id=body['request_id'],status='running',error=None,
            project_id=workflow._broker.project_id,input_revision=source.input_revision.digest,source_sha256=env['source_sha256'],
            source_revision=revision,photo=evidence,model_id=None,candidates=[],explanation=None,response_sha256=None)
        self.root.mkdir(parents=True,exist_ok=True);(self.root/job['job_id']).mkdir()
        self._save_job(job);atomic_json(self.root/'latest.json',dict(job_id=job['job_id']))
        self.job=job;self.owner=owner;self.token=CancellationToken();self.load_error=None
        self.thread=Thread(target=self._run,args=(job,self.token),name='environment-photo-proposal',daemon=True);self.thread.start()
        return parent.snapshot(owner)

    def _check_photo(self,evidence):
        self.parent._verify_overlay_photos(dict(overlays=[dict(evidence=evidence)]))
        raw=(self.parent.root/'overlay-photos'/evidence['sha256']/'source.image').read_bytes()
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {'JPEG','PNG'}:raise ValueError('PHOTO_ANALYSIS_USE_JPEG_OR_PNG')
            mime='image/jpeg' if image.format=='JPEG' else 'image/png'
        return raw,mime

    def reference(self,reference,environment):
        if not isinstance(reference,dict) or set(reference)!={'job_id','candidate_id'}:raise ValueError('PHOTO_CANDIDATE_REFERENCE_INVALID')
        if reference['job_id'] in self.revoked:raise ValueError('PHOTO_PROPOSAL_CANCELLED')
        job=self._read_job(reference['job_id']);self._current(job)
        if job['status']!='ready':raise ValueError('PHOTO_PROPOSAL_NOT_READY')
        candidate=next((c for c in job['candidates'] if c['id']==reference['candidate_id']),None)
        if candidate is None:raise ValueError('PHOTO_CANDIDATE_UNKNOWN')
        self._check_photo(job['photo'])
        folder=self.root/job['job_id']/'adoptions'
        active={o['item']['id'] for o in environment.get('overlays',[])}
        if folder.exists():
            paths=list(folder.glob('*.json'))
            if len(paths)>128:raise ValueError('PHOTO_ADOPTION_BUDGET')
            for path in paths:
                receipt=self._read(path)
                if receipt['candidate_id']==candidate['id'] and receipt['overlay_id'] in active:
                    raise ValueError('PHOTO_CANDIDATE_ALREADY_REPRESENTED')
        return job,candidate

    def record_preview(self,reference,preview,overlay_id,environment):
        job,candidate=self.reference(reference,environment)
        value=dict(schema_version='photo-candidate-adoption-1.0',project_id=job['project_id'],job_id=job['job_id'],
            candidate_id=candidate['id'],response_sha256=job['response_sha256'],photo_sha256=job['photo']['sha256'],
            source_sha256=job['source_sha256'],reviewed_scene_revision=preview['parent_revision'],
            operation_id=preview['operation']['operation_id'],preview_digest=preview['preview_digest'],overlay_id=overlay_id,
            model_id=job['model_id'],candidate=candidate,position_basis='user_reviewed_estimate',dimensions_basis='user_reviewed_estimate',
            metric_alignment_verified=False)
        path=self.root/job['job_id']/'adoptions'/(value['operation_id']+'.json')
        if path.exists():
            if self._read(path)!=value:raise ValueError('PHOTO_ADOPTION_CHANGED')
        else:atomic_json(path,value);self._receipts=None
        return dict(job_id=job['job_id'],candidate_id=candidate['id'],receipt_sha256=canonical_sha256(value))

    def verify_preview(self,reference,preview,*,claim=False):
        if reference['job_id'] in self.revoked:raise ValueError('PHOTO_PROPOSAL_CANCELLED')
        job=self._read_job(reference['job_id']);self._current(job)
        path=self.root/job['job_id']/'adoptions'/(preview['operation']['operation_id']+'.json');value=self._read(path)
        if (job['status']!='ready' or canonical_sha256(value)!=reference['receipt_sha256'] or value['preview_digest']!=preview['preview_digest']):
            raise ValueError('PHOTO_ADOPTION_CHANGED')
        self._check_photo(job['photo'])
        if claim:self.apply_admitted.add(job['job_id'])

    def _run(self,job,token):
        parent=self.parent;folder=self.root/job['job_id'];provider=None;trace=None;primary=None;errors=[];value=None
        try:
            from .stage_routing import build_configured_stage_service,StageRoutingSettings
            from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
            from twinpulse_provider.generation_store import input_digest
            with parent.workflow._lock,parent.lock:
                env,_=self._current(job,same_revision=True)
                context=photo_context(env,self.adopted_kinds(env))
            raw,mime=self._check_photo(job['photo'])
            trace=parent.workflow._application.diagnostics.begin('environment_photo_candidates',request_id=job['request_id'],operation_id=job['job_id'])
            service=build_configured_stage_service(parent.registry,evidence_root=folder/'provider-evidence')
            if service is None or not isinstance(service._provider,BudgetedPipeline):raise ValueError('ENVIRONMENT_BUDGETED_ROUTE_REQUIRED')
            provider=service._provider;route=StageRoutingSettings(parent.registry).load()
            # Candidate lists are short, but a photo model with hidden reasoning spends its budget before the answer
            # (Nemotron 3.5 Super VL hit `length` at 4000 with an empty final, 2026-10-26), so allow room for it.
            provider.stage_output_token_caps['observer']=min(PHOTO_CANDIDATE_OUTPUT_TOKENS,provider.stage_output_token_caps['observer'])
            request=GenerationRequest(job['request_id'],json.dumps(context,ensure_ascii=False),
                images=(ImageInput(job['photo']['source_name'],mime,raw),),schema_version=VERSION,diagnostics=trace)
            request=replace(request,inference_scope=SinglePhotoScope('photo-proposal:'+uuid4().hex,input_digest(request),
                canonical_sha256(route),provider.policy.sha256,folder/'usage.ledger.json',job['project_id']))
            atomic_json(folder/'request.json',dict(project_id=job['project_id'],source_revision=job['source_revision'],
                request_id=job['request_id'],photo_sha256=job['photo']['sha256'],images_sent=1,mesh_sent=False,sensor_logs_sent=False,
                scene_names_sent=True,scene_names_count=len(context['existing_props'])+len(context['scanned_objects']),
                prompt=json.loads(request.prompt),model_id=provider.observer_model_id,max_output_tokens=provider.stage_output_token_caps['observer'],
                max_calls=1,automatic_retry=False,consent=True))
            with parent.workflow._lock,parent.lock:
                self._current(job,same_revision=True)
                if token.is_cancelled:raise ValueError('PHOTO_PROPOSAL_CANCELLED')
                job['model_id']=provider.observer_model_id
            value=asyncio.run(generate_environment_photo(provider,request,token,service._config))
            atomic_json(folder/'result.json',value)
            job['response_sha256']=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()
        except Exception as error:primary=error
        finally:
            if provider is not None:
                try:atomic_json(folder/'provider-diagnostic.json',provider.diagnostic_for(job['request_id']))
                except Exception as error:errors.append(str(error)[:200])
            with parent.workflow._lock,parent.lock:
                try:self._current(job,same_revision=True)
                except Exception as error:
                    if primary is None:primary=error
                candidate=deepcopy(job);candidate.update(status='cancelled' if token.is_cancelled else 'failed' if primary or errors else 'ready',
                    error=str(primary)[:600] if primary else 'Diagnostic storage failed.' if errors else None)
                if candidate['status']=='ready':
                    candidate.update(candidates=value['candidates'],explanation=value['explanation'])
                if trace:
                    try:
                        trace.finish('succeeded' if candidate['status']=='ready' else candidate['status'],error=primary)
                        diagnostics=parent.workflow._application.diagnostics
                        if not diagnostics.flush(timeout=2.) or diagnostics.health['diagnostics_degraded']:raise OSError('PHOTO_DIAGNOSTIC_STORAGE_INCOMPLETE')
                    except Exception as error:errors.append(str(error)[:200])
                if errors:
                    candidate.update(status='failed',error=candidate['error'] or 'Diagnostic storage failed.',candidates=[])
                # Ready is the final atomic publication, after all diagnostics
                # are durable. A crash/failed fallback must leave running (cold
                # UNKNOWN) rather than revive an unverified ready result.
                try:self._save_job(candidate)
                except Exception as error:
                    candidate.update(status='failed',error=candidate['error'] or str(error)[:600],candidates=[])
                    try:self._save_job(candidate)
                    except Exception:pass
                if self.job is job:job.clear();job.update(candidate)
