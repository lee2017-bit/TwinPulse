# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""App no-motion collector tests; no SSH, deployment or robot hardware."""
import json
import hashlib
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import subprocess

from twinpulse_app.command_broker import BrokerError
from twinpulse_app.robot_readiness import RobotReadiness
from tests.integration import test_r5_product_api as r5


def receipt(status='EVIDENCE_GAPS'):
    return {'schema_version': 'robot-readiness-1.0', 'run_requested': True,
            'motion_authorized': False, 'demo_ready': False, 'status': status,
            'steps': {'source_and_idle': {'status': 'SOFTWARE_PREPARED_IDLE'},
                      'stationary_collection': {'status': 'STATIONARY_CHECK_PASS'},
                      'evidence_review': {'status': status}},
            'evidence': {'odom': {'status': 'REJECTED'},
                         'scan': {'status': 'NOT_RECEIVED', 'reason': 'NO_PUBLISHER'},
                         'tf': {'status': 'NOT_RECEIVED'},
                         'room_alignment': 'NOT_VERIFIED'}}


def precollection_fixture(root):
    """Generic persisted CLI prepare failure, not a qualified robot fixture."""
    child=root/'artifacts/robot-preparation/20261001T000001Z-aaaaaaaa/result/report.json'
    child.parent.mkdir(parents=True)
    child.write_text(json.dumps({'schema_version':'robot-prepare-1.0','action':'prepare',
        'status':'PREPARED_NEEDS_ATTENTION','motion_authorized':False,'finished_at_utc':'2026-10-01T00:00:02Z'}),encoding='utf-8')
    report=root/'artifacts/robot-readiness/20261001T000000Z-bbbbbbbb/report.json'
    report.parent.mkdir(parents=True)
    skipped={'status':'NOT_RUN','reason':'DEPENDENCY_NOT_SATISFIED: STOPPED_AT_SOURCE_AND_IDLE'}
    result={'schema_version':'robot-readiness-1.0','status':'STOPPED_AT_SOURCE_AND_IDLE',
        'scope':'NO_MOTION_COLLECTION','run_requested':True,'motion_authorized':False,'demo_ready':False,
        'steps':{'offline_collection_preflight':{'status':'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED'},
            'source_and_idle':{'status':'PREPARED_NEEDS_ATTENTION','exit_code':2,'report_path':str(child),
                'failure_diagnostics':None},'stationary_collection':dict(skipped),'evidence_review':dict(skipped)},
        'remaining_gates':{'ros_lidar_driver_and_physical_stop':'NOT_RUN_SEPARATE_APPROVAL',
            'sensor_chassis_room_alignment':'NOT_VERIFIED','local_collision_protection':'NOT_VERIFIED',
            'scoped_autonomous_mission':'LOCKED'},
        'offline_collection_preflight':{'schema_version':'robot-collection-offline-preflight-1.0',
            'status':'COLLECTION_CONTRACTS_PASS_DEMO_LOCKED','motion_authorized':False,'demo_ready':False,
            'hardware_validation':'NOT_RUN'},'reason':'Preparation requires attention; no stationary collection ran.'}
    report.write_text(json.dumps(result),encoding='utf-8')
    path=root/'artifacts/robot-readiness-app/current.json';path.parent.mkdir(parents=True)
    state={'schema_version':'robot-readiness-app-1.0','status':'REMOTE_STATE_UNKNOWN','project_id':'default',
        'job_id':'a'*32,'owner':'test-owner','motion_authorized':False,'demo_ready':False,'exit_code':2,
        'app_context':{'app_scene_revision':None,'app_robot_profile_id':None,'capture_status':'CAPTURED'},
        'started_at_utc':'2026-10-01T00:00:00Z','finished_at_utc':'2026-10-01T00:00:03Z',
        'report_path':str(report),'result':result,'evidence_recovery':{'status':'NOT_STARTED','transfer_only':True},
        'transfer_requests':{}}
    path.write_text(json.dumps(state),encoding='utf-8')
    return path,report,child


class ReadinessServiceTests(unittest.TestCase):
    def test_stationary_twin_context_is_versioned_historical_reference_not_authority(self):
        from twinpulse_core import canonical_sha256
        with tempfile.TemporaryDirectory() as tmp:
            context=dict(schema_version='scene-sensor-context-1.0',project_id='default',input_revision='1'*64,
                source_sha256='2'*64,current_scene_revision='3'*64,current_state_sha256='4'*64,physical_authority=False)
            report=Path(tmp)/'artifacts/robot-readiness/20261015T000000Z-f1111111/report.json'
            report.parent.mkdir(parents=True);report.write_text(json.dumps(receipt()),encoding='utf-8')
            service=RobotReadiness(tmp,runner=lambda:(receipt(),str(report),2))
            service.start('owner','f'*32,True,time.time()*1000+1000,twin_context=context)
            service._thread.join(3)
            binding=service.snapshot('owner')['twin_collection_binding']
            self.assertEqual(binding['context'],context)
            self.assertEqual(binding['context_sha256'],canonical_sha256(context))
            self.assertTrue(binding['historical_reference_only']);self.assertFalse(binding['alignment_verified'])
            self.assertFalse(binding['physical_authority'])
            self.assertEqual(service.snapshot('owner')['twin_collection_receipt']['status'],'RECORDED')
            terminal=recorded=Path(tmp)/'artifacts/robot-readiness-app/collection-bindings'/('f'*32+'.result.json')
            result_record=json.loads(terminal.read_text(encoding='utf-8'))
            self.assertEqual(result_record['readiness_report_sha256'],hashlib.sha256(report.read_bytes()).hexdigest())
            self.assertEqual(result_record['start_reference_sha256'],binding['record_sha256'])
            restored=RobotReadiness(tmp,runner=lambda:self.fail('read must not collect'))
            self.assertEqual(restored.snapshot(None)['twin_collection_binding'],binding)
            record=Path(tmp)/'artifacts/robot-readiness-app/collection-bindings'/('f'*32+'.json')
            original=record.read_bytes()
            service.start('owner','e'*32,True,time.time()*1000+1000,
                twin_context={**context,'current_state_sha256':'5'*64})
            service._thread.join(3)
            self.assertEqual(record.read_bytes(),original)
            archived=json.loads(original)
            self.assertEqual(archived['context'],context)
            self.assertEqual(archived.pop('sha256'),canonical_sha256(archived))
            self.assertNotEqual(service.snapshot('owner')['twin_collection_binding']['context_sha256'],binding['context_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            service=RobotReadiness(tmp,runner=lambda:self.fail('wrong project must not collect'))
            with self.assertRaises(BrokerError):
                service.start('owner','f'*32,True,time.time()*1000+1000,twin_context=context,project_id='other')

    def test_terminal_precollection_separates_only_saved_sim_and_preserves_real_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=precollection_fixture(Path(tmp));before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            service=RobotReadiness(tmp,runner=lambda:self.fail('collector must never run'))
            self.assertTrue(service.blocks_robot_operation())
            self.assertTrue(service.blocks_scene_edit())
            self.assertFalse(service.blocks_scene_edit(saved_sim_scope=True))
            self.assertTrue(service.blocks_robot_operation())
            self.assertEqual(service.snapshot(None)['status'],'REMOTE_STATE_UNKNOWN')
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
            for name in ('_thread','_resume_thread'):
                setattr(service,name,SimpleNamespace(is_alive=lambda:True))
                self.assertTrue(service.blocks_scene_edit(saved_sim_scope=True))
                setattr(service,name,None)

    def test_sim_exception_rejects_missing_contradictory_restart_transfer_and_authority_records(self):
        variants=('finished','exit','time','context','profile','mode_authority','collection','evidence','extra_authority',
            'report_mismatch','child_action','child_stationary','child_time','child_missing','restart','transfer','error')
        for variant in variants:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                path,report,child=precollection_fixture(Path(tmp));state=json.loads(path.read_text())
                result=state['result'];source=json.loads(child.read_text())
                if variant=='finished':state.pop('finished_at_utc')
                elif variant=='exit':state['exit_code']=0
                elif variant=='time':state['finished_at_utc']='2026-10-01T00:00:03'
                elif variant=='context':state['app_context']['app_scene_revision']='b'*64
                elif variant=='profile':state['app_context']['app_robot_profile_id']='burger3'
                elif variant=='mode_authority':state['motion_authorized']=True
                elif variant=='collection':result['steps']['stationary_collection']['status']='RUNNING'
                elif variant=='evidence':result['steps']['evidence_review']['status']='CAPTURED_UNALIGNED'
                elif variant=='extra_authority':result['alignment_verified']=True
                elif variant=='report_mismatch':result['reason']='Changed after receipt'
                elif variant=='child_action':source['action']='stationary'
                elif variant=='child_stationary':source['stationary']={'observation':{}}
                elif variant=='child_time':source['finished_at_utc']='2026-10-01T00:00:04Z'
                elif variant=='child_missing':child.unlink()
                elif variant=='restart':state['status']='RUNNING'
                elif variant=='transfer':state['evidence_recovery']['status']='INTERRUPTED'
                elif variant=='error':state['result']={'status':'OSError'}
                path.write_text(json.dumps(state),encoding='utf-8')
                if variant!='report_mismatch':report.write_text(json.dumps(state['result']),encoding='utf-8')
                if variant!='child_missing':child.write_text(json.dumps(source),encoding='utf-8')
                service=RobotReadiness(tmp,runner=lambda:self.fail('collector must never run'))
                self.assertTrue(service.blocks_robot_operation())
                self.assertTrue(service.blocks_scene_edit(saved_sim_scope=True))

    def test_not_started_does_not_block_scene_edit_but_a_live_collector_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=RobotReadiness(tmp,runner=lambda:self.fail('collector ran'))
            self.assertFalse(service.blocks_scene_edit())
            service._thread=SimpleNamespace(is_alive=lambda:True)
            self.assertTrue(service.blocks_scene_edit(saved_sim_scope=True))

    def transfer_fixture(self,root,runner=None):
        source=root/'artifacts/robot-preparation/20261005T000000Z-aaaaaaaa/result/report.json'
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps({'schema_version':'robot-prepare-1.0','action':'stationary','status':'EVIDENCE_EXPORT_INCOMPLETE',
            'motion_authorized':False,'run_id':'saved-stationary','boot_id':'boot','release_id':'release'}))
        data=receipt()
        data['steps']['stationary_collection'].update(status='EVIDENCE_EXPORT_INCOMPLETE',report_path=str(source))
        service=RobotReadiness(root,runner=lambda:(data,str(root/'report.json'),2),resume_runner=runner)
        service.start('owner','a'*32,True,time.time()*1000+1000);service._thread.join(3)
        return service,source

    def transfer_receipt(self,status='COMPLETE'):
        return {'schema_version':'robot-evidence-export-1','run_id':'saved-stationary','status':status,
            'files':{'raw':{'status':'COPIED'}},'report_binding':{'status':'VERIFIED_SAME_RUN'},'raw_replay':{'status':'VERIFIED_OFFLINE'}}

    def test_transfer_resume_preserves_original_collection_and_durable_no_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            service,source=self.transfer_fixture(Path(tmp),lambda path:(calls.append(path) or self.transfer_receipt()))
            original=source.read_bytes()
            service.resume_evidence('owner','a'*32,'b'*32,time.time()*1000+1000)
            service._resume_thread.join(3)
            self.assertEqual(service.snapshot('owner')['evidence_recovery']['status'],'COMPLETE')
            self.assertEqual(service.snapshot('owner')['result']['status'],'EVIDENCE_GAPS')
            self.assertEqual(source.read_bytes(),original)
            reopened=RobotReadiness(tmp,runner=lambda:self.fail('collector replay'),resume_runner=lambda path:self.fail('transfer replay'))
            reopened.resume_evidence('new-owner','a'*32,'b'*32,time.time()*1000+1000)
            self.assertEqual(len(calls),1)
            self.assertFalse(reopened.snapshot('new-owner')['demo_ready'])

    def test_transfer_outside_path_and_wrong_job_rejected_before_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,source=self.transfer_fixture(Path(tmp),lambda path:self.fail('unsafe transfer'))
            with self.assertRaises(BrokerError):service.resume_evidence('owner','c'*32,'b'*32,time.time()*1000+1000)
            service._state['result']['steps']['stationary_collection']['report_path']=str(Path(tmp)/'outside.json')
            with self.assertRaises(BrokerError):service.resume_evidence('owner','a'*32,'b'*32,time.time()*1000+1000)
            self.assertIsNone(service._resume_thread)

    def test_transfer_failed_reservation_never_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,_=self.transfer_fixture(Path(tmp),lambda path:self.fail('unreserved transfer'))
            with patch.object(service,'_persist',side_effect=OSError('disk full')):
                with self.assertRaises(BrokerError):service.resume_evidence('owner','a'*32,'b'*32,time.time()*1000+1000)
            self.assertIsNone(service._resume_thread)
            self.assertEqual(service.snapshot('owner')['evidence_recovery']['status'],'INCOMPLETE')

    def test_changed_source_and_unverified_complete_receipt_rejected(self):
        for variant in ('source','receipt'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                def resume(path):
                    value=self.transfer_receipt()
                    if variant=='source':path.write_text(path.read_text()+' ')
                    else:value['report_binding']['status']='REJECTED'
                    return value
                service,_=self.transfer_fixture(Path(tmp),resume)
                service.resume_evidence('owner','a'*32,'b'*32,time.time()*1000+1000);service._resume_thread.join(3)
                self.assertEqual(service.snapshot('owner')['evidence_recovery']['status'],'INCOMPLETE')
                self.assertFalse(service.snapshot('owner')['demo_ready'])

    def test_resume_cli_is_transfer_only_and_receipt_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            service,source=self.transfer_fixture(Path(tmp),lambda path:self.fail('injected runner unused'))
            target=source.parent.parent/'robot-evidence/export.json';target.parent.mkdir()
            target.write_text(json.dumps(self.transfer_receipt()))
            calls=[]
            def fake(command,**kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command,0,b'',b'')
            with patch('twinpulse_app.robot_readiness.subprocess.run',fake):service._run_resume_cli(source)
            index=calls[0].index('--mode')
            self.assertEqual(calls[0][index:index+4],['--mode','resume-evidence','--saved-report',str(source)])
            self.assertEqual(calls[0][calls[0].index('--host')+1],'192.168.35.139')
            self.assertNotIn('--run',calls[0]);self.assertNotIn('--disable-torque',calls[0])

    def test_known_local_failure_does_not_become_remote_uncertainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=receipt('STOPPED_AT_OFFLINE_PREFLIGHT')
            service=RobotReadiness(tmp,runner=lambda:(data,None,2))
            service.start('owner','a'*32,True,time.time()*1000+1000);service._thread.join(3)
            self.assertEqual(service.snapshot('owner')['status'],'BLOCKED_LOCAL')
            self.assertFalse(service.blocks_robot_operation())
            self.assertFalse(service.snapshot('owner')['demo_ready'])

    def test_cli_adapter_uses_only_fixed_one_run_and_validates_saved_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / 'artifacts/robot-readiness/20260930T000000Z-aaaaaaaa/report.json'
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps(receipt()), encoding='utf-8')
            seen = []
            def fake(command, **kwargs):
                seen.append((command, kwargs))
                return subprocess.CompletedProcess(command, 2,
                    ('Report: ' + str(report.with_name('report.html')) + '\n').encode(), b'')
            service = RobotReadiness(root)
            with patch('twinpulse_app.robot_readiness.subprocess.run', fake):
                result, path, exit_code = service._run_cli()
            self.assertEqual(result['status'], 'EVIDENCE_GAPS')
            self.assertEqual(path, str(report))
            self.assertEqual(exit_code, 2)
            self.assertIn(str(root / 'scripts/run_robot_readiness.py'),seen[0][0])
            self.assertEqual(seen[0][0].count('--run'),1)
            self.assertEqual(seen[0][0][seen[0][0].index('--host')+1],'192.168.35.139')
            self.assertNotIn('--allow-torque-off', seen[0][0])
            self.assertEqual(seen[0][1]['stdin'], subprocess.DEVNULL)

    def test_single_flight_duplicate_and_reopen_saved_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            entered, release = Event(), Event()
            calls = []
            def runner():
                calls.append(1); entered.set(); release.wait(3)
                return receipt(), str(Path(tmp) / 'report.json'), 2
            service = RobotReadiness(tmp, runner=runner)
            job = 'a' * 32
            try:
                state = service.start('owner', job, True, time.time() * 1000 + 1000)
                self.assertTrue(entered.wait(2))
                self.assertEqual(state['status'], 'RUNNING')
                self.assertEqual(service.start('owner', job, True, time.time() * 1000 + 1000)['job_id'], job)
                with self.assertRaises(BrokerError):
                    service.start('owner', 'b' * 32, True, time.time() * 1000 + 1000)
                self.assertEqual(len(calls), 1)
            finally:
                release.set(); service._thread.join(3)
            self.assertEqual(service.snapshot('owner')['status'], 'COMPLETED_WITH_GAPS')
            self.assertEqual(service.snapshot('other')['result']['status'], 'EVIDENCE_GAPS')
            self.assertFalse(service.snapshot('owner')['demo_ready'])
            reopened = RobotReadiness(tmp, runner=lambda: self.fail('GET/reopen ran collector'))
            self.assertEqual(reopened.snapshot('owner')['result']['status'], 'EVIDENCE_GAPS')

    def test_collection_job_retains_project_scene_reference_without_motion_claim(self):
        context = {'app_scene_revision': 'a' * 64, 'app_robot_profile_id': 'burger3',
                   'capture_status': 'CAPTURED'}
        with tempfile.TemporaryDirectory() as tmp:
            service = RobotReadiness(tmp, runner=lambda: (receipt(), str(Path(tmp) / 'report.json'), 2))
            state = service.start('owner', 'd' * 32, True, time.time() * 1000 + 1000,
                                  app_context=context)
            service._thread.join(3)
            self.assertEqual(state['project_id'], 'default')
            self.assertEqual(service.snapshot('other')['app_context'], context)
            reopened = RobotReadiness(tmp, runner=lambda: self.fail('reopen ran collector'))
            self.assertEqual(reopened.snapshot('other')['app_context'], context)
            self.assertFalse(reopened.snapshot('other')['motion_authorized'])

    def test_invalid_app_context_rejected_before_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RobotReadiness(tmp, runner=lambda: self.fail('collector ran'))
            with self.assertRaises(BrokerError):
                service.start('owner', 'd' * 32, True, time.time() * 1000 + 1000,
                              app_context={'app_scene_revision': 'not-a-revision'})
            self.assertEqual(service.snapshot('owner')['status'], 'NOT_STARTED')

    def test_restart_running_stays_uncertain_until_explicit_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'artifacts/robot-readiness-app/current.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'schema_version': 'robot-readiness-app-1.0',
                'status': 'RUNNING', 'job_id': 'a' * 32, 'owner': 'owner',
                'demo_ready': False, 'motion_authorized': False,
                'result': None, 'report_path': None}), encoding='utf-8')
            service = RobotReadiness(tmp, runner=lambda: self.fail('unexpected collector'))
            self.assertTrue(service.blocks_robot_operation())
            with self.assertRaises(BrokerError):
                service.start('owner', 'b' * 32, True, time.time() * 1000 + 1000)
            with self.assertRaises(BrokerError):
                service.clear_uncertain('owner', False, time.time() * 1000 + 1000)
            self.assertEqual(service.clear_uncertain('owner', True, time.time() * 1000 + 1000)['status'],
                             'CLEARED_AFTER_OPERATOR_OFF')

    def test_rejects_invalid_result_and_never_grants_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = dict(receipt(), demo_ready=True)
            service = RobotReadiness(tmp, runner=lambda: (bad, None, 0))
            service.start('owner', 'a' * 32, True, time.time() * 1000 + 1000)
            service._thread.join(3)
            self.assertEqual(service.snapshot('owner')['status'], 'REMOTE_STATE_UNKNOWN')
            self.assertFalse(service.snapshot('owner')['demo_ready'])

    def test_status_exit_conflict_is_uncertain_not_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RobotReadiness(tmp, runner=lambda: (receipt('NO_MOTION_COLLECTION_COMPLETE'), None, 2))
            service.start('owner', 'a' * 32, True, time.time() * 1000 + 1000)
            service._thread.join(3)
            self.assertEqual(service.snapshot('owner')['status'], 'REMOTE_STATE_UNKNOWN')
            self.assertFalse(service.snapshot('owner')['demo_ready'])


class ReadinessHttpTests(unittest.TestCase):
    request = r5.R5ProductApiTests.request

    def setUp(self):
        r5.R5ProductApiTests.setUp(self)
        self.calls = []
        self.service = RobotReadiness(self.static, runner=lambda: (self.calls.append(1) or receipt(),
                                                                  str(self.static / 'fake-report.json'), 2))
        self.server.robot_readiness = self.service
        self.headers = {'Cookie': self.cookie, 'X-TwinPulse-CSRF': self.csrf, 'Origin': self.server.base_url}

    def tearDown(self):
        r5.R5ProductApiTests.tearDown(self)

    def test_authenticated_single_start_and_saved_gap(self):
        path = '/v1/product/robot/readiness'
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request(path + '/start', {}, headers={'Cookie': self.cookie})[0], 403)
        self.assertEqual(self.request(path, headers=self.headers)[0], 200)
        self.assertEqual(self.calls, [])
        body = {'request_id': 'a' * 32, 'confirmed_no_motion_deployment': True,
                'expires_at_ms': time.time() * 1000 + 1000}
        self.assertEqual(self.request(path + '/start', {**body, 'host': 'other'}, headers=self.headers)[0], 400)
        code, _, _ = self.request(path + '/start', body, headers=self.headers)
        self.assertEqual(code, 202)
        self.service._thread.join(3)
        code, state, _ = self.request(path, headers=self.headers)
        self.assertEqual(code, 200)
        self.assertEqual(state['status'], 'COMPLETED_WITH_GAPS')
        self.assertFalse(state['demo_ready'])
        self.assertEqual(self.calls, [1])

    def test_http_collection_captures_current_app_scene_reference(self):
        body = {'request_id': 'e' * 32, 'confirmed_no_motion_deployment': True,
                'expires_at_ms': time.time() * 1000 + 1000}
        with patch.object(self.server.product_workflow, 'snapshot', return_value={
                'site_draft': {'revision': 'b' * 64, 'robot_profile_id': 'burger3'}}):
            code, state, _ = self.request('/v1/product/robot/readiness/start', body, headers=self.headers)
        self.assertEqual(code, 202)
        self.assertEqual(state['app_context']['app_scene_revision'], 'b' * 64)
        self.service._thread.join(3)
        code, saved, _ = self.request('/v1/product/robot/readiness', headers=self.headers)
        self.assertEqual(code, 200)
        self.assertEqual(saved['app_context']['app_robot_profile_id'], 'burger3')
        self.assertEqual(saved['project_id'], 'default')

    def test_no_motion_and_physical_start_are_mutually_exclusive(self):
        class Physical:
            def __init__(self):
                self.busy = False
                self.calls = 0
                self.evidence_recovery = SimpleNamespace(snapshot=lambda _owner: {'status': 'NOT_STARTED'})
            def snapshot(self, _owner): return {'busy': self.busy}
            def start(self, *_args, **_kwargs):
                self.calls += 1
                return {'busy': True}
            def close(self): pass
        physical = Physical()
        self.server.physical_controller = physical
        physical.busy = True
        body = {'request_id': 'b' * 32, 'confirmed_no_motion_deployment': True,
                'expires_at_ms': time.time() * 1000 + 1000}
        self.assertEqual(self.request('/v1/product/robot/readiness/start', body, headers=self.headers)[0], 409)
        self.assertEqual(self.calls, [])
        physical.busy = False
        self.service._state['status'] = 'REMOTE_STATE_UNKNOWN'
        physical_body = {'mode': 'prepare', 'request_id': 'c' * 32, 'confirmed': True,
                         'expires_at_ms': time.time() * 1000 + 1000}
        self.assertEqual(self.request('/v1/product/robot/physical/start', physical_body,
                                      headers=self.headers)[0], 409)
        self.assertEqual(physical.calls, 0)

    def test_direct_mission_start_cannot_bypass_uncertain_readiness(self):
        self.service._state['status']='REMOTE_STATE_UNKNOWN'
        with patch.object(self.server.automatic_mission,'start') as start:
            code,value,_=self.request('/v1/product/automatic-demo/mission-start',
                {'map_id':None,'goal':{'x':0,'y':0}},headers=self.headers)
        self.assertEqual(code,409);self.assertEqual(value['error']['code'],'readiness_busy_or_uncertain')
        start.assert_not_called();self.assertEqual(self.calls,[])


if __name__ == '__main__':
    unittest.main()
