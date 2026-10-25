# SPDX-License-Identifier: Apache-2.0
"""Fake completion/real App and parser. No live model or hardware acceptance."""
from contextlib import contextmanager
from copy import deepcopy
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import sys
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_core.environment_photo import VERSION,checked_photo_candidates
from twinpulse_app.environment_photo_review import EnvironmentPhotoReview
from twinpulse_app.single_photo_scope import SinglePhotoLedger
from twinpulse_app.library_asset_store import atomic_json
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.nebius_pipeline import ChatCompletion
from tests.integration import test_environment_model_move as fixture


def output():
    return dict(schema_version=VERSION,candidates=[dict(id='Candidate_1',kind='basket',label='Basket',confidence=.8,
        bbox=[.1,.2,.4,.7],description='A visible basket; exact scene identity is unverified.')],explanation='Review duplicates and place the center explicitly.')


class EnvironmentPhotoTests(unittest.TestCase):
    @contextmanager
    def workspace(self,*,value=None,hook=None):
        with fixture.EnvironmentModelMoveTests().workspace() as (space,app,workflow,draft,provider,calls):
            provider.observer_model_id='supplementary-fake-observer';provider.stage_output_token_caps['observer']=1000
            deferred=SimpleNamespace(start=lambda:None,is_alive=lambda:False)
            async def complete(stage,body,token,config):
                calls.append(deepcopy(body))
                if hook:hook(space,app,workflow,draft,token)
                return ChatCompletion('fake-response',provider.observer_model_id,json.dumps(value if value is not None else output()),'stop',{},'fake-attempt')
            provider._complete_stage=complete
            with patch('twinpulse_app.environment_photo_review.Thread',return_value=deferred):
                yield space,app,workflow,draft,provider,calls

    def image(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(40,30),(30,40,50)).save(stream,format='PNG')
        return dict(name='fixture.png',bytes_base64=base64.b64encode(stream.getvalue()).decode())

    def start(self,space,*,consent=True,request='photo-request'):
        state=space.snapshot('owner')
        return space.action(dict(action='photo_analyze',request_id=request,expected_scene_revision=state['scene_revision'],photo=self.image(),consent=consent),'owner')

    def complete_job(self,space):
        self.start(space);space.photos._run(space.photos.job,space.photos.token)
        self.assertEqual(space.photos.job['status'],'ready',space.photos.job['error'])
        return space.photos.job

    def preview_body(self,space,job,request='candidate-preview'):
        return dict(action='photo_candidate_preview',request_id=request,expected_scene_revision=space.snapshot('owner')['scene_revision'],
            obstacle=dict(kind='basket',label='Reviewed basket',position_xy_m=[1.3,1.3],dimensions_m=[.35,.3,.4],yaw_deg=0.,uncertainty_m=.2),
            candidate_ref=dict(job_id=job['job_id'],candidate_id='Candidate_1'),duplicate_reviewed=True)

    def test_candidate_contract_rejects_metric_fields_nan_inverted_or_duplicate_regions(self):
        for change in ('metric','nan','inverted','duplicate','kind','four'):
            value=output()
            if change=='metric':value['candidates'][0]['position_m']=[1,1,0]
            if change=='nan':value['candidates'][0]['confidence']=float('nan')
            if change=='inverted':value['candidates'][0]['bbox']=[.5,0,.1,1]
            if change=='duplicate':value['candidates']*=2
            if change=='kind':value['candidates'][0]['kind']='sofa'
            if change=='four':value['candidates']*=4
            with self.subTest(change=change),self.assertRaises(ValueError):checked_photo_candidates(value)
        empty=output();empty['candidates']=[];checked_photo_candidates(empty)

    def test_consent_is_required_before_storage_or_dispatch(self):
        with self.workspace() as (space,app,w,d,p,calls):
            with self.assertRaisesRegex(ValueError,'CONSENT'):self.start(space,consent=False)
            self.assertFalse(space.photos.root.exists());self.assertFalse(calls)

    def test_one_observer_only_image_and_no_mesh_metric_or_automatic_preview(self):
        with self.workspace() as (space,app,w,d,p,calls):
            original=app.scene_change_store().load();job=self.complete_job(space)
            self.assertEqual(len(calls),1);body=calls[0]
            self.assertEqual(body['model'],p.observer_model_id)
            self.assertEqual(body['response_format']['json_schema']['name'],'twinpulse_environment_photo')
            text=body['messages'][-1]['content'][0]['text'];self.assertEqual(json.loads(text),dict(existing_props=[]))
            self.assertEqual(body['messages'][-1]['content'][1]['type'],'image_url')
            self.assertEqual(app.scene_change_store().load(),original);self.assertFalse(space.previews)
            saved=json.loads((space.photos.root/job['job_id']/'job.json').read_text())
            self.assertEqual(saved['status'],'ready');self.assertNotIn('_owner',saved)
            for _ in range(3):self.assertEqual(space.snapshot('owner')['photo_proposal']['status'],'ready')
            self.assertEqual(len(calls),1)

    def test_same_request_and_cold_reopen_never_dispatch_again(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);identity=job['job_id'];self.start(space)
            self.assertEqual(space.photos.job['job_id'],identity);self.assertEqual(len(calls),1)
            cold=EnvironmentPhotoReview(space);self.assertEqual(cold.job['job_id'],identity);self.assertFalse(cold.active())
            space.photos=cold;self.start(space)
            self.assertEqual(len(calls),1);self.assertEqual(cold.job['status'],'ready')

    def test_changed_photo_same_request_cannot_reuse_authorization(self):
        with self.workspace() as (space,app,w,d,p,calls):
            self.complete_job(space);body=dict(action='photo_analyze',request_id='photo-request',photo=self.image(),consent=True,
                expected_scene_revision=space.snapshot('owner')['scene_revision']);body['photo']['name']='different.png'
            with self.assertRaisesRegex(ValueError,'REQUEST_CHANGED'):space.action(body,'owner')
            self.assertEqual(len(calls),1)

    def test_interrupted_job_is_failed_cold_without_restart_or_ready(self):
        with self.workspace() as (space,app,w,d,p,calls):
            self.start(space);cold=EnvironmentPhotoReview(space)
            self.assertEqual(cold.job['status'],'failed');self.assertIn('unknown',cold.job['error'])
            space.photos=cold;self.start(space);self.assertEqual(cold.job['status'],'failed');self.assertFalse(calls)

    def test_explicit_candidate_preview_uses_exact_photo_and_pinned_adoption(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);body=self.preview_body(space,job);state=space.action(body,'owner');preview=state['preview']
            evidence=preview['operation']['tool_call']['arguments']['environment']['overlays'][0]['evidence']
            self.assertEqual(evidence,job['photo']);self.assertFalse(evidence['alignment_verified'])
            exact,_=space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner')
            self.assertEqual(exact,preview['operation']);self.assertFalse(app.scene_change_store().path.exists())
            history=app.scene_change_store().apply(preview['operation'],preview['preview_digest']);w._publish_scene_change(app.scene_change_store(),history)
            with self.assertRaisesRegex(ValueError,'ALREADY_REPRESENTED'):space.action(self.preview_body(space,job,request='duplicate'),'owner')

    def test_user_duplicate_confirmation_kind_and_current_revision_are_required(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space)
            for change in ('duplicate','kind','revision','id'):
                body=self.preview_body(space,job)
                if change=='duplicate':body['duplicate_reviewed']=False
                if change=='kind':body['obstacle']['kind']='bag'
                if change=='revision':body['expected_scene_revision']='0'*64
                if change=='id':body['candidate_ref']['candidate_id']='Candidate_3'
                with self.subTest(change=change),self.assertRaises(ValueError):space.action(body,'owner')
            self.assertFalse(space.previews)

    def test_response_or_adoption_tampering_blocks_apply_without_second_call(self):
        for target in ('result','adoption'):
            with self.subTest(target=target),self.workspace() as (space,app,w,d,p,calls):
                job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
                folder=space.photos.root/job['job_id']
                path=folder/'result.json' if target=='result' else next((folder/'adoptions').glob('*.json'))
                value=json.loads(path.read_text());value['explanation' if target=='result' else 'model_id']='tampered';atomic_json(path,value)
                with self.assertRaises(ValueError):space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner')
                self.assertEqual(len(calls),1)

    def test_photo_cancel_and_apply_admission_share_one_fence(self):
        for admitted in (False,True):
            with self.subTest(admitted=admitted),self.workspace() as (space,app,w,d,p,calls):
                job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
                cancel=dict(action='photo_cancel',request_id='cancel',job_id=job['job_id'])
                if admitted:
                    space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)
                    with self.assertRaisesRegex(ValueError,'ALREADY_ADMITTED'):space.action(cancel,'owner')
                    self.assertEqual(job['status'],'ready')
                else:
                    space.action(cancel,'owner')
                    with self.assertRaises(ValueError):space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)

    def test_invalid_output_cancel_scene_change_and_storage_failure_never_publish_ready(self):
        def cancel(space,app,w,d,token):token.cancel()
        def change(space,app,w,d,token):w._input=None
        for mode in ('invalid','cancel','scene','storage'):
            value=output()
            if mode=='invalid':value['candidates'][0]['bbox']=[1,1,0,0]
            with self.subTest(mode=mode),self.workspace(value=value,hook=cancel if mode=='cancel' else change if mode=='scene' else None) as (space,app,w,d,p,calls):
                self.start(space);job=space.photos.job
                if mode=='storage':
                    with patch('twinpulse_app.environment_photo_review.atomic_json',side_effect=OSError('diagnostics failed')):space.photos._run(job,space.photos.token)
                else:space.photos._run(job,space.photos.token)
                self.assertIn(job['status'],('failed','cancelled'));self.assertFalse(job['candidates']);self.assertFalse(space.previews)
                self.assertEqual(len(calls),0 if mode=='storage' else 1)

    def test_failed_cancel_storage_still_revokes_existing_preview_in_this_process(self):
        with self.workspace() as (space,app,w,d,p,calls):
            job=self.complete_job(space);preview=space.action(self.preview_body(space,job),'owner')['preview']
            with patch.object(space.photos,'_save_job',side_effect=OSError('cancel storage failed')):
                with self.assertRaises(OSError):space.action(dict(action='photo_cancel',request_id='cancel',job_id=job['job_id']),'owner')
            with self.assertRaisesRegex(ValueError,'CANCELLED'):
                space.pinned_environment_operation(preview['operation']['operation_id'],preview['preview_digest'],'owner',claim=True)
            with self.assertRaisesRegex(ValueError,'CANCELLED'):space.action(self.preview_body(space,job,request='again'),'owner')
            self.assertFalse(app.scene_change_store().path.exists());self.assertEqual(len(calls),1)

    def test_late_diagnostic_or_publication_failure_cannot_revive_ready_cold(self):
        for failure in ('flush','publish'):
            with self.subTest(failure=failure),self.workspace() as (space,app,w,d,p,calls):
                self.start(space);job=space.photos.job
                with patch.object(space.photos,'_save_job',side_effect=OSError('job storage failed')):
                    if failure=='flush':
                        with patch.object(app.diagnostics,'flush',return_value=False):space.photos._run(job,space.photos.token)
                    else:space.photos._run(job,space.photos.token)
                self.assertEqual(job['status'],'failed');self.assertFalse(job['candidates']);self.assertEqual(len(calls),1)
                saved=json.loads((space.photos.root/job['job_id']/'job.json').read_text())
                self.assertEqual(saved['status'],'running')
                cold=EnvironmentPhotoReview(space)
                self.assertEqual(cold.job['status'],'failed');self.assertIn('unknown',cold.job['error'])
                self.assertFalse(cold.job['candidates']);self.assertEqual(len(calls),1)

    def test_single_dispatch_ledger_keeps_unknown_attempt_spent(self):
        for failure in (False,True):
            ledger=Mock(state=dict(requests=[]))
            if failure:ledger.reserve.side_effect=OSError('original failure')
            owner=SinglePhotoLedger(ledger)
            if failure:
                with self.assertRaises(OSError):owner.reserve(dict(model='fixture'))
            else:owner.reserve(dict(model='fixture'))
            with self.assertRaisesRegex(ProviderConfigurationError,'ONE_CALL'):owner.reserve(dict(model='fixture'))
            self.assertEqual(ledger.reserve.call_count,1)
