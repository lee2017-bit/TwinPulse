# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual authenticated chat/API loop integration; offline sensor doubles."""
from copy import deepcopy
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.integration import test_chat_goal_navigation as fixture
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.command_broker import BrokerError


class TaskChatTests(unittest.TestCase):
    setUp=fixture.ChatGoalTests.setUp;tearDown=fixture.ChatGoalTests.tearDown
    request=fixture.ChatGoalTests.request;product_headers=fixture.ChatGoalTests.product_headers
    call=fixture.ChatGoalTests.call;send=fixture.ChatGoalTests.send;use_room_gateway=fixture.ChatGoalTests.use_room_gateway
    attach=fixture.ChatGoalTests.attach;choose=fixture.ChatGoalTests.choose;start_real=fixture.ChatGoalTests.start_real
    wait=fixture.ChatGoalTests.wait;configure=fixture.ChatGoalTests.configure;goal=fixture.ChatGoalTests.goal

    def arrival(self,**changes):
        nav=self.configure(receipt=True);self.goal()
        preview=deepcopy(nav.review['plan']);nav.review=None;nav.job_id='first'
        self.current['pose_map'][:2]=preview['goal']
        self.job={'job_id':'first','map_id':'fixture-prior','state':'MISSION_ARRIVED','worker_active':False,'elapsed_s':5.,
                  'report_status':'SAVED','approved_preview':preview,**changes}
        job=patch.object(self.mission,'snapshot',side_effect=lambda _: {'job':deepcopy(self.job)})
        job.start();self.addCleanup(job.stop)
        return nav

    def answer(self,state,choice='loop'):
        card=next(c for c in state['cards'] if c['kind']=='robot_goal_loop' and c['state']=='waiting')
        return {'action':'answer','request_id':uuid4().hex,'card_id':card['id'],'choice_id':choice,
                'expected_session_revision':card['expected_session_revision'],'expires_at_ms':time.time()*1000+1500}

    def test_one_inline_offer_no_motion_until_choice_finish_and_reload_expiration(self):
        self.arrival();state=self.call()
        self.assertEqual(sum(c['kind']=='robot_goal_loop' for c in state['cards']),1)
        self.assertEqual(sum(c['kind']=='robot_goal_loop' for c in self.call()['cards']),1)
        restored=ConversationService(self.workflow,self.server.conversation.path).snapshot()
        self.assertIsNone(restored['restore_error'])
        self.assertEqual(next(c for c in restored['cards'] if c['kind']=='robot_goal_loop')['state'],'expired')
        result=self.call(self.answer(state,'finish'));self.assertIn('No repeat movement',result['messages'][-1]['content'])
        self.assertEqual(self.starts,[])

    def test_api_single_start_missing_fresh_battery_is_visible_no_transport_retry(self):
        nav=self.arrival();state=self.call();body=self.answer(state)
        self.call(body);nav.task_loop.worker.join(3.)
        result=self.call();task=result['navigation']['task_loop']
        self.assertEqual(task['state'],'FAILED');self.assertIn('TASK_BATTERY_UNAVAILABLE',task['error'])
        self.assertTrue(any('TASK_BATTERY_UNAVAILABLE' in m['content'] and m['status']=='failed' for m in result['messages']))
        self.call(body);self.call();self.assertEqual(self.starts,[])
        self.assertFalse(task['motion_authorized']);self.assertFalse(task['physical_demo_ready'])

    def test_independent_stop_api_operates_between_legs_even_chat_save_failure(self):
        nav=self.arrival();owner=self.server.conversation._request_owner
        with patch.object(nav.task_loop,'active',return_value=True),\
             patch.object(nav.task_loop,'stop',return_value={'state':'STOPPING','stop_confirmed':False}) as stop,\
             patch.object(self.server.conversation,'_persist',side_effect=OSError('DISK_FULL')):
            for force in (False,True):
                status,body,_=self.request('/v1/product/conversation/robot/stop',{'force':force},headers=self.product_headers)
                self.assertEqual(status,200);self.assertFalse(body['stop_confirmed']);stop.assert_called_with(owner,force)

    def test_arrival_cleanup_and_storage_pending_never_offer_repeat(self):
        self.arrival(worker_active=True);self.assertFalse(any(c['kind']=='robot_goal_loop' for c in self.call()['cards']))
        self.job.update(worker_active=False,report_status='FAILED',report_error='DISK_FULL')
        self.assertFalse(any(c['kind']=='robot_goal_loop' for c in self.call()['cards']))

    def test_conversation_save_failure_prevents_task_start(self):
        nav=self.arrival();body=self.answer(self.call())
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            status,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
        self.assertNotEqual(status,200);self.assertIsNone(nav.task_loop.worker)

    def test_restart_marks_saved_running_repeat_as_interrupted_history(self):
        self.arrival();service=self.server.conversation
        service._message('assistant','Repeat A ↔ B · DRIVING',status='pending',operation_id='old-task')
        service._event('goal_task_changed',task_id='old-task',state='DRIVING',leg=1);service._persist()
        restored=ConversationService(self.workflow,service.path).snapshot()
        self.assertIsNone(restored['restore_error']);self.assertIsNone(restored['navigation'])
        message=next(m for m in restored['messages'] if m['operation_id']=='old-task')
        self.assertEqual(message['status'],'interrupted');self.assertTrue(message['content'].startswith('Historical'))
        self.assertEqual(self.starts,[])
