# SPDX-License-Identifier: Apache-2.0
"""Offline App-to-worker contract, not user/hardware acceptance."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from tests.integration import test_robot_fleet as fixture
from twinpulse_app.robot_fleet import RobotFleet
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.sim_fleet_navigation import checked_scene_geometry


class PhysicalPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=100.
        self.fleet=RobotFleet(fixture.Broker(),Path(self.tmp.name),clock=lambda:self.now,wall=lambda:self.now)
        self.fleet.physical=SimpleNamespace(navigate=Mock())
        self.row=self.fleet._robot('physical','Robot',[0,0,0],kind='physical')
        self.row.update(operation_id='operation',connection_epoch='connection',display_pose={'visual_epoch':'visual'})
        self.fleet.robots['physical']=self.row
        self.binding=('engine','stage','revision')
        self.scene=dict(binding=self.binding,produced_at=100.,geometry=dict(epoch=1,bounds=[0,0,5,5],
            targets=[dict(id='bed1',kind='bed',label='bed',bounds=[1.,3.,2.,4.5])],obstacles=[[1.,3.,2.,4.5]]))
        self.fleet.navigation_scene=deepcopy(self.scene)
        self.anchor=dict(key=('operation','connection','tracking','visual',self.binding),origin=[0.,0.,0.])
        self.estimate=dict(scene_revision='revision',visual_epoch='visual',position_m=[2.5,1.,0.])
        self.tracking=dict(status='ESTIMATED',epoch='tracking',pose=[0.,0.,0.],sample_s=100.)
        self.fleet.physical_navigation_reviews['physical']=('connection','visual','tracking')
    def tearDown(self):self.fleet.close();self.tmp.cleanup()
    def send(self):
        return self.fleet._physical_destination('physical','owner','request','bed','Go to bed',{'context_id':'context'},
            self.scene,self.anchor,self.estimate,self.tracking,'connection','motion')
    def test_real_adapter_task_carries_estimated_target_anchor_native_epoch_and_context(self):
        self.send();kw=self.fleet.physical.navigate.call_args.kwargs
        self.assertEqual(kw['payload']['route']['tracking_epoch'],'tracking')
        self.assertEqual(kw['payload']['route']['anchor_world'],[2.5,1.,0.])
        self.assertEqual(kw['request_twin_context']['context_id'],'context')
        self.assertEqual(kw['motion_epoch'],'motion');self.assertTrue(kw['guard']())
        self.now+=1. # GPU frame delay alone is not a physical input lease.
        self.assertTrue(kw['guard']())
        self.fleet.navigation_scene['geometry']['epoch']=2;self.assertFalse(kw['guard']())
    def test_stale_scene_new_connection_missing_review_or_changed_native_epoch_reject(self):
        self.now+=.51
        with self.assertRaises(BrokerError):self.send()
        self.now=100.;self.fleet.physical_navigation_reviews.clear()
        with self.assertRaises(BrokerError):self.send()
        self.fleet.physical_navigation_reviews['physical']=('connection','visual','tracking');self.tracking['epoch']='new'
        with self.assertRaises(BrokerError):self.send()
        self.fleet.physical.navigate.assert_not_called()
    def test_geometry_validator_rejects_unsafe_unbounded_payload(self):
        value=deepcopy(self.scene['geometry']);self.assertEqual(checked_scene_geometry(value),value)
        value['obstacles']=[[0,0,float('nan'),1]];self.assertIsNone(checked_scene_geometry(value))


class CaptureLifecycleTests(unittest.TestCase):
    def test_capture_lifecycle_is_not_inside_bounded_trajectory_history(self):
        import ast
        root=Path(__file__).resolve().parents[2]
        tree=ast.parse((root/'scripts/twinpulse_engine_host.py').read_text(encoding='utf-8'))
        limited=[n for n in ast.walk(tree) if isinstance(n,ast.If) and 'len(trajectory)' in ast.unparse(n.test)]
        self.assertEqual(len(limited),1)
        names={n.func.id for n in ast.walk(limited[0]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertNotIn('start_capture',names)
        self.assertNotIn('update_capture',names)


if __name__=='__main__':unittest.main()
