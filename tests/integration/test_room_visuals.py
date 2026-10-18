# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Display meshes must not redefine collision geometry or resurrect old poses."""
from dataclasses import replace
from math import cos, sin, radians, isfinite
import unittest

from twinpulse_core import execute_site_tool_plan
from twinpulse_core.room_visuals import visual_bindings, display_meshes
from twinpulse_core.room_item_catalog import ROOM_ITEM_KINDS
from twinpulse_core.furniture import furniture_kinds
from twinpulse_app.manual_room import manual_room_plan
from tests.integration.test_room_items import clutter_plan
from tests.integration.test_scene_changes import furnished_source


class RoomVisualTests(unittest.TestCase):
    def test_every_catalog_kind_has_named_bounded_nonbox_meshes(self):
        for kind in (*furniture_kinds(), *ROOM_ITEM_KINDS):
            with self.subTest(kind=kind):
                parts=display_meshes(kind,(1.,1.,1.))
                self.assertTrue(parts)
                self.assertLessEqual(len(parts),160)
                self.assertEqual(len({p['name'] for p in parts}),len(parts))
                for p in parts:
                    self.assertTrue(all(isfinite(v) for point in p['points'] for v in point))
                    self.assertTrue(all(len(face)==3 and all(0<=i<len(p['points']) for i in face) for face in p['faces']))
                    self.assertTrue(all(-.550001<=point[0]<=.550001 and -.550001<=point[1]<=.550001 and -1e-6<=point[2]<=1.1 for point in p['points']))
                    self.assertGreater(len(p['points']),8)
        for kind,required in [('bed',{'mattress','pillow_0','quilt'}),('wardrobe',{'clothes_rail','door_handle','shelf_1'}),
                              ('clothes_rack',{'wood_post_0','hanging_rail','coat_0_body'}),
                              ('floor_fan',{'fan_hub','radial_0'}),('office_chair',{'padded_seat','wheel_0'})]:
            self.assertTrue(required<={p['name'] for p in display_meshes(kind,(1.,1.,1.))})

    def test_catalog_invalid_size_and_kind_rejected(self):
        for size in ((1,1,0),(1,float('nan'),1),(1,11,1),(1,1)):
            with self.assertRaises(ValueError):display_meshes('bed',size)
        with self.assertRaises(ValueError):display_meshes('model_supplied_code',(1,1,1))

    def test_thin_and_small_meshes_stay_inside_current_display_envelope(self):
        for size in ((.4,.3,.1),(.8,.02,.06),(.6,.6,.9)):
            for kind in (*furniture_kinds(),*ROOM_ITEM_KINDS):
                for part in display_meshes(kind,size):
                    self.assertTrue(all(-size[0]/2-1e-6<=p[0]<=size[0]/2+1e-6
                        and -size[1]/2-1e-6<=p[1]<=size[1]/2+1e-6
                        and -1e-6<=p[2]<=size[2]+1e-6 for p in part['points']),
                        (kind,size,part['name']))

    def test_all_props_bind_without_mutating_scene_plan_hash_or_keepouts(self):
        plan=clutter_plan(); scene=execute_site_tool_plan(plan,source='manual',source_ref='a'*64).scene
        original,original_plan=scene.to_dict(),plan.to_dict()
        bindings,skipped=visual_bindings(scene,plan)
        self.assertEqual(len(bindings),len(ROOM_ITEM_KINDS));self.assertEqual(skipped,[])
        self.assertIn('pallet',{binding['kind'] for binding in bindings})
        self.assertTrue(any(x.endswith('_keepout') for b in bindings for x in b['members']))
        self.assertEqual(scene.to_dict(),original);self.assertEqual(plan.to_dict(),original_plan)

    def test_group_move_yaw_and_height_use_current_geometry(self):
        draft=furnished_source();scene=draft.site.scene
        original,_=visual_bindings(scene,draft.plan);ids=set(original[0]['members'])
        a=radians(35);c,s=cos(a),sin(a)
        def moved(o):
            x,y,z=o.transform.position_m
            return replace(o,transform=replace(o.transform,position_m=(x*c-y*s+.2,x*s+y*c-.3,z+.4),
                                              rotation_rpy_deg=(0.,0.,o.transform.rotation_rpy_deg[2]+35)))
        updated=replace(scene,objects=tuple(moved(o) if o.id in ids else o for o in scene.objects),parent_revision=scene.revision)
        bindings,skipped=visual_bindings(updated,draft.plan)
        self.assertEqual(skipped,[])
        x,y,z=original[0]['origin'];self.assertEqual(bindings[0]['yaw_deg'],original[0]['yaw_deg']+35)
        for actual,expected in zip(bindings[0]['origin'],(x*c-y*s+.2,x*s+y*c-.3,z+.4)):
            self.assertAlmostEqual(actual,expected)

    def test_missing_resize_individual_move_and_dynamic_keep_proxy_visible(self):
        draft=furnished_source();scene=draft.site.scene
        binding,_=visual_bindings(scene,draft.plan);identity=binding[0]['members'][0]
        for change in ('missing','resize','move','dynamic'):
            objects=[]
            for o in scene.objects:
                if o.id==identity:
                    if change=='missing':continue
                    if change=='resize':o=replace(o,shape=replace(o.shape,dimensions_m=tuple(v*1.1 for v in o.shape.dimensions_m)))
                    if change=='move':o=replace(o,transform=replace(o.transform,position_m=(o.transform.position_m[0]+.2,*o.transform.position_m[1:])))
                    if change=='dynamic':o=replace(o,dynamic=True,mass_kg=2.)
                objects.append(o)
            updated=replace(scene,objects=tuple(objects),parent_revision=scene.revision)
            bindings,skipped=visual_bindings(updated,draft.plan)
            self.assertNotIn(binding[0]['id'],[b['id'] for b in bindings]);self.assertEqual(len(skipped),1)


if __name__=='__main__':unittest.main()
