# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local regression only; live App/Isaac acceptance is recorded separately."""
import unittest
import json
from datetime import datetime,timezone
from uuid import uuid4
from dataclasses import replace
from pathlib import Path
from tests.integration.test_generation_approval import GenerationApprovalTests
from twinpulse_app.product_inference import ProductGenerationActions,ProductUsageLedger,ProductInferenceScope


class ProductInferenceTests(unittest.TestCase):
    setUp=GenerationApprovalTests.setUp
    tearDown=GenerationApprovalTests.tearDown
    call=GenerationApprovalTests.call
    request=GenerationApprovalTests.request
    product_headers=GenerationApprovalTests.product_headers
    answer=GenerationApprovalTests.answer
    install_audited_fixture=GenerationApprovalTests.install_audited_fixture
    finish=GenerationApprovalTests.finish

    def test_fresh_product_action_does_not_reuse_another_chats_observation(self):
        first=ProductInferenceScope('first-action','a'*64,'b'*64,'c'*64,
            Path('unused-fixture-ledger'),'first-project')
        second=replace(first,approval_id='second-action',project_id='second-project')
        self.assertNotEqual(first.cache_identity,second.cache_identity)
        self.assertEqual(first.cache_identity,replace(first).cache_identity)

    def test_direct_create_records_usage_without_price_or_amount(self):
        self.install_audited_fixture()
        self.manager=ProductGenerationActions(self.registry,self.workflow,
            clock=lambda:datetime(2030,1,1,tzinfo=timezone.utc),prices={})
        self.workflow.generation_approvals=self.manager
        first=self.call(dict(action='message',request_id=uuid4().hex,text='Create a bed in an estimated bedroom',mode='new',attachment=None))
        self.assertNotIn('generation_approval',first['cards'][-1])
        self.call(self.answer(first))
        final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertFalse(any(c['kind']=='generation_approval' for c in final['cards']))
        ledgers=list(self.manager.root.glob('*.ledger.json'))
        self.assertEqual(len(ledgers),1)
        usage=json.loads(ledgers[0].read_text())
        self.assertNotIn('limit_usd',usage)
        self.assertEqual(len(usage['requests']),3)
        self.assertTrue(all(r['usage']['total_tokens']==30 for r in usage['requests']))

    def test_late_completion_stays_linked_to_original_turn(self):
        conversation=self.server.conversation
        original=conversation._message('user','Create the room')
        conversation._state['generation']=dict(operation_id='original-job',origin_message_id=original['message_id'])
        conversation._message('user','Status?')
        completed=conversation._message('assistant','Room ready',operation_id='original-job')
        self.assertEqual(completed['reply_to'],original['message_id'])

    def test_late_edit_card_and_committed_message_keep_original_turn(self):
        service=self.server.conversation
        original=service._message('user','Move the desk')
        service._message('user','Status?')
        preview={'parent_revision':'a'*64,'operation':{'operation_id':'edit-original'}}
        service._offer_feedback_preview(preview,'Desk proposal',origin_message_id=original['message_id'])
        self.assertEqual(service._state['messages'][-1]['reply_to'],original['message_id'])
        service._state['pending_edit']=None
        service._message('user','Another status question')
        complete=service._message('assistant','Edit saved',operation_id='edit-original')
        self.assertEqual(complete['reply_to'],original['message_id'])

del GenerationApprovalTests  # Imported helpers are not additional test cases.
