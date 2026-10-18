# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Typed saved bytes/real fit, then the existing broker transaction; no device."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.integration.test_scene_edit_transaction import workflow,attach,claim,acknowledge
from tests.fixtures.progressive_sensor_saved import build_test_sensor_history
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.conversation_service import ConversationService
from twinpulse_app.project_store import ProjectRecord,ProjectStore
from twinpulse_app.scene_changes import SceneChangeHistory
from twinpulse_app.scene_sensor_review import SceneSensorReview,checked_sensor_binding
from twinpulse_app.saved_mapping_evidence import load_saved_mapping
from twinpulse_core import InputArtifactStore,canonical_sha256


class SceneSensorReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template=TemporaryDirectory();cls.fixture=build_test_sensor_history(cls.template.name)

    @classmethod
    def tearDownClass(cls):cls.template.cleanup()

    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)/'history'
        shutil.copytree(self.template.name,self.root)
        source=self.fixture['source_record'];store=ProjectStore.for_project(self.root,'default')
        InputArtifactStore(store.input_root()).save(source.input_revision,())
        store.save(ProjectRecord('default',source.input_revision,site_draft=source))
        self.product=workflow(self.root);self.adapter=SceneSensorReview(self.product,self.root)
        self.product.scene_sensor_review=self.adapter
        self.selection=self.adapter.select(self.body('select'))
        self.original=deepcopy(source.to_dict())

    def tearDown(self):
        self.product.shutdown();self.temp.cleanup()

    def body(self,request_id):
        current=self.adapter.context();positive=self.fixture['positive']
        return dict(action='sensor_review',request_id=request_id,map_id=positive['map_id'],
            expected_map_revision=positive['map_revision'],expected_scene_revision=current['current_scene_revision'],
            expected_state_sha256=current['current_state_sha256'])

    def reviewed(self):
        result=self.adapter.review(self.selection,'correct_walls')
        self.assertEqual(result['status'],'preview',{k:v for k,v in result.items() if k!='preview'})
        return result['preview']

    def test_helper_uses_raw_cdr_real_decoder_mapping_and_nominal_offset(self):
        loaded=load_saved_mapping(self.root,'default',self.fixture['positive']['source_job_id'])
        self.assertEqual(len(loaded['scans']),180);self.assertEqual(len(loaded['odom']),180)
        saved,evidence,_=self.adapter._inputs(self.fixture['positive']['map_id'])
        self.assertGreaterEqual(len(saved['keyframes']),8)
        self.assertEqual(saved['source_revision'],loaded['source_revision'])
        self.assertEqual(evidence['provenance'],'SYNTHETIC_TRANSPORT')
        self.assertFalse(saved['alignment_verified']);self.assertFalse(saved['motion_authorized'])
        self.assertNotEqual(saved['offset'],[0,0,0])

    def test_bounded_read_only_diagnostics_keep_fit_competitors_without_pose_authority(self):
        result=self.adapter.review(self.selection,'align_only')
        diagnosis=result['diagnostics']
        self.assertEqual(diagnosis['schema_version'],'scene-sensor-diagnostics-1.0')
        self.assertGreaterEqual(diagnosis['view_count'],8)
        self.assertLessEqual(len(diagnosis['alternatives']),8)
        self.assertLessEqual(len(diagnosis['fit_structures']),12)
        self.assertFalse(diagnosis['physical_authority']);self.assertFalse(diagnosis['source_pose_truth'])
        self.assertEqual(diagnosis['furniture_correspondence'],'not_implemented')
        self.assertIsNone(result['preview'])

    def test_empty_current_context_is_exact_and_read_only(self):
        store=self.product._application.scene_change_store();before=store.project_store.path.read_bytes()
        self.assertFalse(store.path.exists())
        context=self.adapter.context()
        self.assertEqual(context['current_state_sha256'],self.product.snapshot()['site_draft']['scene_state_sha256'])
        self.assertFalse(store.path.exists());self.assertEqual(store.project_store.path.read_bytes(),before)
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_pending_command_allows_metadata_but_not_sensor_selection(self):
        before=self.adapter.context()
        with patch.object(self.product._broker,'has_pending_operations',return_value=True):
            self.assertEqual(self.adapter.context(read_only=True),before)
            with self.assertRaises(BrokerError) as caught:self.adapter.context()
            self.assertEqual(caught.exception.code,'scene_edit_unavailable')
            with self.assertRaises(BrokerError):self.adapter.select(self.body('pending'))
        self.assertEqual(self.adapter.context(),before)
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_align_only_keeps_candidate_but_never_patch_or_history_or_build(self):
        before=self.adapter.context();result=self.adapter.review(self.selection,'align_only')
        self.assertEqual(result['status'],'POSE_CANDIDATE',result)
        self.assertEqual(result['geometry_status'],'BOUNDED_WALL_PROPOSAL_VALIDATED')
        self.assertIsNone(result['preview']);self.assertEqual(self.adapter.context(),before)
        self.assertFalse(self.product._application.scene_change_store().path.exists())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_common_preview_has_one_bounded_wall_and_exact_nonwall_state(self):
        value=self.reviewed();binding=checked_sensor_binding(value['sensor_binding'])
        self.assertEqual(binding['policy'],'correct_walls')
        self.assertEqual(len(value['operation']['dependency_patch']['edits']),1)
        self.assertEqual(value['operation']['dependency_patch']['edits'][0]['target_id'],self.fixture['positive']['wall_id'])
        store=self.product._application.scene_change_store()
        self.adapter.validate_apply(binding,value['operation'],store,store.load())
        self.assertEqual(self.product._application.site_draft.to_dict(),self.original)
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_conversation_single_policy_cancel_preview_cancel_and_restore_no_mutation(self):
        chat=ConversationService(self.product,self.root/'conversation.json')
        selected=chat.dispatch(self.body('select'),'owner');card=selected['cards'][-1]
        self.assertEqual(card['kind'],'scene_sensor_policy');self.assertEqual(len(card['choices']),3)
        self.assertEqual(chat.dispatch(self.body('select'),'owner')['cursor'],selected['cursor'])
        answer=dict(action='answer',request_id='cancel',card_id=card['id'],choice_id='cancel',expected_session_revision=card['expected_session_revision'])
        result=chat.dispatch(answer,'owner');self.assertEqual(result['scene_sensor_review']['status'],'cancelled')
        selected=chat.dispatch(self.body('select2'),'owner');card=selected['cards'][-1]
        result=chat.dispatch({**answer,'request_id':'review','card_id':card['id'],'choice_id':'correct_walls','expected_session_revision':card['expected_session_revision']},'owner')
        self.assertIsNotNone(result['scene_edit_preview']);self.assertEqual(result['cards'][-1]['kind'],'scene_edit')
        restored=ConversationService(self.product,self.root/'conversation.json')
        self.assertIsNone(restored.snapshot()['restore_error'])
        edit=result['cards'][-1]
        restored.dispatch({**answer,'request_id':'cancel-preview','card_id':edit['id'],'expected_session_revision':edit['expected_session_revision']},'owner')
        self.assertFalse(self.product._application.scene_change_store().path.exists())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_apply_ack_disk_undo_origin_archive_and_closed_replay(self):
        value=self.reviewed();attach(self.product);tx=self.product.scene_edit_transaction
        tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(8)
        self.assertEqual(tx.snapshot()['state'],'COMMITTED',tx.snapshot())
        self.assertEqual(tx.value['sensor_binding'],value['sensor_binding'])
        self.assertEqual(tx.value['schema_version'],'scene-edit-transaction-1.3')
        diagnostics=self.product._application.diagnostics
        self.assertTrue(diagnostics.flush())
        detail=diagnostics.detail(tx.value['execution_id'])
        root=next(span for span in detail['spans'] if span['span_id']==detail['manifest']['root_span_id'])
        self.assertEqual(root['metadata']['sensor_execution_id'],value['sensor_binding']['execution_id'])
        self.assertEqual(root['metadata']['sensor_binding_sha256'],canonical_sha256(value['sensor_binding']))
        self.assertEqual(root['metadata']['sensor_raw_sha256'],value['sensor_binding']['evidence']['raw_sha256'])
        graph=diagnostics.graph(tx.value['execution_id'])
        self.assertTrue(any(edge['relation']=='sensor_execution_id' and
            edge['target']==value['sensor_binding']['execution_id'] for edge in graph['edges']))
        self.assertEqual(tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])['command_id'],command.command_id)
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        store=self.product._application.scene_change_store()
        self.assertIsNone(self.product.scene_edit_proposal_service)
        self.assertIsNone(getattr(self.product,'generation_approvals',None))
        chat=ConversationService(self.product,self.root/'undo-chat.json')
        state=chat.dispatch(dict(action='message',request_id='ordinary-undo',text='Undo',mode='new',attachment=None),'owner')
        undo=state['scene_edit_preview']
        self.assertEqual(undo['operation']['mode'],'undo')
        tx.start('owner',undo['operation'],undo['preview_digest']);command=claim(self.product._broker)
        acknowledge(self.product._broker,command);tx.worker.join(5)
        self.assertEqual(tx.snapshot()['state'],'COMMITTED');self.assertIsNone(tx.value['sensor_binding'])
        self.assertEqual(tx.value['sensor_origin_binding'],value['sensor_binding'])
        effective=store.load().effective(store.source)
        self.assertEqual(effective.plan,store.source.plan)
        self.assertEqual(self.product._application.site_draft.to_dict(),self.original)
        restarted=workflow(self.root,self.product._broker)
        try:
            restarted.scene_sensor_review=SceneSensorReview(restarted,self.root)
            self.assertEqual(restarted.scene_edit_transaction.snapshot()['sensor_origin_binding'],value['sensor_binding'])
            self.assertEqual(restarted.scene_sensor_review.context()['current_state_sha256'],store.load().state_sha256(effective))
            refs=restarted._broker.artifact_diagnostic_refs(restarted._site_artifact.artifact_id)
            self.assertEqual(refs['sensor_execution_id'],value['sensor_binding']['execution_id'])
        finally:restarted.shutdown()

    def test_exact_undo_without_model_no_history_and_new_or_attachment_stay_protected(self):
        chat=ConversationService(self.product,self.root/'negative-undo-chat.json')
        original=self.adapter.context()
        for text,attachment,mode,code in (
                ('Undo',None,'new','scene_edit_invalid'),
                ('Create a new room',None,'new','existing_scene_protected'),
                ('Undo this environment and create a new room',None,'new','existing_scene_protected'),
                ('Undo',{'name':'photo.png','media_type':'image/png','content_base64':'not-read'},'new','existing_scene_protected'),
                ('Undo',{'name':'photo.png','media_type':'image/png','content_base64':'not-read'},'change','edit_attachment_pending')):
            with self.subTest(text=text,mode=mode):
                before=chat.snapshot('owner')
                with self.assertRaises(BrokerError) as rejected:
                    chat.dispatch(dict(action='message',request_id='reject_'+str(len(text))+mode+str(attachment is None),
                        text=text,mode=mode,attachment=attachment),'owner')
                self.assertEqual(rejected.exception.code,code)
                self.assertEqual(chat.snapshot('owner')['messages'],before['messages'])
        self.assertEqual(self.adapter.context(),original)
        self.assertFalse(self.product._application.scene_change_store().path.exists())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_ordinary_undo_still_uses_existing_transaction_real_admission(self):
        value=self.reviewed();attach(self.product);tx=self.product.scene_edit_transaction
        tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(8)
        chat=ConversationService(self.product,self.root/'guard-undo-chat.json')
        state=chat.dispatch(dict(action='message',request_id='undo-guard',text='Undo',mode='new',attachment=None),'owner')
        card=state['cards'][-1];before=self.adapter.context();old_operation=tx.value['operation']
        with patch.object(tx,'admission',side_effect=BrokerError('scene_edit_robot_uncertain','REAL cleanup is uncertain',status=409)) as admission:
            result=chat.dispatch(dict(action='answer',request_id='undo-blocked',card_id=card['id'],choice_id='apply',
                expected_session_revision=card['expected_session_revision']),'owner')
        admission.assert_called_once_with('owner')
        self.assertEqual(tx.value['operation'],old_operation);self.assertEqual(self.adapter.context(),before)
        self.assertIn('scene_edit_robot_uncertain',result['messages'][-1]['content'])
        self.assertIsNone(self.product._broker.claim('engine','stage'))

    def test_source_tamper_before_apply_blocks_dispatch_and_preserves_history(self):
        value=self.reviewed();attach(self.product)
        folder=self.root/'artifacts/manual-control'/self.fixture['positive']['source_job_id']/'robot-evidence'
        with (folder/'report.json').open('ab') as stream:stream.write(b' ')
        with self.assertRaises(BrokerError) as error:
            self.product.scene_edit_transaction.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        self.assertEqual(error.exception.code,'scene_sensor_apply_rejected')
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])
        self.assertFalse(self.product._application.scene_change_store().path.exists())

    def test_evidence_changed_after_dispatch_requires_compensation_ack(self):
        value=self.reviewed();attach(self.product);tx=self.product.scene_edit_transaction
        tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        command=claim(self.product._broker)
        folder=self.root/'artifacts/manual-control'/self.fixture['positive']['source_job_id']/'robot-evidence'
        with (folder/'ros-messages.raw').open('ab') as stream:stream.write(b'changed-after-dispatch')
        acknowledge(self.product._broker,command);compensation=claim(self.product._broker)
        self.assertEqual(compensation.expected_applied_revision,value['parent_revision'])
        self.assertTrue(tx.locked());self.assertFalse(self.product._application.scene_change_store().path.exists())
        acknowledge(self.product._broker,compensation);tx.worker.join(5)
        self.assertEqual(tx.snapshot()['state'],'ROLLED_BACK');self.assertFalse(tx.locked())

    def test_stale_context_and_tampered_proposal_are_not_corrected(self):
        body=self.body('stale');body['expected_state_sha256']='0'*64
        with self.assertRaises(BrokerError):self.adapter.select(body)
        value=self.reviewed();binding=deepcopy(value['sensor_binding']);operation=deepcopy(value['operation'])
        operation['dependency_patch']['edits'][0]['tool_call']['arguments']['position_m'][2]+=.01
        binding['preview_sha256']=canonical_sha256(operation)
        store=self.product._application.scene_change_store()
        with self.assertRaisesRegex(ValueError,'PATCH_CHANGED'):
            self.adapter.validate_apply(binding,operation,store,store.load())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_out_of_bound_and_nonwall_proposals_fail_closed(self):
        store=self.product._application.scene_change_store();state=store.load().effective(store.source)
        report=dict(status='ALIGNMENT_CANDIDATE',geometry_status='BOUNDED_WALL_PROPOSAL_VALIDATED',proposals=[
            dict(id='wall_4',translation_xy_m=[0,.201])])
        with self.assertRaisesRegex(ValueError,'BOUND_INVALID'):self.adapter._patch(state,report)
        report['proposals'][0].update(id='chair',translation_xy_m=[0,.1])
        with self.assertRaisesRegex(ValueError,'BOUND_INVALID'):self.adapter._patch(state,report)
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_selected_original_three_jobs_are_held_and_every_original_byte_preserved(self):
        original_root=Path(__file__).resolve().parents[2]
        jobs=('4493be87ef7643ababb661b4a12f0180','b6cf346718da44b99e7bffe6f7919bbf','1a7f033af112437699ca67aef3438ecb')
        paths=[]
        for job in jobs:
            folder=original_root/'artifacts/manual-control'/job
            if not folder.exists():self.skipTest('Original historical sensor evidence not available on this host')
            paths.extend(p for p in folder.rglob('*') if p.is_file())
            paths.append(original_root/'artifacts/project-session-index/default'/(job+'.json'))
        import hashlib
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        with TemporaryDirectory() as directory:
            prepared=build_test_sensor_history(directory,real_history_root=original_root,real_job_ids=jobs)
            source=prepared['source_record'];store=ProjectStore.for_project(Path(directory),'default')
            InputArtifactStore(store.input_root()).save(source.input_revision,())
            store.save(ProjectRecord('default',source.input_revision,site_draft=source))
            product=workflow(Path(directory));adapter=SceneSensorReview(product,directory)
            product.scene_sensor_review=adapter
            try:
                context=adapter.context()
                for row in prepared['real_maps']:
                    with self.subTest(job=row['source_job_id']):
                        selection=adapter.select(dict(map_id=row['map_id'],expected_map_revision=row['map_revision'],
                            expected_scene_revision=context['current_scene_revision'],expected_state_sha256=context['current_state_sha256']))
                        result=adapter.review(selection,'correct_walls')
                        self.assertEqual(result['status'],'HELD',result)
                        self.assertIsNone(result['preview']);self.assertEqual(adapter.context(),context)
                self.assertFalse(product._application.scene_change_store().path.exists())
                self.assertEqual(product._broker.public_state('owner')['operations'],[])
            finally:product.shutdown()
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

    def test_authenticated_normal_api_policy_and_stale_scope_have_zero_dispatch(self):
        from twinpulse_app import LocalApiServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        server=LocalApiServer(self.product._broker,product_workflow=self.product,session_history_root=self.root,
            product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.start()
        def request(path,body=None,headers=None):
            headers=dict(headers or {})
            if body is not None:headers['Content-Type']='application/json'
            try:
                response=urlopen(Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5)
            except HTTPError as response:
                return response.code,json.loads(response.read()),response.headers
            with response:return response.status,json.loads(response.read()),response.headers
        try:
            self.assertEqual(request('/v1/product/scene-edit/sensor-context')[0],401)
            status,session,headers=request('/v1/bootstrap',dict(role='product',secret='p'*43));self.assertEqual(status,200)
            auth={'Cookie':headers['Set-Cookie'].split(';',1)[0],'X-TwinPulse-CSRF':session['csrf_token']}
            status,context,_=request('/v1/product/scene-edit/sensor-context',headers=auth)
            self.assertEqual(status,200);self.assertEqual(context,self.adapter.context())
            self.assertEqual(request('/v1/product/conversation',self.body('forbidden'),headers={'Cookie':auth['Cookie']})[0],403)
            status,state,_=request('/v1/product/conversation',self.body('api-select'),headers=auth)
            self.assertEqual(status,200);card=state['cards'][-1]
            body=dict(action='answer',request_id='api-policy',card_id=card['id'],choice_id='align_only',expected_session_revision=card['expected_session_revision'])
            status,state,_=request('/v1/product/conversation',body,headers=auth)
            self.assertEqual(status,200);self.assertEqual(state['scene_sensor_review']['status'],'POSE_CANDIDATE')
            status,duplicate,_=request('/v1/product/conversation',body,headers=auth)
            self.assertEqual(status,200);self.assertEqual(duplicate['cursor'],state['cursor'])
            stale=self.body('api-stale');stale['expected_state_sha256']='0'*64
            self.assertEqual(request('/v1/product/conversation',stale,headers=auth)[0],409)
            invalid=self.body('api-shape');invalid['source_job_id']='a'*32
            self.assertEqual(request('/v1/product/conversation',invalid,headers=auth)[0],400)
            self.assertFalse(self.product._application.scene_change_store().path.exists())
            self.assertEqual(self.product._broker.public_state('owner')['operations'],[])
        finally:server.stop()


if __name__=='__main__':unittest.main()
