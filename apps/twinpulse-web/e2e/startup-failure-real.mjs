// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Isolated browser check of the real backend after an intentionally absent Isaac import.
import {pathToFileURL} from 'node:url';
const {chromium,expect}=process.env.TWINPULSE_PLAYWRIGHT_MODULE
  ?await import(pathToFileURL(process.env.TWINPULSE_PLAYWRIGHT_MODULE).href)
  :await import('@playwright/test');
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) {
  throw new Error('Owned local failure configuration required');
}
const result = {status: 'FAIL', external_requests: 0, robot_writes: 0,
  engine_commands: 0, page_errors: 0, checks: []};
let browser;
try {
  browser = await chromium.launch({executablePath: chrome, headless: true});
  const context = await browser.newContext({viewport: {width: 1366, height: 900}});
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !['blob:', 'data:'].includes(url.protocol)) {
      result.external_requests++; return route.abort();
    }
    if (url.pathname.startsWith('/v1/product/robot/') && route.request().method() !== 'GET') {
      result.robot_writes++; return route.abort();
    }
    if (url.pathname === '/v1/product/commands') {
      result.engine_commands++; return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByRole('textbox',{name:'Message TwinPulse'})).toBeVisible();
  await page.getByRole('button',{name:/Readiness/}).click();
  await expect(page.getByRole('region',{name:'Runtime checklist'})).toContainText('Launcher: error');
  await expect(page.getByRole('region',{name:'Runtime checklist'})).toContainText('project write');
  await page.getByRole('button',{name:/Readiness/}).click();
  result.checks.push('default_chat_failure_checklist_uses_actual_owned_launcher_status');
  // The remaining checks deliberately exercise the preserved diagnostic
  // interface, not the normal chat-driven demo path.
  await page.getByRole('button',{name:'Projects',exact:true}).click();
  await page.getByRole('button',{name:'Advanced tools',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText: 'Isaac import failed'})).toBeVisible({timeout: 20000});
  await expect(page.getByText('Isaac startup failed · read-only diagnostics')).toBeVisible();
  expect(new URL(page.url()).hash).toBe('');
  const report = await page.evaluate(async () => (await fetch('/v1/product/runtime/diagnostics')).json());
  expect(report.engine_startup?.phase).toBe('isaac_import');
  expect(report.engine_startup?.error_type).toBe('ModuleNotFoundError');
  expect(JSON.stringify(report)).not.toMatch(/site-packages|\\Users\\|private diagnostic detail|my-secret/i);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', {name: 'Save safe diagnostic summary'}).click(),
  ]);
  expect(download.suggestedFilename()).toBe('twinpulse-runtime-diagnostics.json');
  const saved = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
  expect(saved.engine_startup).toEqual(report.engine_startup);
  expect(JSON.stringify(saved)).not.toMatch(/site-packages|\\Users\\|private diagnostic detail|my-secret/i);
  await expect(page.getByRole('button', {name: 'Build scene geometry in Isaac', exact: true})).toHaveCount(0);
  await page.getByLabel('New local project').fill('room_three');
  await expect(page.getByRole('button', {name: 'Create empty project'})).toBeDisabled();
  await page.getByLabel('Instructions (optional)').fill('A test site');
  await expect(page.getByRole('button', {name: 'Create Draft'})).toBeDisabled();
  await page.getByRole('alert').filter({hasText: 'Isaac import failed'}).screenshot({
    path: path.join(output, 'startup-failure-browser.png'),
  });
  await page.setViewportSize({width: 390, height: 844});
  await page.getByRole('alert').filter({hasText: 'Isaac import failed'}).screenshot({
    path: path.join(output, 'startup-failure-mobile.png'),
  });
  result.checks.push('real_backend_read_only_failure_ui_and_downloaded_allowlisted_report');
  await page.getByRole('button', {name: 'Retry startup after stopping this launch'}).click();
  await expect(page.getByText('Retry requested · wait for the new app window')).toBeVisible();
  result.checks.push('browser_one_shot_retry_request_without_scene_or_robot_command');
  expect(result.external_requests).toBe(0);
  expect(result.robot_writes).toBe(0);
  expect(result.engine_commands).toBe(0);
  expect(result.page_errors).toBe(0);
  result.status = 'PASS';
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
