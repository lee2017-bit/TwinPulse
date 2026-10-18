# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Purpose-bound Library jobs. Never apply a scene or run a robot on register."""
import asyncio
import base64
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePath
import re
import shutil
from threading import RLock,Thread
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core.library_assets import MeshAsset,normalize_mesh
from twinpulse_core.model_recipe import recipe_manifest,recipe_digest,recipe_model_id,compiled_parts
from twinpulse_provider import CancellationToken,GenerationRequest,ImageInput
from .command_broker import BrokerError
from .library_asset_store import LibraryAssetStore,atomic_json,store_source
from .library_tools import CSV_SCHEMA,csv_summary,read_obj
from .library_process import call_csv_mcp,run_finite
from .runtime_paths import resource_root
from .library_extension_catalog import definitions,execute

ACTIVE={'queued','running'}
PUBLIC_JOB={'job_id','request_id','project_id','purpose','status','phase','message','tool_id','execution_id',
    'input_sha256','created_at','error','asset_id','asset_version','result'}


class LibraryWorkspace:
    def __init__(self,workflow,registry):
        self.workflow=workflow;self.registry=registry;self.state_root=workflow.model_recipe_store.root.parent
        self.project_id=workflow._broker.project_id
        self.root=self.state_root/'library-workspace'/self.project_id
        self.assets=LibraryAssetStore(self.state_root);self.lock=RLock();self.tokens={};self.threads={}
        self.jobs={};self.closed=False;self.config_path=self.root/'extensions.json'
        self.configuration=json.loads(self.config_path.read_text(encoding='utf-8')) if self.config_path.exists() else {}
        for path in sorted((self.root/'jobs').glob('*/job.json')):
            if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('LIBRARY_JOB_RECORD_INVALID')
            row=json.loads(path.read_text(encoding='utf-8'))
            if row['project_id']!=self.project_id:raise ValueError('LIBRARY_JOB_PROJECT_MISMATCH')
            if row['status'] in ACTIVE:
                row.update(status='unknown',phase='Interrupted',message='Previous process ended before a confirmed result. No automatic retry.',error='LIBRARY_PREVIOUS_OUTCOME_UNKNOWN')
                atomic_json(path,row)
            self.jobs[row['job_id']]=row

    def active(self):
        # Supervisor/state GET must never wait behind a slow optional probe.
        return any(t.is_alive() for t in tuple(self.threads.values()))

    def shutdown(self):
        with self.lock:
            self.closed=True
            for token in self.tokens.values():token.cancel()

    def _folder(self,job):return self.root/'jobs'/job['job_id']
    def _save(self,job):atomic_json(self._folder(job)/'job.json',job)

    def _current_revision(self):
        # Display hint only: never replay a durable history while holding the
        # optional Library lock. Placement/Apply still reload and validate the
        # exact source, history and expected revision in _placement/Tx.
        # Do not acquire workflow._lock here: callers may own self.lock, while
        # placement correctly acquires workflow -> Library in that order.
        workflow=self.workflow
        source=workflow._application.site_draft
        artifact=workflow._site_artifact
        selected=workflow._input
        history=workflow._scene_changes
        if (source is None or artifact is None or selected is None or
                workflow._phase!='draft_ready' or workflow._derived_revision is not None or
                selected.revision!=source.input_revision.digest):return None
        revision=artifact.revision
        if history is not None and (history.project_id!=self.project_id or
                history.input_revision!=source.input_revision.digest or
                history.source_scene_revision!=source.site.scene.revision):return None
        expected=history.current_scene_revision if history is not None else source.site.scene.revision
        if revision!=expected:return None
        if (source is not workflow._application.site_draft or artifact is not workflow._site_artifact or
                selected is not workflow._input or workflow._phase!='draft_ready' or
                history is not workflow._scene_changes or workflow._derived_revision is not None):return None
        return revision

    def _isaac_python(self):
        from .desktop_settings import read_settings
        runtime=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'TwinPulse'/'runtime'
        return Path(read_settings(runtime).get('isaac_root',r'C:\isaacsim'))/'python.bat'

    def extensions(self):
        rows=[]
        for definition in definitions():
            identity=definition['extension_id'];config=self.configuration.get(identity,{})
            rows.append(dict(extension_id=identity,title=definition['title'],transport=definition['transport'],available=True,
                enabled=config.get('enabled',definition['default_enabled']),reason=None,version=definition['version'],
                executable_configurable=False,tools=[{k:v for k,v in t.items() if k!='adapter'} for t in definition['tools']]))
        specs=[
            ('usd_inspector','Static USD inspector','cli',self._isaac_python().is_file(),
                'Needs an existing configured Isaac Python with OpenUSD. Self-contained static triangular meshes only.',False,[]),
            ('cad_converter','NVIDIA CAD converter','cli',False,'Optional usd-convert-cad 0.3.0 program is not configured; no software is installed.',True,[]),
            ('brep','Optional BRep authoring','cli',False,'BRep runtime/finite authoring adapter has not been installed or verified. Built-in recipe creation remains available.',False,[])]
        for identity,title,transport,available,reason,configurable,tools in specs:
            config=self.configuration.get(identity,{})
            if identity=='cad_converter':
                path=Path(config.get('executable',''))
                available=bool(config.get('checked') and path.is_file())
                if available:reason='Local converter verified. Its separate license applies; no Cloud upload.'
            rows.append(dict(extension_id=identity,title=title,transport=transport,available=available,
                enabled=config.get('enabled',identity in {'csv_local','usd_inspector'}),reason=None if available and identity!='cad_converter' else reason,
                version=config.get('version','1.0.0' if identity.startswith('csv_') else None),
                executable_configurable=configurable,tools=[dict(tool_id=i,title=t,input_schema=s,output_kind=o) for i,t,s,o in tools]))
        return rows

    def snapshot(self,**extra):
        with self.lock:
            recipes=[]
            for row in self.workflow.model_recipe_store.records():
                recipe=row['recipe'];manifest=recipe_manifest(recipe)
                recipes.append(dict(asset_id=manifest['model_id'],version=manifest['recipe_sha256'],title=recipe['title'],
                    kind='recipe',source_name='Generated recipe',source_sha256=manifest['recipe_sha256'],
                    dimensions_m=manifest['dimensions_m']['default'],units='m',up_axis='Z',origin=row['origin'],
                    license='Generated output: no blanket license assignment',visual_status=manifest['status'],
                    physics_status='not_validated',reusable=manifest['reusable'],recipe_model_id=manifest['model_id'],
                    preview_parts=compiled_parts(recipe,{p['name']:p['default'] for p in recipe['parameters']})))
            jobs=[dict({k:deepcopy(v) for k,v in row.items() if k in PUBLIC_JOB},can_cancel=row['status'] in ACTIVE,
                can_register=row['status']=='ready' and row['purpose']!='analysis') for row in self.jobs.values()]
            return dict(schema_version='library-workspace-1.0',project_id=self.project_id,
                current_scene_revision=self._current_revision(),assets=recipes+self.assets.catalog(),jobs=jobs,
                extensions=self.extensions(),**extra)

    @staticmethod
    def _request_id(body):
        identity=body.get('request_id')
        if not isinstance(identity,str) or not re.fullmatch('[A-Za-z0-9:_-]{1,100}',identity):raise ValueError('LIBRARY_REQUEST_ID_INVALID')
        return identity

    @staticmethod
    def _attachment(value,role):
        if not isinstance(value,dict) or set(value)!={'name','media_type','bytes_base64','role'} or value['role']!=role:
            raise ValueError('LIBRARY_ATTACHMENT_ROLE_INVALID')
        name=value['name']
        if not isinstance(name,str) or not 1<=len(name)<=240 or PurePath(name).name!=name or any(c in name for c in '/\\\x00'):
            raise ValueError('LIBRARY_FILENAME_INVALID')
        raw=base64.b64decode(value['bytes_base64'],validate=True)
        if not raw or len(raw)>50*1024*1024:raise ValueError('LIBRARY_SOURCE_BYTE_LIMIT')
        return name,raw

    def action(self,body):
        try:return self._action(body)
        except BrokerError:raise
        except (ValueError,TypeError,KeyError,OSError) as error:
            raise BrokerError('library_action_invalid',str(error)[:600],status=409) from error

    def _action(self,body):
        if not isinstance(body,dict) or not isinstance(body.get('action'),str):raise ValueError('LIBRARY_ACTION_INVALID')
        action=body['action']
        fields={'create_recipe':({'action','request_id','prompt'},{'reference'}),
            'import_asset':({'action','request_id','attachment','source','license'},{'source_units','source_up_axis'}),
            'run_tool':({'action','request_id','tool_id','inputs'},{'attachment'}),
            'register_job':({'action','job_id','request_id'},set()),'cancel_job':({'action','job_id'},set()),
            'preview_placement':({'action','asset_id','version','expected_scene_revision','instance_id','position_m','yaw_deg','request_id'},set()),
            'configure_extension':({'action','extension_id','executable','enabled'},set()),
            'check_extension':({'action','extension_id'},set())}
        if action not in fields or not fields[action][0]<=set(body) or set(body)-fields[action][0]-fields[action][1]:
            raise ValueError('LIBRARY_ACTION_FIELDS_INVALID')
        if action=='preview_placement':return self._placement(body)
        if action in {'configure_extension','check_extension'}:return self._extension_action(body)
        with self.lock:
            if action=='cancel_job':
                job=self.jobs[body['job_id']]
                if job['status'] in ACTIVE:
                    self.tokens[job['job_id']].cancel();job.update(status='cancelled',phase='Cancelled',
                        message='Stopped. Late output cannot register an asset or modify a scene. Accounting is retained.')
                    self._save(job)
                return self.snapshot()
            if action=='register_job':
                self._request_id(body);job=self.jobs[body['job_id']]
                if job['status']=='registered':return self.snapshot()
                if job['status']!='ready' or job['purpose']=='analysis':raise ValueError('LIBRARY_VALIDATED_READY_ASSET_REQUIRED')
                payload=json.loads((self._folder(job)/'asset.json').read_text(encoding='utf-8'))
                if payload['kind']=='recipe':
                    manifest=self.workflow.model_recipe_store.register(payload['recipe'],request_id=job['request_id'],model_id=payload['model_id'])
                    identity=manifest['model_id'];version=manifest['recipe_sha256']
                else:
                    asset=self.assets.register(payload['snapshot']);identity=asset.logical_asset_id;version=asset.version
                job.update(status='registered',phase='Registered',message='Immutable Library version registered. Current environment unchanged.',
                    asset_id=identity,asset_version=version);self._save(job);return self.snapshot()
            request_id=self._request_id(body);fingerprint=canonical_sha256(body)
            prior=next((j for j in self.jobs.values() if j['request_id']==request_id),None)
            if prior:
                if prior['fingerprint']!=fingerprint:raise ValueError('LIBRARY_DUPLICATE_REQUEST_CONFLICT')
                return self.snapshot()
            if self.closed or self.active():raise ValueError('LIBRARY_JOB_ALREADY_ACTIVE_OR_CLOSED')
            if len(self.jobs)>=128:raise ValueError('LIBRARY_JOB_HISTORY_CAPACITY')
            if action=='create_recipe':
                if not isinstance(body['prompt'],str) or not 1<=len(body['prompt'].strip())<=4000:raise ValueError('LIBRARY_PROMPT_REQUIRED')
                if 'reference' in body:
                    name,raw=self._attachment(body['reference'],'asset_reference')
                    from .image_validation import decode_image
                    decoded=decode_image(raw,max_pixels=40_000_000)
                    if len(raw)>10*1024*1024 or decoded.media_type!=body['reference']['media_type']:
                        raise ValueError('LIBRARY_REFERENCE_MEDIA_OR_BYTES_INVALID')
            else:
                if 'attachment' not in body:raise ValueError('LIBRARY_SOURCE_REQUIRED')
                name,raw=self._attachment(body['attachment'],'tool_input' if action=='run_tool' else 'asset_source')
            trace=self.workflow._application.diagnostics.begin('library_'+action,request_id=request_id,purpose=action)
            job=dict(job_id=uuid4().hex,project_id=self.project_id,request_id=request_id,fingerprint=fingerprint,
                purpose='asset_create' if action=='create_recipe' else 'asset_import' if action=='import_asset' else 'analysis',
                status='queued',phase='Queued',message='Explicit Library job queued. No scene change.',
                tool_id='builtin.recipe' if action=='create_recipe' else 'asset.inspect' if action=='import_asset' else body['tool_id'],
                execution_id=trace.execution_id,input_sha256=fingerprint,created_at=datetime.now(timezone.utc).isoformat(),error=None)
            folder=self._folder(job);folder.mkdir(parents=True,exist_ok=False)
            if action!='create_recipe' or 'reference' in body:
                path,sha=store_source(self.state_root,raw);job.update(source_sha256=sha,source_name=name)
                job['input_sha256']=sha
            self.jobs[job['job_id']]=job;self._save(job)
            token=CancellationToken();self.tokens[job['job_id']]=token
            worker=Thread(target=self._run,args=(job,deepcopy(body),token,trace),name='TwinPulseLibraryJob',daemon=True)
            self.threads[job['job_id']]=worker;worker.start()
            return self.snapshot()

    def _set_phase(self,job,phase,message):
        with self.lock:
            if job['status']=='cancelled':raise ValueError('LIBRARY_CANCELLED')
            job.update(status='running',phase=phase,message=message);self._save(job)

    def _run(self,job,body,token,trace):
        try:
            if body['action']=='check_extension':payload=self._probe_extension(job,body,token)
            elif body['action']=='create_recipe':payload=self._recipe(job,body,token,trace)
            elif body['action']=='import_asset':payload=self._import(job,body,token)
            else:payload=self._tool(job,body,token)
            with self.lock:
                if self.closed or token.is_cancelled or job['status']=='cancelled':raise ValueError('LIBRARY_CANCELLED')
                if job['purpose']=='analysis':job.update(status='ready',phase='Analysis complete',result=payload,
                    message='Actual input calculation finished; current environment unchanged.')
                else:
                    atomic_json(self._folder(job)/'asset.json',payload)
                    job.update(status='ready',phase='Validated asset ready',message='Review and Register this version separately. Current environment unchanged.')
                self._save(job)
            trace.finish('succeeded')
        except Exception as error:
            with self.lock:
                if job['status']!='cancelled':job.update(status='failed',phase='Failed',error=str(error)[:900],
                    message='No asset registered and no scene changed. Original input and logs retained.')
                self._save(job)
            trace.finish('cancelled' if token.is_cancelled else 'failed',error=error)

    def _recipe(self,job,body,token,trace):
        if self.registry is None:raise ValueError('LIBRARY_CONFIGURED_MODELS_REQUIRED')
        from .stage_routing import build_configured_stage_service,StageRoutingSettings
        from .product_inference import ProductInferenceScope
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        from twinpulse_provider.generation_store import input_digest
        from twinpulse_provider.library_recipe import generate_recipe
        service=build_configured_stage_service(self.registry)
        if service is None or not isinstance(service._provider,BudgetedPipeline):raise ValueError('LIBRARY_BUDGETED_ROUTE_REQUIRED')
        images=()
        if 'reference' in body:
            name,raw=self._attachment(body['reference'],'asset_reference')
            images=(ImageInput(name,body['reference']['media_type'],raw),)
        request=GenerationRequest(job['request_id'],body['prompt'],images,schema_version='library-asset-authoring-1.0',diagnostics=trace)
        from dataclasses import replace
        route=StageRoutingSettings(self.registry).load();provider=service._provider
        scope=ProductInferenceScope('ordinary-generation:'+uuid4().hex,input_digest(request),canonical_sha256(route),
            provider.policy.sha256,self.state_root/'ordinary-generation'/(uuid4().hex+'.ledger.json'),self.project_id)
        request=replace(request,inference_scope=scope)
        self._set_phase(job,'Authoring asset','Configured Flash reference observation / Nemotron reusable recipe; no environment generation.')
        try:recipe=asyncio.run(generate_recipe(provider,request,token,service._config))
        finally:atomic_json(self._folder(job)/'provider-diagnostic.json',provider.diagnostic_for(request.request_id))
        return dict(kind='recipe',recipe=recipe,model_id=provider.planner_model_id)

    def _require_extension(self,identity):
        extension=next(e for e in self.extensions() if e['extension_id']==identity)
        if not extension['available'] or not extension['enabled']:raise ValueError('OPTIONAL_TOOL_UNAVAILABLE: '+str(extension['reason']))

    def _import(self,job,body,token):
        name,raw=self._attachment(body['attachment'],'asset_source');suffix=Path(name).suffix.lower()
        origin=body['source'];license=body['license'] or 'Unspecified — verify source rights before redistribution'
        if any(not isinstance(v,str) or len(v)>300 for v in (origin,license)):raise ValueError('LIBRARY_SOURCE_METADATA_INVALID')
        self._set_phase(job,'Inspecting source','Preserving exact bytes; checking units, axis, topology and external dependencies.')
        folder=self._folder(job);unit=1.;axis='Z'
        if suffix=='.obj':
            if body.get('source_units') not in {'m','cm','mm'} or body.get('source_up_axis') not in {'Y','Z'}:
                raise ValueError('OBJ_EXPLICIT_SOURCE_UNITS_AND_AXIS_REQUIRED')
            unit={'m':1.,'cm':.01,'mm':.001}[body['source_units']];axis=body['source_up_axis']
            points,triangles=read_obj(raw)
        else:
            source=folder/('source'+suffix)
            with source.open('xb') as stream:stream.write(raw)
            if suffix in {'.step','.stp','.igs','.iges'}:
                self._require_extension('cad_converter');self._set_phase(job,'Converting CAD','Running configured local CAD converter; no Cloud transfer.')
                converted=folder/'converted.usdc';cad=Path(self.configuration['cad_converter']['executable'])
                stage=folder/'conversion';stage.mkdir()
                run_finite([str(cad),'-i',str(source),'-o',str(converted),'--no-materials'],stage,token,timeout=300)
                source=converted
            elif suffix not in {'.usd','.usda','.usdc'}:raise ValueError('LIBRARY_FORMAT_NOT_IMPLEMENTED: '+suffix)
            self._require_extension('usd_inspector');inspection=folder/'inspection';inspection.mkdir()
            output=inspection/'mesh.json';python=self._isaac_python()
            command=[str(python),str(resource_root()/'scripts'/'twinpulse_library_worker.py'),'--usd-input',str(source),'--output',str(output)]
            if any(any(c in str(v) for c in '&|<>^%\n\r') for v in command):raise ValueError('LIBRARY_WORKER_PATH_UNSAFE')
            run_finite(command,inspection,token,timeout=90)
            if not output.is_file() or output.stat().st_size>1500000:raise ValueError('LIBRARY_INSPECTION_RESULT_MISSING_OR_LARGE')
            result=json.loads(output.read_text(encoding='utf-8'));points=result['points'];triangles=result['triangles']
            unit=result['metres_per_unit'];axis=result['up_axis']
        sha=hashlib.sha256(raw).hexdigest()
        asset=normalize_mesh(points,triangles,logical_asset_id='asset_'+hashlib.sha256(name.lower().encode()).hexdigest()[:24],
            title=Path(name).stem[:100],source_name=name,source_sha256=sha,origin=origin or 'User-provided local asset',license=license,
            metres_per_unit=unit,up_axis=axis)
        return dict(kind='mesh',snapshot=asset.to_dict())

    def _tool(self,job,body,token):
        name,raw=self._attachment(body['attachment'],'tool_input');tool=body['tool_id']
        match=next(((extension,t) for extension in definitions() for t in extension['tools'] if t['tool_id']==tool),None)
        if match is None:raise ValueError('LIBRARY_TOOL_NOT_ALLOWLISTED')
        extension,descriptor=match;self._require_extension(extension['extension_id'])
        self._set_phase(job,'Running '+descriptor['title'],'Registered '+extension['transport']+' adapter; exact source bytes retained, no scene mutation.')
        result=execute(descriptor,raw,body['inputs'],self._folder(job),token)
        atomic_json(self._folder(job)/'result.json',result);return result

    def _extension_action(self,body):
        identity=body['extension_id']
        if identity not in {e['extension_id'] for e in self.extensions()}:raise ValueError('EXTENSION_NOT_REGISTERED')
        with self.lock:
            if self.closed or self.active():raise ValueError('LIBRARY_JOB_ALREADY_ACTIVE_OR_CLOSED')
            old=deepcopy(self.configuration.get(identity,{}))
            if body['action']=='configure_extension':
                if type(body['enabled']) is not bool or not isinstance(body['executable'],str):raise ValueError('EXTENSION_SETTINGS_INVALID')
                if body['executable']:
                    path=Path(body['executable'])
                    if identity!='cad_converter' or not path.is_absolute() or path.name.lower() not in {'usd-convert-cad.exe','usd-convert-cad'}:
                        raise ValueError('ONLY_REVIEWED_CAD_EXECUTABLE_ALLOWED')
                    old.update(executable=str(path),checked=False)
                old['enabled']=body['enabled'];self.configuration[identity]=old;atomic_json(self.config_path,self.configuration)
                return self.snapshot(message='Project extension settings saved. No tool installed or conversion started.')
            request_id='probe_'+uuid4().hex
            trace=self.workflow._application.diagnostics.begin('library_check_extension',request_id=request_id)
            job=dict(job_id=uuid4().hex,project_id=self.project_id,request_id=request_id,
                fingerprint=canonical_sha256(body),purpose='analysis',status='queued',phase='Queued',
                message='Local capability probe queued; cancellable and no scene change.',tool_id='probe.'+identity,
                execution_id=trace.execution_id,input_sha256=canonical_sha256(body),
                created_at=datetime.now(timezone.utc).isoformat(),error=None)
            self._folder(job).mkdir(parents=True,exist_ok=False);self.jobs[job['job_id']]=job;self._save(job)
            token=CancellationToken();self.tokens[job['job_id']]=token
            worker=Thread(target=self._run,args=(job,deepcopy(body),token,trace),name='TwinPulseLibraryProbe',daemon=True)
            self.threads[job['job_id']]=worker;worker.start();return self.snapshot()

    def _probe_extension(self,job,body,token):
        identity=body['extension_id']
        with self.lock:old=deepcopy(self.configuration.get(identity,{}))
        self._set_phase(job,'Checking optional tool','Local capability probe; no conversion, registration or scene change.')
        folder=self._folder(job)/'probe';folder.mkdir()
        updated=deepcopy(old)
        if identity=='csv_local':result=csv_summary(b'value\n2\n4\n',dict(column='value'))
        elif identity=='csv_mcp':result=call_csv_mcp(b'',{},folder,token,probe=True)
        elif identity=='cad_converter':
            path=Path(old.get('executable',''))
            if not path.is_file():raise ValueError('CAD_CONVERTER_NOT_CONFIGURED')
            run_finite([str(path),'--help'],folder,token,timeout=15)
            help_text=(folder/'stdout.log').read_text(encoding='utf-8',errors='replace')
            if 'usd-convert-cad' not in help_text or '--input' not in help_text:raise ValueError('CAD_CLI_CAPABILITY_MISMATCH')
            updated.update(checked=True,version='help_checked; package_version_unverified')
            result=dict(text='CLI options checked; conversion and licensing not tested.')
        elif identity=='usd_inspector':
            if not self._isaac_python().is_file():raise ValueError('USD_INSPECTOR_NOT_INSTALLED')
            run_finite([str(self._isaac_python()),str(resource_root()/'scripts'/'twinpulse_library_worker.py'),'--probe-usd'],folder,token,timeout=20)
            result=dict(text='Existing OpenUSD imported in a separate worker without starting Kit. Actual mesh import is tested separately; CAD conversion and physics are not certified.')
        else:raise ValueError('BREP_RUNTIME_AND_ADAPTER_NOT_VERIFIED')
        with self.lock:
            if token.is_cancelled or self.closed:raise ValueError('LIBRARY_CANCELLED')
            if self.configuration.get(identity,{})!=old:raise ValueError('LIBRARY_EXTENSION_CONFIGURATION_CHANGED')
            updated['last_check']=datetime.now(timezone.utc).isoformat();self.configuration[identity]=updated
            atomic_json(self.config_path,self.configuration);atomic_json(folder/'probe.json',result)
        return result

    def _placement(self,body):
        request_id=self._request_id(body)
        preview_id=canonical_sha256(dict(project_id=self.project_id,request_id=request_id))[:32]
        fingerprint=canonical_sha256(body)
        with self.workflow._lock:
            with self.lock:
                path=self.root/'placement-previews'/(preview_id+'.json')
                if path.exists():
                    record=self._read_placement(preview_id)
                    if record['request_fingerprint']!=fingerprint:raise ValueError('LIBRARY_DUPLICATE_REQUEST_CONFLICT')
                    return self.snapshot(placement_preview={**deepcopy(record['preview']), 'preview_id':preview_id})
            store=self.workflow._scene_edit_store();history=store.load();state=history.effective(store.source)
            if state.site.scene.revision!=body['expected_scene_revision']:raise ValueError('LIBRARY_PLACEMENT_REVISION_CHANGED')
            identity=body['instance_id'];position=body['position_m'];version=body['version'];asset_id=body['asset_id']
            if not isinstance(position,list) or len(position)!=3:raise ValueError('LIBRARY_PLACEMENT_POSITION_REQUIRED')
            if asset_id.startswith('local.'):
                recipe=self.workflow.model_recipe_store.snapshots().get(asset_id)
                if recipe is None or recipe_digest(recipe)!=version:raise ValueError('LIBRARY_RECIPE_VERSION_UNAVAILABLE')
                if position[2]!=0:raise ValueError('LIBRARY_RECIPE_FLOOR_CENTRE_XY_ONLY')
                args=dict(id=identity,kind=recipe['kind'],model_id=asset_id,recipe_sha256=version,
                    interpreter_version=recipe['interpreter_version'],recipe=recipe,
                    parameters={p['name']:p['default'] for p in recipe['parameters']},center_m=position[:2],yaw_deg=body['yaw_deg'])
                tool='place_model_recipe'
            else:
                snapshot=self.assets.load(asset_id,version);args=dict(id=identity,snapshot=snapshot,position_m=position,yaw_deg=body['yaw_deg']);tool='place_library_asset'
                from twinpulse_core.library_assets import expand_library_asset
                expand_library_asset(args)
            call=dict(call_id='library_'+uuid4().hex[:24],tool=tool,arguments=args)
            patch=dict(patch_version='scene-dependency-patch-1.0',edits=[dict(action='add',target_id=identity,
                reason='Explicit Library version placement; original asset remains immutable.',tool_call=call,
                placement=dict(id=identity,relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None))])
            preview=self.workflow.preview_scene_edit(operation_id='library_'+uuid4().hex,mode='dependency',target_call_id=None,tool_call=patch)
            # The browser cannot preserve Python's integral float spelling (1.0
            # becomes 1). Pin the original operation rather than weakening any
            # historical recipe/scene digest or accepting an altered operation.
            record=dict(schema_version='library-placement-preview-1.0',project_id=self.project_id,
                request_fingerprint=fingerprint,source_sha256=canonical_sha256(store.source.to_dict()),
                input_revision=store.source.input_revision.digest,preview=deepcopy(preview))
            record['sha256']=canonical_sha256(record)
            with self.lock:
                folder=path.parent
                if folder.is_symlink() or any(p.is_symlink() for p in folder.parents):raise ValueError('LIBRARY_LOCATION_INVALID')
                existing=list(folder.glob('*.json'))
                # Never evict previews referenced by an active/unknown Apply.
                # An exhausted local history is explicit, not silent deletion.
                if len(existing)>=128 or sum(p.stat().st_size for p in existing)>256*1024*1024:
                    raise ValueError('LIBRARY_PLACEMENT_HISTORY_CAPACITY')
                if len(json.dumps(record,ensure_ascii=False,allow_nan=False).encode('utf-8'))>16*1024*1024:
                    raise ValueError('LIBRARY_PLACEMENT_PREVIEW_BYTE_LIMIT')
                if path.exists():raise ValueError('LIBRARY_IMMUTABLE_PREVIEW_CONFLICT')
                atomic_json(path,record)
            return self.snapshot(placement_preview={**preview,'preview_id':preview_id},
                message='Validated placement proposal only. Apply still requires engine ACK and durable save.')

    def _read_placement(self,preview_id):
        if not isinstance(preview_id,str) or not re.fullmatch('[a-f0-9]{32}',preview_id):
            raise ValueError('LIBRARY_PLACEMENT_ID_INVALID')
        path=self.root/'placement-previews'/(preview_id+'.json')
        if path.is_symlink() or any(p.is_symlink() for p in path.parents) or not path.is_file() or path.stat().st_size>16*1024*1024:
            raise ValueError('LIBRARY_PLACEMENT_PREVIEW_UNAVAILABLE')
        record=json.loads(path.read_text(encoding='utf-8'))
        keys={'schema_version','project_id','request_fingerprint','source_sha256','input_revision','preview','sha256'}
        if (not isinstance(record,dict) or set(record)!=keys or record['schema_version']!='library-placement-preview-1.0'
                or record['project_id']!=self.project_id
                or record['sha256']!=canonical_sha256({k:v for k,v in record.items() if k!='sha256'})):
            raise ValueError('LIBRARY_PLACEMENT_PREVIEW_CORRUPT')
        source=self.workflow._application.site_draft
        if (source is None or record['source_sha256']!=canonical_sha256(source.to_dict())
                or record['input_revision']!=source.input_revision.digest):
            raise ValueError('LIBRARY_PLACEMENT_SOURCE_CHANGED')
        from .scene_changes import SceneChange
        preview=record['preview'];checked=SceneChange.from_dict(preview['operation'])
        if preview['preview_digest']!=canonical_sha256(checked.to_dict()):raise ValueError('LIBRARY_PLACEMENT_DIGEST_INVALID')
        return record

    def pinned_placement_operation(self,preview_id,digest):
        """Resolve only immutable input, leaving duplicate/current admission to Tx.

        Do not call _scene_edit_store here: its current-revision/mutation guards
        must not precede Tx.start's same-operation BUILDING/COMMITTED recovery.
        """
        try:
            with self.workflow._lock,self.lock:
                record=self._read_placement(preview_id);preview=record['preview']
                if not isinstance(digest,str) or digest!=preview['preview_digest']:
                    raise ValueError('LIBRARY_PLACEMENT_DIGEST_MISMATCH')
                return deepcopy(preview['operation']),digest
        except (ValueError,TypeError,KeyError,OSError) as error:
            raise BrokerError('library_placement_invalid',str(error)[:600],status=409) from error
