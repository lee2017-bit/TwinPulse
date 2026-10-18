// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_FLOW_OUTPUT,base=process.env.TWINPULSE_FLOW_URL;
const cases=JSON.parse(process.env.TWINPULSE_FLOW_CASES);
const result={status:'FAIL',cases:[],switches:[],page_errors:[],checks:[],responses:'actual provider HTTP'};
result.switch_responses=[];
let browser,page,contextId;
const checkpoint=()=>fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));
try{
  browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  page.on('pageerror',e=>result.page_errors.push(e.message));
  page.on('response',async response=>{
    if(new URL(response.url()).pathname==='/v1/product/projects/switch'){
      try{result.switch_responses.push({status:response.status(),body:await response.json()});checkpoint();}catch{}
    }
  });
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_FLOW_BOOTSTRAP)}`);
  if(process.env.TWINPULSE_FLOW_SAVED!=='1'&&process.env.TWINPULSE_FLOW_USER_DEFAULT!=='1')await expect(page.getByRole('heading',{name:'Build your Digital Twin'})).toBeVisible({timeout:20000});
  const session=()=>page.evaluate(async()=>{const r=await fetch('/v1/product/session');if(!r.ok)throw new Error('session '+r.status);return r.json();});
  contextId=(await session()).context_id;
  const read=endpoint=>page.evaluate(async({endpoint,contextId})=>{
    const response=await fetch(endpoint,{headers:{'X-TwinPulse-Context':contextId}});
    if(!response.ok)throw new Error(endpoint+' '+response.status);return response.json();
  },{endpoint,contextId});
  if(process.env.TWINPULSE_FLOW_USER_DEFAULT==='1'){
    await expect(page.getByRole('button',{name:'＋ Start a new chat',exact:true})).toBeVisible({timeout:20000});
    result.default_device_before=(await session()).device;
    const click=page.getByRole('button',{name:'＋ Start a new chat',exact:true});
    await page.screenshot({path:path.join(output,'default-startup.png')});
    await click.click();
    await expect.poll(async()=>(await session()).project_id,{timeout:30000}).not.toBe('default');
    contextId=(await session()).context_id;
    result.default_device_after=(await session()).device;
    expect(result.default_device_before.active).toBe(false);
    expect(result.default_device_before.historical_collection_status).toBe('REMOTE_STATE_UNKNOWN');
    expect(result.default_device_after.historical_collection_status).toBe('REMOTE_STATE_UNKNOWN');
    await page.screenshot({path:path.join(output,'new-chat-from-default.png')});
    result.checks.push('Actual user default/history → Start a new chat while historical readiness remains UNKNOWN');checkpoint();
    await page.getByRole('button',{name:'Readiness · Engine connected',exact:true}).click();
    await page.getByText('Connection log storage',{exact:true}).click();
    const retained=await read('/v1/product/robot/diagnostic-retention');
    await page.getByLabel('Connection log retention days',{exact:true}).fill('1');
    await page.getByRole('button',{name:'Archive older connection logs',exact:true}).click();
    await expect(page.getByText(/^Archived \d+ finished logs\. Current device state is unchanged\.$/)).toBeVisible();
    expect((await session()).device.historical_collection_status).toBe('REMOTE_STATE_UNKNOWN');
    result.retention={before:retained,after:await read('/v1/product/robot/diagnostic-retention')};
    await page.screenshot({path:path.join(output,'connection-log-storage.png')});
    await page.getByRole('button',{name:'Readiness · Engine connected',exact:true}).click();
  }
  const newChat=async()=>{
    const before=await session();await page.getByRole('button',{name:'＋ New chat',exact:true}).click();
    await expect.poll(async()=>{const s=await session();if(s.project_switch)return before.context_id;return s.context_id;},{timeout:30000}).not.toBe(before.context_id);
    const after=await session();contextId=after.context_id;
    expect(page.url().split('/#')[0]).toBe(base+'/');
    await expect(page.getByRole('heading',{name:'Build your Digital Twin'})).toBeVisible({timeout:10000});
    result.switches.push({from:before.project_id,to:after.project_id,context_id:contextId,url:page.url().split('#')[0]});
    checkpoint();return after.project_id;
  };
  if(process.env.TWINPULSE_FLOW_FEEDBACK==='1'){
    const item={id:'feedback-01',status:'FAIL',screens:[],type:'actual planner feedback, not a fresh generation'};
    result.cases.push(item);const opened=page.getByRole('button',{name:/^Open saved chat · /});
    await expect(opened).toBeVisible({timeout:20000});await opened.click();
    await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
    await page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/}).click();
    await expect.poll(async()=>!!(await read('/v1/product/viewport')).frame,{timeout:45000}).toBe(true);
    const original=await read('/v1/product/workflow');item.original_revision=original.site_draft.revision;
    const desk=original.site_draft.editable_calls.find(c=>c.arguments?.kind==='desk')?.arguments?.id;
    if(!desk)throw new Error('Saved real scene has no desk to test feedback');
    const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
    const propose=async()=>{
      await input.fill(`Move ${desk} 0.20 metres to the left. Keep all other objects unchanged.`);
      await page.getByRole('button',{name:'Send',exact:true}).click();
      await expect.poll(async()=>{const c=await read('/v1/product/conversation');item.feedback=c.scene_feedback;
        return c.scene_feedback?.state;},{timeout:310000}).toBe('preview');
      const c=await read('/v1/product/conversation'),card=c.cards.find(c=>c.state==='waiting'&&c.kind==='scene_edit');
      expect(card).toBeTruthy();item.operation_id=item.feedback.operation_id;item.execution_id=item.feedback.execution_id;
      const message=c.messages.find(m=>m.message_id===card.message_id);
      expect(message.reply_to).toBe(item.feedback.origin_message_id);
      return page.getByRole('region',{name:card.question,exact:true});
    };
    const select=async(region,label)=>{await region.getByRole('radio',{name:label,exact:true}).check();await region.getByRole('button',{name:'Continue',exact:true}).click();};
    const first=await propose();await select(first,'Cancel');
    expect((await read('/v1/product/workflow')).site_draft.revision).toBe(item.original_revision);
    const second=await propose();await select(second,'Apply and update Twin');
    await expect.poll(async()=>{const c=await read('/v1/product/conversation');item.transaction=c.scene_edit_transaction;
      return c.scene_edit_transaction?.state==='COMMITTED'&&c.scene_edit_transaction.current_frame;},{timeout:60000}).toBe(true);
    const edited=await read('/v1/product/workflow');expect(edited.site_draft.revision).not.toBe(item.original_revision);
    item.edited_revision=edited.site_draft.revision;await page.screenshot({path:path.join(output,'feedback-applied.png')});item.screens.push('feedback-applied.png');
    await page.getByRole('button',{name:'Undo last edit · preview',exact:true}).click();
    const c=await read('/v1/product/conversation'),card=c.cards.find(c=>c.state==='waiting'&&c.kind==='scene_edit');
    await select(page.getByRole('region',{name:card.question,exact:true}),'Apply and update Twin');
    await expect.poll(async()=>{const c=await read('/v1/product/conversation');item.undo=c.scene_edit_transaction;
      return c.scene_edit_transaction?.state==='COMMITTED'&&c.scene_edit_transaction.current_frame;},{timeout:60000}).toBe(true);
    item.workflow=await read('/v1/product/workflow');item.saved_revision=item.workflow.site_draft.revision;
    expect(item.saved_revision).not.toBe(item.edited_revision);
    await page.reload();contextId=(await session()).context_id;
    expect((await read('/v1/product/workflow')).site_draft.revision).toBe(item.saved_revision);
    await page.screenshot({path:path.join(output,'feedback-undo-reload.png')});item.screens.push('feedback-undo-reload.png');
    item.status='PASS';item.checks=['Actual planner feedback without money approval','Cancel preserves original scene','Apply current frame and save','Offline Undo and reload'];checkpoint();
  }else if(process.env.TWINPULSE_FLOW_SMOKE==='1'){
    const savedProject=(await session()).project_id;
    const reopenSaved=async()=>{
      const openSaved=page.getByRole('button',{name:/^Open saved chat · /});
      const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});
      await expect.poll(async()=>!!(await openSaved.count()||await reopen.count()),{timeout:20000}).toBe(true);
      if(await openSaved.count())await openSaved.click();
      await reopen.click();
      const view=page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/});
      await expect(view).toBeEnabled();await view.click();
      await expect.poll(async()=>!!(await read('/v1/product/viewport')).frame,{timeout:45000}).toBe(true);
      const restored=await read('/v1/product/workflow');
      result.reopened_scene={revision:restored.site_draft.revision,scene_state_sha256:restored.site_draft.scene_state_sha256};
      if(process.env.TWINPULSE_FLOW_EXPECTED_REVISION)expect(restored.site_draft.revision).toBe(process.env.TWINPULSE_FLOW_EXPECTED_REVISION);
      if(process.env.TWINPULSE_FLOW_EXPECTED_STATE)expect(restored.site_draft.scene_state_sha256).toBe(process.env.TWINPULSE_FLOW_EXPECTED_STATE);
    };
    if(process.env.TWINPULSE_FLOW_SAVED==='1'){
      const openSaved=page.getByRole('button',{name:/^Open saved chat · /});
      await expect(openSaved).toBeVisible({timeout:20000});await openSaved.click();
      await expect(page.getByRole('textbox',{name:'Message TwinPulse',exact:true})).toBeVisible();
      result.saved_startup={workflow:await read('/v1/product/workflow'),conversation:await read('/v1/product/conversation'),
        product:await read('/v1/product/state'),buttons:await page.getByRole('button').allTextContents()};
      await page.screenshot({path:path.join(output,'saved-startup.png')});checkpoint();
      await page.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
      await expect(page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/})).toBeEnabled();
      await page.getByRole('button',{name:/^View (draft in Isaac|current Twin(?: in Isaac)?)$/}).click();
      await expect.poll(async()=>!!(await read('/v1/product/viewport')).frame,{timeout:45000}).toBe(true);
      await page.screenshot({path:path.join(output,'saved-actual.png')});
    }
    for(let i=0;i<3;i++){
      await newChat();
      if(process.env.TWINPULSE_FLOW_USER_DEFAULT==='1'){
        const staleContext=contextId;
        await page.getByRole('button',{name:'Open default',exact:true}).click();
        await expect.poll(async()=>(await session()).project_id,{timeout:30000}).toBe('default');
        contextId=(await session()).context_id;
        const current=await session();expect(current.device.active).toBe(false);
        expect(current.device.historical_collection_status).toBe('REMOTE_STATE_UNKNOWN');
        const rejected=await page.evaluate(async({context,csrf})=>{
          const r=await fetch('/v1/product/projects/create',{method:'POST',headers:{'Content-Type':'application/json',
            'X-TwinPulse-Context':context,'X-TwinPulse-CSRF':csrf},body:JSON.stringify({project_id:'stale_should_not_exist'})});
          return {status:r.status,body:await r.json()};
        },{context:staleContext,csrf:current.csrf_token});
        expect(rejected.status).toBe(409);expect(rejected.body.error.code).toBe('project_context_changed');
        result.checks.push('Default return '+(i+1)+' retains historical UNKNOWN and rejects a stale context POST');
        await page.reload();contextId=(await session()).context_id;
        await page.screenshot({path:path.join(output,'default-return-'+(i+1)+'.png')});
      }
      if(process.env.TWINPULSE_FLOW_SAVED==='1'){
        await page.getByRole('button',{name:'Open '+savedProject,exact:true}).click();
        await expect.poll(async()=>{const s=await session();return !s.project_switch&&s.project_id===savedProject;},{timeout:30000}).toBe(true);
        contextId=(await session()).context_id;
        await reopenSaved();
        await page.screenshot({path:path.join(output,'saved-after-switch-'+(i+1)+'.png')});
      }
    }
    result.checks.push('Three actual same-tab same-URL Kit rebinds; saved mode also rebuilds after every switch; no generation');
  }else{
    for(const specification of cases){
      const item={id:specification.id,status:'FAIL',screens:[],milestones:[],started_at:new Date().toISOString()};
      result.cases.push(item);checkpoint();
      try{
        const resume=process.env.TWINPULSE_FLOW_RESUME==='1';
        item.project_id=resume?(await session()).project_id:await newChat();
        const input=page.getByRole('textbox',{name:'Message TwinPulse',exact:true});
        let start;
        if(resume){
          const open=page.getByRole('button',{name:/^Open saved chat · /});await expect(open).toBeVisible({timeout:20000});await open.click();
          start=Date.now();await page.getByRole('button',{name:'Continue unfinished work',exact:true}).click();
          item.continuation=true;
        }else{
        if(specification.image)await page.locator('input[type=file]').setInputFiles(specification.image);
        await input.fill(specification.prompt);await page.getByRole('button',{name:'Send',exact:true}).click();
        const choice=page.getByRole('region',{name:'Do you have a physical robot?',exact:true});
        await expect(choice).toBeVisible();await choice.getByRole('radio',{name:'Simulation only',exact:true}).check();
        start=Date.now();await choice.getByRole('button',{name:'Create Twin',exact:true}).click();
        }
        await expect(page.getByLabel('Maximum spend for this action (USD)')).toHaveCount(0);
        let terminal=null,lastRendered=-1;
        const deadline=Date.now()+940000;
        while(Date.now()<deadline){
          const [chat,workflow,viewport]=await Promise.all([read('/v1/product/conversation'),read('/v1/product/workflow'),read('/v1/product/viewport')]);
          const job=chat.generation;
          if(job){item.operation_id=job.operation_id;item.execution_id=workflow.execution_id??job.execution_id??job.progress?.execution_id;}
          const rendered=job?.progress?.generation_preview?.rendered_count;
          if(viewport.frame && (rendered!==lastRendered || item.screens.length===0)){
            lastRendered=rendered;const name=`${specification.id}-${item.screens.length+1}.png`;
            await page.screenshot({path:path.join(output,name)});item.screens.push(name);
            item.milestones.push({elapsed_s:(Date.now()-start)/1000,rendered:rendered??null,stage:job?.progress?.stage,viewport});
            checkpoint();
          }
          if(job && ['completed','failed','cancelled','interrupted'].includes(job.state)){
            terminal={chat,workflow,viewport};break;
          }
          await page.waitForTimeout(500);
        }
        if(!terminal)throw new Error('Live workflow did not terminate within the current configured allowance');
        item.elapsed_s=(Date.now()-start)/1000;item.generation=terminal.chat.generation;item.workflow=terminal.workflow;item.viewport=terminal.viewport;
        await page.waitForTimeout(2000);
        const name=specification.id+'-terminal.png';await page.screenshot({path:path.join(output,name)});item.screens.push(name);
        if(item.generation.state!=='completed')throw new Error(item.generation.error?.message??item.generation.summary);
        await expect.poll(async()=>{item.current_viewport=await read('/v1/product/viewport');return !!item.current_viewport.frame;},{timeout:45000}).toBe(true);
        item.saved_revision=terminal.workflow.site_draft?.revision;
        await page.reload();contextId=(await session()).context_id;
        await expect(page.getByRole('textbox',{name:'Message TwinPulse',exact:true})).toBeVisible();
        const reopened=await read('/v1/product/workflow');expect(reopened.site_draft.revision).toBe(item.saved_revision);
        item.status='PASS';item.checks=['Real generation without monetary approval','Actual current Isaac frame','Saved scene survives page reload'];
      }catch(error){item.error=String(error);item.status='FAIL';item.alerts=await page.getByRole('alert').allTextContents();}
      checkpoint();console.log(JSON.stringify({id:item.id,status:item.status,elapsed_s:item.elapsed_s,error:item.error}));
      if(item.generation?.error?.diagnostics?.finish_reason==='length')break;
    }
  }
  expect(result.page_errors).toEqual([]);
  result.status=result.cases.every(c=>c.status==='PASS')?'PASS':'FAIL';
}catch(error){result.error=String(error);
  if(page){result.failure_buttons=await page.getByRole('button').allTextContents();
    await page.screenshot({path:path.join(output,'failure.png')});}}
finally{checkpoint();await browser?.close();}
process.exitCode=result.status==='PASS'?0:1;
