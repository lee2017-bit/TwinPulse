# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current explicit ten-call approval; preserve previous ledgers and normal policy."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_split_evaluation import nebius_rate, KeyRegistry, JsonProviderSettingsStore, WindowsCredentialStore, NANO, SplitEvaluationLedger
from twinpulse_app.stage_routing import StageRoutingSettings

root = ROOT/'artifacts/pre-demo-20261009/saved-stage-batch'
root.mkdir(exist_ok=False)
registry = KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore())
route = StageRoutingSettings(registry).load()
scope = json.loads((ROOT/'artifacts/pre-demo-20261009/mixed-corrected-scope/scope.json').read_text(encoding='utf-8'))
if route != dict(observer=dict(key_id=scope['observer_entry_id'], model_id='gpt-5.4-mini'),
        planner=dict(key_id=scope['planner_entry_id'],model_id=NANO)):
    raise RuntimeError('Saved stage route mismatch; no call')
scope.update(approval='2026-10-09 user: 테스트10회; reboot local restart; saved GPT photo and Nebius NVIDIA planning/repair, original photo and prompt, no robot.',
    campaign_path=str(root/'campaign.json'),limit_usd='0.15',max_requests=10)
scope['rates'][NANO] = nebius_rate(registry, registry.settings_for_entry(route['planner']['key_id']))
(root/'scope.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2),encoding='utf-8')
ledger = SplitEvaluationLedger(root/'campaign.json',approval=scope['approval'],rates=scope['rates'],limit_usd='0.15',max_requests=10)
photo = Path(r'C:\Users\jaewo\.codex\codex-remote-attachments\01a09495-5d9b-7680-8c59-9ac914c939fb\12FCC087-9497-4B2E-B6B1-8AAF54A8F987\1-사진-1.jpg')
if hashlib.sha256(photo.read_bytes()).hexdigest() != scope['photo_sha256']:raise RuntimeError('Photo changed')
runs=[]
for i in range(1,6):
    state=json.loads(ledger.path.read_text(encoding='utf-8'))
    left=10-len(state['requests'])
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
    runs.append(dict(run=i,exit_code=completed.returncode,status=result.get('status'),calls=used,error=result.get('error')))
    print(json.dumps(runs[-1],ensure_ascii=False),flush=True)
    # Output exhaustion must end the entire batch, not just this generation.
    evidence_dir=out/'runtime/provider-evidence'
    if any(json.loads(json.loads(p.read_text(encoding='utf-8'))['response_redacted'])
           .get('choices',[{}])[0].get('finish_reason')=='length' for p in evidence_dir.glob('*.json')):
        break
    if used==0 or ledger.lock_path.exists() or any(r['status']=='pending' for r in after['requests']):break
    if result.get('status')=='PASS':break
state=json.loads(ledger.path.read_text(encoding='utf-8'))
summary=dict(runs=runs,calls=len(state['requests']),max_calls=10,normal_timeout_s=90,compact=False,robot_commands=0,
    pending=sum(r['status']=='pending' for r in state['requests']),lock_exists=ledger.lock_path.exists())
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False),flush=True)
