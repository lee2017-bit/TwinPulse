// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {ApiError,type TwinPulseApi} from './api';
import type {SceneEditPreview,SceneEditTransaction} from './types';
import type {ObstacleCorrectionPreview,ObstacleFeedbackState,ObstacleObservation} from './obstacle-types';

const terminal=new Set(['COMMITTED','ROLLED_BACK','CANCELLED_BEFORE_DISPATCH','ENGINE_STATE_UNKNOWN']);
// These Apply admission errors are raised before the transaction is staged or
// its engine worker starts. Do not classify generic 409/transport errors here.
const predispatchRejections=new Set(['scene_edit_invalid','scene_edit_engine_not_ready','scene_sensor_apply_rejected']);
const finiteXY=(point:unknown):point is number[]=>Array.isArray(point)&&point.length>=2&&
  typeof point[0]==='number'&&Number.isFinite(point[0])&&typeof point[1]==='number'&&Number.isFinite(point[1]);
const saved=(value:SceneEditTransaction)=>value.state==='COMMITTED'&&value.durable_committed&&value.engine_acknowledged===true;
const failure=(error:unknown)=>error instanceof ApiError&&/^[A-Za-z0-9_]{1,100}$/.test(error.code)?
  `Obstacle feedback request was not confirmed (${error.code}).`:'Obstacle feedback request was not confirmed. Check the saved result before submitting again.';
const selectionKey=(project:string)=>`twinpulse.obstacle.selection.${project}`;

function ObstaclePlot({observation}:{observation:ObstacleObservation}){
  // Marker sizes are schematic, not inferred map-cell dimensions or accuracy.
  const points=observation.points.filter(finiteXY).slice(0,2000);
  // EvidenceGrid.rows already returns cell centres in room metres. Never
  // multiply those coordinates by the cell size a second time.
  const cells=observation.cells.filter(finiteXY).slice(0,2000);
  const scale=typeof observation.cell_size_m==='number'&&Number.isFinite(observation.cell_size_m)&&observation.cell_size_m>0?observation.cell_size_m:null;
  const all=[...points,...cells];
  const xs=all.map(point=>point[0]),ys=all.map(point=>point[1]);
  const minX=Math.min(0,...xs),maxX=Math.max(1,...xs),minY=Math.min(0,...ys),maxY=Math.max(1,...ys);
  const pixelsPerMetre=Math.min(296/Math.max(.01,maxX-minX),196/Math.max(.01,maxY-minY));
  const x=(value:number)=>160+(value-(minX+maxX)/2)*pixelsPerMetre;
  const y=(value:number)=>110-(value-(minY+maxY)/2)*pixelsPerMetre;
  const colors:Record<string,string>={occupied:'#c35547',free:'#5c9475',unknown:'#9097a3'};
  return <figure aria-label="Obstacle observation XY schematic">
    <svg role="img" aria-label="Imported XY points and occupied free unknown markers" viewBox="0 0 320 220" style={{width:'100%',maxWidth:480}}>
      <rect width="320" height="220" fill="#f2f4f7"/>
      {cells.map((cell,index)=><rect key={`cell-${index}`} x={x(cell[0])-2} y={y(cell[1])-2} width="4" height="4" fill={colors[cell[2]]??colors.unknown}/>)}
      {points.map((point,index)=><circle key={`point-${index}`} cx={x(point[0])} cy={y(point[1])} r="1.5" fill="#294c78"/>)}
      <text x="5" y="217" fontSize="9">X → · Y ↑</text>
    </svg>
    <figcaption>XY schematic · blue points, red occupied, green free, grey unknown. Marker size is not a map-cell dimension.
      {scale?` Supplied grid cell size: ${scale} m; this does not establish sensor accuracy.`:' Points and cell centres use the supplied room-metre coordinates.'}
      {' Blank, unobserved space remains unknown, never certified free.'}
      {(observation.points.length>2000||observation.cells.length>2000)&&' Display limited to 2,000 points and 2,000 cells.'}</figcaption>
  </figure>;
}

export function ObstacleFeedback({api,revision,stateSha,enabled,fresh=true}:{api:TwinPulseApi;revision:string;stateSha:string|null;enabled:boolean;fresh?:boolean}){
  const [state,setState]=useState<ObstacleFeedbackState|null>(null),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false);
  const [stateBinding,setStateBinding]=useState<object|null>(null);
  const [error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
  const [selection,setSelection]=useState({project:'',observation:'',target:''});
  const [file,setFile]=useState<File|null>(null),[pose,setPose]=useState(['','','']),[height,setHeight]=useState('');
  const [manual,setManual]=useState(false),[delta,setDelta]=useState(['','']);
  const [preview,setPreview]=useState<{value:ObstacleCorrectionPreview;epoch:number}|null>(null);
  const [undo,setUndo]=useState<{value:SceneEditPreview;epoch:number}|null>(null);
  const [transaction,setTransaction]=useState<SceneEditTransaction|null>(null),[unconfirmed,setUnconfirmed]=useState(false);
  const mounted=useRef(false),pending=useRef<object|null>(null),trackedOperation=useRef<string|null>(null);
  const transactionEpoch=useRef(0);
  const pollingWindow=useRef({id:'',until:0});
  const binding=useMemo(()=>({api,context:api.context,revision,stateSha,enabled}),[api,api.context,revision,stateSha,enabled]);
  const owner=useRef(binding);
  // Suspended/abandoned renders must not revoke the handlers of the scene
  // still committed on screen. Publish ownership only during commit.
  useLayoutEffect(()=>{owner.current=binding;},[binding]);
  const current=(requested=binding)=>mounted.current&&owner.current===requested&&api.context===requested.context;
  const admission=useRef({fresh,enabled});useLayoutEffect(()=>{admission.current={fresh,enabled};},[fresh,enabled]);
  const admitted=()=>current()&&admission.current.fresh&&admission.current.enabled;
  const available=typeof api.obstacleFeedbackState==='function';
  const identityCurrent=enabled&&stateBinding===binding&&!!stateSha&&state?.context.current_scene_revision===revision&&state.context.current_state_sha256===stateSha;
  const contextCurrent=fresh&&identityCurrent;
  const observation=state?.observations.find(row=>row.id===selection.observation);
  const target=state?.targets.find(row=>row.id===selection.target);
  const form=JSON.stringify([selection.observation,observation?.sha256,selection.target,manual,...delta]);
  const formOwner=useRef({binding,form,epoch:0});
  const formBinding=useMemo(()=>({binding,form,epoch:formOwner.current.epoch+1}),[binding,form]);
  useLayoutEffect(()=>{formOwner.current=formBinding;},[formBinding]);
  const formEpoch=formBinding.epoch;
  useEffect(()=>{setPreview(null);setUndo(null);},[formEpoch]);
  useLayoutEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);

  const publish=(value:ObstacleFeedbackState)=>{
    if(value.schema_version!=='obstacle-feedback-1.0'||value.physical_authority!==false||!value.context||
      !['project_id','current_scene_revision','current_state_sha256'].every(key=>typeof value.context[key as keyof typeof value.context]==='string')||
      !Array.isArray(value.observations)||!Array.isArray(value.targets)||
      value.observations.some(row=>!row||typeof row.id!=='string'||typeof row.sha256!=='string'||typeof row.provenance!=='string'||typeof row.received_at_utc!=='string'||!Array.isArray(row.points)||!Array.isArray(row.cells))||
      value.targets.some(row=>!row||typeof row.id!=='string'||typeof row.label!=='string'||!Array.isArray(row.center_m)||!row.center_m.every(Number.isFinite)))throw new Error('OBSTACLE_STATE_INVALID');
    setState(value);setStateBinding(binding);
    setSelection(previous=>{
      let stored:{observation?:string;target?:string}={};
      if(previous.project!==value.context.project_id){try{const parsed:unknown=JSON.parse(sessionStorage.getItem(selectionKey(value.context.project_id))??'{}');
        if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed)){const candidate=parsed as Record<string,unknown>;
          stored={observation:typeof candidate.observation==='string'?candidate.observation:undefined,target:typeof candidate.target==='string'?candidate.target:undefined};}
      }catch{/* Selection is optional, never authority. */}}
      const requested=previous.project===value.context.project_id?previous:stored;
      const latest=[...value.observations].sort((a,b)=>b.received_at_utc.localeCompare(a.received_at_utc))[0];
      return {project:value.context.project_id,observation:value.observations.some(row=>row.id===requested.observation)?requested.observation!:latest?.id??'',
        target:value.targets.some(row=>row.id===requested.target)?requested.target!:''};
    });
  };
  const observeTransaction=async(requested=binding)=>{
    if(typeof api.sceneEditTransaction!=='function')return;
    const value=await api.sceneEditTransaction();if(!current(requested))return;
    if(trackedOperation.current&&value?.operation_id!==trackedOperation.current){
      setNotice('The submitted correction is not confirmed in the saved transaction. No Apply is repeated.');return;
    }
    setTransaction(value);
    if(value&&terminal.has(value.state))setUnconfirmed(!saved(value)&&!['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(value.state));
  };
  useEffect(()=>{
    trackedOperation.current=null;++transactionEpoch.current;pollingWindow.current={id:'',until:0};setUnconfirmed(false);
    setFile(null);setPose(['','','']);setHeight('');setManual(false);setDelta(['','']);
  },[api,api.context]);
  useEffect(()=>{
    let active=true;const requested=binding;
    pending.current=null;setBusy(false);setState(null);setStateBinding(null);setPreview(null);setUndo(null);setTransaction(null);setError(null);setNotice(null);
    if(!enabled||!available||!stateSha){setLoading(false);return()=>{active=false;};}
    setLoading(true);
    void Promise.all([api.obstacleFeedbackState(),typeof api.sceneEditTransaction==='function'?api.sceneEditTransaction():Promise.resolve(null)])
      .then(([value,tx])=>{if(!active||!current(requested))return;publish(value);
        if(!trackedOperation.current||tx?.operation_id===trackedOperation.current){setTransaction(tx);if(tx&&terminal.has(tx.state))setUnconfirmed(!saved(tx)&&!['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(tx.state));}})
      .catch(caught=>{if(active&&current(requested))setError(failure(caught));})
      .finally(()=>{if(active&&current(requested))setLoading(false);});
    return()=>{active=false;};
  },[binding,available]);
  useEffect(()=>{
    if(!selection.project)return;
    try{sessionStorage.setItem(selectionKey(selection.project),JSON.stringify({observation:selection.observation,target:selection.target}));}catch{/* Storage is optional. */}
  },[selection]);
  useEffect(()=>{
    const id=transaction?.operation_id;
    if(!id||!enabled||typeof api.sceneEditTransaction!=='function'||
      terminal.has(transaction.state)&&(transaction.state!=='COMMITTED'||transaction.current_frame))return;
    if(pollingWindow.current.id!==id)pollingWindow.current={id,until:Date.now()+135000};
    let active=true;const requested=binding,epoch=transactionEpoch.current;let timer:ReturnType<typeof setTimeout>|undefined;
    const read=async()=>{
      if(!active||!current(requested)||epoch!==transactionEpoch.current||Date.now()>=pollingWindow.current.until)return;
      try{const value=await api.sceneEditTransaction();if(active&&current(requested)&&epoch===transactionEpoch.current&&value?.operation_id===id){setTransaction(value);
        if(terminal.has(value.state))setUnconfirmed(!saved(value)&&!['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(value.state));}}
      catch{if(active&&current(requested)&&epoch===transactionEpoch.current)setNotice('Saved transaction check delayed. No Apply or Undo was repeated.');}
      if(active&&current(requested)&&epoch===transactionEpoch.current&&Date.now()<pollingWindow.current.until)timer=setTimeout(()=>void read(),750);
    };
    timer=setTimeout(()=>void read(),750);return()=>{active=false;clearTimeout(timer);};
  },[api,binding,enabled,transaction?.operation_id,transaction?.state,transaction?.current_frame]);
  const perform=async(task:()=>Promise<void>,readOnly=false)=>{
    if(pending.current||!current()||!enabled||!readOnly&&!admitted())return;
    const requested=binding,request={};pending.current=request;setBusy(true);setError(null);setNotice(null);
    try{await task();}catch(caught){if(current(requested))setError(failure(caught));}
    finally{if(pending.current===request){pending.current=null;if(current(requested))setBusy(false);}}
  };
  const select=(change:Partial<typeof selection>)=>setSelection(value=>({...value,...change}));
  const importScan=()=>void perform(async()=>{
    if(!file||!contextCurrent||unconfirmed)return;
    if(file.size>2*1024*1024){setError('Choose a sensor JSON file up to 2 MiB. No import request was sent.');return;}
    const requested=binding;let value:unknown,text:string;
    try{text=await file.text();value=JSON.parse(text);}
    catch{if(current(requested))setError('The local file could not be read as JSON. Review the sensor format below; no import request was sent.');return;}
    if(!current(requested))return;
    if(!value||typeof value!=='object'||Array.isArray(value)){setError('Sensor JSON must be an observation object or a connection-log wrapper. No import request was sent.');return;}
    if(!admitted()){setNotice('State observation changed while reading the file. No import request was sent; wait for a fresh workflow and import explicitly.');return;}
    // Validate the envelope locally without reserializing the signed source.
    // JSON number spellings (for example 0.0) matter to the server's source hash.
    const result=await api.importObstacleObservation({json_text:text},revision,stateSha!,pose.map(Number),Number(height));
    if(current(requested)){publish(result);setPreview(null);setUndo(null);setNotice('Observation imported locally. Choose its saved ID below; provenance and furniture correspondence remain unverified. The Twin is unchanged.');}
  });
  const previewCorrection=()=>void perform(async()=>{
    if(!observation||!target||!contextCurrent||unconfirmed||!admitted())return;
    const requested=binding,epoch=formEpoch;
    const value=await api.previewObstacleCorrection(observation.id,observation.sha256,revision,stateSha!,target.id,manual?delta.map(Number):null);
    if(!value||!['preview','HELD'].includes(value.status)||typeof value.reason!=='string')throw new Error('OBSTACLE_PREVIEW_INVALID');
    if(current(requested)&&formOwner.current.epoch===epoch&&value.observation_id===observation.id&&value.observation_sha256===observation.sha256){setPreview({value,epoch});setUndo(null);}
  });
  const submitTransaction=async(operationId:string,submit:()=>Promise<SceneEditTransaction>)=>{
    if(!admitted())return;
    const requested=binding;trackedOperation.current=operationId;++transactionEpoch.current;setTransaction(null);setUnconfirmed(true);setPreview(null);setUndo(null);
    try{const value=await submit();if(!current(requested))return;
      if(value.operation_id!==operationId)throw new Error('OBSTACLE_TRANSACTION_ID_MISMATCH');
      setTransaction(value);if(terminal.has(value.state))setUnconfirmed(!saved(value)&&!['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(value.state));
    }catch(caught){if(current(requested)){
      if(caught instanceof ApiError&&predispatchRejections.has(caught.code)){
        trackedOperation.current=null;setUnconfirmed(false);
        setNotice(caught.code==='scene_edit_engine_not_ready'
          ?'Preview was rejected before dispatch; use "View current Twin" to display the saved scene in Isaac and wait until it is ready and idle. Then refresh obstacle feedback and prepare a new preview. No correction was sent to the engine.'
          :'Preview was rejected before dispatch; refresh the saved scene and prepare a new preview. No correction was sent to the engine.');
      }else setNotice('Correction outcome is unconfirmed. Check the saved transaction; no Apply or Undo will be repeated.');
    }throw caught;}
  };
  const chosenPreview=preview?.epoch===formEpoch?preview.value:null;
  const chosenUndo=undo?.epoch===formEpoch?undo.value:null;
  const canApply=!!chosenPreview&&chosenPreview.status==='preview'&&chosenPreview.apply_version==='scene-edit-apply-2.0'&&
    !!chosenPreview.preview_digest&&!!chosenPreview.sensor_binding&&typeof chosenPreview.operation?.operation_id==='string'&&
    finiteXY(chosenPreview.translation_xy_m)&&chosenPreview.translation_xy_m.length===2&&contextCurrent&&!busy&&!unconfirmed;
  // The generic preview endpoint has no apply_version field. The explicit
  // startSceneEditTransaction request selects the 2.0 transaction protocol.
  const canUndo=!!chosenUndo&&contextCurrent&&!busy&&!unconfirmed&&chosenUndo.operation?.mode==='undo'&&
    chosenUndo.parent_revision===revision&&chosenUndo.parent_state_sha256===stateSha&&
    chosenUndo.operation.parent_revision===revision&&chosenUndo.operation.parent_state_sha256===stateSha&&
    typeof chosenUndo.operation.operation_id==='string'&&!!chosenUndo.operation.operation_id.trim()&&
    typeof chosenUndo.preview_digest==='string'&&/^[a-f0-9]{64}$/.test(chosenUndo.preview_digest);
  const importCoordinates=pose.every((value,index)=>value.trim()&&Number.isFinite(Number(value))&&Math.abs(Number(value))<=(index===2?Math.PI:10))&&
    height.trim()&&Number.isFinite(Number(height))&&Number(height)>=.02&&Number(height)<=3;
  const deltaValid=!manual||delta.every(value=>value.trim()&&Number.isFinite(Number(value))&&Math.abs(Number(value))<=10)&&delta.some(value=>Math.abs(Number(value))>=1e-6);
  return <section aria-label="Obstacle observation feedback" className="chat-question">
    <strong>Refine an estimated Twin with obstacle observations</strong>
    <p>The initial Twin is an editable estimate. A sensor plane does not identify furniture or prove room alignment. No navigation, robot motion or paid model request is authorized here.</p>
    {!available?<p>Local obstacle import is unavailable in this backend. An estimated draft can still be created without a scan.</p>:<>
      <p>Choose a robot → check this PC → check connection → download its observation log, or import a local sensor JSON file below. A scan is not required to create a draft.</p>
      <button type="button" disabled={!enabled||busy||loading} onClick={()=>void perform(async()=>{const requested=binding;const value=await api.obstacleFeedbackState();if(current(requested))publish(value);await observeTransaction(requested);},true)}>Refresh obstacle feedback · read only</button>
      {loading&&<p role="status">Reading saved obstacle observations…</p>}
      {!enabled&&<p role="status">Obstacle feedback waits for the current operation to finish. Nothing is imported or applied.</p>}
      {!fresh&&<p role="status" aria-label="Obstacle feedback availability">Scene observation is stale · retained proposals are locked views only. Import, Preview, Apply and Undo wait for fresh matching conversation, workflow and product state. Nothing is repeated automatically.</p>}
      {state&&!identityCurrent&&<p role="status">Current scene binding changed. Refresh before importing or preparing a correction.</p>}
      <fieldset disabled={!contextCurrent||busy||loading||unconfirmed}><legend>Import a local observation</legend>
        <label>Sensor observation JSON (up to 2 MiB)<input aria-label="Sensor observation JSON" type="file" accept=".json,application/json" onChange={event=>{setFile(event.target.files?.[0]??null);event.target.value='';}}/></label>
        {file&&<p>{file.name} · local sensor evidence, not a photo/model upload</p>}
        <p>Enter an estimated sensor pose (x, y, yaw in radians) and scan height for the last snapshot. These are user-specified estimates, not calibrated measurements. Earlier snapshots stay in the source log; they are not merged at this pose.</p>
        {['X','Y','yaw'].map((axis,index)=><label key={axis}>Estimated sensor {axis}{axis==='yaw'?' (rad)':' (m)'}<input aria-label={`Estimated sensor ${axis}`} type="number" min={index===2?-Math.PI:-10} max={index===2?Math.PI:10} step="any" value={pose[index]} onChange={event=>setPose(values=>values.map((value,i)=>i===index?event.target.value:value))}/></label>)}
        <label>Estimated scan height (m)<input aria-label="Estimated scan height" type="number" min=".02" max="3" step="any" value={height} onChange={event=>setHeight(event.target.value)}/></label>
        <button type="button" disabled={!file||!importCoordinates} onClick={importScan}>Import obstacle observation · local only</button>
      </fieldset>
      <details><summary>Sensor JSON format</summary><p>A downloaded connection log may wrap this record in obstacle_observation. Provenance is declared, not independently verified. Use finite ranges in metres; null is an unavailable return.</p><pre>{JSON.stringify({schema_version:'obstacle-observation-1.0',provenance:'IMPORTED_SENSOR',scans:[{stamp_ns:1,frame_id:'laser',angle_min_rad:0,angle_increment_rad:.1,range_min_m:.05,range_max_m:4,ranges_m:[1,null,2]}]},null,2)}</pre></details>
      {state?.observations.length===0&&<p>No saved obstacle observation. Import a same-room scan when available; draft generation remains available without it.</p>}
      <label>Obstacle observation<select aria-label="Obstacle observation" disabled={busy||!contextCurrent} value={selection.observation} onChange={event=>select({observation:event.target.value})}><option value="">Choose an observation</option>{state?.observations.map(row=><option key={row.id} value={row.id}>{row.id} · {row.provenance} · {row.received_at_utc}</option>)}</select></label>
      {observation&&<><p>Declared provenance: {observation.provenance} · {observation.scan_count} snapshots saved · association unassigned. Occupied {observation.occupied_count} · free {observation.free_count} · unknown {observation.unknown_count}.</p>
        {Array.isArray(observation.sensor_pose_m)&&observation.sensor_pose_m.every(Number.isFinite)&&<p>Saved user-estimated sensor pose (x m, y m, yaw rad): {observation.sensor_pose_m.map(value=>value.toFixed(3)).join(', ')} · estimated scan height {observation.scan_height_m} m. Not calibrated or independently aligned.</p>}
        <ObstaclePlot observation={observation}/></>}
      <fieldset disabled={!contextCurrent||busy||unconfirmed}><legend>Associate one saved object explicitly</legend>
        <label>Correction target<select aria-label="Correction target" value={selection.target} onChange={event=>select({target:event.target.value})}><option value="">Choose the object yourself</option>{state?.targets.map(row=><option key={row.id} value={row.id}>{row.label} · {row.id}</option>)}</select></label>
        {target&&<p>Current estimated centre: {target.center_m.map(value=>value.toFixed(3)).join(', ')} m. Selection is not a proven sensor-to-furniture match.</p>}
        <label><input type="checkbox" checked={manual} onChange={event=>setManual(event.target.checked)}/>Specify an estimated XY translation instead of automatic fit</label>
        {manual&&delta.map((value,index)=><label key={index}>Estimated delta {index===0?'X':'Y'} (m)<input aria-label={`Estimated delta ${index===0?'X':'Y'}`} type="number" min="-10" max="10" step="any" value={value} onChange={event=>setDelta(values=>values.map((prior,i)=>i===index?event.target.value:prior))}/></label>)}
        <button type="button" disabled={!observation||!target||!deltaValid} onClick={previewCorrection}>Preview obstacle correction</button>
      </fieldset>
      {chosenPreview&&<section aria-label="Obstacle correction proposal"><h4>{chosenPreview.status==='HELD'?'Correction held · not applied':'Estimated correction proposal · review before Apply'}</h4>
        <p>{chosenPreview.reason.slice(0,240)}</p><small>Execution {chosenPreview.execution_id} · observation {chosenPreview.observation_id}</small>
        {finiteXY(chosenPreview.translation_xy_m)&&<p>Estimated translation: X {chosenPreview.translation_xy_m[0].toFixed(3)} m · Y {chosenPreview.translation_xy_m[1].toFixed(3)} m. No rotation, identity or physical accuracy is confirmed.</p>}
        {chosenPreview.fit&&<details><summary>Bounded fit diagnostics</summary><pre>{JSON.stringify(chosenPreview.fit,null,2).slice(0,6000)}</pre></details>}
        <button type="button" disabled={!canApply} onClick={()=>void perform(async()=>{if(canApply)await submitTransaction(chosenPreview.operation!.operation_id as string,()=>api.applyObstacleCorrection(chosenPreview));})}>Apply reviewed obstacle correction</button>
        <button type="button" disabled={busy} onClick={()=>setPreview(null)}>Discard obstacle proposal</button>
      </section>}
      <button type="button" disabled={!contextCurrent||busy||unconfirmed} onClick={()=>void perform(async()=>{if(unconfirmed||!contextCurrent)return;const requested=binding,epoch=formEpoch;const value=await api.previewSceneEdit('obstacle_undo_'+crypto.randomUUID(),'undo',null,null);
        if(current(requested)&&formOwner.current.epoch===epoch){setUndo({value,epoch});setPreview(null);}})}>Preview Undo last scene edit</button>
      {chosenUndo&&<section aria-label="Obstacle feedback Undo review"><p>Undo reverses the latest scene edit, not the imported sensor log. Review this separate proposal before Apply.</p>
        <button type="button" disabled={!canUndo} onClick={()=>void perform(async()=>{if(canUndo)await submitTransaction(chosenUndo.operation.operation_id as string,()=>api.startSceneEditTransaction(chosenUndo));})}>Apply reviewed Undo</button>
        <button type="button" disabled={busy} onClick={()=>setUndo(null)}>Discard Undo proposal</button></section>}
      {(transaction||unconfirmed)&&<section aria-label="Obstacle correction saved transaction">
        {transaction?<><p>{saved(transaction)?'Engine ACK received · disk COMMITTED':`Scene transaction: ${transaction.state} · no correction success claimed`}</p>
          <p>{transaction.current_frame&&transaction.historical!==true?'Current frame confirmed for this transaction.':'Current frame not confirmed here. Saved geometry and current 3D display are separate checks.'}</p>
          <small>Operation {transaction.operation_id} · execution {transaction.execution_id??'not recorded'}</small>{transaction.error&&<p>{transaction.error.slice(0,240)}</p>}</>:<p>Correction result is unconfirmed. Do not Apply again.</p>}
        <button type="button" disabled={!enabled||busy} onClick={()=>void perform(()=>observeTransaction(),true)}>Check saved correction result · read only</button>
      </section>}
      {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
    </>}
  </section>;
}
