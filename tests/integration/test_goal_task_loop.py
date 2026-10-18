# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline task orchestration/fault contracts. No robot or Isaac acceptance."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock, Event
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from twinpulse_app.goal_task_loop import GoalTaskLoop, resource_check, check_leg
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.revisions import canonical_sha256


def plan():
    return {'schema':'current-goal-preview-2.0','plan_id':'a'*64,'physical_authority':False,
            'scene_revision':'b'*64,'start':[0.,0.],'goal':[.2,0.],'route':[[.2,0.]],'yaw_rad':0.,
            'binding':{'context':{'project_id':'room','source_revision':'d'*64,'epoch':3,'boot_id':'boot','session_id':'first'},
            'room_revision':'c'*64,'map_revision':'e'*64,'alignment_revision':'f'*64,'room_from_map':[0.,0.,0.]}}


def resources():
    return {'task_resources':{'schema':'task-resources-1.0','sample_s':10.,'source_age_s':.02,'voltage_v':12.,'motor_disabled':True}}


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p=plan();self.initial={'job_id':'first','state':'MISSION_ARRIVED','worker_active':False,
            'report_status':'SAVED','approved_preview':self.p}
        self.current=deepcopy(self.initial);self.inputs=[];self.stops=[];self.checks=[]
        self.preparing=Event();self.release=Event();self.delay=False;self.fault=None
        outer=self
        class Navigation:
            start_lock=RLock();demonstration=None
            def snapshot(inner,owner):return {'job':deepcopy(outer.current)}
            def prepare(inner,owner,text,**kw):
                outer.inputs.append(text);outer.preparing.set()
                if outer.delay:outer.release.wait(2.)
                if kw['_task_token'] is not inner.task_loop.token or inner.task_loop.cancelled.is_set():raise ValueError('TASK_STOP_REQUESTED')
                leg=len(outer.inputs);preview=deepcopy(outer.p)
                preview.update(start=[.2,0.] if leg%2 else [0.,0.],goal=[0.,0.] if leg%2 else [.2,0.],
                    route=[[0.,0.]] if leg%2 else [[.2,0.]],yaw_rad=3.14159 if leg%2 else 0.)
                ev=resources()
                if outer.fault=='missing':ev={}
                if outer.fault=='low':ev['task_resources']['voltage_v']=11.19
                if outer.fault=='source':preview['binding']['context']['boot_id']='changed'
                kw['_task_check'](preview,ev,preview['binding']['context'],10.05)
                outer.checks.append('preview');inner.review=preview
                return {'plan':preview}
            def can_confirm(inner):return True
            def confirm(inner,owner,digest,expiry,**kw):
                if inner.task_loop.cancelled.is_set():raise ValueError('TASK_STOP_REQUESTED')
                ev=resources()
                if outer.fault=='low_confirm':ev['task_resources']['voltage_v']=11.19
                kw['_task_check'](inner.review,ev,inner.review['binding']['context'],10.05)
                outer.checks.append('confirm')
                outer.current={'job_id':str(len(outer.inputs)),'state':'MISSION_ARRIVED','worker_active':False,'report_status':'SAVED'}
                if outer.fault=='watchdog':outer.current.update(state='FAILED',error='INPUT_DEADLINE_EXPIRED')
                if outer.fault=='report':outer.current.update(report_status='FAILED',report_error='MISSION_REPORT_STORAGE_FULL')
                if outer.fault=='cleanup':outer.current['cleanup_error']='SENSOR_CLEANUP_NOT_CONFIRMED'
                if len(outer.inputs)>=3 and not outer.fault:inner.task_loop.cancelled.set()
                return {'job':deepcopy(outer.current)}
            def cancel(inner,owner):pass
        self.nav=Navigation()
        self.nav.mission=SimpleNamespace(automatic=SimpleNamespace(root=Path(self.temp.name)),
            snapshot=lambda _: {'job':deepcopy(self.current)},
            stop=lambda owner,jid,force:self.stops.append((owner,jid,force)))
        self.loop=GoalTaskLoop(self.nav);self.nav.task_loop=self.loop;self.addCleanup(self.loop.close)

    def start(self):
        offer=self.loop.offer('owner',self.current)
        self.loop.start('owner',offer['task_digest'],time.time()*1000+1500)
        return offer

    def finish(self):
        self.loop.worker.join(4.)
        self.assertFalse(self.loop.active())
        return self.loop.snapshot('owner')

    def test_one_approval_alternates_successful_fresh_legs_and_durable_history(self):
        offer=self.start();state=self.finish()
        self.assertEqual([s.split('x=')[1].split()[0] for s in self.inputs],['0.0','0.2','0.0'])
        self.assertEqual(self.checks,['preview','confirm']*3)
        self.assertEqual(state['completed_legs'],2);self.assertEqual(state['state'],'STOPPED')
        self.assertEqual(offer['max_leg_s'],45.);self.assertFalse(state['physical_demo_ready'])
        rows=[json.loads(v) for v in self.loop.path.read_text().splitlines()]
        self.assertEqual(rows[0]['kind'],'task_approved');self.assertEqual(rows[-1]['kind'],'task_ended')
        self.assertEqual(sum(r['kind']=='leg_result' for r in rows),3)
        self.assertTrue(state['resources']['historical']);self.assertEqual(state['resources']['load_measurement'],'UNSUPPORTED')
        self.assertIsNone(self.loop.offer('owner',self.current))
        restored=GoalTaskLoop(self.nav)
        self.assertIsNone(restored.snapshot('owner'));self.assertFalse(restored.active())

    def test_missing_low_changed_source_rejected_before_confirmation(self):
        for fault,reason in [('missing','TASK_BATTERY_UNAVAILABLE'),('low','TASK_BATTERY_BELOW_REARM_MARGIN'),('source','TASK_SOURCE_CHANGED')]:
            with self.subTest(fault=fault):
                self.current=deepcopy(self.initial);self.inputs=[];self.checks=[];self.fault=fault
                self.loop.job=None;self.start();state=self.finish()
                self.assertEqual(state['state'],'FAILED');self.assertIn(reason,state['error'])
                self.assertEqual(len(self.inputs),1);self.assertEqual(self.checks,[])

    def test_new_resource_check_after_isaac_does_not_reuse_preview_voltage(self):
        self.fault='low_confirm';self.start();state=self.finish()
        self.assertEqual(state['state'],'FAILED');self.assertIn('TASK_BATTERY_BELOW_REARM_MARGIN',state['error'])
        self.assertEqual(self.checks,['preview']);self.assertEqual(self.current['job_id'],'first')

    def test_failed_worker_cleanup_report_do_not_renew_or_start_next_leg(self):
        for fault,reason in [('watchdog','INPUT_DEADLINE_EXPIRED'),('report','MISSION_REPORT_STORAGE_FULL'),('cleanup','SENSOR_CLEANUP_NOT_CONFIRMED')]:
            with self.subTest(fault=fault):
                self.current=deepcopy(self.initial);self.inputs=[];self.fault=fault;self.loop.job=None
                self.start();state=self.finish()
                self.assertEqual(state['state'],'FAILED');self.assertIn(reason,state['error']);self.assertEqual(len(self.inputs),1)

    def test_stop_preempts_slow_prepare_and_force_upgrade(self):
        self.delay=True;self.start();self.assertTrue(self.preparing.wait(1.))
        with self.assertRaises(BrokerError):self.loop.stop('other',False)
        before=time.monotonic();self.loop.stop('owner',False);self.loop.stop('owner',True)
        self.assertLess(time.monotonic()-before,.1)
        self.release.set();state=self.finish()
        self.assertEqual(self.checks,[]);self.assertEqual(self.current['job_id'],'first')
        self.assertEqual(state['completed_legs'],0);self.assertFalse(state['motion_authorized'])

    def test_no_offer_before_saved_report_cleanup_and_no_owned_confirmation_replay(self):
        for change in ({'worker_active':True},{'report_status':'PENDING'},{'cleanup_error':'FAILED'},{'state':'FAILED'}):
            self.assertIsNone(self.loop.offer('owner',{**self.initial,**change}))
        offer=self.loop.offer('owner',self.initial)
        for owner,digest,expiry in [('other',offer['task_digest'],time.time()*1000+1500),('owner','bad',time.time()*1000+1500),('owner',offer['task_digest'],0)]:
            with self.assertRaises(BrokerError):self.loop.start(owner,digest,expiry)
        self.assertEqual(self.inputs,[])
        self.start();self.finish()
        with self.assertRaises(BrokerError):self.loop.start('owner',offer['task_digest'],time.time()*1000+1500)

    def test_journal_failure_prevents_transport(self):
        self.loop.offer('owner',self.initial)
        with patch.object(self.loop,'_record',side_effect=OSError('DISK_FULL')):
            with self.assertRaises(OSError):self.loop.start('owner',self.loop.contract['task_digest'],time.time()*1000+1500)
        self.assertEqual(self.inputs,[]);self.assertIsNone(self.loop.worker)

    def test_internal_snapshot_never_renews_browser_presence(self):
        self.loop.owner='owner';self.loop.owner_seen_s=time.monotonic()-3.
        self.loop.snapshot('owner')
        with self.assertRaisesRegex(ValueError,'TASK_OWNER_CONNECTION_LOST'):self.loop.can_continue()
        self.loop.touch('other')
        with self.assertRaisesRegex(ValueError,'TASK_OWNER_CONNECTION_LOST'):self.loop.can_continue()
        self.loop.touch('owner');self.assertTrue(self.loop.can_continue())

    def test_resource_age_unknown_nonfinite_motor_and_hysteresis(self):
        for key,value,reason in [('sample_s',9.8,'STALE'),('source_age_s',.2,'STALE'),('voltage_v',float('nan'),'INVALID'),
                                ('motor_disabled',False,'MOTOR_OFF'),('voltage_v',11.2,'REARM_MARGIN')]:
            ev=resources();ev['task_resources'][key]=value
            with self.assertRaisesRegex(ValueError,reason):resource_check(ev,10.)
        self.assertFalse(resource_check(resources(),10.1)['capacity_measured'])

    def test_anchor_frame_scene_budget_and_start_envelope(self):
        contract=self.loop.offer('owner',self.initial);preview=deepcopy(self.p)
        preview.update(start=[.2,0.],goal=[0.,0.],route=[[0.,0.]],yaw_rad=3.14159)
        for fault,reason in [('scene','TASK_SCENE_CHANGED'),('frame','TASK_FRAME_OR_REVISION_CHANGED'),('start','TASK_START_OUTSIDE_ARRIVAL_ENVELOPE'),('budget','TASK_ROUTE_EXCEEDS_BOUNDED_BUDGET')]:
            bad=deepcopy(preview)
            if fault=='scene':bad['scene_revision']='z'*64
            if fault=='frame':bad['binding']['room_from_map'][0]=.1
            if fault=='start':bad['start']=[.31,0.]
            if fault=='budget':bad['route']=[[2.,0.],[0.,0.]]
            with self.assertRaisesRegex(ValueError,reason):check_leg(contract,bad,resources(),bad['binding']['context'],10.05,'a')
        changed=deepcopy(preview);changed['binding']['map_revision']='1'*64
        self.assertEqual(check_leg(contract,changed,resources(),changed['binding']['context'],10.05,'a')['voltage_v'],12.)
