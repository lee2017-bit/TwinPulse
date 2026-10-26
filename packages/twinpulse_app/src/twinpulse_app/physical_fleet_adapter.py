# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Per-instance physical services; read-only connection is never a drive lease.

The workspace owns this pool once, outside project/selection lifetimes. Services
are bound once and never rebound by focus(). Only check_connection() invokes the
existing explicit read-only checker. No constructor/snapshot opens transport.

The explicit persistent worker separates heartbeat/sensor/control lifetimes.
Measured profiles and robot-local qualification, never a UI flag, admit drive.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from threading import RLock,Thread
import time
from uuid import UUID, uuid4
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_SEGMENTS

from .command_broker import BrokerError
from .robot_adapters import instance_binding, require_adapter
from .session_journal import SessionJournal
from twinpulse_core.robot_lineage import checked_twin_context
from twinpulse_core.robot_battery import battery_estimate, battery_display_estimate, battery_display_config


def _uuid(value, label):
    try:
        if not isinstance(value, str):
            raise ValueError()
        return UUID(value).hex
    except (ValueError, AttributeError):
        raise BrokerError('physical_fleet_id', 'Invalid ' + label + '.', status=400) from None


def _owner(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise BrokerError('physical_fleet_owner', 'An authenticated owner is required.', status=403)


def _endpoint(binding):
    endpoint = binding['endpoint']
    # Different users/domains still address the same board on this SSH endpoint.
    return endpoint['host'].rstrip('.').casefold(), endpoint['port']


@dataclass
class PhysicalFleetServices:
    diagnostics: object
    readiness: object = None
    controller: object = None
    live: object = None


@dataclass
class _Session:
    binding: dict
    label: str
    services: PhysicalFleetServices
    lock: object = field(default_factory=RLock)
    owner: str | None = None
    connection_epoch: str = field(default_factory=lambda: uuid4().hex)
    motion_epoch: str = field(default_factory=lambda: uuid4().hex)
    operation_id: str | None = None
    project_id: str | None = None
    source_twin_context: dict | None = None
    journal: object = None
    events: list = field(default_factory=list)
    dropped_events: int = 0
    disconnected: bool = False
    disconnecting: bool = False
    cleanup_uncertain: bool = False
    reason: str | None = None
    footer_written: bool = False
    footer_error: str | None = None


class PhysicalFleetAdapter:
    """Lazy, bounded pool sharing the workspace's existing device-owner lease.

    services_factory(binding, archive_root) is a local injection seam for tests;
    it must not spawn transport. The default creates the existing services.
    API integration must keep this object on WorkspaceDevices, route explicit
    actions by robot_id, and call close() only at workspace shutdown.
    """
    def __init__(self, devices, source_root, state_root, *, services_factory=None,
                 clock=time.monotonic, wall=lambda: time.time() * 1000):
        registry_service = getattr(devices, 'registry_service', None)
        if registry_service is None:
            raise BrokerError('robot_registry_unavailable', 'Robot registry is unavailable.', status=409)
        self.devices, self.registry = devices, registry_service.registry
        self.source_root, self.state_root = Path(source_root), Path(state_root)
        self.clock, self.wall = clock, wall
        self.lock = RLock()
        self.sessions, self.requests, self.focused, self.operations = {}, {}, {}, {}
        self.closed = False
        self.factory = services_factory or self._services
        from .physical_motion_review import PhysicalMotionReview
        self.motion_reviews=PhysicalMotionReview(devices,self.source_root,self.state_root)

    def _services(self, binding, archive_root):
        from .robot_diagnostics import RobotDiagnostics
        from .physical_controller import PhysicalController
        from .robot_readiness import RobotReadiness
        from .physical_live_session import PhysicalLiveSession
        existing = self.devices.diagnostics
        diagnostics = RobotDiagnostics(self.source_root, archive_root=archive_root,
            identity=existing.identity, known_hosts=existing.known_hosts)
        enabled = self.devices.controller is not None
        return PhysicalFleetServices(diagnostics,
            RobotReadiness(self.source_root, archive_root=archive_root) if enabled else None,
            PhysicalController(self.source_root, archive_root=archive_root) if enabled else None,
            PhysicalLiveSession(self.source_root, self.state_root/'physical-live',
                identity=existing.identity,known_hosts=existing.known_hosts,
                on_timing_measurement=lambda context,measurement:self.registry.record_timing_measurement(
                    context['robot_id'],context['binding_sha256'],context['operation_id'],measurement)) if enabled else None)

    def _row(self, robot_id):
        identity = _uuid(robot_id, 'robot ID')
        row = self.registry.registered(identity)
        if row is None:
            raise BrokerError('physical_fleet_unknown', 'Registered robot not found.', status=404)
        if identity == '0' * 32:
            raise BrokerError('physical_fleet_legacy_identity', 'Register a non-legacy robot identity.', status=409)
        binding = instance_binding(row)
        require_adapter(binding, operation='observation')
        return row, binding

    def _entry(self, robot_id, *, create=False):
        row, binding = self._row(robot_id)
        with self.lock:
            if self.closed or getattr(self.devices, 'closed', False):
                raise BrokerError('physical_fleet_closed', 'Physical fleet is closed.', status=409)
            entry = self.sessions.get(row['id'])
            if entry is not None and not entry.disconnected and not (entry.services.live is not None and entry.services.live.closed):
                if entry.disconnecting or entry.cleanup_uncertain:
                    raise BrokerError('physical_fleet_cleanup_uncertain', 'The previous services have not confirmed local cleanup.', status=409)
                if entry.binding != binding:
                    raise BrokerError('physical_fleet_binding_changed', 'Disconnect the old instance before changing its endpoint or adapter.', status=409)
                entry.label = row['label']
                return entry
            if not create:
                return None
            if self.devices.diagnostics is None:
                raise BrokerError('robot_diagnostics_unavailable', 'Read-only connection is disabled in this release.', status=409)
            if len(self.sessions) >= 32 and row['id'] not in self.sessions:
                raise BrokerError('physical_fleet_capacity', 'Physical service pool is full.', status=409)
            for other in self.sessions.values():
                if (not other.disconnected and not (other.services.live is not None and other.services.live.closed)
                        and _endpoint(other.binding) == _endpoint(binding)):
                    raise BrokerError('physical_fleet_endpoint_owned', 'This endpoint is already reserved by another robot instance.', status=409)
            archive = self.state_root / 'physical-fleet' / row['id']
            services = self.factory(deepcopy(binding), archive)
            if not isinstance(services, PhysicalFleetServices) or services.diagnostics is None:
                raise ValueError('PHYSICAL_FLEET_FACTORY_INVALID')
            for service in (services.diagnostics, services.readiness, services.controller, services.live):
                if service is not None:
                    service.bind_instance(binding)
            entry = _Session(deepcopy(binding), row['label'], services)
            self.sessions[row['id']] = entry
            return entry

    def _claim(self, entry, owner):
        _owner(owner)
        if entry.owner is not None and entry.owner != owner:
            raise BrokerError('physical_fleet_owned', 'Another authenticated session owns this robot.', status=409)
        entry.owner = owner

    def _cached(self, robot_id):
        # Registry edits/removal must never prevent stopping the pinned session.
        identity = _uuid(robot_id, 'robot ID')
        with self.lock:
            return self.sessions.get(identity)

    def _admission(self, entry, owner):
        if getattr(self.devices,'engine_process_probe_blocked',False):
            raise BrokerError('engine_observation_stale','Wait for current engine observation before connecting.',status=409)
        # Equivalent scene/collection checks, applied per target rather than
        # using the old workspace-wide "any robot busy" selection restriction.
        for context in getattr(self.devices, 'contexts', []):
            workspace = getattr(context, 'workspace', None)
            workflow = getattr(context, 'product_workflow', None)
            if workspace is not None and workspace.switching():
                raise BrokerError('project_switch_pending', 'Wait for the conversation switch.', status=409)
            if workflow is not None and (workflow.scene_edit_transaction.locked() or workflow.has_active_generation()):
                raise BrokerError('robot_registry_workspace_busy', 'Finish the active scene change before connecting.', status=409)
            preparation = getattr(context, 'chat_robot_preparation', None)
            navigation = getattr(getattr(context, 'conversation', None), 'navigation', None)
            task = getattr(navigation, 'task_loop', None)
            workers = [getattr(getattr(context, name, None), 'worker', None)
                       for name in ('automatic_mission', 'automatic_demo')]
            if (preparation is not None and preparation._busy()
                    or task is not None and task.active()
                    or any(worker is not None and worker.is_alive() for worker in workers)):
                raise BrokerError('robot_registry_workspace_busy', 'Finish the active legacy robot task before connecting.', status=409)
        readiness, controller = entry.services.readiness, entry.services.controller
        if readiness is not None and readiness.blocks_read_only_observation():
            raise BrokerError('readiness_busy_or_uncertain', 'This robot has an active or uncertain collection.', status=409)
        if controller is not None and controller.snapshot(owner).get('busy'):
            raise BrokerError('robot_operation_busy', 'This robot already owns its board ports.', status=409)
        # During migration, legacy services and pooled services may coexist.
        # Never open the same endpoint in both paths, even under another label.
        for service, active in ((self.devices.diagnostics, '_running'),
                                (self.devices.readiness, 'blocks_read_only_observation')):
            if service is not None and getattr(service, active)():
                value = service.snapshot(owner)
                binding = (value.get('job') or {}).get('robot_binding') or value.get('robot_binding') or value.get('selected_robot_binding')
                if binding is None or _endpoint(binding) == _endpoint(entry.binding):
                    raise BrokerError('physical_fleet_legacy_busy', 'The legacy path still owns this robot.', status=409)
        legacy = self.devices.controller
        if legacy is not None:
            value = legacy.snapshot(owner)
            if value.get('busy'):
                binding = value.get('robot_binding') or value.get('selected_robot_binding')
                if binding is None or _endpoint(binding) == _endpoint(entry.binding):
                    raise BrokerError('physical_fleet_legacy_busy', 'The legacy controller still owns this robot.', status=409)

    def _event(self, entry, kind, **data):
        if entry.operation_id is None:
            return
        event = dict(schema_version='physical-fleet-event-1.0', operation_id=entry.operation_id,
            robot_id=entry.binding['instance_id'], project_id=entry.project_id,
            connection_epoch=entry.connection_epoch, motion_epoch=entry.motion_epoch,
            sequence=len(entry.events) + entry.dropped_events + 1, kind=kind,
            utc=datetime.now(timezone.utc).isoformat(), monotonic_s=self.clock(), data=data)
        if len(entry.events) >= 256:
            entry.dropped_events += 1
            return
        entry.events.append(event)
        if entry.journal is not None and not entry.journal.append(event):
            entry.dropped_events += 1

    def check_connection(self, robot_id, owner, *, request_id, operation_id, project_id, source_twin_context=None):
        """Explicit read-only action; same preflight/token checker as RegistryService."""
        _owner(owner)
        request_id, operation_id = _uuid(request_id, 'request ID'), _uuid(operation_id, 'operation ID')
        if not isinstance(project_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', project_id):
            raise BrokerError('physical_fleet_project', 'Current project ID is required.', status=400)
        if source_twin_context is not None:
            source_twin_context=checked_twin_context(source_twin_context,project_id=project_id)
        entry = self._entry(robot_id, create=True)
        # Legacy admission uses this same workspace start lock. Never hold the
        # pool lock while waiting for it or while invoking a service.
        with self.devices.lock, entry.lock:
            self.motion_reviews.cancel_for_start()
            self._claim(entry, owner)
            if entry.disconnecting or entry.disconnected or entry.cleanup_uncertain or self.closed:
                raise BrokerError('physical_fleet_closed', 'This instance is closing or closed.', status=409)
            identity = (entry.binding['sha256'], entry.connection_epoch, owner, operation_id, project_id,
                        source_twin_context['context_id'] if source_twin_context is not None else None)
            with self.lock:
                prior = self.requests.get(request_id)
                if prior is not None:
                    if prior['identity'] != identity:
                        raise BrokerError('physical_fleet_request_reused', 'Request ID content changed.', status=409)
                    if prior.get('error'):
                        code, message, status = prior['error']
                        raise BrokerError(code, message, status=status)
                    return self._snapshot(entry, owner)
                if len(self.requests) >= 256:
                    raise BrokerError('physical_fleet_request_capacity', 'Physical request history is full.', status=409)
            self._admission(entry, owner)
            if entry.operation_id is not None and (entry.operation_id, entry.project_id) != (operation_id, project_id):
                raise BrokerError('physical_fleet_operation_changed', 'Keep the same operation/project until explicit disconnect.', status=409)
            if entry.operation_id is not None and entry.source_twin_context!=source_twin_context:
                raise BrokerError('physical_fleet_twin_changed','The operation Twin reference is immutable. Disconnect and explicitly reconnect for a new reference.',status=409)
            if entry.operation_id is None:
                with self.lock:
                    if operation_id in self.operations:
                        raise BrokerError('physical_fleet_operation_reused', 'Operation ID already belongs to another connection.', status=409)
                directory = self.state_root / 'physical-fleet-operations'
                directory.mkdir(parents=True, exist_ok=True)
                journal = SessionJournal(directory / (operation_id + '.jsonl'), max_bytes=1024 * 1024)
                try:
                    journal.start()  # Exclusive local evidence creation before remote work.
                except FileExistsError:
                    raise BrokerError('physical_fleet_operation_reused', 'A saved operation already uses this ID; start a new explicit connection operation.', status=409) from None
                entry.operation_id, entry.project_id, entry.journal = operation_id, project_id, journal
                entry.source_twin_context=deepcopy(source_twin_context)
                with self.lock:
                    self.operations[operation_id] = entry
                self._event(entry, 'operation_started', binding_sha256=entry.binding['sha256'],
                            adapter_id=entry.binding['adapter_id'], adapter_version=entry.binding['adapter_version'],
                            **({'source_twin_context':deepcopy(entry.source_twin_context)} if entry.source_twin_context is not None else {}))
            with self.lock:
                # Reserve before transport. An uncertain start is never replayed.
                receipt = self.requests[request_id] = {'identity': identity}
            try:
                if entry.services.live is not None:
                    self._event(entry,'persistent_connection_requested',request_id=request_id)
                    entry.services.live.start(dict(operation_id=entry.operation_id,
                        robot_id=entry.binding['instance_id'],project_id=entry.project_id,
                        connection_epoch=entry.connection_epoch,motion_epoch=entry.motion_epoch,
                        timing_profile=self.registry.timing_store.read(entry.binding['instance_id'],entry.binding['sha256'])['profile'],
                        **({'source_twin_context':deepcopy(entry.source_twin_context)} if entry.source_twin_context is not None else {})))
                    profile=self.profile_for_view(entry.binding['instance_id'])
                    # Restoring data is not restoring authority. The transport
                    # sends this only after a matching fresh robot heartbeat.
                    if profile is not None:entry.services.live.pending_profile=profile
                    config=self.field_config_for_view(entry.binding['instance_id'])
                    if config is not None:entry.services.live.pending_field_setup=config
                    self._event(entry,'persistent_worker_started',profile_available=profile is not None)
                    return self._snapshot(entry,owner)
                diagnostics = entry.services.diagnostics
                prepared = diagnostics.preflight(owner)
                token = prepared.get('start_token')
                if not token:
                    raise BrokerError('robot_preflight_required', 'Existing SSH client, automation key and trusted host entry are required.', status=409)
                self._event(entry, 'read_only_connection_requested', request_id=request_id)
                result = diagnostics.start(owner, token, True)
                job = result.get('job') or {}
                self._event(entry, 'read_only_job_bound', job_id=job.get('id'), execution_id=job.get('execution_id'))
                return self._snapshot(entry, owner)
            except BrokerError as error:
                receipt['error'] = (error.code, str(error), error.status)
                self._event(entry, 'connection_rejected', reason=error.code)
                raise
            except Exception as error:
                receipt['error'] = ('physical_fleet_check_failed', 'Read-only check failed; the same request will not be replayed.', 409)
                self._event(entry, 'connection_failed', error_type=type(error).__name__)
                raise BrokerError(*receipt['error'][:2], status=409) from None

    def _stop(self, entry, owner, reason, *, close=False, request_id=None, request_twin_context=None):
        self._claim(entry, owner)
        if entry.services.live is not None:
            entry.motion_epoch=uuid4().hex
            entry.services.live.command('close' if close else 'stop',{},
                motion_epoch=entry.motion_epoch,request_id=request_id or uuid4().hex,
                **({'request_twin_context':request_twin_context} if request_twin_context is not None else {}))
            entry.reason=reason
            entry.last_gesture=None
            entry.intent_kind=None
            self._event(entry,'disconnect_requested' if close else 'stop_requested',reason=reason,
                **({'request_id':request_id,'request_twin_context':deepcopy(request_twin_context)} if request_twin_context is not None else {}))
            return
        controller = entry.services.controller
        current = controller.snapshot(owner) if controller is not None else {}
        # Always issue the stop before enqueueing metadata; storage failure must
        # not block an already owned robot's stop, and never closes on key release.
        if current.get('busy') and (close or current.get('mode') not in {'lidar', 'scan', 'off', 'prepare'}):
            if not current.get('owned') or not current.get('job_id'):
                raise BrokerError('physical_fleet_owned', 'The physical operation belongs to another owner.', status=409)
            controller.input(owner, current['job_id'], current['sequence'] + 1,
                             'close' if close else 'stop', self.wall())
        entry.motion_epoch = uuid4().hex
        entry.reason = reason
        self._event(entry, 'disconnect_requested' if close else 'stop_requested', reason=reason,
                    controller_job_id=current.get('job_id'), controller_mode=current.get('mode'),
                    **({'request_id':request_id,'request_twin_context':deepcopy(request_twin_context)} if request_twin_context is not None else {}))

    def stop(self, robot_id, owner, *, request_id=None, request_twin_context=None):
        _owner(owner)
        entry = self._cached(robot_id)
        if entry is None:
            return {'robot_id': _uuid(robot_id, 'robot ID'), 'state': 'DISCONNECTED', 'stop_sent': False}
        with entry.lock:
            self._claim(entry, owner)
            if entry.disconnected:
                return self._snapshot(entry, owner)
            self._stop(entry, owner, 'OPERATOR_STOP',request_id=request_id,request_twin_context=request_twin_context)
            return self._snapshot(entry, owner)

    def focus(self, robot_id, owner):
        _owner(owner)
        row, _ = self._row(robot_id)
        with self.lock:
            previous = self.focused.get(owner)
            if owner not in self.focused and len(self.focused) >= 32:
                raise BrokerError('physical_fleet_focus_capacity', 'Too many active UI owners.', status=409)
        if previous != row['id'] and previous is not None:
            entry = self._cached(previous)
            if entry is not None and not entry.disconnected and entry.owner == owner:
                with entry.lock:
                    if entry.services.live is not None:
                        self._release_live_manual(entry,owner)
                        # An independent finite task and native sensor keep
                        # their operation. Focus is not Disconnect or Stop All.
                    else:
                        controller=entry.services.controller
                        current=controller.snapshot(owner) if controller is not None else {}
                        if current.get('mode') in {'control','control_scan'}:self._stop(entry,owner,'FOCUS_CHANGED')
                        else:
                            entry.motion_epoch=uuid4().hex
                            self._event(entry,'focus_released',manual_stop_required=False)
        with self.lock:
            self.focused[owner] = row['id']
        return {'focused_robot_id': row['id'], 'connections_retained': True}

    def _release_live_manual(self,entry,owner):
        if getattr(entry,'intent_kind',None)=='manual':self._stop(entry,owner,'FOCUS_CHANGED')
        else:self._event(entry,'focus_released',manual_stop_required=False)

    def release_manual(self,robot_id,owner):
        entry=self._cached(robot_id)
        if entry is None:return
        with entry.lock:
            self._claim(entry,owner)
            if entry.services.live is not None:self._release_live_manual(entry,owner)
            elif entry.services.controller is not None and entry.services.controller.snapshot(owner).get('mode') in {'control','control_scan'}:
                self._stop(entry,owner,'FOCUS_CHANGED')

    def _live_command(self,robot_id,owner,action,payload,*,connection_epoch=None,motion_epoch=None,request_id=None,request_twin_context=None,route_guard=None,admission_guard=None):
        _owner(owner)
        if (action in {'prepare','qualify','drive','task','field_arm','field_test'}
                and getattr(self.devices,'engine_process_probe_blocked',False)):
            raise BrokerError('engine_observation_stale','Wait for current engine observation before a new physical operation.',status=409)
        entry=self._entry(robot_id)
        if entry is None:raise BrokerError('physical_connection_required','Connect the robot first.',status=409)
        with entry.lock:
            self._claim(entry,owner)
            if entry.services.live is None:
                raise BrokerError('physical_protective_guards_unavailable' if action in {'drive','task','prepare','qualify'} else 'physical_native_lidar_unavailable',
                    'This observation-only release cannot run the reviewed physical session. Use the physical development candidate.',status=409)
            live_epoch=getattr(entry.services.live,'motion_epoch',None)
            if isinstance(live_epoch,str) and live_epoch!=entry.motion_epoch:
                entry.motion_epoch=live_epoch;entry.last_gesture=None;entry.intent_kind=None
            if connection_epoch is not None and connection_epoch!=entry.connection_epoch:
                raise BrokerError('fleet_connection_changed','The robot connection changed; select it again.',status=409)
            if action in {'drive','task','prepare','qualify','lidar','field_arm','field_test'} and motion_epoch is not None and motion_epoch!=entry.motion_epoch:
                raise BrokerError('fleet_motion_epoch_changed','The motion generation changed; press again.',status=409)
            if action in {'field_arm','field_test'} and motion_epoch is None:
                raise BrokerError('fleet_motion_epoch_changed','Current motion generation is required for field tests.',status=409)
            if action in {'prepare','qualify'}:
                if payload!={'confirmed':True}:raise BrokerError('physical_confirmation_required','Review the on-screen flat/clear floor and power-off conditions first.',status=409)
            if request_twin_context is not None:request_twin_context=checked_twin_context(request_twin_context,project_id=entry.project_id)
            if route_guard is not None:
                if not route_guard():raise BrokerError('physical_navigation_scene_changed','Twin route context expired before admission.',status=409)
                entry.services.live.navigation_guard=route_guard
            elif action in {'drive','task','stop','close'}:entry.services.live.navigation_guard=None
            result=entry.services.live.command(action,payload,motion_epoch=entry.motion_epoch,request_id=request_id or uuid4().hex,
                **({'admission_guard':admission_guard} if admission_guard is not None else {}),
                **({'request_twin_context':request_twin_context} if request_twin_context is not None else {}))
            if action in {'drive','task'}:entry.intent_kind='manual' if action=='drive' else 'task'
            # The live stream records every transmitted command/robot ACK. The
            # small lifecycle view records gesture transitions, not 10Hz repeats.
            signature=(action,payload.get('direction'))
            if action!='drive' or getattr(entry,'last_gesture',None)!=signature:
                self._event(entry,'command_requested',action=action,request_id=request_id,
                            parameters={k:v for k,v in payload.items() if k not in {'profile','challenge'}},
                            **({'request_twin_context':deepcopy(request_twin_context)} if request_twin_context is not None else {}))
            entry.last_gesture=signature
            return result

    def prepare_control(self,robot_id,owner,**values):
        self.motion_reviews.cancel_for_start()
        return self._live_command(robot_id,owner,'prepare',values.pop('payload',{'confirmed':True}),**values)

    def motion_review(self,operation_id,owner,project_id,body=None):
        identity=_uuid(operation_id,'operation ID');self._history_owner(owner,project_id)
        # Small authorization descriptor only. Full segments are verified by
        # the separate worker, not under an API/pool/Stop mutex.
        path=self.state_root/'physical-live'/identity/'events-00000.jsonl'
        if path.is_symlink() or not path.is_file():raise BrokerError('motion_review_missing','No original physical recording is available.',status=404)
        from .physical_live_history import MAX_LINE,_json
        with path.open('rb') as stream:line=stream.readline(MAX_LINE+1)
        if len(line)>MAX_LINE:raise BrokerError('motion_review_invalid','Recording header exceeds its bound.',status=409)
        try:first=_json(line)
        except ValueError:raise BrokerError('motion_review_invalid','Recording header is not valid.',status=409) from None
        if not isinstance(first,dict):raise BrokerError('motion_review_invalid','Recording header is not an object.',status=409)
        if first.get('operation_id')!=identity or first.get('project_id')!=project_id:raise BrokerError('motion_review_project','Recording belongs to another project.',status=403)
        if body is None:return self.motion_reviews.snapshot(identity,project_id)
        if not isinstance(body,dict) or body.get('action') not in {'start','cancel'}:raise BrokerError('motion_review_action','Use Start or Cancel review.',status=400)
        action=body['action'];fields={'action','request_id'}|({'job_id'} if action=='cancel' else set())
        if set(body)!=fields:raise BrokerError('motion_review_action','Unexpected review fields.',status=400)
        request=_uuid(body.get('request_id'),'request ID')
        if action=='cancel':return self.motion_reviews.cancel(identity,project_id,_uuid(body.get('job_id'),'review job ID'))
        receipt=path.parent/'receipt.json'
        # File is created only after local stream finalization, even when that
        # final receipt is incomplete. Never require complete/cleanup PASS.
        if not receipt.is_file() or receipt.is_symlink():raise BrokerError('motion_review_open','Disconnect and finalize the local recording first.',status=409)
        return self.motion_reviews.start(identity,project_id,request)

    def qualify(self,robot_id,owner,**values):
        return self._live_command(robot_id,owner,'qualify',values.pop('payload',{}),**values)

    def drive(self,robot_id,owner,*,action='drive',payload=None,**values):
        return self._live_command(robot_id,owner,action,payload or {},**values)

    def navigate(self,robot_id,owner,*,payload,guard,**values):
        return self._live_command(robot_id,owner,'task',payload,route_guard=guard,**values)

    def lidar(self,robot_id,owner,*,enabled,**values):
        if type(enabled) is not bool:raise BrokerError('fleet_shape','Expected sensor enabled boolean.',status=400)
        return self._live_command(robot_id,owner,'lidar',{'enabled':enabled},**values)

    def _load_profile(self,robot_id):
        path=self.state_root/'physical-fleet-profiles'/(_uuid(robot_id,'robot ID')+'.json')
        if not path.exists():return None
        if path.is_symlink() or path.stat().st_size>128*1024:raise BrokerError('physical_profile_invalid','Saved measured profile is invalid.',status=409)
        return json.loads(path.read_text(encoding='utf-8'))

    def profile_for_view(self,robot_id):
        try:return self._load_profile(robot_id)
        except (BrokerError,OSError,ValueError,RecursionError):return None

    def timing_for_view(self,robot_id):
        entry=self._cached(robot_id)
        if entry is None or entry.services.live is None:return dict(state='DISCONNECTED',profile_sha256=None,values=None,output_guard=None)
        with entry.lock:
            live=entry.services.live.snapshot()
            return dict(state='LAST_AUTHENTICATED_REPORT' if live.get('live_heartbeat') and not entry.disconnected else 'HISTORICAL_OR_DISCONNECTED',
                profile_sha256=live.get('timing_profile_sha256'),values=deepcopy(live.get('timing_values')),
                output_guard=deepcopy(live.get('output_timing')),operation_id=entry.operation_id,
                no_motion_authority=True)

    def field_config_for_view(self,robot_id):
        path=self.state_root/'physical-field-configs'/(_uuid(robot_id,'robot ID')+'.json')
        try:
            if path.is_symlink() or path.stat().st_size>8192:return None
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError,RecursionError):return None

    def save_field_config(self,robot_id,owner,config):
        _owner(owner);_,binding=self._row(robot_id)
        import importlib.util
        path=self.source_root/'packages/twinpulse_robot_safety/field_config.py'
        spec=importlib.util.spec_from_file_location('twinpulse_checked_field_config',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        try:checked=module.checked_config(config,robot_id=binding['instance_id'],binding_sha256=binding['sha256'])
        except (ValueError,TypeError,KeyError) as exc:
            raise BrokerError('physical_field_config_invalid',str(exc)[:160],status=400) from None
        from .release_contract import atomic_json
        target=self.state_root/'physical-field-configs'/(binding['instance_id']+'.json')
        version=target.parent/binding['instance_id']/(module.digest(checked)+'.json')
        if version.exists():
            if version.is_symlink() or json.loads(version.read_text(encoding='utf-8'))!=checked:
                raise BrokerError('physical_field_config_version','Saved field configuration changed.',status=409)
        else:atomic_json(version,checked)
        atomic_json(target,checked)
        entry=self._cached(robot_id)
        if entry is not None and not entry.disconnected:
            with entry.lock:
                self._claim(entry,owner);self._stop(entry,owner,'PROFILE_CHANGED')
                if entry.services.live is not None:entry.services.live.pending_field_setup=checked
        return dict(saved=True,config_sha256=module.digest(checked),motion_authority_restored=False)

    def field_action(self,robot_id,owner,action,payload,**values):
        if action not in {'field_arm','field_test','field_review'}:
            raise BrokerError('physical_field_action','Unknown field test action.',status=400)
        if action in {'field_arm','field_test'} and payload.get('confirmed') is not True:
            raise BrokerError('physical_field_confirmation','Review current supervised conditions first.',status=400)
        return self._live_command(robot_id,owner,action,payload,**values)

    def save_profile(self,robot_id,owner,profile):
        _owner(owner)
        _,binding=self._row(robot_id)
        # Pure validator has no ROS/device imports; reuse the robot-side contract.
        import importlib.util
        path=self.source_root/'packages/twinpulse_robot_safety/physical_profile.py'
        spec=importlib.util.spec_from_file_location('twinpulse_checked_physical_profile',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        try:checked=module.checked_profile(profile,robot_id=binding['instance_id'],binding_sha256=binding['sha256'])
        except (ValueError,TypeError,KeyError) as error:
            raise BrokerError('physical_profile_invalid',str(error)[:160],status=400) from None
        from .release_contract import atomic_json
        target=self.state_root/'physical-fleet-profiles'/(binding['instance_id']+'.json')
        digest=hashlib.sha256(json.dumps(checked,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        version=target.parent/binding['instance_id']/(digest+'.json')
        def persist():
            version.parent.mkdir(parents=True,exist_ok=True)
            if version.exists():
                if version.is_symlink() or json.loads(version.read_text(encoding='utf-8'))!=checked:
                    raise BrokerError('physical_profile_version_changed','An immutable measured profile version changed.',status=409)
            else:
                with version.open('x',encoding='utf-8') as stream:
                    json.dump(checked,stream,sort_keys=True,allow_nan=False);stream.flush();os.fsync(stream.fileno())
            atomic_json(target,checked)
        entry=self._cached(robot_id)
        if entry is not None and not entry.disconnected:
            with entry.lock:
                self._claim(entry,owner)
                self._stop(entry,owner,'PROFILE_CHANGED')
                persist()
                if entry.services.live is not None:
                    entry.services.live.pending_profile=checked
                self._event(entry,'profile_saved',sha256=hashlib.sha256(json.dumps(checked,sort_keys=True).encode()).hexdigest())
        else:persist()
        return {'saved':True,'motion_authority_restored':False}

    def _snapshot(self, entry, owner):
        if entry.services.live is not None:
            live=entry.services.live.snapshot()
            if isinstance(live.get('pc_motion_epoch'),str) and live['pc_motion_epoch']!=entry.motion_epoch:
                entry.motion_epoch=live['pc_motion_epoch'];entry.last_gesture=None;entry.intent_kind=None
            reported_control=live.get('control_state','UNPREPARED')
            control={'ACTIVE':'DRIVING','PREPARING':'ARMING','QUALIFYING':'ARMING',
                'ARMED_AWAITING_FRESH_INPUT':'READY','CLOSED':'UNPREPARED'}.get(reported_control,reported_control)
            # Native board reads report voltage, not a measured capacity percent.
            # Preserve the public fleet shape even when a worker omits optional data.
            battery=dict(voltage_v=None,percent=None,source='unknown',age_ms=None)
            if isinstance(live.get('battery'),dict):battery.update(live['battery'])
            battery=dict(battery,age_ms=None if battery.get('age_ms') is None else
                         battery['age_ms']+(live.get('telemetry_age_ms') or 0))
            if entry.binding['adapter_id']=='turtlebot3_burger_v1' and battery.get('source')=='measured':
                # Keep the measured-percent field nullable. The explicit voltage
                # estimate never grants motion or refreshes its sample age.
                battery.update(battery_estimate(battery.get('voltage_v')))
                battery['reserve_reference_method']='robotis_opencr_voltage_10_5_to_12_3_v1'
                config=self.registry.battery_display_for_view(entry.binding['instance_id'],entry.binding['sha256'])
                battery.update(battery_display_estimate(battery.get('voltage_v'),config or battery_display_config()))
                battery['display_settings_state']='LOADED' if config is not None else 'AWAITING_SETTINGS_VIEW'
            setup=live.get('setup') or dict(runtime_state='STARTING' if not live.get('live_heartbeat') else 'CONNECTED',blockers=live.get('blockers',[]),
                                          profile=live.get('profile'),qualification=live.get('qualification'))
            setup['binding_sha256']=entry.binding['sha256']
            setup['maintenance_phase']=live.get('maintenance_phase')
            setup['output_guard_build']=deepcopy(live.get('output_guard_build'))
            ended=entry.disconnected or entry.services.live.closed
            local_recording=live.get('recording') or {};robot_recording=live.get('robot_recording') or {}
            recording_error=local_recording.get('error') or robot_recording.get('error')
            setup['recording']=dict(pc=local_recording,robot=robot_recording)
            return dict(robot_id=entry.binding['instance_id'],label=entry.label,kind='physical',
                connection_epoch=None if ended else entry.connection_epoch,motion_epoch=None if ended else entry.motion_epoch,
                applied_motion_epoch=live.get('applied_motion_epoch'),
                connection_state='DISCONNECTED' if ended else 'DEGRADED' if entry.disconnecting else live['connection_state'],
                observation_state='LIVE_AUTHENTICATED_SESSION' if live.get('live_heartbeat') else 'STALE_OR_UNVERIFIED',
                live_heartbeat=live.get('live_heartbeat',False) and not ended,
                control_state=control,controller_state=reported_control,
                reason='DISCONNECTING_AWAITING_ROBOT_CLEANUP' if entry.disconnecting else live.get('transport_error') or live.get('reason') or entry.reason or live.get('link_detail'),
                link_detail=live.get('link_detail'),remote_stderr_tail=live.get('remote_stderr_tail'),
                recording_failure_reason=live.get('recording_failure_reason'),control_owner_state=None if ended else live.get('control_owner_state'),
                last_reported_lidar_state=live.get('last_reported_lidar_state'),lidar_state_source='pc_after_exit' if ended else live.get('lidar_state_source','robot'),
                robot_storage=deepcopy(live.get('robot_storage')),
                battery=battery,pose=live.get('pose'),field=live.get('field'),command=deepcopy(live.get('command')),scan=None if ended else live.get('scan'),sensor_frame=live.get('sensor_frame'),
                scan_receipt=None if ended else deepcopy(live.get('scan_receipt')),
                task_local_observation=None if ended else deepcopy(live.get('task_local_observation')),
                task_local_state=deepcopy(live.get('task_local_state')),task_observation_age_ms=live.get('task_observation_age_ms'),
                stop_receipt=deepcopy(live.get('stop_receipt')),device_boot_id=live.get('boot_id'),device_release_id=live.get('release_id'),
                lidar_state=('OFF' if live.get('cleanup_confirmed') else 'FAULT') if ended else live.get('lidar_state','OFF'),
                telemetry_diagnostic=deepcopy(live.get('telemetry_diagnostic')),native_diagnostic=deepcopy(live.get('lidar')),
                motion_observation=deepcopy(live.get('motion_observation')),
                timing_policy=deepcopy(live.get('timing_policy')),odom_interval=deepcopy(live.get('odom_interval')),field_evidence=deepcopy(live.get('field_evidence')),
                timing_values=deepcopy(live.get('timing_values')),timing_profile_sha256=live.get('timing_profile_sha256'),
                output_timing=deepcopy(live.get('output_timing')),
                recording_state='INCOMPLETE' if recording_error else 'BUFFERING' if robot_recording.get('buffering') else
                    'RECORDING' if not ended else 'COMPLETE' if live.get('cleanup_confirmed') and local_recording.get('complete') else 'INCOMPLETE',
                operation_id=None if ended else entry.operation_id,last_operation_id=entry.operation_id,project_id=entry.project_id,setup=setup,
                source_twin_context=deepcopy(entry.source_twin_context),
                cleanup_confirmed=live.get('cleanup_confirmed',False),
                telemetry_age_ms=live.get('telemetry_age_ms'),telemetry_sequence=live.get('telemetry_sequence',0),
                pose_age_ms=live.get('pose_age_ms'),
                capabilities=dict(read_only_connection=True,prepare=True,qualify=True,profile=True,
                    lidar=live.get('live_heartbeat',False) and not ended,drive=not ended and live.get('drive_ready') is True and live.get('live_heartbeat',False)
                    and not recording_error),
                owned=bool(owner and entry.owner==owner),physical_motion_verified=False)
        diagnostics = entry.services.diagnostics.snapshot(owner)
        job = diagnostics.get('job') or {}
        binding = job.get('robot_binding') or {}
        same = binding.get('sha256') == entry.binding['sha256']
        observed = same and job.get('status') == 'COMPLETED' and job.get('authentication_verified') is True
        record = diagnostics.get('record') or {}
        age = record.get('age_seconds')
        fresh = observed and type(age) in (int, float) and math.isfinite(age) and 0 <= age <= 120
        controller = entry.services.controller.snapshot(owner) if entry.services.controller else {}
        journal = entry.journal.status() if entry.journal is not None else None
        disconnected = entry.disconnected
        return dict(robot_id=entry.binding['instance_id'], label=entry.label, kind='physical',
            connection_epoch=entry.connection_epoch, motion_epoch=entry.motion_epoch,
            connection_state='DISCONNECTED' if disconnected else 'CONNECTING' if same and job.get('status') == 'RUNNING' else 'DEGRADED',
            observation_state='VERIFIED_SNAPSHOT' if fresh and not disconnected else 'STALE_OR_UNVERIFIED',
            live_heartbeat=False,
            control_state='FAULT' if entry.cleanup_uncertain else 'PAUSED' if entry.reason and not disconnected else 'UNPREPARED',
            reason=entry.reason or 'READ_ONLY_OBSERVATION_NOT_LIVE_CONNECTION',
            battery={'voltage_v': None, 'percent': None, 'source': 'unknown', 'age_ms': None},
            last_observation=deepcopy(record) if observed else None,
            pose=None, scan=None, lidar_state='OFF',
            recording_state='INCOMPLETE' if entry.dropped_events or entry.footer_error or journal and journal['error']
                            else 'COMPLETE' if entry.footer_written and disconnected
                            else 'INCOMPLETE' if disconnected and entry.journal
                            else 'RECORDING' if entry.journal else 'IDLE',
            operation_id=entry.operation_id, project_id=entry.project_id,source_twin_context=deepcopy(entry.source_twin_context),
            diagnostic_job_id=job.get('id') if same else None,
            controller_job_id=controller.get('job_id'), controller_state=controller.get('state'),
            telemetry_age_ms=age * 1000 if fresh else None, telemetry_sequence=0,
            owned=bool(owner and entry.owner == owner),
            capabilities={'read_only_connection': not (entry.disconnecting or entry.cleanup_uncertain or self.closed or getattr(self.devices, 'closed', False)), 'drive': False, 'lidar': False},
            blockers=['PHYSICAL_NATIVE_LIDAR_FOOTPRINT_TF_UNQUALIFIED',
                      'PHYSICAL_NONUNIFORM_NATIVE_SCAN_ADAPTER_NOT_INTEGRATED',
                      'PHYSICAL_WHEEL_STALL_GUARD_NOT_INTEGRATED', 'PHYSICAL_BODY_PROGRESS_UNVERIFIED',
                      'PHYSICAL_STOP_QUALIFICATION_SAME_BOOT_RELEASE_REQUIRED'],
            identity_assurance='SSH_KNOWN_HOST_ONLY_PHYSICAL_ALIAS_IDENTITY_UNVERIFIED')

    def snapshot(self, owner=None):
        with self.lock:
            entries = list(self.sessions.values())
        values = []
        for entry in entries:
            with entry.lock:
                values.append(self._snapshot(entry, owner))
        return {'schema_version': 'physical-fleet-adapter-1.0', 'robots': values,
                'focused_robot_id': self.focused.get(owner), 'physical_motion_verified': False}

    def assert_legacy_available(self, binding=None):
        """Call under devices.lock from legacy start/scene admission.

        None conservatively checks every robot for document edits. A known
        immutable binding checks only that endpoint for a legacy robot action.
        This is the reciprocal half of _admission; without integrating it,
        legacy and pooled transports must not be exposed concurrently.
        """
        with self.lock:
            entries = list(self.sessions.values())
        for entry in entries:
            if binding is not None and _endpoint(binding) != _endpoint(entry.binding):
                continue
            with entry.lock:
                if entry.disconnected:
                    continue
                services = entry.services
                live=services.live.snapshot() if services.live is not None else {}
                if binding is None and services.live is not None and services.live.closed:
                    continue # Old unknown cleanup is evidence, not a SIM document lock.
                if (entry.disconnecting or entry.cleanup_uncertain or services.diagnostics._running()
                        or live.get('control_state') in {'ACTIVE','DRIVING','PREPARING','QUALIFYING','ARMING','ARMED_AWAITING_FRESH_INPUT'}
                        or services.controller is not None and services.controller.snapshot(None).get('busy')
                        or services.readiness is not None and services.readiness.local_operation_active()):
                    raise BrokerError('physical_fleet_busy', 'A pooled physical operation still owns this robot or its scene.', status=409)

    def operation(self, operation_id, owner, *, project_id=None):
        identity = _uuid(operation_id, 'operation ID')
        _owner(owner)
        with self.lock:
            entry = self.operations.get(identity)
        if entry is None:
            return self._cold_operation(identity, owner, project_id)
        with entry.lock:
            if project_id is not None and project_id != entry.project_id:
                raise BrokerError('physical_fleet_operation_project', 'Operation belongs to another project.', status=403)
            self._claim(entry, owner)
            status = entry.journal.status() if entry.journal else None
            return dict(schema_version='robot-operation-1.0', operation_id=identity,
                robot_id=entry.binding['instance_id'], project_id=entry.project_id,
                events=deepcopy(entry.events)+(deepcopy(entry.services.live.events) if entry.services.live else []),
                manifest=dict(source='physical_existing_controller_and_read_only_diagnostics',
                    source_twin_context=deepcopy(entry.source_twin_context),
                    lineage_status='RECORDED_OPERATION_START_REFERENCE_NOT_ACQUISITION_SYNC' if entry.source_twin_context is not None else 'LEGACY_UNKNOWN',
                    binding_sha256=entry.binding['sha256'], storage=status, dropped_events=entry.dropped_events,
                    complete=entry.disconnected and not entry.dropped_events and status is not None
                             and status['error'] is None and status['saved'] == status['accepted']
                             and entry.footer_written and entry.footer_error is None
                             and (entry.services.live is None or entry.services.live.evidence is not None
                                  and entry.services.live.evidence.snapshot()['complete'] and entry.services.live.error is None),
                    physical_motion_verified=False, original_logs_rewritten=False,
                    footer_written=entry.footer_written, footer_error=entry.footer_error,
                    persistent_manifest='physical-fleet-operations/' + identity + '.jsonl',
                    stream=entry.services.live.evidence.snapshot() if entry.services.live and entry.services.live.evidence else None,
                    local_receipt='physical-live/'+identity+'/receipt.json' if entry.services.live else None,
                    worker_sources=deepcopy(getattr(entry.services.live,'sources',{})),
                    cleanup_confirmed=entry.services.live.cleanup_confirmed if entry.services.live else False))

    def evidence_file(self,operation_id,name,owner,project_id):
        # Authorize with the same current project session as operation history.
        operation=self.operation(operation_id,owner,project_id=project_id)
        if name not in {'receipt.json','ssh-stderr.log'} and not re.fullmatch(r'events-\d{5}\.jsonl',name):
            raise BrokerError('physical_evidence_name','Unknown evidence member.',status=400)
        path=self.state_root/'physical-live'/_uuid(operation_id,'operation ID')/name
        if path.is_symlink() or not path.is_file():raise BrokerError('physical_evidence_missing','Evidence member is not available.',status=404)
        if path.stat().st_size>5*1024*1024:raise BrokerError('physical_evidence_limit','Evidence member exceeds its bounded limit.',status=409)
        return path.read_bytes()

    def _history_owner(self, owner, project_id):
        """Existing product-session authentication, not a caller-supplied flag.

        Logs intentionally contain no session cookie/owner token. Cold history
        access is for a CURRENT authenticated session of the same project, not
        proof of the former operator's identity and never a control takeover.
        """
        if not isinstance(project_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', project_id):
            raise BrokerError('physical_fleet_history_auth_required', 'Current authenticated project context is required for saved history.', status=403)
        for context in getattr(self.devices, 'contexts', []):
            if getattr(getattr(context, 'broker', None), 'project_id', None) != project_id:
                continue
            authenticate = getattr(context, '_session', None)
            if not callable(authenticate):
                continue
            try:
                session = authenticate(owner, 'product')
            except BrokerError:
                continue
            if getattr(session, 'session_id', None) == owner and getattr(session, 'role', None) == 'product':
                return
        raise BrokerError('physical_fleet_history_auth_required', 'A current product session for this project could not be verified.', status=403)

    def _cold_operation(self, identity, owner, project_id):
        self._history_owner(owner, project_id)
        directory = self.state_root / 'physical-fleet-operations'
        path = directory / (identity + '.jsonl')
        if not path.is_file():
            raise BrokerError('physical_fleet_operation_missing', 'Saved physical operation not found.', status=404)
        if path.resolve().parent != directory.resolve():
            raise BrokerError('physical_fleet_history_path', 'Saved operation is outside its evidence directory.', status=409)
        try:
            with path.open('rb') as stream:
                payload = stream.read(1024 * 1024 + 4097)
        except OSError:
            raise BrokerError('physical_fleet_history_unreadable', 'Saved operation could not be read; recording is incomplete.', status=409) from None
        if len(payload) > 1024 * 1024 + 4096:
            raise BrokerError('physical_fleet_history_capacity', 'Saved operation exceeds the bounded reader.', status=409)
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError('DUPLICATE_FIELD')
                value[key] = item
            return value
        def parse(line):
            return json.loads(line.decode('utf-8'), object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE')))
        lines = payload.splitlines(keepends=True)
        try:
            if len(lines[0]) > 16384:
                raise ValueError('HEADER_TOO_LARGE')
            first = parse(lines[0])
            if (type(first) is not dict or first.get('schema_version') != 'physical-fleet-event-1.0'
                    or first.get('operation_id') != identity or first.get('kind') != 'operation_started'
                    or first.get('sequence') != 1 or first.get('project_id') != project_id):
                raise ValueError('FIRST_EVENT_BINDING')
            robot_id = _uuid(first.get('robot_id'), 'saved robot ID')
            connection_epoch = _uuid(first.get('connection_epoch'), 'saved connection epoch')
            _, binding = self._row(robot_id)  # Metadata only; never _entry()/factory.
            if type(first.get('data')) is not dict or first['data'].get('binding_sha256') != binding['sha256']:
                raise ValueError('CURRENT_ROBOT_BINDING_DIFFERS')
            source_twin_context=first['data'].get('source_twin_context')
            if source_twin_context is not None:source_twin_context=checked_twin_context(source_twin_context,project_id=project_id)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError, BrokerError):
            raise BrokerError('physical_fleet_history_binding_unverified', 'Saved project/robot binding cannot be verified against the current registry.', status=409) from None
        fields = {'schema_version', 'operation_id', 'robot_id', 'project_id', 'connection_epoch',
                  'motion_epoch', 'sequence', 'kind', 'utc', 'monotonic_s', 'data'}
        data_fields = {
            'operation_started': {'binding_sha256', 'adapter_id', 'adapter_version'},
            'read_only_connection_requested': {'request_id'},
            'read_only_job_bound': {'job_id', 'execution_id'},
            'connection_rejected': {'reason'}, 'connection_failed': {'error_type'},
            'stop_requested': {'reason', 'controller_job_id', 'controller_mode'},
            'disconnect_requested': {'reason', 'controller_job_id', 'controller_mode'},
            'focus_released': {'manual_stop_required'}, 'stop_delivery_error': {'error_type'},
            'services_closed': {'cleanup_errors'}}
        data_fields.update(persistent_connection_requested={'request_id'},persistent_worker_started={'profile_available'},
            command_requested={'action','request_id','parameters'},profile_saved={'sha256'})
        def data_valid(kind, data):
            def text(value, pattern):
                return isinstance(value, str) and re.fullmatch(pattern, value) is not None
            if 'source_twin_context' in data:
                if kind!='operation_started' or checked_twin_context(data['source_twin_context'],project_id=project_id)!=source_twin_context:return False
            if 'request_twin_context' in data:
                checked_twin_context(data['request_twin_context'],project_id=None if kind in {'stop_requested','disconnect_requested'} else project_id)
                if data.get('request_id') is not None and not text(data['request_id'],'[a-f0-9-]{32,36}'):return False
            if kind == 'operation_started':
                return all(data[key] == binding[key] for key in ('adapter_id', 'adapter_version')) and data['binding_sha256'] == binding['sha256']
            if kind in {'read_only_connection_requested','persistent_connection_requested'}:
                return text(data['request_id'], '[a-f0-9]{32}')
            if kind=='persistent_worker_started':return type(data['profile_available']) is bool
            if kind=='profile_saved':return text(data['sha256'],'[a-f0-9]{64}')
            if kind=='command_requested':
                return (data['action'] in {'prepare','qualify','drive','task','lidar','profile','field_setup','field_arm','field_test','field_review'}
                    and (data['request_id'] is None or text(data['request_id'],'[a-f0-9-]{32,36}'))
                    and type(data['parameters']) is dict and len(json.dumps(data['parameters'],allow_nan=False))<=4096)
            if kind == 'read_only_job_bound':
                return all(data[key] is None or text(data[key], '[a-f0-9]{24,32}') for key in ('job_id', 'execution_id'))
            if kind in {'stop_requested', 'disconnect_requested'}:
                return (data['reason'] in {'OPERATOR_STOP', 'FOCUS_CHANGED', 'EXPLICIT_DISCONNECT', 'WORKSPACE_SHUTDOWN','PROFILE_CHANGED'}
                        and (data.get('controller_job_id') is None or text(data['controller_job_id'], '[a-f0-9]{24,32}'))
                        and (data.get('controller_mode') is None or text(data['controller_mode'], '[a-z_]{1,32}')))
            if kind == 'focus_released':
                return type(data['manual_stop_required']) is bool
            if kind == 'services_closed':
                return type(data['cleanup_errors']) is list and len(data['cleanup_errors']) <= 4 and all(text(error, '[A-Za-z_][A-Za-z0-9_]{0,99}') for error in data['cleanup_errors'])
            key = 'reason' if kind == 'connection_rejected' else 'error_type'
            return text(data[key], '[A-Za-z_][A-Za-z0-9_]{0,99}')
        events, missing, footer = [], [], None
        for index, line in enumerate(lines):
            if len(line) > 16384:
                missing.append('JOURNAL_READ_BUDGET'); break
            try:
                event = parse(line)
                if not line.endswith(b'\n'):
                    missing.append('INCOMPLETE_JOURNAL_LINE')
                if type(event) is not dict:
                    raise ValueError('EVENT_SHAPE')
                if event.get('schema_version') == 'physical-fleet-footer-1.0':
                    footer = event
                    expected = {'schema_version', 'operation_id', 'project_id', 'robot_id', 'connection_epoch',
                                'event_count', 'events_sha256', 'complete', 'dropped_events'}
                    prefix = b''.join(lines[:index])
                    if (set(footer) != expected or footer['operation_id'] != identity
                            or footer['project_id'] != project_id or footer['robot_id'] != robot_id
                            or footer['connection_epoch'] != connection_epoch
                            or type(footer['event_count']) is not int or footer['event_count'] != len(events)
                            or footer['events_sha256'] != hashlib.sha256(prefix).hexdigest()
                            or type(footer['complete']) is not bool
                            or type(footer['dropped_events']) is not int or footer['dropped_events'] < 0):
                        missing.append('FOOTER_INTEGRITY_MISMATCH')
                    if index != len(lines)-1:
                        missing.append('DATA_AFTER_FOOTER')
                    break
                if (len(events) >= 256 or set(event) != fields or event['schema_version'] != 'physical-fleet-event-1.0'
                        or event['operation_id'] != identity or event['robot_id'] != robot_id
                        or event['project_id'] != project_id or event['connection_epoch'] != connection_epoch
                        or type(event['sequence']) is not int or event['sequence'] != len(events)+1
                        or not isinstance(event['motion_epoch'], str) or not re.fullmatch('[a-f0-9]{32}', event['motion_epoch'])
                        or not isinstance(event['kind'], str) or event['kind'] not in data_fields
                        or type(event['data']) is not dict or (set(event['data'])-({'source_twin_context'} if event['kind']=='operation_started'
                            else {'request_twin_context'} if event['kind']=='command_requested'
                            else {'request_id','request_twin_context'} if event['kind'] in {'stop_requested','disconnect_requested'} else set()) != data_fields[event['kind']]
                            and not (event['kind'] in {'stop_requested','disconnect_requested'} and set(event['data'])-{'request_id','request_twin_context'}=={'reason'}))
                        or not data_valid(event['kind'], event['data'])
                        or not isinstance(event['utc'], str) or len(event['utc']) > 80
                        or type(event['monotonic_s']) not in (int, float) or not math.isfinite(event['monotonic_s'])
                        or event['monotonic_s'] < 0):
                    raise ValueError('EVENT_BINDING_SEQUENCE_OR_SHAPE')
                events.append(event)
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                missing.append('JOURNAL_CORRUPT_OR_SEQUENCE_GAP'); break
        if footer is None:
            missing.append('FINAL_RECORDING_RECEIPT_ABSENT')
        elif footer.get('complete') is not True or footer.get('dropped_events') != 0:
            missing.append('RECORDING_OR_CLEANUP_INCOMPLETE')
        if not events or events[-1]['kind'] != 'services_closed' or events[-1]['data'].get('cleanup_errors') != []:
            missing.append('CLEANUP_RECEIPT_ABSENT_OR_FAILED')
        stream=None
        receipt_path=self.state_root/'physical-live'/identity/'receipt.json'
        if receipt_path.is_file() and not receipt_path.is_symlink() and receipt_path.stat().st_size<=128*1024:
            try:
                stream=json.loads(receipt_path.read_text(encoding='utf-8'))
                if stream.get('schema')!='physical-live-recording-1.0' or not isinstance(stream.get('segments'),list) or len(stream['segments'])>EVENT_ARCHIVE_SEGMENTS:
                    raise ValueError('STREAM_RECEIPT_SHAPE')
                for segment in stream['segments']:
                    name=segment.get('path')
                    if not isinstance(name,str) or not re.fullmatch(r'events-\d{5}\.jsonl',name):raise ValueError('STREAM_MEMBER_PATH')
                    member=receipt_path.parent/name
                    if member.is_symlink() or member.stat().st_size!=segment['bytes'] or member.stat().st_size>4*1024*1024:
                        raise ValueError('STREAM_MEMBER_SIZE')
                    if hashlib.sha256(member.read_bytes()).hexdigest()!=segment['sha256']:raise ValueError('STREAM_MEMBER_SHA')
                if stream.get('complete') is not True:missing.append('LIVE_STREAM_INCOMPLETE')
            except (OSError,ValueError,TypeError,KeyError):
                missing.append('LIVE_STREAM_RECEIPT_UNVERIFIED');stream=None
        elif any(e['kind']=='persistent_worker_started' for e in events):missing.append('LIVE_STREAM_RECEIPT_ABSENT')
        recovered={}
        if stream is not None:
            try:
                from .physical_live_history import recover_live_history
                recovered=recover_live_history(receipt_path.parent,stream,operation_id=identity,project_id=project_id,
                    robot_id=robot_id,connection_epoch=connection_epoch,binding_sha256=binding['sha256'],source_twin_context=source_twin_context)
            except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):missing.append('LIVE_STREAM_HISTORY_UNVERIFIED')
        return dict(schema_version='robot-operation-1.0', operation_id=identity, robot_id=robot_id,
            project_id=project_id, events=events+recovered.get('events',[]),
            manifest=dict(source='physical_existing_controller_and_read_only_diagnostics',
                source_twin_context=deepcopy(source_twin_context),
                lineage_status='RECORDED_OPERATION_START_REFERENCE_NOT_ACQUISITION_SYNC' if source_twin_context is not None else 'LEGACY_UNKNOWN',
                binding_sha256=binding['sha256'], complete=not missing,
                completeness='RECOVERED_INCOMPLETE' if missing else 'VERIFIED_CLOSED_RECORDING',
                missing=missing, event_count=len(events)+len(recovered.get('events',[])),lifecycle_event_count=len(events), journal_sha256=hashlib.sha256(payload).hexdigest(),
                authorization_basis='CURRENT_AUTHENTICATED_PROJECT_SESSION', historical_operator_identity_verified=False,
                integrity_basis='LOCAL_SHA256_COUNT_RECEIPT_NOT_AUTHENTICATED_DEVICE_PROOF',
                current_robot_binding_matches=True, physical_motion_verified=False, historical=True,
                worker_sources=recovered.get('worker_sources'),worker_sources_provenance=recovered.get('worker_sources_provenance','NOT_RECORDED'),
                cleanup_confirmed=recovered.get('cleanup_confirmed'),source_export=recovered.get('source_export'),
                runtime_event_count=recovered.get('runtime_event_count'),
                field_trial_resolution=recovered.get('field_trial_resolution'),
                connection_restored=False, device_authority_restored=False, original_logs_rewritten=False,
                persistent_manifest='physical-fleet-operations/' + identity + '.jsonl',stream=stream,
                local_receipt='physical-live/'+identity+'/receipt.json' if stream else None))

    def disconnect(self, robot_id, owner, *, request_id=None, request_twin_context=None):
        _owner(owner)
        entry = self._cached(robot_id)
        if entry is None:
            return
        with entry.lock:
            self._claim(entry, owner)
            if entry.disconnecting or entry.disconnected:
                return
            try:
                self._stop(entry, owner, 'EXPLICIT_DISCONNECT', close=True,request_id=request_id,request_twin_context=request_twin_context)
            except Exception as error:
                self._event(entry, 'stop_delivery_error', error_type=type(error).__name__)
            entry.disconnecting = True
            if entry.services.live is not None:
                entry.close_thread=Thread(target=self._finish_close,args=(entry,),daemon=True,name='physical-disconnect-cleanup')
                entry.close_thread.start()
                return # HTTP reports STOPPING; subsequent GET reports actual receipt.
        self._finish_close(entry)

    def _finish_close(self, entry):
        errors = []
        for service in (entry.services.live, entry.services.controller, entry.services.diagnostics, entry.services.readiness):
            if service is not None:
                try:
                    service.close()
                except Exception as error:
                    errors.append(type(error).__name__)
        try:
            services = entry.services
            if (services.controller is not None and services.controller.snapshot(entry.owner).get('busy')
                    or services.diagnostics._running()
                    or services.readiness is not None and services.readiness.local_operation_active()):
                errors.append('SERVICE_STILL_ACTIVE')
        except Exception as error:
            errors.append(type(error).__name__)
        if entry.services.live is not None and not entry.services.live.cleanup_confirmed:
            errors.append('REMOTE_CLEANUP_UNCONFIRMED')
        with entry.lock:
            entry.disconnected, entry.disconnecting = not errors, False
            entry.cleanup_uncertain = bool(errors)
            if errors:
                entry.reason = 'LOCAL_SERVICE_CLEANUP_UNCONFIRMED'
            self._event(entry, 'services_closed', cleanup_errors=errors)
        if entry.journal is not None:
            drained = entry.journal.close()
            if drained and not entry.footer_written and entry.footer_error is None:
                # The async writer has stopped. Append a bounded hash/count
                # receipt; never rewrite original events or retain owner tokens.
                try:
                    path = entry.journal.path
                    with path.open('rb') as stream:
                        payload = stream.read(1024 * 1024 + 1)
                    if len(payload) > 1024 * 1024:
                        raise ValueError('JOURNAL_BYTE_BUDGET')
                    status = entry.journal.status()
                    footer = dict(schema_version='physical-fleet-footer-1.0', operation_id=entry.operation_id,
                        project_id=entry.project_id, robot_id=entry.binding['instance_id'],
                        connection_epoch=entry.connection_epoch, event_count=status['saved'],
                        events_sha256=hashlib.sha256(payload).hexdigest(),
                        complete=entry.disconnected and not entry.dropped_events
                            and (entry.services.live is None or entry.services.live.evidence is not None
                                and entry.services.live.evidence.snapshot()['complete'] and entry.services.live.error is None),
                        dropped_events=entry.dropped_events)
                    line = (json.dumps(footer, allow_nan=False, separators=(',', ':'))+'\n').encode('utf-8')
                    with path.open('ab') as stream:
                        if stream.write(line) != len(line):
                            raise OSError('SHORT_FOOTER_WRITE')
                        stream.flush()
                        os.fsync(stream.fileno())
                    entry.footer_written = True
                except (OSError, ValueError):
                    entry.footer_error = 'FINAL_RECORDING_RECEIPT_WRITE_FAILED'

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            entries = [entry for entry in self.sessions.values() if not entry.disconnected]
        # Request every owned stop before joining any one device's cleanup.
        for entry in entries:
            with entry.lock:
                if entry.owner is not None:
                    try:
                        self._stop(entry, entry.owner, 'WORKSPACE_SHUTDOWN', close=True)
                    except Exception as error:
                        self._event(entry, 'stop_delivery_error', error_type=type(error).__name__)
                entry.disconnecting = True
        errors=[]
        for entry in entries:
            try:
                thread=getattr(entry,'close_thread',None)
                if thread is not None:
                    thread.join(timeout=36)
                else:self._finish_close(entry)
            except Exception as error:errors.append(error)
        # Stops have already been requested and joined independently. Offline
        # comparison cannot prevent any of the physical Stop attempts above.
        try:
            if not self.motion_reviews.close()['closed']:raise RuntimeError('Offline review cleanup unconfirmed')
        except Exception as error:errors.append(error)
        if errors:raise ExceptionGroup('Physical owners cleanup failed',errors)
