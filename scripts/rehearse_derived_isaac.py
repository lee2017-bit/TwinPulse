# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isolated real browser/API/production BridgeClient/Isaac synthetic rehearsal.

Run with existing Isaac python.bat. No user project, provider, devices or Run.
Only the browser submits commands; no receipts or snapshots injected into broker.
"""
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
for folder in ('packages/twinpulse_core/src', 'packages/twinpulse_app/src', 'packages/twinpulse_provider/src'):
    sys.path.insert(0, str(ROOT / folder))
from rehearse_derived_review import hashes
from rehearse_offline_app import NoCredentials
from tests.integration.test_derived_review_selection import selection_fixture
from twinpulse_app import LocalApiServer, JsonProviderSettingsStore
from twinpulse_app.derived_site_review import DerivedSiteReview


def source_hashes():
    values = hashes()
    for name in ('scripts/rehearse_derived_isaac.py', 'apps/twinpulse-web/e2e/derived-isaac-real.mjs',
                 'packages/twinpulse_app/src/twinpulse_app/command_broker.py',
                 'extensions/twinpulse.extension/twinpulse/extension/bridge_client.py',
                 'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
                 'extensions/twinpulse.extension/twinpulse/extension/runtime.py',
                 'extensions/twinpulse.extension/twinpulse/extension/scene_compiler.py'):
        values[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    node = shutil.which('node')
    chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
    if not node or not chrome.is_file(): parser.error('Existing Node/Chrome required')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['TWINPULSE_STATE_DIR'] = str(output / 'isolated-state')
    for name in ('TWINPULSE_BRIDGE_URL', 'TWINPULSE_ENGINE_BOOTSTRAP', 'TWINPULSE_API_KEY'):
        os.environ.pop(name, None)
    result = dict(status='FAIL', data='synthetic_test_fixture', boundary='browser_API_broker_production_bridge_actual_Isaac',
                  robot_connections=0, provider_calls=0, physics_run='NOT_RUN', physical_validation='NOT_RUN', checks=[])
    sim = server = bridge = child = None
    try:
        baseline = source_hashes()
        application, workflow, broker, source, _, _ = selection_fixture(output / 'isolated-state')
        archive = application.scan_review.download_archive(application.scan_review.snapshot()['workspace_revision'])['archive_text']
        (output / 'synthetic-archive.json').write_text(archive, encoding='utf-8')
        derived = DerivedSiteReview.create(source, archive)
        original_bytes = application._project_store.path.read_bytes()
        from isaacsim import SimulationApp
        sim = SimulationApp({'headless': True, 'width': 960, 'height': 720})
        import omni.usd
        import omni.timeline
        from pxr import UsdGeom
        omni.usd.get_context().new_stage()
        for _ in range(10): sim.update()
        sys.path.insert(0, str(ROOT / 'extensions/twinpulse.extension'))
        from twinpulse.extension import get_extension
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.bridge_client import BridgeClient
        assert get_extension() is None
        runtime = TwinPulseRuntime()
        adapter = IsaacSimulationAdapter(runtime)
        stage = omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage, '/ExternalKeep').GetPrim().SetCustomDataByKey('fixture', 'preserve-this')
        receipts = []
        execute = adapter.execute

        def verify_execute(command):
            assert command.command_type == 'build_site_scene' and len(receipts) < 2
            expected = (source.site.scene, derived.site.scene)[len(receipts)]
            assert command.expected_applied_revision == expected.revision
            receipt = execute(command)
            assert receipt.status == 'succeeded', receipt.error_code
            assert receipt.applied_revision == expected.revision
            assert runtime.compiler.matches_site_scene(expected)
            positions = {}
            for obj in expected.objects:
                prim = stage.GetPrimAtPath(f'/World/TwinPulse/Environment/{obj.id}')
                actual = tuple(prim.GetAttribute('xformOp:translate').Get())
                assert all(abs(a-b) < 1e-6 for a,b in zip(actual, obj.transform.position_m))
                positions[obj.id] = actual
            receipts.append(dict(revision=receipt.applied_revision, fingerprint=receipt.build_fingerprint, positions=positions))
            return receipt

        adapter.execute = verify_execute
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret, engine_bootstrap_secret=engine_secret,
            product_workflow=workflow, static_root=ROOT / 'apps/twinpulse-web/dist',
            provider_settings_store=JsonProviderSettingsStore(output / 'isolated-state/settings.json'), credential_store=NoCredentials())
        server.start()
        bridge = BridgeClient(adapter, base_url=server.base_url, bootstrap_secret=engine_secret)
        bridge.start()
        env = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url, TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                   TWINPULSE_REHEARSAL_OUTPUT=str(output), TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child = subprocess.Popen([node, str(ROOT / 'apps/twinpulse-web/e2e/derived-isaac-real.mjs')],
            cwd=ROOT / 'apps/twinpulse-web', env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 180
        while child.poll() is None and time.monotonic() < deadline:
            sim.update()
            bridge.update()
            assert not omni.timeline.get_timeline_interface().is_playing()
            time.sleep(.005)
        if child.poll() is None: raise TimeoutError('Owned browser rehearsal exceeded deadline')
        browser = json.loads((output / 'browser-result.json').read_text())
        assert child.returncode == 0 and browser['status'] == 'PASS', 'Browser stages failed'
        assert len(receipts) == 2 and runtime.compiler.matches_site_scene(derived.site.scene)
        assert application.site_draft == source and application._project_store.path.read_bytes() == original_bytes
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('fixture') == 'preserve-this'
        assert not stage.GetPrimAtPath('/World/TwinPulse/Robot').IsValid()
        assert not stage.GetPrimAtPath('/World/TwinPulse/Task').IsValid()
        assert 'run' not in adapter.snapshot().permitted_commands
        assert get_extension() is None and baseline == source_hashes()
        stage.GetRootLayer().Export(str(output / 'synthetic-derived-stage.usda'))
        assert browser['failure_checks'] == [
            'failed_browser_state_read_discards_cached_engine_authority',
            'state_read_recovery_no_automatic_build',
            'real_lease_expiry_disables_build_no_automatic_acquisition',
            'never_settling_browser_read_times_out_no_extra_command',
            'post_timeout_recovery_no_automatic_build']
        result.update(status='PASS', checks=browser['stages'], failure_checks=browser['failure_checks'], receipts=receipts,
                      source_and_build_sha256=baseline, original_project_changed=False,
                      external_prim_preserved=True, extension_UI_started=False)
    except Exception as error:
        result['error_type'] = type(error).__name__
        # Do not serialize arbitrary HTTP exceptions or bootstrap/session values.
    finally:
        if child is not None and child.poll() is None:
            # Only this runner's own child; never touch any existing process.
            child.terminate()
            child.wait(timeout=10)
        if bridge: bridge.stop()
        if server: server.stop()
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('COMBINED_DERIVED_REHEARSAL=' + result['status'], flush=True)
        if sim: sim.close()
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
