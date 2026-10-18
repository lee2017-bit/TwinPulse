// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Scripted critic and correction, real App/API/Isaac/current frames. Not model quality.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_PREVIEW_OUTPUT,base=process.env.TWINPULSE_PREVIEW_URL;
const result={status:'FAIL',screens:[],checks:[],page_errors:[],external_requests:0,actual_isaac:true};
let browser;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1100}});
  await context.route('**/*',route=>{
    if(new URL(route.request().url()).origin!==base&&!['blob:','data:'].includes(new URL(route.request().url()).protocol)){
      result.external_requests++;return route.abort();
    }return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',error=>result.page_errors.push(error.message));
  const read=endpoint=>page.evaluate(async endpoint=>{const response=await fetch(endpoint);
    if(!response.ok)throw Error(`${endpoint}: ${response.status}`);return response.json();},endpoint);
  const shot=async name=>{await page.screenshot({path:path.join(output,name)});result.screens.push(name);};
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_PREVIEW_BOOTSTRAP)}`);
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Create an estimated room and bed from this input.');
  await page.locator('input[type=file]').setInputFiles(path.join(output,'fixture.png'));
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?',exact:true});
  await question.getByRole('radio',{name:'Simulation only',exact:true}).check();
  await question.getByRole('button',{name:'Create Twin',exact:true}).click();
  let initial;
  await expect.poll(async()=>{const chat=await read('/v1/product/conversation');initial=chat.generation;
    return initial?.state==='running'&&initial.progress?.stage==='render_review'&&
      initial.progress.generation_preview?.rendered_count===1;},
    {timeout:150000,intervals:[100,200]}).toBe(true);
  const panel=page.getByRole('status',{name:'Twin generation progress',exact:true});
  await expect(panel).toContainText('1 of 1');
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible();
  result.before_revision=initial.progress.generation_preview.scene_revision;
  result.before_frame=(await read('/v1/product/viewport')).frame;
  expect(result.before_frame.applied_revision).toBe(result.before_revision);
  await shot('01-candidate-under-review.png');
  await expect.poll(async()=>{const chat=await read('/v1/product/conversation');
    return chat.generation?.state==='running'&&chat.generation.progress?.stage==='repair';},
    {timeout:30000,intervals:[100,200]}).toBe(true);
  await expect(panel).toContainText('Correcting the scene');
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible();
  expect((await read('/v1/product/viewport')).frame.applied_revision).toBe(result.before_revision);
  await shot('02-repair-pending-old-render.png');
  let final;
  await expect.poll(async()=>{final=(await read('/v1/product/conversation')).generation;return final?.state;},
    {timeout:150000,intervals:[250,500]}).toBe('completed');
  result.completed_operation=final.operation_id;result.completed_progress=final;
  result.after_revision=final.progress.generation_preview.scene_revision;
  expect(result.after_revision).not.toBe(result.before_revision);
  expect(final.progress.budget.repairs).toBe(1);
  await expect(panel).toContainText('generation complete');
  await expect(page.getByRole('region',{name:'Current step',exact:true})).not.toContainText(/Preparing (the )?current Twin/,{timeout:45000});
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:45000});
  const viewport=await read('/v1/product/viewport');result.after_frame=viewport.frame;
  expect(viewport.frame.applied_revision).toBe(result.after_revision);
  expect(viewport.frame.engine_session_id).toBe(result.before_frame.engine_session_id);
  expect(viewport.frame.stage_epoch).toBe(result.before_frame.stage_epoch);
  result.engine_commands=(await read('/v1/product/state')).operations;
  const builds=result.engine_commands.filter(op=>op.command_type==='build_site_scene');
  expect(new Set(builds.map(op=>op.expected_applied_revision)).size).toBe(3);
  expect(builds.every(op=>op.status==='succeeded')).toBe(true);
  const workflow=await read('/v1/product/workflow');expect(workflow.site_draft.revision).toBe(result.after_revision);
  result.saved_revision=workflow.site_draft.revision;
  await shot('03-corrected-current-render.png');
  await page.reload();await expect(panel).toContainText('generation complete');
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:45000});
  expect((await read('/v1/product/workflow')).site_draft.revision).toBe(result.saved_revision);
  await shot('04-corrected-reload.png');
  expect(result.external_requests).toBe(0);expect(result.page_errors).toEqual([]);
  result.checks=['real current candidate passed to scripted critic','old current render retained during scoped repair',
    'typed repair changed revision and actual displayed scene','new current frame and saved revision match'];
  result.status='PASS';
}catch(error){result.error=String(error);}
finally{if(browser)await browser.close();result.browser_closed=true;fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));}
if(result.status!=='PASS')process.exitCode=1;
