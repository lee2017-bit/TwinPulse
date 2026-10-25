# SPDX-License-Identifier: Apache-2.0
"""Supplementary tests, never installed/hardware acceptance."""
from copy import deepcopy
import math,tempfile,time,unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock,patch
from tests.integration import test_r5_product_api
from twinpulse_app.environment_survey_review import EnvironmentSurveyReview
from twinpulse_app.library_asset_store import atomic_json
from twinpulse_core.environment_alignment import wall_references
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.environment_overlays import add_overlay
from twinpulse_core.registered_navigation import intersect_model_free
from twinpulse_app.environment_survey_binding import validate_survey_apply
from twinpulse_app.task_collection import TaskCollection
from twinpulse_app.scene_edit_transaction import SceneEditTransaction
from twinpulse_app.robot_fleet import RobotFleet
from tests.integration.test_environment_alignment import room,samples
from tests.integration.test_environment_survey import collection_frames
from tests.integration.test_physical_robot_tasks import row as physical_row
from tests.integration.test_environment_overlays import overlay

class SurveyReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=room();self.ctx=dict(project_id='project',scene_revision='a'*64,source_sha256=self.env['source_sha256'],environment_sha256=canonical_sha256(self.env))
        self.workspace=SimpleNamespace(root=Path(self.tmp.name)/'environment-imports',workflow=SimpleNamespace(_lock=RLock(),_broker=SimpleNamespace(project_id='project')))
        self.fleet=SimpleNamespace(physical=SimpleNamespace(state_root=Path(self.tmp.name)/'devices'),clock=time.monotonic)
        self.review=EnvironmentSurveyReview(self.workspace,self.fleet);self.review.context=lambda:(self.env,self.ctx)
        self.identity='b'*32;self.review.job=dict(job_id=self.identity,status='CHECKING',reason=None)
    def body(self):
        ref=wall_references(self.env)[0]
        return dict(source='CURRENT',robot_id='sim',initial_pose=[1.3,1.1,.22],reference_id=ref['id'],reference_length_m=ref['length_m'],reference_basis='SIM_ONLY',height_m=.182,compare_current_reviewed=False)
    def run_current(self):
        frames=collection_frames(self.env,[[1.3,1.1,.22]]*3)
        for f in frames:f['stamp']=time.time()*1000
        iterator=iter(frames);self.review.current_frame=lambda robot:deepcopy(next(iterator))
        self.review.run(self.body(),self.env,self.ctx,self.identity)
        self.assertEqual(self.review.job['status'],'GEOMETRIC_REVIEW',self.review.job)
        return frames
    def test_current_review_requires_explicit_use_and_cold_restores_no_registration(self):
        frames=self.run_current();self.assertIsNone(self.review.registration);self.assertFalse(self.review.visible)
        self.review.current_frame=lambda robot:deepcopy(frames[-1])
        self.review.action(dict(action='use_registration',request_id='use',review_digest=self.review.digest),'owner')
        self.assertIsNotNone(self.review.registration)
        cold=EnvironmentSurveyReview(self.workspace,self.fleet);cold.context=self.review.context
        self.assertEqual(cold.job['status'],'SAVED');self.assertIsNone(cold.registration);self.assertFalse(cold.visible)
    def test_changed_source_or_pose_cannot_activate_registration(self):
        frames=self.run_current()
        for mutation in ('owner','pose'):
            f=deepcopy(frames[-1])
            if mutation=='owner':f['source_owner']=['sim','different-operation','conn']
            else:f['native_pose'][0]+=.02
            self.review.current_frame=lambda robot:f
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.review.action(dict(action='use_registration',request_id='use',review_digest=self.review.digest),'owner')
        self.assertIsNone(self.review.registration)
    def test_cancel_and_changed_result_cannot_show(self):
        self.run_current()
        with self.assertRaisesRegex(ValueError,'ONLY_PENDING'):self.review.action(dict(action='cancel',request_id='cancel'),'owner')
        self.review.job['status']='CHECKING';self.review.action(dict(action='cancel',request_id='cancel'),'owner')
        with self.assertRaises(ValueError):self.review.action(dict(action='show',request_id='show',review_digest=self.review.digest),'owner')
        self.assertFalse(self.review.visible)
    def test_fault_or_odom_frame_change_rejects_session_transform(self):
        value=physical_row();self.fleet.snapshot=lambda:dict(robots=[value]);frame=self.review.current_frame(value['robot_id'])
        self.review.registration=dict(context=self.ctx,pin=self.review.source_pin(frame),robot_id=value['robot_id'],world_from_native=[1.,1.,0.],job_id=self.identity)
        value['telemetry_age_ms']=200;value['pose_age_ms']=200;value['_physical_projection_at']=time.monotonic()
        self.assertEqual(self.review.visual_pose(value,self.ctx['scene_revision'])['position_m'][:2],[1.,1.])
        self.fleet.clock=lambda:value['_physical_projection_at']+.6
        self.assertIsNone(self.review.visual_pose(value,self.ctx['scene_revision']))
        self.fleet.clock=time.monotonic
        self.assertIsNone(self.review.visual_pose(value,'different-scene'))
        self.assertEqual(self.review.registration_for(value)['world_pose'][:2],[1.,1.])
        value['task_local_state']['pose_valid']=False
        self.assertIsNone(self.review.visual_pose(value,self.ctx['scene_revision']))
        with self.assertRaisesRegex(ValueError,'ODOMETRY_INVALID'):self.review.registration_for(value)
        value['task_local_state']['pose_valid']=True;value['pose']['frame_id']='different'
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.review.registration_for(value)
    def test_physical_current_accessor_uses_original_native_packet_and_rejects_old_age(self):
        value=physical_row();self.fleet.snapshot=lambda:dict(robots=[value])
        frame=self.review.current_frame(value['robot_id'])
        self.assertEqual(frame['source_kind'],'PHYSICAL');self.assertEqual(frame['source_sha256'],value['task_local_observation']['sha256'])
        self.assertEqual(frame['native_pose'][2],value['pose']['yaw_rad'])
        value['task_observation_age_ms']=1001
        with self.assertRaisesRegex(ValueError,'STALE'):self.review.current_frame(value['robot_id'])
    def test_physical_current_accessor_does_not_erase_slow_snapshot_time(self):
        value=physical_row();value['timing_values']=dict(value['timing_values'],native_receipt_ms=500)
        now=[1.];self.fleet.clock=lambda:now[0]
        def snapshot():now[0]+=.4;return dict(robots=[value])
        self.fleet.snapshot=snapshot
        with self.assertRaisesRegex(ValueError,'STALE'):self.review.current_frame(value['robot_id'])
    def test_model_and_measurement_intersection_preserves_unknown_rotated_and_thin_obstacle(self):
        local=[[.05,.05,'free',0,0,0,0],[.15,.05,'unknown',0,0,0,0]]
        world=[[(x+.5)*.1,(y+.5)*.1,'free',0,0,0,0] for x in range(-3,5) for y in range(-3,5)]
        self.assertEqual(intersect_model_free(local,world,[0,0,.4])[0][2],'free')
        next(r for r in world if math.dist(r[:2],[.05,.15])<1e-8)[2]='occupied'
        checked=intersect_model_free(local,world,[0,0,.4])
        self.assertEqual(checked[0][2],'unknown');self.assertEqual(checked[1][2],'unknown')
    def test_fleet_projection_pins_time_before_potentially_slow_snapshot(self):
        now=[1.]
        def snapshot():now[0]+=.5;return dict(robots=[{}])
        fake=SimpleNamespace(clock=lambda:now[0],devices=SimpleNamespace(registry_service=SimpleNamespace(registry=SimpleNamespace(registration_snapshot=lambda:dict(robots=[])))),physical=SimpleNamespace(snapshot=snapshot))
        _,rows=RobotFleet._physical_values(fake)
        self.assertEqual(rows[0]['_fleet_projection_began_at'],1.);self.assertEqual(now[0],1.5)

class SurveyBindingTests(unittest.TestCase):
    def test_new_binding_capability_is_sticky_and_rejects_older_reader(self):
        from twinpulse_app.release_contract import DATA_CONTRACT,check_data_epoch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);transaction=SceneEditTransaction.__new__(SceneEditTransaction)
            transaction.workflow=SimpleNamespace(_application=SimpleNamespace(_project_store=SimpleNamespace(path=root/'projects'/'project'/'project.json')))
            binding=dict(schema_version='environment-survey-binding-1.0')
            transaction._require_sensor_capabilities(binding,None)
            raw=(root/'data-compatibility.json').read_bytes()
            self.assertEqual(check_data_epoch(root),1)
            older=dict(DATA_CONTRACT,read_capabilities=['environment-static-1.1'])
            with self.assertRaisesRegex(ValueError,'CAPABILITY_REQUIRES'):check_data_epoch(root,older)
            transaction._require_sensor_capabilities(None,binding)
            self.assertEqual((root/'data-compatibility.json').read_bytes(),raw)
            with patch('twinpulse_app.release_contract.atomic_json',side_effect=OSError('marker failed')):
                with self.assertRaisesRegex(OSError,'marker failed'):transaction._require_sensor_capabilities(binding)

    def test_original_pose_mutation_is_rejected_again_after_engine_ack_before_save(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);env=room();identity='a'*32;job_id='b'*32;rev='c'*64;events=[]
            capture=dict(source_sha256=env['source_sha256'],meters_per_unit=1.,source_up_axis='Z',units_basis='selected_for_sim',environment_sha256=canonical_sha256(env),scene_revision=rev)
            for i,p in enumerate([[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6]],1):
                scan=dict(source='isaac_usd_surface_rays',point_frame='sensor_local',points=samples(env,p),stream_id='stream',frame_sequence=i,captured_at_ms=1000.+i)
                obs=dict(robot_id='robot',operation_id='op',connection_epoch='conn',binding=['engine','stage',rev],scan=scan,body_pose=dict(position_m=p))
                atomic_json(root/'robot-tasks'/identity/f'observation-{i:04d}.json',obs)
                events.append(dict(kind='observation',scan_sha256=canonical_sha256(scan),pose=obs['body_pose'],scan_identity=['stream',i,1000.+i]))
            job=dict(task_id=identity,project_id='project',robot_id='robot',robot_kind='sim',operation_id='op',connection_epoch='conn',state='PARTIAL',reason='BOUNDED',environment_source=capture,scene_binding=['engine','stage',rev],events=events)
            job['record_sha256']=canonical_sha256(job);atomic_json(root/'robot-tasks'/identity/'task.json',job)
            collection=TaskCollection(root/'robot-tasks','project').load(identity)
            candidate=dict(candidate_id='Residual_'+'d'*20,position_xy_m=[1.3,1.3],observed_extent_xy_m=[.35,.3],uncertainty_m=.2)
            context=dict(schema_version='scene-sensor-context-1.0',project_id='project',input_revision='1'*64,source_sha256='2'*64,current_scene_revision=rev,current_state_sha256='3'*64,physical_authority=False)
            result=dict(status='GEOMETRIC_REVIEW',context=dict(scene_revision=rev,environment_sha256=canonical_sha256(env)),source='TASK',frames_sha256=canonical_sha256(collection['frames']),obstacle_candidates=[candidate])
            folder=root/'environment-imports'/'survey-reviews'/job_id;atomic_json(folder/'collection.json',collection);atomic_json(folder/'result.json',result)
            operation=dict(tool_call=dict(tool='import_environment',arguments=dict(environment=add_overlay(env,overlay()))))
            binding=dict(schema_version='environment-survey-binding-1.0',policy='review_survey_obstacle',job_id=job_id,context=context,collection_sha256=EnvironmentSurveyReview.file_sha(folder/'collection.json'),result_sha256=EnvironmentSurveyReview.file_sha(folder/'result.json'),candidate_id=candidate['candidate_id'],preview_sha256=canonical_sha256(operation),physical_authority=False)
            history=SimpleNamespace(project_id='project',effective=lambda source:SimpleNamespace(site=SimpleNamespace(scene=SimpleNamespace(environment=env))))
            store=SimpleNamespace(path=root/'scene-changes.json',project_id='project',source=None,apply=Mock())
            adapter=SimpleNamespace(context=lambda *args:context)
            validate_survey_apply(adapter,binding,operation,store,history) # admission
            path=root/'robot-tasks'/identity/'observation-0003.json';obs['body_pose']['position_m'][0]+=.3;atomic_json(path,obs)
            tx=object.__new__(SceneEditTransaction);tx.trace=None;tx.value=dict(sensor_binding=binding,operation=operation,before_history={},preview_digest=binding['preview_sha256'])
            adapter.validate_apply=lambda b,o,s,h:validate_survey_apply(adapter,b,o,s,h)
            tx.workflow=SimpleNamespace(scene_sensor_review=adapter)
            with patch('twinpulse_app.scene_edit_transaction.SceneChangeHistory.from_dict',return_value=history):
                with self.assertRaisesRegex(ValueError,'EVENT_POSE'):tx._commit(store,history)
            store.apply.assert_not_called()

if __name__=='__main__':unittest.main()
