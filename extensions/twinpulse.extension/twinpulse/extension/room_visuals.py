# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""USD display-only catalog over unchanged current scene collision geometry."""
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt
from twinpulse_core.room_visuals import VISUAL_VERSION, visual_bindings, display_meshes

PATH = '/World/TwinPulse/Presentation/RoomModels'


def clear_room_visuals(stage):
    """Restore only proxies hidden by this overlay, including ordinary rebuilds."""
    previous = stage.GetPrimAtPath(PATH)
    if previous:
        for identity in previous.GetCustomDataByKey('proxyIds') or ():
            geometry = stage.GetPrimAtPath('/World/TwinPulse/Environment/'+identity+'/geometry')
            if geometry:
                UsdGeom.Imageable(geometry).CreatePurposeAttr().Set(UsdGeom.Tokens.default_)
        stage.RemovePrim(PATH)


def compose_room_visuals(compiler, scene, plan):
    """No physics API, no external assets, no mutation of typed plan/raw/geometry."""
    if not compiler.matches_site_scene(scene):
        raise ValueError('ROOM_VISUAL_CURRENT_SCENE_REQUIRED')
    bindings, skipped = visual_bindings(scene, plan)
    # Validate/tessellate everything before stage edits; never leave partial recipes.
    recipes = [(binding, display_meshes(binding['kind'], binding['size'], binding.get('parameters'))) for binding in bindings]
    stage = compiler.stage
    layer = stage.GetEditTarget().GetLayer()
    backup = Sdf.Layer.CreateAnonymous('room-display-backup.usda')
    previous = stage.GetPrimAtPath(PATH)
    had_previous = bool(previous)
    if previous:
        if layer.GetPrimAtPath(PATH) is None:
            raise ValueError('ROOM_VISUAL_COMPOSED_OVERLAY_UNSUPPORTED')
        Sdf.CreatePrimInLayer(backup, '/World/TwinPulse/Presentation')
        if not Sdf.CopySpec(layer, PATH, backup, PATH): raise ValueError('ROOM_VISUAL_BACKUP_FAILED')
    # Purpose only changes visibility; collision schemas and shapes stay authored.
    old_purposes = {}
    for obj in scene.objects:
        geometry = stage.GetPrimAtPath('/World/TwinPulse/Environment/'+obj.id+'/geometry')
        old_purposes[obj.id] = (UsdGeom.Imageable(geometry).GetPurposeAttr().Get(),
                               layer.GetPropertyAtPath(str(geometry.GetPath())+'.purpose') is not None)
    try:
        clear_room_visuals(stage)
        overlay = UsdGeom.Xform.Define(stage, PATH).GetPrim()
        overlay.SetCustomDataByKey('catalogVersion', VISUAL_VERSION)
        overlay.SetCustomDataByKey('sceneRevision', scene.revision)
        overlay.SetCustomDataByKey('appearanceStatus', 'ILLUSTRATIVE_CATALOG_NOT_PHOTO_EXACT')
        overlay.SetCustomDataByKey('motionAuthorized', False)
        materials = {}
        count = 0
        for binding, parts in recipes:
            group = UsdGeom.Xform.Define(stage, PATH+'/Item_'+binding['id'])
            group.AddTranslateOp().Set(Gf.Vec3d(*binding['origin']))
            group.AddRotateZOp().Set(binding['yaw_deg'])
            group.GetPrim().SetCustomDataByKey('catalogKind', binding['kind'])
            if 'model_id' in binding:
                group.GetPrim().SetCustomDataByKey('libraryModelId',binding['model_id'])
                group.GetPrim().SetCustomDataByKey('dimensionsM',Vt.DoubleArray(binding['size']))
                recipe='recipe' in binding['parameters']
                group.GetPrim().SetCustomDataByKey('variant','standard' if recipe else binding['parameters']['variant'])
                group.GetPrim().SetCustomDataByKey('finish','recipe_materials' if recipe else binding['parameters']['finish'])
                if recipe:
                    group.GetPrim().SetCustomDataByKey('recipeSHA256',binding['parameters']['recipe_sha256'])
                    group.GetPrim().SetCustomDataByKey('recipeCompiler',binding['parameters']['interpreter_version'])
            group.GetPrim().SetCustomDataByKey('currentGeometryIds', Vt.StringArray(binding['members']))
            for part in parts:
                mesh = UsdGeom.Mesh.Define(stage, str(group.GetPath())+'/'+part['name'])
                mesh.CreatePointsAttr([Gf.Vec3f(*p) for p in part['points']])
                mesh.CreateFaceVertexCountsAttr([3]*len(part['faces']))
                mesh.CreateFaceVertexIndicesAttr([i for face in part['faces'] for i in face])
                mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
                mesh.CreateDoubleSidedAttr(True)
                mesh.CreateDisplayColorAttr([Gf.Vec3f(*part['color'])])
                key = part['material']
                if key not in materials:
                    material = UsdShade.Material.Define(stage, PATH+'/Materials/'+key)
                    shader = UsdShade.Shader.Define(stage, str(material.GetPath())+'/Surface')
                    shader.CreateIdAttr('UsdPreviewSurface')
                    shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*part['color']))
                    shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(.45 if key=='metal' else .8)
                    shader.CreateInput('metallic', Sdf.ValueTypeNames.Float).Set(.35 if key=='metal' else 0.)
                    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
                    materials[key] = material
                UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(materials[key])
                count += 1
        ids = [identity for binding in bindings for identity in binding['members']]
        overlay.SetCustomDataByKey('proxyIds', Vt.StringArray(ids))
        for identity in ids:
            geometry = stage.GetPrimAtPath('/World/TwinPulse/Environment/'+identity+'/geometry')
            UsdGeom.Imageable(geometry).CreatePurposeAttr().Set(UsdGeom.Tokens.guide)
        if any(p.HasAPI(api) for p in Usd.PrimRange(overlay)
               for api in (UsdPhysics.CollisionAPI, UsdPhysics.RigidBodyAPI, UsdPhysics.ArticulationRootAPI)):
            raise ValueError('ROOM_VISUAL_PHYSICS_SCHEMA_PRESENT')
        if not compiler.matches_site_scene(scene): raise ValueError('ROOM_VISUAL_CHANGED_COLLISION')
        return dict(catalog_version=VISUAL_VERSION, scene_revision=scene.revision,
                    appearance_status='ILLUSTRATIVE_CATALOG_NOT_PHOTO_EXACT',
                    groups=len(bindings), meshes=count, skipped=skipped,
                    collision_changed=False, physical_validation='NOT_RUN')
    except Exception:
        stage.RemovePrim(PATH)
        if had_previous and not Sdf.CopySpec(backup, PATH, layer, PATH):
            raise RuntimeError('ROOM_VISUAL_ROLLBACK_FAILED')
        for identity, (purpose, authored) in old_purposes.items():
            geometry = stage.GetPrimAtPath('/World/TwinPulse/Environment/'+identity+'/geometry')
            if authored:
                UsdGeom.Imageable(geometry).CreatePurposeAttr().Set(purpose)
            else:
                geometry.RemoveProperty('purpose')
        raise
