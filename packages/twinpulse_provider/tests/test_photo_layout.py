# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Opt-in compact intent contracts. Fixture tests are not photo/Isaac acceptance."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import unittest

PACKAGES=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(PACKAGES/package/'src'))

from twinpulse_core import SiteToolPlan, execute_site_tool_plan, canonical_sha256
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
from twinpulse_provider import GenerationRequest, ImageInput, CancellationToken
from twinpulse_provider.photo_layout import REVISION, LEGACY_REVISION, compile_layout, requested_size, layout_schema
from twinpulse_provider.nebius_pipeline import ObservationArtifact, NebiusChatCompletionsPipelineProvider
from twinpulse_provider.service import GenerationService
from test_nebius_pipeline import ScriptedTransport, completion, config, OBSERVER_MODEL, PLANNER_MODEL


def observation():
    return ObservationArtifact.from_mapping(dict(schema_version='1.0',summary='Unmeasured bedroom.',
        entities=[dict(id='bed_visual',kind='static_obstacle',description='Bed on right',confidence=.8)],
        relations=[],dimensions=[],ambiguities=['Scale is unknown']))


def layout():
    return dict(layout_version=REVISION,summary='Approximate room; no measured geometry.',
        room=dict(width_m=4,length_m=5,height_m=2.5),objects=[dict(id='bed',kind='bed',
            region='middle_right',yaw_deg=0,observation_ids=['bed_visual'])])


def request(prompt='Create an approximate bedroom, 4 by 5 metres.'):
    return GenerationRequest('compact-test',prompt,(ImageInput('room.jpg','image/jpeg',b'fixture'),))


class PhotoLayoutTests(unittest.TestCase):
    def test_explicit_output_cap_reaches_observer_compact_and_single_repair(self):
        from twinpulse_provider import ProviderConfigurationError
        for invalid in (0,10001,True,'10000'):
            with self.assertRaises(ProviderConfigurationError):
                NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
                    planner_model_id=PLANNER_MODEL,output_token_cap=invalid)
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('invalid',PLANNER_MODEL,{}),completion('fixed',PLANNER_MODEL,layout()))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,
            compact_photo_layout=True,output_token_cap=10000)
        asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(request()))
        self.assertEqual([b['max_tokens'] for b in transport.bodies],[10000,10000,10000])
        self.assertEqual(provider.diagnostic_for('compact-test')['repair_count'],1)
        default=NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2')
        self.assertEqual(default.build_observer_body(request())['max_tokens'],4000)
        self.assertEqual(default.build_planner_body(request(),observation())['max_tokens'],8000)
        self.assertEqual(provider.build_planner_body(request(),observation())['max_tokens'],10000)

    def test_literal_reviewed_label_directions_are_mandatory_not_observer_aliases(self):
        from twinpulse_provider.photo_layout import reviewed_region_choices, build_layout_body
        reference=photo_reference(PHOTO_SHA256)
        original=copy.deepcopy(reference)
        choices=reviewed_region_choices(reference,None)
        self.assertEqual(set(choices),{'floor_bags','boxes'})
        self.assertEqual(choices['floor_bags'],['front_left','middle_left','rear_left'])
        self.assertEqual(reference,original)
        body=build_layout_body(request(),observation(),PLANNER_MODEL,reference)
        payload=json.loads(body['messages'][1]['content'])
        self.assertEqual(payload['reviewed_label_region_choices'],choices)
        schema=body['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['objects']['properties']['boxes']['properties']['region']['enum'],choices['boxes'])
        value=dict(layout_version=REVISION,summary='Estimated only',
            room=dict(width_m=8,length_m=8,height_m=2.5),objects={i['id']:
                dict(region='rear_right',yaw_deg=0,observation_ids=[]) for i in reference['items']})
        with self.assertRaisesRegex(ValueError,'PHOTO_LAYOUT_REVIEWED_POSITION_INVALID'):
            compile_layout(value,observation(),request('Create a bedroom'),reference)

    def test_conflicting_reviewed_label_directions_do_not_silently_override(self):
        from twinpulse_provider.photo_layout import reviewed_region_choices
        reference=photo_reference(PHOTO_SHA256)
        reference['items'][0]['label']='Object along the left and right edge'
        with self.assertRaisesRegex(ValueError,'LABEL_DIRECTION_CONFLICT'):
            reviewed_region_choices(reference,None)
        self.assertEqual(reviewed_region_choices(None,None),{})

    def test_packing_failure_has_exact_inventory_and_bounded_synthetic_slot_diagnostics(self):
        from twinpulse_provider.photo_layout import PhotoLayoutPackingError
        value=layout();value['room'].update(width_m=2,length_m=2)
        value['objects']=[dict(id='bed'+str(n),kind='bed',region='front_left',yaw_deg=0,
            observation_ids=['bed_visual']) for n in range(3)]
        original=copy.deepcopy(value)
        with self.assertRaises(PhotoLayoutPackingError) as caught:
            compile_layout(value,observation(),request('Create a room 2 by 2 metres'),None)
        report=caught.exception.packing_report
        self.assertEqual(value,original)
        self.assertEqual(report['room_size_m'],[2,2])
        self.assertEqual(report['region_counts']['front_left'],3)
        self.assertEqual(len(report['inventory_regions']),3)
        self.assertEqual(report['remaining_ids'],['bed0','bed1','bed2'])
        self.assertEqual(report['unplaced_ids'],['bed0','bed1','bed2'])
        self.assertEqual(len(report['packing_failures']),3)
        self.assertTrue(report['floor_must_not_expand'])
        self.assertEqual(len(report['failed_item_alternative_region_slot_counts']),9)
        self.assertTrue(all(type(n) is int and n>=0 for n in report['failed_item_alternative_region_slot_counts'].values()))

    def test_packing_feedback_reaches_the_same_single_repair_without_silent_success(self):
        value=layout();value['room'].update(width_m=2,length_m=2)
        value['objects']=[dict(id='bed'+str(n),kind='bed',region='front_left',yaw_deg=0,
            observation_ids=['bed_visual']) for n in range(3)]
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,value),completion('still_bad',PLANNER_MODEL,value))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',compact_photo_layout=True,max_repairs=1)
        from twinpulse_provider import InvalidProviderResponseError
        with self.assertRaisesRegex(InvalidProviderResponseError,'REGION_FULL'):
            asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(
                request('Create a room 2 by 2 metres')))
        feedback=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertEqual(feedback['layout_packing']['region_counts']['front_left'],3)
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        self.assertEqual(provider.diagnostic_for('compact-test')['repair_count'],1)
        self.assertEqual(len(transport.bodies),3)

    def test_packing_repair_can_revise_unmeasured_floor_estimate(self):
        value=layout();value['room'].update(width_m=2,length_m=2)
        value['objects']=[dict(id='bed'+str(n),kind='bed',region='front_left',yaw_deg=0,
            observation_ids=['bed_visual']) for n in range(3)]
        larger=copy.deepcopy(value);larger['room'].update(width_m=8,length_m=8)
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,value),completion('inflated',PLANNER_MODEL,larger))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',compact_photo_layout=True,max_repairs=1)
        from twinpulse_provider import InvalidProviderResponseError
        result=asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(
            request('Create an approximate bedroom')))
        self.assertEqual(result.plan.calls[0].arguments['size_m'],[8,8])
        self.assertEqual(len(transport.bodies),3)

    def test_reviewed_position_schema_is_evidence_bound_per_slot_and_preserves_default(self):
        from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
        reference=photo_reference(PHOTO_SHA256)
        default=layout_schema('Bedroom',reference,observation())
        constrained=layout_schema('Bedroom',reference,observation(),
            quality_constraints=reviewed_photo_constraints(PHOTO_SHA256))
        slots=constrained['properties']['objects']['properties']
        regions=lambda identity:slots[identity]['properties']['region']['enum']
        self.assertEqual(regions('desk'),['rear_left'])
        self.assertEqual(regions('bed'),['front_right','middle_right','rear_right'])
        self.assertEqual(regions('wardrobe'),['rear_left','rear_centre','rear_right'])
        self.assertEqual(regions('floor_bags'),['front_left','middle_left','rear_left'])
        self.assertEqual(len(default['properties']['objects']['properties']['bed']['properties']['region']['enum']),9)
        self.assertEqual(constrained['properties']['layout_version'],default['properties']['layout_version'])
        self.assertEqual(constrained['properties']['room'],default['properties']['room'])
        from dataclasses import replace
        reviewed=reviewed_photo_constraints(PHOTO_SHA256)
        for ref,quality,reason in ((None,reviewed,'INVENTORY'),
            (dict(reference,image_sha256='0'*64),reviewed,'EVIDENCE'),
            (reference,replace(reviewed,positions=reviewed.positions+(('bed','x','left'),)),'CONFLICT')):
            with self.assertRaisesRegex(ValueError,reason):
                layout_schema('Bedroom',ref,observation(),quality_constraints=quality)

    def test_room_dimensions_not_furniture_dimensions(self):
        self.assertEqual(requested_size('A 4 by 5 metre bedroom with a bed 1 by 2 metres'),(4,5))
        self.assertIsNone(requested_size('A bed 1 by 2 metres'))
        self.assertEqual(requested_size('bedroom 4m x 5m'),(4,5))
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):
            requested_size('room 4 by 5 and room 6 by 7')
        with self.assertRaisesRegex(ValueError,'UNQUALIFIED'):
            requested_size('4 by 5 metres')
        self.assertEqual(layout_schema(request().prompt)['properties']['room']['properties']['width_m']['const'],4)

    def test_normal_room_names_and_object_owners_remain_distinct(self):
        for name in ('전시방','전시실','교육실','실험실','exhibition room','display room'):
            self.assertEqual(requested_size('4m x 5m '+name+'에 가구를 만들어줘'),(4,5))
        self.assertIsNone(requested_size('1m x 2m 가방을 만들어줘'))
        with self.assertRaisesRegex(ValueError,'UNQUALIFIED'):
            requested_size('4m x 5m 알수없는명칭')

    def test_wire_schema_omits_unsupported_uniqueitems_but_local_rejects_duplicates(self):
        self.assertNotIn('uniqueItems',json.dumps(layout_schema(request().prompt)))
        v=layout();v['objects'][0]['observation_ids']=['bed_visual','bed_visual']
        with self.assertRaisesRegex(ValueError,'OBJECT_INVALID'):
            compile_layout(v,observation(),request(),None)

    def test_checked_estimated_proxies_no_physical_authority(self):
        payload,trace=compile_layout(layout(),observation(),request(),None)
        draft=execute_site_tool_plan(SiteToolPlan.from_dict(payload),source='photo',source_ref=canonical_sha256(payload))
        self.assertTrue(draft.scene.revision)
        self.assertEqual(trace['placement_relationships'],'NOT_RECONSTRUCTED')
        self.assertFalse(trace['physical_authority'])
        self.assertFalse(trace['production_default'])
        self.assertIn('not a reconstructed room',payload['summary'])
        self.assertEqual(payload['calls'][0]['arguments']['size_m'],[4,5])

    def test_rejects_missing_visual_unknown_reference_and_invented_objects(self):
        for mutate,reason in (
            (lambda v:v['objects'][0].update(observation_ids=[]),'WITHOUT_EVIDENCE'),
            (lambda v:v['objects'][0].update(observation_ids=['phantom']),'UNOBSERVED_REFERENCES'),
            (lambda v:v['objects'].append(dict(id='extra',kind='box',region='front_left',yaw_deg=0,observation_ids=[])),'WITHOUT_EVIDENCE'),
        ):
            value=layout();mutate(value)
            with self.assertRaisesRegex(ValueError,reason):compile_layout(value,observation(),request(),None)

    def test_unknown_observation_stays_uncertain_and_missing_observations_fail(self):
        raw=observation().to_dict()
        raw['entities'].append(dict(id='uncertain',kind='unknown',description='Unknown object',confidence=.3))
        observed=ObservationArtifact.from_mapping(raw)
        v=layout()
        with self.assertRaisesRegex(ValueError,'OBSERVED_ITEMS_MISSING'):
            compile_layout(v,observed,request(),None)
        v['objects'].append(dict(id='uncertain',kind='unknown',region='front_left',yaw_deg=0,
            observation_ids=['uncertain']))
        payload,trace=compile_layout(v,observed,request(),None)
        evidence=next(e for e in payload['call_evidence'] if e['call_id']=='obj_uncertain')
        self.assertEqual(evidence['basis'],'inferred')
        self.assertFalse(trace['physical_authority'])

    def test_strict_shapes_numbers_and_no_executable_fields(self):
        variants=[]
        for key,value in (('kind',[]),('region',{}),('yaw_deg',True),('observation_ids',[{}])):
            v=layout();v['objects'][0][key]=value;variants.append(v)
        for val in (float('nan'),True,1,13):
            v=layout();v['room']['width_m']=val;variants.append(v)
        v=layout();v['code']='run()';variants.append(v)
        v=layout();v['objects'].append(copy.deepcopy(v['objects'][0]));variants.append(v)
        for v in variants:
            with self.assertRaises(ValueError):compile_layout(v,observation(),request(),None)

    def test_preserves_floor_and_never_omits_objects_to_pack(self):
        v=layout();v['room']['width_m']=5
        with self.assertRaisesRegex(ValueError,'DIMENSIONS_CHANGED'):
            compile_layout(v,observation(),request(),None)
        v=layout();v['room'].update(width_m=2,length_m=2)
        v['objects']=[dict(id='bed'+str(n),kind='bed',region='front_left',yaw_deg=0,
            observation_ids=['bed_visual']) for n in range(3)]
        before=copy.deepcopy(v)
        with self.assertRaisesRegex(ValueError,'REGION_FULL'):
            compile_layout(v,observation(),request('Create a room 2 by 2 metres'),None)
        self.assertEqual(v,before)

    def test_reviewed_inventory_all_24_required_category_preserved(self):
        reference=photo_reference(PHOTO_SHA256)
        v=layout()
        v['layout_version']=LEGACY_REVISION
        with self.assertRaisesRegex(ValueError,'REVIEWED_ITEMS_MISSING'):
            compile_layout(v,observation(),request(),reference)
        v['objects'][0]['kind']='desk'
        with self.assertRaisesRegex(ValueError,'REVIEWED_KIND_CHANGED'):
            compile_layout(v,observation(),request(),reference)
        # Large fixture room verifies complete contract expansion, not photo fidelity.
        v['room'].update(width_m=8,length_m=8)
        regions=['front_left','middle_right','rear_left','middle_left','front_centre','front_right',
                 'rear_right','middle_centre','rear_centre']
        v['objects']=[dict(id=i['id'],kind=i['kind'],region=regions[n%9],yaw_deg=0,
            observation_ids=[]) for n,i in enumerate(reference['items'])]
        for item in v['objects']:
            if item['id'] in {'floor_bags','boxes'}:item['region']='front_left'
        payload,trace=compile_layout(v,observation(),request('Create an approximate room 8 by 8 metres'),reference)
        self.assertEqual(len(trace['placements']),24)
        self.assertEqual(len(payload['calls']),28)
        self.assertEqual({c['arguments']['id'] for c in payload['calls'][4:]},{i['id'] for i in reference['items']})

    def test_reviewed_slots_fix_all_ids_categories_and_visual_enumeration(self):
        reference=photo_reference(PHOTO_SHA256)
        schema=layout_schema(request().prompt,reference,observation())
        slots=schema['properties']['objects']
        self.assertEqual(slots['type'],'object')
        self.assertEqual(set(slots['required']),{i['id'] for i in reference['items']})
        for slot in slots['properties'].values():
            self.assertEqual(set(slot['properties']),{'region','yaw_deg','observation_ids'})
            self.assertEqual(slot['properties']['observation_ids']['items']['enum'],['bed_visual'])
        v=layout();v['room'].update(width_m=8,length_m=8)
        regions=['front_left','middle_right','rear_left','middle_left','front_centre','front_right',
                 'rear_right','middle_centre','rear_centre']
        v['objects']={i['id']:dict(region=regions[n%9],yaw_deg=0,observation_ids=[])
            for n,i in enumerate(reference['items'])}
        for identity in ('floor_bags','boxes'):v['objects'][identity]['region']='front_left'
        prompt=request('Create an approximate room 8 by 8 metres')
        payload,trace=compile_layout(v,observation(),prompt,reference)
        self.assertEqual(len(trace['placements']),24)
        self.assertEqual({c['arguments']['id']:c['arguments']['kind'] for c in payload['calls'][4:]},
            {i['id']:i['kind'] for i in reference['items']})
        v['objects'].pop('bed')
        with self.assertRaisesRegex(ValueError,'MISSING_OR_EXTRA'):compile_layout(v,observation(),prompt,reference)

    def test_reviewed_slots_reject_short_array_extra_fields_and_fake_visual_ids(self):
        reference=photo_reference(PHOTO_SHA256);v=layout()
        with self.assertRaisesRegex(ValueError,'SLOTS_REQUIRED'):
            compile_layout(v,observation(),request(),reference)
        v['objects']={i['id']:dict(region='front_left',yaw_deg=0,observation_ids=[])
            for i in reference['items']}
        v['objects']['bed']['kind']='desk'
        with self.assertRaisesRegex(ValueError,'SLOT_SHAPE_INVALID'):
            compile_layout(v,observation(),request(),reference)
        v['objects']['bed'].pop('kind');v['objects']['bed']['observation_ids']=['invented']
        with self.assertRaisesRegex(ValueError,'UNOBSERVED_REFERENCES: object=bed'):
            compile_layout(v,observation(),request(),reference)

    def test_pipeline_reuses_observer_and_single_repair_same_schema(self):
        invalid=layout();invalid['objects'][0]['observation_ids']=['phantom']
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,invalid),completion('repair',PLANNER_MODEL,layout()))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        result=asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(request()))
        self.assertEqual(result.plan.plan_version,'2.2')
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1)
        self.assertEqual(result.provider_provenance['photo_layout_compiler']['contract'],REVISION)
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        self.assertIn('not tool calls',transport.bodies[2]['messages'][-1]['content'])

    def test_opt_in_does_not_change_text_or_default_photo_body(self):
        for opt in (False,True):
            provider=NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
                planner_model_id=PLANNER_MODEL,site_plan_version='2.2',compact_photo_layout=opt)
            text=GenerationRequest('text','Create a room')
            body=provider.build_planner_body(text,observation())
            self.assertEqual(body['response_format']['json_schema']['name'],'twinpulse_site_tool_plan_v2')
            self.assertNotIn('reasoning_effort',body)
            self.assertNotIn('chat_template_kwargs',body)
        with self.assertRaisesRegex(Exception,'requires Site2.2'):
            NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
                planner_model_id=PLANNER_MODEL,compact_photo_layout=True)

    def test_explicit_template_policy_is_top_level_and_survives_single_photo_repair(self):
        invalid=layout();invalid['objects'][0]['observation_ids']=['phantom']
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,invalid),completion('repair',PLANNER_MODEL,layout()))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,
            compact_photo_layout=True,planner_template_no_thinking=True)
        result=asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2').generate(request()))
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1)
        self.assertNotIn('chat_template_kwargs',transport.bodies[0])
        for body in transport.bodies[1:]:
            self.assertEqual(body['chat_template_kwargs'],{'enable_thinking':False})
            self.assertNotIn('extra_body',body)
            self.assertNotIn('reasoning_effort',body)
            self.assertEqual(body['max_tokens'],8000)
        self.assertEqual(transport.bodies[1]['response_format'],transport.bodies[2]['response_format'])
        text=provider.build_planner_body(GenerationRequest('text','Create a room'),observation())
        self.assertEqual(text['chat_template_kwargs'],{'enable_thinking':False})
        self.assertNotIn('extra_body',text)

    def test_template_policy_rejects_other_models_versions_or_combined_reasoning(self):
        from twinpulse_provider import ProviderConfigurationError
        for changes in ({'planner_model_id':'other/model'}, {'site_plan_version':'1.0'},
                        {'planner_reasoning_effort':'none'}):
            kwargs=dict(observer_model_id=OBSERVER_MODEL,planner_model_id=PLANNER_MODEL,
                site_plan_version='2.2',planner_template_no_thinking=True)
            kwargs.update(changes)
            with self.assertRaises(ProviderConfigurationError):
                NebiusChatCompletionsPipelineProvider(ScriptedTransport(),**kwargs)

    def test_raw_urllib_wire_contains_top_level_template_kwargs_not_sdk_extra_body(self):
        from twinpulse_provider import UrllibChatCompletionsTransport
        provider=NebiusChatCompletionsPipelineProvider(ScriptedTransport(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',planner_template_no_thinking=True)
        body=provider.build_planner_body(GenerationRequest('text','Create a room'),observation())
        captured=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return config().endpoint_url()
            def read(self,limit):return json.dumps(dict(id='fake',model=PLANNER_MODEL,
                choices=[dict(finish_reason='stop',message=dict(content='{}'))],usage={})).encode()
        def opener(request,timeout):
            captured.append(json.loads(request.data))
            return Response()
        transport=UrllibChatCompletionsTransport(lambda:'fake-local-test-only',opener=opener)
        asyncio.run(transport.complete(body,CancellationToken(),config()))
        self.assertEqual(captured,[body])
        self.assertEqual(captured[0]['chat_template_kwargs'],{'enable_thinking':False})
        self.assertNotIn('extra_body',captured[0])


if __name__=='__main__':unittest.main()
