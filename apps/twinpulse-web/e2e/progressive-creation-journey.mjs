// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Fresh ordinary model responses. Draft acceptance is NOT motion/quality PASS.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const specification=JSON.parse(process.env.TWINPULSE_FUNCTIONAL_CASE);
const result={status:'FAIL',checks:[],page_errors:[],input_mode:specification.input_mode,
  physical_robot_connections:0,robot_connection:'NOT_RUN',photo_fidelity:'UNMEASURED',physics_run:'NOT_RUN'};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',error=>result.page_errors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const read=async endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);if(!response.ok)throw new Error(`${endpoint}: ${response.status}`);
    return response.json();
  },endpoint);
  const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
  await expect(page.getByRole('heading',{name:'Build your Digital Twin'})).toBeVisible();
  if(specification.image){
    await page.locator('input[type=file]').setInputFiles(specification.image.path);
    await expect(page.getByAltText('Attached image preview')).toBeVisible();
  }
  await input.fill(specification.prompt);await expect(input).toHaveValue(specification.prompt);
  await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled();
  await page.screenshot({path:path.join(output,'01-actual-input.png')});
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const robotQuestion=page.getByRole('region',{name:'Do you have a physical robot?',exact:true});
  await expect(robotQuestion).toBeVisible();
  expect((await read('/v1/product/state')).operations).toEqual([]);
  expect((await read('/v1/product/conversation')).generation).toBeNull();
  await robotQuestion.getByRole('radio',{name:'Simulation only',exact:true}).check();
  await robotQuestion.getByRole('button',{name:'Continue',exact:true}).click();
  const approval=async(requestCount,filename)=>{
    let card;
    await expect.poll(async()=>{
      const chat=await read('/v1/product/conversation');
      card=chat.cards.find(c=>c.state==='waiting'&&c.kind==='generation_approval');return !!card;
    },{timeout:20000}).toBe(true);
    expect(card.generation_approval.planned_requests??card.generation_approval.policy.max_requests).toBe(requestCount);
    expect(card.generation_approval.models.every(m=>m.max_output_tokens===40000)).toBe(true);
    result.approvals??=[];result.approvals.push(card.generation_approval);
    const region=page.getByRole('region',{name:card.question,exact:true});
    await expect(region).toBeVisible();
    await region.getByLabel('Maximum spend for this action (USD)').fill('1.00');
    await page.screenshot({path:path.join(output,filename)});
    await region.getByRole('radio',{name:card.choices.find(c=>c.id==='approve').label,exact:true}).check();
    await region.getByRole('button',{name:'Continue',exact:true}).click();
  };
  await approval(12,'02-ordinary-approval.png');
  let chat;
  await expect.poll(async()=>{
    chat=await read('/v1/product/conversation');return chat.generation?.state;
  },{timeout:920000,intervals:[500,1000,2000]}).toMatch(/^(completed|failed|cancelled)$/);
  result.generation=chat.generation;
  if(chat.generation.state!=='completed')throw new Error(`GENERATION_${chat.generation.state}: ${chat.generation.summary}`);
  let workflow=await read('/v1/product/workflow');
  expect(workflow.phase).toBe('draft_ready');expect(workflow.site_draft).toBeTruthy();
  result.created_draft=workflow.site_draft;
  result.axes=workflow.site_draft.progressive_twin?.axes??null;
  result.unresolved=workflow.site_draft.progressive_twin?.unresolved??[];
  const refinement=workflow.site_draft.draft_refinement??null;
  if(refinement){
    const subset=refinement.schema_version==='draft-refinement-1.1';
    expect(refinement.schema_version).toBe(subset?'draft-refinement-1.1':'draft-refinement-1.0');
    expect(refinement.acceptance).toBe(subset?'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE':
      'GEOMETRY_VALID_REFINEMENT_INCOMPLETE');
    expect(refinement.current).toBe(true);
    expect(refinement.assessment_state).toBe('needs_revision');
    expect(refinement.physical_authority).toBe(false);
    expect(refinement.world_alignment).toBe('NOT_VERIFIED');
    expect(refinement.physical_validation).toBe('NOT_RUN');
    expect(refinement.quality_review.status).toBe('needs_revision');
    expect(refinement.quality_review.candidate_revision).toBe(refinement.candidate_revision);
    expect(refinement.quality_review.plan_sha256).toBe(refinement.plan_sha256);
    expect(refinement.quality_review.issues.length).toBeGreaterThan(0);
    expect(refinement.quality_review.issues.length).toBeLessThanOrEqual(128);
    expect(refinement.geometry_checks.checks_complete).toBe(!subset);
    expect(refinement.geometry_checks.checks_truncated).toBe(false);
    expect(refinement.geometry_checks.checks).toHaveLength(8);
    expect(refinement.geometry_checks.checks.every(check=>check.status===(subset&&check.check_id==='support_packing'?'partial':'passed')&&
      check.candidate_revision===refinement.candidate_revision)).toBe(true);
    if(subset){
      expect(refinement.geometry_checks.materialized_subset_checked).toBe(true);
      expect(refinement.geometry_checks.inventory_complete).toBe(false);
      expect(refinement.progressive_sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(result.unresolved.length).toBeGreaterThan(0);
      result.checks.push('Materialized subset only; pending inventory remains incomplete, original risk retained, whole geometry is not PASS');
    }
    expect(['QUALITY_REPAIR_LIMIT_REACHED','REPAIR_STALLED']).toContain(refinement.stop_reason);
    expect(refinement.budget.stop_reason).toBe(refinement.stop_reason);
    expect(refinement.budget.in_flight).toBeNull();
    expect(refinement.budget.attempts.every(attempt=>attempt.status==='received'&&attempt.settled===true)).toBe(true);
    result.draft_refinement=refinement;
    result.photo_fidelity='NEEDS_REVISION_NOT_QUALITY_PASS';
    const retained=page.getByRole('status',{name:'Photo refinement retained',exact:true});
    await expect(retained).toBeVisible({timeout:20000});
    await expect(retained).toContainText('Photo quality did not pass');
    await expect(retained).toContainText(refinement.stop_reason);
    for(const issue of refinement.quality_review.issues)await expect(retained).toContainText(issue.code);
    result.checks.push('Independent editable approximate draft; full photo needs_revision issues and original budget stop retained, physical authority false');
  }
  const latest=JSON.parse(fs.readFileSync(path.join(output,'runtime/active_project.json'),'utf8')).latest_input;
  expect(latest.prompt).toBe(specification.prompt);
  expect(latest.images.map(image=>image.sha256)).toEqual(specification.image?[specification.image.sha256]:[]);
  const currentFrame=async(revision,filename)=>{
    const view=page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/});
    let buildCommand,viewAction='existing_owned_build';
    const currentBuilds=async()=> (await read('/v1/product/state')).operations.filter(
      op=>op.command_type==='build_site_scene'&&op.expected_applied_revision===revision);
    // SIM preparation can already own the exact Build and remove the View CTA.
    // Do not require a second click, or accept a revision-only/stale frame.
    if(!(await currentBuilds()).length&&await view.count()&&await view.isEnabled()){
      const responsePromise=page.waitForResponse(response=>{
          if(!response.url().endsWith('/v1/product/commands')||response.request().method()!=='POST')return false;
          const command=response.request().postDataJSON();
          return command.command_type==='build_site_scene'&&command.expected_applied_revision===revision;
        },{timeout:10000}).catch(()=>null);
      try{
        await view.click({timeout:3000});
        const response=await responsePromise;
        if(!response)throw new Error('Explicit View Build response missing');
        if(!response.ok())throw new Error(`Explicit View Build HTTP ${response.status()}`);
        buildCommand=(await response.json()).command_id;
        if(!buildCommand)throw new Error('Explicit View did not return its Build identity');
        viewAction='explicit_view_build';
      }catch(error){
        // Only DOM disappearance/disable caused by an observed matching owned
        // automatic Build can substitute for a click. HTTP/identity errors fail.
        if(error.name!=='TimeoutError'||!(await currentBuilds()).length||
            await view.count()&&await view.isEnabled())throw error;
        viewAction='automatic_build_won_cta_race';
      }
    }
    let state;
    await expect.poll(async()=>{
      state=await read('/v1/product/state');
      const builds=state.operations.filter(op=>op.command_type==='build_site_scene'&&op.expected_applied_revision===revision);
      const target=buildCommand?builds.find(op=>op.command_id===buildCommand):builds.at(-1);
      if(!target)return null;
      buildCommand??=target.command_id;
      if(target.status!=='succeeded')return target.status;
      return state.build_view?.command_id===buildCommand&&state.build_view.status==='succeeded'&&
        !state.operations.some(op=>['accepted','running'].includes(op.status))?'display_ready':'pending';
    },{timeout:60000}).toBe('display_ready');
    await expect.poll(async()=>(await read('/v1/product/state')).snapshot?.applied_revision,{timeout:60000}).toBe(revision);
    await expect.poll(async()=>(await read('/v1/product/viewport')).frame?.applied_revision,{timeout:60000}).toBe(revision);
    // A revision is reusable. Require a new frame after this exact Build was
    // observed terminal; an earlier same-revision frame cannot pass the test.
    const acknowledgedFrame=(await read('/v1/product/viewport')).frame;
    await expect.poll(async()=>{
      const frame=(await read('/v1/product/viewport')).frame;
      return !!frame&&frame.engine_session_id===state.build_view.engine_session_id&&
        frame.stage_epoch===state.build_view.stage_epoch&&frame.applied_revision===revision&&
        frame.frame_id>acknowledgedFrame.frame_id;
    },{timeout:20000}).toBe(true);
    result.display_bindings??=[];result.display_bindings.push({build_command_id:buildCommand,view_action:viewAction,
      build_view:state.build_view,post_ack_frame_id:(await read('/v1/product/viewport')).frame.frame_id});
    const panel=page.getByRole('complementary',{name:'Digital Twin'});
    const canvas=panel.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true});
    await expect(canvas).toBeVisible({timeout:20000});
    const bound=await read('/v1/product/viewport');
    await expect.poll(async()=>Number(await canvas.getAttribute('data-captured-at')),{timeout:20000}).toBeGreaterThanOrEqual(bound.frame.captured_at_ms);
    await expect(panel.getByText(/^Live (Isaac render|render · reduced frame rate)/)).toBeVisible();
    await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(
      'Preparing the current Twin in Isaac',{timeout:15000});
    await page.screenshot({path:path.join(output,filename)});
    return (await read('/v1/product/viewport')).frame;
  };
  // View-only or the already-owned SIM-preparation Build; no Run follows.
  result.created_frame=await currentFrame(workflow.site_draft.revision,'03-created-current-twin.png');
  result.checks.push('Exact fresh text/image input, explicit approval, persisted approximate draft and current Isaac canvas; pending/estimates retained');
  if(specification.feedback){
    result.feedback_trials=[];
    for(const editKind of specification.feedback_kinds??['move']){
    const calls=workflow.site_draft.editable_calls;
    const parents=new Set(calls.filter(c=>c.tool==='set_item_placement').map(c=>c.arguments.parent_id));
    const call=(editKind==='resize'?calls.find(c=>c.tool==='place_furniture'&&parents.has(c.arguments.id)):null)
      ??calls.find(c=>c.tool==='place_furniture');
    if(!call)throw new Error('No editable furniture exists for the declared natural-feedback case');
    const field=editKind==='resize'?'dimensions_m':'center_m';
    const before=structuredClone(call.arguments[field]);
    const after=editKind==='resize'?[Number((before[0]*.98).toFixed(6)),Number((before[1]*.98).toFixed(6)),before[2]]:
      [before[0]+(before[0]>0?-.05:.05),before[1]];
    const text=editKind==='resize'?
      `Resize only furniture with exact object id ${call.arguments.id} so dimensions_m is ${JSON.stringify(after)} metres. Keep its center, height, id, kind, yaw and every other object. Preserve attached children, pending items and support relations using the dependency edit path. Do not regenerate the scene. These are user estimates, not physical measurements.`:
      `Move only the furniture with exact object id ${call.arguments.id} so its center_m is ${JSON.stringify(after)} metres. Preserve its id, dimensions, kind, yaw, support relations and all other room objects. Do not regenerate the scene. I am providing an edit to the current approximate Twin, not measured physical coordinates.`;
    result.feedback_request={kind:editKind,target_id:call.arguments.id,field,before,after,text};
    await input.fill(text);
    await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled({timeout:20000});
    await page.getByRole('button',{name:'Send',exact:true}).click();
    await approval(1,`04-${editKind}-feedback-model-approval.png`);
    let card;
    await expect.poll(async()=>{
      chat=await read('/v1/product/conversation');
      card=chat.cards.find(c=>c.state==='waiting'&&c.kind==='scene_edit');
      return card?'proposal':chat.scene_feedback?.state==='failed'?'failed':chat.scene_feedback?.state==='clarify'?'clarify':null;
    },{timeout:320000,intervals:[500,1000,2000]}).toMatch(/^(proposal|failed|clarify)$/);
    result.fresh_feedback=chat.scene_feedback;
    if(!card){
      await expect(page.getByRole('status',{name:'Scene feedback status',exact:true}))
        .toContainText(`Scene feedback · ${chat.scene_feedback.state.replaceAll('_',' ')}`,{timeout:20000});
      result.failed_feedback_ui_settled=true;
      throw new Error('Fresh feedback did not produce an applicable proposal; retained without implicit repair');
    }
    const region=page.getByRole('region',{name:card.question,exact:true});await expect(region).toBeVisible();
    await page.screenshot({path:path.join(output,`05-${editKind}-feedback-preview.png`)});
    const previousTransaction=await read('/v1/product/scene-edit/transaction');
    const oldFailedMessages=new Set((await read('/v1/product/conversation')).messages.filter(m=>m.status==='failed').map(m=>m.message_id));
    const appliedState=async(previousId)=>{
      const current=await read('/v1/product/scene-edit/transaction');
      const session=await read('/v1/product/conversation');
      const rejection=session.messages.find(m=>m.role==='assistant'&&m.status==='failed'&&!oldFailedMessages.has(m.message_id));
      if(rejection){
        result.apply_rejection=rejection;
        await expect(page.getByText(rejection.content,{exact:true})).toBeVisible({timeout:20000});
        throw new Error(`Actual Apply rejected: ${rejection.content}`);
      }
      return current&&current.operation_id!==previousId?current:null;
    };
    await region.getByRole('radio',{name:'Apply and update Twin',exact:true}).check();
    await region.getByRole('button',{name:'Continue',exact:true}).click();
    let transaction;
    await expect.poll(async()=>{transaction=await appliedState(previousTransaction?.operation_id);return transaction?.state??null;},
      {timeout:135000}).toMatch(/^(COMMITTED|ROLLED_BACK|ENGINE_STATE_UNKNOWN)$/);
    result.feedback_transaction=transaction;expect(transaction.state).toBe('COMMITTED');
    result.feedback_frame=await currentFrame(transaction.result_revision,`06-${editKind}-fresh-feedback-current.png`);
    workflow=await read('/v1/product/workflow');
    expect(workflow.site_draft.editable_calls.find(c=>c.arguments.id===call.arguments.id).arguments[field]).toEqual(after);
    await input.fill('Undo');
    await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled({timeout:20000});
    await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect.poll(async()=>{
      const state=await read('/v1/product/conversation');card=state.cards.find(c=>c.state==='waiting'&&c.kind==='scene_edit');return !!card;
    },{timeout:20000}).toBe(true);
    const undoRegion=page.getByRole('region',{name:card.question,exact:true});await expect(undoRegion).toBeVisible();
    await undoRegion.getByRole('radio',{name:'Apply and update Twin',exact:true}).check();
    await undoRegion.getByRole('button',{name:'Continue',exact:true}).click();
    await expect.poll(async()=>{transaction=await appliedState(result.feedback_transaction.operation_id);return transaction?.operation_id??result.feedback_transaction.operation_id;},
      {timeout:20000}).not.toBe(result.feedback_transaction.operation_id);
    await expect.poll(async()=>{transaction=await appliedState(result.feedback_transaction.operation_id);return transaction?.state??null;},
      {timeout:135000}).toBe('COMMITTED');
    result.undo_transaction=transaction;result.undo_frame=await currentFrame(transaction.result_revision,`07-${editKind}-fresh-feedback-undo.png`);
    workflow=await read('/v1/product/workflow');
    expect(workflow.site_draft.editable_calls.find(c=>c.arguments.id===call.arguments.id).arguments[field]).toEqual(before);
    result.feedback_trials.push({request:result.feedback_request,proposal:result.fresh_feedback,
      transaction:result.feedback_transaction,frame:result.feedback_frame,undo:transaction,undo_frame:result.undo_frame});
    result.checks.push('Fresh Super proposal via ordinary feedback approval, checked Apply/current canvas and local Undo; no response substitution');
    }
  }
  workflow=await read('/v1/product/workflow');result.final_draft=workflow.site_draft;
  const state=await read('/v1/product/state');result.operations=state.operations;
  expect(state.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
  result.diagnostics=await read('/v1/product/diagnostics?limit=100');
  const count=state.operations.length;await page.reload();
  await expect(page.getByRole('complementary',{name:'Digital Twin'}).getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:20000});
  expect((await read('/v1/product/state')).operations).toHaveLength(count);
  expect((await read('/v1/product/workflow')).site_draft.revision).toBe(workflow.site_draft.revision);
  expect((await read('/v1/product/workflow')).site_draft.draft_refinement??null)
    .toEqual(workflow.site_draft.draft_refinement??null);
  await page.screenshot({path:path.join(output,'08-reloaded-current.png')});
  expect(result.page_errors).toEqual([]);result.status='PASS';
}catch(error){
  result.error_type=error.name;result.error=String(error).slice(0,3000);
  if(page)try{await page.screenshot({path:path.join(output,'failed-current-screen.png')});}catch{}
}finally{
  if(browser)await browser.close();fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));
}
if(result.status!=='PASS')process.exitCode=1;
