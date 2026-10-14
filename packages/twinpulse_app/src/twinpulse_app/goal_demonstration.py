# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned existing broker/Isaac Build -> exact route PhysX -> checked receipt.

Starts only on an explicit goal request; polling and restore cannot start it.
The receipt is ephemeral and binds the actual engine, stage, scene and run.
"""
from copy import deepcopy
import math
from threading import Event, RLock, Thread
import time
from uuid import uuid4
from twinpulse_core.goal_simulation import make_goal_simulation
from twinpulse_core.presentation import DEFAULT_PRESENTATION
from twinpulse_core.revisions import canonical_sha256
from .command_broker import BrokerError
from .simulation_assets import burger_inventory


class GoalDemonstration:
    def __init__(self,broker,scene_loader,*,timeout_s=155.,scene_guard_factory=None):
        self.broker=broker;self.scene_loader=scene_loader;self.timeout_s=timeout_s
        self.lock=RLock();self.worker=None;self.cancelled=Event();self.job=None;self.owner=None
        self.lease_stop=Event();self.lease_worker=None
        self.scene_guard_factory=scene_guard_factory;self.scene_guard=None

    def _maintain_lease(self,owner,lease,stop,cancelled):
        # Only explicit start arms this bounded keeper. Snapshot/restore never
        # acquires or resurrects an expired lease. Stop only stops renewal;
        # it does not revoke another operation's shared owner lease.
        started=time.monotonic()
        while not stop.wait(.5):
            try:
                if time.monotonic()-started>=445.:raise ValueError('GOAL_REVIEW_LEASE_LIFETIME_EXPIRED')
                self.broker.renew_lease(owner,lease)
            except Exception:
                cancelled.set();return

    def start(self,owner,scene,review):
        with self.lock:
            if self.worker and self.worker.is_alive():raise BrokerError('goal_demonstration_busy','Wait for or stop the current Isaac preview.',status=409)
            if review.get('binding',{}).get('context',{}).get('project_id')!=self.broker.project_id:
                raise BrokerError('goal_demonstration_project_changed','Reviewed route belongs to another project.',status=409)
            plan=make_goal_simulation(scene,review,burger_inventory())
            guard=self.scene_guard_factory() if self.scene_guard_factory else None
            if guard:
                # Bind the cheap fingerprint to a fully reopened matching
                # scene. Edits during this initial validation still reject.
                if self.scene_loader().revision!=scene.revision:
                    raise ValueError('GOAL_DEMONSTRATION_ROOM_CHANGED')
                guard()
            lease=self.broker.acquire_lease(owner)['control_lease_id']
            self.lease_stop.set()
            self.owner=owner;self.cancelled=Event()
            self.scene_guard=guard
            self.lease_stop=Event()
            self.job={'state':'PREPARING','stage':'BUILD','review_id':review['plan_id'],'simulation_id':plan['plan_id'],
                'scene_revision':scene.revision,'error':None,'cleanup_error':None,'receipt':None,
                'physical_authority':False,'elapsed_s':0.}
            self.lease_worker=Thread(target=self._maintain_lease,args=(owner,lease,self.lease_stop,self.cancelled),
                name='TwinPulseGoalLease',daemon=True)
            self.lease_worker.start()
            self.worker=Thread(target=self._run,args=(owner,scene,plan,self.cancelled),name='TwinPulseGoalDemonstration',daemon=True)
            self.worker.start()
            return deepcopy(self.job)

    def _view(self,owner,identity,*,check_scene=True):
        view=(self.broker.execution_receipt_state(owner) if not check_scene
              else self.broker.public_state(owner))
        if (not view['engine_connected'] or not view['lease_owned']
                or (view['engine_session_id'],view['stage_epoch'])!=identity):
            raise ValueError('GOAL_DEMONSTRATION_ENGINE_OR_LEASE_CHANGED')
        if check_scene:
            if self.scene_guard:self.scene_guard()
            elif self.scene_loader().revision!=self.job['scene_revision']:raise ValueError('GOAL_DEMONSTRATION_ROOM_CHANGED')
        return view

    def _run(self,owner,scene,plan,cancelled):
        started=time.monotonic();identity=None;run_sent=False;pending=None
        def update(**fields):
            with self.lock:self.job.update(fields)
        def view():
            if cancelled.is_set():raise ValueError('GOAL_DEMONSTRATION_CANCELLED')
            elapsed=time.monotonic()-started;update(elapsed_s=elapsed)
            if elapsed>self.timeout_s:raise TimeoutError('GOAL_DEMONSTRATION_TIMEOUT')
            return self._view(owner,identity)
        def wait_operation(operation):
            while True:
                result=next(o for o in view()['operations'] if o['command_id']==operation['command_id'])
                if result['status'] not in {'accepted','running'}:
                    if result['status']!='succeeded':
                        receipt=result.get('receipt') or {}
                        raise ValueError('GOAL_DEMONSTRATION_COMMAND_FAILED: '+str(receipt.get('error_code'))+': '+str(receipt.get('message'))[:220])
                    return result['receipt']
                cancelled.wait(.05)
        try:
            initial=self.broker.public_state(owner);identity=(initial['engine_session_id'],initial['stage_epoch'])
            current=view();snapshot=current['snapshot']
            if (snapshot is None or 'exact_goal_demonstration_v1' not in snapshot['capabilities']
                    or snapshot['runtime_state']=='running' or snapshot['safety_state']):
                raise ValueError('GOAL_DEMONSTRATION_ENGINE_NOT_READY')
            # The authenticated Bridge applies the freshly acquired lease on
            # its next main-thread heartbeat. Never submit before that permit.
            permit_until=time.monotonic()+6.
            while not view()['engine_readiness']['site_scene_build_v2']['ready']:
                if time.monotonic()>=permit_until:raise TimeoutError('GOAL_DEMONSTRATION_BUILD_PERMIT_TIMEOUT')
                cancelled.wait(.05)
            self.broker.register_simulation_plan(scene,plan)
            artifact_id='goal-sim-'+plan['plan_id']
            self.broker.register_site_scene(artifact_id,scene,presentation={**DEFAULT_PRESENTATION,'view':'top'})
            build=self.broker.submit(owner,{'client_request_id':'goal-build-'+uuid4().hex,'command_type':'build_site_scene',
                'artifact_id':artifact_id,'simulation_id':plan['plan_id'],'expected_applied_revision':scene.revision})
            pending=build;build_receipt=wait_operation(build);pending=None
            while view()['snapshot']['applied_revision']!=scene.revision:cancelled.wait(.05)
            update(stage='RUN',state='RUNNING')
            operation=self.broker.submit(owner,{'client_request_id':'goal-run-'+uuid4().hex,'command_type':'run',
                'simulation_id':plan['plan_id'],'expected_applied_revision':scene.revision})
            pending=operation;run_sent=True;run_receipt=wait_operation(operation);pending=None
            # A successful Run receipt is only admission, not arrival.
            while True:
                snapshot=view()['snapshot']
                if (snapshot['applied_revision']!=scene.revision or snapshot['safety_state']
                        or snapshot['runtime_state'] in {'error','stage_invalid','disconnected','off_route','unstable'}):
                    raise ValueError('GOAL_DEMONSTRATION_RUNTIME_FAILED: '+str(snapshot.get('safety_reason'))[:180])
                if snapshot['run_id']==plan['plan_id'] and snapshot['runtime_state']=='completed':
                    if (not snapshot['telemetry_available'] or snapshot['position_m'] is None
                            or math.dist(snapshot['position_m'][:2],plan['goal'])>plan['tolerance_m']+1e-6):
                        raise ValueError('GOAL_DEMONSTRATION_ARRIVAL_NOT_VERIFIED')
                    update(stage='FREEZE_RECEIPT')
                    pause=self.broker.submit(owner,{'client_request_id':'goal-freeze-'+uuid4().hex,
                        'command_type':'pause','expected_applied_revision':scene.revision})
                    pending=pause;pause_receipt=wait_operation(pause);pending=None
                    while True:
                        snapshot=view()['snapshot']
                        if (snapshot['run_id']!=plan['plan_id'] or snapshot['applied_revision']!=scene.revision
                                or snapshot['safety_state']):raise ValueError('GOAL_DEMONSTRATION_FREEZE_CHANGED')
                        if snapshot['runtime_state']=='paused':break
                        cancelled.wait(.05)
                    if (not snapshot['telemetry_available'] or snapshot['position_m'] is None
                            or math.dist(snapshot['position_m'][:2],plan['goal'])>plan['tolerance_m']+1e-6):
                        raise ValueError('GOAL_DEMONSTRATION_FROZEN_ARRIVAL_NOT_VERIFIED')
                    body={'schema':'goal-demonstration-receipt-1.0','review_id':plan['review']['plan_id'],
                        'simulation_id':plan['plan_id'],'project_id':self.broker.project_id,
                        'engine_session_id':identity[0],'stage_epoch':identity[1],'scene_revision':scene.revision,
                        'build_command_id':build_receipt['command_id'],'run_command_id':run_receipt['command_id'],
                        'pause_command_id':pause_receipt['command_id'],
                        'terminal_sequence':snapshot['sequence'],'terminal_position_m':snapshot['position_m'],
                        'route_sha256':canonical_sha256(plan['route']),'asset_files':plan['asset_files'],
                        'status':'COMPLETED','physical_authority':False}
                    update(state='COMPLETED',stage='ARRIVAL',receipt={**body,'revision':canonical_sha256(body)})
                    break
                if snapshot['run_id']==plan['plan_id'] and snapshot['runtime_state']=='paused':
                    raise ValueError('GOAL_DEMONSTRATION_PAUSED_BEFORE_ARRIVAL')
                cancelled.wait(.05)
        except Exception as exc:
            update(state='CANCELLED' if cancelled.is_set() else 'FAILED',error=type(exc).__name__+': '+str(exc)[:320],receipt=None)
            try:self._cleanup(owner,identity,plan,pending,operation if run_sent else None)
            except Exception as cleanup:update(cleanup_error=type(cleanup).__name__+': '+str(cleanup)[:180])
        finally:
            update(elapsed_s=time.monotonic()-started)
            if self.job['state']!='COMPLETED':self.lease_stop.set()

    def _cleanup(self,owner,identity,plan,pending,run_operation):
        """Cancel queued Run or await claimed admission and pause only our run.

        No replay, lease renewal, unrelated-stage write or physical command.
        Failure to observe a stop remains a separate, explicit cleanup error.
        """
        deadline=time.monotonic()+2.;pause=None
        while True:
            current=self.broker.public_state(owner);s=current['snapshot']
            if (not current['engine_connected'] or not current['lease_owned']
                    or (current['engine_session_id'],current['stage_epoch'])!=identity):
                if pending is not None or run_operation is not None:raise ValueError('GOAL_DEMONSTRATION_CLEANUP_IDENTITY_UNAVAILABLE')
                return
            if pending is not None:
                operation=next(o for o in current['operations'] if o['command_id']==pending['command_id'])
                if operation['status']=='accepted':self.broker.cancel(owner,pending['command_id']);pending=None
                elif operation['status']!='running':pending=None
            if pending is None:
                if run_operation is None:return
                if s and s['run_id']==plan['plan_id']:
                    if s['runtime_state'] in {'paused','error','stage_invalid','disconnected'}:return
                    if pause is None:
                        pause=self.broker.submit(owner,{'client_request_id':'goal-pause-'+uuid4().hex,
                            'command_type':'pause','expected_applied_revision':plan['scene_revision']})
                    else:
                        outcome=next(o for o in current['operations'] if o['command_id']==pause['command_id'])
                        if outcome['status'] not in {'accepted','running','succeeded'}:
                            raise ValueError('GOAL_DEMONSTRATION_CLEANUP_PAUSE_FAILED')
                elif next(o for o in current['operations'] if o['command_id']==run_operation['command_id'])['status'] in {'failed','cancelled','expired','rejected'}:
                    # A rejected/cancelled Run never created this articulation.
                    return
            if time.monotonic()>=deadline:raise TimeoutError('GOAL_DEMONSTRATION_CLEANUP_UNCONFIRMED')
            time.sleep(.02)

    def snapshot(self,owner):
        with self.lock:return deepcopy(self.job) if owner==self.owner else None

    def passed(self,owner,digest):
        return self._receipt_current(owner,digest,check_scene=True)

    def execution_passed(self,owner,digest):
        # Only ChatGoalNavigation's mission execution guard uses this. Its
        # AutomaticMissionService independently checks the source fingerprint
        # on every tick; admission/Confirm/UI still fully reopen the scene.
        # Rehashing photos and assets here would stall the input keeper.
        return self._receipt_current(owner,digest,check_scene=False)

    def _receipt_current(self,owner,digest,*,check_scene):
        if self.cancelled.is_set():return False
        job=self.snapshot(owner)
        if not job or job['state']!='COMPLETED' or job['review_id']!=digest:return False
        receipt=job['receipt']
        try:
            view=self._view(owner,(receipt['engine_session_id'],receipt['stage_epoch']),check_scene=check_scene);s=view['snapshot']
            return bool(s and s['run_id']==job['simulation_id'] and s['applied_revision']==job['scene_revision']
                and s['runtime_state']=='paused' and not s['safety_state'] and s['telemetry_available']
                and s['sequence']>=receipt['terminal_sequence'] and s['position_m']==receipt['terminal_position_m'])
        except (ValueError,BrokerError,OSError,KeyError):return False

    def stop(self,owner):
        with self.lock:
            if owner!=self.owner:raise BrokerError('goal_demonstration_not_owned','Preview belongs to another connection.',status=409)
            self.cancelled.set()
            self.lease_stop.set()

    def finish_execution(self,owner):
        # Terminal navigation releases only this keeper, not its historical
        # SIM receipt or any lease shared by another same-owner operation.
        with self.lock:
            if owner==self.owner:self.lease_stop.set()

    def close(self):
        self.cancelled.set()
        self.lease_stop.set()
        worker=self.worker
        if worker and worker.is_alive():worker.join(2.)
        if self.lease_worker and self.lease_worker.is_alive():self.lease_worker.join(1.)
