# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary geometry evidence tests, not real-model photo acceptance."""
from copy import deepcopy
import unittest
from twinpulse_core import canonical_sha256
from twinpulse_core.model_recipe import recipe_model_id,ModelRecipeError,RECIPE_VERSION,INTERPRETER_VERSION
from twinpulse_provider.assembly_evidence import describe,recipe_descriptor
from twinpulse_provider.model_recipe_planning import available_models
from twinpulse_provider.model_recipe_authoring import compile_authoring
from twinpulse_provider.render_review import compiled_geometry,repair_geometry_context
from test_recipe_authoring import table


class AssemblyEvidenceTests(unittest.TestCase):
    def test_boundary_coverage_tracks_actual_signed_side_not_kind_or_name(self):
        parts=[dict(id='opaque',center=[0,-.24,.5],size=[1,.02,1]),
            dict(id='top',center=[0,0,.99],size=[1,.5,.02],support_top=True)]
        original=deepcopy(parts)
        value=describe(parts,[1,.5,1],yaw_deg=90,centre_xy=[2,3])
        by_side={p['local_face']:p for p in value['side_faces']}
        self.assertEqual(by_side['y-']['covered_area_ratio'],1)
        self.assertEqual(by_side['y-']['world_outward_xy'],[1,0])
        self.assertLess(by_side['y+']['covered_area_ratio'],.03)
        self.assertEqual(value['functional_front'],'unknown_not_inferred_from_boundary_coverage')
        self.assertEqual(value['support_surfaces'][0]['id'],'top')
        self.assertEqual(parts,original)

    def test_overlapping_face_projections_use_union_not_double_count(self):
        parts=[dict(id=str(i),center=[0,-.24,.5],size=[1,.02,1]) for i in range(3)]
        value=describe(parts,[1,.5,1])
        self.assertEqual(next(f for f in value['side_faces'] if f['local_face']=='y-')['covered_area_ratio'],1)

    def test_all_128_compiler_allowed_expanded_parts_are_aggregated(self):
        parts=[dict(id=str(i),center=[0,-.24,.5],size=[1,.02,1]) for i in range(128)]
        value=describe(parts,[1,.5,1])
        self.assertEqual(value['part_count'],128)
        face=next(f for f in value['side_faces'] if f['local_face']=='y-')
        self.assertEqual(face['covered_area_ratio'],1)
        self.assertEqual(face['boundary_part_count'],128)
        self.assertEqual(len(face['largest_boundary_part_ids']),4)
        self.assertTrue(value['vertical_parts_truncated'])
        with self.assertRaises(ValueError):describe(parts+[parts[0]],[1,.5,1])

    def test_truncation_explicit_and_hash_bound_without_changing_recipe(self):
        parts=[dict(id='p'+str(i),center=[0,0,.5],size=[.01,.01,1],support_top=True) for i in range(32)]
        value=describe(parts,[1,.5,1])
        self.assertEqual(value['part_count'],32)
        self.assertEqual(len(value['major_vertical_parts']),8)
        self.assertTrue(value['vertical_parts_truncated'])
        self.assertEqual(len(value['support_surfaces']),12)
        self.assertTrue(value['support_surfaces_truncated'])
        digest=value.pop('evidence_sha256')
        self.assertEqual(digest,canonical_sha256(value))

    def test_discovery_and_actual_review_share_recipe_and_parameter_binding(self):
        recipe=compile_authoring(table());original=deepcopy(recipe)
        model=recipe_model_id(recipe)
        row=next(m for m in available_models({model:recipe}) if m['model_id']==model)
        defaults={p['name']:p['default'] for p in recipe['parameters']}
        args=dict(id='stand',recipe=recipe,parameters=defaults,center_m=[1,2],yaw_deg=90,
            recipe_sha256=row['recipe_sha256'])
        plan=dict(calls=[dict(tool='place_model_recipe',arguments=args)])
        actual=compiled_geometry(plan)['calls'][0]['assembly_geometry']
        self.assertEqual(actual['binding'],row['assembly_geometry']['binding'])
        self.assertEqual(actual['parameters'],recipe['parameters'])
        self.assertNotEqual(actual['evidence_sha256'],row['assembly_geometry']['evidence_sha256'])
        self.assertEqual(actual['yaw_deg'],90)
        self.assertEqual(recipe,original)
        context=repair_geometry_context(plan,['stand'])
        self.assertEqual(context['plan_sha256'],canonical_sha256(plan))
        self.assertEqual(context['target_calls'][0]['assembly_geometry'],actual)
        self.assertNotIn('parts',context['target_calls'][0]['arguments'].get('recipe',{}))
        changed=deepcopy(defaults);changed['width']*=1.5
        self.assertNotEqual(recipe_descriptor(recipe,changed)['evidence_sha256'],row['assembly_geometry']['evidence_sha256'])
        changed['width']=999
        with self.assertRaises(ModelRecipeError):recipe_descriptor(recipe,changed)

    def test_valid_repeated_recipe_with_128_parts_reaches_discovery_and_review(self):
        parameters=[dict(name=k,type='number',minimum=.3,maximum=2.,default=v)
            for k,v in [('width',1.),('depth',.5),('height',1.)]]
        parameters.append(dict(name='copies',type='integer',minimum=1,maximum=10,default=10))
        recipe=dict(schema_version=RECIPE_VERSION,interpreter_version=INTERPRETER_VERSION,
            title='Repeated solid contract fixture',family='common',kind='storage',parameters=parameters,
            parts=[dict(id='part'+str(i),center=[0,0,dict(op='mul',args=['height',.5])],
                size=['width','depth','height'],material='wood',support_top=False,
                repeat='copies' if i<12 else None) for i in range(20)])
        identity=recipe_model_id(recipe)
        selected=next(m for m in available_models({identity:recipe}) if m['model_id']==identity)
        self.assertEqual(selected['assembly_geometry']['part_count'],128)
        args=dict(id='repeated',recipe=recipe,parameters={p['name']:p['default'] for p in parameters},
            center_m=[0,0],yaw_deg=0)
        current=compiled_geometry(dict(calls=[dict(tool='place_model_recipe',arguments=args)]))
        self.assertEqual(current['calls'][0]['assembly_geometry']['part_count'],128)

    def test_export_isolation_and_builtin_axes_are_explicit(self):
        recipe=compile_authoring(table());model=recipe_model_id(recipe)
        rows=available_models({model:recipe})
        row=next(m for m in rows if m['model_id']==model)
        row['assembly_geometry']['parameters'][0]['maximum']=999
        self.assertNotEqual(recipe['parameters'][0]['maximum'],999)
        chair=next(m for m in rows if m['kind']=='chair')
        self.assertIn('X width',chair['assembly_geometry']['local_axes'])
        self.assertEqual(chair['assembly_geometry']['functional_front'],'unknown_not_inferred_from_boundary_coverage')


if __name__=='__main__':unittest.main()
