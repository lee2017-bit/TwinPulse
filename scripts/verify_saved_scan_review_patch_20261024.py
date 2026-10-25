# SPDX-License-Identifier: Apache-2.0
"""Focused regression + frozen offline role, no device or App action."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import argparse
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/roomplan-lidar-review-20261024-02'
parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);args=parser.parse_args()
if not re.fullmatch('[0-9]{2}',args.tag):raise ValueError('NEW_TWO_DIGIT_TAG_REQUIRED')
TEST=OUT/('focused-tests'+args.tag);TEST.mkdir()
commands=[([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','unittest',
    'tests.integration.test_saved_scan_geometry','tests.integration.test_physical_motion_review','tests.integration.test_environment_import'],ROOT),
    (['pnpm.cmd','exec','vitest','run','src/EnvironmentImport.test.tsx','src/PhysicalLidarPanel.test.tsx'],ROOT/'apps/twinpulse-web'),
    (['pnpm.cmd','exec','tsc','-b'],ROOT/'apps/twinpulse-web')]
results=[]
for index,(command,cwd) in enumerate(commands):
    completed=subprocess.run(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    log=TEST/f'test-{index}.log';log.write_bytes(completed.stdout)
    results.append(dict(command=command,cwd=str(cwd),return_code=completed.returncode,
        log=log.name,sha256=hashlib.sha256(completed.stdout).hexdigest()))
    if completed.returncode:break
active=json.loads((Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json').read_text(encoding='utf-8-sig'))
exe=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'/active['exe']
state=OUT/('frozen-role-state'+args.tag);op='db929f4ad15e418e88ddd71a85ea55f6';job='02402402402402402402402402402402'
source=ROOT/'outputs/robot-auto-charged-20261024-01/raw'/op
target=state/'physical-live'/op;target.mkdir(parents=True)
originals={}
for f in source.iterdir():
    if f.is_file() and (f.name=='receipt.json' or f.name.startswith('events-')):
        originals[f.name]=hashlib.sha256(f.read_bytes()).hexdigest();os.link(f,target/f.name)
result_dir=state/'motion-reviews/jobs'/job;result_dir.mkdir(parents=True)
command=[str(exe),'--internal-role','motion-review','--state-root',str(state),'--operation',op,
    '--project','chat_mvki3gm9_e212190a','--job',job]
completed=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=75,
    env={**os.environ,'TWINPULSE_RELEASE_ID':active['release_id']},creationflags=subprocess.CREATE_NO_WINDOW)
(TEST/'frozen-worker.log').write_bytes(completed.stdout)
worker=json.loads((result_dir/'result.json').read_text(encoding='utf-8')) if (result_dir/'result.json').exists() else None
unchanged=all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in originals.items())
passed=(all(v['return_code']==0 for v in results) and len(results)==3 and completed.returncode==0 and worker and
    worker.get('analysis_revision')=='2026-10-24.2' and worker.get('status')=='COMPLETED_WITH_LIMITS' and
    worker.get('physical_motion_verified') is False and worker.get('authority_restored') is False and unchanged)
result=dict(status='PASS_SCOPED_OFFLINE_AND_UNIT_NOT_UI_OR_HARDWARE' if passed else 'FAIL',tests=results,
    frozen_role=dict(command=command,return_code=completed.returncode,review_status=worker.get('status') if worker else None,
        analysis_revision=worker.get('analysis_revision') if worker else None,job_id=job,source_release=active['release_id']),
    original_hashes=originals,originals_unchanged=unchanged,devices_accessed=False)
with (TEST/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(dict(status=result['status'],frozen_role=result['frozen_role'])))
raise SystemExit(0 if passed else 1)
