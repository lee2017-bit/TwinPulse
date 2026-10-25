// SPDX-License-Identifier: Apache-2.0
// Passive recorder diagnostics only. Never classifies a failed hold as PASS.
export function beginGestureAttempt({direction,before,auditStart,responseStart,failedRequestStart,observedAtMs,continuous=false}){
 return structuredClone({direction,continuous,status:'RUNNING',before,before_observed_at_ms:observedAtMs,
  expected_input_identity:{action:'drive',robot_id:before?.robot_id,operation_id:before?.operation_id,
   connection_epoch:before?.connection_epoch,motion_epoch:before?.motion_epoch,direction},
  audit_start_index:auditStart,response_start_index:responseStart,failed_request_start_index:failedRequestStart,
  call_times_basis:'Node wall clock around input calls; actual event times are retained separately'});
}

export function gestureAttemptDiagnostic(attempt,{audit,rows=[],failedRequests=[],finalRobot=null,error=null}){
 const original=structuredClone(attempt),expected=original.expected_input_identity;
 const events=Array.isArray(audit?.events)?audit.events.slice(original.audit_start_index,original.audit_end_index):null;
 const downIndex=events?.findIndex(e=>e.type==='pointerdown'&&e.button==='Hold '+original.direction)??-1;
 const actualUp=events?.slice(downIndex>=0?downIndex+1:0).find(e=>e.type==='pointerup')??null;
 const owns=request=>request?.robot_id===expected.robot_id&&request?.connection_epoch===expected.connection_epoch&&
  request?.motion_epoch===expected.motion_epoch&&['drive','stop'].includes(request?.action);
 const requests=rows.slice(original.response_start_index).flatMap((row,index)=>owns(row.request)?[{
  response_index:original.response_start_index+index,at:row.at,path:row.path,method:row.method,status:row.status,
  request:structuredClone(row.request),native_start_ms:row.native_start_ms,native_timing:structuredClone(row.native_timing)}]:[]);
 const failures=failedRequests.slice(original.failed_request_start_index).flatMap((row,index)=>owns(row.request)?[{
  failed_request_index:original.failed_request_start_index+index,...structuredClone(row)}]:[]);
 return {...original,actual_down:downIndex>=0?events[downIndex]:null,
  actual_up:actualUp,up_button_matches_direction:actualUp?actualUp.button==='Hold '+original.direction:null,
  passive_events:events,interruptions:events?.filter(e=>['pointercancel','blur','resize'].includes(e.type))??null,
  audit_status:audit?.status??'UNAVAILABLE',observed_requests:requests,observed_failed_requests:failures,
  final_reported_robot:structuredClone(finalRobot),failure:original.status==='PASS'?null:error,
  acceptance_basis:'Diagnostic only; automatic Stop and missing release are not normal-release success'};
}
