# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from twinpulse_app import CommandBroker,LocalApiServer
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.project_store import AutomaticMapStore
from twinpulse_core.observation_stream import ObservationWindow
from packages.twinpulse_core.tests.test_automatic_mapping import CONTEXT, observations


GEOMETRY={'base_footprint_to_base_link_xyz_m':[0,0,.01],'base_link_to_scan_xyz_m':[0,0,.172],'revision':'c'*64}
class Source:
    def __init__(self,positions=None,gate=None,context=None):
        self.context=context or CONTEXT;self.window=ObservationWindow(self.context);self.gate=gate
        self.positions=positions or [[0,-.7+i*.014,.35+i*.004] for i in range(30)]
    def __iter__(self):
        if self.gate:self.gate.wait(3)
        yield from observations(self.positions,context=self.context)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.service=AutomaticDemoService(self.root,'default',source_factory=lambda *a:Source(),geometry_loader=lambda:GEOMETRY)
        self.addCleanup(self.service.close)
    def finish(self):
        self.service.worker.join(timeout=8)
        self.assertFalse(self.service.worker.is_alive())
        return self.service.snapshot('owner')['job']

    def test_start_single_owned_worker_save_reopen_no_pose(self):
        started=self.service.start('owner','a'*32);self.assertEqual(started['job']['mode'],'RECORDED_CAUSAL_REPLAY')
        ended=self.finish();self.assertEqual(ended['state'],'COMPLETED',ended)
        elapsed=ended['elapsed_s'];time.sleep(.01)
        self.assertEqual(self.service.snapshot('owner')['job']['elapsed_s'],elapsed)
        self.assertEqual(ended['result']['counts']['scans_seen'],30)
        self.assertFalse(ended['result']['motion_authorized'])
        reopened=self.service.reopen('different-http-connection',ended['map_id'])
        self.assertIsNone(reopened['pose_candidate']);self.assertFalse(reopened['motion_authorized'])
        self.assertFalse(reopened['map']['reference_eligible'])
        other=AutomaticMapStore(self.root,'other')
        with self.assertRaises(OSError):other.load(ended['map_id'])
        with self.assertRaises(BrokerError):self.service.snapshot('not-owner')
        self.assertEqual(self.service.maps()['maps'][0]['map_id'],ended['map_id'])
        with self.assertRaises(FileExistsError):self.service.store.save(ended['map_id'],reopened['map'])

    def test_pause_seek_resume_epoch_late_failure_cancel_no_auto_restart(self):
        gate=threading.Event();entered=threading.Event();calls=[]
        def factory(*args):
            calls.append(1)
            if len(calls)==1:
                entered.set()
                gate.wait(3);raise ValueError('OLD_EPOCH_FAILURE')
            return Source()
        self.service.source_factory=factory
        start=self.service.start('owner','a'*32)['job'];job=start['job_id']
        self.assertTrue(entered.wait(2))
        self.service.control('owner',job,'pause');self.service.control('owner',job,'seek',5)
        gate.set();time.sleep(.05)
        paused=self.service.snapshot('owner')['job'];self.assertEqual(paused['state'],'PAUSED');self.assertIsNone(paused['result'])
        self.service.control('owner',job,'resume');ended=self.finish()
        self.assertEqual(ended['state'],'COMPLETED',ended);self.assertGreater(ended['epoch'],start['epoch'])
        self.assertIsNone(ended['error'])
        gate.clear();self.service.source_factory=lambda *a:Source(gate=gate)
        start=self.service.start('owner','b'*32)['job']
        with self.assertRaises(BrokerError):self.service.start('owner','b'*32)
        with self.assertRaises(BrokerError):self.service.control('wrong',start['job_id'],'cancel')
        self.service.control('owner',start['job_id'],'cancel');gate.set()
        ended=self.finish();self.assertEqual(ended['state'],'CANCELLED');self.assertIsNone(ended['map_id'])

    def test_source_change_map_tamper_seek_and_failures_are_precise(self):
        count=[0]
        def changing(*args):
            count[0]+=1
            context=copy.deepcopy(CONTEXT)
            if count[0]>1:context['source_revision']='d'*64
            return Source(context=context)
        self.service.source_factory=changing;self.service.start('owner','a'*32)
        failed=self.finish();self.assertEqual(failed['state'],'FAILED');self.assertEqual(failed['error'],'AUTOMATIC_SOURCE_CHANGED')
        self.assertFalse(list(self.service.store.folder.glob('*.json')))
        failures=list((self.service.store.folder/'failures').glob('*.json'))
        self.assertEqual(json.loads(failures[0].read_text())['error'],'AUTOMATIC_SOURCE_CHANGED')
        self.service.source_factory=lambda *a:Source();self.service.start('owner','b'*32)
        good=self.finish();path=self.service.store._path(good['map_id']);body=json.loads(path.read_text());body['cells'][0][0]+=1
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(BrokerError,'HASH_MISMATCH'):self.service.reopen('owner',good['map_id'])

    def test_authenticated_api_start_poll_reopen_strict_shape_and_no_motion(self):
        server=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.automatic_demo.close();server.automatic_demo=self.service;server.start();self.addCleanup(server.stop)
        def request(path,body=None,headers=None):
            req=Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json',**(headers or {})})
            try:
                with urlopen(req,timeout=8) as response:return response.status,json.loads(response.read()),response.headers
            except HTTPError as exc:return exc.code,json.loads(exc.read()),exc.headers
        _,boot,h=request('/v1/bootstrap',{'role':'product','secret':'p'*43})
        auth={'Cookie':h['Set-Cookie'].split(';')[0],'X-TwinPulse-CSRF':boot['csrf_token']}
        # Offline mapping must remain usable when the unrelated Isaac runtime fails.
        server._supervisor_status=lambda:{'status':'error'}
        body={'job_id':'a'*32,'reference_map_id':None,'photo_policy':'correct_walls'}
        self.assertNotEqual(request('/v1/product/automatic-demo/start',body)[0],202)
        self.assertEqual(request('/v1/product/automatic-demo/start',{**body,'goal':[1,2]},auth)[0],400)
        self.assertEqual(request('/v1/product/automatic-demo/start',{**body,'photo_policy':'force_accept'},auth)[0],400)
        self.assertEqual(request('/v1/product/automatic-demo/start',{**body,'replay_mode':'live'},auth)[0],400)
        status,started,_=request('/v1/product/automatic-demo/start',body,auth);self.assertEqual(status,202,started)
        self.service.worker.join(timeout=8);self.assertFalse(self.service.worker.is_alive())
        status,ended,_=request('/v1/product/automatic-demo',headers=auth)
        self.assertEqual(status,200);self.assertEqual(ended['job']['state'],'COMPLETED');self.assertFalse(ended['motion_authorized'])
        self.assertEqual(ended['job']['result']['photo_alignment']['status'],'INSUFFICIENT_EVIDENCE')
        self.assertEqual(request('/v1/product/automatic-demo/rollback-photo',{'job_id':ended['job']['job_id'],'revision':'e'*64},auth)[0],409)
        status,reopened,_=request('/v1/product/automatic-demo/reopen',{'map_id':ended['job']['map_id']},auth)
        self.assertEqual(status,200);self.assertIsNone(reopened['pose_candidate'])
        status,started,_=request('/v1/product/automatic-demo/start',{**body,'replay_mode':'recorded_1x'},auth)
        self.assertEqual(status,202,started)
        self.service.worker.join(8);self.assertFalse(self.service.worker.is_alive())
        status,value,_=request('/v1/product/automatic-demo',headers=auth)
        self.assertEqual(status,200);paced=value['job'];self.assertEqual(paced['state'],'COMPLETED')
        self.assertEqual(paced['replay_timing']['events'],60)
        self.assertGreaterEqual(paced['elapsed_s'],2.9)
        self.assertEqual(request('/v1/product/automatic-demo?file=outside',headers=auth)[0],400)
        self.assertEqual(request('/v1/product/automatic-demo/reopen',{'map_id':'../outside'},auth)[0],409)
        gate=threading.Event();self.service.source_factory=lambda *a:Source(gate=gate)
        status,started,_=request('/v1/product/automatic-demo/start',body,auth);self.assertEqual(status,202,started)
        pending=self.root/'switch.json';pending.write_text('{}');server._launcher_project_switch_file=pending
        self.assertEqual(request('/v1/product/automatic-demo/start',body,auth)[1]['error']['code'],'project_switch_pending')
        status,_,_=request('/v1/product/automatic-demo/control',{'job_id':started['job']['job_id'],'action':'cancel','sequence':None},auth)
        self.assertEqual(status,200);gate.set();self.service.worker.join(timeout=8)
        self.assertEqual(request('/v1/product/automatic-demo',headers=auth)[1]['job']['state'],'CANCELLED')


if __name__=='__main__':unittest.main()
