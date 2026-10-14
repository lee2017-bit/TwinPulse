// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import { ApiError, TwinPulseApi } from './api';
import type { ProjectCatalogState } from './types';

export function ChatProjects({api, launcherReady, operationBusy, report, advanced, currentProject, currentConversation, openCurrent, newChatRequest=0, apiReady=true, activityChanged, onProjectChanged}: {
  api:TwinPulseApi; launcherReady:boolean; operationBusy:boolean; report:(reason:string)=>void; advanced:()=>void;
  currentProject?:string; openCurrent?:()=>void; newChatRequest?:number;
  currentConversation?:{display_name:string;message_count:number;last_message_at:string|null};
  apiReady?:boolean;
  activityChanged?:(activity:{busy:boolean;message:string|null})=>void;
  onProjectChanged?:(selection:{project_id:string;context_id?:string})=>void|Promise<void>;
}) {
  const [catalog,setCatalog]=useState<ProjectCatalogState|null>(null);
  const [name,setName]=useState('');
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState<string|null>(null);
  const [switching,setSwitching]=useState(false);
  const [query,setQuery]=useState('');
  const [manageOpen,setManageOpen]=useState(false);
  const lock=useRef(false);
  const lastNewChatRequest=useRef(0);
  const newChatAttempt=useRef<{target:string;created:boolean}|null>(null);
  useEffect(()=>{activityChanged?.({busy:busy||switching,message:result});},[busy,switching,result,activityChanged]);
  useEffect(()=>{let active=true;if(!apiReady||typeof api.projects!=='function')return;
    void api.projects().then(value=>{if(active)setCatalog(value);})
    .catch(error=>{if(active)report(error instanceof Error ? error.message : 'Project inventory unavailable.');});
    return()=>{active=false;};},[api,apiReady]);
  const create=async()=>{
    if(!apiReady||lock.current || operationBusy || switching || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name) || name==='default')return;
    const target=name;lock.current=true;setBusy(true);setResult('Creating project…');
    try {const value=await api.createProject(target);setCatalog(value.catalog);setName('');
      setResult(`Created ${target}. Choose Open to use this project.`);
    } catch(error) {
      if(error instanceof ApiError && error.code!=='delivery_unknown') {report(error.message);setResult(null);}
      else {try {const saved=await api.projects();setCatalog(saved);
          setResult(saved.projects.some(p=>p.project_id===target)
            ? `${target} is present in the saved catalog. No creation was repeated; inspect or open it.`
            : 'Creation outcome not confirmed. No automatic retry; refresh the project list before another attempt.');
        } catch {setResult('Creation outcome unknown. No automatic retry; check the saved project list.');}}
    } finally {lock.current=false;setBusy(false);}
  };
  const open=async(project:string)=>{
    if(project===currentProject){openCurrent?.();return;}
    if(!apiReady||lock.current || operationBusy || !launcherReady || switching)return;
    lock.current=true;setBusy(true);setSwitching(true);setResult(`Opening ${project}…`);
    try {const selected=await api.switchProject(project);
      if(selected.status==='switched'){
        await onProjectChanged?.(selected);
        setCatalog(previous=>previous?{...previous,active_project_id:project,projects:previous.projects.map(row=>({...row,active:row.project_id===project}))}:previous);
        setSwitching(false);setResult(`Opened ${project}. Saved conversation is ready.`);
      }else setResult('Project switch requested. Waiting for the selected conversation.');}
    catch(error){
      if(error instanceof ApiError && error.code!=='delivery_unknown'){report(error.message);setSwitching(false);setResult(null);}
      else {setSwitching(false);setResult('Project switch response unknown. Check the saved outcome before another request.');}
    } finally{lock.current=false;setBusy(false);}
  };
  const newChat=async()=>{
    if(!apiReady||lock.current||operationBusy||switching||!launcherReady||typeof api.createProject!=='function')return;
    const attempt=newChatAttempt.current??{target:`chat_${Date.now().toString(36)}_${crypto.randomUUID().slice(0,8)}`,created:false};
    newChatAttempt.current=attempt;
    const target=attempt.target;
    let switchRequested=false;
    lock.current=true;setBusy(true);setResult('Preparing a new chat…');
    try {
      if(!attempt.created){const created=await api.createProject(target);setCatalog(created.catalog);attempt.created=true;}
      setSwitching(true);setResult('Opening a new chat…');
      switchRequested=true;const selected=await api.switchProject(target);
      if(selected.status==='switched'){
        await onProjectChanged?.(selected);
        setCatalog(previous=>previous?{...previous,active_project_id:target,projects:previous.projects.map(row=>({...row,active:row.project_id===target}))}:previous);
        setSwitching(false);setResult('New chat ready.');
        newChatAttempt.current=null;
      }
    } catch(error) {
      if(error instanceof ApiError&&error.code!=='delivery_unknown'){
        setSwitching(false);setResult(error.message);report(error.message);
      } else {
        // Even a visible catalog entry is not permission to repeat an unknown switch.
        setSwitching(true);setResult('New chat outcome is unconfirmed. No automatic retry. Check startup status or the saved conversation list.');
        try{setCatalog(await api.projects());}catch{/* Preserve the uncertain request. */}
      }
    } finally{lock.current=false;setBusy(false);}
  };
  useEffect(()=>{if(newChatRequest>lastNewChatRequest.current){lastNewChatRequest.current=newChatRequest;void newChat();}},[newChatRequest]);
  const reason=!apiReady?'Connecting to the App before loading saved conversations.':operationBusy?'Finish the active operation before switching projects.':!launcherReady?'Wait for Isaac startup before opening another project.':switching?'Opening the selected conversation.':null;
  const filtered=(catalog?.projects??[]).map(project=>project.active&&currentConversation?{...project,...currentConversation}:project)
    .filter(project=>`${project.display_name??''} ${project.project_id}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a,b)=>(Date.parse(b.last_message_at??'')||0)-(Date.parse(a.last_message_at??'')||0));
  const row=(project:ProjectCatalogState['projects'][number])=><li key={project.project_id}>
    <button className="chat-project-link" aria-label={`Open ${project.project_id}`} aria-current={project.active?'page':undefined}
      disabled={busy||switching||(!project.active&&(!!reason||!['empty','review_required'].includes(project.status)))}
      title={project.active?'Open the current saved conversation':reason??project.project_id}
      onClick={()=>void open(project.project_id)}>
      <strong>{project.display_name??project.project_id}</strong><small>{project.message_count?`${project.message_count} messages · `:''}{project.active?'Current project':project.status.replaceAll('_',' ')}</small>
    </button>
  </li>;
  return <aside className="chat-projects" aria-label="Projects and saved conversations">
    <h2>Chats & projects</h2>
    <button className="chat-new-conversation" disabled={busy||!!reason||typeof api.createProject!=='function'} onClick={()=>void newChat()}>＋ New chat</button>
    <input aria-label="Search conversations and projects" type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search conversations"/>
    <h3>Recent chats</h3><ul>{filtered.filter(project=>!!project.message_count).map(row)}</ul>
    <h3>Projects</h3><ul>{filtered.filter(project=>!project.message_count).map(row)}</ul>
    {!catalog&&currentProject&&<button onClick={openCurrent}>Open current chat · {currentProject}</button>}
    {catalog?.truncated&&<small>List display limit reached. Original projects are not deleted.</small>}
    {catalog&&filtered.length===0&&<p>No matching conversations.</p>}
    {reason && <small>{reason}</small>}
    <section className="chat-project-tools"><button type="button" aria-expanded={manageOpen} onClick={()=>setManageOpen(!manageOpen)}>Manage projects</button>
    {manageOpen&&<div>
    <button disabled={!apiReady||busy||typeof api.projects!=='function'} onClick={()=>void api.projects().then(setCatalog).catch(error=>report(error.message))}>Refresh projects</button>
    <form onSubmit={event=>{event.preventDefault();void create();}}><label htmlFor="chat-project-name">New project name</label>
      <input id="chat-project-name" value={name} maxLength={64} onChange={event=>setName(event.target.value)} placeholder="my_room" autoComplete="off"/>
      <small>Lowercase letters, digits, underscore or hyphen. Creates a separate empty project, never overwrites the current scene.</small>
      <button type="submit" disabled={!apiReady||busy || operationBusy || switching || name==='default' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)}>Create project</button></form>
    <button onClick={advanced}>Advanced tools</button></div>}</section>
    {result && <p role="status">{result}</p>}
  </aside>;
}
