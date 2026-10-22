# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit robot-local entry: reviewed base, fresh challenge inputs, owned cleanup.

No boot service and no automatic deployment. Never called during PC-only tests.
Stdout is a bounded JSON-line protocol; logs/receipts stay in this run's directory.
"""
import json
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid

from teleop_contract import InputGate, MotionPaused, DIRECTIONS, MANUAL_DIRECTIONS, settling_details, TERMINAL_STOPS, finish_segment
from control_timing import INPUT_TTL_S
from stop_policy import assess_stop, POLICY, POLICY_SHA256, MM_PER_TICK, OBSERVE_S


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def emit(value):
    # No Python stdout-buffer lock in a daemon sender blocked by its peer.
    emit_line(json.dumps(value, allow_nan=False))


def emit_line(line):
    """Trusted pre-encoded JSON body, not an additional command interpreter."""
    if not isinstance(line,str) or '\n' in line:raise ValueError('PROTOCOL_PREPARED_LINE')
    data=(line+'\n').encode('utf-8')
    while data:
        written=os.write(sys.stdout.fileno(),data)
        if written<=0:raise OSError('PROTOCOL_WRITE_FAILED')
        data=data[written:]


class ProtocolOutbox:
    """Bounded FIFO mirror: transport stalls cannot block the wheel loop.

    No event drops, nonce restamping or automatic resume. The robot-local
    journal remains authoritative. Buffered manual sessions expose short delay
    without closing; actual capacity/write failures still latch a fault. No
    delayed nonce/input is restamped. Cleanup never waits on the sender thread.
    """
    def __init__(self, writer, *, clock=time.monotonic, max_messages=128,
                 max_bytes=1024*1024, stall_s=.2, buffered=False,line_writer=None):
        self.writer,self.clock=writer,clock
        self.line_writer=line_writer
        self.max_bytes,self.stall_s=max_bytes,stall_s
        self.queue=queue.Queue(maxsize=max_messages)
        self.lock=threading.Lock()
        self.pending={};self.pending_bytes=0;self.sequence=0
        self.closed=False;self.error=None;self.max_write_s=0.;self.sent=0
        self.buffered=buffered is True;self.buffering=False
        self.thread=threading.Thread(target=self._write,daemon=True)
        self.thread.start()

    def check(self):
        with self.lock:
            self.buffering=bool(self.pending and self.clock()-min(self.pending.values())>=self.stall_s)
            if self.buffering and not self.buffered:
                self.error=self.error or 'PROTOCOL_DELIVERY_STALLED'
            error=self.error
        if error:raise ValueError(error)

    def send(self,value):
        # Serialize now, not in the thread: mutable reports cannot change while
        # queued, and invalid/oversized messages never reach the wire.
        line=json.dumps(value,allow_nan=False)
        self.send_prepared(line)

    def send_prepared(self,line):
        """Enqueue an owned JSON line without serializing under an emit lock.

        Only the fixed local event builder calls this prepared path. Preserve
        the exact UTF-8 capacity and FIFO of send(), including the newline.
        """
        if not isinstance(line,str) or not line or '\n' in line:raise ValueError('PROTOCOL_PREPARED_LINE')
        size=len(line.encode('utf-8'))+1
        self.check()
        with self.lock:
            if self.closed:raise ValueError('PROTOCOL_CLOSED')
            if self.pending_bytes+size>self.max_bytes:
                self.error='PROTOCOL_BYTE_BUDGET';raise ValueError(self.error)
            self.sequence+=1;index=self.sequence
            self.pending[index]=self.clock();self.pending_bytes+=size
            try:self.queue.put_nowait((index,line,size))
            except queue.Full:
                del self.pending[index];self.pending_bytes-=size
                self.error='PROTOCOL_QUEUE_FULL';raise ValueError(self.error)

    def _write(self):
        while True:
            try:index,line,size=self.queue.get(timeout=.05)
            except queue.Empty:
                with self.lock:
                    if self.closed:return
                continue
            started=self.clock()
            try:
                if self.line_writer is None:self.writer(json.loads(line))
                else:self.line_writer(line)
            except Exception:
                with self.lock:self.error=self.error or 'PROTOCOL_WRITE_FAILED'
                return
            finally:self.queue.task_done()
            with self.lock:
                self.max_write_s=max(self.max_write_s,self.clock()-started)
                self.sent+=1;del self.pending[index];self.pending_bytes-=size

    def status(self):
        with self.lock:
            return {'queued_messages':len(self.pending),'queued_bytes':self.pending_bytes,
                    'sent_messages':self.sent,'max_write_s':self.max_write_s,
                    'delivery_state':'BUFFERING' if self.buffering else 'CURRENT',
                    'error':self.error,'sender_alive':self.thread.is_alive()}

    def close(self,timeout=.5):
        with self.lock:self.closed=True
        self.thread.join(timeout=timeout)
        return self.status()


class InputStream:
    def __init__(self, max_line=1024):
        self.max_line=max_line
        self.messages = queue.Queue(maxsize=8)
        self.failed = threading.Event()
        self.failure_reason='INPUT_EOF'
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            buffer=b''
            while True:
                # Unbuffered fd read avoids holding a Python BufferedReader lock
                # across interpreter shutdown while the peer keeps stdin open.
                block=os.read(sys.stdin.fileno(),1024)
                if not block:
                    self.failure_reason='INPUT_TRUNCATED' if buffer else 'INPUT_EOF'
                    break
                buffer+=block
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    if len(line)>self.max_line:raise ValueError('INPUT_SIZE')
                    self.messages.put_nowait(json.loads(line))
                if len(buffer)>self.max_line:raise ValueError('INPUT_SIZE')
        except queue.Full:self.failure_reason='INPUT_QUEUE_FULL'
        except json.JSONDecodeError:self.failure_reason='INPUT_INVALID_JSON'
        except ValueError as exc:self.failure_reason=str(exc)
        except Exception:self.failure_reason='INPUT_READ_FAILED'
        self.failed.set()

    def receive(self):
        try: return self.messages.get_nowait()
        except queue.Empty:
            if self.failed.is_set():raise ValueError(self.failure_reason)
            return None


def control(link, incoming, output, mode, gate=None, clock=time.monotonic, before_trial=lambda:None,
            record=lambda *_args, **_kwargs:None, prepare_trial=lambda *_args:None,
            safety=lambda:None):
    persistent=mode in {'control','control_scan'}
    gate = gate or InputGate(clock,continuous=persistent,persistent=persistent,recoverable=persistent)
    directions=MANUAL_DIRECTIONS if persistent else DIRECTIONS
    last_emit = -1.
    last_navigation = -1.
    last_preview = -1.
    preview_stamp = 0
    preview_fault = None
    first_deadline = clock()+2
    received = False
    armed_at = None
    last_output_s = None
    while True:
        try:gate.check()
        except MotionPaused as exc:
            # Stop/readback comes before recording. A UI deadline is not an SSH close.
            if link.enabled:link.release()
            armed_at=last_output_s=None;last_emit=-1.
            record('motion_paused',reason=str(exc),motion_generation=gate.generation)
        if persistent and link.enabled and link.reason=='command_timeout':
            link.release();gate.pause('LOCAL_OUTPUT_TIMEOUT')
            armed_at=last_output_s=None;last_emit=-1.
            record('motion_paused',reason='LOCAL_OUTPUT_TIMEOUT',motion_generation=gate.generation)
        safety()
        if clock()-last_preview >= .2 and hasattr(link,'scan_preview'):
            preview=link.scan_preview()
            fault=link.scan_display_fault() if hasattr(link,'scan_display_fault') else 'NONE' if preview is not None else 'NOT_RECEIVED'
            if fault!=preview_fault:
                record('scan_display_fault',reason=fault)
                preview_fault=fault
            if preview is not None and preview['source_stamp_ns']>preview_stamp:
                record('scan_preview',scan=preview)
                preview_stamp=preview['source_stamp_ns']
            last_preview=clock()
        if not received and clock() >= first_deadline: raise ValueError('NO_OPERATOR_INPUT')
        if clock()-last_emit >= .05:
            if getattr(link, 'rows', None): record('observation', sample=link.rows[-1], guard=link.reason)
            if clock()-last_navigation >= 1. and hasattr(link,'navigation_snapshot'):
                record('navigation', snapshot=link.navigation_snapshot())
                last_navigation=clock()
            output({'state': 'READY', 'challenge': gate.challenge(), 'mode': mode,
                    'motion_lease_policy':'fresh-intent-1.0' if gate.continuous else 'bounded-hold-1.0',
                    'session_policy':'until-stop-1.0' if gate.persistent else 'bounded-60s-1.0',
                    'manual_speed':{'linear_m_s':.05,'angular_rad_s':.30} if persistent else None,
                    'input_sequence':gate.sequence,
                    'motion_generation':gate.generation,'pause_reason':gate.pause_reason,
                    'guard': link.reason, 'voltage_v': float(link.sensor.battery)})
            last_emit = clock()
        packet = incoming.receive()
        if packet is not None:
            try: action, age = gate.accept(packet)
            except MotionPaused as exc:
                if link.enabled:link.release()
                armed_at=last_output_s=None;last_emit=-1.
                record('motion_paused',reason=str(exc),motion_generation=gate.generation)
                continue
            except ValueError as exc:
                if (persistent and gate.recoverable and not gate.active
                        and str(exc) in {'INPUT_EXPIRED','INPUT_CHALLENGE'}):
                    # An arm transition revokes its pre-arm challenges while
                    # torque may already be enabled. A delayed old frame is
                    # not a new movement lease and is not a transport failure.
                    # Confirm zero/OFF before metadata; preserve sensor/worker
                    # ownership, and require a wholly new post-arm input.
                    if link.enabled:link.release()
                    gate.pause(str(exc))
                    armed_at=last_output_s=None;last_emit=-1.
                    record('motion_paused',reason=str(exc),motion_generation=gate.generation)
                    continue
                # OFF confirmation can take longer than an input lease. Drop
                # expired in-flight frames only while outputs are disabled;
                # never replay them, and never excuse expiry during motion.
                if not link.enabled and not gate.active and str(exc) in {'INPUT_EXPIRED','INPUT_CHALLENGE'}:
                    last_emit=-1.
                    continue
                raise
            received = True
            record('accepted', sequence=packet['sequence'], action=action, source_age_s=age)
            if action in TERMINAL_STOPS:
                record('stop_requested',sequence=packet['sequence'],action=action)
                try:
                    status=('FORCE_STOPPED' if action=='force_stop' else
                        finish_segment(link,incoming,gate,last_output_s,.1,record=record,clock=clock))
                finally:link.halt()
                record('idle_confirmed',sequence=packet['sequence'])
                return {'status':status}
            if action in {'stop','close'}:
                record('release_requested' if action == 'stop' else 'close_requested', sequence=packet['sequence'])
                if action == 'stop': link.release()
                else: link.halt()
                record('idle_confirmed', sequence=packet['sequence'])
                if getattr(link, 'rows', None): record('observation', sample=link.rows[-1], guard=link.reason)
                if action == 'close': return {'status': 'OPERATOR_STOP'}
                if gate.persistent:gate.presence_at=clock()  # Bounded local idle readback just completed.
                armed_at = None
                last_output_s = None
                last_emit = -1.
                continue
            if mode in {'qualify','qualify_scan'}:
                if action == 'qualify':
                    if mode == 'qualify_scan':
                        gate.suspend_for_sensor_warmup()
                    trial_guard = prepare_trial(link, incoming, output, gate, clock)
                    if mode == 'qualify_scan' and (not gate.active or gate.last_action != 'watch'):
                        raise ValueError('FRESH_WATCH_REQUIRED_AFTER_SENSOR_WARMUP')
                    before_trial()
                    return qualify(link, incoming, output, gate, clock,
                                   safety=trial_guard or (lambda:None))
                if action != 'watch': raise ValueError('QUALIFICATION_ONLY')
            elif mode == 'scan':
                if action != 'watch' or link.enabled:raise ValueError('SCAN_ONLY_INPUT_REJECTED')
                gate.discard_idle_watch()
            elif action in DIRECTIONS:
                source_created=gate.source_created
                if not link.enabled:
                    # Enabling does NOT replay the input with a fresh timestamp.
                    # Require a subsequent post-arm challenge/input to actually publish.
                    if persistent:gate.suspend_for_arm()
                    link.enable()
                    record('armed', sequence=packet['sequence'])
                    armed_at = clock()
                    if persistent:gate.suspend_for_arm()
                    last_emit = -1.
                else:
                    total_age = clock()-source_created if source_created is not None else age
                    # An already-in-flight pre-arm challenge can arrive after
                    # enable. Consume it without output; never restamp it.
                    if armed_at is not None and source_created is not None and source_created > armed_at:
                        if total_age>=INPUT_TTL_S:
                            if persistent:
                                link.release();gate.pause('INPUT_DEADLINE_EXPIRED');armed_at=last_output_s=None
                                record('motion_paused',reason='INPUT_DEADLINE_EXPIRED',motion_generation=gate.generation)
                                continue
                            raise ValueError('INPUT_DEADLINE_EXPIRED')
                        try:link.publish(*directions[action], total_age)
                        except ValueError as exc:
                            if not persistent or str(exc) not in {'INPUT_DEADLINE_EXPIRED','COMMAND_SOURCE_AGE','SOURCE_EXPIRED_DURING_ENABLE'}:raise
                            link.release();gate.pause(str(exc));armed_at=last_output_s=None;last_emit=-1.
                            record('motion_paused',reason=str(exc),motion_generation=gate.generation)
                            continue
                        last_output_s=clock()
                        record('published', sequence=packet['sequence'], action=action,
                               linear_m_s=directions[action][0], angular_rad_s=directions[action][1], source_age_s=total_age)
            elif action == 'watch':
                if link.enabled:
                    if not persistent:raise ValueError('RELEASE_REQUIRES_STOP')
                    link.release();gate.pause('OPERATOR_STOP');armed_at=last_output_s=None;last_emit=-1.
                    record('motion_paused',reason='OPERATOR_STOP',motion_generation=gate.generation)
                    continue
                gate.discard_idle_watch()
            else: raise ValueError('UNSUPPORTED_CONTROL_ACTION')
        link.spin(.005)
        link.fresh()


def wait_for_post_arm_watch(link, incoming, output, gate, clock, *, safety=lambda:None):
    """No output from a pre-arm lease; require a new current-generation watch.

    The same configured input lifetime applies. Motor enable can consume that
    lifetime, so it is preparation, not a refreshed movement authorization.
    Stop and missing/stale input still abort before the first publication.
    """
    end = clock() + INPUT_TTL_S
    last_emit=-math.inf
    while clock() < end:
        safety()
        if clock()-last_emit>=.05:
            output({'state':'TESTING','challenge':gate.challenge(),'mode':'qualify_post_arm'})
            last_emit=clock()
        packet = incoming.receive()
        if packet is not None:
            try:
                action, _ = gate.accept(packet)
            except ValueError as exc:
                if packet.get('action') == 'watch' and str(exc) in {'INPUT_EXPIRED','INPUT_CHALLENGE'}:
                    continue
                raise
            if action != 'watch':raise ValueError('TRIAL_INTERRUPTED_BEFORE_PUBLICATION')
            gate.check();safety();return
        link.spin(.005);link.fresh()
    raise ValueError('FRESH_POST_ARM_INPUT_REQUIRED')


def qualify(link, incoming, output, gate, clock, *, safety=lambda:None, supervised_field_speed=None, supervised_stop_timing=None, post_arm_watch=False, diagnostic=lambda _:None):
    """Fixed 0.05m/s / 600ms expiry test; versioned supervised stop metrics."""
    if supervised_field_speed not in (None, .03):raise ValueError('QUALIFICATION_SPEED_NOT_REVIEWED')
    from stop_policy import field_stop_policy, assess_field_stop
    if supervised_stop_timing is not None and supervised_field_speed!=.03:
        raise ValueError('FIELD_STOP_TIMING_REQUIRES_SUPERVISED_SPEED')
    stop_policy=field_stop_policy(supervised_stop_timing) if supervised_stop_timing is not None else POLICY
    trial_speed = .05 if supervised_field_speed is None else .03
    origin = [link.sensor.left_encoder, link.sensor.right_encoder]
    if post_arm_watch:gate.suspend_for_arm()
    diagnostic('ENABLE_BEGIN');link.enable();diagnostic('ENABLE_END')
    if post_arm_watch:
        wait_for_post_arm_watch(link,incoming,output,gate,clock,safety=safety)
        diagnostic('POST_ARM_ACCEPTED')
    # New robot-local diagnostic commands, not re-stamped remote direction inputs.
    started = clock(); last_send = started; timeout_seen = None
    gate.hold_end = started+4
    last_emit = -1.
    timeout_encoders = None
    while clock()-started < 3.:
        diagnostic('LOOP_CHECK')
        gate.check()
        if clock()-last_emit >= .05:
            output({'state': 'TESTING', 'challenge': gate.challenge(), 'mode': 'qualify'})
            last_emit = clock()
        packet = incoming.receive()
        if packet is not None:
            action, _ = gate.accept(packet)
            if action=='force_stop':return {'status':'FORCE_STOPPED'}
            if action != 'watch': raise ValueError('TRIAL_INTERRUPTED')
        diagnostic('INPUT_PROCESSED')
        link.spin(.005);diagnostic('ROS_SPIN_END');link.fresh();safety();diagnostic('SAFETY_END')
        current = [link.sensor.left_encoder,link.sensor.right_encoder]
        dl, dr = [b-a for a,b in zip(origin,current)]
        if min(dl,dr)<-40 or max(dl,dr)>=1300 or abs(dl-dr)>=350: raise ValueError('TRIAL_ENCODER_BOUND')
        if not link.sensor.torque: raise ValueError('TRIAL_TORQUE_LOST')
        if clock()-started < .6:
            if clock()-last_send >= .05:
                diagnostic('PUBLISH_BEGIN');link.publish(trial_speed,0.,0.);last_send=clock();diagnostic('PUBLISH_END')
        elif timeout_seen is None:
            if link.reason == 'command_timeout':
                timeout_seen = clock()
                timeout_encoders = current
            elif clock()-last_send >= .7: raise ValueError('GUARD_TIMEOUT_NOT_OBSERVED')
        else:
            if link.reason != 'command_timeout': raise ValueError('STOP_NOT_LATCHED')
            if max(abs(a-b) for a,b in zip(current,timeout_encoders))*MM_PER_TICK > POLICY['wheel_travel_limit_mm']:
                raise ValueError('STOP_TRAVEL_EXCEEDED')
            if clock()-timeout_seen >= OBSERVE_S:
                assessment = (assess_field_stop(link.rows,timeout_seen,last_send,supervised_stop_timing)
                    if supervised_stop_timing is not None else assess_stop(link.rows, timeout_seen, last_send))
                # Wait only for a real bracketing sensor sample; never invent one.
                if (assessment.get('reason') == 'OBSERVATION_WINDOW_INCOMPLETE'
                        and clock()-timeout_seen < OBSERVE_S + stop_policy['max_sample_gap_s']):
                    continue
                detail = settling_details(link.rows, timeout_seen)
                passed = assessment['status']=='PASS' and min(dl,dr)>0
                return {'status': 'STOP_POLICY_PASS' if passed else 'STOP_POLICY_FAIL',
                        'stop_assessment': assessment,
                        'reason': '' if passed else assessment['reason'] if min(dl,dr)>0 else 'FORWARD_NOT_OBSERVED',
                        'stop_diagnostics': {**detail, 'forward_observed': min(dl,dr)>0},
                        'timeout_seen_s':timeout_seen,'last_send_s':last_send,
                        'required_stable_ms':200,'window_ms':500,'band_ticks':2}
    raise ValueError('TRIAL_DEADLINE')


def wait_for_same_window_inputs(link, incoming, output, gate, clock, driver):
    """No motor enable until the owned scan driver and passive odom are arriving."""
    output({'state': 'PREPARING', 'mode': 'qualify_scan',
            'reason': 'SENSOR_WARMUP_WHEELS_DISABLED'})
    driver.start()
    end = clock() + 8.
    gate.hold_end = min(gate.started + 60., end + 1.)
    last_emit = -1.
    while clock() < end:
        gate.check()
        if not driver.running():
            raise ValueError('ISOLATED_SCAN_DRIVER_EARLY_EXIT')
        if clock() - last_emit >= .05:
            output({'state': 'TESTING', 'challenge': gate.challenge(),
                    'mode': 'qualify_scan', 'input_sequence': gate.sequence})
            last_emit = clock()
        packet = incoming.receive()
        if packet is not None:
            try:
                action, _ = gate.accept(packet)
            except ValueError as exc:
                if (isinstance(packet, dict) and packet.get('action') == 'watch'
                        and str(exc) in {'INPUT_EXPIRED', 'INPUT_CHALLENGE'}):
                    # A pre-warmup challenge cannot be refreshed or replayed.
                    continue
                raise
            if action in {'force_stop','close','stop','finish_stop'}:
                raise ValueError('TRIAL_CANCELLED_BEFORE_MOTOR_ENABLE')
            if action != 'watch':
                raise ValueError('TRIAL_PREP_UNEXPECTED_INPUT')
            # A watch received before the scan is ready cannot arm a later
            # motor command. Discard its input lease while wheels are OFF,
            # then require a new challenge/watch after sensor readiness.
            counts = link.received_counts
            if counts['scan'] < 3 or counts['odom'] < 3:
                gate.discard_warmup_watch()
        link.spin(.005)
        link.fresh()
        counts = link.received_counts
        if gate.active:
            # ROS callbacks can take longer than a lease. Do not turn a
            # transient delay with torque OFF into a motion authorization.
            if clock() >= gate.deadline:
                gate.discard_warmup_watch()
                continue
            if counts['scan'] >= 3 and counts['odom'] >= 3:
                link.fresh_scan()
                gate.check()
                link.require_scan_fresh = True
                def during_trial():
                    if not driver.running():
                        raise ValueError('ISOLATED_SCAN_DRIVER_EARLY_EXIT')
                    link.fresh_scan()
                return during_trial
            gate.discard_warmup_watch()
    raise ValueError('SAME_WINDOW_SCAN_OR_ODOM_NOT_READY')


def prepare_manual_scan(link, output, driver, clock=time.monotonic, *, scan_only=False, incoming=None):
    """One owned scan driver and ROS link, with wheels disabled during warmup.

    This establishes scan availability, not measured obstacle geometry or an
    autonomous collision-clearance claim. Manual control remains supervised.
    """
    output({'state': 'PREPARING', 'mode': 'scan' if scan_only else 'control_scan',
            'reason': 'SENSOR_WARMUP_WHEELS_DISABLED'})
    driver.start()
    deadline = clock() + 8.
    while clock() < deadline:
        if incoming is not None:
            packet=incoming.receive()
            if packet is not None and packet.get('action') in {'close','force_stop','finish_stop','stop'}:
                raise ValueError('SCAN_CANCELLED_BEFORE_READY')
            if packet is not None and packet.get('action')!='watch':
                raise ValueError('SCAN_PREPARATION_INPUT_REJECTED')
        if not driver.running():
            raise ValueError('ISOLATED_SCAN_DRIVER_EARLY_EXIT')
        link.spin(.01)
        link.fresh()
        if link.received_counts['scan'] >= 3 and (scan_only or link.received_counts['odom'] >= 3):
            link.fresh_scan()
            link.require_scan_fresh = True
            return
    raise ValueError('MANUAL_SCAN_OR_ODOM_NOT_READY')


def main(mode):
    from runtime import HOME, ownership, verify_release, read_board, disarm_board, write_json
    from robot_health import parse_board_snapshot
    from stationary import require_idle, cleanup_signals, stop_child, commands
    from teleop_ros import RosLink
    from robot_journal import RobotJournal
    if mode not in {'control','control_scan','scan','qualify','qualify_scan','lidar','off','mission','localize'}: return 2
    release = Path(__file__).resolve().parent
    manifest = verify_release(release)
    if not {'teleop_worker.py','teleop_contract.py','teleop_ros.py','teleop.sh','lidar_capture.py','stop_policy.py','local_navigation.py','ros_observations.py','navigation_binding.py','robot_journal.py','observation_stream.py'}.issubset(manifest['files']):
        raise ValueError('MANUAL_SOURCES_NOT_IN_MANIFEST')
    if mode in {'qualify_scan','control_scan','scan','mission','localize'} and 'isolated_ros_scan.py' not in manifest['files']:
        raise ValueError('ISOLATED_SCAN_SOURCE_NOT_IN_MANIFEST')
    profile=json.loads((release/'profile.json').read_text())
    if profile.get('manual_control_policy')!='explicit_session_and_same_boot_release_stop_receipt':
        raise ValueError('MANUAL_CONTROL_POLICY_MISSING')
    if (HOME/'current').resolve(strict=True) != release: raise ValueError('RELEASE_CHANGED')
    boot = boot_id()
    mission_request=None
    mission_stream=None
    if mode in {'mission','localize'}:
        from mission_runtime import POLICY as MISSION_POLICY, receive_request
        # Shipped profile does NOT opt in. Reject before opening any device.
        if profile.get('autonomous_control_policy')!=MISSION_POLICY:
            raise ValueError('AUTONOMOUS_PROFILE_NOT_REVIEWED')
        if not {'mission_runtime.py','mission_contract.py'}<=set(manifest['files']):raise ValueError('MISSION_SOURCE_NOT_IN_MANIFEST')
        mission_stream=InputStream(max_line=16384)
        mission_request=receive_request(release,manifest,boot,mission_stream,emit)
        if (mode=='localize')!=(mission_request.get('adaptive_scope',{}).get('phase')=='IDLE_LOCALIZATION_ONLY'):
            raise ValueError('IDLE_LOCALIZATION_ENTRY_SCOPE_MISMATCH')
        if 'adaptive_scope' in mission_request:
            from observed_runtime import reviewed_observed_release
            reviewed_observed_release(release,manifest,mission_request['calibration_sha256'])
        if (HOME/'state'/('mission-consumed-'+mission_request['mission_id'])).exists():
            raise ValueError('MISSION_ALREADY_CONSUMED')
    receipt_path = HOME/'state/manual-qualification.json'
    binding = {'boot_id':boot,'release_id':manifest['source_id'],'schema':'manual-stop-2.0',
               'policy_sha256':POLICY_SHA256}
    out = HOME/'reports'/('manual-'+uuid.uuid4().hex)
    out.mkdir(parents=True)
    report = {**binding,'mode':mode,'status':'STARTED','physical_validation':'ACTUAL_ROBOT',
              'cleanup_errors':[],
              'cleanup_confirmed':False, 'robot_session_id':out.name,
              'observation_limits':{'chassis_pose':'NOT_MEASURED','odom':'PASSIVE_IF_PUBLISHED',
                                    'scan':'PASSIVE_IF_PUBLISHED_TF_UNVERIFIED'}}
    if mode in {'qualify_scan','control_scan','scan','mission','localize'}:
        from coin_driver_identity import description
        report['expected_driver_identity'] = description()
    if mode in {'control_scan','scan'}:
        report['observation_limits']['scan'] = 'OWNED_ACTIVE_ROS_SCAN_TF_UNVERIFIED'
    write_json(out/'report.json',report)
    if mission_request and 'full_reference' in mission_request:
        write_json(out/'survey-reference.json',mission_request['full_reference'])
    base = link = scan_driver = None
    observed_factory = None
    def interrupt(*_): raise KeyboardInterrupt('SESSION_INTERRUPTED')
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM): signal.signal(sig,interrupt)
    signal.alarm(110)
    persistent=mode in {'control','control_scan'}
    with ownership() as lease, (out/'base.log').open('ab') as log:
        journal=RobotJournal(out/'session.jsonl',buffered=persistent)
        protocol=ProtocolOutbox(emit,buffered=persistent)
        output=protocol.send if protocol is not None else emit
        event_index=0
        def record(kind, **data):
            nonlocal event_index
            event_index+=1
            if event_index>(131072 if persistent else 4096): raise ValueError('SESSION_EVENT_BUDGET')
            event={'schema':'robot-session-1.1' if persistent else 'robot-session-1.0','robot_session_id':out.name,'event_index':event_index,
                   'clock_domain':'robot_monotonic','t':time.monotonic(),'kind':kind,'data':data}
            journal.append(event)
            output({'state':'SESSION_EVENT','event':event})
        def snapshot(name):
            path = out/(name+'.log')
            read_board(release,path,lease.fileno())
            return parse_board_snapshot(path.read_text())
        try:
            # Approval to this entry explicitly includes OFF maintenance first.
            disarm_board(release,out/'off.log',lease.fileno(),operator_confirmed=True)
            report['before'] = snapshot('before'); require_idle(report['before'])
            if mode in {'control','control_scan','mission','localize'}:
                try: qualification = json.loads(receipt_path.read_text())
                except (OSError,ValueError):
                    raise ValueError('PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE')
                if any(qualification.get(k)!=v for k,v in binding.items()) or qualification.get('status')!='QUALIFIED':
                    raise ValueError('PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE')
            if mode == 'off': report['status']='IDLE_CONFIRMED'
            elif mode == 'lidar':
                from lidar_capture import acquire, SerialChannel
                stream = InputStream()
                stop = threading.Event()
                def watch_cancel():
                    while not stop.wait(.02):
                        try:
                            packet=stream.receive()
                            if packet is not None and packet.get('action') in {'close','stop','force_stop','finish_stop'}:
                                stop.set()
                        except Exception: stop.set()
                threading.Thread(target=watch_cancel,daemon=True).start()
                emit({'state':'LIDAR_RUNNING'})
                data,chunks=acquire(SerialChannel(),report,cancel=stop.is_set)
                stop.set()
                (out/'raw.bin').write_bytes(data); write_json(out/'chunks.json',chunks)
                report['status']='LIDAR_DATA_QUIET' if (report.get('data_quiet_after_stop') is True
                    and report.get('port_restored') is True and not report.get('acquisition_error')) else 'LIDAR_STOP_UNCONFIRMED'
            else:
                marker=HOME/'state'/('manual-trial-'+boot+'-'+manifest['source_id'])
                if mode in {'qualify','qualify_scan'} and marker.exists():
                    raise ValueError('TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED')
                base_command,_=commands(release,out)
                base=subprocess.Popen(base_command,stdout=log,stderr=log,start_new_session=True,pass_fds=(lease.fileno(),))
                link=RosLink(base,raw_path=out/'ros-messages.raw')
                link.bind_observations({'project_id':mission_request['adaptive_scope']['project_id'] if mission_request and 'adaptive_scope' in mission_request else 'default',
                    'session_id':out.name,'boot_id':boot,'release_id':manifest['source_id'],
                    'source_revision':manifest['source_id'],'origin':'live_ros'})
                link.preflight()
                link.persistent_manual=persistent
                link.manual_speed_profile=mode in {'control','control_scan','qualify','qualify_scan'}
                if persistent:
                    report['session_policy']='until-stop-1.0'
                    report['manual_speed']={'linear_m_s':.05,'angular_rad_s':.30}
                    report['telemetry_scope']='ROLLING_TAIL_10000_EXACT_RAW_AND_JOURNAL_RETAINED'
                def consume_trial():
                    # Consume immediately before motor enable, not while merely
                    # preparing. Failed physical attempts cannot be auto-retried.
                    marker.touch(exist_ok=False)
                record('session_started', mode=mode, boot_id=boot, release_id=manifest['source_id'])
                if mode in {'mission','localize'}:
                    from mission_runtime import run_mission
                    from isolated_ros_scan import IsolatedRosScan
                    scan_driver = IsolatedRosScan(out/'driver.log')
                    # Wheel-disabled preparation drains stale watch packets.
                    # run_mission then issues a new challenge before enabling.
                    prepare_manual_scan(link,output,scan_driver,incoming=mission_stream)
                    observed_factory = None
                    if 'adaptive_scope' in mission_request:
                        from observed_runtime import RobotObservedFactory
                        observed_factory = RobotObservedFactory(link,mission_request,output=output,clock=time.monotonic)
                        observed_factory.handoff_sink=lambda value:write_json(out/'goal-handoff.json',value)
                        observed_factory.prepare()
                    def consume_mission():
                        (HOME/'state'/('mission-consumed-'+mission_request['mission_id'])).touch(exist_ok=False)
                    def mission_safety():
                        protocol.check();journal.check()
                        if not scan_driver.running():raise ValueError('ISOLATED_SCAN_DRIVER_EARLY_EXIT')
                        link.fresh_scan()
                    def mission_record(kind,**data):
                        record(kind,**data)
                        if kind=='mission_decision' and observed_factory:observed_factory.record_visual()
                    if mode=='localize':
                        from mission_runtime import run_idle_localization
                        report['motion_authorized']=False
                        report['operation_scope']='IDLE_LOCALIZATION_ONLY'
                        report.update(run_idle_localization(link,mission_stream,output,mission_request,
                            observed_factory,safety=mission_safety,record=mission_record,consume=consume_mission))
                        if mission_request['adaptive_scope'].get('phase')=='REVIEWED_GOAL_EXECUTION':
                            report.update(operation_scope='REVIEWED_GOAL_EXECUTION',
                                goal_review_id=observed_factory.approved_preview['plan_id'])
                    else:
                        report.update(run_mission(link,mission_stream,output,mission_request,record=mission_record,
                            consume=consume_mission,transport_safety=mission_safety,
                            mission_factory=observed_factory))
                    if observed_factory:report['adaptive_visual']=observed_factory.visual()
                else:
                    incoming=InputStream()
                    if mode in {'qualify_scan','control_scan','scan','mission','localize'}:
                        from isolated_ros_scan import IsolatedRosScan
                        scan_driver = IsolatedRosScan(out/'driver.log')
                    if mode in {'control_scan','scan'}:
                        prepare_manual_scan(link,output,scan_driver,scan_only=mode=='scan',incoming=incoming)
                    def scan_running():
                        if scan_driver is not None and not scan_driver.running():
                            raise ValueError('ISOLATED_SCAN_DRIVER_EARLY_EXIT')
                        link.fresh_scan()
                    def live_safety():
                        if protocol is not None:protocol.check()
                        journal.check()
                        # A stalled loop still interrupts/cleans up; not a total-session timer.
                        if persistent:signal.alarm(10)
                        if persistent and time.monotonic()-live_safety.checked_at>=1.:
                            live_safety.checked_at=time.monotonic()
                            import shutil
                            if shutil.disk_usage(out).free<128*1024*1024:raise ValueError('RECORDING_DISK_RESERVE')
                            for path in (out/'base.log',out/'driver.log'):
                                if path.exists() and path.stat().st_size>=8*1024*1024:raise ValueError('RECORDING_LOG_BUDGET')
                        if mode in {'control_scan','scan'}:scan_running()
                    live_safety.checked_at=-1.
                    prepare = (lambda current, incoming, output, gate, clock:
                               wait_for_same_window_inputs(current,incoming,output,gate,clock,scan_driver)) if mode=='qualify_scan' else (lambda *_:None)
                    report.update(control(link,incoming,output,mode,before_trial=consume_trial,
                                          record=record,prepare_trial=prepare,
                                          safety=live_safety))
                if report.get('reason'):
                    report['first_failure']={'stage':'operation','code':report['reason']}
        except (Exception,KeyboardInterrupt) as exc:
            report.update(status='FAILED',reason=str(exc)[:160],error_type=type(exc).__name__)
            report['first_failure']={'stage':'operation','code':str(exc)[:160],'error_type':type(exc).__name__}
            from cleanup_notes import checked_notes
            report['cleanup_errors'].extend(checked_notes(getattr(exc,'mission_cleanup_errors',[])))
        finally:
            signal.alarm(0)
            with cleanup_signals():
                if link is not None:
                    try:report['common_observation_health']=link.observation_health()
                    except Exception as exc:
                        report['observation_health_error']=type(exc).__name__
                    try: link.halt()
                    except Exception as exc:
                        report['ros_stop_confirmed']=False
                        report['cleanup_errors'].append({'stage':'ros_stop','code':'ROS_STOP_FAILED','error_type':type(exc).__name__})
                    else: report['ros_stop_confirmed']=True
                    if mode in {'qualify_scan','control_scan','scan','mission'}:
                        report['received_counts'] = dict(link.received_counts)
                        report['moving_command_ns'] = list(link.moving_command_ns)
                if scan_driver is not None:
                    report['scan_driver_cleanup'] = scan_driver.stop()
                    stop = report['scan_driver_cleanup'].get('sensor_stop', {})
                    report['sensor_cleanup_confirmed'] = (
                        scan_driver.child is None or (scan_driver.child.poll() is not None
                        and stop.get('write_complete') is True
                        and stop.get('quiet_after_1s') is True
                        and stop.get('port_restored') is True))
                    if not report['sensor_cleanup_confirmed']:
                        report['status'] = 'SCAN_DRIVER_STOP_UNCONFIRMED'
                        report['operator_cutoff_required'] = True
                reaped=True
                report['operation_status']=report['status']
                report['cleanup_stage']='base_exit'
                if base is not None:
                    try: report['base_exit']=stop_child(base)
                    except Exception as exc:
                        reaped=False
                        report['cleanup_error']=str(exc)[:160]
                        report['cleanup_errors'].append({'stage':'base_exit','code':'BASE_EXIT_FAILED','error_type':type(exc).__name__})
                if reaped:
                    try:
                        report['cleanup_stage']='independent_torque_off'
                        disarm_board(release,out/'final-off.log',lease.fileno(),operator_confirmed=True)
                        report['cleanup_stage']='independent_idle_read'
                        report['after']=snapshot('after'); require_idle(report['after'])
                        report['cleanup_confirmed']=True
                        report['cleanup_stage']='confirmed'
                    except Exception as exc:
                        report['cleanup_error']=str(exc)[:160]
                        report['cleanup_errors'].append({'stage':report['cleanup_stage'],'code':'FINAL_IDLE_UNCONFIRMED','error_type':type(exc).__name__})
                # Safety cleanup precedes every disk export/close. A failing
                # or blocked archive must never postpone independent OFF/read.
                if link is not None:
                    try:
                        write_json(out/'telemetry.json',link.rows)
                    except Exception as exc:
                        report['status']='FAILED'
                        report['telemetry_write_error']=type(exc).__name__
                        report['cleanup_errors'].append({'stage':'telemetry_export','code':'TELEMETRY_WRITE_FAILED','error_type':type(exc).__name__})
                    report['telemetry_tail']=link.rows[-100:]
                    try:
                        report['raw_ros']=link.close()
                        if report['raw_ros'] is not None and not report['raw_ros']['complete']:
                            report['status']='FAILED'
                            report['reason']='RAW_RECORDING_INCOMPLETE'
                            report['cleanup_errors'].append({'stage':'raw_close','code':report['reason']})
                    except Exception as exc:
                        report['raw_ros']={'complete':False,'error_type':type(exc).__name__}
                        report['status']='FAILED'
                        report['reason']='RAW_RECORDING_CLOSE_FAILED'
                        report['cleanup_errors'].append({'stage':'raw_close','code':report['reason'],'error_type':type(exc).__name__})
                if not report['cleanup_confirmed']: report['status']='FINAL_IDLE_UNCONFIRMED'
                if report['status'] in {'OPERATOR_STOP','MISSION_ARRIVED','MISSION_CANCELLED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED'} and report.get('ros_stop_confirmed') is not True:
                    report['status']='FINAL_ROS_STOP_UNCONFIRMED'
                journal_status=journal.close()
                report['local_journal_write']=journal_status
                if journal_status['error'] is not None or journal_status['saved']!=journal_status['accepted']:
                    report['status']='FAILED'
                    report['reason']=journal_status['error'] or 'SESSION_JOURNAL_INCOMPLETE'
                if report.get('reason') and 'first_failure' not in report:
                    report['first_failure']={'stage':'recording_or_cleanup','code':report['reason']}
                if mode in {'qualify','qualify_scan'} and report['status']=='STOP_POLICY_PASS':
                    if report.get('ros_stop_confirmed') is True and report.get('stop_assessment',{}).get('status')=='PASS':
                        write_json(receipt_path,{**binding,'status':'QUALIFIED','report_directory':str(out)})
                        report['status']='QUALIFIED'
                    else:
                        report['status']='FINAL_ROS_STOP_UNCONFIRMED'
                if mode=='mission' and observed_factory is not None:
                    # Large map/fit data never competes with fresh input or
                    # scan processing. All independent OFF/read/driver cleanup
                    # above has already been attempted before disk export.
                    try:
                        descriptor=observed_factory.save_evidence(out)
                        report['mission_evidence_status']='SAVED' if descriptor else 'NOT_COLLECTED'
                        if descriptor:
                            report['mission_evidence']=descriptor
                            report['mission_id']=observed_factory.request['mission_id']
                            report['mission_request_sha256']=observed_factory.request['request_sha256']
                    except Exception as exc:
                        code=str(exc)
                        if not __import__('re').fullmatch('[A-Z0-9_]{1,120}',code):code='MISSION_EVIDENCE_SAVE_FAILED'
                        report['mission_evidence_status']='FAILED'
                        report['mission_evidence_error']=code
                        report['mission_evidence_error_type']=type(exc).__name__
                if protocol is not None:
                    report['protocol_delivery']={**protocol.status(),'basis':'PRE_FINISHED_ENQUEUE_SNAPSHOT'}
                write_json(out/'report.json',report)
                try:output({'state':'FINISHED','report':report})
                except (ValueError,OSError):
                    if protocol is None:raise
                finally:
                    if protocol is not None:
                        protocol.close()
    return 0 if report['cleanup_confirmed'] and report['status'] in {'QUALIFIED','OPERATOR_STOP','IDLE_CONFIRMED','LIDAR_DATA_QUIET','MISSION_ARRIVED','MISSION_CANCELLED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED'} else 2


if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit(2)
    try: raise SystemExit(main(sys.argv[1]))
    except Exception as exc:
        code=str(exc)
        if not __import__('re').fullmatch('[A-Z0-9_]{1,160}',code):code=type(exc).__name__
        emit({'state':'REJECTED','reason':code,'error_type':type(exc).__name__,'stage':'PRE_DEVICE_ADMISSION'}); raise SystemExit(2)
