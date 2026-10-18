# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only old model evidence -> current compiler/gate. No API or credentials.

Local reviewed region corrections are explicitly NOT new model repair success.
Original results/raw files stay immutable; derived reports use a fresh folder.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

from twinpulse_core.photo_quality import inspect_photo_geometry, reviewed_photo_constraints
from tests.fixtures.historical_room_photo_inventory import PHOTO_SHA256, photo_reference
from twinpulse_provider import GenerationRequest, ImageInput
from twinpulse_provider.nebius_pipeline import ObservationArtifact, parse_chat_completion
from twinpulse_provider.photo_layout import compile_layout
from scripts.replay_audited_inference import live_run_inputs


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_completion(path):
    evidence=json.loads(path.read_text(encoding='utf-8'))
    raw=evidence['response_redacted'].encode('utf-8')
    if (hashlib.sha256(raw).hexdigest()!=evidence['response_sha256']
            or len(raw)!=evidence['response_byte_count'] or evidence['response_truncated']):
        raise ValueError('ORIGINAL_RESPONSE_HASH_OR_LENGTH_MISMATCH')
    completion=parse_chat_completion(json.loads(raw.decode('utf-8')))
    if completion.model_id!=evidence['model_id']:raise ValueError('ORIGINAL_RESPONSE_MODEL_MISMATCH')
    return json.loads(completion.content)


def verify(args):
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'artifacts') or output.exists():
        raise ValueError('Use a new output directory inside repository artifacts; no overwrite')
    photo=args.photo.read_bytes()
    if hashlib.sha256(photo).hexdigest()!=PHOTO_SHA256:raise ValueError('Reviewed P01 photo required')
    previous=ROOT/'artifacts/agent-reliability-20261007/photo-quality-loop-r1'
    source=ROOT/'artifacts/agent-reliability-20261007/compact-chat-isaac-live-r1'
    draft,evidence_root,ids=live_run_inputs(source)
    original_files=[ROOT/'artifacts/agent-reliability-20261007/campaign.json',
        source/'result.json',source/'runtime/active_project.json',
        *previous.glob('*.json'),*previous.glob('responses/*.json'),*evidence_root.glob('*.json')]
    before={str(p.relative_to(ROOT)):digest(p) for p in original_files}
    source_paths=['packages/twinpulse_core/src/twinpulse_core/photo_quality.py',
        'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py',
        'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py',
        'packages/twinpulse_provider/src/twinpulse_provider/errors.py',
        'packages/twinpulse_app/src/twinpulse_app/product_workflow_service.py',
        'scripts/verify_photo_geometry_gate.py']
    source_hashes={p:digest(ROOT/p) for p in source_paths}
    observation=ObservationArtifact.from_mapping(read_completion(evidence_root/(ids[0]+'.json')))
    request=GenerationRequest('offline-quality-current-source',draft.input_revision.prompt,
        (ImageInput(draft.input_revision.images[0]['name'],'image/jpeg',photo),))
    constraints=reviewed_photo_constraints(PHOTO_SHA256)
    report=dict(scope='OLD_ACTUAL_RESPONSES_CURRENT_LOCAL_COMPILER_NOT_NEW_LLM',
        new_calls=0,robot_connections=0,isaac='NOT_RUN',whole_demo_ready=False,
        prior_negative_cases=[],current_compiler_cases=[],original_hashes=before,source_hashes=source_hashes)
    output.mkdir(parents=True,exist_ok=False)
    for name in ('saved_actual_negative','controlled_region_repair','quality_feedback_correction'):
        payload=json.loads((previous/(name+'-plan.json')).read_text(encoding='utf-8'))
        quality=inspect_photo_geometry(payload,PHOTO_SHA256)
        if quality['status']!='FAIL':raise AssertionError('Previously invalid candidate incorrectly accepted')
        report['prior_negative_cases'].append(dict(name=name,quality=quality))
    for identity in ('a94679c2be7f460a8d5f842a3e78a5f3','810d355e06854215af79fc0a8386ebd6'):
        intent=read_completion(previous/'responses'/(identity+'.json'))
        for corrected in (False,True):
            candidate=deepcopy(intent)
            if corrected:
                for object_id,axis,expected in constraints.positions:
                    row,col=candidate['objects'][object_id]['region'].split('_')
                    candidate['objects'][object_id]['region']=(expected if axis=='y' else row)+'_'+(expected if axis=='x' else col)
            payload,trace=compile_layout(candidate,observation,request,photo_reference(PHOTO_SHA256),
                                         quality_constraints=constraints)
            quality=inspect_photo_geometry(payload,PHOTO_SHA256)
            if any(i['code']=='PHOTO_SUPPORT_MISMATCH' for i in quality['issues']):
                raise AssertionError('Current derived support failed')
            if corrected and (quality['checked_relation_status']!='PASS' or quality['status']!='PARTIAL'):
                raise AssertionError('Reviewed local position correction failed')
            name=identity+('-local-reviewed-region-correction' if corrected else '-original-model-regions')
            (output/(name+'-plan.json')).write_text(json.dumps(payload,indent=2),encoding='utf-8')
            report['current_compiler_cases'].append(dict(name=name,
                local_region_correction_not_llm=corrected,compiler=trace,quality=quality))
    report['originals_unchanged']=all(digest(ROOT/p)==sha for p,sha in before.items())
    if not report['originals_unchanged']:raise AssertionError('Original evidence changed')
    report['sources_unchanged_during_check']=all(digest(ROOT/p)==sha for p,sha in source_hashes.items())
    if not report['sources_unchanged_during_check']:raise AssertionError('Implementation changed during check')
    report['status']='LOCAL_CHECKS_PASS_NOT_FULL_FIDELITY'
    (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],old_candidates_rejected=len(report['prior_negative_cases']),
        current_cases=len(report['current_compiler_cases']),original_files=len(before),
        originals_unchanged=report['originals_unchanged'],new_calls=0,result=str(output/'result.json'))))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--photo',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    verify(parser.parse_args())
