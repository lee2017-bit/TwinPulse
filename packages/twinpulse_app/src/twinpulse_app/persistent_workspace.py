# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One loopback listener, immutable project services, acknowledged Kit rebinds."""
from threading import RLock, Event, Thread, get_ident
import time
from uuid import uuid4
from urllib.parse import urlsplit
from twinpulse_core import SimulationSnapshot
from .command_broker import BrokerError

DIAGNOSTIC_ROUTES=frozenset('/v1/product/'+name for name in (
    'conversation','commands','projects/switch','projects/create','viewport/camera',
    'viewport/observation','runtime/shutdown','scene-sensor/review','scene-feedback'))

class PersistentWorkspace:
    def __init__(self, server, factory):
        self.root=server;self.active=server;self.factory=factory
        if not hasattr(server,'context_id'):server.context_id=uuid4().hex
        self.lock=RLock();self.pending=None;self.completed={};self.contexts=[server]
        self.mutations={server.context_id:0};self.abandoned=[];self.closing=False
        self.active_requests={}
        self.sim_retirements=[]
        # Response delivery can occur inside an API/robot mutex. Never acquire
        # workspace.lock there: callers may already own worker/robot locks.
        # Activity only ever nests after workspace, never the other way round.
        self._request_lock=RLock()
        server.workspace=self

    def dispatch(self, request):
        path=urlsplit(request.path).path
        with self.lock:reader=self.active
        body=None
        stop_actions={'/v1/product/robot/physical/input':{'stop','close','finish_stop','force_stop'},
            '/v1/product/robot-fleet':{'stop','stop_all','disconnect'},
            '/v1/product/robot/controller/input':{'stop','stop_all','close','lidar_stop'},
            '/v1/product/automatic-demo/control':{'cancel'},'/v1/product/conversation':{'cancel'}}
        if request.command=='POST' and path in stop_actions:
            try:
                reader._authenticate_product(request,require_csrf=True)
                body=reader._read_json(request,maximum=14*1024*1024 if path.endswith('/conversation') else 256*1024)
                request._twinpulse_saved_json=body
            except BrokerError as error:return reader._error(request,error.status,error.code,str(error))
        failure=None
        with self.lock:
            api=self.active
            context=request.headers.get('X-TwinPulse-Context')
            product=path.startswith('/v1/product/')
            stopping=path.endswith('/cancel') or path.endswith('/mission-stop') or path=='/v1/product/conversation/robot/stop' or bool(body and body.get('action') in stop_actions.get(path,set()))
            if product and path!='/v1/product/session' and (
                    context is not None and context!=api.context_id or
                    len(self.contexts)>1 and context is None) and not stopping:
                request._twinpulse_context_id=api.context_id
                failure=('project_context_changed','The active conversation changed. Reload its state.')
            mutation=product and request.command=='POST' and not stopping
            if self.closing and mutation and path != '/v1/product/runtime/shutdown':
                failure=('runtime_stopping','TwinPulse is shutting down. Reopen it after completion.')
            if self.pending and mutation:
                failure=('project_switch_pending','Opening the selected conversation.')
            ticket=None
            if mutation and not failure:
                context_id=api.context_id
                with self._request_lock:
                    self.mutations[context_id]=self.mutations.get(context_id,0)+1
                    ticket=uuid4().hex
                    self.active_requests[ticket]=dict(context_id=context_id,
                        route=path if path in DIAGNOSTIC_ROUTES else 'other_product_post',
                        thread_id=get_ident(),phase='dispatch',started=time.monotonic(),fenced=True)
                request._twinpulse_request_phase=lambda phase:self.request_phase(ticket,phase)
                request._twinpulse_business_done=lambda:self.finish_business(ticket)
            request._twinpulse_context_id=api.context_id
        if failure:return api._error(request,409,*failure)
        try:
            # Every callback/guard belongs to this immutable service instance.
            return api._handle_current(request)
        finally:
            if mutation:
                with self.lock:
                    self.finish_business(ticket)
                    with self._request_lock:self.active_requests.pop(ticket,None)

    def finish_business(self,ticket):
        """A ready response no longer owns scene mutation, even if its socket stalls.

        Worker, transaction, pending engine command, physical UNKNOWN and switch
        gates remain separate. Late response identity is still request-pinned.
        """
        with self._request_lock:
            item=self.active_requests.get(ticket)
            if item and item['fenced']:
                self.mutations[item['context_id']]-=1
                item['fenced']=False

    def request_phase(self,ticket,phase):
        with self._request_lock:
            item=self.active_requests.get(ticket)
            if item:item['phase']=phase

    def request_diagnostics(self):
        """No body, address, query string, credentials, or user text."""
        with self._request_lock:
            now=time.monotonic()
            return [dict(request_id=k,**{name:v[name] for name in
                ('context_id','route','thread_id','phase','fenced')},elapsed_s=round(now-v['started'],3))
                for k,v in list(self.active_requests.items())[:32]]

    def pending_business_count(self):
        # Authority must never use the capped diagnostic sample above.
        with self._request_lock:
            return sum(v['fenced'] and v['route']!='/v1/product/runtime/shutdown'
                for v in self.active_requests.values())

    def begin(self, api, project_id):
        with self.lock:
            if api is not self.active or self.pending:
                raise BrokerError('project_switch_pending','A conversation switch is already pending.',status=409)
            if self.mutations.get(api.context_id,0)>1:
                raise BrokerError('project_switch_busy','Wait for the current change to finish.',status=409)
            state=api.broker.supervisor_state()
            snapshot=state.get('snapshot') or {}
            if not state['engine_connected'] or snapshot.get('runtime_state')=='running':
                raise BrokerError('project_switch_busy','Stop the current simulation before switching.',status=409)
            if 'project_rebind_v1' not in snapshot.get('capabilities',[]):
                raise BrokerError('project_rebind_unavailable','Restart TwinPulse once to load conversation switching.',status=409)
            ticket=dict(switch_id=uuid4().hex,from_context_id=api.context_id,
                target_context_id=uuid4().hex,project_id=project_id,new_stage_epoch=str(uuid4()))
            pending=dict(ticket=ticket,api=None,event=Event(),error=None)
            self.pending=pending
        try:
            # New mutations are now fenced. Recheck workers started by an older request.
            with api._scene_edit_admission('project-switch'):
                if api._workflow().has_active_generation() or api.broker.has_pending_operations() or (
                        api.conversation._feedback_worker and api.conversation._feedback_worker.is_alive()):
                    raise BrokerError('project_switch_busy','Wait for the current operation to finish.',status=409)
            # A prior context may still be draining this project's files. Never
            # create a new writer alongside it. This wait is outside workspace
            # and robot locks and does not delay the bridge's 2s rebind ACK.
            self._wait_sim_retirement(project_id)
            with self.lock:
                if self.closing:raise BrokerError('runtime_stopping','TwinPulse is shutting down.',status=409)
            target=self.factory(project_id)
            target.context_id=ticket['target_context_id'];target.workspace=self
            for name in ('_sessions','_session_lock','_bootstrap','_bootstrap_expires_at','_product_bootstrap_tickets','_httpd'):
                setattr(target,name,getattr(self.root,name))
            with self.lock:pending['api']=target
        except Exception:
            with self.lock:self.pending=None
            raise
        event=pending['event']
        if not event.wait(15):
            # Keep admission closed: Kit may have switched even if the ACK was lost.
            return dict(status='requested',project_id=project_id,new_session_required=False,
                        context_id=api.context_id,switch_id=ticket['switch_id'])
        with self.lock:
            result=self.completed[ticket['switch_id']]
        if result.get('error'):
            raise BrokerError('project_switch_failed',result['error'],status=409)
        return result

    def instruction(self):
        with self.lock:
            return dict(self.pending['ticket']) if self.pending and self.pending['api'] else None

    def switching(self):
        with self.lock:return self.pending is not None

    def acknowledge(self, api, session, body):
        with self.lock:
            identity=body.get('switch_id')
            if identity in self.completed:return self.completed[identity]
            pending=self.pending
            if not pending or pending['api'] is None or body.get('ticket')!=pending['ticket']:
                raise BrokerError('project_rebind_stale','The project switch does not match.',status=409)
            if body.get('error'):
                if str(body['error']).startswith('PROJECT_REBIND_UNCERTAIN'):
                    pending['error']='Engine switch needs reconciliation; the saved scene checkpoint is retained.'
                    return dict(status='uncertain',switch_id=identity)
                result=dict(status='failed',project_id=pending['ticket']['project_id'],
                    error='Isaac could not switch conversations: '+str(body['error'])[:100])
                self.abandoned.append(pending['api'])
                self.completed[identity]=result;self.pending=None;pending['event'].set();return result
            snapshot=SimulationSnapshot.from_dict(body['snapshot'])
            ticket=pending['ticket'];target=pending['api']
            if (api is not self.active or session.engine_session_id!=snapshot.engine_session_id
                    or snapshot.project_id!=ticket['project_id'] or snapshot.stage_epoch!=ticket['new_stage_epoch']
                    or snapshot.runtime_state=='running' or snapshot.applied_revision is not None):
                raise BrokerError('project_rebind_snapshot_invalid','Isaac did not confirm the selected empty context.',status=409)
            target.broker.register_engine(snapshot.engine_session_id,snapshot.stage_epoch)
            target.broker.record_snapshot(snapshot)
            session.stage_epoch=snapshot.stage_epoch
            fleet=getattr(api,'robot_fleet',None)
            retirement=None
            if fleet is not None:
                retirement=dict(project_id=api.broker.project_id,fleet=fleet,done=Event(),receipt=None)
                self.sim_retirements.append(retirement)
            self.active=target;self.contexts.append(target);self.mutations[target.context_id]=0
            result=dict(status='switched',project_id=ticket['project_id'],context_id=target.context_id,
                        new_session_required=False,switch_id=identity,stage_epoch=snapshot.stage_epoch)
            self.completed[identity]=result;self.pending=None;pending['event'].set()
        # Disk serialization/joins must not happen inside workspace.lock or the
        # 2s bridge ACK. Physical sessions belong to WorkspaceDevices and are not
        # closed by RobotFleet.close. Duplicate ACKs reuse completed above.
        if retirement is not None:
            def retire():
                try:retirement['receipt']=fleet.close(reason='PROJECT_SWITCH')
                except Exception:retirement['receipt']=dict(complete=False,error='SIM_RETIRE_FAILED')
                finally:retirement['done'].set()
            Thread(target=retire,name='TwinPulseRetiredSIM',daemon=True).start()
        with self.lock:
            if not self.closing:target.manual_controller.start_watchdog()
        return result

    def _wait_sim_retirement(self,project_id):
        with self.lock:pending=[r for r in self.sim_retirements if r['project_id']==project_id]
        end=time.monotonic()+3
        for item in pending:
            item['done'].wait(max(0,end-time.monotonic()))
            fleet=item['fleet']
            while (not item['done'].is_set() or fleet.snapshot_writer.thread.is_alive() or
                   any(r.thread.is_alive() for r in fleet.recorders.values())):
                if time.monotonic()>=end:
                    raise BrokerError('project_retirement_pending','Previous SIM records are still draining. Wait before reopening this conversation.',status=409)
                time.sleep(.01)

    def close(self):
        contexts=self.contexts[1:]+self.abandoned
        if self.pending and self.pending.get('api'):contexts.append(self.pending['api'])
        for context in contexts:
            context.stop()
