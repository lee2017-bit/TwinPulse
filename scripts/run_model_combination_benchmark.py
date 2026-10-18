# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Serialized, current-authorized full App benchmark; reports send no inference.

The campaign limit includes all current grants, not just successful runs. An
unfinished run/unknown settlement blocks a new grant. No historical ledger is
borrowed, no fixture is substituted, no robot or public upload is performed.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal,ROUND_DOWN
import hashlib
import json
import math
import os
import re
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_ordinary_staged_live_ten import audit_ordinary_run
from scripts.benchmark_campaign import output_limit_reached

PAIRS={
    'flash-lightning':('deepseek-ai/DeepSeek-V4.1-Flash','nvidia/Nemotron-3_5-Lightning'),
    'qwen-lightning':('Qwen/Qwen3.8-27B','nvidia/Nemotron-3_5-Lightning'),
    'luna-lightning':('gpt-6-luna','nvidia/Nemotron-3_5-Lightning'),
    'flash-luna':('deepseek-ai/DeepSeek-V4.1-Flash','gpt-6-luna'),
    'luna-luna':('gpt-6-luna','gpt-6-luna'),
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    temporary=path.with_suffix(path.suffix+'.new')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def provider(model):
    return 'openai' if model.startswith('gpt-') else 'nebius'


def exposure(campaign):
    """Worst-case limits for unfinished grants, actual charges after audit."""
    totals={name:Decimal(0) for name in ('nebius','openai')}
    for row in campaign['runs']:
        costs=row.get('cost_by_provider') if row.get('audit_status')=='PASS' else row['reserved_usd']
        for name in totals:
            totals[name]+=Decimal(costs.get(name,'0'))
            if row.get('audit_status')=='PASS':totals[name]+=Decimal(row.get('held_by_provider',{}).get(name,'0'))
    for name,total in totals.items():
        if total>Decimal(campaign['limits_usd'][name]):
            raise ValueError('CAMPAIGN_BUDGET_EXCEEDED:'+name)
    return totals


def wilson(passed,total):
    if not total:return None
    z=1.959963984540054;p=passed/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    margin=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [round(max(0,center-margin),6),round(min(1,center+margin),6)]


def percentile(values,probability):
    """Linear interpolation, not a stable tail estimate for this small sample."""
    if not values:return None
    values=sorted(values);index=(len(values)-1)*probability
    lower=math.floor(index);upper=math.ceil(index)
    return round(values[lower]+(values[upper]-values[lower])*(index-lower),6)


def distribution(values):
    return dict(samples=len(values),p50_s=percentile(values,.5),p95_s=percentile(values,.95))


def routing(run):
    rows=run.get('rows',[])
    observer=run.get('observer_model') or next((r['model_id'] for r in rows if r.get('stage')=='twinpulse_image_observation'),None)
    planner=run.get('planner_model') or next((r['model_id'] for r in rows if r.get('stage')=='twinpulse_semantic_structure'),None)
    return observer,planner


def repeated_failure_stop(campaign):
    """Five distinct consecutive failed configurations with the same root."""
    root=None;configurations=set()
    for run in reversed(campaign['runs']):
        if run.get('status')=='PREFLIGHT_FAIL':continue
        if run.get('audit_status')!='PASS' or run.get('status')!='FAIL':break
        codes=tuple(sorted(run.get('root_failure_codes') or [run.get('failure_code')]))
        if root is not None and codes!=root:break
        root=codes;configurations.add(routing(run))
        if len(configurations)>=5:return True
    return False


def blocked_providers(campaign):
    return {row['provider'] for run in campaign['runs'] for row in run.get('rows',[])
            if row.get('http_status')==402}


def simulation_failure_codes(browser):
    """Only typed terminal SIM codes, never private message text or coordinates."""
    messages=(browser.get('conversation') or {}).get('messages',[])
    for message in reversed(messages):
        if message.get('role')!='assistant' or message.get('status')!='failed':continue
        match=re.match(r'^(SIM_[A-Z0-9_]+)(?:\s|:|$)',message.get('content',''))
        return [match.group(1)] if match else []
    return []


def profile_snapshot(detail):
    """Rank only complete, validated owner-thread profiles; retain exclusions.

    Legacy rows are not retroactively calibrated. Raw values stay in their
    original execution record, including anomalous values and failed spans.
    """
    events = [e for e in detail.get('events', []) if e.get('type') == 'profile_row']
    invalid = set()
    for event in events:
        row = event.get('metadata', {})
        self_s, cumulative = row.get('self_s'), row.get('cumulative_s')
        if (type(self_s) not in (int, float) or type(cumulative) not in (int, float)
                or not math.isfinite(self_s) or not math.isfinite(cumulative)
                or not 0 <= self_s <= cumulative + 1e-6 or row.get('profile_valid') is False
                or type(row.get('calls')) is not int or row['calls'] < 0):
            invalid.add(event.get('span_id'))
    profiles = defaultdict(lambda: dict(calls=0, self_s=0.0, cumulative_s=0.0))
    excluded = 0
    for event in events:
        row = event.get('metadata', {})
        if (detail.get('events_truncated') or (detail.get('health') or {}).get('diagnostics_degraded')
                or event.get('span_id') in invalid
                or row.get('profile_valid') is not True
                or row.get('profiler_kind') != 'thread_filtered_cprofile'
                or row.get('profile_id') != event.get('span_id')
                or row.get('timer_basis') not in ('thread_cpu', 'wall')
                or type(row.get('calls')) is not int or row['calls'] < 0):
            excluded += 1
            continue
        key = (Path(row.get('source_file', 'unknown')).name, row.get('function', 'unknown'),
               row['timer_basis'], row.get('source_line'))
        values = profiles[key]
        for field in ('calls', 'self_s', 'cumulative_s'):
            values[field] += row[field]
    ranked = [dict(source_file=key[0], function=key[1], timer_basis=key[2], source_line=key[3], **values)
              for key, values in profiles.items()]
    ranked.sort(key=lambda row: row['self_s'], reverse=True)
    return dict(rows=ranked[:8], excluded_rows=excluded, invalid_profiles=len(invalid),
        status='PARTIAL_UNRANKED' if excluded else 'VALID' if events else 'NOT_MEASURED')


def ready_storage_bound(checkpoint,draft,*,photo):
    """Photos require current render review; text has no source-photo review.

    Both still require the exact persisted final plan. Text cannot manufacture
    observed entities, a source-photo critic or human quality acceptance.
    """
    return bool(draft and checkpoint.get('plan_sha256')==draft.get('plan_sha256')
        and (not photo or checkpoint.get('render_history')))


def summarize_run(directory):
    audit=audit_ordinary_run(directory)
    result=read(directory/'run-1/result.json');browser=result.get('browser',{})
    evidence=directory/'run-1/runtime/provider-evidence'
    checkpoint_paths=list((evidence/'generation-store/checkpoint').glob('*.json'))
    checkpoints=[read(path)['payload'] for path in checkpoint_paths]
    if len(checkpoints)>1:raise ValueError('AMBIGUOUS_CHECKPOINT')
    checkpoint=checkpoints[0] if checkpoints else {}
    costs={name:Decimal(0) for name in ('nebius','openai')}
    held={name:Decimal(0) for name in ('nebius','openai')}
    rows=[]
    for row in audit['rows']:
        costs[provider(row['model_id'])]+=Decimal(row['estimated_usd'])
        held[provider(row['model_id'])]+=Decimal(row.get('held_without_usage_usd','0'))
        dispatch=read(evidence/'dispatches'/(row['attempt_id']+'.json'))
        body=json.loads(dispatch['request_redacted'])
        stage=body.get('response_format',{}).get('json_schema',{}).get('name','unknown')
        rows.append({**row,'stage':stage,'provider':provider(row['model_id'])})
    conversation=browser.get('conversation',{}) or {}
    generation=conversation.get('generation',{}) or {}
    draft=browser.get('workflow',{}).get('site_draft') or {}
    history=checkpoint.get('render_history',[])
    ready=checkpoint.get('state')=='APPROXIMATE_TWIN_READY'
    generation_completed=generation.get('state')=='completed'
    photo=result.get('case')!='text'
    if ready and generation_completed and not ready_storage_bound(checkpoint,draft,photo=photo):
        raise ValueError('READY_FINAL_RENDER_OR_STORAGE_UNBOUND')
    pipeline_pass=(result['status']=='PASS' and browser.get('status')=='PASS' and
          ready and generation_completed and result.get('render_review_closed_backend_reopen',{}).get('status')=='PASS')
    diagnostic=None
    if (directory/'benchmark-case.json').exists():
        packet=read(directory/'benchmark-case.json')
        if packet['goal']['expected']!='arrival' and pipeline_pass:
            from scripts.benchmark_diagnostic import validate_diagnostic
            diagnostic=validate_diagnostic(packet,browser.get('diagnostic_goal'))
    full=pipeline_pass and diagnostic is None
    accepted=full or bool(pipeline_pass and diagnostic)
    if result['status']=='PASS' and not accepted:raise ValueError('FALSE_FULL_PASS')
    contract=(checkpoint.get('working_branch') or {}).get('diagnosis') or checkpoint.get('best_diagnosis') or {}
    # Root diagnostics live under different stages. Keep only codes here, not
    # private object descriptions, coordinates or raw model output.
    def issue_codes(value):
        found=set()
        if isinstance(value,dict):
            for key,child in value.items():
                if key=='issues' and isinstance(child,list):
                    found.update(item.get('code') for item in child if isinstance(item,dict) and item.get('code'))
                elif key in ('contract_report','geometry_report','geometry','report','validation','local_revalidation','rollback_revalidation','progress','diagnostics','last_report','diagnosis'):
                    found.update(issue_codes(child))
        return found
    root_codes=sorted(issue_codes(contract))
    if not root_codes:root_codes=sorted(issue_codes(checkpoint.get('quality_review') or {}))
    sim_codes=simulation_failure_codes(browser) if generation_completed and not accepted else []
    if sim_codes:root_codes=sorted(set(root_codes+sim_codes))
    patch_kinds=defaultdict(int)
    for patch in checkpoint.get('patches',[]):patch_kinds[patch.get('repair_kind','unknown')]+=1
    rejected=[row for row in rows if row.get('status')=='rejected']
    failure_origin=(None if accepted else 'provider_billing' if any(r.get('http_status')==402 for r in rejected) else
                    'app_provider_contract_or_transport' if rejected else
                    'simulation_navigation' if sim_codes else
                    'semantic_candidate_or_local_geometry' if root_codes else 'harness_or_engine')
    detail=browser.get('diagnostics',{}).get('detail',{})
    profile_metrics=profile_snapshot(detail)
    observer_model=next((r['model_id'] for r in rows if r['stage']=='twinpulse_image_observation'),None)
    planner_model=next((r['model_id'] for r in rows if r['stage']=='twinpulse_semantic_structure'),None)
    observation=checkpoint.get('observation') or {}
    inventory=(checkpoint.get('draft') or {}).get('inventory') or {}
    inventory_items=inventory.get('items',[]) if isinstance(inventory,dict) else inventory
    return dict(audit_status='PASS',status='PASS' if accepted else 'FAIL',
        diagnostic_goal_acceptance=diagnostic,
        observer_model=observer_model,planner_model=planner_model,
        generation_ready=ready,generation_completed=generation_completed,
        final_render_status=history[-1]['status'] if history else 'NOT_APPLICABLE_TEXT' if not photo and ready else 'NOT_REACHED',
        render_reviews=len(history),repair_requests=checkpoint.get('budget',{}).get('repairs',0),
        generation_active_s=checkpoint.get('budget',{}).get('cumulative_active_s'),
        cost_by_provider={name:str(value) for name,value in costs.items()},
        held_by_provider={name:str(value) for name,value in held.items()},
        actual_requests=len(rows),rows=rows,unknown_requests=0,pending_locks=0,
        model_http_wall_s=round(sum(row['elapsed_s'] for row in rows),6),
        root_failure_codes=[] if accepted else root_codes,
        repair_kinds=dict(patch_kinds),
        patch_stage_verdicts=[{key:patch.get(key) for key in ('repair_kind','validation','geometry_validation','quality_validation')}
                             for patch in checkpoint.get('patches',[])],
        failure_origin=failure_origin,
        rejected_http_statuses=[row.get('http_status') for row in rejected],
        completed_stages=checkpoint.get('completed_stages',[]),
        observed_entities=len(observation.get('entities',[])),
        inventory_items=len(inventory_items),saved_items=len(draft.get('room_inventory',{}).get('items',[])),
        geometry_checks_complete=(checkpoint.get('local_revalidation') or contract).get('checks_complete'),
        arrival_error_m=(browser.get('arrival') or {}).get('distance_to_goal_m'),
        semantic_goal_distance_m=(browser.get('semantic_arrival') or {}).get('distance_to_goal_m'),
        navigation_evidence_status='PASS' if full and browser.get('semantic_goal_evidence') else 'NOT_EVALUATED',
        arrival_sim_time_s=(browser.get('arrival') or {}).get('sim_time_s'),
        stopped_runtime_state=(browser.get('stop') or {}).get('runtime_state'),
        cpu_profile_top_self=profile_metrics['rows'],profile_events_truncated=detail.get('events_truncated'),
        cpu_profile_status=profile_metrics['status'],cpu_profile_excluded_rows=profile_metrics['excluded_rows'],
        cpu_profile_invalid_profiles=profile_metrics['invalid_profiles'],
        generation_span_s=next((span.get('duration_s') for span in detail.get('spans',[]) if span.get('stage')=='scene_generation'),None),
        failure_code=(sim_codes[0] if sim_codes else checkpoint.get('error_code') or
                      (generation.get('error',{}).get('code') if isinstance(generation.get('error'),dict) else None)),
        harness_error=result.get('error'),originals_unchanged=audit['originals_unchanged'],
        inference_source_sha256=hashlib.sha256(json.dumps(result['inference_source_at_start'],sort_keys=True).encode()).hexdigest(),
        model_response_quality='limited_current_render_review_not_measurement',invoice_verified=False,
        actual_sim_full=full,robot_calls=0)


def collect(directory,campaign):
    for row in campaign['runs']:
        target=directory/row['id']
        if (target/'summary.json').exists() and (row.get('audit_status')!='PASS' or row.get('metrics_revision')!='1.7'):
            row.update(summarize_run(target))
            row['metrics_revision']='1.7'
        elif (row.get('audit_status')!='PASS' and row.get('runner_returncode') not in (None,0)
                and not target.exists() and (directory/(row['id']+'.log')).is_file()):
            # The child creates its exclusive output before any inference. No
            # directory + recorded nonzero exit proves this preflight sent none.
            row.update(audit_status='PASS',status='PREFLIGHT_FAIL',actual_requests=0,rows=[],
                cost_by_provider={'nebius':'0','openai':'0'},unknown_requests=0,pending_locks=0,
                generation_ready=False,generation_completed=False,actual_sim_full=False,
                render_reviews=0,repair_requests=0,failure_code='TEST_PREFLIGHT_FAILURE',
                inference_source_sha256='NO_INFERENCE_PREFLIGHT',physical_authority=False)
    exposure(campaign)
    return campaign


def public_summary(campaign):
    """Whitelisted metrics only: no image, geometry, user text or local paths."""
    groups=defaultdict(list)
    for run in campaign['runs']:
        if run.get('audit_status')!='PASS' or run.get('actual_requests',0)==0:continue
        groups[(routing(run),run['inference_source_sha256'])].append(run)
    result=[]
    for ((observer,planner),version),runs in groups.items():
        successes=sum(run['status']=='PASS' for run in runs)
        latencies=[row['elapsed_s'] for run in runs for row in run['rows']]
        stages=defaultdict(list)
        for run in runs:
            for row in run['rows']:stages[row.get('stage','unknown')].append(row)
        result.append(dict(observer_model=observer,planner_model=planner,code_sha256=version,samples=len(runs),
            full_journey_pass=successes,full_journey_fail=len(runs)-successes,
            full_journey_success_rate=successes/len(runs),wilson_95_interval=wilson(successes,len(runs)),
            generation_ready=sum(run['generation_ready'] for run in runs),
            requests=sum(run['actual_requests'] for run in runs),
            actual_sim_pass=sum(run['actual_sim_full'] for run in runs),
            repair_requests=sum(run['repair_requests'] for run in runs),
            repair_kinds={kind:sum(run.get('repair_kinds',{}).get(kind,0) for run in runs)
                          for kind in sorted(set(kind for run in runs for kind in run.get('repair_kinds',{})))},
            natural_repair_recovery_samples=sum(run['repair_requests']>0 and run['status']=='PASS' for run in runs),
            render_reviews=sum(run['render_reviews'] for run in runs),
            request_latency_median_s=statistics.median(latencies) if latencies else None,
            request_latency=distribution(latencies),
            end_to_end_wall=distribution([run['end_to_end_wall_s'] for run in runs if 'end_to_end_wall_s' in run]),
            generation_active=distribution([run['generation_active_s'] for run in runs if run.get('generation_active_s') is not None]),
            model_http_wall=distribution([run['model_http_wall_s'] for run in runs if 'model_http_wall_s' in run]),
            stages={stage:dict(requests=len(rows),response_complete=sum(r['finish_reason']=='stop' for r in rows),
                samples_reached=sum(any(r.get('stage')==stage for r in run['rows']) for run in runs),
                request_latency=distribution([r['elapsed_s'] for r in rows])) for stage,rows in stages.items()},
            current_render_verdicts={verdict:sum(run['final_render_status']==verdict for run in runs)
                for verdict in sorted(set(run['final_render_status'] for run in runs))},
            saved_item_counts=[run.get('saved_items') for run in runs],
            observed_entity_counts=[run.get('observed_entities') for run in runs],
            declared_inventory_item_counts=[run.get('inventory_items') for run in runs],
            arrival_error_m=[run.get('arrival_error_m') for run in runs if run['actual_sim_full']],
            root_failure_codes=[run.get('root_failure_codes',[]) for run in runs if run['status']!='PASS'],
            failure_origins=[run.get('failure_origin') for run in runs if run['status']!='PASS'],
            failure_codes=[run['failure_code'] or 'HARNESS_OR_ENGINE_FAILURE' for run in runs if run['status']!='PASS'],
            held_without_usage_usd={name:str(sum((Decimal(run.get('held_by_provider',{}).get(name,'0')) for run in runs),Decimal(0))) for name in ('nebius','openai')},
            estimated_usd={name:str(sum((Decimal(run['cost_by_provider'][name]) for run in runs),Decimal(0))) for name in ('nebius','openai')}))
    trial_keys=('id','status','observer_model','planner_model','inference_source_sha256',
                'actual_requests','repair_requests','generation_ready','final_render_status',
                'render_reviews','saved_items','failure_code','root_failure_codes','failure_origin',
                'rejected_http_statuses','actual_sim_full','generation_active_s','model_http_wall_s',
                'end_to_end_wall_s','cost_by_provider','held_by_provider','unknown_requests','pending_locks')
    return dict(schema_version='public-combination-benchmark-1.2',dataset='private-bedroom-01',
        distinct_source_photos=1,independent_generalization_test=False,status=campaign['status'],
        cohorts=result,invoice_verified=False,physical_robot_pass=False,
        completed_at=campaign.get('completed_at'),
        trials=[{key:run.get(key) for key in trial_keys} for run in campaign['runs'] if run.get('actual_requests',0)>0],
        cpu_profile_anomalous_trials=sum(bool(run.get('cpu_profile_invalid_profiles')) or any(p.get('self_s',0)>p.get('cumulative_s',0)+.000001
            or min(p.get('self_s',0),p.get('cumulative_s',0))<0 for p in run.get('cpu_profile_top_self',[])) for run in campaign['runs']),
        preflight_failures=sum(r.get('status')=='PREFLIGHT_FAIL' for r in campaign['runs']),
        blocked_providers=sorted(blocked_providers(campaign)),
        deferred_cases=[{key:row.get(key) for key in ('id','status','reason')}
                        for row in campaign.get('deferred_cases',[])],
        source_images_included=False,room_geometry_included=False,raw_responses_included=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--run-next',action='store_true',help='One fresh run explicitly within current campaign; otherwise read-only report')
    parser.add_argument('--id',default='flash-lightning-2')
    parser.add_argument('--manifest',type=Path,help='New frozen multi-case lane, never modifies legacy campaign')
    parser.add_argument('--authorization',type=Path,help='Separate current expiring human/provider grant')
    parser.add_argument('--initialize',action='store_true',help='Exclusive local campaign initialization; no inference')
    parser.add_argument('--reconcile',action='store_true',help='Audit an interrupted existing child; never re-dispatch')
    args=parser.parse_args()
    if args.manifest:
        if not args.authorization:parser.error('--manifest requires --authorization')
        from scripts.benchmark_campaign import manifest_main
        return manifest_main(args)
    if args.authorization or args.initialize or args.reconcile:parser.error('New campaign options require --manifest')
    directory=args.directory.resolve();path=directory/'campaign.json'
    campaign=collect(directory,read(path))
    if not args.run_next:
        write(path,campaign);write(directory/'public-summary.json',public_summary(campaign))
        print(json.dumps({'status':campaign['status'],'settled_runs':sum(r.get('audit_status')=='PASS' for r in campaign['runs']),
            'exposure_usd':{k:str(v) for k,v in exposure(campaign).items()}},ensure_ascii=True));return
    case=args.id.rsplit('-',1)[0]
    if case not in PAIRS or args.id not in campaign['planned_remaining_cases']:
        raise ValueError('Only frozen reviewed current campaign cases allowed')
    lock=directory/'campaign.dispatch-lock'
    with lock.open('x',encoding='utf-8') as stream:json.dump({'pid':os.getpid(),'case':args.id},stream)
    try:
        if (datetime.fromisoformat(campaign['deadline'])-datetime.now(timezone.utc)).total_seconds()<1800:
            raise ValueError('CAMPAIGN_DEADLINE_RESERVE')
        if campaign['status']!='RUNNING' or any(r.get('audit_status')!='PASS' for r in campaign['runs']):raise ValueError('UNSETTLED_PRIOR_RUN')
        if repeated_failure_stop(campaign):raise ValueError('FIVE_DISTINCT_SAME_FAILURE_STOP')
        if any(r['id']==args.id for r in campaign['runs']):raise ValueError('CASE_ALREADY_STARTED')
        if any(output_limit_reached(run) for run in campaign['runs']):raise ValueError('OUTPUT_LIMIT_STOP')
        totals=exposure(campaign);models=PAIRS[case];providers={provider(model) for model in models}
        blocked=blocked_providers(campaign)
        if providers&blocked:raise ValueError('PROVIDER_PAYMENT_REQUIRED_STOP:'+','.join(sorted(providers&blocked)))
        limit=min([Decimal('1'),*[Decimal(campaign['limits_usd'][name])-totals[name] for name in providers]]).quantize(Decimal('.01'),rounding=ROUND_DOWN)
        if limit<=0:raise ValueError('NEBIUS_BUDGET_EXHAUSTED')
        campaign['runs'].append(dict(id=args.id,status='RESERVED',
            reserved_usd={name:str(limit) if name in providers else '0' for name in ('nebius','openai')},
            fresh=True,observer_model=models[0],planner_model=models[1]))
        write(path,campaign)
        command=[sys.executable,str(ROOT/'scripts/run_ordinary_staged_live_ten.py'),str(directory/args.id),
            str(ROOT/'outputs/ordinary-full-retest-20261010/run-1/1-사진-1.jpg'),
            '--recommended-nebius','--benchmark-profile','--request-cap','24','--cost-limit',str(limit),
            '--observer-model',models[0],'--planner-model',models[1],
            '--approval-text',campaign['authorization']+'; fresh '+args.id+'; current serialized per-run combined USD'+str(limit)]
        started=time.monotonic()
        with (directory/(args.id+'.log')).open('x',encoding='utf-8') as stream:
            process=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        campaign=read(path);campaign['runs'][-1]['end_to_end_wall_s']=round(time.monotonic()-started,3)
        campaign['runs'][-1]['runner_returncode']=process.returncode
        campaign=collect(directory,campaign)
        write(path,campaign);write(directory/'public-summary.json',public_summary(campaign))
        print(json.dumps({'status':campaign['runs'][-1]['status'],'actual_requests':campaign['runs'][-1].get('actual_requests'),
            'exposure_usd':{k:str(v) for k,v in exposure(campaign).items()}},ensure_ascii=True))
    finally:
        lock.unlink()


if __name__=='__main__':main()
