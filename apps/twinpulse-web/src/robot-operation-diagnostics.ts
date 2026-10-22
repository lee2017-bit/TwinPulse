// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
import {fleetRobotFresh,type RobotFleetOperation,type RobotFleetRobot} from './robot-fleet-types';

export const diagnosticFileLimit=8*1024*1024;
const diagnosticLineLimit=256*1024;
export const diagnosticRecord=(value:unknown):Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value);
export const diagnosticText=(value:unknown,limit=180)=>typeof value==='string'?value.slice(0,limit):finite(value)?String(value):typeof value==='boolean'?String(value):'not recorded';
const measured=(value:unknown,scale=1)=>finite(value)&&value>=0?value*scale:null;
export type DiagnosticCategory='input'|'sensor'|'tracking'|'battery'|'stop'|'recording'|'state';
export type DiagnosticRow={index:number;kind:string;categories:DiagnosticCategory[];clock:string;time:number|string|null;epoch:string;
  sequence:number|null;scene:string;request:string;values:[string,string][];sourceAgeMs:number|null;sensorIdentity:string|null;
  callbackReceiptS:number|null;sensorStream:string|null;controlState:string|null;pauseId:string|null;
  computeMs:number|null;computeIdentity:string|null};
export type DiagnosticProjection={rows:DiagnosticRow[];sourceEvents:number;rawOmitted:number;unverifiedIdentities:number};
export function lidarDiagnosticLabel(robot:RobotFleetRobot,available=true){
  return available&&fleetRobotFresh(robot)?robot.lidar_state:`No current stream · last reported ${robot.lidar_state}`;
}
const ms=(value:unknown)=>{const n=measured(value,1000);return n===null?'not recorded':`${n.toFixed(2)} ms`;};
function rowFor(event:Record<string,unknown>,index:number):DiagnosticRow|null{
  const data=diagnosticRecord(event.data),kind=diagnosticText(event.kind??event.event??event.type??(event.action?`input ${event.action}`:event.schema),80);
  const raw=kind==='raw';
  // Native byte payloads and CDR/base64 never enter the DOM. Only the original
  // sensor callback metadata is projected; it is not decoded or resubmitted.
  if(kind==='raw_source'||raw&&(data.source!=='serialized_ros_message'||data.topic!=='sensor_state'))return null;
  const values:[string,string][]=[],categories=new Set<DiagnosticCategory>();
  const value=(name:string,item:unknown)=>{if(item!==null&&item!==undefined)values.push([name,diagnosticText(item)]);};
  const numeric=(name:string,item:unknown,scale=1)=>{if(finite(item))values.push([name,`${(item*scale).toFixed(2)}${scale===1000?' ms':''}`]);};
  const diagnostic=diagnosticRecord(data.telemetry_diagnostic),callback=diagnosticRecord(raw?data.callback_timing:diagnostic.callback_timing);
  const originalFailure=diagnosticRecord(data.last_control_fault),failedCheck=diagnosticRecord(originalFailure.telemetry);
  if(Object.keys(originalFailure).length){categories.add('stop');categories.add('sensor');
    value('original failed control reason',originalFailure.reason);value('original failed check reason',failedCheck.reason);
    value('original failed check robot s',failedCheck.checked_monotonic_s);
    numeric('original failed sensor receipt age',failedCheck.sensor_receipt_age_s,1000);
    numeric('original failed guard receipt age',failedCheck.guard_receipt_age_s,1000);}
  const tracking=diagnosticRecord(diagnosticRecord(data.field).tracking??data.tracking),timing=diagnosticRecord(tracking.compute_timing);
  const epoch=diagnosticText(event.connection_epoch??data.connection_epoch,80);
  const robotTime=finite(event.robot_monotonic_s),pcSentTime=finite(event.pc_sent_monotonic_s),hostTime=finite(event.monotonic_s);
  const clock=robotTime?'robot_monotonic_s':pcSentTime?'pc_sent_monotonic_s':hostTime?'monotonic_s · host domain unqualified':typeof event.utc==='string'?'recorded UTC':'record order only';
  const time=robotTime?event.robot_monotonic_s as number:pcSentTime?event.pc_sent_monotonic_s as number:hostTime?event.monotonic_s as number:typeof event.utc==='string'?event.utc:null;
  if(/input|command|intent|drive|request|action/.test(kind)){categories.add('input');
    for(const key of ['action','status','direction','reason'])value(key,data[key]??event[key]);
    const payload=diagnosticRecord(data.payload??data.parameters??event.payload);for(const key of ['direction','amount','sequence','expires_at_ms','source_age_ms'])value(`input ${key}`,payload[key]);
    value('input age ms',data.age_ms);value('accepted sequence',data.sequence);
  }
  const delivery=diagnosticRecord(data.event_delivery);
  if(Object.keys(delivery).length){categories.add('input');
    numeric('event payload preparation',delivery.payload_prepare_s,1000);numeric('event order-lock wait',delivery.order_lock_wait_s,1000);
    value('event payload original start s',delivery.payload_started_s);value('event ordered s',delivery.ordered_s);}
  const motion=diagnosticRecord(data.motion_observation);
  if(Object.keys(motion).length){categories.add('tracking');
    for(const key of ['state','direction','result','reason','request_id','latest_request_id','sample_s','samples','body_progress','independent_comparison','basis','stop_readback_confirmed'])value(`wheel ${key}`,motion[key]);
    if(finite(motion.centre_m))value('wheel centre mm',(motion.centre_m*1000).toFixed(2));numeric('wheel yaw rad',motion.yaw_rad);}
  let sourceAgeMs:number|null=null,sensorIdentity:string|null=null,callbackReceiptS:number|null=null,sensorStream:string|null=null;
  if(raw||Object.keys(diagnostic).length){categories.add('sensor');
    if(raw){value('topic',data.topic);value('ROS stream',data.stream_id);value('callback sequence',data.observation_sequence);
      value('source stamp ns · recorded precision',callback.source_stamp_ns);value('ROS now ns · recorded precision',callback.receipt_ros_now_ns);
      numeric('source age at callback',callback.source_age_at_receipt_s,1000);
      value('callback robot receipt s',data.receipt_end_s);
      if(typeof data.stream_id==='string'&&data.stream_id&&Number.isSafeInteger(data.observation_sequence)&&(data.observation_sequence as number)>=0){
        sourceAgeMs=measured(callback.source_age_at_receipt_s,1000);
        sensorIdentity=`${epoch}/${data.stream_id}/sensor_state/${data.observation_sequence}`;
        callbackReceiptS=measured(data.receipt_end_s);sensorStream=`${epoch}/${data.stream_id}`;
      }
    }else{
      value('diagnostic reason at record',diagnostic.reason);numeric('source age at check',diagnostic.source_age_s,1000);
      numeric('sensor callback receipt age',diagnostic.sensor_receipt_age_s,1000);numeric('guard callback receipt age',diagnostic.guard_receipt_age_s,1000);
      numeric('diagnostic check age',diagnostic.check_age_s,1000);value('diagnostic checked robot s',diagnostic.checked_monotonic_s);
      value('prior check reason',diagnostic.last_check_reason);
    }
  }
  const native=diagnosticRecord(data.lidar??data.native_diagnostic);
  if(Object.keys(native).length){categories.add('sensor');for(const key of ['lidar_state','frame_count','checksum_errors','unframed_segments'])value(`native ${key}`,native[key]);
    numeric('native last frame publication age',native.last_frame_publish_age_s,1000);}
  let computeMs:number|null=null,computeIdentity:string|null=null;
  if(Object.keys(tracking).length){categories.add('tracking');for(const key of ['status','reason','sample_s','epoch','stream_id','frame_sequence','raw_sha256'])value(`tracking ${key}`,tracking[key]);
    for(const key of ['stage','job_id'])value(`compute ${key}`,timing[key]);numeric('compute elapsed',timing.compute_elapsed_s,1000);numeric('compute delivery elapsed',timing.delivery_elapsed_s,1000);
    if(Number.isSafeInteger(timing.job_id)&&typeof tracking.stream_id==='string'&&finite(timing.compute_elapsed_s)){
      computeMs=measured(timing.compute_elapsed_s,1000);computeIdentity=`${epoch}/${tracking.stream_id}/${timing.job_id}`;
    }
  }
  const battery=diagnosticRecord(data.battery);
  if(Object.keys(battery).length){categories.add('battery');numeric('battery voltage V',battery.voltage_v);numeric('battery age ms',battery.age_ms);value('battery origin',battery.origin??battery.source);}
  if(/stop|cleanup|pause|fault/.test(kind)||data.reason&&/STOP|PAUSE|CLEANUP/.test(String(data.reason))){categories.add('stop');
    for(const key of ['reason','status','confirmed','cleanup_confirmed','ros_stop_confirmed','independent_idle_confirmed','base_reaped','pause_id','observed_monotonic_s','motion_generation','zero_off_readback_confirmed'])value(`stop ${key}`,data[key]);}
  for(const [name,record] of [['recording',diagnosticRecord(data.recording)],['ROS recording',diagnosticRecord(data.ros_record_delivery)],['field evidence',diagnosticRecord(data.field_evidence)]] as const){
    if(Object.keys(record).length){categories.add('recording');for(const key of ['error','complete','accepted','saved','queued','pending','slowest_event_kind'])value(`${name} ${key}`,record[key]);
      for(const key of ['max_write_s','maximum_delivery_s','oldest_pending_age_s','oldest_pending_s'])numeric(`${name} ${key}`,record[key],1000);}
  }
  const field=diagnosticRecord(data.field);if(field.evidence_error){categories.add('recording');value('field evidence error',field.evidence_error);}
  const fieldStatus=diagnosticRecord(field.evidence_status);if(Object.keys(fieldStatus).length){categories.add('recording');
    for(const key of ['error','pending','phase'])value(`field writer ${key}`,fieldStatus[key]);
    for(const key of ['phase_elapsed_s','phase_max_s','oldest_pending_s'])numeric(`field writer ${key}`,fieldStatus[key],1000);}
  if(/error|record|writer/.test(kind)){categories.add('recording');for(const key of ['reason','error','status'])value(key,data[key]??event[key]);}
  for(const key of ['control_state','reason','recording_state'])value(key,data[key]);
  if(!categories.size)categories.add('state');
  const sourceContext=diagnosticRecord(data.source_twin_context??event.source_twin_context??event.twin_context??data.twin_context),requestContext=diagnosticRecord(data.request_twin_context??event.request_twin_context);
  return {index,kind,categories:[...categories],clock,time,epoch,sequence:finite(event.sequence)?event.sequence:null,
    scene:diagnosticText(sourceContext.scene_revision??requestContext.scene_revision??event.source_twin_context_id,80),
    request:diagnosticText(data.request_id??event.request_id,80),values:values.slice(0,56),sourceAgeMs,sensorIdentity,callbackReceiptS,sensorStream,
    controlState:typeof data.control_state==='string'?data.control_state:null,pauseId:typeof data.pause_id==='string'?data.pause_id:null,computeMs,computeIdentity};
}
export function projectDiagnosticEvents(events:Record<string,unknown>[]):DiagnosticProjection{
  const rows:DiagnosticRow[]=[];let rawOmitted=0,unverifiedIdentities=0;
  for(let index=0;index<events.length;index++){
    const event=events[index],row=rowFor(event,index);if(row)rows.push(row);else rawOmitted++;
    if(event.operation_id===undefined)unverifiedIdentities++;
  }
  return {rows,sourceEvents:events.length,rawOmitted,unverifiedIdentities};
}
export function diagnosticStatistics(rows:DiagnosticRow[],field:'sensor'|'compute'){
  const unique=new Map<string,number>();let conflicting=0;
  for(const row of rows){const id=field==='sensor'?row.sensorIdentity:row.computeIdentity,value=field==='sensor'?row.sourceAgeMs:row.computeMs;
    if(id&&value!==null){if(unique.has(id)&&unique.get(id)!==value)conflicting++;else unique.set(id,value);}}
  const values=[...unique.values()].sort((a,b)=>a-b),n=values.length;
  if(conflicting||n<2)return {n,conflicting,mean:null,sd:null,p99:null,p999:null,max:conflicting?null:n?values[n-1]:null};
  const mean=values.reduce((sum,value)=>sum+value,0)/n;
  return {n,conflicting,mean,sd:Math.sqrt(values.reduce((sum,value)=>sum+(value-mean)**2,0)/(n-1)),p99:values[Math.ceil(.99*n)-1],p999:values[Math.ceil(.999*n)-1],max:values[n-1]};
}
export function diagnosticContinuity(rows:DiagnosticRow[],sourceLimitMs:number|null){
  const seen=new Map<string,{receipt:number|null;age:number|null}>(),last=new Map<string,number>();let maximumGapMs:number|null=null,gaps=0,clockConflicts=0,over=0,ages=0,missingReceipts=0;
  for(const row of rows){if(!row.sensorIdentity||!row.sensorStream)continue;
    const prior=seen.get(row.sensorIdentity);if(prior){if(prior.receipt!==row.callbackReceiptS||prior.age!==row.sourceAgeMs)clockConflicts++;continue;}
    seen.set(row.sensorIdentity,{receipt:row.callbackReceiptS,age:row.sourceAgeMs});
    if(row.sourceAgeMs!==null){ages++;if(sourceLimitMs!==null&&row.sourceAgeMs>=sourceLimitMs)over++;}
    if(row.callbackReceiptS===null){missingReceipts++;continue;}
    const previous=last.get(row.sensorStream);if(previous!==undefined){const gap=row.callbackReceiptS-previous;if(gap<0)clockConflicts++;else{gaps++;maximumGapMs=Math.max(maximumGapMs??0,gap*1000);}}
    last.set(row.sensorStream,row.callbackReceiptS);
  }
  return {callbacks:seen.size,gaps,maximumGapMs:clockConflicts||missingReceipts?null:maximumGapMs,clockConflicts,missingReceipts,sourceLimitMs,
    over:sourceLimitMs===null||clockConflicts?null:over,ageSamples:ages,overPercent:sourceLimitMs===null||clockConflicts||!ages?null:over/ages*100};
}
export function diagnosticPauseWindows(rows:DiagnosticRow[]){
  const groups=new Map<string,{clock:string;epoch:string;first:number;last:number;lastState:string|null;stateSamples:number;initialPaused:number;transitions:number;ids:Set<string>}>();
  for(const row of rows){if(typeof row.time!=='number'||(!row.controlState&&!row.pauseId))continue;const key=`${row.clock}/${row.epoch}`;
    let group=groups.get(key);if(!group){group={clock:row.clock,epoch:row.epoch,first:row.time,last:row.time,lastState:null,stateSamples:0,initialPaused:0,transitions:0,ids:new Set()};groups.set(key,group);}
    group.last=Math.max(group.last,row.time);group.first=Math.min(group.first,row.time);
    if(row.pauseId)group.ids.add(row.pauseId);
    if(row.controlState){if(!group.stateSamples&&row.controlState==='PAUSED')group.initialPaused++;
      if(group.lastState&&group.lastState!=='PAUSED'&&row.controlState==='PAUSED')group.transitions++;
      group.stateSamples++;group.lastState=row.controlState;}
  }
  return [...groups.values()].map(group=>{const seconds=group.last-group.first,count=group.ids.size||group.transitions;
    return {clock:group.clock,epoch:group.epoch,seconds,count,initialPaused:group.initialPaused,method:group.ids.size?'explicit distinct pause IDs':'observed PAUSED transitions · lower bound',perHour:seconds>0?count/seconds*3600:null};});
}
export function recordedTimingPolicy(operation:RobotFleetOperation|null){
  if(!operation)return null;
  for(let i=operation.events.length-1;i>=0;i--){const value=diagnosticRecord(diagnosticRecord(operation.events[i].data).timing_policy);if(Object.keys(value).length)return value;}
  return null;
}
export function currentDiagnosticStatus(robot:RobotFleetRobot,available:boolean){
  if(!available||!fleetRobotFresh(robot))return 'No current diagnostic · disconnected or receipt stale';
  const diagnostic=diagnosticRecord(robot.telemetry_diagnostic),policy=diagnosticRecord(diagnosticRecord(robot).timing_policy);
  const limit=diagnosticRecord(diagnosticRecord(policy.limits).ros_receipt).seconds,age=diagnostic.check_age_s;
  if(finite(age)&&finite(limit)&&age>=0&&age<limit&&finite(diagnostic.checked_monotonic_s))return 'Current diagnostic check · validity is separate from drive permission';
  return 'Last reported diagnostic · current check validity not established';
}
export function liveDiagnosticRows(robot:RobotFleetRobot):[string,string][]{
  const d=diagnosticRecord(robot.telemetry_diagnostic),tracking=diagnosticRecord(robot.field?.tracking),timing=diagnosticRecord(tracking.compute_timing),evidence=diagnosticRecord(diagnosticRecord(robot).field_evidence),writer=diagnosticRecord(diagnosticRecord(robot.field).evidence_status);
  return [['Reported reason',diagnosticText(d.reason)],['Source age at check',ms(d.source_age_s)],['Sensor callback receipt age',ms(d.sensor_receipt_age_s)],
    ['Guard callback receipt age',ms(d.guard_receipt_age_s)],['Diagnostic check age',ms(d.check_age_s)],['Tracking state',diagnosticText(tracking.status)],
    ['Tracking reason',diagnosticText(tracking.reason)],['Measured compute duration',ms(timing.compute_elapsed_s)],['Field evidence error',diagnosticText(evidence.error??diagnosticRecord(robot.field).evidence_error)],
    ['Writer phase',diagnosticText(writer.phase)],['Writer phase duration',ms(writer.phase_elapsed_s)],['Writer maximum phase duration',ms(writer.phase_max_s)],['Writer pending',diagnosticText(writer.pending)],['Writer oldest pending',ms(writer.oldest_pending_s)]];
}
export type ImportedDiagnostics={projection:DiagnosticProjection;sha256:string;bytes:number;name:string;scope:'selected JSONL segment'|'selected operation JSON';verifiedManifest:boolean};
const abort=()=>new Error('Diagnostic file reading cancelled. No control or sensor command was sent.');
export async function readDiagnosticFile(file:File,operation:RobotFleetOperation,signal:AbortSignal,progress:(bytes:number)=>void=()=>{}):Promise<ImportedDiagnostics>{
  if(!file.size||file.size>diagnosticFileLimit)throw new Error('Choose one non-empty diagnostic JSON/JSONL segment of at most 8 MiB.');
  if(!/\.jsonl?$/i.test(file.name))throw new Error('Choose a recorded JSON or JSONL file.');
  const rows:Record<string,unknown>[]=[],parts:Uint8Array[]=[],decoder=new TextDecoder();let text='',lines=0;
  const check=()=>{if(signal.aborted)throw abort();};
  const add=(line:string)=>{if(line.length>diagnosticLineLimit)throw new Error('Diagnostic line exceeds 256 KiB.');
    let event:unknown;try{event=JSON.parse(line);}catch{throw new Error(`Diagnostic JSONL parse failed at line ${lines}. No partial analysis was accepted.`);}
    const value=diagnosticRecord(event);if(!Object.keys(value).length)throw new Error(`Diagnostic event is not an object at line ${lines}.`);
    if(value.operation_id!==operation.operation_id||value.robot_id!==operation.robot_id)throw new Error('Recorded operation / robot identity differs from the open operation.');
    // Reduce raw byte payloads immediately; do not retain multi-megabyte CDR
    // or source-code/base64 strings in projected replay state.
    if(value.kind==='raw'||value.kind==='raw_source'){
      const data=diagnosticRecord(value.data);value.data={source:data.source,topic:data.topic,stream_id:data.stream_id,observation_sequence:data.observation_sequence,receipt_end_s:data.receipt_end_s,callback_timing:data.callback_timing};
    }
    rows.push(value);if(rows.length>100000)throw new Error('Diagnostic file exceeds 100,000 records. Choose a smaller segment.');
  };
  const jsonl=/\.jsonl$/i.test(file.name);
  for(let offset=0;offset<file.size;offset+=64*1024){
    check();const part=new Uint8Array(await file.slice(offset,Math.min(offset+64*1024,file.size)).arrayBuffer());check();parts.push(part);
    text+=decoder.decode(part,{stream:true});
    if(jsonl){let boundary;while((boundary=text.indexOf('\n'))>=0){const line=text.slice(0,boundary).trim();text=text.slice(boundary+1);lines++;if(line)add(line);}
      if(text.length>diagnosticLineLimit)throw new Error('Diagnostic line exceeds 256 KiB.');}
    progress(Math.min(offset+part.length,file.size));await new Promise(resolve=>setTimeout(resolve,0));
  }
  text+=decoder.decode();check();
  if(jsonl){if(text.trim()){lines++;add(text.trim());}}
  else{
    let document:unknown;try{document=JSON.parse(text);}catch{throw new Error('Invalid operation JSON. No partial analysis was accepted.');}
    const value=diagnosticRecord(document);
    if(value.operation_id!==operation.operation_id||value.robot_id!==operation.robot_id||!Array.isArray(value.events))throw new Error('Choose an operation JSON for the open operation and robot.');
    for(let i=0;i<value.events.length;i++){check();const event=value.events[i],row=diagnosticRecord(event);if(!Object.keys(row).length)throw new Error('Invalid operation event.');
      if(row.operation_id!==undefined&&row.operation_id!==operation.operation_id||row.robot_id!==undefined&&row.robot_id!==operation.robot_id)throw new Error('Mixed operation / robot identities in the operation JSON.');
      rows.push(row);if(rows.length>100000)throw new Error('Diagnostic file exceeds 100,000 records.');if(i%256===255)await new Promise(resolve=>setTimeout(resolve,0));}
  }
  if(!rows.length)throw new Error('No diagnostic records in this file.');
  const bytes=new Uint8Array(file.size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
  const sha256=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(value=>value.toString(16).padStart(2,'0')).join('');check();
  const segmentName=file.name.match(/events-\d{5}\.jsonl$/)?.[0],stream=diagnosticRecord(operation.manifest.stream),segments=Array.isArray(stream.segments)?stream.segments:[];
  const expected=segments.map(diagnosticRecord).find(item=>item.path===segmentName);
  if(expected&&(expected.sha256!==sha256||expected.bytes!==file.size))throw new Error('Selected segment bytes / SHA256 differ from the operation manifest.');
  const projection:DiagnosticProjection={rows:[],sourceEvents:rows.length,rawOmitted:0,unverifiedIdentities:0};
  for(let i=0;i<rows.length;i+=256){check();const part=projectDiagnosticEvents(rows.slice(i,i+256));
    projection.rows.push(...part.rows.map(row=>({...row,index:row.index+i})));projection.rawOmitted+=part.rawOmitted;projection.unverifiedIdentities+=part.unverifiedIdentities;
    await new Promise(resolve=>setTimeout(resolve,0));}
  check();return {projection,sha256,bytes:file.size,name:file.name,scope:jsonl?'selected JSONL segment':'selected operation JSON',verifiedManifest:!!expected};
}
