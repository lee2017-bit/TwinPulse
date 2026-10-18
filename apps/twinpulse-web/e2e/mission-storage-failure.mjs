// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const out=process.env.TWINPULSE_REHEARSAL_OUTPUT,map=process.env.TWINPULSE_REHEARSAL_MAP;
let browser,page;const result={status:'FAIL',mission_starts:0,page_errors:0,external_requests:0,robot_requests:0};
try{
  if(!base||new URL(base).hostname!=='127.0.0.1')throw Error('Owned local server required');
  browser=await chromium.launch({headless:true,executablePath:process.env.TWINPULSE_REHEARSAL_CHROME});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',route=>{const u=new URL(route.request().url());
    if(u.origin!==base&&!['data:','blob:'].includes(u.protocol)){result.external_requests++;return route.abort();}
    if(u.pathname.startsWith('/v1/product/robot/')){result.robot_requests++;return route.abort();}
    if(u.pathname.endsWith('/automatic-demo/mission-start'))result.mission_starts++;
    return route.continue();});
  page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  await page.getByRole('region',{name:'Automatic sensor mapping'}).getByLabel('Saved evidence map').selectOption(map);
  const mission=page.getByRole('region',{name:'Observed goal mission'});
  await expect(mission.getByText('Start observed mission · maximum 45 s')).toBeEnabled({timeout:10000});
  await mission.getByLabel('Goal X (m)').fill('.05');await mission.getByLabel('Goal Y (m)').fill('-.6');
  await mission.getByText('Start observed mission · maximum 45 s').click();
  const popup=mission.getByRole('alertdialog',{name:'Observed mission error'});
  await expect(popup).toBeVisible({timeout:60000});
  await expect(popup).toContainText('REPORT_SAVE: MISSION_REPORT_STORAGE_FULL (OSError, errno 28)');
  await expect(mission.getByText('Show saved mission in Isaac 3D')).toBeDisabled();
  await expect(mission.getByText(/Current room position unavailable/)).toBeVisible();
  const apiResponse=await page.request.get(`${base}/v1/product/automatic-demo/mission`);
  expect(apiResponse.ok()).toBe(true);const api=await apiResponse.json();
  expect(api.job.state).toBe('FAILED');expect(api.job.report_status).toBe('FAILED');
  expect(api.job.visual.pose_room).toBeNull();expect(api.job.visual.scan_room).toEqual([]);
  await mission.screenshot({path:path.join(out,'storage-failure-desktop.png')});
  await popup.screenshot({path:path.join(out,'storage-error-popup-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await mission.screenshot({path:path.join(out,'storage-failure-mobile.png')});
  await popup.screenshot({path:path.join(out,'storage-error-popup-mobile.png')});
  await page.reload();await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  await expect(page.getByRole('region',{name:'Observed goal mission'})).toBeVisible();
  // A bounded observation interval, not a retry or source-clock extension.
  await page.waitForTimeout(350);
  expect(result.mission_starts).toBe(1);expect(result.page_errors+result.external_requests+result.robot_requests).toBe(0);
  result.status='PASS';result.checks=['actual_saved_map_worker_report_write_failure',
    'typed_popup_current_pose_cleared_saved_3D_disabled','reload_does_not_restart_motion'];
}catch(e){result.reason=String(e.message).replaceAll(secret??'','[REDACTED]').slice(0,600);}
finally{
  if(browser)try{await browser.close();}catch{result.close_error='OWNED_BROWSER_CLOSE_FAILED';result.status='FAIL';}
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2),{flag:'wx'});
}
console.log(JSON.stringify(result));process.exitCode=result.status==='PASS'?0:1;
