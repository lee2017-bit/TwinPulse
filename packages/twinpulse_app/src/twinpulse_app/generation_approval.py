# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Server-owned ordinary generation approvals. No network, key reads or replay.

The price snapshot is previously reviewed metadata, not an old spending grant.
Unsupported/expired pricing fails closed. Browser input selects only a USD cap;
the server supplies model/origin/input/policy/rate/checkpoint identities.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from threading import RLock

from twinpulse_core import canonical_sha256
from twinpulse_provider import GenerationRequest
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.generation_store import GenerationStore, input_digest
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT
from .command_broker import BrokerError
from .generation_scope import OrdinaryInferenceScope
from .stage_routing import StageRoutingSettings, DEFAULT_OUTPUT_TOKENS

# Verified in the earlier model metadata audit. No prior approval/ledger IDs are
# imported. Re-review prices before expiry; never silently extend this date.
REVIEWED_PRICES = {
    'gpt-6-luna': {'input_per_million':'0.10','output_per_million':'0.50',
        'context_tokens':1050000,'source':'https://developers.openai.com/api/docs/models/gpt-6-luna',
        'verified_at':'2026-10-10T05:31:00+00:00'},
    'Qwen/Qwen3.8-27B': {'input_per_million':'0.45','output_per_million':'3.0',
        'context_tokens':262144,'source':'https://api.tokenfactory.nebius.com/private/v1/models_info',
        'source_sha256':'c9c56152c844c5984f7340604248713b8582aa7dcfaebc39634ea5465507e604',
        'verified_at':'2026-10-10T05:31:00+00:00'},
    'deepseek-ai/DeepSeek-V4.1-Flash': {'input_per_million': '0.3', 'output_per_million': '1.2',
        'context_tokens': 1048000, 'source': 'https://api.tokenfactory.nebius.com/private/v1/models_info',
        'source_sha256': 'c9c56152c844c5984f7340604248713b8582aa7dcfaebc39634ea5465507e604',
        'verified_at': '2026-10-10T05:04:00+00:00'},
    'nvidia/Nemotron-3_5-Lightning': {'input_per_million': '0.06', 'output_per_million': '0.24',
        'context_tokens': 1048576, 'source': 'https://api.tokenfactory.nebius.com/private/v1/models_info',
        'source_sha256': 'c9c56152c844c5984f7340604248713b8582aa7dcfaebc39634ea5465507e604',
        'verified_at': '2026-10-10T05:04:00+00:00'},
    OPENAI_MINI_SNAPSHOT: {'input_per_million': '0.75', 'output_per_million': '4.50',
        'context_tokens': 400000, 'source': 'https://developers.openai.com/api/docs/models/gpt-5.4-mini',
        'verified_at': '2026-10-08T13:17:09.320184+00:00'},
    'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': {'input_per_million': '0.06', 'output_per_million': '0.24',
        'context_tokens': 262144, 'source': 'https://api.tokenfactory.nebius.com/private/v1/models_info',
        'source_sha256': '3497af852ae7cf688dd191bf98cb8753040f2d664883207dd5b1da36ea742c91',
        'verified_at': '2026-10-09T04:29:01.011348+00:00'},
}
PRICES_VALID_UNTIL = '2026-10-16T00:00:00+00:00'


def usd_limit(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]?)\.[0-9]{2}', value):
        raise BrokerError('generation_cost_invalid', 'Use a USD limit with two decimal places.', status=400)
    amount = Decimal(value)
    if not Decimal('0.01') <= amount <= Decimal('20.00'):
        raise BrokerError('generation_cost_invalid', 'The per-action USD limit must be between 0.01 and 20.00.', status=400)
    return amount


def full_context_reserve(rate, cap):
    """Shared ordinary-preview arithmetic; caller supplies reviewed rate/cap."""
    return (Decimal(rate['input_per_million'])*rate['context_tokens']
        + Decimal(rate['output_per_million'])*cap)/1000000


def minimum_initial_reserve(reserves):
    """Observer when selected, then room shell, inventory and first parameters."""
    return sum(reserves, Decimal(0)) + 2*reserves[-1]


def _read(path):
    if path.is_symlink() or path.stat().st_size > 2*1024*1024:
        raise ValueError('unsafe approval record')
    return json.loads(path.read_text(encoding='utf-8'))


class GenerationApprovals:
    def __init__(self, registry, workflow, *, clock=lambda: datetime.now(timezone.utc), prices=None):
        self.routes = StageRoutingSettings(registry)
        self.workflow = workflow
        self.root = registry.settings.path.parent/'ordinary-generation'
        self.store = GenerationStore(registry.settings.path.parent/'provider-evidence'/'generation-store')
        self.project_id = workflow._broker.project_id
        self.clock = clock
        self.prices = deepcopy(REVIEWED_PRICES if prices is None else prices)
        self.custom_prices=prices is not None
        self.lock = RLock()

    def enabled(self):
        route = self.routes.load()
        return bool(route and 'generation_policy' in route)

    def request(self,edit_context=None):
        if edit_context is not None:
            from twinpulse_provider.scene_edit_provider import scene_edit_generation_request
            return scene_edit_generation_request(edit_context,'approval-preview')
        prepared = self.workflow._application.generation_context().prepared
        return GenerationRequest('approval-preview', prepared.revision.prompt, prepared.images,
            image_detail=prepared.revision.generation_settings.get('image_detail', 'auto'),
            measurement_constraints=prepared.measurement_constraints)

    def prepare(self, *, checkpoint=None,edit_context=None):
        if edit_context is not None:
            fresh=self.workflow.scene_edit_context(edit_context['request_text'],edit_context['selected_call_id'],dependency=True)
            if fresh!=edit_context:raise BrokerError('scene_edit_proposal_stale','Current feedback context changed; nothing was sent.',status=409)
            if checkpoint is not None:raise BrokerError('scene_edit_scope_invalid','Feedback cannot resume a generation checkpoint.',status=409)
        route = self.routes.load()
        if not route or 'generation_policy' not in route:
            raise BrokerError('generation_policy_required', 'Save the staged generation policy before requesting this approval.', status=409)
        if self.clock() >= datetime.fromisoformat(PRICES_VALID_UNTIL):
            raise BrokerError('generation_pricing_expired', 'Reviewed pricing expired. Refresh trusted price metadata before approving; nothing was sent.', status=409)
        catalog=self.routes.model_catalog(route)
        valid_until=PRICES_VALID_UNTIL
        if catalog:
            from twinpulse_provider.model_contracts import checked_catalog,catalog_prices
            try:checked_catalog(catalog,now=self.clock())
            except ValueError:
                raise BrokerError('generation_pricing_expired', 'Frozen catalog pricing is expired or dated in the future. No request was sent.',status=409) from None
            valid_until=min(valid_until,catalog['valid_until'],key=datetime.fromisoformat)
        # Merge into this preview only: a changed/removed catalog cannot leave
        # a previous route's rates in the ordinary default snapshot.
        effective_prices={**self.prices,**(catalog_prices(catalog) if catalog and not self.custom_prices else {})}
        policy = GenerationPolicy.from_dict(route['generation_policy'])
        metadata = self.routes.metadata()
        if edit_context is not None and (metadata['base_url']!='https://api.tokenfactory.nebius.com/v1/' or
                metadata['model_id']!='nvidia/nemotron-3-super-120b-a12b' or
                route['planner'].get('max_output_tokens')!=40000 or policy.per_call_timeout_s!=300):
            raise BrokerError('scene_feedback_route_invalid','Feedback requires the approved Nebius Super 40k / 300s planner route; no fallback or request.',status=409)
        request = self.request(edit_context)
        # prepare_input adds the trusted catalog revision, not a user override.
        from twinpulse_core import SCENE_TOOL_CATALOG_REVISION
        expected_settings = {**metadata, 'tool_catalog_revision': SCENE_TOOL_CATALOG_REVISION}
        if edit_context is None and dict(self.workflow.current_input.prepared.revision.generation_settings) != expected_settings:
            raise BrokerError('generation_approval_stale', 'The current input uses different model settings. Review the input again before approval.', status=409)
        selected = ('observer', 'planner') if request.images else ('planner',)
        models, rates, reserves = [], {}, []
        for stage in selected:
            prefix = 'observer_' if stage == 'observer' else ''
            model = metadata[prefix+'model_id']
            rate = effective_prices.get(model)
            if not rate:
                raise BrokerError('generation_pricing_unavailable', 'Reviewed pricing is unavailable for the selected '+stage+' model. No fallback or request was made.', status=409)
            cap = route[stage].get('max_output_tokens', DEFAULT_OUTPUT_TOKENS[stage])
            reserve = full_context_reserve(rate, cap)
            rates[model] = deepcopy(rate)
            reserves.append(reserve)
            models.append({'stage': stage, 'model_id': model, 'origin': metadata[prefix+'base_url'],
                'max_output_tokens': cap, 'thinking_mode': route[stage].get('thinking_mode', 'default'),
                'full_context_reserve_usd': str(reserve), 'price_source': rate['source'],
                'price_verified_at': rate['verified_at']})
        parent = self._checkpoint(checkpoint) if checkpoint else None
        if checkpoint and not parent:
            raise BrokerError('generation_checkpoint_missing', 'This checkpoint is unavailable; nothing was resumed.', status=409)
        if parent:
            self._check_parent(parent, input_digest(request))
        descriptor = {'schema_version': 'ordinary-generation-preview-1.0', 'project_id': self.project_id,
            'input_sha256': input_digest(request), 'input_revision': self.workflow.current_input.revision,
            'route_sha256': canonical_sha256(route), 'settings_sha256': canonical_sha256(metadata),
            'policy': policy.to_dict(), 'policy_sha256': policy.sha256, 'models': models,
            'rates_sha256': canonical_sha256(rates), 'pricing_valid_until': valid_until,
            'image_count': len(request.images), 'purpose': ('Create an approximate scene; automatically Build idle '
                'Isaac previews and send the source photo plus derived renders to the selected observer provider for comparison; '
                'repair and re-render within this same budget. No Run or robot movement.'
                if request.images and policy.external_final_review else 'Create and validate an approximate editable 3D scene'),
            'render_review_approved': bool(request.images and policy.external_final_review),
            'checkpoint_id': checkpoint, 'checkpoint_sha256': canonical_sha256(parent) if parent else None,
            'prior_requests': parent['budget'].get('cumulative_requests', parent['budget']['requests']) if parent else 0,
            'prior_active_s': parent['budget'].get('cumulative_active_s', parent['budget']['elapsed_s']) if parent else 0,
            'prior_cost': deepcopy(parent['budget'].get('cumulative_cost', parent['budget'].get('cost'))) if parent else None,
            'default_limit_usd': '1.00', 'worst_single_reserve_usd': str(max(reserves)),
            'minimum_initial_reserve_usd': str(minimum_initial_reserve(reserves)),
            'automatic_retry': False, 'physical_authority': False}
        descriptor['preview_sha256'] = canonical_sha256(descriptor)
        if edit_context is not None:
            descriptor.update(scene_edit_context_sha256=edit_context['context_sha256'],planned_requests=1,
                purpose='Interpret this feedback using the current saved scene, support relations and retained unresolved inventory. '
                    'Exactly one planner-only proposal request; no source photo, automatic repair, Build, Run or robot command. '
                    'Apply/Cancel is a separate local review decision.',minimum_initial_reserve_usd=str(reserves[0]))
            descriptor['preview_sha256']=canonical_sha256({k:v for k,v in descriptor.items() if k!='preview_sha256'})
        return descriptor

    def _approval_path(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'ordinary-generation:[a-f0-9-]{32,36}', identity):
            raise BrokerError('generation_checkpoint_owner_invalid', 'Checkpoint approval owner is invalid.', status=409)
        return self.root/(identity.split(':')[1]+'.json')

    def _checkpoint(self, key):
        try:
            return self.store.read('checkpoint', key)
        except ProviderConfigurationError:
            raise BrokerError('generation_checkpoint_invalid', 'The saved checkpoint failed its identity or integrity check. No request was sent.', status=409) from None

    def _check_parent(self, parent, digest):
        try:
            manifest = _read(self._approval_path(parent.get('approval_id')))
            if (manifest['project_id'] != self.project_id or manifest['input_sha256'] != digest
                    or parent['input_sha256'] != digest or manifest['approval_id'] != parent['approval_id']):
                raise ValueError('owner')
            ledger_path = self.root/(parent['approval_id'].split(':')[1]+'.ledger.json')
            if ledger_path.with_suffix('.dispatch-lock').exists():
                raise BrokerError('generation_remote_unknown', 'The previous request is still owned or has an unknown result. Wait for recorded settlement; no automatic retry.', status=409)
            ledger = _read(ledger_path)
            if (ledger['approval'] != manifest['approval_id'] or ledger['rates'] != manifest['rates']
                    or ledger['max_requests'] != manifest['max_requests'] or ledger['limit_usd'] != manifest['limit_usd']):
                raise ValueError('ledger scope')
            old_rows = parent['budget']['attempts']
            rows = ledger['requests']
            if (len(rows) != len(old_rows) or len({r['attempt_id'] for r in rows}) != len(rows)
                    or {r['attempt_id'] for r in rows} != {r['attempt_id'] for r in old_rows}):
                raise ValueError('attempts')
            if any(not r.get('finished_at') or r.get('status') == 'outcome_unknown' for r in rows):
                raise BrokerError('generation_remote_unknown', 'Remote completion remains unknown. Reservations and the original failure were preserved; do not retry yet.', status=409)
            for row in rows:
                if not re.fullmatch('[a-f0-9]{32}', row['attempt_id']):
                    raise ValueError('attempt identity')
                raw = _read(self.store.root.parent/(row['attempt_id']+'.json'))
                if (raw.get('attempt_id') != row['attempt_id'] or raw.get('model_id') != row['model_id']
                        or raw.get('status') != row['status'] or raw.get('usage') != row.get('usage')):
                    raise ValueError('settlement evidence')
        except BrokerError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            raise BrokerError('generation_checkpoint_owner_invalid', 'Checkpoint and its project approval/ledger could not be matched. Nothing was resumed.', status=409) from None
        return rows

    def checkpoint_for_approval(self, identity):
        """Resolve only the current job's grant, never scan other projects."""
        try:
            manifest = _read(self._approval_path(identity))
            if manifest['project_id'] != self.project_id or manifest['input_sha256'] != input_digest(self.request()):
                raise ValueError('owner')
            ledger_path = self.root/(identity.split(':')[1]+'.ledger.json')
            if ledger_path.with_suffix('.dispatch-lock').exists():
                raise BrokerError('generation_remote_unknown', 'The earlier request is still owned or unresolved. No new request was sent.', status=409)
            if ledger_path.exists():
                ledger = _read(ledger_path)
                if (ledger['approval'] != identity or ledger['rates'] != manifest['rates']
                        or ledger['limit_usd'] != manifest['limit_usd']
                        or ledger['max_requests'] != manifest['max_requests']):
                    raise ValueError('ledger owner')
                if any(not r.get('finished_at') or r.get('status') == 'outcome_unknown' for r in ledger['requests']):
                    raise BrokerError('generation_remote_unknown', 'The earlier remote result remains unknown; reservations are preserved.', status=409)
            claim = ledger_path.with_suffix('.ordinary-scope.json')
            if not claim.exists():
                return None  # no backend grant bind, not a hidden HTTP retry
            bound = _read(claim)
            if bound['approval_id'] != identity or bound['input_sha256'] != manifest['input_sha256']:
                raise ValueError('claim')
            key = canonical_sha256({'request_id': bound['request_id'], 'input': bound['input_sha256']})
            return key if self._checkpoint(key) else None
        except BrokerError:
            raise
        except (OSError, KeyError, ValueError, TypeError):
            raise BrokerError('generation_checkpoint_owner_invalid', 'The current job approval could not be resolved safely.', status=409) from None

    def reconcile(self, checkpoint):
        """Explicit local read/reconciliation, never dispatch or rewrite old FAIL."""
        parent = self._checkpoint(checkpoint)
        if not parent:
            raise BrokerError('generation_checkpoint_missing', 'Checkpoint unavailable.', status=409)
        rows = self._check_parent(parent, input_digest(self.request()))
        budget = parent['budget']
        if not budget.get('in_flight') and all(r.get('settled') and r.get('status') != 'outcome_unknown' for r in budget['attempts']):
            return checkpoint
        # Only recorded final outcomes release this dependency, not an exited
        # PID, elapsed time, missing lock alone or a claimed cheap invoice.
        value = deepcopy(parent)
        by_id = {r['attempt_id']: r for r in rows}
        for attempt in value['budget']['attempts']:
            row = by_id[attempt['attempt_id']]
            if row['status'] not in ('received', 'rejected'):
                raise BrokerError('generation_remote_unknown', 'Settlement is not final; nothing was resumed.', status=409)
            attempt.update(settled=True, status=row['status'])
            if row.get('usage'):
                attempt['usage'] = deepcopy(row['usage'])
        value['budget']['in_flight'] = None
        old_cost = value['budget'].get('cost')
        if old_cost:
            held = sum((Decimal(r['charged_or_reserved_usd']) for r in rows if not r.get('usage')), Decimal(0))
            estimated = sum((Decimal(r['charged_or_reserved_usd']) for r in rows if r.get('usage')), Decimal(0))
            old_cost.update(estimated_usage_usd=str(estimated), reserved_unknown_usd=str(held))
            previous_costs = [r.get('cost') for r in value['budget'].get('prior_executions', [])]
            value['budget']['cumulative_cost'] = {'currency': 'USD',
                'estimated_usage_usd': str(estimated + sum((Decimal(r['estimated_usage_usd']) for r in previous_costs if r), Decimal(0))),
                'reserved_unknown_usd': str(held + sum((Decimal(r['reserved_unknown_usd']) for r in previous_costs if r), Decimal(0))),
                'history_complete': all(r is not None for r in previous_costs), 'invoice_verified': False}
        value['settlement_parent_checkpoint'] = checkpoint
        value['settlement_evidence_sha256'] = canonical_sha256(rows)
        key = canonical_sha256({'parent': checkpoint, 'settlement': value['settlement_evidence_sha256']})
        self.store.save('checkpoint', key, value)
        return key

    def approve(self, descriptor, card_id, limit, *, edit_context=None):
        with self.lock:
            if not isinstance(card_id, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', card_id):
                raise BrokerError('generation_approval_invalid', 'Approval question identity invalid.', status=400)
            fresh = self.prepare(checkpoint=descriptor.get('checkpoint_id'),edit_context=edit_context)
            if fresh != descriptor:
                raise BrokerError('generation_approval_stale', 'Input, model settings, pricing or checkpoint changed. Review a fresh approval; nothing was sent.', status=409)
            amount = usd_limit(limit)
            if amount < Decimal(descriptor['minimum_initial_reserve_usd']):
                raise BrokerError('generation_cost_insufficient', 'The USD limit is below the conservative initial-request reservation. Increase it explicitly; no request was sent.', status=409)
            identity = 'ordinary-generation:'+card_id
            catalog=self.routes.model_catalog(self.routes.load())
            from twinpulse_provider.model_contracts import catalog_prices
            effective_prices={**self.prices,**(catalog_prices(catalog) if catalog and not self.custom_prices else {})}
            manifest = {**deepcopy(descriptor), 'approval_id': identity, 'approved_at': self.clock().isoformat(),
                'limit_usd': limit, 'max_requests': descriptor['policy']['max_requests'],
                'rates': {m['model_id']: deepcopy(effective_prices[m['model_id']]) for m in descriptor['models']}}
            path = self._approval_path(identity)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open('x', encoding='utf-8') as stream:
                    json.dump(manifest, stream, allow_nan=False)
                    stream.flush(); os.fsync(stream.fileno())
            except FileExistsError:
                raise BrokerError('generation_approval_consumed', 'This approval was already recorded. Query the existing job; do not send it again.', status=409) from None
            return OrdinaryInferenceScope(identity, descriptor['input_sha256'], descriptor['route_sha256'],
                descriptor['policy_sha256'], self.root/(card_id+'.ledger.json'), manifest['rates'],
                limit, manifest['max_requests'], descriptor['checkpoint_sha256'], descriptor['render_review_approved'],
                approved_request_limit=1 if edit_context is not None else None)
