# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Workspace admission and live observation over a data-only local registry."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import re
import time
from threading import Thread
from uuid import uuid4
from twinpulse_core.robot_battery import battery_display_config

from .command_broker import BrokerError
from .robot_adapters import ADAPTERS, CREDENTIAL_REF, instance_binding, require_adapter
from .robot_registry import RobotEndpoint, RobotRegistry
from .robot_discovery import discover
from .robot_connection_preparation import RobotConnectionPreparation


class RobotRegistryService:
    def __init__(self, devices, state_root, *, discoverer=discover, source_root=None, preparation=None,
                 clock=time.monotonic, utcnow=lambda:datetime.now(timezone.utc)):
        self.devices=devices
        self.registry=RobotRegistry(state_root)
        self.discoverer=discoverer
        self.clock=clock;self.utcnow=utcnow;self._discovery_finished=None
        self.thread=None
        self.discovery={'state':'idle','candidates':[],'known_devices':[],'sources':{}}
        self.closed=False
        diagnostics=devices.diagnostics
        self.preparation=preparation or RobotConnectionPreparation(
            source_root or getattr(diagnostics,'root',None),
            identity=getattr(diagnostics,'identity',None),known_hosts=getattr(diagnostics,'known_hosts',None))
        # A fresh installation has no robot. Preserve existing registry/history,
        # but never invent or auto-select the developer's old fixed endpoint.
        # Legacy job readers retain their original per-job binding separately.
        self._bind(self.registry.active())

    def _bind(self,row):
        if all(service is None for service in (self.devices.diagnostics,self.devices.readiness,self.devices.controller)):
            return
        try:binding=instance_binding(row)
        except ValueError:
            if self.devices.controller is not None or self.devices.readiness is not None:raise
            binding=None
        for service in (self.devices.diagnostics,self.devices.readiness,self.devices.controller):
            if service is not None:service.bind_instance(binding)

    def _discovery_snapshot(self,robots):
        value=deepcopy(self.discovery)
        observed=value.pop('_observed_candidates',[])
        age=None if self._discovery_finished is None else self.clock()-self._discovery_finished
        value['age_seconds']=None if age is None else round(max(0,age),3)
        value['freshness']='none'
        visible=[]
        for candidate in value['candidates']:
            lifetime=candidate.get('valid_for_seconds',0)
            if age is None or age<0 or not 0<=age<lifetime or value['state']!='completed':continue
            candidate['remaining_seconds']=round(lifetime-age,3)
            endpoint=candidate.get('endpoint') or {}
            hosts={str(candidate.get('address','')).rstrip('.').casefold(),str(candidate.get('hostname','')).rstrip('.').casefold()}
            matches=[row for row in robots if row['endpoint']['host'].rstrip('.').casefold() in hosts
                and row['endpoint']['port']==endpoint.get('port')]
            candidate['registered_matches']=[{'id':row['id'],'label':row['label']} for row in matches]
            visible.append(candidate)
        # A completed search with no replies is still recent, not evidence of power-off.
        network_ok=(value.get('sources',{}).get('network') or {}).get('state')=='completed'
        if value['state']=='completed' and network_ok and age is not None:
            value['freshness']='recent' if 0<=age<30 and (visible or (not value['candidates'] and not observed)) else 'expired'
        if not network_ok:visible=[]
        value['candidates']=visible
        value['remaining_seconds']=max(0,30-age) if value['freshness']=='recent' else 0
        for row in robots:
            match=next((candidate for candidate in visible if any(item['id']==row['id'] for item in candidate['registered_matches'])),None)
            previously_matched=any(row['endpoint']['host'].rstrip('.').casefold() in
                {str(item.get('address','')).rstrip('.').casefold(),str(item.get('hostname','')).rstrip('.').casefold()}
                and row['endpoint']['port']==(item.get('endpoint') or {}).get('port') for item in [*self.discovery['candidates'],*observed])
            row['discovery_presence']={'state':'recent_address_response' if match else 'not_seen' if value['freshness']=='recent' and not previously_matched else 'unknown',
                'identity_verified':False,'observed_at_utc':value.get('finished_at_utc'),
                'remaining_seconds':match['remaining_seconds'] if match else value['remaining_seconds']}
        return value

    def snapshot(self,owner):
        value=self.registry.snapshot()
        value['battery_display_presets']={mode:battery_display_config(mode) for mode in ('voltage_only','robotis_opencr')}
        value['timing_fields']=self.registry.timing_store.fields()
        pool=getattr(self.devices,'physical_fleet',None)
        if pool is not None and hasattr(pool,'timing_for_view'):
            for row in value['robots']:row['timing_runtime']=pool.timing_for_view(row['id'])
        value['adapters']=deepcopy(list(ADAPTERS))
        value['discovery']=self._discovery_snapshot(value['robots'])
        value['guide']={'discovery_is_connectivity':False,'registration_is_connectivity':False,
                        'supported_adapter_ids':[ADAPTERS[0]['id']],
                        'new_hardware':'Register metadata only, then review an adapter. Device names never authorize a motor protocol.'}
        connection={'state':'idle'}
        diagnostics=self.devices.diagnostics
        if diagnostics is not None:
            current=diagnostics.snapshot(owner);job=current.get('job') or {};record=current.get('record') or {}
            binding=job.get('robot_binding') or {}
            same=binding.get('instance_id')==value['active_id']
            if same and job:
                connection={'state':'running' if job.get('status')=='RUNNING' else 'completed' if job.get('status')=='COMPLETED' else 'failed',
                            'code':job.get('result_code'),'message':'Read-only observation only; motion remains unauthorized.'}
                for key in ('id','started_at_utc','finished_at_utc','health_status','sensor_status'):
                    item=job.get(key)
                    if isinstance(item,str) and len(item)<=100:connection['job_id' if key=='id' else key]=item
                connection.update(execution_id=job.get('execution_id'),logs_saved=job.get('saved') is True,
                    scan_count=job.get('scan_count',0),artifact_id=job.get('id'))
                detail=(job.get('diagnostic') or {}).get('code')
                if isinstance(detail,str) and re.fullmatch(r'[A-Z0-9_]{1,80}',detail):
                    connection['diagnostic_code']=detail
                reason=detail or job.get('result_code')
                connection['next_step']={
                    'SSH_CONNECTION_REFUSED':'Check the selected address and whether the robot SSH service is available.',
                    'SSH_CONNECT_TIMEOUT':'Check robot power, current address and the shared network.',
                    'SSH_NO_ROUTE':'Check the PC and robot network connection and current address.',
                    'SSH_HOST_KEY_REJECTED':'Verify the robot fingerprint using a trusted source. Do not replace a host key automatically.',
                    'SSH_AUTH_FAILED':'Check the selected SSH account and adapter automation-key setup.',
                    'SSH_NAME_RESOLUTION_FAILED':'Check the robot name or register its current known IP address.',
                    'OBSERVATION_NEEDS_ATTENTION':'Review the fresh health and sensor result before any later collection or movement.',
                    'CHECK_OR_SAVE_FAILED':'Review the local diagnostic log and installation. Connectivity was not confirmed.',
                }.get(reason,'Wait for the current observation.' if job.get('status')=='RUNNING'
                    else 'Read-only result recorded. It does not enable collection or motion.')
                fresh=(job.get('status')=='COMPLETED' and job.get('authentication_verified') is True
                       and type(record.get('age_seconds')) in (int,float) and 0<=record['age_seconds']<=120)
                if fresh:
                    for row in value['robots']:
                        if row['id']==value['active_id']:row['connection_state']='verified_observation'
        value['connection']=connection
        value['observation_history']=diagnostics.observation_catalog(value['active_id']) if diagnostics is not None else []
        binding_problem=None
        try:binding=instance_binding(self.registry.active())
        except ValueError as error:binding=None;binding_problem=str(error)
        value['capabilities']={'registration':True,'discovery':True,'local_preparation':True,
            'selected_preparation_available':binding is not None,
            'read_only_connection':diagnostics is not None,'physical_control':self.devices.controller is not None,
            'unavailable_reason':self.devices.unavailable_reason}
        value['preparation']=self.preparation.snapshot(binding,value['revision'])
        if binding_problem:
            value['preparation'].update(state='needs_attention',checks=[{'id':'reviewed_adapter','state':'needs_attention',
                'detail':'Saved adapter/version metadata needs review before connection preparation.',
                'next_step':'Keep the saved registration and review its adapter version and calibration metadata.'}],
                reason='ROBOT_ADAPTER_REVIEW_REQUIRED')
        return value

    def _admission(self):
        if getattr(self.devices,'engine_process_probe_blocked',False):
            raise BrokerError('engine_observation_stale','Wait for current engine observation before connecting.',status=409)
        self.devices.assert_document_available()
        for context in self.devices.contexts:
            workflow=getattr(context,'product_workflow',None)
            workspace=getattr(context,'workspace',None)
            if workspace is not None and workspace.switching():
                raise BrokerError('project_switch_pending','Wait for the conversation switch before changing robot settings.',status=409)
            if workflow is not None and (workflow.scene_edit_transaction.locked() or workflow.has_active_generation()):
                raise BrokerError('robot_registry_workspace_busy','Finish the current generation or scene change before changing the active robot.',status=409)

    def request(self,body,owner):
        with self.devices.lock:
            if self.closed:raise BrokerError('robot_registry_closed','Robot registry is closed.',status=409)
            if body is None:return self.snapshot(owner)
            if not isinstance(body,dict):raise BrokerError('robot_registry_request_invalid','A robot action is required.',status=400)
            operation=body.get('action')
            allowed={'register':{'action','expected_revision','label','adapter_id','endpoint'},
                     'set_battery_display':{'action','expected_revision','id','config','expected_display_sha256'},
                     'set_timing_profile':{'action','expected_revision','id','values','mode','expected_timing_sha256'},
                     'import_timing_measurement':{'action','expected_revision','id','report','expected_timing_sha256'},
                     'recalculate_timing_profile':{'action','expected_revision','id','expected_timing_sha256'},
                     'apply_timing_recommendation':{'action','expected_revision','id','expected_timing_sha256','expected_recommendation_sha256'},
                     'select':{'action','expected_revision','id'},'discover':{'action','expected_revision'},
                     'connect':{'action','expected_revision'},'prepare':{'action','expected_revision'}}
            if not isinstance(operation,str) or operation not in allowed or set(body)!=allowed[operation]:
                raise BrokerError('robot_registry_request_invalid','Unsupported robot registry action or fields.',status=400)
            expected=body.get('expected_revision')
            if type(expected) is not int or expected!=self.registry.snapshot()['revision']:
                raise BrokerError('robot_registry_changed','Robot registry changed. Refresh before applying this action.',status=409)
            try:
                if operation=='register':
                    adapter=next((a for a in ADAPTERS if a['id']==body['adapter_id']),None)
                    if adapter is None:raise ValueError('ROBOT_ADAPTER_UNKNOWN')
                    endpoint=body['endpoint']
                    if not isinstance(endpoint,dict) or set(endpoint)!={'host','user','port','ros_domain_id'}:raise ValueError('ROBOT_ENDPOINT_INVALID')
                    self.registry.register(label=body['label'],adapter_id=adapter['id'],adapter_version=adapter['version'],
                        robot_profile_id=adapter['robot_profile_id'],endpoint=RobotEndpoint(**endpoint),
                        credential_ref=CREDENTIAL_REF,expected_revision=expected)
                elif operation=='set_battery_display':
                    # Local display metadata only: no device binding, admission,
                    # connection, deployment or motion authority is changed.
                    self.registry.set_battery_display(body['id'],body['config'],expected_revision=expected,
                        expected_display_sha256=body['expected_display_sha256'])
                elif operation=='set_timing_profile':
                    if body['mode']!='custom':raise ValueError('TIMING_MODE')
                    self.registry.timing_action(body['id'],expected_revision=expected,expected_sha256=body['expected_timing_sha256'],
                        values=body['values'],mode=body['mode'])
                elif operation=='recalculate_timing_profile':
                    self.registry.timing_action(body['id'],expected_revision=expected,expected_sha256=body['expected_timing_sha256'],recalculate=True)
                elif operation=='apply_timing_recommendation':
                    self.registry.timing_action(body['id'],expected_revision=expected,expected_sha256=body['expected_timing_sha256'],
                        mode='measured_default',expected_recommendation_sha256=body['expected_recommendation_sha256'])
                elif operation=='import_timing_measurement':
                    from twinpulse_core.robot_timing_profile import digest
                    report=body['report']
                    if (not isinstance(report,dict) or set(report)!={'schema_version','robot_id','binding_sha256','operation_id','measurement','measurement_sha256','origin'}
                            or report['schema_version']!='robot-timing-import-1.0' or report['robot_id']!=body['id']
                            or digest(report['measurement'])!=report['measurement_sha256']
                            or report['origin']!='IMPORTED_RECORDED_TIMING_NOT_LIVE_AUTHENTICATION'):
                        raise ValueError('TIMING_IMPORT_SHAPE')
                    row=next((r for r in self.registry.snapshot()['robots'] if r['id']==body['id']),None)
                    if row is None or instance_binding(row)['sha256']!=report['binding_sha256']:raise ValueError('TIMING_BINDING_CHANGED')
                    self.registry.timing_action(body['id'],expected_revision=expected,expected_sha256=body['expected_timing_sha256'],
                        measurement=report['measurement'],operation_id=report['operation_id'],origin=report['origin'])
                elif operation=='select':
                    self._admission()
                    if self.thread and self.thread.is_alive():raise BrokerError('robot_discovery_busy','Wait for discovery to finish.',status=409)
                    current=self.registry.active()
                    row=self.registry.select(body['id'],expected_revision=expected,assert_workspace_idle=self._admission)
                    if current!=row:
                        try:self._bind(row)
                        except Exception:
                            # A failed bind must never leave live services on a
                            # different endpoint from the saved active selection.
                            for service in (self.devices.diagnostics,self.devices.readiness,self.devices.controller):
                                if service is not None:service.bind_instance(None)
                            raise
                elif operation=='discover':
                    self._admission()
                    if self.thread and self.thread.is_alive():raise BrokerError('robot_discovery_busy','Discovery is already running.',status=409)
                    run=uuid4().hex
                    self._discovery_finished=None
                    self.discovery={'state':'running','run_id':run,'started_at_utc':self.utcnow().isoformat(),
                        'candidates':[],'known_devices':[],'sources':{}}
                    self.thread=Thread(target=self._discover,args=(run,),daemon=True,name='TwinPulseRobotDiscovery')
                    self.thread.start()
                elif operation=='prepare':
                    self._admission()
                    try:binding=instance_binding(self.registry.active())
                    except ValueError:return self.snapshot(owner)
                    if binding is None:raise BrokerError('robot_selection_required','Select a registered robot first.',status=409)
                    self.preparation.check(binding,expected)
                else:
                    self._admission()
                    try:row=self.registry.active_at_revision(expected)
                    except ValueError:
                        raise BrokerError('robot_registry_changed','Robot selection changed. Refresh before connecting.',status=409) from None
                    binding=instance_binding(row)
                    require_adapter(binding)
                    diagnostics=self.devices.diagnostics
                    if diagnostics is None:raise BrokerError('robot_diagnostics_unavailable','Read-only diagnostics is unavailable.',status=409)
                    diagnostics.bind_instance(binding)
                    prepared=diagnostics.preflight(owner)
                    token=prepared.get('start_token')
                    if not token:raise BrokerError('robot_preflight_required','Existing OpenSSH client, automation key and known-host entry are required. Review PC preparation.',status=409)
                    diagnostics.start(owner,token,True)
            except (ValueError,TypeError,KeyError) as error:
                code=str(error)
                if code=='ROBOT_REGISTRY_CHANGED':
                    raise BrokerError('robot_registry_changed','Saved robot settings changed. Refresh before saving again.',status=409) from error
                raise BrokerError('robot_registry_invalid',code if code.startswith('ROBOT_') else 'Invalid robot registry data.',status=400) from error
            return self.snapshot(owner)

    def _discover(self,run):
        try:
            result=self.discoverer()
            with self.devices.lock:
                if not self.closed and self.discovery.get('run_id')==run:
                    finished=self.utcnow();self._discovery_finished=self.clock()
                    # OS inventory cannot establish current presence, even from an old adapter.
                    responses=[];known=deepcopy(result.get('known_devices',[]));observed=deepcopy(result.get('expired_candidates',[]))
                    for candidate in deepcopy(result['candidates']):
                        if candidate.get('transport')!='network':known.append(candidate);continue
                        lifetime=candidate.get('valid_for_seconds',0)
                        if type(lifetime) not in (int,float) or not 0<lifetime<=30:continue
                        expires=candidate.pop('_expires_monotonic',None)
                        if type(expires) in (int,float):lifetime=min(lifetime,max(0,expires-self._discovery_finished))
                        if lifetime<=0:observed.append(candidate);continue
                        candidate.update(valid_for_seconds=lifetime,observed_at_utc=finished.isoformat(),
                            expires_at_utc=(finished+timedelta(seconds=lifetime)).isoformat(),identity_verified=False)
                        responses.append(candidate)
                    self.discovery={'state':'completed','run_id':run,'started_at_utc':self.discovery.get('started_at_utc'),
                        'finished_at_utc':finished.isoformat(),'candidates':responses,
                        'known_devices':known,'_observed_candidates':observed,'sources':result['sources']}
        except Exception:
            with self.devices.lock:
                if not self.closed and self.discovery.get('run_id')==run:
                    self._discovery_finished=None
                    self.discovery={'state':'failed','run_id':run,'finished_at_utc':self.utcnow().isoformat(),
                        'candidates':[],'known_devices':[],'sources':{}}

    def close(self):
        self.closed=True
        if self.thread:self.thread.join(timeout=6)
