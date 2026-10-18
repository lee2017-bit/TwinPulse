# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Compose a reviewed approximate room and local Burger visual; no Run authority.

Separate from RobotProfile/mission execution. The robot's Physics=none variant
ensures opening this preview cannot create an uncontrolled articulated robot.
"""
from pathlib import Path
from hashlib import sha256

from pxr import Gf, Usd, UsdGeom, UsdPhysics
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_app.bedroom_twin import bedroom_manifest

PREVIEW_PATH = "/World/TwinPulse/Presentation/BurgerPhotoPreview"


def compose_simulation_preview(compiler, value):
    """Current checked SIM spawn, fixed local visual asset, no Physics or Run."""
    import math
    from twinpulse_core.site_simulation import checked_plan
    from twinpulse_app.simulation_assets import ASSET_ROOT, burger_inventory
    plan = checked_plan(compiler.site_scene, value)
    if plan['asset_files'] != burger_inventory():
        raise ValueError('SIM_ASSET_BYTES_CHANGED')
    result=_compose_fixed_burger(compiler,[*plan['start'],plan['yaw_rad']],plan['spawn_z_m'],
        {'poseStatus':'ILLUSTRATIVE_SIM_SPAWN_NOT_MEASURED','simulationPlanId':plan['plan_id'],
         'sceneRevision':plan['scene_revision'],'assetFilesSha256':canonical_sha256(plan['asset_files'])})
    if plan.get('schema_version')=='site-goal-demonstration-1.0':
        path='/World/TwinPulse/Presentation/GoalRoutePreview'
        curve=UsdGeom.BasisCurves.Define(compiler.stage,path)
        points=[plan['start'],*plan['route']]
        curve.CreateTypeAttr('linear');curve.CreateCurveVertexCountsAttr([len(points)])
        curve.CreatePointsAttr([Gf.Vec3f(p[0],p[1],plan['spawn_z_m']+.01) for p in points])
        curve.CreateWidthsAttr([.012]);curve.SetWidthsInterpolation('constant')
        curve.CreateDisplayColorAttr([Gf.Vec3f(1.,.65,.2)])
        curve.GetPrim().SetCustomDataByKey('reviewId',plan['review']['plan_id'])
        curve.GetPrim().SetCustomDataByKey('physicalAuthority',False)
        curve.GetPrim().SetCustomDataByKey('poseStatus','REVIEWED_SENSOR_START_NOT_LIVE')
    return {**result,'plan_id':plan['plan_id']}


def _compose_fixed_burger(compiler, pose, spawn_z, metadata):
    """Shared fixed asset composition. Caller supplies checked scene/pose only."""
    import math
    from twinpulse_app.simulation_assets import ASSET_ROOT, burger_inventory
    burger_inventory()
    entry = ASSET_ROOT / 'turtlebot3_burger.usda'
    source = Usd.Stage.Open(str(entry))
    if (not source or not source.GetDefaultPrim() or
            'none' not in source.GetDefaultPrim().GetVariantSet('Physics').GetVariantNames()):
        raise ValueError('SIM_VISUAL_VARIANT_MISSING')
    stage = compiler.stage
    root = stage.GetPrimAtPath('/World/TwinPulse')
    if not root or not compiler._is_owned_root(root) or not compiler.matches_site_scene(compiler.site_scene):
        raise RuntimeError('SIM_PREVIEW_CURRENT_OWNED_ROOM_REQUIRED')
    stage.RemovePrim(PREVIEW_PATH)
    try:
        placement = UsdGeom.Xform.Define(stage, PREVIEW_PATH)
        placement.AddTranslateOp().Set(Gf.Vec3d(pose[0],pose[1],spawn_z))
        placement.AddRotateZOp().Set(math.degrees(pose[2]))
        model = stage.DefinePrim(PREVIEW_PATH + '/Model', 'Xform')
        model.GetReferences().AddReference(str(entry))
        model.GetVariantSet('Physics').SetVariantSelection('none')
        prims = list(Usd.PrimRange(model, Usd.TraverseInstanceProxies()))
        for prim in prims:
            if prim.HasAPI(UsdPhysics.CollisionAPI) and not prim.IsInstanceProxy():
                prim.RemoveAPI(UsdPhysics.CollisionAPI)
        if any(p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.ArticulationRootAPI)
               or p.HasAPI(UsdPhysics.CollisionAPI) for p in prims):
            raise ValueError('SIM_VISUAL_PHYSICS_SCHEMAS_PRESENT')
        meshes = [p for p in prims if p.IsA(UsdGeom.Mesh)]
        if not meshes:
            raise ValueError('SIM_VISUAL_MESH_MISSING')
        marker = placement.GetPrim()
        for key, item in {**metadata,'motionAuthorized':False,'worldAlignmentVerified':False}.items():
            marker.SetCustomDataByKey(key, item)
        return {'mesh_count':len(meshes), 'physics_variant':'none'}
    except Exception:
        stage.RemovePrim(PREVIEW_PATH)
        raise


def compose_inspection_preview(compiler, visual):
    """Historical candidate from the checked current-chat report, not live pose."""
    scene=compiler.site_scene
    floors=[o for o in scene.objects if o.kind=='floor']
    if len(floors)!=1:raise ValueError('INSPECTION_DISPLAY_FLOOR_REQUIRED')
    floor=floors[0]
    z=floor.transform.position_m[2]+floor.shape.dimensions_m[2]/2+.002
    result=_compose_fixed_burger(compiler,visual['pose_room'],z,
        {'poseStatus':'HISTORICAL_SURVEY_CANDIDATE_NOT_CURRENT','sceneRevision':scene.revision,
         'currentPoseAvailable':False,'missionSessionId':visual['session_id']})
    compose_automatic_mission_visual(compiler,{'robot_placement':{'position_m':[0.,0.,z]}},visual)
    # Scan hits on vertical walls are otherwise occluded by the wall tops in
    # the survey overview. Lift only the annotation, never geometry/raw XYZ.
    overlay=compiler.stage.GetPrimAtPath('/World/TwinPulse/Presentation/AutomaticMission')
    overlay_z=max([z]+[o.transform.position_m[2]+o.shape.dimensions_m[2]/2
                      for o in scene.objects if o.kind=='wall' and o.shape.type=='box'])+.03
    cloud=UsdGeom.Points(compiler.stage.GetPrimAtPath(str(overlay.GetPath())+'/Scan'))
    cloud.GetPointsAttr().Set([Gf.Vec3f(p[0],p[1],overlay_z) for p in visual['scan_room']])
    cloud.GetWidthsAttr().Set([.025]*len(visual['scan_room']))
    trace=UsdGeom.BasisCurves(compiler.stage.GetPrimAtPath(str(overlay.GetPath())+'/Trace'))
    if trace:trace.GetPointsAttr().Set([Gf.Vec3f(p[0],p[1],z+.015) for p in visual['trajectory_room']])
    overlay.SetCustomDataByKey('annotationHeightIsPresentationOnly',True)
    marker=compiler.stage.GetPrimAtPath(PREVIEW_PATH)
    marker.SetCustomDataByKey('poseStatus','HISTORICAL_SURVEY_CANDIDATE_NOT_CURRENT')
    marker.SetCustomDataByKey('currentPoseAvailable',False)
    overlay.SetCustomDataByKey('currentPoseAvailable',False)
    return result


def compose_bedroom_preview(compiler, draft, manifest, asset_root, *, pinned_project_visual=False,
                            reviewed_scene=None, presentation=None):
    checked = SiteDraftRecord.from_dict(draft.to_dict())
    asset_root = Path(asset_root).resolve()
    paths = sorted(path for path in asset_root.rglob("*") if path.is_file())
    if not paths or any(not path.resolve().is_relative_to(asset_root) for path in paths):
        raise ValueError("Local Burger asset directory is invalid")
    hashes = {p.relative_to(asset_root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths}
    if pinned_project_visual:
        body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if (manifest.get("schema_version") != "project-room-visual-1.0"
                or manifest.get("manifest_sha256") != canonical_sha256(body)
                or manifest.get("draft_sha256") != canonical_sha256(checked.to_dict())
                or manifest.get("scene_revision") != checked.site.scene.revision
                or manifest.get("asset_files_sha256") != hashes):
            raise ValueError("Project room/Burger manifest differs from current source bytes")
    else:
        expected = bedroom_manifest(checked, hashes)
        if canonical_sha256(manifest) != canonical_sha256(expected):
            raise ValueError("Room/asset manifest differs from current source bytes")
    entry = asset_root / "turtlebot3_burger.usda"
    if not entry.is_file():
        raise ValueError("Existing Burger entry is missing")
    # Validate the composed asset in its own stage before editing the user's stage.
    source = Usd.Stage.Open(str(entry))
    if not source or not source.GetDefaultPrim():
        raise ValueError("Burger default prim missing")
    variants = source.GetDefaultPrim().GetVariantSet("Physics")
    if "none" not in variants.GetVariantNames():
        raise ValueError("Visual-only Physics variant missing")
    scene = reviewed_scene if reviewed_scene is not None else checked.site.scene
    compiler.compile_site_scene(scene, presentation=presentation)
    stage = compiler.stage
    stage.RemovePrim('/World/TwinPulse/Presentation/BedroomTrace')
    stage.RemovePrim('/World/TwinPulse/Presentation/RecordedRoomScan')
    # This owned preview is replaceable; never mutate imported source layers.
    stage.RemovePrim(PREVIEW_PATH)
    placement = UsdGeom.Xform.Define(stage, PREVIEW_PATH)
    placement.AddTranslateOp().Set(Gf.Vec3d(*manifest["robot_placement"]["position_m"]))
    placement.AddRotateZOp().Set(manifest["robot_placement"]["yaw_deg"])
    model = stage.DefinePrim(PREVIEW_PATH + "/Model", "Xform")
    model.GetReferences().AddReference(str(entry))
    model.GetVariantSet("Physics").SetVariantSelection("none")
    prims = list(Usd.PrimRange(model, Usd.TraverseInstanceProxies()))
    # The importer keeps collision shapes in its base layer even for Physics=none.
    # Remove only their API in our stronger preview layer; never edit the source.
    for prim in prims:
        if prim.HasAPI(UsdPhysics.CollisionAPI) and not prim.IsInstanceProxy():
            prim.RemoveAPI(UsdPhysics.CollisionAPI)
    if any(p.HasAPI(UsdPhysics.RigidBodyAPI) or p.HasAPI(UsdPhysics.ArticulationRootAPI)
           or p.HasAPI(UsdPhysics.CollisionAPI) for p in prims):
        stage.RemovePrim(PREVIEW_PATH)
        raise ValueError("Visual preview unexpectedly contains physical control schemas")
    meshes = [p for p in prims if p.IsA(UsdGeom.Mesh)]
    if not meshes:
        stage.RemovePrim(PREVIEW_PATH)
        raise ValueError("Burger visual mesh missing")
    marker = placement.GetPrim()
    marker.SetCustomDataByKey("twinpulseManifestSha256", manifest["manifest_sha256"])
    marker.SetCustomDataByKey("poseStatus", "ILLUSTRATIVE_NOT_MEASURED")
    marker.SetCustomDataByKey("motionAuthorized", False)
    marker.SetCustomDataByKey("worldAlignmentVerified", False)
    marker.SetCustomDataByKey("assetFilesSha256", canonical_sha256(hashes))
    root = stage.GetPrimAtPath("/World/TwinPulse")
    root.SetCustomDataByKey("geometryStatus", manifest["geometry_status"])
    root.SetCustomDataByKey("photoSha256", manifest["photo_sha256"])
    root.SetCustomDataByKey("worldAlignmentVerified", False)
    # Presentation colors affect neither scene geometry nor its identity.
    palette = {"floor": (.62, .49, .34), "bed": (.59, .64, .69),
               "wardrobe": (.82, .80, .70), "wardrobe_open_door": (.75, .73, .64),
               "desk": (.38, .24, .12), "chair": (.065, .08, .09),
               "fan_boxes": (.12, .23, .33), "bag": (.025, .04, .045),
               "left_luggage": (.23, .27, .16)}
    for name, color in palette.items():
        prim = stage.GetPrimAtPath(f"/World/TwinPulse/Environment/{name}/geometry")
        if prim.IsValid():
            UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if not compiler.matches_site_scene(scene):
        raise RuntimeError("Visual composition changed the source scene geometry")
    return {"scene_revision": scene.revision, "mesh_count": len(meshes),
            "manifest_sha256": manifest["manifest_sha256"], "robot_path": PREVIEW_PATH,
            "physics_variant": "none", "physical_validation": "NOT_RUN"}


def compose_bedroom_replay(compiler, draft, manifest, descriptor):
    """Explicit seek of synthetic samples. Never starts timeline/physics or interpolates observations."""
    import math
    from twinpulse_app.bedroom_rehearsal import checked_replay
    result = checked_replay(draft, manifest, descriptor)
    stage = compiler.stage
    marker = stage.GetPrimAtPath(PREVIEW_PATH)
    if (not marker or marker.GetCustomDataByKey('twinpulseManifestSha256') != manifest['manifest_sha256']
            or marker.GetCustomDataByKey('motionAuthorized') is not False
            or not compiler.matches_site_scene(draft.site.scene)):
        raise ValueError('Matching visual-only room required')
    frame = descriptor['frame']
    poses = [result['start_pose']] + [e['pose_after'] for e in result['events'][:frame]]
    pose = poses[-1]
    # Keep the original ordered double translation / float rotation attributes.
    # AddXformOp's default precision would conflict with AddRotateZOp's float.
    translation = marker.GetAttribute('xformOp:translate')
    rotation = marker.GetAttribute('xformOp:rotateZ')
    if not translation or not rotation:
        raise ValueError('Visual placement transform attributes missing')
    translation.Set(Gf.Vec3d(pose[0],pose[1],manifest['robot_placement']['position_m'][2]))
    rotation.Set(math.degrees(pose[2]))
    trace_path = '/World/TwinPulse/Presentation/BedroomTrace'
    stage.RemovePrim(trace_path)
    if len(poses) > 1:
        curve = UsdGeom.BasisCurves.Define(stage, trace_path)
        curve.CreateTypeAttr('linear'); curve.CreateCurveVertexCountsAttr([len(poses)])
        curve.CreatePointsAttr([Gf.Vec3f(p[0],p[1],.015) for p in poses])
        curve.CreateWidthsAttr([.008]); curve.SetWidthsInterpolation('constant')
        curve.CreateDisplayColorAttr([Gf.Vec3f(.12,.9,.65)])
    marker.SetCustomDataByKey('replayRevision',result['revision'])
    marker.SetCustomDataByKey('replayFrame',frame)
    marker.SetCustomDataByKey('replayProvenance',result['provenance'])
    marker.SetCustomDataByKey('poseStatus','SYNTHETIC_KINEMATIC_NOT_MEASURED')
    return pose


def compose_saved_scan_preview(compiler,draft,manifest,descriptor):
    """Historical candidate overlay only; never physics, Run or measured TF."""
    import math
    from twinpulse_app.room_localization_review import checked_localization_visual
    result=checked_localization_visual(descriptor,draft)
    stage=compiler.stage;marker=stage.GetPrimAtPath(PREVIEW_PATH)
    if not marker or marker.GetCustomDataByKey('motionAuthorized') is not False:
        raise ValueError('Visual-only Burger preview required')
    pose=result['robot_pose_room_candidate']
    marker.GetAttribute('xformOp:translate').Set(Gf.Vec3d(pose[0],pose[1],manifest['robot_placement']['position_m'][2]))
    marker.GetAttribute('xformOp:rotateZ').Set(math.degrees(pose[2]))
    path='/World/TwinPulse/Presentation/RecordedRoomScan';stage.RemovePrim(path)
    cloud=UsdGeom.Points.Define(stage,path)
    cloud.CreatePointsAttr([Gf.Vec3f(p[0],p[1],result['scan_height_m']) for p in result['scan_points_room_candidate']])
    cloud.CreateWidthsAttr([.018]*len(result['scan_points_room_candidate']))
    cloud.CreateDisplayColorAttr([Gf.Vec3f(.18,.92,.80)])
    cloud.GetPrim().SetCustomDataByKey('mappingStatus',result['match']['status'])
    cloud.GetPrim().SetCustomDataByKey('sourceRevision',result['source_revision'])
    cloud.GetPrim().SetCustomDataByKey('sourceStampNs',str(result['stamp_ns']))
    poses=[p['pose'] for p in result['trajectory_candidate']]
    if len(poses)>1:
        curve=UsdGeom.BasisCurves.Define(stage,'/World/TwinPulse/Presentation/BedroomTrace')
        curve.CreateTypeAttr('linear');curve.CreateCurveVertexCountsAttr([len(poses)])
        curve.CreatePointsAttr([Gf.Vec3f(p[0],p[1],.015) for p in poses])
        curve.CreateWidthsAttr([.008]);curve.SetWidthsInterpolation('constant')
        curve.CreateDisplayColorAttr([Gf.Vec3f(.95,.65,.2)])
    marker.SetCustomDataByKey('poseStatus','SAVED_SCAN_MATCH_CANDIDATE_NOT_CALIBRATED')
    marker.SetCustomDataByKey('mappingStatus',result['match']['status'])
    marker.SetCustomDataByKey('worldAlignmentVerified',False)
    return pose


def compose_automatic_mission_visual(compiler,manifest,visual):
    """Checked immutable mission report, never control/physics/timeline input."""
    import math
    stage=compiler.stage;marker=stage.GetPrimAtPath(PREVIEW_PATH)
    if not marker or marker.GetCustomDataByKey('motionAuthorized') is not False:
        raise ValueError('Visual-only Burger preview required')
    pose=visual['pose_room']
    marker.GetAttribute('xformOp:translate').Set(Gf.Vec3d(pose[0],pose[1],manifest['robot_placement']['position_m'][2]))
    marker.GetAttribute('xformOp:rotateZ').Set(math.degrees(pose[2]))
    base='/World/TwinPulse/Presentation/AutomaticMission';stage.RemovePrim(base)
    root=UsdGeom.Xform.Define(stage,base).GetPrim()
    for key in ('session_id','revision','room_revision','map_revision','alignment_revision','route_revision','provenance'):
        root.SetCustomDataByKey(key,str(visual.get(key) or 'UNAVAILABLE'))
    root.SetCustomDataByKey('motionAuthorized',False)
    root.SetCustomDataByKey('physicalValidation','NOT_RUN')
    cloud=UsdGeom.Points.Define(stage,base+'/Scan')
    cloud.CreatePointsAttr([Gf.Vec3f(p[0],p[1],.18) for p in visual['scan_room']])
    cloud.CreateWidthsAttr([.015]*len(visual['scan_room']))
    cloud.CreateDisplayColorAttr([Gf.Vec3f(.18,.92,.80)])
    for name,points,color in (('Trace',visual['trajectory_room'],(.18,.8,.6)),
                              ('Route',[pose[:2]]+visual['route_room'],(.95,.65,.2))):
        if len(points)<2:continue
        curve=UsdGeom.BasisCurves.Define(stage,base+'/'+name)
        curve.CreateTypeAttr('linear');curve.CreateCurveVertexCountsAttr([len(points)])
        curve.CreatePointsAttr([Gf.Vec3f(p[0],p[1],.018) for p in points])
        curve.CreateWidthsAttr([.008]);curve.SetWidthsInterpolation('constant')
        curve.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if visual.get('goal_room') is not None:
        goal=UsdGeom.Points.Define(stage,base+'/Goal');p=visual['goal_room']
        goal.CreatePointsAttr([Gf.Vec3f(p[0],p[1],.025)]);goal.CreateWidthsAttr([.08])
        goal.CreateDisplayColorAttr([Gf.Vec3f(.95,.65,.2)])
    marker.SetCustomDataByKey('poseStatus','CURRENT_SENSOR_CANDIDATE_SAVED_REPORT_NOT_CALIBRATED')
    marker.SetCustomDataByKey('missionSessionId',visual['session_id'])
    marker.SetCustomDataByKey('missionVisualRevision',visual['revision'])
    return pose
