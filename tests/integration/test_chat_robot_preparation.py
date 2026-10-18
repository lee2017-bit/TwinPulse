# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Authenticated chat + existing diagnostics; all transports explicit offline.

The reactive controller is a test double, not robot evidence. It completes only
after the adapter sends the one approved qualify input. No subprocess/SSH runs.
"""
from copy import deepcopy
from threading import RLock
import time
import json
import unittest
from uuid import uuid4
from unittest.mock import patch

from tests.integration.test_chat_conversation import ChatConversationTests
from tests.integration.test_robot_diagnostics import fixture, observation
from twinpulse_app.chat_robot_preparation import ChatRobotPreparation
from twinpulse_app.command_broker import BrokerError


class ReactiveController:
    real_transport=False
    def __init__(self):
        self.calls=[]
        self.inputs=[]
        self.state={'state':'NOT_STARTED','busy':False,'job_id':None,'sequence':0,'owned':False,'last_trial':None}
        self.result='QUALIFIED'
        self.boot=None
        self.release=None
        self.cleanup_error=None
        self.hold=False

    def snapshot(self,owner):return deepcopy(self.state)
    def start(self,owner,mode,job,confirmed,app_context=None):
        self.calls.append(mode)
        self.state.update(state='READY',busy=True,job_id=job,sequence=0,owned=True)
        return self.snapshot(owner)
    def input(self,owner,job,sequence,action,expires):
        if not self.state['busy']:raise BrokerError('physical_session','No active worker',status=409)
        self.state['sequence']=sequence
        self.inputs.append(action)
        if action=='qualify' and not self.hold:
            trial={'status':self.result,'job_id':job,'historical':True,'boot_id':self.boot,'release_id':self.release,
                'stop_assessment':{'status':'PASS' if self.result=='QUALIFIED' else 'FAIL'},'cleanup_confirmed':self.cleanup_error is None}
            self.state.update(state='FINISHED',busy=False,result=self.result,last_trial=trial,
                              cleanup_confirmed=self.cleanup_error is None,cleanup_error=self.cleanup_error)
        elif action in {'finish_stop','force_stop'}:
            self.state.update(state='FINISHED',busy=False,result='STOPPED',cleanup_confirmed=True)
        return self.snapshot(owner)


class ChatRobotTests(unittest.TestCase):
    setUp=ChatConversationTests.setUp
    tearDown=ChatConversationTests.tearDown
    request=ChatConversationTests.request
    product_headers=ChatConversationTests.product_headers
    call=ChatConversationTests.call
    send=ChatConversationTests.send
    use_room_gateway=ChatConversationTests.use_room_gateway

    def attach(self, *, fault=None):
        self.use_room_gateway()
        self.controller=ReactiveController()
        self.report=observation()
        self.controller.boot=self.report['health']['boot_id']
        self.controller.release=self.report['health']['deployment']['release_id']
        self.collects=[]
        def collect(*a,**k):
            self.collects.append('READ_ONLY')
            return deepcopy(fault or self.report)
        root=self.static/'robot-fixture';root.mkdir()
        self.diag=fixture(root,collect)
        original=self.diag._pc
        def pc():
            result=original()
            self.diag._local_release_id=self.controller.release
            return result
        self.diag._pc=pc
        service=ChatRobotPreparation(self.diag,self.controller,None,RLock(),lambda:None)
        self.server.chat_robot_preparation=service
        self.server.conversation.robot_preparation=service
        return service

    def choose(self,state,choice, *, fresh=False, request=None):
        card=next(c for c in reversed(state['cards']) if c['state']=='waiting')
        body={'action':'answer','request_id':request or uuid4().hex,'card_id':card['id'],
              'choice_id':choice,'expected_session_revision':card['expected_session_revision']}
        if fresh:body['expires_at_ms']=time.time()*1000+1500
        return self.call(body),body

    def start_real(self):
        state=self.send()
        state,_=self.choose(state,'real')
        return self.choose(state,'turtlebot3_burger')

    def attach_collection(self, *, resume_failure=False, local_failure=False, delay=None):
        from twinpulse_app.robot_readiness import RobotReadiness
        from tests.integration.test_robot_readiness_app import receipt
        service=self.server.chat_robot_preparation
        root=self.static/'collector-fixture'
        source=root/'artifacts/robot-preparation/20261005T000000Z-aaaaaaaa/result/report.json'
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps({'schema_version':'robot-prepare-1.0','action':'stationary',
            'motion_authorized':False,'status':'EVIDENCE_EXPORT_INCOMPLETE','run_id':'stationary-fixture',
            'boot_id':'boot','release_id':'release'}))
        self.collection_calls=[];self.transfer_calls=[]
        data=receipt()
        data['steps']['stationary_collection'].update(report_path=str(source),status='EVIDENCE_EXPORT_INCOMPLETE')
        data['evidence_export']={'status':'INCOMPLETE'}
        if local_failure:
            data.update(status='STOPPED_AT_OFFLINE_PREFLIGHT',reason='LOCAL_CONTRACT_FAILED',evidence={})
            data['steps']={'offline_collection_preflight':{'status':'FAILED','reason':'LOCAL_CONTRACT_FAILED'},
                **{key:{'status':'NOT_RUN','reason':'DEPENDENCY_NOT_SATISFIED'} for key in ('source_and_idle','stationary_collection','evidence_review')}}
        def collect():
            self.collection_calls.append('STATIONARY')
            if delay:delay.wait(3)
            return data,str(root/'collection-report.json'),2
        def resume(path):
            self.transfer_calls.append(str(path))
            if resume_failure:raise TimeoutError('fixture transfer timeout')
            return {'schema_version':'robot-evidence-export-1','run_id':'stationary-fixture','status':'COMPLETE',
                'files':{'ros-messages.raw':{'status':'COPIED'}},'report_binding':{'status':'VERIFIED_SAME_RUN'},
                'raw_replay':{'status':'VERIFIED_OFFLINE'}}
        ready=RobotReadiness(root,runner=collect,resume_runner=resume)
        self.server.robot_readiness=ready;service.readiness=ready
        return ready

    def test_collection_and_transfer_are_separate_idempotent_chat_actions(self):
        self.attach();ready=self.attach_collection()
        self.start_real();self.wait('AWAITING_QUALIFICATION')
        body={'action':'robot_collect','request_id':'stationary-request','expires_at_ms':time.time()*1000+1500,'confirmed_source_transfer':True}
        self.call(body);ready._thread.join(3);state=self.wait('COLLECTION_RESULT');self.call(body)
        collection=state['robot_preparation']['collection']
        self.assertEqual(self.collection_calls,['STATIONARY'])
        self.assertEqual(self.controller.calls,[])
        self.assertEqual(next(v for v in collection['sources'] if v['id']=='odom')['status'],'REJECTED')
        self.assertTrue(collection['resume_available'])
        self.assertFalse(collection['alignment_verified'])
        self.assertTrue(all(c['state']!='waiting' for c in state['cards'] if c['kind']=='robot_qualification'))
        transfer={'action':'robot_transfer','request_id':'transfer-request','expires_at_ms':time.time()*1000+1500,'kind':'stationary','job_id':collection['job_id']}
        self.call(transfer);ready._resume_thread.join(3);state=self.call();self.call(transfer)
        self.assertEqual(len(self.transfer_calls),1)
        self.assertEqual(state['robot_preparation']['collection']['recovery']['status'],'COMPLETE')
        self.assertEqual(state['robot_preparation']['collection']['raw_export']['status'],'INCOMPLETE')
        self.assertFalse(state['physical_authority'])
        self.assertEqual(self.collection_calls,['STATIONARY'])

    def test_transfer_failure_does_not_repeat_collection_or_hide_sensor_fault(self):
        self.attach();ready=self.attach_collection(resume_failure=True)
        self.start_real();self.wait('AWAITING_QUALIFICATION')
        self.call({'action':'robot_collect','request_id':uuid4().hex,'expires_at_ms':time.time()*1000+1500,'confirmed_source_transfer':True})
        ready._thread.join(3);state=self.wait('COLLECTION_RESULT')
        self.call({'action':'robot_transfer','request_id':uuid4().hex,'expires_at_ms':time.time()*1000+1500,'kind':'stationary','job_id':state['robot_preparation']['collection']['job_id']})
        ready._resume_thread.join(3);state=self.call()
        self.assertEqual(state['robot_preparation']['collection']['recovery']['status'],'INCOMPLETE')
        self.assertIn('TimeoutError',state['robot_preparation']['collection']['recovery']['reason'])
        self.assertEqual(self.collection_calls,['STATIONARY'])
        self.assertEqual(self.controller.calls,[])

    def test_collection_approval_expiry_busy_and_save_gates_before_runner(self):
        self.attach();self.attach_collection()
        self.start_real();self.wait('AWAITING_QUALIFICATION')
        body={'action':'robot_collect','request_id':uuid4().hex,'expires_at_ms':0,'confirmed_source_transfer':True}
        self.call(body)
        self.assertEqual(self.collection_calls,[])
        self.controller.state['busy']=True
        self.call(dict(body,request_id=uuid4().hex,expires_at_ms=time.time()*1000+1500))
        self.assertEqual(self.collection_calls,[])
        self.controller.state['busy']=False
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            code,_,_=self.request('/v1/product/conversation',dict(body,request_id=uuid4().hex,expires_at_ms=time.time()*1000+1500),headers=self.product_headers)
        self.assertEqual(code,409)
        self.assertEqual(self.collection_calls,[])

    def test_busy_transfer_cannot_expire_an_unrelated_observation_question(self):
        self.attach();ready=self.attach_collection()
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION')
        card=next(c for c in state['cards'] if c['kind']=='robot_observation' and c['state']=='waiting')
        # Status-only recovery updates do not change the physical question.
        self.controller.state['evidence_recovery']={'status':'TRANSFERRING','transfer_only':True}
        state=self.call()
        self.assertEqual(next(c for c in state['cards'] if c['id']==card['id'])['state'],'waiting')
        body={'action':'robot_collect','request_id':uuid4().hex,'expires_at_ms':time.time()*1000+1500,'confirmed_source_transfer':True}
        self.call(body)
        self.assertEqual(self.collection_calls,[])
        self.controller.state['evidence_recovery']={'status':'NOT_STARTED','transfer_only':True}

    def test_stationary_resume_blocks_other_owner_active_raw_transfer(self):
        service=self.attach();self.attach_collection()
        # Another owner's recovery is hidden from the scoped snapshot.
        # The shared worker still reserves robot access globally.
        with patch.object(self.controller,'evidence_recovery',create=True) as recovery:
            recovery.thread.is_alive.return_value=True
            with self.assertRaises(BrokerError) as caught:
                service.resume_evidence('another-owner','stationary',uuid4().hex,time.time()*1000+1500)
            self.assertEqual(caught.exception.code,'evidence_recovery_busy')
        self.assertEqual(self.transfer_calls,[])

    def wait(self,phase):
        for _ in range(100):
            state=self.call()
            if state['robot_preparation']['state']==phase:return state
            time.sleep(.02)
        self.fail(state['robot_preparation'])

    def test_choice_parallel_check_one_trial_observation_and_idempotency(self):
        self.attach()
        state,selection=self.start_real()
        state=self.wait('AWAITING_QUALIFICATION')
        self.assertEqual(self.collects,['READ_ONLY'])
        self.assertEqual(self.controller.calls,[])
        self.assertFalse(state['physical_authority'])
        self.assertIsNone(state['simulation_review'])
        self.assertEqual(state['robot_preparation']['transport'],'OFFLINE_TEST_TRANSPORT')
        self.call(selection);self.call()
        self.assertEqual(self.collects,['READ_ONLY'])
        state,trial=self.choose(state,'qualify',fresh=True)
        state=self.wait('AWAITING_OBSERVATION')
        self.assertEqual(self.controller.calls,['qualify'])
        self.assertEqual(self.controller.inputs.count('qualify'),1)
        self.call(trial);self.call()
        state,_=self.choose(state,'normal')
        self.assertEqual(state['robot_preparation']['state'],'LINKED')
        self.assertFalse(state['robot_preparation']['demo_ready'])
        self.assertFalse(state['robot_preparation']['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_ssh_failure_preserves_specific_cause_and_generation_completes(self):
        self.attach(fault={'status':'SSH_OR_REMOTE_SETUP_FAILED','exit_code':255,'reason':'PRIVATE_PATH connection refused'})
        self.start_real();state=self.wait('BLOCKED')
        self.assertEqual(state['robot_preparation']['code'],'SSH_CONNECTION_REFUSED')
        self.assertEqual(state['cards'][-1]['kind'],'robot_recheck')
        for _ in range(100):
            state=self.call()
            if state['generation']['state']=='completed':break
            time.sleep(.01)
        self.assertEqual(state['generation']['state'],'completed')
        self.assertNotIn('PRIVATE_PATH',str(state))
        self.assertEqual(self.controller.calls,[])
        self.assertEqual(self.collects,['READ_ONLY'])

    def test_release_mismatch_does_not_deploy_or_qualify(self):
        self.attach();self.report['health']['deployment']['release_id']='b'*64
        self.start_real();state=self.wait('BLOCKED')
        self.assertEqual(state['robot_preparation']['code'],'REVIEWED_RELEASE_MISMATCH')
        self.assertEqual(self.controller.calls,[])

    def test_missing_sensors_do_not_fake_alignment_or_block_bounded_stop(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.assertFalse(state['robot_preparation']['demo_ready'])
        self.assertEqual(self.diag.snapshot('unowned')['job']['sensor_status'],'NO_SENSOR_DATA')

    def test_failed_stop_and_cleanup_causes_preserved_no_repeat(self):
        self.attach();self.controller.result='STOP_FAILED';self.controller.cleanup_error='MOTOR_OFF_READ_FAILED'
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('BLOCKED')
        self.assertEqual(state['robot_preparation']['code'],'STOP_FAILED')
        self.assertEqual(state['robot_preparation']['cleanup_error'],'MOTOR_OFF_READ_FAILED')
        self.assertTrue(any('MOTOR_OFF_READ_FAILED' in m['content'] for m in state['messages']))
        self.choose(state,'check');state=self.wait('BLOCKED')
        self.assertEqual(state['robot_preparation']['code'],'CURRENT_STOP_RECORD_FAILED')
        self.assertEqual(self.controller.calls,['qualify'])

    def test_boot_change_expires_old_button_without_motion(self):
        service=self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.diag._reports._record['boot_id']='00000000-0000-0000-0000-000000000000'
        state=self.wait('EXPIRED')
        self.assertEqual(state['robot_preparation']['code'],'chat_robot_identity_changed')
        self.assertTrue(any(c['kind']=='robot_qualification' and c['state']=='expired' for c in state['cards']))
        self.assertEqual(self.controller.calls,[])

    def test_report_problem_is_latched_for_same_boot_release(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION')
        self.choose(state,'problem');state=self.wait('BLOCKED')
        self.choose(state,'check');state=self.wait('BLOCKED')
        self.assertEqual(state['robot_preparation']['code'],'OPERATOR_REPORTED_PROBLEM')
        self.assertEqual(self.controller.calls,['qualify'])

    def test_restart_expires_history_and_does_not_resume(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        from twinpulse_app.conversation_service import ConversationService
        recovered=ConversationService(self.workflow,self.server.conversation.path).snapshot()
        self.assertIsNone(recovered['restore_error'])
        self.assertEqual(recovered['cards'][-1]['state'],'expired')
        self.assertEqual(self.controller.calls,[])

    def test_existing_real_project_can_explicitly_recheck_after_backend_restart(self):
        self.attach();self.start_real();self.wait('AWAITING_QUALIFICATION')
        from twinpulse_app.conversation_service import ConversationService
        self.server.conversation=ConversationService(self.workflow,self.server.conversation.path)
        # New backend service holds no restored transport ownership/permission.
        self.server.chat_robot_preparation.close()
        service=ChatRobotPreparation(self.diag,self.controller,None,RLock(),lambda:None)
        self.server.chat_robot_preparation=service
        self.server.conversation.robot_preparation=service
        state=self.call()
        self.assertFalse(state['robot_preparation']['owned'])
        self.assertEqual(self.collects,['READ_ONLY'])
        body={'action':'robot_check','request_id':'explicit-reconnect'}
        self.call(body);self.wait('AWAITING_QUALIFICATION');self.call(body)
        self.assertEqual(self.collects,['READ_ONLY','READ_ONLY'])
        self.assertEqual(self.controller.calls,[])

    def test_expired_click_is_consumed_and_not_retried(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        _,body=self.choose(state,'qualify')
        self.assertEqual(self.controller.calls,[])
        state=self.call(body)
        self.assertTrue(any('physical_start_expired' in m['content'] for m in state['messages']))
        self.assertEqual(self.controller.calls,[])

    def test_stop_bypasses_conversation_save_and_provider(self):
        self.attach();self.controller.hold=True
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);self.wait('QUALIFYING')
        with patch.object(self.server.conversation,'_persist',side_effect=OSError('disk-full')):
            code,body,_=self.request('/v1/product/conversation/robot/stop',{'force':True},headers=self.product_headers)
        self.assertEqual(code,200,body)
        self.assertIn('force_stop',self.controller.inputs)
        self.assertEqual(self.controller.calls,['qualify'])

    def test_chat_stop_also_reaches_owned_existing_manual_worker(self):
        service=self.attach();self.start_real();self.wait('AWAITING_QUALIFICATION')
        self.controller.start(service.owner,'control',uuid4().hex,True)
        state=self.call()
        self.assertTrue(state['robot_preparation']['active_control']['busy'])
        code,body,_=self.request('/v1/product/conversation/robot/stop',{'force':False},headers=self.product_headers)
        self.assertEqual(code,200,body)
        self.assertEqual(self.controller.inputs[-1],'finish_stop')
        self.assertEqual(self.controller.calls,['control'])

    def test_normal_stop_waits_for_cleanup_without_escalating_to_force(self):
        from threading import Timer
        service=self.attach();self.controller.hold=True
        original=self.controller.input
        def delayed(owner,job,sequence,action,expires):
            if action!='finish_stop':return original(owner,job,sequence,action,expires)
            self.controller.inputs.append(action)
            self.controller.state.update(state='STOPPING',sequence=sequence)
            Timer(.25,lambda:self.controller.state.update(state='FINISHED',busy=False,
                result='STOPPED',cleanup_confirmed=True)).start()
            return self.controller.snapshot(owner)
        self.controller.input=delayed
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);self.wait('QUALIFYING')
        service.stop(service.owner,force=False)
        state=self.wait('STOPPED')
        self.assertTrue(state['robot_preparation']['cleanup_confirmed'])
        self.assertEqual(self.controller.inputs.count('finish_stop'),1)
        self.assertNotIn('force_stop',self.controller.inputs)

    def test_raw_export_failure_is_separate_from_trial_and_never_demo_success(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.controller.state.update(evidence_export='INCOMPLETE',evidence_export_error='TimeoutExpired',session_log_complete=True)
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION')
        evidence=state['robot_preparation']['evidence']
        self.assertEqual(evidence['evidence_export'],'INCOMPLETE')
        self.assertEqual(evidence['evidence_export_error'],'TimeoutExpired')
        self.assertFalse(state['robot_preparation']['demo_ready'])

    def test_qualification_save_failure_prevents_worker(self):
        self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        card=state['cards'][-1]
        body={'action':'answer','request_id':'save-failed','card_id':card['id'],'choice_id':'qualify',
              'expected_session_revision':card['expected_session_revision'],'expires_at_ms':time.time()*1000+1500}
        with patch.object(self.server.conversation,'_persist',side_effect=BrokerError('conversation_save_failed','Disk full')):
            code,_,_=self.request('/v1/product/conversation',body,headers=self.product_headers)
        self.assertEqual(code,409)
        self.assertEqual(self.controller.calls,[])

    def test_unowned_history_cannot_qualify(self):
        service=self.attach();self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        observed=service.snapshot('different-owner')
        self.assertIsNone(observed['binding']);self.assertIsNone(observed['record'])
        with self.assertRaises(BrokerError):service.qualify('different-owner',state['robot_preparation']['binding'],time.time()*1000+1000)
        self.assertEqual(self.controller.calls,[])

    def test_actual_pc_physical_controller_uses_fixed_worker_and_saves_journal(self):
        import json
        import threading
        from tests.integration.test_physical_controller import FakeChild,FakePipe,FakeOutput
        from twinpulse_app.physical_controller import PhysicalController
        service=self.attach()
        report={'mode':'qualify','status':'QUALIFIED','physical_validation':'OFFLINE_TEST',
            'boot_id':self.controller.boot,'release_id':self.controller.release,
            'cleanup_confirmed':True,'stop_assessment':{'status':'PASS'}}
        children=[]
        class Pipe(FakePipe):
            def write(pipe,data):
                super().write(data)
                if json.loads(data)['action']=='qualify':pipe.child.qualified.set()
        class Output(FakeOutput):
            def readline(output,limit):
                if output.child.qualified.is_set() and not output.child.reported:
                    output.child.reported=True
                    return (json.dumps({'state':'FINISHED','report':report})+'\n').encode()
                return super().readline(limit)
        class Child(FakeChild):
            def __init__(child,*a,**k):
                super().__init__(*a,**k)
                child.qualified=threading.Event();child.reported=False
                child.stdin=Pipe(child);child.stdout=Output(child)
                children.append(child)
        controller=PhysicalController(self.static/'actual-controller',factory=Child,command=lambda root,mode:['fixed-fixture',mode])
        self.server.physical_controller=controller
        service.controller=controller
        self.start_real();state=self.wait('AWAITING_QUALIFICATION')
        self.choose(state,'qualify',fresh=True);state=self.wait('AWAITING_OBSERVATION')
        self.assertEqual(len(children),1)
        self.assertEqual(sum(p['action']=='qualify' for p in children[0].stdin.sent),1)
        job=state['robot_preparation']['job_id']
        directory=controller.root/'artifacts/manual-control'/job
        self.assertTrue((directory/'robot-report.json').is_file())
        self.assertTrue((directory/'session.jsonl').is_file())
        result=json.loads((directory/'result.json').read_text())
        self.assertTrue(result['session_log_complete'])
        self.assertFalse(result['physical_verified'])
        self.assertFalse(result['real_transport'])
        self.assertTrue(state['robot_preparation']['evidence']['session_log_complete'])


if __name__=='__main__':unittest.main()
