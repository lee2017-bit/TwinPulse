# SPDX-License-Identifier: Apache-2.0
"""Scoped installed alignment evidence gate. Prior failures remain failures."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'outputs/environment-alignment-20261024-01'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_package import verify_package
active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json');release=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'/Path(active['exe']).parent
verified=verify_package(release);ui=read(out/'ui06/result.json');cold=read(out/'cold05/result.json');probe=read(out/'saved-sim02/result.json');visual=read(out/'visual-review01.json')
def steps(v,names):return v['status']=='PASS_SCOPED' and set(names)<={s['name'] for s in v['steps'] if s['status']=='PASS'}
required=['Register explicit built-in TurtleBot3 SIM at test pose','SIM Connect Prepare and original LiDAR acquisition','Explicit approximate pose and SIM-only reference then fixed heldout review','Explicit review body and scan projected into current Isaac frame','Single explicit SIM forward command and scan tracking at moved pose','Exact fresh Stop before LiDAR OFF removes alignment and Disconnect']
checks=dict(final_ui=steps(ui,required),missing_step_negative=not steps({**ui,'steps':ui['steps'][:-1]},required),
    same_final_release=all(v['versions']['engine']['release_id']==verified['build_id'] for v in (ui,cold)),
    cold_journey=steps(cold,['Cold review hidden with no restored robot connection','Explicit historical scan show uses saved pair and no authority']),
    cold_same_job=cold['saved_review']['review']['job_id']==ui['review']['review']['job_id'] and cold['saved_review']['review_digest']==ui['review']['review_digest'],
    sources_distinct=ui['current_overlay']['source']=='CURRENT' and cold['saved_overlay']['source']=='SAVED',
    no_authority=not ui['review']['physical_authority'] and not cold['saved_review']['physical_authority'],
    sim_truth_only=probe['status']=='PASS_SAVED_SIM_SCOPE' and probe['translation_error_m']<.02 and probe['yaw_error_rad']<.02,
    old_wrong_first_hit_rejected=probe['comparison'][1]['first_hit_inlier_fraction']<.7,
    focused_pass=read(out/'focused10/result.json')['status']=='PASS',archive_role_pass=read(out/'archive-worker04/result.json')['status']=='PASS',
    failed_visual_retained=read(out/'acceptance01.json')['status']=='FAIL_VISUAL_ACCEPTANCE',
    pixels_reviewed=visual['robot_body_and_scan_visible'] and visual['off_removes_review_layer'] and visual['saved_not_live'] and all(sha(out/i['path'])==i['sha256'] for i in visual['images']))
q=ui['stop_receipt']['request'];ack=ui['stop_receipt']['ack'];accepted=ui['stop_receipt']['accepted'];after=ui['stop'];before=ui['before_stop']
checks['fresh_stop_applied']=(q['request_id']==ack['request_id'] and ack['status']=='accepted' and q['robot_id']==ack['robot_id']==after['robot_id']==before['robot_id'] and q['motion_epoch']==before['motion_epoch']!=accepted['motion_epoch'] and after['motion_epoch']==after['applied_motion_epoch']==accepted['motion_epoch'] and after['control_state']=='PAUSED')
for v in (ui,cold):
    checks[v['phase']+'_no_errors']=not v['errors'] and not any(r['status']>=400 for r in v['responses'])
    checks[v['phase']+'_no_photo_dispatch']=not any(r.get('request',{}).get('action')=='photo_analyze' for r in v['responses'])
    checks[v['phase']+'_dom_receipt_bound']=bool(v.get('rendered_receipts')) and all(r['dom']['live']=='true' and r['dom']['id']==r['frame']['frame_id'] and r['dom']['stamp']==r['frame']['captured_at_ms'] and 0<=r['at']-r['frame']['captured_at_ms']<1000 and r['bounds']['height']>=200 for r in v['rendered_receipts'])
for folder in out.glob('runtime-copies*/*'):
    value=read(folder/'owned-exit-observations.json');inner=read(folder/'engine-result.json');copied=read(folder/'copy-receipt.json');prefix=folder.parent.name
    checks[prefix+'_normal_roots']=value['evidence_complete'] and all(value['roles'][r]['return_code']==0 and value['roles'][r]['root_disposition']=='EXITED_DURING_GRACE' and not value['roles'][r]['errors'] for r in ('backend','engine'))
    checks[prefix+'_inner_cleanup']=inner['cleanup_status']=='PRE_CLOSE_COMPLETE' and not inner['cleanup_errors']
    checks[prefix+'_exact_copies']=all(sha(folder/i['name'])==i['sha256'] for i in copied['files'] if i['status']=='EXACT_COPY')
for v,copy_set in ((ui,'03'),(cold,'04')):
    folder=out/('runtime-copies'+copy_set)/v['versions']['engine']['launch_id'];checks[copy_set+'_launch_bound_exit']=(folder/'owned-exit-observations.json').is_file()
videos=[]
for name in ('ui06','cold05'):
    p=out/name/'recording/app-screen.mp4';run=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',str(p),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','NUL'],capture_output=True)
    videos.append(dict(path=str(p.relative_to(out)),sha256=sha(p),exit_code=run.returncode,error=run.stderr.decode('utf-8',errors='replace')))
checks['accepted_videos_decode']=all(v['exit_code']==0 and not v['error'] for v in videos)
checks['no_live_launcher']=not (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists()
result=dict(status='PASS_SIM_LOCAL_ALIGNMENT_REVIEW_SCOPE' if all(checks.values()) else 'FAIL',checks=checks,passed=sum(checks.values()),total=len(checks),installed_verification=verified,videos=videos,
    physical_authority=False,physical_world_registration='NOT_QUALIFIED',original_physical_poor_fit='UNCHANGED',model_calls_this_turn=0)
with (out/'acceptance02.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(dict(status=result['status'],passed=result['passed'],total=result['total'],failed=[k for k,v in checks.items() if not v])));raise SystemExit(0 if all(checks.values()) else 1)
