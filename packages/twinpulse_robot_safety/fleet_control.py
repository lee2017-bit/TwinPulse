# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Explicit fleet control owner; importing this module never touches hardware.

The persistent heartbeat is not a motion lease. Only original, robot-challenged
inputs reach a separately owned ROS thread. Native protection is installed at
RosLink's actual publish boundary. Every pause requires a new operator intent.
"""
from copy import deepcopy
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from teleop_contract import InputGate, MANUAL_DIRECTIONS, MotionPaused
from control_timing import TIMING_POLICY
from physical_profile import checked_profile, profile_objects, profile_sha256
from field_tests import checked_config, digest, CASES, CAP_V, CAP_W, TTL, FieldGuard, NativeTracker, FieldEvidenceWriter, frame_points, control_observation
try:
    from twinpulse_core.manual_motion_guard import (NativeBeam, NativeFrame, MotionIntent,
        evaluate_manual_motion, ProgressObservation, WheelBodyProgressMonitor)
except ModuleNotFoundError:
    from manual_motion_guard import (NativeBeam, NativeFrame, MotionIntent,
        evaluate_manual_motion, ProgressObservation, WheelBodyProgressMonitor)


def reason_code(exc):
    import re
    code = str(exc)
    return code if re.fullmatch('[A-Z0-9_]{1,120}', code) else type(exc).__name__


class RosRecordDelivery:
    """Bounded original-message FIFO; no CDR/base64/journal in ROS callbacks."""
    def __init__(self,emit,serializer,topics):
        from uuid import uuid4
        self.emit,self.serializer,self.topics=emit,serializer,topics
        self.stream_id='ros-'+uuid4().hex
        self.queue=queue.Queue(maxsize=256);self.cancel=threading.Event();self.lock=threading.Lock()
        self.error=None;self.accepted=self.saved=self.offset=0;self.pending={};self.closed=False
        self.max_delivery_s=0.;self.thread=threading.Thread(target=self._run,daemon=True,name='FleetRosRecording')
        self.thread.start()

    def __call__(self,topic,message,metadata):
        self.check()
        if topic not in self.topics:raise ValueError('RAW_TOPIC_NOT_ALLOWLISTED')
        # rclpy callback objects are not modified after enqueue. The metadata
        # and order are frozen at callback entry, never at eventual delivery.
        with self.lock:
            if self.closed:raise ValueError('RAW_ROS_DELIVERY_CLOSED')
            index=self.accepted
            try:self.queue.put_nowait((index,topic,message,dict(metadata)))
            except queue.Full:
                self.error='RAW_ROS_DELIVERY_CAPACITY';raise ValueError(self.error)
            self.accepted+=1;self.pending[index]=time.monotonic()

    def check(self):
        if self.error:raise ValueError(self.error)

    def status(self):
        with self.lock:
            return dict(accepted=self.accepted,saved=self.saved,pending=len(self.pending),error=self.error,
                oldest_pending_s=max(0.,time.monotonic()-min(self.pending.values())) if self.pending else 0.,
                maximum_delivery_s=self.max_delivery_s,worker_reaped=not self.thread.is_alive())

    def _run(self):
        while not self.cancel.is_set() or not self.queue.empty():
            try:index,topic,message,metadata=self.queue.get(timeout=.02)
            except queue.Empty:continue
            try:
                raw=bytes(self.serializer(message))
                if len(raw)>65536:raise ValueError('RAW_ROS_MESSAGE_BOUND')
                self.emit('raw',dict(source='serialized_ros_message',topic=topic,message_type=self.topics[topic],
                    stream_id=self.stream_id,offset=self.offset,chunk_index=index,length=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),base64=base64.b64encode(raw).decode(),
                    receipt_start_s=metadata['receipt_monotonic_ns']/1e9,receipt_end_s=metadata['receipt_monotonic_ns']/1e9,
                    callback_timing={k:metadata[k] for k in ('receipt_ros_now_ns','source_stamp_ns','source_age_at_receipt_s') if k in metadata},
                    observation_sequence=metadata['sequence'],publish_attempt=topic=='guarded_cmd_vel'))
                with self.lock:
                    self.offset+=len(raw);self.saved+=1
                    self.max_delivery_s=max(self.max_delivery_s,time.monotonic()-self.pending.pop(index))
            except Exception as exc:
                self.error=reason_code(exc);return
            finally:self.queue.task_done()

    def close(self):
        with self.lock:self.closed=True
        self.cancel.set();self.thread.join(timeout=1.)
        status=self.status()
        if not status['worker_reaped'] or status['pending'] or status['saved']!=status['accepted']:
            self.error=self.error or 'RAW_ROS_DELIVERY_INCOMPLETE'
        return self.status()


class NativeOutputGuard:
    def __init__(self, profile, native, link, *, clock=time.monotonic):
        self.profile = checked_profile(profile)
        self.geometry, self.sampling, self.stop, thresholds = profile_objects(profile)
        self.native, self.link, self.clock = native, link, clock
        self.monitor = WheelBodyProgressMonitor(thresholds, require_independent_body=
            profile['progress']['body_progress_policy'] == 'independent_required')
        self.last_sample = None
        self.last_result = None
        self.progress = {'body_progress': 'UNVERIFIED', 'wheel_progress': 'UNKNOWN'}

    def reset(self):
        self.monitor.reset(); self.last_sample = None

    def __call__(self, v, w, source_created):
        if not (v or w):return
        now = self.clock()
        frame = self.native.latest_frame()
        if not frame or not frame['complete']:raise ValueError('NATIVE_COMPLETE_FRAME_REQUIRED')
        if frame.get('interval_fallback'):raise ValueError('NATIVE_INTERVAL_FALLBACK_UNQUALIFIED')
        timing = frame['timing']
        if timing['basis'] != 'conservative_measured_interval':raise ValueError('MEASURED_PIPELINE_BOUND_REQUIRED')
        rows = self.link.rows
        if len(rows) < 2:raise ValueError('MEASURED_WHEEL_VELOCITY_REQUIRED')
        a, b = rows[-2:]
        sample_s = b['t']-b['source_age_s']
        dt = sample_s-(a['t']-a['source_age_s'])
        if not 0 < dt <= .2 or not 0 <= now-sample_s < .2:raise ValueError('WHEEL_VELOCITY_SAMPLE_INVALID')
        progress = self.profile['progress']
        scale, separation = progress['wheel_metres_per_tick'], progress['wheel_separation_m']
        dl, dr = [(right-left)*scale/dt for left, right in zip(a['encoders'], b['encoders'])]
        native = NativeFrame(tuple(NativeBeam(**{k: beam[k] for k in
            ('angle_deg','distance_m','quality','node_index','source_byte_cursor')}) for beam in frame['beams']),
            self.geometry.sensor_frame, 'live_sensor', frame['raw_sha256'], frame['nodes_sha256'],
            timing['acquisition_earliest_s'], timing['acquisition_latest_s'], timing['basis'],
            timing['evidence_sha256'], timing['uncertainty_s'])
        result = evaluate_manual_motion(MotionIntent(v,w,source_created,(dl+dr)/2,(dr-dl)/separation,sample_s),
            native,self.geometry,self.sampling,self.stop,now)
        self.last_result = dict(result,raw_sha256=frame['raw_sha256'],nodes_sha256=frame['nodes_sha256'],
            timing=deepcopy(timing),profile_sha256=profile_sha256(self.profile))
        if not result['model_clear']:raise ValueError(result['reason'])
        # Encoders are NOT an independent chassis pose, including in /odom.
        if progress['body_progress_policy'] == 'independent_required':
            raise ValueError('INDEPENDENT_BODY_PROGRESS_SOURCE_NOT_IMPLEMENTED')
        if sample_s != self.last_sample:
            self.last_sample = sample_s
            observed = ProgressObservation(sample_s,'current_motion',tuple(n*scale for n in b['encoders']),
                scale,None,0.,0.,'wheel_encoder_only',None,None)
            self.progress = self.monitor.observe(observed,(v-w*separation/2,v+w*separation/2),
                progress_kind='translation' if v else 'rotation',now=now)
            if self.progress['requires_stop']:raise ValueError(self.progress['reason'])
        checked_at=self.clock()
        if (not 0<=checked_at-timing['acquisition_earliest_s']<self.stop.maximum_scan_age_s
                or not 0<=checked_at-sample_s<self.stop.maximum_scan_age_s):
            raise ValueError('NATIVE_GUARD_COMPUTE_EXPIRED_OBSERVATION')


class RobotControl:
    """One base/ROS owner. Long prepare/cleanup never blocks heartbeat or Stop admission."""
    def __init__(self, context, directory, emit, native, *, clock=time.monotonic):
        self.context, self.directory, self.emit, self.native = context, Path(directory), emit, native
        self.clock = clock; self.lock = threading.RLock(); self.queue = queue.Queue(maxsize=32)
        self.cancel = threading.Event(); self.stop_requested = threading.Event()
        self.profile = None; self.gate = InputGate(clock,continuous=True,persistent=True,recoverable=True)
        self.link = self.base = self.lease = self.lease_context = self.base_log = None
        self.release = None; self.guard = None; self.task = None; self.direction = None
        self.drive_command = None; self.last_publish = -math.inf; self.armed_until = 0.
        self.cleanup_confirmed = True
        self.field_config=None; self.field_until=0.; self.field_receipt=None; self.field_trials=[]
        self.field_trial=None; self.tracker=None; self.field_mode=False
        self.field_writer=None;self.field_evidence_fault=None;self.field_pending={};self.pause_sequence=0
        self.ros_delivery=None
        self.state = {'control_state':'UNPREPARED','reason':None,'challenge':None,'motion_generation':0,'timing_policy':TIMING_POLICY,
            'qualification':{'status':'UNKNOWN'},'battery':{'voltage_v':None,'source':'unknown','age_ms':None},
            'pose':None,'blockers':['PREPARE_REQUIRED'],'profile':None,'drive_ready':False,'applied_motion_epoch':None}
        self.thread = threading.Thread(target=self._run,daemon=True,name='TwinPulseFleetControl')

    def start(self):self.thread.start()

    def snapshot(self):
        with self.lock:value=deepcopy(self.state)
        diagnostic=value.get('telemetry_diagnostic')
        if diagnostic and diagnostic.get('checked_monotonic_s') is not None:
            elapsed=self.clock()-diagnostic['checked_monotonic_s']
            diagnostic['check_age_s']=elapsed
            if not 0<=elapsed<.2:
                diagnostic['last_check_reason']=diagnostic.get('reason')
                diagnostic['last_check_values']={k:diagnostic.get(k) for k in
                    ('source_age_s','sensor_receipt_age_s','guard_receipt_age_s')}
                diagnostic.update(reason='DIAGNOSTIC_CHECK_STALE',source_age_s=None,
                    sensor_receipt_age_s=None,guard_receipt_age_s=None)
        return value

    def submit(self, command):
        if self.thread.ident is not None and not self.thread.is_alive() and command['action'] not in {'stop','close'}:
            raise ValueError('CONTROL_WORKER_EXITED_RECONNECT_REQUIRED')
        if command['action'] in {'stop','close'}:
            self.stop_requested.set()
            if command['action']=='close':self.cancel.set()
            try:
                while True:self.queue.get_nowait()
            except queue.Empty:pass
        try:self.queue.put_nowait(command)
        except queue.Full:
            self.stop_requested.set()
            raise ValueError('CONTROL_INPUT_CAPACITY')

    def close(self):
        self.cancel.set(); self.stop_requested.set()
        self.thread.join(timeout=24)
        return dict(self.snapshot(),worker_reaped=not self.thread.is_alive(),cleanup_confirmed=self.cleanup_confirmed)

    def _update(self, **data):
        with self.lock:self.state.update(data)

    def _safety(self):
        if self.cancel.is_set() or self.stop_requested.is_set():raise ValueError('OPERATOR_STOP')
        if self.field_evidence_fault:raise ValueError(self.field_evidence_fault)
        if self.field_writer:self.field_writer.check()
        if getattr(self,'ros_delivery',None):self.ros_delivery.check()
        if self.release is not None:
            from runtime import HOME
            if (HOME/'current').resolve(strict=True)!=self.release:raise ValueError('RELEASE_CHANGED')

    def _qualification(self):
        from runtime import HOME
        from stop_policy import POLICY_SHA256
        expected = {'boot_id':self.context['boot_id'],'release_id':self.context['release_id'],
                    'schema':'manual-stop-2.0','policy_sha256':POLICY_SHA256}
        try:receipt = json.loads((HOME/'state/manual-qualification.json').read_text())
        except (OSError,ValueError):receipt={}
        valid = receipt.get('status')=='QUALIFIED' and all(receipt.get(k)==v for k,v in expected.items())
        result = dict(status='QUALIFIED' if valid else 'REQUIRED', scope='LEGACY_LOCAL_STOP_SAME_BOOT_RELEASE',
            native_integration='HARDWARE_NOT_RUN', expected=expected,
            prior_status=receipt.get('status','UNKNOWN'))
        self._update(qualification=result)
        return valid

    def _read_board(self, label):
        from runtime import read_board
        from robot_health import parse_board_snapshot
        path = self.directory/(label+'.log')
        offset=path.stat().st_size if path.exists() else 0
        read_board(self.release,path,self.lease.fileno())
        # The helper appends. Parse this observation only; earlier valid reads
        # must remain raw evidence, not become duplicate register ranges.
        with path.open('rb') as stream:
            stream.seek(offset);raw=stream.read(65537)
        if len(raw)>65536:raise ValueError('BOARD_READ_OUTPUT_BOUND')
        return parse_board_snapshot(raw.decode('utf-8'))

    def _prepare(self):
        if self.link is not None:return
        from runtime import HOME, ownership, verify_release, disarm_board
        from stationary import commands, require_idle
        from teleop_ros import RosLink
        self._update(control_state='PREPARING',blockers=['PREPARATION_IN_PROGRESS'])
        self.release = (HOME/'current').resolve(strict=True)
        manifest = verify_release(self.release)
        if manifest['source_id']!=self.context['release_id']:raise ValueError('RELEASE_CHANGED')
        deployed = json.loads((self.release/'profile.json').read_text())
        if deployed.get('manual_control_policy')!='explicit_session_and_same_boot_release_stop_receipt':
            raise ValueError('LEGACY_MANUAL_POLICY_NOT_REVIEWED')
        deadline=self.clock()+9.
        while self.lease is None:
            self._safety()
            self.lease_context=ownership()
            try:self.lease=self.lease_context.__enter__()
            except RuntimeError as exc:
                # A Connect idle READ may still hold our shared package lease.
                # Waiting opens no port; Stop remains independently admitted.
                if not str(exc).startswith('BUSY:') or self.clock()>=deadline:raise ValueError('OPENCR_ALREADY_OWNED') from exc
                self.cancel.wait(.05)
        self.cleanup_confirmed = False
        # Only explicit Prepare, never Connect/heartbeat, approves OFF maintenance.
        disarm_board(self.release,self.directory/'prepare-off.log',self.lease.fileno(),operator_confirmed=True)
        require_idle(self._read_board('prepare-before'))
        self._safety()
        base_command,_ = commands(self.release,self.directory)
        self.base_log = (self.directory/'base.log').open('ab')
        self.base = subprocess.Popen(base_command,stdout=self.base_log,stderr=self.base_log,
            start_new_session=True,pass_fds=(self.lease.fileno(),))
        self.link = RosLink(self.base)
        from rclpy.serialization import serialize_message
        from raw_ros_record import TOPICS
        self.ros_delivery=RosRecordDelivery(self.emit,serialize_message,TOPICS)
        self.link.record_sink=self.ros_delivery
        self.link.preflight_safety=self._safety
        self.link.persistent_manual = self.link.manual_speed_profile = True
        self.link.bind_observations({'project_id':self.context['project_id'],
            'session_id':self.context['operation_id'],'boot_id':self.context['boot_id'],
            'release_id':self.context['release_id'],'source_revision':self.context['worker_sha256'],'origin':'live_ros'})
        self.link.preflight(); self._safety(); self._qualification()
        self._install_guard()
        self._update(control_state='READY',reason=None)

    def _install_guard(self):
        if self.link is None:return
        if self.field_mode and self.field_config is not None:
            self.guard=FieldGuard(self.field_config,self.native,self.link,
                lambda:self.field_until>self.clock(),clock=self.clock)
            self.guard.tracker=self.tracker
            self.link.native_output_guard=self.guard
        elif self.profile is None:
            self.guard = None
            def reject(*_):raise ValueError('MEASURED_PROFILE_REQUIRED')
            self.link.native_output_guard=reject
        else:
            self.guard = NativeOutputGuard(self.profile,self.native,self.link,clock=self.clock)
            self.link.native_output_guard=self.guard

    def _cleanup(self):
        from stationary import stop_child, require_idle
        from runtime import disarm_board
        # Zero-authority maintenance may outlast the bounded command queue.
        # The session owner acknowledges presence separately, never as a motor
        # lease, while this thread performs actual zero/OFF/readback cleanup.
        self._update(control_state='PAUSED',reason='CONTROL_CLEANUP_IN_PROGRESS',maintenance_phase='CLEANUP',
                     drive_ready=False,blockers=['CONTROL_CLEANUP_IN_PROGRESS'])
        result={'subsystem':'control','ros_stop_confirmed':False,'base_reaped':self.base is None,
                'independent_idle_confirmed':False,'cleanup_confirmed':False}
        errors=[]
        if self.link is not None:
            try:self.link.halt(); result['ros_stop_confirmed']=True
            except Exception as exc:errors.append(reason_code(exc))
            try:self.link.close()
            except Exception as exc:errors.append(reason_code(exc))
            self.link=None
        if self.ros_delivery is not None:
            delivery=self.ros_delivery.close();self._update(ros_record_delivery=delivery)
            if delivery['error']:errors.append(delivery['error'])
            if delivery['worker_reaped']:self.ros_delivery=None
        if self.base is not None:
            try:result['base_exit']=stop_child(self.base);result['base_reaped']=True
            except Exception as exc:errors.append(reason_code(exc))
            if result['base_reaped']:self.base=None
        if self.lease is not None and result['base_reaped']:
            try:
                disarm_board(self.release,self.directory/'final-off.log',self.lease.fileno(),operator_confirmed=True)
                require_idle(self._read_board('final-read'));result['independent_idle_confirmed']=True
            except Exception as exc:errors.append(reason_code(exc))
            if self.base_log:self.base_log.close();self.base_log=None
            self.lease_context.__exit__(None,None,None);self.lease=None;self.lease_context=None
        result['errors']=errors
        result['cleanup_confirmed']=result['base_reaped'] and result['independent_idle_confirmed'] and not errors
        self.cleanup_confirmed = result['cleanup_confirmed']
        self._update(cleanup=result)
        self._update(control_state='UNPREPARED' if self.cleanup_confirmed else 'FAULT',drive_ready=False,
                     maintenance_phase=None)
        self.emit('cleanup',result)
        return result

    def _pause(self, reason, *, repeated_observation=False):
        prior=(self.state.get('control_state'),self.state.get('reason'),self.gate.generation)
        self.direction=None;self.task=None;self.drive_command=None
        self.gate.pause(reason,repeated_observation=repeated_observation)
        if self.guard:self.guard.reset()
        release_confirmed=False
        try:
            if self.link is not None and (self.link.enabled or self.link.sensor and self.link.sensor.torque):
                self.link.release();release_confirmed=True
        finally:
            # Evidence storage must never precede the immediate zero/OFF path.
            if self.field_trial and self.field_trial['status']=='RUNNING' and self.field_trial['case'] not in {'stationary','soak','bootstrap_stop'}:
                status='INCONCLUSIVE' if reason=='TASK_WHEEL_ODOM_TARGET_REACHED' or reason.startswith('FIELD_') else 'CANCELLED'
                if self.field_trial['case']=='presence_gap' and reason=='INPUT_DEADLINE_EXPIRED' and release_confirmed and self.field_trial.get('publications',0)>0:
                    status='PASS'
                self._finish_field(status,
                    reason,stop_readback_confirmed=release_confirmed,publications=self.field_trial.get('publications',0),
                    progress=self.guard.progress if self.guard else None)
        self._update(control_state='PAUSED' if self.link else 'UNPREPARED',reason=reason,
                     motion_generation=self.gate.generation,task=None)
        if prior!=(self.state['control_state'],reason,self.gate.generation):
            self.pause_sequence+=1
            self.emit('control_pause',dict(pause_id=f"{self.context.get('connection_epoch','local')}:{self.pause_sequence}",
                reason=reason,observed_monotonic_s=self.clock(),motion_generation=self.gate.generation,
                zero_off_readback_confirmed=release_confirmed))

    def _accept(self, command, action):
        p=command['payload']
        if p.get('motion_generation') != self.gate.generation:raise ValueError('MOTION_GENERATION_CHANGED')
        return self.gate.accept({'sequence':command['sequence'],'action':action,
            'challenge':p.get('challenge'),'age_ms':p.get('source_age_ms')})

    def _movement_ready(self):
        if self.link is None:raise ValueError('PREPARE_REQUIRED')
        if self.field_mode:
            blockers=self._field_blockers()
            if blockers:raise ValueError(blockers[0])
            return
        if self.profile is None:raise ValueError('MEASURED_PROFILE_REQUIRED')
        if self.profile['progress']['body_progress_policy']=='independent_required':
            raise ValueError('INDEPENDENT_BODY_PROGRESS_SOURCE_NOT_IMPLEMENTED')
        if not self._qualification():raise ValueError('PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE')
        if self.native.snapshot()['lidar_state']!='STREAMING':raise ValueError('NATIVE_LIDAR_ON_REQUIRED')

    def _velocity(self, direction):
        """Measured caps can only lower the existing manual policy command."""
        if self.field_mode:
            return {'forward':(CAP_V,0.),'backward':(-CAP_V,0.),'left':(0.,CAP_W),'right':(0.,-CAP_W)}[direction]
        if self.profile is None:raise ValueError('MEASURED_PROFILE_REQUIRED')
        v,w=MANUAL_DIRECTIONS[direction];model=self.profile['stop_model']
        return (math.copysign(min(abs(v),model['maximum_linear_speed_m_s']),v),
                math.copysign(min(abs(w),model['maximum_angular_speed_rad_s']),w))

    def _pose(self):
        snapshot=self.link.navigation_snapshot() if self.link else None
        odom=snapshot.get('odom') if snapshot else None
        if not odom:return None
        q=odom['quaternion_xyzw'];x,y,z,w=q
        yaw=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
        return dict(x=odom['position_m'][0],y=odom['position_m'][1],yaw=yaw,
            position_m=list(odom['position_m']),yaw_rad=yaw,aligned=False,
            frame_id=odom['frame_id'],sample_s=odom['sample_s'],source='wheel_odom',independent_body=False)

    def _command(self, command):
        action,p=command['action'],command['payload']
        if action.startswith('field_'):
            return self._field_command(command)
        if action=='profile':
            if self.link is not None and self.link.enabled:raise ValueError('PROFILE_CHANGE_REQUIRES_STOP')
            profile=checked_profile(p['profile'],robot_id=self.context['robot_id'],binding_sha256=self.context['binding_sha256'])
            self.field_mode=False;self.field_until=0.
            self.profile=profile;self.native.timing_profile=deepcopy(profile['timing']);self._install_guard()
            self.gate.pause('PROFILE_CHANGED')
            self._update(profile={'status':'VALIDATED_OPERATOR_MEASUREMENTS','sha256':profile_sha256(profile),
                'body_progress_policy':profile['progress']['body_progress_policy']})
        elif action=='prepare':
            if p.get('confirmed') is not True:raise ValueError('EXPLICIT_PREPARE_CONFIRMATION_REQUIRED')
            self._prepare()
        elif action=='watch':
            old=(self.gate.active,self.gate.deadline,self.gate.hold_end,self.gate.source_created,self.gate.last_action)
            self._accept(command,'watch')
            if self.task is None:
                (self.gate.active,self.gate.deadline,self.gate.hold_end,self.gate.source_created,self.gate.last_action)=old
            elif self.task['status']=='WAITING_POST_ARM_WATCH':
                pose=self._pose()
                if pose is None:raise ValueError('FRESH_ODOM_TASK_PROGRESS_REQUIRED')
                self.task['origin']=pose;self.task['previous_pose']=pose
                self.task['status']='RUNNING';self.direction=self.task['direction']
                self._update(control_state='ACTIVE',reason=None)
            if self.task:self.gate.hold_end=self.task['deadline']
        elif action in {'stop','close'}:
            if action=='close':self.field_until=0.
            self._pause('OPERATOR_STOP');self.stop_requested.clear()
            if self.field_trial and self.field_trial['status']=='RUNNING':self._finish_field('CANCELLED','OPERATOR_STOP')
            self._update(applied_motion_epoch=command['motion_epoch'])
        elif action in {'drive','task'}:
            if self.field_trial and self.field_trial['status']=='RUNNING' and self.field_trial['case'] in {'stationary','soak'}:
                raise ValueError('FIELD_ZERO_MOTION_COLLECTION_ACTIVE')
            self._movement_ready()
            direction=p.get('direction')
            if direction not in MANUAL_DIRECTIONS:raise ValueError('DIRECTION_INVALID')
            self._accept(command,direction)
            if action=='drive':
                if self.guard and hasattr(self.guard,'require_body'):self.guard.require_body=False
                # A fresh manual gesture supersedes an earlier finite task.
                # Otherwise presence watches would renew this manual input
                # through the leftover task branch after its 250ms lifetime.
                self.task=None
                self._update(task=None)
            task=None
            if action=='task':
                amount=p.get('amount')
                if type(amount) not in (int,float) or not math.isfinite(amount) or not 0<amount<=(2. if direction in {'forward','backward'} else math.tau):
                    raise ValueError('TASK_AMOUNT_OUTSIDE_BOUND')
                pose=self._pose()
                if pose is None:raise ValueError('FRESH_ODOM_TASK_PROGRESS_REQUIRED')
                velocity=self._velocity(direction)
                speed=abs(velocity[0] or velocity[1])
                task=dict(direction=direction,amount=amount,origin=pose,deadline=self.clock()+min(120.,amount/speed+2.),
                    progress_basis='wheel_odom_not_independent_body',status='RUNNING',rotation=0.,previous_pose=pose)
            self.drive_command=deepcopy(command)
            if not self.link.enabled:
                self.guard(*self._velocity(direction),self.gate.source_created)
                self.gate.suspend_for_arm();self.link.enable();self._safety()
                # The pre-arm clearance probe is not an observed drive window.
                # Start wheel progress only with fresh post-arm publication.
                self.guard.reset()
                self.armed_until=self.clock()+.25
                if task:self.task=dict(task,status='WAITING_POST_ARM_WATCH')
                self._update(control_state='ARMED_AWAITING_FRESH_INPUT',reason='NEW_POST_ARM_INPUT_REQUIRED')
                return
            if self.direction is not None and self.direction!=direction:
                self._pause('DIRECTION_CHANGE_REQUIRES_VERIFIED_STOP');return
            self.direction=direction
            if action=='task':
                self.task=task
            self._update(control_state='ACTIVE',reason=None)
        elif action=='qualify':self._qualify(command)
        else:raise ValueError('CONTROL_ACTION_INVALID')

    def _qualify(self, command):
        if command['payload'].get('confirmed') is not True:raise ValueError('EXPLICIT_QUALIFICATION_CONFIRMATION_REQUIRED')
        if self.link is None:raise ValueError('PREPARE_REQUIRED')
        if self._qualification():return
        if self.profile is None:raise ValueError('MEASURED_PROFILE_REQUIRED')
        # The existing same-boot receipt certifies a fixed .05m/s trial. A
        # lower-speed trial must not silently mint that broader qualification.
        # Reject before the physical single-trial marker is consumed.
        if self.profile['stop_model']['maximum_linear_speed_m_s']<.05:
            raise ValueError('LEGACY_QUALIFICATION_REQUIRES_0_05_PROFILE_CAP')
        from teleop_worker import qualify
        from runtime import HOME,write_json
        self._accept(command,'qualify')
        # Check native readiness before consuming the single physical trial.
        self.guard(.05,0.,self.gate.source_created)
        marker=HOME/'state'/('manual-trial-'+self.context['boot_id']+'-'+self.context['release_id'])
        if marker.exists():raise ValueError('TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED')
        marker.touch(exist_ok=False)
        self._update(control_state='QUALIFYING')
        owner=self
        class Incoming:
            pending=None
            def receive(self):
                owner._safety()
                if self.pending is not None and owner.gate.sequence==self.pending['sequence']:
                    owner.emit('command',{'request_id':self.pending['request_id'],'action':'watch','status':'COMPLETED'})
                    self.pending=None
                try:c=owner.queue.get_nowait()
                except queue.Empty:return None
                if c['action']!='watch':raise ValueError('TRIAL_INTERRUPTED')
                if c['payload'].get('motion_generation')!=owner.gate.generation:raise ValueError('MOTION_GENERATION_CHANGED')
                self.pending=c
                return {'sequence':c['sequence'],'action':'watch','challenge':c['payload'].get('challenge'),
                        'age_ms':c['payload'].get('source_age_ms')}
        def output(value):self._update(challenge=value['challenge'],watch_challenge=value['challenge'],motion_generation=self.gate.generation)
        self.guard.reset()
        result=qualify(self.link,Incoming(),output,self.gate,self.clock,safety=self._safety)
        cleanup=self._cleanup()
        if result['status']=='STOP_POLICY_PASS' and cleanup['cleanup_confirmed']:
            expected=self.snapshot()['qualification']['expected']
            write_json(HOME/'state/manual-qualification.json',dict(expected,status='QUALIFIED',report_directory=str(self.directory)))
            write_json(self.directory/'qualification.json',dict(result,cleanup=cleanup,worker_sha256=self.context['worker_sha256']))
            self.gate.pause('QUALIFICATION_COMPLETE');self._prepare()
        else:
            write_json(self.directory/'qualification.json',dict(result,cleanup=cleanup))
            raise ValueError('PHYSICAL_QUALIFICATION_FAILED')

    def _tick(self):
        if self.link is None:return
        began=self.clock();self.link.spin(.005)
        # Record observations independently of drive admission. A stale source
        # must still display its real voltage/age; fresh() below still blocks it.
        sensor=self.link.sensor
        pose=self._pose()
        if sensor is not None:
            voltage=float(sensor.battery)
            self._update(battery={'voltage_v':voltage if math.isfinite(voltage) else None,
                'source':'measured' if math.isfinite(voltage) else 'unknown','origin':'live_sensor_state',
                'read_status':{'state':'OBSERVED','origin':'ROS_SENSOR_STATE'},
                'age_ms':(self.clock()-self.link.sensor_t)*1000,'sample_monotonic_s':self.link.sensor_t},pose=pose,
                ros_spin_s=max(0.,self.clock()-began),ros_source_age_s=(getattr(self.link,'rows',[])[-1].get('source_age_s') if getattr(self.link,'rows',[]) else None))
        try:self.link.fresh()
        finally:
            diagnostic=deepcopy(getattr(self.link,'fresh_diagnostic',None))
            if diagnostic is not None:diagnostic['checked_monotonic_s']=self.clock()
            self._update(telemetry_diagnostic=diagnostic)
        self._safety();self.gate.check()
        if self.direction is None:
            if self.link.enabled and self.clock()>=self.armed_until:raise MotionPaused('POST_ARM_INPUT_EXPIRED')
            return
        if self.task:
            if pose is None:raise MotionPaused('TASK_ODOM_STALE')
            if pose['frame_id']!=self.task['origin']['frame_id']:raise MotionPaused('TASK_ODOM_FRAME_CHANGED')
            if self.clock()>=self.task['deadline']:raise MotionPaused('TASK_DEADLINE')
            origin=self.task['origin'];direction=self.task['direction']
            previous=self.task['previous_pose']
            if pose['sample_s']!=previous['sample_s']:
                dt=pose['sample_s']-previous['sample_s']
                delta=math.remainder(pose['yaw']-previous['yaw'],math.tau)
                model=self.profile['stop_model'] if not self.field_mode else dict(
                    angular_velocity_uncertainty_rad_s=.15,linear_velocity_uncertainty_m_s=.03,position_uncertainty_m=.01)
                if (not 0<dt<=.2 or abs(delta)>(.3+model['angular_velocity_uncertainty_rad_s'])*dt
                        or math.hypot(pose['x']-previous['x'],pose['y']-previous['y'])>
                            (.05+model['linear_velocity_uncertainty_m_s'])*dt+2*model['position_uncertainty_m']):
                    raise MotionPaused('TASK_ODOM_JUMP')
                self.task['rotation']+=delta;self.task['previous_pose']=pose
            if direction in {'forward','backward'}:
                progress=((pose['x']-origin['x'])*math.cos(origin['yaw'])+(pose['y']-origin['y'])*math.sin(origin['yaw']))*(1 if direction=='forward' else -1)
            else:
                progress=self.task['rotation']*(1 if direction=='left' else -1)
            if progress>=self.task['amount']:
                self._pause('TASK_WHEEL_ODOM_TARGET_REACHED');return
            self._update(task=dict(self.task,progress=progress))
        if self.gate.source_created is None:raise MotionPaused('FRESH_INPUT_REQUIRED')
        if self.clock()-self.last_publish<.05:return
        v,w=self._velocity(self.direction)
        decision=self.link.publish(v,w,self.clock()-self.gate.source_created,before_publish=self._safety)
        if self.field_trial and self.field_trial['status']=='RUNNING':
            self.field_trial['publications']=self.field_trial.get('publications',0)+1
        self.last_publish=self.clock()
        self._update(applied_motion_epoch=self.drive_command['motion_epoch'])
        self.emit('command',{'request_id':self.drive_command['request_id'],'action':self.drive_command['action'],
            'status':'PUBLISHED','direction':self.direction,'linear_m_s':v,
            'angular_rad_s':w,'source_created_s':self.gate.source_created,
            'applied_motion_epoch':self.drive_command['motion_epoch'],'guard':self.guard.last_result,
            'progress':self.guard.progress,'publisher_decision':decision})

    def _run(self):
        last_challenge=-math.inf
        try:
            while not self.cancel.is_set():
                if self.stop_requested.is_set():
                    try:
                        self._pause('OPERATOR_STOP')
                        if self.field_trial and self.field_trial['status']=='RUNNING':self._finish_field('CANCELLED','OPERATOR_STOP')
                    finally:self.stop_requested.clear()
                try:command=self.queue.get(timeout=.01)
                except queue.Empty:command=None
                if command:
                    try:
                        self._command(command)
                        self.emit('command',{'request_id':command['request_id'],'action':command['action'],
                            'status':'ADMITTED' if command['action'] in {'drive','task'} else 'COMPLETED'})
                    except Exception as exc:
                        code=reason_code(exc)
                        if command['action']!='watch':self._pause(code)
                        if (command['action']=='field_test' and self.field_trial and self.field_trial['status']=='RUNNING'
                                and self.field_trial['case']=='bootstrap_stop'):
                            self.field_receipt=None;self.field_until=0.
                            cleanup=self._cleanup() if self.link else {'cleanup_confirmed':True}
                            self._finish_field('INCONCLUSIVE',code,cleanup=cleanup)
                        self.emit('command',{'request_id':command['request_id'],'action':command['action'],'status':'REJECTED','reason':code})
                        if command['action']=='prepare':self._cleanup()
                self._cycle()
                if self.clock()-last_challenge>=.05:
                    last_challenge=self.clock()
                    blockers=[]
                    if self.link is None:blockers.append('PREPARE_REQUIRED')
                    if self.profile is None:blockers.append('MEASURED_PROFILE_REQUIRED')
                    elif self.profile['progress']['body_progress_policy']=='independent_required':blockers.append('INDEPENDENT_BODY_PROGRESS_SOURCE_NOT_IMPLEMENTED')
                    if self.snapshot()['qualification']['status']!='QUALIFIED':blockers.append('PHYSICAL_STOP_QUALIFICATION_REQUIRED')
                    if self.native.snapshot()['lidar_state']!='STREAMING':blockers.append('NATIVE_LIDAR_ON_REQUIRED')
                    frame=self.native.latest_frame()
                    if not frame or not frame['complete']:blockers.append('NATIVE_COMPLETE_FRAME_REQUIRED')
                    elif frame['timing']['acquisition_earliest_s'] is None:blockers.append('MEASURED_PIPELINE_BOUND_REQUIRED')
                    elif not 0<=self.clock()-frame['timing']['acquisition_earliest_s']<.2:blockers.append('NATIVE_FRAME_STALE')
                    if self.link and self.clock()-self.link.sensor_t>=.2:blockers.append('TELEMETRY_STALE')
                    if self.field_mode:blockers=self._field_blockers()
                    self._update(ros_record_delivery=self.ros_delivery.status() if self.ros_delivery else None,
                        challenge=self.gate.challenge(),watch_challenge=self.gate.challenge(),motion_generation=self.gate.generation,blockers=blockers,
                        drive_ready=not blockers,
                        guard=self.guard.last_result if self.guard else None,progress=self.guard.progress if self.guard else None,
                        field=self._field_snapshot())
        except Exception as exc:
            self._update(control_state='FAULT',reason=reason_code(exc))
            self.emit('fault',{'subsystem':'control','reason':reason_code(exc)})
        finally:
            self.field_until=0.
            try:
                if self.lease is not None:self._cleanup()
            finally:
                tracking_cleanup=self.tracker.close() if self.tracker else dict(worker_reaped=True,thread_reaped=True)
                if not all(tracking_cleanup.values()):self.cleanup_confirmed=False
                self._update(tracking_cleanup=tracking_cleanup)
                try:
                    if self.field_trial and self.field_trial['status']=='RUNNING':self._finish_field('CANCELLED','SESSION_CLOSED')
                except Exception:self._update(field_evidence_error='FIELD_FINAL_RECORD_INCOMPLETE')
                evidence=self.field_writer.close() if self.field_writer else dict(complete=True,writer_reaped=True)
                if not evidence['complete'] and self.field_pending:
                    evidence['writer_close_result']=deepcopy(evidence)
                    self.field_evidence_fault=self.field_evidence_fault or 'FIELD_EVIDENCE_CLOSE_UNCONFIRMED'
                    self._fail_pending_fields(self.field_evidence_fault)
                self._poll_field_writes(resume=False)
                if self.field_evidence_fault:
                    evidence.update(complete=False,error=self.field_evidence_fault)
                self.cleanup_confirmed=self.cleanup_confirmed and evidence['complete']
                self._update(control_state='CLOSED',field_evidence=evidence,field=self._field_snapshot(),challenge=None,watch_challenge=None,drive_ready=False,blockers=['CONTROL_WORKER_CLOSED'])

    def _cycle(self):
        # A latched archive failure must revoke motion, not starve ROS callbacks
        # forever. Keep observing original sensor/guard clocks while stopped.
        try:self._field_tick()
        except Exception as exc:
            code=reason_code(exc)
            if code.startswith('FIELD_EVIDENCE'):
                self.field_evidence_fault=self.field_evidence_fault or code
                self.field_until=0.
                self._update(field_evidence_error=self.field_evidence_fault)
                self._pause(code,repeated_observation=True)
                self._finish_field('INCONCLUSIVE',code)
                self._fail_pending_fields(code)
            else:self._pause(code,repeated_observation=True)
        try:self._tick()
        except Exception as exc:
            code=reason_code(exc)
            if self.field_evidence_fault:
                self._update(secondary_control_fault=code)
                self._pause(self.field_evidence_fault,repeated_observation=True)
            else:self._pause(code,repeated_observation=True)

    def _field_write(self,name,value):
        if self.field_writer is None:self.field_writer=FieldEvidenceWriter(self.directory,clock=self.clock)
        return self.field_writer.append(name,value)

    def _field_snapshot(self):
        frame=self.native.latest_frame()
        native_observation=None if not frame else dict(frame_sequence=frame['frame_sequence'],
            stream_id=frame.get('stream_id'),raw_sha256=frame['raw_sha256'],
            raw_ring_complete=bool(frame['complete']),
            unknown_bytes=(frame.get('quality') or {}).get('unframed_bytes',0),
            receipt_age_s=self.clock()-frame['timing']['receipt_end_s'],
            policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',directional_clearance='CHECKED_PER_OUTPUT_NOT_BY_THIS_STATUS')
        return dict(mode='SUPERVISED_FIELD_TEST',config=deepcopy(self.field_config),
            config_sha256=digest(self.field_config) if self.field_config else None,
            armed=self.field_until>self.clock(),remaining_s=max(0.,self.field_until-self.clock()),
            blockers=self._field_blockers(),stop_receipt=deepcopy(self.field_receipt),
            tracking=self.tracker.snapshot() if self.tracker else None,
            evidence_error=self.field_evidence_fault or (self.field_writer.error if self.field_writer else None),
            evidence_status=self.field_writer.status() if self.field_writer and hasattr(self.field_writer,'status') else None,
            native_observation=native_observation,
            active_trial=deepcopy(self.field_trial),trials=deepcopy(self.field_trials[-32:]))

    def _field_blockers(self, *, receipt=True):
        result=[]
        evidence_error=self.field_evidence_fault or (self.field_writer.error if self.field_writer else None)
        if evidence_error:result.append(evidence_error)
        if self.field_config is None:result.append('FIELD_CONFIG_REVIEW_REQUIRED')
        if self.link is None:result.append('PREPARE_REQUIRED')
        if self.field_until<=self.clock():result.append('FIELD_SUPERVISION_CONFIRMATION_REQUIRED')
        if receipt and self.field_receipt is None:result.append('FIELD_BOOTSTRAP_STOP_REQUIRED')
        try:control_observation(self.native,self.field_config or {},self.clock())
        except (ValueError,TypeError,KeyError) as exc:result.append(reason_code(exc))
        if self.link and not 0<=self.clock()-self.link.sensor_t<=.2:result.append('FIELD_WHEEL_TELEMETRY_STALE')
        return result

    def _finish_field(self,status,reason,*,stop_write=None,**result):
        if not self.field_trial or self.field_trial['status']!='RUNNING':return
        self.field_trial.update(status='PENDING_PERSISTENCE',reason=reason,ended_s=self.clock(),result=result,
            decision=dict(status=status,reason=reason),persistence=dict(state='AWAITING_WRITE_ACK'))
        self.field_trials.append(deepcopy(self.field_trial));self.field_trials=self.field_trials[-32:]
        try:
            token=self._field_write('field-trials.json',dict(schema='field-trials-1.0',context=self.context,trials=self.field_trials))
            if not token:raise ValueError('FIELD_EVIDENCE_ACK_MISSING')
            self.field_pending[self.field_trial['trial_id']]=dict(trial=self.field_trial,
                tokens=([stop_write] if stop_write else [])+[token],context=deepcopy(self.context))
        except Exception as exc:
            # Preserve the attempted decision, but never claim a durable PASS.
            # Stop/cleanup must not die by writing to an already failed writer.
            code=reason_code(exc)
            if not code.startswith('FIELD_EVIDENCE'):code='FIELD_EVIDENCE_WRITE_FAILED'
            self.field_evidence_fault=self.field_evidence_fault or code;self.field_until=0.;self.field_receipt=None
            self.field_trial.update(status='INCONCLUSIVE',reason=self.field_evidence_fault,
                result={**result,'evidence_error':self.field_evidence_fault,
                        'attempted_decision':dict(status=status,reason=reason)},persistence=dict(state='FAILED'))
            self.field_trials[-1]=deepcopy(self.field_trial)
            self._update(field_evidence_error=self.field_evidence_fault)
        self.emit('command',dict(action='field_test',status=self.field_trial['status'],trial=deepcopy(self.field_trial)))

    def _fail_pending_fields(self, code):
        self.field_until=0.;self.field_receipt=None
        pending_items=list(self.field_pending.values());self.field_pending.clear();notifications=[]
        for pending in pending_items:
            trial=pending['trial'];trial.update(status='INCONCLUSIVE',reason=code,
                persistence=dict(state='FAILED',writes=pending['tokens']))
            trial['result']=dict(trial.get('result',{}),evidence_error=code,attempted_decision=trial['decision'])
            self._replace_field_trial(trial)
            notifications.append(dict(action='field_test',status='INCONCLUSIVE',trial=deepcopy(trial)))
        for notification in notifications:
            try:self.emit('command',notification)
            except Exception as exc:
                self.cleanup_confirmed=False;self._update(evidence_notification_error=reason_code(exc))

    def _replace_field_trial(self, trial):
        for i,item in enumerate(self.field_trials):
            if item.get('trial_id')==trial['trial_id']:self.field_trials[i]=deepcopy(trial);break
        if self.field_trial and self.field_trial.get('trial_id')==trial['trial_id']:self.field_trial=trial

    def _poll_field_writes(self, *, resume=True):
        for key,pending in list(self.field_pending.items()):
            try:
                acknowledgements=[self.field_writer.receipt(token) for token in pending['tokens']]
                if not all(acknowledgements):continue
                if pending['context']!=self.context:raise ValueError('FIELD_EVIDENCE_CONTEXT_CHANGED')
            except Exception as exc:
                self.field_evidence_fault=self.field_evidence_fault or reason_code(exc)
                self._fail_pending_fields(self.field_evidence_fault);return
            trial=pending['trial'];trial.update(**trial['decision'],persistence=dict(state='COMMITTED',writes=acknowledgements))
            self._replace_field_trial(trial);del self.field_pending[key]
            # Persisted observations are historical facts; receipt authority and
            # continuation additionally require the same still-live generation.
            current=(resume and not self.cancel.is_set() and not self.stop_requested.is_set()
                and not self.field_evidence_fault and self.field_until>self.clock()
                and pending.get('resume_generation')==self.gate.generation)
            if trial['case']=='bootstrap_stop' and trial['status']=='PASS' and current:
                self.field_receipt=deepcopy(trial['result']['receipt'])
                self.field_receipt['persistence']=deepcopy(trial['persistence'])
                self._prepare()
            self.emit('command',dict(action='field_test',status=trial['status'],trial=deepcopy(trial)))

    def _field_command(self, command):
        action,p=command['action'],command['payload']
        extra={'challenge','motion_generation','source_age_ms'}
        user={k:v for k,v in p.items() if k not in extra}
        if action=='field_setup':
            if set(user)!={'config'}:raise ValueError('FIELD_CONFIG_SHAPE')
            config=checked_config(user['config'],robot_id=self.context['robot_id'],binding_sha256=self.context['binding_sha256'])
            self._pause('FIELD_CONFIG_CHANGED');self.field_until=0.;self.field_receipt=None
            self.field_config=config;self.field_mode=True
            self.native.timing_profile=None
            if self.tracker:
                tracking_cleanup=self.tracker.close()
                self._update(tracking_cleanup=tracking_cleanup)
                if not tracking_cleanup or not all(tracking_cleanup.values()):
                    raise ValueError('TRACKING_OLD_OWNER_NOT_REAPED')
            self.tracker=NativeTracker(self.native,config,clock=self.clock)
            self._install_guard();self._field_write('field-config.json',dict(context=self.context,config=config,sha256=digest(config),motion_authority=False))
        elif action=='field_arm':
            if user!={'confirmed':True}:raise ValueError('FIELD_SUPERVISION_CONFIRMATION_REQUIRED')
            if self.field_evidence_fault:raise ValueError(self.field_evidence_fault)
            if self.field_writer:self.field_writer.check()
            if not self.field_config:raise ValueError('FIELD_CONFIG_REVIEW_REQUIRED')
            if self.link is None:raise ValueError('PREPARE_REQUIRED')
            if self.direction is not None or self.task is not None or self.link.enabled:
                raise ValueError('FIELD_ARM_REQUIRES_STOPPED_IDLE')
            if self.field_trial and self.field_trial['status'] in {'RUNNING','PENDING_PERSISTENCE'}:raise ValueError('FIELD_TRIAL_ALREADY_RUNNING')
            self.link.fresh() # Current ROS/header ownership, not just a native ring.
            control_observation(self.native,self.field_config,self.clock())
            self._accept(command,'watch');self.gate.pause('FIELD_ARMED_NEW_INPUT_REQUIRED')
            self.field_mode=True;self.field_until=self.clock()+TTL;self._install_guard()
            self._update(reason='SUPERVISED_FIELD_TEST_NOT_PROTECTED_QUALIFICATION')
        elif action=='field_review':
            if set(user)-{'trial_id','observed','clearance_m'} or user.get('observed') not in {'stopped','not_stopped','moved','not_moved','inconclusive'}:
                raise ValueError('FIELD_REVIEW_SHAPE')
            trial=next((t for t in self.field_trials if t['trial_id']==user.get('trial_id')),None)
            if trial is None:raise ValueError('FIELD_TRIAL_NOT_FOUND')
            if trial['status']=='PENDING_PERSISTENCE':raise ValueError('FIELD_RESULT_PERSISTENCE_PENDING')
            gap=user.get('clearance_m')
            if gap is not None and (type(gap) not in (int,float) or not math.isfinite(gap) or not 0<=gap<=10):
                raise ValueError('FIELD_CLEARANCE_INPUT_INVALID')
            trial['operator_review']=dict(user,recorded_s=self.clock(),source='operator_observation_not_independent_certification')
            # The machine result is immutable. Operator evidence is a separate scope.
            trial['operator_verdict']='FAIL' if user['observed']=='not_stopped' else 'INCONCLUSIVE'
            evidence=trial.get('result',{})
            if (trial['case']=='proximity' and trial.get('reason')=='FIELD_PROXIMITY_10CM'
                    and evidence.get('publications',0)>0 and evidence.get('stop_readback_confirmed') is True
                    and user['observed']=='stopped' and gap is not None):
                trial['operator_verdict']='PASS' if gap>=.1 else 'FAIL'
            self._field_write('field-trials.json',dict(schema='field-trials-1.0',context=self.context,trials=self.field_trials))
        elif action=='field_test':
            if set(user)!={'case','confirmed'} or user['case'] not in CASES or user['confirmed'] is not True:
                raise ValueError('FIELD_TEST_CONFIRMATION_REQUIRED')
            if self.field_trial and self.field_trial['status'] in {'RUNNING','PENDING_PERSISTENCE'}:raise ValueError('FIELD_TRIAL_ALREADY_RUNNING')
            case=user['case']
            if case not in {'stationary','soak'}:
                missing=self._field_blockers(receipt=case!='bootstrap_stop')
                if missing:raise ValueError(missing[0])
                if not self.field_mode:raise ValueError('FIELD_MODE_REQUIRED')
            elif not self.field_config:raise ValueError('FIELD_CONFIG_REVIEW_REQUIRED')
            else:
                # Diagnostic zero-command acquisition may start on an invalid
                # ring. The interval still records invalids and cannot PASS or
                # grant movement by ignoring them. A live source is required.
                source=self.native.snapshot()
                if source.get('lidar_state')!='STREAMING':raise ValueError('NATIVE_LIDAR_ON_REQUIRED')
                if source.get('error'):raise ValueError('NATIVE_RECORDING_UNAVAILABLE')
            if self.direction is not None or self.task is not None or self.link and self.link.enabled:
                raise ValueError('FIELD_TRIAL_REQUIRES_STOPPED_IDLE')
            self.field_trial=dict(trial_id=__import__('uuid').uuid4().hex,case=case,status='RUNNING',
                started_s=self.clock(),config_sha256=digest(self.field_config),request_id=command['request_id'],
                context=deepcopy(self.context),request_twin_context=deepcopy(command.get('request_twin_context')),
                frames=0,last_frame=None)
            if case=='bootstrap_stop':return self._field_bootstrap(command)
            if case in {'stationary','soak'}:
                self._pause('FIELD_ZERO_MOTION_COLLECTION');return
            direction={'forward':'forward','backward':'backward','left':'left','right':'right','full_turn':'left',
                'proximity':'forward','stall':'forward','presence_gap':'forward'}[case]
            amount=math.tau if case=='full_turn' else math.pi/2 if case in {'left','right'} else .1
            task=deepcopy(command);task['action']='task';task['payload']=dict(p,direction=direction,amount=amount)
            if self.guard:self.guard.require_body=case=='stall'
            return self._command(task)
        else:raise ValueError('FIELD_ACTION_INVALID')

    def _field_bootstrap(self,command):
        from teleop_worker import qualify
        self.field_receipt=None
        self._accept(command,'qualify');self.guard.reset();self.guard.bootstrap=True
        self.guard(CAP_V,0.,self.gate.source_created)
        self.guard.reset()
        self._update(control_state='QUALIFYING');owner=self
        class Incoming:
            pending=None
            def receive(self):
                owner._safety()
                if self.pending is not None and owner.gate.sequence==self.pending['sequence']:
                    owner.emit('command',{'request_id':self.pending['request_id'],'action':'watch','status':'COMPLETED'})
                    self.pending=None
                try:c=owner.queue.get_nowait()
                except queue.Empty:return None
                if c['action']!='watch':raise ValueError('FIELD_BOOTSTRAP_INTERRUPTED')
                if c['payload'].get('motion_generation')!=owner.gate.generation:raise ValueError('MOTION_GENERATION_CHANGED')
                self.pending=c
                return dict(sequence=c['sequence'],action='watch',challenge=c['payload'].get('challenge'),age_ms=c['payload'].get('source_age_ms'))
        def output(value):self._update(challenge=value['challenge'],watch_challenge=value['challenge'],motion_generation=self.gate.generation)
        try:
            observed=qualify(self.link,Incoming(),output,self.gate,self.clock,safety=self._safety,supervised_field_speed=CAP_V)
        except Exception as exc:
            observed=dict(status='INCONCLUSIVE',reason=reason_code(exc))
        finally:
            cleanup=self._cleanup()
        passed=observed['status']=='STOP_POLICY_PASS' and cleanup['cleanup_confirmed']
        receipt=dict(schema='field-stop-observation-1.0',context=self.context,config_sha256=digest(self.field_config),
            trial_id=self.field_trial['trial_id'],status='OBSERVED' if passed else 'INCONCLUSIVE',
            linear_command_cap_m_s=CAP_V,angular_stopping='NOT_MEASURED',body_stopping='NOT_MEASURED',
            scope='FORWARD_WHEEL_WATCHDOG_OBSERVATION_ONLY',observed=observed,cleanup=cleanup)
        stop_write=self._field_write('field-stop.json',receipt)
        if not passed:self.field_until=0.
        self._finish_field('PASS' if passed else 'INCONCLUSIVE','FORWARD_WHEEL_STOP_OBSERVATION',receipt=receipt,stop_write=stop_write)
        self.gate.pause('FIELD_BOOTSTRAP_COMPLETE')
        pending=self.field_pending.get(self.field_trial['trial_id'])
        if pending:pending['resume_generation']=self.gate.generation

    def _field_tick(self):
        if self.field_writer:self.field_writer.check()
        self._poll_field_writes()
        trial=self.field_trial
        if self.field_until and self.clock()>=self.field_until:
            self.field_until=0.;self._pause('FIELD_SUPERVISION_EXPIRED')
        if not trial or trial['status']!='RUNNING':return
        if trial['case']=='bootstrap_stop':return
        frame=self.native.latest_frame()
        try:
            if trial['case'] in {'stationary','soak'}:frame_points(frame,self.field_config,self.clock())
            else:
                selected,_,partial,_=control_observation(self.native,self.field_config,self.clock())
                if partial and partial['frame_sequence']!=trial.get('last_warning_frame'):
                    trial['last_warning_frame']=partial['frame_sequence']
                    trial['unknown_ring_observations']=trial.get('unknown_ring_observations',0)+1
                    trial['last_incomplete_raw_sha256']=partial['raw_sha256']
                frame=selected
            if frame['frame_sequence']!=trial['last_frame']:
                trial['last_frame']=frame['frame_sequence'];trial['frames']+=1
                trial['last_raw_sha256']=frame['raw_sha256']
        except (ValueError,TypeError,KeyError) as exc:
            if trial['case'] not in {'stationary','soak'}:
                self._finish_field('INCONCLUSIVE',reason_code(exc));self._pause('FIELD_COLLECTION_INVALID');return
            # Diagnostic zero-command collection preserves the whole requested
            # interval, including failures. Invalid rings never become PASS or
            # authorize motion; a later valid ring cannot erase the failure.
            key=(frame or {}).get('frame_sequence')
            if key!=trial.get('last_invalid_frame') or not trial.get('invalid_reasons'):
                trial['last_invalid_frame']=key
                trial['invalid_frames']=trial.get('invalid_frames',0)+1
                reasons=trial.setdefault('invalid_reasons',{})
                code=reason_code(exc);reasons[code]=reasons.get(code,0)+1
        if self.tracker and self.clock()-getattr(self,'field_tracking_written',-math.inf)>=1.:
            tracking=self.tracker.snapshot()
            self._field_write('field-tracking.json',dict(context=self.context,tracking=tracking))
            self.field_tracking_written=self.clock()
        elapsed=self.clock()-trial['started_s']
        if trial['case'] in {'stationary','soak'} and elapsed>=(300. if trial['case']=='soak' else 8.):
            invalid=trial.get('invalid_frames',0)
            self._finish_field('PASS' if trial['frames']>=10 and not invalid else 'INCONCLUSIVE',
                'NATIVE_COLLECTION_CONTAINS_INVALID_FRAMES' if invalid else 'ZERO_MOTION_NATIVE_COLLECTION',
                frames=trial['frames'],invalid_frames=invalid,invalid_reasons=trial.get('invalid_reasons',{}),
                collection_complete=True,strict_ring_quality='INCOMPLETE_RINGS' if invalid else 'COMPLETE_RINGS',
                raw_archive_integrity='PENDING_NATIVE_FINAL_MANIFEST',
                motion_authority='NOT_GRANTED_BY_COLLECTION',
                duration_s=elapsed,body_accuracy='NOT_MEASURED',
                scope='NATIVE_COLLECTION_WITH_NO_APP_MOTION_COMMANDS_NOT_PHYSICAL_IMMOBILITY_PROOF')
