# SPDX-License-Identifier: Apache-2.0
"""No devices: recording volume of a synthetic physical session at measured rates.

2026-10-27 session 2 recorded 26 MB/min and the PC archive reached its 768 MiB
budget after 31 min (STREAM_RECORDING_CAPACITY); attempt 1 driving at about
40 MB/min failed SESSION_JOURNAL_PENDING_BYTE_BUDGET after a 25 s SD write
stall. These sessions use the real robot emit/journal, ROS record delivery and
NativeStream scans, and the PC receive and archive encoding; only the control
snapshot, sensor bytes and clocks are synthetic.
"""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as S
import unittest

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from fleet_worker import FleetWorker
from fleet_control import RosRecordDelivery
from native_stream import NativeStream
from field_config import checked_config,digest
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_BYTES
from twinpulse_core.robot_lineage import twin_context
from twinpulse_core.robot_timing_profile import profile as timing_profile,digest as timing_digest,runtime_policy,TimingAccumulator
from twinpulse_app.physical_live_session import PhysicalLiveSession,StreamEvidence
from twinpulse_app.physical_live_history import recover_live_history
from tests.integration import test_physical_live_session as live_tests

# Rates per second recorded on 2026-10-27 (session 7d9e86d5) and the nominal driving rates of attempt 1.
TODAY=dict(heartbeat=5.8,input_window=20,watch=4,scan=4.9,native=8.9,odom=11.6,tf=11.6,sensor_state=13.9,guard=18.3,drive=4,pc_watch=11.5)
NOMINAL=dict(heartbeat=10,input_window=20,watch=10,scan=5,native=10,odom=20,tf=20,sensor_state=20,guard=50,drive=20,pc_watch=10)
# Display diagnostics the live view may show up to one sample (1 s) late; everything else must be exact.
SAMPLED={'timing_measurement','telemetry_diagnostic','event_emission','ros_record_delivery','lidar','sensor_frame','motion_observation','recording'}
R=random.Random(7)
hx=lambda n:''.join(R.choice('0123456789abcdef') for _ in range(n))
hs=lambda tag,n,size=64:hashlib.sha256(f'{tag}:{n}'.encode()).hexdigest()[:size]
ROBOT,BINDING='b'*32,'a'*64
PROFILE=timing_profile(ROBOT,BINDING)
TWIN=twin_context('default','s'*32,dict(engine_connected=True,snapshot=dict(applied_revision='rev-'+hx(12)),engine_session_id=hx(32),stage_epoch=hx(16)),
    anchor=dict(position_m=[1.25,-.5,0.],source='operator_estimate_not_localized',scene_revision='rev-'+hx(12),frame_id='isaac_world',aligned=False,visual_epoch=hx(16)))
CONTEXT=dict(schema='physical-live-start-2.0',operation_id=hx(32),robot_id=ROBOT,project_id='default',connection_epoch=hx(32),
    binding_sha256=BINDING,worker_sha256=hx(64),source_twin_context=TWIN,timing_profile=PROFILE,timing_profile_sha256=timing_digest(PROFILE))
DEVICE=dict(boot_id='%s-%s-%s-%s-%s'%(hx(8),hx(4),hx(4),hx(4),hx(12)),release_id=hx(64))
CONFIG=checked_config(dict(schema='supervised-field-test-1.0',robot_id=ROBOT,binding_sha256=BINDING,provenance='operator_reviewed',
    axes_reviewed=True,angle_sign=-1,footprint_radius_m=.105,sensor_x_m=-.032,sensor_y_m=0.,sensor_yaw_rad=math.pi,
    wheel_metres_per_tick=.0015339807878856412,wheel_separation_m=.16))


def trial(case,status,started):
    """A completed field trial as the robot keeps it in every heartbeat (context, decision, persistence)."""
    value=dict(trial_id=hx(32),case=case,status=status,started_s=started,config_sha256=digest(CONFIG),request_id=hx(32),
        context=dict(CONTEXT,**DEVICE),request_twin_context=deepcopy(TWIN),frames=R.randrange(30,200),last_frame=R.randrange(1000,9000),
        last_raw_sha256=hx(64),reason='ZERO_MOTION_NATIVE_COLLECTION',ended_s=started+8.4,decision=dict(status=status,reason='ZERO_MOTION_NATIVE_COLLECTION'),
        persistence=dict(state='COMMITTED',writes=[dict(token=hx(32),sha256=hx(64),bytes=R.randrange(2000,90000),durable=True,
            committed_s=started+9.1,member='field-trials.json')]))
    value['result']=dict(frames=value['frames'],invalid_frames=0,invalid_reasons={},collection_complete=True,strict_ring_quality='COMPLETE_RINGS',
        raw_archive_integrity='PENDING_NATIVE_FINAL_MANIFEST',motion_authority='NOT_GRANTED_BY_COLLECTION',duration_s=8.0123456789,
        body_accuracy='NOT_MEASURED',scope='NATIVE_COLLECTION_WITH_NO_APP_MOTION_COMMANDS_NOT_PHYSICAL_IMMOBILITY_PROOF',
        stop_readback_confirmed=True,publications=R.randrange(0,90),
        progress=dict(body_progress='UNVERIFIED',wheel_progress='OBSERVED',wheel_centre_m=.0987654321,wheel_yaw_rad=.00123456789))
    return value


STOP_RECEIPT=dict(schema='field-stop-observation-1.0',context=dict(CONTEXT,**DEVICE),config_sha256=digest(CONFIG),trial_id=hx(32),status='OBSERVED',
    linear_command_cap_m_s=.03,angular_stopping='NOT_MEASURED',body_stopping='NOT_MEASURED',scope='FORWARD_WHEEL_WATCHDOG_OBSERVATION_ONLY',
    observed=dict(status='STOP_POLICY_PASS',stop_latency_s=.1234567891,zero_command_s=101.123456789,readback=dict(left=0,right=0,torque=False),
        publications=14,first_publish_s=100.98765432,last_publish_s=101.0123456789,policy_sha256=hx(64)),
    cleanup=dict(cleanup_confirmed=True,ros_stop_confirmed=True,base_reaped=True,independent_idle_confirmed=True,errors=[]),
    input_diagnostic=dict(first_fault=None,phases=[dict(phase='ARMED_WATCH',sequence=12,generation=3,source_age_ms=23.456789,admitted_s=100.123456,
        deadline_s=100.473456,challenge_age_s=.0123456)]*2,phase_count=31),
    persistence=dict(state='COMMITTED',writes=[dict(token=hx(32),sha256=hx(64),bytes=12345,durable=True)]*2))
TRIALS=[dict(trial('bootstrap_stop','PASS',90.),result=dict(receipt=deepcopy(STOP_RECEIPT))),
    trial('stationary','PASS',100.),trial('forward','INCONCLUSIVE',120.)]


def accumulated(duration):
    measurements=TimingAccumulator()
    for load,names in (('base',3),('lidar',4),('tracking_recording',7)):
        for name in ('sensor_source_ms','sensor_receipt_ms','guard_receipt_ms','native_receipt_ms','odom_interval_ms','odom_source_ms','wheel_interval_ms')[:names]:
            for k in range(50):measurements.observe(name,(k*37%40)+.123456,100.+k*.1,load)
    return dict(measurements.snapshot(),duration_s=duration)


class Control:
    """The robot control snapshot at its recorded size (about 35 KB, mostly unchanging field/guard receipts)."""
    def __init__(self,*_,**__):
        self.lock=threading.RLock();self.state=dict(control_state='READY');self.stop_requested=threading.Event();self.cancel=threading.Event()
        self.field_until=0.;self.now=0.;self.driving=False;self.beat=0;self.timing=accumulated(0.)
        self.static=dict(reason=None,timing_policy=runtime_policy(PROFILE['values']),timing_values=deepcopy(PROFILE['values']),
            timing_profile_sha256=CONTEXT['timing_profile_sha256'],profile=None,drive_ready=True,applied_motion_epoch=hx(32),blockers=[],
            qualification=dict(status='QUALIFIED',scope='LEGACY_LOCAL_STOP_SAME_BOOT_RELEASE',native_integration='HARDWARE_NOT_RUN',
                expected=dict(DEVICE,schema='manual-stop-2.0',policy_sha256=hx(64),timing_values_sha256=hx(64)),prior_status='QUALIFIED'),
            output_guard_build=dict(source_id=hx(64),artifacts=[dict(name=n,sha256=hx(64),bytes=R.randrange(10**5,10**6)) for n in ('turtlebot3_node','libguard.so')],
                tests=dict(command_guard_test='PASS',torque_off_test='PASS',ros_guard_test='PASS'),motion_enabled=False),
            output_guard_diagnostic=dict(attempt_id=hx(32),source_id=hx(64),status='VERIFIED_NOT_RUNNING',active_step=None,
                binding=dict({k:CONTEXT[k] for k in ('operation_id','robot_id','project_id','connection_epoch','worker_sha256','binding_sha256')},**DEVICE,
                    request_id=hx(32),trigger='EXPLICIT_PREPARE',source_twin_context_id=TWIN['context_id']),error=None,evidence_error=None,
                log_tail=dict(schema='output-guard-log-tail-1.0',attempt_id=hx(32),source_id=hx(64),source_size_bytes=48213,exported_bytes=48213,sha256=hx(64),source_complete=True)),
            output_guard_diagnostic_expected=True,output_guard_log_expected=True,
            output_timing=dict(output_timeout_ms=400,applied=True,source='motion_guard/timing',observed_s=100.123,readback=dict(timeout_ms=400,ok=True)),
            stop_receipt=dict(request_id=hx(32),motion_epoch=hx(32),zero_off_readback_confirmed=True,observed_s=120.5,reason='OPERATOR_STOP',publications=12),
            task_local_state=dict(pose_epoch=hx(32),fault=None,pose_basis='WHEEL_ODOMETRY_SINCE_CONNECT_NOT_LOCALIZED',independent_body=False,pose_valid=True))
        self.idle=None

    def start(self):pass
    def close(self):return dict(control_state='CLOSED',worker_reaped=True,cleanup_confirmed=True)

    def snapshot(self):
        t,beat,driving=self.now,self.beat,self.driving;self.beat+=1
        frame,segment=int(t*5),int(t//20)
        if int(t)!=int(t-.1):self.timing=accumulated(t)
        guard=dict(scope='RECEIPT_BASED_SUPERVISED_PROXIMITY_NOT_STOP_DISTANCE',estimated_radial_clearance_m=.8+(beat%97)/100,threshold_m=.1,
            raw_sha256=hs('raw',frame),nodes_sha256=hs('nodes',frame),frame_sequence=frame,receipt_age_s=(beat%11)/100,raw_ring_complete=True,
            latest_raw_ring_complete=True,latest_raw_frame_sequence=frame,latest_raw_sha256=hs('raw',frame),latest_unknown_bytes=0,
            latest_receipt_age_s=(beat%13)/100,valid_return_count=430,latest_valid_return_count=430,maximum_return_gap_deg=10.,
            coverage_policy='POSITIVE_VALID_RETURNS_MAXIMUM_GAP_10_DEG_NOT_ZERO_AS_FREE_SPACE',
            observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',acquisition_timing='UNQUALIFIED',config_sha256=digest(CONFIG))
        observation=dict(schema='robot-wheel-observation-1.0',state='OBSERVING' if driving else 'ENDED',operation_id=CONTEXT['operation_id'],robot_id=ROBOT,
            source_twin_context_id=TWIN['context_id'],motion_epoch=hs('motion',segment,32),request_id=hs('request',segment,32),
            latest_request_id=hs('latest',int(t*4),32),action='task',direction='forward',started_s=segment*20.,first_sample_s=segment*20.+.1,
            sample_s=t-.03,ended_s=None if driving else t-1.,samples=beat%200,first_encoders=[123456,654321],encoders=[123456+beat,654321+beat],
            wheel_metres_per_tick=CONFIG['wheel_metres_per_tick'],wheel_separation_m=.16,receipt_s=t-.03,source_age_s=.02,source_s=t-.05,
            left_m=beat*.0015,right_m=beat*.0015,centre_m=beat*.0015,yaw_rad=0.,result=None if driving else 'INCONCLUSIVE_BODY_MOTION',
            body_progress='UNKNOWN',basis='WHEEL_ENCODERS_ONLY',stop_readback_confirmed=None if driving else True,
            reason=None if driving else 'TASK_WHEEL_ODOM_TARGET_REACHED',wheel_data_quality='MEASURED_ENCODER_DELTA_UNQUALIFIED')
        command=dict(request_id=hs('command',segment,32),action='task',state='RUNNING' if driving else 'COMPLETED',direction='forward',amount=.5,
            remaining_m=.5-(t%20)*.025 if driving else 0.,started_s=segment*20.,motion_epoch=hs('motion',segment,32),route_id=hs('route',0,32),leg=2,legs=5)
        if not driving:
            # A stopped robot repeats its last guard/observation/command receipts unchanged.
            self.idle=self.idle or dict(guard=guard,motion_observation=observation,command=command)
            guard,observation,command=self.idle['guard'],self.idle['motion_observation'],self.idle['command']
        else:self.idle=None
        field=dict(mode='SUPERVISED_FIELD_TEST',config=CONFIG,config_sha256=digest(CONFIG),armed=True,remaining_s=900.-t%900,blockers=[],
            stop_receipt=STOP_RECEIPT,active_trial=None,trials=TRIALS,evidence_error=None,
            evidence_status=dict(phase='IDLE',queued=0,committed=5,error=None,phase_max=dict(FSYNC=1.058,ACK_FSYNC=.8)),
            tracking=dict(status='ESTIMATED',epoch=hs('epoch',0,32),pose=[round(.5*math.sin(frame/50),6),round(.3*math.cos(frame/60),6),round(frame/100%6,6)],
                sample_s=frame/5,raw_sha256=hs('raw',frame),previous_raw_sha256=hs('raw',frame-1),frame_sequence=frame,
                compute_timing=dict(job_id=frame,compute_started_s=frame/5+.05,compute_ended_s=frame/5+.07,stage='COMPLETED',compute_elapsed_s=.02,delivery_elapsed_s=.021),
                residual_m=.012,accuracy='UNQUALIFIED',independent=True),
            native_observation=dict(frame_sequence=frame,stream_id='native-'+'d'*32,raw_sha256=hs('raw',frame),raw_ring_complete=True,unknown_bytes=0,
                receipt_age_s=(beat%17)/100,policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1'))
        return dict(self.static,control_state='ACTIVE' if driving else 'READY',challenge=hx(24),watch_challenge=hx(24),motion_generation=40+int(t//60),
            battery=dict(voltage_v=round(11.9-t*1e-5,3),source='measured',origin='ros_sensor_state',sample_monotonic_s=t-.02),
            pose=dict(x=.5*math.sin(t/30),y=.3*math.cos(t/40),yaw=(t/20)%math.tau-math.pi,sample_s=t-.03,frame_id='odom',source='wheel_odometry',aligned=False),
            ros_record_delivery=dict(accepted=beat*7,saved=beat*7,pending=0,error=None,oldest_pending_s=0.,maximum_delivery_s=.0123,worker_reaped=False),
            guard=guard,progress=dict(body_progress='UNVERIFIED',wheel_progress='OBSERVED' if driving else 'UNKNOWN'),
            telemetry_diagnostic=dict(reason=None,source_age_s=(beat%7)/100,sensor_receipt_age_s=(beat%5)/100,guard_receipt_age_s=(beat%3)/100,checked_monotonic_s=t-.004),
            field=field,command=command,motion_observation=observation,timing_measurement=self.timing)


class Native:
    """Heartbeat-side sensor view; the scan and raw events come from the real NativeStream (below)."""
    def __init__(self,clock):self.clock=clock
    def latest_frame(self):
        frame=int(self.clock()*5)
        return dict(frame_sequence=frame,raw_sha256=hs('raw',frame),nodes_sha256=hs('nodes',frame),complete=True,
            timing=dict(receipt_start_s=frame/5,receipt_end_s=frame/5+.1,basis='serial_receipt_unqualified'))
    def snapshot(self):
        frame=int(self.clock()*5)
        return dict(lidar_state='STREAMING',recording_state='RECORDING',reason=None,bytes_received=frame*2700,frame_count=frame,
            stream_id='native-'+'d'*32,checksum_errors=0,unframed_bytes=12,archive=dict(accepted=frame*2,saved=frame*2,queued=0,error=None,writer_alive=True))
    def start(self):pass
    def stop(self):pass
    def close(self):return dict(lidar_state='OFF')


def ring(sequence,points=400):
    """One COIN-D4 ring of room-like millimetre ranges with valid checksums."""
    out=bytearray();per=math.ceil(points/12);noise=random.Random(sequence)
    for p in range(12):
        n=min(per,points-p*per);first,last=p*30,(p+1)*30-360/points
        a,b=int(first*64)*2+1,int(last*64)*2+1;ct=int(p==0);payload=b''
        for j in range(n):
            i=p*per+j;d=int((1.5+abs(math.sin(i*math.tau/points*2))+.3*math.cos(i*math.tau/points*5))*1000)+noise.randrange(-2,3);q=180+noise.randrange(-3,4)
            payload+=bytes(((q<<2)&255,((q>>6)&3)|((d%64)<<2),d//64))
        checksum=0x55aa^(ct|n<<8)^a^b
        for i in range(0,len(payload),3):checksum^=payload[i]^int.from_bytes(payload[i+1:i+3],'little')
        out+=b'\xaa\x55'+struct.pack('<BBHHH',ct,n,a,b,checksum)+payload
    return bytes(out)


def native_events(seconds=12.):
    """Scan and raw events of the real NativeStream decoding 7.2 Hz rings on a fake serial channel."""
    events=[];clock=[1000.];data=b''.join(ring(i) for i in range(int(seconds*7.2)+3));per=int(len(data)/(seconds*20))
    class Channel:
        cleanup=staticmethod(nullcontext)
        def __init__(self):self.at=0
        def configure(self):pass
        def write(self,value):return len(value)
        def read(self,_):
            clock[0]+=.05
            if self.at>=len(data):stream.stop();return b''
            self.at+=per;return data[self.at-per:self.at]
        def drain(self,_):return 0
        def restore(self):return True
        def close(self):pass
    with tempfile.TemporaryDirectory() as folder:
        stream=NativeStream(folder,lambda kind,value:events.append((kind,deepcopy(value))),channel_factory=Channel,clock=lambda:clock[0],maximum_bytes=64*1024*1024)
        stream.start();stream.thread.join(60)
    return [v for k,v in events if k=='scan'],[v for k,v in events if k=='raw']


NATIVE={}
def native():
    if not NATIVE:NATIVE['scans'],NATIVE['raws']=native_events()
    return NATIVE['scans'],NATIVE['raws']


class Sink:
    """The robot journal's disk: counts bytes instead of writing 800 MB; `stalled` holds the writer like a slow SD card."""
    def __init__(self):self.bytes=0;self.open=threading.Event();self.open.set()
    def write(self,line):self.open.wait();self.bytes+=len(line.encode('utf-8'));return len(line)
    def flush(self):pass
    def close(self):pass


def message(**fields):return S(cdr=hashlib.sha256(repr(sorted(fields.items())).encode()).digest()*(fields.pop('size',64)//32+1),**fields)


class Session:
    def __init__(self,folder,rates,driving,*,on_heartbeat=None,archive=None):
        self.rates,self.driving,self.on_heartbeat,self.archive=rates,driving,on_heartbeat,archive
        self.now=0.;self.lines=[];self.pc_bytes=self.heartbeat_bytes=0;self.peak_pending=0;self.bodies=[]
        self.worker=FleetWorker({k:v for k,v in CONTEXT.items()},folder,lambda *_:None,control_factory=Control,
            native_factory=lambda *_:Native(lambda:self.now),line_writer=self.lines.append,clock=lambda:self.now)
        self.worker.context.update(DEVICE);self.sink=self.worker.journal.stream=Sink()
        self.control=self.worker.control
        self.delivery=RosRecordDelivery(self.worker.emit,lambda m:m.cdr,{'odom':'nav_msgs/msg/Odometry','/tf':'tf2_msgs/msg/TFMessage',
            'sensor_state':'turtlebot3_msgs/msg/SensorState','motion_guard/status':'std_msgs/msg/String','guarded_cmd_vel':'geometry_msgs/msg/TwistStamped'})
        self.pc=PhysicalLiveSession(ROOT,folder,identity=Path(folder),known_hosts=Path(folder),clock=lambda:self.now,wall=lambda:self.now+1.7e9)
        self.pc.context={k:CONTEXT[k] for k in ('schema','operation_id','robot_id','project_id','connection_epoch','binding_sha256','worker_sha256',
            'source_twin_context','timing_profile','timing_profile_sha256')}
        if archive is not None:self._archive(json.dumps(dict(self.pc.context,schema='physical-live-pc-start-2.0'),separators=(',',':')))
        self.scans,self.raws=native()
        self.due={};self.sequence=0;self.guard='armed'

    def _archive(self,line):
        raw=(line+'\n').encode();self.pc_bytes+=len(raw)
        if self.archive is not None and not self.archive.append(raw):raise AssertionError(self.archive.error)

    def _every(self,name,t):
        rate=self.rates[name]
        if t+1e-9<self.due.get(name,0.):return False
        self.due[name]=self.due.get(name,0.)+1/rate;return True

    def _ros(self,topic,value,t):
        self.sequence+=1
        self.delivery(topic,value,dict(sequence=self.sequence,receipt_monotonic_ns=int(t*1e9),receipt_ros_now_ns=int(t*1e9),
            source_stamp_ns=int(t*1e9)-20_000_000,source_age_at_receipt_s=.02))

    def drain(self):
        deadline=time.monotonic()+30
        while self.delivery.status()['pending'] and time.monotonic()<deadline:time.sleep(.0005)
        end=len(self.lines)
        for line in self.lines[:end]:
            event=json.loads(line);self.pc.receive(event)
            if event['kind']=='heartbeat':
                self.heartbeat_bytes+=len(line)+1
                if self.on_heartbeat:self.on_heartbeat(event,self.pc.last)
            # The PC archive line: the received event without its nonces (as PhysicalLiveSession._run writes it).
            archived=dict(event,data={k:v for k,v in event['data'].items() if k not in {'challenge','watch_challenge'}})
            self._archive(json.dumps(archived,separators=(',',':'),allow_nan=False))
        del self.lines[:end]
        deadline=time.monotonic()+30
        while self.archive is not None and self.archive.pending_bytes and time.monotonic()<deadline:time.sleep(.0005)

    def run(self,seconds,*,stall=None,stop_on_failure=False):
        step=0;t=0.;k=0;stalled=False
        while t<seconds:
            self.now=self.control.now=t;driving=self.control.driving=self.driving(t)
            if stall is not None:
                if stall[0]<=t<stall[1] and not stalled:self.sink.open.clear();stalled=True
                elif t>=stall[1] and stalled:self.sink.open.set();stalled=False
            if self._every('heartbeat',t):
                body=self.worker.heartbeat()
                if self.on_heartbeat:self.bodies.append((t,deepcopy(body)))
                self.worker.emit('heartbeat',body)
            if self._every('input_window',t):
                challenge=hx(24);self.worker.emit('command',dict(action='input_window',schema='robot-input-window-1.0',challenge=challenge,
                    watch_challenge=challenge,motion_generation=40,issued_s=t-.001,scope='CURRENT_INPUT_CHALLENGE_NOT_MOTION_ACK'))
            if self._every('watch',t):
                self.worker.emit('command',dict(request_id=hx(32),action='watch',status='COMPLETED',input_timing=dict(sequence=k,age_ms=12.3456789,admitted_s=t)))
            if self._every('scan',t):self.worker.emit('scan',self.scans[k%len(self.scans)])
            if self._every('native',t):self.worker.emit('raw',self.raws[k%len(self.raws)])
            if self._every('odom',t):
                stamp=S(sec=int(t),nanosec=int(t%1*1e9));pose=S(position=S(x=.5*math.sin(t/30),y=.3*math.cos(t/40),z=0.),orientation=S(x=0.,y=0.,z=math.sin(t/40),w=math.cos(t/40)))
                self._ros('odom',message(header=S(stamp=stamp,frame_id='odom'),child_frame_id='base_footprint',pose=S(pose=pose),size=732),t)
                if self._every('tf',t):
                    self._ros('/tf',message(transforms=[S(header=S(stamp=stamp,frame_id='odom'),child_frame_id='base_footprint',
                        transform=S(translation=pose.position,rotation=pose.orientation))],size=108),t+.0002)
            if self._every('sensor_state',t):self._ros('sensor_state',message(stamp=t,size=52),t)
            if self._every('guard',t):
                if k%5000==4999:self.guard={'armed':'timeout','timeout':'armed'}[self.guard]
                self._ros('motion_guard/status',message(data=self.guard,size=34),t)
            if driving and self._every('drive',t):
                snapshot=self.control.snapshot()
                self.worker.emit('command',dict(request_id=hx(32),action='drive',status='PUBLISHED',direction='forward',linear_m_s=.05,angular_rad_s=0.,
                    source_created_s=t-.0312345,source_basis='ORIGINAL_REMOTE_INPUT',applied_motion_epoch=hs('motion',int(t//20),32),guard=snapshot['guard'],
                    progress=snapshot['progress'],publisher_decision=dict(published=True,source_age_s=.0312345678,sequence=k,stamp_ns=int(t*1e9))))
                self._ros('guarded_cmd_vel',message(v=.05,t=t,size=84),t)
            elif not driving:self.due['drive']=t
            if self._every('pc_watch',t):
                self._archive(json.dumps(dict(schema='physical-live-pc-command-2.0',**{x:CONTEXT[x] for x in ('operation_id','robot_id','project_id','connection_epoch')},
                    motion_epoch=hx(32),request_id=hx(32),sequence=k,action='watch',payload=dict(motion_generation=40,source_age_ms=0),
                    source_twin_context_id=TWIN['context_id'],request_twin_context=None,pc_queue_age_s=.0012345,pc_sent_monotonic_s=t,execution_confirmed=False),separators=(',',':')))
            self.peak_pending=max(self.peak_pending,self.worker.journal.pending_bytes)
            k+=1;step+=1;t=step*.01
            if step%50==0:
                self.drain()
                if not stalled:
                    # A healthy SD card keeps up in real time; the synthetic clock runs much faster.
                    deadline=time.monotonic()+30
                    while self.worker.journal.pending_bytes and time.monotonic()<deadline:time.sleep(.0005)
                if stop_on_failure and self.worker.recording_failed:break
        self.sink.open.set();self.drain();self.delivery.close()
        self.worker.protocol.close(timeout=5);self.drain()
        return self.worker.journal.close(timeout=60)


class RecordingVolumeTests(unittest.TestCase):
    def test_forty_minutes_of_ready_and_driving_at_todays_rates_fit_the_robot_and_pc_budgets(self):
        minutes=40
        with tempfile.TemporaryDirectory() as folder:
            session=Session(folder,TODAY,lambda t:t%120>=60)
            journal=session.run(minutes*60.,stop_on_failure=True)
        self.assertIsNone(session.worker.recording_failure_reason)
        self.assertIsNone(journal['error'])
        self.assertLessEqual(journal['reserved_bytes'],EVENT_ARCHIVE_BYTES)
        self.assertLessEqual(session.pc_bytes,EVENT_ARCHIVE_BYTES)
        # The goal is a 60-minute session: the same mix for 60 minutes stays under the PC archive budget.
        self.assertLess(session.pc_bytes/minutes*60,EVENT_ARCHIVE_BYTES)

    def test_twice_attempt_1s_25_second_sd_write_stall_fits_the_pending_budget_while_driving(self):
        with tempfile.TemporaryDirectory() as folder:
            session=Session(folder,NOMINAL,lambda t:True)
            journal=session.run(60.,stall=(5.,55.))
        self.assertIsNone(session.worker.recording_failure_reason)
        self.assertIsNone(journal['error'])
        self.assertLess(session.peak_pending,journal['pending_byte_limit'])
        self.assertEqual(journal['saved'],journal['accepted'])

    def test_heartbeats_shrink_yet_restore_exactly_for_the_live_view_and_the_cold_history(self):
        restored=[]
        with tempfile.TemporaryDirectory() as folder:
            evidence=StreamEvidence(Path(folder)/'archive')
            session=Session(folder,NOMINAL,lambda t:t%40>=20,on_heartbeat=lambda event,last:restored.append(deepcopy(last)),archive=evidence)
            session.run(80.)
            receipt=evidence.close(cleanup_confirmed=True)
            history=recover_live_history(Path(folder)/'archive',receipt,source_twin_context=TWIN,
                **{k:CONTEXT[k] for k in ('operation_id','project_id','robot_id','connection_epoch','binding_sha256')})
        whole=sum(len(json.dumps(body,separators=(',',':'))) for _,body in session.bodies)
        self.assertLess(session.heartbeat_bytes,whole/3)
        self.assertEqual(len(restored),len(session.bodies))
        for index,((at,body),view) in enumerate(zip(session.bodies,restored)):
            recent=[b for t,b in session.bodies[max(0,index-12):index+1] if at-1.1<=t]
            self.assertEqual(set(view),set(body),at);self.assertEqual(set(view['field']),set(body['field']),at)
            for key,value in body.items():
                if key in SAMPLED:self.assertTrue(any(b[key]==view[key] for b in recent),(at,key))
                elif key!='field':self.assertEqual(view[key],value,(at,key))
            for name,value in body['field'].items():
                if name=='native_observation':self.assertTrue(any(b['field'][name]==view['field'][name] for b in recent),(at,name))
                else:self.assertEqual(view['field'][name],value,(at,name))
        # The cold history tail shows the same whole heartbeats as the live view (minus nonces).
        tail=[e['data'] for e in history['events'] if e['kind']=='heartbeat']
        self.assertGreater(len(tail),5)
        self.assertEqual(tail,[{k:v for k,v in view.items() if k not in {'challenge','watch_challenge'}} for view in restored[-len(tail):]])


class RecordingBudgetViewTests(unittest.TestCase):
    LIMIT=6_000_000

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=10.
        self.session=PhysicalLiveSession(ROOT,self.tmp.name,identity=Path('unused'),known_hosts=Path('unused'),
            process_factory=lambda *a,**k:self.fail('No SSH in this test'),clock=lambda:self.now,wall=lambda:self.now+100.)
        self.identity=dict(operation_id='o'*32,robot_id='b'*32,project_id='project-a',connection_epoch='c'*32)
        self.session.context=dict(self.identity,worker_sha256='a'*64)
        self.session.evidence=StreamEvidence(Path(self.tmp.name)/'archive',maximum_bytes=self.LIMIT)
        self.addCleanup(lambda:self.session.evidence.close(cleanup_confirmed=False))

    def beat(self,**data):
        self.session.receive(dict(schema='physical-live-event-1.0',**self.identity,sequence=self.session.sequence+1,kind='heartbeat',
            robot_monotonic_s=self.now,data=dict(dict(challenge='x'*24,motion_generation=1,boot_id='b'*32,release_id='c'*64,worker_sha256='a'*64,
            battery=dict(voltage_v=11.8,percent=None,source='measured',age_ms=50),control_state='READY',lidar_state='OFF'),**data)))
        request='r%031d'%self.session.sequence;self.session.watches[request]=self.now
        self.session.receive(dict(schema='physical-live-event-1.0',**self.identity,sequence=self.session.sequence+1,kind='command',
            robot_monotonic_s=self.now,data=dict(action='watch',request_id=request,status='COMPLETED')))

    def archive(self,size):
        line=b'x'*(size-1)+b'\n'
        return self.session.evidence.append(line)

    def budget(self):
        value=self.session.snapshot();return value.get('recording_budget') or {},value

    def test_warning_from_75_percent_with_minutes_left_then_the_limit_names_itself(self):
        for _ in range(42):self.assertTrue(self.archive(100_000))
        for second in range(70):
            self.assertTrue(self.archive(10_000))
            for _ in range(10):self.beat();self.now+=.1
            if second==25:
                budget,value=self.budget()
                self.assertEqual(budget.get('state'),'OK');self.assertIsNone(value['link_detail'])
        budget,value=self.budget()
        self.assertEqual((budget.get('state'),budget.get('source')),('NEAR_LIMIT','pc'))
        self.assertAlmostEqual(budget['rate_bytes_per_s'],10_000,delta=500)
        self.assertAlmostEqual(budget['minutes_left'],(self.LIMIT-budget['used_bytes'])/10_000/60,delta=.1)
        self.assertGreater(budget['minutes_left'],1.)
        while self.archive(100_000):pass
        self.beat()
        budget,value=self.budget()
        self.assertEqual(budget.get('state'),'LIMIT_REACHED')
        self.assertEqual(value['link_detail'],'Recording limit reached - reconnect to continue')
        self.assertEqual(value['recording']['error'],'ValueError:STREAM_RECORDING_CAPACITY')

    def test_the_robot_journal_budget_counts_and_only_its_byte_budget_is_the_limit(self):
        self.archive(1000)
        self.beat(recording=dict(reserved_bytes=int(.8*EVENT_ARCHIVE_BYTES),byte_limit=EVENT_ARCHIVE_BYTES,error=None))
        budget,_=self.budget()
        self.assertEqual((budget.get('state'),budget.get('source')),('NEAR_LIMIT','robot'))
        self.now+=1;self.beat(recording_failure_reason='SESSION_JOURNAL_PENDING_BYTE_BUDGET',blockers=['RECORDING_INCOMPLETE'],
            recording=dict(reserved_bytes=int(.8*EVENT_ARCHIVE_BYTES),byte_limit=EVENT_ARCHIVE_BYTES,error='SESSION_JOURNAL_PENDING_BYTE_BUDGET'))
        budget,value=self.budget()
        # A write stall is a recording fault, not the session limit.
        self.assertEqual(budget.get('state'),'NEAR_LIMIT');self.assertNotIn('Recording limit',value['link_detail'] or '')
        self.now+=1;self.beat(recording_failure_reason='SESSION_LOG_BYTE_BUDGET',blockers=['RECORDING_INCOMPLETE'],
            recording=dict(reserved_bytes=EVENT_ARCHIVE_BYTES-10,byte_limit=EVENT_ARCHIVE_BYTES,error='SESSION_LOG_BYTE_BUDGET'))
        budget,value=self.budget()
        self.assertEqual(budget.get('state'),'LIMIT_REACHED')
        self.assertEqual(value['link_detail'],'Recording limit reached - reconnect to continue')
        self.assertEqual(value['control_owner_state'],'EXITED_RECONNECT_REQUIRED')


class FleetRecordingBudgetTests(unittest.TestCase):
    setUp=live_tests.FleetPhysicalEnvelopeTests.setUp
    action=live_tests.FleetPhysicalEnvelopeTests.action

    def test_the_fleet_row_carries_the_warning_and_the_limit_reason_to_the_app(self):
        original=self.live.snapshot
        budget=dict(state='NEAR_LIMIT',source='pc',used_bytes=640_000_000,limit_bytes=EVENT_ARCHIVE_BYTES,fraction=.79,warning_fraction=.75,
            rate_bytes_per_s=150_000.,minutes_left=18.5,basis='LAST_60_S_RATE_DISPLAY_ONLY')
        self.live.snapshot=lambda:dict(original(),recording_budget=deepcopy(budget))
        self.action('focus');row=self.action('connect')['robots'][0]
        self.assertEqual(row.get('recording_budget'),budget)
        budget.update(state='LIMIT_REACHED',minutes_left=None)
        self.live.snapshot=lambda:dict(original(),connection_state='DEGRADED',live_heartbeat=False,recording_budget=deepcopy(budget),
            link_detail='Recording limit reached - reconnect to continue')
        row=self.fleet.snapshot()['robots'][0]
        self.assertEqual(row.get('recording_budget'),budget)
        self.assertEqual(row['link_detail'],'Recording limit reached - reconnect to continue')
        # After the session ends the limit still explains it; an old near-limit warning does not.
        self.live.closed=True
        self.assertEqual(self.fleet.snapshot()['robots'][0].get('recording_budget'),budget)
        budget.update(state='NEAR_LIMIT',minutes_left=3.)
        self.assertIsNone(self.fleet.snapshot()['robots'][0].get('recording_budget'))


if __name__=='__main__':
    unittest.main()
