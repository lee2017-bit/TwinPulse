# SPDX-License-Identifier: Apache-2.0
"""Multi-position collection review; geometric estimates, never motor authority.

All temporal views are fixed before fitting. Odom-relative motion is explicit;
separate views sharing odometry/nominal TF are not independent ground truth.
"""
from copy import deepcopy
import math,time
from .environment_alignment import StructuralMatcher,body_points,finite_pose,wall_references,reference_check
from .environment_section import horizontal_section
from .environment_overlays import overlay_meshes
from .lidar_geometry import SectionIndex
from .revisions import canonical_sha256
from .room_localization import compose,inverse,angle

SCHEMA='environment-survey-review-1.0'


def checked_frames(frames):
    if not isinstance(frames,list) or not 3<=len(frames)<=512:raise ValueError('SURVEY_THREE_DISTINCT_VIEWS_REQUIRED')
    identities=set();source=None
    for f in frames:
        if not isinstance(f,dict) or not {'identity','points','local_pose','native_pose','extrinsic','source_owner','source_sha256','stamp','source_kind'}<=set(f):
            raise ValueError('SURVEY_FRAME_SHAPE')
        key=canonical_sha256(f['identity'])
        if key in identities:raise ValueError('SURVEY_DUPLICATE_ACQUISITION')
        identities.add(key)
        finite_pose(f['local_pose']);finite_pose(f['native_pose']);finite_pose(f['extrinsic'])
        body_points(f['points'],f['extrinsic'])
        if type(f['stamp']) not in (int,float) or not math.isfinite(f['stamp']):raise ValueError('SURVEY_ORIGINAL_TIME_REQUIRED')
        current=(f['source_owner'],f['source_kind'],f['extrinsic'],f.get('pose_epoch'),f.get('config_sha256'))
        if source is None:source=current
        if current!=source:raise ValueError('SURVEY_SOURCE_OR_TF_CHANGED')
    return deepcopy(frames)


def review_collection(environment,frames,initial_pose,reference_id,reference_length_m,reference_basis,height_m,*,cancel=lambda:False):
    frames=checked_frames(frames);seed=finite_pose(initial_pose)
    reference=reference_check(environment,reference_id,reference_length_m,reference_basis)
    if frames[0]['source_kind']=='PHYSICAL' and reference_basis!='OPERATOR_REFERENCE':raise ValueError('SURVEY_PHYSICAL_REFERENCE_REQUIRED')
    matcher=StructuralMatcher(environment,height_m,[r['id'] for r in wall_references(environment)])
    first=frames[0];first_local=finite_pose(first['local_pose']);native_origin=finite_pose(first['native_pose'])
    # Freeze every direction-only visibility selection from the caller seed and
    # original relative poses, before looking at any fit/validation residual.
    initial_from_local=compose(seed,inverse(first_local))
    selections=[matcher.structural_indices(f['points'],compose(initial_from_local,f['local_pose']),f['extrinsic']) for f in frames]
    if cancel():raise ValueError('SURVEY_REVIEW_CANCELLED')
    fit=matcher.fit(body_points(first['points'],first['extrinsic']),seed,raw_sensor_points=first['points'],
        extrinsic=first['extrinsic'],indices=selections[0]['indices'],deadline=time.monotonic()+5.)
    world_from_local=compose(fit['body_pose'],inverse(first_local));world_from_native=compose(fit['body_pose'],inverse(native_origin))
    validations=[];world_poses=[]
    for i,(frame,selection) in enumerate(zip(frames,selections)):
        if cancel():raise ValueError('SURVEY_REVIEW_CANCELLED')
        pose=compose(world_from_local,frame['local_pose']);world_poses.append(pose)
        try:score=matcher.validation(body_points(frame['points'],frame['extrinsic']),selection['indices'],pose,frame['points'],frame['extrinsic'])
        except ValueError:score=None
        validations.append(dict(frame_index=i,frame_identity=frame['identity'],local_pose=frame['local_pose'],world_pose=pose,
            selection_sha256=canonical_sha256(selection),score=score,passes=bool(score and matcher.passes(score))))
    good=(reference['status']=='REFERENCE_CONSISTENT' and fit['status']=='GEOMETRIC_REVIEW' and all(v['passes'] for v in validations[1:]))
    travelled=max(math.dist(f['local_pose'][:2],first_local[:2]) for f in frames)
    result=dict(schema=SCHEMA,status='GEOMETRIC_REVIEW' if good else 'HELD',reference=reference,match=fit,
        world_from_local=world_from_local,world_from_native=world_from_native,first_native_pose=native_origin,
        frame_validations=validations,pre_fit_selections=selections,frames_sha256=canonical_sha256(frames),
        view_count=len(frames),maximum_view_baseline_m=travelled,height_m=height_m,
        sensor_height_basis='EXPLICIT_NOMINAL_PLANE_NOT_AS_BUILT',physical_authority=False,world_registration_verified=False,
        pose_basis='WHEEL_RELATIVE_GEOMETRIC_REVIEW' if first['source_kind']=='PHYSICAL' else 'SIM_KINEMATIC_GEOMETRIC_REVIEW',
        whole_room_coverage_verified=False,geometry_changed=False)
    result['obstacle_candidates']=residual_candidates(environment,frames,world_poses,validations,height_m,cancel=cancel) if good else []
    return result


def residual_candidates(environment,frames,world_poses,validations,height_m,*,cancel=lambda:False):
    """Closer-than-model returns with multiple original frames/viewpoints.

    Endpoints are observed only at this plane. Height/full extent and photo
    class association remain explicit review estimates, never inferred facts.
    """
    env=deepcopy(environment);env['meshes']+=overlay_meshes(environment)
    # overlay meshes are valid review geometry but not a different imported
    # source contract. Slice parts independently rather than revalidate IDs.
    from .lidar_geometry import slice_triangle
    from .environment_source import mesh_points
    segments=[]
    for mesh in env['meshes']:
        if mesh['category'] in {'floor','window'} or mesh.get('synthetic_keepout'):continue
        vertices=mesh_points(mesh)
        for t in mesh['triangles']:segments.extend(slice_triangle([vertices[i] for i in t],height_m))
    index=SectionIndex(segments);cells={};rows=[]
    for frame_id,(frame,pose,validation) in enumerate(zip(frames,world_poses,validations)):
        if cancel():raise ValueError('SURVEY_REVIEW_CANCELLED')
        if not validation['passes']:continue
        sensor=compose(pose,frame['extrinsic'])
        for point_id,(u,v) in enumerate(frame['points']):
            distance=math.hypot(u,v)
            if not .08<=distance<=8.:continue
            bearing=math.atan2(v,u)+sensor[2];direction=[math.cos(bearing),math.sin(bearing)]
            predicted=index.cast(sensor[:2],direction,10.)
            if predicted>=9.99 or predicted-distance<.18:continue
            hit=[sensor[0]+distance*direction[0],sensor[1]+distance*direction[1]]
            key=tuple(math.floor(p/.1) for p in hit)
            rows.append(dict(point=hit,frame=frame_id,point_index=point_id,predicted_range_m=predicted,observed_range_m=distance))
            cells.setdefault(key,[]).append(len(rows)-1)
            if len(rows)>60000:raise ValueError('SURVEY_RESIDUAL_POINT_BUDGET')
    pending=set(cells);candidates=[]
    while pending:
        seed=min(pending);pending.remove(seed);todo=[seed];members=[]
        while todo:
            key=todo.pop();members+=cells[key]
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    adjacent=(key[0]+dx,key[1]+dy)
                    if adjacent in pending:pending.remove(adjacent);todo.append(adjacent)
        evidence=[rows[i] for i in members];views=sorted({r['frame'] for r in evidence})
        baseline=max((math.dist(frames[a]['local_pose'][:2],frames[b]['local_pose'][:2]) for a in views for b in views),default=0.)
        if len(evidence)<6 or len(views)<2 or baseline<.10:continue
        x0,y0=[min(r['point'][axis] for r in evidence) for axis in (0,1)]
        x1,y1=[max(r['point'][axis] for r in evidence) for axis in (0,1)]
        if max(x1-x0,y1-y0)>2.5:continue
        body=dict(position_xy_m=[(x0+x1)/2,(y0+y1)/2],observed_extent_xy_m=[max(.10,x1-x0),max(.10,y1-y0)],
            uncertainty_m=max(.10,min(.5,max(validations[i]['score']['mean_error_m'] for i in views)+.05)),
            view_indices=views,view_baseline_m=baseline,return_count=len(evidence),height_m=height_m,
            full_3d_size_known=False,classification='unknown',source_returns=evidence,
            basis='MULTIVIEW_CLOSER_THAN_MODEL_RETURNS_NOT_VERIFIED_OBJECT')
        body['candidate_id']='Residual_'+canonical_sha256(body)[:20];candidates.append(body)
        if len(candidates)>64:raise ValueError('SURVEY_RESIDUAL_CLUSTER_BUDGET')
    return sorted(candidates,key=lambda r:r['candidate_id'])
