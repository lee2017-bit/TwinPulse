# SPDX-License-Identifier: Apache-2.0
"""Supplementary review lifecycle tests; no device or runtime acceptance."""
import json,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock,patch
from twinpulse_app.environment_alignment_review import AlignmentReview
from twinpulse_app.library_asset_store import atomic_json
from twinpulse_app.command_broker import BrokerError
from twinpulse_core.environment_alignment import body_points,wall_references,reference_check
from twinpulse_core.revisions import canonical_sha256
from tests.integration.test_environment_alignment import room,samples

class AlignmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=room();self.ctx=dict(project_id='project',scene_revision='a'*64,source_sha256=self.env['source_sha256'],environment_sha256=canonical_sha256(self.env))
        self.workspace=SimpleNamespace(root=Path(self.tmp.name),workflow=SimpleNamespace(_broker=SimpleNamespace(project_id='project')))
        self.fleet=Mock();self.fleet.devices=None
        self.review=AlignmentReview(self.workspace,self.fleet);self.review.context=lambda:(self.env,self.ctx)
        self.raw=samples(self.env,[1.3,1.1,.22]);self.tf=[-.032,0,0];self.identity='b'*32
        self.frame=dict(identity=['s',1,'raw'],source_owner=['sim','op','epoch'],points=self.raw,stamp=time.time()*1000,control_state='READY',height_m=.182)
    def result(self):
        return dict(schema='environment-alignment-review-1.0',job_id=self.identity,context=self.ctx,status='GEOMETRIC_REVIEW',source='CURRENT',
            match=dict(body_pose=[1.3,1.1,.22]),sensor_height_m=.182,physical_authority=False)
    def stage_saved(self):
        folder=self.review.root/self.identity;folder.mkdir(parents=True)
        inputs=dict(frames=[self.frame],extrinsic=self.tf,angle_sign=1)
        result=self.result();result['input_bundle_sha256']=canonical_sha256(inputs)
        atomic_json(folder/'input.json',inputs);atomic_json(self.review.saved_path,result)
        self.review.result=deepcopy(result);self.review.saved_result=deepcopy(result)
        self.review.review_digest=canonical_sha256(result);self.review.job=dict(job_id=self.identity,status='SAVED')
        return result
    def test_cancel_revokes_before_a_late_publish_and_cold_show(self):
        result=self.stage_saved();self.review.action(dict(action='cancel',request_id='cancel'),'owner')
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED|CANCELLED'):
            self.review.publish(result,body_points(self.raw,self.tf),self.tf,.182,self.ctx,frame=self.frame,persist=True)
        self.assertIsNone(self.review.packet);self.assertEqual(self.review.job['status'],'CANCELLED')
        cold=AlignmentReview(self.workspace,self.fleet);cold.context=self.review.context
        self.assertTrue(cold.revoked);self.assertEqual(cold.job['status'],'CANCELLED')
        with self.assertRaises(BrokerError):cold.action(dict(action='show',request_id='show',review_digest=cold.review_digest),'owner')
    def test_hide_show_preserves_paired_latest_packet_and_cold_uses_original_pair(self):
        result=self.stage_saved();latest=deepcopy(result);latest['match']['body_pose']=[1.4,1.2,.3]
        self.review.result=latest;self.review.make_packet(latest,body_points(self.raw,self.tf),self.tf,.182,self.frame)
        paired=deepcopy(self.review.packet)
        self.review.action(dict(action='hide',request_id='hide'),'owner')
        self.review.action(dict(action='show',request_id='show',review_digest=self.review.review_digest),'owner')
        self.assertEqual(self.review.packet,paired)
        cold=AlignmentReview(self.workspace,self.fleet);cold.context=self.review.context
        self.assertFalse(cold.visible);self.assertIsNone(cold.packet)
        cold.action(dict(action='show',request_id='show',review_digest=cold.review_digest),'owner')
        self.assertEqual(cold.packet['source'],'SAVED');self.assertEqual(cold.packet['body_pose'],result['match']['body_pose'])
        self.assertFalse(cold.packet['physical_authority'])
    def test_saved_input_tamper_cannot_show(self):
        self.stage_saved();path=self.review.root/self.identity/'input.json';data=json.loads(path.read_bytes());data['frames'][0]['points'][0][0]+=1;atomic_json(path,data)
        with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):self.review.action(dict(action='show',request_id='show',review_digest=self.review.review_digest),'owner')
        self.assertFalse(self.review.visible)
    def test_initial_tf_change_holds_without_publishing(self):
        self.review.job=dict(job_id=self.identity,status='CHECKING');self.review.current_frame=Mock(side_effect=[
            (self.frame,self.tf,1,'basis'),(dict(self.frame,identity=['s',2,'raw2']),[.1,0,0],1,'basis')])
        ref=wall_references(self.env)[0];reference=reference_check(self.env,ref['id'],ref['length_m'],'SIM_ONLY')
        self.review.run(dict(source='CURRENT',robot_id='sim',height_m=.182),self.env,self.ctx,[1.3,1.1,.22],reference,'owner',self.identity)
        self.assertEqual(self.review.job['status'],'HELD');self.assertIn('INITIAL_TF_CHANGED',self.review.job['reason']);self.assertIsNone(self.review.packet)
        self.fleet.assert_not_called()
    def test_off_or_changed_scene_hides_current_overlay(self):
        result=self.stage_saved();self.review.make_packet(result,body_points(self.raw,self.tf),self.tf,.182,self.frame);self.review.visible=True
        broker=self.workspace.workflow._broker;broker.supervisor_state=lambda:dict(engine_connected=True,snapshot=dict(project_id='project',applied_revision='a'*64))
        self.review.row=Mock(side_effect=ValueError('ALIGNMENT_FRESH_SCAN_REQUIRED'));self.assertIsNone(self.review.overlay())
        self.review.row.assert_called_once();broker.supervisor_state=lambda:dict(engine_connected=True,snapshot=dict(project_id='project',applied_revision='c'*64))
        self.assertIsNone(self.review.overlay())
    def test_current_scan_uses_actual_keyword_only_fleet_snapshot_contract(self):
        row=dict(robot_id='sim',kind='sim',connection_state='CONNECTED',lidar_state='STREAMING',scan=dict(captured_at_ms=time.time()*1000))
        class Fleet:
            def snapshot(self,*,refresh_physical=True):return dict(robots=[row])
        self.review.fleet=Fleet();self.assertEqual(self.review.row('sim','owner'),row)
