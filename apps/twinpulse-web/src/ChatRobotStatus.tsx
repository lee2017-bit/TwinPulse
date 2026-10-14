// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useRef, useState} from 'react';
import type {RobotPreparation} from './conversation-types';
import type {TwinPulseApi} from './api';

export function ChatRobotStops({state,api,report,forceOnly=false}:{state:RobotPreparation|null|undefined;api:TwinPulseApi;report:(error:string)=>void;forceOnly?:boolean}) {
  const [stopping,setStopping]=useState<string|null>(null);
  const stoppingNormal=useRef(false);
  const stoppingForce=useRef(false);
  const stop=async(force:boolean)=>{
    const flight=force?stoppingForce:stoppingNormal;
    if(flight.current)return;
    flight.current=true;setStopping(force?'Force STOP requested…':'Stop requested…');
    try {
      const result=await api.chatRobotStop(force);
      setStopping(`${result.state} · stop acknowledgement/cleanup must still be checked`);
    } catch(error){report(error instanceof Error?error.message:'Stop delivery failed. Robot stop is unconfirmed.');}
    finally{flight.current=false;}
  };
  const active=!!state?.active_control?.owned&&state.active_control.busy ||
    !!state?.owned&&['CHECKING','QUALIFYING','INITIALIZING'].includes(state.state);
  return <div className="chat-robot-stops">
    {!forceOnly&&<button disabled={!active||stoppingNormal.current} onClick={()=>void stop(false)}>Stop after current command</button>}
    <button disabled={!active||stoppingForce.current} onClick={()=>void stop(true)}>Force STOP</button>
    {stopping&&<small role="status">{stopping}</small>}
  </div>;
}

export function ChatRobotStatus({state,api,report,check,collect,transfer,checkBusy=false}:{state:RobotPreparation|null|undefined;api:TwinPulseApi;report:(error:string)=>void;check?:()=>void;collect?:()=>void;transfer?:(kind:'stationary'|'qualification',job:string)=>void;checkBusy?:boolean}) {
  const collection=state?.collection;
  const transferBusy=collection?.recovery?.status==='TRANSFERRING'||state?.evidence?.evidence_recovery?.status==='TRANSFERRING';
  const operationBusy=!!state?.active_control?.busy||['CHECKING','QUALIFYING','INITIALIZING','COLLECTING'].includes(state?.state??'')||collection?.status==='RUNNING'||transferBusy;
  return <section className="chat-question" aria-label="Robot preparation">
    <strong>Robot preparation · {state?.state.replaceAll('_',' ')??'Unavailable'}</strong>
    <p role="status">{state?.stage.replaceAll('_',' ')??'Physical adapter not configured'}{state?.code?` · ${state.code}`:''}</p>
    {check&&<button disabled={checkBusy||!state?.available||operationBusy} onClick={check}>Check robot connection · read-only</button>}
    {state?.state==='CHECKING'&&<p>Checking PC tools, then SSH and the board. Booting may take 2–3 minutes. No movement or automatic retry.</p>}
    {state?.state==='QUALIFYING'&&<p>One bounded forward-and-stop trial is running. No further click is needed until its result.</p>}
    {state?.state==='INITIALIZING'&&<p>Preparing the approved source and Motor OFF, then checking the board again. No drive or sensor start. Wait for the result.</p>}
    {state?.code==='TORQUE_ENABLED_INITIALIZATION_REQUIRED'&&<p>Connected · initial preparation required. Motor torque may be enabled after boot; this observation is not a motor fault. Wheels and command bytes were zero. Use the preparation approval above.</p>}
    {state?.state==='LINKED'&&<p>Connection and stop record reviewed. Survey and mission gates are still separate.</p>}
    {state?.record?.battery&&<p>Battery snapshot: {state.record.battery.estimated_percent.toFixed(1)}% estimated · {state.record.battery.voltage_v.toFixed(2)} V</p>}
    {state?.transport==='OFFLINE_TEST_TRANSPORT'&&<small>Offline test transport · not a physical qualification</small>}
    <ChatRobotStops state={state} api={api} report={report}/>
    <small>No autonomous movement is authorized by this preparation.</small>
    {collect&&<section aria-label="Stationary evidence collection">
      <strong>Stationary sensor evidence · {collection?.status.replaceAll('_',' ')??'Not started'}</strong>
      <p>Keep the robot stationary. This one action may transfer reviewed source and captures existing odom, scan and TF. It does not enable motors, start LiDAR or drive.</p>
      <button disabled={checkBusy||!state?.available||operationBusy||!collection||['REMOTE_STATE_UNKNOWN','LOCAL_RECORD_UNREADABLE'].includes(collection.status)} onClick={collect}>Approve source transfer and collect once</button>
      {collection?.result_code&&<p role="status">{collection.result_code}{collection.reason?` · ${collection.reason}`:''}</p>}
      {collection?.job_id&&<>
        <ul>{collection.sources.map(item=><li key={item.id}>{item.id}: {item.status}{item.reason?` · ${item.reason}`:''}</li>)}</ul>
        <p>Initial raw export: {collection.raw_export?.status??'Not confirmed'} · Recovery: {collection.recovery?.status??'Not started'}</p>
        {collection.recovery?.status==='COMPLETE'?<p role="status">Recovered files verified. The initial failure is retained as history.</p>:
          collection.resume_available&&transfer&&<button disabled={checkBusy||operationBusy} onClick={()=>transfer('stationary',collection.job_id!)}>Resume saved raw transfer only</button>}
        {collection.recovery?.reason&&<p role="alert">Transfer: {collection.recovery.reason}</p>}
        <details><summary>Collection steps and sensor faults</summary>
          {collection.steps.map(item=><p key={item.id}>{item.id}: {item.status}{item.reason?` · ${item.reason}`:''}</p>)}
          {collection.sources.map(item=><p key={item.id}>{item.id} faults: {Object.entries(item.fault_counts).map(([code,count])=>`${code}=${count}`).join(', ')||'None recorded'}</p>)}
        </details>
      </>}
      <small>Stored collection, not live telemetry. Coordinates remain unaligned; a completed transfer does not make the demo ready.</small>
    </section>}
    <details><summary>Evidence and blockers</summary>
      <p>Attempt: {state?.attempt_id??'None'} · Worker: {state?.job_id??'None'}</p>
      {state?.record&&<p>Observed: {state.record.observed_at_utc} · boot {state.record.boot_id} · release {state.record.release_id}</p>}
      {state?.missing?.map(code=><p key={code}>{code}</p>)}
      {state?.cleanup_error&&<p role="alert">Cleanup: {state.cleanup_error}</p>}
      {state?.evidence&&<p>Local journal: {state.evidence.session_log_complete===true?'Saved':state.evidence.session_log_complete===false?'Incomplete':'Not confirmed'} ·
        Raw export: {state.evidence.evidence_export??'Not confirmed'} ·
        Transfer recovery: {state.evidence.evidence_recovery?.status??'Not started'}</p>}
      {state?.evidence?.evidence_export_error&&<p role="alert">Raw export: {state.evidence.evidence_export_error}</p>}
      {state?.owned&&state.job_id&&transfer&&state.evidence?.evidence_export==='INCOMPLETE'&&
        <button disabled={checkBusy||operationBusy} onClick={()=>transfer('qualification',state.job_id!)}>Resume qualification raw transfer only</button>}
      {state?.evidence?.session_storage?.error&&<p role="alert">Journal storage: {state.evidence.session_storage.error}</p>}
      <p>Existing worker saves its raw journal and robot report. A board snapshot is not continuous telemetry. Target build, calibration and route admission are not proved here.</p>
    </details>
  </section>;
}
