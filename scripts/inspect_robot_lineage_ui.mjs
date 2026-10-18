// SPDX-License-Identifier: Apache-2.0
// Read only: the actual same installed Electron renderer, no product API calls.
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const out=process.argv[2];if(!out)throw Error('New output directory required');await fs.mkdir(out,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));if(pages.length!==1)throw Error('Exactly one renderer required');
 const page=pages[0];let workflow,conversation;
 page.on('response',async r=>{if(new URL(r.url()).pathname==='/v1/product/conversation'&&r.status()===200){try{const v=await r.json();conversation={project_id:v.project_id,restore_error:v.restore_error,accepted_request_ids:v.accepted_request_ids};}catch{}}});
 page.on('response',async r=>{if(new URL(r.url()).pathname==='/v1/product/workflow'&&r.status()===200){try{workflow=await r.json();}catch{}}});
 await new Promise(r=>setTimeout(r,4500));
 if(conversation){await fs.writeFile(out+'/conversation-status.json',JSON.stringify(conversation,null,2));console.log(JSON.stringify(conversation));}
 if(workflow){const s=workflow.site_draft;const summary={phase:workflow.phase,revision:s?.revision,keys:Object.keys(s??{}),site:s};
 await fs.writeFile(out+'/workflow-scene.json',JSON.stringify(summary,null,2));console.log(JSON.stringify({phase:summary.phase,revision:summary.revision,keys:summary.keys}));}
 const text=await page.locator('body').innerText();await fs.writeFile(out+'/visible.txt',text);await page.screenshot({path:out+'/screen.png'});
 console.log(text.slice(0,2400));}finally{await browser.close();}
