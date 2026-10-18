// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const output=process.env.TWINPULSE_CHAT_OUTPUT;
const scenario=process.env.TWINPULSE_CHAT_CASE;
if(!output||!['text','photo','retry','repair','timeout'].includes(scenario))throw new Error('Owned test scenario and output required');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_CHAT_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_CHAT_BOOTSTRAP)}`);
  const box=page.getByRole('textbox',{name:'Message TwinPulse'});
  await expect(box).toBeVisible();
  await box.fill('Create an approximate small bedroom, 4 by 5 metres, with a Burger robot');
  if(scenario==='photo')await page.locator('input[type=file]').setInputFiles(process.env.TWINPULSE_CHAT_IMAGE);
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await expect(question).toBeVisible();
  await expect(question.getByRole('button')).toHaveCount(1);
  await expect(question.getByRole('button',{name:'Continue',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:/Check robot connection|collect once|inspection readiness/})).toHaveCount(0);
  await question.getByRole('radio',{name:'Simulation only',exact:true}).check();
  const before=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
  if(before.phase!=='input_ready')throw new Error('Radio selection prematurely started generation');
  await page.screenshot({path:path.join(output,'question.png')});
  await question.getByRole('button',{name:'Continue',exact:true}).click();
  if(scenario==='repair'){
    await expect(page.getByText(/Stage: planner.*Repairs: 1\/1/)).toBeVisible();
    await expect(page.getByRole('button',{name:/Retry scene generation/})).toHaveCount(0);
    await page.screenshot({path:path.join(output,'automatic-repair-progress.png')});
  }
  if(scenario==='retry'){
    await expect(page.getByText('Scene generation · failed',{exact:true})).toBeVisible();
    const retry=page.getByRole('button',{name:'Retry scene generation · original input, one provider attempt'});
    await expect(retry).toBeEnabled();
    await page.screenshot({path:path.join(output,'failed-diagnosis.png')});
    await retry.click();
  }
  if(scenario==='timeout'){
    await expect(page.getByText('Scene generation · failed',{exact:true})).toBeVisible({timeout:2000});
    await page.screenshot({path:path.join(output,'timeout-before-late-response.png')});
    const failed=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    if(failed.phase!=='generation_failed'||failed.error?.diagnostics?.status!=='outcome_unknown'||failed.site_draft)
      throw new Error('Timeout public state is incorrect');
    await page.waitForTimeout(3500);
    await page.reload();
    await expect(page.getByText('Scene generation · failed',{exact:true})).toBeVisible();
    const late=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    if(late.phase!=='generation_failed'||late.site_draft)throw new Error('Late response applied a scene');
    if(errors.length)throw new Error(`Browser exceptions: ${errors.join(',')}`);
    fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({status:'PASS',scenario,
      deadline_visible_before_response:true,late_response_not_applied:true,reload_no_retry:true,
      paid_calls:0,robot_connections:0,isaac_runtime:'NOT_RUN'},null,2));
    console.log(JSON.stringify({scenario,status:'PASS'}));
  }else{
  await expect(page.getByText('Scene generation · completed',{exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole('radio')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Continue',exact:true})).toHaveCount(0);
  const saved=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
  if(saved.phase!=='draft_ready'||!saved.site_draft?.artifact_id)throw new Error('Site artifact missing');
  await expect(page.getByText('No current 3D frame',{exact:true})).toBeVisible();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toHaveCount(0);
  await page.screenshot({path:path.join(output,'generated-scene.png')});
  await page.reload();
  await expect(page.getByText('Scene generation · completed',{exact:true})).toBeVisible();
  await expect(page.getByRole('radio')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  if(await page.getByRole('button',{name:'Hide Twin'}).count())await page.getByRole('button',{name:'Hide Twin'}).click();
  await expect(box).toBeVisible();
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw new Error('Mobile horizontal overflow');
  await page.screenshot({path:path.join(output,'mobile.png')});
  if(errors.length)throw new Error(`Browser exceptions: ${errors.join(',')}`);
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({status:'PASS',scenario,
    question_actions:1,text_and_photo_site_path:true,isaac_runtime:'NOT_RUN',paid_calls:0,robot_connections:0,console_errors:errors},null,2));
  console.log(JSON.stringify({scenario,status:'PASS'}));
  }
}finally{await browser.close();}
