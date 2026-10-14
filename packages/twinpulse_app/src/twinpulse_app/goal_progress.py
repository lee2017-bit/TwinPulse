# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded English worker receipt summaries, not localization authority."""
import math
import re

TERMINAL={'MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'}


def code(value):
    return value if type(value) is str and re.fullmatch('[A-Z0-9_]{1,120}',value) else 'UNAVAILABLE'


def describe_goal_job(job, *, terminal=False):
    phase=code(job.get('state'));elapsed=job.get('elapsed_s')
    duration=(f'{elapsed:.1f}s' if type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=0 else 'unavailable')
    prefix=f'Goal mission · {phase} · elapsed {duration}. '
    if terminal:
        status='failed' if phase=='FAILED' or job.get('cleanup_error') or job.get('report_error') else 'completed'
        content=prefix+'Worker result observed; previous pose and scan are historical, not a current robot location. '
        for field,label in (('error','Cause'),('error_stage','Stage'),('cleanup_error','Cleanup cause'),('report_error','Report cause')):
            if job.get(field):content+=label+': '+code(job[field])+'. '
        from twinpulse_core.cleanup_diagnostics import checked_notes
        for note in checked_notes(job.get('native_cleanup_errors',[])):
            content+=f'Native cleanup {note["stage"]}: {note["code"]} ({note["error_type"]}). '
        cleanup=('PENDING' if job.get('worker_active') else 'ERROR' if job.get('cleanup_error') else 'WORKER_FINISHED')
        content+=f'Cleanup: {cleanup} (not physical stop confirmation). Report: {code(job.get("report_status"))}. No automatic restart.'
        return content,status
    if phase=='STOPPING':
        return prefix+'Stop requested; worker cleanup is pending. No new route or automatic resume.','pending'
    visual=job.get('visual') or {};age=job.get('visual_age_s');pose=visual.get('pose_room')
    recent=(job.get('worker_active') is True and phase in {'DRIVING','REPLANNING','ARRIVED'}
            and visual.get('state') in {'DRIVING','REPLANNING','ARRIVED'}
            and type(age) in (int,float) and math.isfinite(age) and 0<=age<=.2
            and type(pose) is list and len(pose)==3
            and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=12.1 for v in pose))
    if recent:
        content=(f'Latest worker frame: room x={pose[0]:.2f}m, y={pose[1]:.2f}m, heading={pose[2]:.2f}rad. '
                 f'Scan returns: {len(visual.get("scan_room") or [])}. ')
        goal=visual.get('goal_room')
        if (type(goal) is list and len(goal)==2
                and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=12.1 for v in goal)):
            content+=f'Straight-line goal separation: {math.hypot(goal[0]-pose[0],goal[1]-pose[1]):.2f}m (not remaining route length). '
    else:content='Current room pose/scan unavailable; no previous frame is substituted. '
    trace=visual.get('trajectory_room') or []
    if (type(trace) is list and 2<=len(trace)<=512
            and all(type(p) is list and len(p)==3 and all(type(v) in (int,float) and math.isfinite(v) for v in p) for p in trace)):
        distance=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(trace,trace[1:]))
        content+=f'Recorded trace distance: {distance:.2f}m (bounded history). '
    reason=next((e.get('data',{}).get('decision',{}).get('reason',e.get('data',{}).get('reason')) for e in reversed(job.get('events') or [])
                 if e.get('kind')=='mission_decision'),None)
    content+=f'Last decision: {code(reason)}. '
    telemetry=job.get('telemetry') if job.get('telemetry_status')=='RECENT_WORKER_RECEIPT' else None
    if telemetry:
        battery=telemetry.get('battery');waypoint=telemetry.get('next_waypoint')
        content+=(f'Latest battery receipt: {battery["voltage_v"]:.2f} V / estimated {battery["estimated_percent"]:.1f}% (not measured capacity). '
                  if battery else 'Current battery unavailable. ')
        content+=(f'Next waypoint {waypoint["index"]+1}/{waypoint["count"]}: ({waypoint["xy_room"][0]:.2f}, {waypoint["xy_room"][1]:.2f}) m. '
                  if waypoint else 'Current next waypoint unavailable. ')
        content+='Motor load measurement unsupported. '
    else:content+='Next waypoint and live battery: unavailable in this receipt. '
    provenance=code(visual.get('provenance'))
    return prefix+content+f'Source: {provenance}. Transport delay is unmeasured; this summary grants no motion authority.','pending'
