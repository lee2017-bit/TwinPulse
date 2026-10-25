# SPDX-License-Identifier: Apache-2.0
"""Preserve each supplementary physical-task test attempt, including failures."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--output-root',type=Path);parser.add_argument('--include-survey',action='store_true');parser.add_argument('--include-engine-recovery',action='store_true');args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
folder=(args.output_root or ROOT/'outputs/physical-task-preparation-20261025-01')/('tests'+args.attempt)
folder.mkdir(parents=True,exist_ok=False)
names=['tests.integration.test_physical_robot_tasks','tests.integration.test_robot_tasks',
    'tests.integration.test_fleet_elapsed_motion','tests.integration.test_sim_fleet_navigation',
    'tests.integration.test_physical_live_session','tests.integration.test_physical_fleet_adapter',
    'packages.twinpulse_robot_safety.tests.test_finite_execution','packages.twinpulse_robot_safety.tests.test_fleet_native']
if args.include_survey:names+=['tests.integration.test_environment_survey','tests.integration.test_environment_survey_review',
    'tests.integration.test_environment_alignment','tests.integration.test_environment_alignment_review',
    'tests.integration.test_environment_overlays','tests.integration.test_environment_photo',
    'tests.integration.test_chat_conversation','tests.integration.test_scene_edit_transaction',
    'tests.integration.test_scene_changes','tests.integration.test_scene_edit_snapshot_projection',
    'tests.integration.test_dependency_scene_changes','tests.integration.test_scene_state_metadata']
if args.include_engine_recovery:
    # Child crash/OS-lock tests must import the same repository sources too.
    os.environ['PYTHONPATH']=os.pathsep.join(str(ROOT/'packages'/p/'src') for p in
        ('twinpulse_core','twinpulse_provider','twinpulse_app'))+os.pathsep+str(ROOT)
    names+=['tests.integration.test_bridge_late_receipt','tests.integration.test_bridge_lease_rotation',
        'tests.integration.test_bridge_robot_channel','tests.integration.test_r4_bridge_api',
        'tests.integration.test_execution_diagnostics']
suite=unittest.defaultTestLoader.loadTestsFromNames(names);stream=io.StringIO();started=time.monotonic()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
(folder/'console.txt').write_text(stream.getvalue(),encoding='utf-8')
value=dict(scope='SUPPLEMENTARY_FAKE_DEVICES_MODEL_NOT_HARDWARE_OR_INSTALLED_UI_ACCEPTANCE',
    status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    skipped=len(result.skipped),elapsed_s=time.monotonic()-started,modules=names,
    failing=[test.id() for test,_ in result.failures+result.errors])
(folder/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value))
sys.exit(0 if result.wasSuccessful() else 1)
