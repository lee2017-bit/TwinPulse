# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current chat survey tests. Fake devices, actual mission/fit/persistence/API."""
from copy import deepcopy
from pathlib import Path
from threading import RLock
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.integration.test_chat_robot_preparation import ChatRobotTests
from twinpulse_core.adaptive_mission_contract import adaptive_scope,nominal_room
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.chat_inspection import ChatInspection
from twinpulse_app.command_broker import BrokerError
from tests.integration.test_cold_start_mission import ColdStartTests
from tests.integration.test_automatic_demo_service import GEOMETRY


class SurveyOnlyRuntimeTests(unittest.TestCase):
    setUp=ColdStartTests.setUp
    execute=ColdStartTests.execute
    def test_survey_correction_rebinds_without_placeholder_navigation(self):
        job,adapter,report=self.execute('survey_correct',1.,[0.,-.6,0.],[0.,0.],
            mode='SURVEY_ONLY',photo_policy='correct_walls')
        self.assertEqual(job['state'],'MISSION_ARRIVED',job.get('error'))
        self.assertEqual(report['cold_start']['stage'],'SURVEY_COMPLETE')
        self.assertNotEqual(job['original_goal']['room_revision'],job['goal']['room_revision'])
        self.assertEqual(job['photo_correction']['goal_revalidation'],'SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL')
        self.assertIsNone(job['visual']['goal_room']);self.assertEqual(job['visual']['route_room'],[])
        self.assertEqual(adapter.velocity,(0.,0.));self.assertFalse(report['physical_demo_ready'])
        reasons=[e['data']['decision']['reason'] for e in report['events'] if e['kind']=='mission_decision']
        self.assertIn('SURVEY_COMPLETE_NO_GOAL_COMMAND',reasons)
        self.assertNotIn('PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR',reasons)

    def test_survey_only_two_starts_never_navigates_to_placeholder_goal(self):
        for name,scale,start in (('survey_one',1.,[0.,-.6,0.]),('survey_two',1.2,[-.2,-.6,0.])):
            with self.subTest(room=name):
                job,adapter,report=self.execute(name,scale,start,[0.,0.],mode='SURVEY_ONLY')
                self.assertEqual(job['state'],'MISSION_ARRIVED',{k:job.get(k) for k in ('state','error','cold_start')})
                self.assertEqual(report['cold_start']['stage'],'SURVEY_COMPLETE')
                self.assertEqual(report['photo_alignment']['status'],'ALIGNMENT_CANDIDATE')
                self.assertGreater(len(report['survey_map']['keyframes']),7)
                self.assertIsNone(job['visual']['goal_room']);self.assertEqual(job['visual']['route_room'],[])
                self.assertIsNotNone(job['visual']['pose_room']);self.assertEqual(adapter.velocity,(0.,0.))
                reasons=[e['data']['decision']['reason'] for e in report['events'] if e['kind']=='mission_decision']
                self.assertIn('SURVEY_COMPLETE_NO_GOAL_COMMAND',reasons)
                self.assertNotIn('PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR',reasons)
                self.assertFalse(report['physical_demo_ready']);self.assertEqual(adapter.consumed,1)

    def test_v4_survey_scope_does_not_change_old_v2_scope_contract(self):
        from tests.integration.test_automatic_photo_service import recipe
        objects,_=recipe(self.root,'scope_room',1.)
        # The existing room loader supplies checked structural objects.
        from twinpulse_app.automatic_photo_store import load_automatic_room
        room=load_automatic_room(self.root,'scope_room')
        from twinpulse_core.revisions import canonical_sha256
        revision=canonical_sha256(room['objects'])
        scope={'schema':'observed-mission-scope-4.0','project_id':'scope_room',
            'goal':{'mode':'SURVEY_ONLY','xy':[0.,0.],'duration_s':45.,'room_revision':revision},
            'reference':None,'alignment':None,'nominal':nominal_room(room['objects'],.182,revision)}
        self.assertEqual(adaptive_scope(scope),scope)
        for changed in ({**scope,'schema':'observed-mission-scope-2.0'},
                {**scope,'goal':{**scope['goal'],'xy':[.1,0.]}},
                {**scope,'goal':{**scope['goal'],'mode':'SURVEY_THEN_NAVIGATE'}}):
            with self.assertRaises(ValueError):adaptive_scope(changed)
        legacy={**scope,'schema':'observed-mission-scope-2.0','goal':{**scope['goal'],'mode':'SURVEY_THEN_NAVIGATE','xy':[.1,0.]}}
        self.assertEqual(adaptive_scope(legacy),legacy)


class ChatInspectionTests(ChatRobotTests):
    def configure_inspection(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION');self.choose(state,'normal')
        self.automatic=AutomaticDemoService(self.static,'default',room_loader=self.workflow.inspection_room,geometry_loader=lambda:GEOMETRY)
        self.automatic.room_source_token=self.workflow.inspection_source_token
        self.automatic.room_scene_loader=self.workflow.inspection_scene
        self.addCleanup(self.automatic.close)
        self.started=[]
        # Bounded failure fixture, not sensor or target qualification evidence.
        def factory(prior,room,effective,goal):
            self.started.append(deepcopy(goal));raise ValueError('FIXTURE_ADMISSION_FAILURE')
        self.mission=AutomaticMissionService(self.automatic,adapter_factory=factory)
        self.addCleanup(self.mission.close)
        self.inspection=ChatInspection(self.mission,self.workflow,self.server.chat_robot_preparation,RLock())
        self.server.chat_inspection=self.inspection;self.server.conversation.inspection=self.inspection
        view={'engine_connected':True,'snapshot':{'applied_revision':self.workflow._site_artifact.revision}}
        self.view=view
        self.engine=patch.object(self.broker,'supervisor_state',return_value=view);self.engine.start();self.addCleanup(self.engine.stop)

    def test_current_default_chat_room_and_question_bound_once_not_legacy_room(self):
        self.configure_inspection()
        room=self.workflow.inspection_room(self.static,'default')
        self.assertEqual(room['adapter'],'current-chat-room-1.0')
        self.assertEqual(room['scene_revision'],self.workflow._site_artifact.revision)
        self.assertEqual(room['input_revision'],self.workflow._application.site_draft.input_revision.digest)
        state=self.call();cards=[c for c in state['cards'] if c['kind']=='robot_inspection' and c['state']=='waiting']
        self.assertEqual(len(cards),1);self.assertEqual(self.started,[])
        for _ in range(3):self.call()
        self.assertEqual(self.started,[])
        card=cards[0];body={'action':'answer','request_id':uuid4().hex,'card_id':card['id'],'choice_id':'inspect',
            'expected_session_revision':card['expected_session_revision'],'expires_at_ms':time.time()*1000+1500}
        self.call(body);self.mission.worker.join(3);state=self.call();self.call(body)
        self.assertEqual(len(self.started),1);self.assertEqual(self.started[0]['mode'],'SURVEY_ONLY')
        self.assertEqual(state['inspection']['state'],'FAILED')
        self.assertEqual(state['inspection']['error'],'FIXTURE_ADMISSION_FAILURE')
        self.assertFalse(state['physical_authority']);self.assertFalse(state['inspection']['demo_ready'])
        self.assertEqual(self.controller.calls,['qualify'])
        # A failed survey is not automatically retried. Explicit readiness
        # review offers a fresh question, while preserving the old failure.
        self.call({'action':'inspection_check','request_id':uuid4().hex})
        state=self.call()
        self.assertEqual(len(self.started),1)
        self.assertEqual(sum(c['kind']=='robot_inspection' and c['state']=='waiting' for c in state['cards']),1)
        self.assertEqual(state['inspection']['error'],'FIXTURE_ADMISSION_FAILURE')
        self.assertEqual(state['room_build']['scene_revision'],room['scene_revision'])

    def test_correction_policy_changes_confirmation_digest_and_is_explicit(self):
        self.configure_inspection()
        state=self.call();old=state['inspection']['readiness']
        self.assertEqual(old['photo_policy'],'align_only')
        self.mission.adapter_factory.supports_local_correction=True
        state=self.call();current=state['inspection']['readiness']
        self.assertEqual(current['photo_policy'],'correct_walls')
        self.assertNotEqual(old['binding'],current['binding'])
        self.assertTrue(any('derived room revision' in m['content'] for m in state['messages']))

    def test_changed_twin_expired_confirmation_and_save_failure_start_no_worker(self):
        self.configure_inspection();state=self.call();card=next(c for c in state['cards'] if c['kind']=='robot_inspection' and c['state']=='waiting')
        self.view['snapshot']['applied_revision']='f'*64
        body={'action':'answer','request_id':uuid4().hex,'card_id':card['id'],'choice_id':'inspect',
            'expected_session_revision':card['expected_session_revision'],'expires_at_ms':time.time()*1000+1500}
        status,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.started,[])
        self.view['snapshot']['applied_revision']=self.workflow._site_artifact.revision
        state=self.call();card=next(c for c in reversed(state['cards']) if c['kind']=='robot_inspection' and c['state']=='waiting')
        body.update(request_id=uuid4().hex,card_id=card['id'],expected_session_revision=card['expected_session_revision'],expires_at_ms=0)
        self.call(body);self.assertEqual(self.started,[])
        # New service/readiness question, then failed durable confirmation.
        state=self.call({'action':'inspection_check','request_id':uuid4().hex})
        card=next(c for c in reversed(state['cards']) if c['kind']=='robot_inspection' and c['state']=='waiting')
        body.update(request_id=uuid4().hex,card_id=card['id'],expected_session_revision=card['expected_session_revision'],expires_at_ms=time.time()*1000+1500)
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','fixture')):
            status,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.started,[])

    def test_missing_target_registration_is_visible_not_robot_power_request(self):
        self.configure_inspection()
        from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
        self.mission.adapter_factory=RemoteObservedFactory(self.controller,self.static,'default')
        state=self.call()
        self.assertEqual(state['inspection']['readiness']['code'],'REVIEWED_OBSERVED_RELEASE_NOT_REGISTERED')
        self.assertFalse(state['inspection']['readiness']['ready'])
        self.assertFalse(any(c['kind']=='robot_inspection' and c['state']=='waiting' for c in state['cards']))
        self.assertEqual(self.started,[])

    def test_stop_api_bypasses_conversation_storage_and_ordinary_never_escalates(self):
        self.configure_inspection()
        # Active worker stand-in, no sensors or driving. Exercise the existing
        # authenticated Stop route even when chat persistence cannot work.
        with patch.object(self.inspection,'active',return_value=True), patch.object(self.mission,'stop') as stop, \
                patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','fixture')):
            self.inspection.job_id='owned-inspection'
            status,ordinary,_=self.request('/v1/product/conversation/robot/stop',{'force':False},headers=self.product_headers)
            self.assertEqual(status,200);self.assertFalse(ordinary['stop_confirmed'])
            self.assertEqual(stop.call_args.args[1:],('owned-inspection',False))
            status,forced,_=self.request('/v1/product/conversation/robot/stop',{'force':True},headers=self.product_headers)
            self.assertEqual(status,200);self.assertEqual(forced['state'],'FORCE_STOP_REQUESTED')
            self.assertEqual(stop.call_args.args[1:],('owned-inspection',True))
            self.assertEqual(self.controller.calls,['qualify'])


class InspectionSnapshotTests(unittest.TestCase):
    def test_cleanup_or_storage_failure_cannot_promote_terminal_pose_to_current(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        job={'job_id':'survey','state':'MISSION_ARRIVED','report_status':'SAVED',
            'goal':{'room_revision':'room'},'cold_start':{'stage':'SURVEY_COMPLETE','alignment_status':'ALIGNMENT_CANDIDATE'},
            'visual':{'pose_room':[1.,2.,0.]},'elapsed_s':1.}
        mission=SimpleNamespace(worker=None,snapshot=lambda owner:{'job':deepcopy(job)})
        inspection=ChatInspection(mission,None,None,RLock())
        inspection.owner='owner';inspection.job_id='survey';inspection.scene_revision='original-scene'
        inspection.readiness=Mock(return_value={'ready':False,'code':'CURRENT_ROBOT_LINK_REQUIRED'})
        complete=inspection.snapshot('owner')
        self.assertEqual(complete['state'],'SURVEY_COMPLETE');self.assertIsNone(complete['visual'])
        self.assertFalse(complete['current_pose_available']);self.assertFalse(complete['motion_authorized'])
        self.assertEqual(inspection.snapshot('owner')['summary']['observed_at_ms'],complete['summary']['observed_at_ms'])
        for key in ('cleanup_error','report_error'):
            job.update(state='FAILED',**{key:'FIXTURE_FAILURE'})
            failed=inspection.snapshot('owner')
            self.assertFalse(failed['alignment_candidate']);self.assertIsNone(failed['visual'])
            self.assertEqual(failed['scene_revision'],'original-scene')
            self.assertEqual(failed['summary']['error'],'FIXTURE_FAILURE')
            self.assertEqual(failed['summary']['next_action'],'INSPECTION_FAILED_REVIEW_CAUSES')
        mission.worker=SimpleNamespace(is_alive=lambda:True);mission.clock=lambda:10.
        job.update(state='SURVEYING',visual_updated_s=9.7)
        self.assertFalse(inspection.snapshot('owner')['current_pose_available'])
        self.assertIsNone(inspection.snapshot('owner')['visual'])
        job.update(visual_updated_s=9.9)
        self.assertTrue(inspection.snapshot('owner')['current_pose_available'])
