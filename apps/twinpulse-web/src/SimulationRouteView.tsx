// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useState} from 'react';
import type {SimulationReview} from './conversation-types';
import type {SimulationSnapshot} from './engine-contracts';

export function SimulationRouteView({review,snapshot}:{review:SimulationReview;snapshot:SimulationSnapshot|null}){
  const [trace,setTrace]=useState<{run:string;points:number[][]}>({run:'',points:[]});
  useEffect(()=>{
    if(!snapshot?.run_id||!snapshot.telemetry_available||snapshot.applied_revision!==review.scene_revision||!snapshot.position_m)return;
    const point=snapshot.position_m.slice(0,2),run=snapshot.run_id;
    setTrace(previous=>({run,points:previous.run===run?[...previous.points,point].slice(-500):[point]}));
  },[snapshot?.sequence,snapshot?.run_id,review.scene_revision]);
  const plan=review.plan;if(!plan)return null;
  const [xmin,xmax,ymin,ymax]=review.drawing.bounds;
  const size=Math.max(xmax-xmin,ymax-ymin),scale=330/size;
  const point=(p:number[])=>[35+(p[0]-xmin)*scale,35+(ymax-p[1])*scale];
  const line=(points:number[][])=>points.map(p=>point(p).join(',')).join(' ');
  const current=snapshot?.telemetry_available&&snapshot.applied_revision===review.scene_revision?snapshot.position_m:null;
  const goal=point(plan.goal),start=point(plan.start);
  return <figure className="sim-route-map">
    <svg viewBox="0 0 400 400" role="img" aria-label="SIM planned route and observed trajectory">
      <rect width="400" height="400" rx="12" fill="#0d202a"/>
      <rect x="35" y="35" width={(xmax-xmin)*scale} height={(ymax-ymin)*scale} fill="#122630" stroke="#577480"/>
      {review.drawing.boxes.map((b,i)=>{const [x,y]=point(b);return <rect key={i} x={x-b[2]*scale} y={y-b[3]*scale} width={2*b[2]*scale} height={2*b[3]*scale} transform={`rotate(${-b[4]*180/Math.PI} ${x} ${y})`} fill="#59636e"/>;})}
      {review.drawing.discs.map((d,i)=>{const [x,y]=point(d);return <circle key={i} cx={x} cy={y} r={d[2]*scale} fill="#59636e"/>;})}
      <polyline points={line([plan.start,...plan.route])} fill="none" stroke="#f6bf68" strokeWidth="3" strokeDasharray="6 4"/>
      {trace.points.length>1&&snapshot?.run_id===trace.run&&<polyline points={line(trace.points)} fill="none" stroke="#67efd2" strokeWidth="3"/>}
      <circle cx={start[0]} cy={start[1]} r="5" fill="#fff"/><circle cx={goal[0]} cy={goal[1]} r="7" fill="#f6bf68"/>
      {current&&<circle cx={point(current)[0]} cy={point(current)[1]} r="6" fill="#67efd2" stroke="#fff"/>}
      <text x="35" y="390" fill="#bacfd6" fontSize="12">World X → · World Y ↑ · metres · approximate SIM geometry</text>
    </svg>
    <figcaption>Dashed amber: planned candidate · teal: observed SIM trajectory. {review.target?`Approach ${review.target.label} · ${review.target.id}`:'Explicit coordinate goal'}. Not a physical map.</figcaption>
  </figure>;
}
