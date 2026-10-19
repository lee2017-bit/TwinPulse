# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free supplementary checks; not actual installed App acceptance."""
from copy import deepcopy
import json
from unittest.mock import patch
import unittest
from tests.integration.test_r5_product_api import R5ProductApiTests
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.robot_fleet import RobotFleet


class RegistrationHistoryTests(unittest.TestCase):
    setUp=R5ProductApiTests.setUp
    tearDown=R5ProductApiTests.tearDown
    request=R5ProductApiTests.request
    product_headers=R5ProductApiTests.product_headers

    def body(self,request='register-menu',label='TurtleBot3'):
        return dict(action='register_sim',request_id=request,robot_id=None,
                    connection_epoch=None,motion_epoch=None,payload=dict(label=label,position_m=[1.,1.,0.]))

    def call(self,body=None):
        status,value,_=self.request('/v1/product/robot-fleet',body,headers=self.product_headers)
        return status,value

    def chat(self):
        status,value,_=self.request('/v1/product/conversation',headers=self.product_headers)
        self.assertEqual(status,200,value)
        return value

    def test_real_registration_then_poll_is_durable_linked_and_not_repeated(self):
        status,fleet=self.call(self.body());self.assertEqual(status,200)
        state=self.chat();event=next(e for e in state['events'] if e['type']=='fleet_sim_registered')
        receipt=event['payload']['registration'];messages={m['message_id']:m for m in state['messages']}
        action=messages[event['payload']['menu_message_id']];reply=messages[event['payload']['message_id']]
        self.assertTrue(action['content'].startswith('Menu action · Add SIM robot:'))
        self.assertEqual(reply['reply_to'],action['message_id']);self.assertIn('built-in SIM model',reply['content'])
        self.assertIn('does not connect, display or move',reply['content']);self.assertEqual(receipt['robot_id'],fleet['focused_robot_id'])
        self.assertEqual(receipt['source_twin_context']['conversation_session_id'],state['session_id'])
        self.assertEqual(receipt['source_twin_context']['project_id'],state['project_id'])
        self.assertEqual(receipt['position_m'],[1.,1.,0.]);self.assertEqual(receipt['model_id'],'turtlebot3_burger')
        for _ in range(3):self.assertEqual(self.chat()['messages'],state['messages'])
        self.assertEqual(self.call(self.body())[0],200);self.assertEqual(self.chat()['messages'],state['messages'])
        saved=json.loads(self.server.conversation.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['messages'],state['messages'])
        self.assertEqual(fleet['robots'][0]['connection_state'],'DISCONNECTED')
        self.assertIsNone(state['robot_id']);self.assertFalse(state['physical_authority'])

    def test_invalid_registration_never_adds_a_success_message(self):
        body=self.body();body['payload']['position_m']=[float('inf'),1,0]
        # Invalid JSON number is rejected before a registration receipt exists.
        self.assertNotEqual(self.call(body)[0],200)
        self.assertFalse([e for e in self.chat()['events'] if e['type']=='fleet_sim_registered'])

    def test_save_queue_failure_rolls_back_unaccepted_registration(self):
        with patch.object(self.server.robot_fleet,'_persist',side_effect=OSError('test-only-storage-failure')):
            with self.assertRaises(OSError):self.server.robot_fleet.action(self.body(),'owner')
        self.assertFalse(self.server.robot_fleet.robots)
        self.assertFalse([e for e in self.chat()['events'] if e['type']=='fleet_sim_registered'])

    def test_restart_outbox_recovers_missing_chat_without_replay_or_duplication(self):
        status,fleet=self.call(self.body());self.assertEqual(status,200)
        original_path=self.server.conversation.path
        original_session=self.server.conversation._state['session_id']
        self.server.conversation._persist() # Store pre-poll chat; registration outbox is separate.
        self.server.robot_fleet.close()
        restored=ConversationService(self.workflow,original_path)
        restored.robot_fleet=RobotFleet(self.broker,original_path.parent,conversation_session_id=original_session)
        try:
            state=restored.snapshot();self.assertIsNone(state['restore_error'])
            self.assertEqual(len([e for e in state['events'] if e['type']=='fleet_sim_registered']),1)
            self.assertEqual(restored.snapshot()['messages'],state['messages'])
            robot=restored.robot_fleet.snapshot()['robots'][0]
            self.assertEqual(robot['robot_id'],fleet['focused_robot_id']);self.assertIsNone(robot['connection_epoch'])
            self.assertEqual(len(restored.robot_fleet.action(self.body(),'owner')['robots']),1)
            changed=self.body();changed['payload']['label']='Changed'
            with self.assertRaisesRegex(Exception,'different content'):restored.robot_fleet.action(changed,'owner')
            wrong=deepcopy(restored._state);wrong['session_id']='different-conversation'
            restored._state=wrong
            self.assertEqual(restored.robot_fleet.registration_receipts('different-conversation'),[])
        finally:restored.robot_fleet.close()


if __name__=='__main__':unittest.main()
