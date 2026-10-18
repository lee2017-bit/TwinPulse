# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Pure compiler regressions; synthetic inputs are not Isaac/model acceptance."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

PACKAGES=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(PACKAGES/package/'src'))

from twinpulse_core import SiteToolPlan
from twinpulse_core.geometry_diagnostics import GeometryValidationError
from twinpulse_core.model_library import library_models
from twinpulse_core.photo_placement import placement_contract_from_trace, validate_placement_plan
from twinpulse_core.photo_quality import support_geometry
from twinpulse_provider import GenerationRequest
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.photo_layout import compile_layout, layout_schema, PARAMETRIC_REVISION, SIZES


def item(identity,kind,size,*,parent=None,part=None):
    model=next(model for model in library_models() if model['kind']==kind)
    value=dict(id=identity,kind=kind,region='middle_centre',yaw_deg=0,observation_ids=['visible'],
        model_id=model['model_id'],dimensions_m=list(size),variant=model['variants'][0],finish=model['finishes'][0],
        placement=dict(relation='surface' if parent else 'floor',parent_id=parent,part=part,
            anchor='centre',elevation_m=None))
    if kind=='rack':value['warehouse_parameters']=dict(bay_count=1,level_count=3)
    return value


def layout(*items):
    return dict(layout_version=PARAMETRIC_REVISION,summary='Synthetic estimated support chain.',
        room=dict(width_m=8,length_m=8,height_m=3),objects=list(items))


def compile(value,**options):
    observation=ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Synthetic objects.',
        entities=[dict(id='visible',kind='static_obstacle',description='Synthetic objects',confidence=.8)],
        relations=[],dimensions=[],ambiguities=['Unmeasured']))
    return compile_layout(value,observation,GenerationRequest('nested-synthetic','Create an estimated room'),None,**options)


def checked(payload,trace):
    plan=SiteToolPlan.from_dict(payload)
    validate_placement_plan(plan,placement_contract_from_trace(trace))
    return {call.arguments['id']:call.arguments for call in plan.calls}


class NestedSurfaceLayoutTests(unittest.TestCase):
    def test_new_recursive_move_and_legacy_contact_tolerance_are_versioned(self):
        from twinpulse_core.photo_placement import relocate_attached_children
        value=layout(item('a_prop','tabletop_item',(.15,.15,.1),parent='b_box',part='top'),
            item('b_box','box',(.4,.4,.2),parent='z_table',part='top'),
            item('z_table','dining_table',(1.8,1.,.75)))
        payload,trace=compile(value);old=SiteToolPlan.from_dict(payload);contract=placement_contract_from_trace(trace)
        changed=deepcopy(payload)
        next(c['arguments'] for c in changed['calls'] if c['arguments']['id']=='z_table')['center_m'][0]+=.3
        moved=relocate_attached_children(old,SiteToolPlan.from_dict(changed),contract,'obj_z_table')
        before={c.arguments['id']:c.arguments for c in old.calls}
        after={c.arguments['id']:c.arguments for c in moved.calls}
        for identity in ('a_prop','b_box'):
            self.assertAlmostEqual(after[identity]['position_m'][0]-before[identity]['position_m'][0],.3)
        validate_placement_plan(moved,contract)
        legacy={**contract,'schema_version':'photo-placement-contract-1.1'}
        historical=deepcopy(payload)
        next(c['arguments'] for c in historical['calls'] if c['arguments']['id']=='a_prop')['position_m'][2]-=.005
        plan=SiteToolPlan.from_dict(historical)
        validate_placement_plan(plan,legacy) # original 1.1 ±2cm support contract, not rewritten
        with self.assertRaises(GeometryValidationError):validate_placement_plan(plan,contract)

    def test_real_recipe_part_named_keepout_is_not_mistaken_for_synthetic_hazard(self):
        from test_model_recipe_planning import plinth_recipe
        from twinpulse_core.model_recipe import recipe_model_id,recipe_digest
        from twinpulse_core.photo_placement import ancestor_support_collisions
        recipe=plinth_recipe()
        recipe['parameters'][2].update(minimum=2.,maximum=3.,default=2.)
        for name in ('upper_keepout','keepout'):
            recipe['parts']=[dict(id='base',center=[0,0,.02],size=['width','depth',.04],
                material='wood',support_top=True,repeat=None),
                dict(id='post',center=[dict(op='sub',args=[dict(op='mul',args=['width',.5]),.02]),0,
                    dict(op='mul',args=['height',.5])],size=[.04,.04,'height'],material='wood',support_top=False,repeat=None),
                dict(id=name,center=[0,0,dict(op='mul',args=['height',.75])],size=['width','depth',.04],
                    material='wood',support_top=True,repeat=None)]
            parent=dict(id='assembly',kind='storage',model_id=recipe_model_id(recipe),recipe_sha256=recipe_digest(recipe),
                interpreter_version=recipe['interpreter_version'],recipe=deepcopy(recipe),
                parameters={p['name']:p['default'] for p in recipe['parameters']},center_m=[0,0],yaw_deg=0)
            box=dict(id='box',kind='box',label='box',catalog_version='room-items-1.0',position_m=[0,0,.09],
                dimensions_m=[.2,.2,.1],yaw_deg=0,observation_time_utc=None)
            prop={**box,'id':'prop','position_m':[0,0,.89],'dimensions_m':[.1,.1,1.5]}
            relations=dict(box=dict(parent_id='assembly'),assembly=dict(parent_id=None))
            hits=ancestor_support_collisions(prop,'box',dict(box=box,assembly=parent),relations)
            self.assertIn('assembly_'+name,hits)

    def test_final_validator_rejects_tampered_grandchild_without_relaxing_contact_or_yaw(self):
        value=layout(item('a_prop','tabletop_item',(.2,.2,.1),parent='b_box',part='top'),
            item('b_box','box',(.4,.4,.1),parent='z_rack',part='shelf_1'),
            item('z_rack','rack',(1.6,1.,1.8)))
        payload,trace=compile(value);contract=placement_contract_from_trace(trace)
        changed=deepcopy(payload)
        child=next(c['arguments'] for c in changed['calls'] if c['arguments']['id']=='a_prop')
        bottom=child['position_m'][2]-child['dimensions_m'][2]/2
        child['dimensions_m'][2]=1.;child['position_m'][2]=bottom+.5
        plan=SiteToolPlan.from_dict(changed)
        calls={c.arguments['id']:c.arguments for c in plan.calls}
        self.assertEqual(support_geometry(child,calls['b_box'],'top')['status'],'PASS')
        with self.assertRaises(GeometryValidationError) as caught:validate_placement_plan(plan,contract)
        self.assertIn('PHOTO_PLACEMENT_ANCESTOR_PENETRATION',
            [r['code'] for r in caught.exception.contract_report['issues']])
        rotated=layout(item('a_prop','tabletop_item',(.2,.2,.1),parent='b_box',part='top'),
            item('b_box','box',(.4,.4,.1),parent='z_table',part='top'),
            item('z_table','dining_table',(1.8,1.,.75)))
        for row in rotated['objects']:row['yaw_deg']=90
        checked(*compile(rotated))

    def test_reverse_ids_compile_three_surface_levels_and_version_only_nested_sidecar(self):
        value=layout(item('a_small','tabletop_item',(.15,.15,.1),parent='b_box',part='top'),
            item('b_box','box',(.5,.4,.25),parent='c_cover',part='top'),
            item('c_cover','surface_covering',(1.2,.7,.03),parent='z_table',part='top'),
            item('z_table','dining_table',(1.8,1.,.75)))
        before=deepcopy(value);payload,trace=compile(value);calls=checked(payload,trace)
        self.assertEqual(trace['placement_contract_version'],'photo-placement-contract-1.2')
        self.assertEqual(placement_contract_from_trace(trace)['schema_version'],'photo-placement-contract-1.2')
        ordered=[call['arguments']['id'] for call in payload['calls']]
        self.assertEqual([identity for identity in ordered if identity in {'a_small','b_box','c_cover','z_table'}],
            ['z_table','c_cover','b_box','a_small'])
        for child,parent in [('c_cover','z_table'),('b_box','c_cover'),('a_small','b_box')]:
            self.assertEqual(support_geometry(calls[child],calls[parent],'top')['status'],'PASS')
        self.assertEqual(calls['c_cover']['catalog_version'],'room-items-1.2')
        self.assertEqual(value,before)
        _,flat=compile(layout(item('z_table','dining_table',(1.8,1.,.75)),
            item('c_cover','surface_covering',(1.2,.7,.03),parent='z_table',part='top')))
        self.assertNotIn('placement_contract_version',flat)
        self.assertEqual(placement_contract_from_trace(flat)['schema_version'],'photo-placement-contract-1.0')

    def test_repacked_parent_is_final_before_descendant_calls_evidence_and_trace(self):
        value=layout(item('a_descendant','tabletop_item',(.1,.1,.1),parent='b_box0',part='top'),
            *(item('b_box'+str(n),'box',(.45,.3,.1),parent='z_table',part='top') for n in range(4)),
            item('z_table','dining_table',(1.8,1.,.75)))
        before=deepcopy(value);payload,trace=compile(value);calls=checked(payload,trace)
        self.assertEqual(trace['bounded_support_searches'][0]['status'],'FOUND')
        self.assertNotEqual(calls['b_box0']['position_m'][:2],calls['z_table']['center_m'])
        self.assertEqual(calls['a_descendant']['position_m'][:2],calls['b_box0']['position_m'][:2])
        positions={row['id']:row['centre_xy_m'] for row in trace['placements']}
        self.assertEqual(positions['a_descendant'],calls['a_descendant']['position_m'][:2])
        ids=[entry['call_id'] for entry in payload['call_evidence']]
        self.assertEqual(ids.count('obj_a_descendant'),1)
        self.assertEqual(ids.count('obj_b_box0'),1)
        self.assertEqual(value,before)

    def test_pending_parent_keeps_inventory_and_descendant_is_hard_dependency_failure(self):
        table=item('z_table','dining_table',(1.8,1.,.75))
        box=item('b_box','box',(3.,2.,.25),parent='z_table',part='top')
        value=layout(item('a_child','tabletop_item',(.1,.1,.1),parent='b_box',part='top'),box,table)
        before=deepcopy(value)
        with self.assertRaises(GeometryValidationError) as caught:compile(value,progressive=True)
        issues=caught.exception.contract_report['issues']
        capacity=next(issue for issue in issues if issue['target_ids']==['b_box'])
        self.assertEqual(capacity['actual']['reason'],'SURFACE_CAPACITY_EXCEEDED')
        dependency=next(issue for issue in issues if issue['code']=='PARENT_VALIDATION_PENDING')
        self.assertEqual(dependency['target_ids'],['a_child'])
        self.assertEqual(dependency['expected']['parent_id'],'b_box')
        self.assertEqual(dependency['actual']['reason'],'PARENT_VALIDATION_PENDING')
        self.assertEqual(value,before)
        self.assertEqual({row['id'] for row in value['objects']},{'a_child','b_box','z_table'})

    def test_descendant_cannot_penetrate_actual_grandparent_shelf(self):
        value=layout(item('a_tall','tabletop_item',(.2,.2,1.),parent='b_box',part='top'),
            item('b_box','box',(.4,.4,.1),parent='z_rack',part='shelf_1'),
            item('z_rack','rack',(1.6,1.,1.8)))
        before=deepcopy(value)
        with self.assertRaises(GeometryValidationError) as caught:compile(value)
        issue=next(issue for issue in caught.exception.contract_report['issues'] if 'a_tall' in issue['target_ids'])
        self.assertEqual(issue['actual']['reason'],'SUPPORT_CLEARANCE_EXCEEDED')
        self.assertTrue(any(identity.startswith('z_rack_') for identity in
            issue['actual']['child']['rejected_parent_parts']))
        self.assertEqual(issue['expected']['bounded_search']['termination_code'],'EMPTY_VALID_DOMAIN')
        self.assertEqual(value,before)

    def test_cycles_and_invalid_parts_remain_hard_failures(self):
        for value,code in [
            (layout(item('a','box',(.5,.5,.2),parent='b',part='top'),
                    item('b','box',(.5,.5,.2),parent='a',part='top')),'PHOTO_RELATION_CYCLE'),
            (layout(item('a','box',(.5,.5,.2),parent='z_table',part='missing'),
                    item('z_table','dining_table',(1.8,1.,.75))),'PHOTO_RELATION_PART_UNSUPPORTED')]:
            before=deepcopy(value)
            with self.subTest(code=code),self.assertRaises(GeometryValidationError) as caught:compile(value,progressive=True)
            self.assertIn(code,[issue['code'] for issue in caught.exception.contract_report['issues']])
            self.assertEqual(value,before)

    def test_surface_covering_schema_is_surface_only_and_has_distinct_default(self):
        schema=layout_schema('Create a cover',None,None,revision=PARAMETRIC_REVISION)
        options=schema['properties']['objects']['items']['anyOf']
        cover=next(branch['properties'] for branch in options if branch['properties']['kind']['enum']==['surface_covering'])
        self.assertEqual(cover['placement']['properties']['relation']['enum'],['surface'])
        self.assertEqual(SIZES['surface_covering'],(1.,.7,.03))


if __name__=='__main__':unittest.main()
