# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isolated TEST-ONLY device fake for production protocol/loop browser integration.
Never imports ROS/serial or spawns SSH. Cannot produce production qualification.
"""
import json
import hashlib
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
sys.path.insert(0,str(ROOT))
from teleop_worker import control,InputStream,emit
from twinpulse_core.ros_observations import RosObservations
from teleop_ros import RosLink


class Link:
    def __init__(self):
        self.sensor=SimpleNamespace(battery=12.4,left_encoder=0,right_encoder=0,torque=False)
        self.reason='explicit_stop';self.enabled=False;self.rows=[];self.events=[]
        self.v=self.w=0.;self.last=0.;self.pos=[0.,0.]
    def navigation_snapshot(self):
        # Test-only missing sensor state exercises real journal transport without
        # inventing odometry from wheel commands or starting a fake lidar driver.
        return RosObservations().snapshot(time.monotonic())
    def enable(self):self.enabled=True;self.sensor.torque=True;self.reason='armed_waiting_for_command'
    def publish(self,v,w,age):
        self.v,self.w=v,w;self.last=time.monotonic()-age;self.reason='active'
        self.events.append([v,w,age])
    def fresh(self):pass
    def spin(self,seconds):
        time.sleep(seconds);now=time.monotonic()
        if self.reason=='active' and now-self.last>=.4:self.reason='command_timeout';self.v=self.w=0.
        self.pos[0]+=(self.v-self.w*.08)*seconds*19755
        self.pos[1]+=(self.v+self.w*.08)*seconds*19755
        self.sensor.left_encoder,self.sensor.right_encoder=map(round,self.pos)
        if not self.rows or now>self.rows[-1]['t']:
            self.rows.append({'t':now,'encoders':[self.sensor.left_encoder,self.sensor.right_encoder],
                              'torque':self.sensor.torque,'source_age_s':0.})
    def halt(self):
        self.enabled=False;self.sensor.torque=False;self.v=self.w=0.;self.reason='explicit_stop'
        self.spin(.25)  # Production OFF telemetry confirmation is not instantaneous.
    def release(self):
        self.halt()
        self.spin(.30)  # Stress a longer readback than the old 250ms cleanup sleep.


class MissionLink(Link):
    """Artificial sensor/dynamics fixture, production navigation/publish methods."""
    navigation_step=RosLink.navigation_step
    navigation_snapshot=RosLink.navigation_snapshot
    navigation_evidence=staticmethod(RosLink.navigation_evidence)
    navigation_stop_check=RosLink.navigation_stop_check
    publish=RosLink.publish

    def __init__(self):
        super().__init__()
        self.navigation=RosObservations();self.pose=[0.,0.,0.]
        NS=SimpleNamespace
        self.node=NS(count_publishers=lambda _:1,get_clock=lambda:NS(now=lambda:NS(nanoseconds=int(time.monotonic()*1e9))))
        self.Twist=lambda:NS(header=NS(frame_id='',stamp=NS(sec=0,nanosec=0)),twist=NS(linear=NS(x=0.),angular=NS(z=0.)))
        def sent(msg):
            age=time.monotonic()-(msg.header.stamp.sec+msg.header.stamp.nanosec/1e9)
            Link.publish(self,msg.twist.linear.x,msg.twist.angular.z,age)
        self.pub=NS(publish=sent)
        self.spin(.001)

    def spin(self,seconds):
        from packages.twinpulse_core.tests.test_ros_observations import message
        super().spin(seconds)
        self.pose[0]+=math.cos(self.pose[2])*self.v*seconds
        self.pose[1]+=math.sin(self.pose[2])*self.v*seconds;self.pose[2]+=self.w*seconds
        now=time.monotonic();stamp=int((now-.02)*1e9)
        if stamp<=self.navigation.stamps['odom']:return  # Windows clock tick: no fabricated duplicate sample.
        for kind in ('odom','scan'):
            msg=message(kind,stamp)
            if kind=='odom':
                msg.pose.pose.position.x,msg.pose.pose.position.y=self.pose[:2]
                msg.pose.pose.orientation.z=math.sin(self.pose[2]/2);msg.pose.pose.orientation.w=math.cos(self.pose[2]/2)
            else:msg.time_increment=.0001
            self.navigation.receive(kind,msg,int(now*1e9),now,1)


def mission_fixture(state,stream):
    from mission_runtime import receive_request
    calibration={'schema':'planar-calibration-1.0','basis':'reviewed_robot_frames',
        'odom_child_frame':'base_footprint','scan_frame':'base_scan','child_to_base':[0.,0.,0.],
        'base_to_scan':[.1,0.,0.],'footprint_radius_m':.18,'evidence_sha256':'a'*64,
        'guard_sha256':'b'*64,'namespace':'/tp_guard_stationary'}
    # These labels are ONLY artificial fixtures, never deployed or real evidence.
    path=state/'navigation-calibration.json';path.write_text(json.dumps(calibration))
    manifest={'source_id':'c'*64,'files':{'navigation-calibration.json':hashlib.sha256(path.read_bytes()).hexdigest(),
                                         'bin/turtlebot3_ros':'b'*64}}
    return receive_request(state,manifest,'fake-boot',stream,emit)


def main(mode,state):
    state.mkdir(exist_ok=True)
    report={'physical_validation':'SYNTHETIC_TEST_ONLY','cleanup_confirmed':True,'status':'FAILED'}
    link=Link()
    try:
        if mode=='prepare':return 0
        if mode=='off':report['status']='IDLE_CONFIRMED'
        elif mode=='lidar':
            emit({'state':'LIDAR_RUNNING'});stream=InputStream();end=time.monotonic()+8
            while time.monotonic()<end:
                try:
                    msg=stream.receive()
                    if msg and msg['action'] in {'stop','close','finish_stop','force_stop'}:break
                except ValueError:break
                time.sleep(.01)
            report['status']='LIDAR_DATA_QUIET'
        else:
            if mode in {'control','mission'} and not (state/'fake-qualified').exists():raise ValueError('PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE')
            index=0
            def record(kind,**data):
                nonlocal index
                index+=1
                emit({'state':'SESSION_EVENT','event':{'schema':'robot-session-1.0',
                    'robot_session_id':'synthetic-test-only','event_index':index,
                    'clock_domain':'robot_monotonic','t':time.monotonic(),'kind':kind,'data':data}})
            if mode=='mission':
                from mission_runtime import run_mission
                stream=InputStream(max_line=16384);request=mission_fixture(state,stream)
                link=MissionLink()
                report.update(run_mission(link,stream,emit,request,record=record,
                    consume=lambda:(state/('consumed-'+request['mission_id'])).touch(exist_ok=False)))
            else:report.update(control(link,InputStream(),emit,mode,record=record))
            if mode=='qualify' and report['status']=='STOP_POLICY_PASS':
                (state/'fake-qualified').touch();report['status']='QUALIFIED'
    except Exception as exc:report['reason']=str(exc)
    finally:
        link.halt()
        (state/(str(time.time_ns())+'-events.json')).write_text(json.dumps(link.events))
        emit({'state':'FINISHED','report':report})
    return 0


if __name__=='__main__':raise SystemExit(main(sys.argv[1],Path(sys.argv[2])))
