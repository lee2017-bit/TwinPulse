// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
if(!output)throw new Error('Explicit isolated output required');
const result={status:'FAIL',checks:[],runs:[],qualification:'EXPLICIT_TEST_ONLY',robot_connections:0};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let page;
try{
  page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const state=()=>page.evaluate(async()=>await(await fetch('/v1/product/state')).json());
  const chat=()=>page.evaluate(async()=>await(await fetch('/v1/product/conversation')).json());
  await expect.poll(async()=>!!(await state()).snapshot?.capabilities?.includes('exact_goal_demonstration_v1'),{timeout:150000}).toBe(true);
  // Use the actual UI lease and message controls, not backend calls for goal
  // review/Confirm. The fixture qualifies only a local synthetic worker.
  // Explicit goal starts and owns its engine lease in the production service;
  // no hidden manual acquisition or renewal is injected by this verifier.
  const input=page.getByRole('textbox',{name:/message/i});
  async function send(text){await input.fill(text);await input.press('Enter');}
  async function chooseCurrent(label){
    const button=page.getByRole('button',{name:label,exact:true});
    const radio=page.getByRole('radio',{name:label,exact:true});
    await expect.poll(async()=>await button.count()>0||await radio.count()>0,{timeout:15000}).toBe(true);
    if(await button.count()){await expect(button).toBeEnabled();await button.click();return;}
    await expect(radio).toBeEnabled();await radio.check();
    await page.getByRole('button',{name:'Continue',exact:true}).click();
  }
  const looping=process.env.TWINPULSE_TASK_LOOP==='1';
  const loopLegs=Number(process.env.TWINPULSE_TASK_LOOP_LEGS??2);
  const soakSeconds=Number(process.env.TWINPULSE_SOAK_SECONDS??0);
  const stalled=process.env.TWINPULSE_PROGRESS_FAULT==='1';
  const combined=process.env.TWINPULSE_UI_FAULT;
  for(const [index,text] of (looping||stalled||combined?['Go x=.05 y=-.6']:['Go x=.05 y=-.6','Go x=-.1 y=-.45']).entries()){
    const preceding=(await chat()).navigation?.demonstration?.review_id;
    await send(text);
    await expect.poll(async()=>{const n=(await chat()).navigation;
      if(n?.demonstration?.state==='FAILED')return 'FAILED';
      return !!(n?.review?.plan && n.demonstration?.state==='COMPLETED'
        && n.demonstration.review_id===n.review.plan.plan_id && n.demonstration.review_id!==preceding);
    },{timeout:65000}).not.toBe(false);
    const before=await chat();
    expect(before.navigation.demonstration.state,JSON.stringify(before.navigation.demonstration)).toBe('COMPLETED');
    const review=before.navigation.review.plan;
    expect(before.navigation.demonstration.robot_review_parked).toBe(true);
    expect(before.navigation.current_pose_available).toBe(false);
    await page.screenshot({path:path.join(output,`goal-${index}-preview.png`),fullPage:true});
    await chooseCurrent('Confirm goal route · bounded movement');
    await expect(page.getByLabel('Current worker telemetry').getByText(/^Latest worker battery:/)).toBeVisible({timeout:15000});
    await expect(page.getByLabel('Mission battery status')).toContainText('recent worker receipt',{timeout:15000});
    await expect(page.getByLabel('Mission next waypoint')).not.toHaveText('Current receipt unavailable',{timeout:15000});
    if(!combined&&!stalled){
      await expect.poll(async()=>(await chat()).navigation?.job?.isaac_display?.status,{timeout:15000})
        .toBe('ACTIVE_SENSOR_CANDIDATE_NOT_CALIBRATED');
      const live=(await chat()).navigation.job;
      expect(live.native_visual_binding.app_job_id).toBe(live.job_id);
      expect(live.native_visual_binding.native_mission_id).toBe(live.native_mission_id);
      expect(live.visual.session_id).toBe(live.native_mission_id);
      expect(live.native_mission_id).not.toBe(live.job_id);
      result.checks.push(`goal ${index}: authenticated actual Isaac renders current native sensor candidate; raw native identity preserved with explicit App display binding`);
    }
    await page.screenshot({path:path.join(output,`goal-${index}-live-telemetry.png`),fullPage:true});
    await expect.poll(async()=>(await chat()).navigation?.job?.state,{timeout:65000})
      .toMatch(/^(MISSION_ARRIVED|FAILED|FORCE_STOPPED|COMMAND_SEGMENT_STOPPED|MISSION_CANCELLED)$/);
    const after=await chat();expect(after.navigation.job.approved_preview).toEqual(review);
    if(combined){
      await expect.poll(async()=>!(await chat()).navigation.job.worker_active,{timeout:15000}).toBe(true);
      const stopped=(await chat()).navigation.job;
      expect(stopped.state).toBe('FAILED');
      expect(stopped.error).toBe(combined==='stall'?'OBSERVED_PROGRESS_STALLED':'NAVIGATION_TIME_SKEW');
      expect(stopped.native_cleanup_errors.some(n=>n.code==='STOP_READBACK_UNCONFIRMED')).toBe(true);
      expect(stopped.cleanup_error).toBe('OWNED_SENSOR_STOP_UNCONFIRMED');
      expect(stopped.report_error).toBe('MISSION_REPORT_STORAGE_FULL');expect(stopped.report_status).toBe('FAILED');
      expect(stopped.visual.pose_room).toBeNull();expect(stopped.visual.scan_room).toEqual([]);
      expect(stopped.telemetry).toBeNull();
      const popup=page.getByRole('alertdialog',{name:'Goal mission failure'});
      await expect(popup).toBeVisible({timeout:10000});
      for(const code of [stopped.error,'STOP_READBACK_UNCONFIRMED','OWNED_SENSOR_STOP_UNCONFIRMED','MISSION_REPORT_STORAGE_FULL']){
        await expect(popup).toContainText(code);
        expect((await chat()).messages.some(m=>m.content.includes(code))).toBe(true);
      }
      expect(JSON.stringify(stopped)).not.toContain('TEST_ONLY_STORAGE_CANARY');
      const confirmAgain=page.getByRole('button',{name:'Confirm goal route · bounded movement',exact:true});
      if(await confirmAgain.count())await expect(confirmAgain).toBeDisabled();
      const confirmRadio=page.getByRole('radio',{name:'Confirm goal route · bounded movement',exact:true});
      if(await confirmRadio.count())await expect(confirmRadio).toBeDisabled();
      await expect(page.getByRole('button',{name:'Repeat A ↔ B',exact:true})).toHaveCount(0);
      await expect(page.getByRole('radio',{name:'Repeat A ↔ B',exact:true})).toHaveCount(0);
      const operations=(await state()).operations.length;
      const peerCount=fs.readdirSync(output).filter(n=>/^synthetic-peer-/.test(n)).length;
      await page.screenshot({path:path.join(output,`combined-${combined}-failed.png`),fullPage:true});
      await page.waitForTimeout(1800);await page.reload();await expect(input).toBeVisible();
      await page.waitForTimeout(1800);
      expect((await state()).operations.length).toBe(operations);
      expect(fs.readdirSync(output).filter(n=>/^synthetic-peer-/.test(n)).length).toBe(peerCount);
      const restored=(await chat()).navigation;
      expect(restored.job.worker_active).toBe(false);expect(restored.current_pose_available).toBe(false);
      expect(restored.job.visual.pose_room).toBeNull();expect(restored.job.visual.scan_room).toEqual([]);
      await page.screenshot({path:path.join(output,`combined-${combined}-reloaded.png`),fullPage:true});
      result.combined_job=stopped;result.checks.push('actual built UI and Isaac exact preview; native fault plus native halt/adapter cleanup/storage retained in chat/popup; pose/cloud cleared, card locks, reload does not resume');
      break;
    }else if(stalled){
      expect(after.navigation.job.state).toBe('FAILED');
      expect(after.navigation.job.error).toBe('OBSERVED_PROGRESS_STALLED');
      await expect.poll(async()=>!(await chat()).navigation.job.worker_active,{timeout:15000}).toBe(true);
      const stopped=(await chat()).navigation.job;
      expect(stopped.cleanup_error??null).toBeNull();expect(stopped.report_status).toBe('SAVED');
      expect(stopped.telemetry).toBeNull();
      expect((await chat()).messages.some(m=>m.content.includes('OBSERVED_PROGRESS_STALLED'))).toBe(true);
      await page.screenshot({path:path.join(output,'progress-stall-stopped.png'),fullPage:true});
      result.stall_job=stopped;result.checks.push('actual native publications with stationary synthetic odom/scan cause OBSERVED_PROGRESS_STALLED; cleanup, saved cause, chat and stale telemetry');
      break;
    }
    expect(after.navigation.job.state,JSON.stringify({stage:after.navigation.job.error_stage,
      error:after.navigation.job.error,cleanup:after.navigation.job.cleanup_error})).toBe('MISSION_ARRIVED');
    const identity=after.navigation.job.job_id;
    const updates=after.events.filter(e=>e.type==='goal_execution_progress'&&e.payload.job_id===identity);
    const telemetry=after.navigation.job.events.filter(e=>e.kind==='mission_telemetry');
    expect(telemetry.length).toBeGreaterThan(0);
    expect(telemetry.some(e=>e.data.telemetry.battery?.measured_capacity===false)).toBe(true);
    expect(telemetry.some(e=>e.data.telemetry.next_waypoint)).toBe(true);
    expect(telemetry.at(-1).data.telemetry.motor_load).toBe('UNSUPPORTED');
    expect(after.navigation.job.telemetry).toBeNull();
    const terminals=after.events.filter(e=>e.type==='goal_execution_terminal'&&e.payload.job_id===identity);
    expect(updates.length).toBeGreaterThan(0);expect(terminals.length).toBeGreaterThan(0);
    expect(new Set(updates.map(e=>e.payload.message_id)).size).toBe(1);
    expect(after.messages.filter(m=>m.operation_id===identity&&m.content.startsWith('Historical mission update')).length).toBe(1);
    await expect(page.getByText(/Goal mission · MISSION_ARRIVED/).last()).toBeVisible();
    result.checks.push(`goal ${index}: five-second live message updated in place; arrival in chat; historical frame labeling`);
    result.runs.push({review,demonstration:before.navigation.demonstration,job:after.navigation.job});
    await page.screenshot({path:path.join(output,`goal-${index}-arrived.png`),fullPage:true});
  }
  if(stalled||combined){
    expect(errors).toEqual([]);result.status='PASS';
  }else if(looping){
    await chooseCurrent('Repeat A ↔ B');
    if(soakSeconds){
      expect(soakSeconds).toBe(1800);
      const started=performance.now();const samples=[];
      fs.writeFileSync(path.join(output,'soak-started'),'');
      const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
      while(performance.now()-started<soakSeconds*1000){
        const c=await chat();const t=c.navigation?.task_loop;
        expect(t?.worker_active,JSON.stringify(t)).toBe(true);
        expect(t?.state).toMatch(/^(PREPARING|DRIVING)$/);
        expect(c.events.length).toBeLessThanOrEqual(2100);expect(c.messages.length).toBeLessThanOrEqual(1000);
        expect(c.cards.length).toBeLessThanOrEqual(500);
        const metrics=(await cdp.send('Performance.getMetrics')).metrics;
        const heap=metrics.find(m=>m.name==='JSHeapUsedSize')?.value;
        expect(heap).toBeLessThan(256*1024**2);
        const sample={elapsed_s:(performance.now()-started)/1000,state:t.state,completed_legs:t.completed_legs,
          events:c.events.length,messages:c.messages.length,cards:c.cards.length,js_heap_bytes:heap,
          painted_frame_id:await page.locator('canvas[aria-label="Current Isaac Digital Twin render"]').getAttribute('data-frame-id').catch(()=>null)};
        samples.push(sample);fs.appendFileSync(path.join(output,'browser-soak.jsonl'),JSON.stringify(sample)+'\n');
        await page.waitForTimeout(10000);
      }
      const t=(await chat()).navigation.task_loop;
      expect(new Set(samples.filter(s=>s.painted_frame_id!==null).map(s=>s.painted_frame_id)).size).toBeGreaterThanOrEqual(6);
      result.soak={elapsed_s:(performance.now()-started)/1000,completed_legs:t.completed_legs,samples,
        // Parent metrics label receipt of the owned start/end markers. No
        // subtraction of browser and Python monotonic clock domains.
        duration_policy:'REAL_BROWSER_PERFORMANCE_WALL_TIME_NO_ACCELERATION'};
      fs.writeFileSync(path.join(output,'soak-ended'),'');
      await cdp.detach();
    }else{
      await expect.poll(async()=>{const t=(await chat()).navigation?.task_loop;
        return t?.state==='FAILED'?'FAILED':(t?.completed_legs??0)>=loopLegs;
      },{timeout:loopLegs===6?450000:130000}).toBe(true);
    }
    result.loop_before_stop=(await chat()).navigation.task_loop;
    await page.screenshot({path:path.join(output,'loop-active.png'),fullPage:true});
    await page.getByRole('button',{name:'Stop after current command',exact:true}).click();
    await expect.poll(async()=>{const t=(await chat()).navigation?.task_loop;return t&&!t.worker_active?t.state:'PENDING';},
      {timeout:45000}).toBe('STOPPED');
    result.loop_after_stop=(await chat()).navigation.task_loop;
    expect((await chat()).messages.filter(m=>m.operation_id===result.loop_after_stop.task_id&&m.status==='pending')).toEqual([]);
    result.checks.push(`single repeat approval; A/B endpoints fixed; ${loopLegs} fresh bounded legs in continuous synthetic world; ordinary Stop cancels next leg; original-time telemetry archived`);
    const operations=(await state()).operations.length;
    await page.reload();await expect(input).toBeVisible();
    await expect.poll(async()=>(await state()).operations.length).toBe(operations);
    expect((await chat()).navigation.task_loop.worker_active).toBe(false);
    expect(errors).toEqual([]);result.status='PASS';
    await page.screenshot({path:path.join(output,'loop-stopped-reloaded.png'),fullPage:true});
  }else{
  result.checks.push('actual built chat → native full reference/park → separate actual Isaac exact PhysX → one Confirm → fresh native arrival twice');
  const operations=(await state()).operations.length;
  const terminalCount=(await chat()).events.filter(e=>e.type==='goal_execution_terminal').length;
  await page.reload();await expect(input).toBeVisible();
  await expect.poll(async()=>(await state()).operations.length).toBe(operations);
  expect((await chat()).navigation.current_pose_available).toBe(false);
  expect((await chat()).events.filter(e=>e.type==='goal_execution_terminal').length).toBe(terminalCount);
  result.checks.push('reload/polling does not start a worker or Build/Run and never restores current physical pose');
  fs.writeFileSync(path.join(output,'fault.json'),JSON.stringify({case:'stale'}));
  await send('Go x=.05 y=-.6');
  await expect.poll(async()=>(await chat()).messages.some(m=>m.status==='failed'
    && m.content.includes('current_goal_preview_rejected')
    && /IDLE_LOCALIZATION_QUERY_TIMEOUT|IDLE_OBSERVATION_SOURCE_OR_TRANSPORT_CHANGED|GOAL_PREVIEW_CURRENT_EVIDENCE_STALE/.test(m.content)),
    {timeout:40000}).toBe(true);
  const failed=await chat();result.stale_failure=failed.messages.slice(-3);
  expect(failed.navigation.review).toBeNull();
  expect(failed.navigation.current_pose_available).toBe(false);
  expect((await state()).operations.length).toBe(operations);
  await expect(page.getByRole('button',{name:'Confirm goal route · bounded movement',exact:true})).toHaveCount(0);
  await expect(page.getByRole('radio',{name:'Confirm goal route · bounded movement',exact:true})).toHaveCount(0);
  await page.screenshot({path:path.join(output,'stale-rejected.png'),fullPage:true});
  result.checks.push('delayed raw observation rejects without motion or retry and shows original cause in chat');
  expect(errors).toEqual([]);result.status='PASS';
  }
}catch(e){result.error=String(e);if(page){
  result.failure_ui=(await page.locator('body').innerText()).slice(-14000);
  result.failure_state=await page.evaluate(async()=>await(await fetch('/v1/product/conversation')).json()).catch(()=>null);
  await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
}}finally{fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));await browser.close();}
process.exitCode=result.status==='PASS'?0:1;
