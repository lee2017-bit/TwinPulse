# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Audited functional results plus deliberately auxiliary pre-output kind recall.

No model self-judge, hidden oracle injection, human quality PASS or automatic
winner. Public metrics omit photos, prompts, geometry and raw responses.
"""
import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import prepare,read_json,file_sha,canonical_sha
from scripts.benchmark_campaign import validate,exposure
from scripts.benchmark_results import paired_interval
from scripts.run_model_combination_benchmark import summarize_run,distribution

# General semantic aliases, fixed before seeing any result in this cohort.
GROUPS={
    'cabinet':{'cabinet','wardrobe','cupboard','sideboard','dresser','storage_cabinet','drawer_unit'},
    'table':{'table','desk','dining_table','coffee_table','workbench','diningtable'},
    'chair':{'chair','office_chair','armchair','dining_chair','stool'},
    'screen':{'monitor','tv','television','computer_monitor','screen'},
    'shelf':{'shelf','bookshelf','bookcase','rack','storage_shelf','storage_rack','shelving_unit'},
    'box':{'box','storage_box','cardboard_box'},
    'bed':{'bed'},'pallet':{'pallet'},'bag':{'bag','backpack','handbag'},
    'curtain':{'curtain','curtains','blind','blinds'},'cable':{'cable','cables','cord','wire','power_strip'},
    'rug':{'rug','carpet','floor_mat','mat'},'lamp':{'lamp','floor_lamp','table_lamp','pendant_lamp','ceiling_light','light_fixture'},
    'plant':{'plant','potted_plant','vase','flower_vase'}
}


def category(kind):
    kind=str(kind).lower().strip().replace(' ','_').replace('-','_')
    return next((key for key,values in GROUPS.items() if kind in values),kind)


def count_recall(expected,predicted):
    denominator=sum(expected.values())
    matched=sum(min(count,predicted.get(kind,0)) for kind,count in expected.items())
    return dict(matched=matched,denominator=denominator,value=matched/denominator if denominator else None)


def auxiliary(reference,checkpoint,project):
    observed=Counter(category(e.get('category') or e.get('kind')) for e in
        (checkpoint.get('observation') or {}).get('entities',[]) if e.get('role','object')=='object')
    draft=(project or {}).get('site_draft') or {};plan=draft.get('plan')
    predicted=Counter()
    if plan:
        for call in plan.get('calls',[]):
            if call.get('tool') in ('place_furniture','place_room_item'):
                predicted[category(call['arguments']['kind'])]+=1
            elif call.get('tool')=='create_rack_row':
                predicted[category('rack')]+=1
            elif call.get('tool')=='place_pallet_stack':
                # Loaded cargo is not an empty pallet; retain that distinction.
                predicted[category('pallet_stack')]+=1
    expected=reference['minimum_counts']
    return dict(reference_source=reference['source'],coverage=reference['coverage'],
        observer_required_kind_recall=count_recall(expected,observed) if checkpoint.get('observation') else None,
        saved_required_kind_recall=count_recall(expected,predicted),saved_plan_available=bool(plan),
        # Kind recall is not geometry/support/scale accuracy or photo precision.
        spatial_accuracy='NOT_EVALUATED',support_accuracy='NOT_EVALUATED',
        metric_scale='UNMEASURED' if reference['metric_dimensions'] is None else 'EXPLICIT_DESIGN_NOT_MEASURED',
        full_quality='NOT_EVALUATED',human_reviewers=0)


def collect(directory,manifest,authorization):
    prepared=prepare(manifest);state=validate(read_json(directory/'manifest-campaign.json'),prepared,read_json(authorization))
    refs_path=Path(manifest).resolve().parent/'auxiliary-reference.json'
    if prepared['freeze'].get(str(refs_path))!=file_sha(refs_path):raise ValueError('PILOT_REFERENCE_NOT_FROZEN')
    refs={r['case_id']:r for r in read_json(refs_path)['cases']};runs={r['job_id']:r for r in state['runs']};trials=[]
    for job in prepared['jobs']:
        run=runs.get(job['job_id']);row={**job,'status':'NOT_RUN','audit_status':'NOT_EVALUATED',
            'functional_pass':False,'qualified_full_pass':False,'quality_status':'NOT_EVALUATED'}
        if run:
            try:
                summary=summarize_run(directory/job['job_id'])
                if not run.get('settled') or any(summary[k]!=run['summary'][k] for k in
                    ('status','actual_requests','cost_by_provider','held_by_provider','unknown_requests','pending_locks')):
                    raise ValueError('PILOT_UNSETTLED_OR_CHANGED_SUMMARY')
                evidence=directory/job['job_id']/'run-1/runtime/provider-evidence/generation-store/checkpoint'
                checkpoints=list(evidence.glob('*.json'))
                if len(checkpoints)>1:raise ValueError('PILOT_AMBIGUOUS_CHECKPOINT')
                checkpoint=read_json(checkpoints[0])['payload'] if checkpoints else {}
                project=read_json(directory/job['job_id']/'run-1/runtime/active_project.json')
                row.update(status=summary['status'],audit_status='PASS',functional_pass=summary['status']=='PASS',
                    **{k:summary.get(k) for k in ('actual_requests','generation_ready','generation_completed','actual_sim_full',
                        'repair_requests','repair_kinds','root_failure_codes','failure_origin','rejected_http_statuses',
                        'generation_active_s','model_http_wall_s','cost_by_provider','held_by_provider','final_render_status',
                        'observed_entities','saved_items','semantic_goal_distance_m','navigation_evidence_status')},
                    auxiliary=auxiliary(refs[job['case_id']],checkpoint,project))
            except (ValueError,OSError,KeyError,TypeError) as error:
                row.update(status='UNRESOLVED',audit_status='FAIL',audit_error_type=type(error).__name__,
                    reserved_usd=run['reserved_usd'])
        trials.append(row)
    groups=[]
    for modality in ('photo','text'):
        for config in prepared['configs']:
            rows=[r for r in trials if r['modality']==modality and r['config_id']==config['config_id']]
            actual=[r for r in rows if r['status']!='NOT_RUN'];audited=[r for r in actual if r['audit_status']=='PASS']
            failures=Counter(code for r in audited if not r['functional_pass'] for code in r.get('root_failure_codes',[]))
            recall=[r['auxiliary']['saved_required_kind_recall']['value'] for r in audited]
            groups.append(dict(modality=modality,config_id=config['config_id'],planned=len(rows),started=len(actual),
                audited=len(audited),functional_pass=sum(r['functional_pass'] for r in audited),
                qualified_full_pass=0,quality_status='NOT_EVALUATED',
                saved_required_kind_recall_mean=sum(recall)/len(recall) if recall else None,
                http_wall=distribution([r['model_http_wall_s'] for r in audited]),
                generation_active=distribution([r['generation_active_s'] for r in audited if r.get('generation_active_s') is not None]),
                requests=sum(r['actual_requests'] for r in audited),failure_codes=dict(failures)))
    paired=[]
    for modality in ('photo','text'):
        for left,right in combinations([c['config_id'] for c in prepared['configs']],2):
            differences=[]
            room_ids=sorted({r['room_group'] for r in trials if r['modality']==modality})
            for room in room_ids:
                a=[r for r in trials if r['modality']==modality and r['room_group']==room and r['config_id']==left]
                b=[r for r in trials if r['modality']==modality and r['room_group']==room and r['config_id']==right]
                if any(r['audit_status']!='PASS' for r in a+b):continue
                differences.append(sum(r['functional_pass'] for r in a)/len(a)-sum(r['functional_pass'] for r in b)/len(b))
            interval=paired_interval(differences,seed=61146,alpha=.05/20) if differences else None
            paired.append(dict(modality=modality,left=left,right=right,
                completed_matched_rooms=len(differences),planned_rooms=len(room_ids),
                functional_paired_interval=interval,quality_ranking='NOT_EVALUATED',
                conclusion='INCONCLUSIVE' if not interval or interval['interval'][0]<=0<=interval['interval'][1] else 'FUNCTIONAL_ONLY_PILOT_DIFFERENCE'))
    return dict(schema_version='public-pilot-benchmark-1.0',manifest_sha256=prepared['manifest_sha256'],
        dataset_id=prepared['dataset_id'],status=state['status'],planned=len(trials),started=len(runs),
        actual_requests=sum(r.get('actual_requests',0) for r in trials),
        configs=prepared['configs'],groups=groups,paired_comparisons=paired,trials=trials,
        exposure_usd={p:str(v) for p,v in exposure(state).items()},invoice_verified=False,
        human_quality='NOT_EVALUATED',statistical_family_alpha=.05,
        independent_rooms_per_modality=3,source_images_included=False,user_text_included=False,geometry_included=False,
        raw_responses_included=False,physical_robot_pass=False,whole_demo_pass=False,
        claim_scope='FROZEN_TASK_SPECIFIC_PILOT_NOT_GLOBAL_RANKING')


def markdown(report):
    lines=['# TwinPulse actual model combination pilot','',
        'Frozen inputs, two repetitions, balanced serial execution. Functional success is not independently quality-qualified success.',
        'Photo references are pre-output agent-reviewed visible lower bounds. Text references are explicit authored design contracts. No human blind quality review.',
        '', '| Input | Combination | Functional / planned | Audited / started | Auxiliary saved kind recall | HTTP p50 / p95 s |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    for g in report['groups']:
        recall=g['saved_required_kind_recall_mean'];time=g['http_wall']
        lines.append(f"| {g['modality']} | {g['config_id']} | {g['functional_pass']}/{g['planned']} | {g['audited']}/{g['started']} | {recall:.3f} | {time['p50_s']} / {time['p95_s']} |" if recall is not None else
            f"| {g['modality']} | {g['config_id']} | {g['functional_pass']}/{g['planned']} | {g['audited']}/{g['started']} | NOT_EVALUATED | NOT_RUN |")
    lines+=['',f"Actual HTTP requests: {report['actual_requests']}. Provider exposures, including prior carry-in: {report['exposure_usd']}.",
        'Only three independent inputs per modality; repetitions are not new rooms. Family-adjusted room-clustered paired intervals are retained in JSON. No global winner is declared.',
        'Failure and unexecuted cases remain in the denominator. Unknown billing retains reservations. Costs are usage estimates, not invoices.',
        'Public export contains metrics only; no private photo, prompt, raw response or geometry. No robot or complete product acceptance is claimed.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--authorization',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();paths=[*args.directory.rglob('*.json'),args.manifest,args.authorization]
    hashes={p:file_sha(p) for p in paths}
    report=collect(args.directory,args.manifest,args.authorization)
    if any(file_sha(p)!=digest for p,digest in hashes.items()):raise ValueError('PILOT_ORIGINAL_CHANGED')
    args.output.mkdir(parents=True,exist_ok=False)
    with (args.output/'public-pilot.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,ensure_ascii=False,allow_nan=False)
    with (args.output/'public-pilot.md').open('x',encoding='utf-8') as stream:stream.write(markdown(report))
    print(json.dumps(dict(status='PILOT_COLLECTED_READ_ONLY',planned=report['planned'],started=report['started'],
        actual_requests=report['actual_requests'],HTTP=0)))


if __name__=='__main__':main()
