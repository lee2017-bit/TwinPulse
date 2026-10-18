// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import {ModelComparison,type ModelComparisonResult} from './ModelComparison';
import {SensorMapLocalization} from './SensorMapLocalization';

export interface ObservationMapResult {
  revision:string;job_id:string;source_revision:string;status:string;frame_count:number;
  coordinate_frame:string;paired_frames:number;rejected_frames:number;sampled_hits:number;
  endpoint_cells:number[][];bounds_m:number[];
  keyframes:{frame:number;elapsed_s:number;sensor_pose:number[];points:number[][]}[];
  trajectory:{stamp_ns:number;pose:number[]}[];
  timing:{header_basis:string;beam_order:string;acquisition_timing_verified:false};
  failures:{frame:number;reason:string}[];
  photo_geometry_used:false;motion_authorized:false;physical_demo_ready:false;
}

export function ObservationMap({api,job,disabled,roomRevision='',onDiagnostic,jobs=[]}:{api:TwinPulseApi;job:string;disabled:boolean;roomRevision?:string;onDiagnostic?:()=>void;jobs?:string[]}) {
  const [map,setMap]=useState<ObservationMapResult|null>(null),[busy,setBusy]=useState(false);
  const [error,setError]=useState(''),[cursor,setCursor]=useState(0),[playing,setPlaying]=useState(false);
  const request=useRef(0);
  const [comparison,setComparison]=useState<ModelComparisonResult|null>(null);
  const [activity,setActivity]=useState('build');
  useEffect(()=>{request.current++;setMap(null);setBusy(false);setError('');setCursor(0);setPlaying(false);
    setComparison(null);return ()=>{request.current++;};},[job,disabled,roomRevision]);
  useEffect(()=>{
    if(!playing||!map)return;
    if(cursor>=map.keyframes.length-1){setPlaying(false);return;}
    const next=map.keyframes[cursor+1],current=map.keyframes[cursor];
    // Historical keyframe playback at 4x acquisition-header time, no command.
    const timer=window.setTimeout(()=>setCursor(c=>c+1),Math.max(50,(next.elapsed_s-current.elapsed_s)*250));
    return ()=>window.clearTimeout(timer);
  },[playing,map,cursor]);
  async function build(){
    setActivity('build');
    onDiagnostic?.();setComparison(null);
    const token=++request.current;setMap(null);setBusy(true);setError('');setPlaying(false);
    try{const value=await api.sessionObservationMap(job);if(token===request.current){setMap(value);setCursor(0);}}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Observation map failed. No coordinates retained.');}
    finally{if(token===request.current)setBusy(false);}
  }
  async function compare(){
    setActivity('compare');
    if(!map)return;onDiagnostic?.();const token=++request.current;
    setBusy(true);setError('');setPlaying(false);setComparison(null);
    try{const value=await api.compareObservationModel(job,roomRevision,map.revision);if(token===request.current)setComparison(value);}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Model comparison failed. No geometry changed.');}
    finally{if(token===request.current)setBusy(false);}
  }
  const key=map?.keyframes[cursor];
  const bounds=map?.bounds_m??[-1,1,-1,1];
  const x=bounds[0]*100,y=-bounds[3]*100,w=Math.max(50,(bounds[1]-bounds[0])*100),h=Math.max(50,(bounds[3]-bounds[2])*100);
  return <section aria-label="Session observation map" className="native-quality">
    <h4>Observed scans · independent of photo geometry</h4>
    <p>Inspect the recorded session before fitting the approximate 3D room. No robot connection or room changes.</p>
    <button disabled={disabled||busy||!job} onClick={()=>void build()}>Build observation map · entire session</button>
    {busy&&<p role="status">{activity==='sensor'?'Finding recorded scan position in the sensor map…':map?'Comparing multiple saved scans with the unchanged photo model…':'Projecting saved scan returns and checking timing…'} No robot action.</p>}
    {error&&<p role="alert">{error}</p>}
    {map&&<>
      <p role="status">Diagnostic map · {map.paired_frames}/{map.frame_count} declared-time paired frames · {map.rejected_frames} rejected</p>
      <p>Timing unverified · nominal sensor mounting · odom may drift. This is not SLAM, free-space clearance or a measured room.</p>
      <svg role="img" aria-label="Whole-session endpoints and selected historical scan in session odom" viewBox={`${x} ${y} ${w} ${h}`}
        style={{width:'100%',maxWidth:640,aspectRatio:`${w} / ${h}`,background:'#101923'}}>
        {map.endpoint_cells.map((p,i)=><circle key={`end-${i}`} cx={p[0]*100} cy={-p[1]*100} r="1.3" fill="#687b89"/>)}
        <polyline points={map.trajectory.map(p=>`${p.pose[0]*100},${-p.pose[1]*100}`).join(' ')} fill="none" stroke="#e4ab52" strokeWidth="1.3"/>
        {key?.points.map((p,i)=><circle key={`ray-${i}`} cx={p[0]*100} cy={-p[1]*100} r="2" fill="#59ead9"/>)}
        {key&&<g transform={`translate(${key.sensor_pose[0]*100} ${-key.sensor_pose[1]*100}) rotate(${-key.sensor_pose[2]*180/Math.PI})`}>
          <circle r="4" fill="#d0f8ff"/><line x2="12" stroke="#d0f8ff" strokeWidth="2"/></g>}
      </svg>
      <p>Gray: all-session endpoint evidence · amber: odom trace · cyan: selected recorded scan.</p>
      <label>Recorded scan time<input aria-label="Observation scan time" type="range" min="0" max={map.keyframes.length-1} step="1" value={cursor}
        onChange={e=>{setPlaying(false);setCursor(Number(e.target.value));}}/></label>
      <p>Original frame {key?key.frame+1:0}/{map.frame_count} · {key?.elapsed_s.toFixed(2)} s · {map.keyframes.length} sampled playback keyframes</p>
      <button onClick={()=>{if(cursor===map.keyframes.length-1)setCursor(0);setPlaying(p=>!p);}} disabled={map.keyframes.length<2}>{playing?'Pause recorded scans':'Play recorded scans · 4×'}</button>
      <p>No scan-to-room transform or movement permission is created. Missing rays stay unknown; gray endpoints include later frames, not current visibility.</p>
      <button disabled={disabled||busy||!roomRevision} onClick={()=>void compare()}>Compare with photo 3D · multiple frames</button>
      {comparison&&<ModelComparison value={comparison}/>}
      <SensorMapLocalization api={api} referenceJob={job} observationRevision={map.revision} jobs={jobs} roomRevision={roomRevision} disabled={disabled||busy}
        onBegin={()=>{onDiagnostic?.();setComparison(null);setPlaying(false);setActivity('sensor');setBusy(true);}} onEnd={()=>setBusy(false)}/>
      <details><summary>Source, timing and rejected frames</summary>
        <p>Session {map.job_id} · raw revision {map.source_revision} · {map.coordinate_frame}</p>
        <p>{map.timing.header_basis} · {map.timing.beam_order}</p>
        <p>5 cm endpoint bins, returns within 8 m, up to 160 original-index samples per scan. No free-space inference or pose correction.</p>
        <ul>{map.failures.map(f=><li key={f.frame}>Frame {f.frame}: {f.reason}</li>)}</ul>
      </details>
    </>}
  </section>;
}
