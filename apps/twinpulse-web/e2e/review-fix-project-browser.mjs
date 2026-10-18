// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real Chrome and local API; injected first creation failure, no engine or robot.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) {
  throw new Error('Owned local configuration required');
}
const result = {status: 'FAIL', step: 'bootstrap', checks: [], external_requests: 0,
  robot_requests: 0, create_requests: [], page_errors: 0};
let browser;
try {
  browser = await chromium.launch({executablePath: chrome, headless: true});
  const context = await browser.newContext({viewport: {width: 1366, height: 900}});
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) {
      result.external_requests++;
      return route.abort();
    }
    if (url.pathname.startsWith('/v1/product/robot/') && route.request().method() !== 'GET') {
      result.robot_requests++;
      return route.abort();
    }
    if (url.pathname === '/v1/product/projects/create-bedroom' && route.request().method() === 'POST') {
      result.create_requests.push(route.request().postDataJSON());
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
  const panel = page.getByRole('region', {name: 'Local projects'});
  await expect(panel).toBeVisible();
  result.step = 'create_failure';
  await panel.getByLabel('New local project').fill('retry_room');
  await panel.getByLabel('Project source').selectOption('preserved_bedroom');
  await panel.getByRole('button', {name: 'Create bedroom project'}).click();
  await expect(panel.getByRole('button', {name: 'Retry bedroom creation'})).toBeVisible();
  expect(result.create_requests).toHaveLength(1);
  result.checks.push('failed_copy_leaves_same_name_retry_visible');

  result.step = 'retry';
  await panel.getByRole('button', {name: 'Retry bedroom creation'}).click();
  await expect(panel.getByText(/Created retry_room/)).toBeVisible({timeout: 30000});
  expect(result.create_requests).toHaveLength(2);
  expect(result.create_requests[0].request_id).toBe(result.create_requests[1].request_id);
  expect(result.create_requests[0].project_id).toBe('retry_room');
  await expect(panel.getByText(/retry_room · review_required/)).toBeVisible();
  result.checks.push('same_request_id_retries_and_publishes_reviewable_project');

  result.step = 'legacy_recovery';
  await panel.getByRole('button', {name: 'Preserve incomplete original and recreate partial_room'}).click();
  await expect(panel.getByText(/Created partial_room/)).toBeVisible({timeout: 30000});
  await expect(panel.getByText(/partial_room · review_required/)).toBeVisible();
  result.checks.push('explicit_legacy_recovery_preserves_original_and_lists_complete_project');
  expect(result.page_errors).toBe(0);
  expect(result.external_requests).toBe(0);
  expect(result.robot_requests).toBe(0);
  await panel.screenshot({path: path.join(output, 'project-recovery-browser.png')});
  result.status = 'PASS';
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  // Never save bootstrap credentials or full request payloads from the page.
  result.create_requests = result.create_requests.map(item => ({project_id: item.project_id,
    request_id_same_as_first: item.request_id === result.create_requests[0]?.request_id}));
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
