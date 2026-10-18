// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base = process.env.TWINPULSE_REHEARSAL_URL, bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT, chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Owned loopback required');
const result = { status: 'FAIL', data: 'PC_REHEARSAL_ONLY', stages: [], external_requests: 0, robot_requests: 0, engine_commands: 0, page_errors: 0 };
let browser, stage = 'bootstrap', drop = false;
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 1000 } });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) { result.external_requests++; return route.abort(); }
    if (url.pathname === '/v1/product/commands') { result.engine_commands++; return route.abort(); }
    if (url.pathname === '/v1/product/robot/check') { result.robot_requests++; return route.abort(); }
    if (drop && url.pathname.endsWith('/controller/input')) return route.abort();
    return route.continue();
  });
  const page = await context.newPage(); page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', { exact: true })).toBeVisible({ timeout: 15000 });
  const panel = page.getByRole('region', { name: 'Virtual controller' });
  const state = () => page.evaluate(async () => (await fetch('/v1/product/robot/controller')).json());
  await expect(panel.getByText(/Physical control locked/)).toBeVisible();
  await expect(panel.getByText('↑ Forward', { exact: true })).toBeDisabled();
  await panel.screenshot({ path: path.join(output, 'physical-locked.png') });
  result.stages.push('physical_controls_locked_no_auto_activation');
  await panel.getByRole('button', { name: 'PC rehearsal', exact: true }).click();
  const arm = async () => {
    await panel.getByRole('checkbox').check();
    await panel.getByText('Prepare rehearsal controls', { exact: true }).click();
    await expect(panel.getByText('↑ Forward', { exact: true })).toBeEnabled();
  };
  await arm(); stage = 'four_directions';
  for (const [label, field, value] of [['↑ Forward', 'linear_m_s', .03], ['↓ Backward', 'linear_m_s', -.03], ['↶ Turn left', 'angular_rad_s', .2], ['↷ Turn right', 'angular_rad_s', -.2]]) {
    await panel.getByText(label, { exact: true }).hover(); await page.mouse.down();
    await expect.poll(async () => (await state())[field]).toBe(value);
    await page.mouse.up();
    await expect.poll(async () => (await state())[field]).toBe(0);
  }
  result.stages.push('four_pointer_directions_and_release_zero');
  stage = 'lidar';
  await panel.getByText('Start lidar · 8-second simulation', { exact: true }).click();
  await expect.poll(async () => (await state()).lidar_running).toBe(true);
  await panel.getByText('Stop simulated lidar', { exact: true }).click();
  await expect.poll(async () => (await state()).lidar_running).toBe(false);
  await panel.getByText('Start lidar · 8-second simulation', { exact: true }).click();
  await expect.poll(async () => (await state()).lidar_running, { timeout: 10000 }).toBe(false);
  result.stages.push('lidar_manual_stop_and_eight_second_auto_stop');
  stage = 'blur';
  await panel.focus(); await page.keyboard.down('w');
  await expect.poll(async () => (await state()).linear_m_s).toBe(.03);
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await page.keyboard.up('w');
  await expect.poll(async () => (await state()).armed).toBe(false);
  result.stages.push('keyboard_window_blur_stops_and_disarms');
  await arm(); stage = 'lost_transport';
  await panel.getByText('↑ Forward', { exact: true }).hover(); await page.mouse.down();
  await expect.poll(async () => (await state()).linear_m_s).toBe(.03);
  drop = true;
  await expect.poll(async () => (await state()).armed, { timeout: 3000 }).toBe(false);
  expect((await state()).linear_m_s).toBe(0);
  await expect(panel.getByText('Synthetic velocity: 0.00 m/s · 0.00 rad/s', { exact: true })).toBeVisible();
  await page.mouse.up(); drop = false;
  result.stages.push('lost_input_backend_deadline_stops_without_stop_request');
  stage = 'mobile';
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: path.join(output, 'controller-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const final = await state(); expect(final.physical_motion_authorized).toBe(false); expect(final.physical_lidar_authorized).toBe(false);
  expect(result.external_requests).toBe(0); expect(result.engine_commands).toBe(0); expect(result.robot_requests).toBe(0); expect(result.page_errors).toBe(0);
  result.stages.push('mobile_zero_robot_or_engine_calls_physical_gate_unchanged');
  result.status = 'PASS';
} catch (error) {
  result.failed_stage = stage; result.error_type = error.constructor?.name ?? 'Error';
  result.error_summary = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0, 6).join('\n');
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
