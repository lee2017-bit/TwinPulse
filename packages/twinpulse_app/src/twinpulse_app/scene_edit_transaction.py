# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned Build/ACK/disk-commit journal over the existing scene-change sidecar.

Polling and reopening never dispatch a command. Only explicit Apply/recovery
uses the existing broker and its authenticated engine receipts.
"""
from copy import deepcopy
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
from threading import Event, RLock, Thread, get_ident
import time
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core import CommandReceipt
from .command_broker import BrokerError
from .scene_changes import SceneChange, SceneChangeHistory
from .scene_sensor_review import checked_sensor_binding


TERMINAL = {'COMMITTED', 'ROLLED_BACK', 'CANCELLED_BEFORE_DISPATCH'}
FEEDBACK_LINEAGE_FIELDS = frozenset({'feedback_execution_id','feedback_operation_id','feedback_request_id',
    'feedback_approval_id','feedback_response_sha256','feedback_context_sha256','feedback_preview_execution_id'})


def checked_feedback_lineage(value):
    """Bounded host-recorded provenance, not an edit or execution permission."""
    if value is None:return None
    if not isinstance(value,dict) or set(value)!=FEEDBACK_LINEAGE_FIELDS:
        raise ValueError('SCENE_FEEDBACK_LINEAGE_INVALID')
    for field,item in value.items():
        pattern=('[a-f0-9]{32}' if field in {'feedback_execution_id','feedback_preview_execution_id'} else
            '[a-f0-9]{64}' if field.endswith('_sha256') else '[A-Za-z0-9_.:/-]{1,160}')
        if field=='feedback_approval_id' and item is None:continue
        if not isinstance(item,str) or not re.fullmatch(pattern,item):raise ValueError('SCENE_FEEDBACK_LINEAGE_INVALID')
    return deepcopy(value)


class SceneEditTransaction:
    def __init__(self,workflow,*,timeout_s=125.):
        self.workflow=workflow;self.broker=workflow._broker
        self.path=workflow._application._project_store.path.with_suffix('.scene-edit-transaction.json')
        self.lock=RLock();self.worker=None;self.cancelled=Event();self.timeout_s=timeout_s
        # Separate operation ownership from the short state lock. Broker guards
        # never acquire this mutex. Polling does not wait behind an owned Build.
        self.ownership=RLock()
        self.admission=lambda owner:nullcontext()
        self.value=None;self.storage_error=None;self.trace=None
        self.dispatch_thread=None
        if self.path.exists():
            try:
                value=self._read()
                self._require_sensor_capabilities(value.get('sensor_binding'),value.get('sensor_origin_binding'))
                if value['state'] not in TERMINAL:
                    value.update(state='ENGINE_STATE_UNKNOWN',error='Interrupted transaction; reconcile the current engine before recovery.')
                self.value=value
                if value.get('execution_id'):
                    try:
                        from twinpulse_core.execution_diagnostics import TraceContext
                        diagnostics=self.workflow._application.diagnostics
                        detail=diagnostics.detail(value['execution_id'])
                        self.trace=TraceContext(diagnostics,value['execution_id'],detail['manifest']['root_span_id'])
                        self.trace.child('scene_edit_journal_reopen',transaction_state=value['state']).finish('unknown' if value['state'] not in TERMINAL else 'succeeded')
                    except Exception:
                        self.workflow._application.diagnostics.note_storage_error()
            except (OSError,ValueError,TypeError,KeyError) as error:
                self.storage_error=type(error).__name__

    def _require_sensor_capabilities(self,*bindings):
        if any(b and b.get('schema_version')=='environment-survey-binding-1.0' for b in bindings):
            from .release_contract import require_data_capability,project_runtime_root
            require_data_capability(project_runtime_root(self.workflow._application._project_store.path),
                'environment-survey-binding-1.0')

    def _read(self,path=None):
        path=path or self.path
        if path.is_symlink() or path.stat().st_size>4*1024*1024:
            raise ValueError('SCENE_TRANSACTION_PATH_INVALID')
        value=json.loads(path.read_text(encoding='utf-8'))
        keys={'schema_version','project_id','source_sha256','operation','preview_digest','before_history',
            'after_history','state','engine_session_id','stage_epoch','request_id','command_id','receipt',
            'compensation_command_id','compensation_receipt','error','sha256'}
        version=value.get('schema_version') if isinstance(value,dict) else None
        extended=version in {'scene-edit-transaction-1.1','scene-edit-transaction-1.2','scene-edit-transaction-1.3'}
        expected=keys|({'execution_id'} if extended else set())|({'feedback_lineage'} if version in {'scene-edit-transaction-1.2','scene-edit-transaction-1.3'} else set())|({'sensor_binding','sensor_origin_binding'} if version=='scene-edit-transaction-1.3' else set())
        if (not isinstance(value,dict) or set(value)!=expected or version not in {'scene-edit-transaction-1.0','scene-edit-transaction-1.1','scene-edit-transaction-1.2','scene-edit-transaction-1.3'}
                or value['project_id']!=self.broker.project_id or value['sha256']!=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
                or value['state'] not in TERMINAL|{'STAGED','BUILDING','ENGINE_ACKNOWLEDGED','COMPENSATING','ENGINE_STATE_UNKNOWN'}):
            raise ValueError('SCENE_TRANSACTION_INVALID')
        if extended and (not isinstance(value['execution_id'],str) or len(value['execution_id'])!=32 or
                any(c not in 'abcdef0123456789' for c in value['execution_id'])):
            raise ValueError('SCENE_TRANSACTION_DIAGNOSTIC_ID_INVALID')
        checked_feedback_lineage(value.get('feedback_lineage'))
        checked_sensor_binding(value.get('sensor_binding'))
        checked_sensor_binding(value.get('sensor_origin_binding'))
        source=self.workflow._application.site_draft
        if source is None or value['source_sha256']!=canonical_sha256(source.to_dict()):
            raise ValueError('SCENE_TRANSACTION_SOURCE_CHANGED')
        before=SceneChangeHistory.from_dict(value['before_history'],source,self.broker.project_id)
        after=SceneChangeHistory.from_dict(value['after_history'],source,self.broker.project_id)
        operation=SceneChange.from_dict(value['operation'])
        if before.append(source,operation)!=after or value['preview_digest']!=canonical_sha256(operation.to_dict()):
            raise ValueError('SCENE_TRANSACTION_CANDIDATE_CHANGED')
        for field,revision,command_field in (('receipt',after.current_scene_revision,'command_id'),
                ('compensation_receipt',before.current_scene_revision,'compensation_command_id')):
            if value[field] is not None:
                receipt=CommandReceipt.from_dict(value[field])
                if (receipt.command_id!=value[command_field] or receipt.project_id!=value['project_id'] or
                        receipt.engine_session_id!=value['engine_session_id'] or receipt.stage_epoch!=value['stage_epoch'] or
                        receipt.status!='succeeded' or receipt.applied_revision!=revision):
                    raise ValueError('SCENE_TRANSACTION_RECEIPT_INVALID')
        return value

    def _save(self,**fields):
        with self.lock:
            value={**self.value,**fields}
            value['sha256']=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.path.is_symlink():raise ValueError('SCENE_TRANSACTION_PATH_INVALID')
            temporary=self.path.with_name(self.path.name+'.tmp-'+uuid4().hex)
            try:
                with temporary.open('xb') as stream:
                    stream.write(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
                    stream.flush();os.fsync(stream.fileno())
                temporary.replace(self.path)
                self.value=value;self.storage_error=None
                if self.trace:self.trace.bind(transaction_state=value['state'],journal_sha256=value['sha256'],
                    command_id=value['command_id'],engine_session_id=value['engine_session_id'],stage_epoch=value['stage_epoch'],
                    persisted=True,automatic_retry=False)
            except Exception as error:
                self.storage_error=type(error).__name__
                raise
            finally:
                if temporary.exists():temporary.unlink()

    def locked(self):
        with self.lock:return bool(self.storage_error or self.value and self.value['state'] not in TERMINAL)

    def guard(self,command_type):
        if command_type in {'run','reset','build_scene','build_site_scene'} and self.locked() and self.dispatch_thread!=get_ident():
            raise BrokerError('engine_state_unknown','Scene transaction must be reconciled before geometry or execution.',status=409)

    def snapshot(self,owner=None):
        if self.storage_error:
            return dict(state='ENGINE_STATE_UNKNOWN',error='Scene transaction journal is unavailable.',storage_error=self.storage_error,physical_authority=False)
        def capture():
            # Caller owns self.lock. Polling needs only these projection fields,
            # never copies the potentially large edit/history/receipt journals.
            value=self.value
            if value is None:return None
            return dict(state=value['state'],operation_id=value['operation']['operation_id'],preview_digest=value['preview_digest'],
                parent_revision=value['before_history']['current_scene_revision'],result_revision=value['after_history']['current_scene_revision'],
                command_id=value['command_id'],compensation_command_id=value['compensation_command_id'],
                engine_session_id=value['engine_session_id'],stage_epoch=value['stage_epoch'],
                engine_acknowledged=value['receipt'] is not None,compensation_acknowledged=value['compensation_receipt'] is not None,
                error=value['error'],execution_id=value.get('execution_id'),feedback_lineage=deepcopy(value.get('feedback_lineage')),
                sensor_binding=deepcopy(value.get('sensor_binding')),sensor_origin_binding=deepcopy(value.get('sensor_origin_binding')))
        with self.lock:
            value=capture()
        if value is None:return None
        if owner and not (self.worker and self.worker.is_alive()):
            self.reconcile(owner)
            with self.lock:value=capture()
        view=self.broker.public_state(owner or '')
        current=view.get('build_view')
        restored=value['state']=='ROLLED_BACK'
        displayed_revision=value['parent_revision'] if restored else value['result_revision']
        displayed_command=value['compensation_command_id'] if restored else value['command_id']
        frame_current=bool(current and current['status']=='succeeded' and current.get('applied_revision')==displayed_revision and
            current.get('command_id')==displayed_command and (current.get('engine_session_id'),current.get('stage_epoch'))==(value['engine_session_id'],value['stage_epoch']))
        return dict(state=value['state'],operation_id=value['operation_id'],preview_digest=value['preview_digest'],
            parent_revision=value['parent_revision'],result_revision=value['result_revision'],
            command_id=value['command_id'],engine_acknowledged=value['engine_acknowledged'],
            durable_committed=value['state']=='COMMITTED',current_frame=frame_current,error=value['error'],
            execution_id=value['execution_id'],feedback_lineage=value['feedback_lineage'],
            sensor_binding=value['sensor_binding'],sensor_origin_binding=value['sensor_origin_binding'],
            displayed_revision=displayed_revision,compensation_acknowledged=value['compensation_acknowledged'],physical_authority=False)

    def start(self,owner,operation,digest,*,feedback_lineage=None,sensor_binding=None):
        if not self.ownership.acquire(blocking=False):
            with self.lock:
                same=bool(self.value and self.value['operation']==operation and self.value['preview_digest']==digest and self.value.get('sensor_binding')==sensor_binding)
            if same:return self.snapshot()
            raise BrokerError('scene_edit_busy','A scene transaction is already owned.',status=409)
        try:return self._start(owner,operation,digest,feedback_lineage=feedback_lineage,sensor_binding=sensor_binding)
        finally:self.ownership.release()

    def _start(self,owner,operation,digest,*,feedback_lineage=None,sensor_binding=None):
        checked=SceneChange.from_dict(operation)
        if canonical_sha256(checked.to_dict())!=digest:raise BrokerError('scene_edit_invalid','Preview digest changed.',status=409)
        duplicate=False
        archive=self.path.with_name(self.path.stem+'.history')/(checked.operation_id+'.json')
        with self.lock:
            if self.value and self.value['operation']['operation_id']==checked.operation_id:
                if self.value['operation']!=checked.to_dict() or self.value['preview_digest']!=digest or self.value.get('sensor_binding')!=sensor_binding:
                    raise BrokerError('scene_edit_duplicate_conflict','Operation ID was used for a different edit.',status=409)
                duplicate=True
            elif archive.exists():
                prior=self._read(archive)
                if prior['operation']!=checked.to_dict() or prior['preview_digest']!=digest or prior.get('sensor_binding')!=sensor_binding:
                    raise BrokerError('scene_edit_duplicate_conflict','Operation ID was used for a different edit.',status=409)
                return dict(state=prior['state'],operation_id=checked.operation_id,command_id=prior['command_id'],
                    durable_committed=prior['state']=='COMMITTED',engine_acknowledged=prior['receipt'] is not None,
                    current_frame=False,physical_authority=False,historical=True)
            if duplicate:pass
            elif self.locked():raise BrokerError('engine_state_unknown','Finish or recover the current scene transaction.',status=409)
        if duplicate:return self.snapshot(owner)
        lineage=checked_feedback_lineage(feedback_lineage)
        sensor=checked_sensor_binding(sensor_binding)
        # Admission shares the existing physical start mutex. Establish STAGED
        # before releasing it; all physical starts then see locked()==True.
        with self.admission(owner),self.workflow._lock:
            store=self.workflow._scene_edit_store()
            before=store.load()
            origin=(deepcopy(self.value.get('sensor_binding') or self.value.get('sensor_origin_binding'))
                if checked.mode=='undo' and self.value and before.operations and
                self.value['operation']['operation_id']==before.operations[-1].operation_id else None)
            if sensor:
                if self.workflow.scene_sensor_review is None:raise BrokerError('scene_sensor_unavailable','Sensor evidence validator is unavailable.',status=409)
                try:self.workflow.scene_sensor_review.validate_apply(sensor,checked.to_dict(),store,before)
                except (OSError,ValueError,TypeError,KeyError,BrokerError) as error:
                    raise BrokerError('scene_sensor_apply_rejected',str(error)[:240],status=409) from error
            if before.schema_version=='scene-changes-1.2' and checked.mode=='undo' and (not checked.parent_state_sha256 or not checked.result_state_sha256):
                raise BrokerError('scene_edit_invalid','Current-state SHA binding is required for transactional Undo.',status=409)
            if checked.parent_revision!=self.workflow._site_artifact.revision:
                raise BrokerError('scene_edit_stale_or_invalid','Reviewed scene changed.',status=409)
            after=before.append(store.source,checked)
            from .scene_changes import admit_new_scene_change
            admit_new_scene_change(store.source,after,checked)
            current=self.broker.public_state(owner)
            snapshot=current['snapshot']
            if (not current['engine_connected'] or snapshot is None or snapshot['runtime_state']=='running'
                    or snapshot['safety_state'] or snapshot['applied_revision']!=before.current_scene_revision):
                raise BrokerError('scene_edit_engine_not_ready','View the current saved scene in idle Isaac before applying this edit.',status=409)
            self.broker.acquire_lease(owner)
            # This must precede even a STAGED journal. Old programs must not
            # reopen only the original scene while ignoring new obstacle history.
            store.require_data_contract(after)
            self._require_sensor_capabilities(sensor,origin)
            if self.value:
                retained=self.path.with_name(self.path.stem+'.history')/(self.value['operation']['operation_id']+'.json')
                if retained.parent.is_symlink():raise ValueError('SCENE_TRANSACTION_PATH_INVALID')
                retained.parent.mkdir(parents=True,exist_ok=True)
                if retained.exists():
                    if self._read(retained)!=self.value:raise ValueError('SCENE_TRANSACTION_ARCHIVE_CHANGED')
                else:
                    with retained.open('xb') as stream:
                        stream.write(json.dumps(self.value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
                        stream.flush();os.fsync(stream.fileno())
            self.trace=self.workflow._edit_trace('scene_edit_undo' if checked.mode=='undo' else 'scene_edit_apply',checked.operation_id,
                feedback_lineage=lineage)
            self.trace.bind(parent_state_sha256=checked.parent_state_sha256,result_state_sha256=checked.result_state_sha256,
                preview_sha256=digest,engine_session_id=current['engine_session_id'],stage_epoch=current['stage_epoch'])
            if sensor or origin:
                proof=sensor or origin
                self.trace.bind(sensor_binding_sha256=canonical_sha256(proof))
                if proof.get('policy')=='review_survey_obstacle':
                    self.trace.bind(sensor_status='COLLECTED_SURVEY_REVIEW',sensor_raw_sha256=proof['collection_sha256'],
                        sensor_alignment_sha256=proof['result_sha256'])
                elif proof.get('policy')=='correct_obstacles':
                    self.trace.bind(sensor_execution_id=proof['execution_id'])
                    self.trace.bind(observation_id=proof['observation_id'],sensor_raw_sha256=proof['observation_sha256'])
                else:
                    self.trace.bind(sensor_execution_id=proof['execution_id'],sensor_map_id=proof['evidence']['map_id'],sensor_raw_sha256=proof['evidence']['raw_sha256'],
                        sensor_evidence_sha256=canonical_sha256(proof['evidence']),sensor_alignment_sha256=proof['alignment_sha256'])
            self.value=dict(schema_version='scene-edit-transaction-1.2',execution_id=self.trace.execution_id,feedback_lineage=lineage,project_id=store.project_id,
                source_sha256=canonical_sha256(store.source.to_dict()),operation=checked.to_dict(),preview_digest=digest,
                before_history=before.to_dict(),after_history=after.to_dict(),state='STAGED',
                engine_session_id=current['engine_session_id'],stage_epoch=current['stage_epoch'],
                request_id='edit-build-'+checked.operation_id,command_id=None,receipt=None,
                compensation_command_id=None,compensation_receipt=None,error=None,sha256='')
            if sensor or origin:self.value.update(schema_version='scene-edit-transaction-1.3',sensor_binding=sensor,sensor_origin_binding=origin)
            self._save()
            self.workflow._acknowledged_identity=None
            self.cancelled=Event()
            self.worker=Thread(target=self._run,args=(owner,store,after),name='TwinPulseSceneEdit',daemon=True)
            self.worker.start()
        return self.snapshot(owner)

    def _view(self,owner,*,require_lease=True):
        view=self.broker.public_state(owner)
        if not view['engine_connected']:
            raise ValueError('SCENE_EDIT_ENGINE_DISCONNECTED')
        if (view['engine_session_id'],view['stage_epoch'])!=(self.value['engine_session_id'],self.value['stage_epoch']):
            raise ValueError('SCENE_EDIT_ENGINE_IDENTITY_CHANGED')
        if require_lease and not view['lease_owned']:
            raise ValueError('SCENE_EDIT_CONTROL_LEASE_LOST')
        snapshot=view['snapshot']
        if snapshot is None or snapshot['runtime_state']=='running' or snapshot['safety_state']:
            raise ValueError('SCENE_EDIT_ENGINE_NOT_IDLE')
        return view

    def _refresh_lease(self,owner,*,phase=None):
        # Replay, validation and durable diagnostics may outlive the short
        # lease. Re-establish only this explicitly approved writer's control
        # on the same current idle engine; never steal another owner's lease.
        before=self._view(owner,require_lease=False)
        if phase and self.trace:
            self.trace.bind(control_lease_refresh_phase=phase,
                control_lease_owned_before_refresh=before['lease_owned'],
                expected_engine_identity_current=True)
        self.broker.acquire_lease(owner)
        return self._view(owner)

    def _wait(self,owner,operation):
        deadline=time.monotonic()+self.timeout_s
        while True:
            view=self._refresh_lease(owner)
            result=next((r for r in view['operations'] if r['command_id']==operation['command_id']),None)
            if result and result['status'] not in {'accepted','running'}:
                if result['status']!='succeeded':raise ValueError('SCENE_EDIT_BUILD_'+result['status'].upper())
                receipt=result['receipt']
                if receipt is None:raise ValueError('SCENE_EDIT_ACK_MISSING')
                return receipt
            if self.cancelled.wait(.05) or time.monotonic()>=deadline:raise TimeoutError('SCENE_EDIT_ACK_TIMEOUT')

    def _build(self,owner,source,history,request_id,*,compensation=False):
        artifact=self.workflow._register_scene_change(source,history)
        if self.trace:
            self.trace.bind(artifact_id=artifact.artifact_id,scene_edit_revision=artifact.revision)
            self.broker.bind_artifact_diagnostics(artifact.artifact_id,scene_edit_execution_id=self.trace.execution_id)
        self._save(state='COMPENSATING' if compensation else 'BUILDING')
        deadline=time.monotonic()+6.
        first=True
        while True:
            view=self._refresh_lease(owner,phase=('compensation' if compensation else 'before_dispatch') if first else None)
            first=False
            if view['engine_readiness']['site_scene_build_v2']['ready']:break
            if time.monotonic()>=deadline:raise TimeoutError('SCENE_EDIT_BUILD_PERMIT_TIMEOUT')
            self.cancelled.wait(.05)
        self.dispatch_thread=get_ident()
        try:
            operation=self.broker.submit(owner,dict(client_request_id=request_id,command_type='build_site_scene',
                artifact_id=artifact.artifact_id,expected_applied_revision=artifact.revision))
        finally:self.dispatch_thread=None
        self._save(**({'compensation_command_id':operation['command_id']} if compensation else {'command_id':operation['command_id']}))
        if self.trace:self.trace.bind(command_id=operation['command_id'],
            command_execution_id=operation.get('execution_id'),transaction_state='COMPENSATING' if compensation else 'BUILDING')
        with self.trace.span('scene_edit_compensation_ack' if compensation else 'scene_edit_engine_ack') if self.trace else nullcontext():
            receipt=self._wait(owner,operation)
        return artifact,receipt

    def _commit(self,store,history):
        with self.trace.span('scene_edit_validate_and_save') if self.trace else nullcontext():
            if self.value.get('sensor_binding'):
                before=SceneChangeHistory.from_dict(self.value['before_history'],store.source,store.project_id)
                if self.workflow.scene_sensor_review is None:raise ValueError('SCENE_SENSOR_VALIDATOR_UNAVAILABLE')
                self.workflow.scene_sensor_review.validate_apply(self.value['sensor_binding'],self.value['operation'],store,before)
            updated=store.apply(self.value['operation'],self.value['preview_digest'])
            if updated!=history:raise ValueError('SCENE_EDIT_DISK_CAS_CHANGED')
        self._remember_commit(store,updated)
        self._save(state='COMMITTED',error=None)
        self.workflow._publish_scene_change(store,updated)

    def _remember_commit(self,store,updated):
        if self.trace:
            history_digest=canonical_sha256(updated.to_dict())
            self.trace.bind(scene_edit_revision=updated.current_scene_revision,scene_change_sha256=history_digest)
            self.workflow._application.diagnostics.flush()
            self.workflow._application.diagnostics.remember_edit_binding(self.trace.execution_id,
                request_id=store.source.request_id,input_revision=store.source.input_revision.digest,
                source_revision=store.source.site.scene.revision,operation_id=updated.operations[-1].operation_id,
                history_digest=history_digest,result_revision=updated.current_scene_revision)

    def _run(self,owner,store,after):
        with self.ownership:self._run_owned(owner,store,after)

    def _run_owned(self,owner,store,after):
        try:
            _,receipt=self._build(owner,store.source,after,self.value['request_id'])
            self._save(state='ENGINE_ACKNOWLEDGED',receipt=receipt)
            try:
                self._commit(store,after)
                if self.trace:self.trace.finish()
            except Exception as error:
                # Compensation is a second existing Build, never an assumed rollback.
                before=SceneChangeHistory.from_dict(self.value['before_history'],store.source,store.project_id)
                if store.load()==after:
                    self._unknown('Disk committed; commit journal/publish failed: '+type(error).__name__)
                    return
                try:
                    _,ack=self._build(owner,store.source,before,'edit-rollback-'+self.value['operation']['operation_id'],compensation=True)
                    if store.load()!=before:
                        raise ValueError('SCENE_EDIT_DISK_CHANGED_AFTER_COMMIT')
                    self._save(state='ROLLED_BACK',compensation_receipt=ack,error=type(error).__name__)
                    if self.trace:self.trace.finish('failed',error=error,transaction_state='ROLLED_BACK')
                except Exception as recovery:
                    self._unknown(type(error).__name__+'; compensation '+type(recovery).__name__)
        except Exception as error:self._unknown(type(error).__name__+': '+str(error)[:180])

    def _unknown(self,error):
        with self.lock:
            self.value.update(state='ENGINE_STATE_UNKNOWN',error=error)
        try:self._save()
        except Exception:pass
        if self.trace:
            trace=self.trace if self.trace._root else self.trace.child('scene_edit_state_unknown')
            trace.finish('unknown',error_code='scene_edit_state_unknown',
                diagnostic_sha256=canonical_sha256(error),transaction_state='ENGINE_STATE_UNKNOWN')

    def reconcile(self,owner):
        if not self.ownership.acquire(blocking=False):return
        try:self._reconcile_owned(owner)
        finally:self.ownership.release()

    def _reconcile_owned(self,owner):
        """Compare durable ACK, history and current engine. Never submit/retry."""
        if self.storage_error or not self.value or self.worker and self.worker.is_alive():return
        if self.value['state'] in TERMINAL:return
        # With no authoritative ACK there is nothing to reconcile. In
        # particular UNKNOWN polls must not replay two full history chains.
        if not self.value['receipt'] and not self.value['compensation_receipt']:return
        try:
            current=self.broker.public_state(owner);snapshot=current['snapshot']
            if (not current['engine_connected'] or snapshot is None or snapshot['runtime_state']=='running' or snapshot['safety_state'] or
                    (current['engine_session_id'],current['stage_epoch'])!=(self.value['engine_session_id'],self.value['stage_epoch'])):return
            store=self.workflow._application.scene_change_store()
            before=SceneChangeHistory.from_dict(self.value['before_history'],store.source,store.project_id)
            after=SceneChangeHistory.from_dict(self.value['after_history'],store.source,store.project_id)
            if self.value['receipt'] and snapshot['applied_revision']==after.current_scene_revision:
                if store.load() not in (before,after):raise ValueError('SCENE_EDIT_RECONCILE_DISK_CHANGED')
                store.recover_interrupted_lock(self.value['operation'],self.value['preview_digest'])
                with self.trace.span('scene_edit_reconcile') if self.trace else nullcontext():
                    self._commit(store,after)
            elif self.value['compensation_receipt'] and snapshot['applied_revision']==before.current_scene_revision and store.load()==before:
                self._save(state='ROLLED_BACK')
        except Exception as error:self._unknown('Reconciliation: '+type(error).__name__)

    def recover(self,owner):
        """Explicit recovery rebuilds the durable revision and requires its ACK."""
        if not self.ownership.acquire(blocking=False):
            raise BrokerError('scene_edit_busy','A scene transaction is already owned.',status=409)
        try:
            with self.admission(owner):return self._recover_owned(owner)
        finally:self.ownership.release()

    def _recover_owned(self,owner):
        with self.lock:
            if self.worker and self.worker.is_alive():raise BrokerError('scene_edit_busy','Wait for the current scene transaction.',status=409)
            if self.storage_error or not self.value:raise BrokerError('scene_edit_journal_invalid','Repair the retained journal before recovery.',status=409)
            terminal=self.value['state'] in TERMINAL
        if terminal:return self.snapshot(owner)
        # Never enter broker/workflow while holding the state lock: submit owns
        # broker._lock before its transaction guard takes the state lock.
        store=self.workflow._application.scene_change_store()
        store.recover_interrupted_lock(self.value['operation'],self.value['preview_digest'])
        current=store.load()
        if current.to_dict() not in (self.value['before_history'],self.value['after_history']):
            raise BrokerError('scene_edit_disk_changed','Saved revision differs from this transaction.',status=409)
        view=self.broker.public_state(owner)
        if not view['engine_connected'] or view['snapshot'] is None or view['snapshot']['runtime_state']=='running' or view['snapshot']['safety_state']:
            raise BrokerError('scene_edit_engine_not_ready','Recovery requires current idle Isaac.',status=409)
        self.broker.acquire_lease(owner)
        self._save(engine_session_id=view['engine_session_id'],stage_epoch=view['stage_epoch'],receipt=None,
            compensation_receipt=None,compensation_command_id=None)
        self.cancelled=Event()
        def run():
            with self.ownership:
                recovery_trace=self.trace.child('scene_edit_explicit_recovery') if self.trace else None
                try:
                    # Explicit cold recovery also restores the saved *review*
                    # through its existing source/history validator. It grants
                    # no Build/Run authority and never replaces another input.
                    with self.workflow._lock:
                        selected=self.workflow._input
                        if selected is None:
                            if self.workflow._phase!='restore_review_required':
                                raise ValueError('SCENE_EDIT_RECOVERY_INPUT_NOT_COLD')
                            self.workflow.resume_saved_scene(store.project_id,
                                store.source.site.scene.revision,store.source.input_revision.digest)
                        elif selected.revision!=store.source.input_revision.digest:
                            raise ValueError('SCENE_EDIT_RECOVERY_INPUT_CHANGED')
                    _,ack=self._build(owner,store.source,current,'edit-recovery-'+uuid4().hex,compensation=True)
                    if store.load()!=current:raise ValueError('SCENE_EDIT_DISK_CHANGED_DURING_RECOVERY')
                    committed=current.to_dict()==self.value['after_history']
                    if committed:
                        with self.trace.span('scene_edit_validate_and_save') if self.trace else nullcontext():
                            if store.load()!=current:raise ValueError('SCENE_EDIT_DISK_CHANGED_DURING_RECOVERY')
                        self._remember_commit(store,current)
                    self._save(state='COMMITTED' if committed else 'ROLLED_BACK',
                        **(dict(receipt=ack,command_id=ack['command_id'],compensation_command_id=None,compensation_receipt=None)
                           if committed else dict(compensation_receipt=ack)),error=None)
                    self.workflow._publish_scene_change(store,current)
                    if recovery_trace:recovery_trace.finish(transaction_state=self.value['state'])
                except Exception as error:
                    if recovery_trace:recovery_trace.finish('unknown',error=error)
                    self._unknown('Recovery: '+type(error).__name__)
        self.worker=Thread(target=run,name='TwinPulseSceneRecovery',daemon=True);self.worker.start()
        return self.snapshot(owner)
