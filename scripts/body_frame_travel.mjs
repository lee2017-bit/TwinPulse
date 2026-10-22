// SPDX-License-Identifier: Apache-2.0
// Observation math only. Never changes pose, commands, guards or acceptance distances.
export function measuredBodyTranslation(before,after){
 for(const key of ['robot_id','operation_id','connection_epoch'])
  if(typeof before?.[key]!=='string'||!before[key]||before[key]!==after?.[key])throw Error('Movement observation identity changed');
 for(const row of [before,after]){
  const pose=row.pose;
  if(pose?.frame_id!=='isaac_world'||pose.source!=='isaac_usd_kinematic'||pose.aligned!==true||
   !Array.isArray(pose.position_m)||pose.position_m.length!==3||pose.position_m.some(v=>typeof v!=='number'||!Number.isFinite(v)||Math.abs(v)>1e6))
   throw Error('Movement observation pose invalid');
 }
 const p=before.pose.position_m,q=after.pose.position_m,dx=q[0]-p[0],dy=q[1]-p[1];
 return {forward_m:dx*Math.cos(p[2])+dy*Math.sin(p[2]),lateral_m:-dx*Math.sin(p[2])+dy*Math.cos(p[2]),
  distance_m:Math.hypot(dx,dy),yaw_change_rad:Math.atan2(Math.sin(q[2]-p[2]),Math.cos(q[2]-p[2])),frame:'original_measured_body_heading'};
}
export function requireBodyTranslation(before,after,direction,minimum){
 if(!['forward','backward'].includes(direction)||typeof minimum!=='number'||!Number.isFinite(minimum)||minimum<=0)throw Error('Movement observation criterion invalid');
 const measured=measuredBodyTranslation(before,after),signed=measured.forward_m*(direction==='forward'?1:-1);
 // Original approach was strictly greater than5cm; original reverse allowed
 // equality at9cm. Preserve both boundary operators, not only the numbers.
 if((direction==='forward'?signed<=minimum:signed<minimum)||Math.abs(measured.lateral_m)>.005||Math.abs(measured.yaw_change_rad)>.01)
  throw Error('Body-frame '+direction+' movement not proven: '+JSON.stringify(measured));
 return measured;
}
