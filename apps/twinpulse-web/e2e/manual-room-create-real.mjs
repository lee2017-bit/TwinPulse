// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual local Chrome/App/API creation with a synthetic image and a fake-ready launcher.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
const furnitureScenario = process.env.TWINPULSE_REHEARSAL_FURNITURE === '1';
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) {
  throw new Error('Owned local configuration required');
}
const result = {status: 'FAIL', step: 'bootstrap', external_requests: 0, robot_mutations: 0,
  scene_commands: 0, page_errors: 0};
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
      result.robot_mutations++;
      return route.abort();
    }
    if (url.pathname === '/v1/product/commands') {
      result.scene_commands++;
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
  result.step = 'manual-room-create';
  await page.getByLabel('New local project').fill('photo_room_two');
  await page.getByLabel('Project source').selectOption('manual_photo');
  await page.getByLabel('Room photo').setInputFiles(path.join(output, 'synthetic-room.png'));
  await page.getByLabel('Width (m)').fill('3.6');
  await page.getByLabel('Length (m)').fill('5.2');
  await page.getByLabel('Wall height (m)').fill('2.6');
  await page.getByLabel('Source note').fill('User-entered dimensions; synthetic photo retained, not interpreted');
  await page.getByLabel('Include pinned Burger visual').check();
  if (furnitureScenario) {
    await page.getByRole('button', {name: 'Add furniture preset'}).click();
    await page.locator('#furniture-kind-0').selectOption('bed');
    await page.locator('#furniture-x-0').fill('-0.9');
    await page.locator('#furniture-y-0').fill('0.8');
    await page.getByRole('button', {name: 'Add furniture preset'}).click();
    await page.locator('#furniture-kind-1').selectOption('desk');
    await page.locator('#furniture-x-1').fill('0.9');
    await page.locator('#furniture-y-1').fill('0.8');
  }
  await page.getByRole('button', {name: 'Create photo room'}).click();
  await expect(page.getByText('photo_room_two · review_required')).toBeVisible({timeout: 20000});
  await expect(page.getByText(/Created photo_room_two\. Current project remains default/)).toBeVisible();
  expect(result.external_requests).toBe(0);
  expect(result.robot_mutations).toBe(0);
  expect(result.scene_commands).toBe(0);
  expect(result.page_errors).toBe(0);
  await page.locator('.project-panel').screenshot({path: path.join(output, 'manual-room-create.png')});
  result.status = 'PASS';
  result.furniture_scenario = furnitureScenario;
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
