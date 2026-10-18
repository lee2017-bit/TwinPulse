// SPDX-License-Identifier: Apache-2.0
// Synthetic negative classifier fixtures ONLY; not App/model/robot acceptance.
import assert from 'node:assert/strict';
import {safeUnknownDriveRejection,scopedFetchBoundaryFailure} from './explicit_fault_recovery.mjs';
const clone=v=>structuredClone(v),robot={robot_id:'r',operation_id:'o',connection_epoch:'c',motion_epoch:'new',applied_motion_epoch:'new',control_state:'PAUSED',pose:{position_m:[0,0,0]},telemetry_sequence:10};
const drive={...robot,action:'drive',request_id:'app-id',motion_epoch:'old',order:1,response_order:2,response_at:251,expires_at_ms:250,at:0};
const stop={...robot,action:'stop',motion_epoch:'old',status:200,order:3,response_at:270,result_robots:[robot]};
const error={path:'/v1/product/robot-fleet',method:'POST',action:'drive',status:409,request_id:'app-id',response_body_available:false,fault:{kind:'dispatch-delay-matrix',delay_ms:100}};
const record={fleet_requests:[drive,stop],request_failures:[{request_id:'app-id',error:'net::ERR_ABORTED',fault:error.fault}],fault_matrix_trials:[{request_ids:['app-id'],delay_ms:100,confirmed:robot,after:clone({...robot,telemetry_sequence:11}),confirmed_at:300,after_at:800}]};
assert(safeUnknownDriveRejection(error,record));
let count=1;
for(const mutate of [r=>r.fleet_requests.pop(),r=>r.fleet_requests[1].status=500,r=>r.fleet_requests[1].operation_id='wrong',r=>r.fault_matrix_trials[0].after.pose.position_m[0]=.02,r=>r.fault_matrix_trials[0].after.telemetry_sequence=10,r=>r.fault_matrix_trials[0].request_ids=[],r=>r.request_failures[0].request_id='other']){const r=clone(record);mutate(r);assert.equal(safeUnknownDriveRejection(error,r),null);count++;}
for(const mutate of [e=>e.code='unexpected',e=>e.status=500,e=>e.fault=null,e=>e.response_body_available=true]){const e=clone(error);mutate(e);assert.equal(safeUnknownDriveRejection(e,record),null);count++;}
for(const mutate of [r=>r.fleet_requests[0].motion_epoch='new',r=>r.fleet_requests[1].motion_epoch='other',r=>delete r.fleet_requests[0].response_at,r=>delete r.fault_matrix_trials[0].after.telemetry_sequence,r=>r.fault_matrix_trials[0].after_at=NaN,r=>r.fault_matrix_trials[0].after.pose.position_m[0]=NaN]){const r=clone(record);mutate(r);assert.equal(safeUnknownDriveRejection(error,r),null);count++;}
{const r=clone(record);delete r.fleet_requests[0].motion_epoch;delete r.fleet_requests[1].motion_epoch;assert.equal(safeUnknownDriveRejection(error,r),null);count++;}
const get={path:'/v1/product/viewport',method:'GET',error:'net::ERR_FAILED',at:150,context:'ctx',current_context:'ctx'};
const view={live:true,frame_id:10,frame_age_ms:100,scene_revision:'scene',stage_epoch:'stage'};
const n={path:get.path,method:'GET',error:get.error,failed_at:150,cdp_timestamp:1.49,failure_cdp_timestamp:1.51,browser_request_id:'browser-id',context_id:'ctx'};
const rec={request_failures:[get],network_failures:[n],fetch_boundaries:[{action:'after_enable',cdp_monotonic_s:1},{action:'before_disable',cdp_monotonic_s:1.5},{action:'after_disable',cdp_monotonic_s:1.52}],fetch_teardown_recovery:{before:view,after:{...view,frame_id:11},stopped_robots:[robot],disable_completed_at:152,observed_after_disable_at:160}};
assert(scopedFetchBoundaryFailure(get,rec));count++;
for(const mutate of [r=>r.network_failures[0].cdp_timestamp=.9,r=>r.network_failures[0].failure_cdp_timestamp=1.53,r=>r.network_failures.push(clone(n)),r=>r.fetch_teardown_recovery.after.frame_id=10,r=>r.fetch_teardown_recovery.after.stage_epoch='other',r=>r.fetch_teardown_recovery.stopped_robots[0].applied_motion_epoch='old']){const r=clone(rec);mutate(r);assert.equal(scopedFetchBoundaryFailure(get,r),null);count++;}
for(const mutate of [r=>{delete r.fetch_teardown_recovery.before.frame_id;delete r.fetch_teardown_recovery.after.frame_id},r=>delete r.fetch_teardown_recovery.observed_after_disable_at,r=>r.fetch_teardown_recovery.after.frame_age_ms=1000]){const r=clone(rec);mutate(r);assert.equal(scopedFetchBoundaryFailure(get,r),null);count++;}
for(const mutate of [r=>r.request_failures.push({...get,at:151}),r=>delete r.network_failures[0].browser_request_id,r=>r.network_failures[0].context_id='other']){const r=clone(rec);mutate(r);assert.equal(scopedFetchBoundaryFailure(get,r),null);count++;}
assert.equal(scopedFetchBoundaryFailure({...get,path:'/v1/product/conversation'},rec),null);count++;
console.log(JSON.stringify({status:'PASS',assertions:count,scope:'SYNTHETIC_CLASSIFIER_SUPPLEMENTARY_NOT_USER_ACCEPTANCE'}));
