// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import {AutomaticMission} from './AutomaticMission';
import {AutomaticComparison} from './AutomaticComparison';

export interface SavedMap {map_id:string;revision:string;source_revision:string;reference_eligible:boolean;keyframes:number;}
export interface MapData {cells?:Cell[];corrected_cells?:Cell[];odom_cells?:Cell[];keyframes?:unknown[];reference_eligible:boolean;}
export type PhotoPolicy='disabled'|'align_only'|'correct_walls';
type Wall={id:string;a:number[];b:number[];thickness:number};
type SceneObject={id:string;kind:string;transform:{position_m:number[];rotation_rpy_deg?:number[]};shape:{dimensions_m:number[]}};
type StructureResidual={structure_index:number;nearest_wall_hypothesis:string;mean_uncapped_residual_m:number;support_sequences:number[]};
export interface PhotoAlignment {status:string;reason?:string;policy:PhotoPolicy;room_from_map:number[]|null;
  geometry_status?:string;applied_revision?:string|null;rollback_revision?:string;goal_revalidation_required:boolean;
  fit_error_m?:number;validation_before_m?:number;validation_after_m?:number;validation_basis:string;
  fit_sequences?:number[];validation_sequences?:number[];sensor_section?:{walls:Wall[];unknown:unknown[];height_m:number};
  validation_structures?:{a:number[];b:number[]}[];effective_objects?:SceneObject[];corrected_objects?:SceneObject[];
  residual_diagnosis?:{fit:StructureResidual[];held_out:StructureResidual[];unresolved_causes:string[]};}
type Cell=[number,number,string,number,number,number,string];
export interface AutomaticState {photo_alignment?:PhotoAlignment;map_id?:string;job:null|{job_id:string;source_job_id:string;state:string;epoch:number;elapsed_s:number;progress_sequence:number;
  replay_mode?:string;replay_timing?:{receipt_span_s:number;processing_elapsed_s:number;maximum_lateness_s:number;pending_event_bound:number}|null;
  map_id:string|null;error:string|null;result:null|MapData&{state:string;pose_candidate:number[]|null;counts:Record<string,number>;
  reasons:Record<string,number>;loop_status:string;timing_basis:string;trajectory:{corrected_pose:number[]}[];photo_alignment?:PhotoAlignment|null}};}

export function AutomaticDemo({api,available,projectId}:{api:TwinPulseApi;available:boolean;projectId:string}){
  const [sources,setSources]=useState<string[]>([]),[source,setSource]=useState('');
  const [replayMode,setReplayMode]=useState('as_fast');
  const [maps,setMaps]=useState<SavedMap[]>([]),[reference,setReference]=useState('');
  const [photoPolicy,setPhotoPolicy]=useState<PhotoPolicy>('correct_walls'),[savedPhoto,setSavedPhoto]=useState<PhotoAlignment|null>(null);
  const [savedId,setSavedId]=useState('');
  const [state,setState]=useState<AutomaticState>({job:null}),[saved,setSaved]=useState<MapData|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[seek,setSeek]=useState('-1');
  const token=useRef(0);const job=state.job;
  const active=job&&!['COMPLETED','FAILED','CANCELLED'].includes(job.state);
  async function bounded<T>(promise:Promise<T>):Promise<T>{
    let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([promise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('Automatic session request timed out. Refresh status; no automatic restart.')),15000);})]);}
    finally{clearTimeout(timer);}
  }
  useEffect(()=>{
    token.current++;setState({job:null});setSaved(null);setSavedPhoto(null);setError('');setSources([]);setMaps([]);setSource('');setReference('');setBusy(false);
    if(!available||typeof api.automaticMaps!=='function')return;
    const current=token.current;let alive=true;
    Promise.allSettled([bounded(api.physicalSessions()),bounded(api.automaticMaps())]).then(([s,m])=>{
      if(!alive||current!==token.current)return;
      if(s.status==='fulfilled'){setSources(s.value.sessions.map(v=>v.job_id));setSource(s.value.sessions[0]?.job_id??'');}
      if(m.status==='fulfilled')setMaps(m.value.maps);
      const failed=s.status==='rejected'?s:m.status==='rejected'?m:null;
      if(failed)setError(failed.reason instanceof Error?failed.reason.message:'Saved input unavailable.');
    });
    return()=>{alive=false;token.current++;};
  },[api,available,projectId]);
  useEffect(()=>{
    if(!active||!job||busy||error)return;
    const current=token.current;let alive=true;let polling=false;
    const timer=setInterval(()=>{
      if(polling)return;polling=true;
      bounded(api.automaticState()).then(value=>{if(alive&&current===token.current){setState(value);if(value.job?.error)setError(value.job.error);}})
        .catch(e=>{if(alive&&current===token.current)setError(e instanceof Error?e.message:'Status unavailable.');})
        .finally(()=>{polling=false;});
    },500);
    return()=>{alive=false;clearInterval(timer);};
  },[api,active,job?.job_id,busy,error]);
  useEffect(()=>{
    if(job?.state!=='COMPLETED')return;
    let alive=true;const current=token.current;
    bounded(api.automaticMaps()).then(value=>{if(alive&&current===token.current)setMaps(value.maps);})
      .catch(e=>{if(alive&&current===token.current)setError(e instanceof Error?e.message:'Saved map catalog unavailable.');});
    return()=>{alive=false;};
  },[api,job?.job_id,job?.state]);
  async function run(action:string){
    const current=++token.current;setBusy(true);setError('');setSaved(null);setSavedPhoto(null);
    if(action!=='refresh')setState(prev=>prev.job?{job:{...prev.job,result:null}}:prev);
    try{
      const next=action==='start'?await bounded(replayMode==='recorded_1x'?api.automaticStart(source,reference||null,photoPolicy,'recorded_1x'):api.automaticStart(source,reference||null,photoPolicy)):
        action==='refresh'?await bounded(api.automaticState()):
        await bounded(api.automaticControl(job!.job_id,action,action==='seek'?Number(seek):null));
      if(current===token.current){setState(next);if(next.job?.error)setError(next.job.error);}
    }catch(e){if(current===token.current)setError(e instanceof Error?e.message:'Automatic session failed.');}
    finally{if(current===token.current)setBusy(false);}
  }
  async function reopen(id:string){
    const current=++token.current;setBusy(true);setError('');setSaved(null);setSavedPhoto(null);
    try{const value=await bounded(api.automaticReopen(id));if(current===token.current){setSaved(value.map);setSavedPhoto(value.photo_alignment??null);setSavedId(id);}}
    catch(e){if(current===token.current)setError(e instanceof Error?e.message:'Saved map rejected.');}
    finally{if(current===token.current)setBusy(false);}
  }
  const result=job?.result,data=saved??result;
  const allCells=data?.corrected_cells??data?.cells??[];
  const cells=allCells.filter((_,i)=>i%Math.max(1,Math.ceil(allCells.length/2000))===0);
  const pose=saved?null:result?.pose_candidate;
  const photo=saved?savedPhoto:result?.photo_alignment;
  async function rollbackPhoto(){
    if(!photo?.applied_revision)return;
    const current=++token.current;setBusy(true);setError('');
    try{
      const value=await bounded(api.automaticRollbackPhoto(saved?savedId:job!.job_id,photo.applied_revision));
      if(current===token.current){if(saved)setSavedPhoto(value.photo_alignment??null);else setState(value);}
    }catch(e){if(current===token.current)setError(e instanceof Error?e.message:'Photo rollback failed.');}
    finally{if(current===token.current)setBusy(false);}
  }
  return <section className="native-quality" aria-label="Automatic sensor mapping">
    <h3>Automatic sensor mapping</h3>
    <p>Saved ROS replay · no robot connection. Start once; frames are processed automatically.</p>
    <div className="native-controls">
      <label>Recorded input<select aria-label="Automatic recorded input" disabled={!!active||busy} value={source} onChange={e=>setSource(e.target.value)}>
        <option value="">No saved input selected</option>{sources.map(id=><option key={id} value={id}>{id.slice(0,12)}</option>)}</select></label>
      <label>Mapping mode<select aria-label="Automatic reference map" value={reference} disabled={!!active||busy} onChange={e=>setReference(e.target.value)}>
        <option value="">New local map · no previous pose</option>{maps.filter(m=>m.reference_eligible).map(m=><option key={m.map_id} value={m.map_id}>Revisit {m.map_id.slice(0,12)}</option>)}</select></label>
      <label>Photo Twin policy<select aria-label="Automatic photo policy" value={photoPolicy} disabled={!!active||busy} onChange={e=>setPhotoPolicy(e.target.value as PhotoPolicy)}>
        <option value="correct_walls">Align + bounded wall corrections</option><option value="align_only">Align only · preserve geometry</option><option value="disabled">Sensor map only</option></select></label>
      <label>Replay speed<select aria-label="Automatic replay speed" value={replayMode} disabled={!!active||busy} onChange={e=>setReplayMode(e.target.value)}>
        <option value="as_fast">As processed · offline analysis</option><option value="recorded_1x">1× original receipt timing · load check</option></select></label>
      <button disabled={!available||busy||!!active||!source} onClick={()=>void run('start')}>Start automatic replay</button>
      <button disabled={!available||busy} onClick={()=>void run('refresh')}>Refresh session status</button>
    </div>
    <p role="status" aria-live="polite">{busy?'Processing request…':job?`${job.state} · ${job.elapsed_s.toFixed(1)} s · source sequence ${job.progress_sequence} · epoch ${job.epoch}`:'Ready to select recorded input'}</p>
    {job?.replay_timing&&<p>Historical 1× replay · source {job.replay_timing.receipt_span_s.toFixed(1)} s · processing {job.replay_timing.processing_elapsed_s.toFixed(1)} s · maximum late delivery {job.replay_timing.maximum_lateness_s.toFixed(3)} s. Not live acquisition or control timing.</p>}
    {job?.error&&!error&&<p role="alert">{job.error}</p>}
    {error&&<dialog open role="alertdialog" aria-label="Automatic mapping error"><p>{error}</p><button onClick={()=>setError('')}>Dismiss</button></dialog>}
    {active&&<div className="native-controls">
      <button disabled={busy||job?.state==='PAUSED'} onClick={()=>void run('pause')}>Pause · invalidate current pose</button>
      <button disabled={busy||job?.state!=='PAUSED'} onClick={()=>void run('resume')}>Resume causal replay</button>
      <button disabled={busy} onClick={()=>void run('cancel')}>Cancel session</button>
      <button disabled={busy} onClick={()=>void run('reposition')}>Moved by hand · invalidate</button>
      <details><summary>Replay diagnostics</summary><label>Original event sequence<input aria-label="Automatic seek sequence" type="number" min="-1" max="65536" value={seek} onChange={e=>setSeek(e.target.value)}/></label>
        <button disabled={busy||!Number.isInteger(Number(seek))} onClick={()=>void run('seek')}>Seek and pause · new epoch</button></details>
    </div>}
    {data&&<><svg role="img" aria-label="Automatic corrected sensor map" viewBox="-650 -650 1300 1300" style={{width:'100%',maxWidth:600,background:'#101923'}}>
      {cells.map((c,i)=><rect key={i} x={c[0]*50} y={-c[1]*50} width="5" height="5" fill={c[2]==='occupied'?'#59ead9':c[2]==='free'?'#294754':'#927947'}/>)}
      {result&&!saved&&<polyline points={result.trajectory.map(t=>`${t.corrected_pose[0]*50},${-t.corrected_pose[1]*50}`).join(' ')} fill="none" stroke="#e4ab52"/>}
      {pose&&<circle cx={pose[0]*50} cy={-pose[1]*50} r="7" fill="white"/>}
    </svg><p>{allCells.length} observed cells · occupied / observed free / conflicting unknown. Unobserved space remains unknown. Up to 2000 cells displayed.</p></>}
    {result&&<p>Localization: {result.state} · paired scans {result.counts.scans_paired??0} · derived analysis skipped {result.counts.derived_skipped??0} · loop: {result.loop_status}</p>}
    {photo&&<PhotoComparison photo={photo} historical={!!saved}/>}
    {photo?.applied_revision&&!active&&<button disabled={busy} onClick={()=>void rollbackPhoto()}>Roll back automatic wall correction</button>}
    {job?.map_id&&<button disabled={busy||!!active} onClick={()=>void reopen(job.map_id!)}>Reopen saved map · no retained pose</button>}
    {maps.length>0&&<label>Saved evidence map<select aria-label="Saved evidence map" value={savedId||''} disabled={busy||!!active} onChange={e=>{if(e.target.value)void reopen(e.target.value);}}>
      <option value="">Select historical map · no restored pose</option>{maps.map(m=><option key={m.map_id} value={m.map_id}>{m.map_id.slice(0,12)}</option>)}</select></label>}
    <AutomaticMission api={api} mapId={saved?savedId:job?.map_id??null} available={available}/>
    <AutomaticComparison api={api} available={available&&!active} projectId={projectId}/>
    <details><summary>Evidence and limits</summary><p>Scan-to-submap frontend, not globally optimized SLAM. Declared acquisition timing and nominal mounting remain unverified. Photo alignment is a geometric candidate, never calibrated motion authority. Corrections create derived versions; the original photo and recipe stay unchanged. Isaac stage rendering and autonomous execution are separate steps.</p>
      {result&&<pre>{JSON.stringify({counts:result.counts,reasons:result.reasons},null,2)}</pre>}
      {maps.map(m=><button key={m.map_id} disabled={busy||!!active} onClick={()=>void reopen(m.map_id)}>Inspect map {m.map_id.slice(0,12)}</button>)}
    </details>
  </section>;
}

function PhotoComparison({photo,historical}:{photo:PhotoAlignment;historical:boolean}){
  const pose=photo.room_from_map;
  const transform=(p:number[])=>pose?[pose[0]+Math.cos(pose[2])*p[0]-Math.sin(pose[2])*p[1],pose[1]+Math.sin(pose[2])*p[0]+Math.cos(pose[2])*p[1]]:p;
  const afterWalls=(photo.geometry_status==='ROLLED_BACK'?photo.effective_objects:photo.corrected_objects)?.filter(o=>o.kind==='wall').map(o=>{
    const d=o.shape.dimensions_m,p=o.transform.position_m,yaw=(o.transform.rotation_rpy_deg?.[2]??0)*Math.PI/180+(d[1]>d[0]?Math.PI/2:0);
    return {id:o.id,a:[p[0]-Math.cos(yaw)*Math.max(d[0],d[1])/2,p[1]-Math.sin(yaw)*Math.max(d[0],d[1])/2],
      b:[p[0]+Math.cos(yaw)*Math.max(d[0],d[1])/2,p[1]+Math.sin(yaw)*Math.max(d[0],d[1])/2]};
  });
  const line=(w:{a:number[];b:number[]},color:string,key:string)=> <line key={key} x1={w.a[0]*90} y1={-w.a[1]*90} x2={w.b[0]*90} y2={-w.b[1]*90} stroke={color} strokeWidth="3"/>;
  const endpoints=photo.sensor_section?.walls.flatMap(w=>[w.a,w.b])??[];
  const view=endpoints.length?`${Math.min(...endpoints.map(p=>p[0]*90))-30} ${Math.min(...endpoints.map(p=>-p[1]*90))-30} ${Math.max(...endpoints.map(p=>p[0]*90))-Math.min(...endpoints.map(p=>p[0]*90))+60} ${Math.max(...endpoints.map(p=>p[1]*90))-Math.min(...endpoints.map(p=>p[1]*90))+60}`:'-600 -600 1200 1200';
  return <article aria-label="Automatic photo Twin comparison">
    <h4>Photo Twin alignment · {photo.status}</h4>
    <p role="status">{photo.reason?.replaceAll('_',' ')}{photo.geometry_status?` · ${photo.geometry_status.replaceAll('_',' ')}`:''}</p>
    {historical&&<p>Historical evidence only · no current robot pose restored. Check the current revision before use.</p>}
    <p>Fit / held-out structure error: {photo.fit_error_m?.toFixed(3)??'—'} / {photo.validation_before_m?.toFixed(3)??'—'} m
      {photo.validation_after_m!==undefined?` → ${photo.validation_after_m.toFixed(3)} m after proposal`:''}. These are model residuals, not actual position accuracy.</p>
    {photo.sensor_section&&<><svg role="img" aria-label="Photo walls and held-out scan structures" viewBox={view} style={{width:'100%',maxWidth:600,background:'#101923'}}>
      {photo.sensor_section.walls.map(w=>line(w,'#879aaa',`old-${w.id}`))}
      {afterWalls?.map(w=>line(w,'#59ead9',`new-${w.id}`))}
      {pose&&photo.validation_structures?.map((w,i)=>line({a:transform(w.a),b:transform(w.b)},'#e4ab52',`obs-${i}`))}
    </svg><p>Gray: photo walls · cyan: bounded proposed/effective walls · amber: held-out scan structures after candidate transform.
      Sensor height {photo.sensor_section.height_m.toFixed(3)} m · {photo.sensor_section.unknown.length} furniture/lower structures remain unknown, not forced sensor surfaces.</p></>}
    <details><summary>Automatic alignment evidence</summary><p>No selected points or frames. Separate fit and held-out views share odom/TF; they are not independent ground truth. Height, material and scale are not changed.</p>
      <p>Fit sequences: {photo.fit_sequences?.join(', ')??'Insufficient views'}<br/>Held-out sequences: {photo.validation_sequences?.join(', ')??'Insufficient views'}</p>
      {photo.goal_revalidation_required&&<p>Scene changed: old goal/route evidence must be revalidated. Motion remains locked.</p>}
    </details>
    {photo.residual_diagnosis&&<details><summary>Why structures disagree</summary>
      <p>Nearest wall hypotheses under a diagnostic candidate, not an accepted robot pose. Residuals are uncapped distances; furniture is not used as a structural wall.</p>
      <div style={{overflowX:'auto'}}><table><thead><tr><th>Interval</th><th>Structure</th><th>Wall hypothesis</th><th>Residual</th><th>Supporting views</th></tr></thead><tbody>
        {(['fit','held_out'] as const).flatMap(interval=>photo.residual_diagnosis![interval].map(row=><tr key={`${interval}-${row.structure_index}`}>
          <td>{interval==='fit'?'Fit':'Held out'}</td><td>{row.structure_index}</td><td>{row.nearest_wall_hypothesis}</td>
          <td>{row.mean_uncapped_residual_m.toFixed(3)} m</td><td>{row.support_sequences.length}</td></tr>))}
      </tbody></table></div>
      <p>Unresolved causes: {photo.residual_diagnosis.unresolved_causes.map(c=>c.replaceAll('_',' ')).join(' · ')}. No geometry edit or motion authorization follows from this diagnosis.</p>
    </details>}
  </article>;
}
