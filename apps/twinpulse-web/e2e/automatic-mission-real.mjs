// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const out=process.env.TWINPULSE_REHEARSAL_OUTPUT,map=process.env.TWINPULSE_REHEARSAL_MAP;
const cold=process.env.TWINPULSE_REHEARSAL_COLD==='1';
const correction=process.env.TWINPULSE_REHEARSAL_CORRECTION==='1';
let browser,page,stage='bootstrap';const result={status:'FAIL',page_errors:0,external_requests:0,robot_requests:0,checks:[]};
try{
  if(!base||new URL(base).hostname!=='127.0.0.1')throw Error('Owned local server required');
  browser=await chromium.launch({headless:true,executablePath:process.env.TWINPULSE_REHEARSAL_CHROME});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',route=>{const u=new URL(route.request().url());
    if(u.origin!==base&&!['data:','blob:'].includes(u.protocol)){result.external_requests++;return route.abort();}
    if(u.pathname.startsWith('/v1/product/robot/')&&route.request().method()!=='GET'){result.robot_requests++;return route.abort();}
    return route.continue();});
  page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  const mapping=page.getByRole('region',{name:'Automatic sensor mapping'}),mission=page.getByRole('region',{name:'Observed goal mission'});
  if(cold&&process.env.TWINPULSE_REHEARSAL_ISAAC==='1'){
    stage='owned_room_build';
    const accepted=await page.evaluate(async()=>{
      const csrf=sessionStorage.getItem('twinpulse.csrf');
      async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-TwinPulse-CSRF':csrf},body:JSON.stringify(body)});
        const v=await r.json();if(!r.ok)throw Error(`${path}: ${r.status} ${v.error?.code}`);return v;}
      let workflow=await (await fetch('/v1/product/workflow')).json();
      if(workflow.phase==='restore_review_required')workflow=await post('/v1/product/project/continue-room',{});
      const draft=workflow.site_draft;
      await post('/v1/product/draft/acknowledge',{revision:draft.revision});
      await post('/v1/product/lease',{});
      const deadline=Date.now()+15000;
      while(true){
        const state=await (await fetch('/v1/product/state')).json();
        if(state.engine_readiness?.site_scene_build_v2?.ready)break;
        if(Date.now()>deadline)throw Error(`Build readiness: ${state.engine_readiness?.site_scene_build_v2?.code}`);
        await post('/v1/product/lease',{});await new Promise(resolve=>setTimeout(resolve,200));
      }
      return post('/v1/product/commands',{client_request_id:crypto.randomUUID(),command_type:'build_site_scene',artifact_id:draft.artifact_id,expected_applied_revision:draft.revision});
    });
    await expect.poll(async()=>{const r=await page.request.get(`${base}/v1/product/state`);const v=await r.json();return v.operations.find(o=>o.command_id===accepted.command_id)?.status;},{timeout:30000}).toBe('succeeded');
    result.checks.push('authenticated_owned_room_Build_before_cold_mission');
  }
  stage='reopen_without_pose';if(!cold)await mapping.getByLabel('Saved evidence map').selectOption(map);
  await expect(mission.getByText('Start observed mission · maximum 45 s')).toBeEnabled({timeout:10000});
  if(correction)await mission.getByLabel('Photo correction').selectOption('correct_walls');
  for(const [x,y] of cold?[[correction?.4:.15,-.6]]:[[.15,-.6],[-.14,-.4]]){
    stage='current_pose_goal_feedback';await mission.getByLabel('Goal X (m)').fill(String(x));await mission.getByLabel('Goal Y (m)').fill(String(y));
    const [response]=await Promise.all([page.waitForResponse(r=>r.url().endsWith('/automatic-demo/mission-start')&&r.ok()),
      mission.getByText('Start observed mission · maximum 45 s').click()]);const started=await response.json();
    expect(started.motion_authorized).toBe(false);
    // Wall time includes heavy headless Isaac/fit CPU work. The actual worker
    // contract still has its unchanged 45 s source-clock budget.
    await expect(mission.getByRole('status').filter({hasText:/^(MISSION_ARRIVED|FAILED|FORCE_STOPPED) ·/})).toBeVisible({timeout:cold?(process.env.TWINPULSE_REHEARSAL_DENSE==='1'?180000:120000):60000});
    await expect(mission.getByRole('status').filter({hasText:/^MISSION_ARRIVED ·/})).toBeVisible();
    await expect(mission.getByRole('img',{name:'Mission route and current scan'})).toBeVisible();
    result.checks.push('sensor_feedback_arrival_without_per_command_input');
  }
  await mission.screenshot({path:path.join(out,'mission-desktop.png')});
  stage='saved_report_3d';
  if(process.env.TWINPULSE_REHEARSAL_ISAAC==='1'){
    const lease=await page.evaluate(async()=>{const csrf=sessionStorage.getItem('twinpulse.csrf');
      const r=await fetch('/v1/product/lease',{method:'POST',headers:{'Content-Type':'application/json','X-TwinPulse-CSRF':csrf},body:'{}'});return r.status;});
    expect(lease).toBe(200);
    const [r]=await Promise.all([page.waitForResponse(r=>r.url().endsWith('/automatic-demo/mission-preview3d')),
      mission.getByText('Show saved mission in Isaac 3D').click()]);const operation=await r.json();
    if(r.status()!==202)throw Error(`Isaac submission ${r.status()}: ${JSON.stringify(operation)}`);
    await expect.poll(async()=>{const r=await page.request.get(`${base}/v1/product/state`);const value=await r.json();
      return value.operations.find(o=>o.command_id===operation.command_id)?.status;},{timeout:30000}).toBe('succeeded');
    result.checks.push('same_report_broker_bridge_Isaac_saved_visual');
  }
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await mission.screenshot({path:path.join(out,'mission-mobile.png')});
  expect(result.page_errors+result.external_requests+result.robot_requests).toBe(0);result.status='PASS';
}catch(e){result.failed_stage=stage;result.reason=String(e.message).replaceAll(secret??'','[REDACTED]').slice(0,600);
  if(page)try{result.screen_text=(await page.locator('body').innerText({timeout:2000})).replaceAll(secret??'','[REDACTED]').slice(-12000);}catch{}
}
finally{
  // Persist the diagnostic even if closing our owned browser also fails.
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2),{flag:'wx'});
  if(browser)try{await browser.close();}catch(e){result.close_error=String(e.message).slice(0,300);
    fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));}
}
console.log(JSON.stringify(result));process.exitCode=result.status==='PASS'?0:1;
