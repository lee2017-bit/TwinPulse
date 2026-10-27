# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""TEST ONLY pipe peer: actual bootstrap/RosLink/observed worker, synthetic rays.

No SSH, ROS, serial, profile registration or physical qualification. World pose
is private to the output-reactive raycaster, never given to the matcher.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT,ROOT/'packages/twinpulse_core/src',ROOT/'packages/twinpulse_robot_safety'):
    sys.path.insert(0,str(folder))
import json
import hashlib
import math
import time
from tests.fixtures.manual_robot_process import Link,MissionLink,mission_fixture
from teleop_worker import InputStream,emit
from mission_runtime import run_mission
from observed_runtime import RobotObservedFactory
from twinpulse_core.observation_stream import ObservationWindow,from_ros_message
from packages.twinpulse_core.tests.test_ros_observations import message
from packages.twinpulse_core.tests.test_room_localization import scan_points
from twinpulse_core.room_localization import compose


def fixture_evidence_exporter(source):
    """TEST ONLY local file exchange, not a real raw/ROS qualification receipt."""
    source=Path(source)
    def export(report,destination):
        destination.mkdir(parents=True,exist_ok=True);files={}
        if 'mission_evidence' in report:
            descriptor=report['mission_evidence'];data=(source/descriptor['file']).read_bytes()
            (destination/descriptor['file']).write_bytes(data)
            files[descriptor['file']]={'status':'COPIED','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        receipt={'status':'COMPLETE','binding':'VERIFIED','mode':'mission',
            'robot_session_id':report['robot_session_id'],'files':files,'test_only':True}
        (destination/'export.json').write_text(json.dumps(receipt));return receipt
    return export


class ObservedLink(MissionLink):
    def halt(self):
        # TEST ONLY: fail one native readback after real synthetic publications;
        # independent outer cleanup still runs. Never used by deployed code.
        fail=(self.world.get('combined_halt_fault') and self.enabled
              and sum(bool(v or w) for v,w,_ in self.events)>5
              and not getattr(self,'halt_fault_injected',False))
        super().halt()
        if fail:
            self.halt_fault_injected=True
            raise ValueError('STOP_READBACK_UNCONFIRMED')

    def task_resources(self):
        # TEST ONLY battery source. Production uses ROS SensorState timestamps.
        return {'schema':'task-resources-1.0','sample_s':self.rows[-1]['t'],'source_age_s':0.,
                'voltage_v':self.world.get('voltage_v',12.4),'motor_disabled':not self.enabled and not self.sensor.torque}

    def __init__(self,context,*,world=None):
        # Fixture-only world configuration is not part of the signed mission
        # scope. The estimator sees only the generated ROS-shaped observations.
        self.world=world or {'vertices':[[-2,-2],[2,-2],[2,1],[-1,1],[-1,2],[-2,2]]}
        self.world_started=False
        self.world_started_at=time.monotonic()
        self.observation_window=ObservationWindow(context);self.sequence=0;self.dynamics_at=time.monotonic()
        super().__init__()

    def fresh_scan(self):pass

    def enable(self):
        # Model the real RosLink's first-arm spin: callbacks receive NEW rays
        # and odometry while wheels remain at zero. Never re-stamp an old
        # observation or hand the estimator the private world pose.
        already_enabled=self.enabled
        super().enable()
        if not already_enabled:self.spin(.06)

    def spin(self,dt):
        if not self.world_started:
            self.pose=list(self.world.get('start',[0.,0.,0.]));self.world_started=True
        Link.spin(self,dt)
        now=time.monotonic();elapsed=now-self.dynamics_at;self.dynamics_at=now
        # Fault injection only: observations retain original causal times and
        # stationary geometry despite actual native nonzero publications.
        if self.world.get('fault')!='progress_stall':
            self.pose[0]+=math.cos(self.pose[2])*self.v*elapsed
            self.pose[1]+=math.sin(self.pose[2])*self.v*elapsed;self.pose[2]+=self.w*elapsed
        stamp=int((now-.02)*1e9)
        if stamp<=self.navigation.stamps['odom']:return
        for kind in ('odom','scan'):
            if kind=='scan' and (self.world.get('fault')=='stale_scan' and now-self.world_started_at>1.5
                or self.world.get('fault')=='moving_stale_scan' and sum(bool(v or w) for v,w,_ in self.events)>20):continue
            msg=message(kind,stamp)
            if kind=='odom':
                msg.pose.pose.position.x,msg.pose.pose.position.y=self.pose[:2]
                msg.pose.pose.orientation.z=math.sin(self.pose[2]/2);msg.pose.pose.orientation.w=math.cos(self.pose[2]/2)
            else:
                vertices=self.world['vertices']
                outline={'segments':[[vertices[i],vertices[(i+1)%len(vertices)]] for i in range(len(vertices))]}
                points=scan_points(outline,compose(self.pose,[.1,0,0]))
                msg.ranges=[math.hypot(*p) for p in points];msg.angle_min=0.
                msg.angle_increment=math.tau/len(points);msg.angle_max=(len(points)-1)*msg.angle_increment
                msg.time_increment=0.;msg.scan_time=.1
            self.sequence+=1
            self.observation_window.receive(kind,from_ros_message(kind,msg),self.sequence,int(now*1e9),ros_now_ns=int(now*1e9))
            self.navigation.receive(kind,msg,int(now*1e9),now,1)


def main(state):
    state.mkdir(exist_ok=True);report={'physical_validation':'SYNTHETIC_TEST_ONLY','status':'FAILED','cleanup_confirmed':False}
    link=None;index=0;stop_published_index=None;fit_hold={}
    def record(kind,**data):
        nonlocal index,stop_published_index
        index+=1
        if (kind=='accepted' and data.get('action') in {'stop','close','finish_stop','force_stop'}
                and stop_published_index is None and link is not None):
            # TEST ONLY: the exact publish count when the robot RECEIVED the Stop.
            stop_published_index=len(link.events)
        emit({'state':'SESSION_EVENT','event':{'schema':'robot-session-1.0','robot_session_id':'synthetic-observed',
            'event_index':index,'clock_domain':'robot_monotonic','t':time.monotonic(),'kind':kind,'data':data}})
        if factory and kind=='mission_decision':factory.record_visual()
    factory=None
    try:
        stream=InputStream(max_line=16384);request=mission_fixture(state,stream)
        fixture_path=state/'synthetic-world.json'
        world=json.loads(fixture_path.read_text()) if fixture_path.is_file() else None
        hold=(world or {}).get('hold_fit_until_stop_s')
        if hold:
            # TEST ONLY: a photo fit slower than the PC's Stop latency, so a Stop
            # sent while the PC sees PHOTO_FIT_WHEELS_IDLE is received while the
            # fit still runs. The real fit then completes after cancellation: a
            # late result that must not resume the mission.
            from twinpulse_core import cold_start_mission
            real_fit=cold_start_mission.ColdStartMission._fit
            def held_fit(mission,saved):
                fit_hold['held_until_cancelled']=mission.cancelled.wait(float(hold))
                real_fit(mission,saved)
            cold_start_mission.ColdStartMission._fit=held_fit
        link=ObservedLink({'project_id':request['adaptive_scope']['project_id'],'session_id':'synthetic-observed',
            'boot_id':'fake-boot','release_id':'c'*64,'source_revision':'c'*64,'origin':'live_ros'},world=world)
        factory=RobotObservedFactory(link,request,output=emit,clock=time.monotonic)
        factory.prepare()
        report.update(run_mission(link,stream,emit,request,record=record,mission_factory=factory,
            consume=lambda:(state/('consumed-'+request['mission_id'])).touch(exist_ok=False)))
    except Exception as exc:
        report['reason']=str(exc)
        if link:report['synthetic_navigation_faults']=link.navigation.snapshot(time.monotonic())['faults']
    finally:
        if link:
            link.halt();report['cleanup_confirmed']=True
            report['sensor_cleanup_confirmed']=True
            report['synthetic_final_pose']=link.pose
            report['synthetic_final_velocity']=[link.v,link.w]
            report['synthetic_nonzero_after_stop']=(None if stop_published_index is None else
                sum(1 for v,w,_ in link.events[stop_published_index:] if v or w))
            if fit_hold:report['synthetic_fit_held_until_cancelled']=fit_hold.get('held_until_cancelled')
            (state/'published.json').write_text(json.dumps(link.events))
        if factory:
            report.update(mode='mission',robot_session_id=factory.context['session_id'],
                boot_id=factory.context['boot_id'],release_id=factory.context['release_id'])
            try:
                descriptor=factory.save_evidence(state)
                report['mission_evidence_status']='SAVED' if descriptor else 'NOT_COLLECTED'
                if descriptor:
                    report['mission_evidence']=descriptor
                    report['mission_id']=factory.request['mission_id']
                    report['mission_request_sha256']=factory.request['request_sha256']
            except Exception as exc:
                report['mission_evidence_status']='FAILED';report['mission_evidence_error']=str(exc)
        emit({'state':'FINISHED','report':report})


if __name__=='__main__':main(Path(sys.argv[-1]))
