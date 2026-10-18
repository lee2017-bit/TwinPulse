// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Explicit synthetic support graph. Actual App/API/Isaac, never a model score.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const output=process.env.TWINPULSE_VIEW_OUTPUT;
const source=JSON.parse(process.env.TWINPULSE_EDIT_SOURCE_JSON);
const phase=process.env.TWINPULSE_EDIT_PHASE||'edit';
const feedback=process.env.TWINPULSE_EDIT_FEEDBACK==='1';
const fault=process.env.TWINPULSE_EDIT_FAULT||'';
const full=source.full_geometry_refinement;
const native=source.native_pending_refinement||full;
const result={status:'FAIL',provider_calls:0,physical_robot_connections:0,steps:[],page_errors:[],
  history_path:'active_project.scene-changes.json'};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',error=>result.page_errors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const read=async endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);const value=await response.json();
    if(!response.ok)throw new Error(`${endpoint}: HTTP ${response.status} ${value.error?.code??''}`);
    return value;
  },endpoint);
  const post=async(endpoint,body)=>page.evaluate(async({endpoint,body})=>{
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
      'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
    const value=await response.json();
    if(!response.ok)throw new Error(`${endpoint}: HTTP ${response.status} ${value.error?.code??''}`);
    return {status:response.status,value};
  },{endpoint,body});
  const savedChat=page.getByRole('button',{name:/^Open saved chat ·/});
  const savedScene=page.getByRole('button',{name:'Reopen saved scene',exact:true});
  await expect.poll(async()=>await savedChat.count()||await savedScene.count(),{timeout:20000}).toBeGreaterThan(0);
  if(await savedChat.count()){
    await savedChat.click();result.explicit_saved_chat_open=true;
  }
  const showTwin=page.getByRole('button',{name:'Show Twin',exact:true});
  if(await showTwin.count())await showTwin.click();
  await expect(savedScene).toBeVisible();
  await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
  await expect.poll(async()=>(await read('/v1/product/workflow')).phase,{timeout:10000}).toBe('draft_ready');
  const restoredState=await read('/v1/product/workflow');
  const viewDraft=page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/});
  await expect(viewDraft).toBeEnabled({timeout:15000});
  // Explicit browser-transport delay, not a fake engine receipt: prove that a
  // typed draft/Enter cannot silently dispatch feedback during local Build.
  let releaseBuild;
  const buildGate=new Promise(resolve=>{releaseBuild=resolve;});
  if(feedback&&phase==='edit'){
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    await input.fill('Move the support');
    await page.route('**/v1/product/commands',async route=>{
      const body=route.request().postDataJSON();
      if(body?.command_type==='build_site_scene')await buildGate;
      await route.continue();
    });
  }
  await viewDraft.click();
  if(feedback&&phase==='edit'){
    try{
      const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
      const before=await read('/v1/product/conversation');
      await expect(page.getByRole('button',{name:'Send',exact:true})).toBeDisabled();
      await input.press('Enter');
      expect((await read('/v1/product/conversation')).messages).toEqual(before.messages);
      await expect(input).toHaveValue('Move the support');
      result.build_feedback_admission={status:'PASS',transport_delay:'explicit browser Build request gate',
        send_disabled:true,enter_dispatches:0,draft_preserved:true,engine_receipt_substitution:false};
    }finally{releaseBuild();}
  }
  const waitFrame=async(revision,filename)=>{
    let buildState;
    await expect.poll(async()=>{
      buildState=await read('/v1/product/state');
      const target=buildState.operations.filter(op=>op.command_type==='build_site_scene'&&op.expected_applied_revision===revision).at(-1);
      return !!target&&target.status==='succeeded'&&buildState.build_view?.command_id===target.command_id&&
        buildState.build_view.status==='succeeded'&&!buildState.operations.some(op=>['accepted','running'].includes(op.status));
    },{timeout:45000}).toBe(true);
    await expect.poll(async()=>(await read('/v1/product/state')).snapshot?.applied_revision,{timeout:45000}).toBe(revision);
    await expect.poll(async()=>(await read('/v1/product/viewport')).frame?.applied_revision,{timeout:45000}).toBe(revision);
    const acknowledgedFrame=(await read('/v1/product/viewport')).frame;
    await expect.poll(async()=>{
      const frame=(await read('/v1/product/viewport')).frame;
      return !!frame&&frame.applied_revision===revision&&frame.engine_session_id===buildState.build_view.engine_session_id&&
        frame.stage_epoch===buildState.build_view.stage_epoch&&frame.frame_id>acknowledgedFrame.frame_id;
    },{timeout:30000}).toBe(true);
    const panel=page.getByRole('complementary',{name:'Digital Twin'});
    const canvas=panel.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true});
    await expect(canvas).toBeVisible({timeout:15000});
    const frame=await read('/v1/product/viewport');
    await expect.poll(async()=>Number(await canvas.getAttribute('data-captured-at')),{timeout:15000}).toBeGreaterThanOrEqual(frame.frame.captured_at_ms);
    await expect(panel.getByText(/^Live (Isaac render|render · reduced frame rate)/)).toBeVisible();
    const state=await read('/v1/product/state');
    expect(state.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(/Preparing (the )?current Twin/,{timeout:15000});
    await page.screenshot({path:path.join(output,filename)});
    return {frame:frame.frame,snapshot:state.snapshot,build_count:state.operations.filter(op=>op.command_type==='build_site_scene').length};
  };
  result.initial=await waitFrame(restoredState.site_draft.revision,
    phase==='restart'?'09-closed-restart-current.png':'01-partial-original.png');
  const finish=async()=>{
    const current=await read('/v1/product/workflow');
    result.final_revision=current.site_draft.revision;
    result.final_state_sha256=current.site_draft.scene_state_sha256;
    if(native){
      expect(current.site_draft.progressive_twin).toEqual(native.progressive_twin);
      expect(current.site_draft.draft_refinement).toEqual(native.draft_refinement);
      expect(current.site_draft.run_allowed).toBe(false);
      result.final_progressive=current.site_draft.progressive_twin;
      result.final_refinement=current.site_draft.draft_refinement;
      result.fixture_provenance=native.provenance;
      result.live_photo_quality='NOT_RUN';result.physics_run='NOT_RUN';
    }
    result.diagnostics=await read('/v1/product/diagnostics?limit=100');
    result.page_errors.length===0||(()=>{throw new Error('Unexpected page error');})();
    result.status='PASS';
  };
  if(phase==='restart'){
    expect((await read('/v1/product/state')).operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    result.closed_runtime_reopen=true;
    await finish();
  }else if(native){
    expect(native.site_schema_version).toBe('2.3');
    expect(native.source_progressive_schema_version).toBe('progressive-twin-1.0');
    expect(native.progressive_twin.schema_version).toBe('progressive-twin-1.1');
    const original=await read('/v1/product/workflow');
    const pending=native.progressive_twin.unresolved[0];
    const immutableRefinement=value=>Object.fromEntries(Object.entries(value).filter(([key])=>
      !['current','assessment_state','world_alignment','physical_validation'].includes(key)));
    const checked=async current=>{
      const draft=(await read('/v1/product/workflow')).site_draft;
      expect(draft.run_allowed).toBe(false);
      expect(draft.progressive_twin.schema_version).toBe('progressive-twin-1.1');
      expect(draft.progressive_twin.inventory_count).toBe(native.progressive_twin.inventory_count);
      expect(draft.progressive_twin.materialized_count).toBe(native.progressive_twin.materialized_count);
      if(!full){
        expect(draft.progressive_twin.unresolved).toHaveLength(1);
        const issue=draft.progressive_twin.unresolved[0];
        for(const key of ['id','parent_id','hazard','bounds_z_m','source','evidence'])expect(issue[key]).toEqual(pending[key]);
        expect(issue.hazard).toBe('entanglement');expect(issue.bounds_z_m[0]).toBe(0);
      }else{
        expect(draft.progressive_twin.unresolved).toEqual([]);
        expect(draft.progressive_twin.materialized_count).toBe(draft.progressive_twin.inventory_count);
        expect(draft.draft_refinement.schema_version).toBe('draft-refinement-1.0');
        expect(draft.draft_refinement.acceptance).toBe('GEOMETRY_VALID_REFINEMENT_INCOMPLETE');
      }
      expect(immutableRefinement(draft.draft_refinement)).toEqual(immutableRefinement(native.draft_refinement));
      expect(draft.draft_refinement.current).toBe(current);
      expect(draft.draft_refinement.assessment_state).toBe(current?'needs_revision':'recheck_required');
      expect(draft.draft_refinement.physical_validation).toBe('NOT_RUN');
      expect(draft.draft_refinement.world_alignment).toBe('NOT_VERIFIED');
      expect(draft.draft_refinement.geometry_checks.checks_complete).toBe(!!full);
      if(!full){
        expect(draft.draft_refinement.geometry_checks.materialized_subset_checked).toBe(true);
        expect(draft.draft_refinement.geometry_checks.inventory_complete).toBe(false);
        expect(draft.draft_refinement.geometry_checks.checks.filter(r=>r.status==='passed')).toHaveLength(7);
        expect(draft.draft_refinement.geometry_checks.checks.find(r=>r.check_id==='support_packing').status).toBe('partial');
      }else expect(draft.draft_refinement.geometry_checks.checks.filter(r=>r.status==='passed')).toHaveLength(8);
      expect(draft.draft_refinement.quality_review.status).toBe('needs_revision');
      return draft;
    };
    await checked(true);
    expect(original.site_draft.progressive_twin).toEqual(native.progressive_twin);
    expect(original.site_draft.draft_refinement).toEqual(native.draft_refinement);
    await expect(page.getByRole('status',{name:'Photo refinement retained',exact:true})).toContainText(
      full?'The saved candidate passed its geometry compiler checks. All objects remain represented.':
      'The materialized subset passed its remaining compiler checks. Unresolved support objects remain pending; whole-inventory geometry did not pass.');
    const committed=async(operationId,filename)=>{
      let transaction;
      await expect.poll(async()=>{
        transaction=await read('/v1/product/scene-edit/transaction');
        return transaction?.operation_id===operationId&&['COMMITTED','ROLLED_BACK','ENGINE_STATE_UNKNOWN','CANCELLED_BEFORE_DISPATCH'].includes(transaction.state);
      },{timeout:135000}).toBe(true);
      expect(transaction.state).toBe('COMMITTED');expect(transaction.engine_acknowledged).toBe(true);
      expect(transaction.durable_committed).toBe(true);
      const actual=await waitFrame(transaction.result_revision,filename);
      return {transaction,actual};
    };
    const apply=async(operation_id,edits,filename)=>{
      const preview=(await post('/v1/product/scene-edit/preview',{operation_id,mode:'dependency',target_call_id:null,
        tool_call:{patch_version:'scene-dependency-patch-1.0',edits}})).value;
      const body={schema_version:'scene-edit-apply-2.0',operation:preview.operation,preview_digest:preview.preview_digest};
      expect((await post('/v1/product/scene-edit/apply',body)).status).toBe(202);
      const evidence=await committed(operation_id,filename);
      expect(evidence.transaction.result_revision).toBe(preview.result_revision);
      const duplicate=await post('/v1/product/scene-edit/apply',body);
      expect(duplicate.value.operation_id).toBe(operation_id);
      expect((await read('/v1/product/state')).operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(evidence.actual.build_count);
      result.steps.push({operation_id,preview,...evidence,duplicate_dispatch:false});
    };
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    const send=async text=>{await input.fill(text);await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled({timeout:15000});await page.getByRole('button',{name:'Send',exact:true}).click();};
    const undo=async(filename)=>{
      const previous=await read('/v1/product/scene-edit/transaction');
      await send('Undo');let card;
      await expect.poll(async()=>{
        const chat=await read('/v1/product/conversation');card=chat.cards.find(c=>c.kind==='scene_edit'&&c.state==='waiting');
        return !!card;
      },{timeout:20000}).toBe(true);
      const region=page.getByRole('region',{name:card.question,exact:true});
      await expect(region).toBeVisible();
      if(card.choices.filter(c=>c.enabled).length!==1){
        await region.getByRole('radio',{name:'Apply and update Twin',exact:true}).check();
        await region.getByRole('button',{name:'Continue',exact:true}).click();
      }else await region.getByRole('button',{name:'Apply and update Twin',exact:true}).click();
      let next;
      await expect.poll(async()=>{next=await read('/v1/product/scene-edit/transaction');return !!next&&next.operation_id!==previous.operation_id;},{timeout:20000}).toBe(true);
      const evidence=await committed(next.operation_id,filename);
      expect(evidence.transaction.result_revision).not.toBe(previous.result_revision);
      expect(evidence.transaction.result_revision).not.toBe(source.scene_revision);
      result.steps.push({operation_id:next.operation_id,ordinary_default_mode_undo:true,...evidence});
    };
    const moved=structuredClone(original.site_draft.editable_calls.find(call=>full?
      Array.isArray(call.arguments.center_m)&&Array.isArray(call.arguments.dimensions_m):call.arguments.id===pending.parent_id));
    expect(moved).toBeTruthy();moved.arguments.center_m[0]+=.1;
    await apply(full?'full_geometry_edit':'native_parent_move',[{action:'change',target_id:moved.arguments.id,
      reason:'Explicit synthetic parent movement acceptance',tool_call:moved}],full?'02-full-geometry-edited.png':'02-native-parent-moved.png');
    const afterParent=await checked(false);
    result.parent_edit=afterParent;
    expect(afterParent.progressive_twin.plan_sha256).not.toBe(native.progressive_twin.plan_sha256);
    await undo(full?'03-full-geometry-undo-current.png':'03-native-parent-undo-current.png');
    result.parent_undo=await checked(true);
    expect(result.parent_undo.progressive_twin).toEqual(native.progressive_twin);
    let restored=result.parent_undo;
    let beforeOps=(await read('/v1/product/state')).operations;
    if(!full){
    const beforePending=await checked(true);
    await apply('native_pending_only',[{action:'defer',target_id:pending.id,
      reason:'Explicit synthetic pending-only metadata revision; native attachment and hazard retained'}],'04-native-pending-only.png');
    const changedPending=await checked(false);
    result.pending_only=changedPending;
    expect(changedPending.progressive_twin.plan_sha256).toBe(beforePending.progressive_twin.plan_sha256);
    expect(changedPending.scene_state_sha256).not.toBe(beforePending.scene_state_sha256);
    expect(changedPending.editable_calls).toEqual(beforePending.editable_calls);
    expect(changedPending.progressive_twin.unresolved[0].reason).not.toBe(pending.reason);
    await undo('05-native-pending-undo-current.png');
    restored=await checked(true);expect(restored.progressive_twin).toEqual(native.progressive_twin);
    result.pending_undo=restored;
    const beforeGoal=await read('/v1/product/conversation');beforeOps=(await read('/v1/product/state')).operations;
    await send('Go to bed');let rejected;
    await expect.poll(async()=>{
      const chat=await read('/v1/product/conversation');rejected=chat.messages.find(m=>m.role==='assistant'&&m.status==='failed'&&
        !beforeGoal.messages.some(old=>old.message_id===m.message_id)&&m.content.includes('progressive_task_unresolved'));
      return !!rejected;
    },{timeout:20000}).toBe(true);
    await expect(page.getByRole('region',{name:'Conversation',exact:true}).locator('article.chat-message.assistant').getByText(rejected.content,{exact:true})).toBeVisible();
    expect((await read('/v1/product/conversation')).simulation_review).toBeNull();
    expect((await read('/v1/product/state')).operations).toEqual(beforeOps);
    result.task_rejection=rejected;result.motion='NOT_RUN_PENDING_HAZARD';
    await checked(true);
    await page.screenshot({path:path.join(output,'06-native-goal-blocked-current.png')});
    }else result.motion='NOT_RUN_EXPLICIT_SYNTHETIC_VIEW_EDIT_ONLY';
    await page.reload();result.final=await waitFrame(restored.revision,full?'04-full-geometry-reloaded-current.png':'07-native-reloaded-current.png');
    expect((await read('/v1/product/state')).operations).toEqual(beforeOps);
    await checked(true);result.reload_no_dispatch=true;
    await finish();
  }else{
  const initial=await read('/v1/product/workflow');
  expect(initial.site_draft.progressive_twin.unresolved.map(row=>row.id)).toContain('item_0');
  const currentCall=async id=>(await read('/v1/product/workflow')).site_draft.editable_calls.find(call=>call.arguments.id===id);
  const relation=(id,parent,part='body')=>({id,relation:'surface',parent_id:parent,part,anchor:'centre',elevation_m:null});
  const prop=(id,position,size)=>({call_id:`obj_${id}`,tool:'place_room_item',arguments:{id,kind:'tabletop_item',
    label:'Explicit synthetic rigid prop',catalog_version:'room-items-1.0',position_m:position,
    dimensions_m:size,yaw_deg:0,observation_time_utc:null}});
  const edit=(action,target_id,fields={})=>({action,target_id,reason:'Explicit synthetic acceptance feedback',...fields});
  if(fault){
    const changed=await currentCall('support');changed.arguments.center_m=[.2,0];
    const preview=(await post('/v1/product/scene-edit/preview',{operation_id:`fault_${fault}`,mode:'dependency',
      target_call_id:null,tool_call:{patch_version:'scene-dependency-patch-1.0',edits:[edit('change','support',{tool_call:changed})]}})).value;
    expect((await post('/v1/product/scene-edit/apply',{schema_version:'scene-edit-apply-2.0',
      operation:preview.operation,preview_digest:preview.preview_digest})).status).toBe(202);
    let transaction;
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction.state;},
      {timeout:135000}).toBe(fault==='commit'?'ROLLED_BACK':'ENGINE_STATE_UNKNOWN');
    result.fault_transaction=transaction;
    if(fault==='ack'){
      const beforeCount=(await read('/v1/product/state')).operations.length;
      for(let i=0;i<10;i++)await read('/v1/product/scene-edit/transaction');
      expect((await read('/v1/product/state')).operations).toHaveLength(beforeCount);
      const currentWorkflow=await read('/v1/product/workflow');
      expect(currentWorkflow.site_draft.revision).toBe(source.scene_revision);
      const recoveryButton=page.getByRole('button',{name:'Recover saved Twin in Isaac',exact:true});
      await expect(recoveryButton).toBeEnabled({timeout:20000});
      await page.screenshot({path:path.join(output,'02-unknown-explicit-recovery.png')});
      await recoveryButton.click();
      await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction.state;},
        {timeout:135000}).toBe('ROLLED_BACK');
      result.recovery_transaction=transaction;result.poll_dispatch_count=0;
    }
    result.final=await waitFrame(source.scene_revision,'03-fault-compensated-current.png');
    transaction=await read('/v1/product/scene-edit/transaction');
    expect(transaction.compensation_acknowledged).toBe(true);
    expect(transaction.displayed_revision).toBe(source.scene_revision);
    expect(transaction.current_frame).toBe(true);
    result.compensated_display=transaction;
    await expect(page.getByText(/Previous saved Twin restored · Compensation ACK: confirmed/)).toBeVisible({timeout:15000});
    result.final=await waitFrame(source.scene_revision,'04-compensated-ui-settled.png');
    await finish();
  }else if(feedback){
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    const send=async text=>{await input.fill(text);await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled({timeout:15000});await page.getByRole('button',{name:'Send',exact:true}).click();};
    const waiting=async kind=>{
      let chat;
      await expect.poll(async()=>{chat=await read('/v1/product/conversation');
        return chat.cards.filter(c=>c.state==='waiting').map(c=>c.kind);},{timeout:20000}).toEqual([kind]);
      return chat.cards.find(c=>c.state==='waiting');
    };
    const choose=async(kind,label)=>{
      const card=await waiting(kind);const region=page.getByRole('region',{name:card.question,exact:true});
      await expect(region).toBeVisible();
      const choice=region.getByRole('radio',{name:label,exact:true});
      if(card.choices.filter(c=>c.enabled).length!==1){await expect(choice).toBeVisible();await choice.check();await region.getByRole('button',{name:'Continue',exact:true}).click();}
      else await region.getByRole('button',{name:label,exact:true}).click();
    };
    await send('Move the synthetic support a little.');
    await waiting('scene_edit_clarify');
    await page.screenshot({path:path.join(output,'02-feedback-one-question.png')});
    expect((await read('/v1/product/state')).operations).toHaveLength(result.initial.build_count);
    await send('0.2 metres along X');
    await waiting('scene_edit');
    await page.screenshot({path:path.join(output,'03-feedback-preview.png')});
    await choose('scene_edit','Cancel');
    expect((await read('/v1/product/workflow')).site_draft.revision).toBe(source.scene_revision);
    expect((await read('/v1/product/state')).operations).toHaveLength(result.initial.build_count);
    result.cancel_no_mutation=true;
    await send('Move the synthetic support by 0.2 metres along X.');
    await waiting('scene_edit');
    await choose('scene_edit','Apply and update Twin');
    let transaction;
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.state;},
      {timeout:135000}).toBe('COMMITTED');
    result.feedback_transaction=transaction;
    result.feedback_frame=await waitFrame(transaction.result_revision,'04-feedback-applied-current.png');
    expect((await currentCall('support')).arguments.center_m).toEqual([.2,0]);
    const editCount=(await read('/v1/product/workflow')).site_draft.scene_edit_count;
    await send('Move it out of bounds.');
    await expect.poll(async()=>(await read('/v1/product/conversation')).scene_feedback?.state,{timeout:20000}).toBe('failed');
    expect((await read('/v1/product/workflow')).site_draft.scene_edit_count).toBe(editCount);
    result.invalid_proposal_no_mutation=true;
    await page.screenshot({path:path.join(output,'05-feedback-rejected-current.png')});
    await send('Undo');
    await choose('scene_edit','Apply and update Twin');
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.operation_id;},
      {timeout:20000}).not.toBe(result.feedback_transaction.operation_id);
    await expect.poll(async()=>{transaction=await read('/v1/product/scene-edit/transaction');return transaction?.state;},
      {timeout:135000}).toBe('COMMITTED');
    result.undo_transaction=transaction;
    result.final=await waitFrame(transaction.result_revision,'06-feedback-undo-current.png');
    expect((await currentCall('support')).arguments.center_m).toEqual([0,0]);
    expect(transaction.result_revision).not.toBe(source.scene_revision);
    const count=(await read('/v1/product/state')).operations.length;
    await page.reload();await waitFrame(transaction.result_revision,'07-feedback-reload-current.png');
    expect((await read('/v1/product/state')).operations).toHaveLength(count);
    await finish();
  }else{
  const apply=async(operation_id,edits,{undo=false,filename}={})=>{
    const preview=(await post('/v1/product/scene-edit/preview',{operation_id,mode:undo?'undo':'dependency',
      target_call_id:null,tool_call:undo?null:{patch_version:'scene-dependency-patch-1.0',edits}})).value;
    const body={schema_version:'scene-edit-apply-2.0',operation:preview.operation,preview_digest:preview.preview_digest};
    const started=await post('/v1/product/scene-edit/apply',body);
    expect(started.status).toBe(202);
    let transaction;
    await expect.poll(async()=>{
      transaction=await read('/v1/product/scene-edit/transaction');
      return transaction.state;
    },{timeout:135000}).toMatch(/^(COMMITTED|ROLLED_BACK|ENGINE_STATE_UNKNOWN|CANCELLED_BEFORE_DISPATCH)$/);
    expect(transaction.state).toBe('COMMITTED');
    expect(transaction.engine_acknowledged).toBe(true);expect(transaction.durable_committed).toBe(true);
    expect(transaction.result_revision).toBe(preview.result_revision);
    const actual=await waitFrame(transaction.result_revision,filename??`${operation_id}.png`);
    const workflow=await read('/v1/product/workflow');
    expect(workflow.site_draft.revision).toBe(transaction.result_revision);
    const duplicate=await post('/v1/product/scene-edit/apply',body);
    expect(duplicate.value.operation_id).toBe(operation_id);
    const again=await read('/v1/product/state');
    expect(again.operations.filter(op=>op.command_type==='build_site_scene')).toHaveLength(actual.build_count);
    result.steps.push({operation_id,preview,transaction,actual,workflow:workflow.site_draft,
      duplicate_dispatch:false});
    return workflow.site_draft;
  };
  const enlarged=await currentCall('support');enlarged.arguments.dimensions_m=[1.4,.8,.9];
  await apply('resize_restore',[edit('change','support',{tool_call:enlarged}),
    edit('restore','item_0',{tool_call:prop('item_0',[0,0,.95],[.9,.6,.1]),placement:relation('item_0','support')})],
    {filename:'02-restored-support.png'});
  await apply('nested_support',[edit('add','upper',{tool_call:prop('upper',[0,0,1.01],[.1,.1,.02]),
    placement:relation('upper','item_0','top')})],{filename:'03-nested-support.png'});
  const moved=await currentCall('support');moved.arguments.center_m=[.25,.15];
  await apply('parent_move',[edit('change','support',{tool_call:moved})],{filename:'04-parent-moved.png'});
  const attached=await currentCall('upper');expect(attached.arguments.position_m.slice(0,2)).toEqual([.25,.15]);
  await apply('reparent_upper',[edit('reparent','upper',{tool_call:prop('upper',[.85,.15,.91],[.1,.1,.02]),
    placement:relation('upper','support')})],{filename:'05-reparented.png'});
  const deferred=await apply('defer_parent',[edit('defer','support')],{filename:'06-pending-preserved.png'});
  expect(new Set(deferred.progressive_twin.unresolved.map(row=>row.id))).toEqual(new Set(['support','item_0','upper']));
  const restored=await apply('undo_defer',null,{undo:true,filename:'07-undo-restored.png'});
  expect(restored.progressive_twin.unresolved).toEqual([]);
  expect(restored.revision).not.toBe(result.steps[3].transaction.result_revision);
  const count=(await read('/v1/product/state')).operations.length;
  await page.reload();
  result.final=await waitFrame(restored.revision,'08-reloaded-current.png');
  expect((await read('/v1/product/state')).operations).toHaveLength(count);
  expect(result.page_errors).toEqual([]);
  result.final_revision=restored.revision;result.final_state_sha256=restored.scene_state_sha256;
  await finish();
  }
  }
}catch(error){
  result.error_type=error.name;result.error=String(error);
  if(page)await page.screenshot({path:path.join(output,'failed-current-screen.png')}).catch(()=>{});
}finally{
  if(browser)await browser.close();fs.writeFileSync(path.join(output,phase==='restart'?'restart-browser.json':'browser.json'),JSON.stringify(result,null,2));
}
if(result.status!=='PASS')process.exitCode=1;
