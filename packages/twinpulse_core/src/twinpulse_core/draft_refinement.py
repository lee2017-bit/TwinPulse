# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Durable incomplete visual refinement of an independently valid tool plan.

This is neither photo quality acceptance nor a world/robot authority record.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
from .revisions import canonical_sha256
from .geometry_checks import CHECK_REVISION,PHASES
from .generation_limits import MODEL_REQUEST_BOUNDS,REPAIR_REQUEST_BOUNDS,STALLED_REPAIR_BOUNDS,LEGACY_STALLED_REPAIR_LIMIT

VERSION='draft-refinement-1.0'
ACCEPTANCE='GEOMETRY_VALID_REFINEMENT_INCOMPLETE'
SUBSET_VERSION='draft-refinement-1.1'
SUBSET_ACCEPTANCE='MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE'
STOPS={'QUALITY_REPAIR_LIMIT_REACHED','REPAIR_STALLED'}


def create_refinement(plan,*,request_id,candidate_revision,source_observation_sha256,quality,checks,budget,progressive=None):
    subset=bool(progressive and progressive.get('unresolved'))
    ledger={k:deepcopy(checks[k]) for k in ('check_ledger_version','candidate_revision','checks',
        'mandatory_checks','checks_complete','checks_truncated')}
    if subset:ledger.update(materialized_subset_checked=checks.get('materialized_subset_checked'),
        inventory_complete=checks.get('inventory_complete'))
    body=dict(schema_version=SUBSET_VERSION if subset else VERSION,
        acceptance=SUBSET_ACCEPTANCE if subset else ACCEPTANCE,request_id=request_id,
        candidate_revision=candidate_revision,plan_sha256=canonical_sha256(plan),
        source_observation_sha256=source_observation_sha256,quality_review=deepcopy(quality),
        geometry_checks=ledger,stop_reason=budget['stop_reason'],budget=deepcopy(budget),physical_authority=False)
    if subset:body['progressive_sha256']=progressive['sha256']
    return checked_refinement({**body,'sha256':canonical_sha256(body)},plan,request_id=request_id,progressive=progressive)


def checked_refinement(value,plan,*,request_id,progressive=None):
    subset=isinstance(value,dict) and value.get('schema_version')==SUBSET_VERSION
    fields={'schema_version','acceptance','request_id','candidate_revision','plan_sha256',
        'source_observation_sha256','quality_review','geometry_checks','stop_reason','budget','physical_authority','sha256'}
    if subset:fields.add('progressive_sha256')
    if (not isinstance(value,dict) or set(value)!=fields or value['schema_version']!=(SUBSET_VERSION if subset else VERSION) or
            value['acceptance']!=(SUBSET_ACCEPTANCE if subset else ACCEPTANCE) or value['request_id']!=request_id or
            value['physical_authority'] is not False or value['stop_reason'] not in STOPS or
            value['plan_sha256']!=canonical_sha256(plan) or
            value['sha256']!=canonical_sha256({k:v for k,v in value.items() if k!='sha256'})):
        raise ValueError('DRAFT_REFINEMENT_BINDING_INVALID')
    if subset:
        from .progressive_twin import checked_envelope
        witness=checked_envelope(progressive,plan)
        if not witness['unresolved'] or witness['sha256']!=value['progressive_sha256']:
            raise ValueError('DRAFT_REFINEMENT_PROGRESSIVE_INVALID')
    elif progressive and progressive.get('unresolved'):
        raise ValueError('DRAFT_REFINEMENT_PROGRESSIVE_INVALID')
    if len(json.dumps(value,allow_nan=False).encode())>1024*1024:raise ValueError('DRAFT_REFINEMENT_BUDGET')
    for name in ('candidate_revision','source_observation_sha256'):
        if not isinstance(value[name],str) or len(value[name])!=64 or any(c not in '0123456789abcdef' for c in value[name]):
            raise ValueError('DRAFT_REFINEMENT_SHA_INVALID')
    quality=value['quality_review'];checks=value['geometry_checks'];budget=value['budget']
    if (not isinstance(quality,dict) or quality.get('schema_version') not in
            {'candidate-quality-review-1.0','current-render-review-1.0'} or
            quality.get('status')!='needs_revision' or quality.get('physical_authority') is not False or
            quality.get('candidate_revision')!=value['candidate_revision'] or
            quality.get('plan_sha256')!=value['plan_sha256'] or
            not isinstance(quality.get('issues'),list) or not 1<=len(quality['issues'])<=128):
        raise ValueError('DRAFT_REFINEMENT_QUALITY_INVALID')
    ids={c['arguments']['id'] for c in plan['calls']}
    for issue in quality['issues']:
        if (not isinstance(issue,dict) or not isinstance(issue.get('code'),str) or
                not issue['code'].startswith(('PHOTO_','RENDER_')) or issue.get('severity')!='error' or
                not isinstance(issue.get('target_ids'),list) or not issue['target_ids'] or
                any(not isinstance(i,str) for i in issue['target_ids']) or
                not isinstance(issue.get('related_ids',[]),list) or
                any(not isinstance(i,str) for i in issue.get('related_ids',[])) or
                not set(issue['target_ids'])<=ids or not set(issue.get('related_ids',[]))<=ids or
                issue.get('repairable') is not True):
            raise ValueError('DRAFT_REFINEMENT_ISSUE_INVALID')
    if (not isinstance(checks,dict) or checks.get('check_ledger_version')!=CHECK_REVISION or
            checks.get('candidate_revision')!=value['candidate_revision'] or
            checks.get('mandatory_checks')!=list(PHASES) or checks.get('checks_complete') is not (not subset) or
            checks.get('checks_truncated') is not False or not isinstance(checks.get('checks'),list) or
            len(checks['checks'])!=len(PHASES) or any(not isinstance(r,dict) for r in checks['checks']) or
            [r.get('check_id') for r in checks['checks']]!=list(PHASES) or
            any(r.get('status')!=('partial' if subset and r.get('check_id')=='support_packing' else 'passed') or r.get('candidate_revision')!=value['candidate_revision'] or
                r.get('checker_revision')!=CHECK_REVISION for r in checks['checks'])):
        raise ValueError('DRAFT_REFINEMENT_GEOMETRY_INVALID')
    if subset and (checks.get('materialized_subset_checked') is not True or
            checks.get('inventory_complete') is not False or any(
                set(r.get('target_ids',[]))!={i['id'] for i in witness['inventory']} for r in checks['checks'])):
        raise ValueError('DRAFT_REFINEMENT_GEOMETRY_INVALID')
    def known_cost(cost):
        if not isinstance(cost,dict):return False
        try:
            held=Decimal(cost['reserved_unknown_usd'])
            return held.is_finite() and held==0
        except (KeyError,ValueError,TypeError,InvalidOperation):return False
    # Older records omit explicit carried/threshold fields. Prior request counts
    # are local, but prior repair counts are cumulative: never sum repairs.
    history=budget.get('prior_executions',[]) if isinstance(budget,dict) else None
    history_valid=isinstance(history,list)
    prior_requests=prior_repairs=0
    if history_valid:
        for row in history:
            if (not isinstance(row,dict) or type(row.get('requests')) is not int or
                    not 0<=row['requests']<=MODEL_REQUEST_BOUNDS[1] or
                    type(row.get('repairs')) is not int or not prior_repairs<=row['repairs']<=REPAIR_REQUEST_BOUNDS[1] or
                    row['repairs']-prior_repairs>row['requests'] or
                    row.get('stop_reason')=='REMOTE_OUTCOME_UNKNOWN'):
                history_valid=False;break
            prior_requests+=row['requests'];prior_repairs=row['repairs']
    stalled_limit=budget.get('stalled_repair_limit',LEGACY_STALLED_REPAIR_LIMIT) if isinstance(budget,dict) else None
    if (not isinstance(budget,dict) or budget.get('stop_reason')!=value['stop_reason'] or
            budget.get('in_flight') is not None or not isinstance(budget.get('attempts'),list) or
            type(budget.get('max_requests')) is not int or not MODEL_REQUEST_BOUNDS[0]<=budget['max_requests']<=MODEL_REQUEST_BOUNDS[1] or
            type(budget.get('max_repairs')) is not int or not REPAIR_REQUEST_BOUNDS[0]<=budget['max_repairs']<=REPAIR_REQUEST_BOUNDS[1] or
            type(budget.get('requests')) is not int or not 0<=budget['requests']<=budget['max_requests'] or
            not history_valid or (budget['requests']==0 and prior_requests==0) or
            type(budget.get('carried_requests',prior_requests)) is not int or budget.get('carried_requests',prior_requests)!=prior_requests or
            type(budget.get('carried_repairs',prior_repairs)) is not int or budget.get('carried_repairs',prior_repairs)!=prior_repairs or
            type(budget.get('cumulative_requests',budget['requests']+prior_requests)) is not int or
            budget.get('cumulative_requests',budget['requests']+prior_requests)!=budget['requests']+prior_requests or
            budget['requests']+prior_requests>budget['max_requests'] or
            budget['requests']!=len(budget['attempts']) or budget.get('automatic_retry') is not False or
            type(budget.get('repairs')) is not int or not 0<=budget['repairs']<=budget['max_repairs'] or
            len(budget['attempts'])>budget.get('max_requests',0) or
            any(not isinstance(r,dict) for r in budget['attempts']) or
            budget['repairs']!=prior_repairs+sum(r.get('role')=='repair' for r in budget['attempts']) or
            type(stalled_limit) is not int or not STALLED_REPAIR_BOUNDS[0]<=stalled_limit<=STALLED_REPAIR_BOUNDS[1] or
            any(r.get('status')!='received' or r.get('settled') is not True for r in budget['attempts']) or
            (value['stop_reason']=='QUALITY_REPAIR_LIMIT_REACHED' and budget['repairs']!=budget['max_repairs']) or
            (value['stop_reason']=='REPAIR_STALLED' and
                (type(budget.get('stalled_repairs')) is not int or not stalled_limit<=budget['stalled_repairs']<=budget['repairs'])) or
            (budget.get('financial_scope')=='bound' and
                (not known_cost(budget.get('cost')) or
                 ('cumulative_cost' in budget and (not known_cost(budget['cumulative_cost']) or
                    budget['cumulative_cost'].get('history_complete') is not True)))) or
            budget.get('financial_scope') not in ('bound','not_bound','usage_only')):
        raise ValueError('DRAFT_REFINEMENT_OUTCOME_UNKNOWN')
    return deepcopy(value)


def public_refinement(value,current_plan,*,pending_context_current=None):
    if value is None:return None
    current=current_plan is not None and canonical_sha256(current_plan)==value['plan_sha256']
    if value['schema_version']==SUBSET_VERSION:current=current and pending_context_current is True
    return {**deepcopy(value),'current':current,
        'assessment_state':'needs_revision' if current else 'recheck_required',
        'world_alignment':'NOT_VERIFIED','physical_validation':'NOT_RUN'}
