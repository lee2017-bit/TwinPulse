// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {SensorMapResult} from './SensorMapLocalization';

export interface LinkPair {endpoint_index:number;anchor_id:string;role:'fit'|'validation'}
export interface PhotoLinkContext {revision:string;anchors:{id:string;object_id:string;corner:number;xy_m:number[]}[];outline:{bounds_m:number[];segments:number[][][]}}
export interface PhotoLinkResult {revision:string;status:string;fit_rms_m:number;fit_max_residual_m:number;validation_max_residual_m:number;
  sensor_pose_room_candidate:number[]|null;diagnostic_sensor_pose_room:number[];outline:{bounds_m:number[];segments:number[][][]};
  overlays:{points:number[][]}[];pairs:(LinkPair&{projected_room_xy_m:number[];room_xy_m:number[];residual_m:number})[];
  alignment_verified:false;motion_authorized:false;physical_demo_ready:false}

export function SensorPhotoLink({api,sensor,roomRevision,disabled,onBegin,onEnd}:{api:TwinPulseApi;sensor:SensorMapResult;roomRevision:string;disabled:boolean;onBegin:()=>void;onEnd:()=>void}){
  const [context,setContext]=useState<PhotoLinkContext|null>(null),[pairs,setPairs]=useState<LinkPair[]>([]);
  const [index,setIndex]=useState(0),[anchor,setAnchor]=useState(''),[role,setRole]=useState<'fit'|'validation'>('fit');
  const [result,setResult]=useState<PhotoLinkResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [goal,setGoal]=useState(['0','0']),[mapped,setMapped]=useState<number[]|null>(null);const request=useRef(0);
  useEffect(()=>{request.current++;setContext(null);setPairs([]);setResult(null);setMapped(null);setError('');setBusy(false);
    return ()=>{request.current++;};},[sensor.revision,roomRevision]);
  function clear(){request.current++;setResult(null);setMapped(null);setError('');}
  async function run(action:'load'|'link'|'goal'){
    const token=++request.current;setBusy(true);setError('');setMapped(null);onBegin();
    if(action!=='goal')setResult(null);
    try{
      if(action==='load'){
        const value=await api.photoLinkContext(roomRevision,sensor.revision);
        if(token===request.current){setContext(value);setPairs([]);setAnchor(value.anchors[0]?.id??'');}
      }else if(action==='link'&&context){
        const value=await api.linkSensorPhoto(roomRevision,sensor.revision,context.revision,pairs);
        if(token===request.current)setResult(value);
      }else if(action==='goal'&&result){
        if(goal.some(v=>!v.trim()||!Number.isFinite(Number(v))))throw Error('Enter finite goal coordinates.');
        const value=await api.photoLinkGoal(roomRevision,result.revision,goal.map(Number));
        if(token===request.current)setMapped(value.query_odom_goal_candidate_m);
      }
    }catch(e){if(token===request.current){setResult(null);setError(e instanceof Error?e.message:'Photo link failed. No coordinates retained.');}}
    finally{if(token===request.current){setBusy(false);onEnd();}}
  }
  const locked=disabled||busy,points=sensor.reference_endpoint_cells,b=sensor.bounds_m;
  const fit=pairs.filter(p=>p.role==='fit').length,checks=pairs.length-fit;
  const selected=context?.anchors.find(a=>a.id===anchor),pose=result?.sensor_pose_room_candidate;
  const ab=context?.outline.bounds_m??[-1,1,-1,1],ap=context?.anchors.map(a=>a.xy_m)??[];
  const anchorBounds=[Math.min(ab[0],...ap.map(p=>p[0]))-.08,Math.max(ab[1],...ap.map(p=>p[0]))+.08,
    Math.min(ab[2],...ap.map(p=>p[1]))-.08,Math.max(ab[3],...ap.map(p=>p[1]))+.08];
  const cloud=result?.overlays.flatMap(o=>o.points)??[],rb=result?.outline.bounds_m??[-1,1,-1,1];
  const resultBounds=[Math.min(rb[0],...cloud.map(p=>p[0]))-.1,Math.max(rb[1],...cloud.map(p=>p[0]))+.1,
    Math.min(rb[2],...cloud.map(p=>p[1]))-.1,Math.max(rb[3],...cloud.map(p=>p[1]))+.1];
  const view=(bounds:number[])=>`${bounds[0]*100} ${-bounds[3]*100} ${(bounds[1]-bounds[0])*100} ${(bounds[3]-bounds[2])*100}`;
  return <section aria-label="Sensor map to photo room link">
    <h4>Link sensor map to photo room</h4>
    <p>Choose corresponding observed points and authored wall corners. This is a visual hypothesis, not a survey. No scaling, mirror correction or robot action.</p>
    <button disabled={locked||!roomRevision} onClick={()=>void run('load')}>Load photo wall anchors</button>
    {busy&&<p role="status">Checking sources and coordinate link… No movement or room edit.</p>}
    {error&&<p role="alert">{error}</p>}
    {context&&<>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,260px),1fr))',gap:16}}>
        <div><p>Observed reference map · select a recorded endpoint</p>
          <svg role="img" aria-label="Select observed endpoint" viewBox={view(b)} style={{width:'100%',background:'#101923'}}>
            {points.map((p,i)=><circle key={i} cx={p[0]*100} cy={-p[1]*100} r={index===i?4:1.3} fill={index===i?'#e4ab52':'#687b89'}
              onClick={()=>{if(!locked){clear();setIndex(i);}}}><title>Endpoint {i}</title></circle>)}
          </svg>
        </div>
        <div><p>Photo room XY · select an approximate wall corner</p>
          <svg role="img" aria-label="Select photo wall corner" viewBox={view(anchorBounds)} style={{width:'100%',background:'#101923'}}>
            {context.outline.segments.map((s,i)=><line key={i} x1={s[0][0]*100} y1={-s[0][1]*100} x2={s[1][0]*100} y2={-s[1][1]*100} stroke="#687b89"/>)}
            {context.anchors.map(a=><circle key={a.id} cx={a.xy_m[0]*100} cy={-a.xy_m[1]*100} r="4" fill={a.id===anchor?'#e4ab52':'#59ead9'}
              onClick={()=>{if(!locked){clear();setAnchor(a.id);}}}><title>{a.id}</title></circle>)}
          </svg>
        </div>
      </div>
      <label>Endpoint index<input aria-label="Photo link endpoint index" type="number" min="0" max={points.length-1} step="1" value={index} disabled={locked}
        onChange={e=>{clear();setIndex(Number(e.target.value));}}/></label>
      <label>Wall corner<select aria-label="Photo link wall anchor" value={anchor} disabled={locked} onChange={e=>{clear();setAnchor(e.target.value);}}>
        {context.anchors.map(a=><option key={a.id} value={a.id}>{a.id}</option>)}</select></label>
      <label>Point role<select aria-label="Photo link pair role" value={role} disabled={locked} onChange={e=>setRole(e.target.value as 'fit'|'validation')}>
        <option value="fit">Fit transform</option><option value="validation">Check only · not fitted</option></select></label>
      <button disabled={locked||pairs.length>=16||!Number.isInteger(index)||!points[index]||!selected||pairs.some(p=>p.endpoint_index===index||p.anchor_id===anchor)}
        onClick={()=>{clear();setPairs([...pairs,{endpoint_index:index,anchor_id:anchor,role}]);}}>Add correspondence</button>
      <p>{fit} fit points · {checks} held-out check points. At least 3 noncollinear fit points and 1 check point are required.</p>
      <ol>{pairs.map((p,i)=><li key={i}>Endpoint {p.endpoint_index} → {p.anchor_id} · {p.role} <button disabled={locked} onClick={()=>{clear();setPairs(pairs.filter((_,j)=>j!==i));}}>Remove pair {i+1}</button></li>)}</ol>
      <button disabled={locked||fit<3||checks<1} onClick={()=>void run('link')}>Check coordinate link · no movement</button>
    </>}
    {result&&<>
      <p role="status">{result.status.replaceAll('_',' ')} · fit RMS {(result.fit_rms_m*1000).toFixed(0)} mm · held-out maximum {(result.validation_max_residual_m*1000).toFixed(0)} mm</p>
      <p>Residuals measure only your selected correspondences. Physical pose uncertainty remains unknown.</p>
      <svg role="img" aria-label="Sensor scans linked to approximate photo room" viewBox={view(resultBounds)} style={{width:'100%',maxWidth:600,background:'#101923'}}>
        {result.outline.segments.map((s,i)=><line key={i} x1={s[0][0]*100} y1={-s[0][1]*100} x2={s[1][0]*100} y2={-s[1][1]*100} stroke="#687b89"/>)}
        {cloud.map((p,i)=><circle key={i} cx={p[0]*100} cy={-p[1]*100} r="1.6" fill="#59ead9"/>)}
        {result.pairs.map((p,i)=><line key={`residual-${i}`} x1={p.projected_room_xy_m[0]*100} y1={-p.projected_room_xy_m[1]*100}
          x2={p.room_xy_m[0]*100} y2={-p.room_xy_m[1]*100} stroke={p.role==='validation'?'#ee6358':'#e4ab52'} strokeWidth="2"/>)}
        {pose&&<g transform={`translate(${pose[0]*100} ${-pose[1]*100}) rotate(${-pose[2]*180/Math.PI})`}><circle r="5" fill="#e4ab52"/><line x2="14" stroke="#e4ab52"/></g>}
      </svg>
      <p>Three selected historical scans in cyan; outside-room returns are retained. Gray photo boxes are unmeasured appearance, not collision geometry.</p>
      <ul>{result.pairs.map((p,i)=><li key={i}>{p.anchor_id} · {p.role}: {(p.residual_m*1000).toFixed(0)} mm</li>)}</ul>
      {pose&&<>
        <p>Historical sensor in photo-room coordinates: X {pose[0].toFixed(2)} m · Y {pose[1].toFixed(2)} m. Not the current robot pose.</p>
        {['X','Y'].map((axis,i)=><label key={axis}>Room goal {axis}<input aria-label={`Photo link goal ${axis}`} type="number" value={goal[i]} disabled={locked}
          onChange={e=>{setMapped(null);setGoal(goal.map((v,j)=>j===i?e.target.value:v));}}/></label>)}
        <button disabled={locked} onClick={()=>void run('goal')}>Preview linked goal coordinates</button>
        {mapped&&<p>Historical query odom goal: {mapped[0].toFixed(2)}, {mapped[1].toFixed(2)} m · no mission submitted.</p>}
      </>}
      <p>Photo geometry unchanged. Correspondence identity, metric alignment, live positioning and collision clearance remain unverified.</p>
    </>}
  </section>;
}
