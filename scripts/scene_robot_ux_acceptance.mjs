// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Same installed BrowserWindow, visible controls and passive telemetry only.
import {expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import {currentControlView,checkControlView,visibleMotion} from './control_view_acceptance.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {waitForScanDisplay} from './scan_display_observation.mjs';

export async function sceneRobotUx({page,step,select,robot,drawer,poll,sleep,sendChat,shot,result,demoRecorder}){
 await select('Alpha');
 const command=async text=>{await drawer('Alpha').getByRole('textbox',{name:'Robot command',exact:true}).fill(text);
  const [request]=await Promise.all([page.waitForRequest(r=>{
   if(new URL(r.url()).pathname!=='/v1/product/robot-fleet'||r.method()!=='POST')return false;
   try{const body=r.postDataJSON();return body.action==='command'&&body.robot_id===robot('Alpha')?.robot_id&&body.payload?.text===text;}catch{return false;}
  },{timeout:5000}),drawer('Alpha').getByRole('button',{name:'Send command',exact:true}).click()]);
  return request.postDataJSON().request_id;};
 await step('Frame-bound selected LiDAR points and optional sparse rays, no localization claim',async()=>{
  const picker=page.getByRole('combobox',{name:'LiDAR visualization',exact:true});
  await picker.selectOption('points');const svg=page.locator('.robot-lidar-overlay');
  await expect(svg).toBeVisible();await poll(()=>robot('Alpha')?.scan?.points?.length>0);
  const points=await svg.locator('circle').count();if(!points||points>90)throw Error('Unbounded or missing real scan points');
  const actual=robot('Alpha').scan;
  if(actual.source!=='isaac_usd_surface_rays'||Math.abs(actual.height_m-.182)>1e-6||actual.point_frame!=='sensor_local'||actual.sensor_xy_yaw_world?.length!==3)throw Error('Model sensor height / original sensor pose / surface source not applied');
  const details=page.locator('.lidar-display-help');
  if(await details.getAttribute('open')===null)await details.locator('summary').click();
  await expect(details.getByText('sensor 18.2 cm · surface hits',{exact:false})).toBeVisible();
  if(await svg.getAttribute('data-robot-id')!==robot('Alpha').robot_id)throw Error('Wrong selected scan');
  await picker.selectOption('rays');
  // Replace, not append to, the old line-visibility5s wait. Only explicit
  // absence may be reobserved; a visible invalid sample terminates the run.
  const start=Date.now(),selected=robot('Alpha');
  const scanWindow={started_at_ms:start,deadline_ms:start+5000,timeout_ms:5000,
   expected:{robot_id:selected.robot_id,connection_epoch:selected.connection_epoch,motion_epoch:selected.motion_epoch}};
  result.scan_display_window=scanWindow;result.scan_display_observations=[];
  const scanDisplay=await waitForScanDisplay(page,scanWindow,{record:sample=>result.scan_display_observations.push(sample)});
  const rays=scanDisplay.rays_count;
  await expect(details.getByText('Isaac pose · no correction applied',{exact:false})).toBeVisible();
  await shot('lidar-sparse-rays');await picker.selectOption('off');await expect(svg).toHaveCount(0);
  await picker.selectOption('points');await details.locator('summary').click();
  return {points,rays,sensor:actual,scan_display:scanDisplay,scan_display_window:scanWindow,source:'actual current captured SIM surface scan',localization:'NOT_APPLIED'};
 });
 await step('Missing scene destination fails explicitly; command receipt is not arrival',async()=>{
  await command('Go to the nearest wardrobe');await poll(()=>robot('Alpha')?.command?.target_kind==='wardrobe');
  await poll(()=>robot('Alpha')?.command?.state==='FAILED');const row=structuredClone(robot('Alpha'));
  if(row.reason!=='NAVIGATION_TARGET_MISSING')throw Error('Missing destination not explicitly rejected: '+row.reason);
  const receipt=drawer('Alpha').getByLabel('Robot command progress',{exact:true});
  await expect(receipt).toContainText('FAILED');await expect(receipt).toHaveAttribute('title','Request '+row.command.request_id);
  await shot('destination-missing');return {command:row.command,pose:row.pose};
 });
 await step('Destination Stop cancels planning or travel and never replays old route',async()=>{
  const requestId=await command('Go to the nearest bed');await poll(()=>{
   const current=robot('Alpha')?.command;if(current?.request_id!==requestId)return false;
   if(['FAILED','CANCELLED','ARRIVED'].includes(current.state))throw Error('Destination cancellation precondition ended before Stop: '+JSON.stringify(current));
   return current.target_kind==='bed'&&['PLANNING','RUNNING'].includes(current.state);
  });
  await sleep(600);await drawer('Alpha').getByRole('button',{name:'Stop',exact:true}).click();
  await poll(()=>robot('Alpha')?.control_state==='PAUSED'&&robot('Alpha')?.motion_epoch===robot('Alpha')?.applied_motion_epoch);
  const stopped=structuredClone(robot('Alpha'));await sleep(800);const after=structuredClone(robot('Alpha'));
  if(stopped.command.state!=='CANCELLED'||after.pose.position_m.some((n,i)=>Math.abs(n-stopped.pose.position_m[i])>.001))throw Error('Cancelled route replayed');
  await shot('destination-cancelled');return {stopped,after};
 });
 for(const [kind,source] of [['bed','panel'],['chair','main-chat']])await step(`Actual ${source} nearest ${kind} destination reaches scene-derived approach with visible receipt`,async()=>{
  const before=structuredClone(robot('Alpha')),text=`Go to the nearest ${kind}`;
  if(source==='panel')await command(text);else await sendChat('Alpha robot '+text.toLowerCase());
  await poll(()=>robot('Alpha')?.command?.request_id!==before.command?.request_id&&robot('Alpha')?.command?.target_kind===kind);
  const id=robot('Alpha').command.request_id;
  const motion=await visibleMotion(page,'Alpha',()=>['ARRIVED','FAILED','CANCELLED'].includes(robot('Alpha')?.command?.state),{timeout:125000,onSample:v=>result.display_samples.push(v)});
  const after=structuredClone(robot('Alpha')),c=after.command;
  if(c.state!=='ARRIVED'||after.reason!=='NAVIGATION_ARRIVED'||!c.target_id||!c.goal_xy||Math.hypot(after.pose.position_m[0]-c.goal_xy[0],after.pose.position_m[1]-c.goal_xy[1])>.016)throw Error('No actual measured destination arrival: '+JSON.stringify(c));
  if(c.request_id!==id||after.operation_id!==before.operation_id||after.connection_epoch!==before.connection_epoch)throw Error('Destination identity changed');
  const receipt=drawer('Alpha').getByLabel('Robot command progress',{exact:true});await expect(receipt).toContainText('ARRIVED');await expect(receipt).toHaveAttribute('title','Request '+c.request_id);
  const view=await currentControlView(page,'Alpha');checkControlView(view);await shot('destination-'+kind+'-arrived');
  return {before,after,motion,source,criteria:'Current scene target and exterior standoff; original collision guard and low speed unchanged. Not physical navigation.'};
 });
 if(demoRecorder){
  // End the continuous public Home→new generation→controls video BEFORE any
  // private historical sensor import or saved physical configuration is shown.
  result.demo_end_at=Date.now();result.demo_end='AFTER_ACTUAL_CHAIR_ARRIVAL_BEFORE_NATIVE_OR_PC_SETUP';
  await fs.writeFile(path.join(demoRecorder,'finish-recording.request'),'Actual chair arrival completed; stop before private reviews.\n');
  const end=Date.now()+60000;let complete=false;
  while(Date.now()<end){try{await fs.access(path.join(demoRecorder,'app-screen.mp4'));complete=true;break;}catch{}await sleep(250);}
  if(!complete)throw Error('Public demo recorder did not finish before private review');
 }
 await step('Actual saved native scan imported via UI and shown by the shared renderer without world alignment',async()=>{
  const inputPath=fileURLToPath(new URL('../artifacts/photo-scan-review-20260927/native-scan-bundle.json',import.meta.url));
  const bytes=await fs.readFile(inputPath),original=JSON.parse(bytes);
  const setup=drawer('Alpha').locator('.robot-fleet-diagnostics>summary');
  if(await setup.locator('..').getAttribute('open')===null)await setup.click();
  await expect(setup.locator('..')).toHaveAttribute('open','');
  await drawer('Alpha').getByRole('button',{name:'Review LiDAR scans',exact:true}).click();
  const review=page.getByRole('dialog',{name:'LiDAR sensor review',exact:true});await expect(review).toBeVisible();
  const native=review.locator('.native-review');if(await native.getAttribute('open')===null)await native.locator('summary').first().click();
  await native.getByLabel('Import native scan bundle (JSON)',{exact:false}).setInputFiles(inputPath);
  await expect(native.getByRole('heading',{name:'Saved sensor recording — imported provenance',exact:true})).toBeVisible({timeout:20000});
  // Import intentionally selects the latest original frame, not frame zero.
  // Select the first frame through its real UI before testing Next.
  await native.getByRole('combobox',{name:'Saved frame',exact:true}).selectOption('0');
  await expect(native.getByRole('combobox',{name:'Saved frame',exact:true})).toHaveValue('0');
  await native.getByText('Shared sensor view · recorded returns',{exact:true}).click();
  const view=native.locator('.lidar-point-view');await expect(view.getByText('Recorded scan · not live',{exact:false})).toBeVisible();
  const first=await view.locator('circle').count();if(first<2)throw Error('No actual native returns');
  await view.getByRole('checkbox',{name:'Sparse sensor rays',exact:true}).check();
  const rays=await view.locator('line').count();if(!rays||rays>24)throw Error('Native sparse rays not bounded');
  await view.locator('svg').scrollIntoViewIfNeeded();const bounds=await view.locator('svg').boundingBox();
  if(!bounds||bounds.height<200)throw Error('Native scan only exists in a clipped console');
  await shot('saved-real-scan-shared');await native.getByRole('button',{name:'Next saved frame',exact:true}).click();
  await expect(native.getByRole('combobox',{name:'Saved frame',exact:true})).toHaveValue('1');
  const second=await view.locator('circle').count();if(second<2)throw Error('Second original scan absent');
  await review.getByRole('button',{name:'Close sensor review',exact:true}).click();await expect(review).toHaveCount(0);await setup.click();
  return {input_sha256:createHash('sha256').update(bytes).digest('hex'),input_bytes:bytes.length,source:original.source,
    first_visible_returns:first-1,second_visible_returns:second-1,rays,bounds,mode:'RECORDED_SENSOR_LOCAL_NOT_LIVE_NOT_WORLD_ALIGNED',physical_connection:false};
 });
}
