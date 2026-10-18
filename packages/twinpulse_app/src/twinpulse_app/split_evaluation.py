# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Host-only approved mixed-provider evaluation; no browser-created approval."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from twinpulse_provider import GenerationService, ProviderConfigurationError
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT
from twinpulse_provider.reliability import CampaignLedger, AuditedChatTransport, InferenceEvidence, utc_now
from .settings import JsonProviderSettingsStore
from .key_registry import KeyRegistry
from .credentials import WindowsCredentialStore
from .provider_composition import build_split_generation_service

NANO = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'


class SplitEvaluationLedger(CampaignLedger):
    """One shared call/budget ledger, but credentials and HTTP origins stay separate."""
    def __init__(self, *args, openai_planner=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.openai_planner = openai_planner

    @staticmethod
    def text_input_bound(body):
        messages = body.get('messages')
        if (not isinstance(messages, list) or not 1 <= len(messages) <= 4
                or any(not isinstance(m, dict) or not isinstance(m.get('content'), str) for m in messages)
                or 'data:image/' in json.dumps(body)):
            raise ProviderConfigurationError('Planner permits bounded text-only messages')
        return len(json.dumps(body, ensure_ascii=False).encode('utf-8')) + 4096

    @staticmethod
    def image_input_bound(body):
        bounded = deepcopy(body)
        messages = bounded.get('messages')
        if not isinstance(messages, list) or not 1 <= len(messages) <= 4:
            raise ProviderConfigurationError('Observer message bound exceeded')
        images = 0
        for message in messages:
            content = message.get('content')
            if isinstance(content, list):
                for part in content:
                    if part.get('type') == 'image_url':
                        images += 1
                        if not part.get('image_url', {}).get('url', '').startswith('data:image/jpeg;base64,'):
                            raise ProviderConfigurationError('Evaluation permits its approved JPEG only')
                        part['image_url']['url'] = '[IMAGE_NOT_LOGGED]'
                    elif part.get('type') != 'text':
                        raise ProviderConfigurationError('Unsupported input modality')
        if images != 1:
            raise ProviderConfigurationError('Exactly one approved image required')
        return len(json.dumps(bounded, ensure_ascii=False).encode('utf-8')) + 4096 + 36000

    def reserve(self, body):
        if self.path.with_suffix('.continued-to').exists():
            raise ProviderConfigurationError('This evaluation ledger is read-only after continuation')
        if body.get('model') == NANO:
            if self.openai_planner:
                raise ProviderConfigurationError('GPT evaluation cannot authorize NVIDIA dispatch')
            return super().reserve(body)  # Full verified planner context reservation.
        if body.get('model') != OPENAI_MINI_SNAPSHOT:
            raise ProviderConfigurationError('Unapproved mixed evaluation model')
        with self._lock:
            identity = uuid4().hex
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise ProviderConfigurationError('In-flight mixed evaluation; no automatic retry') from None
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'owner_pid': os.getpid(), 'attempt_id': identity}, stream)
                stream.flush(); os.fsync(stream.fileno())
            try:
                self.state = json.loads(self.path.read_text(encoding='utf-8'))
                rate = self.state['rates'][OPENAI_MINI_SNAPSHOT]
                maximum = body.get('max_completion_tokens')
                stage = body.get('response_format', {}).get('json_schema', {}).get('name')
                is_planner = stage in {'twinpulse_site_tool_plan_v2', 'twinpulse_compact_photo_layout'}
                if is_planner and not self.openai_planner:
                    raise ProviderConfigurationError('Mixed approval cannot authorize a GPT planner')
                if self.openai_planner and stage not in {'twinpulse_image_observation', 'twinpulse_site_tool_plan_v2', 'twinpulse_compact_photo_layout'}:
                    raise ProviderConfigurationError('Unknown GPT evaluation stage')
                bound = self.text_input_bound(body) if is_planner else self.image_input_bound(body)
                if type(maximum) is not int or not 1 <= maximum <= 10000 or bound + maximum > rate['context_tokens']:
                    raise ProviderConfigurationError('Observer output/context bound exceeded')
                reserve = (Decimal(rate['input_per_million']) * bound + Decimal(rate['output_per_million']) * maximum) / 1000000
                used = sum((Decimal(r['charged_or_reserved_usd']) for r in self.state['requests']), Decimal(0))
                count = len(self.state['requests'])
                if (count >= self.state['max_requests'] or used + reserve > Decimal(self.state['limit_usd'])
                        or self._run_request_ceiling is not None and count >= self._run_request_ceiling):
                    raise ProviderConfigurationError('Mixed evaluation call/cost ceiling reached')
                self.state['requests'].append({'attempt_id': identity, 'model_id': OPENAI_MINI_SNAPSHOT,
                    'started_at': utc_now(), 'status': 'outcome_unknown', 'max_tokens': maximum,
                    'stage_schema': stage,
                    'input_token_bound': bound, 'reserved_usd': str(reserve), 'charged_or_reserved_usd': str(reserve)})
                self._write()
                return identity
            except BaseException:
                self.lock_path.unlink(missing_ok=True)
                raise


def load_evaluation_scope(path, campaign_path, *, request_cap=3):
    """Read a trusted host scope, require existing registered provider bindings."""
    path, campaign_path = Path(path), Path(campaign_path)
    if campaign_path.with_suffix('.continued-to').exists():
        raise ProviderConfigurationError('Retired scope cannot start another evaluation')
    if path.stat().st_size > 65536:
        raise ProviderConfigurationError('Mixed evaluation scope too large')
    scope = json.loads(path.read_text(encoding='utf-8'))
    saved_stage = scope.get('schema_version') == 'configured-stage-evaluation-1.0'
    openai_planner = scope.get('schema_version') == 'gpt-evaluation-1.0'
    planner_model = OPENAI_MINI_SNAPSHOT if openai_planner else NANO
    if (scope.get('schema_version') not in {'mixed-evaluation-1.0', 'gpt-evaluation-1.0', 'configured-stage-evaluation-1.0'} or not scope.get('approval')
            or (not saved_stage and scope.get('max_requests') != 10)
            or (saved_stage and (type(scope.get('max_requests')) is not int or not 1 <= scope['max_requests'] <= 10))
            or scope.get('limit_usd') not in (('0.15','0.50') if openai_planner else ('0.15',))
            or scope.get('observer_model') != OPENAI_MINI_SNAPSHOT or scope.get('planner_model') != planner_model
            or scope.get('campaign_path') != str(campaign_path.resolve())
            or type(request_cap) is not int or not 1 <= request_cap <= 5):
        raise ProviderConfigurationError('Explicit matching mixed evaluation scope required')
    lineage=scope.get('continued_from')
    if lineage:
        parent=Path(lineage['campaign_path'])
        saved=json.loads(parent.read_text(encoding='utf-8'))
        current=json.loads(campaign_path.read_text(encoding='utf-8'))
        receipt=json.loads(parent.with_suffix('.continued-to').read_text(encoding='utf-8'))
        if (hashlib.sha256(parent.read_bytes()).hexdigest()!=lineage['campaign_sha256']
                or receipt.get('scope_path')!=str(path.resolve())
                or saved['requests']!=current['requests'][:lineage['carried_requests']]
                or not saved['max_requests']==scope['max_requests']==lineage['unchanged_max_requests']):
            raise ProviderConfigurationError('Continuation identity/count changed; no dispatch')
    rates=scope.get('rates',{})
    if set(rates)!=({OPENAI_MINI_SNAPSHOT} if openai_planner else {OPENAI_MINI_SNAPSHOT,NANO}):
        raise ProviderConfigurationError('Exact two-model pricing scope required')
    observer_rate=rates[OPENAI_MINI_SNAPSHOT];planner_rate=rates.get(NANO,{})
    if (observer_rate.get('input_per_million')!='0.75' or observer_rate.get('output_per_million')!='4.50'
            or observer_rate.get('context_tokens')!=400000
            or observer_rate.get('source')!='https://developers.openai.com/api/docs/models/gpt-5.4-mini'
            or (not openai_planner and (planner_rate.get('source')!='https://api.tokenfactory.nebius.com/private/v1/models_info'
            or type(planner_rate.get('context_tokens')) is not int or not 10000<planner_rate['context_tokens']<=1048576))):
        raise ProviderConfigurationError('Reviewed stage pricing/context metadata required')
    for field,maximum in (() if openai_planner else (('input_per_million','.06'),('output_per_million','.24'))):
        value=Decimal(planner_rate.get(field,'NaN'))
        if not value.is_finite() or not 0<=value<=Decimal(maximum):
            raise ProviderConfigurationError('Planner pricing outside reviewed cap')
    store = JsonProviderSettingsStore()
    registry = KeyRegistry(store, WindowsCredentialStore())
    observer = registry.settings_for_entry(scope['observer_entry_id'])
    planner = registry.settings_for_entry(scope['planner_entry_id'])
    if observer.to_dict() != scope['observer_settings'] or planner.to_dict() != scope['planner_settings']:
        raise ProviderConfigurationError('Registered stage settings changed; no dispatch')
    if saved_stage:
        from .stage_routing import StageRoutingSettings, DEFAULT_OUTPUT_TOKENS, DEFAULT_GENERATION_TIMEOUT_S
        routes=StageRoutingSettings(registry)
        selected=routes.load()
        if (selected != scope.get('saved_stage_route') or selected is None
                or selected['observer']['key_id'] != scope['observer_entry_id']
                or selected['planner']['key_id'] != scope['planner_entry_id']
                or selected['observer']['model_id'] != 'gpt-5.4-mini'
                or selected['planner']['model_id'] != NANO
                or {k:selected[k].get('max_output_tokens',DEFAULT_OUTPUT_TOKENS[k]) for k in ('observer','planner')}
                    != scope.get('stage_output_tokens')
                or type(scope.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)) is not int
                or selected.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)
                    != scope.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)):
            raise ProviderConfigurationError('Approved saved stage route/output limits/timeout changed; no dispatch')
    if openai_planner and (observer != planner or scope['observer_entry_id'] != scope['planner_entry_id']):
        raise ProviderConfigurationError('GPT evaluation requires the selected OpenAI registration for both stages')
    observer_key, planner_key = registry.resolve(observer), registry.resolve(planner)
    if not observer_key.is_configured() or not planner_key.is_configured():
        raise ProviderConfigurationError('Both registered stage credentials required')
    ledger = SplitEvaluationLedger(campaign_path, approval=scope['approval'], rates=scope['rates'],
        limit_usd=scope['limit_usd'], max_requests=scope['max_requests'], run_request_cap=request_cap,
        openai_planner=openai_planner)
    return scope, observer, observer_key, planner, planner_key, ledger


def build_scoped_split_service(scope, observer, observer_key, planner, planner_key, ledger, evidence_root,
                               *, timeout_s=120., compact_photo_layout=False, planner_template_no_thinking=False,
                               output_token_cap=10000):
    if scope.get('schema_version') == 'configured-stage-evaluation-1.0':
        raise ProviderConfigurationError('Saved-stage evaluation requires its explicit saved-stage harness, not the legacy split builder')
    observer_transport = AuditedChatTransport(observer_key.load, InferenceEvidence(evidence_root), ledger)
    planner_transport = AuditedChatTransport(planner_key.load, InferenceEvidence(evidence_root), ledger)
    service = build_split_generation_service(observer, observer_transport, planner, planner_transport,
        timeout_s=timeout_s, compact_photo_layout=compact_photo_layout,
        planner_template_no_thinking=planner_template_no_thinking, output_token_cap=output_token_cap,
        openai_planner=scope.get('schema_version')=='gpt-evaluation-1.0')
    original = service._provider
    class ScopedProvider:
        def diagnostic_for(self, request_id):
            return original.diagnostic_for(request_id)
        async def generate(self, request, token, config):
            if (request.prompt != scope['prompt'] or len(request.images) != 1
                    or hashlib.sha256(request.images[0].content).hexdigest() != scope['photo_sha256']):
                raise ProviderConfigurationError('Input outside approved photo/prompt; no dispatch')
            response = await original.generate(request, token, config)
            from dataclasses import replace
            both_gpt = scope.get('schema_version')=='gpt-evaluation-1.0'
            return replace(response, provider_name='OpenAI observation + OpenAI planning' if both_gpt else 'OpenAI observation + Nebius NVIDIA planning',
                provenance={**response.provenance, 'stage_routing': {
                    'observer_origin': 'https://api.openai.com', 'planner_origin': 'https://api.openai.com' if both_gpt else 'https://api.tokenfactory.nebius.com',
                    'independent_credentials': not both_gpt, 'planner_receives_image': False}})
    return GenerationService(ScopedProvider(), service._config, plan_version='2.2')
