// SPDX-License-Identifier: Apache-2.0
// Installed Electron UI only. One authorized photo analysis; no API writes,
// injected completion, automatic retry, metric alignment or physical actions.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {reservePhotoSubmission} from './photo_call_allowance.mjs';
const [phase,output,project,candidateId,allowanceFile]=process.argv.slice(2);
if(!['analyze','adopt','undo','cold','cold-empty','cold-failed'].includes(phase)||!output)throw Error('phase/new output required');
await fs.mkdir(output,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);
const panel=p.getByRole('region',{name:'Import space',exact:true});
const result={phase,status:'FAIL',scope:'PHOTO_CANDIDATE_REVIEW_NOT_METRIC_ALIGNMENT_OR_ROBOT_QUALIFICATION',responses:[],steps:[],errors:[],hardware_actions:0};
const pending=new Set();let finish;
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
p.on('pageerror',e=>result.errors.push(String(e)));
p.on('response',r=>{const task=(async()=>{const u=new URL(r.url()),q=r.request();
 if(!u.pathname.startsWith('/v1/product/environment')&&!u.pathname.startsWith('/v1/product/scene-edit'))return;
 const row={path:u.pathname,method:q.method(),status:r.status(),at:Date.now()};
 if(q.method()==='POST')try{const b=q.postDataJSON();row.action=b.action;row.request_id=b.request_id;}catch{}
 try{row.body=await r.json();}catch{}result.responses.push(row);
 })();pending.add(task);void task.finally(()=>pending.delete(task));});
const step=async(name,work)=>{await work();result.steps.push({name,status:'PASS',at:Date.now()});await save();console.log(name);};
const shot=async name=>{await p.screenshot({path:path.join(output,name+'.png')});await fs.writeFile(path.join(output,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const state=()=>[...result.responses].reverse().find(r=>r.body?.status==='imported'&&r.body?.scene_revision)?.body;
try{
 result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());
 await expect(p.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 if(phase==='analyze'){
  finish=await recordRenderedPage(p,path.join(output,'recording'));
  await step('New chat original USD and explicit selected SIM units',async()=>{
   await p.getByRole('button',{name:'＋ New chat',exact:true}).click();
   await p.locator('input[type=file]').first().setInputFiles('C:/Users/jaewo/OneDrive/문서/카카오톡 받은 파일/Project-2610222326.usd');
   await p.getByRole('button',{name:'Import space',exact:true}).last().click();
   await panel.getByLabel('Space source units',{exact:true}).selectOption('m');await panel.getByRole('button',{name:'Inspect space',exact:true}).click();
   await expect(panel.getByText('Inspection ready · review units and objects before import.',{exact:true})).toBeVisible({timeout:110000});
   await panel.getByRole('button',{name:'Import space',exact:true}).click();await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible();
   result.project_id=state()?.project_id;
  });
  await step('Explicit Build original room',async()=>{await panel.getByRole('button',{name:'Show Twin',exact:true}).click();
   await expect(panel.getByText('Build command: succeeded · receipt received',{exact:true})).toBeVisible({timeout:120000});});
  await step('One explicitly approved photo analysis',async()=>{
   await panel.getByText('Added obstacles · 0').click();
   await panel.getByLabel('Obstacle reference photo').setInputFiles('C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg');
   await expect(panel.getByRole('button',{name:'Analyze photo',exact:true})).toBeDisabled();
   await panel.getByLabel('Allow photo analysis').check();await shot('01-consent');
   // This guard is never automatically removed, even on unknown/error outcome.
   if(candidateId&&!/^[a-z0-9-]{1,40}$/.test(candidateId))throw Error('Invalid authorization reference');
   const guard=candidateId?'authorization-consumed-'+candidateId+'.json':'authorization-consumed.json';
   await fs.writeFile(path.join(path.dirname(output),guard),JSON.stringify({photo:'KakaoTalk_20261023_001642352.jpg',max_calls:1,authorization_reference:candidateId??'initial',at:Date.now()}),{flag:'wx'});
   if(allowanceFile)result.allowance_claim=await reservePhotoSubmission(allowanceFile,'C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg',{output,project_id:result.project_id});
   await panel.getByRole('button',{name:'Analyze photo',exact:true}).click();
   await expect.poll(()=>state()?.photo_proposal?.status,{timeout:330000}).toMatch(/^(ready|failed|cancelled)$/);
   result.proposal=state()?.photo_proposal;result.environment=state();await shot('02-observed-result');
   if(result.responses.filter(r=>r.action==='photo_analyze').length!==1)throw Error('Expected one submitted action');
   if(result.proposal?.status!=='ready')throw Error('Actual call did not yield a ready result; no retry: '+result.proposal?.error);
  });
 }else if(phase==='undo'){
  result.project_id=project;await expect(panel).toBeVisible();
  await step('Undo photo adoption with exact current-frame commit',async()=>{
   const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='undo_preview');
   await panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click();const r=await response,b=await r.json();
   if(r.status()!==200||!b.preview)throw Error('Undo preview failed');result.preview=b.preview;
   const accepted=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/scene-edit/apply'&&r.request().method()==='POST');
   await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();const applied=await accepted;result.receipt=await applied.json();
   if(applied.status()!==202||result.receipt.operation_id!==result.preview.operation.operation_id)throw Error('Wrong Undo receipt');
   await expect.poll(()=>[...result.responses].reverse().find(r=>r.path==='/v1/product/scene-edit/transaction'&&r.body?.operation_id===result.preview.operation.operation_id)?.body,{timeout:135000})
    .toMatchObject({state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:true,result_revision:result.preview.result_revision});
   await expect(panel.getByText('Added obstacles · 0')).toBeVisible();result.environment=state();await shot('undo-current-frame');
  });
 }else if(phase==='adopt'){
  await expect(panel).toBeVisible();result.project_id=project;
  if(!candidateId)throw Error('Explicit reviewed candidate id required');
  finish=await recordRenderedPage(p,path.join(output,'recording'));
  await step('Review image candidate with explicit test placement and duplicate check',async()=>{
   // Schema 1.2: a candidate next to a named scanned/added object arrives with a local suggested center (estimate); otherwise X stays empty.
   const reviewed=state()?.photo_proposal?.candidates?.find(c=>c.id===candidateId);result.suggested=reviewed?.suggested??null;result.suggestion_reason=reviewed?.suggestion_reason??null;
   await panel.getByRole('button',{name:'Review '+candidateId,exact:true}).click();
   await expect(panel.getByLabel('Obstacle X',{exact:true})).toHaveValue(reviewed?.suggested?String(reviewed.suggested.position_m[0]):'');
   const xy=allowanceFile?JSON.parse(await fs.readFile(allowanceFile,'utf8')).obstacle_xy:[-3.15,-.45];
   await panel.getByLabel('Obstacle X',{exact:true}).fill(String(xy[0]));await panel.getByLabel('Obstacle Y',{exact:true}).fill(String(xy[1]));
   await panel.getByLabel('Obstacle name').fill('Photo candidate - test placement');
   await expect(panel.getByRole('button',{name:'Preview obstacle',exact:true})).toBeDisabled();
   await panel.getByLabel('Candidate duplicate reviewed').check();await shot('03-reviewed-estimate');
   const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='photo_candidate_preview');
   await panel.getByRole('button',{name:'Preview obstacle',exact:true}).click();const r=await response,b=await r.json();
   if(r.status()!==200||!b.preview)throw Error('Candidate preview failed: '+JSON.stringify(b));result.preview=b.preview;
  });
  await step('Common Apply exact ACK durable commit and current frame',async()=>{
   const accepted=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/scene-edit/apply'&&r.request().method()==='POST');
   await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();const r=await accepted;result.receipt=await r.json();
   if(r.status()!==202||result.receipt.operation_id!==result.preview.operation.operation_id)throw Error('Wrong Apply receipt');
   await expect.poll(()=>[...result.responses].reverse().find(r=>r.path==='/v1/product/scene-edit/transaction'&&r.body?.operation_id===result.preview.operation.operation_id)?.body,{timeout:135000})
    .toMatchObject({state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:true,result_revision:result.preview.result_revision});
   await expect(panel.getByText('Added obstacles · 1')).toBeVisible();result.environment=state();await shot('04-applied-current-frame');
  });
  await step('English compact layout no horizontal panel overflow',async()=>{
   for(const [width,height] of [[1280,720],[1024,768]]){await p.setViewportSize({width,height});const d=await panel.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));
    if(d.scroll>d.width+1)throw Error('Horizontal overflow');(result.layouts??=[]).push({width,height,...d});await shot('layout-'+width);}
  });
 }else{
  finish=await recordRenderedPage(p,path.join(output,'recording'));
  await step('Cold reopen same project read-only proposal and saved overlay',async()=>{
   if(!project)throw Error('Same project required');result.project_id=project;
   const toggle=p.getByRole('button',{name:'Toggle conversations and projects',exact:true});if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
   await p.getByRole('button',{name:'Open '+project,exact:true}).click();const reopen=p.getByRole('button',{name:'Reopen saved scene',exact:true});await reopen.click();await reopen.waitFor({state:'hidden',timeout:45000});
   await p.getByRole('button',{name:'Import space',exact:true}).first().click();await panel.getByText('Added obstacles · '+(['cold-failed','cold-empty'].includes(phase)?'0':'1')).click();
   if(phase==='cold-failed')await expect(panel.getByRole('alert').filter({hasText:'Configured harness composition failed'})).toBeVisible();
   else await expect(panel.getByText(/^Photo candidates · [0-6]$/)).toBeVisible();
   result.environment=state();result.proposal=state()?.photo_proposal;
   if(result.proposal?.status!==(phase==='cold-failed'?'failed':'ready')||result.responses.some(r=>r.action==='photo_analyze'))throw Error('Cold result missing or repeated request');
  });
  await step('Explicit saved scene Build no restored model call',async()=>{
   await panel.getByRole('button',{name:'Show Twin',exact:true}).click();await expect(panel.getByText('Build command: succeeded · receipt received',{exact:true})).toBeVisible({timeout:120000});await shot('05-cold-proposal-scene');
  });
 }
 if(result.errors.length||result.responses.some(r=>r.status>=400))throw Error('Retained renderer/HTTP failure');
 result.status='PASS_SCOPED';
}catch(e){result.errors.push(String(e));await shot('failure').catch(()=>{});}
finally{await Promise.all([...pending]);if(finish)result.recording=await finish().catch(e=>({error:String(e)}));await save();await browser.close();}
if(result.status!=='PASS_SCOPED')throw Error(result.errors.join('\n'));
