# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary pure-core recipe regressions, not live LLM/Isaac acceptance."""
from copy import deepcopy
import unittest
from twinpulse_core.model_recipe import (checked_recipe, compiled_parts, expression, expand_model_recipe,
    recipe_model_id, recipe_digest, recipe_manifest, recipe_display_meshes, INTERPRETER_VERSION, RECIPE_VERSION)
from twinpulse_core.photo_quality import support_surface, support_geometry
from twinpulse_core.site_tools import SiteToolPlan, execute_site_tool_plan
from twinpulse_core.revisions import canonical_sha256


def op(name,a,b):return dict(op=name,args=[a,b])


def shelf_recipe():
    definitions=[dict(name=k,type='number',minimum=lo,maximum=hi,default=default) for k,lo,hi,default in
        [('width',.4,2.,1.),('depth',.25,.8,.4),('height',.6,2.5,1.6)]]
    definitions.append(dict(name='shelf_count',type='integer',minimum=1,maximum=5,default=3))
    def part(identity,center,size,support=False,repeat=None):
        return dict(id=identity,center=center,size=size,material='white',support_top=support,repeat=repeat)
    return dict(schema_version=RECIPE_VERSION,interpreter_version=INTERPRETER_VERSION,title='Adjustable open shelf',
        family='home',kind='storage',parameters=definitions,parts=[
            part('left',[op('add',op('mul','width',-.5),.01),0,op('mul','height',.5)],[.02,'depth','height']),
            part('right',[op('sub',op('mul','width',.5),.01),0,op('mul','height',.5)],[.02,'depth','height']),
            part('back',[0,op('sub',op('mul','depth',.5),.01),op('mul','height',.5)],['width',.02,'height']),
            part('base',[0,0,.01],['width','depth',.02]),
            part('shelf',[0,0,op('mul',op('div','height',op('add','shelf_count',1)),op('add','index',1))],
                 [op('sub','width',.04),op('sub','depth',.02),.02],True,'shelf_count')])


def arguments(recipe=None,yaw=0):
    recipe=recipe or shelf_recipe()
    return dict(id='shelf',kind=recipe['kind'],model_id=recipe_model_id(recipe),recipe_sha256=recipe_digest(recipe),
        interpreter_version=INTERPRETER_VERSION,recipe=recipe,
        parameters={p['name']:p['default'] for p in recipe['parameters']},center_m=[0,0],yaw_deg=yaw)


class ModelRecipeTests(unittest.TestCase):
    def test_every_part_needs_connected_floor_path_and_actual_envelope(self):
        recipe=shelf_recipe()
        recipe['parts'].append(dict(id='floating',center=[0,0,op('mul','height',.9)],size=[.1,.1,.002],
            material='wood',support_top=True,repeat=None))
        with self.assertRaisesRegex(ValueError,'DISCONNECTED_PARTS'):checked_recipe(recipe)
        recipe=shelf_recipe()
        for p in recipe['parts']:
            p['size'][2]=op('mul',p['size'][2],.8)
            p['center'][2]=op('mul',p['center'][2],.8)
        with self.assertRaisesRegex(ValueError,'DIMENSION_ENVELOPE_MISMATCH'):checked_recipe(recipe)

    def test_legacy_snapshot_replay_retained_but_invalid_new_reuse_excluded(self):
        from twinpulse_core.model_recipe import recipe_reuse_problem
        recipe=shelf_recipe();recipe['interpreter_version']='model-recipe-compiler-1.0'
        recipe['parts'].append(dict(id='floating',center=[0,0,op('mul','height',.9)],size=[.1,.1,.002],
            material='wood',support_top=True,repeat=None))
        args=arguments(recipe);args['interpreter_version']=recipe['interpreter_version']
        self.assertTrue(expand_model_recipe(args))
        self.assertIn('DISCONNECTED_PARTS',recipe_reuse_problem(recipe))
        self.assertFalse(recipe_manifest(recipe)['reusable'])
        self.assertEqual(recipe_manifest(recipe)['interpreter_version'],recipe['interpreter_version'])
    def test_unknown_floor_recipe_keeps_unknown_motion_envelope(self):
        recipe=shelf_recipe();recipe['kind']='unknown';args=arguments(recipe)
        parts=expand_model_recipe(args)
        self.assertEqual(parts[-1].id,'shelf_keepout');self.assertTrue(parts[-1].collision)
        self.assertAlmostEqual(parts[-1].shape.dimensions_m[0],1.2)
        self.assertEqual(recipe_manifest(recipe)['risk'],'unknown')
        recipe['parts'][0]['id']='keepout'
        with self.assertRaisesRegex(ValueError,'RESERVED_PART_ID'):checked_recipe(recipe)

    def test_parameterized_geometry_and_real_support(self):
        recipe=checked_recipe(shelf_recipe());args=arguments(recipe)
        self.assertEqual(len(expand_model_recipe(args)),7)
        self.assertEqual(recipe_manifest(recipe)['support_parts'],['shelf_0','shelf_1','shelf_2'])
        self.assertTrue(len(recipe_display_meshes(args))==7)
        before=canonical_sha256([p.transform.position_m for p in expand_model_recipe(args)])
        resized=deepcopy(args);resized['parameters']['height']=2.
        self.assertNotEqual(before,canonical_sha256([p.transform.position_m for p in expand_model_recipe(resized)]))
        self.assertEqual(recipe_digest(recipe),recipe_digest(deepcopy(recipe)))

    def test_child_fit_and_clearance_at_rotated_surface(self):
        for yaw in (0,90,180,-90):
            parent=arguments(yaw=yaw);surface=support_surface(parent,'shelf_0')
            child=dict(id='book',kind='tabletop_item',label='book',catalog_version='room-items-1.0',
                position_m=[*surface.transform.position_m[:2],surface.transform.position_m[2]+.01+.04],
                dimensions_m=[.12,.1,.08],yaw_deg=yaw,observation_time_utc=None)
            self.assertEqual(support_geometry(child,parent,'shelf_0')['status'],'PASS')
            child['dimensions_m'][2]=.7;child['position_m'][2]=surface.transform.position_m[2]+.01+.35
            result=support_geometry(child,parent,'shelf_0')
            self.assertEqual(result['status'],'FAIL')
            self.assertIn('shelf_shelf_1',result['parent_collision_ids'])
        self.assertIsNone(support_surface(arguments(),'nonexistent'))

    def test_snapshot_pin_and_tampering(self):
        old=arguments();new=deepcopy(old['recipe']);new['title']='Another version'
        self.assertNotEqual(recipe_digest(new),old['recipe_sha256'])
        old_geometry=expand_model_recipe(old)
        self.assertEqual(old_geometry,expand_model_recipe(deepcopy(old)))
        corrupt=deepcopy(old);corrupt['recipe']=new
        with self.assertRaisesRegex(ValueError,'BINDING_MISMATCH'):expand_model_recipe(corrupt)
        corrupt=deepcopy(old);corrupt['interpreter_version']='future'
        with self.assertRaisesRegex(ValueError,'BINDING_MISMATCH'):expand_model_recipe(corrupt)

    def test_unsupported_code_and_parameter_errors(self):
        for expr in ('__import__',{'op':'eval','args':['width',1]},op('div',1,0),float('nan')):
            with self.subTest(expr=expr),self.assertRaises(ValueError):expression(expr,{'width':1})
        recipe=shelf_recipe();recipe['parts'][0]['support_top']=True
        with self.assertRaisesRegex(ValueError,'SUPPORT_NOT_HORIZONTAL'):checked_recipe(recipe)
        recipe=shelf_recipe();recipe['parts'][0]['center'][0]=100
        with self.assertRaisesRegex(ValueError,'OUTSIDE_ENVELOPE'):checked_recipe(recipe)
        recipe=shelf_recipe();recipe['parts'][0]['repeat']='width'
        with self.assertRaisesRegex(ValueError,'REPEAT_INVALID'):checked_recipe(recipe)
        args=arguments();args['parameters']['shelf_count']=2.5
        with self.assertRaisesRegex(ValueError,'INSTANCE_RANGE'):expand_model_recipe(args)

    def test_real_site_executor_and_existing_clearance(self):
        plan=dict(plan_version='2.2',scene_id='generic_shelf_trial',summary='Shelf trial',image_observations='',
            calls=[dict(call_id='floor',tool='create_floor',arguments=dict(id='floor',center_m=[0,0],size_m=[4,5])),
                   dict(call_id='shelf',tool='place_model_recipe',arguments=arguments())])
        result=execute_site_tool_plan(SiteToolPlan.from_dict(plan),source='manual',source_ref='a'*64)
        self.assertEqual(len(result.scene.objects),8)
        from twinpulse_core.site_contracts import SceneRevision
        import json
        reopened=SceneRevision.from_dict(json.loads(json.dumps(result.scene.to_dict())))
        self.assertEqual(reopened.revision,result.scene.revision)
        from twinpulse_core.room_items import room_inventory
        inventory=room_inventory(SiteToolPlan.from_dict(plan),result.scene)
        self.assertEqual(len(inventory['items']),1)
        self.assertEqual(inventory['items'][0]['id'],'shelf')
        self.assertEqual(inventory['items'][0]['placement_status'],'represented')
        self.assertEqual(len(inventory['items'][0]['geometry']),7)
        plan['calls'][1]['arguments']['center_m']=[1.8,0]
        with self.assertRaisesRegex(ValueError,'outside the floor'):execute_site_tool_plan(
            SiteToolPlan.from_dict(plan),source='manual',source_ref='a'*64)


if __name__=='__main__':unittest.main()
