// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual Chrome/ordinary API; provider replies are explicitly audited fixtures.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_UI_URL,output=process.env.TWINPULSE_UI_OUTPUT;
if(!base||new URL(base).hostname!=='127.0.0.1'||!output)throw Error('Owned localhost configuration required');
const result={status:'FAIL',external_browser_requests:0,page_errors:[],choice_posts:0,checks:[],browser_closed:false};
let browser,page;
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_browser_requests++;return route.abort();}
    if(request.method()==='POST'&&url.pathname==='/v1/product/conversation'){
      const body=request.postDataJSON();if(body.action==='answer')result.choice_posts++;
    }
    return route.continue();
  });
  page=await context.newPage();page.on('pageerror',error=>result.page_errors.push(error.message));
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_UI_BOOTSTRAP)}`);
  const inventory=process.env.TWINPULSE_UI_CASE==='inventory',count=Number(process.env.TWINPULSE_UI_COUNT);
  const prompt=inventory?'Estimate these observed objects':'Create a bed in an estimated bedroom';
  await page.getByRole('textbox',{name:'Message TwinPulse'}).fill(prompt);
  if(process.env.TWINPULSE_UI_CASE==='photo-paste'||inventory){
    const encoded=fs.readFileSync(process.env.TWINPULSE_UI_IMAGE).toString('base64');
    await page.getByRole('heading',{name:'Digital Twin',exact:true}).click();
    await page.evaluate(base64=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      const transfer=new DataTransfer();transfer.items.add(new File([bytes],'pasted.png',{type:'image/png'}));
      Object.defineProperty(transfer,'files',{value:new DataTransfer().files}); // Explicit items-only browser shape.
      document.body.dispatchEvent(new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}));
    },encoded);
    await expect(page.getByAltText('Attached image preview')).toBeVisible();
    await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toHaveValue(prompt);
    if(result.choice_posts)throw Error('Paste dispatched an inference');
    await page.screenshot({path:path.join(output,'00-pasted-image.png')});
    result.checks.push('Items-only paste on the page attaches bytes and keeps the text; OS clipboard untouched');
  }
  await page.getByRole('button',{name:'Send',exact:true}).click();
  const question=page.getByRole('region',{name:'Do you have a physical robot?'});
  await expect(question).toBeVisible();
  await question.getByRole('radio',{name:'Simulation only'}).click();
  await expect(question.getByRole('button',{name:'Create Twin',exact:true})).toBeEnabled();
  await page.screenshot({path:path.join(output,'01-single-choice.png')});
  await question.getByRole('button',{name:'Create Twin',exact:true}).click();
  await expect(page.getByText(`Scene generation · ${inventory&&count===60?'failed':'completed'}`,{exact:true})).toBeVisible({timeout:30000});
  await expect(page.getByRole('region',{name:'Approve this scene-generation action and its spending limit?'})).toHaveCount(0);
  await expect(page.getByText(/Creating the Twin now, within your USD 1.00/)).toBeVisible();
  if(inventory){
    const progress=page.getByRole('status',{name:'Inventory work progress'});
    await expect(progress).toContainText(count===60?'42 of 60 objects parameterized · 18 pending':'36 of 36 objects parameterized · 0 pending');
    await progress.scrollIntoViewIfNeeded();
    if(count===60){
      await expect(progress).toContainText('Incomplete draft, not a verified scene');
      await expect(page.getByRole('button',{name:'Review generation budget and resume options'})).toBeEnabled();
    }
    result.checks.push('All declared inventory retained; progress matches saved checkpoint; no automatic resume');
  }
  await page.screenshot({path:path.join(output,inventory&&count===60?'02-saved-incomplete.png':'02-generated.png')});
  result.checks.push('One fresh SIM choice/cap starts normal generation; no second Approve question');
  if(result.choice_posts!==1||result.external_browser_requests||result.page_errors.length)throw Error('Duplicate choice, external request or page error');
  result.status='PASS';
}catch(error){result.error=String(error.message).replace(/#bootstrap=[^\s]+/g,'#bootstrap=[redacted]');
  if(page&&!page.isClosed())await page.screenshot({path:path.join(output,'failure.png')});
}finally{
  if(browser){await browser.close();result.browser_closed=true;}
  fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));
}
if(result.status!=='PASS')process.exitCode=1;
