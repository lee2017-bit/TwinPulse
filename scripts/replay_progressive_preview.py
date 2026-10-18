# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Recompile immutable saved candidates locally; no inference, engine or source edits."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'packages'/package/'src') for package in ('twinpulse_core','twinpulse_provider','twinpulse_app')]
from twinpulse_core import canonical_sha256
from twinpulse_provider.contracts import GenerationRequest,ImageInput
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.generation_preview import compile_generation_preview
from twinpulse_provider.semantic_scene import compile_scene


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();checkpoint=args.checkpoint.resolve();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'outputs'):raise SystemExit('OUTPUT_OUTSIDE_WORKSPACE')
    output.mkdir(parents=True,exist_ok=False)
    original=checkpoint.read_bytes();raw=json.loads(original)
    if raw['payload_sha256']!=canonical_sha256(raw['payload']):raise ValueError('CHECKPOINT_DIGEST_MISMATCH')
    final=raw['payload'];history=checkpoint.parent.parent/'checkpoint-history'/checkpoint.stem
    rows=[]
    for path in history.glob('*.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value['payload_sha256']!=canonical_sha256(value['payload']):raise ValueError('HISTORY_DIGEST_MISMATCH')
        payload=value['payload']
        if payload.get('draft') and not payload['budget']['repairs']:rows.append(payload)
    request=GenerationRequest('readonly-saved-candidate-replay','',images=(ImageInput('existing-photo-context','image/jpeg',b'offline-no-image-decoding'),))
    result=dict(status='PASS',scope='LOCAL_COMPILER_REPLAY_NOT_FRESH_MODEL_OR_ISAAC',
        original_checkpoint_sha256=hashlib.sha256(original).hexdigest(),external_requests=0,external_cost_usd='0',
        stages=[],original_stop_reason=final['budget']['stop_reason'])
    for count in sorted({len(row['draft']['objects']) for row in rows}):
        row=next(row for row in rows if len(row['draft']['objects'])==count);draft=row['draft'];before=canonical_sha256(draft)
        plan,_,progress=compile_generation_preview(draft,ObservationArtifact.from_mapping(row['observation'],allow_derived=True),request)
        result['stages'].append(dict(parameterized=count,inventory=len(draft['inventory']),
            rendered=progress['rendered_count'],pending=progress['pending_count'],
            pending_objects=progress['pending_objects'],source_candidate_unchanged=canonical_sha256(draft)==before,
            plan_sha256=canonical_sha256(plan),preview_only=progress['preview_only']))
    try:
        compile_scene(final['draft'],ObservationArtifact.from_mapping(final['observation'],allow_derived=True),request)
        result['full_candidate']='compiled'
    except Exception as error:
        result['full_candidate']='still_blocked'
        result['full_candidate_error']=str(error)[:500]
    result['original_file_unchanged']=checkpoint.read_bytes()==original
    assert result['original_file_unchanged'] and all(row['source_candidate_unchanged'] for row in result['stages'])
    assert next(row for row in result['stages'] if row['parameterized']==6)['rendered']>0
    (output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','full_candidate','external_requests','external_cost_usd')}))
    print(json.dumps([{key:row[key] for key in ('parameterized','inventory','rendered','pending')} for row in result['stages']]))


if __name__=='__main__':main()
