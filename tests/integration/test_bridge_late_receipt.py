# SPDX-License-Identifier: Apache-2.0
"""Real authenticated HTTP delivery; fake clock/adapter, never Kit or hardware."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests.integration.test_bridge_lease_rotation import BridgeClient
from tests.integration.test_r4_bridge_api import FakeClock
from twinpulse_app import CommandBroker, LocalApiServer, BrokerError
from twinpulse_core import CommandReceipt, SimulationSnapshot, fixed_warehouse_bundle
from twinpulse_core.execution_diagnostics import ExecutionStore


class LateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.clock=FakeClock();self.broker=CommandBroker(clock=self.clock)
        self.store=ExecutionStore(Path(self.folder.name)/'diagnostics','default')
        self.broker.diagnostics=self.store
        self.server=LocalApiServer(self.broker,product_bootstrap_secret='p'*43,
            engine_bootstrap_secret='e'*43,clock=self.clock)
        self.server.start();self.addCleanup(self.server.stop)
        self.client=BridgeClient(SimpleNamespace(engine_session_id='engine',stage_epoch='stage'),
            base_url=self.server.base_url,bootstrap_secret='e'*43,clock=self.clock)
        self.client._bootstrap()
        self.artifact=self.broker.register_artifact('fixture',fixed_warehouse_bundle())
        self.broker.acquire_lease('owner')
        self.operation=self.broker.submit('owner',dict(client_request_id='original',
            command_type='build_scene',artifact_id='fixture',expected_applied_revision=self.artifact.revision))
        self.command=self.broker.claim('engine','stage')
        self.late=CommandReceipt(self.command.command_id,'build_scene','default','engine','stage',
            'succeeded',applied_revision=self.artifact.revision)
        self.clock.advance(3.1)
        self.original=self.broker.public_state('owner')['operations'][0]['receipt']
        self.assertEqual(self.original['status'],'unknown')
        self.assertFalse(self.broker.public_state('owner')['lease_owned'])
        self.broker.engine_heartbeat('engine','stage')

    def tearDown(self):
        self.store.flush()

    def test_late_ack_is_durable_unknown_unchanged_then_snapshot_and_explicit_new_build(self):
        self.client._outgoing.append(self.late)
        self.client._flush_receipts()
        self.assertFalse(self.client._outgoing)
        current=self.broker.public_state('owner')
        self.assertEqual(current['operations'][0]['receipt'],self.original)
        self.assertFalse(current['lease_owned'])
        paths=list((self.store.root/'late-engine-receipts').glob('*.json'))
        self.assertEqual(len(paths),1)
        evidence=json.loads(paths[0].read_text())
        self.assertEqual(evidence['original_receipt'],self.original)
        self.assertEqual(evidence['late_receipt'],self.late.to_dict())
        # Delivery retry is idempotent, no authority or evidence rewrite.
        original=paths[0].read_bytes();self.client._outgoing.append(self.late)
        self.client._flush_receipts();self.assertEqual(paths[0].read_bytes(),original)
        self.client._latest_snapshot=SimulationSnapshot('engine','stage','default',
            self.artifact.revision,None,2,'built',None,None,('build_scene',),('simulation',))
        self.client._flush_snapshot()
        self.assertIsNone(self.client._latest_snapshot)
        self.assertEqual(self.broker.public_state('owner')['snapshot']['sequence'],2)
        self.assertIsNone(self.broker.claim('engine','stage'))
        self.broker.acquire_lease('owner')
        self.broker.submit('owner',dict(client_request_id='explicit-recovery',
            command_type='build_scene',artifact_id='fixture',expected_applied_revision=self.artifact.revision))
        fresh=self.broker.claim('engine','stage')
        self.assertNotEqual(fresh.command_id,self.command.command_id)
        self.broker.record_receipt(replace(self.late,command_id=fresh.command_id))
        old=next(v for v in self.broker.public_state('owner')['operations']
            if v['command_id']==self.command.command_id)
        self.assertEqual(old['receipt'],self.original)

    def test_wrong_identity_revision_and_different_late_result_do_not_pop(self):
        for receipt,code in ((replace(self.late,project_id='other'),'receipt_identity_mismatch'),
                             (replace(self.late,stage_epoch='other'),'receipt_identity_mismatch'),
                             (replace(self.late,applied_revision='f'*64),'receipt_revision_mismatch')):
            with self.subTest(code=code):
                with self.assertRaises(BrokerError) as caught:self.broker.record_receipt(receipt)
                self.assertEqual(caught.exception.code,code)
        self.broker.record_receipt(self.late)
        conflicting=replace(self.late,status='failed',error_code='actual_failure')
        self.client._outgoing.append(conflicting)
        with self.assertRaisesRegex(RuntimeError,'receipt_duplicate_conflict'):self.client._flush_receipts()
        self.assertEqual(list(self.client._outgoing),[conflicting])
        self.assertEqual(self.broker.public_state('owner')['operations'][0]['receipt'],self.original)

    def test_storage_error_keeps_head_and_unknown(self):
        self.client._outgoing.append(self.late)
        with patch('twinpulse_app.engine_receipt_evidence.os.fsync',side_effect=OSError('test storage fault')):
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError,'late_receipt_storage_failed'):self.client._flush_receipts()
        self.assertEqual(list(self.client._outgoing),[self.late])
        self.assertEqual(self.broker.public_state('owner')['operations'][0]['receipt'],self.original)

    def test_bridge_rejects_unbound_disposition(self):
        self.client._outgoing.append(self.late)
        for value in ({}, {'accepted':False}, dict(accepted=False,disposition='late_receipt_recorded',
                command_id='other',original_status='unknown',receipt_sha256='f'*64)):
            with patch.object(self.client,'_post',return_value=value):
                with self.assertRaisesRegex(RuntimeError,'disposition'):self.client._flush_receipts()
            self.assertEqual(list(self.client._outgoing),[self.late])

    def test_other_terminal_receipt_never_uses_quarantine(self):
        self.broker.acquire_lease('owner')
        new=self.broker.submit('owner',dict(client_request_id='cancelled',command_type='build_scene',artifact_id='fixture',expected_applied_revision=self.artifact.revision))
        self.broker.cancel('owner',new['command_id'])
        with self.assertRaises(BrokerError) as caught:
            self.broker.record_receipt(replace(self.late,command_id=new['command_id']))
        self.assertEqual(caught.exception.code,'receipt_duplicate_conflict')

    def test_replaced_engine_cannot_quarantine_an_old_receipt(self):
        self.broker.register_engine('replacement','new-stage')
        with self.assertRaises(BrokerError) as caught:self.broker.record_receipt(self.late)
        self.assertEqual(caught.exception.code,'receipt_identity_mismatch')
        self.assertFalse((self.store.root/'late-engine-receipts').exists())


if __name__=='__main__':unittest.main()
