# SPDX-License-Identifier: Apache-2.0
"""Bind actual completed receipts; never manufacture a missing journey PASS."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--reproduction-attempt',required=True)
    parser.add_argument('--source-review',type=Path,required=True,help='Required actual independently reviewed, hash-bound current delta; never synthesize a reviewer approval from current files.')
    parser.add_argument('--reproduction-project',required=True)
    parser.add_argument('--reproduction-scene',required=True)
    args=parser.parse_args();a=args.attempt;b=args.reproduction_attempt
    if any(len(v)!=2 or not v.isascii() or not v.isdecimal() for v in (a,b)):raise ValueError('TWO_DIGIT_ATTEMPTS_REQUIRED')
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    paths=[OUT/name for name in (f'ui-{a}/result.json',f'ui-cold-{a}/result.json',f'lineage-{a}/result.json',
        f'lineage-cold-{a}/result.json',f'ui-reproduction-{b}/result.json',f'cleanup-fresh-{a}.json',f'cleanup-cold-{a}.json',
        f'cleanup-lineage-{a}.json',f'cleanup-history-{a}.json',f'cleanup-reproduction-{b}.json',
        f'normal{a}/shutdown.json',f'normal{a}-restart/shutdown.json',f'installed-files{a}.json',f'supplementary{a}/result.json')]
    unresolved=['FINAL_RECEIPT_NOT_PASS:'+p.relative_to(OUT).as_posix() for p in paths if not p.is_file() or read(p).get('status')!='PASS']
    reproduction=OUT/f'ui-reproduction-{b}/result.json'
    if reproduction.is_file() and read(reproduction).get('status')=='PASS':
        checks=runpy.run_path(str(ROOT/'scripts/verify_robot_focus_gate.py'))
        unresolved+=checks['reproduction_issues'](read(reproduction),active['release_id'],dict(project=args.reproduction_project,scene_revision=args.reproduction_scene))
    diagnostic=OUT/f'diagnostic-installed-roundtrip{a}.json'
    if args.source_review:
        if (not diagnostic.is_file() or read(diagnostic).get('status')!='PASS'
                or read(diagnostic).get('release_id')!=active['release_id']
                or read(diagnostic).get('source_sha256')!=active['source_manifest_sha256']):
            unresolved.append('FINAL_ACTUAL_DIAGNOSTIC_ROUNDTRIP_NOT_PASS')
    reviewed_files=['scripts/twinpulse_engine_host.py','scripts/twinpulse_live_viewport.py','scripts/twinpulse_update_probe.py',
        'scripts/twinpulse_fleet_runtime.py','scripts/twinpulse_scan_worker.py',
        'packages/twinpulse_core/src/twinpulse_core/lidar_geometry.py','packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py',
        'packages/twinpulse_robot_safety/fleet_worker.py','packages/twinpulse_robot_safety/fleet_control.py',
        'packages/twinpulse_robot_safety/teleop_ros.py','packages/twinpulse_app/src/twinpulse_app/physical_live_session.py',
        'apps/twinpulse-web/src/RobotFleet.tsx','apps/twinpulse-web/src/robot-operation-diagnostics.ts','apps/twinpulse-web/src/TwinViewport.tsx','apps/twinpulse-web/src/api.ts',
        'packages/twinpulse_app/src/twinpulse_app/process_manager.py',
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'packages/twinpulse_app/src/twinpulse_app/application.py',
        'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
        'packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/request_latency.py','scripts/verify_robot_focus_gate.py']
    source_review=dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',fork='none',read_only=True,
        recorded_by='Main agent from actual independent collaboration reviews; reviewer made no file or App/device writes',
        release_id=active['release_id'],source_manifest_sha256=active['source_manifest_sha256'],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in reviewed_files},
        found_and_fixed=['Copy/serialization still inside event or PC Stop critical sections',
            'Terminal wheel observation cleanup/projection and optional malformed diagnostic exceptions',
            'Original failed check absent from compact summary despite exact expanded/export data',
            'Final Kit/viewport elapsed, failed HTTP and join diagnostics missing after original failure',
            'Synchronous SIM raycast blocks Kit; one-slot no-queue worker with original sample and epoch fences',
            'Cleanup exception could skip later owners and APP.close; final close failure not in saved result',
            'Huge optional JSON integer/invalid reason could throw instead of typed rejection',
            'Expected SDK fast nonreturn made post-close final write unreachable',
            'Root natural/forced exit and Job descendant close were not separately recorded',
            'Final stdout failure, missing/downgraded shutdown contract and cross-launch handoff swap',
            'Serialized live metadata/JPEG requests and unsafe cold-history pairing boundary',
            'Unconsumed204 fetch completion: actual21b alternating body-drain comparison; exact zero-byte drain/context recheck within original2s, no recorder/gate abort exception',
            'Slow host-tail child timing scope and optional diagnostic exception masking',
            'Report mtime aggregation could lend another attempt READY; explicit selected-attempt paths/SHA and missing/failing journey veto added',
            'Required next supervised session sequence absent from the single report'],
        provider_observation_review='Astra reviewed the startup/explicit-refresh cache as display-only, not authentication; initial/refresh failure stays unconfirmed and blocks only new model generations. Candidate/old cancellation precedes mutation; late refresh cannot commit. The discarded-response test now supplies actual HTTP headers, without relaxing framing.',
        harness_finding='Extra reproduction12 first hold used +world-X despite west-facing saved pose; original body-forward105.45mm. Original failed tool/source retained; reproduction13 only uses unchanged4cm body-forward criterion.',
        current_actual_receipts=[ref(p) for p in paths if p.is_file()],
        limits=['Historical05 producer/executor and03 6.53s sole causes UNKNOWN',
            '08 synchronous scan671ms confirmed, original substage/scheduling sole cause UNKNOWN',
            'Saved-geometry13 has different initial/bed-entry poses, not exact original timing replay',
            'Original15 host-tail703ms specific substage/sole cause UNKNOWN; original17 displayed-frame1043ms FAIL preserved',
            'Original reproduction23 conversation/workflow 3000ms aborts remain FAIL; observed credential-file lookup under workflow lock was removed, but the sole cause including CPU and explicit fault-harness scheduling is UNKNOWN',
            'Atomic live receipt removes an observed serial request path; a clean new journey is not proof of the old tail cause repaired or a recurrence guarantee',
            'Actual Pi/continuous physical driving/braking/world alignment NOT_RUN',
            'Generalized independent LiDAR automatic body verdict NOT_IMPLEMENTED; wheel body UNKNOWN',
            'F12 machine gate still independently required; review cannot substitute for it'])
    if args.source_review:
        source_review=read(args.source_review.resolve())
        if (source_review.get('release_id')!=active['release_id'] or source_review.get('source_manifest_sha256')!=active['source_manifest_sha256']
                or source_review.get('read_only') is not True or source_review.get('unresolved')
                or source_review.get('status')!='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION'):
            raise ValueError('CURRENT_ACTUAL_SOURCE_REVIEW_REQUIRED')
        if not source_review.get('final_reviewed_files') or any(sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in source_review['final_reviewed_files'].items()):
            raise ValueError('REVIEWED_SOURCE_CHANGED')
    source_path=OUT/f'astra-review{a}.json';write(source_path,source_review)
    # Exact archived App records, not a fabricated terminal success summary.
    branches={}
    for role,start_path in dict(fresh=OUT/f'start-fresh-{a}.json',cold=OUT/f'start-cold-{a}.json',
            lineage=OUT/f'start-lineage-{a}.json',lineage_cold=OUT/f'start-history-{a}.json',
            normal=OUT/f'normal{a}/result.json',restart=OUT/f'normal{a}-restart/result.json',
            reproduction=OUT/f'start-reproduction-{b}.json').items():
        if not start_path.is_file():unresolved.append('SHUTDOWN_START_MISSING:'+role);continue
        launch=read(start_path)['launch_id'];folder=OUT/f'runtime-final{a}'/launch
        evidence=dict(start=start_path,engine_result=folder/'engine-result.json',owner_exit=folder/'owned-exit-observations.json',cleanup=folder/'cleanup-receipt.json')
        for key,path in evidence.items():
            if not path.is_file():unresolved.append('SHUTDOWN_FILE_MISSING:'+role+':'+key)
        branches[role]={key:ref(path) for key,path in evidence.items() if path.is_file()}
    shutdown=OUT/f'shutdown-contract{a}.json'
    write(shutdown,dict(schema='owned-shutdown-contract-1.0',release_id=active['release_id'],source_sha256=active['source_manifest_sha256'],branches=branches,
        limitation='Root natural exit is not a claim that all Job descendants shut down gracefully. Pre-close descendant counts and Job close remain explicit.'))
    replay=OUT/f'observation-replay{a}.json'
    review=dict(schema='physical-readiness-review-1.2',status='KNOWN_BLOCKER' if unresolved else 'SOFTWARE_NO_KNOWN_BLOCKER',
        unresolved=unresolved,scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
        observation_policy='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',
        not_run=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT'],
        protocol_status='UNKNOWN_BYTES_PRESERVED_NOT_DECODED',replay=ref(replay),shutdown_contract=ref(shutdown),reproduction=ref(reproduction),
        reproduction_expected=dict(project=args.reproduction_project,scene_revision=args.reproduction_scene),
        evidence=[ref(p) for p in (source_path,diagnostic,OUT/'original08-stall-analysis.json',OUT/'sim-retest-analysis13.json',
            OUT/'followup15-17-analysis.json',OUT/f'runtime-final{a}/receipt.json',shutdown,*paths) if p.is_file()],
        note='Permission to begin the supervised live checks only, not whole R1-R5 completion or physical navigation qualification.')
    target=OUT/f'physical-readiness-review{a}.json';write(target,review)
    print(json.dumps(dict(status=review['status'],unresolved=unresolved,review=str(target))))
if __name__=='__main__':main()
