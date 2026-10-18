# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual shared pair workers/API; output-reactive synthetic truth, no device."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from twinpulse_app import CommandBroker,LocalApiServer
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_comparison_service import AutomaticComparisonService
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.automatic_mission_comparison import compare_automatic_missions
from twinpulse_core.revisions import canonical_sha256
from tests.integration.test_automatic_photo_service import recipe
from tests.integration.test_automatic_demo_service import GEOMETRY


class AutomaticComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.outline,_=recipe(self.root,'comparison_room',1.)
        self.automatic=AutomaticDemoService(self.root,'comparison_room',geometry_loader=lambda:GEOMETRY)
        self.addCleanup(self.automatic.close)
        self.service=AutomaticComparisonService(self.automatic,world_loader=lambda *_:self.outline)
        self.addCleanup(self.service.close)

    def test_pair_actual_workers_independent_ledgers_immutable_sources_and_raw(self):
        originals={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root/'projects').rglob('*') if p.is_file()}
        saving=threading.Event();release=threading.Event();original_open=Path.open
        def delayed_save(path,*args,**kwargs):
            if path.name=='comparison.json' and args and args[0]=='x':
                saving.set()
                if not release.wait(15):raise ValueError('TEST_SAVE_RELEASE_MISSING')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',delayed_save):
            job=self.service.start('owner',[0.,-.6,0.],[.15,-.6])['job']
            try:
                self.assertTrue(saving.wait(150),'PAIR_NEVER_REACHED_SAVING')
                during=self.service.snapshot('owner')['job'];self.assertEqual(during['state'],'SAVING')
                self.assertNotIn('report_revision',during)
                self.assertEqual(self.service.stop('owner',job['job_id'])['job']['state'],'SAVING')
            finally:release.set()
            self.service.worker.join(180)
        self.assertFalse(self.service.worker.is_alive())
        result=self.service.snapshot('owner')['job'];self.assertEqual(result['state'],'COMPLETED',result)
        compared=result['result'];self.assertTrue(compared['comparable_arrivals'],compared['arms'])
        self.assertFalse(compared['arms']['baseline']['geometry_corrected'])
        self.assertTrue(compared['arms']['corrected']['geometry_corrected'])
        self.assertEqual([a['collision_episodes'] for a in compared['arms'].values()],[0,0])
        self.assertFalse(compared['motion_authorized']);self.assertFalse(compared['physical_demo_ready'])
        folder=self.root/'artifacts/automatic-comparison'/job['job_id']
        report=json.loads((folder/'comparison.json').read_text());digest=report.pop('revision')
        self.assertEqual(canonical_sha256(report),digest)
        reopened=self.service.reopen('owner',job['job_id'],digest)
        self.assertEqual(reopened['report']['result'],compared);self.assertFalse(reopened['motion_authorized'])
        for name,arm in compared['arms'].items():
            raw=json.loads((folder/(name+'-synthetic-raw.json')).read_text())
            self.assertGreater(len(raw['commands']),10);self.assertGreater(len(raw['observations']),10)
            self.assertEqual(arm['final_output'],[0.,0.]);self.assertEqual(arm['conditions_revision'],compared['conditions']['revision'])
            mission=json.loads((folder/arm['report_path']).read_text());r=mission.pop('revision')
            self.assertEqual(canonical_sha256(mission),r);self.assertEqual(r,arm['report_revision'])
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals},originals)
        self.assertFalse((self.root/'artifacts/automatic-photo-alignment/comparison_room').exists())
        evidence=os.environ.get('TWINPULSE_PREFLIGHT_EVIDENCE')
        if evidence:
            import shutil
            destination=Path(evidence)/'actual-comparison';destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(folder,destination)
        (folder/'baseline-synthetic-raw.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'RAW_HASH_CHANGED'):self.service.reopen('owner',job['job_id'],digest)

    def test_first_admission_failure_still_executes_independent_candidate(self):
        from twinpulse_app.offline_mission_adapter import OfflineMissionAdapter
        count=[]
        def admit(adapter,goal):
            count.append(1)
            if len(count)==1:raise ValueError('SYNTHETIC_BASELINE_ADMISSION_FAILED')
        with patch.object(OfflineMissionAdapter,'admit',admit):
            self.service.start('owner',[0.,-.6,0.],[.15,-.6]);self.service.worker.join(180)
        job=self.service.snapshot('owner')['job'];self.assertEqual(job['state'],'COMPLETED',job)
        self.assertEqual(job['result']['arms']['baseline']['state'],'FAILED')
        self.assertEqual(job['result']['arms']['corrected']['state'],'MISSION_ARRIVED')
        self.assertFalse(job['result']['comparable_arrivals']);self.assertIsNone(job['result']['distance_reduction_m'])

    def test_exact_coordinates_owner_cancel_no_second_arm(self):
        for start in ([float('nan'),0,0],[True,0,0],[0,0],['0',0,0]):
            with self.assertRaises(BrokerError):self.service.start('owner',start,[0,0])
        job=self.service.start('owner',[0.,-.6,0.],[.15,-.6])['job']
        with self.assertRaises(BrokerError):self.service.snapshot('other')
        self.service.stop('owner',job['job_id']);self.service.worker.join(15)
        self.assertFalse(self.service.worker.is_alive());result=self.service.snapshot('owner')['job']
        self.assertEqual(result['state'],'CANCELLED');self.assertIsNone(result['result'])

    def test_default_world_is_photo_assumption_and_api_auth_exact_shape(self):
        server=LocalApiServer(CommandBroker(project_id='comparison_room'),product_bootstrap_secret='p'*43,
            engine_bootstrap_secret='e'*43,session_history_root=self.root)
        server.automatic_comparison.close();server.automatic_comparison=self.service
        server.start();self.addCleanup(server.stop)
        def req(path,body=None,headers=None):
            request=Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Origin':server.base_url,'Content-Type':'application/json',**(headers or {})})
            with urlopen(request,timeout=10) as response:return json.loads(response.read()),dict(response.headers)
        with self.assertRaises(HTTPError):req('/v1/product/automatic-demo/comparison')
        auth,headers=req('/v1/bootstrap',{'role':'product','secret':'p'*43})
        identity={'Cookie':headers['Set-Cookie'].split(';')[0],'X-TwinPulse-CSRF':auth['csrf_token']}
        with self.assertRaises(HTTPError):req('/v1/product/automatic-demo/comparison-start',
            {'start':[0,-.6,0],'goal':[.15,-.6],'world':'injected'},identity)
        job,_=req('/v1/product/automatic-demo/comparison-start',{'start':[0,-.6,0],'goal':[.15,-.6]},identity)
        req('/v1/product/automatic-demo/comparison-stop',{'job_id':job['job']['job_id']},identity)
        self.service.worker.join(15)
        result,_=req('/v1/product/automatic-demo/comparison',headers=identity)
        self.assertEqual(result['job']['state'],'CANCELLED');self.assertEqual(result['scope'],'OUTPUT_REACTIVE_SYNTHETIC_NOT_ROBOT')

    def test_failed_arm_is_not_improvement_and_collision_penalty_is_explicit(self):
        from twinpulse_core.automatic_mission_comparison import checked_conditions
        c={'schema':'automatic-mission-conditions-1.0','project_id':'r','room_revision':'a'*64,'world_revision':'b'*64,
            'start':[0.,0.,0.],'goal':[.1,0.],'seed':0,'dynamics':'static_kinematic_raycast_v1',
            'geometry_revision':'c'*64,'duration_s':45.,'footprint_radius_m':.18,'collision_penalty':100}
        c={**c,'revision':canonical_sha256(c)};checked_conditions(c)
        a={'conditions_revision':c['revision'],'state':'MISSION_ARRIVED','physical_validation':'NOT_RUN',
            'provenance':'synthetic_raycast','distance_m':1.,'source_elapsed_s':3.,'goal_error_m':.01,'collision_episodes':2}
        arms={'baseline':{**a,'policy':'align_only'},'corrected':{**a,'policy':'correct_walls','state':'FAILED','collision_episodes':0}}
        result=compare_automatic_missions(c,arms)
        self.assertFalse(result['comparable_arrivals']);self.assertIsNone(result['source_time_reduction_s'])
        self.assertEqual(result['arms']['baseline']['score'],-100)
        arms['corrected']['conditions_revision']='d'*64
        with self.assertRaisesRegex(ValueError,'CONDITIONS_OR_PROVENANCE'):compare_automatic_missions(c,arms)

    def test_disk_failure_retains_type_errno_in_snapshot(self):
        import errno
        with patch.object(Path,'mkdir',side_effect=OSError(errno.ENOSPC,'private data must not escape')):
            self.service.start('owner',[0.,-.6,0.],[.15,-.6]);self.service.worker.join(5)
        job=self.service.snapshot('owner')['job'];self.assertEqual(job['state'],'FAILED')
        self.assertEqual(job['error'],'COMPARISON_PROCESSING_FAILED');self.assertEqual(job['error_errno'],errno.ENOSPC)
        self.assertEqual(job['report_error'],'COMPARISON_REPORT_SAVE_FAILED');self.assertEqual(job['report_errno'],errno.ENOENT)
        self.assertNotIn('private data',json.dumps(job))

if __name__=='__main__':unittest.main()
