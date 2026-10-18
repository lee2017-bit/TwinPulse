// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useMemo,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import {RobotFieldTests} from './RobotFieldTests';
import {fleetBatteryLabel,fleetRobotFresh,type FleetDirection,type RobotFleetAction,type RobotFleetOperation,type RobotFleetRobot,type RobotFleetState} from './robot-fleet-types';

const keyDirections:Record<string,FleetDirection>={ArrowUp:'forward',w:'forward',ArrowDown:'backward',s:'backward',ArrowLeft:'left',a:'left',ArrowRight:'right',d:'right'};
const scalar=(value:unknown,limit=120):string=>{
  if(typeof value==='string')return value.length>limit?`${value.slice(0,limit)}…`:value;
  if(typeof value==='number')return Number.isFinite(value)?String(value):'unknown';
  if(typeof value==='boolean')return String(value);
  return 'not recorded';
};
const record=(value:unknown):Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const age=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)&&value>=0?`${Math.round(value)} ms`:'unknown';
const stopCommand=(value:string)=>/(?:멈춰|정지|스톱|\bstop|\bpause)(?:해줘|해|줘)?[.!?]*$/i.test(value.trim())||/^(?:stop|pause)\s*(?:robot|로봇)[.!?]*$/i.test(value.trim());
const readCommand=(value:string)=>/상태|배터리|battery|status|로그|기록.*(?:보여|분석)|\b(?:logs?|recording)\b/i.test(value);
const profileLimit=64*1024;
const evidenceName=(value:unknown):string|null=>typeof value==='string'&&/^(?:events-[0-9]{5}\.jsonl|receipt\.json|ssh-stderr\.log)$/.test(value)?value:null;
type ProfileReview={name:string;document:Record<string,unknown>;json:string};
const blankFields=(names:string)=>Object.fromEntries(names.split(' ').map(name=>[name,null]));
function blankMeasuredProfile(robot:RobotFleetRobot){
  return {schema:'physical-manual-profile-1.0',robot_id:robot.robot_id,binding_sha256:robot.setup?.binding_sha256??null,
    geometry:blankFields('sensor_frame sensor_xy_yaw native_angle_sign footprint_xy_m planar_extrinsic_sha256 footprint_sha256'),
    sampling:blankFields('minimum_range_m maximum_range_m minimum_quality maximum_gap_deg minimum_target_width_m range_uncertainty_m opaque_target_coverage_sha256'),
    timing:blankFields('maximum_pipeline_age_s measurement_sha256 provenance'),
    stop_model:blankFields('body_clearance_m reaction_s minimum_linear_deceleration_m_s2 minimum_angular_deceleration_rad_s2 linear_velocity_uncertainty_m_s angular_velocity_uncertainty_rad_s position_uncertainty_m maximum_scan_age_s maximum_input_age_s maximum_linear_speed_m_s maximum_angular_speed_rad_s stopping_measurement_sha256'),
    progress:blankFields('window_s maximum_sample_gap_s minimum_command_m_s minimum_wheel_progress_m minimum_body_translation_m minimum_body_rotation_rad maximum_wheel_speed_m_s maximum_body_speed_m_s maximum_body_rotation_rad_s measurement_sha256 wheel_metres_per_tick wheel_separation_m body_progress_policy')};
}
const bodyOnlyThresholds=new Set(['progress.minimum_body_translation_m','progress.minimum_body_rotation_rad',
  'progress.maximum_body_speed_m_s','progress.maximum_body_rotation_rad_s']);
function missingMeasurements(value:unknown,path='',unverifiedBody=false):string[]{
  if(!path)unverifiedBody=record(record(value).progress).body_progress_policy==='explicitly_unverified_supervised';
  if(value===null)return unverifiedBody&&bodyOnlyThresholds.has(path)?[]:[path];
  if(typeof value!=='object')return [];
  return Object.entries(value).flatMap(([key,item])=>missingMeasurements(item,path?`${path}.${key}`:key,unverifiedBody));
}
function parseProfileJSON(text:string,name:string):ProfileReview{
  if(new TextEncoder().encode(text).byteLength>profileLimit)throw new Error('Profile JSON exceeds 64 KiB. Import a bounded measured-profile document.');
  try{
    const parsed:unknown=JSON.parse(text,(_key,value:unknown)=>{
      if(typeof value==='number'&&!Number.isFinite(value))throw new Error('Non-finite profile value.');
      return value;
    });
    if(parsed===null||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Expected a JSON object.');
    return {name,document:parsed as Record<string,unknown>,json:JSON.stringify(parsed,null,2)};
  }catch{throw new Error('Invalid profile JSON. Import a JSON object; the server will validate its measured-profile schema.');}
}
function readProfile(file:File):Promise<ProfileReview>{
  if(file.size>profileLimit)return Promise.reject(new Error('Profile JSON exceeds 64 KiB. Import a bounded measured-profile document.'));
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();reader.onerror=()=>reject(new Error('Could not read the profile file.'));
    reader.onload=()=>{try{
      // The server validates the strict measured-profile schema and references.
      // Parsing this file never assigns measurement provenance or authority.
      resolve(parseProfileJSON(String(reader.result),file.name));
    }catch(caught){reject(caught);}};
    reader.readAsText(file);
  });
}
function summarizeOperation(operation:RobotFleetOperation){
  const manifest=operation.manifest,observations:{index:number;kind:string;detail:string}[]=[],commands:{index:number;kind:string;detail:string}[]=[];
  // Keep raw arrays out of the DOM and accessibility tree. This projection is
  // memoized per fetched operation, not rebuilt on every telemetry receipt.
  for(let index=operation.events.length-1;index>=0;index--){
    const original=operation.events[index],event={...original,...record(original.data)},kind=scalar(event.kind??event.event??event.type,60);
    const observation=/observation|telemetry|scan_preview|sensor_sample/i.test(kind);
    if(observation&&observations.length>=5||!observation&&commands.length>=50)continue;
    const details:string[]=[];
    if(observation){
      details.push(`sequence ${scalar(event.telemetry_sequence??event.sequence??event.event_sequence,40)}`);
      const pose=event.position_m??event.pose??record(event.navigation).pose_xy_yaw;
      if(Array.isArray(pose))details.push(`pose [${pose.slice(0,3).map(value=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(3):'?').join(', ')}]`);
      const points=record(event.scan).points;
      details.push(`scan points ${Array.isArray(points)?points.length:'not recorded'}`);
    }else{
      for(const key of ['action','reason','status','command_id'])if(event[key]!==undefined)details.push(`${key} ${scalar(event[key],80)}`);
      const parameters=record(event.parameters);
      for(const key of ['direction','amount'])if(parameters[key]!==undefined)details.push(`${key} ${scalar(parameters[key],40)}`);
    }
    const eventContext=record(original.twin_context),requestContext=record(event.request_twin_context);
    if(eventContext.scene_revision)details.push(`Twin ${scalar(eventContext.scene_revision,16)}`);
    if(requestContext.scene_revision)details.push(`request Twin ${scalar(requestContext.scene_revision,16)}`);
    if(original.source_twin_context_id)details.push(`source context ${scalar(original.source_twin_context_id,16)}`);
    const item={index,kind,detail:scalar(details.join(' · ')||'See complete JSON for source details.',180)};
    (observation?observations:commands).push(item);
    if(commands.length>=50&&observations.length>=5)break;
  }
  const missing=manifest.missing;
  const rows:[string,string][]=[['Complete',scalar(manifest.complete)],['Status',scalar(manifest.completeness??manifest.status)],
    ['Project / chat',scalar(operation.project_id)],
    ['Conversation session',scalar(record(manifest.source_twin_context).conversation_session_id,80)],
    ['Connection Twin revision',scalar(record(manifest.source_twin_context).scene_revision,80)],
    ['Twin context SHA256',scalar(record(manifest.source_twin_context).context_id,80)],
    ['Twin linkage',scalar(manifest.lineage_status??'LEGACY_UNKNOWN',160)],
    ['Coordinate alignment',scalar(record(record(manifest.source_twin_context).alignment).status)],
    ['Source',scalar(manifest.source??manifest.telemetry_source)],['Started',scalar(manifest.started_at)],['Ended',scalar(manifest.ended_at)],
    ['End reason',scalar(manifest.end_reason)],['Events SHA256',scalar(manifest.events_sha256,80)],
    ['Source files',String(Object.keys(record(manifest.source_files??manifest.worker_sources)).length)],
    ['Missing',Array.isArray(missing)?`${missing.length}${missing.length?` · ${missing.slice(0,4).map(item=>scalar(item,60)).join(' · ')}`:''}`:scalar(missing)]];
  const stream=record(manifest.stream),receipt=record(stream.local_receipt??manifest.local_receipt);
  const hasStream=manifest.stream!==null&&typeof manifest.stream==='object'&&!Array.isArray(manifest.stream);
  if(hasStream){
    rows.push(['Runtime stream complete',scalar(stream.complete)],['Runtime stream error',scalar(stream.error)],['Cleanup confirmed',scalar(stream.cleanup_confirmed??manifest.cleanup_confirmed)],
      ['Local receipt',scalar(receipt.complete??receipt.status??stream.local_receipt??manifest.local_receipt,240)]);
  }
  const evidence=Array.isArray(stream.segments)?[...stream.segments]:Array.isArray(receipt.files)?[...receipt.files]:Array.isArray(stream.files)?[...stream.files]:[];
  if(typeof (stream.local_receipt??manifest.local_receipt)==='string')evidence.push({path:'receipt.json',status:'Local runtime receipt'});
  if(hasStream)evidence.push({path:'ssh-stderr.log',status:'Transport diagnostic · may be unavailable'});
  return {rows,evidence:evidence.slice(0,200).map(item=>{
    const file=record(item),path=typeof item==='string'?item:file.path??file.name??file.relative_path;
    return {path:scalar(path,200),file:evidenceName(path),sha:scalar(file.sha256,80),status:scalar(file.status??file.complete??(typeof file.events==='number'?`${file.events} events`:'not recorded'))};
  }),evidenceCount:evidence.length,events:[...commands.slice(0,50-observations.length),...observations].sort((a,b)=>b.index-a.index)};
}
type Hold={robot:RobotFleetRobot;direction:FleetDirection;timer:ReturnType<typeof setInterval>;lastTick:number;token:number};
type Props={api:TwinPulseApi;state:RobotFleetState|null;selectedId:string|null;onSelect:(id:string)=>void;
  onChange:(state:RobotFleetState)=>void;available?:boolean;error?:string|null;drawerOpen?:boolean;onClose?:()=>void;selectionPending?:boolean};
export function RobotFleet({api,state,selectedId,onSelect,onChange,available=true,error:pollError,drawerOpen=true,onClose,selectionPending=false}:Props){
  const [error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  const [label,setLabel]=useState('SIM robot'),[x,setX]=useState('0'),[y,setY]=useState('0'),[yaw,setYaw]=useState('0');
  const [text,setText]=useState(''),[held,setHeld]=useState<FleetDirection|null>(null);
  const [operation,setOperation]=useState<RobotFleetOperation|null>(null),[logBusy,setLogBusy]=useState(false);
  const [showRegister,setShowRegister]=useState(false);
  const [expanded,setExpanded]=useState(false);
  const [profileReview,setProfileReview]=useState<ProfileReview|null>(null),[profileReviewed,setProfileReviewed]=useState(false);
  const [profileReading,setProfileReading]=useState(false),[profileError,setProfileError]=useState<string|null>(null);
  const [profileDraft,setProfileDraft]=useState('');
  const [prepareConfirmed,setPrepareConfirmed]=useState(false),[qualifyConfirmed,setQualifyConfirmed]=useState(false);
  const [markerX,setMarkerX]=useState('0'),[markerY,setMarkerY]=useState('0'),[markerYaw,setMarkerYaw]=useState('0');
  const [evidenceBusy,setEvidenceBusy]=useState<string|null>(null);
  const importGeneration=useRef(0);
  const operationSummary=useMemo(()=>operation?summarizeOperation(operation):null,[operation]);
  const profileMissing=useMemo(()=>profileReview?missingMeasurements(profileReview.document):[],[profileReview]);
  const hold=useRef<Hold|null>(null),sequence=useRef(0),token=useRef(0),stopPending=useRef(false);
  const owner=useRef({api,context:api.context,selectedId});owner.current={api,context:api.context,selectedId};
  const current=useRef({state,onChange,available});current.current={state,onChange,available};
  const robot=state?.robots.find(row=>row.robot_id===selectedId)??null;
  const logOperationId=robot?.operation_id??robot?.last_operation_id??null;
  const historicalOperation=!!robot&&!robot.operation_id&&!!robot.last_operation_id;
  const shownSourceContext=record(robot?.source_twin_context??operation?.manifest.source_twin_context);
  const shownRelation=robot?.source_twin_context?robot.twin_context_relation:
    operation?.manifest.lineage_status??'OPEN_LOGS_TO_CHECK_SAVED_REFERENCE';
  const selected=useRef(robot);selected.current=robot;
  const context=api.context;
  function envelope(action:RobotFleetAction['action'],target:RobotFleetRobot|null,payload:unknown={}):RobotFleetAction{
    return {action,request_id:crypto.randomUUID(),robot_id:target?.robot_id??null,
      connection_epoch:target?.connection_epoch??null,motion_epoch:target?.motion_epoch??null,payload} as RobotFleetAction;
  }
  const apply=(next:RobotFleetState)=>{
    if(owner.current.api===api&&owner.current.context===context&&next.revision>=(current.current.state?.revision??-1))current.current.onChange(next);
  };
  const send=async(body:RobotFleetAction)=>{const next=await api.robotFleetAction(body);apply(next);return next;};
  const reportError=(caught:unknown)=>{if(owner.current.api===api&&owner.current.context===context)setError(caught instanceof Error?caught.message:'Robot request failed.');};
  const stop=(target=hold.current?.robot??selected.current,force=false)=>{
    const active=hold.current;token.current++;
    if(active)clearInterval(active.timer);
    hold.current=null;setHeld(null);
    if(!target||!active&&!force)return;
    stopPending.current=true;
    void send(envelope('stop',target)).catch(reportError).finally(()=>{stopPending.current=false;});
  };
  const release=useRef(stop);release.current=stop;
  useEffect(()=>{
    const blur=()=>release.current();
    const visibility=()=>{if(document.hidden)release.current();};
    const keyup=(event:KeyboardEvent)=>{if(keyDirections[event.key]||event.code==='Space')release.current();};
    window.addEventListener('blur',blur);window.addEventListener('keyup',keyup);document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener('blur',blur);window.removeEventListener('keyup',keyup);document.removeEventListener('visibilitychange',visibility);release.current();};
  },[api,context]);
  useEffect(()=>{release.current();setOperation(null);setError(null);},[selectedId]);
  useEffect(()=>{
    importGeneration.current++;setProfileReview(null);setProfileReviewed(false);setProfileReading(false);setProfileError(null);
    setProfileDraft('');
    setPrepareConfirmed(false);setQualifyConfirmed(false);
    setMarkerX('0');setMarkerY('0');setMarkerYaw('0');
  },[api,context,selectedId]);
  useEffect(()=>{setPrepareConfirmed(false);setQualifyConfirmed(false);setProfileReviewed(false);},[robot?.connection_epoch]);
  useEffect(()=>{setOperation(null);},[logOperationId]);
  useEffect(()=>{if(!drawerOpen)release.current();},[drawerOpen]);
  useEffect(()=>{
    const active=hold.current;
    if(active&&(!available||selectionPending||state?.focused_robot_id!==selectedId||!robot||!fleetRobotFresh(robot)||!['READY','DRIVING','PAUSED'].includes(robot.control_state)||
      active.robot.connection_epoch!==robot.connection_epoch||active.robot.motion_epoch!==robot.motion_epoch))release.current();
  },[available,robot,selectionPending,state?.focused_robot_id,selectedId]);
  const adapterAvailable=robot?.kind!=='physical'||!!state?.capabilities.physical;
  const physical=robot?.kind==='physical';
  const fresh=!!robot&&fleetRobotFresh(robot);
  const physicalSessionActive=physical&&(!!robot.connection_epoch||robot.connection_state!=='DISCONNECTED');
  const canSetup=!busy&&!selectionPending&&available&&adapterAvailable&&fresh;
  const canSaveProfile=!busy&&!selectionPending&&available&&adapterAvailable&&!!robot?.capabilities.profile;
  const commandIsStop=stopCommand(text),commandIsRead=readCommand(text);
  const focusConfirmed=!!selectedId&&state?.focused_robot_id===selectedId&&!selectionPending;
  const canCommand=!!text.trim()&&(commandIsStop||!busy&&!selectionPending&&available&&adapterAvailable&&(commandIsRead||focusConfirmed&&!!robot?.capabilities.drive));
  const mayDrive=!busy&&available&&focusConfirmed&&adapterAvailable&&!!robot&&fleetRobotFresh(robot)&&robot.capabilities.drive&&
    ['READY','DRIVING','PAUSED'].includes(robot.control_state)&&!!robot.connection_epoch&&!!robot.motion_epoch;
  function start(direction:FleetDirection){
    if(!mayDrive||!robot||stopPending.current||hold.current)return;
    setError(null);const captured=robot,gesture=++token.current;
    let inFlight=false,sentAt=0;
    const tick=()=>{
      if(token.current!==gesture)return;
      const now=Date.now(),active=hold.current;
      if(owner.current.api!==api||owner.current.context!==context||api.context!==context||current.current.state?.focused_robot_id!==captured.robot_id||!current.current.available||document.hidden||active&&now-active.lastTick>250){release.current();return;}
      if(active)active.lastTick=now;
      const expiry=Math.min(250,current.current.state?.policy.input_expiry_ms??250);
      // One current packet, never a queue of held renewals. Concurrent HTTP
      // handlers can otherwise admit seq N+1 before N and cancel a valid hold.
      // Stop still uses its independent channel and never waits for this reply.
      if(inFlight){if(now-sentAt>=expiry){setError('Held input delivery expired. Movement paused; release and press again.');release.current();}return;}
      inFlight=true;sentAt=now;
      void send(envelope('drive',captured,{direction,sequence:++sequence.current,expires_at_ms:now+expiry})).catch(caught=>{
        if(token.current===gesture){reportError(caught);release.current();}
      }).finally(()=>{inFlight=false;});
    };
    hold.current={robot:captured,direction,lastTick:Date.now(),token:gesture,timer:setInterval(tick,100)};
    setHeld(direction);tick();
  }
  async function action(body:RobotFleetAction){
    if(busy||selectionPending)return;setBusy(true);setError(null);
    try{await send(body);}catch(caught){reportError(caught);}finally{setBusy(false);}
  }
  function choose(id:string){release.current();onSelect(id);}
  async function logs(){
    if(!robot||!logOperationId)return;
    const id=robot.robot_id;setLogBusy(true);setError(null);
    try{const next=await api.robotFleetOperation(logOperationId);
      if(owner.current.api===api&&owner.current.context===context&&owner.current.selectedId===id&&
        (selected.current?.operation_id??selected.current?.last_operation_id)===logOperationId)setOperation(next);
    }catch(caught){reportError(caught);}finally{setLogBusy(false);}
  }
  async function importProfile(file:File){
    const generation=++importGeneration.current,captured=owner.current;
    setProfileReview(null);setProfileReviewed(false);setProfileReading(true);setProfileError(null);
    try{const review=await readProfile(file);
      if(generation===importGeneration.current&&owner.current.api===captured.api&&owner.current.context===captured.context&&owner.current.selectedId===captured.selectedId)setProfileReview(review);
    }catch(caught){if(generation===importGeneration.current)setProfileError(caught instanceof Error?caught.message:'Could not read the profile file.');}
    finally{if(generation===importGeneration.current)setProfileReading(false);}
  }
  function reviewProfileDraft(){
    importGeneration.current++;setProfileReading(false);setProfileReview(null);setProfileReviewed(false);setProfileError(null);
    try{
      if(!robot?.setup?.binding_sha256)throw new Error('PROFILE_BINDING_UNAVAILABLE · Wait for this registered robot binding before creating a profile.');
      const review=parseProfileJSON(profileDraft,'App profile editor');
      if(review.document.robot_id!==robot.robot_id)throw new Error('PROFILE_ROBOT_MISMATCH · The profile robot_id must match the selected registered robot.');
      if(review.document.binding_sha256!==robot.setup.binding_sha256)throw new Error('PROFILE_BINDING_MISMATCH · The profile binding_sha256 must match the current registered binding.');
      setProfileReview(review);
    }catch(caught){setProfileError(caught instanceof Error?caught.message:'Could not review the edited profile.');}
  }
  function downloadProfileTemplate(){
    if(!robot?.setup?.binding_sha256)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(blankMeasuredProfile(robot),null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`physical-profile-${robot.robot_id}-unmeasured.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
  }
  const download=()=>{
    if(!operation)return;const url=URL.createObjectURL(new Blob([JSON.stringify(operation)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=`robot-operation-${operation.operation_id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
  };
  async function downloadEvidence(file:string){
    if(!operation||!evidenceName(file)||evidenceBusy)return;
    const operationId=operation.operation_id,id=robot?.robot_id;setEvidenceBusy(file);setError(null);
    try{
      const bytes=await api.robotFleetEvidence(operationId,file);
      if(owner.current.api!==api||owner.current.context!==context||owner.current.selectedId!==id||
        (selected.current?.operation_id??selected.current?.last_operation_id)!==operationId)return;
      const url=URL.createObjectURL(bytes),link=document.createElement('a');link.href=url;link.download=`physical-${operationId}-${file}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),0);
    }catch(caught){if(owner.current.selectedId===id&&(selected.current?.operation_id??selected.current?.last_operation_id)===operationId)reportError(caught);}
    finally{setEvidenceBusy(null);}
  }
  return <section className={`robot-fleet ${expanded?'is-expanded':'is-condensed'}`} aria-label="Robot fleet">
    <header><h3>Robots <span>{state?.robots.length??0} · {available?state?.robots.filter(fleetRobotFresh).length??0:0} connected</span></h3>
      <div className="robot-fleet-header-actions"><button type="button" aria-label="Manage robot fleet" aria-expanded={expanded} onClick={()=>{setExpanded(value=>!value);setShowRegister(false);}}>{expanded?'Less':'Manage'}</button>
        <button type="button" onClick={()=>{release.current();void send(envelope('stop_all',null)).catch(reportError);}} disabled={!state}>Stop all</button></div></header>
    {(pollError||!available)&&<p role="status">{pollError??'Fleet status unavailable · movement paused'}</p>}
    <div className="robot-fleet-list" aria-label="Registered robots">
      {state?.robots.map(row=><button type="button" key={row.robot_id} className="robot-fleet-row" disabled={selectionPending} aria-pressed={selectedId===row.robot_id}
        title={`${row.label} · ${row.kind==='sim'?'SIM':'Physical'} · ${available?row.connection_state:'STALE'} · ${fleetBatteryLabel(row)}`} onClick={()=>choose(row.robot_id)}>
        <span className={`robot-connection-dot ${available&&fleetRobotFresh(row)?'fresh':''}`} aria-label={available&&fleetRobotFresh(row)?'Fresh connected heartbeat':'Connection not current'}/>
        <span><span className="robot-fleet-row-heading"><strong>{row.label}</strong> <small>{row.kind==='sim'?'SIM':'Physical'}</small></span>
          {expanded&&<small>{available?row.connection_state:'STALE'} · {row.control_state} · LiDAR {row.lidar_state}</small>}
          <small className="robot-fleet-row-battery">{fleetBatteryLabel(row)}{!available?' · receipt stale':''}</small></span>
      </button>)}
      {!state?.robots.length&&<p>No fleet robot registered. Add a SIM robot or register a supported physical robot in Robots.</p>}
    </div>
    {selectionPending&&<p role="status">Selecting robot · movement paused until its focus receipt arrives.</p>}
    {expanded&&<details className="robot-fleet-register" onToggle={event=>setShowRegister(event.currentTarget.open)}><summary>Add SIM robot</summary>
      {showRegister&&<form onSubmit={event=>{event.preventDefault();const position=[Number(x),Number(y),Number(yaw)];
        if(!label.trim()||position.some(value=>!Number.isFinite(value))){setError('Enter a name and finite position values.');return;}
        void action(envelope('register_sim',null,{label:label.trim(),position_m:position}));}}>
        <label>Name<input value={label} maxLength={80} onChange={event=>setLabel(event.target.value)} required/></label>
        <div className="robot-fleet-position">{([['X (m)',x,setX],['Y (m)',y,setY],['Yaw (rad)',yaw,setYaw]] as const).map(([name,value,set])=>
          <label key={name}>{name}<input type="number" step="any" value={value} onChange={event=>set(event.target.value)} required/></label>)}</div>
        <button disabled={busy||selectionPending||!available||!state?.capabilities.sim}>Add SIM robot</button>
      </form>}<small>Kinematic Isaac SIM · simulated telemetry. Physical drive qualification requires separate tests.</small>
    </details>}
    {robot&&drawerOpen&&<section className="robot-fleet-drawer" aria-label={`Control ${robot.label}`}>
      <header><h4>{robot.label} · {robot.kind==='sim'?'SIM':'Physical'}</h4><button type="button" className="robot-fleet-stop" onClick={()=>stop(robot,true)}>Stop</button>
        {onClose&&<button type="button" aria-label="Close robot controls" onClick={()=>{release.current();onClose();}}>×</button>}</header>
      <p>{robot.connection_state} · {robot.control_state} · LiDAR {robot.lidar_state} · Recording {robot.recording_state}</p>
      {robot.connection_state==='CONNECTED'&&robot.control_state==='PAUSED'&&robot.applied_motion_epoch!==undefined&&
        <p role="status">{robot.motion_epoch!==null&&robot.applied_motion_epoch===robot.motion_epoch?'Engine stop confirmed':'Stop requested · waiting for engine confirmation'}</p>}
      <p>{!physical&&<>{fleetBatteryLabel(robot)}{!available?' · receipt stale':''} · </>}{robot.pose?.aligned?'Pose aligned':'Pose unaligned / unavailable'}</p>
      {pollError&&<p role="status">{pollError}</p>}
      {error&&<p role="alert">{error}</p>}
      {robot.reason&&<p className="robot-fleet-reason" role="status">{robot.reason}</p>}
      {!focusConfirmed&&!selectionPending&&<p role="status">Control focus differs from this drawer. Select this robot again before driving or sending a command.</p>}
      {!adapterAvailable&&<p className="robot-fleet-reason" role="status">Physical control unavailable in this build. This robot is not replaced with a SIM robot.</p>}
      {physical&&<>
        <dl className="robot-physical-status" aria-label="Physical connection and readiness">
          <div><dt>SSH heartbeat</dt><dd>{available&&fresh?'Fresh authenticated session':'Unavailable / stale'} · age {age(robot.telemetry_age_ms)}</dd></div>
          <div><dt>Battery</dt><dd>{fleetBatteryLabel(robot)}{!available?' · receipt stale':''} · age {age(robot.battery.age_ms)}</dd></div>
          <div><dt>Control</dt><dd>{robot.control_state} · controller {scalar(robot.controller_state)}</dd></div>
          <div><dt>Sensor</dt><dd>LiDAR {robot.lidar_state} · source {scalar(record(robot.sensor_frame).source??robot.scan?.source)} · age {age(record(robot.sensor_frame).age_ms)}{!available?' · receipt stale':''}</dd></div>
          <div><dt>Recording</dt><dd>{robot.recording_state}</dd></div>
          <div><dt>Cleanup</dt><dd>{robot.cleanup_confirmed===true?'Confirmed by robot':robot.cleanup_confirmed===false?'Not confirmed':'Unknown · no cleanup receipt'}</dd></div>
        </dl>
        <p className="robot-fleet-policy">Connect keeps one authenticated SSH session and starts no motor or sensor. Fresh heartbeat and measured voltage do not grant driving permission. Reconnect requires Disconnect first.</p>
        {!robot.capabilities.drive&&<p role="status">Protected manual movement is unavailable until the runtime grants drive capability. The separate supervised field-test path has its own explicit admission below. Status, Stop and operation logs remain available.</p>}
      </>}
      <div className="robot-fleet-actions">
        <button type="button" disabled={busy||selectionPending||!available||!adapterAvailable||(physical?physicalSessionActive:!['DISCONNECTED','DEGRADED'].includes(robot.connection_state))} onClick={()=>void action(envelope('connect',robot))}>{physicalSessionActive?(robot.connection_state==='CONNECTED'?'Connected':robot.connection_state==='CONNECTING'?'Connecting…':'Disconnect to reconnect'):'Connect'}</button>
        <button type="button" disabled={!canSetup||!(physical?robot.capabilities.prepare:robot.capabilities.drive)||robot.control_state==='ARMING'||physical&&!prepareConfirmed} onClick={()=>{
          release.current();setPrepareConfirmed(false);void action(envelope('prepare',robot,physical?{confirmed:true}:{}));}}>Prepare</button>
        <button type="button" disabled={busy||selectionPending||!available||robot.connection_state==='DISCONNECTED'&&!robot.connection_epoch} onClick={()=>{release.current();void action(envelope('disconnect',robot));}}>Disconnect</button>
        <button type="button" disabled={busy||selectionPending||!available||!adapterAvailable||!robot.capabilities.lidar||!fleetRobotFresh(robot)} aria-pressed={['STREAMING','STARTING'].includes(robot.lidar_state)} onClick={()=>{
          release.current();void action(envelope('lidar',robot,{enabled:!['STREAMING','STARTING'].includes(robot.lidar_state)}));}}>LiDAR {['STREAMING','STARTING'].includes(robot.lidar_state)?'Off':'On'}</button>
      </div>
      {physical&&<details className="robot-estimated-marker">
        <summary>Estimated Twin marker</summary>
        <p>Visualization estimate only; not sensor/world alignment or driving permission.</p>
          {robot.display_pose&&<p className="robot-fleet-policy">Static visualization estimate [{robot.display_pose.position_m.map(value=>scalar(value)).join(', ')}] · revision {scalar(robot.display_pose.scene_revision)} · {robot.display_pose.source}. This is the initial operator anchor, not localization. A valid same-epoch native relative tracker updates the displayed robot from this anchor; lost tracking keeps the last estimate and requires a new anchor. Accuracy remains unqualified.</p>}
        <form onSubmit={event=>{
          event.preventDefault();if(!available||busy||selectionPending)return;
          const values=[markerX,markerY,markerYaw],position=values.map(Number);
          if(values.some(value=>!value.trim())||position.some(value=>!Number.isFinite(value))){setError('Enter finite X, Y and yaw values for the visualization estimate.');return;}
          void action(envelope('set_twin_pose',robot,{position_m:position}));
        }}>
          <div className="robot-fleet-position">{([['Marker X (m)',markerX,setMarkerX],['Marker Y (m)',markerY,setMarkerY],['Marker yaw (rad)',markerYaw,setMarkerYaw]] as const).map(([name,value,set])=>
            <label key={name}>{name}<input type="number" step="any" value={value} onChange={event=>set(event.target.value)} required/></label>)}</div>
          <button disabled={!available||busy||selectionPending}>Place estimated robot marker</button>
        </form>
        <small>The saved marker belongs to the current confirmed Twin revision. Placing it starts no connection, sensor or movement.</small>
      </details>}
      {physical&&<RobotFieldTests key={`${context}:${robot.robot_id}`} robot={robot} available={available&&adapterAvailable&&!selectionPending} busy={busy}
        onAction={(name,payload)=>{release.current();void action(envelope(name,robot,payload));}} onOpenLogs={()=>void logs()}/>}
      {physical&&<details className="robot-physical-setup" open>
        <summary>Physical setup · {scalar(robot.setup?.runtime_state)}</summary>
        <p>Prepare opens the reviewed controller in zero-command mode. Qualification performs the existing supervised stop test and may move the robot. Each requires a new explicit confirmation; neither runs on Connect or reconnect.</p>
        <label className="robot-fleet-confirm"><input type="checkbox" checked={prepareConfirmed} onChange={event=>setPrepareConfirmed(event.target.checked)}/>I am present and confirm zero-command controller preparation.</label>
        <label className="robot-fleet-confirm"><input type="checkbox" checked={qualifyConfirmed} onChange={event=>setQualifyConfirmed(event.target.checked)}/>I am supervising the robot with the required clear space and confirm the stop qualification movement.</label>
        <button type="button" disabled={!canSetup||!robot.capabilities.qualify||!qualifyConfirmed} onClick={()=>{
          release.current();setQualifyConfirmed(false);void action(envelope('qualify',robot,{confirmed:true}));}}>Run same-boot stop qualification</button>
        <section aria-label="Physical setup blockers">
          <h5>Setup requirements</h5>
          {robot.setup?.blockers.length?<ul>{robot.setup.blockers.map((blocker,index)=><li key={`${index}-${blocker}`}>{scalar(blocker,500)}</li>)}</ul>:
            <p>{robot.setup?'No setup blockers reported. Drive and LiDAR still require their individual runtime capabilities.':'No current setup receipt. Connect to receive robot-side preparation and qualification requirements.'}</p>}
          {!fresh&&<p>Connect and wait for a fresh authenticated heartbeat before Prepare or qualification. Measured-profile import and saving are available while the robot is off.</p>}
          {!robot.setup?.profile&&<p>A measured geometry, timing, stopping and progress profile is required for protected driving. Import and review its original JSON below.</p>}
          {!robot.setup?.qualification&&<p>Same-boot / same-release stop qualification has not been reported.</p>}
        </section>
        {robot.setup?.qualification&&<details><summary>Qualification receipt</summary><dl className="robot-physical-status">{Object.entries(robot.setup.qualification).slice(0,16).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{scalar(value,200)}</dd></div>)}</dl></details>}
        <details aria-label="Measured profile import and review" className="robot-physical-profile">
          <summary>Advanced measured protective profile · strict JSON</summary>
          <p>Import the original physical-manual-profile-1.0 JSON with robot/binding identity, measured geometry, sampling, timing, stopping and progress evidence. The App supplies no measured defaults. Review and import do not certify measurement quality; the runtime validates the strict schema and evidence references.</p>
          <small>Wheel odometry does not prove body movement. Independent body progress remains unknown without an independent measured source.</small>
          <p className="robot-fleet-policy">Robot {robot.robot_id} · binding SHA256 {scalar(robot.setup?.binding_sha256,80)}</p>
          <details key={robot.robot_id} aria-label="측정 프로필 작성 안내">
            <summary>측정 프로필 작성 안내</summary>
            <p>이 안내는 측정 준비용 점검표입니다. 자동 측정기나 측정 완료 인증이 아닙니다. 선택한 모드의 필수 항목이 미측정(null)이면 보호 주행은 차단됩니다. 로봇이 꺼진 동안에는 양식 작성·원본 검토만 할 수 있고, 실제 센서·시간·정지·진행 측정은 별도의 현장 감독이 필요합니다.</p>
            <ol>
              <li><strong>로봇·근거 고정</strong><p>현재 robot_id와 binding_sha256를 사용합니다. 장착·배선·구성이 바뀌면 이전 프로필을 재사용하기 전에 다시 확인하세요. 각 *_sha256에는 실제 측정 원본의 검증된 SHA256만 넣으세요. 앱은 해시를 만들거나 측정 근거를 인증하지 않습니다.</p></li>
              <li><strong>Geometry · 차체와 센서</strong><p>base_link 원점·전방 x·좌측 y를 정하고, 줄자와 각도 측정으로 센서 중심의 sensor_xy_yaw=[x(m),y(m),yaw(rad)]와 실제 sensor_frame을 기록합니다. 위치를 아는 불투명 표적의 native 각도로 native_angle_sign(+1 또는 -1)을 확인하세요. 바퀴·돌출부를 포함한 실제 외곽을 footprint_xy_m에 원점 포함·반시계·볼록 다각형 3–16점으로 기록하고 planar_extrinsic_sha256·footprint_sha256 원본을 보관합니다. 사진·명목 URDF·추정 Twin 마커로 대신할 수 없습니다.</p></li>
              <li><strong>Sampling · 감지 범위와 사각</strong><p>거리를 실측한 불투명 표적을 방향·거리별로 관측해 minimum_range_m, maximum_range_m, minimum_quality, maximum_gap_deg, minimum_target_width_m, range_uncertainty_m를 보수적으로 정하고 opaque_target_coverage_sha256에 시험 원본을 연결합니다. 원래 비균일 각도를 유지하세요. 무반사·낮은 품질·큰 간격은 UNKNOWN이며 빈 공간이 아닙니다. 유리·가는 줄·낮거나 높은 장애물을 감지한다고 인증하는 모델이 아닙니다.</p></li>
              <li><strong>Timing · 샘플부터 제어까지</strong><p>원시 바이트 수신·샘플 시간 근거와 디코드·전달·guard 시각을 같은 검증된 시간 기준으로 기록해 최악 지연 maximum_pipeline_age_s(초)를 측정하고 measurement_sha256를 연결합니다. provenance는 실제 측정 후에만 measured로 지정합니다. 허용 상한은 0.2초이며 측정 기본값이 아닙니다. timing sidecar 없는 저장 raw·SSH ping·파일 수정 시각으로 샘플 시각을 대신할 수 없습니다.</p></li>
              <li><strong>Stop model · 실제 정지</strong><p>충분한 공간과 현장 감독 아래 기존 정지 검증 경로로 실제 전후진·회전의 명령/관측 시각과 제동 거리·각도를 기록하세요. reaction_s, 최소 선형/각 감속도, 속도·위치 불확실성과 최대 scan/input age를 원본에서 정하고 stopping_measurement_sha256를 연결합니다. body_clearance_m는 차체 외곽 기준 최소 0.10m, 최대 속도는 0.05m/s·0.30rad/s, scan/input age 상한은 0.2/0.25초입니다. 이 수치는 정책 한계이며 측정값 자동 채움이 아닙니다. 같은 boot/release 정지 qualification도 별도로 필요합니다.</p></li>
              <li><strong>Progress · 바퀴와 독립 차체</strong><p>감독된 구간에서 encoder tick과 실측 주행 거리·바퀴 간격으로 wheel_metres_per_tick·wheel_separation_m를 구합니다. 같은 시간창의 명령·wheel odometry로 window_s, maximum_sample_gap_s, minimum_command_m_s, minimum_wheel_progress_m, maximum_wheel_speed_m_s를 측정하고 measurement_sha256를 연결합니다. body_progress_policy는 검토 후 명시적으로 선택하며 기본 선택은 없습니다. independent_required 또는 미선택에서는 독립 카메라/위치 계측으로 minimum_body_translation_m, minimum_body_rotation_rad, maximum_body_speed_m_s, maximum_body_rotation_rad_s 네 항목도 측정해야 합니다. explicitly_unverified_supervised를 명시한 경우에만 이 네 항목을 null 그대로 둘 수 있습니다. 양수로 제공한 기존 값은 유지하며 0·추정값을 대신 채우지 않습니다. 이 경로의 body 진행은 UNKNOWN이며 body 정체·slip 검증 PASS가 아닙니다. wheel odometry를 독립 차체 증거로 이름 바꾸지 마세요. geometry·sampling·timing·stop·바퀴 측정은 두 모드 모두 필수입니다.</p></li>
              <li><strong>원본 검토·저장</strong><p>저장된 native/odom 자료는 재분석에 쓸 수 있지만, 없는 extrinsic·외곽·정지 거리·독립 차체·byte timing 측정을 채워 주지 않습니다. 새 측정 원본과 ID·SHA를 검토한 뒤 JSON을 검토/적용하세요. 서버의 strict schema 검증 오류는 화면에 표시됩니다. 프로필 저장·점검표 읽기는 연결·센서 시작·주행 권한을 부여하지 않습니다.</p></li>
            </ol>
            <button type="button" disabled={!robot.setup?.binding_sha256} onClick={downloadProfileTemplate}>Download blank measured-profile JSON</button>
            <button type="button" disabled={!robot.setup?.binding_sha256} onClick={()=>{
              importGeneration.current++;setProfileReading(false);setProfileReview(null);setProfileReviewed(false);setProfileError(null);
              setProfileDraft(JSON.stringify(blankMeasuredProfile(robot),null,2));
            }}>Start blank profile in App</button>
            {!robot.setup?.binding_sha256&&<p>현재 등록 binding ID가 없어 빈 양식을 만들 수 없습니다. 연결 시작이 아니라 등록 상태 갱신을 먼저 확인하세요.</p>}
            <label>Profile JSON editor<textarea rows={16} maxLength={profileLimit} value={profileDraft} spellCheck={false} onChange={event=>{
              setProfileDraft(event.target.value);setProfileReview(null);setProfileReviewed(false);setProfileError(null);
            }}/></label>
            <button type="button" disabled={!profileDraft.trim()||profileReading} onClick={reviewProfileDraft}>Review edited profile JSON</button>
            <small>Schema physical-manual-profile-1.0 · robot/binding IDs must remain fixed. Every measurement and evidence hash begins as null. Empty templates cannot be applied for driving; strict server validation remains authoritative.</small>
          </details>
          {robot.setup?.profile&&<details><summary>Current profile receipt</summary><pre>{JSON.stringify(robot.setup.profile,null,2)}</pre></details>}
          <label>Measured profile JSON<input type="file" accept=".json,application/json" onChange={event=>{
            const file=event.target.files?.[0];event.target.value='';if(file)void importProfile(file);
          }}/></label>
          {profileReading&&<p role="status">Reading profile JSON…</p>}
          {profileError&&<p role="alert">{profileError}</p>}
          {profileReview&&<>
            <p>Imported {profileReview.name} · schema {scalar(profileReview.document.schema)} · robot {scalar(profileReview.document.robot_id)} · server validation pending</p>
            {record(profileReview.document.progress).body_progress_policy==='explicitly_unverified_supervised'&&
              <p role="status">Body progress UNKNOWN · explicitly unverified supervised policy. Independent body stall/slip is not verified; only its four body-only thresholds may remain null.</p>}
            <details><summary>Review imported profile JSON</summary><pre>{profileReview.json}</pre></details>
            {profileMissing.length>0&&<p role="status">Unmeasured fields · {profileMissing.length}: {profileMissing.slice(0,12).join(', ')}{profileMissing.length>12?' …':''}. Fill these from reviewed physical measurements; protected driving remains blocked.</p>}
            <label className="robot-fleet-confirm"><input type="checkbox" checked={profileReviewed} onChange={event=>setProfileReviewed(event.target.checked)}/>I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.</label>
            <button type="button" disabled={!canSaveProfile||!profileReviewed||profileMissing.length>0} onClick={()=>{
              release.current();setProfileReviewed(false);void action(envelope('profile',robot,{profile:profileReview.document}));}}>Apply reviewed profile</button>
          </>}
        </details>
      </details>}
      <div className="robot-fleet-pad" role="group" aria-label="Hold to drive" tabIndex={0}
        onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))release.current();}}
        onKeyDown={event=>{if(event.code==='Space'){event.preventDefault();stop(robot,true);return;}
          const direction=keyDirections[event.key];if(direction){event.preventDefault();if(!event.repeat)start(direction);}}}>
        {(['forward','left','backward','right'] as const).map(direction=><button type="button" key={direction} className={`fleet-drive-${direction}`} disabled={!mayDrive}
          aria-label={`Hold ${direction}`} aria-pressed={held===direction}
          onPointerDown={event=>{if(event.button!==0)return;event.preventDefault();event.currentTarget.focus();event.currentTarget.setPointerCapture?.(event.pointerId);start(direction);}}
          onPointerUp={()=>release.current()} onPointerCancel={()=>release.current()} onLostPointerCapture={()=>release.current()}>
          {{forward:'↑',backward:'↓',left:'↶',right:'↷'}[direction]} <span>{direction}</span></button>)}
      </div>
      <small>Hold a direction or focus the pad and use arrows / WASD. Release, Space or leaving the window stops movement and retains the connection.</small>
      <p className="robot-fleet-policy">{physical&&robot.field?.config?'Supervised field policy: 0.03 m/s · 0.20 rad/s':`${state?.policy.linear_m_s} m/s · ${state?.policy.angular_rad_s} rad/s`} · input expiry {state?.policy.input_expiry_ms} ms</p>
      {robot.scan&&<details><summary>LiDAR points · {robot.scan.points.length} · {robot.scan.source}</summary>
        <svg className="robot-fleet-scan" viewBox="-3 -3 6 6" aria-label={`LiDAR scan · ${robot.scan.source}`} role="img">
          <circle r="0.08" fill="currentColor"/>{robot.scan.points.slice(0,3000).filter(point=>point.every(Number.isFinite)).map(([px,py],i)=><circle key={i} cx={px} cy={-py} r="0.02" fill="#6ed1df"/>)}</svg>
        <small>Sensor points only · obstacle protection depends on the active adapter and guard.</small></details>}
      <form className="robot-fleet-command" onSubmit={event=>{event.preventDefault();if(canCommand){
        release.current();const body=envelope('command',robot,{text:text.trim()});
        if(commandIsStop)void send(body).catch(reportError);else void action(body);
      }}}>
        <label>Robot command<input value={text} maxLength={1000} placeholder="Forward 10 cm, turn left 90°, or stop" onChange={event=>setText(event.target.value)}/></label>
        <button disabled={!canCommand}>Send command</button><small>{physical&&!robot.capabilities.drive?'Use status, battery, logs or Stop while movement is unavailable. Complete setup before a finite movement command.':'Commands require a finite distance or angle. You can also use the main chat.'}</small>
      </form>
      {state?.last_command?.robot_id===robot.robot_id&&<p role="status">{state.last_command.status} · {state.last_command.message}</p>}
      <button type="button" disabled={!logOperationId||logBusy} onClick={()=>void logs()}>Operation logs</button>
      {historicalOperation&&<small>Saved operation logs · historical. Viewing this record does not restore a connection or driving permission.</small>}
      {logOperationId&&<small className="robot-operation-id">Operation {logOperationId}{historicalOperation?' · historical':''}</small>}
      {logOperationId&&<details aria-label="Robot Twin record linkage"><summary>기록 연결 · 채팅 / Twin 버전</summary>
        <dl className="robot-physical-status">
          <div><dt>채팅 프로젝트</dt><dd>{scalar(shownSourceContext.project_id??robot.current_twin_context?.project_id)}</dd></div>
          <div><dt>대화 ID</dt><dd>{scalar(shownSourceContext.conversation_session_id,80)}</dd></div>
          <div><dt>연결 시작 Twin</dt><dd>{scalar(shownSourceContext.scene_revision,80)}</dd></div>
          <div><dt>현재 Twin</dt><dd>{scalar(robot.current_twin_context?.scene_revision,80)}</dd></div>
          <div><dt>연결 관계</dt><dd>{scalar(shownRelation)}</dd></div>
          <div><dt>좌표 정합</dt><dd>{scalar(record(shownSourceContext.alignment).status??'UNKNOWN')}</dd></div>
        </dl>
        <small>{physical?'실물 원자료는 연결 시작 Twin을 참고 기준으로 기록합니다. 취득 시각의 장면 동기화나 세계 좌표 정합 완료를 뜻하지 않습니다. 새 Twin을 수집 기준으로 삼으려면 Disconnect 후 Check Connection으로 새 작업을 시작하세요.':'SIM 관측은 각 프레임의 실제 engine / stage / Twin 버전을 따로 기록합니다. 연결 시작 버전과 이후 관측 버전은 다를 수 있습니다.'}</small>
        {robot.twin_context_relation&& !['SAME_TWIN_REFERENCE_NOT_ALIGNMENT_PROOF','LEGACY_UNKNOWN'].includes(robot.twin_context_relation)&&
          <p role="status">Twin 기준이 다르거나 현재 확인되지 않습니다. 이전 기록을 현재 Twin으로 재분류하지 않습니다. Stop과 원시 기록은 유지됩니다.</p>}
      </details>}
      {operation&&operationSummary&&<section className="robot-operation-log" aria-label="Operation summary">
        <h5>Operation · {scalar(operation.operation_id,80)}</h5>
        <p>{operation.events.length} events · showing {operationSummary.events.length} recent summaries, including up to 5 observations.</p>
        <p>{physical?'The JSON contains summaries and receipts. Download the separate runtime evidence segments below for original sensor bytes and helper logs.':'Complete source events, scan points and manifest details are included in the download.'}</p>
        <button type="button" onClick={download}>Download operation JSON</button>
        <dl aria-label="Operation manifest summary">{operationSummary.rows.map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
        {operationSummary.evidenceCount>0&&<details><summary>Physical runtime evidence · {operationSummary.evidenceCount} files</summary>
          <p>Source paths, SHA256 and receipt status come from the runtime manifest. The complete JSON includes all receipts and missing evidence.</p>
          <ul className="robot-runtime-evidence">{operationSummary.evidence.map((item,index)=><li key={index}>{item.path}<small>SHA256 {item.sha} · {item.status}</small>
            <button type="button" disabled={!item.file||evidenceBusy!==null} onClick={()=>{if(item.file)void downloadEvidence(item.file);}}>Download {item.file??'unavailable file'}</button></li>)}</ul>
          {operationSummary.evidenceCount>operationSummary.evidence.length&&<small>Showing the first {operationSummary.evidence.length} files; download the complete operation JSON for all evidence.</small>}
        </details>}
        <ol aria-label="Recent operation events">{operationSummary.events.map(event=><li key={event.index}>
          <strong>#{event.index+1} · {event.kind}</strong><span>{event.detail}</span></li>)}</ol>
      </section>}
    </section>}
    {error&&(!robot||!drawerOpen)&&<p role="alert">{error}</p>}
  </section>;
}
