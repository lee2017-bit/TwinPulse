// SPDX-License-Identifier: Apache-2.0
// Actual installed Electron UI only. No product API writes or state injection.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {classifyRoomplanResponses} from './roomplan_response_gate.mjs';
import {visibleMotion} from './control_view_acceptance.mjs';
import {checkedSpacePreview,checkedSpaceApply,spaceCommitObservation,COMMITTED_CAPTION} from './roomplan_edit_observation.mjs';
import {beginGestureAttempt,gestureAttemptDiagnostic} from './roomplan_gesture_audit.mjs';
const [phase,out,project,expectedOperation]=process.argv.slice(2);
if(!phase||!out)throw Error('phase and new output folder required');
await fs.mkdir(out,{recursive:false});
const result={phase,status:'FAIL',basis:'Same installed Electron BrowserWindow, explicit Test entry',
 native_os_input:'NOT_RUN',native_file_dialog:'NOT_RUN',hardware_actions:0,
 provider_calls:phase==='ai-edit'?null:0,provider_call_basis:phase==='ai-edit'?'Actual audited model ledger required; UI submission is not HTTP proof':'No model action in this phase',steps:[],responses:[],errors:[]};
result.recorder_sha256=createHash('sha256').update(await fs.readFile(new URL(import.meta.url))).digest('hex');
result.response_policy_sha256=createHash('sha256').update(await fs.readFile(new URL('./roomplan_response_gate.mjs',import.meta.url))).digest('hex');
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('Expected one ordinary installed renderer');
const page=pages[0];page.setDefaultTimeout(30000);
const clean=v=>String(v).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]').slice(0,1500);
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
let finish,auditInstalled=false,activeGesture=null,gestureRobotSnapshot=()=>null;
const pendingResponses=new Set();
page.on('pageerror',e=>result.errors.push(clean(e)));
page.on('requestfailed',r=>{if(new URL(r.url()).pathname.startsWith('/v1/')){
 const row={at:Date.now(),path:new URL(r.url()).pathname,method:r.method(),error:clean(r.failure()?.errorText),native_timing:r.timing()};
 if(row.path==='/v1/product/robot-fleet'&&row.method==='POST')try{row.request=r.postDataJSON();}catch{}
 (result.failed_requests??=[]).push(row);
}});
page.on('response',r=>{const capture=(async()=>{const url=new URL(r.url());
 let savedResume=false;
 if(url.pathname==='/v1/product/conversation'&&r.request().method()==='POST')try{savedResume=r.request().postDataJSON()?.action==='resume';}catch{}
 const usual=url.pathname.includes('/environment')||url.pathname.includes('/scene-edit')||url.pathname.includes('/robot-fleet')||url.pathname==='/v1/product/workflow'||savedResume||r.status()>=400;
 if(usual||r.request().method()==='POST'&&url.pathname.startsWith('/v1/product/')){
  const row={at:Date.now(),path:url.pathname,status:r.status(),method:r.request().method()};result.responses.push(row);
  const timing=r.headers()['server-timing'];if(typeof timing==='string')row.server_timing=timing.slice(0,1200);
  // Retain the actual input/Stop identity. Never capture bootstrap/auth headers.
  if((url.pathname==='/v1/product/robot-fleet'||savedResume)&&row.method==='POST')try{row.request=r.request().postDataJSON();}catch{}
  if(url.pathname==='/v1/product/environment/action'&&row.method==='POST')try{const b=r.request().postDataJSON();if(!b.attachment)row.request=b;}catch{}
  if(url.pathname==='/v1/product/scene-edit/apply'&&row.method==='POST')try{row.request=r.request().postDataJSON();}catch{}
  if(usual)try{const b=await r.json();row.body=b;}catch{}
  await r.finished().catch(()=>{});row.native_timing=r.request().timing();row.native_start_ms=row.native_timing.startTime;
  if(r.request().method()==='POST'||r.status()>=400)await fs.appendFile(path.join(out,'responses.jsonl'),JSON.stringify(row)+'\n');
 }
 })();pendingResponses.add(capture);void capture.finally(()=>pendingResponses.delete(capture));
});
const shot=async n=>{await page.screenshot({path:path.join(out,n+'.png')});await fs.writeFile(path.join(out,n+'.aria.txt'),await page.locator('body').ariaSnapshot());};
const step=async(n,f)=>{const start=Date.now();await f();result.steps.push({name:n,status:'PASS',started_at_ms:start,ended_at_ms:Date.now(),ms:Date.now()-start});await save();console.log(n);};
try{
 result.versions=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 result.user_agent=await page.evaluate(()=>navigator.userAgent);
 if(!result.user_agent.includes('Electron/'))throw Error('Not Electron');
 if(phase==='inspect'){await shot('current');result.status='OBSERVED';}
 if(phase==='final-log'){
  if(!/^[a-f0-9]{32}$/.test(expectedOperation??''))throw Error('Original same-session operation ID required');
  const controls=page.getByRole('region',{name:'Control '+project,exact:true});
  await controls.getByRole('button',{name:'Operation logs',exact:true}).click();
  const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Download operation JSON',exact:true}).click();
  const item=await pending;await item.saveAs(path.join(out,item.suggestedFilename()));
  const original=JSON.parse(await fs.readFile(path.join(out,item.suggestedFilename()),'utf8'));
  if(original.operation_id!==expectedOperation||original.manifest?.complete!==true||original.manifest?.completeness!=='FINALIZED')throw Error('Original operation is not finalized');
  result.operation_download=item.suggestedFilename();result.operation_id=original.operation_id;result.manifest=original.manifest;
  await shot('finalized-operation');result.status='PASS';
 }
 if(phase==='import'){
  finish=await recordRenderedPage(page,path.join(out,'recording'));
  await step('Isaac ready',async()=>await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000}));
  await step('Actual New chat',async()=>{await page.getByRole('button',{name:'＋ New chat',exact:true}).click();await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toBeVisible();});
  await step('Attach original USD and choose space purpose',async()=>{
   const file=page.locator('input[type=file]').first();
   await file.setInputFiles('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd');
   await expect(page.getByRole('button',{name:'Library asset',exact:true})).toBeVisible();
   await shot('01-purpose');
   await page.getByRole('button',{name:'Import space',exact:true}).last().click();
  });
  const panel=page.getByRole('region',{name:'Import space',exact:true});
  await step('Explicit uncalibrated meters and local inspection',async()=>{
   await panel.getByLabel('Space source units',{exact:true}).selectOption('m');
   await panel.getByRole('button',{name:'Inspect space',exact:true}).click();
   await expect(panel.getByText('Inspection ready · review units and objects before import.',{exact:true})).toBeVisible({timeout:110000});
   await shot('02-inspection');
  });
  await step('Adopt original space into empty project',async()=>{
   await panel.getByRole('button',{name:'Import space',exact:true}).click();
   await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible();
   await shot('03-imported');
  });
  await step('Show Twin with engine receipt',async()=>{
   await panel.getByRole('button',{name:'Show Twin',exact:true}).click();
   await expect.poll(async()=>{const alert=await panel.getByRole('alert').allTextContents();if(alert.length)throw Error(alert.join(';'));return await panel.innerText();},{timeout:120000}).toContain('Build command: succeeded · receipt received');
   await panel.getByRole('button',{name:'Close import space',exact:true}).click();
   await expect(page.getByRole('heading',{name:'Digital Twin',exact:true})).toBeVisible();
   await page.waitForTimeout(4000);await shot('04-live-import');
  });
  result.status='PASS';
 }
 if(phase==='exit'){
  await shot('before-exit');await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();
  await page.waitForEvent('close',{timeout:60000});result.status='PASS';
 }
 if(phase==='stop-failed'){
  const controls=page.getByRole('region',{name:'Control '+(project??'RoomPlan SIM'),exact:true});
  await step('Explicit Stop and LiDAR off after retained failure',async()=>{
   await controls.getByRole('button',{name:'Stop',exact:true}).click();
   const off=controls.getByRole('button',{name:'Turn LiDAR off'});if(await off.isVisible())await off.click();
   await controls.getByRole('button',{name:'Operation logs',exact:true}).click();
   const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Download operation JSON',exact:true}).click();
   const download=await pending;await download.saveAs(path.join(out,download.suggestedFilename()));
   await shot('failure-logs');
   await controls.getByRole('button',{name:'Disconnect',exact:true}).click();
  });
  await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await page.waitForEvent('close',{timeout:60000});result.status='PASS_STOP_CLEANUP_NOT_MOTION';
 }
 if(phase==='sim'){
  result.gesture_audit_helper_sha256=createHash('sha256').update(await fs.readFile(new URL('./roomplan_gesture_audit.mjs',import.meta.url))).digest('hex');
  finish=await recordRenderedPage(page,path.join(out,'recording'));
  // Passive recording-only input evidence, never product/robot state.
  await page.evaluate(()=>{
   const events=[];
   const observe=e=>{if(['blur','resize'].includes(e.type)&&e.target!==window)return;const button=e.target?.closest?.('button')?.getAttribute('aria-label');events.push({type:e.type,at:Date.now(),native_event_ms:e.timeStamp,button,trusted:e.isTrusted});};
   for(const type of ['pointerdown','pointerup','pointercancel','blur','resize'])window.addEventListener(type,observe,{capture:true,passive:true});
   window.__roomplanGestureAudit={events,remove:()=>{for(const type of ['pointerdown','pointerup','pointercancel','blur','resize'])window.removeEventListener(type,observe,true);delete window.__roomplanGestureAudit;}};
  });auditInstalled=true;result.gestures=[];result.gesture_attempts=[];
  const simLabel='RoomPlan SIM '+path.basename(out);
  const fleet=page.getByRole('region',{name:'Robot fleet',exact:true});
  const current=()=>[...result.responses].reverse().find(r=>r.body?.robots)?.body?.robots.find(r=>r.label===simLabel);
  gestureRobotSnapshot=current;
  const recordAttempt=(direction,before,auditStart,continuous=false)=>{
   const attempt=beginGestureAttempt({direction,before,auditStart,continuous,responseStart:result.responses.length,
    failedRequestStart:result.failed_requests?.length??0,observedAtMs:Date.now()});
   result.gesture_attempts.push(attempt);activeGesture=attempt;return attempt;
  };
  await step('Control view keeps the imported space visible',async()=>{
   if(await page.getByRole('button',{name:'Control view',exact:true}).getAttribute('aria-pressed')!=='true')await page.getByRole('button',{name:'Control view',exact:true}).click();
   if(await page.getByRole('button',{name:'Toggle conversations and projects'}).getAttribute('aria-expanded')==='true')await page.getByRole('button',{name:'Toggle conversations and projects'}).click();
   await shot('01-control-view');
  });
  await step('Explicit SIM registration at predeclared start',async()=>{
   if(await fleet.getByRole('button',{name:'Manage robot fleet'}).getAttribute('aria-expanded')!=='true')await fleet.getByRole('button',{name:'Manage robot fleet'}).click();
   const registration=fleet.locator('details.robot-fleet-register');
   if(await registration.getAttribute('open')===null)await registration.locator('summary').click();
   await fleet.getByLabel('Name',{exact:true}).fill(simLabel);
   await fleet.getByLabel('X (m)',{exact:true}).fill('2.25');await fleet.getByLabel('Y (m)',{exact:true}).fill('0.95');
   await fleet.getByLabel('Yaw (rad)',{exact:true}).fill('0');
   await page.waitForTimeout(1500);await shot('02-add-sim');
   await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();
   await expect(fleet.getByRole('button',{name:new RegExp(simLabel+' ')})).toBeVisible();
   await fleet.getByRole('button',{name:new RegExp(simLabel+' ')}).click();
   await expect(page.getByRole('region',{name:'Control '+simLabel,exact:true})).toBeVisible();
  });
  const controls=page.getByRole('region',{name:'Control '+simLabel,exact:true});
  result.stop_receipts=[];
  const nextStop=before=>page.waitForResponse(response=>{
   if(new URL(response.url()).pathname!=='/v1/product/robot-fleet'||response.request().method()!=='POST')return false;
   try{const q=response.request().postDataJSON();return q.action==='stop'&&q.robot_id===before.robot_id&&q.connection_epoch===before.connection_epoch&&q.motion_epoch===before.motion_epoch;}catch{return false;}
  },{timeout:12000});
  const confirmedStop=async(responsePromise,before)=>{
   const response=await responsePromise,q=response.request().postDataJSON(),body=await response.json();
   const receipt=body.robots?.find(r=>r.robot_id===before.robot_id);
   if(response.status()!==200||!receipt?.motion_epoch||receipt.motion_epoch===before.motion_epoch||receipt.operation_id!==before.operation_id||receipt.connection_epoch!==before.connection_epoch||receipt.control_state!=='PAUSED')throw Error('Exact Stop response/new epoch missing');
   await expect.poll(()=>{const r=current();return r?.robot_id===before.robot_id&&r.operation_id===before.operation_id&&r.connection_epoch===before.connection_epoch&&r.control_state==='PAUSED'&&r.motion_epoch===receipt.motion_epoch&&r.applied_motion_epoch===receipt.motion_epoch;},{timeout:12000}).toBe(true);
   result.stop_receipts.push({request:q,receipt,engine_ack:current()});
  };
  const explicitStop=async()=>{
   const before=current(),pending=nextStop(before);
   await controls.getByRole('button',{name:'Stop',exact:true}).click();
   await confirmedStop(pending,before);
  };
  await step('Connect and Prepare the explicitly selected SIM',async()=>{
   await controls.getByRole('button',{name:'Connect',exact:true}).click();
   await expect(controls.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:45000});
   await controls.getByRole('button',{name:'Prepare',exact:true}).click();
   await expect(controls.getByRole('button',{name:'Hold forward'})).toBeEnabled({timeout:45000});
   await shot('03-prepared');result.registered=current();
  });
  await step('LiDAR streaming from the imported mesh',async()=>{
   await controls.getByRole('button',{name:'Turn LiDAR on'}).click();
   await expect.poll(()=>current()?.lidar_state,{timeout:20000}).toBe('STREAMING');
   await page.getByRole('combobox',{name:'LiDAR visualization'}).selectOption('rays');
   await page.waitForTimeout(2000);await shot('04-lidar');result.sensor=current();
  });
  for(const direction of ['forward','backward','left','right'])await step('Manual '+direction+' and release stop',async()=>{
   const button=controls.getByRole('button',{name:'Hold '+direction});await expect(button).toBeEnabled();
   const auditStart=await page.evaluate(()=>window.__roomplanGestureAudit.events.length);
   const before=current(),attempt=recordAttempt(direction,before,auditStart);await button.hover();
   attempt.down_requested_at_ms=Date.now();await page.mouse.down();attempt.down_returned_at_ms=Date.now();
   await page.waitForTimeout(direction==='forward'||direction==='backward'?1200:800);
   const pendingStop=nextStop(before);void pendingStop.catch(()=>{});
   attempt.up_requested_at_ms=Date.now();await page.mouse.up();attempt.up_returned_at_ms=Date.now();
   await confirmedStop(pendingStop,before);
   const after=current(),a=before.pose.position_m,b=after.pose.position_m;
   const delta=(b[0]-a[0])*Math.cos(a[2])+(b[1]-a[1])*Math.sin(a[2]);
   const yaw=Math.atan2(Math.sin(b[2]-a[2]),Math.cos(b[2]-a[2]));
   if(direction==='forward'&&delta<.02||direction==='backward'&&delta>-.02||direction==='left'&&yaw<.1||direction==='right'&&yaw>-.1)throw Error('Actual SIM direction did not meet the minimum displacement/angle');
   await expect.poll(()=>current()?.telemetry_sequence,{timeout:5000}).toBeGreaterThan(after.telemetry_sequence+1);
   const stable=current(),events=await page.evaluate(index=>window.__roomplanGestureAudit.events.slice(index),auditStart);
   const down=events.find(e=>e.type==='pointerdown'&&e.button==='Hold '+direction),up=events.find(e=>e.type==='pointerup'&&e.button==='Hold '+direction);
   if(!down||!up)throw Error('Original trusted pointer down/up evidence absent');
   result.gestures.push({direction,before,after,stable_after:stable,down,up,interruptions:events.filter(e=>['pointercancel','blur','resize'].includes(e.type))});
   attempt.status='PASS';attempt.completed_at_ms=Date.now();attempt.audit_end_index=auditStart+events.length;activeGesture=null;
   result.steps.push({name:'manual-observation-'+direction,before,after:current()});
  });
  await step('Shared imported mask and 60-second uninterrupted visible hold',async()=>{
   const map=[...result.responses].reverse().find(r=>r.body?.navigation_scene?.status==='AVAILABLE')?.body.navigation_scene;
   if(map?.kind!=='imported'||map.source_sha256!=='844366fc9e53e1ad8887a2db92c086462bf12a4b54b16d39eb2d7e3259b4d69b'||
      map.units_basis!=='selected_for_sim'||map.physical_accuracy!=='UNQUALIFIED'||!map.geometry_revision)throw Error('No current source-bound imported mask summary');
   result.shared_map=map;result.continuous_display=[];
   const button=controls.getByRole('button',{name:'Hold left'});await button.hover();const before=current();
   const auditStart=await page.evaluate(()=>window.__roomplanGestureAudit.events.length);
   const attempt=recordAttempt('left',before,auditStart,true);
   attempt.down_requested_at_ms=Date.now();await page.mouse.down();attempt.down_returned_at_ms=Date.now();
   await expect.poll(()=>current()?.control_state,{timeout:5000}).toBe('DRIVING');
   result.continuous=await visibleMotion(page,simLabel,null,{duration:60000,timeout:65000,onSample:value=>{
    const robot=current();if(robot?.control_state!=='DRIVING'||robot.motion_epoch!==before.motion_epoch)throw Error('Held control paused or changed epoch: '+JSON.stringify(robot));
    result.continuous_display.push({view:value,control_state:robot.control_state,motion_epoch:robot.motion_epoch,sequence:robot.telemetry_sequence});
   }});
   const pending=nextStop(before);void pending.catch(()=>{});
   attempt.up_requested_at_ms=Date.now();await page.mouse.up();attempt.up_returned_at_ms=Date.now();await confirmedStop(pending,before);
   const after=current();await expect.poll(()=>current()?.telemetry_sequence,{timeout:5000}).toBeGreaterThan(after.telemetry_sequence+1);
   const events=await page.evaluate(index=>window.__roomplanGestureAudit.events.slice(index),auditStart);
   result.gestures.push({direction:'left',continuous:true,before,after,stable_after:current(),
    down:events.find(e=>e.type==='pointerdown'&&e.button==='Hold left'),up:events.find(e=>e.type==='pointerup'&&e.button==='Hold left'),
    interruptions:events.filter(e=>['pointercancel','blur','resize'].includes(e.type))});
   attempt.status='PASS';attempt.completed_at_ms=Date.now();attempt.audit_end_index=auditStart+events.length;activeGesture=null;await shot('04-continuous-60s');
  });
  await step('Original Sofa0 destination, not a substituted goal',async()=>{
   const command=controls.getByRole('textbox',{name:'Robot command'});await command.fill('Go to the nearest sofa');await page.waitForTimeout(3000);
   await shot('05-sofa-command');await command.press('Enter');await expect(command).toHaveValue('');
   await expect.poll(()=>current()?.command?.state,{timeout:90000}).toBe('ARRIVED');
   if(current()?.command?.target_id!=='Env_cc8fbcdf2f69d0ebdbd8')throw Error('Wrong target identity');
   result.arrival=current();await shot('06-sofa-arrived');
   await explicitStop();
  });
  await step('Main chat finite robot command uses the same selected SIM',async()=>{
   const input=page.getByRole('textbox',{name:'Message TwinPulse'});await input.fill('Robot move backward 10 cm');await page.waitForTimeout(3000);
   await input.press('Enter');
   await expect.poll(()=>current()?.command?.text,{timeout:15000}).toBe('Robot move backward 10 cm');
   await expect.poll(()=>current()?.command?.state,{timeout:20000}).toBe('COMPLETED');
   result.chat_motion=current();await shot('06b-chat-control');
   await explicitStop();
  });
  await step('One full scan turn is an explicit bounded SIM command',async()=>{
   const input=controls.getByRole('textbox',{name:'Robot command'});await input.fill('LiDAR one full turn');await page.waitForTimeout(3000);await input.press('Enter');
   await expect.poll(()=>current()?.command?.text,{timeout:15000}).toBe('LiDAR one full turn');
   await expect.poll(()=>current()?.command?.state,{timeout:45000}).toBe('COMPLETED');
   result.full_turn=current();await shot('06c-full-turn');
   await explicitStop();
  });
  await step('LiDAR off and operation export',async()=>{
   await controls.getByRole('button',{name:'Turn LiDAR off'}).click();
   await expect.poll(()=>current()?.lidar_state,{timeout:15000}).toBe('OFF');
   await controls.getByRole('button',{name:'Operation logs',exact:true}).click();await shot('07-operation-logs');
   const download=page.waitForEvent('download');await page.getByRole('button',{name:/Download complete JSON|Download operation/}).click();
   const item=await download;await item.saveAs(path.join(out,item.suggestedFilename()));result.operation_download=item.suggestedFilename();
   const originalExport=JSON.parse(await fs.readFile(path.join(out,result.operation_download),'utf8'));
   result.operation_events=originalExport.events;result.operation_id=originalExport.operation_id;result.project_id=originalExport.project_id;
  });
  await controls.getByRole('button',{name:'Disconnect',exact:true}).click();
  await expect.poll(()=>current()?.connection_state,{timeout:15000}).toBe('DISCONNECTED');
  result.status='PASS';
 }
 if(phase==='edit'||phase==='ai-edit'){
  result.edit_observation_sha256=createHash('sha256').update(await fs.readFile(new URL('./roomplan_edit_observation.mjs',import.meta.url))).digest('hex');
  finish=await recordRenderedPage(page,path.join(out,'recording'));
  const openedAt=result.responses.length;
  await page.getByRole('button',{name:'Import space',exact:true}).first().click();
  const panel=page.getByRole('region',{name:'Import space',exact:true});
  const currentEnvironment=()=>[...result.responses.slice(openedAt)].reverse().find(r=>r.path==='/v1/product/environment'&&r.method==='GET'&&r.status===200&&r.body?.status==='imported'&&r.body.scene_revision)?.body;
  await expect.poll(()=>!!currentEnvironment(),{timeout:15000}).toBe(true);
  const origin=currentEnvironment();result.edit_origin={project_id:origin.project_id,source_sha256:origin.source_sha256,scene_revision:origin.scene_revision};
  result.edit_previews=[];result.edit_transactions=[];
  let movedPreview,undoPreview;
  const observePreview=async(action,click,mode,parent,previousOperation=null)=>{
   const pending=page.waitForResponse(response=>{
    if(new URL(response.url()).pathname!=='/v1/product/environment/action'||response.request().method()!=='POST')return false;
    try{return response.request().postDataJSON()?.action===action;}catch{return false;}
   },{timeout:30000});void pending.catch(()=>{});
   await click();const response=await pending;
   const original={status:response.status(),request:response.request().postDataJSON(),body:await response.json()};
   const expected=checkedSpacePreview(original,{mode,parent,project:origin.project_id,source:origin.source_sha256,previousOperation});
   result.edit_previews.push({expected,request:original.request,status:original.status});return expected;
  };
  const applyAndConfirm=async expected=>{
   const boundary=result.responses.length,started=Date.now();
   const pending=page.waitForResponse(response=>new URL(response.url()).pathname==='/v1/product/scene-edit/apply'&&response.request().method()==='POST',{timeout:30000});
   void pending.catch(()=>{});
   await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();
   const response=await pending;
   checkedSpaceApply(expected,{status:response.status(),request:response.request().postDataJSON(),body:await response.json()});
   let evidence;
   await Promise.race([
    expect.poll(async()=>{
     const canvas=page.locator('.twin-frame-slot canvas');
     const frame=await canvas.count()?await canvas.evaluate(canvas=>({live:canvas.dataset.live==='true',scene_revision:canvas.dataset.sceneRevision,
      stage_epoch:canvas.dataset.stageEpoch,frame_id:Number(canvas.dataset.frameId),frame_age_ms:Date.now()-Number(canvas.dataset.capturedAt)})):null;
     const ui={caption:await panel.getByText(COMMITTED_CAPTION,{exact:true}).isVisible()?COMMITTED_CAPTION:null,
      undo_enabled:await panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).isEnabled(),
      preview_visible:await panel.getByRole('region',{name:'Space edit preview',exact:true}).isVisible(),frame};
     evidence=spaceCommitObservation(expected,result.responses.slice(boundary),ui);return !!evidence;
    },{timeout:140000}).toBe(true),
    panel.getByRole('alert').first().waitFor({state:'visible',timeout:140000}).then(async()=>{throw Error(await panel.getByRole('alert').first().innerText());}),
   ]);
   const catalog=page.locator('section[aria-label="Obstacle observation feedback"]');
   // The existing feedback lives under a collapsed Details element. Read its
   // public DOM state without opening it or claiming visible-pixel evidence.
   const observation=catalog.locator('select[aria-label="Obstacle observation"]');
   await expect(observation).toBeEnabled({timeout:6000});
   await expect(catalog.locator('[role="alert"]')).toHaveCount(0);
   const catalog_ui={at:Date.now(),project_id:expected.project_id,scene_revision:expected.result_revision,context_controls_enabled:await observation.isEnabled(),alert_count:await catalog.locator('[role="alert"]').count(),observation_scope:'Public DOM state under existing collapsed Details; not visible-pixel evidence'};
   result.edit_transactions.push(structuredClone({started_at_ms:started,confirmed_at_ms:Date.now(),...evidence,catalog_ui}));
  };
  await step('Select Chair0 and preview a bounded 0.1m edit',async()=>{
   await panel.getByLabel('Imported object',{exact:true}).selectOption('Env_7869f91460f65066f8c9');
   if(phase==='ai-edit'){
    await panel.getByLabel('Object move request',{exact:true}).fill('Move the selected object 10 cm along world +X. Keep Y and Z unchanged.');
    await page.waitForTimeout(3000);await shot('00-model-request');
    await panel.getByRole('button',{name:'Suggest move',exact:true}).click();
    await expect.poll(async()=>{const alert=await panel.getByRole('alert').allTextContents();if(alert.length)throw Error(alert.join(';'));return await panel.innerText();},{timeout:120000}).toContain('Move suggestion: ready');
    const response=[...result.responses].reverse().find(r=>r.body?.proposal?.status==='ready');
    if(!response?.body.proposal?.suggestion||!response.body.proposal.model_id)throw Error('No actual identified model proposal');
    result.model_proposal=response.body.proposal;
    if(JSON.stringify(result.model_proposal.suggestion.translation_m)!=='[0.1,0,0]')throw Error('Model did not honor the explicit 10cm +X request');
    await shot('01-model-suggestion');
    if(result.model_proposal.source_revision!==origin.scene_revision)throw Error('Model suggestion changed the original edit revision');
    movedPreview=await observePreview('model_review',()=>panel.getByRole('button',{name:'Review suggestion',exact:true}).click(),'change',origin.scene_revision);
   }else{
    await panel.getByLabel('Space object move X',{exact:true}).fill('0.1');
    movedPreview=await observePreview('move_preview',()=>panel.getByRole('button',{name:'Preview object move',exact:true}).click(),'change',origin.scene_revision);
   }
   await expect(panel.getByRole('region',{name:'Space edit preview'})).toBeVisible({timeout:16000});await shot('01-move-preview');
  });
  await step('Apply, engine ACK, durable revision and current frame',async()=>{
   await applyAndConfirm(movedPreview);
   await shot('02-move-committed');
  });
  await step('Undo through the same engine/durable transaction',async()=>{
   undoPreview=await observePreview('undo_preview',()=>panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click(),'undo',movedPreview.result_revision,movedPreview.operation_id);
   if(undoPreview.result_revision===origin.scene_revision)throw Error('Undo must retain its new parent-bound revision');
   await expect(panel.getByRole('region',{name:'Space edit preview'})).toBeVisible({timeout:16000});await shot('03-undo-preview');
   await applyAndConfirm(undoPreview);
   await shot('04-undo-committed');
  });
  result.edit_chain={initial_revision:origin.scene_revision,moved_revision:movedPreview.result_revision,undone_revision:undoPreview.result_revision,
   operation_ids:[movedPreview.operation_id,undoPreview.operation_id]};
  await panel.getByRole('button',{name:'Close import space'}).click();await shot('05-restored');result.status='PASS';
 }
 if(phase==='undo-pending'){
  const panel=page.getByRole('region',{name:'Import space',exact:true});
  await expect(panel.getByRole('region',{name:'Space edit preview'})).toBeVisible();
  await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();
  await expect(panel.getByText('Edit COMMITTED · Engine ACK confirmed · Saved yes · Current frame confirmed',{exact:true})).toBeVisible({timeout:140000});
  await expect(panel.getByRole('button',{name:'Show Twin',exact:true})).toBeEnabled({timeout:16000});
  await shot('recovered-undo');await panel.getByRole('button',{name:'Close import space'}).click();result.status='PASS';
 }
 if(phase==='cold'){
  if(!/^chat_[A-Za-z0-9_]+$/.test(project??''))throw Error('Exact prior UI project ID required');
  result.selected_project=project;
  finish=await recordRenderedPage(page,path.join(out,'recording'));
  await step('Cold installed Isaac start',async()=>await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000}));
  await step('Reopen the exact imported project',async()=>{
   if(await page.getByRole('button',{name:'Toggle conversations and projects'}).getAttribute('aria-expanded')!=='true')await page.getByRole('button',{name:'Toggle conversations and projects'}).click();
   await page.getByRole('button',{name:'Open '+project,exact:true}).click();
   // Initial switch admission + pending-project observation each retain their
   // existing 15s budgets. A 5s assertion is not that product contract.
   await expect(page.getByText('Local scanned space imported.',{exact:false}).first()).toBeVisible({timeout:35000});
   // Cold history is not a current review or Build authority. Use the actual
   // existing UI resume action before expecting imported/editable metadata.
   const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});
   await expect(reopen).toBeVisible({timeout:15000});
   const resumed=page.waitForResponse(response=>{
    if(new URL(response.url()).pathname!=='/v1/product/conversation'||response.request().method()!=='POST')return false;
    try{return response.request().postDataJSON()?.action==='resume';}catch{return false;}
   // Existing old-read drain (up to 6s) + 15s mutation + UI delivery margin.
   },{timeout:25000});
   await reopen.click();const resumeResponse=await resumed;if(resumeResponse.status()!==200)throw Error('Saved review did not succeed');
   await expect(reopen).toBeHidden({timeout:20000});
   await page.getByRole('button',{name:'Import space',exact:true}).first().click();
   const panel=page.getByRole('region',{name:'Import space',exact:true});
   await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible({timeout:20000});
   await expect(panel.getByText('Project-2610222326.usd · 30 objects · Units: selected_for_sim',{exact:true})).toBeVisible();
   await shot('01-cold-original');
  });
  await step('Explicitly show saved original geometry after cold reopen',async()=>{
   const panel=page.getByRole('region',{name:'Import space',exact:true});
   await panel.getByRole('button',{name:'Show Twin',exact:true}).click();
   await expect.poll(async()=>await panel.innerText(),{timeout:120000}).toContain('Build command: succeeded · receipt received');
   await panel.getByRole('button',{name:'Close import space'}).click();
   await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();await shot('02-cold-render');
  });
  result.status='PASS';
 }
}catch(e){result.error=clean(e);if(activeGesture){activeGesture.status='FAIL';activeGesture.failed_at_ms=Date.now();activeGesture.error=result.error;}
 console.log(result.error);await shot('failure').catch(()=>{});}
finally{
 if(auditInstalled){
  if(page.isClosed())result.gesture_audit={status:'UNAVAILABLE_PAGE_CLOSED'};
  else try{result.gesture_audit=await page.evaluate(()=>{
   const audit=window.__roomplanGestureAudit;
   return audit?{status:'CAPTURED',captured_at_ms:Date.now(),events:audit.events.slice()}:{status:'UNAVAILABLE_LISTENER_MISSING'};
  });}catch(e){result.gesture_audit={status:'CAPTURE_FAILED',error:clean(e)};}
  // Save original passive event values before removing the observer, even if
  // the gesture threw before release/Stop acknowledgement. This is diagnostic
  // evidence only and is never added to the successful gestures array.
  await save().catch(e=>{result.gesture_audit_storage_error=clean(e);});
  if(!page.isClosed())await page.evaluate(()=>window.__roomplanGestureAudit?.remove()).catch(e=>{result.gesture_audit_remove_error=clean(e);});
 }
 if(finish)try{result.video=await finish();}catch(e){result.video_error=clean(e);}
 await Promise.allSettled([...pendingResponses]);
 if(auditInstalled)result.gesture_diagnostics=(result.gesture_attempts??[]).map(attempt=>gestureAttemptDiagnostic(attempt,{
  audit:result.gesture_audit,rows:result.responses,failedRequests:result.failed_requests??[],finalRobot:gestureRobotSnapshot(),error:attempt.error??result.error??null}));
 result.response_gate=classifyRoomplanResponses(result);
 if(['import','edit','ai-edit','sim','cold','final-log'].includes(phase)&&result.status==='PASS'&&(result.errors.length||result.failed_requests?.length||result.response_gate.status!=='PASS'||result.video_error)){
  result.status='FAIL';result.error='Whole-journey gate rejected renderer/network/recording errors; retain original responses.';
 }
 if(result.status==='PASS'&&result.response_gate.expected_stop_rejections.length)result.status='PASS_WITH_EXPECTED_STOP_REJECTION';
 await save();await browser.close();
}
console.log(JSON.stringify({phase,status:result.status,steps:result.steps.map(s=>({name:s.name,status:s.status,ms:s.ms})),error:result.error}));
process.exitCode=['PASS','PASS_WITH_EXPECTED_STOP_REJECTION','OBSERVED','PASS_STOP_CLEANUP_NOT_MOTION'].includes(result.status)?0:1;
