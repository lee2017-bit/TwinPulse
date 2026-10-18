// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual React -> authenticated local API; explicitly synthetic, engine absent.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base = process.env.TWINPULSE_REHEARSAL_URL, bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT, chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Owned local configuration required');
const result = { status: 'FAIL', data: 'synthetic', stages: [], external_requests: 0, engine_commands: 0, page_errors: 0 };
let browser, stage = 'bootstrap';
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) { result.external_requests++; return route.abort(); }
    if (url.pathname === '/v1/product/commands') { result.engine_commands++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', { exact: true })).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).hash).toBe('');
  const snapshot = () => page.evaluate(async () => (await fetch('/v1/product/workflow')).json());
  const original = (await snapshot()).site_draft.revision;
  await page.getByText('Scan review · Offline scratch draft', { exact: true }).click();
  await page.getByLabel('Restore offline archive (JSON)').setInputFiles(path.join(output, 'synthetic-archive.json'));
  await expect(page.getByText('SYNTHETIC — unverified saved evidence')).toBeVisible();
  const panel = page.getByRole('region', { name: 'Derived scene selection' });
  const adopt = panel.getByRole('button', { name: 'Select scratch edits as scene draft', exact: true });
  await expect(adopt).toBeDisabled();
  result.stages.push('real_bootstrap_original_selected_archive_restored_no_adoption');
  stage = 'explicit_adoption';
  await panel.getByRole('checkbox').check(); await adopt.click();
  await expect(page.getByText(/Offline-derived geometry · alignment unverified/)).toBeVisible();
  const selected = await snapshot();
  expect(selected.site_draft.revision).not.toBe(original);
  expect(selected.site_draft.original_scene_revision).toBe(original);
  expect(selected.acknowledged_revision).toBe(null);
  expect(selected.build_allowed).toBe(false); expect(selected.site_draft.run_allowed).toBe(false);
  await page.getByRole('button', { name: 'Build scene geometry in Isaac', exact: true }).isDisabled().then(value => expect(value).toBe(true));
  result.stages.push('adopt_persisted_derived_requires_new_ack_no_build_or_run');
  await page.getByRole('region', { name: 'Review the draft', exact: true }).screenshot({ path: path.join(output, 'derived-desktop.png') });
  stage = 'new_ack';
  const review = page.getByRole('region', { name: 'Review the draft', exact: true });
  await review.getByRole('checkbox').click();
  await expect.poll(async () => (await snapshot()).acknowledged_revision).toBe(selected.site_draft.revision);
  expect((await snapshot()).build_allowed).toBe(false); // engine absent
  result.stages.push('new_ack_does_not_supply_engine_capability_or_lease');
  stage = 'explicit_restore';
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button', { name: 'Restore saved derived scene for review', exact: true }).click();
  await expect.poll(async () => (await snapshot()).acknowledged_revision).toBe(null);
  expect((await snapshot()).site_draft.revision).toBe(selected.site_draft.revision);
  result.stages.push('explicit_restore_keeps_derived_identity_but_clears_ack');
  stage = 'mobile';
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: path.join(output, 'derived-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const product = await page.evaluate(async () => (await fetch('/v1/product/state')).json());
  expect(product.operations).toEqual([]); expect(product.lease_owned).toBe(false);
  expect(result.external_requests).toBe(0); expect(result.engine_commands).toBe(0); expect(result.page_errors).toBe(0);
  result.stages.push('mobile_no_overflow_no_external_calls_no_engine_commands');
  result.status = 'PASS';
} catch (error) {
  result.failed_stage = stage; result.error_type = error.constructor?.name ?? 'Error';
  result.error_summary = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0, 5).join('\n');
}
finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
