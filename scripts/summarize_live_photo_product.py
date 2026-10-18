# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only live-photo product audit; no HTTP, credentials or robot access.

Writes one new exclusive analysis file, never edits the original run or ledger.
PASS is limited to checked proxy geometry and the actual recorded SIM journey.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.project_store import ProjectStore
from twinpulse_core.photo_quality import inspect_photo_geometry
from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256
from twinpulse_core.revisions import canonical_sha256


def checked_generation_progress(saved,report,quality):
    # Chat action IDs and provider request IDs are different namespaces. Bind
    # the stored provider ID to the product draft, and the generation to its
    # accepted canonical plan/constraints plus all actual HTTP attempt IDs.
    progress=report['browser']['conversation']['generation']['progress']
    draft=report['browser']['workflow']['site_draft']
    last=progress['attempts'][-1]
    if (draft['request_id']!=saved.request_id or progress['status']!='validated'
            or last['validation']!='passed'
            or type(progress['repair_count']) is not int or progress['repair_count'] not in (0,1)
            or last['photo_quality']['plan_sha256']!=saved.plan_sha256
            or last['photo_quality']['constraints_sha256']!=quality['constraints_sha256']):
        raise ValueError('PRODUCT_GENERATION_INPUT_OR_ACCEPTED_PLAN_PROVENANCE_MISMATCH')
    return progress


def audit(run,campaign):
    run,campaign=run.resolve(),campaign.resolve()
    if not run.is_relative_to(ROOT/'artifacts') or not campaign.is_relative_to(ROOT/'artifacts'):
        raise ValueError('LOCAL_ARTIFACT_RUN_AND_CAMPAIGN_REQUIRED')
    original=(run/'result.json').read_bytes()
    report=json.loads(original)
    if (report.get('status')!='PASS' or report.get('provider')!='live_configured_provider'
            or report.get('photo_inference')!='LIVE' or report.get('physics')!='actual_local_Isaac'
            or report.get('experimental_compact_photo') is not True
            or report.get('production_default') is not False or report.get('physical_authority') is not False
            or report.get('robot_connections')!=0 or report['browser']['status']!='PASS'):
        raise ValueError('ACTUAL_LIVE_PHOTO_SIM_PRODUCT_PASS_REQUIRED')
    source=report['inference_source_at_start']
    if (source!=report['inference_source_at_end'] or report['inference_source_unchanged'] is not True
            or any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in source.items())
            or any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in report['source_sha256'].items())
            or any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in report['web_sha256'].items())):
        raise ValueError('PRODUCT_SOURCE_OR_BUILD_CHANGED')
    if any(report['supervisor'][key].get('owned') for key in ('backend','engine')):
        raise ValueError('OWNED_PROCESS_CLEANUP_NOT_CONFIRMED')
    ledger=json.loads(campaign.read_bytes())
    rows={r['attempt_id']:r for r in ledger['requests']}
    paths=list((run/'runtime/provider-evidence').glob('*.json'))
    if not 1<=len(paths)<=5:raise ValueError('HOST_RUN_REQUEST_CAP_EXCEEDED_OR_MISSING')
    raw_audits=[]
    for path in sorted(paths):
        if not re.fullmatch(r'[a-f0-9]{32}',path.stem):raise ValueError('INVALID_ATTEMPT_FILE')
        facts=json.loads(path.read_bytes())
        row=rows[path.stem]
        raw=facts['response_redacted'].encode('utf-8')
        payload=json.loads(raw)
        if (facts['attempt_id']!=row['attempt_id'] or facts['response_truncated']
                or hashlib.sha256(raw).hexdigest()!=facts['response_sha256']
                or len(raw)!=facts['response_byte_count'] or not row.get('finished_at')
                or row['status']=='outcome_unknown' or payload['model']!=row['model_id']
                or any(payload['usage'].get(k)!=v for k,v in row['usage'].items())):
            raise ValueError('ACTUAL_RAW_MODEL_USAGE_OR_LEDGER_MISMATCH')
        raw_audits.append(dict(attempt_id=path.stem,model=row['model_id'],status=row['status'],
            finish_reason=payload['choices'][0]['finish_reason'],elapsed_s=facts['elapsed_s'],
            usage=row['usage'],raw_sha256=facts['response_sha256'],raw_bytes=len(raw)))
    saved=ProjectStore(run/'runtime/active_project.json').load().site_draft
    expected=report['browser']['compact_inventory']
    if (saved.input_revision.images[0]['sha256']!=PHOTO_SHA256
            or saved.plan_sha256!=expected['plan_sha256']
            or saved.input_revision.digest!=expected['input_revision']
            or canonical_sha256(saved.plan.to_dict())!=saved.plan_sha256
            or report['saved_project_reopen']['items']!=24):
        raise ValueError('SAVED_INPUT_PLAN_OR_REOPEN_CHANGED')
    recorded=report['browser']['conversation']['generation']['progress']['photo_quality']
    constraints=reviewed_photo_constraints(PHOTO_SHA256,
        semantic_review=recorded.get('review_revision')=='photo-semantic-review-1.0')
    if recorded.get('review_revision')=='photo-semantic-review-1.0' and recorded.get('scale_review_limit_m2') is None:
        from dataclasses import replace
        constraints=replace(constraints,max_estimated_area_m2=None)
    quality=inspect_photo_geometry(saved.plan.to_dict(),PHOTO_SHA256,constraints)
    if quality['checked_relation_status']!='PASS' or quality['status']!='PARTIAL':
        raise ValueError('CHECKED_PROXY_GEOMETRY_RECHECK_FAILED')
    # Attempts live in generation progress, not SiteDraftRecord serialization.
    progress=checked_generation_progress(saved,report,quality)
    attempts=progress['attempts']
    if {r['attempt_id'] for r in raw_audits}!={a['attempt_id'] for a in attempts}:
        raise ValueError('ACCEPTED_PRODUCT_PROVENANCE_DOES_NOT_BIND_ALL_HTTP_ATTEMPTS')
    arrival=report['browser']['arrival']
    if (arrival['runtime_state']!='completed' or not arrival['telemetry_available']
            or arrival['distance_to_goal_m']>.05 or not report['browser']['frames']):
        raise ValueError('ACTUAL_SIM_ARRIVAL_OR_CURRENT_FRAME_MISSING')
    analysis=dict(schema_version='live-photo-product-analysis-1.0',status='PASS',
        original_result_sha256=hashlib.sha256(original).hexdigest(),new_actual_calls=len(paths),
        request_ids=[r['attempt_id'] for r in raw_audits],raw_audits=raw_audits,
        new_estimated_usd=str(sum((Decimal(rows[r['attempt_id']]['charged_or_reserved_usd'])
                                 for r in raw_audits),Decimal(0))),invoice_verified=False,
        repair_count=progress['repair_count'],quality=quality,
        saved_plan_sha256=saved.plan_sha256,input_revision=saved.input_revision.digest,
        current_isaac_frames=len(report['browser']['frames']),arrival_distance_m=arrival['distance_to_goal_m'],
        checks=report['browser']['checks'],source_and_build_unchanged=True,owned_processes_closed=True,
        metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS',full_photo_reconstruction='UNVERIFIED',
        physical_validation='NOT_RUN',production_default=False,whole_demo_ready=False)
    with (run/'post-run-analysis.json').open('x',encoding='utf-8') as stream:
        json.dump(analysis,stream,ensure_ascii=False,indent=2)
    if (run/'result.json').read_bytes()!=original:raise AssertionError('ORIGINAL_RESULT_CHANGED')
    print(json.dumps(dict(audit='PASS',new_actual_calls=len(paths),repair_count=analysis['repair_count'],
        new_estimated_usd=analysis['new_estimated_usd'],current_isaac_frames=analysis['current_isaac_frames'],
        arrival_distance_m=analysis['arrival_distance_m'],checked_geometry='PASS',full_photo_fidelity='UNVERIFIED')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--campaign',type=Path,required=True)
    args=parser.parse_args()
    audit(args.run,args.campaign)
