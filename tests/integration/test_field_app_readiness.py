# SPDX-License-Identifier: Apache-2.0
"""Device-free admission/persistence tests; not installed UI/hardware acceptance."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from threading import RLock
import sys
import tempfile
import unittest
from uuid import uuid4
from tests.integration import test_physical_fleet_adapter as f
from tests.integration import test_physical_live_session as live_f
sys.path.insert(0,str(f.ROOT/'packages/twinpulse_robot_safety'))
from field_tests import checked_config,digest
from twinpulse_app.physical_fleet_adapter import PhysicalFleetAdapter,PhysicalFleetServices
from twinpulse_app.physical_live_session import PhysicalLiveSession,SCHEMA,reviewed_bundle
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.robot_adapters import instance_binding


class FieldAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.row=f.PhysicalFleetAdapterTests.row('Existing A','192.0.2.1');self.trace=[]
        registry=SimpleNamespace(snapshot=lambda:{'robots':[deepcopy(self.row)]})
        devices=SimpleNamespace(registry_service=SimpleNamespace(registry=registry),lock=RLock(),closed=False,contexts=[],
            diagnostics=f.Diagnostics('legacy',self.trace),readiness=f.Readiness('legacy',self.trace),controller=f.Controller('legacy',self.trace))
        def factory(*_):return PhysicalFleetServices(f.Diagnostics('d',self.trace),f.Readiness('r',self.trace),f.Controller('c',self.trace))
        self.pool=PhysicalFleetAdapter(devices,f.ROOT,self.tmp.name,services_factory=factory)
        self.addCleanup(self.pool.close);self.owner='fixture-owner'
        self.config=dict(schema='supervised-field-test-1.0',robot_id=self.row['id'],binding_sha256=instance_binding(self.row)['sha256'],
            footprint_radius_m=.12,sensor_x_m=0,sensor_y_m=0,sensor_yaw_rad=0,angle_sign=1,
            wheel_metres_per_tick=.00005,wheel_separation_m=.16,provenance='reference',axes_reviewed=True)

    def test_offline_config_versions_persist_without_creating_transport_or_authority(self):
        before=self.pool.snapshot()
        result=self.pool.save_field_config(self.row['id'],self.owner,self.config)
        self.assertEqual(result['config_sha256'],digest(self.config));self.assertFalse(result['motion_authority_restored'])
        self.assertEqual(self.pool.snapshot(),before)
        self.assertEqual(self.pool.field_config_for_view(self.row['id']),self.config)
        self.assertTrue((Path(self.tmp.name)/'physical-field-configs'/self.row['id']/(digest(self.config)+'.json')).is_file())
        bad=dict(self.config,binding_sha256='0'*64)
        with self.assertRaises(BrokerError):self.pool.save_field_config(self.row['id'],self.owner,bad)
        self.assertEqual(self.pool.field_config_for_view(self.row['id']),self.config)

    def test_old_arm_or_trial_epoch_cannot_be_resealed_after_stop(self):
        self.pool.check_connection(self.row['id'],self.owner,request_id=uuid4().hex,operation_id=uuid4().hex,project_id='p')
        entry=self.pool._cached(self.row['id']);sent=[]
        entry.services.live=SimpleNamespace(command=lambda *a,**k:sent.append((a,k)),close=lambda:None,closed=False,cleanup_confirmed=True,evidence=None)
        for action in ('field_arm','field_test'):
            with self.assertRaises(BrokerError) as error:
                self.pool.field_action(self.row['id'],self.owner,action,{'confirmed':True},connection_epoch=entry.connection_epoch,motion_epoch=uuid4().hex)
            self.assertEqual(error.exception.code,'fleet_motion_epoch_changed')
            with self.assertRaises(BrokerError):self.pool.field_action(self.row['id'],self.owner,action,{'confirmed':True})
        self.assertEqual(sent,[])
        entry.services.live=None

    def test_reviewed_source_bundle_includes_new_worker_not_just_pc_ui(self):
        _,_,members=reviewed_bundle(f.ROOT)
        self.assertIn('field_tests.py',members)

    def test_actual_pc_presence_fault_binds_first_published_trial_and_not_repeated(self):
        clock=[10.]
        session=PhysicalLiveSession(f.ROOT,self.tmp.name,identity=Path('unused'),known_hosts=Path('unused'),
            process_factory=lambda *_:self.fail('No SSH'),clock=lambda:clock[0])
        session.context=dict(operation_id=uuid4().hex,robot_id=uuid4().hex,project_id='p',connection_epoch=uuid4().hex,worker_sha256='a'*64)
        def beat(publications):
            data=dict(worker_sha256='a'*64,boot_id='b'*32,release_id='c'*64,
                field=dict(active_trial=dict(trial_id='trial-one',case='presence_gap',status='RUNNING',publications=publications)))
            session.receive(dict(schema=SCHEMA,**{k:session.context[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                sequence=session.sequence+1,kind='heartbeat',robot_monotonic_s=1.,data=data))
        beat(0);self.assertEqual(session.presence_gap_until,0.)
        beat(1);self.assertEqual(session.presence_gap_until,10.7)
        clock[0]=10.4;beat(2);self.assertEqual(session.presence_gap_until,10.7)
        session.pending_profile={'fixture':'data'};session.pending_field_setup=self.config;session.closing=True
        session.command=lambda *_args,**_kw:self.fail('Closing must not send restored settings before cleanup receipt')
        beat(3)
        self.assertTrue(session.closing);self.assertIsNotNone(session.pending_field_setup)

if __name__=='__main__':unittest.main()
