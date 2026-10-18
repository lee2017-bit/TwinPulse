# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual local Isaac verification of exported native evidence; no robot or Run.

Use existing Isaac Python, a saved bundle, and a NEW output directory. Optional
App-downloaded USDA must exactly match the currently generated final frame.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_3d import export_native_frame_3d

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--app-usda', type=Path)
args = parser.parse_args()
bundle = NativeScanBundle.from_text(args.bundle.read_text(encoding='utf-8'))
data = bundle.to_dict()
args.output.mkdir(parents=True, exist_ok=False)
result = {'status': 'FAIL', 'kind': 'actual_isaac_saved_evidence_import', 'source_kind': data['source']['kind'],
          'bundle_digest': bundle.digest, 'frames': [], 'physics_run': 'NOT_RUN',
          'world_alignment': 'UNVERIFIED', 'physical_validation': 'NOT_RUN',
          'motion_authorized': False, 'robot_connections': 0, 'provider_calls': 0}
app = None
try:
    from isaacsim import SimulationApp
    app = SimulationApp({'headless': True, 'width': 960, 'height': 720})
    import omni.usd
    import omni.timeline
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux
    from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
    context = omni.usd.get_context()
    indices = sorted({0, len(data['frames']) // 2, len(data['frames']) - 1})
    for index in indices:
        exported = export_native_frame_3d(bundle, index)
        if args.app_usda and index == indices[-1]:
            actual = args.app_usda.read_bytes()
            if actual != exported['usda'].encode('utf-8'):
                raise AssertionError('App download differs from reviewed native export')
            result['app_download_sha256'] = hashlib.sha256(actual).hexdigest()
        path = args.output / exported['filename']
        path.write_text(exported['usda'], encoding='utf-8', newline='\n')
        authored = Usd.Stage.Open(str(path.resolve()))
        assert authored
        for prim in authored.Traverse():
            assert prim.GetTypeName() in ('Xform', 'Points', 'BasisCurves'), str(prim.GetPath())
            assert not prim.GetAppliedSchemas()
            assert not prim.HasAuthoredReferences() and not prim.HasAuthoredPayloads()
            assert all(not attr.GetTimeSamples() for attr in prim.GetAttributes())
        expected_paths = {str(p.GetPath()) for p in authored.Traverse()}
        assert len(expected_paths) == 5
        context.open_stage(str(path.resolve()))
        for _ in range(10): app.update()
        stage = context.get_stage()
        assert stage and UsdGeom.GetStageUpAxis(stage) == 'Z'
        assert UsdGeom.GetStageMetersPerUnit(stage) == 1
        layer = stage.GetRootLayer()
        assert not layer.subLayerPaths
        assert len(stage.GetUsedLayers()) <= 2
        root = stage.GetPrimAtPath('/World/TwinPulse/NativeEvidence')
        assert root.GetCustomDataByKey('bundleDigest') == bundle.digest
        assert root.GetCustomDataByKey('frameIndex') == index
        assert root.GetCustomDataByKey('worldAlignmentVerified') is False
        assert root.GetCustomDataByKey('motionAuthorized') is False
        assert root.GetCustomDataByKey('sourceBytesVerified') is False
        returns = UsdGeom.Points(stage.GetPrimAtPath('/World/TwinPulse/NativeEvidence/Returns'))
        expected = bundle.frame_preview(index)['points']
        xyz = list(returns.GetPointsAttr().Get())
        assert len(xyz) == len(expected)
        assert list(returns.GetIdsAttr().Get()) == [p['node_index'] for p in expected]
        for observed, point in zip(xyz, expected, strict=True):
            assert abs(observed[0] - point['x_m']) < 1e-5
            assert abs(observed[1] - point['y_m']) < 1e-5
            assert observed[2] == 0
        for attribute, key in [('nativeAngleDegrees', 'angle_deg'), ('nativeRangeMeters', 'distance_m'),
                               ('nativeQuality', 'quality'), ('sourceByteCursor', 'source_byte_cursor')]:
            assert list(returns.GetPrim().GetAttribute(attribute).Get()) == [p[key] for p in expected]
        usable_ids = {p['node_index'] for p in expected}
        assert list(root.GetAttribute('excludedNodeIndices').Get()) == [p['node_index'] for p in data['frames'][index]['beams'] if p['node_index'] not in usable_ids]
        # Kit can add its own viewport/render settings outside the authored layer.
        # Validate the pristine file above and every authored prim after Kit opens it.
        kit_extra_prims = [{'path': str(p.GetPath()), 'type': p.GetTypeName()}
                           for p in stage.Traverse() if str(p.GetPath()) not in expected_paths]
        for extra in kit_extra_prims:
            assert ((extra['path'] == '/Render' or extra['path'].startswith('/Render/'))
                    and extra['type'] in ('', 'RenderProduct', 'RenderSettings', 'RenderVar')) or (
                    extra['path'] in ('/OmniverseKit_Persp', '/OmniverseKit_Front', '/OmniverseKit_Top', '/OmniverseKit_Right')
                    and extra['type'] == 'Camera'), extra
        for prim_path in expected_paths:
            prim = stage.GetPrimAtPath(prim_path)
            assert prim.GetTypeName() in ('Xform', 'Points', 'BasisCurves')
            assert not prim.GetAppliedSchemas()
            assert not prim.HasAuthoredReferences() and not prim.HasAuthoredPayloads()
            assert all(not attr.GetTimeSamples() for attr in prim.GetAttributes())
        # Preview aids belong solely to this new evidence stage, never a user stage.
        camera_path = '/World/TwinPulse/NativeEvidence/PreviewCamera'
        camera = UsdGeom.Camera.Define(stage, camera_path)
        extent = max(1.0, max((math.hypot(p['x_m'], p['y_m']) for p in expected), default=1))
        eye = Gf.Vec3d(0, -extent * .7, extent * 2.8)
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, Gf.Vec3d(0), Gf.Vec3d(0, 1, 0)).GetInverse())
        camera.CreateClippingRangeAttr(Gf.Vec2f(.01, 500))
        camera.CreateFocalLengthAttr(30)
        UsdLux.DomeLight.Define(stage, '/World/TwinPulse/NativeEvidence/PreviewLight').CreateIntensityAttr(1500)
        viewport = get_active_viewport()
        assert viewport, 'No actual viewport available'
        viewport.set_active_camera(camera_path)
        for _ in range(45): app.update()
        capture = args.output / f'frame-{index:03d}.png'
        capture_viewport_to_file(viewport, str(capture.resolve()))
        for _ in range(90):
            app.update()
            if capture.is_file() and capture.stat().st_size > 1000: break
        assert capture.is_file() and capture.stat().st_size > 1000, 'Viewport capture missing'
        assert not omni.timeline.get_timeline_interface().is_playing(), 'Evidence import started a timeline'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == exported['sha256'], 'Original USD file was changed'
        result['frames'].append({'index': index, 'point_count': len(xyz), 'export_sha256': exported['sha256'],
                                 'kit_extra_prims': kit_extra_prims,
                                 'capture': capture.name, 'capture_sha256': hashlib.sha256(capture.read_bytes()).hexdigest()})
    result['status'] = 'PASS'
except Exception as error:
    result['error_type'] = type(error).__name__
    traceback.print_exc()
finally:
    result['source_hashes'] = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [ROOT / 'packages/twinpulse_core/src/twinpulse_core/native_scan.py',
                                       ROOT / 'packages/twinpulse_core/src/twinpulse_core/native_scan_3d.py', Path(__file__).resolve()]}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('NATIVE_3D_RESULT=' + json.dumps(result), flush=True)
    if app: app.close()
sys.exit(0 if result['status'] == 'PASS' else 1)
