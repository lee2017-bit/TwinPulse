# SPDX-License-Identifier: Apache-2.0
"""Verify actual moving-data attempt; preserve all failures, no robot actions."""
import collections,hashlib,json,math,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-moving-survey-20261025-01'
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime';OP='ac26047db06f4c739903327289dc1a05'
read=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
raw=RUNTIME/'devices/local/physical-live'/OP;receipt=read(raw/'receipt.json')
counts=collections.Counter();pc=collections.Counter();commands=collections.Counter();parts=[];last={};pauses=[];guard=[]
scans=0;poses=0;scan_times=[];pose_times=[]
for part in receipt['segments']:
    path=raw/part['path'];digest=hashlib.sha256();n=0;size=0
    with path.open('rb') as stream:
        for line in stream:
            digest.update(line);n+=1;size+=len(line);e=json.loads(line);kind=e.get('kind');d=e.get('data') or {};counts[kind]+=1
            if e.get('schema','').startswith('physical-live-pc-command'):pc[e.get('action')]+=1
            if kind=='command':commands[d.get('action')]+=1
            if kind=='scan':scans+=1;scan_times.append(e.get('robot_monotonic_s'))
            if kind=='heartbeat':
                if d.get('pose'):poses+=1;pose_times.append(e.get('robot_monotonic_s'))
                for key in ('field','pose','battery','command'):
                    if d.get(key) is not None:last[key]=d[key]
            if kind=='control_pause':
                value=dict(robot_monotonic_s=e.get('robot_monotonic_s'),sequence=e.get('sequence'),data=d)
                if len(pauses)<100:pauses.append(value)
                if 'FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP' in json.dumps(d):guard.append(value)
            if kind=='cleanup' and d.get('subsystem')=='session':last['cleanup']=d
    parts.append(dict(**part,exact=digest.hexdigest()==part['sha256'] and size==part['bytes'] and n==part['events']))
taskpath=RUNTIME/'projects/chat_mvmcf9wa_18f1e6d1/robot-tasks/e78663260fa9504d5efa82ab014c7295/task.json'
task=read(taskpath);assist=read(OUT/'assisted-legs01.json');actions=read(OUT/'ui-actions01.json');fleet=read(OUT/'final-fleet01.json')
robot=next(r for r in fleet['robots'] if r['robot_id']=='2bf518f09a234dd5b65c312febda8841')
legs=[]
for leg in assist['legs']:
    command=(leg.get('after') or {}).get('command') or {}
    legs.append(dict(index=leg['index'],text=leg['text'],request_id=command.get('request_id'),state=command.get('state'),
        reason=command.get('reason'),progress=command.get('progress'),unit=command.get('unit'),
        stop_readback_confirmed=command.get('stop_readback_confirmed'),before_pose=leg['before'].get('pose'),after_pose=(leg.get('after') or {}).get('pose')))
folder=OUT/'runtime-copies01/feca72b65210405b8eb82344a912ae2a';cleanup=read(folder/'cleanup-receipt.json');engine=read(folder/'engine-result.json');copy=read(folder/'copy-receipt.json')
compression=[read(OUT/('compression'+suffix+'.json')) for suffix in ('01','02')]
checks=dict(raw_complete=receipt['complete'] and not receipt.get('error') and receipt['accepted']==receipt['saved']==receipt['event_count']==sum(r['events'] for r in parts),
    raw_exact=all(r['exact'] for r in parts),original_auto_fail_preserved=task['state']=='FAILED' and task['segments']==0 and task['reason']=='TASK_LOCAL_FRESH_RING_REQUIRED_BEFORE_MOTION',
    assisted_first_four_completed=len(legs)==5 and all(r['state']=='COMPLETED' and r['stop_readback_confirmed'] for r in legs[:4]),
    original_assisted_failure_preserved=legs[-1]['state']=='FAILED' and legs[-1]['reason']=='FIELD_BODY_PROGRESS_INCONCLUSIVE_STOP' and legs[-1]['stop_readback_confirmed'],
    final_stop=(robot.get('stop_receipt') or {}).get('zero_off_readback_confirmed') is True,
    final_off_disconnect=robot['connection_state']=='DISCONNECTED' and robot['lidar_state']=='OFF',
    terminal_cleanup=last.get('cleanup',{}).get('confirmed') is True,
    normal_exit=cleanup['exit_evidence_complete'] and cleanup['owned_processes_stopped'] and all(r['return_code']==0 and r['root_disposition']=='EXITED_DURING_GRACE' for r in cleanup['process_exit_observations'].values()),
    inner_cleanup=engine['cleanup_status']=='PRE_CLOSE_COMPLETE' and not engine['cleanup_errors'],
    archives_exact=all(sha((folder/r['name']).read_bytes())==r['sha256'] for r in copy['files'] if r['status']=='EXACT_COPY'),
    compression_no_deleted_bytes=all(c['files_deleted']==0 and all(r['all_bytes_unchanged'] for r in c['rows']) for c in compression))
good_times=[t for t in scan_times if isinstance(t,(int,float))]
progress_m=sum(r.get('progress') or 0 for r in legs if r.get('unit')=='m')
end=assist['final_pose'];start=assist['start']['pose']
value=dict(status='PARTIAL_MOVING_DATA_AUTONOMOUS_AND_RETURN_FAILED',scope='ACTUAL_SUPERVISED_OPERATOR_ASSISTED_DATA_NOT_AUTONOMOUS_OR_BODY_QUALIFICATION',
    evidence_checks=checks,all_evidence_checks=all(checks.values()),release_id='20261025T034741Z-1387861a7bfd',
    launch_id=folder.name,operation_id=OP,task_id=task['task_id'],task_sha256=sha(taskpath.read_bytes()),
    autonomous_state=task['state'],autonomous_reason=task['reason'],autonomous_segments=task['segments'],
    assisted_steps=legs,finite_progress_sum_m=progress_m,progress_basis='WHEEL_ODOMETRY_NOT_INDEPENDENT_CHASSIS',
    return_completed=False,estimated_final_distance_from_start_m=math.dist(end['position_m'][:2],start['position_m'][:2]),
    raw_directory=str(raw),receipt_sha256=sha((raw/'receipt.json').read_bytes()),raw_events=receipt['event_count'],raw_bytes=sum(r['bytes'] for r in parts),raw_segments=parts,
    scan_events=scans,heartbeats_with_pose=poses,scan_span_s=max(good_times)-min(good_times) if good_times else None,
    native_event_counts=dict(counts),pc_actions=dict(pc),native_commands=dict(commands),original_pauses=pauses,
    body_progress_rejections=guard,latest_field=last.get('field'),terminal_cleanup=last.get('cleanup'),
    input_errors=[dict(status=e['status'],request_id=e['request'].get('request_id'),error=e['response'].get('error')) for e in actions if e['status']>=400],
    model_claim=13,model_calls_this_attempt=1,new_product_changes=0,new_installation=0,
    limitations=['Whole-room circuit and return did not complete.','Original common task failed before its first child.',
        'First four operator-assisted finite commands completed; fifth translation stopped on inconclusive body progress.',
        'Wheel progress is not independent physical displacement or world registration.',
        'Renderer recording ends during the assisted journey to protect remaining raw-data storage.'])
(OUT/'result01.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps({k:value[k] for k in ('status','all_evidence_checks','raw_events','raw_bytes','scan_events','heartbeats_with_pose','scan_span_s','finite_progress_sum_m','estimated_final_distance_from_start_m')}))
raise SystemExit(0 if all(checks.values()) else 1)
