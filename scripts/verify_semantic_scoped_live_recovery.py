# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Controlled recovery, using the production loop and real Nemotron repairs.

Initial context is replayed from a successful live run, never counted as fresh
model output. A copy receives one generic fault. Only repair requests reach the
registered planner. A separate remainder ledger carries ALL prior calls/cost.
No App/Isaac/robot commands, new photo upload, settings change, or new approval.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_core.execution_diagnostics import ExecutionStore
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import build_configured_stage_service
from twinpulse_provider.contracts import CancellationToken, GenerationRequest, ImageInput
from twinpulse_provider.nebius_pipeline import ObservationArtifact, parse_chat_completion
from twinpulse_provider.generation_store import input_digest
from twinpulse_provider.reliability import CampaignLedger, InferenceEvidence
from twinpulse_provider.semantic_scene import (checked_structure, checked_batch, scene_draft,
    compile_scene, compiler_diagnosis, revision)
from twinpulse_provider.semantic_bindings import (replay_legacy_structure_patch, repair_structure,
    repair_batch, STRUCTURE_REPAIR_REVISION)
from twinpulse_provider.stage_transport import has_image

NANO = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def context(prior, case):
    run = prior/'run-1'
    summary = read(prior/'summary.json')
    if (summary['status'] != 'PASS' and case != 'geometry') or not summary['originals_unchanged']:
        raise ValueError('A successful immutable original live run is required')
    paths = list((run/'runtime/ordinary-generation').glob('*.ledger.json'))
    if len(paths) != 1:
        raise ValueError('Exactly one original paid approval required')
    ledger = read(paths[0])
    if (ledger['max_requests'] != 10 or Decimal(ledger['limit_usd']) != 1
            or paths[0].with_suffix('.dispatch-lock').exists()
            or any(not r.get('finished_at') or r['status'] != 'received' for r in ledger['requests'])):
        raise ValueError('Original paid accounting is unsettled or changed')
    records = []
    for row in ledger['requests']:
        raw = read(run/'runtime/provider-evidence'/f"{row['attempt_id']}.json")
        if (hashlib.sha256(raw['response_redacted'].encode()).hexdigest() != raw['stored_response_sha256']
                or raw['usage'] != row['usage'] or raw['finish_reason'] != 'stop'):
            raise ValueError('Original raw/ledger mismatch')
        if case != 'geometry' or raw['role'] == 'initial':
            records.append(raw)
    revisions = list((run/'runtime/inputs').glob('*/revision.json'))
    if len(revisions) != 1:
        raise ValueError('One archived original input required')
    revision = read(revisions[0])
    images = []
    for image in revision['images']:
        content = (revisions[0].parent/(image['sha256']+'.bin')).read_bytes()
        if hashlib.sha256(content).hexdigest() != image['sha256']:
            raise ValueError('Original archived photo changed')
        images.append(ImageInput(image['name'], image['mime_type'], content))
    request = GenerationRequest(uuid4().hex, revision['prompt'], tuple(images),
        image_detail=revision['generation_settings']['image_detail'])
    observation = ObservationArtifact.from_mapping(json.loads(parse_chat_completion(
        json.loads(records[0]['response_redacted'])).content))
    candidates = [json.loads(parse_chat_completion(json.loads(r['response_redacted'])).content) for r in records]
    original_structure = deepcopy(candidates[1])
    structure = checked_structure(original_structure, request, observation, bound=True)
    draft = scene_draft(structure)
    for candidate in candidates[2:]:
        draft = checked_batch(candidate, draft, list(candidate))
    fault_index = -1 if case == 'geometry' else 1 if case == 'structure' else 2
    failed = deepcopy(draft if case == 'geometry' else candidates[fault_index])
    if case == 'geometry':
        target_id = None
        check = lambda: compile_scene(failed, observation, request)
    elif case == 'structure':
        target = next(row for row in failed['inventory'] if row['evidence_ref'].startswith('seen:'))
        target_id = target['id']
        target['kind'] = 'desk' if target['kind'] != 'desk' else 'bed'
        check = lambda: checked_structure(failed, request, observation, bound=True)
    else:
        target_id = next(iter(failed))
        failed[target_id]['dimensions_m'][0] = -1
        check = lambda: checked_batch(failed, scene_draft(structure), list(failed))
    try:
        check()
    except Exception as error:
        diagnosis = (compiler_diagnosis(error, failed, request) if case == 'geometry'
                     else getattr(error, 'contract_report', None))
        if not diagnosis:
            raise ValueError('Fault must produce a typed product validation diagnosis') from error
        if case == 'geometry':
            targets = [i for row in diagnosis['issues'] for i in row.get('target_ids', [])]
            if not targets or not all(row.get('repairable') for row in diagnosis['issues']):
                raise ValueError('Saved failure is not a repairable geometry candidate')
            target_id = targets[0]
    else:
        raise ValueError('Controlled fault was not detected')
    protected = {str(p): sha(p) for p in prior.rglob('*') if p.is_file()}
    protected.update(read(prior/'approval.json')['originals_at_start'])
    return dict(request=request, observation=observation, records=records, candidates=candidates,
        failed=failed, fault_index=fault_index, target_id=target_id, diagnosis=diagnosis,
        original_draft=draft, ledger=ledger, ledger_path=paths[0], protected=protected,
        input_settings=revision['generation_settings'])


class ReplayInitialLiveRepairs:
    """Explicit test fixture; genuine HTTP is possible ONLY in a repair role."""
    def __init__(self, ordinary, data, output):
        self.ordinary, self.data, self.output = ordinary, data, output
        self.index = 0
        self.replayed = set()
        self.fixture_evidence = InferenceEvidence(output/'replayed-context')

    async def complete(self, body, token, config):
        if token.generation_role == 'repair':
            if (body['model'] != NANO or has_image(body['messages']) or body['max_tokens'] != 20000
                    or body.get('response_format', {}).get('json_schema', {}).get('name') not in
                    {'twinpulse_semantic_structure', 'twinpulse_semantic_batch', 'twinpulse_semantic_patch'}):
                raise ValueError('Only the approved image-free Nemotron repair may dispatch')
            return await self.ordinary.complete(body, token, config)
        if token.generation_role != 'initial':
            raise ValueError('Unknown replay/repair role; no dispatch')
        index = self.index
        self.index += 1
        raw = self.data['records'][index]
        if body['model'] != raw['model_id']:
            raise ValueError('Replay stage changed; refuse unreviewed initial dispatch')
        response = json.loads(raw['response_redacted'])
        if index == self.data['fault_index']:
            response['choices'][0]['message']['content'] = json.dumps(self.data['failed'])
        identity = uuid4().hex
        self.replayed.add(identity)
        save(self.output/'replayed-context'/f'{identity}.json', dict(
            fixture=True, external_http=False, source_attempt_id=raw['attempt_id'],
            source_response_sha256=raw['stored_response_sha256'], injected=index == self.data['fault_index'],
            candidate=json.loads(response['choices'][0]['message']['content'])))
        return replace(parse_chat_completion(response), attempt_id=identity)

    def record_validation(self, stage, identity, record):
        if identity in self.replayed:
            self.fixture_evidence.validation(identity, stage, {**record,
                'fixture': True, 'external_http': False})
        else:
            self.ordinary.record_validation(stage, identity, record)


def accounting_source(prior, expected_approval=None):
    """A settled current grant, independent of the immutable replay source."""
    summary = read(prior/'summary.json')
    approval = read(prior/'approval.json')
    if not summary.get('originals_unchanged') or (expected_approval is not None
            and approval.get('approval') != expected_approval):
        raise ValueError('Current human approval/history binding changed')
    paths = list((prior/'run-1/runtime/ordinary-generation').glob('*.ledger.json'))
    if len(paths) != 1:
        raise ValueError('Exactly one current paid approval required')
    ledger = read(paths[0])
    audit = summary.get('ordinary_live_audit') or {}
    stop = ((summary.get('browser') or {}).get('terminal') or {}).get('conversation', {}).get('generation') or {}
    stop_code = (((stop.get('error') or {}).get('diagnostics') or {}).get('budget') or {}).get('stop_reason')
    if (ledger['max_requests'] != 10 or Decimal(ledger['limit_usd']) != 1
            or paths[0].with_suffix('.dispatch-lock').exists() or audit.get('locks_pending') != 0
            or audit.get('requests') != len(ledger['requests'])
            or len(audit.get('rows', [])) != len(ledger['requests'])
            or any(not r.get('raw_ledger_match') or not r.get('dispatch_sha_matches')
                or not r.get('validation_files') or r.get('finish_reason') != 'stop' for r in audit.get('rows', []))
            or any(not r.get('finished_at') or r['status'] != 'received' for r in ledger['requests'])
            or stop_code in {'PROVIDER_OUTPUT_TRUNCATED', 'REMOTE_OUTCOME_UNKNOWN', 'VALIDATION_EVIDENCE_FAILED'}):
        raise ValueError('Current grant is unsettled or has a campaign-wide protection stop')
    return dict(ledger=ledger, ledger_path=paths[0], approval=approval, summary=summary)


def with_remainder_history(budget, root):
    """Carry settled requests from this grant's earlier controlled cases, too."""
    if root is None:
        return budget
    root = root.resolve()
    scope, audit, previous = read(root/'scope.json'), read(root/'audit.json'), read(root/'campaign.json')
    base = budget['ledger']
    if (scope['prior_ledger_sha256'] != sha(budget['ledger_path'])
            or Path(scope['prior_ledger']).resolve() != budget['ledger_path'].resolve()
            or scope['approval'] != budget['approval']['approval']
            or previous['approval'] != scope['approval']
            or scope['prior_requests'] != len(base['requests'])
            or previous['max_requests'] != 10-len(base['requests'])
            or Decimal(previous['limit_usd']) + sum((Decimal(r['charged_or_reserved_usd'])
                for r in base['requests']), Decimal(0)) != 1
            or (root/'campaign.dispatch-lock').exists() or (root/'STOP.json').exists()):
        raise ValueError('Earlier remainder accounting does not belong to this settled grant')
    merged = deepcopy(base)
    merged['requests'].extend(previous['requests'])
    identities = {r['attempt_id'] for r in merged['requests']}
    used = sum((Decimal(r['charged_or_reserved_usd']) for r in merged['requests']), Decimal(0))
    if (len(identities) != len(merged['requests']) or len(identities) != audit['actual_model_calls']
            or audit['unknown_requests'] != 0 or audit['pending_locks'] != 0
            or used != Decimal(audit['estimated_usd']) or audit['unused_calls'] != 10-len(identities)):
        raise ValueError('Combined grant audit/count/cost mismatch')
    for row in previous['requests']:
        files = list(root.glob(f"*/evidence/{row['attempt_id']}.json"))
        if len(files) != 1 or row['status'] != 'received' or not row.get('finished_at'):
            raise ValueError('Earlier remainder request is unsettled or lacks evidence')
        raw = read(files[0]); evidence = files[0].parent
        dispatch = read(evidence/'dispatches'/files[0].name)
        if (raw['usage'] != row['usage'] or raw['finish_reason'] != 'stop'
                or raw['response_truncated'] or dispatch['request_truncated']
                or hashlib.sha256(raw['response_redacted'].encode()).hexdigest() != raw['stored_response_sha256']
                or hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest() != dispatch['stored_request_sha256']
                or raw['request_sha256'] != dispatch['request_sha256']
                or raw['schema_sha256'] != dispatch['schema_sha256']
                or raw['execution_id'] != dispatch['execution_id']
                or not list((evidence/'validations').glob(f"{row['attempt_id']}-*.json"))):
            raise ValueError('Earlier remainder raw/request/validation/ledger mismatch')
    for path in root.glob('*/result.json'):
        result = read(path)
        if not result['originals_unchanged'] or not all(Path(p).is_file() and sha(Path(p)) == digest
                for p,digest in result['protected_sha256'].items()):
            raise ValueError('Earlier immutable history changed')
    return {**budget, 'ledger':merged, 'remainder_root':root,
        'remainder_protected':{str(p):sha(p) for p in root.rglob('*') if p.is_file()}}


async def run(args, data):
    output = args.output.resolve()
    case_root = output/args.case
    if case_root.exists() or (output/'STOP.json').exists():
        raise ValueError('Do not silently repeat a case or a stopped campaign')
    budget_root = (getattr(args, 'accounting_prior', None) or args.prior).resolve()
    budget = with_remainder_history(accounting_source(budget_root, args.approval_text),
        getattr(args, 'accounting_remainder', None))
    if budget['approval']['photo_sha256'] != read(args.prior.resolve()/'approval.json')['photo_sha256']:
        raise ValueError('Current grant and replay source refer to different approved inputs')
    prior = budget['ledger']
    prior_path = budget['ledger_path']
    protected = {**data['protected'], **budget.get('remainder_protected', {}),
        **{str(p): sha(p) for p in budget_root.rglob('*') if p.is_file()}}
    count = len(prior['requests'])
    used = sum((Decimal(r['charged_or_reserved_usd']) for r in prior['requests']), Decimal(0))
    if not 0 < count < 10 or used >= 1:
        raise ValueError('No remainder in the CURRENT human approval')
    scope = dict(approval=args.approval_text, prior_ledger=str(prior_path),
        prior_ledger_sha256=sha(prior_path), prior_requests=count, prior_cost_usd=str(used),
        max_requests=10-count, limit_usd=str(Decimal('1')-used), rates=prior['rates'],
        image_upload=False, robot_commands=0, isaac_commands=0,
        test='controlled initial-context replay + production automatic scoped repair loop',
        not_natural_model_failure=args.case != 'geometry', stop_on=['length', 'outcome_unknown', 'evidence_failure'])
    if getattr(args, 'accounting_remainder', None):
        scope.update(earlier_remainder=str(args.accounting_remainder.resolve()),
            earlier_remainder_sha256=sha(args.accounting_remainder.resolve()/'campaign.json'))
    if getattr(args, 'accounting_prior', None):
        scope.update(accounting_source=str(budget_root), replay_source=str(args.prior.resolve()),
            replay_approval_sha256=sha(args.prior.resolve()/'approval.json'),
            natural_generation_status=budget['summary']['status'])
    if (output/'scope.json').exists():
        if read(output/'scope.json') != scope:
            raise ValueError('Remainder scope changed; no new budget')
    else:
        save(output/'scope.json', scope)
    ledger = CampaignLedger(output/'campaign.json', approval=args.approval_text, rates=prior['rates'],
        max_requests=scope['max_requests'], limit_usd=scope['limit_usd'])
    if ledger.lock_path.exists() or any(r['status'] == 'outcome_unknown' for r in ledger.state['requests']):
        raise ValueError('Unknown/pending remainder; do not dispatch')
    case_root.mkdir(parents=True)
    settings = JsonProviderSettingsStore(budget_root/'run-1/runtime/provider_settings.json')
    if not settings.path.is_file():
        # Locate metadata by original copied settings name, without reading keys.
        source_settings = JsonProviderSettingsStore()
        settings = JsonProviderSettingsStore(budget_root/'run-1/runtime'/source_settings.path.name)
    registry = KeyRegistry(settings, WindowsCredentialStore())
    service = build_configured_stage_service(registry, evidence_root=case_root/'evidence')
    provider = service._provider
    if provider.policy.max_requests != 10 or provider.planner_model_id != NANO:
        raise ValueError('Original reviewed production route changed')
    class Scope:
        approval_id = uuid4().hex
        cache_identity = approval_id
        def bind(self, request, policy, route_sha256):
            if (request.request_id != data['request'].request_id or input_digest(request) != input_digest(data['request'])
                    or policy.sha256 != provider.policy.sha256 or route_sha256 != provider.route_sha256
                    or sha(prior_path) != scope['prior_ledger_sha256']
                    or not all(Path(p).is_file() and sha(Path(p)) == digest
                        for p,digest in budget.get('remainder_protected', {}).items())):
                raise ValueError('Controlled test input/policy/prior accounting changed')
            return ledger
    request = replace(data['request'], inference_scope=Scope())
    provider._transport = ReplayInitialLiveRepairs(provider._transport, data, case_root)
    store = ExecutionStore(case_root/'diagnostics', 'controlled-scoped-recovery')
    trace = store.begin('controlled_semantic_recovery', component='provider')
    token = CancellationToken()
    token.diagnostics = trace
    start = len(ledger.state['requests'])
    result = dict(case=args.case, status='FAIL', execution_id=trace.execution_id,
        controlled_fault=args.case != 'geometry', natural_model_failure=args.case == 'geometry', initial_context_replayed=True,
        fault_target=data['target_id'], injected_candidate=data['failed'], injected_diagnosis=data['diagnosis'],
        photos_sent=0, robot_commands=0, isaac_commands=0)
    save(case_root/'plan.json', result)
    print(json.dumps(dict(case=args.case, status='RUNNING', execution_id=trace.execution_id)), flush=True)
    try:
        response = await provider.generate(request, token, service._config)
        checkpoint = provider.store.read('checkpoint', response.provenance['checkpoint_id'])
        final = checkpoint['draft']
        before = data['original_draft']
        if args.case == 'geometry':
            unchanged = final['inventory'] == before['inventory']
        elif args.case == 'structure':
            unchanged = final['inventory'] == before['inventory']
        else:
            unchanged = all(final['objects'][i] == v for i, v in before['objects'].items() if i != data['target_id'])
        validations = [json.loads(read(p)['record_redacted']) for p in
            (case_root/'evidence/validations').glob('*.json')]
        targeted = ([v for v in validations if v.get('validation') == 'passed'
                     and isinstance(v.get('candidate'),dict) and 'operations' in v['candidate']]
                    if args.case == 'geometry' else
                    [v for v in validations if (v.get('repair_context') or {}).get('mode') in
                    {'targeted_operations', 'targeted_keyed_changes'}])
        if not unchanged or not targeted or not any(v['validation'] == 'passed' for v in targeted):
            raise AssertionError('Scoped patch/current candidate/sibling preservation not verified')
        result.update(status='PASS', untouched_siblings_preserved=True, actual_scoped_patch_verified=True,
            checkpoint_id=response.provenance['checkpoint_id'], compiled_plan_sha256=canonical_sha256(response.payload),
            provenance=dict(response.provenance), compiled_ready=checkpoint['state'])
        if args.case == 'geometry':
            payload, provenance = compile_scene(final, data['observation'], request)
            save(case_root/'compiled-plan.json', payload)
            save(case_root/'final-candidate.json', final)
            result.update(before_revision=revision(before), after_revision=revision(final),
                geometry_before=data['diagnosis'], full_candidate_validation='passed',
                changed_ids=[i for i in before['objects'] if before['objects'][i] != final['objects'].get(i)],
                room_changed=before['room'] != final['room'],
                source_candidate_sha256=canonical_sha256(before), compiled_provenance=provenance,
                new_natural_generation='NOT_RUN_REPLAYED_INITIAL_CONTEXT')
    except Exception as error:
        result.update(error_type=type(error).__name__, error_code=getattr(error, 'code', None),
            error=str(error)[:1200])
    result['diagnostics'] = provider.diagnostic_for(request.request_id)
    result['new_paid_requests'] = len(ledger.state['requests'])-start
    result['replayed_contexts'] = provider._transport.index
    result['originals_unchanged'] = all(Path(p).is_file() and sha(Path(p)) == digest for p, digest in protected.items())
    result['protected_sha256'] = protected
    if not result['originals_unchanged']:
        result.update(status='FAIL', error='Original metadata/history changed')
    if (ledger.lock_path.exists() or any(r['status'] == 'outcome_unknown' for r in ledger.state['requests'])
            or result['diagnostics']['budget']['stop_reason'] in
                {'PROVIDER_OUTPUT_TRUNCATED', 'REMOTE_OUTCOME_UNKNOWN', 'VALIDATION_EVIDENCE_FAILED'}):
        save(output/'STOP.json', dict(reason='length_unknown_or_evidence', case=args.case, automatic_resume=False))
    trace.finish('succeeded' if result['status'] == 'PASS' else 'failed', error_code=result.get('error_code'))
    store.flush()
    result['diagnostics_health'] = store.health
    save(case_root/'result.json', result)
    print(json.dumps({k:result.get(k) for k in ('case', 'status', 'new_paid_requests', 'execution_id',
        'error_code', 'untouched_siblings_preserved', 'actual_scoped_patch_verified', 'originals_unchanged')}, ensure_ascii=False), flush=True)


def audit(prior, output):
    """Independent saved-evidence revalidation, never a model/network retry."""
    original = context(prior, 'structure')
    scope = read(output/'scope.json')
    budget_root = Path(scope.get('accounting_source', str(prior)))
    budget = accounting_source(budget_root, scope['approval'] if scope.get('accounting_source') else None)
    prior_ledger = budget['ledger']
    ledger = read(output/'campaign.json')
    used = sum((Decimal(r['charged_or_reserved_usd']) for r in prior_ledger['requests']), Decimal(0))
    assert scope['prior_ledger_sha256'] == sha(budget['ledger_path'])
    assert scope['prior_requests'] == len(prior_ledger['requests'])
    assert scope['max_requests'] + len(prior_ledger['requests']) == 10
    assert Decimal(scope['limit_usd']) + used == 1
    assert ledger['max_requests'] == scope['max_requests'] and ledger['limit_usd'] == scope['limit_usd']
    assert not (output/'campaign.dispatch-lock').exists()
    rows, keys = [], set()
    roots = [(budget_root/'run-1/runtime/provider-evidence', prior_ledger, 'natural_generation')]
    for case in ('structure', 'objects'):
        saved = read(output/case/'result.json')
        case_rows = [r for r in ledger['requests'] if (output/case/'evidence'/f"{r['attempt_id']}.json").is_file()]
        assert len(case_rows) == saved['new_paid_requests']
        roots.append((output/case/'evidence', {'requests': case_rows}, case))
    for root, accounting, case in roots:
        for row in accounting['requests']:
            identity = row['attempt_id']
            assert identity not in keys and row.get('finished_at') and row['status'] == 'received'
            keys.add(identity)
            raw = read(root/f'{identity}.json')
            dispatch = read(root/'dispatches'/f'{identity}.json')
            assert hashlib.sha256(raw['response_redacted'].encode()).hexdigest() == raw['stored_response_sha256']
            assert hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest() == dispatch['stored_request_sha256']
            assert raw['usage'] == row['usage'] and raw['model_id'] == row['model_id']
            assert raw['execution_id'] == dispatch['execution_id']
            assert raw['request_sha256'] == dispatch['request_sha256']
            assert raw['schema_sha256'] == dispatch['schema_sha256']
            assert not raw['response_truncated'] and not dispatch['request_truncated']
            assert raw['finish_reason'] == 'stop'
            wire = json.loads(dispatch['request_redacted'])
            validators = [read(p) for p in (root/'validations').glob(f'{identity}-*.json')]
            assert validators
            values = []
            for record in validators:
                assert record['execution_id'] == raw['execution_id'] and record['attempt_id'] == identity
                assert hashlib.sha256(record['record_redacted'].encode()).hexdigest() == record['stored_record_sha256']
                assert not record['record_truncated']
                values.append((record['stage'], json.loads(record['record_redacted'])))
            if case != 'natural_generation':
                assert raw['role'] == 'repair' and raw['model_id'] == NANO and raw['max_tokens'] == 20000
                assert not has_image(wire['messages'])
                data = context(prior, case)
                record = next(value for stage, value in values if stage == case)
                candidate = json.loads(parse_chat_completion(json.loads(raw['response_redacted'])).content)
                assert candidate == record['candidate']
                if case == 'structure':
                    if candidate.get('repair_version') == STRUCTURE_REPAIR_REVISION:
                        assert record['repair_context']['mode'] == 'targeted_keyed_changes'
                        applied = repair_structure(data['failed'], candidate, data['diagnosis'], data['request'], data['observation'])
                        assert applied == record['validation_candidate']
                        checked_structure(applied, data['request'], data['observation'], bound=True)
                        assert record['validation'] == 'passed'
                    else:
                        assert record['repair_context']['mode'] == 'targeted_operations'
                        try:
                            # Explicit audit of immutable historical failures only.
                            replay_legacy_structure_patch(data['failed'], candidate, data['diagnosis'], data['request'], data['observation'])
                        except Exception as error:
                            assert record['validation'] == 'failed'
                            assert getattr(error, 'contract_report') == record['diagnosis']
                        else:
                            raise AssertionError('Historical duplicate patch unexpectedly passed')
                else:
                    assert record['repair_context']['mode'] == 'targeted_operations'
                    draft = scene_draft(checked_structure(data['candidates'][1], data['request'], data['observation'], bound=True))
                    applied = repair_batch(data['failed'], candidate, draft, list(data['failed']))
                    assert applied == record['validation_candidate']
                    checked_batch(applied, draft, list(data['failed']))
                    assert record['validation'] == 'passed'
            rows.append(dict(case=case, attempt_id=identity, execution_id=raw['execution_id'],
                role=raw['role'], elapsed_s=raw['elapsed_s'], model_id=raw['model_id'],
                usage=raw['usage'], estimated_usd=row['charged_or_reserved_usd'],
                raw_request_validation_accounting_match=True))
    assert len(keys) == len(prior_ledger['requests']) + len(ledger['requests']) <= 10
    assert sum(r['case'] != 'natural_generation' for r in rows) == len(ledger['requests'])
    total = sum((Decimal(r['estimated_usd']) for r in rows), Decimal(0))
    assert total <= 1
    assert all(Path(p).is_file() and sha(Path(p)) == digest for p, digest in original['protected'].items())
    structure = read(output/'structure/result.json')
    objects = read(output/'objects/result.json')
    for saved in (structure, objects):
        assert saved['originals_unchanged']
        assert all(Path(p).is_file() and sha(Path(p)) == digest for p, digest in saved.get('protected_sha256', {}).items())
        if saved['status'] == 'PASS':
            assert saved['actual_scoped_patch_verified'] and saved['untouched_siblings_preserved']
    summary = dict(status='AUDIT_PASS_NOT_FULL_DEMO', actual_model_calls=len(rows), call_cap=10,
        unused_calls=10-len(rows), estimated_usd=str(total), invoice_verified=False,
        unknown_requests=0, pending_locks=0, new_photo_uploads_during_repairs=0,
        natural_generation=budget['summary']['status'], controlled_structure_repair=structure['status'],
        controlled_objects_repair=objects['status'], original_evidence_and_settings_unchanged=True,
        fresh_isaac='NOT_RUN', physical='NOT_RUN', new_audit_model_calls=0, rows=rows)
    save(output/'audit.json', summary)
    print(json.dumps({k:v for k,v in summary.items() if k != 'rows'}, ensure_ascii=False))


def audited_geometry(output):
    """Read-only, exact real patch/candidate/compile and whole-grant audit."""
    from twinpulse_provider.semantic_scene import patch_candidate
    output = Path(output).resolve()
    scope = read(output/'scope.json')
    prior_path = Path(scope['prior_ledger'])
    source = prior_path.parents[3]
    budget = with_remainder_history(accounting_source(source, scope['approval']),
        Path(scope['earlier_remainder']))
    data = context(source, 'geometry')
    result = read(output/'geometry/result.json')
    ledger = read(output/'campaign.json')
    if (result['status'] != 'PASS' or result['controlled_fault'] or not result['natural_model_failure']
            or not result['initial_context_replayed'] or scope['prior_requests'] != len(budget['ledger']['requests'])
            or scope['max_requests'] != 10-scope['prior_requests']
            or ledger['max_requests'] != scope['max_requests']
            or ledger['limit_usd'] != scope['limit_usd'] or ledger['approval'] != scope['approval']
            or sha(prior_path) != scope['prior_ledger_sha256']
            or sha(Path(scope['earlier_remainder'])/'campaign.json') != scope['earlier_remainder_sha256']
            or len(ledger['requests']) != result['new_paid_requests']
            or (output/'campaign.dispatch-lock').exists() or (output/'STOP.json').exists()
            or not all(Path(p).is_file() and sha(Path(p)) == digest
                for p,digest in result['protected_sha256'].items())):
        raise ValueError('Geometry recovery source/accounting/history binding failed')
    draft = deepcopy(data['failed'])
    identities = {r['attempt_id'] for r in budget['ledger']['requests']}
    rows=[]
    for row in ledger['requests']:
        identity=row['attempt_id']; root=output/'geometry/evidence'
        raw=read(root/(identity+'.json')); dispatch=read(root/'dispatches'/(identity+'.json'))
        if (identity in identities or row['status'] != 'received' or not row.get('finished_at')
                or raw['usage'] != row['usage'] or raw['model_id'] != NANO or raw['role'] != 'repair'
                or raw['finish_reason'] != 'stop' or raw['max_tokens'] != 20000
                or raw['response_truncated'] or dispatch['request_truncated']
                or hashlib.sha256(raw['response_redacted'].encode()).hexdigest() != raw['stored_response_sha256']
                or hashlib.sha256(dispatch['request_redacted'].encode()).hexdigest() != dispatch['stored_request_sha256']
                or raw['request_sha256'] != dispatch['request_sha256']
                or raw['schema_sha256'] != dispatch['schema_sha256']
                or raw['execution_id'] != result['execution_id'] or dispatch['execution_id'] != raw['execution_id']):
            raise ValueError('Geometry repair raw/dispatch/ledger mismatch')
        identities.add(identity)
        wire=json.loads(dispatch['request_redacted'])
        if has_image(wire['messages']):raise ValueError('Geometry repair may not upload a photo')
        body=json.loads(wire['messages'][-1]['content'].splitlines()[0])
        if body['candidate'] != draft or body['validation'] != compiler_diagnosis_for(draft,data):
            raise ValueError('Actual request lost the current geometry diagnosis')
        response=json.loads(parse_chat_completion(json.loads(raw['response_redacted'])).content)
        validations=list((root/'validations').glob(f'{identity}-*.json'))
        if not validations:raise ValueError('Missing geometry repair validation evidence')
        for path in validations:
            record=read(path)
            if (record['execution_id'] != raw['execution_id'] or record['record_truncated']
                    or hashlib.sha256(record['record_redacted'].encode()).hexdigest() != record['stored_record_sha256']):
                raise ValueError('Geometry validation changed')
        draft=patch_candidate(draft,response,data['observation'],data['request'])
        rows.append(dict(attempt_id=identity,execution_id=raw['execution_id'],elapsed_s=raw['elapsed_s'],
            model_id=NANO,role='repair',usage=row['usage'],estimated_usd=row['charged_or_reserved_usd'],
            raw_request_validation_accounting_match=True))
    payload,provenance=compile_scene(draft,data['observation'],data['request'])
    # The production pipeline sets this host-owned flag after full compile;
    # it is not model geometry and is deliberately excluded from revision().
    draft['state']='APPROXIMATE_TWIN_READY'
    if (draft != read(output/'geometry/final-candidate.json')
            or payload != read(output/'geometry/compiled-plan.json')
            or canonical_sha256(payload) != result['compiled_plan_sha256']):
        raise ValueError('Final saved geometry does not match actual model patch')
    used=sum((Decimal(r['charged_or_reserved_usd']) for r in
        budget['ledger']['requests']+ledger['requests']),Decimal(0))
    if len(identities)>10 or used>1:raise ValueError('Combined human grant exceeded')
    summary=dict(status='AUDIT_PASS_NOT_FULL_DEMO',actual_model_calls=len(identities),call_cap=10,
        unused_calls=10-len(identities),estimated_usd=str(used),invoice_verified=False,
        unknown_requests=0,pending_locks=0,new_photo_uploads=0,new_paid_calls=len(rows),
        natural_initial_context='SAVED_V379_FAILURE',actual_geometry_recovery='PASS',
        fresh_natural_generation='NOT_RUN',fresh_isaac='NOT_RUN',physical='NOT_RUN',
        before_revision=revision(data['failed']),after_revision=revision(draft),
        original_evidence_and_settings_unchanged=True,rows=rows)
    return data,payload,provenance,result,summary


def compiler_diagnosis_for(draft,data):
    try:compile_scene(draft,data['observation'],data['request'])
    except ValueError as error:return compiler_diagnosis(error,draft,data['request'])
    raise ValueError('A repair request must have a real failing candidate')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prior', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--case', choices=('structure', 'objects', 'geometry'))
    parser.add_argument('--approval-text', required=True)
    parser.add_argument('--accounting-prior', type=Path,
        help='Current settled ten-call grant; immutable successful replay context remains the positional prior')
    parser.add_argument('--accounting-remainder', type=Path,
        help='Already settled controlled calls from this SAME grant; deduct them as well')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    if args.audit_only:
        if args.live or args.case:
            parser.error('An offline audit cannot dispatch or choose a live case')
        if (args.output/'geometry/result.json').exists():
            *unused, summary=audited_geometry(args.output)
            save(args.output/'audit.json',summary)
            print(json.dumps(summary,ensure_ascii=False))
        else:
            audit(args.prior.resolve(), args.output.resolve())
        raise SystemExit(0)
    if not args.case:
        parser.error('--case is required for a dry/live recovery test')
    data = context(args.prior.resolve(), args.case)
    if args.live:
        asyncio.run(run(args, data))
    else:
        paid = with_remainder_history(accounting_source(
            (args.accounting_prior or args.prior).resolve(), args.approval_text), args.accounting_remainder)['ledger']
        print(json.dumps(dict(status='DRY_RUN_PASS', case=args.case, target=data['target_id'],
            diagnosis=data['diagnosis'], prior_paid=len(paid['requests']),
            remaining_paid_cap=10-len(paid['requests']), external_calls=0), ensure_ascii=False))
