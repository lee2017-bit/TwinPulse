# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Updated-code regression against immutable failed responses; no new model call.

Unlike the historical exact-request audit, changed request hashes are expected.
Never use this replay as evidence of actual LLM recovery or Isaac acceptance.
"""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from audit_budgeted_request_trace import (SavedResponseTransport, read, sha, BudgetedPipeline,
    GenerationPolicy, GenerationRequest, CancellationToken, ImageInput, _public_generation_diagnostics)


async def verify(run):
    ledgers = list((run/'runtime/ordinary-generation').glob('*.ledger.json'))
    revisions = list((run/'runtime/inputs').glob('*/revision.json'))
    checkpoints = list((run/'runtime/provider-evidence/generation-store/checkpoint').glob('*.json'))
    if not len(ledgers)==len(revisions)==len(checkpoints)==1:
        raise ValueError('Expected one ledger, input and checkpoint')
    ledger, revision, checkpoint = read(ledgers[0]), read(revisions[0]), read(checkpoints[0])['payload']
    raw_paths = [run/'runtime/provider-evidence'/f'{row["attempt_id"]}.json' for row in ledger['requests']]
    records = [read(path) for path in raw_paths]
    images = []
    image_paths = []
    for image in revision['images']:
        path = revisions[0].parent/(image['sha256']+'.bin')
        if sha(path)!=image['sha256']:
            raise ValueError('Archived image digest mismatch')
        image_paths.append(path)
        images.append(ImageInput(image['name'], image['mime_type'], path.read_bytes()))
    protected = [run/'result.json', *raw_paths, *ledgers, *revisions, *checkpoints, *image_paths]
    originals = {str(path): sha(path) for path in protected}
    class Transport(SavedResponseTransport):
        def __init__(self, responses):
            super().__init__(responses)
            self.validations = []
        def record_validation(self, stage, attempt_id, record):
            self.validations.append(dict(stage=stage, attempt_id=attempt_id, record=deepcopy(record)))
    transport = Transport(records)
    provider = BudgetedPipeline(transport, policy=GenerationPolicy.from_dict(checkpoint['policy']),
        observer_model_id=records[0]['model_id'], planner_model_id=records[1]['model_id'],
        site_plan_version='2.2', planner_template_no_thinking=True,
        stage_output_token_caps={'observer': records[0]['max_tokens'], 'planner': records[1]['max_tokens']})
    request = GenerationRequest(checkpoint['request_id'], revision['prompt'], tuple(images),
        image_detail=revision['generation_settings']['image_detail'])
    terminal = None
    try:
        await provider.generate(request, CancellationToken(), None)
    except Exception as error:
        terminal = getattr(error, 'code', None)
    if terminal != 'REPAIR_STALLED' or len(transport.bodies)!=4:
        raise AssertionError('Repeated saved invalid candidates must still fail after bounded repairs')
    for index in (2, 3):
        feedback = json.loads(transport.bodies[index]['messages'][-1]['content'].splitlines()[-1])
        previous = json.loads(json.loads(records[index-1]['response_redacted'])['choices'][0]['message']['content'])
        if feedback['previous_candidate']!=previous or feedback['previous_attempt_id']!=records[index-1]['attempt_id']:
            raise AssertionError('Exact prior candidate/attempt missing')
        if any(issue.get('path','').startswith('$.objects') for issue in feedback['validation']['issues']):
            raise AssertionError('Wrong repair contract path')
    final = provider.diagnostic_for(request.request_id)
    public = _public_generation_diagnostics(final)
    if public['attempts_total']!=4 or len(public['attempts'])!=4 or public['attempts_truncated']:
        raise AssertionError('Public attempt history incomplete')
    if [a['repair'] for a in public['attempts']]!=[False, False, True, True]:
        raise AssertionError('Incorrect attempt role')
    result = dict(verification_kind='updated_code_saved_response_regression', network_calls=0,
        original_execution_id=records[0]['execution_id'], terminal=terminal, attempts=public['attempts'],
        original_artifacts_unchanged=all(sha(Path(path))==digest for path,digest in originals.items()),
        request_hashes_changed_as_expected=[hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
            != records[index]['request_sha256'] for index,body in enumerate(transport.bodies)],
        latest_diagnosis=final.get('scene_contract'), validation_evidence=transport.validations,
        model_quality_acceptance=False, actual_model_recovery='NOT_RUN', Isaac='NOT_RUN')
    if not result['original_artifacts_unchanged']:
        raise AssertionError('Protected historical evidence changed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    def deny(*args, **kwargs):
        raise AssertionError('No network permitted in saved-response regression')
    with asyncio.Runner() as runner:
        runner.get_loop()
        with patch('socket.socket.connect', deny), patch('urllib.request.OpenerDirector.open', deny):
            result = runner.run(verify(args.run.resolve()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key:result[key] for key in ('verification_kind','network_calls','terminal',
        'original_artifacts_unchanged','actual_model_recovery')}, ensure_ascii=False))


if __name__=='__main__':
    main()
