// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_SWITCH_URL, ticket=process.env.TWINPULSE_SWITCH_BOOTSTRAP;
const output=process.env.TWINPULSE_SWITCH_OUTPUT, phase=process.env.TWINPULSE_SWITCH_PHASE;
const buildRoundTrip=process.env.TWINPULSE_SWITCH_BUILD==='1';
const previousFrame=JSON.parse(process.env.TWINPULSE_SWITCH_PREVIOUS_FRAME||'null');
if(!base || new URL(base).hostname!=='127.0.0.1' || !ticket || !output ||
  !['create_switch','switch_back','reopen'].includes(phase))throw new Error('Owned switch configuration required');
const result={status:'FAIL',phase,external_requests:0,robot_requests:0,engine_commands:0,generation_requests:0,page_errors:0};
let browser;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',()=>result.page_errors++);
  await page.route('**/*',route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==base && !['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    if(url.pathname.startsWith('/v1/product/robot/') && request.method()!=='GET'){result.robot_requests++;return route.abort();}
    if(url.pathname==='/v1/product/commands'){result.engine_commands++;
      if(!buildRoundTrip||request.postDataJSON()?.command_type!=='build_site_scene')return route.abort();}
    if(url.pathname.includes('generation') && request.method()==='POST'){result.generation_requests++;return route.abort();}
    return route.continue();
  });
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(ticket)}`);
  const savedChat=page.getByRole('button',{name:/^Open saved chat ·/});
  const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
  const savedScene=page.getByRole('button',{name:'Reopen saved scene',exact:true});
  await expect.poll(async()=>await savedChat.count()||
    (phase==='switch_back'?await input.count():await savedScene.count()),{timeout:20000}).toBeGreaterThan(0);
  if(await savedChat.count())await savedChat.click();
  await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toBeVisible({timeout:20000});
  await expect.poll(()=>new URL(page.url()).hash).toBe('');
  const read=endpoint=>page.evaluate(async endpoint=>{
    const response=await fetch(endpoint);if(!response.ok)throw Error(`${endpoint}: ${response.status}`);
    return response.json();},endpoint);
  await page.getByRole('button',{name:/Readiness/}).click();
  const showSaved=async()=>{
    const button=page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/});
    // Wait for the authenticated saved-state navigation, not the initially
    // empty composer, which can precede the restore-to-Home observation.
    await expect.poll(async()=>await savedChat.count()||await savedScene.count()||await button.count(),
      {timeout:20000}).toBeGreaterThan(0);
    if(await savedChat.count())await savedChat.click();
    const showTwin=page.getByRole('button',{name:'Show Twin',exact:true});
    if(await showTwin.count())await showTwin.click();
    const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});
    if(await reopen.count())await reopen.click();
    const draft=(await read('/v1/product/workflow')).site_draft;
    await expect(button).toBeEnabled({timeout:20000});await button.click();
    await expect.poll(async()=>{const view=await read('/v1/product/viewport');
      return view.frame?.applied_revision;},{timeout:45000}).toBe(draft.revision);
    await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:20000});
    result.current_frame=(await read('/v1/product/viewport')).frame;
    if(previousFrame){
      expect(result.current_frame.engine_session_id).not.toBe(previousFrame.engine_session_id);
      expect(result.current_frame.stage_epoch).not.toBe(previousFrame.stage_epoch);
      expect(result.current_frame.applied_revision).toBe(previousFrame.applied_revision);
      result.secure_reopen_current_identity=true;
    }
    await page.screenshot({path:path.join(output,phase+'-current.png')});
  };
  if(buildRoundTrip&&phase==='create_switch')await showSaved();
  if(buildRoundTrip&&phase==='switch_back'){
    const view=await read('/v1/product/viewport');expect(view.frame).toBeNull();expect(view.last_frame).toBeNull();
    expect(previousFrame).toBeTruthy();
    const status=await page.evaluate(async sha=>(await fetch('/v1/product/viewport/preview/'+sha)).status,previousFrame.sha256);
    expect(status).toBe(409);result.old_frame_cache_rejected=true;
    expect((await read('/v1/product/state')).operations).toEqual([]);
  }
  const checks=page.getByRole('region',{name:'Runtime checklist'});
  await expect(checks.getByText(/web dependencies · ready/)).toBeVisible();
  await expect(checks.getByText(/burger asset manifest · ready/)).toBeVisible();
  await expect(checks.getByText(/Repair attempts: 1\/1/)).toHaveCount(2);
  await page.screenshot({path:path.join(output,phase+'-checks.png')});
  await page.getByRole('button',{name:/Readiness/}).click();
  if(phase==='reopen'){
    // Bootstrap can render the composer before the saved-history Home effect.
    // Open the saved conversation after readiness has settled, as a user does.
    if(await savedChat.count())await savedChat.click();
    await expect(page.getByRole('button',{name:'Reopen saved scene',exact:true})).toBeEnabled();
    const before=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    expect(before.phase).toBe('restore_review_required');expect(before.build_allowed).toBe(false);
    await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
    await expect(page.getByText(/Saved scene reopened for review/)).toBeVisible();
    await page.reload();
    await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toBeVisible();
    const state=await page.evaluate(async()=>await(await fetch('/v1/product/state')).json());
    expect(state.engine_connected).toBe(true);
    if(buildRoundTrip)await showSaved();
  }else{
    const projects=page.getByRole('complementary',{name:'Projects and saved conversations'});
    if(phase==='create_switch'){
      await projects.getByRole('button',{name:'Manage projects',exact:true}).click();
      await projects.getByRole('textbox',{name:'New project name'}).fill('room_two');
      await projects.getByRole('button',{name:'Create project',exact:true}).click();
      await expect(projects.getByText(/Created room_two. Your current project is unchanged/)).toBeVisible();
    }
    await projects.getByRole('button',{name:phase==='create_switch'?'Open room_two':'Open default',exact:true}).click();
    await expect(projects.getByText(/Wait for the launcher's new window/)).toBeVisible();
  }
  await page.screenshot({path:path.join(output,phase+'.png')});
  expect(result.external_requests).toBe(0);expect(result.robot_requests).toBe(0);
  expect(result.engine_commands).toBe(buildRoundTrip&&phase!=='switch_back'?1:0);
  expect(result.generation_requests).toBe(0);expect(result.page_errors).toBe(0);
  result.status='PASS';
}catch(error){result.error=String(error.message).split(ticket).join('[redacted]').split(base).join('[local]').slice(0,1000);}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,phase+'.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
