"""Supplementary no-device regressions for status latency and queued expiry."""
from tests.integration import test_r5_product_api
from tests.integration.test_http_mutation_lifecycle import HttpMutationLifecycleTests
from twinpulse_app.api import LocalApiServer
from twinpulse_app.command_broker import CommandBroker,_Operation
from twinpulse_core import CommandEnvelope
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event,Thread
from types import SimpleNamespace
import json
import time
import unittest
from uuid import uuid4

class StatusAdmissionTests(unittest.TestCase):
    def test_status_and_lease_preflight_do_not_probe_shutdown(self):
        api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32)
        api._httpd=SimpleNamespace(server_address=('127.0.0.1',8765))
        api._authenticate_product=lambda *a,**kw:SimpleNamespace(session_id='owner')
        def status(**kw):
            self.assertEqual(kw,{'inspect_shutdown':False});return dict(status='ready')
        api._supervisor_status=status
        api._read_json=lambda _,**kw:{}
        for method,path in [('GET','/v1/product/state'),('POST','/v1/product/lease')]:
            request=HttpMutationLifecycleTests.request(self,path);request.command=method
            request.headers={'Host':'127.0.0.1:8765'}
            statuses=[];request.send_response=statuses.append
            api._handle_current(request)
            self.assertEqual(statuses,[200])
            self.assertNotIn(b'error',request.wfile.getvalue())
            if method=='POST':self.assertTrue(json.loads(request.wfile.getvalue())['control_lease_id'])

    def test_runtime_advisory_is_unavailable_without_waiting_on_scene_mutex(self):
        with TemporaryDirectory() as root:
            status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
            api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,
                supervisor_status_file=status,launcher_shutdown_file=Path(root)/'shutdown.request')
            held=Event();release=Event()
            def owner():
                with api._robot_start_lock:held.set();release.wait(3)
            worker=Thread(target=owner);worker.start();self.assertTrue(held.wait(1))
            try:
                start=time.monotonic();value=api._supervisor_status()
                self.assertLess(time.monotonic()-start,.5)
                self.assertFalse(value['shutdown_available']);self.assertEqual(value['status'],'ready')
            finally:release.set();worker.join()

    def test_runtime_advisory_does_not_wait_for_independent_broker_or_workflow_locks(self):
        from threading import RLock
        for label in ('broker','workflow','transaction','controller','readiness'):
            with self.subTest(lock=label),TemporaryDirectory() as root:
                status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
                api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,
                    supervisor_status_file=status,launcher_shutdown_file=Path(root)/'shutdown.request')
                lock=RLock()
                if label=='broker':api.broker._lock=lock
                elif label in {'workflow','transaction'}:
                    api.product_workflow=SimpleNamespace(_lock=lock if label=='workflow' else RLock(),
                        scene_edit_transaction=SimpleNamespace(lock=lock if label=='transaction' else RLock()))
                else:api.workspace_devices=SimpleNamespace(controller=SimpleNamespace(lock=lock) if label=='controller' else None,
                    readiness=SimpleNamespace(_lock=lock) if label=='readiness' else None,physical_fleet=None)
                held=Event();release=Event()
                def owner():
                    with lock:held.set();release.wait(3)
                worker=Thread(target=owner);worker.start();self.assertTrue(held.wait(1))
                try:
                    start=time.monotonic();value=api._supervisor_status()
                    self.assertLess(time.monotonic()-start,.5);self.assertFalse(value['shutdown_available'])
                finally:release.set();worker.join()

class QueuedExpiryTests(unittest.TestCase):
    def pending(self,*,claimed=False,expired_ttl=False):
        self.now=100.;broker=CommandBroker(clock=lambda:self.now)
        broker._engine_session_id='engine';broker._stage_epoch='stage';broker._engine_heartbeat_at=self.now
        lease=broker.acquire_lease('owner')['control_lease_id']
        command=CommandEnvelope(command_id=str(uuid4()),command_type='build_site_scene',project_id=broker.project_id,
            engine_session_id='engine',stage_epoch='stage',control_lease_id=lease,expected_applied_revision=None,payload={},
            ttl_s=120.,issued_at_unix_s=time.time()-(121 if expired_ttl else 0))
        operation=_Operation(command,'hash','owner');broker._operations[command.command_id]=operation
        if claimed:broker._inflight=command.command_id;operation.status='running'
        else:broker._queue.append(command.command_id)
        return broker,operation
    def test_lost_lease_ends_never_claimed_command_without_replay(self):
        broker,operation=self.pending();self.now+=broker.lease_ttl_s+.1;broker._engine_heartbeat_at=self.now
        value=broker.public_state('owner')['operations'][0]
        self.assertEqual(value['status'],'expired');self.assertEqual(value['receipt']['error_code'],'control_lease_expired')
        self.assertFalse(broker.has_pending_operations());broker.acquire_lease('owner')
        self.assertIsNone(broker.claim('engine','stage'));self.assertEqual(operation.receipt.status,'expired')
    def test_ttl_expiry_is_processed_even_when_no_valid_lease_exists(self):
        broker,operation=self.pending(expired_ttl=True);broker._lease_expires_at=0
        self.assertIsNone(broker.claim('engine','stage'));self.assertEqual(operation.receipt.error_code,'command_expired')
    def test_running_command_does_not_get_a_false_never_executed_receipt(self):
        broker,operation=self.pending(claimed=True);broker._lease_expires_at=0
        broker.public_state('owner');self.assertIsNone(operation.receipt)
        self.assertTrue(broker.has_pending_operations());self.assertEqual(broker._inflight,operation.command.command_id)
