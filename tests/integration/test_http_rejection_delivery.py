# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Real loopback rejection responses must arrive intact; no external traffic."""
import json
from email.message import Message
from io import BytesIO
import socket
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tests.integration.test_derived_site_review import ROOT
from twinpulse_app import CommandBroker, LocalApiServer


class RejectionDeliveryTests(unittest.TestCase):
    def test_nullable_json_keeps_context_header_and_complete_null_payload(self):
        from unittest.mock import patch
        for value in (None,[],{'ok':True}):
            delivered=[];headers={};context='current-context'
            request=SimpleNamespace(path='/v1/product/scene-edit/transaction',_twinpulse_context_id=context,
                send_response=lambda status:delivered.append(status),send_header=lambda k,v:headers.update({k:v}),
                end_headers=lambda:delivered.append('headers_done'),wfile=BytesIO())
            with patch('twinpulse_app.http_io.write_body',side_effect=lambda req,payload,timeout:req.wfile.write(payload)):
                LocalApiServer._json(request,200,value)
            self.assertEqual(delivered,[200,'headers_done'])
            self.assertEqual(headers['X-TwinPulse-Context'],context)
            self.assertEqual(json.loads(request.wfile.getvalue()),value)

    def test_discard_bounds_and_already_consumed_skip(self):
        class Connection:
            timeout = None
            def gettimeout(self): return self.timeout
            def settimeout(self, value): self.timeout = value
        for length, consumed, expected in (("3", False, 3), ("3", True, 0),
                                           ("524289", False, 0), ("bad", False, 0)):
            headers = Message(); headers["Content-Length"] = length
            request = SimpleNamespace(headers=headers, rfile=BytesIO(b"not-json"), connection=Connection(),
                                      _twinpulse_body_consumed=consumed)
            LocalApiServer._discard_unread_body(request)
            self.assertEqual(request.rfile.tell(), expected)
            self.assertTrue(request.close_connection)
            self.assertIsNone(request.connection.timeout)
            LocalApiServer._discard_unread_body(request)
            self.assertEqual(request.rfile.tell(), expected)

    def test_ambiguous_framing_is_not_drained_or_parsed(self):
        for duplicate in (True, False):
            headers = Message(); headers["Content-Length"] = "3"
            if duplicate: headers["Content-Length"] = "5"
            else: headers["Transfer-Encoding"] = "chunked"
            request = SimpleNamespace(headers=headers, rfile=BytesIO(b"not-json"))
            LocalApiServer._discard_unread_body(request)
            self.assertEqual(request.rfile.tell(), 0)

    def test_repeated_unread_bodies_preserve_rejection_responses(self):
        server = LocalApiServer(CommandBroker(), product_bootstrap_secret="p"*43, engine_bootstrap_secret="e"*43)
        server.start()
        try:
            for index in range(60):
                # Each request is separately rejected before JSON parsing.
                origin = {"Origin": "http://untrusted.invalid"} if index % 2 else {}
                expected = 403 if origin else 401
                body = json.dumps({"padding": "x" * (512 + index * 31)}).encode()
                request = Request(server.base_url + "/v1/product/derived-review/adopt", data=body,
                    headers={"Content-Type": "application/json", **origin})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=2)
                error = caught.exception
                self.assertEqual(error.code, expected)
                self.assertEqual(json.loads(error.read())["error"]["code"], "origin_forbidden" if origin else "session_rejected")
                error.close()
        finally:
            server.stop()

    def test_incomplete_body_cannot_hold_rejection_open(self):
        server = LocalApiServer(CommandBroker(), product_bootstrap_secret="p"*43, engine_bootstrap_secret="e"*43)
        server.start()
        try:
            with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
                start = time.monotonic()
                client.sendall((f"POST /v1/product/derived-review/adopt HTTP/1.0\r\nHost: 127.0.0.1:{server.port}\r\n"
                    "Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n").encode())
                data = client.recv(4096)
                self.assertIn(b"401", data.split(b"\r\n", 1)[0])
                self.assertLess(time.monotonic() - start, 1.0)
        finally:
            server.stop()


if __name__ == "__main__": unittest.main()
