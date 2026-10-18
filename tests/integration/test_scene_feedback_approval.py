# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Normal authenticated feedback approval and audited fake HTTP, paid 0."""
from copy import deepcopy
from datetime import datetime,timezone
from threading import Event
import json
import time
import unittest
from unittest.mock import patch

from tests.integration import test_generation_approval as generation_tests
from tests.integration import test_stage_routing_settings as routing_tests
from tests.integration.test_stage_routing_settings import Credential
from tests.integration.test_dependency_scene_changes import partial_source,edit,item,relation,patch as dependency_patch
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.command_broker import BrokerError
from twinpulse_core import canonical_sha256
from twinpulse_provider import ProviderConfigurationError
from twinpulse_provider.generation_policy import GenerationPolicy


class SceneFeedbackApprovalTests(unittest.TestCase):
    request=generation_tests.GenerationApprovalTests.request
    product_headers=generation_tests.GenerationApprovalTests.product_headers
    call=generation_tests.GenerationApprovalTests.call
    approve=generation_tests.GenerationApprovalTests.approve
    install_audited_fixture=generation_tests.GenerationApprovalTests.install_audited_fixture
    install_physical_catalog=routing_tests.StageSettingsTests.install_physical_catalog

    def setUp(self):
        generation_tests.GenerationApprovalTests.setUp(self)
        self.install_physical_catalog()
        self.route=self.registry.state()['stage_routing']['recommended']
        self.routes.save(self.route,lambda:None)
        self.manager.clock=lambda:datetime.now(timezone.utc)
        source=partial_source();app=self.workflow._application
        record=ProjectRecord('default',source.input_revision,site_draft=source)
        app._artifact_store.save(source.input_revision,())
        app._project_store.save(record);app._project=record
        self.workflow._phase='restore_review_required'
        self.workflow.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
        self.responses=[self.proposal]
        self.install_audited_fixture()
        self.factory=patch('twinpulse_app.stage_routing.build_configured_stage_service',return_value=self.service)
        self.factory.start();Credential.reads=[]

    def tearDown(self):
        worker=self.server.conversation._feedback_worker
        if worker:worker.join(3)
        self.factory.stop()
        generation_tests.GenerationApprovalTests.tearDown(self)

    @staticmethod
    def proposal(body):
        context=json.loads(body['messages'][-1]['content'])
        return dict(schema_version='scene-edit-proposal-1.1',context_sha256=context['context_sha256'],mode='dependency',
            explanation='Restore the retained item on its checked support.',patch=dependency_patch(edit('restore','item_0',
                tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support'))))

    def begin(self):
        return self.call(dict(action='message',request_id='feedback',text='Please restore the retained item on its support.',mode='new',attachment=None))

    def finish(self):
        worker=self.server.conversation._feedback_worker
        if worker:worker.join(3)
        return self.call()

    def test_approval_before_key_read_exact_super_wire_and_single_request_ledger(self):
        state=self.begin();preview=state['cards'][-1]['generation_approval']
        self.assertTrue(state['cards'][-1]['scene_feedback'])
        self.assertEqual(preview['planned_requests'],1);self.assertEqual(preview['image_count'],0)
        self.assertEqual(preview['models'][0]['model_id'],'nvidia/nemotron-3-super-120b-a12b')
        self.assertEqual(preview['models'][0]['max_output_tokens'],40000)
        self.assertEqual(preview['policy']['per_call_timeout_s'],300)
        self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.call();self.assertEqual(self.wires,[])
        action=self.approve(state,request_id='approved-feedback');self.call(action);state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'preview',state['messages'][-1])
        lineage=state['scene_edit_preview']['feedback_lineage']
        self.assertEqual(lineage['feedback_approval_id'],state['scene_feedback']['approval_id'])
        self.assertEqual(lineage['feedback_execution_id'],state['scene_feedback']['execution_id'])
        self.assertEqual(lineage['feedback_request_id'],'approved-feedback')
        self.assertEqual(len(self.wires),1)
        wire=self.wires[0];self.assertEqual(wire['model'],'nvidia/nemotron-3-super-120b-a12b')
        self.assertEqual(wire['max_tokens'],40000)
        self.assertEqual(wire['response_format']['json_schema']['name'],'twinpulse_scene_feedback')
        schema=wire['response_format']['json_schema']['schema']
        context=json.loads(wire['messages'][-1]['content'])
        self.assertEqual(schema['properties']['context_sha256']['enum'],[context['context_sha256']])
        edits=schema['properties']['patch']['anyOf'][0]['properties']['edits']['items']['anyOf']
        restore=next(e for e in edits if e['properties']['action']['enum']==['restore'])
        self.assertEqual(restore['properties']['target_id']['enum'],['item_0'])
        self.assertIn('never tool_call.call_id',wire['messages'][0]['content'])
        self.assertIn('each target_id appears exactly once',wire['messages'][0]['content'])
        self.assertIn('unchanged placement',schema['properties']['patch']['anyOf'][0]['properties']['edits']['description'])
        self.assertNotIn('data:image',json.dumps(wire));self.assertNotIn('chat_template_kwargs',wire)
        self.assertNotIn('max_completion_tokens',wire)
        self.call(action);self.call();self.assertEqual(len(self.wires),1)
        ledger_path=next(self.manager.root.glob('*.ledger.json'))
        ledger=json.loads(ledger_path.read_text());self.assertEqual(len(ledger['requests']),1)
        self.assertEqual(ledger['max_requests'],1)
        self.assertEqual(ledger['requests'][0]['status'],'received')
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        saved=json.loads(next(self.manager.root.glob('*.ordinary-scope.json')).read_text())
        self.assertEqual(saved['dispatch_request_limit'],1)
        self.assertFalse(state['physical_authority'])

    def test_stale_approved_context_or_preview_never_sends_http(self):
        state=self.begin();approval=state['cards'][-1]['generation_approval']
        from tests.integration.test_dependency_scene_changes import preview as scene_preview
        store=self.workflow._application.scene_change_store()
        value=scene_preview(store.load(),store.source,'pending-only',edit('defer','item_0'))
        history=store.apply(value['operation'],value['preview_digest']);self.workflow._publish_scene_change(store,history)
        status,_,_=self.request('/v1/product/conversation',self.approve(state),headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.assertFalse(self.manager.root.exists())

    def test_nonapproved_route_fails_before_budget_grant_or_dispatch(self):
        self.route['planner']['max_output_tokens']=20000
        self.routes.save(self.route,lambda:None)
        status,_,_=self.request('/v1/product/conversation',dict(action='message',request_id='wrong-route',
            text='Restore the retained item.',mode='new',attachment=None),headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.assertFalse(self.manager.root.exists())

    def test_truncation_is_recorded_and_does_not_repair_or_apply(self):
        self.responses=['length'];state=self.begin();self.call(self.approve(state));state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertEqual(len(self.wires),1);self.assertIsNone(state['scene_edit_preview'])
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())
        ledger=json.loads(next(self.manager.root.glob('*.ledger.json')).read_text())
        self.assertEqual(len(ledger['requests']),1);self.assertEqual(ledger['requests'][0]['status'],'rejected')
        self.assertIsNotNone(ledger['requests'][0]['usage'])
        root=self.service._provider._transport.transports['planner'].evidence.root
        attempt=ledger['requests'][0]['attempt_id']
        record=json.loads(json.loads((root/'validations'/(attempt+'-scene_feedback.json')).read_text())['record_redacted'])
        self.assertEqual(record['validation'],'failed')
        self.assertEqual(record['validation_code'],'PROVIDER_OUTPUT_TRUNCATED')
        self.assertIsNone(record['candidate'])

    def test_wrong_sha_is_rejected_and_failed_validation_keeps_raw_usage(self):
        def wrong(body):
            result=self.proposal(body);result['context_sha256']='k'+result['context_sha256'][1:];return result
        self.assert_failed_feedback(wrong,'FEEDBACK_CONTEXT_MISMATCH')

    def test_call_id_is_not_repaired_into_object_id(self):
        def wrong(body):
            result=self.proposal(body)
            result['patch']['edits'][0]['target_id']=result['patch']['edits'][0]['tool_call']['call_id']
            self.assertNotEqual(result['patch']['edits'][0]['target_id'],'item_0')
            return result
        self.assert_failed_feedback(wrong,'FEEDBACK_OBJECT_IDENTITY_MISMATCH')

    def test_duplicate_target_different_reason_is_recorded_without_dedup_or_preview(self):
        def duplicate(body):
            result=self.proposal(body);second=deepcopy(result['patch']['edits'][0])
            second['reason']='Preserve the placement after the requested edit.'
            result['patch']['edits'].append(second);return result
        record=self.assert_failed_feedback(duplicate,'FEEDBACK_DUPLICATE_TARGET')
        self.assertEqual(len(record['candidate']['patch']['edits']),2)
        self.assertIn('item_0',record['validation_detail'])
        self.assertIn('edits[0] and edits[1]',record['validation_detail'])

    def test_duplicate_target_across_actions_is_not_sequential_execution(self):
        def duplicate(body):
            result=self.proposal(body);result['patch']['edits'].append(edit('defer','item_0'));return result
        record=self.assert_failed_feedback(duplicate,'FEEDBACK_DUPLICATE_TARGET')
        self.assertEqual([r['action'] for r in record['candidate']['patch']['edits']],['restore','defer'])

    def test_validation_evidence_storage_failure_blocks_preview_without_retry(self):
        state=self.begin()
        transport=self.service._provider._transport.transports['planner']
        with patch.object(transport,'record_validation',side_effect=OSError('fixture storage failure')):
            self.call(self.approve(state));state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertIn('evidence could not be persisted',state['scene_feedback']['error'])
        self.assertIsNone(state['scene_edit_preview']);self.assertEqual(len(self.wires),1)
        self.call();self.assertEqual(len(self.wires),1)
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())

    def test_cancel_after_transport_receipt_preserves_identity_usage_and_failed_validation(self):
        self.assert_cancelled_after_receipt('transport')

    def test_cancel_after_stage_receipt_still_blocks_preview_and_records_validation(self):
        self.assert_cancelled_after_receipt('stage')

    def assert_cancelled_after_receipt(self,boundary):
        receipt=Event();release=Event();provider=self.service._provider
        target=provider._transport.transports['planner'] if boundary=='transport' else provider
        method='complete' if boundary=='transport' else '_complete_stage'
        original=getattr(target,method)
        async def gated(*args,**kwargs):
            result=await original(*args,**kwargs)
            receipt.set()
            if not release.wait(3):raise AssertionError('fixture cancellation barrier timed out')
            return result
        state=self.begin()
        with patch.object(target,method,new=gated):
            try:
                state=self.call(self.approve(state))
                self.assertTrue(receipt.wait(3))
                self.call(dict(action='cancel',request_id='cancel-received-'+boundary,
                    operation_id=state['scene_feedback']['operation_id']))
            finally:release.set()
            state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'cancelled')
        self.assertIsNone(state['scene_edit_preview']);self.assertEqual(len(self.wires),1)
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())
        ledger=json.loads(next(self.manager.root.glob('*.ledger.json')).read_text())
        self.assertEqual(len(ledger['requests']),1);row=ledger['requests'][0]
        self.assertEqual(row['status'],'received');self.assertIsNotNone(row['usage'])
        diagnostic=provider.diagnostic_for(state['scene_feedback']['request_id'])
        attempt=diagnostic['attempts'][-1]
        self.assertEqual(attempt['attempt_id'],row['attempt_id']);self.assertEqual(attempt['status'],'received')
        self.assertEqual(attempt['usage'],row['usage']);self.assertTrue(attempt['ignored_by_host'])
        root=provider._transport.transports['planner'].evidence.root
        raw=json.loads((root/(row['attempt_id']+'.json')).read_text())
        validation=json.loads((root/'validations'/(row['attempt_id']+'-scene_feedback.json')).read_text())
        record=json.loads(validation['record_redacted'])
        self.assertEqual(record['validation'],'failed')
        self.assertEqual(record['validation_code'],'FEEDBACK_CANCELLED_AFTER_RECEIPT')
        self.assertTrue(record['response_received']);self.assertTrue(record['cancelled'])
        self.assertEqual(validation['execution_id'],raw['execution_id'])
        self.call();self.assertEqual(len(self.wires),1)
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def assert_failed_feedback(self,response,code):
        self.responses=[response];state=self.begin();self.call(self.approve(state));state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertEqual(len(self.wires),1);self.assertIsNone(state['scene_edit_preview'])
        self.assertEqual(self.workflow._application.scene_change_store().load().operations,())
        ledger=json.loads(next(self.manager.root.glob('*.ledger.json')).read_text())
        self.assertEqual(len(ledger['requests']),1);self.assertIsNotNone(ledger['requests'][0]['usage'])
        self.assertEqual(ledger['requests'][0]['status'],'received')
        transport=self.service._provider._transport.transports['planner'];root=transport.evidence.root
        attempt=ledger['requests'][0]['attempt_id']
        raw=json.loads((root/(attempt+'.json')).read_text())
        validation=json.loads((root/'validations'/(attempt+'-scene_feedback.json')).read_text())
        record=json.loads(validation['record_redacted'])
        self.assertEqual(record['validation'],'failed');self.assertEqual(record['validation_code'],code)
        self.assertEqual(record['candidate'],json.loads(json.loads(raw['response_redacted'])['choices'][0]['message']['content']))
        self.assertEqual(validation['execution_id'],raw['execution_id'])
        self.call();self.assertEqual(len(self.wires),1)
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])
        return record
