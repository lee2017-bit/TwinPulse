// SPDX-License-Identifier: Apache-2.0
// Actual installed Test BrowserWindow; read-only history/file viewing and UI Stop/Exit only.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1],has=n=>args.includes(n);
const out=arg('--output'),project=arg('--project'),expected=arg('--operation'),label=arg('--label');
if(!out||!project||!expected||!label)throw Error('Explicit output/project/operation/label required');
await fs.mkdir(out,{recursive:false});
const result={status:'IN_PROGRESS',classification:'INSTALLED_ELECTRON_READ_ONLY_DIAGNOSTICS',project,operation_id:expected,steps:[],http_errors:[],page_errors:[],mutations:[],started_at:new Date().toISOString(),physical_activation:0};
let browser,page,observedConversationContext=null;
const save=()=>fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>page.screenshot({path:path.join(out,name+'.png')});
const step=async(name,fn)=>{const began=Date.now();try{result.steps.push({name,status:'PASS',evidence:await fn(),elapsed_ms:Date.now()-began});}catch(e){result.steps.push({name,status:'FAIL',error:String(e),elapsed_ms:Date.now()-began});throw e;}finally{await save();}};
try{
 browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('Exactly one installed renderer required');[page]=pages;page.setDefaultTimeout(20000);
 result.desktop=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 if(!result.desktop?.engine?.release_id)throw Error('Installed identity missing');
 page.on('pageerror',e=>result.page_errors.push(String(e)));
 page.on('response',r=>{if(r.status()>=400)result.http_errors.push({path:new URL(r.url()).pathname,status:r.status()});});
 page.on('response',r=>{if(r.status()===200&&new URL(r.url()).pathname==='/v1/product/conversation')observedConversationContext=r.headers()['x-twinpulse-context']??null;});
 page.on('request',r=>{if(r.method()==='POST'){let body;try{body=r.postDataJSON();}catch{}result.mutations.push({path:new URL(r.url()).pathname,action:body?.action});}});
 await step('Open exact original chat and robot without connecting',async()=>{
  await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
  if(!await page.locator('.chat-sidebar-slot').isVisible())await page.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
  await page.getByRole('button',{name:'Open '+project,exact:true}).click();
  await expect(page.locator('.chat-project-caption')).toContainText(project);
  const show=page.getByRole('button',{name:'Show Twin',exact:true});if(await show.isVisible())await show.click();
  await page.locator('.robot-fleet-row').filter({hasText:label}).click();
  await expect(page.getByRole('region',{name:'Control '+label,exact:true})).toBeVisible();
 });
 const drawer=page.getByRole('region',{name:'Control '+label,exact:true});
 if(has('--stop'))await step('Visible Stop before diagnosing failed SIM attempt',async()=>{await drawer.getByRole('button',{name:'Stop',exact:true}).click();await expect(drawer).toContainText('Engine stop confirmed');});
 let operation;
 await step('Download exact operation through public UI',async()=>{
  await drawer.getByRole('button',{name:'Operation logs',exact:true}).click();
  const waiting=page.waitForEvent('download');await drawer.getByRole('button',{name:'Download operation JSON',exact:true}).click();
  const file=path.join(out,'operation.json');await(await waiting).saveAs(file);const bytes=await fs.readFile(file);operation=JSON.parse(bytes);
  if(operation.operation_id!==expected||operation.project_id!==project)throw Error('Wrong operation selected');
  await shot('01-operation');return {operation_id:operation.operation_id,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
 });
 if(has('--segment')){
  const timeline=drawer.getByLabel('Robot diagnostic timeline');
  await step('Open actual diagnostic timeline and load preserved raw segment locally',async()=>{
   if(await timeline.getAttribute('open')===null)await timeline.locator('summary').first().click();
   await timeline.getByLabel('Open recorded JSON / JSONL locally (one segment, up to 8 MiB)').setInputFiles(arg('--segment'));
   await expect(timeline.getByText('Exact segment SHA and byte count match the operation manifest',{exact:false})).toBeVisible();
   const bytes=await fs.readFile(arg('--segment'));await shot('02-segment');
   return {source:arg('--segment'),sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,transport:'DOM file selection, not OS paste; no upload'};
  });
  await step('Measured distribution, clocks, cursor and category filters are usable',async()=>{
   const measured=timeline.getByText('Measured distribution · selected evidence only',{exact:true});
   if(await measured.locator('..').getAttribute('open')===null)await measured.click();
   await expect(timeline.getByRole('columnheader',{name:'Sample SD',exact:true})).toBeVisible();
   await timeline.getByRole('button',{name:'Next recorded event',exact:true}).click();
   await timeline.getByRole('button',{name:'Previous recorded event',exact:true}).click();
   await timeline.getByRole('combobox',{name:/^Recorded category/}).selectOption('sensor');
   const stats=timeline.locator('table').filter({has:page.getByRole('columnheader',{name:'Sample SD',exact:true})});
   await stats.scrollIntoViewIfNeeded();await stats.screenshot({path:path.join(out,'03-distribution-table.png')});
   const snapshot=await timeline.innerText();await fs.writeFile(path.join(out,'timeline.txt'),snapshot);await shot('03-distribution');
   await timeline.getByRole('combobox',{name:/^Recorded category/}).selectOption('all');return {text:snapshot.slice(0,16000)};
  });
  await step('History scope and current disconnected status remain distinct',async()=>{
   for(const title of ['Saved operation and evidence scope','Current reported diagnostics']){
    const summary=timeline.getByText(title,{exact:true});if(await summary.locator('..').getAttribute('open')===null)await summary.click();
   }
   await timeline.getByText('Current reported diagnostics',{exact:true}).scrollIntoViewIfNeeded();
   await expect(drawer.getByRole('button',{name:'Connect',exact:true})).toBeEnabled();
   await expect(timeline).toContainText(expected);await shot('04-history-status');return {text:(await timeline.innerText()).slice(0,7000)};
  });
 }
 if(has('--first-read-recovery'))await step('FAULT INJECTION: first conversation timeout recovers after reload and project switch without action replay',async()=>{
  const other=arg('--recovery-project');if(!other||other===project)throw Error('Explicit different saved recovery project required');
  const records=[];let delayMode=null,oldContext=null;
  await page.route('**/v1/product/conversation',async route=>{
   const request=route.request(),context=request.headers()['x-twinpulse-context']??null;
   if(request.method()==='GET'&&delayMode&&(delayMode==='first'||context&&context!==oldContext)){
    const mode=delayMode;delayMode=null;const record={mode,context,started_at:Date.now(),delay_ms:3600};records.push(record);
    await new Promise(resolve=>setTimeout(resolve,3600));
    try{await route.continue();record.delivery='continued_after_original_deadline';}catch(e){record.delivery='original_request_aborted_before_dispatch';record.error=String(e);}
   }else await route.continue().catch(()=>{});
  });
  const mutatingBefore=result.mutations.length;
  delayMode='first';await page.reload({waitUntil:'domcontentloaded'});
  await expect(page.getByText('Local state read exceeded 3 seconds.',{exact:true}).first()).toBeVisible({timeout:10000});
  await shot('06-first-read-timeout');
  // A successfully reloaded saved conversation intentionally opens Home. Its
  // project-specific local button is the public navigation path, not a failed
  // connection or a reason to inject an internal home/context state.
  const openSaved=page.getByRole('button',{name:'Open saved chat · '+project,exact:true});
  await expect.poll(async()=>await openSaved.isVisible()||(await page.locator('.chat-project-caption').innerText()).includes(project),{timeout:12000}).toBe(true);
  if(await openSaved.isVisible())await openSaved.click();
  await expect(page.locator('.chat-project-caption')).toContainText(project,{timeout:12000});
  await expect(page.getByText('App connection available',{exact:true}).first()).toBeVisible({timeout:12000});
  if(!observedConversationContext||records.length!==1)throw Error('Reload recovery did not observe actual new conversation response');
  const reloadRecoveredAt=Date.now();await shot('07-first-read-recovered');oldContext=observedConversationContext;
  delayMode='different-context';
  if(!await page.locator('.chat-sidebar-slot').isVisible())await page.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
  await page.getByRole('button',{name:'Open '+other,exact:true}).click();
  await expect(page.getByText('Local state read exceeded 3 seconds.',{exact:true}).first()).toBeVisible({timeout:10000});
  await shot('08-switch-first-read-timeout');
  await expect(page.locator('.chat-project-caption')).toContainText(other,{timeout:12000});
  await expect(page.getByText('App connection available',{exact:true}).first()).toBeVisible({timeout:12000});
  if(records.length!==2||!records[1].context||records[1].context===oldContext||observedConversationContext!==records[1].context)throw Error('Selected context recovery evidence missing');
  const switchRecoveredAt=Date.now();await shot('09-switch-first-read-recovered');
  await page.getByRole('button',{name:'Open '+project,exact:true}).click();
  await expect(page.locator('.chat-project-caption')).toContainText(project,{timeout:12000});
  await expect(page.getByText('App connection available',{exact:true}).first()).toBeVisible({timeout:12000});
  const mutations=result.mutations.slice(mutatingBefore);
  if(mutations.some(r=>!['/v1/product/session','/v1/product/projects/switch'].includes(r.path))||mutations.filter(r=>r.path==='/v1/product/projects/switch').length!==2)throw Error('Read recovery replayed an action');
  return {records,reload_recovered_at:reloadRecoveredAt,switch_recovered_at:switchRecoveredAt,mutations,physical_activation:0,
   scope:'Real GET delivery delay only; original3s deadline retained. Authentication and two explicit sidebar switches allowed. No model, drive or automatic mutation. Route remains until normal App close; not un-intercepted driving evidence.'};
 });
 if(has('--native-close-advisory'))await step('FAULT INJECTION: unavailable advisory cannot veto explicit native Close; real server admission and ACK',async()=>{
  let altered=0,shutdowns=0,accepted=0;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/v1/product/runtime/shutdown')shutdowns++;});
  page.on('response',r=>{if(r.request().method()==='POST'&&new URL(r.url()).pathname==='/v1/product/runtime/shutdown'&&r.status()===202)accepted++;});
  await page.route('**/v1/product/runtime',async route=>{
   if(route.request().method()!=='GET')return route.continue();
   const response=await route.fetch();const real=await response.json();
   if(real.status!=='ready'||real.shutdown_requested===true)throw Error('Real runtime is not idle-ready for advisory-only fault');
   altered++;await route.fulfill({response,json:{...real,shutdown_available:false}});
  });
  await expect.poll(()=>altered,{timeout:10000}).toBeGreaterThan(0);
  await expect(page.getByRole('button',{name:'Exit TwinPulse',exact:true})).toBeDisabled({timeout:10000});
  await shot('05-native-close-advisory');
  const closing=page.waitForEvent('close',{timeout:90000});
  await fs.writeFile(path.join(out,'awaiting-native-close.json'),JSON.stringify({classification:'EXPLICIT_ADVISORY_ONLY_FAULT_NOT_NORMAL_FLOW',launch:result.desktop.engine.launch_id,shutdowns_before_native_input:shutdowns,altered}));
  console.log('AWAITING_ACTUAL_NATIVE_CLOSE');await closing;
  if(shutdowns!==1||accepted!==1)throw Error('Native close did not use exactly one real202 shutdown admission');
  return {altered_advisory_reads:altered,shutdown_post_count:shutdowns,real202:accepted,input:'Actual native AltF4 separately recorded; not programmatic BrowserWindow.close'};
 });
 else await step('Exit through installed public App button',async()=>{const closing=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;});
 if(result.mutations.some(r=>r.path==='/v1/product/robot-fleet'&&!['focus','stop'].includes(r.action)))throw Error('Unexpected robot action');
 if(result.http_errors.length||result.page_errors.length)throw Error('HTTP/page error');result.status='PASS';
}catch(e){result.status='FAIL';result.error=String(e);if(page&&!page.isClosed())await shot('failure').catch(()=>{});}
finally{result.finished_at=new Date().toISOString();await save();if(browser)await browser.close();}
console.log(JSON.stringify({status:result.status,steps:result.steps.map(s=>({name:s.name,status:s.status})),error:result.error}));
if(result.status!=='PASS')process.exitCode=1;
