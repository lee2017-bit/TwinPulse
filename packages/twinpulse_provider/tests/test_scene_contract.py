# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic source/scene repair contracts; fixtures are not real model accuracy."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import unittest

from twinpulse_core import SiteToolPlan, canonical_sha256, execute_site_tool_plan
from twinpulse_provider import GenerationRequest, GenerationService, InvalidProviderResponseError
from twinpulse_provider.nebius_pipeline import ObservationArtifact, observation_json_schema, NebiusChatCompletionsPipelineProvider
from twinpulse_provider.photo_layout import compile_layout, build_layout_body
from twinpulse_provider.schema import site_proposal_json_schema, site_tool_plan_json_schema
from twinpulse_provider.scene_contract import (GROUNDING_REVISION, PROPOSAL_REVISION,
    SceneContractError, ground_layout, lower_proposal, preflight_site, preflight_legacy_layout, review_photo_relations)
from test_photo_layout import request
from test_photo_parametric import object_intent, intent
from test_nebius_pipeline import ScriptedTransport, completion, config, OBSERVER_MODEL, PLANNER_MODEL


def observed(*rows, relations=()):
    return ObservationArtifact.from_mapping(dict(schema_version='1.1',summary='Synthetic unmeasured observation.',
        entities=[dict(id=identity,kind='static_obstacle',description=category,confidence=.9,
            role=role,category=category,region=region,spatial_confidence=confidence)
            for identity,category,role,region,confidence in rows],
        relations=list(relations),dimensions=[],ambiguities=['Scale unmeasured']))


def bed_observation(confidence=.9):
    return observed(('seen_bed','bed','object','middle_right',confidence))


def grounded(*items,width=6,length=6):
    value=intent(*items,width=width,length=length)
    value['layout_version']=GROUNDING_REVISION
    for item in value['objects']:
        refs=item.pop('observation_ids')
        item['source']=dict(basis='visual',observation_ids=refs,user_quote=None)
    return value


def bed_layout():
    value=grounded(object_intent('bed','bed','middle_right'),width=4,length=5)
    value['objects'][0]['source']['observation_ids']=['seen_bed']
    return value


def proposal(plan, quote=None):
    calls=deepcopy(plan['calls']);evidence=deepcopy(plan['call_evidence'])
    for e in evidence:e['user_quote']=quote if e['basis']=='user' else None
    floor=next(c for c in calls if c['tool']=='create_floor')
    floor_evidence=next(e for e in evidence if e['call_id']==floor['call_id'])
    return {**{k:deepcopy(plan[k]) for k in ('plan_version','scene_id','summary','image_observations')},
        'proposal_version':PROPOSAL_REVISION,'coordinate_frame':'photo_view_right_rear',
        'floor_call':floor,'floor_evidence':floor_evidence,
        'scene_calls':[c for c in calls if c is not floor],
        'call_evidence':[e for e in evidence if e is not floor_evidence]}


class SceneContractTests(unittest.TestCase):
    def test_observer_semantic_wire_is_additive_and_strict(self):
        self.assertEqual(observation_json_schema()['properties']['schema_version'],{'const':'1.0'})
        schema=observation_json_schema('1.1')['properties']['entities']['items']
        self.assertIn('category',schema['required']);self.assertIn('spatial_confidence',schema['required'])
        self.assertEqual(bed_observation().schema_version,'1.1')
        bad=bed_observation().to_dict();bad['entities'][0]['role']='structure'
        with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(bad)
        for role in ('free_space','robot'):
            bad=bed_observation().to_dict();bad['entities'][0]['role']=role
            with self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(bad)

    def test_visual_source_compiles_without_mutating_source(self):
        value=bed_layout();before=deepcopy(value)
        plan,trace=compile_layout(value,bed_observation(),request(),None)
        self.assertEqual(value,before);self.assertEqual(trace['contract'],GROUNDING_REVISION)
        self.assertEqual(trace['grounding']['source_layout_sha256'],canonical_sha256(value))
        self.assertEqual(next(e for e in plan['call_evidence'] if e['call_id']=='obj_bed')['basis'],'visual')
        execute_site_tool_plan(SiteToolPlan.from_dict(plan),source='photo',source_ref=canonical_sha256(value))

    def test_user_only_object_exact_quote_and_no_visual_reference(self):
        value=bed_layout();desk=grounded(object_intent('desk','desk','rear_left'))['objects'][0]
        desk['source']=dict(basis='user',observation_ids=[],user_quote='add a desk')
        value['objects'].append(desk)
        plan,_=compile_layout(value,bed_observation(),request('A bedroom; add a desk.'),None)
        self.assertEqual(next(e for e in plan['call_evidence'] if e['call_id']=='obj_desk')['basis'],'user')
        for invalid in ('invent a desk','',None):
            bad=deepcopy(value);bad['objects'][1]['source']['user_quote']=invalid
            with self.subTest(quote=invalid),self.assertRaisesRegex(SceneContractError,'USER_SOURCE_QUOTE_NOT_IN_REQUEST'):
                ground_layout(bad,bed_observation(),request('add a desk'))

    def test_inferred_source_stays_inferred_after_lowering(self):
        value=bed_layout();value['objects'][0]['source']['basis']='inferred'
        plan,_=compile_layout(value,bed_observation(),request(),None)
        self.assertEqual(next(e for e in plan['call_evidence'] if e['call_id']=='obj_bed')['basis'],'inferred')

    def test_wrong_category_and_non_object_roles_are_rejected(self):
        for category,role,code in [('desk','object','SOURCE_OBJECT_CATEGORY_MISMATCH'),
                ('floor','structure','SCENE_ROLE_IS_NOT_OBJECT'),('opening','opening','SCENE_ROLE_IS_NOT_OBJECT'),
                ('aisle','free_space','SCENE_ROLE_IS_NOT_OBJECT')]:
            obs=observed(('seen_bed',category,role,'unknown',.5))
            with self.subTest(role=role),self.assertRaisesRegex(SceneContractError,code):
                ground_layout(bed_layout(),obs,request())

    def test_unknown_visual_identity_requires_inference(self):
        obs=observed(('seen_bed','unknown','unknown','unknown',.2))
        with self.assertRaisesRegex(SceneContractError,'UNKNOWN_OBSERVATION_REQUIRES_INFERRED_BASIS'):
            ground_layout(bed_layout(),obs,request())
        value=bed_layout();value['objects'][0]['source']['basis']='inferred'
        ground_layout(value,obs,request())

    def test_independent_errors_are_aggregated_and_dependent_checks_blocked(self):
        value=bed_layout();value['objects'][0]['source']['observation_ids']=[]
        extra=deepcopy(value['objects'][0]);extra['id']='other';value['objects'].append(extra)
        with self.assertRaises(SceneContractError) as caught:ground_layout(value,bed_observation(),request())
        report=caught.exception.contract_report
        self.assertEqual(sum(e['code']=='PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE' for e in report['issues']),2)
        self.assertIn('packing',report['blocked_checks']);self.assertFalse(report['physical_authority'])
        self.assertIn('PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING',[e['code'] for e in report['issues']])

    def test_unmeasured_room_can_change_and_raw_candidate_stays_immutable(self):
        for width,length in ((10,12),(4,5)):
            value=bed_layout();value['room'].update(width_m=width,length_m=length);before=deepcopy(value)
            plan,_=compile_layout(value,bed_observation(),request('Unmeasured bedroom'),None)
            self.assertEqual(plan['calls'][0]['arguments']['size_m'],[float(width),float(length)])
            self.assertEqual(value,before)

    def test_floor_is_mandatory_wire_slot_without_mandatory_robot_or_task(self):
        stored=site_tool_plan_json_schema('2.2');before=deepcopy(stored)
        for photo in (True,False):
            schema=site_proposal_json_schema(photo=photo)
            self.assertIn('floor_call',schema['required']);self.assertNotIn('calls',schema['properties'])
            allowed=schema['properties']['scene_calls']['items']['anyOf']
            self.assertTrue(all(c['properties']['tool'].get('const',c['properties']['tool'].get('enum')) not in
                ('create_floor',['create_floor']) for c in allowed))
            self.assertNotIn('agv_call',schema['required']);self.assertEqual(schema['properties']['scene_calls']['minItems'],0)
        self.assertEqual(stored,before)

    def test_proposal_lowering_preserves_storage_format_and_original_hash(self):
        plan,_=compile_layout(bed_layout(),bed_observation(),request(),None)
        wire=proposal(plan,'4 by 5 metres');before=deepcopy(wire)
        lowered,trace=lower_proposal(wire)
        self.assertEqual(lowered,plan);self.assertEqual(wire,before)
        self.assertEqual(trace['proposal_sha256'],canonical_sha256(wire))
        self.assertEqual(preflight_site(lowered,bed_observation(),request(),trace)['issues'],[])

    def test_missing_floor_never_gets_silently_inserted(self):
        plan,_=compile_layout(bed_layout(),bed_observation(),request(),None)
        plan['calls']=plan['calls'][1:];before=deepcopy(plan)
        lowered,trace=lower_proposal(plan);self.assertIsNone(trace)
        check=preflight_site(lowered,bed_observation(),request())
        self.assertIn('REQUIRED_TOOL_COUNT',[e['code'] for e in check['issues']])
        self.assertIn('bounds',check['blocked_checks']);self.assertEqual(plan,before)

    def test_relative_order_and_region_contradictions_but_low_confidence_unverified(self):
        obs=observed(('seen_bed','bed','object','middle_right',.9),('seen_desk','desk','object','rear_left',.9),
            relations=[dict(subject_id='seen_bed',relation='right_of',object_id='seen_desk')])
        value=bed_layout();desk=grounded(object_intent('desk','desk','rear_left'))['objects'][0]
        desk['source']['observation_ids']=['seen_desk'];value['objects'].append(desk)
        plan,_=compile_layout(value,obs,request(),None)
        self.assertEqual(review_photo_relations(plan,obs,'photo_view_right_rear')['issues'],[])
        for c in plan['calls']:
            if c['call_id']=='obj_bed':c['arguments']['center_m'][0]=-2
            if c['call_id']=='obj_desk':c['arguments']['center_m'][0]=2
        check=review_photo_relations(plan,obs,'photo_view_right_rear')
        self.assertIn('PHOTO_RELATIVE_ORDER_CONTRADICTION',[e['code'] for e in check['issues']])
        self.assertIn('PHOTO_OBSERVED_REGION_CONTRADICTION',[e['code'] for e in check['issues']])
        low=obs.to_dict()
        for e in low['entities']:e['spatial_confidence']=.5
        check=review_photo_relations(plan,ObservationArtifact.from_mapping(low),'photo_view_right_rear')
        self.assertEqual(check['status'],'UNVERIFIED');self.assertEqual(check['metric_scale_validation'],'UNVERIFIED')
        self.assertEqual(review_photo_relations(plan,obs,'local_xy')['status'],'UNVERIFIED')

    def test_malformed_sources_and_call_ids_have_structured_errors(self):
        value=bed_layout();value['objects'][0]['source']['basis']={}
        with self.assertRaisesRegex(SceneContractError,'SOURCE_SHAPE_INVALID'):ground_layout(value,bed_observation(),request())
        check=preflight_site({'calls':[{'tool':{},'call_id':[]}],'call_evidence':[]},bed_observation(),request())
        self.assertIn('SITE_CALL_SHAPE_INVALID',[e['code'] for e in check['issues']])
        for key in ('schema_version','role','category','kind','region'):
            obs=bed_observation().to_dict()
            if key=='schema_version':obs[key]=[]
            else:obs['entities'][0][key]={}
            with self.subTest(key=key),self.assertRaises(InvalidProviderResponseError):ObservationArtifact.from_mapping(obs)

    def test_photo_cannot_bypass_ordering_checks_by_claiming_text_frame(self):
        plan,_=compile_layout(bed_layout(),bed_observation(),request(),None)
        wire=proposal(plan,'4 by 5 metres');wire['coordinate_frame']='local_xy'
        lowered,trace=lower_proposal(wire)
        checked=preflight_site(lowered,bed_observation(),request(),trace)
        self.assertIn('SCENE_COORDINATE_FRAME_INVALID',[e['code'] for e in checked['issues']])

    def test_public_diagnostics_never_expose_quotes_or_arbitrary_issue_payload(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        check=_public_generation_diagnostics(dict(validation_code='REPAIR_NO_PROGRESS',repair_no_progress=True,
            scene_contract=dict(issues=[dict(code='USER_SOURCE_QUOTE_NOT_IN_REQUEST',path='$.objects[0].source',
                user_quote='private',response='secret')],blocked_checks=['packing','private'],token='secret')))
        self.assertEqual(check['scene_contract']['issues'],[dict(code='USER_SOURCE_QUOTE_NOT_IN_REQUEST',path='$.objects[0].source')])
        self.assertTrue(check['repair_no_progress']);self.assertNotIn('secret',json.dumps(check))

    def test_saved_failure_responses_remain_rejected_and_immutable(self):
        root=Path(__file__).resolve().parents[3]/'artifacts/pre-demo-20261008'
        cases=[('photo-general-add10-r1','c2c23c006cf04cfa90f13a438be30a89','8f7548f3ff5a4ddf9f2abf579085d6ae'),
            ('photo-general-add10-r2-direct','f7347f7cd5534c56813fd66fa740504b','d125006aa4b74dcb97a3bbcb574eefb6'),
            ('photo-general-add10-r3','2321e52dc860496fb372f55b9f8c5787','f43bc812a47f4fd99fa5ec4f9d0739e0')]
        for folder,plan_id,obs_id in cases:
            files=[root/folder/'runtime/provider-evidence'/f'{i}.json' for i in (plan_id,obs_id)]
            if not all(p.exists() for p in files):self.skipTest('Saved local failure evidence absent')
            import hashlib
            hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
            def content(p):
                response=json.loads(p.read_text(encoding='utf-8'))['response_redacted']
                if isinstance(response,str):response=json.loads(response)
                return json.loads(response['choices'][0]['message']['content'])
            plan=content(files[0]);obs=ObservationArtifact.from_mapping(content(files[1]))
            check=preflight_site(plan,obs,request()) if 'direct' in folder else preflight_legacy_layout(plan,obs)
            self.assertGreater(len(check['issues']),1)
            self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in files])


class RepairContractTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self,transport,compact=True):
        return NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=compact)

    async def test_one_repair_uses_all_errors_and_same_new_wire(self):
        bad=bed_layout();bad['objects'][0]['source']['observation_ids']=[]
        good=bed_layout();before=deepcopy(bad)
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,bed_observation().to_dict()),
            completion('bad',PLANNER_MODEL,bad),completion('good',PLANNER_MODEL,good))
        result=await GenerationService(self.adapter(transport),config(timeout_s=20),plan_version='2.2').generate(request())
        feedback=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertGreater(len(feedback['scene_contract']['issues']),1)
        self.assertEqual(transport.bodies[-1]['response_format'],transport.bodies[-2]['response_format'])
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1);self.assertEqual(bad,before)

    async def test_semantic_no_op_repair_is_recorded_without_further_retry(self):
        bad=bed_layout();bad['objects'][0]['source']['observation_ids']=[]
        repeat=completion('repeat',PLANNER_MODEL,bad)
        from dataclasses import replace
        repeat=replace(repeat,content=json.dumps(bad,indent=3))
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,bed_observation().to_dict()),completion('bad',PLANNER_MODEL,bad),repeat)
        with self.assertRaises(InvalidProviderResponseError) as caught:
            await GenerationService(self.adapter(transport),config(timeout_s=20),plan_version='2.2').generate(request())
        diagnostic=caught.exception.diagnostics
        self.assertTrue(diagnostic['repair_no_progress']);self.assertEqual(len(transport.bodies),3)
        self.assertIn('REPAIR_NO_PROGRESS',[i['code'] for i in diagnostic['scene_contract']['issues']])
        self.assertEqual(diagnostic['attempts'][-1]['candidate_sha256'],diagnostic['attempts'][-2]['candidate_sha256'])

    async def test_direct_missing_floor_repair_uses_required_slot_and_succeeds(self):
        plan,_=compile_layout(bed_layout(),bed_observation(),request(),None)
        bad=deepcopy(plan);bad['calls']=bad['calls'][1:]
        good=proposal(plan,'4 by 5 metres')
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,bed_observation().to_dict()),
            completion('bad',PLANNER_MODEL,bad),completion('good',PLANNER_MODEL,good))
        result=await GenerationService(self.adapter(transport,False),config(timeout_s=20),plan_version='2.2').generate(request())
        self.assertEqual(result.plan.plan_version,'2.2');self.assertEqual(len(transport.bodies),3)
        self.assertIn('site_proposal',result.provider_provenance)

    async def test_high_confidence_wrong_region_can_be_repaired(self):
        bad=bed_layout();bad['objects'][0]['region']='middle_left'
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,bed_observation().to_dict()),
            completion('bad',PLANNER_MODEL,bad),completion('good',PLANNER_MODEL,bed_layout()))
        result=await GenerationService(self.adapter(transport),config(timeout_s=20),plan_version='2.2').generate(request())
        feedback=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertIn('PHOTO_OBSERVED_REGION_CONTRADICTION',[e['code'] for e in feedback['scene_contract']['issues']])
        self.assertEqual(result.provider_provenance['observed_photo_relations']['issues'],[])


if __name__=='__main__':unittest.main()
