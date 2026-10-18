# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen functional inputs and incremental financial admission, not a benchmark.

No geometry answers, fixture responses or credential export. All ordinary
approval ledgers (including edits) are audited; UNKNOWN reserves remain held.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from scripts.benchmark_protocol import canonical_sha, file_sha, read_json, source_freeze

OBSERVER = 'deepseek-ai/DeepSeek-V4.1-Flash'
PLANNER = 'nvidia/nemotron-3-super-120b-a12b'
DEADLINE = '2026-10-11T22:33:20+00:00'


def exclusive(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())


def update(path, value):
    path = Path(path); temporary = path.with_name(path.name+'.new')
    exclusive(temporary, value); os.replace(temporary, path)


def check_scope(path, root, *, frozen=True):
    scope = read_json(path)
    if (scope['schema_version'] != 'progressive-functional-scope-1.0'
            or scope['approval_at'] != '2026-10-11T14:33:20+00:00'
            or scope['expires_at'] != DEADLINE
            or scope['models'] != dict(observer=OBSERVER, planner=PLANNER)
            or Decimal(scope['additional_limit_usd']) != Decimal('10')
            or Decimal(scope['historical_protected_usd']) != Decimal('7.15488417')
            or scope['physical_authority'] or scope['cloud_authority']):
        raise ValueError('FUNCTIONAL_APPROVAL_SCOPE_CHANGED')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(scope['expires_at']):
        raise ValueError('FUNCTIONAL_APPROVED_PERIOD_ENDED')
    if frozen and source_freeze(root) != scope['source_freeze']:
        raise ValueError('FUNCTIONAL_SOURCE_BUILD_CHANGED')
    for name, digest in scope['settings_freeze'].items():
        if file_sha(name) != digest: raise ValueError('FUNCTIONAL_SETTINGS_CHANGED')
    for name,digest in scope.get('prior_finance_freeze',{}).items():
        if file_sha(name)!=digest:raise ValueError('FUNCTIONAL_PRIOR_FINANCE_CHANGED')
    for case in scope['cases']:
        if case['prompt_sha256'] != hashlib.sha256(case['prompt'].encode()).hexdigest():
            raise ValueError('FUNCTIONAL_PROMPT_CHANGED')
        if case['input_mode'] not in ('text_only', 'image_only', 'text_plus_image', 'robot_photo'):
            raise ValueError('FUNCTIONAL_INPUT_MODE_INVALID')
        image = case['image']
        if image and (not case['external_transmission_allowed'] or file_sha(image['path']) != image['sha256']):
            raise ValueError('FUNCTIONAL_PHOTO_CHANGED_OR_UNAPPROVED')
        if (case['input_mode'] == 'image_only' and case['prompt'] != ''
                or case['input_mode'] == 'text_only' and image is not None
                or case['input_mode'] != 'text_only' and image is None):
            raise ValueError('FUNCTIONAL_INPUT_MODE_MISMATCH')
    return scope


def reserve(scope, path, case_id):
    state = read_json(path)
    if state['scope_sha256'] != canonical_sha(scope): raise ValueError('FUNCTIONAL_STATE_SCOPE_CHANGED')
    if any(row['case_id'] == case_id for row in state['runs']): raise ValueError('FUNCTIONAL_CASE_ALREADY_DISPATCHED')
    if any(not row['settled'] for row in state['runs']): raise ValueError('FUNCTIONAL_UNSETTLED_OWNER')
    if state.get('stop_reason'):raise ValueError('FUNCTIONAL_GATED_STOP')
    if any(row['unknown_requests'] or Decimal(row['held_usd']) for row in state['runs']):
        raise ValueError('FUNCTIONAL_UNKNOWN_BILLING_STOP')
    amounts=[Decimal(row[key]) for row in state['runs'] for key in ('estimated_usd','held_usd')]
    if any(not amount.is_finite() or amount<0 for amount in amounts):
        raise ValueError('FUNCTIONAL_INVALID_FINANCIAL_STATE')
    prior=Decimal(state.get('prior_new_exposure_usd','0'))
    if not prior.is_finite() or prior<0 or prior!=Decimal(scope.get('prior_new_exposure_usd','0')):
        raise ValueError('FUNCTIONAL_PRIOR_EXPOSURE_CHANGED')
    exposure = sum(amounts, prior)
    case = next(row for row in scope['cases'] if row['case_id'] == case_id)
    cap = Decimal(case['reservation_usd'])
    if not cap.is_finite() or cap<=0 or case['request_limit'] not in (12,13,14):
        raise ValueError('FUNCTIONAL_INVALID_CASE_CAP')
    if exposure+cap > Decimal(scope['additional_limit_usd']): raise ValueError('FUNCTIONAL_ADDITIONAL_BUDGET_EXCEEDED')
    if (datetime.fromisoformat(scope['expires_at'])-datetime.now(timezone.utc)).total_seconds() < 3600:
        raise ValueError('FUNCTIONAL_DEADLINE_ADMISSION_STOP')
    row = dict(case_id=case_id, settled=False, status='DISPATCH_RESERVED',
               estimated_usd='0', held_usd=str(cap), unknown_requests=0,
               reserved_at=datetime.now(timezone.utc).isoformat())
    state['runs'].append(row); update(path, state)
    return case


def audit_runtime(runtime, *, request_limit, total_limit, require_validation=True):
    """Each response/dispatch/ledger identity; no inference of zero missing usage."""
    runtime = Path(runtime); directory = runtime/'ordinary-generation'
    ledgers = sorted(directory.glob('*.ledger.json'))
    if not ledgers or list(directory.glob('*.dispatch-lock')):
        raise ValueError('FUNCTIONAL_LEDGER_OR_DISPATCH_UNSETTLED')
    evidence = runtime/'provider-evidence'; rows=[]; identities=set()
    estimated=held=Decimal(0); unknown=0
    for ledger_path in ledgers:
        ledger=read_json(ledger_path)
        for request in ledger['requests']:
            attempt=request['attempt_id']
            if attempt in identities:raise ValueError('FUNCTIONAL_DUPLICATE_ATTEMPT')
            identities.add(attempt)
            raw=read_json(evidence/(attempt+'.json'))
            dispatch=read_json(evidence/'dispatches'/(attempt+'.json'))
            if (raw['status']!=request['status'] or raw.get('usage')!=request.get('usage')
                    or raw['response_truncated'] or dispatch['request_truncated']
                    or hashlib.sha256(raw['response_redacted'].encode()).hexdigest()!=raw['stored_response_sha256']
                    or hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest()!=dispatch['stored_request_sha256']
                    or any(raw[k]!=dispatch[k] for k in ('request_sha256','schema_sha256','execution_id'))):
                raise ValueError('FUNCTIONAL_RAW_FINANCIAL_IDENTITY_CHANGED')
            amount=Decimal(request['charged_or_reserved_usd'])
            if not amount.is_finite() or amount<0:raise ValueError('FUNCTIONAL_INVALID_AMOUNT')
            if request.get('usage'):estimated+=amount
            else:held+=amount
            if request['status'] not in ('received','rejected') or not request.get('finished_at'):unknown+=1
            validations=sorted((evidence/'validations').glob(attempt+'-*.json'))
            if request['status']=='received' and not validations and require_validation:
                raise ValueError('FUNCTIONAL_VALIDATION_MISSING')
            for file in validations:
                value=read_json(file)
                if (value['record_truncated'] or value['attempt_id']!=attempt
                        or value['execution_id']!=raw['execution_id']
                        or hashlib.sha256(value['record_redacted'].encode()).hexdigest()!=value['stored_record_sha256']):
                    raise ValueError('FUNCTIONAL_VALIDATION_CHANGED')
            rows.append(dict(attempt_id=attempt,execution_id=raw['execution_id'],role=raw['role'],
                model_id=raw['model_id'],status=request['status'],finish_reason=raw.get('finish_reason'),
                elapsed_s=raw['elapsed_s'],usage=raw.get('usage'),amount_usd=str(amount),
                validation_complete=bool(validations),http_status=raw.get('http_status'),
                raw_sha256=file_sha(evidence/(attempt+'.json')),dispatch_sha256=file_sha(evidence/'dispatches'/(attempt+'.json'))))
    if len(rows)>request_limit or estimated+held>Decimal(total_limit):raise ValueError('FUNCTIONAL_APPROVED_TRIAL_CAP_EXCEEDED')
    return dict(status='RAW_FINANCE_AUDIT_PASS_NOT_PRODUCT_PASS',estimated_usd=str(estimated),
        held_usd=str(held),unknown_requests=unknown,ledger_count=len(ledgers),request_count=len(rows),
        invoice_verified=False,rows=rows)


def host_finance_supplement(scope_path, root):
    """Prove one host audit defect without altering UNKNOWN or releasing its hold.

    This is NOT a general UNKNOWN override: all wire requests must be received,
    complete, independently re-priced and closed. Missing validation is still
    product evidence failure. The original full reservation is carried forward.
    """
    scope_path=Path(scope_path).resolve();root=Path(root).resolve()
    if not scope_path.is_relative_to(root/'outputs/progressive-twin-overnight-20261012'):
        raise ValueError('FUNCTIONAL_SUPPLEMENT_OUTSIDE_APPROVED_OUTPUT')
    scope=check_scope(scope_path,root,frozen=False)
    directory=scope_path.parent;state_path=directory/'functional-finance.json';state=read_json(state_path)
    if state['scope_sha256']!=canonical_sha(scope) or (directory/'functional-owner.lock').exists():
        raise ValueError('FUNCTIONAL_SUPPLEMENT_OWNER_OR_SCOPE_UNRESOLVED')
    rows=state['runs']
    if len(rows)!=1 or rows[0].get('product_status')!='FAIL':
        raise ValueError('FUNCTIONAL_SUPPLEMENT_NOT_TYPED_HOST_FAILURE')
    row=rows[0];case=next(c for c in scope['cases'] if c['case_id']==row['case_id'])
    if (row['settled'] or row['status']!='UNKNOWN' or row.get('audit_error_type')!='ValueError'
            or Decimal(row['held_usd'])!=Decimal(case['reservation_usd'])
            or Decimal(row['estimated_usd']) or row['unknown_requests']!=1):
        raise ValueError('FUNCTIONAL_SUPPLEMENT_NOT_FULL_PROTECTED_HOLD')
    output=directory/row['case_id'];runtime=output/'runtime';result=read_json(output/'result.json')
    if (result['status']!='FAIL' or result.get('financial_audit_error')!='ValueError'
            or not result.get('source_and_build_unchanged') or not result.get('scope_settings_unchanged')
            or result.get('cleanup_error')
            or any(result['supervisor'].get(k,{}).get('owned') for k in ('backend','engine'))):
        raise ValueError('FUNCTIONAL_SUPPLEMENT_PRODUCT_OR_OWNER_UNRESOLVED')
    try:
        audit_runtime(runtime,request_limit=case['request_limit'],total_limit=case['reservation_usd'])
    except ValueError as error:
        if str(error)!='FUNCTIONAL_VALIDATION_MISSING':raise
    else:raise ValueError('FUNCTIONAL_SUPPLEMENT_TYPED_DEFECT_NOT_REPRODUCED')
    audit=audit_runtime(runtime,request_limit=case['request_limit'],total_limit=case['reservation_usd'],require_validation=False)
    if audit['unknown_requests'] or Decimal(audit['held_usd']) or not audit['rows']:
        raise ValueError('FUNCTIONAL_SUPPLEMENT_REAL_BILLING_UNKNOWN')
    evidence=runtime/'provider-evidence';ordinary=runtime/'ordinary-generation'
    attempts={r['attempt_id'] for r in audit['rows']}
    if ({p.stem for p in evidence.glob('*.json')}!=attempts
            or {p.stem for p in (evidence/'dispatches').glob('*.json')}!=attempts
            or any(p.name.split('-')[0] not in attempts for p in (evidence/'validations').glob('*.json'))):
        raise ValueError('FUNCTIONAL_SUPPLEMENT_ORPHAN_OR_MISSING_ATTEMPT')
    catalog_path=directory/'stage-model-catalog.json'
    bound_catalogs=[sha for path,sha in scope['settings_freeze'].items() if Path(path).name=='stage_model_catalog.json']
    if len(bound_catalogs)!=1 or file_sha(catalog_path)!=bound_catalogs[0]:
        raise ValueError('FUNCTIONAL_SUPPLEMENT_CATALOG_NOT_ORIGINALLY_FROZEN')
    catalog=read_json(catalog_path);rates={r['model_id']:r for r in catalog['models']}
    recalculated=Decimal(0)
    for ledger_path in ordinary.glob('*.ledger.json'):
        ledger=read_json(ledger_path)
        binding=read_json(ledger_path.with_name(ledger_path.name.replace('.ledger.json','.ledger.ordinary-scope.json')))
        if binding['rates_sha256']!=canonical_sha(ledger['rates']):
            raise ValueError('FUNCTIONAL_SUPPLEMENT_RATE_BINDING_CHANGED')
        for request in ledger['requests']:
            raw=read_json(evidence/(request['attempt_id']+'.json'))
            model=request['model_id'];rate=ledger['rates'].get(model);frozen=rates.get(model)
            if (model not in scope['models'].values() or rate is None or frozen is None
                    or any(Decimal(rate[k])!=Decimal(frozen[k]) for k in ('input_per_million','output_per_million'))
                    or request['status']!='received' or raw.get('http_status')!=200
                    or raw.get('finish_reason')!='stop' or raw.get('final_empty')
                    or raw.get('model_id')!=model):
                raise ValueError('FUNCTIONAL_SUPPLEMENT_WIRE_OR_RATE_UNCONFIRMED')
            usage=request['usage'];tokens=[usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')]
            if any(type(n) is not int or n<0 for n in tokens) or tokens[0]+tokens[1]!=tokens[2]:
                raise ValueError('FUNCTIONAL_SUPPLEMENT_USAGE_INCOMPLETE')
            calculated=(Decimal(tokens[0])*Decimal(rate['input_per_million'])+
                        Decimal(tokens[1])*Decimal(rate['output_per_million']))/Decimal(1000000)
            if calculated!=Decimal(request['charged_or_reserved_usd']) or calculated!=Decimal(request['estimated_usd']):
                raise ValueError('FUNCTIONAL_SUPPLEMENT_PRICE_RECALCULATION_CHANGED')
            recalculated+=calculated
    if recalculated!=Decimal(audit['estimated_usd']):raise ValueError('FUNCTIONAL_SUPPLEMENT_TOTAL_CHANGED')
    witnesses=[scope_path,state_path,directory/'stage-model-catalog.json',output/'result.json',
        *ordinary.glob('*.json'),*evidence.glob('*.json'),*(evidence/'dispatches').glob('*.json'),
        *(evidence/'validations').glob('*.json')]
    return dict(schema_version='progressive-host-finance-supplement-1.0',
        classification='HOST_VALIDATION_ARTIFACT_MISSING_MONETARY_EVIDENCE_COMPLETE',
        scope_path=str(scope_path),case_id=row['case_id'],original_status='UNKNOWN',
        original_product_status='FAIL',product_validation='INCOMPLETE',
        protected_exposure_usd=row['held_usd'],estimated_wire_usd=str(recalculated),
        original_hold_released=False,invoice_verified=False,raw_audit=audit,
        witnesses={str(p):file_sha(p) for p in sorted(set(witnesses))})


def read_host_finance_supplement(scope_path, root):
    path=Path(scope_path).parent/'host-finance-supplement.json';stored=read_json(path)
    current=host_finance_supplement(scope_path,root)
    if stored!=current:raise ValueError('FUNCTIONAL_SUPPLEMENT_EVIDENCE_CHANGED')
    return path,current
