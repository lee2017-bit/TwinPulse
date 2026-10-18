// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real Chrome + local fake process. Changing the local launcher status file is
// coordinated by the Python owner; no robot network is contacted.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
const explicitStop = process.env.TWINPULSE_STOP_EXPLICIT_ACTION || '';
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) {
  throw new Error('Owned local configuration required');
}
if (!['', 'finish_stop', 'force_stop', 'escape'].includes(explicitStop)) throw new Error('Invalid stop fixture');
const result = {status: 'FAIL', step: 'bootstrap', checks: [], actions_after_error: [],
  external_requests: 0, page_errors: 0, explicit_stop: explicitStop || null,
  explicit_stop_response: null};
let browser;
let afterError = false;
let freezeVisibleRuntime = false;
let readyRuntime = null;
let activePhysicalState = null;
try {
  browser = await chromium.launch({executablePath: chrome, headless: true});
  const page = await browser.newPage({viewport: {width: 1366, height: 900}});
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) {
      result.external_requests++;
      return route.abort();
    }
    if (afterError && url.pathname === '/v1/product/robot/physical/input') {
      const action = route.request().postDataJSON().action;
      result.actions_after_error.push(action);
      if (explicitStop && action === 'watch') {
        // An in-flight watch can fail on the new runtime gate and auto-close
        // before a human can click. Keep only that test heartbeat at its
        // previous fake snapshot; the actual stop action still reaches API.
        return route.fulfill({status: 200, contentType: 'application/json',
          body: JSON.stringify(activePhysicalState)});
      }
      const expected = explicitStop === 'escape' ? 'force_stop' : explicitStop;
      if (expected && action === expected) {
        const response = await route.fetch();
        const body = await response.json();
        result.explicit_stop_response = {http_status: response.status(),
          state: body.state, busy: body.busy, stop_request: body.stop_request};
        return route.fulfill({response});
      }
    }
    if (freezeVisibleRuntime && url.pathname === '/v1/product/runtime' && route.request().method() === 'GET') {
      return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(readyRuntime)});
    }
    return route.continue();
  });
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
  const panel = page.getByRole('region', {name: 'Physical controller'});
  const state = () => page.evaluate(async () => (await fetch('/v1/product/robot/physical')).json());
  const begin = async name => {
    await panel.getByRole('checkbox').check();
    await panel.getByRole('button', {name, exact: true}).click();
  };
  result.step = 'qualify';
  await begin('2. Prepare stop test');
  await expect(panel.getByRole('button', {name: 'Execute stop test · short physical forward motion'})).toBeEnabled();
  await panel.getByRole('button', {name: 'Execute stop test · short physical forward motion'}).click();
  await expect.poll(async () => (await state()).busy, {timeout: 25000}).toBe(false);
  expect((await state()).result).toBe('QUALIFIED');
  result.step = 'active_control';
  await begin('3. Connect manual control');
  await expect(panel.getByText('↑ Forward', {exact: true})).toBeEnabled({timeout: 10000});
  activePhysicalState = await state();
  expect(activePhysicalState.busy).toBe(true);
  result.checks.push('fake_owned_control_active_before_engine_error');
  if (explicitStop) {
    readyRuntime = await (await page.request.get(`${base}/v1/product/runtime`)).json();
    expect(readyRuntime.status).toBe('ready');
    // Model a stale visible launcher status while the backend has already
    // entered error. This keeps the stop UI available without weakening the
    // product's normal automatic close-on-error behavior.
    freezeVisibleRuntime = true;
  }
  afterError = true;
  fs.writeFileSync(path.join(output, 'inject-runtime-error-now'), '1');
  result.step = 'engine_error';
  await expect.poll(async () => (await (await page.request.get(`${base}/v1/product/runtime`)).json()).status,
    {timeout: 15000}).toBe('error');
  if (explicitStop) {
    result.step = `explicit_${explicitStop}`;
    if (explicitStop === 'escape') {
      await panel.focus();
      await page.keyboard.press('Escape');
    } else {
      await panel.getByRole('button', {name: explicitStop === 'finish_stop' ?
        'Stop after current command' : 'Force STOP · Esc'}).click({timeout: 5000});
    }
    const expectedAction = explicitStop === 'escape' ? 'force_stop' : explicitStop;
    await expect.poll(() => result.actions_after_error.includes(expectedAction), {timeout: 15000}).toBe(true);
    await expect.poll(() => result.explicit_stop_response?.http_status, {timeout: 15000}).toBe(200);
    expect(result.explicit_stop_response.stop_request).toBe(expectedAction);
    result.checks.push(`explicit_${expectedAction}_reached_owned_fake_after_backend_error`);
    freezeVisibleRuntime = false;
  }
  await expect(panel.getByText('↑ Forward', {exact: true})).toBeDisabled({timeout: 10000});
  await expect(panel.getByRole('button', {name: 'Force STOP · Esc'})).toBeEnabled();
  await expect.poll(async () => (await state()).busy, {timeout: 25000}).toBe(false);
  if (!explicitStop) expect(result.actions_after_error).toContain('close');
  // The marker precedes the server status-file update, so one pre-error watch
  // may race with it. No directional motion is allowed after the marker.
  expect(result.actions_after_error.every(action => ['watch', 'close', 'finish_stop', 'force_stop', 'stop'].includes(action))).toBe(true);
  result.checks.push('engine_error_ui_disables_motion_and_delivers_owned_close');
  expect(result.page_errors).toBe(0);
  expect(result.external_requests).toBe(0);
  await panel.screenshot({path: path.join(output, 'stop-after-engine-error.png')});
  result.status = 'PASS';
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
