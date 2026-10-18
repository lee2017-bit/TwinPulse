# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Saved catalog -> ordinary gateway/input contracts, without HTTP or Isaac.

Credentials are a rejecting test double. This verifies constructor and local
contract admission only, never model capability, benchmark quality or runtime.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys
import tempfile
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.benchmark_protocol import read_json,file_sha,effective_settings_sha
from twinpulse_core import InputRevision,SCENE_TOOL_CATALOG_REVISION
from twinpulse_provider.model_contracts import checked_catalog,catalog_sha,model_supported
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_app.stage_routing import StageRoutingSettings,build_configured_stage_service
from twinpulse_app.settings import NEBIUS_BASE_URL


class RejectingCredential:
    def is_configured(self):return True  # constructor-only test fixture
    def load(self):raise AssertionError('NO_CREDENTIAL_READ_OR_HTTP')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--original-audit',type=Path,required=True)
    args=parser.parse_args();catalog=checked_catalog(read_json(args.catalog))
    if args.output.exists():raise ValueError('EXCLUSIVE_OUTPUT_REQUIRED')
    hashes=read_json(args.original_audit)['original_hashes']
    if any(file_sha(ROOT/p)!=digest for p,digest in hashes.items()):raise ValueError('ORIGINAL_HASH_CHANGED')
    input_hash=file_sha(args.catalog);args.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    with tempfile.TemporaryDirectory(dir=args.output) as temporary,patch.object(socket.socket,'connect',side_effect=AssertionError('NO_NETWORK')):
        settings=SimpleNamespace(path=Path(temporary)/'provider.json')
        value=SimpleNamespace(provider_profile='nebius_token_factory',base_url=NEBIUS_BASE_URL,
            reasoning_effort='medium',accepted_mime_types=('image/png','image/jpeg'))
        registry=SimpleNamespace(settings=settings,lock=RLock(),settings_for_entry=lambda _:value,
            resolve=lambda _:RejectingCredential())
        routes=StageRoutingSettings(registry)
        (settings.path.parent/'stage_model_catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
        observers=[r['model_id'] for r in catalog['models'] if model_supported(catalog,'observer',r['model_id'])]
        planners=[r['model_id'] for r in catalog['models'] if model_supported(catalog,'planner',r['model_id'])]
        if not observers or not planners:raise ValueError('CATALOG_REQUIRES_BOTH_ROLES')
        for stage,models in (('observer',observers),('planner',planners)):
            for model in models:
                pair=dict(observer=model if stage=='observer' else observers[0],planner=model if stage=='planner' else planners[0])
                route={s:dict(key_id='REJECTING_OFFLINE_TEST_DOUBLE',model_id=m,max_output_tokens=20000)
                    for s,m in pair.items()}
                route.update(model_catalog_sha256=catalog_sha(catalog),generation_policy=GenerationPolicy().to_dict())
                routes.save(route,lambda:None)
                service=build_configured_stage_service(registry)
                metadata={**routes.metadata(),'tool_catalog_revision':SCENE_TOOL_CATALOG_REVISION}
                revision=InputRevision.create(prompt='Offline constructor contract only',images=(),generation_settings=metadata,
                    measurement_constraints=(),profile_id='offline-contract')
                if InputRevision.from_dict(revision.to_dict())!=revision:raise AssertionError('INPUT_CONTRACT_CHANGED')
                if service._provider._transport.configs[stage].model_id!=model:raise AssertionError('MODEL_SUBSTITUTED')
                roles={s:dict(provider='nebius',model=m) for s,m in pair.items()}
                roles.update(repair=deepcopy(roles['planner']),critic=deepcopy(roles['observer']))
                rows.append(dict(stage=stage,model_id=model,status='OFFLINE_GATEWAY_INPUT_CONTRACT_PASS',
                    settings_sha256=effective_settings_sha(route,roles)))
    result=dict(status='OFFLINE_CATALOG_CONTRACT_PASS_NOT_BENCHMARK',models=len(catalog['models']),
        observer_contracts=len(observers),planner_contracts=len(planners),rows=rows,HTTP=0,
        actual_model_runtime='NOT_RUN',actual_Isaac='NOT_RUN',robot_calls=0,credential_reads=0,
        originals_checked=len(hashes),originals_unchanged=all(file_sha(ROOT/p)==d for p,d in hashes.items()),
        catalog_input_unchanged=file_sha(args.catalog)==input_hash,whole_demo_pass=False)
    if not result['originals_unchanged'] or not result['catalog_input_unchanged']:raise AssertionError('ORIGINAL_CHANGED')
    with (args.output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps({key:result[key] for key in ('status','models','observer_contracts','planner_contracts','originals_checked','HTTP')}))


if __name__=='__main__':main()
