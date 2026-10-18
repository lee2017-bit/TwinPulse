# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned built-Web/API chat rehearsal. Never contacts a provider or robot."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import hashlib
import json
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / 'artifacts' / 'c1-chat-20261005'
sys.path.insert(0, str(ROOT))
from tests.integration.test_r5_product_api import R5ProductApiTests, png


def run_case(case):
    output = OUTPUT_ROOT / case
    output.mkdir(parents=True, exist_ok=True)
    os.environ['TWINPULSE_TEST_TMP'] = str(output / 'isolated-api')
    if case.startswith('robot-'):
        from tests.integration.test_chat_robot_preparation import ChatRobotTests
        harness=ChatRobotTests()
    else:harness = R5ProductApiTests()
    harness.setUp()
    try:
        harness.server._static_root = ROOT / 'apps/twinpulse-web/dist'
        if case.startswith('robot-'):
            harness.attach(fault={'status':'SSH_OR_REMOTE_SETUP_FAILED','exit_code':255,'reason':'connection refused'} if case=='robot-ssh' else None)
            if case=='robot-release':harness.report['health']['deployment']['release_id']='b'*64
            if case=='robot-stop-failure':
                harness.controller.result='STOP_FAILED'
                harness.controller.cleanup_error='MOTOR_OFF_READ_FAILED'
            if case=='robot-stop':harness.controller.hold=True
            if case in {'robot-collect','robot-transfer-failure','robot-local-failure'}:
                harness.attach_collection(resume_failure=case=='robot-transfer-failure',local_failure=case=='robot-local-failure')
            if case=='robot-inspection':
                from twinpulse_app.automatic_demo_service import AutomaticDemoService
                from twinpulse_app.automatic_mission_service import AutomaticMissionService
                from twinpulse_app.chat_inspection import ChatInspection
                from tests.integration.test_automatic_demo_service import GEOMETRY
                from threading import RLock
                automatic=AutomaticDemoService(harness.static,'default',room_loader=harness.workflow.inspection_room,geometry_loader=lambda:GEOMETRY)
                automatic.room_source_token=harness.workflow.inspection_source_token
                automatic.room_scene_loader=harness.workflow.inspection_scene
                harness.addCleanup(automatic.close)
                harness.inspection_calls=[]
                def factory(prior,room,effective,goal):
                    harness.inspection_calls.append(goal)
                    raise ValueError('FIXTURE_ADMISSION_FAILURE')
                mission=AutomaticMissionService(automatic,adapter_factory=factory);harness.addCleanup(mission.close)
                inspection=ChatInspection(mission,harness.workflow,harness.server.chat_robot_preparation,RLock())
                # Explicit fixture engine observation only inside readiness;
                # neither actual Isaac nor Build success is claimed.
                actual=inspection.readiness
                def ready(owner):
                    artifact=harness.workflow._site_artifact
                    view={'engine_connected':True,'snapshot':{'applied_revision':artifact.revision if artifact else None}}
                    with patch.object(harness.broker,'supervisor_state',return_value=view):return actual(owner)
                inspection.readiness=ready
                harness.server.chat_inspection=inspection;harness.server.conversation.inspection=inspection
        if case=='saved':
            from tests.integration.test_chat_conversation import ChatConversationTests
            ChatConversationTests.saved_room(harness)
        stack=ExitStack()
        if case=='failed':
            from twinpulse_app.command_broker import BrokerError
            stack.enter_context(patch.object(harness.workflow,'start_generation',side_effect=BrokerError('provider_missing','Provider configuration required')))
            status=json.loads(harness.supervisor_status.read_text(encoding='utf-8'))
            status.update(status='error',phase='engine_start',message='Owned engine fixture failure')
            harness.supervisor_status.write_text(json.dumps(status),encoding='utf-8')
        if case=='cancel':
            factory=harness.workflow._gateway_factory
            def slow_factory():
                gateway=factory();gateway._provider.delay_s=1.8
                return gateway
            harness.workflow._gateway_factory=slow_factory
            # explicit_fixture does not refresh the configured production
            # gateway, so replace only this isolated fixture application's one.
            harness.workflow._application.set_generation_gateway(slow_factory())
        image = output / 'fixture-image.png'
        image.write_bytes(png())
        # Use the authenticated test context's already established cookie by
        # issuing a new one-use bootstrap through the owner-only test API.
        secret = 'c' * 43
        harness.server._bootstrap['product'] = secret
        env = {**os.environ, 'TWINPULSE_CHAT_OUTPUT': str(output), 'TWINPULSE_CHAT_URL': harness.server.base_url,
               'TWINPULSE_CHAT_BOOTSTRAP': secret, 'TWINPULSE_CHAT_IMAGE': str(image), 'TWINPULSE_CHAT_CASE':case}
        with stack:
            script='chat-robot.mjs' if case.startswith('robot-') else 'chat-c1.mjs'
            completed = subprocess.run(['node', str(ROOT / 'apps/twinpulse-web/e2e'/script)],
                                       cwd=ROOT / 'apps/twinpulse-web', env=env, timeout=90, check=False)
        if case=='robot-inspection' and completed.returncode==0:
            if (len(harness.inspection_calls)!=1 or harness.inspection_calls[0]['mode']!='SURVEY_ONLY'
                    or harness.controller.calls!=['qualify']):
                raise AssertionError('Inspection browser repeated work or requested goal motion')
        (output/'conversation-result.json').write_text(json.dumps(harness.server.conversation.snapshot(),indent=2),encoding='utf-8')
        (output/'workflow-result.json').write_text(json.dumps(harness.workflow.snapshot(),indent=2),encoding='utf-8')
        if case.startswith('robot-'):
            (output/'robot-adapter-result.json').write_text(json.dumps({'collector_calls':harness.collects,
                'worker_modes':harness.controller.calls,'inputs':harness.controller.inputs,
                'stationary_calls':getattr(harness,'collection_calls',[]),'transfer_calls':getattr(harness,'transfer_calls',[]),
                'inspection_calls':getattr(harness,'inspection_calls',[]),
                'physical_tests':0,'transport':'REACTIVE_OFFLINE_CONTROLLER'},indent=2),encoding='utf-8')
        return completed.returncode
    finally:
        harness.tearDown()


def main():
    global OUTPUT_ROOT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--robot-cases',action='store_true',help='Only explicit offline chat robot preparation cases; no SSH or robot.')
    args=parser.parse_args()
    if args.output:
        OUTPUT_ROOT=args.output.resolve()
        OUTPUT_ROOT.mkdir(parents=True,exist_ok=False)
    cases=('robot-normal','robot-ssh','robot-release','robot-stop-failure','robot-problem','robot-stop',
           'robot-collect','robot-transfer-failure','robot-local-failure','robot-inspection') if args.robot_cases else ('image','text','real','failed','cancel','saved')
    outcomes={case:run_case(case) for case in cases}
    files=('packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
           'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
           'packages/twinpulse_app/src/twinpulse_app/api.py',
           'packages/twinpulse_app/src/twinpulse_app/startup_checks.py','packages/twinpulse_app/src/twinpulse_app/process_manager.py',
           'apps/twinpulse-web/src/App.tsx','apps/twinpulse-web/src/ChatWorkspace.tsx',
           'apps/twinpulse-web/src/chat.css','apps/twinpulse-web/src/api.ts',
           'apps/twinpulse-web/src/conversation-types.ts','apps/twinpulse-web/src/ChatWorkspace.test.tsx',
           'apps/twinpulse-web/src/ChatProjects.tsx','apps/twinpulse-web/src/ChatProjects.test.tsx','apps/twinpulse-web/src/conversation-intent.ts','apps/twinpulse-web/src/types.ts',
           'tests/integration/test_chat_startup_checks.py',
           'apps/twinpulse-web/e2e/startup-failure-real.mjs','scripts/verify_startup_failure_browser.py',
           'tests/integration/test_chat_conversation.py','scripts/verify_chat_c1.py','apps/twinpulse-web/e2e/chat-c1.mjs',
           'packages/twinpulse_app/src/twinpulse_app/chat_robot_preparation.py',
           'tests/integration/test_chat_robot_preparation.py','apps/twinpulse-web/src/ChatRobotStatus.tsx',
           'apps/twinpulse-web/e2e/chat-robot.mjs','packages/twinpulse_app/src/twinpulse_app/robot_readiness.py',
           'scripts/run_robot_readiness.py','tests/integration/test_robot_readiness.py',
           'tests/integration/test_robot_readiness_app.py','apps/twinpulse-web/src/ChatRobotStatus.test.tsx',
           'packages/twinpulse_app/src/twinpulse_app/chat_inspection.py','packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
           'packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py',
           'packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py','packages/twinpulse_core/src/twinpulse_core/observed_mission.py',
           'packages/twinpulse_core/src/twinpulse_core/adaptive_mission_contract.py','packages/twinpulse_robot_safety/observed_runtime.py',
           'tests/integration/test_chat_inspection.py','tests/integration/test_cold_start_mission.py',
           'apps/twinpulse-web/src/ChatRoomBuild.tsx','apps/twinpulse-web/src/ChatRoomBuild.test.tsx')
    result={'status':'C1_SCOPED_BROWSER_API_PASS' if not any(outcomes.values()) else 'FAIL',
            'cases':outcomes,'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
            'web_dist_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'apps/twinpulse-web/dist').rglob('*') if f.is_file()},
            'physical_tests':0,'paid_calls':0,'isaac_runtime':'NOT_RUN','C1_complete':False,
            'remaining':['Full C1/C2 acceptance beyond this fixture regression; see current execution checkpoint',
                         'Target binary/profile qualification and C4/C5 REAL chat integration','Same-package full field acceptance']}
    if args.robot_cases:
        result.update(status='C3_C4_SCOPED_OFFLINE_BROWSER_API_PASS' if not any(outcomes.values()) else 'FAIL',
            C3_complete=False,C4_complete=False,transport='REACTIVE_OFFLINE_CONTROLLER',
            remaining=['Target ROS/C++ build and reviewed binary/profile identity',
                'Full moving field-suite DAG and measured profile acceptance beyond stationary collection',
                'C4 correction/replay/semantic goal/route Confirm and C5 TaskLoop integration','Physical qualification and demo acceptance'])
    report=OUTPUT_ROOT/'verification.json'
    if report.exists():
        previous=json.loads(report.read_text(encoding='utf-8'))
        if previous['status']=='FAIL':
            from uuid import uuid4
            history=report.parent/'failed-attempts';history.mkdir(exist_ok=True)
            (history/(uuid4().hex+'.json')).write_text(json.dumps(previous,indent=2),encoding='utf-8')
    report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return max(outcomes.values())


if __name__ == '__main__': raise SystemExit(main())
