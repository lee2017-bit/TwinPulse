# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exercise real local freeze/prepare/evaluator worksheets with two synthetic texts.

Not a model trial, final rubric, independent dataset, financial approval or
Isaac acceptance. Original evidence is hash-checked, never rewritten.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import (file_sha,read_json,source_freeze,text_sha,canonical_sha,
                                        prepare,effective_settings_sha)
from scripts.benchmark_environment import verify_environment,identity
from scripts.benchmark_evaluation import selected_rubric
from scripts.prepare_benchmark_evaluation import worksheets
from twinpulse_provider.generation_policy import GenerationPolicy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--environment',type=Path,required=True)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--original-audit',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if any(p.is_symlink() for p in (args.output,*args.output.parents)):
        raise ValueError('BENCHMARK_LINKED_OUTPUT')
    originals=read_json(args.original_audit)['original_hashes']
    if any(file_sha(ROOT/p)!=digest for p,digest in originals.items()):
        raise ValueError('ORIGINAL_HASH_CHANGED')
    frozen=source_freeze(ROOT)
    inputs={str(p.resolve()):file_sha(p) for p in (args.environment,args.catalog,args.original_audit)}
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (output/name).open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
    rubric=dict(schema_version='benchmark-rubric-1.0',entity_f1_min=.8,hazard_recall_min=.9,
        relation_accuracy_min=.8,match_distance_uv=.2,relation_epsilon_uv=.05,
        adjacent_distance_uv=.3,size_relative_tolerance=.2)
    save('provisional-contract-rubric.json',rubric)
    def ref(path):return dict(path=str(path.resolve()),sha256=file_sha(path))
    roles=dict(observer=dict(provider='openai',model='gpt-6-luna'),
               planner=dict(provider='nebius',model='nvidia/Nemotron-3_5-Lightning'))
    roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
    policy=replace(GenerationPolicy(),max_requests=24,external_final_review=True,
                   initial_timeout_s=420,final_timeout_s=180)
    route=dict(observer=dict(key_id='OFFLINE_NO_KEY',model_id=roles['observer']['model'],max_output_tokens=20000),
        planner=dict(key_id='OFFLINE_NO_KEY',model_id=roles['planner']['model'],max_output_tokens=20000,thinking_mode='disabled'),
        generation_policy=policy.to_dict())
    from twinpulse_provider.model_contracts import catalog_sha
    route['model_catalog_sha256']=catalog_sha(read_json(args.catalog))
    cases=[]
    for case_id,prompt,goal in (
            ('bedroom-contract','An approximate bedroom with a bed, desk and chair.','Go to desk'),
            ('warehouse-contract','An approximate warehouse with two shelves and a pallet.','Go to pallet')):
        cases.append(dict(schema_version='benchmark-case-1.0',case_id=case_id,room_group=case_id,
            split='development',modality='text',prompt=prompt,prompt_sha256=text_sha(prompt),photo=None,
            goal=dict(text=goal,sha256=text_sha(goal),expected='arrival',start_policy='checked_sim_preview'),
            source=dict(reference='Self-authored synthetic protocol input, not independently labelled benchmark data',
                license='Local offline contract verification only',external_transmission_allowed=False,public_release_allowed=False),
            annotations=None))
    manifest=dict(schema_version='comparative-benchmark-1.2',dataset_id='offline-package-contract',version='402',
        seed=46,repeats=1,cases=cases,configs=[dict(config_id='reviewed-contract',roles=roles,
            settings_sha256=effective_settings_sha(route,roles))],freeze=frozen,
        model_catalog=ref(args.catalog),execution_environment=ref(args.environment),
        evaluation=dict(rubric=ref(output/'provisional-contract-rubric.json'),review_provenance=None))
    save('manifest.json',manifest)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('NO_NETWORK')), \
         patch('twinpulse_app.credentials.WindowsCredentialStore.load',side_effect=AssertionError('NO_CREDENTIAL')):
        prepared=prepare(output/'manifest.json')
        matching=verify_environment(prepared,ROOT)
        drafts=worksheets(prepared,selected_rubric(prepared))
        save('prepared.json',prepared);save('pending-worksheets.json',drafts)
    if source_freeze(ROOT)!=frozen:raise ValueError('SOURCE_CHANGED_DURING_OFFLINE_VERIFICATION')
    if any(file_sha(p)!=digest for p,digest in inputs.items()):raise ValueError('FROZEN_INPUT_CHANGED')
    if any(file_sha(ROOT/p)!=digest for p,digest in originals.items()):raise ValueError('ORIGINAL_HASH_CHANGED')
    result=dict(status='OFFLINE_PACKAGE_CONTRACT_PASS_NOT_BENCHMARK',
        manifest_sha256=file_sha(output/'manifest.json'),environment_sha256=identity(prepared['execution_environment']),
        source_asset_files=len(frozen),runtime_files=len(prepared['execution_environment']['runtime_files']),
        reviewed_asset_files=len(prepared['execution_environment']['assets']),synthetic_text_cases=len(cases),
        independent_data_cases=0,rubric_status='PROVISIONAL_CONTRACT_ONLY',
        label_readiness=prepared['evaluation_readiness'],environment_match=matching,
        originals_checked=len(originals),originals_unchanged=True,frozen_inputs_unchanged=True,
        HTTP=0,credential_reads=0,actual_model='NOT_RUN',actual_Isaac='NOT_RUN',robot_calls=0,whole_demo_pass=False)
    save('result.json',result)
    print(json.dumps({key:result[key] for key in ('status','source_asset_files','runtime_files',
        'reviewed_asset_files','synthetic_text_cases','independent_data_cases','originals_checked','HTTP')}))


if __name__=='__main__':main()
