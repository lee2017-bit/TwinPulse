# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only audit of a completed bounded live run; writes new analysis only."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
from twinpulse_core.photo_quality import inspect_photo_geometry
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256


def audit(run):
    path = run / 'result.json'
    original = path.read_bytes()
    report = json.loads(original.decode('utf-8'))
    if report['status'] != 'COMPLETED_BOUNDED_EVALUATION_NOT_FULL_DEMO':
        raise ValueError('COMPLETED_RUN_REQUIRED')
    ledger = json.loads((ROOT / 'artifacts/agent-reliability-20261007/campaign.json').read_text(encoding='utf-8'))
    rows = {r['attempt_id']: r for r in ledger['requests']}
    raw_audits = []
    for identity in report['new_attempt_ids']:
        evidence = json.loads((run / 'responses' / (identity + '.json')).read_text(encoding='utf-8'))
        raw = evidence['response_redacted'].encode('utf-8')
        if (hashlib.sha256(raw).hexdigest() != evidence['response_sha256']
                or len(raw) != evidence['response_byte_count'] or evidence['response_truncated']
                or not rows[identity].get('finished_at')):
            raise ValueError('INFERENCE_EVIDENCE_HASH_LENGTH_OR_COMPLETION_MISMATCH')
        body = json.loads(raw.decode('utf-8'))
        choice = body['choices'][0]
        # Product accounting keeps numeric counters, not optional API null fields.
        numeric_usage = rows[identity]['usage']
        if (body['model'] != evidence['model_id'] or any(
                body['usage'].get(key) != value for key, value in numeric_usage.items())):
            raise ValueError('INFERENCE_MODEL_USAGE_MISMATCH')
        raw_audits.append(dict(attempt_id=identity, model=evidence['model_id'], status=evidence['status'],
            finish_reason=choice['finish_reason'], elapsed_s=evidence['elapsed_s'], usage=body['usage'],
            content_characters=len(choice['message'].get('content') or ''),
            exact_raw_sha256=evidence['response_sha256'], raw_byte_count=len(raw),
            reason_for_unreturned_output='UNKNOWN_NOT_PROVEN_AS_REASONING_OR_NETWORK'))
    natural = [j for j in report['jobs'] if j['count_in_natural_success_rate']]
    controlled = [j for j in report['jobs'] if not j['count_in_natural_success_rate']]
    accepted = []
    for job in report['jobs']:
        if job['status'] == 'FAIL':
            continue
        candidate_path = run / (job['name'] + '-plan.json')
        candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
        quality = inspect_photo_geometry(candidate, PHOTO_SHA256)
        if quality != job['quality'] or quality['checked_relation_status'] != 'PASS':
            raise ValueError('SAVED_ACCEPTED_PLAN_QUALITY_MISMATCH')
        accepted.append(dict(name=job['name'], plan_sha256=quality['plan_sha256'], quality=quality,
            source=('ACTUAL_REPAIR_OF_CONTROLLED_NEGATIVE_NOT_NATURAL_FULL_PIPELINE_SUCCESS'
                if not job['count_in_natural_success_rate'] else
                'FRESH_ACTUAL_PLANNER_WITH_EXACT_CACHED_OBSERVER' if job.get('cached_exact_observer') else
                'FRESH_ACTUAL_FULL_PIPELINE')))
    analysis = dict(schema_version='photo-geometry-live-analysis-1.0',
        original_result_sha256=hashlib.sha256(original).hexdigest(),
        new_actual_calls=len(raw_audits), natural_full_pipeline=dict(
            successes=sum(j['status'] != 'FAIL' for j in natural if not j.get('cached_exact_observer')),
            trials=sum(not j.get('cached_exact_observer') for j in natural),
            stable_success_rate_established=False),
        fresh_planner_cached_observer=dict(
            successes=sum(j['status'] != 'FAIL' for j in natural if j.get('cached_exact_observer')),
            trials=sum(bool(j.get('cached_exact_observer')) for j in natural)),
        controlled_trials=[dict(name=j['name'], status=j['status'], error=j.get('error'),
            repair_count=j['diagnostics']['repair_count'], elapsed_s=j['elapsed_s']) for j in controlled],
        accepted_saved_plan_rechecks=accepted, raw_audits=raw_audits,
        new_estimated_usd=str(sum((Decimal(rows[i]['charged_or_reserved_usd']) for i in report['new_attempt_ids']), Decimal(0))),
        source_unchanged_now=all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
            for p, h in report['source_hashes'].items()),
        originals_unchanged_now=all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
            for p, h in report['original_hashes'].items()),
        metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS', full_photo_reconstruction='UNVERIFIED',
        isaac='NOT_RUN', physical_validation='NOT_RUN', whole_demo_ready=False)
    if len(raw_audits) != report['new_calls'] or not analysis['source_unchanged_now'] or not analysis['originals_unchanged_now']:
        raise ValueError('COUNT_OR_PRESERVATION_MISMATCH')
    with (run / 'post-run-analysis.json').open('x', encoding='utf-8') as stream:
        json.dump(analysis, stream, ensure_ascii=False, indent=2)
    if path.read_bytes() != original:
        raise AssertionError('ORIGINAL_RESULT_CHANGED')
    print(json.dumps(dict(audit='PASS', new_actual_calls=len(raw_audits),
        natural_successes=analysis['natural_full_pipeline']['successes'],
        natural_trials=analysis['natural_full_pipeline']['trials'],
        cached_planner=analysis['fresh_planner_cached_observer'],
        controlled_accepted=sum(not j['count_in_natural_success_rate'] and j['status'] != 'FAIL' for j in report['jobs']),
        new_estimated_usd=analysis['new_estimated_usd'],
        source_unchanged=True, originals_unchanged=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    audit(parser.parse_args().run.resolve())
