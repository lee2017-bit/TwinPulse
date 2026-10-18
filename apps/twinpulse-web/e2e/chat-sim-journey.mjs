// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {stopReturnInput,diagnosticSnapshot,diagnosticEvent,currentTargetChoice,freshGoalReview,currentPlanSample} from './benchmark-journey-policy.mjs';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const result={status:'FAIL',case:process.env.TWINPULSE_JOURNEY_CASE,checks:[],samples:[],frames:[],operations:[],page_errors:[],robot_connections:0,paid_calls:0,photo_inference:'NOT_RUN'};
const live=process.env.TWINPULSE_JOURNEY_LIVE==='1';
const compact=process.env.TWINPULSE_JOURNEY_COMPACT==='1';
const exactReplay=!!process.env.TWINPULSE_EXACT_LIVE_REPLAY;
const acceptedGeometry=!!process.env.TWINPULSE_ACCEPTED_GEOMETRY_REPAIR;
const ordinaryLive=process.env.TWINPULSE_ORDINARY_LIVE==='1';
const benchmarkCase=process.env.TWINPULSE_BENCHMARK_INPUT_JSON?JSON.parse(process.env.TWINPULSE_BENCHMARK_INPUT_JSON):null;
const diagnosticGoal=benchmarkCase&&benchmarkCase.goal.expected!=='arrival';
if(benchmarkCase&&!ordinaryLive)throw new Error('Benchmark lane cannot use fixture or saved responses');
const browserImageFault=process.env.TWINPULSE_JOURNEY_BROWSER_IMAGE_FAULT==='1';
const diagnosticDelay=process.env.TWINPULSE_JOURNEY_BROWSER_DIAGNOSTIC_DELAY==='1';
const decodeStall=process.env.TWINPULSE_JOURNEY_BROWSER_DECODE_STALL==='1';
const imageDelay=process.env.TWINPULSE_JOURNEY_BROWSER_IMAGE_DELAY==='1';
const metadataDelay=process.env.TWINPULSE_JOURNEY_METADATA_DELAY==='1';
const imageRoute='**/v1/product/viewport/current';
const isImagePath=value=>value==='/v1/product/viewport/current'||value.startsWith('/v1/product/viewport/frame/');
result.driver_errors=[];
const guardedRoute=(stage,handler)=>async route=>{
  try{await handler(route);}catch(error){result.driver_errors.push({stage,error_type:error?.name??'unknown'});
    try{await route.abort();}catch{} // Preserve failure; let bounded assertions reach browser.close().
  }
};
let releaseDiagnosis,delayedDiagnosis;
const soakSeconds=Number(process.env.TWINPULSE_JOURNEY_SOAK_SECONDS||0);
const placementEdits=process.env.TWINPULSE_PLACEMENT_EDITS==='1';
result.display_observation_ids=[];
result.observation_counts={samples:0,frames:0};
const remember=(kind,value)=>{result.observation_counts[kind]++;result[kind].push(value);if(result[kind].length>2000)result[kind].shift();};
if(exactReplay){result.provider='exact_previous_real_responses';result.photo_inference='PREVIOUS_LIVE_RESULT_REPLAY';}
if(acceptedGeometry){result.provider='audited_real_geometry_result_replay';result.photo_inference='SAVED_LIVE_OBSERVATION';}
if(live){result.paid_calls='see_shared_campaign';result.photo_inference=result.case==='image'?'LIVE':'NOT_APPLICABLE';}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let page;
try{
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',error=>result.page_errors.push(error.message));
  page.on('response',async response=>{
    const endpoint=new URL(response.url()).pathname;
    try{
      if(endpoint==='/v1/product/state'){
        const state=await response.json();if(state.snapshot)remember('samples',state.snapshot);result.operations=state.operations;
      }
      if(endpoint==='/v1/product/conversation')result.conversation=await response.json();
      if(endpoint==='/v1/product/workflow')result.workflow=await response.json();
      if(endpoint==='/v1/product/viewport'){
        const value=await response.json();if(value.frame)remember('frames',value.frame);
      }
      if(endpoint==='/v1/product/viewport/current'&&response.status()===200){
        const value=JSON.parse(await response.headerValue('X-TwinPulse-Viewport'));if(value.frame)remember('frames',value.frame);
      }
      if(endpoint==='/v1/product/viewport/observation'){
        const value=await response.json();if(value.execution_id)result.display_observation_ids.push(value.execution_id);
      }
    }catch{}
  });
  if(browserImageFault)await page.route(imageRoute,route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"explicit_browser_display_test"}'}));
  if(diagnosticDelay)await page.route('**/v1/product/viewport/observation',async route=>{
    const response=await route.fetch();
    expect(response.ok()).toBe(true);
    delayedDiagnosis=await response.json();
    // Only an isolated browser response is held. Actual backend diagnosis
    // persists normally; no production server/driver or robot is patched.
    await new Promise(resolve=>{releaseDiagnosis=resolve;});
    await route.fulfill({response});
  });
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
  await expect(page.getByRole('heading',{name:'Build your Digital Twin'})).toBeVisible();
  if(result.case==='image'){
    await page.locator('input[type=file]').setInputFiles(process.env.TWINPULSE_JOURNEY_IMAGE);
    await expect(page.getByAltText('Attached image preview')).toBeVisible();
  }
  const living=process.env.TWINPULSE_JOURNEY_LAYOUT==='living_room';
  const clutter=process.env.TWINPULSE_JOURNEY_LAYOUT==='cluttered_room';
  const imageOnly=process.env.TWINPULSE_JOURNEY_IMAGE_ONLY==='1';
  if(imageOnly){
    if(result.case!=='image'||benchmarkCase)throw new Error('Image-only must be an image input, not a text benchmark packet');
    await expect(input).toHaveValue('');
  }else await input.fill(benchmarkCase?.prompt||process.env.TWINPULSE_ACCEPTED_GEOMETRY_PROMPT||(clutter?'Create my room including floor cables, clothing, fan and other obstacles.':living?'Create my living room with a sofa, dining table and storage.':'Create a digital twin of my bedroom with a bed and desk.'));
  result.user_input_mode=imageOnly?'image_only':result.case==='image'?'text_plus_image':'text_only';
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await expect(question).toBeVisible();
  await page.waitForTimeout(1200);
  expect(result.operations).toEqual([]);
  expect(result.workflow.phase).toBe('input_ready');
  expect(result.conversation.generation).toBeNull();
  result.checks.push('Fresh input waits for inline Q1; no generation/Build/Run before choice');
  if(result.case==='image')await expect(page.getByAltText(path.basename(process.env.TWINPULSE_JOURNEY_IMAGE))).toBeVisible();
  await question.getByRole('radio',{name:'Simulation only',exact:true}).check();
  await question.getByRole('button',{name:'Continue',exact:true}).click();
  if(process.env.TWINPULSE_ORDINARY_APPROVAL_FIXTURE==='1'){
    const approve=async()=>{
      const section=page.locator('section.chat-question').filter({has:page.getByLabel('Maximum spend for this action (USD)')});
      await expect(section).toBeVisible();
      await expect(section.getByRole('button',{name:'Continue',exact:true})).toBeInViewport();
      await section.getByLabel('Maximum spend for this action (USD)').fill('1.00');
      await section.getByRole('radio',{name:'Approve generation',exact:true}).check();
      await section.getByRole('button',{name:'Continue',exact:true}).click();
    };
    await expect(page.getByLabel('Maximum spend for this action (USD)')).toBeVisible();
    await page.waitForTimeout(1000);
    expect(result.conversation.generation).toBeNull();expect(result.operations).toEqual([]);
    await page.screenshot({path:path.join(output,'ordinary-approval.png')});
    if(process.env.TWINPULSE_RENDER_REVIEW_FIXTURE==='1'){
      const state=await page.evaluate(async()=>(await fetch('/v1/product/conversation')).json());
      const preview=state.cards.at(-1).generation_approval;
      expect(preview.render_review_approved).toBe(true);
      await expect(page.getByText(preview.purpose,{exact:true})).toBeVisible();
    }
    await approve();
    if(process.env.TWINPULSE_RENDER_REVIEW_FIXTURE!=='1'){
    await expect.poll(()=>result.conversation?.generation?.state).toBe('failed');
    expect(result.conversation.generation.progress.finish_reason).toBe('length');
    const failedOperation=result.conversation.generation.operation_id;
    const old=result.conversation.generation.progress.checkpoint_id;
    await page.reload();
    await page.getByRole('button',{name:'Review generation budget and resume options',exact:true}).click();
    await expect(page.getByText(/Previous actions: 2 requests/)).toBeVisible();
    await expect.poll(()=>result.conversation.cards.at(-1)?.generation_approval?.checkpoint_id).toBe(old);
    await page.screenshot({path:path.join(output,'ordinary-resume-approval.png')});
    await approve();
    await expect.poll(async()=>{
      const state=await page.evaluate(async()=>(await fetch('/v1/product/conversation')).json());
      return state.generation?.operation_id;
    }).not.toBe(failedOperation);
    result.checks.push('Ordinary approval waits without HTTP/Build; length stops; reload never retries; explicit new budget resumes checkpoint');
    }else result.checks.push('Single explicit approval discloses source + derived render upload and idle preview Build; scripted critic/repair, zero network');
  }else if(process.env.TWINPULSE_ORDINARY_LIVE==='1'){
    const section=page.locator('section.chat-question').filter({has:page.getByLabel('Maximum spend for this action (USD)')});
    await expect(section).toBeVisible();
    const pending=await page.evaluate(async()=>(await fetch('/v1/product/conversation')).json());
    const preview=pending.cards.find(c=>c.state==='waiting'&&c.kind==='generation_approval')?.generation_approval;
    expect(preview.policy.max_requests).toBe(Number(process.env.TWINPULSE_ORDINARY_TEST_CAP||10));expect(preview.image_count).toBe(result.case==='image'?1:0);
    expect(preview.policy.per_call_timeout_s).toBe(300);expect(preview.policy.total_timeout_s).toBe(900);
    result.approval_preview=preview;
    expect(pending.generation).toBeNull();expect(result.operations).toEqual([]);
    await page.screenshot({path:path.join(output,'ordinary-live-approval.png')});
    await section.getByLabel('Maximum spend for this action (USD)').fill(process.env.TWINPULSE_ORDINARY_TEST_USD||'1.00');
    await section.getByRole('radio',{name:'Approve generation',exact:true}).check();
    await section.getByRole('button',{name:'Continue',exact:true}).click();
    result.checks.push(`Explicit user-authorized USD${process.env.TWINPULSE_ORDINARY_TEST_USD||'1.00'} / ${preview.policy.max_requests}-request ordinary approval; no model replacement or historical budget borrowing`);
  }else await expect(page.getByText('Scene generation · running')).toBeVisible();
  if(process.env.TWINPULSE_JOURNEY_STORAGE_FAULT==='project'){
    await expect(page.getByRole('alert').filter({hasText:'draft is only in memory'})).toBeVisible({timeout:25000});
    await expect(page.getByRole('region',{name:'Current step'})).toContainText('Scene not saved');
    await expect(page.getByRole('heading',{name:'Run your Twin · SIM only'})).not.toBeVisible();
    const saved=await page.evaluate(async()=>{
      const workflow=await(await fetch('/v1/product/workflow')).json();
      const detail=await(await fetch(`/v1/product/diagnostics/${workflow.execution_id}`)).json();
      const state=await(await fetch('/v1/product/state')).json();
      return {workflow,detail,state,export:await(await fetch(`/v1/product/diagnostics/${workflow.execution_id}/export`)).json()};
    });
    expect(saved.workflow.error.code).toBe('project_persistence_failed');
    expect(saved.workflow.site_draft).toBeTruthy();expect(saved.state.operations).toEqual([]);
    expect(saved.detail.status).toBe('failed');expect(saved.detail.first_error.stage).toBe('project_save');
    expect(saved.export.diagnostics.raw_included).toBe(false);
    await page.getByRole('button',{name:'View diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel.getByRole('heading',{name:'scene_generation · failed',exact:true})).toBeVisible();
    await page.screenshot({path:path.join(output,'project-storage-diagnosis.png')});
    await panel.getByRole('button',{name:'Close diagnostics'}).click();await page.reload();
    await expect(page.getByRole('alert').filter({hasText:'draft is only in memory'})).toBeVisible();
    expect((await page.evaluate(async()=>(await fetch('/v1/product/state')).json())).operations).toEqual([]);
    result.storage_fault_diagnostics=saved;
    result.checks.push('Mandatory project commit fails: validated draft retained only in memory, exact failed save diagnostic/export, no Build/Run or reload retry');
    expect(result.page_errors).toEqual([]);result.status='PASS';
  }else{
  // Keep the primary provider error instead of converting an already failed
  // generation into a misleading 100-second missing-Run assertion.
  const generationWait=live?(Number(process.env.TWINPULSE_JOURNEY_LIVE_TIMEOUT_S||90)+10)*1000:process.env.TWINPULSE_RENDER_REVIEW_FIXTURE==='1'?120000:20000;
  let terminalGeneration;
  await expect.poll(async()=>{
    // Capture a current read rather than accepting the previous failed job
    // from a response observer while an explicit continuation is starting.
    const state=await page.evaluate(async()=>(await fetch('/v1/product/conversation')).json());
    result.conversation=state;terminalGeneration=state.generation;
    return terminalGeneration?.state;
  },{timeout:generationWait}).toMatch(/^(completed|failed|cancelled)$/);
  if(terminalGeneration.state!=='completed')throw new Error(
    `GENERATION_${terminalGeneration.state.toUpperCase()}: ${terminalGeneration.summary}`);
  await expect(page.getByRole('heading',{name:'Run your Twin · SIM only'})).toBeVisible({timeout:20000});
  if(process.env.TWINPULSE_JOURNEY_APPLY_FAULT==='1'){
    await expect(page.getByRole('alert').filter({hasText:'3D scene apply failed'})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    const saved=await page.evaluate(async()=>{
      const state=await(await fetch('/v1/product/state')).json();
      const detail=await(await fetch(`/v1/product/diagnostics/${state.build_view.execution_id}`)).json();
      return {state,detail,export:await(await fetch(`/v1/product/diagnostics/${state.build_view.execution_id}/export`)).json()};
    });
    expect(saved.state.build_view.phase).toBe('apply');expect(saved.detail.status).toBe('failed');
    expect(saved.detail.first_error.error_code).toBe('RuntimeError');
    expect(saved.state.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(1);
    expect(saved.state.operations.find(op=>op.command_type==='build_site_scene').receipt.message).toContain('SIM_TEST_APPLY_FAILED');
    expect(saved.state.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    expect(saved.export.diagnostics.raw_included).toBe(false);
    await page.getByRole('button',{name:'View diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel.getByRole('heading',{name:'engine_command_build_site_scene · failed',exact:true})).toBeVisible();
    await page.screenshot({path:path.join(output,'apply-failure-diagnosis.png')});
    await panel.getByRole('button',{name:'Close diagnostics'}).click();await page.reload();
    await expect(page.getByRole('alert').filter({hasText:'3D scene apply failed'})).toBeVisible();
    const again=await page.evaluate(async()=>(await fetch('/v1/product/state')).json());
    expect(again.build_view.execution_id).toBe(saved.state.build_view.execution_id);
    expect(again.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(1);
    expect(again.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    result.apply_fault_diagnostics=saved;
    result.checks.push('Actual apply-boundary exception remains failed with exact command diagnostics/export and locked Run; reload never retries');
    expect(result.page_errors).toEqual([]);result.status='PASS';
  }else if(process.env.TWINPULSE_JOURNEY_FRAME_FAULT==='1'){
    await expect(page.getByRole('alert').filter({hasText:'first_current_frame_timeout'})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    await expect(page.getByRole('region',{name:'Current step'})).toContainText('3D display not confirmed');
    expect(result.frames).toHaveLength(0);
    expect(result.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(1);
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    expect(result.operations.find(op=>op.command_type==='build_site_scene').status).toBe('succeeded');
    const saved=await page.evaluate(async()=>{
      const read=async url=>{const response=await fetch(url);if(!response.ok)throw new Error(`Frame diagnosis HTTP ${response.status}`);return response.json();};
      const state=await read('/v1/product/state');
      if(!state.build_view.execution_id)throw new Error('Exact first-frame diagnosis absent');
      const detail=await read(`/v1/product/diagnostics/${state.build_view.execution_id}`);
      const command=await read(`/v1/product/diagnostics/${detail.manifest.metadata.command_execution_id}`);
      return {state,detail,command,export:await read(`/v1/product/diagnostics/${state.build_view.execution_id}/export`)};
    });
    expect(saved.state.build_view.status).toBe('failed');
    expect(saved.detail.status).toBe('failed');
    expect(saved.detail.first_error.error_code).toBe('first_current_frame_timeout');
    expect(saved.detail.manifest.metadata.command_id).toBe(result.operations.find(op=>op.command_type==='build_site_scene').command_id);
    expect(saved.command.status).toBe('succeeded');
    expect(saved.command.manifest.stage).toBe('engine_command_build_site_scene');
    expect(saved.export.diagnostics.raw_included).toBe(false);
    expect(saved.export.diagnostics.physical_authority).toBe(false);
    result.frame_fault_diagnostics=saved;
    await page.getByRole('button',{name:'View diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel.getByRole('heading',{name:'engine_view_observation · failed',exact:true})).toBeVisible();
    await expect(panel.getByText(/does not identify a GPU, capture, or network cause/)).toBeVisible();
    await expect(panel.getByText(/measured backend-local waiting/)).toBeVisible();
    await page.screenshot({path:path.join(output,'first-frame-diagnosis.png')});
    await panel.getByRole('navigation',{name:'Related executions'}).getByRole('button',{name:saved.command.manifest.execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'engine_command_build_site_scene · succeeded',exact:true})).toBeVisible();
    await panel.getByRole('button',{name:'Close diagnostics'}).click();
    await page.reload();
    await expect(page.getByRole('alert').filter({hasText:'first_current_frame_timeout'})).toBeVisible();
    const again=await page.evaluate(async()=>(await fetch('/v1/product/state')).json());
    expect(again.build_view.execution_id).toBe(saved.state.build_view.execution_id);
    expect(again.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(1);
    expect(again.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
    await page.screenshot({path:path.join(output,'first-frame-mobile.png')});
    await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
    await expect(page.getByRole('region',{name:'Current step'})).toBeVisible();
    await page.screenshot({path:path.join(output,'first-frame-mobile-step.png')});
    result.checks.push('Actual Build ACK preserved; suppressed display delivery yields one exact failed observation, disabled Run, export/navigation/reload and no retry');
    expect(result.page_errors).toEqual([]);result.status='PASS';
  }else{
  if(browserImageFault){
    const warning=page.getByRole('alert').filter({hasText:'Browser 3D display unavailable'});
    await expect(warning).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    await expect(page.getByRole('region',{name:'Current step'})).toContainText('Browser display failed');
    if(diagnosticDelay){
      await expect.poll(()=>!!releaseDiagnosis,{timeout:3000}).toBe(true);
      await page.unroute(imageRoute);
      await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:2500});
      await expect(warning).not.toBeVisible();
      // A successful current frame must clear the local fault before the ACK.
      result.delayed_display_ack={execution_id:delayedDiagnosis.execution_id,recovered_before_ack:true};
      releaseDiagnosis();
      await expect.poll(()=>result.display_observation_ids.includes(delayedDiagnosis.execution_id),{timeout:2000}).toBe(true);
      await page.unroute('**/v1/product/viewport/observation');
      await expect(warning).not.toBeVisible();
      await page.screenshot({path:path.join(output,'display-recovered-before-diagnostic-ack.png')});
      await page.route(imageRoute,route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"explicit_browser_display_test"}'}));
      await expect(warning).toBeVisible({timeout:3000});
      expect(result.display_observation_ids).toEqual([delayedDiagnosis.execution_id]);
      result.checks.push('Actual current frame recovers before optional diagnosis ACK; late ACK does not revive the fault, recurrence reuses its saved ID without POST retry');
    }
    await warning.getByRole('button',{name:'View diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel.getByRole('heading',{name:'browser_view_observation · failed',exact:true})).toBeVisible();
    const id=await panel.locator('code').first().textContent();
    const saved=await page.evaluate(async id=>{
      const read=async url=>{const response=await fetch(url);if(!response.ok)throw new Error(`Display diagnosis ${response.status}`);return response.json();};
      const detail=await read(`/v1/product/diagnostics/${id}`);
      return {detail,state:await read('/v1/product/state'),command:await read(`/v1/product/diagnostics/${detail.manifest.metadata.command_execution_id}`),export:await read(`/v1/product/diagnostics/${id}/export`)};
    },id);
    expect(saved.detail.status).toBe('failed');expect(saved.detail.first_error.error_code).toBe('viewport_http_error');
    expect(saved.detail.manifest.metadata.measurement_source).toBe('browser_reported');
    expect(saved.state.build_view.status).toBe('succeeded');expect(saved.state.build_view.phase).toBe('frame');
    expect(saved.command.status).toBe('succeeded');expect(saved.export.diagnostics.physical_authority).toBe(false);
    expect(saved.export.diagnostics.raw_included).toBe(false);
    expect(saved.state.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(1);
    expect(saved.state.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    await page.screenshot({path:path.join(output,'browser-display-diagnosis.png')});
    await panel.getByRole('navigation',{name:'Related executions'}).getByRole('button',{name:saved.command.manifest.execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'engine_command_build_site_scene · succeeded',exact:true})).toBeVisible();
    await panel.getByRole('button',{name:'Close diagnostics'}).click();
    await page.unroute(imageRoute);
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
    await expect(warning).not.toBeVisible();
    expect((await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}`)).json(),id)).status).toBe('failed');
    result.browser_display_diagnostics=saved;
    result.checks.push('Browser-only HTTP 503 has an exact saved failure/backlink/export; actual Build/frame success unchanged, Run blocked, recovery keeps failed history');
  }
  if(decodeStall){
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
    const framesBefore=result.observation_counts.frames;
    await page.evaluate(()=>{
      const original=window.createImageBitmap;
      const held={requests:0,closed:0,release:null,original};window.__heldDecoder=held;
      window.createImageBitmap=(...args)=>{
        const first=++held.requests===1;
        return original(...args).then(bitmap=>{
          if(!first)return bitmap;
          const close=bitmap.close.bind(bitmap);bitmap.close=()=>{held.closed++;close();};
          return new Promise(resolve=>{held.release=()=>resolve(bitmap);});
        });
      };
    });
    await expect(page.getByRole('alert').filter({hasText:'Viewer decode exceeded frame freshness'})).toBeVisible({timeout:3000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).not.toBeVisible();
    await page.waitForTimeout(300);
    const pending=await page.evaluate(()=>({requests:window.__heldDecoder.requests,ready:!!window.__heldDecoder.release}));
    expect(pending).toEqual({requests:1,ready:true});
    expect(result.observation_counts.frames).toBeGreaterThan(framesBefore+1);
    await expect.poll(()=>result.display_observation_ids.at(-1),{timeout:2000})
      .not.toBe(result.browser_display_diagnostics?.detail.manifest.execution_id);
    const decodeId=result.display_observation_ids.at(-1);
    expect(decodeId).toBeTruthy();
    const decodeDetail=await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}`)).json(),decodeId);
    expect(decodeDetail.status).toBe('failed');expect(decodeDetail.first_error.error_code).toBe('viewport_decode_expired');
    await page.evaluate(()=>window.__heldDecoder.release());
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:3000});
    const recovered=await page.evaluate(()=>{
      const held=window.__heldDecoder;window.createImageBitmap=held.original;
      return {requests:held.requests,closed:held.closed};
    });
    expect(recovered.closed).toBe(1);expect(recovered.requests).toBeGreaterThan(1);
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    result.decode_recovery={status:'PASS',execution_id:decodeId,pending,recovered,metadata_polling_continued:true,extra_run:false};
    await page.screenshot({path:path.join(output,'decode-timeout-recovered.png')});
    result.checks.push('Actual decoded bitmap held past freshness: old pixels hidden/Run locked, one native decode, metadata polling continues, late bitmap released once and fresh reception recovers without Run');
  }
  if(imageDelay){
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
    let delayed=false,finished=false,servedFrame,pendingImages=0,releaseImages;
    const nextImages=new Promise(resolve=>{releaseImages=resolve;});
    const beforeIds=[...result.display_observation_ids];
    const slowImage=guardedRoute('slow_image',async route=>{
      if(delayed){pendingImages++;try{await nextImages;await route.continue();}finally{pendingImages--;}return;}
      const response=await route.fetch();
      if(response.status()!==200){await route.fulfill({response});return;}
      delayed=true;servedFrame=JSON.parse(response.headers()['x-twinpulse-viewport']).frame.frame_id;
      await new Promise(resolve=>setTimeout(resolve,1250));
      await route.fulfill({response});finished=true;
    });
    await page.route(imageRoute,slowImage);
    await expect(page.getByRole('alert').filter({hasText:'Viewer image delivery exceeded frame freshness'})).toBeVisible({timeout:5000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    await expect.poll(()=>result.display_observation_ids.find(id=>!beforeIds.includes(id)),{timeout:3000}).toBeTruthy();
    const id=result.display_observation_ids.find(id=>!beforeIds.includes(id));
    const detail=await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}`)).json(),id);
    expect(detail.status).toBe('failed');expect(detail.first_error.error_code).toBe('viewport_image_expired');
    const timing=detail.manifest.metadata;
    expect(timing.frame_id).toBe(servedFrame);expect(timing.browser_image_ms).toBeGreaterThanOrEqual(1000);
    expect(timing.browser_decode_ms).toBe(0);expect(timing.browser_frame_age_ms).toBeGreaterThanOrEqual(1000);
    expect(timing.measurement_source).toBe('browser_reported');
    await expect.poll(()=>finished).toBe(true);releaseImages();
    await expect.poll(()=>pendingImages).toBe(0);await page.unroute(imageRoute,slowImage);
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:5000});
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    result.image_delay_recovery={status:'PASS',execution_id:id,metadata:timing,injected_delay_ms:1250,
      root_cause_scope:'controlled browser response delay, not proof of earlier CPU or Wi-Fi cause',extra_run:false};
    await page.screenshot({path:path.join(output,'image-delay-recovered.png')});
    result.checks.push('One actual JPEG delivery delayed 1250ms: transport expiry distinct from decoder, bounded timings persisted/exact frame ID, Run locked and read-only recovery without replay');
  }
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled({timeout:45000});
  await expect(page.getByText(/Scene applied in Isaac\. Check the current 3D display/)).toBeVisible();
  await expect(page.getByRole('region',{name:'Current step'})).toContainText('Scene applied · review the SIM route');
  await expect(page.getByRole('img',{name:'SIM planned route and observed trajectory'})).toBeVisible();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
  expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
  let expectedInitialBuilds=process.env.TWINPULSE_RENDER_REVIEW_FIXTURE==='1'?3:1;
  if(ordinaryLive&&result.approval_preview.policy.external_final_review){
    const key=result.conversation.generation.progress.checkpoint_id;
    expect(key).toMatch(/^[a-f0-9]{64}$/);
    const checkpoint=JSON.parse(fs.readFileSync(path.join(output,'runtime/provider-evidence/generation-store/checkpoint',`${key}.json`),'utf8')).payload;
    expect(checkpoint.state).toBe('APPROXIMATE_TWIN_READY');
    expect(checkpoint.plan_sha256).toBe(result.workflow.site_draft.plan_sha256);
    if(result.case==='image')expect(checkpoint.render_history.length).toBeGreaterThan(0);
    else{
      expect(checkpoint.render_history).toHaveLength(0);
      result.source_photo_review='NOT_APPLICABLE_TEXT';
      result.checks.push('Text uses the actual two-stage planner and local geometry validation, not an invented source-photo observation or render critic');
    }
    expectedInitialBuilds+=checkpoint.render_history.length;
    result.actual_render_reviews=checkpoint.render_history.map(row=>({status:row.status,candidate_revision:row.candidate_revision,frame_key:row.frame_key,plan_sha256:row.plan_sha256}));
  }
  expect(result.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(expectedInitialBuilds);
  result.initial_preview_plan=result.conversation.simulation_review.plan;
  if(compact||ordinaryLive){
    const draft=result.workflow.site_draft;
    if(live||exactReplay||acceptedGeometry||ordinaryLive)expect(draft.room_inventory.items.length).toBeGreaterThan(0);
    else expect(draft.room_inventory.items).toHaveLength(process.env.TWINPULSE_GENERIC_PHOTO==='1'?4:24);
    expect(draft.photo_inventory).toBeNull();
    expect(draft.room_inventory.live_observation).toBe(false);
    if(compact)expect(draft.summary).toContain('not a reconstructed room');
    result.compact_inventory={items:draft.room_inventory.items.length,
      source:live?'live_model':acceptedGeometry?'audited_real_geometry_result_replay':exactReplay?'exact_audited_replay':'explicit_transport_fixture',geometry_status:'ESTIMATED_NOT_MEASURED',
      plan_sha256:draft.plan_sha256,input_revision:draft.input_revision};
    result.checks.push(ordinaryLive?'Fresh ordinary live scene reaches Site2.2 with saved object inventory; geometry remains estimated, not measured':'Compact transport fixture reaches Site2.2 with all selected objects, not a reviewed-photo recognition claim');
  }
  if(clutter){
    await page.getByText('Room inventory and scene details',{exact:true}).click();
    await page.getByText('Room inventory · 19 items',{exact:true}).click();
    await expect(page.getByText('cable bundle',{exact:true})).toBeVisible();
    expect(result.workflow.site_draft.room_inventory.items).toHaveLength(19);
    expect(result.workflow.site_draft.room_inventory.live_observation).toBe(false);
    expect(result.workflow.site_draft.room_inventory.items.filter(i=>i.risk==='entanglement'||i.risk==='unknown')
      .every(i=>i.geometry.some(g=>g.synthetic_keepout&&g.collision))).toBe(true);
    result.checks.push('All 19 props visible in saved inventory; fabric/cable/unknown carry colliding synthetic keepouts, not live measurements');
  }
  expect(result.samples.at(-1).run_id).toBeNull();
  expect(result.samples.at(-1).telemetry_available).toBe(false);
  expect(result.samples.at(-1).sim_time_s).toBe(0);
  expect(result.workflow.saved_input.input_kind).toBe(result.case==='image'?'photo':'text');
  result.checks.push(`Choice starts ${live?'live provider':exactReplay?'exact previous real response replay':'explicit fixture'} generation; short checked SIM spawn/route and actual Build prepare automatically, never Run`);
  await page.screenshot({path:path.join(output,'generated-ready.png')});
  const faultContract=process.env.TWINPULSE_JOURNEY_FAULT==='1';
  if(faultContract){
    result.run_requests=[];
    await page.route('**/v1/product/commands',async route=>{
      const body=route.request().postDataJSON();
      if(body.command_type==='run'){
        result.run_requests.push(body.client_request_id);
        const response=await route.fetch();result.lost_run_response=await response.json();
        // The real backend accepted the one request. Only its HTTP response
        // to the browser is lost; subsequent recovery is read-only.
        await route.abort('failed');return;
      }
      await route.continue();
    });
  }
  await page.getByRole('button',{name:'Run simulation',exact:true}).click();
  if(faultContract){
    await expect(page.getByRole('alert').filter({hasText:'SIM_TEST_POSE_LOST'})).toBeVisible({timeout:45000});
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    expect(result.samples.at(-1).runtime_state).toBe('error');
    expect(result.samples.at(-1).telemetry_available).toBe(false);
    expect(result.samples.at(-1).position_m).toBeNull();
    await page.waitForTimeout(1500);
    expect(result.run_requests).toHaveLength(1);
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(1);
    expect(result.operations.find(op=>op.command_type==='run').status).toBe('succeeded');
    await page.screenshot({path:path.join(output,'runtime-fault-receipt-loss.png')});
    await page.reload();
    await expect(page.getByRole('alert').filter({hasText:'SIM_TEST_POSE_LOST'})).toBeVisible();
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    expect(result.run_requests).toHaveLength(1);
    await expect(page.getByRole('region',{name:'Current step'})).toContainText('Isaac execution stopped');
    if(process.env.TWINPULSE_JOURNEY_DIAGNOSTICS==='1'){
      const saved=await page.evaluate(async()=>{
        const read=async url=>{const response=await fetch(url);if(!response.ok)throw new Error(`Saved diagnosis HTTP ${response.status}`);return response.json();};
        const state=await read('/v1/product/state');
        if(!state.snapshot_execution_id)throw new Error('Runtime fault execution absent');
        const detail=await read(`/v1/product/diagnostics/${state.snapshot_execution_id}`);
        const command=await read(`/v1/product/diagnostics/${detail.manifest.metadata.command_execution_id}`);
        return {state,detail,command,export:await read(`/v1/product/diagnostics/${state.snapshot_execution_id}/export`)};
      });
      expect(saved.detail.status).toBe('failed');
      expect(saved.detail.first_error.stage).toBe('engine_runtime_fault');
      expect(saved.detail.first_error.error_code).toBe('SIM_TEST_POSE_LOST');
      expect(saved.command.status).toBe('succeeded');
      expect(saved.command.manifest.stage).toBe('engine_command_run');
      expect(saved.detail.manifest.metadata.command_id).toBe(result.operations.find(op=>op.command_type==='run').command_id);
      expect(saved.export.diagnostics.raw_included).toBe(false);
      expect(saved.export.diagnostics.physical_authority).toBe(false);
      if(process.env.TWINPULSE_JOURNEY_CLEANUP_FAULT==='1'){
        const cleanup=saved.detail.spans.find(span=>span.stage==='engine_runtime_cleanup');
        expect(cleanup.status).toBe('failed');expect(cleanup.metadata.role).toBe('cleanup');
        expect(cleanup.metadata.error_code).toBe('SIM_TEST_CLEANUP_FAILED');
        await expect(page.getByRole('alert').filter({hasText:'SIM_TEST_CLEANUP_FAILED'})).toBeVisible();
      }
      result.runtime_fault_diagnostics=saved;
      await page.getByRole('button',{name:'View diagnostics',exact:true}).click();
      const panel=page.getByRole('region',{name:'Execution diagnostics'});
      await expect(panel.getByRole('heading',{name:'engine_runtime_observation · failed',exact:true})).toBeVisible();
      await expect(panel.getByRole('strong').filter({hasText:/^engine_runtime_fault$/})).toBeVisible();
      if(process.env.TWINPULSE_JOURNEY_CLEANUP_FAULT==='1')
        await expect(panel.getByText('engine_runtime_cleanup',{exact:true})).toBeVisible();
      await page.screenshot({path:path.join(output,'compound-runtime-diagnosis.png')});
      await panel.getByRole('navigation',{name:'Related executions'}).getByRole('button',{name:saved.command.manifest.execution_id,exact:true}).click();
      await expect(panel.getByRole('heading',{name:'engine_command_run · succeeded',exact:true})).toBeVisible();
      await panel.getByRole('button',{name:'Back to previous execution',exact:true}).click();
      await expect(panel.getByRole('heading',{name:'engine_runtime_observation · failed',exact:true})).toBeVisible();
      await panel.getByRole('button',{name:'Refresh diagnostics',exact:true}).click();
      await expect(panel.getByRole('heading',{name:'engine_runtime_observation · failed',exact:true})).toBeVisible();
      const again=await page.evaluate(async()=>{
        const state=await(await fetch('/v1/product/state')).json();
        const rows=await(await fetch('/v1/product/diagnostics')).json();
        return {id:state.snapshot_execution_id,count:rows.executions.filter(row=>row.stage==='engine_runtime_observation').length,
          run_count:state.operations.filter(op=>op.command_type==='run').length};
      });
      expect(again.id).toBe(saved.detail.manifest.execution_id);expect(again.count).toBe(1);expect(again.run_count).toBe(1);
      result.checks.push('Runtime primary and optional cleanup fault persist separately from command ACK success; exact popup link/related command/back/export/reload, no duplicate fault or Run');
    }
    result.checks.push('Actual PhysX fault is an English alert; current pose cleared and Run locked; lost HTTP Run receipt recovered with one operation and no re-execution/reload resume');
    expect(result.page_errors).toEqual([]);result.status='PASS';
  }else{
  await expect(page.getByText(/Physics completed · goal distance/)).toBeVisible({timeout:90000});
  if(benchmarkCase)await expect.poll(()=>result.samples.at(-1)?.run_id===result.initial_preview_plan.plan_id&&
    result.samples.at(-1)?.runtime_state==='completed',{timeout:15000}).toBe(true);
  result.arrival=result.samples.at(-1);
  expect(result.arrival.telemetry_available).toBe(true);
  expect(result.arrival.distance_to_goal_m).toBeLessThanOrEqual(.04);
  await expect(page.getByText('SIM navigation · completed',{exact:true})).toBeVisible();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await page.screenshot({path:path.join(output,'generated-physics-arrived.png')});
  expect(new Set(result.frames.filter(f=>f.applied_revision===result.arrival.applied_revision).map(f=>f.frame_id)).size).toBeGreaterThan(3);
  result.checks.push('One explicit Run of newly generated current room; actual PhysX goal arrival and current task/3D');
  const readGoalState=()=>page.evaluate(async()=>({product:{...await(await fetch('/v1/product/state')).json(),
    workflow:await(await fetch('/v1/product/workflow')).json()},
    conversation:await(await fetch('/v1/product/conversation')).json()}));
  const goalBefore=benchmarkCase?await readGoalState():null;
  await input.fill(benchmarkCase?.goal.text||(clutter?'Go to X=1.4 Y=0':living?'Go to the sofa':'Go to the bed'));await page.getByRole('button',{name:'Send',exact:true}).click();
  if(diagnosticGoal){
    const before=diagnosticSnapshot(goalBefore.product,goalBefore.conversation);
    await expect.poll(async()=>{
      const state=await readGoalState();
      try{return diagnosticEvent(before,state.conversation,benchmarkCase.goal.expected).type;}catch{return null;}
    },{timeout:15000}).toBe(benchmarkCase.goal.expected==='clarification'?'simulation_goal_clarification':'simulation_goal_rejected');
    // Observe a second idle sample: a question/error must not secretly Run.
    await page.waitForTimeout(1000);
    const state=await readGoalState();const event=diagnosticEvent(before,state.conversation,benchmarkCase.goal.expected);
    const after={...diagnosticSnapshot(state.product,state.conversation),event,
      simulation_plan:state.conversation.simulation_review?.plan??null,
      physical_authority:state.conversation.physical_authority,
      goal_text:state.conversation.messages.filter(m=>m.role==='user').at(-1)?.content,
      card:state.conversation.cards.find(c=>c.id===event.payload.card_id)??null};
    for(const key of ['scene_revision','plan_sha256','input_revision','operations','snapshot'])expect(after[key]).toEqual(before[key]);
    expect(after.simulation_plan).toBeNull();
    result.diagnostic_goal={schema_version:'benchmark-goal-diagnostic-1.0',
      case_sha256:process.env.TWINPULSE_BENCHMARK_CASE_SHA256,goal_sha256:benchmarkCase.goal.sha256,
      request_id:event.payload.request_id,before,after};
    result.checks.push('Predeclared diagnostic goal observed through current App; no answer click, new engine command or changed scene/pose');
  }else{
  if(benchmarkCase){
    await expect.poll(async()=>{
      const state=await readGoalState();
      try{return !!freshGoalReview(goalBefore.conversation,state.conversation,benchmarkCase.goal.text,result.arrival.applied_revision);}
      catch{return false;}
    },{timeout:15000}).toBe(true);
    const state=await readGoalState();
    if(!state.conversation.simulation_review?.plan){
      const choice=currentTargetChoice(state.conversation,result.arrival.applied_revision);
      result.semantic_target_choice=choice;
      await page.getByRole('radio',{name:choice.label,exact:true}).check();
      await page.getByRole('button',{name:'Continue',exact:true}).click();
      result.checks.push('Generic target ambiguity resolved through the current chat choice with frozen saved-ID policy');
    }
    await expect.poll(async()=>{
      const state=await readGoalState();
      try{return !!freshGoalReview(goalBefore.conversation,state.conversation,benchmarkCase.goal.text,result.arrival.applied_revision).review.plan;}
      catch{return false;}
    },{timeout:15000}).toBe(true);
    const selectedState=await readGoalState();
    const fresh=freshGoalReview(goalBefore.conversation,selectedState.conversation,benchmarkCase.goal.text,result.arrival.applied_revision);
    result.semantic_goal_evidence={schema_version:'benchmark-arrival-1.0',
      case_sha256:process.env.TWINPULSE_BENCHMARK_CASE_SHA256,goal_sha256:benchmarkCase.goal.sha256,
      goal_text:benchmarkCase.goal.text,before:{cursor:goalBefore.conversation.cursor,
        request_id:goalBefore.conversation.simulation_review?.request_id,snapshot:goalBefore.product.snapshot,
        operations:goalBefore.product.operations},...fresh};
    await expect(page.getByRole('region',{name:'Simulation route',exact:true})).toHaveAttribute('data-plan-id',fresh.review.plan.plan_id);
  }
  // Dense rooms include a bounded grid search and the next UI poll. Observe the
  // completed response; do not retry the command or assume a five-second Kit
  // scheduling budget. Keep failures above this bound as failures.
  // Benchmark readiness is the current route card's verified plan ID and its
  // enabled Run control, not historical chat messages with the same wording.
  if(!benchmarkCase)await expect(page.getByText(clutter?/SIM route ready/:living?/SIM route ready to sofa/:/SIM route ready to bed/)).toBeVisible({timeout:15000});
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Run simulation',exact:true}).click();
  await expect(page.getByText(benchmarkCase?/Physics (running|completed) · goal distance/:/Physics running · goal distance/)).toBeVisible({timeout:15000});
  if(benchmarkCase){
    const proof=result.semantic_goal_evidence;
    await expect.poll(async()=>{
      const state=await readGoalState();
      return currentPlanSample(state.product.snapshot,proof.review.plan,proof.before.snapshot,'completed');
    },{timeout:150000}).toBe(true);
    const arrived=await readGoalState();
    result.semantic_arrival=arrived.product.snapshot;
    proof.arrival=result.semantic_arrival;proof.operations=arrived.product.operations;
    expect(result.semantic_arrival.applied_revision).toBe(result.arrival.applied_revision);
    expect(result.semantic_arrival.telemetry_available).toBe(true);
    expect(result.semantic_arrival.distance_to_goal_m).toBeLessThanOrEqual(.04);
    result.checks.push('Predeclared semantic goal reached in actual Isaac; not merely the short illustrative preview');
    // Completion correctly disables Stop. Exercise Stop in a separate return
    // to this same scene's observed preview endpoint; never alter the room.
    const historical=result.samples.find(s=>s.run_id===result.arrival.run_id&&s.runtime_state==='running'&&s.telemetry_available);
    result.stop_test_input=stopReturnInput(result.arrival,result.semantic_arrival,historical);
    await input.fill(result.stop_test_input);await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect.poll(async()=>{
      const state=await readGoalState();
      try{return !!freshGoalReview(arrived.conversation,state.conversation,result.stop_test_input,result.arrival.applied_revision).review.plan;}
      catch{return false;}
    },{timeout:15000}).toBe(true);
    const returned=await readGoalState();
    const fresh=freshGoalReview(arrived.conversation,returned.conversation,result.stop_test_input,result.arrival.applied_revision);
    result.stop_test_evidence={...fresh,before:arrived.product.snapshot};
    await expect(page.getByRole('region',{name:'Simulation route',exact:true})).toHaveAttribute('data-plan-id',fresh.review.plan.plan_id);
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'Run simulation',exact:true}).click();
    await expect.poll(async()=>{
      const state=await readGoalState();
      return currentPlanSample(state.product.snapshot,fresh.review.plan,arrived.product.snapshot,'running');
    },{timeout:15000}).toBe(true);
    result.stop_test_evidence.running=(await readGoalState()).product.snapshot;
    result.checks.push('Separate return route is moving before Stop; completed arrival alone is not stop acceptance');
  }
  await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  await expect(page.getByRole('button',{name:'Stop simulation',exact:true})).toBeEnabled();
  await input.fill('Stop simulation');await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByText(/Physics paused · goal distance/)).toBeVisible({timeout:15000});
  if(benchmarkCase){
    const proof=result.stop_test_evidence;
    await expect.poll(async()=>currentPlanSample((await readGoalState()).product.snapshot,
      proof.review.plan,proof.running,'paused'),{timeout:15000}).toBe(true);
    result.stop=(await readGoalState()).product.snapshot;
    await page.waitForTimeout(1000);
    proof.paused=result.stop;proof.stable=(await readGoalState()).product.snapshot;
    expect(proof.stable.position_m).toEqual(proof.paused.position_m);
  }else{
    result.stop=result.samples.at(-1);await page.waitForTimeout(1000);
    expect(result.samples.at(-1).position_m).toEqual(result.stop.position_m);
  }
  }
  const builds=result.operations.filter(op=>op.command_type==='build_site_scene').length;
  const runs=result.operations.filter(op=>op.command_type==='run').length;
  const reloadPlan=result.workflow.site_draft.plan_sha256;
  const reloadInput=result.workflow.site_draft.input_revision;
  await page.reload();
  await expect(page.getByText(diagnosticGoal?/Physics completed · goal distance/:/Physics paused · goal distance/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
  await page.waitForTimeout(1000);
  expect(result.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(builds);
  expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(runs);
  expect(result.workflow.site_draft.plan_sha256).toBe(reloadPlan);
  expect(result.workflow.site_draft.input_revision).toBe(reloadInput);
  result.reload_evidence={status:'PASS',plan_sha256:reloadPlan,input_revision:reloadInput,
    builds_before:builds,builds_after:result.operations.filter(op=>op.command_type==='build_site_scene').length,
    runs_before:runs,runs_after:result.operations.filter(op=>op.command_type==='run').length,
    runtime_state:result.samples.at(-1)?.runtime_state,
    restored_run_authorization:false};
  if(diagnosticGoal)result.checks.push('Diagnostic reload retains completed idle pose and no restored Run; moving Stop is NOT_EVALUATED');
  if(browserImageFault){
    await page.route(imageRoute,route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":"explicit_browser_display_test"}'}));
    const warning=page.getByRole('alert').filter({hasText:'Browser 3D display unavailable'});
    await expect(warning).toBeVisible();
    await expect.poll(()=>result.display_observation_ids.at(-1)).toBe(result.browser_display_diagnostics.detail.manifest.execution_id);
    const expectedIds=[result.browser_display_diagnostics.detail.manifest.execution_id,
      ...(decodeStall?[result.decode_recovery.execution_id]:[]),...(imageDelay?[result.image_delay_recovery.execution_id]:[])];
    expect([...new Set(result.display_observation_ids)].sort()).toEqual(expectedIds.sort());
    await page.unroute(imageRoute);
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
    await expect(warning).not.toBeVisible();
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    result.checks.push('The same browser-reported failure after reload reuses its exact saved ID; recovery does not restore Run approval or repeat commands');
  }
  if(compact){
    expect(result.workflow.site_draft.plan_sha256).toBe(result.compact_inventory.plan_sha256);
    expect(result.workflow.site_draft.input_revision).toBe(result.compact_inventory.input_revision);
    expect(result.workflow.site_draft.room_inventory.items).toHaveLength(result.compact_inventory.items);
    expect(result.workflow.site_draft.photo_inventory).toBeNull();
    result.checks.push('Reload preserves the exact compact plan/input and selected inventory; no Build/Run replay');
  }
  result.checks.push(diagnosticGoal?'Expected question/rejection uses current idle pose; no navigation, reload command or restored approval':
    'Next chat goal uses current idle Physics pose; chat Stop while folded; paused pose unchanged; reload no Build/Run or restored approval');
  // Explicit reset via the existing owner API restores the non-physical
  // preview. It must not execute the old plan or invent physical telemetry.
  await page.evaluate(async revision=>{
    const send=async(endpoint,body)=>{
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
        'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
      if(!response.ok)throw new Error(`Reset prerequisite ${response.status}`);return await response.json();
    };
    await send('/v1/product/lease',{});
    await send('/v1/product/commands',{client_request_id:crypto.randomUUID(),command_type:'reset',expected_applied_revision:revision});
  },result.arrival.applied_revision);
  await expect.poll(()=>result.samples.at(-1)?.run_id).toBeNull();
  expect(result.samples.at(-1).telemetry_available).toBe(false);
  expect(result.samples.at(-1).sim_time_s).toBe(0);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await page.waitForTimeout(750);
  expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(runs);
  await page.screenshot({path:path.join(output,'generated-reset-preview.png')});
  const soakIdleRender=async()=>{
    // Return-to-chat remounts the viewport. Backend frame polling alone does
    // not prove that its browser drawing surface has mounted and displayed.
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
    await expect.poll(()=>page.locator('.twin-live-viewport canvas').count(),{timeout:15000}).toBe(1);
    let delayedMetadataRequests=0,metadataPending=0;
    const slowMetadata=guardedRoute('slow_metadata',async route=>{
      metadataPending++;try{const response=await route.fetch();await new Promise(resolve=>setTimeout(resolve,250));
        delayedMetadataRequests++;await route.fulfill({response});}finally{metadataPending--;}
    });
    if(metadataDelay){
      const probes=[];
      for(let attempt=0;attempt<3;attempt++){
        const old=await(await page.request.get(`${process.env.TWINPULSE_VIEW_URL}/v1/product/viewport`)).json();
        expect(old.frame).toBeTruthy();await page.waitForTimeout(250);
        const current=await page.request.get(`${process.env.TWINPULSE_VIEW_URL}/v1/product/viewport/current`);
        expect(current.status()).toBe(200);
        const receipt=JSON.parse(current.headers()['x-twinpulse-viewport']);
        const digest=createHash('sha256').update(await current.body()).digest('hex');
        expect(digest).toBe(receipt.frame.sha256);expect(receipt.frame.frame_id).toBeGreaterThan(old.frame.frame_id);
        const legacy=await page.request.get(`${process.env.TWINPULSE_VIEW_URL}/v1/product/viewport/frame/${old.frame.frame_id}`);
        expect(legacy.status()).toBe(409);
        probes.push({metadata_frame:old.frame.frame_id,packet_frame:receipt.frame.frame_id,legacy_status:legacy.status(),jpeg_hash_matches:true});
      }
      result.atomic_pair_probes=probes;
      await page.route('**/v1/product/viewport',slowMetadata);
    }
    const initial=await page.evaluate(async()=>(await(await fetch('/v1/product/state')).json()));
    const expectedRuns=initial.operations.filter(op=>op.command_type==='run').length;
    const expectedBuilds=initial.operations.filter(op=>op.command_type==='build_site_scene').length;
    const expectedRevision=initial.snapshot.applied_revision;
    const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
    const transport={responses:0,expired:0,failures:0,recent:[]};
    const imageResponse=async request=>{
      if(!isImagePath(new URL(request.url()).pathname))return;
      const response=await request.response();if(!response)return;
      // response fires at headers; responseEnd is still -1 then. Measure only
      // after requestfinished so the retained duration includes the body read.
      const timing=request.timing();const duration=timing.responseEnd>=0?timing.responseEnd:null;
      transport.responses++;if(response.status()===409)transport.expired++;
      if(response.status()!==200&&response.status()!==409)transport.failures++;
      transport.recent.push({at_ms:Date.now(),status:response.status(),duration_ms:duration});
      if(transport.recent.length>32)transport.recent.shift();
    };
    page.on('requestfinished',imageResponse);
    // Observe live->hidden transitions independently of the 1 Hz sampling.
    // Positive display metadata only: no headers, model bodies or raw pixels.
    await page.evaluate(()=>{
      const canvas=document.querySelector('.twin-live-viewport canvas');
      const values=()=>({at_ms:Date.now(),visible:canvas.getAttribute('role')==='img'&&!canvas.hidden,
        frame_id:canvas.dataset.frameId??null,captured_at_ms:Number(canvas.dataset.capturedAt)||null,
        status:canvas.closest('section').querySelector('[role=status]')?.textContent??null});
      let previous=values();
      window.__renderSoak={hidden_transitions:0,transitions:[],last:previous};
      window.__renderSoakObserver=new MutationObserver(()=>{
        const current=values();
        if(current.visible!==previous.visible){
          if(!current.visible)window.__renderSoak.hidden_transitions++;
          window.__renderSoak.transitions.push({before:previous,after:current});
          if(window.__renderSoak.transitions.length>128)window.__renderSoak.transitions.shift();
        }
        previous=current;window.__renderSoak.last=current;
      });
      window.__renderSoakObserver.observe(canvas,{attributes:true,attributeFilter:['role','hidden','data-frame-id','data-captured-at']});
    });
    const started=Date.now(),samples=[];let missingCurrentFrame=0;
    // Keep positive evidence even if a later independent assertion aborts the
    // soak. A partial measurement is not a completed or passed soak.
    result.soak={state:'partial',seconds:soakSeconds,samples,elapsed_s:0,
      missing_current_frame_samples:0,applied_revision:expectedRevision,
      expected_builds:expectedBuilds,expected_runs:expectedRuns,after_placement_edits:placementEdits};
    while(Date.now()-started<soakSeconds*1000){
      const observed=await page.evaluate(async()=>{
        const begin=performance.now();const state=await(await fetch('/v1/product/state')).json();
        const viewport=await(await fetch('/v1/product/viewport')).json();
        const canvas=document.querySelector('.twin-live-viewport canvas');
        return {state,viewport,canvases:document.querySelectorAll('.twin-live-viewport canvas').length,
          images:document.querySelectorAll('canvas[role=img]').length,at_ms:Date.now(),api_elapsed_ms:performance.now()-begin,
          displayed_frame_id:canvas?.dataset.frameId??null,displayed_captured_at_ms:Number(canvas?.dataset.capturedAt)||null,
          viewer_status:canvas?.closest('section').querySelector('[role=status]')?.textContent??null,
          viewer_alerts:[...canvas?.closest('section').querySelectorAll('[role=alert]')??[]].map(e=>e.textContent),
          visibility:document.visibilityState};
      });
      const metrics=(await cdp.send('Performance.getMetrics')).metrics;
      const heap=metrics.find(value=>value.name==='JSHeapUsedSize')?.value;
      samples.push({elapsed_s:(Date.now()-started)/1000,heap_bytes:heap,frame_id:observed.viewport.frame?.frame_id??null,fps:observed.viewport.fps,canvases:observed.canvases,current_image:!!observed.images,server_frame:!!observed.viewport.frame,
        at_ms:observed.at_ms,api_elapsed_ms:observed.api_elapsed_ms,displayed_frame_id:observed.displayed_frame_id,
        displayed_age_ms:observed.displayed_captured_at_ms?observed.at_ms-observed.displayed_captured_at_ms:null,
        server_age_ms:observed.viewport.frame?observed.at_ms-observed.viewport.frame.captured_at_ms:null,
        viewer_status:observed.viewer_status,viewer_alerts:observed.viewer_alerts,visibility:observed.visibility,
        image_responses:transport.responses,image_expired:transport.expired,image_failures:transport.failures,
        ...(observed.images?{}:{recent_image_requests:[...transport.recent]})});
      result.soak.elapsed_s=(Date.now()-started)/1000;
      if(!observed.viewport.frame||!observed.images)missingCurrentFrame++;
      result.soak.missing_current_frame_samples=missingCurrentFrame;
      expect(observed.state.operations.filter(op=>op.command_type==='run')).toHaveLength(expectedRuns);
      expect(observed.state.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(expectedBuilds);
      expect(observed.state.snapshot.applied_revision).toBe(expectedRevision);
      expect(observed.viewport.frame?.applied_revision).toBe(expectedRevision);
      expect(observed.state.snapshot.run_id).toBeNull();expect(observed.state.snapshot.telemetry_available).toBe(false);
      expect(observed.canvases).toBe(1);
      await page.waitForTimeout(1000);
    }
    page.off('requestfinished',imageResponse);
    if(metadataDelay){await page.unrouteAll({behavior:'wait'});
      await expect.poll(()=>metadataPending).toBe(0);result.metadata_delay={delay_ms:250,requests:delayedMetadataRequests,scope:'controlled metadata response delay, not a CPU/GPU load reproduction'};}
    const displayTransitions=await page.evaluate(()=>{window.__renderSoakObserver.disconnect();return window.__renderSoak;});
    await cdp.detach();
    const heaps=samples.map(sample=>sample.heap_bytes).filter(Number.isFinite);
    result.soak={state:'complete',seconds:soakSeconds,elapsed_s:(Date.now()-started)/1000,samples,missing_current_frame_samples:missingCurrentFrame,
      applied_revision:expectedRevision,expected_builds:expectedBuilds,expected_runs:expectedRuns,after_placement_edits:placementEdits,
      heap_first_bytes:heaps[0],heap_last_bytes:heaps.at(-1),heap_peak_bytes:Math.max(...heaps),
      display_transitions:displayTransitions,image_transport:transport,
      measurement:'Chrome Performance JSHeapUsedSize; not total GPU/process memory'};
    expect(missingCurrentFrame).toBe(0);expect(displayTransitions.hidden_transitions).toBe(0);
    if(metadataDelay){expect(delayedMetadataRequests).toBeGreaterThan(10);expect(transport.expired).toBe(0);expect(transport.responses).toBeGreaterThan(10);}
    expect(heaps.at(-1)-heaps[0]).toBeLessThan(32*1024*1024);
    result.checks.push('Bounded idle render soak: one canvas, current frames, no Build/Run replay and JS heap end growth below 32 MiB; not an unlimited leak guarantee');
  };
  if(soakSeconds&&!placementEdits)await soakIdleRender();
  if(process.env.TWINPULSE_JOURNEY_STORAGE_FAULT==='diagnostics'){
    await page.getByRole('button',{name:'Diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel.getByRole('alert')).toContainText('Diagnostics degraded');
    await expect(panel.getByRole('alert')).toContainText('Missing records are not proof of success');
    result.optional_storage_health=await page.evaluate(async()=>(await fetch('/v1/product/diagnostics')).json());
    expect(result.optional_storage_health.health.storage_errors).toBeGreaterThan(0);
    await page.screenshot({path:path.join(output,'optional-storage-degraded.png')});
    await panel.getByRole('button',{name:'Close diagnostics'}).click();
    result.checks.push('Optional diagnostics manifest failure does not fail valid generation/Build/PhysX/Stop; developer view explicitly reports degraded missing records');
  }
  if(process.env.TWINPULSE_JOURNEY_DIAGNOSTICS==='1' && process.env.TWINPULSE_JOURNEY_STORAGE_FAULT!=='diagnostics'){
    const before=result.operations.map(op=>op.command_id);
    const saved=await page.evaluate(async()=>{
      const read=async path=>{const response=await fetch(path);if(!response.ok)throw new Error(`Diagnostics HTTP ${response.status}`);return response.json();};
      const list=await read('/v1/product/diagnostics');
      const generation=list.executions.find(item=>item.stage==='scene_generation');
      if(!generation)throw new Error('Generation execution absent');
      return {list,detail:await read(`/v1/product/diagnostics/${generation.execution_id}`),
        export:await read(`/v1/product/diagnostics/${generation.execution_id}/export`)};
    });
    expect(saved.detail.status).toBe('succeeded');
    expect(saved.detail.manifest.metadata.generation_id).toBe(result.conversation.generation.generation_id);
    expect(saved.detail.manifest.metadata.operation_id).toBe(result.conversation.generation.operation_id);
    const launch=saved.list.executions.find(item=>item.stage==='launcher_start');
    expect(launch).toBeTruthy();
    expect(launch.status).toBe('succeeded');
    expect(saved.detail.manifest.metadata.launch_execution_id).toBe(launch.execution_id);
    expect(saved.detail.events.every(event=>event.schema_version==='1.1'&&event.event_id&&event.component)).toBe(true);
    expect(saved.detail.events.some(event=>event.type==='profile_row')).toBe(true);
    if (result.case==='image') {
      if(acceptedGeometry){
        const replay=saved.detail.events.find(event=>event.type==='references'&&event.metadata.evidence_kind==='audited_real_result_replay');
        expect(replay).toBeTruthy();
        expect(replay.metadata.evidence_id).toBe(process.env.TWINPULSE_ACCEPTED_MODEL_EXECUTION_ID);
        expect(replay.metadata.requests).toBe(0);
        expect(saved.detail.spans.some(span=>span.stage==='observer')).toBe(false);
      }else expect(saved.detail.spans.some(span=>span.stage==='observer')).toBe(true);
      // Only the ordinary synthetic fixture deliberately exercises repair.
      // Fresh live models and exact replays can legitimately succeed first try.
      if(!compact&&!live&&!exactReplay&&process.env.TWINPULSE_RENDER_REVIEW_FIXTURE!=='1')expect(saved.detail.spans.some(span=>span.stage==='planner_validation'&&span.status==='failed')).toBe(true);
      if(process.env.TWINPULSE_RENDER_REVIEW_FIXTURE==='1'){
        expect(saved.detail.spans.some(span=>span.stage==='render_review')).toBe(true);
        expect(saved.detail.spans.some(span=>span.stage==='repair')).toBe(true);
      }
    }
    expect(saved.export.diagnostics.raw_included).toBe(false);
    expect(saved.export.diagnostics.physical_authority).toBe(false);
    const runExecutions=saved.list.executions.filter(item=>item.stage==='engine_command_run');
    expect(runExecutions).toHaveLength(runs);
    expect(new Set(runExecutions.map(item=>item.execution_id)).size).toBe(runs);
    const buildExecution=saved.list.executions.find(item=>item.stage==='engine_command_build_site_scene');
    expect(buildExecution).toBeTruthy();
    const buildDetail=await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}`)).json(),buildExecution.execution_id);
    expect(buildDetail.spans.some(span=>span.stage==='first_current_frame_after_receipt'&&span.status==='succeeded')).toBe(true);
    expect(buildDetail.spans.some(span=>span.stage==='engine_adapter_execute'&&span.metadata.measurement_source==='engine_local_elapsed')).toBe(true);
    saved.build=buildDetail;
    saved.paging=await page.evaluate(async()=>{
      const pages=[];let cursor=null;
      do {
        const response=await fetch('/v1/product/diagnostics?limit=1'+(cursor?'&cursor='+encodeURIComponent(cursor):''));
        if(!response.ok)throw new Error('Diagnostic page failed');
        const value=await response.json();pages.push(value);cursor=value.next_cursor;
        if(pages.length>100)throw new Error('Diagnostic cursor loop');
      } while(cursor);
      return pages;
    });
    const pagedIds=saved.paging.flatMap(value=>value.executions.map(item=>item.execution_id));
    expect(new Set(pagedIds).size).toBe(pagedIds.length);
    expect(pagedIds).toContain(saved.detail.manifest.execution_id);expect(pagedIds).toContain(launch.execution_id);
    await page.getByRole('button',{name:'Diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('button',{name:'Search executions',exact:true})).toBeEnabled();
    await panel.getByLabel('Search saved metadata').fill('scene_generation');
    await panel.getByLabel('Search saved metadata').press('Enter');
    await expect(panel.getByRole('button',{name:saved.detail.manifest.execution_id,exact:true})).toBeVisible();
    await expect(panel.getByLabel('Status')).toBeEnabled();
    await panel.getByLabel('Status').selectOption('succeeded');
    await expect(panel.getByRole('table',{name:'Saved executions'}).locator('tbody tr')).toHaveCount(1);
    await expect(panel.getByRole('button',{name:saved.detail.manifest.execution_id,exact:true})).toBeVisible();
    await page.screenshot({path:path.join(output,'execution-search.png')});
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
    expect(await panel.evaluate(element=>element.scrollWidth<=element.clientWidth)).toBe(true);
    await page.screenshot({path:path.join(output,'execution-search-mobile.png')});
    await panel.evaluate(element=>{element.scrollTop=element.scrollHeight;});
    await page.screenshot({path:path.join(output,'execution-search-mobile-results.png')});
    await panel.evaluate(element=>{element.scrollTop=0;});
    await page.setViewportSize({width:1440,height:1000});
    await panel.getByRole('button',{name:saved.detail.manifest.execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'Stage timeline'})).toBeVisible();
    await expect(panel.getByRole('heading',{name:'Function profile'})).toBeVisible();
    await panel.getByRole('button',{name:'Show linked execution graph',exact:true}).click();
    const graph=panel.getByRole('region',{name:'Linked execution graph'});
    await expect(graph).toBeVisible();
    await expect(graph.getByRole('button',{name:buildExecution.execution_id,exact:true})).toBeEnabled();
    await expect(graph.getByRole('button',{name:launch.execution_id,exact:true})).toBeEnabled();
    saved.graph=await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}/graph`)).json(),saved.detail.manifest.execution_id);
    expect(saved.graph.edges.some(edge=>edge.source===buildExecution.execution_id&&edge.target===saved.detail.manifest.execution_id&&edge.relation==='evidence_id')).toBe(true);
    expect(saved.graph.raw_included).toBe(false);expect(saved.graph.physical_authority).toBe(false);
    await panel.getByRole('navigation',{name:'Related executions'}).getByRole('button',{name:launch.execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'launcher_start · succeeded',exact:true})).toBeVisible();
    await panel.getByRole('button',{name:'Back to previous execution',exact:true}).click();
    await expect(panel.getByRole('heading',{name:'Function profile'})).toBeVisible();
    // Returning to an execution invalidates its prior graph snapshot.
    await panel.getByRole('button',{name:'Show linked execution graph',exact:true}).click();
    await expect(graph).toBeVisible();
    await page.screenshot({path:path.join(output,'execution-diagnostics.png')});
    const download=page.waitForEvent('download');
    await panel.getByRole('button',{name:'Export redacted diagnostics'}).click();
    const exported=await download;await exported.saveAs(path.join(output,'execution-export.json'));
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
    await page.screenshot({path:path.join(output,'execution-diagnostics-mobile.png')});
    expect(await graph.evaluate(element=>element.scrollWidth>element.clientWidth)).toBe(false);
    await panel.getByRole('button',{name:'Close diagnostics'}).click();
    expect(result.operations.map(op=>op.command_id)).toEqual(before);
    result.diagnostics=saved;
    result.checks.push('Execution IDs correlate generation, pure CPU profile and engine receipts; bounded API paging/search; recorded one-hop incoming Build and outgoing launch graph; related/back navigation invalidates old graph; Diagnostics reads/export add no command; raw excluded; actual desktop/mobile UI');
  }
  result.checks.push('Explicit reset clears driven Burger and telemetry; restores the illustrative visual without Run');
  if(process.env.TWINPULSE_JOURNEY_DIAGNOSTICS_EDITS==='1'){
    const saved=await page.evaluate(async()=>{
      const send=async(endpoint,body)=>{
        const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
          'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
        const value=await response.json();
        if(!response.ok)throw new Error(`Edit acceptance ${endpoint} HTTP ${response.status}: ${value.error?.code??'unknown'}`);return value;
      };
      const read=async endpoint=>(await fetch(endpoint)).json();
      const source=await read('/v1/product/workflow');
      const bed=source.site_draft.editable_calls.find(call=>call.tool==='place_furniture'&&call.arguments.kind==='bed');
      const moved={...bed,arguments:{...bed.arguments,center_m:[bed.arguments.center_m[0],bed.arguments.center_m[1]+.05]}};
      const preview=await send('/v1/product/scene-edit/preview',{operation_id:'acceptance-edit',mode:'change',target_call_id:bed.call_id,tool_call:moved});
      const edited=await send('/v1/product/scene-edit/apply',{operation:preview.operation,preview_digest:preview.preview_digest});
      const undoPreview=await send('/v1/product/scene-edit/preview',{operation_id:'acceptance-undo',mode:'undo',target_call_id:null,tool_call:null});
      const undone=await send('/v1/product/scene-edit/apply',{operation:undoPreview.operation,preview_digest:undoPreview.preview_digest});
      const list=await read('/v1/product/diagnostics');
      const edit=list.executions.find(row=>row.stage==='scene_edit_apply');
      const undo=list.executions.find(row=>row.stage==='scene_edit_undo');
      if(!edit||!undo)throw new Error('Committed edit traces absent');
      await send('/v1/product/draft/acknowledge',{revision:undone.site_draft.revision});
      await send('/v1/product/lease',{});
      return {edit_execution_id:edit.execution_id,undo_execution_id:undo.execution_id,
        edit_revision:edited.site_draft.revision,undo_revision:undone.site_draft.revision,artifact_id:undone.site_draft.artifact_id};
    });
    expect(saved.edit_revision).not.toBe(saved.undo_revision);
    // Lease renewal becomes engine permission only after its next heartbeat.
    // Wait for the existing gate; never bypass it or retry a rejected action.
    await expect.poll(async()=>await page.evaluate(async()=>
      (await (await fetch('/v1/product/workflow')).json()).build_allowed),{timeout:10000}).toBe(true);
    saved.build=await page.evaluate(async data=>{
      const response=await fetch('/v1/product/commands',{method:'POST',headers:{'Content-Type':'application/json',
        'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify({
          client_request_id:crypto.randomUUID(),command_type:'build_site_scene',
          artifact_id:data.artifact_id,expected_applied_revision:data.undo_revision})});
      const value=await response.json();
      if(!response.ok)throw new Error(`Edited Build HTTP ${response.status}: ${value.error?.code??'unknown'}`);return value;
    },saved);
    await expect.poll(()=>result.samples.at(-1)?.applied_revision,{timeout:45000}).toBe(saved.undo_revision);
    await expect.poll(()=>result.frames.at(-1)?.applied_revision,{timeout:15000}).toBe(saved.undo_revision);
    const detail=await page.evaluate(async id=>(await fetch(`/v1/product/diagnostics/${id}`)).json(),saved.undo_execution_id);
    expect(detail.status).toBe('succeeded');
    expect(detail.manifest.metadata.scene_edit_execution_id).toBe(saved.edit_execution_id);
    await page.getByRole('button',{name:'Diagnostics',exact:true}).click();
    const panel=page.getByRole('region',{name:'Execution diagnostics'});
    await panel.getByRole('button',{name:saved.undo_execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'scene_edit_undo · succeeded',exact:true})).toBeVisible();
    await panel.getByRole('navigation',{name:'Related executions'}).getByRole('button',{name:saved.edit_execution_id,exact:true}).click();
    await expect(panel.getByRole('heading',{name:'scene_edit_apply · succeeded',exact:true})).toBeVisible();
    await page.screenshot({path:path.join(output,'execution-edit-origin.png')});
    await panel.getByRole('button',{name:'Back to previous execution',exact:true}).click();
    await panel.getByRole('button',{name:'Close diagnostics'}).click();
    result.diagnostic_edits=saved;
    result.checks.push('Committed edit/Undo exact origins, previous edit UI navigation and current actual Isaac frame; no Run after edits');
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(runs);
  }
  if(process.env.TWINPULSE_PARAMETRIC_PHOTO==='1'){
    const origin=await page.evaluate(async()=>(await (await fetch('/v1/product/workflow')).json()).site_draft);
    expect(origin.placement_contract.schema_version).toBe('photo-placement-contract-1.0');
    expect(origin.placement_contract.relations).toHaveLength(24);
    expect(origin.editable_calls.find(c=>c.arguments.id==='bed').arguments.dimensions_m).toEqual([1.1,2,.9]);
    const groupEdits=[];
    for(const [identity,child] of [['desk','monitor'],['bed','bedding_overhang']]){
      const edited=await page.evaluate(async({identity,child})=>{
        const send=async(endpoint,body)=>{
          const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
            'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
          const value=await response.json();
          if(!response.ok)throw new Error(`Parametric edit ${endpoint} HTTP ${response.status}: ${value.error?.code??'unknown'}`);
          return value;
        };
        const source=(await (await fetch('/v1/product/workflow')).json()).site_draft;
        const parent=source.editable_calls.find(c=>c.arguments.id===identity);
        const before=source.editable_calls.find(c=>c.arguments.id===child);
        const call={...parent,arguments:{...parent.arguments,yaw_deg:90,
          dimensions_m:parent.arguments.dimensions_m.map((d,i)=>d+(i===0?.1:i===2?.05:0))}};
        const preview=await send('/v1/product/scene-edit/preview',{
          operation_id:'edit_'+crypto.randomUUID(),mode:'change',target_call_id:parent.call_id,tool_call:call});
        const result=await send('/v1/product/scene-edit/apply',{operation:preview.operation,preview_digest:preview.preview_digest});
        const after=result.site_draft.editable_calls.find(c=>c.arguments.id===child);
        await send('/v1/product/draft/acknowledge',{revision:result.site_draft.revision});
        await send('/v1/product/lease',{});
        return {identity,child,before,after,preview,revision:result.site_draft.revision,
          artifact_id:result.site_draft.artifact_id,plan_sha256:result.site_draft.plan_sha256};
      },{identity,child});
      expect(edited.after.arguments.position_m).not.toEqual(edited.before.arguments.position_m);
      expect(edited.after.arguments.yaw_deg).toBe(90);
      expect(Object.keys(edited.preview.affected_after).some(id=>id.startsWith(child+'_'))).toBe(true);
      const buildRevision=async data=>{
        const command=await page.evaluate(async data=>{
          const post=async(route,body)=>{
            const response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json',
              'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
            const value=await response.json();
            if(!response.ok)throw new Error(`Parametric ${route} HTTP ${response.status}: ${value.error?.code??'unknown'}`);
            return value;
          };
          // One browser task keeps the existing 3 s owner lease fresh. Splitting
          // this across Playwright/CDP round trips allowed render contention to
          // expire it after eligibility was observed. No widened TTL or retry.
          const lease=await post('/v1/product/lease',{});
          const deadline=performance.now()+10000;
          while(true){
            await post('/v1/product/lease/renew',{control_lease_id:lease.control_lease_id});
            const workflow=await (await fetch('/v1/product/workflow')).json();
            if(workflow.build_allowed)break;
            if(performance.now()>=deadline)throw new Error('Parametric Build eligibility timeout');
            await new Promise(resolve=>setTimeout(resolve,500));
          }
          await post('/v1/product/lease/renew',{control_lease_id:lease.control_lease_id});
          const response=await fetch('/v1/product/commands',{method:'POST',headers:{'Content-Type':'application/json',
            'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify({
              client_request_id:crypto.randomUUID(),command_type:'build_site_scene',
              artifact_id:data.artifact_id,expected_applied_revision:data.revision})});
          const value=await response.json();
          if(!response.ok)throw new Error(`Parametric Build HTTP ${response.status}: ${value.error?.code??'unknown'}`);
          return value;
        },data);
        await expect.poll(()=>result.samples.at(-1)?.applied_revision,{timeout:45000}).toBe(data.revision);
        await expect.poll(()=>result.frames.at(-1)?.applied_revision,{timeout:15000}).toBe(data.revision);
        return {command,frame:result.frames.at(-1),snapshot:result.samples.at(-1)};
      };
      edited.actual_build=await buildRevision(edited);
      await page.screenshot({path:path.join(output,`parametric-${identity}-edited.png`)});
      const undone=await page.evaluate(async child=>{
        const send=async(endpoint,body)=>{
          const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
            'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
          const value=await response.json();
          if(!response.ok)throw new Error(`Parametric Undo HTTP ${response.status}`);return value;
        };
        const preview=await send('/v1/product/scene-edit/preview',{
          operation_id:'undo_'+crypto.randomUUID(),mode:'undo',target_call_id:null,tool_call:null});
        const result=await send('/v1/product/scene-edit/apply',{operation:preview.operation,preview_digest:preview.preview_digest});
        await send('/v1/product/draft/acknowledge',{revision:result.site_draft.revision});
        await send('/v1/product/lease',{});
        return {child:result.site_draft.editable_calls.find(c=>c.arguments.id===child),revision:result.site_draft.revision,
          artifact_id:result.site_draft.artifact_id,plan_sha256:result.site_draft.plan_sha256};
      },child);
      expect(undone.child).toEqual(edited.before);
      expect(undone.plan_sha256).toBe(origin.plan_sha256);
      undone.actual_build=await buildRevision(undone);
      await page.screenshot({path:path.join(output,`parametric-${identity}-undone.png`)});
      groupEdits.push({edited,undone});
    }
    result.parametric_edits=groupEdits;
    expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(runs);
    result.checks.push('Photo1.2 library dimensions and 24 persisted relationships: desk/monitor and bed/bedding grouped rotation/resize, exact edited and Undo revisions in actual Isaac frames; no extra Run');
    if(process.env.TWINPULSE_PLACEMENT_EDITS==='1'){
      // Diagnostics includes a mobile view. Restore the desktop editing layout;
      // the narrow layout intentionally shows either Twin or conversation.
      await page.setViewportSize({width:1920,height:1080});
      await page.getByText('Room inventory and scene details',{exact:true}).click();
      await page.getByText('Room inventory · 24 items',{exact:true}).click();
      await page.getByRole('button',{name:'Edit inventory placement',exact:true}).click();
      await page.getByRole('button',{name:'Review Twin',exact:true}).click();
      const editor=page.locator('.scene-edit-review');
      const readSite=()=>page.evaluate(async()=>(await (await fetch('/v1/product/workflow')).json()).site_draft);
      const buildUi=async(name)=>{
        const draft=await readSite();
        // Save and acknowledgement are async controlled inputs. Wait for the
        // same revision in the real UI, then observe its server-backed ack;
        // Playwright check() incorrectly requires a synchronous DOM toggle.
        await expect(editor.getByText(new RegExp(`Saved edits: ${draft.scene_edit_count} .*current ${draft.revision.slice(0,10)}`))).toBeVisible();
        const acknowledgement=page.getByRole('checkbox',{name:'I reviewed the limits of this draft version.',exact:true});
        if(!await acknowledgement.isChecked())await acknowledgement.click();
        await expect(acknowledgement).toBeChecked();
        const acquire=page.getByRole('button',{name:'Acquire scene control',exact:true});
        if(await acquire.isVisible())await acquire.click();
        const build=page.getByRole('button',{name:'Build scene geometry in Isaac',exact:true});
        await expect(build).toBeEnabled({timeout:15000});await build.click();
        await expect.poll(()=>result.samples.at(-1)?.applied_revision,{timeout:45000}).toBe(draft.revision);
        let frame,bytes;
        await expect.poll(async()=>{
          const value=await page.evaluate(async()=>(await (await fetch('/v1/product/viewport')).json()));
          frame=value.frame;
          if(frame?.applied_revision!==draft.revision)return false;
          const image=await page.request.get(new URL(frame.url,page.url()).href);
          // A newer current frame may replace this bounded frame URL between
          // reads. Only that explicit 409 is retried, without another Build.
          if(image.status()===409)return false;
          expect(image.ok()).toBe(true);bytes=await image.body();
          expect(createHash('sha256').update(bytes).digest('hex')).toBe(frame.sha256);
          return true;
        },{timeout:15000}).toBe(true);
        fs.writeFileSync(path.join(output,`placement-${name}-isaac.jpg`),bytes);
        return {revision:draft.revision,frame};
      };
      await editor.getByRole('radio',{name:'Change room item / hazard',exact:true}).check();
      await editor.getByLabel('Existing room item call',{exact:true}).selectOption('obj_monitor');
      await expect(editor.getByRole('button',{name:'Drag selected object',exact:true})).toBeDisabled();
      await expect(editor.getByRole('note').filter({hasText:'Move or rotate parent desk'})).toBeVisible();
      await editor.getByLabel('Existing room item call',{exact:true}).selectOption('obj_cables');
      const before=await readSite();
      const original=before.editable_calls.find(c=>c.arguments.id==='cables');
      const marker=editor.getByRole('button',{name:'Drag selected object',exact:true});
      await marker.scrollIntoViewIfNeeded();
      const markerBox=await marker.boundingBox();
      const mapBox=await editor.getByRole('group',{name:'Selected object floor map',exact:true}).boundingBox();
      await marker.evaluate(element=>{
        window.__placementPointerEvents=[];
        for(const type of ['pointerdown','pointermove','pointerup','pointercancel','gotpointercapture','lostpointercapture'])
          element.addEventListener(type,event=>{
            if(window.__placementPointerEvents.length<32)window.__placementPointerEvents.push({
              type,id:event.pointerId,buttons:event.buttons,x:event.clientX,y:event.clientY});
          });
      });
      await page.mouse.move(markerBox.x+markerBox.width/2,markerBox.y+markerBox.height/2);
      const hoveredBox=await marker.boundingBox();
      expect(hoveredBox.x).toBeCloseTo(markerBox.x,1);expect(hoveredBox.y).toBeCloseTo(markerBox.y,1);
      await page.mouse.down();await page.mouse.move(markerBox.x+markerBox.width/2-mapBox.width*.04,markerBox.y+markerBox.height/2,{steps:5});
      expect((await readSite()).revision).toBe(before.revision);
      await page.mouse.up();
      result.placement_pointer_events=await page.evaluate(()=>window.__placementPointerEvents);
      await expect.poll(async()=>Number(await editor.getByLabel('X (m)',{exact:true}).inputValue()),
        {timeout:3000}).toBeCloseTo(original.arguments.position_m[0]-.32,2);
      await expect(editor.getByRole('button',{name:'Save reviewed change',exact:true})).toBeDisabled();
      await editor.getByRole('button',{name:'Preview change',exact:true}).click();
      await expect(editor.getByRole('button',{name:'Save reviewed change',exact:true})).toBeEnabled();
      await editor.getByRole('button',{name:'Save reviewed change',exact:true}).click();
      await expect.poll(async()=>(await readSite()).scene_edit_count).toBe(5);
      const moved=await readSite();
      expect(moved.editable_calls.find(c=>c.arguments.id==='cables').arguments.observation_time_utc).toBeNull();
      expect(moved.room_inventory.items.find(i=>i.id==='cables').geometry.some(g=>g.synthetic_keepout)).toBe(true);
      const movedFrame=await buildUi('drag');
      await editor.getByLabel('Existing room item call',{exact:true}).selectOption('obj_cables');
      await editor.getByRole('button',{name:'Rotate selected object 90°',exact:true}).click();
      await editor.getByRole('button',{name:'Preview change',exact:true}).click();
      await expect(editor.getByRole('button',{name:'Save reviewed change',exact:true})).toBeEnabled();
      await editor.getByRole('button',{name:'Save reviewed change',exact:true}).click();
      await expect.poll(async()=>(await readSite()).scene_edit_count).toBe(6);
      const rotated=await readSite();
      expect(rotated.editable_calls.find(c=>c.arguments.id==='cables').arguments.yaw_deg).toBe(90);
      const rotatedFrame=await buildUi('rotate');
      await page.screenshot({path:path.join(output,'placement-map-saved.png')});
      const undos=[];
      for(const count of [7,8]){
        await editor.getByRole('radio',{name:'Undo last edit',exact:true}).check();
        await editor.getByRole('button',{name:'Preview change',exact:true}).click();
        await expect(editor.getByRole('button',{name:'Save reviewed change',exact:true})).toBeEnabled();
        await editor.getByRole('button',{name:'Save reviewed change',exact:true}).click();
        await expect.poll(async()=>(await readSite()).scene_edit_count).toBe(count);
        undos.push(await buildUi(`undo-${count}`));
      }
      const restored=await readSite();
      expect(restored.editable_calls.find(c=>c.arguments.id==='cables')).toEqual(original);
      expect(restored.plan_sha256).toBe(origin.plan_sha256);
      result.placement_ui={before:before.revision,moved:movedFrame,rotated:rotatedFrame,undos,
        restored:restored.revision,original_call_restored:true,keepout_preserved:true,physical_authority:false};
      await page.getByRole('button',{name:'← Return to chat',exact:true}).click();
      await expect.poll(()=>result.frames.at(-1)?.applied_revision,{timeout:15000}).toBe(restored.revision);
      await page.screenshot({path:path.join(output,'placement-restored-chat.png')});
      result.checks.push('Existing inventory UI: attached child locked; cable pointer drag and rotation require Preview/Save; actual exact Isaac frames and two Undo builds; original/keepout/unknown timestamp retained; no Run');
      expect(result.operations.filter(op=>op.command_type==='run')).toHaveLength(runs);
    }
  }
  if(soakSeconds&&placementEdits)await soakIdleRender();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:path.join(output,'journey-mobile.png')});
  expect(result.page_errors).toEqual([]);expect(result.driver_errors).toEqual([]);result.status='PASS';
  }
  }
  }
}catch(error){
  result.error=error.message;result.error_stack=error.stack;process.exitCode=1;
  if(page){
    // Public DTOs only: preserve the actual terminal cause instead of just a
    // browser assertion. No headers, credential settings or raw model body.
    result.failure_state=await page.evaluate(async()=>{
      const read=async route=>{const response=await fetch(route);return response.ok?await response.json():{http_status:response.status};};
      return {workflow:await read('/v1/product/workflow'),conversation:await read('/v1/product/conversation'),
        product:await read('/v1/product/state'),viewport:await read('/v1/product/viewport')};
    }).catch(()=>null);
    await page.screenshot({path:path.join(output,'failed-journey.png')}).catch(()=>{});
  }
}
finally{
  fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));
  try{await browser.close();result.browser_closed=true;}
  finally{fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));}
}
