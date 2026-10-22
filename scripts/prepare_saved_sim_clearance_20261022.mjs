// SPDX-License-Identifier: Apache-2.0
// Explicit, recorded SIM-only UI preparation. Never a hidden pose reset or an
// original48 PASS. Product navigation and manual guards are unchanged.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {recordStopReceipt} from './control_stop_receipt.mjs';
const args=process.argv.slice(2),arg=n=>{const index=args.indexOf(n),value=index<0?undefined:args[index+1];return value?.startsWith('--')?undefined:value;};
const output=arg('--output'),endpoint=arg('--cdp'),expectedSource=arg('--expected-source');
if(!output||!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint)||!/^[a-f0-9]{64}$/.test(expectedSource??''))throw Error('Explicit existing test launch, exact source SHA and new output required');
await fs.mkdir(output,{recursive:false});
const source=fileURLToPath(new URL('../outputs/robot-continuous-repair-20261021/navigation48-original-project.json',import.meta.url));
const raw=await fs.readFile(source),project=JSON.parse(raw.toString('utf8').replace(/^\uFEFF/,''));
const scene=project.site_draft.site.scene,expected=scene.revision;
if(createHash('sha256').update(raw).digest('hex')!=='c7efadb7929698e9c753164dea987c36f5d0398217aab2d6e7ba9612794ca061'||
 project.project_id!=='chat_mvh8rm7k_4dafa4c1'||expected!=='37ba75c8f38889ac556d49af289203e42e3376a2c6822be8cf31ecf93459453e')throw Error('Original48 immutable source identity mismatch');
const result={classification:'EXPLICIT_SIM_UI_CLEARANCE_PREPARATION_NOT_ORIGINAL48_REPLAY_OR_ACCEPTANCE',status:'IN_PROGRESS',
 original48_status:'FAIL_PRESERVED',source:{path:source,sha256:createHash('sha256').update(raw).digest('hex')},
 project:project.project_id,scene_revision:expected,physical:'OFF_NOT_RUN',no_request_interception:true,
 requests:[],samples:[],commands:[],steps:[]};
const boxes=[],floors=[];
for(const row of scene.objects){
 if(row.shape.type!=='box'||row.transform.rotation_rpy_deg.some(n=>n!==0))throw Error('Unsupported reconstructed geometry; no guessed conversion');
 const [x,y,z]=row.transform.position_m,[w,d,h]=row.shape.dimensions_m,b=[x-w/2,y-d/2,x+w/2,y+d/2];
 if(z+h/2<=.08&&w>1&&d>1)floors.push(b);
 if(z-h/2<=.18&&z+h/2>.08)boxes.push({id:row.id,bounds:b});
}
const floor=floors.sort((a,b)=>(b[2]-b[0])*(b[3]-b[1])-(a[2]-a[0])*(a[3]-a[1]))[0];
if(!floor)throw Error('No original floor');
const gap=(p,b)=>Math.hypot(Math.max(b[0]-p[0],0,p[0]-b[2]),Math.max(b[1]-p[1],0,p[1]-b[3]));
const angle=n=>Math.atan2(Math.sin(n),Math.cos(n));
let page,browser,finishRecording,conversation,fleet;
let journeySucceeded=false;
const fleets=new Map(),pending=[];
const requestMetadata=new WeakMap();
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(fn,ms=15000)=>{const end=Date.now()+ms;while(Date.now()<end){if(fn())return;await sleep(100);}throw Error('Explicit preparation condition timed out');};
const robot=name=>fleet?.robots.find(r=>r.kind==='sim'&&r.label===name);
const drawer=name=>page.getByRole('region',{name:'Control '+name,exact:true});
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const stop=async(name='Alpha')=>{
 const before=structuredClone(robot(name)),index=result.requests.length;
 await drawer(name).getByRole('button',{name:'Stop',exact:true}).click();
 await poll(()=>result.requests.slice(index).some(r=>r.action==='stop'&&r.robot_id===before.robot_id));
 const request=result.requests.slice(index).find(r=>r.action==='stop'&&r.robot_id===before.robot_id);
 await poll(()=>{
  if(request.status&&request.status!==200)throw Error('Stop HTTP '+request.status);
  const current=robot(name),ack=request.result_robots?.find(r=>r.robot_id===before.robot_id);
  return request.status===200&&ack&&ack.operation_id===before.operation_id&&ack.connection_epoch===before.connection_epoch&&
   ack.motion_epoch!==before.motion_epoch&&current.motion_epoch===ack.motion_epoch&&
   current.applied_motion_epoch===ack.motion_epoch&&current.control_state==='PAUSED';
 });
 result.steps.push({name:'Explicit Stop '+name,before,request_id:request.request_id,after:structuredClone(robot(name))});
};
async function command(text){
 const before=structuredClone(robot('Alpha')),index=result.requests.length;
 await drawer('Alpha').getByRole('textbox',{name:'Robot command',exact:true}).fill(text);await sleep(3000);
 await drawer('Alpha').getByRole('button',{name:'Send command',exact:true}).click();
 await poll(()=>result.requests.slice(index).some(r=>r.action==='command'&&r.payload?.text===text));
 const request=result.requests.slice(index).find(r=>r.action==='command'&&r.payload?.text===text),id=request.request_id;
 if(request.robot_id!==before.robot_id||request.connection_epoch!==before.connection_epoch||request.motion_epoch!==before.motion_epoch||request.operation_id!==before.operation_id)throw Error('Outbound command context mismatch');
 await poll(()=>{
  if(request.status&&request.status!==200)throw Error('Command HTTP '+request.status);
  const r=robot('Alpha');if(r.command?.request_id!==id)return false;
  if(r.operation_id!==before.operation_id||r.connection_epoch!==before.connection_epoch||r.source_twin_context.context_id!==before.source_twin_context.context_id)throw Error('Preparation command context replaced');
  if(['FAILED','CANCELLED'].includes(r.command.state))throw Error('Preparation command rejected: '+r.command.reason);
  const ack=request.command_ack;
  // Acceptance ACK describes the execution epoch. TASK_COMPLETED deliberately
  // pauses into a NEW epoch; require that terminal epoch's later engine ACK,
  // not impossible equality to the original command acceptance snapshot.
  return request.status===200&&ack?.command?.request_id===id&&ack.operation_id===before.operation_id&&
   ack.connection_epoch===before.connection_epoch&&ack.motion_epoch===request.motion_epoch&&
   r.motion_epoch!==ack.motion_epoch&&r.motion_epoch===r.applied_motion_epoch&&r.command.state==='COMPLETED'&&
   r.reason==='TASK_COMPLETED'&&r.control_state==='PAUSED';
 },30000);
 result.commands.push({text,request_id:id,before,completed:structuredClone(robot('Alpha'))});await stop();await save();
}
try{
 browser=await chromium.connectOverCDP(endpoint,{timeout:10000});
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One actual installed BrowserWindow required');[page]=pages;page.setDefaultTimeout(10000);
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 const activePath=path.join(process.env.LOCALAPPDATA,'TwinPulse/installed/active-release.json');
 const activeRaw=await fs.readFile(activePath),active=JSON.parse(activeRaw);
 result.installation={...active,active_record_sha256:createHash('sha256').update(activeRaw).digest('hex')};
 if(active.source_manifest_sha256!==expectedSource||
    result.desktop?.engine?.release_id!==active.release_id||!result.desktop.engine.launch_id)throw Error('Explicit frozen installed source required');
 finishRecording=await recordRenderedPage(page,path.join(output,'recording'));
 page.on('request',r=>{if(new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.method()==='POST'){
  const b=r.postDataJSON(),meta={at:Date.now(),action:b.action,request_id:b.request_id,robot_id:b.robot_id,
   connection_epoch:b.connection_epoch,motion_epoch:b.motion_epoch,payload:b.payload,
   operation_id:fleet?.robots.find(v=>v.robot_id===b.robot_id)?.operation_id};
  requestMetadata.set(r,meta);result.requests.push(meta);
 }});
 page.on('response',response=>pending.push((async()=>{
  const p=new URL(response.url()).pathname,context=response.headers()['x-twinpulse-context'];
  if(!['/v1/product/conversation','/v1/product/robot-fleet'].includes(p))return;
  if(response.status()>=400)throw Error('Actual preparation HTTP '+response.status());
  const body=await response.json(),meta=requestMetadata.get(response.request());
  if(meta){meta.status=response.status();meta.response_at=Date.now();recordStopReceipt(meta,body);
   if(meta.action==='command')meta.command_ack=body.robots.find(r=>r.robot_id===meta.robot_id);}
  if(p.endsWith('/conversation')){conversation={project_id:body.project_id,context};fleet=fleets.get(context);}
  else{const old=fleets.get(context);if(!old||body.revision>=old.revision)fleets.set(context,body);
   if(context===conversation?.context)fleet=fleets.get(context);
   if(context===conversation?.context)result.samples.push({at:Date.now(),revision:body.revision,robots:body.robots.map(r=>({...r,scan:r.scan?{source:r.scan.source,count:r.scan.points.length}:null}))});
  }
 })().catch(e=>{result.listener_error=String(e);}))); // preserved, sticky, final veto
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 if(!await page.locator('.chat-sidebar-slot').isVisible())await page.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
 await page.getByRole('button',{name:'Open '+project.project_id,exact:true}).click();
 await poll(()=>conversation?.project_id===project.project_id&&robot('Alpha')&&robot('Beta'));
 if(fleet.robots.some(r=>r.connection_state==='CONNECTED'))throw Error('Unexpected restored authority');
 const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
 await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
 await page.getByRole('button',{name:'View current Twin',exact:true}).click();
 await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
 for(const name of ['Alpha','Beta']){
  await page.locator('.robot-fleet-row').filter({hasText:name}).click();await expect(drawer(name)).toBeVisible();
  await drawer(name).getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot(name)?.connection_state==='CONNECTED');
  await drawer(name).getByRole('button',{name:'Prepare',exact:true}).click();
  if(robot(name)?.lidar_state!=='STREAMING')await drawer(name).getByRole('button',{name:'Turn LiDAR on',exact:true}).click();
  await poll(()=>robot(name)?.lidar_state==='STREAMING');
  if(robot(name).source_twin_context?.scene_revision!==expected)throw Error('Original geometry not actually displayed');
 }
 await page.locator('.robot-fleet-row').filter({hasText:'Alpha'}).click();await poll(()=>fleet.focused_robot_id===robot('Alpha').robot_id);
 const original=structuredClone(robot('Alpha')),start=original.pose.position_m;
 const discs=fleet.robots.filter(r=>r.kind==='sim'&&r.robot_id!==original.robot_id).map(r=>r.pose.position_m);
 const distance=p=>Math.min(...boxes.map(b=>gap(p,b.bounds)),...discs.map(d=>Math.hypot(p[0]-d[0],p[1]-d[1])-.105),p[0]-floor[0],p[1]-floor[1],floor[2]-p[0],floor[3]-p[1]);
 const originalGap=distance(start);if(!(originalGap>.2075))throw Error('Current manual envelope not established');
 // One bounded plan, not an iterative correction loop. 5mm sampled checks
 // cover all boxes, other robots and original floor. These are not a proof of
 // continuous clearance or physical collision safety; product guards still run.
 const candidates=[];
 for(let k=0;k<72;k++){
  const heading=k*Math.PI/36,length=.35,points=Array.from({length:71},(_,i)=>[start[0]+Math.cos(heading)*length*i/70,start[1]+Math.sin(heading)*length*i/70]);
  const minimum=Math.min(...points.map(distance)),end=points.at(-1),endGap=distance(end);
  if(minimum>=originalGap-1e-10&&endGap>.45)candidates.push({heading,length,end,endGap,minimum,turn:angle(heading-start[2])});
 }
 candidates.sort((a,b)=>Math.abs(a.turn)-Math.abs(b.turn)||b.endGap-a.endGap);
 if(!candidates.length)throw Error('No one-shot conservative manual preparation; do not relax or retry');
 const plan=candidates[0];result.preparation={original,original_gap_m:originalGap,all_static_boxes:boxes,other_robot_positions:discs,floor,plan,
  policy:'Same original manual envelope; 5mm samples never below initial minimum clearance, not continuous swept proof. Final >.45m gives room for subsequent normal small UI gestures. No navigation clearance/pose injection.'};await save();
 if(Math.abs(plan.turn)>.001)await command('Turn '+(plan.turn>0?'left ':'right ')+Math.abs(plan.turn).toFixed(8)+' radians');
 const oriented=robot('Alpha').pose.position_m;
 if(Math.abs(angle(oriented[2]-plan.heading))>.01||Math.hypot(oriented[0]-start[0],oriented[1]-start[1])>.001)throw Error('Measured rotation does not match the checked segment');
 await command('Move forward 35 cm');
 const after=structuredClone(robot('Alpha'));
 if(after.operation_id!==original.operation_id||after.connection_epoch!==original.connection_epoch||distance(after.pose.position_m)<=.45||
    Math.hypot(after.pose.position_m[0]-plan.end[0],after.pose.position_m[1]-plan.end[1])>.016)throw Error('Prepared current measured pose did not meet unchanged clearance');
 result.preparation.after=after;result.preparation.measured_final_clearance_m=distance(after.pose.position_m);
 await page.screenshot({path:path.join(output,'clearance-prepared.png')});
 for(const name of ['Alpha','Beta']){
  await page.locator('.robot-fleet-row').filter({hasText:name}).click();
  await stop(name);
  await drawer(name).getByRole('button',{name:'Disconnect',exact:true}).click();await poll(()=>robot(name)?.connection_state==='DISCONNECTED');
 }
 if(result.listener_error)throw Error(result.listener_error);
 result.status='PREPARATION_MEASURED_PENDING_RECORDING_AND_SHUTDOWN';await save();
 await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();
 journeySucceeded=true;
}catch(e){result.status='FAIL';result.error=String(e);}
finally{
 if(page&&!page.isClosed()&&!journeySucceeded){
  result.failure_cleanup=[];page.setDefaultTimeout(3000);
  for(const name of ['Alpha','Beta']){
   const owned=robot(name);if(!owned||(!owned.connection_epoch&&!owned.operation_id))continue;
   try{await page.locator('.robot-fleet-row').filter({hasText:name}).click();await stop(name);result.failure_cleanup.push({name,stop:'CONFIRMED'});}
   catch(e){result.failure_cleanup.push({name,stop:'UNCONFIRMED',error:String(e)});}
   try{await drawer(name).getByRole('button',{name:'Disconnect',exact:true}).click();await poll(()=>robot(name)?.connection_state==='DISCONNECTED',5000);result.failure_cleanup.push({name,disconnect:'CONFIRMED'});}
   catch(e){result.failure_cleanup.push({name,disconnect:'UNCONFIRMED',error:String(e)});}
  }
  try{await page.screenshot({path:path.join(output,'failure-after-stop.png'),timeout:3000});}
  catch(e){result.failure_cleanup.push({screenshot:'UNCONFIRMED',error:String(e)});}
  try{await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();result.failure_cleanup.push({exit:'REQUESTED_NOT_ROOT_PROOF'});}
  catch(e){result.failure_cleanup.push({exit:'UNCONFIRMED',error:String(e)});}
 }
 result.finalization_errors=[];
 try{await Promise.all(pending);}catch(e){result.finalization_errors.push({phase:'pending',error:String(e)});}
 if(result.listener_error)result.finalization_errors.push({phase:'listener',error:result.listener_error});
 if(finishRecording)try{result.recording=await finishRecording();}catch(e){result.finalization_errors.push({phase:'recording',error:String(e)});}
 try{await browser?.close();}catch(e){result.finalization_errors.push({phase:'browser_detach',error:String(e)});}
 result.status=journeySucceeded&&!result.finalization_errors.length?'PASS_EXPLICIT_PREPARATION_ONLY':'FAIL';
 try{await save();}catch(e){result.status='FAIL';result.finalization_errors.push({phase:'result_storage',error:String(e)});}
}
console.log(JSON.stringify({status:result.status,error:result.error,preparation:result.preparation&&{plan:result.preparation.plan,measured_final_clearance_m:result.preparation.measured_final_clearance_m}}));
if(result.status!=='PASS_EXPLICIT_PREPARATION_ONLY')process.exitCode=1;
