# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline frozen-source regression for worker telemetry and observed progress."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))


def main():
    if len(sys.argv)!=2:raise ValueError('Explicit new verification output required')
    output=Path(sys.argv[1]).resolve()
    permitted=(ROOT/'artifacts/verification').resolve()
    if not output.is_relative_to(permitted) or output.exists():raise ValueError('VERIFICATION_OUTPUT_UNSAFE')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Reuse the preceding reviewed selection and inventory, not its PASS or hashes.
    previous=json.loads((permitted/'goal-task-loop-20261006-final-regression.json').read_text(encoding='utf-8'))
    records=['mission-live-progress-20261006-03/verification.json',
             'mission-live-progress-20261006-stall-03/verification.json']
    actual=[json.loads((permitted/name).read_text(encoding='utf-8')) for name in records]
    for record in actual:
        if (record['status']!='PASS' or record['robot_connections']!=0
                or not record['sources_unchanged'] or not record['web_unchanged']
                or not record['owned_children_exited'] or record.get('forced_owned_cleanup')):
            raise ValueError('FINAL_ACTUAL_RUNTIME_NOT_ACCEPTED')
        if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest for p,digest in record['source_sha256'].items()):
            raise ValueError('FINAL_ACTUAL_SOURCE_CHANGED')
        if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest for p,digest in record['web_sha256'].items()):
            raise ValueError('FINAL_ACTUAL_WEB_CHANGED')
    selection=previous['selection']+[
        'tests.integration.test_mission_live_telemetry.TelemetryTests',
        'packages.twinpulse_core.tests.test_observed_progress.ProgressTests',
        'packages.twinpulse_core.tests.test_observed_mission.ObservedMissionTests',
        'tests.integration.test_cold_start_mission.ColdStartTests',
        'tests.integration.test_robot_source_identity',
    ]
    paths=sorted({r['Path'] for r in previous['source_hashes']}|{p for record in actual for p in record['source_sha256']}|{
        'packages/twinpulse_core/src/twinpulse_core/mission_telemetry.py',
        'packages/twinpulse_core/src/twinpulse_core/observed_progress.py',
        'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
        'scripts/robot_source_identity.py','scripts/verify_mission_live_progress.py',
        'tests/integration/test_mission_live_telemetry.py',
        'packages/twinpulse_core/tests/test_observed_progress.py',
        'packages/twinpulse_core/tests/test_observed_mission.py',
        'tests/integration/test_cold_start_mission.py',
        'tests/integration/test_robot_source_identity.py',
        'apps/twinpulse-web/src/CurrentGoalReview.test.tsx','apps/twinpulse-web/src/ChatWorkspace.test.tsx'})
    def hashes():return [{'Path':p,'Hash':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths]
    before=hashes();started=time.monotonic()
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(selection))
    elapsed=time.monotonic()-started;after=hashes()
    data={'schema_version':'verification-regression-1.0',
          'status':'PASS' if result.wasSuccessful() and before==after else 'FAIL',
          'tests':result.testsRun,'elapsed_s':round(elapsed,3),'selection':selection,
          'source_count':len(paths),'sources_unchanged':before==after,'source_hashes':after,
          'robot_connections':0,'physical_validation':'NOT_RUN',
          'after_actual_runtime':True,'actual_runtime_records':records,
          'skipped':[{'test':str(test),'reason':reason} for test,reason in result.skipped],
          'errors':[{'test':str(test),'traceback':trace} for test,trace in result.errors],
          'failures':[{'test':str(test),'traceback':trace} for test,trace in result.failures]}
    with output.open('x',encoding='utf-8') as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    print(json.dumps({k:data[k] for k in ('status','tests','elapsed_s','source_count','sources_unchanged')}))
    return 0 if data['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
