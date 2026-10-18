# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline photo catalogue and real HTTP boundary; no hardware or Isaac execution."""
import copy
from hashlib import sha256
import json
import unittest
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from tests.integration.test_bedroom_twin import ROOT
from tests.integration.test_derived_review_selection import selection_fixture
from twinpulse_app import CommandBroker, LocalApiServer
from twinpulse_app.bedroom_review import BedroomReview, load_bedroom_source, checked_bedroom_descriptor
from twinpulse_app.command_broker import BrokerError
from twinpulse_core import SimulationSnapshot


class BedroomReviewTests(unittest.TestCase):
    def setUp(self):
        self.source = load_bedroom_source()
        # These offline routing tests do not test wall-clock lease expiry.
        # Keep their synthetic lease deterministic even on a busy test PC.
        self.broker = CommandBroker(clock=lambda: 0.)
        self.review = BedroomReview(self.broker, lambda: self.source)

    def connect(self, preview=True):
        self.broker.register_engine('engine', 'stage')
        self.broker.acquire_lease('product')
        self.broker.record_snapshot(SimulationSnapshot(
            engine_session_id='engine', stage_epoch='stage', project_id='default',
            applied_revision=None, run_id=None, sequence=1, runtime_state='idle',
            safety_state=None, safety_reason=None, permitted_commands=('build_site_scene', 'get_state'),
            capabilities=('simulation', 'site_scene_build_v2') + (('bedroom_visual_v1','bedroom_replay_v1') if preview else ()),
            telemetry_available=False))

    def test_review_is_non_mutating_and_not_motion_authority(self):
        state = self.review.prepare()
        self.assertFalse(state['motion_authorized'])
        self.assertFalse(state['alignment_verified'])
        self.assertEqual(state['physical_validation'], 'NOT_RUN')
        self.assertEqual(len(state['objects']), 12)

    def test_ack_and_preparation_required(self):
        revision = self.source[1]['manifest_sha256']
        for ack in (False, True, 1, 'true'):
            with self.assertRaises(BrokerError): self.review.build('product', revision, ack, 'request')
        self.review.prepare()
        for ack in (False, 1, 'true'):
            with self.assertRaises(BrokerError): self.review.build('product', revision, ack, 'request')

    def test_changed_assets_revoke_review(self):
        state = self.review.prepare()
        manifest = copy.deepcopy(self.source[1]); manifest['manifest_sha256'] = 'a'*64
        self.source = self.source[0], manifest, self.source[2]
        with self.assertRaisesRegex(BrokerError, 'changed'): self.review.build('product', state['revision'], True, 'request')
        with self.assertRaises(BrokerError): self.review.build('product', state['revision'], True, 'again')

    def test_source_failure_revokes_review(self):
        state = self.review.prepare()
        def failed(): raise OSError('fixture')
        self.review._load = failed
        with self.assertRaises(BrokerError): self.review.prepare()
        with self.assertRaises(BrokerError): self.review.build('product', state['revision'], True, 'request')

    def test_engine_capability_required(self):
        self.connect(False)
        state = self.review.prepare()
        with self.assertRaises(BrokerError): self.review.build('product', state['revision'], True, 'request')

    def test_real_broker_envelope_has_bound_preview_no_motion(self):
        self.connect()
        state = self.review.prepare()
        operation = self.review.build('product', state['revision'], True, 'request')
        self.assertEqual(operation['command_type'], 'build_site_scene')
        command = self.broker.claim('engine', 'stage')
        self.assertEqual(command.payload['visual_preview'], dict(kind='bedroom_visual_v1', manifest_sha256=state['revision']))
        self.assertNotIn('mission', command.payload)
        checked_bedroom_descriptor(command.payload['visual_preview'], self.source[0].site.scene)

    def test_descriptor_tampering_rejected(self):
        descriptor = dict(kind='bedroom_visual_v1', manifest_sha256=self.source[1]['manifest_sha256'])
        for bad in ({**descriptor, 'path': 'external'}, {**descriptor, 'manifest_sha256': '0'*64}):
            with self.assertRaises(ValueError): checked_bedroom_descriptor(bad, self.source[0].site.scene)
            with self.assertRaises((ValueError, BrokerError)):
                self.broker.register_site_scene('bad', self.source[0].site.scene, visual_preview={**bad, 'extra': True})

    def test_replay_recomputed_bound_and_separate_artifacts(self):
        self.connect(); state=self.review.prepare()
        result=self.review.rehearse(state['revision'],'route',True)
        replay=dict(scenario='route',revision=result['revision'],frame=len(result['events']))
        self.review.build('product',state['revision'],True,'replay-request',replay)
        command=self.broker.claim('engine','stage')
        self.assertEqual(command.payload['visual_preview']['replay'],replay)
        checked_bedroom_descriptor(command.payload['visual_preview'],self.source[0].site.scene)

    def test_replay_tampering_and_non_integer_frames_rejected(self):
        from twinpulse_app.bedroom_rehearsal import checked_replay
        draft,manifest,_=self.source
        self.review.prepare()
        result=self.review.rehearse(manifest['manifest_sha256'],'stale_scan',True)
        good=dict(scenario='stale_scan',revision=result['revision'],frame=6)
        self.assertEqual(checked_replay(draft,manifest,good)['revision'],result['revision'])
        for bad in (None,{}, {**good,'frame':True},{**good,'frame':1.0},{**good,'frame':-1},
                    {**good,'frame':7},{**good,'revision':'0'*64},{**good,'scenario':'route'},
                    {**good,'pose':[0,0,0]}, {**good,'frame':1802}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):checked_replay(draft,manifest,bad)

    def test_one_offline_product_suite_keeps_all_failure_and_success_records_separate(self):
        state=self.review.prepare()
        result=self.review.offline_acceptance(state['revision'],True)
        self.assertEqual(result['status'],'SYNTHETIC_PASS')
        self.assertEqual(set(result['records']),{'route','direct','detour','detour_no_path','stale_scan'})
        self.assertEqual(result['records']['detour_no_path']['status'],'NO_PATH')
        self.assertEqual(result['records']['stale_scan']['status'],'SCAN_STALE')
        self.assertFalse(result['motion_authorized']);self.assertFalse(result['robot_connection'])
        self.assertEqual(result['physical_validation'],'NOT_RUN')
        self.assertIsNone(result['evaluation']['overall_score'])
        with self.assertRaises(BrokerError):self.review.offline_acceptance(state['revision'],False)
        with self.assertRaises(BrokerError):self.review.export_offline_acceptance(state['revision'],True,'0'*64)
        exported=self.review.export_offline_acceptance(state['revision'],True,result['revision'])
        self.assertEqual(sha256(exported['json_text'].encode()).hexdigest(),exported['sha256'])
        self.assertEqual(json.loads(exported['json_text'])['revision'],result['revision'])
        reopened=self.review.reopen_offline_acceptance(state['revision'],True,exported['json_text'])
        self.assertEqual(reopened['revision'],result['revision'])
        for damaged in (exported['json_text'][:-1],exported['json_text'].replace('SYNTHETIC_PASS','SYNTHETIC_FAIL'),
                        '{"revision":"0"}', 'NaN'):
            with self.subTest(damaged=damaged[:24]),self.assertRaises(BrokerError):
                self.review.reopen_offline_acceptance(state['revision'],True,damaged)

    def test_actual_http_auth_csrf_shape_preserves_project(self):
        with TemporaryDirectory() as folder:
            app, workflow, broker, _, _, _ = selection_fixture(folder)
            original = app._project_store.path.read_bytes()
            server = LocalApiServer(broker, product_workflow=workflow, product_bootstrap_secret='p'*43, engine_bootstrap_secret='e'*43)
            server.start()
            def request(path, body, headers=None):
                req = Request(server.base_url + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
                try:
                    with urlopen(req, timeout=15) as response: return response.status, json.loads(response.read()), response.headers
                except HTTPError as error: return error.code, json.loads(error.read()), error.headers
            try:
                _, boot, headers = request('/v1/bootstrap', dict(role='product', secret='p'*43))
                auth = {'Cookie': headers['Set-Cookie'].split(';',1)[0], 'X-TwinPulse-CSRF': boot['csrf_token']}
                path = '/v1/product/bedroom/prepare'
                self.assertEqual(request(path, {})[0], 401)
                self.assertEqual(request(path, {}, {'Cookie':auth['Cookie']})[0], 403)
                self.assertEqual(request(path, {'path':'arbitrary'}, auth)[0], 400)
                status, state, _ = request(path, {}, auth)
                self.assertEqual(status, 200)
                suite_path='/v1/product/bedroom/offline-acceptance'
                suite_body=dict(revision=state['revision'],acknowledged=True)
                self.assertEqual(request(suite_path,suite_body)[0],401)
                self.assertEqual(request(suite_path,suite_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(suite_path,{**suite_body,'physical_success':True},auth)[0],400)
                code,suite,_=request(suite_path,suite_body,auth)
                self.assertEqual(code,200);self.assertEqual(suite['status'],'SYNTHETIC_PASS')
                self.assertFalse(suite['robot_connection']);self.assertFalse(suite['motion_authorized'])
                self.assertEqual(suite['records']['detour_no_path']['status'],'NO_PATH')
                imported='/v1/product/bedroom/offline-acceptance-import'
                self.assertEqual(request(imported,dict(revision=state['revision'],acknowledged=True,bundle_text='{}'))[0],401)
                self.assertEqual(request(imported,dict(revision=state['revision'],acknowledged=True,bundle_text='{}'),auth)[0],409)
                code,reopened,_=request(imported,dict(revision=state['revision'],acknowledged=True,
                    bundle_text=json.dumps(suite,ensure_ascii=False,separators=(',',':'))),auth)
                self.assertEqual(code,200);self.assertEqual(reopened['revision'],suite['revision'])
                geometry='/v1/product/bedroom/geometry-evidence'
                self.assertEqual(request(geometry,{})[0],401)
                self.assertEqual(request(geometry,{}, {'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(geometry,{'path':'arbitrary'},auth)[0],400)
                code,evidence,_=request(geometry,{},auth);self.assertEqual(code,200)
                goal_path='/v1/product/bedroom/goal-preview'
                goal_body=dict(revision=state['revision'],evidence_revision=evidence['revision'],goal=[0,0],reference=None)
                self.assertEqual(request(goal_path,goal_body)[0],401)
                self.assertEqual(request(goal_path,goal_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(goal_path,{**goal_body,'motion_authorized':True},auth)[0],400)
                code,goal,_=request(goal_path,goal_body,auth);self.assertEqual(code,200)
                self.assertIsNone(goal['odom_goal_candidate_m']);self.assertIsNone(goal['mission_request'])
                self.assertEqual(request('/v1/product/bedroom/build', dict(revision=state['revision'], acknowledged=False, request_id='test'), auth)[0], 409)
                rehearsal='/v1/product/bedroom/rehearse'
                body=dict(revision=state['revision'],scenario='stale_scan',acknowledged=True)
                self.assertEqual(request(rehearsal,body)[0],401)
                self.assertEqual(request(rehearsal,body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(rehearsal,{**body,'radius_m':0},auth)[0],400)
                self.assertEqual(request(rehearsal,{**body,'scenario':'physical'},auth)[0],400)
                code,result,_=request(rehearsal,body,auth)
                self.assertEqual(code,200);self.assertEqual(result['status'],'SCAN_STALE')
                self.assertFalse(result['motion_authorized'])
                mission_export='/v1/product/bedroom/rehearse-export'
                mission_body={**body,'record_revision':result['revision']}
                self.assertEqual(request(mission_export,mission_body)[0],401)
                self.assertEqual(request(mission_export,mission_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(mission_export,{**mission_body,'frame':0},auth)[0],400)
                self.assertEqual(request(mission_export,{**mission_body,'record_revision':'0'*64},auth)[0],409)
                code,mission_data,_=request(mission_export,mission_body,auth)
                self.assertEqual(code,200)
                self.assertEqual(sha256(mission_data['json_text'].encode()).hexdigest(),mission_data['sha256'])
                self.assertEqual(json.loads(mission_data['json_text'])['revision'],result['revision'])
                comparison='/v1/product/bedroom/compare'
                compare_body=dict(revision=state['revision'],acknowledged=True)
                self.assertEqual(request(comparison,compare_body)[0],401)
                self.assertEqual(request(comparison,compare_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(comparison,{**compare_body,'goal':[0,0]},auth)[0],400)
                self.assertEqual(request(comparison,{**compare_body,'revision':'0'*64},auth)[0],409)
                code,comparison_result,_=request(comparison,compare_body,auth)
                self.assertEqual(code,200);self.assertEqual(len(comparison_result['candidates']),2)
                self.assertIsNone(comparison_result['candidates'][0]['metrics']['collision_count'])
                export_path='/v1/product/bedroom/compare-export'
                export_body={**compare_body,'comparison_revision':comparison_result['revision']}
                self.assertEqual(request(export_path,export_body)[0],401)
                self.assertEqual(request(export_path,export_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(export_path,{**export_body,'motion_authorized':True},auth)[0],400)
                self.assertEqual(request(export_path,{**export_body,'comparison_revision':'0'*64},auth)[0],409)
                code,exported,_=request(export_path,export_body,auth)
                self.assertEqual(code,200)
                self.assertEqual(sha256(exported['json_text'].encode()).hexdigest(),exported['sha256'])
                self.assertEqual(json.loads(exported['json_text'])['revision'],comparison_result['revision'])
                evaluation='/v1/product/bedroom/evaluate'
                self.assertEqual(request(evaluation,compare_body)[0],401)
                self.assertEqual(request(evaluation,compare_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(evaluation,{**compare_body,'physical_success':True},auth)[0],400)
                code,evaluated,_=request(evaluation,compare_body,auth)
                self.assertEqual(code,200)
                self.assertEqual(evaluated['source_comparison_revision'],comparison_result['revision'])
                self.assertIsNone(evaluated['candidates'][0]['axes']['collision']['count'])
                self.assertFalse(evaluated['motion_authorized'])
                replay_path='/v1/product/bedroom/replay'
                replay_body=dict(revision=state['revision'],acknowledged=True,request_id='seek',
                    replay=dict(scenario='stale_scan',revision=result['revision'],frame=6))
                self.assertEqual(request(replay_path,replay_body)[0],401)
                self.assertEqual(request(replay_path,replay_body,{'Cookie':auth['Cookie']})[0],403)
                self.assertEqual(request(replay_path,{**replay_body,'pose':[0,0,0]},auth)[0],400)
                self.assertEqual(request(replay_path,{**replay_body,'replay':None},auth)[0],400)
                self.assertEqual(request(replay_path,{**replay_body,'replay':{**replay_body['replay'],'frame':True}},auth)[0],400)
                self.assertEqual(app._project_store.path.read_bytes(), original)
            finally: server.stop()


if __name__ == '__main__': unittest.main()
