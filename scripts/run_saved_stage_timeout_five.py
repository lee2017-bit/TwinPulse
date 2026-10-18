# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit 2026-10-09 renewed five-call approval, saved 300s ordinary service.

Separate immutable-output scope/ledger. No robot, fixture or implicit retry.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_split_evaluation import nebius_rate, KeyRegistry, JsonProviderSettingsStore, WindowsCredentialStore, NANO, SplitEvaluationLedger
from twinpulse_app.stage_routing import StageRoutingSettings, DEFAULT_OUTPUT_TOKENS
from twinpulse_app.split_evaluation import load_evaluation_scope


def main():
    root = ROOT/'artifacts/pre-demo-20261009/saved-stage-300s-five'
    root.mkdir(exist_ok=False)
    registry = KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore())
    route = StageRoutingSettings(registry).load()
    scope = json.loads((ROOT/'artifacts/pre-demo-20261009/saved-stage-20000-five/scope.json').read_text(encoding='utf-8'))
    tokens = {stage:route[stage].get('max_output_tokens', DEFAULT_OUTPUT_TOKENS[stage]) for stage in ('observer','planner')}
    assert route['observer']['key_id'] == scope['observer_entry_id'] and route['observer']['model_id'] == 'gpt-5.4-mini'
    assert route['planner']['key_id'] == scope['planner_entry_id'] and route['planner']['model_id'] == NANO
    assert tokens == {'observer':4000,'planner':20000} and route.get('generation_timeout_s') == 300
    preserved_paths = [ROOT/'artifacts/pre-demo-20261009'/folder/'campaign.json' for folder in
        ('saved-stage-20000-five','saved-stage-batch','mixed-corrected-scope')]
    preserved = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in preserved_paths}
    settings_paths = (registry.settings.path, registry.path, StageRoutingSettings(registry).path)
    settings_sha = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in settings_paths}
    scope.update(approval='2026-10-09 user: 재실행하고 테스트5회까지만. Existing approved bedroom photo to GPT observer, Nebius NVIDIA Nano planning/repair, saved300s/photo4000/planner20000, stop immediately on output exhaustion; actual local Isaac SIM only, no robot.',
        campaign_path=str((root/'campaign.json').resolve()), max_requests=5, saved_stage_route=route,
        generation_timeout_s=300, stage_output_tokens=tokens)
    scope['rates'][NANO] = nebius_rate(registry, registry.settings_for_entry(route['planner']['key_id']))
    with (root/'scope.json').open('x',encoding='utf-8') as stream:
        json.dump(scope,stream,ensure_ascii=False,indent=2)
    ledger = SplitEvaluationLedger(root/'campaign.json',approval=scope['approval'],rates=scope['rates'],limit_usd='0.15',max_requests=5)
    load_evaluation_scope(root/'scope.json',ledger.path,request_cap=3)
    photo = Path(r'C:\Users\jaewo\.codex\codex-remote-attachments\01a09495-5d9b-7680-8c59-9ac914c939fb\12FCC087-9497-4B2E-B6B1-8AAF54A8F987\1-사진-1.jpg')
    assert hashlib.sha256(photo.read_bytes()).hexdigest() == scope['photo_sha256']
    runs = []; reason = 'call_limit'
    print(json.dumps(dict(status='APPROVED_SCOPE_READY',max_calls=5,total_timeout_s=300,stage_output_tokens=tokens,robot_commands=0)),flush=True)
    for i in range(1,4):
        state = json.loads(ledger.path.read_text(encoding='utf-8')); left = 5-len(state['requests'])
        if left < 2 or ledger.lock_path.exists() or any(r['status'] in {'pending','outcome_unknown'} for r in state['requests']):
            break
        out = root/f'run-{i}'
        command = [sys.executable,str(ROOT/'scripts/verify_saved_stage_live.py'),str(out),'--case','image',
            '--live-campaign',str(ledger.path),'--split-provider-scope',str(root/'scope.json'),
            '--live-photo',str(photo),'--live-request-cap',str(min(left,3)),'--live-timeout-s','300','--diagnostics']
        with (root/f'run-{i}.log').open('x',encoding='utf-8') as stream:
            completed = subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        result = json.loads((out/'result.json').read_text(encoding='utf-8')) if (out/'result.json').exists() else {}
        after = json.loads(ledger.path.read_text(encoding='utf-8')); used = len(after['requests'])-len(state['requests'])
        runs.append(dict(run=i,status=result.get('status'),calls=used,error=result.get('error'),exit_code=completed.returncode))
        print(json.dumps(runs[-1],ensure_ascii=False),flush=True)
        length = False
        for p in (out/'runtime/provider-evidence').glob('*.json'):
            raw = json.loads(p.read_text(encoding='utf-8')).get('response_redacted')
            if raw and any(c.get('finish_reason')=='length' for c in json.loads(raw).get('choices',[])):
                length = True
        if length: reason='output_limit_reached'; break
        if used == 0 or ledger.lock_path.exists() or any(r['status']=='pending' for r in after['requests']):
            reason='dispatch_blocked'; break
        if any(r['status']=='outcome_unknown' for r in after['requests']): reason='outcome_unknown'; break
        if result.get('status') == 'PASS': reason='success'; break
        if (not result.get('browser',{}).get('browser_closed')
                or result.get('launcher_shutdown_diagnostics',{}).get('status') != 'succeeded'
                or result.get('supervisor',{}).get('status') != 'stopped'):
            reason='cleanup_failed'; break
    state = json.loads(ledger.path.read_text(encoding='utf-8'))
    assert len(state['requests']) <= 5
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in {**preserved,**settings_sha}.items())
    summary = dict(runs=runs,calls=len(state['requests']),max_calls=5,stop_reason=reason,
        stage_output_tokens=tokens,normal_timeout_s=300,compact=False,robot_commands=0,
        historical_ledger_sha256=preserved,saved_settings_sha256=settings_sha,
        estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in state['requests']),Decimal(0))),
        pending=sum(r['status']=='pending' for r in state['requests']),lock_exists=ledger.lock_path.exists())
    with (root/'summary.json').open('x',encoding='utf-8') as stream:
        json.dump(summary,stream,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
