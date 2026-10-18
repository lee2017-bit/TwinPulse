# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual authenticated chat polling with controlled worker receipts; offline."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from tests.integration.test_chat_robot_preparation import ChatRobotTests
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.goal_progress import describe_goal_job
from twinpulse_app.command_broker import BrokerError


class GoalProgressTests(unittest.TestCase):
    setUp=ChatRobotTests.setUp;tearDown=ChatRobotTests.tearDown
    request=ChatRobotTests.request;product_headers=ChatRobotTests.product_headers;call=ChatRobotTests.call

    def configure(self):
        self.tick=100.;service=self.server.conversation
        service._clock=lambda:self.tick;service._state['mode']='REAL'
        self.job={'job_id':'a'*32,'state':'DRIVING','elapsed_s':0.,'worker_active':True,
                  'visual_age_s':.05,'report_status':'PENDING','error':None,
                  'visual':{'state':'DRIVING','pose_room':[.1,.2,.3],
                            'scan_room':[[.2,.3]],'provenance':'SYNTHETIC_TEST_ONLY'}}
        class Navigation:
            demonstration=None
            def snapshot(inner,owner):
                if owner is None:return None
                return {'job':deepcopy(self.job),'demonstration':None,'current_pose_available':False}
        service.navigation=Navigation();return service

    def progress(self,state):return [e for e in state['events'] if e['type']=='goal_execution_progress']
    def terminal(self,state):return [e for e in state['events'] if e['type']=='goal_execution_terminal']

    def test_five_second_poll_cadence_no_paid_call_command_or_catchup_burst(self):
        self.configure();self.assertEqual(self.progress(self.call()),[])
        self.tick+=4.999;self.assertEqual(self.progress(self.call()),[])
        self.tick+=.001;state=self.call();self.assertEqual(len(self.progress(state)),1)
        self.assertIn('Latest worker frame',state['messages'][-1]['content'])
        self.assertIn('SYNTHETIC_TEST_ONLY',state['messages'][-1]['content'])
        self.assertEqual(self.progress(self.call()),self.progress(state))
        self.tick+=25;state=self.call();self.assertEqual(len(self.progress(state)),2)
        self.assertEqual(len([m for m in state['messages'] if m['operation_id']==self.job['job_id']]),1)
        self.assertIn('Updated at',state['messages'][-1]['content'])
        self.assertFalse(state['physical_authority']);self.assertIsNone(state['generation'])

    def test_all_terminals_immediate_and_duplicate_poll_suppressed(self):
        self.configure()
        for index,phase in enumerate(('MISSION_ARRIVED','FAILED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED')):
            self.job.update(job_id=f'{index:032x}',state=phase,worker_active=False,report_status='SAVED')
            state=self.call();count=len(self.terminal(state))
            self.assertEqual(count,index+1);self.assertIn(phase,state['messages'][-1]['content'])
            self.assertIn('historical',state['messages'][-1]['content'])
            self.assertNotIn('x=0.10',state['messages'][-1]['content'])
            self.assertEqual(len(self.terminal(self.call())),count)

    def test_fault_cleanup_and_report_causes_are_preserved_and_saved(self):
        service=self.configure();self.job.update(state='FAILED',error='INPUT_DEADLINE_EXPIRED',
            error_stage='RUN_CURRENT_MISSION',cleanup_error='OBSERVED_SENSOR_CLEANUP_NOT_CONFIRMED',
            report_error='MISSION_REPORT_STORAGE_FULL',report_status='FAILED',worker_active=False,
            native_cleanup_errors=[{'stage':'mission_halt','code':'STOP_READBACK_UNCONFIRMED','error_type':'ValueError'}])
        state=self.call();message=state['messages'][-1]
        self.assertEqual(message['status'],'failed')
        for cause in ('INPUT_DEADLINE_EXPIRED','RUN_CURRENT_MISSION','OBSERVED_SENSOR_CLEANUP_NOT_CONFIRMED','MISSION_REPORT_STORAGE_FULL','STOP_READBACK_UNCONFIRMED'):
            self.assertIn(cause,message['content'])
        saved=json.loads(service.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['messages'][-1],message)

    def test_late_cleanup_failure_updates_terminal_without_false_success(self):
        self.configure();self.job.update(state='MISSION_ARRIVED',worker_active=True)
        state=self.call();self.assertIn('Cleanup: PENDING',state['messages'][-1]['content'])
        self.job.update(state='FAILED',worker_active=False,cleanup_error='CLEANUP_FAILED',report_status='SAVED')
        state=self.call();self.assertEqual(len(self.terminal(state)),2)
        self.assertEqual(state['messages'][-1]['status'],'failed');self.assertIn('CLEANUP_FAILED',state['messages'][-1]['content'])

    def test_late_native_notes_update_terminal_once_without_new_worker(self):
        self.configure();self.job.update(state='FAILED',error='INPUT_DEADLINE_EXPIRED',worker_active=False)
        first=self.call();count=len(self.terminal(first))
        self.job['native_cleanup_errors']=[{'stage':'mission_halt','code':'STOP_READBACK_UNCONFIRMED','error_type':'ValueError'}]
        after=self.call();self.assertEqual(len(self.terminal(after)),count+1)
        self.assertIn('STOP_READBACK_UNCONFIRMED',after['messages'][-1]['content'])
        self.assertEqual(len(self.terminal(self.call())),count+1)

    def test_stale_missing_nonfinite_or_localizing_frames_never_reuse_pose(self):
        self.configure();self.call()
        for age,phase,pose in ((.201,'DRIVING',[.1,.2,.3]),(None,'DRIVING',[.1,.2,.3]),
                              (.01,'LOCALIZING',[.1,.2,.3])):
            self.job.update(visual_age_s=age,state=phase);self.job['visual']['pose_room']=pose
            self.tick+=5;state=self.call();content=state['messages'][-1]['content']
            self.assertIn('pose/scan unavailable',content);self.assertNotIn('x=0.10',content)

    def test_stop_and_location_loss_do_not_wait_for_interval(self):
        self.configure();self.call();self.tick+=.1;self.job['state']='LOCALIZING'
        state=self.call();self.assertEqual(len(self.progress(state)),1)
        self.assertIn('unavailable',state['messages'][-1]['content'])
        self.job['state']='STOPPING';state=self.call();self.assertEqual(len(self.progress(state)),2)
        self.assertIn('cleanup is pending',state['messages'][-1]['content'])

    def test_other_owner_and_restart_do_not_restore_worker_or_current_pose(self):
        service=self.configure();self.job.update(state='MISSION_ARRIVED',worker_active=False,report_status='SAVED')
        before=self.call();count=len(self.terminal(before))
        restored=ConversationService(self.workflow,service.path,clock=lambda:self.tick)
        state=restored.snapshot();self.assertIsNone(state['navigation']);self.assertFalse(state['physical_authority'])
        self.assertIsNone(state['restore_error']);self.assertEqual(len(self.terminal(state)),count)
        restored.navigation=service.navigation
        # No owner: never import this job. Same owned terminal: persisted dedup.
        self.assertEqual(len(self.terminal(restored.snapshot())),count)
        self.assertEqual(len(self.terminal(restored.snapshot('fixture-owner'))),count)

    def test_save_error_notifies_without_issuing_restart_or_stop(self):
        service=self.configure();self.call();self.tick+=5
        with patch.object(service,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            status,body,_=self.request('/v1/product/conversation',None,headers=self.product_headers)
        self.assertEqual(status,409)
        self.assertIn('conversation_save_failed',str(body));self.assertIsNone(service._state['generation'])

    def test_restart_marks_live_update_historical_without_resuming(self):
        service=self.configure();self.call();self.tick+=5;before=self.call()
        message_id=before['messages'][-1]['message_id']
        restored=ConversationService(self.workflow,service.path)
        state=restored.snapshot();message=next(m for m in state['messages'] if m['message_id']==message_id)
        self.assertEqual(message['status'],'interrupted');self.assertTrue(message['content'].startswith('Historical'))
        self.assertIsNone(state['navigation']);self.assertFalse(state['physical_authority'])
        reopened=ConversationService(self.workflow,service.path).snapshot()
        self.assertEqual(len(reopened['messages']),len(state['messages']));self.assertIsNone(reopened['restore_error'])

    def test_invalid_code_cannot_emit_unbounded_exception_or_nonfinite_text(self):
        content,status=describe_goal_job({'state':'FAILED','elapsed_s':float('nan'),'error':'secret='+('x'*1000)},terminal=True)
        self.assertIn('Cause: UNAVAILABLE',content);self.assertNotIn('secret',content);self.assertEqual(status,'failed')
        content,_=describe_goal_job({'state':'DRIVING','worker_active':True,'visual_age_s':.01,
            'visual':{'state':'DRIVING','pose_room':[float('nan'),.2,.3]}})
        self.assertIn('pose/scan unavailable',content)


if __name__=='__main__':unittest.main()
