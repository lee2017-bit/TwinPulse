// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual local browser + owned backend/Isaac project switch; no motion or provider.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
const phase = process.env.TWINPULSE_SWITCH_PHASE;
const injectCreateFailure = process.env.TWINPULSE_SWITCH_INJECT_CREATE_FAILURE === '1';
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome ||
    !['create_switch', 'reopen'].includes(phase)) throw new Error('Owned local switch configuration required');

const result = {status: 'FAIL', phase, checks: [], external_requests: 0,
  robot_requests: 0, engine_commands: 0, page_errors: 0, create_requests: [], create_statuses: []};
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
      result.robot_requests++; return route.abort();
    }
    if (url.pathname === '/v1/product/commands') {
      result.engine_commands++; return route.abort();
    }
    if (url.pathname === '/v1/product/projects/create-bedroom' && route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      result.create_requests.push({project_id: body.project_id, request_id: body.request_id});
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  page.on('response', response => {
    if (new URL(response.url()).pathname === '/v1/product/projects/create-bedroom') {
      result.create_statuses.push(response.status());
    }
  });
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
  expect(new URL(page.url()).hash).toBe('');
  const project = page.getByRole('region', {name: 'Local projects'});
  if (phase === 'create_switch') {
    await expect(project.getByRole('heading', {name: 'Project · default'})).toBeVisible();
    await project.getByLabel('New local project').fill('room_two');
    await project.getByLabel('Project source').selectOption('preserved_bedroom');
    await project.getByRole('button', {name: 'Create bedroom project'}).click();
    if (injectCreateFailure) {
      await expect(project.getByRole('button', {name: 'Retry bedroom creation'})).toBeVisible({timeout: 15000});
      await expect.poll(() => result.create_statuses[0], {timeout: 15000}).toBe(409);
      fs.writeFileSync(path.join(output, 'release-create-lock-request'), '1');
      await expect.poll(() => fs.existsSync(path.join(output, 'create-lock-released')),
        {timeout: 15000}).toBe(true);
      await project.getByRole('button', {name: 'Retry bedroom creation'}).click();
      await expect.poll(() => result.create_requests.length, {timeout: 15000}).toBe(2);
      await expect.poll(() => result.create_statuses[1], {timeout: 15000}).toBe(201);
      expect(result.create_requests[0].request_id).toBe(result.create_requests[1].request_id);
      expect(result.create_requests[0].project_id).toBe('room_two');
      result.checks.push('first_create_lock_conflict_then_same_request_id_retry');
    }
    await expect(project.getByText('Created room_two.', {exact: false})).toBeVisible({timeout: 15000});
    await project.getByRole('button', {name: 'Open room_two in a new session'}).click();
    await expect(project.getByText('Opening room_two.', {exact: false})).toBeVisible({timeout: 15000});
    result.checks.push('browser_created_preserved_bedroom_project_without_switching_in_place',
      'browser_requested_owned_new_session');
  } else {
    await expect(project.getByRole('heading', {name: 'Project · room_two'})).toBeVisible();
    const response = await page.evaluate(async () => (await fetch('/v1/product/workflow')).json());
    expect(response.phase).toBe('restore_review_required');
    expect(response.build_allowed).toBe(false);
    await expect(page.getByRole('button', {name: 'Build scene geometry in Isaac', exact: true})).toHaveCount(0);
    await page.getByRole('button', {name: 'Open saved scene for review', exact: true}).click();
    await expect(page.getByRole('button', {name: 'Build scene geometry in Isaac', exact: true})).toBeDisabled();
    result.checks.push('browser_reopened_saved_room_with_explicit_review_and_without_build_approval');
  }
  expect(result.external_requests).toBe(0);
  expect(result.robot_requests).toBe(0);
  expect(result.engine_commands).toBe(0);
  expect(result.page_errors).toBe(0);
  result.status = 'PASS';
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  result.create_requests = result.create_requests.map((item, index) => ({
    project_id: item.project_id, same_request_id_as_first: index === 0 ||
      item.request_id === result.create_requests[0]?.request_id,
  }));
  fs.writeFileSync(path.join(output, `browser-${phase}.json`), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
