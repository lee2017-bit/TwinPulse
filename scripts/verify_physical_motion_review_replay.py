# SPDX-License-Identifier: Apache-2.0
"""Supplementary actual offline worker on original bytes, not UI/device proof."""
from pathlib import Path
import argparse
import json
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.physical_motion_review import PhysicalMotionReview

def main():
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path,required=True);p.add_argument('--operation',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('NEW_EVIDENCE_REQUIRED')
    with (args.state_root/'physical-live'/args.operation/'events-00000.jsonl').open('rb') as stream:first=json.loads(stream.readline(256*1024+1))
    class OfflineOnly:
        lock=threading.RLock()
        def physical_runtime_active(self):return False
    service=PhysicalMotionReview(OfflineOnly(),ROOT,args.state_root)
    state=service.start(args.operation,first['project_id'],__import__('uuid').uuid4().hex)
    service.thread.join(85)
    closed=service.close();state=service.snapshot(args.operation,first['project_id'])
    review=state['review']
    result=dict(classification='SUPPLEMENTARY_REAL_OFFLINE_PROCESS_ORIGINAL_BYTES_NOT_UI_OR_HARDWARE_ACCEPTANCE',
        status='PASS' if closed['closed'] and state['job']['status']=='COMPLETED' and review and review['status']=='COMPLETED_WITH_LIMITS' else 'FAIL',
        job=state['job'],closed=closed,review=review)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],job=state['job'],rows=review.get('input_rows') if review else None,
        windows=len(review.get('windows',[])) if review else 0,comparisons=[w.get('comparison') for w in review.get('windows',[])] if review else [])))
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
