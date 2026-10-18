// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,bootstrap=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output=process.env.TWINPULSE_REHEARSAL_OUTPUT,chrome=process.env.TWINPULSE_REHEARSAL_CHROME;
if(!base||new URL(base).hostname!=='127.0.0.1'||!bootstrap||!output||!chrome)throw Error('Owned local configuration required');
let browser,stage='bootstrap';
const result={status:'FAIL',external_requests:0,robot_requests:0,engine_commands:0,page_errors:0,checks:[]};
try{
  browser=await chromium.launch({executablePath:chrome,headless:true});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',route=>{
    const url=new URL(route.request().url()),method=route.request().method();
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    if(url.pathname.startsWith('/v1/product/robot/')&&method!=='GET'){result.robot_requests++;return route.abort();}
    if(['/v1/product/commands','/v1/product/bedroom/build','/v1/product/bedroom/replay'].includes(url.pathname)){
      result.engine_commands++;return route.abort();}
    return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  const panel=page.getByRole('region',{name:'Automatic sensor mapping'});
  stage='saved_input_no_auto_start';
  await expect(panel.getByText('Start automatic replay')).toBeEnabled();
  await expect(panel.getByText('Ready to select recorded input')).toBeVisible();
  await panel.getByLabel('Automatic recorded input').selectOption('1a7f033af112437699ca67aef3438ecb');
  await panel.getByLabel('Automatic reference map').selectOption('');
  await panel.getByLabel('Automatic photo policy').selectOption('correct_walls');
  if(process.env.TWINPULSE_REPLAY_1X==='1')await panel.getByLabel('Automatic replay speed').selectOption('recorded_1x');
  stage='single_start_actual_causal_processing';
  let ended;
  page.on('response',async response=>{
    if(response.url()===`${base}/v1/product/automatic-demo`&&response.ok()){
      const value=await response.json();if(value.job?.state==='COMPLETED')ended=value;
    }
  });
  await panel.getByText('Start automatic replay').click();
  await expect(panel.getByText(/COMPLETED ·/)).toBeVisible({timeout:60000});
  await expect.poll(()=>!!ended).toBe(true);
  expect(ended.motion_authorized).toBe(false);
  expect(ended.job.result.counts.scans_seen).toBe(30);
  expect(ended.job.result.counts.scans_paired).toBe(25);
  expect(ended.job.result.reasons.ODOM_TIME_GAP).toBe(4);
  expect(ended.job.result.source_reason).toBe('INPUT_DEADLINE_EXPIRED');
  expect(ended.job.result.alignment_verified).toBe(false);
  expect(ended.job.result.photo_alignment.status).toBe('INSUFFICIENT_EVIDENCE');
  expect(ended.job.result.photo_alignment.reason).toBe('NEED_MORE_SEPARATED_STRUCTURAL_VIEWS');
  expect(ended.job.result.photo_alignment.applied_revision).toBe(null);
  if(process.env.TWINPULSE_REPLAY_1X==='1'){
    expect(ended.job.replay_mode).toBe('recorded_1x');
    expect(ended.job.replay_timing.receipt_span_s).toBeGreaterThan(3);
    expect(ended.job.elapsed_s).toBeGreaterThanOrEqual(ended.job.replay_timing.receipt_span_s);
    expect(ended.job.replay_timing.processing_elapsed_s).toBeLessThan(120);
    expect(ended.job.replay_timing.pending_event_bound).toBe(1);
    expect(ended.job.replay_timing.timing_verified).toBe(false);
    result.checks.push('explicit_1x_original_receipt_pacing_no_skipped_events_no_live_timing_claim');
  }
  await expect(panel.getByText('Photo Twin alignment · INSUFFICIENT_EVIDENCE')).toBeVisible();
  fs.writeFileSync(path.join(output,'actual-session.json'),JSON.stringify(ended,null,2),{flag:'wx'});
  await expect(panel.getByRole('img',{name:'Automatic corrected sensor map'})).toBeVisible();
  expect(await panel.locator('svg rect').count()).toBeGreaterThan(100);
  result.checks.push('single_Start_built_Web_auth_API_worker_actual_raw_causal_no_frame_selection',
    'historical_failure_and_odom_gaps_preserved_no_pose_authority');
  stage='reopen_and_responsive';
  const reopened=page.waitForResponse(r=>r.url().endsWith('/automatic-demo/reopen')&&r.ok());
  await panel.getByText('Reopen saved map · no retained pose').click();
  const value=await(await reopened).json();expect(value.pose_candidate).toBe(null);expect(value.motion_authorized).toBe(false);
  expect(value.photo_alignment.report_revision).toBe(ended.job.result.photo_alignment.report_revision);
  await expect(panel.getByText(/Historical evidence only/)).toBeVisible();
  await expect(panel.locator('svg circle')).toHaveCount(0);
  await panel.screenshot({path:path.join(output,'automatic-map-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await panel.screenshot({path:path.join(output,'automatic-map-mobile.png')});
  result.checks.push('persisted_map_reopen_without_current_pose','desktop_mobile_no_horizontal_overflow');
  result.checks.push('automatic_photo_policy_disjoint_evidence_rejection_preserved','photo_report_reopen_no_authority');
  expect(result.external_requests+result.robot_requests+result.engine_commands+result.page_errors).toBe(0);
  result.status='PASS';
}catch(error){result.error_type=error.name;result.failed_stage=stage;
  result.reason=String(error.message).replaceAll(bootstrap,'[REDACTED]').slice(0,600);}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2),{flag:'wx'});}
console.log(JSON.stringify(result));process.exitCode=result.status==='PASS'?0:1;
