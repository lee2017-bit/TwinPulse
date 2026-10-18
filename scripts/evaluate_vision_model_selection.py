# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit, bounded existing-Nebius model evaluation. No robots or deployment.

Metadata GETs are not inference. Every model/repair POST uses the existing
durable ledger. A reused observation is labelled, hash-bound, never called fresh.
The caller must hold human approval for the exact photo, provider and budget.
"""
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
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app import JsonProviderSettingsStore, WindowsCredentialStore
from twinpulse_app.project_store import ProjectStore
from twinpulse_core import execute_site_tool_plan
from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider import GenerationRequest,ImageInput,CancellationToken,GenerationService
from twinpulse_provider.nebius_pipeline import (
    NebiusChatCompletionsPipelineProvider,ObservationArtifact,_RejectRedirects,
)
from twinpulse_provider.reliability import (
    CampaignLedger,InferenceEvidence,AuditedChatTransport,utc_now,safe_text,
)
from packages.twinpulse_provider.tests.test_nebius_pipeline import config
from scripts.replay_audited_inference import ExactAuditedResponses

ORIGIN='https://api.tokenfactory.nebius.com'


def saved(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)


def format_observer_body(body,mode):
    body=deepcopy(body)
    if mode!='strict':
        schema=body['response_format']['json_schema']['schema']
        body['messages'][0]['content']+=' Return ONLY one complete JSON object matching this schema: '+json.dumps(schema,separators=(',',':'))
        if mode=='instance':
            body['messages'][0]['content']+= (
                ' The schema above is a DEFINITION, not the output. Do NOT emit type, properties, required, '
                'additionalProperties or const. Output an INSTANCE with exactly this root shape: '
                '{"schema_version":"1.1","summary":"your visible evidence",'
                '"entities":[],"relations":[],"dimensions":[],"ambiguities":[]}. '
                'Fill arrays ONLY with visible evidence, not one item per enum. IDs must be unique. '
                'kind is a coarse enum, category is a specific reusable catalogue enum; do not interchange them. '
                'A physical household object uses kind=static_obstacle, role=object and its catalogue category; '
                'floor/wall use kind=floor/wall and role=structure. A door leaf is an object, not an aperture. '
                'A window blind or ceiling light is an object, not structural floor/wall. '
                'Free space uses kind=free_space, role=free_space, category=aisle. '
                'An unidentified visible object uses kind=unknown, role=unknown, category=unknown. '
                'Do not emit absent objects. Relations must use only listed enum values and real unique entity IDs. '
                'Use null for unreadable metric dimensions. Do not copy the example summary; describe this image.'
            )
        body['response_format']={'type':'json_object' if mode in {'json_object','instance'} else 'text'}
    return body


def observer_body(provider,request,mode):
    return format_observer_body(provider.build_observer_body(request),mode)


def summarize(args):
    """Read-only raw/history audit, then one new report; never loads a key."""
    from twinpulse_provider.nebius_pipeline import parse_chat_completion, observation_json_schema
    scope=saved(args.output/'approval.json'); ledger=saved(args.campaign)
    cases=[];responses=[];all_ids=[]
    for path in sorted(args.output.glob('*.json')):
        row=saved(path)
        if 'case' not in row:continue
        cases.append({k:row.get(k) for k in ('case','model','format','status','elapsed_s','error','code','new_call_ids')})
        all_ids.extend(row['new_call_ids'])
        for identity in row['new_call_ids']:
            rawpath=args.output/'responses'/(identity+'.json'); evidence=saved(rawpath)
            entries=[x for x in ledger['requests'] if x['attempt_id']==identity]
            if len(entries)!=1 or entries[0]['status']!='received' or not entries[0].get('finished_at'):
                raise ValueError('Comparison requires settled matching ledger rows')
            raw=evidence['response_redacted'].encode()
            if (hashlib.sha256(raw).hexdigest()!=evidence['stored_response_sha256']
                    or evidence['response_truncated'] or evidence['http_status']!=200):
                raise ValueError('Comparison stored response hash/status mismatch')
            completion=parse_chat_completion(json.loads(raw)); payload=json.loads(completion.content)
            if completion.model_id!=entries[0]['model_id']:raise ValueError('Model identity changed')
            try:ObservationArtifact.from_mapping(payload); contract='VALID'
            except Exception as error:contract=safe_text(str(error),limit=250)
            ids=[x.get('id') for x in payload.get('entities',[]) if isinstance(x,dict)]
            schema=observation_json_schema('1.1')
            entity_spec=schema['properties']['entities']['items']['properties']
            content_problems=[]
            for n,item in enumerate(payload.get('entities',[])):
                if not isinstance(item,dict):continue
                for field in ('kind','role','category','region'):
                    if item.get(field) not in entity_spec[field]['enum']:
                        content_problems.append(dict(path=f'$.entities[{n}].{field}',value=item.get(field),reason='enum mismatch'))
            if len(ids)!=len(set(ids)):content_problems.append(dict(path='$.entities[*].id',reason='duplicate IDs'))
            responses.append(dict(attempt_id=identity,model=completion.model_id,http_status=200,
                finish_reason=completion.finish_reason,usage=dict(completion.usage),elapsed_s=evidence['elapsed_s'],
                raw_file_sha256=hashlib.sha256(rawpath.read_bytes()).hexdigest(),
                content_sha256=hashlib.sha256(completion.content.encode()).hexdigest(),
                captured_redaction_applied=evidence.get('redaction_applied'),contract=contract,
                content_problems=content_problems,case_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    new_entries=ledger['requests'][scope['start_count']:]
    if len(all_ids)!=len(set(all_ids)) or set(all_ids)!={x['attempt_id'] for x in new_entries}:
        raise ValueError('Case/ledger coverage mismatch')
    historical=canonical_sha256(ledger['requests'][:scope['start_count']])==scope['prior_requests_sha256']
    old=saved(args.source_run/'offline-length-repair-analysis.json')
    old_raw_unchanged=all(hashlib.sha256((args.source_run/'runtime/provider-evidence'/name).read_bytes()).hexdigest()==digest
        for name,digest in old['original_raw_hashes'].items())
    total=sum((Decimal(x['charged_or_reserved_usd']) for x in ledger['requests']),Decimal(0))
    increment=sum((Decimal(x['charged_or_reserved_usd']) for x in new_entries),Decimal(0))
    summary=dict(status='AUDIT_PASS_NOT_PRODUCT_ACCEPTANCE',created_at=utc_now(),cases=cases,responses=responses,
        start_count=scope['start_count'],final_count=len(ledger['requests']),request_ceiling=scope['request_ceiling'],
        calls_used=len(new_entries),remaining_calls=scope['request_ceiling']-len(ledger['requests']),
        pending=sum(not x.get('finished_at') for x in ledger['requests']),dispatch_lock=args.campaign.with_suffix('.dispatch-lock').exists(),
        historical_prefix_unchanged=historical,original_failure_raw_unchanged=old_raw_unchanged,
        photo_sha256=hashlib.sha256(args.photo.read_bytes()).hexdigest(),photo_scope_unchanged=hashlib.sha256(args.photo.read_bytes()).hexdigest()==scope['photo_sha256'],
        incremental_estimated_usd=str(increment),total_estimated_plus_reserved_usd=str(total),invoice_verified=False,
        metadata_inference_calls=0,observer_completions=len(responses),validated_observations=sum(x['contract']=='VALID' for x in responses),
        planner_calls=sum('Nemotron' in x['model_id'] for x in new_entries),new_accepted_scenes=sum(x['status']=='PLAN_AND_LOCAL_GEOMETRY_VALIDATED' for x in cases),
        actual_isaac='NOT_RUN',robot_calls=0,whole_demo_pass=False,
        interpretation='Same-json-mode pairs compare models; strict vs JSON pairs change format and prompt, not a decoder-only controlled comparison. One photo is not a general success-rate benchmark.')
    if not historical or not old_raw_unchanged or summary['pending'] or summary['dispatch_lock'] or summary['remaining_calls']<0 or not summary['photo_scope_unchanged']:
        raise ValueError('Audit failed; no PASS report')
    write_new(args.output/'summary-final.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','calls_used','remaining_calls','final_count','pending','incremental_estimated_usd','total_estimated_plus_reserved_usd','planner_calls')}),flush=True)


def inspect(args,settings,credential):
    args.output.mkdir(parents=True,exist_ok=False)
    opener=urllib.request.build_opener(_RejectRedirects())
    key=credential.load()
    if not key:raise ValueError('Existing credential unavailable')
    def get(path):
        url=ORIGIN+path
        with opener.open(urllib.request.Request(url,headers={'Authorization':'Bearer '+key}),timeout=20) as response:
            if response.geturl()!=url:raise ValueError('Metadata redirect refused')
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Metadata too large')
        return json.loads(raw),hashlib.sha256(raw).hexdigest()
    accounts,account_sha=get('/v1/models?verbose=true')
    catalogue,catalogue_sha=get('/private/v1/models_info')
    key=None
    visible={x['id'] for x in accounts['data']}
    models=[]
    for row in catalogue:
        for flavor in row.get('flavors',[]):
            identity=flavor.get('model_id','')
            uses=flavor.get('use_cases',[])
            if 'image' not in uses and 'nemotron' not in identity.lower():continue
            models.append(dict(model_id=identity,account_visible=identity in visible,use_cases=uses,
                context_tokens=flavor.get('max_model_len'),input_per_million=str(flavor.get('input_price_per_million_tokens')),
                output_per_million=str(flavor.get('output_price_per_million_tokens'))))
    state=saved(args.campaign)
    parent=saved(ROOT/'artifacts/pre-demo-20261008/photo-contract-add10-approval.json')
    photo_hash=hashlib.sha256(args.photo.read_bytes()).hexdigest()
    if photo_hash!=parent['photo_sha256']:raise ValueError('Photo not in approved scope')
    cap=min(parent['batch_request_ceiling']-len(state['requests']),6)
    if cap<1:raise ValueError('No remaining approved calls')
    write_new(args.output/'approval.json',dict(
        approval='User: Nemotron이 잘되면 제일 좋고 안되면 어쩔수없다 가리지않고 테스트해보자',
        approved_scope='Exact existing bedroom photo; existing Nebius provider; image model comparison and NVIDIA planner; no new GPU deployment',
        photo_sha256=photo_hash,start_count=len(state['requests']),request_ceiling=len(state['requests'])+cap,
        prior_requests_sha256=canonical_sha256(state['requests']),limit_usd=state['limit_usd'],
        campaign_limit=state['max_requests'],timeout_s=300,output_cap=10000,
        models=models,account_response_sha256=account_sha,catalogue_response_sha256=catalogue_sha,
        catalogue_source=ORIGIN+'/private/v1/models_info',verified_at=utc_now(),inference_calls=0))
    print(json.dumps(dict(inference_calls=0,remaining_calls=cap,models=models)),flush=True)


async def evaluate(args,settings,credential):
    scope=saved(args.output/'approval.json'); state=saved(args.campaign)
    if (scope['prior_requests_sha256']!=canonical_sha256(state['requests'][:scope['start_count']])
        or state['limit_usd']!=scope['limit_usd'] or state['max_requests']!=scope['campaign_limit']
        or hashlib.sha256(args.photo.read_bytes()).hexdigest()!=scope['photo_sha256']):
        raise ValueError('Scope/history/photo changed; no inference')
    remaining=scope['request_ceiling']-len(state['requests'])
    if remaining<1:raise ValueError('Local batch ceiling reached')
    ledger=CampaignLedger.open_existing_approved(args.campaign,run_request_cap=min(remaining,3 if args.pipeline else 2 if args.plan else 1))
    selected=args.model
    metadata=next((x for x in scope['models'] if x['model_id']==selected),None)
    if not metadata or not metadata['account_visible'] or 'image' not in metadata['use_cases']:
        raise ValueError('No account-visible image capability; do not dispatch')
    for identity in (selected,settings.model_id):
        rate_meta=next(x for x in scope['models'] if x['model_id']==identity)
        rate=dict(input_per_million=rate_meta['input_per_million'],output_per_million=rate_meta['output_per_million'],
            context_tokens=rate_meta['context_tokens'],source=scope['catalogue_source'],
            verified_at=scope['verified_at'],source_sha256=scope['catalogue_response_sha256'])
        if identity in ledger.state['rates']:
            prior=ledger.state['rates'][identity]
            if any(Decimal(prior[k])!=Decimal(rate[k]) for k in ('input_per_million','output_per_million')) or prior['context_tokens']!=rate['context_tokens']:
                raise ValueError('Existing pricing changed; no accounting rewrite')
        else:ledger.register_verified_rate(identity,rate)
    name=args.case
    if not name.isascii() or not name.replace('-','').replace('_','').isalnum():raise ValueError('Invalid case identity')
    result_path=args.output/(name+'.json')
    if result_path.exists():raise ValueError('Case already exists; no implicit retry')
    prior_input=ProjectStore(args.source_run/'runtime/active_project.json').load().latest_input
    request=GenerationRequest('vision-'+name,prior_input.prompt,
        (ImageInput(args.photo.name,'image/jpeg',args.photo.read_bytes()),),image_detail='auto')
    real=AuditedChatTransport(credential.load,InferenceEvidence(args.output/'responses'),ledger)
    provider=NebiusChatCompletionsPipelineProvider(real,observer_model_id=selected,
        planner_model_id=settings.model_id,site_plan_version='2.2',compact_photo_layout=True,
        planner_template_no_thinking=True,output_token_cap=10000,max_repairs=1 if args.plan or args.pipeline else 0)
    body=observer_body(provider,request,args.format)
    row=dict(case=name,model=selected,format=args.format,photo_sha256=scope['photo_sha256'],
        request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
        schema_sha256=hashlib.sha256(json.dumps(body['response_format'],sort_keys=True).encode()).hexdigest(),
        prompt=prior_input.prompt,output_cap=10000,timeout_s=300,started_at=utc_now(),
        status='STARTED',robot_calls=0,actual_isaac='NOT_RUN',physical_or_metric_accuracy='UNVERIFIED')
    token=CancellationToken();started=time.monotonic();c=None
    try:
        if args.plan or args.pipeline:
            if args.plan:
                prior=saved(args.output/(args.plan+'.json'))
                if prior.get('status')!='OBSERVATION_VALIDATED' or prior['model']!=selected or prior['format']!=args.format:
                    raise ValueError('Only a validated exact same-mode observation may be reused')
                exact=ExactAuditedResponses(args.campaign,args.output/'responses',[prior['attempt_id']])
                class ReuseAndPlan:
                    used=False
                    async def complete(self,original,token,cfg):
                        if not self.used:
                            if original!=provider.build_observer_body(request):raise ValueError('Unexpected observer request')
                            value=await exact.complete(body,token,cfg)
                            self.used=True
                            return value
                        return await real.complete(original,token,cfg)
                provider._transport=ReuseAndPlan()
                row['observation_source']=dict(kind='EXACT_PREVIOUS_LIVE_RESPONSE',case=args.plan,attempt_id=prior['attempt_id'],new_observer_calls=0)
            else:
                class FreshFormattedPipeline:
                    async def complete(self,original,token,cfg):
                        is_observer=original.get('response_format',{}).get('json_schema',{}).get('name')=='twinpulse_image_observation'
                        return await real.complete(format_observer_body(original,args.format) if is_observer else original,token,cfg)
                provider._transport=FreshFormattedPipeline()
                row.update(observation_source=dict(kind='FRESH_LIVE',reused_calls=0),
                    prompt_variant='generic-schema-instance-example' if args.format=='instance' else args.format,
                    experimental_format_only=True)
            result=await GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request)
            draft=execute_site_tool_plan(result.plan,source='photo',source_ref=scope['photo_sha256'])
            write_new(args.output/(name+'-plan.json'),result.plan.to_dict())
            row.update(status='PLAN_AND_LOCAL_GEOMETRY_VALIDATED',provider_provenance=dict(result.provider_provenance),
                object_count=len(draft.scene.objects),whole_demo_pass=False)
        else:
            c=await asyncio.wait_for(real.complete(body,token,config(timeout_s=300)),300)
            if c.model_id!=selected:raise ValueError('Response identity mismatch')
            obs=ObservationArtifact.from_mapping(json.loads(c.content))
            row.update(status='OBSERVATION_VALIDATED',attempt_id=c.attempt_id,finish_reason=c.finish_reason,
                usage=dict(c.usage),observation=obs.to_dict(),response_content_sha256=hashlib.sha256(c.content.encode()).hexdigest())
    except Exception as error:
        row.update(status='FAIL',error_type=type(error).__name__,error=safe_text(str(error),limit=800),
            code=getattr(error,'code',None),http_status=getattr(error,'http_status',None),
            attempt_id=getattr(error,'attempt_id',None))
        if c is not None:
            row.update(attempt_id=c.attempt_id,finish_reason=c.finish_reason,usage=dict(c.usage),
                response_content_sha256=hashlib.sha256(c.content.encode()).hexdigest(),
                completion_received=True,contract_validated=False)
    finally:
        token.cancel()
        row.update(elapsed_s=round(time.monotonic()-started,3),new_call_ids=list(real.calls),
            diagnostics=provider.diagnostic_for(request.request_id) if args.plan or args.pipeline else {})
        # The blocking audit worker may finish after asyncio's timeout. Wait
        # without dispatching or refunding; retain a visible lock on failure.
        until=time.monotonic()+25
        while ledger.lock_path.exists() and time.monotonic()<until:await asyncio.sleep(.25)
        latest=saved(args.campaign)
        row.update(ledger_count=len(latest['requests']),pending=sum(not x.get('finished_at') for x in latest['requests']),
            estimated_plus_reserved_usd=str(sum((Decimal(x['charged_or_reserved_usd']) for x in latest['requests']),Decimal(0))),
            historical_prefix_unchanged=canonical_sha256(latest['requests'][:scope['start_count']])==scope['prior_requests_sha256'])
        write_new(result_path,row)
    print(json.dumps({k:row[k] for k in ('case','status','elapsed_s','new_call_ids','ledger_count','pending','estimated_plus_reserved_usd')}),flush=True)
    return 0 if row['status']!='FAIL' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--photo',type=Path,required=True)
    parser.add_argument('--source-run',type=Path,required=True)
    parser.add_argument('--inspect',action='store_true')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--case')
    parser.add_argument('--format',choices=('strict','json_object','text','instance'),default='strict')
    parser.add_argument('--plan',help='Explicit reuse of this successful observation case; fresh planner and bounded repair')
    parser.add_argument('--pipeline',action='store_true',help='Fresh observer, NVIDIA planner and at most one shared repair; at most 3 calls')
    parser.add_argument('--summarize',action='store_true',help='Offline immutable evidence/budget audit; no credentials or HTTP')
    args=parser.parse_args()
    if args.summarize:
        if args.inspect or args.live or args.plan or args.pipeline:raise SystemExit('Offline summary cannot dispatch')
        summarize(args)
        raise SystemExit(0)
    settings=JsonProviderSettingsStore().load().validated()
    if (settings.provider_profile not in {'nebius_site_v2','nebius_token_factory'}
        or settings.adapter_kind!='nebius_chat_completions_pipeline' or settings.base_url!=ORIGIN+'/v1/'):
        raise SystemExit('Existing Nebius site profile required')
    credentials=WindowsCredentialStore(settings.credential_ref)
    if args.inspect:
        if args.live or args.plan or args.pipeline:raise SystemExit('Metadata-only inspection does not imply inference')
        inspect(args,settings,credentials)
    elif args.live and args.model and args.case:
        if args.plan and args.pipeline:raise SystemExit('Choose exact reuse or fresh pipeline, not both')
        raise SystemExit(asyncio.run(evaluate(args,settings,credentials)))
    else:raise SystemExit('Explicit --inspect or --live --model --case required; no inference')
