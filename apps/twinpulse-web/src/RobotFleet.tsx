// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useMemo,useRef,useState} from 'react';
import {ApiError} from './api';
import type {TwinPulseApi} from './api';
import {CONTROL_INPUT_TTL_MS} from './robot-control-timing';
import {isRobotTaskRequest} from './robot-task-intent';
import {downloadBlob} from './download-blob';
import {FieldSessionGate,RobotFieldTests} from './RobotFieldTests';
import {RobotOperationDiagnostics} from './RobotOperationDiagnostics';
import {RobotMotionReview} from './RobotMotionReview';
import {FloorMap} from './FloorMap';
import type {FloorMapState} from './robot-fleet-types';
import {lidarDiagnosticLabel} from './robot-operation-diagnostics';
import {LidarPointView} from './LidarPointView';
import {LidarReviewDialog} from './LidarReviewDialog';
import {fleetBatteryLabel,fleetBatteryPolicyMessage,fleetRobotFresh,fleetStopCommand as stopCommand,fleetReadCommand as readCommand,type FleetDirection,type RobotFleetAction,type RobotFleetOperation,type RobotFleetRobot,type RobotFleetState} from './robot-fleet-types';

const keyDirections:Record<string,FleetDirection>={ArrowUp:'forward',w:'forward',ArrowDown:'backward',s:'backward',ArrowLeft:'left',a:'left',ArrowRight:'right',d:'right'};
const scalar=(value:unknown,limit=120):string=>{
  if(typeof value==='string')return value.length>limit?`${value.slice(0,limit)}…`:value;
  if(typeof value==='number')return Number.isFinite(value)?String(value):'unknown';
  if(typeof value==='boolean')return String(value);
  return 'not recorded';
};
const record=(value:unknown):Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const age=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)&&value>=0?`${Math.round(value)} ms`:'unknown';
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
  // Historical receipts never restore current field-session authority.
  const trials=new Map<string,Record<string,unknown>>();
  const motionEnds=new Map<string,{event:Record<string,unknown>;motion:Record<string,unknown>}>();
  const sourceContext=record(manifest.source_twin_context).context_id;
  let originalFailure:{event:Record<string,unknown>;fault:Record<string,unknown>;check:Record<string,unknown>}|null=null;
  for(const event of operation.events){
    const motion=record(record(event.data).motion_observation);
    // This is a recorded wheel-observation end, not the original pause/check
    // or a reconstructed LiDAR decision. Keep its report identity distinct.
    if(typeof sourceContext==='string'&&sourceContext&&event.operation_id===operation.operation_id&&event.robot_id===operation.robot_id
        &&event.source_twin_context_id===sourceContext&&motion.operation_id===operation.operation_id&&motion.robot_id===operation.robot_id
        &&motion.source_twin_context_id===sourceContext&&typeof event.connection_epoch==='string'&&event.connection_epoch
        &&motion.state==='ENDED'&&typeof motion.reason==='string'&&motion.reason
        &&!['OPERATOR_STOP','TASK_COMPLETED'].includes(motion.reason)
        &&typeof motion.motion_epoch==='string'&&motion.motion_epoch&&typeof motion.request_id==='string'&&motion.request_id
        &&typeof motion.started_s==='number'&&Number.isFinite(motion.started_s)&&motion.started_s>=0
        &&typeof motion.ended_s==='number'&&Number.isFinite(motion.ended_s)&&motion.ended_s>=motion.started_s){
      const key=JSON.stringify([event.connection_epoch,motion.motion_epoch,motion.request_id,motion.started_s,motion.ended_s,motion.reason]);
      if(!motionEnds.has(key))motionEnds.set(key,{event,motion});
      if(motionEnds.size>12)motionEnds.delete(motionEnds.keys().next().value!);
    }
    const fault=record(record(event.data).last_control_fault),check=record(fault.telemetry);
    if(event.operation_id===operation.operation_id&&typeof fault.reason==='string'&&typeof check.reason==='string')originalFailure={event,fault,check};
    const field=record(record(event.data).field),values=Array.isArray(field.trials)?field.trials:[];
    for(const value of values.slice(-64)){
      const trial=record(value),id=trial.trial_id;
      if(typeof id==='string'&&/^[a-f0-9]{32}$/.test(id)&&record(trial.context).operation_id===operation.operation_id)trials.set(id,trial);
    }
  }
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
    ['Source files',manifest.source_files==null&&manifest.worker_sources==null?'Unknown · not recorded':String(Object.keys(record(manifest.source_files??manifest.worker_sources)).length)],
    ['Source manifest basis',scalar(manifest.worker_sources_provenance)],
    ['Missing',Array.isArray(missing)?`${missing.length}${missing.length?` · ${missing.slice(0,4).map(item=>scalar(item,60)).join(' · ')}`:''}`:scalar(missing)]];
  if(originalFailure){
    const {event,fault,check}=originalFailure;
    rows.push(['original failed control reason',scalar(fault.reason)],['original failed check reason',scalar(check.reason)],
      ['Fault-carrying report sequence',scalar(event.sequence)],['Original failed check robot s',scalar(check.checked_monotonic_s)]);
    for(const [label,key] of [['Original failed sensor receipt age','sensor_receipt_age_s'],['Original failed guard receipt age','guard_receipt_age_s']] as const){
      const value=check[key];if(typeof value==='number'&&Number.isFinite(value)&&value>=0)rows.push([label,`${(value*1000).toFixed(2)} ms`]);
    }
  }
  for(const {event,motion} of motionEnds.values())rows.push(
    ['Recorded motion stop reason',scalar(motion.reason)],
    ['Observation scope','Recorded wheel observation · not failed-check telemetry or body-motion proof'],
    ['Motion end robot s',scalar(motion.ended_s)],['Motion epoch',scalar(motion.motion_epoch,80)],
    ['Original input request',scalar(motion.request_id,80)],['Latest input request',scalar(motion.latest_request_id,80)],
    ['Observation report sequence',scalar(event.sequence)],['Observation connection',scalar(event.connection_epoch,80)]);
  const stream=record(manifest.stream),receipt=record(stream.local_receipt??manifest.local_receipt);
  for(const [id,trial] of [...trials].slice(-12))rows.push([`Historical trial ${id}`,
    `${scalar(trial.case)} · ${scalar(trial.status)} · ${scalar(trial.reason,180)} · frames ${scalar(trial.frames)} · not current qualification`]);
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
type Hold={robot:RobotFleetRobot;direction:FleetDirection;timer:ReturnType<typeof setTimeout>;lastTick:number;token:number};
type Props={api:TwinPulseApi;state:RobotFleetState|null;selectedId:string|null;onSelect:(id:string)=>void;
  onChange:(state:RobotFleetState)=>void;available?:boolean;error?:string|null;drawerOpen?:boolean;onClose?:()=>void;selectionPending?:boolean;layoutVersion?:string|number};
export function RobotFleet({api,state,selectedId,onSelect,onChange,available=true,error:pollError,drawerOpen=true,onClose,selectionPending=false,layoutVersion=0}:Props){
  const [error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  const [label,setLabel]=useState('SIM robot'),[x,setX]=useState('0'),[y,setY]=useState('0'),[yaw,setYaw]=useState('0');
  const [obsLabel,setObsLabel]=useState('Test box'),[obsX,setObsX]=useState('0'),[obsY,setObsY]=useState('0'),[obsSize,setObsSize]=useState(['0.4','0.4','0.4']);
  const [text,setText]=useState(''),[held,setHeld]=useState<FleetDirection|null>(null);
  const commandDraftVersion=useRef(0);
  const [submitted,setSubmitted]=useState<{request_id:string;text:string;state:string;prior_command_id?:string}|null>(null);
  const [operation,setOperation]=useState<RobotFleetOperation|null>(null),[logBusy,setLogBusy]=useState(false);
  const [showRegister,setShowRegister]=useState(false);
  const [expanded,setExpanded]=useState(false);
  const [diagnosticsOpen,setDiagnosticsOpen]=useState(false);
  const [lidarReviewOpen,setLidarReviewOpen]=useState(false);
  useEffect(()=>{setLidarReviewOpen(false);},[selectedId,api.context]);
  const [profileReview,setProfileReview]=useState<ProfileReview|null>(null),[profileReviewed,setProfileReviewed]=useState(false);
  const [profileReading,setProfileReading]=useState(false),[profileError,setProfileError]=useState<string|null>(null);
  const [profileDraft,setProfileDraft]=useState('');
  const [prepareConfirmed,setPrepareConfirmed]=useState(false),[qualifyConfirmed,setQualifyConfirmed]=useState(false);
  const [markerX,setMarkerX]=useState('0'),[markerY,setMarkerY]=useState('0'),[markerYaw,setMarkerYaw]=useState('0');
  const [markerOpen,setMarkerOpen]=useState(false);
  const [floor,setFloor]=useState<FloorMapState|null>(null);
  const floorWanted=showRegister||markerOpen;
  useEffect(()=>{
    if(!floorWanted||typeof api.robotFleetFloor!=='function')return;
    let closed=false;const load=()=>void api.robotFleetFloor().then(next=>{if(!closed)setFloor(next);}).catch(()=>{if(!closed)setFloor(null);});
    load();const timer=setInterval(load,4000);return()=>{closed=true;clearInterval(timer);};
  },[api,floorWanted]);
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
    if(active)clearTimeout(active.timer);
    hold.current=null;setHeld(null);
    if(!target||!active&&!force)return;
    stopPending.current=true;
    void send(envelope('stop',target)).catch(reportError).finally(()=>{stopPending.current=false;});
  };
  const release=useRef(stop);release.current=stop;
  useEffect(()=>{
    const blur=()=>release.current();
    const resize=()=>release.current();
    const visibility=()=>{if(document.hidden)release.current();};
    const keyup=(event:KeyboardEvent)=>{if(keyDirections[event.key]||event.code==='Space')release.current();};
    window.addEventListener('blur',blur);window.addEventListener('resize',resize);window.addEventListener('keyup',keyup);document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener('blur',blur);window.removeEventListener('resize',resize);window.removeEventListener('keyup',keyup);document.removeEventListener('visibilitychange',visibility);release.current();};
  },[api,context]);
  useEffect(()=>{release.current();setOperation(null);setError(null);setDiagnosticsOpen(false);},[selectedId]);
  useEffect(()=>{setSubmitted(null);},[api,context,selectedId]);
  useEffect(()=>{
    importGeneration.current++;setProfileReview(null);setProfileReviewed(false);setProfileReading(false);setProfileError(null);
    setProfileDraft('');
    setPrepareConfirmed(false);setQualifyConfirmed(false);
    setMarkerX('0');setMarkerY('0');setMarkerYaw('0');setMarkerOpen(false);
  },[api,context,selectedId]);
  const previousEpoch=useRef<string|null|undefined>(undefined);const [epochNotice,setEpochNotice]=useState<string|null>(null);
  useEffect(()=>{
    setPrepareConfirmed(false);setQualifyConfirmed(false);setProfileReviewed(false);
    // A new connection epoch clears every supervisor tick; say so instead of silently unticking (PHYS09).
    if(previousEpoch.current!==undefined&&previousEpoch.current!==robot?.connection_epoch)setEpochNotice('Confirmations reset: new connection epoch');
    previousEpoch.current=robot?.connection_epoch;
  },[robot?.connection_epoch]);
  useEffect(()=>{setEpochNotice(null);previousEpoch.current=undefined;},[selectedId]);
  useEffect(()=>{setOperation(null);},[logOperationId]);
  useEffect(()=>{if(!drawerOpen)release.current();},[drawerOpen]);
  // Layout changes invalidate the current gesture; moving a console never
  // renews old intent or creates a second control owner.
  useEffect(()=>{release.current();},[layoutVersion]);
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
    const renewal=captured.kind==='physical'?(captured.timing_values?.input_renewal_ms??100):100;
    let inFlight=false,sentAt=0;
    const schedulePhysical=(delay:number)=>{
      const active=hold.current;
      if(captured.kind!=='physical'||token.current!==gesture||active?.token!==gesture)return;
      clearTimeout(active.timer);
      active.timer=setTimeout(tick,Math.max(1,Math.ceil(delay)));
    };
    const tick=()=>{
      if(token.current!==gesture)return;
      const now=Date.now(),active=hold.current;
      const expiry=captured.kind==='physical'?(captured.timing_values?.input_ttl_ms??CONTROL_INPUT_TTL_MS)
        :Math.min(CONTROL_INPUT_TTL_MS,current.current.state?.policy.input_expiry_ms??CONTROL_INPUT_TTL_MS);
      if(owner.current.api!==api||owner.current.context!==context||api.context!==context||current.current.state?.focused_robot_id!==captured.robot_id||!current.current.available||document.hidden||active&&now-active.lastTick>=expiry){release.current();return;}
      if(active)active.lastTick=now;
      // One current packet, never a queue of held renewals. Concurrent HTTP
      // handlers can otherwise admit seq N+1 before N and cancel a valid hold.
      // Stop still uses its independent channel and never waits for this reply.
      if(inFlight){if(now-sentAt>=expiry){setError('Held input delivery expired. Movement paused; release and press again.');release.current();}return;}
      if(captured.kind==='physical'&&sentAt>0&&now-sentAt<renewal){schedulePhysical(renewal-(now-sentAt));return;}
      inFlight=true;sentAt=now;
      // While HTTP is outstanding, retain an original-expiry deadline. A
      // timely reply replaces this one timer with sentAt+renewal, not the
      // phase of an interval created before a delayed response/input.
      schedulePhysical(expiry);
      let timelyReply=false;
      void send(envelope('drive',captured,{direction,sequence:++sequence.current,expires_at_ms:now+expiry})).then(next=>{
        if(captured.kind!=='physical'||token.current!==gesture||hold.current?.token!==gesture)return;
        if(Date.now()-sentAt>=expiry){setError('Held input delivery expired. Movement paused; release and press again.');release.current();return;}
        // React's epoch/capability effect may run after this promise. Apply the
        // same revocation immediately before a response-driven fresh input.
        const updated=next.robots.find(row=>row.robot_id===captured.robot_id);
        if(!next.capabilities.physical||next.focused_robot_id!==captured.robot_id||!updated||
            updated.connection_state!=='CONNECTED'||updated.connection_epoch!==captured.connection_epoch||
            updated.motion_epoch!==captured.motion_epoch||updated.operation_id!==captured.operation_id||
            !updated.capabilities.drive||!fleetRobotFresh(updated)||!['READY','DRIVING','PAUSED'].includes(updated.control_state)){
          release.current();return;
        }
        timelyReply=true;
      }).catch(caught=>{
        if(token.current===gesture){reportError(caught);release.current();}
      }).finally(()=>{
        inFlight=false;
        if(!timelyReply||token.current!==gesture||hold.current?.token!==gesture)return;
        if(Date.now()-sentAt>=expiry){setError('Held input delivery expired. Movement paused; release and press again.');release.current();return;}
        // A 125ms reply must not wait for the 200ms interval tick. This samples
        // the still-held gesture anew; it never extends the previous packet.
        if(Date.now()-sentAt>=renewal)tick();
        else schedulePhysical(renewal-(Date.now()-sentAt));
      });
    };
    hold.current={robot:captured,direction,lastTick:Date.now(),token:gesture,
      timer:captured.kind==='physical'?setTimeout(tick,renewal):setInterval(tick,renewal)};
    setHeld(direction);tick();
  }
  async function action(body:RobotFleetAction){
    if(busy||selectionPending)return;setBusy(true);setError(null);
    try{await send(body);}catch(caught){reportError(caught);}finally{setBusy(false);}
  }
  function choose(id:string){release.current();onSelect(id);}
  async function logs(){
    if(!robot||!logOperationId)return;
    release.current();setDiagnosticsOpen(true);
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
    downloadBlob(new Blob([JSON.stringify(blankMeasuredProfile(robot),null,2)],{type:'application/json'}),`physical-profile-${robot.robot_id}-unmeasured.json`);
  }
  const download=()=>{
    if(!operation||logBusy)return;
    downloadBlob(new Blob([JSON.stringify(operation)],{type:'application/json'}),`robot-operation-${operation.operation_id}.json`);
  };
  async function downloadEvidence(file:string){
    if(!operation||!evidenceName(file)||evidenceBusy)return;
    const operationId=operation.operation_id,id=robot?.robot_id;setEvidenceBusy(file);setError(null);
    try{
      const bytes=await api.robotFleetEvidence(operationId,file);
      if(owner.current.api!==api||owner.current.context!==context||owner.current.selectedId!==id||
        (selected.current?.operation_id??selected.current?.last_operation_id)!==operationId)return;
      downloadBlob(bytes,`physical-${operationId}-${file}`);
    }catch(caught){if(owner.current.selectedId===id&&(selected.current?.operation_id??selected.current?.last_operation_id)===operationId)reportError(caught);}
    finally{setEvidenceBusy(null);}
  }
  return <section className={`robot-fleet ${expanded?'is-expanded':'is-condensed'} ${robot&&drawerOpen?'has-controls':''}`} aria-label="Robot fleet">
    <header><h3>Robots <span>{state?.robots.length??0} · {available?state?.robots.filter(fleetRobotFresh).length??0:0} connected</span></h3>
      <div className="robot-fleet-header-actions"><button type="button" aria-label="Manage robot fleet" aria-expanded={expanded} onClick={()=>{setExpanded(value=>!value);setShowRegister(false);}}>{expanded?'Less':'Manage'}</button>
        <button type="button" onClick={()=>{release.current();void send(envelope('stop_all',null)).catch(reportError);}} disabled={!state}>Stop all</button>
        <button type="button" title="Remove the LiDAR points and LiDAR-move markers kept on the Twin from finished routes (display only)" onClick={()=>{void send(envelope('clear_lidar_layer',null,{})).then(()=>setFloor(null)).catch(reportError);}} disabled={!state}>Clear LiDAR</button></div></header>
    {(pollError||!available)&&<p role="status">{pollError??'Fleet status unavailable · movement paused'}</p>}
    <div className="robot-fleet-list" aria-label="Registered robots">
      {state?.robots.map(row=><button type="button" key={row.robot_id} className="robot-fleet-row" disabled={selectionPending} aria-pressed={selectedId===row.robot_id}
        title={`${row.label} · ${row.kind==='sim'?'SIM':'Physical'} · ${available?row.connection_state:'STALE'} · ${fleetBatteryLabel(row)}`} onClick={()=>choose(row.robot_id)}>
        <span className={`robot-connection-dot ${available&&fleetRobotFresh(row)?'fresh':''}`} aria-label={available&&fleetRobotFresh(row)?'Fresh connected heartbeat':'Connection not current'}/>
        <span><span className="robot-fleet-row-heading"><strong>{row.label}</strong> <small>{row.kind==='sim'?'SIM':'Physical'}</small></span>
          {expanded&&<small>{available?row.connection_state:'STALE'} · {row.control_state} · LiDAR {lidarDiagnosticLabel(row,available)}</small>}
          <small className="robot-fleet-row-battery">{fleetBatteryLabel(row)}{!available?' · receipt stale':''}</small></span>
      </button>)}
      {!state?.robots.length&&<p>No fleet robot registered yet. Add a SIM robot below, or register a supported physical robot in Robots.</p>}
    </div>
    {selectionPending&&<p role="status">Selecting robot · movement paused until its focus receipt arrives.</p>}
    {(expanded||state&&!state.robots.length)&&<details className="robot-fleet-register" open={!state?.robots.length||undefined} onToggle={event=>setShowRegister(event.currentTarget.open)}><summary>Add SIM robot</summary>
      {showRegister&&<form onSubmit={event=>{event.preventDefault();const position=[Number(x),Number(y),Number(yaw)];
        if(!label.trim()||position.some(value=>!Number.isFinite(value))){setError('Enter a name and finite position values.');return;}
        void action(envelope('register_sim',null,{label:label.trim(),position_m:position}));}}>
        <p className="robot-fleet-policy">Model: TurtleBot3 Burger (built-in SIM model). The name is only a label.</p>
        <FloorMap floor={floor} value={[Number(x)||0,Number(y)||0,Number(yaw)||0]} onChange={(px,py,pyaw)=>{setX(String(px));setY(String(py));setYaw(String(pyaw));}}/>
        <label>Name<input value={label} maxLength={80} onChange={event=>setLabel(event.target.value)} required/></label>
        <div className="robot-fleet-position">{([['X (m)',x,setX],['Y (m)',y,setY],['Yaw (rad)',yaw,setYaw]] as const).map(([name,value,set])=>
          <label key={name}>{name}<input type="number" step="any" value={value} onChange={event=>set(event.target.value)} required/></label>)}</div>
        <button disabled={busy||selectionPending||!available||!state?.capabilities.sim}>Add SIM robot</button>
      </form>}<small>Kinematic Isaac SIM · simulated telemetry. Physical drive qualification requires separate tests.</small>
    </details>}
    {expanded&&state?.capabilities.sim&&<details className="robot-fleet-sim-obstacle"><summary>SIM-world test obstacle · {state.sim_obstacles?.length??0}</summary>
      <p className="robot-fleet-policy">A box placed only in the Isaac SIM world. SIM LiDAR and the proximity stop see it; the Twin model and the route planner do not, so a route meets it like an unmodelled object.</p>
      <form onSubmit={event=>{event.preventDefault();const position=[Number(obsX),Number(obsY)],size=obsSize.map(Number);
        if(!obsLabel.trim()||position.some(v=>!Number.isFinite(v))||size.some(v=>!(v>=0.1&&v<=3))){setError('Enter a label, finite X/Y and a size between 0.1 and 3 m.');return;}
        void action(envelope('sim_obstacle',null,{label:obsLabel.trim(),position_m:position,size_m:size}));}}>
        <label>Label<input aria-label="SIM obstacle label" value={obsLabel} maxLength={80} onChange={event=>setObsLabel(event.target.value)} required/></label>
        <div className="robot-fleet-position">{([['Obstacle X (m)',obsX,setObsX],['Obstacle Y (m)',obsY,setObsY]] as const).map(([name,value,set])=>
          <label key={name}>{name}<input aria-label={name} type="number" step="any" value={value} onChange={event=>set(event.target.value)} required/></label>)}
          {(['Width (m)','Depth (m)','Height (m)'] as const).map((name,i)=><label key={name}>{name}<input aria-label={'SIM obstacle '+name} type="number" step="any" min={0.1} max={3} value={obsSize[i]} onChange={event=>setObsSize(obsSize.map((v,j)=>j===i?event.target.value:v))} required/></label>)}</div>
        <button disabled={busy||!available}>Place SIM obstacle</button>
        {!!state.sim_obstacles?.length&&<button type="button" disabled={busy} onClick={()=>{void action(envelope('clear_sim_obstacles',null,{}));}}>Clear SIM obstacles</button>}
      </form>
      {!!state.sim_obstacles?.length&&<ul>{state.sim_obstacles.map(o=><li key={o.id}>{o.label} · ({o.position_m[0]}, {o.position_m[1]}) m · {o.size_m.join(' × ')} m · SIM world only</li>)}</ul>}
    </details>}
    {robot&&drawerOpen&&<section className="robot-fleet-drawer" aria-label={`Control ${robot.label}`}>
      <header><h4>{robot.label} · {robot.kind==='sim'?'SIM':'Physical'}</h4><button type="button" className="robot-fleet-stop" onClick={()=>stop(robot,true)}>Stop</button>
        {onClose&&<button type="button" aria-label="Close robot controls" onClick={()=>{release.current();onClose();}}>×</button>}</header>
      <p className="robot-fleet-current-status" title={`${robot.connection_state} · ${robot.control_state} · LiDAR ${lidarDiagnosticLabel(robot,available)} · Recording ${robot.recording_state}`}>
        <span className={`robot-connection-dot ${available&&fresh?'fresh':''}`} aria-label={available&&fresh?'Selected robot connection current':'Selected robot connection not current'}/>
        {robot.connection_state} · {robot.control_state} · LiDAR {lidarDiagnosticLabel(robot,available)} · {fleetBatteryLabel(robot)}{!available?' · receipt stale':''}
      </p>
      <div className="robot-fleet-notices" aria-label="Robot control readiness">
      {error&&<p role="alert">{error}</p>}
      {pollError&&<p role="status">{pollError}</p>}
      {(robot.setup?.maintenance_phase||robot.reason)&&<p className="robot-fleet-reason" role="status" title={robot.setup?.maintenance_phase?`Prepare: ${robot.setup.maintenance_phase} · ${robot.reason??'No motion during build/check'}`:robot.reason??undefined}>
        {robot.setup?.maintenance_phase?({BUILDING_OUTPUT_GUARD:'Building output guard…',CHECKING_OUTPUT_GUARD:'Checking output guard…',CHECKING_OUTPUT_GUARD_LOADER:'Loading output guard…',VERIFYING_OUTPUT_GUARD_READBACK:'Verifying applied settings…'} as Record<string,string>)[robot.setup.maintenance_phase]??robot.setup.maintenance_phase:robot.reason}</p>}
      {robot.connection_state==='CONNECTED'&&robot.control_state==='PAUSED'&&robot.applied_motion_epoch!==undefined&&
        <p role="status">{physical?'Physical movement paused · current motor stop/readback is not established by an Isaac engine ACK.':robot.motion_epoch!==null&&robot.applied_motion_epoch===robot.motion_epoch?'Engine stop confirmed':'Stop requested · waiting for engine confirmation'}</p>}
      {!focusConfirmed&&!selectionPending&&<p role="status">Control focus differs from this drawer. Select this robot again before driving or sending a command.</p>}
      {!adapterAvailable&&<p className="robot-fleet-reason" role="status">Physical control unavailable in this build. This robot is not replaced with a SIM robot.</p>}
      {state?.last_command?.robot_id===robot.robot_id&&<p className="robot-fleet-command-result" role="status" title={state.last_command.message}>{state.last_command.status} · {physical?'Check robot telemetry':'Check engine telemetry'}</p>}
      </div>
      <div className="robot-fleet-actions">
        <button type="button" disabled={busy||selectionPending||!available||!adapterAvailable||(physical?physicalSessionActive:!['DISCONNECTED','DEGRADED'].includes(robot.connection_state))} onClick={()=>void action(envelope('connect',robot))}>{physicalSessionActive?(robot.connection_state==='CONNECTED'?'Connected':robot.connection_state==='CONNECTING'?'Connecting…':'Disconnect to reconnect'):'Connect'}</button>
        <button type="button" disabled={!canSetup||!(physical?robot.capabilities.prepare:robot.capabilities.drive)||robot.control_state==='ARMING'||robot.reason==='ISAAC_MODEL_WARMING_UP'||physical&&!prepareConfirmed} onClick={()=>{
          release.current();setPrepareConfirmed(false);void action(envelope('prepare',robot,physical?{confirmed:true}:{}));}}>Prepare</button>
        <button type="button" disabled={busy||selectionPending||!available||robot.connection_state==='DISCONNECTED'&&!robot.connection_epoch} onClick={()=>{release.current();void action(envelope('disconnect',robot));}}>Disconnect</button>
        <button type="button" disabled={busy||selectionPending||!available||!adapterAvailable||!robot.capabilities.lidar||!fleetRobotFresh(robot)} aria-pressed={available&&fresh&&['STREAMING','STARTING'].includes(robot.lidar_state)} onClick={()=>{
          release.current();void action(envelope('lidar',robot,{enabled:!['STREAMING','STARTING'].includes(robot.lidar_state)}));}} aria-label={`Turn LiDAR ${available&&fresh&&['STREAMING','STARTING'].includes(robot.lidar_state)?'off':'on'}`} title="Change sensor state; visualization hiding is separate">LiDAR {available&&fresh&&['STREAMING','STARTING'].includes(robot.lidar_state)?'off':'on'}</button>
      </div>
      {physical&&<section className="robot-fleet-session-gate" aria-label="Physical session gate">
        <h5>Supervised session gate</h5>
        {robot.connection_state!=='CONNECTED'&&<p role="alert" className="robot-fleet-link-status">Link {robot.connection_state} · {robot.link_detail??robot.reason??'no detail reported'} · Disconnect, then Connect to start a new session</p>}
        {robot.control_owner_state==='EXITED_RECONNECT_REQUIRED'&&<p role="alert" className="robot-fleet-link-status">Recording fault on the robot ({robot.recording_failure_reason??'reason not reported'}) · controls closed · Disconnect, then Connect</p>}
        {epochNotice&&<p role="status">{epochNotice}</p>}
        <label className="robot-fleet-confirm"><input type="checkbox" checked={prepareConfirmed} onChange={event=>setPrepareConfirmed(event.target.checked)}/>I am present and confirm zero-command controller preparation.</label>
        {(()=>{const why=!available?'Fleet state unavailable; refresh before sending an action.':!adapterAvailable?'Physical adapter missing in this build.':busy||selectionPending?'Another request is in flight.':
          !fresh?`Waiting for a fresh heartbeat · link ${robot.connection_state} · ${robot.link_detail??robot.reason??'no reason reported'}`:
          !robot.capabilities.prepare?`Prepare blocked by the robot: ${robot.setup?.blockers.length?robot.setup.blockers.map(b=>scalar(b,120)).join(' · '):'no setup receipt yet'}`:
          robot.control_state==='ARMING'?'Preparing…':!prepareConfirmed?'Tick "I am present" to enable Prepare.':null;
          return why?<p className="robot-fleet-gate-blocker" role="status">Prepare: {why}</p>:null;})()}
        <label className="robot-fleet-confirm"><input type="checkbox" checked={qualifyConfirmed} onChange={event=>setQualifyConfirmed(event.target.checked)}/>I am supervising the robot with the required clear space and confirm the stop qualification movement.</label>
        <div className="robot-fleet-gate-row"><button type="button" disabled={!canSetup||!robot.capabilities.qualify||!qualifyConfirmed} onClick={()=>{
          release.current();setQualifyConfirmed(false);void action(envelope('qualify',robot,{confirmed:true}));}}>Run same-boot stop qualification</button>
          {(!canSetup||!robot.capabilities.qualify||!qualifyConfirmed)&&<p className="robot-fleet-gate-blocker" role="status">{!fresh?`Waiting for a fresh heartbeat · link ${robot.connection_state} · ${robot.link_detail??robot.reason??'no reason reported'}`:!robot.capabilities.qualify?'Qualification blocked by the robot (see Physical setup blockers).':!qualifyConfirmed?'Tick the supervision confirmation to enable it.':'Another request is in flight.'}</p>}</div>
        <FieldSessionGate robot={robot} available={available&&adapterAvailable&&!selectionPending} busy={busy} onAction={(name,payload)=>{release.current();void action(envelope(name,robot,payload));}}/>
      </section>}
      <div className="robot-fleet-control-primary">
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
        <form className="robot-fleet-command" onSubmit={event=>{event.preventDefault();if(canCommand){
          release.current();const commandText=text.trim(),draftVersion=commandDraftVersion.current,body=envelope('command',robot,{text:commandText}),captured=owner.current;
          const prior_command_id=robot?.command?.request_id;
          setSubmitted({request_id:body.request_id,text:text.trim(),state:'SENDING',prior_command_id});
          const dispatch=async()=>{
            if(!commandIsStop)setBusy(true);setError(null);
            const viaChat=isRobotTaskRequest(commandText,robot?.kind);
            try{
              if(viaChat)await api.conversationAction({action:'message',request_id:body.request_id,text:commandText,attachment:null,mode:'new'});
              else await send(body);
              if(owner.current.api===captured.api&&owner.current.context===captured.context&&owner.current.selectedId===captured.selectedId){
              // A chat-routed task never becomes robot.command; say where to follow it instead of ACCEPTED forever.
              setSubmitted({request_id:body.request_id,text:commandText,state:viaChat?'SENT TO CHAT · answer the route card there':'ACCEPTED',prior_command_id});
              // Only clear the acknowledged draft. A late reply must not erase
              // newer typing, even when the user has typed the same text again.
              if(commandDraftVersion.current===draftVersion)setText('');}}
            catch(caught){reportError(caught);if(owner.current===captured||owner.current.api===captured.api&&owner.current.context===captured.context&&owner.current.selectedId===captured.selectedId){
              // A network error or delivery_unknown may still have been accepted: never invite a resend as FAILED.
              const unknown=!(caught instanceof ApiError)||caught.code==='delivery_unknown';
              setSubmitted({request_id:body.request_id,text:commandText,state:unknown?'DELIVERY UNKNOWN · check chat before sending again':'FAILED',prior_command_id});}}
            finally{if(owner.current.api===captured.api&&owner.current.context===captured.context)setBusy(false);}
          };void dispatch();
        }}}>
          <label>Robot command<input value={text} maxLength={1000} placeholder="Type a new command…" onChange={event=>{commandDraftVersion.current++;setText(event.target.value);}}/></label>
          <button disabled={!canCommand} aria-label="Send command">Send</button>
          <output className="robot-command-receipt" aria-label="Robot command progress" aria-live="polite" title={`Request ${robot.command?.request_id??submitted?.request_id??'not submitted'}`}>
            {robot.command&&(!submitted||submitted.request_id===robot.command.request_id||robot.command.request_id!==submitted.prior_command_id)?<>
              <strong>{robot.command.state}{robot.command.target_label?` · ${robot.command.target_label}`:''}</strong>
              <span>{robot.command.text}{typeof robot.command.remaining_m==='number'?` · ${robot.command.remaining_m.toFixed(2)} m remaining`:''}{robot.command.reason?` · ${robot.command.reason}`:''}</span>
            </>:submitted?<><strong>{submitted.state}</strong><span>{submitted.text}</span></>:<span>{physical?'Review anchor and LiDAR tracking before a destination.':'Enter a scene destination · arrival needs engine confirmation.'}</span>}
          </output>
          <small>Hold arrows / WASD. Release or Space stops. You can also use the main chat.</small>
        </form>
      </div>
      <div className="robot-fleet-detail-tools"><details className="robot-fleet-diagnostics" open={diagnosticsOpen} onToggle={event=>{setDiagnosticsOpen(event.currentTarget.open);release.current();}}><summary title="Setup, sensor details and logs">Details</summary>
      {physical&&<details className="robot-estimated-marker robot-twin-placement-form" open={markerOpen} onToggle={event=>{setMarkerOpen(event.currentTarget.open);release.current();}}>
        <summary>Estimated Twin marker · {robot.display_pose?'Edit position':'Place robot'}</summary>
        <p>Review the robot position and yaw in this Twin. This estimate anchors relative LiDAR tracking for display and explicitly requested destinations; it never grants driving permission or claims measured world alignment.</p>
          {robot.display_pose&&<p className="robot-fleet-policy">Static visualization estimate [{robot.display_pose.position_m.map(value=>scalar(value)).join(', ')}] · revision {scalar(robot.display_pose.scene_revision)} · {robot.display_pose.source}. This is the initial operator anchor, not localization. A valid same-epoch native relative tracker updates the displayed robot from this anchor; lost tracking keeps the last estimate and requires a new anchor. Accuracy remains unqualified.</p>}
        <form onSubmit={event=>{
          event.preventDefault();if(!available||busy||selectionPending)return;
          const values=[markerX,markerY,markerYaw],position=values.map(Number);
          if(values.some(value=>!value.trim())||position.some(value=>!Number.isFinite(value))){setError('Enter finite X, Y and yaw values for the visualization estimate.');return;}
          void action(envelope('set_twin_pose',robot,{position_m:position}));
        }}>
          <FloorMap floor={floor} value={[Number(markerX)||0,Number(markerY)||0,Number(markerYaw)||0]} onChange={(px,py,pyaw)=>{setMarkerX(String(px));setMarkerY(String(py));setMarkerYaw(String(pyaw));}}/>
          <div className="robot-fleet-position">{([['Marker X (m)',markerX,setMarkerX],['Marker Y (m)',markerY,setMarkerY],['Marker yaw (rad)',markerYaw,setMarkerYaw]] as const).map(([name,value,set])=>
            <label key={name}>{name}<input type="number" step="any" value={value} onChange={event=>set(event.target.value)} required/></label>)}</div>
          <button aria-label="Place estimated robot marker" disabled={!available||busy||selectionPending}>Place robot</button>
        </form>
        <small>The saved marker belongs to the current confirmed Twin revision. Placing it starts no connection, sensor or movement.</small>
      </details>}
      {state?.last_command?.robot_id===robot.robot_id&&<p>Last request: {state.last_command.status} · {state.last_command.message}</p>}
      {(robot.command||submitted)&&<p>Command request: <code>{robot.command?.request_id??submitted?.request_id}</code> · {robot.command?.text??submitted?.text}</p>}
      <p>{robot.pose?.aligned?'Pose aligned':'Pose unaligned / unavailable'} · Recording {available&&fresh?'':'last reported '}{robot.recording_state}</p>
      <small>Hold a direction or focus the pad and use arrows / WASD. Release, Space or leaving the window stops movement and retains the connection.</small>
      <p className="robot-fleet-policy">{physical&&robot.field?.config?'Supervised field policy: 0.03 m/s · 0.20 rad/s':`${state?.policy.linear_m_s} m/s · ${state?.policy.angular_rad_s} rad/s`} · input expiry {physical?(robot.timing_values?.input_ttl_ms??state?.policy.input_expiry_ms):state?.policy.input_expiry_ms} ms</p>
      {physical&&robot.timing_values&&<p className="robot-fleet-policy">Session timing: sensor source {robot.timing_values.sensor_source_ms} ms · receipt {robot.timing_values.sensor_receipt_ms} ms · odometry {robot.timing_values.odom_interval_ms} ms · output {robot.output_timing?.output_timeout_ms??'readback not confirmed'} ms. Edit next-connection values in Robots → Timing settings.</p>}
      {physical&&robot.odom_interval&&<p className="robot-fleet-policy">Odometry sample interval: {(robot.odom_interval.interval_s*1000).toFixed(1)} ms / {(robot.odom_interval.limit_s*1000).toFixed(0)} ms · {robot.odom_interval.reason}</p>}
      <small>{physical?'Object destinations use an operator-reviewed Twin anchor and current relative LiDAR tracking under the supervised field setup. The robot-local guard checks each low-speed output. An estimated destination is not verified furniture arrival; lost tracking, a new obstacle or a changed Twin stops the route.':'SIM supports a nearby scene destination, finite distance/angle, status, logs and Stop.'}</small>
      <button type="button" onClick={()=>{release.current();setLidarReviewOpen(true);}}>Review LiDAR scans</button>
      {physical&&<>
        <p className="robot-fleet-policy" aria-label="Physical navigation map">Map: {state?.navigation_scene?.status==='AVAILABLE'?(state.navigation_scene.kind==='imported'?'Imported space · shared floor mask':'Current Twin geometry'):'Unavailable'} · Scale: {state?.navigation_scene?.units_basis==='selected_for_sim'?'user-selected estimate':'unqualified'} · Physical accuracy unqualified.</p>
        <small>Review the anchor in this connection and current Twin. Reconnect or a changed Twin requires a new review; estimated scale and relative LiDAR tracking do not establish measured world alignment.</small>
        <dl className="robot-physical-status" aria-label="Physical connection and readiness">
          <div><dt>SSH heartbeat</dt><dd>{available&&fresh?'Fresh authenticated session':'Unavailable / stale'} · age {age(robot.telemetry_age_ms)}</dd></div>
          <div><dt>Battery</dt><dd>{fleetBatteryLabel(robot)}{!available?' · receipt stale':''} · age {age(robot.battery.age_ms)}</dd></div>
          <div><dt>Control</dt><dd>{robot.control_state} · controller {scalar(robot.controller_state)}</dd></div>
          <div><dt>Sensor</dt><dd>LiDAR {lidarDiagnosticLabel(robot,available)} · source {scalar(record(robot.sensor_frame).source??robot.scan?.source)} · age {age(record(robot.sensor_frame).age_ms)}{!available?' · receipt stale':''}</dd></div>
          <div><dt>ROS receipt diagnosis</dt><dd>Last reported check: {scalar(record(robot.telemetry_diagnostic).reason)} · source {age(typeof record(robot.telemetry_diagnostic).source_age_s==='number'?(record(robot.telemetry_diagnostic).source_age_s as number)*1000:null)} · sensor {age(typeof record(robot.telemetry_diagnostic).sensor_receipt_age_s==='number'?(record(robot.telemetry_diagnostic).sensor_receipt_age_s as number)*1000:null)} · guard {age(typeof record(robot.telemetry_diagnostic).guard_receipt_age_s==='number'?(record(robot.telemetry_diagnostic).guard_receipt_age_s as number)*1000:null)}</dd></div>
          {robot.motion_observation&&<div><dt>Wheel observation</dt><dd aria-label="Wheel observation">{scalar(robot.motion_observation.state)} · {scalar(robot.motion_observation.direction)} · {typeof robot.motion_observation.centre_m==='number'?`${(robot.motion_observation.centre_m*1000).toFixed(1)} mm`:'distance unknown'} · {typeof robot.motion_observation.yaw_rad==='number'?`${(robot.motion_observation.yaw_rad*180/Math.PI).toFixed(1)}°`:'angle unknown'} · Body motion unknown · {scalar(robot.motion_observation.reason)}</dd></div>}
          <div><dt>Voltage read</dt><dd>{scalar(record(robot.battery.read_status).state)} · {scalar(record(robot.battery.read_status).reason)}</dd></div>
          <div><dt>Recording</dt><dd>{available&&fresh?'':'Last reported · '}{robot.recording_state}</dd></div>
          <div><dt>Cleanup</dt><dd>{robot.cleanup_confirmed===true?'Confirmed by robot':robot.cleanup_confirmed===false?'Not confirmed':'Unknown · no cleanup receipt'}</dd></div>
        </dl>
        {fleetBatteryPolicyMessage(robot)&&<p className="robot-fleet-policy" aria-label="Battery estimate and protection">{fleetBatteryPolicyMessage(robot)}</p>}
        <p className="robot-fleet-policy">Connect keeps one authenticated SSH session and starts no motor or sensor. Fresh heartbeat and measured voltage do not grant driving permission. Reconnect requires Disconnect first.</p>
        {!robot.capabilities.drive&&<p role="status">Protected manual movement is unavailable until the runtime grants drive capability. The separate supervised field-test path has its own explicit admission below. Status, Stop and operation logs remain available.</p>}
      </>}
      {physical&&<RobotFieldTests key={`${context}:${robot.robot_id}`} robot={robot} available={available&&adapterAvailable&&!selectionPending} busy={busy} includeGate={false}
        onAction={(name,payload)=>{release.current();void action(envelope(name,robot,payload));}} onOpenLogs={()=>void logs()}/>}
      {physical&&<details className="robot-physical-setup">
        <summary>Physical setup · {scalar(robot.setup?.runtime_state)}</summary>
        <p>Prepare opens the reviewed controller in zero-command mode. Qualification performs the existing supervised stop test and may move the robot. Each requires a new explicit confirmation; neither runs on Connect or reconnect.</p>
        <p>The supervisor confirmations, Prepare, stop qualification, Arm and Bootstrap stop are in the session gate under the buttons above (always visible).</p>
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
          <details key={robot.robot_id} aria-label="Measured profile guide">
            <summary>Measured profile guide</summary>
            <p>This is a measurement preparation checklist, not an automatic instrument or certification. Missing required measurements (null) block protected driving. With the robot off, only form preparation and source review are available. Actual sensor, timing, stopping and progress measurements need separate on-site supervision.</p>
            <ol>
              <li><strong>Bind robot and evidence</strong><p>Use the current robot_id and binding_sha256. Recheck after mounting, wiring or configuration changes. Each *_sha256 must identify verified original measurement data; the app does not invent hashes or certify evidence.</p></li>
              <li><strong>Geometry · body and sensor</strong><p>Establish base_link origin, forward x and left y. Measure sensor_xy_yaw=[x(m),y(m),yaw(rad)] and actual sensor_frame. Confirm native_angle_sign (+1 or -1) against an opaque target at a known location. Record the actual outline, including wheels and protrusions, as a counterclockwise convex footprint_xy_m polygon of 3–16 points containing the origin. Retain planar_extrinsic_sha256 and footprint_sha256 sources. Photos, nominal URDF and estimated Twin markers cannot replace measurements.</p></li>
              <li><strong>Sampling · coverage and blind spots</strong><p>Observe opaque targets at measured distances and directions. Conservatively determine minimum_range_m, maximum_range_m, minimum_quality, maximum_gap_deg, minimum_target_width_m and range_uncertainty_m. Link original tests with opaque_target_coverage_sha256. Keep original nonuniform angles. No returns, low quality and large gaps mean UNKNOWN, not free space. This model does not certify detection of glass, thin cords, or obstacles above or below the sensor plane.</p></li>
              <li><strong>Timing · sample to control</strong><p>Record original byte receipt, acquisition-time evidence, decoding, delivery and guard times on a verified common time basis. Measure worst-case maximum_pipeline_age_s in seconds and link measurement_sha256. Use measured provenance only after actual measurement. The 0.2-second maximum is a policy limit, not a measured default. Stored raw without timing sidecars, SSH ping and file modification times cannot stand in for sample timing.</p></li>
              <li><strong>Stop model · actual stopping</strong><p>With sufficient space and supervision, use the existing stop-verification path to record forward/backward and rotation commands, observations, stopping distance and angle. Derive reaction_s, minimum linear/angular deceleration, speed/position uncertainty and maximum scan/input age from original data; link stopping_measurement_sha256. Policy limits: body_clearance_m at least 0.10m from the body outline, speeds at most 0.05m/s and 0.30rad/s, scan/input ages at most 0.2/0.25 seconds. These are not automatically filled measurements. Same-boot/release stop qualification is separately required.</p></li>
              <li><strong>Progress · wheels and independent body</strong><p>In a supervised interval, derive wheel_metres_per_tick and wheel_separation_m from encoders and measured travel/spacing. Measure window_s, maximum_sample_gap_s, minimum_command_m_s, minimum_wheel_progress_m and maximum_wheel_speed_m_s from same-window commands and wheel odometry; link measurement_sha256. Explicitly review body_progress_policy; there is no default. With independent_required or no selection, independent camera/position measurements must also establish minimum_body_translation_m, minimum_body_rotation_rad, maximum_body_speed_m_s and maximum_body_rotation_rad_s. Only explicitly_unverified_supervised permits these four values to remain null. Preserve supplied positive values; do not substitute zero or estimates. Body progress remains UNKNOWN, not a body-stall/slip PASS. Wheel odometry is not independent body evidence. Geometry, sampling, timing, stopping and wheel measurements are required in both modes.</p></li>
              <li><strong>Review and save original evidence</strong><p>Stored native/odom data can be reanalysed but cannot supply missing extrinsic, footprint, stopping, independent body or byte-timing measurements. Review new original data and IDs/SHA before reviewing/applying JSON. Strict server schema errors are shown on screen. Saving a profile or reading this checklist grants no connection, sensor-start or driving permission.</p></li>
            </ol>
            <button type="button" disabled={!robot.setup?.binding_sha256} onClick={downloadProfileTemplate}>Download blank measured-profile JSON</button>
            <button type="button" disabled={!robot.setup?.binding_sha256} onClick={()=>{
              importGeneration.current++;setProfileReading(false);setProfileReview(null);setProfileReviewed(false);setProfileError(null);
              setProfileDraft(JSON.stringify(blankMeasuredProfile(robot),null,2));
            }}>Start blank profile in App</button>
            {!robot.setup?.binding_sha256&&<p>The registered binding ID is unavailable. Refresh registration before creating a blank form; starting a connection is not required.</p>}
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
      {lidarReviewOpen&&<LidarReviewDialog api={api} robot={robot} onClose={()=>setLidarReviewOpen(false)} onStopAll={()=>{release.current();void send(envelope('stop_all',null)).catch(reportError);}}/>}
      {robot.scan&&<details><summary>LiDAR points · {robot.scan.points.length} · {robot.scan.source}</summary>
        <LidarPointView points={robot.scan.points} source={robot.scan.source} height={robot.scan.height_m}/>
        {robot.kind==='physical'&&<small>PC scan receipt age: {age(robot.scan_receipt?.age_ms)} · acquisition timing is separate · {robot.scan.complete===true?'complete ring':'incomplete / unknown ring'} · not projected into Twin without a synchronized pose and sensor transform.</small>}
        <small>Sensor points only · obstacle protection depends on the active adapter and guard.</small></details>}
      {historicalOperation&&<small>Saved operation logs · historical. Viewing this record does not restore a connection or driving permission.</small>}
      {logOperationId&&<small className="robot-operation-id">Operation {logOperationId}{historicalOperation?' · historical':''}</small>}
      {logOperationId&&<details aria-label="Robot Twin record linkage"><summary>Record linkage · chat / Twin version</summary>
        <dl className="robot-physical-status">
          <div><dt>Chat project</dt><dd>{scalar(shownSourceContext.project_id??robot.current_twin_context?.project_id)}</dd></div>
          <div><dt>Conversation ID</dt><dd>{scalar(shownSourceContext.conversation_session_id,80)}</dd></div>
          <div><dt>Connection-start Twin</dt><dd>{scalar(shownSourceContext.scene_revision,80)}</dd></div>
          <div><dt>Current Twin</dt><dd>{scalar(robot.current_twin_context?.scene_revision,80)}</dd></div>
          <div><dt>Reference relation</dt><dd>{scalar(shownRelation)}</dd></div>
          <div><dt>Coordinate alignment</dt><dd>{scalar(record(shownSourceContext.alignment).status??'UNKNOWN')}</dd></div>
        </dl>
        <small>{physical?'Physical raw data references the connection-start Twin. This does not certify acquisition-time scene synchronization or world alignment. To use a new Twin as collection reference, Disconnect and then Check Connection to start a new operation.':'Each SIM observation records its actual engine / stage / Twin revision. Later observations can differ from the connection-start revision.'}</small>
        {robot.twin_context_relation&& !['SAME_TWIN_REFERENCE_NOT_ALIGNMENT_PROOF','LEGACY_UNKNOWN'].includes(robot.twin_context_relation)&&
          <p role="status">Twin references differ or the current reference is unconfirmed. Historical records are not relabelled as the current Twin. Stop and raw records remain available.</p>}
      </details>}
      <RobotOperationDiagnostics robot={robot} operation={operation} available={available}/>
      <RobotMotionReview api={api} operation={operation?.operation_id??null} physical={physical}/>
      {operation&&operationSummary&&<section className="robot-operation-log" aria-label="Operation summary">
        <h5>Operation · {scalar(operation.operation_id,80)}</h5>
        <p>{operation.events.length} events · showing {operationSummary.events.length} recent summaries, including up to 5 observations.</p>
        <p>{physical?'The JSON contains summaries and receipts. Download the separate runtime evidence segments below for original sensor bytes and helper logs.':'Complete source events, scan points and manifest details are included in the download.'}</p>
        {logBusy&&<p role="status">Refreshing operation log; download waits for the response.</p>}
        <button type="button" disabled={logBusy} onClick={download}>Download operation JSON</button>
        <dl aria-label="Operation manifest summary">{operationSummary.rows.map(([key,value],index)=><div key={`${index}:${key}`}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
        {operationSummary.evidenceCount>0&&<details><summary>Physical runtime evidence · {operationSummary.evidenceCount} files</summary>
          <p>Source paths, SHA256 and receipt status come from the runtime manifest. The complete JSON includes all receipts and missing evidence.</p>
          <ul className="robot-runtime-evidence">{operationSummary.evidence.map((item,index)=><li key={index}>{item.path}<small>SHA256 {item.sha} · {item.status}</small>
            <button type="button" disabled={!item.file||evidenceBusy!==null} onClick={()=>{if(item.file)void downloadEvidence(item.file);}}>Download {item.file??'unavailable file'}</button></li>)}</ul>
          {operationSummary.evidenceCount>operationSummary.evidence.length&&<small>Showing the first {operationSummary.evidence.length} files; download the complete operation JSON for all evidence.</small>}
        </details>}
        <ol aria-label="Recent operation events">{operationSummary.events.map(event=><li key={event.index}>
          <strong>#{event.index+1} · {event.kind}</strong><span>{event.detail}</span></li>)}</ol>
      </section>}
      </details>{physical&&<button type="button" title={robot.display_pose?'Estimated robot position saved · not localized':'Robot not placed in Twin'} onClick={()=>{release.current();setDiagnosticsOpen(!markerOpen);setMarkerOpen(value=>!value);}}>{markerOpen?'Hide position':'Set position'}</button>}<button type="button" disabled={!logOperationId||logBusy} onClick={()=>{release.current();void logs();}}>Operation logs</button></div>
    </section>}
    {error&&(!robot||!drawerOpen)&&<p role="alert">{error}</p>}
  </section>;
}
