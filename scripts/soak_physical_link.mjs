// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
// Physical link soak over the Test-mode CDP endpoint of the installed App: select the registered physical robot,
// Connect, LiDAR on, sample the fleet snapshot the UI already polls (no API writes beyond the three visible clicks),
// then Disconnect and judge. PASS = 0 DEGRADED samples, 0 unexpected disconnects, scan rate >= 4.5 Hz, cleanup
// receipt confirmed on Disconnect. Run only with the operator present and the robot powered; nothing moves.
// usage: node scripts/soak_physical_link.mjs [minutes=10] [robot-label-prefix="Imported existing settings"] [out=outputs/soak/soak.json]
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const minutes=Number(process.argv[2]||10),prefix=process.argv[3]||'Imported existing settings',out=process.argv[4]||'outputs/soak/soak.json';
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222',{timeout:15000});
const page=browser.contexts().flatMap(c=>c.pages()).find(x=>/^http:\/\/127\.0\.0\.1:\d+\//.test(x.url()));
if(!page)throw new Error('TwinPulse page not found on the Test-mode CDP endpoint');
page.setDefaultTimeout(30000);
let fleet=null;
page.on('response',async r=>{if(r.url().endsWith('/v1/product/robot-fleet')){try{fleet=await r.json();}catch{}}});
const robot=()=>fleet?.robots?.find(r=>r.kind==='physical'&&r.label.startsWith(prefix));
const region=page.getByRole('region',{name:'Robot fleet',exact:true});
const waitFor=async(predicate,timeout,label)=>{const began=Date.now();while(Date.now()-began<timeout){if(predicate())return true;await page.waitForTimeout(500);}throw new Error('timeout waiting for '+label);};
await waitFor(()=>!!fleet,30000,'fleet snapshot');
if(!robot())throw new Error('no physical robot whose label starts with "'+prefix+'"');
const label=robot().label,control=page.getByRole('region',{name:'Control '+label,exact:true});
if(!(await control.count())){await region.getByRole('button',{name:new RegExp(label+' Physical')}).last().click();await page.waitForTimeout(1500);}
const log=[];const sample=(phase)=>{const r=robot();if(!r)return;log.push({t:Date.now(),phase,connection_state:r.connection_state,control_state:r.control_state,telemetry_age_ms:r.telemetry_age_ms,
  lidar_state:r.lidar_state,scan_frame:r.scan?.frame_sequence??null,scan_age_ms:r.scan_receipt?.age_ms??r.scan?.age_ms??null,voltage_v:r.battery?.voltage_v??null,
  link_detail:r.link_detail??null,transport_error:r.transport_error??null,remote_exit_code:r.remote_exit_code??null,reason:r.reason??null,cleanup_confirmed:r.cleanup_confirmed??null,live_heartbeat:r.live_heartbeat??null});};
sample('before_connect');
if(robot().connection_state!=='CONNECTED'){await control.getByRole('button',{name:'Connect',exact:true}).click();await waitFor(()=>robot()?.connection_state==='CONNECTED',120000,'CONNECTED');}
sample('connected');
const lidar=control.getByRole('button',{name:/^(Turn LiDAR on|LiDAR on)$/});if(await lidar.count()&&await lidar.first().isEnabled()){await lidar.first().click();await waitFor(()=>robot()?.lidar_state==='STREAMING',60000,'LiDAR STREAMING');}
sample('lidar_on');
const end=Date.now()+minutes*60000;
while(Date.now()<end){await page.waitForTimeout(1000);sample('soak');}
await control.getByRole('button',{name:'Disconnect',exact:true}).click();
await waitFor(()=>robot()?.connection_state==='DISCONNECTED',60000,'DISCONNECTED').catch(()=>{});await page.waitForTimeout(3000);sample('after_disconnect');
// judgement
const soak=log.filter(s=>s.phase==='soak');
const degraded=soak.filter(s=>s.connection_state==='DEGRADED').length,disconnects=soak.filter(s=>s.connection_state==='DISCONNECTED').length;
const frames=soak.filter(s=>typeof s.scan_frame==='number');
const scanRate=frames.length>1?(frames.at(-1).scan_frame-frames[0].scan_frame)/((frames.at(-1).t-frames[0].t)/1000):null;
const last=log.at(-1),cleanup=last?.cleanup_confirmed===true;
const voltages=soak.map(s=>s.voltage_v).filter(v=>typeof v==='number');
const verdict={minutes,samples:soak.length,degraded_samples:degraded,disconnect_samples:disconnects,scan_rate_hz:scanRate===null?null:Number(scanRate.toFixed(2)),
  cleanup_confirmed_on_disconnect:cleanup,voltage_first:voltages[0]??null,voltage_last:voltages.at(-1)??null,max_telemetry_age_ms:Math.max(0,...soak.map(s=>s.telemetry_age_ms??0)),
  pass:degraded===0&&disconnects===0&&scanRate!==null&&scanRate>=4.5&&cleanup,
  reasons:[degraded&&`${degraded} DEGRADED samples`,disconnects&&`${disconnects} DISCONNECTED samples`,scanRate===null?'scan frame counter not in snapshot':scanRate<4.5&&`scan rate ${scanRate.toFixed(2)} Hz < 4.5`,!cleanup&&'cleanup not confirmed on Disconnect'].filter(Boolean)};
fs.mkdirSync(path.dirname(out),{recursive:true});fs.writeFileSync(out,JSON.stringify({verdict,samples:log},null,1));
console.log((verdict.pass?'PASS':'FAIL')+' '+JSON.stringify(verdict));await browser.close();
