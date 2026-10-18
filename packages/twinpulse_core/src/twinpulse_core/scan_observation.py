# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Diagnostic endpoint evidence, independent of photo geometry.

No occupancy/free-space inference, ICP pose correction, SLAM or motion authority.
Original headers are used unchanged and explicitly remain timing-unverified.
"""
import math
from statistics import median

from .room_localization import compose, inverse, deskew


def acquisition_timing_candidate(start_clock_ns, publish_clock_ns, publish_ros_ns, offsets_ns):
    """Device-free clock/beam contract fixture, NOT a hardware correction.

    The two clock samples must share a domain, and its offset to ROS must be
    stable across a scan. Reversed/nonuniform acquisition cannot be represented
    by silently assigning positive index times. No recorded header is modified.
    """
    times = [start_clock_ns, publish_clock_ns, publish_ros_ns]
    if any(type(t) is not int or not 0 <= t < 2**63 for t in times):
        raise ValueError('TIMING_CLOCK_SAMPLE_INVALID')
    if not 0 <= publish_clock_ns-start_clock_ns <= 2_000_000_000:
        raise ValueError('TIMING_CLOCK_DOMAIN_OR_LATENCY_INVALID')
    if not 2 <= len(offsets_ns) <= 4096 or any(type(t) is not int for t in offsets_ns):
        raise ValueError('TIMING_BEAM_OFFSET_COUNT_OR_TYPE')
    if offsets_ns[0] != 0:
        raise ValueError('TIMING_FIRST_BEAM_OFFSET_REQUIRED')
    gaps = [b-a for a,b in zip(offsets_ns, offsets_ns[1:])]
    if min(gaps) <= 0 or len(set(gaps)) != 1:
        raise ValueError('TIMING_BEAM_ORDER_OR_NONUNIFORM_INCREMENT')
    if offsets_ns[-1] > publish_clock_ns-start_clock_ns:
        raise ValueError('TIMING_BEAM_AFTER_PUBLICATION')
    header = publish_ros_ns-(publish_clock_ns-start_clock_ns)
    if header < 0: raise ValueError('TIMING_ROS_CLOCK_UNDERFLOW')
    return {'first_ray_ros_ns_candidate': header, 'time_increment_ns': gaps[0],
            'publish_delay_ns': publish_clock_ns-start_clock_ns,
            'clock_basis':'SAME_DOMAIN_STABLE_OFFSET_ASSUMPTION',
            'acquisition_timing_verified':False, 'hardware_correction_applied':False}


def timing_audit(scans):
    intervals = [(b['stamp_ns']-a['stamp_ns'])/1e9 for a,b in zip(scans,scans[1:])]
    if any(v <= 0 for v in intervals): raise ValueError('SCAN_SOURCE_CLOCK_RESET_OR_DUPLICATE')
    return {'header_basis':'DECLARED_ROS_HEADER_NOT_VERIFIED_FIRST_RAY',
            'beam_order':'DECLARED_ARRAY_INDEX_NOT_VERIFIED_ACQUISITION_ORDER',
            'acquisition_timing_verified':False, 'correction_applied':False,
            'median_header_interval_s':median(intervals) if intervals else None,
            'max_header_interval_s':max(intervals) if intervals else None,
            'max_declared_sweep_s':max((len(s['ranges_m'])-1)*s['time_increment'] for s in scans)}


def build_observation_map(scans, timeline, child_to_scan):
    """Project sampled returns from all paired scans into this session's odom.

    5cm endpoint bins are visualization bins, not navigation occupancy cells.
    Non-return/out-of-view rays do NOT clear any space. 64 uniform keyframes
    retain original frame/time identifiers for historical scan playback.
    """
    if not 1 <= len(scans) <= 8192: raise ValueError('OBSERVATION_SCAN_BUDGET')
    if len({s['frame_id'] for s in scans}) != 1: raise ValueError('SCAN_FRAME_CHANGED')
    audit = timing_audit(scans)
    anchor = list(timeline.poses[0]); local_from_odom = inverse(anchor)
    n = len(scans); key_indices = {round(i*(n-1)/max(1,min(64,n)-1)) for i in range(min(64,n))}
    cells = {}; keyframes = []; failures = []; paired = 0; beyond = 0; first_valid = None
    starts = scans[0]['stamp_ns']; sampled_hits = 0; empty = 0
    for i, scan in enumerate(scans):
        # Keep the exact ray indices; range clipping is display-only and counted.
        far = sum(v is not None and v > 8. for v in scan['ranges_m']); beyond += far
        clipped = {**scan,'ranges_m':[None if v is not None and v>8. else v for v in scan['ranges_m']]}
        try:
            points, sensor = deskew(clipped, timeline, child_to_scan)
            sensor_local = compose(local_from_odom,sensor)
            if max(abs(v) for v in sensor_local[:2]) > 20:
                raise ValueError('OBSERVATION_ODOM_EXTENT_BUDGET')
            cloud = [compose(sensor_local,[*p,0])[:2] for p in points]
            if any(not all(math.isfinite(v) and abs(v)<=30 for v in p) for p in cloud):
                raise ValueError('OBSERVATION_POINT_EXTENT_BUDGET')
            paired += 1; empty += not bool(cloud); sampled_hits += len(cloud)
            for x,y in cloud:
                cell = (math.floor(x/.05), math.floor(y/.05))
                if cell not in cells:
                    if len(cells) >= 18000: raise ValueError('OBSERVATION_ENDPOINT_CELL_BUDGET')
                    cells[cell] = [0,i,i]
                cells[cell][0] += 1; cells[cell][2] = i
            if i in key_indices or first_valid is None:
                keyframe={'frame':i,'stamp_ns':scan['stamp_ns'],
                    'raw_sequence':scan.get('raw_sequence'),
                    'elapsed_s':(scan['stamp_ns']-starts)/1e9,
                    'sensor_pose':sensor_local,'points':cloud}
                if first_valid is None:first_valid=keyframe
                if i in key_indices:keyframes.append(keyframe)
        except ValueError as exc:
            # Budget errors fail the whole operation, not partially mutate a map.
            if 'BUDGET' in str(exc): raise
            failures.append({'frame':i,'raw_sequence':scan.get('raw_sequence'),'reason':str(exc)})
    if not paired or sampled_hits == 0: raise ValueError('OBSERVATION_NO_PAIRED_RETURNS')
    if not keyframes:keyframes=[first_valid]
    endpoints = [[(x+.5)*.05,(y+.5)*.05,*v] for (x,y),v in sorted(cells.items())]
    stride = max(1,math.ceil(len(timeline.rows)/512))
    trace = [{'stamp_ns':r['stamp_ns'],'pose':compose(local_from_odom,p)}
             for r,p in zip(timeline.rows[::stride],timeline.poses[::stride])]
    xy = [p[:2] for p in endpoints]+[r['pose'][:2] for r in trace]
    bounds = [min(p[0] for p in xy)-.2,max(p[0] for p in xy)+.2,
              min(p[1] for p in xy)-.2,max(p[1] for p in xy)+.2]
    return {'schema':'session-observation-map-1.0','status':'DIAGNOSTIC_ODOM_PROJECTION',
            'coordinate_frame':'SESSION_START_ODOM_LOCAL_NOT_ROOM_OR_MAP',
            'odom_anchor_pose':anchor,'local_from_odom':local_from_odom,
            'cell_size_m':.05,'endpoint_cells':endpoints,'bounds_m':bounds,
            'keyframes':keyframes,'trajectory':trace,'timing':audit,
            'frame_count':n,'paired_frames':paired,'rejected_frames':len(failures),
            'failures':failures[:128],'empty_paired_frames':empty,
            'sampled_hits':sampled_hits,'max_points_per_scan':160,
            'display_range_m':8.,'beyond_display_range_returns':beyond,
            'playback':'UP_TO_64_UNIFORM_ORIGINAL_KEYFRAMES_NOT_FULL_RAW_STREAM',
            'free_space_inferred':False,'photo_geometry_used':False,
            'pose_correction_applied':False,'alignment_verified':False,
            'motion_authorized':False,'physical_demo_ready':False}
