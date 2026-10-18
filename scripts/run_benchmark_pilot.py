# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Serial continuation of a frozen, separately authorized actual campaign.

No new grants/retries or orphan/foreign lock deletion. The existing controller
does financial/environment/source admission and audited reservation settlement.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import prepare,read_json
from scripts.benchmark_campaign import validate,admission,exposure,write_atomic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--authorization',type=Path,required=True)
    parser.add_argument('--max-jobs',type=int,default=1000,help='Only reduces the frozen schedule; never retries a job')
    args=parser.parse_args();directory=args.directory.resolve()
    continuation=directory/'pilot-continuation.lock'
    with continuation.open('x',encoding='utf-8') as stream:
        json.dump(dict(pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat()),stream)
    try:
        for _ in range(args.max_jobs):
            if (directory/'pilot-stop-request.json').exists():
                print(json.dumps(dict(status='OWNER_STOP_BEFORE_NEXT_DISPATCH',HTTP=0)),flush=True)
                break
            prepared=prepare(args.manifest)
            state=validate(read_json(directory/'manifest-campaign.json'),prepared,read_json(args.authorization))
            gate=admission(state,datetime.now(timezone.utc))
            if not gate['allowed']:
                print(json.dumps(dict(status='STOPPED_BY_EXISTING_ADMISSION',gate=gate,
                    started=len(state['runs']),planned=len(prepared['jobs']),
                    exposure_usd={p:str(v) for p,v in exposure(state).items()})),flush=True)
                break
            job=gate['job'];log=directory/(job['job_id']+'.controller.log')
            command=[sys.executable,str(ROOT/'scripts/run_model_combination_benchmark.py'),str(directory),
                '--manifest',str(args.manifest.resolve()),'--authorization',str(args.authorization.resolve()),'--run-next']
            with log.open('x',encoding='utf-8') as stream:
                print(json.dumps(dict(status='DISPATCH_NEXT_APPROVED_JOB',job=job)),flush=True)
                process=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if process.returncode:
                print(json.dumps(dict(status='CONTROLLER_ERROR_NO_RETRY',job_id=job['job_id'],returncode=process.returncode)),flush=True)
                break
            state=read_json(directory/'manifest-campaign.json');run=state['runs'][-1]
            print(json.dumps(dict(status='APPROVED_JOB_ENDED',job_id=job['job_id'],config=job['config_id'],
                case=job['case_id'],result=run['status'],requests=(run.get('summary') or {}).get('actual_requests'),
                exposure_usd={p:str(v) for p,v in exposure(state).items()})),flush=True)
        else:
            print(json.dumps(dict(status='LOCAL_JOB_BOUND_REACHED_NO_EXTRA_JOBS')),flush=True)
    finally:
        continuation.unlink()


if __name__=='__main__':main()
