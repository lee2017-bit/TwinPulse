# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only live evidence audit and exact compiler replay, no dispatch or edits to originals."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from scripts.run_ordinary_staged_live_ten import audit_ordinary_run
from twinpulse_provider import GenerationRequest,ImageInput
from twinpulse_provider.nebius_pipeline import ObservationArtifact
from twinpulse_provider.semantic_scene import compile_scene,compiler_diagnosis,review_candidate_quality
from twinpulse_provider import photo_layout
from twinpulse_core.room_items import expand_room_item

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(directory):
    preserved={p:sha(p) for p in directory.rglob('*.json')}
    financial=audit_ordinary_run(directory)
    run=directory/'run-1';browser=read(run/'browser.json')
    generation=browser['conversation']['generation']
    checkpoint=read(run/'runtime/provider-evidence/generation-store/checkpoint'/
                    (generation['progress']['checkpoint_id']+'.json'))['payload']
    photo=run/'1-사진-1.jpg'
    request=GenerationRequest('offline-compiler-replay','Create a digital twin of my bedroom with a bed and desk.',
                             (ImageInput(photo.name,'image/jpeg',photo.read_bytes()),))
    observation=ObservationArtifact.from_mapping(checkpoint['observation'])
    findings=[];original=photo_layout.execute_site_tool_plan
    def inspected(plan,**kwargs):
        floor=next(c.arguments for c in plan.calls if c.tool=='create_floor')
        fx,fy=floor['center_m'];fw,fl=floor['size_m']
        for call in plan.calls:
            if call.tool!='place_room_item':continue
            for obj in expand_room_item(dict(call.arguments)):
                angle=math.radians(obj.transform.rotation_rpy_deg[2]);sx,sy=obj.shape.dimensions_m[:2]
                hx=(abs(math.cos(angle))*sx+abs(math.sin(angle))*sy)/2
                hy=(abs(math.sin(angle))*sx+abs(math.cos(angle))*sy)/2
                x,y=obj.transform.position_m[:2]
                dx=abs(x-fx)+hx-fw/2;dy=abs(y-fy)+hy-fl/2
                if dx>1e-6 or dy>1e-6:
                    findings.append(dict(source_id=call.arguments['id'],generated_part=obj.id,
                        kind=call.arguments['kind'],position_m=obj.transform.position_m,
                        dimensions_m=obj.shape.dimensions_m,excess_x_m=dx,excess_y_m=dy,
                        floor_size_m=[fw,fl],placement=checkpoint['draft']['objects'][call.arguments['id']]['placement']))
        return original(plan,**kwargs)  # Existing guard remains enforced.
    quality=None;checks_complete=False;compiled_sha=None
    try:
        with patch.object(photo_layout,'execute_site_tool_plan',inspected):
            payload,provenance=compile_scene(checkpoint['draft'],observation,request)
        from twinpulse_core import canonical_sha256
        compiled_sha=canonical_sha256(payload);checks_complete=provenance['checks_complete']
        quality=review_candidate_quality(checkpoint['draft'],payload,provenance,observation,request)
        diagnosis=None
    except Exception as error:
        diagnosis=compiler_diagnosis(error,checkpoint['draft'],request)
    if not all(p.is_file() and sha(p)==digest for p,digest in preserved.items()):
        raise AssertionError('Original evidence changed')
    return dict(status='AUDIT_PASS_NOT_GENERATION_PASS',financial=financial,
        generation_error=generation['summary'],operation_id=generation['operation_id'],
        checkpoint_id=generation['progress']['checkpoint_id'],object_count=len(checkpoint['draft']['objects']),
        exact_replay_diagnosis=diagnosis,outside_floor=findings,source_files_unchanged=len(preserved),
        replay_geometry_checks_complete=checks_complete,replay_plan_sha256=compiled_sha,
        replay_observed_quality=quality,
        new_model_calls=0,robot_connections=0,
        second_full_sample='NOT_RUN_SHARED_TEN_CALL_BUDGET_REMAINDER_FOUR_BELOW_SIX_INITIAL_CALLS',
        current_render_review='NOT_REACHED',SIM_Run_Stop='NOT_REACHED',whole_demo_pass=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=audit(args.directory.resolve())
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('status','generation_error','object_count','outside_floor')},ensure_ascii=True))
