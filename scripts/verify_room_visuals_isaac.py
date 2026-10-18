# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual current saved-photo Build/display/proxy-contact acceptance, zero model/robot calls."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'extensions/twinpulse.extension'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path,help='Completed real App run, read only')
    parser.add_argument('output',type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    result=dict(status='FAIL',provider_calls=0,robot_connections=0,physical_validation='NOT_RUN',checks=[])
    app=runtime=None
    source=args.source.resolve()/'runtime/active_project.json';original=sha256(source.read_bytes()).hexdigest()
    try:
        from twinpulse_app.project_store import ProjectStore
        draft=ProjectStore(source).load().site_draft
        state=output/'state';store=ProjectStore.for_project(state,'default')
        store.save(ProjectStore(source).load())
        scene=draft.site.scene
        from isaacsim import SimulationApp
        app=SimulationApp({'headless':True,'width':1280,'height':960})
        import omni.usd
        import omni.timeline
        from pxr import Gf,Usd,UsdGeom,UsdPhysics
        from omni.kit.viewport.utility import get_active_viewport,capture_viewport_to_file
        from twinpulse_core import CommandEnvelope
        from twinpulse.extension.runtime import TwinPulseRuntime
        from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
        from twinpulse.extension.room_visuals import compose_room_visuals,clear_room_visuals,PATH
        context=omni.usd.get_context();context.new_stage()
        for _ in range(10):app.update()
        runtime=TwinPulseRuntime();adapter=IsaacSimulationAdapter(runtime,project_state_root=state)
        adapter.update_control_lease('room-display-test',True)
        stage=context.get_stage();UsdGeom.Xform.Define(stage,'/ExternalKeep').GetPrim().SetCustomDataByKey('marker','untouched')
        command=CommandEnvelope(command_id='display-build-1',command_type='build_site_scene',project_id='default',
            engine_session_id=adapter.engine_session_id,stage_epoch=adapter.stage_epoch,control_lease_id='room-display-test',
            expected_applied_revision=scene.revision,payload=dict(artifact_id='saved-real-model-display',
                scene_revision=scene.revision,scene=scene.to_dict()))
        receipt=adapter.execute(command)
        assert receipt.status=='succeeded',(receipt.error_code,receipt.message)
        def collision_snapshot():
            env=stage.GetPrimAtPath('/World/TwinPulse/Environment')
            return {str(p.GetPath()):dict(type=p.GetTypeName(),schemas=list(p.GetAppliedSchemas()),
                attrs={a.GetName():str(a.Get()) for a in p.GetAttributes() if a.GetName()!='purpose'})
                for p in Usd.PrimRange(env)}
        snapshot=collision_snapshot()
        marker=stage.GetPrimAtPath(PATH);assert marker and marker.GetCustomDataByKey('sceneRevision')==scene.revision
        groups=[p for p in marker.GetChildren() if p.GetName().startswith('Item_')]
        assert len(groups)==24
        assert all(not p.HasAPI(api) for p in Usd.PrimRange(marker)
                   for api in (UsdPhysics.CollisionAPI,UsdPhysics.RigidBodyAPI,UsdPhysics.ArticulationRootAPI))
        first=compose_room_visuals(runtime.compiler,scene,draft.plan)
        assert first['groups']==24 and not first['skipped']
        count=len(list(stage.Traverse()));compose_room_visuals(runtime.compiler,scene,draft.plan)
        assert len(list(stage.Traverse()))==count and collision_snapshot()==snapshot
        result.update(composition=first,scene_revision=scene.revision,plan_sha256=draft.plan_sha256)
        result['checks'].append('actual adapter ordinary Build: saved real plan24 display groups, no physics schemas; idempotent and collision attrs unchanged')
        # Fault after stage authoring exercises overlay AND proxy-purpose rollback.
        import twinpulse.extension.room_visuals as visual_module
        original_display=visual_module.display_meshes
        valid=original_display('bed',(1.,1.,1.))
        broken=[{**p,'points':[('bad',0,0)]} if i==0 else p for i,p in enumerate(valid)]
        before=stage.GetRootLayer().ExportToString()
        visual_module.display_meshes=lambda *unused:broken
        try:
            try:compose_room_visuals(runtime.compiler,scene,draft.plan)
            except (TypeError,ValueError):pass
            else:raise AssertionError('Injected display authoring failure accepted')
        finally:visual_module.display_meshes=original_display
        assert stage.GetRootLayer().ExportToString()==before,'Overlay rollback changed stage'
        result['checks'].append('injected post-authoring failure restores previous overlay and all proxy purposes')
        # Product adapter must also restore the previous room after a NEW
        # geometry build succeeds but its display composer subsequently fails.
        wall=next(o for o in scene.objects if o.kind=='wall')
        shifted=replace(wall,transform=replace(wall.transform,
            position_m=(wall.transform.position_m[0]+.02,*wall.transform.position_m[1:])))
        failed_scene=replace(scene,objects=tuple(shifted if o.id==wall.id else o for o in scene.objects),parent_revision=scene.revision)
        original_compose=visual_module.compose_room_visuals
        def stage_graph():
            return {str(p.GetPath()):dict(type=p.GetTypeName(),schemas=sorted(p.GetAppliedSchemas()),
                data=p.GetCustomData(),attrs={a.GetName():str(a.Get()) for a in p.GetAttributes()},
                relations={r.GetName():[str(t) for t in r.GetTargets()] for r in p.GetRelationships()},
                children=sorted(c.GetName() for c in p.GetChildren())) for p in stage.Traverse()}
        graph_before=stage_graph()
        def fail_composition(*unused):raise RuntimeError('Injected post-Build display failure')
        visual_module.compose_room_visuals=fail_composition
        try:
            failed=adapter.execute(replace(command,command_id='display-build-failure',issued_at_unix_s=time.time(),
                expected_applied_revision=failed_scene.revision,payload=dict(artifact_id='failed-display',
                    scene_revision=failed_scene.revision,scene=failed_scene.to_dict())))
        finally:visual_module.compose_room_visuals=original_compose
        assert failed.status=='failed' and runtime.compiler.matches_site_scene(scene)
        # The existing safe compiler preserves the PhysicsScene prim handle;
        # USD sibling serialization order may change, but no graph data may.
        assert stage_graph()==graph_before,'Adapter rollback changed USD graph'
        result['adapter_rollback_serialization_order_changed']=stage.GetRootLayer().ExportToString()!=before
        result['checks'].append('actual adapter failed new geometry/display Build restores entire old owned scene, overlay and receipt')
        # Actual PhysX comparison: guide-purpose collision still supports a ball.
        bed=next(o for o in scene.objects if o.id=='bed_mattress')
        floor_height=bed.transform.position_m[2]+bed.shape.dimensions_m[2]/2
        timeline=omni.timeline.get_timeline_interface()
        contacts=[]
        for display in (False,True):
            clear_room_visuals(stage)
            if display:compose_room_visuals(runtime.compiler,scene,draft.plan)
            probe=UsdGeom.Sphere.Define(stage,'/World/TwinPulse/DisplayContactProbe')
            probe.CreateRadiusAttr(.04)
            probe.AddTranslateOp().Set(Gf.Vec3d(*bed.transform.position_m[:2],floor_height+.30))
            UsdPhysics.CollisionAPI.Apply(probe.GetPrim());UsdPhysics.RigidBodyAPI.Apply(probe.GetPrim())
            UsdPhysics.MassAPI.Apply(probe.GetPrim()).CreateMassAttr(.05)
            timeline.play()
            for _ in range(220):app.update()
            z=UsdGeom.XformCache().GetLocalToWorldTransform(probe.GetPrim()).ExtractTranslation()[2]
            contacts.append(float(z))
            assert floor_height+.025 < z < floor_height+.08,('Proxy no longer collides',display,z)
            timeline.stop()
            for _ in range(8):app.update()
            stage.RemovePrim('/World/TwinPulse/DisplayContactProbe')
        assert abs(contacts[0]-contacts[1])<.002
        assert runtime.compiler.matches_site_scene(scene) and collision_snapshot()==snapshot
        result['contact_z_m']=contacts
        result['checks'].append('actual PhysX ball rests at same mattress height with original and guide-purpose proxy; no real robot')
        viewport=get_active_viewport();camera=UsdGeom.Camera(stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera'))
        viewport.set_active_camera(str(camera.GetPath()));camera.CreateClippingRangeAttr(Gf.Vec2f(.01,100));camera.CreateFocalLengthAttr(30)
        # Overview cutaway changes only this diagnostic display, not scene/plan.
        for obj in scene.objects:
            if obj.kind=='wall':
                UsdGeom.Imageable(stage.GetPrimAtPath('/World/TwinPulse/Environment/'+obj.id)).MakeInvisible()
        for label,eye,target in [('room-overview',(5,-7,6),(0,.1,.65)),
                                 ('furniture-detail',(3.6,-4,3.3),(0,.3,.8)),
                                 ('wardrobe-rack-detail',(2,4.8,3.0),(-.3,1.3,1.0))]:
            camera.ClearXformOpOrder();camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye),Gf.Vec3d(*target),Gf.Vec3d(0,0,1)).GetInverse())
            for _ in range(45):app.update()
            capture_viewport_to_file(viewport,str(output/(label+'.png')))
            for _ in range(45):app.update()
            assert (output/(label+'.png')).is_file()
        assert stage.GetPrimAtPath('/ExternalKeep').GetCustomDataByKey('marker')=='untouched'
        stage.GetRootLayer().Export(str(output/'room-display.usda'))
        saved=Usd.Stage.Open(str(output/'room-display.usda'))
        assert saved.GetPrimAtPath(PATH).GetCustomDataByKey('sceneRevision')==scene.revision
        assert len([p for p in saved.GetPrimAtPath(PATH).GetChildren() if p.GetName().startswith('Item_')])==24
        result['checks'].append('actual Isaac screenshots, owned USD export/reopen, external prim unchanged')
        # A changed individual part must NOT leave a stale detailed bed behind.
        changed=replace(bed,shape=replace(bed.shape,dimensions_m=(bed.shape.dimensions_m[0]*.9,*bed.shape.dimensions_m[1:])))
        derived=replace(scene,objects=tuple(changed if o.id==bed.id else o for o in scene.objects),parent_revision=scene.revision)
        runtime.build_site_scene(derived)
        partial=compose_room_visuals(runtime.compiler,derived,draft.plan)
        assert not stage.GetPrimAtPath(PATH+'/Item_bed')
        assert partial['skipped']==[dict(id='bed',reason='NONUNIFORM_CURRENT_GEOMETRY')]
        assert UsdGeom.Imageable(stage.GetPrimAtPath('/World/TwinPulse/Environment/bed_mattress/geometry')).GetPurposeAttr().Get()=='default'
        result['checks'].append('resized individual part drops stale bed overlay and retains visible current collider fallback')
        # Actual typed Add/Undo through the existing sidecar, not object-ID guesses.
        from twinpulse_app.scene_changes import SceneChangeStore
        changes=SceneChangeStore(store.path.with_suffix('.scene-changes.json'),project_id='default',source=draft,project_store=store)
        addition=dict(call_id='display_added_box',tool='place_room_item',arguments=dict(id='display_added_box',kind='box',
            label='Explicit added box fixture',catalog_version='room-items-1.0',position_m=[0.,0.,.06],
            dimensions_m=[.12,.12,.12],yaw_deg=0.,observation_time_utc=None))
        preview=changes.load().preview(draft,operation_id='display-add',mode='add',tool_call=addition)
        changes.apply(preview['operation'],preview['preview_digest'])
        _,added=changes.load().replay(draft)
        added_receipt=adapter.execute(replace(command,command_id='display-add-build',issued_at_unix_s=time.time(),expected_applied_revision=added.scene.revision,
            payload=dict(artifact_id='added-display',scene_revision=added.scene.revision,scene=added.scene.to_dict())))
        assert added_receipt.status=='succeeded',(added_receipt.error_code,added_receipt.message)
        assert stage.GetPrimAtPath(PATH+'/Item_display_added_box')
        undo=changes.load().preview(draft,operation_id='display-undo',mode='undo')
        changes.apply(undo['operation'],undo['preview_digest']);_,undone=changes.load().replay(draft)
        undo_receipt=adapter.execute(replace(command,command_id='display-undo-build',issued_at_unix_s=time.time(),expected_applied_revision=undone.scene.revision,
            payload=dict(artifact_id='undone-display',scene_revision=undone.scene.revision,scene=undone.scene.to_dict())))
        assert undo_receipt.status=='succeeded' and not stage.GetPrimAtPath(PATH+'/Item_display_added_box')
        assert runtime.compiler.matches_site_scene(undone.scene)
        result['checks'].append('actual adapter uses checked sidecar typed Add then Undo, current revision bound, removed display does not survive')
        result['status']='PASS'
    except Exception as error:
        traceback.print_exc();result.update(error_type=type(error).__name__,error=str(error))
    finally:
        result['original_project_unchanged']=sha256(source.read_bytes()).hexdigest()==original
        if not result['original_project_unchanged']:result['status']='FAIL'
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('ROOM_DISPLAY='+json.dumps(result),flush=True)
        if runtime:runtime.shutdown()
        if app:app.close()
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
