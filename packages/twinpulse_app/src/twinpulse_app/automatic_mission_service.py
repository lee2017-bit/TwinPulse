# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""AD4 bridge: immutable prior + current adapter -> owned actual mission loop.

No adapter is registered by HTTP or selected by a saved PASS. Production startup
has no qualified live adapter; it remains unavailable until reviewed evidence
and field scope are supplied by the owning launcher, never by a browser flag.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import re
import threading
import time
from uuid import uuid4
from twinpulse_core.observed_mission import checked_goal,ObservedMission
from twinpulse_core.cold_start_mission import ColdStartMission
from twinpulse_core.adaptive_mission_contract import nominal_room
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.mission_telemetry import DISPLAY_RECEIPT_S
from .automatic_photo_store import load_automatic_room
from .command_broker import BrokerError

TERMINAL_STATES={'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}

class _MissionDiagnostic:
    """Optional bounded PC observations, never raw samples or robot clock deltas.

    A phase ends successfully only on its expected forward transition. Remaining
    phases/ACKs at termination are unknown or cancelled, not assumed successful.
    Diagnostic exceptions cannot escape into mission admission/cleanup.
    """
    _NEXT={'OUTBOUND':{'RETURN'},'RETURN':{'ALIGN'},'SURVEY':{'ALIGN'},
           'ALIGN':{'NAVIGATE','VERIFY_SURVEY','SURVEY_COMPLETE'},'VERIFY_SURVEY':{'SURVEY_COMPLETE'}}
    _PHASES={'OUTBOUND','RETURN','SURVEY','ALIGN','NAVIGATE','VERIFY_SURVEY','SURVEY_COMPLETE'}

    def __init__(self,trace):
        self.trace=trace;self.lock=threading.RLock();self.active=None;self.phase=None
        self.seen=set();self.ack=None;self.closed=False;self.phase_refs=None;self.bind_count=0

    def begin(self,stage,**refs):
        if self.trace is None:return None
        try:return self.trace.child(stage,measurement_source='pc_observation',**refs)
        except Exception:self.lost();return None

    def lost(self):
        try:self.trace.store.note_storage_error()
        except Exception:pass

    def bind(self,span,**refs):
        if span is None:return
        try:span.bind(**refs)
        except Exception:self.lost()

    def end(self,span,status='succeeded',**refs):
        if span is None:return
        try:span.finish(status,**refs)
        except Exception:self.lost()

    @contextmanager
    def span(self,stage,*,cancellation=None,**refs):
        span=self.begin(stage,**refs)
        try:yield span
        except BaseException as exc:
            code=str(exc)
            if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_PROCESSING_FAILED'
            self.end(span,'cancelled' if cancellation is not None and cancellation() else 'failed',
                error_code=code,error_type=type(exc).__name__,**refs)
            raise
        else:self.end(span,**refs)

    def phase_observed(self,data):
        if self.trace is None:return
        state=data.get('stage')
        if state not in self._PHASES:return
        with self.lock:
            if self.closed:return
            if state!=self.phase:
                self.end(self.active,'succeeded' if state in self._NEXT.get(self.phase,set()) else 'unknown')
                self.active=None;self.phase=state;self.phase_refs=None
                # No high-rate telemetry or unbounded relocalization trace.
                if state not in self.seen:
                    self.seen.add(state)
                    self.active=self.begin('mission_phase_'+state.lower(),runtime_state=state)
            refs=(data.get('map_revision'),data.get('alignment_revision'))
            if self.active is not None and refs!=self.phase_refs and self.bind_count<16:
                self.bind_count+=1
                self.phase_refs=refs
                self.bind(self.active,map_revision=refs[0],alignment_revision=refs[1])
            if data.get('error_stage')=='PHOTO_ALIGNMENT':
                self.end(self.active,'failed',error_code=data.get('reason'),error_type=data.get('error_type'))
                self.active=None

    def wait_ack(self,**refs):
        with self.lock:
            if not self.closed and self.ack is None:self.ack=self.begin('mission_correction_ack',remote_outcome='unknown',**refs)

    def accepted_ack(self,**refs):
        with self.lock:
            if self.closed:return
            self.end(self.ack,remote_outcome='accepted',**refs);self.ack=None

    def close(self,status,**refs):
        with self.lock:
            self.closed=True
            unresolved='cancelled' if status=='cancelled' else 'failed' if status=='failed' else 'unknown'
            self.end(self.active,status if self.phase in {'NAVIGATE','SURVEY_COMPLETE'} else unresolved,**refs)
            self.end(self.ack,unresolved,remote_outcome='unknown',**refs)
            self.active=None;self.ack=None

class AutomaticMissionService:
    def __init__(self,automatic,*,adapter_factory=None,clock=time.monotonic):
        self.automatic=automatic;self.adapter_factory=adapter_factory;self.clock=clock
        # One lock prevents simultaneous mapping/correction and mission ownership.
        self.lock=automatic.lock;self.job=None;self.worker=None;self.stop_action=None;self.closed=False
        self.adapter=None;self.adapter_available=False;self.last_owner_presence=self.clock()
        self.execution_guard=None
        self.diagnostics=None
        automatic.mission_active=lambda:bool(self.worker and self.worker.is_alive())

    def snapshot(self,owner):
        with self.lock:
            if self.job and self.job['owner']!=owner:raise BrokerError('mission_not_owned','Mission belongs to another connection',status=409)
            self.last_owner_presence=self.clock()
            value=deepcopy({k:v for k,v in (self.job or {}).items() if k!='owner'})
            if value:value['elapsed_s']=round(self.job.get('ended',self.clock())-self.job['started'],3);value.pop('started',None);value.pop('ended',None)
            if value:
                # Receipt diagnostics only, excluded from saved reports and
                # never used to qualify sensor/control authority.
                value['worker_active']=bool(self.worker and self.worker.is_alive())
                updated=self.job.get('visual_updated_s')
                value['visual_age_s']=max(0.,self.clock()-updated) if updated is not None else None
                received=self.job.get('telemetry_received_s')
                age=self.clock()-received if received is not None else None
                value['telemetry_age_s']=age
                recent=(value['worker_active'] and value.get('state') not in TERMINAL_STATES|{'STOPPING'}
                        and age is not None and 0<=age<DISPLAY_RECEIPT_S)
                value['telemetry_status']='RECENT_WORKER_RECEIPT' if recent else 'UNAVAILABLE_OR_HISTORICAL'
                if not recent:value['telemetry']=None
            if value and value.get('isaac_display'):
                receipt_age=self.clock()-value['isaac_display'].pop('received_s',-10)
                if not self.worker or not self.worker.is_alive() or value.get('state') in TERMINAL_STATES:value['isaac_display']['status']='NO_ACTIVE_MISSION'
                elif not value.get('visual') or value['visual']['pose_room'] is None or value['visual']['state']=='LOCALIZING':value['isaac_display']['status']='CURRENT_ROOM_POSE_UNAVAILABLE'
                elif self.clock()-value.get('visual_updated_s',-10)>.5 or receipt_age>.75:value['isaac_display']['status']='ACTIVE_VISUAL_STALE'
            return {'job':value or None,'adapter_available':self.adapter_available,
                    'physical_demo_ready':False,'motion_authorized':False}

    def _prior(self,map_id,goal):
        goal=checked_goal(goal)
        prior=(self._reference(map_id) if map_id is not None else
               {'map':{'revision':None},'photo_alignment':None})
        room=self.automatic.room_loader(self.automatic.root,self.automatic.project_id)
        effective=self.automatic.photo_store.current(room)
        revision=effective['effective_revision']
        if goal['room_revision']!=revision:raise ValueError('GOAL_ROOM_REVISION_CHANGED')
        photo=prior['photo_alignment']
        if goal['mode']=='NAVIGATE_TWIN_GOAL':
            if not photo or photo['status']!='ALIGNMENT_CANDIDATE' or not photo.get('room_from_map'):
                raise ValueError('PHOTO_ALIGNMENT_NOT_SUPPORTED')
            if photo['room_base_revision']!=room['revision'] or photo['effective_objects']!=effective['objects']:
                raise ValueError('PHOTO_EFFECTIVE_REVISION_CHANGED')
        return prior,room,effective,goal

    def _reference(self,map_id):
        if isinstance(map_id,str) and map_id.startswith('survey:'):
            from .survey_reference import load_survey_reference
            loader=getattr(self.automatic,'room_scene_loader',None)
            if loader is None:raise ValueError('SURVEY_REFERENCE_CURRENT_SOURCE_REQUIRED')
            source={'room':self.automatic.room_loader(self.automatic.root,self.automatic.project_id),
                    'scene':loader(self.automatic.root,self.automatic.project_id)}
            geometry=self.automatic.geometry_loader()
            height=geometry['base_footprint_to_base_link_xyz_m'][2]+geometry['base_link_to_scan_xyz_m'][2]
            return load_survey_reference(self.automatic.root,self.automatic.project_id,map_id,
                current_source=source,height_m=height)
        return self.automatic.reopen('mission-prior',map_id)

    def readiness(self,map_id):
        prior=(self._reference(map_id) if map_id is not None else
               {'map':{'revision':None},'photo_alignment':None})
        room=self.automatic.room_loader(self.automatic.root,self.automatic.project_id)
        effective=self.automatic.photo_store.current(room)
        photo=prior['photo_alignment']
        availability=(self.adapter_factory.availability(effective['effective_revision'])
            if self.adapter_factory and hasattr(self.adapter_factory,'availability') else
            {'available':self.adapter_factory is not None,'code':'Qualified current sensor adapter required; saved pose is never restored'})
        with self.lock:self.adapter_available=availability['available']
        return {'room_revision':effective['effective_revision'],'map_revision':prior['map']['revision'],
                'photo_status':photo['status'] if photo else 'NOT_AVAILABLE','adapter_available':availability['available'],
                'current_pose_available':False,'live_start_available':False,
                'next_action':availability['code'],
                'photo_correction_available':self._supports_correction(),
                'motion_authorized':False,'physical_demo_ready':False}

    def require_goal_adapter(self):
        factory=self.adapter_factory
        if (factory is None or not callable(getattr(factory,'preview_current',None))
                or not callable(getattr(factory,'clock',None))
                or getattr(factory,'supports_current_goal_preview',False) is not True):
            raise BrokerError('current_goal_preview_unavailable',
                'A fresh idle localization/preview handoff is not configured. The saved survey pose is historical; no robot operation or SIM substitute started.',status=409)
        return factory

    def preview_goal(self,owner,scene,text,*,furniture=None,selection=None,reference_key=None,task_check=None):
        """Explicit read-only goal request. No provider is registered by HTTP.

        Never substitute a completed report pose, SIM placement or new survey.
        """
        from twinpulse_core.current_goal_preview import goal_preview
        with self.lock:
            factory=self.require_goal_adapter()
            if self.closed or self.worker and self.worker.is_alive() or self.automatic.worker and self.automatic.worker.is_alive():
                raise BrokerError('mission_busy','Wait for the owned mission or mapping to finish.',status=409)
            try:
                selected=self._reference(reference_key) if reference_key is not None else None
                sample=(factory.preview_current(owner,reference_key=reference_key) if reference_key is not None
                        else factory.preview_current(owner))
                if type(sample) is not dict or set(sample)!={'map_id','evidence','context'}:
                    raise ValueError('GOAL_PREVIEW_ADAPTER_SNAPSHOT_INVALID')
                if reference_key is not None and sample['map_id']!=reference_key:
                    raise ValueError('GOAL_PREVIEW_REFERENCE_CHANGED')
                room=self.automatic.room_loader(self.automatic.root,self.automatic.project_id)
                effective=self.automatic.photo_store.current(room)
                evidence=sample['evidence']
                if selected is not None and (evidence.get('alignment_revision')!=selected['photo_alignment']['report_revision']
                        or evidence.get('room_from_map')!=selected['photo_alignment']['room_from_map']):
                    raise ValueError('GOAL_PREVIEW_REFERENCE_ALIGNMENT_CHANGED')
                if evidence.get('room_revision')!=effective['effective_revision']:
                    raise ValueError('GOAL_PREVIEW_ROOM_CHANGED')
                if sample['context'].get('project_id')!=self.automatic.project_id:
                    raise ValueError('GOAL_PREVIEW_PROJECT_CHANGED')
                review=goal_preview(scene,text,evidence,sample['context'],factory.clock(),furniture=furniture,selection=selection,
                    revalidate_route=getattr(factory,'supports_route_revalidation',False) is True)
                if task_check and review['plan'] is not None:
                    task_check(review['plan'],evidence,sample['context'],factory.clock())
                if review['plan'] is not None:self._prior(sample['map_id'],review['plan']['goal_contract'])
                return {**review,'map_id':sample['map_id']}
            except (ValueError,KeyError,OSError,TypeError,RuntimeError) as exc:
                close=getattr(factory,'close_idle',None)
                if callable(close):
                    try:close(owner)
                    except Exception:exc.add_note('IDLE_LOCALIZATION_CLEANUP_PENDING')
                raise BrokerError('current_goal_preview_rejected',str(exc)[:160],status=409) from exc

    def start_preview(self,owner,map_id,preview,*,execution_guard=None,task_check=None):
        """Confirm the exact candidate; worker rechecks before first output."""
        from twinpulse_core.current_goal_preview import check_preview
        with self.lock:
            factory=self.adapter_factory
            if (factory is None or getattr(factory,'supports_current_goal_preview',False) is not True
                    or not callable(getattr(factory,'preview_current',None))):
                raise BrokerError('current_goal_preview_unavailable','Owned current preview adapter required.',status=409)
            try:
                if isinstance(map_id,str) and map_id.startswith('survey:'):
                    selected=self._reference(map_id)
                    resume=getattr(factory,'resume_review',None)
                    current=(resume(owner,map_id,preview) if preview.get('schema')=='current-goal-preview-2.0' and callable(resume)
                        else factory.preview_current(owner,reference_key=map_id))
                    if (current['evidence'].get('alignment_revision')!=selected['photo_alignment']['report_revision']
                            or current['evidence'].get('room_from_map')!=selected['photo_alignment']['room_from_map']):
                        raise ValueError('GOAL_PREVIEW_REFERENCE_ALIGNMENT_CHANGED')
                else:current=factory.preview_current(owner)
                if current['map_id']!=map_id:raise ValueError('GOAL_PREVIEW_REFERENCE_CHANGED')
                checked=check_preview(preview,current['evidence'],current['context'],factory.clock(),preview['goal_contract'])
                if task_check:task_check(checked,current['evidence'],current['context'],factory.clock())
            except (ValueError,KeyError,OSError,TypeError,RuntimeError) as exc:
                close=getattr(factory,'close_idle',None)
                if callable(close):
                    try:close(owner)
                    except Exception:exc.add_note('IDLE_LOCALIZATION_CLEANUP_PENDING')
                raise BrokerError('current_goal_confirmation_rejected',str(exc)[:160],status=409) from exc
            try:
                return self.start(owner,map_id,checked['goal_contract'],approved_preview=checked,execution_guard=execution_guard)
            except Exception as exc:
                close=getattr(factory,'close_idle',None)
                if callable(close):
                    try:close(owner)
                    except Exception:exc.add_note('IDLE_LOCALIZATION_CLEANUP_PENDING')
                raise

    def start(self,owner,map_id,goal,photo_policy='align_only',*,approved_preview=None,execution_guard=None):
        with self.lock:
            if self.closed:raise BrokerError('mission_closed','Mission service is closed',status=409)
            if self.worker and self.worker.is_alive():raise BrokerError('mission_busy','An owned mission is running',status=409)
            if self.automatic.worker and self.automatic.worker.is_alive():raise BrokerError('automatic_busy','Wait for mapping to finish',status=409)
            try:prior,room,effective,goal=self._prior(map_id,goal)
            except (ValueError,KeyError,OSError,TypeError) as exc:
                raise BrokerError('mission_evidence_rejected',str(exc)[:160],status=409) from exc
            if self.adapter_factory is None:
                raise BrokerError('qualified_current_adapter_required','No qualified current sensor adapter. Saved evidence cannot authorize motion.',status=409)
            if type(photo_policy) is not str or photo_policy not in {'align_only','correct_walls'}:
                raise BrokerError('mission_photo_policy_invalid','Exact photo policy required',status=400)
            if photo_policy=='correct_walls' and (goal['mode'] not in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}
                    or not self._supports_correction()):
                raise BrokerError('mission_correction_unavailable','Same-Start correction requires an owned idle commit adapter. Remote correction acknowledgement is not configured.',status=409)
            source=None
            if room.get('adapter')=='current-chat-room-1.0':
                try:
                    from .chat_inspection_visual import checked_source
                    loader=getattr(self.automatic,'room_scene_loader',None)
                    if loader is None:raise ValueError('INSPECTION_SCENE_SOURCE_UNAVAILABLE')
                    source={'room':deepcopy(room),'scene':loader(self.automatic.root,self.automatic.project_id)}
                    checked_source(source,self.automatic.project_id)
                    # The loader can race a completed edit; reject before admission.
                    if self.automatic.room_loader(self.automatic.root,self.automatic.project_id)!=room:
                        raise ValueError('INSPECTION_SCENE_SOURCE_CHANGED')
                except (ValueError,KeyError,OSError,TypeError) as exc:
                    raise BrokerError('inspection_source_rejected',str(exc)[:160],status=409) from exc
            self.stop_action=None;identity=uuid4().hex
            self.execution_guard=execution_guard
            self.last_owner_presence=self.clock()
            self.job={'owner':owner,'job_id':identity,'map_id':map_id,'goal':goal,'state':'PREPARING','started':self.clock(),
                      'objects_revision':canonical_sha256(effective['objects']),'visual_sequence':0,
                      'visual':None,'error':None,'motion_authorized':False,'physical_demo_ready':False,'events':[],
                      'report_status':'PENDING'}
            if approved_preview is not None:self.job['approved_preview']=deepcopy(approved_preview)
            if source is not None:self.job['room_source']=source
            if photo_policy=='correct_walls':
                self.job.update(original_goal=deepcopy(goal),photo_policy={'schema':'mission-photo-correction-policy-1.0',
                    'mode':'correct_walls','room_revision':goal['room_revision'],'expected_head':effective['head']})
            trace = self.diagnostics.begin('observed_mission', durable=False, mission_id=identity,
                draft_revision=goal['room_revision'], evidence_kind='automatic_mission_report', evidence_id=identity) if self.diagnostics else None
            self.worker=threading.Thread(target=self._run,args=(prior,room,effective,trace),name='tp-observed-mission',daemon=True)
            self.worker.start();return self.snapshot(owner)

    def stop(self,owner,job_id,force=False):
        with self.lock:
            self.snapshot(owner)
            if not self.job or self.job['job_id']!=job_id or not self.worker or not self.worker.is_alive():
                raise BrokerError('mission_terminal','No active owned mission',status=409)
            if force or self.stop_action is None:self.stop_action='force_stop' if force else 'finish_stop'
            self.job['state']='STOPPING';return self.snapshot(owner)

    def preview(self,owner,job_id,revision,request_id,broker):
        with self.lock:
            self.snapshot(owner)
            if self.worker and self.worker.is_alive():raise BrokerError('mission_busy','Wait for the mission report',status=409)
            if not self.job or self.job['job_id']!=job_id or self.job.get('report_revision')!=revision:
                raise BrokerError('mission_visual_stale','Refresh the owned mission report',status=409)
            descriptor={'kind':'automatic_mission_visual_v1','manifest_sha256':revision,'mission_id':job_id}
            try:
                from .automatic_mission_visual import checked_mission_visual
                _,_,_,scene,_=checked_mission_visual(self.automatic.root,self.automatic.project_id,descriptor)
            except (ValueError,OSError,KeyError,TypeError) as exc:
                raise BrokerError('mission_visual_rejected',str(exc)[:160],status=409) from exc
            artifact_id='mission-'+canonical_sha256(descriptor)
            broker.register_site_scene(artifact_id,scene,visual_preview=descriptor)
            return broker.submit(owner,{'client_request_id':request_id,'command_type':'build_site_scene',
                                       'artifact_id':artifact_id,'expected_applied_revision':scene.revision})

    def _run(self,prior,room,effective,trace=None):
        if trace is None:
            return self._run_impl(prior,room,effective)
        work = trace.child('mission_worker')
        try:
            self._run_impl(prior,room,effective,trace=work)
        except BaseException as error:
            work.finish('failed',error=error);trace.finish('failed',error=error)
            raise
        finally:
            with self.lock:
                job = dict(self.job or {})
            if job.get('error'):
                primary = trace.child(job.get('error_stage','mission_failure'))
                primary.finish('failed',error_code=job['error'])
            for code, stage, role in (('cleanup_error','cleanup_stage','cleanup'),('report_error','report_stage','storage')):
                if job.get(code):
                    note = trace.child(job.get(stage,role),role=role)
                    note.finish('failed',error_code=job[code],role=role)
            trace.bind(mission_id=job.get('native_mission_id'), robot_session_id=job.get('native_mission_id'))
            status = ('failed' if job.get('error') or job.get('cleanup_error') or job.get('report_error') else
                      'succeeded' if job.get('state')=='MISSION_ARRIVED' else
                      'cancelled' if job.get('state') in {'COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED'} else 'unknown')
            work.finish(status);trace.finish(status,error_code=job.get('error'))

    def _run_impl(self,prior,room,effective,trace=None):
        diagnostic=_MissionDiagnostic(trace)
        admission=diagnostic.begin('mission_adapter_admission',goal_room_revision=self.job['goal']['room_revision'])
        stage='ADAPTER_ADMISSION';identity=self.job['job_id'];events=[];adapter=None;mission=None
        try:
            preview=self.job.get('approved_preview')
            handoff=getattr(self.adapter_factory,'prepare_goal_handoff',None)
            adapter=(handoff(self.job['owner'],self.job['map_id'],prior,effective,preview)
                if preview is not None and callable(handoff) else self.adapter_factory(prior,room,effective,self.job['goal']))
            self.adapter=adapter
            adapter.stop_requested=lambda:self.stop_action
            if hasattr(adapter,'bind_session'):adapter.bind_session(identity)
            # Admission belongs to server-registered adapter; no client boolean.
            adapter.admit(self.job['goal'])
            if self.job.get('approved_preview') is not None:
                if hasattr(adapter,'run') and not callable(handoff):raise ValueError('REMOTE_IDLE_PREVIEW_HANDOFF_NOT_IMPLEMENTED')
                from twinpulse_core.current_goal_preview import review_source_matches
                if not review_source_matches(self.job['approved_preview']['binding']['context'],adapter.context,
                        new_session=self.job['approved_preview']['schema']=='current-goal-preview-2.0'):
                    raise ValueError('GOAL_PREVIEW_SOURCE_CONTEXT_CHANGED')
            with self.lock:self.adapter_available=True
            diagnostic.end(admission);admission=None
            revision_guard=self._revision_guard(room)
            context=adapter.context
            mission=None
            def factory(started):
                nonlocal mission
                if self.job['goal']['mode'] in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:
                    geometry=self.automatic.geometry_loader()
                    base=geometry['base_footprint_to_base_link_xyz_m']
                    mount=geometry['base_link_to_scan_xyz_m']
                    nominal=nominal_room(effective['objects'],base[2]+mount[2],effective['effective_revision'])
                    def commit_impl(result,cancelled):
                        from .mission_photo_correction import corrected_effective_objects
                        def check():
                            if (cancelled.is_set() or self.closed or self.stop_action is not None
                                    or adapter.clock()>=mission.mission.end):raise ValueError('MISSION_CORRECTION_CANCELLED_OR_EXPIRED')
                            safety()
                            if mission.stage!='ALIGN' or mission.proposed!=(0.,0.):raise ValueError('MISSION_CORRECTION_REQUIRES_IDLE')
                        check()
                        after,rebound=corrected_effective_objects(effective,nominal,result,self.job['original_goal'])
                        event=revision_guard.append_owned(lambda:self.automatic.photo_store.append(room,effective['head'],after,
                            action='apply',job_id=identity,map_revision=result['source_map_revision']))
                        with self.lock:self.job['photo_correction']={'status':'DERIVED_REVISION_APPENDED',
                            'applied_revision':event['revision'],'effective_revision':rebound['room_revision'],
                            'goal_revalidation':'NOMINAL_SECTION_CHECKED_FRESH_SENSOR_REPLAN_REQUIRED',
                            'isaac_geometry_status':'RECOMPOSITION_REQUIRED'}
                        check()
                        if self.automatic.photo_store.current(room)['effective_revision']!=rebound['room_revision']:
                            raise ValueError('MISSION_CORRECTED_ROOM_CHANGED')
                        with self.lock:
                            self.job.update(goal=deepcopy(rebound),objects_revision=rebound['room_revision'])
                        return {'schema':'mission-photo-binding-1.0','goal':rebound,'applied_revision':event['revision']}
                    def commit(result,cancelled):
                        with diagnostic.span('mission_correction_commit',cancellation=lambda:self.stop_action is not None or self.closed,
                                map_revision=result.get('source_map_revision')) as span:
                            binding=commit_impl(result,cancelled)
                            diagnostic.bind(span,correction_revision=binding['applied_revision'],goal_room_revision=binding['goal']['room_revision'])
                            return binding
                    mission=ColdStartMission(self.job['goal'],started,tracker=adapter.tracker,
                        current=lambda tracker,pose,now:tracker.update(pose,adapter.last_scan,now),
                        nominal=nominal,provenance=adapter.provenance,frame_id=adapter.frame_id,context=context,
                        photo_policy=self.job.get('photo_policy',{}).get('mode','align_only'),commit_correction=commit)
                else:
                    mission=ObservedMission(self.job['goal'],started,provider=adapter.current,
                        provenance=adapter.provenance,frame_id=adapter.frame_id,context=context,
                        approved_preview=self.job.get('approved_preview'))
                return mission
            def safety():
                checked_started=adapter.clock()
                adapter.safety()
                if self.execution_guard is not None and self.execution_guard() is not True:
                    raise ValueError('GOAL_DEMONSTRATION_RECEIPT_INVALIDATED')
                receipt_checked=adapter.clock()
                # Polling is owner liveness, not renewed per-command approval.
                # A lost browser must not leave the PC generating watch forever.
                if (getattr(adapter,'requires_owner_presence',False)
                        and self.clock()-self.last_owner_presence>2.5):
                    raise ValueError('MISSION_OWNER_CONNECTION_LOST')
                # Do not reload/hash images, USD dependencies or the ledger in
                # the 5ms heartbeat. A changed source stops; no expensive rebuild.
                revision_guard()
                adapter.last_safety_timing={'receipt_check_s':max(0.,receipt_checked-checked_started),
                    'source_guard_s':max(0.,adapter.clock()-receipt_checked)}
            def record(kind,**data):
                if len(events)>=8192:raise ValueError('MISSION_EVENT_BUDGET')
                events.append({'kind':kind,'t':adapter.clock(),'data':deepcopy(data)})
                with self.lock:
                    self.job['events']=deepcopy(events[-32:])
                    if kind=='cold_start_diagnostics':self.job['cold_start']=deepcopy(data)
                    if kind=='mission_telemetry':
                        self.job['telemetry']=deepcopy(data['telemetry'])
                        self.job['telemetry_received_s']=data['received_s']
                if kind=='cold_start_diagnostics':diagnostic.phase_observed(data)
                if kind=='mission_decision' and mission:
                    if hasattr(mission,'stage'):diagnostic.phase_observed({'stage':mission.stage})
                    with self.lock:
                        if (self.job.get('photo_correction') and getattr(mission,'stage',None)=='NAVIGATE'
                                and mission.part.current_pose_valid and mission.part.route_revision):
                            self.job['photo_correction']['goal_revalidation']='NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED'
                        if (self.job.get('photo_correction') and getattr(mission,'stage',None)=='SURVEY_COMPLETE'
                                and mission.part.current_pose_valid):
                            self.job['photo_correction']['goal_revalidation']='SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL'
                        if self.stop_action is None:self.job['state']=mission.phase
                        self.job['visual']=mission.visual(identity)
                        self.job['visual_sequence']+=1;self.job['visual_updated_s']=self.clock()
                        self.job['events']=deepcopy(events[-32:])
            stage='RUN_CURRENT_MISSION'
            if hasattr(adapter,'run'):
                if self.job.get('photo_policy'):
                    if not hasattr(adapter,'configure_correction'):raise ValueError('REMOTE_CORRECTION_ACK_NOT_CONFIGURED')
                    nominal=adapter.scope['nominal']
                    if nominal!=nominal_room(effective['objects'],nominal['height_m'],effective['effective_revision']):
                        raise ValueError('REMOTE_CORRECTION_NOMINAL_CHANGED')
                    def remote_commit_impl(result,cancelled):
                        from .mission_photo_correction import corrected_effective_objects
                        def check():
                            if cancelled.is_set() or self.closed or self.stop_action is not None:
                                raise ValueError('MISSION_CORRECTION_CANCELLED_OR_EXPIRED')
                            safety()
                            with adapter.controller.lock:
                                proposal=adapter.controller.correction_proposal
                                if (proposal is None or adapter.controller.stop_requested
                                        or adapter.controller.clock()-adapter.controller.correction_received_s>=1.):
                                    raise ValueError('CORRECTION_PC_COMMIT_EXPIRED')
                        check()
                        after,rebound=corrected_effective_objects(effective,nominal,result,self.job['original_goal'])
                        # Stop/source checks and the owned append are serialized.
                        # A later Stop may leave immutable diagnostic geometry,
                        # but can never make a late ACK resume the mission.
                        with self.lock:
                            check()
                            event=revision_guard.append_owned(lambda:self.automatic.photo_store.append(room,effective['head'],after,
                                action='apply',job_id=identity,map_revision=result['source_map_revision']))
                            self.job['photo_correction']={'status':'DERIVED_REVISION_APPENDED_AWAITING_ROBOT_ACK',
                                'applied_revision':event['revision'],'effective_revision':rebound['room_revision'],
                                'goal_revalidation':'NOMINAL_SECTION_CHECKED_FRESH_SENSOR_REPLAN_REQUIRED',
                                'isaac_geometry_status':'RECOMPOSITION_REQUIRED'}
                        check()
                        if self.automatic.photo_store.current(room)['effective_revision']!=rebound['room_revision']:
                            raise ValueError('MISSION_CORRECTED_ROOM_CHANGED')
                        return {'schema':'mission-photo-binding-1.0','goal':rebound,'applied_revision':event['revision']}
                    def remote_commit(result,cancelled):
                        with diagnostic.span('mission_correction_commit',cancellation=lambda:self.stop_action is not None or self.closed,
                                map_revision=result.get('source_map_revision')) as span:
                            binding=remote_commit_impl(result,cancelled)
                            refs={'correction_revision':binding['applied_revision'],'goal_room_revision':binding['goal']['room_revision']}
                            diagnostic.bind(span,**refs)
                            diagnostic.wait_ack(**refs)
                            return binding
                    def accepted(binding):
                        safety()
                        with self.lock:
                            if self.stop_action is not None:raise ValueError('MISSION_CORRECTION_CANCELLED_OR_EXPIRED')
                            correction=self.job.get('photo_correction')
                            if (not correction or binding['applied_revision']!=correction['applied_revision']
                                    or binding['goal']['room_revision']!=correction['effective_revision']):
                                raise ValueError('REMOTE_CORRECTION_BINDING_NOT_OWNED')
                            self.job.update(goal=deepcopy(binding['goal']),objects_revision=binding['goal']['room_revision'])
                            correction['status']='ROBOT_IDLE_BINDING_ACKNOWLEDGED'
                        diagnostic.accepted_ack(correction_revision=binding['applied_revision'],goal_room_revision=binding['goal']['room_revision'])
                    adapter.configure_correction(remote_commit,accepted)
                def visual(value):
                    with self.lock:
                        native=getattr(adapter,'identity',identity)
                        if value['session_id']!=native:raise ValueError('MISSION_NATIVE_VISUAL_IDENTITY_CHANGED')
                        # Retain native bytes/hash in reports. The App owns a
                        # separate job ID; only the derived display envelope is rebound.
                        self.job['native_mission_id']=native
                        if (self.job.get('photo_correction') and self.job['goal']['mode']=='SURVEY_ONLY'
                                and self.job['photo_correction'].get('status')=='ROBOT_IDLE_BINDING_ACKNOWLEDGED'
                                and (self.job.get('cold_start') or {}).get('stage')=='SURVEY_COMPLETE'
                                and value['room_revision']==self.job['goal']['room_revision']
                                and value['state']=='ARRIVED' and value['pose_room'] is not None
                                and value['goal_room'] is None and not value['route_room'] and value['route_revision'] is None):
                            self.job['photo_correction']['goal_revalidation']='SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL'
                        if (self.job.get('photo_correction') and value['room_revision']==self.job['goal']['room_revision']
                                and value['state'] in {'DRIVING','REPLANNING','ARRIVED'} and value['pose_room'] is not None
                                and value['route_revision'] is not None):
                            self.job['photo_correction']['goal_revalidation']='NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED'
                        if self.stop_action is None:self.job['state']=value['state']
                        self.job['visual']=deepcopy(value);self.job['events']=deepcopy(events[-32:])
                        self.job['visual_sequence']+=1;self.job['visual_updated_s']=self.clock()
                    # The native protocol exposes SURVEYING, not outbound/return
                    # boundaries. Never invent unobserved robot substage times.
                    phase={'SURVEYING':'SURVEY','ALIGNING_PHOTO':'ALIGN','DRIVING':'NAVIGATE','REPLANNING':'NAVIGATE',
                           'ARRIVED':'SURVEY_COMPLETE' if self.job['goal']['mode']=='SURVEY_ONLY' else 'NAVIGATE'}.get(value['state'])
                    if phase:diagnostic.phase_observed({'stage':phase,'map_revision':value['map_revision'],
                        'alignment_revision':value['alignment_revision']})
                result=adapter.run(record=record,visual=visual,safety=safety)
                # The terminal diagnostic can follow the last visual on the
                # pipe. Reconcile only the acknowledged same-revision result;
                # the pose remains historical after worker completion.
                with self.lock:
                    current=self.job.get('visual') or {}
                    correction=self.job.get('photo_correction') or {}
                    if (result.get('status')=='MISSION_ARRIVED' and self.job['goal']['mode']=='SURVEY_ONLY'
                            and correction.get('status')=='ROBOT_IDLE_BINDING_ACKNOWLEDGED'
                            and (self.job.get('cold_start') or {}).get('stage')=='SURVEY_COMPLETE'
                            and current.get('room_revision')==self.job['goal']['room_revision']
                            and current.get('state')=='ARRIVED' and current.get('pose_room') is not None
                            and current.get('goal_room') is None and not current.get('route_room')
                            and current.get('route_revision') is None):
                        correction['goal_revalidation']='SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL'
            else:
                # Same standalone reviewed worker; isolated local fake transport
                # only. Physical adapters run this loop on the robot, not PC.
                import sys
                from .runtime_paths import resource_root
                robot=resource_root()/'packages/twinpulse_robot_safety'
                if str(robot) not in sys.path:sys.path.insert(0,str(robot))
                from mission_runtime import run_mission
                result=run_mission(adapter.link,adapter.incoming,adapter.output,adapter.request,
                    record=record,consume=adapter.consume,clock=adapter.clock,transport_safety=safety,mission_factory=factory)
            with self.lock:self.job.update(state=result['status'],result=result,ended=self.clock())
        except Exception as exc:
            code=str(exc)
            if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_PROCESSING_FAILED'
            diagnostic.end(admission,'failed',error_code=code,error_type=type(exc).__name__);admission=None
            with self.lock:
                if stage=='ADAPTER_ADMISSION':self.adapter_available=False
                self.job.update(state='FAILED',error=code,error_stage=stage,ended=self.clock())
                from twinpulse_core.cleanup_diagnostics import checked_notes
                native=checked_notes(getattr(exc,'mission_cleanup_errors',[]))
                if native:self.job.update(native_cleanup_errors=native,cleanup_error=native[0]['code'],cleanup_stage='NATIVE_CLEANUP')
        finally:
            with self.lock:
                observed=dict(self.job)
            outcome=('failed' if observed.get('error') else 'succeeded' if observed.get('state')=='MISSION_ARRIVED' else
                     'cancelled' if observed.get('state') in {'COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED'} else 'unknown')
            diagnostic.close(outcome,error_code=observed.get('error'))
            cleanup=diagnostic.begin('mission_adapter_cleanup',role='cleanup')
            # Cleanup/transport failures cannot skip independent stop/OFF.
            if adapter:
                try:adapter.close()
                except Exception as exc:
                    code=str(exc)
                    if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_ADAPTER_CLEANUP_FAILED'
                    with self.lock:
                        self.job.update(state='FAILED',cleanup_error=code,cleanup_stage='ADAPTER_CLEANUP',
                                        cleanup_error_type=type(exc).__name__[:80],ended=self.clock())
                        if not self.job.get('error'):
                            self.job.update(error=code,error_stage='ADAPTER_CLEANUP')
            elif self.job.get('approved_preview') is not None:
                close=getattr(self.adapter_factory,'close_idle',None)
                if callable(close):
                    try:close(self.job['owner'])
                    except Exception as exc:
                        with self.lock:self.job.update(cleanup_error=str(exc)[:120],cleanup_stage='ADAPTER_CLEANUP')
            diagnostic.end(cleanup,'failed' if self.job.get('cleanup_error') else 'succeeded' if adapter else 'skipped',
                role='cleanup',error_code=self.job.get('cleanup_error'))
            report_trace=diagnostic.begin('mission_report_save',role='storage',evidence_kind='automatic_mission_report',evidence_id=identity)
            try:
                # Renderer receipts are transient state. Copy under the shared
                # lock so engine polling cannot mutate a hash-bound saved body.
                with self.lock:
                    # An adapter may raise before record(mission_decision), or
                    # cleanup may fail after arrival. Never save the preceding
                    # active pose/cloud as a current failed/stopped frame. Raw
                    # decisions and the historical trajectory remain intact.
                    if self.job['state']!='MISSION_ARRIVED' and self.job.get('visual'):
                        visual=deepcopy(self.job['visual'])
                        visual.update(state=self.job['state'],pose_room=None,scan_room=[],route_room=[],route_revision=None)
                        visual['revision']=canonical_sha256({k:v for k,v in visual.items() if k!='revision'})
                        self.job['visual']=visual;self.job['visual_sequence']+=1
                    body=deepcopy({k:v for k,v in self.job.items() if k not in
                                   {'owner','started','ended','events','isaac_display','report_status'}})
                body.update(schema='automatic-mission-report-1.0',project_id=self.automatic.project_id,
                    prior_map_revision=prior['map']['revision'],room_base_revision=room['revision'],events=events,
                    provenance=getattr(adapter,'provenance','UNAVAILABLE'),physical_validation='NOT_RUN')
                fit=getattr(mission,'fit_result',None) or getattr(adapter,'fit_result',None)
                if fit:
                    body['photo_alignment']=deepcopy(fit)
                if mission and getattr(mission,'survey_map',None):
                    body['survey_map']=deepcopy(mission.survey_map)
                elif adapter and getattr(adapter,'survey_map',None):
                    body['survey_map']=deepcopy(adapter.survey_map)
                body['revision']=canonical_sha256(body)
                path=self.automatic.root/'artifacts'/'automatic-mission'/self.automatic.project_id/f'{identity}.json'
                if path.resolve()!=path or any(p.is_symlink() for p in path.parents):raise ValueError('MISSION_REPORT_PATH')
                path.parent.mkdir(parents=True,exist_ok=True)
                text=__import__('json').dumps(body,allow_nan=False,sort_keys=True)
                if len(text.encode())>4*1024*1024:raise ValueError('MISSION_REPORT_BUDGET')
                with path.open('x',encoding='utf-8') as stream:stream.write(text)
                with self.lock:self.job.update(report_revision=body['revision'],report_status='SAVED')
                diagnostic.end(report_trace,role='storage',persisted=True)
            except Exception as exc:
                code=str(exc)
                if isinstance(exc,OSError):
                    import errno
                    code={errno.ENOSPC:'MISSION_REPORT_STORAGE_FULL',
                          errno.EDQUOT:'MISSION_REPORT_STORAGE_QUOTA',
                          errno.EACCES:'MISSION_REPORT_PERMISSION_DENIED',
                          errno.EPERM:'MISSION_REPORT_PERMISSION_DENIED',
                          errno.EROFS:'MISSION_REPORT_READ_ONLY'}.get(exc.errno,'MISSION_REPORT_SAVE_FAILED')
                elif not re.fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_REPORT_SAVE_FAILED'
                diagnostic.end(report_trace,'failed',role='storage',error_code=code,error_type=type(exc).__name__,persisted=False)
                with self.lock:
                    # Saving happens after independent adapter halt/cleanup.
                    # Its later failure must not leave the preceding arrival
                    # pose/cloud labeled current, or replace the first cause.
                    self.job.update(state='FAILED',error_record_failed=True,report_status='FAILED',
                        report_error=code,report_stage='REPORT_SAVE',report_error_type=type(exc).__name__[:80],
                        report_errno=exc.errno if isinstance(exc,OSError) and type(exc.errno) is int else None)
                    if not self.job.get('error'):self.job.update(error=code,error_stage='REPORT_SAVE')
                    if self.job.get('visual'):
                        visual=deepcopy(self.job['visual'])
                        visual.update(state='FAILED',pose_room=None,scan_room=[],route_room=[],route_revision=None)
                        visual['revision']=canonical_sha256({k:v for k,v in visual.items() if k!='revision'})
                        self.job['visual']=visual;self.job['visual_sequence']+=1

    def close(self):
        with self.lock:self.closed=True;self.stop_action='force_stop'
        if self.worker:self.worker.join(1.)
        close_idle=getattr(self.adapter_factory,'close_idle',None)
        if callable(close_idle):close_idle()

    def active_visual(self,engine_id,stage_epoch,objects_revision,display_result=None):
        """Engine reads only; never refreshes the browser owner's presence."""
        from twinpulse_core.active_mission_visual import checked_display_result
        display_result=checked_display_result(display_result)
        with self.lock:
            job=self.job
            if not job:return {'frame':None,'code':'NO_ACTIVE_MISSION'}
            blocked=('NO_ACTIVE_MISSION' if not self.worker or not self.worker.is_alive() or job.get('state') in TERMINAL_STATES else
                     'NO_ACTIVE_MISSION' if self.stop_action is not None or self.closed else
                     'CURRENT_ROOM_POSE_UNAVAILABLE' if not job.get('visual') or job['visual']['pose_room'] is None or job['visual']['state']=='LOCALIZING' else
                     'ACTIVE_VISUAL_STALE' if self.clock()-job.get('visual_updated_s',-10)>.5 else None)
            if blocked:
                # Repeated old renderer receipts cannot freshen expired sensor
                # evidence or label a terminal mission as a current robot pose.
                if job.get('isaac_display'):job['isaac_display']['status']=blocked
                return {'frame':None,'code':blocked}
            correction=job.get('photo_correction');original=job.get('original_goal')
            if correction and original and objects_revision in {original['room_revision'],job['objects_revision']}:
                # A post-build failure may already report the new geometry hash.
                # Preserve its cause and block pose display in either revision.
                if (display_result and display_result['job_id']==job['job_id']
                        and display_result['sequence']<=job['visual_sequence']
                        and display_result['status']=='ACTIVE_GEOMETRY_RENDER_FAILED'):
                    correction['isaac_geometry_status']='ACTIVE_GEOMETRY_RENDER_FAILED'
                    correction['error_code']=display_result.get('error_code','ACTIVE_GEOMETRY_RENDER_FAILED')
                    correction['error_type']=display_result.get('error_type','Error')
                    job['isaac_display']={**display_result,'engine_session_id':engine_id,'stage_epoch':stage_epoch,'received_s':self.clock()}
                if correction.get('isaac_geometry_status')=='ACTIVE_GEOMETRY_RENDER_FAILED':
                    return {'frame':None,'code':'ACTIVE_GEOMETRY_RENDER_FAILED'}
            if objects_revision!=job['objects_revision']:
                if (not correction or not original or objects_revision!=original['room_revision']
                        or correction['goal_revalidation']!='NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED'):
                    return {'frame':None,'code':'ISAAC_ROOM_GEOMETRY_CHANGED'}
                from twinpulse_core.active_mission_visual import checked_active_geometry
                body={'schema':'active-mission-geometry-1.0','engine_session_id':engine_id,'stage_epoch':stage_epoch,
                    'project_id':self.automatic.project_id,'job_id':job['job_id'],'sequence':job['visual_sequence'],
                    'previous_objects_revision':objects_revision,'objects_revision':job['objects_revision'],
                    'correction_revision':correction['applied_revision']}
                correction['isaac_geometry_status']='WAITING_FOR_OWNED_ISAAC_RECOMPOSITION'
                return {'frame':None,'code':'ISAAC_ROOM_RECOMPOSITION_REQUIRED',
                        'geometry':checked_active_geometry({**body,'revision':canonical_sha256(body)})}
            if (display_result and display_result['job_id']==job['job_id']
                    and display_result['sequence']<=job['visual_sequence']
                    and display_result['status']=='ACTIVE_GEOMETRY_COMPOSED_NOT_CURRENT' and job.get('photo_correction')):
                job['photo_correction']['isaac_geometry_status']='OWNED_ISAAC_GEOMETRY_COMPOSED'
            if (display_result and display_result['job_id']==job['job_id']
                and display_result['sequence']<=job['visual_sequence']):
                previous=job.get('isaac_display')
                if (not previous or display_result['sequence']>previous['sequence'] or
                    (display_result['sequence']==previous['sequence'] and display_result['status']!=previous['status'])):
                    job['isaac_display']={**display_result,'engine_session_id':engine_id,'stage_epoch':stage_epoch,'received_s':self.clock()}
            display_visual=deepcopy(job['visual'])
            if display_visual['session_id']!=job['job_id']:
                if display_visual['session_id']!=job.get('native_mission_id'):
                    raise ValueError('MISSION_NATIVE_VISUAL_IDENTITY_CHANGED')
                job['native_visual_binding']={'native_mission_id':display_visual['session_id'],
                    'native_visual_revision':display_visual['revision'],'app_job_id':job['job_id']}
                display_visual['session_id']=job['job_id']
                display_visual['revision']=canonical_sha256({k:v for k,v in display_visual.items() if k!='revision'})
            body={'schema':'active-mission-frame-1.0','engine_session_id':engine_id,'stage_epoch':stage_epoch,
                'project_id':self.automatic.project_id,'objects_revision':job['objects_revision'],
                'job_id':job['job_id'],'sequence':job['visual_sequence'],'visual':display_visual}
            from twinpulse_core.active_mission_visual import checked_active_frame
            frame=checked_active_frame({**body,'revision':canonical_sha256(body)})
            return {'frame':frame,'code':'CURRENT_VISUAL_CANDIDATE_NOT_CALIBRATED'}

    def _supports_correction(self):
        return (getattr(self.adapter_factory,'supports_local_correction',False) is True
                or getattr(self.adapter_factory,'supports_remote_correction',False) is True)

    def _revision_guard(self,room):
        root=self.automatic.root;pid=self.automatic.project_id
        ledger=self.automatic.photo_store._ledger(room)
        project=root/'projects'/pid
        def fingerprint():
            # Conversation status/questions are not geometric input. Writing
            # a Confirm or 5s summary must not look like editing the room.
            # Every other project/recipe/asset/ledger and memory token remains
            # guarded, including additions, deletion and metadata changes.
            files=[p for p in project.glob('*.json') if p.name!='project.conversation.json']+list(ledger.glob('*.json'))
            if pid=='default':
                from .bedroom_review import ROOT
                files+=list((ROOT/'artifacts'/'photo-scan-review-20260927').glob('*.jpg'))
            else:files+=list((project/'assets').glob('*'))
            if len(files)>256:raise ValueError('MISSION_SOURCE_FILE_BUDGET')
            result=[]
            token=getattr(self.automatic,'room_source_token',None)
            if token:result.append(('current_chat_room',token()))
            for path in sorted(files):
                if path.is_symlink():raise ValueError('MISSION_SOURCE_PATH_CHANGED')
                stat=path.stat();result.append((str(path),stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size))
            return result
        from .mission_photo_correction import MissionSourceGuard
        return MissionSourceGuard(fingerprint,ledger)
