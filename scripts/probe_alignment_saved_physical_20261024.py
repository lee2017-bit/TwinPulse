# SPDX-License-Identifier: Apache-2.0
"""One original physical scan, historical estimated seed, no surveyed reference."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.environment_alignment import StructuralMatcher,wall_references,body_points
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
archive=ROOT/'outputs/environment-alignment-20261024-01/archive-worker04/extracted.json';source=ROOT/'outputs/roomplan-lidar-review-20261024-02/environment.json'
a=json.loads(archive.read_bytes());env=json.loads(source.read_bytes());raw=a['frames'][0]['points'];tf=a['extrinsic'];sign=a['angle_sign'];seed=[2.25,.95,0.]
matcher=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]);selection=matcher.structural_indices(raw,seed,tf,sign);started=time.monotonic()
try:match=matcher.fit(body_points(raw,tf,sign),seed,raw_sensor_points=raw,extrinsic=tf,angle_sign=sign,indices=selection['indices'])
except ValueError as error:match=dict(status='HELD',reason=str(error))
result=dict(status='HELD_NO_OPERATOR_REFERENCE_OR_VERIFIED_INITIAL_POSE',scope='OFFLINE_DIAGNOSTIC_NOT_PHYSICAL_REGISTRATION',
    sources=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (archive,source)],
    original_frame=a['frames'][0]['identity'],seed=seed,seed_basis='HISTORICAL_OPERATOR_ESTIMATE_NOT_LOCALIZED',reference_measurement=None,
    extrinsic=tf,angle_sign=sign,tf_basis=a['tf_basis'],height_m=.182,height_basis='NOMINAL_NOT_SURVEYED',selection=selection,match=match,
    elapsed_s=time.monotonic()-started,physical_authority=False,original_physical_poor_fit_unchanged=True)
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(status=result['status'],geometric_status=match['status'])))
