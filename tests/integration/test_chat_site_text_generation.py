# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline transport through the real site provider/service; no paid calls."""
import asyncio
import time
import unittest

from packages.twinpulse_provider.tests.test_nebius_pipeline import (
    ScriptedTransport, completion, config, request, observation, OBSERVER_MODEL, PLANNER_MODEL,
)
from twinpulse_app.manual_room import manual_room_plan
from twinpulse_app.provider_composition import build_live_generation_service
from twinpulse_app.settings import provider_settings_preset
from twinpulse_app.product_workflow_service import _public_generation_error
from twinpulse_provider import GenerationRequest, GenerationService, NebiusChatCompletionsPipelineProvider, InvalidProviderResponseError, ProviderTimeoutError
from tests.integration.test_chat_conversation import ChatConversationTests


def room():
    value=manual_room_plan('bedroom',4.,5.,2.6,[]).to_dict()
    value['plan_version']='2.2'
    for item in value['call_evidence']:
        item.update(basis='user',observation_ids=[])
    return value


def shell_observation():
    value=observation()
    value.update(entities=[],relations=[],dimensions=[],summary='No discrete objects in this synthetic shell.')
    return value


def provider(transport):
    return NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
        planner_model_id=PLANNER_MODEL,site_plan_version='2.2')


class TextSiteTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_text_wire_lowers_required_floor_without_photo_and_persists_provenance(self):
        from twinpulse_provider.scene_contract import lower_proposal, PROPOSAL_REVISION
        original=room();calls=original['calls'];evidence=original['call_evidence'];prompt='Make a small bedroom'
        floor=next(c for c in calls if c['tool']=='create_floor')
        sources=[{**e,'user_quote':prompt} for e in evidence]
        wire={**{k:original[k] for k in ('plan_version','scene_id','summary','image_observations')},
            'proposal_version':PROPOSAL_REVISION,'coordinate_frame':'local_xy','floor_call':floor,
            'floor_evidence':next(e for e in sources if e['call_id']==floor['call_id']),
            'scene_calls':[c for c in calls if c['tool']!='create_floor'],
            'call_evidence':[e for e in sources if e['call_id']!=floor['call_id']]}
        transport=ScriptedTransport(completion('plan',PLANNER_MODEL,wire))
        result=await GenerationService(provider(transport),config(),plan_version='2.2').generate(GenerationRequest('text',prompt))
        self.assertEqual(result.plan.to_dict(),original);self.assertEqual(result.image_count,0)
        self.assertEqual(result.provider_provenance['site_proposal']['coordinate_frame'],'local_xy')
        self.assertEqual(len(transport.bodies),1);self.assertEqual(lower_proposal(wire)[0],original)
    async def test_text_skips_observer_and_accepts_a_valid_v22_room(self):
        transport=ScriptedTransport(completion('plan',PLANNER_MODEL,room()))
        service=GenerationService(provider(transport),config(),plan_version='2.2')
        result=await service.generate(GenerationRequest('text','Make a small bedroom'))
        self.assertEqual(result.plan.plan_version,'2.2')
        self.assertEqual(result.image_count,0)
        self.assertEqual(len(transport.bodies),1)
        self.assertEqual(transport.bodies[0]['model'],PLANNER_MODEL)
        self.assertIn('text-only',transport.bodies[0]['messages'][0]['content'])

    async def test_photo_keeps_observer_and_planner(self):
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,shell_observation()),completion('plan',PLANNER_MODEL,room()))
        result=await GenerationService(provider(transport),config(),plan_version='2.2').generate(request())
        self.assertEqual(result.image_count,1)
        self.assertEqual(len(transport.bodies),2)

    async def test_text_cannot_fabricate_visual_evidence(self):
        value=room();value['call_evidence'][0].update(basis='visual',observation_ids=['fabricated'])
        transport=ScriptedTransport(completion('plan',PLANNER_MODEL,value))
        with self.assertRaisesRegex(InvalidProviderResponseError,'SOURCE_UNOBSERVED_REFERENCES'):
            await GenerationService(provider(transport),config(),plan_version='2.2').generate(GenerationRequest('text','Bedroom'))
        self.assertEqual(len(transport.bodies),1)

    async def test_stage_timeout_is_identified_without_retry(self):
        transport=ScriptedTransport(delay_s=.1)
        adapter=provider(transport)
        with self.assertRaises(ProviderTimeoutError) as caught:
            await GenerationService(adapter,config(timeout_s=.01),plan_version='2.2').generate(GenerationRequest('text','Bedroom'))
        public=_public_generation_error(caught.exception)
        self.assertEqual(public['diagnostics']['stage'],'planner')
        self.assertEqual(public['diagnostics']['max_tokens'],8000)
        self.assertIn('planner stage',public['message'])

    async def test_truncation_retains_stage_and_budget_without_response_content(self):
        adapter=provider(ScriptedTransport(InvalidProviderResponseError('Chat Completions output was truncated')))
        with self.assertRaises(InvalidProviderResponseError) as caught:
            await GenerationService(adapter,config(),plan_version='2.2').generate(request())
        diagnostic=_public_generation_error(caught.exception)['diagnostics']
        self.assertEqual(diagnostic['stage'],'observer')
        self.assertEqual(diagnostic['finish_reason'],'length')
        self.assertEqual(diagnostic['max_tokens'],4000)

    def test_explicit_chat_composition_preserves_legacy_settings_and_default(self):
        settings=provider_settings_preset('nebius_token_factory')
        legacy=build_live_generation_service(settings,lambda:None)
        chat=build_live_generation_service(settings,lambda:None,plan_version='2.2')
        self.assertEqual(legacy._plan_version,'1.0')
        self.assertEqual(chat._plan_version,'2.2')
        self.assertEqual(settings.provider_profile,'nebius_token_factory')

    def test_compact_composition_is_host_opt_in_and_default_stays_off(self):
        settings=provider_settings_preset('nebius_token_factory')
        default=build_live_generation_service(settings,lambda:None,plan_version='2.2')
        experimental=build_live_generation_service(settings,lambda:None,plan_version='2.2',compact_photo_layout=True)
        self.assertFalse(default._provider.compact_photo_layout)
        self.assertTrue(experimental._provider.compact_photo_layout)
        from twinpulse_app.provider_composition import generation_request_schema
        self.assertEqual(generation_request_schema(settings.adapter_kind),'site-proposal-1.0')
        self.assertEqual(generation_request_schema(settings.adapter_kind,compact_photo_layout=True),'photo-layout-1.3')
        self.assertEqual(generation_request_schema('openai_responses'),'1.0')
        from twinpulse_provider import ProviderConfigurationError
        with self.assertRaisesRegex(ProviderConfigurationError,'Nebius Site2.2'):
            build_live_generation_service(settings,lambda:None,compact_photo_layout=True)

    def test_template_policy_composition_is_explicit_and_never_reads_key_at_construction(self):
        settings=provider_settings_preset('nebius_token_factory')
        def no_key_access():
            raise AssertionError('construction must not load credentials')
        default=build_live_generation_service(settings,no_key_access,plan_version='2.2')
        explicit=build_live_generation_service(settings,no_key_access,plan_version='2.2',
            compact_photo_layout=True,planner_template_no_thinking=True)
        self.assertFalse(default._provider.planner_template_no_thinking)
        self.assertTrue(explicit._provider.planner_template_no_thinking)
        from twinpulse_provider import ProviderConfigurationError
        with self.assertRaises(ProviderConfigurationError):
            build_live_generation_service(settings,no_key_access,planner_template_no_thinking=True)

    async def test_invalid_observer_shape_preserves_stage_without_calling_planner(self):
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,{'unexpected':'shape'}))
        with self.assertRaises(InvalidProviderResponseError) as caught:
            await GenerationService(provider(transport),config(),plan_version='2.2').generate(request())
        self.assertEqual(_public_generation_error(caught.exception)['diagnostics']['stage'],'observer')
        self.assertEqual(len(transport.bodies),1)

    async def test_invalid_planner_evidence_preserves_stage(self):
        value=room();value['call_evidence'][0].update(basis='visual',observation_ids=['fabricated'])
        transport=ScriptedTransport(completion('plan',PLANNER_MODEL,value))
        with self.assertRaises(InvalidProviderResponseError) as caught:
            await GenerationService(provider(transport),config(),plan_version='2.2').generate(GenerationRequest('text','Bedroom'))
        self.assertEqual(_public_generation_error(caught.exception)['diagnostics']['stage'],'planner')
        self.assertEqual(len(transport.bodies),1)

    def test_public_diagnostic_drops_unknown_fields(self):
        error=ProviderTimeoutError('Timed out')
        error.diagnostics={'stage':'planner','response_body':'do not expose','api_key':'do not expose','elapsed_s':float('nan')}
        self.assertEqual(_public_generation_error(error)['diagnostics'],{'stage':'planner'})


class ChatSiteJourneyTests(unittest.TestCase):
    setUp=ChatConversationTests.setUp
    tearDown=ChatConversationTests.tearDown
    request=ChatConversationTests.request
    product_headers=ChatConversationTests.product_headers
    call=ChatConversationTests.call
    send=ChatConversationTests.send
    answer=ChatConversationTests.answer

    def finished(self):
        for _ in range(100):
            state=self.call()
            if state['generation']['state']!='running':return state
            time.sleep(.02)
        self.fail('Offline generation did not finish')

    def install_gateway(self,*responses):
        self.transport=ScriptedTransport(*responses)
        self.workflow._application.set_generation_gateway(GenerationService(provider(self.transport),config(),plan_version='2.2'))

    def test_text_chat_reaches_site_draft_and_checked_sim_preview_without_an_image(self):
        self.install_gateway(completion('plan',PLANNER_MODEL,room()))
        initial=self.send();self.call(self.answer(initial));state=self.finished()
        self.assertEqual(state['generation']['state'],'completed')
        self.assertIsNotNone(state['simulation_review']['plan'])
        self.assertIsNotNone(self.workflow.snapshot()['site_draft']['artifact_id'])
        self.assertEqual(len(self.transport.bodies),1)
        self.assertFalse(state['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_photo_chat_reaches_the_same_scene_path(self):
        self.install_gateway(completion('obs',OBSERVER_MODEL,shell_observation()),completion('plan',PLANNER_MODEL,room()))
        initial=self.send(image=True);self.call(self.answer(initial));state=self.finished()
        self.assertEqual(state['generation']['state'],'completed')
        self.assertIsNotNone(state['simulation_review']['plan'])
        self.assertEqual(len(self.transport.bodies),2)

    def test_opt_in_compact_photo_uses_existing_chat_artifact_sim_review(self):
        from twinpulse_provider.photo_layout import REVISION
        observed=dict(schema_version='1.0',summary='Unmeasured bedroom.',entities=[
            dict(id='bed_visual',kind='static_obstacle',description='Bed',confidence=.8)],
            relations=[],dimensions=[],ambiguities=['Scale unknown'])
        intent=dict(layout_version=REVISION,summary='Illustrative bedroom inventory.',
            room=dict(width_m=4,length_m=5,height_m=2.5),objects=[dict(id='bed',kind='bed',
                region='middle_right',yaw_deg=0,observation_ids=['bed_visual'])])
        self.transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observed),
            completion('compact',PLANNER_MODEL,intent))
        adapter=NebiusChatCompletionsPipelineProvider(self.transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        self.workflow._application.set_generation_gateway(GenerationService(adapter,config(),plan_version='2.2'))
        initial=self.send(image=True);self.call(self.answer(initial));state=self.finished()
        self.assertEqual(state['generation']['state'],'completed')
        self.assertIsNotNone(state['simulation_review']['plan'])
        self.assertIsNotNone(self.workflow.snapshot()['site_draft']['artifact_id'])
        self.assertEqual(len(self.transport.bodies),2)
        self.assertFalse(state['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        plan=self.workflow._application.site_draft.plan
        self.assertIn('not a reconstructed room',plan.summary)
        self.assertEqual(plan.plan_version,'2.2')

    def test_new_compact_photo_persists_relationship_contract_in_existing_application(self):
        self._relationship_journey(flat_provenance=False)

    def test_staged_flat_compiler_provenance_retains_relationships_on_reopen(self):
        self._relationship_journey(flat_provenance=True)

    def _relationship_journey(self, *, flat_provenance):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/twinpulse_provider/tests'))
        from test_photo_parametric import intent,object_intent
        observed=dict(schema_version='1.0',summary='Explicit estimated fixture.',entities=[
            dict(id='bed_visual',kind='static_obstacle',description='Bed',confidence=.8)],
            relations=[],dimensions=[],ambiguities=['Scale unknown'])
        value=intent(object_intent('bed','bed','middle_right',size=[1.1,2.,.9]),
            object_intent('blanket','bedding_overhang',parent='bed',part='mattress',relation='drape',anchor='left'))
        from twinpulse_provider.scene_contract import GROUNDING_REVISION
        value['layout_version']=GROUNDING_REVISION
        observed['schema_version']='1.1'
        observed['entities']=[]
        for item in value['objects']:
            item.pop('observation_ids')
            item['source']=dict(basis='visual',observation_ids=['seen_'+item['id']],user_quote=None)
            observed['entities'].append(dict(id='seen_'+item['id'],kind='static_obstacle',description=item['kind'],
                confidence=.9,role='object',category=item['kind'],region='unknown',spatial_confidence=0))
        self.transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observed),completion('compact',PLANNER_MODEL,value))
        adapter=NebiusChatCompletionsPipelineProvider(self.transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        if flat_provenance:
            original=adapter
            class FlatProvenance:
                async def generate(self,request,token,configuration):
                    from dataclasses import replace
                    response=await original.generate(request,token,configuration)
                    return replace(response,provenance=response.provenance['photo_layout_compiler'])
            adapter=FlatProvenance()
        self.workflow._application.set_generation_gateway(GenerationService(adapter,config(),plan_version='2.2'))
        initial=self.send(image=True);self.call(self.answer(initial));state=self.finished()
        self.assertEqual(state['generation']['state'],'completed')
        record=self.workflow._application.site_draft
        self.assertEqual(record.schema_version,'2.1')
        self.assertEqual(record.placement_contract['relations'][1]['parent_id'],'bed')
        from twinpulse_app.site_draft import SiteDraftRecord
        from twinpulse_core.photo_placement import validate_placement_plan
        reopened=SiteDraftRecord.from_dict(record.to_dict())
        self.assertEqual(reopened.placement_contract,record.placement_contract)
        validate_placement_plan(reopened.plan,reopened.placement_contract)
        self.assertEqual(self.workflow.snapshot()['site_draft']['placement_contract'],record.placement_contract)
        self.assertIsNotNone(state['simulation_review']['plan']);self.assertFalse(state['physical_authority'])
        self.assertEqual(len(self.transport.bodies),2)

    def test_explicit_retry_keeps_input_failure_history_and_idempotency(self):
        self.install_gateway(InvalidProviderResponseError('Chat Completions output was truncated'),completion('plan',PLANNER_MODEL,room()))
        initial=self.send();self.call(self.answer(initial));failed=self.finished()
        digest=self.workflow.current_input.revision
        self.assertEqual(failed['generation']['state'],'failed')
        retry={'action':'generation_retry','request_id':'retry-1','operation_id':failed['generation']['operation_id']}
        self.call(retry);state=self.finished();self.call(retry)
        self.assertEqual(state['generation']['state'],'completed')
        self.assertEqual(self.workflow.current_input.revision,digest)
        self.assertEqual(len(self.transport.bodies),2)
        self.assertTrue(any(m['status']=='failed' and 'truncated' in m['content'] for m in state['messages']))

    def test_retry_wrong_operation_is_rejected_without_provider_call(self):
        self.install_gateway(InvalidProviderResponseError('Chat Completions output was truncated'))
        initial=self.send();self.call(self.answer(initial));self.finished()
        status,body,_=self.request('/v1/product/conversation',{'action':'generation_retry','request_id':'wrong','operation_id':'other'},headers=self.product_headers)
        self.assertEqual(status,409,body)
        self.assertEqual(len(self.transport.bodies),1)
