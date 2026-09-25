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
    ProviderSettings,
    WindowsCredentialStore,
    ReplayOnlyGateway,
    build_live_generation_service,
    load_replay_fixture,
)
from twinpulse_app.credentials import DEFAULT_CREDENTIAL_TARGET  # noqa: E402
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
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--static-root", type=Path)
    parser.add_argument("--engine-status-file", type=Path)
    parser.add_argument("--supervisor-status-file", type=Path)
    parser.add_argument("--settings-path", type=Path)
    parser.add_argument("--credential-target", default=DEFAULT_CREDENTIAL_TARGET)
    parser.add_argument("--bootstrap-ttl-s", type=float, default=30.0)
    parser.add_argument(
        "--fixture-mode", action="store_true",
        help="Use the explicit deterministic test gateway; never implied by serving the UI.",
    )
    parser.add_argument("--replay-report", type=Path)
    parser.add_argument("--replay-fixture-id")
    args = parser.parse_args()
    product_secret = os.environ.pop("TWINPULSE_PRODUCT_BOOTSTRAP", "")
    engine_secret = os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", "")
    if len(product_secret) < 32 or len(engine_secret) < 32:
        raise SystemExit("Bootstrap environment is missing")
    if (args.replay_report is None) != (args.replay_fixture_id is None):
        raise SystemExit("Replay report and fixture id must be supplied together")
    if args.fixture_mode and args.replay_report is not None:
        raise SystemExit("Fixture generation and stored replay modes are mutually exclusive")
    replay = (
        load_replay_fixture(args.replay_report, args.replay_fixture_id)
        if args.replay_report is not None else None
    )

    broker = CommandBroker()
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

    def gateway():
        if replay is not None:
            return ReplayOnlyGateway()
        settings = settings_store.load().validated()
        if settings.credential_ref != credential_store.target_name:
            raise ProviderConfigurationError("provider credential reference does not match the active secure store")
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
        return build_live_generation_service(settings, credential_store.load, timeout_s=90.0)

    def generation_settings() -> dict[str, str]:
        if replay is not None:
            return dict(replay.input_revision.generation_settings)
        if args.fixture_mode:
            return {
                "base_url": "https://fixture.invalid/v1/", "model_id": "twinpulse-explicit-fixture",
                "reasoning_effort": "low", "image_detail": "auto", "request_schema": "1.0",
            }
        value = settings_store.load().validated()
        return {
            "base_url": value.base_url, "model_id": value.model_id,
            "reasoning_effort": value.reasoning_effort,
            "adapter_kind": value.adapter_kind,
            "provider_profile": value.provider_profile,
            "endpoint_path": value.endpoint_path,
            "observer_model_id": value.observer_model_id,
            "fallback_observer_model_id": value.fallback_observer_model_id,
            "image_detail": "auto", "request_schema": "1.0",
        }

    def provider_state() -> dict[str, object]:
        if replay is not None:
            return {"configured": False, "label": "Stored M2-C replay (zero provider calls)"}
        value = settings_store.load().validated()
        return {
            "configured": True if args.fixture_mode else credential_store.is_configured(),
            "label": (
                "Explicit deterministic fixture"
                if args.fixture_mode else (
                    f"{value.observer_model_id} -> {value.model_id} via {value.adapter_kind}"
                    if value.observer_model_id else f"{value.model_id} via {value.adapter_kind}"
                )
            ),
        }

    # Keep the R4 engine-only bridge usable without product generation.
    workflow = None
    if static_root is not None:
        state_root = settings_store.path.parent
        application = ApplicationService(
            gateway(),
            project_store=ProjectStore(state_root / "active_project.json"),
            artifact_store=InputArtifactStore(state_root / "inputs"),
            allow_invalid_restore=True,
        )
        workflow = ProductWorkflow(
            application, broker,
            mode=("replay" if replay is not None else "explicit_fixture" if args.fixture_mode else "live_provider"),
            generation_settings_getter=generation_settings,
            provider_state_getter=provider_state,
            gateway_factory=gateway,
        )
        if replay is not None:
            workflow.load_replay(replay)
    server = LocalApiServer(
        broker,
        product_bootstrap_secret=product_secret,
        engine_bootstrap_secret=engine_secret,
        port=args.port,
        product_workflow=workflow,
        static_root=static_root,
        supervisor_status_file=args.supervisor_status_file,
        provider_settings_store=settings_store,
        credential_store=credential_store,
        bootstrap_ttl_s=args.bootstrap_ttl_s,
    )
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
            "replay" if replay is not None else "explicit_fixture" if args.fixture_mode else "live_provider"
        ),
        "ui_url": server.base_url + "/" if static_root is not None else None,
    }
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.ready_file.with_suffix(args.ready_file.suffix + ".tmp")
    temporary.write_text(json.dumps(ready, sort_keys=True), encoding="utf-8")
    temporary.replace(args.ready_file)
    print(f"TWINPULSE_BACKEND_READY port={server.port}", flush=True)
    try:
        while not stop.wait(0.2):
            if args.engine_status_file is not None:
                _write_json_atomic(args.engine_status_file, {
                    "schema_version": "1.0",
                    "sampled_at_utc": datetime.now(timezone.utc).isoformat(),
                    **broker.supervisor_state(),
                })
    finally:
        server.stop()
    return 0


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    try:
        for attempt in range(50):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
