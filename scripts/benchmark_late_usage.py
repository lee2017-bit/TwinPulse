# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Opt-in benchmark deadline/collection separation. Not a production retry policy.

One HTTP request, one durable reservation, immutable scored trial. A score
deadline cancels application of the result, not the receiver. Only validated
usage settles its estimate; closed/lost responses retain the full hold forever.
The owner never grants more money or moves the external approval deadline.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from threading import BoundedSemaphore, RLock
from uuid import uuid4

from twinpulse_provider.errors import ProviderConfigurationError, ProviderTimeoutError
from twinpulse_provider.reliability import CampaignLedger, utc_now


def exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush(); os.fsync(stream.fileno())


class CollectingLedger(CampaignLedger):
    """One live owner, short file transactions, independently held attempts.

    Other processes cannot adopt this ledger. Locks are never deleted on crash
    or reopened automatically. Concurrent work is reception, not model retries.
    """
    def __init__(self, path, **kwargs):
        path = Path(path)
        if path.exists():
            raise ProviderConfigurationError('COLLECTION_NEW_LEDGER_REQUIRED')
        self.owner_path = path.with_suffix('.collection-owner')
        self.owner = dict(owner_pid=os.getpid(), owner_id=uuid4().hex)
        exclusive_json(self.owner_path, self.owner)
        super().__init__(path, **kwargs)
        self.timeout_ids = set()
        self.collection_error = None

    @contextmanager
    def transaction(self):
        with self._lock:
            if json.loads(self.owner_path.read_text(encoding='utf-8')) != self.owner:
                raise ProviderConfigurationError('COLLECTION_OWNER_CHANGED')
            # A foreign transaction or legacy in-flight lock is not removed.
            exclusive_json(self.lock_path, self.owner)
            try:
                self.state = json.loads(self.path.read_text(encoding='utf-8'))
                yield
            finally:
                if json.loads(self.lock_path.read_text(encoding='utf-8')) == self.owner:
                    self.lock_path.unlink()

    def reserve(self, body):
        with self.transaction():
            if self.collection_error:
                raise ProviderConfigurationError(self.collection_error)
            model = body.get('model'); rate = self.state['rates'].get(model)
            maximum = body.get('max_tokens', body.get('max_completion_tokens'))
            if not rate or not rate.get('source') or type(maximum) is not int or not 0 < maximum <= rate['context_tokens']:
                raise ProviderConfigurationError('Verified model pricing and bounded output required')
            reserve = (Decimal(str(rate['input_per_million'])) * rate['context_tokens'] +
                       Decimal(str(rate['output_per_million'])) * maximum) / 1000000
            used = sum((Decimal(r['charged_or_reserved_usd']) for r in self.state['requests']), Decimal(0))
            if len(self.state['requests']) >= self.state['max_requests'] or used + reserve > Decimal(self.state['limit_usd']):
                raise ProviderConfigurationError('Approved inference campaign budget/request limit reached')
            identity = uuid4().hex
            self.state['requests'].append(dict(attempt_id=identity, model_id=model,
                started_at=utc_now(), status='outcome_unknown', max_tokens=maximum,
                reserved_usd=str(reserve), charged_or_reserved_usd=str(reserve)))
            self._write()
            return identity

    def settle(self, identity, *, usage=None, status='outcome_unknown'):
        with self.transaction():
            row = next(r for r in self.state['requests'] if r['attempt_id'] == identity)
            if row.get('finished_at'):
                return
            row.update(status=status, finished_at=utc_now())
            if usage and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
                rate = self.state['rates'][row['model_id']]
                actual = (Decimal(str(rate['input_per_million'])) * usage['prompt_tokens'] +
                          Decimal(str(rate['output_per_million'])) * usage['completion_tokens']) / 1000000
                row.update(usage=dict(usage), estimated_usd=str(actual), charged_or_reserved_usd=str(actual))
                if actual > Decimal(row['reserved_usd']):
                    self.collection_error = 'COLLECTION_USAGE_EXCEEDED_RESERVED_BOUND'
            self._write()

    def allows_timeout_continuation(self, row, attempts, errors):
        if row.get('failure_code') != 'PROVIDER_TIMEOUT' or not attempts:
            return False
        pending = [a for a in attempts if a['ledger_status'] == 'outcome_unknown' or not a['settlement_finished'] or not a.get('usage')]
        return (bool(pending) and all(a['attempt_id'] in self.timeout_ids for a in pending)
                and all(e['code'] == 'EVIDENCE_PENDING' and e['attempt_id'] in self.timeout_ids for e in errors)
                and self.collection_error is None)

    def blocking_dispatch_lock(self):
        # Our transaction may be writing in another receiver thread. Wait only
        # for that tiny local critical section, not its network response.
        with self._lock:
            return self.lock_path.exists()

    def close(self):
        with self._lock:
            if any(not r.get('finished_at') for r in self.state['requests']):
                raise ProviderConfigurationError('COLLECTION_RECEIVERS_STILL_ACTIVE')
            if json.loads(self.owner_path.read_text(encoding='utf-8')) != self.owner:
                raise ProviderConfigurationError('COLLECTION_OWNER_CHANGED')
            self.owner_path.unlink()


class LateUsageCollector:
    """300s scored HTTP deadline, up to 900s for that SAME response reception.

    Four bounded receivers; no unbounded paid queue and no second inference.
    A full pool is a host-capacity stop, never counted as model-quality failure.
    """
    def __init__(self, root, *, expires_at, receive_timeout_s=900, workers=4):
        if not 0 < receive_timeout_s <= 900 or not 1 <= workers <= 4:
            raise ValueError('COLLECTION_BOUND_INVALID')
        self.root = Path(root)
        self.expiry = datetime.fromisoformat(expires_at)
        if self.expiry.tzinfo is None:
            raise ValueError('COLLECTION_DEADLINE_INVALID')
        self.receive_timeout_s = receive_timeout_s
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='benchmark-receive')
        self.slots = BoundedSemaphore(workers)
        self.lock = RLock(); self.pending = set(); self.fatal = None
        self.receptions = {}

    def _record_timeout(self, context, identity, *, scored_timeout_s, origin):
        ledger=context['ledger']
        with ledger._lock:
            if not any(r['attempt_id']==identity for r in ledger.state['requests']):
                raise ProviderConfigurationError('COLLECTION_TIMEOUT_LEDGER_JOIN_MISSING')
            path=self.root/'timeouts'/(identity+'.json')
            if not path.exists():
                exclusive_json(path,dict(attempt_id=identity,model_id=context['model'],at=utc_now(),
                    scored_timeout_s=scored_timeout_s,receiver_timeout_s=context['receive'],
                    deadline_origin=origin,result='FAIL_PROVIDER_TIMEOUT',
                    application_of_late_result=False,financial_reservation_retained=True,automatic_retry=False))
            elif json.loads(path.read_text(encoding='utf-8'))['attempt_id']!=identity:
                raise ProviderConfigurationError('COLLECTION_TIMEOUT_RECEIPT_JOIN_CHANGED')
            ledger.timeout_ids.add(identity)

    def record_enclosing_deadline(self, calls, ledger, *, scored_timeout_s):
        """A confirmed BudgetedPipeline per-call timeout cancelled our await.

        Both deadlines can fire on the same loop tick. The enclosing pipeline
        translates its own cancellation into ProviderTimeoutError; only that
        typed per-call deadline may mark this SAME owned receiver as timed out.
        User cancellation, total-generation expiry and foreign calls do not.
        """
        with self.lock:
            contexts=[c for c in self.receptions.values() if c['calls'] is calls and c['ledger'] is ledger]
        marked=[]
        for context in contexts:
            if not 0<scored_timeout_s<=context['score']:
                raise ProviderConfigurationError('COLLECTION_ENCLOSING_DEADLINE_INVALID')
            if len(calls)<=context['initial_calls']:
                raise ProviderConfigurationError('COLLECTION_TIMEOUT_WITHOUT_DISPATCH_ID')
            identity=calls[context['initial_calls']]
            self._record_timeout(context,identity,scored_timeout_s=scored_timeout_s,
                                 origin='budgeted_pipeline_per_call')
            marked.append(identity)
        return marked

    def stop_reason(self):
        with self.lock:
            return self.fatal

    async def complete(self, worker, body, token, config, *, calls, evidence, ledger):
        if not isinstance(ledger, CollectingLedger):
            raise ProviderConfigurationError('COLLECTION_SCOPED_FINANCIAL_OWNER_REQUIRED')
        if self.stop_reason():
            raise ProviderConfigurationError(self.stop_reason())
        remaining = (self.expiry - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise ProviderConfigurationError('BENCHMARK_APPROVAL_EXPIRED_NO_DISPATCH')
        if not self.slots.acquire(blocking=False):
            with self.lock: self.fatal = 'COLLECTION_RECEIVER_CAPACITY_STOP'
            raise ProviderConfigurationError(self.fatal)
        initial_calls = len(calls)
        receive = min(self.receive_timeout_s, remaining)
        score = min(config.timeout_s, receive)
        key = worker._api_key_getter()
        if not key:
            self.slots.release()
            raise ProviderConfigurationError('Existing credential not configured')
        try:
            future = self.pool.submit(worker._post, body, token, replace(config, timeout_s=receive), key)
        except BaseException:
            self.slots.release(); raise
        context=dict(calls=calls,initial_calls=initial_calls,ledger=ledger,model=body['model'],
                     score=score,receive=receive)
        with self.lock:
            self.pending.add(future);self.receptions[future]=context

        def settled(done):
            try:
                # Worker writes raw before its financial settlement. Do not
                # expose its content/key; only keyed local audit metadata here.
                error = done.exception()
                if len(calls) > initial_calls:
                    identity = calls[initial_calls]
                    raw = json.loads((evidence.root / (identity + '.json')).read_text(encoding='utf-8'))
                    entry = next(r for r in ledger.state['requests'] if r['attempt_id'] == identity)
                    reason = ('OUTPUT_LIMIT' if raw.get('finish_reason') == 'length' else
                              'PROVIDER_PAYMENT_REQUIRED_STOP' if raw.get('http_status') == 402 else None)
                    if reason:
                        with self.lock: self.fatal = reason
                    exclusive_json(self.root / 'settlements' / (identity + '.json'), dict(
                        attempt_id=identity, model_id=body['model'], at=utc_now(),
                        trial_timed_out=identity in ledger.timeout_ids,
                        trial_result_rewritten=False, automatic_retry=False,
                        response_status=raw['status'], usage=entry.get('usage'),
                        charged_or_reserved_usd=entry['charged_or_reserved_usd'],
                        raw_path=str(evidence.root / (identity + '.json')),
                        response_sha256=raw.get('response_sha256'),
                        fatal_gate=reason, receiver_error_type=type(error).__name__ if error else None))
                    if ledger.collection_error:
                        with self.lock: self.fatal = ledger.collection_error
                elif error and not isinstance(error, ProviderConfigurationError):
                    with self.lock: self.fatal = 'COLLECTION_WORKER_FAILED_BEFORE_AUDIT'
            except BaseException:
                with self.lock: self.fatal = 'COLLECTION_EVIDENCE_OR_ACCOUNTING_FAILED'
            finally:
                self.slots.release()
                with self.lock:
                    self.pending.discard(done);self.receptions.pop(done,None)

        future.add_done_callback(settled)
        try:
            # Shield prevents scoring cancellation from cancelling the only
            # receiver. The same future remains owned until durable settlement.
            wrapped = asyncio.wrap_future(future)
            # A late cancelled-application result is consumed by its receiver,
            # not leaked as an unobserved asyncio exception after scored FAIL.
            wrapped.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout=score)
        except asyncio.TimeoutError:
            if len(calls) <= initial_calls:
                with self.lock: self.fatal = 'COLLECTION_TIMEOUT_WITHOUT_DISPATCH_ID'
                raise ProviderConfigurationError(self.fatal) from None
            identity = calls[initial_calls]
            self._record_timeout(context,identity,scored_timeout_s=score,origin='collector')
            token.cancel()
            failure = ProviderTimeoutError('scored HTTP deadline expired; same response receiver retained for accounting')
            failure.attempt_id = identity
            raise failure from None

    def snapshot(self):
        with self.lock:
            return dict(active_receivers=len(self.pending), fatal_gate=self.fatal,
                        additional_inference_calls=0, trial_deadline_s=300,
                        receive_timeout_s=self.receive_timeout_s)

    async def drain(self):
        # Called only after all eligible other jobs ended. Not between trials.
        while self.snapshot()['active_receivers']:
            await asyncio.sleep(.1)
        self.pool.shutdown(wait=False)
        return self.snapshot()
