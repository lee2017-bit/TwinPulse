# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Auditor-normalized result accounting, never a model quality judge.

Keeps every scheduled job, including no-call preflight, audit failure, unknown
settlement and unscored quality. An actual caller must supply audited evidence;
this pure module cannot turn fixture/replay or a production critic into truth.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import math
import random

STAGES=('provider_response','generation','independent_quality','current_render',
        'semantic_goal_arrival','stop','reload','reopen')
VERDICTS={'PASS','FAIL','UNKNOWN','NOT_REACHED','NOT_EVALUATED'}


def _money(value):
    if type(value) is not str:raise ValueError('BENCHMARK_COST_INVALID')
    try:amount=Decimal(value)
    except (InvalidOperation,TypeError,ValueError):raise ValueError('BENCHMARK_COST_INVALID') from None
    if not amount.is_finite() or amount<0:raise ValueError('BENCHMARK_COST_INVALID')
    return amount


def account(prepared,records):
    planned={job['job_id']:job for job in prepared['jobs']};seen={}
    for row in records:
        if type(row) is not dict or set(row)-{'diagnostic_verdict'}!={'job_id','manifest_sha256','started','evidence_mode',
                'audit_status','stages','estimated_usd','held_usd'}:
            raise ValueError('BENCHMARK_RESULT_SHAPE_INVALID')
        diagnostic=row.get('diagnostic_verdict')
        if diagnostic is not None:
            from scripts.benchmark_diagnostic import REJECTIONS
            from scripts.benchmark_protocol import DIGEST
            if (type(diagnostic) is not dict or set(diagnostic)!={'status','expected_outcome','code',
                    'evidence_sha256','semantic_goal_arrival','physical_authority'}
                    or diagnostic['status']!='PASS' or diagnostic['expected_outcome'] not in ('rejection','clarification')
                    or diagnostic['semantic_goal_arrival'] is not False or diagnostic['physical_authority'] is not False
                    or type(diagnostic['evidence_sha256']) is not str or not DIGEST.fullmatch(diagnostic['evidence_sha256'])
                    or diagnostic['code'] not in REJECTIONS|{'SIM_TARGET_CLARIFICATION'}):
                raise ValueError('BENCHMARK_DIAGNOSTIC_VERDICT_INVALID')
        if row.get('job_id') not in planned or row['job_id'] in seen:
            raise ValueError('BENCHMARK_RESULT_JOB_UNKNOWN_OR_DUPLICATE')
        if row.get('manifest_sha256')!=prepared['manifest_sha256']:
            raise ValueError('BENCHMARK_RESULT_COHORT_CHANGED')
        if type(row.get('started')) is not bool:raise ValueError('BENCHMARK_STARTED_INVALID')
        if row.get('evidence_mode') not in ('actual_fresh','fixture','saved_replay'):
            raise ValueError('BENCHMARK_EVIDENCE_MODE_REQUIRED')
        if row.get('audit_status') not in ('PASS','FAIL','UNKNOWN','NOT_EVALUATED'):
            raise ValueError('BENCHMARK_AUDIT_STATUS_INVALID')
        stages=row.get('stages')
        if type(stages) is not dict or set(stages)!=set(STAGES) or any(v not in VERDICTS for v in stages.values()):
            raise ValueError('BENCHMARK_STAGE_STATUS_INVALID')
        if not row['started'] and any(v not in {'NOT_REACHED','NOT_EVALUATED'} for v in stages.values()):
            raise ValueError('BENCHMARK_NOT_RUN_CANNOT_PASS_STAGE')
        for name in ('estimated_usd','held_usd'):
            costs=row.get(name)
            if costs is not None:
                if type(costs) is not dict or any(p not in ('nebius','openai') for p in costs):
                    raise ValueError('BENCHMARK_PROVIDER_COST_INVALID')
                for cost in costs.values():_money(cost)
        seen[row['job_id']]=row
    outcomes=[]
    for job in prepared['jobs']:
        row=seen.get(job['job_id'])
        expected=(prepared.get('packets',{}).get(job['case_id'],{}).get('goal') or {}).get('expected','arrival')
        if expected not in ('arrival','rejection','clarification'):
            raise ValueError('BENCHMARK_EXPECTED_OUTCOME_INVALID')
        if expected!='arrival' and job['split']!='diagnostic':
            raise ValueError('NEGATIVE_CASE_REQUIRES_DIAGNOSTIC_SPLIT')
        full=bool(expected=='arrival' and row and row['started'] and row['evidence_mode']=='actual_fresh'
            and row['audit_status']=='PASS' and all(v=='PASS' for v in row['stages'].values()))
        diagnostic=(row or {}).get('diagnostic_verdict') or {}
        guard=bool(expected!='arrival' and row and row['started'] and row['evidence_mode']=='actual_fresh'
            and row['audit_status']=='PASS' and diagnostic.get('status')=='PASS'
            and diagnostic.get('expected_outcome')==expected and diagnostic.get('evidence_sha256')
            and all(row['stages'][s]=='PASS' for s in ('provider_response','generation','current_render','reload','reopen')))
        outcomes.append(dict(**job,expected_outcome=expected,record=row,qualified_full_pass=full,qualified_diagnostic_pass=guard))
    groups=[]
    for split,modality,expected in sorted({(j['split'],j['modality'],j['expected_outcome']) for j in outcomes}):
        for config in prepared['configs']:
            rows=[r for r in outcomes if r['split']==split and r['modality']==modality
                  and r['expected_outcome']==expected and r['config_id']==config['config_id']]
            stage_counts={}
            for stage in STAGES:
                def verdict(outcome):
                    row=outcome['record']
                    if not row:return 'NOT_REACHED'
                    if row['evidence_mode']!='actual_fresh':return 'NOT_EVALUATED'
                    if expected!='arrival' and stage=='semantic_goal_arrival':return 'NOT_EVALUATED'
                    value=row['stages'][stage]
                    return 'UNKNOWN' if value=='PASS' and row['audit_status']!='PASS' else value
                counts=Counter(verdict(r) for r in rows)
                stage_counts[stage]=dict(planned=len(rows),attempted=sum(counts[v] for v in ('PASS','FAIL','UNKNOWN')),
                    **{v.lower():counts[v] for v in sorted(VERDICTS)})
            actual=[r for r in rows if r['record'] and r['record']['started'] and r['record']['evidence_mode']=='actual_fresh']
            passed=sum(r['qualified_full_pass'] for r in rows)
            diagnostic_passed=sum(r['qualified_diagnostic_pass'] for r in rows)
            cost_rows=[r for r in rows if r['record'] and r['record']['evidence_mode']=='actual_fresh']
            all_costs_known=all(r['record'].get('estimated_usd') is not None and
                r['record'].get('held_usd') is not None for r in cost_rows if r['record']['started'])
            estimated={provider:sum((_money(r['record']['estimated_usd'].get(provider,'0'))
                for r in cost_rows if r['record'].get('estimated_usd') is not None),Decimal(0))
                       for provider in ('nebius','openai')}
            held={provider:sum((_money(r['record']['held_usd'].get(provider,'0'))
                for r in cost_rows if r['record'].get('held_usd') is not None),Decimal(0))
                  for provider in ('nebius','openai')}
            all_costs_known=all_costs_known and not any(held.values())
            groups.append(dict(split=split,modality=modality,expected_outcome=expected,
                primary_completion_population=split in ('development','holdout') and expected=='arrival',
                diagnostic_acceptance=('EVALUATED' if any((r['record'] or {}).get('diagnostic_verdict') for r in rows)
                    else 'NOT_EVALUATED') if expected!='arrival' else 'NOT_APPLICABLE',
                qualified_diagnostic_pass=diagnostic_passed,
                diagnostic_rate_over_actual_started=diagnostic_passed/len(actual) if actual and expected!='arrival' else None,
                config_id=config['config_id'],planned=len(rows),
                started=sum(bool(r['record'] and r['record']['started']) for r in rows),
                actual_fresh_started=len(actual),not_run=sum(not r['record'] or not r['record']['started'] for r in rows),
                audit_failed=sum(bool(r['record'] and r['record']['audit_status']=='FAIL') for r in rows),
                audit_unknown=sum(bool(r['record'] and r['record']['audit_status']=='UNKNOWN') for r in rows),
                non_actual=sum(bool(r['record'] and r['record']['evidence_mode']!='actual_fresh') for r in rows),
                qualified_full_pass=passed,stages=stage_counts,
                completion_rate_over_actual_started=passed/len(actual) if actual and expected=='arrival' else None,
                quality_not_evaluated=stage_counts['independent_quality']['not_evaluated'],
                estimated_usd={p:str(v) for p,v in estimated.items()},held_usd={p:str(v) for p,v in held.items()},
                cost_complete=all_costs_known,
                estimated_cost_per_qualified_success=(str(sum(estimated.values())/passed)
                    if all_costs_known and passed else None)))
    return dict(schema_version='comparative-benchmark-accounting-1.2',groups=groups,
        outcomes=outcomes,manifest_sha256=prepared['manifest_sha256'],
        rankings='NOT_COMPUTED',invoice_verified=False,physical_robot_pass=False)


def compare_paired(result,left,right,modality,*,split='holdout',seed=0,alpha=.05,resamples=10000):
    """Same case/repeat, aggregate within room first. No quality-free winner."""
    selected={config:{(row['case_id'],row['repeat']):row for row in result['outcomes']
        if row['config_id']==config and row['modality']==modality and row['split']==split}
              for config in (left,right)}
    if any(row.get('expected_outcome','arrival')!='arrival' for values in selected.values() for row in values.values()):
        return dict(status='INCONCLUSIVE',reason='DIAGNOSTIC_OUTCOME_NOT_ARRIVAL_COMPARISON')
    if left==right or not selected[left] or selected[left].keys()!=selected[right].keys():
        return dict(status='INCONCLUSIVE',reason='INCOMPLETE_OR_UNPAIRED_INPUTS')
    def binary(outcome):
        row=outcome['record']
        if not row or not row['started'] or row['evidence_mode']!='actual_fresh' or row['audit_status']!='PASS':return None
        if outcome['qualified_full_pass']:return 1.
        if 'FAIL' in row['stages'].values():return 0.
        return None
    rooms={}
    for key in selected[left]:
        a,b=selected[left][key],selected[right][key]
        av,bv=binary(a),binary(b)
        if av is None or bv is None:return dict(status='INCONCLUSIVE',reason='QUALITY_OR_AUDIT_OR_OUTCOME_UNRESOLVED')
        if a['room_group']!=b['room_group']:raise ValueError('BENCHMARK_ROOM_PAIR_CHANGED')
        rooms.setdefault(a['room_group'],[]).append(av-bv)
    differences=[sum(values)/len(values) for _,values in sorted(rooms.items())]
    return dict(status='DESCRIPTIVE_PAIRED_COMPARISON_NOT_WINNER',modality=modality,split=split,
        left_config=left,right_config=right,paired_trials=len(selected[left]),
        **paired_interval(differences,seed=seed,resamples=resamples,alpha=alpha))


def paired_interval(room_differences,*,seed=0,resamples=10000,alpha=.05):
    """Each datum is one independent room's mean paired difference, in [-1,1].

    Constant/small samples use bounded Hoeffding intervals, not a zero-width
    bootstrap. Caller predeclares family-adjusted alpha and completed matched
    inputs. No power or winner claim is automatically inferred from this CI.
    """
    if (not room_differences or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1
            for v in room_differences) or not 0<alpha<1 or type(resamples) is not int or resamples<100):
        raise ValueError('BENCHMARK_PAIRED_INPUT_INVALID')
    n=len(room_differences);mean=sum(room_differences)/n
    if n<10 or len(set(room_differences))==1:
        margin=math.sqrt(2*math.log(2/alpha)/n)
        interval=[max(-1.,mean-margin),min(1.,mean+margin)];method='BOUNDED_HOEFFDING'
    else:
        rng=random.Random(seed)
        samples=sorted(sum(rng.choice(room_differences) for _ in range(n))/n for _ in range(resamples))
        interval=[samples[math.floor((resamples-1)*alpha/2)],samples[math.ceil((resamples-1)*(1-alpha/2))]]
        method='ROOM_CLUSTER_PERCENTILE_BOOTSTRAP'
    return dict(independent_rooms=n,paired_mean_difference=mean,interval=interval,
        method=method,alpha=alpha,seed=seed,resamples=resamples,
        practical_superiority='NOT_ASSESSED')


def same_root_model_streak(rows,role):
    """Role-specific five distinct models, not five pairs/configurations."""
    root=None;models=set()
    for row in rows:
        if row.get('role')!=role:continue
        if not row.get('actual_dispatched') or row.get('status')!='FAIL' or not row.get('root_code'):
            root=None;models=set();continue
        if root!=row['root_code']:root=row['root_code'];models=set()
        models.add((row['provider'],row['model_id']))
        if len(models)>=5:return dict(stop=True,role=role,root_code=root,distinct_models=len(models))
    return dict(stop=False,role=role,root_code=root,distinct_models=len(models))
