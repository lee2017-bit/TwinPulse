// SPDX-License-Identifier: Apache-2.0
// Targeted read-only receipt instrumentation around real public-UI SIM turns.
// Not a new-generation/cold acceptance replacement and never a physical call.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import {currentControlView} from './control_view_acceptance.mjs';
const out=process.argv[2],project=process.argv[3];if(!out||!project)throw Error('New output and explicit project required');
await fs.mkdir(out,{recursive:false});
const result={classification:'TARGETED_EXISTING_SCENE_SIM_DIAGNOSTIC_NOT_FRESH_ACCEPTANCE',project,status:'IN_PROGRESS',metadata:[],packets:[],displays:[],fleet:[],turns:[],errors:[],mutations:[]};
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');let page,latest;
const save=()=>fs.writeFile(out+'/result.json',JSON.stringify(result,null,2));
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One actual installed renderer required');[page]=pages;page.setDefaultTimeout(25000);
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());await page.setViewportSize({width:1600,height:900});const pending=[];
 page.on('request',r=>{if(r.method()==='POST'){let b;try{b=r.postDataJSON();}catch{}result.mutations.push({at:Date.now(),path:new URL(r.url()).pathname,action:b?.action,request_id:b?.request_id});}});
 page.on('response',r=>pending.push((async()=>{
  const p=new URL(r.url()).pathname,at=Date.now();
  if(p==='/v1/product/viewport'&&r.status()===200){const v=await r.json();result.metadata.push({at,frame_id:v.frame?.frame_id,captured_at_ms:v.frame?.captured_at_ms,state:v.state,scene:v.frame?.applied_revision,stage:v.frame?.stage_epoch,last_id:v.last_frame?.frame_id});}
  if(p==='/v1/product/viewport/current'&&r.status()===200){const v=JSON.parse(r.headers()['x-twinpulse-viewport']??'null');result.packets.push({at,frame_id:v?.frame?.frame_id,captured_at_ms:v?.frame?.captured_at_ms,scene:v?.frame?.applied_revision,stage:v?.frame?.stage_epoch});}
  if(p==='/v1/product/robot-fleet'&&r.status()===200){latest=await r.json();result.fleet.push({at,robots:latest.robots.filter(x=>['Alpha','Beta'].includes(x.label)).map(x=>({label:x.label,operation_id:x.operation_id,connection_state:x.connection_state,motion_epoch:x.motion_epoch,applied_motion_epoch:x.applied_motion_epoch,control_state:x.control_state,reason:x.reason,pose:x.pose,sequence:x.telemetry_sequence}))});}
 })().catch(e=>result.errors.push({at:Date.now(),kind:'read_only_response_observer',error:String(e)}))));
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 await page.getByRole('button',{name:'Open '+project,exact:true}).click();await expect(page.locator('.chat-project-caption')).toContainText(project);
 const show=page.getByRole('button',{name:'Show Twin',exact:true});if(await show.isVisible())await show.click();
 const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true}),current=page.getByRole('button',{name:'Current Twin and SIM controls',exact:true});
 await expect.poll(async()=>await reopen.isVisible()||await current.isVisible(),{timeout:25000}).toBe(true);
 if(await reopen.isVisible())await reopen.click();
 await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();await page.getByRole('button',{name:'View current Twin',exact:true}).click();
 await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
 const view=page.getByRole('button',{name:'Control view',exact:true});if(await view.getAttribute('aria-pressed')!=='true')await view.click();
 for(const name of ['Alpha','Beta']){
  await expect.poll(()=>latest?.robots.find(x=>x.label===name)?.kind).toBe('sim');
  await page.locator('.robot-fleet-row').filter({has:page.getByText(name,{exact:true})}).click();const d=page.getByRole('region',{name:'Control '+name,exact:true});
  await d.getByRole('button',{name:'Connect',exact:true}).click();await expect.poll(()=>latest?.robots.find(x=>x.label===name)?.connection_state).toBe('CONNECTED');
  await d.getByRole('button',{name:'Prepare',exact:true}).click();
 }
 await page.locator('.robot-fleet-row').filter({has:page.getByText('Alpha',{exact:true})}).click();
 for(let i=0;i<3;i++){
  console.log('PROBE_SINGLE_360_TURN '+i);const before=latest.robots.find(x=>x.label==='Alpha');
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Alpha 로봇 한바퀴 돌면서 라이다 기록해');await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect.poll(()=>latest?.robots.find(x=>x.label==='Alpha')?.control_state,{timeout:15000}).toBe('DRIVING');
  if(i===0)await page.screenshot({path:out+'/first-turn-observation.png'});
  const began=Date.now(),samples=[];
  do{const display=await currentControlView(page,'Alpha');samples.push(display);result.displays.push(display);await page.waitForTimeout(200);
   if(Date.now()-began>35000)throw Error('Original single-turn35s diagnostic deadline exceeded');
  }while(latest?.robots.find(x=>x.label==='Alpha')?.reason!=='TASK_COMPLETED');
  const after=latest.robots.find(x=>x.label==='Alpha');
  result.turns.push({index:i,began,ended:Date.now(),delta_rad:after.pose.position_m[2]-before.pose.position_m[2],operation_id:after.operation_id,
   samples:samples.length,maximum_display_age_ms:Math.max(...samples.map(s=>s.frame_age_ms)),stale_samples:samples.filter(s=>s.frame_age_ms>=1000||!s.live).length});
  await page.getByRole('button',{name:'Stop all',exact:true}).click();await page.waitForTimeout(1000);await save();
 }
 if(result.mutations.some(x=>x.path==='/v1/product/robot-fleet'&&['field_arm','field_trial','field_prepare','set_twin_pose'].includes(x.action)))throw Error('Unexpected physical/setup action');
 await page.screenshot({path:out+'/probe-finished.png'});const closing=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
 await Promise.all(pending);result.status='DIAGNOSTIC_COMPLETED_NOT_FRESH_OR_PHYSICAL_PASS';
}catch(e){result.status='DIAGNOSTIC_FAILED';result.error=String(e);if(page&&!page.isClosed())await page.screenshot({path:out+'/failure.png'}).catch(()=>{});}
finally{await save();await browser.close();}
console.log(JSON.stringify({status:result.status,turns:result.turns,error:result.error}));if(result.status==='DIAGNOSTIC_FAILED')process.exitCode=1;
