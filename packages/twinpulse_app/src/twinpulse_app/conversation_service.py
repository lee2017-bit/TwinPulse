# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Durable, project-scoped chat orchestration. Text never grants motion authority.

The existing ProductWorkflow owns input validation and provider/tool execution.
This service owns questions, idempotency and explanatory product events only.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import base64
from io import BytesIO
import json
import os
import re
import time
from pathlib import Path
from threading import RLock,Thread
from uuid import uuid4

from .command_broker import BrokerError

EXACT_UNDO_COMMANDS = frozenset({'undo','undo last edit','undo last change','되돌리기','되돌려'})

def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ConversationService:
    def __init__(self, workflow, path: Path, *, clock=time.monotonic):
        self.workflow, self.path = workflow, path
        self._parent = path.parent.resolve()
        self._lock = RLock()
        self._external_started = False
        self._restore_error = None
        # Public, process-local navigation hint only. Never persisted authority.
        self._restored_session = False
        self.robot_preparation = None
        self.inspection = None
        self.navigation = None
        self.robot_fleet = None
        self.robot_tasks = None
        self._robot_task_marker = None
        self._robot_task_pending = None
        self._declared_route_pending = None
        self._inspection_marker = None
        self._inspection_review_requested = False
        self._robot_marker = None
        self._collection_marker = None
        self._goal_demonstration_marker = None
        self._clock = clock
        self._goal_progress_job = None
        self._goal_progress_at = None
        self._goal_progress_phase = None
        self._goal_terminal_marker = None
        self._goal_progress_message_id = None
        self._task_loop_marker = None
        self._request_owner = None
        self._feedback_worker=None;self._feedback_token=None;self._feedback_service=None
        self._feedback_outcome=None;self._edit_transaction_marker=None
        self._durable_scene_edit_mode=None
        self._state = {
            "schema_version": "conversation-1.0", "session_id": str(uuid4()),
            "project_id": workflow._broker.project_id, "revision": 0, "cursor": 0,
            "mode": None, "robot_id": None, "messages": [], "cards": [], "events": [],
            "generation": None, "requests": {}, "pending_input": None,
            "pending_input_origin": None,
            "thumbnails": {},
            "pending_edit": None,
            "scene_feedback": None,
            "scene_sensor_review": None,
            "queued_edit": None,
            "simulation_review": None,
            "inspection_display": None,
            "physical_authority": False,
            "twin_edit_approval": "review",  # Twin-edit approval only (review | auto); never robot motion authority
        }
        if path.exists():
            try:
                if path.is_symlink() or path.resolve().parent != self._parent:
                    raise ValueError("Conversation path is unsafe")
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError("Conversation file exceeds budget")
                stored = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(stored, dict): raise ValueError("Conversation must be an object")
                if isinstance(stored, dict) and stored.get("schema_version") == "conversation-1.0":
                    stored.setdefault("thumbnails", {})
                    stored.setdefault("pending_input_origin",None)
                    stored.setdefault("pending_edit", None)
                    stored.setdefault('scene_feedback',None)
                    stored.setdefault('scene_sensor_review',None)
                    stored.setdefault("queued_edit", None)
                    stored.setdefault("simulation_review", None)
                    stored.setdefault("inspection_display", None)
                    stored.setdefault("twin_edit_approval","review")
                    if stored["twin_edit_approval"] not in ("review","auto"):raise ValueError("Twin-edit approval mode invalid")
                if (stored.get("schema_version") != "conversation-1.0"
                        or stored.get("project_id") != self._state["project_id"]
                        or set(stored) != set(self._state)):
                    raise ValueError("Conversation identity or schema mismatch")
                if (stored["physical_authority"] is not False or not isinstance(stored["revision"], int)
                        or not isinstance(stored["cursor"], int) or not isinstance(stored["requests"], dict)
                        or any(not isinstance(stored[name], list) for name in ("messages", "cards", "events"))
                        or not isinstance(stored["thumbnails"], dict)):
                    raise ValueError("Conversation state is invalid")
                self._validate_history(stored)
                self._state = stored
                self._restored_session = bool(stored['messages'])
                self._durable_scene_edit_mode=(stored['project_id'],stored['mode'])
            except (OSError, ValueError, TypeError) as error:
                self._restore_error = {"code": "conversation_restore_invalid",
                                       "message": "Saved conversation could not be validated; original file was preserved. Review or recover it before sending."}
                return
            # Stored operation IDs are history, never permission to restart work.
            feedback=self._state['scene_feedback']
            if feedback and feedback.get('state')=='running':
                feedback.update(state='interrupted',error='App restarted. No feedback request was resumed.')
                self._message('assistant',feedback['error'],status='interrupted')
                self._event('scene_feedback_interrupted',operation_id=feedback['operation_id'])
                try:self._persist()
                except BrokerError:pass
            live_ids={e['payload'].get('message_id') for e in self._state['events']
                      if e['type']=='goal_execution_progress'}
            task_ids={e['payload'].get('task_id') for e in self._state['events'] if e['type']=='goal_task_changed'}
            live_ids.update(m['message_id'] for m in self._state['messages'] if m.get('operation_id') in task_ids)
            interrupted=False
            for message in self._state['messages']:
                if message['message_id'] in live_ids and message['status']=='pending':
                    message.update(content='Historical mission update — '+message['content'],status='interrupted')
                    interrupted=True
            if interrupted:
                self._event('goal_progress_interrupted')
                try:self._persist()
                except BrokerError:pass
            expired_robot_cards = False
            for card in self._state['cards']:
                if card['kind'].startswith('robot_') and card['kind'] not in {'robot_presence','robot_selection'} and card['state']=='waiting':
                    card['state']='expired'
                    expired_robot_cards=True
            if expired_robot_cards:
                self._message('assistant', 'App restarted. Physical preparation choices expired; no robot operation was resumed.')
                try:self._persist()
                except BrokerError:pass
            job = self._state["generation"]
            if job and job["state"] in {"accepted", "running"}:
                job.update(state="interrupted", summary="App restarted. Generation was not resumed.", can_cancel=False)
                self._message("assistant", job["summary"], status="interrupted")
                self._event("generation_interrupted", operation_id=job["operation_id"])
                if self._state['queued_edit']:
                    self._message('assistant', 'The pending edit was retained in conversation history but was not resumed after restart. Submit it again for review.')
                    self._state['queued_edit'] = None
                try:self._persist()
                except BrokerError:pass  # Expose the storage error; never restart work.

    @staticmethod
    def _validate_history(stored):
        sensor=stored.get('scene_sensor_review')
        if sensor is not None:
            from .scene_sensor_review import checked_context
            if (not isinstance(sensor,dict) or sensor.get('status') not in {'HELD','POSE_CANDIDATE','preview','cancelled','imported'} or
                    sensor.get('physical_authority') is not False or sensor.get('preview') is not None):
                raise ValueError('Saved scene sensor review invalid')
            checked_context(sensor.get('context'))
        feedback=stored.get('scene_feedback')
        if feedback is not None:
            from twinpulse_provider.scene_edit_provider import feedback_generation_request
            if (not isinstance(feedback,dict) or feedback.get('state') not in
                    {'prepared','awaiting_approval','running','clarify','preview','failed','cancelled','interrupted'} or
                    not isinstance(feedback.get('operation_id'),str) or type(feedback.get('clarification_count')) is not int or
                    feedback['clarification_count'] not in (0,1) or
                    feedback.get('error') is not None and not isinstance(feedback['error'],str)):
                raise ValueError('Saved scene feedback is invalid')
            feedback_generation_request(feedback['context'],'stored-feedback')
        pending_edit=stored.get('pending_edit')
        if pending_edit is not None:
            from twinpulse_core import canonical_sha256
            from .scene_changes import SceneChange
            if (not isinstance(pending_edit,dict) or
                    canonical_sha256(SceneChange.from_dict(pending_edit['operation']).to_dict())!=pending_edit['preview_digest']):
                raise ValueError('Saved scene edit preview is invalid')
            from .scene_edit_transaction import checked_feedback_lineage
            checked_feedback_lineage(pending_edit.get('feedback_lineage'))
            from .scene_sensor_review import checked_sensor_binding
            checked_sensor_binding(pending_edit.get('sensor_binding'))
        if stored.get('inspection_display') is not None:
            from .chat_inspection_visual import checked_descriptor
            checked_descriptor(stored['inspection_display'])
        if (not isinstance(stored['session_id'], str) or not stored['session_id']
                or type(stored['revision']) is not int or stored['revision'] < 0
                or type(stored['cursor']) is not int or stored['cursor'] < 0
                or stored['mode'] not in {None, 'SIM', 'REAL'}
                or stored['robot_id'] not in {None, 'turtlebot3_burger'}):
            raise ValueError('Conversation identity is invalid')
        if len(stored["events"]) > 2100 or len(stored["messages"]) > 1000 or len(stored["cards"]) > 500:
            raise ValueError("Conversation history exceeds budget")
        if any(not isinstance(key, str) or not 1 <= len(key) <= 128 or not isinstance(value, str)
               or not re.fullmatch(r"[0-9a-f]{64}", value) for key, value in stored["requests"].items()):
            raise ValueError("Conversation request ledger is invalid")
        message_ids = set()
        for message in stored["messages"]:
            if (not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}
                    or not isinstance(message.get("content"), str) or len(message["content"]) > 32000
                    or not isinstance(message.get("message_id"), str) or not isinstance(message.get("attachments"), list)):
                raise ValueError("Conversation message is invalid")
            if message['message_id'] in message_ids or len(message['message_id']) > 128:
                raise ValueError('Conversation message ID is invalid')
            message_ids.add(message['message_id'])
            if not isinstance(message.get('status'), str) or not isinstance(message.get('created_at'), str):
                raise ValueError('Conversation message status is invalid')
            for attachment in message["attachments"]:
                if (not isinstance(attachment, dict) or not isinstance(attachment.get("name"), str)
                        or attachment.get("media_type") not in {"image/png", "image/jpeg", "image/webp"}
                        or attachment.get("preview_url") not in {None, "/v1/product/conversation/image/" + message["message_id"]}):
                    raise ValueError("Conversation attachment reference is invalid")
        input_origin=stored.get('pending_input_origin')
        if input_origin is not None and not any(m['message_id']==input_origin and m['role']=='user' for m in stored['messages']):
            raise ValueError('Pending input origin is invalid')
        allowed = {"robot_presence":{"sim","real"}, "robot_selection":{"turtlebot3_burger"}, "scene_edit":{"apply","cancel"},
                   'robot_qualification':{'qualify','cancel'}, 'robot_observation':{'normal','problem'},
                   'robot_recheck':{'check','cancel'},'robot_initialize':{'initialize','cancel'},'robot_inspection':{'inspect','cancel'},
                   'robot_goal_confirm':{'confirm','cancel'},'robot_goal_loop':{'loop','finish'},
                   'generation_approval':{'approve','cancel'},'scene_edit_clarify':{'cancel'},
                   'scene_sensor_policy':{'align_only','correct_walls','cancel'},
                   'robot_task_plan':{'plan','cancel'},'robot_task_run':{'run','cancel'},'declared_route_run':{'run','cancel'},'declared_route_obstacles':{'add','move','skip'},'declared_route_fallback':{'fallback','cancel'}}
        card_ids = set()
        for card in stored["cards"]:
            # SIM-alpha emits a single SIM choice; historical full-product
            # cards retain SIM/REAL. Both are history, never motion authority.
            card_allowed = ( {'sim'} if isinstance(card,dict) and card.get('kind')=='robot_presence'
                and isinstance(card.get('choices'),list)
                and {c.get('id') for c in card['choices'] if isinstance(c,dict)}=={'sim'}
                else allowed.get(card.get('kind'),set()) if isinstance(card,dict) else set() )
            if isinstance(card,dict) and card.get('kind')=='scene_sensor_policy':
                from .scene_sensor_review import checked_context
                selection=card.get('sensor_selection')
                if (not isinstance(selection,dict) or set(selection)!={'context','map_id','map_revision'} or
                        not isinstance(selection['map_id'],str) or not re.fullmatch('[a-f0-9]{32}',selection['map_id']) or
                        not isinstance(selection['map_revision'],str) or not re.fullmatch('[a-f0-9]{64}',selection['map_revision'])):
                    raise ValueError('Saved sensor selection invalid')
                checked_context(selection['context'])
            if isinstance(card, dict) and (card.get('kind') == 'generation_approval' or
                    card.get('kind') in {'robot_presence','robot_selection'} and 'generation_approval' in card):
                from twinpulse_core import canonical_sha256
                preview = card.get('generation_approval')
                if (not isinstance(preview, dict) or preview.get('schema_version') != 'ordinary-generation-preview-1.0'
                        or preview.get('project_id') != stored['project_id']
                        or preview.get('physical_authority') is not False
                        or canonical_sha256({k:v for k,v in preview.items() if k != 'preview_sha256'}) != preview.get('preview_sha256')):
                    raise ValueError('Generation approval preview invalid')
            if isinstance(card, dict) and card.get('kind') in {'simulation_target','robot_goal_target'}:
                choices = card.get('choices')
                if (not isinstance(choices, list) or not 2 <= len(choices) <= 33
                        or any(not isinstance(c, dict) or not isinstance(c.get('id'), str)
                               or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', c['id']) for c in choices)):
                    raise ValueError('Simulation target choices are invalid')
                allowed[card['kind']] = {c['id'] for c in choices}
                card_allowed = allowed[card['kind']]
            # Optional choices (2026-10-26: the LiDAR card's "move" offer) must not invalidate
            # conversations saved before they existed.
            optional={'declared_route_obstacles':{'move'}}.get(card.get("kind") if isinstance(card,dict) else None,set())
            if (not isinstance(card, dict) or card.get("kind") not in allowed
                    or card.get("state") not in {"waiting", "answered", "expired", "cancelled"}
                    or not isinstance(card.get("choices"), list)
                    or not isinstance(card.get("question"), str)
                    or type(card.get("expected_session_revision")) is not int
                    or {choice.get("id") for choice in card["choices"] if isinstance(choice, dict)}-optional != card_allowed-optional):
                raise ValueError("Conversation question is invalid")
            if (not isinstance(card.get('id'), str) or card['id'] in card_ids
                    or card.get('card_id') != card['id'] or card.get('message_id') not in message_ids
                    or len(card['choices']) not in {len(card_allowed),len(card_allowed-optional)}
                    or card.get('selected_choice_id') not in card_allowed | {None}):
                raise ValueError('Conversation question identity is invalid')
            digest=card.get('related_plan_digest')
            if digest is not None and (not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest)):
                raise ValueError('Conversation question revision binding is invalid')
            card_ids.add(card['id'])
            for choice in card['choices']:
                if (not isinstance(choice, dict) or not isinstance(choice.get('label'), str)
                        or type(choice.get('enabled')) is not bool
                        or not (choice.get('disabled_reason') is None or isinstance(choice['disabled_reason'], str))):
                    raise ValueError('Conversation choice is invalid')
        last_sequence = 0
        for event in stored['events']:
            if (not isinstance(event, dict) or type(event.get('sequence')) is not int
                    or event['sequence'] <= last_sequence or event['sequence'] > stored['cursor']
                    or not isinstance(event.get('event_id'), str) or not isinstance(event.get('type'), str)
                    or not isinstance(event.get('timestamp'), str) or not isinstance(event.get('payload'), dict)):
                raise ValueError('Conversation event is invalid')
            last_sequence = event['sequence']
        job = stored["generation"]
        if job is not None and (not isinstance(job, dict) or job.get("state") not in {
                "accepted", "running", "completed", "failed", "cancelled", "interrupted"}
                or not isinstance(job.get("operation_id"), str) or not isinstance(job.get('summary'), str)
                or not isinstance(job.get('last_progress_at'), str) or type(job.get('can_cancel')) is not bool
                or not (job.get('error') is None or isinstance(job['error'], dict)
                        and isinstance(job['error'].get('code'), str) and isinstance(job['error'].get('message'), str))):
            raise ValueError("Conversation generation is invalid")
        queued = stored['queued_edit']
        if queued is not None and (not isinstance(queued, dict) or not {'text','mode','attachment'}<=set(queued)
                or set(queued)-{'text','mode','attachment','origin_message_id','request_id'}
                or queued.get('origin_message_id') is not None and queued['origin_message_id'] not in message_ids
                or not isinstance(queued['text'], str) or len(queued['text']) > 8000
                or queued['mode'] not in {'add','change'} or queued['attachment'] is not None):
            raise ValueError('Pending edit is invalid')
        review = stored['simulation_review']
        if review is not None:
            if (not isinstance(review, dict) or set(review) != {'request_id','text','scene_revision','start_source','plan','target','choices','drawing'}
                    or not isinstance(review['text'], str) or len(review['text']) > 8000
                    or review['request_id'] not in stored['requests']
                    or not isinstance(review['scene_revision'], str) or not re.fullmatch(r'[0-9a-f]{64}', review['scene_revision'])
                    or not isinstance(review['choices'], list) or len(review['choices']) > 32
                    or not isinstance(review['drawing'], dict)):
                raise ValueError('Simulation review history is invalid')
            if review['plan'] is not None:
                from twinpulse_core.revisions import canonical_sha256
                plan = review['plan']
                if (not isinstance(plan, dict) or plan.get('mode') != 'SIM' or plan.get('physical_authority') is not False
                        or plan.get('scene_revision') != review['scene_revision']
                        or plan.get('plan_id') != canonical_sha256({k:v for k,v in plan.items() if k != 'plan_id'})):
                    raise ValueError('Simulation plan history is invalid')
        for message_id, image in stored['thumbnails'].items():
            if message_id not in message_ids or not isinstance(image, str) or len(image)>2*1024*1024:
                raise ValueError('Conversation thumbnail is invalid')
            try: base64.b64decode(image, validate=True)
            except ValueError as error: raise ValueError('Conversation thumbnail is invalid') from error

    def _persist(self):
        if self._restore_error and self._restore_error['code']=='conversation_restore_invalid':
            raise BrokerError('conversation_restore_invalid',self._restore_error['message'],status=409)
        self._state["revision"] += 1
        temporary = self.path.with_name(self.path.name + ".tmp")
        encoded=json.dumps(self._state, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(encoded)>20*1024*1024:
            raise BrokerError('conversation_limit','Conversation storage limit reached. Preserve this project and use a new project for additional images.',status=409)
        try:
            if (self.path.is_symlink() or temporary.is_symlink()
                    or self.path.parent.resolve() != self._parent):
                raise OSError("Conversation path is unsafe")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            # Windows readers/AV can briefly deny delete sharing on an existing
            # destination. Retry only the already-flushed atomic rename, never
            # the product action, provider call or robot command. Permanent ACL,
            # disk and unknown failures still surface after a strict 150ms bound.
            for attempt, delay in enumerate((0, .01, .02, .04, .08)):
                if delay: time.sleep(delay)
                try:
                    os.replace(temporary, self.path)
                    break
                except OSError as error:
                    if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 4:
                        raise
            self._durable_scene_edit_mode=(self._state['project_id'],self._state['mode'])
            if self._restore_error and self._restore_error['code']=='conversation_save_failed':
                self._restore_error=None
        except OSError as error:
            self._restore_error = {'code':'conversation_save_failed',
                'message':'Conversation save failed. Fix local storage and reopen the app; no operation will be retried automatically.',
                'storage_errno':error.errno,'storage_winerror':getattr(error,'winerror',None)}
            raise BrokerError("conversation_save_failed", f"Conversation could not be saved (errno={error.errno}, winerror={getattr(error,'winerror',None)}). No automatic action retry.", status=503) from error

    def saved_sim_scene_edit_scope(self, project_id):
        # Atomic published tuple: admission already owns the physical start
        # mutex and must not acquire the conversation lock in reverse order.
        # A request-body mode or an unsaved/failed mode change is not sufficient.
        return (self._restore_error is None and self._durable_scene_edit_mode==(project_id,'SIM')
            and self._state['mode']=='SIM' and self._state['physical_authority'] is False)

    def _event(self, kind, **payload):
        self._state["cursor"] += 1
        self._state["events"].append({"event_id": str(uuid4()), "sequence": self._state["cursor"],
                                      "session_id": self._state["session_id"],
                                      "type": kind, "timestamp": now(), "payload": payload})

    def record_environment_import(self,request_id,source_name,source_sha256,scene_revision):
        """An actual Import-space menu action, never an invented model message."""
        with self._lock:
            if any(e['type']=='environment_imported' and e['payload'].get('request_id')==request_id
                   for e in self._state['events']):return
            if self._state['mode']=='REAL':raise BrokerError('environment_sim_required','Import space in a new SIM chat.')
            self._state['mode']='SIM';self._state['physical_authority']=False
            self._message('user','Menu action: Import space for SIM · '+source_name,operation_id=request_id)
            self._message('assistant','Local scanned space imported. Source geometry is preserved. '
                'Selected units and real-world alignment require review. Use Show Twin to apply the scene; '
                'add a SIM robot explicitly to test it.',operation_id=request_id)
            self._event('environment_imported',request_id=request_id,source_name=source_name,
                source_sha256=source_sha256,scene_revision=scene_revision)
            self._persist()

    def _message(self, role, content, *, attachment=None, status="completed", operation_id=None, origin_message_id=None):
        message = {"message_id": str(uuid4()), "role": role, "content": content,
                   "session_id": self._state["session_id"], "reply_to": None,
                   "attachments": [attachment] if attachment else [], "status": status,
                   "created_at": now(), "operation_id": operation_id}
        if role=='assistant':
            previous=next((item for item in reversed(self._state['messages']) if item['role']=='user'),None)
            if origin_message_id:
                previous=next((m for m in self._state['messages'] if m['message_id']==origin_message_id and m['role']=='user'),previous)
            if operation_id:
                for key in ('generation','scene_feedback','pending_edit','queued_edit','simulation_review'):
                    job=self._state.get(key)
                    if isinstance(job,dict) and job.get('operation_id')==operation_id and job.get('origin_message_id'):
                        previous=next((m for m in self._state['messages'] if m['message_id']==job['origin_message_id']),previous)
                        break
                for card in reversed(self._state['cards']):
                    if card.get('operation_id')!=operation_id:continue
                    anchor=next((m for m in self._state['messages'] if m['message_id']==card['message_id']),None)
                    if anchor and anchor.get('reply_to'):
                        previous=next((m for m in self._state['messages'] if m['message_id']==anchor['reply_to']),previous)
                        break
            message['reply_to']=previous['message_id'] if previous else None
        self._state["messages"].append(message)
        self._event("message_accepted", message_id=message["message_id"])
        return message

    def _card(self, kind, question, choices, *, origin_message_id=None):
        message = self._message("assistant", question,origin_message_id=origin_message_id)
        card = {"id": str(uuid4()), "kind": kind, "question": question, "choices": choices,
                "message_id": message["message_id"],
                "state": "waiting", "selected_choice_id": None, "operation_id": None,
                "expected_session_revision": self._state["revision"] + 1,
                "related_plan_digest": None, "expires_at": None, "created_at": now()}
        card["card_id"] = card["id"]
        if kind in {'robot_presence','robot_selection'}:
            selected = self.workflow.snapshot().get('input')
            card['related_plan_digest'] = selected['revision'] if selected else None
            approvals = getattr(self.workflow, 'generation_approvals', None)
            if approvals and approvals.enabled() and not getattr(approvals,'product_mode',False):
                try:
                    # Disclosure only. The fresh choice with an explicit cap
                    # creates a revalidated one-use scope, never a stored grant.
                    card['generation_approval'] = approvals.prepare()
                except BrokerError:
                    pass  # Keep the detailed failure path; never invent pricing.
        self._state["cards"].append(card)
        self._event("card_created", card_id=card["id"])
        return card

    @staticmethod
    def _choice(identifier, label):
        return {"id": identifier, "label": label, "enabled": True, "disabled_reason": None}

    def _sync_generation(self):
        job = self._state["generation"]
        if not job or job["state"] != "running": return
        workflow = self.workflow.snapshot()
        if workflow["generation_id"] != job["generation_id"]:
            status, summary = "interrupted", "Generation changed outside this conversation. No automatic resume."
        elif workflow["phase"] == "generating":
            progress=workflow.get('generation_progress') or {}
            if progress and progress!=job.get('progress'):
                job['progress']=progress
                job['summary']=(f"Adjusting {progress.get('stage','response')} · {progress.get('repair_count')} of {progress.get('max_repairs',1)} repair requests"
                                if progress.get('repair_count') else
                                f"{progress.get('stage','Preparing').capitalize()} · waiting for the configured model")
                job['last_progress_at']=now()
            return
        elif workflow["phase"] == "draft_ready":
            status = "completed" if not workflow["error"] else "failed"
            draft = workflow.get("site_draft") or workflow.get("draft") or {}
            summary = draft.get("summary") or "Your scene draft is ready."
            if draft.get('draft_refinement'):
                summary=('Editable Twin draft saved with pending objects preserved. '
                    if draft['draft_refinement']['acceptance']=='MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE' else
                    'Editable Twin draft saved. ')
                summary+='Furniture positions and dimensions remain estimates. Photo issues are recorded ('+draft['draft_refinement']['stop_reason']+'); you can edit the draft or review sensor observations next. Sensor correction and robot operation are not yet verified.'
            if status == "completed":
                summary += " This is an approximate draft; simulation execution and live 3D readiness are checked separately."
        elif workflow["phase"] == "cancelled": status, summary = "cancelled", "Generation stopped. No robot command was sent."
        else: status, summary = "failed", "Scene generation failed."
        error = workflow.get("error")
        if workflow.get('generation_progress'):job['progress']=workflow['generation_progress']
        if error and status == "failed": summary = error["message"]
        job.update(state=status, summary=summary, can_cancel=False, last_progress_at=now(), error=error)
        self._message("assistant", summary, status=status, operation_id=job["operation_id"])
        self._event("generation_" + status, operation_id=job["operation_id"])
        if status == 'completed' and self._state['mode'] == 'SIM':
            self._state['simulation_review'] = None
            if self._state['robot_id'] is None:
                self._message('assistant', 'Your environment Twin is saved without a SIM robot or automatic route. '
                    'View or edit the current Twin, or explicitly request a SIM goal with a start position to prepare a robot separately. Nothing moved.')
                self._event('environment_twin_ready', operation_id=job['operation_id'])
            progressive=(workflow.get('site_draft') or {}).get('progressive_twin')
            refinement=(workflow.get('site_draft') or {}).get('draft_refinement')
            if refinement:
                self._message('assistant',str(len(refinement['quality_review']['issues']))+
                    ' photo interpretation issues are retained. View or edit the current Twin. '
                    'A requested SIM task must pass its separate current geometry and safety checks; no route or motion was prepared automatically. REAL alignment remains unverified.')
                self._event('draft_visual_refinement_pending',operation_id=job['operation_id'],
                    refinement_sha256=refinement['sha256'],stop_reason=refinement['stop_reason'])
            elif progressive and progressive['unresolved']:
                self._message('assistant','A valid room draft was saved. '+str(len(progressive['unresolved']))+
                    ' objects need support-placement refinement. You can view the draft; '
                    'SIM and physical motion remain locked until their task impact is checked. '
                    'This is neither a generation failure nor full validation.')
                self._event('draft_refinement_pending',operation_id=job['operation_id'],
                    unresolved_count=len(progressive['unresolved']))
            elif self._state['robot_id'] == 'turtlebot3_burger' and workflow.get('site_draft'):
                try:
                    review = self.workflow.simulation_preview()
                    # Bind to the already accepted generation choice, not GET
                    # permission. Restored history cannot arm Web execution.
                    request_id = job['request_id']
                    self._state['simulation_review'] = {**review, 'request_id': request_id,
                                                       'text': 'Generated SIM preview'}
                    self._state['robot_id'] = review['plan']['asset_id']
                    self._message('assistant', 'Your Twin has a checked short SIM preview route. '
                        'I selected the existing supported TurtleBot3 Burger; its start is an illustrative simulated placement, not a measured robot location. '
                        'Review the route and select Run simulation, or tell me where to go. Nothing moves automatically.')
                    self._event('simulation_preview_prepared', operation_id=job['operation_id'],
                                plan_id=review['plan']['plan_id'], scene_revision=review['scene_revision'])
                except BrokerError as error:
                    self._message('assistant', 'Scene generation completed, but SIM preparation needs attention: '
                                  + str(error) + ' (' + error.code + '). Nothing moved.', status='failed')
                    self._event('simulation_preview_rejected', code=error.code, operation_id=job['operation_id'])
            elif self._state['robot_id'] is not None:
                self._message('assistant', 'This provider returned a legacy v1 warehouse, not a v2 room. '
                    'Select a supported v2 site provider for the chat room SIM flow. No room Run was prepared.', status='failed')
                self._event('simulation_preview_rejected', code='simulation_v2_scene_required', operation_id=job['operation_id'])
        self._flush_queued_edit()
        self._persist()

    def _flush_queued_edit(self):
        queued=self._state['queued_edit']
        job=self._state['generation']
        if queued and (not job or job['state'] not in {'accepted','running'}) and not self.workflow.has_active_generation():
            self._state['queued_edit'] = None
            try:
                self._edit_message(queued, record_user=False)
            except BrokerError as error:
                self._message('assistant', str(error) + ' (' + error.code + '). The queued edit was not applied.', status='failed')
                self._event('queued_edit_blocked', code=error.code)
            pending=next((message for message in reversed(self._state['messages'])
                          if message['role']=='user' and message['status']=='pending' and message['content']==queued['text']),None)
            if pending:pending['status']='completed'
            return True
        return False

    def _sync_robot(self, owner):
        if self._state['mode'] != 'REAL' or self.robot_preparation is None:return
        observed = self.robot_preparation.snapshot(owner)
        if not observed['owned']:return
        collection=observed.get('collection') or {}
        marker=(observed['attempt_id'],observed['state'],observed['code'])
        if marker == self._robot_marker:return
        self._robot_marker=marker
        for card in self._state['cards']:
            if card['kind'] in {'robot_qualification','robot_observation','robot_recheck','robot_initialize'} and card['state']=='waiting':card['state']='expired'
        phase=observed['state']
        if phase=='AWAITING_QUALIFICATION':
            card=self._card('robot_qualification', 'Run one short drive and stop verification?',
                [self._choice('qualify','Run once · 0.03 m/s for 0.6 s'), self._choice('cancel','Not now')])
            card['related_plan_digest']=observed['binding']
            self._message('assistant', 'Before Run once: disconnect charging, watch the robot on a level floor and keep at least 30 cm clear. This click approves only the fixed trial, not a route or autonomous mission.')
        elif phase=='AWAITING_OBSERVATION':
            card=self._card('robot_observation', 'Was the short movement and stop normal, without collision or unexpected motion?',
                [self._choice('normal','Movement and stop were normal'), self._choice('problem','Report a problem')])
            card['related_plan_digest']=observed['binding']
        elif phase in {'BLOCKED','EXPIRED'}:
            self._message('assistant', f"Robot preparation needs attention at {observed['stage']}: {observed['code']}. Scene generation is independent. No automatic retry or mission start.",status='failed')
            if observed.get('cleanup_error'):
                self._message('assistant','Robot cleanup also needs attention: '+observed['cleanup_error'],status='failed')
            # Failed stop trials remain consumed. Rechecking observes only; it
            # cannot discard the trial, redeploy or override the stop policy.
            if observed['code']=='TORQUE_ENABLED_INITIALIZATION_REQUIRED':
                self._message('assistant','SSH and board observation succeeded. Wheels and command bytes were zero, but motor torque was enabled. A read-only retry cannot turn it off. Explicit initial-state preparation is required; no drive or sensor starts.')
                card=self._card('robot_initialize','Prepare a safe initial state before the stop test?',
                    [self._choice('initialize','I approve reviewed source transfer and Motor OFF; I am watching on battery power with a level, clear floor'),self._choice('cancel','Not now')])
                card['related_plan_digest']=observed['binding']
            else:
                self._card('robot_recheck','Request a fresh read-only connection observation?',
                           [self._choice('check','Check connection again'),self._choice('cancel','Not now')])
        elif phase=='LINKED':
            self._message('assistant', 'Robot connection and stop record reviewed. Survey/coordinate alignment and mission admission are separate gates; no autonomous movement is authorized.')
        elif phase=='COLLECTION_RESULT':
            self._message('assistant','Stationary collection result: '+str(observed['code'])+'. Review each sensor and raw transfer below. No alignment, driver start or mission was authorized.',
                          status='failed' if collection.get('status') in {'REMOTE_STATE_UNKNOWN','LOCAL_RECORD_UNREADABLE','BLOCKED_LOCAL'} else 'completed')
        self._event('robot_preparation_changed',state=phase,code=observed['code'],attempt_id=observed['attempt_id'])
        self._persist()

    def _sync_collection(self,owner):
        if self._state['mode']!='REAL' or not self.robot_preparation:return
        observed=self.robot_preparation.snapshot(owner)
        collection=observed.get('collection') or {}
        transfer=collection.get('recovery') or {}
        physical_transfer=((observed.get('evidence') or {}).get('evidence_recovery') or {})
        marker=(collection.get('job_id'),collection.get('status'),transfer.get('status'),physical_transfer.get('status'))
        if marker==self._collection_marker:return
        self._collection_marker=marker
        for label,result in (('Stationary raw transfer',transfer),('Qualification raw transfer',physical_transfer)):
            if result.get('status') in {'COMPLETE','INCOMPLETE','INTERRUPTED'}:
                self._message('assistant',label+': '+result['status']+
                    ('. Cause: '+str(result['reason']) if result.get('reason') else '')+
                    '. This does not change the original collection or grant motion.',
                    status='completed' if result['status']=='COMPLETE' else 'failed')
        self._event('robot_collection_changed',job_id=collection.get('job_id'),status=collection.get('status'),transfer=transfer.get('status'))
        self._persist()

    def _sync_inspection(self,owner):
        if self._state['mode']!='REAL' or not self.inspection:return
        result=self.inspection.snapshot(owner)
        ready=result.get('readiness') or {}
        binding=ready.get('binding') if ready.get('ready') else None
        marker=(result['state'],result.get('job_id'),binding,result.get('error'),result.get('cleanup_error'),result.get('report_error'))
        if marker==self._inspection_marker:return
        self._inspection_marker=marker
        changed=False
        for card in self._state['cards']:
            if card['kind']=='robot_inspection' and card['state']=='waiting':card['state']='expired';changed=True
        if not binding and not result.get('owned') and not changed:return
        if binding and (not result.get('owned') or self._inspection_review_requested):
            card=self._card('robot_inspection','Inspect this Twin with a bounded robot survey?',
                [self._choice('inspect','Start inspection · bounded movement and LiDAR'),self._choice('cancel','Not now')])
            card['related_plan_digest']=binding
            correction=' Validated bounded wall changes may be saved as a derived room revision; the original is preserved.' if ready.get('photo_policy')=='correct_walls' else ''
            self._message('assistant','The current Twin and robot adapter are ready for an inspection request. Keep charging disconnected and supervise on a clear level floor. This one approval allows a maximum 45-second local survey and photo alignment only, not goal travel.'+correction)
        elif result.get('owned') and result['state']=='SURVEY_COMPLETE':
            from .chat_inspection_visual import KIND
            self._state['inspection_display']={'kind':KIND,'mission_id':result['job_id'],
                                               'manifest_sha256':result['report_revision']}
            self._message('assistant','Inspection completed and its report was saved. Photo alignment is a candidate, not measured validation. The final pose is historical; a new goal requires fresh current observations and a separate route confirmation.')
        elif result.get('owned') and result['state']=='FAILED':
            causes=[str(result[key]) for key in ('error','cleanup_error','report_error') if result.get(key)]
            self._message('assistant','Inspection failed: '+'; '.join(causes)+'. No automatic retry or goal travel.',status='failed')
        self._event('inspection_changed',state=result['state'],job_id=result.get('job_id'),code=ready.get('code'))
        self._inspection_review_requested=False
        self._persist()

    def _sync_goal_demonstration(self,owner):
        if self._state['mode']!='REAL' or not self.navigation:return
        observed=self.navigation.snapshot(owner)
        self._sync_goal_execution(observed)
        self._sync_task_loop(owner,observed)
        demo=observed.get('demonstration') if observed else None
        if not demo:return
        marker=(demo['review_id'],demo['state'],demo.get('receipt_current'))
        for card in self._state['cards']:
            if card['kind']=='robot_goal_confirm' and card['state']=='waiting' and card.get('related_plan_digest')==demo['review_id']:
                ready=self.navigation.can_confirm()
                reason=(None if ready else 'Isaac preview completed; an owned review and qualified execution handoff are required.'
                    if demo['state']=='COMPLETED' and demo.get('receipt_current') else
                    'The exact route requires a current, completed Isaac 3D preview. Physical execution remains locked.')
                card['choices'][0].update(enabled=ready,disabled_reason=reason)
        if marker==self._goal_demonstration_marker:return
        self._goal_demonstration_marker=marker
        if demo['state']=='COMPLETED':
            self._message('assistant',('Isaac finished the exact reviewed route using live PhysX pose. This is SIM-only, not real motion or measured room validation. '+
                ('The robot is idle during review. Confirm opens a fresh observation and rechecks the complete reviewed path before driving.'
                    if observed['demonstration'].get('robot_review_parked') and self.navigation.can_confirm()
                    else 'Confirm rechecks current robot evidence.' if self.navigation.can_confirm()
                    else 'Physical Confirm remains locked: the owned review or qualified execution handoff is unavailable.'))
                if demo.get('receipt_current') else 'The earlier Isaac route receipt is no longer current. Request a new preview; physical Confirm stays locked. Nothing restarts automatically.')
        elif demo['state'] in {'FAILED','CANCELLED'}:
            self._message('assistant','Isaac route preview '+demo['state'].lower()+': '+str(demo['error'])+'. No physical movement was authorized.',status='failed')
            if demo.get('cleanup_error'):self._message('assistant','SIM cleanup: '+demo['cleanup_error'],status='failed')
        self._event('goal_demonstration_changed',plan_id=demo['review_id'],state=demo['state'],receipt_current=demo.get('receipt_current',False))
        self._persist()

    def _sync_task_loop(self,owner,observed):
        loop=getattr(self.navigation,'task_loop',None)
        if not loop or not observed:return
        task=observed.get('task_loop')
        if task:
            marker=(task['task_id'],task['state'],task['leg'],task.get('error'),task.get('cleanup_error'),task.get('worker_active'))
            if marker!=self._task_loop_marker:
                for previous in self._state['messages']:
                    if previous.get('operation_id')==task['task_id'] and previous['status']=='pending':
                        previous.update(content='Historical repeat update — '+previous['content'],status='completed')
                status='failed' if task['state']=='FAILED' else 'pending' if task.get('worker_active') else 'completed'
                causes='; '.join(str(task[k]) for k in ('error','cleanup_error') if task.get(k))
                self._message('assistant',f"Repeat A ↔ B · {task['state']} · leg {task['leg']} to {task['destination']} · {task['completed_legs']} completed. "
                    + (causes+'. ' if causes else '')
                    +'Each leg keeps its 45-second budget and fresh sensor/Isaac gates. Stop cancels new legs; failed or restored tasks never restart. Motor load measurement is unsupported.',
                    status=status,operation_id=task['task_id'])
                self._event('goal_task_changed',task_id=task['task_id'],state=task['state'],leg=task['leg'])
                self._task_loop_marker=marker;self._persist()
        job=observed.get('job')
        # Never offer a leg's return as a new first-task approval.
        if task and task.get('worker_active'):return
        offer=loop.offer(owner,job)
        if not offer:return
        digest=offer['task_digest']
        if any(c['kind']=='robot_goal_loop' and c.get('related_plan_digest')==digest for c in self._state['cards']):return
        for card in self._state['cards']:
            if card['kind']=='robot_goal_loop' and card['state']=='waiting':card['state']='expired'
        card=self._card('robot_goal_loop',f"Arrived. Repeat between A {offer['a']} and B {offer['b']} until Stop or a guard failure?",
                        [self._choice('loop','Repeat A ↔ B'),self._choice('finish','Finish task')])
        card['related_plan_digest']=digest
        self._event('goal_task_offered',task_digest=digest,first_job_id=job['job_id']);self._persist()

    def _sync_goal_execution(self, observed):
        """Owned worker observations -> chat, never commands or paid calls.

        Polling pauses produce one latest summary, not stale catch-up frames.
        Saved messages cannot attach, restart or authorize a worker.
        """
        from .goal_progress import describe_goal_job, TERMINAL
        job=observed.get('job') if observed else None
        if not job:return
        identity=job['job_id'];phase=job['state'];tick=self._clock()
        if identity!=self._goal_progress_job:
            self._goal_progress_job=identity;self._goal_progress_at=tick
            self._goal_progress_phase=None;self._goal_terminal_marker=None
            self._goal_progress_message_id=None
        if phase in TERMINAL:
            from twinpulse_core.cleanup_diagnostics import checked_notes
            native=checked_notes(job.get('native_cleanup_errors',[]))
            marker=(identity,phase,job.get('error'),job.get('cleanup_error'),job.get('report_error'),
                    job.get('report_status'),job.get('worker_active'),json.dumps(native,sort_keys=True))
            if marker==self._goal_terminal_marker:return
            signature=list(marker)
            if any(e['type']=='goal_execution_terminal' and e['payload'].get('signature')==signature
                   for e in self._state['events']):
                self._goal_terminal_marker=marker;return
            content,status=describe_goal_job(job,terminal=True)
            previous=next((m for m in self._state['messages'] if m['message_id']==self._goal_progress_message_id),None)
            if previous and previous['status']=='pending':
                previous.update(content='Historical mission update — '+previous['content'],status='completed')
            self._message('assistant',content,status=status,operation_id=identity)
            self._event('goal_execution_terminal',job_id=identity,state=phase,signature=signature)
            self._goal_terminal_marker=marker
        else:
            urgent=(phase=='STOPPING' and self._goal_progress_phase!=phase
                    or phase=='LOCALIZING' and self._goal_progress_phase in {'DRIVING','REPLANNING'})
            if not urgent and tick-self._goal_progress_at<5.:
                self._goal_progress_phase=phase;return
            content,status=describe_goal_job(job)
            content+=' Updated at '+now()+' (PC summary time).'
            previous=next((m for m in self._state['messages'] if m['message_id']==self._goal_progress_message_id),None)
            if previous:previous.update(content=content,status=status)
            else:self._goal_progress_message_id=self._message('assistant',content,status=status,operation_id=identity)['message_id']
            self._event('goal_execution_progress',job_id=identity,state=phase,message_id=self._goal_progress_message_id)
        self._goal_progress_at=tick;self._goal_progress_phase=phase
        self._persist()

    def _sync_fleet_registrations(self):
        receipts=getattr(self.robot_fleet,'registration_receipts',None)
        if not callable(receipts):return
        # Consume factual menu receipts on the chat observation path. Never
        # put conversation fsync/locks on held-drive, Stop or telemetry paths.
        known={e['payload']['registration']['request_id'] for e in self._state['events']
               if e['type']=='fleet_sim_registered'}
        pending=[r for r in receipts(self._state['session_id']) if r['request_id'] not in known]
        if not pending:return
        if len(self._state['messages'])+2*len(pending)>1000 or len(self._state['events'])+3*len(pending)>2100:
            raise BrokerError('conversation_limit','Robot registration was accepted but chat history is full. Preserve this project; no robot action was replayed.',status=409)
        for receipt in pending:
            x,y,yaw=receipt['position_m']
            action=self._message('user',f"Menu action · Add SIM robot: {receipt['label']}. "
                f"Start X={x:g} m, Y={y:g} m, yaw={yaw:g} rad (SIM scene coordinates).")
            message=self._message('assistant',f"SIM robot registered: {receipt['label']}. "
                "Model: TurtleBot3 Burger (built-in SIM model; not selected by the name). "
                f"Start X={x:g} m, Y={y:g} m, yaw={yaw:g} rad. "
                "Registration does not connect, display or move the robot. Select it, then use Connect and Prepare separately. "
                f"Robot ID: {receipt['robot_id']}.",origin_message_id=action['message_id'])
            self._event('fleet_sim_registered',registration=deepcopy(receipt),menu_message_id=action['message_id'],message_id=message['message_id'])
        self._persist()

    def snapshot(self, owner=None):
        with self._lock:
            if self._restore_error is None:
                self._sync_feedback(owner)
                self._sync_generation()
                self._sync_collection(owner)
                self._sync_robot(owner)
                self._sync_inspection(owner)
                self._sync_goal_demonstration(owner)
                self._sync_fleet_registrations()
                self._sync_robot_tasks(owner)
                if self._flush_queued_edit():self._persist()
            public = deepcopy(self._state)
            # Attachment bytes are retained locally for a pending restart, not
            # reflected into each polling response or sent to a model twice.
            public.pop("pending_input")
            public.pop("thumbnails")
            public.pop("pending_edit")
            public['scene_feedback']=({k:v for k,v in public['scene_feedback'].items() if k in
                {'operation_id','state','error','progress','clarification_count','request_id','approval_id','execution_id','origin_message_id'}} if public['scene_feedback'] else None)
            public['scene_edit_preview']=deepcopy(self._state['pending_edit'])
            public['scene_edit_transaction']=self.workflow.scene_edit_transaction.snapshot(owner)
            public['queued_edit'] = {'text': public['queued_edit']['text'], 'state':'pending'} if public['queued_edit'] else None
            public["accepted_request_ids"] = list(public["requests"])
            public.pop("requests")
            public["restore_error"] = self._restore_error
            public['restored_session'] = self._restored_session
            approvals = getattr(self.workflow, 'generation_approvals', None)
            observed_enabled = getattr(approvals, 'observed_enabled', None)
            public['budgeted_generation_available'] = bool(callable(observed_enabled) and observed_enabled())
            current_job = self._state['generation']
            settling = getattr(self.workflow, 'generation_settling', lambda generation_id: False)
            public['generation_settling'] = ({
                'operation_id': current_job['operation_id'],
                'generation_id': current_job['generation_id'],
            } if current_job and current_job['state'] == 'cancelled'
                and settling(current_job.get('generation_id')) else None)
            public['robot_preparation'] = self.robot_preparation.snapshot(owner) if self._state['mode']=='REAL' and self.robot_preparation else None
            public['inspection'] = self.inspection.snapshot(owner) if self._state['mode']=='REAL' and self.inspection else None
            public['navigation'] = self.navigation.snapshot(owner) if self._state['mode']=='REAL' and self.navigation else None
            public['robot_task'] = self.robot_tasks.snapshot(owner) if self.robot_tasks else None
            descriptor=self._state['inspection_display']
            public['inspection_display']=(self.inspection.display_readiness(descriptor)
                if descriptor and self._state['mode']=='REAL' and self.inspection else None)
            public['room_build'] = None
            job=self._state['generation']
            workflow=(self.workflow.snapshot() if self._state['mode']=='REAL' and job and job['state']=='completed' else None)
            if (workflow is not None
                    and job['generation_id']==workflow['generation_id'] and workflow['phase']=='draft_ready'
                    and workflow.get('site_draft')):
                draft=workflow['site_draft']
                public['room_build']={'operation_id':job['operation_id'],'scene_revision':draft['revision'],
                                      'artifact_id':draft['artifact_id']}
            return public

    def image(self, message_id):
        with self._lock:
            value = self._state["thumbnails"].get(message_id)
            if not isinstance(value, str):
                raise BrokerError("chat_image_missing", "Saved image preview is not available", status=404)
            return base64.b64decode(value, validate=True)

    def dispatch(self, body, owner=None):
        with self._lock:
            if self._restore_error:
                raise BrokerError(self._restore_error['code'],self._restore_error['message'],status=409)
            self._request_owner=owner
            self._sync_feedback(owner)
            self._sync_generation()
            self._sync_collection(owner)
            self._sync_robot(owner)
            self._sync_inspection(owner)
            if self._restore_error:
                raise BrokerError(self._restore_error["code"], self._restore_error["message"], status=409)
            if not isinstance(body, dict): raise BrokerError("chat_shape_invalid", "Chat request must be an object", status=400)
            action = body.get("action")
            shapes = {"message": {"action", "request_id", "text", "attachment", "mode"},
                      "answer": {"action", "request_id", "card_id", "choice_id", "expected_session_revision"},
                      "cancel": {"action", "request_id", "operation_id"}}
            shapes["resume"] = {"action", "request_id", "expected_scene_revision", "expected_input_revision"}
            shapes['robot_check']={'action','request_id'}
            shapes['inspection_check']={'action','request_id'}
            shapes['robot_collect']={'action','request_id','expires_at_ms','confirmed_source_transfer'}
            shapes['robot_transfer']={'action','request_id','expires_at_ms','kind','job_id'}
            shapes['generation_retry']={'action','request_id','operation_id'}
            shapes['twin_edit_approval']={'action','request_id','mode'}
            shapes['sensor_review']={'action','request_id','map_id','expected_map_revision','expected_scene_revision','expected_state_sha256'}
            shapes['sensor_import']={'action','request_id','mission_id','expected_report_revision','expected_scene_revision','expected_state_sha256'}
            valid_shape=isinstance(action,str) and action in shapes and (set(body)==shapes[action] or
                action=='answer' and set(body) in (shapes[action]|{'expires_at_ms'}, shapes[action]|{'limit_usd'}))
            if not valid_shape:
                raise BrokerError("chat_shape_invalid", "Chat request fields are invalid", status=400)
            if action=='answer' and (any(not isinstance(body[key],str) or not 1<=len(body[key])<=128 for key in ('card_id','choice_id'))
                    or type(body['expected_session_revision']) is not int or body['expected_session_revision']<0):
                raise BrokerError('chat_shape_invalid','Question identity and integer revision are required',status=400)
            if action in {'cancel','resume','generation_retry'}:
                fields=('operation_id',) if action in {'cancel','generation_retry'} else ('expected_scene_revision','expected_input_revision')
                if any(not isinstance(body[key],str) or not 1<=len(body[key])<=128 for key in fields):
                    raise BrokerError('chat_shape_invalid','Bounded operation and revision identities are required',status=400)
            if action=='robot_transfer' and (body['kind'] not in ('stationary','qualification')
                    or not isinstance(body['job_id'],str) or not re.fullmatch('[a-f0-9]{32}',body['job_id'])):
                raise BrokerError('chat_shape_invalid','Known transfer kind and saved job ID are required',status=400)
            if action=='sensor_review' and any(not isinstance(body[key],str) or
                    not re.fullmatch('[a-f0-9]{32}' if key=='map_id' else '[a-f0-9]{64}',body[key])
                    for key in ('map_id','expected_map_revision','expected_scene_revision','expected_state_sha256')):
                raise BrokerError('chat_shape_invalid','Exact saved map and current Twin SHA identities are required.',status=400)
            if action=='sensor_import' and any(not isinstance(body[key],str) or
                    not re.fullmatch('[a-f0-9]{32}' if key=='mission_id' else '[a-f0-9]{64}',body[key])
                    for key in ('mission_id','expected_report_revision','expected_scene_revision','expected_state_sha256')):
                raise BrokerError('chat_shape_invalid','Exact completed survey and current Twin SHA identities are required.',status=400)
            request_id = body.get("request_id")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise BrokerError("request_id_invalid", "A bounded request ID is required", status=400)
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            previous = self._state["requests"].get(request_id)
            if previous:
                if previous != digest: raise BrokerError("request_id_conflict", "Request ID was used for different content", status=409)
                return self.snapshot(owner)
            if len(self._state["events"]) >= 2000:
                raise BrokerError("conversation_limit", "Conversation limit reached; save this project before starting another session", status=409)
            backup = deepcopy(self._state)
            self._external_started = False
            self._state["requests"][request_id] = digest
            try:
                if action == "message": self._accept_message(body)
                elif action == "answer": self._answer(body)
                elif action=='twin_edit_approval':self._set_twin_edit_approval(body)
                elif action=='sensor_import':
                    if (any(c['state']=='waiting' for c in self._state['cards']) or self.workflow.has_active_generation() or
                            self._feedback_worker and self._feedback_worker.is_alive()):
                        raise BrokerError('conversation_busy','Finish the current question before importing a completed survey.',status=409)
                    adapter=self.workflow.scene_sensor_review
                    if adapter is None:raise BrokerError('scene_sensor_unavailable','Saved sensor history is unavailable.',status=409)
                    self._external_started=True
                    result=adapter.surveys.run(body,owner)
                    self._state['scene_sensor_review']=result
                    self._message('user','Import completed saved survey '+body['mission_id']+'. No live operation.')
                    self._message('assistant',('Saved survey imported as map '+result['map_id']+'. Choose that map and review one sensor policy; the Twin is unchanged.'
                        if result['status']=='imported' else 'Saved survey import held: '+result['reason']+'. The Twin is unchanged.'))
                    self._event('scene_sensor_import',status=result['status'],execution_id=result['execution_id'])
                elif action=='sensor_review':
                    if (any(c['state']=='waiting' for c in self._state['cards']) or self.workflow.has_active_generation() or
                            self._feedback_worker and self._feedback_worker.is_alive()):
                        raise BrokerError('conversation_busy','Finish the current question before selecting saved sensor feedback.',status=409)
                    adapter=self.workflow.scene_sensor_review
                    if adapter is None:raise BrokerError('scene_sensor_unavailable','Saved sensor history is unavailable.',status=409)
                    selection=adapter.select(body)
                    self._message('user','Review saved sensor map '+selection['map_id']+' against the current Twin. No robot operation.')
                    card=self._card('scene_sensor_policy','How should this saved sensor evidence be reviewed?',[
                        self._choice('align_only','Pose only · no geometry change'),
                        self._choice('correct_walls','Review bounded wall changes'),self._choice('cancel','Cancel sensor review')])
                    card['sensor_selection']=selection
                    card['related_plan_digest']=selection['context']['current_state_sha256']
                elif action=='inspection_check':
                    if self._state['mode']!='REAL' or not self.inspection:
                        raise BrokerError('inspection_unavailable','Select a physical robot before reviewing inspection readiness.',status=409)
                    if self.inspection.active(owner):
                        raise BrokerError('inspection_busy','Inspection is active. Use Stop, not another confirmation.',status=409)
                    self._inspection_marker=None
                    self._inspection_review_requested=True
                    self._sync_inspection(owner)
                elif action=='generation_retry':
                    job=self._state['generation']
                    if (not job or job['operation_id']!=body['operation_id'] or job['state'] not in {'failed','cancelled','interrupted'}
                            or any(c['state']=='waiting' for c in self._state['cards'])
                            or self.workflow.has_active_generation() or not self._state.get('pending_input')):
                        raise BrokerError('generation_retry_stale','Finish the current step; retry must refer to the current failed generation.',status=409)
                    self._message('user','Review a new scene-generation action using the original input. No automatic retry or budget renewal.')
                    self._start_generation(request_id, review_resume=True)
                elif action in {'robot_check','robot_collect','robot_transfer'}:
                    if self._state['mode']!='REAL' or self._state['robot_id']!='turtlebot3_burger' or not self.robot_preparation:
                        raise BrokerError('chat_robot_selection_required','Select your physical robot before checking its connection.',status=409)
                    self._persist()
                    self._external_started=True
                    try:
                        if action=='robot_check':
                            self.robot_preparation.check(owner,correlation={'workflow_id':self._state['session_id']})
                            self._message('assistant','One read-only robot check requested. No driver, deployment or movement starts.')
                        elif action=='robot_collect':
                            self.robot_preparation.collect(owner,body['expires_at_ms'],body['confirmed_source_transfer'])
                            self._message('assistant','One approved stationary collection requested, including reviewed source transfer. No motor enable, motion or LiDAR driver start. Old link evidence is invalidated; no automatic retry.')
                        else:
                            self.robot_preparation.resume_evidence(owner,body['kind'],body['job_id'],body['expires_at_ms'])
                            self._message('assistant','Saved raw-file transfer requested. Collection, deployment and motion are not repeated. Earlier collection failures remain unchanged.')
                    except BrokerError as error:
                        self._message('assistant',str(error)+' ('+error.code+'). No automatic retry.',status='failed')
                    self._sync_robot(owner)
                elif action == "resume":
                    if any(c['state']=='waiting' for c in self._state['cards']) or self.workflow.has_active_generation():
                        raise BrokerError('conversation_busy', 'Finish the current question or generation before reopening a scene', status=409)
                    self._persist()
                    self._external_started = True
                    try:
                        self.workflow.resume_saved_scene(self._state["project_id"], body["expected_scene_revision"], body["expected_input_revision"])
                    except BrokerError as error:
                        self._message('assistant', str(error) + ' (' + error.code + '). Saved scene was not reopened.', status='failed')
                        self._event('scene_reopen_failed', code=error.code)
                    else:
                        self._message("assistant", "Saved scene reopened for review. Original input and edit history were validated. No build, simulation or robot motion was started.")
                        self._event("scene_reopened", scene_revision=body["expected_scene_revision"])
                else: self._cancel(body)
                self._persist()
            except Exception:
                # A committed external start must not become retryable when a
                # later disk write fails. Query the same operation ID instead.
                if not self._external_started:
                    self._state = backup
                raise
            return self.snapshot(owner)

    def _fleet_message(self,body,*,command_text=None):
        from .robot_fleet import parse_robot_command
        try:parsed=parse_robot_command(command_text or body['text'])
        except BrokerError:parsed=None
        if parsed and parsed['action'] in {'stop','stop_all'}:
            if getattr(self,'declared_routes',None) is not None:self.declared_routes.cancel()
            self._robot_task_pending=None
            for card in self._state['cards']:
                if card['kind'] in {'robot_task_plan','robot_task_run'} and card['state']=='waiting':card['state']='cancelled'
        self._message('user',body['text'])
        try:
            self._external_started=True
            result=self.robot_fleet.action(dict(action='command',request_id=body['request_id'],robot_id=None,
                connection_epoch=None,motion_epoch=None,payload=dict(text=command_text or body['text'])),self._request_owner)
            command=result['last_command'] or {}
            robot=next((r for r in result['robots'] if r['robot_id']==command.get('robot_id')),None)
            detail=(robot['label']+' · '+robot['control_state']+' · '+(robot.get('reason') or 'request accepted')) if robot else 'All connected robots: Stop requested.'
            operation=command.get('operation_id')
            self._message('assistant',detail+((' · Operation '+operation) if operation else '')+
                '. Follow the Twin robot controller for measured progress.',operation_id=operation)
            self._event('robot_fleet_command',operation_id=operation,robot_id=command.get('robot_id'),request_id=body['request_id'])
        except BrokerError as error:
            self._message('assistant',str(error))
            self._event('robot_fleet_command_blocked',code=error.code,request_id=body['request_id'])

    def _declared_route_request(self,text):
        """Survey-and-return on an imported Twin runs the declared-start route (Path B)."""
        from twinpulse_core.robot_task_plan import task_request
        runner=getattr(self,'declared_routes',None);fleet=self.robot_fleet
        scene=getattr(fleet,'navigation_scene',None)
        if runner is None or not fleet.focused or not scene or scene['geometry'].get('schema')!='scene-navigation-2.0':return False
        value=text.strip().lower()
        # Same scene-edit/creation exclusions as the common task hint.
        if not task_request(value,(fleet.robots.get(fleet.focused) or {}).get('kind')):return False
        back=re.search(r'돌아와|복귀|\b(?:return|come back|go back)\b',value)
        return bool(back and (re.search(r'둘러|탐색|순회|\b(?:survey|explore|patrol|look around)\b',value)
                              or ('via' in value or '경유' in value) and self._route_stops(value)))

    @staticmethod
    def _route_stops(text):
        """Clicked route stops typed as '(x, y)' pairs, e.g. 'Survey via (1.2, 0.8), (2.0, 1.5) and come back'."""
        pairs=re.findall(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)',text or '')
        return [[float(x),float(y)] for x,y in pairs][:8]

    def _route_candidates_request(self,text):
        value=text.strip().lower()
        return getattr(self,'add_route_obstacles',None) is not None and bool(
            re.search(r'\blidar\b',value) and re.search(r'\b(?:add|put|reflect|apply)\b',value) and re.search(r'\btwin\b',value))

    def _offer_saved_route_candidates(self,body):
        """Re-offer the LiDAR candidates of the latest finished route (e.g. after an App restart)."""
        if any(c['state']=='waiting' for c in self._state['cards']):
            raise BrokerError('choice_required','Finish the current question before requesting another task.',status=409)
        self._message('user',body['text'])
        folder=self.robot_fleet.root/'declared-routes';latest=None
        for path in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
            try:record=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError):continue
            if record.get('state')=='COMPLETED' and record.get('candidates'):latest=record;break
        if latest is None:
            self._message('assistant','No finished route with LiDAR candidates was found. Run "Survey the room and come back" first.');return
        candidates=latest['candidates'];plan=latest['plan']
        listing='; '.join('#%d at (%.2f, %.2f) m, %d returns'%(i+1,*c['position_xy_m'],c['returns']) for i,c in enumerate(candidates))
        card=self._card('declared_route_obstacles','The last route\'s LiDAR saw %d object%s the Twin does not have: %s. '
            'Positions come from the declared start + wheel odometry (not localized). Add them to the Twin as unknown obstacles? '
            'This edits the Twin (Undo available); no robot moves.'%(len(candidates),'' if len(candidates)==1 else 's',listing),
            [self._choice('add','Add to Twin'),self._choice('skip','Skip')])
        card['operation_id']=plan['plan_id'];self._route_candidates=dict(plan_id=plan['plan_id'],candidates=candidates)

    def _set_twin_edit_approval(self,body):
        """Review (default): LiDAR boxes, LiDAR moves and photo replacements wait for Apply. Auto: they are applied
        through the same Twin edit transaction (Engine ACK, Undo) with a chat notice each. Robot motion guards and
        the Run route decision are untouched in both modes; this is not a robot safety mode."""
        mode=body['mode']
        if mode not in ('review','auto'):raise BrokerError('chat_shape_invalid','Twin-edit approval mode must be review or auto.',status=400)
        previous=self._state['twin_edit_approval'];self._state['twin_edit_approval']=mode
        if mode!='auto':self._auto_route_edits=[]
        self._message('user','Twin edits: '+('Auto-apply' if mode=='auto' else 'Review'))
        self._message('assistant',('Twin-edit auto-apply is on: LiDAR outline boxes, LiDAR position corrections and photo replacements are applied as soon as they are previewed, each through the normal Twin edit transaction (Engine ACK, Undo available) with a notice here. '
            'Robot motion is unchanged: Run route, Stop, proximity, voltage and arming checks still need you.') if mode=='auto' else
            'Twin edits are back to Review: each LiDAR box, LiDAR move or photo replacement waits for your Apply.')
        self._event('twin_edit_approval',mode=mode,previous=previous)

    def _start_declared_route(self,body):
        if any(c['state']=='waiting' for c in self._state['cards']):
            raise BrokerError('choice_required','Finish the current question before requesting another task.',status=409)
        if self.declared_routes.active():raise BrokerError('declared_route_active','A route is already running; Stop it first.',status=409)
        self._message('user',body['text'])
        self._last_route_text=body['text']  # session-only: Twin-edit auto-apply re-plans this request after its edits
        stops=self._route_stops(body['text'])
        tasks=getattr(self,'robot_tasks',None)
        if not stops and tasks is not None and getattr(tasks,'registry',None) is not None and not tasks.active():
            # Hackathon flow: the configured planner (NVIDIA Nemotron via Nebius Token Factory) reads the
            # instruction first; its validated plan then hands over to the deterministic Path B route.
            try:job=tasks.propose(body['text'],self._request_owner,body['request_id'])
            except BrokerError as error:
                self._message('assistant','The planner could not be called: '+str(error)+' ('+error.code+').')
                self._offer_route_fallback(body['text'],body['request_id'],'planner unavailable: '+error.code);return
            self._route_model_pending=dict(request_id=body['request_id'],text=body['text'],task_id=job['task_id'],started=time.monotonic())
            self._message('assistant','Planning with '+str(job.get('model_id') or 'the configured planner')+' via Nebius Token Factory: one text-only call with the instruction and the capability names (no photos, coordinates or sensor logs). The route itself is then planned on the Twin.')
            self._event('declared_route_model_planning',task_id=job['task_id'],request_id=body['request_id'])
            return
        self._plan_declared_route(body['text'],body['request_id'],stops=stops or None,
            planned_by=dict(kind='operator_stops',label='Operator stops · no model call') if stops else dict(kind='deterministic',label='Deterministic planner · no model configured'))

    def _offer_route_fallback(self,text,request_id,reason):
        card=self._card('declared_route_fallback','The model planning step did not complete ('+reason[:200]+'). Use the deterministic Path B planner instead? '
            'This is labeled as a fallback on the route card; no model is involved and nothing moves until you confirm the route.',
            [self._choice('fallback','Use deterministic route (fallback)'),self._choice('cancel','Cancel')])
        card['operation_id']=request_id;self._route_fallback_pending=dict(text=text,request_id=request_id,reason=reason)

    def _plan_declared_route(self,text,request_id,*,stops=None,planned_by=None):
        try:plan=self.declared_routes.plan(self.robot_fleet.focused,stops=stops or None)
        except BrokerError as error:
            detail=str(error)
            if stops and 'BLOCKED' in detail:detail='A chosen stop is not on free floor with the robot berth ('+detail+'). Click inside the grey floor area, away from walls, and ask again.'
            elif 'NO_PATH' in detail or 'BLOCKED' in detail:detail='No clear path on the Twin for this request ('+detail+').'
            self._message('assistant',detail,status='failed');self._event('declared_route_blocked',code=error.code,request_id=request_id)
            return
        plan['planned_by']=planned_by or dict(kind='deterministic',label='Deterministic planner')
        self._declared_route_pending=plan
        self._event('declared_route_planned',plan_id=plan['plan_id'],robot_id=plan['robot_id'],request_id=request_id,
            start=plan['start'],start_basis=plan['start_basis'],waypoints=plan['waypoints'],steps=[s['text'] for s in plan['steps']],scope=plan['scope'],
            request_id_text=None,planned_by=plan['planned_by'])
        card=self._card('declared_route_run',('Route planned through your %d chosen stop%s on the Twin from the '%(len(stops),'' if len(stops)==1 else 's') if stops else 'Route planned once on the Twin from the ')
            +('declared robot position (not localized)' if plan['kind']=='physical' else 'current SIM pose')
            +': %d stops, %.2f m, about %d finite moves, then back to the start heading.%s Moves are re-aimed from wheel odometry; a proximity stop backs off and re-plans. Each move keeps the normal robot checks; Stop ends the route. Run it?'
            %(len(plan['waypoints']),plan['length_m'],len(plan['steps']),
              (' Start LiDAR: %d unmodeled returns kept out.'%len(plan.get('keepouts') or [])) if (plan.get('scan_keepouts') or {}).get('used') else '')
            +(' First leg: straight ahead %.2f m (place a test obstacle on that line).'%plan['first_leg_straight_m'] if plan.get('first_leg_straight_m') else ''),
            [self._choice('run','Run route'),self._choice('cancel','Cancel')])
        card['operation_id']=plan['plan_id']
        card['route_preview']=self._route_preview(plan)
        card['question']=card['question']+' · '+plan['planned_by']['label']

    def _route_preview(self,plan):
        """Small top-down map for the card: free floor near the route, stops, path."""
        xs=[p[0] for p in [plan['start'],*plan['polyline']]];ys=[p[1] for p in [plan['start'],*plan['polyline']]]
        box=[min(xs)-1.,min(ys)-1.,max(xs)+1.,max(ys)+1.]
        scene=self.robot_fleet.navigation_scene or {}
        free=[[round(c[0],2),round(c[1],2)] for c in (scene.get('observed_cells') or [])
              if c[2]=='free' and box[0]<=c[0]<=box[2] and box[1]<=c[1]<=box[3]][:4000]
        r=lambda v:[round(x,3) for x in v]
        return dict(bounds=r(box),free_cells=free,cell_m=.1,start=r(plan['start']),waypoints=[r(w) for w in plan['waypoints']],
            keepouts=[r(d[:2]) for d in plan.get('keepouts') or []][:200],
            polyline=[r(p) for p in plan['polyline']],basis=plan['start_basis'],scope=plan['scope'])

    def _answer_declared_route(self,card,choice):
        self._external_started=True
        card.update(state='answered',selected_choice_id=choice['id'])
        self._message('user',choice['label'])
        plan=getattr(self,'_declared_route_pending',None);self._declared_route_pending=None
        if choice['id']=='cancel':return
        if not plan or plan['plan_id']!=card.get('operation_id'):
            raise BrokerError('declared_route_expired','Ask for the route again; no movement was sent.',status=409)
        try:self.declared_routes.start(plan,self._request_owner,context=dict(session_id=self._state['session_id']))
        except BrokerError as error:
            self._message('assistant',str(error));self._event('declared_route_blocked',code=error.code,plan_id=plan['plan_id'])
            return
        self._message('assistant','Route started: %d stops, about %d planned moves. Each move is re-aimed from wheel odometry, so the final count can be higher. '
            'I will report each stop here; Stop ends the route at any time.'%(len(plan['waypoints']),len(plan['steps'])),operation_id=plan['plan_id'])
        self._event('declared_route_started',plan_id=plan['plan_id'],robot_id=plan['robot_id'])

    def declared_route_progress(self,progress):
        """Per-stop progress from the runner thread (display only; never authority)."""
        with self._lock:
            if (progress.get('context') or {}).get('session_id')!=self._state['session_id']:return
            event=progress['event'];total=progress['total_stops'];moves=progress['completed_steps']
            if event=='stop_reached':
                text='Stop %d of %d reached · %d moves so far'%(progress['stop']+1,total,moves)
                if progress.get('unexplained'):text+=' · LiDAR: %d returns not in the Twin'%progress['unexplained']
            elif event=='return_reached':
                text='Back at the start after %d of %d stops · %d moves · restoring the start heading'%(progress['reached'],total,moves)
            elif event=='recovery':
                text='Proximity stop at (%.2f, %.2f) m · backing off %d cm and re-planning around it (recovery %d of %d). Any stop inside the new keepout is skipped.'%(
                    progress['at'][0],progress['at'][1],25,progress['recoveries'],2)
            else:return
            self._message('assistant',text,operation_id=progress['plan_id'])
            self._event('declared_route_progress',plan_id=progress['plan_id'],event=event,stop=progress.get('stop'),completed_steps=moves)
            self._persist()

    def declared_route_finished(self,result):
        with self._lock:
            plan=result['plan']
            # The run is bound to the chat that confirmed it; a later chat never gets its result.
            if (result.get('context') or {}).get('session_id')!=self._state['session_id']:return
            total=len(plan['waypoints'])
            reached=result.get('reached_stops')
            if reached is None:reached=[s['stop'] for s in result['waypoint_scans'] if not s.get('is_return') and s['stop']<total]
            skipped=result.get('skipped_stops') or []
            returned=result['reason']=='ALL_STOPS_AND_RETURN_COMPLETED'
            self._message('assistant','Route '+result['state'].lower()+': reached %d of %d stops%s%s; %d finite moves completed, including odometry re-aims (%s). '
                'Twin shows the path, trace and LiDAR at each stop from the declared start + wheel odometry; not verified localization.%s'
                %(len(reached),total,(' (skipped stop%s %s after a proximity stop)'%('s' if len(skipped)>1 else '',', '.join(str(s+1) for s in skipped))) if skipped else '',
                  ' and returned to the start' if returned else '',result['completed_steps'],result['reason'],
                  ' The route record could not be saved to disk (%s); free disk space before the next route.'%result['save_error'] if result.get('save_error') else ''),
                operation_id=plan['plan_id'],status='failed' if result['state']=='FAILED' else 'completed')
            self._event('declared_route_finished',plan_id=plan['plan_id'],state=result['state'],reason=result['reason'],
                completed_steps=result['completed_steps'],waypoint_scans=result['waypoint_scans'],candidates=result.get('candidates') or [])
            candidates=result.get('candidates') or []
            if candidates and getattr(self,'add_route_obstacles',None) and not any(c['state']=='waiting' for c in self._state['cards']):
                listing='; '.join('#%d at (%.2f, %.2f) m, %d returns'%(i+1,*c['position_xy_m'],c['returns']) for i,c in enumerate(candidates))
                matcher=getattr(self,'match_route_objects',None);matches=[]
                if matcher:
                    try:matches=matcher(candidates) or []
                    except Exception:matches=[]
                aligned=[m for m in matches if m.get('aligned')];movable=[m for m in matches if not m.get('aligned')]
                explained={m['candidate'] for m in matches};new=[i for i in range(len(candidates)) if i not in explained]
                notes=''.join(' Candidate #%d matches the Twin object "%s" (%.2f m away): no move needed.'%(m['candidate']+1,m['label'],m['distance_m']) for m in aligned)
                correction=(' Candidate #%d is %.2f m from the existing object "%s": choose Move to shift that object to the LiDAR estimate (position correction, user-applied).'
                    %(movable[0]['candidate']+1,movable[0]['distance_m'],movable[0]['label'])) if movable else ''
                pending=dict(plan_id=plan['plan_id'],candidates=candidates,matches=matches,new=new)
                if self._state.get('twin_edit_approval')=='auto':
                    edits=[('move',m) for m in movable]+[('add',None)]*len(new)
                    self._message('assistant','LiDAR at the stops saw %d object%s the Twin does not have: %s.%s Twin-edit auto-apply: %s.'
                        %(len(candidates),'' if len(candidates)==1 else 's',listing,notes,
                          ', '.join(['moving "%s" to the LiDAR estimate'%m['label'] for m in movable]+(['adding %d outline box%s'%(len(new),'' if len(new)==1 else 'es')] if new else [])) or 'nothing to apply')
                        +' Positions come from the declared start + wheel odometry (not localized). Each edit goes through the Twin update (Engine ACK, Undo available); no robot moves.')
                    self._auto_route_edits=[dict(kind=kind,match=match,pending=pending) for kind,match in edits]
                    self._event('declared_route_auto_apply',plan_id=plan['plan_id'],edits=[e['kind'] for e in self._auto_route_edits])
                    self._apply_next_auto_edit()
                elif new or movable:
                    card=self._card('declared_route_obstacles','LiDAR at the stops saw %d object%s the Twin does not have: %s.%s '
                        'Positions come from the declared start + wheel odometry (not localized).%s %s'
                        %(len(candidates),'' if len(candidates)==1 else 's',listing,notes,
                          ' Add the %d unexplained one%s to the Twin as rough outlines (unknown obstacles)?'%(len(new),'' if len(new)==1 else 's') if new else '',
                          'This edits the Twin (Undo available); no robot moves.'+correction),
                        ([self._choice('add','Add to Twin')] if new else [])+([self._choice('move','Move "%s" to the LiDAR estimate'%movable[0]['label'])] if movable else [])+[self._choice('skip','Skip')])
                    card['operation_id']=plan['plan_id'];self._route_candidates=pending
                else:
                    self._message('assistant','LiDAR at the stops saw %d object%s, all matching existing Twin objects:%s No Twin edit needed.'%(len(candidates),'' if len(candidates)==1 else 's',notes))
            self._persist()

    def _apply_next_auto_edit(self):
        """Twin-edit auto-apply: start the next queued LiDAR edit through the normal transaction; the following one
        starts when this one is COMMITTED with its frame confirmed (see the transaction sync). Never robot motion."""
        queue=getattr(self,'_auto_route_edits',None) or []
        while queue:
            edit=queue.pop(0);pending=edit['pending']
            try:
                if edit['kind']=='move':
                    match=edit['match']
                    operation=self.move_route_object(self._request_owner,pending['plan_id'],match)
                    self._message('assistant','Auto-applied (Twin-edit auto-apply): moving "%s" by (%.2f, %.2f) m to the LiDAR estimate. The object stays a LiDAR estimate, not localized; Undo last edit reverts it.'
                        %(match['label'],match['translation_m'][0],match['translation_m'][1]),operation_id=operation)
                    self._event('declared_route_object_moved',plan_id=pending['plan_id'],object_id=match['object_id'],operation_id=operation,auto=True)
                else:
                    exclude=[m['candidate'] for m in (pending.get('matches') or [])]
                    operation,count=self.add_route_obstacles(self._request_owner,pending['plan_id'],pending['candidates'],exclude=exclude)
                    self._message('assistant','Auto-applied (Twin-edit auto-apply): adding one LiDAR outline box (unknown, lidar estimate, not aligned; strongest unexplained candidate first). Undo last edit reverts it.',operation_id=operation)
                    self._event('declared_route_obstacles_added',plan_id=pending['plan_id'],count=count,operation_id=operation,auto=True)
                self._auto_route_edits=queue;self._auto_replan_pending=not queue;return  # re-plan once the last edit's frame is confirmed
            except (BrokerError,ValueError) as error:
                self._message('assistant','Twin-edit auto-apply skipped one edit: '+str(error)[:200])
        self._auto_route_edits=[];self._auto_replan_pending=False
        self._auto_replan()

    def _auto_replan(self):
        """After auto-applied Twin edits, plan the last route request again (deterministic, no model call) and offer Run."""
        text=getattr(self,'_last_route_text',None)
        if not text or any(c['state']=='waiting' for c in self._state['cards']) or self.declared_routes.active():return
        if getattr(self.robot_fleet,'focused',None) is None:return
        self._message('assistant','Twin edits applied; re-planning "%s" on the updated Twin (no model call). Run it only if you want the robot to move.'%text[:120])
        self._plan_declared_route(text,'auto-replan-'+uuid4().hex,planned_by=dict(kind='auto_replan',label='Auto re-plan after Twin-edit auto-apply · no model call'))

    def _offer_robot_task(self,body):
        if any(c['state']=='waiting' for c in self._state['cards']):
            raise BrokerError('choice_required','Finish the current question before requesting another task.',status=409)
        if self.robot_tasks.active():raise BrokerError('robot_task_busy','Finish or cancel the current task.',status=409)
        self._message('user',body['text'])
        self._robot_task_pending=dict(text=body['text'],request_id=body['request_id'],robot_id=self.robot_fleet.focused)
        self._card('robot_task_plan','Send this instruction and the capability names to the configured planner? One text-only call; no photos, coordinates, USD or sensor logs. No movement yet.',[
            self._choice('plan','Plan task'),self._choice('cancel','Cancel')])

    def _sync_robot_tasks(self,owner):
        if not self.robot_tasks:return
        job=self.robot_tasks.snapshot(owner)
        if not job:return
        marker=(job['task_id'],job['state'],job['step_index'],job['segments'])
        if marker==self._robot_task_marker:return
        self._robot_task_marker=marker
        if job['task_id']==getattr(self,'_route_consumed_task',None):return  # its plan became a Path B route; no task-loop message
        pending=getattr(self,'_route_model_pending',None)
        if pending and job['task_id']==pending['task_id'] and job['state'] in {'READY','FAILED','CANCELLED','HELD'}:
            self._route_model_pending=None;latency=round(time.monotonic()-pending['started'],1);model=str(job.get('model_id') or 'configured planner')
            self._route_consumed_task=job['task_id']
            if job['state']=='READY':
                ops=[s.get('op') for s in (job.get('plan') or {}).get('steps') or []]
                valid=bool(ops) and set(ops)<={'observe','survey','return_to_start','stop'} and any(o in {'observe','survey'} for o in ops)
                try:self.robot_tasks.cancel(owner)  # the plan is consumed here; Path B executes, not the task loop
                except Exception:pass
                if valid:
                    self._message('assistant','Planned by '+model+' via Nebius Token Factory in %.1f s: '%latency+' → '.join(ops)+'. '+str((job.get('plan') or {}).get('explanation') or '')
                        +' Handing the plan to the Path B route (model plans, deterministic planner lays out the stops; every safety check unchanged). Call log: robot-tasks/'+job['task_id']+' (no keys).',operation_id=job['task_id'])
                    self._event('declared_route_model_planned',task_id=job['task_id'],model_id=job.get('model_id'),latency_s=latency,ops=ops)
                    self._plan_declared_route(pending['text'],pending['request_id'],planned_by=dict(kind='model',label='Planned by '+model+' via Nebius Token Factory · %.1f s'%latency,model_id=job.get('model_id'),task_id=job['task_id'],latency_s=latency))
                else:
                    self._message('assistant','The planner answered with steps outside the survey capabilities ('+', '.join(map(str,ops))+'); the plan was not used.',status='failed',operation_id=job['task_id'])
                    self._offer_route_fallback(pending['text'],pending['request_id'],'plan rejected: '+', '.join(map(str,ops)))
            else:
                reason=str(job.get('reason') or job['state'])
                self._message('assistant','Model planning '+job['state'].lower()+' after %.1f s: '%latency+reason[:300]+' (call log: robot-tasks/'+job['task_id']+').',status='failed',operation_id=job['task_id'])
                self._event('declared_route_model_failed',task_id=job['task_id'],state=job['state'],reason=reason[:300])
                self._offer_route_fallback(pending['text'],pending['request_id'],reason[:200])
            self._persist();return
        if job['state']=='READY':
            plan=job['plan'];summary=' → '.join(s['op']+((' '+s['target_kind']) if s['op']=='navigate' else
                (' '+s['direction']+' '+str(s['amount'])+(' rad' if s['direction'] in {'left','right'} else ' m')) if s['op']=='move_relative' else '') for s in plan['steps'])
            self._message('assistant','Planner proposal: '+summary+'. '+plan['explanation']+' Limits: '+str(plan['limits']['distance_m'])+' m / '+str(plan['limits']['duration_s'])+' s. This is not motion or whole-room coverage evidence.',operation_id=job['task_id'])
            card=self._card('robot_task_run','Run this exact task? Physical: supervision, Arm and bootstrap Stop required. Collection and return use wheel-estimated local coordinates, not USD alignment or certified body position. Unknown-space and robot-side guards stay active.',[
                self._choice('run','Run task'),self._choice('cancel','Cancel')])
            card['related_plan_digest']=job['plan_sha256'];card['operation_id']=job['task_id']
        elif job['state'] in {'COMPLETED','PARTIAL','HELD','FAILED','CANCELLED'}:
            for card in self._state['cards']:
                if card['kind']=='robot_task_run' and card['operation_id']==job['task_id'] and card['state']=='waiting':card['state']='cancelled'
            self._message('assistant','Robot task '+job['state']+': '+str(job.get('reason') or 'exact child results and Stop checked')+
                '. Finite segments: '+str(job['segments'])+'. Original robot recording remains separate; chassis accuracy and world registration are not certified.',
                status='failed' if job['state'] in {'FAILED','HELD'} else 'completed',operation_id=job['task_id'])
        elif job['state']=='RUNNING':
            self._message('assistant','Robot task: step '+str(job['step_index']+1)+' · '+str(job['segments'])+' finite segments. Observing and rechecking before the next segment.',status='completed',operation_id=job['task_id'])
        self._event('robot_task_changed',task_id=job['task_id'],state=job['state'],step_index=job['step_index'],segments=job['segments'])
        self._persist()

    def _accept_message(self, body):
        text = body["text"]
        if not isinstance(text, str) or len(text) > 8000:
            raise BrokerError("prompt_invalid", "Prompt is invalid", status=400)
        if not isinstance(body['mode'],str) or body['mode'] not in {'new','add','change'}:
            raise BrokerError('scene_mode_invalid','Choose New, Add, or Change',status=400)
        from twinpulse_core.robot_task_plan import immediate_stop
        if body['attachment'] is None and (immediate_stop(text) or text.strip().lower() in {'stop','stop simulation','pause simulation','정지','멈춰'}):
            fleet_stopped=False
            if self.robot_fleet is not None and text.strip().lower() not in {'stop simulation','pause simulation'}:
                # Bare Stop is not a command to whichever SIM happened to keep
                # focus. Deliver to all owned fleet sessions, then any live REAL
                # legacy task below. Explicitly named Stop keeps its target.
                self._fleet_message(body,command_text='all robots stop')
                fleet_stopped=True
                if self._state['mode']!='REAL':return
            if not fleet_stopped:self._message('user', text)
            if self._state['mode']=='REAL' and self.robot_preparation:
                nav=self.navigation.snapshot(self._request_owner) if self.navigation else None
                job=nav.get('job') if nav else None
                loop=getattr(self.navigation,'task_loop',None)
                result=(loop.stop(self._request_owner) if loop and loop.active() else self.navigation.mission.stop(self._request_owner,job['job_id'])['job']
                    if job and job['state'] not in {'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}
                    else self.robot_preparation.stop(self._request_owner))
                self._message('assistant', 'Physical Stop requested: '+result['state']+'. This is not a confirmed stop; check the worker cleanup result.')
                self._event('physical_stop_requested',state=result['state'])
            else:
                self._message('assistant', 'SIM Stop requested from chat. The control card checks the engine acknowledgement; this message is not proof of a stop.'
                    if self._state['mode']!='REAL' else 'Physical preparation is unavailable; no SIM substitute was sent.')
                self._event('simulation_stop_request_recorded' if self._state['mode']!='REAL' else 'physical_stop_unavailable')
            return
        if self.robot_fleet is not None and body['attachment'] is None and body['mode']=='new':
            from twinpulse_core.robot_task_plan import task_request
            focused_kind=(self.robot_fleet.robots.get(self.robot_fleet.focused) or {}).get('kind')
            if self._route_candidates_request(text):
                self._offer_saved_route_candidates(body)
                return
            if self._declared_route_request(text):
                self._start_declared_route(body)
                return
            if self.robot_tasks and self.robot_fleet.focused and task_request(text,focused_kind):
                self._offer_robot_task(body)
                return
            from .robot_fleet import parse_robot_command
            try:robot_command=parse_robot_command(text)
            except BrokerError:
                self._fleet_message(body)
                return
            if robot_command is not None and (robot_command['action'] not in {'status','navigate'} or self.robot_fleet.focused is not None):
                self._fleet_message(body)
                return
        # Explanations do not dismiss a pending choice or submit another job.
        if text.strip().lower() in {"status", "what is happening?", "explain status", "현재 상태", "상태"} and body["attachment"] is None:
            self._message("user", text)
            job = self._state["generation"]
            pending = next((c for c in self._state["cards"] if c["state"] == "waiting"), None)
            self._message("assistant", (job["summary"] if job else "No generation is running.") +
                          (" Waiting for your choice: " + pending["question"] if pending else "") +
                          " No physical motion is authorized by this conversation.")
            return
        pending = next((card for card in self._state['cards'] if card['state']=='waiting'), None)
        if self._feedback_worker and self._feedback_worker.is_alive():
            raise BrokerError('scene_feedback_busy','Wait for the proposal or stop its response. Nothing has been applied.',status=409)
        if self.workflow.scene_edit_transaction.locked():
            raise BrokerError('scene_edit_busy','Geometry and Run remain locked until the retained transaction is resolved.',status=409)
        if pending and pending['kind']=='scene_edit_clarify' and body['attachment'] is None and text.strip():
            feedback=self._state['scene_feedback']
            if (not feedback or pending['related_plan_digest']!=feedback['context']['current_state_sha256'] or
                    self.workflow.scene_edit_context(feedback['context']['request_text'],None,dependency=True)!=feedback['context']):
                raise BrokerError('scene_edit_proposal_stale','The clarification context changed.',status=409)
            pending['state']='answered'
            joined=feedback['context']['request_text']+'\nClarification question: '+pending['question']+'\nHuman answer: '+text
            self._message('user',text)
            self._begin_feedback(joined,body['request_id'],clarification_count=1)
            return
        from twinpulse_core.simulation_goal import is_navigation_request
        # Explicit Add/Change is the user's geometry-edit intent, not a robot
        # destination inferred from words such as Korean "이동해". Stop and
        # status retain their earlier precedence; ordinary New chat navigation
        # still requires its separate reviewed plan and never starts motion.
        if body['mode']=='new' and body['attachment'] is None and is_navigation_request(text) and self.workflow.snapshot().get('site_draft'):
            if pending and pending['kind'] not in {'simulation_target','robot_goal_target','robot_goal_confirm','robot_goal_loop'}:
                raise BrokerError('choice_required', 'Finish the current scene question before planning a route', status=409)
            if pending: pending['state'] = 'cancelled'
            self._message('user', text)
            self._review_navigation(text, body['request_id'])
            return
        aliases = {'robot_presence': {'simulation only':'sim','no physical robot':'sim','no robot':'sim','로봇 없음':'sim',
                                      'use my robot':'real','i have a robot':'real','physical robot':'real','로봇 있음':'real'},
                   'robot_selection': {'burger3':'turtlebot3_burger','turtlebot3 burger':'turtlebot3_burger','burger':'turtlebot3_burger'}}
        choice = aliases.get(pending['kind'], {}).get(text.strip().lower()) if pending and body['attachment'] is None else None
        if choice:
            self._answer({'card_id':pending['id'], 'choice_id':choice, 'expected_session_revision':pending['expected_session_revision'],
                          'request_id':body['request_id']}, user_text=text)
            return
        if any(card["state"] == "waiting" for card in self._state["cards"]):
            raise BrokerError("choice_required", "Answer the pending question before submitting a new scene request", status=409)
        if body["mode"] not in {"new", "add", "change"}:
            raise BrokerError("scene_mode_invalid", "Choose New, Add, or Change", status=400)
        if self.workflow.has_active_generation():
            if body['mode']=='new' or body['attachment'] is not None:
                raise BrokerError('generation_busy', 'Generation is running. A text Add/Change request can be queued; a new environment cannot replace it.', status=409)
            if not text.strip() or self._state['queued_edit']:
                raise BrokerError('pending_edit_exists', 'One pending edit is already saved. Wait for its review before adding another.', status=409)
            queued_user=self._message('user', text, status='pending')
            self._state['queued_edit'] = {**{key:body[key] for key in ('text','mode','attachment')},
                'origin_message_id':queued_user['message_id'],'request_id':body['request_id']}
            self._message('assistant', 'Edit queued. The current generation will not be replaced; a validated preview will be offered after it ends.')
            self._event('edit_queued')
            return
        if body["mode"] != "new":
            self._edit_message(body)
            return
        if (body['attachment'] is None and self.workflow.snapshot().get('site_draft') and
                (text.strip().lower() in EXACT_UNDO_COMMANDS or self.workflow.scene_edit_proposal_service is not None
                 or getattr(self.workflow,'generation_approvals',None))):
            self._edit_message(body)
            return
        if self.workflow.snapshot().get("saved_site_scene_protected") or self.workflow.snapshot().get("draft"):
            raise BrokerError("existing_scene_protected", "This project already has a scene. Create a new project or use a reviewed Add/Change operation; it will not be overwritten.", status=409)
        attachment = body["attachment"]
        if attachment is not None and (not isinstance(attachment, dict) or set(attachment) != {"name", "media_type", "content_base64"}):
            raise BrokerError("attachment_invalid", "Exactly one supported image may be attached", status=400)
        payload = {"name": None, "media_type": None, "content_base64": None,
                   "input_kind": "auto", "prompt": body["text"], "sidecar_name": None, "sidecar_content_base64": None}
        if attachment: payload.update(attachment)
        self.workflow.select_input(payload)
        self._state["pending_input"] = payload
        self._state["mode"], self._state["robot_id"] = None, None
        message = self._message("user", body["text"], attachment={"name": attachment["name"], "media_type": attachment["media_type"]} if attachment else None)
        self._state['pending_input_origin']=message['message_id']
        if attachment:
            from PIL import Image
            with Image.open(BytesIO(base64.b64decode(attachment["content_base64"], validate=True))) as image:
                image.thumbnail((512, 512))
                output = BytesIO()
                image.convert("RGB").save(output, format="PNG")
            self._state["thumbnails"][message["message_id"]] = base64.b64encode(output.getvalue()).decode("ascii")
            message["attachments"][0]["preview_url"] = "/v1/product/conversation/image/" + message["message_id"]
        if os.environ.get('TWINPULSE_SIM_ONLY') == '1':
            self._card('robot_presence', 'Create this Twin in Isaac simulation?', [self._choice('sim', 'Create in simulation')])
        else:
            self._card("robot_presence", "Do you have a physical robot?", [self._choice("sim", "Simulation only"), self._choice("real", "Use my robot")])

    def _answer(self, body, *, user_text=None):
        card = next((c for c in self._state["cards"] if c["id"] == body["card_id"]), None)
        if not card or card["state"] != "waiting": raise BrokerError("card_expired", "This question has already been answered or expired", status=409)
        if body["expected_session_revision"] != card["expected_session_revision"]:
            raise BrokerError("card_stale", "Question revision changed; review its current state", status=409)
        choice = next((c for c in card["choices"] if c["id"] == body["choice_id"] and c["enabled"]), None)
        if not choice: raise BrokerError("choice_invalid", "This choice is unavailable", status=400)
        direct_generation = ('limit_usd' in body and 'generation_approval' in card and
            (card['kind']=='robot_presence' and choice['id']=='sim' or card['kind']=='robot_selection'))
        if 'limit_usd' in body and not direct_generation and (card['kind'] != 'generation_approval' or choice['id'] != 'approve'):
            raise BrokerError('chat_shape_invalid', 'A spending limit is accepted only for this generation approval.', status=400)
        if card['kind']=='declared_route_run':
            self._answer_declared_route(card,choice)
            return
        if card['kind']=='declared_route_fallback':
            card.update(state='answered',selected_choice_id=choice['id']);self._message('user',choice['label'])
            pending=getattr(self,'_route_fallback_pending',None);self._route_fallback_pending=None
            if choice['id']!='fallback':return
            if not pending or pending['request_id']!=card.get('operation_id'):raise BrokerError('declared_route_expired','Ask for the route again; no movement was sent.',status=409)
            self._plan_declared_route(pending['text'],pending['request_id'],planned_by=dict(kind='fallback',label='Deterministic fallback · model call failed: '+pending['reason'][:80]))
            return
        if card['kind']=='declared_route_obstacles':
            card.update(state='answered',selected_choice_id=choice['id'])
            self._message('user',choice['label'])
            pending=getattr(self,'_route_candidates',None);self._route_candidates=None
            if choice['id']=='move':
                match=((pending or {}).get('matches') or [None])[0]
                if not match or not getattr(self,'move_route_object',None):
                    self._message('assistant','The position correction is no longer available; ask for the route again.');return
                try:
                    operation=self.move_route_object(self._request_owner,pending['plan_id'],match)
                    self._message('assistant','Moving "%s" by (%.2f, %.2f) m to the LiDAR estimate. Follow the Twin update and Apply or Undo; the object stays an estimate, not localized.'
                        %(match['label'],match['translation_m'][0],match['translation_m'][1]),operation_id=operation)
                    self._event('declared_route_object_moved',plan_id=pending['plan_id'],object_id=match['object_id'],operation_id=operation)
                except (BrokerError,ValueError) as error:
                    self._message('assistant','The object was not moved: '+str(error)[:200])
                return
            if choice['id']!='add':return
            if not pending or pending['plan_id']!=card.get('operation_id'):
                # After an App restart the saved route record is the source of the candidates.
                pending=dict(plan_id=card.get('operation_id'),candidates=None)
            try:
                exclude=[m['candidate'] for m in (pending.get('matches') or [])]
                operation,count=self.add_route_obstacles(self._request_owner,pending['plan_id'],pending['candidates'],exclude=exclude)
                self._message('assistant','Adding %d LiDAR obstacle%s to the Twin (unknown, lidar estimate, not aligned; one object per Twin edit, strongest first). Follow the Twin update; Undo is available. Ask again to add the next one, or ask for the route again to plan around it.'
                    %(count,'' if count==1 else 's'),operation_id=operation)
                self._event('declared_route_obstacles_added',plan_id=pending['plan_id'],count=count,operation_id=operation)
            except (BrokerError,ValueError) as error:
                self._message('assistant','The LiDAR obstacles were not added: '+str(error)[:200])
            return
        if card['kind'] in {'robot_task_plan','robot_task_run'}:
            if not self.robot_tasks:raise BrokerError('robot_task_unavailable','Robot task service is unavailable.',status=409)
            self._external_started=True
            card.update(state='answered',selected_choice_id=choice['id'])
            self._message('user',choice['label'])
            if choice['id']=='cancel':
                if self.robot_tasks.owner==self._request_owner:self.robot_tasks.cancel(self._request_owner)
                self._robot_task_pending=None
            elif card['kind']=='robot_task_plan':
                pending=self._robot_task_pending
                if not pending:raise BrokerError('robot_task_prompt_expired','Submit the task again; no request was resumed.',status=409)
                if pending['robot_id']!=self.robot_fleet.focused:raise BrokerError('robot_task_selection_changed','Selected robot changed; submit the task again.',status=409)
                self.robot_tasks.propose(pending['text'],self._request_owner,body['request_id']);self._robot_task_pending=None
                self._message('assistant','Planning one bounded robot task with the configured planner. No controls are sent.',status='completed')
            else:
                self.robot_tasks.run(self._request_owner,card['related_plan_digest'])
            self._sync_robot_tasks(self._request_owner)
            return
        if card['kind'] == 'generation_approval' and choice['id'] == 'approve':
            approvals = getattr(self.workflow, 'generation_approvals', None)
            if not approvals:
                raise BrokerError('generation_approval_unavailable', 'Generation approval service is unavailable; nothing was sent.', status=409)
            if card.get('scene_feedback'):
                feedback=self._state['scene_feedback']
                if not feedback or feedback['state']!='awaiting_approval':
                    raise BrokerError('scene_edit_proposal_stale','Feedback approval changed.',status=409)
                scope=approvals.approve(card['generation_approval'],card['id'],body.get('limit_usd'),edit_context=feedback['context'])
                self._external_started=True;card.update(state='answered',selected_choice_id='approve')
                self._message('user','Approve this feedback proposal with USD '+body['limit_usd']+' maximum.')
                self._start_feedback_call(body['request_id'],scope)
                return
            self.workflow.select_input(self._state['pending_input'])
            scope = approvals.approve(card['generation_approval'], card['id'], body.get('limit_usd'))
            # The durable grant cannot become retryable if later chat storage
            # fails. Its one-use record is independent of response delivery.
            self._external_started = True
            card.update(state='answered', selected_choice_id='approve')
            self._message('user', 'Approve this generation action with USD '+body['limit_usd']+' maximum.')
            self._event('generation_scope_approved', card_id=card['id'])
            self._start_generation(body['request_id'], inference_scope=scope,
                continuation_checkpoint=card['generation_approval']['checkpoint_id'])
            return
        if card['kind'] in {'robot_presence','robot_selection'}:
            observed=self.workflow.snapshot()
            current=observed.get('input')
            if (not card.get('related_plan_digest') or current and current['revision']!=card['related_plan_digest']
                    or observed.get('site_draft') or observed.get('draft')):
                card['state']='expired'
                self._message('assistant','Scene input changed. This old choice expired without starting generation; submit the current request for a new question.',status='failed')
                self._event('card_expired',card_id=card['id'])
                return
        card.update(state="answered", selected_choice_id=choice["id"])
        self._message("user", user_text or choice["label"])
        self._event("card_answered", card_id=card["id"], choice_id=choice["id"])
        if card['kind'] == 'generation_approval':
            if card.get('scene_feedback') and self._state['scene_feedback']:
                self._state['scene_feedback']['state']='cancelled'
            self._message('assistant', 'Generation approval cancelled. Nothing was sent or resumed.')
            return
        if card['kind']=='scene_edit_clarify':
            self._state['scene_feedback']['state']='cancelled'
            self._message('assistant','Feedback cancelled. No scene or engine was changed.');return
        if card['kind']=='scene_sensor_policy':
            selection=card['sensor_selection']
            if choice['id']=='cancel':
                self._state['scene_sensor_review']=dict(status='cancelled',policy='cancel',context=selection['context'],
                    preview=None,physical_authority=False,current_pose_available=False,alignment_verified=False)
                self._message('assistant','Saved sensor review cancelled. Geometry, history and engine are unchanged.');return
            adapter=self.workflow.scene_sensor_review
            if adapter is None:raise BrokerError('scene_sensor_unavailable','Saved sensor validator is unavailable.',status=409)
            result=adapter.review(selection,choice['id']);preview=result.pop('preview',None)
            self._state['scene_sensor_review']={**result,'preview':None}
            self._event('scene_sensor_review',status=result['status'],execution_id=result['execution_id'])
            if preview:
                self._offer_feedback_preview(preview,'Historical sensor candidate: '+str(len(result['proposals']))+' bounded wall change(s). No measured pose or physical authority.')
            else:
                self._message('assistant','Saved sensor review '+result['status']+': '+result.get('reason','')+
                    '. No geometry, history, Build or robot command was changed.')
            return
        if card['kind']=='robot_goal_loop':
            if choice['id']=='finish':
                self._message('assistant','Task finished. No repeat movement started.');return
            loop=getattr(self.navigation,'task_loop',None)
            if not loop:raise BrokerError('task_loop_unavailable','Repeat task service is unavailable.',status=409)
            self._persist();self._external_started=True
            try:
                loop.start(self._request_owner,card['related_plan_digest'],body.get('expires_at_ms'))
                self._message('assistant','Repeat task approved once. Preparing a fresh bounded return leg; each leg independently checks battery, location, route, Isaac and cleanup. No per-movement approval.')
            except (BrokerError,ValueError,OSError) as exc:
                self._message('assistant','Repeat task could not start: '+str(exc)+'. Approval consumed; no automatic retry.',status='failed')
            return
        if card['kind'] in {'robot_goal_target','robot_goal_confirm'}:
            if not self.navigation:raise BrokerError('goal_navigation_unavailable','Current goal service is unavailable.',status=409)
            if choice['id']=='cancel':
                self.navigation.cancel(self._request_owner)
                self._message('assistant','Goal cancelled. No destination movement started.');return
            if card['kind']=='robot_goal_target':
                cached=self.navigation.snapshot(self._request_owner)
                review=cached.get('review') if cached else None
                targets=review['choices'] if review else []
                target=next((t['id'] for i,t in enumerate(targets) if choice['id']=='object_'+str(i)),None)
                if target is None:raise BrokerError('goal_selection_stale','Target choice expired.',status=409)
                self._review_navigation(self.navigation.text,body['request_id'],expected_revision=card['related_plan_digest'],selection=target)
                return
            self._persist();self._external_started=True
            try:
                self.navigation.confirm(self._request_owner,card['related_plan_digest'],body.get('expires_at_ms'))
                self._message('assistant','One bounded goal mission started. Current sensors, local guard and independent Stop remain active; no per-command approval or automatic restart.')
            except BrokerError as error:
                self._message('assistant',str(error)+' ('+error.code+'). Approval consumed; request a fresh route. No automatic retry.',status='failed')
            return
        if card['kind'] == 'simulation_target':
            review = self._state['simulation_review']
            if choice['id'] == 'cancel':
                self._state['simulation_review'] = None
                self._message('assistant', 'Route selection cancelled. Nothing moved.')
            elif not review or review['scene_revision'] != card['related_plan_digest']:
                card['state'] = 'expired'
                self._state['simulation_review'] = None
                self._message('assistant', 'This route question expired. Submit the goal again.', status='failed')
            else:
                selected = next((t['id'] for i,t in enumerate(review['choices']) if choice['id'] == 'object_' + str(i)), None)
                if selected is None:
                    raise BrokerError('choice_invalid', 'This saved target is unavailable', status=400)
                self._review_navigation(review['text'], body.get('request_id', review['request_id']),
                                        expected_revision=card['related_plan_digest'], selection=selected)
            return
        if card["kind"] == "scene_edit":
            if choice["id"] == "cancel":
                self._state["pending_edit"] = None
                self._message("assistant", "Edit cancelled. The saved scene is unchanged.")
                return
            self._ensure_site_review()
            preview = self._state["pending_edit"]
            if not preview or self.workflow.snapshot()["site_draft"]["revision"] != preview["parent_revision"]:
                card["state"] = "expired"
                self._state["pending_edit"] = None
                self._message("assistant", "Scene changed. This edit was not applied; submit a fresh preview.", status="failed")
                return
            self._persist()
            self._external_started = True
            try:
                if preview.get('apply_version')=='scene-edit-apply-2.0':
                    self.workflow.scene_edit_transaction.start(self._request_owner,preview['operation'],preview['preview_digest'],
                        feedback_lineage=preview.get('feedback_lineage'),sensor_binding=preview.get('sensor_binding'))
                    self._state['simulation_review']=None
                    for previous in self._state['cards']:
                        if previous['state']=='waiting' and previous['kind'] in {'simulation_target','robot_goal_target','robot_goal_confirm','robot_goal_loop'}:
                            previous['state']='expired'
                    self._message('assistant','Updating the Twin through its engine ACK and durable save. Old goal plans are invalidated. No Run or robot command starts.',status='pending',operation_id=preview['operation']['operation_id'])
                    self._event('scene_edit_started',operation_id=preview['operation']['operation_id'])
                else:
                    self.workflow.apply_scene_edit(preview["operation"], preview["preview_digest"])
                    self._message("assistant", "Edit saved as a new scene revision. Original scene and non-target objects were preserved. 3D build is checked separately.")
                    self._event("scene_edit_completed", operation_id=preview["operation"]["operation_id"])
            except BrokerError as error:
                self._message("assistant", str(error) + " (" + error.code + "). Do not repeat this apply; reopen the saved scene to inspect its outcome.", status="failed")
                self._event("scene_edit_failed", code=error.code)
            except Exception as error:
                self._message('assistant', 'Scene edit failed (' + type(error).__name__ + '). Do not repeat the apply; inspect the saved revision.',status='failed')
                self._event('scene_edit_failed',code='unexpected_edit_failure',error_type=type(error).__name__)
            self._state["pending_edit"] = None
            return
        if card['kind']=='robot_inspection':
            if choice['id']=='cancel':
                self._message('assistant','Inspection deferred. No survey or goal motion started.')
                return
            if not self.inspection:raise BrokerError('inspection_unavailable','Inspection service is unavailable.',status=409)
            self._persist();self._external_started=True
            try:
                self.inspection.start(self._request_owner,card['related_plan_digest'],body.get('expires_at_ms'))
                self._message('assistant','One bounded survey started. Local guard and stop controls remain active; no goal destination was authorized.')
            except BrokerError as error:
                self._message('assistant',str(error)+' ('+error.code+'). No automatic retry.',status='failed')
            self._sync_inspection(self._request_owner)
            return
        if card['kind'] in {'robot_qualification','robot_observation','robot_recheck','robot_initialize'}:
            if not self.robot_preparation:
                raise BrokerError('chat_robot_unavailable','Physical preparation is unavailable.',status=409)
            # Commit this exact choice before any external operation. A failed
            # save cannot start transport; later response loss cannot replay it.
            self._persist()
            self._external_started=True
            try:
                if choice['id']=='cancel':
                    self._message('assistant','Physical preparation deferred. No trial was started.')
                elif card['kind']=='robot_recheck':self.robot_preparation.check(self._request_owner,correlation={'workflow_id':self._state['session_id']})
                elif card['kind']=='robot_initialize':
                    self.robot_preparation.initialize(self._request_owner,card['related_plan_digest'],body.get('expires_at_ms'))
                elif card['kind']=='robot_qualification':
                    self.robot_preparation.qualify(self._request_owner,card['related_plan_digest'],body.get('expires_at_ms'))
                else:self.robot_preparation.observe(self._request_owner,card['related_plan_digest'],choice['id']=='normal')
            except BrokerError as error:
                self._message('assistant',str(error)+' ('+error.code+'). This choice will not be retried.',status='failed')
                self._event('robot_choice_rejected',code=error.code)
            self._sync_robot(self._request_owner)
            return
        if card["kind"] == "robot_presence" and choice["id"] == "real":
            if os.environ.get('TWINPULSE_SIM_ONLY') == '1':
                raise BrokerError('sim_alpha_only', 'This release supports Isaac simulation.', status=409)
            self._state["mode"] = "REAL"
            self._card("robot_selection", "Choose your robot.", [self._choice("turtlebot3_burger", "TurtleBot3 Burger")])
            return
        self._state["mode"] = self._state["mode"] or "SIM"
        self._state['simulation_review'] = None
        if card['kind'] == 'robot_presence' and choice['id'] == 'sim':
            from twinpulse_core.sim_robot_selection import sim_robot_selection
            selected = sim_robot_selection((self._state.get('pending_input') or {}).get('prompt', ''))
            self._message('assistant', selected['reason'])
            self._event('simulation_environment_only' if selected['code'] == 'SIM_ENVIRONMENT_ONLY' else
                        'simulation_robot_selected' if selected['asset_id'] else 'simulation_robot_alternative_required', code=selected['code'])
            if selected['code'] == 'SIM_ROBOT_ALTERNATIVE_REQUIRED':
                self._card('robot_selection', 'Use the supported room SIM robot instead?',
                           [self._choice('turtlebot3_burger', 'Use TurtleBot3 Burger instead')])
                return
            self._state['robot_id'] = selected['asset_id']
        inference_scope = None
        if direct_generation:
            approvals = getattr(self.workflow, 'generation_approvals', None)
            if not approvals:
                raise BrokerError('generation_approval_unavailable','Generation service is unavailable; nothing was sent.',status=409)
            inference_scope = approvals.approve(card['generation_approval'],card['id'],body['limit_usd'])
            self._external_started = True  # A durable one-use scope cannot be replayed on response loss.
            self._message('assistant','Creating the Twin now, within your USD '+body['limit_usd']+
                ' action limit. Uncertain charges remain reserved; no automatic retry or robot movement.')
            self._event('generation_scope_approved',card_id=card['id'],source='generation_choice')
        if card["kind"] == "robot_selection":
            self._state["robot_id"] = choice["id"]
            robot_available=self.robot_preparation and self.robot_preparation.snapshot(self._request_owner)['available']
            self._message("assistant", "TurtleBot3 Burger selected. " +
                ("Scene generation and one read-only connection check run independently. No sensor, deployment or movement starts with this choice." if self._state['mode']=='REAL' and robot_available else
                 "Physical preparation is unavailable in this backend; no robot connection or motion is started." if self._state['mode']=='REAL' else
                 "This is your explicit SIM alternative. No physical connection or motion is started."))
            if self._state['mode']=='REAL' and robot_available:
                self._persist()
                self._external_started=True
                try:self.robot_preparation.check(self._request_owner,correlation={'workflow_id':self._state['session_id']})
                except BrokerError as error:
                    self._message('assistant',str(error)+' ('+error.code+'). Scene generation can still continue.',status='failed')
        self._start_generation(body['request_id'],inference_scope=inference_scope)

    def _review_navigation(self, text, request_id, *, expected_revision=None, selection=None):
        self._state['simulation_review'] = None
        if self._state['mode'] == 'REAL':
            for old in self._state['cards']:
                if old['kind'] in {'robot_goal_target','robot_goal_confirm','robot_goal_loop'} and old['state']=='waiting':old['state']='expired'
            if not self.navigation:
                self._message('assistant','Current goal navigation service is unavailable. No robot operation or SIM substitute started.',status='failed');return
            try:
                result=self.navigation.prepare(self._request_owner,text,selection=selection,expected_digest=expected_revision)
            except BrokerError as error:
                self._message('assistant',str(error)+' ('+error.code+'). Nothing moved.',status='failed')
                self._event('current_goal_rejected',code=error.code);return
            if result['choices']:
                card=self._card('robot_goal_target','Which saved object should the robot approach?',
                    [self._choice('object_'+str(i),t['label']+' · '+t['id']) for i,t in enumerate(result['choices'])]+[self._choice('cancel','Cancel goal')])
                card['related_plan_digest']=result['scene_revision']
            else:
                card=self._card('robot_goal_confirm','Confirm this current-sensor candidate route for one bounded mission?',
                    [self._choice('confirm','Confirm goal route · bounded movement'),self._choice('cancel','Cancel goal')])
                card['related_plan_digest']=result['plan']['plan_id']
                if not self.navigation.can_confirm():
                    card['choices'][0].update(enabled=False,disabled_reason='The exact route requires a verified Isaac 3D preview. Physical execution remains locked.')
                self._message('assistant','Route candidate prepared from current observations. The reviewed start becomes historical immediately; Confirm rechecks it. '
                    'Changed position, source, room, alignment or grid rejects this approval. Object goals stop outside the object; shortest candidate under the known grid, not global optimality. '+
                    ('Isaac will now demonstrate this exact route in the 3D pane; physical motion stays locked until all execution gates pass.'
                     if self.navigation.demonstration else 'The 2D route review is not an executed Isaac 3D demonstration. Nothing moved.'))
                self._event('current_goal_reviewed',plan_id=result['plan']['plan_id'])
            return
        try:
            result = self.workflow.simulation_goal(text, expected_revision=expected_revision, selection=selection)
        except BrokerError as error:
            start_help = (' Please provide the simulated start position, for example: from x=0 y=0 to x=0 y=1.5. '
                          'This is a requested simulated placement, not a measured robot location.'
                          if error.code == 'simulation_goal_rejected' and getattr(error, 'goal_error_code', None) == 'SIM_START_REQUIRED' else '')
            self._message('assistant', str(error) + ' (' + error.code + '). Nothing moved.' + start_help, status='failed')
            self._event('simulation_goal_rejected', code=error.code,
                request_id=request_id, goal_error_code=getattr(error,'goal_error_code',None),
                scene_revision=(self.workflow.snapshot().get('site_draft') or {}).get('revision'),
                goal_diagnostic=getattr(error,'goal_diagnostic',None))
            return
        self._state['simulation_review'] = {**result, 'request_id': request_id, 'text': text}
        self._state['mode'] = 'SIM'
        plan = result.get('plan')
        current_revision = (self.workflow.snapshot().get('site_draft') or {}).get('revision')
        if (plan and plan.get('asset_id') == 'turtlebot3_burger' and current_revision
                and result.get('scene_revision') == current_revision and plan.get('scene_revision') == current_revision):
            self._state['robot_id'] = plan['asset_id']
        if result['choices']:
            card = self._card('simulation_target', 'Which saved object should the simulated Burger approach?',
                [self._choice('object_' + str(i), t['label'] + ' · ' + t['id']) for i,t in enumerate(result['choices'])] + [self._choice('cancel', 'Cancel route')])
            card['related_plan_digest'] = result['scene_revision']
            self._event('simulation_goal_clarification', request_id=request_id,
                scene_revision=result['scene_revision'], card_id=card['id'], choices=len(result['choices']))
        else:
            target = result['target']
            label = target['label'] + ' (' + target['id'] + ')' if target else 'the explicit coordinate'
            self._message('assistant', 'SIM route ready to ' + label + '. Review the dashed candidate route below, then select Run simulation. '
                'Object goals stop outside the object. This uses bounded offline language rules, not a model call or a globally optimal path claim. Nothing moved.')
            self._event('simulation_route_reviewed', plan_id=result['plan']['plan_id'], scene_revision=result['scene_revision'],
                goal_diagnostic=result.get('approach_diagnostic'))

    def _ensure_site_review(self):
        snapshot = self.workflow.snapshot()
        site = snapshot.get("site_draft")
        if not site:
            raise BrokerError("site_scene_required", "Add/Change needs an existing v2 site scene. No scene was modified.", status=409)
        if snapshot["phase"] == "restore_review_required":
            self.workflow.resume_saved_scene(self._state["project_id"], site["revision"], site["input_revision"])

    def _edit_message(self, body, *, record_user=True):
        if body["attachment"] is not None:
            raise BrokerError("edit_attachment_pending", "Image-based scene edits are not yet supported. Keep this image and describe one change with explicit coordinates.", status=409)
        self._ensure_site_review()
        if body['text'].strip().lower() in EXACT_UNDO_COMMANDS:
            if record_user:self._message('user',body['text'])
            value=self.workflow.preview_scene_edit(operation_id='edit_'+uuid4().hex,mode='undo',target_call_id=None,tool_call=None)
            self._offer_feedback_preview(value,'Undo the last edit as a fresh revision?')
            return
        if self.workflow.scene_edit_proposal_service is not None or getattr(self.workflow,'generation_approvals',None):
            if record_user:self._message('user',body['text'])
            self._begin_feedback(body['text'],body.get('request_id') or 'feedback_'+uuid4().hex,
                origin_message_id=body.get('origin_message_id'))
            return
        context = self.workflow.scene_edit_context(body["text"], None)
        text = body["text"].lower()
        kinds = [kind for kind in ("bed", "wardrobe", "desk", "chair", "sofa", "dining_table", "storage")
                 if re.search(r"\b" + kind.replace("_", r"[ _]") + r"\b", text)]
        if record_user: self._message("user", body["text"])
        if len(kinds) != 1:
            self._message("assistant", "Specify one furniture type to add or change: bed, wardrobe, desk, chair, sofa, dining table, or storage. Existing objects are unchanged.")
            return
        kind = kinds[0]
        xy = [re.search(r"\b" + axis + r"\s*=\s*(-?\d+(?:\.\d+)?)\b", text) for axis in ("x", "y")]
        if not all(xy):
            self._message("assistant", f"Where should the {kind.replace('_',' ')} go? Provide X and Y in metres, for example x=1 y=1. No placement was inferred from a photo.")
            return
        calls = context["furniture_calls"]
        target = None
        if body["mode"] == "change":
            matches = [call for call in calls if call["arguments"]["kind"] == kind]
            named = [call for call in matches if call["arguments"]["id"].lower() in text]
            if len(matches) != 1 and len(named) != 1:
                self._message("assistant", "Choose the item by its saved ID: " + ", ".join(call["arguments"]["id"] for call in matches) if matches else "No matching furniture is present. Choose Add to create a new item.")
                return
            target = (named or matches)[0]
        yaw = re.search(r"\byaw\s*=\s*(-?\d+(?:\.\d+)?)\b", text)
        from twinpulse_core.furniture import FURNITURE_CATALOG_VERSION
        arguments = {"id": target["arguments"]["id"] if target else "furn_" + uuid4().hex[:12],
                     "kind": kind, "catalog_version": FURNITURE_CATALOG_VERSION,
                     "center_m": [float(value.group(1)) for value in xy],
                     "yaw_deg": float(yaw.group(1)) if yaw else target["arguments"]["yaw_deg"] if target else 0.0}
        try:
            preview = self.workflow.preview_scene_edit(operation_id="edit_" + uuid4().hex,
                mode="change" if target else "add", target_call_id=target["call_id"] if target else None,
                tool_call={"call_id": target["call_id"] if target else "furn_" + uuid4().hex[:12], "tool":"place_furniture", "arguments":arguments})
        except BrokerError as error:
            self._message("assistant", str(error) + " (" + error.code + "). No edit was applied.", status="failed")
            return
        self._state["pending_edit"] = preview
        card=self._card("scene_edit", f"{body['mode'].capitalize()} {kind.replace('_',' ')} at X={arguments['center_m'][0]} m, Y={arguments['center_m'][1]} m, yaw={arguments['yaw_deg']}°. Apply this validated edit?",
                   [self._choice("apply", "Apply edit"), self._choice("cancel", "Cancel")])
        card['related_plan_digest']=preview['parent_revision']
        card['operation_id']=preview['operation']['operation_id']

    def _offer_feedback_preview(self,preview,explanation,*,origin_message_id=None):
        self._state['pending_edit']={**preview,'apply_version':'scene-edit-apply-2.0'}
        card=self._card('scene_edit',explanation+' Review the before/after changes, then update this Twin?',
            [self._choice('apply','Apply and update Twin'),self._choice('cancel','Cancel')],origin_message_id=origin_message_id)
        card['related_plan_digest']=preview['parent_revision'];card['operation_id']=preview['operation']['operation_id']

    def _begin_feedback(self,text,request_id,*,clarification_count=0,origin_message_id=None):
        if self._feedback_worker and self._feedback_worker.is_alive():
            raise BrokerError('scene_feedback_busy','Wait for the current feedback proposal.',status=409)
        self._ensure_site_review()
        context=self.workflow.scene_edit_context(text,None,dependency=True)
        self._state['scene_feedback']=dict(operation_id='feedback_'+uuid4().hex,state='prepared',context=context,
            clarification_count=clarification_count,error=None,
            origin_message_id=origin_message_id or next((m['message_id'] for m in reversed(self._state['messages']) if m['role']=='user'),None))
        approvals=getattr(self.workflow,'generation_approvals',None)
        if approvals and getattr(approvals,'product_mode',False):
            self._start_feedback_call(request_id,approvals.scope(edit_context=context))
            return
        if self.workflow.scene_edit_proposal_service is None:
            if not approvals or not approvals.enabled():
                raise BrokerError('scene_feedback_unavailable','Save the approved staged planner route before proposing a feedback edit.',status=409)
            descriptor=approvals.prepare(edit_context=context)
            card=self._card('generation_approval','Approve one model-grounded feedback proposal?',
                [self._choice('approve','Approve feedback proposal'),self._choice('cancel','Not now')])
            card['generation_approval']=descriptor;card['scene_feedback']=True
            card['related_plan_digest']=context['current_state_sha256']
            self._state['scene_feedback']['state']='awaiting_approval'
            return
        if self.workflow._mode not in {'explicit_fixture','simulation_offline','replay'}:
            raise BrokerError('scene_feedback_fixture_forbidden','A scripted proposal cannot impersonate a live model.',status=409)
        self._start_feedback_call(request_id,None)

    def _start_feedback_call(self,request_id,scope):
        import asyncio
        from twinpulse_provider import CancellationToken,SceneEditProposalService
        service=self.workflow.scene_edit_proposal_service
        if service is None:
            from .stage_routing import build_configured_stage_service
            from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
            approvals=self.workflow.generation_approvals
            generation=build_configured_stage_service(approvals.routes.registry)
            if generation is None or not isinstance(generation._provider,BudgetedPipeline):
                raise BrokerError('scene_feedback_route_invalid','Budgeted ordinary planner is required; no fallback.',status=409)
            service=SceneEditProposalService(generation._provider,generation._config)
        job=self._state['scene_feedback'];job.update(state='running',request_id=request_id)
        if scope is not None:job['approval_id']=scope.approval_id
        self._feedback_service=service
        identity=job['operation_id'];context=deepcopy(job['context'])
        token=CancellationToken();self._feedback_token=token
        trace=self.workflow._application.diagnostics.begin('scene_feedback',request_id=request_id,
            operation_id=identity,scene_edit_revision=context['current_scene_revision'],
            context_sha256=context['context_sha256'],scene_state_sha256=context['current_state_sha256'],
            feedback_approval_id=job.get('approval_id'))
        job['execution_id']=trace.execution_id
        self._message('assistant','Reading the current scene and retained unresolved items for a bounded proposal. Nothing is applied yet.',status='pending',operation_id=identity)
        self._event('scene_feedback_started',operation_id=identity,fixture=scope is None)
        self._persist();self._external_started=True
        def candidate_validator(proposal):
            # Never hold the conversation mutex during project replay/compile.
            # Both fences reject late work after cancellation/project changes.
            from twinpulse_provider.errors import GenerationCancelledError
            from .dependency_patch import CandidatePoseClearanceError
            def fence():
                with self._lock:
                    current=self._state.get('scene_feedback')
                    if (token.is_cancelled or not current or current.get('operation_id')!=identity
                            or current.get('state')!='running' or self._feedback_token is not token):
                        raise GenerationCancelledError('Feedback candidate owner changed; no additional request or preview.')
            fence()
            if proposal is None:
                observed=self.workflow.scene_edit_context(context['request_text'],None,dependency=True)
                if observed['context_sha256']!=context['context_sha256']:
                    raise BrokerError('scene_edit_proposal_stale','Scene changed during feedback; no retry.',status=409)
                fence();return None
            try:
                self.workflow.preview_scene_edit_proposal(operation_id='validate_'+uuid4().hex,
                    request_text=context['request_text'],selected_call_id=None,
                    expected_revision=context['current_scene_revision'],proposal=proposal)
            except BrokerError as error:
                fence()
                # Only the candidate's exact floor predicate; source replay,
                # identity/scope/support/storage/no-op errors never retry.
                if isinstance(error.__cause__,CandidatePoseClearanceError):
                    return deepcopy(error.__cause__.diagnosis)
                raise
            fence();return None
        product_feedback=bool(scope is not None and getattr(getattr(self.workflow,'generation_approvals',None),'product_mode',False))
        def run():
            try:
                result=asyncio.run(service.propose(context,request_id,inference_scope=scope,diagnostics=trace,token=token,
                    **({'feedback_candidate_validator':candidate_validator} if product_feedback else {})))
                outcome=(identity,result,None,trace,service)
            except Exception as error:outcome=(identity,None,error,trace,service)
            with self._lock:self._feedback_outcome=outcome
        self._feedback_worker=Thread(target=run,name='TwinPulseSceneFeedback',daemon=True);self._feedback_worker.start()

    def _sync_feedback(self,owner):
        job=self._state['scene_feedback']
        if job and self._feedback_service and job.get('request_id'):
            diagnostic=getattr(self._feedback_service._provider,'diagnostic_for',lambda _:None)(job['request_id'])
            if diagnostic:
                from .product_workflow_service import _public_generation_diagnostics
                job['progress']=_public_generation_diagnostics(diagnostic)
        outcome=self._feedback_outcome
        if outcome:
            self._feedback_outcome=None
            identity,result,error,trace,service=outcome;job=self._state['scene_feedback']
            if not job or job['operation_id']!=identity:
                trace.finish('failed',error_code='scene_feedback_stale');return
            try:
                if job['state']=='cancelled':
                    from twinpulse_provider.errors import GenerationCancelledError
                    raise GenerationCancelledError('Feedback response was stopped; late output ignored.')
                if error:raise error
                context=job['context']
                from twinpulse_core import canonical_sha256
                lineage=dict(feedback_execution_id=trace.execution_id,feedback_operation_id=identity,
                    feedback_request_id=job['request_id'],feedback_approval_id=job.get('approval_id'),
                    feedback_context_sha256=context['context_sha256'],feedback_response_sha256=canonical_sha256(result),
                    feedback_preview_execution_id=trace.execution_id)
                trace.bind(**{key:value for key,value in lineage.items() if key!='feedback_preview_execution_id'})
                candidate=self.workflow.preview_scene_edit_proposal(operation_id='edit_'+uuid4().hex,
                    request_text=context['request_text'],selected_call_id=None,
                    expected_revision=context['current_scene_revision'],proposal=result,_feedback_lineage=lineage)
                if candidate['status']=='clarify':
                    if job['clarification_count']:
                        raise BrokerError('scene_feedback_unresolved','The target or metric change is still ambiguous. No edit was made.',status=409)
                    card=self._card('scene_edit_clarify',candidate['explanation'],[self._choice('cancel','Cancel feedback')],origin_message_id=job.get('origin_message_id'))
                    card['related_plan_digest']=context['current_state_sha256'];job['state']='clarify'
                else:
                    self._offer_feedback_preview(candidate['preview'],candidate['explanation'],origin_message_id=job.get('origin_message_id'));job['state']='preview'
                self._event('scene_feedback_'+job['state'],operation_id=identity);trace.finish()
            except Exception as error:
                from .product_workflow_service import _public_generation_error
                public=_public_generation_error(error);cancelled=job['state']=='cancelled'
                job.update(state='cancelled' if cancelled else 'failed',error=public['message'])
                self._message('assistant',public['message']+' No edit applied and no automatic retry.',status='failed',operation_id=identity)
                self._event('scene_feedback_failed',operation_id=identity,code=getattr(error,'code',public['code']))
                trace.finish('failed',error=error)
            # Close only this operation's historical waiting messages. Other
            # generations, projects and ambiguous legacy rows are untouched.
            for message in self._state['messages']:
                if (message['role']=='assistant' and message.get('operation_id')==identity
                        and message['status']=='pending'):
                    message['status']='completed' if job['state'] in {'preview','clarify'} else job['state']
            self._persist()
        # A confirmed edit is durable history. Later viewer staleness must not
        # reopen its chat task, including older duplicate waiting rows on disk.
        confirmed_edits={message.get('operation_id') for message in self._state['messages']
            if message['role']=='assistant' and message['status']=='completed'
            and message.get('operation_id') and message['content'].startswith(
                'Twin updated, saved and its current 3D frame confirmed.')}
        settled=False
        for message in self._state['messages']:
            if (message['role']=='assistant' and message['status']=='pending'
                    and message.get('operation_id') in confirmed_edits):
                message['status']='completed';settled=True
        if settled:self._persist()
        transaction=self.workflow.scene_edit_transaction.snapshot(owner)
        if transaction:
            marker=(transaction.get('operation_id'),transaction['state'],transaction.get('current_frame'),transaction.get('error'))
            if marker!=self._edit_transaction_marker:
                self._edit_transaction_marker=marker
                state=transaction['state']
                operation_id=transaction.get('operation_id')
                was_confirmed=operation_id in confirmed_edits
                frame_confirmed=bool(transaction.get('current_frame'))
                waiting_prefix='Engine acknowledged and the new revision is saved. Waiting for its current 3D frame;'
                if state in {'COMMITTED','ROLLED_BACK','ENGINE_STATE_UNKNOWN'}:
                    for message in self._state['messages']:
                        if (message['role']=='assistant' and message.get('operation_id')==operation_id
                                and message['status']=='pending'):
                            if state!='COMMITTED':message['status']='failed'
                            elif frame_confirmed or was_confirmed or not message['content'].startswith(waiting_prefix):
                                message['status']='completed'
                if state=='COMMITTED':
                    already_waiting=any(message['role']=='assistant' and message.get('operation_id')==operation_id
                        and message['status']=='pending' and message['content'].startswith(waiting_prefix)
                        for message in self._state['messages'])
                    if not was_confirmed and (frame_confirmed or not already_waiting):
                        text=('Twin updated, saved and its current 3D frame confirmed.' if frame_confirmed else
                            waiting_prefix+' display is not yet confirmed.')
                        self._message('assistant',text+' Previous goal plans remain invalid; request a fresh goal.',
                            status='completed' if frame_confirmed else 'pending',operation_id=operation_id)
                    if frame_confirmed and getattr(self,'_auto_route_edits',None):self._apply_next_auto_edit()
                    elif frame_confirmed and getattr(self,'_auto_replan_pending',False):self._auto_replan_pending=False;self._auto_replan()
                elif state in {'ROLLED_BACK','ENGINE_STATE_UNKNOWN'}:
                    self._auto_route_edits=[]
                    self._message('assistant',('Previous saved revision was restored with a compensation engine ACK.' if state=='ROLLED_BACK' else
                        'Engine/save state is unknown. Geometry and Run are locked; inspect and explicitly recover the retained transaction.')+
                        (' '+transaction['error'] if transaction.get('error') else ''),status='failed')
                self._event('scene_edit_transaction',state=state,operation_id=transaction.get('operation_id'))
                self._persist()

    def _start_generation(self, request_id, *, inference_scope=None, continuation_checkpoint=None, review_resume=False):
        previous=self._state.get('generation')
        # Revalidate persisted input with the existing validator after a restart.
        self.workflow.select_input(self._state["pending_input"])
        approvals = getattr(self.workflow, 'generation_approvals', None)
        if approvals and approvals.enabled() and getattr(approvals,'product_mode',False) and inference_scope is None:
            previous=self._state['generation']
            progress=(previous.get('progress') or {}) if previous and review_resume else {}
            # A local preflight failure may have no new checkpoint. Its
            # hash-bound parent remains the unfinished work, not fresh input.
            # scope() independently rechecks this parent and original input.
            checkpoint=progress.get('checkpoint_id') or progress.get('parent_checkpoint_id')
            if review_resume and previous and not checkpoint and previous.get('approval_id'):
                checkpoint=approvals.checkpoint_for_approval(previous['approval_id'])
            if review_resume and not checkpoint:
                raise BrokerError('generation_checkpoint_unavailable',
                    'The retained checkpoint is unavailable. Resume did not start a new generation. No request was sent.',status=409)
            scope=approvals.scope(checkpoint=checkpoint)
            self._start_generation(request_id,inference_scope=scope,continuation_checkpoint=checkpoint,review_resume=review_resume)
            return
        if approvals and approvals.enabled() and inference_scope is None:
            previous = self._state['generation']
            checkpoint = (previous.get('progress') or {}).get('checkpoint_id') if previous and review_resume else None
            try:
                if review_resume and previous and not checkpoint and previous.get('approval_id'):
                    checkpoint = approvals.checkpoint_for_approval(previous['approval_id'])
                # Explicit review only: settlement creates a derived snapshot,
                # never deletes the old failure or itself dispatches a request.
                if checkpoint:
                    checkpoint = approvals.reconcile(checkpoint)
                preview = approvals.prepare(checkpoint=checkpoint)
            except BrokerError as error:
                operation = str(uuid4())
                self._state['generation'] = {'operation_id': operation, 'state': 'failed', 'generation_id': None,
                    'request_id': request_id, 'summary': str(error), 'started_at': now(), 'last_progress_at': now(),
                    'can_cancel': False, 'error': {'code': error.code, 'message': str(error)},
                    **({'progress': previous.get('progress')} if previous and review_resume and previous.get('progress') else {}),
                    **({'approval_id': previous['approval_id']} if previous and review_resume and previous.get('approval_id') else {})}
                self._message('assistant', str(error), status='failed', operation_id=operation)
                return
            card = self._card('generation_approval', 'Approve a new budget to continue the saved scene draft?' if checkpoint else
                'Approve this scene-generation action and its spending limit?',
                [self._choice('approve', 'Approve generation'), self._choice('cancel', 'Not now')])
            card['generation_approval'] = preview
            card['related_plan_digest'] = preview['input_revision']
            self._event('generation_approval_requested', card_id=card['id'])
            return
        operation = str(uuid4())
        job = {"operation_id": operation, "state": "accepted", "generation_id": None, "request_id": request_id,
               "summary": "Starting the existing scene generation service…", "started_at": now(),
               "last_progress_at": now(), "can_cancel": True, "error": None}
        if review_resume and continuation_checkpoint:
            from copy import deepcopy
            retained=deepcopy((previous or {}).get('progress') or {})
            retained['checkpoint_id']=continuation_checkpoint
            retained['generation_activity']={'schema_version':'generation-activity-1.0',
                'stage':'resume_revalidation','phase':'validating'}
            # Do not attach an earlier execution's successful save recheck to
            # the newly accepted resume. Its checkpoint remains preserved.
            retained.pop('retention_revalidation',None)
            if retained.get('generation_preview'):
                retained['generation_preview'].update(state='blocked',error_code='PREVIEW_REBUILD_REQUIRED')
            job['progress']=retained
        # The SIM/robot choice is a user reply, not the generation input.
        pending=self._state['pending_input']
        origin=next((m for m in self._state['messages'] if m['role']=='user' and
            m['message_id']==self._state.get('pending_input_origin')),None)
        origin=origin or next((m for m in reversed(self._state['messages']) if m['role']=='user'
            and m['content']==pending['prompt'] and (not pending.get('name') or
                any(a.get('name')==pending['name'] for a in m.get('attachments',[])))),None)
        job['origin_message_id']=origin['message_id'] if origin else None
        if origin and origin.get('operation_id') is None:origin['operation_id']=operation
        if inference_scope is not None:
            job['approval_id'] = inference_scope.approval_id
        self._state["generation"] = job
        # Journal intent BEFORE the external service, never replay on app restart.
        self._event('generation_accepted', operation_id=operation)
        self._persist()
        try:
            workflow = self.workflow.start_generation(correlation={
                'workflow_id': self._state['session_id'],
                'operation_id': operation, 'chat_request_id': request_id},
                **({'owner': self._request_owner} if getattr(self.workflow, 'render_review_port_factory', None) else {}),
                **({'inference_scope': inference_scope, 'continuation_checkpoint': continuation_checkpoint}
                   if inference_scope is not None else {}))
        except BrokerError as error:
            job.update(state="failed", summary=str(error), can_cancel=False,
                       error={"code": error.code, "message": str(error)})
            self._message("assistant", str(error), status="failed", operation_id=operation)
            self._event("generation_failed", operation_id=operation)
            return
        except Exception as error:
            from .product_workflow_service import _public_generation_error
            public_error = _public_generation_error(error)
            job.update(state="failed", summary=public_error["message"], can_cancel=False, error=public_error)
            self._message("assistant", job["summary"], status="failed", operation_id=operation)
            self._event("generation_failed", operation_id=operation, error_type=type(error).__name__)
            return
        self._external_started = True
        job.update(state="running", generation_id=workflow["generation_id"],
                   summary="Generating and validating the scene through the configured provider and ToolCatalog.")
        self._event("generation_started", operation_id=operation)

    def _cancel(self, body):
        feedback=self._state['scene_feedback']
        if feedback and feedback['operation_id']==body['operation_id']:
            if feedback['state']=='running':
                if self._feedback_token:self._feedback_token.cancel()
                feedback['state']='cancelled'
                self._message('assistant','Feedback response stopped. Late output will be ignored; uncertain request charges remain reserved. No edit was applied.')
                self._event('scene_feedback_cancelled',operation_id=feedback['operation_id'])
            return
        job = self._state["generation"]
        if not job or job["operation_id"] != body["operation_id"]:
            raise BrokerError("operation_stale", "Generation operation is not current", status=409)
        if job["state"] != "running": return
        self.workflow.cancel()
        self._sync_generation()
