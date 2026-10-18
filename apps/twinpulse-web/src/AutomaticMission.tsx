// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
export interface MissionState {adapter_available:boolean;job:null|{job_id:string;state:string;elapsed_s:number;error?:string;error_stage?:string;cleanup_error?:string;report_revision?:string;report_status?:string;report_error?:string;report_stage?:string;report_error_type?:string;report_errno?:number|null;isaac_display?:{status:string};
  cold_start?:{reason:string;error_stage?:string|null;error_type?:string|null};
  photo_correction?:{status:string;goal_revalidation:string;isaac_geometry_status:string;error_code?:string;error_type?:string};
  visual?:{pose_room:number[]|null;goal_room:number[]|null;route_room:number[][];scan_room:number[][];trajectory_room:number[][];revision:string}};}
type Readiness={room_revision:string;photo_status:string;adapter_available:boolean;current_pose_available:boolean;photo_correction_available?:boolean;next_action:string};
export function AutomaticMission({api,mapId,available}:{api:TwinPulseApi;mapId:string|null;available:boolean}){
  const [ready,setReady]=useState<Readiness|null>(null),[state,setState]=useState<MissionState>({adapter_available:false,job:null});
  const [x,setX]=useState('0'),[y,setY]=useState('0'),[mode,setMode]=useState('NAVIGATE_TWIN_GOAL');
  const [photoPolicy,setPhotoPolicy]=useState('align_only');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const epoch=useRef(0);
  const errorSignature=useRef('');
  const [preview,setPreview]=useState(''),[previewBusy,setPreviewBusy]=useState(false);const live=useRef<{id:string;active:boolean}|null>(null);
  const active=state.job&&!['MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'].includes(state.job.state);
  const reportPending=state.job?.report_status==='PENDING';
  useEffect(()=>{
    const job=state.job;
    // A storage failure can also be the primary mission failure. Show its
    // richer typed report diagnostic once; never hide a distinct primary cause.
    const reportIsPrimary=!!job?.report_error&&job.error===job.report_error
      &&job.error_stage===job.report_stage;
    const failures=[job?.error&&!reportIsPrimary?`${job.error_stage??'Mission'}: ${job.error}`:'',
      job?.error&&job.cold_start?.error_stage?`${job.cold_start.error_stage}: ${job.cold_start.reason} (${job.cold_start.error_type??'Error'})`:'',
      job?.cleanup_error?`Cleanup: ${job.cleanup_error}. Robot stop and shutdown require attention.`:'',
      job?.report_error?`${job.report_stage??'Report'}: ${job.report_error}${job.report_error_type?` (${job.report_error_type}${job.report_errno!=null?`, errno ${job.report_errno}`:''})`:''}. Saving is unconfirmed; motion will not restart automatically.`:'',
      job?.photo_correction?.error_code?`Isaac geometry: ${job.photo_correction.error_code} (${job.photo_correction.error_type??'Error'}). No automatic retry.`:''].filter(Boolean);
    const signature=failures.join(' · ');
    if(signature&&signature!==errorSignature.current){errorSignature.current=signature;setError(signature);}
  },[state.job]);
  live.current=state.job?{id:state.job.job_id,active:!!active}:null;
  useEffect(()=>{
    const halt=()=>{const current=live.current;if(current?.active)void api.automaticMissionStop(current.id,true)
      .catch(()=>setError('Force STOP could not be confirmed. The local watchdog remains responsible for stopping.'));};
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape')halt();};
    const hidden=()=>{if(document.hidden)halt();};
    window.addEventListener('blur',halt);window.addEventListener('keydown',key);document.addEventListener('visibilitychange',hidden);
    return()=>{halt();window.removeEventListener('blur',halt);window.removeEventListener('keydown',key);document.removeEventListener('visibilitychange',hidden);};
  },[api]);
  async function bounded<T>(promise:Promise<T>){let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([promise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('Mission request timed out. Stop remains available; no automatic retry.')),15000);})]);}
    finally{clearTimeout(timer);}}
  useEffect(()=>{const token=++epoch.current;setReady(null);setState({adapter_available:false,job:null});setError('');setBusy(false);setPreview('');setPreviewBusy(false);
    errorSignature.current='';
    setMode(mapId?'NAVIGATE_TWIN_GOAL':'SURVEY_THEN_NAVIGATE');
    setPhotoPolicy('align_only');
    if(available&&typeof api.automaticMissionReadiness==='function')bounded(api.automaticMissionReadiness(mapId))
      .then(v=>{if(epoch.current===token)setReady(v);}).catch(e=>{if(epoch.current===token)setError(String(e.message??e));});
    return()=>{epoch.current++;const current=live.current;
      if(current?.active)void api.automaticMissionStop(current.id,true).catch(()=>setError('Force STOP on evidence change was not confirmed.'));};},[api,mapId,available]);
  useEffect(()=>{if(!active&&!reportPending)return;let pending=false;const token=epoch.current,started=Date.now();
    const timer=setInterval(()=>{if(pending)return;
      if(!active&&Date.now()-started>15000){clearInterval(timer);setError('Mission ended, but saving its report is not confirmed. No automatic restart.');return;}
      pending=true;bounded(api.automaticMissionState()).then(v=>{
      if(epoch.current===token)setState(v);
    }).catch(e=>{if(epoch.current===token)setError(String(e.message??e));}).finally(()=>{pending=false;});},250);
    return()=>clearInterval(timer);},[api,active,reportPending]);
  async function start(){if(!ready)return;const token=epoch.current;setBusy(true);setError('');
    errorSignature.current='';
    // Isaac display is optional and never a source of motion authorization.
    if(typeof api.acquireLease==='function')void api.acquireLease().catch(()=>setPreview('Live Isaac view unavailable. Mission diagnostics remain on this screen.'));
    try{
      // A preceding correction may have advanced the room revision. Refresh
      // evidence on the next explicit Start, never restart the mission itself.
      const current=await bounded(api.automaticMissionReadiness(mapId));
      if(token!==epoch.current)return;
      setReady(current);
      if(!current.adapter_available)throw Error(current.next_action);
      if(mode==='SURVEY_THEN_NAVIGATE'&&photoPolicy==='correct_walls'&&!current.photo_correction_available)
        throw Error('Same-Start correction is unavailable for the current adapter. No mission was started.');
      const goal={mode,xy:[Number(x),Number(y)],room_revision:current.room_revision,duration_s:45};
      const v=await bounded(mode==='SURVEY_THEN_NAVIGATE'&&photoPolicy==='correct_walls'
        ?api.automaticMissionStart(mapId,goal,'correct_walls'):api.automaticMissionStart(mapId,goal));
      if(token===epoch.current)setState(v);
      else if(v.job)void api.automaticMissionStop(v.job.job_id,true).catch(()=>setError('Late mission start stop was not confirmed.'));
    }catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'Mission failed');}
    finally{if(token===epoch.current)setBusy(false);}}
  async function stop(force:boolean){if(!state.job)return;const token=epoch.current;
    try{const v=await bounded(api.automaticMissionStop(state.job.job_id,force));if(token===epoch.current)setState(v);}
    catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'Stop request failed');}}
  const visual=state.job?.visual;
  async function preview3d(){if(!state.job?.report_revision||previewBusy)return;const token=epoch.current;setPreviewBusy(true);setPreview('Waiting for Isaac visual readiness…');
    try{await bounded(api.acquireLease());const readyDeadline=Date.now()+15000;
      while(token===epoch.current){
        const engine=await bounded(api.productState());
        if(engine.engine_readiness?.automatic_mission_visual_v1?.ready)break;
        const code=engine.engine_readiness?.automatic_mission_visual_v1?.code??'runtime_snapshot_missing';
        if(Date.now()>=readyDeadline)throw Error(`Isaac visual readiness: ${code}. No command was submitted; no automatic retry.`);
        setPreview(`Waiting for Isaac visual readiness: ${code}…`);
        await new Promise(resolve=>setTimeout(resolve,250));
      }
      if(token!==epoch.current)return;
      setPreview('Submitting saved visual report…');
      const value=await bounded(api.automaticMissionPreview(state.job.job_id,state.job.report_revision,crypto.randomUUID()));
      const deadline=Date.now()+30000;let operation=value;
      while(token===epoch.current&&['accepted','queued','claimed','running'].includes(operation.status)){
        setPreview(`Isaac visual operation: ${operation.status}…`);
        if(Date.now()>=deadline)throw Error('Isaac visual operation timed out. Check the engine result; no automatic retry.');
        await new Promise(resolve=>setTimeout(resolve,500));
        if(token!==epoch.current)return;
        const state=await bounded(api.productState());
        const current=state.operations.find(o=>o.command_id===value.command_id);
        if(current)operation=current;
      }
      if(token===epoch.current){
        if(operation.status!=='succeeded')throw Error(`Isaac visual operation ${operation.status}. Check engine details.`);
        setPreview('Isaac saved visual is ready. This is not physical execution.');
      }}
    catch(e){if(token===epoch.current){setPreview('');setError(e instanceof Error?e.message:'Isaac visual request failed');}}
    finally{if(token===epoch.current)setPreviewBusy(false);}}
  return <section aria-label="Observed goal mission" className="native-quality automatic-mission"><h3>Observed goal mission</h3>
    <p role="status">{state.job?`${state.job.state} · PC runtime ${state.job.elapsed_s.toFixed(1)} s`:ready?ready.next_action:'Checking mission preparation…'}</p>
    {state.job&&<p>PC runtime is wall time, not the adapter-clock mission budget. Synthetic replay can run slower than its sensor timeline; this does not extend the 45 s mission limit.</p>}
    <div className="native-controls"><label>Mission mode<select value={mode} disabled={!!active} onChange={e=>setMode(e.target.value)}>
      <option value="SURVEY_THEN_NAVIGATE">Survey → photo alignment → Twin goal</option>
      <option value="NAVIGATE_TWIN_GOAL" disabled={!mapId}>Navigate Twin goal</option><option value="SURVEY_LOCAL">Bounded local survey</option></select></label>
      <label>Goal X (m)<input type="number" value={x} disabled={!!active} onChange={e=>setX(e.target.value)}/></label>
      <label>Goal Y (m)<input type="number" value={y} disabled={!!active} onChange={e=>setY(e.target.value)}/></label>
      {mode==='SURVEY_THEN_NAVIGATE'&&<label>Photo correction<select value={photoPolicy} disabled={!!active||busy} onChange={e=>setPhotoPolicy(e.target.value)}>
        <option value="align_only">Align only · preserve walls</option>
        <option value="correct_walls" disabled={!ready?.photo_correction_available}>Correct validated walls · derived revision</option></select></label>}
      <button disabled={!ready?.adapter_available||busy||!!active||reportPending||(mode==='NAVIGATE_TWIN_GOAL'&&ready.photo_status!=='ALIGNMENT_CANDIDATE')} onClick={()=>void start()}>Start observed mission · maximum 45 s</button>
      <button disabled={!active} onClick={()=>void stop(false)}>Stop after current command</button>
      <button disabled={!active} onClick={()=>void stop(true)}>Force STOP</button></div>
    <button disabled={!state.job?.report_revision||!state.job?.visual?.pose_room||!!active||previewBusy} onClick={()=>void preview3d()}>Show saved mission in Isaac 3D</button>
    {reportPending&&!active&&<p role="status">Motion ended · saving the immutable result…</p>}
    {preview&&<p role="status">{preview}</p>}
    {state.job?.photo_correction&&<p role="status">Photo correction: {state.job.photo_correction.status} · Goal: {state.job.photo_correction.goal_revalidation} · Isaac geometry: {state.job.photo_correction.isaac_geometry_status}</p>}
    {!!active&&<p role="status">Isaac live display: {state.job?.isaac_display?.status??'Waiting for an owned matching room in Isaac. The 2D diagnostics remain available.'}</p>}
    <p>Autonomous limits: 0.03 m/s · 0.20 rad/s · segment 50 ms. Unknown space is blocked. No per-command approval. Saved results do not restore a current robot pose.</p>
    {mode==='SURVEY_THEN_NAVIGATE'&&<p>One start surveys within 0.5 m of its observed starting pose, fits separated photo-wall views while idle, then rechecks current sensors before goal navigation. The entire sequence shares the 45 s budget; insufficient or ambiguous evidence stops without moving toward the Twin goal.</p>}
    {ready&&<p>Photo evidence: {ready.photo_status} · {ready.adapter_available?'Server-registered adapter; admission is rechecked':'No qualified live adapter configured. Motion is unavailable.'}</p>}
    {visual&&!visual.pose_room&&<p role="status">Current room position unavailable. Any retained trajectory is historical, not a current observation.</p>}
    {visual&&<svg role="img" aria-label="Mission route and current scan" viewBox="-500 -500 1000 1000" style={{width:'100%',maxWidth:550}}>
      {visual.scan_room.map((p,i)=><circle key={i} cx={p[0]*90} cy={-p[1]*90} r="2" fill="#59ead9"/>)}
      <polyline points={visual.route_room.map(p=>`${p[0]*90},${-p[1]*90}`).join(' ')} stroke="#e4ab52" fill="none"/>
      {visual.pose_room&&<circle cx={visual.pose_room[0]*90} cy={-visual.pose_room[1]*90} r="7" fill="white"/>}
      {visual.goal_room&&<circle cx={visual.goal_room[0]*90} cy={-visual.goal_room[1]*90} r="6" stroke="#e4ab52" fill="none"/>}</svg>}
    {error&&<dialog open role="alertdialog" aria-label="Observed mission error"><p>{error}</p><button onClick={()=>setError('')}>Dismiss</button></dialog>}
  </section>;
}
