# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline review of any copied manual session. No robot, route or pose defaults.

Original ROS CDR is hash/frame inspected, NOT fully decoded by this tool.
Display scan timestamps/points and accepted odom snapshots are a sampled mirror;
they are never substituted for calibrated, time-aligned mapping observations.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from inspect_robot_evidence import inspect
from raw_ros_record import inspect_recording


def load(path,limit=64*1024*1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise ValueError('REVIEW_FILE_PATH_OR_SIZE')
    return path.read_text(encoding='utf-8')


def event_summary(rows):
    """Correlate by sequence. PC/robot absolute clocks are never subtracted."""
    events=[r for r in rows if r['kind']=='robot_event']
    robot=[r['data']['event'] for r in events]
    terminal=[e for e in robot if e['kind']=='accepted' and
              e['data']['action'] in {'close','finish_stop','force_stop'}]
    published=[e for e in robot if e['kind']=='published']
    received=[r for r in rows if r['kind']=='input_received']
    piped=[r for r in rows if r['kind']=='pipe_written']
    accepted=[e for e in robot if e['kind']=='accepted']
    finished=next((r for r in reversed(rows) if r['kind']=='robot_finished'),None)
    def last(items):
        if not items:return None
        e=items[-1]
        return {k:e['data'].get(k) for k in ('sequence','action')} | {'t':e['t']}
    stops=[e for e in robot if e['kind']=='idle_confirmed']
    after=[e for e in published if terminal and e['t']>terminal[-1]['t']]
    observations=[r for r in events if r['data']['event']['kind']=='observation']
    excess=max((b['t']-a['t']-(b['data']['event']['t']-a['data']['event']['t'])
                for a,b in zip(observations,observations[1:])),default=0.)
    return {'last_pc_input':last(received),'last_pipe_input':last(piped),
            'last_robot_accepted':last(accepted),'last_robot_published':last(published),
            'last_idle_confirmation':last(stops),
            'terminal_accepted':last(terminal),'published_after_terminal_count':len(after) if terminal else None,
            'pc_inputs_after_finished':[last([r]) for r in received if finished and r['t']>finished['t']],
            'published_by_action':dict(Counter(e['data']['action'] for e in published)),
            'max_observation_receipt_interval_excess_s':max(0.,excess),
            'timing_limit':'Interval difference only, not measured one-way network latency.'}


def review(directory):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('REVIEW_SYMLINK')
    verified=inspect(directory/'robot-evidence')
    if verified['status']!='COMPLETE':
        raise ValueError('EVIDENCE_NOT_COMPLETE:'+','.join(verified['contract_errors']))
    report=json.loads(load(directory/'robot-evidence/report.json'))
    robot_original=[json.loads(line) for line in load(directory/'robot-evidence/session.jsonl').splitlines()]
    rows=[json.loads(line) for line in load(directory/'session.jsonl').splitlines()]
    if not rows or len(rows)>262144:raise ValueError('PC_JOURNAL_COUNT')
    if any(r.get('event_index')!=i or r.get('job_id')!=directory.name or
           r.get('clock_domain')!='pc_monotonic' for i,r in enumerate(rows,1)):
        raise ValueError('PC_JOURNAL_BINDING')
    mirrored=[r['data']['event'] for r in rows if r['kind']=='robot_event']
    # Exact prefix: a failed transport may miss the robot's trailing journal,
    # but may never fabricate, reorder or alter it.
    if mirrored!=robot_original[:len(mirrored)]:raise ValueError('ROBOT_MIRROR_MISMATCH')
    frames=inspect_recording(directory/'robot-evidence/ros-messages.raw')
    timing={}
    for topic in sorted({m['topic'] for m,_ in frames}):
        times=[m['receipt_monotonic_ns'] for m,_ in frames if m['topic']==topic]
        ordered=all(a<=b for a,b in zip(times,times[1:]))
        if not ordered:raise ValueError('RAW_RECEIPT_TIME_ORDER')
        timing[topic]={'count':len(times),'first_receipt_monotonic_ns':times[0],
                       'last_receipt_monotonic_ns':times[-1],
                       'span_s':(times[-1]-times[0])/1e9,
                       'max_receipt_gap_s':max((b-a for a,b in zip(times,times[1:])),default=0)/1e9}
    scans=[e['data']['scan'] for e in robot_original if e['kind']=='scan_preview']
    poses=[e['data']['snapshot']['odom'] for e in robot_original if e['kind']=='navigation'
           and e['data']['snapshot']['odom'] is not None]
    stamps=[s['source_stamp_ns'] for s in scans]
    if any(a>=b for a,b in zip(stamps,stamps[1:])):raise ValueError('SCAN_PREVIEW_TIME_ORDER')
    def pose(p):
        return {k:p[k] for k in ('source_stamp_ns','frame_id','child_frame_id','position_m','quaternion_xyzw')}
    return {'schema':'manual-scan-offline-review-1.0','job_id':directory.name,
            'source_release':report['release_id'],'status':report['status'],
            'reason':report.get('reason'),'raw_verified':True,
            'raw_cdr_message_decode':'NOT_RUN','raw_sha256':report['raw_ros']['sha256'],
            'raw_timeline':timing,'scan_preview_count':len(scans),
            'scan_first_source_stamp_ns':stamps[0] if stamps else None,
            'scan_last_source_stamp_ns':stamps[-1] if stamps else None,
            'odom_snapshot_count':len(poses),'odom_first':pose(poses[0]) if poses else None,
            'odom_last':pose(poses[-1]) if poses else None,
            'commands':event_summary(rows),'mirrored_events':len(mirrored),
            'robot_original_events':len(robot_original),'cleanup_confirmed':report['cleanup_confirmed'],
            'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,
            'mapping_gaps':['FULL_CDR_DECODE_AND_TIME_PAIRING','SENSOR_TO_BASE_EXTRINSICS',
                            'SESSION_LOCAL_ODOM_TO_ROOM_RELOCALIZATION','SCAN_REGISTRATION_ACCEPTANCE'],
            'start_policy':'Relocalize every new session and after unobserved manual repositioning. '
                           'Never reuse an old final pose as a new initial pose.',
            'route_policy':'Recorded commands are observations, not a fixed route or guaranteed motion model.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='New local JSON file; never overwrite originals')
    args=parser.parse_args()
    try:
        result=review(args.session)
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2,allow_nan=False)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print('Offline review failed: '+str(exc)[:200],file=sys.stderr);return 2
    print(json.dumps({'status':'OFFLINE_REVIEW_SAVED','output':str(args.output),
                      'physical_demo_ready':False}));return 0


if __name__=='__main__':raise SystemExit(main())
