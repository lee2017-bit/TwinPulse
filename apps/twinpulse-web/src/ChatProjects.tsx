// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import {flushSync} from 'react-dom';
import { ApiError, TwinPulseApi } from './api';
import type { ProjectCatalogState } from './types';

export function ChatProjects({api, launcherReady, operationBusy, report, advanced, currentProject, currentConversation, openCurrent, newChatRequest=0, workspaceRequest=0, apiReady=true, activityChanged, onProjectChanged, onNewChatReady}: {
  api:TwinPulseApi; launcherReady:boolean; operationBusy:boolean; report:(reason:string)=>void; advanced:()=>void;
  currentProject?:string; openCurrent?:()=>void; newChatRequest?:number; workspaceRequest?:number;  // robot workspace from the current generated Twin
  currentConversation?:{display_name:string;message_count:number;last_message_at:string|null};
  apiReady?:boolean;
  activityChanged?:(activity:{busy:boolean;message:string|null})=>void;
  onProjectChanged?:(selection:{project_id:string;context_id?:string})=>void|Promise<void>;
  onNewChatReady?:()=>void;
}) {
  const [catalog,setCatalog]=useState<ProjectCatalogState|null>(null);
  const [name,setName]=useState('');
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState<string|null>(null);
  const [switching,setSwitching]=useState(false);
  const [query,setQuery]=useState('');
  const [manageOpen,setManageOpen]=useState(false);
  const [listReadError,setListReadError]=useState<{api:TwinPulseApi;context:string;message:string}|null>(null);
  const readOwner=useRef({api,context:api.context});readOwner.current={api,context:api.context};
  const alive=useRef(true);
  const lock=useRef(false);
  const lastNewChatRequest=useRef(0);const lastWorkspaceRequest=useRef(0);
  const newChatAttempt=useRef<{target:string;created:boolean}|null>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const readProjects=async(active=()=>true)=>{
    const context=api.context;
    const current=()=>alive.current&&active()&&readOwner.current.api===api&&readOwner.current.context===context&&api.context===context;
    try{const value=await api.projects();if(current()){setCatalog(value);setListReadError(null);}}
    catch(error){if(current())setListReadError({api,context,message:error instanceof Error?error.message:'Project inventory unavailable.'});}
  };
  useEffect(()=>{activityChanged?.({busy:busy||switching,message:result});},[busy,switching,result,activityChanged]);
  useEffect(()=>{let active=true;if(!apiReady||typeof api.projects!=='function')return;
    void readProjects(()=>active);
    return()=>{active=false;};},[api,apiReady,api.context]);
  const create=async()=>{
    if(!apiReady||lock.current || operationBusy || switching || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name) || name==='default')return;
    const target=name;lock.current=true;activityChanged?.({busy:true,message:'Creating project…'});setBusy(true);setResult('Creating project…');
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
    lock.current=true;flushSync(()=>{activityChanged?.({busy:true,message:`Opening ${project}…`});setBusy(true);setSwitching(true);setResult(`Opening ${project}…`);});
    try {const selected=await api.switchProject(project);
      if(selected.status==='switched'){
        await onProjectChanged?.(selected);
        setCatalog(previous=>previous?{...previous,active_project_id:project,projects:previous.projects.map(row=>({...row,active:row.project_id===project}))}:previous);
        setSwitching(false);setResult(`Opened ${project}. Saved conversation is ready.`);
      }else setResult('Project switch requested. Waiting for the selected conversation.');}
    catch(error){
      if(error instanceof ApiError && error.code!=='delivery_unknown'){report(error.message);setSwitching(false);setResult(null);}
      else {setSwitching(true);setResult('Project switch response unknown. Check the saved outcome before another request.');}
    } finally{lock.current=false;setBusy(false);}
  };
  const newChat=async(robotWorkspace=false)=>{
    if(!apiReady||lock.current||operationBusy||switching||!launcherReady||typeof api.createProject!=='function')return;
    const attempt=newChatAttempt.current??{target:`${robotWorkspace?'robot':'chat'}_${Date.now().toString(36)}_${crypto.randomUUID().slice(0,8)}`,created:false};
    newChatAttempt.current=attempt;
    const target=attempt.target;
    lock.current=true;flushSync(()=>{activityChanged?.({busy:true,message:'Preparing a new chat…'});setBusy(true);setResult('Preparing a new chat…');});
    try {
      if(!attempt.created){const created=robotWorkspace?await api.createRobotWorkspace(target,crypto.randomUUID()):await api.createProject(target);setCatalog(created.catalog);attempt.created=true;}
      setSwitching(true);setResult('Opening a new chat…');
      const selected=await api.switchProject(target);
      if(selected.status==='switched'){
        await onProjectChanged?.(selected);
        onNewChatReady?.();
        setCatalog(previous=>previous?{...previous,active_project_id:target,projects:previous.projects.map(row=>({...row,active:row.project_id===target}))}:previous);
        setSwitching(false);setResult(robotWorkspace?'Robot workspace ready.':'New chat ready.');
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
  useEffect(()=>{let active=true;if(newChatRequest>lastNewChatRequest.current){
    // Run outside the effect commit: the transition must synchronously clean up
    // child observers before the first POST, including home-screen New chat.
    queueMicrotask(()=>{if(active&&newChatRequest>lastNewChatRequest.current){lastNewChatRequest.current=newChatRequest;void newChat();}});
    }return()=>{active=false;};},[newChatRequest]);
  useEffect(()=>{let active=true;if(workspaceRequest>lastWorkspaceRequest.current){
    queueMicrotask(()=>{if(active&&workspaceRequest>lastWorkspaceRequest.current){lastWorkspaceRequest.current=workspaceRequest;void newChat(true);}});
    }return()=>{active=false;};},[workspaceRequest]);
  const reason=!apiReady?'Connecting to the App before loading saved conversations.':operationBusy?'Finish the active operation before switching projects.':!launcherReady?'Wait for Isaac startup before opening another project.':switching?'Opening the selected conversation.':null;
  const currentReadError=listReadError?.api===api&&listReadError.context===api.context?listReadError.message:null;
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
    {currentReadError&&<div role="alert" aria-label="Saved project list read issue"><p>Saved project list could not be refreshed: {currentReadError} The last list is retained.</p>
      <button type="button" disabled={!apiReady||busy} onClick={()=>void readProjects()}>Retry project list · read only</button></div>}
    <section className="chat-project-tools"><button type="button" aria-expanded={manageOpen} onClick={()=>setManageOpen(!manageOpen)}>Manage projects</button>
    {manageOpen&&<div>
    <button disabled={!apiReady||busy||typeof api.projects!=='function'} onClick={()=>void readProjects()}>Refresh projects</button>
    <form onSubmit={event=>{event.preventDefault();void create();}}><label htmlFor="chat-project-name">New project name</label>
      <input id="chat-project-name" value={name} maxLength={64} onChange={event=>setName(event.target.value)} placeholder="my_room" autoComplete="off"/>
      <small>Lowercase letters, digits, underscore or hyphen. Creates a separate empty project, never overwrites the current scene.</small>
      <button type="submit" disabled={!apiReady||busy || operationBusy || switching || name==='default' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)}>Create project</button></form>
    <button onClick={advanced}>Advanced tools</button></div>}</section>
    {result && <p role="status">{result}</p>}
  </aside>;
}
