# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned task orchestration over successful bounded goal workers; no gate renewal.

Only explicit chat approval starts a task. Journals are history, never restored
execution permission. Every leg uses the existing fresh/SIM/exact-handoff path.
"""
from copy import deepcopy
import json
import math
import os
from threading import Event, RLock, Thread
import time
from uuid import uuid4
from twinpulse_core.revisions import canonical_sha256
from .command_broker import BrokerError

TERMINAL={'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}


def resource_check(evidence, now):
    """Robot monotonic receipt, not the PC's saved readiness voltage."""
    value=evidence.get('task_resources') if isinstance(evidence,dict) else None
    if not isinstance(value,dict):raise ValueError('TASK_BATTERY_UNAVAILABLE')
    finite=lambda v:type(v) in (int,float) and math.isfinite(v)
    if (value.get('schema')!='task-resources-1.0' or not finite(value.get('sample_s'))
            or not finite(now) or not 0<=now-value['sample_s']<.2-1e-9
            or not finite(value.get('source_age_s')) or not 0<=value['source_age_s']<.2-1e-9):
        raise ValueError('TASK_BATTERY_STALE')
    voltage=value.get('voltage_v')
    if not finite(voltage) or not 0<voltage<30:raise ValueError('TASK_BATTERY_INVALID')
    # Existing sensor guard requires >11.1V. Restart hysteresis is stricter;
    # 20% voltage estimate is not measured capacity and never bypasses it.
    estimate=max(0.,min(100.,(voltage-10.5)/1.8*100))
    if estimate<=20 or voltage<=11.2:raise ValueError('TASK_BATTERY_BELOW_REARM_MARGIN')
    if value.get('motor_disabled') is not True:raise ValueError('TASK_LEG_REQUIRES_MOTOR_OFF')
    return {'voltage_v':voltage,'estimated_percent':round(estimate,1),'capacity_measured':False,
            'sample_s':value['sample_s'],'source_age_s':value['source_age_s'],
            'load_measurement':'UNSUPPORTED','policy':'task-voltage-rearm-1.0'}


def check_leg(contract, preview, evidence, context, now, destination):
    binding=preview['binding'];original=contract['binding']
    if ({k:v for k,v in context.items() if k!='session_id'}!=
            {k:v for k,v in original['context'].items() if k!='session_id'}):
        raise ValueError('TASK_SOURCE_CHANGED')
    # map_revision hashes the CURRENT deskewed visibility grid, not its frame.
    # It naturally changes after driving. Immutable survey identity, room/
    # alignment/transform stay fixed; each new grid/route is checked below by
    # the existing preview/SIM/first-output and local collision guard path.
    for key in ('room_revision','alignment_revision','room_from_map'):
        if binding.get(key)!=original.get(key):raise ValueError('TASK_FRAME_OR_REVISION_CHANGED')
    if preview['scene_revision']!=contract['scene_revision']:raise ValueError('TASK_SCENE_CHANGED')
    target=contract[destination];origin=contract['b' if destination=='a' else 'a']
    if preview['goal']!=target:raise ValueError('TASK_ENDPOINT_CHANGED')
    # Candidate arrival envelope, not a claim of measured localization accuracy.
    if math.dist(preview['start'],origin)>.10:raise ValueError('TASK_START_OUTSIDE_ARRIVAL_ENVELOPE')
    route=[preview['start'],*preview['route']]
    headings=[math.atan2(b[1]-a[1],b[0]-a[0]) for a,b in zip(route,route[1:]) if math.dist(a,b)>1e-9]
    turns=sum(abs(math.atan2(math.sin(b-a),math.cos(b-a))) for a,b in zip([preview['yaw_rad'],*headings],headings))
    estimate=sum(math.dist(a,b) for a,b in zip(route,route[1:]))/.03+turns/.20+2.
    if estimate>45.:raise ValueError('TASK_ROUTE_EXCEEDS_BOUNDED_BUDGET')
    return resource_check(evidence,now)


class GoalTaskLoop:
    def __init__(self,navigation):
        self.navigation=navigation;self.lock=RLock();self.worker=None
        self.cancelled=Event();self.owner=None;self.contract=None;self.job=None
        self.token=None;self.force=False;self.closed=False
        self.leg_jobs=set()
        self.owner_seen_s=0.

    def touch(self,owner):
        # Internal snapshot calls must never manufacture browser presence.
        if owner==self.owner:self.owner_seen_s=time.monotonic()
        return {'owned':owner==self.owner,'active':owner==self.owner and self.active()}

    def can_continue(self):
        if self.cancelled.is_set():return False
        if time.monotonic()-self.owner_seen_s>2.5:raise ValueError('TASK_OWNER_CONNECTION_LOST')
        return True

    def active(self):
        return bool(self.worker and self.worker.is_alive())

    def offer(self,owner,job):
        if self.active() or not job or job.get('state')!='MISSION_ARRIVED':return None
        if job['job_id'] in self.leg_jobs:return None
        if job.get('worker_active') or job.get('report_status')!='SAVED' or any(job.get(k) for k in ('error','cleanup_error','report_error')):return None
        plan=job.get('approved_preview')
        if not plan or plan.get('physical_authority') is not False:return None
        body={'schema':'goal-task-loop-1.0','first_job_id':job['job_id'],
              'scene_revision':plan['scene_revision'],'binding':deepcopy(plan['binding']),
              'reference_key':job.get('map_id'),
              'a':list(plan['start']),'b':list(plan['goal']),
              'max_leg_s':45.,'physical_authority':False}
        body['task_digest']=canonical_sha256(body)
        with self.lock:
            # A consumed task cannot be resurrected by polling its first arrival.
            if self.job and self.job['task_digest']==body['task_digest']:return None
            self.owner=owner;self.contract=body
        return deepcopy(body)

    def start(self,owner,digest,expires_at_ms):
        with self.navigation.start_lock,self.lock:
            if self.closed or self.active():raise BrokerError('task_loop_busy','Task is unavailable or already running.',status=409)
            if self.job and self.job['task_digest']==digest:
                raise BrokerError('task_loop_consumed','Repeat approval was already consumed; no automatic retry.',status=409)
            if owner!=self.owner or not self.contract or digest!=self.contract['task_digest']:
                raise BrokerError('task_loop_stale','Repeat approval expired; finish a new goal first.',status=409)
            if type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-time.time()*1000<=2000:
                raise BrokerError('task_loop_expired','Use a fresh repeat choice.',status=409)
            current=self.navigation.snapshot(owner)['job']
            if not current or current['job_id']!=self.contract['first_job_id'] or current.get('worker_active'):
                raise BrokerError('task_loop_goal_changed','The completed first goal changed.',status=409)
            if current['state']!='MISSION_ARRIVED' or current.get('report_status')!='SAVED' or current.get('cleanup_error') or current.get('report_error'):
                raise BrokerError('task_loop_cleanup_required','Arrival, saved report and completed cleanup are required.',status=409)
            root=self.navigation.mission.automatic.root
            if root is None:raise BrokerError('task_loop_storage_unavailable','Task history storage is unavailable.',status=409)
            task_id=uuid4().hex;folder=root/'.twinpulse'/'task-loops';folder.mkdir(parents=True,exist_ok=True)
            if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
                raise ValueError('TASK_JOURNAL_PATH_UNSAFE')
            self.path=folder/(task_id+'.jsonl')
            self.stream=self.path.open('xb')
            self.cancelled=Event();self.token=object();self.force=False
            self.owner_seen_s=time.monotonic()
            self.job={'task_id':task_id,'task_digest':digest,'state':'PREPARING','leg':1,
                      'destination':'A','completed_legs':0,'a':self.contract['a'],'b':self.contract['b'],
                      'error':None,'error_stage':None,'cleanup_error':None,'resources':None,
                      'motion_authorized':False,'physical_demo_ready':False}
            try:self._record('task_approved',contract=self.contract)
            except Exception:
                self.stream.close();self.job.update(state='FAILED',error='TASK_JOURNAL_WRITE_FAILED');raise
            diagnostics=getattr(self.navigation.mission,'diagnostics',None)
            trace=diagnostics.begin('goal_task_loop',durable=False,task_id=task_id,
                draft_revision=self.contract['scene_revision'],evidence_kind='task_loop_history',evidence_id=task_id) if diagnostics else None
            self.worker=Thread(target=self._run,args=(owner,deepcopy(self.contract),self.token,trace),name='TwinPulseGoalTaskLoop',daemon=True)
            self.worker.start()
            return self.snapshot(owner)

    def snapshot(self,owner):
        with self.lock:
            return {**deepcopy(self.job),'worker_active':self.active()} if owner==self.owner and self.job else None

    def _record(self,kind,**data):
        row={'schema':'goal-task-history-1.0','task_id':self.job['task_id'],
             'pc_monotonic_s':time.monotonic(),'kind':kind,'data':data}
        payload=(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n').encode()
        if self.stream.tell()+len(payload)>16*1024*1024:raise ValueError('TASK_JOURNAL_BYTE_BUDGET')
        self.stream.write(payload)
        self.stream.flush();os.fsync(self.stream.fileno())

    def guard(self,contract,destination,preview,evidence,context,now):
        if self.cancelled.is_set():raise ValueError('TASK_STOP_REQUESTED')
        self.can_continue()
        resources=check_leg(contract,preview,evidence,context,now,destination)
        with self.lock:self.job['resources']={**resources,'historical':True}
        # Report observations as dated history, not a continuous battery display.

    def stop(self,owner,force=False):
        if owner!=self.owner:raise BrokerError('task_loop_not_owned','Task belongs to another connection.',status=409)
        self.cancelled.set()  # Preempt even while preparation holds start_lock.
        with self.lock:
            self.force=self.force or force
            if self.job and self.active():self.job['state']='STOPPING'
        mission=self.navigation.mission
        observed=mission.snapshot(owner).get('job')
        if observed and observed['state'] not in TERMINAL:mission.stop(owner,observed['job_id'],self.force)
        demo=self.navigation.demonstration
        if demo and demo.owner==owner:demo.stop(owner)
        return {'state':'STOPPING' if self.active() else 'STOPPED','stop_confirmed':False}

    def _run(self,owner,contract,token,trace=None):
        try:
            self._run_impl(owner,contract,token,trace)
        finally:
            if trace:
                with self.lock:job=deepcopy(self.job)
                if job.get('error'):
                    trace.child(job.get('error_stage') or 'task_loop_failure').finish('failed',error_code=job['error'])
                if job.get('cleanup_error'):
                    trace.child('task_loop_cleanup').finish('failed',error_code=job['cleanup_error'],role='cleanup')
                trace.finish('failed' if job.get('error') or job.get('cleanup_error') else
                    'cancelled' if job.get('state') in {'STOPPED','FORCE_STOPPED'} else 'unknown')

    def _run_impl(self,owner,contract,token,trace=None):
        stage='PREPARE_LEG'
        leg_trace=None
        try:
            while not self.cancelled.is_set():
                with self.lock:
                    index=self.job['leg'];destination='a' if index%2 else 'b'
                    self.job.update(state='PREPARING',destination=destination.upper(),resources=None)
                if index>10000:raise ValueError('TASK_JOURNAL_LEG_BUDGET')
                leg_trace=trace.child('goal_task_leg',leg_id=str(index)) if trace else None
                stage='PREPARE_LEG';target=contract[destination]
                review=self.navigation.prepare(owner,f'Go x={target[0]!r} y={target[1]!r}',_task_token=token,
                    _task_check=lambda p,e,c,n:self.guard(contract,destination,p,e,c,n))
                if not review.get('plan'):raise ValueError('TASK_ROUTE_UNAVAILABLE')
                stage='ISAAC_PREVIEW';deadline=time.monotonic()+180.
                while not self.cancelled.wait(.05):
                    self.can_continue()
                    demo=self.navigation.demonstration
                    if self.navigation.can_confirm():break
                    result=demo.snapshot(owner) if demo else None
                    if result and result['state'] in {'FAILED','CANCELLED'}:
                        raise ValueError(result.get('error') or 'TASK_ISAAC_PREVIEW_FAILED')
                    if time.monotonic()>deadline:raise ValueError('TASK_ISAAC_PREVIEW_TIMEOUT')
                if self.cancelled.is_set():break
                stage='CONFIRM_LEG';self._record('leg_admitted',leg=index,destination=destination,plan=review['plan'])
                started=self.navigation.confirm(owner,review['plan']['plan_id'],time.time()*1000+1500,_task_token=token,
                    _task_check=lambda p,e,c,n:self.guard(contract,destination,p,e,c,n))
                self.leg_jobs.add(started['job']['job_id'])
                if leg_trace:leg_trace.bind(mission_id=started['job']['job_id'])
                stage='RUN_LEG'
                with self.lock:self.job['state']='DRIVING'
                deadline=time.monotonic()+180.
                while True:
                    if not self.cancelled.is_set():self.can_continue()
                    current=self.navigation.snapshot(owner).get('job')
                    if self.cancelled.is_set():self.stop(owner,self.force)
                    if current and current['state'] in TERMINAL and not current.get('worker_active'):break
                    if time.monotonic()>deadline:raise ValueError('TASK_LEG_CLEANUP_TIMEOUT')
                    time.sleep(.05)
                self._record('leg_result',leg=index,job_id=current['job_id'],state=current['state'],
                    error=current.get('error'),cleanup_error=current.get('cleanup_error'),report_status=current.get('report_status'))
                if leg_trace:
                    leg_trace.finish('failed' if current.get('error') or current.get('cleanup_error') or current.get('report_error') else
                        'succeeded' if current['state']=='MISSION_ARRIVED' else 'cancelled' if self.cancelled.is_set() else 'unknown',
                        error_code=current.get('error'),mission_id=current['job_id'])
                if self.cancelled.is_set():break
                if current['state']!='MISSION_ARRIVED':raise ValueError(current.get('error') or 'TASK_LEG_NOT_ARRIVED')
                if current.get('cleanup_error') or current.get('report_error') or current.get('report_status')!='SAVED':
                    raise ValueError(current.get('cleanup_error') or current.get('report_error') or 'TASK_LEG_REPORT_NOT_SAVED')
                with self.lock:self.job.update(completed_legs=index,leg=index+1)
            with self.lock:self.job['state']='FORCE_STOPPED' if self.force else 'STOPPED'
        except Exception as exc:
            requested=(self.cancelled.is_set() and (str(exc)=='TASK_STOP_REQUESTED' or getattr(exc,'code',None)=='task_loop_stopped'))
            with self.lock:self.job.update(state='FAILED',error=str(exc)[:160],error_stage=stage)
            # Stop the owned worker, never another connection and never retry.
            try:self.stop(owner,False)
            except Exception as cleanup:
                with self.lock:self.job['cleanup_error']=str(cleanup)[:160]
            with self.lock:
                if requested:self.job.update(state='FORCE_STOPPED' if self.force else 'STOPPED',error=None,error_stage=None)
                else:self.job['state']='FAILED'
        finally:
            if leg_trace:leg_trace.finish('cancelled' if self.cancelled.is_set() else 'unknown')
            stage='TASK_CLEANUP'
            try:
                self.navigation.cancel(owner)
            except Exception as exc:
                with self.lock:self.job.update(state='FAILED',cleanup_error=str(exc)[:160])
            try:self._record('task_ended',result=self.snapshot(owner))
            except Exception:
                with self.lock:self.job.update(state='FAILED',cleanup_error='TASK_JOURNAL_WRITE_FAILED')
            finally:self.stream.close()

    def close(self):
        self.closed=True
        if self.active():
            self.stop(self.owner,True);self.worker.join(2.)
