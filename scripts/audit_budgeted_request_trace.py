# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Reconstruct failed requests from saved responses, with networking disabled.

Diagnostic replay only: never model quality acceptance, a paid retry, a product
fallback, or an edit to the original evidence. Output is a separate audit file.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))

from twinpulse_provider import GenerationRequest
from twinpulse_provider.contracts import CancellationToken, ImageInput
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy, ExecutionBudget, ProgressTracker
from twinpulse_provider.nebius_pipeline import ObservationArtifact, parse_chat_completion
from twinpulse_provider.scene_contract import SceneContractError, role_of
from twinpulse_provider.semantic_scene import checked_structure, _shape_issues
from twinpulse_app.product_workflow_service import _public_generation_diagnostics


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedResponseTransport:
    def __init__(self, responses):
        self.responses = responses
        self.bodies = []

    async def complete(self, body, token, config):
        index = len(self.bodies)
        if index >= len(self.responses):
            raise AssertionError('Replay exhausted; no additional response is available')
        self.bodies.append(deepcopy(body))
        record = self.responses[index]
        budget = token.generation_budget
        identity = budget.reserve(body, role=token.generation_role)
        budget.settle(identity, usage=record['usage'], status='received')
        completion = parse_chat_completion(json.loads(record['response_redacted']))
        return replace(completion, attempt_id=record['attempt_id'])


async def audit(run):
    source = read(run / 'result.json')
    ledgers = list((run / 'runtime/ordinary-generation').glob('*.ledger.json'))
    if len(ledgers) != 1:
        raise ValueError('Expected one saved ordinary approval')
    ledger = read(ledgers[0])
    raw_paths = [run / 'runtime/provider-evidence' / (row['attempt_id'] + '.json')
                 for row in ledger['requests']]
    records = [read(path) for path in raw_paths]
    revisions = list((run / 'runtime/inputs').glob('*/revision.json'))
    if len(revisions) != 1:
        raise ValueError('Expected one archived input revision')
    revision = read(revisions[0])
    images = []
    for image in revision['images']:
        content = revisions[0].parent.joinpath(image['sha256'] + '.bin').read_bytes()
        if hashlib.sha256(content).hexdigest() != image['sha256']:
            raise ValueError('Archived input image digest mismatch')
        images.append(ImageInput(image['name'], image['mime_type'], content))
    checkpoints = list((run / 'runtime/provider-evidence/generation-store/checkpoint').glob('*.json'))
    if len(checkpoints) != 1:
        raise ValueError('Expected one failed checkpoint')
    checkpoint = read(checkpoints[0])['payload']
    policy = GenerationPolicy.from_dict(checkpoint['policy'])
    protected = [*raw_paths, *ledgers, *revisions, *checkpoints]
    before = {str(path): sha(path) for path in protected}
    current_source = {path: sha(ROOT / path) for path in source['inference_source_at_start']}
    if current_source != source['inference_source_at_start']:
        raise ValueError('Inference source differs from recorded run; exact replay refused')
    request = GenerationRequest(checkpoint['request_id'], revision['prompt'], tuple(images),
                                image_detail=revision['generation_settings']['image_detail'])
    transport = SavedResponseTransport(records)
    provider = BudgetedPipeline(transport, policy=policy,
        observer_model_id=records[0]['model_id'], planner_model_id=records[1]['model_id'],
        site_plan_version='2.2', planner_template_no_thinking=True,
        stage_output_token_caps={'observer': records[0]['max_tokens'], 'planner': records[1]['max_tokens']})
    terminal = None
    try:
        await provider.generate(request, CancellationToken(), None)
    except Exception as error:
        terminal = {'type': type(error).__name__, 'code': getattr(error, 'code', None)}
    if len(transport.bodies) != len(records) or not terminal or terminal['code'] != 'REPAIR_STALLED':
        raise AssertionError('Saved failure did not reproduce')
    observation = ObservationArtifact.from_mapping(checkpoint['observation'])
    rows = []
    for index, body in enumerate(transport.bodies[1:], 1):
        raw = records[index]
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if digest != raw['request_sha256']:
            raise AssertionError('Planner request hash differs at attempt ' + str(index + 1))
        schema = body['response_format']['json_schema']['schema']
        parts = [json.loads(part) for part in body['messages'][-1]['content'].splitlines()]
        candidate = json.loads(json.loads(raw['response_redacted'])['choices'][0]['message']['content'])
        try:
            checked_structure(candidate, request, observation)
            diagnosis = None
        except SceneContractError as error:
            diagnosis = error.contract_report
        rows.append({'attempt_id': raw['attempt_id'], 'request_sha256_matches': True,
            'response_schema_sha256_matches': hashlib.sha256(json.dumps(
                body['response_format'], sort_keys=True).encode()).hexdigest() == raw['schema_sha256'],
            'roles': [message['role'] for message in body['messages']],
            'observations_in_request': len(parts[0]['observations']['entities']),
            'required_object_ids': [e['id'] for e in parts[0]['observations']['entities']
                                    if role_of(e) in {'object', 'unknown'}],
            'root_fields': list(schema['properties']),
            'candidate_schema_issues': _shape_issues(candidate, schema),
            'candidate_inventory_count': len(candidate['inventory']),
            'semantic_diagnosis': diagnosis, 'feedback': parts[1:],
            'previous_candidate_in_feedback': any('candidate' in part for part in parts[1:]),
            'request': body})

    # Independent local counterexample: progressive coverage still gets treated
    # as stalled because only code:path, not missing identities, is compared.
    entities = [e for e in observation.entities if role_of(e) in {'object', 'unknown'}]
    tracker = ProgressTracker()
    counter_budget = ExecutionBudget(policy)
    partial_rows = []
    for count in (0, len(entities) // 2, len(entities) - 1):
        candidate = {'summary': 'Synthetic local progress counterexample',
            'room': {'width_m': 4, 'length_m': 4, 'height_m': 2.5}, 'inventory': [
                {'id': 'synthetic_' + e['id'], 'kind': e['category'], 'source': {
                    'basis': 'inferred' if role_of(e) == 'unknown' else 'visual',
                    'observation_ids': [e['id']], 'user_quote': None}}
                for e in entities[:count]]}
        try:
            checked_structure(candidate, request, observation)
            raise AssertionError('Incomplete counterexample unexpectedly passed')
        except SceneContractError as error:
            diagnosis = error.contract_report
        blockers = [i['code'] + ':' + i.get('path', '') for i in diagnosis['issues']]
        progressed = tracker.observe(candidate, blockers)
        if partial_rows:
            try:
                counter_budget.repair_result(progressed=progressed)
            except Exception as error:
                if getattr(error, 'code', None) != 'REPAIR_STALLED':
                    raise
        partial_rows.append({'represented': count, 'missing': len(entities) - count,
            'blocker_keys': blockers, 'progressed': progressed, 'stop_reason': counter_budget.terminal})
    final = provider.diagnostic_for(request.request_id)
    public = _public_generation_diagnostics(final)
    return {'audit_kind': 'offline_saved_response_request_reconstruction', 'network_calls': 0,
        'original_execution_id': records[0]['execution_id'], 'replay_terminal': terminal,
        'planner_exact_request_matches': len(rows), 'source_unchanged': True,
        'protected_originals_unchanged': all(sha(Path(path)) == digest for path, digest in before.items()),
        'planner_attempts': rows, 'provider_final_attempt_count': len(final['attempts']),
        'public_final_attempt_count': len(public['attempts']),
        'public_total_requests': public['budget']['requests'],
        'public_attempts_truncated_indicator': public.get('attempts_truncated'),
        'provider_attempt_repair_flags': [a.get('repair') for a in final['attempts']],
        'synthetic_progress_counterexample': partial_rows,
        'model_quality_acceptance': False,
        'note': 'Planner bodies hash-match the original audited dispatches. Observer transport conversion '
                'was not reconstructed; no provider was contacted. Synthetic rows are not scene results.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    def deny(*_args, **_kwargs):
        raise AssertionError('Network prohibited in offline request audit')
    # Windows creates a loopback self-pipe when constructing its event loop.
    # Construct it before denying all connections during the audit itself.
    with asyncio.Runner() as runner:
        runner.get_loop()
        with patch('socket.socket.connect', deny), patch('urllib.request.OpenerDirector.open', deny):
            result = runner.run(audit(args.run.resolve()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key != 'planner_attempts'}, indent=2))


if __name__ == '__main__':
    main()
