# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""2026-10-09 explicit five-call approval; stop whole batch on output exhaustion."""
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_split_evaluation import nebius_rate,KeyRegistry,JsonProviderSettingsStore,WindowsCredentialStore,NANO,SplitEvaluationLedger
from twinpulse_app.stage_routing import StageRoutingSettings,DEFAULT_OUTPUT_TOKENS

def main():
    root=ROOT/'artifacts/pre-demo-20261009/saved-stage-20000-five'
    root.mkdir(exist_ok=False)
    registry=KeyRegistry(JsonProviderSettingsStore(),WindowsCredentialStore())
    route=StageRoutingSettings(registry).load()
    scope=json.loads((ROOT/'artifacts/pre-demo-20261009/saved-stage-batch/scope.json').read_text(encoding='utf-8'))
    tokens={k:v.get('max_output_tokens',DEFAULT_OUTPUT_TOKENS[k]) for k,v in route.items()}
    assert route['observer']['key_id']==scope['observer_entry_id'] and route['observer']['model_id']=='gpt-5.4-mini'
    assert route['planner']['key_id']==scope['planner_entry_id'] and route['planner']['model_id']==NANO
    assert tokens=={'observer':4000,'planner':20000}
    histories=[ROOT/'artifacts/pre-demo-20261009/saved-stage-batch/campaign.json',
        ROOT/'artifacts/pre-demo-20261009/mixed-corrected-scope/campaign.json']
    preserved={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in histories}
    scope.update(schema_version='configured-stage-evaluation-1.0',
        approval='2026-10-09 user: 다시 실행해서5회까지 테스트. GPT photo/Nebius Nano planner20000, original photo/prompt, stop batch immediately on output exhaustion, actual local Isaac, no robot.',
        campaign_path=str(root/'campaign.json'),max_requests=5,limit_usd='0.15',saved_stage_route=route,stage_output_tokens=tokens)
    scope['rates'][NANO]=nebius_rate(registry,registry.settings_for_entry(route['planner']['key_id']))
    (root/'scope.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2),encoding='utf-8')
    ledger=SplitEvaluationLedger(root/'campaign.json',approval=scope['approval'],rates=scope['rates'],limit_usd='0.15',max_requests=5)
    photo=Path(r'C:\Users\jaewo\.codex\codex-remote-attachments\01a09495-5d9b-7680-8c59-9ac914c939fb\12FCC087-9497-4B2E-B6B1-8AAF54A8F987\1-사진-1.jpg')
    assert hashlib.sha256(photo.read_bytes()).hexdigest()==scope['photo_sha256']
    runs=[];reason='call_limit'
    for i in range(1,4):
        state=json.loads(ledger.path.read_text(encoding='utf-8'));left=5-len(state['requests'])
        if left<2 or ledger.lock_path.exists():break
        out=root/f'run-{i}'
        command=[sys.executable,str(ROOT/'scripts/verify_saved_stage_live.py'),str(out),'--case','image',
            '--live-campaign',str(ledger.path),'--split-provider-scope',str(root/'scope.json'),
            '--live-photo',str(photo),'--live-request-cap',str(min(left,3)),'--diagnostics']
        with (root/f'run-{i}.log').open('x',encoding='utf-8') as stream:
            completed=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        result=json.loads((out/'result.json').read_text(encoding='utf-8')) if (out/'result.json').exists() else {}
        after=json.loads(ledger.path.read_text(encoding='utf-8'))
        used=len(after['requests'])-len(state['requests'])
        runs.append(dict(run=i,status=result.get('status'),calls=used,error=result.get('error'),exit_code=completed.returncode))
        print(json.dumps(runs[-1],ensure_ascii=False),flush=True)
        length=False
        for p in (out/'runtime/provider-evidence').glob('*.json'):
            raw=json.loads(p.read_text(encoding='utf-8')).get('response_redacted')
            if raw and any(c.get('finish_reason')=='length' for c in json.loads(raw).get('choices',[])):length=True
        if length:reason='output_limit_reached';break
        if used==0 or ledger.lock_path.exists() or any(r['status']=='pending' for r in after['requests']):reason='dispatch_blocked';break
        if any(r['status']=='outcome_unknown' for r in after['requests']):reason='outcome_unknown';break
        if result.get('status')=='PASS':reason='success';break
    state=json.loads(ledger.path.read_text(encoding='utf-8'))
    assert len(state['requests'])<=5
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in preserved.items())
    summary=dict(runs=runs,calls=len(state['requests']),max_calls=5,stop_reason=reason,stage_output_tokens=tokens,
        normal_timeout_s=90,compact=False,robot_commands=0,historical_ledger_sha256=preserved,
        estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in state['requests']),Decimal(0))),
        pending=sum(r['status']=='pending' for r in state['requests']),lock_exists=ledger.lock_path.exists())
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
