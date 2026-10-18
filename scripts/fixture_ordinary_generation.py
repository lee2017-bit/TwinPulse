# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit isolated zero-network HTTP fixture for ordinary approval acceptance.

Only the credential store and HTTP response source are test replacements.
Production approval, scope, audit, compiler, persistence and Isaac stay real.
Never imported by the production launcher, never reads a real saved key.
"""
from datetime import datetime, timezone
from copy import deepcopy
from dataclasses import replace
import json
import os
from uuid import uuid4


def install(backend):
    from scripts.fixture_budgeted_generation import RecoveryFixture
    from twinpulse_app.key_registry import KeyRegistry
    from twinpulse_app.settings import provider_settings_preset
    from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service
    from twinpulse_app.generation_approval import GenerationApprovals
    from twinpulse_provider.generation_policy import GenerationPolicy
    from twinpulse_provider.reliability import AuditedChatTransport
    from twinpulse_provider import GenerationRequest
    fixture = RecoveryFixture(GenerationRequest('fixture', 'bed and desk'), '.', 'unused',
        'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B')
    responses = [fixture.responses[0], 'length', *fixture.responses[1:]]
    render_review = os.environ.get('TWINPULSE_RENDER_REVIEW_FIXTURE')=='1'
    if render_review:
        # Generic synthetic scene only; no historical/private bedroom answer.
        observation={'schema_version':'1.1','summary':'Synthetic source fixture; unmeasured',
            'entities':[dict(id='seen_'+kind,kind='static_obstacle',description=kind,confidence=.9,
                role='object',category=kind,region='unknown',spatial_confidence=.9) for kind in ('bed','desk')],
            'relations':[],'dimensions':[],'ambiguities':['Unmeasured synthetic input']}
        structure=deepcopy(fixture.structure);structure['room']={'width_m':6,'length_m':6,'height_m':2.6}
        for item in structure['inventory']:item['evidence_ref']='seen:seen_'+item['id']
        objects=deepcopy(fixture.objects)
        def critic(body, contradiction=False):
            props=body['response_format']['json_schema']['schema']['properties']
            constant=lambda key:props[key].get('const',(props[key].get('enum') or [None])[0])
            return dict(review_version=constant('review_version'),frame_key=constant('frame_key'),
                objects={identity:{aspect:dict(status='contradiction' if contradiction and identity=='bed' and aspect=='layout'
                    else 'consistent',confidence=.9,reason='Scripted test assertion, not actual visual judgement.')
                    for aspect in ('layout','support','appearance')} for identity in props['objects']['properties']})
        def patch(body):
            from twinpulse_provider.semantic_scene import PATCH_REVISION
            return dict(patch_version=PATCH_REVISION,base_revision='bound-below',
                operations=[dict(op='update',id='bed',value=dict(objects['bed'],region='front_left'))])
        responses=[observation,structure,objects,lambda body:critic(body,True),patch,critic]
    class Credential:
        values = {}
        def __init__(self, target): self.target = target
        @property
        def target_name(self): return self.target
        def is_configured(self): return self.target in self.values
        def load(self): return self.values.get(self.target)
        def save(self, value): self.values[self.target] = value
        def delete(self): self.values.pop(self.target, None)
    holder = {}
    def registry_factory(store, credential):
        store.save(provider_settings_preset('nebius_token_factory'))
        Credential.values[store.load().credential_ref] = 'isolated-test-nebius'
        registry = KeyRegistry(store, credential, Credential)
        entry = registry.register({'name':'Isolated GPT fixture', 'provider_profile':'openai',
            'model_id':'gpt-5.4-mini', 'api_key':'isolated-test-gpt'})['entries'][-1]['id']
        routes = StageRoutingSettings(registry)
        routes.save({'observer':{'key_id':entry,'model_id':'gpt-5.4-mini'},
            'planner':{'key_id':'legacy','model_id':'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
                'thinking_mode':'disabled'},'generation_policy':replace(GenerationPolicy(),external_final_review=True,
                    final_timeout_s=180,total_timeout_s=1020).to_dict() if render_review else GenerationPolicy().to_dict()},lambda:None)
        holder.update(registry=registry, routes=routes, root=store.path.parent)
        return registry
    class Response:
        def __init__(self, url, body): self.url,self.body=url,body
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def geturl(self): return self.url
        def read(self, *_): return self.body
    def opener(request, **_):
        body = json.loads(request.data)
        value = responses.pop(0)
        if callable(value):value=value(body)
        # The host binds the patch to the current input/evidence revision.
        # A standalone fixture's candidate has different provenance; reuse
        # only its operation, never its precomputed revision as live evidence.
        schema = body['response_format']['json_schema']['schema']
        if isinstance(value, dict) and 'base_revision' in value:
            binding = schema['properties']['base_revision']
            expected = binding['const'] if 'const' in binding else binding['enum'][0]
            value = dict(value, base_revision=expected)
        finish, content = ('length','') if value == 'length' else ('stop',json.dumps(value))
        return Response(request.full_url,json.dumps({'id':uuid4().hex,'model':body['model'],
            'choices':[{'finish_reason':finish,'message':{'content':content}}],
            'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}).encode())
    original_transport = AuditedChatTransport.__init__
    def transport_init(self, *args, **kwargs):
        original_transport(self, *args, **kwargs, opener=opener)
    AuditedChatTransport.__init__ = transport_init
    original_workflow = backend.ProductWorkflow
    def workflow(*args, **kwargs):
        kwargs['generation_settings_getter'] = holder['routes'].metadata
        value = original_workflow(*args, **kwargs)
        value.generation_approvals = GenerationApprovals(holder['registry'], value,
            clock=lambda:datetime(2026,10,9,8,tzinfo=timezone.utc))
        return value
    backend.WindowsCredentialStore = Credential
    backend.KeyRegistry = registry_factory
    backend.GenerationService = lambda *args, **kwargs: build_configured_stage_service(holder['registry'],
        evidence_root=holder['root']/'provider-evidence')
    backend.ProductWorkflow = workflow
