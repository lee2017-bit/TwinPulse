// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
if(!output)throw new Error('Explicit isolated output required');
const result={status:'FAIL',checks:[],robot_commands:0};
let page;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST'&&/\/robot\/|mission-start|mission-stop/.test(r.url()))result.robot_commands++;});
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const button=page.getByRole('button',{name:'Display saved survey room · no movement'});
  await expect(button).toBeEnabled({timeout:30000});
  const state=()=>page.evaluate(async()=>await(await fetch('/v1/product/state')).json());
  const before=await state();expect(before.operations.length).toBe(0);
  await button.click();
  await expect(page.getByText(/Survey room displayed · historical scan/)).toBeVisible({timeout:60000});
  const applied=await state();expect(applied.operations.length).toBe(1);
  expect(applied.operations[0].command_type).toBe('build_site_scene');expect(applied.operations[0].status).toBe('succeeded');
  expect(applied.snapshot.applied_revision).toBe(process.env.TWINPULSE_SURVEY_SCENE);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:25000});
  await page.screenshot({path:path.join(output,'survey-desktop.png'),fullPage:true});
  result.checks.push('explicit saved display → real API → one real Isaac Build → current matching viewport');
  await page.reload();await expect(button).toBeEnabled({timeout:20000});
  expect((await state()).operations.length).toBe(1);result.checks.push('reload restores history without Build, Run or robot command');
  await page.setViewportSize({width:390,height:844});
  // The existing mobile Twin pane overlays chat; collapse it explicitly.
  await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  await expect(button).toBeVisible();await page.screenshot({path:path.join(output,'survey-mobile.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBe(true);
  expect(result.robot_commands).toBe(0);expect(errors).toEqual([]);
  result.checks.push('mobile Twin collapses; saved history and display control visible without overflow');result.status='PASS';
}catch(e){result.error=String(e);
  if(page){result.failure_ui=(await page.locator('body').innerText()).slice(-12000);
    result.failure_state=await page.evaluate(async()=>await(await fetch('/v1/product/state')).json()).catch(()=>null);
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});}
}finally{fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));await browser.close();}
process.exitCode=result.status==='PASS'?0:1;
