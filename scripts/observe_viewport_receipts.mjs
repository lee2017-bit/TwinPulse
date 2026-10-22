// SPDX-License-Identifier: Apache-2.0
// Passive responses from the same installed BrowserWindow. No requests/actions.
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const [output,resultFile]=process.argv.slice(2);
if(!output||!resultFile)throw Error('Explicit new output and actual journey result required');
await fs.mkdir(output,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('One actual installed renderer required');
const page=pages[0],identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());
if(!identity?.engine?.release_id)throw Error('Installed release identity missing');
const rows=[],pending=new Set();let active=true;
page.on('response',response=>{
 const name=new URL(response.url()).pathname;
 if(!active||!['/v1/product/viewport','/v1/product/viewport/current'].includes(name))return;
 const task=(async()=>{try{
  const received_at=Date.now(),value=name.endsWith('/current')?JSON.parse(response.headers()['x-twinpulse-viewport']??'null'):await response.json();
  const frame=value?.frame;
  rows.push({received_at,path:name,status:response.status(),state:value?.state,fps:value?.fps,
   camera_pending:value?.camera_pending,frame:frame?Object.fromEntries(['frame_id','captured_at_ms','engine_session_id','stage_epoch','applied_revision','camera_sequence','sha256'].map(key=>[key,frame[key]])):null});
 }catch(error){rows.push({at:Date.now(),path:name,error:String(error)});}})();
 pending.add(task);void task.finally(()=>pending.delete(task));
});
let terminal=null;const began=Date.now();
while(Date.now()-began<20*60*1000){
 try{const result=JSON.parse(await fs.readFile(resultFile,'utf8'));if(result.status&&result.status!=='IN_PROGRESS'){terminal={status:result.status,project:result.project};break;}}catch{}
 await new Promise(resolve=>setTimeout(resolve,500));
}
active=false;await Promise.all(pending);
await fs.writeFile(path.join(output,'receipts.json'),JSON.stringify({identity,terminal,began,end:Date.now(),
 classification:'PASSIVE_EXISTING_RESPONSES_NOT_A_USER_JOURNEY_OR_TIMING_BENCHMARK',rows},null,2),{flag:'wx'});
await browser.close();
