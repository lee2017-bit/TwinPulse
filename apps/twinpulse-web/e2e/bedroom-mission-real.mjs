// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output=process.env.TWINPULSE_REHEARSAL_OUTPUT;
if(new URL(base).hostname!=='127.0.0.1')throw Error('owned loopback required');
let browser,stage='bootstrap';
const result={status:'FAIL',data:'SYNTHETIC_PHOTO_GEOMETRY_NOT_ROBOT',stages:[],external_requests:0,forbidden_requests:0,mission_requests:0,comparison_requests:0,mission_export_requests:0,comparison_export_requests:0,page_errors:0};
try{
 browser=await chromium.launch({executablePath:process.env.TWINPULSE_REHEARSAL_CHROME,headless:true});
 const page=await browser.newPage({viewport:{width:1400,height:1100}});
 await page.route('**/*',route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
  if(req.method()==='POST'&&(url.pathname.startsWith('/v1/product/robot/')||url.pathname==='/v1/product/commands'||url.pathname==='/v1/product/bedroom/build'||url.pathname==='/v1/product/bedroom/replay')){
   result.forbidden_requests++;return route.abort();
  }
  if(url.pathname==='/v1/product/bedroom/rehearse')result.mission_requests++;
  if(url.pathname==='/v1/product/bedroom/compare')result.comparison_requests++;
  if(url.pathname==='/v1/product/bedroom/rehearse-export')result.mission_export_requests++;
  if(url.pathname==='/v1/product/bedroom/compare-export')result.comparison_export_requests++;
  return route.continue();
 });
 page.on('pageerror',()=>result.page_errors++);
 await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
 await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
 const panel=page.getByRole('region',{name:'Photo-based room Digital Twin'});
 expect(result.mission_requests).toBe(0);
 await panel.getByRole('button',{name:'Load saved room and model',exact:true}).click();
 await expect(panel.getByRole('button',{name:'Run synthetic mission',exact:true})).toBeEnabled();
 result.stages.push('explicit_photo_source_review_without_engine_or_robot');
 for(const [scenario,label,status] of [['route','Run synthetic mission','ARRIVED'],['blocked','Rehearse obstacle stop','OBSTACLE_IN_SWEPT_ENVELOPE'],['stale_scan','Rehearse stale-sensor stop','SCAN_STALE']]){
  stage=scenario;
  const response=page.waitForResponse(r=>r.url()===base+'/v1/product/bedroom/rehearse'&&r.request().method()==='POST');
  await panel.getByRole('button',{name:label,exact:true}).click();
  const data=await (await response).json();
  expect(data.status).toBe(status);expect(data.motion_authorized).toBe(false);expect(data.physical_validation).toBe('NOT_RUN');
  expect(data.isaac_run).toBe(false);expect(data.events.length).toBeGreaterThan(1);
  fs.writeFileSync(path.join(output,`${scenario}.json`),JSON.stringify(data,null,2));
  await expect(panel.getByText(`${status} · not physical validation`,{exact:true})).toBeVisible();
  await panel.getByLabel('Synthetic mission result').screenshot({path:path.join(output,`${scenario}.png`)});
  if(scenario==='route'){
   await panel.getByLabel('Synthetic replay speed').selectOption('4');
   await panel.getByRole('button',{name:'Play replay',exact:true}).click();
   await expect.poll(async()=>Number(await panel.getByLabel('Synthetic record frame').inputValue())).toBeGreaterThan(3);
   await panel.getByRole('button',{name:'Pause replay',exact:true}).click();
   await panel.getByLabel('Synthetic record frame').press('End');
   expect(Number(await panel.getByLabel('Synthetic record frame').inputValue())).toBe(data.events.length);
   await panel.getByRole('button',{name:'Restart replay',exact:true}).click();
   expect(Number(await panel.getByLabel('Synthetic record frame').inputValue())).toBe(0);
   expect(result.forbidden_requests).toBe(0);
   result.stages.push('local_timed_play_pause_seek_restart_without_engine_or_robot_commands');
   const download=page.waitForEvent('download');
   await panel.getByRole('button',{name:'Save synthetic commands and observations as JSON',exact:true}).click();
   await (await download).saveAs(path.join(output,'export.json'));
   expect(JSON.parse(fs.readFileSync(path.join(output,'export.json'),'utf8')).revision).toBe(data.revision);
  }else{
   const last=data.events.at(-1);expect(last.decision.linear_m_s).toBe(0);expect(last.decision.angular_rad_s).toBe(0);
   expect(last.pose_after).toEqual(last.pose_before);
  }
  result.stages.push(`${scenario}_one_request_many_decisions_no_motion_authority`);
 }
 expect(result.mission_requests).toBe(3);
 stage='comparison';
 const compared=page.waitForResponse(r=>r.url().endsWith('/bedroom/compare'));
 await panel.getByText('Compare two routes under identical conditions',{exact:true}).click();
 const comparison=await(await compared).json();
 expect(comparison.eligible_for_efficiency_comparison).toBe(true);
 expect(comparison.candidates).toHaveLength(2);
 for(const c of comparison.candidates){expect(c.metrics.collision_count).toBe(null);expect(c.metrics.physical_success).toBe(null);}
 expect(comparison.b_minus_a.duration_s).toBeCloseTo(-7.85);
 await expect(panel.getByLabel('Same-condition synthetic comparison')).toBeVisible();
 const comparisonDownload=page.waitForEvent('download');await panel.getByText('Save comparison and both records as JSON').click();
 await(await comparisonDownload).saveAs(path.join(output,'comparison-export.json'));
 expect(JSON.parse(fs.readFileSync(path.join(output,'comparison-export.json'),'utf8')).revision).toBe(comparison.revision);
 await panel.getByText('B review record',{exact:true}).click();
 await expect(panel.getByText('ARRIVED · not physical validation',{exact:true})).toBeVisible();
 expect(result.comparison_requests).toBe(1);expect(result.mission_requests).toBe(3);
 expect(result.mission_export_requests).toBe(1);expect(result.comparison_export_requests).toBe(1);
 await panel.screenshot({path:path.join(output,'comparison-desktop.png')});
 result.stages.push('same_conditions_comparison_unknown_contact_export_and_local_candidate_selection');
 await page.setViewportSize({width:390,height:844});await panel.screenshot({path:path.join(output,'mobile.png')});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 expect(result.external_requests).toBe(0);expect(result.forbidden_requests).toBe(0);expect(result.page_errors).toBe(0);
 result.stages.push('export_mobile_and_no_external_engine_or_robot_commands');result.status='PASS';
}catch(e){result.failed_stage=stage;result.error=String(e.message).split(secret).join('[redacted]').split(base).join('[local]').split('\n').slice(0,7).join('\n');}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
