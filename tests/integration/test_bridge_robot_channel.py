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

if __name__=='__main__':unittest.main()
