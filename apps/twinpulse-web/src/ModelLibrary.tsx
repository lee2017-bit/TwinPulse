// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {LibraryModel} from './model-library-types';
import {LibraryWorkspace,type LibraryWorkspaceTab} from './LibraryWorkspace';
import type {WorkflowState} from './types';
import './model-library.css';

export function ModelPreview({model}:{model:LibraryModel}){
  const parts=model.preview_parts;
  if(!parts?.length)return <p>Built-in model · view its instance in the Twin after generation.</p>;
  const w=model.dimensions_m.default?.[0]??1,d=model.dimensions_m.default?.[1]??1,h=model.dimensions_m.default?.[2]??1;
  const scale=210/Math.max(w+d,h*1.3);
  const project=(p:number[])=>[220+(p[0]-p[1])*scale,310-(p[2]+(p[0]+p[1])*.3)*scale];
  const faces=parts.slice().sort((a,b)=>(b.center[0]+b.center[1])-(a.center[0]+a.center[1])).flatMap(part=>{
    const corners=Array.from({length:8},(_,n)=>project(part.center.map((v,i)=>v+part.size[i]*((n>>i)&1? .5:-.5))));
    return [[0,1,5,4],[0,2,6,4],[4,5,7,6]].map((indexes,i)=><polygon key={`${part.id}:${i}`}
      points={indexes.map(n=>corners[n].join(',')).join(' ')} fill={part.material==='wood'?['#b38959','#92734e','#cfa572'][i]:
        part.material==='dark'?['#3f4650','#262e39','#5e6772'][i]:['#dce2e7','#b5c0c9','#f3f5f7'][i]}
      stroke="#6a7885" strokeWidth="0.6"><title>{part.id}{part.support_top?' · usable top surface':''}</title></polygon>);
  });
  return <figure><svg viewBox="0 0 440 350" role="img" aria-label={`${model.title??model.kind} compiled model preview`}>{faces}</svg>
    <figcaption>Compiled catalog geometry · not a live Isaac frame or photo-quality check.</figcaption></figure>;
}

export function ModelLibrary({api,close,useModel,initialImport,initialReference,initialPrompt,sceneRevision,onSceneApplied,onImportSubmitted,placementEnabled}:{api:TwinPulseApi;close:()=>void;useModel:(model:LibraryModel)=>void;initialImport?:File|null;initialReference?:File|null;initialPrompt?:string;sceneRevision?:string|null;onSceneApplied?:(state:WorkflowState)=>void|Promise<void>;onImportSubmitted?:()=>void;placementEnabled?:boolean}){
  const [tab,setTab]=useState<'catalog'|LibraryWorkspaceTab>(initialImport?'import':initialReference?'create':'catalog');
  const [workspaceOpened,setWorkspaceOpened]=useState(!!initialImport||!!initialReference);
  const [models,setModels]=useState<LibraryModel[]>([]),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(true);
  const [query,setQuery]=useState(''),[family,setFamily]=useState('all'),[selected,setSelected]=useState<string|null>(null),[refresh,setRefresh]=useState(0);
  useEffect(()=>{let cancelled=false;setLoading(true);setError(null);
    void api.modelLibrary().then(result=>{if(!cancelled)setModels(result.models);}).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'Library could not be read');})
      .finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[api,refresh]);
  const filtered=models.filter(m=>(family==='all'||m.family===family||m.environments.includes(family))&&
    `${m.title??''} ${m.kind} ${m.model_id} ${m.origin??'builtin'}`.toLowerCase().includes(query.toLowerCase()));
  const current=models.find(m=>m.model_id===selected);
  return <div className="model-library-backdrop"><section className="model-library" role="dialog" aria-modal="true" aria-label="Model library">
    <header><h2>Model library</h2><button onClick={close}>Close library</button></header>
    <div className="library-tabs" role="tablist" aria-label="Library sections">{([['catalog','Catalog'],['create','Create asset'],['import','Import asset'],['assets','My assets'],['connections','Connections']] as const).map(([id,label])=>
      <button key={id} role="tab" aria-selected={tab===id} aria-controls={`library-${id}`} onClick={()=>{setTab(id);if(id!=='catalog')setWorkspaceOpened(true);}}>{label}</button>)}</div>
    <div hidden={tab!=='catalog'} id="library-catalog" role="tabpanel" aria-label="Catalog">
    <p>Search reusable models. Missing furniture can be created by the configured planner during scene generation; no separate price or registration approval.</p>
    <p>Local generated models are parameter-checked recipes, not photo reconstruction or physical-safety certification. Existing scenes pin their exact model version.</p>
    <div className="model-library-controls"><input aria-label="Search models" placeholder="Search models…" value={query} onChange={e=>setQuery(e.target.value)}/>
      <select aria-label="Model family" value={family} onChange={e=>setFamily(e.target.value)}><option value="all">All families</option><option value="home">Home</option><option value="warehouse">Warehouse</option><option value="common">Common</option></select>
      <button onClick={()=>setRefresh(v=>v+1)} disabled={loading}>Refresh library</button></div>
    {loading&&<p role="status">Reading the local library…</p>}{error&&<p role="alert">{error}</p>}
    <div className="model-library-body"><nav aria-label="Library models">{filtered.map(m=><button key={m.model_id} aria-pressed={selected===m.model_id} onClick={()=>setSelected(m.model_id)}>
      <strong>{m.title??m.kind.replaceAll('_',' ')}</strong><small>{m.origin==='model_generated'?(m.reusable===false?'AI-created · revision needed':'AI-created · geometry checked'):'Built-in'} · {m.family}</small></button>)}
      {!loading&&!filtered.length&&<p>No matching reusable model. Describe the missing furniture in a new scene request.</p>}</nav>
      <article>{current?<><h3>{current.title??current.kind}</h3><ModelPreview model={current}/>
        <p><code>{current.model_id}</code></p><p>Status: {current.status??'builtin'} · photo/physical validation not implied.</p>
        <p>Default size: {current.dimensions_m.default?.join(' × ')??'Depends on its catalog parameters'} m</p>
        {current.parameters&&<dl>{current.parameters.map(p=><div key={p.name}><dt>{p.name}</dt><dd>{p.minimum}–{p.maximum}; default {p.default}</dd></div>)}</dl>}
        <p>Support surfaces: {current.support_parts?.join(', ')||'Use its declared catalog placement capabilities'}</p>
        {current.origin==='model_generated'&&<><p>Generator: {current.generator_model}</p><p>Created: {current.created_at_utc}</p>
          <p>Request: <code>{current.generation_request_id}</code></p><details><summary>Version and validation</summary><p>Recipe SHA: {current.recipe_sha256}</p>
            <p>Compiler: {current.interpreter_version}</p><p>{current.validation_scope}</p></details></>}
        {current.reusable===false&&<p role="alert">Preserved historical model · unavailable for new reuse. {current.reuse_problem} Existing pinned scenes remain unchanged.</p>}
        <button disabled={current.reusable===false} onClick={()=>useModel(current)}>Use this model in chat</button><p>This fills a request; it does not overwrite a saved scene or start an API call.</p>
      </>:<p>Select a model to inspect its geometry and adjustable parameters.</p>}</article></div>
    </div>
    <div hidden={tab==='catalog'} id={`library-${tab}`} role="tabpanel" aria-label={tab==='catalog'?'Library workspace':tab}>
      {workspaceOpened&&<LibraryWorkspace api={api} tab={tab==='catalog'?'assets':tab} initialImport={initialImport} initialReference={initialReference} initialPrompt={initialPrompt}
        sceneRevision={sceneRevision} onSceneApplied={onSceneApplied} onImportSubmitted={onImportSubmitted} placementEnabled={placementEnabled}/>}
    </div>
  </section></div>;
}
