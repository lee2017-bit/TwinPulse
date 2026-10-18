# SPDX-License-Identifier: Apache-2.0
"""Local atomic rename retries, not replay of product/robot requests."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.conversation_service import ConversationService


class ConversationRenameTests(unittest.TestCase):
    def service(self, directory):
        service=object.__new__(ConversationService)
        service.path=Path(directory)/'conversation.json';service._parent=Path(directory).resolve()
        service._state=dict(revision=1,project_id='test',mode='SIM')
        service._restore_error=None
        return service

    def sharing(self, code=32):
        error=PermissionError(13,'Synthetic bounded Windows sharing fault')
        error.winerror=code
        return error

    def test_retry_only_flushed_rename_preserves_exact_one_increment(self):
        with tempfile.TemporaryDirectory() as directory:
            service=self.service(directory)
            import os
            real_replace=os.replace
            for code in (5,32,33):
                count=0
                def replace(source,target):
                    nonlocal count
                    count+=1
                    if count<3:raise self.sharing(code)
                    return real_replace(source,target)
                before=service._state['revision']
                with patch('twinpulse_app.conversation_service.os.replace',side_effect=replace),patch('twinpulse_app.conversation_service.time.sleep') as sleep:
                    service._persist()
                self.assertEqual(count,3);self.assertEqual(service._state['revision'],before+1)
                self.assertEqual(json.loads(service.path.read_text())['revision'],before+1)
                self.assertEqual([call.args[0] for call in sleep.call_args_list],[.01,.02])

    def test_exhausted_retry_keeps_original_and_temp_with_safe_error_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            service=self.service(directory);service.path.write_text('{"original":true}')
            with patch('twinpulse_app.conversation_service.os.replace',side_effect=self.sharing(32)) as rename,patch('twinpulse_app.conversation_service.time.sleep') as sleep:
                with self.assertRaises(BrokerError):service._persist()
            self.assertEqual(rename.call_count,5)
            self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list),.15)
            self.assertEqual(json.loads(service.path.read_text()),{'original':True})
            self.assertTrue(service.path.with_name('conversation.json.tmp').is_file())
            self.assertEqual(service._restore_error['storage_winerror'],32)

    def test_other_error_no_retry_and_success_clears_only_save_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            service=self.service(directory)
            with patch('twinpulse_app.conversation_service.os.replace',side_effect=OSError(28,'full')) as rename:
                with self.assertRaises(BrokerError):service._persist()
                self.assertEqual(rename.call_count,1)
            service._persist();self.assertIsNone(service._restore_error)
            service._restore_error=dict(code='conversation_restore_invalid',message='preserve invalid history')
            with patch('twinpulse_app.conversation_service.os.replace') as rename:
                with self.assertRaises(BrokerError):service._persist()
                rename.assert_not_called()


if __name__=='__main__':unittest.main()
