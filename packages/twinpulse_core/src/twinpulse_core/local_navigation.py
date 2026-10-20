# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Transport-free local command checks; NOT physical execution authority.

Uniform full-circle rays must already be in base_link with explicit transform
evidence. A saved recording or photo hypothesis cannot meet the live contract.
The circular swept envelope is deliberately conservative; low/overhead obstacles,
glass, slip and obstacles between rays remain outside this 2D software check.
"""
from dataclasses import dataclass
import math
from twinpulse_core.robot_control_timing import INPUT_TTL_S


@dataclass(frozen=True)
class LocalScan:
    ranges_m: tuple
    oldest_sample_s: float
    frame_id: str
    transform_basis: str
    provenance: str


@dataclass(frozen=True)
class LocalClearance:
    """Derived circular envelope, NOT fabricated base-frame lidar rays."""
    clear_radius_m: float
    oldest_sample_s: float
    frame_id: str
    transform_basis: str
    provenance: str
    footprint_radius_m: float


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def checked_command(v, w, source_age_s, scan, now, *, require_scan=True, provenance=None, supervised_manual=False, input_ttl_s=INPUT_TTL_S):
    """Shared output boundary. Supervised legacy mode is NOT collision protection.

    Caller retains original command age; this function never grants arm/lease.
    The standalone copy in robot bundles is byte-identical to this core source.
    """
    def deny(reason):
        return {'allowed':False,'reason':reason,'linear_m_s':0.,'angular_rad_s':0.,'physical_authority':False}
    if not finite(input_ttl_s) or not .1<=input_ttl_s<=1.:return deny('INPUT_TIMING_INVALID')
    if not finite(source_age_s) or not 0<=source_age_s<input_ttl_s:return deny('SOURCE_EXPIRED_DURING_ENABLE')
    # Explicit supervised manual mode only; autonomous/scan envelopes stay unchanged.
    if supervised_manual and require_scan:return deny('COMMAND_INVALID')
    linear,angular=(.05,.3) if supervised_manual is True else (.03,.2)
    if not all(finite(x) for x in (v,w,now)) or abs(v)>linear or abs(w)>angular:return deny('COMMAND_INVALID')
    if require_scan:
        if (v or w) and provenance is not None and (not isinstance(scan,(LocalScan,LocalClearance)) or scan.provenance!=provenance):
            return deny('SCAN_SOURCE_MISMATCH')
        return guarded_velocity(v,w,scan,now)
    return {'allowed':True,'reason':'SUPERVISED_WITHOUT_SCAN_CHECK','linear_m_s':v,
            'angular_rad_s':w,'physical_authority':False}


def guarded_velocity(v, w, scan, now, *, radius_m=.18):
    """No command refresh, no auto-arm. Return a decision for a local adapter.

    Radius includes body/wheels/supports and must be established by the caller.
    Default is a rehearsal envelope, NOT a calibrated Burger specification.
    Horizon 1.2s covers existing 400ms output expiry + 800ms stop observation;
    it is an engineering budget, not a guaranteed physical stopping distance.
    """
    def result(reason, allowed=False):
        return {'allowed':allowed, 'reason':reason, 'linear_m_s':v if allowed else 0.,
                'angular_rad_s':w if allowed else 0., 'physical_authority':False}
    if not all(finite(x) for x in (v,w,now,radius_m)) or not 0<radius_m<=1 or abs(v)>.03 or abs(w)>.2:
        return result('COMMAND_INVALID')
    if v==0 and w==0:return result('STOP', True)
    if not isinstance(scan,(LocalScan,LocalClearance)):return result('SCAN_MISSING')
    if scan.provenance not in {'synthetic_raycast','live_sensor'}:return result('SCAN_NOT_CURRENT_SOURCE')
    expected='synthetic_model' if scan.provenance=='synthetic_raycast' else 'measured_sensor_extrinsic'
    if scan.frame_id!='base_link' or scan.transform_basis!=expected:return result('FRAME_UNVERIFIED')
    if not finite(scan.oldest_sample_s) or not 0<=now-scan.oldest_sample_s<.2:return result('SCAN_STALE')
    if isinstance(scan,LocalClearance):
        if (scan.provenance!='live_sensor' or not finite(scan.clear_radius_m)
                or not 0<=scan.clear_radius_m<=30 or not finite(scan.footprint_radius_m)
                or not 0<scan.footprint_radius_m<=1):return result('SCAN_COVERAGE_UNKNOWN')
        clear=scan.clear_radius_m
        radius_m=max(radius_m,scan.footprint_radius_m)  # Never shrink the existing envelope.
    else:
        rays=scan.ranges_m
        if type(rays) is not tuple or not 72<=len(rays)<=720:return result('SCAN_COVERAGE_UNKNOWN')
        if any(not finite(r) or not 0<r<=30 for r in rays):return result('SCAN_COVERAGE_UNKNOWN')
        # Inscribed radius of the polar free-space polygon, no missing rays filled.
        clear=min(rays)*math.cos(math.pi/len(rays))
    required=radius_m+.05+abs(v)*1.2
    decision=result('CLEAR_IN_SCAN_ENVELOPE' if clear>required else 'OBSTACLE_IN_SWEPT_ENVELOPE',clear>required)
    return {**decision,'clear_radius_m':clear,'required_radius_m':required}


class WaypointMission:
    """Fixed bounded mission; each tick decides turn/drive/arrival without UI approval.

    Pose must be supplied by an adapter, not integrated from commands here.
    Reverse requires an explicit policy; CheckedMission still applies the same
    current full-circle footprint guard. No invented recovery or blind reverse.
    """
    def __init__(self, waypoints, started_s, duration_s=90., *, allow_reverse=False):
        if (type(waypoints) is not tuple or not 1<=len(waypoints)<=16
                or any(type(p) is not tuple or len(p)!=2 or any(not finite(x) or abs(x)>10 for x in p) for p in waypoints)
                or not finite(started_s) or not finite(duration_s) or not 0<duration_s<=300):
            raise ValueError('INVALID_MISSION')
        self.waypoints=waypoints;self.index=0;self.end=started_s+duration_s
        self.last=started_s;self.status='RUNNING'
        if type(allow_reverse) is not bool:raise ValueError('INVALID_MISSION_DIRECTION_POLICY')
        self.allow_reverse=allow_reverse

    def tick(self, pose, now):
        if self.status!='RUNNING':return 0.,0.
        if not finite(now) or now<self.last:self.status='CLOCK_FAULT';return 0.,0.
        self.last=now
        if now>=self.end:self.status='MISSION_EXPIRED';return 0.,0.
        if type(pose) is not tuple or len(pose)!=3 or any(not finite(x) for x in pose):
            self.status='POSE_INVALID';return 0.,0.
        x,y,yaw=pose
        while self.index<len(self.waypoints) and math.dist((x,y),self.waypoints[self.index])<=.015:self.index+=1
        if self.index==len(self.waypoints):self.status='ARRIVED';return 0.,0.
        gx,gy=self.waypoints[self.index]
        error=math.atan2(math.sin(math.atan2(gy-y,gx-x)-yaw),math.cos(math.atan2(gy-y,gx-x)-yaw))
        reverse=self.allow_reverse and abs(error)>math.pi/2
        if reverse:error=math.atan2(math.sin(error+math.pi),math.cos(error+math.pi))
        return (0.,.2 if error>0 else -.2) if abs(error)>.04 else (-.03 if reverse else .03,0.)

    def stop(self, reason):self.status=reason


@dataclass(frozen=True)
class LocalPose:
    xy_yaw: tuple
    sample_s: float
    frame_id: str
    basis: str
    provenance: str


class CheckedMission:
    """Robot-local or synthetic decision lifecycle, without transport or auto-arm.

    No per-command user approval. A caller must still hold the existing verified
    lease/qualification and deliver returned decisions through a checked adapter.
    Live entry/ROS scan/TF ingestion is not implemented by this pure class.
    """
    def __init__(self, waypoints, started_s, *, provenance, frame_id, duration_s=90.,allow_reverse=False):
        if provenance not in {'synthetic_raycast','live_sensor'} or frame_id not in {'synthetic_room','odom'}:
            raise ValueError('MISSION_SOURCE_INVALID')
        if (provenance=='synthetic_raycast')!=(frame_id=='synthetic_room'):raise ValueError('MISSION_FRAME_INVALID')
        self.mission=WaypointMission(waypoints,started_s,duration_s,allow_reverse=allow_reverse)
        self.provenance,self.frame_id=provenance,frame_id
        self.proposed=(0.,0.)

    def step(self, pose, scan, now, *, command_created_s):
        self.proposed=(0.,0.)
        def stopped(reason):
            self.mission.stop(reason)
            return {'allowed':False,'reason':reason,'linear_m_s':0.,'angular_rad_s':0.,'physical_authority':False}
        if self.mission.status!='RUNNING':return stopped(self.mission.status)
        if not finite(now) or now<self.mission.last:return stopped('CLOCK_FAULT')
        if now>=self.mission.end:return stopped('MISSION_EXPIRED')
        basis='synthetic_model' if self.provenance=='synthetic_raycast' else 'measured_odometry'
        if (not isinstance(pose,LocalPose) or pose.provenance!=self.provenance
                or pose.frame_id!=self.frame_id or pose.basis!=basis):return stopped('POSE_FRAME_UNVERIFIED')
        if not finite(pose.sample_s) or not 0<=now-pose.sample_s<.2:return stopped('POSE_STALE')
        if not finite(command_created_s):return stopped('SOURCE_EXPIRED_DURING_ENABLE')
        v,w=self.mission.tick(pose.xy_yaw,now)
        self.proposed=(v,w)
        if self.mission.status not in {'RUNNING','ARRIVED'}:return stopped(self.mission.status)
        decision=checked_command(v,w,now-command_created_s,scan,now,provenance=self.provenance)
        if not decision['allowed']:self.mission.stop(decision['reason'])
        return decision
