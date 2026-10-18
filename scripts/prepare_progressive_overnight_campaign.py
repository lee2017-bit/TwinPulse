# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prepare an explicitly approved Flash/Super functional acceptance cohort.

Metadata GETs only. No inference/Isaac/robot dispatch. Preserve the prior ledger
including its UNKNOWN carry-in; the new USD10 is incremental, not a reset.
Run only after product/Web/build are frozen and local acceptance has passed.
"""
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.compare_model_roles_live import metadata_get
from scripts.prepare_benchmark_pilot import build,exclusive
from scripts.benchmark_protocol import file_sha
from scripts.benchmark_campaign import initialize
from twinpulse_app import JsonProviderSettingsStore,WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_provider.model_contracts import catalog_from_inventory

OBSERVER='deepseek-ai/DeepSeek-V4.1-Flash'
PLANNER='nvidia/nemotron-3-super-120b-a12b'
DEADLINE='2026-10-11T22:33:20+00:00'
HISTORICAL=ROOT/'outputs/physical-ai-p2-20261011-v431/approved-scope'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--audit-only',action='store_true',help='Reaudit only historical raw financial exposure; no network or source freeze')
    parser.add_argument('--functional-only',action='store_true',help='Four morning ordinary draft input flows, not a model comparison/full navigation benchmark')
    parser.add_argument('--prior-functional-scope',type=Path,action='append',default=[],help='Explicit closed original scopes whose new exposure remains included in USD10')
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'outputs/progressive-twin-overnight-20261012'):
        raise ValueError('NAMED_OVERNIGHT_OUTPUT_ONLY')
    now=datetime.now(timezone.utc)
    if now>=datetime.fromisoformat(DEADLINE):raise ValueError('APPROVED_PERIOD_ENDED')
    output.mkdir(parents=True,exist_ok=False)
    old=json.loads((HISTORICAL/'campaign/manifest-campaign.json').read_text(encoding='utf-8'))
    # Financial-only raw audit. Updated product code is deliberately NOT checked
    # against a historical source freeze and no old runtime result is promoted.
    from scripts.benchmark_protocol import prepare
    from hashlib import sha256
    old_grant=json.loads((HISTORICAL/'cohort/authorization.json').read_text(encoding='utf-8'))
    if old_grant['manifest_sha256']!=file_sha(HISTORICAL/'cohort/manifest.json'):
        raise ValueError('HISTORICAL_AUTHORIZATION_MANIFEST_CHANGED')
    if old['authorization']!=old_grant:
        raise ValueError('HISTORICAL_AUTHORIZATION_CHANGED')
    audit=[]
    carry=Decimal(old_grant['providers']['nebius']['existing_exposure_usd'])
    for row in old['runs']:
        if not row['settled']:raise ValueError('HISTORICAL_UNSETTLED_RUN_REQUIRES_REVIEW')
        runtime=HISTORICAL/'campaign'/row['job_id']/'run-1/runtime'
        ledgers=list((runtime/'ordinary-generation').glob('*.ledger.json'))
        if len(ledgers)!=1 or list((runtime/'ordinary-generation').glob('*.dispatch-lock')):
            raise ValueError('HISTORICAL_LEDGER_OR_LOCK_UNRESOLVED')
        ledger=json.loads(ledgers[0].read_text(encoding='utf-8'))
        cost=held=Decimal(0);identities=set()
        for request in ledger['requests']:
            identity=request['attempt_id']
            if identity in identities:raise ValueError('HISTORICAL_DUPLICATE_REQUEST')
            identities.add(identity)
            raw=json.loads((runtime/'provider-evidence'/(identity+'.json')).read_text(encoding='utf-8'))
            dispatch=json.loads((runtime/'provider-evidence/dispatches'/(identity+'.json')).read_text(encoding='utf-8'))
            if (request['status'] not in ('received','rejected') or raw['status']!=request['status']
                or not request.get('finished_at') or raw.get('usage')!=request.get('usage')
                or raw['response_truncated'] or dispatch['request_truncated']
                or sha256(raw['response_redacted'].encode()).hexdigest()!=raw['stored_response_sha256']
                or sha256(dispatch['request_redacted'].encode()).hexdigest()!=dispatch['stored_request_sha256']
                or any(raw[k]!=dispatch[k] for k in ('request_sha256','schema_sha256','execution_id'))):
                raise ValueError('HISTORICAL_FINANCIAL_RAW_IDENTITY_CHANGED')
            amount=Decimal(request['charged_or_reserved_usd'])
            if not amount.is_finite() or amount<0:raise ValueError('HISTORICAL_AMOUNT_INVALID')
            if request.get('usage'):cost+=amount
            else:held+=amount
        if cost!=Decimal(row['summary']['cost_by_provider']['nebius']) or held!=Decimal(row['summary']['held_by_provider']['nebius']):
            raise ValueError('HISTORICAL_COST_EVIDENCE_CHANGED')
        audit.append(dict(job_id=row['job_id'],status=row['status'],
            cost_by_provider=dict(nebius=str(cost)),held_by_provider=dict(nebius=str(held)),
            requests=len(identities),raw_finance_only=True))
        carry+=cost+held
    if carry!=Decimal('7.15488417'):raise ValueError('HISTORICAL_CARRY_IN_CHANGED')
    exclusive(output/'historical-exposure-audit.json',dict(historical_nebius_protected_exposure_usd=str(carry),
        historical_manifest_sha256=file_sha(HISTORICAL/'cohort/manifest.json'),runs=audit,
        historical_unknown_retained=True,historical_runtime_acceptance_reaudited=False,
        new_additional_limit_usd='10.00',invoice_verified=False))
    if args.audit_only:
        print(json.dumps(dict(status='HISTORICAL_RAW_FINANCE_AUDIT_PASS',protected_carry_in_usd=str(carry),
            old_unknown_preserved=True,network_requests=0,new_provider_calls=0,invoice_verified=False)))
        return

    settings=JsonProviderSettingsStore()
    registry=KeyRegistry(settings,WindowsCredentialStore())
    entries=[r for r in registry.state()['entries'] if r['provider_profile'] in ('nebius_token_factory','nebius_site_v2')]
    entries=[r for r in entries if r.get('active')] or entries
    if len(entries)!=1:raise ValueError('ONE_EXISTING_NEBIUS_CREDENTIAL_REQUIRED')
    credential=registry.resolve(registry.settings_for_entry(entries[0]['id']))
    metadata,metadata_sha=metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info',credential)
    available,available_sha=metadata_get('https://api.tokenfactory.nebius.com/v1/models',credential)
    ids={r['id'] for r in available['data']}
    models=[]
    for model in (OBSERVER,PLANNER):
        rows=[r for group in metadata for r in group.get('flavors',[]) if r.get('model_id')==model]
        if len(rows)!=1 or model not in ids:raise ValueError('APPROVED_MODEL_UNAVAILABLE')
        row=rows[0]
        models.append(dict(provider='nebius',model_id=model,visible=True,use_cases=row['use_cases'],
            context_tokens=row['max_model_len'],input_per_million=str(row['input_price_per_million_tokens']),
            output_per_million=str(row['output_price_per_million_tokens'])))
    inventory=dict(created_at=now.isoformat(),catalog_sha256=metadata_sha,
        account_models_sha256=available_sha,models=models)
    exclusive(output/'model-metadata.json',inventory)
    catalog=catalog_from_inventory(inventory,valid_until=DEADLINE)
    exclusive(output/'stage-model-catalog.json',catalog)

    if args.functional_only:
        from scripts.prepare_progressive_functional_acceptance import build_functional
        print(json.dumps(build_functional(output,ROOT,catalog,carry,settings,registry,entries[0]['id'],args.prior_functional_scope)))
        return

    old_manifest=json.loads((HISTORICAL/'cohort/manifest.json').read_text(encoding='utf-8'))
    rows=[dict(case_id='text-workspace',room_group='synthetic-workspace',photo=None,
        prompt='Create an approximate 6 by 8 metre workspace with a desk against the back wall, a chair and a storage cabinet. Keep the central passage open. The dimensions are user estimates, not measurements.',
        goal='Go to desk',source=dict(reference='User-authorized synthetic acceptance text',license='TwinPulse authored test input',
            external_transmission_allowed=True,public_release_allowed=True),
        reference=dict(required_kinds=['desk','chair','storage']))]
    for case in old_manifest['cases']:
        rows.append(dict(case_id=case['case_id'],room_group=case['room_group'],photo=case['photo']['path'],
            prompt=case['prompt'],goal=case['goal']['text'],source=case['source'],reference=dict(required_kinds=[])))
    spec=dict(schema_version='pilot-dataset-spec-1.0',dataset_id='progressive-functional-20261012',
        seed=20261012,repeats=1,cases=rows)
    spec_path=output/'functional-input-spec.json';exclusive(spec_path,spec)
    preparation=build(spec,spec_path,output/'stage-model-catalog.json',output/'cohort',
        version='progressive-20261012',observer_cap=40000,planner_cap=40000,
        pairs=(('flash-super',OBSERVER,PLANNER),),request_cap=12)
    exclusive(output/'preparation-result.json',preparation)
    grant=dict(schema_version='benchmark-authorization-1.0',authorization_id='user-progressive-overnight-20261012',
        manifest_sha256=preparation['manifest_sha256'],approved_at='2026-10-11T14:33:20+00:00',expires_at=DEADLINE,
        human_approval='The human explicitly approved up to eight hours, the existing Flash/Super model combination, existing photos and derived renders, and an additional total USD10 of external API exposure including UNKNOWN and duplicate requests. No physical robot or paid Cloud.',
        providers=dict(nebius=dict(limit_usd=str(carry+Decimal('10')),existing_exposure_usd=str(carry),
            original_input=True,derived_render=True)),request_cap=12,trial_usd='1.00',admission_reserve_s=1800)
    exclusive(output/'cohort/authorization.json',grant)
    initialize(prepare(output/'cohort/manifest.json'),grant)
    print(json.dumps(dict(status='APPROVED_COHORT_PREPARED_NO_INFERENCE',planned=preparation['planned'],
        new_total_limit_usd='10.00',historical_exposure_usd=str(carry),metadata_gets=2,inference=0,
        additional_functional_cases='image-only and natural-language edits require separate new ledgers within the same additional limit')))


if __name__=='__main__':main()
