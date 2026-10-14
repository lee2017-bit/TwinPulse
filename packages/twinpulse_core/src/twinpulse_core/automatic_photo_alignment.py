# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded structural registration, not SLAM, calibration or motion authority.

The fit and held-out views are disjoint. Their shared odom/TF provenance is
explicit: held-out consistency is not independent metrological ground truth.
Photo furniture outer boxes are deliberately NOT sensor-height surfaces.
"""
from copy import deepcopy
import json
import math
from .revisions import canonical_sha256
from .room_localization import angle, compose, segment_distance


POLICIES = {'disabled', 'align_only', 'correct_walls'}


def structural_section(objects, height):
    if not 0.05 <= height <= 1 or not 2 <= len(objects) <= 256:
        raise ValueError('PHOTO_SECTION_BUDGET')
    floor = next((o for o in objects if o['kind'] == 'floor'), None)
    if floor is None: raise ValueError('PHOTO_FLOOR_REQUIRED')
    d = floor['shape']['dimensions_m']; p = floor['transform']['position_m']
    if not 0.5 <= min(d[:2]) <= max(d[:2]) <= 12: raise ValueError('PHOTO_FLOOR_BUDGET')
    walls = []; unknown = []
    for o in objects:
        if o['kind'] == 'floor': continue
        if o['kind'] != 'wall' or o.get('dynamic') is True:
            unknown.append({'id': o['id'], 'status': 'LOWER_STRUCTURE_UNKNOWN', 'soft_prior_only': True})
            continue
        p0 = o['transform']['position_m']; dims = o['shape']['dimensions_m']
        rpy = o['transform'].get('rotation_rpy_deg', [0,0,0])
        if abs(rpy[0])+abs(rpy[1]) > .001: raise ValueError('PHOTO_WALL_NOT_UPRIGHT')
        if not p0[2]-dims[2]/2 <= height <= p0[2]+dims[2]/2: continue
        yaw = math.radians(rpy[2]) + (math.pi/2 if dims[1] > dims[0] else 0)
        t = [math.cos(yaw), math.sin(yaw)]; n = [-t[1],t[0]]
        length = max(dims[:2]); thickness = min(dims[:2])
        if length < .6 or not .01 <= thickness <= .5: raise ValueError('PHOTO_WALL_DIMENSIONS')
        a = [p0[j]-t[j]*length/2 for j in range(2)]; b = [p0[j]+t[j]*length/2 for j in range(2)]
        walls.append({'id': o['id'], 'a': a, 'b': b, 'n': n, 't': t,
                      'rho': sum(n[j]*p0[j] for j in range(2)), 'thickness': thickness})
    if not 3 <= len(walls) <= 12: raise ValueError('PHOTO_STRUCTURAL_WALL_BUDGET')
    return {'walls': walls, 'unknown': unknown, 'height_m': height,
            'bounds': [p[0]-d[0]/2,p[0]+d[0]/2,p[1]-d[1]/2,p[1]+d[1]/2],
            'basis': 'PHOTO_APPROXIMATION_NOT_SURVEYED'}


def _line(points):
    c = [sum(p[j] for p in points)/len(points) for j in range(2)]
    xx = sum((p[0]-c[0])**2 for p in points); yy = sum((p[1]-c[1])**2 for p in points)
    xy = sum((p[0]-c[0])*(p[1]-c[1]) for p in points)
    yaw = .5*math.atan2(2*xy,xx-yy); t = [math.cos(yaw),math.sin(yaw)]; n = [-t[1],t[0]]
    # Canonical normal gives stable clustering across reversed ray order.
    if n[0] < -1e-8 or (abs(n[0]) <= 1e-8 and n[1] < 0): n = [-v for v in n]; t = [-v for v in t]
    rho = sum(n[j]*c[j] for j in range(2)); s = [sum(t[j]*p[j] for j in range(2)) for p in points]
    return {'n':n,'t':t,'rho':rho,'lo':min(s),'hi':max(s),
            'error':max(abs(sum(n[j]*p[j] for j in range(2))-rho) for p in points)}


def _spread(views):
    return max((math.dist(a['pose'][:2],b['pose'][:2]) for a in views for b in views),default=0)


def _same_line_basis(row, normal):
    """Unoriented PCA lines must use one basis before clustering/averaging.

    Near an axis, tiny noise can flip the canonical normal. Negating n/t/rho
    and reversing the signed interval preserves exactly the same endpoints;
    it adds no observation and changes no geometric/support threshold.
    """
    if sum(row['n'][j]*normal[j] for j in range(2))>=0:return row
    return {**row,'n':[-v for v in row['n']],'t':[-v for v in row['t']],
            'rho':-row['rho'],'lo':-row['hi'],'hi':-row['lo']}


def stable_lines(views, required=3):
    clusters = []
    for view in views:
        pts = [compose(view['pose'],[*p,0])[:2] for p in view['points']]
        i = 0
        while i+5 <= len(pts):
            if any(math.dist(a,b)>.55 for a,b in zip(pts[i:i+4],pts[i+1:i+5])):
                i+=1;continue
            end = i+5; row = _line(pts[i:end])
            if row['error'] > .025: i += 1; continue
            while end < len(pts) and math.dist(pts[end],pts[end-1]) <= .55:
                grown = _line(pts[i:end+1])
                if grown['error'] > .035: break
                row = grown; end += 1
            i = max(i+1,end-1)
            if row['hi']-row['lo'] < .65: continue
            target=None
            for group in clusters:
                candidate=_same_line_basis(row,group['n'])
                if (abs(sum(group['n'][j]*candidate['n'][j] for j in range(2))-1)<.002
                        and abs(group['rho']-candidate['rho'])<.065
                        and min(group['hi'],candidate['hi'])-max(group['lo'],candidate['lo'])>.3):
                    target=group;row=candidate;break
            if target is None:
                if len(clusters) >= 64: raise ValueError('PHOTO_LINE_EXTRACTION_BUDGET')
                target = {**row,'rows':{},'views':{}}; clusters.append(target)
            target['rows'][view['sequence']] = row; target['views'][view['sequence']] = view
            target['lo'] = min(target['lo'],row['lo']); target['hi'] = max(target['hi'],row['hi'])
    result = []
    for g in clusters:
        rows = list(g.pop('rows').values()); origins = list(g.pop('views').values())
        if len(rows) < required or _spread(origins) < .15: continue
        # Normals differ slightly between PCA windows. Averaging their raw rho
        # values mixes coordinate bases and invents translation. First average
        # the direction, then project all row endpoints into that SAME basis.
        nx=sum(r['n'][0] for r in rows);ny=sum(r['n'][1] for r in rows);norm=math.hypot(nx,ny)
        n=[nx/norm,ny/norm];t=[n[1],-n[0]]
        ends=[[[r['n'][j]*r['rho']+r['t'][j]*s for j in range(2)] for s in (r['lo'],r['hi'])] for r in rows]
        rhos=[sum(n[j]*(e[0][j]+e[1][j])/2 for j in range(2)) for e in ends]
        if max(rhos)-min(rhos)>.06:continue
        g.update(n=n,t=t,rho=sum(rhos)/len(rhos),
                 lo=min(sum(t[j]*p[j] for j in range(2)) for e in ends for p in e),
                 hi=max(sum(t[j]*p[j] for j in range(2)) for e in ends for p in e))
        g['support_sequences'] = [v['sequence'] for v in origins]
        g['span_m'] = _spread(origins)
        g['a'] = [g['n'][j]*g['rho']+g['t'][j]*g['lo'] for j in range(2)]
        g['b'] = [g['n'][j]*g['rho']+g['t'][j]*g['hi'] for j in range(2)]
        result.append(g)
    return sorted(result,key=lambda g:-(g['hi']-g['lo']))[:12]


def _distance(point, wall):
    # Wall thickness is an interval, not a forced exterior box/center line.
    return max(0.,segment_distance(point,[wall['a'],wall['b']])-wall['thickness']/2)


def _score(lines,walls,pose):
    errors=[]; matched=[]
    for line in lines:
        pts=[compose(pose,[*line[k],0])[:2] for k in ('a','b')]
        pts.append([(pts[0][j]+pts[1][j])/2 for j in range(2)])
        options=[(sum(_distance(p,w) for p in pts)/3,w['id']) for w in walls]
        error,identity=min(options); errors.append(min(error,.5)); matched.append(identity if error < .15 else None)
    return sum(errors)/len(errors),sum(e < .15 for e in errors)/len(errors),matched


def _residual_audit(lines, walls, pose):
    """Inspect a rejected candidate too; never supply an accepted transform.

    Uncapped residuals retain severity that the bounded search score hides.
    Nearest model wall is a hypothesis, not an identified physical wall.
    """
    rows=[]
    for index,line in enumerate(lines):
        points=[compose(pose,[*line[k],0])[:2] for k in ('a','b')]
        points.append([(points[0][j]+points[1][j])/2 for j in range(2)])
        options=[(sum(_distance(p,w) for p in points)/3,w) for w in walls]
        error,wall=min(options,key=lambda item:item[0])
        normal=compose([0,0,pose[2]],[*line['n'],0])[:2]
        cosine=min(1.,abs(sum(normal[j]*wall['n'][j] for j in range(2))))
        rows.append({'structure_index':index,'nearest_wall_hypothesis':wall['id'],
            'mean_uncapped_residual_m':error,'search_capped_residual_m':min(error,.5),
            'orientation_difference_rad':math.acos(cosine),
            'normal_offset_m':sum(wall['n'][j]*points[2][j] for j in range(2))-wall['rho'],
            'within_existing_support_distance':error<.15,
            'support_sequences':line['support_sequences'],
            'observed_length_m':math.dist(line['a'],line['b']),
            'physical_wall_identity_verified':False})
    return rows


def _parallel_separations(lines):
    """Rigid-transform-invariant distances, without identifying real walls."""
    rows=[]
    for i,a in enumerate(lines):
        for j,b in enumerate(lines[i+1:],i+1):
            cosine=abs(sum(a['n'][k]*b['n'][k] for k in range(2)))
            if cosine<=.995:continue
            middle=[(b['a'][k]+b['b'][k])/2 for k in range(2)]
            separation=abs(sum(a['n'][k]*middle[k] for k in range(2))-a['rho'])
            rows.append({'structure_indices':[i,j],'normal_separation_m':separation,
                'orientation_difference_rad':math.acos(min(1.,cosine)),
                'physical_wall_pair_verified':False})
    return rows


def _seeds(lines,walls):
    seeds=[]
    for i,l1 in enumerate(lines):
        for l2 in lines[i+1:]:
            if abs(l1['n'][0]*l2['n'][1]-l1['n'][1]*l2['n'][0]) < .35: continue
            for w1 in walls:
                for w2 in walls:
                    if w1['id']==w2['id']:continue
                    for flip in (0,math.pi):
                        yaw=angle(math.atan2(w1['n'][1],w1['n'][0])-math.atan2(l1['n'][1],l1['n'][0])+flip)
                        ns=[compose([0,0,yaw],[*l['n'],0])[:2] for l in (l1,l2)]
                        if abs(abs(sum(ns[1][j]*w2['n'][j] for j in range(2)))-1)>.005:continue
                        rhs=[]
                        for n,l,w in zip(ns,(l1,l2),(w1,w2)):
                            sign=1 if sum(n[j]*w['n'][j] for j in range(2))>0 else -1
                            rhs.append(sign*w['rho']-l['rho'])
                        det=ns[0][0]*ns[1][1]-ns[0][1]*ns[1][0]
                        x=(rhs[0]*ns[1][1]-ns[0][1]*rhs[1])/det
                        y=(ns[0][0]*rhs[1]-rhs[0]*ns[1][0])/det
                        if abs(x)>20 or abs(y)>20:continue
                        if len(seeds)>=16000:raise ValueError('PHOTO_GLOBAL_SEARCH_BUDGET')
                        seeds.append([x,y,yaw])
    return seeds


def align_photo_map(saved_map,objects,*,height_m=.182,policy='align_only',diagnostics=False):
    if policy not in POLICIES:raise ValueError('PHOTO_POLICY_INVALID')
    objects=json.loads(json.dumps(objects,allow_nan=False))
    before=canonical_sha256(objects)
    result={'schema':'automatic-photo-alignment-1.0','policy':policy,'status':'DISABLED',
            'source_map_revision':saved_map['revision'],'scene_revision_before':before,
            'room_from_map':None,'proposals':[],'corrected_objects':None,
            'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,
            'validation_basis':'DISJOINT_VIEWS_SHARED_ODOM_TF_NOT_INDEPENDENT_GROUND_TRUTH',
            'height_material_scale_changed':False,'goal_revalidation_required':False}
    if policy=='disabled':return result
    section=structural_section(objects,height_m);walls=section['walls']
    result.update(status='INSUFFICIENT_EVIDENCE',sensor_section=section,photo_outer_objects=deepcopy(objects))
    views=saved_map['keyframes']
    if len(views)>128:raise ValueError('PHOTO_KEYFRAME_BUDGET')
    if any(len(v['points'])>160 or len(v['pose'])!=3 or any(not math.isfinite(x) for x in v['pose'])
           or any(len(p)!=2 or any(not math.isfinite(x) for x in p) for p in v['points']) for v in views):
        raise ValueError('PHOTO_POINT_BUDGET')
    if any(a['sequence']>=b['sequence'] or a['stamp_ns']>=b['stamp_ns'] for a,b in zip(views,views[1:])):
        raise ValueError('PHOTO_KEYFRAME_ORDER_INVALID')
    views=views[::max(1,math.ceil(len(views)/40))]
    if len(views)<8 or _spread(views)<.4:
        result['reason']='NEED_MORE_SEPARATED_STRUCTURAL_VIEWS';return result
    cut=int(len(views)*.6);fit=views[:cut];validation=views[cut+1:] # purge the boundary view
    result['fit_sequences']=[v['sequence'] for v in fit];result['validation_sequences']=[v['sequence'] for v in validation]
    result['fit_interval_ns']=[fit[0]['stamp_ns'],fit[-1]['stamp_ns']]
    result['validation_interval_ns']=[validation[0]['stamp_ns'],validation[-1]['stamp_ns']]
    lines=stable_lines(fit);held=stable_lines(validation,2)
    result.update(fit_structures=lines,validation_structures=held)
    if len(lines)<3 or len(held)<3:
        result['reason']='REPEATED_NONPARALLEL_STRUCTURE_REQUIRED';return result
    candidates=[]
    for pose in _seeds(lines,walls):
        error,inliers,ids=_score(lines,walls,pose)
        candidates.append({'pose':pose,'mean_error_m':error,'inlier_fraction':inliers,'wall_ids':ids})
    candidates.sort(key=lambda c:c['mean_error_m']);distinct=[]
    for c in candidates:
        if all(math.dist(c['pose'][:2],r['pose'][:2])>.3 or abs(angle(c['pose'][2]-r['pose'][2]))>.2 for r in distinct):
            distinct.append(c)
        if len(distinct)==8:break
    result['alternatives']=distinct
    if len(distinct)<2:result['reason']='INDEPENDENT_TRANSFORM_RIVAL_REQUIRED';return result
    best=distinct[0];margin=distinct[1]['mean_error_m']-best['mean_error_m']
    result.update(alternative_margin_m=margin,fit_error_m=best['mean_error_m'],
                  additional_evidence='SEPARATED_STABLE_NONPARALLEL_WALL_VIEWS_OR_ONE_ASYMMETRIC_STRUCTURAL_CONSTRAINT')
    # The same unchanged fit candidate is audited on later, disjoint views
    # even when rejected. This diagnostic does not enter acceptance or edits.
    if diagnostics:result['residual_diagnosis']={
        'schema':'photo-structure-residual-diagnosis-1.0',
        'candidate_room_from_map':best['pose'],
        'candidate_is_accepted_pose':False,
        'fit':_residual_audit(lines,walls,best['pose']),
        'held_out':_residual_audit(held,walls,best['pose']),
        'fit_parallel_separations':_parallel_separations(lines),
        'held_out_parallel_separations':_parallel_separations(held),
        'furniture_used_as_structural_wall':False,
        'unresolved_causes':['APPROXIMATE_PHOTO_WALL_GEOMETRY',
            'OBSERVED_STRUCTURE_MAY_BE_FURNITURE_OR_CLOTH',
            'DECLARED_TIMESTAMPS_NOT_VERIFIED_ACQUISITION',
            'AS_BUILT_MOUNT_AND_LONG_TERM_ODOM_UNVERIFIED'],
        'causal_attribution':'UNRESOLVED_NOT_A_CALIBRATION',
        'motion_authorized':False}
    if best['mean_error_m']>.12 or best['inlier_fraction']<.75 or len(set(best['wall_ids'])-{None})<3:
        result.update(status='MODEL_MISMATCH',reason='STRUCTURAL_POSE_FIT_REJECTED');return result
    if margin<.025:
        result.update(status='AMBIGUOUS',reason='SYMMETRIC_OR_COMPETING_STRUCTURE');return result
    pose=best['pose'];val_error,val_inliers,val_ids=_score(held,walls,pose)
    result.update(validation_before_m=val_error,fit_error_m=best['mean_error_m'])
    if val_error>.12 or val_inliers<.75 or len(set(val_ids)-{None})<3:
        result.update(status='VALIDATION_REJECTED',reason='HELD_OUT_STRUCTURE_DISAGREES');return result
    result.update(status='ALIGNMENT_CANDIDATE',room_from_map=pose,reason='STRUCTURAL_HELD_OUT_CONSISTENCY_ONLY')
    # Fixed pose and nominal revision throughout the geometry phase. No scale,
    # rotation, height, material, furniture edits or joint pose/model stretching.
    proposals=[];rejections=[];result['geometry_rejections']=rejections
    for w in walls:
        assigned=[l for l,identity in zip(lines,best['wall_ids']) if identity==w['id']]
        checks=[l for l,identity in zip(held,val_ids) if identity==w['id']]
        if not assigned or not checks:
            rejections.append({'id':w['id'],'reason':'WALL_NOT_SUPPORTED_IN_BOTH_INTERVALS'});continue
        def delta_for(l):
            middle=[(l['a'][j]+l['b'][j])/2 for j in range(2)]
            return sum(w['n'][j]*compose(pose,[*middle,0])[j] for j in range(2))-w['rho']
        deltas=[delta_for(l) for l in assigned]
        delta=sum(deltas)/len(deltas)
        # Leave nominal wall thickness uncertainty unedited.
        if abs(delta)<=w['thickness']/2+.025:
            rejections.append({'id':w['id'],'reason':'WITHIN_NOMINAL_THICKNESS_UNCERTAINTY','fit_delta_m':delta});continue
        if abs(delta)>.20 or max(deltas)-min(deltas)>.04:
            rejections.append({'id':w['id'],'reason':'DELTA_OR_FIT_VARIANCE_EXCEEDS_BOUND','fit_delta_m':delta});continue
        validation_delta=[delta_for(l) for l in checks]
        if any(abs(d-delta)>.04 for d in validation_delta):
            rejections.append({'id':w['id'],'reason':'HELD_OUT_DELTA_DISAGREES','fit_delta_m':delta,'validation_delta_m':validation_delta});continue
        proposals.append({'id':w['id'],'translation_xy_m':[delta*n for n in w['n']],
                          'normal_delta_m':delta,'fit_sequences':sorted({s for l in assigned for s in l['support_sequences']}),
                          'validation_sequences':sorted({s for l in checks for s in l['support_sequences']})})
    result['proposals']=proposals
    if not proposals:
        result['geometry_status']='UNCHANGED_NO_IDENTIFIABLE_VALIDATED_EDIT';return result
    if len(proposals)>2:result.update(geometry_status='REJECTED_TOO_MANY_WALL_CHANGES');return result
    corrected=deepcopy(objects)
    for p in proposals:
        target=next(o for o in corrected if o['id']==p['id'])
        for j in range(2):target['transform']['position_m'][j]+=p['translation_xy_m'][j]
    revised=structural_section(corrected,height_m)
    bounds=section['bounds']
    if any(not bounds[0]-.25<=p[0]<=bounds[1]+.25 or not bounds[2]-.25<=p[1]<=bounds[3]+.25
           for w in revised['walls'] for p in (w['a'],w['b'])):
        result['geometry_status']='REJECTED_FLOOR_BOUNDARY';return result
    for i,a in enumerate(revised['walls']):
        for b in revised['walls'][i+1:]:
            if abs(sum(a['n'][j]*b['n'][j] for j in range(2)))>.995 and abs(abs(a['rho'])-abs(b['rho']))<.4:
                # Compare signed normals, not absolute coordinates on opposite sides.
                sign=1 if sum(a['n'][j]*b['n'][j] for j in range(2))>0 else -1
                if abs(a['rho']-sign*b['rho'])<.4:
                    result['geometry_status']='REJECTED_COLLAPSED_STRUCTURE';return result
    after,after_fraction,_=_score(held,revised['walls'],pose)
    result['validation_after_m']=after
    # Judge identifiable edits on their own held-out support, not a mean
    # diluted by unrelated unchanged walls or duplicate visible fragments.
    targets={p['id'] for p in proposals}
    affected=[l for l,identity in zip(held,val_ids) if identity in targets]
    target_before,_,_=_score(affected,walls,pose);target_after,_,_=_score(affected,revised['walls'],pose)
    result.update(target_validation_before_m=target_before,target_validation_after_m=target_after)
    if val_error-after<.001 or target_before-target_after<.025 or after_fraction<val_inliers:
        result['geometry_status']='REJECTED_NO_HELD_OUT_IMPROVEMENT';return result
    result.update(geometry_status='BOUNDED_WALL_PROPOSAL_VALIDATED',corrected_objects=corrected,
                  scene_revision_after=canonical_sha256(corrected))
    return result
