# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline raw-failure replay of repair roles. No HTTP, credentials or robot.

The original length response is parsed unchanged; a local stub reproduces the
recorded second failure. This proves local request construction, not recovery.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_provider import ProviderConfig,ProviderCapabilities,CancellationToken
from twinpulse_provider.errors import InvalidProviderResponseError,ProviderRequestError
from twinpulse_provider.nebius_pipeline import NebiusChatCompletionsPipelineProvider,parse_chat_completion


async def inspect(run):
    paths=list((run/'runtime/provider-evidence').glob('*.json'))
    originals={p:p.read_bytes() for p in paths}
    records=[json.loads(v) for v in originals.values()]
    first=next(r for r in records if 'choices' in json.loads(r['response_redacted']))
    second=next(r for r in records if r.get('http_status')==400)
    payload=json.loads(first['response_redacted']);content=payload['choices'][0]['message']['content']
    recorded_error=json.loads(second['response_redacted'])['error']['message']
    bodies=[]
    class LocalRecordedFailure:
        async def complete(self,body,token,config):
            bodies.append(body)
            if len(bodies)==1:
                try:return parse_chat_completion(payload)
                except InvalidProviderResponseError as error:
                    error.attempt_id=first['attempt_id'];raise
            error=ProviderRequestError('provider request failed (400)')
            error.attempt_id=second['attempt_id'];raise error
    provider=NebiusChatCompletionsPipelineProvider(LocalRecordedFailure(),
        observer_model_id=first['model_id'],planner_model_id='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
        site_plan_version='2.2',max_repairs=1)
    state=dict(request_id='offline-role-replay',repair_count=0,attempts=[],sequence=0)
    provider._diagnostic=state
    original=dict(model=first['model_id'],max_tokens=10000,messages=[
        dict(role='system',content='Offline role-structure diagnostic; no dispatch.'),
        dict(role='user',content='Illustrative bedroom request, not a live replay of image upload.')])
    config=ProviderConfig('https://api.tokenfactory.nebius.com/v1/','chat/completions',
        first['model_id'],'UNUSED_NO_CREDENTIALS',ProviderCapabilities(True,True,1),timeout_s=5)
    try:
        await provider._validated_stage('observer',original,lambda unused:None,
            CancellationToken(),config,state,time.monotonic()+10)
        raise AssertionError('RECORDED_FAILURE_MUST_NOT_PASS')
    except ProviderRequestError:pass
    roles=[m['role'] for m in bodies[1]['messages']]
    assert roles==['system','user','user'] and state['repair_count']==1
    assert state['attempts'][0]['validation_code']=='PROVIDER_VALIDATION_FAILED'
    assert all(p.read_bytes()==v for p,v in originals.items())
    return dict(status='REPRODUCED_LOCAL_DEFECT_NOT_RECOVERY',new_api_calls=0,
        original_finish_reason=payload['choices'][0]['finish_reason'],original_completion_tokens=payload['usage']['completion_tokens'],
        original_elapsed_s=first['elapsed_s'],content_chars=len(content),
        trailing_whitespace_chars=len(content)-len(content.rstrip()),
        incomplete_json=True,observer_repair_count=state['repair_count'],repair_roles=roles,
        parser_discards_completion_before_repair=True,original_error=recorded_error,
        truncated_code_lost=state['attempts'][0]['validation_code'],
        error_classification_mismatch='HTTP400 raw/ledger rejected but public progress outcome_unknown',
        original_raw_unchanged=True,original_raw_hashes={p.name:hashlib.sha256(v).hexdigest() for p,v in originals.items()},
        limitation='Synthetic original message text; exact original raw parser failure and product repair code, no new model output or repaired candidate.')


if __name__=='__main__':
    run=Path(sys.argv[1]);value=asyncio.run(inspect(run))
    with (run/'offline-length-repair-analysis.json').open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
    print(json.dumps(value))
