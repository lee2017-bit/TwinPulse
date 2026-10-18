# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Chat goal preview/confirmation. All cached poses are explicitly historical.

No import-time transport, polling localization or restored execution permission.
Current observations can only come from the server's registered mission factory.
"""
from copy import deepcopy
import time
from .command_broker import BrokerError
from .chat_inspection_visual import checked_source,derived_scene


class ChatGoalNavigation:
    def __init__(self,mission,workflow,preparation,start_lock,inspection=None):
        self.mission=mission;self.workflow=workflow;self.preparation=preparation;self.start_lock=start_lock
        self.inspection=inspection;self.reference_key=None
        self.owner=None;self.review=None;self.text=None;self.selection=None;self.job_id=None;self.error=None
        self.demonstration=None
        from .goal_task_loop import GoalTaskLoop
        self.task_loop=GoalTaskLoop(self)

    def _task_access(self,token):
        if self.task_loop.active() and token is not self.task_loop.token:
            raise BrokerError('task_loop_active','Stop the current repeat task before changing its goal.',status=409)
        if token is not None and (token is not self.task_loop.token or self.task_loop.cancelled.is_set()):
            raise BrokerError('task_loop_stopped','The repeat task was stopped; no new leg will start.',status=409)

    def _scene(self):
        automatic=self.mission.automatic
        if automatic.root is None or automatic.photo_store is None:
            raise BrokerError('goal_storage_unavailable','Current room evidence storage is not configured.',status=409)
        room=automatic.room_loader(automatic.root,automatic.project_id)
        loader=getattr(automatic,'room_scene_loader',None)
        if loader is None:raise BrokerError('goal_scene_unavailable','Current room scene is unavailable.',status=409)
        _,source=checked_source({'room':room,'scene':loader(automatic.root,automatic.project_id)},automatic.project_id)
        effective=automatic.photo_store.current(room)
        return derived_scene(source,effective)

    def prepare(self,owner,text,*,selection=None,expected_digest=None,_task_token=None,_task_check=None):
        with self.start_lock:
            # A current preview may open the native idle-localization sensor
            # worker. No-motion is not exemption from shared scene admission.
            getattr(self.preparation,'scene_edit_guard',lambda:None)()
            readiness=getattr(self.preparation,'readiness',None)
            if readiness is not None and readiness.blocks_robot_operation():
                raise BrokerError('readiness_busy_or_uncertain','Stationary collection is active or uncertain; fresh REAL localization remains locked.',status=409)
            self._task_access(_task_token)
            if self.demonstration and self.demonstration.worker and self.demonstration.worker.is_alive():
                raise BrokerError('goal_demonstration_busy','Wait for or stop the current Isaac route demonstration.',status=409)
            if self.owner is not None and self.owner!=owner:
                if self.mission.worker and self.mission.worker.is_alive():
                    raise BrokerError('goal_not_owned','Goal belongs to another connection.',status=409)
                # A new idle connection can prepare a new route, never inherit
                # the preceding owner's review or execution approval.
                discard=getattr(self.mission.adapter_factory,'discard_review',None)
                if callable(discard):discard(self.owner)
                self.review=None;self.job_id=None;self.owner=owner
            if expected_digest is not None and (self.review is None or self.review['scene_revision']!=expected_digest):
                raise BrokerError('goal_selection_stale','Target choice expired; submit the goal again.',status=409)
            self.owner=owner;self.review=None;self.error=None;self.job_id=None;self.reference_key=None
            discard=getattr(self.mission.adapter_factory,'discard_review',None)
            if callable(discard):discard(owner)
            try:
                self.mission.require_goal_adapter()
                linked=self.preparation.snapshot(owner)
                if not linked.get('owned') or linked.get('state')!='LINKED':
                    raise BrokerError('goal_robot_link_required','Current robot qualification is required before localization preview.',status=409)
                self.reference_key=self.inspection.reference(owner) if self.inspection is not None else None
                scene=self._scene()
                if expected_digest is not None and scene.revision!=expected_digest:
                    raise BrokerError('goal_scene_changed','Room changed; submit the goal again.',status=409)
                result=self.mission.preview_goal(owner,scene,text,selection=selection,reference_key=self.reference_key,
                    **({'task_check':_task_check} if _task_check else {}))
                self._task_access(_task_token)
                if _task_token and result['map_id']!=self.task_loop.contract['reference_key']:
                    raise BrokerError('task_reference_changed','The repeat task survey reference changed.',status=409)
                self.review={**result,'scene_revision':scene.revision}
                self.text=text;self.selection=selection
                park=getattr(self.mission.adapter_factory,'park_review',None)
                if result.get('plan') and result['plan']['schema']=='current-goal-preview-2.0' and callable(park):
                    park(owner,result['map_id'],result['plan'])
                if result.get('plan') and self.demonstration:
                    self.demonstration.start(owner,scene,result['plan'])
                return deepcopy(self.review)
            except (ValueError,KeyError,OSError,TypeError) as exc:
                self._release_failed_review(owner,exc)
                self.error=str(exc)[:160]
                raise BrokerError('goal_scene_rejected',self.error,status=409) from exc
            except BrokerError as exc:
                self._release_failed_review(owner,exc)
                self.error=exc.code+': '+str(exc);raise

    def confirm(self,owner,digest,expires_at_ms,*,_task_token=None,_task_check=None):
        try:return self._confirm(owner,digest,expires_at_ms,_task_token=_task_token,_task_check=_task_check)
        except Exception as exc:
            if self.owner==owner and self.review is None:self._release_failed_review(owner,exc)
            raise

    def _release_failed_review(self,owner,exc):
        if self.owner==owner:self.review=None
        discard=getattr(self.mission.adapter_factory,'discard_review',None)
        if callable(discard):discard(owner)
        close=getattr(self.mission.adapter_factory,'close_idle',None)
        if callable(close):
            try:close(owner)
            except Exception:exc.add_note('IDLE_LOCALIZATION_CLEANUP_PENDING')

    def _confirm(self,owner,digest,expires_at_ms,*,_task_token=None,_task_check=None):
        with self.start_lock:
            self._task_access(_task_token)
            if (self.owner!=owner or self.review is None or self.review['plan'] is None
                    or self.review['plan']['plan_id']!=digest):
                raise BrokerError('goal_confirmation_stale','Review the current goal before confirming.',status=409)
            review=self.review
            # A consumed or failed approval cannot be resumed by polling/retry.
            self.review=None
            if (type(expires_at_ms) not in (int,float) or not 0<expires_at_ms-time.time()*1000<=2000):
                raise BrokerError('goal_confirmation_expired','Confirm again from a fresh preview.',status=409)
            # A geometric route overlay is not the requested Isaac execution.
            # Only the registered backend may supply a checked exact-plan SIM
            # receipt; no browser checkbox can invent it.
            if not self._preview_passed(digest):
                raise BrokerError('goal_3d_preview_required','The exact route has not passed its Isaac 3D preview. Physical goal execution remains locked.',status=409)
            if self.demonstration and getattr(self.mission.adapter_factory,'supports_exact_goal_handoff',False) is not True:
                raise BrokerError('goal_remote_handoff_unavailable','Isaac preview passed, but exact robot execution handoff is not available.',status=409)
            owns=getattr(self.mission.adapter_factory,'owns_idle',None)
            self.preparation._independent_busy(owned_idle=bool(callable(owns) and owns(owner,review['map_id'])))
            linked=self.preparation.snapshot(owner)
            if not linked.get('owned') or linked.get('state')!='LINKED':
                raise BrokerError('goal_robot_link_required','Current robot qualification is required.',status=409)
            if self._scene().revision!=review['scene_revision']:
                raise BrokerError('goal_scene_changed','Room changed; create a fresh preview.',status=409)
            result=self.mission.start_preview(owner,review['map_id'],review['plan'],
                execution_guard=(lambda:(self.task_loop.can_continue() if _task_token else True)
                    and self._execution_preview_passed(digest)) if self.demonstration or _task_token else None,
                **({'task_check':_task_check} if _task_check else {}))
            self.job_id=result['job']['job_id'];return result

    def can_confirm(self):
        plan=self.review.get('plan') if self.review else None
        factory=self.mission.adapter_factory;owns=getattr(factory,'owns_idle',None)
        reserved=getattr(factory,'owns_review',None)
        return bool(plan and self._preview_passed(plan['plan_id']) and (self.demonstration is None
            or getattr(factory,'supports_exact_goal_handoff',False) is True
            and ((callable(owns) and owns(self.owner,self.review['map_id']))
                or (callable(reserved) and reserved(self.owner,self.review['map_id'],plan)))))

    def _preview_passed(self,digest):
        if self.demonstration:return self.demonstration.passed(self.owner,digest)
        # Legacy explicitly injected local adapter tests retain their contract;
        # production always uses the engine/stage-bound service above.
        receipt=getattr(self.mission.adapter_factory,'goal_preview_receipt',None)
        return bool(callable(receipt) and receipt(digest) is True)

    def _execution_preview_passed(self,digest):
        check=getattr(self.demonstration,'execution_passed',None)
        if callable(check):return check(self.owner,digest)
        return self._preview_passed(digest)  # Explicit legacy contract doubles.

    def cancel(self,owner):
        if self.owner!=owner:raise BrokerError('goal_not_owned','Goal belongs to another connection.',status=409)
        self.review=None
        if self.demonstration and self.demonstration.owner==owner:self.demonstration.stop(owner)
        discard=getattr(self.mission.adapter_factory,'discard_review',None)
        if callable(discard):discard(owner)
        close=getattr(self.mission.adapter_factory,'close_idle',None)
        if callable(close):close(owner)

    def snapshot(self,owner):
        # Cached routes are review history, not continuously observed position.
        if self.owner!=owner:return None
        result={'review':deepcopy(self.review),'error':self.error,'current_pose_available':False,
                'motion_authorized':False,'physical_demo_ready':False,'job':None,'reference_key':self.reference_key}
        result['task_loop']=self.task_loop.snapshot(owner)
        if self.demonstration:
            result['demonstration']=self.demonstration.snapshot(owner)
            if result['demonstration']:
                result['demonstration']['receipt_current']=self._preview_passed(result['demonstration']['review_id'])
                owns=getattr(self.mission.adapter_factory,'owns_idle',None)
                reserved=getattr(self.mission.adapter_factory,'owns_review',None)
                result['demonstration']['handoff_ready']=bool(getattr(self.mission.adapter_factory,'supports_exact_goal_handoff',False) is True
                    and self.review and ((callable(owns) and owns(owner,self.review['map_id']))
                        or (callable(reserved) and reserved(owner,self.review['map_id'],self.review['plan']))))
                result['demonstration']['robot_review_parked']=bool(self.review and callable(reserved)
                    and reserved(owner,self.review['map_id'],self.review['plan']))
        if self.job_id:
            job=self.mission.snapshot(owner)['job']
            if job and job['job_id']==self.job_id:
                result['job']=job
                if job['state'] in {'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}:
                    release=getattr(self.demonstration,'finish_execution',None)
                    if callable(release):release(owner)
        return result
