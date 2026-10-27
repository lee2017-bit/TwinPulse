// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import {ApiError,fileToBase64,type TwinPulseApi} from './api';
import {downloadBlob} from './download-blob';
import {isEnvironmentSource,type EnvironmentAction,type EnvironmentProposal,type EnvironmentState} from './environment-types';
import type {SceneEditPreview,SceneEditTransaction,WorkflowState} from './types';
import {EnvironmentObstacles} from './EnvironmentObstacles';
import {EnvironmentAlignment} from './EnvironmentAlignment';
import {EnvironmentSurvey} from './EnvironmentSurvey';

const describe=(error:unknown)=>error instanceof Error?error.message:String(error);
export function EnvironmentImport({api,initialFile,close,onReady,onSubmitted,enabled=true,autoApply=false,undoLastEdit}:{
  api:TwinPulseApi;initialFile?:File|null;close:()=>void;onReady:(workflow:WorkflowState)=>void|Promise<void>;
  onSubmitted?:()=>void;enabled?:boolean;autoApply?:boolean;  // Twin-edit auto-apply: a successful preview is applied without the Apply click
  undoLastEdit?:()=>void;  // the chat's Undo (same message and conditions as its Twin update card), given after a committed edit
}){
  const [state,setState]=useState<EnvironmentState|null>(null),[error,setError]=useState<string|null>(null);
  const [file,setFile]=useState<File|null>(initialFile??null),[units,setUnits]=useState<''|'m'|'cm'|'mm'>('');
  const [dirty,setDirty]=useState(!!initialFile),[busy,setBusy]=useState(false),[unknown,setUnknown]=useState(false);
  const [exported,setExported]=useState<string|null>(null);
  const [selected,setSelected]=useState(''),[translation,setTranslation]=useState(['0','0']);
  const [moveRequest,setMoveRequest]=useState(''),[proposal,setProposal]=useState<EnvironmentProposal|null>(null);
  const [reviewedJob,setReviewedJob]=useState<string|null>(null);
  const proposalOwner=useRef<{requestId:string;jobId:string|null;revision:string;objectId:string;reviewRequested?:boolean}|null>(null);
  const discardProposal=()=>{proposalOwner.current=null;setProposal(null);setReviewedJob(null);};
  const [preview,setPreview]=useState<SceneEditPreview|null>(null),[transaction,setTransaction]=useState<SceneEditTransaction|null>(null);
  const [pendingEdit,setPendingEdit]=useState<{operationId:string;revision:string}|null>(null);
  const [alignmentOpen,setAlignmentOpen]=useState(false);
  const [surveyOpen,setSurveyOpen]=useState(false);
  const editOwner=useRef<typeof pendingEdit>(null),editRead=useRef(0);
  const trackEdit=(value:typeof pendingEdit)=>{editOwner.current=value;editRead.current++;setPendingEdit(value);};
  const [checking,setChecking]=useState(false);
  const context=api.context,owner=useRef({api,context}),mounted=useRef(true),lock=useRef(false),sequence=useRef(0);
  owner.current={api,context};
  const current=()=>mounted.current&&owner.current.api===api&&owner.current.context===context&&api.context===context;
  const receiveProposal=(next:EnvironmentState)=>{
    const pending=proposalOwner.current,result=next.proposal;
    if(!pending)return;
    if(next.scene_revision!==pending.revision){discardProposal();setPreview(null);return;}
    if(!result||result.request_id!==pending.requestId||pending.jobId&&result.job_id!==pending.jobId)return;
    if(result.source_revision!==pending.revision){discardProposal();setPreview(null);setError('Scene changed. Request a new move suggestion.');return;}
    pending.jobId=result.job_id;setProposal(result);
    if(result.status==='ready'&&result.preview&&pending.reviewRequested){
      if(result.preview.parent_revision!==pending.revision){discardProposal();setError('Move suggestion has no current preview. Request a new suggestion.');return;}
      setPreview(result.preview);
    }
    if(result.status==='failed')setError(result.error??'Move suggestion failed. Nothing was applied.');
  };
  const refresh=async()=>{const reading=++sequence.current,next=await api.environment();
    if(current()&&reading===sequence.current){setState(next);receiveProposal(next);}return next;};
  // "Add N suggested objects": one candidate at a time through the same photo_candidate_preview -> Apply -> ACK/commit path as one Review.
  const batch=useRef<{jobId:string;ids:string[];step:'next'|'previewing'|'previewed'|'failed';revision?:string;operationId?:string;failure?:string;added:number}|null>(null);
  const [batchStatus,setBatchStatus]=useState<string|null>(null),[batching,setBatching]=useState(false);
  const stopBatch=(message:string|null)=>{batch.current=null;setBatching(false);setBatchStatus(message);};
  useEffect(()=>{mounted.current=true;stopBatch(null);setState(null);setPreview(null);setTransaction(null);trackEdit(null);discardProposal();setMoveRequest('');setUnknown(false);setSelected('');setError(null);setBusy(false);
    let active=true;void refresh().catch(e=>{if(active&&current())setError(describe(e));});
    return()=>{active=false;mounted.current=false;proposalOwner.current=null;sequence.current++;};},[api,context]);
  useEffect(()=>{if(initialFile){setFile(initialFile);setUnits('');setDirty(true);setPreview(null);discardProposal();}},[initialFile]);
  useEffect(()=>{if(preview&&state?.scene_revision!==preview.parent_revision)setPreview(null);},[state?.scene_revision,preview]);
  const modelRunning=proposal?.status==='running';
  const photoRunning=state?.photo_proposal?.status==='running';
  const polling=modelRunning||photoRunning||state?.status==='inspecting'||!!state?.operation&&['accepted','running'].includes(state.operation.status);
  useEffect(()=>{if(!polling)return;let reading=false;
    const timer=setInterval(()=>{if(reading||lock.current||!current())return;reading=true;
      void refresh().catch(e=>{if(current())setError(describe(e));}).finally(()=>{reading=false;});},1000);
    return()=>clearInterval(timer);},[polling,api,context]);
  const perform=async(work:()=>Promise<void>)=>{if(lock.current)return;lock.current=true;setBusy(true);setError(null);
    try{await work();}catch(e){if(current())setError(describe(e));}
    finally{lock.current=false;if(current())setBusy(false);}};
  const act=async(body:EnvironmentAction)=>{
    if(!current())throw new ApiError('context_changed','Project changed before submission.');
    sequence.current++;
    try{const next=await api.environmentAction(body);if(current()){sequence.current++;setState(next);receiveProposal(next);}return next;}
    catch(e){if(current()&&(!(e instanceof ApiError)||e.code==='delivery_unknown'))setUnknown(true);throw e;}
  };
  const choose=(value:File|null)=>{setError(null);setPreview(null);discardProposal();
    if(value&&(!isEnvironmentSource(value)||value.size>10*1024*1024)){setError('Choose one self-contained USD, USDA or USDC file up to 10 MiB.');return;}
    setFile(value);setUnits('');setDirty(!!value);};
  const inspect=()=>void perform(async()=>{if(!file)return;
    if(!isEnvironmentSource(file)||file.size>10*1024*1024)throw new Error('Choose one self-contained USD, USDA or USDC file up to 10 MiB.');
    const next=await act({action:'inspect',request_id:crypto.randomUUID(),attachment:{name:file.name,bytes_base64:await fileToBase64(file)},units:units||null});
    if(current()){setDirty(false);setPreview(null);if(next.status!=='failed')onSubmitted?.();}});
  const adopt=()=>void perform(async()=>{if(!state?.job_id||dirty)return;
    const next=await act({action:'adopt',request_id:crypto.randomUUID(),job_id:state.job_id});
    if(current()&&next.workflow)await onReady(next.workflow);});
  const build=()=>void perform(async()=>{const next=await act({action:'build',request_id:crypto.randomUUID()});
    if(current()){const workflow=next.workflow??await api.workflow();if(current())await onReady(workflow);}});
  const confirmEdit=async(pending:{operationId:string;revision:string})=>{
    if(!current())return;
    const reading=++editRead.current;
    const owns=()=>current()&&reading===editRead.current&&editOwner.current?.operationId===pending.operationId&&editOwner.current.revision===pending.revision;
    const next=await api.sceneEditTransaction();if(!owns())return;setTransaction(next);
    if(!next||next.operation_id!==pending.operationId)return;
    if(['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH','ENGINE_STATE_UNKNOWN'].includes(next.state)){
      setError(next.error??`Edit ended in ${next.state}.`);if(next.state==='ENGINE_STATE_UNKNOWN')setUnknown(true);trackEdit(null);setPreview(null);return;}
    if(next.state==='COMMITTED'&&next.durable_committed&&next.engine_acknowledged&&next.current_frame&&next.result_revision===pending.revision){
      const workflow=await api.workflow();if(!owns())return;
      if((workflow.site_draft?.revision??workflow.draft?.revision)!==pending.revision)return;
      await onReady(workflow);if(!owns())return;
      // Keep edit controls locked until the refreshed environment snapshot
      // carries this committed revision. Immediate Undo must not send the old
      // parent revision while the ACK/commit label is already visible.
      const refreshed=await refresh();if(!owns())return;
      if(refreshed.scene_revision!==pending.revision)return;
      setPreview(null);setUnknown(false);trackEdit(null);
    }
  };
  useEffect(()=>{if(!pendingEdit)return;let active=true,reading=false;const started=Date.now();
    setChecking(true);
    const timer=setInterval(()=>{if(!active||reading||!current())return;
      if(Date.now()-started>135000){clearInterval(timer);setChecking(false);setError('Edit outcome is unconfirmed. Check its saved result; do not Apply again.');return;}
      reading=true;void confirmEdit(pendingEdit).catch(e=>{if(active&&current())setError(describe(e));}).finally(()=>{reading=false;});},1000);
    return()=>{active=false;clearInterval(timer);setChecking(false);};},[pendingEdit,api,context]);
  const applyPreview=()=>void perform(async()=>{if(!preview)return;
    const operationId=preview.operation.operation_id;
    if(typeof operationId!=='string')throw new Error('Preview has no operation identity. Create a new preview.');
    discardProposal();
    const pending={operationId,revision:preview.result_revision};trackEdit(pending);setTransaction(null);
    try{const accepted=await api.applyEnvironmentEdit(preview.operation,preview.preview_digest);
      if(current()&&accepted.operation_id!==operationId){setUnknown(true);throw new ApiError('delivery_unknown','Apply returned a different operation. Check the saved transaction before another action.');}}
    catch(e){if(current()&&(!(e instanceof ApiError)||e.code==='delivery_unknown')){setUnknown(true);setError('Apply delivery is unconfirmed. Checking this saved operation; no automatic Apply retry.');}
      else{if(current())trackEdit(null);throw e;}}
    if(current())await confirmEdit(pending);
  });
  const editable=state?.status==='imported'&&!!state.scene_revision;
  const blocked=busy||unknown||!!pendingEdit||!enabled;
  const autoApplied=useRef<string|null>(null);
  useEffect(()=>{  // Twin-edit auto-apply (chat setting): the same transaction path as the Apply button, once per preview
    const operationId=preview?.operation?.operation_id;
    // A batch never applies by itself: with the setting off each of its previews waits for the user's Apply.
    if(!autoApply||!preview||typeof operationId!=='string'||blocked||modelRunning||autoApplied.current===operationId)return;
    autoApplied.current=operationId;applyPreview();
  });
  useEffect(()=>{const run=batch.current;if(!run)return;
    const stopped=(reason:string)=>stopBatch(`Stopped at ${run.ids[0]} after ${run.added} added: ${reason}`);
    if(run.step==='failed'){stopped(run.failure??'refused');return;}
    if(run.step==='previewing')return;
    if(run.step==='previewed'){
      if(pendingEdit||busy||lock.current)return;  // Apply, ACK and commit still in flight
      if(preview&&!error&&!unknown)return;  // waiting for its Apply (the user's click, or Twin-edit auto-apply)
      // Counted only when this step's own operation committed with its result revision (not any other scene change).
      const mine=transaction?.operation_id===run.operationId,committed=mine&&transaction?.state==='COMMITTED'&&transaction.durable_committed&&
        transaction.engine_acknowledged&&transaction.result_revision===state?.scene_revision&&state?.scene_revision!==run.revision;
      if(preview||unknown||!committed){stopped(error??(mine?'the edit was not committed':'not applied (preview cancelled)'));return;}
      run.ids.shift();run.added++;run.step='next';
      if(!run.ids.length){stopBatch(`Added ${run.added} suggested object${run.added===1?'':'s'}. Positions are estimates; the robot LiDAR corrects small offsets.`);return;}
    }
    if(blocked||lock.current||modelRunning||photoRunning||preview)return;
    const proposal=state?.photo_proposal,c=proposal?.job_id===run.jobId?proposal.candidates.find(row=>row.id===run.ids[0]):undefined,s=c?.suggested;
    // Recomputed by the server for the current scene: a suggestion that is gone or no longer batch-safe stops the batch.
    if(!c||!s||!c.batch_addable||!c.overlay_kind||!state?.scene_revision){stopped(c?.suggestion_reason??'no current suggestion');return;}
    const revision=state.scene_revision;run.step='previewing';run.revision=revision;
    void perform(async()=>{try{
      const next=await act({action:'photo_candidate_preview',request_id:crypto.randomUUID(),candidate_ref:{job_id:run.jobId,candidate_id:c.id},duplicate_reviewed:true,
        expected_scene_revision:revision,obstacle:{kind:c.overlay_kind!,label:c.label,position_xy_m:[s.position_m[0],s.position_m[1]],dimensions_m:s.dimensions_m,
          yaw_deg:s.yaw_deg,uncertainty_m:s.uncertainty_m}});
      const operationId=next.preview?.operation.operation_id;
      if(!next.preview||typeof operationId!=='string')throw new Error('No preview for this suggestion.');
      if(batch.current===run&&current()){run.operationId=operationId;run.step='previewed';setPreview(next.preview);
        setBatchStatus(`${c.id}: ${run.added+1} of ${run.added+run.ids.length} · ${autoApply?'applying automatically (Twin-edit auto-apply)':'check the preview, then Apply space edit to continue or Cancel to stop'}.`);}
    }catch(e){if(batch.current===run){run.step='failed';run.failure=describe(e);}throw e;}});
  });
  const startBatch=(ids:string[])=>{const job=state?.photo_proposal?.job_id;if(!job||!ids.length||batch.current)return;
    batch.current={jobId:job,ids:[...ids],step:'next',added:0};setBatching(true);setError(null);setPreview(null);discardProposal();
    setBatchStatus(`Adding ${ids.length} suggested object${ids.length===1?'':'s'} one at a time…`);};
  return <section className="library-workspace" aria-label="Import space" style={{margin:'8px 16px',padding:'12px',border:'1px solid #cbd7df',borderRadius:12,maxHeight:'45vh',overflow:'auto',background:'#fff',color:'#172836'}}>
    <header style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><strong>Import space · USD</strong><button type="button" onClick={close}>Close import space</button></header>
    <p>Keep the source geometry as your environment. Inspect locally, import, then show the Twin.</p>
    {error&&<p role="alert">{error}</p>}{state?.error&&state.error!==error&&<p role="alert">{state.error}</p>}
    {unknown&&<p role="alert">Delivery unknown. Check saved results before another action. No action is repeated automatically.</p>}
    {!enabled&&<p role="status">Finish the current scene action before importing or editing.</p>}
    <button type="button" disabled={busy} onClick={()=>void perform(async()=>{await refresh();if(pendingEdit)await confirmEdit(pendingEdit);})}>Check saved import</button>
    {state?.status==='empty'&&typeof api.environmentExportUsda==='function'&&<p className="library-field"><button type="button" disabled={busy} aria-label="Export generated Twin as USD" onClick={()=>void perform(async()=>{
      const {blob,name}=await api.environmentExportUsda();downloadBlob(blob,name);setExported(name);})}>Export generated Twin as USD</button>
      <small>{exported?`Saved ${exported}. Start a New chat, attach it and import it as the robot workspace (approximate boxes, estimated dimensions).`:'A Twin generated from a photo or text can be exported as approximate boxes and imported in a new chat as the robot workspace (routes, LiDAR candidates, Twin edits).'}</small></p>}
    <fieldset disabled={blocked||modelRunning||state?.status==='inspecting'}><legend>Space source</legend>
      <label className="library-field">USD file<input aria-label="Space USD file" type="file" accept=".usd,.usda,.usdc" onChange={e=>{choose(e.target.files?.[0]??null);e.target.value='';}}/></label>
      {file&&<p>{file.name} · {dirty?'selected locally':'inspection submitted'} <button type="button" onClick={()=>choose(null)}>Remove space file</button></p>}
      <label className="library-field">Source units<select aria-label="Space source units" value={units} onChange={e=>{setUnits(e.target.value as typeof units);setDirty(true);setPreview(null);discardProposal();}}>
        <option value="">Unknown / use authored units</option><option value="m">Meters (m)</option><option value="cm">Centimeters (cm)</option><option value="mm">Millimeters (mm)</option></select></label>
      <small>{units?'User-selected units are uncalibrated. Measured scale is not verified.':'Missing authored unit metadata requires an explicit choice. No measured scale is assumed.'}</small>
      <button type="button" disabled={!file} onClick={inspect}>Inspect space</button>
    </fieldset>
    {state&&<p role="status">{state.status==='inspecting'?'Inspecting space locally…':state.status==='ready'?'Inspection ready · review units and objects before import.':state.status==='imported'?'Space imported · saved environment.':'Import status: '+state.status}</p>}
    {state?.source_name&&<p>{state.source_name} · {state.objects.length} objects · Units: {state.units_basis==='selected_for_sim'?'user-selected':state.units_basis??'not confirmed'}</p>}
    {!!state?.objects.length&&<details><summary>Objects and size</summary>
      <small>Scene-axis bounds (X × Y × Z), not measured object dimensions. Photos are not automatically merged into this space.</small>
      <ul style={{paddingInlineStart:20,overflowWrap:'anywhere'}}>{state.objects.map(object=><li key={object.id}>
        {object.label} · {object.category} · {object.dimensions_m?object.dimensions_m.map(v=>v.toFixed(3)).join(' × ')+' m':'size unavailable'}
      </li>)}</ul>
    </details>}
    {state?.metadata_basis==='current_review_not_disk_validation'&&<small>Current reviewed scene. Actions recheck saved data.</small>}
    {state?.job_id&&<small>Inspection job: {state.job_id}</small>}
    {state?.units_basis==='selected_for_sim'&&<small>Saved units are user-selected and uncalibrated. Measured scale is not verified.</small>}
    {state?.status==='ready'&&<><p>Import requires an empty new project. Start New chat to keep an existing Twin.</p><button type="button" disabled={blocked||dirty||!state.job_id} onClick={adopt}>Import space</button></>}
    {editable&&<><button type="button" disabled={blocked||modelRunning} onClick={build}>Show Twin</button><small>Show Twin queues a Build. Confirm the engine ACK and current frame in the Twin pane.</small>
      <details onToggle={event=>setAlignmentOpen(event.currentTarget.open)}><summary>Scan alignment</summary>
        {alignmentOpen&&<EnvironmentAlignment key={context} api={api} revision={state.scene_revision!} disabled={blocked||modelRunning||photoRunning}/>}</details>
      <details onToggle={e=>setSurveyOpen(e.currentTarget.open)}><summary>Collected survey · missing obstacles</summary>
        {surveyOpen&&<EnvironmentSurvey api={api} revision={state.scene_revision!} photo={state.photo_proposal} disabled={blocked||modelRunning||photoRunning||batching}
          onInvalidate={()=>setPreview(null)} onPreview={v=>{discardProposal();setPreview(v);}}/>}</details>
      {state.operation&&<p role="status">Build command: {state.operation.status} · {state.operation.receipt?'receipt received':'ACK pending'}</p>}
      <EnvironmentObstacles key={context} state={state} disabled={blocked||modelRunning||photoRunning||batching}
        addAll={startBatch} batch={{running:batching,status:batchStatus,autoApply}}
        invalidate={()=>{setPreview(null);discardProposal();}}
        analyze={photo=>void perform(async()=>{
          if(!/\.(jpe?g|png)$/i.test(photo.name)||photo.size>5*1024*1024)throw new Error('Choose a JPEG or PNG photo up to 5 MiB for analysis.');
          const pendingRevision=state.scene_revision!;const encoded=await fileToBase64(photo);setPreview(null);discardProposal();
          await act({action:'photo_analyze',request_id:crypto.randomUUID(),photo:{name:photo.name,bytes_base64:encoded},consent:true,expected_scene_revision:pendingRevision});
        })}
        cancelPhoto={id=>void perform(async()=>{await act({action:'photo_cancel',request_id:crypto.randomUUID(),job_id:id});setPreview(null);})}
        preview={(obstacle,photo,candidate,replaceId)=>void perform(async()=>{
          // A photo-recognized candidate carries its own analyzed photo as evidence; the optional reference photo only matters for a manual box.
          if(!candidate&&photo&&(!/\.(jpe?g|png|webp)$/i.test(photo.name)||photo.size>5*1024*1024))throw new Error('Choose a JPEG, PNG or WebP photo up to 5 MiB.');
          discardProposal();const next=await act(candidate?{action:'photo_candidate_preview',request_id:crypto.randomUUID(),obstacle,
            candidate_ref:candidate,duplicate_reviewed:true,expected_scene_revision:state.scene_revision!,...(replaceId?{replace_object_id:replaceId}:{})}:
            {action:'add_overlay_preview',request_id:crypto.randomUUID(),obstacle,
            photo:photo?{name:photo.name,bytes_base64:await fileToBase64(photo)}:null,expected_scene_revision:state.scene_revision!}).catch(e=>{
            if(!/ENVIRONMENT_OVERLAY_OUTSIDE_FLOOR/.test(describe(e)))throw e;  // the uncertainty footprint (+0.10 m for unknown/entanglement boxes) must stay on the floor
            const clearance=obstacle.uncertainty_m+(['unknown','clothing_pile','cable_bundle'].includes(obstacle.kind)?.1:0);
            throw new Error(`Outside the scanned floor. Against a wall: keep the center at least half the depth + ${clearance.toFixed(2)} m away.`);});
          if(current())setPreview(next.preview??null);
        })}
        remove={id=>void perform(async()=>{discardProposal();const next=await act({action:'remove_overlay_preview',request_id:crypto.randomUUID(),object_id:id,expected_scene_revision:state.scene_revision!});if(current())setPreview(next.preview??null);})}/>
      <fieldset disabled={blocked||modelRunning||photoRunning||batching}><legend>Move one imported object</legend>
        <label className="library-field">Object<select aria-label="Imported object" value={selected} onChange={e=>{setSelected(e.target.value);setPreview(null);discardProposal();}}><option value="">Choose an object…</option>{state.objects.map(object=><option key={object.id} value={object.id}>{object.label} · {object.category} · {object.id}</option>)}</select></label>
        <label className="library-field">Move request<input aria-label="Object move request" maxLength={1000} placeholder="Move this object 10 cm along X" value={moveRequest} onChange={e=>{setMoveRequest(e.target.value);setPreview(null);discardProposal();}}/></label>
        <small>Only the selected object ID and relative move request go to the model. Review the preview before Apply.</small>
        <button type="button" disabled={!selected||!moveRequest.trim()} onClick={()=>void perform(async()=>{
          const pending={requestId:crypto.randomUUID(),jobId:null as string|null,revision:state.scene_revision!,objectId:selected};
          proposalOwner.current=pending;setPreview(null);setProposal(null);setReviewedJob(null);
          const next=await act({action:'model_move_preview',request_id:pending.requestId,object_id:selected,text:moveRequest.trim(),expected_scene_revision:pending.revision});
          if(current()&&proposalOwner.current===pending&&(!next.proposal||next.proposal.request_id!==pending.requestId)){discardProposal();throw new Error('Move suggestion was not confirmed. Check saved import before requesting again.');}
        })}>Suggest move</button>
        <div className="library-position">{['X','Y'].map((axis,i)=><label key={axis}>Move {axis} (m)<input aria-label={`Space object move ${axis}`} type="number" step="any" value={translation[i]} onChange={e=>{setTranslation(values=>values.map((value,j)=>i===j?e.target.value:value));setPreview(null);discardProposal();}}/></label>)}</div>
        <button type="button" disabled={!selected} onClick={()=>void perform(async()=>{const delta=translation.map(Number);
          if(translation.some(value=>!value.trim())||!delta.every(Number.isFinite))throw new Error('Enter finite X and Y translations.');
          discardProposal();const next=await act({action:'move_preview',request_id:crypto.randomUUID(),object_id:selected,translation_m:[delta[0],delta[1],0],expected_scene_revision:state.scene_revision!});
          if(current())setPreview(next.preview??null);})}>Preview object move</button>
        <button type="button" onClick={()=>void perform(async()=>{discardProposal();const next=await act({action:'undo_preview',request_id:crypto.randomUUID(),expected_scene_revision:state.scene_revision!});if(current())setPreview(next.preview??null);})}>Undo last edit · preview</button>
      </fieldset>
    </>}
    {proposal&&<p role="status">Move suggestion: {proposal.status}{proposal.model_id?` · ${proposal.model_id}`:''}. {proposal.status==='ready'?'Review before Apply. Nothing applied.':proposal.status==='running'?'Waiting for the model…':''}</p>}
    {proposal?.status==='ready'&&proposal.suggestion&&<p style={{overflowWrap:'anywhere'}}>Move [X, Y]: {proposal.suggestion.translation_m.slice(0,2).join(', ')} m · {proposal.suggestion.explanation}</p>}
    {proposal?.status==='ready'&&!preview&&<button type="button" disabled={blocked||reviewedJob===proposal.job_id} onClick={()=>void perform(async()=>{
      const pending=proposalOwner.current;if(!pending?.jobId||state?.scene_revision!==pending.revision)return;
      if(reviewedJob===pending.jobId||pending.reviewRequested)return;pending.reviewRequested=true;setReviewedJob(pending.jobId);
      const next=await act({action:'model_review',request_id:crypto.randomUUID(),job_id:pending.jobId,expected_scene_revision:pending.revision});
      if(current()&&proposalOwner.current===pending&&next.preview?.parent_revision===pending.revision&&next.scene_revision===pending.revision)setPreview(next.preview);
    })}>Review suggestion</button>}
    {(modelRunning||proposal?.status==='ready')&&<button type="button" disabled={blocked} onClick={()=>void perform(async()=>{const pending=proposalOwner.current;if(!pending?.jobId)return;discardProposal();setPreview(null);await act({action:'model_cancel',request_id:crypto.randomUUID(),job_id:pending.jobId});})}>Cancel suggestion</button>}
    {preview&&<section aria-label="Space edit preview"><strong>Before / after · meters</strong>
      {Object.keys({...preview.affected_before,...preview.affected_after}).map(id=><p key={id}>{id}: {preview.affected_before[id]?.position_m.join(', ')??'absent'} → {preview.affected_after[id]?.position_m.join(', ')??'absent'}</p>)}
      <small>{preview.preserved_object_count} objects preserved. Previous task plans will be invalidated.</small>
      {autoApply&&<p role="status">Twin-edit auto-apply is on: this preview is applied automatically (Engine ACK, Undo available).</p>}
      <button type="button" disabled={blocked||modelRunning} onClick={applyPreview}>Apply space edit</button><button type="button" disabled={busy||!!pendingEdit} onClick={()=>{setPreview(null);discardProposal();}}>Cancel space edit</button></section>}
    {pendingEdit&&<p role="status">{checking?'Checking engine ACK, saved revision and current frame…':'Edit result is unconfirmed. Use Check saved import.'} Operation: {pendingEdit.operationId}</p>}
    {transaction&&<p role="status">Edit {transaction.state} · Engine ACK {transaction.engine_acknowledged?'confirmed':'pending'} · Saved {transaction.durable_committed?'yes':'pending'} · Current frame {transaction.current_frame?'confirmed':'pending'}</p>}
    {state?.source_sha256&&<details><summary>Source and scene identity</summary><small>Source SHA: {state.source_sha256}</small><small>Scene revision: {state.scene_revision??'not imported'}</small></details>}
    {/* Sticky at the panel's bottom edge (-12 covers its padding): with this panel open the chat's Twin update card can be out of sight (2026-10-27 real-app run). */}
    {undoLastEdit&&<p style={{position:'sticky',bottom:-12,margin:0,padding:'4px 0',background:'#fff'}}><button type="button" disabled={blocked||modelRunning||photoRunning||batching} onClick={undoLastEdit}>Undo last edit · preview in chat</button></p>}
  </section>;
}
