// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Explicit synthetic typed transport + unchanged original recordings, not live.
import {chromium, expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {freshGoalReview} from './benchmark-journey-policy.mjs';

const output=process.env.TWINPULSE_VIEW_OUTPUT;
const packet=JSON.parse(process.env.TWINPULSE_SENSOR_PACKET);
const phase=process.env.TWINPULSE_SENSOR_PHASE||'sensor';
const result={status:'FAIL',provider_calls:0,physical_robot_connections:0,physics_run:'NOT_RUN',
  positive_transport:'SYNTHETIC_TRANSPORT',page_errors:[],steps:[],real_reviews:[]};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',error=>result.page_errors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const read=async endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);const body=await response.json();
    if(!response.ok)throw new Error(`${endpoint}: ${response.status} ${body.error?.code||''}`);
    return body;
  },endpoint);
  const postRaw=async(endpoint,body)=>page.evaluate(async({endpoint,body})=>{
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
      'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
    return {status:response.status,value:await response.json()};
  },{endpoint,body});
  const waiting=async kind=>{
    let chat;
    await expect.poll(async()=>{chat=await read('/v1/product/conversation');
      return chat.cards.filter(c=>c.state==='waiting').map(c=>c.kind);},{timeout:30000}).toEqual([kind]);
    return chat.cards.find(c=>c.state==='waiting');
  };
  const choose=async(kind,identity)=>{
    const card=await waiting(kind);
    const option=card.choices.find(c=>c.id===identity||c.label===identity);
    expect(option?.enabled).toBe(true);
    const region=page.getByRole('region',{name:card.question,exact:true});
    await expect(region).toBeVisible();
    if(card.choices.filter(c=>c.enabled).length===1){
      await region.getByRole('button',{name:option.label,exact:true}).click();
    }else{
      await region.getByRole('radio',{name:option.label,exact:true}).check();
      await region.getByRole('button',{name:'Continue',exact:true}).click();
    }
    return card;
  };
  const workflow=()=>read('/v1/product/workflow');
  const calls=async()=>Object.fromEntries((await workflow()).site_draft.editable_calls.map(c=>[c.arguments.id,c]));
  const buildCount=async()=>(await read('/v1/product/state')).operations.filter(o=>o.command_type==='build_site_scene').length;
  const waitFrame=async(revision,name)=>{
    let state;
    await expect.poll(async()=>{state=await read('/v1/product/state');
      const build=state.operations.filter(o=>o.command_type==='build_site_scene'&&o.expected_applied_revision===revision).at(-1);
      return !!build&&build.status==='succeeded'&&state.build_view?.command_id===build.command_id&&
        state.build_view.status==='succeeded'&&state.snapshot?.applied_revision===revision&&
        !state.operations.some(o=>['accepted','running'].includes(o.status));},{timeout:135000}).toBe(true);
    await expect.poll(async()=>(await read('/v1/product/viewport')).frame?.applied_revision,{timeout:45000}).toBe(revision);
    const panel=page.getByRole('complementary',{name:'Digital Twin'});
    const canvas=panel.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true});
    await expect(canvas).toBeVisible({timeout:15000});
    const viewport=await read('/v1/product/viewport');
    await expect.poll(async()=>Number(await canvas.getAttribute('data-captured-at')),{timeout:15000}).toBeGreaterThanOrEqual(viewport.frame.captured_at_ms);
    await expect(panel.getByText(/^Live (Isaac render|render · reduced frame rate)/)).toBeVisible();
    await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(
      'Preparing the current Twin in Isaac',{timeout:15000});
    expect((await read('/v1/product/state')).operations.filter(o=>o.command_type==='run')).toHaveLength(0);
    await page.screenshot({path:path.join(output,name)});
    return {snapshot:state.snapshot,frame:viewport.frame,build_count:await buildCount()};
  };
  await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
  await expect.poll(async()=>(await workflow()).phase,{timeout:15000}).toBe('draft_ready');
  const reopened=await workflow();
  await page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/}).click();
  result.initial=await waitFrame(reopened.site_draft.revision,phase==='restart'?'09-closed-restart-current.png':'01-stored-source-current.png');
  if(phase!=='restart'){
    const context=await read('/v1/product/scene-edit/sensor-context');
    expect(context.physical_authority).toBe(false);
    expect(context.current_scene_revision).toBe(packet.source_revision);
    const initialCalls=await calls();
    const initialBuilds=await buildCount();
    let positive=packet.positive;
    const select=page.getByLabel('Saved sensor map',{exact:true});
    const reviewButton=page.getByRole('button',{name:'Review saved sensor feedback',exact:true});
    const begin=async map=>{
      await expect(select).toBeEnabled({timeout:15000});
      await select.selectOption(map.map_id);
      await expect(reviewButton).toBeEnabled();
      await reviewButton.click();
      return waiting('scene_sensor_policy');
    };
    const settled=async()=>{
      let chat;
      await expect.poll(async()=>{chat=await read('/v1/product/conversation');
        return chat.cards.filter(c=>c.state==='waiting').length;},{timeout:45000}).toBe(0);
      await expect(page.getByRole('status',{name:'Saved sensor review result',exact:true})).toBeVisible();
      return chat.scene_sensor_review;
    };
    const replan=async(revision,filename)=>{
      const before=await read('/v1/product/conversation');
      const {start,goal}=packet.sim_goal_revalidation;
      const text=`Go from X=${start[0]} Y=${start[1]} to X=${goal[0]} Y=${goal[1]}`;
      const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
      await expect(input).toBeEnabled();await input.fill(text);
      await page.getByRole('button',{name:'Send',exact:true}).click();
      let checked;
      await expect.poll(async()=>{
        try{checked=freshGoalReview(before,await read('/v1/product/conversation'),text,revision);
          return !!checked.review.plan;}catch{return false;}
      },{timeout:20000}).toBe(true);
      expect(checked.review.plan.physical_authority).toBe(false);
      await expect(page.getByRole('region',{name:'Simulation route',exact:true})).toHaveAttribute('data-plan-id',checked.review.plan.plan_id);
      expect((await read('/v1/product/state')).operations.filter(o=>o.command_type==='run')).toHaveLength(0);
      await page.screenshot({path:path.join(output,filename)});
      return checked;
    };
    if(packet.import_survey_requested){
      const catalogBefore=await read('/v1/product/automatic-demo/maps');
      const surveys=await read('/v1/product/scene-edit/sensor-surveys');
      expect(surveys.physical_authority).toBe(false);
      const survey=surveys.surveys.find(s=>s.mission_id===packet.survey.mission_id);
      expect(survey?.status).toBe('READY');
      expect(survey.report_revision).toBe(packet.survey.report_revision);
      expect(survey.provenance).toBe('SYNTHETIC_TRANSPORT');
      expect(catalogBefore.maps.some(m=>m.map_id===packet.survey.expected_map_id)).toBe(false);
      await page.getByLabel('Completed survey',{exact:true}).selectOption(survey.mission_id);
      const importButton=page.getByRole('button',{name:'Import saved survey',exact:true});
      await expect(importButton).toBeEnabled();await importButton.click();
      await expect.poll(async()=>(await read('/v1/product/conversation')).scene_sensor_review?.status,
        {timeout:45000}).toBe('imported');
      result.survey_import=(await read('/v1/product/conversation')).scene_sensor_review;
      expect(result.survey_import.map_id).toBe(packet.survey.expected_map_id);
      expect(result.survey_import.physical_authority).toBe(false);
      expect(result.survey_import.current_pose_available).toBe(false);
      expect(result.survey_import.evidence.provenance).toBe('SYNTHETIC_TRANSPORT');
      expect(result.survey_import.duplicate).toBe(false);
      positive={...packet.positive,map_id:result.survey_import.map_id,map_revision:result.survey_import.map_revision};
      const catalogAfter=await read('/v1/product/automatic-demo/maps');
      expect(catalogAfter.maps.length).toBe(catalogBefore.maps.length+1);
      expect(await buildCount()).toBe(initialBuilds);expect(await calls()).toEqual(initialCalls);
      expect(await read('/v1/product/scene-edit/sensor-context')).toEqual(context);
      expect((await read('/v1/product/conversation')).cards.filter(c=>c.state==='waiting')).toHaveLength(0);
      await expect(select).toHaveValue(positive.map_id);
      await expect(importButton).toBeDisabled();
      result.duplicate_import=await postRaw('/v1/product/conversation',{action:'sensor_import',request_id:crypto.randomUUID(),
        mission_id:survey.mission_id,expected_report_revision:survey.report_revision,
        expected_scene_revision:context.current_scene_revision,expected_state_sha256:context.current_state_sha256});
      expect(result.duplicate_import.status).toBe(200);
      const duplicate=(await read('/v1/product/conversation')).scene_sensor_review;
      expect(duplicate.status).toBe('imported');expect(duplicate.duplicate).toBe(true);
      expect(duplicate.map_id).toBe(positive.map_id);expect(duplicate.map_revision).toBe(positive.map_revision);
      expect((await read('/v1/product/automatic-demo/maps')).maps).toEqual(catalogAfter.maps);
      expect(await buildCount()).toBe(initialBuilds);expect(await calls()).toEqual(initialCalls);
      expect(await read('/v1/product/scene-edit/sensor-context')).toEqual(context);
      await page.screenshot({path:path.join(output,'02a-completed-survey-imported.png')});
    }
    await begin(positive);
    await page.screenshot({path:path.join(output,'02-one-sensor-policy.png')});
    await choose('scene_sensor_policy','cancel');
    await expect.poll(async()=>(await read('/v1/product/conversation')).cards.filter(c=>c.state==='waiting').length).toBe(0);
    expect(await buildCount()).toBe(initialBuilds);
    expect(await calls()).toEqual(initialCalls);
    result.cancel_no_mutation=true;
    await begin(positive);
    await choose('scene_sensor_policy','align_only');
    result.align_only=await settled();
    expect(result.align_only.status).toBe('POSE_CANDIDATE');
    expect(result.align_only.physical_authority).toBe(false);
    expect(result.align_only.current_pose_available).toBe(false);
    expect(result.align_only.preview).toBeNull();
    expect(await buildCount()).toBe(initialBuilds);
    expect(await calls()).toEqual(initialCalls);
    await page.screenshot({path:path.join(output,'03-pose-only-not-current.png')});
    if(packet.sim_goal_revalidation){
      result.goal_before_sensor=await replan(context.current_scene_revision,'03a-before-sensor-goal-review.png');
      expect(await buildCount()).toBe(initialBuilds);
    }
    await begin(positive);
    await choose('scene_sensor_policy','correct_walls');
    await waiting('scene_edit');
    const proposal=await read('/v1/product/conversation');
    result.sensor_preview=proposal.scene_edit_preview;
    const binding=proposal.scene_edit_preview.sensor_binding;
    expect(binding.physical_authority).toBe(false);
    expect(binding.evidence.provenance).toBe('SYNTHETIC_TRANSPORT');
    expect(binding.evidence.map_id).toBe(positive.map_id);
    expect(binding.evidence.raw_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(binding.context).toEqual(context);
    expect(proposal.scene_edit_preview.operation.mode).toBe('dependency');
    await page.screenshot({path:path.join(output,'04-bounded-wall-preview.png')});
    await choose('scene_edit','Apply and update Twin');
    let transaction;
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.state;},{timeout:135000}).toBe('COMMITTED');
    result.apply_transaction=transaction;
    result.applied=await waitFrame(transaction.result_revision,'05-sensor-applied-current.png');
    if(packet.sim_goal_revalidation){
      expect((await read('/v1/product/conversation')).simulation_review).toBeNull();
      result.goal_after_sensor=await replan(transaction.result_revision,'05a-after-sensor-goal-review.png');
      expect(result.goal_after_sensor.review.plan.plan_id).not.toBe(result.goal_before_sensor.review.plan.plan_id);
      result.sensor_goal_revalidated_without_run=true;
    }
    const changed=await calls();
    const targets=result.sensor_preview.operation.dependency_patch.edits.map(e=>e.target_id);
    expect(targets.length).toBeGreaterThanOrEqual(1);expect(targets.length).toBeLessThanOrEqual(2);
    for(const [id,call] of Object.entries(initialCalls)){
      if(!targets.includes(id)){expect(changed[id]).toEqual(call);continue;}
      expect(call.tool).toBe('create_wall');
      const delta=Math.hypot(...call.arguments.position_m.slice(0,2).map((v,i)=>changed[id].arguments.position_m[i]-v));
      expect(delta).toBeGreaterThan(.001);expect(delta).toBeLessThanOrEqual(.200000001);
    }
    const beforeStale=await buildCount();
    result.stale_request=await postRaw('/v1/product/conversation',{action:'sensor_review',request_id:crypto.randomUUID(),
      map_id:positive.map_id,expected_map_revision:positive.map_revision,
      expected_scene_revision:context.current_scene_revision,expected_state_sha256:context.current_state_sha256});
    expect(result.stale_request.status).toBe(409);expect(await buildCount()).toBe(beforeStale);
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    await expect(input).toBeEnabled();await input.fill('Undo');await page.getByRole('button',{name:'Send',exact:true}).click();
    await choose('scene_edit','Apply and update Twin');
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.operation_id;},{timeout:30000}).not.toBe(result.apply_transaction.operation_id);
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.state;},{timeout:135000}).toBe('COMMITTED');
    result.undo_transaction=transaction;
    result.undone=await waitFrame(transaction.result_revision,'06-sensor-undo-current.png');
    if(packet.sim_goal_revalidation){
      expect((await read('/v1/product/conversation')).simulation_review).toBeNull();
      result.goal_after_undo=await replan(transaction.result_revision,'06a-after-undo-goal-review.png');
      expect(result.goal_after_undo.review.plan.plan_id).not.toBe(result.goal_after_sensor.review.plan.plan_id);
    }
    expect(await calls()).toEqual(initialCalls);
    expect(transaction.result_revision).not.toBe(context.current_scene_revision);
    const beforeHeld=await buildCount();
    await begin(packet.pose_only);await choose('scene_sensor_policy','align_only');
    result.pose_only=await settled();
    expect(result.pose_only.status).toBe('POSE_CANDIDATE');
    expect(result.pose_only.preview).toBeNull();expect(await buildCount()).toBe(beforeHeld);
    for(const map of packet.real_maps){
      await begin(map);await choose('scene_sensor_policy','correct_walls');
      const held=await settled();result.real_reviews.push({map,...held});
      expect(held.status).toBe('HELD');expect(held.physical_authority).toBe(false);
      expect(held.current_pose_available).toBe(false);expect(held.preview).toBeNull();
      expect(await buildCount()).toBe(beforeHeld);expect(await calls()).toEqual(initialCalls);
    }
    await page.screenshot({path:path.join(output,'07-recorded-data-held.png')});
    const beforeReload=await buildCount();await page.reload();
    await waitFrame(transaction.result_revision,'08-reloaded-current.png');
    expect(await buildCount()).toBe(beforeReload);
  }
  const final=await workflow();
  result.final_revision=final.site_draft.revision;
  result.final_state_sha256=final.site_draft.scene_state_sha256;
  result.diagnostics=await read('/v1/product/diagnostics?limit=100');
  expect(result.page_errors).toEqual([]);
  expect((await read('/v1/product/state')).operations.filter(o=>o.command_type==='run')).toHaveLength(0);
  result.status='PASS';
}catch(error){
  result.error_type=error.constructor.name;result.error=String(error);
  if(page)await page.screenshot({path:path.join(output,`${phase}-failure.png`)}).catch(()=>{});
}finally{
  await browser?.close();
  fs.writeFileSync(path.join(output,`${phase}-browser.json`),JSON.stringify(result,null,2));
}
if(result.status!=='PASS')process.exitCode=1;
