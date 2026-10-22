# SPDX-License-Identifier: Apache-2.0
"""Transcribe actual Astra read-only review; not App or hardware acceptance."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())

def main():
    manifest=read(OUT/'build31/dist/TwinPulse/windows-release-manifest.json')
    original=read(OUT/'scan-source-review47.json')
    assert (manifest['build_id'],manifest['source_manifest_sha256'])==(original['release_id'],original['source_manifest_sha256'])
    files=['apps/twinpulse-web/src/TwinViewport.tsx','scripts/scan_display_observation.mjs',
        'scripts/scan_display_observation.test.mjs','scripts/scene_robot_ux_acceptance.mjs',
        'scripts/body_frame_travel.mjs','scripts/body_frame_travel.test.mjs',
        'scripts/verify_robot_fleet_ui.mjs','scripts/verify_robot_focus_gate.py',
        'tests/integration/test_robot_focus_gate.py','scripts/finalize_continuous_review_20261021.py',
        'scripts/prepare_saved_sim_clearance_20261022.mjs']
    value=dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual independent source and raw50 review; reviewer did not modify files or run the App/device.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],unresolved=[],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        product_delta_since_original47=[],
        original47_tool_sha256=read(OUT/'memory-final47/metadata.json')['test_contract_sha256'],
        source_review_parent=ref(OUT/'scan-source-review47.json'),
        reviewed=['Original48 failed before Stop: saved last pose is inside navigation25cm envelope. Offline original zero-yaw compiled geometry reproduces20 START_OR_GOAL_BLOCKED candidates; original live USD BBox was not retained.',
            'Explicit UI preparation49 is separate: original immutable SHA, all static boxes/floor/other SIM, sampled-only segment checks, actual bounded rotation/forward/Stop/Disconnect/Exit; original48 not relabelled PASS.',
            'Original50 exact body reverse is10cm at rotated saved yaw, while world-X87.681mm falsely failed the old90mm assertion. Original whole50 and unexecuted later branches stay FAIL/NOT_RUN.',
            'Same robot/op/connection and finite measured SIM poses; approach strictly>50mm and reverse>=90mm, with bounded lateral/yaw checks. Independent Python gate recomputes original poses and rejects malformed shapes.',
            'Cancellation test observes the exact outbound UI request ID and reports its terminal failure immediately instead of a generic poll timeout; terminal failure never becomes Stop PASS.',
            'Existing whole47 raw body observations satisfy the corrected calculation. Same frozen product31 whole47 and new original-geometry52 may be separate current evidence, not one joined uninterrupted journey.'],
        references=[ref(OUT/name) for name in ('navigation-failure48-review.json','body-frame-failure50-review.json',
            'clearance-preparation49/result.json','cleanup-preparation49.json',
            'body-frame-node52-final-b.log','body-frame-gate52-final-b.log','memory-final47/metadata.json',
            'runtime-final47/receipt.json','runtime-final50/receipt.json')],
        limits=['Original47 and current acceptance-tool SHA are distinct and preserved. No original App result was changed.',
            'Current36-step saved-geometry52 and independent shutdown, final diagnostic export/gate/negative/report verification remain required.',
            'This does not repair the original historical sole causes, prove physical motion, or grant robot authority. Physical robot remains OFF.'])
    with (OUT/'source-review52.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status='ACTUAL_SOURCE_REVIEW_RECORDED_NOT_UI_ACCEPTANCE',release_id=manifest['build_id'])))

if __name__=='__main__':main()
