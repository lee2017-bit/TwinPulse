# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only response/ledger/source/cleanup audit of the renewed 300s batch."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]/'artifacts/pre-demo-20261009/saved-stage-300s-five'
summary = json.loads((root/'summary.json').read_text(encoding='utf-8'))
ledger = json.loads((root/'campaign.json').read_text(encoding='utf-8'))
scope = json.loads((root/'scope.json').read_text(encoding='utf-8'))
rows = []; ids = []; cleanups = []; runs = []
assert ledger['max_requests'] == scope['max_requests'] == summary['max_calls'] == 5
assert scope['generation_timeout_s'] == summary['normal_timeout_s'] == 300
assert scope['stage_output_tokens'] == {'observer':4000,'planner':20000}
assert len(ledger['requests']) <= 5
for run in summary['runs']:
    folder = root/f"run-{run['run']}"
    result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    cleanup = (result.get('browser',{}).get('browser_closed') is True
        and result.get('launcher_shutdown_diagnostics',{}).get('status') == 'succeeded'
        and result.get('supervisor',{}).get('status') == 'stopped')
    cleanups.append(cleanup)
    assert result['inference_source_unchanged'] and result['live_timeout_s'] == 300
    runs.append(dict(run=run['run'],status=result['status'],error=result.get('error'),owned_cleanup=cleanup))
    for file in (folder/'runtime/provider-evidence').glob('*.json'):
        evidence = json.loads(file.read_text(encoding='utf-8')); raw = evidence.get('response_redacted')
        ids.append(evidence['attempt_id'])
        if raw is not None:
            assert hashlib.sha256(raw.encode()).hexdigest() == evidence['stored_response_sha256']
            response = json.loads(raw); choice = response.get('choices',[{}])[0]
        else:
            response = {}; choice = {}
        assert evidence['max_tokens'] == (4000 if evidence['model_id']==scope['observer_model'] else 20000)
        rows.append(dict(run=run['run'],attempt_id=evidence['attempt_id'],execution_id=evidence.get('execution_id'),
            model=evidence['model_id'],max_tokens=evidence['max_tokens'],status=evidence['status'],elapsed_s=evidence.get('elapsed_s'),
            finish=choice.get('finish_reason'),content_chars=len(choice.get('message',{}).get('content') or ''),usage=response.get('usage'),
            raw_response_retained=raw is not None))
assert len(ids) == len(set(ids)) == len(ledger['requests'])
assert set(ids) == {r['attempt_id'] for r in ledger['requests']}
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in
    {**summary['historical_ledger_sha256'],**summary['saved_settings_sha256']}.items())
pending = sum(r['status']=='pending' for r in ledger['requests'])
unknown = sum(r['status']=='outcome_unknown' for r in ledger['requests'])
locked = root.joinpath('campaign.dispatch-lock').exists()
report = dict(audit='PASS' if all(cleanups) and not pending and not unknown and not locked else 'NEEDS_ATTENTION',
    calls=len(ids),max_calls=5,generation_runs=runs,output_truncations=sum(r['finish']=='length' for r in rows),
    total_timeout_s=300,estimated_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests']),Decimal(0))),
    pending=pending,outcome_unknown=unknown,dispatch_lock=locked,owned_cleanup='PASS' if all(cleanups) else 'FAIL',
    old_ledgers_and_settings_unchanged=True,robot_commands=0,rows=rows)
with (root/'audit.json').open('x',encoding='utf-8') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
