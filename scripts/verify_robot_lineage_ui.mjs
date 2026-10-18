// SPDX-License-Identifier: Apache-2.0
// Actual installed Electron BrowserWindow. No product mutation API, seed,
// fixed model output or separate Chrome. Saved-scene traceability, not generation.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const args=process.argv.slice(2),arg=n=>{const index=args.indexOf(n);return index<0?undefined:args[index+1];};
const endpoint=arg('--cdp'),out=arg('--output'),project=arg('--project'),phase=arg('--phase')??'run';
if(!out||!project||!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint))throw Error('Explicit cdp/output/project required');
await fs.mkdir(out,{recursive:false});
const result={phase,status:'IN_PROGRESS',started_at:new Date().toISOString(),classification:'INSTALLED_ELECTRON_ISAAC_SAVED_SCENE_TRACEABILITY',
 project,steps:[],screenshots:[],http_errors:[],page_errors:[],request_failed:[],posts:[],physical:'NOT_RUN_OFF',provider_calls:0,
 native_input:'NOT_RUN_TEST_BROWSERWINDOW',fresh_generation:'NOT_RUN_NOT_REQUIRED_FOR_ID_LINKAGE'};
let browser,page,fleet,conversation,site,initialScene;const fleets=new Map();
const hash=v=>createHash('sha256').update(typeof v==='string'?v:JSON.stringify(v)).digest('hex');
const clean=e=>String(e).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]').slice(0,1600);
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(test,timeout=30000)=>{const end=Date.now()+timeout;while(Date.now()<end){if(test())return;await sleep(100);}throw Error('Observed state timeout');};
const shot=async(name)=>{await page.screenshot({path:path.join(out,name+'.png'),timeout:8000});result.screenshots.push(name+'.png');};
const step=async(name,fn)=>{const start=Date.now();try{const evidence=await fn();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-start,evidence});}
 catch(error){result.steps.push({name,status:'FAIL',elapsed_ms:Date.now()-start,error:clean(error)});await shot('failure-'+result.steps.length).catch(()=>{});throw error;}finally{await save();}};
const label=arg('--label')??'Lineage Alpha';
const robot=()=>fleet?.robots.find(r=>r.label===label);
const drawer=(targetLabel=label)=>page.getByRole('region',{name:'Control '+targetLabel,exact:true});
const openLinkage=async()=>{const panel=drawer().getByLabel('Robot Twin record linkage');
 if(await panel.getAttribute('open')===null)await panel.locator('summary').click();
 await expect(panel).toHaveAttribute('open','');await expect(panel.locator('dl')).toBeVisible();return panel;};
const select=async(targetLabel=label)=>{const open=page.getByRole('button',{name:/^Open saved chat ·/}),message=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
 // Advanced Return can retire the old chat asynchronously. Explicitly select
 // the sidebar conversation rather than racing the disappearing old form.
 await page.getByRole('button',{name:'Open '+project,exact:true}).click();await expect(message).toBeVisible();
 await expect(page.locator('.chat-project-caption')).toContainText(project);
 const show=page.getByRole('button',{name:'Show Twin',exact:true});if(await show.isVisible())await show.click();
 await page.locator('.robot-fleet-row').filter({hasText:targetLabel}).click();await expect(drawer(targetLabel)).toBeVisible();};
const download=async(name,targetLabel=label)=>{
 await drawer(targetLabel).getByRole('button',{name:'Operation logs',exact:true}).click();
 const button=drawer(targetLabel).getByRole('button',{name:'Download operation JSON',exact:true});await expect(button).toBeVisible({timeout:25000});
 const pending=page.waitForEvent('download');await button.click();await (await pending).saveAs(path.join(out,name));
 return JSON.parse(await fs.readFile(path.join(out,name),'utf8'));
};
try{
 browser=await chromium.connectOverCDP(endpoint);const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('Exactly one installed renderer required');[page]=pages;page.setDefaultTimeout(15000);
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 if(!result.desktop?.engine?.launch_id||!(await page.evaluate(()=>navigator.userAgent)).includes('Electron/'))throw Error('Not installed Electron');
 page.on('pageerror',e=>result.page_errors.push(clean(e)));
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.startsWith('/v1/product/')){
  let v;try{v=r.postDataJSON();}catch{}result.posts.push({path:new URL(r.url()).pathname,action:v?.action,request_id:v?.request_id});}});
 page.on('requestfailed',r=>result.request_failed.push({path:new URL(r.url()).pathname,method:r.method(),reason:clean(r.failure()?.errorText)}));
 page.on('response',async r=>{const p=new URL(r.url()).pathname;
  if(r.status()>=400){const row={path:p,status:r.status(),method:r.request().method()};
   try{const v=await r.json();row.error={code:v.error?.code,message:clean(v.error?.message)};}catch{}result.http_errors.push(row);}
  if(r.status()!==200)return;
  try{
   const context=r.headers()['x-twinpulse-context']??'';
   if(p==='/v1/product/robot-fleet'){const v=await r.json(),before=fleets.get(context);if(!before||v.revision>=before.revision)fleets.set(context,v);
    if(context===conversation?.context_id)fleet=fleets.get(context);}
   if(p==='/v1/product/conversation'){const v=await r.json();conversation={project_id:v.project_id,session_id:v.session_id,context_id:context};fleet=fleets.get(context);}
   if(p==='/v1/product/workflow'){const v=await r.json();site=v.site_draft;}
  }catch{}
 });
 await step('Actual installed startup and saved chat open',async()=>{
  const returnChat=page.getByRole('button',{name:'← Return to chat',exact:true});if(await returnChat.isVisible())await returnChat.click();
  await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:180000});
  await page.getByRole('button',{name:'Open '+project,exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Message TwinPulse',exact:true})).toBeVisible();
  await poll(()=>conversation?.project_id===project&&!!site?.objects);initialScene=structuredClone(site);
  await fs.writeFile(path.join(out,'initial-scene.json'),JSON.stringify(initialScene,null,2));
  result.conversation=conversation;await shot('01-chat');return conversation;
 });
 if(phase==='verify-switched-history'){
  await step('Project switch finalized prior SIM operation and kept event prefix/context without authority',async()=>{
   await poll(()=>!!robot());await select();const record=await download('closed-operation.json'),prior=JSON.parse(await fs.readFile(arg('--prior'),'utf8'));
   if(record.operation_id!==arg('--operation')||!record.manifest.complete||robot().operation_id||
      hash(record.events.slice(0,prior.events.length))!==hash(prior.events)||hash(record.manifest.source_twin_context)!==hash(prior.manifest.source_twin_context))throw Error('Switch history or authority differs');
   await shot('switched-history');result.operation_id=record.operation_id;return {operation_id:record.operation_id,end_reason:record.manifest.end_reason,event_sha256:hash(record.events),source_context:record.manifest.source_twin_context};
  });
  if(arg('--old-label'))await step('Large historical operation actual UI download',async()=>{
   await select(arg('--old-label'));const record=await download('large-historical-operation.json',arg('--old-label'));
   const before=JSON.parse(await fs.readFile(arg('--old-prior'),'utf8'));
   if(record.operation_id!==before.operation_id||!record.manifest.complete||hash(record.events.slice(0,before.events.length))!==hash(before.events))throw Error('Old history changed');
   await shot('large-history');return {operation_id:record.operation_id,bytes:(await fs.stat(path.join(out,'large-historical-operation.json'))).size};
  });
 }else if(phase==='cold'){
  await step('Cold history does not restore authority and retains exact Twin reference',async()=>{
   await poll(()=>!!robot());if(robot().operation_id||robot().connection_state!=='DISCONNECTED')throw Error('Restored authority');
   await select();const record=await download('cold-operation.json');
   if(record.operation_id!==arg('--operation'))throw Error('Wrong operation');
   const prior=JSON.parse(await fs.readFile(arg('--prior'),'utf8'));
   if(hash(record.events)!==hash(prior.events)||hash(record.manifest.source_twin_context)!==hash(prior.manifest.source_twin_context))throw Error('Historical bytes or reference changed');
   await openLinkage();
   await expect(drawer().getByLabel('Robot Twin record linkage').getByText(record.manifest.source_twin_context.scene_revision,{exact:true})).toBeVisible();
   await shot('cold-lineage');return {operation_id:record.operation_id,event_sha256:hash(record.events),source_context:record.manifest.source_twin_context};
  });
 }else{
 if(['resume-edit','resume-edit-unbuilt','finish-history','resume-motion-failure','resume-completed-motion'].includes(phase)){
  if(['resume-motion-failure','resume-completed-motion'].includes(phase)){
   result.operation_id=arg('--operation');await select();
   await step(phase==='resume-completed-motion'?'Completed short command retains exact request/result Twin identity; NOT 90-degree PASS':'Failed finite command retains exact request/result Twin identity; NOT motion PASS',async()=>{
    const failure=await download('failed-motion-operation.json'),command=failure.events.find(e=>e.kind==='command_accepted'),
     completion=failure.events.find(e=>e.kind==='motion_result'&&e.command_id===command?.command_id);
    if(!command||!completion||completion.request_twin_context.context_id!==command.twin_context.context_id||
       (phase==='resume-motion-failure'?completion.reason==='TASK_COMPLETED':completion.reason!=='TASK_COMPLETED'))throw Error('Expected preserved command/result join missing');
    result.motion_result=completion.reason;return {reason:completion.reason,command_id:command.command_id,request_twin_context:completion.request_twin_context};
   });
   await step('Actual LiDAR and readable Twin linkage after failed command',async()=>{
    await drawer().getByRole('button',{name:'Prepare',exact:true}).click();
    const on=drawer().getByRole('button',{name:'LiDAR On',exact:true});if(await on.isVisible())await on.click();await poll(()=>robot()?.scan?.points.length>0,30000);
    // Public scan readiness can precede the bounded 0.5s journal cadence.
    await sleep(800);
    const record=await download('initial-operation.json'),source=record.manifest.source_twin_context,
     scan=record.events.find(e=>e.kind==='engine_observation'&&e.scan?.points.length);
    if(!scan||source.project_id!==project||source.conversation_session_id!==conversation.session_id||scan.scan.twin_context.scene_revision!==source.scene_revision)throw Error('Scan/source join missing');
    const linkage=await openLinkage();await linkage.scrollIntoViewIfNeeded();
    const layout=await linkage.locator('dl').evaluate(e=>({display:getComputedStyle(e).display,valueWidths:[...e.querySelectorAll('dd')].map(d=>d.getBoundingClientRect().width)}));
    if(layout.display!=='block'||layout.valueWidths.some(w=>w<100))throw Error('Unreadable actual linkage layout');
    result.lineage_layout=layout;await linkage.screenshot({path:path.join(out,'03-linkage-panel.png')});result.screenshots.push('03-linkage-panel.png');await shot('03-linked-ids');
    await drawer().getByRole('button',{name:'LiDAR Off',exact:true}).click();await page.getByRole('button',{name:'Stop all',exact:true}).click();
    await drawer().getByRole('button',{name:'Close robot controls',exact:true}).click();
    return {source,stream_id:scan.scan.stream_id,frame_sequence:scan.scan.frame_sequence};
   });
  }else{
  const original=await fs.readFile(arg('--prior'),'utf8');await fs.writeFile(path.join(out,'initial-operation.json'),original);
  result.operation_id=arg('--operation');await select();
  if(arg('--scene-before'))initialScene=JSON.parse(await fs.readFile(arg('--scene-before'),'utf8'));
  }
 }else{
  await step('Explicit saved Twin display in current Isaac',async()=>{
   const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
   const showTwin=page.getByRole('button',{name:'Show Twin',exact:true});if(await showTwin.isVisible())await showTwin.click();
   await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
   await page.getByRole('button',{name:'View current Twin',exact:true}).click();
   await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
   initialScene=structuredClone(site);await fs.writeFile(path.join(out,'initial-scene.json'),JSON.stringify(initialScene,null,2));
   await shot('02-saved-twin');return {basis:'Saved real Twin displayed, not fresh generation'};
  });
  await step('Register and explicitly connect a new SIM operation',async()=>{
   await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();await page.getByText('Add SIM robot',{exact:true}).click();
   await page.getByRole('textbox',{name:'Name',exact:true}).fill(label);
   await page.getByRole('spinbutton',{name:'X (m)',exact:true}).fill('0');await page.getByRole('spinbutton',{name:'Y (m)',exact:true}).fill('0');
   await page.getByRole('button',{name:'Add SIM robot',exact:true}).click();await poll(()=>!!robot());
   await page.getByRole('button',{name:'Manage robot fleet',exact:true}).click();await select();
   await drawer().getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot()?.connection_state==='CONNECTED');
   await drawer().getByRole('button',{name:'Prepare',exact:true}).click();
   result.operation_id=robot().operation_id;result.robot_id=robot().robot_id;return {operation_id:result.operation_id,source_context:robot().source_twin_context};
  });
  await step('Actual finite command and LiDAR observation link to chat and exact scene',async()=>{
   const requestedCommand=arg('--command')??'left 90 degrees';result.requested_command=requestedCommand;
   const input=drawer().getByRole('textbox',{name:'Robot command',exact:true});await input.fill(requestedCommand);
   await drawer().getByRole('button',{name:'Send command',exact:true}).click();await poll(()=>robot()?.reason==='TASK_COMPLETED',30000);
   const lidar=drawer().getByRole('button',{name:'LiDAR On',exact:true});await lidar.click();await poll(()=>robot()?.scan?.points.length>0);
   await sleep(800);const record=await download('initial-operation.json'),source=record.manifest.source_twin_context;
   if(source.project_id!==project||source.conversation_session_id!==conversation.session_id||!source.scene_revision)throw Error('Missing conversation/Twin link');
   const command=record.events.find(e=>e.kind==='command_accepted'),completion=record.events.find(e=>e.kind==='motion_result'&&e.command_id===command?.command_id),scan=record.events.find(e=>e.kind==='engine_observation'&&e.scan?.points.length);
   if(!command||!completion||!scan||completion.request_twin_context.context_id!==command.twin_context.context_id||scan.scan.twin_context.scene_revision!==source.scene_revision)throw Error('Command/result/scan context join missing');
   const linkage=await openLinkage();await linkage.scrollIntoViewIfNeeded();
   const layout=await linkage.locator('dl').evaluate(e=>({display:getComputedStyle(e).display,width:e.getBoundingClientRect().width,
     valueWidths:[...e.querySelectorAll('dd')].map(d=>d.getBoundingClientRect().width)}));
   if(layout.display!=='block'||layout.valueWidths.some(w=>w<100))throw Error('Linkage IDs unreadable in actual layout');
   result.lineage_layout=layout;await linkage.screenshot({path:path.join(out,'03-linkage-panel.png')});result.screenshots.push('03-linkage-panel.png');
   await shot('03-linked-ids');
   await drawer().getByRole('button',{name:'LiDAR Off',exact:true}).click();await poll(()=>robot()?.lidar_state==='OFF');
   result.initial_events_sha256=hash(record.events);return {source,command_id:command.command_id,frame_sequence:scan.scan.frame_sequence,stream_id:scan.scan.stream_id};
  });
  await step('Stop all retains original request identity in operation',async()=>{
   await page.getByRole('button',{name:'Stop all',exact:true}).click();await poll(()=>robot()?.control_state==='PAUSED');
   const record=await download('stop-operation.json');
   if(!record.events.some(e=>e.kind==='stop_all_request'&&e.request_id))throw Error('Stop all identity missing');
   await drawer().getByRole('button',{name:'Close robot controls',exact:true}).click();return {operation_id:record.operation_id};
  });
 }
  if(phase==='finish-history'){
   await step('Previously saved and UI-built Undo retains all historical revisions',async()=>{
    const record=await download('undo-operation.json'),initial=JSON.parse(await fs.readFile(path.join(out,'initial-operation.json'),'utf8'));
    if(robot().current_twin_context.scene_revision!==arg('--undo-revision')||
       hash(record.events.slice(0,initial.events.length))!==hash(initial.events))throw Error('Undo context or history changed');
    const revisions=[...new Set(record.events.filter(e=>e.kind==='engine_observation').map(e=>e.twin_context.scene_revision))];
    if(revisions.length<3||!revisions.includes(arg('--undo-revision')))throw Error('Original/change/Undo observations missing');
    await openLinkage();await shot('undo-context');
    await drawer().getByRole('button',{name:'Close robot controls',exact:true}).click();return {revisions,original_events_sha256:hash(initial.events)};
   });
  }else await step('Actual reviewed scene change and Undo preserve per-event revisions',async()=>{
   const initial=JSON.parse(await fs.readFile(path.join(out,'initial-operation.json'),'utf8')),original=initial.manifest.source_twin_context;
   const enter=async()=>{
    await page.getByRole('button',{name:'Manage projects',exact:true}).click();await page.getByRole('button',{name:'Advanced tools',exact:true}).click();
    await page.getByRole('button',{name:/Review Twin/}).click();await expect(page.getByRole('heading',{name:'Scene edits · local review',exact:true})).toBeVisible();
   };
   const build=async()=>{
    await poll(()=>!!site?.revision);
    await expect(page.locator('.scene-edit-review')).toContainText('current '+site.revision.slice(0,10));
    const ack=page.getByRole('checkbox',{name:'I reviewed the limits of this draft version.',exact:true});
    if(!await ack.isChecked()){await expect(ack).toBeEnabled();await ack.click();await expect(ack).toBeChecked();}
    const acquire=page.getByRole('button',{name:'Acquire scene control',exact:true});if(await acquire.isVisible())await acquire.click();
    await page.getByRole('button',{name:'Build scene geometry in Isaac',exact:true}).click();
    await expect(page.getByText('Scene geometry built. Navigation remains unavailable until robot, map and mission validation.',{exact:true})).toBeVisible({timeout:60000});
    await page.getByRole('button',{name:'← Return to chat',exact:true}).click();await select();
   };
   if(phase==='resume-edit-unbuilt'){
    await enter();await poll(()=>site?.revision===arg('--change-revision'));
    if(!site.objects.some(o=>o.id==='lineage_revision_probe'))throw Error('Known saved test change not present');await build();
   }else if(phase!=='resume-edit'){
   await enter();await page.getByRole('radio',{name:'Add box',exact:true}).check();
   await page.getByRole('textbox',{name:'Object ID',exact:true}).fill('lineage_revision_probe');
   const edit=page.locator('.scene-edit-review');
   for(const [name,value] of [['X (m)','0.5'],['Y (m)','0'],['Length (m)','0.1'],['Width (m)','0.1'],['Height (m)','0.1']])
     await edit.getByRole('spinbutton',{name,exact:true}).fill(value);
   const beforeRevision=site.revision;
   await edit.getByRole('button',{name:'Preview change',exact:true}).click();await edit.getByRole('button',{name:'Save reviewed change',exact:true}).click();
   await poll(()=>site?.revision!==beforeRevision&&site.objects.some(o=>o.id==='lineage_revision_probe'));
   await build();}
   await poll(()=>robot()?.current_twin_context?.scene_revision!==original.scene_revision);
   await sleep(1200);const changed=await download('changed-operation.json');
   const changedRevision=robot().current_twin_context.scene_revision;
   if(changed.manifest.source_twin_context.context_id!==original.context_id||!changed.events.some(e=>e.kind==='engine_observation'&&e.twin_context?.scene_revision===changedRevision))throw Error('Changed scene history reference missing');
   await openLinkage();await shot('changed-twin-context');
   await drawer().getByRole('button',{name:'Close robot controls',exact:true}).click();
   await enter();await poll(()=>!!site?.revision);
   // Resume a failed test without undoing someone else's previous edit. The
   // previous attempt may already have saved the desired Undo before Build.
   if(phase==='resume-edit'&&arg('--undo-revision')){
    if(site.revision!==arg('--undo-revision')||site.original_scene_revision!==original.scene_revision||
       site.objects.some(o=>o.id==='lineage_revision_probe'))throw Error('Previously saved Undo reference differs; no change sent');
   }else{
    if(site.revision!==changedRevision||!site.objects.some(o=>o.id==='lineage_revision_probe'))throw Error('Saved scene differs from this test change; no Undo sent');
    await page.getByRole('radio',{name:'Undo last edit',exact:true}).check();
    await page.locator('.scene-edit-review').getByRole('button',{name:'Preview change',exact:true}).click();
    await page.locator('.scene-edit-review').getByRole('button',{name:'Save reviewed change',exact:true}).click();
   }
   await poll(()=>site?.revision!==changedRevision&&!site.objects.some(o=>o.id==='lineage_revision_probe'));
   const undoScene=structuredClone(site),undoRevision=undoScene.revision;
   // Undo is a new immutable revision, not the original hash. Compare geometry
   // separately rather than discarding the real Undo lineage to force equality.
   if((phase!=='resume-edit'||arg('--scene-before'))&&hash(undoScene.objects)!==hash(initialScene.objects))throw Error('Undo geometry differs from pre-edit scene');
   await fs.writeFile(path.join(out,'undo-scene.json'),JSON.stringify(undoScene,null,2));
   await build();await poll(()=>robot()?.current_twin_context?.scene_revision===undoRevision);await sleep(800);
   const undone=await download('undo-operation.json');
   if(hash(undone.events.slice(0,initial.events.length))!==hash(initial.events))throw Error('Historical events mutated by Undo');
   await shot('undo-context');await drawer().getByRole('button',{name:'Close robot controls',exact:true}).click();
   return {original:original.scene_revision,changed:changedRevision,restored_geometry_new_revision:robot().current_twin_context.scene_revision,
    geometry_comparison:phase==='resume-edit'?'PREVIOUS_SAVED_UNDO_ID_AND_PROBE_ABSENCE':'EXACT_PRE_EDIT_OBJECTS_SHA',original_events_sha256:hash(initial.events)};
  });
  await step('Project switch closes old operation without relabelling old events',async()=>{
   await page.getByRole('button',{name:'＋ New chat',exact:true}).click();
   await poll(()=>conversation&&conversation.project_id!==project);result.switched_project=conversation.project_id;
   await page.getByRole('button',{name:'Open '+project,exact:true}).click();await poll(()=>conversation?.project_id===project);await poll(()=>!!robot());
   await select();const record=await download('closed-operation.json'),initial=JSON.parse(await fs.readFile(path.join(out,'initial-operation.json'),'utf8'));
   if(record.operation_id!==result.operation_id||!record.manifest.complete||hash(record.events.slice(0,initial.events.length))!==hash(initial.events))throw Error('Old context mutated or not finalized');
   if(record.manifest.source_twin_context.conversation_session_id!==result.conversation.session_id||robot().operation_id)throw Error('Reference changed or authority restored');
   await shot('04-history');result.closed_event_sha256=hash(record.events);return {operation_id:record.operation_id,event_sha256:hash(record.events)};
  });
  if(arg('--old-label'))await step('Previously timed-out large historical record opens without reconnect',async()=>{
   const before=JSON.parse(await fs.readFile(arg('--old-prior'),'utf8'));await select(arg('--old-label'));
   const record=await download('large-historical-operation.json',arg('--old-label'));
   if(record.operation_id!==before.operation_id||!record.manifest.complete||hash(record.events.slice(0,before.events.length))!==hash(before.events))throw Error('Historical record changed');
   await shot('05-large-history');return {operation_id:record.operation_id,bytes:(await fs.stat(path.join(out,'large-historical-operation.json'))).size,event_count:record.events.length};
  });
 }
 await step('Exit through installed App button',async()=>{const closing=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;});
 if(result.http_errors.length||result.page_errors.length)throw Error('HTTP/page errors recorded');
 result.status='PASS';
}catch(error){result.status='FAIL';result.error=clean(error);}
finally{await save();if(browser)await browser.close();}
console.log(JSON.stringify({status:result.status,steps:result.steps.map(s=>({name:s.name,status:s.status})),operation_id:result.operation_id,error:result.error}));
if(result.status!=='PASS')process.exitCode=1;
