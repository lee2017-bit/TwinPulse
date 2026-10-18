# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One authorized live ordinary generation, default max10/USD1, benchmark24.

Copies metadata only to isolated settings. No fake response source, automatic
retry/new grant, real robot, secret export or original settings mutation.
"""
from dataclasses import replace
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_app','twinpulse_provider','twinpulse_core'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings
from twinpulse_provider.generation_policy import GenerationPolicy


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_trial_settings(settings, registry, routes, target, *, manifest_bound=False):
    """Copy non-secret identity metadata, never pair an old route with a new catalog.

    A frozen manifest supplies the COMPLETE trial route and catalog below. Its
    isolated routing file must start absent so save() can validate/rollback
    against None, rather than loading a global route pinned to another catalog.
    Legacy runs keep their prior-route behavior; global files stay unchanged.
    """
    # A selected immutable profile is part of the route, not optional global
    # state. Resolve before copying so a missing/tampered snapshot fails closed.
    profiles={} if manifest_bound else (routes.harness_bindings(routes.load()) or {})
    paths=(settings.path,registry.path) if manifest_bound else (settings.path,registry.path,routes.path)
    for path in paths:
        shutil.copyfile(path,target/path.name)
    if profiles:
        from twinpulse_app.harness_store import HarnessStore
        store=HarnessStore(target)
        for frozen in profiles.values():
            copied=store.save(frozen['profile'])
            if copied!={key:frozen[key] for key in ('id','revision','sha256')}:
                raise ValueError('TRIAL_HARNESS_COPY_MISMATCH')


class RunnerPhaseTrace:
    """Secret-free terminal DIAGNOSTIC, never a zero-cost settlement receipt.

    Missing ordinary ledgers still require the strict independent auditor.
    Mark dispatch intent before entering the child: an exception after this
    point must NEVER be described as proof of zero external inference.
    """
    def __init__(self,output,*,case_id=None,config_id=None):
        self.output=Path(output).resolve();self.events=[];self.dispatch_intent=False
        self.case_id=case_id;self.config_id=config_id
        self.mark('INPUT_PREFLIGHT')

    def mark(self,phase):
        if phase=='JOURNEY_DISPATCH_INTENT':self.dispatch_intent=True
        self.events.append(dict(phase=phase,at=datetime.now(timezone.utc).isoformat()))

    def finish(self,status,*,error_type=None):
        # Both paths belong to the explicitly named run. No broad directory
        # creation, overwrite, keys, prompts, error messages or auth headers.
        path=(self.output/'runner-terminal.json' if self.output.is_dir()
              else self.output.with_name(self.output.name+'.preflight.json'))
        if path.is_symlink() or path.parent.is_symlink():raise ValueError('LINKED_RUNNER_TRACE')
        value=dict(schema_version='ordinary-runner-terminal-diagnostic-1.0',status=status,
            case_id=self.case_id,config_id=self.config_id,events=self.events,
            terminal_phase=self.events[-1]['phase'],error_type=error_type,
            journey_dispatch_intent=self.dispatch_intent,
            inference_status='UNKNOWN_AUDIT_REQUIRED' if self.dispatch_intent else 'NOT_ENTERED_JOURNEY',
            financial_settlement_authority=False,physical_authority=False,
            source_sha256=sha(Path(__file__)))
        with path.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        return value


def audit_ordinary_run(output):
    """Read-only settled wire/raw/validation audit; never promotes a failed run."""
    from decimal import Decimal
    from twinpulse_provider.stage_transport import has_image
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    approval=read(output/'approval.json')
    summary=read(output/'summary.json')
    from scripts.benchmark_environment import audit_environment_evidence
    audit_environment_evidence(approval,summary)
    run=output/'run-1'
    paths=list((run/'runtime/ordinary-generation').glob('*.ledger.json'))
    if len(paths)!=1:raise ValueError('One fresh ordinary grant required')
    ledger=read(paths[0]);evidence=run/'runtime/provider-evidence';rows=[]
    cap=approval['route']['generation_policy']['max_requests']
    if ledger['max_requests']!=cap or Decimal(ledger['limit_usd'])!=Decimal(approval['cost_limit_usd']):
        raise ValueError('Reviewed financial scope changed')
    if list((run/'runtime/ordinary-generation').glob('*.dispatch-lock')):
        raise ValueError('Unsettled inference dispatch')
    for entry in ledger['requests']:
        identity=entry['attempt_id'];raw=read(evidence/(identity+'.json'))
        dispatch=read(evidence/'dispatches'/(identity+'.json'))
        validations=list((evidence/'validations').glob(identity+'-*.json'))
        if (entry['status'] not in ('received','rejected') or raw['status']!=entry['status']
                or not entry.get('finished_at') or raw.get('usage')!=entry.get('usage')
                or raw['response_truncated'] or dispatch['request_truncated']
                or hashlib.sha256(raw['response_redacted'].encode()).hexdigest()!=raw['stored_response_sha256']
                or hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest()!=dispatch['stored_request_sha256']
                or any(raw[k]!=dispatch[k] for k in ('request_sha256','schema_sha256','execution_id'))
                or (entry['status']=='received' and not validations)):
            raise ValueError('Raw/request/accounting identity mismatch')
        if entry['status']=='rejected' and not entry.get('usage'):
            # A recorded HTTP rejection is a known failed outcome, not a
            # successful model response. Unknown billing keeps its reservation.
            if (not isinstance(raw.get('http_status'),int) or not raw.get('response_redacted')
                    or Decimal(entry['charged_or_reserved_usd'])!=Decimal(entry['reserved_usd'])):
                raise ValueError('Rejected request billing reservation or evidence changed')
        for path in validations:
            check=read(path)
            if (check['record_truncated'] or check['attempt_id']!=identity
                    or check['execution_id']!=raw['execution_id']
                    or hashlib.sha256(check['record_redacted'].encode()).hexdigest()!=check['stored_record_sha256']):
                raise ValueError('Validation evidence changed')
        rows.append(dict(attempt_id=identity,execution_id=raw['execution_id'],model_id=raw['model_id'],
            role=raw['role'],finish_reason=raw.get('finish_reason'),elapsed_s=raw['elapsed_s'],
            status=entry['status'],http_status=raw.get('http_status'),usage=raw.get('usage'),
            estimated_usd=entry['charged_or_reserved_usd'] if entry.get('usage') else '0',
            held_without_usage_usd=entry['charged_or_reserved_usd'] if not entry.get('usage') else '0',
            image_sent=has_image(json.loads(dispatch['request_redacted'])),
            validation_files=len(validations),raw_ledger_match=True,dispatch_sha_matches=True))
    unchanged=all(Path(p).is_file() and sha(Path(p))==digest for p,digest in approval['originals_at_start'].items())
    photo=run/approval.get('photo_name','1-사진-1.jpg') if approval.get('photo_sha256') else None
    if (not unchanged or not summary['originals_unchanged']
            or photo is not None and sha(photo)!=approval['photo_sha256']
            or len(rows)>cap):raise ValueError('Original settings/history/input or call cap changed')
    if approval.get('benchmark_case_sha256'):
        from scripts.benchmark_protocol import checked_packet,text_sha
        packet=checked_packet(read(output/'benchmark-case.json'),actual=True)
        if sha(output/'benchmark-case.json')!=approval['benchmark_case_sha256']:
            raise ValueError('Benchmark input/goal changed')
        latest=read(run/'runtime/active_project.json')['latest_input']
        if (text_sha(latest['prompt'])!=packet['prompt_sha256']
                or [image['sha256'] for image in latest['images']]!=
                    ([packet['photo']['sha256']] if packet['photo'] else [])):
            raise ValueError('Actual submitted benchmark input differs from approved case')
        if summary['status']=='PASS' and packet['goal']['expected']!='arrival':
            from scripts.benchmark_diagnostic import validate_diagnostic
            validate_diagnostic(packet,summary.get('browser',{}).get('diagnostic_goal'))
        if summary['status']=='PASS' and packet['goal']['expected']=='arrival':
            from scripts.benchmark_arrival_evidence import validate_arrival
            validate_arrival(packet,summary.get('browser',{}))
            arrival=summary.get('browser',{}).get('semantic_arrival')
            if (not arrival or not arrival.get('telemetry_available')
                    or arrival.get('runtime_state')!='completed'
                    or type(arrival.get('distance_to_goal_m')) not in (int,float)
                    or not 0<=arrival['distance_to_goal_m']<=.04):
                raise ValueError('Benchmark PASS requires actual predeclared semantic-goal arrival')
    return dict(status='AUDIT_PASS_NOT_GENERATION_PASS',generation_status=summary['status'],
        call_cap=cap,actual_calls=len(rows),unused_calls=cap-len(rows),
        estimated_usd=str(sum((Decimal(r['estimated_usd']) for r in rows),Decimal(0))),
        held_without_usage_usd=str(sum((Decimal(r['held_without_usage_usd']) for r in rows),Decimal(0))),
        invoice_verified=False,unknown_requests=0,pending_locks=0,originals_unchanged=True,
        photo_uploads=sum(r['image_sent'] for r in rows),robot_connections=0,rows=rows)


def journey_command(output,photo,settings,*,generation_only=False,benchmark_case=None):
    """Existing ordinary App path; text has no upload/photo argument."""
    if generation_only:
        if photo is None or benchmark_case:raise ValueError('Generation-only benchmark is not a full journey')
        return [sys.executable,str(ROOT/'scripts/verify_live_generation_screen.py'),str(output/'run-1'),
                '--photo',str(photo),'--settings',str(settings)]
    return [sys.executable,str(ROOT/'scripts/verify_chat_sim_journey.py'),str(output/'run-1'),
        '--case','image' if photo else 'text',*(['--live-photo',str(photo)] if photo else []),
        *(['--benchmark-case',str(benchmark_case)] if benchmark_case else []),
        '--ordinary-live-settings',str(settings),'--diagnostics']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('photo',type=Path,nargs='?')
    parser.add_argument('--benchmark-manifest',type=Path,help='Frozen approved case manifest, not a new financial approval')
    parser.add_argument('--case-id',help='One predeclared case from the manifest')
    parser.add_argument('--config-id',help='One frozen configuration from the same manifest')
    parser.add_argument('--approval-text',required=True,help='Current explicit human approval; never reuse a past grant')
    parser.add_argument('--recommended-nebius',action='store_true',help='Reviewed DeepSeek observer + Lightning planner, including actual current-render review')
    parser.add_argument('--benchmark-profile',action='store_true',help='Current explicitly authorized benchmark: up to 24 calls, same 900s total with 180s render reserve; does not change product defaults')
    parser.add_argument('--observer-model',help='Frozen catalog model; unlisted models require a manifest')
    parser.add_argument('--planner-model',help='Frozen catalog model; unlisted models require a manifest')
    parser.add_argument('--request-cap',type=int,default=10,help='Reduced current grant cap, never above ten')
    parser.add_argument('--cost-limit',default='1.00',help='Reduced current grant USD cap, never above USD1')
    parser.add_argument('--generation-only',action='store_true',
                        help='Serve the real UI/backend without an engine; never launch Isaac or send Build/Run/Stop')
    args=parser.parse_args()
    trace=RunnerPhaseTrace(args.output,case_id=args.case_id,config_id=args.config_id)
    try:
        run_reviewed(args,trace)
    except Exception as error:
        trace.finish('FAIL',error_type=type(error).__name__)
        raise
    else:
        trace.finish('COMPLETED_REQUIRES_ORDINARY_AUDIT')


def run_reviewed(args,trace):
    output=args.output.resolve()
    packet=prepared=environment_before=None
    if args.benchmark_manifest:
        from scripts.benchmark_protocol import prepare,checked_packet,source_freeze,effective_settings_sha
        if not args.benchmark_profile or not args.case_id or not args.config_id or args.generation_only:
            raise ValueError('Manifest case requires benchmark profile, case/config IDs and actual full journey')
        prepared=prepare(args.benchmark_manifest)
        if any(prepared['freeze'].get(p)!=digest for p,digest in source_freeze(ROOT).items()):
            raise ValueError('Full product/harness source freeze differs')
        from scripts.benchmark_environment import verify_environment
        environment_before=verify_environment(prepared,ROOT)
        if prepared.get('evaluation_readiness'):
            labels=next((r for r in prepared['evaluation_readiness']['cases'] if r['case_id']==args.case_id),None)
            if labels and labels['split']=='holdout' and labels['status']!='LABELS_REVIEWED_ATTESTED':
                raise ValueError('HOLDOUT_LABELS_NOT_REVIEWED_BEFORE_OUTPUTS')
            if labels and labels['split']=='holdout':
                from scripts.benchmark_campaign import utc
                from datetime import datetime,timezone
                if utc(labels['reviewed_at'])>datetime.now(timezone.utc):
                    raise ValueError('HOLDOUT_LABEL_REVIEW_NOT_PRE_RUN')
        selected_config=next((row for row in prepared['configs'] if row['config_id']==args.config_id),None)
        if selected_config is None:raise ValueError('Benchmark config not declared')
        roles=selected_config['roles']
        if roles['repair']!=roles['planner'] or roles['critic']!=roles['observer']:
            raise ValueError('This actual adapter requires inherited planner repair and observer critic roles')
        from scripts.benchmark_campaign import role_supported
        for stage in ('observer','planner'):
            model=roles[stage]['model']
            if not role_supported(prepared,stage,roles[stage]):
                raise ValueError('Model/provider is not eligible in this reviewed actual adapter')
            supplied=getattr(args,stage+'_model')
            if supplied and supplied!=model:raise ValueError('CLI model differs from frozen benchmark config')
            setattr(args,stage+'_model',model)
        if args.case_id not in prepared['packets']:raise ValueError('Benchmark case not declared')
        packet=checked_packet(prepared['packets'][args.case_id],actual=True)
        photo=Path(packet['photo']['path']) if packet['photo'] else None
        if args.photo and (photo is None or args.photo.resolve()!=photo):
            raise ValueError('Positional photo differs from manifest case')
    else:
        if args.case_id or args.config_id or args.photo is None:raise ValueError('Legacy test requires approved photo')
        from scripts.benchmark_campaign import MODELS
        if any(getattr(args,stage+'_model') and getattr(args,stage+'_model') not in MODELS[stage]
               for stage in ('observer','planner')):raise ValueError('Unlisted model requires frozen catalog manifest')
        photo=args.photo.resolve()
    # Test input binding, not a product-generated room answer or inventory.
    if packet is None and sha(photo)!='ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8':
        raise ValueError('Photo differs from this user-approved existing bedroom input')
    trace.mark('IDENTITY_PREFLIGHT')
    settings=JsonProviderSettingsStore()
    registry=KeyRegistry(settings,WindowsCredentialStore())
    routes=StageRoutingSettings(registry)
    route=routes.load()
    from decimal import Decimal
    from twinpulse_app.generation_approval import usd_limit
    maximum=24 if args.benchmark_profile else 10
    if (not 6<=args.request_cap<=maximum or usd_limit(args.cost_limit)>Decimal('1')
            or args.benchmark_profile and not args.recommended_nebius):
        raise ValueError('Reduced cap outside reviewed total scope')
    if (args.observer_model or args.planner_model) and not args.benchmark_profile:
        raise ValueError('Alternate pairs require explicitly authorized benchmark profile')
    if args.recommended_nebius:
        if args.benchmark_profile and args.observer_model and args.planner_model:
            route={}  # Select ONLY providers used by the frozen pair below.
        else:
            matches=[r for r in registry.state()['entries'] if r['provider_profile'] in ('nebius_token_factory','nebius_site_v2')]
            active=[r for r in matches if r.get('active')]
            matches=active or matches
            if len(matches)!=1:raise ValueError('One existing Nebius registration required; no ambiguous automatic selection')
            route={'observer':{'key_id':matches[0]['id'],'model_id':'deepseek-ai/DeepSeek-V4.1-Flash'},
                   'planner':{'key_id':matches[0]['id'],'model_id':'nvidia/Nemotron-3_5-Lightning'}}
        if args.generation_only:raise ValueError('Recommended combination requires actual current-render review')
    elif (route['observer']['model_id']!='gpt-5.4-mini' or route['planner']['model_id']!='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'):
        raise ValueError('Existing approved model combination changed')
    if args.benchmark_profile:
        for stage,model in (('observer',args.observer_model),('planner',args.planner_model)):
            if model:
                profiles={'openai'} if model=='gpt-6-luna' else {'nebius_token_factory','nebius_site_v2'}
                matches=[r for r in registry.state()['entries'] if r['provider_profile'] in profiles]
                matches=[r for r in matches if r.get('active')] or matches
                if len(matches)!=1:raise ValueError('One existing stage registration required')
                route[stage]={'key_id':matches[0]['id'],'model_id':model}
    for stage in ('observer','planner'):
        if not registry.resolve(registry.settings_for_entry(route[stage]['key_id'])).is_configured():
            raise ValueError('Existing registered stage credential unavailable')
    output.mkdir(parents=True,exist_ok=False)
    config=output/'reviewed-settings'
    config.mkdir()
    oldpaths=[settings.path,registry.path,routes.path]
    if not prepared:
        oldpaths += [routes.harness_store()._path(value['sha256'])
                     for value in (routes.harness_bindings(routes.load()) or {}).values()]
    historical=ROOT/'artifacts/pre-demo-20261009'
    oldpaths += [historical/folder/'campaign.json' for folder in
        ('saved-stage-300s-five','saved-stage-20000-five','saved-stage-batch','mixed-corrected-scope')
        if (historical/folder/'campaign.json').is_file()]
    if prepared:
        oldpaths += [args.benchmark_manifest.resolve(),
                     *[Path(p) for p in prepared['freeze']]]
    originals={str(p):sha(p) for p in oldpaths}
    trace.mark('SETTINGS_ISOLATION')
    copy_trial_settings(settings,registry,routes,config,manifest_bound=prepared is not None)
    copied=KeyRegistry(JsonProviderSettingsStore(config/settings.path.name),WindowsCredentialStore())
    trial_route=dict(route)
    trial_route['observer']={**route['observer'],'max_output_tokens':20000 if args.recommended_nebius else 4000}
    trial_route['planner']={**route['planner'],'max_output_tokens':20000,
        'thinking_mode':'disabled' if route['planner']['model_id'] in
            ('nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B','nvidia/Nemotron-3_5-Lightning') else 'default'}
    if prepared:
        from scripts.benchmark_protocol import frozen_stage_output_caps
        for stage,cap in frozen_stage_output_caps(selected_config).items():
            trial_route[stage]['max_output_tokens']=cap
    if prepared and prepared.get('model_catalog'):
        from twinpulse_provider.model_contracts import checked_catalog,catalog_sha
        from datetime import datetime,timezone
        catalog=checked_catalog(prepared['model_catalog'],now=datetime.now(timezone.utc))
        trial_route['model_catalog_sha256']=catalog_sha(catalog)
        with (config/'stage_model_catalog.json').open('x',encoding='utf-8') as stream:
            json.dump(catalog,stream,ensure_ascii=False,indent=2,allow_nan=False)
    policy=replace(GenerationPolicy(),max_requests=args.request_cap,
        external_final_review=args.recommended_nebius)
    if args.benchmark_profile:
        policy=replace(policy,initial_timeout_s=420,final_timeout_s=180)
    trial_route['generation_policy']=policy.validate().to_dict()
    if prepared and effective_settings_sha(trial_route,roles)!=selected_config['settings_sha256']:
        raise ValueError('Effective stage/output/time/repair policy differs from frozen benchmark config')
    trace.mark('ROUTE_SAVE_READBACK')
    StageRoutingSettings(copied).save(trial_route,lambda:None)
    manifest={'schema_version':'ordinary-staged-live-test-1.0',
        'approval':args.approval_text,
        'photo_sha256':sha(photo) if photo else None,
        'photo_name':photo.name if photo else None,'route':trial_route,'cost_limit_usd':args.cost_limit,
        'automatic_new_approval':False,'physical_authority':False,'originals_at_start':originals,
        'openai_price_source':'https://developers.openai.com/api/docs/models/gpt-5.4-mini'}
    if os.environ.get('TWINPULSE_BENCHMARK_EXPIRES_AT') is not None:
        from twinpulse_provider.reliability import check_benchmark_dispatch_deadline
        check_benchmark_dispatch_deadline()
        manifest['benchmark_expires_at']=os.environ['TWINPULSE_BENCHMARK_EXPIRES_AT']
    manifest['generation_only']=args.generation_only
    if packet:
        case_path=output/'benchmark-case.json'
        with case_path.open('x',encoding='utf-8') as stream:
            json.dump(packet,stream,ensure_ascii=False,indent=2,allow_nan=False)
        manifest.update(benchmark_case_sha256=sha(case_path),
            benchmark_manifest_sha256=prepared['manifest_sha256'],case_id=packet['case_id'],
            config_id=args.config_id,settings_sha256=selected_config['settings_sha256'],
            input_kind=packet['modality'],goal_sha256=packet['goal']['sha256'])
        if prepared.get('execution_environment'):
            from scripts.benchmark_environment import identity
            manifest.update(execution_environment_sha256=identity(prepared['execution_environment']),
                            evaluation_rubric_sha256=prepared['evaluation']['rubric_sha256'])
    trace.mark('APPROVAL_METADATA')
    (output/'approval.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # Metadata GET only; refuses cost growth before inference. Existing model
    # catalog and secure store are reused, not the old campaign approval.
    from scripts.prepare_split_evaluation import nebius_rate
    from twinpulse_app.generation_approval import REVIEWED_PRICES
    reviewed_prices=dict(REVIEWED_PRICES)
    trace.mark('MODEL_METADATA_PREFLIGHT')
    if prepared and prepared.get('model_catalog'):
        from twinpulse_provider.model_contracts import catalog_prices
        reviewed_prices.update(catalog_prices(prepared['model_catalog']))
    if args.recommended_nebius:
        from scripts.compare_model_roles_live import metadata_get
        catalog,catalog_sha=[],None
        if any(trial_route[s]['model_id']!='gpt-6-luna' for s in ('observer','planner')):
            neb=[r for r in copied.state()['entries'] if r['provider_profile'] in ('nebius_token_factory','nebius_site_v2')]
            neb=[r for r in neb if r.get('active')] or neb
            if len(neb)!=1:raise ValueError('One existing Nebius metadata registration required')
            catalog,catalog_sha=metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info',
                copied.resolve(copied.settings_for_entry(neb[0]['id'])))
        account=None;account_sha=None
        if prepared and prepared.get('model_catalog') and catalog:
            account,account_sha=metadata_get('https://api.tokenfactory.nebius.com/v1/models',
                copied.resolve(copied.settings_for_entry(neb[0]['id'])))
        checks={}
        for stage in ('observer','planner'):
            model=trial_route[stage]['model_id'];reviewed=reviewed_prices[model]
            if model in checks:continue  # Same exact model metadata is checked once.
            if model=='gpt-6-luna':
                available,available_sha=metadata_get('https://api.openai.com/v1/models',
                    copied.resolve(copied.settings_for_entry(trial_route[stage]['key_id'])))
                if not any(r['id']==model for r in available['data']):raise ValueError('Luna not available for registered account')
                checks[model]={'account_models_sha256':available_sha,'rate_source':reviewed['source'],
                    'rates':{k:reviewed[k] for k in ('input_per_million','output_per_million','context_tokens')}}
                continue
            rows=[f for r in catalog for f in r.get('flavors',[]) if f.get('model_id')==model]
            if len(rows)!=1:raise ValueError('Reviewed model not available')
            item=rows[0]
            if prepared and prepared.get('model_catalog'):
                from twinpulse_provider.model_contracts import model_supported
                frozen=next(r for r in prepared['model_catalog']['models'] if r['model_id']==model)
                if sorted(set(item.get('use_cases',[])) & {'text','image'})!=frozen['modalities']:
                    raise ValueError('Current model modalities differ from frozen catalog')
            if account is not None and not any(r['id']==model for r in account['data']):
                raise ValueError('Frozen model not available for registered account')
            rate=dict(input_per_million=str(item['input_price_per_million_tokens']),
                output_per_million=str(item['output_price_per_million_tokens']),context_tokens=item['max_model_len'])
            if any(Decimal(str(rate[k]))!=Decimal(str(reviewed[k])) for k in rate):
                raise ValueError('Current model pricing/context differs from reviewed approval rates')
            checks[model]=rate
        manifest['nebius_price_check']={'rates':checks,'source_sha256':catalog_sha}
        if account_sha:manifest['nebius_price_check']['account_models_sha256']=account_sha
    else:
        rate=nebius_rate(copied,copied.settings_for_entry(trial_route['planner']['key_id']))
        reviewed=REVIEWED_PRICES[trial_route['planner']['model_id']]
        if any(str(rate[k])!=str(reviewed[k]) for k in ('input_per_million','output_per_million','context_tokens')):
            raise ValueError('Current Nebius pricing differs from reviewed ordinary approval rates')
        manifest['nebius_price_check']=rate
    (output/'approval.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'APPROVAL_READY','max_requests':args.request_cap,'limit_usd':args.cost_limit,'robot_connections':0}),flush=True)
    command=journey_command(output,photo,config/settings.path.name,generation_only=args.generation_only,
        benchmark_case=output/'benchmark-case.json' if packet else None)
    try:
        trace.mark('JOURNEY_DISPATCH_INTENT')
        with (output/'runner.log').open('x',encoding='utf-8') as log:
            completed=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800,
                env={**os.environ,'TWINPULSE_ORDINARY_TEST_CAP':str(args.request_cap),
                    'TWINPULSE_ORDINARY_TEST_USD':args.cost_limit},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        result=json.loads((output/'run-1/result.json').read_text(encoding='utf-8'))
        trace.mark('JOURNEY_RETURNED')
        result['runner_returncode']=completed.returncode
    except Exception as error:
        result={'status':'FAIL','error_type':type(error).__name__,'error':str(error)[:800]}
    if prepared and prepared.get('execution_environment'):
        try:
            after=verify_environment(prepared,ROOT)
            result['benchmark_environment_audit']=dict(before=environment_before,after=after)
        except (ValueError,OSError) as error:
            result.update(status='FAIL',error_type=type(error).__name__,error=str(error)[:800],
                          benchmark_environment_audit=dict(before=environment_before,after=None))
    result['originals_unchanged']=all(Path(p).is_file() and sha(Path(p))==digest for p,digest in originals.items())
    if not result['originals_unchanged']:result.update(status='FAIL',error='Original metadata/history changed')
    trace.mark('SUMMARY_WRITTEN')
    (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'ordinary_live_audit':result.get('ordinary_live_audit'),
        'error':result.get('error'),'originals_unchanged':result['originals_unchanged']},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
