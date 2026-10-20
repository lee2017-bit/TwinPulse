# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Outbound stdlib HTTP bridge worker; no USD/PhysX access occurs here."""

from __future__ import annotations

from collections import deque
import json
from threading import Event, Lock, Thread, local
import time
from typing import Any, Mapping
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from twinpulse_core import CommandEnvelope, CommandReceipt, SimulationSnapshot

from .isaac_adapter import IsaacSimulationAdapter


class BridgeProtocolError(RuntimeError):
    pass


class BridgeClient:
    """Polls the backend on an I/O thread and executes on explicit main-thread updates."""

    def __init__(
        self,
        adapter: IsaacSimulationAdapter,
        *,
        base_url: str,
        bootstrap_secret: str,
        poll_interval_s: float = 0.1,
        heartbeat_interval_s: float = 1.0,
        watchdog_timeout_s: float = 3.0,
        queue_limit: int = 16,
        clock=time.monotonic,
    ) -> None:
        if not base_url.startswith("http://127.0.0.1:"):
            raise ValueError("Bridge URL must use the 127.0.0.1 loopback origin")
        if len(bootstrap_secret) < 32:
            raise ValueError("Engine bootstrap secret is invalid")
        self.adapter = adapter
        self.base_url = base_url.rstrip("/")
        self._bootstrap_secret: str | None = bootstrap_secret
        self._poll_interval_s = poll_interval_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._watchdog_timeout_s = watchdog_timeout_s
        self._queue_limit = queue_limit
        self._clock = clock
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._robot_http=local()
        self._incoming: deque[CommandEnvelope] = deque()
        self._activity_records = deque(maxlen=120)
        self._outgoing: deque[CommandReceipt] = deque()
        self._command_timings = {}
        self._timing_clock_id = uuid4().hex
        self._dropped_receipts = 0
        self._latest_snapshot: SimulationSnapshot | None = None
        self._engine_token: str | None = None
        self._shared_stage_epoch = adapter.stage_epoch
        self._remote_stage_epoch: str | None = None
        self._lease_valid = False
        self._lease_id: str | None = None
        self._last_success = clock()
        self._last_snapshot_at = 0.0
        self._last_error: str | None = None
        self._rebind_ticket=None;self._rebind_ack=None
        self._mission_objects=None;self._mission_frame=None;self._mission_received=0.;self._mission_revision=None
        self._mission_available=False;self._mission_result=None
        self._mission_geometry=None;self._mission_geometry_cursor=None
        self.mission_visual_status='NOT_STARTED'
        self.mission_visual_error=None

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._engine_token is not None and self._clock() - self._last_success <= self._watchdog_timeout_s

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def activity_snapshot(self):
        """Bounded UI facts only; command payloads/authentication stay private."""
        with self._lock:
            return [dict(row) for row in self._activity_records]

    def _activity_locked(self, command, status, *, elapsed_s=None, error_code=None, revision=None):
        row=dict(timestamp=time.time(),command_id=command.command_id,command_type=command.command_type,
            project_id=command.project_id,status=status,engine_session_id=command.engine_session_id,
            stage_epoch=command.stage_epoch)
        execution_id=self._command_timings.get(command.command_id,{}).get('execution_id')
        if execution_id:row['execution_id']=execution_id
        if elapsed_s is not None:row['elapsed_s']=round(elapsed_s,3)
        if error_code:row['error_code']=error_code
        if revision:row['revision']=revision
        self._activity_records.append(row)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._network_loop, name="TwinPulseBridgeIO", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None

    def update(self) -> None:
        """Run from Kit's update thread; this is the only method touching the adapter."""
        with self._lock:
            ticket=self._rebind_ticket if self._rebind_ack is None else None
        if ticket:
            try:
                with self._lock:
                    if self._incoming:raise ValueError('PROJECT_SWITCH_COMMAND_PENDING')
                snapshot=self.adapter.rebind_project(ticket)
                ack=dict(switch_id=ticket['switch_id'],ticket=ticket,snapshot=snapshot.to_dict(),error=None)
                with self._lock:
                    self._shared_stage_epoch=self.adapter.stage_epoch
                    self._incoming.clear();self._outgoing.clear();self._command_timings.clear()
                    self._latest_snapshot=None;self._mission_objects=None;self._mission_frame=None
                    self._mission_geometry=None;self._mission_geometry_cursor=None;self._mission_result=None
                    self._mission_available=False;self._mission_revision=None
                    self._lease_valid=False;self._lease_id=None
            except Exception as error:
                ack=dict(switch_id=ticket['switch_id'],ticket=ticket,snapshot=None,
                    error=('PROJECT_REBIND_UNCERTAIN: ' if getattr(self.adapter,'_project_rebind_started',False) else '')+type(error).__name__+': '+str(error)[:100])
            with self._lock:self._rebind_ack=ack
            return
        if self.adapter.refresh_stage_epoch():
            with self._lock:
                self._shared_stage_epoch = self.adapter.stage_epoch
                self._mission_geometry=None;self._mission_geometry_cursor=None;self._mission_frame=None
        now = self._clock()
        with self._lock:
            lease_valid = self._lease_valid
            lease_id = self._lease_id
            stale = now - self._last_success > self._watchdog_timeout_s
            command = self._incoming.popleft() if self._incoming else None
        self.adapter.update_control_lease(lease_id, lease_valid and not stale)
        with self._lock:
            frame=self._mission_frame;received=self._mission_received;self._mission_frame=None
            geometry=self._mission_geometry;self._mission_geometry=None
            visual_available=self._mission_available
        if geometry and (not lease_valid or stale or now-received>=.5):
            with self._lock:self._mission_result={'job_id':geometry['job_id'],'sequence':geometry['sequence'],
                'status':'ACTIVE_GEOMETRY_RENDER_FAILED','error_code':'ACTIVE_GEOMETRY_PERMIT_EXPIRED','error_type':'ValueError'}
            self.mission_visual_status='ACTIVE_GEOMETRY_RENDER_FAILED'
        if geometry and lease_valid and not stale and now-received<.5:
            outcome={'job_id':geometry['job_id'],'sequence':geometry['sequence'],'status':'ACTIVE_GEOMETRY_COMPOSED_NOT_CURRENT'}
            try:
                self.adapter.update_mission_geometry(geometry)
                self.mission_visual_status=self.adapter.mission_visual_status
            except Exception as exc:
                import re
                code=str(exc)
                outcome.update(status='ACTIVE_GEOMETRY_RENDER_FAILED',
                    error_code=code if re.fullmatch('[A-Z0-9_]{1,120}',code) else 'ACTIVE_GEOMETRY_PROCESSING_FAILED',
                    error_type=type(exc).__name__[:80])
                self.mission_visual_status=outcome['status']
            with self._lock:self._mission_result=outcome;self._mission_frame=None
            # Fresh pose/scan are accepted only on a subsequent authenticated
            # poll after composition. A late build cannot revive the session.
        elif frame and lease_valid and not stale and now-received<.5:
            try:
                self.adapter.update_mission_visual(frame)
                self.mission_visual_status=self.adapter.mission_visual_status
            except Exception as exc:
                # Visual failure has no physical control authority and does
                # not execute an engine command or silently claim success.
                from twinpulse_core.active_mission_visual import DISPLAY_STATUSES
                self.mission_visual_status=str(exc) if str(exc) in DISPLAY_STATUSES else 'ACTIVE_VISUAL_RENDER_FAILED'
                import re
                code=str(exc)
                self.mission_visual_error={'error_code':code if re.fullmatch('[A-Z0-9_]{1,120}',code) else 'ACTIVE_VISUAL_PROCESSING_FAILED',
                    'error_type':type(exc).__name__[:80]}
            with self._lock:
                self._mission_result={'job_id':frame['job_id'],'sequence':frame['sequence'],'status':self.mission_visual_status}
        elif hasattr(self.adapter,'mark_mission_visual_inactive') and (not visual_available or not lease_valid or stale or now-received>=.5):
            reason='ACTIVE_VISUAL_STALE' if visual_available else self.mission_visual_status
            self.adapter.mark_mission_visual_inactive(reason)
            with self._lock:
                if self._mission_result:
                    previous=self._mission_result
                    self._mission_result=({**previous,'status':reason} if reason=='ACTIVE_GEOMETRY_RENDER_FAILED' else
                        {'job_id':previous['job_id'],'sequence':previous['sequence'],'status':reason})
        objects=self.adapter.mission_objects_revision() if hasattr(self.adapter,'mission_objects_revision') else None
        with self._lock:self._mission_objects=objects
        if stale:
            # Promote the safety reason once the transport watchdog confirms a
            # backend outage, even if an earlier lease failure already paused.
            self.adapter.fail_safe_pause("Backend connection lost")
        elif not lease_valid and self.adapter.runtime.state == "running":
            self.adapter.fail_safe_pause("Control lease expired")
        if command is not None:
            executing_at = self._clock()
            with self._lock:self._activity_locked(command,'executing')
            receipt = self.adapter.execute(command)
            executed_at = self._clock()
            with self._lock:
                self._activity_locked(command,receipt.status,elapsed_s=executed_at-executing_at,
                    error_code=receipt.error_code,revision=receipt.applied_revision)
                if len(self._outgoing) >= self._queue_limit:
                    dropped = self._outgoing.popleft()
                    self._command_timings.pop(dropped.command_id,None)
                    self._dropped_receipts += 1
                timing = self._command_timings.get(command.command_id)
                if timing is not None:
                    timing.update(kit_queue_s=max(0.,executing_at-timing.pop('queued_at')),
                                  adapter_execute_s=max(0.,executed_at-executing_at),executed_at=executed_at)
                self._outgoing.append(receipt)
        if now - self._last_snapshot_at >= 0.1:
            snapshot = self.adapter.snapshot()
            with self._lock:
                self._latest_snapshot = snapshot
            self._last_snapshot_at = now

    def _network_loop(self) -> None:
        next_heartbeat = 0.0
        next_visual=0.
        try:
            self._bootstrap()
            while not self._stop.is_set():
                try:
                    with self._lock:rebind=self._rebind_ticket;ack=self._rebind_ack
                    if rebind:
                        if ack:
                            result=self._post('/v1/engine/project-rebind',ack)
                            if result.get('status') not in ('switched','failed'):
                                raise BridgeProtocolError('Project rebind was not acknowledged')
                            with self._lock:
                                self._remote_stage_epoch=self._shared_stage_epoch
                                self._rebind_ticket=None;self._rebind_ack=None
                                self._last_success=self._clock()
                            next_heartbeat=0.
                        self._stop.wait(self._poll_interval_s)
                        continue
                    with self._lock:
                        stage_epoch = self._shared_stage_epoch
                        remote_stage_epoch = self._remote_stage_epoch
                    if remote_stage_epoch != stage_epoch:
                        self._transition_stage(remote_stage_epoch or stage_epoch, stage_epoch)
                    now = self._clock()
                    if now >= next_heartbeat:
                        self._refresh_control_lease(stage_epoch)
                        next_heartbeat = now + self._heartbeat_interval_s
                    self._flush_receipts()
                    self._flush_snapshot()
                    with self._lock:objects=self._mission_objects;visual_allowed=self._lease_valid
                    if visual_allowed and objects and now>=next_visual:
                        # Optional display transport must not disable unrelated
                        # engine commands or become a physical control signal.
                        try:
                            with self._lock:display_result=self._mission_result
                            result=self._post('/v1/engine/mission-visual',{'engine_session_id':self.adapter.engine_session_id,
                                'stage_epoch':stage_epoch,'objects_revision':objects,'display_result':display_result})
                            frame=result.get('frame')
                            geometry=result.get('geometry')
                            if geometry:
                                from twinpulse_core.active_mission_visual import checked_active_geometry
                                geometry=checked_active_geometry(geometry)
                                cursor=(geometry['engine_session_id'],geometry['stage_epoch'],geometry['job_id'],geometry['correction_revision'])
                                with self._lock:
                                    self._mission_frame=None;self._mission_available=False
                                    if cursor!=self._mission_geometry_cursor:
                                        self._mission_received=self._clock();self._mission_geometry=geometry;self._mission_geometry_cursor=cursor
                            elif frame:
                                from twinpulse_core.active_mission_visual import checked_active_frame
                                frame=checked_active_frame(frame)
                                with self._lock:
                                    self._mission_received=self._clock();self._mission_available=True
                                    if frame['revision']!=self._mission_revision:self._mission_frame=frame
                                self._mission_revision=frame['revision']
                            else:
                                with self._lock:self._mission_frame=None;self._mission_geometry=None;self._mission_available=False
                                self.mission_visual_status=result.get('code','ACTIVE_VISUAL_UNAVAILABLE')
                        except (BridgeProtocolError,HTTPError,URLError,OSError,ValueError):
                            with self._lock:self._mission_frame=None;self._mission_geometry=None;self._mission_available=False
                            self.mission_visual_status='ACTIVE_VISUAL_UNAVAILABLE'
                        next_visual=now+.2
                    with self._lock:
                        can_claim = self._lease_valid and len(self._incoming) < self._queue_limit
                    if can_claim:
                        result = self._post(
                            "/v1/engine/claim",
                            {"engine_session_id": self.adapter.engine_session_id, "stage_epoch": stage_epoch},
                        )
                        value = result.get("command")
                        if value is not None:
                            if not isinstance(value, Mapping):
                                raise BridgeProtocolError("Backend command is not an object")
                            command = CommandEnvelope.from_dict(value)
                            self._queue_claimed_command(command, stage_epoch,execution_id=result.get('execution_id'))
                    with self._lock:
                        self._last_success = self._clock()
                        self._last_error = None
                except (BridgeProtocolError, HTTPError, URLError, OSError, ValueError) as error:
                    with self._lock:
                        self._last_error = f"{type(error).__name__}: {str(error)[:240]}"
                        self._lease_valid = False
                        self._lease_id = None
                    self._stop.wait(min(0.5, self._poll_interval_s * 5.0))
                    continue
                self._stop.wait(self._poll_interval_s)
        except (BridgeProtocolError, HTTPError, URLError, OSError, ValueError) as error:
            with self._lock:
                self._last_error = f"{type(error).__name__}: {str(error)[:240]}"
                self._lease_valid = False
                self._lease_id = None

    def _refresh_control_lease(self, stage_epoch: str) -> None:
        # Only the authenticated backend heartbeat grants a lease. A command
        # envelope alone never grants authority or extends its lifetime.
        heartbeat = self._post("/v1/engine/heartbeat", {
            "engine_session_id": self.adapter.engine_session_id,
            "stage_epoch": stage_epoch,
        })
        with self._lock:
            ticket=heartbeat.get('project_rebind')
            if ticket:
                from twinpulse_app.project_store import checked_project_id
                checked_project_id(ticket['project_id'])
                if set(ticket)!= {'switch_id','from_context_id','target_context_id','project_id','new_stage_epoch'}:
                    raise BridgeProtocolError('Invalid project rebind ticket')
                self._rebind_ticket=ticket
            lease = heartbeat.get("control_lease_id")
            self._lease_id = lease if isinstance(lease, str) else None
            self._lease_valid = bool(heartbeat.get("lease_valid")) and self._lease_id is not None

    def _queue_claimed_command(self, command: CommandEnvelope, stage_epoch: str, execution_id=None) -> None:
        with self._lock:
            refresh = not self._lease_valid or command.control_lease_id != self._lease_id
            if refresh:
                # A new product lease can be acquired between periodic engine
                # heartbeats. Invalidate the old cached grant before network I/O.
                self._lease_valid = False
                self._lease_id = None
        try:
            if refresh:
                self._refresh_control_lease(stage_epoch)
        finally:
            # The broker already claimed this command. Preserve it for an
            # explicit adapter rejection/receipt even if refresh fails. Kit's
            # update applies the trusted (or invalid) grant before execution.
            with self._lock:
                if len(self._command_timings)<self._queue_limit*2:
                    self._command_timings[command.command_id]={'queued_at':self._clock()}
                    import re
                    if isinstance(execution_id,str) and re.fullmatch(r'[a-f0-9]{32}',execution_id):
                        self._command_timings[command.command_id]['execution_id']=execution_id
                self._incoming.append(command)
                self._activity_locked(command,'received')

    def _bootstrap(self) -> None:
        secret = self._bootstrap_secret
        if secret is None:
            raise BridgeProtocolError("Engine bootstrap secret is unavailable")
        result = self._post(
            "/v1/bootstrap",
            {
                "role": "engine", "secret": secret,
                "engine_session_id": self.adapter.engine_session_id,
                "stage_epoch": self.adapter.stage_epoch,
            },
            authenticated=False,
        )
        token = result.get("session_token")
        if not isinstance(token, str) or not token:
            raise BridgeProtocolError("Backend did not issue an engine session")
        with self._lock:
            self._engine_token = token
            self._remote_stage_epoch = self.adapter.stage_epoch
            self._last_success = self._clock()
        self._bootstrap_secret = None

    def _transition_stage(self, current: str, new: str) -> None:
        result = self._post(
            "/v1/engine/stage",
            {
                "engine_session_id": self.adapter.engine_session_id,
                "current_stage_epoch": current,
                "new_stage_epoch": new,
            },
        )
        if result.get("stage_epoch") != new:
            raise BridgeProtocolError("Backend did not accept the stage transition")
        with self._lock:
            self._remote_stage_epoch = new

    def _flush_receipts(self) -> None:
        while True:
            with self._lock:
                receipt = self._outgoing[0] if self._outgoing else None
            if receipt is None:
                return
            body={'receipt':receipt.to_dict()}
            with self._lock:
                timing=self._command_timings.get(receipt.command_id)
                if timing is not None and 'executed_at' in timing:
                    body['diagnostics']={'clock_instance_id':self._timing_clock_id,
                        'kit_queue_s':timing['kit_queue_s'],'adapter_execute_s':timing['adapter_execute_s'],
                        'receipt_queue_s':max(0.,self._clock()-timing['executed_at']),
                        'dropped_receipts':min(self._dropped_receipts,1000000)}
            self._post("/v1/engine/receipt", body)
            with self._lock:
                if self._outgoing and self._outgoing[0] == receipt:
                    self._outgoing.popleft()
                    self._command_timings.pop(receipt.command_id,None)

    def _flush_snapshot(self) -> None:
        with self._lock:
            snapshot = self._latest_snapshot
        if snapshot is None:
            return
        self._post("/v1/engine/snapshot", {"snapshot": snapshot.to_dict()})
        with self._lock:
            if self._latest_snapshot == snapshot:
                self._latest_snapshot = None

    def _post(
        self, path: str, body: Mapping[str, Any], *, authenticated: bool = True,
    ) -> Mapping[str, Any]:
        headers = {"Content-Type": "application/json", "Host": self.base_url.removeprefix("http://")}
        if authenticated:
            with self._lock:
                token = self._engine_token
            if token is None:
                raise BridgeProtocolError("Engine session is unavailable")
            headers["Authorization"] = f"Bearer {token}"
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if path=='/v1/engine/robots':
            return self._post_robot_report(payload,headers)
        request = Request(self.base_url + path, data=payload, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=2.0) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = detail.get("error", {}).get("code", "http_error")
            except Exception:
                message = "http_error"
            raise BridgeProtocolError(f"Backend rejected request: {message}") from error
        if not isinstance(value, Mapping):
            raise BridgeProtocolError("Backend response is not an object")
        return value

    def close_robot_channel(self):
        """Called by its owning FleetIO thread; never shared with BridgeIO."""
        connection=getattr(self._robot_http,'connection',None)
        self._robot_http.connection=None
        if connection is not None:connection.close()

    def _post_robot_report(self,payload,headers):
        from http.client import HTTPConnection
        from urllib.parse import urlsplit
        connection=getattr(self._robot_http,'connection',None)
        if connection is None:
            address=urlsplit(self.base_url)
            if address.hostname!='127.0.0.1' or address.path or address.query or address.fragment:
                raise BridgeProtocolError('Robot channel requires exact loopback origin')
            connection=HTTPConnection(address.hostname,address.port,timeout=2.0)
            self._robot_http.connection=connection
        try:
            # One owner, one in-flight current report. No retry of this POST,
            # including on stale reused sockets: discard and fail this cycle.
            started=time.monotonic()
            connection.request('POST','/v1/engine/robots',body=payload,headers=headers)
            sent=time.monotonic()
            response=connection.getresponse();responded=time.monotonic();raw=response.read()
            read=time.monotonic()
            if response.will_close:self.close_robot_channel()
            value=json.loads(raw.decode('utf-8'))
            self._robot_http.timing=dict(send_s=round(sent-started,6),headers_s=round(responded-sent,6),
                body_s=round(read-responded,6),decode_s=round(time.monotonic()-read,6))
            if response.status!=200:
                raise BridgeProtocolError('Backend rejected robot report')
            if not isinstance(value,Mapping) or not isinstance(value.get('fleet'),Mapping):
                raise BridgeProtocolError('Backend robot response is not a fleet object')
            return value
        except Exception:
            self.close_robot_channel()
            raise

    def robot_channel_timing(self):
        # Numeric phases only, read by the same FleetIO owner; no URL, headers,
        # payload, credential, socket operations or authority changes.
        return dict(getattr(self._robot_http,'timing',{}))
