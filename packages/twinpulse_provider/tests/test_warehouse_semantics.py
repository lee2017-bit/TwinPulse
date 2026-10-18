# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""General warehouse regression through real compiler/core, zero network/device.

Scripted provider replies test host recovery, NOT fresh model performance.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[3]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
import test_budgeted_generation as generation_fixtures
from test_budgeted_generation import (text_request,empty_observation,FixtureTransport,config)
from twinpulse_provider import GenerationService
from twinpulse_provider.semantic_scene import (checked_structure,scene_draft,checked_batch,compile_scene,
    batch_schema,_shape_issues,patch_schema,patch_candidate,PATCH_REVISION,revision,compiler_diagnosis)
from twinpulse_core import SiteToolPlan,canonical_sha256,execute_site_tool_plan
from twinpulse_core.photo_placement import (validate_placement_plan,placement_contract_from_trace,
    relocate_attached_children)
from twinpulse_core.photo_quality import support_geometry, support_surface
from twinpulse_core.room_items import room_inventory
from twinpulse_core.room_visuals import visual_bindings,display_meshes
from twinpulse_core.geometry_diagnostics import GeometryValidationError
from twinpulse_provider.generation_policy import GenerationBudgetError


def parameter(kind,size,region='middle_centre',parent=None,part=None,yaw=0,levels=3):
    result=dict(region=region,yaw_deg=yaw,model_id='warehouse.'+kind if kind in ('rack','pallet','pallet_stack')
        else 'common.'+kind,dimensions_m=list(size),variant='standard',finish='catalog_default',
        placement=dict(relation='surface' if parent else 'floor',parent_id=parent,part=part,
            anchor='centre',elevation_m=None))
    if kind=='rack':result['warehouse_parameters']=dict(bay_count=2,level_count=levels)
    if kind=='pallet_stack':result['warehouse_parameters']=dict(stack_levels=levels)
    return result


def fixture(parent_kind='pallet', child_size=(.5,.5,.3), part=None):
    request=text_request('Create an estimated warehouse with a pallet, rack and a box',identity='warehouse-test')
    observation=empty_observation()
    structure=dict(summary='Synthetic warehouse estimate',room=dict(width_m=8,length_m=8,height_m=3),
        inventory=[dict(id=i,kind=k,evidence_ref='text:0') for i,k in [('support',parent_kind),('cargo','box')]])
    size={'pallet':(1.2,.8,.12),'rack':(2.,1.,2.),'pallet_stack':(1.2,.8,1.)}[parent_kind]
    part=part or {'pallet':'deck','rack':'shelf_1','pallet_stack':'stack_top'}[parent_kind]
    params={'support':parameter(parent_kind,size),'cargo':parameter('box',child_size,parent='support',part=part)}
    draft=checked_batch(params,scene_draft(checked_structure(structure,request,observation,bound=True)),list(params))
    return request,observation,structure,params,draft


class WarehouseSemanticsTests(unittest.TestCase):
    def test_all_factories_compiler_visual_inventory_and_persisted_contract(self):
        for kind in ('pallet','rack','pallet_stack'):
            with self.subTest(kind=kind):
                request,observation,_,_,draft=fixture(kind);before=deepcopy(draft)
                payload,trace=compile_scene(draft,observation,request)
                plan=SiteToolPlan.from_dict(json.loads(json.dumps(payload)))
                scene=execute_site_tool_plan(plan,source='manual',source_ref=canonical_sha256(payload)).scene
                contract=placement_contract_from_trace(trace)
                validate_placement_plan(plan,json.loads(json.dumps(contract)))
                calls={c.arguments['id']:c for c in plan.calls}
                self.assertEqual(support_geometry(calls['cargo'].arguments,calls['support'].arguments,
                    draft['objects']['cargo']['placement']['part'])['status'],'PASS')
                bindings,skipped=visual_bindings(scene,plan)
                self.assertFalse(skipped)
                for binding in bindings:
                    self.assertTrue(display_meshes(binding['kind'],binding['size'],binding.get('parameters')))
                self.assertEqual({r['kind'] for r in room_inventory(plan,scene)['items']},{kind,'box'})
                self.assertTrue(trace['checks_complete']);self.assertFalse(trace['physical_authority'])
                self.assertEqual(draft,before)

    def test_model_grammar_has_matching_parent_parts_and_typed_dimensions(self):
        request,observation,_,_,draft=fixture('rack')
        props=batch_schema(draft['inventory'],['support','cargo'])['properties']
        self.assertEqual(props['support']['properties']['yaw_deg']['enum'],[0])
        branches=props['cargo']['properties']['placement']['anyOf']
        surface=next(b['properties'] for b in branches if b['properties']['relation']['enum']==['surface'])
        self.assertEqual(surface['parent_id']['enum'],['support'])
        self.assertEqual(surface['part']['enum'],['shelf_1','shelf_2','shelf_3','shelf_4','shelf_5'])
        wrong=deepcopy(draft['objects']);wrong['support']['warehouse_parameters']['bay_count']=True
        self.assertTrue(_shape_issues(wrong,batch_schema(draft['inventory'],list(wrong))))

    def test_support_invalid_size_retains_actual_dimensions_and_cannot_auto_drop(self):
        request,observation,_,_,draft=fixture(child_size=(1.4,1.4,.3));before=deepcopy(draft)
        with self.assertRaises(GeometryValidationError) as caught:compile_scene(draft,observation,request)
        issue=caught.exception.contract_report['issues'][0]
        self.assertEqual(issue['target_ids'],['cargo']);self.assertIn('support',issue['related_ids'])
        self.assertEqual(issue['actual']['child']['surface_size_m'],[1.2,.8])
        self.assertEqual(issue['actual']['child']['rotated_footprint_m'],[1.4,1.4])
        self.assertEqual(draft,before)

    def test_selected_level_must_exist_and_bare_pallet_is_distinct_from_loaded(self):
        for kind,part in [('rack','shelf_5'),('pallet_stack','deck'),('pallet','stack_top')]:
            request,observation,_,_,draft=fixture(kind)
            draft['objects']['cargo']['placement']['part']=part
            with self.assertRaises(GeometryValidationError) as caught:compile_scene(draft,observation,request)
            self.assertIn('PHOTO_RELATION_PART_UNSUPPORTED',str(caught.exception))

    def test_other_shelves_and_posts_are_not_ignored(self):
        request,observation,_,_,draft=fixture('rack',child_size=(.5,.5,.8))
        with self.assertRaises(GeometryValidationError):compile_scene(draft,observation,request)
        request,observation,_,_,draft=fixture('rack')
        payload,_=compile_scene(draft,observation,request)
        parent=next(c['arguments'] for c in payload['calls'] if c['tool']=='create_rack_row')
        child=next(c['arguments'] for c in payload['calls'] if c['arguments']['id']=='cargo')
        surface=support_surface(parent,'shelf_1')
        child['position_m']=[parent['center_m'][0],parent['center_m'][1],surface.transform.position_m[2]+.04+.15]
        child['dimensions_m']=[.15,.95,.3]
        result=support_geometry(child,parent,'shelf_1')
        self.assertEqual(result['status'],'FAIL');self.assertTrue(result['parent_collision_ids'])

    def test_nominal_rack_height_cannot_bypass_expanded_ceiling_check(self):
        request,observation,_,_,draft=fixture('rack')
        draft['objects']['support']['dimensions_m'][2]=3
        with self.assertRaises(GeometryValidationError) as caught:compile_scene(draft,observation,request)
        issue=next(i for i in caught.exception.contract_report['issues'] if i['code']=='PHOTO_MODEL_EXCEEDS_ROOM_HEIGHT')
        self.assertAlmostEqual(issue['actual'],3.04)

    def test_parent_rotation_rejected_not_silently_rewritten_but_bare_pallet_rotates(self):
        request,observation,_,_,draft=fixture('rack');draft['objects']['support']['yaw_deg']=90
        with self.assertRaises(GeometryValidationError) as caught:compile_scene(draft,observation,request)
        self.assertIn('PHOTO_WAREHOUSE_ROTATION_UNSUPPORTED',str(caught.exception))
        request,observation,_,_,draft=fixture('pallet');draft['objects']['support']['yaw_deg']=90
        compile_scene(draft,observation,request)

    def test_parent_move_relocates_children_saved_contract_validation_rejects_tampering(self):
        for kind in ('rack','pallet','pallet_stack'):
            request,observation,_,_,draft=fixture(kind)
            payload,trace=compile_scene(draft,observation,request);plan=SiteToolPlan.from_dict(payload)
            contract=placement_contract_from_trace(trace)
            parent=next(c for c in plan.calls if c.arguments['id']=='support')
            args=deepcopy(parent.arguments);key='position_m' if kind=='pallet' else 'center_m'
            args[key][0]+=1.2
            moved=replace(plan,calls=tuple(replace(c,arguments=args) if c==parent else c for c in plan.calls))
            fixed=relocate_attached_children(plan,moved,contract,parent.call_id)
            validate_placement_plan(fixed,contract)
            with self.assertRaises(GeometryValidationError):validate_placement_plan(moved,contract)

    def test_typed_repair_can_add_a_warehouse_parent(self):
        request,observation,_,_,draft=fixture()
        patch=dict(patch_version=PATCH_REVISION,base_revision=revision(draft),operations=[dict(op='add',id='row',
            kind='rack',evidence_ref='hypothesis',
            value=parameter('rack',(2.,.8,2.),region='rear_left'))])
        self.assertFalse(_shape_issues(patch,patch_schema(draft,observation,request=request)))
        changed=patch_candidate(draft,patch,observation,request)
        payload,_=compile_scene(changed,observation,request)
        self.assertIn('create_rack_row',[c['tool'] for c in payload['calls']])

    def test_real_generation_service_recovers_bad_support_without_special_ids(self):
        request,observation,structure,params,draft=fixture(child_size=(1.4,1.4,.3))
        corrected=deepcopy(params['cargo']);corrected['dimensions_m']=[.5,.5,.3]
        patch=dict(patch_version=PATCH_REVISION,base_revision=revision(draft),
            operations=[dict(op='update',id='cargo',value=corrected)])
        transport=FixtureTransport([structure,params,patch])
        provider=generation_fixtures.PipelineTests.provider(self,transport)
        result=asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(result.provider_provenance['budget']['repairs'],1)
        self.assertIn('warehouse.pallet',json.dumps(transport.bodies[0]))
        self.assertTrue(result.plan)

    def test_unchanged_repair_still_stops_and_keeps_the_failed_parent_relation(self):
        request,_,structure,params,draft=fixture(child_size=(1.4,1.4,.3));before=deepcopy(draft)
        patch=dict(patch_version=PATCH_REVISION,base_revision=revision(draft),
            operations=[dict(op='update',id='cargo',value=deepcopy(params['cargo']))])
        transport=FixtureTransport([structure,params,patch,patch])
        provider=generation_fixtures.PipelineTests.provider(self,transport)
        with self.assertRaisesRegex(GenerationBudgetError,'REPAIR_STALLED'):
            asyncio.run(GenerationService(provider,config(timeout_s=300),plan_version='2.2').generate(request))
        self.assertEqual(len(transport.bodies),4)
        self.assertEqual(draft,before)

    def test_generated_contracts_have_no_optional_warehouse_fields_on_home_objects(self):
        from twinpulse_provider.photo_layout import layout_schema,PARAMETRIC_REVISION
        request,observation,_,_,draft=fixture('rack')
        schemas=[batch_schema(draft['inventory'],list(draft['objects'])),
            patch_schema(draft,observation,request=request),
            layout_schema(request.prompt,observation=observation,revision=PARAMETRIC_REVISION)]
        def visit(value):
            if isinstance(value,dict):
                if value.get('type')=='object':
                    self.assertFalse(value['additionalProperties'])
                    self.assertEqual(set(value['required']),set(value['properties']))
                for child in value.values():visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        for schema in schemas:visit(schema)
        branches=schemas[-1]['properties']['objects']['items']['anyOf']
        for branch in branches:
            fields=branch['properties'];kind=fields['kind']['enum'][0]
            self.assertEqual('warehouse_parameters' in fields,kind in ('rack','pallet_stack'))

    def test_compiled_warehouse_targets_use_current_exterior_approach_plan_not_part_ids(self):
        from twinpulse_core.simulation_goal import goal_review
        from twinpulse_core.site_simulation import checked_plan
        from twinpulse_app.simulation_assets import burger_inventory
        for kind in ('rack','pallet','pallet_stack'):
            request,observation,_,_,draft=fixture(kind)
            payload,_=compile_scene(draft,observation,request);plan=SiteToolPlan.from_dict(payload)
            scene=execute_site_tool_plan(plan,source='manual',source_ref=canonical_sha256(payload)).scene
            furniture={i['id']:i['kind'] for i in room_inventory(plan,scene)['items']}
            result=goal_review(scene,'Go to id=support',[0,-2],burger_inventory(),furniture=furniture)
            self.assertEqual(result['target']['id'],'support')
            self.assertEqual(result['plan']['scene_revision'],scene.revision)
            self.assertFalse(result['plan']['physical_authority'])
            checked_plan(scene,result['plan'])

    def test_original_failed_candidate_stays_failed_and_typed_counterfactual_is_separate(self):
        path=ROOT/'outputs/physical-ai-p2-20261011-v420/campaign/cd3af43a5774797737f85e825964e549/run-1/runtime/provider-evidence/validations/c3b135888784462b922dd06edc49f924-semantic_compile.json'
        raw=path.read_bytes();record=json.loads(json.loads(raw)['record_redacted']);original=record['candidate']
        request=text_request(original['inventory'][0]['source']['user_quote'])
        with self.assertRaises(GeometryValidationError) as caught:compile_scene(original,empty_observation(),request)
        problem=caught.exception.contract_report['issues'][0]
        self.assertEqual(problem['actual']['child']['surface_size_m'],[.8,.42])
        self.assertEqual(problem['target_ids'],['box1'])
        # This is an explicit test-only counterfactual, never a product rewrite
        # of a model's rejected kind, source or parent choice.
        candidate=deepcopy(original)
        next(r for r in candidate['inventory'] if r['id']=='pallet1')['kind']='pallet'
        candidate['objects']['pallet1']['model_id']='warehouse.pallet'
        candidate['objects']['box1']['placement'].update(parent_id='pallet1',part='deck')
        payload,_=compile_scene(candidate,empty_observation(),request)
        self.assertEqual(len(payload['calls']),9)
        self.assertEqual(path.read_bytes(),raw);self.assertEqual(original,record['candidate'])

    def test_saved_app_preview_apply_closed_reopen_undo_and_invalid_resize(self):
        from twinpulse_app.application import ApplicationService
        from twinpulse_app.site_draft import SiteDraftRecord
        from twinpulse_app.scene_changes import SceneChangeStore
        for kind in ('rack','pallet','pallet_stack'):
            request,observation,_,_,draft=fixture(kind)
            payload,trace=compile_scene(draft,observation,request)
            prepared=ApplicationService.prepare_input(prompt=request.prompt,images=(),measurement_constraints=(),
                generation_settings={'model_id':'offline-fixture'})
            source=SiteDraftRecord.create(request_id='warehouse',provider_name='offline-fixture',model_id='offline-fixture',
                image_count=0,input_revision=prepared.revision,plan=SiteToolPlan.from_dict(payload),
                placement_contract=placement_contract_from_trace(trace))
            original=deepcopy(source.to_dict())
            with TemporaryDirectory() as folder:
                path=Path(folder)/'changes.json';store=SceneChangeStore(path,project_id='warehouse',source=source)
                history=store.load();parent=next(c for c in source.plan.calls if c.arguments['id']=='support')
                call=deepcopy(parent.to_dict());key='position_m' if kind=='pallet' else 'center_m';call['arguments'][key][0]+=.4
                preview=history.preview(source,operation_id='move',mode='change',target_call_id=parent.call_id,tool_call=call)
                self.assertFalse(path.exists()) # preview/cancel has no persistent write
                history=store.apply(preview['operation'],canonical_sha256(preview['operation']))
                restored=SiteDraftRecord.from_dict(json.loads(json.dumps(source.to_dict())))
                reopened=SceneChangeStore(path,project_id='warehouse',source=restored).load()
                moved,_=reopened.replay(restored);validate_placement_plan(moved,restored.placement_contract)
                original_child=next(c for c in source.plan.calls if c.arguments['id']=='cargo')
                child=next(c for c in moved.calls if c.arguments['id']=='cargo')
                self.assertAlmostEqual(child.arguments['position_m'][0]-original_child.arguments['position_m'][0],.4)
                undo=reopened.preview(restored,operation_id='undo',mode='undo')
                undone=store.apply(undo['operation'],canonical_sha256(undo['operation']))
                self.assertEqual(undone.replay(restored)[0].to_dict(),source.plan.to_dict())
                bad=parent.to_dict()
                if kind=='rack':bad['arguments']['depth_m']=.35
                elif kind=='pallet_stack':bad['arguments']['footprint_m']=[.3,.3]
                else:bad['arguments']['dimensions_m']=[.3,.3,.12]
                persisted=path.read_bytes()
                with self.assertRaises(ValueError):
                    undone.preview(restored,operation_id='bad_resize',mode='change',target_call_id=parent.call_id,tool_call=bad)
                self.assertEqual(path.read_bytes(),persisted);self.assertEqual(source.to_dict(),original)


if __name__=='__main__':unittest.main()
