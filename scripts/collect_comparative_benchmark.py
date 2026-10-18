# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only ordinary audit -> independent evaluator -> metrics-only report.

Default never dispatches inference or services. Every scheduled NOT_RUN/unknown/
failed job remains in the denominator. Old single-photo campaigns cannot be
retroactively labelled a frozen multi-case benchmark.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import prepare,read_json,file_sha,canonical_sha,checked_manifest,effective_settings_sha
from scripts.benchmark_campaign import validate,exposure,utc,eligibility_matrix
from scripts.benchmark_results import STAGES,account,compare_paired
from scripts.benchmark_quality import evaluate


def stages_from_evidence(summary,result,quality_status):
    browser=result.get('browser') or {};draft=(browser.get('workflow') or {}).get('site_draft') or {}
    rows=summary['rows'];generation=summary['generation_completed'] and summary['generation_ready']
    revision=draft.get('revision')
    frames=[f for f in browser.get('frames',[]) if revision and f.get('applied_revision')==revision]
    arrival=browser.get('semantic_arrival') or {};stop=browser.get('stop') or {};reload=browser.get('reload_evidence') or {}
    arrived=(arrival.get('runtime_state')=='completed' and arrival.get('telemetry_available') is True
        and revision and arrival.get('applied_revision')==revision
        and type(arrival.get('distance_to_goal_m')) in (int,float) and 0<=arrival['distance_to_goal_m']<=.04)
    stopped=(stop.get('runtime_state')=='paused' and stop.get('telemetry_available') is True
        and revision and stop.get('applied_revision')==revision and stop.get('position_m') is not None)
    diagnostic=bool(summary.get('diagnostic_goal_acceptance'))
    reloaded=(reload.get('status')=='PASS' and reload.get('plan_sha256')==draft.get('plan_sha256')
        and reload.get('input_revision')==draft.get('input_revision')
        and reload.get('builds_before') is not None and reload['builds_before']==reload.get('builds_after')
        and reload.get('runs_before') is not None and reload['runs_before']==reload.get('runs_after')
        and reload.get('restored_run_authorization') is False and reload.get('runtime_state')==('completed' if diagnostic else 'paused'))
    reopened=result.get('render_review_closed_backend_reopen') or {}
    reopen=(reopened.get('status')=='PASS' and reopened.get('plan_sha256')==draft.get('plan_sha256')
        and reopened.get('source_unchanged') is True and reopened.get('automatic_dispatch') is False)
    return dict(provider_response='PASS' if rows and all(r['status']=='received' and r['finish_reason']=='stop' for r in rows) else 'FAIL',
        generation='PASS' if generation else 'FAIL',independent_quality=quality_status,
        current_render='PASS' if generation and frames else 'NOT_REACHED',
        semantic_goal_arrival='NOT_EVALUATED' if diagnostic else 'PASS' if arrived else 'FAIL' if generation else 'NOT_REACHED',
        stop='NOT_EVALUATED' if diagnostic else 'PASS' if stopped else 'NOT_REACHED',reload='PASS' if reloaded else 'NOT_REACHED',
        reopen='PASS' if reopen else 'NOT_REACHED')


def collector(prepared,state,directory,manifest,rubric=None,*,visual_reviews=None):
    """No stored campaign summary is trusted as an audited trial result."""
    from scripts.run_model_combination_benchmark import summarize_run
    from scripts.benchmark_evaluation import selected_rubric,readiness
    rubric=selected_rubric(prepared,rubric)
    if prepared.get('evaluation') and prepared['evaluation']!=manifest.get('evaluation'):
        raise ValueError('BENCHMARK_EVALUATION_BINDING_CHANGED')
    if prepared.get('evaluation') and readiness(manifest,prepared['packets'])!=prepared['evaluation_readiness']:
        raise ValueError('BENCHMARK_LABEL_READINESS_CHANGED')
    directory=Path(directory);visual_reviews=visual_reviews or {};records=[];details=[]
    cases={case['case_id']:case for case in manifest['cases']};jobs={j['job_id']:j for j in prepared['jobs']}
    for run in state['runs']:
        job=jobs[run['job_id']];target=directory/job['job_id'];packet=prepared['packets'][job['case_id']]
        record=dict(job_id=job['job_id'],manifest_sha256=prepared['manifest_sha256'],started=True,
            evidence_mode='actual_fresh',audit_status='UNKNOWN',stages={s:'UNKNOWN' for s in STAGES},
            estimated_usd=None,held_usd=deepcopy(run['reserved_usd']))
        record['stages']['independent_quality']='NOT_EVALUATED'
        detail=dict(job_id=job['job_id'],status='UNKNOWN',quality=None)
        # Missing files or an exited PID cannot prove zero HTTP/billing. An
        # interrupted preflight and deleted evidence retain the full reservation.
        try:
            summary=summarize_run(target);approval=read_json(target/'approval.json')
            result=read_json(target/'run-1/result.json');browser=result.get('browser') or {}
            if prepared.get('execution_environment'):
                from scripts.benchmark_environment import identity
                expected=identity(prepared['execution_environment'])
                summary_result=read_json(target/'summary.json')
                from scripts.benchmark_environment import audit_environment_evidence
                audit_environment_evidence(approval,summary_result)
                if (approval.get('execution_environment_sha256')!=expected
                        or approval.get('evaluation_rubric_sha256')!=prepared['evaluation']['rubric_sha256']):
                    raise ValueError('BENCHMARK_EXECUTION_ENVIRONMENT_AUDIT_MISSING_OR_CHANGED')
            config=next(c for c in prepared['configs'] if c['config_id']==job['config_id'])
            if (approval.get('benchmark_manifest_sha256')!=prepared['manifest_sha256']
                    or approval.get('case_id')!=job['case_id'] or approval.get('config_id')!=job['config_id']
                    or approval.get('settings_sha256')!=config['settings_sha256']
                    or read_json(target/'benchmark-case.json')!=packet or approval.get('generation_only') is not False
                    or not result.get('ordinary_live_audit') or result.get('inference_source_unchanged') is not True
                    or browser.get('photo_inference')!=('LIVE' if packet['modality']=='photo' else 'NOT_APPLICABLE')
                    or result.get('replay_source_at_start') or result.get('accepted_geometry_source_at_start')
                    or browser.get('robot_connections')!=0):
                raise ValueError('BENCHMARK_FRESH_INPUT_SETTINGS_OR_SOURCE_AUDIT_FAILED')
            audit_frozen_settings(approval,config,summary,target,state['authorization'])
            if run['settled'] and any(run['summary'].get(key)!=summary.get(key) for key in
                    ('status','audit_status','cost_by_provider','held_by_provider','actual_requests','unknown_requests','pending_locks')):
                raise ValueError('BENCHMARK_CAMPAIGN_SETTLEMENT_DIFFERS_FROM_RAW_AUDIT')
            actual=read_json(target/'run-1/runtime/active_project.json');draft=actual.get('site_draft')
            quality=None;case=cases[job['case_id']]
            label_ready=(not prepared.get('evaluation_readiness') or next(r for r in
                prepared['evaluation_readiness']['cases'] if r['case_id']==case['case_id'])['status']=='LABELS_REVIEWED_ATTESTED')
            if label_ready and prepared.get('evaluation_readiness'):
                labels=next(r for r in prepared['evaluation_readiness']['cases'] if r['case_id']==case['case_id'])
                label_ready=bool(run.get('started_at') and utc(labels['reviewed_at'])<=utc(run['started_at']))
            if rubric and case['annotations'] and draft and label_ready:
                annotation_path=Path(case['annotations']['path'])
                if file_sha(annotation_path)!=case['annotations']['sha256']:
                    raise ValueError('BENCHMARK_ANNOTATION_SHA_CHANGED')
                # Draft bytes must match actual saved/approved candidate, not a
                # hand-picked plan copied in merely for independent evaluation.
                from twinpulse_app.project_store import ProjectRecord
                saved=ProjectRecord.from_dict(actual).site_draft
                public=(browser.get('workflow') or {}).get('site_draft') or {}
                if (saved.plan_sha256!=public.get('plan_sha256')
                        or saved.site.scene.revision!=public.get('revision')):
                    raise ValueError('BENCHMARK_EVALUATION_SAVED_PLAN_UNBOUND')
                visual=visual_reviews.get(job['job_id'])
                if visual:
                    frames=[f for f in browser.get('frames',[]) if f.get('applied_revision')==saved.site.scene.revision]
                    if not any(f.get('sha256')==visual.get('frame_sha256') for f in frames):
                        raise ValueError('BENCHMARK_VISUAL_REVIEW_FRAME_NOT_OBSERVED')
                quality=evaluate(read_json(annotation_path),packet,rubric,draft['plan'],
                                 draft.get('placement_contract'),render_review=visual)
            record.update(audit_status='PASS',stages=stages_from_evidence(summary,result,
                quality['status'] if quality else 'NOT_EVALUATED'),
                estimated_usd=summary['cost_by_provider'],held_usd=summary['held_by_provider'])
            if packet['goal']['expected']!='arrival':
                from scripts.benchmark_diagnostic import validate_diagnostic
                diagnostic=summary.get('diagnostic_goal_acceptance')
                record['diagnostic_verdict']=validate_diagnostic(packet,browser.get('diagnostic_goal')) if diagnostic else None
            detail.update(status=summary['status'],quality=quality,actual_requests=summary['actual_requests'],
                failure_codes=summary['root_failure_codes'],wall_http_s=summary['model_http_wall_s'])
        except (ValueError,OSError,KeyError,TypeError) as error:
            detail.update(status='AUDIT_FAIL_OR_UNRESOLVED',error_type=type(error).__name__)
            import re
            code=str(error).split(':',1)[0]
            detail['error_code']=code if re.fullmatch(r'BENCHMARK_[A-Z_]+',code) else 'LOCAL_EVIDENCE_AUDIT_ERROR'
            # Failure to audit is not proof of zero cost. Keep original reservation.
            record['audit_status']='FAIL' if isinstance(error,(ValueError,KeyError,TypeError)) else 'UNKNOWN'
        records.append(record);details.append(detail)
    from scripts.benchmark_results import _money
    # Re-audited costs, not a hand-edited controller summary, drive exposure.
    totals={p:_money(state['authorization']['providers'].get(p,{}).get('existing_exposure_usd','0')) for p in ('nebius','openai')}
    for record in records:
        for p in totals:
            totals[p]+=_money((record['estimated_usd'] or {}).get(p,'0'))+_money((record['held_usd'] or {}).get(p,'0'))
    return dict(accounting=account(prepared,records),private_details=details,
        exposure_usd={p:str(max(v,exposure(state)[p])) for p,v in totals.items()},HTTP=0,robot_commands=0)


def audit_frozen_settings(approval,config,summary,target,grant):
    route=approval['route'];stored=read_json(Path(target)/'reviewed-settings/provider_stage_routing.json')
    if (stored!={'schema_version':'1.0','route':route}
            or effective_settings_sha(route,config['roles'])!=config['settings_sha256']
            or route['generation_policy']['max_requests']!=grant['request_cap']
            or approval['cost_limit_usd']!=grant['trial_usd']
            or approval.get('benchmark_expires_at')!=grant['expires_at']):
        raise ValueError('BENCHMARK_EFFECTIVE_ROUTE_OR_RESOURCE_POLICY_CHANGED')
    if route.get('model_catalog_sha256'):
        from twinpulse_provider.model_contracts import load_catalog
        load_catalog(Path(target)/'reviewed-settings/stage_model_catalog.json',route['model_catalog_sha256'])
    stages=dict(twinpulse_image_observation='observer',twinpulse_render_review='critic',
                twinpulse_semantic_structure='planner',twinpulse_semantic_batch='planner',twinpulse_semantic_patch='repair')
    for row in summary['rows']:
        role=stages.get(row['stage'])
        if role is None or (row['provider'],row['model_id'])!=(config['roles'][role]['provider'],config['roles'][role]['model']):
            raise ValueError('BENCHMARK_ACTUAL_DISPATCH_ROLE_CHANGED')
        dispatch=read_json(Path(target)/'run-1/runtime/provider-evidence/dispatches'/(row['attempt_id']+'.json'))
        body=json.loads(dispatch['request_redacted']);stage='observer' if role in ('observer','critic') else 'planner'
        if body['model']!=row['model_id'] or body.get('max_tokens',body.get('max_completion_tokens'))!=route[stage]['max_output_tokens']:
            raise ValueError('BENCHMARK_ACTUAL_DISPATCH_OUTPUT_POLICY_CHANGED')
        if not utc(grant['approved_at'])<=utc(dispatch['started_at'])<utc(grant['expires_at']):
            raise ValueError('BENCHMARK_DISPATCH_OUTSIDE_APPROVAL_WINDOW')


def public_report(collected,prepared,*,alpha=.05):
    """Whitelist only aggregate metrics, anonymous schedule IDs and role names."""
    from scripts.benchmark_environment import identity
    result=collected['accounting'];configs=[c['config_id'] for c in prepared['configs']]
    from scripts.prepare_benchmark_model_catalog import report as catalog_report
    catalog_inventory=catalog_report(prepared['model_catalog'])['models'] if prepared.get('model_catalog') else []
    pairs=[(a,b) for i,a in enumerate(configs) for b in configs[i+1:]]
    modalities=sorted({j['modality'] for j in prepared['jobs']});family=max(1,len(pairs)*len(modalities))
    comparisons=[compare_paired(result,a,b,modality,alpha=alpha/family)
                 for a,b in pairs for modality in modalities]
    jobs=[dict(job_id=o['job_id'],config_id=o['config_id'],modality=o['modality'],split=o['split'],repeat=o['repeat'],
        expected_outcome=o['expected_outcome'],
        started=bool(o['record'] and o['record']['started']),
        audit_status=o['record']['audit_status'] if o['record'] else 'NOT_RUN',
        stages=o['record']['stages'] if o['record'] else {s:'NOT_REACHED' for s in STAGES},
        qualified_full_pass=o['qualified_full_pass'],qualified_diagnostic_pass=o['qualified_diagnostic_pass']) for o in result['outcomes']]
    for job in jobs:
        # A derived public result cannot claim arrival for a non-arrival task.
        # Leave the private/original evidence unchanged for debugging.
        if job['expected_outcome'] != 'arrival':
            job['stages'] = {**job['stages'], 'semantic_goal_arrival':'NOT_EVALUATED'}
    quality_metrics=[]
    details={d['job_id']:d for d in collected['private_details']}
    for outcome in result['outcomes']:
        quality=details.get(outcome['job_id'],{}).get('quality')
        if not quality:continue
        quality_metrics.append(dict(job_id=outcome['job_id'],config_id=outcome['config_id'],
            modality=outcome['modality'],split=outcome['split'],**{key:quality[key] for key in
                ('status','entity_precision','entity_recall','entity_f1','hazard_recall',
                 'spatial_accuracy','support_accuracy','size_compliance','room_size_compliance',
                 'geometry_contradictions','visual_recognizability','human_reviewers','excluded_unobservable')}))
    return dict(schema_version='public-comparative-benchmark-1.2',manifest_sha256=prepared['manifest_sha256'],
        reproducibility=dict(environment_sha256=identity(
            prepared['execution_environment']) if prepared.get('execution_environment') else None,
            runtime_scope='ENTRYPOINTS_REVIEWED_ASSETS_NOT_FULL_INSTALL' if prepared.get('execution_environment') else 'LEGACY_PARTIAL_FREEZE',
            rubric_sha256=(prepared.get('evaluation') or {}).get('rubric_sha256'),
            label_readiness=(prepared.get('evaluation_readiness') or {}).get('status','LEGACY_EVALUATION_SELECTION'),
            human_identity_verified=False),
        groups=result['groups'],configs=[dict(config_id=c['config_id'],roles=c['roles'],settings_sha256=c['settings_sha256'])
            for c in prepared['configs']],trials=jobs,paired_comparisons=comparisons,
        statistical_family_alpha=alpha,comparison_alpha=alpha/family,
        execution_eligibility=eligibility_matrix(prepared),account_model_availability='NOT_CHECKED_NO_NETWORK',
        catalog_role_eligibility=catalog_inventory,
        exposure_usd=collected['exposure_usd'],quality_metrics=quality_metrics,rankings='NOT_COMPUTED',HTTP=0,
        invoice_verified=False,physical_robot_pass=False,
        source_images_included=False,user_text_included=False,annotations_included=False,
        room_geometry_included=False,raw_responses_included=False,
        scope='FROZEN_CASE_RESULTS_NOT_GLOBAL_MODEL_SUPERIORITY')


def markdown(report):
    rows=['# Comparative benchmark — audited frozen conditions','',
        'No automatic winner. Photo and text are separate; missing independent quality is not PASS.','',
        '| Split | Modality | Expected task | Config | Planned | Actual started | Qualified full PASS | Diagnostic PASS | Quality unscored | Cost complete |',
        '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for group in report['groups']:
        rows.append('| '+ ' | '.join(map(str,(group['split'],group['modality'],group['expected_outcome'],group['config_id'],group['planned'],
            group['actual_fresh_started'],group['qualified_full_pass'],group['qualified_diagnostic_pass'],group['quality_not_evaluated'],group['cost_complete'])))+' |')
    rows+=['','Diagnostic rejection/clarification tasks never count as arrival completion. Only audited fresh goal/scene/event/no-command proofs can count as diagnostic acceptance.',
           'Local adapter support is not account availability, authorization or evidence of model quality.',
           '| Planned job | Adapter status | Reason |','| --- | --- | --- |']
    for row in report['execution_eligibility']:
        rows.append('| '+' | '.join((row['job_id'],row['status'],', '.join(row['reasons']) or 'No local contract exclusion'))+' |')
    if report.get('catalog_role_eligibility'):
        rows+=['','Frozen catalog includes exclusions; modalities do not prove structured-output support or current availability.',
            '| Catalog model | Observer | Planner |','| --- | --- | --- |']
        for row in report['catalog_role_eligibility']:
            rows.append('| '+' | '.join((row['model_id'],row['roles']['observer'],row['roles']['planner']))+' |')
    rows+=['','Paired comparisons are room-clustered; unresolved outcomes remain inconclusive.',
           'Costs are estimates, not invoice verification. No physical robot acceptance is claimed.','']
    return '\n'.join(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--authorization',type=Path,required=True);parser.add_argument('--rubric',type=Path)
    parser.add_argument('--visual-reviews',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepared=prepare(args.manifest)
    manifest=checked_manifest(read_json(args.manifest),args.manifest.resolve().parent)
    state=validate(read_json(args.directory/'manifest-campaign.json'),prepared,read_json(args.authorization))
    if args.output.resolve().is_relative_to(args.directory.resolve()):
        raise ValueError('BENCHMARK_DERIVED_REPORT_MUST_NOT_CHANGE_RUN_TREE')
    if args.rubric and prepared['freeze'].get(str(args.rubric.resolve()))!=file_sha(args.rubric):
        raise ValueError('BENCHMARK_RUBRIC_NOT_FROZEN')
    # Hash all local trial/annotation/review inputs before and after evaluation.
    paths=[*args.directory.rglob('*.json'),args.manifest,args.authorization,
        *[Path(c['annotations']['path']) for c in manifest['cases'] if c['annotations']]]
    paths+=([args.rubric] if args.rubric else [])+([args.visual_reviews] if args.visual_reviews else [])
    hashes={p:file_sha(p) for p in paths}
    collected=collector(prepared,state,args.directory,manifest,read_json(args.rubric) if args.rubric else None,
        visual_reviews=read_json(args.visual_reviews) if args.visual_reviews else None)
    report=public_report(collected,prepared)
    if any(file_sha(p)!=digest for p,digest in hashes.items()):raise ValueError('BENCHMARK_SOURCE_CHANGED_DURING_COLLECTION')
    args.output.mkdir(parents=True,exist_ok=False)
    for name,value in (('private-collection.json',collected),('public-summary.json',report)):
        with (args.output/name).open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
    with (args.output/'public-summary.md').open('x',encoding='utf-8') as stream:stream.write(markdown(report))
    print(json.dumps(dict(status='COLLECTED_NO_INFERENCE',planned=len(prepared['jobs']),HTTP=0)))


if __name__=='__main__':main()
