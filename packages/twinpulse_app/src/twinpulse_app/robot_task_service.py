# SPDX-License-Identifier: Apache-2.0
"""Common model-proposed robot task orchestration over the trusted fleet.

The model only proposes data. Separate consent and Run bind the exact proposal,
project, robot, connection, scene and cancellation generation. No cold resume,
automatic connect/Prepare/Arm, inferred hardware permission or generated code.
"""
import asyncio
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from threading import Event, RLock, Thread
import time
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core.robot_task_plan import VERSION,CAPABILITIES,checked_plan,primitive_text
from twinpulse_core.robot_survey import next_observation,route_to,route_length,checked_motion_segment,ROUTE_TURN_TOLERANCE_RAD,MIN_CLEARANCE_M,PLANNING_CLEARANCE_M,task_clearance
from twinpulse_core.sim_fleet_navigation import next_leg
from twinpulse_provider import CancellationToken,GenerationRequest
from .command_broker import BrokerError
from .library_asset_store import atomic_json
from .product_inference import ProductInferenceScope


TERMINAL={'COMPLETED','PARTIAL','HELD','FAILED','CANCELLED','INTERRUPTED'}


class _OneCallLedger:
    product_usage=True
    def __init__(self,ledger):self.ledger=ledger;self.used=False;self.lock=RLock()
    @property
    def state(self):return self.ledger.state
    def reserve(self,body):
        with self.lock:
            if self.used:raise ValueError('ROBOT_TASK_ONE_CALL_ONLY')
            self.used=True
            return self.ledger.reserve(body)
    def settle(self,*args,**kwargs):return self.ledger.settle(*args,**kwargs)


class _Scope(ProductInferenceScope):
    def bind(self,*args,**kwargs):return _OneCallLedger(super().bind(*args,**kwargs))


class RobotTaskService:
    def __init__(self,workflow,fleet,registry,*,clock=time.monotonic):
        self.workflow,self.fleet,self.registry=workflow,fleet,registry
        self.root=fleet.root/'robot-tasks';self.clock=clock;self.lock=RLock()
        self.job=None;self.owner=None;self.worker=None;self.cancelled=Event();self.token=None
        self.permit=None;self.closed=False;self.presence=clock();self._model_token=None
        self.storage_error=None
        self.execution_admission=lambda:nullcontext()
        self.source_binding=self._scene_binding
        self.pending_stop=None
        self.pending_lock=RLock()
        self.stop_lock=RLock()
        self.motion_pin=None
        self.motion_guard_rejections=[]
        self.physical_local=None
        self.capture_environment=None
        self.spatial_review=None;self.task_registration=None
        fleet.task_service=self

    def owns_execution(self):return bool(self.pending_stop or self.job and self.job['state'] in {'RUNNING','STOPPING'})

    def active(self):return bool(self.owns_execution() or self.worker and self.worker.is_alive() or self.job is not None and not self.cancelled.is_set() and self.job['state'] in {'PLANNING','READY'})

    def revoke(self,reason):
        # Called under the fleet lock BEFORE external Stop/manual/focus/change.
        # Never acquire service/workflow locks here (fleet -> service inversion).
        self.cancelled.set();self.permit=None
        if self._model_token:self._model_token.cancel()

    def admit(self,token):
        if token is not self.permit or token is None or self.cancelled.is_set() or self.closed:
            raise BrokerError('robot_task_revoked','Task was stopped; no further step is allowed.',status=409)

    def admit_motion(self,body,row,scene,*,stage='fleet_admission'):
        # Called only under the fleet publication lock. No workflow/service
        # locks or storage here. A later pose/map cannot reuse an old projection.
        pin=self.motion_pin
        if row and row['kind']=='physical':
            if not pin or pin.get('request_id')!=body['request_id'] or pin.get('text')!=body['payload'].get('text') or not self._physical_motion_guard(pin,stage=stage)(row):
                raise BrokerError('robot_task_motion_context_changed','Physical task pose or observed map changed before admission.',status=409)
            return
        if (not pin or pin['request_id']!=body['request_id'] or pin['text']!=body['payload'].get('text')
                or not row or row.get('pose',{}).get('position_m')!=pin['pose']
                or not scene or scene['binding']!=pin['binding'] or scene['geometry']!=pin['geometry']
                or self._peer_context()!=pin.get('peers')
                or not 0<=self.clock()-scene['produced_at']<.5):
            raise BrokerError('robot_task_motion_context_changed','Current pose or map changed after the movement check; no child was published.',status=409)

    def _physical_motion_guard(self,pin,*,stage='live_queue_or_wire'):
        permit=self.permit;local=self.physical_local;binding=self.binding
        def rejected(code,value,**details):
            # Called under fleet/live locks. Only bounded memory publication:
            # no service/workflow lock or filesystem I/O can delay Stop here.
            now=self.clock()
            diagnostic=dict(stage=stage,code=code,request_id=pin.get('request_id'),
                observation_sha256=pin.get('observation_sha256'),checked_at_ms=time.time()*1000,
                source_age_ms=(now-pin['produced_at'])*1000 if isinstance(pin.get('produced_at'),(int,float)) else None,
                source_limit_ms=(value.get('timing_values') or {}).get('native_receipt_ms',350),**details)
            first=pin.setdefault('_first_guard_rejection',diagnostic)
            if first is diagnostic and len(self.motion_guard_rejections)<64:self.motion_guard_rejections.append(first)
            return False
        def guard(value):
            try:
                if permit is None or self.permit is not permit or self.cancelled.is_set() or self.closed:return rejected('AUTHORITY_REVOKED',value)
                if local is not self.physical_local or not local.latest or local.latest['packet']['sha256']!=pin['observation_sha256']:return rejected('PINNED_OBSERVATION_CHANGED',value)
                scene=self.fleet.navigation_scene
                if scene and tuple(scene['binding'])!=binding[3]:return rejected('SCENE_BINDING_CHANGED',value)
                if canonical_sha256((value.get('field') or {}).get('config'))!=local.context['config_sha256']:return rejected('FIELD_CONFIG_CHANGED',value)
                if self.task_registration is not None and (self.spatial_review is None or self.spatial_review.registration is not self.task_registration):return rejected('REGISTRATION_CHANGED',value)
                if pin.get('registered_model') is not None and (not scene or scene['geometry']!=pin['registered_model']):return rejected('REGISTERED_MODEL_CHANGED',value)
                # Live session roots use raw robot names; fleet roots use typed
                # device names. Never acquire fleet/workflow locks in this guard.
                row=dict(value,robot_id=binding[0],operation_id=binding[2],connection_epoch=binding[1],
                    device_boot_id=value.get('device_boot_id',value.get('boot_id')),
                    device_release_id=value.get('device_release_id',value.get('release_id')))
                if row.get('control_state')!='PAUSED':return rejected('WHEELS_NOT_PAUSED',value)
                pose=local.pose(row)
                position_delta=math.dist(pose[:2],pin['pose'][:2]);yaw_delta=abs(math.atan2(math.sin(pose[2]-pin['pose'][2]),math.cos(pose[2]-pin['pose'][2])))
                if position_delta>.005 or yaw_delta>.01:return rejected('POSE_CHANGED',value,position_delta_m=position_delta,yaw_delta_rad=yaw_delta)
                limit=(row.get('timing_values') or {}).get('native_receipt_ms',350)/1000
                if not 0<=self.clock()-pin['produced_at']<=limit:return rejected('PINNED_RING_EXPIRED',value)
                checked_motion_segment(pose,pin['step']['direction'],pin['step']['amount'],pin['geometry'],observed_cells=pin['fresh_cells'])
                return True
            except (ValueError,KeyError,TypeError) as exc:return rejected('VALIDATION_REJECTED',value,validation_reason=str(exc)[:200])
        return guard

    def _flush_motion_rejections(self):
        # Outside transport locks, retain the FIRST failed check, not a later
        # handler snapshot. A diagnostic write failure never masks its cause.
        for diagnostic in self.motion_guard_rejections:
            if diagnostic.get('_persisted'):continue
            value={k:v for k,v in diagnostic.items() if k!='_persisted'}
            try:self._event('motion_admission_rejected',**value);diagnostic['_persisted']=True
            except Exception:self.storage_error='ROBOT_TASK_STORAGE_FAILED'

    def _peer_context(self):
        # Caller holds fleet.lock. A moving/unfinished peer cannot be treated
        # as a stationary disc. Bind the stopped peers used by the check too.
        peers=[]
        for identity,r in sorted(self.fleet.robots.items()):
            if identity==self.job['robot_id'] or r['kind']!='sim' or not r.get('_connected'):continue
            if (r.get('_task') or r.get('_intent') or r['control_state']=='DRIVING'
                    or r['connection_state']!='CONNECTED' or r.get('applied_motion_epoch')!=r.get('motion_epoch') or not r.get('pose')):
                raise BrokerError('robot_task_peer_not_stopped','Stop every other connected SIM robot and wait for its applied epoch before this task.',status=409)
            peers.append(dict(robot_id=identity,connection_epoch=r['connection_epoch'],motion_epoch=r['motion_epoch'],
                applied_motion_epoch=r['applied_motion_epoch'],pose=deepcopy(r['pose']['position_m'])))
        return peers

    def snapshot(self,owner):
        with self.lock:
            if self.owner!=owner:return None
            self.presence=self.clock()
            if self.pending_stop:
                try:
                    row=self._row(raw=True);pin=self.pending_stop
                    if (row['connection_epoch']==pin['connection_epoch'] and row['operation_id']==pin['operation_id']
                            and row['motion_epoch']==pin['motion_epoch'] and row['applied_motion_epoch']==pin['motion_epoch']
                            and row['control_state']=='PAUSED' and row['connection_state']=='CONNECTED'
                            and (row['kind']=='sim' or self._physical_stop_confirmed(row,pin))):
                        if self._clear_pending_stop(pin):
                            self._event('late_stop_confirmed',**pin)
                            self.job['stop_reconciled']=True;self._save()
                except Exception:pass # UNKNOWN ownership remains, never a success fallback.
            if self.job and self.cancelled.is_set() and self.job['state']=='READY':
                self.job.update(state='CANCELLED',reason='AUTHORITY_REVOKED')
                try:self._save()
                except Exception:self.job.update(state='FAILED',reason=self.storage_error)
            value=deepcopy(self.job)
            if value:value['worker_active']=bool(self.worker and self.worker.is_alive());value['storage_error']=self.storage_error
            return value

    def _save(self):
        value=deepcopy(self.job);value['record_sha256']=canonical_sha256(value)
        try:atomic_json(self.root/self.job['task_id']/'task.json',value)
        except Exception:
            self.storage_error='ROBOT_TASK_STORAGE_FAILED';self.revoke(self.storage_error);raise

    def propose(self,text,owner,request_id):
        with self.lock:
            if self.closed or self.active():raise BrokerError('robot_task_busy','Finish or cancel the current robot task.',status=409)
            if self.registry is None:raise BrokerError('robot_task_planner_unavailable','Save a configured planner route first.',status=409)
            snap=self.fleet.snapshot();robot=next((r for r in snap['robots'] if r['robot_id']==snap['focused_robot_id']),None)
            if not robot:raise BrokerError('robot_task_robot_required','Select a robot before requesting a task plan.',status=409)
            # Request hash is a durable dispatch claim, never an owner credential.
            identity=hashlib.sha256(request_id.encode()).hexdigest()[:32]
            if (self.root/identity).exists():raise BrokerError('robot_task_request_used','This task request already has evidence; no automatic retry.',status=409)
            self.cancelled=Event();self.permit=None;self.owner=owner;self.storage_error=None;self.physical_local=None
            self.job=dict(schema_version=VERSION,task_id=identity,request_id=request_id,text=text,project_id=self.fleet.broker.project_id,
                robot_id=robot['robot_id'],robot_kind=robot['kind'],state='PLANNING',reason=None,model_id=None,
                plan=None,plan_sha256=None,events=[],step_index=0,distance_m=0.,segments=0,coverage=None,
                physical_authority=False,world_alignment_required=False,whole_room_coverage_verified=False)
            self.job['proposal_binding']=[robot['robot_id'],robot['kind'],robot['connection_epoch'],robot['operation_id'],list(self._scene_binding())]
            self.job['source_state_sha256']=canonical_sha256(self.source_binding())
            self._save();self._model_token=CancellationToken()
            self.worker=Thread(target=self._plan,args=(self.job,self._model_token),name='TwinPulseRobotTaskPlan',daemon=True);self.worker.start()
            return deepcopy(self.job)

    def _plan(self,job,token):
        provider=None;value=None;error=None;folder=self.root/job['task_id']
        try:
            from .stage_routing import build_configured_stage_service,StageRoutingSettings
            from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
            from twinpulse_provider.generation_store import input_digest
            from twinpulse_provider.robot_task_planner import generate_robot_task
            service=build_configured_stage_service(self.registry,evidence_root=folder/'provider-evidence')
            if service is None or not isinstance(service._provider,BudgetedPipeline):raise ValueError('ROBOT_TASK_CONFIGURED_PLANNER_REQUIRED')
            provider=service._provider;provider.stage_output_token_caps['planner']=min(2500,provider.stage_output_token_caps['planner'])
            route=StageRoutingSettings(self.registry).load()
            request=GenerationRequest(job['request_id'],json.dumps(dict(text=job['text'],robot_kind=job['robot_kind'],capabilities=list(CAPABILITIES)),ensure_ascii=False),schema_version=VERSION)
            request=replace(request,inference_scope=_Scope('robot-task:'+uuid4().hex,input_digest(request),canonical_sha256(route),provider.policy.sha256,folder/'usage.ledger.json',job['project_id']))
            atomic_json(folder/'request.json',dict(prompt=json.loads(request.prompt),model_id=provider.planner_model_id,max_calls=1,
                images_sent=0,mesh_sent=False,coordinates_sent=False,sensor_logs_sent=False,automatic_retry=False))
            with self.lock:
                if self.cancelled.is_set() or self.closed:raise ValueError('ROBOT_TASK_CANCELLED')
                job['model_id']=provider.planner_model_id
            value=asyncio.run(generate_robot_task(provider,request,token,service._config))
            atomic_json(folder/'proposal.json',value)
        except Exception as exc:error=str(exc)[:600]
        finally:
            if provider is not None:
                try:atomic_json(folder/'provider-diagnostic.json',provider.diagnostic_for(job['request_id']))
                except Exception:error=error or 'ROBOT_TASK_DIAGNOSTIC_STORAGE_FAILED'
            with self.lock:
                if self.job is not job:return
                job.update(state='CANCELLED' if self.cancelled.is_set() or self.closed else 'FAILED' if error else 'HELD' if value['mode']=='clarify' else 'READY',reason=error)
                if value and not error and not self.cancelled.is_set():job.update(plan=value,plan_sha256=canonical_sha256(value),reason=value['explanation'] if value['mode']=='clarify' else None)
                try:self._save()
                except Exception:job.update(state='FAILED',reason=self.storage_error)

    def _row(self,*,raw=False):
        snapshot_started=self.clock()
        snap=self.fleet.snapshot();row=next((r for r in snap['robots'] if r['robot_id']==self.job['robot_id']),None)
        if not row or not raw and snap['focused_robot_id']!=row['robot_id']:raise ValueError('ROBOT_TASK_SELECTION_CHANGED')
        if row['kind']=='physical':row=dict(row,_task_snapshot_started_at=snapshot_started)
        if not raw and row['kind']=='physical' and self.physical_local is not None:
            native=deepcopy(row.get('pose'));position=self.physical_local.pose(row)
            row=dict(row,native_pose=native,pose=dict(position_m=position,frame_id='task_session_local',source='wheel_odom_estimate',independent_body=False))
        return row

    def run(self,owner,digest):
        with self.execution_admission(),self.lock:
            if self.owner!=owner or not self.job or self.job['state']!='READY' or self.job['plan_sha256']!=digest or self.cancelled.is_set():
                raise BrokerError('robot_task_review_stale','Review a fresh exact robot task plan.',status=409)
            plan=checked_plan(self.job['plan'],request_text=self.job['text']);row=self._row()
            if self.capture_environment is not None:self.job['environment_source']=deepcopy(self.capture_environment())
            if canonical_sha256(self.source_binding())!=self.job['source_state_sha256']:
                raise BrokerError('robot_task_source_changed','Saved scene changed after planning; request a new plan.',status=409)
            if [row['robot_id'],row['kind'],row['connection_epoch'],row['operation_id'],list(self._scene_binding())]!=self.job['proposal_binding']:
                raise BrokerError('robot_task_context_changed','Robot connection or scene changed after the proposal; request a new plan.',status=409)
            if row['connection_state']!='CONNECTED' or row['control_state'] not in {'READY','PAUSED'}:
                raise BrokerError('robot_task_prepare_required','Connect and Prepare this robot first. No automatic connection or motor enable.',status=409)
            if row['kind']=='sim' and row['applied_motion_epoch']!=row['motion_epoch']:
                raise BrokerError('robot_task_stop_epoch_pending','Wait for the current stopped engine epoch before Run.',status=409)
            with self.fleet.lock:self._peer_context()
            if row['kind']=='physical':
                self.task_registration=None
                if any(s['op']=='navigate' for s in plan['steps']):
                    registration=self.spatial_review.registration_for(row) if self.spatial_review else None
                    if not registration:
                        self.job.update(state='HELD',reason='PHYSICAL_SEMANTIC_TARGET_REQUIRES_REVIEWED_WORLD_ALIGNMENT');self._save();return deepcopy(self.job)
                    self.task_registration=registration['_token']
                    self.job['spatial_review']=dict(job_id=registration['job_id'],review_digest=registration['review_digest'],
                        world_from_native=registration['world_from_native'],physical_authority=False,world_registration_verified=False)
                field=row.get('field') or {}
                if (not row.get('live_heartbeat') or not (row.get('capabilities') or {}).get('drive')
                        or field.get('armed') is not True or field.get('remaining_s',0)<plan['limits']['duration_s']
                        or not field.get('stop_receipt') or not row.get('task_local_state')):
                    raise BrokerError('robot_task_field_prepare_required','Prepare, enable LiDAR, confirm supervision/Arm and complete bootstrap Stop in this connection first.',status=409)
                if (field.get('config') or {}).get('footprint_radius_m',1)>MIN_CLEARANCE_M:
                    raise BrokerError('robot_task_footprint_larger_than_envelope','The reviewed body radius exceeds the selected task envelope; review geometry first.',status=409)
                from .physical_task_map import PhysicalTaskMap
                self.physical_local=PhysicalTaskMap(row['robot_id'],row['operation_id'],row['connection_epoch'],clock=self.clock)
                self.physical_local.pose(row) # Typed [x,y,yaw], never odom [x,y,z].
            else:self.physical_local=None;self.task_registration=None
            self.binding=(row['robot_id'],row['connection_epoch'],row['operation_id'],self._scene_binding())
            self.expected_epoch=row['motion_epoch'];self.start_pose=deepcopy((row.get('pose') or {}).get('position_m')) if row['kind']=='sim' else None
            if row['kind']=='sim' and not self.start_pose:raise BrokerError('robot_task_pose_required','A current engine pose is required.',status=409)
            self.permit=object();self.presence=self.clock();self.started=self.clock();self.visited=[];self.distance=0.;self.segments=0;self.motion_pin=None;self.geometry_records=set();self.motion_guard_rejections=[]
            from twinpulse_core.automatic_mapping import EvidenceGrid
            self.evidence_grid=EvidenceGrid();self.observations=0
            # Broker submit already serializes its guard and publication under
            # this lock. Do not take a fleet/workflow lock inside this section.
            # Either an earlier Build is pending, or it observes our owner.
            with self.fleet.broker._lock:
                if self.task_registration is not None and self.spatial_review.registration is not self.task_registration:
                    self.permit=None
                    raise BrokerError('robot_task_registration_changed','Session alignment changed before Run; review a fresh task.',status=409)
                if self.fleet.broker.has_pending_operations() or self._scene_binding()!=self.binding[3]:
                    self.permit=None
                    raise BrokerError('robot_task_engine_changed','Engine mutation started before task admission.',status=409)
                self.job.update(state='RUNNING',reason=None,connection_epoch=row['connection_epoch'],operation_id=row['operation_id'],
                    scene_binding=list(self.binding[3]),started_at_ms=time.time()*1000,progress_basis='ISAAC_KINEMATIC' if row['kind']=='sim' else 'WHEEL_ODOMETRY_NOT_INDEPENDENT_BODY')
                if row['kind']=='physical':self.job['execution_scope']='SUPERVISED_STATIONARY_NATIVE_RECEIPT_WHEEL_ESTIMATE'
            self._save();self.worker=Thread(target=self._execute,name='TwinPulseRobotTaskExecute',daemon=True);self.worker.start()
            return deepcopy(self.job)

    def _scene_binding(self):
        state=self.fleet.broker.supervisor_state()
        return state.get('engine_session_id'),state.get('stage_epoch'),(state.get('snapshot') or {}).get('applied_revision')

    def _check(self):
        self.admit(self.permit)
        if self.clock()-self.presence>3:raise ValueError('ROBOT_TASK_OWNER_NOT_PRESENT')
        if self.clock()-self.started>=self.job['plan']['limits']['duration_s']:raise ValueError('ROBOT_TASK_DURATION_LIMIT')
        row=self._row()
        if (row['robot_id'],row['connection_epoch'],row['operation_id'],self._scene_binding())!=self.binding:raise ValueError('ROBOT_TASK_CONTEXT_CHANGED')
        if row['connection_state']!='CONNECTED' or row['recording_state'] in {'FAILED','INCOMPLETE'}:raise ValueError('ROBOT_TASK_TELEMETRY_OR_RECORDING_LOST')
        return row

    def _event(self,kind,**values):
        with self.lock:
            if len(self.job['events'])>=1024:raise ValueError('ROBOT_TASK_EVENT_BUDGET')
            self.job['events'].append(dict(kind=kind,at_ms=time.time()*1000,**values));self._save()

    def _send(self,action,payload,*,motion_pin=None):
        row=self._check()
        if row['motion_epoch']!=self.expected_epoch:raise ValueError('ROBOT_TASK_UNEXPECTED_MOTION_EPOCH')
        request=uuid4().hex
        pin=dict(motion_pin,request_id=request) if motion_pin is not None else None
        if pin:self.motion_pin=pin
        try:
            result=self.fleet.action(dict(action=action,request_id=request,robot_id=row['robot_id'],connection_epoch=row['connection_epoch'],
                motion_epoch=row['motion_epoch'],payload=payload),self.owner,_task_token=self.permit)
        finally:
            if pin is not None and self.motion_pin is pin:self.motion_pin=None
        return request,row,result

    def _command(self,step):
        # This is the exact 9-decimal number serialized by primitive_text and
        # read by the ordinary parser. Never check the unrounded ideal endpoint.
        step=dict(step,amount=float(f"{step['amount']:.9f}"))
        if self.segments>=self.job['plan']['limits']['segments']:raise ValueError('ROBOT_TASK_SEGMENT_LIMIT')
        distance=step['amount'] if step['op']=='move_relative' and step['direction'] in {'forward','backward'} else 0.
        if self.distance+distance>self.job['plan']['limits']['distance_m']:raise ValueError('ROBOT_TASK_DISTANCE_LIMIT')
        text=primitive_text(step)
        if self.physical_local is not None:
            # Survey/route planning and durable provenance can consume a ring's
            # original lifetime. Acquire ONE genuinely new stationary ring
            # before request creation, then recheck this exact serialized leg.
            # Never refresh a pin after queue/wire admission or retry a command.
            self._observe_physical()
        row,scene,discs=self._geometry();pose=row['pose']['position_m']
        endpoint=checked_motion_segment(pose,step['direction'],step['amount'],scene['geometry'],observed_cells=scene.get('fresh_cells',scene.get('observed_cells')),discs=discs,clearance_m=task_clearance(row['kind']))
        pin=dict(pose=deepcopy(pose),binding=scene['binding'],geometry=scene['geometry'],text=text,peers=scene['_task_peers'])
        if row['kind']=='physical':pin.update(observation_sha256=scene['observation_sha256'],fresh_cells=scene['fresh_cells'],produced_at=scene['produced_at'],step=step,registered_model=scene.get('registered_model'))
        request,before,_=self._send('command',dict(text=text),motion_pin=pin)
        self.segments+=1;self.distance+=distance
        self.job.update(segments=self.segments,distance_m=self.distance)
        self._event('child_started',request_id=request,text=text,motion_epoch=before['motion_epoch'],checked_pose=pose,
            predicted_endpoint_m=endpoint,geometry_sha256=canonical_sha256(scene['geometry']),minimum_clearance_m=task_clearance(row['kind']),requested_minimum_clearance_m=MIN_CLEARANCE_M,
            navigation_sha256=scene.get('record_sha256'),observation_sha256=scene.get('observation_sha256'),
            fresh_grid_sha256=canonical_sha256(scene['fresh_cells']) if 'fresh_cells' in scene else None)
        acknowledgement_deadline=self.clock()+8
        while True:
            self.cancelled.wait(.1);row=self._check();command=row.get('command') or {}
            if command.get('request_id')!=request:
                if row['kind']=='physical' and self.clock()<acknowledgement_deadline:continue
                raise ValueError('ROBOT_TASK_CHILD_NOT_ACKNOWLEDGED' if row['kind']=='physical' else 'ROBOT_TASK_CHILD_REPLACED')
            state=command.get('state')
            if state in {'FAILED','CANCELLED','ESTIMATE_REACHED'}:raise ValueError('ROBOT_TASK_CHILD_'+state+': '+str(command.get('reason')))
            if state not in {'COMPLETED','ARRIVED'}:continue
            if row['kind']=='sim':
                if command.get('reason') not in {'TASK_COMPLETED','NAVIGATION_ARRIVED'}:raise ValueError('ROBOT_TASK_CHILD_RESULT_MISMATCH')
                if row['motion_epoch']==before['motion_epoch']:raise ValueError('ROBOT_TASK_NEW_STOP_EPOCH_REQUIRED')
                # The exact child completed; wait for its new zero-output epoch
                # to reach the engine. A user's Stop revokes the permit first.
                if row['applied_motion_epoch']!=row['motion_epoch']:continue
            elif command.get('stop_readback_confirmed') is not True:raise ValueError('ROBOT_TASK_STOP_READBACK_UNCONFIRMED')
            else:
                # Native completion and its PC pause fence are asynchronous.
                # Establish our own exact new Stop request/readback before
                # accepting the next generation's stationary observation.
                self._stop();row=self._row(raw=True)
            self.expected_epoch=row['motion_epoch']
            self._event('child_completed',request_id=request,command=command,new_motion_epoch=self.expected_epoch,
                applied_motion_epoch=row.get('applied_motion_epoch'),pose=deepcopy(row.get('pose')))
            return row

    def _observe(self):
        if self.physical_local is not None:return self._observe_physical()
        row=self._check();scan=row.get('scan') or {};old=(scan.get('stream_id'),scan.get('frame_sequence'),scan.get('captured_at_ms'))
        if row['lidar_state'] not in {'STARTING','STREAMING'}:self._send('lidar',dict(enabled=True))
        deadline=self.clock()+4
        while self.clock()<deadline:
            self.cancelled.wait(.1);row=self._check();scan=row.get('scan') or {}
            key=(scan.get('stream_id'),scan.get('frame_sequence'),scan.get('captured_at_ms'))
            age=time.time()*1000-scan.get('captured_at_ms',0) if row['kind']=='sim' else (row.get('scan_receipt') or {}).get('age_ms',1e9)
            if row['lidar_state']=='STREAMING' and key!=old and scan.get('points') and 0<=age<700:
                if row['motion_epoch']!=self.expected_epoch:raise ValueError('ROBOT_TASK_OBSERVE_EPOCH_CHANGED')
                if row['kind']=='sim':
                    sensor=scan.get('sensor_xy_yaw_world')
                    if (scan.get('source')!='isaac_usd_surface_rays' or scan.get('point_frame')!='sensor_local'
                            or not isinstance(sensor,list) or len(sensor)!=3):raise ValueError('ROBOT_TASK_SCAN_FRAME_REQUIRED')
                    co,si=math.cos(sensor[2]),math.sin(sensor[2]);rays=[]
                    for x,y in scan['points']:
                        if .02<=math.hypot(x,y)<=8:rays.append((list(sensor[:2]),[sensor[0]+co*x-si*y,sensor[1]+si*x+co*y]))
                    self.evidence_grid.insert(rays,round(scan['captured_at_ms']*1e6),canonical_sha256(dict(binding=list(self.binding[3]),operation=row['operation_id'],scan=key)))
                    self.observations+=1
                    atomic_json(self.root/self.job['task_id']/f'observation-{self.observations:04d}.json',dict(
                        robot_id=row['robot_id'],operation_id=row['operation_id'],connection_epoch=row['connection_epoch'],
                        binding=list(self.binding[3]),scan=scan,body_pose=row['pose'],scope='SIM_ACTUAL_RAYS_NOT_PHYSICAL_MEASUREMENT'))
                    rows=self.evidence_grid.rows()
                    measured=dict(observations=self.observations,free_cells=sum(r[2]=='free' for r in rows),occupied_cells=sum(r[2]=='occupied' for r in rows),
                        unknown_cells=sum(r[2]=='unknown' for r in rows),grid_sha256=canonical_sha256(rows),cell_size_m=.1,
                        source='ACTUAL_SIM_SURFACE_RAYS',model_prior_is_measurement=False,whole_room_verified=False)
                    atomic_json(self.root/self.job['task_id']/'observed-grid.json',dict(summary=measured,cells=rows))
                    self.job['measured_coverage']=measured
                self._event('observation',operation_id=row['operation_id'],scan_identity=list(key),scan_sha256=canonical_sha256(scan),
                    pose=deepcopy(row.get('pose')),source=scan.get('source'),alignment_required=False)
                return row
        raise ValueError('ROBOT_TASK_FRESH_OBSERVATION_REQUIRED')

    def _observe_physical(self):
        row=self._check()
        if row['lidar_state']!='STREAMING':raise ValueError('TASK_LOCAL_LIDAR_ON_REQUIRED')
        deadline=self.clock()+8
        waiting={'TASK_LOCAL_OBSERVATION_STALE','TASK_LOCAL_NEW_RING_PENDING','TASK_OBSERVATION_REQUIRED','TASK_LOCAL_POST_STOP_RING_PENDING'}
        while self.clock()<deadline:
            self.cancelled.wait(.1);row=self._check()
            if row['motion_epoch']!=self.expected_epoch:raise ValueError('ROBOT_TASK_UNEXPECTED_MOTION_EPOCH')
            if not row.get('task_local_observation'):continue
            try:value=self.physical_local.accept(row)
            except ValueError as exc:
                if str(exc) in waiting:continue
                raise
            self.observations+=1
            packet=value['packet'];summary=self.physical_local.summary()
            atomic_json(self.root/self.job['task_id']/f'observation-{self.observations:04d}.json',dict(
                robot_id=row['robot_id'],operation_id=row['operation_id'],connection_epoch=row['connection_epoch'],
                binding=list(self.binding[3]),packet=packet,body_pose=row['pose'],native_pose=row['native_pose'],
                scope=packet['scope'],independent_body=False,world_aligned=False))
            atomic_json(self.root/self.job['task_id']/'observed-grid.json',dict(summary=summary,cells=self.physical_local.grid.rows()))
            self.job['measured_coverage']=summary
            if self.start_pose is None:self.start_pose=list(value['pose'])
            self._event('observation',operation_id=row['operation_id'],scan_identity=value['scan_identity'],
                scan_sha256=packet['scan']['raw_sha256'],observation_sha256=packet['sha256'],pose=deepcopy(row['pose']),
                source=packet['scope'],alignment_required=False,independent_body=False)
            return row
        raise ValueError('TASK_LOCAL_STATIONARY_OBSERVATION_TIMEOUT')

    def _geometry(self, *, _after_record=False):
        row=self._check()
        if row['kind']=='physical':
            scene=self.physical_local.scene(row,self.clock);peers=[];discs=[]
            if self.task_registration is not None:
                registration=self.spatial_review.registration_for(dict(row,pose=row['native_pose']))
                if self.spatial_review.registration is not self.task_registration:raise ValueError('ROBOT_TASK_REGISTRATION_CHANGED')
                from twinpulse_core.room_localization import compose,inverse
                native_from_world=inverse(registration['world_from_native'])
                local_from_world=compose(inverse(self.physical_local.origin),native_from_world)
                with self.fleet.lock:
                    model=deepcopy(self.fleet.navigation_scene)
                if not model or tuple(model['binding'])!=self.binding[3]:raise ValueError('ROBOT_TASK_CURRENT_REGISTERED_MODEL_REQUIRED')
                targets=[]
                for t in model['geometry']['targets']:
                    x0,y0,x1,y1=t['bounds'];corners=[compose(local_from_world,[x,y,0.]) for x,y in ((x0,y0),(x0,y1),(x1,y0),(x1,y1))]
                    targets.append(dict(t,bounds=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]))
                # Only semantic target coordinates come from USD. Traversable
                # space remains the original observed local grid, NEVER model
                # floor cells masquerading as sensor measurements.
                scene['geometry']['targets']=targets
                scene['registration_sha256']=registration['review_digest']
                from twinpulse_core.registered_navigation import intersect_model_free
                world_from_local=compose(registration['world_from_native'],self.physical_local.origin)
                if model.get('observed_cells') is None:raise ValueError('ROBOT_TASK_REGISTERED_MODEL_GRID_REQUIRED')
                scene['observed_cells']=intersect_model_free(scene['observed_cells'],model['observed_cells'],world_from_local)
                scene['fresh_cells']=intersect_model_free(scene['fresh_cells'],model['observed_cells'],world_from_local)
                scene['registered_model']=model['geometry']
            age_limit=(row.get('timing_values') or {}).get('native_receipt_ms',350)/1000
        else:
            with self.fleet.lock:
                scene=deepcopy(self.fleet.navigation_scene)
                peers=self._peer_context()
                discs=[(*r['pose'][:2],.18) for r in peers]
            age_limit=.5
            if not scene or tuple(scene['binding'])!=self.binding[3] or not 0<=self.clock()-scene['produced_at']<age_limit:
                raise ValueError('ROBOT_TASK_CURRENT_GEOMETRY_REQUIRED')
        scene['_task_peers']=peers
        record=dict(binding=list(scene['binding']),geometry=scene['geometry'],observed_cells=scene.get('observed_cells'),peers=peers)
        if row['kind']=='physical':record.update(fresh_cells=scene['fresh_cells'],observation_sha256=scene['observation_sha256'],context=scene['context'],scope=scene['scope'])
        digest=canonical_sha256(record)
        scene['record_sha256']=digest
        if digest not in self.geometry_records:
            atomic_json(self.root/self.job['task_id']/('navigation-'+digest+'.json'),record)
            self.geometry_records.add(digest);self._event('geometry_recorded',sha256=digest)
            # Provenance I/O may outlive the original SIM snapshot. Read a
            # genuinely new owner/pose/map/peer snapshot once, never restamp or
            # discount I/O time from source age. A second changed digest is
            # persisted normally but cannot trigger another refresh. Physical
            # native observations retain their separate original-age contract.
            if row['kind']=='sim' and not _after_record:
                return self._geometry(_after_record=True)
        if not 0<=self.clock()-scene['produced_at']<age_limit:raise ValueError('ROBOT_TASK_CURRENT_GEOMETRY_REQUIRED')
        return row,scene,discs

    def _go(self,goal):
        replans=0
        while True:
            row,scene,discs=self._geometry();pose=row['pose']['position_m']
            if math.dist(pose[:2],goal)<.04:return
            route=route_to(pose,goal,scene['geometry'],observed_cells=scene.get('observed_cells'),discs=discs,clearance_m=task_clearance(row['kind'],planning=True))
            direction,amount,_=next_leg(pose,route,0)
            if direction is None:return
            if direction=='forward':
                target=next(p for p in route if math.dist(pose[:2],p)>.015)
                error=math.atan2(math.sin(math.atan2(target[1]-pose[1],target[0]-pose[0])-pose[2]),math.cos(math.atan2(target[1]-pose[1],target[0]-pose[0])-pose[2]))
                tolerance=.04 if row['kind']=='physical' else ROUTE_TURN_TOLERANCE_RAD
                if abs(error)>tolerance:direction,amount=('left' if error>0 else 'right'),abs(error)
            amount=min(amount,.40 if direction in {'forward','backward'} else math.pi)
            self._command(dict(op='move_relative',direction=direction,amount=amount))
            self._observe()
            # Replan from current observations after each bounded segment,
            # never issue an old fixed room circuit or continue after a fault.
            replans+=1
            if replans>96:raise ValueError('ROBOT_TASK_REPLAN_BUDGET')

    def _survey(self,return_required):
        while True:
            row=self._observe();pose=row['pose']['position_m'];self.visited.append(list(pose))
            _,scene,discs=self._geometry()
            result=next_observation(pose,self.start_pose,self.visited,scene['geometry'],self.job['plan']['limits']['distance_m']-self.distance,
                return_required=return_required,observed_cells=scene.get('observed_cells'),discs=discs,clearance_m=task_clearance(row['kind'],planning=True))
            self.job['coverage']={k:v for k,v in result.items() if k!='route'}
            self._event('survey_replanned',coverage=self.job['coverage'],visited_positions=len(self.visited))
            if result['route'] is None:return
            # Reserve return distance; _go independently revalidates every leg.
            from twinpulse_core.robot_survey import execution_cost
            costs=dict(linear_speed_m_s=.03,angular_speed_rad_s=.2,turn_tolerance_rad=.04) if row['kind']=='physical' else {}
            outbound=execution_cost(pose,result['route'],**costs)
            returning=route_to(outbound['end_pose'],self.start_pose[:2],scene['geometry'],observed_cells=scene.get('observed_cells'),discs=discs,clearance_m=task_clearance(row['kind'],planning=True)) if return_required else []
            back=execution_cost(outbound['end_pose'],returning,final_yaw=self.start_pose[2] if return_required else None,**costs)
            reserve_segments=outbound['segments']+back['segments']
            reserve_s=outbound['duration_s']+back['duration_s']+8 # observation/explicit Stop margin
            if (self.clock()-self.started+reserve_s>self.job['plan']['limits']['duration_s']
                    or self.segments+reserve_segments>self.job['plan']['limits']['segments']):
                self.job['coverage']['reason']='RETURN_TIME_AND_SEGMENTS_RESERVED';return
            self._go(result['goal'])

    def _stop(self):
        with self.stop_lock:return self._stop_serialized()

    def _set_pending_stop(self,pin):
        with self.pending_lock:self.pending_stop=pin

    def _clear_pending_stop(self,pin):
        with self.pending_lock:
            if self.pending_stop is not pin:return False
            self.pending_stop=None;return True

    def _stop_serialized(self):
        request=uuid4().hex
        self._set_pending_stop(dict(request_id=request,motion_epoch=None,connection_epoch=self.job.get('connection_epoch'),operation_id=self.job.get('operation_id')))
        result=self.fleet.action(dict(action='stop',request_id=request,robot_id=self.job['robot_id'],connection_epoch=None,motion_epoch=None,payload={}),self.owner,_task_token=self.permit)
        row=next(r for r in result['robots'] if r['robot_id']==self.job['robot_id'])
        epoch=row['motion_epoch'];deadline=self.clock()+4
        pin=dict(request_id=request,motion_epoch=epoch,connection_epoch=row['connection_epoch'],operation_id=row['operation_id']);self._set_pending_stop(pin)
        while self.clock()<deadline:
            row=self._row(raw=True)
            if row['kind']=='sim' and row['applied_motion_epoch']==epoch and row['control_state']=='PAUSED':
                self.expected_epoch=epoch;self._clear_pending_stop(pin);self._event('stop_confirmed',request_id=request,new_motion_epoch=epoch,applied_motion_epoch=row['applied_motion_epoch']);return
            if row['kind']=='physical':
                receipt=row.get('stop_receipt') or {}
                if self._physical_stop_confirmed(row,pin):
                    self.expected_epoch=row['motion_epoch'];self._clear_pending_stop(pin);self._event('stop_confirmed',request_id=request,receipt=receipt);return
            time.sleep(.1)
        raise ValueError('ROBOT_TASK_STOP_UNCONFIRMED')

    @staticmethod
    def _physical_stop_confirmed(row,pin):
        receipt=row.get('stop_receipt') or {}
        return (all(receipt.get(k)==pin.get(k) for k in ('request_id','operation_id','connection_epoch','motion_epoch'))
            and receipt.get('zero_off_readback_confirmed') is True and row.get('applied_motion_epoch')==pin.get('motion_epoch')
            and (receipt.get('readback') or {}).get('confirmed') is True
            and row.get('control_state')=='PAUSED')

    def _execute(self):
        outcome='COMPLETED';reason=None
        try:
            plan=self.job['plan'];return_required=any(s['op']=='return_to_start' for s in plan['steps'])
            if self.physical_local is not None:
                self._stop();self._observe()
            for index,step in enumerate(plan['steps']):
                self._check();self.job['step_index']=index;self._event('step_started',index=index,step=step)
                if step['op']=='observe':self._observe()
                elif step['op']=='survey':self._survey(return_required)
                elif step['op']=='return_to_start':
                    self._go(self.start_pose[:2]);row=self._check();pose=row['pose']['position_m']
                    error=math.atan2(math.sin(self.start_pose[2]-pose[2]),math.cos(self.start_pose[2]-pose[2]))
                    if abs(error)>.04:self._command(dict(op='move_relative',direction='left' if error>0 else 'right',amount=abs(error)))
                    row=self._observe();pose=row['pose']['position_m']
                    distance=math.dist(pose[:2],self.start_pose[:2]);yaw=abs(math.atan2(math.sin(pose[2]-self.start_pose[2]),math.cos(pose[2]-self.start_pose[2])))
                    self._event('return_verified',position_error_m=distance,yaw_error_rad=yaw,
                        position_basis='WHEEL_LOCAL_ESTIMATE_NOT_INDEPENDENT_BODY' if self.physical_local is not None else 'ISAAC_KINEMATIC_NOT_PHYSICAL')
                    if distance>.04 or yaw>.04:raise ValueError('ROBOT_TASK_RETURN_NOT_VERIFIED')
                elif step['op']=='stop':self._stop()
                elif step['op']=='navigate':
                    from twinpulse_core.sim_fleet_navigation import approach_plan
                    row,scene,discs=self._geometry();geometry=scene['geometry']
                    if sum(t['kind']==step['target_kind'] for t in geometry['targets'])!=1:
                        raise ValueError('ROBOT_TASK_TARGET_SELECTION_REQUIRED')
                    route=approach_plan(row['pose']['position_m'],step['target_kind'],geometry['targets'],geometry['bounds'],geometry['obstacles'],discs,observed_cells=scene.get('observed_cells'),clearance_m=task_clearance(row['kind'],planning=True))
                    self._go(route['goal_xy'])
                else:
                    self._command(step)
                    if self.physical_local is not None:self._observe()
            if any(s['op']=='survey' for s in plan['steps']):outcome='PARTIAL';reason='BOUNDED_KNOWN_GEOMETRY_COLLECTED_NOT_WHOLE_ROOM_VERIFIED'
        except Exception as exc:outcome='CANCELLED' if self.cancelled.is_set() else 'FAILED';reason=str(exc)[:600]
        finally:
            # Always request Stop, even after cancellation/diagnostic failure.
            # A failed Stop is retained separately and cannot become COMPLETED.
            stop_error=None
            try:self._stop()
            except Exception as exc:stop_error=str(exc)[:600]
            self._flush_motion_rejections()
            with self.lock:
                if stop_error:outcome='FAILED'
                if self.storage_error:outcome='FAILED'
                self.job.update(state=outcome,reason=reason,stop_error=stop_error,ended_at_ms=time.time()*1000)
                if self.storage_error:self.job['diagnostic_storage_error']=self.storage_error
                self.permit=None
                try:self._save()
                except Exception:
                    self.job.update(state='FAILED',terminal_save_error=self.storage_error)
                    if not self.job.get('reason'):self.job['reason']=self.storage_error

    def cancel(self,owner):
        if self.owner!=owner:raise BrokerError('robot_task_not_owned','This task belongs to another connection.',status=409)
        # Revoke before waiting, then pass through the SAME fleet publication
        # lock. Cancel cannot acknowledge ahead of an already admitted child.
        self.revoke('CANCELLED')
        with self.fleet.lock:self.revoke('CANCELLED')
        if self.job and self.job['state']=='RUNNING':
            try:self._stop()
            except Exception as exc:self.job['stop_error']=str(exc)[:600]
        with self.lock:
            if self.job and self.job['state']!='RUNNING':self.job.update(state='CANCELLED',reason='OPERATOR_CANCELLED');self._save()

    def close(self):
        self.closed=True;self.revoke('APP_CLOSED')
        with self.fleet.lock:self.revoke('APP_CLOSED')
        worker=self.worker
        if worker and worker is not __import__('threading').current_thread():worker.join(timeout=5)
        if worker and worker.is_alive():self.storage_error='ROBOT_TASK_WORKER_SHUTDOWN_UNCONFIRMED'
