# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only failed-checkpoint compiler diagnosis, never live acceptance.

No model/network/Isaac/robot/credential access or product-state writes. The
original terminal and immutable checkpoint are retained unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    path=args.checkpoint.resolve();output=args.output.resolve();runtime=args.runtime.resolve()
    if (not path.is_relative_to(runtime/'provider-evidence/generation-store/checkpoint-history') or
            not output.is_relative_to(ROOT/'outputs') or output.exists()):
        raise ValueError('Immutable original history and fresh local output required')
    original=path.read_bytes();envelope=json.loads(original);checkpoint=envelope['payload']
    from twinpulse_core import canonical_sha256,InputArtifactStore
    from twinpulse_app.project_store import ProjectStore
    from twinpulse_provider import GenerationRequest,ImageInput
    from twinpulse_provider.nebius_pipeline import ObservationArtifact
    from twinpulse_provider.semantic_scene import compile_scene,revision
    from twinpulse_provider.partial_refinement import checked_support_subset
    if canonical_sha256(checkpoint)!=envelope['payload_sha256'] or path.stem!=envelope['payload_sha256']:
        raise ValueError('Original checkpoint hash mismatch')
    store=ProjectStore.for_project(runtime,args.project);record=store.load()
    input_revision,images=InputArtifactStore(store.input_root()).load(record.latest_input)
    request=GenerationRequest('offline-pending-diagnosis',input_revision.prompt,
        tuple(ImageInput(*image) for image in images))
    observation=ObservationArtifact.from_mapping(checkpoint['observation'],allow_derived=True)
    draft=checkpoint['draft'];before=revision(draft)
    plan,report=compile_scene(draft,observation,request,progressive=True)
    witness=checked_support_subset(draft,plan,report)
    if path.read_bytes()!=original or revision(draft)!=before:
        raise ValueError('Original diagnostic input changed')
    result=dict(status='PASS_OFFLINE_SUBSET_ONLY',original_live_status='FAIL',
        original_stop=checkpoint['error_code'],external_calls=0,Isaac='NOT_RUN',robot='NOT_RUN',
        photo_quality='NOT_VERIFIED',original_checkpoint_sha256=hashlib.sha256(original).hexdigest(),
        checkpoint_payload_sha256=envelope['payload_sha256'],candidate_revision=before,
        plan_sha256=canonical_sha256(plan),schema_version=witness['schema_version'],
        materialized_count=sum(r['status']=='render_pending' for r in witness['inventory']),
        inventory_count=len(witness['inventory']),unresolved=witness['unresolved'],
        checks=report['checks'],original_unchanged=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','original_stop','schema_version',
        'materialized_count','inventory_count','original_unchanged')}))


if __name__=='__main__':main()
