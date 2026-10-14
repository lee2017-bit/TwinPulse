# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One bounded survey -> held-out photo fit -> current observed goal mission.

No devices, admission or future lap. Expensive fit runs off the control thread
while zero velocity is emitted. A survey's completion is not final arrival.
The transient map is explicitly odometry-projected, not global SLAM/revisit proof.
"""
from copy import deepcopy
import math
import threading
from .automatic_mapping import EvidenceGrid
from .automatic_photo_alignment import align_photo_map, structural_section
from .current_mission_evidence import CurrentMissionEvidence
from .local_navigation import CheckedMission, finite
from .observed_mission import ObservedMission, checked_goal
from .revisions import canonical_sha256
from .room_localization import angle, compose


def survey_tracking_endpoints(views):
    """Bounded original deskewed endpoints, not occupancy-cell centers.

    The occupancy grid still owns free/unknown space. This separate reference
    contains only prior accepted survey returns projected by observed odometry;
    no photo geometry, future scans or synthetic world pose enters tracking.
    """
    points=[compose(view['pose'],[*point,0.])[:2]
            for view in views for point in view['points']]
    step=max(1,math.ceil(len(points)/18000))
    return points[::step]


class ColdStartMission(CheckedMission):
    def __init__(self,goal,started_s,*,tracker,current,nominal,provenance,frame_id,context,
                 photo_policy='align_only',commit_correction=None):
        self.goal=checked_goal(goal)
        if self.goal['mode'] not in {'SURVEY_THEN_NAVIGATE','SURVEY_ONLY'}:raise ValueError('COLD_START_GOAL_REQUIRED')
        self.survey_only=self.goal['mode']=='SURVEY_ONLY'
        structural_section(nominal['objects'],nominal['height_m'])
        if photo_policy not in {'align_only','correct_walls'}:raise ValueError('COLD_START_PHOTO_POLICY')
        if photo_policy=='correct_walls' and not callable(commit_correction):raise ValueError('COLD_START_CORRECTION_COMMIT_REQUIRED')
        self.photo_policy=photo_policy;self.commit_correction=commit_correction;self.next_goal=None
        self.fit_result=None
        super().__init__(((0.,0.),),started_s,provenance=provenance,frame_id=frame_id,duration_s=goal['duration_s'])
        self.context=deepcopy(context);self.nominal=deepcopy(nominal);self.tracker=tracker;self.current=current
        self.phase='SURVEYING';self.stage='OUTBOUND';self.views=[];self.grid=EvidenceGrid()
        self.worker=None;self.cancelled=threading.Event();self.answer=None;self.failure=None;self.failure_type=None
        self.alignment=None;self.survey_map=None;self.previous=None;self.last_evidence=None
        self.part=self._part([.47,0.],started_s)

    def _part(self,xy,started,*,navigate=False):
        goal={**self.goal,'mode':'NAVIGATE_TWIN_GOAL' if navigate else 'SURVEY_LOCAL','xy':list(xy)}
        value=ObservedMission(goal,started,provider=self._current,provenance=self.provenance,frame_id=self.frame_id,context=self.context,allow_reverse=True)
        value.mission.end=self.mission.end  # No per-stage renewal of the approved budget.
        return value

    def _current(self,pose,now):
        value=self.current(self.tracker,pose,now)
        if self.stage in {'OUTBOUND','RETURN'}:
            capture=self.tracker.capture
            if capture and capture['pose'] is not None:
                at=capture['pose'];last=self.views[-1] if self.views else None
                if (last is None or math.dist(at[:2],last['pose'][:2])>=.04
                        or abs(angle(at[2]-last['pose'][2]))>=.25):
                    if len(self.views)>=128:raise ValueError('COLD_START_VIEW_BUDGET')
                    if last and (capture['sequence']<=last['sequence'] or capture['stamp_ns']<=last['stamp_ns']):
                        raise ValueError('COLD_START_VIEW_ORDER')
                    # Photo-fit keyframes have a160-point contract. Keep the
                    # original capture and all fresh occupancy rays intact;
                    # only this derived fit view uses uniform original indices.
                    view=deepcopy(capture)
                    step=max(1,math.ceil(len(view['points'])/160))
                    view['points']=view['points'][::step]
                    view['origins']=view['origins'][::step]
                    self.views.append(view)
                    self.grid.insert([(compose(at,[*a,0.])[:2],compose(at,[*b,0.])[:2])
                        for a,b in zip(capture['origins'],capture['points'])],capture['stamp_ns'],self.context['source_revision'])
        self.last_evidence=value
        return value

    def _fit(self,saved):
        try:
            result=align_photo_map(saved,self.nominal['objects'],height_m=self.nominal['height_m'],policy=getattr(self,'photo_policy','align_only'))
            # Retain the validated or rejected proposal even if its commit
            # fails. It is diagnostic evidence, never a motion permission.
            self.fit_result={**deepcopy(result),'report_revision':canonical_sha256(result)}
            next_goal=self.goal
            if result.get('geometry_status')=='BOUNDED_WALL_PROPOSAL_VALIDATED' and self.photo_policy=='correct_walls':
                if self.cancelled.is_set():return
                binding=self.commit_correction(result,self.cancelled)
                next_goal=checked_goal(binding['goal'])
                import re
                if (set(binding)!={'schema','goal','applied_revision'} or binding['schema']!='mission-photo-binding-1.0'
                        or not isinstance(binding['applied_revision'],str) or not re.fullmatch('[a-f0-9]{64}',binding['applied_revision'])
                        or any(next_goal[k]!=self.goal[k] for k in ('mode','xy','duration_s'))):
                    raise ValueError('COLD_START_CORRECTION_BINDING_CHANGED_SCOPE')
                result['goal_binding']=deepcopy(binding)
            result['report_revision']=canonical_sha256(result)
            self.fit_result=deepcopy(result)
            # Construct the local tracking field off-thread too. Only the next
            # fresh control tick can use it; a late result cannot resume a stop.
            tracker=None
            if result['status']=='ALIGNMENT_CANDIDATE':
                tracker=CurrentMissionEvidence(saved,result,self.context,next_goal['room_revision'])
                tracker.transform=deepcopy(self.tracker.session_anchor)
            if not self.cancelled.is_set():self.next_goal=next_goal;self.answer=(result,tracker)
        except Exception as exc:
            if not self.cancelled.is_set():
                # Preserve bounded machine codes, never arbitrary exception text
                # that might contain source content, credentials or host paths.
                import re
                code=str(exc)
                self.failure=code if re.fullmatch('[A-Z0-9_]{1,120}',code) else 'PHOTO_FIT_PROCESSING_FAILED'
                self.failure_type=type(exc).__name__[:80]

    def _zero(self,reason,*,terminal=False):
        self.proposed=(0.,0.)
        if terminal:self.mission.stop(reason);self.phase='FAILED';self.cancelled.set()
        return {'allowed':not terminal,'reason':reason,'linear_m_s':0.,'angular_rad_s':0.,'physical_authority':False}

    def step(self,pose,scan,now,*,command_created_s):
        if self.mission.status!='RUNNING' or self.cancelled.is_set():return self._zero(self.mission.status,terminal=True)
        self.part.current_pose_valid=False
        # The outer contract and local guard are checked even while fitting.
        health=CheckedMission(((0.,0.),),now,provenance=self.provenance,frame_id=self.frame_id,duration_s=1.)
        health.mission.end=self.mission.end
        check=health.step(pose,scan,now,command_created_s=command_created_s)
        if not check['allowed']:return self._zero(check['reason'],terminal=True)
        if self.stage=='VERIFY_SURVEY':
            evidence=self._current(pose,now)
            if (not isinstance(evidence,dict) or any(evidence.get(k)!=v for k,v in self.context.items())
                    or evidence.get('room_revision')!=self.goal['room_revision']
                    or not finite(evidence.get('sample_s'))
                    or not 0<=now-evidence['sample_s']<.2):
                return self._zero('SURVEY_CURRENT_EVIDENCE_CHANGED',terminal=True)
            if (evidence.get('state')!='TRACKING_CANDIDATE' or evidence.get('pose_map') is None
                    or evidence.get('alignment_status')!='ALIGNMENT_CANDIDATE' or evidence.get('room_from_map') is None):
                self.phase='LOCALIZING';return self._zero('SURVEY_RECHECK_CURRENT_SENSOR')
            if any(type(evidence[k]) not in (list,tuple) or len(evidence[k])!=3
                   or any(not finite(v) for v in evidence[k]) for k in ('pose_map','room_from_map')):
                return self._zero('SURVEY_CURRENT_POSE_INVALID',terminal=True)
            # Completion consumes a fresh tracking tick, never the saved fit
            # pose. No goal route is constructed or output after alignment.
            self.part.last_evidence=deepcopy(evidence);self.part.current_pose_valid=True
            self.part.route_map=();self.part.route_revision=None
            self.stage='SURVEY_COMPLETE';self.phase='ARRIVED';self.mission.stop('ARRIVED')
            return self._zero('SURVEY_COMPLETE_NO_GOAL_COMMAND')
        # Zero output alone does not validate a scan. Reuse the current mission
        # source/epoch/freshness/guard checks before accepting any worker result.
        if self.stage=='ALIGN':
            self.part.mission.status='RUNNING'
            probe=self.part.step(pose,scan,now,command_created_s=command_created_s)
            self.phase='ALIGNING_PHOTO'
            if not probe['allowed']:return self._zero(probe['reason'],terminal=True)
            if self.failure:return self._zero('COLD_START_FIT_FAILED',terminal=True)
            if self.answer is None:return self._zero('PHOTO_FIT_WHEELS_IDLE')
            result,tracker=self.answer;self.alignment=result
            if tracker is None:return self._zero('COLD_START_PHOTO_'+result['status'],terminal=True)
            if self.next_goal is not None:self.goal=deepcopy(self.next_goal)
            self.tracker=tracker;self.phase='LOCALIZING'
            if self.survey_only:
                # The return leg was bound to pre-correction geometry. A fresh
                # current-only verifier must use the newly owned revision.
                self.part=self._part([0.,0.],now)
                self.stage='VERIFY_SURVEY'
                return self._zero('SURVEY_RECHECK_CURRENT_SENSOR')
            self.stage='NAVIGATE'
            self.part=self._part(self.goal['xy'],now,navigate=True)
            return self._zero('PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR')
        value=self.part.step(pose,scan,now,command_created_s=command_created_s)
        self.proposed=self.part.proposed;self.phase=self.part.phase
        if not value['allowed']:return self._zero(value['reason'],terminal=True)
        if self.part.mission.status=='ARRIVED':
            if self.stage=='OUTBOUND':
                self.stage='RETURN';self.phase='SURVEYING';self.part=self._part([.20,0.],now)
                return self._zero('SURVEY_RETURN_FOR_HELD_OUT_VIEWS')
            if self.stage=='RETURN':
                body={'schema':'session-survey-map-1.0','project_id':self.context['project_id'],
                    'source_revision':self.context['source_revision'],'endpoint_cells':self.grid.endpoints(),
                    'tracking_endpoints':survey_tracking_endpoints(self.views),
                    'tracking_endpoint_basis':'ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED',
                    'keyframes':deepcopy(self.views),'reference_eligible':False,
                    'mapping_method':'CAUSAL_DESKEWED_ODOMETRY_PROJECTION_NOT_GLOBAL_SLAM',
                    'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}
                self.survey_map={**body,'revision':canonical_sha256(body)}
                self.stage='ALIGN';self.phase='ALIGNING_PHOTO'
                # A non-arriving zero-distance probe still checks every current
                # source. Reset its status each fit tick without sending motion.
                self.part=self._part(self.last_evidence['pose_map'][:2],now)
                self.worker=threading.Thread(target=self._fit,args=(deepcopy(self.survey_map),),daemon=True,name='tp-cold-photo-fit')
                self.worker.start();return self._zero('PHOTO_FIT_WHEELS_IDLE')
            self.mission.stop('ARRIVED');self.phase='ARRIVED'
        return value

    def note_output(self,now,v,w):
        self.part.note_output(now,v,w)

    def visual(self,session_id):
        value=self.part.visual(session_id)
        value.update(state=self.phase,goal_room=None if self.survey_only else self.goal['xy'])
        value['revision']=canonical_sha256({k:v for k,v in value.items() if k!='revision'})
        return value

    def close(self):
        self.cancelled.set()
        if self.worker:self.worker.join(.1)

    def diagnostics(self):
        result=self.alignment or (self.answer[0] if self.answer else {})
        return {'stage':self.stage,'view_count':len(self.views),
                'map_revision':self.survey_map['revision'] if self.survey_map else None,
                'alignment_status':result.get('status','NOT_RUN'),
                'alignment_revision':result.get('report_revision'),
                'reason':self.failure or result.get('reason','NOT_RUN'),
                'error_stage':'PHOTO_ALIGNMENT' if self.failure else None,
                'error_type':self.failure_type if self.failure else None}
