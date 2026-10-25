# SPDX-License-Identifier: Apache-2.0
"""Original saved SIM acquisition; ground truth is validation only, never fit input."""
import hashlib,json,math,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.environment_alignment import StructuralMatcher,body_points,wall_references
from twinpulse_core.room_localization import compose
base=ROOT/'outputs/environment-photo-live-20261024-01';out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
sources=[base/'adopt04/result.json',base/'sim05/result.json']
env=json.loads(sources[0].read_bytes())['preview']['operation']['tool_call']['arguments']['environment']
scan=json.loads(sources[1].read_bytes())['scan']['scan'];raw=scan['points'];tf=[-.032,0,0];seed=[1.45,1.05,.1]
matcher=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]);selection=matcher.structural_indices(raw,seed,tf)
started=time.monotonic();match=matcher.fit(body_points(raw,tf),seed,raw_sensor_points=raw,extrinsic=tf,indices=selection['indices']);elapsed=time.monotonic()-started
sensor=scan['sensor_xy_yaw_world'];truth=[sensor[0]-math.cos(sensor[2])*tf[0],sensor[1]-math.sin(sensor[2])*tf[0],sensor[2]]
known_wrong=[1.274738,1.29119,0.];allpoints=body_points(raw,tf);ids=selection['indices']
compare=[dict(name=name,body_pose=pose,**matcher.validation(allpoints,ids,pose,raw,tf)) for name,pose in [('known_sim_truth',truth),('previous_nearest_face_wrong_solution',known_wrong),('new_fit',match['body_pose'])]]
result=dict(scope='SINGLE_SAVED_SIM_VALIDATION_NOT_LIVE_OR_PHYSICAL_ACCEPTANCE',sources=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources],
    selection=selection,match=match,comparison=compare,fit_elapsed_s=elapsed,ground_truth_body_pose=truth,
    translation_error_m=math.dist(truth[:2],match['body_pose'][:2]),yaw_error_rad=abs(truth[2]-match['body_pose'][2]),
    physical_authority=False,original_physical_poor_fit_unchanged=True)
result['status']='PASS_SAVED_SIM_SCOPE' if result['translation_error_m']<.02 and result['yaw_error_rad']<.02 and match['status']=='GEOMETRIC_REVIEW' and not matcher.passes(compare[1]) else 'FAIL'
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:result[k] for k in ('status','translation_error_m','yaw_error_rad','fit_elapsed_s')}))
raise SystemExit(0 if result['status'].startswith('PASS') else 1)
