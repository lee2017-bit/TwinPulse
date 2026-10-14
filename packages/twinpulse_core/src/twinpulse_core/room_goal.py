# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit metric Twin/odom correspondences, never execution calibration.

Rigid SE(2), no reflection/scale fitting or photo-derived defaults. Fit quality
does not authenticate reference points, odometry or the approximate room scale.
"""
import itertools
import math
import re
from .revisions import canonical_sha256


def xy(value):
    if (type(value) is not list or len(value)!=2 or
        any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>100 for x in value)):
        raise ValueError('METRIC_XY_REQUIRED')
    return tuple(value)


def room_goal_preview(goal, reference, *, scene_revision, evidence_revision):
    point=xy(goal)
    result={'schema':'room-goal-preview-1.0','scene_revision':scene_revision,
        'evidence_revision':evidence_revision,'twin_goal_xy_m':list(point),
        'odom_goal_candidate_m':None,'twin_to_odom_candidate':None,
        'status':'MISSING_METRIC_REFERENCE','alignment_verified':False,
        'motion_authorized':False,'physical_validation':'NOT_RUN'}
    if reference is None:return result
    fields={'schema','scene_revision','evidence_revision','boot_id','basis','pairs'}
    if type(reference) is not dict or set(reference)!=fields:raise ValueError('REFERENCE_SHAPE')
    if (reference['schema']!='twin-odom-reference-1.0' or reference['scene_revision']!=scene_revision
        or reference['evidence_revision']!=evidence_revision):raise ValueError('REFERENCE_CONTEXT_CHANGED')
    if reference['basis'] not in {'operator_supplied_metric_reference','synthetic_test_fixture'}:
        raise ValueError('METRIC_REFERENCE_REQUIRED_NOT_PHOTO')
    if not isinstance(reference['boot_id'],str) or not re.fullmatch('[a-zA-Z0-9-]{1,64}',reference['boot_id']):
        raise ValueError('BOOT_ID_REQUIRED')
    pairs=reference['pairs']
    if type(pairs) is not list or not 3<=len(pairs)<=16:raise ValueError('THREE_TO_SIXTEEN_PAIRS_REQUIRED')
    source=[];target=[]
    for pair in pairs:
        if type(pair) is not dict or set(pair)!={'twin_xy_m','odom_xy_m'}:raise ValueError('PAIR_SHAPE')
        source.append(xy(pair['twin_xy_m']));target.append(xy(pair['odom_xy_m']))
    def area(points):
        return max(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
                   for a,b,c in itertools.combinations(points,3))
    if (len(set(source))!=len(source) or len(set(target))!=len(target)
        or min(area(source),area(target))<.01):raise ValueError('DEGENERATE_REFERENCE_GEOMETRY')
    # Require all pair distances to agree: neither scale nor shear is absorbed.
    if any(abs(math.dist(source[a],source[b])-math.dist(target[a],target[b]))>.05
           for a,b in itertools.combinations(range(len(source)),2)):
        raise ValueError('REFERENCE_SCALE_OR_DISTANCE_MISMATCH')
    sx,sy=[sum(p[i] for p in source)/len(source) for i in (0,1)]
    tx,ty=[sum(p[i] for p in target)/len(target) for i in (0,1)]
    dot=sum((p[0]-sx)*(q[0]-tx)+(p[1]-sy)*(q[1]-ty) for p,q in zip(source,target))
    cross=sum((p[0]-sx)*(q[1]-ty)-(p[1]-sy)*(q[0]-tx) for p,q in zip(source,target))
    if math.hypot(dot,cross)<1e-12:raise ValueError('DEGENERATE_ROTATION')
    angle=math.atan2(cross,dot);c,s=math.cos(angle),math.sin(angle)
    dx,dy=tx-c*sx+s*sy,ty-s*sx-c*sy
    def convert(p):return [c*p[0]-s*p[1]+dx,s*p[0]+c*p[1]+dy]
    residuals=[math.dist(convert(p),q) for p,q in zip(source,target)]
    if max(residuals)>.05:raise ValueError('REFERENCE_RESIDUAL_OR_REFLECTION')
    converted=convert(point)
    if any(abs(v)>10 for v in converted):raise ValueError('GOAL_OUTSIDE_MISSION_COORDINATE_LIMIT')
    return {**result,'status':'CANDIDATE_ONLY_NOT_CALIBRATED',
        'odom_goal_candidate_m':converted,'twin_to_odom_candidate':{'x_m':dx,'y_m':dy,'yaw_rad':angle},
        'reference_sha256':canonical_sha256(reference),'boot_id':reference['boot_id'],
        'basis':reference['basis'],'max_residual_m':max(residuals),
        'reference_verified':False,'current_boot_verified':False}
