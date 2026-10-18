// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { chromium,expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL, secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output=process.env.TWINPULSE_REHEARSAL_OUTPUT;
if(new URL(base).hostname!=='127.0.0.1')throw Error('owned loopback required');
let browser,stage='bootstrap';
const result={status:'FAIL',data:'SYNTHETIC_PROCESS_ONLY_NO_ROBOT',stages:[],external_requests:0,errors:0,keyboard_actions:[],cancelled_start_actions:[],mission_actions:[]};
try{
 browser=await chromium.launch({executablePath:process.env.TWINPULSE_REHEARSAL_CHROME,headless:true});
 const page=await browser.newPage({viewport:{width:1400,height:1000}});
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());
  if(u.origin!==base&&!['blob:','data:'].includes(u.protocol)){result.external_requests++;return route.abort();}
  if(stage==='keyboard' && u.pathname==='/v1/product/robot/physical/input') result.keyboard_actions.push(route.request().postDataJSON().action);
  if(stage==='late_start' && u.pathname==='/v1/product/robot/physical/input') result.cancelled_start_actions.push(route.request().postDataJSON().action);
  if(stage.startsWith('mission_') && u.pathname==='/v1/product/robot/physical/input') result.mission_actions.push(route.request().postDataJSON().action);
  return route.continue();
 });
 page.on('pageerror',()=>result.errors++);
 await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
 await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
 const p=page.getByRole('region',{name:'Physical controller'});
 const state=()=>page.evaluate(async()=> (await fetch('/v1/product/robot/physical')).json());
 const begin=async(name)=>{await p.getByRole('checkbox').check();await p.getByRole('button',{name,exact:true}).click();};
 const finish=()=>expect.poll(async()=> (await state()).busy,{timeout:20000}).toBe(false);
 await expect(p.getByText('↑ Forward',{exact:true})).toBeDisabled();
 await expect(p.getByText('TEST DEVICE · not a physical robot',{exact:true})).toBeVisible();
 expect((await state()).state).toBe('NOT_STARTED');result.stages.push('no_auto_connection');
 await p.screenshot({path:path.join(output,'physical-desktop.png')});
 stage='reject_unqualified';
 await begin('3. Connect manual control');await finish();
 expect((await state()).result).toBe('FAILED');
 await expect(p.getByText('↑ Forward',{exact:true})).toBeDisabled();result.stages.push('unqualified_control_rejected');
 stage='cleanup_failure_display';
 const observed=await state();
 // Explicit UI-only fixture, distinct from the production process-loop stages.
 const cleanupFixture={...observed,last_trial:{historical:true,job_id:'synthetic-prior-trial',
   status:'FINAL_IDLE_UNCONFIRMED',cleanup_confirmed:false,cleanup_stage:'independent_torque_off',
   cleanup_error:'Synthetic helper exit=3',stop_assessment:{policy_id:'supervised-stop-2.0',status:'PASS',
     reason:'',checks:{},metrics:{wheel_travel_mm:[3.19,3.29]},limits:{deceleration_budget_s:.5,
       verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}};
 await page.route('**/v1/product/robot/physical',route=>route.fulfill({json:cleanupFixture}));
 await p.getByRole('button',{name:'Refresh results · read-only',exact:true}).click();
 await expect(p.getByText(/Stop metrics PASS \/ cleanup confirmation failed/)).toBeVisible();
 await expect(p.getByText('↑ Forward',{exact:true})).toBeDisabled();
 await p.screenshot({path:path.join(output,'physical-blocked-desktop.png')});
 await page.unroute('**/v1/product/robot/physical');
 result.stages.push('synthetic_cleanup_failure_separate_from_stop_PASS');
 stage='qualification';
 await begin('2. Prepare stop test');
 const run=p.getByRole('button',{name:'Execute stop test · short physical forward motion',exact:true});
 await expect(run).toBeEnabled({timeout:10000});await run.click();await finish();
 expect((await state()).result).toBe('QUALIFIED');expect((await state()).physical_verified).toBe(false);
 expect((await state()).stop_assessment.status).toBe('PASS');
 await p.getByText('View test metrics and operating criteria',{exact:true}).click();
 await expect(p.getByLabel('Separated stop assessment')).toBeVisible();
 await p.getByText('View test metrics and operating criteria',{exact:true}).click();
 result.stages.push('production_fixed_trial_loop_with_fake_sensor');
 stage='late_start';
 let arrived,release;
 const received=new Promise(r=>{arrived=r;});const gate=new Promise(r=>{release=r;});
 await page.route('**/v1/product/robot/physical/start',async route=>{
   const response=await route.fetch();arrived();await gate;await route.fulfill({response});
 });
 await begin('3. Connect manual control');await received;
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')));release();
 await finish();
 await expect.poll(()=>result.cancelled_start_actions.includes('close')).toBe(true);
 expect(result.cancelled_start_actions.every(action=>action==='close')).toBe(true);
 expect((await state()).session_evidence.robot_published).toBe(0);
 await p.getByRole('button',{name:'Refresh results · read-only',exact:true}).click();
 await expect(p.getByText('↑ Forward',{exact:true})).toBeDisabled();
 await page.unroute('**/v1/product/robot/physical/start');
 result.stages.push('delayed_start_after_blur_closes_without_watch_or_motion');
 stage='control';
 await begin('3. Connect manual control');
 await expect(p.getByText('↑ Forward',{exact:true})).toBeEnabled({timeout:10000});
 stage='keyboard';
 await expect(p).toBeFocused();
 const keyboardJob=(await state()).job_id;
 for(const [key,code] of [['ㅈ','KeyW'],['ㅁ','KeyA'],['S','KeyS'],['Process','KeyD']]){
   await p.dispatchEvent('keydown',{key,code,bubbles:true});await page.waitForTimeout(180);
   await p.dispatchEvent('keyup',{key,code,bubbles:true});
   await expect.poll(async()=> (await state()).state).toBe('RELEASING');
   await expect(p.getByText('↑ Forward',{exact:true})).toBeEnabled();
   expect((await state()).job_id).toBe(keyboardJob);expect((await state()).state).toBe('READY');
 }
 for(const action of ['forward','left','backward','right','stop']) expect(result.keyboard_actions).toContain(action);
 result.stages.push('Korean_code_CapsLock_and_repeated_keys_same_fake_session');
 stage='control';
 for(const label of ['↑ Forward','↓ Backward','↶ Turn left','↷ Turn right']){
   await p.getByText(label,{exact:true}).hover();await page.mouse.down();
   await page.waitForTimeout(280);await page.mouse.up();
   await expect.poll(async()=> (await state()).state).toBe('RELEASING');
   await expect(p.getByText('↑ Forward',{exact:true})).toBeEnabled();
   expect((await state()).state).toBe('READY');
 }
 await expect.poll(async()=> (await state()).session_storage.saved).toBeGreaterThan(20);
 const evidence=(await state()).session_evidence;
 expect(evidence.robot_published).toBeGreaterThan(0);expect(evidence.observations).toBeGreaterThan(0);
 expect(evidence.physical_success).toBe(null);expect(evidence.floor_pose_measured).toBe(false);
 await expect(p.getByLabel('Command and observation record')).toBeVisible();
 await p.getByLabel('Command and observation record').screenshot({path:path.join(output,'session-evidence.png')});
 result.stages.push('live_synced_prefix_and_distinct_command_observation_evidence');
 await p.getByRole('button',{name:'Stop after current command',exact:true}).click();await finish();
 expect((await state()).session_log_complete).toBe(true);
 expect((await state()).result).toBe('COMMAND_SEGMENT_STOPPED');
 expect((await state()).cleanup_confirmed).toBe(true);result.stages.push('four_real_input_paths_release_and_owned_cleanup_fake_devices');
 stage='saved_history';
 const beforeReview=await state();
 await p.getByRole('button',{name:'Load saved history',exact:true}).click();
 await p.getByRole('button',{name:`Record ${keyboardJob}`,exact:true}).click();
 const review=p.getByLabel('Saved session details');
 await expect(review.getByText('Synthetic transport record · Consistent end record',{exact:true})).toBeVisible();
 const download=page.waitForEvent('download');await review.getByRole('button',{name:'Save review JSON'}).click();
 await(await download).saveAs(path.join(output,'session-review-export.json'));
 const exported=JSON.parse(fs.readFileSync(path.join(output,'session-review-export.json'),'utf8'));
 expect(exported.motion_authorized).toBe(false);expect(exported.physical_success).toBe(null);
 expect(exported.recorded_end.status).toBe('COMMAND_SEGMENT_STOPPED');
 expect(exported.published_count).toBeGreaterThan(0);expect(exported.job_id).toBe(keyboardJob);
 expect(exported.navigation_observations.length).toBeGreaterThan(0);
 expect(exported.navigation_observations.every(x=>x.odom===null&&x.scan===null&&x.motion_authorized===false&&x.alignment_verified===false)).toBe(true);
 expect((await state()).job_id).toBe(beforeReview.job_id);expect((await state()).sequence).toBe(beforeReview.sequence);
 await expect(review.getByLabel('Saved session replay')).toBeVisible();
 await review.getByLabel('Replay position').press('End');
 await expect(review.getByText(/visual replay only/)).toBeVisible();
 const second=review.getByLabel('Second saved session');
 if(await second.count()){
   const candidate=await second.locator('option').nth(1).getAttribute('value');
   await second.selectOption(candidate);
   await expect(review.getByText(/Outcome ranking is disabled/)).toBeVisible();
 }
 await review.screenshot({path:path.join(output,'session-history-desktop.png')});
 result.stages.push('saved_history_replay_comparison_read_only_without_reconnect');
 stage='saved_mission_history';
 await expect(p.getByRole('button',{name:`Record ${'f'.repeat(32)}`,exact:true})).toHaveCount(0);
 expect((await state()).job_id).toBe(beforeReview.job_id);expect((await state()).sequence).toBe(beforeReview.sequence);
 result.stages.push('legacy_unbound_mission_archive_not_assigned_to_project');
 stage='mission_arrival';
 await p.getByLabel('Mission waypoints XY',{exact:true}).fill('[[0.04,0]]');
 await p.getByLabel('Mission time limit',{exact:true}).fill('5');
 await begin('Start approved mission');
 await expect.poll(async()=> (await state()).mode).toBe('mission');
 const missionJob=(await state()).job_id;
 await expect(p.getByText('↑ Forward',{exact:true})).toBeDisabled();
 await finish();expect((await state()).result).toBe('MISSION_ARRIVED');
 expect((await state()).mission_scope.waypoints).toEqual([[.04,0]]);
 expect((await state()).session_evidence.robot_published).toBeGreaterThan(5);
 await p.getByRole('button',{name:'Load saved history',exact:true}).click();
 await p.getByRole('button',{name:`Record ${missionJob}`,exact:true}).click();
 const liveExport=page.waitForEvent('download');await review.getByRole('button',{name:'Save review JSON'}).click();
 await(await liveExport).saveAs(path.join(output,'started-mission-export.json'));
 const started=JSON.parse(fs.readFileSync(path.join(output,'started-mission-export.json'),'utf8'));
 expect(started.mission_scopes.length).toBe(1);expect(started.mission_requests.length).toBe(1);
 expect(started.mission_requests[0].request_sha256).toBe(started.mission_events.find(e=>e.kind==='mission_started').data.request_sha256);
 expect(started.recorded_end.status).toBe('MISSION_ARRIVED');expect(started.physical_success).toBe(null);
 await p.getByLabel('Autonomous mission',{exact:true}).screenshot({path:path.join(output,'mission-started-desktop.png')});
 result.stages.push('one_scope_approval_app_bootstrap_production_mission_arrival_and_archive');
 stage='mission_cancel';
 await p.getByLabel('Mission waypoints XY',{exact:true}).fill('[[1,0]]');
 await p.getByLabel('Mission time limit',{exact:true}).fill('15');
 await begin('Start approved mission');
 await expect.poll(async()=> (await state()).session_evidence.robot_published).toBeGreaterThan(2);
 await p.getByRole('button',{name:'Cancel mission',exact:true}).click();await finish();
 expect((await state()).result).toBe('MISSION_CANCELLED');expect((await state()).cleanup_confirmed).toBe(true);
 expect(result.mission_actions.length).toBeGreaterThan(3);
 expect(result.mission_actions.every(a=>['watch','close'].includes(a))).toBe(true);
 result.stages.push('mission_cancel_without_remote_direction_commands');
 for(const [action,label,status] of [
   ['finish_stop','Stop after current command','COMMAND_SEGMENT_STOPPED'],
   ['force_stop','Force STOP · Esc','FORCE_STOPPED']]){
   stage=`mission_${action}`;
   await begin('Start approved mission');
   await expect.poll(async()=> (await state()).session_evidence.robot_published).toBeGreaterThan(2);
   await p.getByRole('button',{name:label,exact:true}).click();await finish();
   expect((await state()).result).toBe(status);expect((await state()).cleanup_confirmed).toBe(true);
   expect((await state()).session_log_complete).toBe(true);
   result.stages.push(`production_mission_${action}_and_cleanup_fake_devices`);
 }
 for(const [action,status] of [['finish_stop','COMMAND_SEGMENT_STOPPED'],['force_stop','FORCE_STOPPED']]){
   stage=`manual_${action}`;await begin('3. Connect manual control');
   await expect(p.getByText('↑ Forward',{exact:true})).toBeEnabled();
   await p.focus();await page.keyboard.down('w');
   await expect.poll(async()=> (await state()).session_evidence.robot_published).toBeGreaterThan(0);
   if(action==='finish_stop')await p.getByRole('button',{name:'Stop after current command',exact:true}).click();
   else await page.keyboard.press('Escape');
   await page.keyboard.up('w');await finish();
   expect((await state()).result).toBe(status);expect((await state()).cleanup_confirmed).toBe(true);
   result.stages.push(`held_manual_keyboard_${action}_and_cleanup_fake_devices`);
 }
 await p.getByLabel('Stop controls',{exact:true}).screenshot({path:path.join(output,'two-stop-controls.png')});
 stage='lidar';await begin('Start lidar · up to 8 seconds');
 await expect.poll(async()=> (await state()).state).toBe('LIDAR_RUNNING');
 await p.getByRole('button',{name:'Stop lidar',exact:true}).click();await finish();
 expect((await state()).result).toBe('LIDAR_DATA_QUIET');result.stages.push('lidar_start_cancel_reporting_fake_device');
 stage='lost_input';await begin('3. Connect manual control');
 await expect(p.getByText('↑ Forward',{exact:true})).toBeEnabled({timeout:10000});
 await p.getByText('↑ Forward',{exact:true}).hover();await page.mouse.down();await page.waitForTimeout(180);
 await page.route('**/v1/product/robot/physical/input',route=>route.abort());
 await finish();await page.mouse.up();
 expect((await state()).result).toBe('FAILED');
 expect((await state()).cleanup_confirmed).toBe(true);result.stages.push('input_loss_robot_local_loop_exits_without_ui_stop');
 await page.unroute('**/v1/product/robot/physical/input');
 stage='history_reload';await page.reload();
 await expect(page.getByText('Backend ready',{exact:true})).toBeVisible();
 await p.getByRole('button',{name:'Load saved history',exact:true}).click();
 await p.getByRole('button',{name:`Record ${keyboardJob}`,exact:true}).click();
 await expect(p.getByLabel('Saved session details')).toBeVisible();
 expect((await state()).busy).toBe(false);result.stages.push('history_after_page_reload_no_automatic_connection');
 await page.setViewportSize({width:390,height:844});
 await p.screenshot({path:path.join(output,'physical-mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 expect(result.external_requests).toBe(0);expect(result.errors).toBe(0);
 result.stages.push('mobile_no_external_traffic');result.status='PASS';
}catch(e){result.failed_stage=stage;result.error_summary=String(e.message).split(secret).join('[redacted]').split(base).join('[local]').split('\n').slice(0,7).join('\n');}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
