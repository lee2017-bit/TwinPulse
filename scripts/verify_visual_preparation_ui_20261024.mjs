// SPDX-License-Identifier: Apache-2.0
// Actual installed BrowserWindow public UI; no interception or API mutations.
import {expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
import {currentControlView,checkControlView} from './control_view_acceptance.mjs';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const [phase,out]=process.argv.slice(2);
if(!['marker','restore','extra','cleanup'].includes(phase)||!out)throw Error('Explicit phase/new output required');
const u=await attachPoweredSession(out,'http://127.0.0.1:19222',{interactive:true}),p=u.page;
p.setDefaultTimeout(15000);
const label='Imported existing settings · unverified',project='chat_mvki3gm9_e212190a';
const control=name=>p.getByRole('region',{name:'Control '+name,exact:true});
const row=name=>u.fleet?.robots.find(r=>r.label===name);
const step=async(name,run)=>{const evidence=await run();await u.note(name,{status:'PASS',...evidence});};
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const choose=async name=>{await p.locator('.robot-fleet-row').filter({hasText:name}).click();await control(name).waitFor();};
async function stop(name){
 const before=row(name);const pending=p.waitForResponse(r=>{try{return new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON().action==='stop'&&r.request().postDataJSON().robot_id===before.robot_id;}catch{return false;}});
 await control(name).getByRole('button',{name:'Stop',exact:true}).click();const response=await pending,body=await response.json(),after=body.robots.find(r=>r.robot_id===before.robot_id);
 if(response.status()!==200||after.operation_id!==before.operation_id||after.connection_epoch!==before.connection_epoch||after.motion_epoch===before.motion_epoch)throw Error('Exact Stop missing');
 await expect.poll(()=>row(name)?.applied_motion_epoch).toBe(after.motion_epoch);
 return {request:response.request().postDataJSON(),receipt:after,engine_ack:row(name)};
}
try{
 await expect(p.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 if(phase==='marker'||phase==='restore'){
  if(await p.getByRole('button',{name:'Toggle conversations and projects'}).getAttribute('aria-expanded')!=='true')await p.getByRole('button',{name:'Toggle conversations and projects'}).click();
  if((await p.getByRole('banner').innerText()).includes(project)){
   await p.getByRole('button',{name:'＋ New chat',exact:true}).click();await expect.poll(async()=>!(await p.getByRole('banner').innerText()).includes(project)).toBe(true);
  }
  await p.getByRole('button',{name:'Open '+project,exact:true}).click();
  const reopen=p.getByRole('button',{name:'Reopen saved scene',exact:true});
  await reopen.waitFor({timeout:35000});await reopen.click();await reopen.waitFor({state:'hidden',timeout:35000});
  await p.getByRole('button',{name:'Import space',exact:true}).first().click();
  const panel=p.getByRole('region',{name:'Import space',exact:true});
  await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible({timeout:20000});
  await panel.getByRole('button',{name:'Show Twin',exact:true}).click();
  await expect(panel.getByText('Build command: succeeded · receipt received',{exact:false})).toBeVisible({timeout:120000});
  await panel.getByRole('button',{name:'Close import space',exact:true}).click();
  if(await p.getByRole('button',{name:'Control view',exact:true}).getAttribute('aria-pressed')!=='true')await p.getByRole('button',{name:'Control view',exact:true}).click();
  if(await p.getByRole('button',{name:'Toggle conversations and projects'}).getAttribute('aria-expanded')==='true')await p.getByRole('button',{name:'Toggle conversations and projects'}).click();
  await choose(label);
  if(phase==='marker')await step('Offline physical model placement',async()=>{
   await control(label).getByRole('button',{name:'Set position',exact:true}).click();
   for(const [name,value] of [['Marker X (m)','2.25'],['Marker Y (m)','0.95'],['Marker yaw (rad)','0']])await p.getByLabel(name,{exact:true}).fill(value);
   await p.getByRole('button',{name:'Place estimated robot marker',exact:true}).click();
   await p.getByRole('button',{name:'Hide position',exact:true}).click();
   await expect(p.getByText('Robot model visible · estimated',{exact:true})).toBeVisible();
   return {position_m:row(label).display_pose.position_m,not_localized:true};
  });
  if(phase==='restore')await step('Cold estimated marker and no physical authority',async()=>{
   await expect.poll(()=>!!row(label)?.display_pose).toBe(true);const r=row(label);
   if(JSON.stringify(r.display_pose.position_m)!=='[2.25,0.95,0]'||r.connection_state!=='DISCONNECTED'||r.operation_id||r.connection_epoch||r.capabilities.drive)throw Error('Cold marker or authority mismatch');
   await expect(p.getByText('Robot model visible · estimated',{exact:true})).toBeVisible();
   return {robot:r,placement_writes:u.fleet_requests.filter(q=>q.action==='set_twin_pose').length};
  });
  await step('Physical sensor panel disconnected',async()=>{
   const panel=p.getByRole('complementary',{name:'Physical robot and LiDAR'});await expect(panel).toContainText('Disconnected · no live scan');
   const a=await panel.locator('svg').count(),b=await p.getByRole('combobox',{name:'LiDAR visualization'}).count();
   if(a||b)throw Error('Old/Sim scan shown for disconnected physical robot');
   return {text:await panel.innerText(),physical_scan_svg_count:a,sim_visualization_selector_count:b};
  });
  // Existing camera controls only. This is a display estimate, never a teleport.
  await p.locator('details.twin-display-details > summary').click();
  for(const action of [...Array(9).fill('Zoom in'),'Pan right','Pan right','Pan up','Pan up','Pan up']){
   const button=p.getByRole('button',{name:action,exact:true});await expect(button).toBeEnabled();await button.click();await p.waitForTimeout(400);
  }
  await p.locator('details.twin-display-details > summary').click();
  await step('Unclipped physical controls at both sizes',async()=>{
   const samples=[];for(const size of [{width:1280,height:720},{width:1600,height:900}]){
    await p.setViewportSize(size);await p.waitForTimeout(1200);const view=await currentControlView(p,label);checkControlView(view);samples.push(view);await u.shot('layout-'+size.width+'x'+size.height);
   }return {samples};
  });
  const view=await currentControlView(p,label);checkControlView(view);await u.shot('body-for-review');
  await u.note('Physical model body captured',{status:'PASS',view,screenshot:'body-for-review.png',needs_visual_review:true});
  if(phase==='restore')await step('Original failed physical history preserved',async()=>{
   const original=JSON.parse(await fs.readFile('outputs/robot-powered-roomplan-20261023-01/ui-retry09/live-final/operation-final.json','utf8'));
   await control(label).getByRole('button',{name:'Operation logs',exact:true}).click();
   const summary=control(label).getByLabel('Operation summary');await expect(summary).toContainText('FIELD_DIRECTION_COVERAGE_GAP');
   const button=p.getByRole('button',{name:'Download operation JSON',exact:true});
   await u.download(button,'original-physical-operation.json');const actual=JSON.parse(await fs.readFile(out+'/original-physical-operation.json','utf8'));
   if(actual.operation_id!==original.operation_id||hash(actual.events)!==hash(original.events)||hash(actual.manifest.stream)!==hash(original.manifest.stream)||actual.manifest.cleanup_confirmed!==original.manifest.cleanup_confirmed)throw Error('Original physical history changed');
   return {operation_id:actual.operation_id,events_sha256:hash(actual.events),stream_sha256:hash(actual.manifest.stream),original_failure:'FIELD_DIRECTION_COVERAGE_GAP',physical_authority_restored:false};
  });
  if(phase==='restore')await step('Exact original pause in read-only timeline',async()=>{
   const summary=control(label).getByLabel('Operation summary');await summary.locator('details > summary').filter({hasText:'Physical runtime evidence'}).click();
   const receipt=await u.download(summary.getByRole('button',{name:'Download events-00014.jsonl',exact:true}),'events-00014.jsonl');
   const expected='26600372789497ae6f22dea4f08b75fed35169c63a007c7b6540ff9c99796b5c';if(receipt.sha256!==expected)throw Error('Original failed segment differs');
   const pause=JSON.parse((await fs.readFile(out+'/events-00014.jsonl','utf8')).split('\n')[545]);
   if(pause.sequence!==22669||pause.kind!=='control_pause'||pause.operation_id!=='490bf6806c064797b087177aef632f8e'||pause.data.reason!=='FIELD_DIRECTION_COVERAGE_GAP')throw Error('Exact original pause not found');
   const timeline=control(label).getByLabel('Robot diagnostic timeline');await timeline.locator(':scope > summary').click();await timeline.getByLabel('Open recorded JSON / JSONL locally (one segment, up to 8 MiB)').setInputFiles(out+'/events-00014.jsonl');
   await expect(timeline).toContainText('Exact segment SHA and byte count match the operation manifest');await timeline.getByLabel('Recorded category').selectOption('stop');
   // The bounded table previews only four values; a later heartbeat can expose
   // the same wheel reason while the original control_pause previews delivery
   // timing. Select its immutable original source order, not a matching reason.
   const target=timeline.getByRole('table',{name:'Recorded diagnostic events'}).getByRole('row').filter({has:p.getByRole('button',{name:'#546',exact:true})});await expect(target).toContainText('control_pause');await target.getByRole('button',{name:'#546',exact:true}).click();
   const selected=timeline.getByRole('region',{name:'Selected recorded diagnostic'});await expect(selected).toContainText('22669');await expect(selected).toContainText(pause.data.pause_id);await expect(selected).toContainText(pause.connection_epoch);await expect(selected).toContainText('FIELD_DIRECTION_COVERAGE_GAP');await u.shot('original-pause-selected');
   return {operation_id:pause.operation_id,connection_epoch:pause.connection_epoch,source_segment_sha256:receipt.sha256,source_line:546,sequence:pause.sequence,pause_id:pause.data.pause_id,reason:pause.data.reason,physical_actions:0,source:'Original segment read locally through existing diagnostic UI; not reconstructed from summary or inferred scan'};
  });
 }
 if(phase==='extra'){
  const fleet=p.getByRole('region',{name:'Robot fleet',exact:true}),suffix=out.split(/[\\/]/).at(-1),names=['Visual Alpha '+suffix,'Visual Beta '+suffix];
  await step('Two SIM connections and independent sensors',async()=>{
   if(await fleet.getByRole('button',{name:'Manage robot fleet'}).getAttribute('aria-expanded')!=='true')await fleet.getByRole('button',{name:'Manage robot fleet'}).click();
   for(const [i,name] of names.entries()){
    const form=fleet.locator('details.robot-fleet-register');if(await form.getAttribute('open')===null)await form.locator('summary').click();
    await fleet.getByLabel('Name',{exact:true}).fill(name);await fleet.getByLabel('X (m)',{exact:true}).fill(String(2.25+i*.45));await fleet.getByLabel('Y (m)',{exact:true}).fill('.95');await fleet.getByLabel('Yaw (rad)',{exact:true}).fill('0');
    await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();await choose(name);await control(name).getByRole('button',{name:'Connect',exact:true}).click();
    await expect(control(name).getByRole('button',{name:'Prepare',exact:true})).toBeEnabled();await control(name).getByRole('button',{name:'Prepare',exact:true}).click();await expect(control(name).getByRole('button',{name:'Hold left',exact:true})).toBeEnabled();
    await control(name).getByRole('button',{name:'Turn LiDAR on',exact:true}).click();await expect.poll(()=>row(name)?.lidar_state).toBe('STREAMING');
   }
   const robots=names.map(row);if(robots.some(r=>r.kind!=='sim'||r.connection_state!=='CONNECTED'||!r.scan?.points?.length)||robots[0].connection_epoch===robots[1].connection_epoch)throw Error('Two independent SIMs missing');
   return {robots};
  });
  await choose(names[0]);if(await fleet.getByRole('button',{name:'Manage robot fleet'}).getAttribute('aria-expanded')==='true')await fleet.getByRole('button',{name:'Manage robot fleet'}).click();
  await step('Keyboard and bounded 90 degree command',async()=>{
   const before=structuredClone(row(names[0])),requestStart=u.fleet_requests.length,pad=control(names[0]).getByRole('group',{name:'Hold to drive'});await pad.focus();await p.keyboard.down('ArrowLeft');
   await expect.poll(()=>row(names[0])?.control_state).toBe('DRIVING');await p.waitForTimeout(600);await p.keyboard.up('ArrowLeft');await expect.poll(()=>row(names[0])?.control_state).toBe('PAUSED');const released=await stop(names[0]),keyboardAfter=structuredClone(row(names[0]));
   const keyboardDelta=keyboardAfter.pose.position_m[2]-before.pose.position_m[2],keyboardRequests=structuredClone(u.fleet_requests.slice(requestStart).filter(q=>q.action==='drive'));
   if(keyboardDelta<.1||!keyboardRequests.length||keyboardRequests.some(q=>q.payload?.direction!=='left'||q.robot_id!==before.robot_id||q.status!==200)||['operation_id','connection_epoch'].some(k=>keyboardAfter[k]!==before[k]))throw Error('Original keyboard movement/request identity missing');
   const start=row(names[0]).pose.position_m[2],input=control(names[0]).getByRole('textbox',{name:'Robot command'});await input.fill('Turn left 90 degrees');await p.waitForTimeout(3000);await input.press('Enter');await expect(input).toHaveValue('');
   await expect.poll(()=>row(names[0])?.command?.state,{timeout:30000}).toBe('COMPLETED');const after=row(names[0]),delta=Math.atan2(Math.sin(after.pose.position_m[2]-start),Math.cos(after.pose.position_m[2]-start));
   if(Math.abs(delta-Math.PI/2)>.01)throw Error('Original 90 degree command incomplete');
   await control(names[0]).getByRole('button',{name:'Operation logs',exact:true}).click();await u.download(p.getByRole('button',{name:'Download operation JSON',exact:true}),'keyboard-operation.json');
   const operation=JSON.parse(await fs.readFile(out+'/keyboard-operation.json','utf8'));
   const faults=operation.events.filter(e=>/INPUT_STALE|INPUT_EXPIRED|INPUT_DEADLINE_EXPIRED|NOT_READY/.test(JSON.stringify(e)));
   if(operation.operation_id!==before.operation_id||!operation.events.length||faults.length)throw Error('Original keyboard/90 degree operation contains a rejection or expiry');
   return {before,released,keyboardAfter,keyboardDelta,keyboardRequests,after,delta,original_operation_id:operation.operation_id,original_faults:faults,original_events_sha256:hash(operation.events)};
  });
  await step('Exact Stop all ACK and engine application',async()=>{
   const before=names.map(row),pending=p.waitForResponse(r=>{try{return new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON().action==='stop_all';}catch{return false;}});
   await fleet.getByRole('button',{name:'Stop all',exact:true}).click();const response=await pending,body=await response.json();if(response.status()!==200)throw Error('Stop all rejected');
   for(const prior of before){const receipt=body.robots.find(r=>r.robot_id===prior.robot_id);if(!receipt||receipt.operation_id!==prior.operation_id||receipt.connection_epoch!==prior.connection_epoch||receipt.motion_epoch===prior.motion_epoch)throw Error('Stop all identity mismatch');await expect.poll(()=>u.fleet?.robots.find(r=>r.robot_id===prior.robot_id)?.applied_motion_epoch).toBe(receipt.motion_epoch);}
   return {before,request:response.request().postDataJSON(),response:body,engine_acks:names.map(row)};
  });
  await step('SIM sensors OFF and disconnect',async()=>{
   const stopped=[];for(const name of names){await choose(name);await control(name).getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await expect.poll(()=>row(name)?.lidar_state).toBe('OFF');stopped.push(row(name));await control(name).getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>row(name)?.connection_state).toBe('DISCONNECTED');}return {sensor_off_before_disconnect:stopped,final:names.map(row)};
  });
 }
 if(phase==='cleanup'){
  await p.getByRole('region',{name:'Robot fleet',exact:true}).getByRole('button',{name:'Stop all',exact:true}).click();
  for(const name of ['Visual Alpha 24','Visual Beta 24']){await choose(name);if(row(name)?.lidar_state==='STREAMING'){await control(name).getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await expect.poll(()=>row(name)?.lidar_state).toBe('OFF');}if(row(name)?.connection_state==='CONNECTED'){await control(name).getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>row(name)?.connection_state).toBe('DISCONNECTED');}}
  await u.note('Failed harness SIM cleanup',{status:'PASS',not_new_acceptance:true});
 }
 const physicalIds=u.fleet?.robots.filter(r=>r.kind==='physical').map(r=>r.robot_id)??[];
 const physical=u.fleet_requests.filter(q=>physicalIds.includes(q.robot_id)&&!['select','focus','set_twin_pose'].includes(q.action));
 if(physical.length)throw Error('Unexpected physical action in robot-OFF acceptance');
 await u.note('Physical actions',{hardware_actions:physical.length,requests:u.fleet_requests});await u.note('UI completed',{status:'PASS',phase});
}catch(error){u.errors.push({error:String(error)});await u.note('FAIL',{error:String(error)});await u.shot('failure').catch(()=>{});process.exitCode=1;}
finally{await u.finishVideo();await u.browser.close();}
