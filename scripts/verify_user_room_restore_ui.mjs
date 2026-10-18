// SPDX-License-Identifier: Apache-2.0
// Saved user-room reference only: no provider, robot connection or motion.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1],out=arg('--output'),project=arg('--project');
if(!out||!project)throw Error('Explicit new output and saved project required');await fs.mkdir(out,{recursive:false});
const result={status:'IN_PROGRESS',project,classification:'SAVED_USER_ROOM_REFERENCE_NOT_FRESH_PHOTO_QUALITY_OR_LOCALIZATION',steps:[],screenshots:[],http_errors:[],posts:[],physical:'NOT_RUN_OFF',provider_calls:0};
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
let page,workflow,conversation,conversationContext;const pending=[],workflows=new Map();
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
const poll=async test=>{const end=Date.now()+30000;while(Date.now()<end){if(test())return;await new Promise(r=>setTimeout(r,100));}throw Error('Current saved-room state not observed');};
const step=async(name,fn)=>{const at=Date.now();try{const evidence=await fn();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-at,evidence});}catch(e){result.steps.push({name,status:'FAIL',error:String(e)});throw e;}finally{await save();}};
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));if(pages.length!==1)throw Error('One installed renderer required');[page]=pages;
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());if(!result.desktop?.engine?.launch_id)throw Error('Missing installed identity');
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.startsWith('/v1/product/')){let b;try{b=r.postDataJSON();}catch{}result.posts.push({path:new URL(r.url()).pathname,action:b?.action});}});
 page.on('response',r=>pending.push((async()=>{const p=new URL(r.url()).pathname;
  if(r.status()>=400&&p.startsWith('/v1/product/'))result.http_errors.push({path:p,status:r.status()});
  const context=r.headers()['x-twinpulse-context']??'';
  if(r.status()===200&&p==='/v1/product/conversation'){conversation=await r.json();conversationContext=context;workflow=workflows.get(context);}
  if(r.status()===200&&p==='/v1/product/workflow'){const value=await r.json();workflows.set(context,value);if(context===conversationContext)workflow=value;}
 })().catch(()=>{})));
 await step('Actual saved user-room chat open and display in current Isaac',async()=>{
  await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
  await page.getByRole('button',{name:'Open '+project,exact:true}).click();
  await expect(page.locator('.chat-project-caption')).toContainText(project);await poll(()=>conversation?.project_id===project&&!!workflow?.site_draft);
  const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
  const show=page.getByRole('button',{name:'Show Twin',exact:true});if(await show.isVisible())await show.click();
  await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();await page.getByRole('button',{name:'View current Twin',exact:true}).click();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
  const scene=workflow.site_draft;await fs.writeFile(path.join(out,'saved-scene.json'),JSON.stringify(scene,null,2));
  await page.screenshot({path:path.join(out,'user-room-current.png')});result.screenshots.push('user-room-current.png');
  return {project,conversation_session_id:conversation.session_id,scene_revision:scene.revision,input_revision:scene.input_revision,
   scene_json_sha256:createHash('sha256').update(JSON.stringify(scene,null,2)).digest('hex'),object_count:scene.objects?.length,
   quality:'Prior PARTIAL/uncertain retained; this is restore/display only',world_alignment:'UNVERIFIED'};
 });
 await step('No fresh generation or robot activation; actual normal Exit',async()=>{
  if(result.posts.some(p=>p.path==='/v1/product/robot-fleet'&&['connect','prepare','drive','field_arm','field_test'].includes(p.action)))throw Error('Unexpected robot activation');
  if(result.posts.some(p=>p.path==='/v1/product/conversation'&&p.action==='message'))throw Error('Unexpected new generation request');
  const close=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await close;
 });
 await Promise.allSettled(pending);result.status=result.http_errors.length?'FAIL':'PASS';
}catch(e){result.status='FAIL';result.error=String(e);if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});}
finally{await save();await browser.close();}
console.log(JSON.stringify({status:result.status,steps:result.steps,error:result.error}));if(result.status!=='PASS')process.exitCode=1;
