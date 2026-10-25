# SPDX-License-Identifier: Apache-2.0
"""Scoped evidence gate; original failures and missing global alignment remain."""
from copy import deepcopy
import hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'outputs/environment-photo-live-20261024-01'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def required_steps(value,names):
    seen={s['name'] for s in value['steps'] if s['status']=='PASS'}
    return set(names)<=seen
ui=read(out/'ui01/result.json');adopt=read(out/'adopt04/result.json');cold=read(out/'cold07/result.json');sim=read(out/'sim05/result.json')
audit=read(out/'job-audit03/audit.json');job=audit['jobs'][0];jobdir=out/'job-audit03'/job['job_id'];usage=read(jobdir/'usage.ledger.json')
env=adopt['preview']['operation']['tool_call']['arguments']['environment'];base=read(root/'outputs/roomplan-lidar-review-20261024-02/environment.json')
receipt=read(jobdir/'adoptions'/(adopt['preview']['operation']['operation_id']+'.json'))
checks=dict(
    one_actual_observer_call=audit['total_requests']==len(usage['requests'])==1 and usage['requests'][0]['status']=='received',
    within_approved_ten=audit['total_requests']<=len(list((out/'call-claims').glob('*.json')))<=read(out/'allowance.json')['max_calls']==10,
    same_original_usd=env['source_sha256']==job['source_sha256']==base['source_sha256'],
    original_thirty_meshes_preserved=len(env['meshes'])==30 and env['meshes']==base['meshes'],
    photo_and_response_bound=receipt['photo_sha256']==job['photo_sha256'] and receipt['response_sha256']==job['response_sha256']==sha(jobdir/'result.json'),
    exact_current_adoption=receipt['operation_id']==adopt['preview']['operation']['operation_id'] and receipt['preview_digest']==adopt['preview']['preview_digest'],
    photo_candidates_three=ui['status']=='PASS_SCOPED' and len(ui['proposal']['candidates'])==3,
    cold_restores_same_genuine_job=cold['status']=='PASS_SCOPED' and cold['proposal']['job_id']==job['job_id'] and cold['proposal']['response_sha256']==job['response_sha256'],
    cold_no_extra_model_action=not any(r.get('action')=='photo_analyze' for r in cold['responses']),
    cold_same_final_revision=cold['environment']['scene_revision']==adopt['preview']['result_revision'],
    cold_same_overlay=next(o for o in cold['environment']['objects'] if o.get('added'))['id']==env['overlays'][0]['item']['id'],
    final_sim_journey=sim['status']=='PASS_SCOPED' and required_steps(sim,['Explicit TurtleBot3 SIM registration at test pose','SIM Connect Prepare LiDAR and visible composed sensor first hit','Finite SIM turn and exact Stop OFF Disconnect']),
    current_command_completed=sim['motion']['command']['state']=='COMPLETED',
    scan_bound_to_adopted_scene=sim['scan']['scan']['twin_context']==sim['scan']['source_twin_context']==sim['scan']['current_twin_context']
        and sim['scan']['current_twin_context']['scene_revision']==adopt['preview']['result_revision']
        and sim['scan']['current_twin_context']['project_id']==ui['project_id'],
    off_has_no_scan=sim['off']['lidar_state']=='OFF' and sim['off']['scan'] is None,
    separate_stage_same_algorithm_replay=read(out/'usd02/result.json')['status']=='PASS_SIM_GEOMETRY' and read(out/'usd02/result.json')['sim_result_sha256']==sha(out/'sim05/result.json'),
    focused_contracts=read(out/'focused05/result.json')['status']=='PASS',
    old_failure_retained=read(root/'outputs/environment-photo-20261024-01/ui01/result.json')['status']=='FAIL',
    no_launcher_lock=not (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists(),
)
# An SDK-only diagnostic wrote unmanifested bytecode into the installed tree.
# Recovery moves precisely inventoried extras, never changes the allowlist.
spec=importlib.util.spec_from_file_location('tp_package_check',root/'packages/twinpulse_app/src/twinpulse_app/windows_package.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
installation=read(out/'installation04.json');package=Path(installation['receipt']['exe']).parent
verified=module.verify_package(package)
checks['current_installed_package_exact']=verified==installation['verification'] and verified['files']==1690
cache=read(out/'cache-quarantine-inventory.json');quarantine=(out/'cache-quarantine').resolve()
old_package=Path(read(out/'installation03.json')['receipt']['exe']).parent
checks['original_package_exact_after_probe_recovery']=module.verify_package(old_package)==read(out/'installation03.json')['verification']
checks['diagnostic_bytecode_preserved_not_deleted']=len(cache)==114 and sum(c['bytes'] for c in cache)==2390858 and all(
    Path(c['source']).resolve().is_relative_to(old_package.resolve()) and not Path(c['source']).exists()
    and Path(c['target']).resolve().is_relative_to(quarantine) and sha(Path(c['target']))==c['sha256'] for c in cache)
for case in ('adopt01','adopt02','adopt03','adopt04','undo01','undo02','undo03'):
    v=read(out/case/'result.json');p=v['preview'];op=p['operation']['operation_id']
    tx=next(r['body'] for r in reversed(v['responses']) if r['path']=='/v1/product/scene-edit/transaction' and r.get('body',{}).get('operation_id')==op)
    checks[case+'_exact_commit']=v['status']=='PASS_SCOPED' and all(tx[k] is True for k in ('engine_acknowledged','durable_committed','current_frame')) and tx['result_revision']==p['result_revision'] and tx['state']=='COMMITTED'
def exact_stop_applied(value):
    before=value.get('before_stop',{});receipt=value.get('stop_receipt',{});after=value.get('stop',{})
    request=receipt.get('request',{});ack=receipt.get('ack',{});accepted=receipt.get('accepted',{})
    rid=before.get('robot_id');epoch=accepted.get('motion_epoch')
    stops=[r for r in value['responses'] if r.get('request',{}).get('request_id')==request.get('request_id') and r.get('request',{}).get('action')=='stop']
    if len(stops)!=1 or not epoch or not rid:return False
    stop=stops[0]
    return (request.get('action')=='stop' and receipt.get('status')==stop['status']==200
        and request==stop['request'] and ack==stop['body']['last_command']
        and accepted==next((r for r in stop['body']['robots'] if r['robot_id']==rid),None)
        and ack.get('request_id')==request.get('request_id') and ack.get('robot_id')==rid and ack.get('status')=='accepted'
        and request.get('robot_id')==accepted.get('robot_id')==after.get('robot_id')==rid
        and before.get('connection_epoch')==request.get('connection_epoch')==accepted.get('connection_epoch')==after.get('connection_epoch')
        and bool(before.get('connection_epoch')) and before.get('motion_epoch')==request.get('motion_epoch')!=epoch
        and after.get('motion_epoch')==after.get('applied_motion_epoch')==epoch and after.get('control_state')=='PAUSED')
checks['exact_stop_ack_and_new_applied_epoch']=exact_stop_applied(sim)
stale=deepcopy(sim);stale['stop']=stale['before_stop'];checks['stale_paused_stop_negative']=not exact_stop_applied(stale)
checks['sim04_stop_gap_retained']=not exact_stop_applied(read(out/'sim04/result.json')) and read(out/'sim04-review.json')['exact_stop_engine_applied_accepted'] is False
checks['original_cold05_and_gate_failure_retained']=read(out/'cold05/result.json')['status']==read(out/'acceptance01.json')['status']=='FAIL'
checks['disconnect_ack']=any(r.get('request',{}).get('action')=='disconnect' and r['body']['last_command']['request_id']==r['request']['request_id'] for r in sim['responses'] if r['path']=='/v1/product/robot-fleet' and 'request' in r)
visual=read(out/'visual-review02.json');checks['pixels_checked']=all(sha(out/i['path'])==i['sha256'] for i in visual['images']) and visual['robot_body_and_sensor_hits_visible'] and visual['off_removes_hits_and_active_status']
for folder in sorted(out.glob('runtime-copies*/*')):
    v=read(folder/'owned-exit-observations.json');copy=read(folder/'copy-receipt.json')
    inner=read(folder/'engine-result.json')
    checks[folder.parent.name+'_natural_roots']=v['evidence_complete'] and all(v['roles'][r]['evidence_complete'] and not v['roles'][r]['errors'] and v['roles'][r]['return_code']==0 and v['roles'][r]['root_disposition']=='EXITED_DURING_GRACE' for r in ('backend','engine'))
    checks[folder.parent.name+'_inner_cleanup']=inner['cleanup_status']=='PRE_CLOSE_COMPLETE' and inner['cleanup_errors']==[]
    checks[folder.parent.name+'_copies']=all(sha(folder/i['name'])==i['sha256'] for i in copy['files'] if i['status']=='EXACT_COPY')
for case,copy_set in [('cold06','06'),('cold07','07')]:
    v=read(out/case/'result.json');engine=v['versions']['engine'];launch=engine['launch_id'];folder=out/('runtime-copies'+copy_set)/launch
    checks[case+'_same_release_and_bound_normal_exit']=(v['status']=='PASS_SCOPED' and engine['release_id']==verified['build_id']
        and (folder/'owned-exit-observations.json').is_file() and read(folder/'owned-exit-observations.json')['launch_id']==launch
        and read(out/('exit'+copy_set)/'result.json')['status']=='PASS'
        and v['proposal']['job_id']==job['job_id'] and v['proposal']['response_sha256']==job['response_sha256']
        and v['environment']['scene_revision']==adopt['preview']['result_revision'] and not any(r.get('action')=='photo_analyze' for r in v['responses']))
checks['sim_same_current_release_and_launch']=sim['versions']['engine']==read(out/'cold06/result.json')['versions']['engine']
checks['seven_launches_archived']=len(list(out.glob('runtime-copies*/*/owned-exit-observations.json')))==7
decodes=[]
for p in sorted(out.glob('*/recording/app-screen.mp4')):
    r=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',str(p),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','NUL'],capture_output=True)
    decodes.append(dict(path=str(p.relative_to(out)),exit_code=r.returncode,error=r.stderr.decode('utf-8',errors='replace')))
checks['all_recordings_decode']=bool(decodes) and all(r['exit_code']==0 for r in decodes)
checks['accepted_recordings_no_decode_warning']=all(not r['error'] for r in decodes if Path(r['path']).parts[0] in {'ui01','adopt04','sim05'})
pts=[]
for case in ('ui01','adopt04','sim05'):
    p=out/case/'recording/app-screen.mp4'
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(p)],capture_output=True)
    values=[float(f['best_effort_timestamp_time']) for f in json.loads(probe.stdout)['frames']]
    ok=probe.returncode==0 and len(values)>2 and all(b>a for a,b in zip(values,values[1:]))
    pts.append(dict(case=case,frames=len(values),strict_monotonic=ok,first=values[0],last=values[-1]))
checks['accepted_recordings_strict_pts']=all(v['strict_monotonic'] for v in pts)
checks['accepted_original_packet_times_and_duration']=read(out/'media-checks01.json')['status']=='PASS'
# A previously labelled step PASS must not bypass a newly mandatory journey step.
negative=deepcopy(sim);negative['steps']=[s for s in negative['steps'] if s['name']!='Explicit TurtleBot3 SIM registration at test pose']
checks['missing_entry_negative']=not required_steps(negative,['Explicit TurtleBot3 SIM registration at test pose'])
result=dict(status='PASS_PHOTO_PROPOSAL_ADOPTION_AND_SIM_SCOPE' if all(checks.values()) else 'FAIL',checks=checks,
    actual_observer_calls=1,approved_maximum=10,remaining=9,project_id=ui['project_id'],job_id=job['job_id'],response_sha256=job['response_sha256'],
    automatic_metric_photo_alignment=False,physical_world_registration=False,physical_qualification=False,all_obstacles_detected=False,
    scope='Actual single observer result, explicit test adoption/Undo/cold reopen, visible SIM body and geometric LiDAR. Not full submitted demo or real robot readiness.',
    installed_verification=verified,diagnostic_probe_cache_files_quarantined=len(cache),decodes=decodes,pts=pts)
with (out/(sys.argv[1] if len(sys.argv)>1 else 'acceptance02.json')).open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(result));raise SystemExit(0 if all(checks.values()) else 1)
