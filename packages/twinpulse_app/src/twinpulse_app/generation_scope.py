# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Trusted ordinary-generation approval adapter, separate from host campaigns.

Constructed by an explicit authorized action, never by a model or settings GET.
No historical campaign is discovered, borrowed or extended by this adapter.
"""
from dataclasses import dataclass
from pathlib import Path
from copy import deepcopy
import json
import os

from twinpulse_core import canonical_sha256
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.reliability import CampaignLedger


@dataclass(frozen=True)
class OrdinaryInferenceScope:
    approval_id: str
    approved_input_sha256: str
    approved_route_sha256: str
    approved_policy_sha256: str
    ledger_path: Path
    rates: dict
    limit_usd: str
    max_requests: int
    approved_checkpoint_sha256: str | None = None
    approved_render_review: bool = False
    approved_request_limit: int | None = None

    def __post_init__(self):
        # Snapshot caller-owned nested data; later settings mutations cannot
        # silently alter this already approved scope.
        object.__setattr__(self, 'rates', deepcopy(self.rates))

    @property
    def cache_identity(self):
        # Current bind still validates the new approval/input/route. Reusing an
        # already local observation performs no image transmission, so planner
        # changes/new approval IDs alone need not pay for the same photo again.
        return canonical_sha256({'purpose': 'ordinary-scene-generation',
            'input_sha256': self.approved_input_sha256})

    def bind(self, request, policy, route_sha256):
        if (not self.approval_id or not self.approval_id.startswith('ordinary-generation:')
                or input_digest(request) != self.approved_input_sha256
                or policy.sha256 != self.approved_policy_sha256
                or (request.images and policy.external_final_review and not self.approved_render_review)
                or route_sha256 != self.approved_route_sha256
                or type(self.max_requests) is not int or self.max_requests != policy.max_requests
                or self.approved_request_limit is not None and (type(self.approved_request_limit) is not int or
                    not 1<=self.approved_request_limit<=self.max_requests)):
            raise ProviderConfigurationError('ORDINARY_GENERATION_APPROVAL_MISMATCH')
        # Full-context reservation/rate provenance/unknown accounting are the
        # existing verified algorithm, not an average-cost approximation.
        claim = Path(self.ledger_path).with_suffix('.ordinary-scope.json')
        claim.parent.mkdir(parents=True, exist_ok=True)
        manifest = {'schema_version': 'ordinary-generation-scope-1.0',
            'approval_id': self.approval_id, 'request_id': request.request_id,
            'input_sha256': self.approved_input_sha256, 'route_sha256': route_sha256,
            'policy_sha256': policy.sha256, 'checkpoint_sha256': self.approved_checkpoint_sha256,
            'rates_sha256': canonical_sha256(self.rates), 'limit_usd': self.limit_usd,
            'max_requests': self.max_requests}
        manifest['render_review_approved'] = self.approved_render_review
        if self.approved_request_limit is not None:manifest['dispatch_request_limit']=self.approved_request_limit
        try:
            with claim.open('x', encoding='utf-8') as stream:
                json.dump(manifest, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            # One approval/action cannot restart the shared repair/time counters.
            # Read-only reopen never consumes or renews this claim.
            raise ProviderConfigurationError('ORDINARY_GENERATION_APPROVAL_ALREADY_BOUND') from error
        return CampaignLedger(self.ledger_path, approval=self.approval_id,
            rates=self.rates, limit_usd=self.limit_usd, max_requests=self.approved_request_limit or self.max_requests)
