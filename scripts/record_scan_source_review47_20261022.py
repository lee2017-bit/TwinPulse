# SPDX-License-Identifier: Apache-2.0
"""Transcribe the actual read-only review and preserve original45 uncertainty."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def main():
    old=read(OUT/'build30/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build31/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build31/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed and all(name.startswith('apps/twinpulse-web/dist/') for name in changed),changed
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==new[name] for name in changed if name in new)
    files=['apps/twinpulse-web/src/TwinViewport.tsx','apps/twinpulse-web/src/RobotFleet.test.tsx',
        'scripts/scan_display_observation.mjs','scripts/scan_display_observation.test.mjs','scripts/scene_robot_ux_acceptance.mjs',
        'scripts/verify_robot_focus_gate.py','tests/integration/test_robot_focus_gate.py']
    write(OUT/'scan-source-review47.json',dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual final source/negative-artifact read-only review. Reviewer did not execute tests, App, system or device actions.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        exact_compiled_product_delta_from_frozen30=changed,product_source_delta=['apps/twinpulse-web/src/TwinViewport.tsx'],unresolved=[],
        fixed=['Original scan700ms deadline render request and current-render clock; image1000ms, control clocks, pose and epochs unchanged.',
            'Atomic DOM/renderer-time/live/preview/frame/epoch sample separated from request/receipt clocks.',
            'Existing5s rays visibility wait replaced, not extended: only explicit absence on a current frame may wait.',
            'Pending evaluate bounded by remaining budget; every received sample recorded before validation; visible invalid sample terminal.',
            'Independent gate verifies all observations, original deadline, no intermediate visible violations, final exact sample/window and bounded numeric values.'],
        references=[ref(OUT/name) for name in ('scan-expiry-red47.log','scan-expiry-red47b.log','scan-expiry-final47.log',
            'scan-observation-deadline47.log','scan-gate-deadline47.log','history-source-review45.json')],
        limits=['Original45 FAIL unchanged;827ms was step duration, not measured scan age. Missing original stamp/atomic time cannot be backfilled.',
            'Initial new RED fixture omitted selection callback; preserved separately. Corrected RED reproduced both product boundaries.',
            'Timer/render change is not a hard real-time guarantee while the event loop is blocked.',
            'Original43 cold-read timeout branch was not reached in45; current installed UI retest remains required.',
            'No physical/Pi/braking/driving/world registration qualification. Fresh47/cold/lineage/history and original geometry48 plus final gate required.']))
    original=read(OUT/'ui-45/result.json');assert original['status']=='FAIL'
    write(OUT/'scan-failure45-review.json',dict(status='ORIGINAL_FAIL_PRESERVED_SCAN_DISPLAY_BOUNDARY_CONTRIBUTIONS_UNKNOWN',
        launch_id=original['desktop']['engine']['launch_id'],project=original['project'],failed_step=original['steps'][-1],
        original_scan_captured_at_ms=None,original_atomic_observation_at_ms=None,
        interpretation=['Original step duration827ms is not the original scan age.',
            'Source100ms age-state expiry gap and cross-process assertion-clock race separately confirmed; original contribution UNKNOWN.',
            'Source/recorder/gate correction is not a retroactive original45 PASS.'],
        not_run=['COLD45','LINEAGE45','HISTORY45','REPRODUCTION46'],
        references=[ref(OUT/name) for name in ('ui-45/result.json','ui-45/failure-22.png','failed-ui45-original-logs/receipt.json',
            'runtime-final45/receipt.json','memory-final45/receipt.json','budget-final45.json','gate-result45.json')]))
    print(json.dumps(dict(status='ACTUAL_READ_ONLY_SOURCE_REVIEW_RECORDED',release_id=manifest['build_id'],source_sha256=manifest['source_manifest_sha256'],changed=changed)))
if __name__=='__main__':main()
