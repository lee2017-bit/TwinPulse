# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The October13 user-approved USD10 public-photo acceptance; metadata only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from scripts.compare_model_roles_live import metadata_get
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings
from twinpulse_provider.reliability import CampaignLedger
from twinpulse_provider.model_contracts import catalog_from_inventory, catalog_prices


def main():
    output = ROOT/'outputs/product-flow-20261013/device-authorized-live'
    output.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    store = JsonProviderSettingsStore()
    registry = KeyRegistry(store, WindowsCredentialStore())
    route = StageRoutingSettings(registry).load()
    models = ['deepseek-ai/DeepSeek-V4.1-Flash', 'nvidia/nemotron-3-super-120b-a12b']
    if [route[s]['model_id'] for s in ('observer', 'planner')] != models:
        raise ValueError('Existing Flash/Super route changed')
    key = registry.resolve(registry.settings_for_entry(route['observer']['key_id']))
    info, digest = metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info', key)
    visible, visible_digest = metadata_get('https://api.tokenfactory.nebius.com/v1/models', key)
    identities = {r['id'] for r in visible['data']}
    rows = []
    for model in models:
        row = next(r for group in info for r in group.get('flavors', []) if r.get('model_id') == model)
        if model not in identities:
            raise ValueError('Selected model unavailable')
        rows.append(dict(provider='nebius', model_id=model, visible=True, use_cases=row['use_cases'],
                         context_tokens=row['max_model_len'], input_per_million=str(row['input_price_per_million_tokens']),
                         output_per_million=str(row['output_price_per_million_tokens'])))
    expires = (now + timedelta(hours=6)).isoformat()
    catalog = catalog_from_inventory(dict(created_at=now.isoformat(), catalog_sha256=digest, models=rows), valid_until=expires)
    cases = json.loads((ROOT/'outputs/product-flow-20261013/device-public-inputs/cases.json').read_text(encoding='utf-8'))
    inputs = [dict(id=case['id'], prompt_sha256=hashlib.sha256(case['prompt'].encode()).hexdigest(),
                   photo_sha256=hashlib.sha256(Path(case['image']).read_bytes()).hexdigest() if case['image'] else None)
              for case in cases]
    scope = dict(schema_version='product-live-test-1.0', approval_id='device-flow-20261013-user-usd10',
                 authorization='User: proceed with actual tests; new public photo download/use; USD10 allowed; no separate approval wait',
                 approved_at=now.isoformat(), expires_at=expires, total_authorized_usd='10.00',
                 carried_unknown_usd='3.00', limit_usd='7.00', max_generations=6, max_requests=72,
                 per_generation_requests=12, max_repairs=3, model_ids=models,
                 origin='https://api.tokenfactory.nebius.com/v1/', inputs=inputs,
                 input_purpose='Three public/text cases, their Isaac renders, and natural-language editing feedback. No private photos or robot data.',
                 prices=catalog_prices(catalog), metadata_gets=2, visible_sha256=visible_digest)
    (output/'authorization.json').write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'catalog.json').write_text(json.dumps(catalog, indent=2), encoding='utf-8')
    CampaignLedger(output/'agent-test.ledger.json', approval=scope['approval_id'], rates=scope['prices'],
                   limit_usd='7.00', max_requests=72)
    print(json.dumps(dict(status='READY', metadata_gets=2, inference_requests=0, expires_at=expires)), flush=True)


if __name__ == '__main__':
    main()
