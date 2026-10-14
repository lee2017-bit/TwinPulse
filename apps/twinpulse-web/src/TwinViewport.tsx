// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import type { ViewportFrame,ViewportState,ViewportTimings } from './viewport-types';
import type {ConversationState,GenerationPreview,InventoryWorkProgress} from './conversation-types';
import {AuthenticatedConversationImage} from './AuthenticatedConversationImage';
import type {WorkflowState} from './types';

export const inventoryCheckpointSaved=(work:InventoryWorkProgress)=>work.checkpoint_saved||work.draft_saved===true||work.observation_saved===true;
export type SavedGenerationScene={revision:string;partial:boolean};
export function savedGenerationScene(generation:NonNullable<ConversationState['generation']>,workflow:WorkflowState|null|undefined):SavedGenerationScene|null{
  if(!workflow||!['draft_ready','restore_review_required'].includes(workflow.phase)||workflow.error?.code==='project_persistence_failed')return null;
  const draft=workflow.site_draft??workflow.draft;
  if(!draft?.revision||!draft.input_revision||workflow.input&&workflow.input.revision!==draft.input_revision)return null;
  const preview=generation.error?.diagnostics?.generation_preview??generation.progress?.generation_preview;
  const original=workflow.site_draft?.original_scene_revision;
  if(preview?.scene_revision&&preview.scene_revision!==draft.revision&&preview.scene_revision!==original)return null;
  return {revision:draft.revision,partial:!!preview?.pending_count||!!workflow.site_draft?.progressive_twin?.unresolved.length};
}
const frameKey=(frame:ViewportFrame)=>[frame.engine_session_id,frame.stage_epoch,frame.applied_revision,frame.frame_id,frame.sha256,
  frame.captured_at_ms,frame.camera_sequence,frame.width,frame.height].join('/');
const stageLabels:Record<string,string>={observer:'Reading the source photo',observation:'Reading the source photo',
  observer_structure:'Estimating the initial room structure',initial_structure:'Estimating the initial room structure',structure_observation:'Estimating the initial room structure',
  detailed_observation:'Reading the full object inventory',preparation:'Preparing the Isaac workspace',
  room:'Preparing the room shell',room_seed:'Preparing the room shell',
  scene_design:'Designing the space',designer:'Designing the space',planner:'Designing the space',inventory:'Planning the object inventory',
  structure:'Designing the room and inventory',objects:'Preparing object details',final_validation:'Checking the final scene',
  render_preview:'Rendering the preview',photo_quality:'Reviewing photo quality',
  parameters:'Preparing object details',parameterize:'Preparing object details',parameter_batch:'Preparing object details',
  validation:'Checking the scene',geometry:'Checking geometry',geometry_checks:'Checking geometry',repair:'Correcting the scene',
  render:'Rendering the preview',render_review:'Reviewing the preview',critic:'Reviewing photo quality',quality:'Reviewing photo quality',
  quality_review:'Reviewing photo quality',compile:'Building the scene',build:'Building the scene'};
export function generationStageLabel(stage?:string){return stage?stageLabels[stage]??stage.replaceAll('_',' '):'Preparing your Twin';}

export function generationIsIncomplete(generation:NonNullable<ConversationState['generation']>){
  const inventory=generation.error?.diagnostics?.inventory_progress??generation.progress?.inventory_progress;
  const preview=generation.error?.diagnostics?.generation_preview??generation.progress?.generation_preview;
  return generation.state!=='completed'||inventory?.parameters_complete===false||!!inventory?.pending_count||
    !!preview&&(preview.state!=='ready'||!!preview.pending_count);
}

export function generationActivityLabel(generation:NonNullable<ConversationState['generation']>){
  const diagnostics=generation.error?.diagnostics,progress=generation.progress;
  const activity=diagnostics?.generation_activity??progress?.generation_activity;
  const stage=activity?.stage??diagnostics?.stage??progress?.stage;
  const preview=diagnostics?.generation_preview??progress?.generation_preview;
  const reasons=activity?.reason_codes??[];
  const stopped=generation.error?.code?generation.error.code==='REPAIR_STALLED':reasons.includes('REPAIR_STALLED');
  const retained=preview?.scene_revision?' · last valid preview retained':' · no confirmed 3D preview';
  if(generation.state==='completed')return generationIsIncomplete(generation)?
    'Generation ended · incomplete preview retained':'Scene generation completed · photo quality and motion checks require separate review';
  if(['failed','cancelled','interrupted'].includes(generation.state)){
    // Activity is the last observed worker phase, not proof that a terminal
    // job is still waiting for a model or applying a candidate.
    const result=generation.state==='failed'&&stopped?'stopped after no validated repair progress':`generation ${generation.state}`;
    const code=generation.error?.code??(generation.state==='failed'?reasons[0]:undefined);
    return `${generationStageLabel(stage)} · ${result}${code?` (${code})`:''}${retained}`;
  }
  if(stopped)return `Stopped after no validated repair progress${retained}`;
  if(activity?.phase==='blocked')return `${generationStageLabel(stage)} · blocked${retained}`;
  const phases={waiting_model:'waiting for model response',validating:'validating the received candidate',
    building:'applying the checked candidate in Isaac',awaiting_frame:'waiting for its current Isaac frame',
    ready:'stage completed',blocked:'blocked'};
  const phase=activity?phases[activity.phase]:generation.state==='accepted'?'waiting for stage update':progress?.status??generation.state;
  const batch=activity?.batch_index!==undefined?` · batch ${activity.batch_index}${activity.batch_total!==undefined?`/${activity.batch_total}`:''}`:'';
  const repair=stage?.includes('repair')&&progress?.repair_count!==undefined?` · repair ${progress.repair_count}/${progress.max_repairs??'?'}`:'';
  const targets=activity?.affected_ids?.length?` · ${activity.affected_ids.join(', ')}`:'';
  return `${generationStageLabel(stage)} · ${phase}${batch}${repair}${targets}`;
}

function GenerationProgress({generation,confirmedPreview,imageDecoded,savedScene}:{generation:NonNullable<ConversationState['generation']>;confirmedPreview:GenerationPreview|null;imageDecoded:boolean;savedScene:SavedGenerationScene|null}){
  const progress=generation.progress,diagnostics=generation.error?.diagnostics;
  const preview=diagnostics?.generation_preview??progress?.generation_preview;
  const inventory=diagnostics?.inventory_progress??progress?.inventory_progress;
  const incomplete=generationIsIncomplete(generation);
  const pending=preview?.pending_objects??confirmedPreview?.pending_objects;
  const completedSaved=generation.state==='completed'&&!incomplete&&!!savedScene&&!savedScene.partial;
  return <div className="twin-generation-progress" role="status" aria-label="Twin generation progress" tabIndex={0}
    aria-description="Scrollable generation details. Focus this panel and use the arrow keys to read additional progress and errors.">
    <strong>{incomplete?'Incomplete · Preview':'Preview · generation complete'}</strong>
    <p>{generationActivityLabel(generation)}</p>
    <p>Repairs: {progress?.repair_count??0}/{progress?.max_repairs??0}{progress?.elapsed_s!==undefined&&` · ${Math.round(progress.elapsed_s)} s`}</p>
    {inventory?.inventory_planned?<p>Parameters: {inventory.parameterized_count} of {inventory.inventory_count} objects prepared · {inventory.pending_count} awaiting parameters</p>:
      <><p>Observation: {inventory?`${inventory.observed_instances} provisional instances`:'object count not confirmed'} · object inventory not planned</p>
        <p>{inventory?'Parameters: 0 objects prepared · awaiting inventory':'Parameters: count not confirmed'}</p></>}
    <p>Last confirmed 3D: {confirmedPreview?`${confirmedPreview.rendered_count} of ${confirmedPreview.inventory_count} objects rendered · ${confirmedPreview.pending_count} not rendered${confirmedPreview.inventory_count===0?' · room shell only':''}`:
      'not confirmed · no object-render count available'}</p>
    <p>Displayed image: {imageDecoded?'decoded Isaac image available · see current / static frame status below':'waiting for a decoded Isaac frame'}</p>
    {preview?.state==='building'&&<p>Candidate preview: {preview.rendered_count} of {preview.inventory_count} objects selected · {preview.pending_count} not included yet · render not confirmed</p>}
    {preview&&<small>{preview.state==='blocked'&&preview.error_code==='PREVIEW_REBUILD_REQUIRED'?
      imageDecoded?'Exact candidate static preview · rebuild required before a current frame or camera controls':'Candidate rebuild required · no exact static preview decoded':preview.state==='blocked'?preview.scene_revision?'Last valid preview retained · current candidate blocked':
      'Current candidate blocked · no confirmed 3D preview':`Candidate preview: ${preview.state}`}</small>}
    {(confirmedPreview?.scene_revision||preview?.candidate_revision)&&<details><summary>Preview details</summary>
      {confirmedPreview?.scene_revision&&<small>Confirmed preview revision: {confirmedPreview.scene_revision}</small>}
      {preview?.candidate_revision&&<small>Candidate revision: {preview.candidate_revision}</small>}
    </details>}
    {!!pending?.length&&<details><summary>Objects waiting for 3D · {pending.length}</summary><ul>
      {pending.map(object=><li key={object.id}>{object.id} · {object.reason_code.replaceAll('_',' ').toLowerCase()}
        {!!object.blocked_by?.length&&` · waiting for: ${object.blocked_by.join(', ')}`}</li>)}
    </ul><p>The full inventory is retained. These objects are not confirmed as rendered.</p></details>}
    {completedSaved&&<p>Scene draft saved · photo quality, simulation and physical execution require separate checks.</p>}
    {!completedSaved&&inventory&&inventoryCheckpointSaved(inventory)&&<p>Resume checkpoint saved · resume data retained; scene acceptance and storage are separate.</p>}
    {!completedSaved&&savedScene&&<p>{savedScene.partial?'Saved partial scene':'Accepted scene saved separately'} · the resume checkpoint is not a complete accepted scene.</p>}
    {(generation.error||preview?.error_code)&&<p>Latest error: {generation.error?`${generation.error.message} (${generation.error.code})`:preview?.error_code}</p>}
    <small>Preview only. Whole-scene completion, simulation and physical execution require separate checks.</small>
  </div>;
}

export type ViewerFault={code:string;execution_id:string|null};
export function TwinViewport({api,projectId,report,diagnose,generation,sourcePhoto,savedScene=null}: {api:TwinPulseApi;projectId?:string;report?:(fault:ViewerFault|null)=>void;diagnose?:(id:string|null)=>void;
  generation?:ConversationState['generation'];sourcePhoto?:{url:string;name:string}|null;savedScene?:SavedGenerationScene|null}) {
  const preview=generation?.error?.diagnostics?.generation_preview??generation?.progress?.generation_preview;
  const rebuildRequired=preview?.state==='blocked'&&preview.error_code==='PREVIEW_REBUILD_REQUIRED';
  const [state,setState]=useState<ViewportState|null>(null);
  const [displayed,setDisplayed]=useState<{api:TwinPulseApi;projectId?:string;inputOrigin:string|null;frame:ViewportFrame;previewOnly:boolean}|null>(null);
  // A temporarily omitted origin and a new operation for the same input do
  // not retire its preview. A different explicit input does, even in the
  // same project and API session.
  const lineage=useRef({api,projectId,inputOrigin:generation?.origin_message_id??null,requireConfirmedRevision:false});
  if(lineage.current.api!==api||lineage.current.projectId!==projectId)
    lineage.current={api,projectId,inputOrigin:generation?.origin_message_id??null,requireConfirmedRevision:false};
  else if(generation?.origin_message_id&&generation.origin_message_id!==lineage.current.inputOrigin)
    lineage.current={api,projectId,inputOrigin:generation.origin_message_id,requireConfirmedRevision:true};
  const {inputOrigin,requireConfirmedRevision}=lineage.current;
  const owner=useRef({api,projectId,inputOrigin});owner.current={api,projectId,inputOrigin};
  const image=displayed?.api===api&&displayed.projectId===projectId&&displayed.inputOrigin===inputOrigin&&
    (!rebuildRequired||displayed.previewOnly&&displayed.frame.applied_revision===preview.scene_revision)?displayed:null;
  const decoding=useRef(false);
  const surface=useRef<HTMLCanvasElement>(null);
  const [error,setError]=useState<string|null>(null);
  const [diagnostic,setDiagnostic]=useState<string|null>(null);
  const callbacks=useRef({report,diagnose});callbacks.current={report,diagnose};
  const [cameraError,setCameraError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const [cameraReadyAt,setCameraReadyAt]=useState(0);
  const [displayAge,setDisplayAge]=useState(Date.now());
  const confirmedNow=preview?.scene_revision&&preview.state!=='building'?preview:null;
  const generationSnapshot=useRef(generation);generationSnapshot.current=generation;
  const [lastConfirmed,setLastConfirmed]=useState<{api:TwinPulseApi;projectId?:string;inputOrigin:string|null;operationId:string;preview:GenerationPreview}|null>(null);
  useEffect(()=>{
    if(confirmedNow&&generation)setLastConfirmed({api,projectId,inputOrigin,operationId:generation.operation_id,preview:confirmedNow});
    else setLastConfirmed(current=>current?.api===api&&current.projectId===projectId&&current.inputOrigin===inputOrigin&&current.operationId===generation?.operation_id?current:null);
  },[api,projectId,inputOrigin,generation?.operation_id,confirmedNow]);
  const confirmedPreview=confirmedNow??(lastConfirmed?.api===api&&lastConfirmed.projectId===projectId&&
    lastConfirmed.inputOrigin===inputOrigin&&lastConfirmed.operationId===generation?.operation_id?lastConfirmed.preview:null);
  useEffect(()=>{
    let closed=false, pending=false, last='',shown:ViewportFrame|null=null,reported='';
    const reportedFailures=new Map<string,string|null>();
    let reportedId:string|null=null;
    let timer:ReturnType<typeof setTimeout>|undefined;
    let scheduledAt=performance.now();
    const clear=()=>{
      const canvas=surface.current;
      canvas?.getContext('2d')?.clearRect(0,0,canvas.width,canvas.height);
      setDisplayed(null);last='';shown=null;
    };
    // A replacement session, project or explicit input must not inherit
    // pixels or camera authority while its first matching receipt is pending.
    clear();setState(null);setError(null);setDiagnostic(null);reported='';callbacks.current.report?.(null);
    setCameraError(null);setBusy(false);setCameraReadyAt(0);
    const acceptsFrame=(frame:ViewportFrame)=>{
      if(owner.current.api!==api||owner.current.projectId!==projectId||owner.current.inputOrigin!==inputOrigin)return false;
      const job=generationSnapshot.current;
      // Reload has no earlier lineage to compare. An unfinished generation
      // still needs its own confirmed revision before adopting a receipt.
      const unfinished=!!job&&['accepted','running','failed'].includes(job.state);
      const expected=job?.error?.diagnostics?.generation_preview??job?.progress?.generation_preview;
      const rebuilding=expected?.state==='blocked'&&expected.error_code==='PREVIEW_REBUILD_REQUIRED';
      if(!requireConfirmedRevision&&!unfinished&&!rebuilding)return true;
      if(job?.origin_message_id&&job.origin_message_id!==inputOrigin)return false;
      return !!expected?.scene_revision&&expected.state!=='building'&&expected.scene_revision===frame.applied_revision;
    };
    const poll=async()=>{
      if(closed||pending||typeof api.viewportState!=='function')return;
      pending=true;
      const started=performance.now();
      const timings:ViewportTimings={metadata_ms:0,image_ms:0,decode_ms:0,poll_ms:0,frame_age_ms:0,
        schedule_lag_ms:Math.max(0,started-scheduledAt)};
      let observed:ViewportState['frame']=null,code='viewport_http_error';
      try {
        let next:ViewportState;
        try{next=await api.viewportState();}finally{timings.metadata_ms=performance.now()-started;}
        if(closed)return;
        observed=next.frame;setState(next);
        const job=generationSnapshot.current,expected=job?.error?.diagnostics?.generation_preview??job?.progress?.generation_preview;
        const rebuilding=expected?.state==='blocked'&&expected.error_code==='PREVIEW_REBUILD_REQUIRED';
        let previewOnly=rebuilding||!next.frame;
        let frame=previewOnly?next.last_frame:next.frame;
        if(!frame){reported='';return;}
        // A new input can precede the engine's retirement of the previous
        // input receipt. Wait for this generation's confirmed scene revision.
        if(!acceptsFrame(frame))return;
        let key=frameKey(frame);
        if(previewOnly&&(next.last_frame?.preview_only!==true||next.last_frame.physical_authority!==false||
          !/^[a-f0-9]{64}$/.test(frame.sha256)||frame.url!==`/v1/product/viewport/preview/${frame.sha256}`||
          typeof api.viewportPreviewImage!=='function'))return;
        // Reuse pixels already decoded for this project when the server has
        // retired that receipt to its authenticated static preview.
        if(previewOnly&&shown?.sha256===frame.sha256){
          if(key!==last||shown!==frame){last=key;shown=frame;setDisplayed({api,projectId,inputOrigin,frame,previewOnly:true});}
          return;
        }
        if(key!==last){
          // A timed-out native decoder cannot be cancelled. Wait for that
          // single decoder to settle; still poll metadata, never stack work.
          if(decoding.current)return;
          let blob:Blob;const imageStarted=performance.now();
          try{
            if(previewOnly){
              if(next.last_frame?.preview_only!==true||next.last_frame.physical_authority!==false||
                !/^[a-f0-9]{64}$/.test(frame.sha256)||frame.url!==`/v1/product/viewport/preview/${frame.sha256}`||
                typeof api.viewportPreviewImage!=='function')return;
              blob=await api.viewportPreviewImage(frame.sha256);
            }else if(typeof api.viewportImageFrame==='function'){
              const packet=await api.viewportImageFrame();if(closed)return;
              next=packet.state;observed=next.frame;setState(next);
              if(!next.frame){reported='';return;}
              frame=next.frame;key=frameKey(frame);
              if(!acceptsFrame(frame))return;
              if(!packet.image){code='viewport_image_invalid';throw new Error('Viewer current receipt has no image');}
              blob=packet.image;
            }else blob=await api.viewportImage(frame.frame_id); // Legacy test/adaptor contract remains available.
          }finally{timings.image_ms=performance.now()-imageStarted;}
          if(closed)return;
          // Do not blame native decoding when an already stale JPEG arrived.
          // The read itself can be delayed while Isaac continues publishing.
          if(!previewOnly&&Date.now()-frame.captured_at_ms>=1000){code='viewport_image_expired';throw new Error('Viewer image delivery exceeded frame freshness');}
          // One reusable surface, one decode in flight, no per-frame blob URL
          // or image-resource cache. Always release native decoded storage,
          // including late completion, stale frame and drawing failures.
          code='viewport_decode_failed';
          let abandoned=false,released=false,decodeTimer:ReturnType<typeof setTimeout>|undefined;
          const releaseBitmap=(value:ImageBitmap)=>{if(!released){released=true;value.close();}};
          decoding.current=true;
          const decoded=Promise.resolve().then(()=>createImageBitmap(blob)).then(bitmap=>{
            decoding.current=false;
            if(abandoned||closed)releaseBitmap(bitmap);
            return bitmap;
          },cause=>{decoding.current=false;throw cause;});
          let bitmap:ImageBitmap;
          const decodeStarted=performance.now();
          try{
            bitmap=await Promise.race([decoded,new Promise<never>((_,reject)=>{
              decodeTimer=setTimeout(()=>{
                abandoned=true;code='viewport_decode_expired';
                reject(new Error('Viewer decode exceeded frame freshness; waiting for decoder completion'));
              },previewOnly?2000:Math.max(0,1000-(Date.now()-frame!.captured_at_ms)));
            })]);
          }finally{timings.decode_ms=performance.now()-decodeStarted;if(decodeTimer!==undefined)clearTimeout(decodeTimer);}
          try {
            if(closed||!acceptsFrame(frame))return;
            if(!previewOnly&&Date.now()-frame.captured_at_ms>=1000){code='viewport_decode_expired';throw new Error('Viewer frame expired during decode');}
            if(bitmap.width!==frame.width||bitmap.height!==frame.height)
              throw new Error('Viewer frame dimensions do not match its receipt');
            const canvas=surface.current;const context=canvas?.getContext('2d');
            code='viewport_draw_failed';
            if(!canvas||!context)throw new Error('Viewer drawing surface unavailable');
            if(canvas.width!==bitmap.width)canvas.width=bitmap.width;
            if(canvas.height!==bitmap.height)canvas.height=bitmap.height;
            context.clearRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0);
            last=key;shown=frame;reported='';setDisplayed({api,projectId,inputOrigin,frame,previewOnly});setError(null);setDiagnostic(null);callbacks.current.report?.(null);
          } finally {releaseBitmap(bitmap);}
        }
        setState(next);
      }catch(caught){
        if(!closed){
          // The engine can replace a frame between metadata and image GET.
          // This expected read race is not a display failure. Retain the
          // decoded pixels as a preview; only their own matching fresh receipt
          // can make them live or authorize camera controls.
          if(caught && typeof caught==='object' && 'code' in caught && caught.code==='viewport_frame_expired')return;
          setState(null);setError(caught instanceof Error?caught.message:'Viewer reception failed');
          if(caught && typeof caught==='object' && 'code' in caught && caught.code==='viewport_image_invalid')code='viewport_image_invalid';
          const signature=observed?[observed.engine_session_id,observed.stage_epoch,observed.applied_revision,code].join('/'):'';
          reported=signature;
          reportedId=reportedFailures.get(signature)??null;setDiagnostic(reportedId);
          callbacks.current.report?.({code,execution_id:reportedId});
          if(observed && !reportedFailures.has(signature) && typeof api.viewportObservation==='function'){
            reportedFailures.set(signature,null);
            if(reportedFailures.size>64)reportedFailures.delete(reportedFailures.keys().next().value!);
            // Optional diagnostic delivery must never suspend frame reception.
            // Keep the saved failure ID, but a late ACK cannot revive its UI
            // fault after recovery or a different scene/fault has superseded it.
            timings.poll_ms=performance.now()-started;timings.frame_age_ms=Date.now()-observed.captured_at_ms;
            for(const key of Object.keys(timings) as (keyof ViewportTimings)[])
              timings[key]=Math.round(Math.min(60000,Math.max(0,timings[key]))*100)/100;
            void api.viewportObservation({frame_id:observed.frame_id,engine_session_id:observed.engine_session_id,
                stage_epoch:observed.stage_epoch,applied_revision:observed.applied_revision,error_code:code,timings})
              .then(result=>{
                if(closed)return;
                if(reportedFailures.has(signature))reportedFailures.set(signature,result.execution_id);
                if(reported!==signature)return;
                reportedId=result.execution_id;setDiagnostic(result.execution_id);
                callbacks.current.report?.({code,execution_id:result.execution_id});
              }).catch(()=>{/* Keep local error; never retry an unknown POST. */});
          }
        }
      }finally{
        pending=false;
        // A slow response must not lose the next whole interval. Keep only
        // one request in flight and cap normal polling at about 7 requests/s.
        if(!closed){const delay=Math.max(20,140-(performance.now()-started));scheduledAt=performance.now()+delay;
          timer=setTimeout(()=>void poll(),delay);}
      }
    };
    void poll();
    const age=setInterval(()=>setDisplayAge(Date.now()),100);
    return()=>{closed=true;clearTimeout(timer);clearInterval(age);};
  },[api,projectId,inputOrigin,requireConfirmedRevision]);
  const currentGeneration=!rebuildRequired&&(!generation||generation.state==='completed'||generation.state==='running'&&
    !!preview&&preview.state==='ready'&&preview.scene_revision===image?.frame.applied_revision);
  const fresh=currentGeneration&&!!image&&!image.previewOnly&&!error&&!!state?.frame&&['live','degraded'].includes(state.state)&&
    frameKey(image.frame)===frameKey(state.frame)&&displayAge-image.frame.captured_at_ms<1000;
  const camera=async(action:string)=>{
    if(busy||!fresh||!state?.frame||Date.now()-state.frame.captured_at_ms>=1000||Date.now()<cameraReadyAt)return;
    setBusy(true);setCameraError(null);
    try{
      const result=await api.viewportCamera({request_id:crypto.randomUUID(),frame_id:state.frame.frame_id,action});
      if(owner.current.api!==api||owner.current.projectId!==projectId||owner.current.inputOrigin!==inputOrigin)return;
      // Match the server's bounded camera rate; a fast frame ACK is not a
      // permit to send another camera mutation before its 200 ms interval.
      setCameraReadyAt(Date.now()+200);
      setState(current=>current?{...current,camera_pending:result.camera_pending,camera_result:result.camera_result}:current);
    }
    catch(caught){if(owner.current.api===api&&owner.current.projectId===projectId&&owner.current.inputOrigin===inputOrigin)setCameraError(caught instanceof Error?caught.message:'Camera request failed. No automatic retry.');}
    finally{if(owner.current.api===api&&owner.current.projectId===projectId&&owner.current.inputOrigin===inputOrigin)setBusy(false);}
  };
  return <section className="twin-live-viewport" aria-label="Isaac viewport">
    <p role="status">{fresh ? state!.state==='live'?'Live Isaac render':'Live render · reduced frame rate' : image?'Last preview · not live':'Viewer waiting / stale'}
      {fresh && ` · ${state!.fps.toFixed(1)} FPS`}</p>
    {generation&&<GenerationProgress generation={generation} confirmedPreview={confirmedPreview} imageDecoded={!!image} savedScene={savedScene}/>}
    <canvas ref={surface} hidden={!image} role={image?'img':undefined}
      aria-label={image?fresh?'Current Isaac Digital Twin render':'Last Isaac preview · not live':undefined}
      data-frame-id={image?.frame.frame_id} data-captured-at={image?.frame.captured_at_ms}
      data-preview-only={image?!fresh:undefined}/>
    {!image && <div className="chat-twin-placeholder"><strong>No current 3D frame</strong>
      <p>Build the scene in Isaac to see a 3D preview.</p></div>}
    {sourcePhoto&&<figure key="source-photo" className="twin-source-photo"><AuthenticatedConversationImage api={api} url={sourcePhoto.url} alt={`Source photo: ${sourcePhoto.name}`}/>
      <figcaption>Source photo · reference for this Twin</figcaption></figure>}
    {error && <p role="alert">Viewer: {error}. Browser display is unavailable; this does not mean scene apply failed.
      {diagnostic && <button onClick={()=>callbacks.current.diagnose?.(diagnostic)}>View display diagnostics</button>}</p>}
    {cameraError && <p role="alert">Camera: {cameraError}. This action is not retried automatically.</p>}
    {state?.camera_result?.state==='failed' && <p role="alert">Camera action failed: {state.camera_result.code}. No automatic retry.</p>}
    <div className="twin-camera-actions" aria-label="Camera controls">
      {([['orbit_left','Orbit left'],['orbit_right','Orbit right'],['zoom_in','Zoom in'],['zoom_out','Zoom out'],
        ['pan_left','Pan left'],['pan_right','Pan right'],['pan_up','Pan up'],['pan_down','Pan down']] as const).map(([action,label])=>
          <button key={action} disabled={!fresh||busy||state?.camera_pending||displayAge<cameraReadyAt} onClick={()=>void camera(action)}>{label}</button>)}
    </div>
    <p className="twin-camera-status" role="status" style={{visibility:fresh&&state?.camera_pending?'visible':'hidden'}}>Camera request accepted · waiting for Isaac</p>
    <small className="twin-frame-caption">{image?fresh?<>
      Frame {image.frame.frame_id} · stage {image.frame.stage_epoch} · captured {new Date(image.frame.captured_at_ms).toLocaleTimeString('en-GB',{hour12:false})}.
      Rendering is not proof of simulation or robot movement.</>:<>
      Static preview from revision {image.frame.applied_revision} · captured {new Date(image.frame.captured_at_ms).toLocaleTimeString('en-GB',{hour12:false})}. It may differ from the current scene. Camera controls require a fresh current frame.</>:
      'Waiting for a decoded Isaac frame. Camera controls require a fresh current frame.'}</small>
  </section>;
}
