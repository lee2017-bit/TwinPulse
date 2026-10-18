# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""User-approved isolated role comparison; no robot or production settings writes."""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_provider.nebius_pipeline import _RejectRedirects
from twinpulse_provider.reliability import utc_now


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def credentials():
    settings = JsonProviderSettingsStore()
    registry = KeyRegistry(settings, WindowsCredentialStore())
    entries = registry.state()['entries']
    selected = {}
    for label, profiles in [('nebius', {'nebius_token_factory', 'nebius_site_v2'}),
                            ('openai', {'openai'})]:
        matches = [row for row in entries if row['provider_profile'] in profiles]
        active = [row for row in matches if row.get('active')]
        matches = active or matches
        if len(matches) != 1:
            raise ValueError(f'One existing {label} credential required, got {len(matches)}')
        selected[label] = registry.resolve(registry.settings_for_entry(matches[0]['id']))
    paths = [p for p in (settings.path, registry.path, settings.path.with_name('provider_stage_routing.json')) if p.is_file()]
    return selected, {str(p): sha(p) for p in paths}


def metadata_get(url, credential):
    key = credential.load()
    if not key:
        raise ValueError('Existing credential unavailable')
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
    with urllib.request.build_opener(_RejectRedirects()).open(request, timeout=30) as response:
        if response.geturl() != url:
            raise ValueError('Metadata redirect refused')
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Metadata exceeds bound')
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def inventory(output):
    stores, originals = credentials()
    catalog, catalog_sha = metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info', stores['nebius'])
    visible, visible_sha = metadata_get('https://api.tokenfactory.nebius.com/v1/models?verbose=true', stores['nebius'])
    opened, opened_sha = metadata_get('https://api.openai.com/v1/models', stores['openai'])
    ids = {r['id'] for r in visible['data']}
    rows = []
    for group in catalog:
        for row in group.get('flavors', []):
            rows.append(dict(provider='nebius', model_id=row.get('model_id'),
                visible=row.get('model_id') in ids, use_cases=row.get('use_cases', []),
                context_tokens=row.get('max_model_len'),
                input_per_million=str(row.get('input_price_per_million_tokens')),
                output_per_million=str(row.get('output_price_per_million_tokens')),
                supports=row.get('supported_parameters', [])))
    result = dict(schema_version='role-comparison-1.0', created_at=utc_now(), models=rows,
        account_models=visible['data'], openai_luna_visible=any(r['id']=='gpt-6-luna' for r in opened['data']),
        catalog_sha256=catalog_sha, account_sha256=visible_sha, openai_models_sha256=opened_sha,
        originals_at_start=originals, metadata_calls=3, inference_calls=0,
        budget_usd={'nebius':'10.00','openai':'0.50'}, repetitions=2,
        authorization='2026-10-10 user: all available Nebius image/design models twice under identical conditions; stop after five consecutive distinct models with same failure; OpenAI GPT6 Luna only; existing room source and derived render comparison; no robots.',
        robot_calls=0, whole_demo_pass=False)
    save(output/'inventory.json', result)
    print(json.dumps(dict(models=rows, openai_luna_visible=result['openai_luna_visible'], inference_calls=0), ensure_ascii=True), flush=True)


from twinpulse_provider import (GenerationRequest, ImageInput, CancellationToken, ChatCompletion,
    ProviderConfig, ProviderCapabilities, GenerationService)
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider, ObservationArtifact, _validation_code, _json_content
from twinpulse_provider.reliability import CampaignLedger, InferenceEvidence, AuditedChatTransport, safe_text
from twinpulse_provider.stage_transport import explicit_json_contract, openai_observer_body, has_image
from twinpulse_provider.semantic_scene import _shape_issues
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_core.execution_diagnostics import ExecutionStore

PHOTO = ROOT/'outputs/ordinary-full-retest-20261010/run-1/1-사진-1.jpg'
OBSERVATION = ROOT/'outputs/ordinary-full-retest-20261010/run-1/runtime/provider-evidence/generation-store/observation/3e6e8b33a42b0ac25d18794cccf7fa5be28b82ca7461457419355ceb6e679cb4.json'
PROMPT = 'Create a digital twin of my bedroom with a bed and desk.'
LUNA = dict(provider='openai', model_id='gpt-6-luna', visible=True, use_cases=['text','image'],
    context_tokens=1050000, input_per_million='0.10', output_per_million='0.50')


class ComparisonLedger(CampaignLedger):
    def reserve(self, body):
        accounting = deepcopy(body)
        if 'max_completion_tokens' in accounting:
            accounting['max_tokens'] = accounting.pop('max_completion_tokens')
        return super().reserve(accounting)


def wire_for(body, provider, *, current_adapter=False):
    result = explicit_json_contract(body)
    if provider == 'openai':
        result.pop('chat_template_kwargs', None)
        # Documented GPT6 Luna Chat Completions structured/function output mode.
        result = openai_observer_body(result, reasoning_effort='none')
    elif not has_image(result.get('messages')) and (not current_adapter or result['model'] in
            ('nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B','nvidia/Nemotron-3_5-Lightning')):
        # Trial-only adapter: no expansion of the production Nano allow-list.
        result['chat_template_kwargs']={'enable_thinking':False}
    return result


def plan_cases(scope):
    models = [r for r in scope['models'] if r['visible'] and 'text' in r['use_cases']]
    # Priority is frozen before inference, not reordered to hide failed samples.
    priority = ['nvidia/Nemotron-3_5-Lightning', 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
                'nvidia/Nemotron-3-Ultra-550b-a55b', 'nvidia/nemotron-3-super-120b-a12b']
    models.sort(key=lambda r: (priority.index(r['model_id']) if r['model_id'] in priority else 9,
                               r['model_id']))
    if scope['openai_luna_visible']:
        models.insert(0, LUNA)
    return [(role, row, repetition) for repetition in (1, 2) for role in ('observer','planner')
            for row in models if role=='planner' or 'image' in row['use_cases']]


def failure_fingerprint(result):
    if result['status']=='PASS':
        return None
    report = result.get('contract_report') or {}
    codes = sorted({r.get('code','unknown') for r in report.get('issues',[])})
    return (result.get('role'), result.get('http_status'), tuple(codes), result.get('failure_code'), result.get('provider_error_code'))


class FailureStreak:
    def __init__(self):
        self.previous = None
        self.models = []

    def observe(self, result):
        if result.get('actual_calls') == 0:
            self.previous, self.models = None, []
            return False  # Host preparation failure is not a failed model reply.
        fingerprint = failure_fingerprint(result)
        if fingerprint is None:
            self.previous, self.models = None, []
        elif fingerprint != self.previous:
            self.previous, self.models = fingerprint, [result['model_id']]
        elif result['model_id'] not in self.models:
            self.models.append(result['model_id'])
        return len(self.models)>=5


def role_attempt_snapshot(calls, evidence_root, ledger):
    """Read settlement without assuming a timeout has joined the HTTP thread.

    Missing/partial raw is not an empty reply or a zero-cost call. Preserve the
    reserved amount and stop; the worker remains the only raw/settlement writer.
    No polling, retry, fabricated raw or late PASS promotion.
    """
    attempts, evidence_errors = [], []
    for identity in tuple(calls):
        entry = next((dict(r) for r in ledger.state['requests'] if r['attempt_id'] == identity), None)
        if entry is None:
            raise ValueError('ROLE_LEDGER_ATTEMPT_MISSING')
        try:
            raw = json.loads((evidence_root / f'{identity}.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            raw = {}; evidence_errors.append(dict(attempt_id=identity, code='EVIDENCE_PENDING'))
        except (OSError, ValueError):
            pending = not entry.get('finished_at') and identity in getattr(ledger, 'timeout_ids', set())
            raw = {}; evidence_errors.append(dict(attempt_id=identity,
                code='EVIDENCE_PENDING' if pending else 'EVIDENCE_UNREADABLE'))
        facts = {k: raw.get(k) for k in ('attempt_id','model_id','http_status','finish_reason','usage','elapsed_s','status')}
        facts.update(attempt_id=identity, model_id=entry['model_id'],
                     ledger_status=entry['status'], settlement_finished=bool(entry.get('finished_at')),
                     evidence_status='PRESENT' if raw else 'UNAVAILABLE',
                     estimated_or_reserved_usd=entry['charged_or_reserved_usd'])
        if not raw:
            facts['status'] = entry['status']
        if not facts['finish_reason'] and raw.get('response_redacted'):
            try:
                facts['finish_reason'] = (json.loads(raw['response_redacted']).get('choices') or [{}])[0].get('finish_reason')
            except (ValueError, AttributeError):
                pass
        if facts.get('http_status') and facts['http_status'] != 200:
            try:
                facts['provider_error_code'] = json.loads(raw.get('response_redacted','{}')).get('error',{}).get('code')
            except (ValueError, AttributeError):
                pass
        attempts.append(facts)
    return attempts, evidence_errors


def role_terminal_stop(row, attempts, evidence_errors, ledger):
    if row.get('failure_code') == 'PROVIDER_OUTPUT_TRUNCATED' or any(a.get('finish_reason') == 'length' for a in attempts):
        return 'OUTPUT_LIMIT'
    if getattr(ledger, 'allows_timeout_continuation', lambda *_: False)(row, attempts, evidence_errors):
        return None  # scored FAIL remains immutable; only named timeout holds continue
    blocked = getattr(ledger, 'blocking_dispatch_lock', lambda: ledger.lock_path.exists())()
    if any(a.get('ledger_status') == 'outcome_unknown' or not a.get('settlement_finished') or not a.get('usage') or
           a.get('status') == 'outcome_unknown' for a in attempts) or blocked:
        return 'REMOTE_UNKNOWN'
    if evidence_errors:
        return 'EVIDENCE_INCOMPLETE'
    return None


async def run_case(output, role, model, repetition, stores, ledger, observation, scope, *, host_fix=False,
                   photo=None,prompt=None,output_cap=20000,current_adapter=False,expires_at=None,collection=None):
    # Explicit reusable inputs avoid the private legacy fixture entirely.
    photo=PHOTO if photo is None else Path(photo)
    prompt=PROMPT if prompt is None else prompt
    if type(output_cap) is not int or not 1<=output_cap<=40000:raise ValueError('ROLE_OUTPUT_CAP_INVALID')
    identity = f'{role}-{model["provider"]}-{hashlib.sha256(model["model_id"].encode()).hexdigest()[:12]}-r{repetition}'
    target = output/'cases'/identity
    if target.exists():
        prior=json.loads((target/'result.json').read_text(encoding='utf-8'))
        if not host_fix or prior['actual_calls']!=0 or prior['status']!='FAIL':
            raise ValueError('Only a preserved zero-dispatch host failure may use the host-fix suffix')
        target=target.with_name(identity+'-hostfix')
        if target.exists():raise ValueError('Host-fix case already exists')
    trace_store = ExecutionStore(target/'diagnostics', 'model-role-comparison')
    trace = trace_store.begin('model_role_comparison', component='provider')
    token = CancellationToken(); token.diagnostics=trace
    token.generation_role = 'initial'
    evidence = InferenceEvidence(target/'evidence')
    opener=None
    if expires_at is not None:
        from datetime import datetime,timezone
        expiry=datetime.fromisoformat(expires_at)
        allowed='https://api.openai.com/v1/chat/completions' if model['provider']=='openai' else 'https://api.tokenfactory.nebius.com/v1/chat/completions'
        original_open=urllib.request.build_opener(_RejectRedirects()).open
        def guarded_open(request,**kwargs):
            if request.full_url!=allowed or datetime.now(timezone.utc)>=expiry:
                raise ValueError('ROLE_AUTHORIZATION_EXPIRED_OR_DESTINATION_CHANGED')
            return original_open(request,**kwargs)
        opener=guarded_open
    transport = AuditedChatTransport(stores[model['provider']].load, evidence,
                                    ledger if role=='observer' else None,opener=opener,
                                    **({'collection':collection} if collection is not None else {}))
    config = ProviderConfig('https://api.openai.com/v1/' if model['provider']=='openai'
        else 'https://api.tokenfactory.nebius.com/v1/', 'chat/completions', model['model_id'],
        'EXISTING_REGISTERED_CREDENTIAL', ProviderCapabilities(True, True, 1), timeout_s=300)
    request = GenerationRequest(identity, prompt, (ImageInput(photo.name,'image/jpeg', photo.read_bytes()),), diagnostics=trace)
    row = dict(case_id=identity, role=role, model_id=model['model_id'], provider=model['provider'],
        repetition=repetition, execution_id=trace.execution_id, timeout_s=300, max_output_tokens=output_cap,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), photo_sha256=scope['photo_sha256'],
        shared_observation_sha256=scope['observation_sha256'] if role=='planner' else None,
        status='STARTED', isaac='NOT_RUN', photo_fidelity='NOT_MEASURED', physical_authority=False)
    save(target/'start.json', row)
    print(json.dumps({k:row[k] for k in ('case_id','role','model_id','status') }),flush=True)
    started=time.monotonic()
    pipeline=None
    try:
        if role=='observer':
            provider = NebiusChatCompletionsPipelineProvider(transport, observer_model_id=model['model_id'],
                planner_model_id='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',site_plan_version='2.2',
                compact_photo_layout=True, stage_output_token_caps={'observer':output_cap,'planner':output_cap})
            body = wire_for(provider.build_observer_body(request),model['provider'],current_adapter=current_adapter)
            body['max_completion_tokens' if model['provider']=='openai' else 'max_tokens']=output_cap
            completion = await transport.complete(body,token,config)
            value=_json_content(completion,'observer')
            schema=body['response_format']['json_schema']['schema']
            problems=_shape_issues(value,schema)
            if problems:
                row['contract_report']={'issues':problems}
                raise ValueError('OBSERVER_SCHEMA_INVALID')
            observed=ObservationArtifact.from_mapping(value)
            save(target/'observation.json',observed.to_dict())
            row.update(status='PASS', acceptance='OBSERVATION_CONTRACT_ONLY',
                entity_count=len(observed.entities), relation_count=len(observed.relations),
                categories=sorted({r.get('category',r['kind']) for r in observed.entities}),
                measured_dimensions=sum(r.get('value_m') is not None for r in observed.dimensions))
        else:
            class ApprovedRoleScope:
                cache_identity={'campaign':str(output),'role':'fixed-observation-planner'}
                def bind(self, req, policy, route_sha256):
                    if req.prompt!=prompt or sha(photo)!=scope['photo_sha256']:
                        raise ValueError('Role input changed')
                    return ledger
            class ReuseObserverAndLivePlanner:
                async def complete(self, body, inner_token, inner_config):
                    name=body['response_format']['json_schema']['name']
                    if name=='twinpulse_image_observation':
                        return ChatCompletion('historical-observation-reuse',body['model'],
                            json.dumps(observation.to_dict()),'stop',{})
                    if has_image(body.get('messages')):
                        raise ValueError('Image leaked to planner')
                    wire=wire_for(body,model['provider'],current_adapter=current_adapter)
                    return await transport.complete(wire,inner_token,replace(config,timeout_s=inner_config.timeout_s))
                def record_validation(self, stage, attempt_id, record):
                    if attempt_id:
                        transport.record_validation(stage,attempt_id,record)
            policy=replace(GenerationPolicy(), max_requests=12,max_repairs=3,
                total_timeout_s=1800,initial_timeout_s=900,repair_timeout_s=840,final_timeout_s=60)
            request=replace(request,inference_scope=ApprovedRoleScope())
            pipeline=BudgetedPipeline(ReuseObserverAndLivePlanner(),policy=policy,
                store_root=target/'generation-store',observer_model_id='historical-shared-observation',
                planner_model_id=model['model_id'],site_plan_version='2.2',
                planner_template_no_thinking=False,
                stage_output_token_caps={'observer':output_cap,'planner':output_cap})
            result=await GenerationService(pipeline,config,plan_version='2.2').generate(request)
            save(target/'plan.json',result.plan.to_dict())
            save(target/'provenance.json',result.provider_provenance)
            row.update(status='PASS',acceptance='APPROXIMATE_GEOMETRY_AND_OBSERVED_QUALITY',
                tool_calls=len(result.plan.calls),quality_review=result.provider_provenance.get('quality_review'))
    except Exception as error:
        from twinpulse_provider.errors import ProviderTimeoutError
        if (collection is not None and isinstance(error,ProviderTimeoutError)
                and getattr(error,'per_call_timeout_s',None) is not None):
            collection.record_enclosing_deadline(transport.calls,ledger,
                scored_timeout_s=error.per_call_timeout_s)
        code='PROVIDER_TIMEOUT' if isinstance(error,ProviderTimeoutError) else getattr(error,'code',None) or _validation_code(error)
        row.update(status='FAIL',error_type=type(error).__name__,failure_code=code,
                   error=safe_text(str(error),limit=600))
        if getattr(error,'contract_report',None):row['contract_report']=error.contract_report
    if pipeline:
        row['diagnostic']=pipeline.diagnostic_for(identity)
    row.update(elapsed_s=round(time.monotonic()-started,3),attempt_ids=list(transport.calls),actual_calls=len(transport.calls))
    attempts,evidence_errors=role_attempt_snapshot(transport.calls,target/'evidence',ledger)
    for facts in attempts:
        if facts.get('http_status') and facts['http_status']!=200:
            row['http_status']=facts['http_status']
            row['provider_error_code']=facts.get('provider_error_code')
    row['attempts']=attempts
    row['evidence_errors']=evidence_errors
    row['estimated_or_reserved_usd']=str(sum((Decimal(a['estimated_or_reserved_usd']) for a in attempts),Decimal(0)))
    row['terminal_stop']=role_terminal_stop(row,attempts,evidence_errors,ledger)
    if row['status']=='PASS' and row['terminal_stop']:
        row.update(status='FAIL',failure_code='ROLE_EVIDENCE_OR_SETTLEMENT_INCOMPLETE')
    transport.record_validation('role_result',transport.calls[-1],row) if transport.calls else None
    trace.finish('succeeded' if row['status']=='PASS' else 'failed',error_code=row.get('failure_code'))
    trace_store.flush()
    save(target/'result.json',row)
    print(json.dumps({k:row.get(k) for k in ('case_id','status','failure_code','elapsed_s','actual_calls','estimated_or_reserved_usd','terminal_stop') }),flush=True)
    return row


async def evaluate(output, *, resume_host_fix=False):
    scope=json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    stores,originals=credentials()
    if any(not Path(p).is_file() or sha(Path(p))!=digest for p,digest in scope['originals_at_start'].items()):
        raise ValueError('Original settings changed after inventory')
    source=json.loads(OBSERVATION.read_text(encoding='utf-8'))['payload']['observation']
    observation=ObservationArtifact.from_mapping(source)
    scope.update(photo_sha256=sha(PHOTO),observation_sha256=sha(OBSERVATION),
        prompt=PROMPT,output_limit=20000,per_call_timeout_s=300,
        planner_observation='EXACT_PRIOR_LIVE_GPT_OBSERVATION_NOT_NEW_OR_GROUND_TRUTH',
        per_planner_trial_max_requests=12,per_planner_trial_max_repairs=3,
        render_review='NOT_RUN_ROLE_COMPARISON_ONLY',default_settings_changed=False)
    cases=plan_cases(scope)
    scope['planned_cases']=[{'role':r,'model_id':m['model_id'],'repetition':n} for r,m,n in cases]
    if resume_host_fix:
        frozen=json.loads((output/'scope.json').read_text(encoding='utf-8'))
        if any(scope[k]!=frozen[k] for k in ('photo_sha256','observation_sha256','planned_cases','budget_usd','authorization')):
            raise ValueError('Comparison scope changed; no resume')
        scope=frozen
        save(output/'host-fix.json',dict(created_at=utc_now(),source_sha256=sha(Path(__file__)),
            reason='Do not feed Nano-only constructor flag to other planners; diagnostic token propagation and partial finish-reason audit.',
            new_scope=False,production_defaults_changed=False,additional_requests=0))
    else:save(output/'scope.json',scope)
    ledgers={}
    for provider in ('nebius','openai'):
        rates={m['model_id']:{k:m[k] for k in ('input_per_million','output_per_million','context_tokens')}
            for _,m,_ in cases if m['provider']==provider}
        for rate in rates.values():
            rate.update(source=('https://api.tokenfactory.nebius.com/private/v1/models_info' if provider=='nebius'
                else 'https://developers.openai.com/api/docs/models/gpt-6-luna'),verified_at=utc_now())
        path=output/(provider+'.ledger.json')
        if path.exists():rates=json.loads(path.read_text(encoding='utf-8'))['rates']
        ledgers[provider]=ComparisonLedger(path,approval=scope['authorization'],rates=rates,
            limit_usd=scope['budget_usd'][provider],max_requests=sum(1 if r=='observer' else 12 for r,m,n in cases if m['provider']==provider))
    streak=FailureStreak(); results=[]; stopped=None
    for role,model,repetition in cases:
        identity=f'{role}-{model["provider"]}-{hashlib.sha256(model["model_id"].encode()).hexdigest()[:12]}-r{repetition}'
        prior=output/'cases'/identity/'result.json'
        if resume_host_fix and prior.exists():
            original=json.loads(prior.read_text(encoding='utf-8'))
            if original['actual_calls']>0:
                row=original
            else:
                row=await run_case(output,role,model,repetition,stores,ledgers[model['provider']],observation,scope,host_fix=True)
        else:row=await run_case(output,role,model,repetition,stores,ledgers[model['provider']],observation,scope)
        results.append(row)
        if row['terminal_stop']:
            stopped=row['terminal_stop'];break
        if streak.observe(row):
            stopped='FIVE_DISTINCT_MODELS_SAME_FAILURE';break
    result=dict(created_at=utc_now(),status='STOPPED' if stopped else 'COMPLETED',stop_reason=stopped,
        results=results, planned_cases=len(cases),finished_cases=len(results),
        missing_cases=scope['planned_cases'][len(results):],
        originals_unchanged=all(Path(p).is_file() and sha(Path(p))==digest for p,digest in originals.items()),
        source_unchanged=sha(PHOTO)==scope['photo_sha256'] and sha(OBSERVATION)==scope['observation_sha256'],
        financial={p:dict(actual_calls=len(l.state['requests']),
            estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in l.state['requests']),Decimal(0))),
            limit_usd=l.state['limit_usd'],pending_lock=l.lock_path.exists()) for p,l in ledgers.items()},
        invoice_verified=False,isaac='NOT_RUN',robot_calls=0,whole_demo_pass=False)
    save(output/('summary-final.json' if resume_host_fix else 'summary.json'),result)
    print(json.dumps({k:result[k] for k in ('status','stop_reason','planned_cases','finished_cases','financial','originals_unchanged','source_unchanged')}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--resume-after-host-fix',action='store_true')
    args = parser.parse_args()
    if args.inventory:
        inventory(args.output.resolve())
    elif args.evaluate:
        asyncio.run(evaluate(args.output.resolve(),resume_host_fix=args.resume_after_host_fix))
