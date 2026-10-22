# SPDX-License-Identifier: Apache-2.0
"""Record original failed acceptance; never generates a success/reviewer verdict."""
from hashlib import sha256
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'

def ref(path):return dict(path=path.relative_to(OUT).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',choices=('25','27'),default='25');args=parser.parse_args()
    a=args.attempt
    failed=OUT/('ui-reproduction-29/result.json' if a=='27' else 'ui-25/result.json')
    value=json.loads(failed.read_text(encoding='utf-8-sig'))
    if value.get('status')!='FAIL':raise ValueError('ORIGINAL_FAILURE_REQUIRED')
    if a=='27':
        review=dict(schema='physical-readiness-review-1.2',status='KNOWN_BLOCKER',
            classification='MAIN_RECORDED_ORIGINAL29_FAILURE_WITH_ASTRA_READ_ONLY_REVIEW_NOT_READY',
            scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
            unresolved=['ORIGINAL25_GEOMETRY29_CHAIR_ISAAC_UPDATE_STALLED_516MS',
                'FROZEN23_FAILED_CHECK_RESOURCE_DIAGNOSTIC_ALLOWLIST_MISMATCH',
                'SAME_SOURCE_REBOOT_COMPARISON_NOT_RUN','FINAL_NORMAL_AND_RESTART27_NOT_RUN'],
            observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
            not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],
            protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',replay=ref(OUT/'observation-replay27.json'),
            evidence=[ref(OUT/p) for p in ('ui-27/result.json','ui-cold-27/result.json','lineage-27/result.json','lineage-cold-27/result.json',
                'ui-reproduction-29/result.json','failed-ui-reproduction29-original-logs/receipt.json','runtime-final27/receipt.json','memory-failure29-review.json')],
            note='Four installed UI journeys passed. Saved original25 geometry29 failed. No reboot or threshold/source change during retry. Four PASS do not override29 FAIL; exact failed CPU phase remains unavailable.')
        with (OUT/'physical-readiness-review27.json').open('x',encoding='utf-8') as stream:json.dump(review,stream,indent=2)
        print(json.dumps(dict(status=review['status'],unresolved=review['unresolved'])))
        return
    review=dict(schema='physical-readiness-review-1.2',status='KNOWN_BLOCKER',
        classification='MAIN_RECORDED_BLOCKED_ACCEPTANCE_NOT_INDEPENDENT_SOURCE_APPROVAL',
        scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
        unresolved=['ORIGINAL25_ISAAC_UPDATE_STALLED_AND_STALE_FRAME_UNRESOLVED',
            'FINAL_FROZEN_R4_UI_AND_COLD_RESTORE_NOT_RUN','FINAL_WHOLE_NORMAL_RESTART_AND_REPRODUCTION_NOT_RUN'],
        observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
        not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],
        protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',replay=ref(OUT/'observation-replay25.json'),
        evidence=[ref(OUT/p) for p in ('ui-25/result.json','failed-ui25-original-logs/receipt.json','runtime-final25/receipt.json','resources-after25.json')],
        note='Resource pressure is observed, not proved to be the sole cause. Await clean resource state; do not relax deadlines or silently retry into a success verdict.')
    with (OUT/'physical-readiness-review25.json').open('x',encoding='utf-8') as stream:json.dump(review,stream,indent=2)
    print(json.dumps(dict(status=review['status'],unresolved=review['unresolved'])))

if __name__=='__main__':main()
