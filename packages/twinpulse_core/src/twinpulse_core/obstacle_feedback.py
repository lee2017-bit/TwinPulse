# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Observed obstacle evidence over an editable photo prior.

The supplied sensor pose is an explicit estimate, not localization. Invalid
returns never clear space. Association does not follow from a furniture name.
"""
from copy import deepcopy
import math
import re
from time import monotonic

from .automatic_mapping import EvidenceGrid
from .revisions import canonical_sha256


def finite(value, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('OBSTACLE_OBSERVATION_NUMBER_INVALID')
    return float(value)


def checked_observation(value):
    if not isinstance(value, dict):raise ValueError('OBSTACLE_OBSERVATION_OBJECT_REQUIRED')
    attribution=deepcopy(value.get('source_attribution'))
    # A connection export includes its exact normalized sensor payload.
    if 'obstacle_observation' in value:
        if value.get('schema_version')=='robot-console-result-1.2':
            if value.get('sha256')!=canonical_sha256({k:v for k,v in value.items() if k!='sha256'}):
                raise ValueError('OBSTACLE_CONNECTION_EXPORT_CHANGED')
            attribution=dict(source_job_id=value.get('job_id'),source_execution_id=value.get('execution_id'),export_sha256=value['sha256'])
        value=value['obstacle_observation']
    if not isinstance(value, dict) or value.get('schema_version')!='obstacle-observation-1.0':
        raise ValueError('OBSTACLE_OBSERVATION_SCHEMA_INVALID')
    scans=value.get('scans')
    if not isinstance(scans, list) or not 1<=len(scans)<=16:
        raise ValueError('OBSTACLE_OBSERVATION_SCANS_REQUIRED')
    result=[]
    for scan in scans:
        if not isinstance(scan, dict):raise ValueError('OBSTACLE_SCAN_INVALID')
        stamp=scan.get('stamp_ns');frame=scan.get('frame_id')
        if type(stamp) is not int or not 0<stamp<2**63 or not isinstance(frame,str) or not 1<=len(frame)<=128:
            raise ValueError('OBSTACLE_SCAN_FRAME_OR_STAMP_INVALID')
        angle=finite(scan.get('angle_min_rad'),-math.tau,math.tau)
        step=finite(scan.get('angle_increment_rad'),1e-7,math.tau)
        lower=finite(scan.get('range_min_m'),.001,100)
        upper=finite(scan.get('range_max_m'),lower+.001,100)
        ranges=scan.get('ranges_m')
        if not isinstance(ranges,list) or not 2<=len(ranges)<=4096 or (len(ranges)-1)*step>math.tau+1e-5:
            raise ValueError('OBSTACLE_SCAN_RANGES_INVALID')
        ranges=[None if r is None else finite(r,lower,upper) for r in ranges]
        result.append(dict(stamp_ns=stamp,frame_id=frame,angle_min_rad=angle,
            angle_increment_rad=step,range_min_m=lower,range_max_m=upper,ranges_m=ranges))
    declared=value.get('provenance','IMPORTED_SENSOR')
    if declared not in {'SIMULATED_SENSOR','ROBOT_READ_ONLY','IMPORTED_SENSOR'}:
        raise ValueError('OBSTACLE_OBSERVATION_PROVENANCE_INVALID')
    if attribution is not None:
        if not isinstance(attribution,dict) or set(attribution)!={'source_job_id','source_execution_id','export_sha256'}:
            raise ValueError('OBSTACLE_ATTRIBUTION_INVALID')
        for key,size in (('source_job_id',24),('source_execution_id',32),('export_sha256',64)):
            if not isinstance(attribution[key],str) or not re.fullmatch('[a-f0-9]{'+str(size)+'}',attribution[key]):
                raise ValueError('OBSTACLE_ATTRIBUTION_INVALID')
    return dict(schema_version='obstacle-observation-1.0',provenance=declared,scans=result,source_attribution=attribution,
        provenance_verified=False,physical_authority=False)


def project_observation(observation, sensor_pose_m, scan_height_m):
    observation=checked_observation(observation)
    if not isinstance(sensor_pose_m,list) or len(sensor_pose_m)!=3:
        raise ValueError('OBSTACLE_SENSOR_POSE_REQUIRED')
    pose=[finite(v,-10 if i<2 else -math.pi,10 if i<2 else math.pi) for i,v in enumerate(sensor_pose_m)]
    height=finite(scan_height_m,.02,3)
    # A connection capture need not be stationary. Do not silently assign one
    # pose to several times: review the LAST individual original snapshot only.
    scan=observation['scans'][-1];points=[];rays=[]
    for index,distance in enumerate(scan['ranges_m']):
        if distance is None or distance>8:continue
        angle=pose[2]+scan['angle_min_rad']+index*scan['angle_increment_rad']
        end=[pose[0]+distance*math.cos(angle),pose[1]+distance*math.sin(angle)]
        if max(abs(v) for v in end)>12:continue
        points.append(end);rays.append((pose[:2],end))
    if not points:raise ValueError('OBSTACLE_OBSERVATION_NO_VALID_RETURNS')
    grid=EvidenceGrid();grid.insert(rays,scan['stamp_ns'],canonical_sha256(observation))
    cells=[[r[0],r[1],r[2]] for r in grid.rows()]
    return dict(sensor_pose_m=pose,scan_height_m=height,points=points,cells=cells,
        cell_size_m=.1,cell_coordinates='room_metres_cell_centres',
        occupied_count=sum(r[2]=='occupied' for r in cells),free_count=sum(r[2]=='free' for r in cells),
        unknown_count=sum(r[2]=='unknown' for r in cells),scan_count=len(observation['scans']),
        reviewed_scan_index=len(observation['scans'])-1,association='unassigned',
        coordinate_basis='USER_ESTIMATED_ROOM_FROM_SENSOR',alignment_verified=False,
        unobserved_space='unknown',physical_authority=False)


def _first_hit(origin,direction,half):
    if all(abs(origin[i])<=half[i] for i in (0,1)):return -1.
    near,far=0.,100.
    for i in (0,1):
        if abs(direction[i])<1e-10:
            if abs(origin[i])>half[i]:return None
            continue
        a=(-half[i]-origin[i])/direction[i];b=(half[i]-origin[i])/direction[i]
        near=max(near,min(a,b));far=min(far,max(a,b))
        if near>far:return None
    return near if far>=0 else None


def propose_translation(observation, boxes):
    """Conservative translation suggestions; ambiguous alternatives stay HELD.

    Fitting observed surfaces cannot establish object identity or hidden volume.
    The caller must still validate the entire dependency edit before Apply.
    """
    height=observation['scan_height_m'];points=observation['points']
    boxes=[b for b in boxes if b.get('collision') is True and b['shape']['type']=='box'
        and b['transform']['position_m'][2]-b['shape']['dimensions_m'][2]/2<=height
        <=b['transform']['position_m'][2]+b['shape']['dimensions_m'][2]/2]
    if not boxes:return dict(status='HELD',reason='NO_TARGET_GEOMETRY_AT_SCAN_HEIGHT')
    # Sample original endpoints, never clear or delete the underlying evidence.
    all_points=points;points=points[::max(1,math.ceil(len(points)/180))];options=[]
    sensor=observation['sensor_pose_m'];rays=[];prepared=[]
    for box in boxes:
        t=box['transform'];yaw=math.radians(t['rotation_rpy_deg'][2])
        prepared.append((t['position_m'],box['shape']['dimensions_m'],math.cos(yaw),math.sin(yaw)))
    for point in all_points:
        dx=point[0]-sensor[0];dy=point[1]-sensor[1];distance=math.hypot(dx,dy)
        if distance>1e-6:rays.append((distance,[(c*dx/distance+s*dy/distance,-s*dx/distance+c*dy/distance)
            for centre,size,c,s in prepared]))
    all_rays=rays;rays=rays[::max(1,math.ceil(len(rays)/180))]
    final_deadline=monotonic()+2.
    def score(delta,rows=None):
        origins=[]
        for centre,size,c,s in prepared:
            dx=sensor[0]-centre[0]-delta[0];dy=sensor[1]-centre[1]-delta[1]
            origin=(c*dx+s*dy,-s*dx+c*dy);half=(size[0]/2,size[1]/2)
            if all(abs(origin[i])<=half[i] for i in (0,1)):return None
            origins.append((origin,half))
        matched=[];contradictions=0
        for index,(measured,directions) in enumerate(rays if rows is None else rows):
            if index%64==0 and monotonic()>final_deadline:return [],-1
            hits=[_first_hit(o,d,h) for (o,h),d in zip(origins,directions)]
            hits=[h for h in hits if h is not None]
            if not hits:continue
            predicted=min(hits);residual=abs(predicted-measured)
            if predicted<measured-.08:contradictions+=1
            elif residual<=.06:matched.append(residual)
        return matched,contradictions
    deadline=monotonic()+1.5
    for ix in range(-10,11):
        for iy in range(-10,11):
            if monotonic()>deadline:return dict(status='HELD',reason='TRANSLATION_SEARCH_TIME_BUDGET; evidence retained; use an explicit draft translation')
            delta=[ix*.2,iy*.2]
            scored=score(delta)
            if scored is None:continue
            matched,contradictions=scored
            if contradictions==0 and len(matched)>=5:
                options.append((len(matched),sum(matched)/len(matched),math.hypot(*delta),delta))
    if not options:return dict(status='HELD',reason='NO_SUPPORTED_TRANSLATION; select correspondences or enter an explicit draft translation')
    options.sort(key=lambda r:(-r[0],r[1],r[2]));best=options[0]
    rivals=[r for r in options[1:] if math.dist(r[3],best[3])>.25 and r[0]>=best[0]*.9 and r[1]<=best[1]+.02]
    fit=dict(matched_endpoints=best[0],mean_surface_residual_m=best[1],competing_translations=len(rivals),
        semantic_identity_verified=False,hidden_geometry_verified=False,search_step_m=.2,
        observed_free_ray_contradictions=0,first_intersection_checked=True)
    before=score([0,0]);fit['before']=dict(matched_endpoints=len(before[0]),observed_free_ray_contradictions=before[1]) if before is not None else dict(sensor_inside_target=True)
    if rivals:return dict(status='HELD',reason='AMBIGUOUS_OBSTACLE_ASSOCIATION',fit=fit)
    if best[2]<.05:return dict(status='HELD',reason='NO_MATERIAL_TRANSLATION',fit=fit)
    full=score(best[3],all_rays)
    if full is None or full[1]!=0:
        return dict(status='HELD',reason='FULL_RAY_VALIDATION_TIME_BUDGET' if full is not None and full[1]<0 else 'FULL_OBSERVATION_FREE_RAY_CONTRADICTION',fit=fit)
    fit.update(full_valid_endpoints_checked=len(all_rays),total_valid_endpoints=len(all_rays),
        full_matched_endpoints=len(full[0]),observed_free_ray_contradictions=full[1])
    return dict(status='candidate',reason='Surface-supported draft translation; identity and sensor pose remain estimates',
        translation_xy_m=best[3],fit=fit)
