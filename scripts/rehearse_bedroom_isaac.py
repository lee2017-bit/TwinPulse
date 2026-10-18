# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual browser/product bridge/Isaac photo-approximation preview. No robot or Run."""
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
from rehearse_offline_app import NoCredentials
from tests.integration.test_derived_review_selection import selection_fixture
from twinpulse_app import LocalApiServer, JsonProviderSettingsStore
from twinpulse_app.bedroom_review import load_bedroom_source


def source_hashes():
    paths = [ROOT / name for name in (
        'scripts/rehearse_bedroom_isaac.py', 'apps/twinpulse-web/e2e/bedroom-isaac-real.mjs',
        'apps/twinpulse-web/src/BedroomTwin.tsx', 'apps/twinpulse-web/src/App.tsx', 'apps/twinpulse-web/src/api.ts',
        'packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/bedroom_review.py',
        'packages/twinpulse_app/src/twinpulse_app/robot_geometry_evidence.py',
        'packages/twinpulse_core/src/twinpulse_core/room_goal.py',
        'apps/twinpulse-web/src/BedroomGoalReview.tsx',
        'packages/twinpulse_app/src/twinpulse_app/bedroom_twin.py',
        'packages/twinpulse_app/src/twinpulse_app/bedroom_rehearsal.py',
        'packages/twinpulse_core/src/twinpulse_core/bounded_grid_plan.py',
        'packages/twinpulse_core/src/twinpulse_core/local_navigation.py',
        'packages/twinpulse_app/src/twinpulse_app/command_broker.py',
        'extensions/twinpulse.extension/twinpulse/extension/isaac_adapter.py',
        'extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py',
        'extensions/twinpulse.extension/twinpulse/extension/runtime.py',
        'extensions/twinpulse.extension/twinpulse/extension/scene_compiler.py')]
    paths.extend(p for p in (ROOT / 'apps/twinpulse-web/dist').rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.resolve()
    node = shutil.which('node')
    chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
    if not node or not chrome.is_file(): parser.error('Existing Node/Chrome required')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['TWINPULSE_STATE_DIR'] = str(output / 'isolated-state')
    for name in ('TWINPULSE_BRIDGE_URL', 'TWINPULSE_ENGINE_BOOTSTRAP', 'TWINPULSE_API_KEY'): os.environ.pop(name, None)
    result = dict(status='FAIL', data='user_photo_approximate_geometry_existing_local_Burger',
                  boundary='browser_API_broker_production_bridge_actual_Isaac', robot_connections=0,
                  provider_calls=0, physics_run='NOT_RUN', physical_validation='NOT_RUN', alignment_verified=False)
    sim = server = bridge = child = None
    try:
        sources = source_hashes()
        draft, manifest, _ = load_bedroom_source()
        app, workflow, broker, original, _, _ = selection_fixture(output / 'isolated-state')
        original_bytes = app._project_store.path.read_bytes()
        from isaacsim import SimulationApp
        sim = SimulationApp({'headless': True, 'width': 960, 'height': 720})
        import omni.usd
        import omni.timeline
        from pxr import Gf, Usd, UsdGeom, UsdPhysics
        from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
        omni.usd.get_context().new_stage()
        for _ in range(10): sim.update()
        sys.path.insert(0, str(ROOT / 'extensions/twinpulse.extension'))
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.bridge_client import BridgeClient
        from twinpulse.extension.bedroom_preview import PREVIEW_PATH
        runtime = TwinPulseRuntime(); adapter = IsaacSimulationAdapter(runtime)
        stage = omni.usd.get_context().get_stage()
        UsdGeom.Xform.Define(stage, '/ExternalKeep').GetPrim().SetCustomDataByKey('marker', 'preserve')
        product_secret, engine_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        server = LocalApiServer(broker, product_bootstrap_secret=product_secret, engine_bootstrap_secret=engine_secret,
            product_workflow=workflow, static_root=ROOT / 'apps/twinpulse-web/dist',
            provider_settings_store=JsonProviderSettingsStore(output / 'isolated-state/settings.json'), credential_store=NoCredentials())
        server.start()
        bridge = BridgeClient(adapter, base_url=server.base_url, bootstrap_secret=engine_secret); bridge.start()
        env = dict(os.environ, TWINPULSE_REHEARSAL_URL=server.base_url, TWINPULSE_REHEARSAL_BOOTSTRAP=product_secret,
                   TWINPULSE_REHEARSAL_OUTPUT=str(output), TWINPULSE_REHEARSAL_CHROME=str(chrome))
        child = subprocess.Popen([node, str(ROOT / 'apps/twinpulse-web/e2e/bedroom-isaac-real.mjs')],
            cwd=ROOT / 'apps/twinpulse-web', env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 180
        seen_replay = {}
        while child.poll() is None and time.monotonic() < deadline:
            sim.update(); bridge.update()
            assert not omni.timeline.get_timeline_interface().is_playing()
            preview = stage.GetPrimAtPath(PREVIEW_PATH)
            if preview and preview.GetCustomDataByKey('replayFrame') is not None:
                index = preview.GetCustomDataByKey('replayFrame')
                seen_replay[index] = list(preview.GetAttribute('xformOp:translate').Get())
                seen_replay[index].append(preview.GetAttribute('xformOp:rotateZ').Get())
            time.sleep(.005)
        if child.poll() is None: raise TimeoutError('Owned browser deadline exceeded')
        browser = json.loads((output / 'browser-result.json').read_text(encoding='utf-8'))
        result['operation_outcomes']=[{'status':op.status,'message':op.receipt.message if op.receipt else None}
                                      for op in broker._operations.values()]
        assert child.returncode == 0 and browser['status'] == 'PASS', 'Browser checks failed'
        assert runtime.compiler.matches_site_scene(draft.site.scene)
        marker = stage.GetPrimAtPath(PREVIEW_PATH)
        assert marker.IsValid()
        assert not stage.GetPrimAtPath('/World/TwinPulse/Robot').IsValid()
        assert not stage.GetPrimAtPath('/World/TwinPulse/Task').IsValid()
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker') == 'preserve'
        assert app.site_draft == original and app._project_store.path.read_bytes() == original_bytes
        assert 'run' not in adapter.snapshot().permitted_commands
        assert load_bedroom_source()[1] == manifest
        assert marker.GetCustomDataByKey('twinpulseManifestSha256') == manifest['manifest_sha256']
        assert marker.GetCustomDataByKey('motionAuthorized') is False
        mission=json.loads((output/'mission.json').read_text(encoding='utf-8'))
        assert marker.GetCustomDataByKey('replayRevision')==mission['revision']
        assert marker.GetCustomDataByKey('replayFrame')==len(mission['events'])
        translation=marker.GetAttribute('xformOp:translate').Get()
        assert all(abs(translation[i]-mission['final_pose'][i])<1e-8 for i in (0,1))
        curve=UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/TwinPulse/Presentation/BedroomTrace'))
        assert len(curve.GetPointsAttr().Get())==len(mission['events'])+1
        result['replay_final_pose']=list(translation)
        result['replay_revision']=mission['revision']
        for frame in (0,len(mission['events'])//2,len(mission['events'])):
            import math
            expected=mission['start_pose'] if frame==0 else mission['events'][frame-1]['pose_after']
            assert all(abs(seen_replay[frame][i]-expected[i])<1e-8 for i in (0,1))
            assert abs(seen_replay[frame][3]-math.degrees(expected[2]))<1e-5
        result['actual_Isaac_replay_samples']=seen_replay
        from twinpulse.extension.bedroom_preview import compose_bedroom_replay
        unchanged=stage.GetRootLayer().ExportToString()
        try:
            compose_bedroom_replay(runtime.compiler,draft,manifest,dict(scenario='route',revision='0'*64,frame=0))
        except ValueError: pass
        else: raise AssertionError('Tampered replay accepted')
        assert stage.GetRootLayer().ExportToString()==unchanged
        result['tampered_replay_no_stage_mutation']=True
        robot_prims = list(Usd.PrimRange(marker, Usd.TraverseInstanceProxies()))
        mesh_count = sum(p.IsA(UsdGeom.Mesh) for p in robot_prims)
        assert mesh_count == 4
        assert not any(p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.CollisionAPI)
                       or p.HasAPI(UsdPhysics.ArticulationRootAPI) for p in robot_prims)
        camera = UsdGeom.Camera(stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera'))
        camera.ClearXformOpOrder()
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(3.7,-5.9,5.1), Gf.Vec3d(0,.15,.35), Gf.Vec3d(0,0,1)).GetInverse())
        camera.CreateClippingRangeAttr(Gf.Vec2f(.01,100)); camera.CreateFocalLengthAttr(30)
        UsdGeom.Imageable(stage.GetPrimAtPath('/World/TwinPulse/Environment/wall_right')).MakeInvisible()
        viewport = get_active_viewport(); viewport.set_active_camera(str(camera.GetPath()))
        for _ in range(45): sim.update()
        capture_viewport_to_file(viewport, str(output / 'actual-Isaac.png'))
        for _ in range(45): sim.update()
        assert (output / 'actual-Isaac.png').stat().st_size > 1000
        stage.GetRootLayer().Export(str(output / 'bedroom-product-stage.usda'))
        saved=Usd.Stage.Open(str(output / 'bedroom-product-stage.usda'))
        assert saved.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey('replayRevision')==mission['revision']
        assert saved.GetPrimAtPath(PREVIEW_PATH).GetAttribute('xformOp:translate').Get()==translation
        result['saved_replay_stage_reopened']=True
        assert sources == source_hashes()
        result.update(status='PASS', browser_checks=browser['checks'], original_project_changed=False,
                      external_prim_preserved=True, manifest_sha256=manifest['manifest_sha256'], scene_revision=draft.site.scene.revision,
                      asset_files=manifest['asset_files_sha256'], source_and_build_sha256=sources,
                      visual_mesh_count=mesh_count, robot_physics_enabled=False)
    except Exception as error:
        result['error_type'] = type(error).__name__
        import traceback
        result['failure_location'] = traceback.extract_tb(error.__traceback__)[-1].lineno
    finally:
        if child is not None and child.poll() is None: child.terminate(); child.wait(timeout=10)
        if bridge: bridge.stop()
        if server: server.stop()
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print('BEDROOM_PRODUCT_REHEARSAL=' + result['status'], flush=True)
        if sim: sim.close()
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
