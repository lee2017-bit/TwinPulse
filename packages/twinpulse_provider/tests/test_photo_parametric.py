# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Additive photo contract tests, not model quality or physical evidence."""
import asyncio
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

PACKAGES=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(PACKAGES/package/'src'))
from twinpulse_core import SiteToolPlan, execute_site_tool_plan, canonical_sha256
from twinpulse_core.model_library import library_models, FURNITURE_MODELS
from twinpulse_core.photo_quality import support_geometry
from twinpulse_core.room_visuals import visual_bindings
from twinpulse_provider import GenerationService
from twinpulse_provider.photo_layout import (compile_layout, layout_schema, build_layout_body,
    PARAMETRIC_REVISION, PARAMETRIC_COMPILER_REVISION)
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
from test_photo_layout import observation, request, layout
from test_nebius_pipeline import ScriptedTransport, completion, config, OBSERVER_MODEL, PLANNER_MODEL


def object_intent(identity,kind,region='middle_centre',*,parent=None,part=None,relation='floor',anchor='centre',elevation=None,size=None):
    model=next(m for m in library_models() if m['kind']==kind)
    from twinpulse_provider.photo_layout import SIZES
    size=list(size or (FURNITURE_MODELS[kind][0] if kind in FURNITURE_MODELS else SIZES[kind]))
    return dict(id=identity,kind=kind,region=region,yaw_deg=0,observation_ids=['bed_visual'],
        model_id=model['model_id'],dimensions_m=size,variant=model['variants'][0],finish=model['finishes'][0],
        placement=dict(relation=relation,parent_id=parent,part=part,anchor=anchor,elevation_m=elevation))


def intent(*objects,width=6,length=6):
    return dict(layout_version=PARAMETRIC_REVISION,summary='Estimated library relationships, not measured.',
        room=dict(width_m=width,length_m=length,height_m=2.6),objects=list(objects))


def compile(value):
    return compile_layout(value,observation(),request('An estimated bedroom'),None)


class PhotoParametricTests(unittest.TestCase):
    def test_reviewed_schema_prevents_furniture_surface_and_pins_reviewed_supports(self):
        from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
        from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
        reference=photo_reference(PHOTO_SHA256);before=deepcopy(reference)
        constraints=reviewed_photo_constraints(PHOTO_SHA256)
        schema=layout_schema('Bedroom',reference,observation(),
            quality_constraints=constraints,revision=PARAMETRIC_REVISION)
        slots=schema['properties']['objects']['properties']
        for item in reference['items']:
            if item['kind'] in (*FURNITURE_MODELS,'office_chair','floor_fan','clothes_rack','door_leaf'):
                placement=slots[item['id']]['properties']['placement']['properties']
                self.assertEqual(placement,dict(relation={'enum':['floor']},
                    parent_id={'type':'null'},part={'type':'null'},
                    anchor={'enum':['centre']},elevation_m={'type':'null'}))
        for identity,parent,part in constraints.supports:
            placement=slots[identity]['properties']['placement']['properties']
            self.assertEqual(placement,dict(relation={'enum':['surface']},
                parent_id={'enum':[parent]},part={'enum':[part]},
                anchor={'enum':['centre']},elevation_m={'type':'null'}))
        self.assertEqual(reference,before)
        # Raw output is still rejected, including exact bad desk->wardrobe
        # relation from the real failed trial; no post-hoc candidate repair.
        desk=object_intent('desk','desk',parent='wardrobe',part='body',relation='surface')
        bad=intent(desk,object_intent('wardrobe','wardrobe'));original=deepcopy(bad)
        with self.assertRaisesRegex(ValueError,'furniture must be floor-standing: desk'):
            compile(bad)
        self.assertEqual(bad,original)

    def test_unreviewed_and_legacy_schema_are_not_given_reviewed_parent_authority(self):
        from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
        from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
        generic=layout_schema('Bedroom',None,observation(),revision=PARAMETRIC_REVISION)
        options=generic['properties']['objects']['items']['anyOf']
        bed=next(b['properties'] for b in options if b['properties']['kind']['enum']==['bed'])
        box=next(b['properties'] for b in options if b['properties']['kind']['enum']==['box'])
        self.assertEqual(bed['placement']['properties']['relation']['enum'],['floor'])
        self.assertEqual(box['placement']['properties']['relation']['enum'],['floor','surface','drape','wall','ceiling'])
        legacy=layout_schema('Bedroom',photo_reference(PHOTO_SHA256),observation(),
            quality_constraints=reviewed_photo_constraints(PHOTO_SHA256))
        self.assertNotIn('placement',legacy['properties']['objects']['properties']['desk']['properties'])
        body=build_layout_body(request(),observation(),PLANNER_MODEL,None)
        self.assertIn('MUST be floor-standing',body['messages'][0]['content'])

    def test_wire_positive_dimensions_and_estimated_prop_options_are_not_measurements(self):
        from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
        from twinpulse_provider.photo_layout import SIZES
        reference=photo_reference(PHOTO_SHA256)
        body=build_layout_body(request(),observation(),PLANNER_MODEL,reference)
        payload=json.loads(body['messages'][1]['content'])
        defaults=payload['estimated_prop_dimensions_m']
        self.assertEqual(set(defaults),{i['kind'] for i in reference['items']} & set(SIZES))
        self.assertEqual(defaults['floor_fan'],[.4,.4,1.1])
        self.assertTrue(all(min(size)>0 for size in defaults.values()))
        fields=body['response_format']['json_schema']['schema']['properties']['objects']['properties']
        self.assertEqual(fields['floor_fan']['properties']['dimensions_m']['items'],
            {'type':'number','minimum':.001,'maximum':10})
        self.assertIn('unmeasured',body['messages'][0]['content'])
        zero=intent(object_intent('fan','floor_fan',size=[0,0,0]));before=deepcopy(zero)
        with self.assertRaisesRegex(ValueError,'PHOTO_MODEL_PARAMETERS_INVALID'):compile(zero)
        self.assertEqual(zero,before)

    def test_reviewed_attachment_schema_pairs_parent_parts_and_explicit_planes(self):
        from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
        slots=layout_schema('Bedroom',photo_reference(PHOTO_SHA256),observation(),
            revision=PARAMETRIC_REVISION)['properties']['objects']['properties']
        for identity in ('hanging_clothes','bedding_overhang','clothing_pile'):
            branches=slots[identity]['properties']['placement']['anyOf']
            self.assertEqual(branches[0]['properties']['relation']['enum'],['floor'])
            for branch in branches[1:]:
                fields=branch['properties']
                self.assertNotIn(identity,fields['parent_id']['enum'])
                if fields['parent_id']['enum']==['bed']:
                    self.assertEqual(fields['part']['enum'],['base','mattress','headboard'])
                if fields['parent_id']['enum']==['desk']:
                    self.assertEqual(fields['part']['enum'],['top'])
        blind=slots['window_blind']['properties']['placement']['properties']
        light=slots['ceiling_light']['properties']['placement']['properties']
        self.assertEqual(blind['parent_id']['enum'],['left_wall','right_wall','rear_wall'])
        self.assertEqual(blind['elevation_m']['type'],'number')
        self.assertEqual(light['parent_id']['enum'],['ceiling'])
        # The actual primary response used floor + parent desk on a bag. Bind
        # the null floor parent in every prop's branch, not only fabrics.
        bags=slots['underdesk_bag']['properties']['placement']['anyOf']
        self.assertEqual(bags[0]['properties']['parent_id'],{'type':'null'})
        self.assertEqual(bags[0]['properties']['part'],{'type':'null'})
        self.assertTrue(all(b['properties']['relation']['enum']==['surface'] for b in bags[1:]))
        for child in (object_intent('bedding','bedding_overhang',parent='bed',part='body',relation='drape',anchor='front'),
                      object_intent('blind','window_blind',relation='wall')):
            with self.assertRaises(ValueError):compile(intent(object_intent('bed','bed'),child))

    def test_new_request_schema_and_prompt_expose_library_legacy_helper_unchanged(self):
        body=build_layout_body(request(),observation(),PLANNER_MODEL,None)
        schema=body['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['layout_version']['const'],'photo-layout-1.3')
        for branch in schema['properties']['objects']['items']['anyOf']:
            self.assertIn('source',branch['required'])
            self.assertIn('model_id',branch['required'])
            self.assertIn('placement',branch['required'])
        self.assertIn('model_library',json.loads(body['messages'][1]['content']))
        self.assertIn('dimensions_m',body['messages'][0]['content'])
        self.assertEqual(layout_schema('Bedroom')['properties']['layout_version']['const'],'photo-layout-1.1')

    def test_dimensions_variant_finish_reach_typed_plan_and_current_display(self):
        bed=object_intent('bed','bed',size=[.9,1.9,.75]);bed.update(variant='single',finish='white')
        value=intent(bed);before=deepcopy(value)
        payload,trace=compile(value);plan=SiteToolPlan.from_dict(payload)
        args=next(c.arguments for c in plan.calls if c.tool=='place_furniture')
        self.assertEqual(args['catalog_version'],'furniture-parametric-1.0')
        self.assertEqual(args['dimensions_m'],[.9,1.9,.75]);self.assertEqual(args['variant'],'single')
        site=execute_site_tool_plan(plan,source='photo',source_ref='a'*64)
        bindings,skipped=visual_bindings(site.scene,plan)
        self.assertEqual(skipped,[]);self.assertEqual(bindings[0]['size'],(.9,1.9,.75))
        from twinpulse_provider.photo_layout import BOUNDARY_PACKING_COMPILER_REVISION
        self.assertEqual(trace['compiler_revision'],BOUNDARY_PACKING_COMPILER_REVISION)
        self.assertEqual(trace['model_parameters'][0]['model_id'],'home.bed')
        self.assertFalse(trace['physical_authority']);self.assertEqual(value,before)

    def test_every_furniture_kind_with_nondefault_size_uses_existing_library(self):
        for kind,(default,lower,upper,variants,_) in FURNITURE_MODELS.items():
            with self.subTest(kind=kind):
                size=[(lower[i]+default[i])/2 for i in range(3)]
                item=object_intent('item',kind,size=size);item.update(variant=variants[-1],finish='dark')
                payload,_=compile(intent(item));args=payload['calls'][4]['arguments']
                self.assertEqual(args['dimensions_m'],size);self.assertEqual(args['variant'],variants[-1])

    def test_surface_respects_resized_rotated_parent_and_no_separate_floor_packing(self):
        desk=object_intent('desk','desk','rear_left',size=[.8,.5,.8]);desk['yaw_deg']=90
        monitor=object_intent('monitor','monitor','front_right',parent='desk',part='top',relation='surface',size=[.3,.1,.25])
        payload,trace=compile(intent(desk,monitor));by_id={c['arguments']['id']:c['arguments'] for c in payload['calls']}
        self.assertEqual(support_geometry(by_id['monitor'],by_id['desk'],'top')['status'],'PASS')
        self.assertGreater(by_id['monitor']['position_m'][2],.8)
        self.assertEqual(len([p for p in trace['placements'] if p['id']=='monitor']),1)
        self.assertEqual(next(p for p in trace['placements'] if p['id']=='monitor')['parent'],'desk')

    def test_surface_siblings_do_not_overlap_and_too_large_child_is_rejected(self):
        desk=object_intent('desk','desk',size=[.8,.5,.74])
        children=[object_intent(i,'tabletop_item',parent='desk',part='top',relation='surface',size=[.2,.2,.2]) for i in ('a','b')]
        payload,_=compile(intent(desk,*children));by_id={c['arguments']['id']:c['arguments'] for c in payload['calls']}
        a,b=(by_id[i]['position_m'] for i in ('a','b'))
        self.assertTrue(abs(a[0]-b[0])>=.225-1e-8 or abs(a[1]-b[1])>=.225-1e-8)
        children[0]['dimensions_m']=[2,2,.2]
        with self.assertRaisesRegex(ValueError,'SUPPORT_PLACEMENT_UNAVAILABLE'):compile(intent(desk,children[0]))

    def test_drape_attaches_to_bed_and_rack_preserving_floor_keepout(self):
        bed=object_intent('bed','bed','middle_right');rack=object_intent('rack','clothes_rack','rear_left')
        blanket=object_intent('blanket','bedding_overhang',parent='bed',part='mattress',relation='drape',anchor='left')
        clothes=object_intent('clothes','hanging_clothes',parent='rack',part='body',relation='drape',anchor='front')
        payload,trace=compile(intent(bed,rack,blanket,clothes));plan=SiteToolPlan.from_dict(payload)
        scene=execute_site_tool_plan(plan,source='photo',source_ref='a'*64).scene
        keeps=[o for o in scene.objects if o.id in {'blanket_keepout','clothes_keepout'}]
        self.assertEqual(len(keeps),2);self.assertTrue(all(o.collision for o in keeps))
        by_id={c.arguments['id']:c.arguments for c in plan.calls}
        self.assertAlmostEqual(by_id['blanket']['position_m'][0],by_id['bed']['center_m'][0]-.68)
        self.assertAlmostEqual(by_id['clothes']['position_m'][1],by_id['rack']['position_m'][1]-.225)

    def test_wall_and_ceiling_are_not_floor_slots_and_use_explicit_planes(self):
        blind=object_intent('blind','window_blind',parent='left_wall',relation='wall',elevation=1.5)
        light=object_intent('light','ceiling_light',parent='ceiling',relation='ceiling')
        payload,trace=compile(intent(blind,light));by_id={c['arguments']['id']:c['arguments'] for c in payload['calls']}
        self.assertEqual(by_id['blind']['yaw_deg'],90);self.assertEqual(by_id['blind']['position_m'][2],1.5)
        self.assertAlmostEqual(by_id['light']['position_m'][2]+.06,2.598)
        scene=execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='photo',source_ref='a'*64).scene
        self.assertFalse(next(o for o in scene.objects if o.id=='blind_visual_0').collision)
        self.assertEqual(len(trace['placements']),2)

    def test_invalid_dimensions_model_and_style_are_not_clamped(self):
        for field,bad in [('model_id','warehouse.rack'),('variant','open'),('finish','chrome'),
                          ('dimensions_m',[3,2,.9]),('dimensions_m',[True,2,.9]),
                          ('dimensions_m',[1,2,math.nan]),('dimensions_m',[0,2,.9])]:
            value=intent(object_intent('bed','bed'));value['objects'][0][field]=bad
            with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):compile(value)

    def test_missing_self_cyclic_and_nested_parents_are_rejected(self):
        child=object_intent('child','hanging_clothes',parent='missing',part='body',relation='drape',anchor='front')
        with self.assertRaisesRegex(ValueError,'PARENT_MISSING'):compile(intent(child))
        child['placement']['parent_id']='child'
        with self.assertRaisesRegex(ValueError,'SELF'):compile(intent(child))
        # Legal parent kinds still require an acyclic, supported one-level graph.
        bed=object_intent('bed','bed');bed['placement'].update(relation='surface',parent_id='child',part='body')
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED'):compile(intent(bed,child))

    def test_unsupported_attachment_and_overheight_are_explicit_failures(self):
        cases=[object_intent('bag','bag',parent='bed',part='mattress',relation='drape',anchor='front'),
               object_intent('blind','window_blind',parent='rear_wall',relation='wall',elevation=.1),
               object_intent('bed2','bed',size=[1,2,3])]
        for child in cases:
            with self.subTest(kind=child['kind']),self.assertRaises(ValueError):compile(intent(object_intent('bed','bed'),child))

    def test_floor_monitor_does_not_become_nonblocking_decoration(self):
        payload,_=compile(intent(object_intent('monitor','monitor')))
        scene=execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='photo',source_ref='a'*64).scene
        self.assertTrue(next(o for o in scene.objects if o.id=='monitor_visual_0').collision)

    def test_single_model_parameter_repair_has_same_new_schema(self):
        good=intent(object_intent('bed','bed'));bad=deepcopy(good);bad['objects'][0]['dimensions_m']=[9,2,.9]
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,bad),completion('fixed',PLANNER_MODEL,good))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        result=asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(request('Bedroom')))
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1)
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        self.assertEqual(result.provider_provenance['photo_layout_compiler']['contract'],PARAMETRIC_REVISION)

    def test_old_layout_hash_and_fixed_dimensions_are_not_upgraded(self):
        value=layout();before=canonical_sha256(value);payload,trace=compile_layout(value,observation(),request(),None)
        self.assertEqual(canonical_sha256(value),before)
        self.assertEqual(payload['calls'][4]['arguments']['catalog_version'],'furniture-blocks-1.0')
        self.assertNotIn('model_parameters',trace)

if __name__=='__main__':unittest.main()
