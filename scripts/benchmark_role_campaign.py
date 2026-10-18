# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reusable public-input role screening, distinct from full App/Isaac acceptance.

One fixed Luna observation per room is shared by every planner. It is a model
output, not an oracle. Responses, failures and cost reservations remain local.
The same source/caps/policy are frozen for the entire owner process. An explicitly
approved continuation skips all previously started jobs, carries every hold, and
uses a new source cohort. No grants, private fixture or robot operation.
"""
import argparse
import asyncio
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.compare_model_roles_live import (credentials,metadata_get,save,sha,LUNA,ComparisonLedger,
    run_case,FailureStreak)
from scripts.benchmark_protocol import source_freeze,canonical_sha,text_sha
from scripts.run_model_combination_benchmark import distribution
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.reliability import utc_now,safe_text
from twinpulse_provider.model_contracts import catalog_from_inventory
from scripts.benchmark_late_usage import CollectingLedger,LateUsageCollector

DEADLINE='2026-10-11T09:00:00+00:00'
APPROVAL=('2026-10-11 human explicitly approved existing public CC BY-SA room photos, '
          'derived Isaac renders and trial texts to Nebius comparison models and OpenAI gpt-6-luna; '
          'USD5 total/provider including all previous usage and unknown reservations; '
          'until 18:00 KST. Private bedroom and robot excluded. Output-limit, unknown-cost '
          'and five-distinct-models same-root stop rules retained.')


def load_continuation(root, audit_path, audit_sha, acknowledged, cases, carry):
    """Read-only admission from a sealed pre-change audit, never a retry/refund.

    A human acknowledgement applies only to the named old holds. New uncertain
    requests remain subject to the normal terminal-stop rule in the new ledger.
    """
    root=Path(root).resolve();audit_path=Path(audit_path).resolve()
    if not audit_sha or sha(audit_path)!=audit_sha:raise ValueError('ROLE_PRIOR_AUDIT_SHA_CHANGED')
    audit=json.loads(audit_path.read_text(encoding='utf-8'))
    if audit.get('schema_version')=='closed-role-prefix-seal-1.0':
        return load_closed_continuation(root,audit_path,audit_sha,audit,acknowledged,cases,carry)
    if audit.get('schema_version')!='interrupted-public-role-audit-1.0' or audit.get('integrity_status')!='PASS' or audit.get('integrity_errors'):
        raise ValueError('ROLE_PRIOR_AUDIT_NOT_VERIFIED')
    if set(audit['stop_reasons'])-{'INTERRUPTED_CAMPAIGN_NO_FINAL_REPORT','REMOTE_UNKNOWN_NEBIUS','REMOTE_UNKNOWN_OPENAI'}:
        raise ValueError('ROLE_PRIOR_STOP_NOT_AUTHORIZED')
    if (root/'owner.lock').exists() or any((root/(p+'.ledger.dispatch-lock')).exists() for p in ('nebius','openai')):
        raise ValueError('ROLE_PRIOR_OWNER_OR_DISPATCH_LOCK')
    files=audit['original_files_sha256']
    current={str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()}
    if set(current)!=set(files) or any(p.is_symlink() or sha(p)!=files[name] for name,p in current.items()):
        raise ValueError('ROLE_PRIOR_ORIGINAL_CHANGED')
    scope=json.loads((root/'scope.json').read_text(encoding='utf-8'))
    if scope['case_inputs']!=cases or scope['expires_at']!=DEADLINE:
        raise ValueError('ROLE_PRIOR_INPUT_OR_DEADLINE_CHANGED')
    expected=dict(common_output_cap=40000,per_http_timeout_s=300,planner_request_cap=12,
                  planner_repair_cap=3,planner_total_timeout_s=1800)
    if any(scope[k]!=v for k,v in expected.items()):raise ValueError('ROLE_PRIOR_POLICY_CHANGED')
    if any(sha(Path(p))!=h for p,h in scope['settings_hashes'].items()):
        raise ValueError('ROLE_PRIOR_GLOBAL_SETTINGS_CHANGED')
    unknown=set()
    for provider in ('nebius','openai'):
        ledger=json.loads((root/(provider+'.ledger.json')).read_text(encoding='utf-8'))
        rows=ledger['requests']
        if any(not r.get('finished_at') or r['status'] not in ('received','outcome_unknown') for r in rows):
            raise ValueError('ROLE_PRIOR_REQUEST_STILL_PENDING')
        unknown.update(r['attempt_id'] for r in rows if r['status']=='outcome_unknown')
        total=Decimal(scope['existing_exposure_usd'][provider])+sum((Decimal(r['charged_or_reserved_usd']) for r in rows),Decimal(0))
        if total!=Decimal(carry[provider]) or total!=Decimal(audit['financial'][provider]['total_exposure_usd']):
            raise ValueError('ROLE_PRIOR_COST_MUST_CARRY_ALL_HOLDS')
        remaining(carry[provider])
    if unknown!=set(acknowledged):raise ValueError('ROLE_PRIOR_HELD_ACKNOWLEDGEMENT_REQUIRED')
    history=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((root/'progress').glob('*.json'))]
    count=audit['started_cases']
    if len(history)!=audit['reported_cases'] or count!=len(history)+1 or len(scope['jobs'])!=audit['planned']:
        raise ValueError('ROLE_PRIOR_PREFIX_AMBIGUOUS')
    if [r['job_id'] for r in history]!=[j['job_id'] for j in scope['jobs'][:len(history)]]:
        raise ValueError('ROLE_PRIOR_JOB_ORDER_CHANGED')
    skipped=scope['jobs'][count-1]
    starts=[p for p in (root/skipped['case_id']/'cases').glob('*/start.json') if
            (r:=json.loads(p.read_text(encoding='utf-8')))['role']==skipped['role'] and
            r['model_id']==skipped['model_id'] and r['repetition']==skipped['repeat']]
    if len(starts)!=1 or (starts[0].parent/'result.json').exists():raise ValueError('ROLE_PRIOR_INTERRUPTION_AMBIGUOUS')
    jobs=deepcopy(scope['jobs'][count:]);shared={};seeds={}
    if len(jobs)!=audit['undispatched']:raise ValueError('ROLE_PRIOR_REMAINING_COUNT_CHANGED')
    for case in cases:
        seed_job=next(j for j in scope['jobs'] if j['case_id']==case['case_id'] and j['role']=='observer' and
                      j['model_id']=='gpt-6-luna' and j['repeat']==1)
        source=next(r for r in history if r['job_id']==seed_job['job_id'] and r['status']=='PASS')
        path=root/case['case_id']/'cases'/source['case_id']/'observation.json'
        ref=json.loads((root/(case['case_id']+'-shared-observation.json')).read_text(encoding='utf-8'))
        artifact=ObservationArtifact.from_mapping(json.loads(path.read_text(encoding='utf-8')))
        if ref['source_job_id']!=source['job_id'] or ref['source_file_sha256']!=sha(path) or ref['sha256']!=canonical_sha(artifact.to_dict()) or ref['ground_truth']:
            raise ValueError('ROLE_PRIOR_SHARED_OBSERVATION_CHANGED')
        shared[case['case_id']]=artifact;seeds[case['case_id']]=dict(**ref,path=str(path))
    reference=dict(prior_root=str(root),prior_scope_sha256=sha(root/'scope.json'),
                   prior_audit_path=str(audit_path),prior_audit_sha256=audit_sha,
                   unchanged_original_files=len(files),skipped_started_jobs=count,
                   skipped_interrupted_job=skipped,acknowledged_old_held_attempts=sorted(unknown),
                   shared_observations=seeds,new_unknown_stops=True,prior_scores_merged=False)
    inventory=json.loads((root/'inventory.json').read_text(encoding='utf-8'))
    return dict(jobs=jobs,shared=shared,history=history,reference=reference,inventory=inventory,scope=scope)


def load_closed_continuation(root, audit_path, audit_sha, seal, acknowledged, cases, carry):
    """Only the sealed never-started suffix; late collection is a new cohort."""
    if seal.get('integrity_status')!='PASS':raise ValueError('ROLE_CLOSED_SEAL_INVALID')
    audited=Path(seal['independent_audit_path'])
    if sha(audited)!=seal['independent_audit_sha256']:raise ValueError('ROLE_CLOSED_AUDIT_CHANGED')
    audit=json.loads(audited.read_text(encoding='utf-8'))
    if audit['integrity_status']!='PASS' or audit['integrity_errors'] or audit['stop_reason']!='REMOTE_UNKNOWN':
        raise ValueError('ROLE_CLOSED_AUDIT_NOT_TIMEOUT_PREFIX')
    if (root/'owner.lock').exists() or any((root/(p+'.ledger.dispatch-lock')).exists() for p in ('nebius','openai')):
        raise ValueError('ROLE_PRIOR_OWNER_OR_DISPATCH_LOCK')
    files=seal['original_files_sha256'];current={str(p.relative_to(root)):p for p in root.rglob('*') if p.is_file()}
    if set(files)!=set(current) or any(p.is_symlink() or sha(p)!=files[n] for n,p in current.items()):
        raise ValueError('ROLE_PRIOR_ORIGINAL_CHANGED')
    scope=json.loads((root/'scope.json').read_text(encoding='utf-8'))
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    if sha(root/'scope.json')!=audit['original_scope_sha256'] or sha(root/'summary.json')!=audit['original_summary_sha256']:
        raise ValueError('ROLE_CLOSED_AUDITED_SUMMARY_CHANGED')
    if scope['case_inputs']!=cases or scope['expires_at']!=DEADLINE or any(sha(Path(p))!=h for p,h in scope['settings_hashes'].items()):
        raise ValueError('ROLE_PRIOR_INPUT_SETTINGS_OR_DEADLINE_CHANGED')
    caps=dict(common_output_cap=40000,per_http_timeout_s=300,planner_request_cap=12,planner_repair_cap=3,planner_total_timeout_s=1800)
    if any(scope[k]!=v for k,v in caps.items()):raise ValueError('ROLE_PRIOR_POLICY_CHANGED')
    history=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((root/'progress').glob('*.json'))]
    count=seal['completed_prefix'];earlier=seal['earlier_skipped_jobs'];full=seal['full_jobs']
    if len(history)!=count or count!=summary['ended'] or summary['interrupted_job'] is not None or full[earlier:]!=scope['jobs']:
        raise ValueError('ROLE_CLOSED_PREFIX_AMBIGUOUS')
    if [r['job_id'] for r in history]!=[j['job_id'] for j in scope['jobs'][:count]]:
        raise ValueError('ROLE_PRIOR_JOB_ORDER_CHANGED')
    oldroot=Path(scope['continuation']['prior_root'])
    oldaudit=Path(scope['continuation']['prior_audit_path'])
    if sha(oldaudit)!=scope['continuation']['prior_audit_sha256']:raise ValueError('ROLE_OLDER_AUDIT_CHANGED')
    older=json.loads(oldaudit.read_text(encoding='utf-8'))
    oldfiles={str(p.relative_to(oldroot)):p for p in oldroot.rglob('*') if p.is_file()}
    if set(oldfiles)!=set(older['original_files_sha256']) or any(sha(p)!=older['original_files_sha256'][n] for n,p in oldfiles.items()):
        raise ValueError('ROLE_OLDER_ORIGINAL_CHANGED')
    unknown=set(scope['continuation']['acknowledged_old_held_attempts'])
    for provider in ('nebius','openai'):
        ledger=json.loads((root/(provider+'.ledger.json')).read_text(encoding='utf-8'))
        if any(not r.get('finished_at') for r in ledger['requests']):raise ValueError('ROLE_PRIOR_REQUEST_STILL_PENDING')
        unknown.update(r['attempt_id'] for r in ledger['requests'] if r['status']=='outcome_unknown' or not r.get('usage'))
        total=Decimal(scope['existing_exposure_usd'][provider])+sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests']),Decimal(0))
        if total!=Decimal(carry[provider]) or total!=Decimal(seal['total_exposure_usd'][provider]):
            raise ValueError('ROLE_PRIOR_COST_MUST_CARRY_ALL_HOLDS')
        remaining(carry[provider])
    if unknown!=set(acknowledged):raise ValueError('ROLE_PRIOR_HELD_ACKNOWLEDGEMENT_REQUIRED')
    shared={};seeds=deepcopy(scope['continuation']['shared_observations'])
    for case_id,ref in seeds.items():
        path=Path(ref['path']);artifact=ObservationArtifact.from_mapping(json.loads(path.read_text(encoding='utf-8')))
        if sha(path)!=ref['source_file_sha256'] or canonical_sha(artifact.to_dict())!=ref['sha256'] or ref['ground_truth']:
            raise ValueError('ROLE_PRIOR_SHARED_OBSERVATION_CHANGED')
        shared[case_id]=artifact
    if set(shared)!={c['case_id'] for c in cases}:raise ValueError('ROLE_SHARED_COVERAGE_CHANGED')
    reference=dict(prior_root=str(root),prior_scope_sha256=sha(root/'scope.json'),prior_audit_path=str(audit_path),
        prior_audit_sha256=audit_sha,unchanged_original_files=len(files),older_original_files=len(oldfiles),
        skipped_started_jobs=earlier+count,skipped_interrupted_job=None,
        acknowledged_old_held_attempts=sorted(unknown),shared_observations=seeds,
        new_unknown_stops=True,prior_scores_merged=False)
    check_scope=deepcopy(scope);check_scope['jobs']=full
    return dict(jobs=deepcopy(full[earlier+count:]),shared=shared,history=history,reference=reference,
        inventory=json.loads((root/'inventory.json').read_text(encoding='utf-8')),scope=check_scope)


def validate_continuation_inventory(continuation, inventory, jobs, originals):
    old=continuation['inventory']
    by_id=lambda rows:{r['model_id']:r for r in rows}
    if by_id(old['models'])!=by_id(inventory['models']):raise ValueError('ROLE_PRIOR_MODEL_CATALOG_CHANGED')
    if originals!=continuation['scope']['settings_hashes']:raise ValueError('ROLE_PRIOR_SETTINGS_IDENTITY_CHANGED')
    prefix=continuation['reference']['skipped_started_jobs']
    # The metadata endpoint can reorder unchanged rows. Admission compares job
    # identity/coverage, then dispatches ONLY the sealed old ordering, not a new
    # shuffle of that incidental response order.
    identities=lambda rows:{r['job_id']:{k:r[k] for k in ('role','case_id','model_id','repeat')} for r in rows}
    if len(jobs)!=len(continuation['scope']['jobs']) or identities(jobs)!=identities(continuation['scope']['jobs']) or continuation['scope']['jobs'][prefix:]!=continuation['jobs']:
        raise ValueError('ROLE_PRIOR_SCHEDULE_CHANGED')

def remaining(exposure):
    result=Decimal('5')-Decimal(exposure)
    if not result.is_finite() or not 0<result<=5:raise ValueError('ROLE_EXISTING_EXPOSURE_INVALID')
    return str(result)

def public_cases(spec,path):
    """Explicit datasets only; no legacy PHOTO/PROMPT fallback."""
    if spec.get('schema_version')!='pilot-dataset-spec-1.0':raise ValueError('ROLE_DATASET_INVALID')
    rows=[]
    for row in spec['cases']:
        if not row['photo']:continue
        source=row['source']
        if not source['external_transmission_allowed'] or not source['public_release_allowed'] or not source['license'].startswith('CC BY-SA'):
            raise ValueError('ROLE_PUBLIC_PHOTO_PERMISSION_REQUIRED')
        photo=(path.parent/row['photo']).resolve()
        if not photo.is_file() or photo.is_symlink():raise ValueError('ROLE_PHOTO_INVALID')
        rows.append(dict(case_id=row['case_id'],room_group=row['room_group'],photo=str(photo),
            photo_sha256=sha(photo),prompt=row['prompt'],prompt_sha256=text_sha(row['prompt']),source=deepcopy(source)))
    if not rows or len({r['room_group'] for r in rows})!=len(rows) or len({r['photo_sha256'] for r in rows})!=len(rows):
        raise ValueError('ROLE_INDEPENDENT_INPUT_REQUIRED')
    return rows

def planned(models,cases,seed=61149):
    """Two repetitions per model/input, role-specific balanced cyclic order."""
    rng=random.Random(seed);jobs=[]
    for role in ('observer','planner'):
        available=[m for m in models if 'text' in m['use_cases'] and (role=='planner' or 'image' in m['use_cases'])]
        rng.shuffle(available)
        for block,(case,repeat) in enumerate((c,n) for n in (1,2) for c in cases):
            offset=block%len(available);order=available[offset:]+available[:offset]
            # Shared preprocessing is declared before output, not selected for quality.
            if role=='observer' and repeat==1:
                order=sorted(order,key=lambda m:m['model_id']!='gpt-6-luna')
            for position,m in enumerate(order):
                identity=dict(role=role,case_id=case['case_id'],model_id=m['model_id'],repeat=repeat)
                jobs.append(dict(job_id=canonical_sha(identity)[:32],position=position,**identity))
    return jobs

def limit_status(ledgers):
    return {p:dict(actual_calls=len(l.state['requests']),
        estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in l.state['requests']),Decimal(0))),
        pending_lock=l.lock_path.exists(),unknown=sum(r.get('status')=='outcome_unknown' for r in l.state['requests']))
        for p,l in ledgers.items()}

def aggregate(jobs,results,models):
    indexed={r['job_id']:r for r in results};groups=defaultdict(list)
    for job in jobs:groups[job['role'],job['model_id']].append(indexed.get(job['job_id']))
    table=[]
    for (role,model),rows in sorted(groups.items()):
        statuses=Counter(r['status'] if r else 'NOT_RUN' for r in rows)
        actual=[r for r in rows if r and r.get('actual_calls',0)>0]
        table.append(dict(role=role,model_id=model,planned=len(rows),pass_count=statuses['PASS'],
            fail_count=statuses['FAIL'],not_run=statuses['NOT_RUN'],independent_rooms=len({r['room_group'] for r in actual}),
            http_requests=sum(r.get('actual_calls',0) for r in actual),
            http_time=distribution([a['elapsed_s'] for r in actual for a in r.get('attempts',[]) if type(a.get('elapsed_s')) in (int,float)]),
            estimated_or_reserved_usd=str(sum((Decimal(r.get('estimated_or_reserved_usd','0')) for r in actual),Decimal(0))),
            failures=dict(Counter(r.get('failure_code') or r.get('not_run_reason') or 'unspecified' for r in rows if r and r['status']!='PASS'))))
    return table

def final_accounting_rows(output,results,ledgers):
    """Derived financial view only; immutable scored result/progress stays put."""
    from scripts.compare_model_roles_live import role_attempt_snapshot
    rows=deepcopy(results)
    for row in rows:
        if not row.get('actual_calls'):continue
        ledger=ledgers[row['provider']]
        evidence=output/row['input_case']/'cases'/row['case_id']/'evidence'
        attempts,errors=role_attempt_snapshot(row['attempt_ids'],evidence,ledger)
        if errors:raise ValueError('COLLECTION_FINAL_RAW_INCOMPLETE')
        row['scored_attempts']=row['attempts']
        row['scored_estimated_or_reserved_usd']=row['estimated_or_reserved_usd']
        row['attempts']=attempts
        row['estimated_or_reserved_usd']=str(sum((Decimal(a['estimated_or_reserved_usd']) for a in attempts),Decimal(0)))
        row['financial_view']='POST_TRIAL_SAME_HTTP_NO_RESULT_PROMOTION'
    return rows

async def bounded_role_case(output, job, runner, *args, **kwargs):
    """A reporting exception must stop the campaign without hiding spend.

    Do not synthesize result/progress or retry the interrupted job. Original
    start/ledger/dispatch files remain independent audit evidence.
    """
    try:
        return await runner(*args, **kwargs), None
    except Exception as error:
        failure=dict(job=deepcopy(job),error_type=type(error).__name__,
                     error=safe_text(str(error),limit=600),at=utc_now(),
                     status='HOST_REPORT_ABORTED',automatic_retry=False)
        save(output/'interrupted-job.json',failure)
        return None,failure


async def execute(args):
    output=args.output.resolve()
    expiry=datetime.fromisoformat(DEADLINE)
    if datetime.now(timezone.utc)>=expiry:raise ValueError('ROLE_APPROVAL_EXPIRED')
    cases=public_cases(json.loads(args.spec.read_text(encoding='utf-8')),args.spec.resolve())
    carry=dict(nebius=args.existing_nebius,openai=args.existing_openai)
    continuation=None
    if getattr(args,'continue_from',None):
        continuation=load_continuation(args.continue_from,args.prior_audit,args.prior_audit_sha256,
            args.acknowledge_held_attempt,cases,carry)
    approval=APPROVAL
    if continuation:
        approval+=' Human explicitly approved continuing undispatched jobs with the named prior UNKNOWN hold fully carried; no interrupted-job retry or deadline/cap extension.'
    collecting=getattr(args,'collect_late_usage',False)
    if collecting:
        approval+=' Latest human explicitly approved continuing other models after a scored timeout while the SAME request receiver collects late response/usage. Full reservations count until settlement; no retry, cap increase, refund, result promotion or deadline extension. Non-timeout unknown, evidence failure, output length and payment gates still stop.'
    if output.exists():raise ValueError('ROLE_NEW_DIRECTORY_REQUIRED_NO_RETRY')
    output.mkdir(parents=True)
    owner=output/'owner.lock'
    with owner.open('x',encoding='utf-8') as f:json.dump(dict(pid=os.getpid(),started_at=utc_now()),f)
    results=[];stop=None;ledgers={};interrupted=None;collector=None
    try:
        stores,originals=credentials()
        catalog,catalog_sha=metadata_get('https://api.tokenfactory.nebius.com/private/v1/models_info',stores['nebius'])
        visible,visible_sha=metadata_get('https://api.tokenfactory.nebius.com/v1/models?verbose=true',stores['nebius'])
        opened,opened_sha=metadata_get('https://api.openai.com/v1/models',stores['openai'])
        visible_ids={r['id'] for r in visible['data']};all_models=[]
        for group in catalog:
            for row in group.get('flavors',[]):
                all_models.append(dict(provider='nebius',model_id=row['model_id'],visible=row['model_id'] in visible_ids,
                    use_cases=row.get('use_cases',[]),context_tokens=row['max_model_len'],
                    input_per_million=str(row['input_price_per_million_tokens']),output_per_million=str(row['output_price_per_million_tokens'])))
        if not any(r['id']=='gpt-6-luna' for r in opened['data']):raise ValueError('ROLE_LUNA_NOT_CURRENTLY_VISIBLE')
        inventory=dict(created_at=utc_now(),models=all_models,catalog_sha256=catalog_sha,account_sha256=visible_sha,
            openai_models_sha256=opened_sha,metadata_calls=3,inference_calls=0)
        save(output/'inventory.json',inventory)
        save(output/'stage-model-catalog.json',catalog_from_inventory(inventory,valid_until=DEADLINE))
        models=[m for m in all_models if m['visible'] and 'text' in m['use_cases']]+[deepcopy(LUNA)]
        jobs=planned(models,cases)
        if continuation:
            validate_continuation_inventory(continuation,inventory,jobs,originals)
            jobs=continuation['jobs']
        frozen=source_freeze(ROOT)
        scope=dict(schema_version='public-role-screening-1.0',created_at=utc_now(),expires_at=DEADLINE,
            human_approval=approval,existing_exposure_usd=carry,total_limit_usd=dict(nebius='5',openai='5'),
            case_inputs=cases,jobs=jobs,seed=61149,repeats=2,source_freeze=frozen,
            settings_hashes=originals,common_output_cap=40000,per_http_timeout_s=300,
            planner_request_cap=12,planner_repair_cap=3,planner_total_timeout_s=1800,
            planner_observation='FIRST_LUNA_R1_PER_ROOM_SHARED_FIXED_LLM_OUTPUT_NOT_GROUND_TRUTH',
            thinking='LUNA_NONE_NANO_LIGHTNING_DISABLED_OTHERS_PROVIDER_DEFAULT',
            independent_critic='NOT_IMPLEMENTED',actual_isaac='NOT_RUN_ROLE_SCREENING',physical_authority=False,
            excluded_models=[m for m in all_models if not m['visible'] or 'text' not in m['use_cases']])
        if continuation:
            scope['continuation']=continuation['reference']
            if collecting:scope['continuation']['new_unknown_stops']='EXCEPT_HOST_RECORDED_SCORED_TIMEOUT_WITH_FULL_HOLD'
            for case_id,reference in continuation['reference']['shared_observations'].items():
                save(output/(case_id+'-shared-observation.json'),reference)
        save(output/'scope.json',scope)
        if collecting:
            collector=LateUsageCollector(output/'response-collection',expires_at=DEADLINE)
            save(output/'collection-policy.json',dict(scored_http_timeout_s=300,receiver_timeout_s=900,
                max_receivers=4,automatic_retry=False,late_result_applied=False,
                conservative_pending_cost=True,product_defaults_changed=False,approval_expires_at=DEADLINE))
        for provider in ('nebius','openai'):
            rates={m['model_id']:{**{k:m[k] for k in ('input_per_million','output_per_million','context_tokens')},
                'source':'https://api.tokenfactory.nebius.com/private/v1/models_info' if provider=='nebius' else 'https://developers.openai.com/api/docs/models/gpt-6-luna'}
                for m in models if m['provider']==provider}
            ledgers[provider]=(CollectingLedger if collecting else ComparisonLedger)(output/(provider+'.ledger.json'),approval=approval,rates=rates,
                limit_usd=remaining(carry[provider]),max_requests=sum(1 if j['role']=='observer' else 12 for j in jobs
                    if next(m for m in models if m['model_id']==j['model_id'])['provider']==provider))
        print(json.dumps(dict(status='FROZEN_PUBLIC_ROLE_SCREENING',models=len(all_models),planned=len(jobs),
            photo_rooms=len(cases),output_cap=40000)),flush=True)
        shared=continuation['shared'] if continuation else {};streaks={r:FailureStreak() for r in ('observer','planner')}
        if continuation:
            for prior in continuation['history']:
                if streaks[prior['role']].observe(prior):raise ValueError('ROLE_PRIOR_FIVE_MODEL_STOP')
            # The old unreported UNKNOWN cannot disappear at the cohort boundary.
            interrupted_prior=continuation['reference']['skipped_interrupted_job']
            if interrupted_prior:
                streaks[interrupted_prior['role']].observe(dict(**interrupted_prior,status='FAIL',actual_calls=1,
                    failure_code='PROVIDER_TIMEOUT',provider_error_code='REMOTE_UNKNOWN'))
        for job in jobs:
            if collector and collector.stop_reason():stop=collector.stop_reason();break
            if (expiry-datetime.now(timezone.utc)).total_seconds()<1800:
                stop='DEADLINE_ADMISSION_STOP';break
            if source_freeze(ROOT)!=frozen or any(sha(Path(p))!=h for p,h in originals.items()):
                stop='SOURCE_OR_GLOBAL_SETTINGS_CHANGED';break
            case=next(c for c in cases if c['case_id']==job['case_id']);model=next(m for m in models if m['model_id']==job['model_id'])
            if sha(Path(case['photo']))!=case['photo_sha256']:stop='PUBLIC_INPUT_CHANGED';break
            if continuation and any(sha(Path(r['path']))!=r['source_file_sha256'] for r in continuation['reference']['shared_observations'].values()):
                stop='SHARED_OBSERVATION_CHANGED';break
            reason='OUTPUT_CAP_EXCEEDS_MODEL_CONTEXT_INPUT_MARGIN' if model['context_tokens']<=40000 else None
            if job['role']=='planner' and job['case_id'] not in shared:reason='SHARED_OBSERVATION_UNAVAILABLE'
            if reason:
                row=dict(**job,status='NOT_RUN',not_run_reason=reason,actual_calls=0,room_group=case['room_group'])
            else:
                observation=shared.get(job['case_id']);obs_sha=canonical_sha(observation.to_dict()) if observation else None
                inputs=dict(photo_sha256=case['photo_sha256'],observation_sha256=obs_sha)
                row,interrupted=await bounded_role_case(output,job,run_case,output/job['case_id'],job['role'],model,job['repeat'],stores,ledgers[model['provider']],
                    observation,inputs,photo=Path(case['photo']),prompt=case['prompt'],output_cap=40000,
                    current_adapter=True,expires_at=DEADLINE,
                    **({'collection':collector} if collector else {}))
                if interrupted:
                    stop='HOST_REPORT_ABORTED';break
                row.update(job_id=job['job_id'],room_group=case['room_group'],input_case=case['case_id'])
                if job['role']=='observer' and model['model_id']=='gpt-6-luna' and job['repeat']==1 and row['status']=='PASS':
                    identity=row['case_id'];path=output/job['case_id']/'cases'/identity/'observation.json'
                    shared[job['case_id']]=ObservationArtifact.from_mapping(json.loads(path.read_text(encoding='utf-8')))
                    save(output/(job['case_id']+'-shared-observation.json'),dict(source_job_id=job['job_id'],
                        sha256=canonical_sha(shared[job['case_id']].to_dict()),source_file_sha256=sha(path),ground_truth=False))
            results.append(row);save(output/'progress'/f'{len(results):04d}.json',row)
            if row.get('terminal_stop'):stop=row['terminal_stop'];break
            if row.get('http_status')==402:stop='PROVIDER_PAYMENT_REQUIRED_STOP';break
            if row.get('failure_code') in ('BUDGET_EXHAUSTED','CAMPAIGN_BUDGET_EXCEEDED'):stop='BUDGET_ADMISSION_STOP';break
            if streaks[job['role']].observe(row):stop='FIVE_DISTINCT_MODELS_SAME_ROLE_ROOT_STOP';break
        if collector:
            save(output/'collection-at-trials-end.json',collector.snapshot())
            drained=await collector.drain()
            save(output/'collection-final.json',drained)
            if drained['fatal_gate']:stop=drained['fatal_gate']
        finances=limit_status(ledgers)
        audit=dict(source_unchanged=source_freeze(ROOT)==frozen,
            global_settings_unchanged=all(sha(Path(p))==h for p,h in originals.items()),
            input_photos_unchanged=all(sha(Path(c['photo']))==c['photo_sha256'] for c in cases),
            invoice_verified=False,raw_local_only=True,private_photo_used=False,robot_calls=0)
        reporting=final_accounting_rows(output,results,ledgers) if collector else results
        if collector:save(output/'accounting-results.json',reporting)
        table=aggregate(jobs,reporting,models)
        result=dict(schema_version='public-role-screening-result-1.0',status='STOPPED' if stop else 'COMPLETED',
            stop_reason=stop,planned=len(jobs),ended=len(results),not_run=sum(r['not_run'] for r in table),
            interrupted_job=interrupted,
            rows=table,financial=finances,total_exposure_usd={p:str(Decimal(carry[p])+Decimal(finances[p]['estimated_or_reserved_usd'])) for p in carry},
            audit=audit,full_app_isaac='NOT_RUN',photo_quality='NO_BLIND_HUMAN_LABELS_NO_FIDELITY_PASS',
            independent_rooms=len(cases),whole_demo_pass=False)
        save(output/'summary.json',result)
        lines=['# Public-input role screening','',f"Status: {result['status']} · stop: {stop} · planned {len(jobs)} · ended {len(results)}",'',
            'Role-only screening, not full App/Isaac or photo-fidelity acceptance. Planner inputs are identical fixed Luna observations, not human truth.', '',
            '|Role|Model|PASS|FAIL|NOT_RUN|HTTP|p50 s|p95 s|Estimated/held USD|','|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for r in table:
            lines.append('|'+ '|'.join(str(v) for v in (r['role'],r['model_id'],r['pass_count'],r['fail_count'],r['not_run'],r['http_requests'],r['http_time']['p50_s'],r['http_time']['p95_s'],r['estimated_or_reserved_usd']))+'|')
        with (output/'metrics-only.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
        print(json.dumps(dict(status=result['status'],stop_reason=stop,ended=len(results),planned=len(jobs),
            financial=finances,audit=audit)),flush=True)
    except Exception as error:
        if not (output/'scope.json').exists():
            save(output/'admission-failure.json',dict(status='ADMISSION_FAILED_BEFORE_INFERENCE',
                error_type=type(error).__name__,error=safe_text(str(error),limit=600),at=utc_now(),
                inference_calls=0,automatic_retry=False))
        raise
    finally:
        if collector:
            await collector.drain()
            for ledger in ledgers.values():ledger.close()
        owner.unlink()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--existing-nebius',required=True);parser.add_argument('--existing-openai',required=True)
    parser.add_argument('--continue-from',type=Path)
    parser.add_argument('--prior-audit',type=Path);parser.add_argument('--prior-audit-sha256')
    parser.add_argument('--acknowledge-held-attempt',action='append',default=[])
    parser.add_argument('--check-continuation-only',action='store_true',help='Local admission only; no metadata, credentials or inference.')
    parser.add_argument('--collect-late-usage',action='store_true',help='Explicitly approved benchmark-only scored timeout continuation with retained receivers/holds.')
    args=parser.parse_args()
    if args.check_continuation_only:
        cases=public_cases(json.loads(args.spec.read_text(encoding='utf-8')),args.spec.resolve())
        loaded=load_continuation(args.continue_from,args.prior_audit,args.prior_audit_sha256,
            args.acknowledge_held_attempt,cases,dict(nebius=args.existing_nebius,openai=args.existing_openai))
        print(json.dumps(dict(status='LOCAL_CONTINUATION_ADMISSION_PASS',remaining=len(loaded['jobs']),
            original_files=loaded['reference']['unchanged_original_files'],shared_rooms=len(loaded['shared']),
            skipped_started=loaded['reference']['skipped_started_jobs'],inference_calls=0)))
    else:asyncio.run(execute(args))

if __name__=='__main__':main()
