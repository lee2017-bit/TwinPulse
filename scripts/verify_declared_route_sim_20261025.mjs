// SPDX-License-Identifier: Apache-2.0
// Path B SIM journey in the ordinary installed renderer: existing imported
// RoomPlan Twin -> SIM robot -> "survey the room and come back" -> Run route
// card -> finite moves -> return. No interception, injected state, direct
// product API writes or physical robot actions.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
const [output,endpoint,label='PathB SIM 01',poseArg='1.4725,1.0526,-0.8204']=process.argv.slice(2);
if(!output||!endpoint)throw Error('usage: <new output dir> <cdp endpoint> [label] [x,y,yaw]');
await fs.mkdir(output,{recursive:false});
const pose=poseArg.split(',').map(Number);
const b=await chromium.connectOverCDP(endpoint);
const pages=b.contexts().flatMap(c=>c.pages()).filter(p=>/^http:\/\/127\.0\.0\.1:\d+\//.test(p.url()));
if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);let lastFleet,lastConversation,finish;
const result={status:'FAIL',steps:[],errors:[],requests:[],physical_actions:0,label,pose,
 scope:'INSTALLED_SIM_DECLARED_ROUTE_NOT_PHYSICAL_NOT_LOCALIZATION'};
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await p.screenshot({path:path.join(output,name+'.png')});await fs.writeFile(path.join(output,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const step=async(name,fn)=>{await fn();result.steps.push({name,at:Date.now(),status:'PASS'});await save();console.log('PASS',name);};
const robot=()=>lastFleet?.robots?.find(r=>r.label===label);
const events=()=>lastConversation?.events??[];
p.on('pageerror',e=>result.errors.push(String(e)));
p.on('response',async r=>{const url=new URL(r.url());
 if(!['/v1/product/conversation','/v1/product/robot-fleet'].includes(url.pathname))return;
 let data;try{data=await r.json();}catch{return;}
 if(url.pathname.endsWith('robot-fleet'))lastFleet=data;else lastConversation=data;
 if(r.request().method()==='POST'){const q=r.request().postDataJSON();
  if(lastFleet?.robots?.some(x=>x.robot_id===q?.robot_id&&x.kind==='physical'))result.physical_actions++;
  result.requests.push({path:url.pathname,status:r.status(),request:q,error:data.error??null});}});
const fleet=p.getByRole('region',{name:'Robot fleet',exact:true}),control=p.getByRole('region',{name:'Control '+label,exact:true});
try{
 result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());await p.setViewportSize({width:1440,height:1000});
 finish=await recordRenderedPage(p,path.join(output,'recording'));
 await step('Imported Twin is the current navigation map',async()=>{
  await expect.poll(()=>lastFleet?.navigation_scene?.status,{timeout:60000}).toBe('AVAILABLE');
  if(lastFleet.navigation_scene.kind!=='imported')throw Error('Imported RoomPlan scene required, got '+lastFleet.navigation_scene.kind);
  result.navigation_scene=lastFleet.navigation_scene;await shot('00-imported-twin');});
 await step('Register or select the SIM robot at the start pose',async()=>{
  if(!await fleet.getByRole('button',{name:new RegExp(label+' SIM ')}).count()){
   await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
   const registration=fleet.locator('details.robot-fleet-register');if(await registration.getAttribute('open')===null)await registration.locator('summary').click();
   await fleet.getByLabel('Name',{exact:true}).fill(label);await fleet.getByLabel('X (m)',{exact:true}).fill(String(pose[0]));
   await fleet.getByLabel('Y (m)',{exact:true}).fill(String(pose[1]));await fleet.getByLabel('Yaw (rad)',{exact:true}).fill(String(pose[2]));
   await shot('01-registration');await p.waitForTimeout(2000);await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();
   await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();}
  await fleet.getByRole('button',{name:new RegExp(label+' SIM ')}).click();await expect(control).toBeVisible();
  await expect.poll(()=>robot()?.kind).toBe('sim');});
 await step('Connect and Prepare the SIM robot',async()=>{
  if(robot()?.connection_state!=='CONNECTED'){await control.getByRole('button',{name:'Connect',exact:true}).click();
   await expect(control.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:60000});await control.getByRole('button',{name:'Prepare',exact:true}).click();}
  await expect.poll(()=>robot()?.control_state,{timeout:60000}).toMatch(/READY|PAUSED/);result.start=robot();});
 const text='Survey the room and come back';
 await step('Type the request; Run route card shows the planned moves',async()=>{
  const input=control.getByRole('textbox',{name:'Robot command'});await input.fill(text);await p.waitForTimeout(3000);await input.press('Enter');
  await expect(p.getByRole('radio',{name:'Run route',exact:true})).toBeVisible({timeout:60000});
  result.planned=events().filter(e=>e.type==='declared_route_planned').at(-1)?.payload??null;
  if(!result.planned?.steps?.length)throw Error('No planned steps recorded');await shot('02-route-card');});
 await step('Run route; every move completes and the robot returns',async()=>{
  await p.getByRole('radio',{name:'Run route',exact:true}).check();await p.getByRole('button',{name:'Continue',exact:true}).click();
  const timeout=60000+result.planned.steps.length*30000;
  await expect.poll(()=>events().filter(e=>e.type==='declared_route_finished').at(-1)?.payload?.plan_id,{timeout,intervals:[2000]}).toBe(result.planned.plan_id);
  result.finished=events().filter(e=>e.type==='declared_route_finished').at(-1).payload;result.end=robot();
  await shot('03-route-finished');
  if(result.finished.state!=='COMPLETED')throw Error('Route '+result.finished.state+': '+result.finished.reason);
  const a=result.start.pose.position_m,c=result.end.pose.position_m;
  result.return_error_m=Math.hypot(a[0]-c[0],a[1]-c[1]);result.return_yaw_error_rad=Math.abs(Math.atan2(Math.sin(a[2]-c[2]),Math.cos(a[2]-c[2])));});
 result.status=result.physical_actions?'FAIL_PHYSICAL_ACTION':'PASS';
}catch(error){result.errors.push(String(error?.stack??error));await shot('failure').catch(()=>{});}
finally{if(finish)result.recording=await finish().catch(e=>String(e));await save();await b.close();console.log('STATUS',result.status);}
