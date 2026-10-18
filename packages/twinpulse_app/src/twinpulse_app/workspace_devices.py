# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One device owner per workspace; historical records do not own SIM documents."""
from threading import RLock
from pathlib import Path
import os

from .command_broker import BrokerError


class WorkspaceDevices:
    def __init__(self, *, diagnostics=None, readiness=None, controller=None, owner_lease=None,
                 unavailable_reason=None, registry_state_root=None, source_root=None):
        self.diagnostics = diagnostics
        self.readiness = readiness
        self.controller = controller
        self.lock = RLock()
        self.contexts = []
        self.closed = False
        self.owner_lease = owner_lease
        self.unavailable_reason = unavailable_reason
        self.registry_service=None
        self.physical_fleet=None
        if registry_state_root is not None:
            from .robot_registry_service import RobotRegistryService
            self.registry_service=RobotRegistryService(self,registry_state_root,source_root=source_root)
            if source_root is not None and self.diagnostics is not None:
                from .physical_fleet_adapter import PhysicalFleetAdapter
                self.physical_fleet=PhysicalFleetAdapter(self,source_root,registry_state_root)

    @classmethod
    def from_paths(cls, source_root, state_root, *, physical_enabled=True, observation_enabled=False):
        data_root = Path(state_root) / 'devices' / 'local'
        if not physical_enabled:
            if observation_enabled:
                # A separately declared build may observe a selected robot,
                # without enabling preparation/deployment/collection/motion.
                from .device_storage import DeviceOwnerLease
                from .robot_diagnostics import RobotDiagnostics
                lease=None
                try:
                    owner_root=Path(os.environ.get('LOCALAPPDATA',state_root))/'TwinPulse'
                    lease=DeviceOwnerLease(owner_root/'local-device-owner.lock')
                    return cls(diagnostics=RobotDiagnostics(source_root,archive_root=data_root),
                        owner_lease=lease,registry_state_root=data_root,source_root=source_root,
                        unavailable_reason='ROBOT_OBSERVATION_ONLY')
                except (OSError,ValueError):
                    if lease is not None:lease.close()
                    return cls(registry_state_root=data_root,source_root=source_root,
                        unavailable_reason='ROBOT_OBSERVATION_OWNER_UNAVAILABLE')
            # SIM packages still expose saved metadata and the registration
            # guide. Do not instantiate, migrate or lease physical services.
            return cls(registry_state_root=data_root, source_root=source_root, unavailable_reason='SIM_ONLY_RELEASE')
        from .device_storage import DeviceOwnerLease, migrate_device_records
        from .robot_diagnostics import RobotDiagnostics
        from .robot_readiness import RobotReadiness
        from .physical_controller import PhysicalController
        lease = None
        try:
            owner_root = Path(os.environ.get('LOCALAPPDATA', state_root)) / 'TwinPulse'
            lease = DeviceOwnerLease(owner_root / 'local-device-owner.lock')
            migrate_device_records(source_root, data_root)
            return cls(diagnostics=RobotDiagnostics(source_root, archive_root=data_root),
                       readiness=RobotReadiness(source_root, archive_root=data_root),
                       controller=PhysicalController(source_root, archive_root=data_root),
                       owner_lease=lease,registry_state_root=data_root,source_root=source_root)
        except (OSError, ValueError):
            if lease is not None:
                lease.close()
            # Device storage/ownership never locks an unrelated conversation.
            return cls(unavailable_reason='DEVICE_STORAGE_OR_OWNER_UNAVAILABLE')

    def attach(self, context):
        self.contexts.append(context)

    def robot_registry_api(self,body,owner):
        if self.registry_service is None:
            raise BrokerError('robot_registry_unavailable','Local robot registry storage is unavailable.',status=409)
        return self.registry_service.request(body,owner)

    def assert_document_available(self):
        """Only live local work can hold the shared scene; no remote action here."""
        if self.physical_fleet is not None:self.physical_fleet.assert_legacy_available()
        for context in self.contexts:
            navigation = getattr(context.conversation, 'navigation', None)
            task = getattr(navigation, 'task_loop', None)
            if (context.chat_robot_preparation._busy()
                    or context.automatic_mission.worker and context.automatic_mission.worker.is_alive()
                    or context.automatic_demo.worker and context.automatic_demo.worker.is_alive()
                    or task and task.active()):
                raise BrokerError('scene_edit_robot_busy', 'Finish the active robot task before changing its scene.', status=409)
        readiness = self.readiness
        if readiness is not None and readiness.local_operation_active():
            raise BrokerError('scene_edit_robot_busy', 'Stationary collection or evidence transfer is running.', status=409)
        if self.diagnostics is not None and self.diagnostics._running():
            raise BrokerError('scene_edit_robot_busy', 'Wait for the active robot observation.', status=409)
        if self.controller is not None:
            state = self.controller.snapshot(None)
            recovery = getattr(self.controller, 'evidence_recovery', None)
            thread = getattr(recovery, 'thread', None)
            if state.get('busy') or thread and thread.is_alive():
                raise BrokerError('scene_edit_robot_busy', 'A robot operation or evidence transfer is running.', status=409)
            # A current local stop/cleanup still owns its scene. A historical
            # disconnected record never establishes current physical readiness.
            if state.get('state') == 'STOPPING':
                raise BrokerError('scene_edit_robot_busy', 'The current robot session is stopping.', status=409)

    def bind_operation(self, context):
        """Called under the shared start lock before a fresh physical operation."""
        for other in self.contexts:
            if other.product_workflow is not None and other.product_workflow.scene_edit_transaction.locked():
                raise BrokerError('scene_edit_busy', 'Finish the scene transaction before starting a robot operation.', status=409)
        execution = context.product_workflow._application.diagnostics if context.product_workflow else None
        if self.controller is not None:
            self.controller.diagnostics = execution
        if self.readiness is not None:
            self.readiness.execution_diagnostics = execution

    def snapshot(self):
        readiness = self.readiness.snapshot(None) if self.readiness else None
        controller = self.controller.snapshot(None) if self.controller else {}
        active = bool(readiness and self.readiness.local_operation_active()
                      or controller.get('busy')
                      or self.diagnostics and self.diagnostics._running())
        return dict(active=active, historical_collection_status=readiness.get('status') if readiness else None,
                    physical_state=controller.get('state', 'UNAVAILABLE'), motion_authorized=False,
                    unavailable_reason=self.unavailable_reason)

    def retain_diagnostics(self, *, days=30, archive=False):
        from .device_storage import diagnostic_retention
        if self.diagnostics is None:
            raise BrokerError('device_diagnostics_unavailable', 'Device diagnostics storage is unavailable.', status=409)
        with self.lock:
            if archive:
                self.assert_document_available()
            job = self.diagnostics.snapshot(None).get('job') or {}
            return diagnostic_retention(self.diagnostics.archive_root, days=days, archive=archive, active_job=job.get('id'))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
        if self.physical_fleet is not None:self.physical_fleet.close()
        for service in (self.controller, self.diagnostics, self.readiness):
            if service is not None:
                service.close()
        if self.registry_service is not None:self.registry_service.close()
        if self.owner_lease is not None:
            self.owner_lease.close()
