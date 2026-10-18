# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only original ordinary live raw/ledger validation; no model/network."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_provider','twinpulse_core'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_provider import GenerationRequest
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.semantic_scene import checked_structure
from twinpulse_provider.scene_contract import SceneContractError,role_of


def main():
    run=Path(sys.argv[1]).resolve()
    paths=list((run/'runtime/ordinary-generation').glob('*.ledger.json'))
    if len(paths)!=1:raise ValueError('Expected one reviewed natural live grant')
    ledger=json.loads(paths[0].read_text(encoding='utf-8'))
    result=json.loads((run/'result.json').read_text(encoding='utf-8'))
    conversation=result['browser']['failure_state']['conversation']
    prompt=next(message['content'] for message in conversation['messages']
                if message['role']=='user')
    request=GenerationRequest('read-only-original-validation',prompt)
    rows=[];observation=None
    for entry in ledger['requests']:
        raw=json.loads((run/'runtime/provider-evidence'/f"{entry['attempt_id']}.json").read_text(encoding='utf-8'))
        response=json.loads(raw['response_redacted'])
        value=json.loads(response['choices'][0]['message']['content'])
        if hashlib.sha256(raw['response_redacted'].encode()).hexdigest()!=raw['stored_response_sha256']:
            raise ValueError('Stored raw response checksum mismatch')
        if raw['usage']!=entry['usage']:raise ValueError('Raw/ledger usage differs')
        row={k:raw[k] for k in ('attempt_id','model_id','http_status','finish_reason','elapsed_s','usage','max_tokens')}
        if raw['model_id'].startswith('gpt-'):
            observation=ObservationArtifact.from_mapping(value)
            row.update(stage='observer',entities=len(observation.entities),
                required_objects=[{'id':e['id'],'kind':e.get('category')} for e in observation.entities
                                  if role_of(e) in {'object','unknown'}])
        else:
            if observation is None:raise ValueError('No earlier original observation')
            try:
                checked_structure(value,request,observation)
                row['validation']='PASS'
            except SceneContractError as error:
                row['validation']=error.contract_report
            row.update(stage='structure',inventory=value['inventory'],room=value['room'],
                inventory_sha256=hashlib.sha256(json.dumps(value['inventory'],sort_keys=True).encode()).hexdigest())
        rows.append(row)
    analysis={'paid_requests':len(rows),'unchanged_raw_ledger_usage':True,
        'model_result':result['status'],'rows':rows,'new_model_calls':0,
        'validation_only':True,'original_user_prompt':prompt}
    (run/'original-response-analysis.json').write_text(
        json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(analysis,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
