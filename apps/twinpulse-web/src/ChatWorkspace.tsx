// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { Activity, useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ApiError, fileToBase64, TwinPulseApi } from './api';
import { isConversationStatusRequest, isConversationChoiceRequest, isConversationStopRequest } from './conversation-intent';
import {clipboardImage} from './clipboard-image';
import { ChatProjects } from './ChatProjects';
import { IsaacConnectionStatus } from './IsaacConnectionStatus';
import {AuthenticatedConversationImage} from './AuthenticatedConversationImage';
import { ExecutionDiagnostics } from './ExecutionDiagnostics';
import { ApiKeySettings } from './ApiKeySettings';
import {RobotRegistry} from './RobotRegistry';
import { ModelLibrary } from './ModelLibrary';
import {isLibrarySource} from './library-workspace-types';
import {isEnvironmentSource} from './environment-types';
import {EnvironmentImport} from './EnvironmentImport';
import { TwinViewport, generationActivityLabel, generationIsIncomplete, generationRetentionRevalidationLabel, inventoryCheckpointSaved, savedGenerationScene, type ViewerFault } from './TwinViewport';
import {RobotFleet} from './RobotFleet';
import type {RobotFleetState} from './robot-fleet-types';
import { SimulationRunCard } from './SimulationRunCard';
import { ChatRoomBuild } from './ChatRoomBuild';
import { ChatInspectionBuild } from './ChatInspectionBuild';
import { CurrentGoalReview,useRecentMissionTelemetry } from './CurrentGoalReview';
import {nativeCleanupLines} from './mission-cleanup';
import { RoomInventory } from './RoomInventory';
import { SceneSensorFeedback } from './SceneSensorFeedback';
import { DeviceLogStorage } from './DeviceLogStorage';
import { ChatRobotStatus,ChatRobotStops } from './ChatRobotStatus';
import type { ConversationAction, ConversationState, QuestionCard, ResumeSceneAction,RobotCheckAction } from './conversation-types';
import type {SimulationReview} from './conversation-types';
import type { ProductState, SupervisorState, WorkflowState } from './types';
import './chat.css';

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'The operation could not be completed.';
}

export interface ConversationTurn {id:string;messages:ConversationState['messages'];cards:QuestionCard[]}

export function generationResumePresentation(job:NonNullable<ConversationState['generation']>){
  // The retained budget stop is the host continuation gate. Generic public
  // provider errors can wrap a more specific cancellation or output-length stop.
  const stop=job.progress?.budget?.stop_reason;
  const reason=typeof stop==='string'&&stop?stop:job.error?.code==='generation_cancelled'?'GENERATION_CANCELLED':
    job.error?.code??(job.state==='cancelled'?'GENERATION_CANCELLED':undefined);
  if(reason==='GENERATION_CANCELLED'||reason==='PROVIDER_OUTPUT_TRUNCATED')
    return {label:'Continue unfinished work',explanation:'The host checks the retained checkpoint and remaining original allowance before continuing. No automatic restart or budget reset.'};
  if(reason==='NEEDS_REQUEST_BUDGET')
    return {label:'Review resume options',explanation:'The host will check the saved stage and remaining allowance before continuing. No automatic restart or budget reset.'};
  if(['GENERATION_LOCAL_STATE_FAILED','REPAIR_STALLED','REPAIR_LIMIT_REACHED','QUALITY_REPAIR_LIMIT_REACHED',
    'REQUEST_LIMIT_REACHED','NEEDS_TIME_BUDGET','REMOTE_OUTCOME_UNKNOWN','VALIDATION_EVIDENCE_FAILED'].includes(reason??''))
    return {label:'Recheck retained draft · no new model requests',explanation:'This stop permits local revalidation of retained data only. It may end with the same failure; request, repair and time limits are not reset.'};
  return {label:'Recheck retained draft',explanation:'Resume eligibility is not confirmed from this saved status. The host will check the retained checkpoint; no automatic restart or budget reset.'};
}

export function generationSourceAttachment(state:Pick<ConversationState,'messages'|'generation'>){
  const job=state.generation;
  // An explicit origin is authoritative even when it has no photo or is no
  // longer in the bounded history. Never borrow another request's attachment.
  const source=job?.origin_message_id?state.messages.find(message=>message.role==='user'&&message.message_id===job.origin_message_id):
    job?state.messages.find(message=>message.role==='user'&&message.operation_id===job.operation_id):
    state.messages.slice().reverse().find(message=>message.role==='user');
  return source?.attachments.find(attachment=>!!attachment.preview_url);
}

// Explicit reply links keep late tool replies under the request that started them.
// Legacy rows retain their chronological position; orphan cards are never appended
// to the active turn merely because their message is absent from a bounded history.
export function conversationTurns(state:Pick<ConversationState,'messages'|'cards'>):ConversationTurn[] {
  const messages=new Map(state.messages.map(message=>[message.message_id,message]));
  const roots=new Map<string,string>();
  let previous:string|null=null;
  const root=(id:string,seen=new Set<string>()):string|null=>{
    const message=messages.get(id);if(!message||seen.has(id))return null;
    if(roots.has(id))return roots.get(id)!;
    seen.add(id);
    return message.reply_to?root(message.reply_to,seen):message.role==='user'?id:null;
  };
  for(const message of state.messages){
    const linked=root(message.message_id);
    const operation=message.operation_id?state.messages.find(row=>row.role==='user'&&row.operation_id===message.operation_id):undefined;
    const owner:string=linked??operation?.message_id??previous??message.message_id;
    roots.set(message.message_id,owner);
    if(message.role==='user')previous=owner;
  }
  const turns:ConversationTurn[]=[];
  for(const message of state.messages){
    const id=roots.get(message.message_id)!;
    let turn=turns.find(row=>row.id===id);
    if(!turn){turn={id,messages:[],cards:[]};turns.push(turn);}
    turn.messages.push(message);
  }
  for(const card of state.cards){
    const linked=roots.get(card.reply_to??card.message_id);
    const operation=card.operation_id&&state.messages.find(row=>row.operation_id===card.operation_id);
    let turn=turns.find(row=>row.id===(linked??(operation?roots.get(operation.message_id):null)));
    if(!turn){
      const timestamp=Date.parse(card.created_at??'');
      const index=Number.isFinite(timestamp)?turns.findIndex(row=>Date.parse(row.messages[0]?.created_at??'')>timestamp):0;
      turn={id:`legacy-card:${card.id}`,messages:[],cards:[]};
      turns.splice(index<0?turns.length:index,0,turn);
    }
    turn.cards.push(card);
  }
  return turns.length?turns:[{id:'empty',messages:[],cards:[]}];
}

export function RoutePreview({preview}:{preview:NonNullable<QuestionCard['route_preview']>}){
  const [x0,y0,x1,y1]=preview.bounds,w=x1-x0,h=y1-y0,c=preview.cell_m;
  // World +Y is drawn up; SVG y grows down.
  const X=(x:number)=>x-x0,Y=(y:number)=>y1-y,path=preview.polyline.map(p=>`${X(p[0])},${Y(p[1])}`).join(' ');
  const [sx,sy,syaw]=preview.start;
  return <svg role="img" aria-label="Planned route on the Twin floor · model plan, not localization" className="route-preview"
    viewBox={`0 0 ${w} ${h}`} style={{width:'100%',maxHeight:260,background:'#20262e',borderRadius:6}}>
    {preview.free_cells.map(([x,y],i)=><rect key={i} x={X(x)-c/2} y={Y(y)-c/2} width={c} height={c} fill="#3b4652"/>)}
    <polyline points={`${X(sx)},${Y(sy)} ${path}`} fill="none" stroke="#5fd3a6" strokeWidth={0.04} strokeLinejoin="round"/>
    {preview.waypoints.map(([x,y],i)=><g key={i}><circle cx={X(x)} cy={Y(y)} r={0.09} fill="#f2b84b"/>
      <text x={X(x)+0.12} y={Y(y)-0.1} fontSize={0.22} fill="#f2b84b">{i+1}</text></g>)}
    <circle cx={X(sx)} cy={Y(sy)} r={0.1} fill="#ffffff"/>
    <line x1={X(sx)} y1={Y(sy)} x2={X(sx+0.3*Math.cos(syaw))} y2={Y(sy+0.3*Math.sin(syaw))} stroke="#ffffff" strokeWidth={0.05}/>
    <text x={X(sx)+0.12} y={Y(sy)+0.3} fontSize={0.2} fill="#ffffff">Start</text>
  </svg>;
}

export function ActionCard({ card, busy, act, current=true }: {card: QuestionCard; busy: boolean; act: (card: QuestionCard, choice: string, limit?:string) => void;current?:boolean}) {
  const [choice,setChoice]=useState<string|null>(null);
  const preview=card.generation_approval;
  const directOffer=!!preview&&['robot_presence','robot_selection'].includes(card.kind);
  const waiting = card.state === 'waiting' && current;
  if(!waiting||card.kind==='generation_approval')return <section className="chat-question-history" aria-label="Previous question">
    <p>{card.question}</p>{card.route_preview&&<RoutePreview preview={card.route_preview}/>}<small>{card.choices.find(c=>c.id===card.selected_choice_id)?.label ??
      (card.state==='waiting'?'Waiting for the current step to finish':card.state.replaceAll('_',' '))}</small>
  </section>;
  const enabled=card.choices.filter(c=>c.enabled);
  const selected=enabled.length===1?enabled[0].id:enabled.some(option=>option.id===choice)?choice:null;
  const startsGeneration=['robot_presence','robot_selection'].includes(card.kind)&&(card.kind==='robot_selection'||selected==='sim');
  return <section className="chat-question" aria-label={card.question}>
    <p>{card.question}</p>{card.route_preview&&<RoutePreview preview={card.route_preview}/>}
    <small role="status">{busy ? 'Submitting your choice…' : card.kind==='scene_edit_clarify'?'Reply to this one question in chat, or cancel feedback':'Current step · choose an option, then continue'}</small>
    {directOffer&&<div className="generation-start-offer">
      <p>Selecting Create Twin starts generation once. {preview.image_count?
        preview.render_review_approved?'Your photo, description and derived Isaac renders go':'Your photo and description go':
        'Your description goes'} to the configured models below. No robot movement.</p>
      <details><summary>Generation models and limits</summary><p>{preview.purpose}</p>
        <p>Up to {preview.policy.max_requests} requests · {preview.policy.max_repairs} repairs · {preview.policy.per_call_timeout_s}s per request.</p>
        {preview.models.map(model=><p key={model.stage}>{model.stage}: {model.model_id} · {model.origin} · output {model.max_output_tokens}</p>)}
      </details>
    </div>}
    {preview&&!directOffer&&<div className="generation-details">
      <p>{card.scene_feedback?'Your feedback, current scene and unresolved inventory':preview.image_count?'The attached photo and your description':'Your text description'} will be sent to the listed providers {card.scene_feedback?'for a proposal only':'for scene generation'}. No robot command is included.</p>
      {(preview.render_review_approved||card.scene_feedback)&&<p>{preview.purpose}</p>}
      <p>{card.scene_feedback?'Exactly one planner request, no automatic repair':`Up to ${preview.policy.max_requests} requests, including up to ${preview.policy.max_repairs} shared repairs`}. Per request: {preview.policy.per_call_timeout_s}s · action allowance: {preview.policy.total_timeout_s}s. No automatic retry.</p>
      {preview.checkpoint_id&&<p>Continue only unfinished stages. Previous actions: {preview.prior_requests} requests · {Math.round(preview.prior_active_s)}s active time.</p>}
      <details><summary>Input and model details</summary>
        <p>Input SHA: {preview.input_sha256}</p>
        {preview.models.map(model=><p key={model.stage}>{model.stage}: {model.model_id} · {model.origin} · output {model.max_output_tokens} · reasoning {model.thinking_mode}</p>)}
      </details>
    </div>}
    {enabled.length!==1&&<fieldset disabled={busy}><legend>Your choice</legend>
      {card.choices.map(option=><label key={option.id}>
        <input type="radio" name={`choice-${card.id}`} value={option.id} disabled={!option.enabled}
          checked={choice===option.id} onChange={()=>setChoice(option.id)}/>{option.label}</label>)}
    </fieldset>}
    <button type="button" disabled={busy||!selected} onClick={()=>{
      if(selected)act(card,selected);
    }}>
      {busy?'Submitting…':startsGeneration?'Create Twin':selected==='approve'?'Continue':enabled.length===1?enabled[0].label:'Continue'}</button>
    {card.choices.filter(c => !c.enabled).map(c => <small key={c.id}>{c.disabled_reason}</small>)}
  </section>;
}

export function ChatWorkspace({api, advanced, runtimeExit}: {api: TwinPulseApi; advanced: () => void; runtimeExit?:ReactNode}) {
  const [state, setState] = useState<ConversationState | null>(null);
  const missionTelemetry=useRecentMissionTelemetry(state?.navigation?.job);
  // Only an acknowledged user action supplies a fresh preview. Poll/reload
  // retains conversation history but never silently restores execution review.
  const [simulationReview,setSimulationReview]=useState<SimulationReview|null>(null);
  const [realBuild,setRealBuild]=useState<ConversationState['room_build']>(null);
  const [inspectionBuild,setInspectionBuild]=useState<ConversationState['inspection_display']>(null);
  const chosenInspection=useRef<string|null>(null);
  const [runtime, setRuntime] = useState<SupervisorState | null>(null);
  const [product, setProduct] = useState<ProductState | null>(null);
  const [observedWorkflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [workflowObservation,setWorkflowObservation]=useState<{api:TwinPulseApi;context:string;fresh:boolean}|null>(null);
  // Retained workflow is display data only until this exact context's next
  // successful workflow read. Other API successes cannot restore its authority.
  const workflowOwned=workflowObservation?.api===api&&workflowObservation.context===api.context;
  const workflow=workflowOwned?observedWorkflow:null;
  const workflowFresh=workflowOwned&&workflowObservation.fresh;
  const [text, setText] = useState('');
  const [mode, setMode] = useState<'new' | 'add' | 'change'>('new');
  const [file, setFile] = useState<File | null>(null);
  const [librarySource,setLibrarySource]=useState<File|null>(null);
  const [usdPurposeSource,setUsdPurposeSource]=useState<File|null>(null);
  const [environmentSource,setEnvironmentSource]=useState<File|null>(null);
  const [showEnvironment,setShowEnvironment]=useState(false);
  const [imageRole,setImageRole]=useState<'environment_reference'|'asset_reference'>('environment_reference');
  const composerRevisions=useRef({text:0,attachment:0});
  const composerValues=useRef({text,file,imageRole});composerValues.current={text,file,imageRole};
  const composerApi=useRef(api);composerApi.current=api;
  const editComposerText=(value:string)=>{composerRevisions.current.text++;composerValues.current.text=value;setText(value);};
  const editComposerFile=(value:File|null)=>{composerRevisions.current.attachment++;composerValues.current.file=value;setFile(value);};
  const editImageRole=(value:typeof imageRole)=>{composerRevisions.current.attachment++;composerValues.current.imageRole=value;setImageRole(value);};
  const composerSubmissions=useRef(new Map<string,{api:TwinPulseApi;context:string;epoch:number;text:string;textRevision:number;file:File|null;attachmentRevision:number}>());
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionError,setConnectionError] = useState<string|null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [simOperationBusy,setSimOperationBusy]=useState(false);
  const simOperationBusyRef=useRef(false);
  const simOperationChanged=useCallback((active:boolean)=>{
    simOperationBusyRef.current=active;setSimOperationBusy(active);
  },[]);
  const [recoveringEdit,setRecoveringEdit]=useState(false);
  const [delivery, setDeliveryState] = useState<ConversationAction | ResumeSceneAction | RobotCheckAction | null>(null);
  const deliveryOwner=useRef<typeof delivery>(null);
  const deliveryCheckGeneration=useRef(0);
  const pendingDeliveryCheck=useRef<{request_id:string;generation:number}|null>(null);
  const setDelivery=(next:typeof delivery)=>{
    if(deliveryOwner.current?.request_id!==next?.request_id){deliveryCheckGeneration.current++;pendingDeliveryCheck.current=null;}
    deliveryOwner.current=next;setDeliveryState(next);
  };
  const [launcherRequest, setLauncherRequest] = useState<string | null>(null);
  const [showTwin, setShowTwin] = useState(window.innerWidth >= 1000);
  const [controlView,setControlView]=useState(false);
  const [chatShare,setChatShare]=useState(55);
  const [layoutVersion,setLayoutVersion]=useState(0);
  const columns=useRef<HTMLElement|null>(null);
  const splitPointer=useRef<number|null>(null);
  const updateSplit=(share:number)=>setChatShare(Math.min(70,Math.max(25,Math.round(share))));
  const openControlView=()=>{setControlView(true);setShowTwin(true);setShowProjects(false);setChatShare(33);setLayoutVersion(value=>value+1);};
  const [showChecks, setShowChecks] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showKeys,setShowKeys] = useState(false);
  const [showRobots,setShowRobots] = useState(false);
  const [showLibrary,setShowLibrary] = useState(false);
  const [diagnosticExecution, setDiagnosticExecution] = useState<string | null>(null);
  const [viewerFault,setViewerFault]=useState<ViewerFault|null>(null);
  const [showProjects,setShowProjects] = useState(window.innerWidth>=1000);
  const [home,setHome]=useState(false);
  const [newChatRequest,setNewChatRequest]=useState(0);
  const [projectActivity,setProjectActivity]=useState<{busy:boolean;message:string|null}>({busy:false,message:null});
  const projectActivityRef=useRef(false);
  const projectActivityChanged=useCallback((activity:{busy:boolean;message:string|null})=>{projectActivityRef.current=activity.busy;setProjectActivity(activity);},[]);
  const [newUpdates, setNewUpdates] = useState(false);
  const [connected, setConnected] = useState(false);
  const observationAdmission=useRef({api,context:api.context,fresh:false});
  useLayoutEffect(()=>{observationAdmission.current={api,context:api.context,fresh:workflowFresh&&connected&&!!product};},[api,api.context,workflowFresh,connected,product]);
  const mayStartSceneAction=()=>observationAdmission.current.api===api&&observationAdmission.current.context===api.context&&observationAdmission.current.fresh;
  const [contextVersion,setContextVersion]=useState(0);
  const [fleetReceipt,setFleetReceipt]=useState<{api:TwinPulseApi;context:string;state:RobotFleetState;receivedAt:number}|null>(null);
  const [fleetError,setFleetError]=useState<string|null>(null);
  const [fleetSelectedId,setFleetSelectedId]=useState<string|null>(null);
  const [fleetDrawerOpen,setFleetDrawerOpen]=useState(false);
  const [fleetSelecting,setFleetSelecting]=useState(false);
  const fleetSelectionSequence=useRef(0);
  const fleetFocusPending=useRef(false);
  const fleetOwner=useRef({api,context:api.context});fleetOwner.current={api,context:api.context};
  const fleetContext=api.context;
  const fleet=fleetReceipt?.api===api&&fleetReceipt.context===fleetContext?fleetReceipt.state:null;
  const fleetAvailable=connected&&!!fleet&&!fleetError&&Date.now()-(fleetReceipt?.receivedAt??0)<1000;
  const applyFleet=useCallback((next:RobotFleetState)=>{
    if(fleetOwner.current.api!==api||fleetOwner.current.context!==fleetContext)return;
    setFleetReceipt(current=>current?.api===api&&current.context===fleetContext&&current.state.revision>next.revision?current:
      {api,context:fleetContext,state:next,receivedAt:Date.now()});setFleetError(null);
  },[api,fleetContext]);
  useEffect(()=>{
    if(!fleetReceipt)return;
    const timer=setTimeout(()=>setFleetError('Fleet heartbeat is stale · movement paused.'),1000);
    return()=>clearTimeout(timer);
  },[fleetReceipt]);
  useEffect(()=>{
    if(!connected||!fleetContext)return;
    let closed=false;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      try{const next=await api.robotFleet();if(!closed)applyFleet(next);}
      catch{if(!closed)setFleetError('Fleet status unavailable · movement paused. Other App features remain available.');}
      finally{if(!closed)timer=setTimeout(()=>void poll(),500);}
    };
    void poll();return()=>{closed=true;clearTimeout(timer);};
  },[api,fleetContext,connected,applyFleet]);
  useEffect(()=>{setFleetSelectedId(null);setFleetDrawerOpen(false);setFleetError(null);setFleetSelecting(false);fleetFocusPending.current=false;fleetSelectionSequence.current++;},[api,fleetContext]);
  const selectFleetRobot=(id:string)=>{
    // Only one focus mutation may be outstanding. A later click cannot race
    // an older HTTP request into changing the control owner after its receipt.
    if(fleetFocusPending.current)return;
    if(!controlView)openControlView();
    setFleetSelectedId(id);setFleetDrawerOpen(true);
    const target=fleet?.robots.find(row=>row.robot_id===id);
    if(!target)return;
    // A current rendered name can open the status panel while fleet status is
    // unavailable. It must not turn that display-only selection into a focus
    // mutation or new movement authority; the user can select again once fresh.
    if(!fleetAvailable)return;
    const selection=++fleetSelectionSequence.current;fleetFocusPending.current=true;setFleetSelecting(true);
    void api.robotFleetAction({action:'focus',request_id:crypto.randomUUID(),robot_id:id,
      connection_epoch:target.connection_epoch,motion_epoch:target.motion_epoch,payload:{}}).then(applyFleet)
      .catch(()=>{if(fleetOwner.current.api===api&&fleetOwner.current.context===fleetContext)setFleetError('Robot selection delivery unconfirmed. Check fleet status before driving.');})
      .finally(()=>{if(fleetSelectionSequence.current===selection){fleetFocusPending.current=false;setFleetSelecting(false);}});
  };
  const selectedProject=useRef<string|null>(null);
  const contextEpoch=useRef(0);
  const scrollPositions=useRef(new Map<string,{top:number;nearBottom:boolean}>());
  const list = useRef<HTMLDivElement>(null);
  const simulationPanel=useRef<HTMLElement>(null);
  const nearBottom = useRef(true);
  const fileInput = useRef<HTMLInputElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const composerForm = useRef<HTMLFormElement>(null);
  const inFlight = useRef(false);
  const busyOwner=useRef<string|null>(null);
  const releaseOwnedBusy=(request:string)=>{
    if(busyOwner.current!==request)return;
    busyOwner.current=null;inFlight.current=false;setBusy(false);
  };
  const simStop = useRef<{stop:()=>void}|null>(null);
  // Only generation chosen in this mounted chat may prepare a fresh preview.
  // Polling/restored conversations never restore permission to Build or Run.
  const chosenGeneration = useRef<{operation:string;request:string;mode:'SIM'|'REAL'}|null>(null);
  const pollSequence = useRef(0);
  const lastApplied = useRef(0);
  const draftRestored = useRef(false);
  const authenticatedApi=useRef<TwinPulseApi|null>(null);
  const composerEdited = useRef(false);
  const navigationInitialized=useRef(false);
  const restoredGeneration=useRef<string|null>(null);
  const restoredFailures=useRef(new Set<string>());

  const apply = (next: ConversationState) => {
    if(selectedProject.current&&next.project_id!==selectedProject.current)return false;
    if(next.context_id&&api.context&&next.context_id!==api.context)return false;
    selectedProject.current=next.project_id;
    if(!navigationInitialized.current){
      navigationInitialized.current=true;
      if(next.restored_session){
        restoredGeneration.current=next.generation?.operation_id??null;
        restoredFailures.current=new Set(next.messages.filter(row=>row.status==='failed').map(row=>row.message_id));
        if(next.messages.length&&!['accepted','running'].includes(next.generation?.state??'')&&
          !next.inspection?.busy&&!next.navigation?.job?.worker_active&&!next.navigation?.task_loop?.worker_active&&
          next.scene_feedback?.state!=='running'&&(!next.scene_edit_transaction||
            ['COMMITTED','ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(next.scene_edit_transaction.state)))setHome(true);
      }
    }
    setState(previous => previous && previous.project_id===next.project_id && previous.revision > next.revision ? previous : next);
    if (!draftRestored.current) {
      if(!composerEdited.current)editComposerText(sessionStorage.getItem(`twinpulse.chat.draft.${next.project_id}`) ?? '');
      draftRestored.current = true;
    }
    const chosen=chosenGeneration.current;
    if(chosenInspection.current&&next.inspection?.job_id===chosenInspection.current&&!next.inspection.busy){
      if(next.inspection.state==='SURVEY_COMPLETE'&&next.inspection_display?.ready&&
        next.inspection_display.descriptor.mission_id===chosenInspection.current)setInspectionBuild(next.inspection_display);
      chosenInspection.current=null;
    }
    if(chosen && next.generation?.operation_id===chosen.operation && next.generation.state==='completed'){
      if(next.simulation_review?.request_id===chosen.request)setSimulationReview(next.simulation_review);
      if(chosen.mode==='REAL'&&next.room_build?.operation_id===chosen.operation)setRealBuild(next.room_build);
      chosenGeneration.current=null;
    }
    return true;
  };

  const projectChanged=useCallback((selection:{project_id:string;context_id?:string})=>{
    if(selectedProject.current&&list.current)scrollPositions.current.set(selectedProject.current,
      {top:list.current.scrollTop,nearBottom:nearBottom.current});
    selectedProject.current=selection.project_id;contextEpoch.current++;
    busyOwner.current=null;inFlight.current=false;setBusy(false);
    lastApplied.current=++pollSequence.current;
    chosenGeneration.current=null;chosenInspection.current=null;
    restoredGeneration.current=null;restoredFailures.current=new Set();
    draftRestored.current=false;composerEdited.current=false;navigationInitialized.current=true;
    simOperationBusyRef.current=false;simStop.current=null;
    setState(null);setProduct(null);setWorkflow(null);setWorkflowObservation(null);setRuntime(null);setConnected(false);
    setSimulationReview(null);setRealBuild(null);setInspectionBuild(null);setViewerFault(null);
    setError(null);setConnectionError(null);setDismissed(null);setDelivery(null);
    composerSubmissions.current.clear();editComposerText('');editComposerFile(null);setLibrarySource(null);setUsdPurposeSource(null);setEnvironmentSource(null);setShowEnvironment(false);editImageRole('environment_reference');setShowLibrary(false);setMode('new');setNewUpdates(false);setHome(false);
    setShowChecks(false);setShowDiagnostics(false);setShowKeys(false);setDiagnosticExecution(null);
    setSimOperationBusy(false);setRecoveringEdit(false);
    nearBottom.current=scrollPositions.current.get(selection.project_id)?.nearBottom??true;
    if(window.innerWidth<1000)setShowProjects(false);
    setContextVersion(value=>value+1);
  },[]);

  useEffect(() => {
    if(projectActivity.busy)return;
    let active = true, polling = false, authenticated = false;
    const epoch=contextEpoch.current;
    const refresh = async () => {
      if (polling) return;
      polling = true;
      const sequence = ++pollSequence.current;
      const requestedContext=api.context;
      try {
        // These independent observations never start engine, provider or robot work.
        const results = await Promise.allSettled([api.conversation(), api.runtimeState(), api.productState(), api.workflow()]);
        if (!active || epoch!==contextEpoch.current || sequence < lastApplied.current || api.context!==requestedContext) return;
        lastApplied.current = sequence;
        const [chat, startup, engine, generation] = results;
        const currentChat = chat.status === 'fulfilled' && apply(chat.value);
        if (currentChat) { setConnected(true); setConnectionError(null); }
        else { setConnected(false); setConnectionError(chat.status === 'rejected' ? errorText(chat.reason) : 'Waiting for the selected conversation state. No action was replayed.'); }
        if (startup.status === 'fulfilled') setRuntime(startup.value);
        else setRuntime(null);
        if (engine.status === 'fulfilled') setProduct(engine.value);
        else setProduct(null);
        if (generation.status === 'fulfilled') {
          setWorkflow(generation.value);setWorkflowObservation({api,context:requestedContext,fresh:currentChat});
        }else setWorkflowObservation(previous=>previous?.api===api&&previous.context===requestedContext?{...previous,fresh:false}:null);
      } finally { polling = false; }
    };
    void (contextVersion||authenticatedApi.current===api?Promise.resolve():api.bootstrap().then(()=>{authenticatedApi.current=api;}))
      .then(() => { if (active) { authenticated = true; void refresh(); } }).catch(e => { if (active) setConnectionError(errorText(e)); });
    // Draft restoration depends on the first successful conversation read. It
    // must not gate observation retries: a first-read timeout after startup or
    // project switch otherwise leaves this context permanently disconnected.
    // Only authenticated, single-flight GET observations repeat; no action,
    // draft restoration, movement authority or old-context response is replayed.
    const timer = window.setInterval(() => { if (active && authenticated) void refresh(); }, 750);
    return () => { active = false; window.clearInterval(timer); };
  }, [api,contextVersion,projectActivity.busy]);

  useEffect(()=>{
    if(!state||!list.current)return;
    const previous=scrollPositions.current.get(state.project_id);
    if(previous&&!previous.nearBottom)list.current.scrollTop=previous.top;
  },[state?.project_id]);

  useEffect(() => { if (state) sessionStorage.setItem(`twinpulse.chat.draft.${state.project_id}`, text); }, [text, state?.project_id]);
  useEffect(()=>{const input=composerInput.current;if(!input)return;
    input.style.height='auto';input.style.height=`${Math.min(140,Math.max(44,input.scrollHeight))}px`;
  },[text,home]);
  useEffect(()=>{const form=composerForm.current;if(!form||typeof ResizeObserver==='undefined')return;
    const observer=new ResizeObserver(()=>form.closest<HTMLElement>('.chat-conversation')?.style
      .setProperty('--composer-height',`${Math.ceil(form.getBoundingClientRect().height)}px`));
    observer.observe(form);return()=>observer.disconnect();
  },[home]);
  useEffect(() => {
    if (!file) { setThumbnail(null); return; }
    const url = URL.createObjectURL(file); setThumbnail(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    if(home||!list.current){setNewUpdates(false);return;}
    if (nearBottom.current && list.current) { list.current.scrollTop = list.current.scrollHeight; setNewUpdates(false); }
    else setNewUpdates(true);
  }, [state?.cursor,home]);

  const attachment = (candidate?: File) => {
    if (!candidate) return;
    if(isEnvironmentSource(candidate)){
      if(candidate.size>50*1024*1024){setError('Choose a USD source up to 50 MiB. Your scene draft has been kept.');return;}
      setUsdPurposeSource(candidate);setShowEnvironment(false);setShowLibrary(false);setError(null);return;
    }
    if(isLibrarySource(candidate)){
      if(candidate.size>50*1024*1024){setError('Choose a Library asset source up to 50 MiB. Your scene draft has been kept.');return;}
      setLibrarySource(candidate);setShowLibrary(true);setError(null);return;
    }
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(candidate.type) || candidate.size > 10 * 1024 * 1024) {
      setError('Attach one PNG, JPEG, or WebP image up to 10 MiB. Your draft has been kept.'); return;
    }
    if (file) { setError('One image per message is supported. Remove the current image before attaching another.'); return; }
    editComposerFile(candidate);editImageRole('environment_reference');setError(null);
  };
  useEffect(()=>{
    if(home||showKeys||showRobots||showLibrary||showEnvironment||usdPurposeSource||showDiagnostics)return;
    const paste=(event:ClipboardEvent)=>{
      if(event.defaultPrevented||!event.clipboardData)return;
      const target=event.target instanceof Element?event.target:document.activeElement;
      const editor=target?.closest('input,textarea,[contenteditable]')??document.activeElement?.closest('input,textarea,[contenteditable]');
      if(editor&&editor!==composerInput.current)return;
      const result=clipboardImage(event.clipboardData);
      if(result.image){event.preventDefault();attachment(result.image);}
      else if(result.message)setError(result.message);
    };
    document.addEventListener('paste',paste);
    return()=>document.removeEventListener('paste',paste);
  },[file,home,showKeys,showRobots,showLibrary,showEnvironment,usdPurposeSource,showDiagnostics]);

  const acknowledge = (next: ConversationState, action: ConversationAction | ResumeSceneAction | RobotCheckAction) => {
    // A response from a retired project/session cannot acknowledge this draft.
    if(composerApi.current!==api||selectedProject.current&&next.project_id!==selectedProject.current||
      next.context_id&&api.context&&next.context_id!==api.context)return;
    const sent=composerSubmissions.current.get(action.request_id);
    if(sent&&(sent.api!==api||sent.context!==api.context||sent.epoch!==contextEpoch.current))return;
    setHome(false);
    if(action.action==='answer'&&action.choice_id==='inspect'&&next.inspection?.owned&&next.inspection.job_id)
      chosenInspection.current=next.inspection.job_id;
    if((action.action==='answer'||action.action==='message'||action.action==='generation_retry') && next.mode && next.generation?.request_id===action.request_id &&
        ['accepted','running','completed'].includes(next.generation.state))
      chosenGeneration.current={operation:next.generation.operation_id,request:action.request_id,mode:next.mode};
    apply(next);
    setSimulationReview(next.simulation_review?.request_id===action.request_id?next.simulation_review:null);
    if (action.action === 'message'&&sent) {
      // Text and attachment have independent ownership. Equality alone misses
      // deleting/retyping the same words or reselecting the same File object.
      if(composerRevisions.current.text===sent.textRevision&&composerValues.current.text===sent.text)editComposerText('');
      if(composerRevisions.current.attachment===sent.attachmentRevision&&composerValues.current.file===sent.file)editComposerFile(null);
      composerSubmissions.current.delete(action.request_id);composerInput.current?.focus();
    }
    setDelivery(null); setError(null);
  };

  const submit = async (action: ConversationAction | ResumeSceneAction | RobotCheckAction) => {
    const epoch=contextEpoch.current,context=api.context;
    const current=()=>composerApi.current===api&&contextEpoch.current===epoch&&api.context===context;
    const observationOrStop=action.action==='cancel'||action.action==='message'&&!action.attachment&&
      (isConversationStatusRequest(action.text)||isConversationStopRequest(action.text));
    if(!mayStartSceneAction()&&!observationOrStop){composerSubmissions.current.delete(action.request_id);releaseOwnedBusy(action.request_id);setError('Scene observation is stale. Wait for a successful conversation, workflow and product refresh before starting a new action. No request was sent.');return;}
    if (inFlight.current||projectActivityRef.current) {
      composerSubmissions.current.delete(action.request_id);
      releaseOwnedBusy(action.request_id);
      setError('Previous action is still settling; no new request was sent. Wait then choose Continue explicitly.');
      return;
    }
    busyOwner.current=action.request_id;inFlight.current = true; setBusy(true); setError(null); setDismissed(null);
    try { const next=await api.conversationAction(action);if(current())acknowledge(next, action); }
    catch (caught) {
      if(!current())return;
      if (caught instanceof ApiError && !['delivery_unknown','conversation_save_failed'].includes(caught.code)) {
        composerSubmissions.current.delete(action.request_id);setError(errorText(caught));
      }
      else {
        // A lost HTTP response is not a failed execution. Query, never resubmit.
        try {
          const observed = await api.conversation();
          if(!current())return;
          if (observed.accepted_request_ids.includes(action.request_id)) acknowledge(observed, action);
          else { setDelivery(action); setError('Delivery unknown. Check the saved result; this request will not be repeated automatically.'); }
        } catch { if(current()){setDelivery(action); setError('Delivery unknown. Check the saved result before trying any new operation.');} }
      }
    } finally { releaseOwnedBusy(action.request_id); }
  };

  const send = async () => {
    if(librarySource||file&&imageRole==='asset_reference'){setShowLibrary(true);return;}
    if (inFlight.current || projectActivityRef.current || busy || delivery || !connected || (!text.trim() && !file)) return;
    const observingOnly=!file&&(isConversationStatusRequest(text)||isConversationStopRequest(text));
    if(!observingOnly&&!mayStartSceneAction())return;
    if(!observingOnly&&(simOperationBusyRef.current || product?.operations?.some(op=>['accepted','running'].includes(op.status))))return;
    const request_id=crypto.randomUUID(),sent={api,context:api.context,epoch:contextEpoch.current,text,
      textRevision:composerRevisions.current.text,file,attachmentRevision:composerRevisions.current.attachment};
    composerSubmissions.current.set(request_id,sent);
    while(composerSubmissions.current.size>32)composerSubmissions.current.delete(composerSubmissions.current.keys().next().value!);
    // Lock synchronously while converting an attachment, before the first await.
    busyOwner.current=request_id;inFlight.current = true; setBusy(true);
    // An explicit Send requests Stop immediately, not after journal/network
    // polling. Opening/reloading chat never invokes this control method.
    if(!file&&isConversationStopRequest(text)&&state?.mode!=='REAL')simStop.current?.stop();
    try {
      const image = sent.file ? { name: sent.file.name, media_type: sent.file.type, content_base64: await fileToBase64(sent.file) } : null;
      if(busyOwner.current!==request_id){composerSubmissions.current.delete(request_id);return;}
      inFlight.current = false;
      if(composerApi.current!==api||sent.context!==api.context||sent.epoch!==contextEpoch.current){composerSubmissions.current.delete(request_id);releaseOwnedBusy(request_id);return;}
      await submit({action: 'message', request_id, text:sent.text, mode, attachment: image});
    } catch (caught) {
      composerSubmissions.current.delete(request_id);
      if(composerApi.current===api&&sent.context===api.context&&sent.epoch===contextEpoch.current)setError(errorText(caught));
      releaseOwnedBusy(request_id);
    }
  };

  const choose = (card: QuestionCard, choice: string, limit?:string) => void submit({action: 'answer', request_id: crypto.randomUUID(),
    card_id: card.id, choice_id: choice, expected_session_revision: card.expected_session_revision,
    ...(limit?{limit_usd:limit}:{}),
    ...((card.kind==='robot_initialize'&&choice==='initialize'||card.kind==='robot_qualification'&&choice==='qualify'||card.kind==='robot_inspection'&&choice==='inspect'||card.kind==='robot_goal_confirm'&&choice==='confirm'||card.kind==='robot_goal_loop'&&choice==='loop')?{expires_at_ms:Date.now()+1500}:{})});
  const job = state?.generation;
  const generationSettling=!!job?.generation_id&&state?.generation_settling?.operation_id===job.operation_id&&
    state.generation_settling.generation_id===job.generation_id;
  const instances=job?.error?.diagnostics?.instance_grounding??job?.progress?.instance_grounding;
  const inventoryWork=job?.error?.diagnostics?.inventory_progress??job?.progress?.inventory_progress;
  const acceptedSavedScene=job?savedGenerationScene(job,workflow):null;
  // Durable geometry storage and unresolved visual quality are separate facts.
  // Never claim "no scene accepted" just because photo refinement remains.
  const completedDraftSaved=!!job&&job.state==='completed'&&!!acceptedSavedScene&&!acceptedSavedScene.partial;
  const sourceAttachment=state?generationSourceAttachment(state):undefined;
  const attemptDiagnostic = job?.error?.diagnostics?.attempts ? job.error.diagnostics : job?.progress;
  const retentionLabel=job?generationRetentionRevalidationLabel(job):null;
  const resumePresentation=job?generationResumePresentation(job):null;
  const generationSettlingMessage=`Cancellation is still settling · no new generation request was sent. Wait, then choose ${resumePresentation?.label??'Continue'} explicitly. No automatic restart.`;
  const activeJob = !!job&&['accepted','running'].includes(job.state);
  const feedback=state?.scene_feedback;
  const feedbackBusy=feedback?.state==='running';
  const editTransaction=state?.scene_edit_transaction??workflow?.scene_edit_transaction;
  const editLocked=!!editTransaction&&!['COMMITTED','ROLLED_BACK','CANCELLED_BEFORE_DISPATCH'].includes(editTransaction.state);
  useEffect(()=>{
    if(editLocked||simulationReview&&workflow?.site_draft&&simulationReview.scene_revision!==workflow.site_draft.revision){
      setSimulationReview(null);chosenGeneration.current=null;
    }
  },[editLocked,workflow?.site_draft?.revision,simulationReview?.scene_revision]);
  // A SIM preview adds its Burger to a derived scene revision. Observe that
  // revision, not the original provider draft; observation never restores Run.
  const simRoomRevision=simulationReview?.plan?.scene_revision??state?.simulation_review?.plan?.scene_revision??workflow?.site_draft?.revision;
  const simSnapshot=product?.engine_connected && product.snapshot?.run_id &&
    product.snapshot.applied_revision===simRoomRevision &&
    product.snapshot.capabilities.includes('site_simulation_v1') ? product.snapshot : null;
  const inspection=state?.inspection;
  const goalJob=state?.navigation?.job;
  const taskLoop=state?.navigation?.task_loop;
  useEffect(()=>{
    if(projectActivity.busy||state?.mode!=='REAL'||typeof api.chatTaskPresence!=='function')return;
    let pending=false;
    const presence=()=>{if(pending)return;pending=true;
      void api.chatTaskPresence().catch(()=>{/* Task/native guard fails closed; no retry of movement. */}).finally(()=>{pending=false;});};
    presence();const timer=setInterval(presence,700);return()=>clearInterval(timer);
  },[api,state?.mode,projectActivity.busy]);
  const goalBusy=!!goalJob&&!['MISSION_ARRIVED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','MISSION_CANCELLED','FAILED'].includes(goalJob.state);
  const robotControlState=state?.robot_preparation&&taskLoop?.worker_active ? {...state.robot_preparation,
    active_control:{owned:true,busy:true,state:taskLoop.state,mode:'repeat',cleanup_confirmed:false}}:
    state?.robot_preparation&&goalBusy ? {...state.robot_preparation,
    active_control:{owned:true,busy:true,state:goalJob!.state,mode:'goal',cleanup_confirmed:false}}:
    state?.robot_preparation&&inspection?.busy ? {...state.robot_preparation,
    active_control:{owned:inspection.owned,busy:true,state:inspection.state,mode:'survey',cleanup_confirmed:false}}:state?.robot_preparation;
  const inspectionFault=inspection?.state==='FAILED'?[inspection.job_id,inspection.error,inspection.cleanup_error,inspection.report_error].filter(Boolean).join(' · '):null;
  useEffect(()=>{if(inspectionFault)setError(`Inspection failed: ${inspectionFault}`);},[inspectionFault]);
  const goalFault=goalJob?.state==='FAILED'?[goalJob.error,...nativeCleanupLines(goalJob),goalJob.cleanup_error,goalJob.report_error].filter(Boolean).join(' · '):null;
  useEffect(()=>{if(goalFault)setError(`Goal mission failed: ${goalFault}`);},[goalFault]);
  const taskFault=taskLoop?.state==='FAILED'?[taskLoop.error_stage,taskLoop.error,taskLoop.cleanup_error].filter(Boolean).join(' · '):null;
  useEffect(()=>{if(taskFault)setError(`Repeat task failed: ${taskFault}`);},[taskFault]);
  const demonstration=state?.navigation?.demonstration;
  const demonstrationFault=demonstration&&[demonstration.error,demonstration.cleanup_error].filter(Boolean).join(' · ');
  useEffect(()=>{if(demonstrationFault)setError(`Isaac route demonstration: ${demonstrationFault}`);},[demonstrationFault]);
  const taskStatus=simSnapshot ? `SIM navigation · ${simSnapshot.runtime_state}` : activeJob ? 'Generating scene' :
    !product?.engine_connected ? 'Task state unavailable' : 'No active motion task';
  const waitingCard = state?.cards.find(card => card.state === 'waiting'&&card.kind!=='generation_approval');
  const pendingChoice = !!waitingCard;
  const engineCommandPending=!!product?.operations?.some(op=>['accepted','running'].includes(op.status));
  const sceneOperationBusy=simOperationBusy||engineCommandPending;
  const hasRobot=state?.robot_id==='turtlebot3_burger';
  const baseIdleFlow=!pendingChoice&&!activeJob&&!feedbackBusy&&!editLocked&&!busy&&!delivery&&!sceneOperationBusy;
  const sceneObservationFresh=workflowFresh&&connected&&!!product;
  const idleFlow=baseIdleFlow&&sceneObservationFresh;
  // Keep a retained job action stable while its previous delivery settles,
  // but never offer another submission while that delivery is pending.
  const generationRetryVisible=!pendingChoice&&!activeJob&&!feedbackBusy&&!editLocked&&!sceneOperationBusy;
  const needsRoomDisplay=state?.mode==='REAL'&&!!state.room_build&&(!realBuild||realBuild.operation_id!==state.room_build.operation_id||realBuild.scene_revision!==state.room_build.scene_revision);
  const roomApplied=!!product?.engine_connected&&!!workflow?.site_draft&&product.snapshot?.applied_revision===
    (state?.mode==='SIM'?simRoomRevision:workflow.site_draft.revision);
  const canReviewInspection=idleFlow&&roomApplied&&state?.robot_preparation?.state==='LINKED'&&!inspection?.busy&&!goalBusy&&!taskLoop?.worker_active&&inspection?.state!=='SURVEY_COMPLETE';
  const engineSnapshot=product?.engine_connected?product.snapshot:null;
  // Stage invalidation can intentionally clear run_id and telemetry. That
  // must not hide the current engine failure behind "No active motion task".
  const executionError=engineSnapshot && (engineSnapshot.safety_state || ['error','unstable','off_route','stage_invalid'].includes(engineSnapshot.runtime_state)) ?
    `SIM execution stopped (${engineSnapshot.runtime_state}): ${engineSnapshot.safety_reason ?? engineSnapshot.safety_state ?? 'Check the engine diagnosis.'}` : null;
  const displayError=product?.build_view && ['failed','unknown'].includes(product.build_view.status) ?
    product.build_view.phase==='apply' ?
      `3D scene apply failed or unconfirmed (${product.build_view.error_code}): ${product.build_view.message ?? 'Review the engine receipt.'} No automatic Build or Run retry.` :
      `3D display unavailable (${product.build_view.error_code}). Scene apply succeeded, but its current frame was not confirmed. No automatic Build or Run retry.` : null;
  const storageError=workflow?.error?.code==='project_persistence_failed' ?
    'Scene validated but not saved · the draft is only in memory. Build and Run are blocked; reopening may lose this draft. No automatic model retry.' : null;
  const applyError=product?.build_view?.phase==='apply'?displayError:null;
  const browserError=viewerFault?`Browser 3D display unavailable (${viewerFault.code}). Scene and engine receipts are unchanged. Run is blocked while this display error remains; Stop is still available.`:null;
  const currentStep=pendingChoice?waitingCard.question:feedbackBusy?'Preparing one scene-feedback proposal · nothing is applied yet':
    editLocked?`Twin update · ${editTransaction!.state.replaceAll('_',' ')} · geometry and Run locked`:activeJob?generationActivityLabel(job):
    browserError?'Browser display failed · review display diagnostics; Stop remains available':
    storageError?'Scene not saved · review the storage diagnosis before continuing':
    applyError?'3D scene apply failed · review the diagnosis; no automatic retry':
    executionError?'Isaac execution stopped · review the cause; nothing resumes automatically':
    displayError?'3D display not confirmed · review the diagnosis; no automatic retry':
    sceneOperationBusy?'Preparing the current Twin in Isaac · your message draft is kept; wait for the command ACK and current frame':
    product?.build_view?.status==='waiting'?'Scene applied · waiting for its first current 3D frame; no action needed':
    generationSettling?generationSettlingMessage:
    job&&['cancelled','interrupted'].includes(job.state)&&state?.budgeted_generation_available&&inventoryWork&&inventoryCheckpointSaved(inventoryWork)?
      `Generation ${job.state} · checkpoint and any last preview retained. Select ${resumePresentation!.label} when ready; nothing resumes automatically. Preview is not execution validation.`:
    job?.state==='failed'&&(job.error?.code==='REPAIR_STALLED'||job.error?.diagnostics?.generation_activity?.phase==='blocked')?generationActivityLabel(job):
    job?.state==='failed'&&inventoryWork&&inventoryCheckpointSaved(inventoryWork)?
      'Resume checkpoint saved · review the stop reason, then continue unfinished work':
    job?.state==='failed'?'Scene generation failed · review the cause, then continue unfinished work':
    needsRoomDisplay?'Reopen the current room display · no robot command':
    inspection?.busy?`Inspection in progress · ${inspection.state.replaceAll('_',' ')}`:
    goalBusy?`Goal mission in progress · ${goalJob!.state.replaceAll('_',' ')}`:
    taskLoop?.worker_active?'Repeat task active · Stop remains available':
    workflow&&!sceneObservationFresh?'Last saved scene details retained for review only · current scene observation delayed; new scene actions are locked':
    workflow?.site_draft?.draft_refinement?'Editable Twin draft saved · estimated positions; photo issues and pending objects retained. Edit or review sensor feedback next':
    workflow?.site_draft?.progressive_twin?.unresolved.length?'Partial draft saved · view the 3D draft and refinement list; motion remains locked':
    canReviewInspection?'Twin applied and robot linked · check inspection readiness':
    state?.mode==='REAL'&&hasRobot?`Robot preparation · ${state.robot_preparation?.stage.replaceAll('_',' ')??'Checking readiness'}`:
    simulationReview?(simSnapshot?.runtime_state==='completed'?'SIM destination reached · stopped normally. Ask for another destination to continue':
      simSnapshot?.runtime_state==='running'?'SIM running · Stop simulation remains available':
      roomApplied?'Scene applied · review the SIM route, then Run simulation':'Scene validated · wait for the Isaac build, then review the SIM route'):
    state?.mode==='SIM'&&workflow?.site_draft?'Saved scene · request or preview a SIM route; nothing resumes automatically':
    workflow?.phase==='draft_ready'&&workflow.site_draft?'Current Twin saved · review it, then request an edit or a goal; nothing moves automatically':
    'Describe a space or attach a photo. A photo is optional.';
  const jobError = job?.error&&job.operation_id!==restoredGeneration.current ? `${job.error.message} (${job.error.code})` : null;
  const lastAssistant=state?.messages.slice().reverse().find(message=>message.role==='assistant');
  const chatFailure=!activeJob && lastAssistant?.status==='failed'&&!restoredFailures.current.has(lastAssistant.message_id) ? lastAssistant.content : null;
  const runtimeError=runtime?.status==='error'?`Isaac runtime failed (${runtime.phase}): ${runtime.message}`:null;
  const visibleError = browserError ?? storageError ?? applyError ?? executionError ?? displayError ?? error ?? (!state?connectionError:null) ?? state?.restore_error?.message ?? jobError ?? chatFailure ??
    runtimeError;
  const engineReady = product?.engine_connected === true;
  const savedDraft = workflow?.site_draft ?? workflow?.draft;
  const turns=conversationTurns(state??{messages:[],cards:[]});
  const owner=(origin?:string,operation?:string|null,at?:string):string=>{
    const linked=turns.find(turn=>turn.id===origin||turn.messages.some(message=>message.message_id===origin));
    if(linked)return linked.id;
    const matching=operation&&turns.find(turn=>turn.messages.some(message=>message.operation_id===operation)||turn.cards.some(card=>card.operation_id===operation));
    if(matching)return matching.id;
    const timestamp=Date.parse(at??'');
    if(Number.isFinite(timestamp)){
      const preceding=turns.filter(turn=>turn.messages.some(message=>Date.parse(message.created_at)<=timestamp)).at(-1);
      if(preceding)return preceding.id;
    }
    return turns.find(turn=>turn.messages.some(message=>message.role==='user'))?.id??turns[0].id;
  };
  const generationTurn=owner(job?.origin_message_id,job?.operation_id,job?.started_at);
  const feedbackTurn=owner(feedback?.origin_message_id,feedback?.operation_id);
  const transactionTurn=owner(editTransaction?.origin_message_id,editTransaction?.operation_id);
  const pendingEditTurn=owner(state?.queued_edit?.origin_message_id);
  const simulationTurn=simulationReview?.origin_message_id||state?.simulation_review?.origin_message_id?
    owner(simulationReview?.origin_message_id??state?.simulation_review?.origin_message_id):generationTurn;
  // A saved/edited room without a current chat goal is workspace state, not
  // part of the old generation transcript. Keep its display/route entry at the
  // front of the history; an explicit goal still owns its own route card.
  const simulationHasOrigin=!!(simulationReview?.origin_message_id||state?.simulation_review?.origin_message_id);
  const simulationCard=state?.mode!=='REAL'&&!storageError&&workflow?.site_draft?.artifact_id&&workflow.phase==='draft_ready'?
    <section ref={simulationPanel} id="current-twin-sim-controls" aria-label="Current Twin and SIM preparation" tabIndex={-1}>
    {workflow.site_draft.provider_name==='local-environment-import'?<p>Imported space · use the Twin robot controls to add a SIM robot, choose a destination and inspect its scans. Source units and real-world alignment remain uncalibrated.</p>:<SimulationRunCard key={`${workflow.site_draft.input_revision}:${workflow.site_draft.revision}`} api={api} revision={workflow.site_draft.revision}
      artifactId={workflow.site_draft.artifact_id} product={product} report={setError} review={simulationReview} stopHandle={simStop} showActions={!pendingChoice&&!editLocked&&!feedbackBusy} browserBlocked={!!viewerFault} chatPending={busy||!!delivery||editLocked||feedbackBusy||!sceneObservationFresh} fresh={sceneObservationFresh} sceneWriterActive={showLibrary||editLocked||feedbackBusy}
      operationBusyChanged={simOperationChanged}
      taskBlocked={!!workflow.site_draft.progressive_twin?.unresolved.length}/>}</section>:null;
  const restartLauncher = async (cancel: boolean) => {
    if (launcherRequest) return;
    setLauncherRequest(cancel ? 'Cancelling startup…' : 'Requesting an owned restart…');
    try {
      if (cancel) await api.cancelStartup(); else await api.retryLauncher();
      setLauncherRequest(cancel ? 'Startup cancellation requested.' : 'Restart requested. Wait for the launcher’s new secure window; no robot task resumes.');
    } catch (caught) { setError(errorText(caught)); setLauncherRequest(null); }
  };

  return <div className={`chat-workspace ${controlView?'is-control-view':''}`}>
    <header className="chat-appbar"><button className="chat-sidebar-toggle" onClick={()=>setShowProjects(!showProjects)} aria-expanded={showProjects} aria-label="Toggle conversations and projects">☰</button>
      <strong>TwinPulse</strong><span className="chat-project-caption" title={home?'Choose a conversation or start a new chat':`${state?.project_id??'Connecting…'} · ${state?.mode??'Choose a mode'}`}>{home?'New or saved chat':`${state?.project_id??'Connecting…'} · ${state?.mode??'Choose a mode'}`}</span>
      <IsaacConnectionStatus runtime={runtime} connected={engineReady} apiConnected={connected} inspect={()=>setShowChecks(!showChecks)}/>
      {runtimeExit}
      <button onClick={()=>setShowKeys(true)} aria-expanded={showKeys}>API keys</button>
      <button onClick={()=>setShowRobots(true)} aria-expanded={showRobots}>Robots</button>
      <button onClick={()=>setShowLibrary(true)} aria-expanded={showLibrary}>Library</button>
      <button type="button" onClick={()=>{setShowEnvironment(!showEnvironment);setUsdPurposeSource(null);setHome(false);}} aria-expanded={showEnvironment}>Import space</button>
      <button onClick={() => setShowChecks(!showChecks)} aria-expanded={showChecks} aria-label={`Readiness · ${engineReady?'Engine connected':'Needs attention'}`} title={engineReady?'Engine connected · inspect readiness checks':'Needs attention · inspect readiness checks'}>Readiness</button>
      <button onClick={() => {setDiagnosticExecution(null);setShowDiagnostics(!showDiagnostics);}} aria-expanded={showDiagnostics}>Diagnostics</button>
      <button onClick={() => {if(home){setHome(false);setShowTwin(true);}else setShowTwin(!showTwin);}} aria-expanded={showTwin&&!home}>{showTwin&&!home ? 'Hide Twin' : 'Show Twin'}</button>
      <button type="button" aria-pressed={controlView} onClick={()=>{
        if(controlView){setControlView(false);setChatShare(55);setLayoutVersion(value=>value+1);}
        else{setHome(false);openControlView();}
      }}>Control view</button>
      {state?.mode==='REAL'&&<ChatRobotStops state={robotControlState} api={api} report={setError} forceOnly/>}
    </header>
    <Activity mode={projectActivity.busy?'hidden':'visible'}>
    {showKeys&&<ApiKeySettings api={api} close={()=>setShowKeys(false)}/>}
    {showRobots&&<RobotRegistry api={api} close={()=>setShowRobots(false)} runtimeReady={connected&&runtime?.status==='ready'}/>}
    {usdPurposeSource&&<section className="chat-question" aria-label="USD import purpose" style={{margin:'8px 16px'}}>
      <strong>{usdPurposeSource.name}</strong><p>How will you use this USD file?</p>
      <button type="button" onClick={()=>{setEnvironmentSource(usdPurposeSource);setUsdPurposeSource(null);setShowEnvironment(true);setHome(false);}}>Import space</button>
      <button type="button" onClick={()=>{setLibrarySource(usdPurposeSource);setUsdPurposeSource(null);setShowLibrary(true);}}>Library asset</button>
      <button type="button" onClick={()=>setUsdPurposeSource(null)}>Cancel USD attachment</button>
    </section>}
    {showEnvironment&&<EnvironmentImport key={contextVersion} api={api} initialFile={environmentSource} close={()=>setShowEnvironment(false)}
      enabled={connected&&!busy&&!delivery&&!activeJob&&!feedbackBusy&&!editLocked&&!sceneOperationBusy&&!goalBusy&&!taskLoop?.worker_active}
      onSubmitted={()=>setEnvironmentSource(null)} onReady={async next=>{setWorkflow(next);setWorkflowObservation({api,context:api.context,fresh:false});setSimulationReview(null);setShowTwin(true);setHome(false);apply(await api.conversation());}}/>}
    {showLibrary&&<ModelLibrary key={contextVersion} api={api} close={()=>setShowLibrary(false)}
      initialImport={librarySource} initialReference={imageRole==='asset_reference'?file:null} initialPrompt={text}
      sceneRevision={workflowFresh?workflow?.site_draft?.revision??null:null} placementEnabled={idleFlow&&connected&&engineReady&&!sceneOperationBusy&&!goalBusy&&!taskLoop?.worker_active}
      onImportSubmitted={()=>setLibrarySource(null)} onSceneApplied={async next=>{setWorkflow(next);setWorkflowObservation({api,context:api.context,fresh:false});setSimulationReview(null);setShowTwin(true);setHome(false);apply(await api.conversation());}}
      useModel={model=>{
      editComposerText(`Use model ${model.model_id} (${model.title??model.kind}) from the local library in this Twin. Keep its named support surfaces; dimensions are estimates unless I provide measurements.`);
      setShowLibrary(false);setShowTwin(false);setHome(false);
    }}/>}
    {showDiagnostics && <ExecutionDiagnostics key={diagnosticExecution ?? 'all'} initialExecution={diagnosticExecution} api={api} close={() => setShowDiagnostics(false)}/>}
    </Activity>
    <div className="chat-workspace-body">
    <div className="chat-sidebar-slot" hidden={!showProjects}><ChatProjects api={api} apiReady={connected} launcherReady={runtime?.status==='ready'} activityChanged={projectActivityChanged} onProjectChanged={projectChanged}
      onNewChatReady={()=>{if(window.innerWidth<1000)setShowTwin(false);}}
      operationBusy={!sceneObservationFresh||busy||!!delivery||activeJob||feedbackBusy||editLocked||sceneOperationBusy||goalBusy||!!inspection?.busy||!!taskLoop?.worker_active}
      report={setError} advanced={advanced} currentProject={state?.project_id}
      currentConversation={state?.messages.length?{display_name:state.messages.find(row=>row.role==='user')?.content.trim().replace(/\s+/g,' ').slice(0,80)||'Photo Twin',message_count:state.messages.length,last_message_at:state.messages.at(-1)?.created_at??null}:undefined}
      openCurrent={()=>{setHome(false);if(window.innerWidth<1000)setShowProjects(false);}} newChatRequest={newChatRequest}/></div>
    <Activity mode={projectActivity.busy?'hidden':'visible'}><div className="chat-main-shell">
    {showChecks && <section className="chat-checklist" aria-label="Runtime checklist">
      <h2>Runtime checklist</h2><DeviceLogStorage api={api}/><p>File integrity and current runtime readiness are separate checks. A matching file does not authorize motion.</p><ul>
        <li>{connected ? '✓' : '…'} Local chat API {connected ? 'connected' : 'not confirmed'}</li>
        <li>{runtime?.status === 'ready' ? '✓' : '…'} Launcher: {runtime?.status ?? 'unavailable'} — {runtime?.message ?? 'Status observation unavailable'}</li>
        <li>{engineReady ? '✓' : '⚠'} Isaac: {engineReady ? 'connected' : 'not connected'} — no live scene claimed</li>
        {product?.engine_readiness && ['legacy_scene_build','site_scene_build_v2'].map(feature => {
          const observed=product.engine_readiness![feature];
          return <li key={feature}>{observed?.ready ? '✓' : '⚠'} Runtime capability · {feature.replaceAll('_',' ')} · {observed?.ready ? 'ready' : observed?.code ?? 'not observed'}</li>;
        })}
        <li>{workflow?.provider.configured ? '✓' : '⚠'} Provider: {workflow?.provider.label ?? 'not observed'} {workflow?.provider.configured ? '(configured)' : '(configuration required)'}</li>
        <li>— Embedded viewport: fresh Isaac frames are checked in the Twin pane</li>
        <li>— Robot: {state?.mode === 'REAL' ? state.robot_preparation?.state.replaceAll('_',' ')??'Preparation unavailable' : 'not required for simulation'}</li>
        {runtime?.startup_checks?.map(item => <li key={item.id}>{item.state==='ready'?'✓':'⚠'} {item.id.replaceAll('_',' ')} · {item.state}<p>{item.detail}{item.action ? ` ${item.action}` : ''}{item.attempts!==undefined ? ` Repair attempts: ${item.attempts}/1.` : ''}</p><small>Checked at {item.sampled_at}. Not a continuous monitor.</small></li>)}
      </ul><small>These are current software observations, not physical test results.</small>
      {runtime?.status==='error' && <button disabled={!!launcherRequest || !runtime.retry_remaining}
        title={!runtime.retry_remaining ? 'No owned restart attempts remain' : undefined} onClick={() => void restartLauncher(false)}>Retry owned engine</button>}
      {runtime?.status==='starting' && <button disabled={!!launcherRequest} onClick={() => void restartLauncher(true)}>Cancel engine startup</button>}
      {launcherRequest && <p role="status">{launcherRequest}</p>}
      </section>}
    {visibleError && visibleError !== dismissed && (!home||visibleError!==jobError&&visibleError!==chatFailure) && <aside className="chat-error-banner" role="alert">
      <span>{visibleError}</span><button onClick={() => {setDiagnosticExecution(browserError ? viewerFault?.execution_id ?? null : storageError ? workflow?.execution_id ?? null : applyError ? product?.build_view?.execution_id ?? null : executionError ? product?.snapshot_execution_id ?? null : displayError ? product?.build_view?.execution_id ?? null : workflow?.error ? workflow.execution_id ?? null : visibleError===runtimeError ? runtime?.diagnostic_execution_id ?? null : null);setShowDiagnostics(true);}}>View diagnostics</button>
      <button onClick={() => setDismissed(visibleError)}>Dismiss</button>
    </aside>}
    {goalFault&&visibleError===error&&visibleError!==dismissed&&<aside className="chat-failure-popup"
      role="alertdialog" aria-modal="false" aria-label="Goal mission failure">
      <strong>Mission stopped · needs attention</strong><p>{goalFault}</p>
      <small>No automatic restart. Stop controls remain available.</small>
      <button onClick={()=>setDismissed(visibleError)}>Dismiss failure</button>
    </aside>}
    {state&&<div className="chat-link-observation" role="status" aria-label="App connection observation"
      title={connectionError??'Application state connection available'}>
      {connectionError?`App connection delayed · last view retained · ${connectionError}`:'App connection available'}
    </div>}
    {workflow&&!workflowFresh&&<p role="status" aria-label="Workflow observation">Workflow observation delayed · last saved scene details retained for display only. Scene actions are locked until a successful workflow refresh; no work is restarted.</p>}
    {workflowFresh&&!product&&<p role="status" aria-label="Scene state observation">Product state observation delayed · saved details are display only. Scene actions await fresh product state; no work is restarted.</p>}
    <main ref={columns} className={`chat-columns ${showTwin&&!home ? '' : 'twin-folded'}`}
      style={{'--chat-share':`${chatShare}%`} as CSSProperties}>
      {home?<section className="chat-home" aria-label="Conversation home">
        <h1>What would you like to build?</h1><p>Describe a space or use a photo to create your Digital Twin.</p>
        <button className="chat-home-new" aria-busy={projectActivity.busy} disabled={!sceneObservationFresh||projectActivity.busy||runtime?.status!=='ready'||!connected||busy||activeJob||feedbackBusy||editLocked||sceneOperationBusy||goalBusy||!!inspection?.busy||!!taskLoop?.worker_active}
          onClick={()=>setNewChatRequest(value=>value+1)}>{projectActivity.busy?'Opening new chat…':'＋ Start a new chat'}</button>
        {projectActivity.message&&<p role="status">{projectActivity.message}</p>}
        <p className="chat-home-note">Open saved conversations and Twins from the sidebar. A new chat creates a separate project and never overwrites an original.</p>
        <button onClick={()=>setHome(false)}>Open saved chat · {state?.project_id}</button>
      </section>:<>
      <section id="chat-conversation-pane" className="chat-conversation" aria-label="Conversation">
        <section className="chat-current-step" aria-label="Current step"><strong>Current step</strong><p role="status">{currentStep}</p>
          {simulationCard&&<button type="button" aria-label="Current Twin and SIM controls" title="Open current Twin and SIM controls" aria-controls="current-twin-sim-controls" onClick={()=>{
            nearBottom.current=false;setNewUpdates(false);simulationPanel.current?.scrollIntoView({block:'start'});simulationPanel.current?.focus({preventScroll:true});
          }}>Twin controls</button>}
        </section>
        <div ref={list} className="chat-message-list" onScroll={() => { const node = list.current; if (node) nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80; }}>
          {!simulationHasOrigin&&simulationCard}
          {state?.restored_session&&<p className="chat-history-note">Saved conversation · previous execution history. Reopening never automatically starts generation or motion.</p>}
          {workflow?.site_draft?.progressive_twin&&<section aria-label="Twin draft acceptance" role="status">
            <p>Draft compiled · current 3D display checked separately · SIM task unverified · physical execution unverified</p>
            <p>{workflow.site_draft.progressive_twin.materialized_count}/{workflow.site_draft.progressive_twin.inventory_count} input objects materialized. Dimensions are not measured.</p>
            {!workflow.site_draft.progressive_twin.current&&<p>The scene changed. The original assessment needs revalidation.</p>}
            {!!workflow.site_draft.progressive_twin.unresolved.length&&<>
              <p>{workflow.site_draft.progressive_twin.unresolved.length} objects need refinement. Viewing is available; motion remains locked until their task impact is checked.</p>
              <details><summary>Refinement list</summary><ul>{workflow.site_draft.progressive_twin.unresolved.map(row=><li key={row.id}>
                {row.id} · parent {row.parent_id} · support placement unresolved ({row.reason}){row.hazard?` · retained ${row.hazard} hazard`:''}
              </li>)}</ul></details>
            </>}
          </section>}
          {workflow?.site_draft?.draft_refinement&&<section aria-label="Photo refinement retained" role="status">
            <h3>Approximate Twin saved · photo refinement incomplete</h3>
            <p>{workflow.site_draft.draft_refinement.acceptance==='MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE'?
              'The materialized subset passed its remaining compiler checks. Unresolved support objects remain pending; whole-inventory geometry did not pass.':
              'The saved candidate passed its geometry compiler checks. All objects remain represented.'}
              Photo quality did not pass: {workflow.site_draft.draft_refinement.stop_reason}. Known photo interpretation issues are retained, not dismissed as decoration.</p>
            {!workflow.site_draft.draft_refinement.current&&<p>The Twin changed. The original photo assessment needs revalidation; no issue is automatically marked resolved.</p>}
            <ul>{workflow.site_draft.draft_refinement.quality_review.issues.map((row,index)=><li key={index}>
              {row.code} · {row.target_ids.join(', ')}{row.violation_m!==undefined?` · estimated violation ${row.violation_m} m`:''}</li>)}</ul>
            <p>View or edit the current Twin. {workflow.site_draft.progressive_twin?.unresolved.length?
              'Unresolved hazards keep SIM and REAL tasks locked.':'A requested SIM task needs separate current geometry and safety checks.'}
              No motion starts automatically; photo/world alignment and REAL readiness are unverified.</p>
          </section>}
          {workflow?.site_draft&&<details><summary>Room inventory and scene details</summary><RoomInventory inventory={workflow.site_draft.room_inventory} photo={workflow.photo_inventory !== undefined ? workflow.photo_inventory : workflow.site_draft.photo_inventory} edit={idleFlow ? advanced : undefined}/></details>}
          {idleFlow&&workflow?.phase==='restore_review_required' && savedDraft && <section className="chat-question">
            <p>A saved scene is available in this project.</p><small>Reopen its original input and edit history. This does not start simulation or a robot.</small>
            <div><button disabled={busy || !!delivery || !connected} onClick={() => void submit({action:'resume',request_id:crypto.randomUUID(),
              expected_scene_revision:savedDraft.revision,expected_input_revision:savedDraft.input_revision!})}>Reopen saved scene</button></div>
          </section>}
          {!state?.messages.length && <div className="chat-welcome"><h1>Build your Digital Twin</h1><p>Describe a space or upload a photo to build your Twin.</p><p>Text chat first. Nothing moves just by opening this page.</p></div>}
          {turns.map(turn=><section key={turn.id} className="chat-turn" data-turn-id={turn.id}>
          {turn.messages.map(message => <article key={message.message_id} className={`chat-message ${message.role}`}>
            <small>{message.role === 'user' ? 'You' : 'TwinPulse'} · {message.status}</small>
            {!turn.cards.some(card => card.message_id === message.message_id&&card.kind!=='generation_approval') && <p>{message.content}</p>}
            {message.attachments.map(a => <div className="chat-attachment-name" key={a.name}>{a.preview_url && <AuthenticatedConversationImage api={api} url={a.preview_url} alt={a.name}/>}<span>▧ {a.name}</span></div>)}
          </article>)}
            {turn.cards.filter(card=>card.kind!=='generation_approval').map(card => <ActionCard key={card.id} card={card}
              current={card.id===waitingCard?.id}
              busy={!sceneObservationFresh || busy || !!delivery || !connected || (['robot_qualification','robot_observation','robot_recheck','robot_initialize'].includes(card.kind)&&!state?.robot_preparation?.owned)} act={choose}/>)}
          {job && turn.id===generationTurn && <section className="chat-tool-progress" role="status"><strong>Scene generation · {job.state}</strong>
            {job.state==='completed'?<details><summary>Generation summary</summary><p>{job.summary}</p></details>:<p>{job.summary}</p>}
            {job.progress&&<p>Stage: {generationActivityLabel(job)} · {job.progress.elapsed_s??0} s · Repairs: {job.progress.repair_count??0}/{job.progress.max_repairs??0}</p>}
            {retentionLabel&&<small aria-label="Partial scene retention recheck">{retentionLabel}</small>}
            {inventoryWork&&<div role="status" aria-label="Inventory work progress">
              <p>{inventoryWork.inventory_planned?`${inventoryWork.parameterized_count} of ${inventoryWork.inventory_count} objects parameterized · ${inventoryWork.pending_count} awaiting parameters`:`Observed inventory retained · ${inventoryWork.observed_instances} provisional instances · inventory not planned · 0 objects parameterized`} · batches of {inventoryWork.parameter_batch_size}</p>
              <details className="generation-storage-details"><summary>Storage details</summary>
              {completedDraftSaved&&<p>Scene draft saved. Photo quality, simulation and physical execution require separate checks.</p>}
              {!completedDraftSaved&&inventoryCheckpointSaved(inventoryWork)&&<p>Resume checkpoint saved. Resume data is retained; this does not confirm an accepted saved scene. Continue only unfinished work. No automatic restart or robot movement.</p>}
              {!completedDraftSaved&&acceptedSavedScene&&<p>{acceptedSavedScene.partial?'Saved partial scene':'Accepted scene saved separately'}. Scene storage and the resume checkpoint have separate acceptance.</p>}
              {!inventoryWork.parameters_complete&&<p>Incomplete generation, not a verified scene. Pending objects have not been discarded.</p>}
              </details>
            </div>}
            <details className="generation-validation-details"><summary>Validation details · estimates only</summary>
            {(job.error?.diagnostics?.repair_decision??job.progress?.repair_decision)?.decision==='advanced_checks'&&
              <p>Correction advanced to the next checks. The scene still needs correction; it is not ready to Run.</p>}
            {(job.error?.diagnostics?.repair_decision??job.progress?.repair_decision)?.decision==='exploring'&&
              <p>Exploring an unpublished layout within the remaining repair budget. The best checked candidate is retained.</p>}
            {(job.error?.diagnostics?.repair_decision??job.progress?.repair_decision)?.branch_abandoned&&
              <p>Exploration ended. The best checked candidate was restored; unresolved checks remain.</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.approximate_draft==='passed'&&
              <p>Approximate draft checks passed. Photo quality, simulation and physical execution have separate checks.</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.approximate_draft==='partial'&&
              <p>{acceptedSavedScene?'Accepted partial scene saved separately.':'Partial candidate checks passed; accepted scene storage is not confirmed.'} Refinement remains; this is not full-scene or motion validation.</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.Isaac_Build==='preview_passed'&&
              <p>Current Isaac preview was captured. Visual quality review is reported separately. This is not a simulation Run or robot test.</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.photo_quality==='consistent'&&
              <p>Reviewed visual checks are consistent with the photo. Dimensions remain estimated, not measured.</p>}
            {instances&&instances.expanded_groups>0&&<p>{instances.effective_object_count} provisional object instances recorded in inventory. Repeated groups were expanded; individual positions and support remain unverified.</p>}
            {instances&&(instances.status==='count_partially_unverified'||instances.status==='legacy_count_unverified')&&
              <p>Object counts remain partly unverified. This is an approximate inventory, not complete photo coverage.</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.photo_quality==='needs_revision'&&
              <p>{job.state==='running'
                ? 'Correcting observed photo layout conflicts within the shared repair budget. Geometry will be checked again; image/render fidelity is not confirmed.'
                : acceptedSavedScene?'Photo layout conflicts remain in the saved approximate draft. Review or edit the Twin; photo fidelity is not confirmed.'
                : 'Photo layout conflicts remain. Correction stopped without accepting a scene; see the stop reason.'}</p>}
            {(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.photo_quality==='uncertain'&&
              <p>{(job.error?.diagnostics?.stage_acceptance??job.progress?.stage_acceptance)?.Isaac_Build==='preview_passed'
                ? 'The current render was reviewed, but some visual checks remain uncertain. Dimensions are not measured.'
                : 'Photo fidelity remains uncertain: support relationships, scale and the current 3D render still need review.'}</p>}
            {workflow?.mode === 'explicit_fixture' && <small>Explicit deterministic test provider — not a new photo interpretation or physical validation.</small>}
            </details>
            <details><summary>Tool details</summary><p>Existing ProductWorkflow → configured provider → validated ToolCatalog.</p><p>Operation: {job.operation_id}</p><p>Last progress: {job.last_progress_at}</p>
              {!!(job.error?.diagnostics?.scope_decision??job.progress?.scope_decision)?.accepted.length&&
                <p>Host-approved related objects: {(job.error?.diagnostics?.scope_decision??job.progress?.scope_decision)?.accepted.map(row=>`${row.id} (${row.reason_code})`).join(', ')}. Explicit measurements and observed identities remain protected.</p>}
              {!!attemptDiagnostic?.attempts?.length&&<section aria-label="Generation attempt history">
                <p>Recorded attempts: {attemptDiagnostic.attempts.length}/{attemptDiagnostic.attempts_total??attemptDiagnostic.attempts.length}{attemptDiagnostic.attempts_truncated?' · Additional attempts omitted by the display bound.':''}</p>
                <ol>{attemptDiagnostic.attempts.map((attempt,index)=><li key={attempt.attempt_id??index}>
                  {attempt.stage??'unavailable'} · {attempt.role??(attempt.repair?'repair':'initial')} · {attempt.status??'unknown'} · Validation: {attempt.validation??'not recorded'}
                  {attempt.validation_code&&` · ${attempt.validation_code}`}
                  {attempt.patch_shape&&` · Patch format: ${attempt.patch_shape}`}
                  {attempt.patch_effect&&` · Change: ${attempt.patch_effect}`}
                  {attempt.candidate_validation&&` · Full scene check: ${attempt.candidate_validation}`}
                  <small> · Attempt ID: {attempt.attempt_id??'not recorded'}</small>
                </li>)}</ol>
              </section>}
              {job.progress?.budget?.cumulative_requests!==undefined&&<p>Cumulative approved actions: {job.progress.budget.cumulative_requests} requests · {job.progress.budget.cumulative_active_s??0}s active time.</p>}
              {job.progress?.budget&&<p>API requests: {job.progress.budget.requests??0}/{job.progress.budget.max_requests??0} · Repairs: {job.progress.budget.repairs??0}/{job.progress.budget.max_repairs??0} · Remaining: {job.progress.budget.remaining_s??0} s{job.progress.budget.stop_reason&&` · Stopped: ${job.progress.budget.stop_reason}`}</p>}
              {job.error?.diagnostics&&<p>Failed stage: {job.error.diagnostics.stage??'not observed'} · model: {job.error.diagnostics.model_id??'not observed'} · output budget: {job.error.diagnostics.max_tokens??'not observed'} · elapsed: {job.error.diagnostics.elapsed_s??'not observed'} s · finish: {job.error.diagnostics.finish_reason??'not received'}</p>}
              {(job.error?.diagnostics?.repair_no_progress||job.progress?.repair_no_progress)&&<p>Repair made no progress: the corrected candidate repeated the failed content. No further automatic retry.</p>}
              {(job.error?.diagnostics?.scene_contract??job.progress?.scene_contract)?.issues.map((issue,index)=><p key={index}>{issue.code} · {issue.path??'$'}
                {!!issue.target_ids?.length&&` · Object: ${issue.target_ids.join(', ')}`}
                {issue.actual_count!==undefined&&` · Count: ${issue.actual_count}`}
                {issue.maximum!==undefined&&` · Capacity: ${issue.maximum}`}
                {issue.structural_metadata_count!==undefined&&` · Separate metadata: ${issue.structural_metadata_count}`}
                {issue.actual_m!==undefined&&` · Current: ${issue.actual_m} m`}
                {issue.expected_bounds_m&&` · Allowed: ${issue.expected_bounds_m.min_m??'—'} to ${issue.expected_bounds_m.max_m??issue.expected_bounds_m.max_top_m??issue.expected_bounds_m.max_height_m??'—'} m`}
                {issue.geometry_values_m?.bottom_m!==undefined&&` · Bottom: ${issue.geometry_values_m.bottom_m} m`}
                {issue.geometry_values_m?.support_top_m!==undefined&&` · Support top: ${issue.geometry_values_m.support_top_m} m`}
                {issue.violation_m!==undefined&&` · Violation: ${issue.violation_m} m`}
              </p>)}
              {(job.error?.diagnostics?.scene_contract?.checks??job.progress?.scene_contract?.checks??job.progress?.geometry_checks?.checks)?.map(check=>
                <p key={check.check_id}>{check.check_id}: {check.status}{check.blocked_by.length>0&&` · waiting for ${check.blocked_by.join(', ')}`}</p>)}
              {((job.error?.diagnostics?.scene_contract??job.progress?.scene_contract)?.blocked_checks.length??0)>0&&
                <p>Dependent checks wait for a corrected candidate: {(job.error?.diagnostics?.scene_contract??job.progress?.scene_contract)?.blocked_checks.join(', ')}</p>}
              <p>No token streaming is claimed by this structured generation gateway.</p></details>
            {generationRetryVisible&&(job.state==='failed'||state?.budgeted_generation_available&&['cancelled','interrupted'].includes(job.state))&&<>
              <small>{generationSettling?generationSettlingMessage:resumePresentation!.explanation}</small>
              <button disabled={!sceneObservationFresh||!connected||busy||!!delivery||projectActivity.busy||generationSettling} onClick={()=>void submit({action:'generation_retry',request_id:crypto.randomUUID(),operation_id:job.operation_id})}>{resumePresentation!.label}</button>
            </>}
          </section>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&hasRobot&&inspection&&(inspection.state!=='NOT_STARTED'||canReviewInspection)&&<section className="chat-question" aria-label="Twin inspection status">
            <strong>Twin inspection · {inspection.state.replaceAll('_',' ')}</strong>
            {inspection.readiness&&!inspection.readiness.ready&&<p role="status">{inspection.readiness.code}</p>}
            {inspection.busy&&<p role="status">Survey and alignment only · {(inspection.summary?.elapsed_s??inspection.elapsed_s??0).toFixed(1)} s · no goal destination</p>}
            {inspection.diagnostics&&<p>{inspection.diagnostics.stage} · {inspection.diagnostics.view_count} views · {inspection.diagnostics.alignment_status} · {inspection.diagnostics.reason}</p>}
            {inspection.state==='SURVEY_COMPLETE'&&<p>Report saved. Alignment candidate only; the final pose is historical, not current navigation permission.</p>}
            {inspection.photo_correction&&<p>Wall correction · {inspection.photo_correction.status.replaceAll('_',' ')}. Original room preserved; derived revision {inspection.photo_correction.effective_revision.slice(0,12)}. Display progress is separate below; no goal travel approved.</p>}
            {inspection.summary&&<small>Observed status updates every 5 s; faults are immediate. Battery: {inspection.summary.battery_status.replaceAll('_',' ')}.</small>}
            {inspection.error&&<p role="alert">{inspection.error_stage}: {inspection.error}</p>}
            {inspection.cleanup_error&&<p role="alert">Cleanup: {inspection.cleanup_error}</p>}
            {inspection.report_error&&<p role="alert">Report: {inspection.report_error}</p>}
            {canReviewInspection&&<button type="button" disabled={!connected}
              onClick={()=>void submit({action:'inspection_check',request_id:crypto.randomUUID()})}>Refresh inspection readiness · no robot command</button>
            }
          </section>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&<CurrentGoalReview state={state.navigation}/>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&idleFlow&&state.inspection_display&&<section className="chat-question" aria-label="Saved survey room">
            <strong>Saved survey · historical candidate</strong>
            <p>No current robot position or movement permission is restored.</p>
            {!state.inspection_display.ready&&<p role="alert">{state.inspection_display.code}</p>}
            {inspectionBuild&&inspectionBuild.descriptor.manifest_sha256===state.inspection_display.descriptor.manifest_sha256&&state.inspection_display.ready?
              <ChatInspectionBuild key={inspectionBuild.descriptor.manifest_sha256} api={api} display={inspectionBuild} product={workflowFresh&&connected?product:null} report={setError}/>:
              <button type="button" disabled={busy||!connected||!state.inspection_display.ready||inspection?.busy}
                onClick={()=>setInspectionBuild(state.inspection_display)}>Display saved survey room · no movement</button>}
          </section>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&realBuild&&state.room_build?.operation_id===realBuild.operation_id&&
            state.room_build.scene_revision===realBuild.scene_revision&&<ChatRoomBuild key={realBuild.operation_id}
              api={api} build={realBuild} product={workflowFresh&&connected?product:null} report={setError}/>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&idleFlow&&state.room_build&&needsRoomDisplay&&<button type="button" disabled={busy||!connected}
              onClick={()=>setRealBuild(state.room_build)}>Display current room in Isaac · no robot command</button>}
          {turn.id===generationTurn&&state?.mode==='REAL'&&hasRobot&&<ChatRobotStatus state={robotControlState} api={api} report={setError}
            checkBusy={busy||!!delivery||!connected} check={idleFlow&&job?.state!=='failed'&&!needsRoomDisplay&&state.robot_preparation?.state!=='LINKED'?()=>void submit({action:'robot_check',request_id:crypto.randomUUID()}):undefined}
            transfer={(kind,job_id)=>void submit({action:'robot_transfer',request_id:crypto.randomUUID(),expires_at_ms:Date.now()+1500,kind,job_id})}/>}
          {turn.id===pendingEditTurn&&state?.queued_edit && <section className="chat-tool-progress" role="status"><strong>Pending edit</strong><p>{state.queued_edit.text}</p><small>The current generation is unchanged. A preview will be offered after it ends.</small></section>}
          {turn.id===feedbackTurn&&feedback&&<section className="chat-tool-progress" aria-label="Scene feedback status" role="status">
            <strong>Scene feedback · {feedback.state.replaceAll('_',' ')}</strong>
            <p>Proposal only. Preview, engine apply, disk save and current 3D display are checked separately. No motion is authorized.</p>
            {feedback.progress&&<p>{feedback.progress.stage??'planner'} · {feedback.progress.status??'waiting'} · {feedback.progress.elapsed_s??0} s · {feedback.progress.budget?.requests??0}/{feedback.progress.budget?.max_requests??1} requests · repairs {feedback.progress.budget?.repairs??0}/{feedback.progress.budget?.max_repairs??0}{feedback.progress.budget?.stop_reason&&` · ${feedback.progress.budget.stop_reason}`}</p>}
            {feedback.error&&<p role="alert">{feedback.error}</p>}
            {workflow?.mode!=='live_provider'&&<small>Explicit scripted/offline proposal provider — not a fresh model or photo interpretation.</small>}
            {feedbackBusy&&<button type="button" disabled={busy||!!delivery} onClick={()=>void submit({action:'cancel',request_id:crypto.randomUUID(),operation_id:feedback.operation_id})}>Stop feedback response</button>}
          </section>}
          {turn.cards.some(card=>card.id===waitingCard?.id)&&waitingCard?.kind==='scene_edit'&&state?.scene_edit_preview&&<section className="chat-question" aria-label="Scene edit before and after">
            <strong>Before / after preview</strong><p>Previous task plans will be invalidated. Original input is retained; physical validation has not run.</p>
            {Array.from(new Set([...Object.keys(state.scene_edit_preview.affected_before),...Object.keys(state.scene_edit_preview.affected_after)])).map(id=>{
              const before=state.scene_edit_preview!.affected_before[id],after=state.scene_edit_preview!.affected_after[id];
              return <p key={id}>{id}: {before?`position ${before.position_m.join(', ')} · size ${before.dimensions_m.join(', ')}`:'not materialized'} → {after?`position ${after.position_m.join(', ')} · size ${after.dimensions_m.join(', ')}`:'not materialized'} m</p>;
            })}
            <details><summary>Retained inventory and revision changes</summary><pre>{JSON.stringify({parent_state:state.scene_edit_preview.parent_state_sha256,result_state:state.scene_edit_preview.result_state_sha256,inventory:state.scene_edit_preview.inventory_changes},null,2)}</pre></details>
          </section>}
          {turn.id===generationTurn&&workflow?.phase==='draft_ready'&&workflow.site_draft&&typeof api.sceneSensorContext==='function'&&
            <details className="chat-question sensor-correction-panel" key={`${state?.project_id}:${workflow.site_draft.input_revision}`}><summary>Sensor correction</summary>
            <p>Optional saved-scan review · no connection or motion starts here.</p>
            <SceneSensorFeedback api={api} revision={workflow.site_draft.revision}
              stateSha={workflow.site_draft.scene_state_sha256??null} enabled={baseIdleFlow&&!goalBusy&&!taskLoop?.worker_active}
              fresh={sceneObservationFresh}
              result={state?.scene_sensor_review} review={action=>void submit(action)}/></details>}
          {turn.id===transactionTurn&&editTransaction&&<section className="chat-question" aria-label="Twin update status" role="status">
            <strong>Twin update · {editTransaction.state.replaceAll('_',' ')}</strong>
              <p>Engine ACK: {editTransaction.engine_acknowledged?'confirmed':'not confirmed'} · Disk commit: {editTransaction.durable_committed?'confirmed':'not committed'} · Transaction 3D frame: {editTransaction.current_frame?'confirmed':'not currently confirmed'}</p>
              {!editTransaction.current_frame&&['COMMITTED','ROLLED_BACK'].includes(editTransaction.state)&&
                <p>The original transaction frame receipt is separate from a later View current Twin. Check the current viewport and its latest frame receipt; reopening does not restore the original transaction frame confirmation.</p>}
              {editTransaction.state==='ROLLED_BACK'&&<p>Previous saved Twin restored · Compensation ACK: {editTransaction.compensation_acknowledged?'confirmed':'not confirmed'}. Transaction frame above refers to that restored revision, not the rejected edit.</p>}
            {editTransaction.error&&<p role="alert">{editTransaction.error}</p>}
            {editTransaction.execution_id&&<button type="button" onClick={()=>{setDiagnosticExecution(editTransaction.execution_id!);setShowDiagnostics(true);}}>View Twin update diagnostics</button>}
            {editTransaction.state==='ENGINE_STATE_UNKNOWN'&&<><p>Inspect the idle engine and retained saved revision. This explicit recovery sends one Build of the durable revision; it never resumes Run or a model request.</p>
              <button type="button" disabled={!sceneObservationFresh||recoveringEdit||busy||!connected||!engineReady} onClick={()=>{
                setRecoveringEdit(true);void api.recoverSceneEdit().then(()=>api.conversation()).then(apply).catch(e=>setError(errorText(e))).finally(()=>setRecoveringEdit(false));
              }}>{recoveringEdit?'Recovery requested…':'Recover saved Twin in Isaac'}</button></>}
            {editTransaction.state==='COMMITTED'&&idleFlow&&<button type="button" disabled={!connected} onClick={()=>void submit({action:'message',request_id:crypto.randomUUID(),text:'Undo',mode:'change',attachment:null})}>Undo last edit · preview</button>}
          </section>}
          {simulationHasOrigin&&turn.id===simulationTurn&&simulationCard}
          </section>)}
          {visibleError && (visibleError===dismissed ? <details className="chat-earlier-error"><summary>Earlier issue · dismissed</summary><p>{visibleError}</p></details> :
            <div className="chat-inline-error"><strong>{delivery ? 'Delivery unknown' : 'Needs attention'}</strong><p>{visibleError}</p></div>)}
        </div>
        {newUpdates && <button className="chat-new-updates" onClick={() => { nearBottom.current = true; if (list.current) list.current.scrollTop = list.current.scrollHeight; setNewUpdates(false); }}>New updates ↓</button>}
        <form ref={composerForm} className="chat-composer" onSubmit={e => { e.preventDefault(); void send(); }}
          onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); attachment(e.dataTransfer.files[0]); }}>
          {sceneOperationBusy&&<p className="chat-composer-wait" role="status">Isaac preparation is still in progress. Your text and attachment are kept. Status and Stop remain available.</p>}
          {librarySource&&<div className="chat-image-preview"><span>{librarySource.name} · Library asset source · scene draft kept</span><button type="button" onClick={()=>setShowLibrary(true)}>Open Library import</button><button type="button" onClick={()=>setLibrarySource(null)}>Remove Library attachment</button></div>}
          {file && <div className="chat-image-preview">{thumbnail && <img src={thumbnail} alt="Attached image preview"/>}<span>{file.name} · {imageRole==='asset_reference'?'Library asset reference':'environment reference photo'}</span>
            <label>Image role<select aria-label="Attached image role" value={imageRole} onChange={e=>{const role=e.target.value as typeof imageRole;editImageRole(role);if(role==='asset_reference')setShowLibrary(true);}}><option value="environment_reference">Environment reference photo</option><option value="asset_reference">Library asset reference</option></select></label><button type="button" onClick={() => {editComposerFile(null);editImageRole('environment_reference');}}>Remove image</button></div>}
          {projectActivity.busy&&<p role="status">Opening the selected conversation · input and sending are paused.</p>}
          <textarea ref={composerInput} disabled={projectActivity.busy} rows={1} aria-label="Message TwinPulse" placeholder="Message TwinPulse…" maxLength={8000} value={text} onChange={e => {composerEdited.current=true;editComposerText(e.target.value);}}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); void send(); } }}/>
          <footer><input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp,.step,.stp,.iges,.igs,.usd,.usda,.usdc,.usdz,.obj,.stl,.ply,.gltf,.glb" hidden onChange={e => { attachment(e.target.files?.[0]); e.target.value = ''; }}/>
            <button type="button" onClick={() => fileInput.current?.click()} aria-label="Attach image">＋ Attach</button>
            <label className="scene-operation-controls"><span className="sr-only">Scene operation</span><select aria-label="Scene operation" value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="new">New environment</option><option value="add">Add to current</option><option value="change">Change current</option></select></label>
            <span role="status">{busy ? 'Sending…' : delivery ? 'Check saved result' : pendingChoice ? 'Answer the question above' : activeJob ? 'Generating…' : 'Enter to send · Shift+Enter for a new line'}</span>
            {activeJob && <button type="button" disabled={busy || !!delivery} onClick={() => void submit({action:'cancel',request_id:crypto.randomUUID(),operation_id:job.operation_id})}>Stop response</button>}
            <button type="submit" disabled={projectActivity.busy || busy || !!delivery || !connected || (!text.trim() && !file &&!librarySource) ||
                (!sceneObservationFresh&&(!!file||!isConversationStatusRequest(text)&&!isConversationStopRequest(text))) ||
                (sceneOperationBusy&&(!!file||!isConversationStatusRequest(text)&&!isConversationStopRequest(text))) ||
                (!!pendingChoice && waitingCard?.kind!=='scene_edit_clarify' && !isConversationStatusRequest(text) && !isConversationStopRequest(text) && !isConversationChoiceRequest(text, waitingCard?.kind)) ||
                ((feedbackBusy||editLocked)&&!isConversationStatusRequest(text)&&!isConversationStopRequest(text)) ||
                (!!activeJob && !isConversationStatusRequest(text) && (mode==='new' || !!file || !!state?.queued_edit))}>Send</button>
          </footer>
          {delivery && <button type="button" onClick={() => {
            const original=deliveryOwner.current;
            if(!original||original.request_id!==delivery.request_id||pendingDeliveryCheck.current)return;
            const check={request_id:original.request_id,generation:++deliveryCheckGeneration.current};pendingDeliveryCheck.current=check;
            const epoch=contextEpoch.current,context=api.context;
            const current=()=>composerApi.current===api&&contextEpoch.current===epoch&&api.context===context&&
              deliveryOwner.current?.request_id===check.request_id&&deliveryCheckGeneration.current===check.generation&&pendingDeliveryCheck.current===check;
            void api.conversation().then(next => {
            if(!current())return;
            if (next.accepted_request_ids.includes(original.request_id)) acknowledge(next, original);
            else { apply(next); setError('No saved receipt is visible yet. Delivery remains unknown; this request has not been repeated. Your draft is kept.'); }
          }).catch(e => {if(current())setError(errorText(e));})
            .finally(()=>{if(pendingDeliveryCheck.current===check)pendingDeliveryCheck.current=null;});}}>Check saved result · no re-execution</button>}
        </form>
      </section>
      {showTwin&&<div className="chat-twin-splitter" role="separator" tabIndex={0} aria-label="Resize chat and Twin" aria-orientation="vertical"
        aria-controls="chat-conversation-pane digital-twin-pane" aria-valuemin={25} aria-valuemax={70} aria-valuenow={chatShare}
        aria-valuetext={`Chat ${chatShare} percent, Twin ${100-chatShare} percent`}
        onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();splitPointer.current=event.pointerId;
          event.currentTarget.setPointerCapture?.(event.pointerId);setLayoutVersion(value=>value+1);}}
        onPointerMove={event=>{if(splitPointer.current!==event.pointerId)return;const bounds=columns.current?.getBoundingClientRect();
          if(bounds&&bounds.width>0)updateSplit((event.clientX-bounds.left)/bounds.width*100);}}
        onPointerUp={()=>{splitPointer.current=null;}} onPointerCancel={()=>{splitPointer.current=null;}} onLostPointerCapture={()=>{splitPointer.current=null;}}
        onKeyDown={event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();setLayoutVersion(value=>value+1);
          updateSplit(event.key==='Home'?25:event.key==='End'?70:chatShare+(event.key==='ArrowRight'?1:-1)*(event.shiftKey?10:2));}}}/>}
      {showTwin && <aside id="digital-twin-pane" className="chat-twin-panel" aria-label="Digital Twin">
        <header className="chat-twin-heading"><h2>Digital Twin</h2><small>{engineReady ? 'Isaac connected' : 'Waiting for Isaac'}</small></header>
        {state?.project_id ? <TwinViewport api={api} projectId={state.project_id} generation={job} appConnected={connected}
          controlView={controlView}
          robotFleet={fleet??undefined} fleetAvailable={fleetAvailable} onRobotSelect={selectFleetRobot}
          savedScene={acceptedSavedScene}
          sourcePhoto={sourceAttachment?.preview_url?{url:sourceAttachment.preview_url,name:sourceAttachment.name}:null}
          report={setViewerFault} diagnose={id=>{setDiagnosticExecution(id);setShowDiagnostics(true);}}/> : <p role="status">Connecting to the App before starting viewer reception…</p>}
        <RobotFleet api={api} state={fleet} selectedId={fleetSelectedId??fleet?.focused_robot_id??null} onSelect={selectFleetRobot}
          onChange={applyFleet} available={fleetAvailable} error={fleetError} drawerOpen={fleetDrawerOpen} onClose={()=>setFleetDrawerOpen(false)} selectionPending={fleetSelecting}
          layoutVersion={`${layoutVersion}:${chatShare}:${controlView}:${showProjects}:${showTwin}`}/>
        <details className="chat-twin-mission-details"><summary>Scene and mission details</summary><dl><dt>Scene</dt><dd>{workflow?.phase ?? 'Not observed'}</dd><dt>Robot</dt><dd>{simSnapshot ? 'Burger · simulated' : state?.robot_id ?? (state?.mode === 'SIM' ?
          state.cards.some(card=>card.kind==='robot_selection'&&card.state==='waiting')?'Simulation asset selection pending':'Environment only · no robot selected' : 'Not selected')}</dd>
          <dt>Battery</dt><dd aria-label="Mission battery status">{simSnapshot || state?.mode==='SIM' ? 'Not applicable · SIM' : goalJob?
            missionTelemetry?.battery?`${missionTelemetry.battery.estimated_percent.toFixed(1)}% estimated · ${missionTelemetry.battery.voltage_v.toFixed(2)} V · recent worker receipt`:'Current receipt unavailable':state?.robot_preparation?.record?.battery ?
            `${state.robot_preparation.record.battery.estimated_percent.toFixed(1)}% estimated · snapshot` : 'Not observed'}</dd>
          <dt>Next waypoint</dt><dd aria-label="Mission next waypoint">{missionTelemetry?.next_waypoint?
            `${missionTelemetry.next_waypoint.index+1}/${missionTelemetry.next_waypoint.count} · (${missionTelemetry.next_waypoint.xy_room.map(x=>x.toFixed(2)).join(', ')}) m`:'Current receipt unavailable'}</dd>
          <dt>Robot connection</dt><dd>{state?.mode==='REAL'?missionTelemetry?'Worker telemetry received · transport delay unmeasured':goalJob?.worker_active?'Worker active · fresh telemetry unavailable':state.robot_preparation?.state.replaceAll('_',' ')??'Unavailable':'Not required'}</dd>
          <dt>Task</dt><dd>{state?.mode==='REAL'?taskLoop?`Repeat A ↔ B · ${taskLoop.state} · leg ${taskLoop.leg} to ${taskLoop.destination}`:goalJob?`Goal · ${goalJob.state}`:inspection?.owned?`Inspection · ${inspection.state.replaceAll('_',' ')}`:state.robot_preparation?.stage.replaceAll('_',' ')??'No physical task':taskStatus}</dd></dl></details>
      </aside>}
      </>}
    </main>
    </div></Activity></div>
  </div>;
}
