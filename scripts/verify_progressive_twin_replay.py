# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable failed candidate -> new partial draft, optionally actual static Isaac.

Zero external requests, credentials, robot access, or Run. Does not reclassify
the original failure or claim a new model/quality/task result.
"""
import argparse
from copy import deepcopy
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
    parser.add_argument('runtime',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--isaac',action='store_true')
    args=parser.parse_args()
    source=args.runtime.resolve();output=args.output.resolve()
    if not source.is_relative_to(ROOT/'outputs') or not output.is_relative_to(ROOT/'outputs') or output.exists():
        raise ValueError('Read-only source and fresh output must be under repository outputs')
    from twinpulse_core import InputArtifactStore,SiteToolPlan,canonical_sha256,CommandEnvelope
    from twinpulse_core.geometry_diagnostics import GeometryValidationError
    from twinpulse_core.photo_placement import placement_contract_from_trace
    from twinpulse_provider import GenerationRequest,ImageInput
    from twinpulse_provider.nebius_pipeline import ObservationArtifact
    from twinpulse_provider.semantic_scene import compile_scene,revision
    from twinpulse_provider.generation_store import LIMIT
    from twinpulse_app.project_store import ProjectStore,ProjectRecord
    from twinpulse_app.site_draft import SiteDraftRecord
    candidates=[]
    originals={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
        for p in sorted(source.rglob('*')) if p.is_file()}
    source_files={str(Path(__file__).relative_to(ROOT))}
    for folder,suffix in [(ROOT/'packages'/name/'src','.py') for name in
            ('twinpulse_core','twinpulse_app','twinpulse_provider')]+[
            (ROOT/'extensions/twinpulse.extension','.py'),(ROOT/'apps/twinpulse-web/src','.tsx'),
            (ROOT/'apps/twinpulse-web/src','.ts'),(ROOT/'apps/twinpulse-web/src','.css')]:
        source_files.update(str(p.relative_to(ROOT)) for p in folder.rglob('*'+suffix) if p.is_file())
    source_hashes={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(source_files)}
    for path in sorted((source/'provider-evidence/generation-store/checkpoint-history').rglob('*.json')):
        raw=path.read_bytes()
        if len(raw)>LIMIT:raise ValueError('Oversized checkpoint')
        stored=json.loads(raw)
        if stored['schema_version']!='generation-store-1.0' or canonical_sha256(stored['payload'])!=stored['payload_sha256']:
            raise ValueError('Corrupt original checkpoint')
        data=stored['payload'];draft=data.get('draft') or {}
        if draft.get('inventory') and len(draft.get('objects',{}))==len(draft['inventory']) and data['budget']['repairs']==0:
            candidates.append((path,data))
    if not candidates:raise ValueError('No complete pre-repair candidate')
    path,checkpoint=candidates[0]
    draft=deepcopy(checkpoint['draft']);candidate=revision(draft)
    project=ProjectStore(source/'active_project.json').load()
    input_revision,images=InputArtifactStore(source/'inputs').load(project.latest_input)
    request=GenerationRequest('progressive-immutable-replay',input_revision.prompt,
        tuple(ImageInput(*image) for image in images))
    observation=ObservationArtifact.from_mapping(checkpoint['observation'],allow_derived=True)
    output.mkdir(parents=True)
    result=dict(status='FAIL',provider_calls=0,robot_connections=0,Run='NOT_RUN',
        quality='NOT_VERIFIED',original_live_status='FAIL',originals=originals,
        source_sha256=source_hashes,source_manifest_sha256=canonical_sha256(source_hashes),
        candidate_revision=candidate,input_digest=input_revision.digest,checkpoint=str(path.relative_to(ROOT)))
    app=None
    try:
        try:compile_scene(draft,observation,request)
        except GeometryValidationError as error:
            result['strict_reproduction']=deepcopy(error.contract_report)
        else:raise AssertionError('Original support failure did not reproduce')
        payload,trace=compile_scene(draft,observation,request,progressive=True)
        saved=SiteDraftRecord.create(request_id=request.request_id,provider_name='immutable-offline-replay',
            model_id='no-new-model-call',image_count=len(images),input_revision=input_revision,
            plan=SiteToolPlan.from_dict(payload),placement_contract=placement_contract_from_trace(trace),
            progressive_twin=trace['progressive_twin'])
        state=output/'state';store=ProjectStore.for_project(state,'default')
        InputArtifactStore(state/'inputs').save(input_revision,tuple((name,content) for name,mime,content in images))
        store.save(ProjectRecord('default',input_revision,site_draft=saved))
        reopened=ProjectStore.for_project(state,'default').load().site_draft
        assert reopened.to_dict()==saved.to_dict() and revision(draft)==candidate
        result.update(status='PASS_OFFLINE_PARTIAL_DRAFT',progressive_twin=saved.progressive_twin,
            scene_revision=saved.site.scene.revision,plan_sha256=saved.plan_sha256,checks=trace['checks'])
        if args.isaac:
            from isaacsim import SimulationApp
            app=SimulationApp({'headless':True,'width':1280,'height':960})
            import omni.usd
            import omni.timeline
            from pxr import Usd,UsdGeom,Gf
            from omni.kit.viewport.utility import get_active_viewport,capture_viewport_to_file
            from twinpulse.extension.runtime import TwinPulseRuntime
            from twinpulse.extension.isaac_adapter import IsaacSimulationAdapter
            from twinpulse.extension.room_visuals import PATH
            context=omni.usd.get_context();context.new_stage()
            for _ in range(10):app.update()
            runtime=TwinPulseRuntime();adapter=IsaacSimulationAdapter(runtime,project_state_root=state)
            adapter.update_control_lease('progressive-static',True)
            scene=saved.site.scene
            command=CommandEnvelope(command_id='partial-static-build',command_type='build_site_scene',project_id='default',
                engine_session_id=adapter.engine_session_id,stage_epoch=adapter.stage_epoch,control_lease_id='progressive-static',
                expected_applied_revision=scene.revision,payload=dict(artifact_id='partial-draft',scene_revision=scene.revision,scene=scene.to_dict()))
            receipt=adapter.execute(command)
            assert receipt.status=='succeeded',(receipt.error_code,receipt.message)
            assert runtime.compiler.matches_site_scene(scene)
            stage=context.get_stage();overlay=stage.GetPrimAtPath(PATH)
            groups=[p for p in overlay.GetChildren() if p.GetName().startswith('Item_')]
            assert len(groups)==sum(row['status']=='render_pending' for row in saved.progressive_twin['inventory'])
            assert all(not stage.GetPrimAtPath(PATH+'/Item_'+row['id']) for row in saved.progressive_twin['unresolved'])
            viewport=get_active_viewport();camera=UsdGeom.Camera(stage.GetPrimAtPath('/World/TwinPulse/Presentation/Camera'))
            camera.ClearXformOpOrder();camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(
                Gf.Vec3d(6,-8,7),Gf.Vec3d(0,.5,.9),Gf.Vec3d(0,0,1)).GetInverse())
            camera.CreateFocalLengthAttr(30);viewport.set_active_camera(str(camera.GetPath()))
            for _ in range(120):app.update();time.sleep(.01)
            capture_viewport_to_file(viewport,str(output/'current-partial.png'))
            for _ in range(60):app.update();time.sleep(.01)
            assert (output/'current-partial.png').stat().st_size>1000
            from PIL import Image
            with Image.open(output/'current-partial.png') as image:image.verify()
            stage.GetRootLayer().Export(str(output/'partial.usda'))
            # Hold the stage for the lifetime of its prim handles (USD weak refs).
            reopened_stage=Usd.Stage.Open(str(output/'partial.usda'))
            assert reopened_stage.GetPrimAtPath(PATH).GetCustomDataByKey('sceneRevision')==scene.revision
            assert not omni.timeline.get_timeline_interface().is_playing()
            assert ProjectStore.for_project(state,'default').load().site_draft.to_dict()==saved.to_dict()
            result.update(status='DRAFT_RUNTIME_ACCEPTED_STATIC_ONLY',receipt=receipt.to_dict(),display_groups=len(groups),
                engine_session_id=adapter.engine_session_id,stage_epoch=adapter.stage_epoch,
                capture=dict(path=str((output/'current-partial.png').relative_to(ROOT)),
                    sha256=sha256((output/'current-partial.png').read_bytes()).hexdigest(),
                    scene_revision=scene.revision,engine_session_id=adapter.engine_session_id,
                    stage_epoch=adapter.stage_epoch,command_id=command.command_id,
                    camera_path=str(camera.GetPath()),camera_transform=[list(row) for row in camera.GetLocalTransformation()]))
    except Exception as error:
        result.update(status='FAIL',error=str(error),traceback=traceback.format_exc())
    finally:
        result['originals_unchanged']=all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in originals.items())
        result['source_unchanged']=all(sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in source_hashes.items())
        if not result['originals_unchanged'] or not result['source_unchanged']:result['status']='FAIL'
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PROGRESSIVE_REPLAY='+result['status'],flush=True)
        if app:app.close()
    return 1 if result['status']=='FAIL' else 0


if __name__=='__main__':raise SystemExit(main())
