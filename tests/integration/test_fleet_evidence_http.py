# SPDX-License-Identifier: Apache-2.0
"""Supplementary loopback contract test; no robot or user acceptance claim."""
import http.client
import json
from types import SimpleNamespace
import unittest

from twinpulse_app.api import LocalApiServer
from twinpulse_app.command_broker import CommandBroker
from twinpulse_app.persistent_workspace import PersistentWorkspace


class FleetEvidenceHttpTests(unittest.TestCase):
    def test_binary_receipt_keeps_context_and_exact_bytes(self):
        api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*43,
                           engine_bootstrap_secret='e'*43)
        PersistentWorkspace(api,lambda _:None)
        calls=[]
        original=b'{"complete":true,"source":"supplementary-contract"}\n'
        def evidence(*args):
            calls.append(args)
            return original
        api.robot_fleet=SimpleNamespace(physical=SimpleNamespace(evidence_file=evidence),close=lambda:None)
        api._supervisor_status=lambda **_:dict(status='ready')
        api.start()
        client=http.client.HTTPConnection('127.0.0.1',api.port,timeout=3)
        try:
            client.request('POST','/v1/bootstrap',json.dumps(dict(role='product',secret='p'*43)),
                           {'Content-Type':'application/json'})
            response=client.getresponse()
            self.assertEqual(response.status,200)
            cookie=response.getheader('Set-Cookie').split(';',1)[0]
            response.read()
            context=api.context_id
            client.request('GET','/v1/product/robot-fleet/operations/operation-a/evidence/receipt.json',
                           headers={'Cookie':cookie,'X-TwinPulse-Context':context})
            response=client.getresponse()
            self.assertEqual(response.status,200)
            self.assertEqual(response.getheader('X-TwinPulse-Context'),context)
            self.assertEqual(response.getheader('Cache-Control'),'no-store')
            self.assertEqual(response.getheader('X-Content-Type-Options'),'nosniff')
            self.assertEqual(response.read(),original)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][:2],('operation-a','receipt.json'))
            self.assertEqual(calls[0][3],api.broker.project_id)
        finally:
            client.close()
            api.stop()


if __name__=='__main__':
    unittest.main()
