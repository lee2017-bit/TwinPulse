// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';

export interface SessionList {sessions:{job_id:string;modified_s:number}[];historical:true;motion_authorized:false}
export interface SavedEvidenceReview {schema_version:'robot-evidence-offline-review-1';job_id:string;
  status:'COMPLETE'|'INCOMPLETE';reason?:string;error_type?:string;export_status?:string;
  files?:Record<string,string>;raw_ros?:{status:string;message_decode:string;messages?:number;reason?:string};
  contract_errors?:string[];physical_validation:'NOT_RUN_BY_THIS_TOOL';transfer_only:true}
export interface ReplayEvent {event_index:number;pc_t:number;robot_t:number|null;clock_domain:'pc_monotonic';
  kind:string;sequence:number|null;action:string|null;linear_m_s:number|null;angular_rad_s:number|null;
  encoders:number[]|null;observation_sample_t?:number|null;odom_xy_m:number[]|null;observation_gap:boolean}
export interface SessionReview {
  schema:string;job_id:string;historical:true;record_status:string;partial_tail_excluded:boolean;sha256:string;
  provenance:string;physical_success:null;motion_authorized:false;floor_pose_measured:false;clock_domains:string[];
  event_count:number;pc_received:number;pipe_written:number;robot_accepted:number;observation_count:number;
  published_count:number;commands_omitted:number;
  project_id?:string|null;attribution?:'BOUND'|'UNATTRIBUTED';timeline?:ReplayEvent[];
  timeline_events_omitted?:number;
  mode?:string|null;robot_boot_id?:string|null;robot_release_id?:string|null;
  comparison_evidence?:{app_context_capture:'CAPTURED'|'UNAVAILABLE'|'LEGACY_UNKNOWN';
    app_scene_revision:string|null;app_robot_profile_id:string|null;
    mission_scope_sha256:string|null;robot_boot_id:string|null;robot_release_id:string|null;
    room_odom_alignment:'UNVERIFIED'};
  navigation_observations?:{t:number;odom:unknown|null;scan:unknown|null;faults:{odom:string;scan:string}}[];
  navigation_observations_omitted?:number;
  mission_events?:{kind:string;t:number;data:{mission_id:string;tick?:number;status?:string;
    decision?:{reason:string;linear_m_s:number;angular_rad_s:number;navigation:{pose_xy_yaw:number[]}}}}[];
  mission_events_omitted?:number;
  recorded_end?:{status:string|null;reason:string|null;cleanup_confirmed:boolean}|null;
  commands:{sequence:number;action:string;robot_t:number;linear_m_s:number;angular_rad_s:number;source_age_s:number;
    next_observation:{t:number;encoders:number[];torque:boolean;source_age_s:number;voltage_v?:number}|null}[];
}
const actions:Record<string,string>={forward:'Forward',backward:'Backward',left:'Turn left',right:'Turn right',stop:'Stop',watch:'Hold',close:'Close'};
const evidenceFields=[
  ['app_scene_revision','App scene snapshot (not a physical map)'],
  ['app_robot_profile_id','App robot profile (not measured geometry)'],
  ['mission_scope_sha256','Approved mission scope'],
  ['robot_boot_id','Robot boot'],
  ['robot_release_id','Robot release'],
] as const;
function conditionMatch(left:string|null|undefined,right:string|null|undefined){
  return left&&right?(left===right?'Recorded match':'Recorded mismatch'):'Not recorded for both';
}

function SessionReplay({record}:{record:SessionReview}) {
  const events=record.timeline??[];
  const first=events[0]?.pc_t??0,last=events.at(-1)?.pc_t??first,duration=Math.max(0,last-first);
  const [elapsed,setElapsed]=useState(0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState(1);
  // The parent keys this component by job ID. A fresh mount already resets
  // playback; a delayed passive reset can otherwise undo an immediate seek.
  useEffect(()=>{
    if(!playing||!duration)return;
    const timer=window.setInterval(()=>setElapsed(previous=>{
      const next=Math.min(duration,previous+.1*speed);
      if(next>=duration)setPlaying(false);
      return next;
    }),100);
    return ()=>window.clearInterval(timer);
  },[playing,speed,duration]);
  if(!events.length)return <p>No time-ordered events in this record.</p>;
  let index=0;
  for(let i=1;i<events.length;i++)if(events[i].pc_t-first<=elapsed)index=i;else break;
  const current=events[index];
  const points=events.slice(0,index+1).filter(e=>e.odom_xy_m).map(e=>e.odom_xy_m!);
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const minX=Math.min(0,...xs),maxX=Math.max(0,...xs),minY=Math.min(0,...ys),maxY=Math.max(0,...ys);
  const plot=points.map(p=>`${12+276*(p[0]-minX)/Math.max(.01,maxX-minX)},${148-136*(p[1]-minY)/Math.max(.01,maxY-minY)}`).join(' ');
  return <div aria-label="Saved session replay" className="session-replay">
    <h4>Recorded timeline · visual replay only</h4>
    {!!record.timeline_events_omitted&&<p>Recent 1,000 events shown · {record.timeline_events_omitted} earlier events remain in the original saved journal.</p>}
    <p>PC event order and robot timestamps are separate clocks. This player sends no commands. The drawn odom trace is not aligned to the room photo or Twin geometry.</p>
    <div className="action-row">
      <button onClick={()=>setPlaying(v=>!v)} disabled={!duration}>{playing?'Pause':'Play'}</button>
      <button onClick={()=>{setPlaying(false);setElapsed(0);}}>Restart</button>
      <label>Speed <select aria-label="Replay speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>
        <option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
      </select></label>
    </div>
    <label>Seek <input aria-label="Replay position" type="range" min={0} max={Math.max(.1,duration)} step={0.01}
      value={elapsed} onChange={e=>{setPlaying(false);setElapsed(Number(e.target.value));}} /></label>
    <p role="status">{elapsed.toFixed(2)} / {duration.toFixed(2)} s · event {index+1} / {events.length}: {current.kind}
      {current.action?` · ${actions[current.action]??current.action}`:''}
      {current.robot_t!==null?` · robot ${current.robot_t.toFixed(3)} s`:''}
      {current.observation_gap?' · no following encoder observation within 0.5 s':''}</p>
    {current.encoders&&<p>Observed encoders: {current.encoders.join(' / ')} · not measured floor movement</p>}
    {points.length>1&&<div><svg role="img" aria-label="Sparse recorded odometry trace, not room aligned" viewBox="0 0 300 160" width="300" height="160">
      <rect x="0" y="0" width="300" height="160" fill="#12202b"/><polyline points={plot} fill="none" stroke="#59c5e8" strokeWidth="2"/>
    </svg><p>Lines between odom samples are visual interpolation only; missing observations are not filled.</p></div>}
  </div>;
}

export function SessionHistory({api,disabled}:{api:TwinPulseApi;disabled:boolean}) {
  const [list,setList]=useState<SessionList|null>(null),[record,setRecord]=useState<SessionReview|null>(null);
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const [recovery,setRecovery]=useState<{status:string;job_id:string|null;transfer_only:true;
    receipt?:string|null;reason?:string|null}|null>(null);
  const [evidenceReview,setEvidenceReview]=useState<SavedEvidenceReview|null>(null);
  const [comparison,setComparison]=useState<SessionReview|null>(null);
  const generation=useRef(0),comparisonGeneration=useRef(0),evidenceGeneration=useRef(0);
  useEffect(()=>()=>{generation.current++;comparisonGeneration.current++;evidenceGeneration.current++;},[]);
  useEffect(()=>{if(disabled){generation.current++;comparisonGeneration.current++;evidenceGeneration.current++;
    setLoading(false);setError('');setList(null);setRecord(null);setComparison(null);setRecovery(null);setEvidenceReview(null);}},[disabled]);
  useEffect(()=>{
    if(recovery?.status!=='TRANSFERRING')return;
    let cancelled=false;
    const timer=window.setInterval(()=>{void api.physicalState().then(state=>{
      const next=state.evidence_recovery;
      if(!cancelled&&next?.job_id===recovery.job_id)setRecovery(next);
    }).catch(()=>{if(!cancelled)setError('Transfer status unavailable. No robot action was retried. Refresh the saved record later.');});},500);
    return()=>{cancelled=true;window.clearInterval(timer);};
  },[api,recovery?.status,recovery?.job_id]);
  async function load(job?:string){
    if(disabled||loading)return;
    const id=++generation.current;comparisonGeneration.current++;evidenceGeneration.current++;
    setLoading(true);setError('');setRecord(null);setComparison(null);setRecovery(null);setEvidenceReview(null);
    if(!job)setList(null);
    try{
      if(job){const data=await api.physicalSession(job);if(id===generation.current)setRecord(data);}
      else{const data=await api.physicalSessions();if(id===generation.current)setList(data);}
    }catch{if(id===generation.current)setError('Could not read the record. Check for missing, changed, corrupted, or oversized data. No automatic retry.');}
    finally{if(id===generation.current)setLoading(false);}
  }
  async function loadComparison(job:string){
    if(disabled||loading||!record||job===record.job_id)return;
    const id=generation.current,comparisonId=++comparisonGeneration.current;
    setLoading(true);setError('');setComparison(null);
    try{const result=await api.physicalSession(job);
      if(id===generation.current&&comparisonId===comparisonGeneration.current)setComparison(result);}
    catch{if(id===generation.current&&comparisonId===comparisonGeneration.current)
      setError('Could not compare this saved record. It may be missing or changed. No automatic retry.');}
    finally{if(id===generation.current&&comparisonId===comparisonGeneration.current)setLoading(false);}
  }
  function download(){
    if(!record)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download=`session-review-${record.job_id}.json`;a.click();URL.revokeObjectURL(url);
  }
  async function resumeEvidence(){
    if(!record||disabled||loading||recovery?.status==='TRANSFERRING')return;
    setError('');
    try{setRecovery(await api.physicalResumeEvidence(record.job_id,crypto.randomUUID().replaceAll('-','')));}
    catch{setError('Saved evidence transfer could not start. No robot operation was started; check the stored report and connection before retrying.');}
  }
  async function reviewEvidence(){
    if(!record||disabled||loading)return;
    const id=++evidenceGeneration.current,job=record.job_id;
    setLoading(true);setError('');setEvidenceReview(null);
    try{const result=await api.physicalReviewEvidence(job);
      if(id===evidenceGeneration.current&&record.job_id===job)setEvidenceReview(result);}
    catch{if(id===evidenceGeneration.current)setError('Saved evidence could not be reviewed. The local files may be unavailable or unsafe; no transfer or robot action was started.');}
    finally{if(id===evidenceGeneration.current)setLoading(false);}
  }
  return <section className="console-evidence" aria-label="Saved control history">
    <div className="console-section-title"><h3>Saved control history</h3><span>Review is local · transfer requires an explicit click</span></div>
    <button disabled={disabled||loading} onClick={()=>void load()}>Load saved history</button>
    <p className="console-hint">Only records explicitly bound to this project are listed. Older unbound records remain in the legacy archive. History is unavailable during control; this replay never operates the robot.</p>
    {loading&&<p role="status">Checking saved files</p>}{error&&<p role="alert">{error}</p>}
    {list&&<div aria-label="Session list">{list.sessions.length===0?<p>No saved session logs.</p>:list.sessions.map(item=>
      <button key={item.job_id} disabled={disabled||loading} onClick={()=>void load(item.job_id)} aria-label={`Record ${item.job_id}`}>
        {item.job_id.slice(0,8)} · {new Date(item.modified_s*1000).toLocaleString('en-US')}
      </button>)}</div>}
    {record&&<div aria-label="Saved session details">
      <p>{record.provenance==='SYNTHETIC_TRANSPORT'?'Synthetic transport record':'Recorded through real transport · physical success unverified'} · {record.record_status==='COMPLETE_RECORD'?'Consistent end record':'Incomplete record'}</p>
      <p>Recorded ending: {record.recorded_end?`${record.recorded_end.status??'unknown'} · ${record.recorded_end.reason??'reason not recorded'}`:'No ending observed'}</p>
      {record.partial_tail_excluded&&<p>An incomplete final row was excluded. Only the preceding data is shown; the source file was not changed.</p>}
      <p>Received {record.pc_received} · written {record.pipe_written} · accepted {record.robot_accepted} · published {record.published_count} · observed {record.observation_count}</p>
      <p>Pose/scan records {record.navigation_observations?.length??0} · pose received {record.navigation_observations?.filter(x=>x.odom!==null).length??0} · scan received {record.navigation_observations?.filter(x=>x.scan!==null).length??0}</p>
      <p className="console-hint">Previously published sensors are recorded about once per second. This does not start drivers; original coordinates and timestamps are retained in JSON. These records do not certify coordinate alignment, collision avoidance, or measured floor position. Older records may lack them.</p>
      <p className="console-hint">Below are ROS publications on the robot clock and samples within the following 0.5 seconds. Causality, body position, and collision remain unverified; PC and robot clocks are not merged.</p>
      <button disabled={disabled} onClick={download}>Save review JSON</button>
      <div aria-label="Saved evidence offline review">
        <button disabled={disabled||loading} onClick={()=>void reviewEvidence()}>Review saved evidence locally</button>
        <p className="console-hint">Reads saved PC files only. It does not connect to the robot, transfer files, decode unavailable ROS types, or validate physical motion.</p>
        {evidenceReview?.job_id===record.job_id&&<div role="status">
          <p>Saved file integrity: {evidenceReview.status}{evidenceReview.reason?` · ${evidenceReview.reason}`:''}{evidenceReview.error_type?` · ${evidenceReview.error_type}`:''}</p>
          <p>ROS raw: {evidenceReview.raw_ros?.status??'NOT_CAPTURED'} · message decode: {evidenceReview.raw_ros?.message_decode??'NOT_RUN'}{evidenceReview.raw_ros?.reason?` · ${evidenceReview.raw_ros.reason}`:''} · physical validation: NOT RUN</p>
          {!!evidenceReview.contract_errors?.length&&<p>Contract errors: {evidenceReview.contract_errors.join(', ')}</p>}
          {evidenceReview.files&&<ul>{Object.entries(evidenceReview.files).map(([name,status])=><li key={name}>{name}: {status}</li>)}</ul>}
        </div>}
      </div>
      {record.provenance==='RECORDED_REAL_TRANSPORT'&&record.recorded_end&&<div aria-label="Saved evidence recovery">
        <button disabled={disabled||loading||recovery?.status==='TRANSFERRING'} onClick={()=>void resumeEvidence()}>
          Retry saved evidence transfer only</button>
        <p className="console-hint">This opens an SSH file transfer for this finished session only. It does not rerun preparation, sensors, motors or the operation. Existing robot originals remain in place.</p>
        {recovery?.job_id===record.job_id&&<p role="status">Transfer: {recovery.status}{recovery.reason?` · ${recovery.reason}`:''}</p>}
      </div>}
      <p>Project: {record.project_id??'unattributed'} · {record.attribution??'legacy attribution unknown'} · mode {record.mode??'unknown'} · robot boot {record.robot_boot_id??'not recorded'} · release {record.robot_release_id??'not recorded'}</p>
      <p>App scene context at session start: {record.comparison_evidence?.app_context_capture??'legacy unknown'} · not physical alignment or motion permission</p>
      <SessionReplay key={record.job_id} record={record}/>
      {list&&list.sessions.filter(item=>item.job_id!==record.job_id).length>0&&<div aria-label="Compare saved sessions">
        <h4>Side-by-side record comparison</h4>
        <select aria-label="Second saved session" defaultValue="" onChange={event=>{if(event.target.value)void loadComparison(event.target.value);}}>
          <option value="">Select another record</option>{list.sessions.filter(item=>item.job_id!==record.job_id).map(item=><option key={item.job_id} value={item.job_id}>{item.job_id.slice(0,8)}</option>)}
        </select>
        {comparison&&<div><p>Start/goal, policy, sensor conditions and room-to-odom alignment were not fully recorded for both sessions. Outcome ranking is disabled; counts below are descriptive only.</p>
          <table aria-label="Recorded comparison conditions"><thead><tr><th>Condition</th><th>Recorded relationship</th></tr></thead><tbody>
            {evidenceFields.map(([field,label])=><tr key={field}><td>{label}</td><td>{conditionMatch(
              record.comparison_evidence?.[field],comparison.comparison_evidence?.[field])}</td></tr>)}
            <tr><td>Room-to-odom alignment</td><td>Unverified</td></tr>
          </tbody></table>
          <table><thead><tr><th>Metric</th><th>Primary</th><th>Second</th></tr></thead><tbody>
            <tr><td>Provenance</td><td>{record.provenance}</td><td>{comparison.provenance}</td></tr>
            <tr><td>Published</td><td>{record.published_count}</td><td>{comparison.published_count}</td></tr>
            <tr><td>Observations</td><td>{record.observation_count}</td><td>{comparison.observation_count}</td></tr>
            <tr><td>End reason</td><td>{record.recorded_end?.reason??'not recorded'}</td><td>{comparison.recorded_end?.reason??'not recorded'}</td></tr>
          </tbody></table></div>}
      </div>}
      {!!record.mission_events?.length&&<div aria-label="Saved autonomous decisions">
        <h4>Autonomous decision history · saved record</h4>
        <p>Recent mission events {record.mission_events.length} · omitted {record.mission_events_omitted??0}. Not current execution status or proof of physical success.</p>
        <p>Coordinates are derived from recorded odom and are not aligned with the room in the photo. The 10 latest decisions follow.</p>
        <div style={{overflowX:'auto'}}><table><thead><tr><th>Mission tick</th><th>Decision / status</th><th>Observed x / y / yaw</th><th>Output v / w</th></tr></thead>
          <tbody>{record.mission_events.filter(e=>e.kind==='mission_decision'&&e.data.decision).slice(-10).map(e=>
            <tr key={`${e.data.mission_id}-${e.data.tick}`}><td>{e.data.tick}</td><td>{e.data.decision!.reason} / {e.data.status}</td>
              <td>{e.data.decision!.navigation.pose_xy_yaw.map(v=>v.toFixed(3)).join(' / ')}</td>
              <td>{e.data.decision!.linear_m_s.toFixed(3)}m/s / {e.data.decision!.angular_rad_s.toFixed(3)}rad/s</td></tr>)}</tbody>
        </table></div>
      </div>}
      <p>Recent publications {record.commands.length} · omitted {record.commands_omitted}</p>
      <div style={{overflowX:'auto'}}><table><thead><tr><th>Sequence / robot time (s)</th><th>Command</th><th>v / w</th><th>Following encoder sample</th></tr></thead>
        <tbody>{record.commands.map((command,index)=><tr key={index}>
          <td>{command.sequence} / {command.robot_t.toFixed(3)}</td><td>{actions[command.action]??command.action}</td>
          <td>{command.linear_m_s.toFixed(3)}m/s / {command.angular_rad_s.toFixed(3)}rad/s</td>
          <td>{command.next_observation?`${command.next_observation.encoders.join(' / ')} @ ${command.next_observation.t.toFixed(3)}s`:'No observation'}</td>
        </tr>)}</tbody></table></div>
    </div>}
  </section>;
}
