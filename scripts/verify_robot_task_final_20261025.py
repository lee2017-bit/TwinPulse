# SPDX-License-Identifier: Apache-2.0
"""Final current-release evidence only. No controls, model calls or SDK startup."""
import hashlib,json,math,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-task-20261025-01'
for name in ('twinpulse_core','twinpulse_app','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT))
from twinpulse_app.windows_package import verify_package
from twinpulse_core import canonical_sha256
from twinpulse_core.automatic_mapping import EvidenceGrid
from scripts.roomplan_runtime_copy_gate import check_runtime_copy
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
release=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'/Path(active['exe']).parent
package=verify_package(release)
names=('ui03','compose01','compose02','survey04','survey05','survey06','survey07','compose04','cancel07','cold04')
cases={name:read(OUT/name/'result.json') for name in names}
survey=cases['survey07'];compose=cases['compose04'];cancel=cases['cancel07'];cold=cases['cold04'];old=cases['survey04']
required=['Select existing registered TurtleBot3 SIM only','Explicit SIM Connect Prepare with current engine epoch',
    'Camera frames the actual robot body before the task','Natural goal through Robot command waits three seconds before Enter',
    'One approved text-only configured planner request','Explicit exact-plan Run uses measured child results and observations',
    'Final exact Stop LiDAR OFF Disconnect without physical calls']
def steps(c,required):return c['status']=='PASS_SCOPED' and set(required)<={s['name'] for s in c['steps'] if s['status']=='PASS'}
def children(c):
    job=c['final_task'];starts={e['request_id']:e for e in job['events'] if e['kind']=='child_started'}
    ends=[e for e in job['events'] if e['kind']=='child_completed']
    return len(ends)>=2 and len(starts)==len(ends) and all(e['request_id'] in starts and e['command']['request_id']==e['request_id']
        and e['new_motion_epoch']==e['applied_motion_epoch'] and e['new_motion_epoch']!=starts[e['request_id']]['motion_epoch'] for e in ends)
def returned(c):
    events=c['final_task']['events'];r=[e for e in events if e['kind']=='return_verified']
    return len(r)==1 and r[0]['position_error_m']<.04 and r[0]['yaw_error_rad']<.04 and any(e['kind']=='stop_confirmed' for e in events) and not c['final_task'].get('stop_error')
def exact_stops_and_disconnect(c):
    rows=[r for r in c['requests'] if r['path']=='/v1/product/robot-fleet'];stops=[(i,r) for i,r in enumerate(rows) if r['request']['action']=='stop']
    if not stops:return False
    for i,r in stops:
        q,a,b=r['request'],r['last_command'],r['robot']
        if not (r['status']==200 and a['request_id']==q['request_id'] and a['robot_id']==q['robot_id']==b['robot_id']
            and a['operation_id']==b['operation_id'] and q['connection_epoch']==b['connection_epoch']
            and b['motion_epoch']!=q['motion_epoch'] and b['control_state']=='PAUSED' and b['connection_state']=='CONNECTED'):return False
        # Original ACK is preserved. A subsequent SAME-operation observation
        # must carry this exact new applied epoch (never a different launch or
        # a generic later PAUSED snapshot). The first cancel Stop is observed
        # in the second Stop ACK's applied epoch; its original ACK is NOT filled in.
        observations=[v['robot'] for v in rows[i+1:]]+[c['stop']['robot']]
        if not any(v['robot_id']==b['robot_id'] and v['operation_id']==b['operation_id'] and v['connection_epoch']==b['connection_epoch']
            and v['applied_motion_epoch']==b['motion_epoch'] for v in observations):return False
    final=stops[-1][1]
    if c['stop']['request']!=final['request'] or c['stop']['ack']!=final['last_command'] or c['stop']['robot']['motion_epoch']!=final['robot']['motion_epoch']:return False
    disconnect_applied=final['robot']['motion_epoch']
    for r in rows[rows.index(final)+1:]:
        if r['request']['action']=='lidar' and r['request']['payload']=={'enabled':False}:
            q,a,b=r['request'],r['last_command'],r['robot']
            if not (r['status']==200 and a['request_id']==q['request_id'] and a['robot_id']==q['robot_id']==b['robot_id']
                and a['operation_id']==b['operation_id']==final['robot']['operation_id'] and q['connection_epoch']==b['connection_epoch']==final['robot']['connection_epoch']
                and q['motion_epoch']==disconnect_applied and b['applied_motion_epoch'] in {disconnect_applied,b['motion_epoch']} and b['motion_epoch']!=q['motion_epoch']
                and b['lidar_state']=='OFF' and b['control_state']=='PAUSED'):return False
            # LiDAR OFF intentionally issues a further zero-output epoch.
            # Follow its exact ACK; do not demand the preceding Stop's epoch
            # after that legitimate transition or erase the original gate FAIL.
            disconnect_applied=b['motion_epoch']
    dis=[r for r in rows if r['request']['action']=='disconnect']
    if len(dis)!=1:return False
    d=dis[0];q=d['request'];b=d['robot'];a=d['last_command']
    return (d['status']==200 and a['request_id']==q['request_id'] and a['robot_id']==q['robot_id']==b['robot_id']
        and a['operation_id']==b['operation_id']==final['robot']['operation_id'] and b['connection_epoch']==q['connection_epoch']==final['robot']['connection_epoch']
        and b['lidar_state']=='OFF' and b['connection_state']=='DISCONNECTED' and q['motion_epoch']==disconnect_applied and b['applied_motion_epoch']==disconnect_applied)
checks=dict(package=package['files']==1698,
    final_ui_survey=steps(survey,required),final_ui_composition=steps(compose,required),
    final_ui_missing_step_negative=not steps({**survey,'steps':survey['steps'][:-1]},required),
    same_current_release=all(cases[n]['versions']['engine']['release_id']==package['build_id'] for n in ('survey07','compose04','cancel07','cold04')),
    same_original_failed_survey_instruction=survey['proposal']['text']==old['proposal']['text'],
    same_original_failed_survey_start=survey['start']['pose']['position_m']==old['start']['pose']['position_m'] and survey['original_failed_survey']['task_id']==old['final_task']['task_id'],
    original_survey_failure_retained=old['status']=='FAIL' and old['final_task']['state']=='FAILED' and old['final_task']['reason']=='START_OR_GOAL_BLOCKED',
    original_composition_failure_retained=cases['compose01']['status']=='FAIL' and cases['compose01']['final_task']['state']=='COMPLETED',
    survey_partial_not_whole_room=survey['final_task']['state']=='PARTIAL' and survey['final_task']['distance_m']>.5 and survey['final_task']['measured_coverage']['observations']>=3 and survey['final_task']['whole_room_coverage_verified'] is False,
    composition_completed=compose['final_task']['state']=='COMPLETED' and compose['proposal']['text']==cases['compose01']['proposal']['text'],
    survey_child_epochs=children(survey),composition_child_epochs=children(compose),survey_return=returned(survey),composition_return=returned(compose),
    stopped_after_survey=exact_stops_and_disconnect(survey),
    survey_off_connected_frame=survey['off']['robot']['motion_epoch']==survey['off']['robot']['applied_motion_epoch'] and survey['off']['robot']['lidar_state']=='OFF'
        and survey['off']['robot']['connection_state']=='CONNECTED' and survey['off']['robot']['scan'] is None and not survey['off']['frame']['lidar_overlay'] and survey['off']['frame']['captured_at_ms']>survey['off']['at'],
    stopped_after_composition=exact_stops_and_disconnect(compose),stopped_during_and_after_cancel=exact_stops_and_disconnect(cancel),
    stop_while_planning=steps(cancel,[*required[:5],'Stop after planner submission prevents late execution',required[-1]]) and cancel['cancel_at_state']=='PLANNING' and cancel['cancel_worker_active'] is True,
    cancelled_no_late_execution=cancel['cancelled']['state']=='CANCELLED' and cancel['cancelled']['segments']==0 and cancel['cancelled']['plan'] is None and cancel['cancelled']['worker_active'] is False,
    cold_no_authority=steps(cold,[required[0],'Cold history does not resume a task or connection']) and not cold['task_snapshots'],
    no_physical_actions=all(c['physical_actions']==0 for c in cases.values()),
    regressions=read(OUT/'focused-final04/result.json')==dict(scope='SUPPLEMENTARY_FAKE_ENGINE_MODEL_NO_HARDWARE',status='PASS',tests=150,failures=0,errors=0,skipped=0))
off=survey['off'];offack=next(r for r in survey['requests'] if r['request'].get('request_id')==off['request']['request_id'])
checks['survey_off_exact_scene_binding']=(off['request']==offack['request'] and off['ack']==offack['last_command']
    and all(off['robot'][k]==offack['robot'][k] for k in ('robot_id','operation_id','connection_epoch','motion_epoch'))
    and off['robot']['robot_id']==survey['final_task']['robot_id'] and off['robot']['operation_id']==survey['final_task']['operation_id']
    and [off['frame'][k] for k in ('engine_session_id','stage_epoch','applied_revision')]==survey['final_task']['scene_binding'])
sensor=read(OUT/'off-dom02/result.json');draw=sensor['off_drawn'];obs=sensor['off']['observed'];ack=sensor['off']['robot']
checks['separate_off_dom_journey']=(sensor['status']=='PASS_SCOPED' and sensor['model_calls']==sensor['motion_commands']==sensor['physical_actions']==0
    and sensor['versions']['engine']['release_id']==package['build_id'] and sensor['off']['ack']['request_id']==sensor['off']['request']['request_id']
    and all(obs[k]==ack[k] for k in ('robot_id','connection_epoch','operation_id','motion_epoch')) and obs['motion_epoch']==obs['applied_motion_epoch']
    and obs['connection_state']=='CONNECTED' and obs['lidar_state']=='OFF' and obs['scan'] is None and not draw['frame']['lidar_overlay']
    and draw['dom']['live']=='true' and draw['dom']['frame_id']==str(draw['frame']['frame_id']) and draw['dom']['captured_at_ms']==draw['frame']['captured_at_ms']
    and draw['dom']['scene']==draw['frame']['applied_revision'] and draw['dom']['stage']==draw['frame']['stage_epoch'] and draw['dom']['colors']>12
    and [draw['frame'][k] for k in ('engine_session_id','stage_epoch','applied_revision')]==survey['final_task']['scene_binding'])
runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1/robot-tasks'
copies=[];usage=[];records=[]
for name in names[:-1]:
    c=cases[name];j=c.get('final_task') or c.get('cancelled') or c.get('planning_result') or c['task_snapshots'][-1]['job'];identity=j['task_id'];folder=runtime/identity;target=OUT/'task-originals'/identity;target.mkdir(parents=True,exist_ok=True)
    paths=[p for p in folder.iterdir() if p.is_file() and (p.name in {'task.json','request.json','proposal.json','usage.ledger.json','observed-grid.json','provider-diagnostic.json'} or p.name.startswith(('observation-','navigation-')))]
    paths+=list((folder/'provider-evidence').glob('**/*.json'))
    for p in paths:
        raw=p.read_bytes();relative=p.relative_to(folder);dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists() and dest.read_bytes()!=raw:raise ValueError('Frozen original changed: '+str(dest))
        if not dest.exists():dest.write_bytes(raw)
        copies.append(dict(case=name,task_id=identity,name=relative.as_posix(),bytes=len(raw),sha256=sha(p)))
    rec=read(folder/'task.json');digest=rec.pop('record_sha256');records.append(canonical_sha256(rec)==digest)
    usage.extend(read(folder/'usage.ledger.json')['requests'])
    request=read(folder/'request.json');checks['text_scope_'+name]=set(request['prompt'])=={'text','robot_kind','capabilities'} and request['images_sent']==0 and not request['coordinates_sent'] and not request['sensor_logs_sent'] and not request['mesh_sent']
    if name in ('survey07','compose04'):
        navpaths=list(folder.glob('navigation-*.json'));navigation=[read(p) for p in navpaths]
        hashes={canonical_sha256(n['geometry']) for n in navigation}
        recorded={e['sha256'] for e in j['events'] if e['kind']=='geometry_recorded'}
        checks['frozen_navigation_'+name]=(len(navigation)==1 and all(p.stem=='navigation-'+canonical_sha256(n) and canonical_sha256(n) in recorded
            and n['binding']==j['scene_binding'] and n['peers']==[] for p,n in zip(navpaths,navigation))
            and all(e['geometry_sha256'] in hashes and e['minimum_clearance_m']==.30 for e in j['events'] if e['kind']=='child_started'))
        checks['same_replayed_room_grid_'+name]=all(n['geometry']['grid']['sha256']==read(OUT/'route-replay01/result.json')['grid']['sha256'] for n in navigation)
        observations=[read(p) for p in sorted(folder.glob('observation-*.json'))];events=[e for e in j['events'] if e['kind']=='observation'];grid=EvidenceGrid();bound=True
        for o,e in zip(observations,events):
            scan=o['scan'];key=[scan['stream_id'],scan['frame_sequence'],scan['captured_at_ms']]
            bound=bound and (canonical_sha256(scan)==e['scan_sha256'] and key==e['scan_identity'] and o['operation_id']==e['operation_id']==j['operation_id']
                and o['connection_epoch']==j['connection_epoch'] and o['binding']==j['scene_binding'] and o['robot_id']==j['robot_id'] and o['body_pose']==e['pose'])
            sensor=scan['sensor_xy_yaw_world'];co,si=math.cos(sensor[2]),math.sin(sensor[2]);rays=[]
            for x,y in scan['points']:
                if .02<=math.hypot(x,y)<=8:rays.append((sensor[:2],[sensor[0]+co*x-si*y,sensor[1]+si*x+co*y]))
            grid.insert(rays,round(scan['captured_at_ms']*1e6),canonical_sha256(dict(binding=j['scene_binding'],operation=j['operation_id'],scan=key)))
        saved=read(folder/'observed-grid.json');summary=j['measured_coverage']
        checks['raw_observations_'+name]=bound and len(observations)==len(events)==summary['observations']
        checks['raw_grid_replayed_'+name]=saved['summary']==summary and grid.rows()==saved['cells'] and canonical_sha256(saved['cells'])==summary['grid_sha256']
checks['original_record_hashes']=all(records)
claims=list((OUT/'call-claims').glob('*.json'));extra=read(OUT/'approval-additional03.json')
checks['approved_budget']=len(claims)==len(usage)==9 and extra['additional_max_requests']==10 and extra['cumulative_max_requests']==17 and extra['physical_operation_allowed'] is False
rejected=cases['survey05']['task_snapshots'][-1]['job']
checks['missing_survey_plan_was_not_executed']=cases['survey05']['status']=='FAIL' and rejected['state']=='FAILED' and rejected['segments']==0 and rejected['reason']=='ROBOT_TASK_REQUESTED_CAPABILITY_MISSING: survey'
# Installed-only pure core in a fresh isolated interpreter; no robot worker/SDK.
code="""import sys,json
sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1])
from twinpulse_core.robot_task_plan import checked_plan
from twinpulse_core.robot_survey import MIN_CLEARANCE_M,PLANNING_CLEARANCE_M,checked_motion_segment
v=json.load(open(sys.argv[2],encoding='utf-8'))
try:checked_plan(v['proposal']['plan'],request_text=v['proposal']['text'])
except ValueError as e:assert 'REQUESTED_CAPABILITY_MISSING' in str(e)
else:raise AssertionError('Original missing-return plan accepted')
n=json.load(open(sys.argv[3],encoding='utf-8'))
try:checked_motion_segment([1.900000000091919,.5000000159354973,2.634397e-8],'forward',.05,n['geometry'],observed_cells=n['observed_cells'])
except ValueError as e:assert 'START_OR_GOAL_BLOCKED' in str(e)
else:raise AssertionError('Original blocked pose was snapped or collision epsilon relaxed')
assert MIN_CLEARANCE_M==.30 and PLANNING_CLEARANCE_M==.32
print(json.dumps({'status':'REJECTED_ORIGINAL_BAD_PLAN_AND_BLOCKED_POSE','minimum_clearance_m':MIN_CLEARANCE_M,'planning_clearance_m':PLANNING_CLEARANCE_M}))
"""
probe=subprocess.run([sys.executable,'-I','-B','-c',code,str(release/'_internal/resources/packages/twinpulse_core/src'),str(OUT/'compose01/result.json'),str(OUT/'route-replay01/navigation.json')],capture_output=True,text=True,check=True)
replay=json.loads(probe.stdout);checks['installed_negative_replay']=replay['status']=='REJECTED_ORIGINAL_BAD_PLAN_AND_BLOCKED_POSE'
source_files=['packages/twinpulse_app/src/twinpulse_app/robot_task_service.py','packages/twinpulse_app/src/twinpulse_app/robot_fleet.py','packages/twinpulse_core/src/twinpulse_core/robot_survey.py','packages/twinpulse_core/src/twinpulse_core/robot_task_plan.py','packages/twinpulse_provider/src/twinpulse_provider/robot_task_planner.py']
checks['source_installed_match']=all(sha(ROOT/p)==sha(release/'_internal/resources'/p) for p in source_files)
launches=[('runtime-copiesruntime-copies01','exit-live01.json'),('runtime-copies02','exit-live02.json'),('runtime-copies03','exit-cold01.json'),('runtime-copies04','exit-survey04.json'),('runtime-copies05','exit-planner05.json'),('runtime-copies06','exit-final-live.json'),('runtime-copies07','exit-final-cold.json')]
launches.extend([('runtime-copies08','exit-survey07.json'),('runtime-copies09','exit-cold04.json')])
logs=[]
for folder,exitname in launches:
    identity=read(OUT/exitname)['identity']['engine']['launch_id'];path=OUT/folder/identity
    issues=check_runtime_copy(path,identity,read(path/'copy-receipt.json'));exitrec=read(path/'owned-exit-observations.json');cleanup=read(path/'cleanup-receipt.json')
    checks['original_logs_'+identity]=not issues
    checks['normal_exit_'+identity]=exitrec['evidence_complete'] and cleanup['exit_evidence_complete'] and all(exitrec['roles'][r]['root_disposition']=='EXITED_DURING_GRACE' and exitrec['roles'][r]['return_code']==0 for r in ('backend','engine'))
    logs.append(dict(launch_id=identity,path=folder+'/'+identity,issues=issues,optional_liveness='ORIGINAL_UNAVAILABLE_NOT_HEALTH_PROOF'))
media=read(OUT/'media-checks03.json');checks['encoded_media']=media['status']=='PASS' and {'survey07','compose04','cancel07'}<={v['name'] for v in media['videos']}
checks['source_usd_unchanged']=sha(Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd'))=='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b'
value=dict(status='PASS_SCOPED_NATURAL_TASKS_SIM' if all(checks.values()) else 'FAIL',scope='CURRENT_INSTALLED_SIM_NOT_PHYSICAL_ROOM_TOUR_READINESS',build_id=package['build_id'],
    checks=checks,passed=sum(checks.values()),total=len(checks),approved_slots=17,claimed_slots=len(claims),unused_approved_slots=17-len(claims),reserved_requests=len(usage),responses_with_usage=sum(bool(r.get('usage')) for r in usage),
    unknown_usage_requests=sum(not bool(r.get('usage')) for r in usage),known_total_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in usage),
    physical_task_ready=False,whole_room_coverage_verified=False,installed_negative_replay=replay,task_copies=copies,runtime_copies=logs)
target=OUT/'acceptance06.json'
with target.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in value.items() if k not in {'checks','task_copies','runtime_copies'}},ensure_ascii=False))
if value['status']=='FAIL':raise SystemExit('Failed evidence: '+','.join(k for k,v in checks.items() if not v))
