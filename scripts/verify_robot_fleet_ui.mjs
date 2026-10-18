// SPDX-License-Identifier: Apache-2.0
// Actual installed Electron UI only: no product mutation API, seeding or mocks.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1];
const out=arg('--output'),endpoint=arg('--cdp'),phase=arg('--phase')??'fresh';
if(!out||!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint))throw Error('Explicit CDP/output required');
await fs.mkdir(out,{recursive:false});
const result={phase,status:'IN_PROGRESS',steps:[],errors:[],http_errors:[],request_failures:[],network_failures:[],fault_rejections:[],stop_fence_rejections:[],fleet_requests:[],expected_rejections:[],samples:[],screenshots:[],native_os_input:'NOT_RUN',physical:'OFF_CHARGING_NOT_RUN'};
const faultRequests=new WeakMap(),requestMeta=new WeakMap(),responseChecks=[];let observedOrder=0;
let browser,page,fleet=null,conversation=null,expectInvalidProfile=false,exiting=false,activeStep='HARNESS_ATTACH',fleetRouteHandler=null;const fleetsByContext=new Map();
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await page.screenshot({path:path.join(out,name+'.png'),timeout:5000});result.screenshots.push(name+'.png');};
const clean=e=>String(e).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]').slice(0,2000);
const step=async(name,fn)=>{activeStep=name;const start=Date.now();try{const evidence=await fn();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-start,evidence});}
 catch(e){result.steps.push({name,status:'FAIL',elapsed_ms:Date.now()-start,error:clean(e)});await shot('failure-'+result.steps.length).catch(()=>{});throw e;}finally{await save();}};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(predicate,ms=15000)=>{const end=Date.now()+ms;while(Date.now()<end){if(predicate())return;await sleep(100);}throw Error('Observed state did not meet condition');};
const sims=()=>fleet?.robots.filter(r=>r.kind==='sim')??[];
const robot=name=>sims().find(r=>r.label===name);
const drawer=name=>page.getByRole('region',{name:'Control '+name,exact:true});
const padBox=async(name,direction)=>{const button=drawer(name).getByRole('button',{name:'Hold '+direction,exact:true});
 await button.scrollIntoViewIfNeeded();await expect(button).toBeEnabled();const box=await button.boundingBox();
 const size=page.viewportSize();if(!box||size&&(box.y+box.height/2<0||box.y+box.height/2>size.height))throw Error('Drive button not in visible viewport');return box;};
const focusPad=async name=>{const pad=drawer(name).getByRole('group',{name:'Hold to drive',exact:true});
 // The upper-left grid cell is visibly empty (forward occupies column 2).
 // A real click there focuses the group without starting a direction/Stop.
 await pad.click({position:{x:4,y:4}});
 if(!await pad.evaluate(el=>el===document.activeElement))throw Error('Keyboard did not focus the drive pad');};
const stopped=()=>robot('Alpha')?.control_state==='PAUSED'&&robot('Alpha')?.motion_epoch===robot('Alpha')?.applied_motion_epoch;
const checkedTravel=(before,after,direction)=>{const p=before.pose.position_m,q=after.pose.position_m;
 if(['forward','backward'].includes(direction)&&Math.hypot(q[0]-p[0],q[1]-p[1])<.01)throw Error(direction+' did not move');
 const yaw=Math.atan2(Math.sin(q[2]-p[2]),Math.cos(q[2]-p[2]));
 if(direction==='left'&&yaw<.1||direction==='right'&&yaw>-.1)throw Error(direction+' rotation wrong/missing');};
const select=async name=>{await page.locator('.robot-fleet-row').filter({hasText:name}).click();await expect(drawer(name)).toBeVisible();};
const sendChat=async text=>{await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
try{
 browser=await chromium.connectOverCDP(endpoint,{timeout:10000});
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');[page]=pages;page.setDefaultTimeout(10000);
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 if(!result.desktop?.engine?.launch_id)throw Error('Installed desktop identity missing');
 const network=await page.context().newCDPSession(page),networkRequests=new Map();
 network.on('Network.requestWillBeSent',e=>{const pathname=new URL(e.request.url).pathname;if(pathname.startsWith('/v1/product/'))networkRequests.set(e.requestId,{path:pathname,method:e.request.method,at:Date.now(),step:activeStep});});
 network.on('Network.loadingFailed',e=>{const request=networkRequests.get(e.requestId);if(request)result.network_failures.push({...request,failed_at:Date.now(),failed_step:activeStep,error:e.errorText,canceled:e.canceled,blocked_reason:e.blockedReason,cors:e.corsErrorStatus});});
 await network.send('Network.enable');
 page.on('request',r=>{if(new URL(r.url()).pathname!=='/v1/product/robot-fleet'||r.method()!=='POST')return;
  let body;try{body=r.postDataJSON();}catch{return;}
  const meta={order:++observedOrder,at:Date.now(),action:body?.action,request_id:body?.request_id,robot_id:body?.robot_id,
   connection_epoch:body?.connection_epoch,motion_epoch:body?.motion_epoch,operation_id:fleet?.robots.find(v=>v.robot_id===body?.robot_id)?.operation_id,
   sequence:body?.payload?.sequence,expires_at_ms:body?.payload?.expires_at_ms};
  requestMeta.set(r,meta);result.fleet_requests.push(meta);});
 page.on('pageerror',e=>result.errors.push(clean(e)));
 page.on('requestfailed',r=>{let body;try{body=r.postDataJSON();}catch{}
  const pathname=new URL(r.url()).pathname;if(pathname.startsWith('/v1/product/'))result.request_failures.push({path:pathname,method:r.method(),action:body?.action,request_id:body?.request_id,error:r.failure()?.errorText,at:Date.now(),step:activeStep,context:r.headers()['x-twinpulse-context'],current_context:conversation?.context,exiting,fault:faultRequests.get(r)});
 });
 page.on('response',r=>{const meta=requestMeta.get(r.request());if(meta){meta.response_order=++observedOrder;meta.response_at=Date.now();meta.status=r.status();}
  responseChecks.push((async()=>{const p=new URL(r.url()).pathname;if(r.status()>=400){
    let payload=null,body=null;try{payload=await r.json();}catch{}try{body=r.request().postDataJSON();}catch{}
    const fault=faultRequests.get(r.request());const code=payload?.code??payload?.error?.code;
    const row={path:p,status:r.status(),method:r.request().method(),action:body?.action,request_id:body?.request_id,
     code,message:payload?.message??payload?.error?.message,fault};
    if(fault&&p==='/v1/product/robot-fleet'&&r.status()===409&&body?.action==='drive'&&['fleet_input_expired','fleet_motion_changed','fleet_sequence'].includes(code))result.fault_rejections.push(row);
    else if(expectInvalidProfile&&p==='/v1/product/robot-fleet'&&body?.action==='profile'&&r.status()===400&&code==='physical_profile_invalid')result.expected_rejections.push(row);
    else result.http_errors.push(row);
   }
   const context=r.headers()['x-twinpulse-context']??'';
   if(p==='/v1/product/conversation'&&r.status()===200)try{const incoming=await r.json();conversation={project_id:incoming.project_id,session_id:incoming.session_id,context};
     fleet=fleetsByContext.get(context)??null;result.conversation=conversation;}catch{}
   if(p==='/v1/product/robot-fleet'&&r.status()===200)try{const incoming=await r.json(),previous=fleetsByContext.get(context);const old=previous&&incoming.revision<previous.revision;
     if(meta?.action==='stop'){meta.result_revision=incoming.revision;meta.result_robots=incoming.robots.map(v=>({robot_id:v.robot_id,
      operation_id:v.operation_id,connection_epoch:v.connection_epoch,motion_epoch:v.motion_epoch,applied_motion_epoch:v.applied_motion_epoch,control_state:v.control_state}));}
     if(!old)fleetsByContext.set(context,incoming);if(context===conversation?.context)fleet=fleetsByContext.get(context);result.samples.push({at:Date.now(),context,observation_order:++observedOrder,revision:incoming.revision,observer_rejected_old_revision:!!old,
     focused:incoming.focused_robot_id,robots:incoming.robots.map(v=>({...v,scan:v.scan?{source:v.scan.source,count:v.scan.points.length}:null}))});
     // Preserve the original early Stop/applied-epoch evidence through the
     // final assertion. Never silently evict it during the 60-second soak.
     if(result.samples.length>5000){result.errors.push('Telemetry evidence capacity exceeded; original early receipts preserved');result.samples.pop();}}catch{}})());});
 // Keep interception installed for this whole test window. Repeatedly
 // enabling/disabling Chromium interception in a live polling renderer is a
 // harness confounder; only delay configuration changes during fault tests.
 await page.route('**/v1/product/robot-fleet',request=>fleetRouteHandler?fleetRouteHandler(request):request.continue());
 await step('Visible Isaac startup readiness before scene operations',async()=>{
  await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
  await shot('startup-ready');return {criterion:'UI current authenticated engine connection; startup waiting is measured, not immediate readiness'};});
 await step('Robots menu PC preparation and connection entry while hardware stays OFF',async()=>{
  await page.getByRole('button',{name:'Robots',exact:true}).click();const panel=page.getByRole('dialog');
  await expect(panel.getByRole('heading',{name:'Registered robots',exact:true})).toBeVisible();
  const active=panel.getByRole('combobox',{name:'Active robot',exact:true});
  if(!await active.inputValue())throw Error('A real saved robot must already be selected; no fake registration');
  const prepare=panel.getByRole('button',{name:'Check PC preparation',exact:true});await expect(prepare).toBeEnabled();await prepare.click();
  const checks=panel.getByRole('region',{name:'PC connection preparation',exact:true});
  await expect(checks.getByText('PC prerequisites found · robot connection not checked',{exact:true})).toBeVisible({timeout:20000});
  await expect(panel.getByRole('button',{name:'Check connection (read-only)',exact:true})).toBeEnabled();
  await expect(panel.getByText('Read-only robot mode:',{exact:false})).toHaveCount(0);
  await shot('robot-pc-prepared');const evidence={pc_preparation:await checks.innerText(),connection_requested:false};
  await panel.getByRole('button',{name:/^Close/}).click();return evidence;
 });
 if(['physical-only','controls-only','controls-tail'].includes(phase))result.project=arg('--project');
 if(phase==='fresh'){
  await step('Visible New chat and original robot-containing scene brief',async()=>{
   const home=page.getByRole('button',{name:'＋ Start a new chat',exact:true});
   if(await home.isVisible())await home.click();else await page.getByRole('button',{name:'＋ New chat',exact:true}).click();
   result.project=(await page.getByRole('banner').innerText()).match(/chat_[a-zA-Z0-9_]+/)?.[0];
   const text='6m x 5m 크기의 추정 방을 만들어줘. 뒤쪽 벽 근처 왼쪽에 침대 1개, 오른쪽에 책상 1개와 의자 1개를 놓고, 가운데와 앞쪽 바닥은 로봇 2대의 저속 시뮬레이션을 위해 넓게 비워줘. 치수는 추정이라고 표시해줘.';
   result.input_sha256=createHash('sha256').update(text).digest('hex');
   await sendChat(text);
   const mode=page.getByRole('radio',{name:'Simulation only',exact:true});
   await expect(page.getByRole('button',{name:'Create Twin',exact:true}).or(mode)).toBeVisible({timeout:15000});
   if(await mode.isVisible())await mode.check();
   await expect(page.getByRole('button',{name:'Create Twin',exact:true})).toBeVisible();
   result.project=(await page.getByRole('banner').innerText()).match(/chat_[a-zA-Z0-9_]+/)?.[0];
   await page.getByRole('button',{name:'Create Twin',exact:true}).click();return {text};});
  await step('Real provider generation and current Isaac frame',async()=>{
   const end=Date.now()+240000;let index=0;
   while(Date.now()<end){
    if(await page.getByText('Your environment Twin is saved without a SIM robot or automatic route.',{exact:false}).count())break;
    await shot('generation-'+index++);await save();await sleep(5000);
   }
   await expect(page.getByText('Your environment Twin is saved without a SIM robot or automatic route.',{exact:false})).toBeVisible();
   await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible();
   await shot('generated');return {display:'actual Isaac',photo_quality:'NOT_APPLICABLE_TEXT',physics:'kinematic only'};});
  await step('Register two robots through Manage form',async()=>{
   await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
   await page.getByText('Add SIM robot',{exact:true}).click();
   for(const [name,x] of [['Alpha','1'],['Beta','2']]){
    await page.getByRole('textbox',{name:'Name',exact:true}).fill(name);
    await page.getByRole('spinbutton',{name:'X (m)',exact:true}).fill(x);
    await page.getByRole('spinbutton',{name:'Y (m)',exact:true}).fill('1');
    await page.getByRole('button',{name:'Add SIM robot',exact:true}).click();await poll(()=>!!robot(name));
   }
   await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();return sims();});
 }
 if(phase==='reopen'){
  await step('Open saved conversation from visible sidebar',async()=>{
   result.project=arg('--project');
   await page.getByRole('button',{name:'Open '+arg('--project'),exact:true}).click();
   await poll(()=>sims().length===2);return sims();});
  await step('Cold restore preserves definitions but no motion authority',async()=>{
   if(sims().some(r=>r.connection_state!=='DISCONNECTED'||r.operation_id||r.motion_epoch))throw Error('Restored authority');
   await shot('cold-restored');return sims();});
  await step('Historical operation reopened and downloaded without reconnecting',async()=>{
   await select('Alpha');const prior=robot('Alpha').last_operation_id;
   if(!prior)throw Error('Historical operation ID missing');
   await drawer('Alpha').getByRole('button',{name:'Operation logs',exact:true}).click();
   await expect(drawer('Alpha').getByRole('button',{name:'Download operation JSON',exact:true})).toBeVisible();
   const pending=page.waitForEvent('download');await drawer('Alpha').getByRole('button',{name:'Download operation JSON',exact:true}).click();
   await (await pending).saveAs(path.join(out,'cold-operation.json'));const record=JSON.parse(await fs.readFile(path.join(out,'cold-operation.json'),'utf8'));
   if(record.operation_id!==prior||!record.manifest.complete||!record.manifest.journal?.complete)throw Error('Finalized historical journal missing');
   if(robot('Alpha').connection_state!=='DISCONNECTED'||robot('Alpha').operation_id)throw Error('Log lookup restored connection');
   await shot('historical-operation');await drawer('Alpha').getByRole('button',{name:'Close robot controls',exact:true}).click();return {operation_id:prior,manifest:record.manifest};});
  await step('Explicitly display saved Twin in current Isaac; no automatic motion restore',async()=>{
   const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});
   if(await reopen.isVisible())await reopen.click();
   await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
   await page.getByRole('button',{name:'View current Twin',exact:true}).click();
   await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
   await shot('saved-twin-current');return {source:'visible View current Twin button',motion_restored:false};});
  await step('Cold new explicit SIM connection; actual backward and right pad buttons',async()=>{
   await select('Alpha');await drawer('Alpha').getByRole('button',{name:'Connect',exact:true}).click();
   await poll(()=>robot('Alpha')?.connection_state==='CONNECTED');
   await drawer('Alpha').getByRole('button',{name:'Prepare',exact:true}).click();
   const moves=[];
   for(const direction of ['backward','right']){
    const before=structuredClone(robot('Alpha'));
    const box=await padBox('Alpha',direction);
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await sleep(1600);await page.mouse.up();
    await poll(()=>robot('Alpha')?.control_state==='PAUSED'&&robot('Alpha')?.motion_epoch===robot('Alpha')?.applied_motion_epoch);
    const after=structuredClone(robot('Alpha')),p=before.pose.position_m,q=after.pose.position_m;
    if(direction==='backward'&&Math.hypot(q[0]-p[0],q[1]-p[1])<.03)throw Error('Backward pad produced no measured travel');
    if(direction==='right'&&Math.atan2(Math.sin(q[2]-p[2]),Math.cos(q[2]-p[2]))>-.1)throw Error('Right pad produced no measured clockwise rotation');
    if(robot('Beta')?.connection_state!=='DISCONNECTED')throw Error('Other robot reconnected automatically');
    moves.push({direction,before,after});
   }
   await shot('cold-backward-right');await drawer('Alpha').getByRole('button',{name:'Disconnect',exact:true}).click();
   await poll(()=>robot('Alpha')?.connection_state==='DISCONNECTED');
   await drawer('Alpha').getByRole('button',{name:'Close robot controls',exact:true}).click();return {moves};
  });
 }else if(['fresh','controls-only','controls-tail'].includes(phase)){
  if(phase==='controls-tail')await select('Alpha');
  else{
  await step('Two simultaneous real Isaac SIM connections and independent scan',async()=>{
   for(const name of ['Alpha','Beta']){
    await select(name);if(robot(name)?.connection_state!=='CONNECTED')await drawer(name).getByRole('button',{name:'Connect',exact:true}).click();
    await poll(()=>robot(name)?.connection_state==='CONNECTED');
    await drawer(name).getByRole('button',{name:'Prepare',exact:true}).click();
    if(robot(name)?.lidar_state!=='STREAMING')await drawer(name).getByRole('button',{name:'LiDAR On',exact:true}).click();
    await poll(()=>robot(name)?.lidar_state==='STREAMING');
   }
   await select('Alpha');await shot('two-connected');return sims();});
  await step('Held button moves selected robot; release retains both connections and scans',async()=>{
   const before=structuredClone(sims());const button=drawer('Alpha').getByRole('button',{name:'Hold forward',exact:true});
   const b=await padBox('Alpha','forward');await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await sleep(2100);await page.mouse.up();
   await poll(()=>robot('Alpha')?.control_state==='PAUSED');await sleep(500);const after=structuredClone(sims());
   const a=after.find(r=>r.label==='Alpha'),b0=before.find(r=>r.label==='Alpha'),beta=after.find(r=>r.label==='Beta');
   if(a.pose.position_m[0]-b0.pose.position_m[0]<.04)throw Error('No measured movement');
   if(after.some((r,i)=>r.connection_epoch!==before[i].connection_epoch||r.connection_state!=='CONNECTED'||r.lidar_state!=='STREAMING'))throw Error('Connection/sensor lost');
   if(JSON.stringify(beta.pose)!==JSON.stringify(before.find(r=>r.label==='Beta').pose))throw Error('Wrong robot moved');
   await shot('held-release');return {before,after};});
  await step('All four normal pointer directions without injected delay',async()=>{
   const moves=[];for(const direction of ['forward','backward','left','right']){
    const before=structuredClone(robot('Alpha')),box=await padBox('Alpha',direction);
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await sleep(900);await page.mouse.up();
    await poll(stopped);const after=structuredClone(robot('Alpha'));checkedTravel(before,after,direction);moves.push({direction,before,after});
   }await shot('four-pad-directions');return {moves};});
  await step('Continuous 60-second held SIM rotation keeps session, sensor and fresh input',async()=>{
   const before=structuredClone(robot('Alpha')),box=await padBox('Alpha','left'),observations=[];
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
   try{
    await poll(()=>robot('Alpha')?.control_state==='DRIVING');const start=Date.now();
    while(Date.now()-start<60000){await sleep(500);const row=structuredClone(robot('Alpha'));
     observations.push({at:Date.now(),control_state:row.control_state,reason:row.reason,telemetry_sequence:row.telemetry_sequence,yaw:row.pose.position_m[2]});
     if(row.control_state!=='DRIVING'||row.connection_epoch!==before.connection_epoch||row.connection_state!=='CONNECTED'||row.lidar_state!=='STREAMING'||Date.now()-result.samples.at(-1).at>2500)throw Error('Continuous held rotation interrupted or observation became stale');
    }
   }finally{await page.mouse.up();result.sustained_hold_observations=observations;await save();}
   await poll(stopped);const after=structuredClone(robot('Alpha'));
   if(after.pose.position_m[2]-before.pose.position_m[2]<2*Math.PI)throw Error('Sustained SIM rotation did not complete a measured turn');
   await shot('held-60s');return {before,after,observed_samples:observations.length,classification:'actual kinematic SIM, not hardware continuous-motion acceptance'};});
  await step('FAULT INJECTION: delayed drive dispatch pauses, retains connection, needs fresh input',async()=>{
   const before=structuredClone(robot('Alpha'));let delayed=0;
   const route=async request=>{let body;try{body=request.request().postDataJSON();}catch{}
    if(request.request().method()==='POST'&&body?.action==='drive'){delayed++;faultRequests.set(request.request(),{delay_ms:350,kind:'dispatch-delay'});await sleep(350);}
    await request.continue().catch(()=>{});};
   fleetRouteHandler=route;
   try{const b=await padBox('Alpha','left');
    await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await sleep(1000);await page.mouse.up();}
   finally{fleetRouteHandler=null;}
   await poll(()=>robot('Alpha')?.control_state==='PAUSED');const after=structuredClone(robot('Alpha'));
   if(!delayed||after.connection_epoch!==before.connection_epoch||after.connection_state!=='CONNECTED'||after.lidar_state!=='STREAMING')throw Error('Delay ended session/sensor');
   await sleep(700);if(Math.abs(robot('Alpha').pose.position_m[2]-after.pose.position_m[2])>.01)throw Error('Old intent resumed');
   return {before,after,delayed,method:'350ms dispatch delay only; no fake response or product state injection'};});
  await step('FAULT MATRIX: 100/250/500/1000ms dispatch gaps preserve session and never replay after confirmed Stop',async()=>{
   const trials=[];result.fault_matrix_trials=trials;
   for(const delay of [100,250,500,1000]){
    const epoch=robot('Alpha').connection_epoch;let dispatches=0;
    const route=async request=>{let body;try{body=request.request().postDataJSON();}catch{}
     if(request.request().method()==='POST'&&body?.action==='drive'){dispatches++;faultRequests.set(request.request(),{delay_ms:delay,kind:'dispatch-delay-matrix'});await sleep(delay);}
     await request.continue().catch(()=>{});};
    fleetRouteHandler=route;
    try{const b=await padBox('Alpha','left');
     await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await sleep(900);await page.mouse.up();}
    finally{await sleep(delay+100);fleetRouteHandler=null;}
    await poll(()=>robot('Alpha')?.control_state==='PAUSED'&&robot('Alpha')?.applied_motion_epoch===robot('Alpha')?.motion_epoch);
    const confirmed=structuredClone(robot('Alpha'));await sleep(500);const after=structuredClone(robot('Alpha'));
    trials.push({delay_ms:delay,dispatches,expected_connection_epoch:epoch,confirmed,after});await save();
    if(!dispatches)throw Error(`Fault matrix ${delay}ms: no drive request observed after pointer input`);
    if(after.connection_epoch!==epoch||after.connection_state!=='CONNECTED'||after.lidar_state!=='STREAMING')throw Error(`Fault matrix ${delay}ms: connection/sensor changed`);
    if(Math.abs(after.pose.position_m[2]-confirmed.pose.position_m[2])>.01)throw Error('Delayed direction replayed after engine Stop');
   }
   return {trials,method:'Delay-only routing on actual renderer requests; not Wi-Fi disconnection or fake engine data'};});
  await step('Keyboard hold and control focus loss pause without disconnect',async()=>{
   // Navigate to the pad using actual keyboard focus. Clicking a direction
   // merely to focus it emits a tiny drive+Stop and races the next keydown.
   await focusPad('Alpha');
   const before=structuredClone(robot('Alpha'));
   await page.keyboard.down('ArrowLeft');await poll(()=>robot('Alpha')?.control_state==='DRIVING');await sleep(900);await page.getByRole('textbox',{name:'Message TwinPulse'}).click();await page.keyboard.up('ArrowLeft');
   const stopRequested=Date.now();await poll(()=>robot('Alpha')?.control_state==='PAUSED'&&robot('Alpha')?.motion_epoch===robot('Alpha')?.applied_motion_epoch);
   const confirmedAfterMs=Date.now()-stopRequested;const a=structuredClone(robot('Alpha'));await sleep(700);const b=structuredClone(robot('Alpha'));
   if(Math.abs(a.pose.position_m[2]-before.pose.position_m[2])<.1)throw Error('Keyboard input did not move');
   if(Math.abs(b.pose.position_m[2]-a.pose.position_m[2])>.01||b.connection_epoch!==before.connection_epoch)throw Error('Focus loss failed to stop or disconnected');
   return {before,a,b,confirmedAfterMs,input:'Test BrowserWindow keyboard, not native OS keyboard'};});
  }
  await step('WASD and all arrow key releases; Space stops without replay',async()=>{
   await focusPad('Alpha');const moves=[];
   for(const [key,direction] of [['w','forward'],['s','backward'],['a','left'],['d','right'],['ArrowUp','forward'],['ArrowDown','backward'],['ArrowLeft','left'],['ArrowRight','right']]){
    const before=structuredClone(robot('Alpha'));await page.keyboard.down(key);await sleep(750);await page.keyboard.up(key);
    await poll(stopped);const after=structuredClone(robot('Alpha'));checkedTravel(before,after,direction);moves.push({key,direction,before,after});
   }
   await page.keyboard.down('w');await poll(()=>robot('Alpha')?.control_state==='DRIVING');await page.keyboard.press('Space');
   await poll(stopped);const afterSpace=structuredClone(robot('Alpha'));await sleep(500);const quiet=structuredClone(robot('Alpha'));await page.keyboard.up('w');
   if(Math.hypot(...quiet.pose.position_m.slice(0,2).map((n,i)=>n-afterSpace.pose.position_m[i]))>.01)throw Error('Space did not keep the held direction stopped');
   await shot('keyboard-matrix');return {moves,afterSpace,quiet,native_os_input:'NOT_RUN'};});
  await step('Main chat bounded 90 degree command, measured completion',async()=>{
   const old=robot('Alpha').pose.position_m[2];await sendChat('Alpha 로봇 왼쪽으로 90도 회전해');
   await poll(()=>robot('Alpha')?.control_state==='DRIVING');await poll(()=>robot('Alpha')?.reason==='TASK_COMPLETED',15000);
   const delta=robot('Alpha').pose.position_m[2]-old;if(Math.abs(delta-Math.PI/2)>.01)throw Error('Wrong angular motion');return {delta,operation_id:robot('Alpha').operation_id};});
  await step('One session full turn with actual simulated scan',async()=>{
   const old=robot('Alpha').pose.position_m[2];await sendChat('Alpha 로봇 한바퀴 돌면서 라이다 기록해');
   await poll(()=>robot('Alpha')?.control_state==='DRIVING');await shot('turn-scan-running');
   await poll(()=>robot('Alpha')?.reason==='TASK_COMPLETED',35000);
   const delta=robot('Alpha').pose.position_m[2]-old;if(Math.abs(delta-2*Math.PI)>.01)throw Error('Full turn incomplete');
   await shot('turn-scan-complete');return {delta,scan_points:robot('Alpha').scan?.points.length,operation_id:robot('Alpha').operation_id};});
  await step('LiDAR Off pauses but retains connection; On restarts sensor',async()=>{
   const epoch=robot('Alpha').connection_epoch;await drawer('Alpha').getByRole('button',{name:'LiDAR Off',exact:true}).click();
   await poll(()=>robot('Alpha')?.lidar_state==='OFF');if(robot('Alpha').connection_epoch!==epoch)throw Error('Disconnected');
   await drawer('Alpha').getByRole('button',{name:'LiDAR On',exact:true}).click();await poll(()=>robot('Alpha')?.lidar_state==='STREAMING');return {epoch};});
  await step('Actual obstacle approach stops Beta and fresh reverse escapes',async()=>{
   await select('Beta');const before=structuredClone(robot('Beta'));
   await sendChat('Beta 로봇 앞으로 1m 이동해');await poll(()=>robot('Beta')?.control_state==='DRIVING');
   await poll(()=>robot('Beta')?.reason==='OBSTACLE_STOP',30000);const stopped=structuredClone(robot('Beta'));
   if(stopped.pose.position_m[0]<=before.pose.position_m[0]+.05)throw Error('No approach before obstacle result');
   await shot('obstacle-stop');await sendChat('Beta 로봇 뒤로 10cm 이동해');
   await poll(()=>robot('Beta')?.control_state==='DRIVING');await poll(()=>robot('Beta')?.reason==='TASK_COMPLETED',10000);
   const escaped=structuredClone(robot('Beta'));if(stopped.pose.position_m[0]-escaped.pose.position_m[0]<.09)throw Error('Fresh escape failed');
   await select('Alpha');return {before,stopped,escaped,guard:'AABB kinematic SIM only, not physical stopping-distance qualification'};});
  await step('Named chat Stop interrupts finite task without model call or disconnect',async()=>{
   const epoch=robot('Alpha').connection_epoch;await sendChat('Alpha 로봇 앞으로 10cm 이동해');
   await poll(()=>robot('Alpha')?.control_state==='DRIVING');await sleep(300);
   await sendChat('Alpha 로봇 멈춰');await poll(()=>robot('Alpha')?.reason==='OPERATOR_STOP');
   if(robot('Alpha').connection_epoch!==epoch||robot('Alpha').connection_state!=='CONNECTED')throw Error('Stop disconnected');return {operation_id:robot('Alpha').operation_id,epoch};});
  await step('Two named finite tasks coexist; visible Stop all confirms both without disconnect',async()=>{
   const before=structuredClone(sims()),alphaText='Alpha 로봇 왼쪽으로 90도 회전해',betaText='Beta 로봇 오른쪽으로 90도 회전해';let delayed=0;
   const route=async request=>{let body;try{body=request.request().postDataJSON();}catch{}
    if(request.request().method()==='POST'&&body?.action==='message'&&body.text===alphaText){delayed++;await sleep(500);}
    await request.continue();};
   await page.route('**/v1/product/conversation',route);
   try{
    await sendChat(alphaText);await poll(()=>delayed===1);
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true}),send=page.getByRole('button',{name:'Send',exact:true});
    await input.fill(betaText);await expect(send).toBeDisabled();
    await expect(send).toBeEnabled();await expect(input).toHaveValue(betaText);
    // Explicit per-robot selection is the product's movement admission contract.
    // Selecting Beta must preserve Alpha's finite task and the newly typed draft.
    await select('Beta');await expect(input).toHaveValue(betaText);
    await send.click();
   }finally{await page.unroute('**/v1/product/conversation',route);}
   await poll(()=>sims().every(row=>row.control_state==='DRIVING'));
   const concurrent=structuredClone(sims());
   await page.getByRole('button',{name:'Stop all',exact:true}).click();
   await poll(()=>sims().every(row=>row.control_state==='PAUSED'&&row.applied_motion_epoch===row.motion_epoch));
   const after=structuredClone(sims());
   if(after.some(row=>row.connection_state!=='CONNECTED'||row.lidar_state!=='STREAMING'||row.connection_epoch!==before.find(old=>old.robot_id===row.robot_id).connection_epoch))throw Error('Stop all ended a connection or sensor');
   await select('Alpha');await shot('two-task-stop-all');return {before,concurrent,after,delayed,explicit_selection_required:true,
    draft_preserved_while_previous_ack_pending:true,method:'500ms dispatch-only delay on actual UI conversation POST; original server response unmodified'};});
  await step('Operation summary opens; raw JSON download is separate',async()=>{
   await drawer('Alpha').getByRole('button',{name:'Operation logs',exact:true}).click();
   await expect(drawer('Alpha').getByRole('button',{name:'Download operation JSON',exact:true})).toBeVisible();
   await shot('operation-summary');const d=page.waitForEvent('download');await drawer('Alpha').getByRole('button',{name:'Download operation JSON',exact:true}).click();
   const download=await d;await download.saveAs(path.join(out,'operation.json'));
   const record=JSON.parse(await fs.readFile(path.join(out,'operation.json'),'utf8'));
   if(record.operation_id!==robot('Alpha').operation_id||!record.events.some(e=>e.kind==='motion_result'))throw Error('Operation correlation missing');
   await drawer('Alpha').getByRole('button',{name:'Close robot controls',exact:true}).click();return {operation_id:record.operation_id,event_count:record.events.length,manifest:record.manifest};});
  await step('Actual frame anchors and camera transition',async()=>{
   const badges=page.locator('.robot-anchor-badge');result.anchor_count=await badges.count();
   await page.getByRole('button',{name:'Orbit left',exact:true}).click();await sleep(1000);await shot('camera-after-orbit');
   const count=await badges.count();if(count<2)throw Error('Missing current robot badge');
   const clicks=[];for(const name of ['Alpha','Beta']){
    await page.getByRole('button',{name:`Select ${name} in Twin`,exact:true}).click();
    await expect(drawer(name)).toBeVisible();clicks.push(name);await drawer(name).getByRole('button',{name:'Close robot controls',exact:true}).click();
   }
   await shot('badges-both-clicked');return {count,clicks};});
 }
 await step('Physical setup shown while robot remains off; no Connect or movement',async()=>{
  const physical=fleet?.robots.find(r=>r.kind==='physical'&&r.robot_id!=='legacy-physical');
  if(!physical)throw Error('Existing registered physical robot required; no fake registration');
  if(phase==='fresh'&&physical.display_pose)throw Error('A previous project/revision physical marker leaked into this new scene');
  result.physical_robot_id=physical.robot_id;result.physical_label=physical.label;
  await page.locator('.robot-fleet-row').filter({hasText:physical.label}).first().click();
  const controls=drawer(physical.label);await expect(controls).toBeVisible();
  await expect(controls.getByRole('region',{name:'Physical connection and readiness'})).toHaveCount(0);
  await expect(controls.getByText('Fresh authenticated session',{exact:false})).toHaveCount(0);
  await expect(controls.getByRole('button',{name:'Hold forward',exact:true})).toBeDisabled();
  const advanced=controls.getByText('Advanced measured protective profile · strict JSON',{exact:true});
  await expect(advanced).toBeVisible();
  if(await advanced.locator('..').getAttribute('open')===null)await advanced.click();
  await expect(controls.getByRole('button',{name:'Prepare',exact:true})).toBeDisabled();
  await expect(controls.getByRole('button',{name:'Run same-boot stop qualification',exact:true})).toBeDisabled();
  const guide=controls.getByText('측정 프로필 작성 안내',{exact:true});
  if(await guide.locator('..').getAttribute('open')===null)await guide.click();
  await expect(controls.getByText('이 안내는 측정 준비용 점검표입니다.',{exact:false})).toBeVisible();
  const pending=page.waitForEvent('download');await controls.getByRole('button',{name:'Download blank measured-profile JSON',exact:true}).click();
  await (await pending).saveAs(path.join(out,'blank-measured-profile.json'));
  const template=JSON.parse(await fs.readFile(path.join(out,'blank-measured-profile.json'),'utf8'));
  if(template.robot_id!==physical.robot_id||!template.binding_sha256||!Object.entries(template).filter(([k])=>!['schema','robot_id','binding_sha256'].includes(k)).every(([,group])=>Object.values(group).every(v=>v===null)))throw Error('Template fabricated measured values or lost identity');
  await shot('physical-off-setup');return {robot_id:physical.robot_id,connection:physical.connection_state,drive:physical.capabilities.drive};
 });
 await step('App-only supervised setup saves offline; all eleven trial paths visible without physical activation',async()=>{
  const controls=drawer(result.physical_label),section=controls.getByRole('region',{name:'Supervised field tests',exact:true});
  await expect(section).toBeVisible();
  const colors=await section.getByRole('form',{name:'Supervised field setup',exact:true}).getByText('Outer footprint radius (m)',{exact:true}).evaluate(label=>{
   const input=label.querySelector('input');return {label:getComputedStyle(label).color,input:input?getComputedStyle(input).color:null,background:input?getComputedStyle(input).backgroundColor:null};
  });
  const luminance=color=>{const rgb=color?.match(/[\d.]+/g)?.slice(0,3).map(Number);if(!rgb||rgb.length!==3)throw Error('Cannot observe RGB');return rgb.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);};
  const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
  if(contrast(colors.label,'rgb(255,255,255)')<4.5||contrast(colors.input,colors.background)<4.5)throw Error('Field form label/input contrast below 4.5:1');
  const runtime=()=>fleet?.robots.find(r=>r.robot_id===result.physical_robot_id);
  const form=section.getByRole('form',{name:'Supervised field setup',exact:true});
  if(phase!=='reopen'){
   await form.getByRole('spinbutton',{name:'Outer footprint radius (m)',exact:true}).fill('0.13');
   await form.getByRole('checkbox',{name:'I reviewed robot model applicability, forward X, left Y, sensor pose, native angle sign and these setup values.',exact:true}).check();
   await form.getByRole('button',{name:'Save supervised setup',exact:true}).click();
   await poll(()=>runtime()?.field?.config?.footprint_radius_m===.13);
  }else{
   const expected=JSON.parse(await fs.readFile(arg('--field-config'),'utf8'));
   if(JSON.stringify(runtime()?.field?.config)!==JSON.stringify(expected))throw Error('Saved supervised config changed after cold reopen');
   await expect(form.getByRole('spinbutton',{name:'Outer footprint radius (m)',exact:true})).toHaveValue('0.13');
  }
  const field=runtime()?.field;
  if(!field?.config||field.config.provenance!=='reference'||field.armed||field.stop_receipt||runtime().operation_id||runtime().capabilities.drive)throw Error('Offline setup promoted measurements or restored physical authority');
  await fs.writeFile(path.join(out,'saved-field-config.json'),JSON.stringify(field.config,null,2));
  const cases=section.getByRole('list',{name:'Available field test cases',exact:true});
  await expect(cases.locator('li')).toHaveCount(11);
  for(const button of await cases.getByRole('button').all())await expect(button).toBeDisabled();
  await expect(section.getByRole('button',{name:'Arm supervised field session',exact:true})).toBeDisabled();
  const physicalRequests=result.fleet_requests.filter(r=>r.robot_id===result.physical_robot_id);
  if(physicalRequests.some(r=>['connect','prepare','qualify','drive','field_arm','field_test'].includes(r.action)))throw Error('Physical activation requested while OFF');
  await shot(phase==='reopen'?'field-cold-restored':'field-offline-saved');
  return {field,colors,label_contrast:contrast(colors.label,'rgb(255,255,255)'),input_contrast:contrast(colors.input,colors.background),
    physical_activation_requests:0,physical_outcomes:'NOT_RUN_ROBOT_OFF'};
 });
 await step('In-App measured-profile editor preserves identity and blocks null or mismatched measurements',async()=>{
  const controls=drawer(result.physical_label),before=result.fleet_requests.filter(row=>row.action==='profile').length;
  await controls.getByRole('button',{name:'Start blank profile in App',exact:true}).click();
  const editor=controls.getByRole('textbox',{name:'Profile JSON editor',exact:true}),blank=JSON.parse(await editor.inputValue());
  const template=JSON.parse(await fs.readFile(path.join(out,'blank-measured-profile.json'),'utf8'));
  if(JSON.stringify(blank)!==JSON.stringify(template))throw Error('App blank differs from original blank download');
  await controls.getByRole('button',{name:'Review edited profile JSON',exact:true}).click();
  await expect(controls.getByText('Unmeasured fields',{exact:false})).toBeVisible();
  await controls.getByRole('checkbox',{name:'I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.',exact:true}).check();
  await expect(controls.getByRole('button',{name:'Apply reviewed profile',exact:true})).toBeDisabled();
  for(const [field,value,code] of [['robot_id','0'.repeat(32),'PROFILE_ROBOT_MISMATCH'],['binding_sha256','0'.repeat(64),'PROFILE_BINDING_MISMATCH']]){
   await editor.fill(JSON.stringify({...blank,[field]:value},null,2));
   await controls.getByRole('button',{name:'Review edited profile JSON',exact:true}).click();
   await expect(controls.getByRole('alert').filter({hasText:code})).toBeVisible();
  }
  await editor.fill(JSON.stringify(blank,null,2));await controls.getByRole('button',{name:'Review edited profile JSON',exact:true}).click();
  await expect(controls.getByText('Unmeasured fields',{exact:false})).toBeVisible();
  const missingCount=async()=>Number((await controls.getByText('Unmeasured fields',{exact:false}).innerText()).match(/Unmeasured fields · (\d+):/)?.[1]);
  const originalMissing=await missingCount();
  for(const [policy,removed] of [['independent_required',1],['explicitly_unverified_supervised',5]]){
   const policyOnly={...blank,progress:{...blank.progress,body_progress_policy:policy}};
   await editor.fill(JSON.stringify(policyOnly,null,2));await controls.getByRole('button',{name:'Review edited profile JSON',exact:true}).click();
   if(await missingCount()!==originalMissing-removed)throw Error('Policy optional measurements do not match exact four body-only null contract');
   await controls.getByRole('checkbox',{name:'I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.',exact:true}).check();
   await expect(controls.getByRole('button',{name:'Apply reviewed profile',exact:true})).toBeDisabled();
   if(policy==='explicitly_unverified_supervised')await expect(controls.getByText('Body progress UNKNOWN',{exact:false})).toBeVisible();
  }
  await editor.fill(JSON.stringify(blank,null,2));await controls.getByRole('button',{name:'Review edited profile JSON',exact:true}).click();
  if(result.fleet_requests.filter(row=>row.action==='profile').length!==before)throw Error('Editor inspection transmitted an unapplied profile');
  await shot('physical-profile-editor');return {identity:blank.robot_id,all_measurements:'original null',policy_only_null_review:true,profile_mutations:0};
 });
 await step('Explicit static estimated physical marker in actual Isaac; not tracking or localization',async()=>{
  const controls=drawer(result.physical_label),marker=controls.getByText('Estimated Twin marker',{exact:true});
  if(await marker.locator('..').getAttribute('open')===null)await marker.click();
  if(phase!=='reopen'){
   await controls.getByRole('spinbutton',{name:'Marker X (m)',exact:true}).fill('3.5');
   await controls.getByRole('spinbutton',{name:'Marker Y (m)',exact:true}).fill('2');
   await controls.getByRole('spinbutton',{name:'Marker yaw (rad)',exact:true}).fill('0');
   await controls.getByRole('button',{name:'Place estimated robot marker',exact:true}).click();
  }
  await poll(()=>fleet?.robots.find(r=>r.robot_id===result.physical_robot_id)?.display_pose?.source==='operator_estimate_not_localized');
  await expect(controls.getByText('Static visualization estimate',{exact:false})).toBeVisible();
  await controls.getByRole('button',{name:'Close robot controls',exact:true}).click();
  await expect(page.getByRole('button',{name:`Select ${result.physical_label} in Twin`,exact:true})).toBeVisible({timeout:20000});
  await page.getByRole('button',{name:`Select ${result.physical_label} in Twin`,exact:true}).click();
  await expect(drawer(result.physical_label)).toBeVisible();await shot('physical-static-marker');
  const r=fleet.robots.find(r=>r.robot_id===result.physical_robot_id);if(r.operation_id||r.capabilities.drive)throw Error('Marker restored physical authority');
  return {display_pose:r.display_pose,connection:r.connection_state,authority:false};
 });
 if(phase!=='reopen')await step('Invalid measured profile rejected by real installed service without fake measured defaults',async()=>{
  const controls=drawer(result.physical_label);expectInvalidProfile=true;
  const advanced=controls.getByText('Advanced measured protective profile · strict JSON',{exact:true});
  if(await advanced.locator('..').getAttribute('open')===null)await advanced.click();
  await controls.getByLabel('Measured profile JSON',{exact:true}).setInputFiles({name:'invalid-profile.json',mimeType:'application/json',buffer:Buffer.from('{}')});
  await expect(controls.getByText('Imported invalid-profile.json',{exact:false})).toBeVisible();
  await controls.getByRole('checkbox',{name:'I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.',exact:true}).check();
  await controls.getByRole('button',{name:'Apply reviewed profile',exact:true}).click();
  await expect(controls.getByRole('alert').filter({hasText:'PROFILE_SHAPE'})).toBeVisible();
  await Promise.all(responseChecks);if(!result.expected_rejections.length)throw Error('Expected schema rejection not recorded');
  expectInvalidProfile=false;await shot('profile-shape-rejected');
  return {classification:'invalid input user flow; DOM file selection, not OS clipboard',rejections:result.expected_rejections};
 });
 await step('Visible Exit TwinPulse normal shutdown',async()=>{exiting=true;const close=page.waitForEvent('close',{timeout:60000});
  await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await close;});
 await Promise.all(responseChecks);
 // A drive already in flight when the operator released the pad must be
 // rejected after the independent Stop. HTTP responses can arrive in either
 // order, so require the matching Stop request before rejection, its 200
 // receipt, and a separately observed engine-applied new epoch.
 result.http_errors=result.http_errors.filter(error=>{
  const drive=result.fleet_requests.find(row=>row.request_id===error.request_id);
  const stopped=drive&&result.fleet_requests.find(row=>row.action==='stop'&&row.status===200&&row.robot_id===drive.robot_id&&
   row.connection_epoch===drive.connection_epoch&&row.operation_id===drive.operation_id&&row.motion_epoch===drive.motion_epoch&&row.order>drive.order&&row.order<drive.response_order&&
   row.result_robots?.some(v=>v.robot_id===drive.robot_id&&v.operation_id===drive.operation_id&&v.connection_epoch===drive.connection_epoch&&v.motion_epoch!==drive.motion_epoch&&
    result.samples.some(sample=>sample.revision>=row.result_revision&&sample.observation_order>row.order&&
     !result.fleet_requests.some(next=>next.action==='drive'&&next.robot_id===drive.robot_id&&next.order>row.order&&next.order<sample.observation_order)&&
     sample.robots.some(applied=>applied.robot_id===v.robot_id&&applied.operation_id===v.operation_id&&
      applied.connection_epoch===v.connection_epoch&&applied.motion_epoch===v.motion_epoch&&applied.applied_motion_epoch===v.motion_epoch&&applied.control_state==='PAUSED'))));
  if(error.path==='/v1/product/robot-fleet'&&error.action==='drive'&&error.status===409&&error.code==='fleet_motion_changed'&&stopped){
   result.stop_fence_rejections.push({...error,drive,confirmed_stop:stopped,
    classification:'Old-epoch rejection overlapping an exact Stop request; engine-applied new epoch confirmed, sole rejection cause not inferred'});return false;}
  return true;
 });
 result.status=result.errors.length||result.http_errors.length||result.request_failures.some(r=>!r.exiting&&!r.fault)?'FAIL':'PASS';
}catch(e){result.status='FAIL';result.error=clean(e);}
finally{if(page&&!page.isClosed()){await page.mouse.up().catch(()=>{});await page.keyboard.up('ArrowLeft').catch(()=>{});}await save();if(browser)await browser.close().catch(()=>{});console.log(JSON.stringify({status:result.status,steps:result.steps.map(({name,status})=>({name,status})),error:result.error}));}
if(result.status!=='PASS')process.exitCode=1;
