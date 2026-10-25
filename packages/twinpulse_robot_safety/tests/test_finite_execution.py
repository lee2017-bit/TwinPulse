# SPDX-License-Identifier: Apache-2.0
"""Finite task authority checks only; fake clock/devices, no hardware PASS."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from twinpulse_core.robot_timing_profile import DEFAULTS,profile
from fleet_control import RobotControl
from teleop_ros import RosLink


class FiniteExecutionTests(unittest.TestCase):
    def make(self,amount=6.283185307179586):
        now=[10.];events=[];outputs=[]
        values=dict(DEFAULTS,input_ttl_ms=1000,output_timeout_ms=1200,operator_presence_ms=5000)
        context=dict(operation_id='op',robot_id='b'*32,connection_epoch='conn',project_id='project',
            boot_id='boot',release_id='release',source_twin_context={'context_id':'twin'},
            timing_profile=profile('b'*32,'a'*64,values=values,mode='custom'))
        owner=RobotControl(context,'.',lambda *a:events.append(a),SimpleNamespace(),clock=lambda:now[0])
        owner._movement_ready=lambda:None;owner._velocity=lambda _: (0.,.2)
        owner.profile={'stop_model':dict(angular_velocity_uncertainty_rad_s=.15,
            linear_velocity_uncertainty_m_s=.03,position_uncertainty_m=.01)}
        # This fixture isolates authority; sensor-age and odom-interval checks
        # have their existing independent fault cases. No body proof implied.
        pose=lambda:dict(x=0.,y=0.,yaw=0.,sample_s=10.,frame_id='odom')
        owner._pose=pose
        def guard(*_):pass
        guard.last_result=None;guard.progress={};guard.reset=lambda:None;owner.guard=guard
        link=SimpleNamespace(enabled=True,sensor=None,rows=[],spin=lambda _:None,fresh=lambda:None)
        link.release=lambda:setattr(link,'enabled',False)
        def publish(v,w,age,**kw):
            kw['before_publish']()
            outputs.append(dict(v=v,w=w,created=now[0]-age))
            return {}
        link.publish=publish;owner.link=link
        command=dict(action='task',request_id='finite',motion_epoch='motion',sequence=1,
            payload=dict(direction='left',amount=amount,text='Turn left 360 degrees',
                motion_generation=0,challenge=owner.gate.challenge(),source_age_ms=0))
        owner._command(command)
        return now,owner,outputs,events

    def watch(self,owner,sequence=2,age_ms=0,challenge=None):
        return dict(action='watch',request_id='watch'+str(sequence),sequence=sequence,
            payload=dict(motion_generation=owner.gate.generation,source_age_ms=age_ms,
                challenge=owner.gate.challenge() if challenge is None else challenge))

    def test_finite_continues_past_remote_input_ttl_with_live_supervision(self):
        now,owner,outputs,_=self.make()
        now[0]=11.2;owner._tick()
        self.assertEqual(len(outputs),1)
        self.assertEqual(owner.gate.source_created,10.)
        owner._command(self.watch(owner));now[0]=12.4;owner._tick()
        self.assertEqual(len(outputs),2)
        self.assertEqual(owner.task['execution']['request_source_s'],10.)
        self.assertEqual(owner.task['execution']['supervision_source_s'],11.2)
        self.assertEqual([row['created'] for row in outputs],[11.2,12.4])

    def test_manual_original_input_still_expires_and_is_never_restamped(self):
        now,owner,outputs,_=self.make()
        owner.task=None;owner.drive_command['action']='drive'
        now[0]=11.001
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):owner._tick()
        self.assertEqual(outputs,[]);self.assertEqual(owner.gate.first_fault['source_created_s'],10.)

    def test_stale_or_repeated_watch_does_not_extend_supervision(self):
        for stale in ('age','nonce','sequence','generation'):
            with self.subTest(stale=stale):
                now,owner,outputs,_=self.make();now[0]=11.2
                command=self.watch(owner)
                if stale=='age':command['payload']['source_age_ms']=1000
                if stale=='nonce':command['payload']['challenge']='0'*24
                if stale=='sequence':command['sequence']=1
                if stale=='generation':command['payload']['motion_generation']=-1
                before=deepcopy(owner.task['execution'])
                with self.assertRaises(ValueError):owner._command(command)
                self.assertEqual(owner.task['execution'],before)
                now[0]=15.
                with self.assertRaisesRegex(ValueError,'TASK_SUPERVISION_EXPIRED'):owner._tick()
                self.assertEqual(outputs,[])

    def test_total_deadline_cannot_be_extended_by_watch(self):
        now,owner,outputs,_=self.make(amount=.2);deadline=owner.task['deadline']
        now[0]=deadline-.1;owner._command(self.watch(owner));now[0]=deadline
        with self.assertRaisesRegex(ValueError,'TASK_DEADLINE'):owner._tick()
        self.assertEqual(outputs,[])

    def test_task_binding_and_stop_cannot_be_bypassed_at_publish(self):
        for fault in ('request','epoch','generation','context','stop','cancel','recording'):
            with self.subTest(fault=fault):
                now,owner,outputs,_=self.make();now[0]=10.2
                original=owner.link.publish
                def interrupted(v,w,age,**kw):
                    if fault=='request':owner.drive_command['request_id']='other'
                    if fault=='epoch':owner.drive_command['motion_epoch']='other'
                    if fault=='generation':owner.gate.generation+=1
                    if fault=='context':owner.context['connection_epoch']='other'
                    if fault=='stop':owner.stop_requested.set()
                    if fault=='cancel':owner.cancel.set()
                    if fault=='recording':owner.field_evidence_fault='ARCHIVE_FAILED'
                    return original(v,w,age,**kw)
                owner.link.publish=interrupted
                with self.assertRaises(ValueError):owner._tick()
                self.assertEqual(outputs,[])

    def test_controller_decision_keeps_start_time_across_slow_computation(self):
        now,owner,outputs,_=self.make()
        owner.link.spin=lambda _:now.__setitem__(0,now[0]+1.01)
        def reject_old(v,w,age,**kw):
            self.assertGreater(age,1.)
            raise ValueError('INPUT_DEADLINE_EXPIRED')
        owner.link.publish=reject_old
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):owner._tick()
        self.assertEqual(owner.task['execution']['decision']['started_s'],10.)
        self.assertEqual(outputs,[])

    def test_sensor_fault_and_completed_task_never_publish(self):
        for fault in ('sensor','complete'):
            now,owner,outputs,_=self.make();now[0]=10.2
            if fault=='sensor':
                owner.link.fresh=lambda:(_ for _ in ()).throw(ValueError('SENSOR_STALE'))
                with self.assertRaisesRegex(ValueError,'SENSOR_STALE'):owner._tick()
            else:
                owner._pose=lambda:dict(x=0.,y=0.,yaw=0.,sample_s=now[0],frame_id='odom')
                owner.task['rotation']=owner.task['amount'];owner._tick()
                self.assertIsNone(owner.task)
            self.assertEqual(outputs,[])

    def test_stop_revokes_authority_and_late_watch_does_not_restore_task(self):
        now,owner,outputs,_=self.make();owner._pause('OPERATOR_STOP')
        owner._command(self.watch(owner));now[0]=11.2;owner._tick()
        self.assertIsNone(owner.task);self.assertIsNone(owner.direction);self.assertEqual(outputs,[])

    def test_disabled_output_requires_fresh_post_arm_watch_for_execution_authority(self):
        now,owner,outputs,_=self.make();owner._pause('OPERATOR_STOP')
        owner.link.enable=lambda:setattr(owner.link,'enabled',True)
        generation=owner.gate.generation;old_watch=self.watch(owner,sequence=2)
        owner._command(dict(action='task',request_id='post-arm',motion_epoch='new-motion',sequence=3,
            payload=dict(direction='left',amount=1.,text='Turn left',motion_generation=generation,
                challenge=owner.gate.challenge(),source_age_ms=0)))
        self.assertEqual(owner.task['status'],'WAITING_POST_ARM_WATCH')
        self.assertNotIn('execution',owner.task);owner._tick();self.assertEqual(outputs,[])
        with self.assertRaisesRegex(ValueError,'MOTION_GENERATION_CHANGED'):owner._command(old_watch)
        with self.assertRaisesRegex(ValueError,'INPUT_AGE'):owner._command(self.watch(owner,4,age_ms=1000))
        self.assertNotIn('execution',owner.task);self.assertEqual(outputs,[])
        owner._command(self.watch(owner,5));self.assertTrue(owner._finite_execution())
        now[0]+=.1;owner._tick();self.assertEqual(len(outputs),1)

    def test_real_publisher_path_preserves_native_and_final_stop_vetoes(self):
        for fault in ('native','stop','supervision','slow_record'):
            with self.subTest(fault=fault):
                now,owner,outputs,_=self.make();now[0]=10.2
                link=RosLink.__new__(RosLink)
                link.enabled=True;link.sensor=SimpleNamespace(torque=True,battery=11.6)
                link.sensor_t=10.2;link.reason='active';link.rows=[]
                link.spin=lambda _:None;link.fresh=lambda:None;link.release=lambda:None
                link.timing_values=owner.timing_values
                link.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=int(now[0]*1e9))))
                link.Twist=lambda:SimpleNamespace(header=SimpleNamespace(frame_id='',stamp=SimpleNamespace(sec=0,nanosec=0)),
                    twist=SimpleNamespace(linear=SimpleNamespace(x=0.),angular=SimpleNamespace(z=0.)))
                link.pub=SimpleNamespace(publish=outputs.append)
                def native(*_):
                    if fault=='native':raise ValueError('FIELD_PROXIMITY')
                    if fault=='stop':owner.stop_requested.set()
                    if fault=='supervision':now[0]=15.
                link.native_output_guard=native;owner.link=link
                def record(*_):
                    if fault=='slow_record':now[0]+=1.01
                with patch('teleop_ros.time.monotonic',side_effect=lambda:now[0]),patch.object(RosLink,'_record',side_effect=record):
                    with self.assertRaisesRegex(ValueError,{'native':'FIELD_PROXIMITY','stop':'OPERATOR_STOP',
                            'supervision':'TASK_SUPERVISION_EXPIRED','slow_record':'INPUT_DEADLINE_EXPIRED'}[fault]):owner._tick()
                self.assertEqual(outputs,[])
                self.assertEqual(link.publication_diagnostic['task_decision']['started_s'],10.2)


if __name__=='__main__':unittest.main()
