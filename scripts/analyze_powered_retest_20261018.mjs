// SPDX-License-Identifier: Apache-2.0
// OFFLINE: verify the UI-exported originals, preserve bytes, summarize failures.
// No network, App, device or model calls. Artifact writing is analysis only.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import {createHash} from 'node:crypto';
const root=path.resolve(process.argv[2]??'outputs/robot-retest-20261018');
const dir=path.join(root,'raw'),output=path.join(root,'analysis');
fs.mkdirSync(output,{recursive:true});
const sha=b=>createHash('sha256').update(b).digest('hex');
const receipt=JSON.parse(fs.readFileSync(path.join(dir,'receipt.json'),'utf8'));
const scope=fs.existsSync(path.join(root,'session-scope.json'))?JSON.parse(fs.readFileSync(path.join(root,'session-scope.json'),'utf8')):{};
const result={schema:'powered-retest-original-analysis-1.0',method:'OFFLINE_ORIGINAL_UI_DOWNLOADS',
  recorded_release:scope.release_id??'NOT_RECORDED_IN_SCOPE',receipt,files:[],commands:[],faults:[],cleanup:[],
  topics:{},reasons:{},diagnostic_reasons:{},tracking_reasons:{},raw:{chunks:0,ros_messages:0,sha_errors:0},
  first_t:null,last_t:null,max_generation:0,stale_diagnostic_example:null,identity:null};
const metrics={source_age_s:[],sensor_receipt_age_s:[],guard_receipt_age_s:[],ros_spin_s:[],
  approximate_source_age_at_callback_s:[],
  native_decode_s:[],native_frame_build_s:[],native_publication_lock_wait_s:[],native_publish_age_s:[]};
const native=[],sources={},sourceChunks={},nativeTimings=[];
native.reduceTotal=0;
let previousGeneration=null,previousNative=null;
for(const segment of receipt.segments){
 const file=path.join(dir,segment.path),bytes=fs.readFileSync(file);
 if(bytes.length!==segment.bytes||sha(bytes)!==segment.sha256)throw Error('ORIGINAL_SEGMENT_MISMATCH '+segment.path);
 result.files.push({file:segment.path,bytes:bytes.length,sha256:sha(bytes)});
 for await(const line of readline.createInterface({input:fs.createReadStream(file),crlfDelay:Infinity})){
  const e=JSON.parse(line),d=e.data??{},t=e.robot_monotonic_s;
  if(e.schema==='physical-live-pc-start-2.0')result.identity=e;
  if(Number.isFinite(t)){result.first_t??=t;result.last_t=t;}
  if(e.kind==='command'&&d.action!=='watch')result.commands.push({sequence:e.sequence,t,...d});
  if(e.kind==='fault')result.faults.push({sequence:e.sequence,t,...d});
  if(e.kind==='cleanup')result.cleanup.push({sequence:e.sequence,t,...d});
  if(e.kind==='raw'){
   const bytes=Buffer.from(d.base64,'base64');
   if(bytes.length!==d.length||sha(bytes)!==d.sha256)throw Error('RAW_CHUNK_MISMATCH '+e.sequence);
   if(d.source==='serialized_ros_message'){
    result.raw.ros_messages++;
    const topic=result.topics[d.topic]??={count:0,first_t:t,last_t:t,max_receipt_gap_s:0};
    if(topic.count)topic.max_receipt_gap_s=Math.max(topic.max_receipt_gap_s,t-topic.last_t);
    topic.count++;topic.last_t=t;
   }else{
    if(d.offset!==native.reduceTotal)throw Error('NATIVE_BYTE_ORDER '+e.sequence);
    native.push(bytes);native.reduceTotal+=bytes.length;result.raw.chunks++;
    nativeTimings.push({...d,base64:undefined});
   }
  }
  if(e.kind==='raw_source'){
   if(d.kind==='chunk'){
    if(!/^[A-Za-z0-9_.-]+$/.test(d.member))throw Error('SOURCE_MEMBER');
    const bytes=Buffer.from(d.base64,'base64');
    if(bytes.length!==d.length||sha(bytes)!==d.sha256)throw Error('SOURCE_CHUNK_MISMATCH');
    (sourceChunks[d.member]??=[]).push({offset:d.offset,bytes});
   }else if(d.kind==='manifest')Object.assign(sources,d);
  }
  if(e.kind==='heartbeat'){
   if(d.reason)result.reasons[d.reason]=(result.reasons[d.reason]??0)+1;
   const diagnostic=d.telemetry_diagnostic;
   if(diagnostic){
    result.diagnostic_reasons[diagnostic.reason]=(result.diagnostic_reasons[diagnostic.reason]??0)+1;
    for(const key of ['source_age_s','sensor_receipt_age_s','guard_receipt_age_s'])
     if(Number.isFinite(diagnostic[key]))metrics[key].push(diagnostic[key]);
    // Both ages refer to the same latest sensor in fresh(). Difference cancels
    // elapsed time after callback entry, assuming a stable ROS/monotonic rate.
    // It does NOT distinguish publisher delay from DDS or executor queueing.
    if(Number.isFinite(diagnostic.source_age_s)&&Number.isFinite(diagnostic.sensor_receipt_age_s))
     metrics.approximate_source_age_at_callback_s.push(diagnostic.source_age_s-diagnostic.sensor_receipt_age_s);
    if(diagnostic.reason==='SENSOR_SOURCE_AGE'&&!result.stale_diagnostic_example)
     result.stale_diagnostic_example={sequence:e.sequence,t,...diagnostic};
   }
   if(Number.isFinite(d.ros_spin_s))metrics.ros_spin_s.push(d.ros_spin_s);
   if(d.motion_generation!==previousGeneration){result.max_generation=Math.max(result.max_generation,d.motion_generation??0);previousGeneration=d.motion_generation;}
   const lidar=d.lidar??{};
   if(lidar.frame_count!==previousNative){
    previousNative=lidar.frame_count;
    for(const [input,key] of Object.entries({last_decode_s:'native_decode_s',last_frame_build_s:'native_frame_build_s',
        last_publication_lock_wait_s:'native_publication_lock_wait_s',last_frame_publish_age_s:'native_publish_age_s'}))
     if(Number.isFinite(lidar[input]))metrics[key].push(lidar[input]);
   }
   const tracking=d.field?.tracking;
   if(tracking?.reason)result.tracking_reasons[tracking.reason]=(result.tracking_reasons[tracking.reason]??0)+1;
  }
 }
}
function statistics(a){if(!a.length)return null;const s=[...a].sort((a,b)=>a-b);return{n:s.length,median_s:s[Math.floor(s.length*.5)],p95_s:s[Math.min(s.length-1,Math.ceil(s.length*.95)-1)],max_s:s.at(-1)};}
result.metrics=Object.fromEntries(Object.entries(metrics).map(([k,v])=>[k,statistics(v)]));
const bytes=Buffer.concat(native);result.raw.native_bytes=bytes.length;result.raw.native_sha256=sha(bytes);
fs.writeFileSync(path.join(output,'native-original.raw'),bytes);
fs.writeFileSync(path.join(output,'native-chunks.json'),JSON.stringify(nativeTimings));
result.sources=sources;result.source_files=[];
fs.mkdirSync(path.join(output,'robot-sources'),{recursive:true});
for(const member of sources.members??[]){
 if(member.status!=='COMPLETE')continue;
 const chunks=(sourceChunks[member.member]??[]).sort((a,b)=>a.offset-b.offset);let next=0;
 for(const c of chunks){if(c.offset!==next)throw Error('SOURCE_OFFSET');next+=c.bytes.length;}
 const b=Buffer.concat(chunks.map(c=>c.bytes));
 if(b.length!==member.source_size_bytes||sha(b)!==member.source_sha256)throw Error('SOURCE_DIGEST');
 fs.writeFileSync(path.join(output,'robot-sources',member.member),b);
 result.source_files.push({name:member.member,bytes:b.length,sha256:sha(b)});
}
result.elapsed_robot_s=result.last_t-result.first_t;
result.motion_publications=result.commands.filter(c=>c.status==='PUBLISHED');
result.wheel_tests={motion_publications:result.motion_publications.length,
 requested_actions:result.commands.map(c=>({action:c.action,status:c.status,reason:c.reason,trial:c.trial?.case})),
 limitation:'No motion publication does not prove physical immobility; classify trial/motion scopes separately.'};
result.metrics_limit='Heartbeat diagnostics can repeat a frozen last check. These aggregate statistics are not deduplicated source callbacks or continuous freshness proof; inspect original ROS receipt gaps and callback headers.';
result.voltage_problem='No evidence of low battery in source-age rejection example';
result.cost={provider_http:0,additional_usd:0,prior_approved_ledgers_unchanged:true};
fs.writeFileSync(path.join(output,'original-analysis.json'),JSON.stringify(result,null,2));
const actions=[];
for await(const line of readline.createInterface({input:fs.createReadStream(path.join(root,'recording-01','fleet-observations.jsonl')),crlfDelay:Infinity})){
 const value=JSON.parse(line);
 if(value.method==='POST'&&value.request?.action)actions.push({at:value.at,request:value.request,
   response_revision:value.response.revision,last_command:value.response.last_command});
}
const frames=JSON.parse(fs.readFileSync(path.join(root,'recording-01','frame-times.json'),'utf8'));
const disconnect=actions.findLast(x=>x.request.action==='disconnect');
const cleanupFrame=disconnect?frames.frames.find(x=>x.at>=disconnect.at+1500):null;
fs.writeFileSync(path.join(output,'actual-ui-actions.json'),JSON.stringify({actions,cleanup_frame:cleanupFrame,
  observer_note:'Derived from actual UI request bodies and response time; recorder stage labels do not establish completed robot execution.'},null,2));
console.log(JSON.stringify({files:result.files.length,events:receipt.event_count,bytes:receipt.bytes,complete:receipt.complete,
 raw:result.raw,topics:result.topics,diagnostic_reasons:result.diagnostic_reasons,metrics:result.metrics,
 motion_publications:result.motion_publications.length,sources:result.source_files.length,cleanup:result.cleanup.map(c=>({subsystem:c.subsystem,confirmed:c.confirmed,recording_complete:c.recording_complete}))},null,2));
