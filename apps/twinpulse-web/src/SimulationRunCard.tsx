// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useImperativeHandle,useRef,useState,type Ref} from 'react';
import {ApiError, type TwinPulseApi} from './api';
import type {Operation} from './engine-contracts';
import type {ProductState} from './types';
import type {SimulationReview} from './conversation-types';
import {SimulationRouteView} from './SimulationRouteView';

function roomReady(state:ProductState,revision:string):boolean{
  const snapshot=state.snapshot;
  return state.engine_connected && state.lease_owned && !!snapshot && !snapshot.safety_state &&
    (!state.build_view || state.build_view.applied_revision!==revision || state.build_view.status==='succeeded') &&
    snapshot.applied_revision===revision && ['built','paused','completed'].includes(snapshot.runtime_state);
}
function runReady(state:ProductState,revision:string):boolean{
  return roomReady(state,revision) && !!state.snapshot?.capabilities.includes('site_simulation_v1');
}
function resetReady(state:ProductState|null,revision:string):boolean{
  const snapshot=state?.snapshot;
  return !!state?.engine_connected&&state.lease_owned&&!!state.control_lease_id&&!!snapshot&&
    snapshot.project_id===state.project_id&&snapshot.engine_session_id===state.engine_session_id&&snapshot.stage_epoch===state.stage_epoch&&
    snapshot.applied_revision===revision&&snapshot.runtime_state!=='running'&&snapshot.permitted_commands.includes('reset')&&
    !state.operations.some(op=>op.project_id===state.project_id&&op.engine_session_id===state.engine_session_id&&['accepted','running','unknown'].includes(op.status));
}

export interface SimulationPlan {
  plan_id:string; scene_revision:string; mode:'SIM'; asset_id:string;
  start:number[]; goal:number[]; route:number[][]; yaw_rad:number;
  max_linear_mps:number; max_angular_rps:number; physical_authority:false;
}

function coordinate(text:string):number[]{
  const match=text.trim().match(/^\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?$/);
  if(!match)throw new Error('Enter an explicit x, y coordinate in metres.');
  return [Number(match[1]),Number(match[2])];
}

export function SimulationRunCard({api,revision,artifactId,product,report,review,stopHandle,showActions=true,browserBlocked=false,chatPending=false,taskBlocked=false,operationBusyChanged}:{api:TwinPulseApi;revision:string;artifactId:string;product:ProductState|null;report:(text:string)=>void;review?:SimulationReview|null;stopHandle?:Ref<{stop:()=>void}>;showActions?:boolean;browserBlocked?:boolean;chatPending?:boolean;taskBlocked?:boolean;operationBusyChanged?:(busy:boolean)=>void}){
  const [start,setStart]=useState('0, 0');
  const [goal,setGoal]=useState('0, 0.5');
  const [plan,setPlan]=useState<SimulationPlan|null>(null);
  useEffect(()=>{if(taskBlocked){setPlan(null);setPhase('Draft viewing is available. Refinement and task-impact checks are pending.');}},[taskBlocked]);
  const [routeView,setRouteView]=useState<SimulationReview|null>(null);
  const consumedReview=useRef<string|null>(null);
  const resetInvalidatedReview=useRef<string|null>(null);
  const preparedGeneration=useRef<string|null>(null);
  const [phase,setPhase]=useState('Choose a start and goal to preview a SIM route.');
  const [busy,setBusy]=useState(false);
  const [pending,setPending]=useState<string|null>(null);
  const [receiptCheck,setReceiptCheck]=useState(0);
  const [receiptExpired,setReceiptExpired]=useState(false);
  const lease=useRef<string|null>(null);
  const locked=useRef(false);
  const stopping=useRef(false);
  const [stopPending,setStopPending]=useState(false);
  const [resetUnconfirmed,setResetUnconfirmed]=useState(false);
  const mounted=useRef(true);
  const owner=useRef({api,revision,projectId:product?.project_id});owner.current={api,revision,projectId:product?.project_id};
  const snapshot=product?.engine_connected?product.snapshot:null;
  const engineIdentity=useRef<string|null>(null);
  const engineFault=!!snapshot && (!!snapshot.safety_state || ['error','unstable','off_route','stage_invalid','disconnected'].includes(snapshot.runtime_state));
  const displayPending=product?.build_view?.applied_revision===revision && product.build_view.status!=='succeeded';
  const currentDisplayed=!!product?.engine_connected && product.snapshot?.applied_revision===revision &&
    product.build_view?.applied_revision===revision && product.build_view.status==='succeeded';
  useEffect(()=>{
    const identity=snapshot?`${snapshot.engine_session_id}/${snapshot.stage_epoch}`:null;
    if(engineIdentity.current && (!identity || identity!==engineIdentity.current) || engineFault){
      setPlan(null);setRouteView(null);
      setPhase('Engine control changed or failed. Review a fresh route after recovery; no automatic resume.');
    }
    engineIdentity.current=identity;
  },[product?.engine_connected,snapshot?.engine_session_id,snapshot?.stage_epoch,engineFault]);
  const live=!!snapshot?.telemetry_available && !!snapshot.run_id && snapshot.applied_revision===revision &&
    snapshot.capabilities.includes('site_simulation_v1');
  const moving=snapshot?.runtime_state==='running' && live;
  useEffect(()=>{setPlan(null);setPending(null);setRouteView(null);consumedReview.current=null;resetInvalidatedReview.current=null;setResetUnconfirmed(false);},[revision]);
  useEffect(()=>{
    if(taskBlocked){consumedReview.current=null;setPlan(null);setRouteView(null);return;}
    if(!review&&consumedReview.current){consumedReview.current=null;setPlan(null);setRouteView(null);return;}
    if(!review||review.scene_revision!==revision||review.request_id===consumedReview.current||review.request_id===resetInvalidatedReview.current)return;
    consumedReview.current=review.request_id;
    setPlan(review.plan);setRouteView(review);
    if(review.plan){setStart(review.plan.start.map(v=>Number(v.toFixed(3))).join(', '));setGoal(review.plan.goal.map(v=>Number(v.toFixed(3))).join(', '));setPhase('Chat goal reviewed. Select Run simulation to confirm this SIM route.');}
  },[review,revision,taskBlocked]);

  useEffect(()=>{
    mounted.current=true;
    let renewing=false;
    const timer=setInterval(()=>{
      if(!lease.current||renewing)return;
      renewing=true;
      void api.renewLease(lease.current).catch(error=>{
        lease.current=null;
        if(mounted.current){setPlan(null);setPhase('Control lease lost. The engine must stop; no automatic resume.');report(String(error));}
      }).finally(()=>{renewing=false;});
    },750);
    return()=>{mounted.current=false;clearInterval(timer);lease.current=null;operationBusyChanged?.(false);};
  },[api,report,operationBusyChanged]);
  useEffect(()=>{
    if(!pending)return;
    let active=true,inFlight=false;
    const until=Date.now()+45000;
    setReceiptExpired(false);
    const expire=()=>{if(!active)return;active=false;clearInterval(timer);setReceiptExpired(true);
      setPhase('Run receipt is still unconfirmed. Check the saved result; never resend this Run.');
      report('Run receipt was not confirmed within 45 seconds. Execution may have started. Use the read-only check or Stop if running.');};
    const poll=async()=>{
      if(!active||inFlight)return;
      if(Date.now()>=until){expire();return;}
      inFlight=true;
      try{
        const op=await api.simulationOutcome(pending);
        if(!active)return;
        if(op.status==='succeeded'){setPending(null);setPlan(null);setPhase('Run acknowledged. Waiting for live Physics observations…');}
        else if(['failed','expired','cancelled'].includes(op.status)){setPending(null);setPlan(null);report(op.receipt?.message??op.status);}
      }catch{/* No receipt yet. Never re-execute a lost Run request. */}
      finally{inFlight=false;}
    };
    const timer=setInterval(()=>void poll(),750);
    const deadline=setTimeout(expire,45000);void poll();
    return()=>{active=false;clearInterval(timer);clearTimeout(deadline);};
  },[pending,api,receiptCheck,report]);

  const act=async(work:()=>Promise<void>)=>{
    if(locked.current)return;locked.current=true;setBusy(true);operationBusyChanged?.(true);
    try{await work();}catch(error){setPlan(null);setPhase('Needs attention · see the error above.');report(error instanceof Error?error.message:String(error));}
    finally{locked.current=false;if(mounted.current){setBusy(false);operationBusyChanged?.(false);}}
  };
  const preview=()=>void act(async()=>{
    if(resetUnconfirmed)throw new Error('Reset outcome is unconfirmed. Do not start a new simulation task.');
    if(taskBlocked)throw new Error('Check unresolved objects against the task first. Draft viewing is available.');
    setPhase('Checking current room geometry and planning a bounded route…');setPlan(null);
    const actual=live?snapshot!.position_m!.slice(0,2):coordinate(start);
    const destination=coordinate(goal);
    if(live&&Math.hypot(actual[0]-destination[0],actual[1]-destination[1])<.10){
      setPhase('Already at this goal, or within the minimum 0.10 m route distance. Choose another destination in chat or edit the goal. No new movement started.');
      return;
    }
    const result=await api.simulationPlan(revision,actual,destination,live?(snapshot!.yaw_rad??0):0);
    setPlan(result);setPhase('Route reviewed. Run moves only the simulated Burger.');
  });
  const waitOperation=async(op:Operation,confirm?:(current:Operation,state:ProductState)=>boolean)=>{
    const until=Date.now()+45000;
    while(Date.now()<until){
      if(!mounted.current)throw new Error('View closed. Execution was not continued.');
      const state=await api.productState();
      const current=state.operations.find(item=>item.command_id===op.command_id);
      if(current?.status==='succeeded'&&(!confirm||confirm(current,state)))return;
      if(current && !['accepted','running','succeeded'].includes(current.status))throw new Error(current.receipt?.message??current.status);
      await new Promise(resolve=>setTimeout(resolve,200));
    }
    throw new Error('Engine preparation timed out. Check its saved operation; no retry was sent.');
  };
  const prepareRoom=async(previewPlan?:SimulationPlan,forceBuild=false,viewOnly=false)=>{
    setPhase('Preparing the same room in Isaac…');
    const value=await api.acquireLease();lease.current=value.control_lease_id;
    await api.acknowledge(revision);
    let state=await api.productState();
    if(forceBuild || state.snapshot?.applied_revision!==revision){
      const until=Date.now()+6000;
      while(!state.engine_readiness?.site_scene_build_v2?.ready&&Date.now()<until){await new Promise(r=>setTimeout(r,150));state=await api.productState();}
      if(!state.engine_readiness?.site_scene_build_v2?.ready)throw new Error('Isaac has not granted Build readiness.');
      if(previewPlan && !state.snapshot?.capabilities.includes('site_simulation_preview_v1'))
        throw new Error('Updated Isaac adapter is required to display Burger before Run. No Run was sent.');
      await waitOperation(await api.command('build_site_scene',revision,artifactId,previewPlan?.plan_id));
    }
    const readyUntil=Date.now()+18000;
    state=await api.productState();
    // A Build receipt and its applied snapshot arrive independently. Never infer
    // current-scene readiness from the receipt or capability alone.
    setPhase('Waiting for the current room and idle SIM engine observation…');
    const ready=(value:ProductState)=>viewOnly?roomReady(value,revision):runReady(value,revision);
    while(!ready(state)&&Date.now()<readyUntil){
      if(!mounted.current)return;
      if(state.snapshot?.safety_state || ['error','unstable','off_route','stage_invalid','disconnected'].includes(state.snapshot?.runtime_state??''))
        throw new Error(state.snapshot?.safety_reason ?? 'Current engine safety condition blocks this Run. Review a fresh route after recovery.');
      if(state.build_view?.applied_revision===revision && ['failed','unknown'].includes(state.build_view.status))
        throw new Error(state.build_view.phase==='apply' ?
          `Scene apply failed or unconfirmed (${state.build_view.error_code}). No Run was sent.` :
          `Scene apply succeeded, but no current 3D frame was confirmed (${state.build_view.error_code}). No Run was sent.`);
      await new Promise(r=>setTimeout(r,150));state=await api.productState();
    }
    if(!ready(state))
      throw new Error(viewOnly?'Current room display readiness was not observed. No Run was sent.':'Current SIM control readiness was not observed. No Run was sent.');
  };
  // A new accepted generation already authorizes building its owned preview,
  // not motion. This review is supplied only by a fresh acknowledged action.
  useEffect(()=>{
    if(taskBlocked || !review?.plan || review.start_source!=='planned_sim_spawn' ||
        review.request_id===resetInvalidatedReview.current ||
        review.text!=='Generated SIM preview' || review.scene_revision!==revision ||
        !product?.engine_connected || preparedGeneration.current===review.request_id)return;
    preparedGeneration.current=review.request_id;
    void act(async()=>{await prepareRoom(review.plan!,true);if(mounted.current)setPhase('Scene applied in Isaac. Check the current 3D display, review the SIM preview route, then select Run simulation.');});
  },[review,revision,product?.engine_connected,taskBlocked]);
  const run=()=>void act(async()=>{
    if(resetUnconfirmed)throw new Error('Reset outcome is unconfirmed. No Run was sent.');
    if(taskBlocked)throw new Error('Unresolved objects have unverified motion impact. No Run was sent.');
    if(browserBlocked)throw new Error('Browser 3D display is unavailable. No Run command was sent.');
    if(!plan||plan.scene_revision!==revision)throw new Error('Preview the current route first.');
    await prepareRoom(plan);
    if(!mounted.current)return;
    const requestId=crypto.randomUUID();setPending(requestId);setPhase('Run submitted · observing its saved receipt.');
    try{const op=await api.simulationRun(plan.plan_id,revision,requestId);await waitOperation(op);setPending(null);setPlan(null);setPhase('Run acknowledged. Waiting for live Physics observations…');}
    catch(error){
      if(error instanceof ApiError && error.code!=='delivery_unknown'){setPending(null);setPlan(null);}
      setPhase('Run outcome requires checking. No automatic re-execution.');throw error;
    }
  });
  const stop=async()=>{
    if(stopping.current)return;stopping.current=true;setStopPending(true);
    setPhase('Stop requested · waiting for the engine acknowledgement…');
    try{await waitOperation(await api.command('pause',revision));setPlan(null);setPhase('SIM stopped. Preview a new goal to continue.');}
    catch(error){report(error instanceof Error?error.message:String(error));}
    finally{stopping.current=false;if(mounted.current)setStopPending(false);}
  };
  const reset=()=>void act(async()=>{
    if(chatPending||pending||stopPending||stopping.current||resetUnconfirmed||!resetReady(product,revision))throw new Error('Reset requires current idle control permission and no unconfirmed Run or busy operation.');
    const initial=await api.productState();
    if(!resetReady(initial,revision))throw new Error('Current Reset permission changed. No Reset was sent.');
    const identity={projectId:initial.project_id,engine:initial.engine_session_id,epoch:initial.stage_epoch,sequence:initial.snapshot!.sequence,context:api.context};
    const currentOwner=()=>mounted.current&&owner.current.api===api&&owner.current.revision===revision&&owner.current.projectId===identity.projectId&&api.context===identity.context;
    const sameScene=(value:ProductState)=>currentOwner()&&value.engine_connected&&value.project_id===identity.projectId&&
      value.engine_session_id===identity.engine&&value.stage_epoch===identity.epoch&&value.snapshot?.engine_session_id===identity.engine&&
      value.snapshot.project_id===identity.projectId&&value.snapshot.stage_epoch===identity.epoch&&value.snapshot.applied_revision===revision;
    const control=await api.acquireLease();lease.current=control.control_lease_id;
    if(!currentOwner())throw new Error('Scene changed before Reset. No Reset was sent.');
    await api.acknowledge(revision);
    const checked=await api.productState();
    if(!sameScene(checked)||!resetReady(checked,revision))throw new Error('Scene or Reset permission changed before submission. No Reset was sent.');
    identity.sequence=checked.snapshot!.sequence;
    setResetUnconfirmed(true);setPlan(null);setRouteView(null);resetInvalidatedReview.current=review?.request_id??consumedReview.current;consumedReview.current=null;
    setPhase('Reset submitted · waiting for its receipt and a current idle observation…');
    try{
      const operation=await api.command('reset',revision);
      await waitOperation(operation,(completed,state)=>{
        if(!sameScene(state))throw new Error('Scene changed while Reset was pending. Its result is not confirmed here.');
        const receipt=completed.receipt;
        if(completed.command_type!=='reset'||completed.project_id!==identity.projectId||completed.engine_session_id!==identity.engine||
          completed.stage_epoch!==identity.epoch||completed.expected_applied_revision!==revision||!receipt||receipt.command_id!==operation.command_id||
          receipt.command_type!=='reset'||receipt.status!=='succeeded'||receipt.project_id!==identity.projectId||receipt.engine_session_id!==identity.engine||
          receipt.stage_epoch!==identity.epoch||receipt.applied_revision!==revision)throw new Error('Reset receipt identity was not confirmed. No automatic retry.');
        return state.snapshot!.sequence>identity.sequence&&state.snapshot!.runtime_state==='built'&&state.snapshot!.run_id===null;
      });
      if(currentOwner()){setResetUnconfirmed(false);setPhase('Simulation reset confirmed. Preview a fresh route before Run. The saved scene is retained; no motion restarted.');}
    }catch(error){
      if(error instanceof ApiError&&!['delivery_unknown','context_changed'].includes(error.code)&&currentOwner())setResetUnconfirmed(false);
      throw error;
    }
  });
  const resetAllowed=!chatPending&&!busy&&!stopPending&&!pending&&!resetUnconfirmed&&resetReady(product,revision);
  const resetNotice=phase.startsWith('Simulation reset confirmed');
  const status=chatPending?'Preparing the current chat request · Run locked':live&&!busy&&!stopPending&&!resetUnconfirmed&&!resetNotice?`Physics ${snapshot!.runtime_state} · goal distance ${snapshot!.distance_to_goal_m?.toFixed(2)??'unknown'} m`:phase;
  useImperativeHandle(stopHandle,()=>({stop:()=>{if(moving)void stop();else report('No current running SIM task was observed. No Stop success is claimed.');}}));
  return <section className="chat-question" aria-label="Simulation route" data-plan-id={plan?.plan_id??''} data-review-request-id={consumedReview.current??''}>
    <h3>{taskBlocked?'Review your Twin draft':'Run your Twin · SIM only'}</h3><p role="status">{status}</p>
    {live&&!resetUnconfirmed&&!resetNotice&&snapshot!.runtime_state==='completed'&&<p className="sim-completion" role="status">Destination reached · stopped normally. This was one finite route, not continuous roaming. Ask in chat for the next destination.</p>}
    {live&&phase.startsWith('Already at this goal')&&<p role="status">{phase}</p>}
    <small>Existing Burger with PhysX. Coordinates refer to the approximate room, not a measured physical map.</small>
    {!taskBlocked&&<><p>Ask in chat: “Go to the bed” or “Go to x=0 y=1”. Without a saved start, include “from x=0 y=0 to x=0 y=1”. Unsupported goals require clarification; no paid model is called.</p>
    <div><label>Start x, y (m)<input aria-label="SIM start" value={start} disabled={busy||live||!!pending} onChange={e=>{setStart(e.target.value);setPlan(null);}}/></label>
      <label>Goal x, y (m)<input aria-label="SIM goal" value={goal} disabled={busy||moving||!!pending} onChange={e=>{setGoal(e.target.value);setPlan(null);}}/></label></div></>}
    {plan&&<p>{plan.route.length} waypoint(s) · up to {plan.max_linear_mps} m/s · no physical command</p>}
    {plan&&routeView?.text==='Generated SIM preview'&&<p>Initial movement check: {plan.route.reduce((distance,point,index)=>{
      const previous=index?plan.route[index-1]:plan.start;return distance+Math.hypot(point[0]-previous[0],point[1]-previous[1]);
    },0).toFixed(2)} m. It stops at the goal; request another destination for a longer task.</p>}
    {routeView?.plan&&routeView.scene_revision===revision&&<SimulationRouteView review={routeView} snapshot={snapshot}/>}
    {taskBlocked&&<p>Refinement and task-impact checks are pending. Draft viewing only; the SIM task has not passed.</p>}
    <div>{showActions&&(taskBlocked||!currentDisplayed)&&<button disabled={chatPending||busy||moving||!!pending||resetUnconfirmed||!product?.engine_connected||engineFault}
      onClick={()=>void act(async()=>{await prepareRoom(undefined,true,true);setPhase('Draft apply confirmed. Check the current 3D display. No motion is authorized.');})}>{taskBlocked?'View draft in Isaac':'View current Twin'}</button>}
      {showActions&&!taskBlocked&&!plan&&<button disabled={chatPending||busy||moving||!!pending||resetUnconfirmed||!product?.engine_connected||engineFault} onClick={preview}>Preview SIM route</button>}
      {showActions&&!taskBlocked&&<button disabled={chatPending||busy||moving||!!pending||resetUnconfirmed||!plan||!product?.engine_connected||engineFault||displayPending||browserBlocked} onClick={run}>Run simulation</button>}
      {showActions&&<button disabled={!resetAllowed} onClick={reset} title="Reset simulated runtime only. The saved scene is retained; preview a fresh route before Run.">Reset simulation</button>}
      <button disabled={!moving||stopPending} onClick={()=>void stop()}>{stopPending?'Stopping simulation…':'Stop simulation'}</button></div>
    {resetUnconfirmed&&<small>Reset outcome is not yet confirmed. Do not resend it or start another simulation task; review the saved operation.</small>}
    {pending&&<small>Checking Run receipt. Do not resend this request. Closing the App does not grant automatic resume.</small>}
    {pending&&receiptExpired&&<button onClick={()=>setReceiptCheck(value=>value+1)}>Check Run result · read only</button>}
  </section>;
}
