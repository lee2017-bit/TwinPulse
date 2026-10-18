# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Independent synthetic truth evaluator for the actual AD2/AD3 local service.

Does not call a provider, robot, or Isaac. Synthetic fixtures do not establish
real timing, mounting, photos, friction, calibration or position accuracy.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.automatic_demo_service import AutomaticDemoService
from twinpulse_app.automatic_photo_store import load_automatic_room
from twinpulse_core.room_localization import angle
from tests.integration.test_automatic_photo_service import recipe,RaycastSource,GEOMETRY


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for identity,scale in (('room_one',1.),('room_two',1.2)):
        outline,truth=recipe(output,identity,scale)
        folder=output/'projects'/identity
        originals={p.relative_to(folder).as_posix():sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
        nominal=load_automatic_room(output,identity)
        service=AutomaticDemoService(output,identity,source_factory=lambda *a:RaycastSource(identity,outline),geometry_loader=lambda:GEOMETRY)
        try:
            service.start('synthetic-evaluator','a'*32,photo_policy='correct_walls');service.worker.join(30)
            if service.worker.is_alive():raise ValueError('SYNTHETIC_WORKER_TIMEOUT')
            job=service.snapshot('synthetic-evaluator')['job']
            if job['state']!='COMPLETED':raise ValueError(job['error'] or 'SYNTHETIC_FAILED')
            result=job['result']['photo_alignment'];transform=result['room_from_map']
            if result.get('geometry_status')!='AUTO_APPLIED_DERIVED_REVISION':raise ValueError('SYNTHETIC_APPLY_NOT_SUPPORTED')
            # Hidden truth is consulted here, NEVER in the production runner.
            actual={o['id']:o for o in truth};before=nominal['objects'];after=result['effective_objects']
            def geometry_error(objects):
                return sum(math.dist(o['transform']['position_m'][:2],actual[o['id']]['transform']['position_m'][:2])
                           for o in objects if o['kind']=='wall')/6
            pose_error=math.dist(transform[:2],[0,-.7]);yaw_error=abs(angle(transform[2]-.35))
            if pose_error>.10 or yaw_error>math.radians(5):raise ValueError('SYNTHETIC_POSE_REJECTED')
            if geometry_error(after)>=geometry_error(before):raise ValueError('SYNTHETIC_GEOMETRY_NOT_IMPROVED')
            reopened=service.reopen('reader',job['map_id'])
            if reopened['pose_candidate'] is not None or reopened['motion_authorized']:raise ValueError('UNEXPECTED_AUTHORITY')
            service.rollback_photo('synthetic-evaluator',job['job_id'],result['applied_revision'])
            if any(sha256((folder/p).read_bytes()).hexdigest()!=h for p,h in originals.items()):raise ValueError('ORIGINAL_CHANGED')
            rows.append({'project_id':identity,'scale':scale,'map_id':job['map_id'],'photo_report':result['report_revision'],
                         'pose_error_m':pose_error,'yaw_error_rad':yaw_error,
                         'nominal_mean_wall_position_error_m':geometry_error(before),'corrected_mean_wall_position_error_m':geometry_error(after),
                         'nominal_target_wall_error_m':.12,'corrected_target_wall_error_m':math.dist(after[5]['transform']['position_m'][:2],truth[5]['transform']['position_m'][:2]),
                         'fit_error_m':result['fit_error_m'],'validation_before_m':result['validation_before_m'],
                         'validation_after_m':result['validation_after_m'],
                         'fit_sequences':result['fit_sequences'],'validation_sequences':result['validation_sequences'],
                         'source_counts':job['result']['counts'],'originals_unchanged':True,'rollback_verified':True})
        finally:service.close()
    report={'status':'PASS','basis':'SYNTHETIC_RAYCAST_TRUTH_SEPARATE_FROM_PRODUCTION_RUNNER',
            'pose_baseline':'NO_PRIOR_ODOM_TO_ROOM_TRANSFORM_NOT_A_COMPARABLE_METRIC_BASELINE',
            'rooms':rows,'robot_connections':0,'provider_calls':0,'Isaac':'NOT_RUN','physical_demo_ready':False}
    with (output/'verification.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(report))


if __name__=='__main__':main()
