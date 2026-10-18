// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const output=process.env.TWINPULSE_CHAT_OUTPUT;
if(!output)throw new Error('Test output directory required');
fs.mkdirSync(output,{recursive:true});
const checks=[];
const scenario=process.env.TWINPULSE_CHAT_CASE;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1920,height:1080}});
  const consoleErrors=[];page.on('pageerror',error=>consoleErrors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_CHAT_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_CHAT_BOOTSTRAP)}`);
  const box=page.getByRole('textbox',{name:'Message TwinPulse'});
  await expect(box).toBeVisible();
  await expect(page.getByText('Build your Digital Twin',{exact:true})).toBeVisible();
  await page.screenshot({path:path.join(output,'desktop-welcome.png')});
  await page.getByRole('button',{name:/Readiness/}).click();
  await expect(page.getByRole('region',{name:'Runtime checklist'})).toBeVisible();
  await page.getByRole('button',{name:/Readiness/}).click();
  checks.push('UI-01 desktop / readiness details');
  if(scenario==='saved') {
    await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
    await expect(page.getByText(/Saved scene reopened for review/)).toBeVisible();
    const original=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    await page.getByRole('combobox',{name:'Scene operation'}).selectOption('add');
    await box.fill('Add a chair');await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect(page.getByText(/Provide X and Y in metres/)).toBeVisible();
    await box.fill('Add a chair x=0.8 y=-1.4');await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect(page.getByRole('button',{name:'Apply edit',exact:true})).toBeEnabled();
    await page.screenshot({path:path.join(output,'saved-edit-preview.png')});
    await page.getByRole('button',{name:'Apply edit',exact:true}).click();
    await expect(page.getByText(/Edit saved as a new scene revision/)).toBeVisible();
    const edited=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    if(edited.site_draft.revision===original.site_draft.revision || edited.site_draft.scene_edit_count!==1)
      throw new Error('Saved revision did not change exactly once');
    await page.getByRole('combobox',{name:'Scene operation'}).selectOption('change');
    await box.fill('Move chair x=0.5 y=-1.4 yaw=90');await page.getByRole('button',{name:'Send',exact:true}).click();
    await page.reload();
    const pendingChange=page.getByRole('region',{name:/^Change chair at/});
    await expect(pendingChange.getByRole('button',{name:'Cancel',exact:true})).toBeEnabled();
    await pendingChange.getByRole('button',{name:'Cancel',exact:true}).click();
    await expect(page.getByText('Edit cancelled. The saved scene is unchanged.',{exact:true})).toBeVisible();
    const cancelled=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    if(cancelled.site_draft.revision!==edited.site_draft.revision)throw new Error('Cancelling changed the saved revision');
    await page.screenshot({path:path.join(output,'saved-edit-cancelled.png')});
    checks.push('UI-09/17 saved scene reopen / Add preview and one apply / Change reload and Cancel preserve revision');
  } else {
  await box.fill('Create a compact warehouse');
  await box.press('Shift+Enter');
  await page.dispatchEvent('textarea','keydown',{key:'Enter',code:'Enter',isComposing:true,keyCode:229});
  await expect(page.getByRole('button',{name:'Simulation only',exact:true})).toHaveCount(0);
  await box.fill('Create a compact warehouse');
  checks.push('UI-03 built browser Shift+Enter / IME Enter do not send');
  if(scenario==='image') {
    await page.locator('input[type=file]').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('fixture')});
    await expect(page.getByRole('alert').filter({hasText:'PNG, JPEG, or WebP'})).toHaveCount(1);
    await expect(box).toHaveValue('Create a compact warehouse');
    await page.locator('input[type=file]').setInputFiles({name:'room.png',mimeType:'image/png',buffer:fs.readFileSync(process.env.TWINPULSE_CHAT_IMAGE)});
    await expect(page.getByAltText('Attached image preview')).toBeVisible();
  }
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('button',{name:'Simulation only',exact:true})).toBeEnabled();
  await expect(page.getByText('Waiting for your choice',{exact:true})).toBeVisible();
  await page.screenshot({path:path.join(output,'desktop-question.png')});
  const before=await page.evaluate(async()=>await (await fetch('/v1/product/workflow')).json());
  if(before.phase!=='input_ready')throw new Error('Generation started before the answer');
  await page.reload();
  await expect(page.getByText('Waiting for your choice',{exact:true})).toBeVisible();
  if(scenario==='image') await expect(page.getByAltText('room.png')).toBeVisible();
  checks.push(`UI-02 ${scenario==='image'?'image+text / retained thumbnail':'text only'} / UI-04 Q1 gate / UI-17 reload persists question`);
  // Intentionally discard an accepted response: the UI must recover by GET,
  // not send a second generation action.
  if(scenario==='real') {
    await page.getByRole('button',{name:'Use my robot',exact:true}).click();
    await expect(page.getByRole('button',{name:'TurtleBot3 Burger',exact:true})).toBeEnabled();
    const selected=await page.evaluate(async()=>await(await fetch('/v1/product/workflow')).json());
    if(selected.phase!=='input_ready')throw new Error('Generation began before registered robot choice');
    await page.reload();await expect(page.getByRole('button',{name:'TurtleBot3 Burger',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'TurtleBot3 Burger',exact:true}).click();
  } else if(scenario==='cancel') {
    await page.getByRole('button',{name:'Simulation only',exact:true}).click();
    await expect(page.getByRole('button',{name:'Stop response'})).toBeEnabled();
    await page.getByRole('button',{name:'Stop response'}).click();
  } else if(scenario==='failed') {
    await page.getByRole('button',{name:'Simulation only',exact:true}).click();
  } else {
  let posts=0;
  await page.route('**/v1/product/conversation',async route=> {
    if(route.request().method()==='POST') {
      posts++;await route.fetch();await route.abort('connectionreset');
    } else await route.continue();
  });
  await page.getByRole('button',{name:'Simulation only',exact:true}).click();
  await expect(page.getByText('Scene generation · completed',{exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole('button',{name:/Simulation only/})).toBeDisabled();
  if(posts!==1)throw new Error(`Duplicate POST after response loss: ${posts}`);
  checks.push('UI-05 answered+completed / UI-06 response-loss recovery, one POST');
  await page.unroute('**/v1/product/conversation');
  }
  const expectedState=scenario==='failed'?'failed':scenario==='cancel'?'cancelled':'completed';
  await expect(page.getByText(`Scene generation · ${expectedState}`,{exact:true})).toBeVisible({timeout:15000});
  if(scenario==='real') {
    await expect(page.getByText(/Physical preparation is unavailable in this backend/)).toBeVisible();
    await expect(page.getByRole('region',{name:'Robot preparation'})).toContainText('PHYSICAL_PREPARATION_NOT_CONFIGURED');
    const saved=await page.evaluate(async()=>await(await fetch('/v1/product/conversation')).json());
    if(saved.physical_authority!==false)throw new Error('Stored history granted physical authority');
    checks.push('UI-04 Q2 / REAL selection reload / generation gated / motion authority false');
  }
  if(scenario==='failed') {
    await expect(page.getByRole('alert').filter({hasText:'Provider configuration required'})).toHaveCount(1);
    await page.getByRole('button',{name:'Dismiss',exact:true}).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    // Dismiss removes the active alert, not the original diagnosis. Earlier
    // issues are intentionally collapsed so they do not look like current work.
    await expect(page.locator('.chat-earlier-error')).toContainText('provider_missing');
    await page.getByText('Earlier issue · dismissed',{exact:true}).click();
    await expect(page.locator('.chat-earlier-error p')).toBeVisible();
    await page.getByRole('button',{name:/Readiness/}).click();
    await expect(page.getByRole('region',{name:'Runtime checklist'})).toContainText('Owned engine fixture failure');
    await page.getByRole('button',{name:/Readiness/}).click();
    checks.push('UI-07 provider and engine errors separate / dismissal is not resolution');
  }
  if(scenario==='cancel')checks.push('UI-08 cancel actual generation / history retained / no repeat');
  await page.screenshot({path:path.join(output,'desktop-generated.png')});
  if(scenario==='text') {
    // A second authenticated request updates this conversation while the user
    // reads old messages. The incoming cursor must not steal scroll or focus.
    await page.evaluate(async()=>{
      for(let index=0;index<9;index++)await fetch('/v1/product/conversation',{method:'POST',headers:{'Content-Type':'application/json','X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},
        body:JSON.stringify({action:'message',request_id:crypto.randomUUID(),text:'status',mode:'new',attachment:null})});
    });
    await expect(page.locator('.chat-message.user')).toHaveCount(11);
    await box.focus();
    await page.locator('.chat-message-list').evaluate(node=>{node.scrollTop=0;});
    await page.waitForTimeout(50);
    await page.evaluate(async()=>await fetch('/v1/product/conversation',{method:'POST',headers:{'Content-Type':'application/json','X-TwinPulse-CSRF':sessionStorage.getItem('twinpulse.csrf')},
      body:JSON.stringify({action:'message',request_id:crypto.randomUUID(),text:'status',mode:'new',attachment:null})}));
    await expect(page.getByRole('button',{name:'New updates ↓'})).toBeVisible();
    if(await page.locator('.chat-message-list').evaluate(node=>node.scrollTop)>1)throw new Error('Incoming progress stole reading scroll');
    await expect(box).toBeFocused();
    await page.getByRole('button',{name:'New updates ↓'}).click();
    checks.push('UI-14 incoming persisted events do not steal reading scroll or composer focus');
  }
  await page.getByRole('button',{name:'Hide Twin'}).click();
  await expect(page.getByRole('complementary',{name:'Digital Twin'})).toHaveCount(0);
  await page.getByRole('button',{name:'Show Twin'}).click();
  await expect(page.getByText('No current 3D frame',{exact:true})).toBeVisible();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Orbit left',exact:true})).toBeDisabled();
  checks.push('UI-13 fold without restart; no fake Live');
  await page.setViewportSize({width:1280,height:800});
  await page.screenshot({path:path.join(output,'desktop-1280.png')});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Hide Twin'}).click();
  await expect(box).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(overflow)throw new Error('Mobile horizontal overflow');
  await page.screenshot({path:path.join(output,'mobile-chat.png')});
  await page.reload();
  await expect(box).toBeVisible();
  await expect(page.getByText(`Scene generation · ${expectedState}`,{exact:true})).toBeVisible();
  checks.push('UI-16 mobile 390x844 chat-first / UI-17 reload completed operation');
  if(scenario==='text') {
    await page.getByRole('button',{name:'Projects',exact:true}).click();
    await page.getByRole('textbox',{name:'New project name'}).fill('another_room');
    let creates=0;
    await page.route('**/v1/product/projects/create',async route=>{creates++;await route.fetch();await route.abort('connectionreset');});
    await page.getByRole('button',{name:'Create project',exact:true}).click();
    await expect(page.getByText(/another_room is present in the saved catalog/)).toBeVisible();
    if(creates!==1)throw new Error('Project create was repeated');
    await page.unroute('**/v1/product/projects/create');
    const projectState=await page.evaluate(async()=>await(await fetch('/v1/product/projects')).json());
    if(projectState.active_project_id!=='default')throw new Error('Creating a project implicitly replaced the current project');
    await page.getByRole('button',{name:'Open another_room',exact:true}).click();
    await expect(page.getByText(/Wait for the launcher's new window/)).toBeVisible();
    checks.push('UI-17 separate project creation / lost-create response queried / explicit switch request (owned restart NOT_RUN)');
  }
  }
  if(consoleErrors.length)throw new Error(`Browser exceptions: ${consoleErrors.join(',')}`);
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({status:'C1_SCOPED_BROWSER_API_PASS',checks,
    provider:'explicit deterministic fixture',isaac:'NOT_RUN',robot:'NOT_CONNECTED',console_errors:consoleErrors},null,2));
  console.log(JSON.stringify({status:'C1_SCOPED_BROWSER_API_PASS',checks:checks.length}));
} finally {await browser.close();}
