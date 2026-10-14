# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Production mission/RosLink functions with artificial observations only."""
from collections import deque
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_app/src'))
from mission_runtime import load_request, run_mission
from teleop_ros import RosLink
from twinpulse_core.navigation_binding import PlanarBinding
from twinpulse_core.ros_observations import RosObservations
from tests.integration import test_r5_product_api  # Existing local package-path bootstrap.
from twinpulse_app.physical_controller import valid_event
from packages.twinpulse_core.tests.test_ros_observations import message


class MissionTests(unittest.TestCase):
    def test_bootstrap_one_scope_robot_clock_and_context_not_pc_clock(self):
        from mission_runtime import receive_request
        from twinpulse_core.mission_contract import bootstrap_packet,document_hash
        with tempfile.TemporaryDirectory() as td:
            release,_,manifest,_=self.fixture(td);packets=[]
            def output(context):
                packets.append(bootstrap_packet(context,'d'*32,{'frame_id':'odom','waypoints':[[.04,0.]],'duration_s':5.}))
            value=receive_request(release,manifest,'test-boot',NS(receive=lambda:packets.pop()),output,clock=lambda:20.)
            self.assertEqual(value['created_s'],20.);self.assertEqual(value['expires_s'],110.)
            self.assertEqual(value['waypoints'],((.04,0.),));self.assertEqual(value['mission_id'],'d'*32)
            self.assertEqual(len(list(release.iterdir())),1)

    def test_bootstrap_cancel_stale_nonce_expired_or_changed_context_rejected(self):
        from mission_runtime import receive_request
        from twinpulse_core.mission_contract import bootstrap_packet
        for fault in ('cancel','nonce','boot','expiry','frame','no_input'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as td:
                release,_,manifest,_=self.fixture(td);now=[20.];packets=[]
                def output(context):
                    packet=bootstrap_packet(context,'d'*32,{'frame_id':'odom','waypoints':[[.04,0.]],'duration_s':5.})
                    if fault=='cancel':packet={'action':'close'}
                    if fault=='nonce':packet['nonce']='0'*24
                    if fault=='boot':packet['request']['boot_id']='other'
                    if fault=='expiry':now[0]=22.
                    if fault=='frame':packet['request']['frame_id']='photo'
                    if fault!='no_input':packets.append(packet)
                def sleep(_):now[0]+=.5
                with self.assertRaises(ValueError):receive_request(release,manifest,'test-boot',
                    NS(receive=lambda:packets.pop() if packets else None),output,clock=lambda:now[0],sleep=sleep)

    def test_scope_is_copied_bounded_and_cannot_promote_photo_coordinates(self):
        from twinpulse_core.mission_contract import scope_document
        scope={'frame_id':'odom','waypoints':[[.04,0.]],'duration_s':5.}
        saved=scope_document(scope);scope['waypoints'][0][0]=2
        self.assertEqual(saved['waypoints'],[[.04,0.]])
        for bad in ({'frame_id':'photo'},{'duration_s':True},{'duration_s':46},{'waypoints':[]},
                    {'waypoints':[[float('nan'),0.]]},{'waypoints':[[0,0]]*17},{'authorized':True}):
            with self.assertRaises(ValueError):scope_document({**saved,**bad})

    def fixture(self, folder):
        release=Path(folder)/'release';release.mkdir();state=Path(folder)/'state';state.mkdir()
        calibration={'schema':'planar-calibration-1.0','basis':'reviewed_robot_frames',
            'odom_child_frame':'base_footprint','scan_frame':'base_scan','child_to_base':[0.,0.,0.],
            'base_to_scan':[.1,0.,0.],'footprint_radius_m':.18,'evidence_sha256':'a'*64,
            'guard_sha256':'b'*64,'namespace':'/tp_guard_stationary'}
        raw=json.dumps(calibration).encode();(release/'navigation-calibration.json').write_bytes(raw)
        digest=hashlib.sha256(raw).hexdigest()
        request={'schema':'robot-mission-request-1.0','mission_id':'a'*32,'boot_id':'test-boot',
            'release_id':'c'*64,'calibration_sha256':digest,'created_s':20.,'expires_s':70.,
            'duration_s':5.,'waypoints':[[.08,0.]]}
        (state/'mission-request.json').write_text(json.dumps(request))
        manifest={'source_id':'c'*64,'files':{'navigation-calibration.json':digest,'bin/turtlebot3_ros':'b'*64}}
        return release,state,manifest,request

    def test_loader_exact_release_boot_time_calibration_and_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            release,state,manifest,request=self.fixture(td)
            before=(state/'mission-request.json').read_bytes()
            result=load_request(release,state,manifest,'test-boot',20.)
            self.assertEqual(result['waypoints'],((.08,0.),))
            self.assertEqual((state/'mission-request.json').read_bytes(),before)
            for changes in ({'boot_id':'other'},{'release_id':'d'*64},{'calibration_sha256':'e'*64},
                            {'created_s':21.},{'expires_s':20.},{'duration_s':46.},
                            {'duration_s':True},{'waypoints':[[math.nan,0.]]},{'extra':1}):
                (state/'mission-request.json').write_text(json.dumps({**request,**changes}))
                with self.assertRaises(ValueError):load_request(release,state,manifest,'test-boot',20.)

    def test_loader_missing_tampered_unmeasured_or_duplicate_reject(self):
        for change in ('missing','tampered','photo','duplicate','oversize'):
            with tempfile.TemporaryDirectory() as td:
                release,state,manifest,_=self.fixture(td);path=release/'navigation-calibration.json'
                if change=='missing':manifest['files'].pop('navigation-calibration.json')
                if change=='tampered':path.write_text(path.read_text()+' ')
                if change=='photo':
                    value=json.loads(path.read_text());value['basis']='photo_hypothesis';path.write_text(json.dumps(value))
                    manifest['files']['navigation-calibration.json']=hashlib.sha256(path.read_bytes()).hexdigest()
                if change=='duplicate':(state/'mission-request.json').write_text('{"schema":1,"schema":2}')
                if change=='oversize':(state/'mission-request.json').write_text(' '*16385)
                with self.assertRaises(ValueError):load_request(release,state,manifest,'test-boot',20.)

    def run_fixture(self, *, fault=None):
        clock=[20.];position=[0.,0.,0.];velocity=[0.,0.];packets=deque();events=[];sent=[]
        consumed=[];halts=[];arm_calls=[];sequence=[0]
        link=RosLink.__new__(RosLink);link.enabled=False;link.navigation=RosObservations()
        link.rows=[];link.reason='active';link.sensor=NS(torque=True)
        link.node=NS(count_publishers=lambda _:1,get_clock=lambda:NS(now=lambda:NS(nanoseconds=int((clock[0]-10)*1e9))))
        link.Twist=lambda:NS(header=NS(frame_id='',stamp=NS(sec=0,nanosec=0)),
                             twist=NS(linear=NS(x=0.),angular=NS(z=0.)))
        def receive():
            if fault=='disconnect' and len(sent)>=3:raise ValueError('INPUT_CLOSED_OR_OVERFLOW')
            if fault in {'cancel','finish_stop','force_stop'} and len(sent)>=3 and not packets:
                sequence[0]+=1
                return {'sequence':sequence[0],'action':'close' if fault=='cancel' else fault,'challenge':'','age_ms':0}
            return packets.popleft() if packets else None
        def output(value):
            if fault=='no_input' or fault=='lost_heartbeat' and len(sent)>=3:return
            sequence[0]+=1
            packets.append({'sequence':sequence[0],'action':'forward' if fault=='remote_direction' else 'watch',
                            'challenge':value['challenge'],'age_ms':0})
        def refresh():
            stamp=int((clock[0]-10-.02)*1e9)
            for kind in ('odom','scan'):
                previous=link.navigation.values[kind]
                if previous is not None and stamp<=previous['source_stamp_ns']:continue
                msg=message(kind,stamp)
                if kind=='odom':
                    msg.pose.pose.position.x,msg.pose.pose.position.y=position[:2]
                    msg.pose.pose.orientation.z=math.sin(position[2]/2)
                    msg.pose.pose.orientation.w=math.cos(position[2]/2)
                else:
                    msg.time_increment=.0001
                    if fault=='obstacle' and len(sent)>=3:msg.ranges=[.2]*72
                    if fault=='missing_scan':continue
                link.navigation.receive(kind,msg,int((clock[0]-10)*1e9),clock[0],1)
            link.rows.append({'t':clock[0],'encoders':[len(sent),len(sent)],'torque':link.enabled,
                              'source_age_s':.02,'voltage_v':12.})
        def spin(dt):
            v,w=velocity;position[0]+=math.cos(position[2])*v*dt
            position[1]+=math.sin(position[2])*v*dt;position[2]+=w*dt
            clock[0]+=dt
            if not (fault=='stale_scan' and len(sent)>=3):refresh()
        def enable():
            if link.enabled:return
            arm_calls.append(clock[0]);link.enabled=True
            if fault=='cancel_during_arm':
                sequence[0]+=1;packets.append({'sequence':sequence[0],'action':'close','challenge':'','age_ms':0})
            spin(.01)
        def publish(msg):
            velocity[:]=[msg.twist.linear.x,msg.twist.angular.z]
            stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
            sent.append((clock[0],*velocity,clock[0]-10-stamp))
        def halt():
            halts.append(clock[0]);velocity[:]=[0.,0.];link.enabled=False
            if fault=='stop_failed':raise ValueError('STOP_READBACK_UNCONFIRMED')
        def record(kind,**data):
            if fault=='journal_failed' and kind=='mission_decision':raise ValueError('JOURNAL_WRITE_FAILED')
            event={'schema':'robot-session-1.0','robot_session_id':'mission-fake','event_index':len(events)+1,
                'clock_domain':'robot_monotonic','t':clock[0],'kind':kind,'data':data}
            self.assertTrue(valid_event(event),event);events.append(event)
            if fault=='slow_decision_log' and kind=='mission_decision':clock[0]+=.02
        link.spin=spin;link.fresh=lambda:None;link.enable=enable;link.halt=halt;link.pub=NS(publish=publish)
        refresh()
        request={'mission_id':'a'*32,'request_sha256':'b'*64,'waypoints':((.08,0.),),
            'duration_s':.15 if fault=='deadline' else 5.,'expires_s':70.,
            'binding':PlanarBinding('base_footprint','base_scan',(0.,0.,0.),(.1,0.,0.),.18,'a'*64)}
        if fault=='turn':request.update(waypoints=((.03,.03),),duration_s=10.)
        def consume():
            if fault=='consumed':raise FileExistsError('CONSUMED')
            consumed.append(1)
        result=error=None
        with patch('teleop_ros.time.monotonic',lambda:clock[0]):
            try:result=run_mission(link,NS(receive=receive),output,request,record=record,consume=consume,clock=lambda:clock[0])
            except Exception as exc:error=exc
        self.assertTrue(halts);self.assertFalse(link.enabled);self.assertEqual(velocity,[0.,0.])
        return result,error,sent,events,consumed,arm_calls

    def test_local_mission_arrives_without_remote_directions_or_repeat_approval(self):
        result,error,sent,events,consumed,armed=self.run_fixture()
        self.assertIsNone(error);self.assertEqual(result['status'],'MISSION_ARRIVED')
        self.assertGreater(len(sent),30);self.assertEqual(len(consumed),1);self.assertEqual(len(armed),1)
        self.assertEqual({e['data']['action'] for e in events if e['kind']=='accepted'},{'watch'})
        decisions=[e for e in events if e['kind']=='mission_decision']
        self.assertEqual(len(decisions),len(sent)+1)
        self.assertGreater(decisions[-1]['data']['decision']['navigation']['pose_xy_yaw'][0],.06)

    def test_failure_paths_stop_and_do_not_report_arrival(self):
        for fault in ('disconnect','lost_heartbeat','stale_scan','obstacle','journal_failed','deadline','stop_failed'):
            with self.subTest(fault=fault):
                result,error,*_=self.run_fixture(fault=fault)
                self.assertIsNone(result);self.assertIsNotNone(error)

    def test_turn_then_drive_is_selected_locally(self):
        result,error,sent,events,*_=self.run_fixture(fault='turn')
        self.assertIsNone(error);self.assertEqual(result['status'],'MISSION_ARRIVED')
        self.assertTrue(any(v==0 and w==.2 for _,v,w,_ in sent))
        self.assertTrue(any(v==.03 and w==0 for _,v,w,_ in sent))
        self.assertEqual({e['data']['action'] for e in events if e['kind']=='accepted'},{'watch'})

    def test_log_delay_never_changes_recorded_publish_source_age(self):
        result,error,sent,events,*_=self.run_fixture(fault='slow_decision_log')
        self.assertIsNone(error);self.assertEqual(result['status'],'MISSION_ARRIVED')
        published=[e for e in events if e['kind']=='published']
        for event,command in zip(published,sent):
            self.assertGreater(event['t']-command[0],.019)
            self.assertAlmostEqual(event['data']['source_age_s'],command[3],places=7)

    def test_no_input_unreviewed_scan_remote_direction_or_consumed_request_never_output(self):
        for fault in ('no_input','missing_scan','remote_direction','consumed'):
            with self.subTest(fault=fault):
                _,error,sent,*_=self.run_fixture(fault=fault)
                self.assertIsNotNone(error);self.assertEqual(sent,[])

    def test_cancel_between_commands_or_during_arm_never_resumes(self):
        result,error,sent,*_=self.run_fixture(fault='cancel')
        self.assertIsNone(error);self.assertEqual(result['status'],'MISSION_CANCELLED');self.assertEqual(len(sent),3)
        result,error,sent,*_=self.run_fixture(fault='cancel_during_arm')
        self.assertIsNone(error);self.assertEqual(result['status'],'MISSION_CANCELLED');self.assertEqual(sent,[])

    def test_both_stop_modes_never_publish_another_mission_command(self):
        for action,status in (('finish_stop','COMMAND_SEGMENT_STOPPED'),('force_stop','FORCE_STOPPED')):
            result,error,sent,events,*_=self.run_fixture(fault=action)
            self.assertIsNone(error);self.assertEqual(result['status'],status);self.assertEqual(len(sent),3)
            self.assertTrue(any(e['kind']=='stop_requested' and e['data']['action']==action for e in events))

    def test_production_mission_events_reach_existing_archive_without_reexecution(self):
        from twinpulse_app.session_history import review_session
        from twinpulse_app.command_broker import BrokerError
        _,error,_,events,*_=self.run_fixture()
        self.assertIsNone(error)
        with tempfile.TemporaryDirectory() as td:
            job='a'*32;out=Path(td)/'artifacts/manual-control'/job;out.mkdir(parents=True)
            rows=[]
            def append(kind,data,t):
                rows.append({'schema':'control-session-1.0','job_id':job,'event_index':len(rows)+1,
                    'clock_domain':'pc_monotonic','t':t,'kind':kind,'real_transport':False,'data':data})
            append('pc_session_started',{'mode':'mission'},100.)
            for event in events:append('robot_event',{'event':event},event['t']+100)
            append('robot_finished',{'status':'MISSION_ARRIVED','reason':None,
                'robot_session_id':'mission-fake','cleanup_confirmed':True},200.)
            path=out/'session.jsonl'
            def save():path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            save();before=path.read_bytes()
            (out/'result.json').write_text(json.dumps({'session_log_complete':True,'session_event_count':len(rows),'real_transport':False}))
            value=review_session(td,job)
            self.assertEqual(value['record_status'],'COMPLETE_RECORD');self.assertFalse(value['motion_authorized'])
            self.assertIsNone(value['physical_success']);self.assertGreater(len(value['mission_events']),30)
            self.assertEqual(path.read_bytes(),before)
            decisions=[r['data']['event'] for r in rows if r['kind']=='robot_event' and r['data']['event']['kind']=='mission_decision']
            decisions[1]['data']['tick']=1;save()
            with self.assertRaises(BrokerError):review_session(td,job)

    def test_mission_event_rejects_forged_authority_or_inconsistent_stop(self):
        import copy
        _,_,_,events,*_=self.run_fixture()
        value=next(e for e in events if e['kind']=='mission_decision')
        for key,changed in (('physical_authority',True),('reason','STOP'),('allowed',False)):
            bad=copy.deepcopy(value);bad['data']['decision'][key]=changed
            self.assertFalse(valid_event(bad))
        bad=copy.deepcopy(value);bad['data']['decision']['navigation']['alignment_verified']=True
        self.assertFalse(valid_event(bad))


def write_rehearsal_archive(root):
    """Fixed artificial sensor run through production code, for the App browser test."""
    result,error,sent,events,consumed,_=MissionTests().run_fixture()
    if error is not None:raise error
    job='f'*32;out=Path(root)/'artifacts/manual-control'/job;out.mkdir(parents=True,exist_ok=False)
    rows=[]
    def append(kind,data,t):
        rows.append({'schema':'control-session-1.0','job_id':job,'event_index':len(rows)+1,
            'clock_domain':'pc_monotonic','t':t,'kind':kind,'real_transport':False,'data':data})
    append('pc_session_started',{'mode':'mission'},100.)
    for event in events:append('robot_event',{'event':event},event['t']+100)
    append('robot_finished',{'status':result['status'],'reason':None,
        'robot_session_id':'mission-fake','cleanup_confirmed':True},200.)
    (out/'session.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    (out/'result.json').write_text(json.dumps({'session_log_complete':True,'session_event_count':len(rows),
                                             'real_transport':False}),encoding='utf-8')
    return {'job_id':job,'status':result['status'],'data':'ARTIFICIAL_SENSOR_FIXTURE',
            'physical_validation':'NOT_RUN','published_count':len(sent),'consumed_count':len(consumed),
            'remote_actions':sorted({e['data']['action'] for e in events if e['kind']=='accepted'})}


if __name__=='__main__':unittest.main()
