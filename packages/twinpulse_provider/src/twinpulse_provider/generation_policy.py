# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned generation limits; legacy route timeouts keep their old meaning.

One owner counts observer, batches and repairs together. This policy is not a
paid-call authorization and cannot extend an existing financial ledger.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
import time
from uuid import uuid4

from twinpulse_core import canonical_sha256
from twinpulse_core.generation_limits import MODEL_REQUEST_BOUNDS,REPAIR_REQUEST_BOUNDS,STALLED_REPAIR_BOUNDS
from .errors import ProviderConfigurationError, ProviderError


class GenerationBudgetError(ProviderError):
    def __init__(self, code):
        self.code = code
        self.repairable = False
        super().__init__(code)


@dataclass(frozen=True)
class GenerationPolicy:
    schema_version: str = 'generation-policy-1.0'
    per_call_timeout_s: int = 300
    total_timeout_s: int = 900
    max_requests: int = 12
    max_repairs: int = 3
    stalled_repairs: int = 2
    initial_timeout_s: int = 540
    repair_timeout_s: int = 300
    final_timeout_s: int = 60
    repair_start_margin_s: int = 90
    external_final_review: bool = False

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(asdict(cls())):
            raise ProviderConfigurationError('Explicit complete generation-policy-1.0 required')
        try:
            result = cls(**value)
        except TypeError as error:
            raise ProviderConfigurationError('Generation policy shape invalid') from error
        result.validate()
        return result

    def validate(self):
        if self.schema_version != 'generation-policy-1.0' or type(self.external_final_review) is not bool:
            raise ProviderConfigurationError('Generation policy version/review invalid')
        bounds = {'per_call_timeout_s': (1, 300), 'total_timeout_s': (1, 3600),
            'max_requests': MODEL_REQUEST_BOUNDS, 'max_repairs': REPAIR_REQUEST_BOUNDS, 'stalled_repairs': STALLED_REPAIR_BOUNDS,
            'initial_timeout_s': (1, 3600), 'repair_timeout_s': (0, 3600),
            'final_timeout_s': (1, 3600), 'repair_start_margin_s': (1, 300)}
        for key, (lo, hi) in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not lo <= value <= hi:
                raise ProviderConfigurationError('Generation policy invalid: '+key)
        if self.initial_timeout_s + self.repair_timeout_s + self.final_timeout_s > self.total_timeout_s:
            raise ProviderConfigurationError('Generation time allocations exceed total timeout')
        if self.max_requests - self.max_repairs - int(self.external_final_review) < 2:
            raise ProviderConfigurationError('Generation policy leaves fewer than two initial requests')
        if self.max_repairs and self.repair_timeout_s < self.repair_start_margin_s:
            raise ProviderConfigurationError('Repair reserve smaller than repair start margin')
        return self

    def to_dict(self):
        return asdict(self)

    @property
    def sha256(self):
        return canonical_sha256(self.to_dict())


class ExecutionBudget:
    """Thread-safe reserve-before-dispatch, unknown retains financial reservation.

The optional financial owner implements the existing CampaignLedger protocol.
Its approval is supplied independently by a trusted scope adapter, not inferred
from saving settings. Local fixtures may exercise counters without that owner.
"""
    def __init__(self, policy, *, clock=time.monotonic, financial_owner=None):
        self.policy = policy.validate()
        self.clock = clock
        self.started = clock()
        self.financial_owner = financial_owner
        self.usage_only = bool(getattr(financial_owner, 'product_usage', False))
        self.rows = []
        self.lock = RLock()
        self.in_flight = None
        self.repairs = 0
        self.no_progress = 0
        self.terminal = None
        self.initial_closed = False
        self.repair_used_s = 0.0
        self.final_used_s = 0.0
        self.prior_executions = []
        self.carried_requests = 0
        self.carried_repairs = 0
        self.carried_elapsed_s = 0

    def snapshot(self):
        with self.lock:
            result = {'policy_sha256': self.policy.sha256, 'requests': len(self.rows),
                'max_requests': self.policy.max_requests, 'repairs': self.repairs,
                'max_repairs': self.policy.max_repairs, 'stalled_repairs': self.no_progress,
                'stalled_repair_limit': self.policy.stalled_repairs,
                'carried_requests': self.carried_requests, 'carried_repairs': self.carried_repairs,
                'elapsed_s': round(max(0, self.clock()-self.started), 3),
                'remaining_s': round(max(0, self.policy.total_timeout_s-(self.clock()-self.started)-self.carried_elapsed_s), 3),
                'in_flight': self.in_flight, 'stop_reason': self.terminal,
                'repair_used_s': round(self.repair_used_s, 3),
                'final_used_s': round(self.final_used_s, 3),
                'financial_scope': 'bound' if self.financial_owner else 'not_bound',
                'prior_executions': [dict(row) for row in self.prior_executions],
                'cumulative_requests': len(self.rows) + sum(row['requests'] for row in self.prior_executions),
                'cumulative_active_s': round(max(0, self.clock()-self.started) + sum(
                    row['elapsed_s'] for row in self.prior_executions), 3),
                'automatic_retry': False, 'attempts': [dict(row) for row in self.rows]}
            if self.usage_only:
                rows = self.financial_owner.state['requests']
                result['financial_scope'] = 'usage_only'
                result['usage'] = {'attempts': len(rows),
                    'prompt_tokens': sum(r.get('usage',{}).get('prompt_tokens',0) for r in rows),
                    'completion_tokens': sum(r.get('usage',{}).get('completion_tokens',0) for r in rows),
                    'usage_missing': sum(not bool(r.get('usage')) for r in rows),
                    'estimated_usage_usd': None, 'invoice_verified': False}
            elif self.financial_owner:
                from decimal import Decimal
                state = self.financial_owner.state
                rows = state['requests']
                held = sum((Decimal(row['charged_or_reserved_usd']) for row in rows
                    if not row.get('usage')), Decimal(0))
                estimated = sum((Decimal(row['charged_or_reserved_usd']) for row in rows
                    if row.get('usage')), Decimal(0))
                result['cost'] = {'currency': 'USD', 'limit_usd': state['limit_usd'],
                    'estimated_usage_usd': str(estimated), 'reserved_unknown_usd': str(held),
                    'invoice_verified': False}
                previous_costs = [row.get('cost') for row in self.prior_executions]
                result['cumulative_cost'] = {'currency': 'USD',
                    'estimated_usage_usd': str(estimated + sum((Decimal(row['estimated_usage_usd'])
                        for row in previous_costs if row), Decimal(0))),
                    'reserved_unknown_usd': str(held + sum((Decimal(row['reserved_unknown_usd'])
                        for row in previous_costs if row), Decimal(0))),
                    'history_complete': all(row is not None for row in previous_costs),
                    'invoice_verified': False}
            return result

    def timeout_for(self, role):
        elapsed = self.clock()-self.started+self.carried_elapsed_s
        remaining = self.policy.total_timeout_s-elapsed
        if role == 'initial':
            remaining = min(remaining, self.policy.initial_timeout_s-elapsed)
        elif role == 'repair':
            # The final local/apply reserve is not borrowed by HTTP.
            remaining = min(remaining-self.policy.final_timeout_s,
                            self.policy.repair_timeout_s-self.repair_used_s)
            if remaining < self.policy.repair_start_margin_s:
                raise GenerationBudgetError('NEEDS_TIME_BUDGET')
        elif role == 'final_review':
            remaining = min(remaining, self.policy.final_timeout_s-self.final_used_s)
        else:
            raise GenerationBudgetError('BUDGET_ROLE_INVALID')
        if remaining <= 0:
            raise GenerationBudgetError('NEEDS_TIME_BUDGET')
        return min(self.policy.per_call_timeout_s, remaining)

    def reserve(self, body, *, role='initial'):
        with self.lock:
            if self.terminal:
                raise GenerationBudgetError(self.terminal)
            if self.in_flight is not None:
                raise GenerationBudgetError('DISPATCH_IN_FLIGHT')
            self.timeout_for(role)
            if len(self.rows)+self.carried_requests >= self.policy.max_requests:
                raise GenerationBudgetError('REQUEST_LIMIT_REACHED')
            # Repairs are a shared maximum, not guaranteed slots. Keep one
            # next repair plus the final review; reserve() still enforces the
            # exact cumulative HTTP and repair ceilings before financial I/O.
            reserved = int(self.repairs < self.policy.max_repairs) + int(self.policy.external_final_review)
            if role == 'initial' and (self.initial_closed or self.policy.max_requests-len(self.rows)-self.carried_requests <= reserved):
                raise GenerationBudgetError('NEEDS_REQUEST_BUDGET')
            if role == 'repair' and self.repairs >= self.policy.max_repairs:
                raise GenerationBudgetError('REPAIR_LIMIT_REACHED')
            if role == 'repair' and self.policy.external_final_review and self.policy.max_requests-len(self.rows)-self.carried_requests <= 1:
                raise GenerationBudgetError('NEEDS_REQUEST_BUDGET')
            if role == 'final_review' and not self.policy.external_final_review:
                raise GenerationBudgetError('FINAL_REVIEW_NOT_SELECTED')
            financial_body = dict(body)
            if 'max_tokens' not in financial_body and 'max_completion_tokens' in financial_body:
                financial_body['max_tokens'] = financial_body.pop('max_completion_tokens')
            identity = self.financial_owner.reserve(financial_body) if self.financial_owner else uuid4().hex
            self.rows.append({'attempt_id': identity, 'role': role, 'status': 'outcome_unknown',
                'model_id': body['model'], 'max_tokens': body.get('max_tokens', body.get('max_completion_tokens')),
                'started_elapsed_s': max(0, self.clock()-self.started)})
            self.in_flight = identity
            if role == 'repair':
                self.repairs += 1
            return identity

    def settle(self, identity, *, usage=None, status='outcome_unknown'):
        with self.lock:
            row = next((row for row in self.rows if row['attempt_id'] == identity), None)
            if row is None:
                raise GenerationBudgetError('ATTEMPT_ID_UNKNOWN')
            if row.get('settled'):
                return  # duplicate completion cannot refund/count twice
            if self.financial_owner:
                self.financial_owner.settle(identity, usage=usage, status=status)
            row.update(status=status, settled=True)
            row['elapsed_s'] = max(0, self.clock()-self.started-row['started_elapsed_s'])
            if row['role'] == 'repair':
                self.repair_used_s += row['elapsed_s']
            if row['role'] == 'final_review':
                self.final_used_s += row['elapsed_s']
            if usage:
                row['usage'] = {k: v for k, v in usage.items() if k in
                    {'prompt_tokens', 'completion_tokens', 'total_tokens'} and type(v) is int and v >= 0}
            self.in_flight = None
            if status == 'outcome_unknown':
                self.terminal = 'REMOTE_OUTCOME_UNKNOWN'

    def stop(self, code):
        with self.lock:
            self.terminal = self.terminal or code

    def repair_result(self, *, progressed, exploratory=False):
        with self.lock:
            if exploratory and not progressed:
                # New unresolved search is not validated progress or a repeated
                # response. The original request/repair/time bounds still apply.
                return
            self.no_progress = 0 if progressed else self.no_progress+1
            if self.no_progress >= self.policy.stalled_repairs:
                self.stop('REPAIR_STALLED')
                raise GenerationBudgetError('REPAIR_STALLED')


def diagnostic_blockers(diagnosis, fallback):
    """Compare exact remaining targets, not just a shared aggregate error code."""
    blockers = []
    for row in diagnosis.get('issues', []):
        if row.get('severity','error')!='error':continue
        prefix = row['code']+':'+row.get('path', '')
        targets = []
        for key in ('missing_ids', 'invalid_ids', 'target_ids'):
            if isinstance(row.get(key), list):
                targets.extend(prefix+':'+key+':'+str(identity) for identity in row[key])
        blockers.extend(targets or [prefix])
    if diagnosis.get('issues_truncated'):
        blockers.append('DIAGNOSTIC_TRUNCATED')
    return blockers or [fallback]


class ProgressTracker:
    """Semantic order-independent identity and blocker set; detect A -> B -> A."""
    def __init__(self):
        self.previous = None
        self.seen = set()
        self.metrics = None
        self.best_metrics = None
        self.best_errors = None
        self.best_blocked = set()
        self.best_previous = None
        self.regressed = False
        self.decision = 'initial'
        self.best_checks = {}
        self.advanced_checks = []
        self.history = []
        self.comparison_uncertain = False

    def snapshot(self):
        from copy import deepcopy
        return deepcopy(dict(schema_version='geometry-progress-1.0', seen=sorted(self.seen),
            previous=[self.previous[0],sorted(self.previous[1])] if self.previous else None,
            metrics=self.metrics, best_metrics=self.best_metrics,
            best_errors=sorted(self.best_errors) if self.best_errors is not None else None,
            best_previous=[self.best_previous[0],sorted(self.best_previous[1])] if self.best_previous else None,
            best_checks=self.best_checks, history=self.history))

    @classmethod
    def restore(cls, value):
        from copy import deepcopy
        if not isinstance(value,dict) or value.get('schema_version')!='geometry-progress-1.0':
            raise ProviderConfigurationError('CONTINUATION_PROGRESS_HISTORY_UNAVAILABLE')
        try:
            result=cls()
            result.seen=set(value['seen'])
            for name in ('previous','best_previous'):
                pair=value[name]
                setattr(result,name,(pair[0],frozenset(pair[1])) if pair else None)
            result.best_errors=frozenset(value['best_errors']) if value['best_errors'] is not None else None
            for name in ('metrics','best_metrics','best_checks','history'):
                setattr(result,name,deepcopy(value[name]))
            if not isinstance(result.best_checks,dict) or not isinstance(result.history,list):raise ValueError('shape')
            return result
        except (KeyError,TypeError,ValueError,IndexError) as error:
            raise ProviderConfigurationError('CONTINUATION_PROGRESS_HISTORY_INVALID') from error

    def observe(self, candidate, blockers, diagnosis=None):
        # Stable entity IDs are part of the contract; ordering is not progress.
        from copy import deepcopy
        value = deepcopy(candidate)
        if isinstance(value, dict):
            for key in ('objects', 'inventory'):
                if isinstance(value.get(key), list):
                    value[key].sort(key=lambda row: str(row.get('id', '')) if isinstance(row, dict) else str(row))
        if isinstance(value, dict):
            value.pop('summary', None)
        digest = canonical_sha256(value)
        errors = frozenset(blockers)
        metrics = {row.get('issue_id') or row['code']+':'+row.get('path',''):row['violation_m']
            for row in (diagnosis or {}).get('issues',[]) if isinstance(row.get('violation_m'),(int,float))}
        improved_numeric = bool(self.best_metrics) and errors==self.best_errors and set(metrics)==set(self.best_metrics)
        if improved_numeric:
            improved_numeric = all(metrics[k]<=v+1e-9 for k,v in self.best_metrics.items()) and any(
                metrics[k]<v-1e-6 for k,v in self.best_metrics.items())
        progressed = self.previous is not None and digest not in self.seen and (
            errors < (self.best_errors or frozenset()) or improved_numeric)
        # Compare to the best checked candidate, not a failed patch/summary.
        # New errors exposed by formerly blocked checks remain exploratory.
        from twinpulse_core.geometry_checks import CHECK_REVISION, PHASES
        report=diagnosis or {}
        rows=report.get('checks',[])
        valid_ledger=bool(rows) and report.get('check_ledger_version')==CHECK_REVISION and not report.get('checks_truncated')
        valid_ledger=valid_ledger and report.get('mandatory_checks')==list(PHASES) and len(rows)==len(PHASES)
        valid_ledger=valid_ledger and all(isinstance(r,dict) and r.get('status') in
            ('passed','partial','failed','blocked','not_run','error') and r.get('candidate_revision')==report.get('candidate_revision')
            and r.get('checker_revision')==CHECK_REVISION and r.get('check_id') in PHASES
            and isinstance(r.get('depends_on'),list) and isinstance(r.get('issue_refs'),list)
            for r in rows)
        checks={r['check_id']:r for r in rows} if valid_ledger else {}
        valid_ledger=valid_ledger and set(checks)==set(PHASES)
        if valid_ledger and isinstance(value,dict) and all(k in value for k in ('room','inventory','objects')):
            objects=value['objects']
            if isinstance(objects,list):objects={r['id']:{k:v for k,v in r.items() if k!='id'} for r in objects}
            expected_revision=canonical_sha256({'room':value['room'],'inventory':value['inventory'],'objects':objects})
            valid_ledger=report.get('candidate_revision')==expected_revision
        if not valid_ledger:checks={}
        same_versions=bool(self.best_checks) and all(k in checks and all(checks[k].get(v)==old.get(v)
            for v in ('checker_revision','compiler_revision','library_revision')) for k,old in self.best_checks.items())
        fixed={k for k,old in self.best_checks.items() if old['status']=='failed' and
            k in checks and checks[k]['status']=='passed'} if same_versions else set()
        self.advanced_checks=[k for k,old in self.best_checks.items() if old['status']=='blocked' and
            k in checks and checks[k]['status'] in ('passed','failed') and
            bool(fixed & set(checks[k].get('depends_on',[])))] if same_versions else []
        new_errors=errors-(self.best_errors or frozenset())
        self.comparison_uncertain=bool(same_versions and
            self.best_checks.get('floor_packing',{}).get('status')=='failed' and
            checks.get('floor_packing',{}).get('status')=='failed' and
            any(e.startswith('PHOTO_LAYOUT_REGION_FULL:') for e in errors))
        if self.comparison_uncertain:
            # Greedy/fallback failure exposes a bounded conflict set, not a
            # numerical global-feasibility score. A new first failure or fewer
            # unplaced proxies cannot establish either improvement or regression.
            new_errors={e for e in new_errors if not e.startswith('PHOTO_LAYOUT_REGION_FULL:')}
            progressed=False
        exposed_refs={ref for k in self.advanced_checks for ref in checks[k].get('issue_refs',[])}
        exposed_problems=set(diagnostic_blockers({'issues':[r for r in report.get('issues',[])
            if r.get('issue_id',r.get('code')) in exposed_refs]},''))-{''}
        self.regressed = bool(diagnosis is not None and self.best_errors is not None and
            any(e not in exposed_problems for e in new_errors))
        if same_versions:
            self.regressed = self.regressed or any(old['status']=='passed' and checks[k]['status'] in ('failed','partial')
                for k,old in self.best_checks.items())
        if self.best_metrics is not None:
            self.regressed = self.regressed or any(metrics[k]>self.best_metrics[k]+1e-6
                for k in set(metrics)&set(self.best_metrics))
        insufficient=(bool(rows) and not valid_ledger or report.get('issues_truncated') is True or
            any(r['status']=='error' for r in checks.values()) or
            bool(self.best_checks) and valid_ledger and not same_versions or
            same_versions and not self.regressed and any(old['status'] in ('passed','partial','failed') and checks[k]['status'] in ('blocked','not_run')
                for k,old in self.best_checks.items()))
        if self.advanced_checks and not self.regressed:progressed=True
        if self.comparison_uncertain:progressed=False
        if self.regressed or insufficient or digest in self.seen:progressed=False
        self.decision = ('evidence_insufficient' if insufficient else 'repeated_candidate' if digest in self.seen else
            'rollback' if self.regressed else 'advanced_checks' if progressed and self.advanced_checks else
            'progress' if progressed else 'initial' if self.previous is None else
            'exploratory' if self.comparison_uncertain and not self.regressed and digest not in self.seen else 'no_progress')
        if self.best_errors is None or progressed:
            self.best_errors=errors;self.best_metrics=metrics.copy()
            self.best_checks=deepcopy(checks);self.best_previous=(digest,errors)
        self.seen.add(digest)
        self.previous = self.best_previous if self.regressed else (digest, errors)
        self.metrics=self.best_metrics.copy() if self.regressed else metrics
        self.history.append(dict(candidate_sha256=digest,decision=self.decision,progressed=progressed,
            advanced_checks=list(self.advanced_checks),regressed=self.regressed,
            comparison_uncertain=self.comparison_uncertain,
            **({'comparison_basis':'same_unresolved_bounded_floor_packing_phase'} if self.comparison_uncertain else {})))
        return progressed

    def rebind_locally_checked_best(self, candidate, report):
        """Repair a legacy tracker baseline only from a fresh compiler report.

        Partial is valid incomplete evidence, never whole-scene PASS. Preserve
        seen candidates, history and the caller's request/repair/stall budgets.
        """
        from copy import deepcopy
        probe=type(self)()
        probe.observe(candidate,[],report)
        if (not probe.best_checks or not all(r['status'] in ('passed','partial')
                for r in probe.best_checks.values()) or not (
                report.get('checks_complete') is True or report.get('materialized_subset_checked') is True)):
            raise ProviderConfigurationError('CONTINUATION_BEST_REVALIDATION_INVALID')
        self.best_checks=deepcopy(probe.best_checks)
        self.best_metrics=deepcopy(probe.best_metrics)
        self.best_errors=probe.best_errors
        self.best_previous=probe.best_previous
        self.seen.add(probe.best_previous[0])
        self.history.append(dict(decision='best_locally_revalidated',
            candidate_sha256=probe.best_previous[0],progressed=False,
            checks_complete=report.get('checks_complete') is True,
            materialized_subset_checked=report.get('materialized_subset_checked') is True))
