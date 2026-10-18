// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const result={status:'FAIL',checks:[],samples:[],robot_connections:0,provider_calls:0};
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
let page;
try{
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('response',async response=>{
    if(new URL(response.url()).pathname==='/v1/product/state'){
      try{const state=await response.json();if(state.snapshot)result.samples.push(state.snapshot);}catch{}
    }
  });
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  await expect(page.getByRole('heading',{name:'Run your Twin · SIM only'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
  await page.getByRole('textbox',{name:'SIM start',exact:true}).fill('-.3, -1.2');
  // Decimal input must include an integer digit; the UI must explain the failure.
  await page.getByRole('button',{name:'Preview SIM route',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('explicit x, y');
  await page.getByRole('button',{name:'Dismiss',exact:true}).click();
  await expect(page.getByText('Needs attention',{exact:true})).not.toBeVisible();
  await page.getByRole('textbox',{name:'SIM start',exact:true}).fill('-0.3, -1.2');
  await page.getByRole('textbox',{name:'SIM goal',exact:true}).fill('0.88, -0.05');
  await page.getByRole('button',{name:'Preview SIM route',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
  result.checks.push('Blocked goal surfaces a reason and never enables Run');
  await page.getByRole('button',{name:'Dismiss',exact:true}).click();
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Go to x=-0.3 y=-0.25');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByText(/SIM route ready to the explicit coordinate/)).toBeVisible();
  await expect(page.getByRole('img',{name:'SIM planned route and observed trajectory'})).toBeVisible();
  result.checks.push('Natural coordinate goal uses saved SIM placement, chat journal and route view without auto Run');
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Run simulation',exact:true}).click();
  await expect(page.getByText(/Physics running · goal distance/)).toBeVisible({timeout:45000});
  await expect(page.getByText('SIM navigation · running',{exact:true})).toBeVisible();
  await expect(page.getByText('Burger · simulated',{exact:true})).toBeVisible();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
  await page.screenshot({path:path.join(output,'actual-sim-running.png')});
  await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  await expect(page.getByRole('button',{name:'Stop simulation',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Show Twin',exact:true}).click();
  await expect(page.getByText(/Physics completed · goal distance/)).toBeVisible({timeout:120000});
  await expect(page.getByText('SIM navigation · completed',{exact:true})).toBeVisible();
  result.checks.push('Chat route preview → one Run → actual v2 Build and Burger Physics arrival, with embedded viewer');
  await page.screenshot({path:path.join(output,'actual-sim-arrived.png')});
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Go to the bed');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByText(/SIM route ready to bed/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Run simulation',exact:true}).click();
  await expect(page.getByText(/Physics running · goal distance/)).toBeVisible({timeout:15000});
  await expect(page.getByText(/Physics completed · goal distance/)).toBeVisible({timeout:90000});
  result.object_arrival=result.samples.at(-1);
  result.checks.push('Natural object goal approaches bed exterior from current Physics pose; exact scene and one explicit Run');
  await page.screenshot({path:path.join(output,'actual-chat-object-arrived.png')});
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Go to x=-0.3 y=-1.2');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Run simulation',exact:true}).click();
  await expect(page.getByText(/Physics running · goal distance/)).toBeVisible({timeout:15000});
  await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill('Stop simulation');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByText(/Physics paused · goal distance/)).toBeVisible({timeout:15000});
  await expect(page.getByText('SIM navigation · paused',{exact:true})).toBeVisible();
  const last=result.samples.at(-1);result.stop=last;
  await page.waitForTimeout(1000);
  expect(result.samples.at(-1).position_m).toEqual(last.position_m);
  result.checks.push('Explicit chat Stop uses same SIM pause path; live pose does not advance, Stop button remains available while Twin folded');
  await page.reload();
  await expect(page.getByText(/Physics paused · goal distance/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Run simulation',exact:true})).toBeDisabled();
  result.checks.push('Reload observes paused state; does not restore a route approval or automatically Run');
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  await expect(page.getByRole('button',{name:'Preview SIM route',exact:true})).toBeVisible();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  expect(overflow).toBe(false);
  await page.screenshot({path:path.join(output,'actual-sim-mobile.png')});
  result.page_errors=errors;expect(errors).toEqual([]);result.status='PASS';
}catch(error){result.error=error.message;process.exitCode=1;if(page)await page.screenshot({path:path.join(output,'failed-sim-ui.png')}).catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));await browser.close();}
