# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One offline entry point for verified saved scans and room pose candidates.

No SSH, drivers, sensors, motors, deployment, installations or paid providers.
Derived reports are saved exclusively; measured originals remain unchanged.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for relative in ('packages/twinpulse_core/src','packages/twinpulse_app/src','packages/twinpulse_provider/src'):
    sys.path.insert(0,str(ROOT/relative))
from twinpulse_app.bedroom_review import load_bedroom_source
from twinpulse_app.room_localization_review import RoomLocalizationReview
from twinpulse_app.command_broker import BrokerError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id',help='Exact saved project-bound 32-character job ID')
    parser.add_argument('--frame',type=int,default=0,help='Original scan index, not a fixed route')
    parser.add_argument('--goal',type=float,nargs=2,help='Optional Twin XY goal candidate; never movement')
    parser.add_argument('--observation-map',action='store_true',help='Whole-session diagnostic odom endpoint map; independent of photo room')
    parser.add_argument('--compare-model',action='store_true',help='Build independent map then compare multiple keyframes with the unchanged photo room')
    parser.add_argument('--sensor-map-query',metavar='QUERY_JOB_ID',help='Locate three recorded scans in an independent sensor map; no photo or robot position prior')
    args=parser.parse_args();service=RoomLocalizationReview(ROOT,'default')
    try:
        if args.sensor_map_query:
            if args.goal or args.compare_model:raise ValueError('SENSOR_MAP_DIAGNOSTIC_CANNOT_CONVERT_PHOTO_GOALS')
            observed=service.observation_map(args.job_id)
            value=service.locate_sensor_map(args.job_id,observed['revision'],args.sensor_map_query,args.frame)
            best=value['best_diagnostic_hypothesis']
            print(json.dumps({k:value[k] for k in ('job_id','query_job_id','report_id','status','query_frames','alternative_margin_m','reference_retained_scan_count','photo_geometry_used','physical_demo_ready')} |
                {'excluded_reference_count':len(value['holdout']['excluded_reference_frames']),
                 'supported_query_frames':best['supported_query_frames'] if best else 0,
                 'weighted_capped_mean_error_m':best['weighted_capped_mean_error_m'] if best else None},allow_nan=False));return 0
        if args.compare_model:
            if args.goal:raise ValueError('MODEL_COMPARISON_CANNOT_CONVERT_A_ROOM_GOAL')
            observed=service.observation_map(args.job_id)
            value=service.compare_model(load_bedroom_source()[1]['manifest_sha256'],args.job_id,observed['revision'])
            best=value['best_diagnostic_hypothesis']
            print(json.dumps({k:value[k] for k in ('job_id','report_id','revision','status','evaluated_keyframes','searched_frames','geometry_changed','physical_demo_ready')} |
                {'supported_frames':best['supported_frames'] if best else 0,'weighted_capped_mean_error_m':best['weighted_capped_mean_error_m'] if best else None},allow_nan=False));return 0
        if args.observation_map:
            if args.goal:raise ValueError('OBSERVATION_MAP_CANNOT_CONVERT_A_ROOM_GOAL')
            value=service.observation_map(args.job_id)
            result={k:value[k] for k in ('job_id','report_id','revision','status','frame_count','paired_frames',
                'rejected_frames','failures','sampled_hits','timing','photo_geometry_used','physical_demo_ready')}
            result['endpoint_cell_count']=len(value['endpoint_cells']);result['playback_keyframes']=len(value['keyframes'])
            print(json.dumps(result,allow_nan=False));return 0
        revision=load_bedroom_source()[1]['manifest_sha256']
        value=service.analyse(revision,args.job_id,args.frame)
        result={k:value[k] for k in ('job_id','report_id','revision','frame','frame_count','elapsed_s','duration_s',
            'match','timing','diagnostics','goal_candidate_available','robot_pose_room_candidate','physical_demo_ready')}
        if args.goal:
            try:result['goal']=service.goal(revision,value['revision'],value['epoch'],args.goal)
            except BrokerError as exc:result['goal_rejected']={'code':exc.code,'reason':str(exc)}
        print(json.dumps(result,allow_nan=False));return 0
    except (BrokerError,OSError,ValueError,KeyError) as exc:
        print(json.dumps({'status':'OFFLINE_LOCALIZATION_REJECTED','reason':str(exc)[:200],
                          'physical_demo_ready':False}));return 2


if __name__=='__main__':raise SystemExit(main())
