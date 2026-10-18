# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit synthetic terminal lifecycle + actual CDR mapping; no physical ACK."""
from copy import deepcopy
import hashlib
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
from twinpulse_app.scene_sensor_review import SceneSensorReview
from twinpulse_core import InputArtifactStore,canonical_sha256


class SceneSensorImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template=TemporaryDirectory();cls.fixture=build_test_sensor_history(cls.template.name)

    @classmethod
    def tearDownClass(cls):cls.template.cleanup()

    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)/'history';shutil.copytree(self.template.name,self.root)
        source=self.fixture['source_record'];store=ProjectStore.for_project(self.root,'default')
        InputArtifactStore(store.input_root()).save(source.input_revision,())
        store.save(ProjectRecord('default',source.input_revision,site_draft=source))
        self.product=workflow(self.root);self.review=SceneSensorReview(self.product,self.root)
        self.product.scene_sensor_review=self.review;self.importer=self.review.surveys
        self.survey=self.fixture['survey'];self.report_path=self.importer._report_path(self.survey['mission_id'])

    def tearDown(self):self.product.shutdown();self.temp.cleanup()

    def body(self,request_id='import'):
        context=self.review.context()
        return dict(action='sensor_import',request_id=request_id,mission_id=self.survey['mission_id'],
            expected_report_revision=self.survey['report_revision'],expected_scene_revision=context['current_scene_revision'],
            expected_state_sha256=context['current_state_sha256'])

    def imported(self):
        result=self.importer.run(self.body(),'owner');self.assertEqual(result['status'],'imported',result)
        return result

    def selected(self,result):
        return self.review.select(dict(map_id=result['map_id'],expected_map_revision=result['map_revision'],
            expected_scene_revision=self.review.context()['current_scene_revision'],expected_state_sha256=self.review.context()['current_state_sha256']))

    def rewrite_report(self,change):
        body=json.loads(self.report_path.read_text(encoding='utf-8'));change(body);body.pop('revision')
        body['revision']=canonical_sha256(body)
        self.report_path.write_text(json.dumps(body,sort_keys=True),encoding='utf-8');self.survey=deepcopy(self.survey)
        self.survey['report_revision']=body['revision']

    def unchanged(self,context):
        self.assertEqual(self.review.context(),context)
        self.assertFalse(self.product._application.scene_change_store().path.exists())
        self.assertEqual(self.product._broker.public_state('owner')['operations'],[])

    def test_catalog_read_only_and_unregistered_positive_normal_mapping_duplicate(self):
        before=self.review.context();original={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertFalse(self.importer.maps._path(self.survey['expected_map_id']).exists())
        catalog=self.importer.catalog();self.assertEqual(catalog['surveys'][0]['status'],'READY',catalog)
        self.assertEqual(original,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()})
        result=self.imported();self.assertEqual(result['map_id'],self.survey['expected_map_id']);self.assertFalse(result['duplicate'])
        saved,proof,_=self.review._inputs(result['map_id']);self.assertGreaterEqual(len(saved['keyframes']),8)
        self.assertEqual(proof['provenance'],'SYNTHETIC_TRANSPORT');self.assertFalse(saved['motion_authorized'])
        path=self.importer.maps._path(result['map_id']);encoded=path.read_bytes();stamp=path.stat().st_mtime_ns
        with patch.object(self.importer.maps,'save',wraps=self.importer.maps.save) as save:
            duplicate=self.importer.run(self.body('duplicate'),'owner')
        self.assertTrue(duplicate['duplicate']);save.assert_not_called();self.assertEqual(path.read_bytes(),encoded)
        self.assertEqual(path.stat().st_mtime_ns,stamp);self.unchanged(before)
        for p,digest in original.items():self.assertEqual(hashlib.sha256(Path(p).read_bytes()).hexdigest(),digest,p)

    def test_conversation_import_then_one_policy_and_closed_restore(self):
        chat=ConversationService(self.product,self.root/'conversation.json');result=chat.dispatch(self.body(),'owner')
        imported=result['scene_sensor_review'];self.assertEqual(imported['status'],'imported');self.assertEqual(result['cards'],[])
        duplicate=chat.dispatch(self.body(),'owner');self.assertEqual(duplicate['cursor'],result['cursor'])
        restored=ConversationService(self.product,self.root/'conversation.json');self.assertIsNone(restored.snapshot()['restore_error'])
        context=self.review.context()
        selected=restored.dispatch(dict(action='sensor_review',request_id='review',map_id=imported['map_id'],
            expected_map_revision=imported['map_revision'],expected_scene_revision=context['current_scene_revision'],
            expected_state_sha256=context['current_state_sha256']),'owner')
        card=selected['cards'][-1];self.assertEqual(card['kind'],'scene_sensor_policy');self.assertEqual(len(card['choices']),3)
        self.unchanged(context)

    def test_missing_terminal_cleanup_and_source_are_held_not_registered(self):
        before=self.review.context()
        for mutate,reason in ((lambda b:b.update(state='FAILED'),'NOT_COMPLETED'),
                (lambda b:b['result'].update(sensor_cleanup_confirmed=False),'NOT_COMPLETED'),
                (lambda b:b.pop('room_source'),'SOURCE_INVALID'),
                (lambda b:b.update(goal={'mode':'SURVEY_THEN_NAVIGATE'}),'NOT_COMPLETED')):
            with self.subTest(reason=reason):
                original=self.report_path.read_bytes();old=deepcopy(self.survey)
                self.rewrite_report(mutate);result=self.importer.run(self.body(reason),'owner')
                self.assertEqual(result['status'],'HELD');self.assertIn(reason,result['reason'])
                self.assertFalse(self.importer.maps._path(old['expected_map_id']).exists());self.unchanged(before)
                self.report_path.write_bytes(original);self.survey=old

    def test_missing_export_raw_or_index_stays_held(self):
        before=self.review.context();job=self.survey['source_job_id'];folder=self.root/'artifacts/manual-control'/job
        paths=[folder/'robot-evidence/export.json',folder/'robot-evidence/ros-messages.raw',
            self.root/'artifacts/project-session-index/default'/(job+'.json')]
        for path in paths:
            with self.subTest(path=path.name):
                saved=path.read_bytes();path.unlink();result=self.importer.run(self.body(path.name),'owner')
                self.assertEqual(result['status'],'HELD');self.assertFalse(self.importer.maps._path(self.survey['expected_map_id']).exists())
                self.unchanged(before);path.write_bytes(saved)

    def test_stale_current_and_report_or_real_busy_never_map_dispatch(self):
        before=self.review.context()
        for key in ('expected_scene_revision','expected_state_sha256','expected_report_revision'):
            body=self.body(key);body[key]='0'*64
            with self.subTest(key=key),self.assertRaises(BrokerError) as error:self.importer.run(body,'owner')
            self.assertEqual(error.exception.code,'scene_sensor_stale')
        for code in ('scene_edit_robot_busy','scene_edit_robot_uncertain'):
            with patch.object(self.product.scene_edit_transaction,'admission',side_effect=BrokerError(code,'REAL remains locked',status=409)):
                with self.assertRaises(BrokerError) as error:self.importer.run(self.body(code),'owner')
                self.assertEqual(error.exception.code,code)
        self.assertFalse(self.importer.maps._path(self.survey['expected_map_id']).exists());self.unchanged(before)

    def test_native_terminal_id_is_checked_not_report_claim(self):
        # Keep a complete internally-consistent PC record for a DIFFERENT native mission.
        job=self.survey['source_job_id'];folder=self.root/'artifacts/manual-control'/job;path=folder/'session.jsonl'
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for row in rows:
            event=row['data'].get('event',{})
            if event.get('kind') in ('mission_started','mission_finished'):event['data']['mission_id']='d'*32
        path.write_text(''.join(json.dumps(row,sort_keys=True)+'\n' for row in rows),encoding='utf-8')
        from twinpulse_app.session_history import index_project_session
        index=self.root/'artifacts/project-session-index/default'/(job+'.json');index.unlink();index_project_session(self.root,'default',job)
        result=self.importer.run(self.body(),'owner');self.assertEqual(result['status'],'HELD')
        self.assertIn('NATIVE_TERMINAL_MISMATCH',result['reason']);self.assertFalse(self.importer.maps._path(self.survey['expected_map_id']).exists())

    def test_imported_map_cannot_be_reused_for_different_original_or_input(self):
        imported=self.imported();saved=self.importer.maps.load(imported['map_id']);original=self.product._application.site_draft
        from dataclasses import replace
        old_project=self.product._application._project
        self.product._application._project=replace(old_project,site_draft=replace(original,request_id='different-original-with-identical-geometry'))
        with self.assertRaisesRegex(ValueError,'IMPORT_ORIGINAL_CHANGED'):self.importer.validate_map(saved)
        self.product._application._project=old_project
        selected=self.product._input
        from types import SimpleNamespace
        self.product._input=SimpleNamespace(revision='0'*64)
        with self.assertRaisesRegex(ValueError,'IMPORT_ORIGINAL_CHANGED'):self.importer.validate_map(saved)
        self.product._input=selected;self.importer.validate_map(saved)

    def test_authenticated_catalog_and_ordinary_import_api_no_mutation_authority(self):
        from twinpulse_app import LocalApiServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        server=LocalApiServer(self.product._broker,product_workflow=self.product,session_history_root=self.root,
            product_bootstrap_secret='p'*43,engine_bootstrap_secret='e'*43)
        server.start()
        def request(path,body=None,headers=None):
            headers=dict(headers or {})
            if body is not None:headers['Content-Type']='application/json'
            try:response=urlopen(Request(server.base_url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=15)
            except HTTPError as response:return response.code,json.loads(response.read()),response.headers
            with response:return response.status,json.loads(response.read()),response.headers
        try:
            path='/v1/product/scene-edit/sensor-surveys';self.assertEqual(request(path)[0],401)
            status,session,headers=request('/v1/bootstrap',dict(role='product',secret='p'*43));self.assertEqual(status,200)
            auth={'Cookie':headers['Set-Cookie'].split(';',1)[0],'X-TwinPulse-CSRF':session['csrf_token']}
            status,catalog,_=request(path,headers=auth);self.assertEqual(status,200);self.assertEqual(catalog['surveys'][0]['status'],'READY')
            self.assertEqual(request('/v1/product/conversation',self.body('no-csrf'),{'Cookie':auth['Cookie']})[0],403)
            invalid=self.body('extra');invalid['expected_map_id']=self.survey['expected_map_id']
            self.assertEqual(request('/v1/product/conversation',invalid,auth)[0],400)
            status,state,_=request('/v1/product/conversation',self.body('api-import'),auth)
            self.assertEqual(status,200);self.assertEqual(state['scene_sensor_review']['status'],'imported')
            status,duplicate,_=request('/v1/product/conversation',self.body('api-import'),auth)
            self.assertEqual(status,200);self.assertEqual(duplicate['cursor'],state['cursor'])
            self.unchanged(self.review.context())
        finally:server.stop()

    def test_imported_fit_common_apply_undo_and_closed_map_witness(self):
        imported=self.imported();review=self.review.review(self.selected(imported),'correct_walls')
        self.assertEqual(review['status'],'preview',review);value=review['preview'];attach(self.product);tx=self.product.scene_edit_transaction
        tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        command=claim(self.product._broker);acknowledge(self.product._broker,command);tx.worker.join(8)
        self.assertEqual(tx.snapshot()['state'],'COMMITTED',tx.snapshot());store=self.product._application.scene_change_store()
        undo=self.product.preview_scene_edit(operation_id='undo-imported',mode='undo',target_call_id=None,tool_call=None)
        tx.start('owner',undo['operation'],undo['preview_digest']);command=claim(self.product._broker)
        acknowledge(self.product._broker,command);tx.worker.join(5);self.assertEqual(tx.snapshot()['state'],'COMMITTED')
        state=store.load().effective(store.source);self.assertEqual(state.plan,store.source.plan)
        restarted=workflow(self.root,self.product._broker)
        try:
            adapter=SceneSensorReview(restarted,self.root);saved,proof,_=adapter._inputs(imported['map_id'])
            self.assertEqual(proof['map_revision'],imported['map_revision']);self.assertIn('survey_import',saved)
            self.assertEqual(adapter.context()['current_state_sha256'],store.load().state_sha256(state))
        finally:restarted.shutdown()

    def test_report_byte_changed_preapply_and_afterack_is_compensated(self):
        imported=self.imported();review=self.review.review(self.selected(imported),'correct_walls')
        self.assertEqual(review['status'],'preview',review);value=review['preview'];attach(self.product);tx=self.product.scene_edit_transaction
        original=self.report_path.read_bytes();self.report_path.write_bytes(original+b' ')
        with self.assertRaises(BrokerError) as error:tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        self.assertEqual(error.exception.code,'scene_sensor_apply_rejected');self.assertEqual(self.product._broker.public_state('owner')['operations'],[])
        self.report_path.write_bytes(original);tx.start('owner',value['operation'],value['preview_digest'],sensor_binding=value['sensor_binding'])
        command=claim(self.product._broker);self.report_path.write_bytes(original+b' ');acknowledge(self.product._broker,command)
        compensation=claim(self.product._broker);self.assertTrue(tx.locked());acknowledge(self.product._broker,compensation);tx.worker.join(5)
        self.assertEqual(tx.snapshot()['state'],'ROLLED_BACK');self.assertFalse(self.product._application.scene_change_store().path.exists())


if __name__=='__main__':unittest.main()
