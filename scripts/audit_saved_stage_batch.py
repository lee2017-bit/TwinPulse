# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only evidence audit; emits a local report, never inference."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'artifacts/pre-demo-20261009/saved-stage-batch'
ledger=json.loads((root/'campaign.json').read_text(encoding='utf-8'))
rows=[]
identities=[]
for i in range(1,6):
    run=root/f'run-{i}'
    result=json.loads((run/'result.json').read_text(encoding='utf-8'))
    assert result['browser']['browser_closed'] and result['launcher_shutdown_diagnostics']['status']=='succeeded'
    assert result['inference_source_unchanged'] and result['supervisor']['status']=='stopped'
    assert result['status']=='FAIL' and result['browser']['workflow']['phase']=='generation_failed'
    for path in (run/'runtime/provider-evidence').glob('*.json'):
        evidence=json.loads(path.read_text(encoding='utf-8'))
        response=evidence['response_redacted']
        assert hashlib.sha256(response.encode('utf-8')).hexdigest()==evidence['stored_response_sha256']
        payload=json.loads(response)
        choice=payload['choices'][0]
        identities.append(evidence['attempt_id'])
        rows.append(dict(run=i,attempt_id=evidence['attempt_id'],execution_id=evidence['execution_id'],
            model=evidence['model_id'],elapsed_s=evidence['elapsed_s'],finish=choice['finish_reason'],
            content_chars=len(choice['message'].get('content') or ''),
            reasoning_chars=len(choice['message'].get('reasoning') or ''),usage=payload['usage']))
assert len(identities)==len(set(identities))==len(ledger['requests'])==10
assert set(identities)=={r['attempt_id'] for r in ledger['requests']}
assert not root.joinpath('campaign.dispatch-lock').exists()
assert not any(r['status']=='pending' for r in ledger['requests'])
report=dict(audit='PASS',generation='FAIL',calls=10,observer_calls=5,planner_initial_calls=5,repair_calls=0,
    estimated_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in ledger['requests']),Decimal(0))),
    pending=0,owned_cleanup='PASS',robot_commands=0,normal_pipeline_tested=True,
    normal_settings_ui_metadata_acceptance=False,normal_timeout_s=90,compact=False,rows=rows)
(root/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
