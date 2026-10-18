// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Fixed installed-window checks. No product API calls, fixtures or user commands.
const path=require('node:path'),fs=require('node:fs/promises');
const {chromium}=require('./testing/playwright-core');
const [endpoint,origin,folder,launchId]=process.argv.slice(2);
const result={schema:'twinpulse-basic-ui-checks-1.0',status:'FAIL',steps:[],screenshots:[],
  paid_generation:'NOT_RUN',robot_connection:'NOT_RUN',native_os:'NOT_RUN',http_errors:0,page_errors:0};
let browser,page,stage='attach';
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const check=async(name,action)=>{stage=name;const t=Date.now();try{await action();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-t});}
  catch{result.steps.push({name,status:'FAIL',elapsed_ms:Date.now()-t,code:'UI_CHECK_FAILED'});throw Error('UI_CHECK_FAILED');}};
const shot=async name=>{await page.screenshot({path:path.join(folder,name)});result.screenshots.push(name);};
async function main(){
  try{
    if(!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(endpoint)||!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(origin))throw Error('TARGET_REJECTED');
    browser=await chromium.connectOverCDP(endpoint,{timeout:10000});
    const pages=browser.contexts().flatMap(context=>context.pages()).filter(item=>new URL(item.url()).origin===origin);
    if(pages.length!==1)throw Error('WINDOW_AMBIGUOUS');[page]=pages;page.setDefaultTimeout(10000);
    result.desktop=await page.evaluate(()=>window.twinpulseDesktop.versions());
    if(result.desktop?.engine?.launch_id!==launchId)throw Error('LAUNCH_MISMATCH');
    page.on('pageerror',()=>result.page_errors++);
    page.on('response',response=>{if(new URL(response.url()).pathname.startsWith('/v1/product/')&&response.status()>=400)result.http_errors++;});
    await check('Idle installed window and authenticated Isaac',async()=>{
      await page.getByRole('dialog').waitFor({state:'hidden'});
      await page.getByText('Isaac connected',{exact:true}).first().waitFor();
      if(!await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).isEnabled())throw Error('APP_BUSY');
      await shot('01-home.png');
    });
    await check('Saved robot menu without discovery or connection',async()=>{
      await page.getByRole('button',{name:'Robots',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'Robots',exact:true});
      await dialog.getByRole('heading',{name:'Registered robots',exact:true}).waitFor();await shot('02-robots.png');
      await dialog.getByRole('button',{name:'Close',exact:true}).click();
    });
    await check('Library keyboard input and results',async()=>{
      await page.getByRole('button',{name:'Library',exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'Model library'});
      await dialog.getByRole('textbox',{name:'Search models'}).fill('desk');
      await dialog.getByRole('navigation',{name:'Library models'}).getByRole('button').first().waitFor();
      await shot('03-library.png');await dialog.getByRole('button',{name:'Close library',exact:true}).click();
    });
    await check('Actual Twin pane visibility',async()=>{
      const show=page.getByRole('button',{name:'Show Twin',exact:true});const opened=await show.isVisible();
      if(opened)await show.click();await page.getByRole('heading',{name:'Digital Twin',exact:true}).waitFor();
      await shot('04-twin.png');if(opened)await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
    });
    result.status=result.http_errors||result.page_errors?'FAIL':'PASS';
  }catch{result.error={stage,code:'BASIC_CHECK_NOT_CONFIRMED'};}
  finally{
    if(page&&!page.isClosed()){
      const close=page.getByRole('dialog').getByRole('button',{name:/^Close/});
      if(await close.count()===1)await close.click().catch(()=>{});
    }
    if(browser)await browser.close().catch(()=>{});
    await fs.writeFile(path.join(folder,'result.json'),JSON.stringify(result,null,2));
    const images=[];for(const name of result.screenshots){const data=await fs.readFile(path.join(folder,name));
      images.push(`<figure><img style="max-width:100%" src="data:image/png;base64,${data.toString('base64')}" alt="${esc(name)}"><figcaption>${esc(name)}</figcaption></figure>`);}
    await fs.writeFile(path.join(folder,'report.html'),`<!doctype html><meta charset="utf-8"><title>TwinPulse basic checks</title><main style="max-width:1100px;margin:auto;font:16px/1.6 system-ui"><h1>TwinPulse basic UI checks: ${result.status}</h1><p>Local/private. Screenshots may contain your project text or local device details. No upload. This is not paid generation, native OS or physical robot acceptance.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(result,null,2))}</pre>${images.join('')}</main>`);
  }
}
main().then(()=>process.exit(result.status==='PASS'?0:1)).catch(()=>process.exit(1));
