# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded P01 real-model evaluation of the current product geometry gate.

--prepare-only never loads credentials or makes requests. Live evaluation needs
an explicit host-approved additional batch; the original ledger is never reset.
Natural trials and controlled negatives are separate. No robot or Isaac calls.
"""
import argparse
import asyncio
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))

from twinpulse_core.photo_quality import inspect_photo_geometry, reviewed_photo_constraints
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
from twinpulse_core.revisions import canonical_sha256
from twinpulse_provider import GenerationRequest, ImageInput, GenerationService
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider, ObservationArtifact
from twinpulse_provider.photo_layout import compile_layout
from twinpulse_provider.reliability import CampaignLedger, utc_now, safe_text
from scripts.replay_audited_inference import ExactAuditedResponses, live_run_inputs
from scripts.verify_photo_quality_loop import require_settled_dispatches
from scripts.verify_photo_geometry_gate import read_completion


def extend_approved_batch(path, *, expected_count, batch_id, approval, new_batch_cap=10, carry_unused_allowance=False):
    """Explicit human-authorized batch, same dollar cap/rates/prior requests.

    Not callable by model output. Immutable approval history makes repeats
    idempotent; no new campaign or refund for previous unknown outcomes.
    """
    if (not approval or not batch_id or type(expected_count) is not int or expected_count < 0
            or type(new_batch_cap) is not int or not 1 <= new_batch_cap <= 100
            or type(carry_unused_allowance) is not bool):
        raise ValueError('EXPLICIT_BATCH_APPROVAL_REQUIRED')
    saved = json.loads(path.read_text(encoding='utf-8'))
    ledger = CampaignLedger(path, approval=saved['approval'], rates=saved['rates'],
        limit_usd=saved['limit_usd'], max_requests=saved['max_requests'])
    descriptor = os.open(ledger.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descriptor)
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        history = state.setdefault('additional_batch_approvals', [])
        existing = [row for row in history if row['batch_id'] == batch_id]
        if existing:
            if (len(existing) != 1 or existing[0]['start_count'] != expected_count
                    or existing[0]['approval'] != approval or existing[0]['new_batch_cap'] != new_batch_cap
                    or ('carry_forward_remaining' in existing[0]) != carry_unused_allowance):
                raise ValueError('BATCH_APPROVAL_IDENTITY_CHANGED')
            return existing[0]
        if len(state['requests']) != expected_count or any(not r.get('finished_at') for r in state['requests']):
            raise ValueError('CAMPAIGN_CHANGED_OR_PENDING')
        if Decimal(state['limit_usd']) > Decimal('1.00'):
            raise ValueError('ORIGINAL_DOLLAR_LIMIT_MUST_NOT_INCREASE')
        carry = state['max_requests'] - expected_count if carry_unused_allowance else 0
        target = expected_count + carry + new_batch_cap
        if target <= state['max_requests']:
            raise ValueError('EXISTING_ALLOWANCE_SUFFICIENT_NO_EXTENSION')
        row = dict(batch_id=batch_id, approval=approval, approved_at=utc_now(),
            start_count=expected_count, new_batch_cap=new_batch_cap, old_max_requests=state['max_requests'],
            new_max_requests=target, unchanged_limit_usd=state['limit_usd'],
            prior_requests_sha256=canonical_sha256(state['requests']))
        if carry_unused_allowance:row['carry_forward_remaining']=carry
        history.append(row)
        state['max_requests'] = target
        ledger.state = state
        ledger._write()
        return row
    finally:
        ledger.lock_path.unlink(missing_ok=True)


def remaining_approved_allowance(path, *, expected_count, cap):
    """Read-only resume of an existing approval. Never extend/reset the ledger."""
    state = json.loads(path.read_text(encoding='utf-8'))
    if path.with_suffix('.dispatch-lock').exists() or any(not r.get('finished_at') for r in state['requests']):
        raise ValueError('CAMPAIGN_CHANGED_OR_PENDING')
    if (type(expected_count) is not int or len(state['requests']) != expected_count
            or type(cap) is not int or not 1 <= cap <= 5):
        raise ValueError('RESUME_COUNT_OR_CAP_INVALID')
    history = state.get('additional_batch_approvals', [])
    if (not history or state['max_requests'] != history[-1]['new_max_requests']
            or expected_count < history[-1]['start_count']
            or Decimal(state['limit_usd']) > Decimal('1.00')):
        raise ValueError('EXISTING_BATCH_APPROVAL_REQUIRED')
    remaining = min(cap, state['max_requests'] - expected_count)
    if remaining < 1:
        raise ValueError('EXISTING_BATCH_EXHAUSTED')
    return remaining


class ExactObserverTransport:
    """Reuse only the exact audited observation; all planner calls are fresh."""
    def __init__(self, real, campaign, evidence_root, observer_id):
        self.real = real
        self.observer = ExactAuditedResponses(campaign, evidence_root, [observer_id])

    async def complete(self, body, token, config):
        if body['response_format']['json_schema']['name'] == 'twinpulse_image_observation':
            return await self.observer.complete(body, token, config)
        return await self.real.complete(body, token, config)


class LimitedTransport:
    def __init__(self, real, allowance):
        if type(allowance) is not int or not 1 <= allowance <= 10:
            raise ValueError('BATCH_CAP_MUST_BE_1_TO_10')
        self.real, self.allowance = real, allowance

    async def complete(self, body, token, config):
        if len(self.real.calls) >= self.allowance:
            raise ValueError('NEW_BATCH_REQUEST_CAP_REACHED')
        return await self.real.complete(body, token, config)


class ControlledNegative:
    """Replay exact observer; inject one stored negative, pay for actual repair."""
    def __init__(self, real, campaign, evidence_root, observer_id, seed, content):
        self.real = real
        self.observer = ExactAuditedResponses(campaign, evidence_root, [observer_id])
        self.seed, self.content, self.injected = seed, content, False

    async def complete(self, body, token, config):
        if body['response_format']['json_schema']['name'] == 'twinpulse_image_observation':
            return await self.observer.complete(body, token, config)
        if not self.injected:
            self.injected = True
            return replace(self.seed, attempt_id=None, response_id='controlled-negative-NOT-fresh-model',
                content=json.dumps(self.content))
        if 'geometry_quality' not in json.loads(body['messages'][-1]['content']):
            raise ValueError('FULL_GEOMETRY_REPAIR_FEEDBACK_MISSING')
        return await self.real.complete(body, token, config)


def read_inputs(args):
    source = args.source_run.resolve()
    draft, evidence_root, ids = live_run_inputs(source)
    photo = args.photo.read_bytes()
    if hashlib.sha256(photo).hexdigest() != PHOTO_SHA256:
        raise ValueError('ONLY_APPROVED_P01_PHOTO_SUPPORTED')
    request = GenerationRequest('live-photo-geometry', draft.input_revision.prompt,
        (ImageInput(draft.input_revision.images[0]['name'], 'image/jpeg', photo),))
    saved = json.loads(args.campaign.read_text(encoding='utf-8'))
    if args.campaign.with_suffix('.dispatch-lock').exists() or any(not r.get('finished_at') for r in saved['requests']):
        raise ValueError('CAMPAIGN_PENDING_STOP_NO_RETRY')
    observer = ExactAuditedResponses(args.campaign, evidence_root, [ids[0]])
    seed = ExactAuditedResponses(args.campaign, evidence_root, [ids[1]]).entries[0][1]
    provider = NebiusChatCompletionsPipelineProvider(observer,
        observer_model_id=observer.entries[0][1].model_id, planner_model_id=seed.model_id,
        site_plan_version='2.2', max_repairs=1, compact_photo_layout=True)
    body = provider.build_observer_body(request)
    evidence = observer.entries[0][0]
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != evidence['request_sha256']:
        raise ValueError('OBSERVATION_REQUEST_CHANGED_NO_REUSE')
    old = ROOT / 'artifacts/agent-reliability-20261007/photo-quality-loop-r1'
    intent = read_completion(old / 'responses/a94679c2be7f460a8d5f842a3e78a5f3.json')
    observation = ObservationArtifact.from_mapping(json.loads(observer.entries[0][1].content))
    payload, quality = controlled_negative_preflight(intent, observation, request,
        enabled=not getattr(args,'natural_only',False))
    return request, source, evidence_root, ids, seed, intent, payload, quality, saved


def controlled_negative_preflight(intent, observation, request, *, enabled):
    # A natural-only trial cannot depend on an unrelated historical controlled
    # negative remaining valid after schema evolution. Never mutate that raw.
    if not enabled:return None,None
    payload, _ = compile_layout(intent, observation, request, photo_reference(PHOTO_SHA256),
        quality_constraints=reviewed_photo_constraints(PHOTO_SHA256))
    quality = inspect_photo_geometry(payload, PHOTO_SHA256)
    if quality['status'] != 'FAIL' or not quality['repairable']:
        raise ValueError('CONTROLLED_REPAIRABLE_NEGATIVE_NOT_REPRODUCED')
    return payload,quality


async def evaluate(args):
    from twinpulse_app import JsonProviderSettingsStore, WindowsCredentialStore
    from twinpulse_provider import ProviderConfig, ProviderCapabilities
    from twinpulse_provider.reliability import InferenceEvidence, AuditedChatTransport
    inputs = read_inputs(args)
    request, source, evidence_root, ids, seed, intent, payload, quality, saved = inputs
    resume = bool(args.resume_existing_batch)
    if args.controlled_only and (not resume or args.resume_cap != 1):
        raise ValueError('CONTROLLED_ONLY_REQUIRES_EXISTING_APPROVAL_AND_ONE_CALL_CAP')
    if args.controlled_only and args.natural_only:
        raise ValueError('CONTROLLED_AND_NATURAL_ONLY_ARE_EXCLUSIVE')
    allowance = remaining_approved_allowance(args.campaign, expected_count=args.expected_count,
        cap=args.resume_cap) if resume else 10
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'artifacts') or output.exists():
        raise ValueError('FRESH_OUTPUT_INSIDE_REPOSITORY_ARTIFACTS_REQUIRED')
    settings = JsonProviderSettingsStore(source / 'runtime/provider_settings.json').load().validated()
    if settings.model_id != seed.model_id:
        raise ValueError('CONFIGURED_MODEL_ID_CHANGED')
    # Use the configured provider's endpoint; do not send a stored secret elsewhere.
    config = ProviderConfig(base_url=settings.base_url, endpoint_path=settings.endpoint_path,
        model_id=settings.model_id, api_key_env='TWINPULSE_UNUSED_NEBIUS_KEY',
        capabilities=ProviderCapabilities(supports_images=True, supports_structured_output=True,
            max_images=1, accepted_mime_types=('image/jpeg',)), timeout_s=90., max_attempts=1)
    config.endpoint_url()
    output.mkdir(parents=True, exist_ok=False)
    source_names = [
        'packages/twinpulse_core/src/twinpulse_core/photo_quality.py',
        *['packages/twinpulse_provider/src/twinpulse_provider/' + n for n in
          ('photo_layout.py', 'nebius_pipeline.py', 'errors.py', 'service.py', 'reliability.py')],
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'packages/twinpulse_app/src/twinpulse_app/provider_composition.py',
        'scripts/verify_photo_geometry_live.py', 'scripts/summarize_photo_geometry_live.py']
    originals = [source / 'result.json', source / 'runtime/active_project.json',
        *evidence_root.glob('*.json'), *old_files()]
    reused_observer=None
    if args.reuse_observation_from:
        reused_run=args.reuse_observation_from.resolve()
        if not reused_run.is_relative_to(ROOT/'artifacts'):
            raise ValueError('AUDITED_OBSERVER_RUN_MUST_BE_INSIDE_ARTIFACTS')
        prior=json.loads((reused_run/'result.json').read_text(encoding='utf-8'))
        if prior['status']!='COMPLETED_BOUNDED_EVALUATION_NOT_FULL_DEMO':
            raise ValueError('COMPLETED_OBSERVER_RUN_REQUIRED')
        fresh=[a for j in prior['jobs'] if not j.get('cached_exact_observer')
            for a in j['diagnostics']['attempts'] if a['stage']=='observer' and a.get('validation')=='passed'
            and a.get('attempt_id') in prior['new_attempt_ids']]
        if len(fresh)!=1:
            raise ValueError('ONE_FRESH_AUDITED_OBSERVER_REQUIRED')
        reused_observer=(reused_run/'responses',fresh[0]['attempt_id'])
        preflight=ExactAuditedResponses(args.campaign,reused_observer[0],[reused_observer[1]])
        checker=NebiusChatCompletionsPipelineProvider(preflight,observer_model_id=settings.observer_model_id,
            planner_model_id=settings.model_id,site_plan_version='2.2',compact_photo_layout=True,
            output_token_cap=getattr(args,'output_token_cap',None))
        expected=hashlib.sha256(json.dumps(checker.build_observer_body(request),sort_keys=True).encode()).hexdigest()
        if expected!=preflight.entries[0][0]['request_sha256']:
            raise ValueError('EXACT_REUSED_OBSERVER_REQUEST_CHANGED_NO_DISPATCH')
        originals += [reused_run/'result.json',*reused_run.glob('responses/*.json')]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(status='PREPARED_NOT_RUN', new_call_cap=allowance, original_request_count=len(saved['requests']),
        original_max_requests=saved['max_requests'], limit_usd=saved['limit_usd'],
        observer_reuse_preflight='EXACT_ORIGINAL_REQUEST_HASH_VERIFIED', controlled_negative=quality,
        product_quality_gate_implemented=True, metric_scale_validation='UNVERIFIED_NO_MEASUREMENTS',
        physical_validation='NOT_RUN', isaac='NOT_RUN', whole_demo_ready=False, jobs=[],
        source_hashes={p: sha(ROOT / p) for p in source_names},
        original_hashes={str(p.relative_to(ROOT)): sha(p) for p in originals}, started_at=utc_now())
    report.update(resume_existing_approval=resume,
        output_token_cap=getattr(args,'output_token_cap',None),
        planner_template_no_thinking=resume and args.template_policy=='off', quality_gate_unchanged=True,
        controlled_only=args.controlled_only, reviewed_position_schema=True)
    report['reused_observer_attempt_id']=reused_observer[1] if reused_observer else None
    def save():
        (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    if args.prepare_only:
        print('PREPARED_NO_CREDENTIAL_ACCESS_NO_NETWORK', flush=True)
        return
    if not resume and not args.approval_ref:
        raise ValueError('EXPLICIT_ADDITIONAL_BATCH_APPROVAL_REQUIRED_NO_DISPATCH')
    start_count = len(saved['requests'])
    if resume:
        report['batch_approval'] = saved['additional_batch_approvals'][-1]
    else:
        report['batch_approval'] = extend_approved_batch(args.campaign, expected_count=start_count,
            batch_id=output.name, approval=args.approval_ref)
    state = json.loads(args.campaign.read_text(encoding='utf-8'))
    ledger = CampaignLedger.open_existing_approved(args.campaign,run_request_cap=allowance) if resume else CampaignLedger(
        args.campaign, approval=state['approval'], rates=state['rates'],
        limit_usd=state['limit_usd'], max_requests=state['max_requests'])
    real = AuditedChatTransport(WindowsCredentialStore(settings.credential_ref).load,
        InferenceEvidence(output / 'responses'), ledger)
    limited = LimitedTransport(real, allowance)
    report['status'] = 'RUNNING_BOUNDED_EVALUATION'
    save()
    async def job(name, transport, *, compact, controlled=False, cached_observer=False):
        provider = NebiusChatCompletionsPipelineProvider(transport, observer_model_id=settings.observer_model_id,
            planner_model_id=settings.model_id, site_plan_version='2.2', max_repairs=1,
            compact_photo_layout=compact, planner_template_no_thinking=resume and args.template_policy=='off',
            output_token_cap=getattr(args,'output_token_cap',None))
        item = dict(name=name, status='FAIL', initial_candidate='CONTROLLED_STORED_NEGATIVE' if controlled else 'FRESH_MODEL',
            count_in_natural_success_rate=not controlled, cached_exact_observer=cached_observer)
        begin = len(real.calls)
        started = time.monotonic()
        try:
            result = await GenerationService(provider, config, plan_version='2.2').generate(replace(request, request_id=name))
            checked = inspect_photo_geometry(result.plan.to_dict(), PHOTO_SHA256)
            if checked['checked_relation_status'] != 'PASS' or checked['status'] != 'PARTIAL':
                raise AssertionError('PRODUCT_ACCEPTED_INVALID_OR_UNVERIFIED_GEOMETRY')
            item.update(status='CHECKED_RELATIONS_PASS_FULL_FIDELITY_PARTIAL', quality=checked,
                provenance=result.provider_provenance, plan_sha256=canonical_sha256(result.plan.to_dict()))
            (output / (name + '-plan.json')).write_text(json.dumps(result.plan.to_dict(), indent=2), encoding='utf-8')
        except Exception as error:
            item.update(error_type=type(error).__name__, error=safe_text(str(error), limit=1200))
        item.update(diagnostics=provider.diagnostic_for(name), elapsed_s=round(time.monotonic()-started, 3),
            new_attempt_ids=real.calls[begin:])
        report['jobs'].append(item)
        save()
        print(name + ': ' + item['status'], flush=True)
        require_settled_dispatches(ledger, item['new_attempt_ids'])
        if item.get('error_type') in {'ProviderTimeoutError', 'TimeoutError', 'GenerationCancelledError',
                                     'ProviderAuthenticationError', 'ProviderRateLimitError', 'ProviderRequestError'}:
            raise ValueError('TRANSPORT_FAILURE_STOP_NO_RETRY')
        return item
    try:
        if args.controlled_only:
            await job('controlled_reviewed_schema_actual_quality_repair', ControlledNegative(limited,
                args.campaign, evidence_root, ids[0], seed, intent), compact=True, controlled=True)
        else:
            if reused_observer:
                first=await job('fresh_planner_same_audited_observer',ExactObserverTransport(limited,
                    args.campaign,*reused_observer),compact=True,cached_observer=True)
            else:
                first = await job('natural_full_pipeline_1', limited, compact=True)
        # At most one independent replication; not ten copies of the same failed call.
        if args.controlled_only:
            pass
        elif resume:
            if first['status'] != 'FAIL' and allowance-len(real.calls) >= 2 and not getattr(args,'output_token_cap',None):
                await job('natural_planner_exact_observer_replication', ExactObserverTransport(limited,
                    args.campaign, evidence_root, ids[0]), compact=True, cached_observer=True)
            elif not args.natural_only and first['status'] == 'FAIL' and allowance-len(real.calls) >= 1:
                await job('controlled_compact_actual_quality_repair', ControlledNegative(limited,
                    args.campaign, evidence_root, ids[0], seed, intent), compact=True, controlled=True)
        else:
            if first['status'] != 'FAIL':
                await job('natural_full_pipeline_2', limited, compact=True)
            await job('controlled_compact_actual_quality_repair', ControlledNegative(limited,
                args.campaign, evidence_root, ids[0], seed, intent), compact=True, controlled=True)
            negative = json.loads((ROOT / 'artifacts/agent-reliability-20261007/photo-quality-loop-r1/saved_actual_negative-plan.json').read_text(encoding='utf-8'))
            await job('controlled_default_actual_quality_repair', ControlledNegative(limited,
                args.campaign, evidence_root, ids[0], seed, negative), compact=False, controlled=True)
        report['status'] = 'COMPLETED_BOUNDED_EVALUATION_NOT_FULL_DEMO'
    except Exception as error:
        report.update(status='STOPPED_WITH_DIAGNOSTICS', error_type=type(error).__name__, error=safe_text(str(error), limit=1200))
    finally:
        until = time.monotonic() + 95
        while ledger.lock_path.exists() and time.monotonic() < until:
            await asyncio.sleep(.5)
        end = json.loads(args.campaign.read_text(encoding='utf-8'))
        report.update(finished_at=utc_now(), new_calls=len(end['requests'])-start_count,
            new_attempt_ids=real.calls, request_count=len(end['requests']), max_requests=end['max_requests'],
            prior_requests_unchanged=end['requests'][:start_count] == saved['requests'],
            source_unchanged=all(sha(ROOT / p) == h for p, h in report['source_hashes'].items()),
            originals_unchanged=all(sha(ROOT / p) == h for p, h in report['original_hashes'].items()),
            new_estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in end['requests'][start_count:]), Decimal(0))),
            total_estimated_or_reserved_usd=str(sum((Decimal(r['charged_or_reserved_usd']) for r in end['requests']), Decimal(0))),
            pending_dispatches=sum(not r.get('finished_at') for r in end['requests']), invoice_verified=False)
        save()
        print('PHOTO_GEOMETRY_LIVE=' + report['status'], flush=True)


def old_files():
    root = ROOT / 'artifacts/agent-reliability-20261007/photo-quality-loop-r1'
    previous = ROOT / 'artifacts/agent-reliability-20261007/photo-geometry-live-r1'
    wire_trial = ROOT / 'artifacts/agent-reliability-20261007/photo-geometry-live-r2'
    more=[p for name in ('photo-geometry-live-r3','photo-geometry-live-r4','photo-geometry-live-r5','photo-geometry-live-r6',
                         'photo-geometry-live-r7','photo-geometry-live-r8','photo-geometry-live-r9','photo-geometry-live-r10',
                         'photo-geometry-chat-isaac-r1')
        for root in [ROOT/'artifacts/agent-reliability-20261007'/name]
        for p in [*root.glob('*.json'),*root.glob('responses/*.json')]]
    return [*root.glob('*.json'), *root.glob('responses/*.json'),
        *previous.glob('*.json'), *previous.glob('responses/*.json'),
        *wire_trial.glob('*.json'), *wire_trial.glob('responses/*.json'),*more]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--photo', type=Path, required=True)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--approval-ref')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--resume-existing-batch', action='store_true')
    parser.add_argument('--expected-count', type=int, default=64)
    parser.add_argument('--resume-cap', type=int, default=5)
    parser.add_argument('--controlled-only', action='store_true')
    parser.add_argument('--authorize-only', action='store_true')
    parser.add_argument('--new-batch-cap', type=int, default=10)
    parser.add_argument('--carry-unused-allowance', action='store_true')
    parser.add_argument('--output-token-cap',type=int)
    parser.add_argument('--template-policy', choices=('off','default'), default='off')
    parser.add_argument('--natural-only', action='store_true')
    parser.add_argument('--reuse-observation-from', type=Path)
    arguments=parser.parse_args()
    if arguments.output_token_cap is not None and (not arguments.resume_existing_batch or
            not arguments.natural_only or not 1 <= arguments.output_token_cap <= 10000):
        parser.error('Output token override requires an existing approved natural-only batch and cap 1..10000')
    if arguments.authorize_only:
        receipt=extend_approved_batch(arguments.campaign,expected_count=arguments.expected_count,
            batch_id=arguments.output.name,approval=arguments.approval_ref,new_batch_cap=arguments.new_batch_cap,
            carry_unused_allowance=arguments.carry_unused_allowance)
        print(json.dumps(dict(authorization_recorded=True,new_batch_cap=receipt['new_batch_cap'],
            max_requests=receipt['new_max_requests'],unchanged_limit_usd=receipt['unchanged_limit_usd'])))
    else:
        asyncio.run(evaluate(arguments))
