# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""App adapter for one owned fixed-command robot worker; no import-time SSH.

The robot runs the planner and final guard. PC only supplies scoped bootstrap,
fresh challenge keepalives, cancellation and display. Source review is not a
substitute for the robot's current-boot stop/sensor admission.
"""
from copy import deepcopy
import math
import time
import threading
from uuid import uuid4
from twinpulse_core.adaptive_mission_contract import adaptive_scope,nominal_room
from twinpulse_core.revisions import canonical_sha256
from .observed_release_registration import ObservedReleaseRegistration


def checked_remote_visual(value, identity, scope, context=None,*,binding=None):
    keys={'schema','session_id','context','state','room_revision','route_revision','map_revision',
          'alignment_revision','pose_room','goal_room','route_room','scan_room','trajectory_room',
          'motion_authorized','physical_demo_ready','provenance','revision'}
    if (not isinstance(value,dict) or set(value)!=keys or value['schema']!='automatic-mission-visual-1.0'
            or value['session_id']!=identity
            or value['motion_authorized'] is not False or value['physical_demo_ready'] is not False
            or value['provenance']!='live_sensor'
            or value['state'] not in {'LOCALIZING','SURVEYING','ALIGNING_PHOTO','DRIVING','REPLANNING','ARRIVED','FAILED'}):
        raise ValueError('OBSERVED_REMOTE_VISUAL_CONTEXT')
    revision=scope['goal']['room_revision']
    if binding is not None:
        from twinpulse_core.observed_mission import checked_goal
        goal=checked_goal(binding['goal'])
        if (scope['schema'] not in {'observed-mission-scope-3.0','observed-mission-scope-5.0'}
                or any(goal[k]!=scope['goal'][k] for k in ('mode','xy','duration_s'))):
            raise ValueError('OBSERVED_REMOTE_BINDING_SCOPE')
        revision=goal['room_revision']
    if value['room_revision']!=revision:
        # An ALIGN visual already queued at ACK time may still name the old
        # scene, but must not carry a current room pose or route/scan permission.
        if not (binding and value['room_revision']==scope['goal']['room_revision']
                and value['state']=='ALIGNING_PHOTO' and value['pose_room'] is None
                and not value['scan_room'] and not value['route_room']):
            raise ValueError('OBSERVED_REMOTE_VISUAL_CONTEXT')
    from twinpulse_core.observation_stream import checked_context
    source=checked_context(value['context'])
    if source['origin']!='live_ros' or source['project_id']!=scope['project_id']:
        raise ValueError('OBSERVED_REMOTE_SOURCE_CONTEXT')
    if context and any(source[k]!=context[k] for k in ('boot_id','release_id')):
        raise ValueError('OBSERVED_REMOTE_SOURCE_CHANGED')
    if source['source_revision']!=source['release_id']:raise ValueError('OBSERVED_REMOTE_SOURCE_REVISION')
    finite=lambda x:type(x) in (int,float) and math.isfinite(x) and abs(x)<=20
    def points(rows,n,size):
        return isinstance(rows,list) and len(rows)<=n and all(type(p) is list and len(p)==size and all(finite(x) for x in p) for p in rows)
    if not all(points(value[k],limit,size) for k,limit,size in (('route_room',16,2),('scan_room',160,2),('trajectory_room',512,3))):
        raise ValueError('OBSERVED_REMOTE_VISUAL_GEOMETRY')
    for key,size in (('pose_room',3),('goal_room',2)):
        if value[key] is not None and not points([value[key]],1,size):raise ValueError('OBSERVED_REMOTE_VISUAL_GEOMETRY')
    expected=scope['goal']['xy'] if scope['goal']['mode'] not in {'SURVEY_LOCAL','SURVEY_ONLY'} else None
    if value['goal_room']!=expected:raise ValueError('OBSERVED_REMOTE_VISUAL_GOAL')
    import re
    for key in ('route_revision','map_revision','alignment_revision','revision'):
        if value[key] is not None and (not isinstance(value[key],str) or not re.fullmatch('[a-f0-9]{64}',value[key])):
            raise ValueError('OBSERVED_REMOTE_VISUAL_REVISION')
    if value['revision']!=canonical_sha256({k:v for k,v in value.items() if k!='revision'}):
        raise ValueError('OBSERVED_REMOTE_VISUAL_HASH')
    return deepcopy(value)


class RemoteObservedFactory:
    supports_remote_correction=True
    supports_current_goal_preview=True
    supports_exact_goal_handoff=True
    supports_route_revalidation=True
    def __init__(self, controller, root, project_id, *, source_root=None):
        self.controller=controller;self.root=root;self.project_id=project_id
        self.source_root=source_root if source_root is not None else root
        self.reference_loader=None;self.idle_owner=None;self.idle_key=None;self.idle_job=None
        self.idle_stop=threading.Event();self.idle_keeper=None;self.idle_lock=threading.RLock()
        self.parked_review=None

    def _keep_idle(self):
        while not self.idle_stop.wait(.05):
            try:
                with self.controller.lock:
                    if self.idle_stop.is_set():return
                    state=self.controller.snapshot(self.idle_owner)
                    if not state['busy'] or state['state'] in {'FINISHED','FAILED','REJECTED','CONNECTION_LOST','STOPPING'}:return
                    self.controller.input(self.idle_owner,self.idle_job,state['sequence']+1,'watch',self.controller.wall()+250)
            except Exception:return

    def clock(self):
        with self.controller.lock:
            receipt=self.controller.localization_received
            if receipt is None:raise ValueError('IDLE_LOCALIZATION_NO_CURRENT_RECEIPT')
            delta=self.controller.clock()-receipt['pc_s']
            if delta<0:raise ValueError('IDLE_LOCALIZATION_PC_CLOCK_FAULT')
            return receipt['robot_upper_s']+delta

    def preview_current(self,owner,*,reference_key=None):
        # A failed explicit query must not leave its watch keeper running.
        # Keep the original diagnosis even if cleanup itself is still pending;
        # requests from a different owner never close the existing worker.
        try:
            return self._preview_current(owner,reference_key=reference_key)
        except Exception as exc:
            if self.idle_owner==owner:
                import re
                code=str(exc)
                if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='IDLE_LOCALIZATION_QUERY_FAILED'
                with self.controller.lock:
                    self.controller.state['localization_error']=code
                    sink=self.controller.journal_sink
                    if sink is not None and not sink.closing.is_set():
                        self.controller._record('localization_request_failed',reason=code)
                try:self.close_idle(owner)
                except Exception:
                    exc.add_note('IDLE_LOCALIZATION_CLEANUP_PENDING')
                    with self.controller.lock:
                        self.controller.state['localization_cleanup_error']='IDLE_LOCALIZATION_CLEANUP_PENDING'
            raise

    def _preview_current(self,owner,*,reference_key=None):
        # Explicit goal request only. Refresh/history never opens this worker.
        # Starts the reviewed fixed no-motion entry; never deploys or enables.
        from twinpulse_core.reference_transport import ReferenceSender
        if not callable(self.reference_loader) or reference_key is None:
            raise ValueError('IDLE_LOCALIZATION_OWNED_REFERENCE_REQUIRED')
        with self.idle_lock:
            prior=self.reference_loader(reference_key)
            sender=ReferenceSender(prior)
            if self.idle_job and owner!=self.idle_owner:
                raise ValueError('IDLE_LOCALIZATION_OWNER_CHANGED')
            if self.idle_job and reference_key!=self.idle_key:
                raise ValueError('IDLE_LOCALIZATION_REFERENCE_CHANGED')
            state=self.controller.snapshot(owner)
            if not self.idle_job:
                if state['busy']:raise ValueError('ROBOT_OPERATION_BUSY')
                alignment={k:prior['photo_alignment'][k] for k in ('status','room_from_map','report_revision')}
                room=self.reference_room_revision(prior)
                scope=adaptive_scope({'schema':'observed-mission-scope-6.0','phase':'IDLE_LOCALIZATION_ONLY',
                    'project_id':self.project_id,'goal':{'mode':'NAVIGATE_TWIN_GOAL','xy':[0.,0.],
                        'room_revision':room,'duration_s':45.},
                    'reference':{'kind':prior['reference_kind'],'revision':prior['map']['revision'],'payload':sender.descriptor},
                    'alignment':alignment})
                registration=ObservedReleaseRegistration(self.root,self.project_id,room,source_root=self.source_root)
                registration(scope)
                job=uuid4().hex
                self.controller.mission_admission=registration
                self.controller.start(owner,'localize',job,True,scope=scope,reference=prior)
                self.idle_owner=owner;self.idle_key=reference_key;self.idle_job=job
                self.idle_stop.clear()
                self.idle_keeper=threading.Thread(target=self._keep_idle,daemon=True,name='tp-idle-localization-watch')
                self.idle_keeper.start()
            started=self.controller.clock()
            while True:
                state=self.controller.snapshot(owner)
                if state['job_id']!=self.idle_job or not state['owned']:raise ValueError('IDLE_LOCALIZATION_SESSION_CHANGED')
                if not state['busy'] or state['state'] in {'FAILED','REJECTED','CONNECTION_LOST','FINISHED','STOPPING'}:
                    raise ValueError(state.get('reason') or 'IDLE_LOCALIZATION_WORKER_ENDED')
                # READY(0) advertises a challenge, not an accepted keeper yet.
                # A query must not race ahead of the first fresh watch input.
                if state['state']=='READY' and state.get('localization_input_sequence',0)>0:break
                if self.controller.clock()-started>65.:raise ValueError('IDLE_LOCALIZATION_PREPARATION_TIMEOUT')
                time.sleep(.01)
            # Reopen original/ledger again after preparation before each query.
            if self.reference_loader(reference_key)!=prior:raise ValueError('IDLE_LOCALIZATION_REFERENCE_CHANGED')
            if self.controller.mission_scope['reference']['payload']!=sender.descriptor:
                raise ValueError('IDLE_LOCALIZATION_REFERENCE_CHANGED')
            query=uuid4().hex;self.controller.query_localization(owner,self.idle_job,query)
            deadline=self.controller.clock()+.25
            while True:
                with self.controller.lock:
                    value=deepcopy(self.controller.localization_observation)
                    invalid=self.controller.stop_requested or self.controller.job!=self.idle_job
                if invalid:
                    state=self.controller.snapshot(owner)
                    raise ValueError(state.get('reason') or 'IDLE_LOCALIZATION_CLOSED')
                if value is not None:
                    from twinpulse_core.current_goal_preview import current_binding
                    upper=self.clock()
                    try:current_binding(value['evidence'],value['context'],upper,self.controller.mission_scope['goal']['room_revision'])
                    except ValueError as exc:
                        # Record this BEFORE normal failed-query cleanup closes
                        # the journal. A validated receipt may expire while a
                        # caller is scheduled; never re-stamp or reuse it.
                        with self.controller.lock:
                            receipt=self.controller.localization_received or {}
                            self.controller._record('localization_return_rejected',query_id=query,
                                reason=str(exc)[:160],evidence_age_upper_s=upper-value['evidence']['sample_s'],
                                round_trip_upper_s=receipt.get('round_trip_s'),
                                elapsed_since_receipt_s=self.controller.clock()-receipt['pc_s'] if 'pc_s' in receipt else None)
                        raise
                    return {'map_id':reference_key,**value}
                state=self.controller.snapshot(owner)
                if not state['busy'] or state['state'] in {'FAILED','REJECTED','CONNECTION_LOST','STOPPING','FINISHED'}:
                    raise ValueError(state.get('reason') or 'IDLE_LOCALIZATION_WORKER_ENDED')
                if self.controller.clock()>=deadline:raise ValueError('IDLE_LOCALIZATION_QUERY_TIMEOUT')
                time.sleep(.002)

    def reference_room_revision(self,prior):
        # Loader checks current effective geometry; recover its exact revision,
        # not a hash guessed from structural walls or the original scene.
        loader=getattr(self,'room_revision_loader',None)
        if not callable(loader):raise ValueError('IDLE_LOCALIZATION_CURRENT_ROOM_REQUIRED')
        return loader()

    def close_idle(self,owner=None):
        with self.idle_lock:
            if owner is not None and self.idle_owner!=owner:return
            self.idle_stop.set()
            if self.idle_job:
                state=self.controller.snapshot(self.idle_owner)
                if state['busy'] and state['job_id']==self.idle_job:
                    self.controller.input(self.idle_owner,self.idle_job,state['sequence']+1,'close',0)
                    self.controller.thread.join(22)
                    if self.controller.thread.is_alive():raise ValueError('IDLE_LOCALIZATION_CLEANUP_PENDING')
            if self.idle_keeper:self.idle_keeper.join(.2)
            self.idle_job=None;self.idle_key=None;self.idle_owner=None

    def discard_review(self,owner=None):
        with self.idle_lock:
            if owner is None or self.parked_review and self.parked_review['owner']==owner:
                self.parked_review=None

    def close(self):
        self.discard_review();self.close_idle()

    def park_review(self,owner,key,preview):
        # No sensors/watch keeper run while Isaac or the user reviews. This
        # memory-only reservation is not current pose, approval or a lease.
        from twinpulse_core.current_goal_preview import check_preview
        with self.idle_lock:
            self.discard_review(owner)
            if preview.get('schema')!='current-goal-preview-2.0':raise ValueError('GOAL_REVIEW_REVALIDATION_REQUIRED')
            if not self.owns_idle(owner,key):raise ValueError('GOAL_REVIEW_NOT_OWNED_IDLE')
            value=self.preview_current(owner,reference_key=key)
            check_preview(preview,value['evidence'],value['context'],self.clock(),preview['goal_contract'])
            reference=deepcopy(self.controller.mission_scope['reference'])
            old_job=self.idle_job
            self.close_idle(owner)
            state=self.controller.snapshot(owner)
            if (state['busy'] or state.get('cleanup_confirmed') is not True
                    or state.get('sensor_cleanup_confirmed') is not True):
                raise ValueError('GOAL_REVIEW_IDLE_CLEANUP_NOT_CONFIRMED')
            self.parked_review={'owner':owner,'key':key,'preview':deepcopy(preview),
                'reference':reference,'old_job':old_job}

    def owns_review(self,owner,key,preview):
        with self.idle_lock:
            value=self.parked_review
            return bool(value and value['owner']==owner and value['key']==key and value['preview']==preview
                and not self.controller.snapshot(owner)['busy'])

    def resume_review(self,owner,key,preview):
        # Called once by explicit Confirm only. Never polling, retry or history.
        from twinpulse_core.reference_transport import ReferenceSender
        with self.idle_lock:
            if not self.owns_review(owner,key,preview):raise ValueError('GOAL_REVIEW_RESERVATION_CHANGED')
            saved=self.parked_review;self.parked_review=None
            prior=self.reference_loader(key)
            if (ReferenceSender(prior).descriptor!=saved['reference']['payload']
                    or prior['map']['revision']!=saved['reference']['revision']):
                raise ValueError('GOAL_REVIEW_REFERENCE_CHANGED')
            return self.preview_current(owner,reference_key=key)

    def owns_idle(self,owner,reference_key):
        with self.idle_lock:
            if owner!=self.idle_owner or reference_key!=self.idle_key or not self.idle_job:return False
            state=self.controller.snapshot(owner)
            return bool(state['busy'] and state['owned'] and state['job_id']==self.idle_job
                and self.controller.mode=='localize' and not self.controller.stop_requested
                and state['state']=='READY'
                and self.controller.goal_handoff_value is None)

    def prepare_goal_handoff(self,owner,key,prior,effective,preview):
        from twinpulse_core.reference_transport import goal_handoff
        if not self.owns_idle(owner,key):raise ValueError('GOAL_HANDOFF_NOT_OWNED_IDLE')
        if self.reference_loader(key)!=prior or self.reference_room_revision(prior)!=effective['effective_revision']:
            raise ValueError('GOAL_HANDOFF_REFERENCE_CHANGED')
        scope=self.controller.mission_scope
        value=goal_handoff(scope,self.idle_job,preview)
        registration=ObservedReleaseRegistration(self.root,self.project_id,effective['effective_revision'],source_root=self.source_root)
        registration(value['scope'])
        return RemoteGoalHandoffAdapter(self,registration,value,owner,key)

    def availability(self, room_revision):
        registration=ObservedReleaseRegistration(self.root,self.project_id,room_revision,source_root=self.source_root)
        probe={'schema':'observed-mission-scope-1.0','project_id':self.project_id,
            'goal':{'mode':'SURVEY_LOCAL','xy':[0.,0.],'room_revision':room_revision,'duration_s':45},
            'reference':None,'alignment':None}
        try:registration(probe)
        except (ValueError,OSError,TypeError,KeyError) as exc:
            return {'available':False,'code':str(exc)[:160]}
        return {'available':True,'code':'ROBOT_LOCAL_ADMISSION_RECHECK_REQUIRED'}

    def __call__(self,prior,room,effective,goal):
        reference=alignment=None
        if goal['mode']=='NAVIGATE_TWIN_GOAL':
            if prior.get('reference_kind')=='accepted-survey-reference-1.0':
                # A session's deskewed tracking endpoints/keyframes cannot be
                # stripped into the legacy512-endpoint bootstrap silently.
                # Idle upload/query now use a separate hash-bound lifecycle.
                # Exact approved-plan handoff to driving remains unavailable.
                raise ValueError('SURVEY_REFERENCE_REMOTE_FULL_HANDOFF_REQUIRED')
            # Do not silently downsample a reference to fit the bootstrap budget.
            reference={k:prior['map'][k] for k in ('revision','endpoint_cells')}
            alignment={k:prior['photo_alignment'][k] for k in ('status','room_from_map','report_revision')}
        value={'schema':'observed-mission-scope-1.0','project_id':self.project_id,
               'goal':goal,'reference':reference,'alignment':alignment}
        if goal['mode'] in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:
            from .robot_geometry_evidence import load_geometry_evidence
            geometry=load_geometry_evidence()
            base=geometry['base_footprint_to_base_link_xyz_m']
            mount=geometry['base_link_to_scan_xyz_m']
            value.update(schema='observed-mission-scope-4.0' if goal['mode']=='SURVEY_ONLY' else 'observed-mission-scope-2.0',nominal=nominal_room(effective['objects'],base[2]+mount[2],effective['effective_revision']))
        scope=adaptive_scope(value)
        registration=ObservedReleaseRegistration(self.root,self.project_id,effective['effective_revision'],source_root=self.source_root)
        return RemoteObservedAdapter(self.controller,registration,scope)


class RemoteObservedAdapter:
    provenance='live_sensor';frame_id='odom'
    requires_owner_presence=True
    def __init__(self,controller,registration,scope,*,sleep=time.sleep,clock=time.monotonic):
        self.controller=controller;self.registration=registration;self.scope=adaptive_scope(scope)
        self.sleep=sleep;self.clock=clock;self.stop_requested=lambda:None;self.started=False
        self.identity=uuid4().hex;self.owner='automatic-'+self.identity
        self.context={'project_id':scope['project_id']}
        self.commit_correction=None;self.accept_binding=None;self.fit_result=None;self.survey_map=None
        self.correction_cancelled=threading.Event();self.correction_worker=None;self.correction_answer=None

    def configure_correction(self,commit,accepted):
        if self.started or self.scope['schema'] not in {'observed-mission-scope-2.0','observed-mission-scope-4.0'} or not callable(commit) or not callable(accepted):
            raise ValueError('REMOTE_CORRECTION_CONFIGURATION')
        self.scope=adaptive_scope({**self.scope,'schema':'observed-mission-scope-5.0' if self.scope['schema']=='observed-mission-scope-4.0' else 'observed-mission-scope-3.0','photo_policy':'idle-bounded-wall-ack-1.0'})
        self.commit_correction=commit;self.accept_binding=accepted

    def _commit(self,proposal):
        self.fit_result={**deepcopy(proposal['fit']),'report_revision':canonical_sha256(proposal['fit'])}
        try:
            binding=self.commit_correction(proposal['fit'],self.correction_cancelled)
            self.correction_answer={'binding':binding,'reason':None}
        except Exception as exc:
            import re
            code=str(exc)
            self.correction_answer={'binding':None,'reason':code if re.fullmatch('[A-Z0-9_]{1,120}',code) else 'REMOTE_CORRECTION_COMMIT_FAILED'}

    def admit(self,goal):
        if goal!=self.scope['goal']:raise ValueError('OBSERVED_ADAPTER_GOAL_CHANGED')
        self.registration(self.scope)

    def bind_session(self,identity):
        import re
        if self.started or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('OBSERVED_SESSION_BINDING')
        self.identity=identity;self.owner='automatic-'+identity

    def safety(self):pass  # Robot owns current sensor/board/watchdog checks.

    def _begin(self):
        with self.controller.lock:
            if self.controller.thread and self.controller.thread.is_alive():raise ValueError('ROBOT_OPERATION_BUSY')
            self.controller.mission_admission=self.registration
            self.controller.start(self.owner,'mission',self.identity,True,scope=self.scope)

    def run(self,*,record,visual,safety):
        # Registration is server-owned. The fixed robot bootstrap checks the
        # remote release/calibration again before any device initialization.
        safety();self._begin()
        self.started=True;started=self.clock()
        # Raw journal replay and UI/report copies can exceed one watch interval.
        # Every admitted observed mission needs an independent sender, including
        # cold survey/fit. Otherwise a PC report or visual callback can starve
        # the native 250ms input gate even while the operator intent is current.
        # The SAME execution/source/owner guard runs before each watch; no new
        # consent, motion authority, clock budget or automatic restart is given.
        # The old idle keeper is already stopped by _begin for a goal handoff.
        watch_stop=threading.Event()
        self.watch_failure=None;watch_thread=None
        if watch_stop is not None:
            watch_thread=threading.Thread(target=self._goal_watches,args=(watch_stop,safety),
                daemon=True,name='tp-owned-goal-watch')
            watch_thread.start()
        try:return self._follow(record=record,visual=visual,safety=safety,started=started,
                                independent_watch=watch_stop is not None)
        finally:
            if watch_stop is not None:
                import sys
                primary=sys.exc_info()[1]
                watch_stop.set();watch_thread.join(1.)
                if watch_thread.is_alive():
                    failure=ValueError('GOAL_WATCH_CLEANUP_PENDING')
                    if primary is not None:
                        from twinpulse_core.cleanup_diagnostics import retain_cleanup
                        retain_cleanup(primary,'goal_watch_join',failure)
                    else:raise failure

    def _goal_watches(self,stop,safety):
        sent_stop=None
        while not stop.is_set():
            try:
                cycle_started=self.clock()
                action=self.stop_requested()
                if not action:safety()
                guard_ended=self.clock()
                with self.controller.lock:
                    lock_acquired=self.clock()
                    state=self.controller.snapshot(self.owner)
                    if not state['busy']:return
                    # Read Stop again after guard work and under the same lock
                    # used by the sender; never enqueue a watch after a latched
                    # stop. Upgrade ordinary Stop to Force STOP at any time.
                    action=self.stop_requested()
                    if action and action!=sent_stop:
                        self.controller.input(self.owner,self.identity,state['sequence']+1,action,0)
                        sent_stop=action
                    elif not action and state['state'] not in {'STOPPING','FINISHED','FAILED','CONNECTION_LOST','REJECTED'}:
                        self.controller.input(self.owner,self.identity,state['sequence']+1,'watch',self.controller.wall()+250)
                    if isinstance(self,RemoteGoalHandoffAdapter):
                        # This existing diagnostic kind belongs only to the
                        # reviewed-goal protocol. Cold survey archives retain
                        # their established input/pipe/accepted records.
                        self.controller._record('goal_watch_cycle',
                            guard_s=max(0.,guard_ended-cycle_started),
                            controller_lock_wait_s=max(0.,lock_acquired-guard_ended),
                            sender_s=max(0.,self.clock()-lock_acquired),
                            **getattr(self,'last_safety_timing',{}))
            except Exception as exc:
                self.watch_failure=exc
                # Stop only this owned active worker. Keep the original cause;
                # failed delivery remains an independent cleanup diagnosis.
                try:
                    with self.controller.lock:
                        state=self.controller.snapshot(self.owner)
                        if state['owned'] and state['busy']:
                            self.controller.input(self.owner,self.identity,state['sequence']+1,'force_stop',0)
                except Exception:pass
                return
            if stop.wait(.05):return

    def _follow(self,*,record,visual,safety,started,independent_watch):
        last_visual=None;last_telemetry=None;last_event=0;sent_stop=None;receipt_consumed=False
        while True:
            if self.watch_failure is not None:raise self.watch_failure
            safety()
            state=self.controller.snapshot(self.owner)
            with self.controller.lock:
                events=[e['data']['event'] for e in self.controller.journal if e['kind']=='robot_event'
                        and e['data']['event']['event_index']>last_event]
            for event in events:
                record(event['kind'],robot_t=event['t'],**event['data']);last_event=event['event_index']
            with self.controller.lock:
                proposal=deepcopy(self.controller.correction_proposal)
                replied=self.controller.correction_reply is not None
                receipt=deepcopy(self.controller.correction_receipt)
            action=self.stop_requested()
            if action:self.correction_cancelled.set()
            if proposal is not None and self.correction_worker is None and not action:
                if self.commit_correction is None:raise ValueError('REMOTE_CORRECTION_ACK_NOT_CONFIGURED')
                self.correction_worker=threading.Thread(target=self._commit,args=(proposal,),daemon=True,name='tp-remote-idle-commit')
                self.correction_worker.start()
            if self.correction_answer is not None and not replied and not action and state['busy']:
                answer=self.correction_answer
                self.controller.reply_correction(self.owner,self.identity,proposal['revision'],answer['binding'],reason=answer['reason'])
            if receipt is not None and not receipt_consumed and not action:
                record('correction_robot_receipt',**{k:v for k,v in receipt.items() if k!='state'})
                if receipt['binding'] is not None:
                    self.accept_binding(receipt['binding'])
                    self.fit_result['goal_binding']=deepcopy(receipt['binding'])
                    self.fit_result['report_revision']=canonical_sha256({k:v for k,v in self.fit_result.items() if k!='report_revision'})
                receipt_consumed=True
            current=state.get('adaptive_visual')
            if current and current['revision']!=last_visual:
                visual(current);last_visual=current['revision'];self.context=current['context']
            telemetry=state.get('adaptive_telemetry')
            if telemetry and telemetry['revision']!=last_telemetry:
                record('mission_telemetry',telemetry=telemetry,received_s=state['telemetry_received_s'])
                last_telemetry=telemetry['revision']
            if not state['busy']:
                if self.watch_failure is not None:raise self.watch_failure
                with self.controller.lock:
                    evidence=deepcopy(getattr(self.controller,'mission_evidence',None))
                if evidence is not None:
                    self.survey_map=evidence['survey_map'];self.fit_result=evidence['photo_alignment']
                record('remote_evidence_status',status=state.get('mission_evidence_status','NOT_AVAILABLE'),
                       reason=state.get('mission_evidence_error'),historical_only=True)
                if state.get('reason') and state.get('result') not in {'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED'}:
                    from twinpulse_core.cleanup_diagnostics import checked_notes
                    failure=ValueError(state['reason'])
                    failure.mission_cleanup_errors=checked_notes(state.get('native_cleanup_errors',[]))
                    raise failure
                if state.get('cleanup_confirmed') is not True:raise ValueError('OBSERVED_ROBOT_CLEANUP_NOT_CONFIRMED')
                if state.get('sensor_cleanup_confirmed') is not True:raise ValueError('OBSERVED_SENSOR_CLEANUP_NOT_CONFIRMED')
                result=state.get('result')
                if result not in {'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED'}:
                    code=state.get('reason') or 'OBSERVED_ROBOT_OPERATION_FAILED'
                    raise ValueError(code)
                if (result=='MISSION_ARRIVED' and self.scope['goal']['mode'] in {'SURVEY_ONLY','SURVEY_THEN_NAVIGATE'}
                        and (self.survey_map is None or self.fit_result is None)):
                    raise ValueError(state.get('mission_evidence_error') or 'REMOTE_SURVEY_EVIDENCE_MISSING')
                return {'status':result,'mission_id':self.identity,'robot_job_id':self.identity,
                        'sensor_cleanup_confirmed':state.get('sensor_cleanup_confirmed') is True,
                        'evidence_export':state.get('evidence_export','NOT_AVAILABLE'),
                        'mission_evidence_status':state.get('mission_evidence_status','NOT_AVAILABLE')}
            if not independent_watch and action and action!=sent_stop:
                self.controller.input(self.owner,self.identity,state['sequence']+1,action,0);sent_stop=action
            elif not independent_watch and not action and state['state'] not in {'STOPPING','FINISHED','FAILED','CONNECTION_LOST','REJECTED'}:
                self.controller.input(self.owner,self.identity,state['sequence']+1,'watch',self.controller.wall()+250)
            if self.clock()-started>135:raise ValueError('OBSERVED_REMOTE_SESSION_TIMEOUT')
            self.sleep(.05)

    def close(self):
        self.correction_cancelled.set()
        if not self.started:return
        state=self.controller.snapshot(self.owner)
        if state['busy']:
            self.controller.input(self.owner,self.identity,state['sequence']+1,'force_stop',0)
            self.controller.thread.join(22)
            if self.controller.thread.is_alive():raise ValueError('OBSERVED_REMOTE_CLEANUP_PENDING')
        if self.correction_worker:
            self.correction_worker.join(.1)
            if self.correction_worker.is_alive():raise ValueError('REMOTE_CORRECTION_CLEANUP_PENDING')


class RemoteGoalHandoffAdapter(RemoteObservedAdapter):
    """Adopts only the current owner's idle link. No new subprocess or survey."""
    def __init__(self,factory,registration,value,owner,key):
        super().__init__(factory.controller,registration,value['scope'])
        self.factory=factory;self.value=deepcopy(value);self.owner=owner;self.key=key
        self.identity=value['mission_id'];self.context=deepcopy(factory.controller.localization_observation['context'])

    def bind_session(self,identity):
        if self.started:raise ValueError('OBSERVED_SESSION_BINDING')
        # App report identity is separate; native identity must not change.
        self.app_identity=identity

    def _begin(self):
        from twinpulse_core.current_goal_preview import check_preview
        if not self.factory.owns_idle(self.owner,self.key):raise ValueError('GOAL_HANDOFF_NOT_OWNED_IDLE')
        phase='FRESH_QUERY';current=None;started=self.controller.clock()
        try:
            current=self.factory.preview_current(self.owner,reference_key=self.key)
            phase='RECHECK_REVIEWED_ROUTE'
            check_preview(self.value['preview'],current['evidence'],current['context'],self.factory.clock(),self.scope['goal'])
            phase='RELEASE_ADMISSION'
            self.registration(self.scope)
            if self.stop_requested():raise ValueError('GOAL_HANDOFF_CANCELLED')
            phase='SEND_HANDOFF'
            self.controller.handoff_goal(self.owner,self.identity,self.value['preview'])
        except Exception as exc:
            # Keep the exact original cause and pinpoint pre-output failure.
            # This diagnosis never retries, refreshes evidence or grants motion.
            age=None
            if current is not None:
                try:age=self.factory.clock()-current['evidence']['sample_s']
                except (ValueError,KeyError):pass
            self.controller._record('goal_handoff_admission_failed',phase=phase,
                error_type=type(exc).__name__,reason=str(exc)[:160],
                elapsed_s=self.controller.clock()-started,evidence_age_upper_s=age)
            raise
        self.started=True
        # The existing adapter now supplies watches; never two owners/keepers.
        self.factory.idle_stop.set()

    def close(self):
        # Even admission failure closes the owned idle sensor/watch worker.
        self.factory.close_idle(self.owner)
        super().close()
