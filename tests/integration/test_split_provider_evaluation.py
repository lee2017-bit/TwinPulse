# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline scripted boundaries, not live model quality or Isaac acceptance."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.provider_composition import build_split_generation_service
from twinpulse_app.settings import provider_settings_preset
from twinpulse_app.split_evaluation import SplitEvaluationLedger,NANO,build_scoped_split_service
from twinpulse_provider import GenerationRequest,ImageInput,CancellationToken,ProviderConfigurationError
from twinpulse_provider.nebius_pipeline import ChatCompletion,ObservationArtifact
from twinpulse_provider import InvalidProviderResponseError
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT,openai_observer_body
from twinpulse_provider.photo_layout import REVISION,layout_schema
from twinpulse_provider.scene_contract import GROUNDING_REVISION

OBSERVER=replace(provider_settings_preset('openai'),model_id='gpt-5.4-mini')
PLANNER=provider_settings_preset('nebius_site_v2')
REQUEST=GenerationRequest('split-test','Create an approximate bedroom, 4 by 5 metres.',
    (ImageInput('room.jpg','image/jpeg',b'fixture'),))
OBS=dict(schema_version='1.0',summary='Unmeasured bedroom.',entities=[dict(
    id='bed_visual',kind='static_obstacle',description='Bed on right',confidence=.8)],
    relations=[],dimensions=[],ambiguities=['Scale is unknown'])
LAYOUT=dict(layout_version=REVISION,summary='Approximate room; no measured geometry.',
    room=dict(width_m=4,length_m=5,height_m=2.5),objects=[dict(id='bed',kind='bed',
    region='middle_right',yaw_deg=0,observation_ids=['bed_visual'])])

class Transport:
    def __init__(self,*values):self.values=list(values);self.calls=[]
    async def complete(self,body,token,config):
        self.calls.append((deepcopy(body),config))
        return ChatCompletion(str(len(self.calls)),config.model_id,json.dumps(self.values.pop(0)),
            'stop',{'prompt_tokens':1000,'completion_tokens':100})

def composed(obs=None,plans=None):
    observer=Transport(*(obs or [OBS]));planner=Transport(*(plans or [LAYOUT]))
    service=build_split_generation_service(OBSERVER,observer,PLANNER,planner,timeout_s=10,
        compact_photo_layout=True,output_token_cap=10000)
    return service,observer,planner

def account(root,**kwargs):
    return SplitEvaluationLedger(root/'campaign.json',approval='offline-only',rates={
        OPENAI_MINI_SNAPSHOT:dict(input_per_million='.75',output_per_million='4.5',context_tokens=400000,source='https://developers.openai.com/api/docs/models/gpt-5.4-mini'),
        NANO:dict(input_per_million='.06',output_per_million='.24',context_tokens=262144,source='https://api.tokenfactory.nebius.com/private/v1/models_info')},
        max_requests=10,limit_usd='.15',**kwargs)

class RoutingTests(unittest.TestCase):
    def test_kind_bound_grammar_separates_visual_refs_library_finish_and_floor(self):
        value=deepcopy(OBS);value['schema_version']='1.1'
        value['entities']=[dict(id='c',kind='static_obstacle',description='Chair',confidence=.8,
            role='object',category='office_chair',region='middle_centre',spatial_confidence=.8),
            dict(id='b',kind='static_obstacle',description='Covering',confidence=.8,
            role='object',category='window_blind',region='rear_centre',spatial_confidence=.8)]
        observation=ObservationArtifact.from_mapping(value)
        schema=layout_schema('Create a room',observation=observation,revision=GROUNDING_REVISION)
        branches={b['properties']['kind']['enum'][0]:b['properties']
            for b in schema['properties']['objects']['items']['anyOf']}
        chair=branches['office_chair'];door=branches['door_leaf'];blind=branches['window_blind']
        self.assertEqual(chair['placement']['properties']['parent_id'],{'type':'null'})
        self.assertNotIn('natural',chair['finish']['enum'])
        visual=next(b for b in chair['source']['anyOf'] if b['properties']['basis'].get('const')=='visual')
        self.assertEqual(visual['properties']['observation_ids']['items']['enum'],['c'])
        door_sources=door['source']['anyOf']
        self.assertEqual({b['properties']['basis']['const'] for b in door_sources},{'user','inferred'})
        # An unobserved estimate is permitted, never fake visual door evidence.
        self.assertTrue(all(b['properties']['observation_ids']['maxItems']==0 for b in door_sources))
        self.assertIn('rear_wall',blind['placement']['properties']['parent_id']['enum'])
        self.assertEqual([e['id'] for e in observation.entities],['c','b'])

    def test_all_semantic_role_errors_have_exact_entity_paths_for_one_repair(self):
        bad=deepcopy(OBS);bad['schema_version']='1.1'
        bad['entities']=[dict(id='chair',kind='static_obstacle',description='Chair',confidence=.8,
            role='robot',category='office_chair',region='middle_centre',spatial_confidence=.8),
            dict(id='blind',kind='static_obstacle',description='Window covering',confidence=.8,
            role='structure',category='window_blind',region='rear_centre',spatial_confidence=.8)]
        with self.assertRaises(InvalidProviderResponseError) as caught:ObservationArtifact.from_mapping(bad)
        issues=caught.exception.contract_report['issues']
        self.assertEqual([i['path'] for i in issues],['$.entities[0].role','$.entities[1].role'])
        self.assertTrue(all(i['allowed_roles']==['object','unknown'] for i in issues))
        fixed=deepcopy(bad)
        for item in fixed['entities']:item['role']='object'
        self.assertEqual(len(ObservationArtifact.from_mapping(fixed).entities),2)
        self.assertEqual(bad['entities'][0]['role'],'robot')

    def test_split_input_metadata_is_accepted_without_secret_or_unvalidated_url(self):
        from twinpulse_core.revisions import InputRevision
        settings={'base_url':PLANNER.base_url,'observer_base_url':OBSERVER.base_url,
                  'model_id':NANO,'observer_model_id':OPENAI_MINI_SNAPSHOT,'request_schema':'2.2'}
        revision=InputRevision.create(prompt=REQUEST.prompt,images=(),generation_settings=settings,
            measurement_constraints=(),profile_id='offline')
        self.assertEqual(revision.generation_settings,settings)
        for mutation in ({'observer_base_url':'https://user:secret@api.openai.com/v1/'},
                         {'api_key':'secret'}):
            with self.assertRaises(ValueError):
                InputRevision.create(prompt=REQUEST.prompt,images=(),generation_settings={**settings,**mutation},
                    measurement_constraints=(),profile_id='offline')

    def test_stage_credentials_config_and_wire_semantics(self):
        service,observer,planner=composed()
        asyncio.run(service.generate(REQUEST))
        body,config=observer.calls[0]
        self.assertEqual(config.base_url,'https://api.openai.com/v1/')
        self.assertEqual(config.model_id,OPENAI_MINI_SNAPSHOT)
        self.assertEqual(body['max_completion_tokens'],10000)
        self.assertNotIn('temperature',body)
        self.assertIn('data:image/jpeg',json.dumps(body['messages']))
        body,config=planner.calls[0]
        self.assertEqual(config.base_url,'https://api.tokenfactory.nebius.com/v1/')
        self.assertEqual(config.model_id,NANO)
        self.assertNotIn('data:image',json.dumps(body))
        self.assertEqual(body['max_tokens'],10000)

    def test_single_shared_content_repair_uses_planner_not_observer(self):
        service,observer,planner=composed(plans=[{},LAYOUT])
        asyncio.run(service.generate(REQUEST))
        self.assertEqual(len(observer.calls),1)
        self.assertEqual(len(planner.calls),2)
        self.assertEqual(service._provider.diagnostic_for(REQUEST.request_id)['repair_count'],1)
        self.assertGreater(len(planner.calls[1][0]['messages']),len(planner.calls[0][0]['messages']))

    def test_unknown_stage_model_and_image_leak_are_rejected_before_dispatch(self):
        service,observer,planner=composed()
        transport=service._provider._transport
        base={'model':NANO,'response_format':{'json_schema':{'name':'twinpulse_compact_photo_layout'}},
              'messages':[{'role':'user','content':'data:image/jpeg;base64,fixture'}]}
        for mutation in ({},{'model':'other'},{'response_format':{'json_schema':{'name':'unknown'}}}):
            with self.assertRaises(ProviderConfigurationError):
                asyncio.run(transport.complete({**base,**mutation},CancellationToken(),service._config))
        self.assertFalse(observer.calls or planner.calls)

    def test_wire_normalization_does_not_mutate_original(self):
        service,_,_=composed();original=service._provider.build_observer_body(REQUEST)
        before=deepcopy(original);body=openai_observer_body(original)
        self.assertEqual(original,before)
        self.assertEqual(body['messages'],original['messages'])
        self.assertEqual(body['response_format']['json_schema']['schema']['required'],
            original['response_format']['json_schema']['schema']['required'])

    def test_wrong_approved_input_does_not_load_or_send_keys(self):
        class Key:
            def load(self):raise AssertionError('key must not be loaded')
        service=build_scoped_split_service({'prompt':'approved','photo_sha256':'not-this-input'},
            OBSERVER,Key(),PLANNER,Key(),None,Path('unused'))
        with self.assertRaises(ProviderConfigurationError):asyncio.run(service.generate(REQUEST))

class LedgerTests(unittest.TestCase):
    def body(self):
        service,_,_=composed()
        return openai_observer_body(service._provider.build_observer_body(REQUEST))

    def test_inflight_lock_and_unknown_cost_are_not_reset(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);ledger=account(root);body=self.body();identity=ledger.reserve(body)
            with self.assertRaises(ProviderConfigurationError):account(root).reserve(body)
            ledger.settle(identity,status='outcome_unknown')
            ledger=account(root)
            self.assertEqual(len(ledger.state['requests']),1)
            self.assertGreater(float(ledger.state['requests'][0]['charged_or_reserved_usd']),.07)
            with self.assertRaises(ProviderConfigurationError):ledger.reserve(body)
            self.assertFalse(ledger.lock_path.exists())

    def test_shared_ten_call_cap_is_durable_across_restarts(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);body=self.body()
            for _ in range(10):
                ledger=account(root);identity=ledger.reserve(body)
                ledger.settle(identity,usage={'prompt_tokens':100,'completion_tokens':1},status='received')
            ledger=account(root)
            with self.assertRaises(ProviderConfigurationError):ledger.reserve(body)
            self.assertEqual(len(ledger.state['requests']),10)

    def test_per_run_call_limit_applies_to_both_models(self):
        with TemporaryDirectory() as temp:
            ledger=account(Path(temp),run_request_cap=2)
            for body in (self.body(),{'model':NANO,'max_tokens':10000}):
                identity=ledger.reserve(body)
                ledger.settle(identity,usage={'prompt_tokens':100,'completion_tokens':1},status='received')
            with self.assertRaises(ProviderConfigurationError):ledger.reserve(self.body())
            self.assertEqual(len(ledger.state['requests']),2)

    def test_rejects_missing_image_unreviewed_models_or_excess_output(self):
        with TemporaryDirectory() as temp:
            ledger=account(Path(temp));body=self.body()
            for mutation in ({'model':'other'},{'messages':[]},{'max_completion_tokens':10001}):
                with self.assertRaises(ProviderConfigurationError):ledger.reserve({**body,**mutation})
            self.assertFalse(ledger.state['requests'])
            self.assertFalse(ledger.lock_path.exists())

if __name__=='__main__':unittest.main()
