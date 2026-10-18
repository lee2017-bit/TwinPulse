# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Common causal ROS evidence input for live and recorded adapters.

This evidence channel is separate from qualified navigation inputs. Geometry
accepted here is not clearance, calibrated timing, a pose, or motion authority.
"""
from collections import Counter, deque
import copy
import math
import re


TOPICS = {'odom', 'scan', '/tf', '/tf_static'}
UNVERIFIED_TIMING = 'DECLARED_HEADER_UNVERIFIED_ACQUISITION'


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def checked_context(value):
    keys = {'project_id', 'session_id', 'boot_id', 'release_id', 'source_revision', 'origin'}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('OBSERVATION_CONTEXT_SHAPE')
    if value['origin'] not in {'live_ros', 'recorded_ros'}:
        raise ValueError('OBSERVATION_ORIGIN')
    for key in keys - {'origin'}:
        if not isinstance(value[key], str) or not re.fullmatch('[A-Za-z0-9_.-]{1,128}', value[key]):
            raise ValueError('OBSERVATION_CONTEXT_VALUE')
    return dict(value)


def scan_quality(value):
    """Keep original spacing, terminal gaps and missing rays; never fill them."""
    keys = ('angle_min', 'angle_max', 'angle_increment', 'time_increment',
            'scan_time', 'range_min', 'range_max')
    if any(not finite(value.get(k)) for k in keys):
        raise ValueError('SCAN_METADATA_NONFINITE')
    rays = value.get('ranges_m')
    if type(rays) is not list or not 2 <= len(rays) <= 720:
        raise ValueError('SCAN_RAY_BUDGET')
    inc = value['angle_increment']; count = len(rays)
    span = abs(inc) * (count - 1)
    end = value['angle_min'] + (count - 1) * inc
    if (not 0 < abs(inc) <= math.pi or span > math.tau + .001
            or abs(value['angle_min']) > math.tau
            or min(abs(value['angle_max'] - (end + k * inc)) for k in (0, 1, 2)) > .001
            or not 0 <= value['time_increment'] <= .1
            or not 0 < value['scan_time'] <= 2
            or value['time_increment'] * (count - 1) > value['scan_time'] + 1e-6
            or not 0 <= value['range_min'] < value['range_max'] <= 1000):
        raise ValueError('SCAN_GEOMETRY')
    if any(r is not None and (not finite(r) or not value['range_min'] <= r <= value['range_max']) for r in rays):
        raise ValueError('SCAN_RANGES_NOT_NORMALIZED')
    unknown = sum(r is None for r in rays)
    closing = math.tau - span
    return {'unknown_rays': unknown, 'closing_gap_rad': max(0., closing),
            'control_coverage': ('UNKNOWN' if unknown or not 72 <= count <= 720
                                 or not 0 < closing <= .1 else 'GEOMETRY_ONLY'),
            'oldest_stamp_ns': value['stamp_ns'],
            'last_stamp_ns': value['stamp_ns'] + round((count - 1) * value['time_increment'] * 1e9)}


def checked_payload(topic, value):
    if not isinstance(value, dict):raise ValueError('OBSERVATION_MESSAGE_SHAPE')
    if topic in {'/tf', '/tf_static'}:
        rows = value.get('transforms')
        if type(rows) is not list or len(rows) > 128:
            raise ValueError('TF_SEQUENCE_BUDGET')
        if not rows:raise ValueError('TF_EMPTY_MESSAGE')
        for row in rows:
            if not isinstance(row,dict):raise ValueError('OBSERVATION_MESSAGE_SHAPE')
            _frame(row.get('frame_id')); _frame(row.get('child_frame_id'))
            if row['frame_id']==row['child_frame_id']:raise ValueError('TF_SELF_EDGE')
            _stamp(row.get('stamp_ns'), zero=topic == '/tf_static')
            _vector(row.get('translation_m'), 3, 1000)
            _quaternion(row.get('quaternion_xyzw'))
        return {'transform_count':len(rows),'oldest_stamp_ns':min(r['stamp_ns'] for r in rows),
                'last_stamp_ns':max(r['stamp_ns'] for r in rows)}
    _stamp(value.get('stamp_ns')); _frame(value.get('frame_id'))
    if topic == 'scan':
        return scan_quality(value)
    _frame(value.get('child_frame_id'))
    _vector(value.get('position_m'), 3, 1000)
    _quaternion(value.get('quaternion_xyzw'))
    return {}


def _stamp(value, zero=False):
    if type(value) is not int or not (0 if zero else 1) <= value < 2**63:
        raise ValueError('OBSERVATION_STAMP')


def _frame(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_/]{0,79}', value):
        raise ValueError('OBSERVATION_FRAME')


def _vector(value, size, limit):
    if type(value) is not list or len(value) != size or any(not finite(v) or abs(v) > limit for v in value):
        raise ValueError('OBSERVATION_VECTOR')


def _quaternion(value):
    _vector(value, 4, 1.001)
    if abs(sum(v*v for v in value) - 1) > .001:
        raise ValueError('OBSERVATION_QUATERNION')


def from_ros_message(topic, msg):
    """Normalize duck-typed ROS without importing ROS or changing raw bytes."""
    def header(obj):
        s = obj.header.stamp
        if type(s.sec) is not int or type(s.nanosec) is not int or not 0 <= s.nanosec < 10**9:
            raise ValueError('STAMP_FORMAT')
        return {'stamp_ns': s.sec*10**9+s.nanosec, 'frame_id': obj.header.frame_id}
    if topic in {'/tf', '/tf_static'}:
        if len(msg.transforms) > 128: raise ValueError('TF_SEQUENCE_BUDGET')
        rows = []
        for row in msg.transforms:
            p, q = row.transform.translation, row.transform.rotation
            rows.append({**header(row), 'child_frame_id': row.child_frame_id,
                         'translation_m': [p.x,p.y,p.z], 'quaternion_xyzw': [q.x,q.y,q.z,q.w]})
        return {'transforms': rows}
    value = header(msg)
    if topic == 'odom':
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        return {**value, 'child_frame_id': msg.child_frame_id, 'position_m': [p.x,p.y,p.z],
                'quaternion_xyzw': [q.x,q.y,q.z,q.w]}
    if len(msg.ranges) > 720: raise ValueError('SCAN_RAY_BUDGET')
    value.update({k: getattr(msg,k) for k in ('angle_min','angle_max','angle_increment',
                 'time_increment','scan_time','range_min','range_max')})
    value['ranges_m'] = [r if finite(r) and finite(msg.range_min) and finite(msg.range_max)
                        and msg.range_min <= r <= msg.range_max else None for r in msg.ranges]
    return value


class ObservationWindow:
    """One source/epoch, bounded history, ordered receipts and explicit faults."""
    def __init__(self, context, *, capacity=128):
        self.context = checked_context(context)
        if type(capacity) is not int or not 4 <= capacity <= 1024:
            raise ValueError('OBSERVATION_WINDOW_BUDGET')
        self.history = deque(maxlen=capacity)
        self.latest = {k: None for k in sorted(TOPICS)}
        self.faults = {k: 'NOT_RECEIVED' for k in sorted(TOPICS)}
        self.counts = Counter(); self.errors = deque(maxlen=8)
        self.last_sequence = -1; self.last_receipt = -1; self.evicted = 0
        self.stamps = {}; self.offset_ns = None; self.clock_fault = False
        self.last_evicted_sequence=-1
        self.frames={};self.epoch_fault=False

    def receive(self, topic, value, sequence, receipt_ns, *, ros_now_ns=None, publishers=None):
        if topic not in TOPICS: raise ValueError('OBSERVATION_TOPIC')
        self.counts[topic] += 1; self.latest[topic] = None
        try:
            if self.clock_fault: raise ValueError('OBSERVATION_CLOCK_LATCHED')
            if self.epoch_fault:raise ValueError('OBSERVATION_FRAME_LATCHED')
            if (type(sequence) is not int or sequence <= self.last_sequence
                    or type(receipt_ns) is not int or not 0 <= receipt_ns < 2**63
                    or receipt_ns < self.last_receipt):
                self.clock_fault = True
                self.latest = {k: None for k in self.latest}
                self.faults = {k: 'OBSERVATION_CLOCK_LATCHED' for k in self.faults}
                raise ValueError('OBSERVATION_RECEIPT_OR_SEQUENCE_REVERSED')
            self.last_sequence, self.last_receipt = sequence, receipt_ns
            if publishers is not None and (type(publishers) is not int or publishers != 1):
                raise ValueError('ENDPOINT_MISSING' if publishers == 0 else 'ENDPOINT_MULTIPLE_OR_UNKNOWN')
            if ros_now_ns is not None:
                _stamp(ros_now_ns)
                offset = ros_now_ns - receipt_ns
                if self.offset_ns is not None and abs(offset-self.offset_ns) > 50_000_000:
                    self.clock_fault = True; self.latest = {k: None for k in self.latest}
                    self.faults = {k: 'OBSERVATION_CLOCK_LATCHED' for k in self.faults}
                    raise ValueError('OBSERVATION_ROS_CLOCK_JUMP')
                if self.offset_ns is None: self.offset_ns = offset
            quality = checked_payload(topic, value)
            if ros_now_ns is not None and topic=='/tf':
                if quality['last_stamp_ns']>ros_now_ns:raise ValueError('OBSERVATION_SOURCE_IN_FUTURE')
                if ros_now_ns-quality['oldest_stamp_ns']>200_000_000:raise ValueError('OBSERVATION_SOURCE_STALE')
            ns = value.get('stamp_ns')
            if ns is not None:
                frames=(value['frame_id'],value.get('child_frame_id'))
                if topic in self.frames and self.frames[topic]!=frames:
                    self.epoch_fault=True;self.latest={k:None for k in self.latest}
                    self.faults={k:'OBSERVATION_FRAME_LATCHED' for k in self.faults}
                    raise ValueError('OBSERVATION_FRAME_CHANGED')
                self.frames[topic]=frames
                if ns <= self.stamps.get(topic, -1): raise ValueError('OBSERVATION_SOURCE_TIME_REVERSED')
                if ros_now_ns is not None and quality.get('last_stamp_ns', ns) > ros_now_ns:
                    raise ValueError('OBSERVATION_SOURCE_IN_FUTURE')
                if ros_now_ns is not None and ros_now_ns-ns > 200_000_000:
                    raise ValueError('OBSERVATION_SOURCE_STALE')
                self.stamps[topic] = ns
            keys = ({'transforms'} if topic in {'/tf','/tf_static'} else
                    {'stamp_ns','frame_id','child_frame_id','position_m','quaternion_xyzw'} if topic=='odom' else
                    {'stamp_ns','frame_id','angle_min','angle_max','angle_increment','time_increment',
                     'scan_time','range_min','range_max','ranges_m'})
            event = {'topic': topic, 'sequence': sequence, 'receipt_monotonic_ns': receipt_ns,
                     'timing_basis': UNVERIFIED_TIMING,
                     'data':copy.deepcopy({k:value[k] for k in keys}), 'quality': quality}
            if len(self.history) == self.history.maxlen:
                self.evicted += 1;self.last_evicted_sequence=self.history[0]['sequence']
            self.history.append(event); self.latest[topic] = event; self.faults[topic] = 'NONE'
            return event
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'OBSERVATION_MESSAGE_SHAPE'
            self.faults[topic] = reason
            self.errors.append({'topic': topic, 'sequence': sequence, 'reason': reason})
            return None

    def summary(self):
        return {'schema': 'common-ros-evidence-1.0', 'context': dict(self.context),
                'counts': dict(self.counts), 'faults': dict(self.faults),
                'retained_events': len(self.history), 'evicted_events': self.evicted,
                'recent_errors':list(self.errors),'clock_fault':self.clock_fault,'epoch_fault':self.epoch_fault,
                'timing_basis': UNVERIFIED_TIMING, 'alignment_verified': False, 'motion_authorized': False}

    def pose_at(self, stamp_ns):
        """Interpolate only already-received odom; never extrapolate or use TF as calibration."""
        from math import atan2, sin, cos
        _stamp(stamp_ns)
        if self.clock_fault:raise ValueError('OBSERVATION_CLOCK_LATCHED')
        if self.epoch_fault:raise ValueError('OBSERVATION_FRAME_LATCHED')
        rows=[e['data'] for e in self.history if e['topic']=='odom']
        def pose(row):
            q=row['quaternion_xyzw'];p=row['position_m']
            if abs(q[0])+abs(q[1])>.001:raise ValueError('NONPLANAR_OR_INVALID_ODOM')
            return [p[0],p[1],2*atan2(q[2],q[3])]
        for i,row in enumerate(rows):
            if row['stamp_ns']==stamp_ns:return pose(row)
            if i and rows[i-1]['stamp_ns']<stamp_ns<row['stamp_ns']:
                lo=rows[i-1];gap=row['stamp_ns']-lo['stamp_ns']
                if (lo['frame_id'],lo['child_frame_id'])!=(row['frame_id'],row['child_frame_id']):
                    raise ValueError('ODOM_FRAME_CHANGED')
                if gap>100_000_000:raise ValueError('ODOM_TIME_GAP')
                f=(stamp_ns-lo['stamp_ns'])/gap;a,b=pose(lo),pose(row)
                delta=atan2(sin(b[2]-a[2]),cos(b[2]-a[2]))
                return [a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]),atan2(sin(a[2]+f*delta),cos(a[2]+f*delta))]
        raise ValueError('ODOM_TIME_UNBRACKETED')

    def events_since(self, sequence):
        """Shared polling contract; consumers cannot silently skip overwritten input."""
        if type(sequence) is not int or sequence < -1:raise ValueError('OBSERVATION_CURSOR_INVALID')
        if self.clock_fault:raise ValueError('OBSERVATION_CLOCK_LATCHED')
        if self.epoch_fault:raise ValueError('OBSERVATION_FRAME_LATCHED')
        if sequence < self.last_evicted_sequence:raise ValueError('OBSERVATION_CONSUMER_OVERRUN')
        return copy.deepcopy([e for e in self.history if e['sequence']>sequence])

    def health_at(self, receipt_ns):
        if type(receipt_ns) is not int or receipt_ns<self.last_receipt:
            raise ValueError('OBSERVATION_HEALTH_CLOCK')
        health=self.summary();health['faults']=dict(health['faults'])
        for topic,event in self.latest.items():
            if event is not None and topic!='/tf_static' and receipt_ns-event['receipt_monotonic_ns']>200_000_000:
                health['faults'][topic]='OBSERVATION_RECEIPT_STALE'
        return health


class RecordedObservationSource:
    """Yield raw-sequence order, exposing no future observations to consumers.

    The adapter supplies already integrity-verified frames and the CDR decoder.
    Timing remains unverified even if all messages decode successfully.
    """
    def __init__(self, frames, decoder, context):
        self.window = ObservationWindow(context)
        if self.window.context['origin'] != 'recorded_ros': raise ValueError('RECORDED_SOURCE_ORIGIN')
        self.frames, self.decoder = frames, decoder
        self.started=False

    def __iter__(self):
        if self.started:raise ValueError('OBSERVATION_REPLAY_ALREADY_CONSUMED')
        self.started=True
        for meta, payload in self.frames:
            topic = meta['topic']
            if topic not in TOPICS: continue
            try: value = self.decoder(meta['type'], payload)
            except (ValueError, TypeError) as exc:
                self.window.receive(topic,{},meta['sequence'],meta['receipt_monotonic_ns'])
                code=str(exc) if re.fullmatch('[A-Z0-9_]{1,100}',str(exc)) else 'CDR_DECODE_FAILED'
                if not self.window.clock_fault and not self.window.epoch_fault:
                    self.window.faults[topic]='CDR_DECODE_FAILED'
                    self.window.errors[-1]={'topic':topic,'sequence':meta['sequence'],'reason':code}
                yield {'topic':topic,'sequence':meta['sequence'],'status':'REJECTED',
                    'reason':self.window.faults[topic],'error_code':code}
                continue
            event = self.window.receive(topic, value, meta['sequence'], meta['receipt_monotonic_ns'])
            yield event if event is not None else {'topic':topic,'sequence':meta['sequence'],
                'status':'REJECTED','reason':self.window.faults[topic]}
