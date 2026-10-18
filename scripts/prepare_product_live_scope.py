# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Freeze this explicitly approved USD2/two-hour test; metadata GET only."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.compare_model_roles_live import metadata_get
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings
from twinpulse_provider.reliability import CampaignLedger
from twinpulse_provider.model_contracts import catalog_from_inventory,catalog_prices

def main():
    output=(ROOT/'outputs/product-flow-20261013/authorized-live').resolve()
    output.mkdir(parents=True,exist_ok=False)
    now=datetime.now(timezone.utc)
    store=JsonProviderSettingsStore();registry=KeyRegistry(store,WindowsCredentialStore())
    route=StageRoutingSettings(registry).load()
    models=['deepseek-ai/DeepSeek-V4.1-Flash','nvidia/nemotron-3-super-120b-a12b']
    if [route[s]['model_id'] for s in ('observer','planner')]!=models:raise ValueError('Selected route changed')
    credential=registry.resolve(registry.settings_for_entry(route['observer']['key_id']))
    info,sha=metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info',credential)
    visible,visible_sha=metadata_get('https://api.tokenfactory.nebius.com/v1/models',credential)
    identities={r['id'] for r in visible['data']};rows=[]
    for model in models:
        row=next(r for group in info for r in group.get('flavors',[]) if r.get('model_id')==model)
        if model not in identities:raise ValueError('Selected model is unavailable')
        rows.append(dict(provider='nebius',model_id=model,visible=True,use_cases=row['use_cases'],
            context_tokens=row['max_model_len'],input_per_million=str(row['input_price_per_million_tokens']),
            output_per_million=str(row['output_price_per_million_tokens'])))
    catalog=catalog_from_inventory(dict(created_at=now.isoformat(),catalog_sha256=sha,models=rows),
        valid_until=(now+timedelta(hours=2)).isoformat())
    photos=ROOT/'outputs/benchmark-overnight-20261011'
    inputs=[dict(name=name,sha256=hashlib.sha256((photos/name).read_bytes()).hexdigest())
            for name in ('public-bedroom-1280.jpg','public-living.jpg','public-dining.jpg')]
    scope=dict(schema_version='product-live-test-1.0',authorization='User: 명시한 범위·추가 USD2·2시간 승인',
        approved_at=now.isoformat(),expires_at=(now+timedelta(hours=2)).isoformat(),limit_usd='2.00',
        max_generations=6,max_requests=72,per_generation_requests=12,max_repairs=3,
        model_ids=models,origin='https://api.tokenfactory.nebius.com/v1/',inputs=inputs,
        input_purpose='Public CC BY-SA room photos, derived Isaac renders, and six stated test descriptions',
        prices=catalog_prices(catalog),metadata_gets=2,inference_requests=0,visible_sha256=visible_sha)
    (output/'authorization.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    CampaignLedger(output/'agent-test.ledger.json',approval='product-live-20261013-user-usd2',
        rates=scope['prices'],limit_usd='2.00',max_requests=72)
    print(json.dumps(dict(status='READY',metadata_gets=2,inference_requests=0,expires_at=scope['expires_at'])),flush=True)
if __name__=='__main__':main()
