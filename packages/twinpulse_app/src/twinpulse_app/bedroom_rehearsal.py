# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Existing photo-room geometry → bounded PC-only kinematic mission evidence.

No ROS, SSH, serial, engine calls or physics claims. Synthetic rays/poses only.
"""
import math
from twinpulse_core.local_navigation import LocalScan, LocalPose, CheckedMission, checked_command
from twinpulse_core.bounded_grid_plan import NoBoundedPath, plan_bounded_grid
from twinpulse_core.revisions import canonical_sha256


def ray_box(x,y,dx,dy,item):
    cx,cy,_=item.transform.position_m
    a=math.radians(item.transform.rotation_rpy_deg[2]);c,s=math.cos(a),math.sin(a)
    px,py=c*(x-cx)+s*(y-cy),-s*(x-cx)+c*(y-cy)
    vx,vy=c*dx+s*dy,-s*dx+c*dy
    lo,hi=0.,3.
    for p,v,half in zip((px,py),(vx,vy),(item.shape.dimensions_m[0]/2,item.shape.dimensions_m[1]/2)):
        if abs(v)<1e-12:
            if abs(p)>half:return 3.
        else:
            t1,t2=(-half-p)/v,(half-p)/v
            lo,hi=max(lo,min(t1,t2)),min(hi,max(t1,t2))
            if lo>hi:return 3.
    return lo


def ray_disc(x,y,dx,dy,disc):
    cx,cy,radius=disc
    px,py=cx-x,cy-y
    along=px*dx+py*dy
    perpendicular_sq=px*px+py*py-along*along
    if perpendicular_sq>radius*radius:return 3.
    half_chord=math.sqrt(max(0.,radius*radius-perpendicular_sq))
    if along+half_chord<0:return 3.
    return max(0.,along-half_chord)


class RehearsalAdapter:
    """Manual and mission proposals use this same checked output adapter."""
    def __init__(self,scene,pose):
        self.scene=scene;self.pose=pose;self.events=[];self.distance=0.

    def scan(self,now,discs=()):
        x,y,yaw=self.pose
        floor=next(o for o in self.scene.objects if o.kind=='floor')
        ox,oy,_=floor.transform.position_m
        hx,hy=[v/2 for v in floor.shape.dimensions_m[:2]]
        if abs(x-ox)>=hx or abs(y-oy)>=hy:return LocalScan((0.,)*72,now,'base_link','synthetic_model','synthetic_raycast')
        rays=[]
        for i in range(72):
            a=yaw+i*math.tau/72;dx,dy=math.cos(a),math.sin(a)
            limits=[3.]
            # Floor boundary is a conservative simulation limit, not an observed wall.
            for p,d,center,half in ((x,dx,ox,hx),(y,dy,oy,hy)):
                if abs(d)>1e-12:limits.append((center+(half if d>0 else -half)-p)/d)
            limits.extend(ray_box(x,y,dx,dy,o) for o in self.scene.objects if o.kind!='floor' and o.collision)
            limits.extend(ray_disc(x,y,dx,dy,disc) for disc in discs)
            rays.append(max(0.,min(limits)))
        return LocalScan(tuple(rays),now,'base_link','synthetic_model','synthetic_raycast')

    def apply(self,source,v,w,scan,now,dt=.05):
        decision=checked_command(v,w,0.,scan,now,provenance='synthetic_raycast')
        return self._integrate(source,(v,w),decision,now,dt)

    def _integrate(self,source,proposed,decision,now,dt=.05):
        # Internal synthetic integration only; no external decision/pose API.
        if source not in {'manual','mission'}:raise ValueError('UNSUPPORTED_COMMAND_SOURCE')
        if not 0<dt<=.05:raise ValueError('STEP_TOO_LARGE')
        proposed=list(proposed)
        before=self.pose
        v,w=decision['linear_m_s'],decision['angular_rad_s']
        x,y,yaw=self.pose
        # Missions deliberately turn in place; exact unicycle arc for other inputs.
        if abs(w)>1e-12:
            x+=v/w*(math.sin(yaw+w*dt)-math.sin(yaw));y-=v/w*(math.cos(yaw+w*dt)-math.cos(yaw))
        else:x+=v*math.cos(yaw)*dt;y+=v*math.sin(yaw)*dt
        self.pose=(x,y,yaw+w*dt);self.distance+=abs(v)*dt
        self.events.append({'t':now,'clock_domain':'synthetic_seconds','source':source,
            'proposed':proposed,'decision':decision,'pose_before':before,'pose_after':self.pose})
        return decision


def checked_replay(draft, manifest, descriptor):
    """Recompute trusted synthetic data; never accept client pose/trace/path bytes."""
    if (type(descriptor) is not dict or set(descriptor) != {'scenario','revision','frame'}
            or type(descriptor['frame']) is not int or not 0 <= descriptor['frame'] <= 1801
            or descriptor['scenario'] not in ('route','direct','blocked','stale_scan','detour','detour_no_path')):
        raise ValueError('Invalid synthetic replay descriptor')
    result = rehearse_bedroom(draft, manifest, descriptor['scenario'])
    if descriptor['revision'] != result['revision'] or descriptor['frame'] > len(result['events']):
        raise ValueError('Synthetic replay revision/frame mismatch')
    return result


def rehearse_bedroom(draft,manifest,scenario='route'):
    if scenario not in {'route','direct','blocked','stale_scan','detour','detour_no_path'}:raise ValueError('UNSUPPORTED_REHEARSAL')
    p=manifest['robot_placement'];pose=(*p['position_m'][:2],math.radians(p['yaw_deg']))
    route=((0.,-.40),(-.20,-.40))
    if scenario=='direct':route=((-0.20,-.40),)
    if scenario=='blocked':route=((-1.10,-.65),)
    if scenario in {'detour','detour_no_path'}:route=((-0.45,-0.05),)
    controller=CheckedMission(route,0.,provenance='synthetic_raycast',frame_id='synthetic_room')
    mission=controller.mission
    adapter=RehearsalAdapter(draft.site.scene,pose)
    replan_events=[]
    obstacle=(-.05,-.20,.06) if scenario=='detour' else (-.05,-.20,.80)
    for i in range(1801):
        now=i*.05
        active_discs=(obstacle,) if scenario in {'detour','detour_no_path'} and i>=8 else ()
        scan=adapter.scan(now,active_discs)
        if active_discs and i==8:
            # Explicit zero output before changing route. The obstacle is a
            # synthetic fixture, not a lidar-derived or physically safe map.
            stopped=adapter.apply('mission',0.,0.,scan,now)
            adapter.events[-1]['phase']='synthetic_obstacle_stop'
            mission.stop('SYNTHETIC_OBSTACLE_EVENT')
            floor=next(item for item in draft.site.scene.objects if item.kind=='floor')
            fx,fy,_=floor.transform.position_m
            hx,hy=(value/2 for value in floor.shape.dimensions_m[:2])
            boxes=tuple((item.transform.position_m[0],item.transform.position_m[1],
                         item.shape.dimensions_m[0]/2,item.shape.dimensions_m[1]/2,
                         math.radians(item.transform.rotation_rpy_deg[2]))
                        for item in draft.site.scene.objects if item.kind!='floor' and item.collision)
            try:
                route=plan_bounded_grid(adapter.pose[:2],route[-1],
                                        (fx-hx,fx+hx,fy-hy,fy+hy),boxes,active_discs)
            except NoBoundedPath as exc:
                replan_events.append({'t':now,'status':'NO_PATH','reason':str(exc),
                                      'output_zero':stopped['linear_m_s']==0. and stopped['angular_rad_s']==0.})
                break
            replan_events.append({'t':now,'status':'NEW_SYNTHETIC_PATH',
                                  'reason':'SYNTHETIC_OBSTACLE_EVENT','waypoints':route,
                                  'output_zero':stopped['linear_m_s']==0. and stopped['angular_rad_s']==0.})
            controller=CheckedMission(route,now,provenance='synthetic_raycast',
                                      frame_id='synthetic_room',duration_s=90.-now)
            mission=controller.mission
            continue
        if scenario=='stale_scan' and i>=5:
            scan=LocalScan(scan.ranges_m,now-.21,'base_link','synthetic_model','synthetic_raycast')
        decision=controller.step(LocalPose(adapter.pose,now,'synthetic_room','synthetic_model','synthetic_raycast'),
                                 scan,now,command_created_s=now)
        adapter._integrate('mission',controller.proposed,decision,now)
        if not decision['allowed']:mission.stop(decision['reason'])
        if mission.status!='RUNNING':break
    final_status='NO_PATH' if replan_events and replan_events[-1]['status']=='NO_PATH' else mission.status
    body={'schema':'bedroom-mission-rehearsal-1.0','scenario':scenario,'status':final_status,
          'manifest_revision':manifest['manifest_sha256'],'scene_revision':draft.site.scene.revision,
          'provenance':'SYNTHETIC_KINEMATIC_PHOTO_APPROXIMATION','physical_validation':'NOT_RUN',
          'motion_authorized':False,'alignment_verified':False,'isaac_run':False,
          'start_pose':pose,'waypoints':route,'final_pose':adapter.pose,'duration_s':now,
          'distance_m':adapter.distance,'events':adapter.events,'command_count':len(adapter.events),
          'limits':['No measured sensor TF or calibrated robot envelope','No dynamics/slip/contact validation',
                    'Full-circle conservative envelope; no replanning in this version',
                    'Floor boundary and rays are synthetic, not observed free space']}
    if scenario in {'detour','detour_no_path'}:
        body.update(replan_events=replan_events,obstacle_fixture=obstacle,
                    planner='bounded_grid_astar_synthetic_v1',
                    limits=[*body['limits'],
                            'Detour uses simulator obstacle geometry, not measured lidar occupancy'])
    return {**body,'revision':canonical_sha256(body)}


def comparison_conditions(record):
    """For freshly recomputed results only, not an imported-record attestation."""
    return {'manifest_revision':record['manifest_revision'],'scene_revision':record['scene_revision'],
            'start_pose':record['start_pose'],'goal_xy':record['waypoints'][-1],
            'profile':{'model':'synthetic_unicycle_v1','step_s':.05,'duration_limit_s':90.,
                       'max_linear_m_s':.03,'max_angular_rad_s':.2,'goal_tolerance_m':.015,
                       'radius_m':.18,'margin_m':.05,'guard_horizon_s':1.2,
                       'scan':'72_uniform_rays_photo_boxes_floor_boundary_3m_v1'},
            'provenance':record['provenance'],'physical_validation':record['physical_validation']}


def comparison_metrics(record):
    decisions=[e['decision'] for e in record['events'] if 'clear_radius_m' in e['decision']]
    margins=[d['clear_radius_m']-d['required_radius_m'] for d in decisions]
    return {'status':record['status'],'arrived':record['status']=='ARRIVED',
            'duration_s':record['duration_s'],'distance_m':record['distance_m'],
            'goal_error_m':math.dist(record['final_pose'][:2],record['waypoints'][-1]),
            'turn_radians':sum(abs(e['pose_after'][2]-e['pose_before'][2]) for e in record['events']),
            'min_guard_margin_m':min(margins) if margins else None,
            'guard_samples':len(margins),'near_guard_samples':sum(m<=.05 for m in margins),
            'guard_denials':sum(not e['decision']['allowed'] for e in record['events']),
            'collision_count':None,'collision_measurement':'NOT_MEASURED',
            'physical_success':None}


def compare_rehearsals(left,right):
    """Compare only current-server-generated records; caller owns trusted generation."""
    conditions=comparison_conditions(left)
    if canonical_sha256(conditions)!=canonical_sha256(comparison_conditions(right)):
        raise ValueError('Comparison scene/start/goal/profile conditions differ')
    for record in (left,right):
        body={k:v for k,v in record.items() if k!='revision'}
        if (record['revision']!=canonical_sha256(body) or record['motion_authorized'] is not False
                or record['physical_validation']!='NOT_RUN' or record['isaac_run'] is not False
                or record['provenance']!='SYNTHETIC_KINEMATIC_PHOTO_APPROXIMATION'
                or record['scenario'] not in ('route','direct')):
            raise ValueError('Only intact current synthetic comparison records allowed')
    candidates=[{'label':label,'metrics':comparison_metrics(record),'record':record}
                for label,record in (('A · 경유점 경로',left),('B · 목표 직행 경로',right))]
    eligible=all(c['metrics']['arrived'] for c in candidates)
    body={'schema':'bedroom-route-comparison-1.0','conditions':conditions,
          'conditions_revision':canonical_sha256(conditions),'candidates':candidates,
          'eligible_for_efficiency_comparison':eligible,
          'b_minus_a':{'duration_s':right['duration_s']-left['duration_s'],
                       'distance_m':right['distance_m']-left['distance_m']} if eligible else None,
          'physical_validation':'NOT_RUN','motion_authorized':False,
          'limits':['Two fixed routes, not automatic planning or optimization',
                    'Synthetic scan guard margin is not measured obstacle clearance',
                    'Near samples are time samples, not collision/near-miss events',
                    'Collision/contact not measured; no physical winner or deployment']}
    return {**body,'revision':canonical_sha256(body)}
