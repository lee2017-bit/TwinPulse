// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type {CurrentGoalState} from './conversation-types';
import {useEffect,useState} from 'react';
import {nativeCleanupLines} from './mission-cleanup';

export function useRecentMissionTelemetry(job:CurrentGoalState['job']|undefined){
  const [recent,setRecent]=useState(false);
  const age=job?.telemetry_age_s;
  const valid=job?.telemetry_status==='RECENT_WORKER_RECEIPT'&&job.worker_active===true
    &&typeof age==='number'&&age>=0&&age<1
    &&!['FAILED','MISSION_ARRIVED','FORCE_STOPPED','COMMAND_SEGMENT_STOPPED','MISSION_CANCELLED','STOPPING'].includes(job.state);
  useEffect(()=>{
    setRecent(valid);
    if(!valid)return;
    // A cached response must expire even when the next HTTP poll fails.
    const timer=window.setTimeout(()=>setRecent(false),Math.max(0,1000-age!*1000));
    return ()=>window.clearTimeout(timer);
  },[job,valid,age]);
  return valid&&recent?job?.telemetry:null;
}

function CurrentWorkerTelemetry({job}:{job:NonNullable<CurrentGoalState['job']>}){
  const receipt=useRecentMissionTelemetry(job);
  return <div aria-label="Current worker telemetry">
    <p>{receipt?.battery?`Latest worker battery: ${receipt.battery.voltage_v.toFixed(2)} V · estimated ${receipt.battery.estimated_percent.toFixed(1)}% (not measured capacity).`:'Current battery unavailable; previous leg checks are historical.'}</p>
    <p>{receipt?.next_waypoint?`Next waypoint ${receipt.next_waypoint.index+1}/${receipt.next_waypoint.count}: (${receipt.next_waypoint.xy_room.map(x=>x.toFixed(2)).join(', ')}) m.`:'Current next waypoint unavailable.'}</p>
    <small>Worker receipt younger than 1 second, not continuously verified physical status. Transport delay is unmeasured. Display is not motion authorization. Motor load measurement is unsupported.</small>
  </div>;
}

export function CurrentGoalReview({state}:{state:CurrentGoalState|null|undefined}){
  if(!state)return null;
  const review=state.review,plan=review?.plan;
  const demo=state.demonstration;
  const task=state.task_loop;
  const bounds=review?.drawing.bounds??[-1,1,-1,1];
  const scale=330/Math.max(bounds[1]-bounds[0],bounds[3]-bounds[2]);
  const point=(p:number[])=>[35+(p[0]-bounds[0])*scale,35+(bounds[3]-p[1])*scale];
  return <section className="chat-question" aria-label="Current sensor goal review">
    <strong>{state.job?`Goal mission · ${state.job.state.replaceAll('_',' ')}`:'Current-sensor route review'}</strong>
    {state.error&&<p role="alert">{state.error}</p>}
    {task&&<div aria-label="Repeat task status">
      <strong>Repeat A ↔ B · {task.state.replaceAll('_',' ')}</strong>
      <p role="status">Leg {task.leg} → {task.destination} · {task.completed_legs} completed · A ({task.a.join(', ')}) / B ({task.b.join(', ')})</p>
      {task.worker_active&&<progress aria-label="Repeat task active"/>}
      {task.error&&<p role="alert">{task.error_stage}: {task.error}</p>}
      {task.cleanup_error&&<p role="alert">Cleanup: {task.cleanup_error}</p>}
      <p>{task.resources?`Last leg check: ${task.resources.voltage_v.toFixed(2)} V · estimated ${task.resources.estimated_percent}% (historical, not measured capacity).`:'Battery: waiting for a fresh leg check; no saved readiness value is reused.'}</p>
      <p>Each leg retains the 45-second limit. Stop cancels new legs. No automatic restart. Motor load measurement is unsupported.</p>
    </div>}
    {demo&&<div>
      <p role="status">Isaac 3D route demonstration · {demo.state.replaceAll('_',' ')} · {demo.stage} · {demo.elapsed_s.toFixed(1)} s</p>
      {['PREPARING','RUNNING'].includes(demo.state)&&<progress aria-label="Isaac route demonstration in progress"/>}
      {demo.error&&<p role="alert">{demo.error}</p>}
      {demo.cleanup_error&&<p role="alert">SIM cleanup: {demo.cleanup_error}</p>}
      {demo.robot_review_parked&&<p role="status">Robot idle during review. Confirm collects a fresh position and rechecks the entire route before driving.</p>}
      {demo.state==='COMPLETED'&&<p>{demo.receipt_current?'Exact route completed in Isaac PhysX.':'Historical SIM receipt · no longer current.'} SIM-only, not physical validation.
        {!demo.handoff_ready&&' Physical execution handoff is not yet available.'}</p>}
    </div>}
    {plan&&<figure className="sim-route-map">
      <svg viewBox="0 0 400 400" role="img" aria-label="Candidate route from the reviewed sensor position">
        <rect width="400" height="400" rx="12" fill="#0d202a"/>
        {review!.drawing.boxes.map((b,i)=>{const [x,y]=point(b);return <rect key={i} x={x-b[2]*scale} y={y-b[3]*scale}
          width={b[2]*2*scale} height={b[3]*2*scale} transform={`rotate(${-b[4]*180/Math.PI} ${x} ${y})`} fill="#59636e"/>;})}
        {review!.drawing.discs.map((d,i)=>{const [x,y]=point(d);return <circle key={i} cx={x} cy={y} r={d[2]*scale} fill="#59636e"/>;})}
        <polyline points={[plan.start,...plan.route].map(p=>point(p).join(',')).join(' ')} fill="none" stroke="#f6bf68" strokeWidth="3" strokeDasharray="6 4"/>
        <circle cx={point(plan.start)[0]} cy={point(plan.start)[1]} r="5" fill="#fff"/>
        <circle cx={point(plan.goal)[0]} cy={point(plan.goal)[1]} r="7" fill="#f6bf68"/>
      </svg>
      <figcaption>Reviewed start, not a continuously observed current position. Candidate route only; not an executed Isaac 3D demonstration.</figcaption>
    </figure>}
    {state.job&&<p role="status">{state.job.elapsed_s.toFixed(1)} s · no automatic restart</p>}
    {state.job&&<CurrentWorkerTelemetry job={state.job}/>}
    {state.job?.error&&<p role="alert">{state.job.error}</p>}
    {nativeCleanupLines(state.job).map((line,i)=><p role="alert" key={i}>{line}</p>)}
    {state.job?.cleanup_error&&<p role="alert">Cleanup: {state.job.cleanup_error}</p>}
    {state.job?.report_error&&<p role="alert">Report: {state.job.report_error}</p>}
  </section>;
}
