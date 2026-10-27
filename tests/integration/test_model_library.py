# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reusable library → provider schema → scene/edit → current display, no network."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core import execute_site_tool_plan, SiteToolPlan, SceneToolCall, canonical_sha256
from twinpulse_core.furniture import expand_furniture
from twinpulse_core.model_library import (library_models,library_for_request,FURNITURE_MODELS,
    PARAMETRIC_FURNITURE_VERSION, FINISHES)
from twinpulse_core.room_visuals import display_meshes, visual_bindings
from twinpulse_core.scene_tools import SceneToolPlanError
from twinpulse_app.manual_room import manual_room_plan
from twinpulse_app.scene_changes import SceneChange, SceneChangeHistory
from twinpulse_app.scene_edit_proposals import furniture_edit_context, checked_furniture_proposal
from twinpulse_provider import GenerationService, GenerationRequest, ProviderResponse
from twinpulse_provider.scene_edit_provider import scene_edit_generation_request, scene_edit_proposal_json_schema
from twinpulse_provider.schema import site_tool_plan_json_schema
from tests.integration.test_scene_changes import furnished_source
from tests.integration.test_site_furniture_generation import config, observation
from twinpulse_provider import NebiusChatCompletionsPipelineProvider, ObservationArtifact


def arguments(kind='bed',size=(1.6,2.1,1.),variant='standard',finish='natural'):
    return dict(id='model',kind=kind,catalog_version=PARAMETRIC_FURNITURE_VERSION,
                center_m=[0,0],yaw_deg=0,dimensions_m=list(size),variant=variant,finish=finish)


class ModelLibraryTests(unittest.TestCase):
    def test_authenticated_api_lists_library_without_any_engine_or_robot_command(self):
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from twinpulse_app.api import LocalApiServer
        from twinpulse_app.command_broker import CommandBroker
        server=LocalApiServer(CommandBroker(project_id='default'),product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.start()
        try:
            with self.assertRaises(HTTPError):urlopen(server.base_url+'/v1/product/model-library',timeout=3)
            req=Request(server.base_url+'/v1/bootstrap',data=json.dumps(dict(role='product',secret='p'*43)).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=3) as response:cookie=response.headers['Set-Cookie'].split(';')[0]
            with urlopen(Request(server.base_url+'/v1/product/model-library',headers={'Cookie':cookie}),timeout=3) as response:
                result=json.load(response)
            self.assertEqual(len(result['models']),35);self.assertFalse(result['physical_authority'])
            self.assertIn('warehouse.pallet',{m['model_id'] for m in result['models']})
        finally:server.stop()

    def test_shared_family_discovery_has_no_scene_side_effect(self):
        all_models=library_models();home=library_models('home');warehouse=library_models('warehouse')
        self.assertEqual(len(all_models),35)  # 2026-10-27: + home.floor_lamp
        self.assertIn('warehouse.pallet',{m['model_id'] for m in all_models})
        self.assertEqual(len({m['model_id'] for m in all_models}),35)
        lamp=next(m for m in all_models if m['kind']=='floor_lamp')
        self.assertEqual((lamp['model_id'],lamp['tool'],lamp['catalog_version'],lamp['environments']),('home.floor_lamp','place_room_item','room-items-1.3',['home']))
        self.assertIn('home.floor_lamp',{m['model_id'] for m in library_for_request('warehouse with a floor lamp')['models']})
        self.assertIn('common.desk',{m['model_id'] for m in home}&{m['model_id'] for m in warehouse})
        self.assertNotIn('warehouse.rack',{m['model_id'] for m in home})
        self.assertIn('warehouse.rack',{m['model_id'] for m in warehouse})
        all_models[0]['variants'].clear();self.assertTrue(library_models()[0]['variants'])
        self.assertEqual(library_for_request('한국형 아파트 침대')['environment'],'home')
        mixed=library_for_request('warehouse with a bed')
        self.assertIn('home.bed',{m['model_id'] for m in mixed['models']})
        self.assertEqual(library_for_request('space')['environment'],'mixed_or_unspecified')
        with self.assertRaises(ValueError):library_models('untrusted_download')

    def test_every_furniture_size_variant_and_finish_regenerates_bounded_parts(self):
        for kind,(default,lower,upper,variants,_) in FURNITURE_MODELS.items():
            for size in (default,lower,upper,(lower[0],upper[1],lower[2])):
                for variant in variants:
                    for finish in FINISHES:
                        with self.subTest(kind=kind,size=size,variant=variant,finish=finish):
                            args=arguments(kind,size,variant,finish);before=deepcopy(args)
                            objects=expand_furniture(args)
                            self.assertEqual(args,before)
                            for obj in objects:
                                self.assertTrue(all(v>0 for v in obj.shape.dimensions_m))
                                p=obj.transform.position_m;s=obj.shape.dimensions_m
                                self.assertLessEqual(abs(p[0])+s[0]/2,size[0]/2+1e-8)
                                self.assertLessEqual(abs(p[1])+s[1]/2,size[1]/2+1e-8)
                                self.assertGreaterEqual(p[2]-s[2]/2,-1e-8)
                                self.assertLessEqual(p[2]+s[2]/2,size[2]+1e-8)
                            meshes=display_meshes(kind,size,args)
                            self.assertEqual(len({p['name'] for p in meshes}),len(meshes))
                            for part in meshes:
                                self.assertTrue(all(-size[0]/2-1e-6<=p[0]<=size[0]/2+1e-6 and
                                    -size[1]/2-1e-6<=p[1]<=size[1]/2+1e-6 and
                                    -1e-6<=p[2]<=size[2]+1e-6 for p in part['points']),part['name'])

    def test_fixed_thickness_is_not_whole_mesh_scale_and_variants_are_real(self):
        small=expand_furniture(arguments('desk',(.8,.5,.7)))
        large=expand_furniture(arguments('desk',(2.,1.,1.1)))
        self.assertEqual(small[0].shape.dimensions_m[2],large[0].shape.dimensions_m[2])
        self.assertEqual(small[1].shape.dimensions_m[:2],large[1].shape.dimensions_m[:2])
        single=display_meshes('bed',(1.4,2.,.9),arguments('bed',(1.4,2.,.9),'single'))
        double=display_meshes('bed',(1.4,2.,.9),arguments('bed',(1.4,2.,.9),'double'))
        self.assertNotIn('pillow_1',{p['name'] for p in single});self.assertIn('pillow_1',{p['name'] for p in double})
        for variant in ('open','closed'):
            meshes=display_meshes('wardrobe',(1.2,.6,2.),arguments('wardrobe',(1.2,.6,2.),variant))
            self.assertEqual('door_1' in {p['name'] for p in meshes},variant=='closed')
        white=display_meshes('chair',(.5,.5,1.),arguments('chair',(.5,.5,1.),'office','white'))
        dark=display_meshes('chair',(.5,.5,1.),arguments('chair',(.5,.5,1.),'office','dark'))
        self.assertNotEqual(next(p['color'] for p in white if p['name']=='padded_seat'),
                            next(p['color'] for p in dark if p['name']=='padded_seat'))

    def test_invalid_dimensions_options_and_legacy_arguments_fail_not_clamp(self):
        for override in ({'dimensions_m':[.1,2.,1.]},{'dimensions_m':[1.,2.,float('nan')]},
                         {'dimensions_m':[True,2.,1.]},{'variant':'remote-code'},{'finish':'download'},
                         {'unknown_option':1},{'catalog_version':'furniture-blocks-1.0'}):
            with self.assertRaises((SceneToolPlanError,ValueError)):expand_furniture({**arguments(),**override})
        plan=manual_room_plan('library',6,6,2.6,[{k:v for k,v in arguments().items()
            if k in {'kind','center_m','yaw_deg','dimensions_m','variant','finish'}}])
        with self.assertRaises(SceneToolPlanError):execute_site_tool_plan(replace(plan,plan_version='2.1'),source='manual',source_ref='a'*64)

    def test_provider_manifest_and_schema_feed_actual_generation_service(self):
        provider=NebiusChatCompletionsPipelineProvider(None,observer_model_id='observer',planner_model_id='planner',site_plan_version='2.2')
        body=provider.build_planner_body(GenerationRequest(request_id='catalog',prompt='bedroom with bed 1.6 by 2.1m'),ObservationArtifact.from_mapping(observation()))
        manifest=json.loads(body['messages'][1]['content'])['environment_model_library']
        self.assertEqual(manifest['environment'],'home')
        self.assertIn(PARAMETRIC_FURNITURE_VERSION,body['messages'][0]['content'])
        schema=site_tool_plan_json_schema('2.2')
        self.assertIn(PARAMETRIC_FURNITURE_VERSION,json.dumps(schema))
        self.assertNotIn(PARAMETRIC_FURNITURE_VERSION,json.dumps(site_tool_plan_json_schema('2.1')))
        self.assertIn(PARAMETRIC_FURNITURE_VERSION,json.dumps(scene_edit_proposal_json_schema()))
        plan=manual_room_plan('library',6,6,2.6,[{k:v for k,v in arguments().items()
            if k in {'kind','center_m','yaw_deg','dimensions_m','variant','finish'}}])
        class Provider:
            async def generate(self,request,token,config):return ProviderResponse(request.request_id,plan.to_dict(),'explicit library fixture',config.model_id)
        result=asyncio.run(GenerationService(Provider(),config(),plan_version='2.2').generate(GenerationRequest(request_id='library',prompt='A bed')))
        scene=result.site_draft.scene if hasattr(result,'site_draft') else execute_site_tool_plan(result.plan,source='manual',source_ref='a'*64).scene
        bindings,skipped=visual_bindings(scene,result.plan)
        self.assertEqual(skipped,[]);self.assertEqual(bindings[0]['model_id'],'home.bed')
        self.assertEqual(bindings[0]['size'],(1.6,2.1,1.))

    def test_legacy_upgrade_resize_sidecar_roundtrip_undo_preserves_original(self):
        source=furnished_source();original=source.to_dict();history=SceneChangeHistory.empty('test',source)
        old=next(c for c in source.plan.calls if c.tool=='place_furniture' and c.arguments['kind']=='bed')
        args={**arguments(size=(1.5,2.1,1.)), 'id':old.arguments['id'],'center_m':old.arguments['center_m']}
        context=furniture_edit_context('test',source,history,'Resize the selected bed',old.call_id)
        raw=dict(call_id=old.call_id,tool='place_furniture',arguments=args)
        proposal=dict(schema_version='scene-edit-proposal-1.0',context_sha256=context['context_sha256'],
            mode='change_furniture',explanation='Resize this bed only.',target_call_id=old.call_id,tool_call=raw)
        mode,target,call,_=checked_furniture_proposal(context,proposal)
        preview=history.preview(source,operation_id='resize',mode=mode,target_call_id=target,tool_call=call)
        history=history.append(source,SceneChange.from_dict(preview['operation']))
        plan,site=SceneChangeHistory.from_dict(history.to_dict(),source,'test').replay(source)
        self.assertEqual(plan.plan_version,'2.2')
        self.assertEqual(visual_bindings(site.scene,plan)[0][0]['size'],(1.5,2.1,1.))
        context=furniture_edit_context('test',source,history,'Move bed',old.call_id)
        self.assertIn('environment_model_library',json.loads(scene_edit_generation_request(context,'edit').prompt))
        undo=history.preview(source,operation_id='undo',mode='undo')
        undone=history.append(source,SceneChange.from_dict(undo['operation'])).replay(source)
        self.assertEqual(undone[0].to_dict(),source.plan.to_dict());self.assertEqual(source.to_dict(),original)

    def test_rack_and_pallet_are_reused_factories_and_display_bound_to_current_parts(self):
        calls=(SceneToolCall('floor','create_floor',dict(id='floor',center_m=[0,0],size_m=[14,8])),
            SceneToolCall('rack','create_rack_row',dict(id='rack',center_m=[-3,1],length_m=4.,depth_m=.8,height_m=2.2,bay_count=2,level_count=3)),
            SceneToolCall('pallet','place_pallet_stack',dict(id='pallet',center_m=[3,-1],footprint_m=[1.2,.8],stack_height_m=1.,stack_levels=2)))
        plan=SiteToolPlan('warehouse','Warehouse library fixture','Not measured',calls,plan_version='2.2')
        scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene;before=scene.to_dict()
        bindings,skipped=visual_bindings(scene,plan)
        self.assertEqual(skipped,[]);self.assertEqual({b['model_id'] for b in bindings},{'warehouse.rack','warehouse.pallet_stack'})
        for b in bindings:self.assertTrue(display_meshes(b['kind'],b['size'],b['parameters']))
        self.assertEqual(scene.to_dict(),before)

if __name__=='__main__':unittest.main()
