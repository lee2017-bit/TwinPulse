"""Read-only final evidence gate. Never runs an App/model/robot or repairs data."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re

def preview_cache_issues(row):
    """Independently verify classification; never trust the recorder's flag."""
    expected=row.get('expected_preview_cache_miss',[])
    originals=row.get('original_http_errors',[])
    residual=row.get('http_errors',[])
    candidates=[e for e in originals if e.get('code')=='viewport_preview_expired']
    if not expected and not candidates:return []
    bad=['UNPROVEN_PREVIEW_CACHE_CLASSIFICATION']
    if len(expected)!=len(candidates):return bad
    finite=lambda v:type(v) in (int,float) and math.isfinite(v) and v>=0
    seen=set();native_seen=set()
    for item in expected:
        e=item.get('error',{});p=item.get('proof',{})
        match=re.fullmatch(r'/v1/product/viewport/preview/([a-f0-9]{64})',e.get('path',''))
        key=(e.get('path'),e.get('context'),e.get('request_wall_time_ms'))
        if (not match or key in seen or sum(v==e for v in originals)!=1 or e in residual
                or e.get('method')!='GET' or e.get('status')!=409 or e.get('code')!='viewport_preview_expired'
                or e.get('response_body_available') is not True or e.get('request_fault_window') is not True or not re.match(r'^(FAULT INJECTION:|FAULT MATRIX:)',e.get('request_step',''))
                or (e.get('response_body',{}).get('code') or e.get('response_body',{}).get('error',{}).get('code'))!='viewport_preview_expired'
                or not e.get('context') or any(e['context']!=v for v in (e.get('response_context'),e.get('current_context'),row.get('final_fault_context')))
                or not all(finite(e.get(k)) for k in ('request_at','response_at','request_wall_time_ms')) or e['response_at']<e['request_at']):return bad
        seen.add(key)
        starts=[v for v in row.get('fetch_boundaries',[]) if v.get('action')=='after_enable']
        if len(starts)!=1 or not finite(starts[0].get('node_at')) or e['request_at']<starts[0]['node_at'] or row.get('fault_window_held_until_exit') is not True:return bad
        native=[v for v in row.get('viewport_network_timings',[]) if v.get('path')==e['path'] and v.get('method')=='GET' and v.get('context_id')==e['context']
            and v.get('status')==409 and finite(v.get('cdp_wall_time')) and abs(v['cdp_wall_time']*1000-e['request_wall_time_ms'])<=1]
        if len(native)!=1 or not native[0].get('browser_request_id') or not finite(native[0].get('cdp_timestamp')) or native[0]['cdp_timestamp']<starts[0].get('cdp_monotonic_s',math.inf):return bad
        if (native[0]['browser_request_id'] in native_seen or len([v for v in originals if v.get('path')==e['path'] and v.get('method')=='GET' and v.get('context')==e['context']
                and finite(v.get('request_wall_time_ms')) and abs(native[0]['cdp_wall_time']*1000-v['request_wall_time_ms'])<=1])!=1):return bad
        native_seen.add(native[0]['browser_request_id'])
        receipts=row.get('viewport_receipt_trace',{}).get('receipts',[])
        priors=[v for v in receipts if v.get('path')=='/v1/product/viewport' and v.get('status')==200 and v.get('context')==e['context']
            and finite(v.get('at')) and 0<=e['request_at']-v['at']<=2000]
        if not priors:return bad
        prior=priors[-1];f=prior.get('last_frame') or {};a=(row.get('final_fault_recovery') or {}).get('after') or {}
        if (f.get('sha256')!=match[1] or f.get('preview_only') is not True or f.get('physical_authority') is not False
                or not all(f.get(k) for k in ('engine_session_id','stage_epoch','applied_revision')) or not finite(f.get('frame_id'))
                or a.get('live') is not True or not all(finite(a.get(k)) for k in ('at','frame_id','frame_age_ms'))
                or a['at']<=e['response_at'] or a['frame_age_ms']>=1000 or a['frame_id']<=f['frame_id']
                or a.get('stage_epoch')!=f['stage_epoch'] or a.get('scene_revision')!=f['applied_revision']):return bad
        decoded=[v for v in receipts if v.get('status')==200 and v.get('context')==e['context'] and finite(v.get('at')) and e['response_at']<v['at']<=a['at']
            and (v.get('frame') or {}).get('frame_id')==a['frame_id'] and all((v.get('frame') or {}).get(k)==f[k] for k in ('engine_session_id','stage_epoch','applied_revision'))]
        if (not decoded or p.get('classification')!='TYPED_PREVIEW_CACHE_REPLACEMENT_WITH_SAME_CONTEXT_DECODE'
                or p.get('browser_request_id')!=native[0]['browser_request_id'] or p.get('sha256')!=match[1]
                or p.get('context')!=e['context'] or p.get('metadata_at')!=prior['at'] or p.get('decoded_frame_id')!=a['frame_id']):return bad
    return []

REQUIRED={
 'fresh':[
  'Visible Isaac startup readiness before scene operations',
  'Robots menu PC preparation and connection entry while hardware stays OFF',
  'Visible New chat and original robot-containing scene brief',
  'Real provider generation and current Isaac frame',
  'Register two robots through Manage form',
  'SIM menu registrations persist once in the matching chat',
  'Two simultaneous real Isaac SIM connections and independent scan',
  'Non-overlapping dock and visible robot across actual renderer sizes; CSS scaling is not OS DPI proof',
  'Held button moves selected robot; release retains both connections and scans',
  'Actual resize releases held input without replay or session loss',
  'FAULT INJECTION: image delivery gap retains exact decoded image, reports stale, disables camera and recovers',
  'All four normal pointer directions without injected delay',
  'Continuous 60-second held SIM rotation keeps session, sensor and fresh input',
  'FAULT INJECTION: delayed drive dispatch pauses, retains connection, needs fresh input',
  'FAULT MATRIX: 100/250/500/1000ms dispatch gaps preserve session and never replay after confirmed Stop',
  'FAULT INJECTION: delayed chat ACK preserves a newly typed draft; confirmed Stop before closing final fault window',
  'Keyboard hold and control focus loss pause without disconnect',
  'WASD and all arrow key releases; Space stops without replay',
  'Main chat bounded 90 degree command, measured completion',
  'One session full turn with actual simulated scan',
  'LiDAR Off pauses but retains connection; On restarts sensor',
  'Actual obstacle approach stops Beta and fresh reverse escapes',
  'Named chat Stop interrupts finite task without model call or disconnect',
  'Two named finite tasks coexist; visible Stop all confirms both without disconnect',
  'Operation summary opens; raw JSON download is separate',
  'Actual frame anchors and camera transition',
  'Frame-bound selected LiDAR points and optional sparse rays, no localization claim',
  'Missing scene destination fails explicitly; command receipt is not arrival',
  'Destination Stop cancels planning or travel and never replays old route',
  'Actual panel nearest bed destination reaches scene-derived approach with visible receipt',
  'Actual main-chat nearest chair destination reaches scene-derived approach with visible receipt',
  'Actual saved native scan imported via UI and shown by the shared renderer without world alignment',
  'Physical setup shown while robot remains off; no Connect or movement',
  'App-only supervised setup saves offline; all eleven trial paths visible without physical activation',
  'In-App measured-profile editor preserves identity and blocks null or mismatched measurements',
  'Explicit static estimated physical marker in actual Isaac; not tracking or localization',
  'Invalid measured profile rejected by real installed service without fake measured defaults',
  'Visible Exit TwinPulse normal shutdown'],
 'cold':[
  'Robots menu PC preparation and connection entry while hardware stays OFF',
  'Cold restore preserves definitions but no motion authority',
  'Saved menu registration history reopens unchanged without reconnecting',
  'Historical operation reopened and downloaded without reconnecting',
  'Explicitly display saved Twin in current Isaac; no automatic motion restore',
  'Cold new explicit SIM connection; actual backward and right pad buttons',
  'FAULT INJECTION: cold delayed ACK preserves and actually submits the next robot draft before confirmed Stop',
  'App-only supervised setup saves offline; all eleven trial paths visible without physical activation',
  'Visible Exit TwinPulse normal shutdown'],
 'lineage':[
  'Actual installed startup and saved chat open',
  'Explicit saved Twin display in current Isaac',
  'Register and explicitly connect a new SIM operation',
  'Actual finite command and LiDAR observation link to chat and exact scene',
  'Stop all retains original request identity in operation',
  'Actual reviewed scene change and Undo preserve per-event revisions',
  'Project switch closes old operation without relabelling old events',
  'Original physical cold failure exposes exact trial, source provenance and cleanup without reconnect',
  'Original physical recording motion review runs offline with exact IDs and no restored authority',
  'Exit through installed App button'],
 'lineage_cold':[
  'Actual installed startup and saved chat open',
  'Cold history does not restore authority and retains exact Twin reference',
  'Original physical cold failure exposes exact trial, source provenance and cleanup without reconnect',
  'Saved physical motion review cold reopens without Analyze or restored authority',
  'Exit through installed App button']}
ROLES=set(REQUIRED)|{'normal','lifecycle','installation','supplementary','budget'}
REPRODUCTION_EXCLUDED={'Visible New chat and original robot-containing scene brief',
    'Real provider generation and current Isaac frame','Register two robots through Manage form',
    'SIM menu registrations persist once in the matching chat'}
REPRODUCTION_OPEN='Explicitly reopen the original failed SIM scene through the visible UI'
REPRODUCTION_REQUIRED=(set(REQUIRED['fresh'])-REPRODUCTION_EXCLUDED)|{REPRODUCTION_OPEN}

def reproduction_issues(row,release,expected):
    """Independently inspect the whole selected saved-geometry journey."""
    issues=[];steps={s.get('name'):s for s in row.get('steps',[]) if isinstance(s,dict)}
    if row.get('status')!='PASS' or row.get('phase')!='reproduction':issues.append('REPRODUCTION_NOT_WHOLE_PASS')
    if row.get('desktop',{}).get('engine',{}).get('release_id')!=release:issues.append('REPRODUCTION_WRONG_RELEASE')
    for name in sorted(REPRODUCTION_REQUIRED):
        if steps.get(name,{}).get('status')!='PASS':issues.append('REPRODUCTION_MISSING_OR_FAILED_STEP:'+name)
    if any(s.get('status')!='PASS' for s in row.get('steps',[])):issues.append('REPRODUCTION_FAILED_STEP')
    if row.get('http_errors') or row.get('errors') or row.get('page_errors'):issues.append('REPRODUCTION_UNRESOLVED_UI_ERROR')
    if any(not r.get('exiting') and not r.get('fault') for r in row.get('request_failures',[])+row.get('request_failed',[])):
        issues.append('REPRODUCTION_UNCLASSIFIED_REQUEST_FAILURE')
    original=steps.get(REPRODUCTION_OPEN,{}).get('evidence',{})
    connected=steps.get('Two simultaneous real Isaac SIM connections and independent scan',{}).get('evidence')
    if (not isinstance(expected,dict) or not expected.get('project') or not expected.get('scene_revision')
            or row.get('project')!=expected.get('project') or original.get('project')!=expected.get('project')
            or original.get('expected_revision')!=expected.get('scene_revision')
            or not isinstance(connected,list) or len(connected)!=2
            or any(r.get('kind')!='sim' or r.get('connection_state')!='CONNECTED'
                or r.get('source_twin_context',{}).get('scene_revision')!=expected.get('scene_revision') for r in connected)):
        issues.append('REPRODUCTION_ORIGINAL_GEOMETRY_NOT_BOUND')
    normal=REPRODUCTION_REQUIRED-{n for n in REPRODUCTION_REQUIRED if n.startswith('FAULT')}-{'Visible Exit TwinPulse normal shutdown'}
    ordered=[s.get('name') for s in row.get('steps',[])];first=next((i for i,n in enumerate(ordered) if isinstance(n,str) and n.startswith('FAULT')),len(ordered))
    if (set(row.get('normal_steps_before_fault_window',[]))!=normal or set(ordered[:first])!=normal
            or any(n in normal for n in ordered[first:]) or row.get('fault_window_held_until_exit') is not True):
        issues.append('REPRODUCTION_NORMAL_PATH_NOT_SEPARATE_FROM_FAULTS')
    issues+=['REPRODUCTION_'+issue for issue in preview_cache_issues(row)]
    if not body_escape_verified(row):issues.append('REPRODUCTION_BODY_ESCAPE_UNVERIFIED')
    if not scan_display_verified(row):issues.append('REPRODUCTION_SCAN_DISPLAY_UNVERIFIED')
    issues+=['REPRODUCTION_'+issue for issue in validate_display(row)]
    issues+=['REPRODUCTION_'+issue for issue in final_fault_stop_issues(row)]
    for name,angle in [('Main chat bounded 90 degree command, measured completion',math.pi/2),('One session full turn with actual simulated scan',2*math.pi)]:
        delta=steps.get(name,{}).get('evidence',{}).get('delta')
        if type(delta) not in (int,float) or not math.isfinite(delta) or abs(delta-angle)>.01:
            issues.append('REPRODUCTION_ORIGINAL_ANGLE_NOT_PROVEN:'+name)
    return issues

def scan_display_verified(row):
    step=next((s for s in row.get('steps',[]) if s.get('name')=='Frame-bound selected LiDAR points and optional sparse rays, no localization claim'),{})
    evidence=step.get('evidence',{});window=row.get('scan_display_window');samples=row.get('scan_display_observations')
    finite=lambda value:type(value) in (int,float) and -1e15<=value<=1e15 and math.isfinite(value)
    if (not isinstance(window,dict) or window!=evidence.get('scan_display_window')
            or window.get('timeout_ms')!=5000 or not all(finite(window.get(k)) for k in ('started_at_ms','deadline_ms'))
            or window['deadline_ms']-window['started_at_ms']!=5000
            or not isinstance(samples,list) or not 1<=len(samples)<=128 or samples[-1]!=evidence.get('scan_display')):return False
    expected=window.get('expected')
    if not isinstance(expected,dict) or any(not isinstance(expected.get(k),str) or not expected[k] for k in ('robot_id','connection_epoch','motion_epoch')):return False
    for index,scan in enumerate(samples):
        if (not isinstance(scan,dict) or scan.get('frame_live') is not True or scan.get('preview_only') is not False
                or not all(finite(scan.get(k)) for k in ('requested_at_ms','observed_at_ms','received_at_ms','frame_captured_at_ms'))
                or not window['started_at_ms']<=scan['requested_at_ms']<=scan['observed_at_ms']<=scan['received_at_ms']<=window['deadline_ms']
                or not 0<=scan['observed_at_ms']-scan['frame_captured_at_ms']<1000
                or type(scan.get('frame_id')) is not int or scan['frame_id']<=0
                or any(not isinstance(scan.get(k),str) or not scan[k] for k in ('stage_epoch','scene_revision'))):return False
        if scan.get('present') is False and scan.get('visible') is False and scan.get('captured_at_ms') is None and scan.get('age_ms') is None:
            if index==len(samples)-1:return False
            continue
        if (index!=len(samples)-1 or scan.get('present') is not True or scan.get('visible') is not True
                or not all(finite(scan.get(k)) for k in ('captured_at_ms','age_ms'))
                or not 0<=scan['age_ms']<700 or scan['age_ms']!=scan['observed_at_ms']-scan['captured_at_ms']
                or any(scan.get(k)!=expected[k] for k in ('robot_id','connection_epoch','motion_epoch'))
                or type(scan.get('rays_count')) is not int or not 1<=scan['rays_count']<=12
                or type(scan.get('points_count')) is not int or not 1<=scan['points_count']<=90):return False
    return True

def validate_records(records,release,source):
    issues=[]
    for role in sorted(ROLES-records.keys()):issues.append('MISSING_ROLE:'+role)
    for role,steps in REQUIRED.items():
        row=records.get(role,{})
        issues.extend(v+':'+role for v in preview_cache_issues(row))
        if row.get('status')!='PASS':issues.append('RUN_NOT_PASS:'+role)
        if row.get('desktop',{}).get('engine',{}).get('release_id')!=release:issues.append('WRONG_RELEASE:'+role)
        actual={s.get('name'):s for s in row.get('steps',[])}
        for name in steps:
            if actual.get(name,{}).get('status')!='PASS':issues.append('MISSING_OR_FAILED_STEP:'+role+':'+name)
        if any(s.get('status')!='PASS' for s in row.get('steps',[])):issues.append('FAILED_STEP:'+role)
        if row.get('http_errors') or row.get('errors') or row.get('page_errors'):issues.append('UNRESOLVED_UI_ERROR:'+role)
        if any(not r.get('exiting') and not r.get('fault') for r in row.get('request_failures',[])+row.get('request_failed',[])):
            issues.append('UNCLASSIFIED_REQUEST_FAILURE:'+role)
    for role,phase in [('fresh','fresh'),('cold','reopen'),('lineage','run'),('lineage_cold','cold')]:
        if records.get(role,{}).get('phase')!=phase:issues.append('SPLIT_OR_WRONG_PHASE:'+role)
    for first,second in [('fresh','cold'),('lineage','lineage_cold')]:
        if not records.get(first,{}).get('project') or records[first]['project']!=records.get(second,{}).get('project'):
            issues.append('PROJECT_MISMATCH:'+first+':'+second)
    def motion_evidence(role,name):
        return next((s.get('evidence',{}) for s in records.get(role,{}).get('steps',[]) if s.get('name')==name),{})
    analysed=motion_evidence('lineage','Original physical recording motion review runs offline with exact IDs and no restored authority')
    restored=motion_evidence('lineage_cold','Saved physical motion review cold reopens without Analyze or restored authority')
    if (any(not isinstance(analysed.get(k),str) or not analysed[k] or analysed[k]!=restored.get(k) for k in ('operation_id','job_id','input_receipt_sha256','review_sha256','input_segments_sha256'))
            or analysed.get('input_rows')!=restored.get('input_rows') or type(analysed.get('input_rows')) is not int or analysed.get('input_rows',0)<=0
            or analysed.get('analysis_post_count')!=1 or restored.get('analysis_post_count')!=0
            or any(v.get('raw_receipt_sha256_checked') is not True or v.get('physical_activation')!=0 or v.get('physical_motion_verified') is not False for v in (analysed,restored))):
        issues.append('MOTION_REVIEW_COLD_BINDING_OR_AUTHORITY_INVALID')
    fresh=records.get('fresh',{});steps={s.get('name'):s for s in fresh.get('steps',[])}
    if not scan_display_verified(fresh):issues.append('CURRENT_SCAN_DISPLAY_UNVERIFIED')
    if not body_escape_verified(fresh):issues.append('BODY_FRAME_OBSTACLE_ESCAPE_UNVERIFIED')
    normal_names={n for n in REQUIRED['fresh'] if not n.startswith('FAULT') and n!='Visible Exit TwinPulse normal shutdown'}
    before=fresh.get('normal_steps_before_fault_window',[])
    ordered=[s.get('name') for s in fresh.get('steps',[])]
    first_fault=next((i for i,n in enumerate(ordered) if isinstance(n,str) and n.startswith('FAULT')),len(ordered))
    if (set(before)!=normal_names or set(ordered[:first_fault])!=normal_names
            or any(n in normal_names for n in ordered[first_fault:]) or fresh.get('fault_window_held_until_exit') is not True):
        issues.append('ORDINARY_PATH_NOT_SEPARATE_FROM_FINAL_FAULT_WINDOW')
    cold=records.get('cold',{});cold_names=[s.get('name') for s in cold.get('steps',[])]
    cold_move='Cold new explicit SIM connection; actual backward and right pad buttons'
    cold_fault=next((i for i,n in enumerate(cold_names) if isinstance(n,str) and n.startswith('FAULT')),0)
    if (cold_move not in cold.get('normal_steps_before_fault_window',[]) or cold_move not in cold_names[:cold_fault]
            or cold_move in cold_names[cold_fault:] or cold.get('fault_window_held_until_exit') is not True):
        issues.append('COLD_NORMAL_MOTION_NOT_BEFORE_FAULT_WINDOW')
    issues+=final_fault_stop_issues(fresh)
    for name,angle in [('Main chat bounded 90 degree command, measured completion',math.pi/2),
                       ('One session full turn with actual simulated scan',2*math.pi)]:
        delta=steps.get(name,{}).get('evidence',{}).get('delta')
        if type(delta) not in (int,float) or not math.isfinite(delta) or abs(delta-angle)>.01:issues.append('ORIGINAL_ANGLE_NOT_PROVEN:'+name)
    if records.get('lineage',{}).get('requested_command')!='left 90 degrees':issues.append('ORIGINAL_LINEAGE_90_NOT_RUN')
    destination=steps.get('Physical setup shown while robot remains off; no Connect or movement',{}).get('evidence',{})
    if (destination.get('destination_policy_visible') is not True or destination.get('off_destination_send_disabled') is not True
            or destination.get('physical_destination_commands_sent')!=0):
        issues.append('PHYSICAL_DESTINATION_OFF_ENTRY_NOT_PROVEN')
    return issues+nonmotion_record_issues(records,release,source,fresh)

def final_fault_stop_issues(fresh):
    issues=[]
    recovery=fresh.get('final_fault_recovery') or {};a=recovery.get('before') or {};b=recovery.get('after') or {}
    robots=recovery.get('stopped_robots') or [];old_rows=recovery.get('before_stop_robots') or [];old={r.get('robot_id'):r for r in old_rows}
    stop_id=recovery.get('stop_request_id')
    stop_matches=[r for r in fresh.get('fleet_requests',[]) if isinstance(stop_id,str) and stop_id and r.get('request_id')==stop_id and r.get('action')=='stop_all' and r.get('status')==200]
    stop=stop_matches[0] if len(stop_matches)==1 else {}
    finite=lambda v:type(v) in (int,float) and math.isfinite(v)
    if (a.get('live') is not True or b.get('live') is not True or not all(finite(v) for v in (a.get('frame_id'),b.get('frame_id'),a.get('frame_age_ms'),b.get('frame_age_ms')))
            or not 0<=a.get('frame_age_ms',math.inf)<1000 or not 0<=b.get('frame_age_ms',math.inf)<1000 or b.get('frame_id',0)<=a.get('frame_id',0)
            or not a.get('scene_revision') or a.get('scene_revision')!=b.get('scene_revision') or not a.get('stage_epoch') or a.get('stage_epoch')!=b.get('stage_epoch')
            or any(v.get(flag) is not True for v in (a,b) for flag in ('canvas_visible','stop_visible','pad_visible','robot_badge_visible'))
            or any(not finite(v.get('intersection_px2')) or v['intersection_px2']!=0 for v in (a,b))
            or len(robots)!=2 or len({r.get('robot_id') for r in robots})!=2 or len(old_rows)!=2 or len(old)!=2 or not stop
            or any(not all(isinstance(r.get(k),str) and r[k] for k in ('robot_id','operation_id','connection_epoch','motion_epoch'))
                or r.get('control_state')!='PAUSED' or r.get('applied_motion_epoch')!=r.get('motion_epoch')
                or r.get('connection_state')!='CONNECTED' or r.get('lidar_state')!='STREAMING'
                or not all(old.get(r.get('robot_id'),{}).get(k)==r.get(k) for k in ('robot_id','operation_id','connection_epoch'))
                or not isinstance(old.get(r.get('robot_id'),{}).get('motion_epoch'),str) or not old[r['robot_id']]['motion_epoch']
                or old.get(r.get('robot_id'),{}).get('motion_epoch')==r.get('motion_epoch')
                or not any(all(s.get(k)==r.get(k) for k in ('robot_id','operation_id','connection_epoch','motion_epoch')) for s in stop.get('result_robots',[])) for r in robots)):
        issues.append('FINAL_ISOLATED_FAULT_STOP_AND_DISPLAY_RECOVERY_NOT_PROVEN')
    return issues

def nonmotion_record_issues(records,release,source,fresh):
    issues=[]
    normal=records.get('normal',{})
    if (normal.get('status')!='PASS_NORMAL_START_REUSE_DEBUG_OFF' or normal.get('release_id')!=release
            or normal.get('source_sha256')!=source or type(normal.get('ready_wait_ms')) not in (int,float)
            or not 0<normal.get('ready_wait_ms',0)<=120000 or normal.get('debug_listener_count')!=0
            or normal.get('app_listener_count')!=1 or normal.get('repeated_start_same_owner') is not True):issues.append('NORMAL_START_NOT_QUALIFIED')
    install=records.get('installation',{})
    if install.get('status')!='PASS' or install.get('release_id')!=release or install.get('source_manifest_sha256')!=source or install.get('mismatches')!=[] or install.get('capabilities',{}).get('physical_robot') is not True:
        issues.append('INSTALLATION_NOT_EXACT')
    supplementary=records.get('supplementary',{})
    if (supplementary.get('inspection_target')=='FROZEN_CANDIDATE_NOT_INSTALLED' or supplementary.get('status')!='PASS' or supplementary.get('source_sha256')!=source
            or supplementary.get('release_id')!=release or supplementary.get('source_unchanged') is not True
            or {g['name'] for g in supplementary.get('groups',[]) if g.get('status')=='PASS'}!={'lineage-and-pc','native-worker','field','ui','web-build'}):
        issues.append('SUPPLEMENTARY_MISSING_OR_FAILED')
    lifecycle=records.get('lifecycle',{})
    if (lifecycle.get('status')!='PASS' or lifecycle.get('release_id')!=release or lifecycle.get('source_sha256')!=source
            or lifecycle.get('normal_start_launch_id')!=normal.get('launch_id') or lifecycle.get('shutdown_clean') is not True
            or lifecycle.get('restart_ready') is not True or lifecycle.get('restart_shutdown_clean') is not True or not lifecycle.get('restart_launch_id')
            or lifecycle.get('restart_launch_id')==normal.get('launch_id') or lifecycle.get('restart_debug_listener_count')!=0
            or lifecycle.get('restart_app_listener_count')!=1 or lifecycle.get('restart_authenticated_ready') is not True
            or type(lifecycle.get('restart_ready_wait_ms')) not in (int,float)
            or not 0<lifecycle.get('restart_ready_wait_ms',0)<=120000):
        issues.append('NORMAL_LIFECYCLE_NOT_QUALIFIED')
    if records.get('budget',{}).get('within_approved_total') is not True:issues.append('BUDGET_UNCONFIRMED_OR_EXCEEDED')
    registration=records.get('fresh',{}).get('registration_history')
    if (not isinstance(registration,dict) or registration.get('project_id')!=records.get('fresh',{}).get('project')
            or len(registration.get('entries',[]))!=2 or registration!=records.get('cold',{}).get('registration_history')):
        issues.append('REGISTRATION_CHAT_RESTORE_NOT_PROVEN')
    issues+=validate_display(fresh)
    return issues

def body_escape_verified(fresh):
    """Independently recompute from original recorded poses, not asserted distances."""
    try:
        evidence=next(s['evidence'] for s in fresh['steps'] if s['name']=='Actual obstacle approach stops Beta and fresh reverse escapes')
        a,b,c=(evidence[k] for k in ('before','stopped','escaped'))
        if any(not isinstance(row,dict) for row in (a,b,c)):return False
        for key in ('robot_id','operation_id','connection_epoch'):
            if not isinstance(a.get(key),str) or not a[key] or b.get(key)!=a[key] or c.get(key)!=a[key]:return False
        for row in (a,b,c):
            pose=row['pose']
            if not isinstance(pose,dict):return False
            p=pose['position_m']
            if (pose.get('frame_id')!='isaac_world' or pose.get('source')!='isaac_usd_kinematic' or pose.get('aligned') is not True
                    or not isinstance(p,list) or len(p)!=3
                    or any(type(n) not in (int,float) or not -1e6<=n<=1e6 or not math.isfinite(n) for n in p)):return False
        if (b.get('reason')!='OBSTACLE_STOP' or c.get('reason')!='TASK_COMPLETED'
                or not isinstance(c.get('command'),dict) or c['command'].get('state')!='COMPLETED'):return False
        for left,right,direction,minimum in ((a,b,1,.05),(b,c,-1,.09)):
            p,q=left['pose']['position_m'],right['pose']['position_m'];dx,dy=q[0]-p[0],q[1]-p[1]
            forward=dx*math.cos(p[2])+dy*math.sin(p[2]);lateral=-dx*math.sin(p[2])+dy*math.cos(p[2])
            yaw=math.atan2(math.sin(q[2]-p[2]),math.cos(q[2]-p[2]))
            if (forward<=minimum if direction==1 else -forward<minimum) or abs(lateral)>.005 or abs(yaw)>.01:return False
        return True
    except (KeyError,StopIteration,TypeError,ValueError,OverflowError):return False


def validate_display(fresh):
    """Actual recorded geometry/current receipts, not pose-only readiness."""
    issues=[];steps={s.get('name'):s for s in fresh.get('steps',[])}
    layout=steps.get('Non-overlapping dock and visible robot across actual renderer sizes; CSS scaling is not OS DPI proof',{}).get('evidence',{}).get('rows',[])
    if len(layout)!=5:issues.append('DISPLAY_LAYOUT_MATRIX_MISSING')
    bodies=steps.get('Non-overlapping dock and visible robot across actual renderer sizes; CSS scaling is not OS DPI proof',{}).get('evidence',{}).get('bodySelections',[])
    if (len(bodies)!=2 or {r.get('name') for r in bodies}!={'Alpha','Beta'} or
            any(r.get('bodyHit') is not True or r.get('origin_marker_count')!=0 or
                any(type(r.get(k)) not in (int,float) or not 0<=r[k]<=1 for k in ('label_under_body_error_px','label_horizontal_error_px')) for r in bodies)):
        issues.append('CURRENT_MODEL_BODY_SELECTION_NOT_PROVEN')
    off=steps.get('LiDAR Off pauses but retains connection; On restarts sensor',{}).get('evidence',{}).get('off',{})
    if off.get('overlay_count')!=0 or off.get('sensor_state')!='OFF' or off.get('observed_ms',0)<900:
        issues.append('SENSOR_OFF_OVERLAY_REMOVAL_NOT_PROVEN')
    targets=[(1920,1080),(1366,768),(1093,614),(911,512),(1600,900)]
    sizes=[(r.get('window',{}).get('width',0),r.get('window',{}).get('height',0)) for r in layout]
    if len(set(sizes))!=5 or any(not any(abs(w-x)<=1 and abs(h-y)<=1 for w,h in sizes) for x,y in targets):issues.append('DISPLAY_LAYOUT_SIZES_NOT_PROVEN')
    displays=fresh.get('display_samples',[])
    if len(displays)<80:issues.append('CONTINUOUS_DISPLAY_SAMPLES_MISSING')
    for value in layout+displays:
        age=value.get('frame_age_ms');bounds=value.get('robot_bounds')
        if (value.get('live') is not True or type(age) not in (int,float) or not math.isfinite(age) or not 0<=age<1000
                or type(value.get('frame_id')) not in (int,float) or not math.isfinite(value['frame_id'])
                or not value.get('canvas_visible') or type(value.get('canvas',{}).get('height')) not in (int,float)
                or not math.isfinite(value.get('canvas',{}).get('height',0)) or value.get('canvas',{}).get('height',0)<150
                or value.get('intersection_px2')!=0 or not value.get('stop_visible') or not value.get('pad_visible')
                or not value.get('robot_badge_visible') or not isinstance(bounds,list) or len(bounds)!=4
                or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in bounds)
                or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]):
            issues.append('INVALID_OR_OBSCURED_CURRENT_DISPLAY');break
        if (value.get('origin_marker_count')!=0 or any(type(value.get(k)) not in (int,float) or not 0<=value[k]<=1
                for k in ('label_under_body_error_px','label_horizontal_error_px'))):
            issues.append('ROBOT_LABEL_NOT_ATTACHED_TO_BODY');break
    if displays and displays[-1].get('frame_id',0)<=displays[0].get('frame_id',0):issues.append('DECODED_DISPLAY_NOT_ADVANCING')
    if (displays and (not displays[0].get('scene_revision') or not displays[0].get('stage_epoch')
            or any((r.get('scene_revision'),r.get('stage_epoch'))!=(displays[0].get('scene_revision'),displays[0].get('stage_epoch')) for r in displays)
            or any(type(r.get('at')) not in (int,float) or not math.isfinite(r['at']) for r in displays)
            or any(b.get('at',0)<=a.get('at',0) or b.get('frame_id',0)<a.get('frame_id',0) for a,b in zip(displays,displays[1:])))):
        issues.append('DISPLAY_TIME_FRAME_OR_LINEAGE_INVALID')
    hold=fresh.get('sustained_hold_observations',[])
    hold_step=steps.get('Continuous 60-second held SIM rotation keeps session, sensor and fresh input',{})
    if len(hold)<80 or hold[-1].get('at',0)-hold[0].get('at',0)<59000 or hold_step.get('elapsed_ms',0)<60000:
        issues.append('CONTINUOUS_60S_DISPLAY_INTERVAL_MISSING')
    else:
        covered=[r for r in displays if hold[0]['at']-1000<=r.get('at',0)<=hold[-1]['at']+1000]
        if (len(covered)<80 or covered[0]['at']>hold[0]['at']+1000 or covered[-1]['at']<hold[-1]['at']-1000
                or any(b['at']-a['at']>1000 for a,b in zip(covered,covered[1:]))):issues.append('CONTINUOUS_HOLD_DISPLAY_NOT_COVERED')
        elif covered[-1]['frame_id']<=covered[0]['frame_id']:issues.append('CONTINUOUS_HOLD_DECODED_FRAME_NOT_ADVANCING')
    return issues

def physical_review_issues(manifest):
    review=manifest.get('physical_readiness_review')
    if not isinstance(review,dict):return ['MISSING_CURRENT_PHYSICAL_READINESS_REVIEW']
    if (review.get('schema') not in {'physical-readiness-review-1.0','physical-readiness-review-1.1','physical-readiness-review-1.2'} or not isinstance(review.get('unresolved'),list)
            or any(not isinstance(code,str) or not code for code in review['unresolved'])
            or not isinstance(review.get('evidence'),list) or not review['evidence']):return ['INVALID_PHYSICAL_READINESS_REVIEW']
    if review.get('unresolved'):
        return ['KNOWN_PHYSICAL_BLOCKER:'+str(code) for code in review['unresolved']]
    if review.get('schema') in {'physical-readiness-review-1.1','physical-readiness-review-1.2'}:
        # Outcomes to be measured in the first supervised test are not a
        # prerequisite to BEGIN that test. Unknown software failures still veto.
        if (review.get('scope')!='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION'
                or review.get('observation_policy')!='SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1'
                or review.get('not_run')!=['PI_LOAD_AND_STORAGE','PHYSICAL_STOPPING_AND_DRIVING','WORLD_ALIGNMENT']
                or review.get('protocol_status')!='UNKNOWN_BYTES_PRESERVED_NOT_DECODED'
                or not isinstance(review.get('replay'),dict)):
            return ['INVALID_SUPERVISED_TEST_ENTRY_REVIEW']
    if review.get('status')!='SOFTWARE_NO_KNOWN_BLOCKER':return ['PHYSICAL_READINESS_REVIEW_NOT_QUALIFIED']
    return []


def replay_review_issues(manifest,root):
    review=manifest.get('physical_readiness_review') or {}
    if review.get('schema') not in {'physical-readiness-review-1.1','physical-readiness-review-1.2'}:return []
    ref=review.get('replay') or {};path=(root/ref.get('path','')).resolve()
    if not path.is_relative_to(root.resolve()):return ['INVALID_CONTROL_REPLAY_PATH']
    try:
        raw=path.read_bytes();value=json.loads(raw)
        if sha256(raw).hexdigest()!=ref.get('sha256'):return ['CONTROL_REPLAY_SHA_MISMATCH']
        if (value.get('status')!='PASS' or value.get('classification')!='OFFLINE_SAVED_INPUT_NOT_PI_OR_PHYSICAL_ACCEPTANCE'
                or value.get('raw_sha256')!='7a50ff3fec3cb24e500faead1e5b5d0caeea8b0654ad2db615aa491ebaa21522'
                or value.get('raw_bytes')!=8336993 or value.get('chunks')!=51791
                or value.get('checksum_errors')!=0 or value.get('pending_bytes')!=0
                or value.get('frames')!=6081 or value.get('strict_incomplete')!=202
                or value.get('retained_complete_observations')!=201 or value.get('unknown_bytes')!=2259
                or not 0<value.get('held_age_max_ms',0)<=350):return ['CONTROL_REPLAY_NOT_QUALIFIED']
        if value.get('directions')!={name:{'OBSERVATION_ACCEPTED':6080,'FIELD_COMPLETE_NATIVE_RING_REQUIRED':1}
                for name in ('forward','backward','left','right')}:return ['CONTROL_REPLAY_DIRECTIONS_NOT_QUALIFIED']
        expected={'packages/twinpulse_robot_safety/'+name+'.py' for name in ('native_stream','field_tests','fleet_control')}
        if set(value.get('source_sha256',{}))!=expected:return ['CONTROL_REPLAY_SOURCE_MISSING']
        for name,digest in value.get('source_sha256',{}).items():
            source=(Path(__file__).resolve().parents[1]/name).resolve()
            if not source.is_relative_to(Path(__file__).resolve().parents[1]) or sha256(source.read_bytes()).hexdigest()!=digest:
                return ['CONTROL_REPLAY_SOURCE_CHANGED']
        if len(value.get('source_sha256',{}))!=3:return ['CONTROL_REPLAY_SOURCE_MISSING']
    except (OSError,ValueError,TypeError):return ['CONTROL_REPLAY_UNREADABLE']
    return []

def shutdown_review_issues(manifest,root,records,release,source):
    """Read the exact handoff and owner observations, not an aggregate PASS.

    Inner worker joins and natural root exit are distinct from Job descendant
    reaping. This is an acceptance evidence check, not a new motion interlock.
    """
    review=manifest.get('physical_readiness_review') or {}
    if review.get('schema')!='physical-readiness-review-1.2':return ['CURRENT_SHUTDOWN_CONTRACT_REQUIRED']
    def load(ref):
        if not isinstance(ref,dict):raise ValueError('REFERENCE_MISSING')
        path=(root/ref.get('path','')).resolve()
        if not path.is_relative_to(root.resolve()):raise ValueError('PATH_OUTSIDE_EVIDENCE')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=ref.get('sha256'):raise ValueError('SHA_MISMATCH')
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('OBJECT_REQUIRED')
        return value
    try:contract=load(review.get('shutdown_contract'))
    except (OSError,ValueError,TypeError):return ['SHUTDOWN_CONTRACT_UNREADABLE_OR_SHA_MISMATCH']
    if (contract.get('schema')!='owned-shutdown-contract-1.0' or contract.get('release_id')!=release
            or contract.get('source_sha256')!=source):return ['SHUTDOWN_CONTRACT_WRONG_RELEASE']
    expected={role:(records.get(role,{}).get('desktop',{}).get('engine',{}).get('launch_id'))
              for role in ('fresh','cold','lineage','lineage_cold')}
    expected.update(normal=records.get('normal',{}).get('launch_id'),restart=records.get('lifecycle',{}).get('restart_launch_id'))
    try:
        reproduction=load(review.get('reproduction'))
        if reproduction.get('status')!='PASS' or reproduction.get('desktop',{}).get('engine',{}).get('release_id')!=release:
            return ['SHUTDOWN_REPRODUCTION_NOT_CURRENT_PASS']
        expected['reproduction']=reproduction.get('desktop',{}).get('engine',{}).get('launch_id')
    except (OSError,ValueError,TypeError,AttributeError):return ['SHUTDOWN_REPRODUCTION_UNREADABLE_OR_SHA_MISMATCH']
    branches=contract.get('branches')
    if not isinstance(branches,dict) or set(branches)!=set(expected):return ['SHUTDOWN_REQUIRED_BRANCH_MISSING']
    issues=reproduction_issues(reproduction,release,review.get('reproduction_expected'))
    if len(set(expected.values()))!=len(expected) or not all(expected.values()):issues.append('SHUTDOWN_LAUNCH_IDENTITIES_MISSING_OR_DUPLICATE')
    for branch,launch in expected.items():
        try:
            refs=branches[branch]
            start=load(refs.get('start'));engine=load(refs.get('engine_result'))
            owner=load(refs.get('owner_exit'));cleanup=load(refs.get('cleanup'))
            if (not launch or start.get('launch_id')!=launch or engine.get('launch_id')!=launch or owner.get('launch_id')!=launch or cleanup.get('launch_id')!=launch
                    or type(start.get('owner_pid')) is not int or start['owner_pid']<=0
                    or owner.get('owner_pid')!=start['owner_pid'] or cleanup.get('owner_pid')!=start['owner_pid']):
                issues.append('SHUTDOWN_LAUNCH_BINDING_INVALID:'+branch)
            joins=(engine.get('viewport_phase_diagnostics') or {}).get('join_status') or {}
            app=engine.get('app_close') or {};scan=joins.get('scan_worker') or {}
            if (engine.get('error') or engine.get('error_type') or engine.get('traceback')
                    or engine.get('cleanup_status')!='PRE_CLOSE_COMPLETE' or engine.get('cleanup_errors')!=[]
                    or app.get('state') not in {'PREPARED_FOR_ISAAC_CLOSE','RETURNED'} or app.get('external_confirmation_required') is not True
                    or any(joins.get(k) is not False for k in ('viewport_alive','fleet_alive','diagnostic_alive'))
                    or bool(joins.get('cleanup_errors'))
                    or scan.get('worker_alive') is not False or scan.get('cleanup_errors')!=[]):
                issues.append('SHUTDOWN_INNER_HANDOFF_NOT_COMPLETE:'+branch)
            if (owner.get('schema')!='owned-exit-observations-1.0' or owner.get('evidence_complete') is not True
                    or not owner.get('execution_id') or cleanup.get('exit_evidence_complete') is not True
                    or cleanup.get('owned_processes_stopped') is not True
                    or owner.get('roles')!=cleanup.get('process_exit_observations')):
                issues.append('SHUTDOWN_OWNER_EVIDENCE_INCOMPLETE:'+branch)
            roles=owner.get('roles') or {}
            if set(roles)!={'engine','backend'}:issues.append('SHUTDOWN_OWNED_ROLES_MISSING:'+branch)
            for name in ('engine','backend'):
                r=roles.get(name) or {}
                if (r.get('role')!=name or type(r.get('pid')) is not int or r.get('pid',0)<=0
                        or r.get('ownership')!='HELD_POPEN_PROCESS_HANDLE' or r.get('evidence_complete') is not True or r.get('errors')!=[]
                        or r.get('root_disposition') not in {'ALREADY_EXITED','EXITED_DURING_GRACE'} or r.get('return_code')!=0
                        or r.get('job_close_requested') is not True or r.get('job_observation')!='OBSERVED'
                        or type(r.get('job_active_before_close')) is not int or r.get('job_active_before_close',-1)<0):
                    issues.append('SHUTDOWN_ROOT_FORCED_UNKNOWN_OR_JOB_UNOBSERVED:'+branch+':'+name)
        except (OSError,ValueError,TypeError,AttributeError):issues.append('SHUTDOWN_BRANCH_UNREADABLE_OR_SHA_MISMATCH:'+branch)
    return issues

def load_evidence(manifest,root):
    records={};receipts=[];issues=[]
    for entry in manifest.get('evidence',[]):
        role=entry.get('role');relative=entry.get('path','');path=(root/relative).resolve()
        if role not in ROLES or role in records or not path.is_relative_to(root.resolve()):
            issues.append('INVALID_OR_DUPLICATE_REFERENCE:'+str(role));continue
        try:
            raw=path.read_bytes();digest=sha256(raw).hexdigest()
            if digest!=entry.get('sha256'):issues.append('EVIDENCE_HASH_MISMATCH:'+role);continue
            records[role]=json.loads(raw);receipts.append(dict(role=role,path=relative,sha256=digest))
        except (OSError,ValueError):issues.append('UNREADABLE_EVIDENCE:'+str(role))
    return records,receipts,issues

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.manifest.resolve().parent
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    records,receipts,issues=load_evidence(manifest,root)
    active=json.loads((Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json').read_text(encoding='utf-8-sig'))
    release=active['release_id'];source=active['source_manifest_sha256']
    if manifest.get('release_id')!=release or manifest.get('source_sha256')!=source:issues.append('NOT_ACTIVE_INSTALLED_RELEASE')
    issues+=validate_records(records,release,source)
    software_issues=list(issues)
    issues+=physical_review_issues(manifest)
    issues+=replay_review_issues(manifest,root)
    issues+=shutdown_review_issues(manifest,root,records,release,source)
    result=dict(schema='robot-focused-evidence-gate-1.0',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        status='NOT_READY' if issues else 'READY_FOR_SUPERVISED_POWERED_TEST',release_id=release,source_sha256=source,
        issues=issues,software_status='FAIL' if software_issues else 'PASS_SCOPED_SIM_AND_PC',
        physical_readiness_review=manifest.get('physical_readiness_review'),evidence=receipts,physical_outcomes='NOT_RUN_ROBOT_OFF',
        limitation='Readiness is permission to begin the supervised test sequence, not permission to bypass live guards or a claim of physical success. Known blocking software faults veto; Pi load/braking/alignment are separate NOT_RUN outcomes. Unknown protocol bytes remain unknown.')
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False));return 1 if issues else 0
if __name__=='__main__':raise SystemExit(main())
