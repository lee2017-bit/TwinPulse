# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import asyncio
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_provider import GenerationService,GenerationRequest,ProviderConfig,NebiusChatCompletionsPipelineProvider,ObservationArtifact
from twinpulse_provider.contracts import ProviderResponse
from twinpulse_provider.schema import site_tool_plan_json_schema
from twinpulse_app.manual_room import manual_room_plan
from packages.twinpulse_provider.tests.test_nebius_pipeline import observation,config


class FurnitureGenerationTests(unittest.TestCase):
    def test_legacy_schema_unchanged_and_furniture_only_in_new_site_schema(self):
        old=site_tool_plan_json_schema()
        new=site_tool_plan_json_schema('2.1')
        names=lambda value:{call['properties']['tool']['const'] for call in value['properties']['calls']['items']['anyOf']}
        self.assertNotIn('place_furniture',names(old))
        self.assertIn('place_furniture',names(new))
        self.assertEqual(old['properties']['plan_version']['const'],'2.0')
        self.assertEqual(new['properties']['plan_version']['const'],'2.1')

    def test_new_planner_uses_environment_and_catalog_not_warehouse_only(self):
        provider=NebiusChatCompletionsPipelineProvider(None,observer_model_id='observer',planner_model_id='planner',site_plan_version='2.1')
        # The body builder is pure and issues no transport call.
        request=GenerationRequest(request_id='furniture',prompt='Create an apartment living room')
        observed=ObservationArtifact.from_mapping(observation())
        body=provider.build_planner_body(request,observed)
        prompt=body['messages'][0]['content']
        self.assertIn('sofa, dining_table',prompt)
        self.assertIn('not warehouse racks by default',prompt)
        self.assertEqual(body['response_format']['json_schema']['schema']['properties']['plan_version']['const'],'2.1')

    def test_fake_provider_furniture_plan_flows_through_existing_generation_service(self):
        plan=manual_room_plan('living',6.,7.,2.6,[{'kind':'sofa','center_m':[-1.5,1.6],'yaw_deg':90},
            {'kind':'dining_table','center_m':[1.5,1.6],'yaw_deg':0}])
        class Provider:
            async def generate(self,request,token,config):
                return ProviderResponse(request.request_id,plan.to_dict(),'explicit furniture fixture',config.model_id)
        service=GenerationService(Provider(),config(),plan_version='2.1')
        result=asyncio.run(service.generate(GenerationRequest(request_id='living',prompt='Living room')))
        self.assertEqual(result.plan.plan_version,'2.1')
        self.assertEqual([c.arguments['kind'] for c in result.plan.calls if c.tool=='place_furniture'],['sofa','dining_table'])
