// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual Chrome/App/API; explicitly synthetic engine state, no provider or robot.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_UI_URL, output=process.env.TWINPULSE_UI_OUTPUT;
if(!base||new URL(base).hostname!=='127.0.0.1'||!output)throw Error('Owned local UI configuration required');
const result={status:'FAIL',checks:[],external_requests:0,robot_requests:0,provider_requests:0,post_paths:[],page_errors:[],measurements:[]};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1920,height:1080}});
  await context.route('**/*',route=>{
    const request=route.request(), url=new URL(request.url());
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    if(request.method()==='POST'){
      result.post_paths.push(url.pathname);
      if(/\/robot\/|mission-start|inspection-start/.test(url.pathname)){result.robot_requests++;return route.abort();}
      if(/generation|scene-edit\/propose/.test(url.pathname)){result.provider_requests++;return route.abort();}
    }
    return route.continue();
  });
  page=await context.newPage();page.on('pageerror',error=>result.page_errors.push(error.message));
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_UI_BOOTSTRAP)}`);
  await expect(page.getByRole('button',{name:/Isaac connection status: Isaac starting/})).toBeVisible();
  await page.screenshot({path:path.join(output,'01-starting.png')});
  fs.writeFileSync(path.join(output,'ready.signal'),'explicit UI state transition');
  await expect(page.getByRole('button',{name:'Isaac connection status: Isaac connected'})).toBeVisible({timeout:15000});
  result.checks.push('Startup and observed connection are always visible, without opening checklist');
  if(process.env.TWINPULSE_UI_CASE==='history'){
    await expect(page.getByRole('region',{name:'Conversation home'})).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toHaveCount(0);
    await page.screenshot({path:path.join(output,'02-clean-home.png')});
    const search=page.getByRole('searchbox',{name:'Search conversations and projects'});
    await search.fill('다른 거실');await expect(page.getByRole('button',{name:'Open old_room'})).toBeVisible();
    await expect(page.getByRole('button',{name:'Open default'})).toHaveCount(0);await search.fill('');
    await page.getByRole('button',{name:'Open default'}).click();
    await expect(page.getByText('Previous run: provider exceeded 90s timeout',{exact:true})).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    result.checks.push('Explicit history browse/search preserves prior failure without current error banner or restart');
  }
  if(await page.getByRole('button',{name:'Hide Twin',exact:true}).count())await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  const box=page.getByRole('textbox',{name:'Message TwinPulse'});await expect(box).toBeVisible();
  const measure=async(label)=>{
    const metrics=await page.evaluate(()=>{const form=document.querySelector('.chat-composer'),list=document.querySelector('.chat-message-list'),input=document.querySelector('.chat-composer textarea');
      return {composer_height:form.getBoundingClientRect().height,message_height:list.getBoundingClientRect().height,
        textarea_height:input.getBoundingClientRect().height,window_height:innerHeight,horizontal_overflow:document.documentElement.scrollWidth>innerWidth};});
    result.measurements.push({label,...metrics});return metrics;
  };
  let m=await measure('desktop-empty');if(m.composer_height>160||m.message_height<540||m.horizontal_overflow)throw Error('Desktop empty composer occupies excessive reading space');
  await box.fill(Array.from({length:25},(_,i)=>`입력 줄 ${i+1}`).join('\n'));
  m=await measure('desktop-long');if(m.textarea_height>141||m.message_height<440)throw Error('Long input lost reading space');
  await page.screenshot({path:path.join(output,'03-compact-composer.png')});await box.fill('');
  await page.screenshot({path:path.join(output,'03b-desktop-reading.png')});
  await page.setViewportSize({width:390,height:844});
  const toggle=page.getByRole('button',{name:'Toggle conversations and projects'});
  if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
  m=await measure('mobile-empty');if(m.composer_height>190||m.message_height<300||m.horizontal_overflow)throw Error('Mobile reading area or width regressed');
  await page.screenshot({path:path.join(output,'04-mobile.png')});
  result.checks.push('Desktop/mobile compact composer, bounded auto growth and preserved message reading area');
  if(process.env.TWINPULSE_UI_CASE==='history'){
    await page.setViewportSize({width:1920,height:1080});if(await toggle.getAttribute('aria-expanded')==='false')await toggle.click();
    await page.getByRole('button',{name:'＋ New chat',exact:true}).click();
    await expect(page.getByText(/Opening a new chat/)).toBeVisible();
    await page.screenshot({path:path.join(output,'05-new-chat-request.png')});
    if(result.post_paths.filter(p=>p==='/v1/product/projects/create').length!==1||result.post_paths.filter(p=>p==='/v1/product/projects/switch').length!==1)throw Error('New chat creation or explicit switch was repeated');
    result.checks.push('New chat acknowledged create then explicit owned switch, no destructive history reset');
  }else{
    await box.fill('A compact room with a bed and desk');
    await page.getByRole('button',{name:'Send',exact:true}).click();
    await expect(page.getByRole('region',{name:'Do you have a physical robot?'})).toBeVisible();
    await page.screenshot({path:path.join(output,'05-one-current-question.png')});
    result.checks.push('Fresh text input reaches one ordinary question; no automatic answer or inference');
  }
  if(result.external_requests||result.robot_requests||result.provider_requests||result.page_errors.length)throw Error('Unexpected external/action/page fault');
  result.status='PASS';
}catch(error){result.error=String(error.message).replace(/#bootstrap=[^\s]+/g,'#bootstrap=[redacted]');
  if(page&&!page.isClosed()){result.alerts=await page.getByRole('alert').allTextContents();await page.screenshot({path:path.join(output,'failure.png')});}}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));}
if(result.status!=='PASS')process.exitCode=1;
