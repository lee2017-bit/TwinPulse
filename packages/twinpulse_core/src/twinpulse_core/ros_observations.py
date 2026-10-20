# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded passive ROS evidence, not TF evidence or movement permission.

Duck-typed messages keep ROS imports out of PC tests. Source age is preserved
when mapping a ROS stamp to robot monotonic time. No interpolation/driver startup.
"""
import copy
import math
import re


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def frame(v):
    return isinstance(v, str) and re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_/]{0,79}', v) is not None


def valid_scan_preview(v):
    """Display-only laser rays. Missing returns are holes, never free space.

    This contract is separate from strict navigation observations and cannot
    authorize motion or relax their freshness/range requirements.
    """
    keys={'schema','frame_id','source_stamp_ns','sample_s','receipt_s','angle_min_rad',
          'angle_increment_rad','range_min_m','range_max_m','ranges_m','display_only','alignment_verified'}
    if not isinstance(v,dict) or set(v)!=keys:return False
    if (v['schema']!='lidar-display-1.0' or v['display_only'] is not True
            or v['alignment_verified'] is not False or not frame(v['frame_id'])
            or type(v['source_stamp_ns']) is not int or not 0<v['source_stamp_ns']<2**63):return False
    if not all(finite(v[k]) for k in ('sample_s','receipt_s','angle_min_rad',
            'angle_increment_rad','range_min_m','range_max_m')):return False
    rays=v['ranges_m']
    return (0<=v['sample_s']<=v['receipt_s'] and v['receipt_s']-v['sample_s']<2.
            and 0<v['range_min_m']<v['range_max_m']<=1000 and abs(v['angle_min_rad'])<=math.tau
            and 0<abs(v['angle_increment_rad'])<=.1 and type(rays) is list and 72<=len(rays)<=720
            # COIN D4 can omit a terminal bin. Preserve the supplied spacing;
            # do not stretch returns over the unobserved angular gap.
            and abs(abs(v['angle_increment_rad'])*len(rays)-math.tau)<=abs(v['angle_increment_rad'])+.001
            and all(r is None or finite(r) and v['range_min_m']<=r<=v['range_max_m'] for r in rays))


def scan_preview(msg,ros_now_ns,receipt_s,*,diagnostic=None):
    def fail(reason):
        if diagnostic is not None:diagnostic['reason']=reason
        return None
    try:
        stamp=msg.header.stamp
        if (type(stamp.sec) is not int or type(stamp.nanosec) is not int
                or not 0<=stamp.sec<2**31 or not 0<=stamp.nanosec<10**9
                or type(ros_now_ns) is not int or not finite(receipt_s)):return fail('STAMP_FORMAT')
        ns=stamp.sec*10**9+stamp.nanosec;age=(ros_now_ns-ns)/1e9
        if not 0<=age<2.:return fail('SOURCE_TIME')
        if not 72<=len(msg.ranges)<=720:return fail('RAY_COUNT')
        if (not finite(msg.angle_max) or not finite(msg.angle_min) or not finite(msg.angle_increment)
                or min(abs(msg.angle_max-(msg.angle_min+(len(msg.ranges)+offset)*msg.angle_increment))
                       for offset in (-1,0,1))>.001):return fail('ANGLE_ENDPOINT')
        v={'schema':'lidar-display-1.0','frame_id':msg.header.frame_id,'source_stamp_ns':ns,
           'sample_s':receipt_s-age,'receipt_s':receipt_s,'angle_min_rad':msg.angle_min,
           'angle_increment_rad':msg.angle_increment,'range_min_m':msg.range_min,'range_max_m':msg.range_max,
           'ranges_m':[r if finite(r) and finite(msg.range_min) and finite(msg.range_max)
                       and msg.range_min<=r<=msg.range_max else None for r in msg.ranges],
           'display_only':True,'alignment_verified':False}
        if not valid_scan_preview(v):return fail('DISPLAY_METADATA')
        if diagnostic is not None:diagnostic['reason']='NONE'
        return v
    except (AttributeError,TypeError,ValueError,OverflowError):return fail('MESSAGE_SHAPE')


def valid_snapshot(value, *, odom_age_s=.2, scan_age_s=.2):
    """Same bounded contract on robot output and PC journal input."""
    if not isinstance(value, dict) or set(value) != {'schema','t','odom','scan','faults','alignment_verified','motion_authorized'}:
        return False
    if (value['schema'] != 'passive-ros-observation-1.0' or not finite(value['t']) or value['t'] < 0
            or value['alignment_verified'] is not False or value['motion_authorized'] is not False):return False
    faults=value['faults']
    # Fault vocabulary may grow without changing the snapshot shape.  These
    # codes contain no raw ROS fields and cannot make an invalid sample usable.
    reasons={'NOT_RECEIVED','NONE','STALE','INVALID_MESSAGE','ENDPOINT_COUNT','CLOCK_FAULT','SOURCE_TIME',
             'STAMP_FORMAT','FRAME_ID','ODOM_POSITION','ODOM_ORIENTATION',
             'SCAN_GEOMETRY','SCAN_RANGES','MESSAGE_SHAPE'}
    if (not isinstance(faults,dict) or set(faults)!={'odom','scan'}
            or any(not isinstance(x,str) or x not in reasons for x in faults.values())):return False
    for kind in ('odom','scan'):
        item=value[kind]
        if item is None:
            if faults[kind]=='NONE':return False
            continue
        common={'sample_s','receipt_s','source_stamp_ns','frame_id'}
        extra={'child_frame_id','position_m','quaternion_xyzw'} if kind=='odom' else {
            'angle_min_rad','angle_increment_rad','range_min_m','range_max_m','time_increment_s','ranges_m'}
        if not isinstance(item,dict) or set(item)!=common|extra or faults[kind]!='NONE':return False
        if (not all(finite(item[k]) for k in ('sample_s','receipt_s'))
                or not 0<=item['sample_s']<=item['receipt_s']<=value['t']
                or not 0<=value['t']-item['sample_s']<(odom_age_s if kind=='odom' else scan_age_s)
                or type(item['source_stamp_ns']) is not int or not 0<item['source_stamp_ns']<2**63
                or not frame(item['frame_id'])):return False
        if kind=='odom':
            if not frame(item['child_frame_id']):return False
            for k,size,limit in (('position_m',3,1000),('quaternion_xyzw',4,1.001)):
                if (type(item[k]) is not list or len(item[k])!=size
                        or any(not finite(x) or abs(x)>limit for x in item[k])):return False
            if abs(sum(x*x for x in item['quaternion_xyzw'])-1)>.001:return False
        else:
            rays=item['ranges_m']
            if type(rays) is not list or not 72<=len(rays)<=720:return False
            if not all(finite(item[k]) for k in extra-{'ranges_m'}):return False
            if not (0<item['range_min_m']<item['range_max_m']<=30 and 0<item['angle_increment_rad']<=.1
                    and abs(item['angle_min_rad'])<=math.tau and 0<=item['time_increment_s']<.2):return False
            if abs(item['angle_increment_rad']*len(rays)-math.tau)>.01:return False
            if item['time_increment_s']*(len(rays)-1)>item['receipt_s']-item['sample_s']+1e-6:return False
            if any(not finite(r) or not item['range_min_m']<=r<=item['range_max_m'] for r in rays):return False
    return True


def _payload_fault(kind,item):
    """Bounded diagnostic for a rejected payload; never a validation bypass."""
    if not frame(item['frame_id']) or (kind=='odom' and not frame(item['child_frame_id'])):
        return 'FRAME_ID'
    if kind=='odom':
        p,q=item['position_m'],item['quaternion_xyzw']
        if type(p) is not list or len(p)!=3 or any(not finite(x) or abs(x)>1000 for x in p):
            return 'ODOM_POSITION'
        if (type(q) is not list or len(q)!=4 or any(not finite(x) or abs(x)>1.001 for x in q)
                or abs(sum(x*x for x in q)-1)>.001):
            return 'ODOM_ORIENTATION'
    else:
        rays=item['ranges_m']
        if (type(rays) is not list or not 72<=len(rays)<=720
                or any(not finite(r) or not item['range_min_m']<=r<=item['range_max_m'] for r in rays)):
            return 'SCAN_RANGES'
        if (any(not finite(item[k]) for k in ('angle_min_rad','angle_increment_rad','range_min_m',
                                            'range_max_m','time_increment_s'))
                or not 0<item['range_min_m']<item['range_max_m']<=30
                or not 0<item['angle_increment_rad']<=.1
                or abs(item['angle_min_rad'])>math.tau
                or not 0<=item['time_increment_s']<.2
                or abs(item['angle_increment_rad']*len(rays)-math.tau)>.01):
            return 'SCAN_GEOMETRY'
    return 'INVALID_MESSAGE'


class RosObservations:
    def __init__(self, *, timing_values=None):
        self.timing_values=timing_values
        self.values={'odom':None,'scan':None}
        self.faults={'odom':'NOT_RECEIVED','scan':'NOT_RECEIVED'}
        self.stamps={'odom':0,'scan':0}
        self.offset=None;self.last=-1.;self.clock_fault=False

    def age_limit(self,kind):
        return .2 if self.timing_values is None else self.timing_values['odom_source_ms' if kind=='odom' else 'scan_source_ms']/1000

    def receive(self,kind,msg,ros_now_ns,receipt_s,publishers):
        if kind not in self.values:raise ValueError('UNKNOWN_OBSERVATION')
        if self.clock_fault:return
        self.values[kind]=None
        self.faults[kind]='INVALID_MESSAGE'
        if (not finite(receipt_s) or receipt_s<0 or receipt_s<self.last
                or type(ros_now_ns) is not int or not 0<ros_now_ns<2**63):
            self._clock_failed();return
        offset=ros_now_ns/1e9-receipt_s
        if self.offset is not None and abs(offset-self.offset)>.05:
            self._clock_failed();return
        if self.offset is None:self.offset=offset
        self.last=receipt_s
        if type(publishers) is not int or publishers!=1:
            self.faults[kind]='ENDPOINT_COUNT';return
        try:
            stamp=msg.header.stamp
            if (type(stamp.sec) is not int or type(stamp.nanosec) is not int
                    or not 0<=stamp.sec<2**31 or not 0<=stamp.nanosec<10**9):
                self.faults[kind]='STAMP_FORMAT';return
            ns=stamp.sec*10**9+stamp.nanosec
            age=(ros_now_ns-ns)/1e9
            if ns<=self.stamps[kind] or not 0<=age<self.age_limit(kind):
                self.faults[kind]='SOURCE_TIME';return
            item={'sample_s':receipt_s-age,'receipt_s':receipt_s,'source_stamp_ns':ns,'frame_id':msg.header.frame_id}
            if kind=='odom':
                p,q=msg.pose.pose.position,msg.pose.pose.orientation
                item.update(child_frame_id=msg.child_frame_id,position_m=[p.x,p.y,p.z],quaternion_xyzw=[q.x,q.y,q.z,q.w])
            else:
                if not 72<=len(msg.ranges)<=720:
                    self.faults[kind]='SCAN_RANGES';return
                item.update(angle_min_rad=msg.angle_min,angle_increment_rad=msg.angle_increment,
                            range_min_m=msg.range_min,range_max_m=msg.range_max,
                            time_increment_s=msg.time_increment,ranges_m=list(msg.ranges))
                if not finite(msg.angle_max) or abs(msg.angle_max-(msg.angle_min+(len(msg.ranges)-1)*msg.angle_increment))>.01:
                    self.faults[kind]='SCAN_GEOMETRY';return
            candidate={'schema':'passive-ros-observation-1.0','t':receipt_s,'odom':None,'scan':None,
                       'faults':{'odom':'NOT_RECEIVED','scan':'NOT_RECEIVED'},
                       'alignment_verified':False,'motion_authorized':False}
            candidate[kind]=item;candidate['faults'][kind]='NONE'
            if not valid_snapshot(candidate,odom_age_s=self.age_limit('odom'),scan_age_s=self.age_limit('scan')):
                self.faults[kind]=_payload_fault(kind,item)
                return
            self.values[kind]=item;self.faults[kind]='NONE';self.stamps[kind]=ns
        except (AttributeError,TypeError,ValueError,OverflowError):
            self.faults[kind]='MESSAGE_SHAPE'
            return

    def _clock_failed(self):
        self.clock_fault=True
        self.values={'odom':None,'scan':None}
        self.faults={'odom':'CLOCK_FAULT','scan':'CLOCK_FAULT'}

    def snapshot(self,now):
        if not finite(now) or now<max(0,self.last):
            self._clock_failed()
            raise ValueError('OBSERVATION_CLOCK_FAULT')
        self.last=now
        values=copy.deepcopy(self.values);faults=dict(self.faults)
        for kind,item in values.items():
            if item is not None and not 0<=now-item['sample_s']<self.age_limit(kind):
                values[kind]=None;faults[kind]='STALE'
        return {'schema':'passive-ros-observation-1.0','t':now,**values,'faults':faults,
                'alignment_verified':False,'motion_authorized':False}
