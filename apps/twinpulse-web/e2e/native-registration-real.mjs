// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Synthetic correspondence math through actual React/loopback backend, no engine.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) throw new Error('Local owned rehearsal required');
const reference = JSON.parse(fs.readFileSync(path.join(output, 'reference.json'), 'utf8'));
const result = { status: 'FAIL', data: 'synthetic_test_fixture', stages: [], external_requests: 0,
  page_errors: 0, engine_commands: 0, physical_validation: 'NOT_RUN' };
let browser, currentStage = 'startup';
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
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
  await page.getByText('Native scan · Saved photo review', { exact: true }).click();
  const panel = page.locator('.native-review');
  const input = page.getByLabel('Import native scan bundle (JSON)');
  await input.setInputFiles(path.join(output, 'native-scan-bundle.json'));
  await expect(page.getByText('SYNTHETIC native fixture', { exact: true })).toBeVisible();
  await page.getByText('Coordinate correspondence review (optional, not calibration)', { exact: true }).click();
  await expect(panel.getByText(/No reference proposal for this frame/)).toBeVisible();
  result.stages.push('explicit_synthetic_import_unverified_without_reference');
  currentStage = 'reference_fit';
  const refInput = page.getByLabel('Import coordinate reference JSON');
  await refInput.setInputFiles(path.join(output, 'reference.json'));
  await expect(panel.getByText('Reference fit: UNIQUE_CANDIDATE', { exact: true })).toBeVisible();
  await expect(panel.getByText('SYNTHETIC reference — math test only.', { exact: true })).toBeVisible();
  const state = await page.evaluate(async () => (await fetch('/v1/product/native-scan')).json());
  expect(state.registration.candidate_native_y_sign).toBe(-1);
  expect(state.registration.world_alignment_verified).toBe(false);
  expect(state.world_tf).toBe(null);
  expect(state.motion_authorized).toBe(false);
  result.stages.push('synthetic_reflection_convention_separate_from_proper_rotation');
  await panel.locator('.native-registration').screenshot({ path: path.join(output, 'reference-desktop.png') });
  currentStage = 'bad_reference';
  const bad = { ...reference, reference_kind: 'photo_guess' };
  await refInput.setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bad)) });
  await expect(panel.getByRole('alert')).toBeVisible();
  const kept = await page.evaluate(async () => (await fetch('/v1/product/native-scan')).json());
  expect(kept.registration.proposal_digest).toBe(state.registration.proposal_digest);
  expect(kept.workspace_revision).toBe(state.workspace_revision);
  result.stages.push('photo_guess_rejected_prior_evidence_preserved');
  currentStage = 'mobile_reset';
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.locator('.native-registration').screenshot({ path: path.join(output, 'reference-mobile.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await input.setInputFiles(path.join(output, 'native-scan-bundle.json'));
  await expect(panel.getByText(/No reference proposal for this frame/)).toBeVisible();
  const product = await page.evaluate(async () => (await fetch('/v1/product/state')).json());
  expect(product.operations).toEqual([]); expect(product.lease_owned).toBe(false);
  expect(result.external_requests).toBe(0); expect(result.page_errors).toBe(0); expect(result.engine_commands).toBe(0);
  result.stages.push('mobile_no_overflow_reimport_clears_proposal_no_commands');
  result.status = 'PASS';
} catch (error) {
  result.failed_stage = currentStage;
  result.error_type = error.constructor?.name ?? 'Error';
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
