# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Boundary search regressions: same dimensions, margin and separation gap."""
import unittest
import test_budgeted_generation as f
from twinpulse_provider.packing_candidates import floor_candidates
from twinpulse_provider.photo_layout import _packing_separated
from twinpulse_provider.semantic_scene import compile_scene, checked_batch, scene_draft, checked_structure
from twinpulse_core.room_items import room_item_risk, expand_room_item
from twinpulse_core.room_visuals import display_meshes
from twinpulse_core.photo_placement import validate_placement_plan, PLACEMENT_VERSION
from twinpulse_core import SiteToolPlan, execute_site_tool_plan


class FloorCandidateTests(unittest.TestCase):
    def test_candidate_resource_budget_is_explicit_not_a_geometry_pass(self):
        with self.assertRaisesRegex(ValueError,'CANDIDATE_BUDGET_EXHAUSTED'):
            list(floor_candidates((-.1,.1,-.1,.1),6,6,'middle_centre',max_points=2))
    def test_contact_inside_narrow_non_grid_interval(self):
        bounds=(-.6,.6,-.3,.3); blocker=(-1.45,.25,-1.81,1.3)
        points=list(floor_candidates(bounds,3.2,4.,'middle_right',[('blocker',0.,0.,blocker)]))
        self.assertFalse(any(_packing_separated(bounds,x,y,blocker,0.,0.) for priority,x,y in points if priority==0))
        valid=[(x,y) for priority,x,y in points if priority==1 and _packing_separated(bounds,x,y,blocker,0.,0.)]
        self.assertTrue(valid)
        self.assertTrue(all(x<=.89 and x>=.88 for x,y in valid))

    def test_new_items_compile_store_safe_recipes_and_keep_covering_hazard(self):
        kinds=['floor_covering','wall_fixture','ceiling_fixture','wall_storage']
        prompt='Create a bed and '+', '.join(kinds)+' in a 6 by 6 metre room'
        inventory=f.structure()['inventory']+[dict(id=k,kind=k,source=dict(
            basis='user',observation_ids=[],user_quote=k)) for k in kinds]
        request=f.text_request(prompt)
        draft=scene_draft(checked_structure({**f.structure(),'inventory':inventory},request,f.empty_observation()))
        values=dict(bed=f.bed())
        for kind in kinds:
            relation='floor' if kind=='floor_covering' else 'ceiling' if kind=='ceiling_fixture' else 'wall'
            values[kind]=dict(region='middle_centre',yaw_deg=0,model_id='common.'+kind,
                dimensions_m=[1,.5,.02] if kind=='floor_covering' else [.4,.1,.4],
                variant='standard',finish='catalog_default',placement=dict(relation=relation,
                    parent_id=None if relation=='floor' else 'ceiling' if relation=='ceiling' else 'rear_wall',
                    part=None,anchor='centre',elevation_m=1.8 if relation=='wall' else None))
        draft=checked_batch(values,draft,list(values))
        plan,provenance=compile_scene(draft,f.empty_observation(),request)
        decoded=SiteToolPlan.from_dict(plan);execute_site_tool_plan(decoded,source='manual',source_ref='a'*64)
        validate_placement_plan(decoded,dict(schema_version=PLACEMENT_VERSION,
            relations=[dict(id=i,**v['placement']) for i,v in values.items()]))
        by_id={row['arguments']['id']:row['arguments'] for row in plan['calls']}
        rug=by_id['floor_covering'];self.assertEqual(room_item_risk(rug),'entanglement')
        self.assertTrue(any(row.id.endswith('_keepout') and row.collision for row in expand_room_item(rug)))
        for kind in kinds:
            self.assertEqual(by_id[kind]['catalog_version'],'room-items-1.1')
            self.assertTrue(display_meshes(kind,by_id[kind]['dimensions_m']))
            from copy import deepcopy
            bad=deepcopy(draft)
            bad['objects'][kind]['placement']=dict(relation='surface' if kind=='floor_covering' else 'floor',
                parent_id='bed' if kind=='floor_covering' else None,part='mattress' if kind=='floor_covering' else None,
                anchor='centre',elevation_m=None)
            with self.assertRaises(ValueError):compile_scene(bad,f.empty_observation(),request)
            contract=dict(schema_version=PLACEMENT_VERSION,relations=[dict(id=i,**v['placement']) for i,v in values.items()])
            relation=next(row for row in contract['relations'] if row['id']==kind)
            relation.update(bad['objects'][kind]['placement'])
            with self.assertRaises(ValueError):validate_placement_plan(decoded,contract)
        # No floor-standing furniture: the layer/attachment path must still compile.
        covering_only={**draft,'inventory':[row for row in draft['inventory'] if row['id']!='bed'],
            'objects':{key:value for key,value in draft['objects'].items() if key!='bed'}}
        plan,_=compile_scene(covering_only,f.empty_observation(),request)
        self.assertEqual(len([row for row in plan['calls'] if row['tool']=='place_room_item']),4)


if __name__=='__main__':unittest.main()
