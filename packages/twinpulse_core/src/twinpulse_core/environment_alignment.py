# SPDX-License-Identifier: Apache-2.0
"""Bounded, operator-initialized structural review. NEVER motion authority.

Fit indices are fixed before optimization. Held-out returns are not trimmed or
reselected. A local geometric result is not surveyed scale/body qualification.
"""
import math
import time
from .environment_section import horizontal_section
from .environment_source import mesh_points
from .revisions import canonical_sha256
from .room_localization import angle,compose
from .lidar_geometry import SectionIndex

LIMITS=dict(search_xy_m=.35,search_yaw_rad=.35,mean_error_m=.12,inlier_distance_m=.15,
    minimum_inlier_fraction=.70,maximum_reference_ratio_error=.02,minimum_normal_diversity=.06,
    minimum_validation_returns=12,minimum_fit_returns=24)

def finite_pose(value):
    if not isinstance(value,list) or len(value)!=3 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>100 for n in value):
        raise ValueError('ALIGNMENT_POSE_INVALID')
    return [float(value[0]),float(value[1]),angle(value[2])]

def wall_references(environment):
    result=[]
    for mesh in environment['meshes']:
        if mesh['category']!='wall':continue
        points=sorted({tuple(p[:2]) for p in mesh_points(mesh)})
        if not 2<=len(points)<=512:continue
        a,b=max(((a,b) for a in points for b in points),key=lambda pair:math.dist(*pair))
        if math.dist(a,b)<.3:continue
        result.append(dict(id=mesh['id'],label=mesh['label'],ends_m=[list(a),list(b)],length_m=math.dist(a,b)))
    return result

def reference_check(environment,reference_id,measured_m,basis):
    ref=next((r for r in wall_references(environment) if r['id']==reference_id),None)
    if not ref:raise ValueError('ALIGNMENT_REFERENCE_WALL_REQUIRED')
    if basis not in {'SIM_ONLY','OPERATOR_REFERENCE'}:raise ValueError('ALIGNMENT_REFERENCE_BASIS')
    if type(measured_m) not in (int,float) or not math.isfinite(measured_m) or not .3<=measured_m<=20:
        raise ValueError('ALIGNMENT_REFERENCE_LENGTH')
    ratio=measured_m/ref['length_m']
    return dict(**ref,basis=basis,reported_length_m=measured_m,ratio=ratio,
        status='REFERENCE_CONSISTENT' if abs(ratio-1)<=LIMITS['maximum_reference_ratio_error'] else 'SCALE_MISMATCH',
        whole_scene_scale_verified=False,original_units_basis=environment['units_basis'])

def body_points(points,extrinsic,angle_sign=1):
    transform=finite_pose(extrinsic)
    if angle_sign not in (-1,1) or not isinstance(points,list) or not 40<=len(points)<=4096:
        raise ValueError('ALIGNMENT_SCAN_BOUND')
    if any(not isinstance(p,list) or len(p)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>100 for n in p) for p in points):
        raise ValueError('ALIGNMENT_SCAN_INVALID')
    # This is the sole raw laser -> canonical body normalization.
    return [compose(transform,[p[0],angle_sign*p[1],0])[:2] for p in points]

def fixed_split(points,indices=None):
    # Uniform ORIGINAL return indices; never interpolate missing rays.
    original=list(range(len(points))) if indices is None else sorted(set(indices))
    if not original or any(type(i) is not int or not 0<=i<len(points) for i in original):raise ValueError('ALIGNMENT_ORIGINAL_INDICES')
    ids=[original[i*len(original)//min(150,len(original))] for i in range(min(150,len(original)))]
    return ([i for j,i in enumerate(ids) if j%3!=2],[i for j,i in enumerate(ids) if j%3==2])

class StructuralMatcher:
    def __init__(self,environment,height_m,wall_ids):
        if not isinstance(wall_ids,list) or not wall_ids or len(set(wall_ids))!=len(wall_ids):raise ValueError('ALIGNMENT_WALL_IDS')
        allowed={r['id'] for r in wall_references(environment)}
        if not set(wall_ids)<=allowed:raise ValueError('ALIGNMENT_WALL_IDS')
        section=horizontal_section(environment,height_m)
        self.segments=[s for s in section['segments'] if s['category']=='wall' and s['object_id'] in wall_ids]
        if not 4<=len(self.segments)<=1024:raise ValueError('ALIGNMENT_SECTION_BOUND')
        self.geometry_sha256=canonical_sha256(self.segments)
        self.wall_index=SectionIndex([s['ends_m'] for s in self.segments])
        self.nonwall_index=SectionIndex([s['ends_m'] for s in section['segments'] if s['category']!='wall'])
        self.items=[];self.grid={};self.cell=.4
        for segment in self.segments:
            a,b=segment['ends_m'];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length<1e-6:continue
            index=len(self.items);self.items.append((a,b,dx,dy,length,-dy/length,dx/length))
            for ix in range(math.floor(min(a[0],b[0])/self.cell)-1,math.floor(max(a[0],b[0])/self.cell)+2):
                for iy in range(math.floor(min(a[1],b[1])/self.cell)-1,math.floor(max(a[1],b[1])/self.cell)+2):
                    self.grid.setdefault((ix,iy),[]).append(index)

    def nearest(self,x,y):
        best=None;distance=1.
        for index in self.grid.get((math.floor(x/self.cell),math.floor(y/self.cell)),[]):
            a,b,dx,dy,length,nx,ny=self.items[index]
            t=max(0.,min(1.,((x-a[0])*dx+(y-a[1])*dy)/(length*length)))
            d=math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
            if d<distance:distance=d;best=(nx*(x-a[0])+ny*(y-a[1]),nx,ny)
        return distance,best

    def score(self,points,ids,pose):
        c,s=math.cos(pose[2]),math.sin(pose[2]);errors=[];normals=[]
        for i in ids:
            u,v=points[i];d,pair=self.nearest(pose[0]+c*u-s*v,pose[1]+s*u+c*v)
            errors.append(d)
            if d<=.15 and pair is not None:normals.append(pair[1:])
        diversity=0.
        if normals:
            xx=sum(n[0]*n[0] for n in normals)/len(normals);yy=1-xx;xy=sum(n[0]*n[1] for n in normals)/len(normals)
            diversity=(1-math.sqrt(max(0.,(xx-yy)**2+4*xy*xy)))/2
        return dict(mean_error_m=sum(min(e,.5) for e in errors)/len(errors),
            inlier_fraction=sum(e<=.15 for e in errors)/len(errors),normal_diversity=diversity,count=len(ids))

    def structural_indices(self,raw_sensor_points,seed,extrinsic,angle_sign=1):
        """Freeze geometric visibility BEFORE reading errors/optimizing pose.

        Only ray direction is read from observations, NEVER observed range.
        Foreground unknown returns remain errors, not discarded as clutter.
        """
        sensor=compose(finite_pose(seed),finite_pose(extrinsic));selected=[]
        for p in raw_sensor_points:
            bearing=math.atan2(angle_sign*p[1],p[0])+sensor[2]
            direction=(math.cos(bearing),math.sin(bearing))
            wall=self.wall_index.cast(sensor[:2],direction,20.)
            foreground=self.nonwall_index.cast(sensor[:2],direction,20.)
            selected.append(wall<19.99 and wall+.25<foreground)
        # Erode transitions in original angular order to avoid map silhouette
        # edges becoming a range-dependent ROI. No ray is synthesized.
        indices=[i for i in range(len(selected)) if all(selected[(i+d)%len(selected)] for d in (-2,-1,0,1,2))]
        return dict(indices=indices,total_returns=len(raw_sensor_points),excluded_count=len(raw_sensor_points)-len(indices),
            initial_pose=list(seed),sensor_extrinsic=list(extrinsic),basis='PRE_FIT_MAP_VISIBILITY_FROM_RAY_DIRECTION_ONLY',
            foreground_clearance_m=.25,edge_erosion_returns=2,geometry_sha256=self.geometry_sha256,
            original_indices_sha256=canonical_sha256(indices))

    def range_score(self,raw,ids,pose,extrinsic,angle_sign=1):
        """First visible wall, not the closest arbitrary wall face to a return."""
        sensor=compose(pose,extrinsic);errors=[];missing=occluded=0
        for i in ids:
            p=raw[i];bearing=math.atan2(angle_sign*p[1],p[0])+sensor[2]
            direction=(math.cos(bearing),math.sin(bearing));predicted=self.wall_index.cast(sensor[:2],direction,20.)
            foreground=self.nonwall_index.cast(sensor[:2],direction,20.)
            no_hit=predicted>=19.99;blocked=foreground+1e-6<predicted
            missing+=no_hit;occluded+=blocked
            errors.append(.5 if no_hit or blocked else abs(predicted-math.hypot(*p)))
        return dict(first_hit_mean_error_m=sum(min(e,.5) for e in errors)/len(errors),
            first_hit_inlier_fraction=sum(e<=.15 for e in errors)/len(errors),missing_wall_hits=missing,foreground_occlusions=occluded)

    def validation(self,points,ids,pose,raw,extrinsic,angle_sign=1):
        if not ids:raise ValueError('ALIGNMENT_VALIDATION_COVERAGE')
        return dict(**self.score(points,ids,pose),**self.range_score(raw,ids,pose,extrinsic,angle_sign))

    def fit(self,points,seed,*,raw_sensor_points,extrinsic,angle_sign=1,initial=True,deadline=None,indices=None):
        seed=finite_pose(seed);train,test=fixed_split(points,indices);deadline=deadline or time.monotonic()+2.
        if len(test)<12 or len(train)<24:raise ValueError('ALIGNMENT_HELDOUT_COUNT')
        if len(raw_sensor_points)!=len(points):raise ValueError('ALIGNMENT_RAW_PAIRING')
        extrinsic=finite_pose(extrinsic)
        def objective(pose):
            if time.monotonic()>deadline:raise ValueError('ALIGNMENT_COMPUTE_DEADLINE')
            return self.range_score(raw_sensor_points,train,pose,extrinsic,angle_sign)['first_hit_mean_error_m']
        candidates=[];offsets=(-.2,0.,.2) if initial else (0.,)
        for dx in offsets:
            for dy in offsets:
                for da in ((-.16,0.,.16) if initial else (-.08,0.,.08)):
                    pose=[seed[0]+dx,seed[1]+dy,angle(seed[2]+da)]
                    candidates.append((objective(pose),pose))
        candidates.sort(key=lambda v:v[0]);refined=[]
        for _,candidate in candidates[:3 if initial else 1]:
            pose=list(candidate)
            score=objective(pose)
            # Bounded deterministic search; only the fixed FIT returns select a
            # pose. Range errors are never used to trim/reselect the ROI.
            for step in ((.10,.05,.025,.0125,.00625,.003125,.0015625) if initial else (.025,.0125,.00625,.003125,.0015625)):
                for _ in range(3 if initial else 2):
                    best=(score,pose)
                    for axis in range(3):
                        for direction in (-1,1):
                            proposed=list(pose);proposed[axis]+=direction*step;proposed[2]=angle(proposed[2])
                            if math.dist(seed[:2],proposed[:2])>LIMITS['search_xy_m'] or abs(angle(proposed[2]-seed[2]))>LIMITS['search_yaw_rad']:continue
                            cost=objective(proposed)
                            if cost<best[0]-1e-10:best=(cost,proposed)
                    if best[1] is pose:break
                    score,pose=best
            refined.append((score,pose))
        refined.sort(key=lambda v:v[0]);pose=refined[0][1]
        # Selection above NEVER reads held-out scores.
        validation=self.validation(points,test,pose,raw_sensor_points,extrinsic,angle_sign)
        good=self.passes(validation)
        rival=next((p for score,p in [*refined[1:],*candidates] if score<=refined[0][0]+.01 and (math.dist(p[:2],pose[:2])>.10 or abs(angle(p[2]-pose[2]))>.10)),None)
        return dict(status='AMBIGUOUS' if good and rival is not None else 'GEOMETRIC_REVIEW' if good else 'HELD',body_pose=pose,
            fit=self.validation(points,train,pose,raw_sensor_points,extrinsic,angle_sign),validation=validation,fit_indices=train,validation_indices=test,
            split_sha256=canonical_sha256(dict(fit=train,validation=test)),geometry_sha256=self.geometry_sha256,
            limits=LIMITS,initial_pose=seed,physical_authority=False,world_registration_verified=False,
            refined_candidates=[dict(train_first_hit_error_m=cost,body_pose=p) for cost,p in refined],
            refinement_count=len(refined),uniqueness_scope='BOUNDED_LOCAL_REFINEMENTS_NOT_GLOBAL_UNIQUENESS',
            method='OPERATOR_SEEDED_FIRST_VISIBLE_WALL_RANGE_1')

    @staticmethod
    def passes(score):return (score['count']>=LIMITS['minimum_validation_returns'] and score['mean_error_m']<=LIMITS['mean_error_m']
        and score['inlier_fraction']>=LIMITS['minimum_inlier_fraction'] and score['normal_diversity']>=LIMITS['minimum_normal_diversity']
        and score.get('first_hit_mean_error_m',0)<=LIMITS['mean_error_m']
        and score.get('first_hit_inlier_fraction',1)>=LIMITS['minimum_inlier_fraction'])

def solve(matrix,rhs):
    rows=[list(a)+[b] for a,b in zip(matrix,rhs)];scale=max(abs(v) for r in matrix for v in r)
    for i in range(3):
        pivot=max(range(i,3),key=lambda j:abs(rows[j][i]))
        if abs(rows[pivot][i])<max(1e-9,scale*1e-7):return None
        rows[i],rows[pivot]=rows[pivot],rows[i];v=rows[i][i];rows[i]=[n/v for n in rows[i]]
        for j in range(3):
            if j!=i:
                v=rows[j][i];rows[j]=[a-v*b for a,b in zip(rows[j],rows[i])]
    return [r[3] for r in rows]
