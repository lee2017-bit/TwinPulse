// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {pathToFileURL} from 'node:url';
import fs from 'node:fs';import path from 'node:path';
// Only the browser test runtime is external; Web assets/API/engine come from
// the same hash-checked outside-checkout release.
const {chromium,expect}=await import(pathToFileURL(process.env.TWINPULSE_PLAYWRIGHT_MODULE).href);
const base=process.env.TWINPULSE_REHEARSAL_URL,secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const out=process.env.TWINPULSE_REHEARSAL_OUTPUT,fault=process.env.TWINPULSE_PACKAGE_CASE==='storage';
let browser,page;const result={status:'FAIL',mission_starts:0,external_requests:0,robot_requests:0,page_errors:0};
async function openAdvancedTools(){
  await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toBeVisible({timeout:15000});
  await page.getByRole('button',{name:'Projects',exact:true}).click();
  await page.getByRole('button',{name:'Advanced tools',exact:true}).click();
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
}
try{
  if(new URL(base).hostname!=='127.0.0.1')throw Error('OWNED_LOOPBACK_REQUIRED');
  browser=await chromium.launch({headless:true,executablePath:process.env.TWINPULSE_REHEARSAL_CHROME});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',r=>{const u=new URL(r.request().url());
    if(u.origin!==base&&!['data:','blob:'].includes(u.protocol)){result.external_requests++;return r.abort();}
    if(u.pathname.startsWith('/v1/product/robot/')){result.robot_requests++;return r.abort();}
    if(u.pathname.endsWith('/automatic-demo/mission-start'))result.mission_starts++;
    return r.continue();});
  page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
  await openAdvancedTools();
  // The fixture's initial Build lease must expire normally. Acquire through
  // the authenticated product route, never rewrite broker ownership.
  await page.waitForTimeout(3200);
  const csrf=await page.evaluate(()=>sessionStorage.getItem('twinpulse.csrf'));
  const lease=await page.request.post(`${base}/v1/product/lease`,{data:{},headers:{'X-TwinPulse-CSRF':csrf}});
  expect(lease.ok()).toBe(true);
  const mission=page.getByRole('region',{name:'Observed goal mission'});
  await mission.getByLabel('Mission mode').selectOption('SURVEY_THEN_NAVIGATE');
  await mission.getByLabel('Goal X (m)').fill('.15');await mission.getByLabel('Goal Y (m)').fill('-.6');
  await expect(mission.getByLabel('Photo correction').locator('option[value="correct_walls"]')).toBeEnabled({timeout:15000});
  await mission.getByLabel('Photo correction').selectOption('correct_walls');
  await expect(mission.getByRole('button',{name:'Start observed mission · maximum 45 s',exact:true})).toBeEnabled();
  await mission.getByRole('button',{name:'Start observed mission · maximum 45 s',exact:true}).click();
  if(fault){
    const popup=mission.getByRole('alertdialog',{name:'Observed mission error'});
    await expect(popup).toBeVisible({timeout:110000});
    await expect(popup).toContainText('REPORT_SAVE: MISSION_REPORT_STORAGE_FULL (OSError, errno 28)');
    await expect(mission.getByText('Show saved mission in Isaac 3D')).toBeDisabled();
    await expect(mission.getByText(/Current room position unavailable/)).toBeVisible();
  }else{
    await expect(mission.getByText(/MISSION_ARRIVED · PC runtime/)).toBeVisible({timeout:110000});
    await expect(mission.getByText('Show saved mission in Isaac 3D')).toBeEnabled({timeout:15000});
    await mission.getByText('Show saved mission in Isaac 3D').click();
    // The UI itself permits 15 s readiness + 30 s owned engine execution.
    // An evaluator's shorter 15 s wait is not a product failure criterion.
    await expect(mission.getByText('Isaac saved visual is ready. This is not physical execution.')).toBeVisible({timeout:50000});
  }
  const response=await page.request.get(`${base}/v1/product/automatic-demo/mission`);
  expect(response.ok()).toBe(true);const state=await response.json();
  expect(state.job.state).toBe(fault?'FAILED':'MISSION_ARRIVED');
  expect(state.job.physical_demo_ready).toBe(false);
  if(fault){expect(state.job.visual.pose_room).toBeNull();expect(state.job.visual.scan_room).toEqual([]);}
  await mission.screenshot({path:path.join(out,'browser-mission.png')});
  await page.reload();await openAdvancedTools();
  await page.waitForTimeout(500);
  expect(result.mission_starts).toBe(1);
  expect(result.external_requests+result.robot_requests+result.page_errors).toBe(0);
  result.status='PASS';result.checks=['packaged_built_Web_auth_API_shared_cold_worker_actual_Isaac',
    fault?'typed_storage_popup_pose_clear_saved_3D_locked':'derived_geometry_goal_and_saved_3D',
    'reload_no_new_mission_no_robot_requests'];
}catch(e){
  result.reason=String(e.message??e).replaceAll(secret??'NO_SECRET','[REDACTED]').slice(0,500);
  if(page)try{
    result.failure_view=(await page.getByRole('region',{name:'Observed goal mission'}).innerText()).replaceAll(secret??'NO_SECRET','[REDACTED]').slice(0,3000);
    await page.screenshot({path:path.join(out,'browser-failure.png'),fullPage:true});
  }catch{result.diagnostic_error='BROWSER_FAILURE_VIEW_UNAVAILABLE';}
}
finally{await browser?.close();fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
