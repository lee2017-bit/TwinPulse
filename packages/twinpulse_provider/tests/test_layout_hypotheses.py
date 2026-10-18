# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit offline fixtures; never photo-fidelity or physical evidence."""
import asyncio
from copy import deepcopy
import unittest

import test_render_review_loop as fixtures
from twinpulse_provider.render_review import body,checked,compiled_geometry
from twinpulse_provider.semantic_scene import compile_scene,revision,geometry_repair_context
from twinpulse_provider.repair_scope import delta_schema,checked_scope
from twinpulse_provider.scene_contract import SceneContractError


class LayoutHypothesisTests(unittest.TestCase):
    def test_hypothesis_does_not_unlock_unrelated_packing_neighbors(self):
        from twinpulse_core import canonical_sha256
        from twinpulse_provider.repair_scope import scope_options
        _,_,_,_,_,draft=fixtures.case();draft=deepcopy(draft)
        template=deepcopy(draft['inventory'][0]);params=deepcopy(next(iter(draft['objects'].values())))
        draft['inventory']=[];draft['objects']={}
        for identity,region in (('hard','front_left'),('hyp','rear_right'),('neighbor','middle_right')):
            draft['inventory'].append({**deepcopy(template),'id':identity})
            draft['objects'][identity]={**deepcopy(params),'region':region,'placement':dict(
                relation='floor',parent_id=None,part=None,anchor='centre',elevation_m=None)}
        capture=dict(plan_sha256='a'*64,candidate_revision=revision(draft))
        diagnosis=dict(status='needs_revision',issues=[dict(code='PHOTO_LAYOUT_OVERLAP',target_ids=['hard'])],
            render_comparison='reviewed',candidate_revision=revision(draft),plan_sha256='a'*64,
            capture=capture,frame_key=canonical_sha256(capture),assessments={'hyp':{'layout':dict(status='contradiction',confidence=.55)}})
        context,options=scope_options(draft,diagnosis)
        self.assertEqual(context['hypothesis_only_ids'],['hyp'])
        self.assertNotIn('neighbor',{r['id'] for r in options})
        changed={**draft['objects']['neighbor'],'yaw_deg':90}
        with self.assertRaises(SceneContractError):checked_scope(draft,
            {'operations':[dict(op='update',id='neighbor',value=changed)]},diagnosis)

    def test_manifest_uses_compiled_axis_and_footprint_not_region(self):
        plan={'calls':[{'tool':'place_furniture','arguments':dict(id='desk',center_m=[1,2],
            dimensions_m=[2,1,.8],yaw_deg=90)}, {'tool':'place_room_item','arguments':dict(
            id='square',position_m=[0,0,.1],dimensions_m=[1,1,.2],yaw_deg=0)}]}
        manifest=compiled_geometry(plan)
        self.assertEqual(manifest['calls'][0]['horizontal_long_axis_xy'],[0,1])
        self.assertEqual(manifest['calls'][0]['world_footprint_xy_m'][0],[1.5,1.0])
        self.assertIsNone(manifest['calls'][1]['horizontal_long_axis_xy'])
        self.assertNotIn('recipe',str(manifest))

    def test_uncertain_hypothesis_never_becomes_issue_or_self_starts_repair(self):
        request,port,obs,_,_,draft=fixtures.case()
        plan,_=compile_scene(draft,obs,request)
        capture=asyncio.run(port.capture(plan,revision(draft),None,300));capture['plan']=plan
        wire=body(request,draft,obs,capture,model='fixture',cap=4000)
        response=fixtures.review_response(wire)
        response['objects']['bed']['layout'].update(status='contradiction',confidence=.55)
        result=checked(response,draft,plan,capture,dict(issues=[]))
        self.assertEqual(result['status'],'uncertain');self.assertEqual(result['issues'],[])
        self.assertEqual(result['layout_hypotheses'][0]['target_id'],'bed')
        self.assertFalse(result['layout_hypotheses'][0]['verified'])

    def test_bound_hypothesis_scope_restricts_fields_and_rejects_stale_capture(self):
        request,port,obs,_,_,draft=fixtures.case()
        plan,_=compile_scene(draft,obs,request)
        capture=asyncio.run(port.capture(plan,revision(draft),None,300));capture['plan']=plan
        wire=body(request,draft,obs,capture,model='fixture',cap=4000)
        response=fixtures.review_response(wire)
        ids=list(response['objects']);other=next(i for i in ids if i!='bed')
        response['objects']['bed']['layout'].update(status='contradiction',confidence=.55)
        result=checked(response,draft,plan,capture,dict(issues=[dict(code='EXPLICIT_FIXTURE',target_ids=[other])]))
        context=geometry_repair_context(draft,result)
        self.assertIn('bed',context['hypothesis_only_ids'])
        slot=delta_schema(draft,result)['properties']['changes']['properties']['bed']['anyOf'][1]
        self.assertEqual(set(slot['properties']),{'region','yaw_deg','placement'})
        changed=deepcopy(draft['objects']['bed']);changed['dimensions_m'][0]+=.1
        with self.assertRaises(SceneContractError):checked_scope(draft,dict(operations=[dict(op='update',id='bed',value=changed)]),result)
        changed=deepcopy(draft['objects']['bed']);changed['yaw_deg']=90
        checked_scope(draft,dict(operations=[dict(op='update',id='bed',value=changed)]),result)
        stale=deepcopy(result);stale['capture']['plan_sha256']='0'*64
        self.assertEqual(geometry_repair_context(draft,stale)['hypothesis_only_ids'],[])
        self.assertEqual(result['issues'][0]['code'],'EXPLICIT_FIXTURE')


if __name__=='__main__':unittest.main()
