// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real React + authenticated loopback API; injected collector is synthetic and cannot SSH.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Owned loopback required');
const result = { status:'FAIL', data:'synthetic_transport_fixture', stages:[], check_posts:0, external_requests:0, engine_commands:0, physical_starts:0, page_errors:0 };
let browser, page, stage = 'start';
try {
  browser = await chromium.launch({ executablePath:chrome, headless:true });
  const context = await browser.newContext({ viewport:{width:1366,height:900} });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:','data:'].includes(url.protocol)) { result.external_requests++; return route.abort(); }
    if (url.pathname === '/v1/product/commands') { result.engine_commands++; return route.abort(); }
    if (url.pathname === '/v1/product/robot/check') result.check_posts++;
    if (url.pathname === '/v1/product/robot/physical/start') { result.physical_starts++; return route.abort(); }
    return route.continue();
  });
  page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#robot-console=1&bootstrap=${encodeURIComponent(bootstrap)}`);
  const status = page.getByRole('region',{name:'Robot connection status'});
  stage = 'auto_read';
  await expect(status.getByText('Connected — status received')).toBeVisible({timeout:15000});
  expect(result.check_posts).toBe(1);
  const controller = page.getByRole('region',{name:'Physical controller'});
  await expect(controller).toBeVisible();
  await expect(controller.getByRole('button',{name:'Drive joystick'})).toBeDisabled();
  expect(result.physical_starts).toBe(0);
  result.stages.push('one_automatic_read_only_check_without_isaac_or_motion');
  await page.screenshot({path:path.join(output,'quick-console-success.png'),fullPage:true});
  stage = 'attention';
  await status.getByRole('button',{name:'Check again'}).click();
  await expect(status.getByText('Connected — review robot status')).toBeVisible({timeout:15000});
  await expect(controller.getByRole('button',{name:'Drive joystick'})).toBeDisabled();
  expect(result.check_posts).toBe(2);
  result.stages.push('new_attention_observation_keeps_motion_locked');
  stage = 'failure';
  await status.getByRole('button',{name:'Check again'}).click();
  await expect(status.getByText(/Connection or remote check failed/)).toBeVisible({timeout:15000});
  await expect(controller).toHaveCount(0);
  expect(result.check_posts).toBe(3);
  await expect(status.getByRole('button',{name:'Retry connection'})).toBeEnabled();
  result.stages.push('failure_shows_reason_and_retry_without_auto_repeated_job');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(output,'quick-console-failure-mobile.png'),fullPage:true});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  expect(result.external_requests).toBe(0);
  expect(result.engine_commands).toBe(0);
  expect(result.physical_starts).toBe(0);
  expect(result.page_errors).toBe(0);
  result.stages.push('mobile_no_overflow_and_no_external_or_physical_commands');
  result.status = 'PASS';
} catch(error) {
  result.failed_stage = stage;
  result.error_type = error.constructor?.name ?? 'Error';
  result.error_summary = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0,5).join('\n');
  if (page) result.visible_text = (await page.locator('body').innerText()).slice(0,500);
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
