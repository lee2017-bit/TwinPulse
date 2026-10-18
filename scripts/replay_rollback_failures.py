# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Replay immutable actual responses through the fixed product, with network forbidden.

Derived evidence only. Does not retry endpoints, change old results/ledgers,
or claim a saved failed model response becomes a fresh model success.
"""
import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ('twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))

from twinpulse_core import canonical_sha256
from twinpulse_provider import GenerationRequest, GenerationService, ImageInput, ProviderConfig, ProviderCapabilities
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy, GenerationBudgetError
from twinpulse_provider.nebius_pipeline import ChatCompletion, parse_chat_completion
from twinpulse_provider.semantic_scene import revision


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SavedResponseTransport:
    def __init__(self, observation, records):
        self.observation = observation
        self.records = list(records)
        self.used = []
        self.validation = []
        self.next_request = None

    async def complete(self, body, token, config):
        if body['response_format']['json_schema']['name'] == 'twinpulse_image_observation':
            return ChatCompletion('historical-observation-reuse', body['model'],
                json.dumps(self.observation), 'stop', {})
        if not self.records:
            self.next_request = deepcopy(body)
            raise GenerationBudgetError('SAVED_RESPONSES_EXHAUSTED')
        path, record = self.records.pop(0)
        if body['model'] != record['model_id']:
            raise AssertionError('Saved model identity changed')
        completion = parse_chat_completion(json.loads(record['response_redacted']))
        budget = token.generation_budget
        attempt = budget.reserve(body, role=token.generation_role)
        budget.settle(attempt, status='received', usage=completion.usage)
        self.used.append(dict(source_attempt_id=path.stem, source_sha256=digest(path),
            replay_attempt_id=attempt, role=token.generation_role,
            request_sha256=canonical_sha256(body)))
        return replace(completion, attempt_id=attempt)

    def record_validation(self, stage, attempt_id, record):
        self.validation.append(dict(stage=stage, replay_attempt_id=attempt_id, record=deepcopy(record)))


async def replay(source, output):
    scope = read(source/'scope.json')
    summary = read(source/'summary-final.json')
    selected = [row for row in summary['results'] if row.get('role') == 'planner'
        and row.get('error', '').startswith('UNMAPPED_COMPILER_ERROR: PHOTO_LAYOUT_REGION_FULL')]
    if len(selected) != 5:
        raise AssertionError('Expected the five diagnosed original failures')
    photo = ROOT/'outputs/ordinary-full-retest-20261010/run-1/1-사진-1.jpg'
    if digest(photo) != scope['photo_sha256']:
        raise AssertionError('Source photo changed')
    preserved = {p: digest(p) for p in source.rglob('*.json')}
    preserved[photo] = digest(photo)
    outcomes = []
    for row in selected:
        directory = source/'cases'/row['case_id']
        hostfix = directory.with_name(directory.name+'-hostfix')
        if (hostfix/'result.json').exists():
            directory = hostfix
        old = read(directory/'result.json')
        state = read(directory/'generation-store/checkpoint'/(old['diagnostic']['checkpoint_id']+'.json'))['payload']
        transport = SavedResponseTransport(state['observation'], [
            (directory/'evidence'/(identity+'.json'), read(directory/'evidence'/(identity+'.json')))
            for identity in row['attempt_ids']])
        provider = BudgetedPipeline(transport, policy=GenerationPolicy.from_dict(state['policy']),
            store_root=output/row['case_id'], site_plan_version='2.2',
            observer_model_id='historical-shared-observation', planner_model_id=row['model_id'],
            stage_output_token_caps={'observer':20000, 'planner':20000})
        request = GenerationRequest('rollback-replay-'+row['case_id'], scope['prompt'],
            (ImageInput(photo.name, 'image/jpeg', photo.read_bytes()),))
        config = ProviderConfig('https://invalid.example/v1/', 'chat/completions', row['model_id'],
            'OFFLINE_UNUSED', ProviderCapabilities(True, True, 1), timeout_s=300)
        result = error = None
        try:
            result = await GenerationService(provider, config, plan_version='2.2').generate(request)
        except Exception as caught:
            error = caught
        diagnostic = provider.diagnostic_for(request.request_id)
        new = provider.store.read('checkpoint', diagnostic['checkpoint_id'])
        rollback = new.get('rollback_revalidation') or {}
        next_context = json.loads(transport.next_request['messages'][-1]['content']) if transport.next_request else {}
        fixed = (result is None and error is not None and 'UNMAPPED_COMPILER_ERROR' not in str(error)
            and getattr(error, 'code', None) == 'SAVED_RESPONSES_EXHAUSTED'
            and next_context.get('repair_kind') == 'quality'
            and revision(next_context['candidate']) == rollback.get('candidate_revision')
            and rollback.get('validation') == 'passed'
            and rollback.get('quality_status') == 'needs_revision'
            and any(i['code'] == 'PHOTO_LAYOUT_REGION_FULL'
                for i in rollback.get('failed_diagnosis', {}).get('issues', []))
            and new['compiled_plan'] is None and new['budget']['repairs'] == state['budget']['repairs'])
        outcomes.append(dict(model_id=row['model_id'], original_case_id=row['case_id'],
            original_execution_id=row['execution_id'], original_error=old['error'],
            replay_request_id=request.request_id, replay_stop=getattr(error, 'code', None),
            replay_error=str(error), regression_pass=fixed, generation_pass=result is not None,
            reused_responses=transport.used, unused_response_count=len(transport.records),
            next_request_not_dispatched=transport.next_request,
            rollback_revalidation=rollback, budget=new['budget'], validation=transport.validation,
            HTTP=0, Isaac='NOT_RUN', physical_authority=False))
    unchanged = all(digest(p) == value for p, value in preserved.items())
    report = dict(status='PASS' if unchanged and all(r['regression_pass'] for r in outcomes) else 'FAIL',
        scope='Actual saved response replay, not fresh model recovery', cases=outcomes,
        immutable_file_count=len(preserved), original_evidence_unchanged=unchanged,
        HTTP=0, robot_commands=0, whole_demo_pass=False)
    path = output/'report.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return report, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    def forbidden(*args, **kwargs):
        raise AssertionError('Network forbidden during saved response replay')
    # Windows creates the event-loop wakeup socket pair via local TCP.
    # Construct it before denying all connect calls made by the replay.
    loop = asyncio.new_event_loop()
    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    try:
        report, path = loop.run_until_complete(replay(args.source.resolve(), args.output.resolve()))
    finally:
        loop.close()
    print(json.dumps(dict(status=report['status'], report_path=str(path),
        originals_unchanged=report['original_evidence_unchanged'], HTTP=0,
        cases=[{k:row[k] for k in ('model_id','replay_stop','regression_pass','generation_pass')}
            for row in report['cases']]), ensure_ascii=False))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
