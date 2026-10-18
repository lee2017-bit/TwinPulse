# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact-route broker contracts. Engine doubles are NOT actual Isaac evidence."""
from copy import deepcopy
from dataclasses import replace
import time
import unittest
from twinpulse_core import CommandReceipt,SimulationSnapshot
from twinpulse_core.current_goal_preview import goal_preview
from twinpulse_core.goal_simulation import make_goal_simulation
from twinpulse_core.site_simulation import checked_plan
from twinpulse_app.command_broker import CommandBroker
from twinpulse_app.goal_demonstration import GoalDemonstration
from twinpulse_app.simulation_assets import burger_inventory
from tests.integration.test_current_goal_preview import evidence
from tests.integration.test_scene_changes import room_source


class GoalDemonstrationTests(unittest.TestCase):
    def setUp(self):
        self.scene=room_source().site.scene;current=evidence()
        current['project_id']='default'
        context={k:current[k] for k in ('project_id','source_revision','epoch')}
        self.review=goal_preview(self.scene,'Go x=.25 y=-1.8',current,context,1.)['plan']
        self.plan=make_goal_simulation(self.scene,self.review,burger_inventory())
        self.broker=CommandBroker();self.broker.register_engine('engine','stage');self.broker.acquire_lease('owner')
        self.sequence=0;self.commands=[];self.publish('built')
        self.service=GoalDemonstration(self.broker,lambda:self.scene,timeout_s=2.)
        self.addCleanup(self.service.close)

    def publish(self,state,*,run_id=None,position=None,capability=True,safety=None):
        self.sequence+=1
        self.broker.record_snapshot(SimulationSnapshot(engine_session_id='engine',stage_epoch='stage',project_id='default',
            sequence=self.sequence,applied_revision=self.scene.revision,run_id=run_id,runtime_state=state,
            safety_state=safety,safety_reason=safety,permitted_commands=('build_site_scene','run','pause','get_state'),
            capabilities=('site_scene_build_v2','site_simulation_v1','site_simulation_preview_v1','presentation_preset_v1')+
                (('exact_goal_demonstration_v1',) if capability else ()),position_m=position,
            telemetry_available=position is not None))

    def pump(self,*,complete=False,failure=None):
        command=self.broker.claim('engine','stage')
        if command:
            self.commands.append(command)
            self.broker.record_receipt(CommandReceipt(command_id=command.command_id,command_type=command.command_type,
                project_id='default',engine_session_id='engine',stage_epoch='stage',status='succeeded',applied_revision=self.scene.revision))
            if command.command_type=='build_site_scene':self.publish('built')
            elif command.command_type=='run':
                self.publish('running',run_id=self.plan['plan_id'],position=[*self.review['start'],0.])
            elif command.command_type=='pause':self.publish('paused',run_id=self.plan['plan_id'],position=[*self.review['goal'],0.])
        if complete and any(c.command_type=='run' for c in self.commands) and not any(c.command_type=='pause' for c in self.commands):
            self.publish('completed',run_id=self.plan['plan_id'],position=[*self.review['goal'],0.])
        if failure and any(c.command_type=='run' for c in self.commands):
            self.publish('error',run_id=self.plan['plan_id'],safety=failure)

    def finish(self,**kwargs):
        deadline=time.monotonic()+3.
        while self.service.worker.is_alive() and time.monotonic()<deadline:
            self.pump(**kwargs);time.sleep(.01)
        self.service.worker.join(.5)
        self.assertFalse(self.service.worker.is_alive())
        return self.service.snapshot('owner')

    def test_lossless_exact_route_and_digest_checked_not_replanned(self):
        self.assertEqual(self.plan['route'],self.review['route'])
        self.assertEqual(checked_plan(self.scene,self.plan),self.plan)
        self.assertEqual(self.plan['review']['max_linear_mps'],.03)
        for key,value in (('route',[[0.,0.]]),('review',{}),('physical_authority',True),('plan_id','0'*64)):
            changed=deepcopy(self.plan);changed[key]=value
            with self.assertRaises((ValueError,KeyError)):checked_plan(self.scene,changed)

    def test_admission_is_not_completion_and_receipt_bound_to_stage_scene_run(self):
        self.service.start('owner',self.scene,self.review)
        deadline=time.monotonic()+1.
        while not any(c.command_type=='run' for c in self.commands) and time.monotonic()<deadline:self.pump();time.sleep(.01)
        self.assertFalse(self.service.passed('owner',self.review['plan_id']))
        result=self.finish(complete=True)
        self.assertEqual(result['state'],'COMPLETED');self.assertFalse(result['receipt']['physical_authority'])
        self.assertEqual([c.command_type for c in self.commands],['build_site_scene','run','pause'])
        self.assertTrue(self.service.passed('owner',self.review['plan_id']))
        self.assertFalse(self.service.passed('other',self.review['plan_id']))
        self.assertFalse(self.service.passed('owner','0'*64))
        self.publish('built');self.assertFalse(self.service.passed('owner',self.review['plan_id']))
        self.broker.register_engine('new','newstage');self.assertFalse(self.service.passed('owner',self.review['plan_id']))

    def test_engine_capability_or_room_change_never_unlocks(self):
        self.publish('built',capability=False);self.service.start('owner',self.scene,self.review)
        result=self.finish();self.assertEqual(result['state'],'FAILED');self.assertEqual(self.commands,[])
        self.publish('built');self.service.start('owner',self.scene,self.review)
        self.scene=replace(self.scene,parent_revision='f'*64)
        result=self.finish();self.assertEqual(result['state'],'FAILED');self.assertIn('ROOM_CHANGED',result['error'])

    def test_stop_fault_and_timeout_preserve_cause_no_pass_no_retry(self):
        self.service.start('owner',self.scene,self.review);self.service.stop('owner')
        result=self.finish();self.assertEqual(result['state'],'CANCELLED');self.assertIsNone(result['receipt'])
        self.service.start('owner',self.scene,self.review);result=self.finish(failure='injected_fault')
        self.assertEqual(result['state'],'FAILED');self.assertIn('RUNTIME_FAILED',result['error'])
        self.service.timeout_s=.05;self.publish('built');self.service.start('owner',self.scene,self.review)
        result=self.finish();self.assertIn('TIMEOUT',result['error']);self.assertFalse(self.service.passed('owner',self.review['plan_id']))

    def test_foreign_project_rejected_before_worker_and_command(self):
        from twinpulse_app.command_broker import BrokerError
        foreign=deepcopy(self.review);foreign['binding']['context']['project_id']='other'
        with self.assertRaises(BrokerError):self.service.start('owner',self.scene,foreign)
        self.assertIsNone(self.service.worker);self.assertEqual(self.commands,[])

    def test_stop_after_completed_preview_immediately_invalidates_receipt(self):
        self.service.start('owner',self.scene,self.review);self.finish(complete=True)
        self.assertTrue(self.service.passed('owner',self.review['plan_id']))
        self.service.stop('owner')
        self.assertFalse(self.service.passed('owner',self.review['plan_id']))
        self.assertEqual(self.service.snapshot('owner')['state'],'COMPLETED')
        self.assertIsNotNone(self.service.snapshot('owner')['receipt'])

    def test_explicit_start_acquires_lease_and_keeps_it_during_review_not_snapshot(self):
        self.broker._lease_expires_at=0.
        self.broker.lease_ttl_s=.8
        self.service.snapshot('owner')
        self.assertFalse(self.broker.public_state('owner')['lease_owned'])
        self.service.start('owner',self.scene,self.review);self.finish(complete=True)
        time.sleep(1.)
        self.assertTrue(self.broker.public_state('owner')['lease_owned'])
        self.assertTrue(self.service.passed('owner',self.review['plan_id']))
        self.service.finish_execution('other');self.assertFalse(self.service.lease_stop.is_set())
        self.service.finish_execution('owner');self.assertTrue(self.service.lease_stop.is_set())
        time.sleep(.85)
        self.assertFalse(self.broker.public_state('owner')['lease_owned'])
        self.assertFalse(self.service.passed('owner',self.review['plan_id']))

    def test_foreign_live_lease_never_taken_over(self):
        self.broker._lease_expires_at=0.;self.broker.acquire_lease('other')
        from twinpulse_app.command_broker import BrokerError
        with self.assertRaisesRegex(BrokerError,'Another product session'):
            self.service.start('owner',self.scene,self.review)
        self.assertIsNone(self.service.worker);self.assertEqual(self.commands,[])

    def test_execution_receipt_uses_no_scene_io_but_retains_engine_stop_guards(self):
        self.service.start('owner',self.scene,self.review);self.finish(complete=True)
        def forbidden_reload():raise AssertionError('Full scene I/O on heartbeat')
        self.service.scene_loader=forbidden_reload
        self.assertTrue(self.service.execution_passed('owner',self.review['plan_id']))
        with self.assertRaisesRegex(AssertionError,'scene I/O'):
            self.service.passed('owner',self.review['plan_id'])
        self.service.stop('owner')
        self.assertFalse(self.service.execution_passed('owner',self.review['plan_id']))

    def test_execution_receipt_omits_ui_report_and_keeps_all_snapshot_lease_identity_fields(self):
        from unittest.mock import patch
        self.service.start('owner',self.scene,self.review);self.finish(complete=True)
        public=self.broker.public_state('owner');small=self.broker.execution_receipt_state('owner')
        for key in ('engine_connected','engine_session_id','stage_epoch','lease_owned'):
            self.assertEqual(small[key],public[key])
        for key,value in small['snapshot'].items():self.assertEqual(value,public['snapshot'][key])
        self.assertNotIn('operations',small);self.assertNotIn('engine_readiness',small)
        self.assertFalse(self.broker.execution_receipt_state('other')['lease_owned'])
        with patch.object(self.broker,'public_state',side_effect=AssertionError('UI report on watch')):
            self.assertTrue(self.service.execution_passed('owner',self.review['plan_id']))
            self.publish('paused',run_id=self.plan['plan_id'],position=[0.,0.,0.])
            self.assertFalse(self.service.execution_passed('owner',self.review['plan_id']))
            self.publish('paused',run_id=self.plan['plan_id'],position=[*self.review['goal'],0.])
            self.broker._lease_expires_at=0.
            self.assertFalse(self.service.execution_passed('owner',self.review['plan_id']))

    def test_bound_scene_fingerprint_avoids_reload_and_invalidates_changed_source(self):
        changed=[False];loads=[0]
        def guard():
            if changed[0]:raise ValueError('MISSION_ROOM_OR_LEDGER_CHANGED')
        def load():loads[0]+=1;return self.scene
        self.service.scene_guard_factory=lambda:guard;self.service.scene_loader=load
        self.service.start('owner',self.scene,self.review);self.finish(complete=True)
        self.assertEqual(loads,[1])
        self.assertTrue(self.service.passed('owner',self.review['plan_id']))
        self.assertEqual(loads,[1])
        changed[0]=True
        self.assertFalse(self.service.passed('owner',self.review['plan_id']))
        self.broker.register_engine('other','otherstage')
        self.assertFalse(self.service.execution_passed('owner',self.review['plan_id']))


if __name__=='__main__':unittest.main()
