# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Chat adapter over the existing diagnostics and fixed qualification worker.

No transport runs on construction, snapshot, history restore or confirmation.
An explicit robot choice starts one read-only check; an explicit qualification
choice starts one bounded trial. Uploaded reports/chat history never grant a
physical mission. The robot-local worker still makes its own admission checks.
"""
from copy import deepcopy
from contextlib import nullcontext
import hashlib
import json
import re
from threading import Event, RLock, Thread
import time
from uuid import uuid4

from .command_broker import BrokerError


class ChatRobotPreparation:
    def __init__(self, diagnostics, controller, readiness, start_lock, context,
                 *, clock=time.monotonic, wall=lambda: time.time()*1000):
        self.diagnostics, self.controller, self.readiness = diagnostics, controller, readiness
        self.start_lock, self.context = start_lock, context
        self.clock, self.wall = clock, wall
        self.lock, self.cancelled = RLock(), Event()
        self.thread = None
        self.execution_diagnostics = None
        self.closed = False
        self.owner = None
        self.checked_at = None
        self.problem_identity = None
        self._state = {'state':'NOT_STARTED', 'attempt_id':None, 'binding':None,
                       'stage':'NOT_STARTED', 'code':None, 'record':None,
                       'trial':None, 'job_id':None, 'observed_confirmation':None,
                       'physical_authority':False, 'demo_ready':False}

    def _busy(self):
        return bool(self.thread and self.thread.is_alive())

    def _available(self):
        if self.closed or not self.diagnostics or not self.controller:
            raise BrokerError('chat_robot_unavailable', 'Physical preparation is unavailable in this backend/project.', status=409)

    def _independent_busy(self,*,owned_idle=False,read_only=False):
        getattr(self,'scene_edit_guard',lambda:None)()
        if getattr(self,'external_busy',lambda:False)():
            raise BrokerError('robot_operation_busy','A survey or mission is active.',status=409)
        readiness_check=(getattr(self.readiness,'blocks_read_only_observation',self.readiness.blocks_robot_operation)
                         if self.readiness and read_only else self.readiness.blocks_robot_operation if self.readiness else None)
        if readiness_check and readiness_check():
            raise BrokerError('readiness_busy_or_uncertain', 'Stationary collection is active or uncertain.', status=409)
        if self.diagnostics._running() or self.controller.snapshot(self.owner)['busy'] and not owned_idle:
            raise BrokerError('robot_operation_busy', 'Another robot operation is active. It will not be interrupted.', status=409)
        recovery=self.controller.snapshot(self.owner).get('evidence_recovery') or {}
        recovery_thread=getattr(getattr(self.controller,'evidence_recovery',None),'thread',None)
        if recovery.get('status') in {'RUNNING','TRANSFERRING'} or recovery_thread and recovery_thread.is_alive():
            raise BrokerError('evidence_recovery_busy','A raw transfer is still running.',status=409)

    def collect(self,owner,expires_at_ms,confirmed):
        with self.start_lock,self.lock:
            self._available()
            if self.readiness is None:raise BrokerError('readiness_unavailable','Stationary collector is not configured.',status=409)
            if confirmed is not True or self._busy():raise BrokerError('chat_collection_unavailable','Explicit stationary source-transfer approval is required; wait for active preparation.',status=409)
            self._independent_busy()
            job=uuid4().hex
            result=self.readiness.start(owner,job,confirmed,expires_at_ms,app_context=self.context(),
                project_id=getattr(self, 'project_id', 'default'),
                **({'twin_context':self.capture_twin_context()} if hasattr(self,'capture_twin_context') else {}))
            # Collection can transfer reviewed source. Old qualification/link
            # cannot remain current while that independent operation runs.
            self.owner=owner
            self.checked_at=None
            self._state.update(state='COLLECTING',stage='STATIONARY_COLLECTION',code=None,
                attempt_id=uuid4().hex,binding=None,record=None,trial=None,job_id=None,observed_confirmation=None)
            return result

    def resume_evidence(self,owner,kind,job_id,expires_at_ms):
        with self.start_lock,self.lock:
            getattr(self,'scene_edit_guard',lambda:None)()
            self._available()
            if (type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-self.wall()<=2000):
                raise BrokerError('evidence_transfer_expired','A fresh transfer-only click is required.',status=409)
            if self._busy() or self.diagnostics._running() or self.controller.snapshot(owner)['busy']:
                raise BrokerError('robot_operation_busy','Wait for the active operation before transferring saved files.',status=409)
            if kind=='stationary':
                if not self.readiness:raise BrokerError('readiness_unavailable','Stationary collector is not configured.',status=409)
                recovery=self.controller.snapshot(owner).get('evidence_recovery') or {}
                recovery_thread=getattr(getattr(self.controller,'evidence_recovery',None),'thread',None)
                if recovery.get('status') in {'RUNNING','TRANSFERRING'} or recovery_thread and recovery_thread.is_alive():raise BrokerError('evidence_recovery_busy','Raw transfer is already running.',status=409)
                return self.readiness.resume_evidence(owner,job_id,uuid4().hex,expires_at_ms)
            if kind!='qualification' or not job_id or job_id!=self._state.get('job_id') or owner!=self.owner:
                raise BrokerError('evidence_transfer_binding','Transfer must refer to this owned saved qualification.',status=409)
            if self.readiness and self.readiness.blocks_robot_operation():raise BrokerError('readiness_busy_or_uncertain','Stationary collection is active or uncertain.',status=409)
            return self.controller.resume_evidence(owner,job_id,uuid4().hex)

    def _collection_view(self,owner):
        if not self.readiness:return None
        saved=self.readiness.snapshot(owner)
        result=saved.get('result') or {}
        steps=result.get('steps') or {}
        rows=[]
        for key in ('offline_collection_preflight','source_and_idle','stationary_collection','evidence_review'):
            item=steps.get(key) or {}
            rows.append({'id':key,'status':item.get('status','NOT_RUN'),'reason':item.get('reason')})
        evidence=result.get('evidence') or {}
        sources=[]
        for key in ('odom','scan','tf','tf_static'):
            item=evidence.get(key) or {}
            sources.append({'id':key,'status':item.get('status','NOT_RECORDED'),'reason':item.get('reason'),
                            'fault_counts':item.get('fault_counts') or {}})
        stationary=steps.get('stationary_collection') or {}
        return {'status':saved['status'],'job_id':saved.get('job_id'),'owned':saved.get('owned',False),
            'result_code':result.get('status'),'reason':result.get('reason'),
            'steps':rows,'sources':sources,'raw_export':result.get('evidence_export'),
            'recovery':saved.get('evidence_recovery'),
            'resume_available':bool(stationary.get('report_path') and stationary.get('status') in {'STATIONARY_CHECK_PASS','EVIDENCE_EXPORT_INCOMPLETE'}),
            'motion_authorized':False,'alignment_verified':False,'demo_ready':False}

    def _set(self, **values):
        with self.lock:
            self._state.update(values)

    def check(self, owner, *, correlation=None):
        with self.start_lock, self.lock:
            self._available()
            if self._busy():
                raise BrokerError('chat_robot_busy', 'Preparation is still running.', status=409)
            self._independent_busy(read_only=True)
            self.owner = owner
            self.checked_at = None
            self.cancelled.clear()
            self._state.update(state='CHECKING', stage='PC_PREFLIGHT', code=None,
                attempt_id=uuid4().hex, binding=None, record=None, trial=None,
                job_id=None, observed_confirmation=None)
            for key in ('missing','error_type','cleanup_error','cleanup_confirmed'):
                self._state.pop(key,None)
            trace=self.execution_diagnostics.begin('robot_read_only_preparation',durable=False,
                attempt_id=self._state['attempt_id'],**(correlation or {})) if self.execution_diagnostics else None
            self.thread = Thread(target=self._check,args=(None,trace), daemon=True, name='ChatRobotReadOnly')
            self.thread.start()

    def _check(self, expected_idle_identity=None,trace=None):
        try:
            return self._check_impl(expected_idle_identity)
        finally:
            if trace:
                with self.lock:state=deepcopy(self._state)
                record=state.get('record') or {}
                trace.bind(boot_id=record.get('boot_id'),release_id=record.get('release_id'))
                if state.get('state')=='BLOCKED':
                    trace.child(state.get('stage') or 'robot_preparation').finish('failed',
                        error_code=state.get('code'),error_type=state.get('error_type'))
                trace.finish('failed' if state.get('state')=='BLOCKED' else 'cancelled' if state.get('state')=='STOPPED' else
                    'succeeded' if state.get('state') in {'AWAITING_QUALIFICATION','AWAITING_OBSERVATION','LINKED'} else 'unknown')

    def _check_impl(self, expected_idle_identity=None):
        try:
            with self.start_lock:
                if self.cancelled.is_set(): return self._set(state='STOPPED', code='CANCELLED')
                self._independent_busy(read_only=True)
                prepared = self.diagnostics.preflight(self.owner)
                if not prepared['pc']['ready']:
                    failed = [c['id'] for c in prepared['pc']['checks'] if not c['ok']]
                    return self._set(state='BLOCKED', stage='PC_PREFLIGHT', code='PC_PREREQUISITES_MISSING', missing=failed)
                self.diagnostics.start(self.owner, prepared['start_token'], True)
            self._set(stage='READ_ONLY_CONNECTION')
            deadline = self.clock()+130
            while self.diagnostics._running():
                if self.clock() >= deadline:
                    return self._set(state='BLOCKED', code='READ_ONLY_RESULT_TIMEOUT')
                # A bounded read cannot be converted to motor/sensor/deploy work.
                self.cancelled.wait(.1)
                if self.cancelled.is_set(): return self._set(state='STOPPED', code='CANCELLED')
            result = self.diagnostics.snapshot(self.owner)
            job, record = result.get('job') or {}, result.get('record')
            code = (job.get('diagnostic') or {}).get('code') or job.get('result_code') or 'READ_ONLY_RESULT_MISSING'
            if expected_idle_identity is not None:
                if not record or (record.get('boot_id'),record.get('release_id')) != expected_idle_identity:
                    return self._set(state='BLOCKED',stage='POST_INITIALIZATION_CHECK',
                                     code='INITIALIZATION_IDENTITY_CHANGED',record=record,binding=None)
                if code!='OBSERVATION_RECEIVED' or (record.get('board_observation') or {}).get('torque_enabled') is not False:
                    return self._set(state='BLOCKED',stage='POST_INITIALIZATION_CHECK',
                                     code='MOTOR_OFF_NOT_CONFIRMED',record=record,binding=None)
            if (job.get('status')=='COMPLETED' and job.get('saved') and code=='OBSERVATION_NEEDS_ATTENTION'
                    and record and record.get('idle_failure_reasons')==['TORQUE_ENABLED']
                    and record.get('age_seconds',121)<=120 and record.get('release_id')==result.get('local_release_id')
                    and record.get('guard_artifact_verified_at_observation') is True
                    and record.get('battery') and record['battery'].get('near_protection_at_observation') is False
                    and record['battery'].get('charge_requested_at_observation') is False):
                self.checked_at=self.clock()
                binding=hashlib.sha256(json.dumps({'attempt_id':self._state['attempt_id'],
                    'boot_id':record['boot_id'],'release_id':record['release_id'],
                    'report_sha256':record['report_sha256']},sort_keys=True).encode()).hexdigest()
                return self._set(state='BLOCKED',stage='INITIAL_STATE',code='TORQUE_ENABLED_INITIALIZATION_REQUIRED',
                                 record=record,binding=binding)
            if job.get('status') != 'COMPLETED' or code != 'OBSERVATION_RECEIVED' or not job.get('saved'):
                return self._set(state='BLOCKED', stage='READ_ONLY_CONNECTION', code=code, record=record)
            self.checked_at = self.clock()
            local = result.get('local_release_id')
            if not record or not local or record.get('release_id') != local:
                return self._set(state='BLOCKED', stage='RELEASE_IDENTITY', code='REVIEWED_RELEASE_MISMATCH', record=record)
            if (record.get('age_seconds',121)>120 or record.get('idle_at_observation') is not True
                    or record.get('guard_artifact_verified_at_observation') is not True
                    or not record.get('battery') or record['battery'].get('near_protection_at_observation') is not False
                    or record['battery'].get('charge_requested_at_observation') is not False):
                return self._set(state='BLOCKED', stage='BOARD_AND_BATTERY', code='FRESH_IDLE_BATTERY_EVIDENCE_REQUIRED', record=record)
            if self.problem_identity==(record['boot_id'],local):
                return self._set(state='BLOCKED',stage='OPERATOR_OBSERVATION',code='OPERATOR_REPORTED_PROBLEM',record=record)
            material = {'attempt_id':self._state['attempt_id'], 'boot_id':record['boot_id'],
                        'release_id':local, 'report_sha256':record['report_sha256']}
            binding = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
            trial = self.controller.snapshot(self.owner).get('last_trial')
            if self._matching_trial(trial, record):
                if self._passing(trial):
                    return self._set(state='AWAITING_OBSERVATION', stage='CURRENT_STOP_RECORD',
                        code='CURRENT_STOP_RECORD_FOUND', record=record, trial=trial, binding=binding)
                return self._set(state='BLOCKED', stage='STOP_QUALIFICATION', code='CURRENT_STOP_RECORD_FAILED',
                                 record=record, trial=trial, binding=binding)
            self._set(state='AWAITING_QUALIFICATION', stage='STOP_QUALIFICATION',
                      code='ONE_TRIAL_REQUIRED', record=record, binding=binding)
        except BrokerError as error:
            self._set(state='BLOCKED', code=error.code)
        except Exception as error:
            self._set(state='BLOCKED', code='READ_ONLY_ADAPTER_FAILED', error_type=type(error).__name__)

    @staticmethod
    def _matching_trial(trial, record):
        return bool(trial and record and trial.get('boot_id') == record.get('boot_id')
                    and trial.get('release_id') == record.get('release_id'))

    @staticmethod
    def _passing(trial):
        return bool(trial and trial.get('status') == 'QUALIFIED' and trial.get('cleanup_confirmed') is True
                    and (trial.get('stop_assessment') or {}).get('status') == 'PASS')

    def _fresh(self, owner, binding):
        self._available()
        if owner != self.owner or not binding or binding != self._state['binding']:
            raise BrokerError('chat_robot_binding_stale', 'This robot preparation belongs to another attempt/session.', status=409)
        if self.checked_at is None or self.clock()-self.checked_at > 120:
            raise BrokerError('chat_robot_observation_expired', 'Robot observation expired. Request a fresh read-only check.', status=409)
        current = self.diagnostics.snapshot(owner)
        record = current.get('record')
        if ((current.get('job') or {}).get('status') != 'COMPLETED' or not record
                or any(record.get(k) != self._state['record'].get(k) for k in ('boot_id','release_id','report_sha256'))
                or current.get('local_release_id') != record.get('release_id')):
            raise BrokerError('chat_robot_identity_changed', 'Boot, release or observation changed. Old choices cannot run.', status=409)
        if self._state['state'] in {'AWAITING_OBSERVATION','LINKED'} and self.controller.snapshot(owner).get('last_trial') != self._state['trial']:
            raise BrokerError('chat_robot_trial_changed', 'The current stop record changed. This old link is unavailable.',status=409)

    def qualify(self, owner, binding, expires_at_ms):
        with self.start_lock, self.lock:
            self._fresh(owner, binding)
            if (type(expires_at_ms) not in (int,float) or not 0 < expires_at_ms-self.wall() <= 2000):
                raise BrokerError('physical_start_expired', 'A fresh qualification click is required.', status=409)
            if self._busy() or self._state['state'] != 'AWAITING_QUALIFICATION':
                raise BrokerError('chat_robot_trial_unavailable', 'This one trial is no longer available.', status=409)
            self._independent_busy()
            job = uuid4().hex
            self._set(state='QUALIFYING', stage='ROBOT_LOCAL_PREFLIGHT', code=None, job_id=job)
            # Only this fixed bounded operation is admitted. No direction input,
            # transfer, auto-install or source hash override exists here.
            try:self.controller.start(owner, 'qualify', job, True, app_context=self.context())
            except BrokerError as error:
                self._set(state='BLOCKED',code=error.code)
                raise
            except Exception as error:
                self._set(state='BLOCKED',code='QUALIFICATION_START_FAILED',error_type=type(error).__name__)
                raise BrokerError('qualification_start_failed','Qualification worker failed to start; inspect its saved result before another operation.',status=503) from error
            self.thread = Thread(target=self._qualify, daemon=True, name='ChatRobotQualification')
            self.thread.start()

    def _qualify(self):
        sent = False
        cancel_cleanup_deadline = None
        deadline = self.clock()+135
        try:
            while True:
                state = self.controller.snapshot(self.owner)
                if state.get('job_id') != self._state['job_id'] or not state.get('owned'):
                    raise BrokerError('chat_robot_worker_changed', 'Qualification worker ownership changed.', status=409)
                if not state['busy']: break
                if self.cancelled.is_set():
                    # Stop already sent the selected finish_stop/force_stop.
                    # Do not upgrade an ordinary Stop to Force STOP, or send
                    # further watch inputs while the worker finishes cleanup.
                    if cancel_cleanup_deadline is None:cancel_cleanup_deadline=self.clock()+20
                    if self.clock()>=cancel_cleanup_deadline:
                        return self._set(state='STOPPED',stage='OPERATOR_STOP',code='STOP_CLEANUP_UNCONFIRMED',
                            cleanup_confirmed=False,cleanup_error=state.get('cleanup_error'))
                    time.sleep(.1)
                    continue
                if self.clock() >= deadline:
                    self._safe_stop()
                    return self._set(state='STOPPED', code='TRIAL_TIMEOUT',cleanup_confirmed=False)
                if state.get('state') in {'FINISHED','STOPPING','FAILED','CONNECTION_LOST','REJECTED'}:
                    # busy means the PC worker/journal/export is still alive,
                    # not permission to send another input after a terminal
                    # robot receipt or an already requested stop. Preserve the
                    # exact final result and wait within the original budget.
                    self.cancelled.wait(.1)
                    continue
                with getattr(self.controller,'lock',nullcontext()):
                    state=self.controller.snapshot(self.owner)
                    if self.cancelled.is_set():continue
                    if not state['busy']:continue
                    if state.get('state') in {'FINISHED','STOPPING','FAILED','CONNECTION_LOST','REJECTED'}:continue
                    if state['state'] == 'READY' and not sent:
                        self.controller.input(self.owner, state['job_id'], state['sequence']+1, 'qualify', self.wall()+250)
                        sent = True
                    else:
                        self.controller.input(self.owner, state['job_id'], state['sequence']+1, 'watch', self.wall()+250)
                if sent:self._set(stage='BOUNDED_FORWARD_AND_STOP')
                self.cancelled.wait(.1)
            trial = state.get('last_trial')
            if self.cancelled.is_set():
                return self._set(state='STOPPED',stage='OPERATOR_STOP',code='OPERATOR_CANCELLED',
                    cleanup_confirmed=state.get('cleanup_confirmed') is True,cleanup_error=state.get('cleanup_error'))
            valid = (sent and state.get('result') == 'QUALIFIED' and state.get('cleanup_confirmed') is True
                     and trial and trial.get('job_id') == self._state['job_id']
                     and self._matching_trial(trial, self._state['record']) and self._passing(trial))
            self._set(state='AWAITING_OBSERVATION' if valid else 'BLOCKED',
                stage='STOP_QUALIFICATION', trial=trial,
                code='TRIAL_PASSED' if valid else state.get('reason') or state.get('result') or state.get('state'),
                cleanup_error=state.get('cleanup_error'), cleanup_confirmed=state.get('cleanup_confirmed') is True)
        except BrokerError as error:
            if self.cancelled.is_set():
                return self._set(state='STOPPED',stage='OPERATOR_STOP',code='OPERATOR_CANCELLED',
                                 cleanup_confirmed=False)
            self._safe_stop()
            self._set(state='BLOCKED', code=error.code)
        except Exception as error:
            self._safe_stop()
            self._set(state='BLOCKED', code='QUALIFICATION_ADAPTER_FAILED', error_type=type(error).__name__)

    def initialize(self,owner,binding,expires_at_ms):
        """Explicit one-shot approval of existing reviewed prepare/Motor OFF, never driving."""
        with self.start_lock,self.lock:
            self._fresh(owner,binding)
            if self._state['code']!='TORQUE_ENABLED_INITIALIZATION_REQUIRED' or self._busy():
                raise BrokerError('initialization_unavailable','This initial-state approval is no longer current.',status=409)
            if type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-self.wall()<=2000:
                raise BrokerError('physical_start_expired','A fresh initial-state approval is required.',status=409)
            self._independent_busy()
            job=uuid4().hex
            self.cancelled.clear()
            self._set(state='INITIALIZING',stage='REVIEWED_SOURCE_AND_MOTOR_OFF',code=None,job_id=job)
            try:self.controller.start(owner,'prepare',job,True,app_context=self.context())
            except Exception:
                self._set(state='BLOCKED',code='INITIALIZATION_START_FAILED')
                raise
            self.thread=Thread(target=self._initialize,daemon=True,name='ChatRobotInitialState')
            self.thread.start()

    def _initialize(self):
        deadline=self.clock()+350
        expected_identity=(self._state['record']['boot_id'],self._state['record']['release_id'])
        try:
            while True:
                state=self.controller.snapshot(self.owner)
                if not state.get('owned') or state.get('job_id')!=self._state['job_id']:
                    raise BrokerError('initialization_worker_changed','Initial-state worker changed.',status=409)
                if self.cancelled.is_set():return self._set(state='STOPPED',code='OPERATOR_CANCELLED')
                if not state['busy']:break
                if self.clock()>=deadline:
                    self._safe_stop()
                    return self._set(state='BLOCKED',code='INITIALIZATION_TIMEOUT',cleanup_confirmed=False)
                self.cancelled.wait(.1)
            if state.get('result')!='PREPARED':
                return self._set(state='BLOCKED',code=state.get('reason') or 'INITIALIZATION_FAILED')
            # Process exit alone never proves idle or authorizes motion. Obtain
            # a new read-only boot/release/board snapshot before qualification.
            self._set(state='CHECKING',stage='POST_INITIALIZATION_CHECK',code=None,job_id=None)
            self._check(expected_idle_identity=expected_identity)
        except BrokerError as error:
            self._set(state='BLOCKED',stage='INITIAL_STATE',code=error.code,error_type=type(error).__name__)
        except Exception as error:
            self._set(state='BLOCKED',stage='INITIAL_STATE',code='INITIALIZATION_ADAPTER_FAILED',error_type=type(error).__name__)

    def _safe_stop(self):
        try:self.stop(self.owner,force=True)
        except Exception as error:
            self._set(cleanup_error='STOP_REQUEST_FAILED',cleanup_error_type=type(error).__name__)

    def observe(self, owner, binding, ok):
        with self.lock:
            self._fresh(owner, binding)
            if self._state['state'] != 'AWAITING_OBSERVATION':
                raise BrokerError('chat_robot_observation_unavailable', 'No current passing qualification awaits observation.', status=409)
            trial = self.controller.snapshot(owner).get('last_trial')
            if trial != self._state['trial'] or not self._passing(trial):
                raise BrokerError('chat_robot_trial_changed', 'Qualification changed; the old confirmation is unavailable.', status=409)
            self._set(state='LINKED' if ok else 'BLOCKED', stage='OPERATOR_OBSERVATION',
                      code='LINK_REVIEWED' if ok else 'OPERATOR_REPORTED_PROBLEM', observed_confirmation=bool(ok))
            if not ok:self.problem_identity=(self._state['record']['boot_id'],self._state['record']['release_id'])

    def stop(self, owner, *, force=False):
        # Independent of chat persistence, provider and renderer locks. A Stop
        # never starts an off/SSH job in the absence of an owned active worker.
        with self.lock:
            if owner == self.owner:self.cancelled.set()
        # Background trial keepalives share the same sequence. Reserve Stop's
        # sequence atomically with the existing controller lock, so an in-flight
        # watch cannot consume it and reject the safety request as old input.
        with getattr(self.controller,'lock',nullcontext()):
            state = self.controller.snapshot(owner) if self.controller else {}
            if state.get('busy') and state.get('owned'):
                return self.controller.input(owner, state['job_id'], state['sequence']+1,
                    'force_stop' if force else 'finish_stop', self.wall()+250)
        if owner == self.owner:self._set(state='STOPPED', code='NO_ACTIVE_MOTION_WORKER')
        return {'state':'NO_ACTIVE_MOTION_WORKER', 'stop_confirmed':False}

    def snapshot(self, owner):
        with self.lock:
            result = deepcopy(self._state)
            result['owned'] = bool(owner and owner == self.owner)
            result['available'] = bool(not self.closed and self.diagnostics and self.controller)
            if not result['available']:
                result.update(state='UNAVAILABLE',stage='BACKEND_CONFIGURATION',code='PHYSICAL_PREPARATION_NOT_CONFIGURED')
            result['transport'] = 'ACTUAL_ROBOT' if self.controller and self.controller.real_transport else 'OFFLINE_TEST_TRANSPORT'
            physical=self.controller.snapshot(owner) if self.controller else {}
            result['active_control']={'owned':physical.get('owned') is True,'busy':physical.get('busy') is True,
                'state':physical.get('state'), 'mode':physical.get('mode'),
                'cleanup_confirmed':physical.get('cleanup_confirmed') is True}
            result['evidence'] = None
            result['collection']=self._collection_view(owner)
            collection=result['collection']
            if result['owned'] and result['state']=='COLLECTING' and collection:
                if collection['status']!='RUNNING':
                    result.update(state='COLLECTION_RESULT',stage='STATIONARY_COLLECTION',code=collection['result_code'] or collection['status'])
            if result['owned'] and self.controller and result.get('job_id'):
                current=self.controller.snapshot(owner)
                if current.get('job_id')==result['job_id']:
                    # Preserve acquisition, save, transfer and cleanup outcomes
                    # separately. These observations never grant navigation.
                    result['evidence']={key:deepcopy(current.get(key)) for key in
                        ('session_log_complete','session_event_count','session_storage','evidence_export',
                         'evidence_export_error','evidence_recovery','report_saved','session_index_saved','cleanup_confirmed')}
            if result['owned'] and result['state'] in {'AWAITING_QUALIFICATION','AWAITING_OBSERVATION','LINKED'}:
                try:self._fresh(owner, result['binding'])
                except BrokerError as error:result.update(state='EXPIRED', code=error.code)
            if not result['owned']:
                result.update(binding=None, record=None, trial=None, job_id=None,evidence=None)
            return result

    def close(self):
        self._safe_stop()
        self.closed = True
        if self.thread:self.thread.join(timeout=2)
