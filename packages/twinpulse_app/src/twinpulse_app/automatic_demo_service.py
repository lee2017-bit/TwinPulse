# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned offline automatic session. Opening or polling never starts a robot.

One bounded worker, causal input only. Live and closed-loop callers can use the
same core runner; this product route accepts verified saved ROS input only.
"""
from copy import deepcopy
from pathlib import Path
import threading
import time
from uuid import uuid4

from twinpulse_core.automatic_mapping import AutomaticMapping
from twinpulse_core.automatic_photo_alignment import align_photo_map, POLICIES
from .automatic_photo_store import AutomaticPhotoStore, load_automatic_room
from .saved_mapping_evidence import saved_observation_source
from .robot_geometry_evidence import load_geometry_evidence
from .project_store import AutomaticMapStore
from .command_broker import BrokerError
from .recorded_replay import RecordedReplayPacer


class AutomaticDemoService:
    def __init__(self, root, project_id, *, source_factory=saved_observation_source,
                 geometry_loader=load_geometry_evidence, room_loader=load_automatic_room, clock=time.monotonic):
        self.root=Path(root).resolve() if root is not None else None;self.project_id=project_id
        self.source_factory=source_factory;self.geometry_loader=geometry_loader;self.clock=clock
        self.room_loader=room_loader
        self.lock=threading.Condition(threading.RLock());self.job=None;self.worker=None;self.closed=False
        self.store=AutomaticMapStore(self.root,project_id) if self.root else None
        self.photo_store=AutomaticPhotoStore(self.root,project_id) if self.root else None
        self.epoch=0;self.generation=0;self.command='RUN';self.seek_sequence=-1
        self.mission_active=lambda:False

    def _owned(self, owner, job_id=None):
        if not self.job or self.job['owner']!=owner or (job_id is not None and self.job['job_id']!=job_id):
            raise BrokerError('automatic_session_not_owned','No automatic session owned by this connection',status=409)

    def snapshot(self, owner):
        with self.lock:
            if self.job is None:return {'job':None,'motion_authorized':False}
            self._owned(owner)
            result=deepcopy({k:v for k,v in self.job.items() if k not in {'owner','request'}})
            result['elapsed_s']=round(self.job.get('ended',self.clock())-self.job['started'],3)
            result.pop('started',None);result.pop('ended',None)
            return {'job':result,'motion_authorized':False}

    def start(self, owner, source_job_id, reference_map_id=None, photo_policy='disabled', replay_mode='as_fast'):
        if self.root is None:raise BrokerError('automatic_unavailable','Saved session root is unavailable',status=409)
        import re
        if not isinstance(source_job_id,str) or re.fullmatch('[a-f0-9]{32}',source_job_id) is None:
            raise BrokerError('automatic_request_invalid','Exact saved session ID required',status=400)
        if reference_map_id is not None and (not isinstance(reference_map_id,str) or re.fullmatch('[a-f0-9]{32}',reference_map_id) is None):
            raise BrokerError('automatic_request_invalid','Exact saved map ID required',status=400)
        if not isinstance(photo_policy,str) or photo_policy not in POLICIES:
            raise BrokerError('automatic_request_invalid','Unsupported photo correction policy',status=400)
        if type(replay_mode) is not str or replay_mode not in {'as_fast','recorded_1x'}:
            raise BrokerError('automatic_request_invalid','Unsupported recorded replay mode',status=400)
        with self.lock:
            if self.closed:raise BrokerError('automatic_closed','Automatic session service closed',status=409)
            if self.mission_active():raise BrokerError('mission_busy','Stop the current mission before replacing its map',status=409)
            if self.worker and self.worker.is_alive():raise BrokerError('automatic_busy','An automatic session is running; cancel or wait',status=409)
            self.epoch+=1;self.generation+=1;self.command='RUN';self.seek_sequence=-1
            self.job={'owner':owner,'job_id':uuid4().hex,'source_job_id':source_job_id,'reference_map_id':reference_map_id,
                      'request':(source_job_id,reference_map_id,photo_policy),'photo_policy':photo_policy,'replay_mode':replay_mode,'replay_timing':None,'started':self.clock(),'state':'PREPARING',
                      'epoch':self.epoch,'progress_sequence':-1,'result':None,'map_id':None,'error':None,
                      'motion_authorized':False,'physical_demo_ready':False,'mode':'RECORDED_CAUSAL_REPLAY'}
            self.worker=threading.Thread(target=self._run,name='tp-automatic-mapping',daemon=True);self.worker.start()
            return self.snapshot(owner)

    def control(self, owner, job_id, action, sequence=None):
        with self.lock:
            self._owned(owner,job_id)
            active=bool(self.worker and self.worker.is_alive())
            if action not in {'pause','resume','seek','cancel','reposition'}:raise BrokerError('automatic_action_invalid','Unsupported automatic action',status=400)
            if not active:raise BrokerError('automatic_terminal','This session ended; start a new session',status=409)
            if action=='resume' and self.command!='PAUSE':raise BrokerError('automatic_not_paused','Session is not paused',status=409)
            if action=='seek':
                if type(sequence) is not int or not -1<=sequence<=65536:raise BrokerError('automatic_seek_invalid','Seek requires an original sequence within budget',status=400)
                self.seek_sequence=sequence
            elif action in {'pause','reposition'}:self.seek_sequence=self.job['progress_sequence']
            self.generation+=1;self.epoch+=1;self.job['epoch']=self.epoch;self.job['result']=None;self.job['map_id']=None
            self.command='CANCEL' if action=='cancel' else 'PAUSE' if action in {'pause','seek','reposition'} else 'RUN'
            self.job['state']='CANCELLING' if action=='cancel' else 'PAUSED' if self.command=='PAUSE' else 'PREPARING'
            self.lock.notify_all();return self.snapshot(owner)

    def reopen(self, owner, map_id):
        if self.store is None:raise BrokerError('automatic_unavailable','Saved session root is unavailable',status=409)
        try:
            value=self.store.load(map_id)
            report_path=self.photo_store.folder/'reports'/f'{map_id}.json'
            photo=self.photo_store.report(map_id) if report_path.exists() else None
            if photo and photo['source_map_revision']!=value['revision']:raise ValueError('PHOTO_MAP_REVISION_CHANGED')
            # Reopening a historical report never restores a current pose or control authority.
            return {'map_id':map_id,'map':value,'photo_alignment':photo,'motion_authorized':False,'physical_demo_ready':False,'pose_candidate':None}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            raise BrokerError('automatic_map_rejected',str(exc)[:180],status=409) from exc

    def maps(self):
        if self.store is None:return {'maps':[]}
        try:return {'maps':self.store.list_maps()}
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise BrokerError('automatic_map_rejected',str(exc)[:180],status=409) from exc

    def rollback_photo(self,owner,job_id,expected_revision):
        with self.lock:
            if self.mission_active():raise BrokerError('mission_busy','Stop the current mission before changing its room',status=409)
            if self.job:self._owned(owner)
            if self.worker and self.worker.is_alive():raise BrokerError('automatic_busy','Wait for the session to end',status=409)
            try:
                report=self.photo_store.report(job_id)
                if self.store.load(job_id)['revision']!=report['source_map_revision']:raise ValueError('PHOTO_MAP_REVISION_CHANGED')
                if not report.get('applied_revision') or report['applied_revision']!=expected_revision:
                    raise ValueError('PHOTO_APPLIED_REVISION_REQUIRED')
                room=self.room_loader(self.root,self.project_id)
                if room['revision']!=report['room_base_revision']:raise ValueError('PHOTO_ROOM_CHANGED')
                current=self.photo_store.current(room)
                if current['head']!=expected_revision:raise ValueError('PHOTO_LEDGER_HEAD_CHANGED')
                event=self.photo_store.append(room,expected_revision,current['events'][-1]['before_objects'],
                         action='rollback',job_id=job_id,map_revision=report['source_map_revision'])
                result=deepcopy(report)
                result['source_report_revision']=result.pop('report_revision')
                result.update(geometry_status='ROLLED_BACK',applied_revision=None,rollback_revision=event['revision'],
                              effective_objects=event['objects'],goal_revalidation_required=True)
                if self.job and self.job['job_id']==job_id and self.job.get('result'):
                    self.job['result']['photo_alignment']=result
                return {**self.snapshot(owner),'photo_alignment':result,'map_id':job_id}
            except (ValueError,OSError,KeyError,TypeError) as exc:
                raise BrokerError('automatic_photo_rollback_rejected',str(exc)[:180],status=409) from exc

    def close(self):
        with self.lock:self.closed=True;self.command='CANCEL';self.generation+=1;self.lock.notify_all()
        if self.worker:self.worker.join(timeout=1.)

    def _publish(self, token, processor):
        with self.lock:
            if token!=self.generation or self.command!='RUN':return False
            result=processor.snapshot(include_map=True)
            self.job.update(result=result,state=result['state'],progress_sequence=processor.last_sequence)
            return True

    def _run(self):
        while not self._run_cycle():
            pass  # Only a superseded epoch restarts, never a current failure.

    def _run_cycle(self):
        token=None;stage='WAITING';processor=None;pacer=None
        try:
            while True:
                with self.lock:
                    while self.command=='PAUSE' and not self.closed:self.lock.wait(.25)
                    if self.command=='CANCEL' or self.closed:
                        self.job.update(state='CANCELLED',result=None,ended=self.clock());return True
                    token=self.generation;source_id,reference_id,photo_policy=self.job['request'];seek=self.seek_sequence
                stage='VERIFY_SOURCE';source=self.source_factory(self.root,self.project_id,source_id)
                if self.job['replay_mode']=='recorded_1x' and source.window.context['origin']!='recorded_ros':
                    raise ValueError('RECORDED_REPLAY_ORIGIN_REQUIRED')
                geometry=self.geometry_loader()
                base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
                # base_footprint XY is nominal; unsupported/nonzero rotations reject in the existing model loader.
                offset=[mount[0]+base[0],mount[1]+base[1],0.]
                stage='LOAD_PHOTO_ROOM';room=None;effective=None
                if photo_policy!='disabled':
                    room=self.room_loader(self.root,self.project_id);effective=self.photo_store.current(room)
                stage='LOAD_REFERENCE';reference=self.store.load(reference_id) if reference_id else None
                if reference and reference.get('nominal_geometry_revision')!=geometry['revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
                if reference:
                    ref_source=reference.get('source_job_id')
                    if not ref_source:raise ValueError('MAP_REFERENCE_PROVENANCE_MISSING')
                    verified_reference=self.source_factory(self.root,self.project_id,ref_source)
                    if verified_reference.window.context['source_revision']!=reference['source_revision']:raise ValueError('MAP_REFERENCE_SOURCE_CHANGED')
                processor=AutomaticMapping(source.window.context,offset,reference=reference)
                started=self.clock();last_publish=started;restart=False
                pacer=RecordedReplayPacer(started) if self.job['replay_mode']=='recorded_1x' else None
                stage='PROCESS_OBSERVATIONS'
                for event in source:
                    with self.lock:
                        if token!=self.generation or self.closed:restart=True;break
                    if pacer:
                        stage='PACE_RECORDED_RECEIPT'
                        target=pacer.target(event.get('receipt_monotonic_ns',source.window.last_receipt))
                        with self.lock:
                            while token==self.generation and not self.closed and self.command=='RUN':
                                delay=target-self.clock()
                                if delay<=0:break
                                self.job.update(state='REPLAYING_1X',replay_timing=pacer.summary(self.clock()))
                                before_wait=self.clock();self.lock.wait(min(delay,.05))
                                # Only actual explicit pacing wait is excluded. Source decoding,
                                # matching, publication and fit still consume the original budget.
                                pacer.waited(self.clock()-before_wait)
                            if token!=self.generation or self.closed:restart=True;break
                        pacer.delivered(target,self.clock())
                    stage='PROCESS_OBSERVATIONS'
                    if self.clock()-started-(pacer.waited_s if pacer else 0)>120:raise ValueError('AUTOMATIC_PROCESSING_TIME_BUDGET')
                    processor.consume(event)
                    if pacer:
                        with self.lock:self.job['replay_timing']=pacer.summary(self.clock())
                    if event['sequence']>=seek and self.clock()-last_publish>=.20:
                        self._publish(token,processor);last_publish=self.clock()
                if restart:continue
                processor.finish()
                if pacer and self.clock()-started-pacer.waited_s>120:
                    raise ValueError('AUTOMATIC_PROCESSING_TIME_BUDGET')
                # Reverify immutable bytes and nominal model before saving derived output.
                stage='REVERIFY_SOURCE';again=self.source_factory(self.root,self.project_id,source_id)
                if again.window.context!=source.window.context:raise ValueError('AUTOMATIC_SOURCE_CHANGED')
                if self.geometry_loader()['revision']!=geometry['revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
                if reference:
                    if self.store.load(reference_id)['revision']!=reference['revision']:raise ValueError('MAP_REFERENCE_CHANGED')
                    if self.source_factory(self.root,self.project_id,reference['source_job_id']).window.context!=verified_reference.window.context:
                        raise ValueError('MAP_REFERENCE_SOURCE_CHANGED')
                photo=None
                if room is not None:
                    stage='ALIGN_PHOTO_STRUCTURE'
                    with self.lock:
                        if token!=self.generation:continue
                        self.job['state']='ALIGNING_PHOTO'
                    photo=align_photo_map(processor.saved_map(),effective['objects'],
                        height_m=base[2]+mount[2],policy=photo_policy,diagnostics=True)
                    photo.update(room_base_revision=room['revision'],photo_revision=room['photo_revision'],
                                 source_job_id=source_id,nominal_geometry_revision=geometry['revision'],
                                 epoch=self.epoch,applied_revision=None,effective_objects=effective['objects'])
                    if self.clock()-started-(pacer.waited_s if pacer else 0)>150:raise ValueError('AUTOMATIC_PHOTO_TIME_BUDGET')
                    stage='REVERIFY_PHOTO_ROOM'
                    if self.room_loader(self.root,self.project_id)['revision']!=room['revision']:raise ValueError('PHOTO_ROOM_CHANGED')
                    if self.photo_store.current(room)['head']!=effective['head']:raise ValueError('PHOTO_LEDGER_HEAD_CHANGED')
                    # Fit cannot outlive its input or nominal geometry changes.
                    if self.source_factory(self.root,self.project_id,source_id).window.context!=source.window.context:
                        raise ValueError('AUTOMATIC_SOURCE_CHANGED')
                    if self.geometry_loader()['revision']!=geometry['revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
                with self.lock:
                    if token!=self.generation or self.closed:continue
                    if seek>processor.last_sequence:raise ValueError('AUTOMATIC_SEEK_NOT_RECORDED')
                    body=processor.saved_map();body['nominal_geometry_revision']=geometry['revision']
                    body['source_job_id']=source_id
                    body['source_status']=getattr(source,'original_status','UNAVAILABLE')
                    body['source_reason']=getattr(source,'original_reason',None)
                    body['processing_summary']=processor.snapshot()
                    from twinpulse_core.revisions import canonical_sha256
                    body.pop('revision');body['revision']=canonical_sha256(body)
                    stage='SAVE_MAP';self.store.save(self.job['job_id'],body)
                    self.job['map_id']=self.job['job_id']
                    if photo is not None:
                        photo['source_map_revision']=body['revision']
                        stage='SAVE_PHOTO_ALIGNMENT'
                        if photo_policy=='correct_walls' and photo.get('geometry_status')=='BOUNDED_WALL_PROPOSAL_VALIDATED':
                            event=self.photo_store.append(room,effective['head'],photo['corrected_objects'],action='apply',
                                job_id=self.job['job_id'],map_revision=body['revision'])
                            photo.update(applied_revision=event['revision'],geometry_status='AUTO_APPLIED_DERIVED_REVISION',
                                         effective_objects=event['objects'],goal_revalidation_required=True)
                        photo=self.photo_store.save_report(self.job['job_id'],photo)
                    result=processor.snapshot(include_map=True)
                    result.update(source_status=getattr(source,'original_status','UNAVAILABLE'),
                                  source_reason=getattr(source,'original_reason',None),
                                  nominal_geometry_revision=geometry['revision'],photo_alignment=photo)
                    self.job.update(state='COMPLETED',result=result,map_id=self.job['job_id'],progress_sequence=processor.last_sequence,ended=self.clock())
                    if pacer:self.job['replay_timing']=pacer.summary(self.clock())
                    return True
        except Exception as exc:
            # API never emits tracebacks, paths, credentials or arbitrary source exception text.
            code=exc.code.upper() if isinstance(exc,BrokerError) else str(exc)
            import re
            if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='AUTOMATIC_PROCESSING_FAILED'
            with self.lock:
                if token!=self.generation:return False
                self.job.update(state='FAILED',error=code,error_stage=stage,result=None,ended=self.clock())
                if pacer:self.job['replay_timing']=pacer.summary(self.clock())
                if self.store:
                    try:self.store.save_failure(self.job['job_id'],{
                        'schema':'automatic-failure-1.0','project_id':self.project_id,'job_id':self.job['job_id'],
                        'source_job_id':self.job['source_job_id'],'epoch':self.epoch,
                        'sequence':processor.last_sequence if processor else self.job['progress_sequence'],
                        'stage':stage,'error':code,'errno':exc.errno if isinstance(exc,OSError) else None,
                        'diagnostics':processor.snapshot() if processor else None,'replay_timing':self.job.get('replay_timing'),'motion_authorized':False})
                    except (OSError,ValueError):self.job['error_record_failed']=True
                return True
