# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned, explicit no-motion collection through the existing readiness CLI.

The CLI may transfer reviewed source. Construction, GET, and server restart never
contact the robot. A lost/restarted job is uncertain and cannot be retried until
the operator confirms the robot is powered off; no motion authority is granted.
"""

from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import RLock, Thread
import time

from .command_broker import BrokerError


class RobotReadiness:
    def __init__(self, root, *, runner=None, resume_runner=None, wall=lambda: time.time() * 1000, archive_root=None):
        self.root = Path(root).resolve()
        self.archive_root = Path(archive_root).resolve() if archive_root is not None else self.root
        self._state_path = self.archive_root / 'artifacts/robot-readiness-app/current.json'
        self._runner = runner or self._run_cli
        self._resume_runner = resume_runner or self._run_resume_cli
        self._resume_thread = None
        self._wall = wall
        self._lock = RLock()
        self._thread = None
        self._closed = False
        self._state = {'schema_version': 'robot-readiness-app-1.0', 'status': 'NOT_STARTED',
                       'motion_authorized': False, 'demo_ready': False, 'job_id': None,
                       'owner': None, 'project_id': 'default', 'app_context': None,
                       'result': None, 'report_path': None}
        if self._state_path.is_file() and not self._state_path.is_symlink():
            try:
                previous = json.loads(self._state_path.read_text(encoding='utf-8'))
                if (previous.get('schema_version') == 'robot-readiness-app-1.0'
                        and previous.get('status') in {'NOT_STARTED', 'RUNNING', 'REMOTE_STATE_UNKNOWN',
                            'LOCAL_RECORD_UNREADABLE', 'CLEARED_AFTER_OPERATOR_OFF',
                            'COMPLETED_WITH_GAPS', 'COLLECTED_UNALIGNED', 'BLOCKED_LOCAL'}
                        and (previous.get('job_id') is None or isinstance(previous.get('job_id'), str))):
                    self._state = {**previous, 'motion_authorized': False, 'demo_ready': False}
                    if isinstance(previous.get('result'), dict):
                        self._state['result'] = {**previous['result'], 'motion_authorized': False,
                                                 'demo_ready': False}
                    if previous.get('status') == 'RUNNING':
                        self._state = {**previous, 'status': 'REMOTE_STATE_UNKNOWN',
                                       'result': {'status': 'SERVER_RESTARTED_DURING_COLLECTION',
                                                  'demo_ready': False, 'motion_authorized': False}}
                        self._persist()
                else:
                    self._state['status'] = 'LOCAL_RECORD_UNREADABLE'
            except (OSError, ValueError, TypeError):
                self._state['status'] = 'LOCAL_RECORD_UNREADABLE'
        self._state.setdefault('evidence_recovery', {'status':'NOT_STARTED','transfer_only':True})
        self._state.setdefault('transfer_requests', {})
        if (not isinstance(self._state['evidence_recovery'],dict)
                or not isinstance(self._state['transfer_requests'],dict)
                or len(self._state['transfer_requests'])>128
                or any(not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key)
                       or not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value)
                       for key,value in self._state['transfer_requests'].items())):
            self._state.update(status='LOCAL_RECORD_UNREADABLE',transfer_requests={},
                evidence_recovery={'status':'INVALID_RECORD','transfer_only':True})
        if self._state['evidence_recovery'].get('status')=='TRANSFERRING':
            self._state['evidence_recovery'].update(status='INTERRUPTED',reason='APP_RESTARTED_TRANSFER_NOT_RESUMED')
        from .robot_adapters import legacy_binding, checked_binding
        self._instance=legacy_binding()
        try:
            self._job_binding=(checked_binding(self._state['robot_binding'])
                               if 'robot_binding' in self._state else legacy_binding())
        except (ValueError,TypeError,KeyError):
            self._job_binding=None
            self._state['status']='LOCAL_RECORD_UNREADABLE'

    def bind_instance(self,binding):
        from .robot_adapters import checked_binding
        with self._lock:
            if self.local_operation_active():
                raise BrokerError('readiness_busy_or_uncertain','Wait for the collection or evidence transfer before selecting a robot.',status=409)
            self._instance=checked_binding(binding) if binding is not None else None
            # Previous job data keeps its original binding and global UNKNOWN gate.
            # It is historical evidence, never readiness for the new selection.

    def _persist(self):
        folder = self._state_path.parent
        if (self.archive_root/'artifacts').is_symlink() or folder.is_symlink() or self._state_path.is_symlink():
            raise OSError('Unsafe readiness state path')
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / 'current.json.part'
        if temp.is_symlink():
            raise OSError('Unsafe readiness temporary path')
        encoded=json.dumps(self._state,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        with temp.open('wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self._state_path)

    def _reserve_twin_collection_reference(self,binding,*,suffix=''):
        """Immutable per-job start provenance. Never changes original raw/CLI reports."""
        from twinpulse_core import canonical_sha256
        folder=self._state_path.parent/'collection-bindings'
        path=folder/(binding['job_id']+suffix+'.json')
        if any(p.is_symlink() for p in (self.archive_root/'artifacts',self._state_path.parent,folder,path)):
            raise OSError('Unsafe collection binding path')
        folder.mkdir(parents=True,exist_ok=True)
        record={**deepcopy(binding),'sha256':canonical_sha256(binding)}
        data=json.dumps(record,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
        with path.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        return record['sha256']

    def snapshot(self, owner):
        with self._lock:
            state = {key: value for key, value in self._state.items() if key not in {'owner','transfer_requests'}}
            state['owned'] = bool(owner and owner==self._state.get('owner'))
            state['current_operation_active'] = self.local_operation_active()
            state['record_scope'] = 'current_operation' if state['current_operation_active'] else 'saved_result'
            state['robot_binding']=deepcopy(self._job_binding)
            state['selected_robot_binding']=deepcopy(self._instance)
            state['selected_instance_matches_job']=self._instance==self._job_binding
            if not state['selected_instance_matches_job'] and not state['current_operation_active']:
                state['historical_robot_record']={'status':state['status'],'job_id':state.get('job_id'),
                    'robot_binding':deepcopy(self._job_binding),'result':state.get('result'),'report_path':state.get('report_path')}
                if state['status'] not in {'REMOTE_STATE_UNKNOWN','LOCAL_RECORD_UNREADABLE'}:
                    state.update(status='NOT_STARTED',job_id=None,result=None,report_path=None,owned=False)
            # This service exists only in the default local project. Authenticated
            # project sessions may review the saved result after an App restart.
            return json.loads(json.dumps(state))

    def blocks_robot_operation(self):
        with self._lock:
            return (self._state['status'] in {'RUNNING', 'REMOTE_STATE_UNKNOWN', 'LOCAL_RECORD_UNREADABLE'}
                    or bool(self._resume_thread and self._resume_thread.is_alive()))

    def local_operation_active(self):
        """Current work only. Restarted/failed reports remain physical evidence."""
        with self._lock:
            return bool(self._thread and self._thread.is_alive()
                        or self._resume_thread and self._resume_thread.is_alive()
                        or self._state['status'] == 'RUNNING')

    def blocks_read_only_observation(self):
        return self.local_operation_active()

    def blocks_scene_edit(self, *, saved_sim_scope=False):
        """Separate SIM document edits, never physical readiness or Stop proof.

        A completed prepare-only failure can leave REAL readiness unknown even
        though no stationary evidence/scene authority was acquired. Only the
        original, bounded, matching reports prove that narrow distinction.
        Unknown collection, restart, transfer or malformed records still block.
        """
        with self._lock:
            if (self._thread and self._thread.is_alive()
                    or self._resume_thread and self._resume_thread.is_alive()):
                return True
            if not self.blocks_robot_operation():
                return False
            if saved_sim_scope is not True or self._state['status'] != 'REMOTE_STATE_UNKNOWN':
                return True
            try:
                return not self._terminal_precollection_only()
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                return True

    def _bounded_saved_report(self, value, folder, suffix):
        if not isinstance(value, str):raise ValueError('READINESS_REPORT_UNAVAILABLE')
        path=Path(value);resolved=path.resolve(strict=True)
        report_root=self._report_root(resolved)
        base=report_root/'artifacts'/folder
        parts=resolved.relative_to(base.resolve()).parts
        if (not path.is_absolute() or len(parts)!=1+len(suffix) or not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}',parts[0])
                or parts[1:]!=suffix or resolved.stat().st_size>1024*1024
                or any(parent.is_symlink() for parent in (path,*path.parents) if parent.is_relative_to(report_root))):
            raise ValueError('READINESS_REPORT_UNSAFE')
        return json.loads(resolved.read_text(encoding='utf-8'))

    def _report_root(self, path):
        for root in (self.archive_root, self.root):
            if path.is_relative_to(root / 'artifacts'):
                return root
        raise ValueError('READINESS_REPORT_OUTSIDE_ARCHIVE')

    @staticmethod
    def _utc_record_time(value):
        if not isinstance(value,str):raise ValueError('READINESS_TERMINAL_TIME_MISSING')
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:raise ValueError('READINESS_TERMINAL_TIME_UNQUALIFIED')
        return parsed.astimezone(timezone.utc)

    def _terminal_precollection_only(self):
        state=self._state
        # Re-read the durable receipt. Constructor normalization must not turn
        # a contradictory stored authority flag into proof of no authority.
        if (any(path.is_symlink() for path in (self._state_path,self._state_path.parent,self.archive_root/'artifacts'))
                or self._state_path.stat().st_size>1024*1024):return False
        durable=json.loads(self._state_path.read_text(encoding='utf-8'))
        keys=('schema_version','status','job_id','project_id','app_context','result',
              'report_path','started_at_utc','finished_at_utc','exit_code','motion_authorized','demo_ready')
        if any(durable.get(key)!=state.get(key) for key in keys):return False
        if (state.get('schema_version')!='robot-readiness-app-1.0' or state.get('project_id')!='default'
                or not isinstance(state.get('job_id'),str) or not re.fullmatch('[a-f0-9]{32}',state['job_id'])
                or state.get('motion_authorized') is not False or state.get('demo_ready') is not False
                or type(state.get('exit_code')) is not int or state['exit_code']!=2
                or state.get('app_context')!={'app_scene_revision':None,'app_robot_profile_id':None,'capture_status':'CAPTURED'}
                or state.get('evidence_recovery')!={'status':'NOT_STARTED','transfer_only':True}
                or state.get('transfer_requests')):return False
        started=self._utc_record_time(state.get('started_at_utc'))
        finished=self._utc_record_time(state.get('finished_at_utc'))
        if finished<started:return False
        result=self._bounded_saved_report(state.get('report_path'),'robot-readiness',('report.json',))
        if (result!=state.get('result') or set(result)!={'schema_version','status','scope','motion_authorized',
                'run_requested','steps','demo_ready','remaining_gates','offline_collection_preflight','reason'}
                or result.get('schema_version')!='robot-readiness-1.0'
                or result.get('status')!='STOPPED_AT_SOURCE_AND_IDLE' or result.get('scope')!='NO_MOTION_COLLECTION'
                or result.get('run_requested') is not True or result.get('motion_authorized') is not False
                or result.get('demo_ready') is not False
                or any(key in result for key in ('evidence','unbound_evidence','evidence_export','stationary_status','boot_id','release_id'))
                or result.get('remaining_gates')!={'ros_lidar_driver_and_physical_stop':'NOT_RUN_SEPARATE_APPROVAL',
                    'sensor_chassis_room_alignment':'NOT_VERIFIED','local_collision_protection':'NOT_VERIFIED',
                    'scoped_autonomous_mission':'LOCKED'}):return False
        steps=result.get('steps')
        if not isinstance(steps,dict) or set(steps)!={'offline_collection_preflight','source_and_idle','stationary_collection','evidence_review'}:return False
        skipped={'status':'NOT_RUN','reason':'DEPENDENCY_NOT_SATISFIED: STOPPED_AT_SOURCE_AND_IDLE'}
        if steps['stationary_collection']!=skipped or steps['evidence_review']!=skipped:return False
        if steps['offline_collection_preflight']!={'status':'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'}:return False
        preflight=result.get('offline_collection_preflight') or {}
        if (preflight.get('schema_version')!='robot-collection-offline-preflight-1.0'
                or preflight.get('status')!='COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'
                or preflight.get('motion_authorized') is not False or preflight.get('demo_ready') is not False
                or preflight.get('hardware_validation')!='NOT_RUN'):return False
        source=steps['source_and_idle']
        if (source.get('status')!='PREPARED_NEEDS_ATTENTION' or type(source.get('exit_code')) is not int
                or source['exit_code']!=state['exit_code'] or source.get('failure_diagnostics') is not None):return False
        child=self._bounded_saved_report(source.get('report_path'),'robot-preparation',('result','report.json'))
        child_finished=self._utc_record_time(child.get('finished_at_utc'))
        # The prepare report may observe unsafe board state. It is deliberately
        # NOT interpreted as idle, cleanup, alignment or physical motion proof.
        return (child.get('schema_version')=='robot-prepare-1.0' and child.get('action')=='prepare'
            and child.get('status')==source['status'] and child.get('motion_authorized') is False
            and child.get('stationary') is None and started<=child_finished<=finished)

    def start(self, owner, request_id, confirmed, expires_at_ms, *, app_context=None, project_id='default',twin_context=None):
        from .project_store import checked_project_id
        checked_project_id(project_id)
        with self._lock:
            if self._closed:
                raise BrokerError('readiness_closed', 'Readiness service is closed', status=409)
            if (confirmed is not True or not isinstance(request_id, str)
                    or re.fullmatch('[a-f0-9]{32}', request_id) is None
                    or type(expires_at_ms) not in (int, float)
                    or not 0 < expires_at_ms - self._wall() <= 2000):
                raise BrokerError('readiness_confirmation', 'Fresh explicit no-motion collection approval required', status=409)
            if request_id == self._state['job_id'] and owner == self._state['owner']:
                return self.snapshot(owner)
            if self.blocks_robot_operation():
                raise BrokerError('readiness_busy_or_uncertain', 'Previous collection is running or its remote state is unknown', status=409)
            if self._state['job_id'] == request_id:
                raise BrokerError('readiness_request_reused', 'Request ID was already consumed', status=409)
            from .robot_adapters import require_adapter
            require_adapter(self._instance,operation='preparation')
            if app_context is None:
                app_context = {'app_scene_revision': None, 'app_robot_profile_id': None,
                               'capture_status': 'UNAVAILABLE'}
            if (not isinstance(app_context, dict)
                    or set(app_context) != {'app_scene_revision', 'app_robot_profile_id', 'capture_status'}
                    or app_context['capture_status'] not in {'CAPTURED', 'UNAVAILABLE'}
                    or (app_context['app_scene_revision'] is not None
                        and (not isinstance(app_context['app_scene_revision'], str)
                             or re.fullmatch('[a-f0-9]{64}', app_context['app_scene_revision']) is None))
                    or (app_context['app_robot_profile_id'] is not None
                        and (not isinstance(app_context['app_robot_profile_id'], str)
                             or re.fullmatch('[A-Za-z0-9_.-]{1,128}', app_context['app_robot_profile_id']) is None))
                    or (app_context['capture_status'] == 'UNAVAILABLE'
                        and (app_context['app_scene_revision'] is not None
                             or app_context['app_robot_profile_id'] is not None))):
                raise BrokerError('readiness_context_invalid', 'App scene reference is invalid', status=409)
            if twin_context is not None:
                from .scene_sensor_review import checked_context
                try:
                    twin_context=checked_context(twin_context)
                    if twin_context['project_id']!=project_id:raise ValueError('Project changed')
                except (ValueError,TypeError,KeyError) as error:
                    raise BrokerError('readiness_context_invalid','Current Twin binding is invalid',status=409) from error
            self._state = {'schema_version': 'robot-readiness-app-1.0', 'status': 'RUNNING',
                           'robot_binding':deepcopy(self._instance),
                           'motion_authorized': False, 'demo_ready': False, 'job_id': request_id,
                           'project_id': project_id, 'app_context': dict(app_context),
                           'owner': owner, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
                           'result': None, 'report_path': None,
                           'evidence_recovery': {'status':'NOT_STARTED','transfer_only':True},
                           'transfer_requests': dict(self._state.get('transfer_requests',{}))}
            self._job_binding=deepcopy(self._instance)
            self._state['twin_collection_binding']={'schema_version':'stationary-twin-collection-1.0',
                'job_id':request_id,'project_id':project_id,'context':twin_context,
                'robot_binding':deepcopy(self._job_binding),
                'context_sha256':(__import__('twinpulse_core').canonical_sha256(twin_context) if twin_context else None),
                'status':'COLLECTION_START_REFERENCE_ONLY' if twin_context else 'UNBOUND',
                'historical_reference_only':True,'alignment_verified':False,'physical_authority':False}
            try:
                self._state['twin_collection_binding']['record_sha256']=self._reserve_twin_collection_reference(
                    self._state['twin_collection_binding'])
                self._persist()
            except OSError as error:
                self._state['status'] = 'LOCAL_RECORD_UNREADABLE'
                raise BrokerError('readiness_storage_failed', 'Could not reserve a durable collection record', status=409) from error
            diagnostics=getattr(self,'execution_diagnostics',None)
            trace=diagnostics.begin('stationary_evidence_collection',durable=False,request_id=request_id,
                evidence_kind='robot_readiness_report',evidence_id=request_id) if diagnostics else None
            self._thread = Thread(target=self._execute,args=(trace,), daemon=True, name='TwinPulseNoMotionCollection')
            self._thread.start()
            return self.snapshot(owner)

    def clear_uncertain(self, owner, confirmed_powered_off, expires_at_ms):
        with self._lock:
            if (self._state['status'] not in {'REMOTE_STATE_UNKNOWN', 'LOCAL_RECORD_UNREADABLE'}
                    or confirmed_powered_off is not True or type(expires_at_ms) not in (int, float)
                    or not 0 < expires_at_ms - self._wall() <= 2000):
                raise BrokerError('readiness_clear_denied', 'Fresh robot-OFF confirmation is required for an uncertain job', status=409)
            if self._thread and self._thread.is_alive():
                raise BrokerError('readiness_busy_or_uncertain', 'Owned collector is still running', status=409)
            self._state = {**self._state, 'status': 'CLEARED_AFTER_OPERATOR_OFF',
                           'owner': owner, 'demo_ready': False, 'motion_authorized': False}
            try:
                self._persist()
            except OSError as error:
                raise BrokerError('readiness_storage_failed', 'Could not save the OFF confirmation', status=409) from error
            return self.snapshot(owner)

    def _run_cli(self):
        from .runtime_paths import script_command
        command = script_command(self.root, 'robot-readiness') + ['--run']
        from .robot_adapters import require_adapter
        endpoint=require_adapter(self._job_binding,operation='preparation')
        command+=['--host',endpoint.host,'--user',endpoint.user,'--port',str(endpoint.port),
                  '--domain-id',str(endpoint.ros_domain_id)]
        if self.archive_root != self.root:
            command += ['--output-root', str(self.archive_root / 'artifacts')]
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=600, check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        output = completed.stdout[:65536].decode('utf-8', errors='replace')
        paths = [line.removeprefix('Report: ').strip() for line in output.splitlines()
                 if line.startswith('Report: ')]
        if len(paths) != 1:
            raise ValueError('READINESS_REPORT_MISSING_OR_AMBIGUOUS')
        page = Path(paths[0]).resolve()
        expected = (self.archive_root / 'artifacts/robot-readiness').resolve()
        if not page.is_relative_to(expected) or page.name != 'report.html':
            raise ValueError('READINESS_REPORT_OUTSIDE_ROOT')
        report = page.with_name('report.json')
        if report.is_symlink() or report.stat().st_size > 1024 * 1024:
            raise ValueError('READINESS_REPORT_UNSAFE')
        result = json.loads(report.read_text(encoding='utf-8'))
        if 'pc_endpoint' in result and result['pc_endpoint']!=self._job_binding['endpoint']:
            raise ValueError('READINESS_REPORT_ENDPOINT_CHANGED')
        if (result.get('schema_version') != 'robot-readiness-1.0' or result.get('run_requested') is not True
                or result.get('motion_authorized') is not False or result.get('demo_ready') is not False):
            raise ValueError('READINESS_REPORT_CONTRACT_INVALID')
        return result, str(report), completed.returncode

    def _saved_stationary_report(self):
        step=((self._state.get('result') or {}).get('steps') or {}).get('stationary_collection') or {}
        value=step.get('report_path')
        if not isinstance(value,str):raise ValueError('STATIONARY_REPORT_UNAVAILABLE')
        path=Path(value)
        resolved=path.resolve(strict=True)
        report_root=self._report_root(resolved)
        base=report_root/'artifacts/robot-preparation'
        parts=resolved.relative_to(base.resolve()).parts
        if (len(parts)!=3 or not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}',parts[0])
                or parts[1:]!=('result','report.json') or not resolved.is_relative_to(report_root)
                or any(p.is_symlink() for p in (report_root/'artifacts',base,path.parent.parent,path.parent,path))
                or resolved.stat().st_size>16*1024*1024):raise ValueError('STATIONARY_REPORT_PATH_INVALID')
        report=json.loads(resolved.read_text(encoding='utf-8'))
        from .robot_adapters import legacy_binding,require_adapter
        endpoint=require_adapter(self._job_binding,operation='transfer')
        saved_endpoint=report.get('pc_endpoint',legacy_binding()['endpoint'])
        if saved_endpoint!={'host':endpoint.host,'user':endpoint.user,'port':endpoint.port,'ros_domain_id':endpoint.ros_domain_id}:
            raise ValueError('STATIONARY_REPORT_ENDPOINT_CHANGED')
        if (report.get('schema_version')!='robot-prepare-1.0' or report.get('action')!='stationary'
                or report.get('motion_authorized') is not False
                or report.get('status') not in {'STATIONARY_CHECK_PASS','EVIDENCE_EXPORT_INCOMPLETE'}
                or any(not isinstance(report.get(k),str) or not report[k] for k in ('run_id','boot_id','release_id'))):
            raise ValueError('STATIONARY_REPORT_INVALID')
        return resolved,hashlib.sha256(resolved.read_bytes()).hexdigest(),report['run_id']

    def can_resume(self):
        with self._lock:
            try:self._saved_stationary_report()
            except (OSError,ValueError,TypeError,AttributeError):return False
            return True

    def resume_evidence(self,owner,job_id,request_id,expires_at_ms):
        with self._lock:
            if self._closed:raise BrokerError('readiness_closed','Readiness service is closed',status=409)
            if (not isinstance(job_id,str) or job_id!=self._state['job_id']
                    or not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id)
                    or type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-self._wall()<=2000):
                raise BrokerError('readiness_transfer_binding','Fresh transfer request for the current saved collection required',status=409)
            requests=self._state['transfer_requests']
            if request_id in requests:
                if requests[request_id]!=job_id:raise BrokerError('readiness_transfer_reused','Transfer request was consumed',status=409)
                return self.snapshot(owner)
            if self._thread and self._thread.is_alive() or self._resume_thread and self._resume_thread.is_alive():
                raise BrokerError('readiness_transfer_busy','Collection or transfer is still running',status=409)
            if len(requests)>=128:raise BrokerError('readiness_transfer_limit','Transfer request budget reached',status=409)
            try:path,digest,run_id=self._saved_stationary_report()
            except (OSError,ValueError,TypeError,AttributeError) as error:
                raise BrokerError('readiness_transfer_report_invalid','Saved stationary report cannot be safely resumed',status=409) from error
            requests[request_id]=job_id
            self._state['evidence_recovery']={'status':'TRANSFERRING','transfer_only':True,'job_id':job_id,
                'request_id':request_id,'run_id':run_id,'source_sha256':digest,'reason':None}
            try:self._persist()
            except OSError as error:
                self._state['evidence_recovery'].update(status='INCOMPLETE',reason='TRANSFER_RESERVATION_SAVE_FAILED')
                raise BrokerError('readiness_storage_failed','Transfer was not started; reservation could not be saved',status=409) from error
            self._resume_thread=Thread(target=self._resume_execute,args=(path,digest,run_id),daemon=True,name='TwinPulseStationaryTransfer')
            self._resume_thread.start()
            return self.snapshot(owner)

    def _run_resume_cli(self,path):
        # The existing transfer-only CLI validates/caches each file. No run,
        # preparation, driver, torque or movement flags are supplied here.
        from .runtime_paths import script_command
        command=script_command(self.root, 'robot-prepare') + [
            '--mode','resume-evidence','--saved-report',str(path)]
        from .robot_adapters import require_adapter
        endpoint=require_adapter(self._job_binding,operation='transfer')
        command+=['--host',endpoint.host,'--user',endpoint.user,'--port',str(endpoint.port),
                  '--domain-id',str(endpoint.ros_domain_id)]
        if self._report_root(path) != self.root:
            command += ['--output-root',str(self._report_root(path)/'artifacts')]
        completed=subprocess.run(command,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240,check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        receipt_path=path.parent.parent/'robot-evidence/export.json'
        if (receipt_path.parent.is_symlink() or receipt_path.is_symlink() or receipt_path.stat().st_size>1024*1024):
            raise ValueError('TRANSFER_RECEIPT_UNSAFE')
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if completed.returncode!=(0 if receipt.get('status')=='COMPLETE' else 2):raise ValueError('TRANSFER_EXIT_CONFLICT')
        return receipt

    def _resume_execute(self,path,digest,run_id):
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('TRANSFER_SOURCE_CHANGED')
            receipt=self._resume_runner(path)
            if (hashlib.sha256(path.read_bytes()).hexdigest()!=digest
                    or receipt.get('schema_version')!='robot-evidence-export-1' or receipt.get('run_id')!=run_id
                    or receipt.get('status') not in {'COMPLETE','INCOMPLETE'}):raise ValueError('TRANSFER_RECEIPT_BINDING_INVALID')
            if receipt['status']=='COMPLETE' and (receipt.get('report_binding',{}).get('status')!='VERIFIED_SAME_RUN'
                    or receipt.get('raw_replay',{}).get('status')!='VERIFIED_OFFLINE'
                    or not receipt.get('files') or any(item.get('status')!='COPIED' for item in receipt['files'].values())):
                raise ValueError('TRANSFER_COMPLETE_UNVERIFIED')
            with self._lock:
                self._state['evidence_recovery'].update(status=receipt['status'],reason=None,
                    files=receipt.get('files'),report_binding=receipt.get('report_binding'),raw_replay=receipt.get('raw_replay'))
                self._persist()
        except Exception as error:
            with self._lock:
                self._state['evidence_recovery'].update(status='INCOMPLETE',reason=type(error).__name__+':'+str(error)[:120])
                try:self._persist()
                except OSError:self._state['evidence_recovery']['reason']='TRANSFER_RESULT_SAVE_FAILED'

    def _execute(self,trace=None):
        try:
            return self._execute_impl()
        finally:
            if trace:
                with self._lock:state=deepcopy(self._state)
                outcome=state['status'];result=state.get('result') or {}
                status='succeeded' if outcome=='COLLECTED_UNALIGNED' else 'unknown' if outcome=='REMOTE_STATE_UNKNOWN' else 'failed'
                trace.finish(status,error_code=result.get('status') if status!='succeeded' else None)

    def _execute_impl(self):
        try:
            result, path, exit_code = self._runner()
            if (not isinstance(result, dict) or result.get('schema_version') != 'robot-readiness-1.0'
                    or result.get('run_requested') is not True or result.get('motion_authorized') is not False
                    or result.get('demo_ready') is not False):
                raise ValueError('READINESS_REPORT_CONTRACT_INVALID')
            if (result.get('status') == 'NO_MOTION_COLLECTION_COMPLETE' and exit_code != 0
                    or result.get('status') == 'EVIDENCE_GAPS' and exit_code != 2):
                raise ValueError('READINESS_REPORT_EXIT_STATUS_CONFLICT')
            transfer_only_gap=(result.get('status')=='STOPPED_AT_STATIONARY_COLLECTION'
                and result.get('stationary_status')=='STATIONARY_CHECK_PASS'
                and (result.get('evidence_export') or {}).get('status')=='INCOMPLETE')
            status = 'BLOCKED_LOCAL' if result.get('status')=='STOPPED_AT_OFFLINE_PREFLIGHT' else 'COMPLETED_WITH_GAPS' if result.get('status') == 'EVIDENCE_GAPS' or transfer_only_gap else (
                'COLLECTED_UNALIGNED' if result.get('status') == 'NO_MOTION_COLLECTION_COMPLETE' else 'REMOTE_STATE_UNKNOWN')
            with self._lock:
                self._state.update(status=status, result=result, report_path=path,
                                   exit_code=exit_code, finished_at_utc=datetime.now(timezone.utc).isoformat())
                # The per-job reference survives the next collection. Link its
                # terminal original report by exact bytes without rewriting it.
                binding=self._state.get('twin_collection_binding')
                if binding:
                    try:
                        if self._bounded_saved_report(path,'robot-readiness',('report.json',))!=result:
                            raise ValueError('READINESS_TWIN_REPORT_CHANGED')
                        digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
                        receipt=dict(schema_version='stationary-twin-receipt-1.0',job_id=self._state['job_id'],
                            start_reference_sha256=binding['record_sha256'],readiness_report_path=path,
                            readiness_report_sha256=digest,historical_reference_only=True,
                            alignment_verified=False,physical_authority=False)
                        self._state['twin_collection_receipt']={'status':'RECORDED',
                            'record_sha256':self._reserve_twin_collection_reference(receipt,suffix='.result')}
                    except (OSError,ValueError,TypeError,KeyError) as reference_error:
                        # Keep the original remote outcome and report. Missing
                        # provenance is not alignment or permission to retry.
                        self._state['twin_collection_receipt']={'status':'UNAVAILABLE',
                            'reason':str(reference_error)[:160]}
                self._persist()
        except Exception as error:
            with self._lock:
                self._state.update(status='REMOTE_STATE_UNKNOWN',
                                   result={'status': type(error).__name__, 'reason': str(error)[:160],
                                           'demo_ready': False, 'motion_authorized': False},
                                   finished_at_utc=datetime.now(timezone.utc).isoformat())
                try:
                    self._persist()
                except OSError:
                    self._state['status'] = 'LOCAL_RECORD_UNREADABLE'

    def close(self):
        with self._lock:
            self._closed = True
