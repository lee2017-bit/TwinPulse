# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen manifest controller for the existing ordinary runner.

No inference on import, initialization or reporting. Financial approval is a
separate, expiring human grant, never inferred from dataset permissions. Unknown
child outcomes retain reservations. Legacy campaign files are not migrated.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.benchmark_protocol import canonical_sha, prepare, read_json, source_freeze
from scripts.benchmark_results import _money, same_root_model_streak

ROOT=Path(__file__).resolve().parents[1]
PROVIDERS=('nebius','openai')
MODELS={'observer':{'deepseek-ai/DeepSeek-V4.1-Flash','Qwen/Qwen3.8-27B','gpt-6-luna'},
        'planner':{'nvidia/Nemotron-3_5-Lightning','gpt-6-luna'}}


def utc(value):
    try:result=datetime.fromisoformat(value)
    except (ValueError,TypeError):raise ValueError('BENCHMARK_APPROVAL_TIME_INVALID') from None
    if result.tzinfo is None or result.utcoffset().total_seconds()!=0:
        raise ValueError('BENCHMARK_APPROVAL_REQUIRES_UTC')
    return result


def checked_authorization(value,prepared):
    fields={'schema_version','authorization_id','manifest_sha256','approved_at','expires_at',
            'human_approval','providers','request_cap','trial_usd','admission_reserve_s'}
    if type(value) is not dict or set(value)!=fields or value['schema_version']!='benchmark-authorization-1.0':
        raise ValueError('BENCHMARK_AUTHORIZATION_INVALID')
    from scripts.benchmark_protocol import _id
    _id(value['authorization_id'])
    if value['manifest_sha256']!=prepared['manifest_sha256']:
        raise ValueError('BENCHMARK_APPROVAL_MANIFEST_CHANGED')
    if type(value['human_approval']) is not str or not value['human_approval'].strip():
        raise ValueError('BENCHMARK_CURRENT_HUMAN_APPROVAL_REQUIRED')
    if utc(value['approved_at'])>=utc(value['expires_at']):raise ValueError('BENCHMARK_APPROVAL_INTERVAL_INVALID')
    # Explicitly frozen P2 acceptance uses the product's reduced 12-call cap.
    # Historical 24-call grants remain unchanged; other caps are not inferred.
    if type(value['request_cap']) is not int or value['request_cap'] not in (12,24):
        raise ValueError('BENCHMARK_REVIEWED_RESOURCE_POLICY_REQUIRED')
    import re
    if (not isinstance(value['trial_usd'],str) or not re.fullmatch(r'(?:0|1)\.[0-9]{2}',value['trial_usd'])
            or not 0<_money(value['trial_usd'])<=1):raise ValueError('BENCHMARK_TRIAL_BUDGET_INVALID')
    if type(value['admission_reserve_s']) is not int or value['admission_reserve_s']<1800:
        raise ValueError('BENCHMARK_ADMISSION_RESERVE_TOO_SHORT')
    needed={role['provider'] for c in prepared['configs'] for role in c['roles'].values()}
    if type(value['providers']) is not dict or set(value['providers'])!=needed:
        raise ValueError('BENCHMARK_PROVIDER_APPROVAL_INCOMPLETE')
    for provider,grant in value['providers'].items():
        if type(grant) is not dict or set(grant)!={'limit_usd','existing_exposure_usd','original_input','derived_render'}:
            raise ValueError('BENCHMARK_PROVIDER_GRANT_INVALID')
        if (_money(grant['existing_exposure_usd'])>_money(grant['limit_usd'])
                or grant['original_input'] is not True or grant['derived_render'] is not True):
            raise ValueError('BENCHMARK_PROVIDER_SCOPE_OR_EXPOSURE_INVALID')
    return deepcopy(value)


def role_supported(prepared,stage,role):
    catalog=prepared.get('model_catalog')
    if catalog and role['provider']=='nebius':
        from twinpulse_provider.model_contracts import model_supported
        return model_supported(catalog,stage,role['model'])
    return role['model'] in MODELS[stage] and role['provider']==('openai' if role['model']=='gpt-6-luna' else 'nebius')


def eligibility(prepared):
    issues=[]
    for config in prepared['configs']:
        roles=config['roles'];reason=None
        if roles['repair']!=roles['planner'] or roles['critic']!=roles['observer']:
            reason='INDEPENDENT_REPAIR_CRITIC_ADAPTER_NOT_IMPLEMENTED'
        for stage in MODELS:
            role=roles[stage]
            if not role_supported(prepared,stage,role):
                reason='MODEL_NOT_ELIGIBLE_IN_REVIEWED_ACTUAL_ADAPTER'
            catalog=prepared.get('model_catalog')
            if catalog and role['provider']=='nebius':
                from scripts.benchmark_protocol import frozen_stage_output_caps
                model=next((r for r in catalog['models'] if r['model_id']==role['model']),None)
                if model and frozen_stage_output_caps(config)[stage]>=model['context_tokens']:
                    reason='OUTPUT_CAP_EXCEEDS_MODEL_CONTEXT_INPUT_MARGIN'
        if reason:issues.append(dict(config_id=config['config_id'],reason=reason))
    for case,packet in prepared['packets'].items():
        if packet['external_transmission_allowed'] is not True:
            issues.append(dict(case_id=case,reason='DATA_TRANSMISSION_NOT_APPROVED'))
    return issues


def eligibility_matrix(prepared):
    """All planned jobs remain visible; contract support is not model quality.

    No catalog/network request. A locally supported adapter is NOT proof that
    today's account/model endpoint is available or a paid dispatch is approved.
    """
    if not prepared.get('packets') or any(set(c.get('roles',{}))!={'observer','planner','repair','critic'}
                                        for c in prepared['configs']):
        return [dict(job_id=j['job_id'],status='NOT_EVALUATED',reasons=['INCOMPLETE_PREPARED_CONTRACT'])
                for j in prepared['jobs']]
    issues=eligibility(prepared)
    return [dict(job_id=j['job_id'],status='INELIGIBLE' if reasons else 'REVIEWED_ADAPTER_SUPPORTED',reasons=reasons)
            for j in prepared['jobs'] for reasons in [sorted({row['reason'] for row in issues
                if row.get('config_id')==j['config_id'] or row.get('case_id')==j['case_id']})]]


def initialize(prepared,authorization):
    grant=checked_authorization(authorization,prepared)
    return dict(schema_version='manifest-benchmark-campaign-1.0',
        prepared_sha256=canonical_sha(prepared),authorization_sha256=canonical_sha(grant),
        prepared=deepcopy(prepared),authorization=grant,status='PREPARED_NOT_EXECUTED',
        runs=[],failure_probes=[],blocked_providers=[],automatic_new_approval=False,
        physical_authority=False)


def validate(state,prepared,authorization):
    grant=checked_authorization(authorization,prepared)
    if (state.get('schema_version')!='manifest-benchmark-campaign-1.0'
            or state.get('prepared_sha256')!=canonical_sha(prepared)
            or state.get('authorization_sha256')!=canonical_sha(grant)
            or state.get('prepared')!=prepared or state.get('authorization')!=grant
            or state.get('physical_authority') is not False
            or state.get('automatic_new_approval') is not False):
        raise ValueError('BENCHMARK_RESUME_COHORT_OR_APPROVAL_CHANGED')
    scheduled={j['job_id']:j for j in prepared['jobs']};seen=set()
    for index,run in enumerate(state['runs']):
        if run['job_id'] in seen or run['job_id'] not in scheduled or prepared['jobs'][index]['job_id']!=run['job_id']:
            raise ValueError('BENCHMARK_RUN_ORDER_OR_ID_CHANGED')
        seen.add(run['job_id'])
        expected=reservation(state,scheduled[run['job_id']])
        if run.get('reserved_usd')!=expected:raise ValueError('BENCHMARK_RESERVATION_CHANGED')
        if type(run.get('settled')) is not bool:raise ValueError('BENCHMARK_SETTLEMENT_INVALID')
        if run['settled']:
            summary=run.get('summary') or {}
            if summary.get('audit_status')!='PASS' or summary.get('unknown_requests')!=0 or summary.get('pending_locks')!=0:
                raise ValueError('BENCHMARK_SETTLEMENT_REQUIRES_AUDIT')
            for provider in PROVIDERS:
                cost=_money(summary['cost_by_provider'].get(provider,'0'))
                held=_money(summary['held_by_provider'].get(provider,'0'))
                if cost+held>_money(expected[provider]):raise ValueError('BENCHMARK_TRIAL_EXPOSURE_EXCEEDED')
    probes=[p for r in state['runs'] if r['settled'] for p in run_probes(r,prepared)]
    blocked=sorted({row['provider'] for r in state['runs'] if r['settled']
                    for row in r['summary'].get('rows',[]) if row.get('http_status')==402})
    if state['failure_probes']!=probes or state['blocked_providers']!=blocked:
        raise ValueError('BENCHMARK_STOP_EVIDENCE_CHANGED')
    return state


def reservation(state,job):
    config=next(c for c in state['prepared']['configs'] if c['config_id']==job['config_id'])
    used={r['provider'] for r in config['roles'].values()}
    # The child uses a combined per-trial cap. Reserve its full possible charge
    # at EACH involved provider; never shrink a later model's trial policy.
    return {p:state['authorization']['trial_usd'] if p in used else '0' for p in PROVIDERS}


def run_probes(run,prepared):
    """Keep successes/unknowns in role history: nonconsecutive FAILs cannot stop.

    Only a schema-stage-bound, audited actual dispatch can attribute a failure.
    Other role outcomes reset their streak, never guess the same host root.
    """
    job=next(j for j in prepared['jobs'] if j['job_id']==run['job_id'])
    roles=next(c['roles'] for c in prepared['configs'] if c['config_id']==job['config_id'])
    summary=run['summary'];failure=summary.get('failure_probe');probes=[]
    stages=dict(observer={'twinpulse_image_observation'},planner={'twinpulse_semantic_structure','twinpulse_semantic_batch'},
                repair={'twinpulse_semantic_patch'},critic={'twinpulse_render_review'})
    if failure and failure.get('role') not in stages:raise ValueError('BENCHMARK_FAILURE_ROLE_BINDING_CHANGED')
    for role,identity in roles.items():
        dispatched=any(r.get('model_id')==identity['model'] and r.get('provider')==identity['provider']
            and r.get('stage') in stages[role] for r in summary.get('rows',[]))
        probe=dict(role=role,provider=identity['provider'],model_id=identity['model'],
                   actual_dispatched=dispatched,status='PASS' if summary['status']=='PASS' and dispatched else 'UNKNOWN',root_code=None)
        if failure and failure['role']==role:
            if ((failure.get('provider'),failure.get('model_id'))!=(identity['provider'],identity['model'])
                    or failure.get('actual_dispatched') is not dispatched or failure.get('status')!='FAIL'
                    or type(failure.get('root_code')) is not str or not failure['root_code']):
                raise ValueError('BENCHMARK_FAILURE_ROLE_BINDING_CHANGED')
            probe=deepcopy(failure)
        probes.append(probe)
    return probes


def exposure(state):
    totals={p:_money(state['authorization']['providers'].get(p,{}).get('existing_exposure_usd','0')) for p in PROVIDERS}
    for run in state['runs']:
        summary=run.get('summary') or {}
        for p in PROVIDERS:
            totals[p]+=(_money(summary['cost_by_provider'].get(p,'0'))+
                _money(summary['held_by_provider'].get(p,'0')) if run['settled'] else _money(run['reserved_usd'][p]))
    return totals


def output_limit_reached(summary):
    """Stop on audited wire length OR the product's typed truncation failure.

    A rejected structured response can retain usage but lose finish_reason in
    the error record. Its typed terminal code still mandates the stop. Token
    count alone is not proof of truncation; a complete response at the cap is
    not silently reclassified. This never modifies raw evidence or accounting.
    """
    return (summary.get('failure_code')=='PROVIDER_OUTPUT_TRUNCATED'
        or any(row.get('finish_reason')=='length' for row in summary.get('rows',[])))


def admission(state,now):
    grant=state['authorization'];jobs=state['prepared']['jobs']
    if utc(grant['approved_at'])>now:return dict(allowed=False,code='APPROVAL_NOT_YET_VALID')
    if (utc(grant['expires_at'])-now).total_seconds()<grant['admission_reserve_s']:
        return dict(allowed=False,code='APPROVAL_EXPIRED_OR_ADMISSION_RESERVE')
    if state['prepared'].get('model_catalog'):
        from twinpulse_provider.model_contracts import checked_catalog
        try:checked_catalog(state['prepared']['model_catalog'],now=now)
        except ValueError:return dict(allowed=False,code='MODEL_CATALOG_EXPIRED_OR_INVALID')
    issues=eligibility(state['prepared'])
    if issues:return dict(allowed=False,code='ACTUAL_ADAPTER_INELIGIBLE',issues=issues)
    if any(not r['settled'] for r in state['runs']):return dict(allowed=False,code='UNSETTLED_PRIOR_RUN_RESERVATION_HELD')
    for role in ('observer','planner','repair','critic'):
        streak=same_root_model_streak(state['failure_probes'],role)
        if streak['stop']:return dict(allowed=False,code='FIVE_DISTINCT_MODELS_SAME_ROOT_STOP',detail=streak)
    if any(output_limit_reached(run.get('summary') or {}) for run in state['runs']):
        return dict(allowed=False,code='OUTPUT_LIMIT_STOP')
    if len(state['runs'])==len(jobs):return dict(allowed=False,code='CAMPAIGN_EXECUTION_COMPLETE_QUALITY_MAY_BE_PENDING')
    job=jobs[len(state['runs'])];reserved=reservation(state,job)
    if state['prepared'].get('model_catalog'):
        # Same conservative minimum as the ordinary App's approval card.
        # Fail BEFORE a child/UI/financial reservation, never lower the guard
        # or spend the user's full trial merely to discover a disabled button.
        from twinpulse_app.generation_approval import (REVIEWED_PRICES,
            full_context_reserve,minimum_initial_reserve)
        from twinpulse_provider.model_contracts import catalog_prices
        from scripts.benchmark_protocol import frozen_stage_output_caps
        config=next(c for c in state['prepared']['configs'] if c['config_id']==job['config_id'])
        prices={**REVIEWED_PRICES,**catalog_prices(state['prepared']['model_catalog'])}
        caps=frozen_stage_output_caps(config)
        stages=('observer','planner') if state['prepared']['packets'][job['case_id']].get('photo') else ('planner',)
        amounts=[full_context_reserve(prices[config['roles'][s]['model']],caps[s]) for s in stages]
        minimum=minimum_initial_reserve(amounts)
        if minimum>_money(grant['trial_usd']):
            return dict(allowed=False,code='INITIAL_RESERVATION_EXCEEDS_TRIAL_CAP',
                minimum_initial_reserve_usd=str(minimum),trial_usd=grant['trial_usd'])
    if state['prepared'].get('evaluation_readiness') and job['split']=='holdout':
        labels=next(r for r in state['prepared']['evaluation_readiness']['cases'] if r['case_id']==job['case_id'])
        if labels['status']!='LABELS_REVIEWED_ATTESTED':
            return dict(allowed=False,code='HOLDOUT_LABELS_NOT_REVIEWED_BEFORE_OUTPUTS')
        if utc(labels['reviewed_at'])>now:
            return dict(allowed=False,code='HOLDOUT_LABEL_REVIEW_NOT_PRE_RUN')
    if any(_money(reserved[p]) and p in state['blocked_providers'] for p in PROVIDERS):
        return dict(allowed=False,code='PROVIDER_PAYMENT_REQUIRED_STOP')
    # Before beginning a paired block, ensure every config can receive its full
    # frozen trial allowance. Mid-block settlement must still respect actual cap.
    pending=[j for j in jobs[len(state['runs']):] if j['block']==job['block']]
    totals=exposure(state)
    for p in PROVIDERS:
        needed=sum((_money(reservation(state,j)[p]) for j in pending),Decimal(0))
        available=_money(grant['providers'].get(p,{}).get('limit_usd','0'))-totals[p]
        if needed>available:return dict(allowed=False,code='PAIRED_BLOCK_BUDGET_INSUFFICIENT',provider=p)
    return dict(allowed=True,job=deepcopy(job),reserved_usd=reserved)


def reserve_next(state,now):
    gate=admission(state,now)
    if not gate['allowed']:raise ValueError(gate['code'])
    result=deepcopy(state);result['status']='RUNNING'
    result['runs'].append(dict(job_id=gate['job']['job_id'],reserved_usd=gate['reserved_usd'],
        started_at=now.isoformat(),settled=False,status='RESERVED'))
    return result


def settle(state,job_id,summary):
    result=deepcopy(state);run=next(r for r in result['runs'] if r['job_id']==job_id)
    if run['settled']:raise ValueError('BENCHMARK_ALREADY_SETTLED')
    if summary.get('audit_status')!='PASS' or summary.get('unknown_requests')!=0 or summary.get('pending_locks')!=0:
        raise ValueError('BENCHMARK_UNKNOWN_OUTCOME_RESERVATION_HELD')
    for p in PROVIDERS:
        if (_money(summary['cost_by_provider'].get(p,'0'))+_money(summary['held_by_provider'].get(p,'0'))
                >_money(run['reserved_usd'][p])):raise ValueError('BENCHMARK_TRIAL_EXPOSURE_EXCEEDED')
    run.update(settled=True,status=summary['status'],summary=deepcopy(summary))
    result['blocked_providers']=sorted(set(result['blocked_providers'])|
        {r['provider'] for r in summary.get('rows',[]) if r.get('http_status')==402})
    # Only explicit role attribution is eligible for this stop rule. A final
    # host failure must not be guessed to be a failed observer/critic model.
    result['failure_probes'].extend(run_probes(run,result['prepared']))
    if len(result['runs'])==len(result['prepared']['jobs']):
        result['status']='EXECUTION_COMPLETE_QUALITY_MAY_BE_PENDING'
    return result


def attributed_summary(summary,prepared,job):
    result=deepcopy(summary)
    if result['failure_origin']=='semantic_candidate_or_local_geometry' and result['root_failure_codes']:
        identity=next(c['roles']['planner'] for c in prepared['configs'] if c['config_id']==job['config_id'])
        dispatched=any(r['model_id']==identity['model'] and r.get('provider')==identity['provider']
            and r.get('stage') in ('twinpulse_semantic_structure','twinpulse_semantic_batch') for r in result['rows'])
        result['failure_probe']=dict(role='planner',provider=identity['provider'],model_id=identity['model'],
            actual_dispatched=dispatched,status='FAIL',root_code='|'.join(result['root_failure_codes']))
    return result


def child_command(state,job,directory,manifest_path):
    config=next(c for c in state['prepared']['configs'] if c['config_id']==job['config_id'])
    grant=state['authorization'];packet=state['prepared']['packets'][job['case_id']]
    approval=(grant['human_approval']+'; authorization '+grant['authorization_id']+
        '; manifest '+state['prepared']['manifest_sha256']+'; job '+job['job_id']+
        '; expires '+grant['expires_at']+'; input '+canonical_sha(packet))
    return [sys.executable,str(ROOT/'scripts/run_ordinary_staged_live_ten.py'),str(directory/job['job_id']),
        '--benchmark-manifest',str(manifest_path),'--case-id',job['case_id'],'--config-id',job['config_id'],
        '--recommended-nebius','--benchmark-profile','--request-cap',str(grant['request_cap']),
        '--cost-limit',grant['trial_usd'],'--observer-model',config['roles']['observer']['model'],
        '--planner-model',config['roles']['planner']['model'],'--approval-text',approval]


def write_atomic(path,value,*,create=False):
    path=Path(path)
    if path.is_symlink():raise ValueError('BENCHMARK_LINKED_OUTPUT')
    if create:
        with path.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        return
    temp=path.with_name(path.name+'.new')
    with temp.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)


def manifest_main(args):
    prepared=prepare(args.manifest);authorization=read_json(args.authorization)
    directory=args.directory.resolve();path=directory/'manifest-campaign.json'
    if directory.is_symlink():raise ValueError('BENCHMARK_LINKED_OUTPUT')
    if args.initialize:
        directory.mkdir(parents=True,exist_ok=True)
        write_atomic(path,initialize(prepared,authorization),create=True)
    state=validate(read_json(path),prepared,authorization)
    if args.reconcile:
        # After an interrupted controller, audit an existing child only. Never
        # re-dispatch it, reset its cap, infer zero billing or erase a failure.
        lock=directory/'manifest-dispatch-lock.json'
        with lock.open('x',encoding='utf-8') as stream:json.dump(dict(pid=os.getpid()),stream)
        try:
            from scripts.run_model_combination_benchmark import summarize_run
            for run in state['runs']:
                if not run['settled']:
                    job=next(j for j in prepared['jobs'] if j['job_id']==run['job_id'])
                    state=settle(state,run['job_id'],attributed_summary(summarize_run(directory/run['job_id']),prepared,job))
            validate(state,prepared,authorization);write_atomic(path,state)
        finally:lock.unlink()
    now=datetime.now(timezone.utc);gate=admission(state,now)
    if not args.run_next:
        print(json.dumps(dict(status=state['status'],admission=gate,
            settled=sum(r['settled'] for r in state['runs']),planned=len(prepared['jobs']),
            exposure_usd={p:str(v) for p,v in exposure(state).items()},HTTP=0)));return
    # Refuse a partial/changed source freeze BEFORE reserving or starting child.
    actual_source=source_freeze(ROOT)
    # Full source inventory is mandatory; evaluator rubric/label hashes may be
    # additional frozen inputs. prepare() separately verifies EVERY freeze file.
    if any(prepared['freeze'].get(p)!=digest for p,digest in actual_source.items()):
        raise ValueError('BENCHMARK_FULL_SOURCE_FREEZE_CHANGED')
    from scripts.benchmark_environment import verify_environment
    verify_environment(prepared,ROOT)
    lock=directory/'manifest-dispatch-lock.json'
    with lock.open('x',encoding='utf-8') as stream:json.dump(dict(pid=os.getpid()),stream)
    try:
        current=prepare(args.manifest)
        verify_environment(current,ROOT)
        state=validate(read_json(path),current,read_json(args.authorization))
        state=reserve_next(state,datetime.now(timezone.utc));write_atomic(path,state)
        job=prepared['jobs'][len(state['runs'])-1]
        command=child_command(state,job,directory,args.manifest.resolve())
        with (directory/(job['job_id']+'.log')).open('x',encoding='utf-8') as stream:
            process=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                env={**os.environ,'TWINPULSE_BENCHMARK_EXPIRES_AT':state['authorization']['expires_at']},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        state['runs'][-1]['runner_returncode']=process.returncode
        try:
            from scripts.run_model_combination_benchmark import summarize_run
            summary=attributed_summary(summarize_run(directory/job['job_id']),prepared,job)
            state=settle(state,job['job_id'],summary)
        except (ValueError,OSError,KeyError) as error:
            state['status']='STOPPED_UNSETTLED';state['runs'][-1]['status']='UNKNOWN'
            state['runs'][-1]['audit_error_type']=type(error).__name__
        # Child must not have mutated any approved input, labels, code or policy.
        validate(state,prepare(args.manifest),read_json(args.authorization))
        verify_environment(prepared,ROOT)
        write_atomic(path,state)
        print(json.dumps(dict(status=state['status'],job_status=state['runs'][-1]['status'],
            next_admission=admission(state,datetime.now(timezone.utc)))))
    finally:lock.unlink()
