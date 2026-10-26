# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary real loopback sockets, no App/robot/provider acceptance."""
from tests.integration import test_r4_bridge_api as base
import http.client
import json
import unittest

class HttpReuseTests(unittest.TestCase):
    setUp=base.R4ApiTests.setUp
    tearDown=base.R4ApiTests.tearDown
    request=base.R4ApiTests.request
    bootstrap=base.R4ApiTests.bootstrap

    def test_success_reuses_socket_but_auth_and_csrf_are_checked_each_request(self):
        cookie,csrf,_=self.bootstrap()
        conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
        try:
            conn.request('GET','/v1/product/state',headers={'Cookie':cookie})
            response=conn.getresponse();self.assertEqual(response.status,200);response.read()
            first=conn.sock;self.assertFalse(response.will_close)
            conn.request('POST','/v1/product/lease',b'{}',headers={'Cookie':cookie,'X-TwinPulse-CSRF':csrf,'Content-Type':'application/json'})
            response=conn.getresponse();self.assertEqual(response.status,200);self.assertTrue(json.loads(response.read())['control_lease_id'])
            self.assertIs(conn.sock,first)
            conn.request('POST','/v1/product/lease',b'{}',headers={'Cookie':cookie,'Content-Type':'application/json'})
            response=conn.getresponse();self.assertEqual(response.status,403);self.assertEqual(json.loads(response.read())['error']['code'],'csrf_rejected')
            self.assertTrue(response.will_close)
            conn.request('GET','/v1/product/state')
            response=conn.getresponse();self.assertEqual(response.status,401);response.read()
        finally:conn.close()
        self.assertTrue(self.server._httpd.RequestHandlerClass.disable_nagle_algorithm)

    def test_request_local_saved_body_and_callbacks_are_reset(self):
        cookie,csrf,_=self.bootstrap();seen=[];original=self.server._handle
        def inspect(request):
            seen.append([name for name in vars(request) if name.startswith('_twinpulse_')])
            self.assertFalse(seen[-1]);result=original(request)
            request._twinpulse_saved_json={'DO_NOT_REUSE':True};request._twinpulse_context_id='old-context'
            request._twinpulse_business_done=lambda:self.fail('Previous request callback reused')
            return result
        self.server._handle=inspect
        conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
        try:
            for path in ('/v1/product/state','/v1/product/state'):
                conn.request('GET',path,headers={'Cookie':cookie});response=conn.getresponse()
                self.assertEqual(response.status,200);response.read()
            self.assertEqual(len(seen),2)
        finally:conn.close()

    def test_client_close_and_http10_are_not_kept_alive(self):
        cookie,_,_=self.bootstrap()
        for version,close in (('HTTP/1.1','close'),('HTTP/1.1','keep-alive, CLOSE'),('HTTP/1.0','keep-alive')):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
            if version=='HTTP/1.0':conn._http_vsn=10;conn._http_vsn_str=version
            try:
                conn.request('GET','/v1/product/state',headers={'Cookie':cookie,'Host':f'127.0.0.1:{self.server.port}',
                    'Connection':close})
                response=conn.getresponse();self.assertEqual(response.status,200);response.read();self.assertTrue(response.will_close)
            finally:conn.close()

    def test_ambiguous_lengths_or_chunked_framing_are_rejected_and_closed(self):
        cookie,csrf,_=self.bootstrap()
        for kind in ('duplicate','transfer-encoding','comma','negative','invalid-json','oversize'):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
            try:
                conn.putrequest('POST','/v1/product/lease');conn.putheader('Cookie',cookie);conn.putheader('X-TwinPulse-CSRF',csrf)
                conn.putheader('Content-Type','application/json');conn.putheader('Content-Length',{'comma':'2,2','negative':'-2','oversize':'999999'}.get(kind,'2'))
                if kind=='duplicate':conn.putheader('Content-Length','2')
                if kind=='transfer-encoding':conn.putheader('Transfer-Encoding','chunked')
                conn.endheaders(b'xx' if kind=='invalid-json' else b'{}')
                try:
                    response=conn.getresponse();self.assertGreaterEqual(response.status,400);response.read()
                    self.assertTrue(response.will_close)
                except (ConnectionAbortedError,ConnectionResetError,http.client.RemoteDisconnected):
                    # For deliberately ambiguous/unread framing Windows may
                    # reset TCP while rejecting it. That is a closed transport,
                    # not a delivered HTTP error. Never allow timeout or a
                    # successful mutation as an alternative; validly framed
                    # invalid JSON still requires the explicit error above.
                    if kind=='invalid-json':raise
                self.assertIsNone(self.broker._lease_owner)
            finally:conn.close()

    def test_reused_connection_rejects_changed_credentials_host_origin_and_context(self):
        cookie,csrf,_=self.bootstrap()
        for mutation in ({'Cookie':'invalid'}, {'X-TwinPulse-CSRF':'invalid'},
                         {'Host':'evil.example'}, {'Origin':'https://evil.example'}):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
            try:
                conn.request('GET','/v1/product/state',headers={'Cookie':cookie})
                response=conn.getresponse();self.assertEqual(response.status,200);response.read();first=conn.sock
                headers={'Cookie':cookie,'X-TwinPulse-CSRF':csrf,'Content-Type':'application/json',**mutation}
                conn.request('POST','/v1/product/lease',b'{}',headers=headers)
                response=conn.getresponse();self.assertIn(response.status,(401,403));response.read();self.assertTrue(response.will_close)
            finally:conn.close()

    def test_reused_connection_uses_each_new_post_body_once(self):
        cookie,csrf,_=self.bootstrap();bodies=[];read=self.server._read_json
        def capture(request,**kw):
            value=read(request,**kw);bodies.append(value);return value
        self.server._read_json=capture
        conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
        try:
            for payload in ({},{'unexpected':'second-body'}):
                conn.request('POST','/v1/product/lease',json.dumps(payload),headers={'Cookie':cookie,'X-TwinPulse-CSRF':csrf,'Content-Type':'application/json'})
                response=conn.getresponse();response.read()
            self.assertEqual(bodies,[{},{'unexpected':'second-body'}]);self.assertEqual(response.status,400);self.assertTrue(response.will_close)
        finally:conn.close()

    def test_get_with_body_cannot_keep_connection_alive(self):
        cookie,_,_=self.bootstrap()
        conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
        try:
            conn.request('GET','/v1/product/state',body=b'{}',headers={'Cookie':cookie})
            response=conn.getresponse();response.read();self.assertTrue(response.will_close)
        finally:conn.close()

    def test_context_rechecked_on_reused_workspace_connection(self):
        from twinpulse_app.persistent_workspace import PersistentWorkspace
        cookie,csrf,_=self.bootstrap();self.server.context_id='current-context'
        PersistentWorkspace(self.server,lambda _:None)
        conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
        try:
            conn.request('GET','/v1/product/state',headers={'Cookie':cookie,'X-TwinPulse-Context':'current-context'})
            response=conn.getresponse();self.assertEqual(response.status,200);response.read()
            conn.request('POST','/v1/product/lease',b'{}',headers={'Cookie':cookie,'X-TwinPulse-CSRF':csrf,'Content-Type':'application/json','X-TwinPulse-Context':'old-context'})
            response=conn.getresponse();self.assertEqual(response.status,409);self.assertEqual(json.loads(response.read())['error']['code'],'project_context_changed')
            self.assertTrue(response.will_close);self.assertIsNone(self.broker._lease_owner)
        finally:conn.close()

    def test_invalid_json_does_not_execute_appended_second_request(self):
        cookie,csrf,_=self.bootstrap()
        import socket
        raw=socket.create_connection(('127.0.0.1',self.server.port),timeout=2)
        headers=f'POST /v1/product/lease HTTP/1.1\r\nHost: 127.0.0.1:{self.server.port}\r\nCookie: {cookie}\r\nX-TwinPulse-CSRF: {csrf}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n'.encode()
        try:
            raw.sendall(headers+b'xx'+headers+b'{}');response=b''
            while True:
                chunk=raw.recv(8192)
                if not chunk:break
                response+=chunk
            self.assertEqual(response.count(b'HTTP/1.1 '),1);self.assertIn(b' 400 ',response)
            self.assertIsNone(self.broker._lease_owner)
        finally:raw.close()

    def test_partial_body_and_idle_connection_end_with_existing_io_timeout(self):
        from unittest.mock import patch
        import socket
        import time
        cookie,csrf,_=self.bootstrap()
        with patch('twinpulse_app.api.LOCAL_SOCKET_IO_TIMEOUT_S',.1):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.port,timeout=2)
            try:
                conn.request('GET','/v1/product/state',headers={'Cookie':cookie})
                response=conn.getresponse();self.assertEqual(response.status,200);response.read();raw=conn.sock
                time.sleep(.25);self.assertEqual(raw.recv(1),b'')
            finally:conn.close()
            raw=socket.create_connection(('127.0.0.1',self.server.port),timeout=2)
            try:
                raw.sendall(f'POST /v1/product/lease HTTP/1.1\r\nHost: 127.0.0.1:{self.server.port}\r\nCookie: {cookie}\r\nX-TwinPulse-CSRF: {csrf}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{{'.encode())
                response=raw.makefile('rb');first=response.readline();self.assertIn(b' 408 ',first)
                self.assertIsNone(self.broker._lease_owner)
            finally:raw.close()

if __name__=='__main__':unittest.main()
