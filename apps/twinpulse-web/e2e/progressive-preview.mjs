// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual App/API/Isaac; model responses are explicit deterministic fixtures.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_PREVIEW_OUTPUT,base=process.env.TWINPULSE_PREVIEW_URL;
const mode=process.env.TWINPULSE_PREVIEW_MODE;
const result={status:'FAIL',checks:[],screens:[],page_errors:[],external_requests:0,actual_isaac:process.env.TWINPULSE_PREVIEW_ACTUAL==='true'};
let browser;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1100}});
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',e=>result.page_errors.push(e.message));
  const read=endpoint=>page.evaluate(async endpoint=>{
    const r=await fetch(endpoint);if(!r.ok)throw Error(`${endpoint}: ${r.status}`);return r.json();
  },endpoint);
  const progress=async()=>{
    const chat=await read('/v1/product/conversation');
    if(chat.generation?.state==='failed')throw Error(chat.generation.summary);
    return chat;
  };
  const catalogue=async count=>{
    if(!result.actual_isaac)return;
    const state=await read('/v1/product/state');
    const receipt=state.operations.filter(row=>row.status==='succeeded'&&
      row.receipt?.message?.includes(`catalog groups=${count} meshes=`)).at(-1);
    if(!receipt)throw Error(`Actual Isaac did not confirm ${count} catalogue groups`);
    (result.catalog_receipts??=[]).push(receipt);
  };
  const shot=async name=>{await page.screenshot({path:path.join(output,name)});result.screens.push(name);};
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_PREVIEW_BOOTSTRAP)}`);
  if(mode!=='image')await page.getByRole('textbox',{name:'Message TwinPulse'}).fill(process.env.TWINPULSE_PREVIEW_TYPED==='true'
    ?'Create chairs, floor_covering, wall_fixture, ceiling_fixture and wall_storage in an estimated room'
    :'Create chairs in an estimated room');
  if(mode!=='text')await page.locator('input[type=file]').setInputFiles(path.join(output,'fixture.png'));
  await shot('01-input.png');await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await question.getByRole('radio',{name:'Simulation only'}).check();
  await question.getByRole('button',{name:'Create Twin',exact:true}).click();
  await expect.poll(async()=>{
    const chat=await progress();const p=chat.generation?.progress;
    return chat.generation?.state==='running'&&p?.generation_preview?.state==='ready'&&
      p.generation_preview.rendered_count===0&&p.inventory_progress.inventory_planned===false;
  },{timeout:150000,intervals:[50,100]}).toBe(true);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await catalogue(0);
  await shot('02-room-before-inventory.png');result.checks.push('Actual room shell is visible while whole inventory is still being planned');
  await expect.poll(async()=>{
    const chat=await progress();const p=chat.generation?.progress;
    return chat.generation?.state==='running'&&p?.generation_preview?.state==='ready'&&p.generation_preview.rendered_count===5;
  },{timeout:150000,intervals:[50,100]}).toBe(true);
  const first=await read('/v1/product/conversation');result.partial=first.generation;
  expect(first.generation.progress.inventory_progress.parameterized_count).toBe(6);
  expect(first.generation.progress.generation_preview.pending_count).toBe(7);
  expect(first.generation.progress.generation_preview.pending_objects.length).toBe(7);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await catalogue(5);
  if(mode!=='text'){
    await expect(page.getByAltText(/^Source photo:/)).toBeVisible();
    await page.getByAltText(/^Source photo:/).evaluate(el=>{el.dataset.testPersistent='same-source-image';});
  }
  await shot('03-valid-five-before-repair.png');result.checks.push('One bad object stays pending while five valid objects render before repair');
  await expect.poll(async()=>{
    const chat=await progress();return chat.generation?.progress?.stage==='repair';
  },{timeout:150000,intervals:[50,100]}).toBe(true);
  const repairing=await read('/v1/product/conversation');result.repairing=repairing.generation;
  expect(repairing.generation.progress.generation_preview.rendered_count).toBe(11);
  await catalogue(11);
  await shot('04-eleven-during-repair.png');
  if(mode!=='text')expect(await page.getByAltText(/^Source photo:/).getAttribute('data-test-persistent')).toBe('same-source-image');
  if(process.env.TWINPULSE_PREVIEW_FAILED_REPAIR==='true'){
    let stopped;
    await expect.poll(async()=>{stopped=await read('/v1/product/conversation');return stopped.generation?.state;},
      {timeout:150000,intervals:[100,250]}).toBe('failed');
    result.failed_operation=stopped.generation.operation_id;result.failed_progress=stopped.generation;
    expect(stopped.generation.progress.generation_preview.rendered_count).toBe(11);
    expect(stopped.generation.progress.generation_preview.pending_count).toBe(1);
    expect(stopped.generation.summary).toContain('REPAIR_STALLED');
    await expect(page.getByRole('img',{name:'Last Isaac preview · not live'})).toBeVisible();
    if(mode!=='text')expect(await page.getByAltText(/^Source photo:/).getAttribute('data-test-persistent')).toBe('same-source-image');
    await shot('05-repair-failed-eleven-retained.png');
    const priorState=await read('/v1/product/state');
    await page.getByRole('button',{name:'Review generation budget and resume options'}).click();
    const chat=await read('/v1/product/conversation');
    const card=chat.cards.find(row=>row.kind==='generation_approval'&&row.state==='waiting');
    if(!card)throw Error('Missing explicit continuation approval');
    const approval=page.getByRole('region',{name:card.question,exact:true});
    await approval.getByLabel('Maximum spend for this action (USD)').fill('1.00');
    await approval.getByRole('radio',{name:card.choices.find(row=>row.id==='approve').label,exact:true}).check();
    await approval.getByRole('button',{name:'Continue',exact:true}).click();
    let blocked;
    await expect.poll(async()=>{blocked=await read('/v1/product/conversation');return blocked.generation?.state;},
      {timeout:15000,intervals:[100,250]}).toBe('failed');
    expect(blocked.generation.summary).toBe('CONTINUATION_STALLED_POLICY_EXHAUSTED');
    const after=await read('/v1/product/state');
    expect(after.snapshot.applied_revision).toBe(priorState.snapshot.applied_revision);
    expect(after.operations.map(row=>row.command_id)).toEqual(priorState.operations.map(row=>row.command_id));
    await expect(page.getByRole('img',{name:'Last Isaac preview · not live'})).toBeVisible();
    await shot('06-stalled-resume-blocked.png');
    result.engine_commands=after.operations;
    result.checks.push('REPAIR_STALLED retains eleven objects and one pending; exhausted same-policy continuation makes no new Build or remote request');
  }
  if(process.env.TWINPULSE_PREVIEW_FAILED_REPAIR!=='true'){
  let final;
  await expect.poll(async()=>{final=await read('/v1/product/conversation');return final.generation?.state;},
    {timeout:150000,intervals:[100,250]}).toBe('completed');
  expect(final.generation.progress.generation_preview.rendered_count).toBe(12);
  expect(final.generation.progress.generation_preview.pending_count).toBe(0);
  await catalogue(12);
  await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(
    /Preparing (the )?current Twin/,{timeout:45000});
  await expect.poll(async()=>{const state=await read('/v1/product/state');
    return state.operations.some(row=>['accepted','claimed','running'].includes(row.status));},
    {timeout:45000,intervals:[100,250]}).toBe(false);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:45000});
  await shot('05-repair-updated-twelve.png');result.final=final.generation;
  result.completed_operation=final.generation.operation_id;
  const before=await read('/v1/product/workflow');result.saved_revision=before.site_draft.revision;
  result.engine_commands=(await read('/v1/product/state')).operations;
  await page.reload();
  await expect(page.getByRole('status',{name:'Twin generation progress'})).toContainText('12 of 12 objects rendered');
  const after=await read('/v1/product/workflow');expect(after.site_draft.revision).toBe(result.saved_revision);
  await shot('06-saved-reload.png');
  result.checks.push('Repair updates the actual scene, preserves source-photo DOM and saves/reloads the same completed draft');
  }
  expect(result.external_requests).toBe(0);expect(result.page_errors).toEqual([]);result.status='PASS';
}catch(error){result.error=String(error);}
finally{if(browser)await browser.close();result.browser_closed=true;fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));}
if(result.status!=='PASS')process.exitCode=1;
