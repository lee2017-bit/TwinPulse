# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only saved observer replay. No image/provider/network/geometry execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_core import canonical_sha256
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.observation_instances import checked_observation_instances,expand_observation_instances
from twinpulse_provider.semantic_scene import checked_structure
from twinpulse_provider.scene_contract import role_of
from twinpulse_provider.scene_capacity import SEMANTIC_OBJECT_CAPACITY
from twinpulse_provider import GenerationRequest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.observation.resolve();output=args.output.resolve()
    root=Path(__file__).resolve().parents[1]
    if root/'outputs/photo-paste-capacity-20261012' not in output.parents:
        raise SystemExit('SCOPED_NEW_OUTPUT_REQUIRED')
    if source.is_symlink() or source.stat().st_size>2*1024*1024 or output.exists():
        raise SystemExit('BOUNDED_READ_NEW_REPORT_REQUIRED')
    original=source.read_bytes();record=json.loads(original)
    if record.get('payload_sha256')!=canonical_sha256(record.get('payload')):
        raise SystemExit('OBSERVATION_STORE_INTEGRITY_FAILED')
    raw=record['payload']['observation']
    observation=checked_observation_instances(raw)
    effective,trace=expand_observation_instances(observation)
    objects=[e for e in effective.entities if role_of(e) in {'object','unknown'}]
    # Explicit synthetic inventory validates the existing one-seen-ref design
    # contract. Not a new model response or reconstructed room.
    inventory=[dict(id='item_'+str(index),kind=e['category'],evidence_ref='seen:'+e['id']) for index,e in enumerate(objects)]
    checked=checked_structure(dict(summary='Offline capacity witness; geometry is not reconstructed',
        room=dict(width_m=12,length_m=12,height_m=2.6),inventory=inventory),
        GenerationRequest('capacity-witness','Validate observed inventory'),effective,bound=True)
    unchanged=source.read_bytes()==original and observation.to_dict()==raw
    result=dict(status='PASS' if unchanged else 'FAIL',source_file_sha256=hashlib.sha256(original).hexdigest(),
        source_observation_sha256=observation.sha256,effective_observation_sha256=effective.sha256,
        raw_rows=len(raw['entities']),expanded_objects=len(objects),metadata_rows=len(effective.entities)-len(objects),
        scene_capacity=SEMANTIC_OBJECT_CAPACITY,checked_inventory_count=len(checked['inventory']),
        original_bytes_unchanged=unchanged,unresolved_counts=trace['unresolved_counts'],
        individual_pose_and_support_verified=False,geometry_compiled=False,actual_llm_requests=0,actual_isaac=False,
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in [
            'packages/twinpulse_provider/src/twinpulse_provider/observation_instances.py',
            'packages/twinpulse_provider/src/twinpulse_provider/scene_capacity.py',
            'packages/twinpulse_provider/src/twinpulse_provider/semantic_scene.py']})
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('OBSERVER_CAPACITY_'+result['status']+' objects='+str(len(objects)))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
