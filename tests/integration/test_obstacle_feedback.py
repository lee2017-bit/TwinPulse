# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary local evidence/transaction checks; never hardware acceptance."""
from copy import deepcopy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.integration.test_scene_edit_transaction import workflow,attach,claim,acknowledge
from twinpulse_app.scene_sensor_review import SceneSensorReview,checked_sensor_binding
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_core import canonical_sha256
from twinpulse_core.obstacle_feedback import checked_observation,project_observation,propose_translation


def observation():
    return dict(schema_version='obstacle-observation-1.0',provenance='SIMULATED_SENSOR',scans=[
        dict(stamp_ns=1000000000,frame_id='scan',angle_min_rad=-math.pi,
            angle_increment_rad=math.tau/360,range_min_m=.05,range_max_m=8,
            ranges_m=[None if i%5==0 else 2. for i in range(360)])])


class ObstacleFeedbackTests(unittest.TestCase):
    def test_projection_keeps_unknown_rays_and_uses_one_original_snapshot(self):
        value=observation();value['scans'].append({**value['scans'][0],'stamp_ns':2000000000,'ranges_m':[None]*359+[1.]})
        source=deepcopy(value);projected=project_observation(value,[0,0,0],.182)
        self.assertEqual(len(projected['points']),1)
        self.assertEqual(projected['reviewed_scan_index'],1)
        self.assertEqual(projected['scan_count'],2)
        self.assertFalse(projected['alignment_verified'])
        self.assertEqual(projected['unobserved_space'],'unknown')
        self.assertEqual(source,value)
        self.assertLessEqual(projected['free_count'],11)
        self.assertTrue(all(math.hypot(x,y)<1.1 for x,y,state in projected['cells']))

    def test_invalid_nonfinite_or_unbounded_data_is_rejected(self):
        for bad in (float('nan'),float('inf'),-1,900):
            value=observation();value['scans'][0]['ranges_m'][0]=bad
            with self.assertRaises(ValueError):checked_observation(value)
        with self.assertRaises(ValueError):project_observation(observation(),[float('nan'),0,0],.182)

    def test_wall_endpoints_cannot_fit_a_solid_box_around_the_sensor(self):
        source=observation()
        source['scans'][0]['ranges_m']=[1/max(abs(math.cos(-math.pi+i*math.tau/360)),abs(math.sin(-math.pi+i*math.tau/360))) for i in range(360)]
        projected=project_observation(source,[0,0,0],.182)
        box=dict(collision=True,shape=dict(type='box',dimensions_m=[2,2,1]),
            transform=dict(position_m=[1,0,.5],rotation_rpy_deg=[0,0,0]))
        result=propose_translation(projected,[box])
        self.assertEqual(result['status'],'HELD',result)

    def test_independent_shifted_box_supports_translation_not_photo_accuracy(self):
        # Independent authored sensor world: a room and a translated obstacle.
        # Do not create a reference from the estimated Twin under test.
        source=observation();ranges=[]
        for i in range(360):
            angle=-math.pi+i*math.tau/360;dx,dy=math.cos(angle),math.sin(angle)
            candidates=[4/max(abs(dx),abs(dy))]
            if dx>0:
                distance=1.8/dx;y=distance*dy
                if .1<=y<=.9:candidates.append(distance)
            if dy>0:
                distance=.1/dy;x=distance*dx
                if 1.8<=x<=2.2:candidates.append(distance)
            ranges.append(min(candidates))
        source['scans'][0]['ranges_m']=ranges
        projected=project_observation(source,[0,0,0],.182)
        box=dict(collision=True,shape=dict(type='box',dimensions_m=[.4,.8,1]),
            transform=dict(position_m=[1.6,.5,.5],rotation_rpy_deg=[0,0,0]))
        result=propose_translation(projected,[box])
        self.assertEqual(result['status'],'candidate',result)
        self.assertAlmostEqual(result['translation_xy_m'][0],.4)
        self.assertAlmostEqual(result['translation_xy_m'][1],0)
        self.assertEqual(result['fit']['observed_free_ray_contradictions'],0)
        self.assertFalse(result['fit']['semantic_identity_verified'])

    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.product=workflow(self.root);self.review=SceneSensorReview(self.product,self.root)
        self.product.scene_sensor_review=self.review;self.service=self.review.obstacles

    def tearDown(self):
        self.product.shutdown();self.temp.cleanup()

    def test_observations_survive_release_root_change_in_user_data(self):
        user_root=self.root/'user-data'
        first=SceneSensorReview(self.product,self.root/'release-one',observation_root=user_root)
        self.product.scene_sensor_review=first;self.review=first;self.service=first.obstacles
        imported=self.imported()['observations'][0]
        self.assertFalse((self.root/'release-one').exists())
        second=SceneSensorReview(self.product,self.root/'release-two',observation_root=user_root)
        self.assertEqual(second.obstacles.snapshot()['observations'][0]['sha256'],imported['sha256'])
        self.assertFalse((self.root/'release-two').exists())

    def test_read_only_catalog_does_not_take_scene_write_admission(self):
        from unittest.mock import patch
        self.imported()
        with patch.object(self.product,'_scene_edit_store',side_effect=BrokerError('scene_edit_unavailable','Engine command pending.',status=409)):
            self.assertEqual(len(self.service.snapshot()['observations']),1)
            with self.assertRaises(BrokerError):self.review.context()

    def test_catalog_captures_one_checked_state_without_second_history_replay(self):
        from unittest.mock import patch
        self.imported()
        with patch.object(self.review,'read_state',wraps=self.review.read_state) as capture, \
                patch.object(self.review,'context',side_effect=AssertionError('catalog must not replay context again')):
            result=self.service.snapshot()
        capture.assert_called_once_with()
        self.assertEqual(len(result['observations']),1)
        self.assertFalse(result['physical_authority'])

    def test_catalog_only_consumes_published_metadata_without_compile_fallback(self):
        from unittest.mock import patch
        self.imported()
        with patch.object(SceneChangeHistory,'effective',side_effect=AssertionError('metadata replay')), \
                patch.object(SceneChangeHistory,'replay',side_effect=AssertionError('metadata compile')):
            self.assertEqual(len(self.service.snapshot()['observations']),1)
            self.product._site_summary_cache=None
            with self.assertRaises(BrokerError) as failure:self.service.snapshot()
            self.assertEqual(failure.exception.code,'obstacle_metadata_not_ready')

    def test_catalog_rejects_same_size_same_mtime_source_and_sidecar_changes(self):
        import os
        store=self.product._application._project_store
        self.imported()
        paths=[store.path]
        history=self.product._scene_changes
        side=store.path.with_suffix('.scene-changes.json')
        side.write_text(json.dumps(history.to_dict()),encoding='utf-8');paths.append(side)
        for path in paths:
            original=path.read_bytes();stat=path.stat()
            # Any full-content change must be noticed, even when filesystem
            # metadata is deliberately identical and geometry was not changed.
            changed=original.replace(b'default',b'defauLt',1)
            self.assertNotEqual(changed,original);self.assertEqual(len(changed),len(original))
            try:
                path.write_bytes(changed);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
                with self.assertRaises(BrokerError):self.service.snapshot()
            finally:path.write_bytes(original)

    def test_catalog_pending_only_and_selection_changes_invalidate_publication(self):
        from dataclasses import replace
        from unittest.mock import patch
        self.imported();source=self.product._application.site_draft
        pending=deepcopy(source.progressive_twin);pending['unresolved'][0]['evidence']['note']='changed pending only'
        pending['sha256']=canonical_sha256({k:v for k,v in pending.items() if k!='sha256'})
        changed=replace(source,progressive_twin=pending)
        project=self.product._application._project
        with patch.object(self.product._application,'_project',replace(project,site_draft=changed)):
            with self.assertRaises(BrokerError) as failure:self.service.snapshot()
            self.assertEqual(failure.exception.code,'obstacle_metadata_not_ready')
        original=json.loads
        def switched(*args,**kwargs):
            result=original(*args,**kwargs);self.product._derived_revision='changed-during-disk-read';return result
        try:
            with patch('twinpulse_app.scene_sensor_review.json.loads',side_effect=switched):
                with self.assertRaises(BrokerError):self.service.snapshot()
        finally:self.product._derived_revision=None

    def test_candidate_compilation_releases_status_lock_and_rechecks_before_publish(self):
        from unittest.mock import patch
        from threading import Thread
        original=SceneChangeHistory.preview;available=[]
        def compile_candidate(history,*args,**kwargs):
            def read_status():
                acquired=self.product._lock.acquire(timeout=.2);available.append(acquired)
                if acquired:self.product._lock.release()
            worker=Thread(target=read_status);worker.start();worker.join(1)
            return original(history,*args,**kwargs)
        with patch.object(SceneChangeHistory,'preview',compile_candidate):
            result=self.preview()
        self.assertEqual(result['status'],'preview',result)
        self.assertEqual(available,[True])
        def changed_candidate(history,*args,**kwargs):
            result=original(history,*args,**kwargs)
            self.product._derived_revision='changed-during-local-compile'
            return result
        try:
            with patch.object(SceneChangeHistory,'preview',changed_candidate):
                stale=self.preview()
            self.assertEqual(stale['status'],'HELD',stale)
            self.assertNotIn('sensor_binding',stale)
        finally:self.product._derived_revision=None

    def body(self):
        context=self.review.context()
        return dict(expected_scene_revision=context['current_scene_revision'],expected_state_sha256=context['current_state_sha256'])

    def imported(self):
        return self.service.import_observation(dict(self.body(),observation=observation(),sensor_pose_m=[0,0,0],scan_height_m=.182),'owner')

    def preview(self):
        row=self.imported()['observations'][0]
        return self.service.preview(dict(self.body(),observation_id=row['id'],observation_sha256=row['sha256'],
            target_id='support',translation_xy_m=[.1,0]))

    def test_import_is_immutable_idempotent_and_never_changes_scene(self):
        before=self.review.context();one=self.imported();two=self.imported()
        self.assertEqual(len(two['observations']),1)
        self.assertEqual(one['observations'][0]['sha256'],two['observations'][0]['sha256'])
        self.assertEqual(before,self.review.context())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])
        reopened=SceneSensorReview(self.product,self.root).obstacles.snapshot()
        self.assertEqual(reopened['observations'],two['observations'])

    def test_raw_file_transport_and_server_pinned_numeric_types(self):
        source=json.dumps(observation());value=self.service.import_observation(dict(self.body(),
            observation={'json_text':source},sensor_pose_m=[0,0,0],scan_height_m=.182),'owner')
        import hashlib
        self.assertEqual(value['observations'][0]['source_file_sha256'],hashlib.sha256(source.encode()).hexdigest())
        preview=self.preview();operation,digest,binding=self.service.pinned_preview(preview['execution_id'],preview['preview_digest'])
        self.assertEqual(canonical_sha256(operation),digest)
        def js(value):
            if type(value) is float and value.is_integer():return int(value)
            if isinstance(value,dict):return {k:js(v) for k,v in value.items()}
            if isinstance(value,list):return [js(v) for v in value]
            return value
        # A browser can change numeric spellings; the exact host operation must
        # be loaded by opaque ID rather than accepting that replacement object.
        self.assertNotEqual(canonical_sha256(js(operation)),digest)
        self.assertEqual(binding,preview['sensor_binding'])

    def test_source_tamper_and_stale_delta_do_not_admit_apply(self):
        result=self.preview();self.assertEqual(result['status'],'preview',result)
        binding=checked_sensor_binding(result['sensor_binding'])
        store=self.product._application.scene_change_store();history=store.load()
        self.review.validate_apply(binding,result['operation'],store,history)
        changed=deepcopy(binding);changed['translation_xy_m'][0]=.3
        with self.assertRaisesRegex(ValueError,'PROOF_CHANGED'):
            self.review.validate_apply(changed,result['operation'],store,history)
        changed=deepcopy(binding);changed['mode']='surface_candidate'
        with self.assertRaisesRegex(ValueError,'PROOF_CHANGED'):
            self.review.validate_apply(changed,result['operation'],store,history)
        path=next((self.root/'artifacts/obstacle-feedback').rglob('*.json'))
        raw=json.loads(path.read_text());raw['source']['scans'][0]['ranges_m'][1]=1.
        raw['sha256']=canonical_sha256({k:v for k,v in raw.items() if k!='sha256'})
        path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'PROJECTION_CHANGED'):
            self.review.validate_apply(binding,result['operation'],store,history)

    def test_existing_transaction_ack_save_undo_and_observation_retention(self):
        result=self.preview();self.assertEqual(result['status'],'preview',result)
        before=self.review.context();attach(self.product)
        tx=self.product.scene_edit_transaction
        tx.start('owner',result['operation'],result['preview_digest'],sensor_binding=result['sensor_binding'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command)
        tx.worker.join(4)
        self.assertEqual(tx.value['state'],'COMMITTED',tx.value.get('error'))
        after=self.review.context();self.assertNotEqual(before['current_state_sha256'],after['current_state_sha256'])
        exact,digest,binding=self.service.pinned_preview(result['execution_id'],result['preview_digest'])
        previous_command=tx.value['command_id']
        duplicate=tx.start('owner',exact,digest,sensor_binding=binding)
        self.assertEqual(duplicate['state'],'COMMITTED')
        self.assertEqual(duplicate['command_id'],previous_command)
        store=self.product._application.scene_change_store();history=store.load()
        undo=history.preview(store.source,operation_id='undo_observation',mode='undo')
        tx.start('owner',undo['operation'],undo['preview_digest'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(4)
        self.assertEqual(tx.value['state'],'COMMITTED')
        self.product.snapshot()
        self.assertEqual(self.service.snapshot()['observations'][0]['sha256'],result['observation_sha256'])
        state=store.load().effective(store.source);original=SceneChangeHistory.empty('default',store.source).effective(store.source)
        self.assertEqual(state.plan,original.plan)
        # Four real local history entries (Apply/Undo twice) must not turn a
        # subsequent read-only catalog into a history replay under status lock.
        result=self.preview()
        tx.start('owner',result['operation'],result['preview_digest'],sensor_binding=result['sensor_binding'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(4)
        undo=store.load().preview(store.source,operation_id='undo_second_observation',mode='undo')
        tx.start('owner',undo['operation'],undo['preview_digest'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(4)
        self.assertEqual(tx.value['state'],'COMMITTED')
        self.assertEqual(len(store.load().operations),4)
        self.product.snapshot()  # the strict publisher, not the metadata GET
        from unittest.mock import patch
        with patch.object(SceneChangeHistory,'effective',side_effect=AssertionError('metadata replay')), \
                patch.object(SceneChangeHistory,'replay',side_effect=AssertionError('metadata compile')):
            self.assertEqual(len(self.service.snapshot()['observations']),1)
            side=store.path;raw=side.read_bytes()
            try:
                side.unlink()
                with self.assertRaises(BrokerError) as failure:self.service.snapshot()
                self.assertEqual(failure.exception.code,'scene_sensor_stale')
            finally:side.write_bytes(raw)


if __name__=='__main__':unittest.main()
