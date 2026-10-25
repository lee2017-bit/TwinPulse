// SPDX-License-Identifier: Apache-2.0
// Acceptance evidence only: never creates or repairs a product response.
export function recordStopReceipt(meta,incoming){
 if(!meta||!['stop','stop_all'].includes(meta.action))return;
 meta.result_revision=incoming.revision;
 meta.result_robots=incoming.robots.map(v=>Object.fromEntries(
  ['robot_id','operation_id','connection_epoch','motion_epoch','applied_motion_epoch','control_state'].map(k=>[k,v[k]])));
}
export function exactStopAllApplied(before,response,current){
 // Observation predicate only. An already-paused pre-click snapshot cannot
 // acknowledge the new Stop; bind its own HTTP body, revision and both epochs.
 if(!Array.isArray(before)||before.length!==2||new Set(before.map(r=>r.robot_id)).size!==2||
    !Number.isInteger(response?.revision)||!Number.isInteger(current?.revision)||current.revision<response.revision||
    !Array.isArray(response.robots)||!Array.isArray(current.robots))return false;
 return before.every(old=>{
  const accepted=response.robots.find(r=>r.robot_id===old.robot_id),applied=current.robots.find(r=>r.robot_id===old.robot_id);
  return old.kind==='sim'&&accepted?.kind==='sim'&&applied?.kind==='sim'&&
   ['robot_id','operation_id','connection_epoch'].every(k=>typeof old[k]==='string'&&old[k]&&accepted[k]===old[k]&&applied[k]===old[k])&&
   typeof accepted.motion_epoch==='string'&&accepted.motion_epoch&&accepted.motion_epoch!==old.motion_epoch&&
   applied.motion_epoch===accepted.motion_epoch&&applied.applied_motion_epoch===accepted.motion_epoch&&applied.control_state==='PAUSED';
 });
}
export function assertFinalStopReceipt(result){
 const recovery=result.final_fault_recovery,robots=recovery?.stopped_robots??[],previous=recovery?.before_stop_robots??[];
 const stop=result.fleet_requests.find(r=>r.request_id===recovery?.stop_request_id&&r.action==='stop_all'&&r.status===200);
 if(robots.length!==2||new Set(robots.map(r=>r.robot_id)).size!==2||!stop)throw Error('Final Stop all request/HTTP200/two-robot evidence missing');
 for(const robot of robots){
  const old=previous.find(r=>r.robot_id===robot.robot_id);
  const ack=stop.result_robots?.find(r=>['robot_id','operation_id','connection_epoch','motion_epoch'].every(k=>r[k]===robot[k]));
  if(!old||!ack||!['robot_id','operation_id','connection_epoch'].every(k=>typeof robot[k]==='string'&&robot[k]&&old[k]===robot[k])||
    !robot.motion_epoch||robot.motion_epoch===old.motion_epoch||robot.applied_motion_epoch!==robot.motion_epoch||robot.control_state!=='PAUSED')
   throw Error('Final Stop all exact ACK and engine-applied new epoch not bound for '+robot.robot_id);
 }
}
