# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Product-mode App/real compiler with audited fake HTTP; not user acceptance."""
from copy import deepcopy
import json
import unittest

from tests.integration import test_scene_feedback_approval as base
from tests.integration.test_dependency_scene_changes import edit,patch
from twinpulse_app.product_inference import ProductGenerationActions


class ProductFeedbackPoseRepairTests(unittest.TestCase):
    request=base.SceneFeedbackApprovalTests.request
    product_headers=base.SceneFeedbackApprovalTests.product_headers
    call=base.SceneFeedbackApprovalTests.call
    install_physical_catalog=base.SceneFeedbackApprovalTests.install_physical_catalog
    install_audited_fixture=base.SceneFeedbackApprovalTests.install_audited_fixture
    proposal=staticmethod(base.SceneFeedbackApprovalTests.proposal)
    finish=base.SceneFeedbackApprovalTests.finish

    def setUp(self):
        base.SceneFeedbackApprovalTests.setUp(self)
        self.manager=ProductGenerationActions(self.registry,self.workflow)
        self.workflow.generation_approvals=self.manager

    def tearDown(self):base.SceneFeedbackApprovalTests.tearDown(self)

    @staticmethod
    def response(x):
        def make(body):
            context=json.loads(body['messages'][1]['content'])
            call=deepcopy(next(c for c in context['current_plan']['calls'] if c['arguments']['id']=='support'))
            call['arguments']['center_m']=[x,0]
            return dict(schema_version='scene-edit-proposal-1.1',context_sha256=context['context_sha256'],mode='dependency',
                explanation='Move only the saved support, preserving pending items.',patch=patch(edit('change','support',tool_call=call)))
        return make

    def begin(self):
        return self.call(dict(action='message',request_id='product-feedback',text='Move only the support to the right; preserve size and pending items.',mode='new',attachment=None))

    def test_typed_candidate_compile_repairs_then_preview_without_apply(self):
        self.responses=[self.response(5),self.response(.2)]
        self.begin();state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'preview',state['scene_feedback'])
        self.assertEqual(len(self.wires),2)
        self.assertIn('candidate_geometry_error',self.wires[1]['messages'][-1]['content'])
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())
        ledger=json.loads(next(self.manager.root.glob('*.ledger.json')).read_text())
        self.assertEqual(len(ledger['requests']),2)
        self.assertEqual(state['scene_feedback']['progress']['budget']['repairs'],1)
        self.assertFalse(state['physical_authority'])

    def test_other_candidate_errors_never_receive_geometry_retry_authority(self):
        self.responses=[self.response(100)] # prototype coordinate bounds, not floor predicate
        self.begin();state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertEqual(len(self.wires),1)
        self.assertIsNone(state['scene_edit_preview'])
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())


if __name__=='__main__':unittest.main()
