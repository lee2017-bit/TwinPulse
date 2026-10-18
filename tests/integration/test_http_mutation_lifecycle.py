# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit local HTTP fault tests, not ordinary browser/Isaac acceptance."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import http.client
import json
import socket
from threading import Event,Thread,Timer
import time
import unittest
from unittest.mock import patch

from twinpulse_app.api import LocalApiServer
from twinpulse_app.command_broker import BrokerError,CommandBroker
from twinpulse_app.persistent_workspace import PersistentWorkspace


class HttpMutationLifecycleTests(unittest.TestCase):
    def test_workspace_and_api_fleet_classification_consume_body_once(self):
        class CountedBody(BytesIO):
            count=0
            def read(self,*a):self.count+=1;return super().read(*a)
            def read1(self,*a):self.count+=1;return super().read1(*a)
        for action in ('register_sim','drive','stop_all'):
            api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,virtual=True)
            api._httpd=SimpleNamespace(server_address=('127.0.0.1',8765))
            api._authenticate_product=lambda *a,**kw:SimpleNamespace(session_id='owner')
            api._supervisor_status=lambda **_:dict(status='ready')
            seen=[];api.robot_fleet=SimpleNamespace(action=lambda body,owner:seen.append((body,owner)) or dict(accepted=True))
            workspace=PersistentWorkspace(api,lambda _:None)
            body=dict(action=action,request_id='fresh-request',robot_id=None,connection_epoch=None,motion_epoch=None,payload={})
            raw=json.dumps(body).encode();request=self.request('/v1/product/robot-fleet')
            request.headers={'Host':f'127.0.0.1:{api.port}','Content-Type':'application/json','Content-Length':str(len(raw))}
            request.rfile=CountedBody(raw)
            workspace.dispatch(request)
            self.assertEqual(seen,[(body,'owner')]);self.assertEqual(request.rfile.count,1)

    def test_owned_fleet_stop_does_not_inspect_unrelated_shutdown_readiness(self):
        api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,virtual=True)
        api._httpd=SimpleNamespace(server_address=('127.0.0.1',8765))
        api._authenticate_product=lambda *a,**kw:SimpleNamespace(session_id='owner')
        api._supervisor_status=lambda:self.fail('Stop must not wait for shutdown/scene locks')
        api.robot_fleet=SimpleNamespace(action=lambda body,owner:dict(stopped=True))
        request=self.request('/v1/product/robot-fleet');raw=json.dumps(dict(action='stop_all')).encode()
        request.headers={'Host':f'127.0.0.1:{api.port}','Content-Type':'application/json','Content-Length':str(len(raw))}
        request.rfile=BytesIO(raw)
        PersistentWorkspace(api,lambda _:None).dispatch(request)

    def test_fleet_stop_and_disconnect_bypass_closing_switch_and_stale_context(self):
        for action in ('stop','stop_all','disconnect'):
            seen=[]
            def handle(request):seen.append(request._twinpulse_saved_json);return {'delivered':True}
            api=SimpleNamespace(context_id='current',_handle_current=handle,
                _authenticate_product=lambda *a,**k:None,_read_json=lambda _,**kw:dict(action=action),
                _error=lambda *a: self.fail('Owned Stop must not be a fenced mutation'))
            workspace=PersistentWorkspace(api,lambda _:None)
            workspace.closing=True;workspace.pending={'in_progress':True}
            request=self.request('/v1/product/robot-fleet');request.headers={'X-TwinPulse-Context':'old'}
            self.assertEqual(workspace.dispatch(request),{'delivered':True})
            self.assertEqual(seen,[{'action':action}]);self.assertEqual(workspace.mutations['current'],0)

    def request(self,path='/v1/product/commands'):
        return SimpleNamespace(command='POST',path=path,headers={},wfile=BytesIO(),
            send_response=lambda _:None,send_header=lambda *_:None,end_headers=lambda:None)

    def test_response_write_no_longer_fences_but_remains_observable(self):
        entered=Event();release=Event()
        class WaitingWriter:
            def write(self,value):
                entered.set();release.wait(2)
        def handle(request):LocalApiServer._json(request,200,dict(status='business_finished'))
        api=SimpleNamespace(context_id='fixture-context',_handle_current=handle)
        workspace=PersistentWorkspace(api,lambda _:None)
        request=self.request();request.wfile=WaitingWriter()
        worker=Thread(target=lambda:workspace.dispatch(request),daemon=True);worker.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(workspace.mutations[api.context_id],0)
            active=workspace.request_diagnostics()
            self.assertEqual(active[0]['phase'],'response_write');self.assertFalse(active[0]['fenced'])
            self.assertNotIn('headers',active[0]);self.assertNotIn('body',active[0])
            self.assertEqual(request._twinpulse_context_id,'fixture-context')
        finally:release.set();worker.join(2)
        self.assertEqual(workspace.active_requests,{})
        self.assertEqual(workspace.mutations[api.context_id],0)

    def test_slow_business_keeps_guard_and_exception_does_not_leak_count(self):
        entered=Event();release=Event();caught=[]
        def handle(request):
            entered.set();release.wait(2);raise ValueError('explicit fixture exception')
        api=SimpleNamespace(context_id='fixture-context',_handle_current=handle)
        workspace=PersistentWorkspace(api,lambda _:None)
        def run():
            try:workspace.dispatch(self.request('/v1/product/not-a-real-route/private-text'))
            except ValueError:caught.append(True)
        worker=Thread(target=run,daemon=True);worker.start()
        try:
            self.assertTrue(entered.wait(1));self.assertEqual(workspace.mutations[api.context_id],1)
            self.assertEqual(workspace.request_diagnostics()[0]['route'],'other_product_post')
            self.assertTrue(workspace.request_diagnostics()[0]['fenced'])
        finally:release.set();worker.join(2)
        self.assertEqual(caught,[True]);self.assertEqual(workspace.mutations[api.context_id],0)
        self.assertEqual(workspace.request_diagnostics(),[])

    def test_timed_out_body_does_not_start_business_or_retry_read(self):
        class MissingBody:
            def read(self,_):raise TimeoutError('explicit fixture socket inactivity')
        api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,virtual=True)
        request=self.request();request.headers={'Content-Type':'application/json','Content-Length':'10'}
        request.rfile=MissingBody();phases=[];request._twinpulse_request_phase=phases.append
        with self.assertRaisesRegex(BrokerError,'body did not arrive') as error:api._read_json(request)
        self.assertEqual(error.exception.status,408);self.assertTrue(request.close_connection)
        self.assertTrue(request._twinpulse_body_consumed);self.assertEqual(phases,['request_body_read'])

    def test_response_timeout_is_not_a_second_mutation_or_error_response(self):
        class UnreadResponse:
            def write(self,_):raise TimeoutError('explicit fixture write timeout')
        calls=[];request=self.request();request.wfile=UnreadResponse()
        request._twinpulse_business_done=lambda:calls.append('business_done')
        LocalApiServer._json(request,200,dict(status='committed'))
        self.assertTrue(request.close_connection);self.assertEqual(calls,['business_done'])

    def test_actual_loopback_header_read_has_bounded_inactivity(self):
        # This tests the real accepted socket, not an endpoint/auth workaround.
        # No authenticated request, model, engine or robot is started.
        with patch('twinpulse_app.api.LOCAL_SOCKET_IO_TIMEOUT_S',.15):
            api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32)
            api.start()
            try:
                with socket.create_connection(('127.0.0.1',api.port),timeout=2) as client:
                    client.settimeout(2)
                    client.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n')
                    started=time.monotonic();self.assertEqual(client.recv(1),b'')
                    self.assertLess(time.monotonic()-started,1.8)
            finally:api.stop()

    def test_actual_authenticated_half_body_releases_mutation_without_command(self):
        with patch('twinpulse_app.api.LOCAL_SOCKET_IO_TIMEOUT_S',.3):
            api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32)
            workspace=PersistentWorkspace(api,lambda _:None);api.start()
            try:
                control=http.client.HTTPConnection('127.0.0.1',api.port,timeout=2)
                control.request('POST','/v1/bootstrap',json.dumps(dict(role='product',secret='p'*32)),
                    {'Content-Type':'application/json'})
                response=control.getresponse();self.assertEqual(response.status,200)
                cookie=response.getheader('Set-Cookie').split(';',1)[0]
                csrf=json.loads(response.read())['csrf_token'];control.close()
                with socket.create_connection(('127.0.0.1',api.port),timeout=2) as client:
                    client.settimeout(2)
                    header=(f'POST /v1/product/commands HTTP/1.1\r\nHost: 127.0.0.1:{api.port}\r\n'
                        f'Cookie: {cookie}\r\nX-TwinPulse-CSRF: {csrf}\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n')
                    client.sendall(header.encode()+b'{')
                    deadline=time.monotonic()+.2
                    while time.monotonic()<deadline and not workspace.request_diagnostics():time.sleep(.005)
                    self.assertEqual(workspace.request_diagnostics()[0]['phase'],'request_body_read')
                    self.assertEqual(workspace.mutations[api.context_id],1)
                    self.assertIn(b'408',client.recv(2048))
                deadline=time.monotonic()+1
                while workspace.request_diagnostics() and time.monotonic()<deadline:time.sleep(.005)
                self.assertEqual(workspace.mutations[api.context_id],0)
                self.assertEqual(workspace.request_diagnostics(),[])
                self.assertFalse(api.broker.has_pending_operations())
            finally:api.stop()

    def test_dribbling_body_and_partial_writes_do_not_reset_total_deadline(self):
        from twinpulse_app.http_io import read_body,write_body
        clock=[0.0]
        class Drip:
            def read(self,_):raise AssertionError('Do not use blocking read(length)')
            def read1(self,_):clock[0]+=.06;return b'x'
        class Writer:
            def __init__(self):self.parts=[]
            def write(self,value):self.parts.append(value);clock[0]+=.06
        with patch('twinpulse_app.http_io.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(TimeoutError):read_body(SimpleNamespace(rfile=Drip()),10,.1)
            clock[0]=0;writer=Writer()
            with self.assertRaises(TimeoutError):write_body(SimpleNamespace(wfile=writer),b'x'*180000,.1)
            self.assertEqual(len(writer.parts),2)

    def test_shutdown_fences_new_posts_drains_business_then_rechecks_workers(self):
        for starts_worker in (False,True):
            with self.subTest(starts_worker=starts_worker),TemporaryDirectory() as root:
                status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
                shutdown=Path(root)/'shutdown.request'
                api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                    engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
                workspace=PersistentWorkspace(api,lambda _:None);entered=Event();release=Event()
                def handle(request):
                    entered.set();release.wait(2)
                    if starts_worker:
                        api.product_workflow=SimpleNamespace(has_active_generation=lambda:True,
                            scene_edit_transaction=SimpleNamespace(locked=lambda:False))
                    LocalApiServer._json(request,200,dict(done=True))
                with patch.object(api,'_handle_current',side_effect=handle):
                    worker=Thread(target=lambda:workspace.dispatch(self.request()),daemon=True);worker.start()
                    self.assertTrue(entered.wait(1))
                    timer=Timer(.1,release.set);timer.start()
                    try:
                        if starts_worker:
                            with self.assertRaisesRegex(BrokerError,'active or uncertain'):api._request_shutdown()
                            self.assertFalse(shutdown.exists());self.assertFalse(workspace.closing)
                        else:
                            self.assertEqual(api._request_shutdown()['status'],'requested')
                            self.assertTrue(shutdown.exists());self.assertTrue(workspace.closing)
                    finally:release.set();timer.join();worker.join(2)
                self.assertEqual(workspace.mutations[api.context_id],0)

    def test_busy_worker_is_not_waited_out_or_counter_cleared(self):
        with TemporaryDirectory() as root:
            status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
            shutdown=Path(root)/'shutdown.request'
            api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
            workspace=PersistentWorkspace(api,lambda _:None)
            with patch.object(api.broker,'has_pending_operations',return_value=True):
                with self.assertRaises(BrokerError):api._request_shutdown()
            self.assertFalse(shutdown.exists());self.assertFalse(workspace.closing)

    def test_capped_diagnostics_never_hide_the_33rd_active_business(self):
        with TemporaryDirectory() as root:
            status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
            shutdown=Path(root)/'shutdown.request'
            api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
            workspace=PersistentWorkspace(api,lambda _:None)
            for i in range(33):
                workspace.active_requests[str(i)]=dict(context_id=api.context_id,route='/v1/product/commands',
                    thread_id=i,phase='dispatch' if i==32 else 'response_write',started=0,fenced=i==32)
            workspace.mutations[api.context_id]=1
            self.assertFalse(any(r['fenced'] for r in workspace.request_diagnostics()))
            self.assertEqual(workspace.pending_business_count(),1)
            ticks=iter(range(0,1000,3))
            with patch('twinpulse_app.api.time.monotonic',side_effect=lambda:next(ticks)):
                with self.assertRaisesRegex(BrokerError,'outside the diagnostic sample'):api._request_shutdown()
            self.assertFalse(shutdown.exists());self.assertFalse(workspace.closing)
            self.assertEqual(workspace.mutations[api.context_id],1)

    def test_shutdown_never_holds_workspace_while_waiting_for_robot_lock(self):
        with TemporaryDirectory() as root:
            status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
            shutdown=Path(root)/'shutdown.request'
            api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
            workspace=PersistentWorkspace(api,lambda _:None)
            held=Event();crossed=Event();result=[]
            def robot_start_already_admitted():
                with api._robot_start_lock:
                    held.set();deadline=time.monotonic()+1
                    while not workspace.closing and time.monotonic()<deadline:time.sleep(.005)
                    # Same lock order as a real robot start's physical guard.
                    workspace.switching();crossed.set()
            robot=Thread(target=robot_start_already_admitted,daemon=True);robot.start()
            self.assertTrue(held.wait(1))
            def stop():
                try:result.append(api._request_shutdown())
                except Exception as error:result.append(error)
            with patch.object(api,'_supervisor_status',return_value=dict(status='ready')):
                stopper=Thread(target=stop,daemon=True);stopper.start();stopper.join(2)
                self.assertTrue(crossed.is_set(),'robot -> workspace must not deadlock shutdown')
                self.assertFalse(stopper.is_alive());self.assertEqual(result[0]['status'],'requested')
            robot.join(1)

    def test_unpublished_write_fsync_and_link_failure_leave_no_shutdown_or_closing_latch(self):
        for failure in ('write','fsync','link'):
            with self.subTest(failure=failure),TemporaryDirectory() as root:
                status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
                shutdown=Path(root)/'shutdown.request'
                api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                    engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
                workspace=PersistentWorkspace(api,lambda _:None)
                original_open=Path.open
                class WriteFailure:
                    def __init__(self,stream):self.stream=stream
                    def __enter__(self):return self
                    def __exit__(self,*_):self.stream.close()
                    def write(self,_):raise OSError('explicit unpublished write failure')
                def opening(path,*args,**kwargs):
                    stream=original_open(path,*args,**kwargs)
                    return WriteFailure(stream) if str(path).endswith('.unpublished') else stream
                target={'write':'pathlib.Path.open','fsync':'twinpulse_app.api.os.fsync','link':'twinpulse_app.api.os.link'}[failure]
                with patch(target,**({'new':opening} if failure=='write' else {'side_effect':OSError('explicit unpublished failure')})):
                    with self.assertRaisesRegex(BrokerError,'Could not save'):api._request_shutdown()
                self.assertFalse(shutdown.exists());self.assertFalse(workspace.closing)
                self.assertFalse(list(Path(root).glob('*.unpublished')))
                self.assertEqual(api._request_shutdown()['status'],'requested')
                self.assertEqual(json.loads(shutdown.read_text()),dict(schema_version='1.0',action='shutdown'))

    def test_existing_incomplete_shutdown_is_not_success_or_overwritten(self):
        with TemporaryDirectory() as root:
            status=Path(root)/'status.json';status.write_text(json.dumps(dict(status='ready',phase='ready')))
            shutdown=Path(root)/'shutdown.request';shutdown.write_bytes(b'{')
            api=LocalApiServer(CommandBroker(),virtual=True,product_bootstrap_secret='p'*32,
                engine_bootstrap_secret='e'*32,supervisor_status_file=status,launcher_shutdown_file=shutdown)
            workspace=PersistentWorkspace(api,lambda _:None)
            with self.assertRaisesRegex(BrokerError,'incomplete or invalid'):api._request_shutdown()
            self.assertEqual(shutdown.read_bytes(),b'{');self.assertFalse(workspace.closing)
            self.assertFalse(api._supervisor_status()['shutdown_requested'])
            self.assertTrue(api._supervisor_status()['shutdown_request_uncertain'])


if __name__=='__main__':unittest.main()
