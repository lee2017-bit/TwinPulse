// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,bootstrap=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output=process.env.TWINPULSE_REHEARSAL_OUTPUT,chrome=process.env.TWINPULSE_REHEARSAL_CHROME;
if(!base||new URL(base).hostname!=='127.0.0.1'||!bootstrap||!output||!chrome)throw Error('Owned local configuration required');
let browser,step='bootstrap';
const result={status:'FAIL',external_requests:0,robot_requests:0,robot_snapshot_reads:0,engine_commands:0,page_errors:0,checks:[]};
try{
  browser=await chromium.launch({executablePath:chrome,headless:true});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    // Abort before delivery as well as recording accidental forbidden paths.
    if(url.pathname.startsWith('/v1/product/robot/')){
      if(route.request().method()==='GET'){result.robot_snapshot_reads++;return route.continue();}
      result.robot_requests++;return route.abort();
    }
    if(['/v1/product/commands','/v1/product/bedroom/build','/v1/product/bedroom/replay'].includes(url.pathname)){
      result.engine_commands++;return route.abort();}
    return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  const panel=page.getByRole('region',{name:'Photo-based room Digital Twin'});
  step='room_read_only_without_engine';
  await panel.getByText('Load saved room and model').click();
  await expect(panel.getByText('Display room + Burger in Isaac')).toBeDisabled();
  const localization=page.getByRole('region',{name:'Automatic saved scan localization'});
  await localization.getByText('Load saved sessions').click();
  await expect.poll(async()=>localization.getByLabel('Localization saved session').locator('option').count()).toBeGreaterThan(1);
  await localization.getByLabel('Localization saved session').selectOption('4493be87ef7643ababb661b4a12f0180');
  const map=page.getByRole('region',{name:'Session observation map'});
  step='actual_observation_map';
  const response=page.waitForResponse(r=>r.url().endsWith('/observation-map'));
  await map.getByText('Build observation map · entire session').click();
  await expect(map.getByText(/Projecting saved scan/)).toBeVisible();
  const report=await(await response).json();
  expect(report.paired_frames).toBe(2317);expect(report.frame_count).toBe(2318);
  expect(report.photo_geometry_used).toBe(false);expect(report.motion_authorized).toBe(false);
  expect(report.timing.acquisition_timing_verified).toBe(false);
  fs.writeFileSync(path.join(output,'actual-report.json'),JSON.stringify(report));
  await expect(map.getByText(/Diagnostic map/)).toBeVisible();
  expect(await map.locator('svg circle').count()).toBeGreaterThan(3800);
  result.checks.push('real_UI_auth_API_raw_decoder_endpoint_map_without_engine_or_robot');
  step='seek_and_play';
  const slider=map.getByLabel('Observation scan time');
  const seek=async value=>{await slider.evaluate((input,value)=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,String(value));
    input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
  },value);};
  await seek(31);
  await expect(map.getByText(`Original frame ${report.keyframes[31].frame+1}/2318`,{exact:false})).toBeVisible();
  await map.getByText('Play recorded scans · 4×').click();
  await expect.poll(async()=>Number(await slider.inputValue()),{timeout:5000}).toBeGreaterThan(31);
  await map.getByText('Pause recorded scans').click();
  await map.screenshot({path:path.join(output,'observation-map-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await map.screenshot({path:path.join(output,'observation-map-mobile.png')});
  result.checks.push('time_seek_and_play_real_saved_keyframes','desktop_mobile_no_horizontal_overflow');
  step='real_multiframe_model_comparison';
  await page.setViewportSize({width:1366,height:950});
  const compared=page.waitForResponse(r=>r.url().endsWith('/compare-model'));
  await map.getByText('Compare with photo 3D · multiple frames').click();
  await expect(map.getByText(/Comparing multiple saved scans/)).toBeVisible();
  const diagnostic=await(await compared).json();
  expect(diagnostic.status).toBe('MODEL_OR_ODOM_INCONSISTENT');expect(diagnostic.evaluated_keyframes).toBe(63);
  expect(diagnostic.best_diagnostic_hypothesis.supported_frames).toBe(0);
  expect(diagnostic.geometry_changed).toBe(false);expect(diagnostic.motion_authorized).toBe(false);
  expect(diagnostic.observation_revision).toBe(report.revision);
  fs.writeFileSync(path.join(output,'actual-comparison.json'),JSON.stringify(diagnostic));
  const comparison=page.getByRole('region',{name:'Photo model comparison'});
  await expect(comparison).toBeVisible();await comparison.screenshot({path:path.join(output,'model-comparison-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await comparison.screenshot({path:path.join(output,'model-comparison-mobile.png')});
  result.checks.push('real_multiframe_photo_comparison_no_geometry_mutation_or_pose_authority');
  step='real_heldout_sensor_map_location';
  const sensor=page.getByRole('region',{name:'Sensor map localization'});
  await sensor.getByLabel('Sensor map test frame').fill('772');
  const located=page.waitForResponse(r=>r.url().endsWith('/sensor-map'));
  await sensor.getByText('Locate recorded scans · sensor map').click();
  await expect(sensor.getByText(/Rebuilding the reference/)).toBeVisible();
  const candidate=await(await located).json();
  expect(candidate.status).toBe('SENSOR_MAP_GEOMETRIC_CANDIDATE');
  expect(candidate.query_frames).toEqual([771,772,773]);
  expect(candidate.best_diagnostic_hypothesis.supported_query_frames).toBe(3);
  expect(candidate.reference_retained_scan_count).toBe(2273);
  expect(candidate.holdout.excluded_reference_frames.length).toBe(45);
  expect(candidate.holdout.direct_query_scan_reuse).toBe(false);
  expect(candidate.observation_revision).toBe(report.revision);
  expect(candidate.reference_source_revision).toBe(report.source_revision);
  expect(candidate.query_source_revision).toBe(report.source_revision);
  expect(candidate.photo_geometry_used).toBe(false);expect(candidate.room_transform_created).toBe(false);
  expect(candidate.alignment_verified).toBe(false);expect(candidate.motion_authorized).toBe(false);
  const excluded=new Set(candidate.holdout.excluded_reference_frames);
  expect(candidate.reference_endpoint_cells.every(p=>!excluded.has(p[3])&&!excluded.has(p[4]))).toBe(true);
  fs.writeFileSync(path.join(output,'actual-sensor-map-location.json'),JSON.stringify(candidate));
  await expect(sensor.getByText(/Historical sensor position candidate/)).toBeVisible();
  await expect(page.getByRole('region',{name:'Photo model comparison'})).toHaveCount(0);
  await page.setViewportSize({width:1366,height:950});
  await sensor.screenshot({path:path.join(output,'sensor-map-location-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await sensor.screenshot({path:path.join(output,'sensor-map-location-mobile.png')});
  step='real_sensor_photo_context_and_inconsistent_correspondence_rejection';
  const link=page.getByRole('region',{name:'Sensor map to photo room link'});
  const contextResponse=page.waitForResponse(r=>r.url().endsWith('/photo-link-context'));
  await link.getByText('Load photo wall anchors').click();
  const linkContext=await(await contextResponse).json();
  expect(linkContext.anchors.length).toBe(12);expect(linkContext.reference_kind).toBe('PHOTO_APPROXIMATION_NOT_METRIC_REFERENCE');
  expect(linkContext.anchors.every(a=>a.object_id.startsWith('wall_'))).toBe(true);
  await expect(link.getByText('Check coordinate link · no movement')).toBeDisabled();
  // Deliberately unverified test selections exercise real-source rejection.
  // They are NOT surveyed corners or an assertion of physical correspondence.
  const indices=[0,1200,2500,3500],anchors=['wall_left:0','wall_right:1','wall_window:2','wall_window:3'];
  for(let i=0;i<4;i++){
    await link.getByLabel('Photo link endpoint index').fill(String(indices[i]));
    await link.getByLabel('Photo link wall anchor').selectOption(anchors[i]);
    if(i===3)await link.getByLabel('Photo link pair role').selectOption('validation');
    await link.getByText('Add correspondence').click();
  }
  const linkedResponse=page.waitForResponse(r=>r.url().endsWith('/photo-link'));
  await link.getByText('Check coordinate link · no movement').click();
  const linked=await(await linkedResponse).json();
  expect(linked.status).toBe('ANCHOR_MISMATCH');expect(linked.sensor_pose_room_candidate).toBe(null);
  expect(linked.photo_geometry_changed).toBe(false);expect(linked.motion_authorized).toBe(false);
  expect(linked.sensor_revision).toBe(candidate.revision);expect(linked.context_revision).toBe(linkContext.revision);
  expect(linked.scale).toBe(1);expect(linked.rotation_determinant).toBe(1);
  fs.writeFileSync(path.join(output,'actual-photo-link-rejection.json'),JSON.stringify(linked));
  await expect(link.getByText('Preview linked goal coordinates')).toHaveCount(0);
  await page.setViewportSize({width:1366,height:950});
  await link.screenshot({path:path.join(output,'sensor-photo-link-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await link.screenshot({path:path.join(output,'sensor-photo-link-mobile.png')});
  result.checks.push('real_reference_photo_wall_ids_and_invalid_test_pairs_rejected_no_pose_or_goal_authority');
  await sensor.getByLabel('Sensor map test session').selectOption('b6cf346718da44b99e7bffe6f7919bbf');
  await expect(sensor.getByText(/Historical sensor position candidate/)).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Sensor map to photo room link'})).toHaveCount(0);
  result.checks.push('real_3frame_sensor_map_location_45_reference_scans_held_out_no_pose_authority',
                     'sensor_location_desktop_mobile_and_test_session_change_clears_candidate');
  step='session_invalidation';
  await localization.getByLabel('Localization saved session').selectOption('b6cf346718da44b99e7bffe6f7919bbf');
  await expect(map.getByText(/Diagnostic map/)).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Photo model comparison'})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Sensor map localization'})).toHaveCount(0);
  expect(result.robot_requests).toBe(0);expect(result.engine_commands).toBe(0);
  expect(result.external_requests).toBe(0);expect(result.page_errors).toBe(0);
  result.checks.push('session_change_clears_historical_map_no_auto_actions');result.status='PASS';
}catch(error){result.failed_stage=step;result.error_type=error.name;
  result.reason=String(error.message).replaceAll(bootstrap,'[redacted]').replaceAll(encodeURIComponent(bootstrap),'[redacted]').slice(0,600);}
finally{
  if(browser)await browser.close();
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));
}
if(result.status!=='PASS')process.exitCode=1;
