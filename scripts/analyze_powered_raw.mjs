// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Offline, read-only analysis of recorded robot events. No device connection.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
const directory=process.argv[2];
const topics={},kinds={},reasons={},commands=[],faults=[],states=[];
let previousState='',lines=0,bad=0;
for(const name of fs.readdirSync(directory).filter(n=>/^events-\d+\.jsonl$/.test(n)).sort()) {
 for await(const line of readline.createInterface({input:fs.createReadStream(path.join(directory,name)),crlfDelay:Infinity})) {
  let event;try{event=JSON.parse(line);}catch{bad++;continue;}lines++;
  const {kind,data:d={},robot_monotonic_s:t}=event;kinds[kind]=(kinds[kind]??0)+1;
  if(kind==='raw'&&d.source==='serialized_ros_message') {
   const s=topics[d.topic]??={count:0,first:t,last:t,max_receipt_gap_s:0,source_stamp_first:null,source_stamp_last:null};
   if(s.count)s.max_receipt_gap_s=Math.max(s.max_receipt_gap_s,t-s.last);
   s.count++;s.last=t;
   if(d.topic==='sensor_state'||d.topic==='odom') {
    const bytes=Buffer.from(d.base64,'base64');
    if(bytes.length>=12) {const stamp=bytes.readInt32LE(4)+bytes.readUInt32LE(8)/1e9;
     s.source_stamp_first??=stamp;s.source_stamp_last=stamp;
     const lag=t-s.first-(stamp-s.source_stamp_first);s.max_relative_backlog_s=Math.max(s.max_relative_backlog_s??0,lag);
    }
   }
  }
  if(kind==='command'&&d.action!=='watch')commands.push({t,...d});
  if(kind==='fault'&&faults.length<80)faults.push({t,...d});
  if(kind==='heartbeat') {
   if(d.reason)reasons[d.reason]=(reasons[d.reason]??0)+1;
   const key=JSON.stringify([d.control_state,d.reason,d.battery?.sample_monotonic_s]);
   if(key!==previousState) {states.push({t,state:d.control_state,reason:d.reason,battery:d.battery});previousState=key;}
  }
 }
}
console.log(JSON.stringify({directory,lines,bad,kinds,topics,reasons,commands,faults:faults.slice(0,5),states:states.slice(-5)},null,2));
