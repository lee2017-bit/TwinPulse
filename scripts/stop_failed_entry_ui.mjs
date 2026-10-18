// SPDX-License-Identifier: Apache-2.0
// Explicit actual UI cleanup of a failed SIM journey, never continuation PASS.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const out=process.argv[2];if(!out)throw Error('New evidence file required');
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');const page=pages[0];
 const identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());let stopReceipt=null;
 page.on('response',async r=>{if(r.request().method()==='POST'&&new URL(r.url()).pathname==='/v1/product/robot-fleet'){
  const body=r.request().postDataJSON();if(body.action==='stop_all')stopReceipt={status:r.status(),request_id:body.request_id,response:await r.json()};
 }});
 const stop=page.getByRole('button',{name:'Stop all',exact:true});
 if(await stop.isEnabled())await stop.click();
 await expect.poll(()=>stopReceipt?.status,{timeout:15000}).toBe(200);
 await page.waitForTimeout(1500);
 const snapshot=await page.locator('body').innerText();
 const closing=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
 await fs.writeFile(out,JSON.stringify({classification:'FAILED_JOURNEY_SEPARATE_STOP_AND_NORMAL_EXIT_NOT_CONTINUATION_PASS',identity,stopReceipt,ui_text_after_stop:snapshot,physical_activation:0},null,2),{flag:'wx'});
}finally{await browser.close();}
