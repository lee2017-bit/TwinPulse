# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""User-initiated product requests and usage recording, without monetary gates."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json
import os

from twinpulse_core import canonical_sha256
from twinpulse_provider.errors import ProviderConfigurationError
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.reliability import utc_now
from .generation_approval import GenerationApprovals
from .command_broker import BrokerError


class ProductUsageLedger:
    product_usage = True

    def __init__(self, path, identity):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix('.dispatch-lock')
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = dict(schema_version='product-usage-1.0', approval=identity,
                          created_at=utc_now(), requests=[])
        self.agent_test_ledger=None
        test_scope=os.environ.get('TWINPULSE_AGENT_TEST_SCOPE')
        if test_scope:
            # Host-only test accounting, never read from browser/project/settings.
            from twinpulse_provider.reliability import CampaignLedger
            scope_path=Path(test_scope)
            scope=json.loads(scope_path.read_text(encoding='utf-8'))
            if scope.get('schema_version')!='product-live-test-1.0':raise ProviderConfigurationError('INVALID_AGENT_TEST_SCOPE')
            self.agent_test_ledger=CampaignLedger(scope_path.with_name('agent-test.ledger.json'),
                approval=scope.get('approval_id','product-live-20261013-user-usd2'),rates=scope['prices'],
                limit_usd=scope['limit_usd'],max_requests=scope['max_requests'])
        with self.path.open('x', encoding='utf-8') as stream:
            json.dump(self.state, stream)

    def _write(self):
        temporary = self.path.with_name('.'+self.path.name+'.'+uuid4().hex+'.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(self.state, stream, allow_nan=False)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def reserve(self, body):
        with self._lock:
            identity = uuid4().hex
            try:
                if self.agent_test_ledger:
                    identity=self.agent_test_ledger.reserve(body)
                descriptor = os.open(self.lock_path, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            except FileExistsError as error:
                raise ProviderConfigurationError('PRODUCT_REQUEST_ALREADY_IN_FLIGHT') from error
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    json.dump(dict(owner_pid=os.getpid(), attempt_id=identity), stream)
                self.state['requests'].append(dict(attempt_id=identity, model_id=body['model'],
                    max_tokens=body.get('max_tokens'), started_at=utc_now(), status='outcome_unknown'))
                self._write()
                return identity
            except BaseException:
                self.lock_path.unlink(missing_ok=True)
                raise

    def settle(self, identity, *, usage=None, status='outcome_unknown'):
        with self._lock:
            row = next(r for r in self.state['requests'] if r['attempt_id']==identity)
            if row.get('finished_at'):return
            row.update(finished_at=utc_now(), status=status)
            if usage:row['usage']=deepcopy(usage)
            if self.agent_test_ledger:self.agent_test_ledger.settle(identity,usage=usage,status=status)
            self._write()
            self.lock_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class ProductInferenceScope:
    approval_id: str
    approved_input_sha256: str
    approved_route_sha256: str
    approved_policy_sha256: str
    ledger_path: Path
    project_id: str
    approved_checkpoint_sha256: str | None = None
    approved_render_review: bool = True
    product_usage: bool = True

    @property
    def cache_identity(self):
        # New chat/Create is a fresh model action, even for identical bytes.
        # Explicit continuation restores its observation from the checkpoint
        # before this cache path, so it does not re-observe completed work.
        return canonical_sha256(dict(purpose='ordinary-scene-generation',
            input_sha256=self.approved_input_sha256,action_id=self.approval_id))

    def bind(self, request, policy, route_sha256):
        if (input_digest(request)!=self.approved_input_sha256 or route_sha256!=self.approved_route_sha256
                or policy.sha256!=self.approved_policy_sha256):
            raise ProviderConfigurationError('PRODUCT_REQUEST_CONTEXT_CHANGED')
        claim=self.ledger_path.with_suffix('.ordinary-scope.json')
        claim.parent.mkdir(parents=True,exist_ok=True)
        try:
            with claim.open('x',encoding='utf-8') as stream:
                json.dump(dict(approval_id=self.approval_id,request_id=request.request_id,
                    project_id=self.project_id,
                    input_sha256=self.approved_input_sha256,route_sha256=route_sha256,
                    policy_sha256=policy.sha256),stream)
        except FileExistsError as error:
            raise ProviderConfigurationError('PRODUCT_REQUEST_ALREADY_DISPATCHED') from error
        return ProductUsageLedger(self.ledger_path,self.approval_id)


class ProductGenerationActions(GenerationApprovals):
    product_mode = True

    def scope(self, *, checkpoint=None, edit_context=None):
        route=self.routes.load()
        if not route or 'generation_policy' not in route:
            raise BrokerError('generation_policy_required','Configure the generation models first.',status=409)
        parent=self._checkpoint(checkpoint) if checkpoint else None
        request=self.request(edit_context)
        if parent and parent.get('input_sha256')!=input_digest(request):
            raise BrokerError('generation_checkpoint_owner_invalid','This draft belongs to another input.',status=409)
        if parent:
            path=self._approval_path(parent['approval_id'])
            claim=path.with_suffix('.ledger.ordinary-scope.json')
            owner=json.loads((claim if claim.exists() else path).read_text(encoding='utf-8'))
            if owner.get('project_id')!=self.project_id or owner.get('approval_id')!=parent['approval_id']:
                raise BrokerError('generation_checkpoint_owner_invalid','This draft belongs to another conversation.',status=409)
        from twinpulse_provider.generation_policy import GenerationPolicy
        identity=uuid4().hex
        return ProductInferenceScope('ordinary-generation:'+identity,input_digest(request),canonical_sha256(route),
            GenerationPolicy.from_dict(route['generation_policy']).sha256,self.root/(identity+'.ledger.json'),self.project_id,
            canonical_sha256(parent) if parent else None)

    def checkpoint_for_approval(self, identity):
        claim=self._approval_path(identity).with_suffix('.ledger.ordinary-scope.json')
        if not claim.exists():return None
        value=json.loads(claim.read_text(encoding='utf-8'))
        if value.get('approval_id')!=identity or value.get('project_id')!=self.project_id or value['input_sha256']!=input_digest(self.request()):return None
        key=canonical_sha256(dict(request_id=value['request_id'],input=value['input_sha256']))
        return key if self._checkpoint(key) else None

    def reconcile(self, checkpoint):
        # Usage uncertainty is reported, not converted to a monetary permission.
        # The provider separately rejects resuming a still-running HTTP request.
        self._checkpoint(checkpoint)
        return checkpoint
