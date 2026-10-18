// SPDX-License-Identifier: Apache-2.0
// Read-only harness differential: no model, product POST, robot or fake response.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const out=process.argv[2];if(!out)throw Error('New output required');await fs.mkdir(out,{recursive:false});
const result={classification:'TEST_HARNESS_ROUTING_DIFFERENTIAL_NOT_NORMAL_USER_ACCEPTANCE',status:'IN_PROGRESS',failures:[],network_failures:[],posts:[],timeline:[]};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let phase='attach';
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));if(pages.length!==1)throw Error('One installed renderer required');const page=pages[0];
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 const cdp=await page.context().newCDPSession(page),requests=new Map();
 cdp.on('Network.requestWillBeSent',e=>{const p=new URL(e.request.url).pathname;if(p.startsWith('/v1/product/'))requests.set(e.requestId,{path:p,method:e.request.method,started_at:Date.now(),phase});});
 cdp.on('Network.loadingFailed',e=>{const r=requests.get(e.requestId);if(r)result.network_failures.push({...r,failed_at:Date.now(),failed_phase:phase,error:e.errorText,canceled:e.canceled,cors:e.corsErrorStatus,blocked:e.blockedReason});});await cdp.send('Network.enable');
 page.on('requestfailed',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/v1/product/'))result.failures.push({path:p,method:r.method(),at:Date.now(),phase,error:r.failure()?.errorText});});
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.startsWith('/v1/product/'))result.posts.push({path:new URL(r.url()).pathname,at:Date.now()});});
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 phase='quiet_baseline';await sleep(5000);
 for(let i=0;i<8;i++){
  const route=r=>r.continue();phase='enable_interception_'+i;result.timeline.push({phase,at:Date.now()});await page.route('**/v1/product/robot-fleet',route);await sleep(190);
  phase='disable_interception_'+i;result.timeline.push({phase,at:Date.now()});await page.unroute('**/v1/product/robot-fleet',route);await sleep(560);
 }
 phase='quiet_recovery';await sleep(3000);
 result.status=result.posts.length?'INVALID_UNEXPECTED_POST':result.failures.some(r=>r.phase.startsWith('disable_interception'))?'REPRODUCED_DURING_INTERCEPTION_DISABLE':'NOT_REPRODUCED';
 await page.screenshot({path:path.join(out,'quiet-after-routing.png')});
}catch(e){result.status='DIAGNOSTIC_FAILED';result.error=String(e);}
finally{await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));await browser.close();}
console.log(JSON.stringify(result));
