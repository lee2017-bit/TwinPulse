// SPDX-License-Identifier: Apache-2.0
// Read-only transport diagnostic on the actual installed BrowserWindow.
// Not a user journey, model response, state injection or physical test.
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
const [startPath,out]=process.argv.slice(2);
const start=JSON.parse(await fs.readFile(startPath,'utf8'));
const browser=await chromium.connectOverCDP(start.cdp_endpoint);
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('ONE_INSTALLED_WINDOW_REQUIRED');
const page=pages[0],cdp=await page.context().newCDPSession(page),requests=new Map();
const result={classification:'READ_ONLY_DIAGNOSTIC_NOT_USER_ACCEPTANCE',launch_id:start.launch_id,fetches:[],network:[]};
cdp.on('Network.requestWillBeSent',e=>{const sequence=e.request.headers['X-TwinPulse-Diagnostic-Sequence'];if(sequence!==undefined){
 const row={browser_request_id:e.requestId,sequence:Number(sequence),resource_type:e.type,began:e.timestamp};
 requests.set(e.requestId,row);result.network.push(row);
}});
cdp.on('Network.responseReceived',e=>{const row=requests.get(e.requestId);if(row)Object.assign(row,{status:e.response.status,response_at:e.timestamp});});
cdp.on('Network.loadingFinished',e=>{const row=requests.get(e.requestId);if(row)Object.assign(row,{finished_at:e.timestamp,encoded_length:e.encodedDataLength});});
cdp.on('Network.loadingFailed',e=>{const row=requests.get(e.requestId);if(row)Object.assign(row,{failed_at:e.timestamp,error:e.errorText,canceled:e.canceled});});
await cdp.send('Network.enable');
await page.getByRole('button',{name:'API keys',exact:true}).waitFor({timeout:120000});
result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
for(let sequence=0;sequence<8;sequence++){
 result.fetches.push(await page.evaluate(async sequence=>{
  const began=performance.now();
  try{
   const session=await (await fetch('/v1/product/session',{cache:'no-store',credentials:'same-origin'})).json();
   const response=await fetch('/v1/product/viewport/current',{cache:'no-store',credentials:'same-origin',
    headers:{'X-TwinPulse-Context':session.context_id,'X-TwinPulse-Diagnostic-Sequence':String(sequence)}});
   const state=JSON.parse(response.headers.get('X-TwinPulse-Viewport')??'null');
   const consume=sequence%2===0;const bytes=consume?(await response.arrayBuffer()).byteLength:null;
   return {sequence,consume,status:response.status,body_bytes:bytes,body_null:response.body===null,content_length:response.headers.get('Content-Length'),
    receipt:{state:state?.state,frame:state?.frame,physical_authority:state?.physical_authority},fetch_fulfilled:true,elapsed_ms:performance.now()-began};
  }catch(error){return {sequence,fetch_fulfilled:false,error:String(error),elapsed_ms:performance.now()-began};}
 },sequence));
 await page.waitForTimeout(100);
}
await page.waitForTimeout(250);
await fs.mkdir(path.dirname(out),{recursive:true});
await fs.writeFile(out,JSON.stringify(result,null,2),{flag:'wx'});
// Only actual visible App shutdown; no direct product mutation API.
await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();
await page.waitForEvent('close',{timeout:30000}).catch(()=>{});
await browser.close();
console.log(JSON.stringify({fetches:result.fetches,network:result.network}));
