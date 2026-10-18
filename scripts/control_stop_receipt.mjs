// SPDX-License-Identifier: Apache-2.0
// Acceptance evidence only: never creates or repairs a product response.
export function recordStopReceipt(meta,incoming){
 if(!meta||!['stop','stop_all'].includes(meta.action))return;
 meta.result_revision=incoming.revision;
 meta.result_robots=incoming.robots.map(v=>Object.fromEntries(
  ['robot_id','operation_id','connection_epoch','motion_epoch','applied_motion_epoch','control_state'].map(k=>[k,v[k]])));
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
