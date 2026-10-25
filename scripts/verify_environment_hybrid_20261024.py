# SPDX-License-Identifier: Apache-2.0
"""Local device-free focused contracts; retain complete command results."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
environment=dict(os.environ);environment['PYTHONPATH']=os.pathsep.join(str(root/'packages'/p/'src') for p in ('twinpulse_core','twinpulse_provider','twinpulse_app'))
commands=[('python',[str(root/'.venv/Scripts/python.exe'),'-B','-m','unittest',
    'tests.integration.test_environment_overlays','tests.integration.test_environment_import',
    'tests.integration.test_environment_model_move','tests.integration.test_environment_photo','tests.integration.test_stage_routing_settings','tests.integration.test_windows_install',
    'tests.integration.test_scene_edit_transaction','tests.integration.test_saved_scan_geometry','tests.integration.test_live_viewport'],root),
    ('typescript',['pnpm.cmd','exec','tsc','-b','--pretty','false'],root/'apps/twinpulse-web'),
    ('ui',['pnpm.cmd','exec','vitest','run','src/EnvironmentImport.test.tsx','src/PhysicalLidarPanel.test.tsx','src/TwinViewport.test.tsx'],root/'apps/twinpulse-web')]
result=dict(scope='SUPPLEMENTARY_CONTRACTS_NOT_INSTALLED_UI_OR_HARDWARE',runs=[])
for name,command,cwd in commands:
    run=subprocess.run(command,cwd=cwd,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    raw=run.stdout.encode('utf-8');(out/(name+'.log')).write_bytes(raw)
    result['runs'].append(dict(name=name,command=command,exit_code=run.returncode,sha256=hashlib.sha256(raw).hexdigest()))
    print(name,run.returncode,flush=True)
result['status']='PASS' if all(r['exit_code']==0 for r in result['runs']) else 'FAIL'
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
raise SystemExit(0 if result['status']=='PASS' else 1)
