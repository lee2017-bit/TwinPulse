# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline intent/geometry tests; never claims physical or LLM acceptance."""
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
from tests.integration.test_scene_changes import room_source, furnished_source
from twinpulse_core.simulation_goal import is_navigation_request, coordinates, goal_review, preview_review, target_label_matches
from twinpulse_core.site_simulation import checked_plan, make_plan
from twinpulse_core.bounded_grid_plan import NoBoundedPath
from twinpulse_app.simulation_assets import burger_inventory


class SimulationGoalTests(unittest.TestCase):
    def supported_scene(self):
        scene=room_source().site.scene
        floor=next(o for o in scene.objects if o.kind=='floor')
        original=next(o for o in scene.objects if o.id=='desk')
        support=replace(original,id='carrier',shape=replace(original.shape,dimensions_m=(2.,2.,.12)),
            transform=replace(original.transform,position_m=(0.,0.,.06)))
        child=replace(original,id='cargo',shape=replace(original.shape,dimensions_m=(.2,.2,.2)),
            transform=replace(original.transform,position_m=(0.,0.,.22)))
        scene=replace(scene,objects=(floor,support,child))
        contract=dict(schema_version='photo-placement-contract-1.0',relations=[
            dict(id='carrier',relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None),
            dict(id='cargo',relation='surface',parent_id='carrier',part='deck',anchor='centre',elevation_m=None)])
        return scene,contract

    def test_supported_target_uses_parent_exterior_without_retargeting_or_ignored_collision(self):
        from copy import deepcopy
        scene,contract=self.supported_scene();before=scene.to_dict();saved=deepcopy(contract)
        furniture={'cargo':'box','carrier':'pallet'}
        with self.assertRaisesRegex(ValueError,'SIM_TARGET_NO_REACHABLE_APPROACH'):
            goal_review(scene,'Go to box',[0,-1.8],burger_inventory(),furniture=furniture)
        review=goal_review(scene,'Go to box',[0,-1.8],burger_inventory(),furniture=furniture,placement_contract=contract)
        self.assertEqual(review['target']['id'],'cargo')
        self.assertEqual(review['approach_diagnostic']['support_parent_ids'],['carrier'])
        self.assertEqual(len(review['approach_diagnostic']['attempts']),16)
        self.assertEqual(checked_plan(scene,review['plan']),review['plan'])
        self.assertEqual(scene.to_dict(),before);self.assertEqual(contract,saved)
        self.assertFalse(review['plan']['physical_authority'])

    def test_supported_target_checks_parent_identity_cycle_and_legacy_behavior(self):
        from copy import deepcopy
        scene,contract=self.supported_scene()
        missing=replace(scene,objects=tuple(o for o in scene.objects if o.id!='carrier'))
        with self.assertRaisesRegex(ValueError,'SIM_TARGET_SUPPORT_PARENT_NOT_IN_CURRENT_SCENE'):
            goal_review(missing,'Go to cargo',[0,-1.8],burger_inventory(),placement_contract=contract)
        cyclic=deepcopy(contract);cyclic['relations'][0].update(relation='surface',parent_id='cargo',part='body')
        with self.assertRaisesRegex(ValueError,'PHOTO_PLACEMENT_CYCLE'):
            goal_review(scene,'Go to cargo',[0,-1.8],burger_inventory(),placement_contract=cyclic)
        legacy=goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory())
        floor_only=dict(schema_version=contract['schema_version'],relations=[contract['relations'][0]])
        self.assertEqual(legacy['plan'],goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory(),
            placement_contract=floor_only)['plan'])

    def test_parent_and_child_approach_include_rotated_typed_descendant_actual_keepout(self):
        from twinpulse_core.simulation_goal import scene_targets,_approach_envelope
        from twinpulse_core.room_items import expand_room_item
        scene,contract=self.supported_scene();original=deepcopy(contract)
        # Actual room-item expansion contains a rotated floor keepout plus
        # noncolliding visual parts. Only that actual keepout expands bounds.
        parts=expand_room_item(dict(id='cloth',kind='bedding_overhang',label='Explicit synthetic drape',
            catalog_version='room-items-1.0',position_m=[.8,-1.,.35],dimensions_m=[.6,1.2,.4],
            yaw_deg=35.,observation_time_utc=None))
        template=scene.objects[1]
        unrelated=replace(template,id='carrier_unrelated',transform=replace(template.transform,position_m=(8.,8.,.1)))
        scene=replace(scene,objects=(*scene.objects,*parts,unrelated));before=scene.to_dict()
        contract['schema_version']='photo-placement-contract-1.1'
        contract['relations'].append(dict(id='cloth',relation='drape',parent_id='carrier',part='deck',anchor='front',elevation_m=None))
        groups=scene_targets(scene,{'carrier':'pallet','cargo':'box','cloth':'bedding_overhang','carrier_unrelated':'box'})
        by_id={row['id']:row for row in groups}
        bounds=[min(by_id[i]['bounds'][0] for i in ('carrier','cargo','cloth')),
            max(by_id[i]['bounds'][1] for i in ('carrier','cargo','cloth')),
            min(by_id[i]['bounds'][2] for i in ('carrier','cargo','cloth')),
            max(by_id[i]['bounds'][3] for i in ('carrier','cargo','cloth'))]
        for identity,parents in (('carrier',[]),('cargo',['carrier']),('cloth',['carrier'])):
            with self.subTest(target=identity):
                envelope,chain,objects=_approach_envelope(by_id[identity],groups,contract)
                self.assertEqual(envelope,bounds);self.assertEqual(chain,parents)
                self.assertIn('cloth_keepout',objects)
                self.assertNotIn('carrier_unrelated',objects)
                self.assertFalse(any('_visual_' in i for i in objects))
        self.assertEqual(scene.to_dict(),before)
        self.assertEqual(contract['relations'][:2],original['relations'])

    def test_nested_support_descendant_union_is_bounded_and_does_not_retarget(self):
        from twinpulse_core.simulation_goal import scene_targets,_approach_envelope
        scene,contract=self.supported_scene();child=scene.objects[-1]
        extra=replace(child,id='upper',transform=replace(child.transform,position_m=(1.2,0.,.5)))
        scene=replace(scene,objects=(*scene.objects,extra));contract['schema_version']='photo-placement-contract-1.1'
        contract['relations'].append(dict(id='upper',relation='surface',parent_id='cargo',part='top',anchor='centre',elevation_m=None))
        groups=scene_targets(scene);selected=next(r for r in groups if r['id']=='carrier')
        envelope,parents,objects=_approach_envelope(selected,groups,contract)
        self.assertEqual(parents,[]);self.assertEqual(selected['id'],'carrier')
        self.assertEqual(envelope[1],1.3);self.assertIn('upper',objects)

    def test_relation_suffix_is_not_a_kind_match_but_explicit_child_id_still_works(self):
        scene,contract=self.supported_scene()
        names={'carrier':'pallet_right','cargo':'box_on_pallet'}
        scene=replace(scene,objects=tuple(replace(o,id=names.get(o.id,o.id)) for o in scene.objects))
        for row in contract['relations']:
            row['id']=names[row['id']]
            row['parent_id']=names.get(row['parent_id'],row['parent_id'])
        furniture={'pallet_right':'pallet','box_on_pallet':'box'}
        review=goal_review(scene,'Go to pallet',[0,-1.8],burger_inventory(),furniture=furniture,
            placement_contract=contract)
        self.assertEqual(review['target']['id'],'pallet_right')
        self.assertEqual(review['choices'],[])
        child=goal_review(scene,'Go to pallet id=box_on_pallet',[0,-1.8],burger_inventory(),
            furniture=furniture,placement_contract=contract)
        self.assertEqual(child['target']['id'],'box_on_pallet')
        with self.assertRaisesRegex(ValueError,'SIM_TARGET_NOT_FOUND'):
            goal_review(scene,'Go to pallet',[0,-1.8],burger_inventory(),furniture=furniture,
                placement_contract=contract,selection='box_on_pallet')

    def test_generic_library_head_nouns_are_not_photo_or_id_specific(self):
        for label,text in (('dining_table','Go to table'),('office chair','Go to chair'),
                ('storage_shelf','Go to shelf'),('cardboard box','상자로 가줘')):
            self.assertTrue(target_label_matches(label,text))
        for text in ('Go to stable','Go to tabletop','Go to chair'):
            self.assertFalse(target_label_matches('dining table',text))
        for text in ('Go to cabinet','Go to shelf','Go to bookshelf'):
            self.assertTrue(target_label_matches('storage',text))

    def test_current_semantic_id_is_a_label_not_implicit_unknown_fallback(self):
        scene=room_source().site.scene
        desk=next(o for o in scene.objects if o.id=='desk')
        scene=replace(scene,objects=tuple(replace(o,id='different_pallet') if o.id==desk.id else o
                                         for o in scene.objects))
        result=goal_review(scene,'Go to pallet',[0,-1.8],burger_inventory(),
            furniture={'different_pallet':'unknown'})
        self.assertEqual(result['target']['id'],'different_pallet')
        with self.assertRaisesRegex(ValueError,'SIM_TARGET_NOT_FOUND'):
            goal_review(scene,'Go to Mars',[0,-1.8],burger_inventory(),
                furniture={'different_pallet':'unknown'})

    def test_generic_head_noun_retains_ambiguity_and_explicit_selection(self):
        scene=room_source().site.scene
        desk=next(o for o in scene.objects if o.id=='desk')
        scene=replace(scene,objects=scene.objects+(replace(desk,id='otherDesk',
            transform=replace(desk.transform,position_m=(1.,1.5,.35))),))
        furniture={'desk':'dining_table','otherDesk':'coffee_table'}
        review=goal_review(scene,'Go to table',[0,-1.8],burger_inventory(),furniture=furniture)
        self.assertIsNone(review['plan']);self.assertEqual(len(review['choices']),2)
        selected=goal_review(scene,'Go to table id=desk',[0,-1.8],burger_inventory(),furniture=furniture)
        self.assertEqual(selected['target']['id'],'desk')

    def test_generated_preview_checks_geometry_without_changing_scene(self):
        scene=furnished_source().site.scene
        before=scene.to_dict()
        preview=preview_review(scene,burger_inventory())
        self.assertEqual(checked_plan(scene,preview['plan']),preview['plan'])
        self.assertFalse(preview['plan']['physical_authority'])
        self.assertEqual(scene.to_dict(),before)
        self.assertEqual(preview_review(scene,burger_inventory()),preview)

    def test_generated_preview_rejects_no_clear_corridor(self):
        scene=room_source().site.scene
        floor=next(o for o in scene.objects if o.kind=='floor')
        small=replace(scene,objects=(replace(floor,shape=replace(floor.shape,dimensions_m=(.4,.4,.1))),))
        with self.assertRaisesRegex(ValueError,'SIM_PREVIEW_'):
            preview_review(small,burger_inventory())

    def test_generated_preview_reaches_late_clear_outer_lattice_without_relaxed_collision(self):
        scene=room_source().site.scene
        floor=next(o for o in scene.objects if o.kind=='floor')
        original=next(o for o in scene.objects if o.id=='desk')
        # A conservative cross blocks all inner/edge starts. Only the outer
        # corner lattice permits a checked short route; this is synthetic,
        # unrelated to any photo/room ID, with the normal robot/path checks.
        blockers=tuple(replace(original,id=identity,
            shape=replace(original.shape,dimensions_m=size),
            transform=replace(original.transform,position_m=(0.,0.,.35)))
            for identity,size in (('cross_horizontal',(4.,3.5,.7)),('cross_vertical',(3.5,4.,.7))))
        scene=replace(scene,objects=(floor,*blockers))
        inventory=burger_inventory();before=scene.to_dict();assets=deepcopy(inventory)
        with patch('twinpulse_core.simulation_goal.make_plan',wraps=make_plan) as planner:
            review=preview_review(scene,inventory)
        declared_budget=len(range(1,10))**2*len((.4,.25))*len(((0,1),(1,0),(0,-1),(-1,0)))
        self.assertGreater(planner.call_count,512)
        self.assertLessEqual(planner.call_count,declared_budget)
        self.assertEqual(checked_plan(scene,review['plan']),review['plan'])
        self.assertFalse(review['plan']['physical_authority'])
        self.assertEqual(scene.to_dict(),before);self.assertEqual(inventory,assets)

    def test_generated_preview_all_blocked_terminates_after_complete_finite_set(self):
        scene=room_source().site.scene
        floor=next(o for o in scene.objects if o.kind=='floor')
        scene=replace(scene,objects=(replace(floor,shape=replace(floor.shape,dimensions_m=(.4,.4,.1))),))
        inventory=burger_inventory();before=scene.to_dict();assets=deepcopy(inventory)
        with patch('twinpulse_core.simulation_goal.make_plan',wraps=make_plan) as planner:
            with self.assertRaisesRegex(ValueError,'^SIM_PREVIEW_NO_REACHABLE_ROUTE$'):
                preview_review(scene,inventory)
        declared_budget=len(range(1,10))**2*len((.4,.25))*len(((0,1),(1,0),(0,-1),(-1,0)))
        self.assertEqual(planner.call_count,declared_budget)
        candidates={(tuple(c.args[1]),tuple(c.args[2])) for c in planner.call_args_list}
        self.assertEqual(len(candidates),declared_budget)
        self.assertEqual(scene.to_dict(),before);self.assertEqual(inventory,assets)

    def test_generated_preview_complete_set_preserves_grid_budget_cause(self):
        inventory=burger_inventory();before=self.scene.to_dict();assets=deepcopy(inventory)
        with patch('twinpulse_core.simulation_goal.make_plan',side_effect=NoBoundedPath('GRID_BUDGET_EXCEEDED')) as planner:
            with self.assertRaisesRegex(NoBoundedPath,'^GRID_BUDGET_EXCEEDED$'):
                preview_review(self.scene,inventory)
        declared_budget=len(range(1,10))**2*len((.4,.25))*len(((0,1),(1,0),(0,-1),(-1,0)))
        self.assertEqual(planner.call_count,declared_budget)
        self.assertEqual(self.scene.to_dict(),before);self.assertEqual(inventory,assets)

    def test_large_estimated_sim_floor_direct_preview_preserves_scene_and_identity(self):
        scene=room_source().site.scene
        floor=next(o for o in scene.objects if o.kind=='floor')
        large=replace(scene,objects=(replace(floor,shape=replace(floor.shape,dimensions_m=(10.,12.,.1))),))
        before=large.to_dict()
        review=preview_review(large,burger_inventory())
        self.assertEqual(review['plan']['start'],[0.,0.])
        self.assertEqual(review['plan']['route'],[[0.,.4]])
        self.assertEqual(checked_plan(large,review['plan']),review['plan'])
        self.assertFalse(review['plan']['physical_authority'])
        self.assertEqual(large.to_dict(),before)

    def test_invalid_assets_are_not_hidden_as_candidate_search_failure(self):
        with self.assertRaisesRegex(ValueError,'SIM_ASSET_INVENTORY_INVALID'):
            preview_review(room_source().site.scene,{})

    def test_symbolic_goal_does_not_hide_invalid_assets(self):
        with self.assertRaisesRegex(ValueError,'SIM_ASSET_INVENTORY_INVALID'):
            goal_review(room_source().site.scene,'Go to bed',[0,-1.8],{})

    def test_symbolic_goal_does_not_hide_unexpected_planner_error(self):
        def broken(_):
            raise ValueError('PLANNER_CONFIGURATION_INVALID')
        with self.assertRaisesRegex(ValueError,'PLANNER_CONFIGURATION_INVALID'):
            goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory(),planner=broken)

    def test_all_rejected_approaches_keep_each_cause(self):
        def rejected(_):
            raise NoBoundedPath('START_OR_GOAL_BLOCKED')
        with self.assertRaises(ValueError) as caught:
            goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory(),planner=rejected)
        diagnostic=caught.exception.goal_diagnostic
        self.assertEqual(diagnostic['termination_code'],'NO_ACCEPTED_EXTERIOR_CANDIDATE')
        self.assertEqual(diagnostic['reason_counts'],{'START_OR_GOAL_BLOCKED':16})
        self.assertEqual(len(diagnostic['attempts']),16)
        self.assertFalse(diagnostic['physical_authority'])

    def test_planner_budget_is_not_reported_as_proved_no_path(self):
        def exhausted(_):
            raise NoBoundedPath('SEARCH_BUDGET_EXCEEDED')
        with self.assertRaises(ValueError) as caught:
            goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory(),planner=exhausted)
        self.assertEqual(caught.exception.goal_diagnostic['termination_code'],'PLANNER_BUDGET_EXHAUSTED')

    def test_success_keeps_bounded_candidate_evidence(self):
        review=goal_review(room_source().site.scene,'Go to bed',[0,-1.8],burger_inventory())
        diagnostic=review['approach_diagnostic']
        self.assertEqual(diagnostic['termination_code'],'FOUND')
        self.assertEqual(len(diagnostic['attempts']),16)
        self.assertEqual(diagnostic['selected_point'],review['plan']['goal'])

    def setUp(self):
        self.scene=room_source().site.scene
        self.inventory=burger_inventory()

    def test_intent_does_not_capture_scene_edits(self):
        for text in ('Go to the bed','Please navigate to desk','Show the route to bed','침대로 가줘',
                '책상으로 이동해줘','로봇을 앞으로 이동해줘','장애물을 피해 이동해줘'):
            self.assertTrue(is_navigation_request(text))
        for text in ('Add a bed','Move chair x=1 y=1','Change the desk','create room',
                '책상을 앞쪽으로 0.1m 이동해줘. 책상 위 물체는 함께 이동하고 크기는 유지해줘.',
                '소파를 왼쪽으로 이동해줘','shelf_2를 오른쪽으로 이동해줘'):
            self.assertFalse(is_navigation_request(text))

    def test_coordinate_pairs_require_complete_axes(self):
        self.assertEqual(coordinates('Go from x=0 y=-1 to x=.5 y=1'),([0.,-1.],[.5,1.]))
        for text in ('Go x=nan y=1','Go x=1','Go x=1 y=2 x=3','Go x=1 x=2','Go x=1 y=2 x=3 y=4'):
            with self.assertRaises(ValueError):coordinates(text)

    def test_start_not_invented(self):
        with self.assertRaisesRegex(ValueError,'SIM_START_REQUIRED'):
            goal_review(self.scene,'Go to bed',None,self.inventory)

    def test_object_approach_uses_same_collision_checked_plan(self):
        before=self.scene.to_dict()
        review=goal_review(self.scene,'Go to bed',[0,-1.8],self.inventory)
        self.assertEqual(review['target']['id'],'bed')
        self.assertEqual(checked_plan(self.scene,review['plan']),review['plan'])
        x,y=review['plan']['goal'];self.assertFalse(-1.6<x<-.4 and -.9<y<.9)
        self.assertEqual(self.scene.to_dict(),before)
        explicit=goal_review(self.scene,'Go from x=0 y=-1.8 to bed',None,self.inventory)
        self.assertEqual(explicit['plan'],review['plan'])
        self.assertEqual(goal_review(self.scene,'침대로 가줘',[0,-1.8],self.inventory)['target']['id'],'bed')

    def test_duplicate_targets_require_choice_not_nearest_guess(self):
        desk=next(o for o in self.scene.objects if o.id=='desk')
        scene=replace(self.scene,objects=self.scene.objects+(replace(desk,id='desk_two',transform=replace(desk.transform,position_m=(1.,1.5,.35))),))
        review=goal_review(scene,'Go to desk',[0,-1.8],self.inventory,furniture={'desk':'desk','desk_two':'desk'})
        self.assertIsNone(review['plan']);self.assertEqual(len(review['choices']),2)
        selected=goal_review(scene,'Go to desk',[0,-1.8],self.inventory,furniture={'desk':'desk','desk_two':'desk'},selection='desk_two')
        self.assertEqual(selected['target']['id'],'desk_two')

    def test_furniture_parts_grouped_and_unknown_not_fallback(self):
        scene=furnished_source().site.scene
        review=goal_review(scene,'Go to bed',[0,-1.4],self.inventory,furniture={'furn_1_bed':'bed','furn_2_desk':'desk'})
        self.assertGreater(len(review['target']['object_ids']),1)
        with self.assertRaisesRegex(ValueError,'SIM_TARGET_NOT_FOUND'):
            goal_review(scene,'Go to Mars',[0,-1.4],self.inventory)

    def test_blocked_coordinate_is_not_replaced_by_object_approach(self):
        with self.assertRaises(ValueError):goal_review(self.scene,'Go to bed x=-1 y=0',[0,-1.8],self.inventory)


if __name__=='__main__':unittest.main()
