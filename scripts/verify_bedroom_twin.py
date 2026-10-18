# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual isolated Isaac photo-room/Burger composition verification, no timeline Run."""
import argparse
import copy
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
for package in ("twinpulse_core", "twinpulse_app", "twinpulse_provider"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))
sys.path.insert(0, str(ROOT / "extensions/twinpulse.extension"))
from prepare_bedroom_twin import prepare, ASSET_ROOT, asset_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--saved-localization", help="Fixed saved localization report ID; historical visual only")
    args = parser.parse_args()
    output = args.output.resolve()
    draft, manifest = prepare(output)
    result = {"status": "FAIL", "physical_validation": "NOT_RUN", "physics_run": "NOT_RUN",
              "product_app_integration": "PENDING", "geometry_status": "PHOTO_APPROXIMATION_NOT_SURVEYED",
              "checks": [], "robot_connections": 0, "provider_calls": 0}
    app = None
    before = asset_hashes()
    try:
        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True, "width": 1280, "height": 960})
        import omni.usd
        import omni.timeline
        from pxr import Gf, Usd, UsdGeom
        from twinpulse.extension.scene_compiler import SceneCompiler
        from twinpulse.extension.bedroom_preview import compose_bedroom_preview, PREVIEW_PATH
        from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
        context = omni.usd.get_context()
        context.new_stage()
        for _ in range(10): app.update()
        stage = context.get_stage()
        UsdGeom.Xform.Define(stage, "/ExternalKeep").GetPrim().SetCustomDataByKey("marker", "untouched")
        compiler = SceneCompiler()
        result["composition"] = compose_bedroom_preview(compiler, draft, manifest, ASSET_ROOT)
        if args.saved_localization:
            import re
            if not re.fullmatch('[a-f0-9]{32}-[a-f0-9]{32}',args.saved_localization):
                raise ValueError('LOCALIZATION_VISUAL_DESCRIPTOR')
            from twinpulse.extension.bedroom_preview import compose_saved_scan_preview
            from twinpulse_app.room_localization_review import checked_localization_visual
            report_path=ROOT/'artifacts/room-localization-review'/(args.saved_localization+'.json')
            report=json.loads(report_path.read_text(encoding='utf-8'))
            descriptor={'report_id':args.saved_localization,'revision':report['revision']}
            checked=checked_localization_visual(descriptor,draft)
            pose=compose_saved_scan_preview(compiler,draft,manifest,descriptor)
            assert pose==checked['robot_pose_room_candidate']
            cloud=UsdGeom.Points(stage.GetPrimAtPath('/World/TwinPulse/Presentation/RecordedRoomScan'))
            assert len(cloud.GetPointsAttr().Get())==len(checked['scan_points_room_candidate'])
            assert stage.GetPrimAtPath(PREVIEW_PATH).GetCustomDataByKey('worldAlignmentVerified') is False
            result['saved_localization']={'report_id':args.saved_localization,'revision':checked['revision'],
                'status':checked['match']['status'],'point_count':len(cloud.GetPointsAttr().Get()),
                'alignment_verified':False,'motion_authorized':False}
            result['checks'].append('original raw reverified and reprojected into visual-only scan/Burger candidate')
        assert compiler.matches_site_scene(draft.site.scene)
        assert not stage.GetPrimAtPath("/World/TwinPulse/Robot")
        assert not stage.GetPrimAtPath("/World/TwinPulse/Task")
        assert not omni.timeline.get_timeline_interface().is_playing()
        assert stage.GetPrimAtPath("/ExternalKeep").GetCustomDataByKey("marker") == "untouched"
        result["checks"].append("existing compiler room + visual Burger; no driven Robot/Task/Run")
        count = len(list(stage.Traverse()))
        compose_bedroom_preview(compiler, draft, manifest, ASSET_ROOT)
        if args.saved_localization:compose_saved_scan_preview(compiler,draft,manifest,descriptor)
        assert len(list(stage.Traverse())) == count
        result["checks"].append("idempotent visual composition and external prim preserved")
        unchanged = stage.GetRootLayer().ExportToString()
        bad = copy.deepcopy(manifest)
        bad["robot_placement"]["yaw_deg"] = 0
        try:
            compose_bedroom_preview(compiler, draft, bad, ASSET_ROOT)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered placement was accepted")
        assert stage.GetRootLayer().ExportToString() == unchanged
        result["checks"].append("tampered manifest rejected before stage mutation")
        assert asset_hashes() == before
        result["checks"].append("all existing Burger source/dependency bytes unchanged")
        camera = UsdGeom.Camera(stage.GetPrimAtPath("/World/TwinPulse/Presentation/Camera"))
        viewport = get_active_viewport()
        viewport.set_active_camera(str(camera.GetPath()))
        camera.CreateClippingRangeAttr(Gf.Vec2f(.01, 100))
        camera.CreateFocalLengthAttr(30)
        for label, eye, target in (
            ("room-perspective", (3.7, -5.9, 5.1), (0., .15, .35)),
            ("room-photo-view", (0., -4.0, 2.5), (0., .45, .7)),
            ("burger-detail", (.55, -1.35, .5), (0., -.65, .12)),
        ):
            camera.ClearXformOpOrder()
            camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target),
                                                               Gf.Vec3d(0, 0, 1)).GetInverse())
            # Cutaway only for overview rendering, not a collision/map edit.
            UsdGeom.Imageable(stage.GetPrimAtPath("/World/TwinPulse/Environment/wall_right")).MakeInvisible()
            for _ in range(45): app.update()
            capture = output / f"{label}.png"
            capture_viewport_to_file(viewport, str(capture))
            for _ in range(45): app.update()
            assert capture.is_file() and capture.stat().st_size > 1000
        result["checks"].append("actual Isaac overview/photo-angle/detail captures written")
        # Keep a useful overview camera in the export rather than the detail view.
        camera.ClearXformOpOrder()
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(3.7, -5.9, 5.1),
            Gf.Vec3d(0., .15, .35), Gf.Vec3d(0, 0, 1)).GetInverse())
        stage.GetRootLayer().Export(str(output / "bedroom-burger-preview.usda"))
        # Reload the actual artifact to validate persisted reference/variant/provenance.
        saved = Usd.Stage.Open(str(output / "bedroom-burger-preview.usda"))
        marker = saved.GetPrimAtPath(PREVIEW_PATH)
        assert marker.GetCustomDataByKey("motionAuthorized") is False
        assert marker.GetCustomDataByKey("twinpulseManifestSha256") == manifest["manifest_sha256"]
        assert saved.GetPrimAtPath(PREVIEW_PATH + "/Model").GetVariantSet("Physics").GetVariantSelection() == "none"
        result["checks"].append("saved USD reopens with source binding and visual-only asset")
        result["status"] = "ROOM_BURGER_VISUAL_PASS"
    except Exception as exc:
        traceback.print_exc()
        result.update(error_type=type(exc).__name__, error=str(exc))
    finally:
        (output / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("TWINPULSE_BEDROOM=" + json.dumps(result), flush=True)
        if app: app.close()
    return 0 if result["status"] == "ROOM_BURGER_VISUAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
