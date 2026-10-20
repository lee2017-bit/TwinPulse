# SPDX-License-Identifier: Apache-2.0
"""Scoped supplementary checks; no device, provider or UI substitution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/timing-recommendation-actions-20261020'
if len(sys.argv)>1:OUT=OUT/sys.argv[1]

def run(item):
    name,command,cwd=item
    p=subprocess.run(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    raw=p.stdout;path=OUT/(name+'.log');path.write_bytes(raw)
    return dict(name=name,exit_code=p.returncode,status='PASS' if p.returncode==0 else 'FAIL',log=str(path),sha256=hashlib.sha256(raw).hexdigest())

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);py=str(ROOT/'.venv/Scripts/python.exe');web=ROOT/'apps/twinpulse-web'
    commands=[('store-api',[py,'-m','unittest','tests.integration.test_robot_timing_settings','tests.integration.test_r5_product_api.R5ProductApiTests.test_only_data_only_robot_settings_can_save_before_isaac_is_ready','-v'],ROOT),
        ('registry-session',[py,'-m','unittest','tests.integration.test_robot_registry_binding','tests.integration.test_physical_live_session','tests.integration.test_physical_fleet_adapter','-q'],ROOT),
        ('timing-core',[py,'-m','unittest','discover','-s','packages/twinpulse_robot_safety/tests','-p','test_robot_timing_profile.py','-v'],ROOT),
        ('ui',[str(web/'node_modules/.bin/vitest.cmd'),'run','src/RobotTimingSettings.test.tsx','src/RobotRegistry.test.tsx','src/RobotFleet.test.tsx','src/api.test.ts'],web),
        ('types',[str(web/'node_modules/.bin/tsc.cmd'),'-b'],web)]
    with ThreadPoolExecutor(max_workers=3) as pool:checks=list(pool.map(run,commands))
    (OUT/'supplementary.json').write_text(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),checks=checks,scope='Supplementary only; no physical/runtime qualification'),indent=2),encoding='utf-8')
    print(json.dumps(checks));raise SystemExit(0 if all(r['exit_code']==0 for r in checks) else 1)
