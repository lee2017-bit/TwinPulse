# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned props, supplied-photo coverage and existing edit/SIM paths. No robot."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core import SiteToolPlan, execute_site_tool_plan
from twinpulse_core.room_items import checked_room_item, expand_room_item, room_inventory, room_item_kinds, room_item_risk
from tests.fixtures.historical_room_photo_inventory import photo_reference, inventory_coverage, PHOTO_SHA256
from twinpulse_app.manual_room import manual_room_plan
from twinpulse_app.scene_changes import SceneChangeStore
from twinpulse_app.site_draft import SiteDraftRecord
from twinpulse_core.site_simulation import make_plan
from twinpulse_app.simulation_assets import burger_inventory
from twinpulse_provider.schema import site_tool_plan_json_schema
from twinpulse_provider import ObservationArtifact
from tests.integration.test_scene_changes import room_source, furniture


def item(kind='cable_bundle', object_id='cables', x=0.,y=0.,z=.05):
    from twinpulse_core.room_item_catalog import room_item_catalog_version
    return dict(id=object_id,kind=kind,label=kind.replace('_',' '),catalog_version=room_item_catalog_version(kind),
        position_m=[x,y,z],dimensions_m=[.4,.3,.1],yaw_deg=0.,observation_time_utc=None)


def clutter_plan():
    """All compiler categories; not the legacy manual profile's 24-pick UI."""
    # 2026-10-27: rows start at y=.6 so the sixth row (26 kinds with floor_lamp) stays on the 8 m floor.
    items=[item(kind,kind, -2.4+(i%5)*1.2, .6+(i//5)*.6,
                .8 if kind in {'monitor','tabletop_item','window_blind','ceiling_light'} else .05)
           for i,kind in enumerate(room_item_kinds())]
    from twinpulse_core.site_tools import SceneToolCall,SiteCallEvidence
    base=manual_room_plan('clutter_fixture',7.,8.,2.6,room_items=items[:24])
    extra=tuple(SceneToolCall('extra_prop_'+str(i),'place_room_item',checked_room_item(args))
        for i,args in enumerate(items[24:]))
    return replace(base,calls=base.calls+extra,call_evidence=base.call_evidence+tuple(
        SiteCallEvidence(c.call_id,(),'user','Explicit synthetic compiler category fixture') for c in extra))


class RoomItemTests(unittest.TestCase):
    def test_outside_floor_preserves_expansion_owner_and_numeric_bounds(self):
        for identity,kind in (('prop_owner_7','window_blind'),('different_name','cable_bundle')):
            args=item(kind,identity,x=2.4,z=.8 if kind=='window_blind' else .05)
            plan=manual_room_plan('bounds',5.,5.,2.6,room_items=[args])
            from twinpulse_core.scene_tools import SceneToolPlanError
            with self.assertRaises(SceneToolPlanError) as caught:
                execute_site_tool_plan(plan,source='manual',source_ref='a'*64)
            row=caught.exception.contract_report['issues'][0]
            self.assertEqual(row['code'],'ROOM_ITEM_OUTSIDE_FLOOR')
            self.assertEqual(row['target_ids'],[identity])
            self.assertTrue(row['repairable']);self.assertGreater(row['violation_m'],0)
            self.assertEqual(row['expected']['floor_size_m'],[5.,5.])
            self.assertTrue(row['actual']['generated_part_id'].startswith(identity))

    def test_integer_geometry_roundtrip_without_changing_plan_or_hash_contract(self):
        import json
        from twinpulse_core import SceneRevision, canonical_sha256
        for kind in room_item_kinds():
            with self.subTest(kind=kind):
                args=item(kind);args.update(position_m=[0,0,1],dimensions_m=[1,1,1],yaw_deg=0)
                if kind=='surface_covering':args['dimensions_m'][2]=.1 # thin layer is not a one-metre cube
                original=deepcopy(args)
                plan=manual_room_plan('numeric_props',5.,5.,2.6,room_items=[args])
                digest=canonical_sha256(plan.to_dict())
                scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
                restored=SceneRevision.from_dict(json.loads(json.dumps(scene.to_dict())))
                self.assertEqual(scene.to_dict(),restored.to_dict())
                self.assertEqual(scene.revision,restored.revision)
                self.assertEqual(args,original)
                self.assertEqual(canonical_sha256(plan.to_dict()),digest)
                float_args={**args,'position_m':[0.,0.,1.],'dimensions_m':[float(v) for v in args['dimensions_m']],'yaw_deg':0.}
                self.assertEqual(expand_room_item(args),expand_room_item(float_args))
                tampered=json.loads(json.dumps(scene.to_dict()))
                tampered['objects'][-1]['transform']['position_m'][0]+=.01
                with self.assertRaisesRegex(ValueError,'digest mismatch'):SceneRevision.from_dict(tampered)

    def test_versioned_schema_and_all_categories_expand_roundtrip(self):
        names=lambda v:{x['properties']['tool']['const'] for x in site_tool_plan_json_schema(v)['properties']['calls']['items']['anyOf']}
        self.assertNotIn('place_room_item',names('2.1'))
        self.assertIn('place_room_item',names('2.2'))
        self.assertEqual(site_tool_plan_json_schema('2.1')['properties']['calls']['maxItems'],24)
        self.assertEqual(site_tool_plan_json_schema('2.2')['properties']['calls']['maxItems'],40)
        plan=clutter_plan(); restored=SiteToolPlan.from_dict(plan.to_dict())
        self.assertEqual(plan.to_dict(),restored.to_dict())
        scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
        inventory=room_inventory(plan,scene)
        self.assertEqual(len(inventory['items']),len(room_item_kinds()))
        self.assertTrue(all(r['placement_status']=='represented' for r in inventory['items']))
        self.assertFalse(inventory['live_observation'])
        self.assertTrue(all(r['last_observation_utc'] is None for r in inventory['items']))

    def test_floor_lamp_is_a_tall_slim_rigid_prop_in_its_own_catalog_version(self):
        # 2026-10-27: a photographed floor lamp only fitted small_equipment (a 0.3 m cube).
        from twinpulse_core.room_visuals import display_meshes
        from twinpulse_provider.photo_layout import _model_fields
        args=dict(item('floor_lamp','lamp',z=.8),dimensions_m=[.4,.4,1.6])
        self.assertEqual(args['catalog_version'],'room-items-1.3')
        with self.assertRaises(ValueError):checked_room_item({**args,'catalog_version':'room-items-1.0'})
        call=next(x for x in site_tool_plan_json_schema('2.2')['properties']['calls']['items']['anyOf'] if x['properties']['tool']['const']=='place_room_item')
        self.assertIn('floor_lamp',call['properties']['arguments']['properties']['kind']['enum'])
        self.assertIn('room-items-1.3',call['properties']['arguments']['properties']['catalog_version']['enum'])
        parts=expand_room_item(args);self.assertEqual(room_item_risk(args),'collision');self.assertTrue(all(p.collision for p in parts))
        self.assertAlmostEqual(max(p.transform.position_m[2]+p.shape.dimensions_m[2]/2 for p in parts),1.6)
        self.assertLess(parts[1].shape.dimensions_m[0],.1)  # the pole between base disc and shade is slim
        self.assertEqual({p['name'] for p in display_meshes('floor_lamp',(.4,.4,1.6))},{'base_disc','pole','shade'})
        # The planner may only stand it on the floor, like floor_fan, and the compiler checks the same.
        from twinpulse_core.room_item_catalog import REQUIRED_ROOM_RELATIONS
        self.assertEqual(_model_fields('floor_lamp',allowed_parents={'desk':'desk'})['placement']['properties']['relation'],{'enum':['floor']})
        self.assertEqual(REQUIRED_ROOM_RELATIONS['floor_lamp'],'floor')

    def test_strict_invalid_arguments_no_hidden_collision_or_timestamp(self):
        for changed in ({'position_m':[0,0,0]}, {'dimensions_m':[0,.3,.1]}, {'position_m':[float('nan'),0,.05]},
                        {'yaw_deg':True},{'kind':'drone'},{'catalog_version':'future'},
                        {'observation_time_utc':'2026-10-05T00:00:00'}, {'label':''}, {'extra':True}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):checked_room_item({**item(),**changed})
        checked_room_item({**item(),'observation_time_utc':'2026-10-05T00:00:00Z'})
        for kind in ('cable_bundle','clothing_pile','hanging_clothes','bedding_overhang','unknown'):
            parts=expand_room_item(item(kind))
            self.assertFalse(parts[0].collision)
            self.assertTrue(parts[-1].collision)
            self.assertTrue(parts[-1].id.endswith('_keepout'))
            self.assertAlmostEqual(parts[-1].shape.dimensions_m[0],.6)
        self.assertEqual(room_item_risk(item('monitor')),'collision')
        self.assertEqual(room_item_risk(item('monitor',z=.8)),'visual_only')

    def test_keepouts_block_route_and_bounds_do_not_clip(self):
        plan=manual_room_plan('cables',5.,5.,2.6,room_items=[item()])
        scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
        with self.assertRaises(ValueError):make_plan(scene,[-1.,0.],[0.,0.],burger_inventory())
        route=make_plan(scene,[-1.,0.],[1.,0.],burger_inventory())
        self.assertFalse(route['physical_authority'])
        self.assertGreater(len(route['route']),2)
        with self.assertRaises(ValueError):execute_site_tool_plan(
            manual_room_plan('edge',5.,5.,2.6,room_items=[item(x=2.4)]),source='manual',source_ref='a'*64)

    def test_photo_inventory_exact_image_and_missing_partial_geometry(self):
        self.assertIsNone(photo_reference('b'*64))
        reference=photo_reference(PHOTO_SHA256)
        pending=inventory_coverage(reference,None)
        self.assertEqual(len(pending['items']),24)
        self.assertEqual(len(pending['missing_route_items']),19)
        plan=manual_room_plan('cables',5.,5.,2.6,room_items=[item()])
        scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
        represented=room_inventory(plan,scene)
        self.assertNotIn('cables',inventory_coverage(reference,represented)['missing_route_items'])
        scene=replace(scene,objects=tuple(o for o in scene.objects if not o.id.endswith('_keepout')))
        self.assertIn('cables',inventory_coverage(reference,room_inventory(plan,scene))['missing_route_items'])
        wrong=deepcopy(represented);wrong['items'][0]['kind']='box'
        self.assertIn('cables',inventory_coverage(reference,wrong)['missing_route_items'])

    def test_all_24_photo_items_can_be_represented_without_exceeding_object_budget(self):
        reference=photo_reference(PHOTO_SHA256)
        from twinpulse_core import SceneToolCall
        plan=manual_room_plan('complete_inventory',12.,12.,2.6)
        calls=list(plan.calls)
        for i,row in enumerate(reference['items']):
            x=-4.5+(i%6)*1.6;y=-4.5+(i//6)*2.5
            if row['kind'] in {'bed','wardrobe','desk'}:
                calls.append(SceneToolCall.from_dict(furniture('place_'+row['id'],row['id'],row['kind'],x,y)))
            else:
                args=item(row['kind'],row['id'],x,y,.8 if not row['required_for_route'] else .05)
                calls.append(SceneToolCall('place_'+row['id'],'place_room_item',args))
        plan=replace(plan,plan_version='2.2',calls=tuple(calls),call_evidence=None)
        scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
        coverage=inventory_coverage(reference,room_inventory(plan,scene))
        self.assertTrue(coverage['route_inventory_complete'])
        self.assertEqual(len(coverage['items']),24)
        self.assertLessEqual(len(scene.objects),64)
        self.assertFalse(coverage['live_observation'])
        self.assertEqual(coverage['physical_validation'],'NOT_RUN')

    def test_new_props_existing_edit_history_preserves_original_and_version(self):
        source=room_source(); before=source.to_dict()
        with TemporaryDirectory() as directory:
            store=SceneChangeStore(Path(directory)/'edits.json',project_id='room',source=source)
            call=dict(call_id='cables_call',tool='place_room_item',arguments=item(y=-1.5))
            preview=store.load().preview(source,operation_id='add_cables',mode='add',target_call_id=None,tool_call=call)
            store.apply(preview['operation'],preview['preview_digest'])
            reloaded=SceneChangeStore(store.path,project_id='room',source=source)
            plan,scene=reloaded.load().replay(source)
            self.assertEqual(plan.plan_version,'2.2')
            preview=reloaded.load().preview(source,operation_id='add_chair',mode='add',target_call_id=None,
                tool_call=furniture('chair_call','new_chair','chair',0,1.5))
            reloaded.apply(preview['operation'],preview['preview_digest'])
            self.assertEqual(reloaded.load().replay(source)[0].plan_version,'2.2')
            call['arguments']['yaw_deg']=90
            preview=reloaded.load().preview(source,operation_id='rotate_cables',mode='change',target_call_id='cables_call',tool_call=call)
            reloaded.apply(preview['operation'],preview['preview_digest'])
            self.assertEqual(source.to_dict(),before)

    def test_selected_provider_prompt_has_generic_catalog_not_reviewed_inventory(self):
        from twinpulse_provider import NebiusChatCompletionsPipelineProvider,GenerationRequest
        from twinpulse_provider.contracts import ImageInput
        from packages.twinpulse_provider.tests.test_nebius_pipeline import observation
        provider=NebiusChatCompletionsPipelineProvider(None,observer_model_id='observer',planner_model_id='planner',site_plan_version='2.2')
        image=b'explicit fixture'
        body=provider.build_planner_body(GenerationRequest(request_id='props',prompt='My room',
            images=(ImageInput('room.jpg','image/jpeg',image),)),ObservationArtifact.from_mapping(observation()))
        import json
        encoded=json.dumps(body)
        self.assertIn('site-tools-2.2',encoded)
        self.assertNotIn('reviewed_photo_inventory',encoded)
        self.assertNotIn('Loose floor cable bundle',encoded)
        self.assertIn('never invent freshness',encoded)


if __name__=='__main__':unittest.main()
