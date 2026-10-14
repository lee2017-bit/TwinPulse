# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current evidence -> atomic observed-grid route -> existing local guard.

No transport, auto-arm or qualification. Recorded maps are priors, not current
poses. Provider must supply a fresh independently updated pose/map binding.
"""
from copy import deepcopy
import math
import re
from .local_navigation import CheckedMission, LocalPose, finite, checked_command
from .bounded_grid_plan import plan_bounded_grid, NoBoundedPath,route_footprint_cells,observed_dependency_revision
from .room_localization import compose, inverse, angle
from .revisions import canonical_sha256


def checked_goal(value):
    if (not isinstance(value,dict) or set(value)!={'mode','xy','room_revision','duration_s'}
            or value['mode'] not in {'SURVEY_LOCAL','NAVIGATE_TWIN_GOAL','SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}
            or not isinstance(value['xy'],list) or len(value['xy'])!=2
            or any(not finite(x) or abs(x)>10 for x in value['xy'])
            or not isinstance(value['room_revision'],str) or re.fullmatch('[a-f0-9]{64}',value['room_revision']) is None
            or not finite(value['duration_s']) or not 0<value['duration_s']<=45):
        raise ValueError('AUTOMATIC_GOAL_INVALID')
    if value['mode']=='SURVEY_ONLY' and value['xy']!=[0.,0.]:raise ValueError('SURVEY_ONLY_HAS_NO_DESTINATION')
    return deepcopy(value)


class ObservedMission(CheckedMission):
    """Duck-compatible with RosLink/run_mission, same checked output boundary.

    Replanning never refreshes an expired source command. A map/transform change
    first returns zero, then commits a complete new route on a later tick.
    Survey uses session-local observed space, never a photo/global position.
    """
    def __init__(self,goal,started_s,*,provider,provenance,frame_id,context,allow_reverse=False,approved_preview=None):
        self.goal=checked_goal(goal);self.provider=provider;self.context=deepcopy(context)
        if self.goal['mode'] in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:raise ValueError('COLD_START_FACTORY_REQUIRED')
        super().__init__(((0.,0.),),started_s,provenance=provenance,frame_id=frame_id,duration_s=self.goal['duration_s'],allow_reverse=allow_reverse)
        self.route_revision=None;self.route_map=();self.phase='LOCALIZING';self.pending=True
        self.previous_pose=None;self.last_evidence=None;self.decisions=[];self.plan_count=0
        self.last_control_s=None;self.goal_map=None
        self.route_dependencies=None
        self.current_pose_valid=False
        self.approved_preview=deepcopy(approved_preview);self.preview_consumed=False
        self.approved_output_consumed=False
        from .observed_progress import ObservedProgressGuard
        self.progress_guard=ObservedProgressGuard();self.current_odom=None

    def note_output(self,now,v,w):
        if not (v or w):self.progress_guard.reset();return
        if self.current_pose_valid and self.current_odom is not None:
            self.progress_guard.published(now,v,w,self.current_odom,self.last_evidence['pose_map'])

    def _zero(self,reason,*,terminal=False):
        self.proposed=(0.,0.)
        if terminal:
            self.mission.stop(reason);self.phase='FAILED';self.current_pose_valid=False
        return {'allowed':not terminal,'reason':reason,'linear_m_s':0.,'angular_rad_s':0.,'physical_authority':False}

    def step(self,pose,scan,now,*,command_created_s):
        if self.mission.status!='RUNNING':return self._zero(self.mission.status,terminal=True)
        # Historical evidence stays available for the report, but a new tick
        # must validate its own position before it can label a visual current.
        self.current_pose_valid=False
        if not finite(now) or not finite(command_created_s) or not 0<=now-command_created_s<.25:
            return self._zero('SOURCE_EXPIRED_DURING_ENABLE',terminal=True)
        if self.last_control_s is not None and now<self.last_control_s:return self._zero('CLOCK_FAULT',terminal=True)
        self.last_control_s=now
        if now>=self.mission.end:return self._zero('MISSION_EXPIRED',terminal=True)
        basis='synthetic_model' if self.provenance=='synthetic_raycast' else 'measured_odometry'
        if (not isinstance(pose,LocalPose) or pose.provenance!=self.provenance or pose.frame_id!=self.frame_id
                or pose.basis!=basis or not finite(pose.sample_s) or not 0<=now-pose.sample_s<.2):
            return self._zero('POSE_FRAME_OR_FRESHNESS_INVALID',terminal=True)
        # Check even a zero output against the current source before planning.
        health=checked_command(.001,0.,now-command_created_s,scan,now,provenance=self.provenance)
        if not health['allowed'] and health['reason']!='OBSTACLE_IN_SWEPT_ENVELOPE':
            return self._zero(health['reason'],terminal=True)
        evidence=self.provider(pose,now)
        if not isinstance(evidence,dict):return self._zero('CURRENT_EVIDENCE_INVALID',terminal=True)
        if self.approved_preview is not None and not self.preview_consumed:
            try:
                from .current_goal_preview import check_preview
                check_preview(self.approved_preview,evidence,self.context,now,self.goal)
            except ValueError as exc:return self._zero(str(exc),terminal=True)
        if any(evidence.get(k)!=v for k,v in self.context.items()):return self._zero('MISSION_SOURCE_EPOCH_CHANGED',terminal=True)
        if evidence.get('room_revision')!=self.goal['room_revision']:return self._zero('GOAL_ROOM_REVISION_CHANGED',terminal=True)
        if not finite(evidence.get('sample_s')) or not 0<=now-evidence['sample_s']<.2:
            return self._zero('CURRENT_MAP_POSE_STALE',terminal=True)
        states={'TRACKING_CANDIDATE','SESSION_LOCAL_OBSERVED'} if self.goal['mode']=='SURVEY_LOCAL' else {'TRACKING_CANDIDATE'}
        if evidence.get('state') not in states or evidence.get('pose_map') is None:
            self.phase='LOCALIZING';self.pending=True;self.route_revision=None
            return self._zero('CURRENT_LOCALIZATION_REQUIRED')
        current=evidence['pose_map']
        if type(current) not in (list,tuple) or len(current)!=3 or any(not finite(v) for v in current):return self._zero('POSE_INVALID',terminal=True)
        if self.previous_pose and (math.dist(current[:2],self.previous_pose[:2])>.25 or abs(angle(current[2]-self.previous_pose[2]))>.25):
            return self._zero('POSE_JUMP_REQUIRES_NEW_SESSION',terminal=True)
        self.previous_pose=list(current);self.last_evidence=deepcopy(evidence)
        self.current_odom=pose.xy_yaw
        if self.goal['mode']=='NAVIGATE_TWIN_GOAL':
            if evidence.get('alignment_status')!='ALIGNMENT_CANDIDATE' or evidence.get('room_from_map') is None:
                return self._zero('CURRENT_PHOTO_ALIGNMENT_REQUIRED',terminal=True)
            transform=evidence['room_from_map']
            if type(transform) not in (list,tuple) or len(transform)!=3 or any(not finite(v) for v in transform):
                return self._zero('CURRENT_PHOTO_TRANSFORM_INVALID',terminal=True)
            target=compose(inverse(evidence['room_from_map']),[*self.goal['xy'],0.])[:2]
        else:
            target=self.goal['xy']
            if math.dist(target,current[:2])>.5:return self._zero('SURVEY_SCOPE_EXCEEDED',terminal=True)
        # Source/alignment failures retain their own diagnosis; progress is
        # considered only after this tick's coordinate binding is accepted.
        try:self.progress_guard.check(now,pose.xy_yaw,current)
        except ValueError as exc:return self._zero(str(exc),terminal=True)
        self.current_pose_valid=True
        binding={k:evidence.get(k) for k in ('map_revision','alignment_revision','room_revision','room_from_map')}
        radius=evidence.get('footprint_radius_m',.18)
        if not finite(radius) or not 0<radius<=1:return self._zero('CURRENT_FOOTPRINT_INVALID',terminal=True)
        revalidated=bool(self.approved_preview and self.approved_preview['schema']=='current-goal-preview-2.0')
        clearance=max(.18,radius)+.05+.03*1.2+(.010 if revalidated else 0.)
        binding['footprint_radius_m']=max(.18,radius)
        incremental=evidence.get('planning_revision_policy')=='FRESH_FOOTPRINT_DEPENDENCY_V1'
        if incremental:
            binding['map_revision']=observed_dependency_revision(self.route_dependencies,evidence['cells']) if self.route_dependencies else None
        signature=canonical_sha256(binding)
        if self.route_revision is not None and signature!=self.route_revision:
            self.route_revision=None;self.pending=True;self.phase='REPLANNING'
            return self._zero('REVISION_CHANGED_STOP_BEFORE_REPLAN')
        if self.pending:
            try:
                obstacles=self.approved_preview.get('obstacles_map',{}) if self.approved_preview else {}
                reviewed_route=([compose(inverse(evidence['room_from_map']),[*p,0.])[:2]
                    for p in self.approved_preview['route']] if revalidated and not self.preview_consumed else None)
                route=plan_bounded_grid(current[:2],target,evidence['bounds'],resolution=.10,clearance=clearance,
                    boxes=obstacles.get('boxes',()),discs=obstacles.get('discs',()),
                    observed_cells=evidence['cells'],cell_size_m=evidence.get('cell_size_m',.10),checked_route=reviewed_route)
            except (ValueError,NoBoundedPath) as exc:return self._zero('OBSERVED_PATH_'+str(exc),terminal=True)
            if self.approved_preview and not self.preview_consumed and not revalidated:
                reviewed=[compose(evidence['room_from_map'],[*p,0.])[:2] for p in route]
                if reviewed!=self.approved_preview['route']:
                    return self._zero('GOAL_PREVIEW_ROUTE_CHANGED',terminal=True)
            if self.goal['mode']=='SURVEY_LOCAL' and any(math.hypot(*p)>.5 for p in (current[:2],*route)):
                return self._zero('SURVEY_SCOPE_EXCEEDED',terminal=True)
            map_to_odom=compose(pose.xy_yaw,inverse(current))
            points=tuple(tuple(compose(map_to_odom,[*p,0.])[:2]) for p in route)
            self.mission.waypoints=points;self.mission.index=0
            if incremental:
                self.route_dependencies=route_footprint_cells(current[:2],route,clearance=clearance)
                binding['map_revision']=observed_dependency_revision(self.route_dependencies,evidence['cells'])
                signature=canonical_sha256(binding)
            self.route_map=route;self.route_revision=signature;self.goal_map=target;self.pending=False;self.plan_count+=1
            self.phase='SURVEYING' if self.goal['mode']=='SURVEY_LOCAL' else 'DRIVING'
            # Consumption happens only after a checked current route exists.
            self.preview_consumed=True
        # Preserve one current transform for all waypoints in this tick.
        map_to_odom=compose(pose.xy_yaw,inverse(current))
        self.mission.waypoints=tuple(tuple(compose(map_to_odom,[*p,0.])[:2]) for p in self.route_map)
        decision=super().step(pose,scan,now,command_created_s=command_created_s)
        if decision['reason']=='OBSTACLE_IN_SWEPT_ENVELOPE':
            self.mission.status='RUNNING';self.pending=True;self.phase='REPLANNING';self.route_revision=None
            return self._zero('OBSTACLE_STOP_BEFORE_REPLAN')
        if self.mission.status=='ARRIVED':self.phase='ARRIVED'
        return decision

    def validate_first_output(self,now):
        if self.approved_preview is not None and not self.approved_output_consumed:
            from .current_goal_preview import check_preview
            check_preview(self.approved_preview,self.last_evidence,self.context,now,self.goal)

    def visual(self,session_id):
        e=self.last_evidence or {}
        transform=e.get('room_from_map')
        pose=compose(transform,e['pose_map']) if self.current_pose_valid and transform and e.get('pose_map') else None
        body={'schema':'automatic-mission-visual-1.0','session_id':session_id,'context':self.context,
              'state':self.phase,'room_revision':self.goal['room_revision'],
              'route_revision':self.route_revision if self.current_pose_valid else None,
              'map_revision':e.get('map_revision'),'alignment_revision':e.get('alignment_revision'),
              'pose_room':pose,'goal_room':self.goal['xy'] if self.goal['mode']=='NAVIGATE_TWIN_GOAL' else None,
              'route_room':[compose(transform,[*p,0.])[:2] for p in self.route_map] if self.current_pose_valid and transform else [],
              'scan_room':e.get('scan_room',[]) if self.current_pose_valid else [],'trajectory_room':e.get('trajectory_room',[]),
              'motion_authorized':False,'physical_demo_ready':False,'provenance':self.provenance}
        return {**body,'revision':canonical_sha256(body)}
