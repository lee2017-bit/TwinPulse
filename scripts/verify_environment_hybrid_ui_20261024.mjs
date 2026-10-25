// SPDX-License-Identifier: Apache-2.0
// Ordinary installed Electron UI journey. No product API writes/interception.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
const [phase,output,project]=process.argv.slice(2);
if(!['fresh','cold'].includes(phase)||!output)throw Error('fresh/cold and new output required');
await fs.mkdir(output,{recursive:false});
const qa=JSON.parse(await fs.readFile('outputs/environment-hybrid-20261024-01/usd-geometry02/result.json','utf8'));
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);
const result={phase,status:'FAIL',scope:'INSTALLED_HYBRID_SCENE_ONLY_NOT_PHOTO_ALIGNMENT_OR_PHYSICAL_QUALIFICATION',steps:[],responses:[],errors:[],hardware_actions:0,provider_calls:0};
const pending=new Set();let finish;
p.on('pageerror',e=>result.errors.push(String(e)));
p.on('response',response=>{
 const task=(async()=>{const u=new URL(response.url()),r=response.request();
  if(!u.pathname.startsWith('/v1/'))return;
  if(!/environment|scene-edit|robot-fleet|conversation/.test(u.pathname)&&response.status()<400)return;
  const row={path:u.pathname,method:r.method(),status:response.status(),at:Date.now()};
  if(r.method()==='POST')try{const body=r.postDataJSON();row.action=body.action;row.request_id=body.request_id;row.robot_id=body.robot_id;
   if(u.pathname==='/v1/product/robot-fleet'&&['stop','stop_all'].includes(body.action))row.request=body;}catch{}
  try{row.body=await response.json();}catch{}result.responses.push(row);
 })();pending.add(task);void task.finally(()=>pending.delete(task));
});
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await p.screenshot({path:path.join(output,name+'.png')});await fs.writeFile(path.join(output,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const step=async(name,work)=>{await work();result.steps.push({name,status:'PASS',at:Date.now()});await save();console.log(name);};
const panel=p.getByRole('region',{name:'Import space',exact:true});
const lastRobot=()=>[...result.responses].reverse().flatMap(r=>r.body?.robots??[]).find(r=>r.label==='Hybrid SIM');
const edit=async(action,trigger)=>{
 const pendingPreview=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action===action);
 await trigger();const previewResponse=await pendingPreview,body=await previewResponse.json();
 if(previewResponse.status()!==200||!body.preview)throw Error('Preview failed: '+JSON.stringify(body));
 const preview=body.preview,op=preview.operation.operation_id;
 await expect(panel.getByRole('region',{name:'Space edit preview'})).toBeVisible();
 const accepted=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/scene-edit/apply'&&r.request().method()==='POST');
 await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();
 const response=await accepted,receipt=await response.json();
 if(response.status()!==202||receipt.operation_id!==op)throw Error('Wrong Apply operation');
 await expect.poll(()=>[...result.responses].reverse().find(r=>r.path==='/v1/product/scene-edit/transaction'&&r.body?.operation_id===op)?.body,{timeout:135000}).toMatchObject({state:'COMMITTED',durable_committed:true,engine_acknowledged:true,current_frame:true,result_revision:preview.result_revision});
 await expect(panel.getByRole('button',{name:'Undo last edit · preview'})).toBeEnabled({timeout:20000});
 result.edits??=[];result.edits.push({action,preview,receipt});return preview;
};
try{
 result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());
 await step('Installed Isaac ready',async()=>await expect(p.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000}));
 if(phase==='fresh'){
  finish=await recordRenderedPage(p,path.join(output,'recording'));
  await step('New chat and original USD import',async()=>{
   await p.getByRole('button',{name:'＋ New chat',exact:true}).click();
   await p.locator('input[type=file]').first().setInputFiles('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd');
   await p.getByRole('button',{name:'Import space',exact:true}).last().click();
   await panel.getByLabel('Space source units',{exact:true}).selectOption('m');
   await panel.getByRole('button',{name:'Inspect space',exact:true}).click();
   await expect(panel.getByText('Inspection ready · review units and objects before import.',{exact:true})).toBeVisible({timeout:110000});
   await panel.getByRole('button',{name:'Import space',exact:true}).click();
   await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible();
   const state=[...result.responses].reverse().find(r=>r.body?.status==='imported'&&r.body?.project_id)?.body;result.project_id=state?.project_id;
  });
 }else{
  await step('Cold saved project reopen',async()=>{
   if(!project)throw Error('Same fresh project id required');result.project_id=project;
   const toggle=p.getByRole('button',{name:'Toggle conversations and projects',exact:true});if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
   await p.getByRole('button',{name:'Open '+project,exact:true}).click();
   const reopen=p.getByRole('button',{name:'Reopen saved scene',exact:true});await reopen.click();await reopen.waitFor({state:'hidden',timeout:45000});
   await p.getByRole('button',{name:'Import space',exact:true}).first().click();
   await expect(panel.getByText('Added obstacles · 1')).toBeVisible();
  });
 }
 await step('Explicit original/mixed Build and current frame',async()=>{
  await panel.getByRole('button',{name:'Show Twin',exact:true}).click();
  await expect(panel.getByText('Build command: succeeded · receipt received',{exact:true})).toBeVisible({timeout:120000});
 });
 if(phase==='fresh'){
  await step('Local photo and estimated obstacle preview Apply',async()=>{
   await panel.getByText('Added obstacles · 0').click();
   await panel.getByLabel('Obstacle reference photo').setInputFiles('C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg');
   await panel.getByLabel('Obstacle name').fill('Basket photo estimate');
   await panel.getByLabel('Obstacle X',{exact:true}).fill(String(qa.obstacle_xy[0]));await panel.getByLabel('Obstacle Y',{exact:true}).fill(String(qa.obstacle_xy[1]));
   await shot('01-photo-reference');
   await edit('add_overlay_preview',()=>panel.getByRole('button',{name:'Preview obstacle',exact:true}).click());
   await expect(panel.getByText('Added obstacles · 1')).toBeVisible();await shot('02-applied-obstacle');
   const source=[...result.responses].reverse().find(r=>r.body?.status==='imported'&&r.body?.objects?.some(o=>o.added))?.body;
   result.added=source?.objects.find(o=>o.added);
   if(source?.source_sha256!==qa.source_sha256||result.added?.evidence?.basis!=='photo_estimate'||result.added.evidence.alignment_verified!==false)throw Error('Missing source/provenance');
  });
  await step('Added prop move and Undo',async()=>{
   await panel.getByLabel('Imported object',{exact:true}).selectOption(result.added.id);
   await panel.getByLabel('Space object move X').fill('.1');
   await edit('move_preview',()=>panel.getByRole('button',{name:'Preview object move',exact:true}).click());
   await edit('undo_preview',()=>panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click());
  });
  await step('Remove added prop and Undo preserves original meshes',async()=>{
   await edit('remove_overlay_preview',()=>panel.getByRole('button',{name:'Remove Basket photo estimate · preview',exact:true}).click());
   await expect(panel.getByText('Added obstacles · 0')).toBeVisible();
   await edit('undo_preview',()=>panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click());
   await expect(panel.getByText('Added obstacles · 1')).toBeVisible();
  });
  await step('Compact English form layouts',async()=>{
   for(const size of [[1280,720],[1024,768]]){await p.setViewportSize({width:size[0],height:size[1]});
    const dimensions=await panel.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));if(dimensions.scroll>dimensions.width+1)throw Error('Horizontal panel overflow');
    result.layouts??=[];result.layouts.push({size,...dimensions});await shot('layout-'+size[0]);}
   await p.setViewportSize({width:1440,height:900});
  });
  await panel.getByRole('button',{name:'Close import space',exact:true}).click();
  await step('SIM Burger selection, Connect, Prepare and LiDAR',async()=>{
   const controlView=p.getByRole('button',{name:'Control view',exact:true});if(await controlView.getAttribute('aria-pressed')!=='true')await controlView.click();
   const toggle=p.getByRole('button',{name:'Toggle conversations and projects',exact:true});if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
   const fleet=p.getByRole('region',{name:'Robot fleet',exact:true});
   await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
   const registration=fleet.locator('details.robot-fleet-register');if(await registration.getAttribute('open')===null)await registration.locator('summary').click();
   await fleet.getByLabel('Name',{exact:true}).fill('Hybrid SIM');
   await fleet.getByLabel('X (m)',{exact:true}).fill(String(qa.robot_pose[0]));await fleet.getByLabel('Y (m)',{exact:true}).fill(String(qa.robot_pose[1]));
   await fleet.getByLabel('Yaw (rad)',{exact:true}).fill('0');await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();
   await fleet.getByRole('button',{name:/Hybrid SIM /}).click();
   const controls=p.getByRole('region',{name:'Control Hybrid SIM',exact:true});
   await controls.getByRole('button',{name:'Connect',exact:true}).click();await expect(controls.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:45000});
   await controls.getByRole('button',{name:'Prepare',exact:true}).click();await expect(controls.getByRole('button',{name:'Hold forward'})).toBeEnabled({timeout:45000});
   await controls.getByRole('button',{name:'Turn LiDAR on'}).click();await expect.poll(()=>lastRobot()?.lidar_state,{timeout:30000}).toBe('STREAMING');
   await p.getByRole('combobox',{name:'LiDAR visualization'}).selectOption('rays');
   await expect.poll(()=>lastRobot()?.scan?.source,{timeout:15000}).toBe('isaac_usd_surface_rays');
   result.scan=lastRobot();await shot('03-burger-and-lidar');
  });
  await step('Finite SIM turn, exact Stop, LiDAR OFF and Disconnect',async()=>{
   const controls=p.getByRole('region',{name:'Control Hybrid SIM',exact:true}),input=controls.getByRole('textbox',{name:'Robot command'});
   await input.fill('Turn left 90 degrees');await p.waitForTimeout(3000);await input.press('Enter');await expect(input).toHaveValue('');
   await expect.poll(()=>lastRobot()?.command?.state,{timeout:30000}).toBe('COMPLETED');result.motion=lastRobot();await shot('04-sim-turn-complete');
   await controls.getByRole('button',{name:'Stop',exact:true}).click();await expect.poll(()=>lastRobot()?.control_state).toBe('PAUSED');
   await controls.getByRole('button',{name:'Turn LiDAR off'}).click();await expect.poll(()=>({state:lastRobot()?.lidar_state,scan:lastRobot()?.scan})).toEqual({state:'OFF',scan:null});
   await controls.getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>lastRobot()?.connection_state).toBe('DISCONNECTED');
  });
 }else{
  await panel.getByText('Added obstacles · 1').click();await expect(panel.getByText(/Reference: KakaoTalk_20261023_001642352.jpg/)).toBeVisible();
  await shot('cold-saved-overlay');await panel.getByRole('button',{name:'Close import space',exact:true}).click();
  await step('Cold SIM requires explicit Connect; enlarged current model and LiDAR',async()=>{
   const controlView=p.getByRole('button',{name:'Control view',exact:true});if(await controlView.getAttribute('aria-pressed')!=='true')await controlView.click();
   const fleet=p.getByRole('region',{name:'Robot fleet',exact:true});await fleet.getByRole('button',{name:/Hybrid SIM /}).click();
   const controls=p.getByRole('region',{name:'Control Hybrid SIM',exact:true});
   await expect(controls.getByRole('button',{name:'Connect',exact:true})).toBeEnabled();
   result.no_restored_connection=lastRobot()?.connection_state;
   await controls.getByRole('button',{name:'Connect',exact:true}).click();await expect(controls.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:45000});
   await controls.getByRole('button',{name:'Prepare',exact:true}).click();await expect(controls.getByRole('button',{name:'Hold forward'})).toBeEnabled({timeout:45000});
   await controls.getByRole('button',{name:'Turn LiDAR on'}).click();await expect.poll(()=>lastRobot()?.lidar_state,{timeout:20000}).toBe('STREAMING');
   await p.getByRole('combobox',{name:'LiDAR visualization'}).selectOption('rays');
   const details=p.locator('details.twin-display-details');if(await details.getAttribute('open')===null)await details.locator('summary').click();
   for(let i=0;i<4;i++){const zoom=p.getByRole('button',{name:'Zoom in',exact:true});await expect(zoom).toBeEnabled();await zoom.click();await p.waitForTimeout(500);}
   await details.locator('summary').click();await p.waitForTimeout(1000);await shot('05-enlarged-burger-lidar');result.cold_scan=lastRobot();
   await controls.getByRole('button',{name:'Stop',exact:true}).click();await expect.poll(()=>lastRobot()?.control_state).toBe('PAUSED');
   await controls.getByRole('button',{name:'Turn LiDAR off'}).click();await expect.poll(()=>({state:lastRobot()?.lidar_state,scan:lastRobot()?.scan})).toEqual({state:'OFF',scan:null});
   await controls.getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>lastRobot()?.connection_state).toBe('DISCONNECTED');
  });
 }
 if(result.errors.length)throw Error('Renderer error');
 await Promise.all([...pending]);
 if(result.responses.some(r=>r.status>=400))throw Error('Retained HTTP failure');
 result.status='PASS_SCOPED';if(finish){result.recording=await finish();finish=null;}await save();
 await p.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await p.waitForEvent('close',{timeout:60000});result.exit='WINDOW_CLOSED';await save();
}catch(error){result.errors.push(String(error));await shot('failure').catch(()=>{});if(finish){result.recording=await finish().catch(e=>({error:String(e)}));finish=null;}await Promise.all([...pending]);await save();throw error;}
finally{await browser.close();}
