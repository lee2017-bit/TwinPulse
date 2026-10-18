# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary fault regression; not actual browser/model acceptance."""
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.command_broker import BrokerError


class ConversationPreservationTests(unittest.TestCase):
    def test_local_resume_preflight_retains_hash_bound_parent_not_fresh_input(self):
        with tempfile.TemporaryDirectory() as directory:
            approvals=SimpleNamespace(enabled=lambda:True,product_mode=True,
                checkpoint_for_approval=Mock(return_value=None),
                scope=Mock(return_value=SimpleNamespace(approval_id='new')))
            workflow=SimpleNamespace(_broker=SimpleNamespace(project_id='example'),select_input=Mock(),
                generation_approvals=approvals,start_generation=Mock(side_effect=
                    BrokerError('fixture_preflight','Explicit fixture failure',status=409)))
            service=ConversationService(workflow,Path(directory)/'example.conversation.json')
            service._state['pending_input']={'prompt':'synthetic input','name':None}
            service._state['generation']={'state':'failed','approval_id':'last',
                'progress':{'parent_checkpoint_id':'b'*64}}
            service._start_generation('resume-click',review_resume=True)
            approvals.scope.assert_called_once_with(checkpoint='b'*64)
            approvals.checkpoint_for_approval.assert_not_called()
            self.assertEqual(workflow.start_generation.call_args.kwargs['continuation_checkpoint'],'b'*64)
            self.assertEqual(service._state['generation']['progress']['checkpoint_id'],'b'*64)

    def test_resume_without_checkpoint_never_falls_through_to_fresh_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            approvals=SimpleNamespace(enabled=lambda:True,product_mode=True,
                checkpoint_for_approval=lambda _:None,scope=Mock())
            workflow=SimpleNamespace(_broker=SimpleNamespace(project_id='example'),
                select_input=Mock(),generation_approvals=approvals,start_generation=Mock())
            service=ConversationService(workflow,Path(directory)/'example.conversation.json')
            service._state['generation']={'state':'failed','approval_id':'previous'}
            previous=service._state['generation']
            with self.assertRaises(BrokerError) as raised:
                service._start_generation('resume-click',review_resume=True)
            self.assertEqual(raised.exception.code,'generation_checkpoint_unavailable')
            self.assertIs(service._state['generation'],previous)
            approvals.scope.assert_not_called();workflow.start_generation.assert_not_called()

    def test_resume_start_failure_preserves_checkpoint_progress_without_live_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow=SimpleNamespace(_broker=SimpleNamespace(project_id='example'),select_input=Mock(),
                start_generation=Mock(side_effect=BrokerError('fixture_preflight','Explicit fixture failure',status=409)))
            service=ConversationService(workflow,Path(directory)/'example.conversation.json')
            service._state['pending_input']={'prompt':'synthetic input','name':None}
            service._state['generation']={'state':'failed','progress':{'checkpoint_id':'a'*64,
                'generation_preview':{'state':'ready','rendered_count':1},
                'generation_activity':{'schema_version':'generation-activity-1.0','stage':'render_review','phase':'ready'},
                'retention_revalidation':{'validation':'passed'}}}
            service._start_generation('resume-click',inference_scope=SimpleNamespace(approval_id='new'),
                continuation_checkpoint='a'*64,review_resume=True)
            job=service._state['generation']
            self.assertEqual(job['state'],'failed')
            self.assertEqual(job['progress']['checkpoint_id'],'a'*64)
            self.assertEqual(job['progress']['generation_preview']['rendered_count'],1)
            self.assertEqual(job['progress']['generation_preview']['state'],'blocked')
            self.assertEqual(job['progress']['generation_activity'],{
                'schema_version':'generation-activity-1.0','stage':'resume_revalidation','phase':'validating'})
            self.assertNotIn('retention_revalidation',job['progress'])

    def test_invalid_history_cannot_be_replaced_by_polling_or_transaction_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'example.conversation.json'
            original=b'[]';path.write_bytes(original)
            workflow=SimpleNamespace(_broker=SimpleNamespace(project_id='example'),
                scene_edit_transaction=SimpleNamespace(snapshot=lambda owner:None),snapshot=lambda:{})
            service=ConversationService(workflow,path)
            with patch.object(service,'_sync_feedback') as sync:
                for _ in range(3):
                    self.assertEqual(service.snapshot()['restore_error']['code'],'conversation_restore_invalid')
                with self.assertRaises(BrokerError):service.dispatch({'action':'cancel'})
                sync.assert_not_called()
            with self.assertRaises(BrokerError):service._persist()
            self.assertEqual(path.read_bytes(),original)
