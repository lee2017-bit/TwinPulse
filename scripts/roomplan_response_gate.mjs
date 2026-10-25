// SPDX-License-Identifier: Apache-2.0
// Read-only evidence classification, frozen before the new UI trial.
import {catalogTransition} from './roomplan_catalog_transition.mjs';
export function classifyRoomplanResponses(result){
 const issues=[],expected_stop_rejections=[],expected_catalog_transitions=[];
 const rows=result.responses??[],gestures=result.gestures??[];
 const end=r=>r.native_start_ms+r.native_timing?.responseEnd;
 const pose=r=>JSON.stringify(r?.pose?.position_m);
 const integer=v=>Number.isSafeInteger(v)&&v>=0;
 const finitePose=r=>Array.isArray(r?.pose?.position_m)&&r.pose.position_m.length===3&&r.pose.position_m.every(Number.isFinite);
 for(const g of gestures){
  const events=(result.operation_events??[]).filter(e=>e.operation_id===g.before?.operation_id&&e.robot_id===g.before?.robot_id&&['motion_result','engine_observation'].includes(e.kind));
  if(!events.length||events.some(e=>!Number.isFinite(Date.parse(e.utc)))){issues.push({reason:'Original engine motion events missing/invalid'});continue;}
  const held=events.filter(e=>Date.parse(e.utc)>=g.down.at&&Date.parse(e.utc)<g.up.at-1);
  const moving=held.some(e=>e.kind==='engine_observation'&&e.source==='isaac_usd_kinematic'&&!e.reason&&integer(e.telemetry_sequence)&&Array.isArray(e.position_m)&&e.position_m.length===3&&e.position_m.every(Number.isFinite)&&JSON.stringify(e.position_m)!==pose(g.before));
  if(!moving||held.some(e=>e.runtime_fault||e.reason&&e.reason!=='OPERATOR_STOP')){issues.push({reason:'Original held-input engine outcome missing or faulted',direction:g.direction});}
 }
 for(const rejected of rows.filter(r=>r.status>=400)){
  const transition=catalogTransition(result,rejected);if(transition){expected_catalog_transitions.push(transition);continue;}
  const request=rejected.request;
  const fail=why=>issues.push({request_id:request?.request_id,reason:why});
  if(rejected.status!==409||rejected.body?.error?.code!=='fleet_motion_changed'||request?.action!=='drive'){fail('Unexpected HTTP error');continue;}
  const g=gestures.find(g=>g.before?.robot_id===request.robot_id&&g.before?.connection_epoch===request.connection_epoch&&g.before?.motion_epoch===request.motion_epoch&&g.down?.at<=rejected.native_start_ms&&rejected.native_start_ms<=g.up?.at+1);
  if(!g||!Number.isFinite(g.down.at)||!Number.isFinite(g.up.at)||g.up.at<=g.down.at||!g.down.trusted||!g.up.trusted||g.interruptions?.length){fail('No original uninterrupted trusted release gesture');continue;}
  const up=g.up.at,down=g.down.at;
  if(!Number.isFinite(rejected.native_start_ms)||!Number.isFinite(rejected.native_timing?.responseEnd)||rejected.native_timing.responseEnd<0||end(rejected)<up||request.payload?.direction!==g.direction||!integer(request.payload?.sequence)||request.payload.sequence===0||!Number.isFinite(request.payload.expires_at_ms)){fail('Missing native request timing or input identity');continue;}
  const stop=rows.find(r=>r.status===200&&r.request?.action==='stop'&&r.request.robot_id===request.robot_id&&r.request.connection_epoch===request.connection_epoch&&r.request.motion_epoch===request.motion_epoch&&r.native_start_ms>=up-1&&r.native_start_ms<request.payload.expires_at_ms);
  const stopped=stop?.body?.robots?.find(r=>r.robot_id===request.robot_id);
  if(!stopped||!stopped.motion_epoch||stopped.motion_epoch===request.motion_epoch||stopped.connection_epoch!==request.connection_epoch||stopped.operation_id!==g.before.operation_id||stopped.control_state!=='PAUSED'||stopped.reason!=='OPERATOR_STOP'){fail('No exact same-operation Stop and new epoch');continue;}
  const nextDown=Math.min(...gestures.filter(v=>v.down?.at>up).map(v=>v.down.at),Infinity);
  const drives=rows.filter(r=>r.request?.action==='drive'&&r.request.robot_id===request.robot_id);
  if(drives.some(r=>!Number.isFinite(r.native_start_ms)||!Number.isFinite(r.native_timing?.responseEnd)||r.native_timing.responseEnd<0)){fail('Drive native timing missing');continue;}
  const intervals=drives.filter(r=>r.request.connection_epoch===request.connection_epoch&&r.native_start_ms>=down&&r.native_start_ms<=up+1).sort((a,b)=>a.native_start_ms-b.native_start_ms);
  if(intervals.some((r,i)=>i>0&&r.native_start_ms<end(intervals[i-1]))){fail('Concurrent held-input requests');continue;}
  const outstanding=drives.filter(r=>r.native_start_ms>=down&&r.native_start_ms<=up+1&&end(r)>up);
  if(outstanding.length!==1||outstanding[0].request.request_id!==request.request_id||drives.some(r=>r.native_start_ms>up+1&&r.native_start_ms<nextDown)){fail('Queued/post-release drive or non-unique in-flight request');continue;}
  const ack=rows.find(r=>r.at>=stop.at&&(r.body?.robots??[]).some(v=>v.robot_id===request.robot_id&&v.connection_epoch===request.connection_epoch&&v.motion_epoch===stopped.motion_epoch&&v.applied_motion_epoch===stopped.motion_epoch&&v.control_state==='PAUSED'&&pose(v)===pose(g.after)));
  const valid=r=>r?.robot_id===request.robot_id&&r?.connection_epoch===request.connection_epoch&&r?.operation_id===g.before.operation_id&&r?.motion_epoch===stopped.motion_epoch&&r?.applied_motion_epoch===stopped.motion_epoch&&r?.control_state==='PAUSED'&&r?.reason==='OPERATOR_STOP'&&integer(r?.telemetry_sequence)&&finitePose(r);
  if(!ack||!valid(g.after)||!valid(g.stable_after)||g.stable_after.telemetry_sequence<g.after.telemetry_sequence+2||pose(g.after)!==pose(g.stable_after)){fail('Stop lacks new engine ACK and subsequent stationary telemetry');continue;}
  expected_stop_rejections.push({request_id:request.request_id,stop_request_id:stop.request.request_id,robot_id:request.robot_id,operation_id:stopped.operation_id,old_epoch:request.motion_epoch,new_epoch:stopped.motion_epoch,classification:'EXPECTED_STOP_REJECTION',raw_http_status:409});
 }
 return {schema:'roomplan-response-gate-1.2',status:issues.length?'FAIL':'PASS',issues,expected_stop_rejections,expected_catalog_transitions};
}
