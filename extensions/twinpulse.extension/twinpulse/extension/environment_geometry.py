# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Author checked derived environment meshes; retain source paths as provenance."""
from pxr import Gf,UsdGeom,UsdPhysics,Vt

ROOT='/World/TwinPulse/Environment'


def author_environment(stage,environment):
    from twinpulse_core.environment_source import checked_environment
    from twinpulse_core.environment_overlays import overlay_meshes
    environment=checked_environment(environment)
    root=stage.GetPrimAtPath(ROOT)
    root.SetCustomDataByKey('twinpulseEnvironmentSource',environment['source_sha256'])
    root.SetCustomDataByKey('twinpulseEnvironmentUnitsBasis',environment['units_basis'])
    root.SetCustomDataByKey('twinpulseEnvironmentMetersPerUnit',environment['meters_per_unit'])
    for source in environment['meshes']+overlay_meshes(environment):
        obj=UsdGeom.Xform.Define(stage,ROOT+'/'+source['id'])
        obj.AddTranslateOp().Set(Gf.Vec3d(*source['translation_m']))
        obj.GetPrim().SetCustomDataByKey('sourcePrimPath',source['source_path'])
        obj.GetPrim().SetCustomDataByKey('environmentCategory',source['category'])
        obj.GetPrim().SetCustomDataByKey('environmentLabel',source['label'])
        if 'synthetic_keepout' in source:
            obj.GetPrim().SetCustomDataByKey('syntheticKeepout',source['synthetic_keepout'])
            import json
            obj.GetPrim().SetCustomDataByKey('estimatedEvidence',json.dumps(source['evidence'],sort_keys=True))
        geom=UsdGeom.Mesh.Define(stage,str(obj.GetPath())+'/geometry')
        geom.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in source['points_m']]))
        geom.CreateFaceVertexCountsAttr([3]*len(source['triangles']))
        geom.CreateFaceVertexIndicesAttr([i for t in source['triangles'] for i in t])
        geom.CreateSubdivisionSchemeAttr('none');geom.CreateDoubleSidedAttr(True)
        geom.CreateDisplayColorAttr([Gf.Vec3f(*source['color_rgb'])])
        if source.get('synthetic_keepout',False):
            geom.GetPrim().SetCustomDataByKey('syntheticKeepout',True)
            geom.CreateVisibilityAttr('invisible')
        if source.get('collision',True):
            UsdPhysics.CollisionAPI.Apply(geom.GetPrim())
            UsdPhysics.MeshCollisionAPI.Apply(geom.GetPrim()).CreateApproximationAttr('none')
    root.SetCustomDataByKey('twinpulseEnvironmentRevision',stage.GetPrimAtPath('/World/TwinPulse').GetCustomDataByKey('twinpulseSiteSceneRevision'))


def matches_environment(stage,environment):
    from twinpulse_core.environment_overlays import overlay_meshes
    root=stage.GetPrimAtPath(ROOT)
    if (not root or root.GetCustomDataByKey('twinpulseEnvironmentSource')!=environment['source_sha256']
            or root.GetCustomDataByKey('twinpulseEnvironmentUnitsBasis')!=environment['units_basis']
            or root.GetCustomDataByKey('twinpulseEnvironmentMetersPerUnit')!=environment['meters_per_unit']):return False
    sources=environment['meshes']+overlay_meshes(environment)
    if {c.GetName() for c in root.GetChildren()}!={m['id'] for m in sources}:return False
    for source in sources:
        obj=stage.GetPrimAtPath(ROOT+'/'+source['id']);geom=UsdGeom.Mesh.Get(stage,str(obj.GetPath())+'/geometry')
        if (not obj.IsA(UsdGeom.Xform) or not geom or len(obj.GetChildren())!=1 or
                obj.GetCustomDataByKey('sourcePrimPath')!=source['source_path'] or
                obj.GetCustomDataByKey('environmentCategory')!=source['category'] or
                obj.GetCustomDataByKey('environmentLabel')!=source['label'] or
                obj.HasAPI(UsdPhysics.RigidBodyAPI) or
                geom.GetPrim().HasAPI(UsdPhysics.CollisionAPI)!=source.get('collision',True) or
                source.get('collision',True) and geom.GetPrim().GetAttribute('physics:approximation').Get()!='none'):return False
        synthetic=source.get('synthetic_keepout',False)
        if (bool(geom.GetPrim().GetCustomDataByKey('syntheticKeepout'))!=synthetic or
                geom.GetVisibilityAttr().Get()!=('invisible' if synthetic else 'inherited')):return False
        if 'evidence' in source:
            import json
            if (obj.GetCustomDataByKey('syntheticKeepout')!=synthetic or
                    obj.GetCustomDataByKey('estimatedEvidence')!=json.dumps(source['evidence'],sort_keys=True)):return False
        ops=UsdGeom.Xformable(obj).GetOrderedXformOps()
        if len(ops)!=1 or any(abs(float(a)-b)>1e-7 for a,b in zip(ops[0].Get(),source['translation_m'])):return False
        points=geom.GetPointsAttr().Get()
        if (len(points)!=len(source['points_m']) or
                any(abs(float(a)-b)>1e-5 for p,q in zip(points,source['points_m']) for a,b in zip(p,q)) or
                list(geom.GetFaceVertexCountsAttr().Get())!=[3]*len(source['triangles']) or
                list(geom.GetFaceVertexIndicesAttr().Get())!=[i for t in source['triangles'] for i in t] or
                UsdGeom.Xformable(geom).GetOrderedXformOps() or geom.GetSubdivisionSchemeAttr().Get()!='none'):
            return False
    return True
