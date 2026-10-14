# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Held-out sensor-map matching, independent of photo boxes and old pose.

Endpoint evidence is NOT occupancy or free space. Reference projection and
query deskew use declared scan timing and nominal mounting, not calibration.
"""
import heapq
import math
from .revisions import canonical_sha256
from .room_localization import RoomMatcher, angle, compose, inverse, deskew
from .scan_observation import build_observation_map


class EndpointMatcher(RoomMatcher):
    """Existing bounded global search over a chamfer endpoint distance field."""
    def __init__(self, reference, *, interpolate=False):
        if type(interpolate) is not bool:raise ValueError('SENSOR_MAP_FIELD_SAMPLING_INVALID')
        # Existing saved/replay scores retain nearest-cell sampling by default.
        # Current mission tracking opts into continuous sampling of the SAME
        # field; no new endpoints, cells or free space are invented.
        self.interpolate=interpolate
        points=reference['endpoint_cells'];self.bounds=reference['bounds_m'];self.cell=.06
        if not 24 <= len(points) <= 18000:raise ValueError('SENSOR_MAP_ENDPOINT_BUDGET')
        if len(self.bounds)!=4 or not all(math.isfinite(v) and abs(v)<=31 for v in self.bounds):
            raise ValueError('SENSOR_MAP_BOUNDS_INVALID')
        x0,x1,y0,y1=self.bounds
        if x1<=x0 or y1<=y0:raise ValueError('SENSOR_MAP_BOUNDS_INVALID')
        self.x0,self.y0=x0-.5,y0-.5
        self.nx=math.ceil((x1-x0+1)/self.cell)+1;self.ny=math.ceil((y1-y0+1)/self.cell)+1
        if self.nx*self.ny>60000:raise ValueError('SENSOR_MAP_DISTANCE_FIELD_BUDGET')
        if math.ceil((x1-x0)/.2)*math.ceil((y1-y0)/.2)*36>150000:
            raise ValueError('GLOBAL_SEARCH_BUDGET')
        self.outline={'bounds_m':self.bounds,'solids':[]};self.field=[.5]*(self.nx*self.ny);queue=[]
        for p in points:
            if len(p)<2 or not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=30 for v in p[:2]):
                raise ValueError('SENSOR_MAP_ENDPOINT_INVALID')
            ix,iy=round((p[0]-self.x0)/self.cell),round((p[1]-self.y0)/self.cell)
            if not (0<=ix<self.nx and 0<=iy<self.ny):raise ValueError('SENSOR_MAP_ENDPOINT_OUTSIDE_FIELD')
            index=iy*self.nx+ix
            if self.field[index]:self.field[index]=0.;heapq.heappush(queue,(0.,index))
        while queue:
            distance,index=heapq.heappop(queue)
            if distance!=self.field[index]:continue
            y,x=divmod(index,self.nx)
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                nx,ny=x+dx,y+dy
                if not 0<=nx<self.nx or not 0<=ny<self.ny:continue
                candidate=distance+self.cell*(math.sqrt(2) if dx and dy else 1)
                next_index=ny*self.nx+nx
                if candidate<self.field[next_index]:
                    self.field[next_index]=candidate;heapq.heappush(queue,(candidate,next_index))

    def score(self,points,pose):
        if not self.interpolate:return super().score(points,pose)
        c,s=math.cos(pose[2]),math.sin(pose[2]);errors=[]
        for px,py in points:
            x=(pose[0]+c*px-s*py-self.x0)/self.cell
            y=(pose[1]+s*px+c*py-self.y0)/self.cell
            if not 0<=x<=self.nx-1 or not 0<=y<=self.ny-1:
                errors.append(1.);continue
            ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy
            jx,jy=min(ix+1,self.nx-1),min(iy+1,self.ny-1)
            lo=(1-fx)*self.field[iy*self.nx+ix]+fx*self.field[iy*self.nx+jx]
            hi=(1-fx)*self.field[jy*self.nx+ix]+fx*self.field[jy*self.nx+jx]
            errors.append((1-fy)*lo+fy*hi)
        # Keep original cap/inlier threshold and count every sampled return.
        return sum(min(v,.5) for v in errors)/len(errors),sum(v<=.15 for v in errors)/len(errors)


def locate_in_sensor_map(reference_evidence, query_evidence, frame, reference_offset, query_offset, *, matcher_factory=EndpointMatcher):
    queries=query_evidence['scans'];scans=reference_evidence['scans']
    if type(frame) is not int or not 0<=frame<len(queries):raise ValueError('QUERY_SCAN_FRAME_NOT_RECORDED')
    if len(queries)<3:raise ValueError('QUERY_THREE_SCANS_REQUIRED')
    if queries[frame]['frame_id']!='base_scan' or any(s['frame_id']!='base_scan' for s in scans):
        raise ValueError('NOMINAL_SCAN_FRAME_UNSUPPORTED')
    start=max(0,min(frame-1,len(queries)-3));indices=list(range(start,start+3))
    selected=[queries[i] for i in indices]
    if any(s['frame_id']!='base_scan' for s in selected):raise ValueError('NOMINAL_SCAN_FRAME_UNSUPPORTED')
    if selected[-1]['stamp_ns']-selected[0]['stamp_ns']>1_000_000_000:
        raise ValueError('QUERY_MULTIFRAME_TIME_GAP')
    # Hold out entire beam intervals, not just a frame's declared first stamp.
    lo=selected[0]['stamp_ns']-2_000_000_000
    hi=max(s['stamp_ns']+round((len(s['ranges_m'])-1)*s['time_increment']*1e9) for s in selected)+2_000_000_000
    shared=(reference_evidence['source_revision']==query_evidence['source_revision'] or
            reference_evidence['boot_id']==query_evidence['boot_id'])
    excluded=[];retained=[];retained_indices=[]
    for i,scan in enumerate(scans):
        end=scan['stamp_ns']+round((len(scan['ranges_m'])-1)*scan['time_increment']*1e9)
        if shared and scan['stamp_ns']<=hi and end>=lo:excluded.append(i)
        else:retained.append(scan);retained_indices.append(i)
    if len(retained)<3:raise ValueError('REFERENCE_TOO_SMALL_AFTER_QUERY_HOLDOUT')
    reference=build_observation_map(retained,reference_evidence['timeline'],reference_offset)
    # Filtered-list indices must never masquerade as original recording indices.
    reference['failures']=[dict(r,frame=retained_indices[r['frame']]) for r in reference['failures']]
    reference['endpoint_cells']=[[*p[:3],retained_indices[p[3]],retained_indices[p[4]]] for p in reference['endpoint_cells']]
    query_frames=[]
    for index in indices:
        scan=queries[index]
        clipped={**scan,'ranges_m':[None if v is not None and v>8. else v for v in scan['ranges_m']]}
        points,pose=deskew(clipped,query_evidence['timeline'],query_offset)
        if not 24<=len(points)<=160:raise ValueError('QUERY_SCAN_MATCH_POINT_BUDGET')
        query_frames.append({'frame':index,'raw_sequence':scan.get('raw_sequence'),'stamp_ns':scan['stamp_ns'],
                             'points':points,'sensor_pose_query_odom':pose})
    central=next(k for k in query_frames if k['frame']==frame)
    matcher=matcher_factory(reference);seed=matcher.match(central['points'])
    candidates=seed.get('alternatives',[]) or ([seed] if seed.get('pose') else [])
    ranked=[]
    for candidate in candidates[:4]:
        transform=compose(candidate['pose'],inverse(central['sensor_pose_query_odom']))
        rows=[];error_sum=0.;hits=0
        for key in query_frames:
            pose=compose(transform,key['sensor_pose_query_odom']);error,inliers=matcher.score(key['points'],pose)
            supports=error<=.12 and inliers>=.70 and matcher.possible(pose)
            rows.append({'frame':key['frame'],'capped_mean_endpoint_error_m':error,'within_15cm_fraction':inliers,
                         'supports_same_transform':supports,'sensor_pose_reference_candidate':pose})
            error_sum+=error*len(key['points']);hits+=len(key['points'])
        ranked.append({'sensor_pose_reference_candidate':candidate['pose'],
            'reference_from_query_odom_candidate':transform,'weighted_capped_mean_error_m':error_sum/hits,
            'supported_query_frames':sum(r['supports_same_transform'] for r in rows),'frames':rows})
    ranked.sort(key=lambda c:c['weighted_capped_mean_error_m']);best=ranked[0] if ranked else None
    rival=next((c for c in ranked[1:] if math.dist(c['sensor_pose_reference_candidate'][:2],best['sensor_pose_reference_candidate'][:2])>.35 or
                abs(angle(c['sensor_pose_reference_candidate'][2]-best['sensor_pose_reference_candidate'][2]))>.30),None) if best else None
    margin=rival['weighted_capped_mean_error_m']-best['weighted_capped_mean_error_m'] if rival else None
    status='NO_SEARCH_HYPOTHESIS' if best is None else 'POOR_FIT'
    if best and best['supported_query_frames']==3:
        status='SENSOR_MAP_GEOMETRIC_CANDIDATE' if margin is not None and margin>=.025 else 'AMBIGUOUS'
    overlay=[]
    if best:
        for key in query_frames:
            pose=compose(best['reference_from_query_odom_candidate'],key['sensor_pose_query_odom'])
            overlay.append({'frame':key['frame'],'points':[compose(pose,[*p,0])[:2] for p in key['points']],
                            'sensor_pose_reference_candidate':pose})
    identity={'reference_source_revision':reference_evidence['source_revision'],'query_source_revision':query_evidence['source_revision'],
              'excluded_original_reference_frames':excluded,'query_frames':indices,'reference_offset':reference_offset,'query_offset':query_offset,
              'reference_endpoints_revision':canonical_sha256(reference['endpoint_cells'])}
    return {'schema':'sensor-map-localization-review-1.0','status':status,'frame':frame,'query_frames':indices,
            'seed_status':seed['status'],'best_diagnostic_hypothesis':best,'alternatives':ranked[1:4],
            'alternative_margin_m':margin,'reference_endpoint_cells':reference['endpoint_cells'],'bounds_m':reference['bounds_m'],
            'reference_map_revision':canonical_sha256(identity),'reference_original_scan_count':len(scans),
            'reference_retained_scan_count':len(retained),'reference_paired_scan_count':reference['paired_frames'],
            'reference_rejected_frames':reference['failures'],'reference_rejected_scan_count':reference['rejected_frames'],
            'holdout':{'basis':'DECLARED_BEAM_INTERVAL_PLUS_2_SECONDS_EACH_SIDE_SHARED_RAW_OR_BOOT',
                       'shared_source_or_boot':shared,'excluded_reference_frames':excluded,'declared_interval_ns':[lo,hi],
                       'direct_query_scan_reuse':False,'independent_physical_ground_truth':False},
            'query_provenance':[{'frame':k['frame'],'raw_sequence':k['raw_sequence'],'stamp_ns':k['stamp_ns']} for k in query_frames],
            'overlays':overlay,'coordinate_frame':'REFERENCE_SESSION_START_ODOM_LOCAL_NOT_PHOTO_ROOM',
            'search_prior':'NONE_NO_OLD_POSE_OR_ROUTE','sensor_model':'OBSERVED_ENDPOINTS_NOT_PHOTO_BOXES',
            'score_basis':'60MM_CHAMFER_DISTANCE_FIELD_500MM_CAP_NOT_POSE_ERROR',
            'query_odom_use':'DECLARED_TIME_DESKEW_AND_RELATIVE_THREE_FRAME_MOTION_NOT_GLOBAL_POSITION_PRIOR',
            'timing_verified':False,'as_built_mount_verified':False,'photo_geometry_used':False,'geometry_changed':False,
            'free_space_inferred':False,'room_transform_created':False,'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}
