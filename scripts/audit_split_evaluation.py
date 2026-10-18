# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only raw/result audit. No model calls, candidate changes or robot I/O."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT
from twinpulse_provider.errors import InvalidProviderResponseError
from twinpulse_provider import GenerationRequest, ImageInput
from twinpulse_provider.photo_layout import compile_layout
from twinpulse_app.settings import JsonProviderSettingsStore

def audit(scope_path,trial_paths):
    scope_path=scope_path.resolve()
    scope=json.loads(scope_path.read_text(encoding='utf-8'))
    campaign_path=Path(scope['campaign_path'])
    campaign=json.loads(campaign_path.read_text(encoding='utf-8'))
    trials=[];seen=set();raw_checks=[]
    for path in trial_paths:
        path=path.resolve()
        result=json.loads((path/'result.json').read_text(encoding='utf-8'))
        browser=result.get('browser',{})
        diagnosis=(browser.get('workflow',{}).get('error') or {}).get('diagnostics',{})
        observations=[];plans=[];valid_observation=None
        ordering={r['attempt_id']:n for n,r in enumerate(campaign['requests'])}
        for raw_path in sorted((path/'runtime'/'provider-evidence').glob('*.json'),key=lambda p:ordering.get(p.stem,-1)):
            item=json.loads(raw_path.read_text(encoding='utf-8'));identity=raw_path.stem
            raw_checks.append(dict(attempt_id=identity,duplicate=identity in seen,
                source=raw_path.relative_to(ROOT).as_posix(),response_sha256=item.get('response_sha256'),
                http_status=item.get('http_status'),model_id=item.get('model_id'),
                elapsed_s=item.get('elapsed_s'),usage=item.get('usage'),input_images_saved=item.get('input_images_saved')))
            seen.add(identity)
            raw=json.loads(item.get('response_redacted','{}'))
            content=(raw.get('choices') or [{}])[0].get('message',{}).get('content')
            try:candidate=json.loads(content)
            except (ValueError,TypeError):continue
            stage = next((r.get('stage_schema') for r in campaign['requests'] if r['attempt_id']==identity), None)
            if (stage == 'twinpulse_image_observation' or
                    stage is None and item.get('model_id')==OPENAI_MINI_SNAPSHOT):
                row=dict(attempt_id=identity,valid=False)
                try:
                    value=ObservationArtifact.from_mapping(candidate)
                    valid_observation=value
                    row.update(valid=True,entities=len(value.entities),relations=len(value.relations),
                        unmeasured_dimensions=sum(d['value_m'] is None for d in value.dimensions))
                except InvalidProviderResponseError as error:
                    row.update(error_code=getattr(error,'code','provider_response_invalid'),
                        detail=str(error),contract_report=getattr(error,'contract_report',None))
                observations.append(row)
            else:
                objects=candidate.get('objects',[]) if isinstance(candidate,dict) else []
                plan=dict(attempt_id=identity,room=candidate.get('room'),
                    objects=len(objects),kinds=[i.get('kind') for i in objects if isinstance(i,dict)],
                    candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
                photos=list(path.glob('*.jpg'))
                if valid_observation is not None and len(photos)==1 and candidate.get('layout_version'):
                    content=photos[0].read_bytes()
                    if hashlib.sha256(content).hexdigest()!=scope['photo_sha256']:
                        raise ValueError('Original photo audit binding changed')
                    request=GenerationRequest('read-only-audit',scope['prompt'],(ImageInput('approved.jpg','image/jpeg',content),))
                    try:
                        _,trace=compile_layout(candidate,valid_observation,request,None)
                        plan.update(pure_compile_status='PASS',pure_compile_scope='Compiler only, not full photo quality or actual Isaac',
                            compiled_placements=trace.get('placements'))
                    except (ValueError,TypeError,KeyError,InvalidProviderResponseError) as error:
                        plan.update(pure_compile_status='FAIL',pure_compile_error=str(error),
                            source_contract=getattr(error,'contract_report',None),
                            packing_report=getattr(error,'packing_report',None))
                plans.append(plan)
        trials.append(dict(path=path.relative_to(ROOT).as_posix(),status=result['status'],
            error=browser.get('error') or result.get('error'),checks=browser.get('checks',[]),
            execution_id=browser.get('workflow',{}).get('execution_id'),
            observations=observations,planner_candidates=plans,
            diagnosis=diagnosis,robot_connections=result.get('robot_connections'),
            physical_authority=result.get('physical_authority'),
            source_unchanged=result.get('inference_source_unchanged'),
            host_capture_status=result.get('host',{}).get('capture',{}).get('status'),
            browser_closed=browser.get('browser_closed'),supervisor_state=result.get('supervisor',{}).get('status'),
            backend_owned=result.get('supervisor',{}).get('backend',{}).get('owned'),
            engine_owned=result.get('supervisor',{}).get('engine',{}).get('owned')))
    requests=campaign['requests'];ids={r['attempt_id'] for r in requests}
    cost=sum((Decimal(r['charged_or_reserved_usd']) for r in requests),Decimal(0))
    checks=dict(all_ledger_attempts_have_raw=ids==seen,no_duplicate_raw=not any(r['duplicate'] for r in raw_checks),
        within_call_cap=len(requests)<=scope['max_requests'],within_cost_cap=cost<=Decimal(scope['limit_usd']),
        no_pending=not any(r['status']=='outcome_unknown' for r in requests),
        dispatch_lock_absent=not campaign_path.with_suffix('.dispatch-lock').exists(),
        input_images_not_logged=all(r['input_images_saved'] is False for r in raw_checks),
        selected_provider_settings_unchanged=JsonProviderSettingsStore().load().to_dict()==scope['observer_settings'],
        no_robot_commands=all(t['robot_connections']==0 and t['physical_authority'] is False for t in trials),
        source_hashes_unchanged=all(t['source_unchanged'] for t in trials),
        owned_processes_closed=all(t['browser_closed'] and t['supervisor_state']=='stopped'
            and t['backend_owned'] is False and t['engine_owned'] is False for t in trials))
    lineage=scope.get('continued_from')
    if lineage:
        original_path=Path(lineage['campaign_path'])
        original=json.loads(original_path.read_text(encoding='utf-8'))
        checks['continuation_preserves_all_prior_requests']=(
            hashlib.sha256(original_path.read_bytes()).hexdigest()==lineage['campaign_sha256']
            and original['requests']==requests[:lineage['carried_requests']]
            and original['max_requests']==scope['max_requests']==lineage['unchanged_max_requests'])
        checks['parent_ledger_retired']=original_path.with_suffix('.continued-to').exists()
    return dict(status='PASS' if all(checks.values()) else 'FAIL',scope='Accounting/raw/cleanup audit, not scene quality',
        mixed_product_journey_pass=any(t['status']=='PASS' for t in trials),
        model_calls=len(requests),max_model_calls=scope['max_requests'],estimated_cost_usd=str(cost),
        received_usage_cost_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in requests if r.get('usage')),Decimal(0))),
        no_usage_reservations_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in requests if not r.get('usage')),Decimal(0))),
        unmeasured_geometry=True,full_physical_demo_pass=False,checks=checks,trials=trials,raw_attempts=raw_checks)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('trials',type=Path,nargs='+');args=parser.parse_args()
    result=audit(args.scope,args.trials)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('status','mixed_product_journey_pass','model_calls','estimated_cost_usd','checks')},ensure_ascii=True))
    raise SystemExit(0 if result['status']=='PASS' else 1)
