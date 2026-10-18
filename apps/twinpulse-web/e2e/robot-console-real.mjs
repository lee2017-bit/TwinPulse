// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual React/API; backend transport is injected synthetic data, never SSH.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base = process.env.TWINPULSE_REHEARSAL_URL, bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT, chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Owned loopback required');
const result = { status: 'FAIL', data: 'synthetic_transport_fixture', stages: [], external_requests: 0, engine_commands: 0, page_errors: 0, check_posts: 0 };
let browser, stage = 'bootstrap';
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 1000 } });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) { result.external_requests++; return route.abort(); }
    if (url.pathname === '/v1/product/commands') { result.engine_commands++; return route.abort(); }
    if (url.pathname === '/v1/product/robot/check') result.check_posts++;
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', { exact: true })).toBeVisible({ timeout: 15000 });
  const panel = page.getByRole('region', { name: 'Robot readiness and checks' });
  const prepare = panel.getByRole('button', { name: 'Check PC only', exact: true });
  const start = panel.getByRole('button', { name: 'Connect robot and run bundled check', exact: true });
  await expect(start).toBeEnabled();
  await expect(panel.getByRole('checkbox')).toHaveCount(0);
  expect(result.check_posts).toBe(0);
  await panel.getByText('Check PC only, without robot (optional)', { exact: true }).click();
  await prepare.click();
  await expect(panel.getByText('Existing identity file: Verified', { exact: true })).toBeVisible();
  await expect(start).toBeEnabled(); expect(result.check_posts).toBe(0);
  result.stages.push('optional_PC_check_without_transport_connection_needs_no_extra_checkbox');
  stage = 'read';
  await start.click();
  await expect(start).toBeDisabled(); await expect(prepare).toBeDisabled();
  await expect(panel.getByText(/Collecting connection/)).toBeVisible();
  await expect(panel.getByText(/11.21 V/)).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText(/Result saved/)).toBeVisible();
  expect(result.check_posts).toBe(1);
  await panel.screenshot({ path: path.join(output, 'console-desktop.png') });
  result.stages.push('single_job_progress_normalized_battery_timestamp_saved_no_motion');
  stage = 'reload';
  await page.reload();
  await expect(page.getByText('Backend ready', { exact: true })).toBeVisible();
  await panel.getByRole('button', { name: 'Refresh results', exact: true }).click();
  await expect(panel.getByText(/11.21 V/)).toBeVisible();
  expect(result.check_posts).toBe(1);
  result.stages.push('reload_recovers_observation_without_restarting_transport');
  stage = 'torque_reason';
  await start.click();
  await expect(panel.getByText(/Motor torque is enabled/)).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText(/left 0, right 0/)).toBeVisible();
  await expect(panel.getByText(/Velocity command bytes: all zero/)).toBeVisible();
  await expect(panel.getByText(/Communication port restored: verified/)).toBeVisible();
  await panel.screenshot({ path: path.join(output, 'console-torque-reason.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: path.join(output, 'console-torque-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1366, height: 1000 });
  result.stages.push('torque_only_reason_zero_speeds_next_action_no_automatic_control');
  stage = 'failure';
  await start.click();
  await expect(panel.getByText(/Connection or remote check failed/)).toBeVisible({ timeout: 15000 });
  await expect(panel.getByText(/11.21 V/)).toHaveCount(0);
  await expect(panel.getByText(/Current battery and motor state are unverified/)).toBeVisible();
  await expect(start).toBeEnabled(); expect(result.check_posts).toBe(3);
  result.stages.push('failed_new_read_clears_old_battery_no_automatic_retry');
  stage = 'mobile';
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: path.join(output, 'console-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(result.external_requests).toBe(0); expect(result.engine_commands).toBe(0); expect(result.page_errors).toBe(0);
  result.stages.push('mobile_no_overflow_external_requests_or_engine_commands');
  result.status = 'PASS';
} catch (error) {
  result.failed_stage = stage; result.error_type = error.constructor?.name ?? 'Error';
  result.error_summary = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0, 5).join('\n');
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
