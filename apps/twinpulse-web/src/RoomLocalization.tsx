// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {BedroomReviewState} from './BedroomTwin';
import {ObservationMap} from './ObservationMap';

export interface LocalizationResult {
  revision:string;epoch:number;job_id:string;frame:number;frame_count:number;elapsed_s:number;duration_s:number;
  stamp_ns:number;source_revision:string;goal_candidate_available:boolean;
  match:{status:string;mean_error_m?:number;inlier_fraction?:number;alternative_margin_m?:number|null};
  robot_pose_room_candidate:number[]|null;scan_points_room_candidate:number[][];
  trajectory_candidate:{stamp_ns:number;pose:number[]}[];
  outline:{bounds_m:number[];segments:number[][][]};
  timing:{paired_frames:number;rejected_frames:number;failures:{frame:number;reason:string}[]};
  diagnostics:{decoded_counts:Record<string,number>;tf_static_count:number;sensor_extrinsic:string};
  alignment_verified:false;motion_authorized:false;physical_demo_ready:false;
}

export function RoomLocalization({api,review,backendReady,canPreview=false,refresh}:{api:TwinPulseApi;review:BedroomReviewState;backendReady:boolean;canPreview?:boolean;refresh?:()=>Promise<void>}){
  const [jobs,setJobs]=useState<string[]>([]),[job,setJob]=useState(''),[frame,setFrame]=useState(0);
  const [result,setResult]=useState<LocalizationResult|null>(null),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[goal,setGoal]=useState(['0','0']),[mapped,setMapped]=useState<number[]|null>(null);
  const [previewStatus,setPreviewStatus]=useState('');
  const request=useRef(0);
  useEffect(()=>()=>{request.current++;},[]);
  useEffect(()=>{request.current++;setResult(null);setMapped(null);setError('');setPreviewStatus('');setBusy(false);},[review.revision,backendReady]);
  function clear(){request.current++;setResult(null);setMapped(null);setError('');setPreviewStatus('');}
  async function preview(){
    if(!result)return;const token=request.current;setBusy(true);setError('');setPreviewStatus('');
    try{const operation=await api.previewLocalizedRoom(review.revision,result.revision,crypto.randomUUID());
      if(token===request.current){setPreviewStatus(`3D preview request ${operation.status}. Check the Isaac window; this is a historical position candidate, not measured alignment.`);await refresh?.();}}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'3D preview failed.');}
    finally{setBusy(false);}
  }
  async function sessions(){
    clear();const token=request.current;setBusy(true);
    try{const list=await api.physicalSessions();if(token===request.current){const ids=list.sessions.map(s=>s.job_id);setJobs(ids);setJob(ids[0]??'');setFrame(0);}}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Saved sessions are unavailable.');}
    finally{setBusy(false);}
  }
  async function match(){
    clear();const token=request.current;setBusy(true);
    try{const value=await api.roomLocalization(job,frame,review.revision);if(token===request.current)setResult(value);}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Scan review failed. No coordinates were retained.');}
    finally{setBusy(false);}
  }
  async function invalidate(){
    clear();setBusy(true);
    try{await api.invalidateRoomLocalization();setError('Previous position invalidated. Review a new scan before using coordinates.');}
    catch(e){setError(e instanceof Error?e.message:'Could not confirm backend invalidation. Do not use old coordinates.');}
    finally{setBusy(false);}
  }
  async function convert(){
    if(!result)return;const token=request.current;setBusy(true);setMapped(null);setError('');
    try{
      if(goal.some(v=>!v.trim()||!Number.isFinite(Number(v))))throw Error('Enter finite goal coordinates.');
      const value=await api.localizedRoomGoal(review.revision,result.revision,result.epoch,goal.map(Number));
      if(token===request.current)setMapped(value.odom_goal_candidate_m);
    }catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Goal conversion failed.');}
    finally{setBusy(false);}
  }
  const pose=result?.robot_pose_room_candidate;
  return <section className="native-quality" aria-label="Automatic saved scan localization">
    <h3>Scan → room position → goal</h3>
    <p>Route-independent offline review. No robot connection or movement. Photo geometry and nominal sensor mounting are not measured calibration.</p>
    <div className="native-controls">
      <button disabled={busy||!backendReady} onClick={()=>void sessions()}>Load saved sessions</button>
      <label>Saved session<select aria-label="Localization saved session" disabled={busy} value={job} onChange={e=>{clear();setJob(e.target.value);setFrame(0);}}>
        <option value="">Select a session</option>{jobs.map(id=><option key={id} value={id}>{id.slice(0,12)}</option>)}</select></label>
      <label>Original scan frame<input aria-label="Localization scan frame" type="number" min="0" max={result?result.frame_count-1:8191} step="1" value={frame} disabled={busy}
        onChange={e=>{clear();setFrame(Number(e.target.value));}}/></label>
      <button disabled={busy||!backendReady||!job||!Number.isInteger(frame)||frame<0} onClick={()=>void match()}>Find position from scan</button>
      <button disabled={!backendReady} onClick={()=>void invalidate()}>Robot moved by hand · invalidate position</button>
    </div>
    <ObservationMap api={api} job={job} jobs={jobs} disabled={!backendReady||busy} roomRevision={review.revision} onDiagnostic={clear}/>
    {busy&&<p role="status" aria-live="polite">Reviewing original data / finding position… No movement.</p>}
    {error&&<p role="alert">{error}</p>}
    {result&&<>
      <p role="status">{result.match.status.replaceAll('_',' ')} · frame {result.frame+1}/{result.frame_count} · {result.elapsed_s.toFixed(2)} / {result.duration_s.toFixed(2)} s
        {result.match.mean_error_m!==undefined&&` · mean outline error ${(result.match.mean_error_m*1000).toFixed(0)} mm`}</p>
      {pose&&<p>Robot position candidate: X {pose[0].toFixed(3)} m · Y {pose[1].toFixed(3)} m · heading {(pose[2]*180/Math.PI).toFixed(1)}°. Not a measured floor pose.</p>}
      <button disabled={busy||!canPreview||!pose} onClick={()=>void preview()}>Show candidate scan and Burger in 3D</button>
      {!canPreview&&<p>3D overlay requires a connected, updated Isaac preview adapter. Offline position review remains available.</p>}
      {previewStatus&&<p role="status">{previewStatus}</p>}
      <svg role="img" aria-label="Recorded scan and trajectory in approximate room" viewBox="-160 -230 320 460" style={{width:'100%',maxWidth:440,aspectRatio:'320 / 460',background:'#101923'}}>
        {result.outline.segments.map((s,i)=><line key={`outline-${i}`} x1={s[0][0]*100} y1={-s[0][1]*100} x2={s[1][0]*100} y2={-s[1][1]*100} stroke="#8295a7" strokeWidth="2"/>)}
        <polyline points={result.trajectory_candidate.map(p=>`${p.pose[0]*100},${-p.pose[1]*100}`).join(' ')} fill="none" stroke="#e4ab52" strokeWidth="1"/>
        {result.scan_points_room_candidate.map((p,i)=><circle key={`scan-${i}`} cx={p[0]*100} cy={-p[1]*100} r="1.7" fill="#59ead9"/>)}
        {pose&&<g transform={`translate(${pose[0]*100} ${-pose[1]*100}) rotate(${-pose[2]*180/Math.PI})`}><circle r="6" fill="#d0f8ff"/><line x2="14" stroke="#d0f8ff" strokeWidth="3"/></g>}
      </svg>
      <p>Declared-time paired frames: {result.timing.paired_frames} · rejected: {result.timing.rejected_frames}. Actual beam acquisition timing is unverified. Unknown rays remain unknown. The trace is transformed odometry, not SLAM or a surveyed map.</p>
      {result.timing.failures.length>0&&<details><summary>Rejected frame reasons</summary><ul>{result.timing.failures.map(f=><li key={f.frame}>Frame {f.frame}: {f.reason}</li>)}</ul></details>}
      <div className="native-controls">{['X','Y'].map((axis,i)=><label key={axis}>Goal {axis} (m)<input type="number" aria-label={`Localized goal ${axis}`} step=".01" disabled={busy} value={goal[i]}
        onChange={e=>{setMapped(null);setGoal(goal.map((v,j)=>i===j?e.target.value:v));}}/></label>)}
        <button disabled={busy||!result.goal_candidate_available} onClick={()=>void convert()}>Convert goal · review only</button>
      </div>
      {!result.goal_candidate_available&&<p>Goal conversion unavailable: scan quality or timing did not establish a unique candidate.</p>}
      {mapped&&<p role="status">Odom goal candidate: {mapped.map(v=>v.toFixed(3)).join(' / ')} m. Saved frame only; no physical mission request.</p>}
      <details><summary>Data and calibration boundaries</summary><p>{Object.entries(result.diagnostics.decoded_counts).map(([k,v])=>`${k}: ${v}`).join(' · ')} · static TF: {result.diagnostics.tf_static_count}</p>
        <p>Sensor mounting: {result.diagnostics.sensor_extrinsic}. Each new session starts without a position. Manual repositioning invalidates the old binding. Ambiguous matches are not used for goal conversion.</p></details>
    </>}
  </section>;
}
