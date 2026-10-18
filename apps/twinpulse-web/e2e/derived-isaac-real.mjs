// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual product UI and production engine bridge. Synthetic geometry only.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base = process.env.TWINPULSE_REHEARSAL_URL, bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT, chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Owned local configuration required');
const result = { status: 'FAIL', data: 'synthetic', stages: [], failure_checks: [], external_requests: 0, commands: [], page_errors: 0 };
let browser, stage = 'bootstrap';
let acquisitions = 0;
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) { result.external_requests++; return route.abort(); }
    if (url.pathname === '/v1/product/commands') {
      const command = route.request().postDataJSON();
      result.commands.push(command.command_type);
      if (command.command_type !== 'build_site_scene' || result.commands.length > 2) return route.abort();
    }
    if (url.pathname === '/v1/product/lease') acquisitions++;
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', { exact: true })).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).hash).toBe('');
  const state = endpoint => page.evaluate(async endpoint => (await fetch(endpoint)).json(), endpoint);
  const workflow = () => state('/v1/product/workflow');
  const product = () => state('/v1/product/state');
  await expect.poll(async () => (await product()).engine_connected, { timeout: 20000 }).toBe(true);
  const original = (await workflow()).site_draft.revision;
  await page.getByRole('button', { name: 'Review Twin', exact: true }).click();
  const review = page.getByRole('region', { name: 'Review the draft', exact: true });
  const build = page.getByRole('button', { name: 'Build scene geometry in Isaac', exact: true });
  await page.getByRole('button', { name: 'Acquire scene control', exact: true }).click();
  await expect.poll(async () => (await product()).lease_owned).toBe(true);
  expect((await product()).operations).toEqual([]);
  expect((await workflow()).acknowledged_revision).toBe(null);
  result.stages.push('explicit_control_acquisition_does_not_build_or_acknowledge');
  async function acknowledgeAndBuild(revision, count) {
    await expect(build).toBeDisabled();
    await review.getByRole('checkbox').click();
    await expect.poll(async () => (await workflow()).acknowledged_revision).toBe(revision);
    await expect(build).toBeEnabled({ timeout: 15000 });
    await build.click();
    await expect.poll(async () => {
      const value = await product();
      return value.operations.filter(item => item.command_type === 'build_site_scene' && item.status === 'succeeded').length;
    }, { timeout: 25000 }).toBe(count);
    await expect(page.getByText('Scene geometry built. Navigation remains unavailable until robot, map and mission validation.', { exact: true })).toBeVisible({ timeout: 15000 });
    expect((await workflow()).site_draft.run_allowed).toBe(false);
  }
  stage = 'source_build';
  await acknowledgeAndBuild(original, 1);
  result.stages.push('source_real_UI_ack_build_bridge_receipt_snapshot_confirmed');
  stage = 'derived_adoption';
  await page.getByText('Scan review · Offline scratch draft', { exact: true }).click();
  await page.getByLabel('Restore offline archive (JSON)').setInputFiles(path.join(output, 'synthetic-archive.json'));
  await expect(page.getByText('SYNTHETIC — unverified saved evidence')).toBeVisible();
  const panel = page.getByRole('region', { name: 'Derived scene selection' });
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Select scratch edits as scene draft', exact: true }).click();
  await expect(page.getByText(/Offline-derived geometry · alignment unverified/)).toBeVisible();
  const selected = await workflow();
  expect(selected.site_draft.revision).not.toBe(original);
  expect(selected.site_draft.original_scene_revision).toBe(original);
  expect(selected.acknowledged_revision).toBe(null);
  stage = 'derived_build';
  await acknowledgeAndBuild(selected.site_draft.revision, 2);
  await review.screenshot({ path: path.join(output, 'combined-desktop.png') });
  result.stages.push('derived_explicit_adoption_new_ack_real_build_UI_confirmation');
  stage = 'run_disabled';
  await page.getByRole('button', { name: 'Simulate', exact: true }).click();
  await expect(page.getByRole('button', { name: '▶ Run', exact: true })).toBeDisabled();
  result.stages.push('scene_only_real_engine_Run_disabled_no_motion_command');
  stage = 'restore';
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Restore saved derived scene for review', exact: true }).click();
  await expect.poll(async () => (await workflow()).acknowledged_revision).toBe(null);
  await expect(build).toBeDisabled();
  expect((await product()).operations).toHaveLength(2);
  result.stages.push('explicit_restore_revokes_ack_without_engine_mutation');
  await page.setViewportSize({ width: 390, height: 844 });
  await review.screenshot({ path: path.join(output, 'combined-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  expect(result.external_requests).toBe(0); expect(result.page_errors).toBe(0);
  expect(result.commands).toEqual(['build_site_scene', 'build_site_scene']);
  result.stages.push('mobile_no_overflow_exactly_two_builds_no_external_requests');
  // Real API/bridge/Isaac remain running; inject browser transport faults only.
  // No extra scene command, engine mutation, Run, robot or synthetic receipt.
  stage = 'failed_state_read';
  await page.setViewportSize({ width: 1366, height: 900 });
  await review.getByRole('checkbox').click();
  await expect(build).toBeEnabled({ timeout: 10000 });
  await context.route('**/v1/product/state', route => route.abort('connectionfailed'));
  await expect(build).toBeDisabled({ timeout: 5000 });
  await expect(page.getByText('Isaac disconnected', { exact: true })).toBeVisible();
  result.failure_checks.push('failed_browser_state_read_discards_cached_engine_authority');
  await context.unroute('**/v1/product/state');
  await expect.poll(async () => (await product()).engine_connected).toBe(true);
  if (!(await product()).lease_owned) {
    await page.getByRole('button', { name: 'Acquire scene control', exact: true }).click();
  }
  await expect(build).toBeEnabled({ timeout: 10000 });
  expect((await product()).operations).toHaveLength(2);
  result.failure_checks.push('state_read_recovery_no_automatic_build');
  stage = 'lease_expiry';
  const acquiredBeforeExpiry = acquisitions;
  await context.route('**/v1/product/lease/renew', route => route.abort('connectionfailed'));
  await expect.poll(async () => (await product()).lease_owned, { timeout: 10000 }).toBe(false);
  await expect(build).toBeDisabled({ timeout: 5000 });
  await expect(page.getByRole('button', { name: 'Acquire scene control', exact: true })).toBeEnabled();
  expect(acquisitions).toBe(acquiredBeforeExpiry);
  expect((await product()).operations).toHaveLength(2);
  await review.screenshot({ path: path.join(output, 'expired-control.png') });
  result.failure_checks.push('real_lease_expiry_disables_build_no_automatic_acquisition');
  stage = 'never_settling_state_read';
  await context.unroute('**/v1/product/lease/renew');
  await page.getByRole('button', { name: 'Acquire scene control', exact: true }).click();
  await expect(build).toBeEnabled({ timeout: 10000 });
  let releaseHeld;
  const held = new Promise(resolve => { releaseHeld = resolve; });
  await context.route('**/v1/product/state', async route => {
    const response = await route.fetch();
    await held; // Old valid response must not revive cached authority after timeout.
    try { await route.fulfill({ response }); } catch { /* request already aborted */ }
  });
  const started = Date.now();
  await expect(build).toBeDisabled({ timeout: 6500 });
  result.state_timeout_observed_ms = Date.now() - started;
  await expect(page.getByText(/Local status did not respond within 3 seconds/)).toBeVisible();
  result.failure_checks.push('never_settling_browser_read_times_out_no_extra_command');
  await context.unroute('**/v1/product/state');
  releaseHeld();
  await expect.poll(async () => (await product()).engine_connected).toBe(true);
  if (!(await product()).lease_owned) await page.getByRole('button', { name: 'Acquire scene control', exact: true }).click();
  await expect(build).toBeEnabled({ timeout: 10000 });
  expect((await product()).operations).toHaveLength(2);
  result.failure_checks.push('post_timeout_recovery_no_automatic_build');
  expect(result.commands).toEqual(['build_site_scene', 'build_site_scene']);
  expect(result.page_errors).toBe(0); expect(result.external_requests).toBe(0);
  result.status = 'PASS';
} catch (error) {
  result.failed_stage = stage; result.error_type = error.constructor?.name ?? 'Error';
  result.error_summary = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0, 7).join('\n');
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
