# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One chat-approved current-room survey. No route/goal approval is inferred.

The existing mission worker owns admission, guards and cleanup. Snapshot and
history never start work; the production registered adapter remains required.
"""
import time
from copy import deepcopy
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.adaptive_mission_contract import nominal_room
from .command_broker import BrokerError


class ChatInspection:
    def __init__(self,mission,workflow,preparation,start_lock):
        self.mission=mission;self.workflow=workflow;self.preparation=preparation;self.start_lock=start_lock
        self.owner=None;self.job_id=None;self.scene_revision=None
        self.reference_descriptor=None
        self.summary=None;self.summary_at=0.

    def active(self,owner):
        return owner==self.owner and self.job_id is not None and bool(self.mission.worker and self.mission.worker.is_alive())

    def readiness(self,owner):
        if self.mission.worker and self.mission.worker.is_alive():
            # No inspection may start during another active mission. Polling
            # must not reopen/hash room assets while its fresh input runs.
            return {'ready':False,'binding':None,'code':'MISSION_BUSY',
                'room_revision':None,'scene_revision':None,'motion_authorized':False,'demo_ready':False}
        code='CURRENT_CHAT_ROOM_UNAVAILABLE';binding=None;revision=None;scene=None;policy='align_only'
        if self.mission.automatic.root is None or self.mission.automatic.photo_store is None:
            return {'ready':False,'binding':None,'code':'INSPECTION_STORAGE_UNAVAILABLE',
                    'room_revision':None,'scene_revision':None,'motion_authorized':False,'demo_ready':False}
        try:
            room=self.mission.automatic.room_loader(self.mission.automatic.root,self.mission.automatic.project_id)
            effective=self.mission.automatic.photo_store.current(room)
            revision=effective['effective_revision'];scene=room['scene_revision']
            geometry=self.mission.automatic.geometry_loader()
            height=geometry['base_footprint_to_base_link_xyz_m'][2]+geometry['base_link_to_scan_xyz_m'][2]
            nominal_room(effective['objects'],height,revision)
            view=self.workflow._broker.supervisor_state();snapshot=view.get('snapshot') or {}
            from .chat_inspection_visual import derived_scene
            from twinpulse_core.site_contracts import SceneRevision
            current_scene=SceneRevision.from_dict(self.workflow.inspection_scene(self.mission.automatic.root,self.mission.automatic.project_id))
            if not view['engine_connected'] or snapshot.get('applied_revision') not in {scene,derived_scene(current_scene,effective).revision}:
                code='CURRENT_TWIN_BUILD_REQUIRED'
            else:
                robot=self.preparation.snapshot(owner)
                if not robot['owned'] or robot['state']!='LINKED':code='CURRENT_ROBOT_LINK_REQUIRED'
                else:
                    result=self.mission.readiness(None)
                    code=result['next_action']
                    if result['adapter_available']:
                        policy='correct_walls' if result.get('photo_correction_available') else 'align_only'
                        binding=canonical_sha256({'room':room['revision'],'effective':revision,'head':effective['head'],
                            'link':robot['binding'],'attempt':robot['attempt_id'],'mode':'SURVEY_ONLY','duration_s':45.,
                            'photo_policy':policy})
                        code='SURVEY_REQUIRES_EXPLICIT_CONFIRM'
        except (ValueError,KeyError,OSError,TypeError,BrokerError) as error:
            text=str(error)
            import re
            code=error.code if isinstance(error,BrokerError) else text if re.fullmatch('[A-Z0-9_]{1,120}',text) else 'INSPECTION_SOURCE_REJECTED'
        busy=bool(self.mission.worker and self.mission.worker.is_alive())
        return {'ready':binding is not None and not busy,'binding':binding,'code':code,
                'room_revision':revision,'scene_revision':scene,'photo_policy':policy,'motion_authorized':False,'demo_ready':False}

    def start(self,owner,binding,expires_at_ms):
        with self.start_lock:
            if (type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-time.time()*1000<=2000):
                raise BrokerError('inspection_confirmation_expired','Click the current inspection question again.',status=409)
            self.preparation._independent_busy()
            current=self.readiness(owner)
            if not current['ready'] or not binding or binding!=current['binding']:
                raise BrokerError('inspection_binding_changed',current['code']+'; refresh current Twin and robot readiness.',status=409)
            goal={'mode':'SURVEY_ONLY','xy':[0.,0.],'room_revision':current['room_revision'],'duration_s':45.}
            result=self.mission.start(owner,None,goal,current['photo_policy'])
            self.owner=owner;self.job_id=result['job']['job_id'];self.scene_revision=current['scene_revision']
            self.reference_descriptor=None
            return self.snapshot(owner)

    def snapshot(self,owner):
        if self.owner!=owner or self.job_id is None:
            return {'state':'NOT_STARTED','owned':False,'busy':False,'readiness':self.readiness(owner),
                    'motion_authorized':False,'demo_ready':False}
        value=self.mission.snapshot(owner);job=value.get('job') or {}
        if job.get('job_id')!=self.job_id:
            return {'state':'SESSION_REPLACED','owned':False,'busy':False,'motion_authorized':False,'demo_ready':False}
        busy=self.active(owner);finished=not busy
        diagnostics=job.get('cold_start') or {}
        successful=(finished and job.get('state')=='MISSION_ARRIVED' and job.get('report_status')=='SAVED'
            and diagnostics.get('stage')=='SURVEY_COMPLETE' and diagnostics.get('alignment_status')=='ALIGNMENT_CANDIDATE')
        # Terminal pose is historical, never a current localization lease for
        # a future goal. An explicit new goal still needs current observations.
        phase='SURVEY_COMPLETE' if successful else job.get('state','FAILED')
        stamp=time.monotonic()
        error=job.get('error') or job.get('cleanup_error') or job.get('report_error')
        if stamp-self.summary_at>=5 or (self.summary or {}).get('state')!=phase or (self.summary or {}).get('error')!=error:
            self.summary={'state':phase,'elapsed_s':job.get('elapsed_s',0),'observed_at_ms':time.time()*1000,
                'next_action':'SURVEY_AND_ALIGNMENT_ONLY' if busy else 'FRESH_GOAL_PREVIEW_REQUIRED' if successful
                    else 'INSPECTION_FAILED_REVIEW_CAUSES' if phase=='FAILED' else 'INSPECTION_STOPPED_NO_GOAL_AUTHORITY',
                'battery':None,'battery_status':'NOT_OBSERVED','error':error}
            self.summary_at=stamp
        visual=deepcopy(job.get('visual')) if (busy
            and 0<=self.mission.clock()-job.get('visual_updated_s',-10)<.2
            and (job.get('visual') or {}).get('state')!='LOCALIZING') else None
        return {'state':phase,'owned':True,'busy':busy,'summary':deepcopy(self.summary),
            'readiness':self.readiness(owner) if not busy else None,
            'job_id':self.job_id,'elapsed_s':job.get('elapsed_s',0),'room_revision':job['goal']['room_revision'],
            'scene_revision':self.scene_revision,
            'diagnostics':job.get('cold_start'),'visual':visual,
            'photo_correction':deepcopy(job.get('photo_correction')),
            'report_status':job.get('report_status'),'report_revision':job.get('report_revision'),
            'error':job.get('error'),'error_stage':job.get('error_stage'),'cleanup_error':job.get('cleanup_error'),
            'report_error':job.get('report_error'),'alignment_candidate':successful,
            'current_pose_available':bool((visual or {}).get('pose_room')),
            'physical_validation':'NOT_RUN','motion_authorized':False,'demo_ready':False}

    def reference(self,owner):
        # Explicit internal selection for a subsequent goal; polling never
        # starts localization, starts sensors or grants driving permission.
        if owner!=self.owner or self.job_id is None or self.active(owner):
            raise BrokerError('survey_reference_unavailable','An owned completed survey is required.',status=409)
        from .survey_reference import reference_key
        from .chat_inspection_visual import KIND
        if self.reference_descriptor is None:
            job=self.mission.snapshot(owner)['job']
            if (not job or job['job_id']!=self.job_id or job.get('state')!='MISSION_ARRIVED'
                    or job.get('report_status')!='SAVED'):
                raise BrokerError('survey_reference_unavailable','A saved successful survey report is required.',status=409)
            self.reference_descriptor={'kind':KIND,'mission_id':self.job_id,'manifest_sha256':job['report_revision']}
        key=reference_key(self.reference_descriptor)
        try:self.mission._reference(key)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            raise BrokerError('survey_reference_rejected',str(exc)[:160],status=409) from exc
        return key

    def stop(self,owner,force):
        self.mission.stop(owner,self.job_id,force)
        return {'state':'FORCE_STOP_REQUESTED' if force else 'STOP_REQUESTED','stop_confirmed':False}

    def display_readiness(self,descriptor):
        from .chat_inspection_visual import checked_inspection_visual
        try:
            root=self.mission.automatic.root;project=self.mission.automatic.project_id
            source={'room':self.workflow.inspection_room(root,project),'scene':self.workflow.inspection_scene(root,project)}
            scene,_=checked_inspection_visual(root,project,descriptor,current_source=source)
            return {'ready':True,'code':'SAVED_SURVEY_DISPLAY_AVAILABLE','descriptor':deepcopy(descriptor),
                    'scene_revision':scene.revision,'current_pose_available':False,'motion_authorized':False}
        except (ValueError,OSError,TypeError,KeyError,BrokerError) as exc:
            import re
            code=exc.code if isinstance(exc,BrokerError) else str(exc)
            if not re.fullmatch('[A-Za-z0-9_]{1,120}',code):code='INSPECTION_DISPLAY_SOURCE_REJECTED'
            return {'ready':False,'code':code,'descriptor':deepcopy(descriptor),'scene_revision':None,
                    'current_pose_available':False,'motion_authorized':False}

    def display(self,owner,descriptor,request_id,broker):
        # Build is visual-only, but never replace a scene during physical work.
        with self.start_lock, self.mission.lock:
            if self.preparation.diagnostics is not None and self.preparation.controller is not None:
                self.preparation._independent_busy()
            if self.mission.worker and self.mission.worker.is_alive():
                raise BrokerError('inspection_busy','Wait for the saved survey report.',status=409)
            current=self.display_readiness(descriptor)
            if not current['ready']:raise BrokerError('inspection_display_rejected',current['code'],status=409)
            from .chat_inspection_visual import checked_inspection_visual
            root=self.mission.automatic.root;project=self.mission.automatic.project_id
            source={'room':self.workflow.inspection_room(root,project),'scene':self.workflow.inspection_scene(root,project)}
            scene,_=checked_inspection_visual(root,project,descriptor,current_source=source)
            artifact_id='inspection-'+canonical_sha256(descriptor)
            from twinpulse_core.presentation import DEFAULT_PRESENTATION
            # A closed room's automatic side view can hide the entire scan.
            # This display-only preset does not edit geometry or measured data.
            broker.register_site_scene(artifact_id,scene,visual_preview=descriptor,
                presentation={**DEFAULT_PRESENTATION,'view':'top'})
            return broker.submit(owner,{'client_request_id':request_id,'command_type':'build_site_scene',
                'artifact_id':artifact_id,'expected_applied_revision':scene.revision})
