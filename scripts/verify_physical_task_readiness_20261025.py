# SPDX-License-Identifier: Apache-2.0
"""Hash-bound software readiness gate. Never grants physical authority."""
import argparse,hashlib,json,os,sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physical-task-preparation-20261025-01'
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=dict(installed='installed01.json',tests='tests07/result.json',bundle='bundle02/result.json',replay='original-replay01/result.json',
    clearance='clearance-replay02/result.json',survey='survey03/result.json',compose='compose01/result.json',cancel='cancel01/result.json',
    opened='open03/result.json',cold='cold01/result.json',media='media01.json',cold_media='media02.json')
data={k:read(OUT/p) for k,p in paths.items()};checks={}
def require(name,value):checks[name]=bool(value)
def evaluate_ui(value,release):
    return value.get('status')=='PASS_SCOPED' and not value.get('errors') and value.get('versions',{}).get('engine',{}).get('release_id')==release
def exact_action(value,job,action):
    q=value.get('request') or {};ack=value.get('ack') or {};r=value.get('robot') or {}
    return (q.get('action')==action and q.get('request_id') and q['request_id']==ack.get('request_id')
        and q.get('robot_id')==ack.get('robot_id')==r.get('robot_id')==job.get('robot_id')
        and q.get('connection_epoch')==r.get('connection_epoch')==job.get('connection_epoch')
        and ack.get('operation_id')==r.get('operation_id')==job.get('operation_id') and ack.get('status')=='accepted'
        and q.get('motion_epoch') and r.get('motion_epoch') and q['motion_epoch']!=r['motion_epoch']
        and r.get('motion_epoch')==r.get('applied_motion_epoch') and r.get('control_state')=='PAUSED' and r.get('connection_state')=='CONNECTED')
def exact_off(value,job):
    frame=value.get('frame') or {};r=value.get('robot') or {};scene=job.get('scene_binding') or []
    return (exact_action(value,job,'lidar') and value['request'].get('payload')=={'enabled':False}
        and r.get('lidar_state')=='OFF' and r.get('scan') is None and not frame.get('lidar_overlay')
        and [frame.get('engine_session_id'),frame.get('stage_epoch'),frame.get('applied_revision')]==scene
        and type(frame.get('captured_at_ms')) in (int,float) and frame['captured_at_ms']>value.get('at',float('inf'))
        and any(a.get('robot_id')==job.get('robot_id') and a.get('visible') is True for a in frame.get('robot_anchors',[])))
def exact_cancel(c):
    j=c.get('cancelled') or {};binding=j.get('proposal_binding') or []
    if len(binding)!=5:return False
    context=dict(robot_id=j.get('robot_id'),connection_epoch=binding[2],operation_id=binding[3])
    return (binding[:4]==[c['start']['robot_id'],'sim',c['start']['connection_epoch'],c['start']['operation_id']]
        and c.get('cancel_at_state')=='PLANNING' and c.get('cancel_worker_active') and j.get('segments')==0
        and j.get('state')=='CANCELLED' and j.get('worker_active') is False and j.get('reason')=='models stage cancelled; output ignored'
        and not j.get('stop_error') and not any(e['kind']=='child_started' for e in j.get('events',[]))
        and c.get('stop_history') and all(exact_action(v,context,'stop') for v in c['stop_history']))
release=data['installed']['package']['build_id']
require('final_installed_sources_and_isolated_import',data['installed']['status']=='PASS' and all(data['installed']['checks'].values()))
active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
require('active_release_is_tested_release',release in active['exe'])
require('tests203_pass',data['tests']['status']=='PASS' and data['tests']['tests']==203 and not data['tests']['failures'] and not data['tests']['errors'])
require('actual_receiver_complete_manifest',data['bundle']['status']=='PASS' and data['bundle']['members']==114 and data['bundle']['receiver']['files'])
require('installed_receiver_source_match',data['bundle']['bundle_sha256']==data['installed']['isolated_probe']['bundle_sha256'])
require('original_sensor_replay_retains_limits',data['replay']['status']=='REPLAYED_WITH_LIMITS' and data['replay']['counts']['eligible_stationary_pairs']==105)
require('original_sensor_bytes_unchanged',all((ROOT/r['path']).stat().st_size==r['bytes'] and sha(ROOT/r['path'])==r['sha256'] for r in data['replay']['originals']))
require('original_stop_reproduced_and_replan_compatible',data['clearance']['status']=='PASS' and all(data['clearance']['checks'].values()) and data['clearance']['unchanged_stop_protection'])
for role in ('survey','compose','cancel','opened','cold'):
    require(role+'_whole_current_ui',evaluate_ui(data[role],release))
    require(role+'_no_physical_actions',data[role].get('physical_actions',data[role].get('hardware_actions'))==0)
survey=data['survey'];job=survey.get('final_task') or {};events=job.get('events',[])
require('survey_original_instruction_and_start',survey['original_failed_survey']['pose']==survey['start']['pose']['position_m'] and job['text']==read(OUT/'survey02/result.json')['final_task']['text'])
require('survey_multi_location_return_stop',job.get('state')=='PARTIAL' and job.get('segments',0)>=2 and job.get('distance_m',0)>1.5 and job.get('measured_coverage',{}).get('observations',0)>=3
    and any(e['kind']=='return_verified' and e['position_error_m']<=.04 and e['yaw_error_rad']<=.04 for e in events)
    and any(e['kind']=='stop_confirmed' for e in events) and not job.get('stop_error') and job.get('whole_room_coverage_verified') is False)
require('sim_requested_and_effective_envelope_explicit',all(e.get('requested_minimum_clearance_m')==.15 and abs(e.get('minimum_clearance_m',0)-.2075)<1e-12 for e in events if e['kind']=='child_started'))
require('actual_model_and_lidar_visible',bool(survey.get('body_bounds_before')) and (survey.get('moving_frame',{}).get('lidar_overlay') or {}).get('points_uv'))
for role in ('survey','compose'):
    value=data[role];j=value.get('final_task') or {};ev=j.get('events',[]);children=[e for e in ev if e['kind']=='child_completed']
    require(role+'_all_child_stop_epochs_applied',children and all(e.get('new_motion_epoch')==e.get('applied_motion_epoch') for e in children))
    off=value.get('off') or {};row=off.get('robot') or {}
    require(role+'_off_applied_connected_and_points_removed',exact_off(off,j))
    require(role+'_exact_new_final_stop_ack',value.get('stop_history') and all(exact_action(v,j,'stop') for v in value['stop_history']))
    require(role+'_final_disconnect',value['requests'][-1]['request']['action']=='disconnect' and value['requests'][-1]['robot']['connection_state']=='DISCONNECTED')
    require(role+'_not_forged_physical_completion',all(r.get('robot') is None or r['robot'].get('kind')!='physical' for r in value['requests']))
require('compose_exact_goal_and_return',data['compose']['final_task']['state']=='COMPLETED' and data['compose']['final_task']['segments']>=4 and any(e['kind']=='return_verified' for e in data['compose']['final_task']['events']))
require('stop_during_pending_model_no_late_motion',exact_cancel(data['cancel']))
require('cold_all_registered_physical_disconnected',data['cold']['physical_rows'] and all(r['connection_state']=='DISCONNECTED' and not r['live_heartbeat'] and not r['capabilities']['drive'] for r in data['cold']['physical_rows']))
require('media_decoded_original_times',data['media']['status']=='PASS' and data['cold_media']['status']=='PASS')
require('prior_sim_gate_unchanged',sha(ROOT/'outputs/robot-task-20261025-01/acceptance06.json')=='4af379da23c8d81d30b07fb034a70756111d465146ef083209acbf3e457b8006')
require('original_survey_failure_retained',sha(OUT/'survey02/result.json')==data['clearance']['original_result_sha256'] and read(OUT/'survey02/result.json')['status']=='FAIL')
archives=[]
for copyset,launch in [('01','52009edb4a1e49a1ace07dff08622393'),('02','8f7b7ffc2bcd41f69e2ba6dd6d2656c3'),('03','5f3beaa160984999b8c649e7f0816401')]:
    folder=OUT/('runtime-copies'+copyset)/launch;receipt=read(folder/'copy-receipt.json');cleanup=read(folder/'cleanup-receipt.json');engine=read(folder/'engine-result.json')
    exact=[r for r in receipt['files'] if r['status']=='EXACT_COPY'];missing=[r['name'] for r in receipt['files'] if r['status']!='EXACT_COPY']
    require('launch'+copyset+'_original_logs_exact',len(exact)==9 and missing==['engine-liveness-observations.json'] and any(r['name'].startswith('kit_') for r in exact) and all(sha(folder/r['name'])==r['sha256'] for r in exact))
    require('launch'+copyset+'_normal_roots_and_inner_cleanup',cleanup['exit_evidence_complete'] and cleanup['owned_processes_stopped'] and engine['cleanup_status']=='PRE_CLOSE_COMPLETE' and not engine['cleanup_errors'] and all(r['root_disposition']=='EXITED_DURING_GRACE' and r['return_code']==0 and r['evidence_complete'] for r in cleanup['process_exit_observations'].values()))
    archives.append(dict(launch_id=launch,receipt=str((folder/'copy-receipt.json').relative_to(ROOT)),sha256=sha(folder/'copy-receipt.json')))
require('app_closed_no_restored_owner',not (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists())
oldstop=deepcopy(survey['stop']);oldstop['robot']['motion_epoch']=oldstop['robot']['applied_motion_epoch']=oldstop['request']['motion_epoch']
wrongstop=deepcopy(survey['stop']);wrongstop['robot']['operation_id']='different-operation'
oldoff=deepcopy(survey['off']);oldoff['frame']['captured_at_ms']=oldoff['at']-1
wrongoff=deepcopy(survey['off']);wrongoff['frame']['stage_epoch']='different-stage'
latecancel=deepcopy(data['cancel']);latecancel['cancelled']['worker_active']=True
wrongcancel=deepcopy(data['cancel']);wrongcancel['cancelled']['proposal_binding'][2]='different-connection'
negative=dict(missing_ui_rejected=not evaluate_ui({},release),original_failed_ui_rejected=not evaluate_ui(read(OUT/'survey02/result.json'),release),wrong_release_rejected=not evaluate_ui(survey,'different-release'),
    old_stop_epoch_rejected=not exact_action(oldstop,job,'stop'),wrong_stop_operation_rejected=not exact_action(wrongstop,job,'stop'),
    old_off_frame_rejected=not exact_off(oldoff,job),wrong_off_stage_rejected=not exact_off(wrongoff,job),
    unfinished_cancel_worker_rejected=not exact_cancel(latecancel),wrong_cancel_proposal_rejected=not exact_cancel(wrongcancel))
require('gate_rejects_missing_failed_old_release',all(negative.values()))
claims=list((ROOT/'outputs/robot-task-20261025-01/call-claims').glob('*.json'))
usage=[]
for role in ('survey02','survey03','compose01','cancel01'):
    v=read(OUT/role/'result.json');j=v.get('final_task') or v.get('cancelled') or v.get('planning_result')
    ledger=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects'/j['project_id']/'robot-tasks'/j['task_id']/'usage.ledger.json'
    requests=read(ledger)['requests'];usage.append(dict(role=role,task_id=j['task_id'],requests=requests,ledger_sha256=sha(ledger)))
require('approved_text_calls_within_17',len(claims)<=17 and all(len(r['requests'])==1 for r in usage))
value=dict(status='READY_FOR_SUPERVISED_PHYSICAL_LOCAL_TASK_TEST' if all(checks.values()) else 'NOT_READY',
    scope='THIS_PC_EXPLICIT_TEST_ENTRY_SOFTWARE_READINESS_NOT_HARDWARE_OR_WHOLE_ROOM_PASS',checks=checks,passed=sum(checks.values()),total=len(checks),
    release_id=release,source_manifest_sha256=data['installed']['package']['source_manifest_sha256'],
    roles={k:dict(path=str((OUT/p).relative_to(ROOT)),sha256=sha(OUT/p)) for k,p in paths.items()},archives=archives,negative_checks=negative,
    physical_actions=0,hardware_outcomes='NOT_RUN',chassis_accuracy='UNQUALIFIED',world_registration='NOT_QUALIFIED',whole_room_coverage_verified=False,
    text_calls=dict(approved=17,reserved=len(claims),remaining=17-len(claims),this_work=usage),public_release_ready=False,
    next='Fresh user supervision confirmation, explicit physical Connect/Prepare/Arm/bootstrap Stop, then reviewed bounded local survey task.')
with (OUT/('acceptance'+args.attempt+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps({k:v for k,v in value.items() if k not in {'roles','archives','text_calls'}}));sys.exit(0 if all(checks.values()) else 1)
