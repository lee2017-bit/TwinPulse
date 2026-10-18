# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual Isaac import evidence in a new isolated process; no real robot or Run."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/robot-models/burger-isaac"
OUTPUT.mkdir(parents=True, exist_ok=True)
from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 960, "height": 720})
result = {"status": "FAIL", "physical_robot_match": "UNVERIFIED", "motion_authorized": False}
try:
    import omni.kit.app
    import omni.usd
    from pxr import Usd, UsdGeom, UsdLux, Gf
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.set_extension_enabled_immediate("isaacsim.asset.importer.urdf", True)
    for _ in range(5):
        app.update()
    from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
    config = URDFImporterConfig(
        urdf_path=str(ROOT / "artifacts/robot-models/burger-prepared/turtlebot3_burger.urdf"),
        usd_path=str(OUTPUT / "usd"), fix_base=False, collision_from_visuals=False,
        joint_target_type="velocity", override_joint_stiffness=0.0)
    importer = URDFImporter(config)
    path = importer.import_urdf()
    if not path:
        raise RuntimeError("Importer returned no USD")
    context = omni.usd.get_context()
    context.open_stage(str(path))
    for _ in range(30):
        app.update()
    stage = context.get_stage()
    for prim in stage.Traverse():
        variants = prim.GetVariantSet("Physics")
        if "physx" in variants.GetVariantNames():
            variants.SetVariantSelection("physx")
    prims = list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))
    joints = [p.GetName() for p in prims if p.GetTypeName() == "PhysicsRevoluteJoint"]
    if not all(name in joints for name in ("wheel_left_joint", "wheel_right_joint")):
        raise RuntimeError("Expected wheel joints missing")
    meshes = [p for p in prims if p.GetTypeName() == "Mesh"]
    if not meshes:
        raise RuntimeError("No visual mesh imported")
    result.update(status="IMPORT_STRUCTURE_PASS", usd_path=str(path), mesh_count=len(meshes),
                  revolute_joints=joints, physics_run="NOT_RUN", sensor_emulation="NOT_CONFIGURED")
    UsdLux.DomeLight.Define(stage, "/PreviewLight").CreateIntensityAttr(1000)
    camera = UsdGeom.Camera.Define(stage, "/PreviewCamera")
    eye, target = Gf.Vec3d(0.55, 0.55, 0.40), Gf.Vec3d(0, 0, 0.12)
    matrix = Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1)).GetInverse()
    camera.AddTransformOp().Set(matrix)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100))
    camera.CreateFocalLengthAttr(35)
    from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
    viewport = get_active_viewport()
    viewport.set_active_camera("/PreviewCamera")
    for _ in range(60):
        app.update()
    capture = OUTPUT / "burger-import.png"
    capture_viewport_to_file(viewport, str(capture))
    for _ in range(60):
        app.update()
    result["capture"] = str(capture) if capture.exists() else None
    stage.GetRootLayer().Export(str(OUTPUT / "preview.usda"))
except Exception as exc:
    import traceback
    traceback.print_exc()
    result.update(error_type=type(exc).__name__, error=str(exc))
finally:
    (OUTPUT / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("TWINPULSE_BURGER_IMPORT=" + json.dumps(result), flush=True)
    app.close()
sys.exit(0 if result["status"] == "IMPORT_STRUCTURE_PASS" and result.get("capture") else 1)
