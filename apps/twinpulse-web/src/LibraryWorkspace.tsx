// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import {ApiError,fileToBase64,type TwinPulseApi} from './api';
import type {LibraryAttachment,LibraryExtension,LibraryJob,LibraryPlacementPreview,LibraryWorkspaceAction,LibraryWorkspaceState,ToolInputSchema} from './library-workspace-types';
import type {SceneEditTransaction,WorkflowState} from './types';
import {ModelPreview} from './ModelLibrary';

export type LibraryWorkspaceTab='create'|'import'|'assets'|'connections';
const imageTypes=['image/png','image/jpeg','image/webp'];
const inputError=(error:unknown)=>error instanceof Error?error.message:String(error);
const retryableColdRead=(error:unknown)=>error instanceof ApiError?error.code==='state_read_timeout':
  error instanceof TypeError&&error.message==='Failed to fetch';
type PlacementCheck={operationId:string;parentRevision:string;resultRevision:string;message:string};
async function attachment(file:File,role:LibraryAttachment['role']):Promise<LibraryAttachment>{
  if(file.size>50*1024*1024)throw new Error('Choose a local file up to 50 MiB.');
  if(role==='asset_reference'&&(!imageTypes.includes(file.type)||file.size>10*1024*1024))throw new Error('Choose one PNG, JPEG or WebP asset reference up to 10 MiB.');
  return {name:file.name,media_type:file.type||'application/octet-stream',bytes_base64:await fileToBase64(file),role};
}

export function ToolFields({schema,values,change,disabled=false,prefix='tool'}:{schema:ToolInputSchema;values:Record<string,unknown>;change:(key:string,value:unknown)=>void;disabled?:boolean;prefix?:string}){
  return <>{Object.entries(schema.properties??{}).map(([name,field])=>{
    const label=field.title??name,value=values[name]??field.default??'',required=schema.required?.includes(name);
    return <label className="library-field" key={name}>{label}{required?' *':''}
      {field.enum?<select aria-label={label} disabled={disabled} value={String(value)} onChange={e=>change(name,e.target.value)}><option value="">Choose…</option>{field.enum.map((option,i)=><option key={i} value={String(option)}>{String(option)}</option>)}</select>:
        field.type==='boolean'?<input aria-label={label} type="checkbox" disabled={disabled} checked={value===true} onChange={e=>change(name,e.target.checked)}/>:
        ['object','array'].includes(field.type??'')?<textarea aria-label={label} disabled={disabled} value={typeof value==='string'?value:JSON.stringify(value)} placeholder={field.type==='array'?'[]':'{}'} onChange={e=>change(name,e.target.value)}/>:
        <input aria-label={label} id={`${prefix}-${name}`} disabled={disabled} type={['number','integer'].includes(field.type??'')?'number':'text'} min={field.minimum} max={field.maximum} step={field.type==='integer'?1:'any'} value={String(value)} onChange={e=>change(name,e.target.value)}/>}
      {field.description&&<small>{field.description}</small>}</label>;
  })}{!schema.properties&&<p>This tool declares no input fields.</p>}</>;
}
export function toolInputs(schema:ToolInputSchema,values:Record<string,unknown>):Record<string,unknown>{
  const result:Record<string,unknown>=Object.create(null);
  for(const [name,field] of Object.entries(schema.properties??{})){
    let value=values[name]??field.default;
    if(value===undefined||value===''){if(schema.required?.includes(name))throw new Error(`${field.title??name} is required.`);continue;}
    if(field.enum){value=field.enum.find(item=>String(item)===String(value));if(value===undefined)throw new Error(`Choose a supported ${name}.`);}
    else if(field.type==='number'||field.type==='integer'){
      value=Number(value);if(!Number.isFinite(value)||(field.type==='integer'&&!Number.isInteger(value)))throw new Error(`${name} must be a valid ${field.type}.`);
      if(field.minimum!==undefined&&(value as number)<field.minimum||field.maximum!==undefined&&(value as number)>field.maximum)throw new Error(`${name} is outside the supported range.`);
    }else if(field.type==='object'||field.type==='array'){
      if(typeof value==='string'){try{value=JSON.parse(value);}catch{throw new Error(`${name} needs valid JSON.`);}}
      if(field.type==='array'?!Array.isArray(value):typeof value!=='object'||value===null||Array.isArray(value))throw new Error(`${name} must be a JSON ${field.type}.`);
    }
    result[name]=value;
  }
  return result;
}
function Result({value}:{value:Record<string,unknown>}){
  const tables=Array.isArray(value.tables)?value.tables:('columns'in value&&'rows'in value?[value]:[]);
  return <div className="library-result">{typeof value.text==='string'&&<p>{value.text}</p>}{tables.map((table,index)=>{
    if(!table||typeof table!=='object')return null;
    const item=table as Record<string,unknown>,columns=Array.isArray(item.columns)?item.columns:[],rows=Array.isArray(item.rows)?item.rows:[];
    return <table key={index}><caption>{typeof item.title==='string'?item.title:'Tool results'}</caption><thead><tr>{columns.map((column,i)=><th key={i}>{String(column)}</th>)}</tr></thead>
      <tbody>{rows.slice(0,200).map((row,i)=><tr key={i}>{(Array.isArray(row)?row:columns.map(column=>(row as Record<string,unknown>)?.[String(column)])).map((cell,j)=><td key={j}>{typeof cell==='object'?JSON.stringify(cell):String(cell??'')}</td>)}</tr>)}</tbody></table>;
  })}<details><summary>Saved result data</summary><pre>{JSON.stringify(value,null,2)}</pre></details></div>;
}
function JobCard({job,busy,act}:{job:LibraryJob;busy:boolean;act:(action:LibraryWorkspaceAction)=>void}){
  return <article className="library-job" aria-label={`Library job ${job.job_id}`}><h4>{job.purpose.replaceAll('_',' ')} · {job.status}</h4>
    <p role="status">{job.phase} · {job.message}</p>{job.error&&<p role="alert">{job.error}</p>}
    <small>Tool: {job.tool_id} · Execution: {job.execution_id}</small>
    {job.can_cancel&&<button disabled={busy} onClick={()=>act({action:'cancel_job',job_id:job.job_id})}>Cancel Library job</button>}
    {job.can_register&&job.status==='ready'&&<button disabled={busy} onClick={()=>act({action:'register_job',job_id:job.job_id,request_id:crypto.randomUUID()})}>Register asset</button>}
    {job.status==='unknown'&&<p>Outcome unknown. Check the saved result; do not repeat this work.</p>}
    {job.result&&<Result value={job.result}/>}</article>;
}
function ExtensionCard({extension,busy,act}:{extension:LibraryExtension;busy:boolean;act:(action:LibraryWorkspaceAction)=>void}){
  const [executable,setExecutable]=useState(''),[enabled,setEnabled]=useState(extension.enabled);
  useEffect(()=>setEnabled(extension.enabled),[extension.enabled]);
  return <article className="library-extension"><h4>{extension.title}</h4><p>{extension.available?'Available':'Unavailable'} · {extension.transport} · {extension.version??'Version not checked'}</p>
    {extension.reason&&<p>{extension.reason}</p>}
    <label><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>setEnabled(e.target.checked)}/>Enable for this project</label>
    {extension.executable_configurable&&<label className="library-field">Reviewed program path<input aria-label={`${extension.title} program path`} value={executable} disabled={busy} onChange={e=>setExecutable(e.target.value)}/></label>}
    <button disabled={busy} onClick={()=>act({action:'configure_extension',extension_id:extension.extension_id,executable,enabled})}>Save {extension.title} settings</button>
    <button disabled={busy} onClick={()=>act({action:'check_extension',extension_id:extension.extension_id})}>Check {extension.title}</button>
    <small>Saving settings does not install or run this program. Check tests only the reviewed adapter.</small></article>;
}

export function LibraryWorkspace({api,tab,initialImport,initialReference,initialPrompt='',sceneRevision,onSceneApplied,onImportSubmitted,placementEnabled=true}:{
  api:TwinPulseApi;tab:LibraryWorkspaceTab;initialImport?:File|null;initialReference?:File|null;initialPrompt?:string;
  sceneRevision?:string|null;onSceneApplied?:(state:WorkflowState)=>void|Promise<void>;onImportSubmitted?:()=>void;placementEnabled?:boolean;
}){
  const [workspace,setWorkspace]=useState<LibraryWorkspaceState|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  const [readPhase,setReadPhase]=useState<'loading'|'retrying'|'ready'|'failed'>('loading');
  const [prompt,setPrompt]=useState(initialPrompt),[reference,setReference]=useState<File|null>(initialReference??null),[sourceFile,setSourceFile]=useState<File|null>(initialImport??null);
  const [source,setSource]=useState('User-provided local file'),[license,setLicense]=useState(''),[selected,setSelected]=useState<string|null>(null);
  const [sourceUnits,setSourceUnits]=useState<''|'m'|'cm'|'mm'>(''),[sourceUpAxis,setSourceUpAxis]=useState<''|'Y'|'Z'>('');
  const [toolId,setToolId]=useState(''),[toolValues,setToolValues]=useState<Record<string,unknown>>({}),[toolFile,setToolFile]=useState<File|null>(null);
  const [instance,setInstance]=useState(''),[position,setPosition]=useState(['0','0','0']),[yaw,setYaw]=useState('0');
  const positionEdited=useRef([false,false,false]);
  const [preview,setPreview]=useState<{value:LibraryPlacementPreview;asset:string;version:string;revision:string;epoch:number}|null>(null);
  const [placementCheck,setPlacementCheck]=useState<PlacementCheck|null>(null);
  const [unknown,setUnknown]=useState<{requestId:string|null;message:string}|null>(null);
  const context=api.context;
  const lock=useRef<symbol|null>(null),mounted=useRef(true),sequence=useRef(0),lastRead=useRef(0),owner=useRef({api,context});owner.current={api,context};
  const readEpoch=useRef(0);
  const sceneOwner=useRef(sceneRevision);sceneOwner.current=sceneRevision;
  const current=()=>mounted.current&&owner.current.api===api&&owner.current.context===context&&api.context===context;
  const accept=(next:LibraryWorkspaceState)=>{if(!current())return;setWorkspace(next);};
  const refresh=async()=>{const reading=++sequence.current,epoch=readEpoch.current;
    try{const next=await api.libraryWorkspace();if(!current()||epoch!==readEpoch.current||reading!==sequence.current||reading<lastRead.current)return;
      lastRead.current=reading;accept(next);setReadPhase('ready');return next;
    }catch(error){if(!current()||epoch!==readEpoch.current||reading!==sequence.current||reading<lastRead.current)return;throw error;}
  };
  useEffect(()=>{mounted.current=true;lock.current=null;setBusy(false);setWorkspace(null);setPreview(null);setPlacementCheck(null);setUnknown(null);
    const epoch=++readEpoch.current;let active=true,timer:ReturnType<typeof setTimeout>|undefined;
    setReadPhase('loading');setError(null);
    const initialRead=async(retried=false)=>{
      const request=refresh(),reading=sequence.current;
      try{await request;}catch(e){
        if(!active||!current()||readEpoch.current!==epoch||sequence.current!==reading)return;
        if(!retried&&retryableColdRead(e)){
          setReadPhase('retrying');timer=setTimeout(()=>{
            if(active&&current()&&readEpoch.current===epoch&&sequence.current===reading)void initialRead(true);
          },400);
        }else{setReadPhase('failed');setError(inputError(e));}
      }
    };
    void initialRead();return()=>{active=false;clearTimeout(timer);readEpoch.current++;mounted.current=false;};},[api,api.context]);
  const active=!!workspace?.jobs.some(job=>['queued','running'].includes(job.status));
  useEffect(()=>{if(!active)return;let running=false;const timer=setInterval(()=>{if(!current()||running||lock.current)return;running=true;void refresh().catch(e=>{if(current())setError(inputError(e));}).finally(()=>{running=false;});},1000);return()=>clearInterval(timer);},[active,api,api.context]);
  const perform=async(work:()=>Promise<void>,readOnly=false)=>{if(lock.current||unknown&&!readOnly)return;const token=Symbol();lock.current=token;setBusy(true);setError(null);
    try{await work();}catch(e){if(current())setError(inputError(e));}finally{if(lock.current===token){lock.current=null;if(current())setBusy(false);}}};
  const action=async(body:LibraryWorkspaceAction)=>{
    if(!current())throw new ApiError('context_changed','Project changed before Library submission. The draft was not sent.');
    try{const result=await api.libraryWorkspaceAction(body);if(current()){lastRead.current=++sequence.current;accept(result);}return result;}
    catch(e){if(current()&&(!(e instanceof ApiError)||e.code==='delivery_unknown'))setUnknown({requestId:'request_id'in body?body.request_id:null,message:'Delivery unknown. Check the saved workspace; this action will not be repeated automatically.'});throw e;}
  };
  const act=(body:LibraryWorkspaceAction)=>void perform(async()=>{await action(body);});
  const assets=workspace?.assets??[],asset=assets.find(item=>`${item.asset_id}/${item.version}`===selected);
  const availableTools=(workspace?.extensions??[]).flatMap(extension=>extension.tools.map(tool=>({extension,tool})));
  const chosenTool=availableTools.find(item=>item.tool.tool_id===toolId);
  const usdInspector=workspace?.extensions.find(extension=>extension.extension_id==='usd_inspector');
  const usdAvailable=!!usdInspector?.available&&usdInspector.enabled;
  const selectedUsd=!!sourceFile&&/\.(?:usd|usda|usdc)$/i.test(sourceFile.name);
  const selectedObj=!!sourceFile&&/\.obj$/i.test(sourceFile.name);
  const currentRevision=sceneRevision===undefined?workspace?.current_scene_revision:sceneRevision;
  // A transient null observation hides Apply but does not revoke the server's
  // pinned preview. Confirmed scene, form and owner changes invalidate it even
  // if those values later return before a pending response arrives.
  const previewForm=JSON.stringify([selected,instance,...position,yaw]);
  const previewOwner=useRef({api,context,revision:currentRevision??null,form:previewForm,epoch:0});
  const previousPreviewOwner=previewOwner.current;
  if(previousPreviewOwner.api!==api||previousPreviewOwner.context!==context||previousPreviewOwner.form!==previewForm||
    !!currentRevision&&previousPreviewOwner.revision!==currentRevision){
    previewOwner.current={api,context,revision:currentRevision??previousPreviewOwner.revision,form:previewForm,epoch:previousPreviewOwner.epoch+1};
  }
  const previewEpoch=previewOwner.current.epoch;
  useEffect(()=>{setPreview(null);},[previewEpoch]);
  const canPlace=!!asset?.reusable&&!!currentRevision&&workspace?.current_scene_revision===currentRevision&&placementEnabled;
  const selectedPreview=preview&&preview.epoch===previewEpoch&&asset&&preview.asset===asset.asset_id&&preview.version===asset.version&&preview.revision===currentRevision?preview:null;
  const placementUnconfirmed=(tracking:PlacementCheck,message:string)=>{
    if(current()){setPlacementCheck({...tracking,message});setUnknown({requestId:null,message});}
  };
  const confirmPlacement=async(tracking:PlacementCheck)=>{
    const until=Date.now()+135000;
    let active=true,timer:ReturnType<typeof setTimeout>|undefined;
    const targetCurrent=()=>current()&&(sceneOwner.current===undefined||sceneOwner.current===tracking.parentRevision||sceneOwner.current===tracking.resultRevision);
    const stopped=()=>!active||!current();
    const observe=async()=>{
      let transaction:SceneEditTransaction|null=null;
      while(!stopped()&&Date.now()<until){
        if(!targetCurrent())throw new ApiError('delivery_unknown','The target scene changed while placement was pending. Inspect its saved transaction; do not Apply again.');
        if(transaction?.operation_id===tracking.operationId){
          if(['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(transaction.state)){
            setPlacementCheck(null);setUnknown(null);setPreview(null);
            throw new ApiError('library_placement_failed',transaction.error??`Placement ended in ${transaction.state}. No placement success is claimed.`);
          }
          if(transaction.state==='ENGINE_STATE_UNKNOWN')throw new ApiError('delivery_unknown',transaction.error??'Placement engine state is unknown. Inspect its saved transaction; do not Apply again.');
          if(transaction.state==='COMMITTED'&&transaction.current_frame&&transaction.durable_committed&&transaction.engine_acknowledged===true&&transaction.result_revision===tracking.resultRevision){
            const next=await api.workflow();
            if(stopped())return;
            if(!targetCurrent())throw new ApiError('delivery_unknown','The target scene changed while placement was pending. Inspect its saved transaction; do not Apply again.');
            const revision=next.site_draft?.revision??next.draft?.revision;
            if(revision===tracking.resultRevision){
              setPlacementCheck(null);setUnknown(null);setPreview(null);await onSceneApplied?.(next);
              if(!stopped())await refresh();return;
            }
          }
        }
        if(stopped())return;
        await new Promise(resolve=>setTimeout(resolve,750));
        if(stopped())return;
        try{transaction=await api.sceneEditTransaction();}
        catch(error){if(stopped())return;transaction=null;setPlacementCheck({...tracking,message:`Placement result check delayed: ${inputError(error)}. No Apply was repeated.`});}
      }
      if(!stopped())throw new ApiError('delivery_unknown','Placement was not confirmed within 135 seconds. Check this saved transaction; do not Apply again.');
    };
    try{
      await Promise.race([observe(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(new ApiError('delivery_unknown','Placement was not confirmed within 135 seconds. Check this saved transaction; do not Apply again.')),135000);})]);
    }catch(error){if(current()&&!(error instanceof ApiError&&error.code==='library_placement_failed'))placementUnconfirmed(tracking,`Placement outcome is unconfirmed: ${inputError(error)} No Apply was repeated.`);throw error;}
    finally{active=false;if(timer!==undefined)clearTimeout(timer);}
  };
  const applyPlacement=()=>void perform(async()=>{
    if(!selectedPreview)return;
    const {preview_id,preview_digest,operation,result_revision}=selectedPreview.value;
    const operationId=operation.operation_id;
    if(!preview_id||typeof operationId!=='string')throw new ApiError('library_preview_invalid','Create a fresh server-saved placement preview before Apply.');
    const tracking:PlacementCheck={operationId,parentRevision:selectedPreview.revision,resultRevision:result_revision,message:'Placement submitted · checking the engine ACK, saved revision and current frame.'};
    setPlacementCheck(tracking);
    let accepted:SceneEditTransaction|undefined;
    try{accepted=await api.applyLibraryPlacement(preview_id,preview_digest);}
    catch(error){
      if(!current())return;
      if(error instanceof ApiError&&error.code!=='delivery_unknown'){setPlacementCheck(null);setPreview(null);throw error;}
      placementUnconfirmed(tracking,'Placement response is unconfirmed. Checking the same saved operation; no Apply will be repeated.');
    }
    if(!current())return;
    if(accepted&&accepted.operation_id!==operationId){const message='Placement response belongs to a different operation. Inspect the saved transaction; do not Apply again.';placementUnconfirmed(tracking,message);throw new ApiError('delivery_unknown',message);}
    await confirmPlacement(tracking);
  });
  const uploadNote=<p>Asset work keeps the current Twin. Placement is a separate preview and Apply action. Existing scenes retain their saved asset versions.</p>;
  return <section className="library-workspace" aria-label="Library workspace">
    {!workspace&&<p role="status">{readPhase==='retrying'?'Rechecking saved Library assets · read only; one automatic retry.':
      readPhase==='failed'?'Library assets could not be read. Use Check saved Library results · read only.':'Reading Library assets and tool availability…'}</p>}
    {error&&error!==unknown?.message&&<p role="alert">{error}</p>}{workspace?.message&&<p role="status">{workspace.message}</p>}
    {unknown&&<p role="alert">{unknown.message}</p>}
    {placementCheck&&<section aria-label="Library placement transaction"><p role="status">{placementCheck.message}</p><small>Operation: {placementCheck.operationId}</small>
      {!busy&&<button onClick={()=>void perform(()=>confirmPlacement(placementCheck),true)}>Check placement result · read only</button>}</section>}
    <button disabled={busy} onClick={()=>{void refresh().then(next=>{if(!current()||!next)return;if(!unknown)setError(null);else if(unknown.requestId&&next.jobs.some(job=>job.request_id===unknown.requestId)){setUnknown(null);setError(null);}}).catch(e=>{if(current()){setReadPhase('failed');setError(inputError(e));}});}}>Check saved Library results · read only</button>
    {tab==='create'&&<><h3>Create a Library asset</h3>{uploadNote}<p>Uses the configured recipe model. CAD tools are optional. An asset reference is sent for this asset only.</p>
      <label className="library-field">Describe one asset<textarea aria-label="Describe Library asset" value={prompt} disabled={busy||!!unknown} onChange={e=>setPrompt(e.target.value)}/></label>
      <label className="library-field">Asset reference image (optional)<input aria-label="Asset reference image" type="file" accept={imageTypes.join(',')} disabled={busy||!!unknown} onChange={e=>{setReference(e.target.files?.[0]??null);e.target.value='';}}/></label>
      {reference&&<p>{reference.name} · asset_reference <button disabled={busy} onClick={()=>setReference(null)}>Remove asset reference</button></p>}
      <button disabled={busy||!!unknown||!prompt.trim()||!workspace} onClick={()=>void perform(async()=>{const ref=reference?await attachment(reference,'asset_reference'):undefined;await action({action:'create_recipe',request_id:crypto.randomUUID(),prompt,...(ref?{reference:ref}:{})});})}>Create asset</button></>}
    {tab==='import'&&<><h3>Import a Library asset</h3>{uploadNote}<p>CAD is an asset source. It is never sent as an environment photo. Optional conversion tools must be available before conversion can succeed.</p>
      <p>OBJ mesh files (.obj) can use the built-in local inspector. USD files (.usd, .usda, .usdc) require the optional USD inspection program.</p>
      <p role="status">{usdAvailable?`USD inspection available${usdInspector?.version?` · ${usdInspector.version}`:''}.`:usdInspector?.available?'USD inspection is disabled. Enable the USD inspector in Connections.':`USD inspection unavailable: ${usdInspector?.reason??'availability has not been confirmed. Check the USD inspector in Connections.'}`}
        {' '}USD support is limited to self-contained static meshes without external references, payloads or textures.</p>
      {workspace?.extensions.filter(extension=>extension.transport==='cli'&&!extension.available).map(extension=><p key={extension.extension_id}>{extension.title}: {extension.reason??'Optional program is unavailable'}</p>)}
      <label className="library-field">Asset source file<input aria-label="Library asset file" type="file" accept=".step,.stp,.iges,.igs,.usd,.usda,.usdc,.usdz,.obj,.stl,.ply,.gltf,.glb" disabled={busy||!!unknown} onChange={e=>{setSourceFile(e.target.files?.[0]??null);setSourceUnits('');setSourceUpAxis('');e.target.value='';}}/></label>
      {sourceFile&&<p>{sourceFile.name} · Library asset source · selected locally, not yet submitted <button disabled={busy} onClick={()=>setSourceFile(null)}>Remove asset source</button></p>}
      {selectedObj&&<fieldset disabled={busy||!!unknown}><legend>OBJ source coordinates</legend><p>OBJ does not declare units or an up axis. Choose the source values; no metre or axis assumption is made.</p>
        <label className="library-field">Source units<select aria-label="OBJ source units" value={sourceUnits} onChange={e=>setSourceUnits(e.target.value as typeof sourceUnits)}><option value="">Choose source units…</option><option value="m">Metres (m)</option><option value="cm">Centimetres (cm)</option><option value="mm">Millimetres (mm)</option></select></label>
        <label className="library-field">Source up axis<select aria-label="OBJ source up axis" value={sourceUpAxis} onChange={e=>setSourceUpAxis(e.target.value as typeof sourceUpAxis)}><option value="">Choose source up axis…</option><option value="Y">Y up</option><option value="Z">Z up</option></select></label></fieldset>}
      <label className="library-field">Source / provenance<input aria-label="Asset source provenance" value={source} disabled={busy||!!unknown} onChange={e=>setSource(e.target.value)}/></label>
      <label className="library-field">License / permitted use<input aria-label="Asset license" value={license} disabled={busy||!!unknown} onChange={e=>setLicense(e.target.value)}/></label>
      <button disabled={busy||!!unknown||!sourceFile||!source.trim()||!license.trim()||!workspace||selectedUsd&&!usdAvailable||selectedObj&&(!sourceUnits||!sourceUpAxis)} onClick={()=>void perform(async()=>{if(sourceFile){await action({action:'import_asset',request_id:crypto.randomUUID(),attachment:await attachment(sourceFile,'asset_source'),source,license,...(selectedObj&&sourceUnits&&sourceUpAxis?{source_units:sourceUnits,source_up_axis:sourceUpAxis}:{})});if(current())onImportSubmitted?.();}})}>Import asset</button></>}
    {tab==='assets'&&<><h3>My assets</h3>{uploadNote}<div className="model-library-body"><nav aria-label="Saved Library assets">{assets.map(item=><button key={`${item.asset_id}/${item.version}`} aria-pressed={selected===`${item.asset_id}/${item.version}`} onClick={()=>{setSelected(`${item.asset_id}/${item.version}`);setInstance(`asset_${crypto.randomUUID().replaceAll('-','').slice(0,12)}`);
      if(!positionEdited.current[2])setPosition(values=>[values[0],values[1],String(item.kind==='recipe'?0:item.dimensions_m[2]/2)]);
    }}>{item.title}<small>{item.kind} · {item.version.slice(0,12)}</small></button>)}{workspace&&!assets.length&&<p>No registered assets yet. Create or import an asset, then register its validated result.</p>}</nav>
      <article>{asset?<><h4>{asset.title}</h4>{asset.preview_parts&&<ModelPreview model={{model_id:asset.asset_id,title:asset.title,kind:asset.kind,family:'common',environments:[],tool:'place_model_recipe',dimensions_m:{default:asset.dimensions_m},preview_parts:asset.preview_parts}}/>}
        <p>Source: {asset.source_name} · {asset.origin}</p><p>Dimensions: {asset.dimensions_m.join(' × ')} m · {asset.up_axis} up</p><p>Visual: {asset.visual_status} · Physics: {asset.physics_status}. Physical certification is not implied.</p>
        <p>License: {asset.license}</p><details><summary>Immutable asset version</summary><p>Asset: {asset.asset_id}</p><p>Version: {asset.version}</p><p>Source SHA: {asset.source_sha256}</p></details>
        {!asset.reusable&&<p>This preserved asset is unavailable for new placement.</p>}
        {!currentRevision&&<p>Create or reopen a Twin before placing this asset.</p>}
        {currentRevision&&!placementEnabled&&<p>Finish the current action and wait for the connected, idle Isaac engine before placement.</p>}
        <p>{asset.kind==='recipe'?'Recipe placement uses the XY centre at floor level (Z = 0). Arbitrary elevation is not supported.':`Imported mesh assets support independent floor placement only. Centre Z must equal half the asset height (${asset.dimensions_m[2]/2} m). Elevated or on-furniture placement is not supported.`}</p>
        <fieldset disabled={busy||!!unknown||!canPlace}><legend>Place an instance in the current Twin</legend><label className="library-field">Instance ID<input aria-label="Asset instance ID" value={instance} onChange={e=>setInstance(e.target.value)}/></label>
          <div className="library-position">{['X','Y','Z'].map((axis,i)=><label key={axis}>{axis} (m)<input aria-label={`Asset ${axis} position`} type="number" step="any" value={position[i]} onChange={e=>{positionEdited.current[i]=true;setPosition(values=>values.map((value,j)=>i===j?e.target.value:value));}}/></label>)}<label>Yaw (deg)<input aria-label="Asset yaw" type="number" step="any" value={yaw} onChange={e=>setYaw(e.target.value)}/></label></div>
          <button disabled={busy||!!unknown||!canPlace} onClick={()=>void perform(async()=>{const xyz=position.map(Number),angle=Number(yaw);if(!instance.trim()||position.some(value=>!value.trim())||!yaw.trim()||!xyz.every(Number.isFinite)||!Number.isFinite(angle))throw new Error('Enter an instance ID and finite placement coordinates.');
            const requested={asset:asset.asset_id,version:asset.version,revision:currentRevision!,epoch:previewEpoch};const result=await action({action:'preview_placement',asset_id:requested.asset,version:requested.version,expected_scene_revision:requested.revision,instance_id:instance,position_m:xyz as [number,number,number],yaw_deg:angle,request_id:crypto.randomUUID()});
            if(current()&&previewOwner.current.epoch===requested.epoch&&result.placement_preview)setPreview({value:result.placement_preview,...requested});})}>Preview asset placement</button></fieldset>
        {selectedPreview&&<section aria-label="Library placement preview"><h4>Placement proposal</h4><p>{Object.keys(selectedPreview.value.affected_after).length} affected objects · {selectedPreview.value.preserved_object_count} preserved. Review the position before Apply.</p>
          <p>Asset {selectedPreview.asset} · version {selectedPreview.version.slice(0,12)} · scene {selectedPreview.revision.slice(0,12)}</p>
          {!selectedPreview.value.preview_id&&<p>Create a fresh server-saved preview before Apply.</p>}
          <button disabled={busy||!!unknown||!canPlace||!selectedPreview.value.preview_id} onClick={applyPlacement}>Apply asset placement</button>
          <button disabled={busy} onClick={()=>setPreview(null)}>Cancel placement</button></section>}
      </>:<p>{workspace?'Select an immutable asset version to inspect or place it.':'Saved Library assets have not been confirmed yet.'}</p>}</article></div></>}
    {tab==='connections'&&<><h3>Connections and tools</h3><p>Optional tools do not block built-in home generation. External programs keep their own installation and license.</p>
      {(workspace?.extensions??[]).map(extension=><ExtensionCard key={extension.extension_id} extension={extension} busy={busy||!!unknown} act={act}/>)}
      <h4>Run a registered tool</h4><label className="library-field">Tool<select aria-label="Library tool" disabled={busy||!!unknown} value={toolId} onChange={e=>{setToolId(e.target.value);setToolValues({});setToolFile(null);}}><option value="">Choose a tool…</option>{availableTools.map(({extension,tool})=><option key={`${extension.extension_id}/${tool.tool_id}`} value={tool.tool_id}>{tool.title}{!extension.available||!extension.enabled?' · unavailable':''}</option>)}</select></label>
      {chosenTool&&<><p>{chosenTool.extension.reason}</p><ToolFields schema={chosenTool.tool.input_schema} values={toolValues} change={(key,value)=>setToolValues(values=>({...values,[key]:value}))} disabled={busy||!!unknown}/>
        <label className="library-field">Tool input file (optional)<input aria-label="Library tool input file" type="file" disabled={busy||!!unknown} onChange={e=>{setToolFile(e.target.files?.[0]??null);e.target.value='';}}/></label>{toolFile&&<p>{toolFile.name} · tool input, selected locally</p>}
        <button disabled={busy||!!unknown||!chosenTool.extension.available||!chosenTool.extension.enabled} onClick={()=>void perform(async()=>{const file=toolFile?await attachment(toolFile,'tool_input'):undefined;await action({action:'run_tool',request_id:crypto.randomUUID(),tool_id:chosenTool.tool.tool_id,inputs:toolInputs(chosenTool.tool.input_schema,toolValues),...(file?{attachment:file}:{})});})}>Run {chosenTool.tool.title}</button></>}
    </>}
    {!!workspace?.jobs.length&&<section aria-label="Library work"><h3>Library work</h3>{workspace.jobs.map(job=><JobCard key={job.job_id} job={job} busy={busy||!!unknown} act={act}/>)}</section>}
  </section>;
}
