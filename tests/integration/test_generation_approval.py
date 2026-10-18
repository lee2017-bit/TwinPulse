# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Authenticated ordinary chat approval/resume, audited fake HTTP only."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.integration import test_r5_product_api as r5
from tests.integration.test_stage_routing_settings import Credential
from tests.integration import test_chat_conversation as chat
from twinpulse_app.generation_approval import GenerationApprovals
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.settings import provider_settings_preset
from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service
from twinpulse_core import canonical_sha256
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.semantic_bindings import STRUCTURE_REPAIR_REVISION
from twinpulse_app.command_broker import BrokerError


def structure():
    return {'summary':'An estimated bedroom', 'room':{'width_m':6,'length_m':6,'height_m':2.6},
        'inventory':[{'id':'bed','kind':'bed','evidence_ref':'text:0'}]}


def furniture():
    return {'bed': {'region':'middle_centre','yaw_deg':0,'model_id':'home.bed',
        'dimensions_m':[1.4,2,.9],'variant':'standard','finish':'natural',
        'placement':{'relation':'floor','parent_id':None,'part':None,'anchor':'centre','elevation_m':None}}}


class GenerationApprovalTests(unittest.TestCase):
    def test_capacity_diagnostics_expose_only_bounded_integer_counts(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        from twinpulse_provider.scene_contract import report,issue
        diagnostic={'scene_contract':report([issue('OBSERVER_INSTANCE_LIMIT_EXCEEDED','$.entities',
            actual_count=33,maximum=32,structural_metadata_count=4,private_text='must not expose')])}
        row=_public_generation_diagnostics(diagnostic)['scene_contract']['issues'][0]
        self.assertEqual(row,dict(code='OBSERVER_INSTANCE_LIMIT_EXCEEDED',path='$.entities',
            actual_count=33,maximum=32,structural_metadata_count=4))
        for value in (True,-1,4097,1.5,'secret'):
            diagnostic['scene_contract']['issues'][0]['actual_count']=value
            self.assertNotIn('actual_count',_public_generation_diagnostics(diagnostic)['scene_contract']['issues'][0])
    def test_fresh_sim_choice_starts_once_with_visible_bounded_generation_offer(self):
        self.install_audited_fixture(); Credential.reads=[]
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Create a bed in an estimated bedroom',
            'mode':'new','attachment':None})
        card=first['cards'][-1]
        self.assertIn('generation_approval',card)
        self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        action={**self.answer(first),'limit_usd':'1.00'}
        started=self.call(action)
        self.assertFalse(any(c['kind']=='generation_approval' and c['state']=='waiting' for c in started['cards']))
        final=self.finish();self.assertEqual(final['generation']['state'],'completed')
        self.assertEqual(len(self.wires),4)
        self.call(action);self.call()
        self.assertEqual(len(self.wires),4)
        self.assertFalse(final['physical_authority'])

    def test_direct_generation_offer_rejects_changed_route_before_any_request(self):
        self.install_audited_fixture()
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Create a bed in an estimated bedroom',
            'mode':'new','attachment':None})
        self.route['planner']['max_output_tokens']=19000
        self.routes.save(self.route,lambda:None)
        with self.assertRaises(BrokerError) as caught:
            self.server.conversation.dispatch({**self.answer(first),'limit_usd':'1.00'},owner='product')
        self.assertEqual(caught.exception.code,'generation_approval_stale')
        self.assertEqual(self.wires,[])

    def test_direct_generation_rejects_insufficient_cap_and_real_presence_without_spending(self):
        self.install_audited_fixture()
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Create a bed in an estimated bedroom',
            'mode':'new','attachment':None})
        for choice,limit,code in [('sim','0.01','generation_cost_insufficient'),('real','1.00','chat_shape_invalid')]:
            with self.subTest(choice=choice):
                with self.assertRaises(BrokerError) as caught:
                    self.server.conversation.dispatch({**self.answer(first),'request_id':uuid4().hex,
                        'choice_id':choice,'limit_usd':limit},owner='product')
                self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.wires,[]);self.assertFalse(self.manager.root.exists())
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_direct_offer_reopening_history_does_not_create_a_grant_or_request(self):
        from twinpulse_app.conversation_service import ConversationService
        self.install_audited_fixture()
        self.call({'action':'message','request_id':uuid4().hex,'text':'Create a bed in an estimated bedroom',
            'mode':'new','attachment':None})
        self.server.conversation=ConversationService(self.workflow,self.server.conversation.path)
        restored=self.call()
        self.assertIsNone(restored['restore_error']);self.assertIsNone(restored['generation'])
        self.assertEqual(self.wires,[]);self.assertFalse(self.manager.root.exists())

    def test_catalog_prices_are_bound_expiring_and_removed_route_does_not_keep_them(self):
        from twinpulse_provider.model_contracts import catalog_sha
        from twinpulse_app.generation_approval import REVIEWED_PRICES
        value=dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
            valid_until='2026-10-11T00:00:00+00:00',source_sha256='a'*64,models=[
                dict(model_id='test/new',visible=True,modalities=['text','image'],context_tokens=32000,
                     input_per_million='0.1',output_per_million='0.2')])
        path=self.routes.path.with_name('stage_model_catalog.json');path.write_text(json.dumps(value),encoding='utf-8')
        original=deepcopy(self.route)
        self.route.update(model_catalog_sha256=catalog_sha(value))
        self.route['planner']={'key_id':'legacy','model_id':'test/new'}
        self.routes.save(self.route,lambda:None);self.manager.clock=lambda:datetime(2026,10,10,8,tzinfo=timezone.utc)
        self.install_audited_fixture();state=self.begin()
        preview=state['cards'][-1]['generation_approval']
        self.assertEqual(preview['models'][0]['model_id'],'test/new')
        self.assertEqual(preview['pricing_valid_until'],value['valid_until'])
        self.assertEqual(preview['models'][0]['full_context_reserve_usd'],'0.0072')
        self.assertEqual(self.manager.prices,REVIEWED_PRICES);self.assertEqual(self.wires,[])
        # Local approval construction only: no worker/HTTP, credential or billing call.
        Credential.reads=[]
        scope=self.manager.approve(preview,state['cards'][-1]['id'],'1.00')
        saved=json.loads(self.manager._approval_path(scope.approval_id).read_text())
        self.assertEqual(saved['rates_sha256'],canonical_sha256(saved['rates']))
        self.assertEqual(saved['rates']['test/new']['input_per_million'],'0.1')
        self.assertEqual(saved['rates']['test/new']['output_per_million'],'0.2')
        self.assertEqual(saved['rates']['test/new']['context_tokens'],32000)
        self.assertEqual(saved['rates'],scope.rates)
        ledger=scope.bind(self.manager.request(),GenerationPolicy.from_dict(self.route['generation_policy']),
            preview['route_sha256'])
        self.assertEqual(ledger.state['rates'],saved['rates'])
        self.assertEqual(ledger.state['requests'],[])
        self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.manager.clock=lambda:datetime(2026,10,11,tzinfo=timezone.utc)
        with self.assertRaisesRegex(BrokerError,'expired'):self.manager.prepare()
        self.routes.save(original,lambda:None)
        self.assertEqual(self.manager.prices,REVIEWED_PRICES);self.assertEqual(self.wires,[])

    tearDown = r5.R5ProductApiTests.tearDown
    request = r5.R5ProductApiTests.request
    product_headers = r5.R5ProductApiTests.product_headers
    call = chat.ChatConversationTests.call
    answer = chat.ChatConversationTests.answer

    def setUp(self):
        r5.R5ProductApiTests.setUp(self)
        self.settings_store.save(provider_settings_preset('nebius_token_factory'))
        Credential.secrets = {self.settings_store.load().credential_ref:'fixture-nebius'}
        Credential.reads = []
        self.registry = KeyRegistry(self.settings_store, Credential(self.settings_store.load().credential_ref), Credential)
        gpt = self.registry.register({'name':'GPT','provider_profile':'openai','model_id':'gpt-5.4-mini','api_key':'fixture-gpt'})['entries'][-1]['id']
        self.routes = StageRoutingSettings(self.registry)
        self.route = {'observer':{'key_id':gpt,'model_id':'gpt-5.4-mini'},
            'planner':{'key_id':'legacy','model_id':'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B','thinking_mode':'disabled'},
            'generation_policy':GenerationPolicy().to_dict()}
        self.routes.save(self.route, lambda:None)
        saved=self.routes.load()
        for stage in ('observer','planner'):
            self.assertEqual(self.routes.metadata()[stage+'_harness_sha256'],saved[stage]['harness_profile']['sha256'])
        self.workflow._generation_settings_getter = self.routes.metadata
        self.manager = GenerationApprovals(self.registry, self.workflow,
            clock=lambda:datetime(2026,10,9,8,tzinfo=timezone.utc))
        self.workflow.generation_approvals = self.manager
        self.responses = [structure(), furniture()]
        self.wires = []

    def install_audited_fixture(self):
        class Response:
            def __init__(self, endpoint, payload):self.endpoint,self.payload=endpoint,payload
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def geturl(self):return self.endpoint
            def read(self,*_):return self.payload
        def opener(request, **_):
            body=json.loads(request.data);self.wires.append(body)
            if body['response_format']['json_schema']['name']=='twinpulse_room_observation':
                value=dict(summary='Explicit fixture initial structure; no object inventory yet.',ambiguities=['Scale unmeasured'])
            elif body['response_format']['json_schema']['name']=='twinpulse_semantic_room':
                seed=getattr(self,'room_seed_fixture',None) or next(row for row in self.responses if isinstance(row,dict) and 'room' in row)
                value={key:deepcopy(seed[key]) for key in ('summary','room')}
                if not value['summary']:
                    value['summary']='Explicit fixture room shell'
            elif body['response_format']['json_schema']['name']=='twinpulse_model_resolution':
                # Current product discovery is a separate, audited model call.
                # Return actual builtin IDs for each requested kind, not the
                # parameter response queued for the following batch stage.
                from twinpulse_core.model_library import library_models
                schema=body['response_format']['json_schema']['schema']
                context=json.loads(body['messages'][-1]['content'].splitlines()[0])
                kinds={row['id']:row['kind'] for row in context['inventory']}
                models={row['kind']:row['model_id'] for row in library_models()}
                value={identity:models[kinds[identity]] for identity in schema['properties']}
                for identity,model_id in value.items():
                    self.assertIn(model_id,schema['properties'][identity]['enum'])
            else:
                value=self.responses.pop(0)
            if callable(value):value=value(body)
            finish,content=value if isinstance(value,tuple) else (('length','') if value == 'length' else ('stop',json.dumps(value)))
            return Response(request.full_url,json.dumps({'id':uuid4().hex,'model':body['model'],
                'choices':[{'finish_reason':finish,'message':{'content':content}}],
                'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}).encode())
        from twinpulse_provider.reliability import AuditedChatTransport
        original=AuditedChatTransport.__init__
        def fixture_init(transport,*args,**kwargs):
            original(transport,*args,**kwargs,opener=opener)
        with patch.object(AuditedChatTransport,'__init__',fixture_init):
            service=build_configured_stage_service(self.registry)
        self.workflow._application.set_generation_gateway(service)
        self.service=service

    def begin(self, image=False):
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Create a bed in an estimated bedroom',
            'mode':'new','attachment':{'name':'room.png','media_type':'image/png','content_base64':base64.b64encode(r5.png()).decode()} if image else None})
        return self.call(self.answer(first))

    def approve(self, state, limit='1.00', request_id=None):
        card=next(c for c in state['cards'] if c['state']=='waiting')
        return {'action':'answer','request_id':request_id or uuid4().hex,'card_id':card['id'],'choice_id':'approve',
            'expected_session_revision':card['expected_session_revision'],'limit_usd':limit}

    def finish(self):
        for _ in range(200):
            state=self.call()
            if state['generation'] and state['generation']['state'] not in {'accepted','running'}:
                return state
            time.sleep(.01)
        self.fail('Generation worker did not finish')

    def test_single_question_no_key_or_http_before_approval_then_audited_generation(self):
        self.install_audited_fixture();Credential.reads=[]
        state=self.begin()
        self.assertEqual([c['kind'] for c in state['cards'] if c['state']=='waiting'],['generation_approval'])
        self.assertIsNone(state['generation']);self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.assertEqual(state['cards'][-1]['generation_approval']['image_count'],0)
        for _ in range(3):self.call()
        self.assertFalse(self.manager.root.exists())
        action=self.approve(state);self.call(action);final=self.finish()
        self.assertEqual(final['generation']['state'],'completed', final['generation'])
        self.assertEqual(len(self.wires),4)
        self.assertEqual([w['response_format']['json_schema']['name'] for w in self.wires],
            ['twinpulse_semantic_room','twinpulse_semantic_structure','twinpulse_model_resolution','twinpulse_semantic_batch'])
        self.assertTrue(all(w['max_tokens']==20000 and w['chat_template_kwargs']=={'enable_thinking':False} for w in self.wires))
        fields=self.wires[1]['response_format']['json_schema']['schema']['properties']['inventory']['items']['properties']
        self.assertEqual(set(fields),{'id','kind','evidence_ref'})
        payload=json.loads(self.wires[1]['messages'][-1]['content'])
        self.assertEqual(payload['evidence_catalog'][0]['ref'],'text:0')
        self.assertTrue(all(w['messages'][0]['content'].count('Response JSON Schema:')==1 for w in self.wires))
        self.assertEqual(self.call(action)['generation']['operation_id'],final['generation']['operation_id'])
        self.assertEqual(len(self.wires),4)
        manifests=list(self.manager.root.glob('*.ledger.json'));self.assertEqual(len(manifests),1)
        ledger=json.loads(manifests[0].read_text());self.assertEqual(len(ledger['requests']),4)
        self.assertFalse(final['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_actual_chat_worker_uses_scoped_structure_correction_before_batch(self):
        invalid={**structure(),'summary':''}
        fix={'base_revision':canonical_sha256(invalid),
             'repair_version':STRUCTURE_REPAIR_REVISION,'changes':{},'additions':{},
             'room':None,'summary':'An estimated bedroom'}
        self.responses=[invalid,fix,furniture()];self.install_audited_fixture()
        self.call(self.approve(self.begin()));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),5)
        feedback=json.loads(self.wires[2]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'],invalid)
        schema=self.wires[2]['response_format']['json_schema']['schema']
        self.assertEqual(set(schema['properties']),{'repair_version','base_revision','changes','additions','room','summary'})
        self.assertEqual(schema['properties']['changes']['properties'],{})
        self.assertEqual(schema['properties']['summary']['anyOf'][1]['type'],'string')
        self.assertEqual(final['generation']['progress']['budget']['repairs'],1)
        self.assertFalse(final['physical_authority'])

    def test_cancel_and_bad_cost_never_dispatch_or_create_grant(self):
        self.install_audited_fixture();state=self.begin()
        for limit in ('0.00','NaN','1','1.000','21.00','0.01'):
            status,body,_=self.request('/v1/product/conversation',self.approve(state,limit),headers=self.product_headers)
            self.assertIn(status,(400,409));self.assertEqual(self.wires,[])
        card=state['cards'][-1]
        cancelled=self.call({'action':'answer','request_id':uuid4().hex,'card_id':card['id'],'choice_id':'cancel',
            'expected_session_revision':card['expected_session_revision']})
        self.assertIsNone(cancelled['generation']);self.assertFalse(self.manager.root.exists())

    def test_chat_ambiguous_json_patch_keeps_scoped_contract_and_recovers(self):
        invalid={**structure(),'summary':''}
        fix={'repair_version':STRUCTURE_REPAIR_REVISION,'base_revision':canonical_sha256(invalid),
             'changes':{},'additions':{},'room':None,'summary':'An estimated bedroom'}
        ambiguous=json.dumps(fix)[:-1]+',"summary":"Conflicting duplicate"}'
        self.responses=[invalid,('stop',ambiguous),fix,furniture()];self.install_audited_fixture()
        self.call(self.approve(self.begin()));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),6)
        feedback=json.loads(self.wires[3]['messages'][-1]['content'].splitlines()[-1])
        self.assertEqual(feedback['previous_candidate'],invalid)
        self.assertEqual(feedback['error_code'],'PROVIDER_JSON_DUPLICATE_KEY')
        self.assertEqual(feedback['validation']['issues'][0]['code'],'SEMANTIC_SUMMARY_INVALID')
        self.assertEqual(self.wires[3]['response_format']['json_schema']['schema']['properties']
                         ['base_revision']['enum'],[canonical_sha256(invalid)])
        self.assertEqual(final['generation']['progress']['budget']['repairs'],2)
        self.assertEqual(final['generation']['progress']['attempts_total'],6)
        attempts=final['generation']['progress']['attempts']
        self.assertEqual(attempts[2]['validation_code'],'PROVIDER_JSON_DUPLICATE_KEY')
        root=self.service._provider._transport.transports['planner'].evidence.root
        identity=attempts[2]['attempt_id']
        raw=json.loads((root/(identity+'.json')).read_text())
        dispatch=json.loads((root/'dispatches'/(identity+'.json')).read_text())
        validation=json.loads((root/'validations'/(identity+'-structure.json')).read_text())
        record=json.loads(validation['record_redacted'])
        self.assertEqual(json.loads(raw['response_redacted'])['choices'][0]['message']['content'],ambiguous)
        self.assertEqual(record['validation_code'],'PROVIDER_JSON_DUPLICATE_KEY')
        self.assertEqual(record['diagnosis']['issues'][0]['duplicate_key'],'summary')
        self.assertEqual(record['validation_candidate'],invalid)
        self.assertIsNone(record['candidate'])
        self.assertEqual(validation['execution_id'],dispatch['execution_id'])
        self.assertEqual(raw['execution_id'],validation['execution_id'])
        self.assertFalse(final['physical_authority'])
        self.assertEqual(self.broker.public_state('unowned')['operations'],[])

    def test_chat_photo_kind_error_is_one_target_and_preserves_photo_evidence(self):
        observation={'schema_version':'1.1','summary':'Synthetic bed, not a real photo test',
            'entities':[{'id':'new_bed','kind':'static_obstacle','role':'object','category':'bed',
                'description':'Bed','confidence':.9,'region':'middle_right','spatial_confidence':.9}],
            'relations':[],'dimensions':[],'ambiguities':['Estimated']}
        invalid=structure();invalid['inventory'][0].update(kind='desk',evidence_ref='seen:new_bed')
        fix={'repair_version':STRUCTURE_REPAIR_REVISION,'base_revision':canonical_sha256(invalid),
            'changes':{'bed':{'op':'set','value':{'kind':'bed','evidence_ref':'seen:new_bed'}}},
            'additions':{},'room':None,'summary':None}
        self.responses=[observation,invalid,fix,furniture()];self.install_audited_fixture()
        self.call(self.approve(self.begin(image=True)));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),7)
        context=json.loads(self.wires[4]['messages'][-1]['content'].splitlines()[0])['structure_repair']
        self.assertEqual(context['missing_observations'],[])
        self.assertEqual([row['id'] for row in context['targets']],['bed'])
        self.assertEqual(len(context['targets'][0]['issues']),2)
        props=self.wires[4]['response_format']['json_schema']['schema']['properties']
        self.assertEqual(props['changes']['properties']['bed']['anyOf'][1]['properties']
            ['value']['properties']['evidence_ref']['enum'],['seen:new_bed'])
        self.assertFalse(final['physical_authority'])

    def test_route_change_stales_approval_before_key_read(self):
        self.install_audited_fixture();state=self.begin();Credential.reads=[]
        self.route['planner']['max_output_tokens']=19000;self.routes.save(self.route,lambda:None)
        status,body,_=self.request('/v1/product/conversation',self.approve(state),headers=self.product_headers)
        self.assertEqual(status,409);self.assertIn('generation_approval_stale',json.dumps(body))
        self.assertEqual(self.wires,[]);self.assertEqual(Credential.reads,[])
        self.assertFalse(self.manager.root.exists())

    def test_restart_keeps_pending_choice_but_never_dispatches_and_grant_cannot_repeat(self):
        self.install_audited_fixture();state=self.begin()
        from twinpulse_app.conversation_service import ConversationService
        self.server.conversation=ConversationService(self.workflow,self.server.conversation.path)
        restored=self.call();self.assertIsNone(restored['restore_error'])
        self.assertEqual(self.wires,[])
        self.call(self.approve(restored));final=self.finish()
        preview=restored['cards'][-1]['generation_approval'];card=restored['cards'][-1]
        with self.assertRaisesRegex(BrokerError,'already recorded'):
            self.manager.approve(preview,card['id'],'1.00')
        self.assertEqual(len(self.wires),4)

    def test_length_stops_and_explicit_resume_calls_only_missing_batch(self):
        self.responses=[structure(),'length'];self.install_audited_fixture()
        self.call(self.approve(self.begin()));failed=self.finish()
        self.assertEqual(failed['generation']['state'],'failed')
        self.assertEqual(len(self.wires),4)
        key=failed['generation']['progress']['checkpoint_id'];old=self.manager.store.read('checkpoint',key)
        self.responses=[furniture()]
        state=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':failed['generation']['operation_id']})
        self.assertEqual(len(self.wires),4)
        self.assertEqual(state['cards'][-1]['generation_approval']['prior_requests'],4)
        self.call(self.approve(state));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),5)
        self.assertEqual(self.wires[-1]['response_format']['json_schema']['name'],'twinpulse_semantic_batch')
        self.assertEqual(self.manager.store.read('checkpoint',key),old)
        self.assertEqual(final['generation']['progress']['budget']['cumulative_requests'],5)
        self.assertEqual(final['generation']['progress']['budget']['cumulative_cost']['estimated_usage_usd'],'0.0000270')
        self.assertTrue(final['generation']['progress']['budget']['cumulative_cost']['history_complete'])
        self.assertEqual(len(list(self.manager.root.glob('*.ledger.json'))),2)

    def test_large_inventory_ordinary_api_retains_and_explicitly_resumes_saved_work(self):
        import sys
        sys.path.insert(0,str(r5.ROOT/'packages/twinpulse_provider/tests'))
        from test_inventory_work import many_objects
        raw,inventory,batches=many_objects()
        # A settled output truncation may explicitly continue within the same
        # original counters. Hard request exhaustion is tested separately below.
        self.route['generation_policy']['max_requests']=24
        self.routes.save(self.route,lambda:None)
        self.responses=[raw,inventory,*batches[:6],'length'];self.install_audited_fixture()
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Estimate these observed objects',
            'mode':'new','attachment':{'name':'fixture.png','media_type':'image/png','content_base64':base64.b64encode(r5.png()).decode()}})
        offered=self.call(self.answer(first))
        self.call(self.approve(offered));failed=self.finish()
        self.assertEqual(failed['generation']['state'],'failed')
        progress=failed['generation']['progress']['inventory_progress']
        self.assertEqual((progress['inventory_count'],progress['parameterized_count'],progress['pending_count']),(60,36,24))
        self.assertTrue(progress['checkpoint_saved']);self.assertFalse(progress['parameters_complete'])
        self.assertEqual(len(self.wires),12)
        self.assertEqual(failed['generation']['progress']['budget']['stop_reason'],'PROVIDER_OUTPUT_TRUNCATED')
        key=failed['generation']['progress']['checkpoint_id'];parent=self.manager.store.read('checkpoint',key)
        self.responses=deepcopy(batches[6:])
        self.install_audited_fixture()
        state=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':failed['generation']['operation_id']})
        self.assertEqual(len(self.wires),12)
        self.assertEqual(state['cards'][-1]['generation_approval']['prior_requests'],12)
        self.call(self.approve(state));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),16)
        self.assertEqual(final['generation']['progress']['inventory_progress']['pending_count'],0)
        self.assertEqual(final['generation']['progress']['budget']['cumulative_requests'],16)
        self.assertEqual(self.manager.store.read('checkpoint',key),parent)
        self.assertTrue(all(b['response_format']['json_schema']['name']=='twinpulse_semantic_batch' for b in self.wires[12:]))
        from twinpulse_app import ApplicationService
        from twinpulse_app.project_store import ProjectStore
        store=ProjectStore(self.static/'active_project.json');before=store.path.read_bytes()
        restored=ApplicationService(None,project_store=store)
        self.assertEqual(restored.site_draft.to_dict(),self.workflow._application.site_draft.to_dict())
        self.assertEqual(store.path.read_bytes(),before)

    def test_large_inventory_hard_exhaustion_is_not_reset_by_a_larger_saved_policy(self):
        import sys
        sys.path.insert(0,str(r5.ROOT/'packages/twinpulse_provider/tests'))
        from test_inventory_work import many_objects
        raw,inventory,batches=many_objects()
        self.responses=[raw,inventory,*batches];self.install_audited_fixture()
        first=self.call({'action':'message','request_id':uuid4().hex,'text':'Estimate these observed objects',
            'mode':'new','attachment':{'name':'fixture.png','media_type':'image/png','content_base64':base64.b64encode(r5.png()).decode()}})
        self.call(self.approve(self.call(self.answer(first))));failed=self.finish()
        self.assertEqual(failed['generation']['state'],'failed')
        progress=failed['generation']['progress']
        self.assertEqual(progress['budget']['stop_reason'],'NEEDS_REQUEST_BUDGET')
        self.assertEqual(len(self.wires),11)
        key=progress['checkpoint_id'];original=self.manager.store.read('checkpoint',key)
        self.route['generation_policy']['max_requests']=24
        self.routes.save(self.route,lambda:None);self.install_audited_fixture()
        offered=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':failed['generation']['operation_id']})
        self.call(self.approve(offered));resumed=self.finish()
        self.assertEqual(resumed['generation']['state'],'failed')
        self.assertEqual(resumed['generation']['progress']['budget']['stop_reason'],'NEEDS_REQUEST_BUDGET')
        self.assertEqual(resumed['generation']['progress']['budget']['requests'],0)
        self.assertEqual(resumed['generation']['progress']['budget']['cumulative_requests'],11)
        self.assertEqual(len(self.wires),11)
        self.assertEqual(self.manager.store.read('checkpoint',key),original)
        retained=resumed['generation']['progress']['inventory_progress']
        self.assertEqual((retained['inventory_count'],retained['parameterized_count'],retained['pending_count']),(60,36,24))

    def test_unknown_blocks_then_explicit_late_settlement_derives_new_checkpoint(self):
        self.responses=[structure(),'length'];self.install_audited_fixture()
        self.call(self.approve(self.begin()));failed=self.finish()
        key=failed['generation']['progress']['checkpoint_id'];parent=self.manager.store.read('checkpoint',key)
        unknown=deepcopy(parent);unknown['budget']['in_flight']=parent['budget']['attempts'][-1]['attempt_id']
        unknown['budget']['attempts'][-1].update(settled=False,status='outcome_unknown')
        self.manager.store.save('checkpoint',key,unknown)
        ledger_path=next(self.manager.root.glob('*.ledger.json'));ledger=json.loads(ledger_path.read_text())
        unresolved=deepcopy(ledger);unresolved['requests'][-1]['status']='outcome_unknown'
        # Test-only mechanical fault injection; never an actual billing repair.
        ledger_path.write_text(json.dumps(unresolved))
        with self.assertRaisesRegex(BrokerError,'unknown'):
            self.manager.reconcile(key)
        ledger_path.write_text(json.dumps(ledger))
        derived=self.manager.reconcile(key)
        self.assertNotEqual(derived,key);self.assertEqual(self.manager.store.read('checkpoint',key),unknown)
        value=self.manager.store.read('checkpoint',derived)
        self.assertIsNone(value['budget']['in_flight'])
        self.assertEqual(value['settlement_parent_checkpoint'],key)
        self.assertEqual(len(self.wires),4)
        # Raw/ledger disagreement must not qualify a resumed snapshot.
        row=ledger['requests'][-1];rawpath=self.manager.store.root.parent/(row['attempt_id']+'.json')
        raw=json.loads(rawpath.read_text());raw['model_id']='other';rawpath.write_text(json.dumps(raw))
        with self.assertRaisesRegex(BrokerError,'could not be matched'):
            self.manager.reconcile(key)

    def test_unpriced_or_expired_route_is_specific_and_zero_calls(self):
        self.install_audited_fixture();self.manager.prices={}
        state=self.begin();self.assertEqual(state['generation']['error']['code'],'generation_pricing_unavailable')
        self.assertEqual(self.wires,[])
        self.manager.clock=lambda:datetime(2026,10,17,tzinfo=timezone.utc)
        state=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':state['generation']['operation_id']})
        self.assertEqual(state['generation']['error']['code'],'generation_pricing_expired')
        self.assertEqual(self.wires,[])

    def test_photo_preview_lists_observer_and_planner_without_transmission(self):
        self.install_audited_fixture();state=self.begin(image=True)
        preview=state['cards'][-1]['generation_approval']
        self.assertEqual(preview['image_count'],1)
        self.assertEqual([m['stage'] for m in preview['models']],['observer','planner'])
        self.assertEqual(preview['models'][0]['full_context_reserve_usd'],'0.318')
        text=json.dumps(preview);self.assertNotIn('fixture-gpt',text);self.assertNotIn('content_base64',text)
        self.assertEqual(self.wires,[])

    def test_photo_calls_only_observer_with_image_then_text_only_planner(self):
        observed={'schema_version':'1.0','summary':'Synthetic image has no recognized objects',
            'entities':[],'relations':[],'dimensions':[],'ambiguities':['Scale unmeasured']}
        self.responses=[observed,structure(),furniture()];self.install_audited_fixture()
        self.call(self.approve(self.begin(image=True)));final=self.finish()
        self.assertEqual(final['generation']['state'],'completed',final['generation'])
        self.assertEqual(len(self.wires),6)
        self.assertEqual([w['response_format']['json_schema']['name'] for w in self.wires],
            ['twinpulse_room_observation','twinpulse_semantic_room','twinpulse_image_observation',
             'twinpulse_semantic_structure','twinpulse_model_resolution','twinpulse_semantic_batch'])
        observers=[self.wires[0],self.wires[2]]
        planners=[self.wires[index] for index in (1,3,4,5)]
        self.assertTrue(all('data:image/png;base64,' in json.dumps(wire) for wire in observers))
        self.assertNotIn('data:image',json.dumps(planners))
        self.assertEqual(self.wires[0]['model'],'gpt-5.4-mini-2026-03-17')
        for wire in observers:self.assertEqual(wire['max_completion_tokens'],4000)
        self.assertTrue(all(w['model']=='gpt-5.4-mini-2026-03-17' for w in observers))
        self.assertTrue(all(w['model']=='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B' for w in planners))

    def test_corrupt_checkpoint_blocks_review_without_a_new_call(self):
        self.responses=[structure(),'length'];self.install_audited_fixture()
        self.call(self.approve(self.begin()));failed=self.finish()
        key=failed['generation']['progress']['checkpoint_id']
        self.manager.store._path('checkpoint',key).write_text('{}')
        state=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':failed['generation']['operation_id']})
        self.assertEqual(state['generation']['error']['code'],'generation_checkpoint_invalid')
        self.assertEqual(len(self.wires),4)

    def test_restart_resolves_current_grant_if_progress_metadata_is_missing(self):
        self.responses=[structure(),'length'];self.install_audited_fixture()
        self.call(self.approve(self.begin()));failed=self.finish()
        key=failed['generation']['progress']['checkpoint_id']
        self.server.conversation._state['generation'].pop('progress')
        self.server.conversation._persist()
        from twinpulse_app.conversation_service import ConversationService
        self.server.conversation=ConversationService(self.workflow,self.server.conversation.path)
        restored=self.call();self.assertEqual(len(self.wires),4)
        state=self.call({'action':'generation_retry','request_id':uuid4().hex,'operation_id':restored['generation']['operation_id']})
        self.assertEqual(state['cards'][-1]['generation_approval']['checkpoint_id'],key)
        self.assertEqual(state['cards'][-1]['generation_approval']['prior_requests'],4)
        self.assertEqual(len(self.wires),4)
