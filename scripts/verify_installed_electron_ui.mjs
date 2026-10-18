// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Attach to the actual installed Electron renderer. Never launch Chrome, seed
// state/cookies, stub responses or call a product mutation endpoint.
import {chromium, expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const args=process.argv.slice(2);
const arg=name=>args[args.indexOf(name)+1];
const endpoint=arg('--cdp'), output=arg('--output'), action=args.includes('--exit')?'exit':'smoke';
if(!args.includes('--cdp')||!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(endpoint)||!args.includes('--output'))
  throw Error('Usage: node scripts/verify_installed_electron_ui.mjs --cdp http://127.0.0.1:PORT --output NEW_DIRECTORY [--exit]');
await fs.mkdir(output,{recursive:false});
const result={schema:'twinpulse-installed-electron-ui-1.0',status:'FAIL',action,
  transport:'CDP on installed Electron BrowserWindow',steps:[],screenshots:[],page_errors:[],http_errors:[],
  native_os_input:'NOT_RUN',native_file_dialog:'NOT_RUN',native_titlebar_close:'NOT_RUN',paid_generation:'NOT_RUN'};
const clean=value=>String(value).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]').slice(0,1200);
let browser,page;
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await page.screenshot({path:path.join(output,name)});result.screenshots.push(name);};
const step=async(name,fn)=>{const start=Date.now();try{await fn();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-start});}
  catch(error){result.steps.push({name,status:'FAIL',elapsed_ms:Date.now()-start,error:clean(error)});
    await shot('failure-step-'+result.steps.length+'.png').catch(()=>{});
    if(action==='exit')throw error;
    // Independent menu checks may continue after retaining the actual failure.
    const close=page.getByRole('dialog').getByRole('button',{name:/^Close/});
    if(await close.count()===1)await close.click();
  }finally{await save();}};
try{
  browser=await chromium.connectOverCDP(endpoint,{timeout:15000});
  const pages=browser.contexts().flatMap(context=>context.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
  if(pages.length!==1)throw Error('Expected exactly one ordinary TwinPulse Electron renderer');
  [page]=pages;page.setDefaultTimeout(20000);
  result.origin=new URL(page.url()).origin;result.title=await page.title();
  // Read-only preload -> authenticated main/manager response proves this is
  // the desktop host. No private control socket, token or raw session access.
  result.desktop_versions=await page.evaluate(()=>window.twinpulseDesktop?.versions());
  if(!result.desktop_versions?.electron||!result.desktop_versions?.engine?.launch_id)throw Error('Desktop host identity unavailable');
  result.user_agent=await page.evaluate(()=>navigator.userAgent);
  if(!result.user_agent.includes('Electron/'))throw Error('Target is not Electron');
  page.on('pageerror',error=>result.page_errors.push(clean(error)));
  page.on('response',async response=>{if(response.status()>=400){
    const row={path:new URL(response.url()).pathname,status:response.status()};result.http_errors.push(row);
    if(row.path==='/v1/product/robots')try{const body=await response.json();row.code=body.code??body.error?.code;row.message=body.message??body.error?.message;}catch{}
  }});
  const oldDialog=page.getByRole('dialog').getByRole('button',{name:/^Close/});
  if(await oldDialog.count()===1)await oldDialog.click();
  if(action==='exit'){
    await step('Visible Exit TwinPulse button requests ordinary shutdown',async()=>{
      await shot('01-before-exit.png');
      await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();
      await page.waitForEvent('close',{timeout:60000});
    });
  }else{
    await step('Installed Electron home and actual Isaac connection',async()=>{
      await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible();
      await expect(page.getByRole('button',{name:'Exit TwinPulse',exact:true})).toBeVisible();
      await shot('01-electron-home.png');
      await fs.writeFile(path.join(output,'01-home.aria.txt'),await page.locator('body').ariaSnapshot());
    });
    await step('Robots menu opens and loads',async()=>{
      await page.getByRole('button',{name:'Robots',exact:true}).click();
      const dialog=page.getByRole('dialog');
      await expect(dialog.getByRole('heading',{name:'Registered robots'})).toBeVisible();
      await shot('02-robots.png');
      await dialog.getByRole('button',{name:/^Close/}).click();
    });
    await step('Library search accepts keyboard input',async()=>{
      await page.getByRole('button',{name:'Library',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'Model library'});
      const input=dialog.getByRole('textbox',{name:'Search models'});
      await input.click();await input.pressSequentially('desk');await expect(input).toHaveValue('desk');
      await expect(dialog.getByRole('navigation',{name:'Library models'}).getByRole('button').first()).toBeVisible();
      await shot('03-library-search.png');await dialog.getByRole('button',{name:'Close library'}).click();
    });
    await step('API/model settings open without changing routes',async()=>{
      await page.getByRole('button',{name:'API keys',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'API keys'});
      await expect(dialog.getByText('Model routing',{exact:true})).toBeVisible();
      await shot('04-settings.png');await dialog.getByRole('button',{name:'Close',exact:true}).click();
    });
    await step('New chat and Korean composer input',async()=>{
      const home=page.getByRole('button',{name:'＋ Start a new chat',exact:true});
      if(await home.isVisible())await home.click();
      else await page.getByRole('button',{name:'＋ New chat',exact:true}).click();
      const input=page.getByRole('textbox',{name:'Message TwinPulse'});
      await input.click();await expect(input).toBeFocused();
      const text='설치된 Electron 창에서 직접 입력을 확인합니다. 이 문장은 전송하지 않습니다.';
      await page.keyboard.insertText(text);await expect(input).toHaveValue(text);
      await shot('05-korean-input.png');
      await input.press('Control+A');await input.press('Backspace');await expect(input).toHaveValue('');
    });
    await step('Twin pane opens and closes in the installed window',async()=>{
      const show=page.getByRole('button',{name:'Show Twin',exact:true});
      if(await show.isVisible())await show.click();
      await expect(page.getByRole('heading',{name:'Digital Twin',exact:true})).toBeVisible();
      await shot('06-twin-pane.png');
      await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
      await expect(page.getByRole('button',{name:'Show Twin',exact:true})).toBeVisible();
    });
  }
  if(result.page_errors.length||result.http_errors.length)throw Error('Renderer or HTTP errors observed; retain failed attempt');
  result.status=result.steps.some(item=>item.status==='FAIL')?'FAIL':'PASS';
}catch(error){result.error=clean(error);if(page&&!page.isClosed()){
  await shot('failure.png').catch(()=>{});
  await fs.writeFile(path.join(output,'failure.aria.txt'),await page.locator('body').ariaSnapshot()).catch(()=>{});
}}
finally{
  // For a connected CDP client close() detaches; only the visible Exit button
  // above is allowed to terminate the product in this test.
  if(browser)await browser.close().catch(()=>{});await save();
}
console.log(JSON.stringify({status:result.status,action,launch_id:result.desktop_versions?.engine?.launch_id,steps:result.steps}));
process.exitCode=result.status==='PASS'?0:1;
