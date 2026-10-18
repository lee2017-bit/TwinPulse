# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual loopback App with injected synthetic transport. Never contacts a robot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.integration.test_derived_review_selection import selection_fixture
from tests.integration.test_robot_diagnostics import fixture, observation
from twinpulse_app import LocalApiServer, JsonProviderSettingsStore
from twinpulse_app.physical_controller import PhysicalController
from rehearse_offline_app import NoCredentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--controller', action='store_true', help='Test PC-only manual controls, never real robot')
    parser.add_argument('--physical-fake', action='store_true', help='Production protocol with local fake subprocess; no robot')
    parser.add_argument('--bedroom-mission', action='store_true', help='Photo-room synthetic mission; no robot or Isaac')
    parser.add_argument('--quick-console', action='store_true', help='Dedicated auto-read UI with synthetic collector; no robot')
    parser.add_argument('--joystick-scan', action='store_true', help='Joystick and scan browser fixtures; no robot or physical process')
    args = parser.parse_args()
    output = args.output.resolve()
    node = shutil.which('node')
    chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
    if not node or not chrome.is_file(): parser.error('Existing Node/Chrome required')
    output.mkdir(parents=True, exist_ok=False)
    robot_root = output/'synthetic-robot-state'
    robot_root.mkdir()
    calls = []
    def collect(*args, **kwargs):
        calls.append(1)
        time.sleep(1.5)
        if len(calls) == 1: return observation()
        if len(calls) == 2:
            value = observation()
            value['health']['board']['torque_enabled'] = True
            value['health']['status'] = 'NEEDS_ATTENTION'
            return value
        return {'status': 'SSH_OR_REMOTE_SETUP_FAILED'}
    diagnostics = fixture(robot_root, collect, time.monotonic)
    app, workflow, broker, _, _, _ = selection_fixture(output/'isolated-state')
    original = app._project_store.path.read_bytes()
    secret = secrets.token_urlsafe(32)
    status_file = None
    if args.physical_fake or args.bedroom_mission:
        # This rehearsal has no owned engine, but its fake controller must be
        # reachable through the same ready-only UI gate as a launched app.
        # The offline bedroom review uses that UI gate too; this fixture
        # advertises only local App readiness, never Isaac or robot readiness.
        status_file = output/'synthetic-launcher-ready.json'
        status_file.write_text(json.dumps({'schema_version':'1.0','status':'ready',
            'phase':'fake_process_only','message':'Synthetic UI readiness; no engine or robot',
            'backend':{'owned':False,'state':'ready'},
            'engine':{'owned':False,'state':'not_started'},
            'browser':{'launched':False}}),encoding='utf-8')
    server = LocalApiServer(broker, product_bootstrap_secret=secret,
        engine_bootstrap_secret=secrets.token_urlsafe(32), product_workflow=workflow,
        static_root=ROOT/'apps/twinpulse-web/dist', robot_diagnostics=diagnostics,
        supervisor_status_file=status_file,
        session_history_root=output,
        physical_controller=(PhysicalController(output,command=lambda _root,mode:[sys.executable,'-B',
            str(ROOT/'tests/fixtures/manual_robot_process.py'),mode,str(output/'fake-robot')])),
        provider_settings_store=JsonProviderSettingsStore(output/'isolated-state/settings.json'),
        credential_store=NoCredentials())
    result = dict(status='FAIL', data='synthetic_transport_fixture', robot='NOT_RUN', isaac='NOT_RUN')
    try:
        if args.physical_fake:
            from packages.twinpulse_robot_safety.tests.mission_test import write_rehearsal_archive
            result['mission_rehearsal']=write_rehearsal_archive(output)
        source_paths = [ROOT/name for name in ('scripts/rehearse_robot_console.py',
            'packages/twinpulse_app/src/twinpulse_app/session_journal.py',
            'packages/twinpulse_app/src/twinpulse_app/session_history.py',
            'apps/twinpulse-web/src/SessionHistory.tsx',
            'apps/twinpulse-web/e2e/robot-console-real.mjs', 'apps/twinpulse-web/e2e/physical-controller-fake.mjs',
            'apps/twinpulse-web/e2e/manual-controller-real.mjs', 'apps/twinpulse-web/src/RobotCheckDetails.tsx',
            'apps/twinpulse-web/src/RobotDiagnostics.tsx', 'apps/twinpulse-web/src/PhysicalRobotController.tsx',
            'apps/twinpulse-web/src/RobotQuickConsole.tsx', 'apps/twinpulse-web/e2e/quick-console-real.mjs',
            'apps/twinpulse-web/src/DriveJoystick.tsx', 'apps/twinpulse-web/src/LidarScanView.tsx',
            'apps/twinpulse-web/e2e/joystick-scan.mjs',
            'scripts/launch_robot_console.py',
            'apps/twinpulse-web/src/RobotController.tsx', 'apps/twinpulse-web/src/driveKeys.ts',
            'packages/twinpulse_app/src/twinpulse_app/robot_diagnostics.py',
            'packages/twinpulse_robot_safety/teleop_worker.py', 'packages/twinpulse_robot_safety/teleop_ros.py',
            'packages/twinpulse_robot_safety/mission_runtime.py',
            'packages/twinpulse_robot_safety/teleop.sh','packages/twinpulse_robot_safety/profile.json',
            'packages/twinpulse_robot_safety/tests/mission_test.py',
            'packages/twinpulse_robot_safety/tests/teleop_test.py','scripts/verify_twinpulse.ps1',
            'packages/twinpulse_robot_safety/teleop_contract.py', 'packages/twinpulse_robot_safety/stop_policy.py',
            'tests/fixtures/manual_robot_process.py',
            'packages/twinpulse_app/src/twinpulse_app/physical_controller.py')]
        source_paths.extend(ROOT/name for name in ('apps/twinpulse-web/src/BedroomTwin.tsx',
            'apps/twinpulse-web/src/api.ts','apps/twinpulse-web/e2e/bedroom-mission-real.mjs',
            'packages/twinpulse_core/src/twinpulse_core/local_navigation.py',
            'packages/twinpulse_core/src/twinpulse_core/ros_observations.py',
            'packages/twinpulse_core/src/twinpulse_core/navigation_binding.py',
            'packages/twinpulse_core/src/twinpulse_core/mission_contract.py',
            'packages/twinpulse_core/src/twinpulse_core/observation_stream.py',
            'packages/twinpulse_robot_safety/robot_journal.py',
            'packages/twinpulse_core/tests/test_navigation_binding.py',
            'tests/integration/test_physical_controller.py',
            'scripts/prepare_robot.py',
            'scripts/robot_source_identity.py',
            'packages/twinpulse_app/src/twinpulse_app/bedroom_rehearsal.py',
            'packages/twinpulse_app/src/twinpulse_app/bedroom_review.py',
            'packages/twinpulse_app/src/twinpulse_app/evaluation_report.py',
            'packages/twinpulse_app/src/twinpulse_app/api.py'))
        source_paths.extend(p for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file())
        source_hashes = lambda: {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
        sources = source_hashes()
        server.start()
        env = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url,
            TWINPULSE_REHEARSAL_BOOTSTRAP=secret, TWINPULSE_REHEARSAL_OUTPUT=str(output),
            TWINPULSE_REHEARSAL_CHROME=str(chrome))
        browser_script = ('joystick-scan.mjs' if args.joystick_scan else 'bedroom-mission-real.mjs' if args.bedroom_mission else 'physical-controller-fake.mjs' if args.physical_fake else
                          'manual-controller-real.mjs' if args.controller else 'quick-console-real.mjs' if args.quick_console else 'robot-console-real.mjs')
        child = subprocess.run([node, str(ROOT/'apps/twinpulse-web/e2e'/browser_script)],
            cwd=ROOT/'apps/twinpulse-web', env=env, capture_output=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        browser = json.loads((output/'browser-result.json').read_text(encoding='utf-8'))
        if child.returncode or browser['status'] != 'PASS': raise RuntimeError('Browser failed')
        if args.bedroom_mission:
            from twinpulse_core.revisions import canonical_sha256
            from twinpulse_app.evaluation_report import evaluate_bedroom_comparison
            downloaded=json.loads((output/'export.json').read_text(encoding='utf-8'))
            if downloaded['revision'] != canonical_sha256({k:v for k,v in downloaded.items() if k!='revision'}):
                raise RuntimeError('Browser mission export canonical identity changed')
            comparison=json.loads((output/'comparison-export.json').read_text(encoding='utf-8'))
            if evaluate_bedroom_comparison(comparison)['source_comparison_revision'] != comparison['revision']:
                raise RuntimeError('Browser comparison export canonical identity changed')
            result['browser_export_canonical_identity_verified']=True
        if len(calls) != (0 if args.controller or args.physical_fake or args.bedroom_mission else 3) or app._project_store.path.read_bytes() != original:
            raise RuntimeError('Transport count or original project changed')
        if args.physical_fake:
            events=[row for file in (output/'fake-robot').glob('*-events.json') for row in json.loads(file.read_text())]
            if not {(.03,0.),(-.03,0.),(0.,.2),(0.,-.2)}.issubset({tuple(row[:2]) for row in events}):
                raise RuntimeError('Not every control reached fake device output')
            if any(not 0<=row[2]<.25 for row in events):raise RuntimeError('Expired fake output')
            result['fake_output_count']=len(events)
            result['all_four_directions_at_fake_output']=True
            logs=list((output/'artifacts/manual-control').glob('*/session.jsonl'))
            records=[json.loads(line) for file in logs for line in file.read_text().splitlines()]
            robot=[r['data']['event'] for r in records if r['kind']=='robot_event']
            if not {'accepted','armed','published','release_requested','idle_confirmed','observation'} <= {r['kind'] for r in robot}:
                raise RuntimeError('Missing command-observation evidence')
            if not {'forward','backward','left','right'} <= {r['data']['action'] for r in robot if r['kind']=='published'}:
                raise RuntimeError('Missing published directions in session journal')
            if any(r['real_transport'] is not False for r in records):raise RuntimeError('Fake journal mislabelled')
            if any('challenge' in file.read_text() for file in logs):raise RuntimeError('Challenge leaked to journal')
            stop_sessions=[]
            for file in logs:
                saved=[json.loads(line) for line in file.read_text().splitlines()]
                trace=[row['data']['event'] for row in saved if row['kind']=='robot_event']
                stops=[i for i,event in enumerate(trace) if event['kind']=='stop_requested']
                if not stops:continue
                if any(event['kind']=='published' for event in trace[stops[0]+1:]):
                    raise RuntimeError('Movement published after terminal stop was accepted')
                ends=[row['data'] for row in saved if row['kind']=='robot_finished']
                if not ends or not ends[-1].get('cleanup_confirmed'):raise RuntimeError('Stop cleanup unconfirmed')
                stop_sessions.append({'action':trace[stops[0]]['data']['action'],'status':ends[-1]['status'],
                                      'published_after_stop':0,'cleanup_confirmed':True})
            if not {'finish_stop','force_stop'}<={row['action'] for row in stop_sessions}:
                raise RuntimeError('Both terminal stop paths must reach production worker')
            result['terminal_stop_sessions']=stop_sessions
            result.update(session_journals=len(logs),session_events=len(records),robot_events=len(robot),
                          session_evidence='SYNTHETIC_ONLY_NOT_FLOOR_MOTION')
        elif (output/'fake-robot').exists():
            raise RuntimeError('Unexpected fake physical process in read-only/rehearsal test')
        if sources != source_hashes(): raise RuntimeError('Source/build changed during rehearsal')
        result.update(status='PASS', stages=browser['stages'], synthetic_collector_calls=len(calls),
                      original_project_changed=False, source_and_build_sha256=sources)
    except Exception as error:
        result['error_type'] = type(error).__name__
    finally:
        server.stop()
        (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('ROBOT_CONSOLE_REHEARSAL=' + result['status'])
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
