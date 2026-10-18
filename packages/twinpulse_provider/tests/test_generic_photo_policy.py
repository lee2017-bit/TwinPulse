# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic draft acceptance. Scripted transport is not actual model quality."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import unittest
from unittest.mock import patch

from twinpulse_core.photo_quality import inspect_photo_geometry, reviewed_photo_constraints
from twinpulse_core.room_photo_inventory import photo_reference
from twinpulse_provider import GenerationService, InvalidProviderResponseError
from twinpulse_provider.photo_layout import compile_layout, build_layout_body, PhotoLayoutPackingError
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider
from test_photo_layout import observation, request, layout
from test_photo_parametric import object_intent, intent
from test_nebius_pipeline import ScriptedTransport, completion, config, OBSERVER_MODEL, PLANNER_MODEL


class GenericPhotoPolicyTests(unittest.TestCase):
    def run_pipeline(self, values, req=None):
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            *(completion(str(n),PLANNER_MODEL,v) for n,v in enumerate(values)))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        result=asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2')
            .generate(req or request('An approximate room')))
        return result,transport

    def test_retired_known_photo_factories_are_inert(self):
        # Historical hash is a test input only, not a product scene recipe.
        from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256
        for digest in (PHOTO_SHA256,'0'*64,hashlib.sha256(b'another room').hexdigest()):
            self.assertIsNone(photo_reference(digest))
            self.assertIsNone(reviewed_photo_constraints(digest,semantic_review=True))

    def test_general_compact_schema_uses_reusable_parametric_array(self):
        req=request('An approximate room')
        first=build_layout_body(req,observation(),PLANNER_MODEL,None)
        other=replace(req,images=(replace(req.images[0],content=b'a different photo'),))
        second=build_layout_body(other,observation(),PLANNER_MODEL,None)
        self.assertEqual(first['response_format'],second['response_format'])
        schema=first['response_format']['json_schema']['schema']
        self.assertEqual(schema['properties']['layout_version']['const'],'photo-layout-1.3')
        self.assertEqual(schema['properties']['objects']['type'],'array')
        item=schema['properties']['objects']['items']
        # Exact per-kind branches keep optional warehouse parameters out of
        # home rows while preserving the same generic parametric array.
        for branch in item['anyOf']:
            self.assertIn('dimensions_m',branch['properties'])
            self.assertIn('placement',branch['properties'])
        payload=json.loads(first['messages'][1]['content'])
        self.assertNotIn('reviewed_photo_inventory',payload)
        self.assertNotIn('reviewed_geometry_constraints',payload)

    def test_10_by_12_estimate_is_draft_success_not_measured_quality(self):
        value=intent(object_intent('free_id','desk'),width=10,length=12)
        before=deepcopy(value)
        result,transport=self.run_pipeline([value])
        self.assertEqual(value,before)
        self.assertEqual(result.plan.calls[0].arguments['size_m'],[10,12])
        quality=result.provider_provenance['photo_geometry_quality']
        self.assertEqual(quality['status'],'UNVERIFIED')
        self.assertTrue(quality['generation_allowed'])
        self.assertFalse(quality['large_room_scale_warning'])
        self.assertEqual(len(transport.bodies),2)

    def test_repair_can_resize_and_reposition_all_inferred_objects(self):
        bad=layout();bad['room'].update(width_m=2,length_m=2)
        bad['objects']=[dict(id='object'+str(n),kind='bed',region='front_left',yaw_deg=0,
                            observation_ids=['bed_visual']) for n in range(3)]
        good=deepcopy(bad);good['room'].update(width_m=8,length_m=8)
        for n,row in enumerate(good['objects']):
            row['region']=('front_left','middle_right','rear_left')[n]
        before=deepcopy(bad)
        result,transport=self.run_pipeline([bad,good])
        self.assertEqual(result.plan.calls[0].arguments['size_m'],[8,8])
        self.assertEqual(bad,before)
        self.assertEqual(result.provider_provenance['reliability']['repair_count'],1)
        feedback=json.loads(transport.bodies[-1]['messages'][-1]['content'])
        self.assertFalse(feedback['layout_packing']['floor_must_not_expand'])
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual({c.arguments['id'] for c in result.plan.calls[4:]},
                         {'object0','object1','object2'})

    def test_generic_backtracking_reconsiders_earlier_placements(self):
        value=intent(object_intent('alpha','desk','front_left',size=[1.1,.6,.8]),
            object_intent('beta','desk','front_left',size=[.9,.5,.8]),
            object_intent('gamma','box','front_left',size=[.3,.3,.3]),width=2.5,length=2.5)
        before=deepcopy(value)
        payload,trace=compile_layout(value,observation(),request('An approximate room'),None)
        self.assertEqual(trace['bounded_packing_search']['status'],'FOUND')
        self.assertLessEqual(trace['bounded_packing_search']['nodes'],512)
        self.assertEqual(value,before)
        self.assertEqual({c['arguments']['id'] for c in payload['calls'][4:]},
                         {'alpha','beta','gamma'})
        self.assertFalse(trace['physical_authority'])

    def test_explicit_room_dimensions_cannot_be_changed_by_repair(self):
        value=layout();value['room'].update(width_m=5,length_m=5)
        with self.assertRaisesRegex(ValueError,'DIMENSIONS_CHANGED'):
            compile_layout(value,observation(),request('Room 4 by 5 metres'),None)

    def test_failed_packing_keeps_shared_repair_limit(self):
        value=layout();value['room'].update(width_m=2,length_m=2)
        value['objects']=[dict(id='large'+str(n),kind='bed',region='front_left',yaw_deg=0,
                              observation_ids=['bed_visual']) for n in range(3)]
        transport=ScriptedTransport(completion('obs',OBSERVER_MODEL,observation().to_dict()),
            completion('bad',PLANNER_MODEL,value),completion('same_bad',PLANNER_MODEL,value))
        provider=NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1,compact_photo_layout=True)
        with self.assertRaises(InvalidProviderResponseError):
            asyncio.run(GenerationService(provider,config(timeout_s=10),plan_version='2.2')
                .generate(request('An approximate room')))
        self.assertEqual(len(transport.bodies),3)
        self.assertEqual(provider.diagnostic_for('compact-test')['repair_count'],1)

    def test_invalid_support_remains_invalid_without_known_photo_constraints(self):
        value=intent(object_intent('bad_desk','desk',relation='surface',parent='other',part='body'),
                     object_intent('other','wardrobe'))
        with self.assertRaisesRegex(ValueError,'furniture must be floor-standing'):
            compile_layout(value,observation(),request('An approximate room'),None)


if __name__=='__main__':unittest.main()
