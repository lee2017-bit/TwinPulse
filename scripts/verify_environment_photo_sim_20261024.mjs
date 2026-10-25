// SPDX-License-Identifier: Apache-2.0
// Real installed SIM UI. No model dispatch/API writes, no physical selection.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
const [out,mode,poseFile,label='Photo SIM']=process.argv.slice(2);if(!out||mode&&!['reuse','focus','focus-new','wide'].includes(mode))throw Error('new output and optional reuse/focus/wide required');await fs.mkdir(out,{recursive:false});
const pose=poseFile?JSON.parse(await fs.readFile(poseFile,'utf8')).robot_pose:[-4.15,-.45,0];
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222'),pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('One installed renderer required');const p=pages[0];p.setDefaultTimeout(30000);
const result={status:'FAIL',scope:'SIM_ONLY_DETERMINISTIC_TEST_PLACEMENT_NOT_PHOTO_OR_PHYSICAL_WORLD_ALIGNMENT',steps:[],responses:[],errors:[],hardware_actions:0,model_calls:0};
const pending=new Set();let finish;
result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
p.on('pageerror',e=>result.errors.push(String(e)));
p.on('response',r=>{const task=(async()=>{const u=new URL(r.url()),q=r.request();if(!/^\/v1\/product\/(robot-fleet|viewport|environment|scene-edit)/.test(u.pathname))return;
 const row={path:u.pathname,method:q.method(),status:r.status(),at:Date.now()};
 if(u.pathname==='/v1/product/viewport/current')try{row.viewport=JSON.parse(r.headers()['x-twinpulse-viewport']);}catch{}
 if(q.method()==='POST')try{row.request=q.postDataJSON();}catch{}
 try{if(!/image|frame$/.test(u.pathname))row.body=await r.json();}catch{}result.responses.push(row);
 })();pending.add(task);void task.finally(()=>pending.delete(task));});
const robot=()=>[...result.responses].reverse().flatMap(r=>r.body?.robots??[]).find(r=>r.label===label);
const shot=async name=>{await p.screenshot({path:path.join(out,name+'.png')});await fs.writeFile(path.join(out,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const step=async(name,fn)=>{await fn();result.steps.push({name,status:'PASS',at:Date.now()});await save();console.log(name);};
try{
 await p.setViewportSize({width:1440,height:900});finish=await recordRenderedPage(p,path.join(out,'recording'));
 const panel=p.getByRole('region',{name:'Import space',exact:true});if(await panel.isVisible())await panel.getByRole('button',{name:'Close import space',exact:true}).click();
 const control=p.getByRole('button',{name:'Control view',exact:true});if(await control.getAttribute('aria-pressed')!=='true')await control.click();
 const toggle=p.getByRole('button',{name:'Toggle conversations and projects',exact:true});if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
 const fleet=p.getByRole('region',{name:'Robot fleet',exact:true});
 if(!mode||mode==='focus-new')await step('Explicit TurtleBot3 SIM registration at test pose',async()=>{
  await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();const registration=fleet.locator('details.robot-fleet-register');
  if(await registration.getAttribute('open')===null)await registration.locator('summary').click();
  const model=fleet.getByText('Model: TurtleBot3 Burger (built-in SIM model). The name is only a label.',{exact:true});await expect(model).toBeVisible();result.registration_model=await model.innerText();
  await fleet.getByLabel('Name',{exact:true}).fill(label);await fleet.getByLabel('X (m)',{exact:true}).fill(String(pose[0]));await fleet.getByLabel('Y (m)',{exact:true}).fill(String(pose[1]));await fleet.getByLabel('Yaw (rad)',{exact:true}).fill(String(pose[2]));
  await p.waitForTimeout(3000);await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();await fleet.getByRole('button',{name:new RegExp(label+' ')}).click();
  await shot('01-registered-sim');
 });
 else await step('Saved SIM selected without restoring connection authority',async()=>{
  await fleet.getByRole('button',{name:new RegExp(label+' ')}).click();await expect(p.getByRole('region',{name:'Control '+label,exact:true}).getByRole('button',{name:'Connect',exact:true})).toBeEnabled();
  result.restored_robot=robot();
 });
 const manage=fleet.getByRole('button',{name:'Manage robot fleet',exact:true});if(await manage.getAttribute('aria-expanded')==='true')await manage.click();
 const controls=p.getByRole('region',{name:'Control '+label,exact:true});
 await step('SIM Connect Prepare LiDAR and visible composed sensor first hit',async()=>{
  await controls.getByRole('button',{name:'Connect',exact:true}).click();await expect(controls.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:45000});
  await controls.getByRole('button',{name:'Prepare',exact:true}).click();await expect(controls.getByRole('button',{name:'Hold forward'})).toBeEnabled({timeout:45000});
  await controls.getByRole('button',{name:'Turn LiDAR on'}).click();await expect.poll(()=>robot()?.lidar_state,{timeout:30000}).toBe('STREAMING');
  await p.getByRole('combobox',{name:'LiDAR visualization'}).selectOption('rays');await expect.poll(()=>robot()?.scan?.source,{timeout:20000}).toBe('isaac_usd_surface_rays');
  result.scan=robot();
  const details=p.locator('details.twin-display-details');if(await details.getAttribute('open')===null)await details.locator('summary').click();
  const camera=async(name)=>{const b=p.getByRole('button',{name,exact:true});await expect(b).toBeEnabled();await b.click();await p.waitForTimeout(700);};
  if(mode==='wide'){for(let i=0;i<4;i++)await camera('Zoom out');}
  else{
  await camera('Top view');
  await shot('02a-top-before-pan');await camera('Orbit right');await shot('02b-oblique-return');await camera('Top view');
  if(mode!=='focus-new'){
   for(let i=0;i<7;i++)await camera('Pan left');
   for(let i=0;i<3;i++)await camera('Zoom in');
  }
  if(mode==='focus'||mode==='focus-new'){
   const anchor=()=>[...result.responses].reverse().find(r=>r.viewport?.frame?.robot_anchors?.some(a=>a.robot_id===robot()?.robot_id))?.viewport.frame.robot_anchors.find(a=>a.robot_id===robot()?.robot_id);
   for(let i=0;i<48;i++){const a=anchor();if(!a)throw Error('No bound current robot envelope');const x=(a.screen_bounds_uv[0]+a.screen_bounds_uv[2])/2;
    if(Math.abs(x-.5)<.01)break;await camera(x<.5?'Pan left':'Pan right');}
   for(let i=0;i<48;i++){const a=anchor();if(!a)throw Error('No bound current robot envelope');const y=(a.screen_bounds_uv[1]+a.screen_bounds_uv[3])/2;
    if(Math.abs(y-.5)<.015)break;await camera(y<.5?'Pan up':'Pan down');}
   for(let i=0;i<18;i++){const a=anchor();if(!a)throw Error('No current model envelope');
    if(a.screen_bounds_uv[2]-a.screen_bounds_uv[0]>(mode==='focus-new'?.06:.10))break;await camera('Zoom in');}
   result.final_anchor=anchor();
  }
  }
  await details.locator('summary').click();await p.waitForTimeout(1500);await shot('02-enlarged-model-lidar');
 });
 await step(mode==='wide'?'Camera inspection only and exact Stop OFF Disconnect':'Finite SIM turn and exact Stop OFF Disconnect',async()=>{
  if(mode!=='wide'){
  const input=controls.getByRole('textbox',{name:'Robot command'});await input.fill('Turn left 90 degrees');await p.waitForTimeout(3000);await input.press('Enter');await expect(input).toHaveValue('');
  await expect.poll(()=>robot()?.command?.state,{timeout:30000}).toBe('COMPLETED');result.motion=robot();await shot('03-turn-complete');
  }
  result.before_stop=robot();
  const stopResponse=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='stop');
  await controls.getByRole('button',{name:'Stop',exact:true}).click();
  const stopped=await stopResponse,request=stopped.request().postDataJSON(),body=await stopped.json();
  const accepted=body.robots.find(r=>r.robot_id===result.before_stop.robot_id),ack=body.last_command;
  if(stopped.status()!==200||ack?.request_id!==request.request_id||ack?.robot_id!==result.before_stop.robot_id||ack?.status!=='accepted'||
     !accepted?.motion_epoch||accepted.motion_epoch===request.motion_epoch||request.motion_epoch!==result.before_stop.motion_epoch||
     accepted.connection_epoch!==request.connection_epoch||request.connection_epoch!==result.before_stop.connection_epoch)
    throw Error('Exact Stop request and changed ACK epoch missing');
  result.stop_receipt={request,status:stopped.status(),revision:body.revision,ack,accepted};
  await expect.poll(()=>{const current=robot();return !!current&&current.robot_id===accepted.robot_id&&current.connection_epoch===accepted.connection_epoch&&
   current.motion_epoch===accepted.motion_epoch&&current.applied_motion_epoch===accepted.motion_epoch&&current.control_state==='PAUSED';},{timeout:30000}).toBe(true);
  result.stop=robot();
  await controls.getByRole('button',{name:'Turn LiDAR off'}).click();await expect.poll(()=>({state:robot()?.lidar_state,scan:robot()?.scan})).toEqual({state:'OFF',scan:null});await shot('04-lidar-off');result.off=robot();
  await controls.getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>robot()?.connection_state).toBe('DISCONNECTED');
 });
 if(result.errors.length||result.responses.some(r=>r.status>=400))throw Error('Retained renderer/HTTP failure');result.status='PASS_SCOPED';
}catch(e){result.errors.push(String(e));await shot('failure').catch(()=>{});}
finally{await Promise.all([...pending]);if(finish)result.recording=await finish().catch(e=>({error:String(e)}));await save();await browser.close();}
if(result.status!=='PASS_SCOPED')throw Error(result.errors.join('\n'));
