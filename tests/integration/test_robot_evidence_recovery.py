# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Transfer-only App recovery tests with no SSH or robot operation."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from tests.integration import test_r5_product_api
from tests.integration.test_physical_controller import history_fixture
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.robot_evidence_export import export_finished_session
from twinpulse_app.session_history import index_project_session


def saved_report(root, job):
    target = Path(root)/'artifacts/manual-control'/job
    target.mkdir(parents=True)
    report = {'robot_session_id':'manual-'+'b'*32,'mode':'control',
              'boot_id':'boot-fixture','release_id':'release-fixture'}
    (target/'robot-report.json').write_text(json.dumps(report), encoding='utf-8')
    return target


def settled(recovery):
    recovery.thread.join(timeout=2)
    assert not recovery.thread.is_alive()


class RecoveryTests(unittest.TestCase):
    def test_saved_report_retry_is_transfer_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            job='a'*32
            saved_report(directory,job)
            exports=[]
            def exporter(report,destination):
                exports.append((report['robot_session_id'],destination))
                return {'status':'INCOMPLETE' if len(exports)==1 else 'COMPLETE'}
            calls=[]
            controller=PhysicalController(directory,factory=lambda *a,**k:calls.append(a),
                                          command=lambda *_:['fake'])
            controller.evidence_recovery.exporter=exporter
            first=controller.resume_evidence('owner',job,'c'*32)
            self.assertIn(first['status'],{'TRANSFERRING','INCOMPLETE'})
            settled(controller.evidence_recovery)
            self.assertEqual(controller.snapshot('owner')['evidence_recovery']['status'],'INCOMPLETE')
            self.assertEqual(controller.resume_evidence('owner',job,'c'*32)['status'],'INCOMPLETE')
            self.assertEqual(len(exports),1)
            controller.resume_evidence('owner',job,'d'*32)
            settled(controller.evidence_recovery)
            self.assertEqual(controller.snapshot('owner')['evidence_recovery']['status'],'COMPLETE')
            self.assertEqual(controller.snapshot('other')['evidence_recovery']['status'],'NOT_STARTED')
            self.assertEqual(len(exports),2)
            self.assertEqual(calls,[])

    def test_invalid_or_missing_report_cannot_start_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=PhysicalController(directory,factory=lambda *a,**k:self.fail('robot process started'),
                                          command=lambda *_:['fake'])
            for job in ('../wrong','a'*32):
                with self.assertRaises(BrokerError):
                    controller.resume_evidence('owner',job,'c'*32)
            target=saved_report(directory,'a'*32)
            (target/'robot-report.json').write_text('{}',encoding='utf-8')
            with self.assertRaises(BrokerError):
                controller.resume_evidence('owner','a'*32,'c'*32)

    def test_active_operation_blocks_transfer_before_exporter(self):
        with tempfile.TemporaryDirectory() as directory:
            job='a'*32
            saved_report(directory,job)
            controller=PhysicalController(directory,factory=lambda *a,**k:self.fail('robot process started'),
                                          command=lambda *_:['fake'])
            controller.evidence_recovery.exporter=lambda *_:self.fail('transfer started')
            class Busy:
                def is_alive(self):return True
            controller.thread=Busy()
            with self.assertRaisesRegex(BrokerError,'Wait for the current operation or transfer'):
                controller.resume_evidence('owner',job,'c'*32)


class RecoveryHttpTests(unittest.TestCase):
    request=test_r5_product_api.R5ProductApiTests.request
    setUp=test_r5_product_api.R5ProductApiTests.setUp
    tearDown=test_r5_product_api.R5ProductApiTests.tearDown

    def test_offline_release_inventory_requires_review_code_and_raw_reader(self):
        root=Path(__file__).resolve().parents[2]
        build=(root/'scripts/build_offline_release.ps1').read_text(encoding='utf-8')
        install=(root/'scripts/install_twinpulse_offline.ps1').read_text(encoding='utf-8')
        for name in ('inspect_robot_evidence.py','ros_message_diagnostics.py','raw_ros_record.py'):
            self.assertIn(name,build)
            self.assertIn(name,install)

    def test_saved_evidence_review_is_authenticated_offline_and_rechecks_files(self):
        with tempfile.TemporaryDirectory() as directory:
            job='a'*32
            calls=[]
            controller=PhysicalController(directory,factory=lambda *a,**k:calls.append(a),
                                          command=lambda *_:['fake'])
            self.server.physical_controller=controller
            self.server.session_history_root=Path(directory)
            path='/v1/product/robot/physical/evidence/review/'+job
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,headers={'Cookie':self.cookie})[0],409)
            out,rows=history_fixture(directory,job)
            rows.insert(0,{**rows[0],'event_index':1,'t':999.,'kind':'pc_session_started',
                           'data':{'mode':'control','project_id':'default'}})
            for n,row in enumerate(rows,1):row['event_index']=n
            (out/'session.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
            (out/'result.json').write_text(json.dumps({'session_log_complete':True,
                'session_event_count':4,'real_transport':False}),encoding='utf-8')
            index_project_session(directory,'default',job)
            status,missing,_=self.request(path,headers={'Cookie':self.cookie})
            self.assertEqual(status,200)
            self.assertEqual(missing['reason'],'EVIDENCE_NOT_EXPORTED')
            self.assertEqual(self.request(path+'bad',headers={'Cookie':self.cookie})[0],400)
            self.assertEqual(self.request(path+'?ignored=1',headers={'Cookie':self.cookie})[0],400)
            report={'robot_session_id':'manual-'+'b'*32,'mode':'off',
                    'boot_id':'boot-fixture','release_id':'release-fixture'}
            base=Path(directory)
            key,known=base/'key',base/'known'
            key.write_text('fixture');known.write_text('fixture')
            def fake_transfer(command,**_):
                name=Path(command[-1]).name.removesuffix('.part')
                Path(command[-1]).write_text(json.dumps(report) if name=='report.json' else name)
                return subprocess.CompletedProcess(command,0,b'',b'')
            destination=base/'artifacts/manual-control'/job/'robot-evidence'
            self.assertEqual(export_finished_session(report,destination,runner=fake_transfer,
                                                      scp='scp',key=key,known=known)['status'],'COMPLETE')
            status,review,_=self.request(path,headers={'Cookie':self.cookie})
            self.assertEqual(status,200)
            self.assertEqual(review['status'],'COMPLETE')
            self.assertEqual(review['job_id'],job)
            self.assertEqual(review['physical_validation'],'NOT_RUN_BY_THIS_TOOL')
            self.assertEqual(review['raw_ros']['status'],'NOT_CAPTURED')
            self.assertNotIn(str(base),json.dumps(review))
            (destination/'off.log').write_text('tampered')
            status,damaged,_=self.request(path,headers={'Cookie':self.cookie})
            self.assertEqual(status,200)
            self.assertEqual(damaged['status'],'INCOMPLETE')
            self.assertEqual(damaged['files']['off.log'],'HASH_OR_SIZE_MISMATCH')
            (destination/'export.json').write_text('{broken',encoding='utf-8')
            status,malformed,_=self.request(path,headers={'Cookie':self.cookie})
            self.assertEqual(status,200)
            self.assertEqual(malformed['status'],'INCOMPLETE')
            self.assertEqual(malformed['reason'],'EVIDENCE_INSPECTION_ERROR')
            self.assertNotIn(str(base),json.dumps(malformed))
            self.assertEqual(calls,[])

    def test_saved_evidence_review_rejects_other_project_index(self):
        with tempfile.TemporaryDirectory() as directory:
            job='b'*32
            out,rows=history_fixture(directory,job)
            rows.insert(0,{**rows[0],'event_index':1,'t':999.,'kind':'pc_session_started',
                           'data':{'mode':'control','project_id':'other-room'}})
            for n,row in enumerate(rows,1):row['event_index']=n
            (out/'session.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
            (out/'result.json').write_text(json.dumps({'session_log_complete':True,
                'session_event_count':4,'real_transport':False}),encoding='utf-8')
            index_project_session(directory,'other-room',job)
            self.server.physical_controller=PhysicalController(directory,factory=lambda *_:self.fail('robot started'),
                                                                command=lambda *_:['fake'])
            self.server.session_history_root=Path(directory)
            path='/v1/product/robot/physical/evidence/review/'+job
            self.assertEqual(self.request(path,headers={'Cookie':self.cookie})[0],409)

    def test_authenticated_explicit_resume_never_starts_robot_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            job='a'*32
            saved_report(directory,job)
            calls=[]
            controller=PhysicalController(directory,factory=lambda *a,**k:calls.append(a),
                                          command=lambda *_:['fake'])
            controller.evidence_recovery.exporter=lambda _report,_destination:{'status':'COMPLETE'}
            self.server.physical_controller=controller
            path='/v1/product/robot/physical/evidence/resume'
            body={'job_id':job,'request_id':'d'*32}
            self.assertEqual(self.request(path,body)[0],401)
            self.assertEqual(self.request(path,body,headers={'Cookie':self.cookie})[0],403)
            headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
            self.assertEqual(self.request(path,{**body,'mode':'control'},headers=headers)[0],400)
            self.assertEqual(self.request(path,body,headers=headers)[0],202)
            settled(controller.evidence_recovery)
            status,response,_=self.request('/v1/product/robot/physical',headers={'Cookie':self.cookie})
            self.assertEqual(status,200)
            self.assertEqual(response['evidence_recovery']['status'],'COMPLETE')
            self.assertEqual(calls,[])
