# SPDX-License-Identifier: Apache-2.0
"""Main records an actual read-only collaboration review; no readiness claim."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
FILES=['packages/twinpulse_app/src/twinpulse_app/physical_motion_analysis.py',
    'packages/twinpulse_app/src/twinpulse_app/physical_motion_review.py',
    'packages/twinpulse_app/src/twinpulse_app/physical_fleet_adapter.py',
    'packages/twinpulse_app/src/twinpulse_app/workspace_devices.py',
    'packages/twinpulse_app/src/twinpulse_app/process_manager.py',
    'packages/twinpulse_app/src/twinpulse_app/library_process.py',
    'packages/twinpulse_app/src/twinpulse_app/api.py','apps/twinpulse-web/src/RobotMotionReview.tsx',
    'apps/twinpulse-web/src/RobotFleet.tsx','apps/twinpulse-web/src/api.ts',
    'scripts/twinpulse_motion_review_worker.py','scripts/twinpulse_update_probe.py',
    'scripts/verify_robot_lineage_ui.mjs','scripts/verify_robot_focused_journey.ps1','scripts/verify_robot_focus_gate.py']

def main():
    package=OUT/'build23/dist/TwinPulse'
    manifest=json.loads((package/'windows-release-manifest.json').read_text())
    sources=json.loads((package/'_internal/resources/source-manifest.json').read_text())
    rows={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    if any(sources[name]!=value for name,value in rows.items() if name in sources):raise ValueError('REVIEWED_SOURCE_CHANGED')
    result=dict(schema='read-only-source-review-candidate-1.0',status='NO_ADDITIONAL_CONFIRMED_SOURCE_BLOCKER_IN_REVIEWED_SCOPE_NOT_UI_ACCEPTANCE',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',reasoning_effort='xhigh',read_only=True,
        recorded_by='Main from actual collaboration review and its final response; no reviewer App/process/network/robot writes.',
        candidate_release=manifest['build_id'],source_sha256=manifest['source_manifest_sha256'],files=rows,
        final_review='Applied epoch and strict before/after wheel brackets, incomplete/fallback scan bridging, interval-bound extrinsics, pending direction/epoch batching, primary/cleanup exception preservation and optional CPU isolation are resolved in reviewed source. No further confirmed source blocker in this scope.',
        acceptance_design='Existing lineage explicitly analyzes immutable original05; separate cold App uses GET only and compares the exact saved JSON/job/receipt/segments/rows. The candidate-only verifier cannot substitute for installed acceptance.',
        unresolved=['Original25 actual stalled Kit/display remains FAIL; observed resource pressure is not a proven sole cause.',
            'Final installed fresh39/cold14/lineage10/history5, ordinary Start/restart/shutdown and current evidence gate remain required.',
            'Physical App acquisition, Pi load/storage, continuous driving, braking and world alignment NOT_RUN; all chassis/body estimates remain unqualified.'])
    with (OUT/'source-review-candidate23.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(dict(status=result['status'],candidate_release=result['candidate_release'])))

if __name__=='__main__':main()
