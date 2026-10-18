# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Freeze a reusable actual pilot, never invent human labels or financial consent.

Source records and auxiliary pre-output references are evaluator-only. Actual
dispatch remains exclusively in the existing expiring manifest controller.
"""
import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import read_json,file_sha,text_sha,canonical_sha,source_freeze,prepare,effective_settings_sha,frozen_stage_output_caps
from scripts.benchmark_environment import capture,identity
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.model_contracts import catalog_sha

PAIRS=(('flash-lightning','deepseek-ai/DeepSeek-V4.1-Flash','nvidia/Nemotron-3_5-Lightning'),
       ('qwen-lightning','Qwen/Qwen3.8-27B','nvidia/Nemotron-3_5-Lightning'),
       ('luna-lightning','gpt-6-luna','nvidia/Nemotron-3_5-Lightning'),
       ('flash-luna','deepseek-ai/DeepSeek-V4.1-Flash','gpt-6-luna'),
       ('luna-luna','gpt-6-luna','gpt-6-luna'))


def exclusive(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def build(spec,spec_path,catalog_path,output,*,version='403-pilot',observer_cap=20000,planner_cap=20000,
          pairs=PAIRS,request_cap=24):
    if spec['schema_version']!='pilot-dataset-spec-1.0':raise ValueError('PILOT_SPEC_VERSION')
    if type(request_cap) is not int or request_cap not in (12,24):
        raise ValueError('BENCHMARK_REVIEWED_RESOURCE_POLICY_REQUIRED')
    caps=frozen_stage_output_caps(dict(stage_output_token_caps=dict(observer=observer_cap,planner=planner_cap)))
    output=Path(output).resolve()
    if any(p.is_symlink() for p in (output,*output.parents)):raise ValueError('PILOT_LINKED_OUTPUT')
    output.mkdir(parents=True,exist_ok=False)
    cases=[];references=[]
    for row in spec['cases']:
        photo=(Path(spec_path).resolve().parent/row['photo']).resolve() if row['photo'] else None
        case=dict(schema_version='benchmark-case-1.0',case_id=row['case_id'],room_group=row['room_group'],
            split='development',modality='photo' if photo else 'text',prompt=row['prompt'],
            prompt_sha256=text_sha(row['prompt']),photo=dict(path=str(photo),sha256=file_sha(photo),
                mime_type='image/jpeg') if photo else None,
            goal=dict(text=row['goal'],sha256=text_sha(row['goal']),expected='arrival',start_policy='checked_sim_preview'),
            source=deepcopy(row['source']),annotations=None)
        cases.append(case)
        references.append(dict(case_id=row['case_id'],prompt_sha256=case['prompt_sha256'],
            photo_sha256=case['photo']['sha256'] if photo else None,**deepcopy(row['reference'])))
    environment=capture(ROOT);exclusive(output/'environment.json',environment)
    # Provisional quality rubric remains selected/bound; no attested human
    # labels means qualified full PASS cannot be manufactured from this pilot.
    rubric=dict(schema_version='benchmark-rubric-1.0',entity_f1_min=.8,hazard_recall_min=.9,
        relation_accuracy_min=.85,match_distance_uv=.2,relation_epsilon_uv=.05,
        adjacent_distance_uv=.3,size_relative_tolerance=.2)
    exclusive(output/'rubric.json',rubric)
    exclusive(output/'auxiliary-reference.json',dict(schema_version='pilot-auxiliary-reference-1.0',
        created_before_outputs=True,human_reviewers=0,metric_scope='REQUIRED_KIND_RECALL_NOT_FULL_PHOTOREAL_QUALITY',
        cases=references))
    policy=replace(GenerationPolicy(),max_requests=request_cap,external_final_review=True,initial_timeout_s=420,final_timeout_s=180)
    configs=[]
    for config_id,observer,planner in pairs:
        def role(model):return dict(provider='openai' if model=='gpt-6-luna' else 'nebius',model=model)
        roles=dict(observer=role(observer),planner=role(planner));roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
        route=dict(observer=dict(model_id=observer,max_output_tokens=caps['observer']),
            planner=dict(model_id=planner,max_output_tokens=caps['planner'],thinking_mode='disabled' if planner=='nvidia/Nemotron-3_5-Lightning' else 'default'),
            generation_policy=policy.to_dict(),model_catalog_sha256=catalog_sha(read_json(catalog_path)))
        configs.append(dict(config_id=config_id,roles=roles,settings_sha256=effective_settings_sha(route,roles),
            stage_output_token_caps=deepcopy(caps)))
    def ref(path):return dict(path=str(Path(path).resolve()),sha256=file_sha(path))
    frozen=source_freeze(ROOT)
    for path in (Path(spec_path),output/'auxiliary-reference.json'):
        frozen[str(path.resolve())]=file_sha(path)
    for case in cases:
        if case['photo']:frozen[case['photo']['path']]=case['photo']['sha256']
    manifest=dict(schema_version='comparative-benchmark-1.3',dataset_id=spec['dataset_id'],version=version,
        seed=spec['seed'],repeats=spec['repeats'],cases=cases,configs=configs,freeze=frozen,
        model_catalog=ref(catalog_path),execution_environment=ref(output/'environment.json'),
        evaluation=dict(rubric=ref(output/'rubric.json'),review_provenance=None))
    exclusive(output/'manifest.json',manifest)
    prepared=prepare(output/'manifest.json');exclusive(output/'prepared.json',prepared)
    return dict(status='PILOT_FROZEN_NOT_AUTHORIZED',manifest_sha256=file_sha(output/'manifest.json'),
        source_files=len(source_freeze(ROOT)),environment_sha256=identity(environment),cases=len(cases),
        photos=sum(c['modality']=='photo' for c in cases),configs=len(configs),planned=len(prepared['jobs']),
        stage_output_token_caps=caps,
        human_quality='NOT_EVALUATED',auxiliary_reference_sha256=file_sha(output/'auxiliary-reference.json'),HTTP=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--version',default='403-pilot',help='Explicit source-cohort version, never changes preserved results')
    parser.add_argument('--observer-output-tokens',type=int,default=20000,help='Frozen observer and inherited critic cap, not an automatic retry')
    parser.add_argument('--planner-output-tokens',type=int,default=20000,help='Frozen planner and inherited repair cap')
    args=parser.parse_args()
    result=build(read_json(args.spec),args.spec,args.catalog,args.output,version=args.version,
        observer_cap=args.observer_output_tokens,planner_cap=args.planner_output_tokens)
    exclusive(args.output/'preparation-result.json',result);print(json.dumps(result))


if __name__=='__main__':main()
