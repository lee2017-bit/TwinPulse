# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only audit of explicit output10000 trials, including late rejected raw.

No credentials or HTTP. A passing audit never changes a failed generation into
a pass. Fresh full pipeline, cached observations and product acceptance differ.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_provider.reliability import CampaignLedger
from twinpulse_core.photo_quality import inspect_photo_geometry
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256


def checked_raw(path,row,*,cap):
    evidence=json.loads(path.read_bytes())
    raw=evidence['response_redacted'].encode('utf-8')
    if (not row.get('finished_at') or evidence['attempt_id']!=row['attempt_id']
            or row['max_tokens']!=cap or evidence['max_tokens']!=cap
            or evidence['response_truncated'] or len(raw)!=evidence['response_byte_count']
            or hashlib.sha256(raw).hexdigest()!=evidence['response_sha256']):
        raise ValueError('OUTPUT_CAP_RAW_OR_SETTLEMENT_MISMATCH')
    response=json.loads(raw)
    if (response['model']!=row['model_id'] or evidence['model_id']!=row['model_id']
            or any(response['usage'].get(k)!=v for k,v in row['usage'].items())):
        raise ValueError('MODEL_USAGE_MISMATCH')
    choice=response['choices'][0]
    return dict(attempt_id=row['attempt_id'],model=row['model_id'],requested_cap=cap,
        finish_reason=choice['finish_reason'],completion_tokens=response['usage']['completion_tokens'],
        content_characters=len(choice['message'].get('content') or ''),elapsed_s=evidence['elapsed_s'],
        late_after_cancellation=bool(evidence.get('cancelled')),raw_sha256=evidence['response_sha256'],
        estimated_usd=row['charged_or_reserved_usd'])


def audit(runs,campaign):
    ledger=CampaignLedger.open_existing_approved(campaign)
    rows={r['attempt_id']:r for r in ledger.state['requests']}
    seen=set();trials=[];raws=[]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for run in runs:
        run=run.resolve()
        if not run.is_relative_to(ROOT/'artifacts'):raise ValueError('ARTIFACT_RUN_REQUIRED')
        report=json.loads((run/'result.json').read_bytes())
        if report.get('output_token_cap')!=10000:raise ValueError('EXPLICIT_OUTPUT10000_REQUIRED')
        product=report.get('provider')=='live_configured_provider'
        if product:
            if report['status']!='PASS' or report['physics']!='actual_local_Isaac':
                raise ValueError('ACTUAL_PRODUCT_PASS_REQUIRED')
            if not report['inference_source_unchanged']:raise ValueError('SOURCE_CHANGED_DURING_PRODUCT')
            for mapping in ('inference_source_at_end','source_sha256','web_sha256'):
                if any(sha(ROOT/p)!=h for p,h in report[mapping].items()):
                    raise ValueError('CURRENT_PRODUCT_SOURCE_CHANGED')
            job=report['browser']['conversation']['generation']['progress']
            ids=[a['attempt_id'] for a in job['attempts']]
            evidence_root=run/'runtime/provider-evidence'
            from twinpulse_app.project_store import ProjectStore
            draft=ProjectStore(run/'runtime/active_project.json').load().site_draft
            quality=inspect_photo_geometry(draft.plan.to_dict(),PHOTO_SHA256)
            if quality['checked_relation_status']!='PASS':raise ValueError('PRODUCT_GEOMETRY_CHANGED')
            trials.append(dict(run=run.name,kind='FRESH_PRODUCT_ACTUAL_ISAAC',success=True,
                first_valid=job['repair_count']==0,repair_count=job['repair_count'],
                arrival_distance_m=report['browser']['arrival']['distance_to_goal_m']))
        else:
            if (report['status'] not in ('COMPLETED_BOUNDED_EVALUATION_NOT_FULL_DEMO','STOPPED_WITH_DIAGNOSTICS')
                    or report['pending_dispatches'] or not report['prior_requests_unchanged']
                    or not report['source_unchanged'] or not report['originals_unchanged']):
                raise ValueError('RUN_UNSETTLED_OR_CHANGED')
            for mapping in ('source_hashes','original_hashes'):
                if any(sha(ROOT/p)!=h for p,h in report[mapping].items()):
                    raise ValueError('CURRENT_SOURCE_OR_ORIGINAL_CHANGED')
            ids=report['new_attempt_ids'];evidence_root=run/'responses'
            for j in report['jobs']:
                success=j['status']!='FAIL'
                if success:
                    quality=inspect_photo_geometry(json.loads((run/(j['name']+'-plan.json')).read_bytes()),PHOTO_SHA256)
                    if quality!=j['quality']:raise ValueError('ACCEPTED_PLAN_CHANGED')
                trials.append(dict(run=run.name,kind='CACHED' if j.get('cached_exact_observer') else
                    'FRESH' if j['count_in_natural_success_rate'] else 'CONTROLLED',
                    policy='off' if report['planner_template_no_thinking'] else 'default',
                    success=success,first_valid=success and j['diagnostics']['repair_count']==0,
                    repair_count=j['diagnostics']['repair_count'],error=j.get('error')))
        if seen.intersection(ids):raise ValueError('DUPLICATE_ACTUAL_CALL')
        seen.update(ids)
        raws.extend(checked_raw(evidence_root/(identity+'.json'),rows[identity],cap=10000) for identity in ids)
    return dict(audit='PASS',trials=trials,raw_checks=raws,new_calls=len(seen),
        new_estimated_usd=str(sum((Decimal(rows[i]['charged_or_reserved_usd']) for i in seen),Decimal(0))),
        campaign_requests=len(rows),max_requests=ledger.state['max_requests'],remaining=ledger.state['max_requests']-len(rows),
        total_estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in rows.values()),Decimal(0))),
        limit_usd=ledger.state['limit_usd'],pending=0,invoice_verified=False,
        full_photo_fidelity='UNVERIFIED',metric_scale='UNVERIFIED',robot_calls=0,whole_demo_ready=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs',nargs='+',type=Path)
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.runs,args.campaign)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('trials','raw_checks')}))
