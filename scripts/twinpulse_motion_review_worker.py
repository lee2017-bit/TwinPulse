# SPDX-License-Identifier: Apache-2.0
"""Fixed offline role. No SSH, robot, model, shell or scene execution."""
from pathlib import Path
import argparse
import json
import multiprocessing  # Collect the shipped field_tests stdlib dependency in the frozen role; no tracker/process is constructed here.
import os
import re
import sys
import time

if not getattr(sys,'frozen',False):
    _root=Path(__file__).resolve().parents[1]
    for _package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
        sys.path.insert(0,str(_root/'packages'/_package/'src'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--operation',required=True);parser.add_argument('--project',required=True);parser.add_argument('--job',required=True)
    args=parser.parse_args()
    if any(not re.fullmatch('[a-f0-9]{32}',s) for s in (args.operation,args.job)) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',args.project):raise ValueError('REVIEW_IDENTITY')
    root=args.state_root.resolve();directory=root/'physical-live'/args.operation;out=root/'motion-reviews'/'jobs'/args.job
    if any(p.is_symlink() for p in (directory,out,*out.parents)) or not out.is_dir():raise ValueError('REVIEW_PATH')
    from twinpulse_app.runtime_paths import resource_root
    resource=resource_root()
    sys.path.insert(0,str(resource/'packages/twinpulse_robot_safety'))
    from twinpulse_app.physical_motion_analysis import read_archive,analyse
    from field_tests import register_pair
    began=time.monotonic()
    try:
        archive=read_archive(directory,args.operation,args.project,began+60)
        result=analyse(archive,register_pair,began+60)
    except Exception as error:
        # Preserve the original diagnostic locally, but return no raw exception
        # text or paths to the renderer. Failure is not a motion PASS.
        import traceback
        (out/'failure.log').write_text(traceback.format_exc(),encoding='utf-8')
        result=dict(schema='physical-motion-review-1.0',status='INCOMPLETE',reason=type(error).__name__,
            operation_id=args.operation,project_id=args.project,physical_motion_verified=False,authority_restored=False)
    result.update(job_id=args.job,release_id=os.environ.get('TWINPULSE_RELEASE_ID','source-development'),
        analyser_source_sha256=__import__('hashlib').sha256((resource/'packages/twinpulse_app/src/twinpulse_app/physical_motion_analysis.py').read_bytes()).hexdigest(),
        elapsed_s=time.monotonic()-began)
    raw=json.dumps(result,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>2*1024*1024:raise ValueError('REVIEW_RESULT_BOUND')
    temp=out/'result.tmp'
    with temp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,out/'result.json')
    return 0

if __name__=='__main__':raise SystemExit(main())
