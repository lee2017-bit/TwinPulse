// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Current saved fresh scene; ordinary chat + actual PhysX. No model substitute.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {freshGoalReview,currentTargetChoice,currentPlanSample} from './benchmark-journey-policy.mjs';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const packet=JSON.parse(process.env.TWINPULSE_SAVED_SIM_PACKET);
const phase=process.env.TWINPULSE_SAVED_SIM_PHASE;
const result={status:'FAIL',phase,provider_calls:0,physical_robot_connections:0,page_errors:[],checks:[],samples:[]};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',error=>result.page_errors.push(error.message));
  page.on('response',async response=>{
    if(new URL(response.url()).pathname==='/v1/product/state')try{
      const value=await response.json();if(value.snapshot)result.samples.push(value.snapshot);
      if(result.samples.length>1200)result.samples.shift();
    }catch{}
  });
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const read=endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);const value=await response.json();
    if(!response.ok)throw new Error(`${endpoint}:HTTP${response.status}:${value.error?.code}`);return value;
  },endpoint);
  const post=(endpoint,body)=>page.evaluate(async({endpoint,body})=>{
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json',
      'X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},body:JSON.stringify(body)});
    const value=await response.json();if(!response.ok)throw new Error(`${endpoint}:HTTP${response.status}:${value.error?.code}`);return value;
  },{endpoint,body});
  const observe=async()=>({product:await read('/v1/product/state'),conversation:await read('/v1/product/conversation')});
  await expect(page.getByRole('button',{name:'Reopen saved scene',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
  await expect.poll(async()=>(await read('/v1/product/workflow')).phase,{timeout:15000}).toBe('draft_ready');
  const draft=(await read('/v1/product/workflow')).site_draft;
  expect(draft.revision).toBe(packet.revision);expect(draft.scene_state_sha256).toBe(packet.state_sha256);
  if(packet.progressive_twin)expect(draft.progressive_twin).toEqual(packet.progressive_twin);
  if(packet.draft_refinement){
    expect(draft.draft_refinement).toEqual(packet.draft_refinement);
    expect(draft.draft_refinement.quality_review.status).toBe('needs_revision');
    expect(draft.draft_refinement.physical_authority).toBe(false);
    await expect(page.getByRole('status',{name:'Photo refinement retained',exact:true})).toBeVisible();
    result.retained_refinement_before_view=draft.draft_refinement;
  }
  const view=page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/});
  await expect(view).toBeEnabled({timeout:15000});await view.click();
  const current=async filename=>{
    await expect.poll(async()=>{
      const state=await read('/v1/product/state');const build=state.operations.filter(op=>op.command_type==='build_site_scene').at(-1);
      return !!build&&build.status==='succeeded'&&state.build_view?.command_id===build.command_id&&state.build_view.status==='succeeded'&&
        state.snapshot?.applied_revision===packet.revision&&!state.operations.some(op=>['accepted','running'].includes(op.status));
    },{timeout:45000}).toBe(true);
    const panel=page.getByRole('complementary',{name:'Digital Twin'});
    const canvas=panel.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true});
    await expect(canvas).toBeVisible({timeout:15000});
    const frame=await read('/v1/product/viewport');expect(frame.frame.applied_revision).toBe(packet.revision);
    await expect.poll(async()=>Number(await canvas.getAttribute('data-captured-at')),{timeout:15000}).toBeGreaterThanOrEqual(frame.frame.captured_at_ms);
    await expect(panel.getByText(/^Live (Isaac render|render · reduced frame rate)/)).toBeVisible();
    await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(
      'Preparing the current Twin in Isaac',{timeout:15000});
    await page.screenshot({path:path.join(output,filename)});return frame.frame;
  };
  result.initial_frame=await current(phase==='restart'?'07-closed-restart-current.png':'01-saved-current.png');
  expect((await read('/v1/product/state')).operations.filter(op=>op.command_type==='run')).toHaveLength(0);
  if(phase==='blocked'){
    expect(packet.expect_task_blocked).toBe(true);
    expect(draft.run_allowed).toBe(false);
    expect(draft.progressive_twin.unresolved.length).toBeGreaterThan(0);
    const before=await observe();
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    await input.fill(packet.goal_text);
    await expect(page.getByRole('button',{name:'Send',exact:true})).toBeEnabled({timeout:15000});
    await page.getByRole('button',{name:'Send',exact:true}).click();
    let rejected;
    await expect.poll(async()=>{
      const value=await observe();
      rejected=value.conversation.messages.find(m=>m.role==='assistant'&&m.status==='failed'&&
        !before.conversation.messages.some(old=>old.message_id===m.message_id)&&m.content.includes('progressive_task_unresolved'));
      return !!rejected;
    },{timeout:20000}).toBe(true);
    await expect(page.getByText(rejected.content,{exact:true})).toBeVisible();
    const after=await observe();
    expect(after.conversation.simulation_review).toBeNull();
    expect(after.product.operations).toHaveLength(before.product.operations.length);
    expect(after.product.operations.filter(op=>op.command_type==='run')).toHaveLength(0);
    expect((await read('/v1/product/workflow')).site_draft.progressive_twin).toEqual(packet.progressive_twin);
    const run=page.getByRole('button',{name:'Run simulation',exact:true});
    if(await run.count())await expect(run).toBeDisabled();
    result.task_rejection=rejected;result.motion='NOT_RUN_PENDING_HAZARD';
    await page.screenshot({path:path.join(output,'02-pending-task-rejected-current.png')});
    await page.reload();
    await expect(page.getByRole('complementary',{name:'Digital Twin'}).getByRole('img',
      {name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:15000});
    expect((await observe()).product.operations).toHaveLength(before.product.operations.length);
    result.reload_no_dispatch=true;
    result.checks.push('Hazardous pending inventory survives ordinary rejected goal/reload; zero route, Run and physical authority');
  }else if(phase==='motion'){
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    const goal=async(text,before)=>{
      await input.fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();
      await expect.poll(async()=>{
        const state=await observe();try{return !!freshGoalReview(before.conversation,state.conversation,text,packet.revision);}catch{return false;}
      },{timeout:20000}).toBe(true);
      let state=await observe();
      if(!state.conversation.simulation_review?.plan){
        const choice=currentTargetChoice(state.conversation,packet.revision);
        await page.getByRole('radio',{name:choice.label,exact:true}).check();
        await page.getByRole('button',{name:'Continue',exact:true}).click();result.target_choice=choice;
      }
      await expect.poll(async()=>{
        const value=await observe();try{return !!freshGoalReview(before.conversation,value.conversation,text,packet.revision).review.plan;}catch{return false;}
      },{timeout:20000}).toBe(true);
      state=await observe();const fresh=freshGoalReview(before.conversation,state.conversation,text,packet.revision);
      expect(fresh.review.plan.physical_authority).toBe(false);
      await expect(page.getByRole('region',{name:'Simulation route',exact:true})).toHaveAttribute('data-plan-id',fresh.review.plan.plan_id);
      await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
      return fresh;
    };
    const initial=await observe();
    const text=`Go from X=${packet.start[0]} Y=${packet.start[1]} to ${packet.goal_text.slice(6)}`;
    result.semantic={before:initial.product.snapshot,text,...await goal(text,initial)};
    await page.screenshot({path:path.join(output,'02-semantic-route-review.png')});
    await page.getByRole('button',{name:'Run simulation',exact:true}).click();
    await expect.poll(async()=>currentPlanSample((await observe()).product.snapshot,result.semantic.review.plan,initial.product.snapshot,'completed'),{timeout:150000}).toBe(true);
    const arrived=await observe();result.arrival=arrived.product.snapshot;
    expect(result.arrival.distance_to_goal_m).toBeLessThanOrEqual(.04);
    expect(Math.hypot(...result.arrival.position_m.slice(0,2).map((v,i)=>v-packet.start[i]))).toBeGreaterThan(.08);
    await page.screenshot({path:path.join(output,'03-actual-physx-arrival.png')});
    const back=`Go to X=${packet.start[0]} Y=${packet.start[1]}`;
    result.return_route=await goal(back,arrived);
    await page.getByRole('button',{name:'Run simulation',exact:true}).click();
    await expect.poll(async()=>{
      const sample=(await observe()).product.snapshot;
      if(currentPlanSample(sample,result.return_route.review.plan,arrived.product.snapshot,'running')&&
        Math.hypot(...sample.position_m.slice(0,2).map((v,i)=>v-arrived.product.snapshot.position_m[i]))>.02){result.running_before_stop=sample;return true;}return false;
    },{timeout:20000}).toBe(true);
    await input.fill('Stop simulation');await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect.poll(async()=>currentPlanSample((await observe()).product.snapshot,result.return_route.review.plan,result.running_before_stop,'paused'),{timeout:15000}).toBe(true);
    result.paused=(await observe()).product.snapshot;await page.waitForTimeout(1000);result.stable=(await observe()).product.snapshot;
    expect(result.stable.position_m).toEqual(result.paused.position_m);
    await page.screenshot({path:path.join(output,'04-moving-stop-stable.png')});
    const beforeReload=await observe();await page.reload();
    await expect(page.getByText(/Physics paused · goal distance/)).toBeVisible({timeout:15000});
    await page.waitForTimeout(1000);const reloaded=await observe();
    expect(reloaded.product.operations).toHaveLength(beforeReload.product.operations.length);
    await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
    result.reload_no_dispatch=true;
    await post('/v1/product/lease',{});
    const reset=await post('/v1/product/commands',{client_request_id:crypto.randomUUID(),command_type:'reset',expected_applied_revision:packet.revision});
    await expect.poll(async()=>{
      const state=await read('/v1/product/state');const op=state.operations.find(op=>op.command_id===reset.command_id);
      return op?.status==='succeeded'&&state.snapshot?.run_id===null&&state.snapshot.telemetry_available===false&&state.snapshot.sim_time_s===0;
    },{timeout:15000}).toBe(true);
    result.reset=(await observe()).product.snapshot;
    // Reset intentionally clears the broker's old Build/view ACK. Require the
    // ordinary explicit View action before claiming a newly bound current view.
    const resetView=page.getByRole('button',{name:'View current Twin',exact:true});
    await expect(resetView).toBeEnabled({timeout:15000});await resetView.click();
    result.reset_view_requested=true;await current('06-reset-current.png');
  }else result.closed_restart_run_count=0;
  const final=(await read('/v1/product/workflow')).site_draft;
  expect(final.revision).toBe(packet.revision);expect(final.scene_state_sha256).toBe(packet.state_sha256);
  if(packet.progressive_twin)expect(final.progressive_twin).toEqual(packet.progressive_twin);
  if(packet.draft_refinement){
    expect(final.draft_refinement).toEqual(packet.draft_refinement);
    result.retained_refinement_after_sim=final.draft_refinement;
    result.photo_quality='NEEDS_REVISION_NOT_QUALITY_PASS';
    await expect(page.getByRole('status',{name:'Photo refinement retained',exact:true})).toBeVisible();
  }
  result.final_draft={revision:final.revision,state_sha256:final.scene_state_sha256};
  result.diagnostics=await read('/v1/product/diagnostics?limit=100');
  expect(result.page_errors).toEqual([]);result.status='PASS';
}catch(error){result.error_type=error.name;result.error=String(error).slice(0,1400);if(page)await page.screenshot({path:path.join(output,phase+'-failure.png')}).catch(()=>{});}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,phase+'-browser.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
