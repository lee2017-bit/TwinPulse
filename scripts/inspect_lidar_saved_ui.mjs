// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Diagnostic continuation only; never counted as the failed fresh journey.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const out=process.argv[2];if(!out)throw Error('Output required');
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const page=browser.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 const projectIndex=process.argv.indexOf('--project');
 if(projectIndex>=0){
  await page.getByRole('button',{name:'Open '+process.argv[projectIndex+1],exact:true}).click();
  await page.locator('.robot-fleet-row').filter({hasText:'Alpha'}).first().click();
 }
 const setup=page.getByRole('region',{name:'Control Alpha',exact:true}).getByText('Setup, sensor details and logs',{exact:true});
 const before=await setup.locator('..').getAttribute('open');if(before===null)await setup.click();
 await page.getByRole('region',{name:'Control Alpha',exact:true}).getByRole('button',{name:'Review LiDAR scans',exact:true}).click();
 const review=page.getByRole('dialog',{name:'LiDAR sensor review',exact:true});await expect(review).toBeVisible();
 const native=review.locator('.native-review');await expect(native).toHaveCount(1);
 let scan;
 if(process.argv.includes('--import')){
  if(await native.getAttribute('open')===null)await native.locator('summary').first().click();
  await native.getByLabel('Import native scan bundle (JSON)',{exact:false}).setInputFiles('artifacts/photo-scan-review-20260927/native-scan-bundle.json');
  await expect(native.getByRole('heading',{name:'Saved sensor recording — imported provenance',exact:true})).toBeVisible({timeout:20000});
  await native.getByRole('combobox',{name:'Saved frame',exact:true}).selectOption('0');
  await expect(native.getByRole('combobox',{name:'Saved frame',exact:true})).toHaveValue('0');
  await native.getByText('Shared sensor view · recorded returns',{exact:true}).click();
  const view=native.locator('.lidar-point-view');await view.getByRole('checkbox').check();
  await view.locator('svg').scrollIntoViewIfNeeded();const bounds=await view.locator('svg').boundingBox();
  if(!bounds||bounds.height<200)throw Error('Scan is clipped');
  scan={points:await view.locator('circle').count()-1,rays:await view.locator('line').count(),bounds};
  await page.screenshot({path:out+'-shared.png'});
  await native.getByRole('button',{name:'Next saved frame',exact:true}).click();
  await expect(native.getByRole('combobox',{name:'Saved frame',exact:true})).toHaveValue('1');
 }
 await page.screenshot({path:out+'.png'});
 await fs.writeFile(out+'.json',JSON.stringify({classification:'DIAGNOSTIC_CONTINUATION_NOT_FRESH_PASS',setup_open_before:before,setup_open_after:await setup.locator('..').getAttribute('open'),native:await native.locator('summary').first().innerText(),scan},null,2),{flag:'wx'});
 await review.getByRole('button',{name:'Close sensor review',exact:true}).click();
}finally{await browser.close();}
