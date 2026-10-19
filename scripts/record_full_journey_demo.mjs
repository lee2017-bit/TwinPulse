// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// A separate clean, fixed-size actual UI demonstration, not the acceptance gate.
import {expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
import {currentControlView,checkControlView} from './control_view_acceptance.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const out=process.argv[2];if(!out)throw Error('New output required');
const s=await attachPoweredSession(out),page=s.page;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(fn,timeout=30000)=>{const end=Date.now()+timeout;while(Date.now()<end){if(fn())return;await sleep(100);}throw Error('Actual observed state timeout');};
const robot=()=>s.fleet?.robots.find(r=>r.label==='TurtleBot3');
const drawer=()=>page.getByRole('region',{name:'Control TurtleBot3',exact:true});
const result={classification:'SEPARATE_FRESH_FIXED_SIZE_DEMO_NOT_FULL_ACCEPTANCE',status:'IN_PROGRESS',identity:s.identity,physical:'OFF_NO_CONTACT',steps:[]};
let videoFinished=false;
async function step(name,fn){await s.note(name);const start=Date.now();console.log(JSON.stringify({demo_step:name,at:start}));const evidence=await fn();result.steps.push({name,elapsed_ms:Date.now()-start,evidence});}
async function send(text){await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();}
try{
 await step('Home before New chat',async()=>{await expect(page.getByRole('heading',{name:'What would you like to build?',exact:true})).toBeVisible();
  await expect(page.locator('.chat-sidebar-slot')).toBeHidden();await poll(()=>s.frames.length>0);await s.shot('home');
  await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});await sleep(1500);return {no_scene_reuse:true};});
 await step('New chat and English input',async()=>{
  await page.getByRole('button',{name:'＋ Start a new chat',exact:true}).click();
  const text='Create an estimated 6m by 5m room. Place one bed near the back wall on the left, and one desk with one chair near the back wall on the right. Leave the middle and front floor open for a low-speed robot simulation. Label all dimensions as estimates.';
  result.input_sha256=createHash('sha256').update(text).digest('hex');await send(text);
  const mode=page.getByRole('radio',{name:'Simulation only',exact:true});await expect(page.getByRole('button',{name:'Create Twin',exact:true}).or(mode)).toBeVisible({timeout:15000});
  if(await mode.isVisible())await mode.check();await sleep(1000);await page.getByRole('button',{name:'Create Twin',exact:true}).click();return {text};});
 await step('Actual provider generation and Isaac scene',async()=>{
  await expect(page.getByText('Your environment Twin is saved without a SIM robot or automatic route.',{exact:false})).toBeVisible({timeout:240000});
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible();
  result.project=(await page.getByRole('banner').innerText()).match(/chat_[a-zA-Z0-9_]+/)?.[0];await s.shot('generated');});
 await step('Register robot and explicit Connect and Prepare',async()=>{
  await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();await page.getByText('Add SIM robot',{exact:true}).click();
  await page.getByRole('textbox',{name:'Name',exact:true}).fill('TurtleBot3');
  await page.getByRole('spinbutton',{name:'X (m)',exact:true}).fill('1');await page.getByRole('spinbutton',{name:'Y (m)',exact:true}).fill('1');
  await page.getByRole('button',{name:'Add SIM robot',exact:true}).click();await poll(()=>!!robot());
  await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
  await page.locator('.robot-fleet-row').filter({hasText:'TurtleBot3'}).click();
  await drawer().getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot()?.connection_state==='CONNECTED');
  await drawer().getByRole('button',{name:'Prepare',exact:true}).click();
  const on=drawer().getByRole('button',{name:'Turn LiDAR on',exact:true});if(await on.isVisible())await on.click();await poll(()=>robot()?.lidar_state==='STREAMING');
  // Selecting a fleet row already opens Control view. It is a toggle, so an
  // unconditional second click would leave the compact control layout.
  const control=page.getByRole('button',{name:'Control view',exact:true});
  if(await control.getAttribute('aria-pressed')!=='true')await control.click();
  await expect(control).toHaveAttribute('aria-pressed','true');await sleep(1000);
  const v=await currentControlView(page,'TurtleBot3');checkControlView(v);await s.shot('name-below-model');return {operation_id:robot().operation_id,view:v};});
 await step('Manual forward backward left right',async()=>{const moves=[];
  for(const direction of ['forward','backward','left','right']){
   const before=structuredClone(robot().pose);const button=drawer().getByRole('button',{name:'Hold '+direction,exact:true});const box=await button.boundingBox();if(!box)throw Error('Pad not visible');
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await sleep(1700);await page.mouse.up();
   await poll(()=>robot()?.control_state==='PAUSED'&&robot().motion_epoch===robot().applied_motion_epoch);checkControlView(await currentControlView(page,'TurtleBot3'));
   moves.push({direction,before,after:structuredClone(robot().pose)});await sleep(600);
  }return moves;});
 await step('LiDAR sensor OFF clears hits and rays',async()=>{
  await drawer().getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await poll(()=>robot()?.lidar_state==='OFF');
  await expect(page.getByText('LiDAR sensor: OFF',{exact:true})).toBeVisible();await expect(page.locator('.robot-lidar-overlay')).toHaveCount(0);await s.shot('lidar-off');await sleep(2000);
  await expect(page.locator('.robot-lidar-overlay')).toHaveCount(0);await drawer().getByRole('button',{name:'Turn LiDAR on',exact:true}).click();await poll(()=>robot()?.lidar_state==='STREAMING');
  await expect(page.locator('.robot-lidar-overlay')).toHaveCount(1);return {off_overlay_count:0};});
 await step('Chat full turn and live SIM scan',async()=>{
  await page.getByRole('combobox',{name:'LiDAR visualization',exact:true}).selectOption('rays');const yaw=robot().pose.position_m[2];
  await send('TurtleBot3 robot one full turn and scan lidar');await poll(()=>robot()?.control_state==='DRIVING');
  await poll(()=>robot()?.reason==='TASK_COMPLETED',35000);const delta=robot().pose.position_m[2]-yaw;if(Math.abs(delta-2*Math.PI)>.01)throw Error('Full turn incomplete');
  await page.getByRole('combobox',{name:'LiDAR visualization',exact:true}).selectOption('points');await s.shot('full-turn-complete');return {delta};});
 for(const kind of ['bed','chair'])await step('Scene destination '+kind+' and visible arrival',async()=>{
  const before=robot().command?.request_id;const text='Go to the nearest '+kind;
  if(kind==='bed'){await drawer().getByRole('textbox',{name:'Robot command',exact:true}).fill(text);await drawer().getByRole('button',{name:'Send command',exact:true}).click();}
  else await send('TurtleBot3 robot '+text.toLowerCase());
  await poll(()=>robot()?.command?.request_id!==before&&robot()?.command?.target_kind===kind);
  await poll(()=>['ARRIVED','FAILED','CANCELLED'].includes(robot()?.command?.state),125000);
  if(robot().command.state!=='ARRIVED')throw Error('Destination did not arrive');
  await expect(drawer().getByLabel('Robot command progress',{exact:true})).toContainText('ARRIVED');await s.shot(kind+'-arrived');await sleep(2000);
  return {command:robot().command,pose:robot().pose,operation_id:robot().operation_id};});
 await step('Stop and LiDAR OFF',async()=>{await page.getByRole('button',{name:'Stop all',exact:true}).click();await poll(()=>robot()?.control_state==='PAUSED');
  await drawer().getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await poll(()=>robot()?.lidar_state==='OFF');await expect(page.locator('.robot-lidar-overlay')).toHaveCount(0);await sleep(2000);await s.shot('stopped-off');});
 result.stop_fence_rejections=[];
 for(const error of s.errors){
  const drive=error.request;
  const stop=drive&&s.fleet_requests.find(row=>row.action==='stop'&&row.status===200&&row.robot_id===drive.robot_id&&row.connection_epoch===drive.connection_epoch&&row.motion_epoch===drive.motion_epoch&&row.order>drive.order&&row.order<drive.response_order&&
    row.result_robots?.some(v=>v.robot_id===drive.robot_id&&v.connection_epoch===drive.connection_epoch&&v.motion_epoch!==drive.motion_epoch&&s.fleet_samples.some(sample=>sample.order>row.order&&
      !s.fleet_requests.some(next=>next.action==='drive'&&next.robot_id===drive.robot_id&&next.order>row.order&&next.order<sample.order)&&
      sample.robots?.some(applied=>applied.robot_id===v.robot_id&&applied.operation_id===v.operation_id&&applied.connection_epoch===v.connection_epoch&&applied.motion_epoch===v.motion_epoch&&applied.applied_motion_epoch===v.motion_epoch&&applied.control_state==='PAUSED'))));
  if(error.status===409&&error.body?.error?.code==='fleet_motion_changed'&&drive?.action==='drive'&&stop)result.stop_fence_rejections.push({error,confirmed_stop:stop,classification:'Old-epoch rejection overlapping exact Stop; engine-applied new epoch confirmed. Not a sole-cause inference.'});
  else throw Error('Unclassified actual demo error: '+JSON.stringify(error));
 }
 result.status='PASS_SEPARATE_FRESH_DEMO';result.operation_id=robot().operation_id;result.video=await s.finishVideo();videoFinished=true;
 const closing=page.waitForEvent('close',{timeout:20000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
}catch(error){result.status='FAIL_DEMO';result.error=String(error).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]');await s.shot('failure').catch(()=>{});if(!videoFinished)await s.finishVideo().catch(()=>{});}
finally{await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,error:result.error,project:result.project}));await s.browser.close();}
if(result.status!=='PASS_SEPARATE_FRESH_DEMO')process.exitCode=1;
