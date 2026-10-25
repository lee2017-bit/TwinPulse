# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Explicit supervised observations, NOT a measured protective drive profile.

Pure validation/registration and a bounded background tracker. No device import,
wheel seed, fabricated beam timestamps, shell or motor action at import time.
"""
from copy import deepcopy
import hashlib
import json
import math
import multiprocessing
import queue
import re
import threading
import time
from pathlib import Path
from uuid import uuid4
from control_timing import NATIVE_RECEIPT_S,ICP_COMPUTE_S,TRACKING_RESULT_S,INPUT_TTL_S
from field_config import SCHEMA,checked_config,digest
from twinpulse_core.robot_timing_profile import values_of

CASES = ('stationary', 'bootstrap_stop', 'forward', 'backward', 'left', 'right',
         'full_turn', 'proximity', 'stall', 'presence_gap', 'soak')
CAP_V, CAP_W, TTL = .03, .20, 900.
# Explicit engineering setting approved by the operator on 2026-10-24.
# This does not qualify missing returns as measured clear space.
FIELD_MAXIMUM_RETURN_GAP_DEG = 10.


def frame_points(frame, config, now, *, timing_values=None):
    """Validate full original ring; unknown returns are not free-space proof."""
    if not frame or not frame.get('complete') or frame.get('interval_fallback'):
        raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
    return _validated_points(frame, config, now, timing_values=timing_values)


def control_observation(native, config, now):
    """Same-stream last COMPLETE ring within its original 350ms receipt limit.

    A newer unknown-byte ring is retained as incomplete and used ONLY to veto
    motion, never to prove clearance or to qualify ICP/strict motion. This is
    an explicit supervised policy, not a claim to have decoded unknown bytes.
    """
    frame,previous=native.control_frames() if hasattr(native,'control_frames') else (native.latest_frame(),None)
    if not frame or frame.get('interval_fallback'):
        raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
    timing=getattr(native,'timing_values',None)
    if frame.get('complete'):return frame,frame_points(frame,config,now,timing_values=timing),None,None
    else:
        q=frame.get('quality') or {};span=frame.get('source_byte_span') or {}
        gaps=q.get('unframed_spans') or []
        if (q.get('complete_start') is not True
                or q.get('checksum_invalid_packets')!=0 or q.get('interval_fallback_packets')!=0
                or q.get('unknown_boundary_policy')!='GAP_BEFORE_VALID_RING_START_BELONGS_TO_CLOSING_RING'
                or not gaps):raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
        cursor=span.get('start');count=0
        for gap in gaps:
            start,end,length=gap.get('start'),gap.get('end'),gap.get('length')
            if (type(start) is not int or type(end) is not int or type(length) is not int
                    or start<cursor or end<=start or length!=end-start or gap.get('classification')!='UNKNOWN'
                    or gap.get('framing_errors')!=0
                    or not re.fullmatch('[a-f0-9]{64}',str(gap.get('raw_sha256','')))):
                raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
            cursor=end;count+=length
        if count!=q.get('unframed_bytes'):raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
        # Current partial returns cannot extend previous-ring freshness. Any
        # newer observed hazard/invalid return in the swept cone still vetoes.
        partial_points=_validated_points(frame,config,now,timing_values=timing)
        if (not previous or not frame.get('stream_id') or previous.get('stream_id')!=frame['stream_id']
                or previous['frame_sequence']>=frame['frame_sequence']
                or previous['timing']['receipt_end_s']>frame['timing']['receipt_end_s']):
            raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
        return previous,frame_points(previous,config,now,timing_values=timing),frame,partial_points


def tracking_observation(native,config,now,*,frame=None):
    """ICP uses complete rings ONLY; a validated closing-gap ring is skipped.

    Skipping never renews a pose timestamp, supplies fake points, or removes the
    output guard's newer-hazard veto. The unchanged tracking age/gap limits
    still stop a route if a new complete ring does not arrive in time.
    """
    frame=native.latest_frame() if frame is None else frame
    if frame and frame.get('complete'):return frame,frame_points(frame,config,now,timing_values=getattr(native,'timing_values',None))
    control_observation(native,config,now) # Reject every other incomplete shape.
    return None


def _validated_points(frame, config, now, *, timing_values=None):
    t = frame['timing']
    limit=values_of(timing_values)['native_receipt_ms']/1000
    if not 0 <= now-t['receipt_end_s'] <= limit or not 0 <= t['receipt_end_s']-t['receipt_start_s'] <= limit:
        raise ValueError('FIELD_NATIVE_RECEIPT_STALE_OR_BACKLOG')
    span = frame['source_byte_span']
    if not 0 <= span['start'] < span['end'] or not re.fullmatch('[a-f0-9]{64}', frame['raw_sha256']):
        raise ValueError('FIELD_NATIVE_SOURCE_INVALID')
    beams = frame['beams']
    if not 60 <= len(beams) <= 4096 or any(not b.get('valid_packet') for b in beams):
        raise ValueError('FIELD_NATIVE_NODES_INVALID')
    if any(a['source_byte_cursor'] > b['source_byte_cursor'] for a, b in zip(beams, beams[1:])):
        raise ValueError('FIELD_NATIVE_BYTE_ORDER')
    points = []
    for b in beams:
        d = b['distance_m'];angle=b['angle_deg'];quality=b['quality']
        if type(d) not in (int, float) or not math.isfinite(d) or d < 0:raise ValueError('FIELD_NATIVE_DISTANCE_INVALID')
        if (type(angle) not in (int,float) or not math.isfinite(angle) or not 0<=angle<=360
                or type(quality) not in (int,float) or not math.isfinite(quality) or quality<0):
            raise ValueError('FIELD_NATIVE_NODES_INVALID')
        a = math.radians(angle)*config['angle_sign']+config['sensor_yaw_rad']
        if d > 0 and b['quality'] > 0:
            points.append((config['sensor_x_m']+d*math.cos(a), config['sensor_y_m']+d*math.sin(a)))
    return points


def register_pair(before, after, *, deadline, clock=time.monotonic):
    """Bounded point-to-point ICP, after -> before; no wheel-derived input.

    An engineering heuristic with explicit ambiguity and UNQUALIFIED accuracy,
    not an error bound for the strict measured progress monitor.
    """
    if len(before) < 40 or len(after) < 40:raise ValueError('TRACKING_INSUFFICIENT_RETURNS')
    p = before[::max(1, len(before)//100)][:120]
    q = after[::max(1, len(after)//100)][:120]
    mx, my = [sum(v[k] for v in p)/len(p) for k in (0, 1)]
    xx = sum((v[0]-mx)**2 for v in p)/len(p); yy = sum((v[1]-my)**2 for v in p)/len(p)
    xy = sum((v[0]-mx)*(v[1]-my) for v in p)/len(p)
    if xx*yy-xy*xy < .002:raise ValueError('TRACKING_DEGENERATE_GEOMETRY')
    # Exact same .15m correspondence cutoff, indexed spatially instead of
    # scanning every reference point for every point/iteration/seed under GIL.
    cells={}
    for index,b in enumerate(p):cells.setdefault((math.floor(b[0]/.15),math.floor(b[1]/.15)),[]).append((index,b))
    candidates = []
    for seed in (0., -.12, .12):
        x = y = 0.; yaw = seed; pairs = []
        for _ in range(7):
            if clock() > deadline:raise ValueError('TRACKING_COMPUTE_DEADLINE')
            c, s = math.cos(yaw), math.sin(yaw)
            transformed = [(c*a-s*b+x, s*a+c*b+y) for a, b in q]
            pairs = []
            for a in transformed:
                ix,iy=math.floor(a[0]/.15),math.floor(a[1]/.15)
                candidates_near=[(index,b) for x in (ix-1,ix,ix+1) for y in (iy-1,iy,iy+1) for index,b in cells.get((x,y),())]
                if not candidates_near:continue
                _,b=min(candidates_near,key=lambda row:((a[0]-row[1][0])**2+(a[1]-row[1][1])**2,row[0]))
                error = (a[0]-b[0])**2+(a[1]-b[1])**2
                if error < .15**2:pairs.append((a, b, error))
            pairs.sort(key=lambda row: row[2]); pairs = pairs[:max(30, int(len(pairs)*.8))]
            if len(pairs) < 30:break
            ax, ay = [sum(a[k] for a, _, _ in pairs)/len(pairs) for k in (0, 1)]
            bx, by = [sum(b[k] for _, b, _ in pairs)/len(pairs) for k in (0, 1)]
            angle = math.atan2(sum((a[0]-ax)*(b[1]-by)-(a[1]-ay)*(b[0]-bx) for a,b,_ in pairs),
                               sum((a[0]-ax)*(b[0]-bx)+(a[1]-ay)*(b[1]-by) for a,b,_ in pairs))
            c, s = math.cos(angle), math.sin(angle)
            tx, ty = bx-c*ax+s*ay, by-s*ax-c*ay
            x, y, yaw = c*x-s*y+tx, s*x+c*y+ty, yaw+angle
        if len(pairs)<30:continue
        score = math.sqrt(sum(row[2] for row in pairs)/len(pairs))
        candidates.append((score, x, y, yaw))
    if not candidates:raise ValueError('TRACKING_OVERLAP_INSUFFICIENT')
    candidates.sort()
    best = candidates[0]
    if best[0] > .06:raise ValueError('TRACKING_RESIDUAL_HIGH')
    for other in candidates[1:]:
        if other[0] <= best[0]+.004 and (math.hypot(other[1]-best[1], other[2]-best[2]) > .025 or abs(other[3]-best[3]) > .04):
            raise ValueError('TRACKING_AMBIGUOUS')
    if clock() > deadline:raise ValueError('TRACKING_COMPUTE_DEADLINE')
    return dict(delta=list(best[1:]), residual_m=best[0], accuracy='UNQUALIFIED', independent=True)


def _registration_worker(connection):
    """Fixed local computation only; no ROS, devices or incoming executable code."""
    try:
        connection.send(dict(ready=True))
        while True:
            job=connection.recv()
            if job is None:return
            job_id,before,after=job[:3]
            budget=job[3] if len(job)==4 else ICP_COMPUTE_S
            if type(budget) not in (float,int) or not .02<=budget<=.5:raise ValueError('TRACKING_BUDGET_INVALID')
            started=time.monotonic()
            try:
                if len(before)>4096 or len(after)>4096:raise ValueError('TRACKING_POINT_BOUND')
                value=register_pair(before,after,deadline=started+budget)
                result=dict(ok=True,fit=value)
            except (ValueError,KeyError,TypeError,OverflowError) as exc:
                result=dict(ok=False,reason=str(exc))
            connection.send(dict(job_id=job_id,compute_started_s=started,
                compute_ended_s=time.monotonic(),**result))
    except (EOFError,BrokenPipeError,OSError):pass
    finally:connection.close()


class NativeTracker:
    """Latest-only tracking; ICP has a separate process/GIL and one in-flight job."""
    def __init__(self, native, config, clock=time.monotonic):
        self.native, self.config, self.clock = native, config, clock
        self.timing_values=values_of(getattr(native,'timing_values',None))
        self.cancel = threading.Event(); self.lock = threading.Lock(); self.epoch = uuid4().hex
        self.result = dict(status='WAITING', epoch=self.epoch, pose=None, independent=True, accuracy='UNQUALIFIED')
        ctx=multiprocessing.get_context('spawn')
        self.connection,child=ctx.Pipe()
        self.process=ctx.Process(target=_registration_worker,args=(child,),daemon=True,name='TwinPulseICP')
        self.process.start();child.close()
        self.job_sequence=0;self.compute_timing={};self.worker_failed=None;self.worker_ready=False
        self.thread = threading.Thread(target=self._run, daemon=True, name='NativeRelativeTracking')
        self.thread.start()

    def snapshot(self):
        with self.lock:r = deepcopy(self.result)
        current=self.native.latest_frame()
        if r.get('status')=='ESTIMATED' and (not current or
            current.get('stream_id',getattr(self.native,'stream_id',None))!=r.get('stream_id') or
            current['frame_sequence']<r.get('frame_sequence',0)):
            r.update(status='STALE',reason='TRACKING_NATIVE_IDENTITY_CHANGED',pose=None)
        if r.get('sample_s') is not None and self.clock()-r['sample_s'] > getattr(self,'timing_values',values_of())['tracking_result_ms']/1000:
            r.update(status='STALE', reason='TRACKING_SAMPLE_STALE')
        return r

    def close(self):
        self.cancel.set();self.thread.join(timeout=1.)
        if not self.thread.is_alive():
            try:self.connection.send(None)
            except (BrokenPipeError,OSError):pass
        self.process.join(timeout=1.)
        if self.process.is_alive():self.process.terminate();self.process.join(timeout=1.)
        self.connection.close()
        return dict(worker_reaped=not self.process.is_alive(),thread_reaped=not self.thread.is_alive())

    def _fit(self,before,after):
        if self.worker_failed:raise ValueError(self.worker_failed)
        if not self.process.is_alive():raise ValueError('TRACKING_PROCESS_EXITED')
        startup=time.monotonic()
        while not self.worker_ready:
            if self.cancel.is_set():raise ValueError('TRACKING_CANCELLED')
            if self.connection.poll(.01):
                self.worker_ready=self.connection.recv()==dict(ready=True)
                if not self.worker_ready:raise ValueError('TRACKING_PROCESS_HANDSHAKE')
            elif time.monotonic()-startup>10. or not self.process.is_alive():
                self.worker_failed='TRACKING_PROCESS_START_TIMEOUT';raise ValueError(self.worker_failed)
        self.job_sequence+=1;job=self.job_sequence
        self.compute_timing=dict(job_id=job,stage='DISPATCHED')
        self.connection.send((job,before,after,getattr(self,'timing_values',values_of())['icp_compute_ms']/1000));sent=time.monotonic()
        while not self.cancel.is_set():
            if self.connection.poll(.01):
                value=self.connection.recv()
                if value.get('job_id')!=job:raise ValueError('TRACKING_RESULT_JOB_MISMATCH')
                self.compute_timing={k:value[k] for k in ('job_id','compute_started_s','compute_ended_s')}
                self.compute_timing['stage']='COMPLETED' if value['ok'] else 'COMPUTE_FAILED'
                self.compute_timing['compute_elapsed_s']=value['compute_ended_s']-value['compute_started_s']
                self.compute_timing['delivery_elapsed_s']=time.monotonic()-sent
                if not value['ok']:raise ValueError(value['reason'])
                return value['fit']
            # This bounds process delivery; it does not extend the .08s compute
            # budget or the original frame/pose freshness checks.
            if time.monotonic()-sent>getattr(self,'timing_values',values_of())['tracking_delivery_ms']/1000 or not self.process.is_alive():
                self.compute_timing.update(stage='DELIVERY_FAILED',delivery_elapsed_s=time.monotonic()-sent)
                self.worker_failed='TRACKING_PROCESS_UNRESPONSIVE'
                raise ValueError(self.worker_failed)
        raise ValueError('TRACKING_CANCELLED')

    def _run(self):
        previous = None; sequence = None; stream_id=None; pose = [0., 0., 0.]
        while not self.cancel.wait(.1):
            frame = self.native.latest_frame()
            if not frame:continue
            stream=frame.get('stream_id',getattr(self.native,'stream_id',None))
            if stream!=stream_id or sequence is not None and frame['frame_sequence']<sequence:
                previous=None;sequence=None;stream_id=stream;self.epoch=uuid4().hex;pose=[0.,0.,0.]
                with self.lock:
                    self.result=dict(status='WAITING',reason='TRACKING_NEW_NATIVE_IDENTITY',epoch=self.epoch,
                        stream_id=stream,frame_sequence=frame['frame_sequence'],pose=None,independent=True,accuracy='UNQUALIFIED')
            if frame['frame_sequence'] == sequence:continue
            sequence = frame['frame_sequence']
            self.compute_timing=dict(stage='FRAME_VALIDATION')
            try:
                observed=tracking_observation(self.native,self.config,self.clock(),frame=frame)
                if observed is None:
                    # Original pose/sample/epoch stay untouched across one
                    # bounded omitted ring. Incomplete bytes remain raw evidence.
                    continue
                frame,pts=observed
                if previous is None:
                    previous = (frame, pts)
                    continue
                prior, p = previous
                dt = frame['timing']['receipt_end_s']-prior['timing']['receipt_end_s']
                if not 0 < dt <= self.timing_values['tracking_result_ms']/1000:raise ValueError('TRACKING_FRAME_GAP')
                fit = self._fit(p, pts)
                current=self.native.latest_frame()
                if self.cancel.is_set():return
                if not current or current.get('stream_id',getattr(self.native,'stream_id',None))!=stream:
                    raise ValueError('TRACKING_STREAM_CHANGED')
                if current['frame_sequence']<sequence:raise ValueError('TRACKING_FRAME_SEQUENCE_ROLLED_BACK')
                if self.clock()-frame['timing']['receipt_end_s']>self.timing_values['tracking_result_ms']/1000:raise ValueError('TRACKING_SAMPLE_STALE')
                dx, dy, da = fit['delta']
                if math.hypot(dx,dy) > .12*dt+.02 or abs(da) > .6*dt+.02:
                    raise ValueError('TRACKING_IMPLAUSIBLE_JUMP')
                c, s = math.cos(pose[2]), math.sin(pose[2])
                pose = [pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy, pose[2]+da]
                value = dict(status='ESTIMATED', epoch=self.epoch, pose=pose, sample_s=frame['timing']['receipt_end_s'],
                    raw_sha256=frame['raw_sha256'], previous_raw_sha256=prior['raw_sha256'],
                    frame_sequence=sequence,stream_id=stream,compute_timing=dict(self.compute_timing),**fit)
                previous = (frame, pts)
            except (ValueError, KeyError, TypeError, EOFError, OSError) as exc:
                # Never accumulate across a failed match or silently wheel-fallback.
                previous = None; self.epoch = uuid4().hex; pose = [0.,0.,0.]
                value = dict(status='INCONCLUSIVE', reason=str(exc), epoch=self.epoch, pose=None,
                             independent=True, accuracy='UNQUALIFIED',sample_s=frame['timing']['receipt_end_s'],
                             raw_sha256=frame['raw_sha256'],frame_sequence=sequence,stream_id=stream,
                             compute_timing=dict(self.compute_timing))
            if self.cancel.is_set():return
            with self.lock:self.result = value


class FieldEvidenceWriter:
    """Fixed members, bounded queue; no disk work on the motor owner thread."""
    MEMBERS={'field-config.json','field-trials.json','field-stop.json','field-tracking.json'}
    # Disk durability is not a motor/sensor deadline. The real no-motion
    # 2026-10-24 connection (6b428c29...) observed FSYNC 1.058 s plus ACK_FSYNC
    # 8.805 s; the former 2 s storage budget latched an otherwise completed
    # write. Report slow storage as buffering, not a fabricated durable ACK.
    # Results/stop authority still wait for both exact-byte durable ACKs.
    # This bounded storage budget is not a measured safety limit. Motor input,
    # sensor age and local output watchdog deadlines are deliberately unchanged.
    BUFFERING_S=.5
    COMMIT_DEADLINE_S=30.
    def __init__(self,directory,clock=time.monotonic):
        self.directory=Path(directory);self.clock=clock;self.queue=queue.Queue(maxsize=32)
        self.lock=threading.Lock();self.pending={};self.error=None;self.closed=False
        self.sequence=0;self.reserved=0;self.committed={};self.writer_id=uuid4().hex
        self.phase='IDLE';self.phase_started=clock();self.phase_max={};self.ledger_created=False
        self.thread=threading.Thread(target=self._run,daemon=True,name='FieldEvidenceWriter');self.thread.start()

    def check(self):
        with self.lock:
            if self.pending and self.clock()-min(self.pending.values())>self.COMMIT_DEADLINE_S:self.error=self.error or 'FIELD_EVIDENCE_STALLED'
            error=self.error
        if error:raise ValueError(error)

    def append(self,name,value):
        if name not in self.MEMBERS:raise ValueError('FIELD_EVIDENCE_MEMBER')
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        self.check()
        with self.lock:
            if self.closed or len(raw)>128*1024 or self.reserved+len(raw)>8*1024*1024:
                self.error='FIELD_EVIDENCE_CAPACITY';raise ValueError(self.error)
            self.sequence+=1;index=self.sequence;self.pending[index]=self.clock()
            try:self.queue.put_nowait((index,name,raw))
            except queue.Full:
                del self.pending[index];self.error='FIELD_EVIDENCE_QUEUE_FULL';raise ValueError(self.error)
            self.reserved+=len(raw)
        return dict(writer_id=self.writer_id,write_id=index,name=name,sha256=hashlib.sha256(raw).hexdigest())

    def receipt(self, token):
        with self.lock:
            if self.error:raise ValueError(self.error)
            value=self.committed.get(token['write_id'])
            if value is not None:
                if any(value.get(k)!=token[k] for k in ('writer_id','write_id','name','sha256')):
                    raise ValueError('FIELD_EVIDENCE_ACK_IDENTITY')
                return dict(value)
            if token['write_id'] not in self.pending:raise ValueError('FIELD_EVIDENCE_ACK_MISSING')
        return None

    def status(self):
        with self.lock:
            age=max(0.,self.clock()-min(self.pending.values())) if self.pending else 0.
            return dict(writer_id=self.writer_id,last_write_id=self.sequence,error=self.error,pending=len(self.pending),phase=self.phase,
                phase_elapsed_s=max(0.,self.clock()-self.phase_started),phase_max_s=dict(self.phase_max),
                oldest_pending_s=age,buffering=age>=self.BUFFERING_S,
                commit_deadline_s=self.COMMIT_DEADLINE_S)

    def _phase(self,name):
        with self.lock:
            now=self.clock();self.phase_max[self.phase]=max(self.phase_max.get(self.phase,0.),now-self.phase_started)
            self.phase=name;self.phase_started=now

    def _run(self):
        import os
        try:
            while not self.closed or not self.queue.empty():
                try:index,name,raw=self.queue.get(timeout=.05)
                except queue.Empty:continue
                target=self.directory/name;temporary=self.directory/(name+'.pending')
                if target.is_symlink() or temporary.is_symlink():raise ValueError('FIELD_EVIDENCE_SYMLINK')
                self._phase('OPEN')
                with temporary.open('wb') as stream:
                    self._phase('WRITE')
                    if stream.write(raw)!=len(raw):raise OSError('SHORT_WRITE')
                    self._phase('FLUSH');stream.flush()
                    self._phase('FSYNC');os.fsync(stream.fileno())
                self._phase('REPLACE')
                os.replace(temporary,target)
                acknowledgement=dict(writer_id=self.writer_id,write_id=index,name=name,
                    sha256=hashlib.sha256(raw).hexdigest(),state='COMMITTED',data_replaced_s=self.clock())
                # Separate append-only ACKs avoid recursively rewriting the
                # trial's own persistence marker. Resolve only with a complete
                # writer receipt, never by existence of a partial ledger alone.
                ledger=self.directory/'field-commits.jsonl'
                if ledger.is_symlink():raise ValueError('FIELD_EVIDENCE_SYMLINK')
                self._phase('ACK_APPEND')
                with ledger.open('ab' if self.ledger_created else 'xb') as stream:
                    self.ledger_created=True
                    encoded=(json.dumps(acknowledgement,sort_keys=True)+'\n').encode()
                    if stream.write(encoded)!=len(encoded):raise OSError('SHORT_ACK_WRITE')
                    self._phase('ACK_FLUSH');stream.flush()
                    self._phase('ACK_FSYNC');os.fsync(stream.fileno())
                self._phase('IDLE')
                with self.lock:
                    if self.clock()-self.pending[index]>self.COMMIT_DEADLINE_S:self.error=self.error or 'FIELD_EVIDENCE_STALLED'
                    acknowledgement['ack_observed_s']=self.clock()
                    self.committed[index]=acknowledgement
                    del self.pending[index]
                    # Owner polls each cycle; old unreferenced tracking ACKs need
                    # not grow forever. An expired ACK is never assumed success.
                    while len(self.committed)>256:self.committed.pop(next(iter(self.committed)))
        except Exception:
            with self.lock:self.error=self.error or 'FIELD_EVIDENCE_WRITE_FAILED'

    def close(self):
        self.closed=True;self.thread.join(timeout=self.COMMIT_DEADLINE_S+.1)
        return dict(self.status(),complete=not self.thread.is_alive() and not self.error and not self.pending,
                    writer_reaped=not self.thread.is_alive())


class FieldGuard:
    def __init__(self, config, native, link, admitted, clock=time.monotonic):
        self.config, self.native, self.link, self.admitted, self.clock = config, native, link, admitted, clock
        self.timing_values=values_of(getattr(link,'timing_values',None))
        self.last_result = None; self.progress = {}; self.last_frame = None; self.last_end = None
        self.bootstrap = False; self.started = None; self.samples = []
        self.tracker=None;self.body_samples=[]

    def reset(self):self.samples = []; self.started = None;self.body_samples=[]

    def __call__(self, v, w, source_created):
        if not (v or w):return
        now = self.clock()
        if not self.admitted():raise ValueError('FIELD_SESSION_NOT_ARMED_OR_EXPIRED')
        if abs(v) > CAP_V+1e-9 or abs(w) > CAP_W+1e-9:raise ValueError('FIELD_POLICY_SPEED_CAP')
        if source_created is None or not 0 <= now-source_created < self.timing_values['input_ttl_ms']/1000:raise ValueError('FIELD_ORIGINAL_INPUT_EXPIRED')
        frame,partial=self._range_check(v,w,now)
        end=frame['timing']['receipt_end_s']
        self._progress_check(v,w,now)
        if hasattr(self.native,'control_frames'):
            current,_=self.native.control_frames()
            if not current or current.get('stream_id')!=frame.get('stream_id'):
                raise ValueError('FIELD_NATIVE_STREAM_CHANGED')
            if current is not (partial or frame):
                # Do not read a newer hazard and then discard it. One bounded
                # full recheck uses original clocks and all direction tests.
                frame,_=self._range_check(v,w,self.clock())
                end=frame['timing']['receipt_end_s']
        if not 0<=self.clock()-source_created<self.timing_values['input_ttl_ms']/1000:raise ValueError('FIELD_ORIGINAL_INPUT_EXPIRED')
        if not 0<=self.clock()-end<=self.timing_values['native_receipt_ms']/1000:raise ValueError('FIELD_GUARD_COMPUTE_EXPIRED')

    def _range_check(self,v,w,now):
        frame,pts,partial,partial_points = control_observation(self.native, self.config, now)
        seq = frame['frame_sequence']; end = frame['timing']['receipt_end_s']
        if self.last_frame is not None and (seq < self.last_frame or seq != self.last_frame and end <= self.last_end):
            raise ValueError('FIELD_NATIVE_REPLAY_OR_CLOCK')
        self.last_frame, self.last_end = seq, end
        relevant = []
        for x, y in pts+(partial_points or []):
            if w or v > 0 and x >= 0 and abs(y) <= self.config['footprint_radius_m']+.1 or v < 0 and x <= 0 and abs(y) <= self.config['footprint_radius_m']+.1:
                relevant.append((x,y))
        # Only positive, valid returns cover an angle. A no-return is never
        # free space, but does not erase surrounding valid samples. Enforce the
        # approved maximum using VALID returns, not raw beam slots.
        needed = set(range(24)) if w else ({22,23,0,1} if v > 0 else {10,11,12,13})
        for returns in [pts]+([partial_points] if partial is not None else []):
            angles=sorted(math.atan2(y,x)%math.tau for x,y in returns)
            sectors={int(a/(math.tau/24)) for a in angles}
            if not needed.issubset(sectors):raise ValueError('FIELD_DIRECTION_COVERAGE_UNKNOWN')
            for a,b in zip(angles,angles[1:]+[angles[0]+math.tau]):
                if b-a<=math.radians(FIELD_MAXIMUM_RETURN_GAP_DEG)+1e-12:continue
                # Include gaps intersecting a cone even if midpoint is outside.
                intersects=any(max(a,sector*math.tau/24+turn)<min(b,(sector+1)*math.tau/24+turn)-1e-12
                               for sector in needed for turn in (0.,math.tau))
                if intersects:raise ValueError('FIELD_DIRECTION_COVERAGE_GAP')
        gap = min((math.hypot(x,y)-self.config['footprint_radius_m'] for x,y in relevant), default=0.)
        self.last_result = dict(scope='RECEIPT_BASED_SUPERVISED_PROXIMITY_NOT_STOP_DISTANCE',
            estimated_radial_clearance_m=gap, threshold_m=.1, raw_sha256=frame['raw_sha256'],
            nodes_sha256=frame['nodes_sha256'], frame_sequence=seq, receipt_age_s=now-end,
            raw_ring_complete=bool(frame['complete']),
            latest_raw_ring_complete=bool((partial or frame)['complete']),
            latest_raw_frame_sequence=(partial or frame)['frame_sequence'],
            latest_raw_sha256=(partial or frame)['raw_sha256'],
            latest_unknown_bytes=((partial or frame).get('quality') or {}).get('unframed_bytes',0),
            latest_receipt_age_s=now-(partial or frame)['timing']['receipt_end_s'],
            valid_return_count=len(pts),latest_valid_return_count=len(partial_points) if partial is not None else len(pts),
            maximum_return_gap_deg=FIELD_MAXIMUM_RETURN_GAP_DEG,
            coverage_policy='POSITIVE_VALID_RETURNS_MAXIMUM_GAP_10_DEG_NOT_ZERO_AS_FREE_SPACE',
            observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
            acquisition_timing='UNQUALIFIED', config_sha256=digest(self.config))
        if gap <= .1:raise ValueError('FIELD_PROXIMITY_10CM')
        return frame,partial

    def _progress_check(self,v,w,now):
        if self.started is None:
            # A new drive window: keys from the previous command must not
            # survive into this one. Final reports read progress before reset.
            self.started=now;self.progress={}
        if self.bootstrap and (v != CAP_V or w != 0. or now-self.started > .65):
            raise ValueError('FIELD_BOOTSTRAP_OUTPUT_BOUND')
        sensor = self.link.sensor
        if not 0 <= now-self.link.sensor_t <= self.timing_values['sensor_receipt_ms']/1000:raise ValueError('FIELD_WHEEL_TELEMETRY_STALE')
        enc = (sensor.left_encoder, sensor.right_encoder)
        commanded=(v-w*self.config['wheel_separation_m']/2,v+w*self.config['wheel_separation_m']/2)
        scale=self.config['wheel_metres_per_tick']
        sample_s=self.link.sensor_t
        if self.samples and sample_s!=self.samples[-1][0]:
            previous=self.samples[-1];dt=sample_s-previous[0]
            if not 0<dt<=self.timing_values['wheel_interval_ms']/1000:raise ValueError('FIELD_WHEEL_CLOCK_OR_GAP')
            for current,prior,requested in zip(enc,previous[1],commanded):
                delta=(current-prior)*scale
                if delta*math.copysign(1,requested)<-2*scale:raise ValueError('FIELD_WHEEL_REVERSE_TO_COMMAND')
                if abs(delta)>2*(CAP_V+CAP_W*self.config['wheel_separation_m']/2)*dt+4*scale:
                    raise ValueError('FIELD_WHEEL_IMPLAUSIBLE_JUMP')
        if not self.samples or sample_s!=self.samples[-1][0]:self.samples.append((sample_s,enc))
        while len(self.samples)>2 and self.samples[1][0] <= now-1.:self.samples.pop(0)
        if len(self.samples)>100:raise ValueError('FIELD_PROGRESS_SAMPLE_CAPACITY')
        first = self.samples[0]
        if now-first[0] >= 1.:
            distances = [(a-b)*scale*math.copysign(1,requested) for a,b,requested in zip(enc,first[1],commanded)]
            if min(distances) < .001:raise ValueError('FIELD_WHEEL_STALL_OBSERVED')
            self.progress = dict(wheel_progress='MOVING', body_progress='UNQUALIFIED', wheel_delta_m=distances)
        tracking=self.tracker.snapshot() if self.tracker else None
        if tracking and tracking['status']=='ESTIMATED' and tracking['sample_s']<self.started:
            # Estimated before this output window began (robot still at rest):
            # it cannot measure progress of this command. Not evidence either way,
            # but a required body check may not wait for one indefinitely.
            self.progress.update(body_progress='AWAITING_IN_WINDOW_SAMPLE')
            if getattr(self,'require_body',False) and now-self.started>self.timing_values['tracking_result_ms']/1000+1.:
                raise ValueError('FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP')
        elif tracking and tracking['status']=='ESTIMATED':
            if self.body_samples and self.body_samples[0]['epoch']!=tracking['epoch']:self.body_samples=[]
            if not self.body_samples or self.body_samples[-1]['sample_s']!=tracking['sample_s']:
                self.body_samples.append(tracking)
            while len(self.body_samples)>2 and self.body_samples[1]['sample_s']<=now-1.:self.body_samples.pop(0)
            first_body=self.body_samples[0]
            if tracking['sample_s']-first_body['sample_s']>=1.:
                progress=math.dist(tracking['pose'][:2],first_body['pose'][:2]) if v else abs(tracking['pose'][2]-first_body['pose'][2])
                self.progress.update(body_progress='ESTIMATED_NOT_QUALIFIED',body_delta=progress,tracking_epoch=tracking['epoch'])
                if progress<(.002 if v else .01):
                    # User decision 2026-10-25 (explicitly_unverified_supervised for
                    # supervised finite commands): the relative tracker followed
                    # ~25% of a 0.58 m odom move in the living room, so a low
                    # estimate is recorded as unverified rather than stopping.
                    # Commands that require body evidence (routes, stall trials)
                    # still stop; wheel stall/proximity/Stop/timeouts are unchanged.
                    self.progress.update(body_progress='UNVERIFIED_LOW_TRACKER_PROGRESS_SUPERVISED')
                    if getattr(self,'require_body',False):raise ValueError('FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP')
        else:
            self.body_samples=[];self.progress.update(body_progress='INCONCLUSIVE',tracking_reason=(tracking or {}).get('reason'))
            if getattr(self,'require_body',False):raise ValueError('FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP')
