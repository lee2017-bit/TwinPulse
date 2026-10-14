# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Persistent credential-free stage choices for the ordinary product gateway.

Evaluation scopes/ledgers remain independent; saving this file never dispatches.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from .key_registry import KeyRegistryError
from .settings import NEBIUS_BASE_URL, NEBIUS_PLANNER_MODEL_ID
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT
from twinpulse_provider.output_diagnostics import MAX_STAGE_OUTPUT_TOKENS

MODELS = {
    'observer': {
        'openai': ('gpt-5.4-mini', 'gpt-6-luna'),
        'nebius': ('google/gemma-3-27b-it', 'openbmb/MiniCPM-V-4_5', 'deepseek-ai/DeepSeek-V4.1-Flash', 'Qwen/Qwen3.8-27B'),
    },
    'planner': {
        'openai': ('gpt-5.4-mini', 'gpt-6-luna'),
        'nebius': (NEBIUS_PLANNER_MODEL_ID, 'nvidia/Nemotron-3_5-Lightning'),
    },
}
DEFAULT_OUTPUT_TOKENS = {'observer': 4000, 'planner': 20000}
MAX_OUTPUT_TOKENS = MAX_STAGE_OUTPUT_TOKENS
DEFAULT_GENERATION_TIMEOUT_S = 90
MAX_GENERATION_TIMEOUT_S = 300
PHYSICAL_AI_OBSERVER = 'deepseek-ai/DeepSeek-V4.1-Flash'
PHYSICAL_AI_PLANNER = 'nvidia/nemotron-3-super-120b-a12b'
PHYSICAL_AI_PROFILE = 'physical-ai-flash-super-1.0'


def configured_model(choice, provider):
    # Preserve the existing mini snapshot pin; other explicit models must not
    # silently resolve to mini. The route validator guards the allowed IDs.
    return OPENAI_MINI_SNAPSHOT if provider=='openai' and choice['model_id']=='gpt-5.4-mini' else choice['model_id']


def configured_reasoning(choice, settings):
    # Reviewed Luna Chat Completions structured/function mode. This exact
    # transport mode is disclosed in metadata before ordinary approval.
    return 'none' if choice['model_id']=='gpt-6-luna' else settings.reasoning_effort


class StageRoutingSettings:
    def __init__(self, registry):
        self.registry = registry
        self.path = registry.settings.path.with_name('provider_stage_routing.json')

    def model_catalog(self, route):
        if not route or 'model_catalog_sha256' not in route:return None
        from twinpulse_provider.model_contracts import load_catalog
        try:
            return load_catalog(self.path.with_name('stage_model_catalog.json'),route['model_catalog_sha256'])
        except (ValueError, OSError, TypeError):
            raise KeyRegistryError('stage_model_catalog_invalid', '동결된 모델 목록이 변경되거나 잘못되었습니다. 원본은 보존했고 요청하지 않습니다.', 409) from None

    def supports(self, route, stage, provider, model):
        catalog=self.model_catalog(route)
        if catalog and provider=='nebius':
            from twinpulse_provider.model_contracts import model_supported
            return model_supported(catalog,stage,model)
        return model in MODELS[stage][provider]

    def available_catalog(self):
        """Read installed metadata for an unsaved choice, without a lookup.

        Saved routes keep their own digest pin; this never repairs a changed
        saved catalog or replaces a selected model.
        """
        from twinpulse_provider.model_contracts import catalog_sha, load_catalog
        path = self.path.with_name('stage_model_catalog.json')
        try:
            if path.stat().st_size > 262144:
                return None
            value = json.loads(path.read_text(encoding='utf-8'))
            return load_catalog(path, catalog_sha(value), now=datetime.now(timezone.utc))
        except (OSError, ValueError, TypeError):
            return None

    def physical_ai_recommendation(self, options, catalog):
        from twinpulse_provider.generation_policy import GenerationPolicy
        from twinpulse_provider.model_contracts import catalog_sha, checked_catalog
        if catalog is None:
            return None
        try:
            checked_catalog(catalog, now=datetime.now(timezone.utc))
        except ValueError:
            return None
        result = {}
        for stage, model in (('observer', PHYSICAL_AI_OBSERVER), ('planner', PHYSICAL_AI_PLANNER)):
            choice = next((v for v in options[stage] if v['provider'] == 'nebius'
                           and v['configured'] and v['model_id'] == model), None)
            contract = next((v for v in catalog['models'] if v['model_id'] == model), None)
            if choice is None or contract is None or contract['context_tokens'] <= 40000:
                return None
            result[stage] = {k: choice[k] for k in ('key_id', 'model_id')}
            result[stage]['max_output_tokens'] = 40000
        result.update(generation_policy=GenerationPolicy().to_dict(),
                      model_catalog_sha256=catalog_sha(catalog))
        return result

    @staticmethod
    def provider(value):
        if value.provider_profile == 'openai' and value.base_url == 'https://api.openai.com/v1/':
            return 'openai'
        if value.provider_profile in {'nebius_token_factory', 'nebius_site_v2'} and value.base_url == NEBIUS_BASE_URL:
            return 'nebius'
        raise KeyRegistryError('stage_provider_unsupported', '이 단계는 등록된 OpenAI 또는 Nebius 주소만 지원합니다.')

    def validate(self, route):
        if route is None:
            return None
        if (not isinstance(route, dict) or not {'observer', 'planner'} <= set(route)
                or set(route) - {'observer', 'planner', 'generation_timeout_s', 'generation_policy', 'model_catalog_sha256'}):
            raise KeyRegistryError('stage_route_invalid', '사진 분석과 설계·수정 설정을 함께 선택하세요.')
        result = {}
        if 'model_catalog_sha256' in route and 'generation_policy' not in route:
            raise KeyRegistryError('stage_catalog_policy_required', '확장 모델은 별도 생성 승인 정책이 필요합니다. 요청하지 않습니다.',409)
        if (isinstance(route.get('planner'), dict)
                and route['planner'].get('model_id') == PHYSICAL_AI_PLANNER
                and not {'generation_policy', 'model_catalog_sha256'} <= set(route)):
            raise KeyRegistryError('stage_catalog_policy_required',
                'Super 설계는 검증된 모델 목록과 생성 정책을 함께 적용해야 합니다.', 409)
        timeout = route.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)
        if type(timeout) is not int or not 1 <= timeout <= MAX_GENERATION_TIMEOUT_S:
            raise KeyRegistryError('stage_timeout_invalid', '전체 생성 대기시간은 1~300초 사이 정수여야 합니다.')
        for stage in ('observer', 'planner'):
            choice = route[stage]
            if (not isinstance(choice, dict) or not {'key_id', 'model_id'} <= set(choice)
                    or set(choice) - {'key_id', 'model_id', 'max_output_tokens', 'thinking_mode'}
                    or not all(isinstance(choice[k], str) for k in ('key_id', 'model_id'))):
                raise KeyRegistryError('stage_route_invalid', '단계별 키와 모델 형식이 잘못되었습니다.')
            cap = choice.get('max_output_tokens', DEFAULT_OUTPUT_TOKENS[stage])
            if type(cap) is not int or not 1 <= cap <= MAX_OUTPUT_TOKENS:
                raise KeyRegistryError('stage_output_limit_invalid', '출력 한도는 1~40,000 사이 정수여야 합니다.')
            value = self.registry.settings_for_entry(choice['key_id'])
            provider = self.provider(value)
            if not self.supports(route,stage,provider,choice['model_id']):
                raise KeyRegistryError('stage_model_unsupported', '해당 공급자·단계에서 지원하는 모델을 선택하세요.')
            catalog = self.model_catalog(route)
            if catalog and provider == 'nebius':
                model = next(r for r in catalog['models'] if r['model_id'] == choice['model_id'])
                if cap >= model['context_tokens']:
                    raise KeyRegistryError('stage_output_context_invalid',
                        '출력 한도가 모델 전체 문맥 이상입니다. 입력을 위한 여유가 필요하며 요청하지 않습니다.')
            mode = choice.get('thinking_mode', 'default')
            if mode not in ('default', 'disabled') or (mode == 'disabled' and (
                    stage != 'planner' or provider != 'nebius' or choice['model_id'] not in
                    (NEBIUS_PLANNER_MODEL_ID, 'nvidia/Nemotron-3_5-Lightning'))):
                raise KeyRegistryError('stage_thinking_unsupported', '추론 비활성화는 지원되는 Nemotron 설계 모델에서만 가능합니다.')
            result[stage] = dict(choice)
        if 'generation_timeout_s' in route:
            result['generation_timeout_s'] = timeout
        if 'model_catalog_sha256' in route:
            result['model_catalog_sha256']=route['model_catalog_sha256']
        if 'generation_policy' in route:
            from twinpulse_provider.generation_policy import GenerationPolicy
            from twinpulse_provider.errors import ProviderConfigurationError
            try:
                policy = GenerationPolicy.from_dict(route['generation_policy'])
                result['generation_policy'] = policy.to_dict()
            except ProviderConfigurationError:
                raise KeyRegistryError('generation_policy_invalid', '새 생성 정책의 한도·시간 배분을 확인하세요.') from None
        return result

    def load(self):
        if not self.path.exists():
            return None
        try:
            if self.path.stat().st_size > 8192:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if set(data) != {'schema_version', 'route'} or data['schema_version'] != '1.0':
                raise ValueError()
            return self.validate(data['route'])
        except Exception:
            raise KeyRegistryError('stage_routing_corrupt', '단계 설정을 읽지 못했습니다. 원본은 보존했고 다른 공급자로 전환하지 않습니다.', 500) from None

    def _save(self, route):
        temporary = self.path.with_name(f'.{self.path.name}.{uuid4().hex}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open('xb') as stream:
                stream.write(json.dumps({'schema_version': '1.0', 'route': route}, ensure_ascii=False).encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, route, changed):
        with self.registry.lock:
            selected = self.validate(route)
            if selected:
                for stage in ('observer', 'planner'):
                    choice = selected[stage]
                    if not self.registry.resolve(self.registry.settings_for_entry(choice['key_id'])).is_configured():
                        raise KeyRegistryError('key_missing', '선택한 단계의 보안 키가 없습니다.', 409)
            previous = self.load()
            try:
                self._save(selected)
                try:
                    changed()  # gateway reconstruction only
                except Exception:
                    self._save(previous)
                    changed()
                    raise KeyRegistryError('stage_switch_failed', '단계 설정 적용에 실패해 이전 조합으로 복구했습니다.', 409) from None
            except KeyRegistryError:
                raise
            except Exception:
                raise KeyRegistryError('stage_settings_storage_failed', '설정 저장 또는 복구에 실패했습니다. 저장 상태를 다시 확인하세요.', 500) from None

    def state(self, entries):
        from twinpulse_provider.generation_policy import GenerationPolicy
        route = self.load()
        options = {stage: [] for stage in MODELS}
        catalog=self.model_catalog(route) or self.available_catalog()
        for entry in entries:
            value = self.registry.settings_for_entry(entry['id'])
            try:
                provider = self.provider(value)
            except KeyRegistryError:
                continue
            for stage in MODELS:
                models=MODELS[stage][provider]
                if catalog and provider=='nebius':
                    from twinpulse_provider.model_contracts import model_supported
                    models=tuple(r['model_id'] for r in catalog['models'] if model_supported(catalog,stage,r['model_id']))
                for model in models:
                    options[stage].append({'key_id': entry['id'], 'model_id': model,
                        'provider': provider, 'key_name': entry['name'], 'configured': entry['configured'],
                        'wire_model_id': configured_model({'model_id': model}, provider)})
        recommended = self.physical_ai_recommendation(options, catalog)
        return {'schema_version': '1.0', 'enabled': route is not None, 'route': route,
            'recommended': recommended, 'options': options,
            'recommended_profile': PHYSICAL_AI_PROFILE,
            'recommended_name': 'DeepSeek V4.1 Flash + Nemotron 3 Super 120B · Nebius',
            'recommended_unavailable_reason': None if recommended else
                'Register a Nebius key and install current reviewed model metadata for Flash and Super.',
            'network_called': False, 'automatic_fallback': False,
            'default_output_tokens': DEFAULT_OUTPUT_TOKENS, 'max_output_tokens': MAX_OUTPUT_TOKENS,
            'default_generation_timeout_s': DEFAULT_GENERATION_TIMEOUT_S,
            'max_generation_timeout_s': MAX_GENERATION_TIMEOUT_S,
            'stop_on_output_limit': True,
            'generation_policy_default': GenerationPolicy().to_dict(),
            'generation_policy_requires_separate_approval': True,
            'note': 'Saving sends no model, authentication-test or robot request. Changes do not apply to an in-flight generation.'}

    def metadata(self):
        from twinpulse_provider.scene_contract import PROPOSAL_REVISION
        route = self.load()
        if route is None:
            return None
        result = {'adapter_kind': 'configured_stage_chat_pipeline', 'provider_profile': 'stage_routing',
            'endpoint_path': 'chat/completions', 'site_plan_version': '2.2', 'request_schema': PROPOSAL_REVISION,
            'image_detail': 'auto',
            'generation_timeout_s': str(route.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S))}
        for stage in ('observer', 'planner'):
            choice = route[stage]
            value = self.registry.settings_for_entry(choice['key_id'])
            provider = self.provider(value)
            prefix = 'observer_' if stage == 'observer' else ''
            result[prefix + 'base_url'] = value.base_url
            result[prefix + 'model_id'] = configured_model(choice,provider)
            result[stage + '_max_output_tokens'] = str(choice.get('max_output_tokens', DEFAULT_OUTPUT_TOKENS[stage]))
            if stage == 'observer':
                result['reasoning_effort'] = configured_reasoning(choice,value)
            else:
                result['planner_reasoning_effort'] = configured_reasoning(choice,value)
            if 'thinking_mode' in choice:
                result[stage + '_thinking_mode'] = choice['thinking_mode']
        if 'generation_policy' in route:
            from twinpulse_provider.generation_policy import GenerationPolicy
            policy = GenerationPolicy.from_dict(route['generation_policy'])
            result['generation_policy_sha256'] = policy.sha256
            # Metadata is part of approval/input identity. Report the effective
            # per-request timeout, not the ignored legacy route default.
            result['generation_timeout_s'] = str(policy.per_call_timeout_s)
            result['request_schema'] = 'semantic-scene-1.0'
        if 'model_catalog_sha256' in route:result['model_catalog_sha256']=route['model_catalog_sha256']
        return result


def build_configured_stage_service(registry, *, evidence_root=None, campaign=None):
    """Ordinary App path. Cannot borrow an evaluation campaign's authorization."""
    from twinpulse_provider import GenerationService, ProviderConfig, ProviderCapabilities, ProviderConfigurationError
    from twinpulse_provider import NebiusChatCompletionsPipelineProvider
    from twinpulse_provider.reliability import AuditedChatTransport, InferenceEvidence
    from twinpulse_provider.stage_transport import ConfiguredStageTransport
    if campaign is not None:
        raise ProviderConfigurationError('Production stage settings cannot reuse a host evaluation campaign')
    routes = StageRoutingSettings(registry)
    route = routes.load()
    if route is None:
        return None
    configs, transports, providers, reasoning = {}, {}, {}, {}
    policy = None
    if 'generation_policy' in route:
        from twinpulse_provider.generation_policy import GenerationPolicy
        policy = GenerationPolicy.from_dict(route['generation_policy'])
    timeout = policy.per_call_timeout_s if policy else route.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)
    for stage in ('observer', 'planner'):
        choice = route[stage]
        settings = registry.settings_for_entry(choice['key_id'])
        providers[stage] = routes.provider(settings)
        credential = registry.resolve(settings)
        if not credential.is_configured():
            raise KeyRegistryError('key_missing', '선택한 단계의 보안 키가 없습니다.', 409)
        configs[stage] = ProviderConfig(settings.base_url, 'chat/completions',
            configured_model(choice,providers[stage]),
            'UNUSED_SECURE_STORE', ProviderCapabilities(True, True, 1, settings.accepted_mime_types),
            timeout_s=float(timeout), max_attempts=1)
        transports[stage] = AuditedChatTransport(credential.load,
            InferenceEvidence(evidence_root or registry.settings.path.parent/'provider-evidence'))
        reasoning[stage] = configured_reasoning(choice,settings)
    transport = ConfiguredStageTransport(transports, configs, providers, reasoning,
        model_catalog=routes.model_catalog(route))
    class ConfiguredPipeline(NebiusChatCompletionsPipelineProvider):
        @property
        def name(self):
            return f"{configs['observer'].model_id} via {providers['observer']} observation + {configs['planner'].model_id} via {providers['planner']} planning"
    options = dict(
        observer_model_id=configs['observer'].model_id, planner_model_id=configs['planner'].model_id,
        site_plan_version='2.2', max_repairs=1,
        planner_template_no_thinking=route['planner'].get('thinking_mode') == 'disabled',
        stage_output_token_caps={stage:route[stage].get('max_output_tokens', DEFAULT_OUTPUT_TOKENS[stage])
                                 for stage in ('observer', 'planner')})
    if policy:
        from twinpulse_core import canonical_sha256
        from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
        provider = BudgetedPipeline(transport, policy=policy,
            store_root=(evidence_root or registry.settings.path.parent/'provider-evidence')/'generation-store',
            route_sha256=canonical_sha256(route), observer_wire_policy={
                'base_url':configs['observer'].base_url, 'provider':providers['observer'],
                'reasoning_effort':reasoning['observer']}, **options)
    else:
        provider = ConfiguredPipeline(transport, **options)
    return GenerationService(provider, configs['planner'], plan_version='2.2')
