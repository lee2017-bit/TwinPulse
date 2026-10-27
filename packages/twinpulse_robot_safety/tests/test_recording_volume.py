# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""No devices: ROS records that repeat a recorded message, and the reason a full journal stops a session.

2026-10-27: /tf repeated every odom pose and motion_guard/status repeated one string at
50 Hz; the session reached its recording budget after 31 min and the owner closed
without a reason of its own in the stream.
"""
import base64
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace as S
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from fleet_control import RosRecordDelivery
from fleet_worker import FleetWorker,InputLines

TOPICS={'odom':'nav_msgs/msg/Odometry','/tf':'tf2_msgs/msg/TFMessage','motion_guard/status':'std_msgs/msg/String'}


def odom(t):
    stamp=S(sec=int(t),nanosec=int(round(t%1*1e9)));pose=S(position=S(x=t/100,y=0.,z=0.),orientation=S(x=0.,y=0.,z=0.,w=1.))
    return S(header=S(stamp=stamp,frame_id='odom'),child_frame_id='base_footprint',pose=S(pose=pose),cdr=b'odom:%.3f'%t)


def tf(source,*,x=None,transforms=1):
    p=source.pose.pose;translation=S(x=p.position.x if x is None else x,y=p.position.y,z=p.position.z)
    item=S(header=S(stamp=source.header.stamp,frame_id='odom'),child_frame_id='base_footprint',transform=S(translation=translation,rotation=p.orientation))
    return S(transforms=[item]*transforms,cdr=b'tf:'+source.cdr)


class RosRepeatTests(unittest.TestCase):
    def test_copies_are_counted_gap_free_and_everything_else_is_recorded(self):
        events=[];received={topic:[] for topic in TOPICS}
        delivery=RosRecordDelivery(lambda kind,data:events.append(data),lambda m:m if isinstance(m,bytes) else m.cdr,TOPICS)
        sequence=0;special={}
        def deliver(topic,value,t):
            nonlocal sequence
            while delivery.status()['pending']>64:time.sleep(.0005)  # callbacks arrive in real time, not in a burst
            sequence+=1;received[topic].append(sequence)
            delivery(topic,value,dict(sequence=sequence,receipt_monotonic_ns=int(round(t*1e9)),receipt_ros_now_ns=int(round(t*1e9))))
            return sequence
        for step in range(500):  # 10 s at 50 Hz
            t=step*.02
            status='timeout' if 200<=step<225 else 'armed'
            deliver('motion_guard/status',S(data=status,cdr=status.encode()),t)
            if step%2==0:
                source=odom(t);deliver('odom',source,t)
                if step==300:special['two']=deliver('/tf',tf(source,transforms=2),t)
                elif step==350:special['moved']=deliver('/tf',tf(source,x=5.),t)
                else:deliver('/tf',tf(source),t)
            if step==400:special['bytes']=deliver('motion_guard/status',b'armed',t)
        status=delivery.close()
        self.assertIsNone(status['error'])
        recorded={topic:[e for e in events if e['topic']==topic] for topic in TOPICS}
        # 250 /tf copies of odom and 500 repeated guard strings are not 750 more records.
        self.assertLessEqual(len(recorded['/tf']),15)
        self.assertLessEqual(len(recorded['motion_guard/status']),16)
        self.assertEqual(len(recorded['odom']),250)
        for topic,rows in recorded.items():
            runs=[e['suppressed_since_previous'] for e in rows if 'suppressed_since_previous' in e]
            pending=status['unreported_runs'].get(topic)
            # Every callback is either a record or inside exactly one counted run between two records.
            self.assertEqual(len(rows)+sum(r['count'] for r in runs)+(pending['count'] if pending else 0),len(received[topic]),topic)
            covered=sorted([e['observation_sequence'] for e in rows]+[s for r in runs+([pending] if pending else [])
                for s in received[topic] if r['first_observation_sequence']<=s<=r['last_observation_sequence']])
            self.assertEqual(covered,received[topic],topic)
            previous=None
            for e in rows:
                run=e.get('suppressed_since_previous')
                if run:
                    self.assertLess(previous['observation_sequence'],run['first_observation_sequence'])
                    self.assertLess(run['last_observation_sequence'],e['observation_sequence'])
                    self.assertLessEqual(run['max_receipt_gap_s'],.04+1e-9)
                if previous is not None:self.assertLessEqual(e['receipt_start_s']-previous['receipt_start_s'],1.+.04+1e-9,topic)
                previous=e
            self.assertEqual(status['suppressed'].get(topic,0),len(received[topic])-len(rows),topic)
        sequences={e['observation_sequence'] for e in events}
        self.assertTrue({special['two'],special['moved'],special['bytes']}<=sequences)
        guard=[(e['receipt_start_s'],base64.b64decode(e['base64'])) for e in recorded['motion_guard/status']]
        self.assertIn((4.,b'timeout'),guard);self.assertIn((4.5,b'armed'),guard)
        self.assertEqual([e['chunk_index'] for e in events],list(range(len(events))))
        self.assertEqual([e['offset'] for e in events],[sum(e['length'] for e in events[:i]) for i in range(len(events))])


class Control:
    def __init__(self,*_,**__):self.stop_requested=threading.Event();self.cancel=threading.Event();self.field_until=1.
    def start(self):pass
    def snapshot(self):
        return dict(control_state='READY',blockers=[],drive_ready=True,battery=dict(voltage_v=11.9,percent=None,source='measured',sample_monotonic_s=None))
    def close(self):return dict(control_state='CLOSED',worker_reaped=True,cleanup_confirmed=True)


class Native:
    def __init__(self,*_):pass
    def latest_frame(self):return None
    def snapshot(self):return {'lidar_state':'OFF'}
    def stop(self):pass
    def close(self):return {'lidar_state':'OFF'}


class RecordingLimitTests(unittest.TestCase):
    def test_a_full_journal_names_its_byte_budget_in_the_stream_once(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(dict(schema='physical-live-start-1.0',operation_id='o'*32,robot_id='b'*32,project_id='default',
                connection_epoch='c'*32,binding_sha256='a'*64,worker_sha256='a'*64),tmp,events.append,control_factory=Control,native_factory=Native)
            worker.context.update(boot_id='b'*32,release_id='c'*64);worker._idle_board=lambda:None
            worker.journal.max_bytes=4096
            while not worker.recording_failed:worker.emit('heartbeat',worker.heartbeat())
            self.assertEqual(worker.recording_failure_reason,'SESSION_LOG_BYTE_BUDGET')
            self.assertTrue(worker.control.stop_requested.is_set())
            incoming=InputLines(io.BytesIO(b''));incoming.failed.wait(1)
            worker.run(incoming)
        faults=[e['data'] for e in events if e['kind']=='fault' and e['data'].get('subsystem')=='recording']
        self.assertEqual(len(faults),1)
        self.assertEqual(faults[0]['reason'],'SESSION_LOG_BYTE_BUDGET')
        self.assertEqual((faults[0]['recording']['reserved_bytes'],faults[0]['recording']['byte_limit']),(worker.journal.reserved,4096))
        self.assertEqual(events[-1]['kind'],'cleanup')


if __name__=='__main__':
    unittest.main()
