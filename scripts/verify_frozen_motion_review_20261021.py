# SPDX-License-Identifier: Apache-2.0
"""Actual fixed EXE offline role, not App UI/robot/whole-cycle acceptance."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.process_manager import _WindowsJob
from twinpulse_app.windows_package import verify_package
from twinpulse_app.runtime_paths import child_environment

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('NEW_EVIDENCE_REQUIRED')
    package=args.package.resolve();checked=verify_package(package)
    root=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local'
    operation='65fe078b1975404886704c2df728a33f';project='chat_mvcck71j_6d94b13d';job=uuid4().hex
    out=root/'motion-reviews/jobs'/job
    if any(p.is_symlink() for p in (out,*out.parents)):raise ValueError('REVIEW_OUTPUT_PATH')
    out.mkdir(parents=True,exist_ok=False);process=None;owned=None;errors=[];code=None;began=time.monotonic()
    try:
        owned=_WindowsJob('frozen-offline-motion-review-check')
        with (out/'worker.log').open('xb') as log:
            process=subprocess.Popen([str(package/'TwinPulse.exe'),'--internal-role','motion-review','--state-root',str(root),
                '--operation',operation,'--project',project,'--job',job],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                env=child_environment(os.environ),creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            owned.assign(process);code=process.wait(timeout=75)
    except Exception as error:errors.append(type(error).__name__)
    finally:
        if process is not None and process.poll() is None:
            try:process.terminate();process.wait(3)
            except Exception as error:errors.append('REAP_'+type(error).__name__)
        if owned is not None:
            try:owned.close()
            except Exception as error:errors.append('JOB_CLOSE_'+type(error).__name__)
    path=out/'result.json';review=json.loads(path.read_bytes()) if path.is_file() else None
    source=package/'_internal/resources/packages/twinpulse_app/src/twinpulse_app/physical_motion_analysis.py'
    expected=sha256(source.read_bytes()).hexdigest()
    okay=not errors and code==0 and review and review.get('status')=='COMPLETED_WITH_LIMITS' and review.get('input_rows')==42484
    okay=okay and all(review.get(k)==v for k,v in dict(operation_id=operation,project_id=project,job_id=job,
        release_id=checked['build_id'],analyser_source_sha256=expected,physical_motion_verified=False,authority_restored=False,original_logs_rewritten=False).items())
    result=dict(classification='SUPPLEMENTARY_ACTUAL_FIXED_FROZEN_ROLE_NOT_INSTALLED_UI_OR_HARDWARE_ACCEPTANCE',
        status='PASS' if okay else 'FAIL',package=checked,job_id=job,exit_code=code,errors=errors,elapsed_s=time.monotonic()-began,
        review=review,result_file=str(path),result_sha256=sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('review',)}))
    return 0 if okay else 1

if __name__=='__main__':raise SystemExit(main())
