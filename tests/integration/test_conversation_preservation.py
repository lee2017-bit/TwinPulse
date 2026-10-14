# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary fault regression; not actual browser/model acceptance."""
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.command_broker import BrokerError


class ConversationPreservationTests(unittest.TestCase):
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
