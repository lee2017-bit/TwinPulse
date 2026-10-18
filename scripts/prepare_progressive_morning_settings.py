# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit normal-App configuration, fresh metadata only and zero inference.

Preserves the registered OS credential and the prior settings/catalog bytes.
The existing Flash/Super route must already be selected. This does not grant
inference spending, motion, live sensors or availability beyond metadata review.
"""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))
from scripts.compare_model_roles_live import metadata_get
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.model_contracts import catalog_from_inventory, catalog_sha

OBSERVER = 'deepseek-ai/DeepSeek-V4.1-Flash'
PLANNER = 'nvidia/nemotron-3-super-120b-a12b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'outputs/progressive-twin-overnight-20261012'):
        raise ValueError('OWNED_LOCAL_OUTPUT_REQUIRED')
    if list((ROOT / 'outputs/progressive-twin-overnight-20261012').glob('fresh-functional-*/functional-owner.lock')):
        raise ValueError('PAID_OWNER_MUST_BE_CLOSED')
    output.mkdir(exist_ok=False)
    store = JsonProviderSettingsStore()
    registry = KeyRegistry(store, WindowsCredentialStore())
    routes = StageRoutingSettings(registry)
    route = routes.load()
    if route is None or route['observer']['model_id'] != OBSERVER or route['planner']['model_id'] != PLANNER:
        raise ValueError('USER_SELECTED_OTHER_ROUTE_NOT_OVERWRITTEN')
    old_route = json.loads(json.dumps(route))
    catalog_path = routes.path.with_name('stage_model_catalog.json')
    old_catalog = catalog_path.read_bytes() if catalog_path.exists() else None
    snapshots = {}
    for path in (store.path, registry.path, routes.path, catalog_path):
        if path.exists():
            content = path.read_bytes()
            (output / (path.name + '.before')).write_bytes(content)
            snapshots[path.name] = hashlib.sha256(content).hexdigest()
    credential = registry.resolve(registry.settings_for_entry(route['observer']['key_id']))
    metadata, metadata_sha = metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info', credential)
    available, available_sha = metadata_get('https://api.tokenfactory.nebius.com/v1/models', credential)
    identities = {entry['id'] for entry in available['data']}
    models = []
    for model in (OBSERVER, PLANNER):
        rows = [row for group in metadata for row in group.get('flavors', []) if row.get('model_id') == model]
        if len(rows) != 1 or model not in identities:
            raise ValueError('EXISTING_MODEL_UNAVAILABLE')
        row = rows[0]
        models.append(dict(provider='nebius', model_id=model, visible=True, use_cases=row['use_cases'],
            context_tokens=row['max_model_len'], input_per_million=str(row['input_price_per_million_tokens']),
            output_per_million=str(row['output_price_per_million_tokens'])))
    now = datetime.now(timezone.utc)
    inventory = dict(created_at=now.isoformat(), catalog_sha256=metadata_sha,
                     account_models_sha256=available_sha, models=models)
    catalog = catalog_from_inventory(inventory, valid_until=(now + timedelta(hours=24)).isoformat())
    policy = replace(GenerationPolicy(), initial_timeout_s=420, final_timeout_s=180,
                     external_final_review=True)
    for stage in ('observer', 'planner'):
        route[stage]['max_output_tokens'] = 40000
    route.update(generation_timeout_s=300, generation_policy=policy.to_dict(), model_catalog_sha256=catalog_sha(catalog))
    try:
        # The old route is already read and bound to the old catalog above.
        # save() would re-read that old route after the catalog SHA changes,
        # incorrectly treating the paired refresh as corrupt settings. Keep the
        # pair under the registry lock and use the normal validated store writer.
        with registry.lock:
            catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
            selected = routes.validate(route)
            for stage in ('observer', 'planner'):
                choice = selected[stage]
                if not registry.resolve(registry.settings_for_entry(choice['key_id'])).is_configured():
                    raise ValueError('EXISTING_KEY_UNAVAILABLE')
            routes._save(selected)
            build_configured_stage_service(registry)
        restarted = StageRoutingSettings(KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore()))
        if restarted.load() != routes.validate(route):
            raise ValueError('NORMAL_APP_ROUTE_READBACK_CHANGED')
        if restarted.available_catalog() != catalog:
            raise ValueError('NORMAL_APP_CATALOG_READBACK_CHANGED')
    except Exception:
        if old_catalog is not None:
            catalog_path.write_bytes(old_catalog)
        else:
            catalog_path.unlink(missing_ok=True)
        routes.path.write_bytes((output / (routes.path.name + '.before')).read_bytes())
        raise
    preserved = all(hashlib.sha256(path.read_bytes()).hexdigest() == snapshots[path.name]
                    for path in (store.path, registry.path) if path.name in snapshots)
    if not preserved:
        raise ValueError('PROVIDER_OR_KEY_METADATA_CHANGED')
    evidence = dict(status='CONFIGURATION_READBACK_PASS_NOT_RUNTIME', metadata_gets=2, inference_calls=0,
        physical_connections=0, observer_model=OBSERVER, planner_model=PLANNER, output_tokens=40000,
        policy=policy.to_dict(), catalog_valid_until=catalog['valid_until'],
        provider_and_key_metadata_unchanged=preserved, before_sha256=snapshots,
        after_route_sha256=hashlib.sha256(routes.path.read_bytes()).hexdigest(),
        after_catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        inference_requires_ordinary_user_approval=True)
    with (output / 'result.json').open('x', encoding='utf-8') as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: evidence[key] for key in ('status', 'metadata_gets', 'inference_calls',
        'physical_connections', 'observer_model', 'planner_model', 'output_tokens', 'catalog_valid_until')}))


if __name__ == '__main__':
    main()
