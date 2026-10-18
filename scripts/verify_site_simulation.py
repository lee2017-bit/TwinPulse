# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual owned Isaac v2 room + existing Burger Physics. No provider/robot."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import os
import subprocess
from threading import Event, Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from scripts.verify_live_viewport import _request, _session
from twinpulse_app.process_manager import TwinPulseProcessManager


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = dict(status='FAIL', input='synthetic saved photo-room recipe', physics='actual_local_Isaac',
                  provider_calls=0, robot_connections=0, samples=[], checks=[])
    manager = None
    lease_stop = Event()
    lease_thread = None
    try:
        from tests.integration.test_a2_room_recipe import write_recipe
        from twinpulse_app.room_recipe import prepare_project_burger_visual, import_project_room_recipe
        state = output/'runtime'
        write_recipe(state, 'sim_room', 'blue', 3.5)
        prepare_project_burger_visual(state, 'sim_room', (-.3, -1.2, .002), 0.)
        draft = import_project_room_recipe(state, 'sim_room')
        manager = TwinPulseProcessManager(repo_root=ROOT, state_dir=state, python_executable=Path(sys.executable),
            isaac_python=Path('C:/isaacsim/python.bat'), browser_executable=None, headless=True,
            fixture_mode=True, ready_timeout_s=180., project_id='sim_room')
        manager.start(open_browser=False)
        base, cookie, csrf = _session(manager)
        def request(path, body=None):
            return _request(base, path, **({'body': body, 'csrf': csrf} if body is not None else {}), cookie=cookie)[1]
        def observation():
            value = request('/v1/product/state')
            sample = value['snapshot']
            if sample is not None and (not result['samples'] or sample['sequence'] != result['samples'][-1]['sequence']):
                result['samples'].append(sample)
            return value
        def wait_operation(op, timeout=45):
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                view = observation()
                current = next(o for o in view['operations'] if o['command_id'] == op['command_id'])
                if current['status'] not in ('accepted', 'running'):
                    if current['status'] != 'succeeded':
                        raise RuntimeError(str(current['receipt']))
                    return current
                time.sleep(.15)
            raise TimeoutError('Bounded operation deadline')
        request('/v1/product/conversation', dict(action='resume', request_id='sim-resume',
            expected_scene_revision=draft.site.scene.revision, expected_input_revision=draft.input_revision.digest))
        summary = request('/v1/product/workflow')['site_draft']
        revision = summary['revision']
        if args.browser:
            _, ticket = manager.product_bootstrap()
            env = {**os.environ, 'TWINPULSE_VIEW_URL': base, 'TWINPULSE_VIEW_BOOTSTRAP': ticket,
                   'TWINPULSE_VIEW_OUTPUT': str(output)}
            completed = subprocess.run(['node', str(ROOT/'apps/twinpulse-web/e2e/site-simulation.mjs')],
                cwd=ROOT/'apps/twinpulse-web', env=env, timeout=210, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            result['browser'] = json.loads((output/'browser.json').read_text(encoding='utf-8'))
            if completed.returncode or result['browser']['status'] != 'PASS':
                raise RuntimeError('Actual SIM Web acceptance failed: '+str(result['browser'].get('error')))
            result['checks'] = result['browser']['checks']
            result['status'] = 'PASS'
            return 0
        request('/v1/product/draft/acknowledge', {'revision': revision})
        lease = request('/v1/product/lease', {})
        def renew():
            request('/v1/product/lease/renew', {'control_lease_id': lease['control_lease_id']})
        def keep_lease():
            while not lease_stop.wait(.75):
                try: renew()
                except Exception as error:
                    result['lease_error'] = str(error)[:320]
                    break
        lease_thread = Thread(target=keep_lease, daemon=True)
        lease_thread.start()
        deadline = time.monotonic()+6
        while time.monotonic() < deadline:
            view = observation()
            if view['engine_readiness']['site_scene_build_v2']['ready']: break
            time.sleep(.1)
        else: raise RuntimeError('Updated leased engine build readiness not observed')
        build = request('/v1/product/commands', dict(client_request_id='sim-build', command_type='build_site_scene',
            expected_applied_revision=revision, artifact_id=summary['artifact_id']))
        result['build'] = wait_operation(build)
        result['plan'] = request('/v1/product/simulation/plan', dict(scene_revision=revision,
            start=[-.3, -1.2], goal=[-.3, -.25], yaw_rad=0.))
        run_body = dict(client_request_id='sim-run', command_type='run', expected_applied_revision=revision,
                        simulation_id=result['plan']['plan_id'])
        run = request('/v1/product/commands', run_body)
        result['run'] = wait_operation(run)
        assert request('/v1/product/commands', run_body)['command_id'] == run['command_id']
        result['checks'].append('duplicate Run request returns same operation; no second Run')
        deadline = time.monotonic()+180
        last_renew = time.monotonic()
        while time.monotonic() < deadline:
            view = observation(); snap = view['snapshot']
            if time.monotonic()-last_renew > 1:
                renew(); last_renew = time.monotonic()
            if snap['runtime_state'] == 'completed': break
            if snap['runtime_state'] in ('error', 'unstable', 'off_route', 'stage_invalid', 'paused'):
                raise RuntimeError('SIM stopped before arrival: '+str(snap))
            time.sleep(.2)
        else: raise TimeoutError('Actual Burger did not reach bounded goal')
        assert snap['telemetry_available'] and snap['run_id'] == result['plan']['plan_id']
        assert snap['distance_to_goal_m'] <= .04
        result['arrival'] = snap
        result['checks'].append('current v2 room and referenced Burger PhysX articulation rotated and reached +Y goal')
        second = request('/v1/product/simulation/plan', dict(scene_revision=revision,
            start=snap['position_m'][:2], goal=[-.3, -1.2], yaw_rad=snap['yaw_rad']))
        op = request('/v1/product/commands', dict(client_request_id='sim-return', command_type='run',
            expected_applied_revision=revision, simulation_id=second['plan_id']))
        wait_operation(op)
        time.sleep(1.)
        renew()
        op = request('/v1/product/commands', dict(client_request_id='sim-stop', command_type='pause',
            expected_applied_revision=revision))
        result['stop'] = wait_operation(op)
        before = observation()['snapshot']; time.sleep(.7); after = observation()['snapshot']
        assert after['runtime_state'] == 'paused' and before['position_m'] == after['position_m']
        result['checks'].append('Stop acknowledged and repeated live PhysX pose unchanged after pause')
        result['final'] = after
        result['viewport'] = request('/v1/product/viewport')
        assert result['viewport']['frame'] is not None
        result['checks'].append('same applied revision has a live embedded-viewer frame during Physics Run')
        result['status'] = 'PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error)[:1800])
    finally:
        if manager:
            lease_stop.set()
            if lease_thread: lease_thread.join(timeout=3)
            manager.stop()
            if manager.engine_result_file.is_file():
                result['host'] = json.loads(manager.engine_result_file.read_text(encoding='utf-8'))
        paths = ['extensions/twinpulse.extension/twinpulse/extension/runtime.py',
                 'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
                 'packages/twinpulse_core/src/twinpulse_core/site_simulation.py',
                 'packages/twinpulse_app/src/twinpulse_app/command_broker.py',
                 'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
                 'packages/twinpulse_app/src/twinpulse_app/simulation_assets.py',
                 'packages/twinpulse_app/src/twinpulse_app/api.py', 'scripts/verify_site_simulation.py',
                 'scripts/twinpulse_engine_host.py', 'apps/twinpulse-web/src/SimulationRunCard.tsx',
                 'apps/twinpulse-web/src/ChatWorkspace.tsx', 'apps/twinpulse-web/src/api.ts',
                 'apps/twinpulse-web/src/chat.css', 'apps/twinpulse-web/e2e/site-simulation.mjs',
                 'packages/twinpulse_core/src/twinpulse_core/simulation_goal.py',
                 'packages/twinpulse_app/src/twinpulse_app/conversation_service.py',
                 'apps/twinpulse-web/src/conversation-types.ts', 'apps/twinpulse-web/src/SimulationRouteView.tsx',
                 'apps/twinpulse-web/src/conversation-intent.ts']
        result['source_sha256'] = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
        result['web_sha256'] = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (ROOT/'apps/twinpulse-web/dist').rglob('*') if p.is_file()}
        (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('SITE_SIMULATION='+result['status'], flush=True)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
