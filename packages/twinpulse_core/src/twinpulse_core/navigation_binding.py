# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Passive ROS evidence -> navigation input under an explicit planar binding.

No default robot calibration and no TF lookup/driver startup. The caller must
establish these transforms and footprint from reviewed evidence before using a
binding on hardware. The evidence digest is attribution, NOT authentication or
proof of calibration. Tests inject artificial bindings; none is shipped for the
user's robot. This module grants neither alignment verification nor motion.
"""
from dataclasses import dataclass
import math
import re

try:
    from .local_navigation import LocalPose, LocalClearance, finite
    from .ros_observations import valid_snapshot, frame
except ImportError:
    # Byte-identical, standalone modules in the reviewed robot release bundle.
    from local_navigation import LocalPose, LocalClearance, finite
    from ros_observations import valid_snapshot, frame


@dataclass(frozen=True)
class PlanarBinding:
    odom_child_frame: str
    scan_frame: str
    # Pose of base_link in the odometry child frame: x,y,yaw.
    child_to_base: tuple
    # Pose of the scan origin in base_link: x,y,yaw. Both frames must be planar.
    base_to_scan: tuple
    footprint_radius_m: float
    evidence_sha256: str

    def valid(self):
        return (frame(self.odom_child_frame) and frame(self.scan_frame)
                and all(type(p) is tuple and len(p)==3
                        and all(finite(x) for x in p)
                        and abs(p[0])<=1 and abs(p[1])<=1 and abs(p[2])<=math.pi
                        for p in (self.child_to_base,self.base_to_scan))
                and finite(self.footprint_radius_m) and .18<=self.footprint_radius_m<=1
                and isinstance(self.evidence_sha256,str)
                and re.fullmatch('[0-9a-f]{64}',self.evidence_sha256) is not None)


def navigation_inputs(snapshot, binding, now):
    """Reject missing/stale/misaligned evidence; preserve raw input unchanged.

    Uniform full-circle rays remain in their source frame. Translate a scalar
    inscribed-circle bound by subtracting the sensor offset; do not relabel the
    rays as base_link measurements. This remains a 2D sampled-space assumption,
    not protection against glass, low obstacles, slip or gaps between beams.
    """
    if not isinstance(binding,PlanarBinding) or not binding.valid():
        raise ValueError('NAVIGATION_BINDING_REQUIRED')
    if not valid_snapshot(snapshot):raise ValueError('NAVIGATION_SNAPSHOT_INVALID')
    if not finite(now) or not snapshot['t']<=now<snapshot['t']+.2:
        raise ValueError('NAVIGATION_SNAPSHOT_STALE')
    odom,scan=snapshot['odom'],snapshot['scan']
    if odom is None or scan is None:raise ValueError('NAVIGATION_OBSERVATION_MISSING')
    if any(not 0<=now-item['sample_s']<.2 for item in (odom,scan)):
        raise ValueError('NAVIGATION_OBSERVATION_STALE')
    if abs(odom['sample_s']-scan['sample_s'])>.05:
        raise ValueError('NAVIGATION_TIME_SKEW')
    if (odom['frame_id']!='odom' or odom['child_frame_id']!=binding.odom_child_frame
            or scan['frame_id']!=binding.scan_frame):raise ValueError('NAVIGATION_FRAME_MISMATCH')
    qx,qy,qz,qw=odom['quaternion_xyzw']
    # No silent projection of roll/pitch or tilted sensor frames into a 2D map.
    if abs(qx)>1e-6 or abs(qy)>1e-6:raise ValueError('NAVIGATION_NONPLANAR_POSE')
    yaw=2*math.atan2(qz,qw)
    x,y,_=odom['position_m'];tx,ty,theta=binding.child_to_base
    pose=LocalPose((x+math.cos(yaw)*tx-math.sin(yaw)*ty,
                    y+math.sin(yaw)*tx+math.cos(yaw)*ty,
                    math.atan2(math.sin(yaw+theta),math.cos(yaw+theta))),
                   odom['sample_s'],'odom','measured_odometry','live_sensor')
    rays=scan['ranges_m'];increment=scan['angle_increment_rad']
    # Include the closing angular gap (the input contract permits small roundoff).
    closing=math.tau-(len(rays)-1)*increment
    if not 0<closing<=.1:raise ValueError('NAVIGATION_SCAN_CLOSURE')
    clear=min(rays)*math.cos(max(increment,closing)/2)
    clear=max(0.,clear-math.hypot(*binding.base_to_scan[:2]))
    envelope=LocalClearance(clear,scan['sample_s'],'base_link',
                            'measured_sensor_extrinsic','live_sensor',binding.footprint_radius_m)
    return pose,envelope
