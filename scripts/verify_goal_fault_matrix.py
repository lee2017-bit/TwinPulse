# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen offline native/App/task faults, not whole UI/Isaac/field acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))


def main():
    if len(sys.argv)!=2 or not re.fullmatch('[a-z0-9-]{1,100}',sys.argv[1]):
        raise ValueError('EXPLICIT_ISOLATED_VERIFICATION_NAME_REQUIRED')
    output=ROOT/'artifacts/verification'/sys.argv[1];output.mkdir(exist_ok=False)
    previous=json.loads((ROOT/'artifacts/verification/mission-live-progress-20261006-final-regression.json').read_text())
    selection=previous['selection']+[
        'tests.integration.test_native_combined_cleanup.CombinedCleanupTests',
        'tests.integration.test_goal_combined_faults',
        'packages.twinpulse_robot_safety.tests.mission_test',
        'packages.twinpulse_robot_safety.tests.teleop_test',
        'tests.integration.test_mission_report_storage_failure',
        'tests.integration.test_remote_correction_guard',
        'tests.integration.test_soak_resource_policy',
    ]
    extra=['tests/integration/test_native_combined_cleanup.py','tests/integration/test_goal_combined_faults.py',
        'tests/fixtures/combined_fault_evidence.py','scripts/verify_goal_fault_matrix.py',
        'packages/twinpulse_core/src/twinpulse_core/cleanup_diagnostics.py',
        'packages/twinpulse_robot_safety/cleanup_notes.py','packages/twinpulse_robot_safety/teleop_worker.py',
        'packages/twinpulse_robot_safety/tests/teleop_test.py','packages/twinpulse_robot_safety/tests/mission_test.py',
        'tests/integration/test_mission_report_storage_failure.py','tests/integration/test_remote_correction_guard.py',
        'scripts/owned_process_metrics.py','tests/integration/test_soak_resource_policy.py',
        'apps/twinpulse-web/src/TwinViewport.tsx','apps/twinpulse-web/src/TwinViewport.test.tsx',
        'apps/twinpulse-web/src/chat.css','apps/twinpulse-web/e2e/live-viewport.mjs',
        'apps/twinpulse-web/src/api.ts','apps/twinpulse-web/src/api.test.ts',
        'apps/twinpulse-web/e2e/chat-c1.mjs','apps/twinpulse-web/e2e/chat-sim-journey.mjs',
        'apps/twinpulse-web/e2e/site-simulation.mjs']
    extra+=['scripts/verify_goal_separated_journey.py','apps/twinpulse-web/e2e/goal-resource-observer.mjs',
            'apps/twinpulse-web/e2e/owned-chrome-observer.mjs','apps/twinpulse-web/e2e/owned-chrome-observer.test.mjs']
    extra+=['apps/twinpulse-web/src/mission-cleanup.ts','apps/twinpulse-web/e2e/goal-native-isaac.mjs',
        'packages/twinpulse_app/src/twinpulse_app/chat_inspection_visual.py','tests/fixtures/idle_reference_robot_process.py',
        'tests/fixtures/observed_robot_process.py','scripts/twinpulse_engine_host.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py','tests/integration/test_active_mission_display.py']
    selection+=['tests.integration.test_active_mission_display','tests.integration.test_chat_inspection_visual']
    extra+=['tests/integration/test_chat_inspection_visual.py',
        'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py','apps/twinpulse-web/vite.config.ts']
    paths=sorted({r['Path'] for r in previous['source_hashes']}|set(extra))
    def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    before=hashes();start=time.monotonic();os.environ['TWINPULSE_COMBINED_EVIDENCE']=sys.argv[1]
    try:result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(selection))
    finally:os.environ.pop('TWINPULSE_COMBINED_EVIDENCE',None)
    after=hashes();cases=sorted((output/'cases').glob('*.json'))
    data={'status':'PASS' if result.wasSuccessful() and before==after else 'FAIL',
        'tests':result.testsRun,'elapsed_s':round(time.monotonic()-start,3),'selection':selection,
        'source_sha256':after,'source_count':len(after),'sources_unchanged':before==after,
        'robot_connections':0,'physical_validation':'NOT_RUN','isaac_browser_matrix':'NOT_RUN',
        'coverage':'NATIVE_ORIGINAL_SENSOR_INPUT_GUARDS_AND_APP_TASK_FAULT_COMBINATIONS',
        'case_artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cases},
        'errors':[{'test':str(t),'traceback':trace} for t,trace in result.errors],
        'failures':[{'test':str(t),'traceback':trace} for t,trace in result.failures],
        'skipped':[{'test':str(t),'reason':why} for t,why in result.skipped]}
    if len(cases)!=17:data['status']='FAIL';data['coverage_error']='EXPECTED_17_NEW_COMBINED_CASE_ARTIFACTS'
    with (output/'verification.json').open('x',encoding='utf-8') as stream:json.dump(data,stream,indent=2)
    print(json.dumps({k:data[k] for k in ('status','tests','elapsed_s','source_count','sources_unchanged')}))
    return 0 if data['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
