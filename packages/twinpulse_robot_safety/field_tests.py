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
import queue
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

SCHEMA = 'supervised-field-test-1.0'
CASES = ('stationary', 'bootstrap_stop', 'forward', 'backward', 'left', 'right',
         'full_turn', 'proximity', 'stall', 'presence_gap', 'soak')
CAP_V, CAP_W, TTL = .03, .20, 900.


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def checked_config(value, *, robot_id=None, binding_sha256=None):
    bounds = dict(footprint_radius_m=(.08, .6), sensor_x_m=(-.6, .6), sensor_y_m=(-.6, .6),
                  sensor_yaw_rad=(-math.pi, math.pi), wheel_metres_per_tick=(.000001, .01),
                  wheel_separation_m=(.08, .8))
    keys = {'schema', 'robot_id', 'binding_sha256', 'provenance', 'axes_reviewed', 'angle_sign', *bounds}
    if not isinstance(value, dict) or set(value) != keys or value['schema'] != SCHEMA:
        raise ValueError('FIELD_CONFIG_SHAPE')
    if (not isinstance(value['robot_id'], str) or not re.fullmatch('[a-f0-9]{32}', value['robot_id'])
            or not isinstance(value['binding_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['binding_sha256'])
            or robot_id is not None and value['robot_id'] != robot_id
            or binding_sha256 is not None and value['binding_sha256'] != binding_sha256):
        raise ValueError('FIELD_CONFIG_ROBOT_BINDING')
    if (value['provenance'] not in {'reference', 'operator_reviewed', 'operator_measured'}
            or value['axes_reviewed'] is not True or type(value['angle_sign']) is not int
            or value['angle_sign'] not in {-1, 1}):
        raise ValueError('FIELD_AXES_AND_PROVENANCE_REVIEW_REQUIRED')
    for key, (low, high) in bounds.items():
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not low <= value[key] <= high:
            raise ValueError('FIELD_VALUE_OUTSIDE_RANGE_' + key.upper())
    return deepcopy(value)


def frame_points(frame, config, now):
    """Validate full original ring; unknown returns are not free-space proof."""
    if not frame or not frame.get('complete') or frame.get('interval_fallback'):
        raise ValueError('FIELD_COMPLETE_NATIVE_RING_REQUIRED')
    t = frame['timing']
    if not 0 <= now-t['receipt_end_s'] <= .35 or not 0 <= t['receipt_end_s']-t['receipt_start_s'] <= .35:
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
        d = b['distance_m']; a = math.radians(b['angle_deg'])*config['angle_sign']+config['sensor_yaw_rad']
        if type(d) not in (int, float) or not math.isfinite(d) or d < 0:raise ValueError('FIELD_NATIVE_DISTANCE_INVALID')
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
    candidates = []
    for seed in (0., -.12, .12):
        x = y = 0.; yaw = seed; pairs = []
        for _ in range(7):
            if clock() > deadline:raise ValueError('TRACKING_COMPUTE_DEADLINE')
            c, s = math.cos(yaw), math.sin(yaw)
            transformed = [(c*a-s*b+x, s*a+c*b+y) for a, b in q]
            pairs = []
            for a in transformed:
                b = min(p, key=lambda b: (a[0]-b[0])**2+(a[1]-b[1])**2)
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
    return dict(delta=list(best[1:]), residual_m=best[0], accuracy='UNQUALIFIED', independent=True)


class NativeTracker:
    """One immutable latest result, bounded worker; publish never runs ICP."""
    def __init__(self, native, config, clock=time.monotonic):
        self.native, self.config, self.clock = native, config, clock
        self.cancel = threading.Event(); self.lock = threading.Lock(); self.epoch = uuid4().hex
        self.result = dict(status='WAITING', epoch=self.epoch, pose=None, independent=True, accuracy='UNQUALIFIED')
        self.thread = threading.Thread(target=self._run, daemon=True, name='NativeRelativeTracking')
        self.thread.start()

    def snapshot(self):
        with self.lock:r = deepcopy(self.result)
        if r.get('sample_s') is not None and self.clock()-r['sample_s'] > .6:
            r.update(status='STALE', reason='TRACKING_SAMPLE_STALE')
        return r

    def close(self):self.cancel.set(); self.thread.join(timeout=1.)

    def _run(self):
        previous = None; sequence = None; stream_id=None; pose = [0., 0., 0.]
        while not self.cancel.wait(.1):
            frame = self.native.latest_frame()
            if not frame:continue
            stream=frame.get('stream_id',getattr(self.native,'stream_id',None))
            if stream!=stream_id or sequence is not None and frame['frame_sequence']<sequence:
                previous=None;sequence=None;stream_id=stream;self.epoch=uuid4().hex;pose=[0.,0.,0.]
            if frame['frame_sequence'] == sequence:continue
            sequence = frame['frame_sequence']
            try:
                pts = frame_points(frame, self.config, self.clock())
                if previous is None:
                    previous = (frame, pts)
                    continue
                prior, p = previous
                dt = frame['timing']['receipt_end_s']-prior['timing']['receipt_end_s']
                if not 0 < dt <= .6:raise ValueError('TRACKING_FRAME_GAP')
                fit = register_pair(p, pts, deadline=self.clock()+.08, clock=self.clock)
                dx, dy, da = fit['delta']
                if math.hypot(dx,dy) > .12*dt+.02 or abs(da) > .6*dt+.02:
                    raise ValueError('TRACKING_IMPLAUSIBLE_JUMP')
                c, s = math.cos(pose[2]), math.sin(pose[2])
                pose = [pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy, pose[2]+da]
                value = dict(status='ESTIMATED', epoch=self.epoch, pose=pose, sample_s=frame['timing']['receipt_end_s'],
                    raw_sha256=frame['raw_sha256'], previous_raw_sha256=prior['raw_sha256'], **fit)
                previous = (frame, pts)
            except (ValueError, KeyError, TypeError) as exc:
                # Never accumulate across a failed match or silently wheel-fallback.
                previous = None; self.epoch = uuid4().hex; pose = [0.,0.,0.]
                value = dict(status='INCONCLUSIVE', reason=str(exc), epoch=self.epoch, pose=None,
                             independent=True, accuracy='UNQUALIFIED', sample_s=self.clock())
            with self.lock:self.result = value


class FieldEvidenceWriter:
    """Fixed members, bounded queue; no disk work on the motor owner thread."""
    MEMBERS={'field-config.json','field-trials.json','field-stop.json','field-tracking.json'}
    def __init__(self,directory,clock=time.monotonic):
        self.directory=Path(directory);self.clock=clock;self.queue=queue.Queue(maxsize=32)
        self.lock=threading.Lock();self.pending={};self.error=None;self.closed=False
        self.sequence=0;self.reserved=0
        self.thread=threading.Thread(target=self._run,daemon=True,name='FieldEvidenceWriter');self.thread.start()

    def check(self):
        with self.lock:
            if self.pending and self.clock()-min(self.pending.values())>.5:self.error=self.error or 'FIELD_EVIDENCE_STALLED'
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

    def _run(self):
        import os
        try:
            while not self.closed or not self.queue.empty():
                try:index,name,raw=self.queue.get(timeout=.05)
                except queue.Empty:continue
                target=self.directory/name;temporary=self.directory/(name+'.pending')
                if target.is_symlink() or temporary.is_symlink():raise ValueError('FIELD_EVIDENCE_SYMLINK')
                with temporary.open('wb') as stream:
                    if stream.write(raw)!=len(raw):raise OSError('SHORT_WRITE')
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,target)
                with self.lock:del self.pending[index]
        except Exception:
            with self.lock:self.error=self.error or 'FIELD_EVIDENCE_WRITE_FAILED'

    def close(self):
        self.closed=True;self.thread.join(timeout=2.)
        return dict(complete=not self.thread.is_alive() and not self.error and not self.pending,
                    writer_reaped=not self.thread.is_alive(),error=self.error,pending=len(self.pending))


class FieldGuard:
    def __init__(self, config, native, link, admitted, clock=time.monotonic):
        self.config, self.native, self.link, self.admitted, self.clock = config, native, link, admitted, clock
        self.last_result = None; self.progress = {}; self.last_frame = None; self.last_end = None
        self.bootstrap = False; self.started = None; self.samples = []
        self.tracker=None;self.body_samples=[]

    def reset(self):self.samples = []; self.started = None;self.body_samples=[]

    def __call__(self, v, w, source_created):
        if not (v or w):return
        now = self.clock()
        if not self.admitted():raise ValueError('FIELD_SESSION_NOT_ARMED_OR_EXPIRED')
        if abs(v) > CAP_V+1e-9 or abs(w) > CAP_W+1e-9:raise ValueError('FIELD_POLICY_SPEED_CAP')
        if source_created is None or not 0 <= now-source_created <= .25:raise ValueError('FIELD_ORIGINAL_INPUT_EXPIRED')
        frame = self.native.latest_frame(); pts = frame_points(frame, self.config, now)
        seq = frame['frame_sequence']; end = frame['timing']['receipt_end_s']
        if self.last_frame is not None and (seq < self.last_frame or seq != self.last_frame and end <= self.last_end):
            raise ValueError('FIELD_NATIVE_REPLAY_OR_CLOCK')
        self.last_frame, self.last_end = seq, end
        relevant = []
        for x, y in pts:
            if w or v > 0 and x >= 0 and abs(y) <= self.config['footprint_radius_m']+.1 or v < 0 and x <= 0 and abs(y) <= self.config['footprint_radius_m']+.1:
                relevant.append((x,y))
        # Require returns throughout the swept direction, not just one clear ray.
        sectors = {int((math.atan2(y,x) % math.tau)/(math.tau/24)) for x,y in pts}
        needed = set(range(24)) if w else ({22,23,0,1} if v > 0 else {10,11,12,13})
        for beam in frame['beams']:
            a=math.radians(beam['angle_deg'])*self.config['angle_sign']+self.config['sensor_yaw_rad']
            sector=int((a % math.tau)/(math.tau/24))
            if sector in needed and (beam['distance_m']<=0 or beam['quality']<=0):
                raise ValueError('FIELD_DIRECTION_COVERAGE_UNKNOWN')
        if not needed.issubset(sectors):raise ValueError('FIELD_DIRECTION_COVERAGE_UNKNOWN')
        angles=sorted((math.radians(b['angle_deg'])*self.config['angle_sign']+self.config['sensor_yaw_rad'])%math.tau for b in frame['beams'])
        for a,b in zip(angles,angles[1:]+[angles[0]+math.tau]):
            if int(((a+b)/2 % math.tau)/(math.tau/24)) in needed and b-a>math.radians(5):
                raise ValueError('FIELD_DIRECTION_COVERAGE_GAP')
        gap = min((math.hypot(x,y)-self.config['footprint_radius_m'] for x,y in relevant), default=0.)
        self.last_result = dict(scope='RECEIPT_BASED_SUPERVISED_PROXIMITY_NOT_STOP_DISTANCE',
            estimated_radial_clearance_m=gap, threshold_m=.1, raw_sha256=frame['raw_sha256'],
            nodes_sha256=frame['nodes_sha256'], frame_sequence=seq, receipt_age_s=now-end,
            acquisition_timing='UNQUALIFIED', config_sha256=digest(self.config))
        if gap <= .1:raise ValueError('FIELD_PROXIMITY_10CM')
        if self.started is None:self.started=now
        if self.bootstrap and (v != CAP_V or w != 0. or now-self.started > .65):
            raise ValueError('FIELD_BOOTSTRAP_OUTPUT_BOUND')
        sensor = self.link.sensor
        if not 0 <= now-self.link.sensor_t <= .2:raise ValueError('FIELD_WHEEL_TELEMETRY_STALE')
        enc = (sensor.left_encoder, sensor.right_encoder)
        commanded=(v-w*self.config['wheel_separation_m']/2,v+w*self.config['wheel_separation_m']/2)
        scale=self.config['wheel_metres_per_tick']
        sample_s=self.link.sensor_t
        if self.samples and sample_s!=self.samples[-1][0]:
            previous=self.samples[-1];dt=sample_s-previous[0]
            if not 0<dt<=.2:raise ValueError('FIELD_WHEEL_CLOCK_OR_GAP')
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
        if tracking and tracking['status']=='ESTIMATED':
            if self.body_samples and self.body_samples[0]['epoch']!=tracking['epoch']:self.body_samples=[]
            if not self.body_samples or self.body_samples[-1]['sample_s']!=tracking['sample_s']:
                self.body_samples.append(tracking)
            while len(self.body_samples)>2 and self.body_samples[1]['sample_s']<=now-1.:self.body_samples.pop(0)
            first_body=self.body_samples[0]
            if tracking['sample_s']-first_body['sample_s']>=1.:
                progress=math.dist(tracking['pose'][:2],first_body['pose'][:2]) if v else abs(tracking['pose'][2]-first_body['pose'][2])
                self.progress.update(body_progress='ESTIMATED_NOT_QUALIFIED',body_delta=progress,tracking_epoch=tracking['epoch'])
                if progress<(.002 if v else .01):raise ValueError('FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP')
        else:
            self.body_samples=[];self.progress.update(body_progress='INCONCLUSIVE',tracking_reason=(tracking or {}).get('reason'))
            if getattr(self,'require_body',False):raise ValueError('FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP')
        if not 0 <= self.clock()-end <= .35:raise ValueError('FIELD_GUARD_COMPUTE_EXPIRED')
