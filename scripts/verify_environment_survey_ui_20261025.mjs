// SPDX-License-Identifier: Apache-2.0
// Installed ordinary UI, actual Isaac scans/model. No API mutation or mocks.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {reserveDevelopmentCall} from './development_call_allowance.mjs';
const [output,sourceFile,phase='review',allowance]=process.argv.slice(2);
if(!output||!sourceFile||!['review','hybrid','adopt','reapply','cold','restore'].includes(phase))throw Error('New output, original task result and phase required');
await fs.mkdir(output,{recursive:false});const original=JSON.parse(await fs.readFile(sourceFile,'utf8'));
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);let survey,environment,frame,transaction,finish;const pending=new Set();
const result={status:'FAIL',phase,steps:[],requests:[],errors:[],frames:[],scope:'INSTALLED_COLLECTION_REGISTRATION_ESTIMATED_OVERLAY_NOT_PHYSICAL_QUALIFICATION',physical_actions:0};
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await p.screenshot({path:path.join(output,name+'.png')});await fs.writeFile(path.join(output,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const step=async(name,fn)=>{await fn();result.steps.push({name,status:'PASS',at:Date.now()});await save();console.log(name);};
p.on('pageerror',e=>result.errors.push(String(e)));p.on('response',r=>{const work=(async()=>{const u=new URL(r.url()),q=r.request();if(u.pathname==='/v1/product/viewport/current'){try{frame=JSON.parse(r.headers()['x-twinpulse-viewport']).frame;}catch{}return;}
 if(!u.pathname.startsWith('/v1/product/environment')&&!u.pathname.startsWith('/v1/product/scene-edit'))return;
 let value;try{value=await r.json();}catch{return;}
 if(u.pathname==='/v1/product/environment/survey')survey=value;
 if(u.pathname==='/v1/product/environment'||u.pathname==='/v1/product/environment/action')environment=value;
 if(u.pathname==='/v1/product/scene-edit/transaction')transaction=value;
 if(q.method()==='POST'){const body=q.postDataJSON();if(body.photo)body.photo={name:body.photo.name,bytes_base64:'REDACTED_IN_UI_LOG_ORIGINAL_PHOTO_PRESERVED_LOCALLY'};result.requests.push({path:u.pathname,request:body,status:r.status(),body:value});}
 })();pending.add(work);void work.finally(()=>pending.delete(work));});
const panel=p.getByRole('region',{name:'Import space',exact:true}),review=p.getByRole('region',{name:'Collected survey review',exact:true});
const open=async()=>{if(!await panel.isVisible())await p.getByRole('button',{name:'Import space',exact:true}).first().click();await panel.getByRole('button',{name:'Check saved import',exact:true}).click();if(!await review.isVisible())await panel.getByText('Collected survey · missing obstacles',{exact:true}).click();await expect(review).toBeVisible();await expect.poll(()=>survey?.context?.scene_revision).toBeTruthy();await expect.poll(()=>environment?.scene_revision).toBeTruthy();};
const apply=async preview=>{transaction=null;const accepted=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/scene-edit/apply'&&r.request().method()==='POST');await panel.getByRole('button',{name:'Apply space edit',exact:true}).click();const r=await accepted,ack=await r.json();if(r.status()!==202||ack.operation_id!==preview.operation.operation_id)throw Error('Exact Apply ACK missing: '+JSON.stringify(ack));
 await expect.poll(()=>transaction,{timeout:135000}).toMatchObject({operation_id:preview.operation.operation_id,state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:true,result_revision:preview.result_revision});
 await expect(panel.getByRole('button',{name:'Undo last edit · preview',exact:true})).toBeEnabled();(result.edits??=[]).push({preview,ack,transaction});};
const check=async()=>{const previous=survey?.job?.job_id;await review.getByLabel('Survey source').selectOption('TASK');await review.getByLabel('Survey collection').selectOption(original.final_task.task_id);
 const pose=original.start.pose.position_m;for(const [i,name] of ['X (m)','Y (m)','Yaw (rad)'].entries())await review.getByLabel('Survey '+name,{exact:true}).fill(String(pose[i]));
 const ref=survey.references[0];await review.getByLabel('Survey reference wall').selectOption(ref.id);await review.getByLabel('Survey reference span').fill(String(ref.length_m));await review.getByLabel('Survey reference basis').selectOption('SIM_ONLY');await review.getByLabel('Survey sensor height').fill('0.182');await review.getByLabel('Compare with the current edited model').check();
 await review.getByRole('button',{name:'Check survey',exact:true}).click();await expect.poll(()=>survey?.job?.job_id!==previous?survey?.job?.status:'WAIT_NEW_JOB',{timeout:60000}).toMatch(/GEOMETRIC_REVIEW|HELD|CANCELLED/);
 if(survey.job.status!=='GEOMETRIC_REVIEW')throw Error('Actual collection review held: '+JSON.stringify(survey.job));(result.reviews??=[]).push(survey);};
const show=async()=>{await review.getByRole('button',{name:'Show survey',exact:true}).click();await expect.poll(()=>frame?.alignment_overlay?.review_id,{timeout:30000}).toBe(survey.job.job_id);
 const layer=p.locator('[aria-label="Frame-bound alignment review"]');await expect(layer).toBeVisible();await expect(layer).toHaveAttribute('data-source','SAVED');
 let receipt;await expect.poll(async()=>{const c=p.locator('canvas[data-frame-id]');const dom=await c.evaluate(c=>({id:Number(c.dataset.frameId),stamp:Number(c.dataset.capturedAt),live:c.dataset.live}));receipt={frame,dom};return frame?.frame_id===dom.id&&frame?.captured_at_ms===dom.stamp&&dom.live==='true'&&Date.now()-dom.stamp<1000;}).toBe(true);result.frames.push(receipt);};
try{
 result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());await p.setViewportSize({width:1440,height:1000});finish=await recordRenderedPage(p,path.join(output,'recording'));await open();
 if(phase==='cold'){
  await step('Cold saved review has no restored session registration or visibility',async()=>{if(survey.job?.status!=='SAVED'||survey.visible||survey.registration_active)throw Error('Cold authority/visibility restored');result.cold=survey;await shot('cold-hidden');});
 }else if(phase==='restore'){
  await step('Explicit common Undo restores the original removed prop before a full repeat',async()=>{const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='undo_preview');await panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click();const r=await response,v=await r.json();if(r.status()!==200||!v.preview)throw Error('Restore Undo preview failed');await apply(v.preview);await expect(panel.getByText('Added obstacles · 1',{exact:true})).toBeVisible();await shot('restored-original-prop');});
 }else{
  if(phase==='hybrid'){
   await step('Remove the estimated prop from the model, not the original collected rays',async()=>{
    const obstacles=panel.locator('details').filter({has:p.getByText('Added obstacles · 1',{exact:true})}).first();if(!await panel.getByRole('button',{name:'Remove Photo candidate - test placement · preview',exact:true}).isVisible())await panel.getByText('Added obstacles · 1',{exact:true}).click();
    const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='remove_overlay_preview');await panel.getByRole('button',{name:'Remove Photo candidate - test placement · preview',exact:true}).click();const r=await response,v=await r.json();if(r.status()!==200||!v.preview)throw Error('No removal preview');await apply(v.preview);await shot('01-model-without-prop');
   });
  }
  await step('Original multi-position task observations checked against current source and units',check);
  await step('Saved aligned scan is visible on an actual fresh Isaac frame',async()=>{await show();await shot('02-survey-registered');});
  if(phase==='hybrid'||phase==='adopt'||phase==='reapply'){
   if(phase==='hybrid'){
   await step('Existing configured photo model recognizes candidate classes without metric coordinates',async()=>{
    if(!await panel.getByLabel('Obstacle reference photo').isVisible())await panel.getByText('Added obstacles · 0',{exact:true}).click();
    await panel.getByLabel('Obstacle reference photo').setInputFiles('C:/Users/jaewo/Downloads/KakaoTalk_20261023_001642352.jpg');await panel.getByLabel('Allow photo analysis').check();
    result.photo_claim=await reserveDevelopmentCall(allowance,'photo',{photo_name:'KakaoTalk_20261023_001642352.jpg',project_id:environment.project_id});
    const previous=environment.photo_proposal?.job_id;const accepted=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='photo_analyze');
    await panel.getByRole('button',{name:'Analyze photo',exact:true}).click();const response=await accepted,v=await response.json();if(response.status()!==200||v.photo_proposal?.job_id===previous)throw Error('New photo request ACK missing');result.photo_request={status:response.status(),job_id:v.photo_proposal?.job_id,request_id:response.request().postDataJSON().request_id};
    await expect.poll(()=>environment?.photo_proposal?.job_id!==previous?environment?.photo_proposal?.status:'WAIT_NEW_JOB',{timeout:330000}).toMatch(/ready|failed|cancelled/);if(environment.photo_proposal.status!=='ready')throw Error('Actual photo analysis failed: '+environment.photo_proposal.error);result.photo=environment.photo_proposal;await expect(review.getByLabel('Survey residual candidate')).toBeEnabled();
   });
   }else await step('Use the preserved ready photo job without another model request',async()=>{if(environment.photo_proposal?.status!=='ready')throw Error('No preserved ready photo');result.photo=environment.photo_proposal;await expect(review.getByLabel('Survey residual candidate')).toBeEnabled();});
   await step('Explicit LiDAR XY plus photo class association creates a review only',async()=>{
    const candidates=survey.review.obstacle_candidates;if(!candidates.length)throw Error('No actual multiview residual candidate');
    const candidate=[...candidates].sort((a,b)=>Math.hypot(a.position_xy_m[0]-2.35,a.position_xy_m[1]-1.15)-Math.hypot(b.position_xy_m[0]-2.35,b.position_xy_m[1]-1.15))[0];
    const photo=environment.photo_proposal.candidates.find(c=>c.kind==='basket');if(!photo)throw Error('Actual photo model did not return a basket class');
    await review.getByLabel('Survey residual candidate').selectOption(candidate.candidate_id);await review.getByLabel('Survey photo association').selectOption(photo.id);await review.getByLabel('Survey obstacle height').fill('0.4');await review.getByLabel('I reviewed the class, extent and possible duplicates').check();
    const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/survey'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='preview_obstacle');await review.getByRole('button',{name:'Preview missing obstacle',exact:true}).click();const r=await response,v=await r.json();if(r.status()!==200||!v.preview)throw Error('Residual preview failed: '+JSON.stringify(v));result.adoption_preview=v.preview;result.selected={candidate,photo};await shot('03-hybrid-preview');
   });
   await step('Common Apply binds original collection and exact candidate through ACK and saved revision',async()=>{await apply(result.adoption_preview);await shot('04-hybrid-applied');});
   if(phase!=='reapply')await step('Common Undo removes the derived overlay without changing original scan or USD',async()=>{const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/environment/action'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='undo_preview');await panel.getByRole('button',{name:'Undo last edit · preview',exact:true}).click();const r=await response,v=await r.json();if(r.status()!==200||!v.preview)throw Error('Undo preview failed');await apply(v.preview);await shot('05-hybrid-undo');});
  }
  await step('Compact English review panel has no horizontal overflow',async()=>{for(const [width,height] of [[1280,720],[1440,1000]]){await p.setViewportSize({width,height});const metrics=await panel.evaluate(e=>({client:e.clientWidth,scroll:e.scrollWidth}));if(metrics.scroll>metrics.client+1)throw Error('Horizontal panel overflow');(result.layout??=[]).push({width,height,...metrics});await shot('layout-'+width);}});
 }
 if(result.errors.length)throw Error('Renderer errors');result.status='PASS_SCOPED';
}catch(e){result.errors.push(String(e));await shot('failure').catch(()=>{});}finally{await Promise.all([...pending]);if(finish)result.recording=await finish().catch(e=>({error:String(e)}));await save();await browser.close();}
if(result.status!=='PASS_SCOPED')throw Error(result.errors.join('\n'));
