// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual browser/API; model replies explicitly fixture. GPU scope comes from the owner.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_PREVIEW_OUTPUT,base=process.env.TWINPULSE_PREVIEW_URL;
const mode=process.env.TWINPULSE_PREVIEW_MODE,actual=process.env.TWINPULSE_PREVIEW_ACTUAL==='true';
const cancellation=process.env.TWINPULSE_PREVIEW_CANCEL==='true';
const result={status:'FAIL',checks:[],screens:[],page_errors:[],external_requests:0,actual_isaac:actual};
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
  const read=async endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);if(!response.ok)throw Error(`${endpoint}: ${response.status}`);return response.json();
  },endpoint);
  const shot=async name=>{await page.screenshot({path:path.join(output,name)});result.screens.push(name);};
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_PREVIEW_BOOTSTRAP)}`);
  if(mode!=='image')await page.getByRole('textbox',{name:'Message TwinPulse'}).fill('Create chairs in an estimated room');
  if(mode!=='text')await page.locator('input[type=file]').setInputFiles(path.join(output,'fixture.png'));
  await shot('01-input.png');await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await expect(question).toBeVisible();await question.getByRole('radio',{name:'Simulation only'}).check();
  await question.getByRole('button',{name:'Create Twin',exact:true}).click();
  await expect.poll(async()=>{const chat=await read('/v1/product/conversation');
    return chat.generation?.state==='running'&&chat.generation.progress?.generation_preview?.state==='ready'&&
      chat.generation.progress.generation_preview.rendered_count===6;},
    {timeout:150000,intervals:[100,200]}).toBe(true);
  await expect(page.getByRole('status',{name:'Twin generation progress'})).toContainText('6 of 12');
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await shot('02-building-six.png');
  result.checks.push('Six-object preview appears while the next generation batch is still running');
  if(cancellation)await page.getByRole('button',{name:'Stop response',exact:true}).click();
  let first;
  await expect.poll(async()=>{first=await read('/v1/product/conversation');return first.generation?.state;},
    {timeout:150000,intervals:[250,500]}).toBe(cancellation?'cancelled':'failed');
  result.failed_operation=first.generation.operation_id;result.failed_progress=first.generation;
  result.interrupted_state=first.generation.state;
  if(cancellation){
    const before=await read('/v1/product/state');
    await page.waitForTimeout(4000); // The held, valid reply has now arrived after cancellation.
    const after=await read('/v1/product/state');const chat=await read('/v1/product/conversation');
    expect(chat.generation.state).toBe('cancelled');
    expect(chat.generation.progress.inventory_progress.parameterized_count).toBe(6);
    expect(after.snapshot.applied_revision).toBe(before.snapshot.applied_revision);
    expect(after.operations.map(op=>op.command_id)).toEqual(before.operations.map(op=>op.command_id));
    result.cancelled_late_valid_reply={status:'PASS',no_new_build:true,scene_revision:after.snapshot.applied_revision};
  }
  const progress=page.getByRole('status',{name:'Twin generation progress'});
  await expect(progress).toContainText('6 of 12 objects rendered');
  await expect(page.getByRole('img',{name:'Last Isaac preview · not live'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Orbit left',exact:true})).toBeDisabled();
  if(mode!=='text')await expect(page.getByAltText(/^Source photo:/)).toBeVisible();
  await shot('03-partial-stop.png');
  result.checks.push(`${cancellation?'Cancellation with a late valid reply':'Output stop'} retains six rendered objects, all twelve inventory entries and six pending; no automatic continuation`);
  {
    fs.writeFileSync(path.join(output,'pause-frames.flag'),'explicit fixture interruption');
    await page.waitForTimeout(1500);
    const blackout=await read('/v1/product/viewport');
    expect(blackout.state).toBe('stale');expect(blackout.frame).toBeNull();expect(blackout.last_frame).toBeTruthy();
    result.frame_delivery_interruption={state:blackout.state,last_revision:blackout.last_frame.applied_revision,
      current_frame:null,actual_publisher:actual};
    await page.reload();
    await expect(page.getByRole('img',{name:'Last Isaac preview · not live'})).toBeVisible({timeout:15000});
    await shot('04-stale-reload.png');
    result.checks.push('Stale static preview fetched through authenticated endpoint after reload; camera stays disabled');
    fs.unlinkSync(path.join(output,'pause-frames.flag'));
  }
  await page.getByRole('button',{name:'Review generation budget and resume options'}).click();
  const approvalChat=await read('/v1/product/conversation');
  result.resume_review=approvalChat;
  const approvalCard=approvalChat.cards.find(card=>card.kind==='generation_approval'&&card.state==='waiting');
  if(!approvalCard)throw Error('No current resume-approval card');
  const approval=page.getByRole('region',{name:approvalCard.question,exact:true});
  await expect(approval).toBeVisible();await approval.getByLabel('Maximum spend for this action (USD)').fill('1.00');
  await approval.getByRole('radio',{name:approvalCard.choices.find(choice=>choice.id==='approve').label,exact:true}).check();
  await approval.getByRole('button',{name:'Continue',exact:true}).click();
  let final;
  await expect.poll(async()=>{final=await read('/v1/product/conversation');return final.generation?.state;},
    {timeout:150000,intervals:[250,500]}).toBe('completed');
  result.completed_operation=final.generation.operation_id;result.completed_progress=final.generation;
  await expect(progress).toContainText('12 of 12 objects rendered');
  await expect(progress).toContainText('generation complete');
  await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(/Preparing (the )?current Twin/,{timeout:45000});
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:45000});
  await shot('05-resumed-current.png');
  result.checks.push('Explicit ordinary approval resumes only the unfinished batch and displays the complete current scene');
  const before=await read('/v1/product/workflow');result.saved_revision=before.site_draft.revision;
  result.engine_commands=(await read('/v1/product/state')).operations;
  await page.reload();await expect(progress).toContainText('12 of 12 objects rendered');
  const after=await read('/v1/product/workflow');expect(after.site_draft.revision).toBe(result.saved_revision);
  await shot('06-completed-reload.png');
  expect(result.external_requests).toBe(0);expect(result.page_errors).toEqual([]);
  result.status='PASS';
}catch(error){result.error=String(error);}
finally{if(browser)await browser.close();result.browser_closed=true;fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));}
if(result.status!=='PASS')process.exitCode=1;
