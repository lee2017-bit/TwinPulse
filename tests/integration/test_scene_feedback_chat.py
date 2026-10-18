# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Ordinary chat -> scripted proposal -> actual broker ACK -> durable history.

Explicit local proposal fixture, never a fresh inference/photo acceptance.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch as mock_patch

from tests.integration.test_scene_edit_transaction import workflow,attach,claim,acknowledge
from tests.integration.test_dependency_scene_changes import edit,item,relation,patch,preview
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.command_broker import BrokerError
from twinpulse_provider import SceneEditProposalService,ProviderConfig,ProviderCapabilities,ProviderResponse


class ScriptedProvider:
    def __init__(self,*,clarify=0,delay=0):
        self.requests=[];self.clarify=clarify;self.delay=delay

    async def generate(self,request,token,config):
        context=json.loads(request.prompt);self.requests.append(request)
        await asyncio.sleep(self.delay)
        clarifying=len(self.requests)<=self.clarify
        value=dict(schema_version='scene-edit-proposal-1.1',context_sha256=context['context_sha256'],
            mode='clarify' if clarifying else 'dependency',
            explanation='Which retained item should be restored?' if clarifying else 'Restore the retained item on its checked parent.',
            patch=None if clarifying else patch(edit('restore','item_0',
                tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support'))))
        return ProviderResponse(request.request_id,value,'explicit-scripted-feedback',config.model_id)


class SceneFeedbackChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.product=workflow(self.root);attach(self.product)
        self.provider=ScriptedProvider()
        self.configure()
        self.chat=ConversationService(self.product,self.root/'chat.json')

    def configure(self):
        config=ProviderConfig(base_url='https://example.invalid/v1/',endpoint_path='responses',model_id='offline',
            api_key_env='UNUSED',capabilities=ProviderCapabilities(False,True),timeout_s=2)
        self.product.scene_edit_proposal_service=SceneEditProposalService(self.provider,config)

    def tearDown(self):
        if self.chat._feedback_worker:self.chat._feedback_worker.join(3)
        if self.product.scene_edit_transaction.worker:self.product.scene_edit_transaction.worker.join(3)
        self.product._application.diagnostics.flush()
        self.temp.cleanup()

    def send(self,text,request='message'):
        return self.chat.dispatch(dict(action='message',request_id=request,text=text,mode='new',attachment=None),'owner')

    def finish(self):
        self.chat._feedback_worker.join(3)
        self.assertFalse(self.chat._feedback_worker.is_alive())
        return self.chat.snapshot('owner')

    def answer(self,state,choice,request='choice'):
        card=next(c for c in state['cards'] if c['state']=='waiting')
        return self.chat.dispatch(dict(action='answer',request_id=request,card_id=card['id'],choice_id=choice,
            expected_session_revision=card['expected_session_revision']),'owner')

    def test_ordinary_text_current_context_cancel_does_not_build(self):
        source=self.product._application.site_draft.to_dict()
        self.send('Please put the missing item back onto the support.')
        state=self.finish();self.assertEqual(state['scene_feedback']['state'],'preview')
        self.assertFalse(any(m['status']=='pending' and m.get('operation_id')==state['scene_feedback']['operation_id'] for m in state['messages']))
        context=json.loads(self.provider.requests[0].prompt)
        self.assertEqual(context['schema_version'],'scene-edit-context-1.2')
        self.assertEqual(context['original_user_intent'],self.product._application.site_draft.input_revision.prompt)
        self.assertIn('current_state_sha256',context);self.assertEqual(len(context['unresolved']),1)
        self.assertFalse(self.provider.requests[0].images)
        self.assertEqual(state['scene_edit_preview']['apply_version'],'scene-edit-apply-2.0')
        self.answer(state,'cancel')
        self.assertEqual(self.product._application.scene_change_store().load().operations,())
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.assertEqual(self.product._application.site_draft.to_dict(),source)
        self.assertEqual(len(self.provider.requests),1)

    def test_confirmed_edit_history_does_not_reopen_when_viewer_becomes_stale(self):
        transaction=dict(operation_id='edit_display',state='COMMITTED',current_frame=False,error=None)
        with mock_patch.object(self.product.scene_edit_transaction,'snapshot',return_value=transaction):
            self.chat._sync_feedback('owner')
            waiting=[m for m in self.chat._state['messages'] if m.get('operation_id')=='edit_display']
            self.assertEqual(len(waiting),1);self.assertEqual(waiting[0]['status'],'pending')
            transaction['current_frame']=True
            self.chat._sync_feedback('owner')
            confirmed=deepcopy(self.chat._state['messages'])
            self.assertFalse(any(m['status']=='pending' for m in confirmed))
            transaction['current_frame']=False
            self.chat._sync_feedback('owner')
            self.assertEqual(self.chat._state['messages'],confirmed)
            # A reopened chat must recognize persisted confirmation too.
            self.chat._edit_transaction_marker=None
            self.chat._sync_feedback('owner')
            self.assertEqual(self.chat._state['messages'],confirmed)

    def test_old_waiting_rows_settle_only_for_the_same_confirmed_operation(self):
        self.chat._message('assistant','Twin updated, saved and its current 3D frame confirmed.',operation_id='edit_old')
        self.chat._message('assistant','Historical display wait',status='pending',operation_id='edit_old')
        self.chat._message('assistant','Unrelated active wait',status='pending',operation_id='edit_other')
        with mock_patch.object(self.product.scene_edit_transaction,'snapshot',return_value=None):
            self.chat._sync_feedback('owner')
        self.assertEqual(self.chat._state['messages'][-2]['status'],'completed')
        self.assertEqual(self.chat._state['messages'][-1]['status'],'pending')

    def test_same_revision_build_pending_rejects_before_message_or_provider_then_manual_send_works(self):
        before=self.chat.snapshot('owner')
        broker=self.product._broker;artifact=self.product._site_artifact
        broker.submit('owner',dict(client_request_id='view_current',command_type='build_site_scene',
            artifact_id=artifact.artifact_id,expected_applied_revision=artifact.revision))
        command=claim(broker)
        self.assertEqual(broker.public_state('owner')['snapshot']['applied_revision'],artifact.revision)
        with self.assertRaisesRegex(BrokerError,'CURRENT_ENGINE_COMMAND_PENDING') as failed:
            self.send('Please restore the retained item.','busy-message')
        self.assertEqual(failed.exception.code,'scene_edit_unavailable')
        rejected=self.chat.snapshot('owner')
        self.assertEqual(rejected['messages'],before['messages'])
        self.assertNotIn('busy-message',rejected['accepted_request_ids'])
        self.assertEqual(self.provider.requests,[])
        acknowledge(broker,command)
        self.assertFalse(broker.has_pending_operations())
        self.assertEqual(self.provider.requests,[]) # ACK/poll never resends the feedback.
        self.send('Please restore the retained item.','manual-message')
        state=self.finish();self.assertEqual(state['scene_feedback']['state'],'preview')
        self.assertEqual(len(self.provider.requests),1)

    def test_unavailable_edit_predicates_remain_closed_and_distinguishable(self):
        for name,value,code in (('_phase','restore_review_required','CURRENT_REVIEW_REQUIRED'),
                ('_input',None,'CURRENT_INPUT_REQUIRED'),('_site_artifact',None,'CURRENT_ARTIFACT_REQUIRED'),
                ('_workers',{object()},'CURRENT_GENERATION_PENDING'),
                ('_derived_revision','derived','DERIVED_REVIEW_BRANCH_ACTIVE')):
            with self.subTest(predicate=code),mock_patch.object(self.product,name,value),\
                    self.assertRaisesRegex(BrokerError,code) as failed:
                self.product.scene_edit_context('Change only the current item.',None,dependency=True)
            self.assertEqual(failed.exception.code,'scene_edit_unavailable')
        self.assertEqual(self.provider.requests,[])
        self.assertFalse(self.product._broker.has_pending_operations())

    def test_apply_ack_save_current_frame_undo_and_closed_chat_reopen(self):
        original=self.product._site_artifact.revision
        self.send('Please restore that item.');state=self.finish()
        lineage=deepcopy(state['scene_edit_preview']['feedback_lineage'])
        applied_operation=state['scene_edit_preview']['operation']['operation_id']
        feedback_id=state['scene_feedback']['execution_id']
        self.assertEqual(lineage['feedback_execution_id'],feedback_id)
        self.assertNotEqual(lineage['feedback_preview_execution_id'],feedback_id)
        # Reopen the pending review first: provenance is durable, not just the
        # currently running feedback job or an in-memory operation lookup.
        self.chat=ConversationService(self.product,self.root/'chat.json')
        state=self.chat.snapshot('owner')
        self.assertEqual(state['scene_edit_preview']['feedback_lineage'],lineage)
        applied=self.answer(state,'apply');self.assertIsNone(applied['scene_edit_preview'])
        command=claim(self.product._broker)
        self.assertEqual(self.product._application.scene_change_store().load().operations,())
        acknowledge(self.product._broker,command);self.product.scene_edit_transaction.worker.join(3)
        self.product._broker.record_current_frame('engine','stage',command.expected_applied_revision,'frame','a'*64)
        state=self.chat.snapshot('owner');self.assertTrue(state['scene_edit_transaction']['current_frame'])
        self.assertEqual(state['scene_edit_transaction']['state'],'COMMITTED')
        self.assertFalse(any(m['status']=='pending' and m.get('operation_id')==applied_operation for m in state['messages']))
        transaction=self.product.scene_edit_transaction
        self.assertEqual(transaction.value['feedback_lineage'],lineage)
        self.assertTrue(self.product._application.diagnostics.flush())
        diagnostics=self.product._application.diagnostics
        detail=diagnostics.detail(transaction.value['execution_id'])
        root=next(span for span in detail['spans'] if span['span_id']==detail['manifest']['root_span_id'])
        self.assertEqual(root['metadata']['feedback_execution_id'],feedback_id)
        self.assertEqual(root['metadata']['feedback_response_sha256'],lineage['feedback_response_sha256'])
        graph=diagnostics.graph(transaction.value['execution_id'])
        self.assertTrue(any(edge['target']==feedback_id and edge['relation']=='feedback_execution_id' for edge in graph['edges']))
        refs=self.product._broker.artifact_diagnostic_refs(self.product._site_artifact.artifact_id)
        self.assertEqual(refs['feedback_execution_id'],feedback_id)
        self.assertIsNone(state['simulation_review'])
        self.send('Undo','undo-message');undo_state=self.chat.snapshot('owner')
        self.assertEqual(len(self.provider.requests),1)
        self.assertNotEqual(undo_state['scene_edit_preview']['result_revision'],original)
        from twinpulse_core import canonical_sha256
        missing_sha=deepcopy(undo_state['scene_edit_preview']['operation'])
        missing_sha.pop('parent_state_sha256');missing_sha.pop('result_state_sha256')
        with self.assertRaises(BrokerError):self.product.scene_edit_transaction.start('owner',missing_sha,canonical_sha256(missing_sha))
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.answer(undo_state,'apply','undo-apply');undo=claim(self.product._broker)
        acknowledge(self.product._broker,undo);self.product.scene_edit_transaction.worker.join(3)
        self.product._broker.record_current_frame('engine','stage',undo.expected_applied_revision,'undo-frame','b'*64)
        self.chat.snapshot('owner')
        reopened=ConversationService(self.product,self.root/'chat.json')
        state=reopened.snapshot('owner');self.assertIsNone(state['restore_error'])
        self.assertEqual(state['scene_edit_transaction']['state'],'COMMITTED')
        archive=transaction.path.with_name(transaction.path.stem+'.history')/(applied_operation+'.json')
        self.assertEqual(json.loads(archive.read_text(encoding='utf-8'))['feedback_lineage'],lineage)
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.assertEqual(self.product._application.scene_change_store().load().effective(
            self.product._application.site_draft).progressive(self.product._application.site_draft)['unresolved'][0]['id'],'item_0')

    def test_one_clarification_human_reply_returns_preview(self):
        self.provider.clarify=1
        self.send('Put it back.');state=self.finish()
        self.assertEqual(state['cards'][-1]['kind'],'scene_edit_clarify')
        self.assertEqual(state['cards'][-1]['question'].count('?'),1)
        self.send('The retained item_0 on support.','reply');state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'preview')
        self.assertEqual(state['scene_feedback']['clarification_count'],1)
        self.assertIn('Human answer:',json.loads(self.provider.requests[1].prompt)['request_text'])
        self.assertEqual(sum(c['kind']=='scene_edit_clarify' for c in state['cards']),1)
        self.assertEqual(len(self.provider.requests),2)
        self.assertIsNone(self.product._broker.claim('engine','stage'))

    def test_second_clarification_stops_without_a_question_loop(self):
        self.provider.clarify=2
        self.send('Put it back.');self.finish()
        self.send('That one.','reply');state=self.finish()
        self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertFalse(any(c['state']=='waiting' for c in state['cards']))
        self.assertEqual(sum(c['kind']=='scene_edit_clarify' for c in state['cards']),1)
        self.assertEqual(self.product._application.scene_change_store().load().operations,())

    def test_late_proposal_and_clarification_state_changes_fail_closed(self):
        self.provider.delay=.06
        self.send('Restore the item.')
        store=self.product._application.scene_change_store()
        value=preview(store.load(),store.source,'outside',edit('defer','item_0'))
        history=store.apply(value['operation'],value['preview_digest'])
        self.product._publish_scene_change(store,history)
        state=self.finish();self.assertEqual(state['scene_feedback']['state'],'failed')
        self.assertIsNone(state['scene_edit_preview']);self.assertEqual(len(self.provider.requests),1)
        self.assertIsNone(self.product._broker.claim('engine','stage'))

    def test_busy_duplicate_cancel_and_restart_never_reinvoke_provider(self):
        self.provider.delay=.12
        body=dict(action='message',request_id='same',text='Restore that retained item.',mode='new',attachment=None)
        state=self.chat.dispatch(body,'owner');self.chat.dispatch(body,'owner')
        with self.assertRaises(BrokerError):self.send('Another change','other')
        self.chat.dispatch(dict(action='cancel',request_id='stop',operation_id=state['scene_feedback']['operation_id']),'owner')
        state=self.finish();self.assertEqual(state['scene_feedback']['state'],'cancelled')
        self.assertFalse(any(m['status']=='pending' and m.get('operation_id')==state['scene_feedback']['operation_id'] for m in state['messages']))
        self.assertIsNone(state['scene_edit_preview']);self.assertEqual(len(self.provider.requests),1)
        reopened=ConversationService(self.product,self.root/'chat.json')
        self.assertIsNone(reopened.snapshot('owner')['restore_error'])
        self.assertEqual(len(self.provider.requests),1)
