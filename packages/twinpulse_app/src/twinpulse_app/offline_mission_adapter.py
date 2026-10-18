# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Output-reactive offline raycaster, never a robot or measured room.

Truth is used only to produce synthetic scans and evaluate the swept footprint.
The shared controller sees synthetic odometry/scan, not evaluator coordinates.
"""
from collections import deque
from copy import deepcopy
import math
import time
from twinpulse_core.current_mission_evidence import CurrentMissionEvidence
from twinpulse_core.local_navigation import LocalPose, LocalScan
from twinpulse_core.room_localization import compose, inverse


def point_segment_distance(point, a, b):
    vector=[b[i]-a[i] for i in (0,1)];length=sum(v*v for v in vector)
    t=max(0.,min(1.,sum((point[i]-a[i])*vector[i] for i in (0,1))/length)) if length else 0.
    return math.dist(point,[a[i]+t*vector[i] for i in (0,1)])


class OfflineMissionAdapter:
    provenance='synthetic_raycast';frame_id='synthetic_room'

    def __init__(self,prior,room,effective,goal,*,segments,start,conditions,radius=.18):
        self.context={'project_id':room['project_id'],'source_revision':conditions['revision'],'epoch':1}
        self.tracker=CurrentMissionEvidence(prior['map'],prior['photo_alignment'],self.context,
            effective['effective_revision'],local_survey=True)
        self.segments=deepcopy(segments);self.world=list(start);self.anchor=inverse(start)
        self.t=20.;self.velocity=(0.,0.);self.sequence=0;self.packets=deque()
        self.link=self;self.incoming=self;self.reason='active';self.stop_requested=lambda:None
        self.request={'mission_id':'a'*32,'request_sha256':'b'*64,'waypoints':((.01,0.),),
                      'duration_s':goal['duration_s'],'expires_s':70.,'binding':None}
        self.conditions=deepcopy(conditions);self.radius=radius;self.last_scan=None
        self.raw=[];self.sent=[];self.samples=[];self.consumed=0;self.halted=0
        self.collision_samples=0;self.collision_episodes=0;self.touching=False

    def clock(self):return self.t
    def admit(self,goal):pass
    def safety(self):pass
    def fresh(self):self.safety()
    def consume(self):
        self.consumed+=1
        if self.consumed!=1:raise ValueError('MISSION_ALREADY_CONSUMED')
    def receive(self):
        action=self.stop_requested()
        if action:
            self.sequence+=1;return {'sequence':self.sequence,'action':action,'challenge':'','age_ms':0}
        return self.packets.popleft() if self.packets else None
    def output(self,value):
        self.sequence+=1;self.packets.append({'sequence':self.sequence,'action':'watch',
                                             'challenge':value['challenge'],'age_ms':0})
    def navigation_snapshot(self):return {'synthetic_raw_count':len(self.raw),'physical_validation':'NOT_RUN'}
    def current(self,pose,now):return self.tracker.update(pose,self.last_scan,now)
    def spin(self,dt):
        v,w=self.velocity
        self.world[0]+=v*dt*math.cos(self.world[2]);self.world[1]+=v*dt*math.sin(self.world[2])
        self.world[2]+=w*dt;self.t+=dt
        # Every published-segment integration step, not sparse UI frames.
        touching=any(point_segment_distance(self.world[:2],a,b)<=self.radius for a,b in self.segments)
        self.collision_samples+=int(touching)
        self.collision_episodes+=int(touching and not self.touching);self.touching=touching
        self.samples.append([self.t,*self.world])
        time.sleep(dt*.15)  # Mission clock continues while the actual fit works.
    def points(self):
        rows=[]
        for i in range(120):
            angle=self.world[2]+i*math.tau/120;dx,dy=math.cos(angle),math.sin(angle);hits=[]
            for p,q in self.segments:
                sx,sy=q[0]-p[0],q[1]-p[1];det=dx*sy-dy*sx
                if abs(det)<1e-8:continue
                ox,oy=p[0]-self.world[0],p[1]-self.world[1]
                distance=(ox*sy-oy*sx)/det;fraction=(ox*dy-oy*dx)/det
                if distance>0 and 0<=fraction<=1:hits.append(distance)
            distance=min(hits) if hits else 8.
            rows.append([distance*math.cos(i*math.tau/120),distance*math.sin(i*math.tau/120)])
        return rows
    def navigation_step(self,mission,binding,created,*,before_publish):
        before_publish();odom=compose(self.anchor,self.world)
        ranges=tuple(math.hypot(*p) for p in self.points())
        pose=LocalPose(tuple(odom),self.t,self.frame_id,'synthetic_model',self.provenance)
        self.last_scan=LocalScan(ranges,self.t,'base_link','synthetic_model',self.provenance)
        self.raw.append({'odom':list(odom),'ranges':list(ranges),'t':self.t})
        result=mission.step(pose,self.last_scan,self.t,command_created_s=created)
        if not result['allowed']:raise ValueError(result['reason'])
        before_publish();self.velocity=(result['linear_m_s'],result['angular_rad_s'])
        self.sent.append([self.t,*self.velocity])
        return {**result,'published_source_age_s':self.t-created}
    def navigation_stop_check(self,*_):self.safety()
    def halt(self):self.velocity=(0.,0.);self.halted+=1
    def close(self):self.halt()

