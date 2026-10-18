# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned local R4 backend process used by the bridge and finite acceptance runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event
import time


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import (  # noqa: E402
    ApplicationService,
    CommandBroker,
    JsonProviderSettingsStore,
    LocalApiServer,
    ProductWorkflow,
    ProjectStore,
    checked_project_id,
    ProviderSettings,
    WindowsCredentialStore,
    ReplayOnlyGateway,
    build_live_generation_service,
    load_replay_fixture,
)
from twinpulse_app.credentials import DEFAULT_CREDENTIAL_TARGET  # noqa: E402
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.robot_diagnostics import RobotDiagnostics
from twinpulse_app.robot_readiness import RobotReadiness
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.project_catalog import ProjectCatalog
from twinpulse_core import InputArtifactStore, fixed_warehouse_bundle  # noqa: E402
from twinpulse_provider import (  # noqa: E402
    GenerationService,
    MockProvider,
    ProviderCapabilities,
    ProviderConfig,
    ProviderConfigurationError,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument('--port-candidates', type=int, default=1)
    parser.add_argument('--backend-stop-file', type=Path)
    parser.add_argument('--launcher-shutdown-file', type=Path)
    parser.add_argument('--profile-generation',action='store_true',
                        help='Opt-in thread-CPU profile of bounded pure draft validation; no model/robot profiling or replay.')
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--static-root", type=Path)
    parser.add_argument("--engine-status-file", type=Path)
    parser.add_argument("--supervisor-status-file", type=Path)
    parser.add_argument("--launcher-retry-file", type=Path)
    parser.add_argument("--launcher-project-switch-file", type=Path)
    parser.add_argument("--launcher-cancel-file", type=Path)
    parser.add_argument("--engine-result-file", type=Path)
    parser.add_argument("--settings-path", type=Path)
    parser.add_argument('--inference-campaign',type=Path,
                        help='Explicit existing approved evaluation ledger; never accepted from the browser.')
    parser.add_argument('--split-provider-scope',type=Path,
                        help='Explicit host-approved OpenAI observer/NVIDIA planner scope; no production auto-selection.')
    parser.add_argument('--inference-request-cap',type=int,default=5,
                        help='Host-only per-process evaluation cap (1 to 5); never extends campaign approval.')
    parser.add_argument('--experimental-compact-photo',action='store_true',
                        help='Host-only opt-in photo-layout compiler evaluation; never a production default.')
    parser.add_argument('--experimental-planner-no-thinking',action='store_true',
                        help='Host-only Nano Site2.2 template evaluation; requires an approved live campaign.')
    parser.add_argument('--inference-output-token-cap',type=int,
                        help='Explicit approved host evaluation output ceiling (1..10000); defaults unchanged.')
    parser.add_argument('--inference-timeout-s',type=int,default=90,
                        help='Host-only approved evaluation total deadline (90..300s); product default remains 90s.')
    parser.add_argument("--credential-target", default=DEFAULT_CREDENTIAL_TARGET)
    parser.add_argument("--bootstrap-ttl-s", type=float, default=30.0)
    parser.add_argument(
        "--fixture-mode", action="store_true",
        help="Use the explicit deterministic test gateway; never implied by serving the UI.",
    )
    parser.add_argument("--replay-report", type=Path)
    parser.add_argument("--replay-fixture-id")
    parser.add_argument("--offline", action="store_true", help="Disable all provider generation")
    parser.add_argument("--project-id", default="default", help="Existing or new local project name")
    parser.add_argument("--session-history-root", type=Path, default=ROOT,
                        help="Trusted host archive root; independent of project state. No browser override.")
    parser.add_argument("--retry-remaining", type=int, default=0)
    args = parser.parse_args()
    if args.split_provider_scope and (not args.inference_campaign or args.fixture_mode or args.offline or args.replay_report):
        raise SystemExit('Split provider scope requires an explicit live campaign; no fixture/offline/replay')
    if args.inference_timeout_s!=90 and (args.inference_campaign is None or
            not 90<=args.inference_timeout_s<=300 or args.fixture_mode or args.offline or args.replay_report):
        raise SystemExit('Timeout override requires an explicit live campaign and bounded deadline 90..300')
    if args.inference_output_token_cap is not None and (args.inference_campaign is None or
            not 1 <= args.inference_output_token_cap <= 10000):
        raise SystemExit('Output token override requires an explicit live campaign and cap 1..10000')
    if args.experimental_compact_photo and (args.inference_campaign is None or args.fixture_mode or args.offline or args.replay_report):
        raise SystemExit('Experimental compact photo requires an explicit live campaign and no fixture/offline/replay mode')
    if args.inference_campaign is not None and (args.fixture_mode or args.offline or args.replay_report):
        raise SystemExit('Live evaluation campaign cannot mix fixture/offline/replay modes')
    if args.experimental_planner_no_thinking and args.inference_campaign is None:
        raise SystemExit('Experimental template policy requires an explicit live campaign')
    selected_project = checked_project_id(args.project_id)
    product_secret = os.environ.pop("TWINPULSE_PRODUCT_BOOTSTRAP", "")
    engine_secret = os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", "")
    if len(product_secret) < 32 or len(engine_secret) < 32:
        raise SystemExit("Bootstrap environment is missing")
    if (args.replay_report is None) != (args.replay_fixture_id is None):
        raise SystemExit("Replay report and fixture id must be supplied together")
    if args.fixture_mode and args.replay_report is not None:
        raise SystemExit("Fixture generation and stored replay modes are mutually exclusive")
    if args.offline and (args.fixture_mode or args.replay_report is not None):
        raise SystemExit("Offline simulation cannot be combined with fixture or replay")
    replay = (
        load_replay_fixture(args.replay_report, args.replay_fixture_id)
        if args.replay_report is not None else None
    )

    broker = CommandBroker(project_id=selected_project)
    static_root = args.static_root.resolve() if args.static_root is not None else None
    if static_root is not None and not static_root.is_dir():
        raise SystemExit(f"Built product UI not found: {static_root}")
    bridge_fixture = (
        broker.register_artifact("fixed_warehouse_v1", fixed_warehouse_bundle())
        if static_root is None else None
    )
    settings_store = JsonProviderSettingsStore(
        args.settings_path,
        defaults=ProviderSettings(credential_ref=args.credential_target),
    )
    credential_store = WindowsCredentialStore(args.credential_target)
    key_registry = KeyRegistry(settings_store, credential_store)
    # One ledger admission per owned process, not per gateway reconstruction.
    campaign = None
    split_bundle = None
    if args.split_provider_scope is not None:
        from twinpulse_app.split_evaluation import load_evaluation_scope
        split_bundle = load_evaluation_scope(args.split_provider_scope, args.inference_campaign,
            request_cap=args.inference_request_cap)
        campaign = split_bundle[-1]
    elif args.inference_campaign is not None:
        from twinpulse_provider.reliability import CampaignLedger
        campaign = CampaignLedger.open_existing_approved(args.inference_campaign,
            run_request_cap=args.inference_request_cap)

    def gateway():
        if replay is not None or args.offline:
            return ReplayOnlyGateway()
        if split_bundle is not None:
            from twinpulse_app.split_evaluation import build_scoped_split_service
            return build_scoped_split_service(*split_bundle,
                evidence_root=settings_store.path.parent/'provider-evidence',timeout_s=float(args.inference_timeout_s),
                compact_photo_layout=args.experimental_compact_photo,
                planner_template_no_thinking=args.experimental_planner_no_thinking,
                output_token_cap=args.inference_output_token_cap or 10000)
        if not args.fixture_mode and campaign is None:
            from twinpulse_app.stage_routing import build_configured_stage_service
            staged = build_configured_stage_service(key_registry,
                evidence_root=settings_store.path.parent/'provider-evidence')
            if staged is not None:
                return staged
        settings = settings_store.load().validated()
        active_credential = key_registry.resolve(settings)
        capabilities = ProviderCapabilities(
            supports_images=settings.supports_images,
            supports_structured_output=settings.supports_structured_output,
            max_images=settings.max_images,
            accepted_mime_types=settings.accepted_mime_types,
        )
        if args.fixture_mode:
            return GenerationService(
                MockProvider(),
                ProviderConfig(
                    base_url="https://fixture.invalid/v1/", endpoint_path="responses",
                    model_id="twinpulse-explicit-fixture", api_key_env="TWINPULSE_UNUSED_FIXTURE_KEY",
                    capabilities=capabilities, timeout_s=10.0, max_attempts=1,
                ),
            )
        # This backend owns the chat-first site product. Do not rewrite saved
        # provider settings or change the legacy composition default.
        return build_live_generation_service(settings, active_credential.load, timeout_s=float(args.inference_timeout_s),
            plan_version="2.2" if settings.adapter_kind == "nebius_chat_completions_pipeline" else None,
            evidence_root=settings_store.path.parent/'provider-evidence',campaign=campaign,
            compact_photo_layout=args.experimental_compact_photo,
            planner_template_no_thinking=args.experimental_planner_no_thinking,
            output_token_cap=args.inference_output_token_cap)

    def generation_settings() -> dict[str, str]:
        if args.offline:
            return {"request_schema": "offline-1.0"}
        if replay is not None:
            return dict(replay.input_revision.generation_settings)
        if args.fixture_mode:
            return {
                "base_url": "https://fixture.invalid/v1/", "model_id": "twinpulse-explicit-fixture",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            }
        if split_bundle is not None:
            from twinpulse_provider.scene_contract import GROUNDING_REVISION, PROPOSAL_REVISION
            scope, observer, _, planner, _, _ = split_bundle
            return {'base_url':planner.base_url,'model_id':scope['planner_model'],
                'observer_model_id':scope['observer_model'],'observer_base_url':observer.base_url,
                'adapter_kind':'explicit_split_chat_pipeline','provider_profile':'host_approved_split_evaluation',
                'endpoint_path':'chat/completions','reasoning_effort':observer.reasoning_effort,
                'request_schema':GROUNDING_REVISION if args.experimental_compact_photo else PROPOSAL_REVISION,
                'image_detail':'auto','site_plan_version':'2.2'}
        if campaign is None:
            from twinpulse_app.stage_routing import StageRoutingSettings
            staged = StageRoutingSettings(key_registry).metadata()
            if staged is not None:
                return staged
        value = settings_store.load().validated()
        from twinpulse_app.provider_composition import generation_request_schema
        return {
            "base_url": value.base_url, "model_id": value.model_id,
            "reasoning_effort": value.reasoning_effort,
            "adapter_kind": value.adapter_kind,
            "provider_profile": value.provider_profile,
            "endpoint_path": value.endpoint_path,
            "observer_model_id": value.observer_model_id,
            "fallback_observer_model_id": value.fallback_observer_model_id,
            "image_detail": "auto", "request_schema": generation_request_schema(value.adapter_kind,
                compact_photo_layout=args.experimental_compact_photo),
            "site_plan_version": "2.2" if value.adapter_kind == "nebius_chat_completions_pipeline" else "1.0",
        }

    def provider_state() -> dict[str, object]:
        if args.offline:
            return {"configured": False, "label": "Offline simulation (provider disabled)"}
        if replay is not None:
            return {"configured": False, "label": "Stored M2-C replay (zero provider calls)"}
        if split_bundle is not None:
            scope, _, observer_key, _, planner_key, _ = split_bundle
            return {'configured':observer_key.is_configured() and planner_key.is_configured(),
                'label':scope['observer_model']+' via OpenAI -> '+scope['planner_model']+
                    (' via OpenAI' if scope['schema_version']=='gpt-evaluation-1.0' else ' via Nebius')+' (explicit evaluation)'}
        if not args.fixture_mode and campaign is None:
            from twinpulse_app.stage_routing import StageRoutingSettings
            routes = StageRoutingSettings(key_registry)
            stage = routes.metadata()
            if stage is not None:
                route = routes.load()
                configured = all(key_registry.resolve(key_registry.settings_for_entry(v['key_id'])).is_configured()
                                 for v in (route['observer'], route['planner']))
                return {'configured': configured,
                    'label': stage['observer_model_id']+' via '+stage['observer_base_url']+' → '+
                        stage['model_id']+' via '+stage['base_url']+' (saved stage settings)'}
        value = settings_store.load().validated()
        return {
            "configured": True if args.fixture_mode else key_registry.resolve(value).is_configured(),
            "label": (
                "Explicit deterministic fixture"
                if args.fixture_mode else (
                    f"{value.observer_model_id} -> {value.model_id} via {value.adapter_kind}"
                    if value.observer_model_id else f"{value.model_id} via {value.adapter_kind}"
                )
            ),
        }

    # Keep the R4 engine-only bridge usable without product generation.
    def make_workflow(project_id, project_broker):
        if static_root is None:return None
        state_root = settings_store.path.parent
        selected_store = ProjectStore.for_project(state_root, project_id)
        application = ApplicationService(
            gateway(),
            project_store=selected_store,
            artifact_store=InputArtifactStore(selected_store.input_root()),
            project_id=project_id,
            allow_invalid_restore=True,
            profile_generation=args.profile_generation,
            launch_execution_id=os.environ.get('TWINPULSE_LAUNCH_EXECUTION_ID'),
            launch_id=os.environ.get('TWINPULSE_LAUNCH_ID'),
        )
        workflow = ProductWorkflow(
            application, project_broker,
            mode=("simulation_offline" if args.offline else "replay" if replay is not None else "explicit_fixture" if args.fixture_mode else "live_provider"),
            generation_settings_getter=generation_settings,
            provider_state_getter=provider_state,
            gateway_factory=gateway,
        )
        if replay is not None:
            workflow.load_replay(replay)
        if not args.fixture_mode and not args.offline and replay is None and campaign is None:
            from twinpulse_app.product_inference import ProductGenerationActions
            workflow.generation_approvals = ProductGenerationActions(key_registry, workflow)
        return workflow
    workflow = make_workflow(selected_project,broker)
    devices = None
    if workflow is not None and not args.fixture_mode and replay is None:
        from twinpulse_app.workspace_devices import WorkspaceDevices
        devices = WorkspaceDevices.from_paths(ROOT, settings_store.path.parent,
            physical_enabled=os.environ.get('TWINPULSE_SIM_ONLY') != '1',
            observation_enabled=os.environ.get('TWINPULSE_ROBOT_OBSERVATION') == '1')
    history_root = (devices.controller.root.resolve() if devices is not None and devices.controller is not None
                    else args.session_history_root.resolve())
    server = LocalApiServer(
        broker,
        product_bootstrap_secret=product_secret,
        engine_bootstrap_secret=engine_secret,
        port=args.port,
        port_candidates=args.port_candidates,
        product_workflow=workflow,
        static_root=static_root,
        supervisor_status_file=args.supervisor_status_file,
        launcher_retry_file=args.launcher_retry_file,
        launcher_project_switch_file=args.launcher_project_switch_file,
        launcher_cancel_file=args.launcher_cancel_file,
        launcher_shutdown_file=args.launcher_shutdown_file,
        engine_result_file=args.engine_result_file,
        launcher_retry_remaining=args.retry_remaining,
        provider_settings_store=settings_store,
        credential_store=credential_store,
        key_registry=key_registry,
        workspace_devices=devices,
        bootstrap_ttl_s=args.bootstrap_ttl_s,
        session_history_root=history_root if workflow is not None else None,
        project_catalog=(ProjectCatalog(settings_store.path.parent, selected_project)
                         if workflow is not None else None),
    )
    if workflow is not None and replay is None:
        from twinpulse_app.persistent_workspace import PersistentWorkspace
        def make_context(project_id):
            project_broker=CommandBroker(project_id=project_id)
            return LocalApiServer(project_broker,virtual=True,
                product_bootstrap_secret=product_secret,engine_bootstrap_secret=engine_secret,
                product_workflow=make_workflow(project_id,project_broker),static_root=static_root,
                supervisor_status_file=args.supervisor_status_file,
                launcher_retry_file=args.launcher_retry_file,launcher_cancel_file=args.launcher_cancel_file,
                launcher_shutdown_file=args.launcher_shutdown_file,
                engine_result_file=args.engine_result_file,launcher_retry_remaining=args.retry_remaining,
                provider_settings_store=settings_store,credential_store=credential_store,key_registry=key_registry,
                bootstrap_ttl_s=args.bootstrap_ttl_s,
                workspace_devices=devices,session_history_root=history_root,
                project_catalog=ProjectCatalog(settings_store.path.parent,project_id))
        PersistentWorkspace(server,make_context)
    server.start()
    stop = Event()

    def request_stop(_signal: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    ready = {
        "pid": os.getpid(), "base_url": server.base_url,
        "artifact_id": bridge_fixture.artifact_id if bridge_fixture is not None else None,
        "revision": bridge_fixture.revision if bridge_fixture is not None else None,
        "generation_mode": (
            "simulation_offline" if args.offline else "replay" if replay is not None else "explicit_fixture" if args.fixture_mode else "live_provider"
        ),
        "ui_url": server.base_url + "/" if static_root is not None else None,
    }
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.ready_file.with_suffix(args.ready_file.suffix + ".tmp")
    temporary.write_text(json.dumps(ready, sort_keys=True), encoding="utf-8")
    temporary.replace(args.ready_file)
    print(f"TWINPULSE_BACKEND_READY port={server.port}", flush=True)
    next_status_write = 0.0
    status_sample_id=0
    try:
        while not stop.wait(0.2):
            if args.backend_stop_file is not None and args.backend_stop_file.is_file():
                try:
                    value = json.loads(args.backend_stop_file.read_text(encoding='utf-8'))
                    if value == {'schema_version': '1.0', 'action': 'stop_backend'}:
                        break
                except (OSError, ValueError):
                    pass
            if args.engine_status_file is not None and time.monotonic() >= next_status_write:
                active_broker=server.workspace.active.broker if server.workspace else broker
                engine_state=active_broker.supervisor_state()
                devices.set_engine_process_probe_blocked(bool(engine_state.get('engine_session_id') and not engine_state.get('engine_connected')))
                status_sample_id+=1
                published=_publish_engine_status(args.engine_status_file,active_broker,
                    sample_id=status_sample_id,physical_runtime_active=devices.physical_runtime_active(),state=engine_state)
                # Optional heartbeat persistence must not kill the whole API on
                # ENOSPC, nor flood failed temporary files every 200 ms.
                next_status_write=time.monotonic()+(1.0 if published else 5.0)
    finally:
        server.stop()
    return 0


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        for attempt in range(50):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass


def _publish_engine_status(path, broker, *, sample_id=None, physical_runtime_active=None,state=None):
    try:
        _write_json_atomic(path, {"schema_version":"1.0",
            "sampled_at_utc":datetime.now(timezone.utc).isoformat(),
            "status_sample_id":sample_id,"physical_runtime_active":physical_runtime_active,**(state if state is not None else broker.supervisor_state())})
        return True
    except OSError:
        if broker.diagnostics is not None:broker.diagnostics.note_storage_error()
        return False


if __name__ == "__main__":
    raise SystemExit(main())
