// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
import {useEffect,useId,useMemo,useRef,useState} from 'react';
import type {RobotFleetOperation,RobotFleetRobot} from './robot-fleet-types';
import {currentDiagnosticStatus,diagnosticContinuity,diagnosticPauseWindows,diagnosticRecord,diagnosticStatistics,diagnosticText,liveDiagnosticRows,
  projectDiagnosticEvents,readDiagnosticFile,recordedTimingPolicy,type DiagnosticCategory,type ImportedDiagnostics} from './robot-operation-diagnostics';
import './robot-operation-diagnostics.css';

type Props={robot:RobotFleetRobot;operation:RobotFleetOperation|null;available:boolean};
const categories:DiagnosticCategory[]=['input','sensor','tracking','battery','stop','recording','state'];
const ms=(value:number|null)=>value===null?'insufficient evidence':`${value.toFixed(2)} ms`;
export function RobotOperationDiagnostics({robot,operation,available}:Props){
  const [imported,setImported]=useState<ImportedDiagnostics|null>(null),[error,setError]=useState<string|null>(null);
  const [reading,setReading]=useState(false),[readBytes,setReadBytes]=useState(0),[cursor,setCursor]=useState(0);
  const [category,setCategory]=useState('all'),[clock,setClock]=useState('all');
  const reader=useRef<AbortController|null>(null),generation=useRef(0),owner=useRef('');
  const identity=`${robot.robot_id}:${operation?.operation_id??''}`;owner.current=identity;
  const cursorId=useId();
  useEffect(()=>{generation.current++;reader.current?.abort();setImported(null);setReading(false);setError(null);setCursor(0);setCategory('all');setClock('all');
    return()=>{generation.current++;reader.current?.abort();};},[identity]);
  const summary=useMemo(()=>projectDiagnosticEvents(operation?.events??[]),[operation]);
  const projection=imported?.projection??summary;
  const rows=useMemo(()=>projection.rows.filter(row=>(category==='all'||row.categories.includes(category as DiagnosticCategory))&&(clock==='all'||row.clock===clock)),[projection,category,clock]);
  const selected=rows[Math.min(cursor,Math.max(0,rows.length-1))];
  const start=Math.max(0,Math.min(cursor-10,rows.length-40)),visible=rows.slice(start,start+40);
  const sensorStats=useMemo(()=>diagnosticStatistics(projection.rows,'sensor'),[projection]);
  const computeStats=useMemo(()=>diagnosticStatistics(projection.rows,'compute'),[projection]);
  const currentPolicy=diagnosticRecord(diagnosticRecord(robot).timing_policy),savedPolicy=useMemo(()=>recordedTimingPolicy(operation),[operation]);
  const policy=Object.keys(currentPolicy).length?currentPolicy:savedPolicy;
  const limits=diagnosticRecord(policy?.limits),manifest=diagnosticRecord(operation?.manifest),stream=diagnosticRecord(manifest.stream);
  const savedLimit=diagnosticRecord(diagnosticRecord(savedPolicy?.limits).ros_source).seconds;
  const sourceLimitMs=typeof savedLimit==='number'&&Number.isFinite(savedLimit)&&savedLimit>0?savedLimit*1000:null;
  const continuity=useMemo(()=>diagnosticContinuity(projection.rows,sourceLimitMs),[projection,sourceLimitMs]);
  const pauses=useMemo(()=>diagnosticPauseWindows(projection.rows),[projection]);
  const resolution=diagnosticRecord(manifest.field_trial_resolution),resolvedTrials=Array.isArray(resolution.trials)?resolution.trials.map(diagnosticRecord):[];
  async function openFile(file:File){
    if(!operation)return;reader.current?.abort();const cancel=new AbortController(),id=++generation.current,captured=identity;reader.current=cancel;
    setReading(true);setReadBytes(0);setError(null);
    try{const value=await readDiagnosticFile(file,operation,cancel.signal,bytes=>{if(owner.current===captured&&generation.current===id)setReadBytes(bytes);});
      if(owner.current!==captured||generation.current!==id)return;setImported(value);setCursor(0);setCategory('all');setClock('all');
    }catch(caught){if(owner.current===captured&&generation.current===id)setError(caught instanceof Error?caught.message:'Could not read diagnostic file.');}
    finally{if(owner.current===captured&&generation.current===id)setReading(false);}
  }
  return <details className="robot-diagnostics" aria-label="Robot diagnostic timeline">
    <summary>Diagnostic timeline · read-only</summary>
    <p>No control, sensor replay, model upload or scene change is performed here.</p>
    <details><summary>Current reported diagnostics</summary>
      <p role="status">{currentDiagnosticStatus(robot,available)}</p>
      <dl>{liveDiagnosticRows(robot).map(([name,value])=><div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
      <small>Source age compares the recorded ROS header with ROS now. Callback receipt age is another measurement. Neither is network round-trip time or calibrated hardware acquisition time. A connected heartbeat does not renew an old diagnostic check.</small>
    </details>
    <details><summary>Recorded timing limits and clock domains</summary>
      {policy?<><p>Basis: {diagnosticText(policy.basis,300)} · schema {diagnosticText(policy.schema)} · adaptive {diagnosticText(policy.adaptive)}</p>
        <small>{Object.keys(currentPolicy).length?'Reported robot policy; current connection and validity remain separate.':'Policy from a saved operation event. It is historical, not proof of current robot configuration.'}</small>
        <div className="robot-diagnostics-table"><table><thead><tr><th>Rule</th><th>Limit</th><th>Clock</th><th>Failure / recovery</th></tr></thead>
          <tbody>{Object.entries(limits).map(([name,value])=>{const rule=diagnosticRecord(value);return <tr key={name}><th>{name}</th><td>{typeof rule.seconds==='number'&&Number.isFinite(rule.seconds)?`${rule.seconds*1000} ms`:'not recorded'}</td><td>{diagnosticText(rule.clock)}</td><td>{diagnosticText(rule.failure)} / {diagnosticText(rule.recovery)}</td></tr>;})}</tbody></table></div></>:
        <p>Timing policy not recorded. No threshold has been inferred or changed.</p>}
    </details>
    <details><summary>Saved operation and evidence scope</summary>
      <dl><div><dt>Operation</dt><dd>{operation?.operation_id??'Open Operation logs first'}</dd></div><div><dt>Robot</dt><dd>{robot.robot_id}</dd></div>
        <div><dt>Project / chat</dt><dd>{operation?.project_id??'not recorded'}</dd></div><div><dt>Connection-start Twin</dt><dd>{diagnosticText(diagnosticRecord(manifest.source_twin_context).scene_revision,80)}</dd></div>
        <div><dt>Alignment</dt><dd>{diagnosticText(diagnosticRecord(diagnosticRecord(manifest.source_twin_context).alignment).status)}</dd></div>
        <div><dt>Record completeness</dt><dd>{diagnosticText(manifest.complete)} · {diagnosticText(stream.error??manifest.end_reason)}</dd></div>
        <div><dt>Original runtime events</dt><dd>{diagnosticText(stream.event_count)}</dd></div></dl>
      <small>A matching ID is a reference, not visual scene verification or world alignment. A complete PC segment does not prove complete field evidence or physical stopping.</small>
      {Object.keys(resolution).length>0&&<><p>Historical field persistence resolution: {diagnosticText(resolution.status)} · authority restored {diagnosticText(resolution.authority_restored)}.</p>
        <div className="robot-diagnostics-table"><table aria-label="Historical field persistence resolution"><thead><tr><th>Trial ID</th><th>Recorded / resolved status</th><th>Reason</th><th>Persistence</th></tr></thead>
          <tbody>{resolvedTrials.slice(0,32).map((trial,index)=><tr key={index}><td>{diagnosticText(trial.trial_id,80)}</td><td>{diagnosticText(trial.status)}</td><td>{diagnosticText(trial.reason)}</td><td>{diagnosticText(diagnosticRecord(trial.persistence).state)}</td></tr>)}</tbody></table></div>
        <small>Saved read-only resolution. PENDING_PERSISTENCE is not PASS; writer-incomplete or unconfirmed ACK remains unverified. Historical results restore no connection, qualification or motion authority.</small></>}
    </details>
    {!operation?<p>Open Operation logs for the selected robot to inspect its recorded timeline.</p>:<>
      <p className="robot-diagnostics-scope" role="status">Historical read-only record · {imported?imported.scope:'bounded operation summary; not the complete raw stream'}.
        {' '}{projection.sourceEvents} source events · {projection.rows.length} projected diagnostic rows · {projection.rawOmitted} raw payload rows omitted from display.</p>
      {projection.unverifiedIdentities>0&&<p>{projection.unverifiedIdentities} legacy event identities are not recorded individually. The operation wrapper is their only available linkage.</p>}
      <label className="robot-diagnostics-file">Open recorded JSON / JSONL locally (one segment, up to 8 MiB)
        <input type="file" accept=".json,.jsonl,application/json" disabled={reading} onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file)void openFile(file);}}/></label>
      {reading&&<p role="status">Reading selected segment · {readBytes.toLocaleString()} bytes. <button type="button" onClick={()=>reader.current?.abort()}>Cancel diagnostic reading</button></p>}
      {error&&<p role="alert">{error}</p>}
      {imported&&<><p>{imported.name} · {imported.bytes.toLocaleString()} bytes · SHA256 <code>{imported.sha256}</code> · {imported.verifiedManifest?'Exact segment SHA and byte count match the operation manifest':'No matching segment SHA in the open manifest; origin remains unverified'}.</p>
        <button type="button" onClick={()=>{reader.current?.abort();generation.current++;setReading(false);setImported(null);setCursor(0);setCategory('all');setClock('all');}}>Return to saved summary</button></>}
      <details><summary>Measured distribution · selected evidence only</summary>
        <div className="robot-diagnostics-table"><table><thead><tr><th>Measurement</th><th>Unique samples</th><th>Mean</th><th>Sample SD</th><th>Observed p99</th><th>Observed p99.9</th><th>Maximum</th></tr></thead>
          <tbody>{([['Sensor source age at original callback',sensorStats],['Tracking measured compute duration',computeStats]] as const).map(([name,stat])=><tr key={name}><th>{name}</th><td>{stat.n}{stat.conflicting?` · ${stat.conflicting} conflicting duplicates`:''}</td><td>{ms(stat.mean)}</td><td>{ms(stat.sd)}</td><td>{ms(stat.p99)}</td><td>{ms(stat.p999)}</td><td>{ms(stat.max)}</td></tr>)}</tbody></table></div>
        <p>Maximum observed consecutive callback receipt gap: {continuity.maximumGapMs===null?'NOT_RECORDED / insufficient or conflicting receipt clocks':ms(continuity.maximumGapMs)} · {continuity.gaps} pairs · {continuity.missingReceipts} missing receipts · {continuity.clockConflicts} clock / identity conflicts.</p>
        <p>Recorded source-age threshold: {sourceLimitMs===null?'NOT_RECORDED':ms(sourceLimitMs)} · at-or-above threshold {continuity.overPercent===null?'NOT_RECORDED':`${continuity.over}/${continuity.ageSamples} (${continuity.overPercent.toFixed(3)}%)`}. The saved operation policy supplies this value; no new limit is inferred.</p>
        <small>Source statistics use original sensor_state callback records with stream + observation sequence. Repeated heartbeat diagnostics are excluded. Receipt gaps use the original callback robot receipt clock within one connection and ROS stream. Compute statistics use explicit stream + job ID and measured compute_elapsed_s; they are observed results, not a count of all attempted jobs. Fewer than two unique samples or conflicting duplicates gives insufficient evidence. SD is n−1; p99 and p99.9 use nearest rank. Selected segments can omit failures or mix load states; these statistics do not calibrate a timeout, prove normal response, or change any limit.</small>
        <div className="robot-diagnostics-table"><table aria-label="Observed pause windows"><thead><tr><th>Clock / epoch</th><th>Observed span</th><th>Pause count</th><th>Count basis</th><th>Per observed hour</th></tr></thead>
          <tbody>{pauses.slice(0,32).map((window,index)=><tr key={index}><td>{window.clock}<small>{window.epoch}</small></td><td>{window.seconds.toFixed(3)} s</td><td>{window.count}</td><td>{window.method}{window.initialPaused?' · already PAUSED at first state, not counted':''}</td><td>{window.perHour===null?'NOT_RECORDED':window.perHour.toFixed(3)}</td></tr>)}</tbody></table></div>
        {!pauses.length&&<p>Pause observation clock / state: NOT_RECORDED.</p>}
        <small>Pause count/rate applies only to state observations in this summary or selected segment, separated by clock and epoch. Sampled PAUSED transitions can miss intervening states and are a lower bound; repeated heartbeats and an initially paused state are not new pause events. The rate is normalized from this observed span, not a long-run prediction. Whether any pause was unnecessary requires reviewing its cause.</small>
      </details>
      <div className="robot-diagnostics-filters"><label>Recorded category<select value={category} onChange={event=>{setCategory(event.target.value);setCursor(0);}}><option value="all">All</option>{categories.map(name=><option key={name} value={name}>{name}</option>)}</select></label>
        <label>Clock field<select value={clock} onChange={event=>{setClock(event.target.value);setCursor(0);}}><option value="all">Original record order · clocks not synchronized</option>{[...new Set(projection.rows.map(row=>row.clock))].map(name=><option key={name} value={name}>{name}</option>)}</select></label></div>
      <label htmlFor={cursorId}>Recorded event cursor · {rows.length?Math.min(cursor+1,rows.length):0}/{rows.length} filtered rows</label>
      <input id={cursorId} aria-label="Recorded event cursor · read-only" type="range" min={0} max={Math.max(0,rows.length-1)} value={Math.min(cursor,Math.max(0,rows.length-1))} disabled={!rows.length}
        onChange={event=>setCursor(Number(event.target.value))}/>
      <div className="robot-diagnostics-step"><button type="button" disabled={!rows.length||cursor===0} onClick={()=>setCursor(value=>value-1)}>Previous recorded event</button>
        <button type="button" disabled={!rows.length||cursor>=rows.length-1} onClick={()=>setCursor(value=>value+1)}>Next recorded event</button></div>
      {selected&&<section aria-label="Selected recorded diagnostic"><h6>#{selected.index+1} · {selected.kind}</h6>
        <dl><div><dt>Clock field</dt><dd>{selected.clock}</dd></div><div><dt>Recorded clock value</dt><dd>{selected.time===null?'not recorded':String(selected.time)}</dd></div>
          <div><dt>Connection epoch</dt><dd>{selected.epoch}</dd></div><div><dt>Original sequence</dt><dd>{selected.sequence??'not recorded'}</dd></div>
          <div><dt>Recorded scene / context</dt><dd>{selected.scene}</dd></div><div><dt>Request ID</dt><dd>{selected.request}</dd></div>
          {selected.values.map(([name,value],index)=><div key={`${index}-${name}`}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
      </section>}
      <div className="robot-diagnostics-table"><table aria-label="Recorded diagnostic events"><thead><tr><th>Source order</th><th>Recorded time and clock</th><th>Event</th><th>Values</th></tr></thead>
        <tbody>{visible.map((row,index)=><tr key={row.index} aria-current={row===selected?'true':undefined}><td><button type="button" onClick={()=>setCursor(start+index)}>#{row.index+1}</button></td><td>{row.time===null?'not recorded':String(row.time)}<small>{row.clock}</small></td><td>{row.kind}</td><td>{row.values.slice(0,4).map(([name,value])=><span key={name}>{name}: {value}<br/></span>)}</td></tr>)}</tbody></table></div>
      <small>Showing at most 40 projected rows around the cursor, in original record order. Robot monotonic, host monotonic and UTC are never subtracted across domains or epochs. Missing clock fields remain missing. Scrubbing only changes this saved-data view.</small>
    </>}
  </details>;
}
