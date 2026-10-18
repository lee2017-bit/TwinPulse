# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Zero-model-call configuration readback; explicit --apply-recommended only.

Never prints keys, credential references or input photos. Not live acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore, DEFAULT_CREDENTIAL_TARGET
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service
from twinpulse_core import InputRevision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings-path', type=Path)
    parser.add_argument('--apply-recommended', action='store_true')
    parser.add_argument('--apply-physical-ai', action='store_true',
        help='Apply the reviewed Flash/Super profile, preserving prior metadata in a snapshot')
    parser.add_argument('--model-catalog', type=Path,
        help='Reviewed saved catalog to install for --apply-physical-ai; no metadata lookup')
    parser.add_argument('--planner-output-tokens',type=int,help='Explicitly update only the saved planner output cap; no model call')
    parser.add_argument('--generation-timeout-s',type=int,help='Explicitly update the total generation deadline; no model call')
    args = parser.parse_args()
    network_attempts = []
    def forbidden(*_args, **_kwargs):
        network_attempts.append(True)
        raise AssertionError('Configuration verification must not access the network')
    previous_create, previous_connect = socket.create_connection, socket.socket.connect
    try:
        socket.create_connection = forbidden
        socket.socket.connect = forbidden
        _verify(args, network_attempts)
    finally:
        socket.create_connection, socket.socket.connect = previous_create, previous_connect


def _verify(args, network_attempts):
    store = JsonProviderSettingsStore(args.settings_path)
    registry = KeyRegistry(store, WindowsCredentialStore(DEFAULT_CREDENTIAL_TARGET))
    routes = StageRoutingSettings(registry)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    preserved = {path: digest(path) for path in (store.path, registry.path)}
    state = registry.state()['stage_routing']
    snapshot_path = None
    if args.model_catalog and not args.apply_physical_ai:
        raise SystemExit('--model-catalog requires --apply-physical-ai')
    if args.apply_physical_ai:
        from datetime import datetime, timezone
        from uuid import uuid4
        from twinpulse_provider.model_contracts import catalog_sha, checked_catalog
        catalog_path = routes.path.with_name('stage_model_catalog.json')
        prior_catalog = catalog_path.read_bytes() if catalog_path.exists() else None
        previous_route = routes.load()
        if args.model_catalog:
            if args.model_catalog.stat().st_size > 262144:
                raise SystemExit('Catalog exceeds the reviewed metadata size limit')
            candidate = checked_catalog(json.loads(args.model_catalog.read_text(encoding='utf-8')),
                                        now=datetime.now(timezone.utc))
            from twinpulse_provider.model_contracts import load_catalog
            candidate = load_catalog(args.model_catalog, catalog_sha(candidate), now=datetime.now(timezone.utc))
        else:
            candidate = routes.available_catalog()
        if candidate is None:
            raise SystemExit('Current reviewed Flash/Super model metadata is missing; nothing changed')
        # Resolve the exact requested combination before touching persisted files.
        from twinpulse_provider.model_contracts import model_supported
        options = {stage: [] for stage in ('observer','planner')}
        for entry in registry.state()['entries']:
            value = registry.settings_for_entry(entry['id'])
            if routes.provider(value) != 'nebius':
                continue
            for stage in options:
                options[stage].extend(dict(key_id=entry['id'],model_id=row['model_id'],
                    provider='nebius',configured=entry['configured']) for row in candidate['models']
                    if model_supported(candidate,stage,row['model_id']))
        selected = routes.physical_ai_recommendation(options,candidate)
        if selected is None:
            raise SystemExit('The reviewed Flash/Super combination or Nebius credential is unavailable; nothing changed')
        snapshot_path = routes.path.with_name('stage-route-before-physical-ai-'+uuid4().hex+'.json')
        snapshot_path.write_text(json.dumps({'schema_version':'stage-route-snapshot-1.0',
            'route':previous_route,'catalog_sha256':digest(catalog_path),
            'provider_settings_sha256':preserved[store.path],
            'key_metadata_sha256':preserved[registry.path]},ensure_ascii=False),encoding='utf-8')
        try:
            temporary = catalog_path.with_name('.stage-model-catalog-'+uuid4().hex+'.tmp')
            try:
                with temporary.open('xb') as stream:
                    stream.write(json.dumps(candidate,ensure_ascii=False).encode('utf-8'))
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,catalog_path)
            finally:
                temporary.unlink(missing_ok=True)
            # Both metadata and route belong to this explicitly approved apply.
            # The existing backend must restart to reconstruct its gateway.
            selected = routes.validate(selected)
            with registry.lock:
                routes._save(selected)
                build_configured_stage_service(registry)
        except Exception:
            if prior_catalog is None:
                catalog_path.unlink(missing_ok=True)
            else:
                catalog_path.write_bytes(prior_catalog)
            routes._save(previous_route)
            raise
        state = registry.state()['stage_routing']
    if args.apply_recommended:
        if not state['recommended']:
            raise SystemExit('The reviewed Flash/Super profile needs a Nebius key and current catalog; nothing changed')
        # No implicit overwrite of a later user-selected combination.
        if state['route'] is not None and state['route'] != state['recommended']:
            raise SystemExit('An explicit saved route exists; change it through settings instead')
        routes.save(state['recommended'], lambda: build_configured_stage_service(registry))
    if args.planner_output_tokens is not None or args.generation_timeout_s is not None:
        route = routes.load()
        if route is None:raise SystemExit('No saved stage route; nothing changed')
        if args.planner_output_tokens is not None:
            route['planner']['max_output_tokens'] = args.planner_output_tokens
        if args.generation_timeout_s is not None:
            route['generation_timeout_s'] = args.generation_timeout_s
        routes.save(route, lambda:build_configured_stage_service(registry))
    restarted = KeyRegistry(store, WindowsCredentialStore(DEFAULT_CREDENTIAL_TARGET))
    service = build_configured_stage_service(restarted)
    metadata = StageRoutingSettings(restarted).metadata()
    if metadata:
        InputRevision.create(prompt='configuration check only', images=(), measurement_constraints=(),
            generation_settings=metadata, profile_id='offline')
    assert not network_attempts
    assert all(digest(path) == value for path, value in preserved.items())
    print(json.dumps({'status':'PASS', 'scope':'configuration only, not live generation',
        'saved_stage_route': metadata is not None, 'generation_gateway_composed': service is not None,
        'provider_settings_and_key_metadata_unchanged': True, 'network_calls':0, 'robot_commands':0,
        'observer_model': metadata.get('observer_model_id') if metadata else None,
        'planner_model': metadata.get('model_id') if metadata else None,
        'observer_max_output_tokens':metadata.get('observer_max_output_tokens') if metadata else None,
        'planner_max_output_tokens':metadata.get('planner_max_output_tokens') if metadata else None,
        'generation_timeout_s':metadata.get('generation_timeout_s') if metadata else None,
        'composed_total_timeout_s':service._config.timeout_s if service else None,
        'stop_on_output_limit':True,
        'model_catalog_sha256':metadata.get('model_catalog_sha256') if metadata else None,
        'generation_policy_sha256':metadata.get('generation_policy_sha256') if metadata else None,
        'composed_whole_generation_timeout_s':getattr(service._provider,'total_timeout_s',None) if service else None,
        'previous_route_snapshot':str(snapshot_path) if snapshot_path else None,
        'requires_existing_backend_restart':True}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
