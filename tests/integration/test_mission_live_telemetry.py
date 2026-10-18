# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Additive source-bound diagnostic stream; no ROS startup or physical result."""
from copy import deepcopy
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from twinpulse_core.mission_telemetry import telemetry,checked_telemetry
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.physical_controller import PhysicalController
from twinpulse_app.session_history import valid_pc
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_mission_service import AutomaticMissionService
from twinpulse_app.goal_progress import describe_goal_job
from scripts.robot_source_identity import bundle_files


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.identity='a'*32
        self.context={'project_id':'room','session_id':'b'*32,'boot_id':'boot',
                      'release_id':'c'*64,'source_revision':'c'*64,'origin':'live_ros'}
        self.scope={'schema':'observed-mission-scope-7.0','project_id':'room','goal':{'room_revision':'d'*64}}
        self.mission=NS(context=self.context,last_evidence={'sample_s':10.,'room_from_map':[1.,2.,0.]},
            mission=NS(index=0,status='RUNNING'),current_pose_valid=True,pending=False,route_map=[[.1,.2]])
        self.resources={'schema':'task-resources-1.0','sample_s':10.,'source_age_s':.02,'voltage_v':12.,'motor_disabled':False}

    def value(self):return telemetry(self.mission,self.identity,self.scope,self.resources,10.05)

    def test_original_times_voltage_estimate_waypoint_and_missing_facts(self):
        value=self.value();self.assertEqual(checked_telemetry(value,self.identity,self.scope,self.context),value)
        self.assertEqual(value['battery']['sample_s'],10.)
        self.assertEqual(value['battery']['estimated_percent'],83.3)
        self.assertFalse(value['battery']['measured_capacity']);self.assertEqual(value['motor_load'],'UNSUPPORTED')
        self.assertEqual(value['next_waypoint']['xy_room'],[1.1,2.2])
        self.mission.current_pose_valid=False;self.resources['sample_s']=9.
        value=self.value();self.assertIsNone(value['battery']);self.assertIsNone(value['next_waypoint'])
        self.assertEqual(checked_telemetry(value,self.identity,self.scope),value)

    def test_scope_identity_source_shape_age_and_digest_tampering(self):
        value=self.value()
        for change in ('scope','identity','source','shape','age','voltage','percent','index','nan','hash'):
            v=deepcopy(value)
            if change=='scope':v['scope_sha256']='e'*64
            if change=='identity':v['session_id']='f'*32
            if change=='source':v['context']['boot_id']='other'
            if change=='shape':v['new_authority']=True
            if change=='age':v['battery']['sample_s']=9.
            if change=='voltage':v['battery']['voltage_v']=99.
            if change=='percent':v['battery']['estimated_percent']=100.
            if change=='index':v['next_waypoint']['index']=1
            if change=='nan':v['emitted_s']=float('nan')
            if change!='hash':v['revision']=canonical_sha256({k:x for k,x in v.items() if k!='revision'}) if change!='nan' else '0'*64
            else:v['revision']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):checked_telemetry(v,self.identity,self.scope,self.context)

    def test_owned_controller_replay_stop_race_and_exact_saved_row(self):
        import threading
        c=PhysicalController.__new__(PhysicalController);c.lock=threading.RLock();c.stop_requested=False
        c.mission_scope=self.scope;c.mission_context=self.context;c.job=self.identity
        c.adaptive_telemetry=None;c.telemetry_received_s=None;c.clock=lambda:20.
        saved=[];c._record=lambda kind,**data:saved.append((kind,data))
        value=self.value();c._receive_adaptive_telemetry(value)
        self.assertEqual(c.telemetry_received_s,20.)
        row={'schema':'control-session-1.0','job_id':self.identity,'event_index':1,'clock_domain':'pc_monotonic',
             't':20.,'kind':saved[0][0],'real_transport':False,'data':saved[0][1]}
        self.assertTrue(valid_pc(row,self.identity,adaptive=True,scope=self.scope))
        with self.assertRaisesRegex(ValueError,'CLOCK_OR_REPLAY'):c._receive_adaptive_telemetry(value)
        c.stop_requested=True;c._receive_adaptive_telemetry(value)
        self.assertEqual(len(saved),1)

    def test_app_receipt_expiry_terminal_and_clock_reversal_never_reuse_cached_values(self):
        with TemporaryDirectory() as td:
            clock=[20.];automatic=AutomaticDemoService(Path(td),'room')
            service=AutomaticMissionService(automatic,clock=lambda:clock[0])
            service.worker=NS(is_alive=lambda:True)
            service.job={'owner':'owner','started':20.,'state':'DRIVING','telemetry':self.value(),'telemetry_received_s':20.}
            current=service.snapshot('owner')['job']
            self.assertEqual(current['telemetry_status'],'RECENT_WORKER_RECEIPT')
            self.assertIn('83.3%',describe_goal_job(current)[0])
            for now,state in ((21.001,'DRIVING'),(19.9,'DRIVING'),(20.05,'MISSION_ARRIVED'),(20.05,'STOPPING')):
                clock[0]=now;service.job['state']=state;value=service.snapshot('owner')['job']
                self.assertIsNone(value['telemetry']);self.assertNotIn('83.3%',describe_goal_job(value)[0])
            service.worker=None;service.job=None;service.close();automatic.close()

    def test_source_bundle_includes_diagnostic_and_guard_dependencies(self):
        files=bundle_files(Path(__file__).resolve().parents[2])
        self.assertIn('twinpulse_core/mission_telemetry.py',files)
        self.assertIn('twinpulse_core/observed_progress.py',files)
