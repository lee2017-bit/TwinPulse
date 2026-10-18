# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only role comparison audit; never dispatch inference or change source evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def audit(root: Path):
    scope = read(root / 'scope.json')
    summary = read(root / ('summary-final.json' if (root / 'summary-final.json').exists() else 'summary.json'))
    ledgers = {p: read(root / (p + '.ledger.json')) for p in ('nebius', 'openai')}
    entries = {r['attempt_id']: r for ledger in ledgers.values() for r in ledger['requests']}
    seen, errors, groups = set(), [], defaultdict(list)
    missing_execution_ids = []
    for row in summary['results']:
        directory = root / 'cases' / row['case_id']
        if (directory.with_name(directory.name + '-hostfix') / 'result.json').exists():
            original = read(directory / 'result.json')
            if original['actual_calls']:
                errors.append('Actual result replaced by host-fix: ' + row['case_id'])
            directory = directory.with_name(directory.name + '-hostfix')
        persisted = read(directory / 'result.json')
        if persisted != row:
            errors.append('Summary/result mismatch: ' + row['case_id'])
        cost = Decimal(0)
        for attempt in row['attempt_ids']:
            if attempt in seen:
                errors.append('Duplicate attempt: ' + attempt)
            seen.add(attempt)
            raw = read(directory / 'evidence' / (attempt + '.json'))
            charged = entries.get(attempt)
            if not charged:
                errors.append('Missing ledger attempt: ' + attempt)
                continue
            cost += Decimal(charged['charged_or_reserved_usd'])
            if raw['model_id'] != row['model_id']:
                errors.append('Model identity mismatch: ' + attempt)
            if raw['max_tokens'] != 20000:
                errors.append('Output limit mismatch: ' + attempt)
            if raw.get('execution_id') not in (None, row['execution_id']):
                errors.append('Execution identity mismatch: ' + attempt)
            if not raw.get('execution_id'):
                missing_execution_ids.append(attempt)
            stored = raw.get('response_redacted')
            if stored is not None and raw.get('stored_response_sha256') != hashlib.sha256(stored.encode('utf-8')).hexdigest():
                errors.append('Stored response SHA mismatch: ' + attempt)
            dispatch = directory / 'evidence' / 'dispatches' / (attempt + '.json')
            if not dispatch.is_file():
                errors.append('Missing dispatch: ' + attempt)
            if not list((directory / 'evidence' / 'validations').glob(attempt + '-*.json')):
                errors.append('Missing validation: ' + attempt)
        if cost != Decimal(row['estimated_or_reserved_usd']):
            errors.append('Per-case cost mismatch: ' + row['case_id'])
        groups[(row['provider'], row['model_id'], row['role'])].append(row)
    if seen != set(entries):
        errors.append('Ledger/result request-set mismatch')
    table = []
    for (provider, model, role), rows in sorted(groups.items()):
        quality = [i for r in rows for i in ((r.get('diagnostic') or {}).get('quality_review') or {}).get('issues', [])]
        rollback_warnings = []
        for row in rows:
            directory = root / 'cases' / row['case_id']
            if (directory.with_name(directory.name + '-hostfix') / 'result.json').exists():
                directory = directory.with_name(directory.name + '-hostfix')
            if 'UNMAPPED_COMPILER_ERROR' not in row.get('error', ''):
                continue
            for path in (directory / 'generation-store' / 'checkpoint').glob('*.json'):
                checkpoint = read(path)['payload']
                previous = checkpoint.get('best_diagnosis') or {}
                current = (checkpoint.get('working_branch') or {}).get('diagnosis') or {}
                if current.get('issues') and not previous.get('issues'):
                    rollback_warnings.append(dict(case_id=row['case_id'],
                        original_issue_codes=[i['code'] for i in current['issues']],
                        original_repairable=all(i.get('repairable') is True for i in current['issues']),
                        saved_best_issues=0,
                        classification='HOST_ROLLBACK_TO_EMPTY_DIAGNOSIS'))
        table.append(dict(provider=provider, model_id=model, role=role,
            pass_count=sum(r['status'] == 'PASS' for r in rows),
            actual_trials=sum(r['actual_calls'] > 0 for r in rows), planned_trials=2,
            mean_elapsed_s=round(sum(r['elapsed_s'] for r in rows) / len(rows), 3),
            actual_calls=sum(r['actual_calls'] for r in rows),
            estimated_or_reserved_usd=str(sum((Decimal(r['estimated_or_reserved_usd']) for r in rows), Decimal(0))),
            failures=dict(Counter(r['failure_code'] for r in rows if r['status'] != 'PASS')),
            rollback_diagnosis_warnings=rollback_warnings,
            quality_issue_codes=dict(Counter(i['code'] for i in quality)),
            execution_ids=[r['execution_id'] for r in rows]))
    return dict(status=summary['status'], stop_reason=summary['stop_reason'],
        finished_cases=summary['finished_cases'], planned_cases=summary['planned_cases'],
        source_hashes=dict(photo=scope['photo_sha256'], observation=scope['observation_sha256']),
        financial=summary['financial'], audit_errors=errors, table=table,
        actual_attempt_count=len(seen), directly_bound_execution_count=len(seen)-len(missing_execution_ids),
        case_attempt_join_only=missing_execution_ids,
        isaac='NOT_RUN', render_accuracy='NOT_MEASURED', metric_accuracy='NOT_MEASURED',
        whole_demo_pass=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, help='New derived JSON report; exclusive create only')
    args = parser.parse_args()
    result = audit(args.root.resolve())
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({k: result[k] for k in ('status', 'stop_reason', 'finished_cases', 'planned_cases',
            'audit_errors', 'actual_attempt_count', 'directly_bound_execution_count')}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result['audit_errors']))
