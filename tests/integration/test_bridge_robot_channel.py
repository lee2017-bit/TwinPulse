# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No Kit/robot: real authenticated loopback report socket lifecycle."""
from tests.integration import test_r4_bridge_api as base
from tests.integration.test_bridge_lease_rotation import BridgeClient
from types import SimpleNamespace
from threading import Thread
from unittest.mock import patch
import unittest

class RobotChannelTests(unittest.TestCase):
    setUp=base.R4ApiTests.setUp
    tearDown=base.R4ApiTests.tearDown
    request=base.R4ApiTests.request
    bootstrap=base.R4ApiTests.bootstrap
    def client(self):
        _,_,token=self.bootstrap()
        client=BridgeClient(SimpleNamespace(stage_epoch='stage-1',engine_session_id='engine-1'),
            base_url=self.server.base_url,bootstrap_secret='x'*32)
        client._engine_token=token
        return client
    def body(self):return dict(engine_session_id='engine-1',stage_epoch='stage-1',report=dict(applied_revision=None,robots=[]))
    def test_report_reuses_owned_socket_and_invalid_epoch_discards_it(self):
        client=self.client();seen=[];handle=self.server._handle
        def capture(request):seen.append(request.path);return handle(request)
        self.server._handle=capture
        try:
            client._post('/v1/engine/robots',self.body());first=client._robot_http.connection.sock
            client._post('/v1/engine/robots',self.body());self.assertIs(client._robot_http.connection.sock,first)
            with self.assertRaisesRegex(RuntimeError,'Backend rejected robot report'):
                client._post('/v1/engine/robots',{**self.body(),'stage_epoch':'stale'})
            self.assertIsNone(client._robot_http.connection);self.assertEqual(len(seen),3)
            client._post('/v1/engine/robots',self.body());self.assertEqual(len(seen),4)
        finally:client.close_robot_channel()
    def test_transport_failure_does_not_retry_the_post(self):
        client=self.client()
        with patch('http.client.HTTPConnection') as connection:
            instance=connection.return_value;instance.request.side_effect=OSError('isolated transport fault')
            with self.assertRaises(OSError):client._post('/v1/engine/robots',self.body())
            instance.request.assert_called_once();instance.close.assert_called_once()
            self.assertIsNone(client._robot_http.connection)
    def test_two_threads_do_not_share_robot_exchange_socket(self):
        client=self.client();connections=[];errors=[]
        def exchange():
            try:
                client._post('/v1/engine/robots',self.body());connections.append(client._robot_http.connection)
            except Exception as error:errors.append(type(error).__name__)
            finally:client.close_robot_channel()
        workers=[Thread(target=exchange) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(3)
        self.assertEqual(errors,[]);self.assertEqual(len(connections),2);self.assertIsNot(connections[0],connections[1])
        self.assertIsNone(getattr(client._robot_http,'connection',None))

    def viewport_body(self):return dict(engine_session_id='engine-1',stage_epoch='stage-1',frame=None,camera_result=None)

    def test_viewport_socket_reuse_is_separate_and_does_not_renew_lease(self):
        client=self.client();last=client._last_success
        try:
            client._post('/v1/engine/viewport',self.viewport_body());first=client._viewport_http.connection.sock
            client._post('/v1/engine/viewport',self.viewport_body());self.assertIs(client._viewport_http.connection.sock,first)
            self.assertEqual(client._last_success,last)
            client._post('/v1/engine/robots',self.body());self.assertIsNot(client._robot_http.connection,client._viewport_http.connection)
            with self.assertRaises(RuntimeError):client._post('/v1/engine/viewport',{**self.viewport_body(),'stage_epoch':'wrong'})
            self.assertIsNone(client._viewport_http.connection)
        finally:client.close_viewport_channel();client.close_robot_channel()

    def test_viewport_failure_is_not_retried_and_phase_has_no_payload(self):
        client=self.client()
        with patch('http.client.HTTPConnection') as factory:
            connection=factory.return_value;connection.request.side_effect=TimeoutError(10060,'private error text not retained')
            with self.assertRaises(TimeoutError):client._post('/v1/engine/viewport',self.viewport_body())
            factory.assert_called_once_with('127.0.0.1',self.server.port,timeout=2.0)
            connection.request.assert_called_once();connection.close.assert_called_once()
            self.assertEqual(client.viewport_transport_error(),dict(phase='request_connect_or_send',reused=False,error_type='TimeoutError',errno=10060,winerror=None))
            self.assertIsNone(client._viewport_http.connection)
        client._engine_token=None
        with self.assertRaisesRegex(RuntimeError,'Engine session is unavailable'):client._post('/v1/engine/viewport',self.viewport_body())
        self.assertIsNone(client.viewport_transport_error())

    def test_viewport_typed_rejection_survives_non_json_body_and_close_failure(self):
        client=self.client()
        for status,body,expected in [(401,b'not json','http_error'),(409,b'{"error":{"code":"frame_invalid"}}','frame_invalid')]:
            with patch('http.client.HTTPConnection') as factory:
                connection=factory.return_value;response=connection.getresponse.return_value
                response.status=status;response.read.return_value=body;response.will_close=True
                connection.close.side_effect=OSError('cleanup failure')
                with self.assertRaisesRegex(RuntimeError,'Backend rejected request: '+expected):client._post('/v1/engine/viewport',self.viewport_body())
                self.assertEqual(client.viewport_cleanup_error(),'OSError');connection.request.assert_called_once()

    def test_viewport_success_not_masked_by_sticky_close_failure(self):
        client=self.client()
        with patch('http.client.HTTPConnection') as factory:
            connection=factory.return_value;response=connection.getresponse.return_value
            response.status=200;response.read.return_value=b'{"camera":null}';response.will_close=True
            connection.close.side_effect=OSError('cleanup failure')
            self.assertEqual(client._post('/v1/engine/viewport',self.viewport_body()),dict(camera=None))
            self.assertEqual(client.viewport_cleanup_error(),'OSError');self.assertIsNone(client._viewport_http.connection)

    def test_viewport_threads_do_not_share_exchange_socket(self):
        client=self.client();connections=[];errors=[]
        def exchange():
            try:
                client._post('/v1/engine/viewport',self.viewport_body());connections.append(client._viewport_http.connection)
            except Exception as error:errors.append(type(error).__name__)
            finally:client.close_viewport_channel()
        workers=[Thread(target=exchange) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(3)
        self.assertEqual(errors,[]);self.assertEqual(len(connections),2);self.assertIsNot(connections[0],connections[1])

if __name__=='__main__':unittest.main()
