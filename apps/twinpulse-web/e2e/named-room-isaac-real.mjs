// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Isolated actual browser/API/bridge/Isaac check for a synthetic named room.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
const expectedProject = process.env.TWINPULSE_REHEARSAL_PROJECT ?? 'room_one';
if (!base || new URL(base).hostname !== '127.0.0.1' || !bootstrap || !output || !chrome) {
  throw new Error('Owned local configuration required');
}
const result = {status: 'FAIL', step: 'bootstrap', checks: [], external_requests: 0,
  robot_requests: 0, commands: [], page_errors: 0};
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
    if (url.pathname.startsWith('/v1/product/robot/')) {
      result.robot_requests++;
      return route.abort();
    }
    if (url.pathname === '/v1/product/commands') {
      const command = route.request().postDataJSON();
      result.commands.push(command.command_type);
      if (command.command_type !== 'build_site_scene' || result.commands.length > 1) return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
  expect(new URL(page.url()).hash).toBe('');
  const get = endpoint => page.evaluate(async endpoint => (await fetch(endpoint)).json(), endpoint);
  const product = () => get('/v1/product/state');
  const workflow = () => get('/v1/product/workflow');
  await expect.poll(async () => (await product()).engine_connected, {timeout: 30000}).toBe(true);
  expect((await product()).project_id).toBe(expectedProject);
  expect((await workflow()).phase).toBe('restore_review_required');
  expect((await product()).operations).toHaveLength(0);
  result.checks.push('saved_project_reopened_without_restored_authority');

  result.step = 'continue';
  await page.getByRole('button', {name: 'Open saved scene for review', exact: true}).click();
  if (process.env.TWINPULSE_REHEARSAL_REATTACH === '1') {
    await expect(page.getByText('Original archive missing', {exact: true})).toBeVisible();
    const reattach = page.getByRole('button', {name: 'Reattach identical source and open review', exact: true});
    if (process.env.TWINPULSE_REHEARSAL_WRONG_PHOTO_FILE) {
      await page.locator('section[aria-labelledby="build-title"] input[accept="image/png,image/jpeg,image/webp"]').setInputFiles(process.env.TWINPULSE_REHEARSAL_WRONG_PHOTO_FILE);
      await reattach.click();
      await expect.poll(async () => (await workflow()).phase).toBe('restore_review_required');
      result.checks.push('different_photo_rejected_without_promoting_review');
    }
    if (process.env.TWINPULSE_REHEARSAL_PHOTO_FILE) {
      await page.locator('section[aria-labelledby="build-title"] input[accept="image/png,image/jpeg,image/webp"]').setInputFiles(process.env.TWINPULSE_REHEARSAL_PHOTO_FILE);
    }
    await reattach.click();
    result.checks.push('missing_original_restored_by_explicit_matching_source');
  }
  await expect.poll(async () => (await workflow()).phase).toBe('draft_ready');
  const state = await workflow();
  expect(state.acknowledged_revision).toBe(null);
  expect(state.build_allowed).toBe(false);
  expect(state.site_draft.review_provenance.source_class).toBe('local_recipe');
  expect(state.site_draft.review_provenance.photo_interpretation_evidence).toBe('local_import_not_performed');
  if (process.env.TWINPULSE_REHEARSAL_ENVIRONMENT === 'warehouse') {
    expect(state.site_draft.editable_calls.map(call => call.tool)).toEqual(
      ['create_rack_row', 'create_rack_row']);
    expect(state.site_draft.object_count).toBeGreaterThan(4);
    expect(state.site_draft.robot_profile_id).toBe(null);
    expect(state.site_draft.mission_id).toBe(null);
    result.checks.push('synthetic_warehouse_reviewed_without_robot_mission_or_photo_inference');
  }
  await expect(page.getByRole('region', {name: 'Scene source and validation scope'}))
    .toContainText('TwinPulse did not analyze the photo or call a model during this import');
  result.checks.push('explicit_continue_only_reviews_saved_room');
  result.checks.push('reviewed_local_recipe_source_without_photo_or_model_claim');

  if (process.env.TWINPULSE_REHEARSAL_EDIT_SCENE === '1') {
    result.step = 'scene-edit';
    const sceneEditor = page.locator('.scene-edit-review');
    await sceneEditor.getByLabel('Object ID').fill('sofa');
    await sceneEditor.getByLabel('X (m)').fill('0.3');
    await sceneEditor.getByLabel('Y (m)').fill('0.2');
    await sceneEditor.getByRole('button', {name: 'Preview change'}).click();
    await expect(sceneEditor.getByText(/existing objects unchanged/)).toBeVisible();
    await sceneEditor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(1);
    await sceneEditor.getByLabel('Change box').check();
    await sceneEditor.getByLabel('Existing box call').selectOption({index: 1});
    await sceneEditor.getByLabel('X (m)').fill('-0.5');
    await sceneEditor.getByRole('button', {name: 'Preview change'}).click();
    await expect(sceneEditor.getByText(/existing objects unchanged/)).toBeVisible();
    await sceneEditor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(2);
    await sceneEditor.getByLabel('Undo last edit').check();
    await sceneEditor.getByRole('button', {name: 'Preview change'}).click();
    await expect(sceneEditor.getByText(/existing objects unchanged/)).toBeVisible();
    await sceneEditor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(3);
    await sceneEditor.getByLabel('Change box').check();
    await sceneEditor.getByLabel('Existing box call').selectOption({index: 1});
    await sceneEditor.getByLabel('X (m)').fill('-0.4');
    await sceneEditor.getByRole('button', {name: 'Preview change'}).click();
    await expect(sceneEditor.getByText(/existing objects unchanged/)).toBeVisible();
    await sceneEditor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(4);
    const edited = await workflow();
    expect(edited.site_draft.revision).not.toBe(edited.site_draft.original_scene_revision);
    expect(edited.acknowledged_revision).toBe(null);
    result.checks.push('browser_add_change_undo_change_again_preserves_original_and_requires_new_review');
  }

  if (process.env.TWINPULSE_REHEARSAL_EDIT_FURNITURE === '1') {
    result.step = 'furniture-edit';
    const editor = page.locator('.scene-edit-review');
    await editor.getByLabel('Add furniture').check();
    await editor.getByLabel('Furniture type').selectOption('chair');
    await editor.getByLabel('Object ID').fill('furn_3_chair');
    await editor.getByLabel('X (m)').fill('0.9');
    await editor.getByLabel('Y (m)').fill('-1.4');
    await editor.getByRole('button', {name: 'Preview change'}).click();
    await expect(editor.getByText(/existing objects unchanged/)).toBeVisible();
    await editor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(1);

    await editor.getByLabel('Change furniture').check();
    const chairCallId = await editor.getByLabel('Existing furniture call')
      .locator('option', {hasText: 'furn_3_chair'}).getAttribute('value');
    expect(chairCallId).toBeTruthy();
    await editor.getByLabel('Existing furniture call').selectOption(chairCallId);
    await editor.getByLabel('Furniture type').selectOption('storage');
    await editor.getByRole('button', {name: 'Preview change'}).click();
    await expect(editor.getByText(/existing objects unchanged/)).toBeVisible();
    await editor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(2);

    await editor.getByLabel('Undo last edit').check();
    await editor.getByRole('button', {name: 'Preview change'}).click();
    await expect(editor.getByText(/existing objects unchanged/)).toBeVisible();
    await editor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(3);
    const edited = await workflow();
    expect(edited.site_draft.revision).not.toBe(edited.site_draft.original_scene_revision);
    expect(edited.acknowledged_revision).toBe(null);
    result.checks.push('browser_furniture_add_change_undo_preserves_original_and_requires_new_review');
  }

  if (process.env.TWINPULSE_REHEARSAL_FURNITURE_REQUEST === '1') {
    result.step = 'furniture-request';
    const editor = page.locator('.scene-edit-review');
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('침대와 의자 추가');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    await expect(editor.getByLabel('Bed staged item')).toBeVisible();
    await expect(editor.getByLabel('Chair staged item')).toBeVisible();
    await editor.getByRole('button', {name: 'Cancel staging'}).click();
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('선택한 가구 이동 X=-0.7');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    await expect(editor.getByText(/Select an item from the saved scene/)).toBeVisible();
    await editor.getByLabel('Change furniture').check();
    const bedCallId = await editor.getByLabel('Existing furniture call')
      .locator('option', {hasText: 'furn_1_bed'}).getAttribute('value');
    expect(bedCallId).toBeTruthy();
    await editor.getByLabel('Existing furniture call').selectOption(bedCallId);
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('선택한 의자 이동');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    await expect(editor.getByText(/selected furniture does not match the type named/)).toBeVisible();
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('선택한 가구 이동 X=-0.7');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    await expect(editor.getByText(/Selected furn_1_bed as the bed to move/)).toBeVisible();
    await expect(editor.getByLabel('X (m)')).toHaveValue('-0.7');
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('의자 추가 X=0.9 Y=-1.4');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    await expect(editor.getByText(/local furniture-blocks-1.0 preset/)).toBeVisible();
    await expect(editor.getByLabel('Add furniture')).toBeChecked();
    await expect(editor.getByLabel('Furniture type')).toHaveValue('chair');
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('button', {name: 'Preview change'}).click();
    await expect(editor.getByText(/existing objects unchanged/)).toBeVisible();
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(1);
    expect((await workflow()).acknowledged_revision).toBe(null);
    result.checks.push('offline_request_binds_selected_furniture_and_rejects_mismatch_before_explicit_preview_apply_new_ack');
  }

  if (process.env.TWINPULSE_REHEARSAL_FAKE_EDIT_PROPOSAL === '1') {
    result.step = 'fake-edit-proposal';
    const editor = page.locator('.scene-edit-review');
    await editor.getByLabel('Change furniture').check();
    const bedCallId = await editor.getByLabel('Existing furniture call')
      .locator('option', {hasText: 'furn_1_bed'}).getAttribute('value');
    expect(bedCallId).toBeTruthy();
    await editor.getByLabel('Existing furniture call').selectOption(bedCallId);
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('선택한 가구 이동 X=-0.7');
    let contextRequests = 0;
    await page.route('**/v1/product/scene-edit/context', async route => {
      contextRequests++;
      if (contextRequests === 1) return route.abort('failed');
      await new Promise(resolve => setTimeout(resolve, 300));
      return route.continue();
    });
    await editor.getByRole('button', {name: 'Preview offline simulated proposal'}).click();
    await expect(page.getByRole('alertdialog')).toBeVisible();
    await page.screenshot({path: path.join(output, 'edit-error-popup.png')});
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await page.getByRole('alertdialog').getByRole('button', {name: 'Close'}).click();
    await editor.getByRole('button', {name: 'Preview offline simulated proposal'}).click();
    await expect(page.getByRole('status').filter({hasText: 'Checking the saved scene edit context'})).toBeVisible();
    await page.screenshot({path: path.join(output, 'edit-loading.png')});
    await expect(editor.getByText(/existing objects unchanged/)).toBeVisible();
    expect(contextRequests).toBe(2);
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('button', {name: 'Save reviewed change'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(1);
    expect((await workflow()).acknowledged_revision).toBe(null);
    result.checks.push('browser_fake_proposal_error_popup_loading_preview_explicit_save_new_ack');
  }

  if (process.env.TWINPULSE_REHEARSAL_FURNITURE_STAGING === '1') {
    result.step = 'furniture-staging';
    const editor = page.locator('.scene-edit-review');
    await editor.getByRole('textbox',{name:'Furniture request',exact:true}).fill('침대와 의자 추가');
    await editor.getByRole('button', {name: 'Interpret furniture request'}).click();
    const map = editor.getByLabel('Room floor placement map');
    await map.scrollIntoViewIfNeeded();
    for (const [name, xRatio] of [['Bed', .25], ['Chair', .75]]) {
      const item = editor.getByLabel(`${name} staged item`);
      await item.scrollIntoViewIfNeeded();
      const box = await item.boundingBox();
      const mapBox = await map.boundingBox();
      if (!box) throw new Error(`Staged ${name} unavailable`);
      if (!mapBox) throw new Error('Room placement map unavailable');
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(mapBox.x + mapBox.width * xRatio, mapBox.y + mapBox.height * .769, {steps: 8});
      await page.mouse.up();
      await expect(item).not.toContainText('not placed');
      await editor.getByLabel('Staged direction').selectOption(name === 'Bed' ? '180' : '-90');
      if (name === 'Bed') {
        const marker = editor.getByLabel('Bed placed position');
        const markerBox = await marker.boundingBox();
        if (!markerBox) throw new Error('Placed bed marker unavailable');
        await page.mouse.move(markerBox.x + markerBox.width / 2, markerBox.y + markerBox.height / 2);
        await page.mouse.down();
        await page.mouse.move(mapBox.x + mapBox.width * (0.5 - .85 / 3.6),
          mapBox.y + mapBox.height * .769, {steps: 8});
        await page.mouse.up();
        await expect(item).toContainText('-0.85');
      }
    }
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('button', {name: 'Preview all'}).click();
    await expect(editor.getByText(/This revision adds 2 furniture items/)).toBeVisible();
    expect((await workflow()).site_draft.scene_edit_count).toBe(0);
    await editor.getByRole('button', {name: 'Save reviewed furniture'}).click();
    await expect.poll(async () => (await workflow()).site_draft.scene_edit_count).toBe(1);
    expect((await workflow()).acknowledged_revision).toBe(null);
    result.checks.push('browser_drags_repositions_and_rotates_staged_furniture_then_saves_one_reviewed_revision');
  }

  const presentationPreset = process.env.TWINPULSE_REHEARSAL_PRESENTATION;
  if (presentationPreset) {
    const [view, lighting] = presentationPreset.split(':');
    if (!['auto', 'front', 'back', 'left', 'right', 'top'].includes(view) ||
        !['balanced', 'soft', 'bright'].includes(lighting)) throw new Error('Invalid presentation rehearsal preset');
    const panel = page.locator('.presentation-review');
    await expect(panel).toBeVisible();
    if (process.env.TWINPULSE_REHEARSAL_PRESENTATION_REOPEN !== '1') {
      await panel.getByLabel('Camera direction').selectOption(view);
      await panel.getByLabel('Lighting').selectOption(lighting);
      await panel.getByRole('button', {name: 'Save view settings'}).click();
      await expect.poll(async () => (await workflow()).presentation.saved).toBe(true);
      result.checks.push('browser_saved_project_local_presentation');
    }
    await page.reload();
    await expect(page.getByText('Backend ready', {exact: true})).toBeVisible({timeout: 20000});
    await page.getByRole('button', {name: /Review Twin/}).click();
    const stateAfterReload = await workflow();
    expect(stateAfterReload.presentation.view).toBe(view);
    expect(stateAfterReload.presentation.lighting).toBe(lighting);
    expect(stateAfterReload.presentation.saved).toBe(true);
    result.checks.push('browser_reloaded_presentation_before_build');
  }

  result.step = 'build';
  const build = page.getByRole('button', {name: 'Build scene geometry in Isaac', exact: true});
  await expect(build).toBeDisabled();
  await page.getByRole('button', {name: 'Acquire scene control', exact: true}).click();
  await expect.poll(async () => (await product()).lease_owned).toBe(true);
  expect((await product()).operations).toHaveLength(0);
  const review = page.getByRole('region', {name: 'Review the draft', exact: true});
  await review.getByRole('checkbox').click();
  await expect.poll(async () => (await workflow()).acknowledged_revision).toBe((await workflow()).site_draft.revision);
  await expect(build).toBeEnabled({timeout: 15000});
  await build.click();
  await expect.poll(async () => {
    const current = await product();
    return current.operations.filter(operation => operation.command_type === 'build_site_scene' &&
      operation.status === 'succeeded').length;
  }, {timeout: 60000}).toBe(1);
  expect(result.commands).toEqual(['build_site_scene']);
  expect((await product()).snapshot.permitted_commands).not.toContain('run');
  result.checks.push('browser_ack_build_API_bridge_actual_Isaac_receipt_no_Run');
  await review.screenshot({path: path.join(output, 'saved-scene-browser.png')});
  expect(result.page_errors).toBe(0);
  expect(result.external_requests).toBe(0);
  result.status = 'PASS';
} catch (error) {
  result.error = String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').slice(0, 700);
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, 'browser-result.json'), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === 'PASS' ? 0 : 1;
