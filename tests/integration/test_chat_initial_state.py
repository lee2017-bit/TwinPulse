# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Initial-state orchestration with injected collectors/controllers only."""
import time
import unittest
from tests.integration.test_chat_robot_preparation import ChatRobotTests
from tests.integration.test_robot_diagnostics import observation


class InitialStateTests(unittest.TestCase):
    setUp=ChatRobotTests.setUp
    tearDown=ChatRobotTests.tearDown
    request=ChatRobotTests.request
    product_headers=ChatRobotTests.product_headers
    call=ChatRobotTests.call
    send=ChatRobotTests.send
    use_room_gateway=ChatRobotTests.use_room_gateway
    attach=ChatRobotTests.attach
    choose=ChatRobotTests.choose
    start_real=ChatRobotTests.start_real

    def wait_state(self,expected):
        for _ in range(120):
            state=self.call()
            if state['robot_preparation']['state']==expected:return state
            time.sleep(.02)
        self.fail(f'Expected {expected}: {state["robot_preparation"]}')

    def torque_state(self,extra=None):
        data=observation();data['health']['board']['torque_enabled']=True
        if extra:data['health']['board'].update(extra)
        self.attach(fault=data)
        self.start_real()
        return self.wait_state('BLOCKED'),data

    def test_torque_only_failure_offers_initialization_not_ssh_retry_or_motion(self):
        state,_=self.torque_state()
        self.assertEqual(state['robot_preparation']['code'],'TORQUE_ENABLED_INITIALIZATION_REQUIRED')
        self.assertEqual(state['cards'][-1]['kind'],'robot_initialize')
        self.assertEqual(self.controller.calls,[])
        self.assertEqual(self.controller.inputs,[])
        self.assertIn('SSH and board observation succeeded',state['messages'][-2]['content'])

    def test_cancel_does_not_prepare(self):
        state,_=self.torque_state()
        self.choose(state,'cancel')
        self.assertEqual(self.controller.calls,[])

    def test_nonzero_wheels_never_offer_torque_only_initialization(self):
        state,_=self.torque_state({'wheel_velocity_raw':[1,0]})
        self.assertNotEqual(state['robot_preparation']['code'],'TORQUE_ENABLED_INITIALIZATION_REQUIRED')
        self.assertEqual(state['cards'][-1]['kind'],'robot_recheck')

    def test_expired_click_cannot_prepare(self):
        state,_=self.torque_state()
        self.choose(state,'initialize',fresh=False)
        self.assertEqual(self.controller.calls,[])

    def test_one_approved_prepare_then_fresh_observation_never_auto_qualifies(self):
        state,data=self.torque_state()
        def prepared(owner,mode,job,confirmed,app_context=None):
            self.controller.calls.append(mode)
            data['health']['board']['torque_enabled']=False
            self.controller.state.update(state='FINISHED',busy=False,job_id=job,owned=True,result='PREPARED')
        self.controller.start=prepared
        self.choose(state,'initialize',fresh=True)
        result=self.wait_state('AWAITING_QUALIFICATION')
        self.assertEqual(self.controller.calls,['prepare'])
        self.assertEqual(self.controller.inputs,[])
        self.assertEqual(result['cards'][-1]['kind'],'robot_qualification')
        self.assertFalse(result['physical_authority'])

    def prepare_result(self,state,data,change):
        def prepared(owner,mode,job,confirmed,app_context=None):
            self.controller.calls.append(mode)
            change(data)
            self.controller.state.update(state='FINISHED',busy=False,job_id=job,owned=True,result='PREPARED')
        self.controller.start=prepared
        self.choose(state,'initialize',fresh=True)

    def test_prepare_ack_but_torque_stays_on_is_not_success_or_another_initialize(self):
        state,data=self.torque_state()
        self.prepare_result(state,data,lambda _:None)
        result=self.wait_state('BLOCKED')
        self.assertEqual(result['robot_preparation']['code'],'MOTOR_OFF_NOT_CONFIRMED')
        self.assertEqual(self.controller.calls,['prepare'])
        self.assertNotEqual(result['cards'][-1]['kind'],'robot_initialize')

    def test_new_boot_after_prepare_does_not_qualify_old_identity(self):
        state,data=self.torque_state()
        def change(report):
            report['health']['boot_id']='new-boot'
            report['health']['board']['torque_enabled']=False
        self.prepare_result(state,data,change)
        result=self.wait_state('BLOCKED')
        self.assertEqual(result['robot_preparation']['code'],'INITIALIZATION_IDENTITY_CHANGED')
        self.assertEqual(self.controller.inputs,[])

    def test_port_restore_failure_prevents_post_initialization_qualification(self):
        state,data=self.torque_state()
        def change(report):
            report['health']['board'].update(torque_enabled=False,port_restored=False)
        self.prepare_result(state,data,change)
        result=self.wait_state('BLOCKED')
        self.assertEqual(result['robot_preparation']['code'],'MOTOR_OFF_NOT_CONFIRMED')
        self.assertFalse(result['physical_authority'])
