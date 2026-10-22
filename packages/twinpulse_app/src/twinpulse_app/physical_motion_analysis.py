# SPDX-License-Identifier: Apache-2.0
"""Offline, unqualified sensor comparison. Never imports a device/controller.

Only the named worker calls this module. Original receipt/segments are read-only;
neither wheel inputs nor an expected motion seed the independent scan fit.
"""
import base64
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import time

from .physical_live_history import MAX_LINE, _json
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_BYTES, EVENT_ARCHIVE_SEGMENTS

SCHEMA='physical-motion-review-1.0'
MAX_SCANS=12000
MAX_WINDOWS=64
# Coverage of the saved 5Hz scan summaries only, NOT a robot safety parameter.
PAIR_GAP_S=.5
EDGE_GAP_S=.3

def finite(v):return type(v) in (int,float) and math.isfinite(v)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def bounded_file(path,limit):
    if path.is_symlink() or path.stat().st_size>limit:raise ValueError('REVIEW_FILE_BOUND')
    return path.read_bytes()

def read_archive(directory,operation,project,deadline):
    directory=Path(directory)
    if directory.is_symlink() or directory.name!=operation:raise ValueError('REVIEW_DIRECTORY')
    raw=bounded_file(directory/'receipt.json',128*1024);receipt=_json(raw)
    if not isinstance(receipt,dict):raise ValueError('REVIEW_RECEIPT')
    segments=receipt.get('segments')
    if receipt.get('schema')!='physical-live-recording-1.0' or not isinstance(segments,list) or not 1<=len(segments)<=EVENT_ARCHIVE_SEGMENTS:
        raise ValueError('REVIEW_RECEIPT')
    scans={};poses={};terminal={};pubs=[];pauses=[];fields=[];sources=defaultdict(bytearray);source_error=False;export={};rejected_scans=defaultdict(int);invalid_scan_times=[]
    first=None;seq=0;count=size=0;seen=set()
    for segment in segments:
        name=segment.get('path')
        if not isinstance(name,str) or not re.fullmatch(r'events-\d{5}\.jsonl',name) or name in seen:raise ValueError('REVIEW_MEMBER')
        seen.add(name);path=directory/name
        if path.is_symlink() or path.resolve().parent!=directory.resolve():raise ValueError('REVIEW_MEMBER')
        h=hashlib.sha256();member_size=0
        with path.open('rb') as stream:
            while True:
                if time.monotonic()>deadline:raise ValueError('REVIEW_DEADLINE')
                line=stream.readline(MAX_LINE+1)
                if not line:break
                if len(line)>MAX_LINE or not line.endswith(b'\n'):raise ValueError('REVIEW_LINE')
                h.update(line);member_size+=len(line);count+=1;size+=len(line)
                if size>EVENT_ARCHIVE_BYTES or count>2_000_000:raise ValueError('REVIEW_ARCHIVE_BOUND')
                e=_json(line)
                if not isinstance(e,dict):raise ValueError('REVIEW_EVENT')
                if first is None:
                    first=e
                    if e.get('schema') not in {'physical-live-pc-start-1.0','physical-live-pc-start-2.0'} or e.get('operation_id')!=operation or e.get('project_id')!=project:
                        raise ValueError('REVIEW_START_BINDING')
                    continue
                if e.get('schema') in {'physical-live-pc-start-1.0','physical-live-pc-start-2.0'}:raise ValueError('REVIEW_DUPLICATE_START')
                if not str(e.get('schema','')).startswith('physical-live-event-'):continue
                if any(e.get(k)!=first.get(k) for k in ('operation_id','project_id','robot_id','connection_epoch')):raise ValueError('REVIEW_EVENT_BINDING')
                context=first.get('source_twin_context')
                if context is not None and e.get('source_twin_context_id')!=context.get('context_id'):raise ValueError('REVIEW_TWIN_BINDING')
                if type(e.get('sequence')) is not int or e['sequence']!=seq+1 or not finite(e.get('robot_monotonic_s')):raise ValueError('REVIEW_SEQUENCE_CLOCK')
                seq=e['sequence'];at=e['robot_monotonic_s'];d=e.get('data');kind=e.get('kind')
                if not isinstance(d,dict):raise ValueError('REVIEW_EVENT_DATA')
                m=d.get('motion_observation')
                if isinstance(m,dict) and m.get('state')=='ENDED':
                    if m.get('operation_id')!=operation or m.get('robot_id')!=first['robot_id'] or m.get('source_twin_context_id')!=(context or {}).get('context_id'):
                        raise ValueError('REVIEW_TERMINAL_BINDING')
                    key=(m.get('request_id'),m.get('motion_epoch'),m.get('first_sample_s'))
                    if any(v is None for v in key):raise ValueError('REVIEW_TERMINAL_IDENTITY')
                    terminal[key]=deepcopy(m)
                if kind=='scan':
                    if d.get('complete') is not True:
                        rejected_scans['INCOMPLETE_SCAN']+=1
                        at_scan=d.get('timing',{}).get('receipt_end_s')
                        if finite(at_scan):invalid_scan_times.append(at_scan)
                        continue
                    quality=d.get('quality',{})
                    if not isinstance(quality,dict) or quality.get('interval_fallback_packets')!=0:
                        rejected_scans['FALLBACK_OR_QUALITY_NOT_RECORDED']+=1
                        at_scan=d.get('timing',{}).get('receipt_end_s')
                        if finite(at_scan):invalid_scan_times.append(at_scan)
                        continue
                    timing=d.get('timing',{});start=timing.get('receipt_start_s');end=timing.get('receipt_end_s');points=d.get('points')
                    if (not finite(start) or not finite(end) or not 0<=end-start<=PAIR_GAP_S or not isinstance(points,list)
                        or not 40<=len(points)<=4096 or any(not isinstance(p,list) or len(p)!=2 or not all(finite(v) for v in p) for p in points)):
                        continue
                    key=(d.get('stream_id'),d.get('frame_sequence'))
                    if not isinstance(key[0],str) or type(key[1]) is not int or not re.fullmatch('[a-f0-9]{64}',str(d.get('raw_sha256',''))):continue
                    item=dict(start=start,end=end,points=points[::max(1,len(points)//120)][:120],stream_id=key[0],frame_sequence=key[1],raw_sha256=d['raw_sha256'])
                    if key in scans and scans[key]!=item:raise ValueError('REVIEW_CONFLICTING_SCAN')
                    scans[key]=item
                    if len(scans)>MAX_SCANS:raise ValueError('REVIEW_SCAN_BOUND')
                if kind=='heartbeat':
                    p=d.get('pose',{})
                    if isinstance(p,dict) and finite(p.get('sample_s')) and all(finite(p.get(k)) for k in ('x','y','yaw')):poses[p['sample_s']]=deepcopy(p)
                    f=d.get('field',{})
                    if isinstance(f,dict) and isinstance(f.get('config'),dict):fields.append((at,deepcopy(f)))
                if kind=='command' and d.get('status')=='PUBLISHED' and d.get('direction'):
                    epochs=[v for v in (d.get('applied_motion_epoch'),d.get('motion_epoch'),e.get('motion_epoch')) if v is not None]
                    if any(not isinstance(v,str) or not 1<=len(v)<=128 for v in epochs) or len(set(epochs))>1:raise ValueError('REVIEW_PUBLICATION_EPOCH_CONFLICT')
                    pubs.append(dict(d,at=at,sequence=seq,motion_epoch=epochs[0] if epochs else None))
                if kind=='control_pause':pauses.append(dict(d,at=at,sequence=seq))
                if kind=='raw_source' and d.get('kind')=='manifest':export=d
                if kind=='raw_source' and d.get('kind')=='chunk' and d.get('member') in {'field-config.json','field-trials.json'}:
                    try:
                        b=base64.b64decode(d['base64'],validate=True);target=sources[d['member']]
                        if len(b)!=d['length'] or hashlib.sha256(b).hexdigest()!=d['sha256'] or d['offset']!=len(target) or len(target)+len(b)>256*1024:raise ValueError()
                        target.extend(b)
                    except (ValueError,KeyError,TypeError):source_error=True
        if member_size!=segment.get('bytes') or h.hexdigest()!=segment.get('sha256'):raise ValueError('REVIEW_SEGMENT_SHA')
    if first is None or count!=receipt.get('event_count') or size!=receipt.get('bytes'):raise ValueError('REVIEW_RECEIPT_COUNTS')
    verified_sources={}
    for name,b in sources.items():
        member=next((m for m in export.get('members',[]) if m.get('member')==name),{})
        if not source_error and member.get('source_complete') is True and member.get('source_sha256')==hashlib.sha256(b).hexdigest():
            value=_json(b)
            if isinstance(value,dict) and all(value.get('context',{}).get(k)==first.get(k) for k in ('operation_id','project_id','robot_id','connection_epoch')):verified_sources[name]=value
    return dict(first=first,receipt=receipt,receipt_sha256=hashlib.sha256(raw).hexdigest(),scans=sorted(scans.values(),key=lambda s:s['end']),
        rejected_scans=dict(rejected_scans),invalid_scan_times=invalid_scan_times,
        poses=sorted(poses.values(),key=lambda p:p['sample_s']),terminal=list(terminal.values()),pubs=pubs,pauses=pauses,fields=fields,sources=verified_sources,rows=count)

def windows(archive):
    """Never join separate same-direction gestures just because names match."""
    result=[]
    for m in archive['terminal']:
        if not all(finite(m.get(k)) for k in ('first_sample_s','sample_s','ended_s')):continue
        if not m['first_sample_s']<=m['sample_s']<=m['ended_s']:continue
        result.append(dict(linkage='RECORDED_TERMINAL_OBSERVATION',request_id=m['request_id'],latest_request_id=m.get('latest_request_id'),
            motion_epoch=m['motion_epoch'],direction=m.get('direction'),start=m['first_sample_s'],end=m['sample_s'],
            command_end_reason=m.get('reason'),stop_readback_confirmed=m.get('stop_readback_confirmed'),
            wheel={k:m.get(k) for k in ('centre_m','yaw_rad','wheel_data_quality','samples','published_count')},terminal=m))
    # Older archives lack terminal observations. Bound intervals by actual
    # publication and the first following pause; don't invent gesture/epoch IDs.
    consumed={p['sequence'] for p in archive['pubs'] if any(
        w['start']<=p['at']<=w.get('terminal',{}).get('ended_s',w['end']) and p['direction']==w['direction']
        and (p.get('motion_epoch') is None or p.get('motion_epoch')==w['motion_epoch']) for w in result)}
    for stop in archive['pauses']:
        group=[p for p in archive['pubs'] if p['sequence']<stop['sequence'] and p['sequence'] not in consumed]
        if not group:continue
        consumed.update(p['sequence'] for p in group)
        batches=[]
        for p in group:
            if not batches or p['direction']!=batches[-1][-1]['direction'] or p.get('motion_epoch')!=batches[-1][-1].get('motion_epoch') or p['at']-batches[-1][-1]['at']>PAIR_GAP_S:batches.append([])
            batches[-1].append(p)
        for batch in batches:
            a,b=batch[0],batch[-1]
            result.append(dict(linkage='LEGACY_RECONSTRUCTED_PUBLICATION_TO_PAUSE_NOT_GESTURE_PROOF',request_id=a.get('request_id'),
                latest_request_id=b.get('request_id'),motion_epoch=a.get('motion_epoch'),direction=a['direction'],start=a['at'],end=stop['at'],
                publication_count=len(batch),command_end_reason=stop.get('reason'),stop_readback_confirmed=stop.get('zero_off_readback_confirmed'),wheel=None))
    pending=[p for p in archive['pubs'] if p['sequence'] not in consumed]
    pending_batches=[]
    for p in pending:
        if not pending_batches or p['direction']!=pending_batches[-1][-1]['direction'] or p.get('motion_epoch')!=pending_batches[-1][-1].get('motion_epoch') or p['at']-pending_batches[-1][-1]['at']>PAIR_GAP_S:pending_batches.append([])
        pending_batches[-1].append(p)
    for batch in pending_batches:
        result.append(dict(linkage='INCOMPLETE_PUBLICATIONS_WITHOUT_TERMINAL_PAUSE',request_id=batch[0].get('request_id'),
            latest_request_id=batch[-1].get('request_id'),motion_epoch=batch[0].get('motion_epoch'),direction=batch[0]['direction'],
            start=batch[0]['at'],end=None,publication_count=len(batch),command_end_reason='TERMINAL_RECORD_MISSING',wheel=None))
    return result[:MAX_WINDOWS],len(result)>MAX_WINDOWS

def transform(points,config):
    sign=config['angle_sign'];yaw=config['sensor_yaw_rad'];x=config['sensor_x_m'];y=config['sensor_y_m'];c=math.cos(yaw);s=math.sin(yaw)
    return [[x+c*a-s*sign*b,y+s*a+c*sign*b] for a,b in points]

def analyse(archive,fit,deadline):
    """fit is the shipped unseeded ICP; injection is only for pure unit tests."""
    scans=archive['scans'];cache={}
    source=archive['sources'].get('field-config.json',{});config=source.get('config')
    if not isinstance(config,dict):config=next((f['config'] for _,f in archive['fields'] if isinstance(f.get('config'),dict)),None)
    recorded={digest(f['config']) for _,f in archive['fields'] if isinstance(f.get('config'),dict)}
    if config is not None:recorded.add(digest(config))
    # A final exported config is not evidence of the calibration at an earlier
    # command. Mixed/absent observation intervals stay sensor-local, not fitted
    # under the final configuration of some other gesture.
    configuration_pinned=len(recorded)==1 and bool(archive['fields'])
    extrinsics=bool(configuration_pinned and config and config.get('axes_reviewed') is True and config.get('robot_id')==archive['first']['robot_id']
        and config.get('binding_sha256')==archive['first'].get('binding_sha256') and config.get('angle_sign') in (-1,1)
        and all(finite(config.get(k)) for k in ('sensor_x_m','sensor_y_m','sensor_yaw_rad')))
    config_sha=digest(config) if config else None
    trials=archive['sources'].get('field-trials.json',{}).get('trials',[])
    stationary=[t for t in trials if t.get('case')=='stationary' and finite(t.get('started_s')) and finite(t.get('ended_s')) and t['ended_s']>t['started_s']
        and t.get('config_sha256')==config_sha and not any(t['started_s']<=p['at']<=t['ended_s'] for p in archive['pubs'])]
    def configured_before(at):
        return bool(extrinsics and any(t<=at and isinstance(f.get('config'),dict) and digest(f['config'])==config_sha for t,f in archive['fields']))
    def chain(selected):
        if len(selected)<2:return dict(status='INSUFFICIENT_SCAN_COVERAGE')
        if any(selected[0]['start']<=at<=selected[-1]['end'] for at in archive.get('invalid_scan_times',[])):return dict(status='REJECTED_SCAN_INTERVAL_UNQUALIFIED')
        use_extrinsics=configured_before(selected[0]['start'])
        x=y=yaw=0.;residuals=[]
        for a,b in zip(selected,selected[1:]):
            if time.monotonic()>deadline:raise ValueError('REVIEW_DEADLINE')
            if a['stream_id']!=b['stream_id'] or not 0<b['end']-a['end']<=PAIR_GAP_S:return dict(status='SCAN_STREAM_OR_COVERAGE_GAP')
            key=(a['stream_id'],a['frame_sequence'],b['frame_sequence'],config_sha if use_extrinsics else None)
            if key not in cache:
                try:
                    pa,pb=(transform(a['points'],config),transform(b['points'],config)) if use_extrinsics else (a['points'],b['points'])
                    cache[key]=fit(pa,pb,deadline=min(deadline,time.monotonic()+.08))
                except ValueError as e:cache[key]=dict(error=str(e)[:80])
            v=cache[key]
            if 'error' in v:return dict(status='INCONCLUSIVE_FIT',reason=v['error'])
            dx,dy,dyaw=v['delta'];c=math.cos(yaw);s=math.sin(yaw);x,y=x+c*dx-s*dy,y+s*dx+c*dy;yaw+=dyaw;residuals.append(v['residual_m'])
        return dict(status='ESTIMATED_UNQUALIFIED',dx_m=x,dy_m=y,translation_m=math.hypot(x,y),yaw_rad=yaw,
            comparison_frame='RECORDED_NOMINAL_BASE_EXTRINSICS_UNQUALIFIED' if use_extrinsics else 'SENSOR_LOCAL_UNCONFIRMED',
            # Unwrapped adjacent fit sum: one full revolution is not folded to0.
            pairs=len(selected)-1,max_residual_m=max(residuals),start_s=selected[0]['start'],end_s=selected[-1]['end'],
            first_frame=selected[0]['frame_sequence'],last_frame=selected[-1]['frame_sequence'],stream_id=selected[0]['stream_id'],
            first_raw_sha256=selected[0]['raw_sha256'],last_raw_sha256=selected[-1]['raw_sha256'])
    rows,truncated=windows(archive)
    for w in rows:
        if w['end'] is None:
            w.update(lidar=dict(status='COMMAND_WINDOW_NOT_CLOSED'),stationary_baseline=dict(windows=0),comparison='TERMINAL_RECORD_MISSING',body_motion='UNQUALIFIED_UNKNOWN')
            continue
        if w['wheel'] is None:
            p_before=next((i for i in range(len(archive['poses'])-1,-1,-1) if archive['poses'][i]['sample_s']<=w['start']),None)
            p_after=next((i for i,p in enumerate(archive['poses']) if p['sample_s']>=w['end']),None)
            poses=archive['poses'][p_before:p_after+1] if p_before is not None and p_after is not None and p_after>p_before else []
            if (len(poses)>=2 and len({p.get('frame_id') for p in poses})==1 and 0<=w['start']-poses[0]['sample_s']<=EDGE_GAP_S
                    and 0<=poses[-1]['sample_s']-w['end']<=EDGE_GAP_S):
                a,b=poses[0],poses[-1];dx=b['x']-a['x'];dy=b['y']-a['y']
                gap=max(b['sample_s']-a['sample_s'] for a,b in zip(poses,poses[1:]))
                w['wheel']=dict(centre_m=dx*math.cos(a['yaw'])+dy*math.sin(a['yaw']),
                    yaw_rad=sum(math.remainder(b['yaw']-a['yaw'],math.tau) for a,b in zip(poses,poses[1:])) if gap<=EDGE_GAP_S else None,
                    wheel_data_quality='LEGACY_INTERVAL_GAP_UNQUALIFIED' if gap>EDGE_GAP_S else 'LEGACY_ODOMETRY_ESTIMATE_UNQUALIFIED',samples=len(poses),
                    maximum_sample_gap_s=gap,
                    source_start_s=a['sample_s'],source_end_s=b['sample_s'])
        before=next((i for i in range(len(scans)-1,-1,-1) if scans[i]['end']<=w['start']),None)
        after=next((i for i,s in enumerate(scans) if s['start']>=w['end']),None)
        selected=scans[before:after+1] if before is not None and after is not None and after>before else []
        covered=bool(selected and 0<=w['start']-selected[0]['end']<=EDGE_GAP_S and 0<=selected[-1]['start']-w['end']<=EDGE_GAP_S)
        w['lidar']=chain(selected) if covered else dict(status='INSUFFICIENT_WINDOW_EDGE_COVERAGE')
        noise=[]
        if w['lidar'].get('status')=='ESTIMATED_UNQUALIFIED':
            span=w['lidar']['end_s']-w['lidar']['start_s']
            for t in stationary:
                pool=[s for s in scans if t['started_s']<=s['start'] and s['end']<=t['ended_s']]
                for i in range(0,len(pool),max(1,len(pool)//12)):
                    target=next((j for j in range(i+1,len(pool)) if pool[j]['end']-pool[i]['start']>=span),None)
                    if target is None or pool[target]['end']-pool[i]['start']-span>EDGE_GAP_S:continue
                    n=chain(pool[i:target+1])
                    if n.get('status')=='ESTIMATED_UNQUALIFIED':noise.append(n)
                    if len(noise)>=24:break
                if len(noise)>=24:break
        w['stationary_baseline']=dict(basis='SAME_SESSION_APP_ZERO_OUTPUT_COLLECTION_NOT_PROOF_OF_PHYSICAL_IMMOBILITY',
            duration_matched=True,pairs=noise,windows=len(noise),statistical_confidence_bound=False)
        frames_confirmed=w['lidar'].get('comparison_frame')=='RECORDED_NOMINAL_BASE_EXTRINSICS_UNQUALIFIED' and all(n.get('comparison_frame')=='RECORDED_NOMINAL_BASE_EXTRINSICS_UNQUALIFIED' for n in noise)
        comparison='INSUFFICIENT_DURATION_MATCHED_BASELINE' if len(noise)<3 else 'CONFIGURATION_CHANGED_OR_UNCONFIRMED' if not frames_confirmed else 'WHEEL_EVIDENCE_MISSING' if not w['wheel'] else 'WHEEL_SAMPLE_STALE' if w['wheel'].get('wheel_data_quality')=='LAST_SAMPLE_STALE' else 'WHEEL_INTERVAL_GAP' if w['wheel'].get('wheel_data_quality')=='LEGACY_INTERVAL_GAP_UNQUALIFIED' else None
        if comparison is None:
            angular=w['direction'] in ('left','right');metric='yaw_rad' if angular else 'translation_m';v=w['lidar']['yaw_rad' if angular else 'dx_m']
            baseline=max(abs(n[metric]) for n in noise);wheel=w['wheel'].get('yaw_rad' if angular else 'centre_m')
            if not finite(wheel):comparison='WHEEL_EVIDENCE_MISSING'
            elif abs(v)<=baseline:comparison='CHANGE_OVERLAPS_OBSERVED_BASELINE'
            elif abs(v-wheel)>baseline:comparison='ESTIMATES_DIFFER_OUTSIDE_OBSERVED_BASELINE'
            else:comparison='ESTIMATED_CHANGE_OUTSIDE_OBSERVED_BASELINE_NOT_BODY_PROOF'
        w['comparison']=comparison;w['body_motion']='UNQUALIFIED_UNKNOWN';w.pop('terminal',None)
    return dict(schema=SCHEMA,status='COMPLETED_WITH_LIMITS',operation_id=archive['first']['operation_id'],project_id=archive['first']['project_id'],
        robot_id=archive['first']['robot_id'],connection_epoch=archive['first']['connection_epoch'],source_twin_context=archive['first'].get('source_twin_context'),
        input_receipt_sha256=archive['receipt_sha256'],input_segments=archive['receipt']['segments'],input_rows=archive['rows'],
        original_complete=archive['receipt'].get('complete'),original_error=archive['receipt'].get('error'),
        config_sha256=config_sha,rejected_scan_reasons=archive.get('rejected_scans',{}),comparison_frame='RECORDED_NOMINAL_BASE_EXTRINSICS_UNQUALIFIED' if extrinsics else 'SENSOR_LOCAL_UNCONFIRMED',
        windows=rows,truncated=truncated,physical_motion_verified=False,authority_restored=False,original_logs_rewritten=False,
        limits=['Offline saved summaries, not measured chassis motion or live robot/world registration.',
            'Fit is independent of wheel input but unqualified; correlated zero-output windows are observed noise, not a confidence bound.',
            'Missing rings/edge coverage/configuration remain inconclusive; no timeouts, permissions or scene state are changed.',
            'Legacy publication windows cannot establish a missing gesture/request/epoch; no identities are fabricated.'])
