# SPDX-License-Identifier: Apache-2.0
"""Final installed software gate. This never grants motor authority."""
import argparse,hashlib,json,os,sys
from copy import deepcopy
from pathlib import Path
from roomplan_runtime_copy_gate import check_runtime_copy
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/environment-task-loop-20261025-01'
parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);args=parser.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=dict(installed='installed18.json',tests='tests11/result.json',web='web-tests.json',bundle='bundle01/result.json',
    history='history-linear01.json',opened='open18/result.json',hybrid='hybrid16/result.json',reapply='reapply16/result.json',
    survey='survey18/result.json',session='session18/result.json',compose='compose18/result.json',cancel='cancel18/result.json',
    reopened='open19/result.json',cold='cold18/result.json',robot_cold='robot-cold18/result.json',media='media18.json',cold_media='media19.json',environment_media='media16.json')
data={k:read(OUT/p) for k,p in paths.items()};checks={}
def require(name,v):checks[name]=bool(v)
release=data['installed']['package']['build_id']
def ui(v,expected_release=None):return v.get('status')=='PASS_SCOPED' and not v.get('errors') and bool(v.get('steps')) and all(s.get('status')=='PASS' for s in v['steps']) and v.get('versions',{}).get('engine',{}).get('release_id')==(expected_release or release)

def mandatory_steps(v,names):
    actual=[s.get('name') for s in v.get('steps',[]) if s.get('status')=='PASS']
    return all(actual.count(n)==1 for n in names)
def completed_edit(v):
    p=v.get('preview') or {};q=v.get('ack') or {};t=v.get('transaction') or {};identity=(p.get('operation') or {}).get('operation_id')
    return bool(identity and identity==q.get('operation_id')==t.get('operation_id') and t.get('state')=='COMMITTED'
        and t.get('engine_acknowledged') and t.get('durable_committed') and t.get('current_frame') and p.get('result_revision')==t.get('result_revision'))
def exact_stop(v,j,action='stop'):
    q=v.get('request') or {};a=v.get('ack') or {};r=v.get('robot') or {}
    return bool(q.get('action')==action and q.get('request_id') and q['request_id']==a.get('request_id') and q.get('robot_id')==a.get('robot_id')==r.get('robot_id')==j.get('robot_id')
        and q.get('connection_epoch')==r.get('connection_epoch')==j.get('connection_epoch') and a.get('operation_id')==r.get('operation_id')==j.get('operation_id')
        and a.get('status')=='accepted' and q.get('motion_epoch') and r.get('motion_epoch')!=q['motion_epoch'] and r.get('motion_epoch')==r.get('applied_motion_epoch')
        and r.get('control_state')=='PAUSED' and r.get('connection_state')=='CONNECTED')
require('verified_final_installed_sources',data['installed']['status']=='PASS' and all(data['installed']['checks'].values()))
require('active_tested_release',release in read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')['exe'])
require('python574_no_skips',data['tests']['status']=='PASS' and data['tests']['tests']==574 and not data['tests']['skipped'])
require('field_capable_package_not_sim_only',data['installed']['package']['capabilities']['physical_robot'] is True)
require('web1234_no_skips',data['web']['success'] and data['web']['numPassedTests']==data['web']['numTotalTests']==1234 and not data['web']['numPendingTests'])
require('actual_receiver114_matches',data['bundle']['status']=='PASS' and data['bundle']['members']==114 and data['bundle']['bundle_sha256']==data['installed']['isolated_probe']['bundle_sha256'])
require('new_journal_has_compatible_reader', 'environment-survey-binding-1.0' in data['installed']['package']['data_contract']['read_capabilities'])
previous=read(OUT/'installed16.json');previous_release=previous['package']['build_id']
manifest16=read(OUT/'build16/dist/TwinPulse/_internal/resources/source-manifest.json')
manifest17=read(OUT/'build18/dist/TwinPulse/_internal/resources/source-manifest.json')
difference={p for p in set(manifest16)|set(manifest17) if manifest16.get(p)!=manifest17.get(p)}
require('unchanged_environment_feature_full_source_closure',previous['status']=='PASS'
    and hashlib.sha256(json.dumps(manifest16,sort_keys=True).encode()).hexdigest()==previous['package']['source_manifest_sha256']
    and hashlib.sha256(json.dumps(manifest17,sort_keys=True).encode()).hexdigest()==data['installed']['package']['source_manifest_sha256']
    and difference=={'packages/twinpulse_core/src/twinpulse_core/robot_task_plan.py','packages/twinpulse_provider/src/twinpulse_provider/robot_task_planner.py',
        'packages/twinpulse_app/src/twinpulse_app/robot_task_service.py'})
for k in ('opened','hybrid','reapply','survey','session','compose','cancel','reopened','cold','robot_cold'):
    require(k+'_version_bound_ui',ui(data[k],previous_release if k in {'hybrid','reapply'} else release))
    require(k+'_no_hardware_actions',data[k].get('physical_actions',data[k].get('hardware_actions'))==0)
h=data['hybrid'];a=data['reapply'];s=data['survey'];j=s['final_task'];ss=data['session'];c=data['cancel'];cj=c['cancelled']
recovery=read(OUT/'recover15b/result.json')
require('historical_transport_recovery_scoped_not_final_source_claim',recovery['status']=='PASS_SCOPED'
    and recovery['versions']['engine']['release_id']==read(OUT/'installed15.json')['package']['build_id']
    and recovery['transaction']['state']=='ROLLED_BACK' and recovery['transaction']['compensation_acknowledged']
    and recovery['transaction']['current_frame'] and len(recovery['requests'])==1 and recovery['requests'][0]['status']==202)
require('original_failure_condition_repeated_in_full_hybrid',len(h['edits'])==3 and all(completed_edit(e) for e in h['edits']) and h['steps'][0]['name'].startswith('Remove the estimated prop'))
require('multi_position_original_returns_identified',h['selected']['candidate']['return_count']>=6 and len(h['selected']['candidate']['view_indices'])>=2 and h['selected']['candidate']['view_baseline_m']>=.1)
require('actual_new_photo_model_and_manual_association',h['photo_request']['job_id']==h['photo']['job_id'] and h['photo']['status']=='ready' and h['selected']['photo']['kind']=='basket' and h.get('photo_claim'))
require('saved_survey_visible_on_exact_live_frame',h['frames'] and all(v['dom']['live']=='true' and v['dom']['id']==v['frame']['frame_id'] and v['dom']['stamp']==v['frame']['captured_at_ms'] and v['frame']['alignment_overlay']['source']=='SAVED' for v in h['frames']))
proof=h['edits'][1]['transaction'].get('sensor_binding') or {}
require('collected_raw_bound_to_common_apply',proof.get('policy')=='review_survey_obstacle' and proof.get('physical_authority') is False and proof.get('candidate_id')==h['selected']['candidate']['candidate_id'])
for package in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(ROOT/'packages'/package/'src'))
from twinpulse_app.task_collection import TaskCollection
from twinpulse_core import canonical_sha256
project=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/projects/chat_mvmcf9wa_18f1e6d1'
def collection_lineage(v,edit):
    binding=edit['transaction'].get('sensor_binding') or {};review=v['reviews'][-1];p=edit['preview'];job=review['job']['job_id']
    if binding.get('job_id')!=job:return False
    folder=project/'environment-imports/survey-reviews'/job
    collection=read(folder/'collection.json');derived=read(folder/'result.json')
    original=read(OUT/'survey01/result.json')['final_task']
    new=TaskCollection(project/'robot-tasks',original['project_id']).load(original['task_id'])
    requests=[r for r in v['requests'] if r['request'].get('action')=='preview_obstacle']
    photo=v['photo'];photo_folder=project/'environment-imports/photo-proposals'/photo['job_id']
    adoption=read(photo_folder/'adoptions'/(p['operation']['operation_id']+'.json'))
    photo_job=read(photo_folder/'job.json');photo_record=photo_job.pop('record_sha256')
    # The renderer JSON log normalizes 1.0 to 1. Hash the retained Python
    # journal bytes' typed operation; also require equal observed UI content.
    operation=next(o for o in read(project/'project.scene-changes.json')['operations'] if o['operation_id']==p['operation']['operation_id'])
    return bool(collection==new and collection['task_id']==original['task_id']
        and len(collection['frames'])==derived['view_count']==14 and sha(folder/'collection.json')==binding['collection_sha256']
        and sha(folder/'result.json')==binding['result_sha256']==review['review_digest']
        and canonical_sha256(collection['frames'])==derived['frames_sha256']
        and operation==p['operation'] and p['preview_digest']==binding['preview_sha256']==canonical_sha256(operation)
        and binding['context']['current_scene_revision']==p['parent_revision']==review['context']['scene_revision']
        and derived['context']==review['context'] and derived['source']=='TASK'
        and any(r['status']==200 and r['body'].get('preview')==p
            and r['request']['candidate_id']==binding['candidate_id']
            and r['request']['candidate_ref']==dict(job_id=photo['job_id'],candidate_id=v['selected']['photo']['id']) for r in requests)
        and adoption['operation_id']==p['operation']['operation_id'] and adoption['preview_digest']==p['preview_digest']
        and adoption['job_id']==photo['job_id'] and adoption['candidate_id']==v['selected']['photo']['id']
        and adoption['response_sha256']==photo['response_sha256'] and adoption['photo_sha256']==photo['photo']['sha256']
        and adoption['candidate']=={k:v['selected']['photo'][k] for k in adoption['candidate']}
        and adoption['reviewed_scene_revision']==p['parent_revision']
        and sha(photo_folder/'result.json')==photo['response_sha256']
        and photo_record==canonical_sha256(photo_job) and photo_job['job_id']==photo['job_id']
        and photo_job['project_id']==collection['project_id'] and photo_job['input_revision']==binding['context']['input_revision']
        and photo_job['source_sha256']==adoption['source_sha256']=='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b'
        and photo_job['photo']['sha256']==photo['photo']['sha256']=='4bae813cf9ec1b0dff9b1ba6caf9af09155b274c5b99da313b4060ad14636b7f')
require('raw_task_derived_photo_preview_apply_full_lineage',collection_lineage(h,h['edits'][1]))
require('raw_task_reapply_full_lineage',collection_lineage(a,a['edits'][0]))
require('apply_undo_reapply_revision_chain',h['edits'][1]['preview']['parent_revision']==h['edits'][0]['transaction']['result_revision']
    and h['edits'][2]['preview']['parent_revision']==h['edits'][1]['transaction']['result_revision']
    and a['edits'][0]['preview']['parent_revision']==h['edits'][2]['transaction']['result_revision']
    and h['edits'][2]['preview']['operation']['mode']=='undo')
from dataclasses import replace
from twinpulse_app.project_store import ProjectStore
from twinpulse_app.scene_changes import SceneChangeHistory
source=ProjectStore.for_project(project.parent.parent,project.name).load().site_draft
history=SceneChangeHistory.from_dict(read(project/'project.scene-changes.json'),source,project.name)
def environment_at(revision):
    if revision==history.source_scene_revision:operations=()
    else:
        index=next(i for i,o in enumerate(history.operations) if o.result_revision==revision)
        operations=history.operations[:index+1]
    return replace(history,operations=operations,current_scene_revision=revision).effective(source).site.scene.environment
require('undo_restored_exact_pre_adoption_geometry',environment_at(h['edits'][1]['preview']['parent_revision'])==environment_at(h['edits'][2]['preview']['result_revision']))
require('reapply_preserved_all_original_meshes',environment_at(a['edits'][0]['preview']['result_revision'])['meshes']==source.site.scene.environment['meshes'])
require('reapply_saved_new_revision',len(a['edits'])==1 and completed_edit(a['edits'][0]))
revision=a['edits'][0]['transaction']['result_revision']
def bound_frame(frame,binding,robot_id):
    return ([frame.get(k) for k in ('engine_session_id','stage_epoch','applied_revision')]==binding
        and any(r.get('robot_id')==robot_id and r.get('visible') for r in frame.get('robot_anchors',[])))
require('new_revision_has_fresh_plan_not_old_resume',j['scene_binding'][2]==revision and j['environment_source']['scene_revision']==revision and s['proposal']['source_state_sha256']==j['source_state_sha256'])
original_compose=read(OUT/'compose17/result.json');condition=data['compose'].get('original_failed_condition') or {}
require('original_failed_compound_condition_repeated',original_compose['status']=='FAIL'
    and condition.get('path')=='outputs/environment-task-loop-20261025-01/compose17/result.json'
    and condition.get('sha256')==sha(OUT/'compose17/result.json')
    and condition.get('task_id')==original_compose['proposal']['task_id']
    and condition.get('text')==original_compose['proposal']['text']==data['compose']['proposal']['text']
    and condition.get('pose')==original_compose['start']['pose']['position_m'])
for role in ('survey','compose'):
    v=data[role];job=v['final_task'];events=job['events'];children=[e for e in events if e['kind']=='child_completed'];off=v.get('off') or {};r=off.get('robot') or {};frame=off.get('frame') or {}
    require(role+'_multi_child_return_stop',job['state'] in {'PARTIAL','COMPLETED'} and len(children)>=2 and any(e['kind']=='return_verified' and e['position_error_m']<=.04 and e['yaw_error_rad']<=.04 for e in events) and any(e['kind']=='stop_confirmed' for e in events) and not job.get('stop_error'))
    require(role+'_child_stop_epochs_applied',children and all(e['new_motion_epoch']==e['applied_motion_epoch'] for e in children))
    require(role+'_exact_stop',v.get('stop_history') and all(exact_stop(e,job) for e in v['stop_history']))
    require(role+'_off_applied_and_display_removed',exact_stop(off,job,'lidar') and off['request'].get('payload')=={'enabled':False} and r.get('lidar_state')=='OFF' and r.get('scan') is None and not frame.get('lidar_overlay') and not frame.get('alignment_overlay') and frame.get('captured_at_ms',0)>off.get('at',float('inf')) and bound_frame(frame,job['scene_binding'],job['robot_id']))
    require(role+'_disconnect',v['requests'][-1]['request'].get('action')=='disconnect' and v['requests'][-1]['robot']['connection_state']=='DISCONNECTED')
require('survey_genuine_moving_collection_not_whole_room_claim',j['distance_m']>1.5 and j['measured_coverage']['observations']>=3 and j['whole_room_coverage_verified'] is False and s['moving_frame']['lidar_overlay']['points_uv'] and s['body_bounds_before'])
require('current_check_did_not_auto_register',ss['checked']['review']['source']=='CURRENT' and ss['checked']['job']['status']=='GEOMETRIC_REVIEW' and not ss['checked']['registration_active'])
require('explicit_current_registration_no_duplicate_body',ss['registered']['registration_active'] and all(v['frame']['alignment_overlay']['source']=='CURRENT' and v['frame']['alignment_overlay']['body_bounds_uv'] is None and v['dom']['id']==v['frame']['frame_id'] for v in (ss['before_frame'],ss['after_frame'])))
require('finite_pose_change_then_current_scan',abs(ss['after']['pose']['position_m'][2]-ss['start']['pose']['position_m'][2])>.1 and ss['after_frame']['frame']['captured_at_ms']>ss['before_frame']['frame']['captured_at_ms'])
def current_scan(v,after=False):
    receipt=v['after_frame' if after else 'before_frame'];frame=receipt['frame'];dom=receipt['dom'];scan=receipt.get('scan') or {};o=frame.get('alignment_overlay') or {};start=v['start'];command=v.get('command') or {};completed=command.get('completed') or {}
    return bool(dom['live']=='true' and dom['id']==frame['frame_id'] and dom['stamp']==frame['captured_at_ms']
        and bound_frame(frame,j['scene_binding'],start['robot_id']) and o.get('source')=='CURRENT'
        and o.get('review_id')==v['checked']['job']['job_id'] and o.get('body_bounds_uv') is None and o.get('points_uv')
        and [scan.get(k) for k in ('robot_id','connection_epoch','operation_id')]==[start.get(k) for k in ('robot_id','connection_epoch','operation_id')]
        and scan.get('scan_identity',[None,None,None])[2]==o.get('original_captured_at_ms')
        and (not after or (command['request']['action']=='command' and command['request']['request_id']==command['ack']['request_id']==completed['command']['request_id']
            and completed['command']['state']=='COMPLETED' and completed['applied_motion_epoch']==completed['motion_epoch']==scan['applied_motion_epoch']
            and (scan.get('command') or {}).get('request_id')==command['request']['request_id']
            and o['original_captured_at_ms']>command['completed_received_at'])))
require('current_points_exact_owner_frame_and_post_completion_capture',current_scan(ss) and current_scan(ss,True))
require('session_explicitly_cleared',not ss['cleared']['registration_active'] and not ss['cleared']['visible'])
require('session_exact_stop_off_disconnect',exact_stop(ss['stop'],ss['start']) and exact_stop(ss['off'],ss['start'],'lidar') and ss['off']['robot']['lidar_state']=='OFF' and ss['off']['frame']['captured_at_ms']>ss['off']['at'] and not ss['off']['frame'].get('alignment_overlay') and not ss['off']['frame'].get('lidar_overlay') and ss['disconnected']['connection_state']=='DISCONNECTED')
require('session_off_preserves_exact_body_on_current_scene',bound_frame(ss['off']['frame'],j['scene_binding'],ss['start']['robot_id']))
task_steps=['Select existing registered TurtleBot3 SIM only','Explicit SIM Connect Prepare with current engine epoch',
    'Camera frames the actual robot body before the task','Natural goal through Robot command waits three seconds before Enter',
    'One approved text-only configured planner request','Final exact Stop LiDAR OFF Disconnect without physical calls']
for role in ('survey','compose','cancel'):
    require(role+'_mandatory_full_journey',mandatory_steps(data[role],task_steps+[
        'Stop after planner submission prevents late execution' if role=='cancel' else
        'Explicit exact-plan Run uses measured child results and observations']))
session_steps=['Explicit existing SIM Connect Prepare and actual LiDAR on',
    'Three new stationary observations checked with explicit SIM pose and wall span',
    'Use session alignment explicitly attaches current points without a duplicate body',
    'Ordinary finite command changes actual pose then fresh registered scan uses that pose',
    'Exact Stop and OFF remove registered sensor display while preserving connection',
    'Explicit Disconnect and clearing alignment leave no physical authority']
require('session_mandatory_full_journey',mandatory_steps(ss,session_steps))
def exact_cancel(v):
    job=v.get('cancelled') or {};binding=job.get('proposal_binding') or [];start=v.get('start') or {}
    if len(binding)!=5:return False
    owner=dict(robot_id=job.get('robot_id'),connection_epoch=binding[2],operation_id=binding[3])
    return (binding[:4]==[start.get('robot_id'),'sim',start.get('connection_epoch'),start.get('operation_id')]
        and v.get('cancel_at_state')=='PLANNING' and v.get('cancel_worker_active') and job.get('state')=='CANCELLED'
        and job.get('reason')=='models stage cancelled; output ignored' and not job.get('worker_active') and not job.get('stop_error')
        and job.get('segments')==0 and not any(e['kind']=='child_started' for e in job.get('events',[]))
        and len(v.get('stop_history',[]))==2 and all(exact_stop(s,owner) for s in v['stop_history']))
require('stop_during_model_no_late_execution',exact_cancel(c))
cold=data['cold']['cold']
require('same_review_cold_hidden_no_registration',cold['job']['status']=='SAVED' and cold['job']['job_id']==ss['checked']['job']['job_id'] and cold['review_digest']==ss['checked']['review_digest'] and not cold['registration_active'] and not cold['visible'])
require('cold_physical_disconnected_no_drive',data['robot_cold']['physical_rows'] and all(r['connection_state']=='DISCONNECTED' and not r['live_heartbeat'] and not r['capabilities']['drive'] for r in data['robot_cold']['physical_rows']))
require('history_failure_fixed_without_rewrite',data['history']['status']=='PASS' and all(data['history']['checks'].values()) and read(OUT/'hybrid09/result.json')['status']=='FAIL')
def bound_media(report,runs):
    videos=report.get('videos') or []
    if report.get('status')!='PASS' or len(videos)!=len(runs) or {v.get('name') for v in videos}!=set(runs):return False
    for v in videos:
        run=v['name'];result=read(OUT/run/'result.json');record=result.get('video') or result.get('recording') or {}
        relative=Path(run)/record.get('path','');video=(OUT/relative).resolve()
        if not video.is_relative_to(OUT.resolve()) or not video.is_file():return False
        if (Path(v.get('path',''))!=relative or v.get('bytes')!=video.stat().st_size or v.get('sha256')!=sha(video)
            or v.get('decode_return_code')!=0 or v.get('contact_return_code')!=0 or v.get('decode_stderr')
            or v.get('contact_stderr') or v.get('original_packet_timestamps_strict') is not True
            or not v.get('original_time_base') or v.get('frames',0)<=1
            or v.get('recorded_wall_s')!=record.get('wall_ms',-1)/1000
            or abs(v.get('duration_s',-10)-v['recorded_wall_s'])>=2):return False
    return True
media_runs=dict(media=('open18','survey18','session18','compose18','cancel18'),
    cold_media=('open19','cold18','robot-cold18'),environment_media=('open16','hybrid16','reapply16'))
require('media_original_timestamps_decode_exact_journey',all(bound_media(data[k],runs) for k,runs in media_runs.items()))
require('compact_english_no_overflow',all(v['scroll']<=v['client']+1 for v in h['layout']+a['layout']))
require('original_usd_unchanged',sha(Path('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd'))=='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b')
require('original_photo_unchanged',sha(Path('C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg'))=='4bae813cf9ec1b0dff9b1ba6caf9af09155b274c5b99da313b4060ad14636b7f')
archives=[]
def normal_roots(cleanup,owned,engine):
    roles=cleanup.get('process_exit_observations',{})
    return (set(roles)=={'backend','engine'} and owned.get('roles')==roles and owned.get('evidence_complete') is True
        and cleanup.get('exit_evidence_complete') and cleanup.get('owned_processes_stopped')
        and engine.get('cleanup_status')=='PRE_CLOSE_COMPLETE' and not engine.get('cleanup_errors')
        and all(v.get('role')==k and v.get('root_disposition')=='EXITED_DURING_GRACE'
            and v.get('return_code')==0 and v.get('evidence_complete') for k,v in roles.items()))
for copyset in ('16','18','19'):
    folders=list((OUT/('runtime-copies'+copyset)).glob('*'));require('launch'+copyset+'_one_archive',len(folders)==1)
    folder=folders[0];receipt=read(folder/'copy-receipt.json');cleanup=read(folder/'cleanup-receipt.json');engine=read(folder/'engine-result.json');exact=[r for r in receipt['files'] if r['status']=='EXACT_COPY']
    roles=('hybrid','reapply') if copyset=='16' else ('opened','survey','session','compose','cancel') if copyset=='18' else ('reopened','cold','robot_cold')
    require('launch'+copyset+'_ui_original_archive_identity',all(data[k]['versions']['engine']['launch_id']==folder.name for k in roles)
        and receipt['launch_id']==cleanup['launch_id']==folder.name and engine.get('launch_id')==folder.name)
    require('launch'+copyset+'_exact_original_logs',not check_runtime_copy(folder,folder.name,receipt))
    require('launch'+copyset+'_normal_roots_inner_cleanup',normal_roots(cleanup,read(folder/'owned-exit-observations.json'),engine))
    archives.append(dict(path=str(folder.relative_to(ROOT)),receipt_sha256=sha(folder/'copy-receipt.json')))
require('app_closed_no_owner',not (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists())
claims=sorted((OUT/'call-claims').glob('*.json'));require('within_50_new_calls',len(claims)<=50 and read(OUT/'approval.json')['additional_max_requests']==50)
oldstop=deepcopy(s['stop']);oldstop['robot']['motion_epoch']=oldstop['robot']['applied_motion_epoch']=oldstop['request']['motion_epoch']
badedit=deepcopy(h['edits'][1]);badedit['transaction']['current_frame']=False
neg=dict(no_ui_rejected=not ui({}),failed_ui_rejected=not ui(read(OUT/'hybrid09/result.json')),missing_frame_rejected=not completed_edit(badedit),old_stop_rejected=not exact_stop(oldstop,j))
missing=deepcopy(ss);missing['steps']=missing['steps'][:-1]
wrong_capture=deepcopy(ss);wrong_capture['after_frame']['frame']['alignment_overlay']['original_captured_at_ms']=ss['command']['completed_received_at']-1
failed_photo=deepcopy(h)
for r in failed_photo['requests']:
    if r['request'].get('action')=='preview_obstacle':r['status']=400
bad_undo=deepcopy(h['edits'][2]);bad_undo['preview']['operation']['mode']='change'
neg.update(missing_session_step_rejected=not mandatory_steps(missing,session_steps),
    precompletion_points_rejected=not current_scan(wrong_capture,True),
    failed_photo_request_rejected=not collection_lineage(failed_photo,failed_photo['edits'][1]),
    empty_cleanup_roles_rejected=not normal_roots(dict(process_exit_observations={}),{},engine),
    missing_engine_role_rejected=not normal_roots(dict(cleanup,process_exit_observations={'backend':cleanup['process_exit_observations']['backend']}),read(folder/'owned-exit-observations.json'),engine),
    non_undo_rejected=bad_undo['preview']['operation']['mode']!='undo')
bad_media=deepcopy(data['media']);bad_media['videos'][2]['path']='session17b/recording/app-screen.mp4'
bad_media_sha=deepcopy(data['media']);bad_media_sha['videos'][2]['sha256']='0'*64
duplicate_media=deepcopy(data['media']);duplicate_media['videos'][2]=duplicate_media['videos'][0]
missing_media=deepcopy(data['media']);missing_media['videos']=missing_media['videos'][:-1]
neg.update(failed_journey_video_rejected=not bound_media(bad_media,media_runs['media']),
    wrong_video_sha_rejected=not bound_media(bad_media_sha,media_runs['media']),
    duplicate_video_role_rejected=not bound_media(duplicate_media,media_runs['media']),
    missing_video_role_rejected=not bound_media(missing_media,media_runs['media']))
require('gate_negative_omissions_rejected',all(neg.values()))
value=dict(status='READY_FOR_SUPERVISED_FIELD_TEST' if all(checks.values()) else 'NOT_READY',scope='FINAL_INSTALLED_PC_ENVIRONMENT_TASK_LOOP_NOT_HARDWARE_QUALIFICATION',
    checks=checks,passed=sum(checks.values()),total=len(checks),release_id=release,source_manifest_sha256=data['installed']['package']['source_manifest_sha256'],
    roles={k:dict(path=str((OUT/p).relative_to(ROOT)),sha256=sha(OUT/p)) for k,p in paths.items()},archives=archives,negative_checks=neg,
    evidence_versions=dict(environment=previous_release,final_task_and_cold=release,changed_sources=sorted(difference),
        boundary='Environment feature is byte-identical; source16 hybrid is not falsely labelled source18. New planner, SIM post-persistence fresh-snapshot check and full task/cold journeys require source18.'),
    calls=dict(additional_approved=50,reserved=len(claims),remaining=50-len(claims),unknown_failed_count_as_used=True),
    physical_actions=0,physical_outcomes='NOT_RUN',chassis_accuracy='UNQUALIFIED',whole_room_coverage_verified=False,physical_world_registration='FIELD_REFERENCE_AND_CURRENT_SENSOR_REQUIRED',
    native_start_double_click='NOT_RUN_IDENTICAL_ENTRY_SCRIPT_EXECUTED',public_release_ready=False,
    next='Fresh supervision confirmation; actual Connect/Prepare/LiDAR/voltage/Arm/bootstrap Stop; bounded moving collection. Review measured wall span and initial pose before optional session alignment and semantic navigation.')
with (OUT/('acceptance'+args.attempt+'.json')).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps({k:v for k,v in value.items() if k not in {'roles','archives'}}));sys.exit(0 if all(checks.values()) else 1)
