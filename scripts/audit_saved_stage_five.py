# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Audit the five-call 20000-token run; no network or response modification."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'artifacts/pre-demo-20261009/saved-stage-20000-five'
summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
ledger=json.loads((root/'campaign.json').read_text(encoding='utf-8'))
rows=[];ids=[]
for run in summary['runs']:
    folder=root/f"run-{run['run']}"
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    assert result['browser']['browser_closed'] and result['launcher_shutdown_diagnostics']['status']=='succeeded'
    assert result['supervisor']['status']=='stopped' and result['inference_source_unchanged']
    for file in (folder/'runtime/provider-evidence').glob('*.json'):
        evidence=json.loads(file.read_text(encoding='utf-8'));raw=evidence['response_redacted']
        assert hashlib.sha256(raw.encode()).hexdigest()==evidence['stored_response_sha256']
        response=json.loads(raw);choice=response['choices'][0]
        ids.append(evidence['attempt_id'])
        rows.append(dict(run=run['run'],attempt_id=evidence['attempt_id'],execution_id=evidence['execution_id'],
            model=evidence['model_id'],max_tokens=evidence['max_tokens'],status=evidence['status'],elapsed_s=evidence['elapsed_s'],
            finish=choice['finish_reason'],content_chars=len(choice['message'].get('content') or ''),usage=response['usage']))
assert len(ids)==len(set(ids))==len(ledger['requests'])==5
assert set(ids)=={r['attempt_id'] for r in ledger['requests']}
assert not ledger['max_requests']!=5 and not any(r['status']=='pending' for r in ledger['requests'])
assert not root.joinpath('campaign.dispatch-lock').exists()
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in summary['historical_ledger_sha256'].items())
report=dict(audit='PASS',generation='FAIL',calls=5,max_calls=5,observer=2,initial_planner=2,repair=1,
    output_truncations=sum(r['finish']=='length' for r in rows),late_rejected=sum(r['status']=='rejected' for r in rows),
    estimated_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests']),Decimal(0))),
    pending=0,dispatch_lock=False,owned_cleanup='PASS',old_ledgers_unchanged=True,robot_commands=0,rows=rows)
(root/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
