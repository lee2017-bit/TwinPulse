# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No-device tests: protocol contract + fixed local fake process, never SSH."""
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tests.integration import test_r5_product_api
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from teleop_contract import InputGate,settling,settling_details,finish_segment
from teleop_worker import control,qualify
from twinpulse_app.physical_controller import PhysicalController,worker_command,valid_event
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.session_journal import SessionJournal
from twinpulse_app.session_history import (list_sessions, review_session, index_project_session,
                                            list_project_sessions, review_project_session)
from twinpulse_core.demo_contract import operation_for_action


class Clock:
    def __init__(self):self.t=0.
    def __call__(self):return self.t


class InputAdmissionTests(unittest.TestCase):
    def test_expired_high_sequence_does_not_poison_current_input(self):
        from unittest.mock import Mock
        controller=PhysicalController.__new__(PhysicalController)
        controller.lock=threading.RLock();controller.owner='owner';controller.job='job'
        controller.thread=Mock();controller.thread.is_alive.return_value=True
        controller.sequence=7;controller.mode='control';controller.wall=lambda:1000.
        controller._record=Mock();controller._pause_manual=Mock()
        with self.assertRaisesRegex(BrokerError,'Expired input'):
            controller.input('owner','job',999,'forward',999.)
        self.assertEqual(controller.sequence,7)
        controller._pause_manual.assert_called_once_with('INPUT_STALE')


class ProtocolTests(unittest.TestCase):
    def test_until_stop_worker_publishes_for_150_seconds_then_explicit_stop(self):
        from types import SimpleNamespace as NS
        c=Clock();pending=[];packets=[];published=[];trace=[];seq=[0]
        class Link:
            enabled=False;reason='active';sensor=NS(battery=12.4)
            def enable(self):self.enabled=True
            def release(self):self.enabled=False
            def halt(self):self.enabled=False
            def spin(self,seconds):c.t+=seconds
            def fresh(self):pass
            def publish(self,v,w,age):published.append((c.t,v,w,age))
        def output(value):
            packets.append(value);seq[0]+=1
            action='force_stop' if c.t>=150 else 'forward'
            pending.append({'sequence':seq[0],'action':action,'challenge':value['challenge'],'age_ms':0})
        incoming=NS(receive=lambda:pending.pop(0) if pending else None)
        result=control(Link(),incoming,output,'control',clock=c,record=lambda k,**d:trace.append((k,d)))
        self.assertEqual(result['status'],'FORCE_STOPPED')
        self.assertGreater(published[-1][0],149.)
        self.assertTrue(all(v==.05 and w==0 and age<.25 for _,v,w,age in published))
        self.assertTrue(all(p['session_policy']=='until-stop-1.0' for p in packets))

    def test_until_stop_presence_and_motion_deadlines_remain_terminal(self):
        for idle in (True,False):
            c=Clock();g=InputGate(c,continuous=True,persistent=True)
            for sequence in range(1,1501):
                c.t=(sequence-1)*.1;g.accept(self.packet(g,sequence,'watch' if idle else 'left'))
                if idle:g.discard_idle_watch()
            c.t+=.5 if idle else .351
            with self.assertRaisesRegex(ValueError,'OPERATOR_PRESENCE_EXPIRED' if idle else 'INPUT_DEADLINE_EXPIRED'):
                g.accept(self.packet(g,1501,'forward'))
            self.assertTrue(g.closed)

    def test_manual_speed_is_separate_from_autonomous_envelope(self):
        from twinpulse_core.local_navigation import checked_command
        self.assertTrue(checked_command(.05,.3,0.,None,1.,require_scan=False,supervised_manual=True)['allowed'])
        for v,w in ((.051,0.),(0.,.301),(float('nan'),0.)):
            self.assertFalse(checked_command(v,w,0.,None,1.,require_scan=False,supervised_manual=True)['allowed'])
        self.assertFalse(checked_command(.05,0.,0.,None,1.,require_scan=False)['allowed'])
        self.assertFalse(checked_command(.05,0.,0.,None,1.,supervised_manual=True)['allowed'])
        self.assertFalse(checked_command(.05,0.,.35,None,1.,require_scan=False,supervised_manual=True)['allowed'])

    def test_production_manual_worker_renews_fresh_hold_without_periodic_release(self):
        from types import SimpleNamespace as NS
        for mode in ('control','control_scan'):
            c=Clock();nonce=[None];sequence=[0];next_input=[0.];events=[];packets=[]
            link=NS(enabled=False,reason='idle',sensor=NS(battery=12.,left_encoder=0,right_encoder=0),
                    spin=lambda dt:setattr(c,'t',c.t+dt),fresh=lambda:None,
                    publish=lambda *_:events.append(('publish',c.t)),halt=lambda:events.append(('halt',c.t)),
                    release=lambda:self.fail('Unexpected periodic release'))
            link.enable=lambda:setattr(link,'enabled',True)
            def output(packet):
                nonce[0]=packet['challenge'];packets.append(packet)
            def receive():
                if c.t<next_input[0] or nonce[0] is None:return None
                sequence[0]+=1;next_input[0]=c.t+.1
                return {'sequence':sequence[0],'action':'close' if c.t>=3.2 else 'forward',
                        'challenge':nonce[0],'age_ms':0}
            result=control(link,NS(receive=receive),output,mode,clock=c)
            self.assertEqual(result['status'],'OPERATOR_STOP')
            self.assertGreater(sum(kind=='publish' for kind,_ in events),25)
            self.assertEqual(sum(kind=='halt' for kind,_ in events),1)
            self.assertGreater(events[-2][1],3.)
            self.assertTrue(all(p['motion_lease_policy']=='fresh-intent-1.0' for p in packets))

    def test_continuous_intent_renews_only_fresh_directions_not_stale_input(self):
        c=Clock();g=InputGate(c,continuous=True)
        for sequence in range(1,51):
            c.t=(sequence-1)*.1
            action,age=g.accept(self.packet(g,sequence,'forward'))
            self.assertEqual(action,'forward');self.assertEqual(age,0.)
            g.check()
        self.assertGreater(c.t,2.);self.assertFalse(g.closed)
        c.t+=.351
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):
            g.accept(self.packet(g,51,'forward'))
        self.assertTrue(g.closed)

    def test_continuous_policy_preserves_session_end_and_expired_nonce(self):
        c=Clock();g=InputGate(c,continuous=True)
        late=self.packet(g,1,'forward');c.t=.351
        with self.assertRaisesRegex(ValueError,'INPUT_EXPIRED'):g.accept(late)
        c=Clock();g=InputGate(c,continuous=True)
        for sequence in range(1,600):
            c.t=(sequence-1)*.1;g.accept(self.packet(g,sequence,'left'))
        c.t=60.
        with self.assertRaisesRegex(ValueError,'SESSION_EXPIRED'):g.accept(self.packet(g,600,'left'))
        self.assertTrue(g.closed)

    def test_display_fault_event_is_bounded_and_not_motion_evidence(self):
        event={'schema':'robot-session-1.0','robot_session_id':'test','event_index':1,
               'clock_domain':'robot_monotonic','t':1.,'kind':'scan_display_fault','data':{'reason':'ANGLE_ENDPOINT'}}
        self.assertTrue(valid_event(event))
        event['data']['reason']='raw unbounded data';self.assertFalse(valid_event(event))

    def test_worker_streams_display_preview_once_per_new_scan_without_arming_wheels(self):
        from types import SimpleNamespace as NS
        from twinpulse_core.ros_observations import scan_preview
        from packages.twinpulse_core.tests.test_ros_observations import message
        c=Clock();c.t=20.;gate=InputGate(c);seq=[0];next_watch=[20.];records=[];halts=[]
        preview=scan_preview(message('scan'),10**10,20.)
        link=NS(enabled=False,reason='idle',sensor=NS(battery=12.,left_encoder=0,right_encoder=0),
            spin=lambda dt:setattr(c,'t',c.t+dt),fresh=lambda:None,halt=lambda:halts.append(True),
            scan_preview=lambda:preview)
        def receive():
            if c.t<next_watch[0]:return None
            seq[0]+=1;next_watch[0]=c.t+.35
            return {'sequence':seq[0],'action':'close' if seq[0]==4 else 'watch',
                    'challenge':gate.challenge(),'age_ms':20}
        result=control(link,NS(receive=receive),lambda _:None,'scan',gate,c,
            record=lambda kind,**data:records.append((kind,data)))
        samples=[data['scan'] for kind,data in records if kind=='scan_preview']
        self.assertEqual(result['status'],'OPERATOR_STOP');self.assertEqual(halts,[True])
        self.assertEqual(len(samples),1);self.assertEqual(samples[0],preview)
        self.assertFalse(link.enabled)

    def test_scan_only_refuses_direction_before_enable(self):
        from types import SimpleNamespace as NS
        c=Clock();g=InputGate(c);armed=[]
        link=NS(enabled=False,reason='idle',sensor=NS(battery=12.,left_encoder=0,right_encoder=0),
            enable=lambda:armed.append(True),spin=lambda dt:setattr(c,'t',c.t+dt),fresh=lambda:None)
        stream=NS(receive=lambda:self.packet(g,1,'forward'))
        with self.assertRaisesRegex(ValueError,'SCAN_ONLY_INPUT_REJECTED'):
            control(link,stream,lambda _:None,'scan',g,c)
        self.assertEqual(armed,[])

    def test_scan_only_warmup_does_not_require_odom_and_checks_cancel(self):
        from types import SimpleNamespace as NS
        from teleop_worker import prepare_manual_scan
        for cancel in (False,True):
            c=Clock();events=[]
            link=NS(received_counts={'scan':3,'odom':0},spin=lambda dt:setattr(c,'t',c.t+dt),
                fresh=lambda:None,fresh_scan=lambda:events.append('scan_fresh'))
            driver=NS(start=lambda:events.append('start'),running=lambda:True)
            incoming=NS(receive=lambda:{'action':'close'} if cancel else None)
            run=lambda:prepare_manual_scan(link,lambda _:None,driver,c,scan_only=True,incoming=incoming)
            if cancel:
                with self.assertRaisesRegex(ValueError,'SCAN_CANCELLED_BEFORE_READY'):run()
                self.assertNotIn('scan_fresh',events)
            else:run();self.assertTrue(link.require_scan_fresh)

    def test_idle_watch_latency_does_not_arm_motion_deadline_in_manual_modes(self):
        from types import SimpleNamespace as NS
        for mode in ('control','control_scan'):
            c=Clock();gate=InputGate(c);seq=[0];next_watch=[0.];events=[]
            link=NS(enabled=False,reason='idle',sensor=NS(battery=12.,left_encoder=0,right_encoder=0),
                spin=lambda dt:setattr(c,'t',c.t+dt),fresh=lambda:None,halt=lambda:events.append('halt'))
            def receive():
                if c.t < next_watch[0]:return None
                seq[0]+=1;next_watch[0]=c.t+.35
                return {'sequence':seq[0],'action':'close' if seq[0]==6 else 'watch',
                        'challenge':gate.challenge(),'age_ms':120}
            result=control(link,NS(receive=receive),lambda _:None,mode,gate,c)
            self.assertEqual(result['status'],'OPERATOR_STOP')
            self.assertGreater(c.t,1.5);self.assertEqual(events,['halt'])

    def test_idle_watch_does_not_relax_fresh_direction_or_session_expiry(self):
        c=Clock();g=InputGate(c)
        g.accept(self.packet(g,1,'watch'));g.discard_idle_watch()
        c.t=.4;g.check();self.assertFalse(g.active)
        packet=self.packet(g,2,'forward');c.t+=.351
        with self.assertRaisesRegex(ValueError,'INPUT_EXPIRED'):g.accept(packet)
        c=Clock();g=InputGate(c);g.accept(self.packet(g,1,'watch'));g.discard_idle_watch()
        g.accept(self.packet(g,2,'forward'));c.t=.35
        with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):g.check()
        c=Clock();g=InputGate(c);g.accept(self.packet(g,1,'watch'));g.discard_idle_watch();c.t=60.
        with self.assertRaisesRegex(ValueError,'SESSION_EXPIRED'):g.check()

    def test_graceful_wait_only_remaining_slice_never_renews_or_publishes(self):
        from types import SimpleNamespace as NS
        for elapsed,wanted in ((.03,.10),(.13,.13)):
            clock=Clock();clock.t=1.;gate=InputGate(clock)
            gate.deadline=1.25;gate.hold_end=2.
            gate.accept({'sequence':1,'action':'finish_stop','challenge':None,'age_ms':0})
            clock.t+=elapsed;spins=[]
            def spin(dt):spins.append(dt);clock.t+=dt
            status=finish_segment(NS(fresh=lambda:None,spin=spin),NS(receive=lambda:None),gate,1.,.1,record=lambda *a,**k:None,clock=clock)
            self.assertEqual(status,'COMMAND_SEGMENT_STOPPED');self.assertAlmostEqual(clock.t,1.+wanted)
            self.assertLessEqual(sum(spins),.070001);self.assertTrue(gate.closed)

    def test_graceful_force_fault_and_original_expiry_take_precedence(self):
        from types import SimpleNamespace as NS
        for cause in ('force','fault','disconnect','expiry','obstacle'):
            clock=Clock();clock.t=1.;gate=InputGate(clock);gate.deadline=1.025 if cause=='expiry' else 1.25;gate.hold_end=2.
            gate.accept({'sequence':1,'action':'finish_stop','challenge':None,'age_ms':0})
            events=[]
            def spin(dt):clock.t+=dt
            def receive():
                if clock.t>=1.02 and cause=='disconnect':raise ValueError('INPUT_CLOSED_OR_OVERFLOW')
                if clock.t>=1.02 and cause=='force':return {'sequence':2,'action':'force_stop','challenge':None,'age_ms':0}
                return None
            def fresh():
                if clock.t>=1.02 and cause=='fault':raise ValueError('TELEMETRY_STALE')
            def safety():
                if clock.t>=1.02 and cause=='obstacle':raise ValueError('OBSTACLE')
            run=lambda:finish_segment(NS(fresh=fresh,spin=spin),NS(receive=receive),gate,1.,.1,
                record=lambda *a,**k:events.append((a,k)),clock=clock,safety=safety)
            if cause in {'fault','disconnect','obstacle'}:
                with self.assertRaises(ValueError):run()
            else:self.assertEqual(run(),'FORCE_STOPPED' if cause=='force' else 'COMMAND_SEGMENT_STOPPED')
            self.assertLessEqual(clock.t,1.026)

    def navigation_fixture(self):
        from types import SimpleNamespace as NS
        from teleop_ros import RosLink
        from twinpulse_core.ros_observations import RosObservations
        from twinpulse_core.local_navigation import CheckedMission
        from twinpulse_core.navigation_binding import PlanarBinding
        from packages.twinpulse_core.tests.test_ros_observations import message
        clock=Clock();clock.t=20.
        link=RosLink.__new__(RosLink);link.enabled=False
        link.navigation=RosObservations()
        for kind in ('odom','scan'):link.navigation.receive(kind,message(kind),10**10,20.,1)
        link.fresh=lambda:None
        link.node=NS(count_publishers=lambda _:1,get_clock=lambda:NS(now=lambda:NS(nanoseconds=int((clock.t-10)*1e9))))
        link.sensor=NS(torque=True);link.reason='active'
        calls={'armed':0,'halted':0,'sent':[]}
        link.Twist=lambda:NS(header=NS(frame_id='',stamp=NS(sec=0,nanosec=0)),
                             twist=NS(linear=NS(x=0.),angular=NS(z=0.)))
        link.pub=NS(publish=calls['sent'].append)
        def enable():calls['armed']+=1;link.enabled=True;clock.t+=.01
        def halt():calls['halted']+=1;link.enabled=False
        link.enable=enable;link.halt=halt
        mission=CheckedMission(((1.,.2),),20.,provenance='live_sensor',frame_id='odom')
        binding=PlanarBinding('base_footprint','base_scan',(0.,0.,0.),(.1,0.,0.),.18,'a'*64)
        return clock,link,mission,binding,calls

    def test_navigation_tick_checks_before_and_after_arm_and_publishes_original_age(self):
        clock,link,mission,binding,calls=self.navigation_fixture()
        with patch('teleop_ros.time.monotonic',clock):
            result=link.navigation_step(mission,binding,20.)
        self.assertTrue(result['allowed']);self.assertFalse(result['physical_authority'])
        self.assertEqual(calls['armed'],1);self.assertEqual(len(calls['sent']),1)
        msg=calls['sent'][0];self.assertEqual(msg.twist.linear.x,.03)
        self.assertAlmostEqual(msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,10.,places=7)

    def test_navigation_running_zero_preserves_owner_without_blocking_motor_off(self):
        from types import SimpleNamespace as NS
        for post_arm in (False,True):
            clock,link,mission,binding,calls=self.navigation_fixture()
            link.enabled=not post_arm
            outputs=iter(([.03,0.] if post_arm else [0.]))
            def step(*args,**kwargs):
                return {'allowed':True,'reason':'REPLANNING','linear_m_s':next(outputs),'angular_rad_s':0.}
            mission=NS(provenance='live_sensor',frame_id='odom',mission=NS(status='RUNNING'),step=step)
            with patch('teleop_ros.time.monotonic',clock):link.navigation_step(mission,binding,20.)
            self.assertTrue(link.enabled);self.assertEqual(calls['halted'],0)
            self.assertEqual(len(calls['sent']),1);self.assertEqual(calls['sent'][0].twist.linear.x,0.)
            self.assertLess(clock.t-20.,.02)

    def test_reviewed_goal_arms_without_output_then_checks_a_new_tick_once(self):
        clock,link,mission,binding,calls=self.navigation_fixture()
        mission.approved_preview={'test_only':True};mission.current_pose_valid=True
        checked=[];mission.validate_first_output=lambda now:checked.append(now)
        original=mission.step;decisions=[]
        def step(*args,**kwargs):
            decisions.append(args[2]);return original(*args,**kwargs)
        mission.step=step
        with patch('teleop_ros.time.monotonic',clock):
            armed=link.navigation_step(mission,binding,20.)
            self.assertEqual(armed['reason'],'ARMED_AWAITING_FRESH_REVIEWED_TICK')
            self.assertEqual((armed['linear_m_s'],armed['angular_rad_s']),(0.,0.))
            self.assertEqual(calls['sent'],[]);self.assertEqual(checked,[])
            self.assertFalse(mission.current_pose_valid)
            from twinpulse_app.physical_controller import valid_mission_decision
            self.assertTrue(valid_mission_decision(armed,clock.t,adaptive=True))
            self.assertFalse(valid_mission_decision(armed,clock.t,adaptive=False))
            self.assertFalse(valid_mission_decision({**armed,'linear_m_s':.03},clock.t,adaptive=True))
            link.navigation_step(mission,binding,clock.t)
        self.assertEqual(calls['armed'],1);self.assertEqual(len(decisions),2)
        self.assertEqual(len(calls['sent']),1);self.assertEqual(len(checked),1)

    def test_reviewed_planning_pumps_original_input_before_arming_without_resetting_age(self):
        clock,link,mission,binding,calls=self.navigation_fixture()
        mission.approved_preview={'test_only':True}
        gate=InputGate(clock);sequence=[1];pumps=[];armed_at=[]
        gate.accept({'sequence':1,'action':'watch','challenge':gate.challenge(),'age_ms':100.})
        original_step=mission.step
        def step(*args,**kwargs):
            result=original_step(*args,**kwargs);clock.t+=.105;return result
        mission.step=step
        def pump():
            gate.check();pumps.append(clock.t)
            if clock.t>20.05:
                sequence[0]+=1
                gate.accept({'sequence':sequence[0],'action':'watch','challenge':gate.challenge(),'age_ms':0.})
        def enable():
            armed_at.append(clock.t);calls['armed']+=1;link.enabled=True;clock.t+=.08
            # New synthetic callbacks, not a re-stamped cached observation.
            from packages.twinpulse_core.tests.test_ros_observations import message
            stamp=int((clock.t-10)*1e9)
            for kind in ('odom','scan'):
                link.navigation.receive(kind,message(kind,stamp-50000000),stamp,clock.t,1)
        link.enable=enable
        with patch('teleop_ros.time.monotonic',clock):
            result=link.navigation_step(mission,binding,20.,before_publish=pump)
        self.assertEqual(result['reason'],'ARMED_AWAITING_FRESH_REVIEWED_TICK')
        self.assertEqual(calls['sent'],[])
        self.assertEqual(pumps[:2],[20.,20.105]);self.assertEqual(armed_at,[20.105])
        self.assertAlmostEqual(clock.t-20.,.185)

    def test_reviewed_planning_cannot_pump_away_expiry_or_a_stop_before_arm(self):
        from teleop_contract import RequestedStop
        for cause in ('expired','stop'):
            clock,link,mission,binding,calls=self.navigation_fixture()
            mission.approved_preview={'test_only':True};original_step=mission.step
            gate=InputGate(clock)
            gate.accept({'sequence':1,'action':'watch','challenge':gate.challenge(),'age_ms':0.})
            def step(*args,**kwargs):
                result=original_step(*args,**kwargs);clock.t+=.351 if cause=='expired' else .01;return result
            mission.step=step
            def pump():
                gate.check()
                if cause=='stop' and clock.t>20.:raise RequestedStop('force_stop',2)
            with patch('teleop_ros.time.monotonic',clock):
                if cause=='expired':
                    with self.assertRaisesRegex(ValueError,'INPUT_DEADLINE_EXPIRED'):
                        link.navigation_step(mission,binding,20.,before_publish=pump)
                else:
                    with self.assertRaises(RequestedStop):
                        link.navigation_step(mission,binding,20.,before_publish=pump)
            self.assertEqual(calls['armed'],0);self.assertEqual(calls['sent'],[])

    def test_reviewed_goal_post_arm_fault_and_later_changed_scan_never_output(self):
        for cause in ('stale','obstacle','old_command','next_tick_obstacle','first_output_review'):
            clock,link,mission,binding,calls=self.navigation_fixture()
            mission.approved_preview={'test_only':True}
            original=link.enable
            def enable():
                original()
                if cause=='stale':clock.t+=.36
                if cause=='obstacle':link.navigation.values['scan']['ranges_m']=[.2]*72
                if cause=='old_command':clock.t+=.04
            link.enable=enable
            def reject(now):raise ValueError('GOAL_PREVIEW_START_MAP_OR_SOURCE_CHANGED')
            mission.validate_first_output=reject if cause=='first_output_review' else lambda now:None
            with patch('teleop_ros.time.monotonic',clock),self.assertRaises(ValueError):
                link.navigation_step(mission,binding,19.68 if cause=='old_command' else 20.)
                if cause=='next_tick_obstacle':link.navigation.values['scan']['ranges_m']=[.2]*72
                link.navigation_step(mission,binding,clock.t)
            self.assertEqual(calls['sent'],[]);self.assertEqual(calls['halted'],1)

    def test_navigation_missing_binding_obstacle_and_endpoint_never_arm(self):
        for cause in ('binding','obstacle','endpoint'):
            clock,link,mission,binding,calls=self.navigation_fixture()
            if cause=='binding':binding=None
            if cause=='obstacle':link.navigation.values['scan']['ranges_m']=[.2]*72
            if cause=='endpoint':link.node.count_publishers=lambda _:2
            with patch('teleop_ros.time.monotonic',clock),self.assertRaises(ValueError):
                link.navigation_step(mission,binding,20.)
            self.assertEqual(calls['armed'],0);self.assertEqual(calls['sent'],[])
            self.assertNotEqual(mission.mission.status,'RUNNING')

    def test_navigation_post_arm_stale_or_obstacle_stops_without_output(self):
        for cause in ('stale','obstacle','partial_arm_failure','old_command'):
            clock,link,mission,binding,calls=self.navigation_fixture()
            def enable():
                calls['armed']+=1
                if cause=='partial_arm_failure':raise ValueError('SERVICE_FAILED')
                link.enabled=True
                if cause=='stale':clock.t+=.36
                if cause=='obstacle':link.navigation.values['scan']['ranges_m']=[.2]*72
                if cause=='old_command':clock.t+=.04
            link.enable=enable
            created=19.68 if cause=='old_command' else 20.
            with patch('teleop_ros.time.monotonic',clock),self.assertRaises(ValueError):
                link.navigation_step(mission,binding,created)
            self.assertEqual(calls['halted'],1);self.assertEqual(calls['sent'],[])
            self.assertNotEqual(mission.mission.status,'RUNNING')

    def test_navigation_final_publish_rechecks_scan_and_does_not_resume_terminal(self):
        clock,link,mission,binding,calls=self.navigation_fixture()
        original=link.publish
        def delayed(v,w,age,**kwargs):
            link.navigation.values['scan']['ranges_m']=[.2]*72
            return original(v,w,age,**kwargs)
        link.publish=delayed
        with patch('teleop_ros.time.monotonic',clock),self.assertRaisesRegex(ValueError,'OBSTACLE'):
            link.navigation_step(mission,binding,20.)
        self.assertEqual(calls['sent'],[]);self.assertEqual(calls['halted'],1)
        link.navigation.values['scan']['ranges_m']=[1.]*72
        with patch('teleop_ros.time.monotonic',clock),self.assertRaises(ValueError):
            link.navigation_step(mission,binding,clock.t)
        self.assertEqual(calls['armed'],1)

    def test_navigation_arrival_is_zero_and_failed_stop_is_not_success(self):
        for fail in (False,True):
            clock,link,mission,binding,calls=self.navigation_fixture()
            link.enabled=True;mission.mission.waypoints=((.1,.2),)
            if fail:link.halt=lambda:(_ for _ in ()).throw(ValueError('STOP_READBACK_UNCONFIRMED'))
            with patch('teleop_ros.time.monotonic',clock):
                if fail:
                    with self.assertRaisesRegex(ValueError,'STOP_READBACK'):link.navigation_step(mission,binding,20.)
                    self.assertNotEqual(mission.mission.status,'ARRIVED')
                else:
                    self.assertEqual(link.navigation_step(mission,binding,20.)['reason'],'STOP')
                    self.assertEqual(calls['halted'],1)
            self.assertEqual(calls['sent'],[]);self.assertEqual(calls['armed'],0)

    def packet(self,gate,seq=1,action='forward',challenge=None):
        return {'sequence':seq,'action':action,'challenge':challenge or gate.challenge(),'age_ms':0}

    def test_challenge_age_and_replay(self):
        c=Clock();g=InputGate(c);n=g.challenge();c.t=.2
        self.assertAlmostEqual(g.accept(self.packet(g,challenge=n))[1],.2)
        self.assertAlmostEqual(g.deadline,.35)
        with self.assertRaises(ValueError):g.accept(self.packet(g,2,challenge=n))
        c.t=.351
        with self.assertRaises(ValueError):g.check()

    def test_pc_queue_age_cannot_be_refreshed_by_new_robot_nonce(self):
        c=Clock();g=InputGate(c);packet=self.packet(g);packet['age_ms']=300
        c.t=.06
        with self.assertRaises(ValueError):g.accept(packet)
        g=InputGate(c);packet=self.packet(g);packet['age_ms']=float('nan')
        with self.assertRaises(ValueError):g.accept(packet)

    def test_old_motion_after_stop_and_invalid_shapes(self):
        g=InputGate();g.accept(self.packet(g,5,'stop'))
        with self.assertRaises(ValueError):g.accept(self.packet(g,4))
        for value in ({},None,{'sequence':True,'action':'forward','challenge':g.challenge()}):
            with self.assertRaises(ValueError):g.accept(value)

    def test_watch_does_not_extend_movement_hold(self):
        c=Clock();g=InputGate(c)
        g.accept(self.packet(g,1,'watch'));c.t=.1;g.accept(self.packet(g,2,'forward'))
        self.assertEqual(g.hold_end,2.1)
        for i in range(3,23):
            c.t+=.09;g.accept(self.packet(g,i,'left' if i%2 else 'right'))
        c.t=2.11
        with self.assertRaises(ValueError):g.check()

    def test_stale_nonce_future_and_session_limits(self):
        c=Clock();g=InputGate(c);n=g.challenge();c.t=.351
        with self.assertRaises(ValueError):g.accept(self.packet(g,challenge=n))
        c.t=61
        with self.assertRaises(ValueError):g.check()

    def test_timeout_reasons_keep_exact_limits(self):
        for expected,now,deadline,hold in [('SESSION_EXPIRED',60.,100.,100.),
                ('INPUT_DEADLINE_EXPIRED',.25,.25,2.),('HOLD_LIMIT_EXCEEDED',2.,2.1,2.)]:
            c=Clock();g=InputGate(c);g.active=True;g.deadline=deadline;g.hold_end=hold;c.t=now
            with self.assertRaisesRegex(ValueError,expected):g.check()
            self.assertTrue(g.closed)

    def test_repeated_release_keeps_session_and_records_actual_publish_only(self):
        c=Clock();q=queue.Queue();g=InputGate(c);events=[];trace=[]
        class Sensor: battery=12.;left_encoder=0;right_encoder=0
        class Link:
            reason='explicit_stop';sensor=Sensor();enabled=False
            def spin(self,seconds):c.t+=seconds
            def fresh(self):pass
            def enable(self):self.enabled=True;events.append('enable')
            def publish(self,v,w,age):events.append((v,w))
            def release(self):self.enabled=False;events.append('release');c.t+=.55
            def halt(self):self.enabled=False;events.append('final')
        class Stream:
            def receive(self):
                try:return q.get_nowait()
                except queue.Empty:return None
        actions=iter(['forward','forward','stop','watch','left','left','stop','watch','close'])
        seq=0
        def output(value):
            nonlocal seq
            seq+=1;q.put(self.packet(g,seq,next(actions),value['challenge']))
        result=control(Link(),Stream(),output,'control',g,c,record=lambda k,**d:trace.append((k,d)))
        self.assertEqual(result['status'],'OPERATOR_STOP')
        self.assertEqual(events,['enable',(.05,0.),'release','enable',(0.,.3),'release','final'])
        self.assertEqual([d['sequence'] for k,d in trace if k=='published'],[2,6])
        self.assertEqual(sum(k=='accepted' for k,d in trace),9)

    def test_fixed_stop_acceptance_missing_and_failure(self):
        rows=[{'t':i*.05,'encoders':[20 if i>=15 else i*2,20 if i>=15 else i*2]} for i in range(31)]
        self.assertTrue(settling(rows,1.))
        moving=[{'t':i*.05,'encoders':[i*10,i*10]} for i in range(31)]
        self.assertFalse(settling(moving,1.))
        self.assertFalse(settling(rows[:22],1.))
        self.assertFalse(settling([*rows[:20],*rows[25:]],1.))

    def test_saved_real_stop_trace_remains_failed_with_explanation(self):
        # Values transcribed from actual 347a6455... report; no hardware access.
        samples=[(311.428730165,3122,2397),(311.471530694,3147,2423),
                 (311.519029681,3171,2443),(311.574124924,3192,2464),
                 (311.621797013,3198,2469),(311.680842451,3202,2471),
                 (311.726573732,3202,2473),(311.768792432,3203,2474),
                 (311.828919986,3205,2476),(311.870045164,3206,2476),
                 (311.920176751,3207,2476)]
        rows=[{'t':t,'encoders':[l,r]} for t,l,r in samples]
        detail=settling_details(rows,311.460813106)
        self.assertFalse(detail['passed'])
        self.assertEqual(detail['reason'],'ENCODER_SETTLING_SHORT')
        self.assertAlmostEqual(detail['stable_ms'],90.767942,places=5)
        self.assertFalse(settling(rows,311.460813106))
        missing=settling_details(rows[:3],311.460813106)
        self.assertIsNone(missing['stable_ms'])
        self.assertEqual(missing['reason'],'SENSOR_COVERAGE_INVALID')

    def test_real_loop_requires_post_arm_input_and_close_halts(self):
        c=Clock();q=queue.Queue();g=InputGate(c);events=[]
        class Sensor: battery=12.;left_encoder=0;right_encoder=0
        class Link:
            reason='explicit_stop';sensor=Sensor();enabled=False
            def spin(self,seconds):c.t+=seconds
            def fresh(self):pass
            def enable(self):self.enabled=True;events.append('enable')
            def publish(self,v,w,age):events.append((v,w,age))
            def halt(self):events.append('halt');self.enabled=False
        class Stream:
            def receive(self):
                try:return q.get_nowait()
                except queue.Empty:return None
        seq=0
        def output(value):
            nonlocal seq
            seq+=1
            q.put({'sequence':seq,'action':'forward' if seq<3 else 'close','challenge':value['challenge'],'age_ms':0})
        result=control(Link(),Stream(),output,'control',g,c)
        self.assertEqual(result['status'],'OPERATOR_STOP')
        self.assertEqual(events[0],'enable');self.assertEqual(events[1][:2],(.05,0.))
        self.assertEqual(events[-1],'halt');self.assertEqual(len(events),3)
        c=Clock();g=InputGate(c);q=queue.Queue();events.clear()
        def qualify_output(value):
            q.put({'sequence':1,'action':'qualify','challenge':value['challenge'],'age_ms':0})
        def consumed():raise ValueError('TRIAL_ALREADY_CONSUMED')
        with self.assertRaisesRegex(ValueError,'TRIAL_ALREADY_CONSUMED'):
            control(Link(),Stream(),qualify_output,'qualify',g,c,before_trial=consumed)
        self.assertEqual(events,[])  # Marker failure precedes even torque enable.

    def test_qualification_loop_separates_deceleration_and_verification(self):
        for unstable in (False,True):
            c=Clock();g=InputGate(c);q=queue.Queue();counter=0
            class Sensor: battery=12.;left_encoder=0;right_encoder=0;torque=True
            class Link:
                sensor=Sensor();reason='active';rows=[];last=0.
                def enable(self):pass
                def publish(self,*_):self.last=c.t
                def fresh(self):pass
                def spin(self,dt):
                    c.t+=dt
                    if c.t-self.last>=.4:self.reason='command_timeout'
                    if self.reason!='command_timeout' or unstable:
                        self.sensor.left_encoder+=1;self.sensor.right_encoder+=1
                    self.rows.append({'t':c.t,'encoders':[self.sensor.left_encoder,self.sensor.right_encoder],
                                      'torque':True,'source_age_s':0.})
            class Stream:
                def receive(self):
                    try:return q.get_nowait()
                    except queue.Empty:return None
            def output(value):
                nonlocal counter
                counter+=1;q.put({'sequence':counter,'action':'watch','challenge':value['challenge'],'age_ms':0})
            result=qualify(Link(),Stream(),output,g,c)
            self.assertEqual(result['status'],'STOP_POLICY_FAIL' if unstable else 'STOP_POLICY_PASS')
            self.assertEqual(result['stop_assessment']['status'],'FAIL' if unstable else 'PASS')
            self.assertEqual(result['required_stable_ms'],200)
            self.assertEqual(result['window_ms'],500)

    def test_ros_publish_preserves_source_age(self):
        from types import SimpleNamespace as NS
        from teleop_ros import RosLink
        link=RosLink.__new__(RosLink);sent=[]
        link.fresh=lambda:None;link.sensor=NS(torque=True);link.reason='active'
        link.node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=10**10)))
        link.pub=NS(publish=sent.append)
        link.Twist=lambda:NS(header=NS(stamp=NS()),twist=NS(linear=NS(),angular=NS()))
        link.publish(.03,0.,.15)
        self.assertEqual(sent[0].header.stamp.sec,9)
        self.assertEqual(sent[0].header.stamp.nanosec,850000000)
        with self.assertRaises(ValueError):link.publish(.03,0.,.351)
        for v,w,age in [(float('nan'),0.,0.),(.031,0.,0.),(0.,.201,0.),(.03,0.,float('inf'))]:
            with self.assertRaises(ValueError):link.publish(v,w,age)
        self.assertEqual(len(sent),1)

    def test_rolling_sensor_tail_never_moves_release_observation_cursor(self):
        from types import SimpleNamespace as NS
        from teleop_ros import RosLink
        link=RosLink.__new__(RosLink);link.rows=[{'t':0.} for _ in range(10000)]
        link.anchor=[0,0];link.changed=0.;link.persistent_manual=True;link.release_observing=True
        link.node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=10**10)))
        msg=NS(left_encoder=1,right_encoder=1,torque=False,battery=12.,header=NS(stamp=NS(sec=10,nanosec=0)))
        link._sensor(msg);self.assertEqual(len(link.rows),10001)
        link.release_observing=False;link._sensor(msg)
        self.assertEqual(len(link.rows),9002)

    def test_robot_bundle_uses_exact_shared_core_without_transport(self):
        import tarfile
        sys.path.insert(0,str(ROOT/'scripts'))
        from prepare_robot import bundle
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'offline.tar';bundle(path)
            with tarfile.open(path) as archive:
                self.assertEqual(archive.extractfile('local_navigation.py').read(),
                                 (ROOT/'packages/twinpulse_core/src/twinpulse_core/local_navigation.py').read_bytes())
                self.assertEqual(archive.extractfile('ros_observations.py').read(),
                                 (ROOT/'packages/twinpulse_core/src/twinpulse_core/ros_observations.py').read_bytes())
                self.assertEqual(archive.extractfile('navigation_binding.py').read(),
                                 (ROOT/'packages/twinpulse_core/src/twinpulse_core/navigation_binding.py').read_bytes())

    def test_ros_passive_subscriptions_callbacks_do_not_start_drivers_or_transform(self):
        from types import SimpleNamespace as NS
        from packages.twinpulse_core.tests.test_ros_observations import message
        import teleop_ros
        subscriptions={};publishers=[];calls=[]
        node=NS(create_publisher=lambda *a:publishers.append(a),create_client=lambda *a:NS(),
                create_subscription=lambda _type,name,callback,_q:subscriptions.update({name:callback}),
                count_publishers=lambda _:1,get_clock=lambda:NS(now=lambda:NS(nanoseconds=10**10)))
        modules={'rclpy':NS(init=lambda:calls.append('init'),create_node=lambda *a,**k:node),
                 'rclpy.qos':NS(qos_profile_sensor_data=NS(depth=5),QoSProfile=lambda **_:NS(),
                                DurabilityPolicy=NS(TRANSIENT_LOCAL=1)),
                 'geometry_msgs.msg':NS(TwistStamped=object),'std_msgs.msg':NS(String=object),
                 'std_srvs.srv':NS(Trigger=object,SetBool=object),'turtlebot3_msgs.msg':NS(SensorState=object),
                 'nav_msgs.msg':NS(Odometry=object),'sensor_msgs.msg':NS(LaserScan=object),
                 'tf2_msgs.msg':NS(TFMessage=object)}
        with patch.dict(sys.modules,modules),patch.object(teleop_ros.time,'monotonic',return_value=20.):
            link=teleop_ros.RosLink(NS())
            subscriptions['odom'](message());subscriptions['/scan'](message('scan'))
            snapshot=link.navigation_snapshot()
        self.assertEqual(set(subscriptions),{'sensor_state','motion_guard/status','odom','/scan','/tf','/tf_static'})
        self.assertEqual(len(publishers),1);self.assertEqual(calls,['init'])
        self.assertEqual(snapshot['scan']['frame_id'],'base_scan')
        self.assertEqual(snapshot['odom']['child_frame_id'],'base_footprint')
        self.assertFalse(snapshot['alignment_verified']);self.assertFalse(link.enabled)

    def test_checked_mission_fake_ros_output_retains_command_age_and_stops_on_scan_loss(self):
        from types import SimpleNamespace as NS
        from twinpulse_core.local_navigation import CheckedMission, LocalPose, LocalScan
        from teleop_ros import RosLink
        sent=[];link=RosLink.__new__(RosLink);link.fresh=lambda:None
        link.sensor=NS(torque=True);link.reason='active'
        link.node=NS(get_clock=lambda:NS(now=lambda:NS(nanoseconds=10**10)))
        link.pub=NS(publish=sent.append)
        link.Twist=lambda:NS(header=NS(stamp=NS()),twist=NS(linear=NS(),angular=NS()))
        mission=CheckedMission(((1.,0.),),0.,provenance='live_sensor',frame_id='odom')
        pose=LocalPose((0.,0.,0.),.1,'odom','measured_odometry','live_sensor')
        scan=LocalScan((1.,)*72,.1,'base_link','measured_sensor_extrinsic','live_sensor')
        decision=mission.step(pose,scan,.1,command_created_s=.05)
        self.assertTrue(decision['allowed'])
        link.publish(decision['linear_m_s'],decision['angular_rad_s'],.05)
        self.assertEqual(sent[-1].header.stamp.nanosec,950000000)
        lost=mission.step(pose,None,.11,command_created_s=.1)
        self.assertFalse(lost['allowed']);self.assertEqual(lost['linear_m_s'],0.)
        # Same guarded output function, no enable/qualification fabricated by mission.
        link.publish(lost['linear_m_s'],lost['angular_rad_s'],.01)
        self.assertEqual(sent[-1].twist.linear.x,0.)
        self.assertFalse(mission.step(pose,scan,.12,command_created_s=.12)['allowed'])


class FakePipe:
    def __init__(self,child):self.child=child;self.closed=False;self.sent=[]
    def write(self,data):
        if self.closed:raise OSError()
        self.sent.append(json.loads(data))
    def flush(self):pass
    def close(self):self.closed=True;self.child.done.set()


class FakeOutput:
    def __init__(self,child):self.child=child
    def readline(self,_limit):
        if self.child.done.wait(.025):return b''
        return (json.dumps({'state':'READY','challenge':'a'*24})+'\n').encode()


class FakeChild:
    def __init__(self,*args,**kwargs):
        self.done=threading.Event();self.stdin=FakePipe(self);self.stdout=FakeOutput(self)
    def poll(self):return 0 if self.done.is_set() else None
    def wait(self,timeout=None):
        self.done.wait(timeout)
        return self.poll()
    def terminate(self):self.done.set()


def history_fixture(root, job='a'*32):
    out=Path(root)/'artifacts/manual-control'/job;out.mkdir(parents=True)
    def robot(index,t,kind,data):
        return {'schema':'robot-session-1.0','robot_session_id':'fixture','event_index':index,
                'clock_domain':'robot_monotonic','t':t,'kind':kind,'data':data}
    events=[robot(1,10.,'published',{'sequence':2,'action':'forward','linear_m_s':.03,'angular_rad_s':0.,'source_age_s':.01}),
            robot(2,10.1,'observation',{'guard':'active','sample':{'t':10.05,'encoders':[5,6],'torque':True,'source_age_s':.05}})]
    rows=[{'schema':'control-session-1.0','job_id':job,'event_index':i+1,'clock_domain':'pc_monotonic',
           't':1000.+i,'kind':'robot_event','real_transport':False,'data':{'event':e}} for i,e in enumerate(events)]
    rows.append({**rows[0],'event_index':3,'t':1002.,'kind':'robot_finished',
                 'data':{'status':'FAILED','reason':'INPUT_DEADLINE_EXPIRED','robot_session_id':'fixture','cleanup_confirmed':True}})
    log=out/'session.jsonl';log.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    (out/'result.json').write_text(json.dumps({'session_log_complete':True,'session_event_count':3,'real_transport':False}),encoding='utf-8')
    return out,rows


class HistoryTests(unittest.TestCase):
    def test_consumed_rejection_preserves_actual_trial_but_not_failed_new_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'artifacts/manual-control'
            for name,value in [('first',{'mode':'qualify','status':'QUALIFIED','boot_id':'boot',
                    'release_id':'r','cleanup_confirmed':True,'stop_assessment':{'status':'PASS'}}),
                ('second',{'mode':'qualify','status':'FAILED','reason':'TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED',
                    'boot_id':'boot','release_id':'r','cleanup_confirmed':True})]:
                out=folder/name;out.mkdir(parents=True)
                (out/'robot-report.json').write_text(json.dumps(value))
            from twinpulse_app.physical_controller import rejected_consumed_trial
            self.assertFalse(rejected_consumed_trial({'reason':'TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED',
                'cleanup_confirmed':False}))
            self.assertFalse(rejected_consumed_trial({'reason':'TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED',
                'cleanup_confirmed':True,'stop_assessment':{'status':'FAIL'}}))
            p=PhysicalController(td)
            self.assertEqual(p.last_trial['job_id'],'first')
            self.assertEqual(json.loads((folder/'second/robot-report.json').read_text())['status'],'FAILED')
            p.close()
    def test_frozen_app_context_is_review_only_and_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td,'d'*32)
            scene='1'*64
            rows.insert(0,{**rows[0],'event_index':1,'t':999.,'kind':'pc_session_started',
                           'data':{'mode':'control','project_id':'default','app_context':{
                               'app_scene_revision':scene,'app_robot_profile_id':'turtlebot3_burger',
                               'capture_status':'CAPTURED'}}})
            for n,row in enumerate(rows,1):row['event_index']=n
            log=out/'session.jsonl'
            log.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            (out/'result.json').write_text(json.dumps({'session_log_complete':True,
                'session_event_count':4,'real_transport':False}),encoding='utf-8')
            index_project_session(td,'default','d'*32)
            view=review_project_session(td,'default','d'*32)
            self.assertEqual(view['comparison_evidence']['app_scene_revision'],scene)
            self.assertEqual(view['comparison_evidence']['app_robot_profile_id'],'turtlebot3_burger')
            self.assertEqual(view['comparison_evidence']['app_context_capture'],'CAPTURED')
            self.assertEqual(view['comparison_evidence']['room_odom_alignment'],'UNVERIFIED')
            self.assertFalse(view['motion_authorized'])
            log.write_bytes(log.read_bytes().replace(scene.encode(),b'2'*64))
            with self.assertRaises(BrokerError):review_project_session(td,'default','d'*32)

    def test_project_index_reopen_replay_and_cross_project_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            history_fixture(td,'a'*32)  # Old global record is never assigned implicitly.
            self.assertEqual(list_project_sessions(td,'default')['sessions'],[])
            for job,project in (('b'*32,'default'),('c'*32,'bedroom-b')):
                out,rows=history_fixture(td,job)
                rows.insert(0,{**rows[0],'event_index':1,'t':999.,'kind':'pc_session_started',
                               'data':{'mode':'control','project_id':project}})
                for n,row in enumerate(rows,1):row['event_index']=n
                (out/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
                (out/'result.json').write_text(json.dumps({'session_log_complete':True,
                    'session_event_count':4,'real_transport':False}),encoding='utf-8')
                index_project_session(td,project,job)
            self.assertEqual([e['job_id'] for e in list_project_sessions(td,'default')['sessions']],['b'*32])
            self.assertEqual([e['job_id'] for e in list_project_sessions(td,'bedroom-b')['sessions']],['c'*32])
            view=review_project_session(td,'default','b'*32)
            self.assertEqual(view['record_status'],'COMPLETE_RECORD')
            self.assertEqual(view['attribution'],'BOUND')
            self.assertEqual([e['kind'] for e in view['timeline']],
                             ['pc_session_started','published','observation','robot_finished'])
            self.assertEqual(view['timeline'][1]['robot_t'],10.)
            self.assertEqual(view['timeline'][1]['pc_t'],1000.)
            self.assertFalse(view['timeline'][1]['observation_gap'])
            self.assertFalse(view['motion_authorized'])
            with self.assertRaises(BrokerError):review_project_session(td,'bedroom-b','b'*32)
            with self.assertRaises(BrokerError):review_project_session(td,'default','a'*32)
            marker=Path(td)/'artifacts/manual-control'/('b'*32)/'result.json'
            original_marker=marker.read_bytes()
            marker.write_bytes(original_marker.replace(b'"session_event_count": 4',b'"session_event_count": 5'))
            with self.assertRaises(BrokerError):review_project_session(td,'default','b'*32)
            marker.write_bytes(original_marker)
            log=Path(td)/'artifacts/manual-control'/('b'*32)/'session.jsonl'
            log.write_bytes(log.read_bytes().replace(b'INPUT_DEADLINE_EXPIRED',b'INPUT_DEADLINE_EXPIREX'))
            with self.assertRaises(BrokerError):review_project_session(td,'default','b'*32)

    def test_project_index_failure_never_rewrites_global_journal(self):
        with tempfile.TemporaryDirectory() as td:
            out,_=history_fixture(td)
            original=(out/'session.jsonl').read_bytes()
            with self.assertRaises(BrokerError):index_project_session(td,'default','a'*32)
            self.assertEqual((out/'session.jsonl').read_bytes(),original)

    def test_navigation_journal_keeps_raw_frame_age_and_no_motion_authority(self):
        from twinpulse_core.ros_observations import RosObservations
        from packages.twinpulse_core.tests.test_ros_observations import message
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td)
            obs=RosObservations();obs.receive('odom',message(),10**10,10.,1)
            obs.receive('scan',message('scan'),10**10,10.,1)
            event=rows[1]['data']['event'];event['kind']='navigation';event['data']={'snapshot':obs.snapshot(10.1)}
            log=out/'session.jsonl';log.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            view=review_session(td,'a'*32);snapshot=view['navigation_observations'][0]
            self.assertEqual(snapshot['scan']['frame_id'],'base_scan');self.assertEqual(snapshot['scan']['ranges_m'],[1.]*72)
            self.assertFalse(view['floor_pose_measured']);self.assertFalse(snapshot['motion_authorized'])
            self.assertIsNone(view['commands'][0]['next_observation'])
            event['data']['snapshot']['alignment_verified']=True
            log.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            with self.assertRaises(BrokerError):review_session(td,'a'*32)

    def test_navigation_journal_preserves_rejection_code_without_pose(self):
        from twinpulse_core.ros_observations import RosObservations
        from packages.twinpulse_core.tests.test_ros_observations import message
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td)
            obs=RosObservations();bad=message();bad.pose.pose.orientation.w=.5
            obs.receive('odom',bad,10**10,10.,1)
            event=rows[1]['data']['event'];event['kind']='navigation'
            event['data']={'snapshot':obs.snapshot(10.1)}
            (out/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            view=review_session(td,'a'*32);snapshot=view['navigation_observations'][0]
            self.assertEqual(snapshot['faults']['odom'],'ODOM_ORIENTATION')
            self.assertIsNone(snapshot['odom'])
            self.assertFalse(view['floor_pose_measured'])
            self.assertFalse(snapshot['motion_authorized'])

    def test_list_and_command_display_budgets(self):
        with tempfile.TemporaryDirectory() as td:
            for n in range(23):history_fixture(td,format(n,'032x'))
            self.assertEqual(len(list_sessions(td)['sessions']),20)
            out,rows=history_fixture(td,'f'*32)
            published=rows[0]
            values=[]
            import copy
            for n in range(205):
                row=copy.deepcopy(published);row['event_index']=n+1;row['t']+=n
                event=row['data']['event'];event['event_index']=n+1;event['t']+=n;event['data']['sequence']=n+1
                values.append(row)
            (out/'session.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in values),encoding='utf-8')
            view=review_session(td,'f'*32)
            self.assertEqual(view['published_count'],205);self.assertEqual(len(view['commands']),200)
            self.assertEqual(view['commands_omitted'],5);self.assertIsNone(view['recorded_end'])
            self.assertEqual(view['record_status'],'INCOMPLETE_RECORD')

    def test_restart_reads_history_without_factory_or_authority_and_preserves_clocks(self):
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td);original=(out/'session.jsonl').read_bytes()
            calls=[];p=PhysicalController(td,factory=lambda *a,**k:calls.append(a),command=lambda *_:['fake'])
            self.assertEqual(list_sessions(p.root)['sessions'][0]['job_id'],'a'*32)
            view=review_session(p.root,'a'*32)
            self.assertEqual(view['record_status'],'COMPLETE_RECORD')
            self.assertEqual(view['recorded_end']['status'],'FAILED')
            self.assertIsNone(view['physical_success']);self.assertFalse(view['motion_authorized'])
            self.assertEqual(view['commands'][0]['robot_t'],10.)
            self.assertEqual(view['commands'][0]['next_observation']['encoders'],[5,6])
            self.assertFalse(calls);self.assertEqual(p.snapshot('x')['state'],'NOT_STARTED')
            self.assertEqual((out/'session.jsonl').read_bytes(),original)

    def test_partial_tail_and_missing_marker_do_not_invent_complete(self):
        with tempfile.TemporaryDirectory() as td:
            out,_=history_fixture(td)
            with (out/'session.jsonl').open('ab') as stream:stream.write(b'{"unfinished":')
            original=(out/'session.jsonl').read_bytes();view=review_session(td,'a'*32)
            self.assertEqual(view['record_status'],'INCOMPLETE_RECORD');self.assertTrue(view['partial_tail_excluded'])
            self.assertEqual(view['event_count'],3);self.assertEqual((out/'session.jsonl').read_bytes(),original)
            (out/'result.json').unlink()
            self.assertEqual(review_session(td,'a'*32)['record_status'],'INCOMPLETE_RECORD')

    def test_invalid_shapes_clock_provenance_and_interior_corruption_reject_without_raw_echo(self):
        import copy
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td)
            variants=[]
            for field,value in [('job_id','b'*32),('event_index',7),('clock_domain','robot_monotonic'),('t',float('nan')),('real_transport',True),('secret','do-not-echo')]:
                bad=copy.deepcopy(rows);bad[1][field]=value;variants.append(bad)
            bad=copy.deepcopy(rows);bad[1]['data']['event']['robot_session_id']='another';variants.append(bad)
            bad=copy.deepcopy(rows);bad[1]['data']['event']['t']=9.;variants.append(bad)
            for values in variants:
                (out/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in values),encoding='utf-8')
                with self.assertRaises(BrokerError) as error:review_session(td,'a'*32)
                self.assertNotIn('do-not-echo',str(error.exception))
            for raw in (b'{broken}\n',b'{"schema":1,"schema":2}\n',b'x'*(8*1024*1024+1)):
                (out/'session.jsonl').write_bytes(raw)
                with self.assertRaises(BrokerError):review_session(td,'a'*32)

    def test_absent_following_observation_stays_unknown_and_ids_are_not_paths(self):
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td);rows[1]['data']['event']['t']=11.;rows[1]['data']['event']['data']['sample']['t']=10.9
            (out/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            self.assertIsNone(review_session(td,'a'*32)['commands'][0]['next_observation'])
            for job in ('../other','a'*32+'/result.json','A'*32,'',None):
                with self.assertRaises(BrokerError):review_session(td,job)


class OperationIdJournalTests(unittest.TestCase):
    def test_new_pc_operation_ids_reopen_and_legacy_rows_remain_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            job='e'*32
            out=Path(td)/'artifacts/manual-control'/job
            out.mkdir(parents=True)
            def row(index,kind,data):
                return {'schema':'control-session-1.0','job_id':job,'event_index':index,
                        'clock_domain':'pc_monotonic','t':float(index),'kind':kind,
                        'real_transport':False,'data':data}
            rows=[row(1,'pc_session_started',{'mode':'control'}),
                  row(2,'input_received',{'sequence':1,'action':'forward','operation_id':'forward_motion'}),
                  row(3,'pipe_written',{'sequence':1,'action':'forward','source_age_ms':10.,
                                        'operation_id':'forward_motion'})]
            def save():
                (out/'session.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in rows),encoding='utf-8')
            save()
            view=review_session(td,job)
            self.assertEqual([item['operation_id'] for item in view['timeline']],[None,'forward_motion','forward_motion'])
            self.assertEqual(view['timeline'][2]['operation_id_basis'],'RECORDED_PC')
            rows[2]['data']['operation_id']='left_turn';save()
            with self.assertRaises(BrokerError):review_session(td,job)
            rows[2]['data'].pop('operation_id');rows[1]['data'].pop('operation_id');save()
            legacy=review_session(td,job)
            self.assertIsNone(legacy['timeline'][2]['operation_id'])
            self.assertEqual(legacy['timeline'][2]['operation_id_basis'],'NOT_RECORDED')

    def test_robot_publish_is_correlated_by_sequence_without_rewriting_raw_event(self):
        with tempfile.TemporaryDirectory() as td:
            job='e'*32
            out,rows=history_fixture(td,job)
            original_event=json.dumps(rows[0]['data']['event'],sort_keys=True)
            rows.insert(0,{**rows[0],'t':999.,'kind':'input_received',
                           'data':{'sequence':2,'action':'forward','operation_id':'forward_motion'}})
            for index,row in enumerate(rows,1):row['event_index']=index
            (out/'session.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in rows),encoding='utf-8')
            (out/'result.json').write_text(json.dumps({'session_log_complete':True,
                'session_event_count':len(rows),'real_transport':False}),encoding='utf-8')
            view=review_session(td,job)
            self.assertEqual(view['timeline'][1]['operation_id'],'forward_motion')
            self.assertEqual(view['timeline'][1]['operation_id_basis'],'SEQUENCE_AND_ACTION_CORRELATED_PC')
            self.assertIsNone(view['timeline'][2]['operation_id'])
            self.assertEqual(view['commands'][0]['operation_id'],'forward_motion')
            self.assertEqual(json.dumps(rows[1]['data']['event'],sort_keys=True),original_event)
            rows[1]['data']['event']['data']['action']='left'
            (out/'session.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in rows),encoding='utf-8')
            self.assertIsNone(review_session(td,job)['commands'][0]['operation_id'])
            rows[1]['data']['event']['data']['action']='forward'
            rows[0]['data'].pop('operation_id')
            (out/'session.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in rows),encoding='utf-8')
            self.assertIsNone(review_session(td,job)['commands'][0]['operation_id'])
            rows[0]['data']['operation_id']='forward_motion'
            late=rows.pop(0);late['t']=1003.;rows.append(late)
            for index,row in enumerate(rows,1):row['event_index']=index
            (out/'session.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in rows),encoding='utf-8')
            self.assertIsNone(review_session(td,job)['commands'][0]['operation_id'])


class JournalTests(unittest.TestCase):
    def test_explicit_byte_budget_never_claims_a_missing_event_saved(self):
        with tempfile.TemporaryDirectory() as td:
            journal=SessionJournal(Path(td)/'small.jsonl',max_bytes=10)
            journal.start()
            self.assertFalse(journal.append({'data':'too large'}))
            self.assertFalse(journal.close())
            self.assertEqual(journal.status()['error'],'JOURNAL_BYTE_BUDGET')

    def test_bounded_queue_rejects_without_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            sink=SessionJournal(Path(td)/'session.jsonl',capacity=1)
            self.assertTrue(sink.append({'n':1}))
            start=time.monotonic();self.assertFalse(sink.append({'n':2}))
            self.assertLess(time.monotonic()-start,.1)
            self.assertEqual(sink.status()['error'],'JOURNAL_QUEUE_FULL')
            self.assertFalse(sink.close())

    def test_stalled_fsync_does_not_block_status_and_is_not_complete(self):
        with tempfile.TemporaryDirectory() as td:
            gate=threading.Event();entered=threading.Event()
            def stall(_):entered.set();gate.wait(3)
            sink=SessionJournal(Path(td)/'session.jsonl',sync=stall)
            sink.start();sink.append({'n':1})
            try:
                self.assertTrue(entered.wait(1))
                with sink.lock:sink.pending_since=time.monotonic()-1.1
                start=time.monotonic();status=sink.status()
                self.assertLess(time.monotonic()-start,.1)
                self.assertEqual(status['error'],'JOURNAL_SAVE_STALLED');self.assertEqual(status['saved'],0)
            finally:gate.set();self.assertFalse(sink.close())

    def test_prefix_survives_process_exit_without_finally(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            result=subprocess.run([sys.executable,str(ROOT/'tests/fixtures/journal_crash.py'),td],
                                  capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            rows=[json.loads(line) for line in (Path(td)/'session.jsonl').read_text().splitlines()]
            self.assertEqual(rows,[{'n':n} for n in range(12)])
            self.assertFalse((Path(td)/'result.json').exists())


class TransportTests(unittest.TestCase):
    def test_display_scan_contract_is_projected_with_receipt_age_and_owner_boundary(self):
        from twinpulse_core.ros_observations import scan_preview
        from packages.twinpulse_core.tests.test_ros_observations import message
        c=Clock();c.t=20.
        preview=scan_preview(message('scan'),10**10,20.)
        event={'schema':'robot-session-1.0','robot_session_id':'manual-test','event_index':1,
            'clock_domain':'robot_monotonic','t':20.,'kind':'scan_preview','data':{'scan':preview}}
        self.assertTrue(valid_event(event))
        self.assertFalse(valid_event({**event,'data':{'scan':{**preview,'display_only':False}}}))
        p=PhysicalController(ROOT,clock=c,command=lambda *_:['fake'])
        p.owner='owner';p._record('robot_event',event=event);c.t=22.
        result=p.snapshot('owner')['scan_preview']
        self.assertEqual(result['receipt_age_s'],2.)
        self.assertFalse(result['transport_delay_measured'])
        self.assertIsNone(p.snapshot('other')['scan_preview'])
        p.close()

    def test_lidar_finish_projects_sensor_cleanup_without_claiming_rotor_stop(self):
        from types import SimpleNamespace as NS
        report={'status':'LIDAR_DATA_QUIET','cleanup_confirmed':True,'operator_cancelled':True,
            'stop_attempts':[{'write_complete':True}], 'data_quiet_after_stop':True,
            'port_restored':True,'physical_rotor_stopped':'UNCONFIRMED'}
        class Child(FakeChild):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                lines=iter([(json.dumps({'state':'FINISHED','report':report})+'\n').encode(),b''])
                self.stdout=NS(readline=lambda _:next(lines,b''))
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=Child,command=lambda *_:['fake'])
            try:
                p.start('owner','lidar','e'*32,True);p.thread.join(3)
                view=p.snapshot('owner')
                self.assertFalse(view['busy'])
                self.assertEqual(view['lidar_result'],{'operator_cancelled':True,
                    'data_quiet_after_stop':True,'port_restored':True,'stop_write_complete':True,
                    'physical_rotor_stopped':False})
                self.assertFalse(view['physical_verified'])
            finally:p.close()

    def test_preparing_watch_maintains_pc_heartbeat_without_pipe_motion(self):
        class PreparingOutput(FakeOutput):
            def readline(self, _limit):
                if self.child.done.wait(.025): return b''
                return b'{"state":"PREPARING","mode":"qualify_scan"}\n'
        class PreparingChild(FakeChild):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.stdout = PreparingOutput(self)
        with tempfile.TemporaryDirectory() as td:
            controller = PhysicalController(td, factory=PreparingChild, command=lambda *_: ['fake'])
            job = 'e' * 32
            try:
                controller.start('operator', 'qualify_scan', job, True)
                deadline = time.monotonic() + 2
                while controller.snapshot('operator')['state'] != 'PREPARING' and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(controller.snapshot('operator')['state'], 'PREPARING')
                controller.input('operator', job, 1, 'watch', time.time() * 1000 + 200)
                self.assertFalse(controller.child.stdin.sent)
            finally:
                controller.close()

    def _assert_direction_reaches_owned_pipe(self, action, mode='control'):
        with tempfile.TemporaryDirectory() as td:
            controller = PhysicalController(td, factory=FakeChild, command=lambda *_: ['fake'])
            job = 'd' * 32
            try:
                controller.start('operator', mode, job, True)
                deadline = time.monotonic() + 2
                while controller.snapshot('operator')['state'] != 'READY' and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(controller.snapshot('operator')['state'], 'READY')
                controller.input('operator', job, 1, action, time.time() * 1000 + 250)
                while not controller.child.stdin.sent and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertEqual(controller.child.stdin.sent[0]['action'], action)
                self.assertEqual(controller.child.stdin.sent[0]['sequence'], 1)
            finally:
                controller.close()
            rows=[json.loads(line) for line in (Path(td)/'artifacts/manual-control'/job/'session.jsonl').read_text().splitlines()]
            for kind in ('input_received','pipe_written'):
                matching=[row['data'] for row in rows if row['kind']==kind and row['data']['action']==action]
                self.assertEqual(len(matching),1)
                self.assertEqual(matching[0]['operation_id'],operation_for_action(action))

    def test_forward_command_reaches_owned_pipe(self):
        self._assert_direction_reaches_owned_pipe('forward')

    def test_combined_manual_scan_mode_keeps_direction_in_the_same_owned_pipe(self):
        self._assert_direction_reaches_owned_pipe('forward', mode='control_scan')

    def test_reverse_command_reaches_owned_pipe(self):
        self._assert_direction_reaches_owned_pipe('backward')

    def test_left_turn_reaches_owned_pipe(self):
        self._assert_direction_reaches_owned_pipe('left')

    def test_right_turn_reaches_owned_pipe(self):
        self._assert_direction_reaches_owned_pipe('right')

    def test_force_supersedes_queued_finish_without_resetting_deadline_or_downgrading(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,command=lambda *_:['fake'])
            p.mode='control';p.sequence=8;p.state={'state':'READY'}
            p.pending_input=(7,'forward',1.);p.writes.put_nowait(b'old-motion')
            p._cancel(operator=True,action='finish_stop');started=p.stop_at
            self.assertEqual(p.state['stop_request'],'finish_stop')
            p.sequence=9;p._cancel(operator=True,action='force_stop')
            self.assertEqual(json.loads(p.writes.get_nowait())['action'],'force_stop')
            self.assertTrue(p.writes.empty());self.assertIsNone(p.pending_input)
            self.assertEqual(p.stop_at,started)
            p._cancel(operator=True,action='finish_stop')
            self.assertEqual(p.state['stop_request'],'force_stop');self.assertTrue(p.writes.empty())
            p._cancel();self.assertIsNone(p.writes.get_nowait())

    def test_close_packet_replaces_queued_motion_and_failure_can_escalate_to_eof(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,command=lambda *_:['fake'])
            p.mode='control';p.sequence=8;p.state={'state':'READY'}
            p.pending_input=(7,'forward',1.)
            p.writes.put_nowait(b'old-motion');p._cancel(operator=True)
            packet=json.loads(p.writes.get_nowait())
            self.assertEqual(packet,{'sequence':8,'action':'close','challenge':None,'age_ms':0})
            self.assertTrue(p.close_pending);self.assertIsNone(p.pending_input)
            started=p.stop_at
            p._cancel(operator=True);self.assertTrue(p.writes.empty())
            p._cancel()
            self.assertIsNone(p.writes.get_nowait());self.assertFalse(p.close_pending)
            self.assertEqual(p.stop_at,started)

    def test_explicit_close_keeps_input_open_but_never_claims_unreceived_result(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            try:
                p.start('x','control','c'*32,True)
                end=time.monotonic()+2
                while p.snapshot('x')['state']!='READY' and time.monotonic()<end:time.sleep(.01)
                p.input('x','c'*32,1,'close',0)
                time.sleep(.65)  # Ordinary missing-input monitor must not preempt close delivery.
                self.assertEqual(p.child.stdin.sent[-1]['action'],'close')
                self.assertFalse(p.child.stdin.closed)
                self.assertEqual(p.snapshot('x')['state'],'STOPPING')
                self.assertFalse(p.snapshot('x').get('cleanup_confirmed',False))
                with self.assertRaises(BrokerError):p.input('x','c'*32,2,'forward',time.time()*1000+250)
            finally:p.close()
            self.assertTrue(p.child.stdin.closed)
            self.assertNotEqual(p.snapshot('x').get('result'),'OPERATOR_STOP')

    def test_journal_is_saved_before_session_exit_and_snapshot_is_evidence_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            try:
                p.start('owner','control','b'*32,True)
                end=time.monotonic()+2
                while p.snapshot('owner')['state']!='READY' and time.monotonic()<end:time.sleep(.005)
                p.input('owner','b'*32,1,'watch',time.time()*1000+250)
                end=time.monotonic()+.3
                while p.snapshot('owner')['session_storage']['saved']<3 and time.monotonic()<end:time.sleep(.005)
                view=p.snapshot('owner')
                self.assertTrue(view['busy']);self.assertGreaterEqual(view['session_storage']['saved'],3)
                rows=[json.loads(s) for s in (Path(td)/'artifacts/manual-control'/('b'*32)/'session.jsonl').read_text().splitlines()]
                self.assertEqual([r['event_index'] for r in rows],list(range(1,len(rows)+1)))
                self.assertEqual(view['session_evidence']['pc_received'],1)
                self.assertEqual(view['session_evidence']['robot_published'],0)
                self.assertIsNone(view['session_evidence']['physical_success'])
            finally:p.close()

    def test_existing_job_directory_is_not_overwritten_or_connected(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'artifacts/manual-control'/('a'*32);out.mkdir(parents=True)
            (out/'session.jsonl').write_bytes(b'original\n');(out/'result.json').write_bytes(b'original result')
            calls=[];p=PhysicalController(td,factory=lambda *a,**k:calls.append(a),command=lambda *_:['fake'])
            p.start('x','control','a'*32,True);p.thread.join(2)
            self.assertEqual(calls,[]);self.assertFalse(p.snapshot('x')['session_log_complete'])
            self.assertEqual((out/'session.jsonl').read_bytes(),b'original\n')
            self.assertEqual((out/'result.json').read_bytes(),b'original result')

    def test_disk_error_requests_transport_close_and_keeps_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            def fail(_):raise OSError('disk failed')
            def sink(path,**kwargs):return SessionJournal(path,sync=fail,**kwargs)
            with patch('twinpulse_app.physical_controller.SessionJournal',side_effect=sink):
                p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
                p.start('x','control','f'*32,True);p.thread.join(3)
                self.assertFalse(p.thread.is_alive())
                view=p.snapshot('x')
                self.assertFalse(view['session_log_complete']);self.assertFalse(view['physical_verified'])
                self.assertEqual(view['session_storage']['error'],'JOURNAL_WRITE_FAILED')
                self.assertTrue(p.stop_requested)
                p.close()

    def test_journal_shape_rejects_unknown_fields_and_nonfinite_values(self):
        event={'schema':'robot-session-1.0','robot_session_id':'manual-test','event_index':1,
               'clock_domain':'robot_monotonic','t':1.,'kind':'observation',
               'data':{'guard':'explicit_stop','sample':{'t':.9,'encoders':[1,2],
                       'torque':False,'source_age_s':.01,'voltage_v':12.}}}
        self.assertTrue(valid_event(event))
        for bad in ({**event,'challenge':'never-log'}, {**event,'t':float('nan')},
                    {**event,'event_index':True},{**event,'kind':[]},
                    {**event,'data':{**event['data'],'cookie':'never-log'}},
                    {**event,'data':{'guard':'explicit_stop','sample':{**event['data']['sample'],'secret':'never-log'}}}):
            self.assertFalse(valid_event(bad))

    def test_journal_budget_closes_instead_of_claiming_complete(self):
        p=PhysicalController(ROOT,command=lambda *_:['fake'])
        p.journal=[None]*8192
        p._record('input_received',sequence=1,action='watch')
        self.assertTrue(p.journal_overflow);self.assertTrue(p.stop_requested)
        self.assertEqual(len(p.journal),8192)

    def test_persistent_journal_tail_and_full_archive_exceed_old_session_budget(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(Path(td),command=lambda *_:['fake'])
            p.mode='control';p.job='a'*32
            base=Path(td)/'artifacts/manual-control'/p.job;base.mkdir(parents=True)
            p.journal_sink=SessionJournal(base/'session.jsonl',capacity=16384,max_bytes=64*1024*1024)
            p.journal_sink.start();p._record('pc_session_started',mode='control',project_id='default')
            for n in range(10000):p._record('input_received',sequence=n+1,action='watch')
            self.assertFalse(p.stop_requested);self.assertFalse(p.journal_overflow)
            self.assertEqual(p.journal_event_count,10001)
            self.assertLess(len(p.journal),8192)
            self.assertEqual(p.journal[-1]['event_index'],10001)
            self.assertTrue(p.journal_sink.close())
            reviewed=review_session(Path(td),p.job)
            self.assertEqual(len((base/'session.jsonl').read_text().splitlines()),10001)
            self.assertIsInstance(reviewed,dict)
            self.assertEqual(reviewed['event_count'],10001)
            self.assertEqual(len(reviewed['timeline']),1000)
            self.assertEqual(reviewed['timeline_events_omitted'],9001)

    def test_saved_trial_survives_console_restart_without_authorizing_or_connecting(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'artifacts/manual-control'/('a'*32)/'robot-report.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'mode':'qualify','status':'FINAL_IDLE_UNCONFIRMED',
                'stop_assessment':{'status':'PASS'},'cleanup_confirmed':False,
                'cleanup_stage':'independent_torque_off','cleanup_error':'child exit=3'}))
            calls=[]
            p=PhysicalController(td,factory=lambda *a,**k:calls.append(a),command=lambda *_:['fake'])
            view=p.snapshot('x')
            self.assertEqual(view['state'],'NOT_STARTED');self.assertFalse(view['physical_verified'])
            self.assertEqual(view['last_trial']['stop_assessment']['status'],'PASS')
            self.assertEqual(view['last_trial']['cleanup_stage'],'independent_torque_off')
            self.assertTrue(view['last_trial']['historical']);self.assertFalse(calls)
            self.assertIsNone(p.child)

    def test_fixed_command_no_arbitrary_host_or_speed(self):
        with patch('shutil.which',return_value='ssh.exe'),patch.object(Path,'is_file',return_value=True):
            cmd=worker_command(ROOT,'control')
        self.assertEqual(cmd[-2],'twinpulse@192.168.35.139')
        self.assertEqual(cmd[-1],'exec bash /home/twinpulse/.local/share/twinpulse/robot/current/teleop.sh control')
        self.assertIn('StrictHostKeyChecking=yes',cmd)
        with self.assertRaises(ValueError):worker_command(ROOT,'control; bad')

    def test_explicit_owned_idempotent_job_and_eof_cancel(self):
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            def factory(*args,**kwargs):calls.append(1);return FakeChild()
            p=PhysicalController(td,factory=factory,command=lambda *_:['fake'])
            self.assertEqual(calls,[])
            with self.assertRaises(BrokerError):p.start('owner','control','a'*32,False)
            value=p.start('owner','control','a'*32,True)
            p.start('owner','control','a'*32,True)
            end=time.monotonic()+2
            while p.snapshot('owner')['state']!='READY' and time.monotonic()<end:time.sleep(.01)
            self.assertEqual(calls,[1])
            with self.assertRaises(BrokerError):p.input('other','a'*32,1,'forward',time.time()*1000+250)
            p.input('owner','a'*32,1,'forward',time.time()*1000+250)
            end=time.monotonic()+1
            while not p.child.stdin.sent and time.monotonic()<end:time.sleep(.005)
            p.input('owner','a'*32,2,'close',0)
            p.close()
            self.assertTrue(p.child.stdin.closed)
            self.assertEqual(p.child.stdin.sent[0]['action'],'forward')
            self.assertFalse(p.snapshot('owner').get('cleanup_confirmed',False))
            log=Path(td)/'artifacts/manual-control'/('a'*32)/'session.jsonl'
            rows=[json.loads(s) for s in log.read_text().splitlines()]
            self.assertTrue(any(r['kind']=='pipe_written' and r['data']['action']=='forward' for r in rows))
            self.assertTrue(any(r['kind']=='pipe_enqueue_requested' and r['data']['action']=='forward' for r in rows))
            self.assertTrue(all(r['data']['pipe_write_s']>=0 for r in rows if r['kind']=='pipe_written'))
            self.assertTrue(all(r['job_id']=='a'*32 and r['clock_domain']=='pc_monotonic' for r in rows))
            self.assertNotIn('challenge',log.read_text());self.assertNotIn('owner',log.read_text())

    def test_no_browser_heartbeat_pauses_manual_but_retains_owned_connection(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            try:
                p.start('x','control','c'*32,True)
                end=time.monotonic()+2
                while p.snapshot('x').get('pause_reason')!='OPERATOR_PRESENCE_EXPIRED' and time.monotonic()<end:time.sleep(.02)
                state=p.snapshot('x')
                self.assertEqual(state.get('pause_reason'),'OPERATOR_PRESENCE_EXPIRED')
                self.assertTrue(state['busy']);self.assertFalse(p.child.stdin.closed)
                self.assertIsNone(p.pending_input);self.assertFalse(p.stop_requested)
                self.assertFalse(state.get('cleanup_confirmed',False))
            finally:p.close()

    def test_release_waits_for_correlated_robot_ready_not_old_inflight_ready(self):
        class Output(FakeOutput):
            def readline(self,_):
                if self.child.done.wait(.02):return b''
                return (json.dumps({'state':'READY','challenge':'a'*24,
                                    'input_sequence':self.child.ack})+'\n').encode()
        class Child(FakeChild):
            def __init__(self,*a,**k):
                super().__init__();self.ack=0;self.stdout=Output(self)
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=Child,command=lambda *_:['fake'])
            p.start('x','control','e'*32,True)
            end=time.monotonic()+2
            while p.snapshot('x')['state']!='READY' and time.monotonic()<end:time.sleep(.01)
            p.input('x','e'*32,1,'stop',0)
            time.sleep(.1)
            self.assertEqual(p.snapshot('x')['state'],'RELEASING')
            self.assertIsNone(p.challenge)
            p.child.ack=1
            end=time.monotonic()+1
            while p.snapshot('x')['state']!='READY' and time.monotonic()<end:time.sleep(.01)
            self.assertEqual(p.snapshot('x')['state'],'READY')
            self.assertEqual(p.snapshot('x')['job_id'],'e'*32)
            p.close()


class MissionTransportTests(unittest.TestCase):
    def exercise(self,action=None):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fake=root/'fake';fake.mkdir();(fake/'fake-qualified').touch()
            p=PhysicalController(root,command=lambda _root,mode:[sys.executable,'-B',str(ROOT/'tests/fixtures/manual_robot_process.py'),mode,str(fake)])
            job='b'*32;scope={'frame_id':'odom','waypoints':[[.04,0.]],'duration_s':5.};sequence=0
            try:
                p.start('owner','mission',job,True,scope=scope)
                scope['waypoints'][0][0]=9  # Cannot change the frozen approved request.
                self.assertEqual(p.snapshot('owner')['mission_scope']['waypoints'],[[.04,0.]])
                with self.assertRaises(BrokerError):p.start('owner','mission',job,True,scope=scope)
                deadline=time.monotonic()+8;acted=False
                while p.snapshot('owner')['busy'] and time.monotonic()<deadline:
                    current=p.snapshot('owner');sequence+=1
                    if action and current['state']=='READY' and not acted:
                        if action=='lost':break
                        if action=='forward':
                            with self.assertRaises(BrokerError):p.input('owner',job,sequence,action,time.time()*1000+250)
                        else:p.input('owner',job,sequence,action,time.time()*1000+250)
                        acted=True
                    elif not acted and current['state'] not in {'FINISHED','STOPPING'}:
                        try:p.input('owner',job,sequence,'watch',time.time()*1000+250)
                        except BrokerError:
                            if p.snapshot('owner')['state'] not in {'FINISHED','STOPPING'}:raise
                    time.sleep(.05)
                if action=='lost':
                    while p.snapshot('owner')['busy'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertFalse(p.snapshot('owner')['busy'])
                final=p.snapshot('owner')
                if not action:self.assertEqual(final.get('result'),'MISSION_ARRIVED',final)
                review=review_session(root,job)
                self.assertEqual(len(review['mission_scopes']),1);self.assertEqual(len(review['mission_requests']),1)
                self.assertEqual(review['mission_scopes'][0]['scope']['waypoints'],[[.04,0.]])
                self.assertFalse(review['motion_authorized']);self.assertIsNone(review['physical_success'])
                rows=[json.loads(line) for line in (root/'artifacts/manual-control'/job/'session.jsonl').read_text().splitlines()]
                robot=[r['data']['event'] for r in rows if r['kind']=='robot_event']
                self.assertTrue(all(r['data']['action'] in {'watch','close'} for r in robot if r['kind']=='accepted'))
                self.assertNotIn('nonce',json.dumps(rows));self.assertNotIn('challenge',json.dumps(rows))
                if not action:
                    self.assertEqual(final['result'],'MISSION_ARRIVED',final);self.assertGreater(review['published_count'],5)
                    self.assertEqual(review['mission_requests'][0]['request_sha256'],next(r['data']['request_sha256'] for r in robot if r['kind']=='mission_started'))
                    self.assertEqual(len(list(fake.glob('consumed-*'))),1)
                elif action=='close':self.assertEqual(final['result'],'MISSION_CANCELLED')
                else:self.assertEqual(final['result'],'FAILED')
            finally:p.close()

    def test_app_transport_bootstrap_loop_and_archive_with_one_consent(self):self.exercise()
    def test_explicit_cancel_is_not_arrival(self):self.exercise('close')
    def test_direction_injection_cancels_not_manual_override(self):self.exercise('forward')
    def test_lost_browser_heartbeat_cannot_continue(self):self.exercise('lost')


class PhysicalHttpTests(unittest.TestCase):
    request=test_r5_product_api.R5ProductApiTests.request
    setUp=test_r5_product_api.R5ProductApiTests.setUp
    tearDown=test_r5_product_api.R5ProductApiTests.tearDown

    def test_http_prepare_mode_reaches_only_owned_fake_prepare(self):
        # The production App route owns the existing prepare operation. This
        # fixture does not package, deploy, connect to, or qualify a real robot.
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        with tempfile.TemporaryDirectory() as td:
            calls=[]
            class FinishedPrepare(FakeChild):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,**kwargs)
                    self.done.set()
            def command(_root,mode):
                calls.append(mode)
                return ['fake-prepare']
            controller=PhysicalController(td,factory=FinishedPrepare,command=command)
            self.server.physical_controller=controller
            try:
                body={'mode':'prepare','request_id':'a'*32,'confirmed':True,
                      'expires_at_ms':time.time()*1000+1500}
                self.assertEqual(self.request('/v1/product/robot/physical/start',body)[0],401)
                self.assertEqual(self.request('/v1/product/robot/physical/start',body,
                                              headers={'Cookie':self.cookie})[0],403)
                status,_,_=self.request('/v1/product/robot/physical/start',body,headers=headers)
                self.assertEqual(status,202)
                deadline=time.monotonic()+2
                while controller.thread.is_alive() and time.monotonic()<deadline:time.sleep(.01)
                result=controller.snapshot('unowned-test-observer')
                self.assertEqual(result['state'],'FINISHED')
                self.assertEqual(result['result'],'PREPARED')
                self.assertFalse(result['physical_verified'])
                self.assertEqual(calls,['prepare'])
                self.assertEqual(controller.child.stdin.sent,[])
            finally:
                controller.close()

    def _assert_input_route_reaches_fake_owned_pipe(self, action, operation_id):
        # Actual App HTTP/auth/controller route, but a local fake child, never SSH.
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        with tempfile.TemporaryDirectory() as td:
            controller=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            self.server.physical_controller=controller
            job='f'*32
            try:
                start={'mode':'control','request_id':job,'confirmed':True,
                       'expires_at_ms':time.time()*1000+1500}
                self.assertEqual(self.request('/v1/product/robot/physical/start',start,headers=headers)[0],202)
                deadline=time.monotonic()+2
                while controller.snapshot('unowned-test-observer')['state']!='READY' and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertEqual(controller.snapshot('unowned-test-observer')['state'],'READY')
                body={'job_id':job,'sequence':1,'action':action,
                      'expires_at_ms':0 if action in {'finish_stop','force_stop'} else time.time()*1000+200}
                status,response,_=self.request('/v1/product/robot/physical/input',body,headers=headers)
                self.assertEqual(status,200,response)
                while (not controller.child.stdin.sent or
                       controller.child.stdin.sent[0]['action']!=action) and time.monotonic()<deadline:
                    time.sleep(.005)
                self.assertEqual(controller.child.stdin.sent[0]['action'],action)
            finally:
                controller.close()
            rows=[json.loads(line) for line in
                  (Path(td)/'artifacts/manual-control'/job/'session.jsonl').read_text().splitlines()]
            received=[row for row in rows if row['kind']=='input_received' and
                      row['data'].get('action')==action]
            self.assertEqual(len(received),1)
            self.assertEqual(received[0]['data']['operation_id'],operation_id)

    def test_http_forward_input_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('forward','forward_motion')

    def test_http_reverse_input_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('backward','reverse_motion')

    def test_http_left_input_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('left','left_turn')

    def test_http_right_input_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('right','right_turn')

    def test_http_graceful_stop_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('finish_stop','graceful_stop')

    def test_http_force_stop_reaches_fake_owned_pipe(self):
        self._assert_input_route_reaches_fake_owned_pipe('force_stop','force_stop')

    def test_api_freezes_current_app_context_without_physical_authority(self):
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        with tempfile.TemporaryDirectory() as td:
            controller=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            self.server.physical_controller=controller
            job='d'*32
            body={'mode':'control','request_id':job,'confirmed':True,
                  'expires_at_ms':time.time()*1000+1500}
            with patch.object(self.server.product_workflow,'snapshot',return_value={'site_draft':{
                    'revision':'a'*64,'robot_profile_id':'turtlebot3_burger'}}):
                self.assertEqual(self.request('/v1/product/robot/physical/start',body,headers=headers)[0],202)
            controller.close()
            review=review_project_session(td,'default',job)
            self.assertEqual(review['comparison_evidence']['app_scene_revision'],'a'*64)
            self.assertEqual(review['comparison_evidence']['app_robot_profile_id'],'turtlebot3_burger')
            self.assertEqual(review['comparison_evidence']['app_context_capture'],'CAPTURED')
            self.assertEqual(review['comparison_evidence']['room_odom_alignment'],'UNVERIFIED')
            self.assertFalse(review['motion_authorized'])

    def test_app_snapshot_failure_is_recorded_unknown_without_new_motion_gate(self):
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        with tempfile.TemporaryDirectory() as td:
            controller=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            self.server.physical_controller=controller
            job='e'*32
            body={'mode':'control','request_id':job,'confirmed':True,
                  'expires_at_ms':time.time()*1000+1500}
            with patch.object(self.server.product_workflow,'snapshot',side_effect=ValueError('invalid app state')):
                self.assertEqual(self.request('/v1/product/robot/physical/start',body,headers=headers)[0],202)
            controller.close()
            evidence=review_project_session(td,'default',job)['comparison_evidence']
            self.assertEqual(evidence['app_context_capture'],'UNAVAILABLE')
            self.assertIsNone(evidence['app_scene_revision'])
            self.assertIsNone(evidence['app_robot_profile_id'])

    def test_runtime_error_does_not_block_owned_force_stop_fake_transport(self):
        headers = {'Cookie': self.cookie, 'X-TwinPulse-CSRF': self.csrf}
        with tempfile.TemporaryDirectory() as td:
            controller = PhysicalController(td, factory=FakeChild, command=lambda *_: ['fake'])
            self.server.physical_controller = controller
            job = 'e' * 32
            start = {'mode': 'control', 'request_id': job, 'confirmed': True,
                     'expires_at_ms': time.time() * 1000 + 1500}
            self.assertEqual(self.request('/v1/product/robot/physical/start', start, headers=headers)[0], 202)
            end = time.monotonic() + 2
            while controller.snapshot('unowned-test-observer')['state'] != 'READY' and time.monotonic() < end:
                time.sleep(.01)
            state = json.loads(self.supervisor_status.read_text(encoding='utf-8'))
            state['status'] = 'error'
            self.supervisor_status.write_text(json.dumps(state), encoding='utf-8')
            before = {'job_id': job, 'sequence': 1, 'action': 'forward',
                      'expires_at_ms': time.time() * 1000 + 200}
            self.assertEqual(self.request('/v1/product/robot/physical/input', before, headers=headers)[0], 409)
            stop = {**before, 'action': 'force_stop', 'expires_at_ms': 0}
            self.assertEqual(self.request('/v1/product/robot/physical/input', stop,
                                          headers={'Cookie': self.cookie})[0], 403)
            self.assertEqual(self.request('/v1/product/robot/physical/input', stop, headers=headers)[0], 200)
            end = time.monotonic() + 2
            while not controller.child.stdin.sent and time.monotonic() < end:
                time.sleep(.01)
            self.assertEqual(controller.child.stdin.sent[-1]['action'], 'force_stop')
            controller.close()

    def test_mission_requires_exact_scope_auth_and_cannot_enable_live_transport(self):
        path='/v1/product/robot/physical/mission'
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        body={'request_id':'a'*32,'confirmed':True,'expires_at_ms':time.time()*1000+1500,
              'scope':{'frame_id':'odom','waypoints':[[.04,0.]],'duration_s':5.}}
        with tempfile.TemporaryDirectory() as td:
            # Default fixed command stays locked even if a process factory is replaced.
            calls=[];p=PhysicalController(td,factory=lambda *a,**k:calls.append(a))
            self.server.physical_controller=p
            self.assertEqual(self.request(path,body)[0],401)
            self.assertEqual(self.request(path,body,headers={'Cookie':self.cookie})[0],403)
            self.assertEqual(self.request(path,{**body,'enabled':True},headers=headers)[0],400)
            self.assertEqual(self.request(path,body,headers=headers)[0],409)
            self.assertFalse(p.snapshot('x')['mission_readiness']['start_available']);self.assertEqual(calls,[])


    def test_history_auth_read_only_and_no_transport_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            history_fixture(td);calls=[]
            self.server.physical_controller=PhysicalController(td,factory=lambda *a,**k:calls.append(a),command=lambda *_:['fake'])
            path='/v1/product/robot/physical/history';headers={'Cookie':self.cookie}
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,headers=headers)[1]['sessions'][0]['job_id'],'a'*32)
            self.assertEqual(self.request(path+'/'+'a'*32,headers=headers)[1]['record_status'],'COMPLETE_RECORD')
            self.assertEqual(self.request(path+'/bad',headers=headers)[0],409)
            self.assertEqual(self.request(path+'/../result.json',headers=headers)[0],409)
            self.assertEqual(calls,[])

    def test_project_history_api_is_read_only_and_requires_project_binding(self):
        with tempfile.TemporaryDirectory() as td:
            out,rows=history_fixture(td)
            rows.insert(0,{**rows[0],'event_index':1,'t':999.,'kind':'pc_session_started',
                           'data':{'mode':'control','project_id':'default'}})
            for n,row in enumerate(rows,1):row['event_index']=n
            (out/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            index_project_session(td,'default','a'*32)
            calls=[];self.server.session_history_root=Path(td)
            self.server.physical_controller=PhysicalController(td,factory=lambda *a,**k:calls.append(a),command=lambda *_:['fake'])
            path='/v1/product/sessions';headers={'Cookie':self.cookie}
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,headers=headers)[1]['sessions'][0]['job_id'],'a'*32)
            self.assertEqual(self.request(path+'/'+'a'*32,headers=headers)[1]['project_id'],'default')
            self.assertEqual(self.request(path+'/bad',headers=headers)[0],409)
            self.assertEqual(calls,[])

    def test_auth_csrf_no_transport_on_get_and_explicit_confirmation(self):
        path='/v1/product/robot/physical'
        headers={'Cookie':self.cookie,'X-TwinPulse-CSRF':self.csrf,'Origin':self.server.base_url}
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            self.server.physical_controller=p
            self.assertEqual(self.request(path)[0],401)
            self.assertEqual(self.request(path,headers=headers)[1]['state'],'NOT_STARTED')
            self.assertIsNone(p.child)
            body={'mode':'control','request_id':'d'*32,'confirmed':True,'expires_at_ms':time.time()*1000+1500}
            self.assertEqual(self.request(path+'/start',body,headers={'Cookie':self.cookie})[0],403)
            self.assertEqual(self.request(path+'/start',{**body,'confirmed':False},headers=headers)[0],400)
            self.assertEqual(self.request(path+'/start',{**body,'speed':100},headers=headers)[0],400)
            self.assertEqual(self.request(path+'/start',{**body,'expires_at_ms':0},headers=headers)[0],409)
            self.assertEqual(self.request(path+'/start',body,headers=headers)[0],202)
            p.close()

    def test_expired_input_stops_and_cannot_revive(self):
        with tempfile.TemporaryDirectory() as td:
            p=PhysicalController(td,factory=FakeChild,command=lambda *_:['fake'])
            p.start('x','control','b'*32,True)
            time.sleep(.06)
            with self.assertRaises(BrokerError):p.input('x','b'*32,1,'forward',0)
            with self.assertRaises(BrokerError):p.input('x','b'*32,2,'forward',time.time()*1000+250)
            p.close()


if __name__=='__main__':unittest.main()
