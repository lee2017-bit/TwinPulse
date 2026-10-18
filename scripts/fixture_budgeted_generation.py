# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit zero-network recovery fixture for the existing actual Isaac journey.

Not a production fallback, photo answer or LLM-quality sample. Only responses
are scripted; semantic compiler, workflow, storage, Build and SIM stay real.
"""
from copy import deepcopy
import json
from pathlib import Path

from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.nebius_pipeline import ChatCompletion, ObservationArtifact
from twinpulse_provider.semantic_scene import scene_draft, checked_structure, checked_batch, revision, PATCH_REVISION
from twinpulse_core.model_library import library_models


class RecoveryFixture:
    def __init__(self, request, store_root, observer_model, planner_model):
        if request.images:
            raise ValueError('This explicit recovery fixture is text-only')
        self.structure = {'summary': 'Explicit estimated recovery fixture, not image reconstruction',
            'room': {'width_m': 2, 'length_m': 2, 'height_m': 2.6}, 'inventory': [
                {'id': kind, 'kind': kind, 'evidence_ref': 'text:0'} for kind in ('bed', 'desk')]}
        self.objects = {}
        models = {model['kind']: model['model_id'] for model in library_models()}
        for kind, size, region, variant in (
            ('bed', [1.5, 2., .9], 'rear_left', 'double'),
            ('desk', [1.1, .6, .74], 'rear_right', 'metal')):
            self.objects[kind] = {'region': region, 'yaw_deg': 0, 'model_id': models[kind],
                'dimensions_m': size, 'variant': variant, 'finish': 'white',
                'placement': {'relation': 'floor', 'parent_id': None, 'part': None,
                              'anchor': 'centre', 'elevation_m': None}}
        observation = ObservationArtifact.from_mapping({'schema_version': '1.0', 'summary': 'Explicit text fixture',
            'entities': [], 'relations': [], 'dimensions': [], 'ambiguities': ['Unmeasured']})
        candidate = checked_batch(self.objects, scene_draft(checked_structure(self.structure, request, observation,
            bound=True)), ['bed', 'desk'])
        self.responses = [self.structure, self.objects, {'patch_version': PATCH_REVISION,
            'base_revision': revision(candidate), 'operations': [{'op': 'room',
                'value': {'width_m': 6, 'length_m': 6, 'height_m': 2.6}}]}]
        self.stages = []
        self.root = Path(store_root)
        self.provider = BudgetedPipeline(self, policy=GenerationPolicy(), store_root=self.root/'checkpoints',
            observer_model_id=observer_model, planner_model_id=planner_model,
            site_plan_version='2.2', planner_template_no_thinking=True,
            stage_output_token_caps={'observer': 4000, 'planner': 20000})

    async def complete(self, body, token, _config):
        budget = token.generation_budget
        identity = budget.reserve(body, role=token.generation_role)
        self.stages.append(body['response_format']['json_schema']['name'])
        assert body['max_tokens'] == 20000
        assert body['chat_template_kwargs'] == {'enable_thinking': False}
        value = self.responses.pop(0)
        budget.settle(identity, status='received', usage={'prompt_tokens': 10, 'completion_tokens': 20})
        return ChatCompletion(identity, body['model'], json.dumps(value), 'stop',
                              {'prompt_tokens': 10, 'completion_tokens': 20}, attempt_id=identity)

    async def generate(self, request, token, config):
        result = await self.provider.generate(request, token, config)
        assert not self.responses
        budget = result.provenance['budget']
        assert budget['requests'] == 3 and budget['repairs'] == 1
        self.root.mkdir(parents=True, exist_ok=True)
        # Test evidence only, never credentials, prompts or private reasoning.
        (self.root/'recovery-result.json').write_text(json.dumps({
            'schema_version': 'budgeted-recovery-fixture-1.0', 'request_id': request.request_id,
            'stages': self.stages, 'provenance': deepcopy(result.provenance),
            'network_calls': 0, 'physical_authority': False}, indent=2), encoding='utf-8')
        return result
