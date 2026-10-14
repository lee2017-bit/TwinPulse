# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Authenticated loopback-only HTTP/JSON API for the R4 bridge."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import base64
import binascii
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
from threading import RLock, Thread
import time
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from twinpulse_core import CommandReceipt, SimulationSnapshot

from .command_broker import BrokerError, CommandBroker
from .credentials import CredentialStore
from .key_registry import KeyRegistry, KeyRegistryError
from .manual_controller import ManualController
from .bedroom_review import BedroomReview, UnavailableBedroomReview
from .room_localization_review import RoomLocalizationReview
from .automatic_demo_service import AutomaticDemoService
from .product_workflow_service import ProductWorkflow
from .settings import (
    DEFAULT_PROVIDER_PROFILE,
    JsonProviderSettingsStore,
    ProviderSettings,
    provider_settings_preset,
)


MAX_JSON_BYTES = 256 * 1024
MAX_UPLOAD_JSON_BYTES = 14 * 1024 * 1024
PRODUCT_COOKIE = "twinpulse_product"


@dataclass(slots=True)
class _Session:
    session_id: str
    role: str
    csrf: str | None
    idle_expires_at: float
    absolute_expires_at: float
    engine_session_id: str | None = None
    stage_epoch: str | None = None


class LocalApiServer:
    """One-process local API. It deliberately has no CORS or remote-bind mode."""

    def __init__(
        self,
        broker: CommandBroker,
        *,
        product_bootstrap_secret: str,
        engine_bootstrap_secret: str,
        host: str = "127.0.0.1",
        port: int = 0,
        bootstrap_ttl_s: float = 30.0,
        session_idle_ttl_s: float = 1800.0,
        session_absolute_ttl_s: float = 28800.0,
        product_workflow: ProductWorkflow | None = None,
        static_root: Path | None = None,
        supervisor_status_file: Path | None = None,
        launcher_retry_file: Path | None = None,
        launcher_project_switch_file: Path | None = None,
        launcher_cancel_file: Path | None = None,
        launcher_shutdown_file: Path | None = None,
        engine_result_file: Path | None = None,
        launcher_retry_remaining: int = 0,
        provider_settings_store: JsonProviderSettingsStore | None = None,
        credential_store: CredentialStore | None = None,
        key_registry: KeyRegistry | None = None,
        robot_diagnostics=None,
        robot_readiness=None,
        physical_controller=None,
        workspace_devices=None,
        project_catalog=None,
        session_history_root: Path | None = None,
        clock=time.monotonic,
        virtual: bool = False,
        port_candidates: int = 1,
    ) -> None:
        if type(port_candidates) is not int or not 1 <= port_candidates <= 10:
            raise ValueError('port candidates must be between 1 and 10')
        if host != "127.0.0.1":
            raise ValueError("TwinPulse local API may bind only to 127.0.0.1")
        if len(product_bootstrap_secret) < 32 or len(engine_bootstrap_secret) < 32:
            raise ValueError("Bootstrap secrets must contain at least 256 bits of material")
        if bootstrap_ttl_s <= 0 or session_idle_ttl_s <= 0 or session_absolute_ttl_s <= 0:
            raise ValueError("Authentication lifetimes must be positive")
        if broker.project_id != "default" and physical_controller is not None and workspace_devices is None:
            raise ValueError("named projects cannot share the default robot session archive")
        self.broker = broker
        self._virtual = virtual
        self.context_id = secrets.token_hex(16)
        self.workspace = None
        from .viewport_service import ViewportService
        self.viewport = ViewportService(broker, clock=clock)
        self.product_workflow = product_workflow
        if product_workflow is not None:
            from .generation_render_port import GenerationRenderPort
            product_workflow.render_review_port_factory = lambda owner, revision, current: GenerationRenderPort(
                broker, self.viewport, owner, revision, current=current)
        from .conversation_service import ConversationService
        self.conversation = ConversationService(product_workflow, product_workflow.conversation_path) if product_workflow is not None else None
        self._static_root = static_root.resolve() if static_root is not None else None
        self._supervisor_status_file = (
            supervisor_status_file.resolve() if supervisor_status_file is not None else None
        )
        if launcher_retry_file is not None and (
            self._supervisor_status_file is None
            or launcher_retry_file.parent.resolve() != self._supervisor_status_file.parent
        ):
            raise ValueError("launcher retry request must belong to the current launch directory")
        self._launcher_retry_file = launcher_retry_file
        self._launcher_retry_lock = RLock()
        if launcher_project_switch_file is not None and (
            self._supervisor_status_file is None
            or launcher_project_switch_file.parent.resolve() != self._supervisor_status_file.parent
        ):
            raise ValueError("project switch request must belong to the current launch directory")
        self._launcher_project_switch_file = launcher_project_switch_file
        if launcher_cancel_file is not None and (
            self._supervisor_status_file is None
            or launcher_cancel_file.parent.resolve() != self._supervisor_status_file.parent
        ):
            raise ValueError("startup cancel request must belong to the current launch directory")
        self._launcher_cancel_file = launcher_cancel_file
        if launcher_shutdown_file is not None and (
            self._supervisor_status_file is None
            or launcher_shutdown_file.parent.resolve() != self._supervisor_status_file.parent
        ):
            raise ValueError('shutdown request must belong to the current launch directory')
        self._launcher_shutdown_file = launcher_shutdown_file
        if engine_result_file is not None and (
            self._supervisor_status_file is None
            or engine_result_file.parent.resolve() != self._supervisor_status_file.parent
        ):
            raise ValueError("engine result must belong to the current launch directory")
        self._engine_result_file = engine_result_file
        if type(launcher_retry_remaining) is not int or not 0 <= launcher_retry_remaining <= 3:
            raise ValueError("launcher retry remaining is invalid")
        self._launcher_retry_remaining = launcher_retry_remaining
        self._provider_settings_store = provider_settings_store
        self._credential_store = credential_store
        self._key_registry = key_registry
        self._static_generation_preview_cache=None
        self._static_generation_preview_at=0
        self.viewport.static_preview_loader=self._retained_generation_preview
        self.workspace_devices = workspace_devices
        if workspace_devices is not None:
            robot_diagnostics = workspace_devices.diagnostics
            robot_readiness = workspace_devices.readiness
            physical_controller = workspace_devices.controller
        self.robot_diagnostics = robot_diagnostics
        self.robot_readiness = robot_readiness
        self._robot_start_lock = workspace_devices.lock if workspace_devices is not None else RLock()
        self.physical_controller = physical_controller
        self.project_catalog = project_catalog
        self.session_history_root = session_history_root.resolve() if session_history_root is not None else None
        self.manual_controller = ManualController()
        self.bedroom_review = BedroomReview(broker) if broker.project_id == "default" else UnavailableBedroomReview()
        self.room_localization = RoomLocalizationReview(self.session_history_root, broker.project_id)
        self.automatic_demo = AutomaticDemoService(self.session_history_root, broker.project_id)
        if workspace_devices is not None and physical_controller is not None:
            from .robot_geometry_evidence import load_geometry_evidence
            self.automatic_demo.geometry_loader = lambda _root: load_geometry_evidence(physical_controller.source_root)
        if self.product_workflow is not None and self.session_history_root is not None:
            from .scene_sensor_review import SceneSensorReview
            self.product_workflow.scene_sensor_review=SceneSensorReview(self.product_workflow,self.session_history_root)
        if self.product_workflow is not None:
            self.automatic_demo.room_loader=self.product_workflow.inspection_room
            self.automatic_demo.room_source_token=self.product_workflow.inspection_source_token
            self.automatic_demo.room_scene_loader=self.product_workflow.inspection_scene
        from .automatic_mission_service import AutomaticMissionService
        from .remote_observed_adapter import RemoteObservedFactory
        mission_factory=(RemoteObservedFactory(self.physical_controller,self.automatic_demo.root,broker.project_id,
                            source_root=getattr(self.physical_controller,'source_root',self.automatic_demo.root))
                         if self.physical_controller is not None else None)
        self.automatic_mission = AutomaticMissionService(self.automatic_demo,adapter_factory=mission_factory)
        if self.product_workflow is not None:
            self.automatic_mission.diagnostics=self.product_workflow._application.diagnostics
            if self.physical_controller is not None and workspace_devices is None:
                self.physical_controller.diagnostics=self.product_workflow._application.diagnostics
        if mission_factory is not None:
            mission_factory.reference_loader=self.automatic_mission._reference
            mission_factory.room_revision_loader=lambda:self.automatic_demo.photo_store.current(
                self.automatic_demo.room_loader(self.automatic_demo.root,broker.project_id))['effective_revision']
        from .automatic_comparison_service import AutomaticComparisonService
        self.automatic_comparison = AutomaticComparisonService(self.automatic_demo)
        from .chat_robot_preparation import ChatRobotPreparation
        self.chat_robot_preparation = ChatRobotPreparation(robot_diagnostics, physical_controller, robot_readiness,
            self._robot_start_lock, self._capture_robot_app_context)
        self.chat_robot_preparation.project_id = broker.project_id
        if self.product_workflow is not None:
            self.chat_robot_preparation.execution_diagnostics=self.product_workflow._application.diagnostics
            if self.robot_readiness is not None and workspace_devices is None:
                self.robot_readiness.execution_diagnostics=self.product_workflow._application.diagnostics
        self.chat_robot_preparation.external_busy=lambda:bool(self.automatic_mission.worker and self.automatic_mission.worker.is_alive())
        self.chat_robot_preparation.scene_edit_guard=self._scene_edit_physical_guard
        if self.product_workflow is not None:
            self.product_workflow.scene_edit_transaction.admission=self._scene_edit_admission
        if self.conversation is not None:
            self.conversation.robot_preparation = self.chat_robot_preparation
            from .chat_inspection import ChatInspection
            self.chat_inspection=ChatInspection(self.automatic_mission,self.product_workflow,
                self.chat_robot_preparation,self._robot_start_lock)
            self.conversation.inspection=self.chat_inspection
            from .chat_goal_navigation import ChatGoalNavigation
            self.conversation.navigation=ChatGoalNavigation(self.automatic_mission,self.product_workflow,
                self.chat_robot_preparation,self._robot_start_lock,self.chat_inspection)
            from .goal_demonstration import GoalDemonstration
            self.conversation.navigation.demonstration=GoalDemonstration(broker,self.conversation.navigation._scene,
                scene_guard_factory=lambda:self.automatic_mission._revision_guard(
                    self.automatic_demo.room_loader(self.automatic_demo.root,self.automatic_demo.project_id)))
        self._provider_settings_lock = RLock()
        self._clock = clock
        self._bootstrap_ttl_s = bootstrap_ttl_s
        self._product_owner_secret = product_bootstrap_secret
        bootstrap_expires_at = clock() + bootstrap_ttl_s
        self._bootstrap_expires_at = {
            "product": bootstrap_expires_at,
            "engine": bootstrap_expires_at,
        }
        self._bootstrap: dict[str, str | None] = {
            "product": product_bootstrap_secret,
            "engine": engine_bootstrap_secret,
        }
        self._product_bootstrap_tickets: dict[str, float] = {}
        self._session_idle_ttl_s = session_idle_ttl_s
        self._session_absolute_ttl_s = session_absolute_ttl_s
        self._sessions: dict[str, _Session] = {}
        self._session_lock = RLock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "TwinPulseLocal/1.0"
            sys_version = ""

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                owner._handle(self)

            def do_POST(self) -> None:  # noqa: N802
                owner._handle(self)

            def do_OPTIONS(self) -> None:  # noqa: N802
                owner._error(self, 405, "method_not_allowed", "Cross-origin preflight is not supported")

        self._httpd = None
        if not virtual:
            for offset in range(port_candidates if port else 1):
                candidate = 1024 + ((port - 1024 + offset) % (65536 - 1024)) if offset else port
                try:
                    self._httpd = ThreadingHTTPServer((host, candidate), Handler)
                    break
                except OSError as error:
                    if (offset + 1 == port_candidates or not port
                            or error.errno not in {13, 98, 10048, 10013}
                            and getattr(error, 'winerror', None) not in {10048, 10013}):
                        raise
        if self._httpd is not None:self._httpd.daemon_threads = True
        self._thread: Thread | None = None
        if workspace_devices is not None:
            workspace_devices.attach(self)

    def _retained_generation_preview(self):
        from copy import deepcopy
        from .generation_preview_restore import preview_binding,load_generation_preview
        if self.conversation is None or self._key_registry is None:return (None,None)
        with self.conversation._lock:
            generation=deepcopy(self.conversation._state.get('generation'))
        binding=preview_binding(generation)
        if binding is None:return (None,None)
        cache=self._static_generation_preview_cache
        if cache is not None and cache[0]==binding and (cache[1] is not None or
                time.monotonic()-self._static_generation_preview_at<1):return cache
        root=self._key_registry.settings.path.parent.resolve()/'provider-evidence'/'generation-store'
        capture=load_generation_preview(root,self.broker.project_id,generation)
        # Recheck under the conversation fence after disk reads. A cancelled
        # or replaced generation never adopts an old capture as its output.
        with self.conversation._lock:
            if preview_binding(self.conversation._state.get('generation'))!=binding:return (None,None)
            self._static_generation_preview_cache=(binding,capture)
            self._static_generation_preview_at=time.monotonic()
            return self._static_generation_preview_cache

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._httpd.serve_forever, name="TwinPulseLocalApi", daemon=True)
        self._thread.start()
        self.manual_controller.start_watchdog()

    def stop(self) -> None:
        if self.workspace is not None and self.workspace.root is self:
            self.workspace.close()
        navigation=getattr(self.conversation,'navigation',None)
        loop=getattr(navigation,'task_loop',None)
        if loop:loop.close()
        if navigation and navigation.demonstration:navigation.demonstration.close()
        self.chat_robot_preparation.close()
        self.automatic_comparison.close()
        self.automatic_mission.close()
        self.automatic_demo.close()
        if self.physical_controller is not None and self.workspace_devices is None:
            self.physical_controller.close()
        self.manual_controller.close()
        if self.product_workflow is not None:
            self.product_workflow.shutdown()
        if self.robot_diagnostics is not None and self.workspace_devices is None:
            self.robot_diagnostics.close()
        if self.robot_readiness is not None and self.workspace_devices is None:
            self.robot_readiness.close()
        if self.workspace_devices is not None and not self._virtual_context():
            self.workspace_devices.close()
        if self._thread is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)
        self._thread = None

    def _handle(self, request: BaseHTTPRequestHandler) -> None:
        if self.workspace is not None:
            return self.workspace.dispatch(request)
        request._twinpulse_context_id=self.context_id
        return self._handle_current(request)

    def _handle_current(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlsplit(request.path)
        if parsed.fragment or (parsed.query and not (
                request.command=='GET' and parsed.path=='/v1/product/diagnostics')):
            return self._error(request, 400, "url_data_forbidden", "Query and fragment data are forbidden")
        if not self._host_allowed(request.headers.get("Host", "")):
            return self._error(request, 403, "host_forbidden", "Host header is not allowed")
        if request.headers.get("Origin") not in (None, self.base_url, f"http://localhost:{self.port}"):
            return self._error(request, 403, "origin_forbidden", "Origin is not allowed")
        try:
            if request.command == "GET" and not parsed.path.startswith("/v1/"):
                return self._serve_static(request, parsed.path)
            if request.command == "POST" and parsed.path == "/v1/bootstrap/product/issue":
                return self._issue_product_bootstrap(request, self._read_json(request))
            if request.command == "POST" and parsed.path == "/v1/bootstrap":
                return self._bootstrap_session(request, self._read_json(request))
            if parsed.path.startswith("/v1/product/"):
                session = self._authenticate_product(request, require_csrf=request.command == "POST")
                if (os.environ.get('TWINPULSE_SIM_ONLY') == '1' and
                        parsed.path.startswith('/v1/product/robot/') and request.command == 'POST'):
                    return self._error(request, 409, 'sim_alpha_only', 'This release supports Isaac simulation.')
                # Classify only the two owned input endpoints after authentication.
                # Keep their parsed body for dispatch: an HTTP request body is a stream.
                gated_body = None
                stop_actions = {
                    '/v1/product/automatic-demo/control': {'cancel'},
                    "/v1/product/robot/physical/input": {"stop", "close", "finish_stop", "force_stop"},
                    "/v1/product/robot/controller/input": {"stop", "stop_all", "close", "lidar_stop"},
                    '/v1/product/conversation': {'cancel'},
                }
                if request.command == "POST" and parsed.path in stop_actions:
                    gated_body = self._read_json(request)
                stop_action = gated_body.get("action") if gated_body is not None else None
                stopping = (isinstance(stop_action, str) and stop_action in stop_actions.get(parsed.path, ())) or parsed.path in {'/v1/product/automatic-demo/mission-stop','/v1/product/conversation/robot/stop'}
                if (request.command != "GET"
                        and (self._launcher_project_switch_file is not None and self._launcher_project_switch_file.exists()
                             or self.workspace is not None and self.workspace.switching())
                        and not stopping
                        and parsed.path not in {"/v1/product/generation/cancel", "/v1/product/commands/cancel"}):
                    raise BrokerError(
                        "project_switch_pending",
                        "Project switch is pending; wait for the new session before changing this project",
                        status=409,
                    )
                runtime_status = self._supervisor_status().get("status")
                if (request.command != "GET" and parsed.path not in {
                        "/v1/product/runtime/retry", "/v1/product/runtime/cancel", '/v1/product/runtime/shutdown',
                        "/v1/product/conversation",
                        "/v1/product/provider-keys",
                        "/v1/product/generation/cancel", "/v1/product/commands/cancel",
                        '/v1/product/automatic-demo/start', '/v1/product/automatic-demo/control',
                        '/v1/product/automatic-demo/reopen',
                        '/v1/product/automatic-demo/rollback-photo',
                        '/v1/product/automatic-demo/mission-readiness', '/v1/product/automatic-demo/mission-start',
                        '/v1/product/automatic-demo/mission-stop',
                        '/v1/product/automatic-demo/comparison-start', '/v1/product/automatic-demo/comparison-stop',
                        '/v1/product/automatic-demo/comparison-reopen',
                    }
                        and not stopping and runtime_status in {"starting", "error"}):
                    code = "runtime_start_failed" if runtime_status == "error" else "runtime_not_ready"
                    raise BrokerError(code, "Launcher is not ready; review runtime status before editing or running", status=409)
                if request.command == "GET" and parsed.path == "/v1/product/session":
                    return self._json(request, 200, self._session_metadata(session))
                if request.command == "GET" and parsed.path == "/v1/product/state":
                    return self._json(request, 200, self.broker.public_state(session.session_id))
                if request.command == 'GET' and parsed.path=='/v1/product/scene-edit/transaction':
                    return self._json(request,200,self._workflow().scene_edit_transaction.snapshot(session.session_id))
                if request.command == 'GET' and parsed.path=='/v1/product/scene-edit/sensor-context':
                    adapter=self._workflow().scene_sensor_review
                    if adapter is None:raise BrokerError('scene_sensor_unavailable','Saved sensor history is unavailable.',status=409)
                    return self._json(request,200,adapter.context())
                if request.command == 'GET' and parsed.path=='/v1/product/scene-edit/sensor-surveys':
                    adapter=self._workflow().scene_sensor_review
                    if adapter is None:raise BrokerError('scene_sensor_unavailable','Saved sensor history is unavailable.',status=409)
                    return self._json(request,200,adapter.surveys.catalog())
                if request.command == 'GET' and parsed.path == '/v1/product/model-library':
                    from twinpulse_core.model_library import LIBRARY_VERSION, library_models
                    return self._json(request,200,dict(library_version=LIBRARY_VERSION,models=library_models(),
                        physical_authority=False))
                if request.command == 'GET' and parsed.path.startswith('/v1/product/diagnostics'):
                    if self.product_workflow is None:
                        raise BrokerError('diagnostics_unavailable', 'No active product project', status=409)
                    store = self.product_workflow._application.diagnostics
                    if parsed.path == '/v1/product/diagnostics':
                        try:
                            if len(parsed.query)>2048:raise ValueError('query exceeds limit')
                            query=parse_qs(parsed.query,keep_blank_values=True,max_num_fields=4,strict_parsing=True)
                            if set(query)-{'limit','q','status','cursor'} or any(len(v)!=1 for v in query.values()):
                                raise ValueError('unsupported or repeated parameter')
                            limit=query.get('limit',['50'])[0]
                            if not re.fullmatch(r'[0-9]{1,3}',limit):raise ValueError('invalid limit')
                        except (ValueError,TypeError):
                            raise BrokerError('diagnostic_query_invalid','Use a valid search, status and page cursor for this project',status=400)
                        from twinpulse_core.execution_diagnostics import DiagnosticQueryError
                        try:
                            value=store.list(int(limit),query=query.get('q',[''])[0],status=query.get('status',[''])[0],
                                             cursor=query.get('cursor',[None])[0])
                        except DiagnosticQueryError:
                            raise BrokerError('diagnostic_query_invalid','Use a valid search, status and page cursor for this project',status=400)
                        except (OSError,ValueError):
                            raise BrokerError('diagnostics_unavailable','Saved diagnostic storage is unavailable; no product operation was started',status=503)
                        return self._json(request, 200, value)
                    parts = parsed.path.removeprefix('/v1/product/diagnostics/').split('/')
                    try:
                        if len(parts) == 1:
                            value = store.detail(parts[0])
                        elif len(parts) == 2 and parts[1] == 'export':
                            value = store.export(parts[0])
                        elif len(parts) == 2 and parts[1] == 'graph':
                            if parsed.query:
                                raise BrokerError('diagnostic_query_invalid', 'Graph scope is fixed to the active project', status=400)
                            value = store.graph(parts[0])
                        else:
                            raise ValueError('invalid diagnostic route')
                    except (OSError, ValueError, KeyError):
                        raise BrokerError('execution_unknown', 'Execution is not available in the active project', status=404)
                    return self._json(request, 200, value)
                if request.command == 'GET' and parsed.path.startswith('/v1/product/simulation/request/'):
                    return self._json(request, 200, self.broker.request_outcome(
                        session.session_id, parsed.path.removeprefix('/v1/product/simulation/request/')))
                if request.command == "GET" and parsed.path == "/v1/product/viewport":
                    return self._json(request, 200, self.viewport.status())
                if request.command == 'GET' and parsed.path == '/v1/product/viewport/current':
                    state,content=self.viewport.image_packet()
                    request.send_response(200 if content is not None else 204)
                    request.send_header('Content-Type','image/jpeg')
                    request.send_header('Content-Length',str(len(content) if content is not None else 0))
                    request.send_header('X-TwinPulse-Viewport',json.dumps(state,ensure_ascii=True,separators=(',',':')))
                    request.send_header('X-TwinPulse-Context',self.context_id)
                    request.send_header('Cache-Control','no-store')
                    request.send_header('X-Content-Type-Options','nosniff')
                    request.end_headers()
                    if content is not None:
                        try:request.wfile.write(content)
                        except (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):request.close_connection=True
                    return
                if request.command == "GET" and parsed.path.startswith("/v1/product/viewport/frame/"):
                    content = self.viewport.image(parsed.path.removeprefix("/v1/product/viewport/frame/"))
                    request.send_response(200)
                    request.send_header("Content-Type", "image/jpeg")
                    request.send_header('X-TwinPulse-Context',self.context_id)
                    request.send_header("Content-Length", str(len(content)))
                    request.send_header("Cache-Control", "no-store")
                    request.send_header("X-Content-Type-Options", "nosniff")
                    request.end_headers()
                    try:
                        request.wfile.write(content)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        request.close_connection = True
                    return
                if request.command == 'GET' and parsed.path.startswith('/v1/product/viewport/preview/'):
                    content=self.viewport.preview_image(parsed.path.removeprefix('/v1/product/viewport/preview/'))
                    request.send_response(200)
                    request.send_header('X-TwinPulse-Context',self.context_id)
                    request.send_header('Content-Type','image/jpeg')
                    request.send_header('Content-Length',str(len(content)))
                    request.send_header('Cache-Control','no-store')
                    request.send_header('X-Content-Type-Options','nosniff')
                    request.end_headers()
                    try:request.wfile.write(content)
                    except (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):request.close_connection=True
                    return
                if request.command == "POST" and parsed.path == "/v1/product/viewport/camera":
                    return self._json(request, 202, self.viewport.camera_action(self._read_json(request)))
                if request.command == 'POST' and parsed.path == '/v1/product/viewport/observation':
                    return self._json(request,202,self.viewport.report_browser_failure(session.session_id,self._read_json(request)))
                if request.command == "GET" and parsed.path == "/v1/product/workflow":
                    return self._json(request, 200, self._workflow().snapshot())
                if request.command == 'POST' and parsed.path == '/v1/product/simulation/plan':
                    if self.conversation is not None and self.conversation.snapshot()['mode'] == 'REAL':
                        raise BrokerError('simulation_mode_required', 'Choose SIM in a new conversation before simulation')
                    return self._json(request, 200, self._workflow().simulation_plan(self._read_json(request)))
                if request.command == "GET" and parsed.path.startswith("/v1/product/conversation/image/"):
                    if self.conversation is None:
                        raise BrokerError("conversation_unavailable", "Conversation service is unavailable", status=503)
                    content = self.conversation.image(parsed.path.removeprefix("/v1/product/conversation/image/"))
                    request.send_response(200)
                    request.send_header('X-TwinPulse-Context',self.context_id)
                    request.send_header("Content-Type", "image/png")
                    request.send_header("Content-Length", str(len(content)))
                    request.send_header("Cache-Control", "no-store")
                    request.send_header("X-Content-Type-Options", "nosniff")
                    request.end_headers()
                    try:
                        request.wfile.write(content)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        request.close_connection = True
                    return
                if parsed.path == "/v1/product/conversation":
                    if self.conversation is None:
                        raise BrokerError("conversation_unavailable", "Conversation service is unavailable", status=503)
                    if request.command == "GET":
                        return self._json(request, 200, self.conversation.snapshot(session.session_id))
                    return self._json(request, 200, self.conversation.dispatch(gated_body if gated_body is not None else self._read_json(request, maximum=MAX_UPLOAD_JSON_BYTES), session.session_id))
                if request.command == 'POST' and parsed.path == '/v1/product/conversation/inspection/display':
                    body=self._read_json(request)
                    self._require_shape(body, {'descriptor','request_id'})
                    if not getattr(self,'chat_inspection',None):
                        raise BrokerError('inspection_unavailable','Inspection display is unavailable.',status=409)
                    return self._json(request,202,self.chat_inspection.display(session.session_id,
                        body['descriptor'],self._string(body,'request_id'),self.broker))
                if request.command == 'GET' and parsed.path == '/v1/product/conversation/robot/task-presence':
                    loop=getattr(getattr(self.conversation,'navigation',None),'task_loop',None)
                    return self._json(request,200,loop.touch(session.session_id) if loop else {'owned':False,'active':False})
                if request.command == 'POST' and parsed.path == '/v1/product/conversation/robot/stop':
                    body=self._read_json(request)
                    self._require_shape(body, {'force'})
                    if type(body['force']) is not bool:
                        raise BrokerError('chat_stop_invalid','Choose ordinary Stop or Force STOP.',status=400)
                    navigation=getattr(self.conversation,'navigation',None)
                    loop=getattr(navigation,'task_loop',None)
                    if loop and loop.active():
                        return self._json(request,200,loop.stop(session.session_id,body['force']))
                    goal=navigation.snapshot(session.session_id) if navigation else None
                    if goal and navigation.demonstration and navigation.demonstration.owner==session.session_id:
                        navigation.demonstration.stop(session.session_id)
                    current=goal.get('job') if goal else None
                    if current and current['state'] not in {'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}:
                        stopped=self.automatic_mission.stop(session.session_id,current['job_id'],body['force'])
                        return self._json(request,200,{'state':stopped['job']['state'],'stop_confirmed':False})
                    inspection=getattr(self,'chat_inspection',None)
                    if inspection and inspection.active(session.session_id):
                        return self._json(request,200,inspection.stop(session.session_id,body['force']))
                    return self._json(request,200,self.chat_robot_preparation.stop(session.session_id,force=body['force']))
                if request.command == "GET" and parsed.path == "/v1/product/projects":
                    if self.project_catalog is None:
                        raise BrokerError("project_catalog_unavailable", "Local project catalog is unavailable", status=409)
                    return self._json(request, 200, self.project_catalog.snapshot())
                if parsed.path == '/v1/product/robot/diagnostic-retention':
                    if self.workspace_devices is None:
                        raise BrokerError('device_diagnostics_unavailable', 'Shared device diagnostics are unavailable.', status=409)
                    if request.command == 'GET':
                        return self._json(request,200,self.workspace_devices.retain_diagnostics())
                    body=self._read_json(request)
                    self._require_shape(body, {'days'})
                    return self._json(request,200,self.workspace_devices.retain_diagnostics(days=body['days'],archive=True))
                if request.command == "POST" and parsed.path == "/v1/product/projects/create":
                    if self.project_catalog is None:
                        raise BrokerError("project_catalog_unavailable", "Local project catalog is unavailable", status=409)
                    body = self._read_json(request)
                    self._require_shape(body, {"project_id"})
                    project_id = self._string(body, "project_id")
                    try:
                        result = self.project_catalog.create_empty(project_id)
                    except FileExistsError as error:
                        raise BrokerError("project_exists", "Project name already exists", status=409) from error
                    except OSError as error:
                        raise BrokerError("project_store_unavailable", "Local project creation failed", status=409) from error
                    return self._json(request, 201, result)
                if request.command == "POST" and parsed.path == "/v1/product/projects/create-bedroom":
                    if self.project_catalog is None:
                        raise BrokerError("project_catalog_unavailable", "Local project catalog is unavailable", status=409)
                    body = self._read_json(request)
                    if set(body) not in ({"project_id"}, {"project_id", "request_id"}):
                        raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)
                    project_id = self._string(body, "project_id")
                    try:
                        result = self.project_catalog.create_from_preserved_bedroom(
                            project_id, self._string(body, "request_id") if "request_id" in body else None)
                    except FileExistsError as error:
                        raise BrokerError("project_exists", "Project name already exists", status=409) from error
                    except (OSError, ValueError) as error:
                        raise BrokerError("project_source_unavailable", "Saved room project could not be prepared; inspect its local source", status=409) from error
                    return self._json(request, 201, result)
                if request.command == "POST" and parsed.path == "/v1/product/projects/create-manual-room":
                    if self.project_catalog is None:
                        raise BrokerError("project_catalog_unavailable", "Local project catalog is unavailable", status=409)
                    body = self._read_json(request, maximum=MAX_UPLOAD_JSON_BYTES)
                    expected = {"project_id", "request_id", "prompt", "media_type",
                                "photo_base64", "width_m", "length_m", "wall_height_m",
                                "include_burger_visual"}
                    if set(body) not in (expected, expected | {"furniture"}):
                        raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)
                    encoded = body["photo_base64"]
                    if not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024:
                        raise BrokerError("image_size_invalid", "Room photo exceeds the upload limit", status=413)
                    try:
                        photo = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError) as error:
                        raise BrokerError("image_base64_invalid", "Room photo encoding is invalid", status=400) from error
                    try:
                        result = self.project_catalog.create_from_manual_room(
                            self._string(body, "project_id"), request_id=self._string(body, "request_id"),
                            prompt=self._string(body, "prompt"), photo=photo,
                            media_type=self._string(body, "media_type"), width_m=body["width_m"],
                            length_m=body["length_m"], wall_height_m=body["wall_height_m"],
                            include_burger_visual=body["include_burger_visual"],
                            furniture=body.get("furniture", ()),
                        )
                    except FileExistsError as error:
                        raise BrokerError("project_exists", "Project name already exists", status=409) from error
                    except ValueError as error:
                        raise BrokerError("manual_room_invalid", "Room photo or entered dimensions are invalid", status=400) from error
                    except OSError as error:
                        raise BrokerError("project_store_unavailable", "Local room creation failed", status=409) from error
                    return self._json(request, 201, result)
                if request.command == "POST" and parsed.path == "/v1/product/projects/recover-bedroom":
                    if self.project_catalog is None:
                        raise BrokerError("project_catalog_unavailable", "Local project catalog is unavailable", status=409)
                    body = self._read_json(request)
                    self._require_shape(body, {"project_id", "request_id", "recovery_fingerprint"})
                    try:
                        result = self.project_catalog.create_from_preserved_bedroom(
                            self._string(body, "project_id"), self._string(body, "request_id"),
                            self._string(body, "recovery_fingerprint"))
                    except FileExistsError as error:
                        raise BrokerError("project_exists", "Project changed or name already exists", status=409) from error
                    except (OSError, ValueError) as error:
                        raise BrokerError("project_recovery_unavailable", "Incomplete project could not be preserved and recreated", status=409) from error
                    return self._json(request, 201, result)
                if request.command == "POST" and parsed.path == "/v1/product/projects/switch":
                    body = self._read_json(request)
                    self._require_shape(body, {"project_id"})
                    return self._json(request, 202, self._request_project_switch(
                        self._string(body, "project_id"), session.session_id,
                    ))
                if request.command == "POST" and parsed.path == "/v1/product/project/continue-room":
                    self._require_shape(self._read_json(request), set())
                    return self._json(request, 200, self._workflow().continue_room_recipe())
                if request.command == "POST" and parsed.path == "/v1/product/project/resume-scene":
                    body = self._read_json(request)
                    self._require_shape(body, {"project_id", "expected_scene_revision", "expected_input_revision"})
                    return self._json(request, 200, self._workflow().resume_saved_scene(
                        self._string(body, "project_id"),
                        self._string(body, "expected_scene_revision"),
                        self._string(body, "expected_input_revision"),
                    ))
                if request.command == "POST" and parsed.path == "/v1/product/project/reattach-source":
                    body = self._read_json(request, maximum=MAX_UPLOAD_JSON_BYTES)
                    self._require_shape(body, {"project_id", "expected_scene_revision", "expected_input_revision",
                                               "name", "media_type", "content_base64"})
                    return self._json(request, 200, self._workflow().reattach_saved_source(
                        self._string(body, "project_id"), self._string(body, "expected_scene_revision"),
                        self._string(body, "expected_input_revision"), body["name"],
                        body["media_type"], body["content_base64"],
                    ))
                if request.command == "GET" and parsed.path == "/v1/product/runtime":
                    return self._json(request, 200, self._supervisor_status())
                if request.command == "GET" and parsed.path == "/v1/product/runtime/diagnostics":
                    return self._json(request, 200, self._runtime_diagnostics())
                if request.command == "POST" and parsed.path == "/v1/product/runtime/retry":
                    self._require_shape(self._read_json(request), set())
                    return self._json(request, 202, self._request_launcher_retry())
                if request.command == "POST" and parsed.path == "/v1/product/runtime/cancel":
                    self._require_shape(self._read_json(request), set())
                    return self._json(request, 202, self._request_startup_cancel())
                if request.command == 'POST' and parsed.path == '/v1/product/runtime/shutdown':
                    self._require_shape(self._read_json(request), set())
                    return self._json(request, 202, self._request_shutdown())
                if request.command == "GET" and parsed.path == "/v1/product/robot/report":
                    return self._json(request, 200, self._workflow().robot_report_snapshot())
                if request.command == "GET" and parsed.path == "/v1/product/robot/diagnostics":
                    return self._json(request, 200, self._diagnostics().snapshot(session.session_id))
                if request.command == "GET" and parsed.path == "/v1/product/robot/readiness":
                    return self._json(request, 200, self._readiness().snapshot(session.session_id))
                if request.command == "GET" and parsed.path == "/v1/product/robot/controller":
                    return self._json(request, 200, self.manual_controller.snapshot(session.session_id))
                if request.command == "GET" and parsed.path == "/v1/product/robot/physical":
                    return self._json(request, 200, self.physical_controller.snapshot(session.session_id)
                        if self.physical_controller else {"state":"UNAVAILABLE","busy":False})
                if request.command == "POST" and parsed.path == "/v1/product/robot/physical/evidence/resume":
                    if self.physical_controller is None:
                        raise BrokerError('physical_unavailable','Physical controller not configured',status=409)
                    body = self._read_json(request)
                    self._require_shape(body, {'job_id','request_id'})
                    with self._robot_start_lock:
                        self._scene_edit_physical_guard()
                        if self.robot_readiness is not None and self.robot_readiness.blocks_robot_operation():
                            raise BrokerError('readiness_busy_or_uncertain','Stationary collection is active or uncertain',status=409)
                        if self.robot_diagnostics is not None and self.robot_diagnostics._running():
                            raise BrokerError('robot_operation_busy','Read-only check is active',status=409)
                        result=self.physical_controller.resume_evidence(session.session_id,self._string(body,'job_id'),self._string(body,'request_id'))
                    return self._json(request,202,result)
                if request.command == "GET" and parsed.path.startswith("/v1/product/robot/physical/evidence/review/"):
                    if (self.physical_controller is None or self.session_history_root is None or parsed.query
                            or self.session_history_root != self.physical_controller.root.resolve()):
                        raise BrokerError('evidence_review_unavailable','Saved evidence review unavailable',status=409)
                    from .offline_evidence_review import review_saved_evidence
                    from .session_history import review_project_session
                    job_id=parsed.path.removeprefix('/v1/product/robot/physical/evidence/review/')
                    if re.fullmatch('[a-f0-9]{32}',job_id) is None:
                        raise BrokerError('evidence_job_invalid','Exact saved job ID required',status=400)
                    review_project_session(self.session_history_root,self.broker.project_id,job_id)
                    return self._json(request,200,review_saved_evidence(self.physical_controller.root,job_id))
                if request.command == "GET" and (parsed.path == "/v1/product/robot/physical/history" or parsed.path.startswith("/v1/product/robot/physical/history/")):
                    from .session_history import list_sessions, review_session
                    if not self.physical_controller or parsed.query:
                        raise BrokerError('session_history_unavailable','Read-only session history unavailable',status=409)
                    prefix='/v1/product/robot/physical/history'
                    return self._json(request,200,list_sessions(self.physical_controller.root) if parsed.path==prefix
                                      else review_session(self.physical_controller.root,parsed.path[len(prefix)+1:]))
                if request.command == "GET" and (parsed.path == "/v1/product/sessions" or parsed.path.startswith("/v1/product/sessions/")):
                    from .session_history import list_project_sessions, review_project_session
                    if self.session_history_root is None or parsed.query:
                        raise BrokerError('session_history_unavailable','Read-only session history unavailable',status=409)
                    prefix='/v1/product/sessions'
                    return self._json(request,200,list_project_sessions(self.session_history_root,self.broker.project_id)
                                      if parsed.path==prefix else review_project_session(
                                          self.session_history_root,self.broker.project_id,parsed.path[len(prefix)+1:]))
                if request.command == "GET" and parsed.path == "/v1/product/scan-review":
                    return self._json(request, 200, self._workflow().scan_review.snapshot())
                if request.command == "GET" and parsed.path == "/v1/product/room-localization":
                    return self._json(request, 200, self.room_localization.snapshot())
                if request.command == 'GET' and parsed.path == '/v1/product/automatic-demo':
                    if parsed.query:raise BrokerError('automatic_request_invalid','Query parameters are not supported',status=400)
                    return self._json(request,200,self.automatic_demo.snapshot(session.session_id))
                if request.command == 'GET' and parsed.path == '/v1/product/automatic-demo/mission':
                    if parsed.query:raise BrokerError('mission_request_invalid','Query parameters are not supported',status=400)
                    return self._json(request,200,self.automatic_mission.snapshot(session.session_id))
                if request.command == 'GET' and parsed.path == '/v1/product/automatic-demo/comparison':
                    if parsed.query:raise BrokerError('comparison_request_invalid','Query parameters are not supported',status=400)
                    return self._json(request,200,self.automatic_comparison.snapshot(session.session_id))
                if request.command == 'GET' and parsed.path == '/v1/product/automatic-demo/maps':
                    if parsed.query:raise BrokerError('automatic_request_invalid','Query parameters are not supported',status=400)
                    return self._json(request,200,self.automatic_demo.maps())
                if request.command == "GET" and parsed.path == "/v1/product/scan-review/export":
                    return self._json(request, 200, self._workflow().scan_review.export_review())
                if request.command == "GET" and parsed.path == "/v1/product/native-scan":
                    return self._json(request, 200, self._workflow().native_scan_review.snapshot())
                if request.command == "GET" and parsed.path == "/v1/product/native-scan/reference":
                    return self._json(request, 200, self._workflow().native_scan_review.world_reference())
                if request.command == "GET" and parsed.path == "/v1/product/native-scan/export":
                    return self._json(request, 200, self._workflow().native_scan_review.export_bundle())
                if request.command == "GET" and parsed.path == "/v1/product/provider-settings":
                    return self._json(request, 200, self._provider_settings())
                if request.command == "GET" and parsed.path == "/v1/product/provider-keys":
                    return self._json(request, 200, self._provider_keys())
                body = gated_body if gated_body is not None else self._read_json(
                    request,
                    maximum=(MAX_UPLOAD_JSON_BYTES if parsed.path == "/v1/product/input" else
                             10 * 1024 * 1024 if parsed.path == "/v1/product/native-scan/import" else
                             22 * 1024 * 1024 if parsed.path == "/v1/product/scan-review/archive-import" else
                             5 * 1024 * 1024 if parsed.path == "/v1/product/bedroom/offline-acceptance-import" else
                             8 * 1024 * 1024 if parsed.path == "/v1/product/scan-review/import" else MAX_JSON_BYTES),
                )
                if request.command == "POST" and parsed.path == "/v1/product/native-scan/import":
                    self._require_shape(body, {"bundle_text"})
                    return self._json(request, 200, self._workflow().native_scan_review.import_bundle(body["bundle_text"]))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/rehearse":
                    self._require_shape(body, {"revision", "scenario", "acknowledged"})
                    return self._json(request, 200, self.bedroom_review.rehearse(
                        self._string(body,"revision"),self._string(body,"scenario"),body["acknowledged"]))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/offline-acceptance":
                    self._require_shape(body, {"revision", "acknowledged"})
                    return self._json(request, 200, self.bedroom_review.offline_acceptance(
                        self._string(body,"revision"),body["acknowledged"]))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/offline-acceptance-export":
                    self._require_shape(body, {"revision", "acknowledged", "acceptance_revision"})
                    return self._json(request, 200, self.bedroom_review.export_offline_acceptance(
                        self._string(body,"revision"),body["acknowledged"],self._string(body,"acceptance_revision")))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/offline-acceptance-import":
                    self._require_shape(body, {"revision", "acknowledged", "bundle_text"})
                    return self._json(request, 200, self.bedroom_review.reopen_offline_acceptance(
                        self._string(body,"revision"),body["acknowledged"],body["bundle_text"]))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/rehearse-export":
                    self._require_shape(body, {"revision", "scenario", "acknowledged", "record_revision"})
                    return self._json(request, 200, self.bedroom_review.export_rehearsal(
                        self._string(body,"revision"),self._string(body,"scenario"),body["acknowledged"],
                        self._string(body,"record_revision")))
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/compare':
                    self._require_shape(body, {'revision','acknowledged'})
                    return self._json(request,200,self.bedroom_review.compare(self._string(body,'revision'),body['acknowledged']))
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/compare-export':
                    self._require_shape(body, {'revision','acknowledged','comparison_revision'})
                    return self._json(request,200,self.bedroom_review.export_comparison(
                        self._string(body,'revision'),body['acknowledged'],self._string(body,'comparison_revision')))
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/evaluate':
                    self._require_shape(body, {'revision','acknowledged'})
                    return self._json(request,200,self.bedroom_review.evaluate(self._string(body,'revision'),body['acknowledged']))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/prepare":
                    self._require_shape(body, set())
                    return self._json(request, 200, self.bedroom_review.prepare())
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/geometry-evidence':
                    self._require_shape(body,set())
                    return self._json(request,200,self.bedroom_review.geometry_evidence())
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/goal-preview':
                    self._require_shape(body,{'revision','evidence_revision','goal','reference'})
                    return self._json(request,200,self.bedroom_review.goal_preview(
                        self._string(body,'revision'),self._string(body,'evidence_revision'),body['goal'],body['reference']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/observation-map':
                    self._require_shape(body,{'job_id'})
                    return self._json(request,200,self.room_localization.observation_map(self._string(body,'job_id')))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/start':
                    self._require_shape(body,{'job_id','reference_map_id'}|({'photo_policy'} if 'photo_policy' in body else set())|({'replay_mode'} if 'replay_mode' in body else set()))
                    with self._robot_start_lock:
                        self._scene_edit_physical_guard()
                        result=self.automatic_demo.start(session.session_id,self._string(body,'job_id'),
                            body['reference_map_id'],body.get('photo_policy','disabled'),body.get('replay_mode','as_fast'))
                    return self._json(request,202,result)
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/mission-readiness':
                    self._require_shape(body,{'map_id'})
                    return self._json(request,200,self.automatic_mission.readiness(None if body['map_id'] is None else self._string(body,'map_id')))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/comparison-start':
                    self._require_shape(body,{'start','goal'})
                    if self.automatic_mission.worker and self.automatic_mission.worker.is_alive():
                        raise BrokerError('mission_busy','Wait for the current mission to finish',status=409)
                    return self._json(request,202,self.automatic_comparison.start(session.session_id,body['start'],body['goal']))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/comparison-stop':
                    self._require_shape(body,{'job_id'})
                    return self._json(request,200,self.automatic_comparison.stop(session.session_id,self._string(body,'job_id')))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/comparison-reopen':
                    self._require_shape(body,{'job_id','revision'})
                    return self._json(request,200,self.automatic_comparison.reopen(session.session_id,self._string(body,'job_id'),self._string(body,'revision')))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/mission-start':
                    self._require_shape(body,{'map_id','goal','photo_policy'} if 'photo_policy' in body else {'map_id','goal'})
                    with self._robot_start_lock:
                        self._scene_edit_physical_guard()
                        if self.robot_readiness is not None and self.robot_readiness.blocks_robot_operation():
                            raise BrokerError('readiness_busy_or_uncertain','Stationary collection is active or uncertain; REAL mission admission remains locked.',status=409)
                        result=self.automatic_mission.start(session.session_id,None if body['map_id'] is None else
                            self._string(body,'map_id'),body['goal'],body.get('photo_policy','align_only'))
                    return self._json(request,202,result)
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/mission-stop':
                    self._require_shape(body,{'job_id','force'})
                    if type(body['force']) is not bool:raise BrokerError('mission_request_invalid','Exact stop mode required',status=400)
                    return self._json(request,200,self.automatic_mission.stop(session.session_id,self._string(body,'job_id'),body['force']))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/mission-preview3d':
                    self._require_shape(body,{'job_id','revision','request_id'})
                    return self._json(request,202,self.automatic_mission.preview(session.session_id,
                        self._string(body,'job_id'),self._string(body,'revision'),self._string(body,'request_id'),self.broker))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/rollback-photo':
                    self._require_shape(body,{'job_id','revision'})
                    return self._json(request,200,self.automatic_demo.rollback_photo(session.session_id,
                        self._string(body,'job_id'),self._string(body,'revision')))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/control':
                    self._require_shape(body,{'job_id','action','sequence'})
                    return self._json(request,200,self.automatic_demo.control(session.session_id,
                        self._string(body,'job_id'),self._string(body,'action'),body['sequence']))
                if request.command == 'POST' and parsed.path == '/v1/product/automatic-demo/reopen':
                    self._require_shape(body,{'map_id'})
                    return self._json(request,200,self.automatic_demo.reopen(session.session_id,self._string(body,'map_id')))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/compare-model':
                    self._require_shape(body,{'revision','job_id','observation_revision'})
                    return self._json(request,200,self.room_localization.compare_model(
                        self._string(body,'revision'),self._string(body,'job_id'),self._string(body,'observation_revision')))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/sensor-map':
                    self._require_shape(body,{'job_id','observation_revision','query_job_id','frame'})
                    return self._json(request,200,self.room_localization.locate_sensor_map(
                        self._string(body,'job_id'),self._string(body,'observation_revision'),self._string(body,'query_job_id'),body['frame']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/photo-link-context':
                    self._require_shape(body,{'revision','sensor_revision'})
                    return self._json(request,200,self.room_localization.photo_link_context(self._string(body,'revision'),self._string(body,'sensor_revision')))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/photo-link':
                    self._require_shape(body,{'revision','sensor_revision','context_revision','pairs'})
                    return self._json(request,200,self.room_localization.link_photo(self._string(body,'revision'),
                        self._string(body,'sensor_revision'),self._string(body,'context_revision'),body['pairs']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/photo-link-goal':
                    self._require_shape(body,{'revision','link_revision','goal'})
                    return self._json(request,200,self.room_localization.photo_link_goal(
                        self._string(body,'revision'),self._string(body,'link_revision'),body['goal']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/review':
                    self._require_shape(body,{'revision','job_id','frame'})
                    return self._json(request,200,self.room_localization.analyse(
                        self._string(body,'revision'),self._string(body,'job_id'),body['frame']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/invalidate':
                    self._require_shape(body,set())
                    return self._json(request,200,self.room_localization.invalidate())
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/goal':
                    self._require_shape(body,{'revision','result_revision','epoch','goal'})
                    return self._json(request,200,self.room_localization.goal(
                        self._string(body,'revision'),self._string(body,'result_revision'),body['epoch'],body['goal']))
                if request.command == 'POST' and parsed.path == '/v1/product/room-localization/preview3d':
                    self._require_shape(body,{'revision','result_revision','request_id'})
                    visual=self.room_localization.visual_descriptor(self._string(body,'revision'),self._string(body,'result_revision'))
                    return self._json(request,202,self.bedroom_review.build(session.session_id,
                        body['revision'],True,self._string(body,'request_id'),localization=visual))
                if request.command == 'POST' and parsed.path == '/v1/product/bedroom/replay':
                    self._require_shape(body, {'revision','acknowledged','request_id','replay'})
                    if type(body['replay']) is not dict:
                        raise BrokerError('invalid_replay','Replay descriptor required',status=400)
                    return self._json(request, 202, self.bedroom_review.build(session.session_id,
                        self._string(body,'revision'),body['acknowledged'],self._string(body,'request_id'),body['replay']))
                if request.command == "POST" and parsed.path == "/v1/product/bedroom/build":
                    self._require_shape(body, {"revision", "acknowledged", "request_id"})
                    return self._json(request, 202, self.bedroom_review.build(session.session_id,
                        self._string(body, "revision"), body["acknowledged"], self._string(body, "request_id")))
                if request.command == "POST" and parsed.path == "/v1/product/robot/preflight":
                    self._require_shape(body, set())
                    return self._json(request, 200, self._diagnostics().preflight(session.session_id))
                if request.command == "POST" and parsed.path == "/v1/product/robot/readiness/start":
                    self._require_shape(body, {'request_id','confirmed_no_motion_deployment','expires_at_ms'})
                    with self._robot_start_lock:
                        self._scene_edit_physical_guard()
                        if (self.physical_controller is not None
                                and (self.physical_controller.snapshot(session.session_id)['busy']
                                     or self._robot_transfer_busy())):
                            raise BrokerError('robot_operation_busy', 'Another robot operation is active', status=409)
                        if self.robot_diagnostics is not None and self.robot_diagnostics._running():
                            raise BrokerError('robot_operation_busy', 'Read-only check is active', status=409)
                        result = self._readiness().start(session.session_id, self._string(body,'request_id'),
                            body['confirmed_no_motion_deployment'], body['expires_at_ms'],
                            app_context=self._capture_robot_app_context(),project_id=self.broker.project_id)
                    return self._json(request, 202, result)
                if request.command == "POST" and parsed.path == "/v1/product/robot/readiness/clear-uncertain":
                    self._require_shape(body, {'confirmed_powered_off','expires_at_ms'})
                    return self._json(request, 200, self._readiness().clear_uncertain(
                        session.session_id, body['confirmed_powered_off'], body['expires_at_ms']))
                if request.command == "POST" and parsed.path in {"/v1/product/robot/physical/start", "/v1/product/robot/physical/input", "/v1/product/robot/physical/mission"}:
                    if self.physical_controller is None:
                        raise BrokerError('physical_unavailable','Physical controller not configured',status=409)
                    if parsed.path.endswith(('/start','/mission')):
                        mission=parsed.path.endswith('/mission')
                        self._require_shape(body, {'scope' if mission else 'mode','request_id','confirmed','expires_at_ms'})
                        expires=body['expires_at_ms']
                        if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-time.time()*1000<=2000:
                            raise BrokerError('physical_start_expired','Fresh operator request required',status=409)
                        # Historical App reference only, never a room-to-odom transform.
                        app_context=self._capture_robot_app_context()
                        with self._robot_start_lock:
                            self._scene_edit_physical_guard()
                            if self.robot_readiness is not None and self.robot_readiness.blocks_robot_operation():
                                raise BrokerError('readiness_busy_or_uncertain', 'No-motion collection is active or uncertain', status=409)
                            if self.robot_diagnostics is not None and self.robot_diagnostics._running():
                                raise BrokerError('robot_operation_busy', 'Read-only check is active', status=409)
                            self.room_localization.invalidate()  # Never carry a saved pose into a new live session.
                            result = self.physical_controller.start(session.session_id,
                                'mission' if mission else self._string(body,'mode'),self._string(body,'request_id'),body['confirmed'],
                                scope=body['scope'] if mission else None,app_context=app_context)
                        return self._json(request,202,result)
                    self._require_shape(body, {'job_id','sequence','action','expires_at_ms'})
                    return self._json(request,200,self.physical_controller.input(session.session_id,
                        self._string(body,'job_id'),body['sequence'],self._string(body,'action'),body['expires_at_ms']))
                if request.command == "POST" and parsed.path == "/v1/product/robot/controller/session":
                    self._require_shape(body, {"mode", "confirmed"})
                    return self._json(request, 200, self.manual_controller.begin(
                        session.session_id, body["mode"], body["confirmed"]))
                if request.command == "POST" and parsed.path == "/v1/product/robot/controller/input":
                    self._require_shape(body, {"session_id", "sequence", "action", "expires_at_ms"})
                    return self._json(request, 200, self.manual_controller.command(
                        session.session_id, self._string(body, "session_id"), body["sequence"],
                        body["action"], body["expires_at_ms"]))
                if request.command == "POST" and parsed.path == "/v1/product/robot/check":
                    self._require_shape(body, {"start_token", "confirmed_read_only"})
                    with self._robot_start_lock:
                        self._scene_edit_physical_guard()
                        if self.robot_readiness is not None and self.robot_readiness.blocks_read_only_observation():
                            raise BrokerError('readiness_busy_or_uncertain', 'No-motion collection is active', status=409)
                        if self.physical_controller is not None and self.physical_controller.snapshot(session.session_id)['busy']:
                            raise BrokerError('robot_operation_busy','Wait for the active physical operation before observing board ports.',status=409)
                        result = self._diagnostics().start(
                            session.session_id, self._string(body, "start_token"), body["confirmed_read_only"])
                    return self._json(request, 202, result)
                if request.command == "POST" and parsed.path in {
                    "/v1/product/derived-review/adopt", "/v1/product/derived-review/restore",
                }:
                    restore = parsed.path.endswith("/restore")
                    fields = {"input_revision", "source_revision"}
                    self._require_shape(body, fields if restore else fields | {"workspace_revision"})
                    return self._json(request, 200, self._workflow().adopt_derived_review(
                        self._string(body, "input_revision"), self._string(body, "source_revision"),
                        None if restore else self._string(body, "workspace_revision"), restore=restore))
                if request.command == "POST" and parsed.path == "/v1/product/scene-edit/preview":
                    self._require_shape(body, {"operation_id", "mode", "target_call_id", "tool_call"})
                    if body["target_call_id"] is not None and type(body["target_call_id"]) is not str:
                        raise BrokerError("scene_edit_invalid", "Target call id must be text or null", status=400)
                    if body["tool_call"] is not None and type(body["tool_call"]) is not dict:
                        raise BrokerError("scene_edit_invalid", "Tool call must be an object or null", status=400)
                    return self._json(request, 200, self._workflow().preview_scene_edit(
                        operation_id=self._string(body, "operation_id"), mode=self._string(body, "mode"),
                        target_call_id=body["target_call_id"], tool_call=body["tool_call"]))
                if request.command == "POST" and parsed.path == "/v1/product/scene-edit/context":
                    self._require_shape(body, {"request_text", "selected_call_id"})
                    if body["selected_call_id"] is not None and type(body["selected_call_id"]) is not str:
                        raise BrokerError("scene_edit_context_invalid", "Selected call id must be text or null", status=400)
                    return self._json(request, 200, self._workflow().scene_edit_context(
                        self._string(body, "request_text"), body["selected_call_id"]))
                if request.command == "POST" and parsed.path == "/v1/product/scene-edit/proposal-preview":
                    self._require_shape(body, {"operation_id", "request_text", "selected_call_id",
                                               "expected_revision", "proposal"})
                    if body["selected_call_id"] is not None and type(body["selected_call_id"]) is not str:
                        raise BrokerError("scene_edit_proposal_invalid", "Selected call id must be text or null", status=400)
                    if type(body["proposal"]) is not dict:
                        raise BrokerError("scene_edit_proposal_invalid", "Proposal must be an object", status=400)
                    return self._json(request, 200, self._workflow().preview_scene_edit_proposal(
                        operation_id=self._string(body, "operation_id"),
                        request_text=self._string(body, "request_text"),
                        selected_call_id=body["selected_call_id"],
                        expected_revision=self._string(body, "expected_revision"),
                        proposal=body["proposal"]))
                if request.command == "POST" and parsed.path == "/v1/product/scene-edit/apply":
                    if body.get('schema_version')=='scene-edit-apply-2.0':
                        if body.get('action')=='recover':
                            self._require_shape(body,{'schema_version','action'})
                            return self._json(request,202,self._workflow().scene_edit_transaction.recover(session.session_id))
                        if set(body) not in ({'schema_version','operation','preview_digest'},
                                {'schema_version','operation','preview_digest','sensor_binding'}):
                            raise BrokerError('request_shape_invalid','Scene edit Apply fields are invalid.',status=400)
                        if not isinstance(body['operation'],dict):
                            raise BrokerError('scene_edit_invalid','Preview operation must be an object.',status=400)
                        return self._json(request,202,self._workflow().scene_edit_transaction.start(session.session_id,
                            body['operation'],self._string(body,'preview_digest'),sensor_binding=body.get('sensor_binding')))
                    self._require_shape(body, {"operation", "preview_digest"})
                    if type(body["operation"]) is not dict:
                        raise BrokerError("scene_edit_invalid", "Preview operation must be an object", status=400)
                    return self._json(request, 200, self._workflow().apply_scene_edit(
                        body["operation"], self._string(body, "preview_digest")))
                if request.command == "POST" and parsed.path == "/v1/product/presentation":
                    self._require_shape(body, {"expected_source_scene_revision", "presentation"})
                    return self._json(request, 200, self._workflow().save_presentation(
                        self._string(body, "expected_source_scene_revision"), body["presentation"]))
                if request.command == "POST" and parsed.path == "/v1/product/native-scan/frame":
                    self._require_shape(body, {"workspace_revision", "frame_index"})
                    return self._json(request, 200, self._workflow().native_scan_review.select_frame(body["frame_index"], body["workspace_revision"]))
                if request.command == "POST" and parsed.path == "/v1/product/native-scan/3d-export":
                    self._require_shape(body, {"workspace_revision", "frame_index"})
                    return self._json(request, 200, self._workflow().native_scan_review.export_3d(body["frame_index"], body["workspace_revision"]))
                if request.command == "POST" and parsed.path == "/v1/product/native-scan/registration":
                    self._require_shape(body, {"workspace_revision", "frame_index", "reference_text"})
                    return self._json(request, 200, self._workflow().native_scan_review.propose_registration(body["workspace_revision"], body["frame_index"], body["reference_text"]))
                if request.command == "POST" and parsed.path.startswith("/v1/product/scan-review/"):
                    review = self._workflow().scan_review
                    action = parsed.path.removeprefix("/v1/product/scan-review/")
                    if action == "archive-export":
                        self._require_shape(body, {"workspace_revision"})
                        return self._json(request, 200, review.download_archive(body["workspace_revision"]))
                    if action == "archive-import":
                        self._require_shape(body, {"workspace_revision", "archive_text"})
                        return self._json(request, 200, review.import_archive(body["workspace_revision"], body["archive_text"]))
                    if action == "import":
                        self._require_shape(body, {"bundle_text"})
                        return self._json(request, 200, review.import_bundle(body["bundle_text"]))
                    if action == "propose":
                        self._require_shape(body, {"workspace_revision", "object_id", "pairs"})
                        return self._json(request, 200, review.propose(body["workspace_revision"], body["object_id"], body["pairs"]))
                    if action == "apply":
                        self._require_shape(body, {"workspace_revision", "proposal_revision"})
                        return self._json(request, 200, review.apply(body["workspace_revision"], body["proposal_revision"]))
                    if action == "undo":
                        self._require_shape(body, {"workspace_revision", "edit_revision"})
                        return self._json(request, 200, review.undo(body["workspace_revision"], body["edit_revision"]))
                    if action == "compare":
                        self._require_shape(body, {"workspace_revision", "conditions_revision", "baseline", "candidate"})
                        return self._json(request, 200, review.compare(body["workspace_revision"], body["conditions_revision"], body["baseline"], body["candidate"]))
                    if action == "map-propose":
                        self._require_shape(body, {"workspace_revision"})
                        return self._json(request, 200, review.propose_map(body["workspace_revision"]))
                    if action == "map-apply":
                        self._require_shape(body, {"workspace_revision", "proposal_revision"})
                        return self._json(request, 200, review.apply_map(body["workspace_revision"], body["proposal_revision"]))
                    raise ValueError("unsupported offline review action")
                if parsed.path == "/v1/product/input":
                    return self._json(request, 200, self._workflow().select_input(body))
                if request.command == "POST" and parsed.path == "/v1/product/robot/report":
                    self._require_shape(body, {"report"})
                    return self._json(request, 200, self._workflow().import_robot_report(body["report"]))
                if parsed.path == "/v1/product/generation":
                    self._require_shape(body, set())
                    return self._json(request, 202, self._workflow().start_generation(owner=session.session_id))
                if parsed.path == "/v1/product/provider-settings":
                    return self._json(request, 200, self._save_provider_settings(body))
                if parsed.path == "/v1/product/provider-keys":
                    return self._json(request, 200, self._provider_keys(body))
                if parsed.path == "/v1/product/generation/cancel":
                    self._require_shape(body, set())
                    return self._json(request, 200, self._workflow().cancel())
                if parsed.path == "/v1/product/draft/acknowledge":
                    self._require_shape(body, {"revision"})
                    return self._json(
                        request, 200,
                        self._workflow().acknowledge(self._string(body, "revision")),
                    )
                if parsed.path == "/v1/product/lease":
                    self._require_shape(body, set())
                    return self._json(request, 200, self.broker.acquire_lease(session.session_id))
                if parsed.path == "/v1/product/lease/renew":
                    self._require_shape(body, {"control_lease_id"})
                    return self._json(request, 200, self.broker.renew_lease(
                        session.session_id, self._string(body, "control_lease_id"),
                    ))
                if parsed.path == "/v1/product/commands":
                    if body.get("command_type") == "build_scene" and self.product_workflow is not None:
                        self.product_workflow.assert_build_allowed(
                            body.get("artifact_id"), body.get("expected_applied_revision"),
                        )
                    if body.get("command_type") == "build_site_scene" and self.product_workflow is not None:
                        self.product_workflow.assert_site_build_allowed(
                            body.get("artifact_id"), body.get("expected_applied_revision"),
                        )
                    if body.get("command_type") == "run" and self.product_workflow is not None:
                        if 'simulation_id' in body and self.conversation is not None and self.conversation.snapshot()['mode'] == 'REAL':
                            raise BrokerError('simulation_mode_required', 'REAL conversation cannot start a simulation binding')
                        self.product_workflow.assert_run_not_site_draft(body.get('simulation_id'), body.get('expected_applied_revision'))
                    return self._json(request, 202, self.broker.submit(session.session_id, body))
                if parsed.path == "/v1/product/commands/cancel":
                    self._require_shape(body, {"command_id"})
                    return self._json(request, 200, self.broker.cancel(
                        session.session_id, self._string(body, "command_id"),
                    ))
            if parsed.path.startswith("/v1/engine/"):
                session = self._authenticate_engine(request)
                body = self._read_json(request)
                engine_id = session.engine_session_id or ""
                stage_epoch = session.stage_epoch or ""
                if parsed.path == "/v1/engine/viewport":
                    self._assert_body_engine(body, session)
                    return self._json(request, 200, self.viewport.exchange(engine_id, stage_epoch, body))
                if parsed.path == "/v1/engine/stage":
                    self._require_shape(
                        body, {"engine_session_id", "current_stage_epoch", "new_stage_epoch"},
                    )
                    if (body.get("engine_session_id") != engine_id
                            or body.get("current_stage_epoch") != stage_epoch):
                        raise BrokerError("engine_identity_mismatch", "Engine stage transition is invalid", status=401)
                    new_stage_epoch = self._string(body, "new_stage_epoch")
                    self.broker.register_engine(engine_id, new_stage_epoch)
                    session.stage_epoch = new_stage_epoch
                    return self._json(request, 200, {"stage_epoch": new_stage_epoch})
                if parsed.path == "/v1/engine/heartbeat":
                    self._require_shape(body, {"engine_session_id", "stage_epoch"})
                    self._assert_body_engine(body, session)
                    result=self.broker.engine_heartbeat(engine_id, stage_epoch)
                    if self.workspace:
                        result['project_rebind']=self.workspace.instruction()
                    return self._json(request, 200, result)
                if parsed.path == '/v1/engine/project-rebind':
                    if not self.workspace:
                        raise BrokerError('project_rebind_unavailable','Conversation switching is unavailable.',status=409)
                    self._require_shape(body,{'switch_id','ticket','snapshot','error'})
                    return self._json(request,200,self.workspace.acknowledge(self,session,body))
                if parsed.path == '/v1/engine/mission-visual':
                    if set(body) not in ({'engine_session_id','stage_epoch','objects_revision'},
                        {'engine_session_id','stage_epoch','objects_revision','display_result'}):
                        raise BrokerError('active_visual_shape','Invalid visual polling request',status=400)
                    self._assert_body_engine(body,session)
                    status=self.broker.engine_heartbeat(engine_id,stage_epoch)
                    if not status['lease_valid']:return self._json(request,200,{'frame':None,'code':'ISAAC_CONTROL_LEASE_REQUIRED'})
                    return self._json(request,200,self.automatic_mission.active_visual(engine_id,stage_epoch,self._string(body,'objects_revision'),body.get('display_result')))
                if parsed.path == "/v1/engine/claim":
                    self._require_shape(body, {"engine_session_id", "stage_epoch"})
                    self._assert_body_engine(body, session)
                    command = self.broker.claim(engine_id, stage_epoch)
                    result={"command":command.to_dict() if command else None}
                    if command:result['execution_id']=self.broker.command_execution_identity(command)
                    return self._json(request,200,result)
                if parsed.path == "/v1/engine/receipt":
                    if set(body) not in ({'receipt'},{'receipt','diagnostics'}):
                        raise BrokerError('receipt_shape_invalid','Invalid receipt request',status=400)
                    receipt_value = body["receipt"]
                    if not isinstance(receipt_value, Mapping):
                        raise BrokerError("receipt_shape_invalid", "Receipt must be an object", status=400)
                    receipt = CommandReceipt.from_dict(receipt_value)
                    if receipt.engine_session_id != engine_id or receipt.stage_epoch != stage_epoch:
                        raise BrokerError("engine_identity_mismatch", "Receipt engine identity is invalid")
                    self.broker.record_receipt(receipt,diagnostics=body.get('diagnostics'))
                    return self._json(request, 200, {"accepted": True})
                if parsed.path == "/v1/engine/snapshot":
                    self._require_shape(body, {"snapshot"})
                    snapshot_value = body["snapshot"]
                    if not isinstance(snapshot_value, Mapping):
                        raise BrokerError("snapshot_shape_invalid", "Snapshot must be an object", status=400)
                    snapshot = SimulationSnapshot.from_dict(snapshot_value)
                    if snapshot.engine_session_id != engine_id or snapshot.stage_epoch != stage_epoch:
                        raise BrokerError("engine_identity_mismatch", "Snapshot engine identity is invalid")
                    self.broker.record_snapshot(snapshot)
                    return self._json(request, 200, {"accepted": True})
            return self._error(request, 404, "endpoint_not_found", "Endpoint does not exist")
        except BrokerError as error:
            return self._error(request, error.status, error.code, str(error))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return self._error(request, 400, "request_invalid", str(error)[:240])

    def _diagnostics(self):
        if self.robot_diagnostics is None:
            raise BrokerError('robot_diagnostics_unavailable', 'Robot diagnostics are disabled in this backend.', status=503)
        return self.robot_diagnostics

    def _readiness(self):
        if self.robot_readiness is None:
            raise BrokerError('robot_readiness_unavailable', 'No-motion collection is unavailable in this backend', status=503)
        return self.robot_readiness

    def _robot_transfer_busy(self):
        thread=getattr(getattr(self.physical_controller,'evidence_recovery',None),'thread',None)
        return bool(thread and thread.is_alive())

    def _scene_edit_physical_guard(self):
        # Called under the shared physical start lock. Stop/terminal input and
        # read-only state/history do not use this guard and remain available.
        if self.product_workflow is not None and self.product_workflow.scene_edit_transaction.locked():
            raise BrokerError('scene_edit_busy','Finish or recover the scene transaction before starting a robot operation.',status=409)
        if self.workspace_devices is not None:
            if self.workspace is not None and self.workspace.switching():
                raise BrokerError('project_switch_pending', 'Opening the selected conversation.', status=409)
            self.workspace_devices.bind_operation(self)

    def _virtual_context(self):
        return self._virtual

    @contextmanager
    def _scene_edit_admission(self,owner):
        with self._robot_start_lock:
            if self.workspace_devices is not None:
                self.workspace_devices.assert_document_available()
                yield
                return
            navigation=getattr(self.conversation,'navigation',None)
            task=getattr(navigation,'task_loop',None)
            if (self.automatic_mission.worker and self.automatic_mission.worker.is_alive()
                    or self.automatic_demo.worker and self.automatic_demo.worker.is_alive()
                    or self.chat_robot_preparation._busy()
                    or task and task.active()):
                raise BrokerError('scene_edit_robot_busy','Stop the current mission, task or mapping worker before editing the Twin.',status=409)
            if self.robot_readiness is not None:
                # This exception is only for a saved SIM document with current
                # v2 geometry/input binding. All REAL admission predicates and
                # worker/transfer/cleanup exclusions remain global and intact.
                sim_scope=False
                if self.conversation is not None and self.product_workflow is not None:
                    with self.product_workflow._lock:
                        source=self.product_workflow._application.site_draft
                        selected=self.product_workflow._input
                        sim_scope=bool(source and selected and source.input_revision
                            and selected.revision==source.input_revision.digest
                            and self.product_workflow._phase=='draft_ready'
                            and self.conversation.saved_sim_scene_edit_scope(self.broker.project_id))
                check=getattr(self.robot_readiness,'blocks_scene_edit',None)
                blocked=check(saved_sim_scope=sim_scope) if check else self.robot_readiness.blocks_robot_operation()
                if blocked:
                    raise BrokerError('scene_edit_robot_uncertain','Stationary collection is active or uncertain; editing remains locked.',status=409)
            if self.robot_diagnostics is not None and self.robot_diagnostics._running():
                raise BrokerError('scene_edit_robot_busy','Wait for the active robot observation before editing.',status=409)
            if self.physical_controller is not None:
                physical=self.physical_controller.snapshot(owner)
                if physical.get('busy') or self._robot_transfer_busy():
                    raise BrokerError('scene_edit_robot_busy','A physical worker or evidence transfer is active; it will not be interrupted.',status=409)
                if physical.get('cleanup_confirmed') is False or physical.get('state') in {'CONNECTION_LOST','UNKNOWN','STOPPING'}:
                    raise BrokerError('scene_edit_robot_uncertain','Robot cleanup is unconfirmed. Editing cannot imply a stop ACK.',status=409)
            yield

    def _capture_robot_app_context(self):
        context={'app_scene_revision':None,'app_robot_profile_id':None,
                 'capture_status':'UNAVAILABLE'}
        if self.product_workflow is not None:
            try:
                workflow_state=self.product_workflow.snapshot()
                scene=workflow_state.get('site_draft') or workflow_state.get('draft')
                if isinstance(scene,Mapping):
                    revision=scene.get('revision')
                    profile=scene.get('robot_profile_id')
                    if isinstance(revision,str) and re.fullmatch('[a-f0-9]{64}',revision):
                        context['app_scene_revision']=revision
                    if isinstance(profile,str) and re.fullmatch('[A-Za-z0-9_.-]{1,128}',profile):
                        context['app_robot_profile_id']=profile
                context['capture_status']='CAPTURED'
            except (BrokerError,OSError,TypeError,ValueError,AttributeError):
                # A lookup failure is not an empty App scene or a physical gate.
                pass
        return context

    def _workflow(self) -> ProductWorkflow:
        if self.product_workflow is None:
            raise BrokerError("workflow_unavailable", "Product workflow is not configured", status=503)
        return self.product_workflow

    def _provider_keys(self, body=None) -> dict[str, object]:
        if self._key_registry is None:
            raise BrokerError('key_registry_unavailable', 'API 키 목록이 구성되지 않았습니다.', status=503)
        try:
            with self._provider_settings_lock:
                if body is None:
                    return self._key_registry.state()
                action = body.get('action')
                if action == 'register':
                    from .stage_routing import StageRoutingSettings
                    before=self._key_registry.state()
                    first=(body.get('provider_profile') in {'nebius_token_factory','nebius_site_v2'}
                        and not self._key_registry.settings.path.exists()
                        and not StageRoutingSettings(self._key_registry).path.exists()
                        and not any(e['configured'] for e in before['entries']))
                    value=self._key_registry.register({k: v for k, v in body.items() if k != 'action'})
                    if first:
                        from .provider_onboarding import configure_first_nebius_key
                        try:
                            if self.product_workflow is not None and (self.product_workflow.has_active_generation()
                                    or self.broker.has_pending_operations()):
                                raise KeyRegistryError('generation_busy','현재 작업이 끝난 뒤 기본 조합을 설정하세요.',409)
                            changed=self.product_workflow.provider_settings_changed if self.product_workflow is not None else lambda:None
                            setup=configure_first_nebius_key(self._key_registry,value['entries'][-1]['id'],changed)
                            value=self._key_registry.state()
                        except Exception as error:
                            setup=dict(state='unavailable',metadata_gets=getattr(error,'metadata_gets',0),
                                code=error.code if isinstance(error,KeyRegistryError) else 'default_metadata_unavailable',
                                message=str(error) if isinstance(error,KeyRegistryError) else '키는 저장했습니다. 모델 목록 확인 또는 기본 조합 적용이 실패했으며 다른 모델로 전환하지 않았습니다.')
                        value.update(network_called=bool(setup['metadata_gets']),default_setup=setup)
                    return value
                if action == 'stage_routing':
                    if set(body) != {'action', 'route'}:
                        raise BrokerError('request_shape_invalid', '단계 설정 요청 형식이 잘못되었습니다.', status=400)
                    if self.product_workflow is not None and (self.product_workflow.snapshot().get('phase') == 'generating'
                            or self.product_workflow.has_active_generation() or self.broker.has_pending_operations()):
                        raise BrokerError('generation_busy', '현재 생성 또는 장면 작업이 끝난 뒤 모델 조합을 변경하세요.', status=409)
                    from .stage_routing import StageRoutingSettings
                    changed = self.product_workflow.provider_settings_changed if self.product_workflow is not None else lambda: None
                    StageRoutingSettings(self._key_registry).save(body['route'], changed)
                    return self._key_registry.state()
                if action not in {'select', 'remove'} or set(body) != {'action', 'id'}:
                    raise BrokerError('request_shape_invalid', '키 목록 요청 형식이 잘못되었습니다.', status=400)
                if action == 'remove':
                    return self._key_registry.remove(body['id'])
                if self.product_workflow is not None and (self.product_workflow.snapshot().get('phase') == 'generating'
                        or self.product_workflow.has_active_generation() or self.broker.has_pending_operations()):
                    raise BrokerError('generation_busy', '현재 생성 또는 장면 작업이 끝난 뒤 키를 변경하세요.', status=409)
                changed = self.product_workflow.provider_settings_changed if self.product_workflow is not None else lambda: None
                return self._key_registry.select(body['id'], changed)
        except KeyRegistryError as error:
            raise BrokerError(error.code, str(error), status=error.status) from None
        except BrokerError:
            raise
        except Exception:
            raise BrokerError('key_settings_unavailable', '키 설정을 완료하지 못했습니다. 보안 저장소와 설정 파일 상태를 확인하세요.', status=500) from None

    def _active_credential(self, value: ProviderSettings) -> CredentialStore:
        if self._key_registry is not None:
            try:
                return self._key_registry.resolve(value)
            except KeyRegistryError as error:
                raise BrokerError(error.code, str(error), status=error.status) from None
        return self._credential_store

    def _provider_settings(self) -> dict[str, object]:
        if self._provider_settings_store is None or self._credential_store is None:
            raise BrokerError("provider_settings_unavailable", "Provider settings are not configured", status=503)
        try:
            value = self._provider_settings_store.load().validated()
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            raise BrokerError(
                "provider_settings_corrupt",
                "Provider settings could not be read; the original file was preserved for review",
                status=500,
            ) from None
        try:
            credential_configured = self._active_credential(value).is_configured()
        except Exception:
            raise BrokerError(
                "credential_status_failed", "Credential status could not be read securely", status=500,
            ) from None
        provider_connected = False
        if self.product_workflow is not None:
            snapshot = self.product_workflow.snapshot()
            provider = snapshot.get("provider")
            provider_connected = bool(
                snapshot.get("mode") == "live_provider"
                and isinstance(provider, Mapping)
                and provider.get("connected")
            )
        return {
            "schema_version": "3.0",
            "base_url": value.base_url,
            "model_id": value.model_id,
            "reasoning_effort": value.reasoning_effort,
            "adapter_kind": value.adapter_kind,
            "provider_profile": value.provider_profile,
            "endpoint_path": value.endpoint_path,
            "credential_ref": value.credential_ref,
            "observer_model_id": value.observer_model_id,
            "fallback_observer_model_id": value.fallback_observer_model_id,
            "capabilities": {
                "supports_images": value.supports_images,
                "supports_structured_output": value.supports_structured_output,
                "max_images": value.max_images,
                "accepted_mime_types": list(value.accepted_mime_types),
            },
            "settings_saved": self._provider_settings_store.exists(),
            "capability_checked": value.provider_profile == DEFAULT_PROVIDER_PROFILE or provider_connected,
            "credential_configured": credential_configured,
            "live_request_succeeded": provider_connected,
        }

    def _save_provider_settings(self, body: Mapping[str, object]) -> dict[str, object]:
        if self._provider_settings_store is None or self._credential_store is None:
            raise BrokerError("provider_settings_unavailable", "Provider settings are not configured", status=503)
        if self._key_registry is not None:
            from .stage_routing import StageRoutingSettings
            if StageRoutingSettings(self._key_registry).load() is not None:
                raise BrokerError('stage_routing_active', '단계별 조합을 사용 중입니다. API keys에서 모델 조합을 변경하세요.', status=409)
        legacy_shape = {"base_url", "model_id", "reasoning_effort", "api_key"}
        current_shape = legacy_shape | {"credential_reapproval"}
        profile_shape = current_shape | {"provider_profile"}
        if frozenset(body) not in {
            frozenset(legacy_shape), frozenset(current_shape), frozenset(profile_shape),
        }:
            raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)
        api_key = body.get("api_key")
        if not isinstance(api_key, str) or len(api_key) > 8192:
            raise BrokerError("request_value_invalid", "api_key is invalid", status=400)
        reapproval = body.get("credential_reapproval", False)
        if not isinstance(reapproval, bool):
            raise BrokerError("request_value_invalid", "credential_reapproval is invalid", status=400)
        with self._provider_settings_lock:
            try:
                previous = self._provider_settings_store.load().validated()
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                raise BrokerError(
                    "provider_settings_corrupt",
                    "Provider settings could not be read; the original file was preserved for review",
                    status=500,
                ) from None
            selected_profile = body.get("provider_profile", previous.provider_profile)
            if not isinstance(selected_profile, str):
                raise BrokerError("request_value_invalid", "provider_profile is invalid", status=400)
            try:
                preset = provider_settings_preset(selected_profile, credential_ref=previous.credential_ref)
                if preset.provider_profile == DEFAULT_PROVIDER_PROFILE:
                    value = ProviderSettings(
                        self._string(body, "base_url"),
                        self._string(body, "model_id"),
                        self._string(body, "reasoning_effort"),
                        preset.adapter_kind,
                        preset.provider_profile,
                        preset.endpoint_path,
                        preset.credential_ref,
                        preset.supports_images,
                        preset.supports_structured_output,
                        preset.max_images,
                        preset.accepted_mime_types,
                        preset.observer_model_id,
                        preset.fallback_observer_model_id,
                    ).validated()
                else:
                    requested = (
                        self._string(body, "base_url"), self._string(body, "model_id"),
                        self._string(body, "reasoning_effort"),
                    )
                    expected = (preset.base_url, preset.model_id, preset.reasoning_effort)
                    if requested != expected:
                        raise BrokerError(
                            "provider_preset_mismatch",
                            "Nebius uses the reviewed S3a endpoint and model pipeline",
                            status=400,
                        )
                    value = preset
            except ValueError as error:
                raise BrokerError("provider_settings_invalid", str(error), status=400) from None
            credential = self._active_credential(value)
            store_target = getattr(credential, "target_name", value.credential_ref)
            if store_target != value.credential_ref:
                raise BrokerError(
                    "credential_reference_mismatch",
                    "The active credential store does not match the selected provider profile",
                    status=409,
                )
            binding_changed = value.binding_identity != previous.binding_identity
            profile_changed = (
                value.adapter_kind != previous.adapter_kind
                or value.provider_profile != previous.provider_profile
                or value.credential_ref != previous.credential_ref
            )
            has_new_key = bool(api_key.strip())
            if binding_changed and not has_new_key:
                try:
                    credential_configured = credential.is_configured()
                except Exception:
                    raise BrokerError(
                        "credential_status_failed", "Credential status could not be read securely", status=500,
                    ) from None
                if profile_changed or not reapproval or not credential_configured:
                    raise BrokerError(
                        "credential_rebind_required",
                        "Endpoint or provider identity changed; enter a new key or explicitly reapprove the existing key",
                        status=409,
                    )
            old_secret: str | None = None
            if has_new_key:
                try:
                    old_secret = credential.load()
                    credential.save(api_key)
                except Exception:
                    raise BrokerError(
                        "credential_save_failed", "The credential could not be stored securely", status=500,
                    ) from None
            try:
                self._provider_settings_store.save(value)
            except Exception:
                if has_new_key:
                    try:
                        if old_secret:
                            credential.save(old_secret)
                        else:
                            credential.delete()
                    except Exception:
                        raise BrokerError(
                            "settings_transaction_rollback_failed",
                            "Settings were not saved and credential rollback requires manual review",
                            status=500,
                        ) from None
                raise BrokerError(
                    "provider_settings_save_failed", "Provider settings could not be saved", status=500,
                ) from None
        if self.product_workflow is not None:
            self.product_workflow.provider_settings_changed()
        return self._provider_settings()

    def _supervisor_status(self) -> dict[str, object]:
        path = self._supervisor_status_file
        if path is None:
            return {
                "schema_version": "1.0", "status": "unmanaged", "phase": "standalone",
                "message": "Started without the TwinPulse process manager",
                "backend": {"owned": False, "state": "running"},
                "engine": {"owned": False, "state": "unknown"},
                "browser": {"launched": False},
            }
        try:
            if path.stat().st_size > 64 * 1024:
                raise ValueError("status file exceeds limit")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError("status must be an object")
            result = _sanitize_supervisor_status(value)
            result['shutdown_requested'] = bool(self._launcher_shutdown_file and self._launcher_shutdown_file.exists())
            result['shutdown_available'] = bool(self._launcher_shutdown_file and result['status'] in
                {'ready', 'starting', 'error'} and not result['shutdown_requested'] and not self._shutdown_busy())
            return result
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            return {
                "schema_version": "1.0", "status": "error", "phase": "status_unavailable",
                "message": str(error)[:240],
                "backend": {"owned": True, "state": "running"},
                "engine": {"owned": True, "state": "unknown"},
                "browser": {"launched": False},
            }

    def _shutdown_busy(self):
        if self.workspace is not None and self.workspace.pending:
            return True
        if self.workspace is not None and sum(self.workspace.mutations.values()) > 1:
            return True
        if self.broker.has_pending_operations():
            return True
        snapshot = self.broker.supervisor_state().get('snapshot') or {}
        if snapshot.get('runtime_state') == 'running':
            return True
        if self.product_workflow is not None and (self.product_workflow.has_active_generation()
                or self.product_workflow.scene_edit_transaction.locked()):
            return True
        if self.conversation is not None and self.conversation._feedback_worker is not None and self.conversation._feedback_worker.is_alive():
            return True
        try:
            with self._scene_edit_admission('desktop-shutdown'):
                return False
        except BrokerError:
            return True

    def _request_shutdown(self):
        path = self._launcher_shutdown_file
        status = self._supervisor_status()
        if path is None or status['status'] not in {'ready', 'starting', 'error'}:
            raise BrokerError('shutdown_unavailable', 'No managed TwinPulse launch is available.', status=409)
        from contextlib import nullcontext
        with self.workspace.lock if self.workspace is not None else nullcontext():
            with self._launcher_retry_lock:
                if path.exists():
                    return {'status': 'requested', 'new_session_required': True}
                if self._shutdown_busy():
                    raise BrokerError('shutdown_busy', 'Stop the current simulation or response before exiting TwinPulse.', status=409)
                try:
                    with path.open('x', encoding='utf-8') as stream:
                        json.dump({'schema_version': '1.0', 'action': 'shutdown'}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError as error:
                    raise BrokerError('shutdown_storage_failed', 'Could not save the shutdown request.', status=503) from error
                if self.workspace is not None:
                    self.workspace.closing = True
        return {'status': 'requested', 'new_session_required': True}

    def _request_launcher_retry(self) -> dict[str, object]:
        retry = self._launcher_retry_file
        status = self._supervisor_status()
        engine = status.get("engine")
        backend = status.get("backend")
        if (retry is None or status.get("status") != "error"
                or self._launcher_retry_remaining < 1
                or status.get("phase") == "status_unavailable"
                or not isinstance(engine, Mapping) or engine.get("state") not in {"exited", "not_started"}
                or not isinstance(backend, Mapping) or backend.get("state") != "running"):
            raise BrokerError("launcher_retry_unavailable", "An owned, stopped engine startup is required", status=409)
        with self._launcher_retry_lock:
            try:
                with retry.open("xb") as stream:
                    stream.write(b'{"schema_version":"1.0","action":"retry"}\n')
            except FileExistsError as error:
                raise BrokerError("launcher_retry_pending", "Launcher retry has already been requested", status=409) from error
            except OSError as error:
                raise BrokerError("launcher_retry_unavailable", "Launcher retry request could not be saved", status=409) from error
        return {"status": "requested", "new_session_required": True}

    def _request_startup_cancel(self) -> dict[str, object]:
        request_file = self._launcher_cancel_file
        status = self._supervisor_status()
        backend = status.get("backend")
        if (request_file is None or status.get("status") != "starting"
                or not isinstance(backend, Mapping) or backend.get("state") != "running"):
            raise BrokerError("startup_cancel_unavailable", "An owned startup must be in progress", status=409)
        with self._launcher_retry_lock:
            try:
                with request_file.open("xb") as stream:
                    stream.write(b'{"schema_version":"1.0","action":"cancel_startup"}\n')
            except FileExistsError as error:
                raise BrokerError("startup_cancel_pending", "Startup cancellation is already requested", status=409) from error
            except OSError as error:
                raise BrokerError("startup_cancel_unavailable", "Startup cancellation could not be saved", status=409) from error
        return {"status": "requested", "new_session_required": True}

    def _runtime_diagnostics(self) -> dict[str, object]:
        """Small allowlisted support bundle: never return raw logs, paths or traces."""
        import re
        import sys

        status = self._supervisor_status()
        startup: dict[str, object] | None = None
        engine_profile: dict[str, object] | None = None
        path = self._engine_result_file
        if path is not None:
            try:
                if path.stat().st_size > 64 * 1024:
                    raise ValueError("oversized result")
                result = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(result, Mapping) and result.get("status") == "FAIL":
                    profile = result.get("startup_profile")
                    if isinstance(profile, Mapping) and profile.get("schema_version") == "engine-startup-profile-1.0":
                        package_values = profile.get("packages")
                        python_version = profile.get("python")
                        if (isinstance(package_values, Mapping) and isinstance(python_version, str)
                                and re.fullmatch(r"3\.[0-9]{1,2}\.[0-9]{1,3}", python_version)):
                            safe_packages: dict[str, object] = {}
                            for name in ("numpy", "scipy"):
                                item = package_values.get(name)
                                if not isinstance(item, Mapping):
                                    continue
                                origin_class = item.get("origin_class")
                                digest = item.get("origin_sha256")
                                version = item.get("version")
                                safe_packages[name] = {
                                    "loaded": item.get("loaded") is True,
                                    "origin_class": origin_class if origin_class in {
                                        "unknown", "extension_prebundle", "isaac_kit_python", "other_local_path",
                                    } else "unknown",
                                    "origin_sha256": digest if isinstance(digest, str)
                                    and re.fullmatch(r"[0-9a-f]{64}", digest) else None,
                                    "version": version if isinstance(version, str)
                                    and re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,4}){1,3}(?:[.+-][A-Za-z0-9]{1,16})?", version) else None,
                                }
                            engine_profile = {"python": python_version, "packages": safe_packages}
                    phase = result.get("startup_phase")
                    error_type = result.get("error_type")
                    if phase in {"isaac_import", "simulation_app_init"} and isinstance(error_type, str):
                        safe_type = error_type if error_type in {
                            "ImportError", "ModuleNotFoundError", "OSError", "RuntimeError",
                            "TypeError", "ValueError", "Exception",
                        } else "OtherException"
                        startup = {"phase": phase, "error_type": safe_type,
                                   "detail": "Raw exception text and traceback remain in local owner-only files"}
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                pass
        def safe_name(value: object) -> str:
            return value if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,64}", value) else "unknown"

        def safe_component(value: object) -> dict[str, object]:
            raw = value if isinstance(value, Mapping) else {}
            state = raw.get("state")
            return {"owned": raw.get("owned") is True,
                    "state": state if state in {"running", "exited", "not_started", "unknown"} else "unknown",
                    "exit_code": raw.get("exit_code") if type(raw.get("exit_code")) is int
                    and -1024 <= raw["exit_code"] <= 1024 else None}

        def safe_time(value: object) -> str | None:
            return value if isinstance(value, str) and re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)", value,
            ) else None

        runtime = {
            "status": safe_name(status.get("status")), "phase": safe_name(status.get("phase")),
            "retry_remaining": status.get("retry_remaining") if type(status.get("retry_remaining")) is int
            and 0 <= status["retry_remaining"] <= 3 else 0,
            "started_at_utc": safe_time(status.get("started_at_utc")),
            "updated_at_utc": safe_time(status.get("updated_at_utc")),
            "backend": safe_component(status.get("backend")),
            "engine": safe_component(status.get("engine")),
            "browser": {"launched": isinstance(status.get("browser"), Mapping)
                        and status["browser"].get("launched") is True},
        }
        return {
            "schema_version": "runtime-diagnostics-1.0",
            "release": {
                "build_id": os.environ.get('TWINPULSE_RELEASE_ID') if re.fullmatch(
                    r'[A-Za-z0-9_-]{1,80}', os.environ.get('TWINPULSE_RELEASE_ID', '')) else None,
                "product_version": os.environ.get('TWINPULSE_RELEASE_VERSION') if re.fullmatch(
                    r'[0-9A-Za-z.+-]{1,40}', os.environ.get('TWINPULSE_RELEASE_VERSION', '')) else None,
                "simulation_only": os.environ.get('TWINPULSE_SIM_ONLY') == '1',
            },
            "runtime": runtime,
            "engine_startup": startup,
            "engine_runtime_profile": engine_profile,
            "profile": {"app_python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                        "platform": sys.platform},
            "export_policy": "allowlisted_metadata_only_no_raw_logs_paths_secrets_or_user_images",
        }

    def _request_project_switch(self, project_id: str, session_id: str) -> dict[str, object]:
        from .project_store import checked_project_id

        try:
            project_id = checked_project_id(project_id)
        except ValueError as error:
            raise BrokerError("project_id_invalid", "Use a listed portable project ID", status=400) from error
        catalog = self.project_catalog
        request_file = self._launcher_project_switch_file
        if catalog is None or (request_file is None and self.workspace is None) or self._supervisor_status().get("status") != "ready":
            raise BrokerError("project_switch_unavailable", "Managed ready launcher is required", status=409)
        if project_id == catalog.active_project_id:
            raise BrokerError("project_already_active", "This project is already active", status=409)
        matches = [item for item in catalog.snapshot()["projects"] if item["project_id"] == project_id]
        if not matches or matches[0]["status"] == "source_invalid":
            raise BrokerError("project_source_unavailable", "Selected local project is absent or invalid", status=409)
        if (self.broker.has_pending_operations()
                or self.automatic_demo.mission_active()
                or (self.automatic_demo.worker is not None and self.automatic_demo.worker.is_alive())
                or self._workflow().has_active_generation()
                or (self.conversation is not None and self.conversation._feedback_worker is not None and self.conversation._feedback_worker.is_alive())
                or self._workflow().scene_edit_transaction.locked()
                or (self.physical_controller is not None
                    and self.physical_controller.snapshot(session_id)["busy"])):
            raise BrokerError("project_switch_busy", "Finish the active operation before switching", status=409)
        if self.workspace is not None:
            return self.workspace.begin(self,project_id)
        with self._launcher_retry_lock:
            try:
                with request_file.open("x", encoding="utf-8") as stream:
                    json.dump({"schema_version": "1.0", "action": "switch_project",
                               "project_id": project_id}, stream, sort_keys=True)
                    stream.write("\n")
            except FileExistsError as error:
                raise BrokerError("project_switch_pending", "Project switch is already requested", status=409) from error
            except OSError as error:
                raise BrokerError("project_switch_unavailable", "Project switch request could not be saved", status=409) from error
        return {"status": "requested", "project_id": project_id, "new_session_required": True}

    def _serve_static(self, request: BaseHTTPRequestHandler, path: str) -> None:
        root = self._static_root
        if root is None:
            return self._error(request, 404, "static_unavailable", "Product UI is not configured")
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        if not relative or "\\" in relative or any(part in {"", ".", ".."} for part in relative.split("/")):
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        if not target.is_file():
            return self._error(request, 404, "asset_not_found", "Static asset does not exist")
        suffix = target.suffix.lower()
        media_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".json": "application/json; charset=utf-8",
        }.get(suffix)
        if media_type is None:
            return self._error(request, 415, "asset_type_forbidden", "Static asset type is forbidden")
        payload = target.read_bytes()
        request.send_response(200)
        request.send_header("Content-Type", media_type)
        request.send_header("Content-Length", str(len(payload)))
        request.send_header("Cache-Control", "no-store" if suffix == ".html" else "public, max-age=31536000, immutable")
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Referrer-Policy", "no-referrer")
        request.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        request.end_headers()
        request.wfile.write(payload)

    def _bootstrap_session(self, request: BaseHTTPRequestHandler, body: Mapping[str, object]) -> None:
        allowed = {"role", "secret", "engine_session_id", "stage_epoch"}
        if set(body) - allowed:
            raise BrokerError("bootstrap_shape_invalid", "Bootstrap request shape is invalid", status=400)
        role = self._string(body, "role")
        supplied = self._string(body, "secret")
        with self._session_lock:
            expected = self._bootstrap.get(role)
            replacement = None
            if role == 'product':
                for ticket, expires in self._product_bootstrap_tickets.items():
                    if self._clock() < expires and hmac.compare_digest(ticket, supplied):
                        replacement = ticket
                        break
            if (replacement is None and (expected is None or self._clock() >= self._bootstrap_expires_at.get(role, 0.0)
                    or not hmac.compare_digest(expected, supplied))):
                raise BrokerError("bootstrap_rejected", "Bootstrap credential is invalid or expired", status=401)
            engine_id = stage_epoch = None
            if role == "engine":
                engine_id = self._string(body, "engine_session_id")
                stage_epoch = self._string(body, "stage_epoch")
                self.broker.register_engine(engine_id, stage_epoch)
            elif role != "product":
                raise BrokerError("bootstrap_role_invalid", "Bootstrap role is unsupported", status=400)
            if replacement is not None:
                self._product_bootstrap_tickets.pop(replacement)
            else:
                self._bootstrap[role] = None
            now = self._clock()
            current = self._sessions.get(self._parse_cookies(request.headers.get('Cookie', '')).get(PRODUCT_COOKIE)) if role == 'product' else None
            if (current is not None and current.role == 'product'
                    and now < current.idle_expires_at and now < current.absolute_expires_at):
                # Reopening the same App must not replace the shared cookie/CSRF
                # of its other tabs. A valid one-use ticket is still consumed;
                # existing permissions and absolute expiry are not extended.
                session_id = current.session_id
            else:
                session_id = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(24) if role == "product" else None
                absolute_expires_at = now + self._session_absolute_ttl_s
                self._sessions[session_id] = _Session(
                    session_id=session_id,
                    role=role,
                    csrf=csrf,
                    idle_expires_at=min(now + self._session_idle_ttl_s, absolute_expires_at),
                    absolute_expires_at=absolute_expires_at,
                    engine_session_id=engine_id,
                    stage_epoch=stage_epoch,
                )
        headers = None
        session = self._sessions[session_id]
        result = self._session_metadata(session)
        if role == "product":
            headers = {"Set-Cookie": (
                f"{PRODUCT_COOKIE}={session_id}; HttpOnly; SameSite=Strict; Path=/; "
                f"Max-Age={max(0, math.ceil(session.absolute_expires_at - self._clock()))}"
            )}
        else:
            result["session_token"] = session_id
        self._json(request, 200, result, headers=headers)

    def _issue_product_bootstrap(
        self, request: BaseHTTPRequestHandler, body: Mapping[str, object],
    ) -> None:
        self._require_shape(body, {"owner_secret"})
        supplied = self._string(body, "owner_secret")
        if not hmac.compare_digest(self._product_owner_secret, supplied):
            raise BrokerError(
                "bootstrap_owner_rejected",
                "Product bootstrap owner credential is invalid",
                status=401,
            )
        with self._session_lock:
            # Concurrent Start clicks can open two windows before either has
            # exchanged its ticket. Never invalidate the first pending ticket.
            now = self._clock()
            for ticket, expires in list(self._product_bootstrap_tickets.items()):
                if now >= expires:
                    self._product_bootstrap_tickets.pop(ticket)
            if len(self._product_bootstrap_tickets) >= 8:
                raise BrokerError('bootstrap_busy', 'Wait for the pending App windows to open before reopening again.', status=409)
            bootstrap_secret = secrets.token_urlsafe(32)
            self._product_bootstrap_tickets[bootstrap_secret] = now + self._bootstrap_ttl_s
        self._json(request, 200, {
            "role": "product",
            "bootstrap_secret": bootstrap_secret,
            "expires_in_s": self._bootstrap_ttl_s,
        })

    def _authenticate_product(self, request: BaseHTTPRequestHandler, *, require_csrf: bool) -> _Session:
        cookies = self._parse_cookies(request.headers.get("Cookie", ""))
        session = self._session(cookies.get(PRODUCT_COOKIE), "product")
        if require_csrf and not hmac.compare_digest(request.headers.get("X-TwinPulse-CSRF", ""), session.csrf or ""):
            raise BrokerError("csrf_rejected", "CSRF token is invalid", status=403)
        return session

    def _authenticate_engine(self, request: BaseHTTPRequestHandler) -> _Session:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise BrokerError("engine_auth_required", "Engine authorization is required", status=401)
        return self._session(authorization[7:], "engine")

    def _session(self, session_id: str | None, role: str) -> _Session:
        with self._session_lock:
            session = self._sessions.get(session_id or "")
            now = self._clock()
            if (session is None or session.role != role
                    or now >= session.idle_expires_at or now >= session.absolute_expires_at):
                if session is not None and (
                    now >= session.idle_expires_at or now >= session.absolute_expires_at
                ):
                    self._sessions.pop(session.session_id, None)
                raise BrokerError("session_rejected", "Session is invalid, expired, or has the wrong role", status=401)
            session.idle_expires_at = min(
                now + self._session_idle_ttl_s,
                session.absolute_expires_at,
            )
            return session

    def _session_metadata(self, session: _Session) -> dict[str, object]:
        now = self._clock()
        result: dict[str, object] = {
            "role": session.role,
            "idle_expires_in_s": max(0, math.ceil(session.idle_expires_at - now)),
            "absolute_expires_in_s": max(0, math.ceil(session.absolute_expires_at - now)),
        }
        if session.role == "product":
            result["csrf_token"] = session.csrf or ""
            result['context_id']=self.context_id
            result['project_id']=self.broker.project_id
            if self.workspace:
                result['project_switch']=self.workspace.instruction()
            if self.workspace_devices is not None:
                result['device'] = self.workspace_devices.snapshot()
        return result

    def _read_json(
        self, request: BaseHTTPRequestHandler, *, maximum: int = MAX_JSON_BYTES,
    ) -> Mapping[str, object]:
        if hasattr(request,'_twinpulse_saved_json'):
            value=request._twinpulse_saved_json
            del request._twinpulse_saved_json
            return value
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise BrokerError("content_type_invalid", "Content-Type must be application/json", status=415)
        raw_length = request.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdigit():
            raise BrokerError("content_length_required", "Content-Length is required", status=411)
        length = int(raw_length)
        if length > maximum:
            self._discard_unread_body(request)
            raise BrokerError("payload_too_large", "JSON payload exceeds the limit", status=413)
        data = request.rfile.read(length)
        request._twinpulse_body_consumed = True
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, Mapping):
            raise BrokerError("json_object_required", "JSON body must be an object", status=400)
        return value

    @staticmethod
    def _require_shape(value: Mapping[str, object], expected: set[str]) -> None:
        if set(value) != expected:
            raise BrokerError("request_shape_invalid", "Request shape is invalid", status=400)

    @staticmethod
    def _string(value: Mapping[str, object], name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item or len(item) > 512:
            raise BrokerError("request_value_invalid", f"{name} is invalid", status=400)
        return item

    @staticmethod
    def _parse_cookies(value: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in value.split(";"):
            name, separator, content = item.strip().partition("=")
            if separator:
                result[name] = content
        return result

    @staticmethod
    def _assert_body_engine(value: Mapping[str, object], session: _Session) -> None:
        if (value.get("engine_session_id") != session.engine_session_id
                or value.get("stage_epoch") != session.stage_epoch):
            raise BrokerError("engine_identity_mismatch", "Engine body identity is invalid", status=401)

    def _host_allowed(self, value: str) -> bool:
        return value in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    @staticmethod
    def _json(
        request: BaseHTTPRequestHandler,
        status: int,
        value: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        context=getattr(request,'_twinpulse_context_id',None)
        if not isinstance(context,str):context=None
        if context and getattr(request,'path',None)=='/v1/product/conversation':
            value={'context_id':context,**value}
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        try:
            request.send_response(status)
            request.send_header("Content-Type", "application/json; charset=utf-8")
            request.send_header("Content-Length", str(len(payload)))
            request.send_header("Cache-Control", "no-store")
            request.send_header("X-Content-Type-Options", "nosniff")
            if context:request.send_header('X-TwinPulse-Context',str(value.get('context_id',context)))
            if headers:
                for name, content in headers.items():
                    request.send_header(name, content)
            request.end_headers()
            request.wfile.write(payload)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # A browser reload can discard an already committed response. It
            # must not turn into another error response or repeat the mutation;
            # the operation ledger remains the authoritative queryable result.
            request.close_connection = True

    @classmethod
    def _error(cls, request: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
        # Auth/Host/Origin/CSRF failures happen before JSON parsing. Closing with
        # unread body bytes can reset the connection instead of delivering the
        # error on Windows. Discard small bodies without interpreting them, with
        # a strict total time/byte bound; rejection and all access checks remain.
        cls._discard_unread_body(request)
        cls._json(request, status, {"error": {"code": code, "message": message}})

    @staticmethod
    def _discard_unread_body(request: BaseHTTPRequestHandler) -> None:
        request.close_connection = True
        if getattr(request, "_twinpulse_body_consumed", False):
            return
        # Set before reading so a timeout/overflow is never drained twice.
        request._twinpulse_body_consumed = True
        lengths = request.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 9
                or request.headers.get("Transfer-Encoding") is not None):
            return
        remaining = int(lengths[0])
        if remaining > MAX_JSON_BYTES * 2:
            return
        deadline = time.monotonic() + 0.1
        previous_timeout = request.connection.gettimeout()
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                request.connection.settimeout(timeout)
                chunk = request.rfile.read1(min(remaining, 16384))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (OSError, ValueError):
            pass  # Still send the original rejection; never process this body.
        finally:
            request.connection.settimeout(previous_timeout)


def _sanitize_supervisor_status(value: Mapping[str, object]) -> dict[str, object]:
    def text(name: str, default: str = "") -> str:
        item = value.get(name, default)
        return str(item)[:240]

    def component(name: str) -> dict[str, object]:
        raw = value.get(name)
        if not isinstance(raw, Mapping):
            raw = {}
        result: dict[str, object] = {
            "owned": bool(raw.get("owned", False)),
            "state": str(raw.get("state", "unknown"))[:64],
        }
        if isinstance(raw.get("pid"), int) and int(raw["pid"]) > 0:
            result["pid"] = int(raw["pid"])
        if isinstance(raw.get("exit_code"), int):
            result["exit_code"] = int(raw["exit_code"])
        return result

    browser_raw = value.get("browser")
    browser = browser_raw if isinstance(browser_raw, Mapping) else {}
    checks = []
    raw_checks = value.get('startup_checks', [])
    if isinstance(raw_checks, list):
        for row in raw_checks[:24]:
            if (not isinstance(row, Mapping) or not isinstance(row.get('id'),str)
                    or not re.fullmatch(r'[a-z_]{1,40}', row['id'])
                    or row.get('state') not in {'ready','checking','repairing','needs_action','failed','not_required'}):
                continue
            checks.append({'id':row['id'],'state':row['state'],'detail':str(row.get('detail',''))[:240],
                           'action':str(row['action'])[:240] if row.get('action') is not None else None,
                           'sampled_at':str(row.get('sampled_at',''))[:40]})
            if type(row.get('attempts')) is int and 0 <= row['attempts'] <= 1:
                checks[-1]['attempts'] = row['attempts']
    return {
        "schema_version": "1.0",
        "status": text("status", "unknown"),
        "phase": text("phase", "unknown"),
        "message": text("message"),
        "retry_remaining": value.get("retry_remaining") if type(value.get("retry_remaining")) is int
        and 0 <= value["retry_remaining"] <= 3 else 0,
        "started_at_utc": text("started_at_utc") or None,
        "updated_at_utc": text("updated_at_utc") or None,
        "backend": component("backend"),
        "engine": component("engine"),
        "browser": {"launched": bool(browser.get("launched", False))},
        "startup_checks": checks,
        "diagnostic_execution_id": value.get('diagnostic_execution_id')
        if type(value.get('diagnostic_execution_id')) is str
        and re.fullmatch(r'[a-f0-9]{32}', value['diagnostic_execution_id']) else None,
    }
