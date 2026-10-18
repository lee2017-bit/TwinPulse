# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic prompt/format boundaries only; fixtures are not model acceptance."""
from copy import deepcopy
import unittest

from scripts.evaluate_vision_model_selection import format_observer_body, observer_body
from packages.twinpulse_provider.tests.test_nebius_pipeline import (
    request,ScriptedTransport,OBSERVER_MODEL,PLANNER_MODEL,
)
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider


class VisionComparisonFormatTests(unittest.TestCase):
    def setUp(self):
        self.provider=NebiusChatCompletionsPipelineProvider(ScriptedTransport(),
            observer_model_id=OBSERVER_MODEL,planner_model_id=PLANNER_MODEL,site_plan_version='2.2')
        self.original=self.provider.build_observer_body(request())

    def test_strict_mode_is_the_exact_existing_product_request(self):
        self.assertEqual(observer_body(self.provider,request(),'strict'),self.original)

    def test_json_and_instance_preserve_identity_image_and_original(self):
        before=deepcopy(self.original)
        for mode in ('json_object','instance'):
            result=format_observer_body(self.original,mode)
            self.assertEqual(result['model'],self.original['model'])
            self.assertEqual(result['messages'][1:],self.original['messages'][1:])
            self.assertEqual(result['response_format'],{'type':'json_object'})
            self.assertEqual(result['max_tokens'],self.original['max_tokens'])
            self.assertEqual(self.original,before)

    def test_repair_transformation_preserves_alternating_roles_and_feedback(self):
        body=deepcopy(self.original)
        body['messages'] += [{'role':'assistant','content':'invalid fixture'},
                             {'role':'user','content':'correct generic contract errors'}]
        result=format_observer_body(body,'instance')
        self.assertEqual(result['messages'][1:],body['messages'][1:])
        self.assertEqual([x['role'] for x in result['messages']],['system','user','assistant','user'])


if __name__=='__main__':unittest.main()
