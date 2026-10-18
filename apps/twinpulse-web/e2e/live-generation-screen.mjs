// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual React/ordinary API generation only. NO engine host or Build/Run/Stop.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const result={status:'FAIL',scope:'generation-only',page_errors:[],engine_requests:[],checks:[]};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let page;
try{
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',e=>result.page_errors.push(e.message));
  page.on('request',request=>{
    if(request.method()==='POST'&&/\/commands|\/simulation\/(run|stop)/.test(new URL(request.url()).pathname))
      result.engine_requests.push(new URL(request.url()).pathname);
  });
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  await expect(page.getByRole('heading',{name:'Build your Digital Twin'})).toBeVisible();
  await page.locator('input[type=file]').setInputFiles(process.env.TWINPULSE_JOURNEY_IMAGE);
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Create a digital twin of my bedroom with a bed and desk.');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await expect(question).toBeVisible();
  await question.getByRole('radio',{name:'Simulation only',exact:true}).check();
  await question.getByRole('button',{name:'Continue',exact:true}).click();
  const approval=page.locator('section.chat-question').filter({has:page.getByLabel('Maximum spend for this action (USD)')});
  await expect(approval).toBeVisible();
  const read=async()=>page.evaluate(async()=>{
    const [conversation,workflow,product]=await Promise.all(['/v1/product/conversation','/v1/product/workflow','/v1/product/state'].map(async p=>(await fetch(p)).json()));
    return {conversation,workflow,product};
  });
  const before=await read();
  const policy=before.conversation.cards.find(c=>c.state==='waiting'&&c.kind==='generation_approval')?.generation_approval;
  expect(policy.policy.max_requests).toBe(10);expect(policy.image_count).toBe(1);
  expect(policy.policy.per_call_timeout_s).toBe(300);expect(policy.policy.total_timeout_s).toBe(900);
  expect(before.conversation.generation).toBeNull();expect(before.product.engine_connected).toBe(false);
  expect(before.product.operations).toEqual([]);
  result.approval_preview=policy;
  await page.screenshot({path:path.join(output,'approval-screen.png'),fullPage:true});
  await approval.getByLabel('Maximum spend for this action (USD)').fill('1.00');
  await approval.getByRole('radio',{name:'Approve generation',exact:true}).check();
  await approval.getByRole('button',{name:'Continue',exact:true}).click();
  await expect.poll(async()=>{
    result.terminal=await read();return result.terminal.conversation.generation?.state;
  },{timeout:930000,intervals:[500,1000,2000]}).toMatch(/^(completed|failed|cancelled)$/);
  // Obtain a current poll/render before opening the attempt history.
  await expect(page.getByText(/Scene generation · (completed|failed|cancelled)/)).toBeVisible({timeout:10000});
  await page.getByText('Tool details',{exact:true}).click();
  const history=page.getByRole('region',{name:'Generation attempt history'});
  await expect(history).toBeVisible();
  const generation=result.terminal.conversation.generation;
  const diagnostics=generation.error?.diagnostics??generation.progress;
  expect(diagnostics.attempts.length).toBe(diagnostics.attempts_total);
  expect(diagnostics.attempts_truncated).toBe(false);
  await expect(history.locator('li')).toHaveCount(diagnostics.attempts_total);
  result.displayed_attempts=await history.innerText();
  await history.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'terminal-attempt-history.png'),fullPage:true});
  expect(result.terminal.product.operations).toEqual([]);expect(result.engine_requests).toEqual([]);
  expect(result.page_errors).toEqual([]);
  result.checks.push('Real ordinary approval and real registered model responses; no engine/robot/commands; all attempt IDs visible');
  const operation=generation.operation_id;
  await page.reload();await expect(page.getByRole('textbox',{name:'Message TwinPulse',exact:true})).toBeVisible();
  await page.waitForTimeout(1500);
  result.after_reload=await read();
  expect(result.after_reload.product.operations).toEqual([]);
  expect(result.after_reload.conversation.generation.operation_id).toBe(operation);
  expect(result.after_reload.conversation.generation.state).toBe(generation.state);
  result.checks.push('Reload preserves terminal state and does not auto-retry or submit engine commands');
  result.verification_status='PASS';
  result.status=generation.state==='completed'?'PASS':'FAIL';
  result.generation_result=generation.state;
}catch(error){
  result.error=String(error).slice(0,1600);
  if(page){try{result.failure_state=await page.evaluate(async()=>({conversation:await(await fetch('/v1/product/conversation')).json(),workflow:await(await fetch('/v1/product/workflow')).json(),product:await(await fetch('/v1/product/state')).json()}));await page.screenshot({path:path.join(output,'failed-screen.png'),fullPage:true});}catch{}}
}finally{
  await browser.close();fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));
}
