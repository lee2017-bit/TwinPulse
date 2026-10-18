# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit one-call diagnostics; no App, Isaac, robot, automatic retry or fallback.

Reuses a saved, sanitized semantic request (no image bytes). All calls use the
existing audited HTTP transport and registered credentials. Never changes the
product route/settings. Host validators remain the ORIGINAL strict validators.
"""
from __future__ import annotations
import argparse
import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_core.execution_diagnostics import ExecutionStore
from twinpulse_provider.contracts import CancellationToken, GenerationRequest, ProviderConfig, ProviderCapabilities
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.reliability import InferenceEvidence, AuditedChatTransport, CampaignLedger, utc_now
from twinpulse_provider.semantic_scene import _shape_issues, checked_structure, inventory_requirements
from twinpulse_provider.stage_transport import OPENAI_MINI_SNAPSHOT, openai_observer_body, has_image
from scripts.prepare_split_evaluation import nebius_rate

NANO = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'
PREVIOUS = ROOT/'outputs/staged-repair-live-20261009-ten/run-1/runtime'
ORIGINAL = PREVIOUS/'provider-evidence/dispatches/6bf7268a7b3544448031588531bb9fcf.json'
PRIOR_LEDGER = PREVIOUS/'ordinary-generation/cc6bfb72-a45e-4b76-bd74-a3782e82f200.ledger.json'
OUT = ROOT/'outputs/model-schema-diagnosis-20261009'
CASES = ('gpt_original', 'nano_intent', 'nano_flat', 'nano_normalized',
         'gpt_repair_common', 'nano_repair_common', 'nano_visual_first', 'nano_schema_in_prompt')
APPROVAL = ('2026-10-09 user: diagnose whose failure; use GPT for validation if necessary; '
            'review hackathon alternatives. At most 10 including prior 2, total USD1 retained; '
            'no new photo upload, no Isaac/robot; stop on length/unknown.')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)

def load_original():
    wire = json.loads(json.loads(ORIGINAL.read_text(encoding='utf-8'))['request_redacted'])
    assert wire['model'] == NANO and wire['max_tokens'] == 20000 and not has_image(wire['messages'])
    assert wire['chat_template_kwargs']['enable_thinking'] is False
    payload = json.loads(wire['messages'][1]['content'])
    observation = ObservationArtifact.from_mapping(payload['observations'])
    request = GenerationRequest('schema-diagnosis', payload['user_request'])
    return wire, observation, request

def intent_body():
    # Synthetic non-actuating role probe, not physical robot telemetry/evidence.
    rows = [
        {'id': 'a', 'text': '책상 앞으로 가는 경로만 미리 보여줘. 실제 로봇은 아직 움직이지 마.'},
        {'id': 'b', 'text': '거기로 갔다가 원래 위치로 돌아오는 왕복 작업을 제안해 줘.'},
        {'id': 'c', 'text': '멈춰.'},
    ]
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['requests'], 'properties': {
        'requests': {'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['id', 'intent', 'target', 'execution_authorized'], 'properties': {
                'id': {'type': 'string', 'enum': ['a', 'b', 'c']},
                'intent': {'type': 'string', 'enum': ['preview_route', 'propose_loop', 'stop', 'clarify']},
                'target': {'type': ['string', 'null'], 'enum': ['desk', 'previous_goal', None]},
                'execution_authorized': {'type': 'boolean', 'enum': [False]}}}}}}
    return {'model': NANO, 'max_tokens': 20000, 'temperature': 0,
        'chat_template_kwargs': {'enable_thinking': False},
        'messages': [{'role': 'system', 'content': 'Classify these three independent requests as JSON. '
            'You have no tools and no authority to execute. Return one classification per input id. '
            'A preview is not a drive command. previous_goal is available in the conversation context. '
            'All execution_authorized fields must be false; a deterministic host owns execution and safety.'},
            {'role': 'user', 'content': json.dumps(rows, ensure_ascii=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'twinpulse_non_actuating_intent_probe', 'strict': True, 'schema': schema}}}

def build_case(case):
    original, observation, request = load_original()
    body = deepcopy(original)
    if case in ('gpt_original', 'gpt_repair_common'):
        body.pop('chat_template_kwargs')
        body['model'] = OPENAI_MINI_SNAPSHOT
        body = openai_observer_body(body, reasoning_effort='low')
    elif case == 'nano_flat':
        source = body['response_format']['json_schema']['schema']['properties']['inventory']['items']['properties']['source']
        ids = source['anyOf'][1]['properties']['observation_ids']['items']['enum']
        source.clear()
        source.update(type='object', additionalProperties=False,
            required=['basis', 'observation_ids', 'user_quote'], properties={
                'basis': {'type': 'string', 'enum': ['user', 'visual', 'inferred']},
                'observation_ids': {'type': 'array', 'minItems': 0, 'maxItems': 3,
                                    'items': {'type': 'string', 'enum': ids}},
                'user_quote': {'type': ['string', 'null'], 'minLength': 1, 'maxLength': 256}})
    elif case in ('nano_normalized', 'nano_repair_common', 'nano_visual_first', 'nano_schema_in_prompt'):
        temp = deepcopy(original)
        temp.pop('chat_template_kwargs')
        body['response_format'] = openai_observer_body(temp)['response_format']
        if case.startswith('nano_visual_first'):
            variants = body['response_format']['json_schema']['schema']['properties']['inventory']['items']['properties']['source']['anyOf']
            assert [v['properties']['basis']['enum'] for v in variants] == [['user'], ['visual'], ['inferred']]
            variants[:] = [variants[1], variants[2], variants[0]]
    elif case == 'nano_intent':
        body = intent_body()
    else:
        raise ValueError('Unknown diagnostic case')
    assert not has_image(body['messages']) and (body.get('max_tokens') or body.get('max_completion_tokens')) == 20000
    if case != 'nano_intent':
        assert body['messages'] == original['messages']
    if case == 'nano_schema_in_prompt':
        # General contract visibility experiment; no photo-specific target,
        # known-good answer, inventory, pose, dimensions or hand repair injected.
        body['messages'][0]['content'] += '\nThe response JSON Schema is:\n'+json.dumps(
            body['response_format']['json_schema']['schema'], separators=(',', ':'))
    if case.endswith('_repair_common'):
        from twinpulse_provider.generation_policy import diagnostic_blockers
        from twinpulse_provider.nebius_pipeline import _validation_code
        parent = json.loads((OUT/'nano_normalized/result.json').read_text(encoding='utf-8'))
        candidate = parent['candidate']
        try:
            checked_structure(candidate, request, observation)
        except Exception as error:
            diagnosis = getattr(error, 'contract_report', {})
            if not diagnosis:
                raise ValueError('Repair comparison requires exact parsed contract failure') from error
            code = _validation_code(error)
            # Same feedback serialization/append as BudgetedPipeline.content_stage.
            feedback = json.dumps({'correct_stage': 'structure', 'previous_candidate': candidate,
                'previous_attempt_id': parent['attempt_id'], 'validation': diagnosis,
                'remaining_targets': diagnostic_blockers(diagnosis, code), 'error_code': code,
                'instruction': 'Return only this corrected stage contract. Fix all listed errors. '
                    'Do not omit visible objects, invent measurements, execute tools or change provider.'})
            body['messages'][-1]['content'] += '\n'+feedback
        else:
            raise ValueError('No contract failure to compare')
    return body, original, observation, request

class DiagnosticLedger(CampaignLedger):
    def reserve(self, body):
        # Only accounting translates the OpenAI output-limit field. Actual wire
        # evidence remains untouched; full-context conservative reserve retained.
        accounting = deepcopy(body)
        if accounting['model'] == OPENAI_MINI_SNAPSHOT:
            accounting['max_tokens'] = accounting.pop('max_completion_tokens')
        if accounting['model'] not in (OPENAI_MINI_SNAPSHOT, NANO):
            raise ValueError('Unapproved diagnostic model')
        return super().reserve(accounting)

def prepare():
    if (OUT/'STOP.json').exists():
        raise ValueError('A length/unknown failure stopped this diagnostic campaign; do not dispatch')
    registry = KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore())
    rows = registry.state()['entries']
    selected = {}
    for name, model, profiles in [('gpt', 'gpt-5.4-mini', {'openai'}),
                                  ('nano', NANO, {'nebius_token_factory', 'nebius_site_v2'})]:
        matches = [r for r in rows if r['model_id'] == model and r['provider_profile'] in profiles]
        if len(matches) != 1:
            raise ValueError('Existing credential registration is ambiguous/missing')
        selected[name] = registry.settings_for_entry(matches[0]['id'])
        if not registry.resolve(selected[name]).is_configured():
            raise ValueError('Existing credential unavailable')
    prior = json.loads(PRIOR_LEDGER.read_text(encoding='utf-8'))
    prior_hash = hashlib.sha256(PRIOR_LEDGER.read_bytes()).hexdigest()
    if (len(prior['requests']) != 2 or PRIOR_LEDGER.with_suffix('.dispatch-lock').exists()
            or any(not r.get('finished_at') or r.get('status') == 'outcome_unknown' for r in prior['requests'])):
        raise ValueError('Prior approval accounting changed or has unresolved requests')
    used = sum((Decimal(r['charged_or_reserved_usd']) for r in prior['requests']), Decimal(0))
    scope_path = OUT/'scope.json'
    if scope_path.exists():
        scope = json.loads(scope_path.read_text(encoding='utf-8'))
        if (scope['prior_ledger_sha256'] != prior_hash
                or scope['source_sha256'] != hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()):
            raise ValueError('Prior evidence changed')
    else:
        rates = {OPENAI_MINI_SNAPSHOT: dict(input_per_million='0.75', output_per_million='4.50',
            context_tokens=400000, source='https://developers.openai.com/api/docs/models/gpt-5.4-mini',
            verified_at=utc_now()), NANO: nebius_rate(registry, selected['nano'])}
        scope = dict(approval=APPROVAL, prior_ledger=str(PRIOR_LEDGER), prior_ledger_sha256=prior_hash,
            prior_requests=2, prior_cost_usd=str(used), max_requests=8, limit_usd=str(Decimal('1')-used),
            rates=rates, source_request=str(ORIGINAL), source_sha256=hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),
            plan=['GPT original semantic schema with official wire adapter',
                  'Nano synthetic non-actuating intent role probe',
                  'Nano original messages with source.anyOf flattened only',
                  'Optional Nano original schema const/type normalization only'],
            stop_on=['finish_reason=length', 'outcome_unknown', 'unsettled evidence'],
            image_upload=False, robot=False, isaac=False, product_changes=False)
        save(scope_path, scope)
    ledger = DiagnosticLedger(OUT/'campaign.json', approval=APPROVAL, rates=scope['rates'],
        limit_usd=scope['limit_usd'], max_requests=8)
    if ledger.lock_path.exists() or any(r['status'] == 'outcome_unknown' for r in ledger.state['requests']):
        raise ValueError('Diagnostic campaign has unknown/pending dispatch')
    return registry, selected, ledger

def validate(case, value, wire, original, observation, request):
    wire_issues = _shape_issues(value, wire['response_format']['json_schema']['schema'])
    if case == 'nano_intent':
        expected = [('a', 'preview_route', 'desk', False), ('b', 'propose_loop', 'previous_goal', False),
                    ('c', 'stop', None, False)]
        got = [(r.get('id'), r.get('intent'), r.get('target'), r.get('execution_authorized'))
               for r in value.get('requests', [])] if isinstance(value, dict) else []
        return dict(wire_issues=wire_issues, expected=expected, actual=got, role_probe_pass=not wire_issues and got == expected,
                    synthetic=True, integration_pass=False, physical_authority=False)
    original_issues = _shape_issues(value, original['response_format']['json_schema']['schema'])
    host_issues = []
    try:
        checked_structure(value, request, observation)
    except Exception as error:
        host_issues = getattr(error, 'contract_report', {'error_type': type(error).__name__})
    required = {r['observation_id']: r['category'] for r in inventory_requirements(observation)}
    bindings = []
    if isinstance(value, dict):
        for item in value.get('inventory', []):
            bindings.append(dict(id=item.get('id'), kind=item.get('kind'), source=item.get('source')))
    mismatched_refs = []
    coverage = set()
    for item in bindings:
        for ref in (item['source'] or {}).get('observation_ids', []):
            if ref in required:
                if required[ref] == item['kind']:
                    coverage.add(ref)
                else:
                    mismatched_refs.append({'item': item['id'], 'observation_id': ref, 'category': required[ref], 'kind': item['kind']})
    return dict(wire_issues=wire_issues, original_shape_issues=original_issues, host_issues=host_issues,
        host_pass=not wire_issues and not original_issues and not host_issues, inventory_bindings=bindings,
        required_inventory=required, missing_category_coverage=sorted(set(required)-coverage),
        mismatched_category_refs=mismatched_refs, full_scene_pass=False, measured_size=False)

async def run(case):
    target = OUT/case
    if target.exists():
        raise ValueError('Case already exists; diagnostic runner never silently repeats a call')
    wire, original, observation, request = build_case(case)
    registry, settings, ledger = prepare()
    target.mkdir()
    store = ExecutionStore(OUT/'diagnostics', 'model-schema-diagnosis')
    trace = store.begin('model_schema_comparison', component='provider')
    token = CancellationToken()
    token.diagnostics = trace
    token.generation_role = 'diagnostic'
    owner = 'gpt' if case.startswith('gpt_') else 'nano'
    config = ProviderConfig('https://api.openai.com/v1/' if owner == 'gpt' else 'https://api.tokenfactory.nebius.com/v1/',
        'chat/completions', wire['model'], 'EXISTING_REGISTERED_CREDENTIAL', ProviderCapabilities(False, True), timeout_s=300)
    transport = AuditedChatTransport(registry.resolve(settings[owner]).load, InferenceEvidence(target/'evidence'), ledger)
    result = dict(case=case, execution_id=trace.execution_id, model=wire['model'],
        messages_sha256=digest(wire['messages']), original_messages_sha256=digest(original['messages']),
        same_messages=wire['messages']==original['messages'], timeout_s=300, max_output_tokens=20000,
        original_request_sha256=digest(original), wire_schema_sha256=digest(wire['response_format']),
        photos_sent=0, robot_commands=0, isaac_commands=0)
    save(target/'plan.json', result)
    print(json.dumps(dict(case=case, status='dispatching', execution_id=trace.execution_id)), flush=True)
    try:
        completion = await transport.complete(wire, token, config)
        result['attempt_id'] = completion.attempt_id
        value = json.loads(completion.content)
        result['validation'] = validate(case, value, wire, original, observation, request)
        result['candidate'] = value
        transport.record_validation(case, completion.attempt_id, result['validation'])
        result['status'] = 'received_and_validated'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error_code=getattr(error, 'code', None))
        if transport.calls:
            result['attempt_id'] = transport.calls[-1]
            transport.record_validation(case, transport.calls[-1], {k:result[k] for k in ('status','error_type','error_code')})
    if result.get('attempt_id'):
        saved = json.loads((target/'evidence'/f"{result['attempt_id']}.json").read_text(encoding='utf-8'))
        raw = json.loads(saved['response_redacted']) if saved.get('response_redacted') else {}
        choice = (raw.get('choices') or [{}])[0]
        content = (choice.get('message') or {}).get('content') or ''
        result.update(elapsed_s=saved['elapsed_s'], finish_reason=choice.get('finish_reason'),
            usage=saved.get('usage'), evidence_status=saved['status'], content_chars=len(content),
            trailing_whitespace_chars=len(content)-len(content.rstrip()), raw_truncated=saved.get('response_truncated', False))
        row = next(r for r in ledger.state['requests'] if r['attempt_id']==result['attempt_id'])
        result['estimated_usd'] = row['charged_or_reserved_usd']
    stop = result.get('finish_reason') == 'length' or result.get('evidence_status') == 'outcome_unknown' or ledger.lock_path.exists()
    if stop:
        save(OUT/'STOP.json', dict(case=case, attempt_id=result.get('attempt_id'), reason='length_or_unknown', automatic_resume=False))
    validation = result.get('validation', {})
    result['acceptance_pass'] = validation.get('host_pass', validation.get('role_probe_pass', False))
    trace.finish('succeeded' if result['acceptance_pass'] else 'failed',
                 error_code=None if result['acceptance_pass'] else 'diagnostic_acceptance_failed')
    store.flush()
    result['diagnostics_health'] = store.health
    save(target/'result.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('candidate','validation')}, ensure_ascii=False), flush=True)
    validation = result.get('validation', {})
    print(json.dumps({k:v for k,v in validation.items() if k not in
        ('inventory_bindings', 'required_inventory', 'mismatched_category_refs')}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--live', action='store_true', help='Explicitly dispatch one approved paid comparison call')
    args = parser.parse_args()
    if args.live:
        asyncio.run(run(args.case))
    else:
        body, original, observation, request = build_case(args.case)
        print(json.dumps(dict(case=args.case, status='DRY_RUN_ONLY', model=body['model'],
            has_images=has_image(body['messages']), same_messages=body['messages']==original['messages'],
            schema_sha256=digest(body['response_format'])), ensure_ascii=False))
