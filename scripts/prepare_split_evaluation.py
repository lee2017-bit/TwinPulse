# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prepare this explicitly approved ten-call scope. Metadata GET only, no inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/name/'src'))
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.split_evaluation import SplitEvaluationLedger, OPENAI_MINI_SNAPSHOT, NANO
from twinpulse_provider.nebius_pipeline import _RejectRedirects
from twinpulse_provider.reliability import utc_now

def nebius_rate(registry, planner):
    from decimal import Decimal
    key = registry.resolve(planner).load()
    if not key:
        raise ValueError('Registered planner credential unavailable')
    url = 'https://api.tokenfactory.nebius.com/private/v1/models_info'
    with urllib.request.build_opener(_RejectRedirects()).open(
            urllib.request.Request(url, headers={'Authorization': 'Bearer '+key}), timeout=20) as response:
        if response.geturl() != url:
            raise ValueError('Metadata redirect refused')
        raw = response.read(2000001)
    key = None
    if len(raw) > 2000000:
        raise ValueError('Metadata size exceeded')
    found = [f for r in json.loads(raw) for f in r.get('flavors', []) if f.get('model_id') == NANO]
    if len(found) != 1:
        raise ValueError('Exact planner price not available')
    item = found[0]
    planner_rate = dict(input_per_million=str(item['input_price_per_million_tokens']),
        output_per_million=str(item['output_price_per_million_tokens']), context_tokens=item['max_model_len'],
        source=url, source_sha256=hashlib.sha256(raw).hexdigest(), verified_at=utc_now())
    if (Decimal(planner_rate['input_per_million']) > Decimal('.06')
            or Decimal(planner_rate['output_per_million']) > Decimal('.24')):
        raise ValueError('Planner cost increased; stop before inference')
    return planner_rate

def main(args):
    registry = KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore())
    entries = registry.state()['entries']
    observers = [r for r in entries if r['active'] and r['provider_profile'] == 'openai' and r['model_id'] == 'gpt-5.4-mini']
    planners = observers if args.planner=='openai' else [r for r in entries
        if r['provider_profile'] in {'nebius_token_factory','nebius_site_v2'} and r['model_id']==NANO]
    if len(observers)!=1 or len(planners)!=1:
        raise ValueError('Exact existing stage registrations required; ambiguous keys are not auto-selected')
    observer, planner = [registry.settings_for_entry(r['id']) for r in (observers[0],planners[0])]
    photo_sha = hashlib.sha256(args.photo.read_bytes()).hexdigest()
    if photo_sha!='ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8':
        raise ValueError('Not the user-approved original photo')
    if not registry.resolve(observer).is_configured() or not registry.resolve(planner).is_configured():
        raise ValueError('Registered stage credentials unavailable')
    rates={OPENAI_MINI_SNAPSHOT:dict(input_per_million='0.75',output_per_million='4.50',context_tokens=400000,
        source='https://developers.openai.com/api/docs/models/gpt-5.4-mini',verified_at=utc_now())}
    both_gpt=args.planner=='openai'
    limit='0.50' if both_gpt else '0.15'
    if not both_gpt:
        rates[NANO]=nebius_rate(registry,planner)
    args.output.mkdir(parents=True, exist_ok=False)
    campaign = args.output/'campaign.json'
    scope = dict(schema_version='gpt-evaluation-1.0' if both_gpt else 'mixed-evaluation-1.0',
        approval=('2026-10-08 user: Nemotron도 GPT로 바꿔서 테스트 총10회 실시가능; existing photo OpenAI observer/planner/repair; actual local Isaac; no robot' if both_gpt else
            '2026-10-08 user: 좋아 확인해보자 총10회까지 시도 승인; existing photo OpenAI observer and Nebius NVIDIA planner/repair; actual local Isaac; no robot'),
        photo_sha256=photo_sha, prompt='Create a digital twin of my bedroom with a bed and desk.',
        max_requests=10, limit_usd=limit, campaign_path=str(campaign.resolve()),
        observer_entry_id=observers[0]['id'], planner_entry_id=planners[0]['id'],
        observer_settings=observer.to_dict(), planner_settings=planner.to_dict(),
        observer_model=OPENAI_MINI_SNAPSHOT, planner_model=OPENAI_MINI_SNAPSHOT if both_gpt else NANO,
        rates=rates,
        metadata_inference_calls=0, original_ledgers_unchanged=True, physical_authority=False)
    previous=None
    if args.continue_scope:
        if not both_gpt:raise ValueError('Continuation applies only to this GPT evaluation')
        from twinpulse_app.split_evaluation import load_evaluation_scope
        previous_scope=json.loads(args.continue_scope.read_text(encoding='utf-8'))
        bundle=load_evaluation_scope(args.continue_scope,Path(previous_scope['campaign_path']),request_cap=3)
        previous=bundle[-1]
        if (previous.lock_path.exists() or previous_scope['schema_version']!='gpt-evaluation-1.0'
                or previous_scope['photo_sha256']!=scope['photo_sha256'] or previous_scope['prompt']!=scope['prompt']
                or previous_scope['observer_settings']!=scope['observer_settings']
                or previous_scope['rates'].keys()!=scope['rates'].keys()):
            raise ValueError('Continuation scope mismatch or in-flight call')
        scope['rates']=previous_scope['rates']
        scope['continued_from']=dict(scope_path=str(args.continue_scope.resolve()),
            campaign_path=str(previous.path.resolve()),
            campaign_sha256=hashlib.sha256(previous.path.read_bytes()).hexdigest(),
            carried_requests=len(previous.state['requests']),unchanged_max_requests=10,
            reason='Retain schema-rejected request reservation; user-approved ten-call batch and original total USD1 ceiling unchanged')
    with (args.output/'scope.json').open('x',encoding='utf-8') as stream:
        json.dump(scope,stream,ensure_ascii=False,indent=2)
    ledger=SplitEvaluationLedger(campaign,approval=scope['approval'],rates=scope['rates'],limit_usd=limit,max_requests=10,openai_planner=both_gpt)
    if previous is not None:
        from copy import deepcopy
        ledger.state['requests']=deepcopy(previous.state['requests'])
        ledger.state['continued_from']=scope['continued_from']
        ledger._write()
        with previous.path.with_suffix('.continued-to').open('x',encoding='utf-8') as stream:
            json.dump(dict(scope_path=str((args.output/'scope.json').resolve()),
                campaign_sha256=scope['continued_from']['campaign_sha256'],carried_requests=len(previous.state['requests'])),stream)
    print(json.dumps(dict(status='SCOPE_PREPARED_NOT_INFERENCE',max_requests=10,limit_usd=limit,
        carried_requests=len(ledger.state['requests']),
        observer=OPENAI_MINI_SNAPSHOT,planner=scope['planner_model'],metadata_inference_calls=0)),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--planner',choices=('nebius','openai'),default='nebius')
    parser.add_argument('--continue-scope',type=Path,help='Carry all requests into this batch continuation; never resets count or old files')
    main(parser.parse_args())
