// SPDX-License-Identifier: Apache-2.0
// Test evidence classification, never product behavior or a timeout override.
const identity=(a,b)=>a&&b&&['robot_id','operation_id','connection_epoch'].every(k=>typeof a[k]==='string'&&a[k].length>0&&a[k]===b[k]);
const paused=r=>r?.control_state==='PAUSED'&&typeof r.motion_epoch==='string'&&r.motion_epoch.length>0&&r.motion_epoch===r.applied_motion_epoch;
const finite=(...xs)=>xs.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0);
const pose=r=>Array.isArray(r?.pose?.position_m)&&r.pose.position_m.length===3&&r.pose.position_m.every(x=>typeof x==='number'&&Number.isFinite(x));
export function safeUnknownDriveRejection(error,r){
 if(error.path!=='/v1/product/robot-fleet'||error.method!=='POST'||error.action!=='drive'||error.status!==409||error.response_body_available!==false||error.code!==undefined||error.fault?.kind!=='dispatch-delay-matrix')return null;
 if(typeof error.request_id!=='string'||!error.request_id)return null;
 const requests=r.fleet_requests.filter(v=>v.request_id===error.request_id&&v.action==='drive');if(requests.length!==1)return null;const drive=requests[0];
 if(typeof drive.motion_epoch!=='string'||!drive.motion_epoch)return null;
 const aborted=r.request_failures.some(v=>v.request_id===drive.request_id&&v.error==='net::ERR_ABORTED'&&v.fault?.kind===error.fault.kind&&v.fault.delay_ms===error.fault.delay_ms);
 const trial=r.fault_matrix_trials.find(v=>v.delay_ms===error.fault.delay_ms&&v.request_ids?.includes(drive.request_id));
 if(!aborted||!trial||!identity(drive,trial.confirmed)||!identity(trial.confirmed,trial.after)||!paused(trial.confirmed)||!paused(trial.after)||trial.confirmed.motion_epoch===drive.motion_epoch||trial.confirmed.motion_epoch!==trial.after.motion_epoch||!finite(drive.at,drive.order,drive.response_order,drive.response_at,drive.expires_at_ms,trial.confirmed_at,trial.after_at,trial.confirmed.telemetry_sequence,trial.after.telemetry_sequence)||!pose(trial.confirmed)||!pose(trial.after)||trial.after.telemetry_sequence<=trial.confirmed.telemetry_sequence||trial.after_at-trial.confirmed_at<400||drive.response_at<drive.expires_at_ms)return null;
 if(trial.confirmed.pose.position_m.some((x,i)=>Math.abs(x-trial.after.pose.position_m[i])>.01))return null;
 const stop=r.fleet_requests.find(v=>v.action==='stop'&&v.status===200&&identity(v,drive)&&v.motion_epoch===drive.motion_epoch&&finite(v.order,v.response_at)&&v.order>drive.response_order&&v.response_at>=drive.response_at&&v.response_at<=trial.confirmed_at&&v.result_robots?.some(a=>identity(a,trial.confirmed)&&paused(a)&&a.motion_epoch===trial.confirmed.motion_epoch));
 if(!stop||r.fleet_requests.some(v=>v.action==='drive'&&v.robot_id===drive.robot_id&&v.at>trial.confirmed_at&&v.at<trial.after_at))return null;
 return {classification:'SAFE_RECOVERY_SCOPED_REJECTION_CAUSE_UNKNOWN',application_request_id:drive.request_id,drive,stop,trial_delay_ms:trial.delay_ms,
  basis:'Tagged delayed409 with unread body/client abort, followed by exact Stop200/new applied epoch and advancing unchanged-pose observations before new input. Response after expiry does NOT prove server admission time or rejection reason.'};
}
export function scopedFetchBoundaryFailure(error,r){
 if(!['/v1/product/viewport','/v1/product/viewport/current'].includes(error.path)||error.method!=='GET'||error.exiting||error.fault||error.error!=='net::ERR_FAILED')return null;
 const pairs=r.network_failures.filter(v=>v.path===error.path&&v.method==='GET'&&v.error===error.error&&Math.abs(v.failed_at-error.at)<=3);
 if(pairs.length!==1)return null;const n=pairs[0],e=r.fetch_teardown_recovery;
 if(!n.browser_request_id||!error.context||error.context!==error.current_context||n.context_id!==error.context||r.request_failures.filter(v=>v.path===n.path&&v.method==='GET'&&v.error===n.error&&Math.abs(v.at-n.failed_at)<=3).length!==1)return null;
 const boundary=name=>r.fetch_boundaries.find(v=>v.action===name)?.cdp_monotonic_s;
 const enable=boundary('after_enable'),before=boundary('before_disable'),after=boundary('after_disable');
 if(!e||![enable,before,after,n.cdp_timestamp,n.failure_cdp_timestamp].every(Number.isFinite)||enable>before||before>after||n.cdp_timestamp<enable||n.cdp_timestamp>after||n.failure_cdp_timestamp<before||n.failure_cdp_timestamp>after)return null;
 if(!e.stopped_robots?.length||!e.stopped_robots.every(paused)||e.before?.live!==true||e.after?.live!==true||!finite(e.before.frame_id,e.after.frame_id,e.before.frame_age_ms,e.after.frame_age_ms,e.observed_after_disable_at,e.disable_completed_at)||e.before.frame_age_ms>=1000||e.after.frame_age_ms>=1000||e.after.frame_id<=e.before.frame_id||!e.before.scene_revision||e.before.scene_revision!==e.after.scene_revision||!e.before.stage_epoch||e.before.stage_epoch!==e.after.stage_epoch||e.observed_after_disable_at<e.disable_completed_at)return null;
 return {classification:'FETCH_BOUNDARY_ASSOCIATED_CAUSE_UNKNOWN',browser_request_id:n.browser_request_id??n.request_id,network:n,recovery:e,
  basis:'Unique bidirectional same-context path/time association to a preserved browser ID, not exact page-event ID proof. GET began during the explicit fault window and its lifetime overlapped measured Fetch teardown. Stop/applied epochs and later same-scene/stage decoded frame verified. Cause UNKNOWN; normal-window errors are not excluded.'};
}
