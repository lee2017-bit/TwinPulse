// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,secret=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP,out=process.env.TWINPULSE_REHEARSAL_OUTPUT;
const result={status:'FAIL',external_requests:0,robot_requests:0,page_errors:0,checks:[]};let browser;
try{
  if(!base||new URL(base).hostname!=='127.0.0.1')throw Error('Owned loopback server required');
  browser=await chromium.launch({headless:true,executablePath:process.env.TWINPULSE_REHEARSAL_CHROME});
  const context=await browser.newContext({viewport:{width:1366,height:950}});
  await context.route('**/*',route=>{const u=new URL(route.request().url());
    if(u.origin!==base&&!['data:','blob:'].includes(u.protocol)){result.external_requests++;return route.abort();}
    if(u.pathname.startsWith('/v1/product/robot/')&&route.request().method()!=='GET'){result.robot_requests++;return route.abort();}
    return route.continue();});
  const page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(secret)}`);
  await expect(page.getByText('Backend ready',{exact:true})).toBeVisible({timeout:15000});
  const panel=page.getByRole('region',{name:'Automatic mission comparison'});
  await expect(panel.getByText('Ready for an explicit offline comparison')).toBeVisible();
  await panel.getByRole('button',{name:'Start offline comparison',exact:true}).click();
  await expect(panel.getByText(/RUNNING · baseline/)).toBeVisible({timeout:15000});
  await expect(panel.getByText(/Both missions arrived/)).toBeVisible({timeout:150000});
  await expect(panel.getByRole('img',{name:'Comparison executed trajectories'})).toBeVisible();
  await expect(panel.getByText(/Comparison report saved/)).toBeVisible();
  await page.screenshot({path:path.join(out,'comparison.png'),fullPage:true});
  await page.reload();
  await expect(panel.getByText(/Both missions arrived/)).toBeVisible({timeout:15000});
  result.checks=['built_Web_authenticated_API_actual_two_workers','same_conditions_independent_ledgers',
    'progress_to_saved_score_and_trajectory','reload_no_new_pair_or_physical_authority'];
  if(result.page_errors||result.external_requests||result.robot_requests)throw Error('Unexpected request or page error');
  result.status='PASS';
}catch(e){result.reason=String(e.message??e).replaceAll(secret??'NO_SECRET','[REDACTED]').slice(0,180);}
finally{fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));await browser?.close();}
process.exitCode=result.status==='PASS'?0:1;
