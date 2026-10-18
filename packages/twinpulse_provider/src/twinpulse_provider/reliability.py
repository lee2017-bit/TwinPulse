# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded local inference evidence and durable, fail-closed campaign accounting.

No credentials, headers or input images are persisted. Unknown outcomes retain
their full reservation; restarting a campaign never resets its expenditure.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Mapping
from uuid import uuid4

from .errors import ProviderConfigurationError
from .output_diagnostics import output_diagnostics


# Local redacted structured requests/validations can legitimately exceed the
# old 256KiB character prefix as typed repair schemas and geometry feedback grow.
# Keep a finite BYTE budget, matching response evidence, without changing wire
# bodies, tokens, financial guards or treating truncated history as audited.
MAX_STRUCTURED_EVIDENCE_BYTES = 2 * 1024 * 1024


def bounded_redacted_record(encoded: str, *, secret=None):
    redacted = safe_text(encoded, secret=secret, limit=len(encoded))
    payload = redacted.encode('utf-8')
    captured = payload[:MAX_STRUCTURED_EVIDENCE_BYTES].decode('utf-8', errors='ignore')
    return captured, len(payload) > MAX_STRUCTURED_EVIDENCE_BYTES


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def check_benchmark_dispatch_deadline(*, now=None):
    """Optional evaluation restriction; an environment value NEVER grants access.

    Check again in the admitted worker immediately before HTTP. An already sent
    request may finish after expiry and keeps its accounting/evidence.
    """
    value=os.environ.get('TWINPULSE_BENCHMARK_EXPIRES_AT')
    if value is None:return
    try:
        expires=datetime.fromisoformat(value)
        if expires.tzinfo is None or expires.utcoffset().total_seconds()!=0:raise ValueError()
    except (ValueError,TypeError):
        raise ProviderConfigurationError('BENCHMARK_DISPATCH_DEADLINE_INVALID') from None
    if (now or datetime.now(timezone.utc))>=expires:
        raise ProviderConfigurationError('BENCHMARK_APPROVAL_EXPIRED_NO_DISPATCH')


def safe_text(value: str, *, secret: str | None = None, limit: int = 262144) -> str:
    if secret:
        value = value.replace(secret, '[REDACTED]')
    value = re.sub(r'data:[^\s"<>]*;base64,[A-Za-z0-9+/=]+', '[IMAGE_REMOVED]', value)
    value = re.sub(r'(?i)Bearer\s+[^\s"<>]+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(?i)("(?:api[_-]?key|authorization|access_token|secret)"\s*:\s*")[^"]*',
                   r'\1[REDACTED]', value)
    return value[:limit]


class InferenceEvidence:
    """Exclusive local attempt files. These paths are never exposed through the API."""
    def __init__(self, root: Path):
        self.root = Path(root)

    def started(self, attempt_id: str, facts: Mapping, *, request_body=None, secret=None):
        """Durable intent before HTTP, separate from immutable final raw files.

        Without a final record this means unknown, not proof that HTTP ran.
        Existing final-file glob consumers continue to see only final records.
        """
        if not re.fullmatch(r'[a-f0-9]{32}', attempt_id):
            raise ValueError('invalid inference attempt id')
        pending = self.root / 'dispatches'
        pending.mkdir(parents=True, exist_ok=True)
        item = {**facts, 'dispatch_state': 'admitted_not_proven_sent', 'saved_at': utc_now()}
        if request_body is not None:
            encoded = json.dumps(request_body, ensure_ascii=False)
            captured, truncated = bounded_redacted_record(encoded, secret=secret)
            item.update(request_redacted=captured, request_truncated=truncated,
                request_byte_count=len(encoded.encode('utf-8')), redaction_applied=True,
                captured_request_byte_count=len(captured.encode('utf-8')),
                input_images_saved=False, access_scope='local_only')
            item['stored_request_sha256'] = hashlib.sha256(item['request_redacted'].encode('utf-8')).hexdigest()
        with (pending / f'{attempt_id}.json').open('x', encoding='utf-8') as stream:
            json.dump(item, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())

    def validation(self, attempt_id, stage, record, *, secret=None):
        if not re.fullmatch(r'[a-f0-9]{32}', attempt_id) or not re.fullmatch(r'[a-z_]{1,32}', stage):
            raise ValueError('invalid validation identity')
        # No mutation of historical requests/responses. Each received attempt
        # has independent contract and (where applicable) compile evidence.
        pending = self.root / 'validations'
        pending.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(record, ensure_ascii=False)
        captured, truncated = bounded_redacted_record(encoded, secret=secret)
        item = dict(attempt_id=attempt_id, stage=stage, saved_at=utc_now(),
            access_scope='local_only', input_images_saved=False, redaction_applied=True,
            record_redacted=captured, record_truncated=truncated,
            captured_record_byte_count=len(captured.encode('utf-8')),
            record_sha256=hashlib.sha256(encoded.encode('utf-8')).hexdigest())
        item['stored_record_sha256'] = hashlib.sha256(item['record_redacted'].encode('utf-8')).hexdigest()
        intent = self.root / 'dispatches' / f'{attempt_id}.json'
        if intent.exists():
            facts = json.loads(intent.read_text(encoding='utf-8'))
            item.update({k: facts[k] for k in ('execution_id', 'span_id', 'model_id', 'request_sha256',
                'schema_sha256', 'role') if k in facts})
        with (pending / f'{attempt_id}-{stage}.json').open('x', encoding='utf-8') as stream:
            json.dump(item, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())

    def save(self, attempt_id: str, facts: Mapping, raw: bytes | None = None, *, secret=None):
        if not re.fullmatch(r'[a-f0-9]{32}', attempt_id):
            raise ValueError('invalid inference attempt id')
        self.root.mkdir(parents=True, exist_ok=True)
        item = dict(facts)
        if raw is not None:
            # Match the existing bounded transport size, so a 40k-token
            # reasoning response does not lose its final JSON during logging.
            from .nebius_pipeline import MAX_RESPONSE_BYTES
            captured = raw[:MAX_RESPONSE_BYTES]
            text = captured.decode('utf-8', errors='replace')
            item.update(response_sha256=hashlib.sha256(raw).hexdigest(),
                        response_byte_count=len(raw), captured_byte_count=len(captured),
                        response_truncated=len(raw) > MAX_RESPONSE_BYTES,
                        redaction_applied=True, input_images_saved=False, access_scope='local_only',
                        response_redacted=safe_text(text, secret=secret, limit=MAX_RESPONSE_BYTES))
            item['stored_response_sha256'] = hashlib.sha256(item['response_redacted'].encode('utf-8')).hexdigest()
        item['saved_at'] = utc_now()
        # Errors here stop the attempt rather than silently losing its evidence.
        with (self.root / f'{attempt_id}.json').open('x', encoding='utf-8') as stream:
            json.dump(item, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())


class AuditedChatTransport:
    """Audit in the blocking worker, so timeout cannot refund an in-flight call.

This is the existing Urllib transport, not a proxy or another provider. Raw
response files remain local-only. Production callers may omit a campaign.
"""
    def __init__(self, key_getter, evidence: InferenceEvidence, ledger=None, *, opener=None, collection=None):
        self.key_getter, self.evidence, self.ledger = key_getter, evidence, ledger
        self.calls = []
        self.opener = opener
        # Trusted benchmark host only. Production keeps its original transport
        # and fail-closed single-dispatch accounting unless explicitly supplied.
        self.collection = collection

    def record_validation(self, stage, attempt_id, record):
        # Credentials are only used for redaction, never written to evidence.
        self.evidence.validation(attempt_id, stage, record, secret=self.key_getter())

    async def complete(self, body, token, config):
        from .nebius_pipeline import UrllibChatCompletionsTransport
        from .errors import GenerationCancelledError
        import time
        if token.is_cancelled:
            raise GenerationCancelledError('generation cancelled before dispatch')
        budget = getattr(token, 'generation_budget', None)
        if budget is not None and budget.financial_owner is None:
            raise ProviderConfigurationError('Budgeted generation requires a separately bound financial approval scope')
        if not self.key_getter():
            raise ProviderConfigurationError('Existing credential is not configured')
        parent = self
        # Capture immutable context BEFORE executor admission. A timeout may
        # return while this worker still receives/settles the same HTTP attempt.
        stage_trace = token.diagnostics
        class Worker(UrllibChatCompletionsTransport):
            def _post(self, body, token, config, key):
                if token.is_cancelled:
                    raise GenerationCancelledError('generation cancelled before dispatch')
                check_benchmark_dispatch_deadline()
                # Reserve only after bounded worker admission, before HTTP.
                # A busy-worker rejection must not strand a campaign lock.
                if budget is not None and parent.ledger is not None:
                    raise ProviderConfigurationError('Two financial budget owners cannot share one dispatch')
                identity = (budget.reserve(body, role=getattr(token, 'generation_role', 'initial')) if budget
                            else parent.ledger.reserve(body) if parent.ledger else uuid4().hex)
                parent.calls.append(identity)
                started=time.monotonic(); raw=[]; usage=None
                maximum=body.get('max_tokens',body.get('max_completion_tokens'))
                facts=dict(attempt_id=identity,model_id=body['model'],max_tokens=maximum,
                    request_sha256=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
                    schema_sha256=hashlib.sha256(json.dumps(body['response_format'],sort_keys=True).encode()).hexdigest(),
                    started_at=utc_now(),status='outcome_unknown')
                facts['role'] = getattr(token, 'generation_role', 'initial')
                facts['schema_stage'] = body.get('response_format', {}).get('json_schema', {}).get('name')
                trace = stage_trace.child('http_attempt', attempt_id=identity,
                    model_id=body['model'], max_tokens=maximum) if stage_trace else None
                if trace:
                    facts.update(execution_id=trace.execution_id, span_id=trace.span_id)
                try:
                    parent.evidence.started(identity, facts, request_body=body, secret=key)
                except BaseException as error:
                    if trace: trace.finish('failed', error=error, error_code='dispatch_record_failed')
                    raise  # No HTTP and no automatic retry on mandatory audit failure.
                primary_error = None
                actual_opener=self._opener
                class Capture:
                    def __init__(self,response):self.response=response
                    def __enter__(self):self.response.__enter__();return self
                    def __exit__(self,*args):return self.response.__exit__(*args)
                    def geturl(self):return self.response.geturl()
                    def read(self,*args):
                        value=self.response.read(*args);raw.append(value);return value
                def open_capture(*args,**kwargs):
                    response = actual_opener(*args,**kwargs)
                    facts['http_status'] = getattr(response, 'status', 200)
                    return Capture(response)
                self._opener=open_capture
                try:
                    check_benchmark_dispatch_deadline()
                    result=super()._post(body,token,config,key)
                    usage=dict(result.usage)
                    facts.update(status='received',usage=usage,finish_reason=result.finish_reason,http_status=200)
                    if raw:
                        facts.update(output_diagnostics(json.loads(raw[0])))
                    from dataclasses import replace
                    return replace(result,attempt_id=identity)
                except BaseException as error:
                    primary_error = error
                    import urllib.error
                    cause=error.__cause__
                    if isinstance(cause,urllib.error.HTTPError):
                        facts['http_status']=cause.code
                        raw.append(cause.read(262145))
                    try:
                        payload=json.loads(raw[0]) if raw else {}
                        usage=payload.get('usage') if isinstance(payload,dict) else None
                        facts.update(output_diagnostics(payload))
                    except (ValueError,UnicodeError):pass
                    facts.update(status='rejected' if raw else 'outcome_unknown',
                                 error_type=type(error).__name__,cancelled=token.is_cancelled)
                    # A rejected/truncated response may still carry billable
                    # usage. Keep the same captured facts as the ledger; never
                    # drop them merely because the JSON/content was rejected.
                    if usage is not None:
                        facts['usage'] = usage
                    error.attempt_id=identity
                    error.output_diagnostics={k:v for k,v in facts.items() if k in {
                        'output_pattern','final_empty','visible_chars','visible_nonwhitespace_chars',
                        'visible_trailing_whitespace_chars','reasoning_chars','reasoning_nonwhitespace_chars',
                        'reasoning_tokens','finish_reason'}}
                    raise
                finally:
                    facts['elapsed_s']=round(time.monotonic()-started,3)
                    # Persist evidence before accounting is settled. Failure
                    # leaves its reservation/lock visible, never dispatches again.
                    try:
                        parent.evidence.save(identity,facts,b''.join(raw) if raw else None,secret=key)
                        if parent.ledger:parent.ledger.settle(identity,usage=usage,status=facts['status'])
                        if budget:budget.settle(identity,usage=usage,status=facts['status'])
                    except BaseException as storage_error:
                        if trace:
                            cleanup = trace.child('inference_evidence', role='storage')
                            cleanup.finish('failed', error=storage_error, role='storage')
                            trace.finish('failed', error=primary_error or storage_error)
                        if primary_error is not None:
                            primary_error.evidence_error_type = type(storage_error).__name__
                            raise primary_error
                        raise
                    if trace:
                        trace.bind(finish_reason=facts.get('finish_reason'), http_status=facts.get('http_status'),
                                   cancelled=token.is_cancelled,
                                   **{k:v for k,v in facts.items() if k in {
                                       'output_pattern','final_empty','visible_chars','visible_nonwhitespace_chars',
                                       'visible_trailing_whitespace_chars','reasoning_chars',
                                       'reasoning_nonwhitespace_chars','reasoning_tokens'}},
                                   **{k:v for k,v in (usage or {}).items() if k in {'prompt_tokens','completion_tokens','total_tokens'}})
                        trace.finish('succeeded' if facts['status']=='received' else
                                     'unknown' if facts['status']=='outcome_unknown' else 'failed', error=primary_error)
        worker = Worker(self.key_getter,opener=self.opener)
        if self.collection is not None:
            return await self.collection.complete(worker, body, token, config,
                calls=self.calls, evidence=self.evidence, ledger=budget.financial_owner if budget else self.ledger)
        return await worker.complete(body,token,config)


class CampaignLedger:
    """One-process ledger; O_EXCL dispatch lock prevents concurrent campaign writers.

Rates must be verified by the caller. Full model context is reserved, including
image/reasoning input, not guessed from the image byte size. Billing is an
estimate at these pinned rates, not an authoritative provider invoice.
"""
    def __init__(self, path: Path, *, approval: str, rates: Mapping[str, Mapping],
                 limit_usd='1.00', max_requests=60, run_request_cap=None):
        if run_request_cap is not None and (type(run_request_cap) is not int or not 1 <= run_request_cap <= 5):
            raise ProviderConfigurationError('Evaluation run request cap must be 1 to 5')
        self.path = Path(path)
        self.lock_path = self.path.with_suffix('.dispatch-lock')
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if (self.state['approval'] != approval or self.state['rates'] != dict(rates)
                    or self.state['limit_usd'] != str(limit_usd) or self.state['max_requests'] != max_requests):
                raise ProviderConfigurationError('Campaign identity, rates or approval changed')
        else:
            self.state = dict(schema_version='inference-campaign-1.0', approval=approval,
                              rates=dict(rates), limit_usd=str(limit_usd), max_requests=max_requests,
                              created_at=utc_now(), requests=[])
            with self.path.open('x', encoding='utf-8') as stream:
                json.dump(self.state, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
        self._run_request_ceiling = (len(self.state['requests']) + run_request_cap
                                    if run_request_cap is not None else None)

    @classmethod
    def open_existing_approved(cls, path: Path, *, run_request_cap=5):
        """Trusted host-only evaluation: validate saved approvals, never extend.

        Hashes check consistency, not human authorship. The caller must already
        hold explicit human authorization for this local ledger and photo.
        USD1 and the original60 base remain pinned; browser/model output cannot
        choose a cap. Prefix hashes include failed/unknown charged reservations.
        """
        from twinpulse_core.revisions import canonical_sha256
        path = Path(path)
        saved = json.loads(path.read_text(encoding='utf-8'))
        def reject():
            raise ProviderConfigurationError('Existing evaluation approval history is invalid')
        if (saved.get('schema_version') != 'inference-campaign-1.0'
                or saved.get('limit_usd') != '1.00' or not saved.get('approval')
                or not isinstance(saved.get('requests'), list) or not isinstance(saved.get('rates'), dict)):
            reject()
        cap, ids, previous_start = 60, set(), 0
        history = saved.get('additional_batch_approvals', [])
        if not isinstance(history, list):reject()
        for row in history:
            if not isinstance(row, dict):reject()
            start, extra = row.get('start_count'), row.get('new_batch_cap')
            carry = row.get('carry_forward_remaining',0)
            identity = row.get('batch_id')
            if (not isinstance(identity, str) or not identity or identity in ids
                    or not isinstance(row.get('approval'), str) or not row['approval']
                    or not row.get('approved_at') or type(start) is not int
                    or not previous_start <= start <= cap or start > len(saved['requests'])
                    or type(extra) is not int or not 1 <= extra <= 100
                    or type(carry) is not int or carry < 0
                    or ('carry_forward_remaining' in row and carry != cap - start)
                    or row.get('old_max_requests') != cap
                    or row.get('new_max_requests') != start + extra + carry or start + extra + carry <= cap
                    or row.get('unchanged_limit_usd') != saved['limit_usd']
                    or row.get('prior_requests_sha256') != canonical_sha256(saved['requests'][:start])):
                reject()
            cap, previous_start = start + extra + carry, start
            ids.add(identity)
        if type(saved.get('max_requests')) is not int or saved['max_requests'] != cap:
            reject()
        if (len(saved['requests']) > cap or path.with_suffix('.dispatch-lock').exists()
                or any(not r.get('finished_at') for r in saved['requests'])):
            raise ProviderConfigurationError('Evaluation campaign has pending or invalid dispatches')
        return cls(path, approval=saved['approval'], rates=saved['rates'],
                   limit_usd='1.00', max_requests=cap, run_request_cap=run_request_cap)

    def _write(self):
        temporary = self.path.with_suffix('.pending')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(self.state, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def register_verified_rate(self, model_id, rate):
        """Add a previously unpriced approved model without resetting expenditure.

        Existing prices and limits are immutable. This explicit host-side step
        must only be used after fetching the provider's pricing metadata.
        """
        if (not isinstance(rate,dict) or not str(rate.get('source','')).startswith('https://')
                or type(rate.get('context_tokens')) is not int or rate['context_tokens'] <= 0
                or any(Decimal(str(rate.get(k,'-1'))) < 0
                       for k in ('input_per_million','output_per_million'))):
            raise ProviderConfigurationError('Verified model pricing metadata is invalid')
        with self._lock:
            try:
                descriptor=os.open(self.lock_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(descriptor)
            except FileExistsError as error:
                raise ProviderConfigurationError('Cannot register pricing during an in-flight attempt') from error
            try:
                self.state=json.loads(self.path.read_text(encoding='utf-8'))
                existing=self.state['rates'].get(model_id)
                if existing is not None and existing != rate:
                    raise ProviderConfigurationError('Existing campaign pricing is immutable')
                self.state['rates'][model_id]=dict(rate)
                self._write()
            finally:self.lock_path.unlink(missing_ok=True)

    def reserve(self, body: Mapping) -> str:
        with self._lock:
            identity = uuid4().hex
            try:
                descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    json.dump(dict(owner_pid=os.getpid(), attempt_id=identity), stream)
                    stream.flush(); os.fsync(stream.fileno())
            except FileExistsError as error:
                raise ProviderConfigurationError('Campaign has an in-flight/unknown dispatch lock; inspect before resuming') from error
            try:
                # Reload inside the exclusive lock, including other process reservations.
                self.state = json.loads(self.path.read_text(encoding='utf-8'))
                rate = self.state['rates'].get(body.get('model'))
                if not rate or not rate.get('source'):
                    raise ProviderConfigurationError('Verified model pricing/context bound is required before dispatch')
                maximum = body.get('max_tokens')
                if type(maximum) is not int or not 0 < maximum <= rate['context_tokens']:
                    raise ProviderConfigurationError('Bounded max_tokens is required')
                reserve = (Decimal(str(rate['input_per_million'])) * rate['context_tokens']
                           + Decimal(str(rate['output_per_million'])) * maximum) / 1000000
                used = sum((Decimal(row['charged_or_reserved_usd']) for row in self.state['requests']), Decimal(0))
                if self._run_request_ceiling is not None and len(self.state['requests']) >= self._run_request_ceiling:
                    raise ProviderConfigurationError('Evaluation run request limit reached; no automatic new run')
                if len(self.state['requests']) >= self.state['max_requests'] or used + reserve > Decimal(self.state['limit_usd']):
                    raise ProviderConfigurationError('Approved inference campaign budget/request limit reached')
                self.state['requests'].append(dict(attempt_id=identity, model_id=body['model'],
                    started_at=utc_now(), status='outcome_unknown', max_tokens=maximum,
                    reserved_usd=str(reserve), charged_or_reserved_usd=str(reserve)))
                self._write()
                return identity
            except BaseException:
                self.lock_path.unlink(missing_ok=True)
                raise

    def acknowledge_abandoned(self, identity, *, owner_pid, evidence_ref):
        """Explicit host inspection only; never refunds or retries an unknown call.

        An exited local owner cannot write a late result. Remote execution and
        billing remain UNKNOWN and its full reservation continues to count.
        Empty legacy locks require the caller's saved owned-backend receipt.
        """
        if type(owner_pid) is not int or owner_pid <= 0 or not evidence_ref:
            raise ProviderConfigurationError('Exited owned-process evidence is required')
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
            kernel.OpenProcess.restype=wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes=(wintypes.HANDLE,wintypes.DWORD)
            kernel.WaitForSingleObject.restype=wintypes.DWORD
            kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
            handle=kernel.OpenProcess(0x00100000,False,owner_pid)
            if handle:
                try:exited=kernel.WaitForSingleObject(handle,0)==0
                finally:kernel.CloseHandle(handle)
            else:
                exited=ctypes.get_last_error()==87  # invalid PID, not access denied
        else:
            try:os.kill(owner_pid,0);exited=False
            except ProcessLookupError:exited=True
        if not exited:
            raise ProviderConfigurationError('Owner still alive or inspection denied; lock retained')
        with self._lock:
            lock=self.lock_path.read_text(encoding='utf-8')
            if lock and json.loads(lock)!=dict(owner_pid=owner_pid,attempt_id=identity):
                raise ProviderConfigurationError('Dispatch lock ownership does not match')
            self.state=json.loads(self.path.read_text(encoding='utf-8'))
            pending=[r for r in self.state['requests'] if not r.get('finished_at')]
            if len(pending)!=1 or pending[0]['attempt_id']!=identity:
                raise ProviderConfigurationError('Exactly one matching abandoned attempt is required')
            pending[0].update(finished_at=utc_now(),status='outcome_unknown',
                local_owner_exited=True,inspection_evidence=str(evidence_ref),
                remote_completion='UNKNOWN',billing='UNKNOWN')
            self._write()
            self.lock_path.unlink()

    def settle(self, identity, *, usage=None, status='outcome_unknown'):
        with self._lock:
            row = next(item for item in self.state['requests'] if item['attempt_id'] == identity)
            if row.get('finished_at'):
                return  # no duplicate late completion can refund/charge twice
            row.update(status=status, finished_at=utc_now())
            if usage and all(type(usage.get(k)) is int and usage[k] >= 0
                             for k in ('prompt_tokens', 'completion_tokens')):
                rate = self.state['rates'][row['model_id']]
                actual = (Decimal(str(rate['input_per_million'])) * usage['prompt_tokens']
                          + Decimal(str(rate['output_per_million'])) * usage['completion_tokens']) / 1000000
                row.update(usage=dict(usage), estimated_usd=str(actual), charged_or_reserved_usd=str(actual))
            self._write()
            self.lock_path.unlink(missing_ok=True)
