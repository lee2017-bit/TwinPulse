# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Authenticated chat/current goal handoff. Offline doubles, not robot/Isaac PASS."""
from copy import deepcopy
from threading import RLock
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.integration.test_chat_robot_preparation import ChatRobotTests
from tests.integration.test_current_goal_preview import evidence
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.chat_goal_navigation import ChatGoalNavigation
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.conversation_service import ConversationService


class ChatGoalTests(unittest.TestCase):
    setUp=ChatRobotTests.setUp;tearDown=ChatRobotTests.tearDown
    request=ChatRobotTests.request;product_headers=ChatRobotTests.product_headers
    call=ChatRobotTests.call;send=ChatRobotTests.send;use_room_gateway=ChatRobotTests.use_room_gateway
    attach=ChatRobotTests.attach;choose=ChatRobotTests.choose;start_real=ChatRobotTests.start_real;wait=ChatRobotTests.wait

    def configure(self,*,preview=True,receipt=False):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION');self.choose(state,'normal')
        from twinpulse_app.automatic_demo_service import AutomaticDemoService
        auto=AutomaticDemoService(self.static,'default',room_loader=self.workflow.inspection_room)
        auto.room_scene_loader=self.workflow.inspection_scene
        self.addCleanup(auto.close)
        self.current=evidence();self.current['project_id']='default';self.current['pose_map']=[0.,-1.4,0.]
        self.current['room_revision']=auto.photo_store.current(auto.room_loader(auto.root,'default'))['effective_revision']
        self.context={k:self.current[k] for k in ('project_id','source_revision','epoch')}
        self.reads=0;self.starts=[]
        class Factory:
            supports_current_goal_preview=preview
            clock=staticmethod(lambda:1.)
            def preview_current(inner,owner):
                self.reads+=1
                return {'map_id':'fixture-prior','evidence':deepcopy(self.current),'context':deepcopy(self.context)}
            def goal_preview_receipt(inner,digest):return receipt
            def __call__(inner,prior,room,effective,goal):
                self.starts.append(deepcopy(goal));raise ValueError('OFFLINE_FIXTURE_NO_TRANSPORT')
        self.mission=AutomaticMissionService(auto,adapter_factory=Factory());self.addCleanup(self.mission.close)
        # Unit-level prior validation stub. Existing archive/hash integration
        # suites cover real stores; this fixture cannot qualify a real prior.
        prior_patch=patch.object(self.mission,'_prior',side_effect=lambda mid,goal:
            ({'map':{'revision':'a'*64}},auto.room_loader(auto.root,'default'),
             auto.photo_store.current(auto.room_loader(auto.root,'default')),goal))
        prior_patch.start();self.addCleanup(prior_patch.stop)
        navigation=ChatGoalNavigation(self.mission,self.workflow,self.server.chat_robot_preparation,RLock())
        self.server.conversation.navigation=navigation
        self.server.automatic_mission=self.mission
        return navigation

    def goal(self,text='Go x=.2 y=-1.4',request=None):
        return self.call({'action':'message','request_id':request or uuid4().hex,'text':text,'mode':'new','attachment':None})

    def confirmation(self,state):
        card=next(c for c in reversed(state['cards']) if c['state']=='waiting' and c['kind']=='robot_goal_confirm')
        return {'action':'answer','request_id':uuid4().hex,'card_id':card['id'],'choice_id':'confirm',
                'expected_session_revision':card['expected_session_revision'],'expires_at_ms':time.time()*1000+1500}

    def test_missing_current_adapter_has_exact_blocker_no_sim_no_retry(self):
        self.configure(preview=False);state=self.goal()
        self.assertIn('fresh idle localization/preview handoff',state['messages'][-1]['content'])
        self.assertIn('current_goal_preview_unavailable',state['messages'][-1]['content'])
        self.assertIsNone(state['simulation_review']);self.assertEqual(self.reads,0)
        for _ in range(3):self.call()
        self.assertEqual(self.starts,[]);self.assertEqual(self.reads,0)

    def test_route_question_no_robot_command_and_3d_not_faked(self):
        self.configure();state=self.goal();review=state['navigation']['review']
        self.assertEqual(review['plan']['start'],[0.,-1.4]);self.assertEqual(self.starts,[])
        card=next(c for c in state['cards'] if c['kind']=='robot_goal_confirm')
        self.assertFalse(card['choices'][0]['enabled']);self.assertIn('Isaac 3D',card['choices'][0]['disabled_reason'])
        self.assertFalse(state['navigation']['current_pose_available']);self.assertFalse(state['physical_authority'])
        before=self.reads;self.call();self.call();self.assertEqual(self.reads,before)
        response=self.request('/v1/product/conversation',self.confirmation(state),headers=self.product_headers)
        self.assertEqual(response[0],400);self.assertEqual(self.starts,[])

    def test_hand_move_and_source_change_reject_exact_confirm_without_worker(self):
        self.configure(receipt=True)
        for change in ('move','source','grid'):
            state=self.goal();body=self.confirmation(state)
            before=deepcopy(self.current)
            if change=='move':self.current['pose_map'][0]+=.01
            if change=='source':self.current['source_revision']='f'*64
            if change=='grid':self.current['cells'][0][2]='occupied'
            result=self.call(body)
            self.assertEqual(result['messages'][-1]['status'],'failed')
            self.assertEqual(self.starts,[]);self.assertIsNone(self.mission.worker)
            self.assertIsNone(result['navigation']['review']);self.call(body)
            self.current=before

    def test_save_failure_prevents_any_confirmation_transport(self):
        self.configure(receipt=True);state=self.goal()
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            status,_,_=self.request('/v1/product/conversation',self.confirmation(state),headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.starts,[])

    def test_qualified_offline_confirmation_once_and_detailed_failure_report(self):
        self.configure(receipt=True);state=self.goal();body=self.confirmation(state)
        self.call(body);self.mission.worker.join(3);result=self.call()
        self.assertEqual(len(self.starts),1);self.assertEqual(result['navigation']['job']['state'],'FAILED')
        self.assertEqual(result['navigation']['job']['error'],'OFFLINE_FIXTURE_NO_TRANSPORT')
        self.assertEqual(result['navigation']['job']['report_status'],'SAVED')
        self.call(body);self.call();self.assertEqual(len(self.starts),1)
        self.assertFalse(result['navigation']['physical_demo_ready'])

    def test_restart_expires_goal_card_and_never_restores_current_pose(self):
        self.configure(receipt=True);state=self.goal()
        restored=ConversationService(self.workflow,self.server.conversation.path).snapshot()
        self.assertIsNone(restored['restore_error']);self.assertIsNone(restored['navigation'])
        self.assertEqual(next(c for c in restored['cards'] if c['kind']=='robot_goal_confirm')['state'],'expired')
        self.assertEqual(self.starts,[])

    def test_expired_confirm_is_consumed_without_worker(self):
        self.configure(receipt=True);state=self.goal();body=self.confirmation(state);body['expires_at_ms']=0
        result=self.call(body);self.assertIn('goal_confirmation_expired',result['messages'][-1]['content'])
        self.assertEqual(self.starts,[]);self.assertIsNone(result['navigation']['review'])

    def test_new_goal_expires_old_card_and_cannot_replay_old_route(self):
        self.configure(receipt=True);first=self.goal();old=self.confirmation(first)
        second=self.goal('Go x=.3 y=-1.4');self.assertNotEqual(first['navigation']['review']['plan']['plan_id'],second['navigation']['review']['plan']['plan_id'])
        status,_,_=self.request('/v1/product/conversation',old,headers=self.product_headers)
        self.assertEqual(status,409);self.assertEqual(self.starts,[])

    def test_owned_goal_stop_is_independent_of_chat_cards_and_persistence(self):
        navigation=self.configure(receipt=True);self.goal()
        owner=self.server.conversation._request_owner;navigation.job_id='a'*32
        with patch.object(self.mission,'snapshot',return_value={'job':{'job_id':'a'*32,'state':'DRIVING'}}),\
             patch.object(self.mission,'stop',return_value={'job':{'state':'STOPPING'}}) as stop,\
             patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            for force in (False,True):
                status,body,_=self.request('/v1/product/conversation/robot/stop',{'force':force},headers=self.product_headers)
                self.assertEqual(status,200);self.assertEqual(body['state'],'STOPPING');self.assertFalse(body['stop_confirmed'])
                stop.assert_called_with(owner,'a'*32,force)

    def test_observation_failure_is_a_logged_response_not_closed_http(self):
        self.configure()
        with patch.object(self.mission.adapter_factory,'preview_current',side_effect=TimeoutError('CURRENT_OBSERVATION_TIMEOUT')):
            state=self.goal()
        self.assertIn('CURRENT_OBSERVATION_TIMEOUT',state['messages'][-1]['content'])
        self.assertIn('current_goal_preview_rejected',state['messages'][-1]['content']);self.assertEqual(self.starts,[])

    def test_qualification_terminal_receipt_waits_for_pc_cleanup_without_new_input(self):
        from tests.integration.test_chat_robot_preparation import ReactiveController
        service=self.attach()
        class ClosingController(ReactiveController):
            close_at=None
            watch_after_finish=0
            def snapshot(inner,owner):
                if inner.close_at is not None and time.monotonic()>=inner.close_at:inner.state['busy']=False
                return super().snapshot(owner)
            def input(inner,*args):
                if inner.state['state']=='FINISHED':
                    inner.watch_after_finish+=1
                    raise BrokerError('physical_stopping','Stop already requested',status=409)
                value=super().input(*args)
                if args[3]=='qualify':
                    inner.close_at=time.monotonic()+.45;inner.state['busy']=True
                return value
        controller=ClosingController();controller.boot=self.controller.boot;controller.release=self.controller.release
        service.controller=controller
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION')
        self.assertEqual(controller.watch_after_finish,0)
        self.assertEqual(state['robot_preparation']['trial']['status'],'QUALIFIED')
        self.assertTrue(state['robot_preparation']['cleanup_confirmed'])

    def test_production_demonstration_failure_reported_no_boolean_receipt_bypass_or_retry(self):
        from twinpulse_app.goal_demonstration import GoalDemonstration
        navigation=self.configure(receipt=True)
        demo=GoalDemonstration(self.workflow._broker,navigation._scene,timeout_s=.5)
        navigation.demonstration=demo;self.addCleanup(demo.close)
        state=self.goal();demo.worker.join(1.)
        result=self.call();self.assertEqual(result['navigation']['demonstration']['state'],'FAILED')
        self.assertFalse(navigation.can_confirm())
        self.assertIn('Isaac route preview failed',result['messages'][-1]['content'])
        self.assertIsNone(result['navigation']['demonstration']['receipt'])
        commands=len(self.workflow._broker.public_state(self.server.conversation._request_owner)['operations'])
        for _ in range(3):self.call()
        self.assertEqual(len(self.workflow._broker.public_state(self.server.conversation._request_owner)['operations']),commands)
        self.assertEqual(self.starts,[])


if __name__=='__main__':unittest.main()
