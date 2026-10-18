# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic occupied assembly oracles; no photo IDs or target coordinates."""
from copy import deepcopy
from itertools import product
import math
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from test_photo_parametric import object_intent,intent,compile
from twinpulse_core import SiteToolPlan,execute_site_tool_plan,canonical_sha256
from twinpulse_core.photo_placement import placement_contract_from_trace,validate_placement_plan
from twinpulse_provider.photo_layout import (_floor_assembly_bounds,_floor_domain,_packing_separated,
    _bounded_region_repack,_checked_model_relations,PhotoLayoutPackingError)


def assembly(*anchors,yaw=0):
    parent=object_intent('support','bed',region='middle_centre',size=[1.1,1.7,.5])
    parent['yaw_deg']=yaw
    children=[object_intent('cloth_'+str(n),'bedding_overhang',parent='support',part='mattress',
        relation='drape',anchor=anchor,size=[.8,1.5,.12]) for n,anchor in enumerate(anchors)]
    return [parent,*children]


def bounds_for(rows):
    relations=_checked_model_relations(rows,2.6,{})
    return _floor_assembly_bounds(rows[0],rows,relations,parametric=True)


class SignedFloorAssemblyTests(unittest.TestCase):
    def test_one_sided_keepout_is_occupied_not_mirrored(self):
        rows=assembly('front');before=deepcopy(rows);bounds,diagnostic=bounds_for(rows)
        for actual,expected in zip(bounds,(-.55,.55,-1.66,.85)):self.assertAlmostEqual(actual,expected)
        self.assertAlmostEqual(diagnostic['occupied_size_m'][1],2.51)
        self.assertAlmostEqual(diagnostic['conservative_symmetric_footprint_m'][1],3.32)
        child=diagnostic['contributing_children'][0]
        self.assertEqual((child['id'],child['part'],child['anchor']),('cloth_0','mattress','front'))
        keepout=next(p for p in child['parts'] if p['synthetic_keepout'])
        self.assertAlmostEqual(keepout['local_xy_bounds_m'][3]-keepout['local_xy_bounds_m'][2],1.5+2*.10)
        self.assertEqual(rows,before);self.assertFalse(diagnostic['physical_authority'])

    def test_rotation_signed_bounds_enclose_every_derived_actual_part(self):
        for yaw in (0,90,-90,180):
            with self.subTest(yaw=yaw):
                rows=assembly('front',yaw=yaw);original=deepcopy(rows)
                value=intent(*rows,width=4,length=4);payload,trace=compile(value)
                plan=SiteToolPlan.from_dict(payload)
                validate_placement_plan(plan,placement_contract_from_trace(trace))
                scene=execute_site_tool_plan(plan,source='manual',source_ref=canonical_sha256(payload)).scene
                parent=next(c.arguments for c in plan.calls if c.arguments['id']=='support')
                x,y=parent['center_m'];bounds,_=bounds_for(rows)
                for obj in scene.objects:
                    if not obj.id.startswith(('support_','cloth_')):continue
                    dx,dy,_=obj.shape.dimensions_m;a=math.radians(obj.transform.rotation_rpy_deg[2])
                    hx=(abs(math.cos(a))*dx+abs(math.sin(a))*dy)/2
                    hy=(abs(math.sin(a))*dx+abs(math.cos(a))*dy)/2
                    ox,oy,_=obj.transform.position_m
                    self.assertGreaterEqual(ox-hx-x,bounds[0]-1e-9);self.assertLessEqual(ox+hx-x,bounds[1]+1e-9)
                    self.assertGreaterEqual(oy-hy-y,bounds[2]-1e-9);self.assertLessEqual(oy+hy-y,bounds[3]+1e-9)
                self.assertEqual(rows,original)

    def test_one_sided_greedy_fit_preserves_params_and_final_executor_checks(self):
        rows=assembly('front');rows[0]['region']='rear_centre'
        value=intent(*rows,width=2.8,length=3);before=deepcopy(value)
        payload,trace=compile(value);plan=SiteToolPlan.from_dict(payload)
        validate_placement_plan(plan,placement_contract_from_trace(trace))
        execute_site_tool_plan(plan,source='manual',source_ref=canonical_sha256(payload))
        self.assertEqual(value,before);self.assertNotIn('bounded_packing_search',trace)
        report=trace['floor_assemblies'][0]
        self.assertEqual(report['empty_floor_axes'],[])
        self.assertEqual(report['floor_margin_m'],.11);self.assertEqual(report['assembly_gap_m'],.03)
        self.assertEqual({c.arguments['id'] for c in plan.calls if c.tool.startswith('place_')},{'support','cloth_0'})

    def test_same_signed_bounds_are_used_by_bounded_fallback(self):
        rows=assembly('front');parent=rows[0];parent['region']='rear_centre';bounds,_=bounds_for(rows)
        sx,sy=bounds[1]-bounds[0],bounds[3]-bounds[2]
        signed,report=_bounded_region_repack([parent],lambda _:(sx,sy),2.8,3,local_bounds=lambda _:bounds)
        self.assertEqual(report['termination_code'],'FOUND');self.assertIsNotNone(signed)
        _,mirror=_bounded_region_repack([parent],lambda _:(sx,2*max(abs(bounds[2]),abs(bounds[3]))),2.8,3)
        self.assertEqual(mirror['termination_code'],'EMPTY_DOMAIN')
        domain=_floor_domain(bounds,2.8,3);x,y=signed['support']
        self.assertTrue(domain[0]<=x<=domain[1] and domain[2]<=y<=domain[3])

    def test_two_sided_children_and_actual_blocked_floor_remain_failures(self):
        rows=assembly('front','rear');bounds,_=bounds_for(rows)
        self.assertAlmostEqual(bounds[2],-bounds[3])
        value=intent(*rows,width=2.8,length=3);before=deepcopy(value)
        with self.assertRaises(PhotoLayoutPackingError) as caught:compile(value)
        report=caught.exception.packing_report
        self.assertEqual(report['failed_assembly']['empty_floor_axes'],['y'])
        self.assertEqual({c['id'] for c in report['failed_assembly']['contributing_children']},{'cloth_0','cloth_1'})
        self.assertEqual(report['bounded_search']['termination_code'],'EMPTY_DOMAIN')
        self.assertFalse(report['bounded_search']['global_infeasibility_proved']);self.assertEqual(value,before)
        two=assembly('front');other=object_intent('other','bed',size=[1.1,1.7,.5])
        with self.assertRaises(PhotoLayoutPackingError):compile(intent(*two,other,width=2,length=3))

    def test_signed_gap_matches_independent_interval_oracle(self):
        a=(-.4,.7,-.9,.5);b=(-.3,.2,-.2,.6)
        for x,y in product((-.8,0,.8),repeat=2):
            for px,py in product((-.8,0,.8),repeat=2):
                oracle=any((pmax+.03<=qmin or qmax+.03<=pmin) for pmin,pmax,qmin,qmax in
                    ((x+a[0],x+a[1],px+b[0],px+b[1]),(y+a[2],y+a[3],py+b[2],py+b[3])))
                self.assertEqual(_packing_separated(a,x,y,b,px,py),oracle)
        self.assertFalse(_packing_separated(a,0,0,b,1.029,0))
        self.assertTrue(_packing_separated(a,0,0,b,1.031,0))

    def test_existing_symmetric_grid_results_and_budget_are_identical(self):
        rows=[dict(id='a',region='middle_centre'),dict(id='b',region='middle_centre')]
        for room in (1.4,2.4):
            before,old=_bounded_region_repack(rows,lambda _:(.9,.9),room,room,branch_cap=1000)
            after,new=_bounded_region_repack(rows,lambda _:(.9,.9),room,room,branch_cap=1000,
                local_bounds=lambda _:(-.45,.45,-.45,.45))
            self.assertEqual(before,after)
            for key in ('termination_code','nodes','domain_counts','candidate_checks','overlap_pruned','branches_truncated'):
                self.assertEqual(old[key],new[key])
        for kwargs in ({'max_nodes':0},{'max_nodes':1}):
            found,report=_bounded_region_repack(rows,lambda _:(.9,.9),2.4,2.4,
                local_bounds=lambda _:(-.45,.45,-.45,.45),**kwargs)
            self.assertIsNone(found);self.assertEqual(report['termination_code'],'NODE_BUDGET_EXHAUSTED')

    def test_invalid_bounds_and_attachment_geometry_are_not_forgiven(self):
        row=[dict(id='a',region='middle_centre')]
        for bounds in ((0,0,-1,1),(-1,1,float('nan'),1),(-1,1,-1)):
            with self.assertRaisesRegex(ValueError,'PACKING_BOUNDS_INVALID'):
                _bounded_region_repack(row,lambda _:(1,1),4,4,local_bounds=lambda _:bounds)
        rows=assembly('front');rows[1]['dimensions_m'][2]=1.
        from twinpulse_core.geometry_diagnostics import GeometryValidationError
        with self.assertRaises(GeometryValidationError):compile(intent(*rows,width=4,length=4))

    def test_typed_child_domain_diagnosis_survives_semantic_repair_context(self):
        from test_budgeted_generation import text_request,empty_observation
        from twinpulse_provider.semantic_scene import checked_structure,scene_draft,checked_batch,compile_scene,geometry_repair_context
        rows=assembly('front','rear');request=text_request('Create an estimated bedroom with a bed and two draped bedding objects')
        structure=dict(summary='Synthetic estimated assembly',room=dict(width_m=2.8,length_m=3,height_m=2.6),
            inventory=[dict(id=row['id'],kind=row['kind'],evidence_ref='text:0') for row in rows])
        candidate=scene_draft(checked_structure(structure,request,empty_observation(),bound=True))
        params={row['id']:{k:v for k,v in row.items() if k not in {'id','kind','observation_ids'}} for row in rows}
        candidate=checked_batch(params,candidate,list(params));before=deepcopy(candidate)
        with self.assertRaises(PhotoLayoutPackingError) as caught:compile_scene(candidate,empty_observation(),request)
        diagnosis=json.loads(json.dumps(caught.exception.contract_report))
        detail=diagnosis['issues'][0]['actual']['packing']['failed_assembly']
        self.assertEqual(detail['parent_id'],'support');self.assertEqual(detail['parent_dimensions_m'],[1.1,1.7,.5])
        self.assertEqual(detail['empty_floor_axes'],['y'])
        self.assertEqual({row['id'] for row in detail['contributing_children']},{'cloth_0','cloth_1'})
        scope=geometry_repair_context(candidate,diagnosis)
        self.assertEqual({row['id'] for row in scope['targets']},{'support','cloth_0','cloth_1'})
        self.assertEqual(candidate,before);self.assertFalse(detail['physical_authority'])


if __name__=='__main__':unittest.main()
