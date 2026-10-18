// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import {SensorPhotoLink} from './SensorPhotoLink';

export interface SensorMapResult {
  revision:string;status:string;job_id:string;query_job_id:string;frame:number;query_frames:number[];
  reference_endpoint_cells:number[][];bounds_m:number[];reference_retained_scan_count:number;
  holdout:{excluded_reference_frames:number[];direct_query_scan_reuse:false};alternative_margin_m:number|null;
  best_diagnostic_hypothesis:null|{sensor_pose_reference_candidate:number[];weighted_capped_mean_error_m:number;supported_query_frames:number};
  overlays:{frame:number;points:number[][];sensor_pose_reference_candidate:number[]}[];
  photo_geometry_used:false;room_transform_created:false;motion_authorized:false;physical_demo_ready:false;
}

export function SensorMapLocalization({api,referenceJob,observationRevision,jobs,disabled,onBegin,onEnd,roomRevision=''}:{api:TwinPulseApi;referenceJob:string;observationRevision:string;jobs:string[];disabled:boolean;onBegin:()=>void;onEnd:()=>void;roomRevision?:string}){
  const [query,setQuery]=useState(referenceJob),[frame,setFrame]=useState(0),[busy,setBusy]=useState(false);
  const [value,setValue]=useState<SensorMapResult|null>(null),[error,setError]=useState('');const request=useRef(0);
  useEffect(()=>{request.current++;setQuery(referenceJob);setFrame(0);setValue(null);setError('');setBusy(false);
    return ()=>{request.current++;};},[referenceJob,observationRevision]);
  function clear(){request.current++;setValue(null);setError('');}
  async function locate(){
    const token=++request.current;setValue(null);setError('');setBusy(true);onBegin();
    try{const result=await api.locateSensorMap(referenceJob,observationRevision,query,frame);if(token===request.current)setValue(result);}
    catch(e){if(token===request.current)setError(e instanceof Error?e.message:'Sensor-map matching failed. No location retained.');}
    finally{if(token===request.current){setBusy(false);onEnd();}}
  }
  const cloud=value?.overlays.flatMap(k=>k.points)??[],all=[...(value?.reference_endpoint_cells??[]),...cloud];
  const bounds=value?.bounds_m??[-1,1,-1,1],x=Math.min(bounds[0],...all.map(p=>p[0]))-.1,y=Math.min(bounds[2],...all.map(p=>p[1]))-.1;
  const w=Math.max(1,Math.max(bounds[1],...all.map(p=>p[0]))-x+.1),h=Math.max(1,Math.max(bounds[3],...all.map(p=>p[1]))-y+.1);
  const best=value?.best_diagnostic_hypothesis,pose=best?.sensor_pose_reference_candidate;
  return <section aria-label="Sensor map localization">
    <h4>Find scan position in the sensor map</h4>
    <p>Uses observed scan endpoints, not photo furniture boxes. Three consecutive stored scans; no old global position or fixed route.</p>
    <label>Test session<select aria-label="Sensor map test session" value={query} disabled={disabled||busy} onChange={e=>{clear();setQuery(e.target.value);setFrame(0);}}>
      {[...new Set([referenceJob,...jobs])].map(id=><option key={id} value={id}>{id.slice(0,12)}{id===referenceJob?' · same recording, time holdout':''}</option>)}</select></label>
    <label>Original test frame<input aria-label="Sensor map test frame" type="number" min="0" max="8191" step="1" value={frame} disabled={disabled||busy}
      onChange={e=>{clear();setFrame(Number(e.target.value));}}/></label>
    <button disabled={disabled||busy||!query||!Number.isInteger(frame)||frame<0||frame>8191} onClick={()=>void locate()}>Locate recorded scans · sensor map</button>
    {busy&&<p role="status">Rebuilding the reference without test-window scans, then searching position and heading… No robot action.</p>}
    {error&&<p role="alert">{error}</p>}
    {value&&<>
      <p role="status">{value.status.replaceAll('_',' ')} · {best?.supported_query_frames??0}/3 scans support the same transform</p>
      {pose&&<p>Historical sensor position candidate: X {pose[0].toFixed(2)} m · Y {pose[1].toFixed(2)} m · heading {(pose[2]*180/Math.PI).toFixed(1)}°. Reference session coordinates, not the photo room or current robot.</p>}
      <svg role="img" aria-label="Held-out sensor map and recorded scan position candidate" viewBox={`${x*100} ${-(y+h)*100} ${w*100} ${h*100}`}
        style={{width:'100%',maxWidth:640,aspectRatio:`${w}/${h}`,background:'#101923'}}>
        {value.reference_endpoint_cells.map((p,i)=><circle key={i} cx={p[0]*100} cy={-p[1]*100} r="1.3" fill="#687b89"/>)}
        {cloud.map((p,i)=><circle key={`query-${i}`} cx={p[0]*100} cy={-p[1]*100} r="2" fill="#59ead9"/>)}
        {pose&&<g transform={`translate(${pose[0]*100} ${-pose[1]*100}) rotate(${-pose[2]*180/Math.PI})`}><circle r="4" fill="#e4ab52"/><line x2="12" stroke="#e4ab52" strokeWidth="2"/></g>}
      </svg>
      <p>Gray: separate reference endpoints · cyan: three test scans · amber: historical sensor candidate. No free-space or collision clearance.</p>
      <p>Excluded {value.holdout.excluded_reference_frames.length} reference scans around the test window; {value.reference_retained_scan_count} retained. No direct test-scan reuse.</p>
      <details><summary>Quality and source boundaries</summary>
        <p>Recorded test frames {value.query_frames.join(', ')} · capped endpoint residual {best?(best.weighted_capped_mean_error_m*1000).toFixed(0):'—'} mm, not physical position accuracy.</p>
        <p>Alternative margin {value.alternative_margin_m===null?'unavailable':`${(value.alternative_margin_m*1000).toFixed(0)} mm`} · ambiguous candidates remain unaccepted.</p>
        <p>Declared timing and nominal mount unverified; odom-projected reference may drift. Same-recording holdout is not independent physical ground truth. Photo-room binding, live positioning and physical autonomy are not unlocked.</p>
      </details>
      {value.status==='SENSOR_MAP_GEOMETRIC_CANDIDATE'&&roomRevision&&<SensorPhotoLink api={api} sensor={value} roomRevision={roomRevision}
        disabled={disabled||busy} onBegin={onBegin} onEnd={onEnd}/>}
    </>}
  </section>;
}
