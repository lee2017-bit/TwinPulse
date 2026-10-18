# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline integration contracts for ordinary model-bound harness snapshots.

No real API, model, credential read, robot, engine or network request is used.
Scripted transports exercise the production routing/composition/cache boundary;
these supplementary tests make no claim about live model quality.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from io import BytesIO
from email.message import Message
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_app.key_registry import KeyRegistry,KeyRegistryError
from twinpulse_app.settings import JsonProviderSettingsStore,provider_settings_preset
from twinpulse_app.stage_routing import StageRoutingSettings,build_configured_stage_service
from twinpulse_app.generation_scope import OrdinaryInferenceScope
from twinpulse_provider import CancellationToken,GenerationRequest,ImageInput,ProviderConfigurationError
from twinpulse_provider.harness_profiles import default_profile,edited_profile,binding
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.nebius_pipeline import ChatCompletion
from twinpulse_provider.stage_transport import ConfiguredStageTransport,explicit_json_contract,normalize_json_schema

OBSERVER='google/gemma-3-27b-it'
PLANNER='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
SCHEMA={'type':'object','additionalProperties':False,'properties':{'status':{'const':'checked'}},'required':['status']}


class OfflineCredential:
    values={}
    reads=[]
    def __init__(self,target):self.target_name=target
    def is_configured(self):return self.target_name in self.values
    def load(self):self.reads.append(self.target_name);raise AssertionError('No credential may be loaded by offline harness tests')
    def save(self,value):self.values[self.target_name]=value
    def delete(self):self.values.pop(self.target_name,None)


class RecordingTransport:
    def __init__(self):self.bodies=[]
    async def complete(self,body,token,config):
        self.bodies.append(deepcopy(body));return ChatCompletion('fixture',config.model_id,'{}','stop',{})


class BudgetedFixtureTransport(RecordingTransport):
    """Deterministic empty estimated room; never presented as live inference."""
    async def complete(self,body,token,config):
        self.bodies.append(deepcopy(body))
        attempt=token.generation_budget.reserve(body,role=token.generation_role)
        name=body['response_format']['json_schema']['name']
        room={'width_m':6,'length_m':6,'height_m':2.6}
        if name=='twinpulse_room_observation':value={'summary':'Offline estimated empty room','ambiguities':['Unmeasured fixture']}
        elif name=='twinpulse_semantic_room':value={'summary':'Offline estimated empty room','room':room}
        elif name=='twinpulse_image_observation':value={'schema_version':'1.0','summary':'Offline fixture no entities',
            'entities':[],'relations':[],'dimensions':[],'ambiguities':['Unmeasured fixture']}
        elif name=='twinpulse_semantic_structure':value={'summary':'Offline empty room','room':room,'inventory':[]}
        else:raise AssertionError('Unexpected fixture stage '+name)
        token.generation_budget.settle(attempt,status='received',usage={'prompt_tokens':5,'completion_tokens':10})
        return ChatCompletion(attempt,config.model_id,json.dumps(value),'stop',{'prompt_tokens':5,'completion_tokens':10},attempt_id=attempt)


class ModelHarnessIntegrationTests(unittest.TestCase):
    def test_library_schemas_use_the_existing_model_bound_recipe_and_observation_profiles(self):
        from twinpulse_provider.harness_profiles import apply_profile
        for role,model,name,stage in (
                ('planner',PLANNER,'twinpulse_library_recipe','recipe'),
                ('observer',OBSERVER,'twinpulse_asset_observation','observation')):
            profile=default_profile('nebius',model,role)
            body=dict(model=model,max_tokens=20000,response_format=dict(type='json_schema',json_schema=dict(
                name=name,schema=deepcopy(SCHEMA),strict=True)),messages=[dict(role='system',content='Host-owned typed Library rules')])
            composed=apply_profile(body,binding(profile))
            self.assertIn(profile['instructions'][stage],str(composed['messages']))
            self.assertEqual(composed['response_format'],body['response_format'])

    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.settings=JsonProviderSettingsStore(self.root/'settings.json');self.settings.save(provider_settings_preset('nebius_token_factory'))
        OfflineCredential.values={self.settings.load().credential_ref:'explicit-offline-placeholder'};OfflineCredential.reads=[]
        self.registry=KeyRegistry(self.settings,OfflineCredential(self.settings.load().credential_ref),OfflineCredential)
        self.routes=StageRoutingSettings(self.registry)
        self.route={'observer':{'key_id':'legacy','model_id':OBSERVER},'planner':{'key_id':'legacy','model_id':PLANNER}}
        self.original_settings=self.settings.path.read_bytes()

    def tearDown(self):
        self.assertEqual(OfflineCredential.reads,[])
        self.assertEqual(self.settings.path.read_bytes(),self.original_settings)

    def body(self,stage='planner',name='twinpulse_semantic_structure'):
        return {'model':OBSERVER if stage=='observer' else PLANNER,'max_tokens':100,'temperature':0,
            'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':deepcopy(SCHEMA)}},
            'messages':[{'role':'system','content':'Host validation and tool instructions.'},{'role':'user','content':'Explicit offline test input.'}]}

    def transport(self):
        service=build_configured_stage_service(self.registry)
        transport=service._provider._transport
        recorder=RecordingTransport();transport.transports={'observer':recorder,'planner':recorder}
        return service,transport,recorder

    def edit(self,stage,reference,*,marker):
        choice=self.routes.load()[stage]
        editor=self.routes.harness_action({'action':'harness_profile','operation':'draft','stage':stage,
            'key_id':choice['key_id'],'model_id':choice['model_id'],'reference':reference})['harness_editor']
        instructions=deepcopy(editor['profile']['instructions'])
        field='planning' if stage=='planner' else 'observation';instructions[field]+=' '+marker
        return self.routes.harness_action({'action':'harness_profile','operation':'save','stage':stage,
            'key_id':choice['key_id'],'model_id':choice['model_id'],'base_reference':reference,
            'id':editor['profile']['id'],'instructions':instructions})['harness_saved']

    def test_absent_and_legacy_load_do_not_migrate_or_change_existing_wire_body(self):
        self.assertIsNone(self.routes.load());self.assertIsNone(build_configured_stage_service(self.registry))
        self.assertFalse(self.routes.harness_store().root.exists())
        self.routes._save(self.route)  # Exact pre-harness on-disk shape.
        before=self.routes.path.read_bytes();self.assertEqual(self.routes.load(),self.route)
        service,transport,recorder=self.transport();original=explicit_json_contract(self.body())
        asyncio.run(transport.complete(original,CancellationToken(),service._config))
        self.assertEqual(recorder.bodies,[original]);self.assertIsNone(transport.harness_bindings)
        self.assertEqual(self.routes.path.read_bytes(),before);self.assertFalse(self.routes.harness_store().root.exists())

    def test_explicit_save_freezes_default_refs_and_exact_metadata_without_dispatch(self):
        changed=[];self.routes.save(self.route,lambda:changed.append(True))
        saved=self.routes.load();self.assertEqual(changed,[True]);self.assertNotEqual(saved,self.route)
        self.assertNotIn('harness_profile',self.route['planner'])
        frozen=self.routes.harness_bindings(saved);metadata=self.routes.metadata()
        self.assertEqual(metadata['harness_composer_revision'],'harness-profile-1.0')
        for stage in ('observer','planner'):
            ref=saved[stage]['harness_profile'];self.assertEqual(set(ref),{'id','revision','sha256'})
            self.assertEqual(ref['sha256'],frozen[stage]['sha256']);self.assertEqual(metadata[stage+'_harness_sha256'],ref['sha256'])
        self.assertEqual(len(list(self.routes.harness_store().root.glob('*.json'))),2)

    def test_edit_is_immutable_schema_preserving_and_other_model_cannot_borrow_ref(self):
        self.routes.save(self.route,lambda:None);saved=self.routes.load();reference=saved['planner']['harness_profile']
        path=self.routes.harness_store().root/(reference['sha256']+'.json');before=path.read_bytes()
        old_service,old_transport,old_recorder=self.transport()
        revised=self.edit('planner',reference,marker='OFFLINE_NEW_GUIDANCE')
        self.assertEqual(path.read_bytes(),before);self.assertNotEqual(revised['reference']['sha256'],reference['sha256'])
        self.assertEqual(self.routes.load(),saved)  # Saving instructions alone is not routing apply.
        next_route=deepcopy(saved);next_route['planner']['harness_profile']=revised['reference'];self.routes.save(next_route,lambda:None)
        new_service,new_transport,new_recorder=self.transport();body=self.body()
        asyncio.run(old_transport.complete(body,CancellationToken(),old_service._config))
        asyncio.run(new_transport.complete(body,CancellationToken(),new_service._config))
        self.assertNotIn('OFFLINE_NEW_GUIDANCE',old_recorder.bodies[0]['messages'][0]['content'])
        self.assertIn('OFFLINE_NEW_GUIDANCE',new_recorder.bodies[0]['messages'][0]['content'])
        self.assertEqual(new_recorder.bodies[0]['response_format']['json_schema']['schema'],normalize_json_schema(SCHEMA))
        self.assertEqual(body['messages'][0]['content'],'Host validation and tool instructions.')
        wrong=deepcopy(next_route);wrong['planner']['model_id']='nvidia/Nemotron-3_5-Lightning'
        with self.assertRaises(KeyRegistryError):self.routes.validate(wrong)
        stored=self.routes.harness_store().resolve(reference,provider='nebius',model=PLANNER,role='planner')
        self.assertEqual(stored,old_transport.harness_bindings['planner'])

    def test_explicit_null_legacy_survives_save_and_refuses_profile_changed_checkpoint_before_dispatch(self):
        legacy=deepcopy(self.route)
        for choice in legacy.values():choice['harness_profile']=None
        self.routes.save(legacy,lambda:None);self.assertEqual(self.routes.load(),legacy)
        self.assertIsNone(self.routes.harness_bindings(legacy));self.assertNotIn('harness_composer_revision',self.routes.metadata())
        service,transport,recorder=self.transport()
        profile=binding(default_profile('nebius',PLANNER,'planner'))
        policy=GenerationPolicy();provider=BudgetedPipeline(transport,policy=policy,store_root=self.root/'store',
            site_plan_version='2.2',observer_model_id=OBSERVER,planner_model_id=PLANNER)
        base=GenerationRequest('old-execution','Explicit offline room')
        parent={'input_sha256':input_digest(base),'approval_id':'ordinary-generation:old','request_id':base.request_id,
                'harness_bindings':{'planner':profile}}
        key=canonical_sha256(parent);provider.store.save('checkpoint',key,parent)
        scope=SimpleNamespace(approved_checkpoint_sha256=canonical_sha256(parent),approval_id='ordinary-generation:new')
        request=replace(base,request_id='new-execution',continuation_checkpoint=key,inference_scope=scope)
        with self.assertRaisesRegex(ProviderConfigurationError,'CONTINUATION_HARNESS_CHANGED'):
            asyncio.run(provider.generate(request,CancellationToken(),service._config))
        self.assertEqual(recorder.bodies,[]);self.assertFalse(list(self.root.glob('*.ordinary-scope.json')))

    def test_repair_role_retains_recipe_and_batch_instructions_plus_repair_guidance(self):
        self.routes.save(self.route,lambda:None);service,transport,recorder=self.transport()
        profile=transport.harness_bindings['planner']['profile'];token=CancellationToken();token.generation_role='repair'
        for schema,field in (('twinpulse_model_recipe','recipe'),('twinpulse_semantic_batch','batch')):
            asyncio.run(transport.complete(self.body(name=schema),token,service._config))
            content=recorder.bodies[-1]['messages'][0]['content']
            self.assertIn(profile['instructions'][field],content);self.assertIn(profile['instructions']['repair'],content)
            self.assertEqual(content.count('Response JSON Schema:'),1)
            self.assertEqual(recorder.bodies[-1]['response_format']['json_schema']['schema'],normalize_json_schema(SCHEMA))

    def test_observer_cache_is_profile_pinned_but_planner_edit_reuses_original_observation(self):
        selected=deepcopy(self.route);selected['generation_policy']=GenerationPolicy().to_dict();self.routes.save(selected,lambda:None)
        image=ImageInput('explicit-fixture.png','image/png',b'OFFLINE FIXTURE BYTES NOT A REAL PHOTO')
        request=GenerationRequest('unsubmitted','An estimated empty room',images=(image,))
        rates={model:{'input_per_million':1,'output_per_million':1,'context_tokens':131072,'source':'offline-fixture'} for model in (OBSERVER,PLANNER)}
        def run(identity):
            service=build_configured_stage_service(self.registry);provider=service._provider;recorder=BudgetedFixtureTransport()
            provider._transport.transports={'observer':recorder,'planner':recorder}
            scope=OrdinaryInferenceScope('ordinary-generation:'+identity,input_digest(request),provider.route_sha256,
                provider.policy.sha256,self.root/(identity+'-ledger.json'),rates,'5',provider.policy.max_requests)
            asyncio.run(provider.generate(replace(request,request_id=identity,inference_scope=scope),CancellationToken(),service._config))
            names=[body['response_format']['json_schema']['name'] for body in recorder.bodies]
            return provider,names
        first,names=run('first');self.assertIn('twinpulse_image_observation',names)
        old_policy=deepcopy(first.observer_wire_policy);old_ref=self.routes.load()['observer']['harness_profile']
        self.assertEqual(old_policy['harness_sha256'],old_ref['sha256'])
        selected=self.routes.load();edited=self.edit('planner',selected['planner']['harness_profile'],marker='PLANNER_ONLY_EDIT')
        selected['planner']['harness_profile']=edited['reference'];self.routes.save(selected,lambda:None)
        second,names=run('planner-edit');self.assertEqual(second.observer_wire_policy,old_policy)
        self.assertNotIn('twinpulse_image_observation',names);self.assertTrue(second.diagnostic_for('planner-edit')['observation_cache_hit'])
        selected=self.routes.load();edited=self.edit('observer',old_ref,marker='OBSERVER_CHANGED')
        selected['observer']['harness_profile']=edited['reference'];self.routes.save(selected,lambda:None)
        third,names=run('observer-edit');self.assertNotEqual(third.observer_wire_policy['harness_sha256'],old_policy['harness_sha256'])
        self.assertIn('twinpulse_image_observation',names)
        self.assertEqual(len(list(third.store.root.joinpath('observation').glob('*.json'))),2)

    def test_robot_registry_router_requires_session_and_csrf_without_binding_a_socket(self):
        from twinpulse_app.api import LocalApiServer,_Session
        from twinpulse_app.command_broker import CommandBroker
        from twinpulse_app.workspace_devices import WorkspaceDevices
        from twinpulse_app.robot_registry_service import RobotRegistryService
        devices=WorkspaceDevices()
        devices.registry_service=RobotRegistryService(devices,self.root/'devices',
            discoverer=lambda:(_ for _ in ()).throw(AssertionError('No discovery requested')))
        with patch('socket.socket',side_effect=AssertionError('No socket is allowed')):
            api=LocalApiServer(CommandBroker(),product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,virtual=True)
            api._httpd=SimpleNamespace(server_address=('127.0.0.1',8765))  # Address metadata only; no server/socket.
            api.workspace_devices=devices
            api._sessions['offline-session']=_Session('offline-session','product','offline-csrf',float('inf'),float('inf'))
            def request(method,body=None,*,authenticated=True,csrf='offline-csrf'):
                raw=json.dumps(body).encode() if body is not None else b'';status=[]
                headers={'Host':'127.0.0.1:8765','Content-Type':'application/json','Content-Length':str(len(raw))}
                if authenticated:headers['Cookie']='twinpulse_product=offline-session'
                if csrf is not None:headers['X-TwinPulse-CSRF']=csrf
                message=Message()
                for key,value in headers.items():message[key]=value
                incoming=SimpleNamespace(command=method,path='/v1/product/robots',headers=message,rfile=BytesIO(raw),wfile=BytesIO(),
                    connection=SimpleNamespace(gettimeout=lambda:30,settimeout=lambda _:None),
                    send_response=lambda value:status.append(value),send_header=lambda *_:None,end_headers=lambda:None)
                api._handle(incoming)
                return status[-1],json.loads(incoming.wfile.getvalue())
            status,_=request('GET',authenticated=False);self.assertEqual(status,401)
            status,state=request('GET');self.assertEqual(status,200);self.assertEqual(len(state['robots']),0)
            body={'action':'register','expected_revision':state['revision'],'label':'Explicit offline registered robot',
                'adapter_id':'unreviewed','endpoint':{'host':'test-robot.local','user':'twinpulse','port':22,'ros_domain_id':86}}
            status,_=request('POST',body,csrf='wrong');self.assertEqual(status,403)
            self.assertEqual(len(devices.registry_service.snapshot('offline-session')['robots']),0)
            status,result=request('POST',body);self.assertEqual(status,200)
            self.assertEqual(result['revision'],state['revision']+1);self.assertEqual(len(result['robots']),1)
            self.assertEqual(result['active_id'],state['active_id'])
            devices.close()


if __name__=='__main__':unittest.main()
