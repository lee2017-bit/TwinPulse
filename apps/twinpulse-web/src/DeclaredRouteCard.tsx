// SPDX-License-Identifier: Apache-2.0
import {useEffect, useState} from 'react';
import type {TwinPulseApi} from './api';
import type {DeclaredRouteState, RobotFleetState} from './robot-fleet-types';

/** Progress and result of the declared-start route (chat "Survey the room and come back").
 *
 * Display only: the backend runner owns the motion; this card never sends a step.
 * Positions are declared start + wheel odometry, not localization. Stop goes
 * through the ordinary fleet Stop all, which cancels the route before delivery.
 */
export function DeclaredRouteCard({route,api,onChange,available,report}:{route:DeclaredRouteState|null|undefined;api:TwinPulseApi;
  onChange:(next:RobotFleetState)=>void;available:boolean;report:(message:string)=>void}){
  const [dismissed,setDismissed]=useState<string|null>(null);
  const [stopping,setStopping]=useState(false);
  const [now,setNow]=useState(()=>Date.now()/1000);
  const running=route?.state==='RUNNING';
  useEffect(()=>{if(!running)return;const timer=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(timer);},[running]);
  if(!route||!route.scene_current||dismissed===route.plan_id)return null;
  const total=route.total_stops,reached=route.reached_stops?.length??route.reached??0,skipped=route.skipped_stops??[];
  const elapsed=Math.max(0,Math.round(((running?now:route.finished_at??now)-(route.started_at??now))));
  const title=running?`Route running · stop ${reached} of ${total}`:
    route.state==='COMPLETED'?`Route completed · ${reached} of ${total} stops${skipped.length?` (skipped ${skipped.map(s=>s+1).join(', ')})`:''}`:
    `Route ${(route.state??'').toLowerCase()} · ${reached} of ${total} stops`;
  const moves=`${route.completed_steps??0} moves done · about ${route.planned_steps??0} planned; odometry re-aims can add more`;
  const stop=async()=>{
    if(stopping)return;setStopping(true);
    try{onChange(await api.robotFleetAction({action:'stop_all',request_id:crypto.randomUUID(),robot_id:null,connection_epoch:null,motion_epoch:null,payload:{}} as Parameters<TwinPulseApi['robotFleetAction']>[0]));}
    catch(error){report(error instanceof Error?error.message:'Stop delivery unconfirmed. Check the robot card before anything else.');}
    finally{setStopping(false);}
  };
  // Floor map: start, numbered stops (reached green, skipped grey), planned path, odometry trace, current pose.
  const pts=[route.start,...route.waypoints,...route.polyline,...(route.trace??[]),...(route.pose?[route.pose]:[])].filter(p=>p&&p.length>=2) as number[][];
  const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  const x0=Math.min(...xs)-.6,x1=Math.max(...xs)+.6,y0=Math.min(...ys)-.6,y1=Math.max(...ys)+.6;
  const w=Math.max(x1-x0,1),h=Math.max(y1-y0,1),X=(x:number)=>x-x0,Y=(y:number)=>y1-y;
  const line=(rows:number[][])=>rows.map(p=>`${X(p[0])},${Y(p[1])}`).join(' ');
  return <section className="chat-tool-progress declared-route-card" role="status" aria-label="Declared route progress">
    <strong>{title}</strong>
    <p>{moves}{running&&route.current_step?` · now: ${route.current_step}`:''} · {elapsed} s{route.recoveries?` · ${route.recoveries} proximity recover${route.recoveries===1?'y':'ies'}`:''}</p>
    {!running&&route.reason&&<p>Reason: {route.reason.replaceAll('_',' ')}{route.candidates?` · ${route.candidates} LiDAR object${route.candidates===1?'':'s'} not in the Twin (see the chat card to add them)`:''}</p>}
    <svg role="img" aria-label="Route map · declared start + wheel odometry, not localized" viewBox={`0 0 ${w} ${h}`} style={{width:'100%',maxHeight:200,background:'#20262e',borderRadius:6}}>
      {route.polyline.length>1&&<polyline points={line(route.polyline)} fill="none" stroke="#f2b84b" strokeWidth={0.04}/>}
      {(route.trace?.length??0)>1&&<polyline points={line(route.trace!)} fill="none" stroke="#5fd3a6" strokeWidth={0.05}/>}
      {(route.keepouts??[]).map((d,i)=><circle key={'k'+i} cx={X(d[0])} cy={Y(d[1])} r={d[2]??.1} fill="none" stroke="#e5534b" strokeWidth={0.03}/>)}
      {route.waypoints.map(([x,y],i)=>{const done=(route.reached_stops??[]).includes(i),skip=skipped.includes(i);
        return <g key={i}><circle cx={X(x)} cy={Y(y)} r={0.12} fill={done?'#5fd3a6':skip?'#7a7a7a':'#f2b84b'}/>
          <text x={X(x)+0.15} y={Y(y)-0.12} fontSize={0.26} fill="#ffffff">{i+1}</text></g>;})}
      <circle cx={X(route.start[0])} cy={Y(route.start[1])} r={0.1} fill="#ffffff"/>
      {route.pose&&<g><circle cx={X(route.pose[0])} cy={Y(route.pose[1])} r={0.11} fill="#3fa9f5"/>
        <line x1={X(route.pose[0])} y1={Y(route.pose[1])} x2={X(route.pose[0]+.3*Math.cos(route.pose[2]))} y2={Y(route.pose[1]+.3*Math.sin(route.pose[2]))} stroke="#3fa9f5" strokeWidth={0.05}/></g>}
    </svg>
    <small>Declared start + wheel odometry · not localized · nothing here authorizes motion</small>
    <div>{running?<button type="button" onClick={()=>void stop()} disabled={stopping||!available}>{stopping?'Stopping…':'Stop route'}</button>:
      <button type="button" onClick={()=>setDismissed(route.plan_id)}>Dismiss</button>}</div>
  </section>;
}
