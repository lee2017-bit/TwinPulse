# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual PC/robot subprocess exchange; synthetic output-reactive sensors only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.automatic_photo_store import load_automatic_room
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.remote_observed_adapter import RemoteObservedAdapter
from twinpulse_app.session_history import review_session
from twinpulse_core.adaptive_mission_contract import nominal_room
from tests.integration.test_automatic_photo_service import recipe
from tests.integration.test_automatic_demo_service import GEOMETRY
from tests.fixtures.observed_robot_process import fixture_evidence_exporter
from twinpulse_core.mission_evidence_contract import replay_mission_evidence,decode_evidence

ROOT=Path(__file__).resolve().parents[2]


class RemoteCorrectionTests(unittest.TestCase):
    def execute(self,root,*,failure=False,stop_commit=False,survey_only=False,diagnostics=False,slow_record=False):
        outline,_=recipe(root,'remote_room',1.);peer=root/'peer';peer.mkdir()
        (peer/'synthetic-world.json').write_text(json.dumps({'vertices':[a for a,_ in outline['segments']],'start':[0.,-.6,0.]}))
        controller=PhysicalController(root,command=lambda _r,_m:[sys.executable,'-B',str(ROOT/'tests/fixtures/observed_robot_process.py'),str(peer)],
            evidence_exporter=fixture_evidence_exporter(peer))
        self.addCleanup(controller.close)
        automatic=AutomaticDemoService(root,'remote_room',geometry_loader=lambda:GEOMETRY);self.addCleanup(automatic.close)
        adapters=[]
        def factory(prior,room,effective,goal):
            value={'schema':'observed-mission-scope-4.0' if survey_only else 'observed-mission-scope-2.0','project_id':'remote_room','goal':goal,'reference':None,'alignment':None,
                   'nominal':nominal_room(effective['objects'],.182,effective['effective_revision'])}
            adapter=RemoteObservedAdapter(controller,lambda _:{},value)
            if slow_record:
                original_run=adapter.run
                delayed=[False]
                def delayed_run(*,record,visual,safety):
                    def record_after_delay(kind,**data):
                        if kind=='mission_started' and not delayed[0]:
                            delayed[0]=True
                            time.sleep(.35)  # PC report callback only; native gate stays 250ms.
                        record(kind,**data)
                    return original_run(record=record_after_delay,visual=visual,safety=safety)
                adapter.run=delayed_run
            adapters.append(adapter);return adapter
        factory.supports_remote_correction=True
        service=AutomaticMissionService(automatic,adapter_factory=factory);self.addCleanup(service.close)
        if diagnostics:
            from twinpulse_core.execution_diagnostics import ExecutionStore
            store=ExecutionStore(root/'diagnostics','remote_room')
            service.diagnostics=store
            self.addCleanup(store.flush)
        if failure:
            automatic.photo_store.append=lambda *_a,**_k:(_ for _ in ()).throw(ValueError('PHOTO_LEDGER_HEAD_CHANGED'))
        if stop_commit:
            original=automatic.photo_store.append
            def stop_before_append(*a,**kw):
                service.stop('browser',service.job['job_id'],True)
                raise ValueError('MISSION_CORRECTION_CANCELLED_OR_EXPIRED')
            automatic.photo_store.append=stop_before_append
        goal={'mode':'SURVEY_ONLY' if survey_only else 'SURVEY_THEN_NAVIGATE','xy':[0.,0.] if survey_only else [.15,-.6],'room_revision':service.readiness(None)['room_revision'],'duration_s':45.}
        original=copy.deepcopy(goal);job=service.start('browser',None,goal,'correct_walls')['job'];deadline=time.monotonic()+65
        while service.worker.is_alive() and time.monotonic()<deadline:
            service.snapshot('browser');service.worker.join(.03)
        self.assertFalse(service.worker.is_alive(),'offline peer did not finish')
        result=service.snapshot('browser')['job']
        if diagnostics:
            self.assertTrue(store.flush())
            entries=store.list()['executions']
            self.assertEqual(len(entries),1)
            self.trace_detail=store.detail(entries[0]['execution_id'])
        report_path=root/'artifacts/automatic-mission/remote_room'/f"{job['job_id']}.json"
        report=json.loads(report_path.read_text())
        name=os.environ.get('TWINPULSE_REMOTE_CORRECTION_EVIDENCE')
        destination=None
        if name:
            self.assertRegex(name,'^[a-z0-9-]{1,100}$');case='slow-record' if slow_record else 'survey-diagnostics' if survey_only and diagnostics else 'survey' if survey_only else 'stop' if stop_commit else 'rejected' if failure else 'arrived'
            destination=ROOT/'artifacts'/name/case;destination.mkdir(parents=True,exist_ok=False)
            # Retain original bytes BEFORE assertions; failure must not erase
            # its evidence when TemporaryDirectory is cleaned up. No PASS yet.
            early={'mission-report.json':report_path.read_bytes(),'scope.json':json.dumps(adapters[0].scope,sort_keys=True).encode(),
                   'published.json':(peer/'published.json').read_bytes()}
            for p in (root/'artifacts/manual-control'/job['job_id']).iterdir():
                if p.is_file() and p.name in {'robot-report.json','session.jsonl','result.json','stderr.log'}:early[p.name]=p.read_bytes()
            if (peer/'mission-evidence.json').is_file():early['mission-evidence.json']=(peer/'mission-evidence.json').read_bytes()
            if diagnostics:
                early['execution-detail.json']=json.dumps(self.trace_detail,sort_keys=True).encode()
                early['execution-export.json']=json.dumps(store.export(entries[0]['execution_id']),sort_keys=True).encode()
            for n,data in early.items():(destination/n).write_bytes(data)
            (destination/'verification.json').write_text(json.dumps({'status':'EVIDENCE_ONLY','case':case,
                'actual_state':result['state'],'error':result.get('error'),'physical_validation':'NOT_RUN',
                'artifact_sha256':{n:hashlib.sha256(data).hexdigest() for n,data in early.items()}},sort_keys=True),encoding='utf-8')
        self.assertEqual(adapters[0].scope['goal'],original)
        self.assertEqual(adapters[0].scope['schema'],'observed-mission-scope-5.0' if survey_only else 'observed-mission-scope-3.0')
        state=controller.snapshot(adapters[0].owner)
        self.assertFalse(state['busy']);self.assertTrue(state['cleanup_confirmed'],{k:result.get(k) for k in ('state','error','cold_start','photo_correction')});self.assertTrue(state['sensor_cleanup_confirmed'])
        final=json.loads((root/'artifacts/manual-control'/job['job_id']/'robot-report.json').read_text())
        self.assertEqual(final['synthetic_final_velocity'],[0.,0.]);self.assertEqual(report['physical_validation'],'NOT_RUN')
        history=review_session(root,job['job_id']);self.assertFalse(history['motion_authorized'])
        # Do not write a PASS receipt before the case's primary outcome checks.
        if stop_commit:
            self.assertEqual(result['state'],'FORCE_STOPPED',result)
            self.assertEqual(result['goal'],original);self.assertEqual(result['cold_start']['stage'],'ALIGN')
        elif failure:
            self.assertEqual(result['state'],'FAILED',result)
            self.assertEqual(result['goal'],original);self.assertEqual(result['cold_start']['reason'],'PHOTO_LEDGER_HEAD_CHANGED')
        else:
            self.assertEqual(result['state'],'MISSION_ARRIVED',{k:result.get(k) for k in ('state','error','cold_start','photo_correction')})
            self.assertEqual(result['photo_correction']['status'],'ROBOT_IDLE_BINDING_ACKNOWLEDGED')
            self.assertEqual(result['photo_correction']['goal_revalidation'],'SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL' if survey_only else 'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED')
            self.assertEqual(result['result']['mission_evidence_status'],'VERIFIED_HISTORICAL')
            self.assertEqual(report['survey_map'],adapters[0].survey_map)
            self.assertEqual(report['photo_alignment'],adapters[0].fit_result)
            self.assertEqual(report['photo_alignment']['source_map_revision'],report['survey_map']['revision'])
            self.assertGreater(len(report['survey_map']['tracking_endpoints']),160)
            self.assertTrue(report['survey_map']['keyframes'])
            self.assertFalse(report['survey_map']['motion_authorized'])
            evidence=decode_evidence((peer/'mission-evidence.json').read_bytes())
            replay=replay_mission_evidence(evidence,adapters[0].scope,job['job_id'],
                evidence['request_sha256'],evidence['context'])
            self.assertEqual(replay['status'],'MATCH',replay)
            self.assertFalse(replay['current_pose_valid']);self.assertFalse(replay['motion_authorized'])
        if name:
            files={'mission-report.json':report_path.read_bytes(),'scope.json':json.dumps(adapters[0].scope,sort_keys=True).encode(),
                   'published.json':(peer/'published.json').read_bytes()}
            if diagnostics:
                files['execution-detail.json']=json.dumps(self.trace_detail,sort_keys=True).encode()
                files['execution-export.json']=json.dumps(store.export(entries[0]['execution_id']),sort_keys=True).encode()
            for p in (root/'artifacts/manual-control'/job['job_id']).iterdir():
                if p.is_file() and p.name in {'robot-report.json','session.jsonl','result.json','stderr.log'}:files[p.name]=p.read_bytes()
            for n,data in files.items():(destination/n).write_bytes(data)
            sources=('packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py',
                     'packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py','packages/twinpulse_app/src/twinpulse_app/physical_controller.py',
                     'packages/twinpulse_app/src/twinpulse_app/session_history.py','packages/twinpulse_robot_safety/mission_runtime.py',
                     'packages/twinpulse_robot_safety/observed_runtime.py','packages/twinpulse_core/src/twinpulse_core/cold_start_mission.py',
                     'packages/twinpulse_core/src/twinpulse_core/adaptive_mission_contract.py','packages/twinpulse_core/src/twinpulse_core/mission_correction_contract.py',
                     'tests/fixtures/observed_robot_process.py','tests/integration/test_remote_mission_correction.py','scripts/robot_source_identity.py',
                     'packages/twinpulse_core/src/twinpulse_core/mission_evidence_contract.py',
                     'packages/twinpulse_core/src/twinpulse_core/execution_diagnostics.py',
                     'packages/twinpulse_app/src/twinpulse_app/robot_evidence_export.py',
                     'packages/twinpulse_robot_safety/teleop_worker.py','scripts/inspect_robot_evidence.py')
            if (peer/'mission-evidence.json').is_file():
                files['mission-evidence.json']=(peer/'mission-evidence.json').read_bytes()
                (destination/'mission-evidence.json').write_bytes(files['mission-evidence.json'])
            (destination/'verification.json').write_text(json.dumps({'status':'PASS','case':case,'physical_validation':'NOT_RUN',
                'sensor_basis':'OUTPUT_REACTIVE_SYNTHETIC_ROS_MESSAGES','robot_connections':0,'provider_calls':0,
                'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                'artifact_sha256':{n:hashlib.sha256(data).hexdigest() for n,data in files.items()}},sort_keys=True,indent=2))
        return result,report,history,automatic

    def test_remote_survey_correction_ack_finishes_without_goal_route(self):
        with TemporaryDirectory() as td:
            job,report,history,automatic=self.execute(Path(td),survey_only=True)
            self.assertEqual(report['cold_start']['stage'],'SURVEY_COMPLETE')
            self.assertIsNone(job['visual']['goal_room']);self.assertEqual(job['visual']['route_room'],[])
            self.assertNotEqual(job['goal']['room_revision'],job['original_goal']['room_revision'])
            self.assertEqual(len(automatic.photo_store.current(load_automatic_room(Path(td),'remote_room'))['events']),1)

    def test_survey_report_callback_does_not_block_scoped_fresh_watches(self):
        with TemporaryDirectory() as td:
            job,report,history,_=self.execute(Path(td),survey_only=True,diagnostics=True,slow_record=True)
            self.assertEqual(job['state'],'MISSION_ARRIVED')
            self.assertEqual(report['cold_start']['stage'],'SURVEY_COMPLETE')
            self.assertFalse(history['motion_authorized'])

    def test_actual_remote_idle_fit_append_ack_rebind_fresh_goal_arrival(self):
        with TemporaryDirectory() as td:
            job,report,history,automatic=self.execute(Path(td))
            self.assertEqual(job['state'],'MISSION_ARRIVED',{k:job.get(k) for k in ('state','error','cold_start','photo_correction')})
            self.assertEqual(job['photo_correction']['status'],'ROBOT_IDLE_BINDING_ACKNOWLEDGED')
            self.assertEqual(job['photo_correction']['goal_revalidation'],'NOMINAL_SECTION_AND_CURRENT_SENSOR_PLAN_VALIDATED')
            self.assertNotEqual(job['goal']['room_revision'],job['original_goal']['room_revision'])
            for key in ('xy','mode','duration_s'):self.assertEqual(job['goal'][key],job['original_goal'][key])
            self.assertEqual(job['visual']['room_revision'],job['goal']['room_revision'])
            self.assertEqual(report['photo_alignment']['goal_binding']['goal'],job['goal'])
            self.assertEqual({e['kind'] for e in history['correction_exchange']},
                {'correction_proposal_received','correction_reply_sent','correction_robot_receipt'})
            ledger=automatic.photo_store.current(load_automatic_room(Path(td),'remote_room'))
            self.assertEqual(len(ledger['events']),1);self.assertEqual(ledger['effective_revision'],job['goal']['room_revision'])

    def test_remote_correction_stages_are_bound_to_one_execution_without_raw_copy(self):
        with TemporaryDirectory() as td:
            job,report,history,_=self.execute(Path(td),survey_only=True,diagnostics=True)
            detail=self.trace_detail
            self.assertEqual(detail['status'],'succeeded')
            spans={s['stage']:s for s in detail['spans']}
            for stage in ('mission_adapter_admission','mission_phase_survey',
                          'mission_phase_align','mission_correction_commit','mission_correction_ack',
                          'mission_adapter_cleanup','mission_report_save'):
                self.assertIn(stage,spans)
                self.assertEqual(spans[stage]['status'],'succeeded',stage)
                self.assertGreaterEqual(spans[stage]['duration_s'],0)
            correction=spans['mission_correction_commit']['metadata']
            self.assertEqual(correction['map_revision'],report['survey_map']['revision'])
            self.assertEqual(correction['correction_revision'],job['photo_correction']['applied_revision'])
            ack=spans['mission_correction_ack']['metadata']
            self.assertEqual(ack['goal_room_revision'],job['goal']['room_revision'])
            self.assertEqual(ack['measurement_source'],'pc_observation')
            self.assertLess(len(detail['spans']),20)
            exported=json.dumps(detail)
            self.assertNotIn('scan_room',exported);self.assertNotIn('pose_room',exported)
            self.assertNotIn('robot_t',exported)
            self.assertEqual(report['physical_validation'],'NOT_RUN')
            self.assertEqual({e['kind'] for e in history['correction_exchange']},
                {'correction_proposal_received','correction_reply_sent','correction_robot_receipt'})

    def test_commit_rejection_keeps_fit_cause_original_goal_and_idle_cleanup(self):
        with TemporaryDirectory() as td:
            job,report,history,automatic=self.execute(Path(td),failure=True,diagnostics=True)
            self.assertEqual(job['state'],'FAILED');self.assertEqual(job['goal'],job['original_goal'])
            self.assertEqual(job['cold_start']['reason'],'PHOTO_LEDGER_HEAD_CHANGED')
            self.assertEqual(report['photo_alignment']['geometry_status'],'BOUNDED_WALL_PROPOSAL_VALIDATED')
            self.assertNotIn('goal_binding',report['photo_alignment'])
            self.assertFalse(automatic.photo_store.current(load_automatic_room(Path(td),'remote_room'))['events'])
            detail=self.trace_detail
            self.assertEqual(detail['status'],'failed')
            commit=next(s for s in detail['spans'] if s['stage']=='mission_correction_commit')
            self.assertEqual(commit['status'],'failed')
            self.assertEqual(commit['metadata']['error_code'],'PHOTO_LEDGER_HEAD_CHANGED')
            self.assertFalse(any(s['stage']=='mission_correction_ack' for s in detail['spans']))
            self.assertEqual(next(s for s in detail['spans'] if s['stage']=='mission_report_save')['status'],'succeeded')

    def test_stop_at_commit_cannot_send_late_ack_or_resume_navigation(self):
        with TemporaryDirectory() as td:
            job,report,history,automatic=self.execute(Path(td),stop_commit=True,diagnostics=True)
            self.assertEqual(job['state'],'FORCE_STOPPED',job.get('error'))
            self.assertEqual(job['goal'],job['original_goal']);self.assertEqual(job['cold_start']['stage'],'ALIGN')
            self.assertFalse(any(e['kind']=='correction_reply_sent' for e in history['correction_exchange']))
            self.assertFalse(automatic.photo_store.current(load_automatic_room(Path(td),'remote_room'))['events'])
            self.assertEqual(self.trace_detail['status'],'cancelled')
            self.assertIsNone(self.trace_detail['first_error'])
            self.assertEqual(next(s for s in self.trace_detail['spans'] if s['stage']=='mission_correction_commit')['status'],'cancelled')
            self.assertFalse(any(s['stage']=='mission_correction_ack' for s in self.trace_detail['spans']))
            self.assertEqual(next(s for s in self.trace_detail['spans'] if s['stage']=='mission_phase_align')['status'],'cancelled')


if __name__=='__main__':unittest.main()
