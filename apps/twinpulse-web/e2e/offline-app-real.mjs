// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real browser -> real production API, explicitly synthetic data, no engine.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== "127.0.0.1" || !bootstrap || !output || !chrome) throw new Error("Owned local rehearsal configuration required");
const read = name => JSON.parse(fs.readFileSync(path.join(output, name), "utf8"));
const result = { status: "FAIL", data: "synthetic", http: "actual_local_backend", stages: [],
  external_requests: 0, page_errors: 0, engine_commands: 0, physical_validation: "NOT_RUN" };
let browser;
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
  // API requests are never fulfilled by this handler; only prevent external URLs.
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !["blob:", "data:"].includes(url.protocol)) {
      result.external_requests++; return route.abort();
    }
    if (url.pathname === "/v1/product/commands") { result.engine_commands++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", () => result.page_errors++);
  await page.goto(`${base}/#bootstrap=${encodeURIComponent(bootstrap)}`);
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).hash).toBe("");
  result.stages.push("real_bootstrap_session");
  const snapshot = endpoint => page.evaluate(async endpoint => {
    const response = await fetch(endpoint); if (!response.ok) throw new Error("Snapshot unavailable"); return response.json();
  }, endpoint);
  await page.getByText("Robot status · Saved diagnostics", { exact: true }).click();
  await page.getByLabel("Import robot report (JSON)").setInputFiles(path.join(output, "synthetic-health-report.json"));
  await expect(page.getByText("Historical measurement — not live")).toBeVisible();
  await expect(page.getByText(/11.21 V · estimated 39.4%/)).toBeVisible();
  const health = await snapshot("/v1/product/robot/report");
  expect(health.connection).toBe("NOT_CONNECTED"); expect(health.motion_authorized).toBe(false);
  expect(health.demo_ready).toBe(false); expect(health.source_verified).toBe(false);
  result.stages.push("synthetic_health_import_historical_only");
  await page.getByText("Scan review · Offline scratch draft", { exact: true }).click();
  await page.getByLabel("Import scan bundle (JSON)").setInputFiles(path.join(output, "bundle.json"));
  await expect(page.getByText("SYNTHETIC — unverified saved evidence")).toBeVisible();
  const imported = await snapshot("/v1/product/scan-review");
  const before = page.getByLabel("Baseline XY points (JSON)"), after = page.getByLabel("Candidate XY points (JSON)");
  await before.fill(JSON.stringify(read("baseline.json")));
  await after.fill(JSON.stringify(read("candidate.json")));
  await page.getByRole("button", { name: "Compare supplied routes", exact: true }).click();
  await expect(page.getByText(/candidate length reduction 39.64%/)).toBeVisible();
  const compared = await snapshot("/v1/product/scan-review");
  expect(compared.route_comparison.execution_authorized).toBe(false);
  expect(compared.route_comparison.conditions.revision).toBe(imported.route_conditions.revision);
  result.stages.push("actual_http_same_condition_comparison");
  await page.getByRole("region", { name: "Offline route comparison" }).screenshot({ path: path.join(output, "desktop-comparison.png") });
  await after.fill('[[-2,0],[2,0]]');
  await page.getByRole("button", { name: "Compare supplied routes", exact: true }).click();
  await expect(page.getByText(/Not comparable: no shorter-route winner/)).toBeVisible();
  expect((await snapshot("/v1/product/scan-review")).route_comparison.shorter_route_id).toBe(null);
  result.stages.push("shorter_but_blocked_no_winner");
  await page.getByLabel("Landmark pairs (JSON)").fill(JSON.stringify(read("pairs.json")));
  await page.getByRole("button", { name: "Preview XY correction", exact: true }).click();
  await expect(page.getByText(/Proposed obstacle: ΔX 0.100 m, ΔY 0.100 m/)).toBeVisible();
  expect((await snapshot("/v1/product/scan-review")).route_comparison).toBe(null);
  const apply = page.getByRole("button", { name: "Apply to scratch draft only", exact: true });
  await expect(apply).toBeDisabled();
  const review = page.getByLabel("I reviewed this exact scratch-draft change. It does not approve execution.");
  await review.check(); await apply.click();
  await expect(page.getByText(/Map: Absent — rebuild required/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Compare supplied routes", exact: true })).toHaveCount(0);
  const applied = await snapshot("/v1/product/scan-review");
  expect(applied.active_project_changed).toBe(false); expect(applied.motion_authorized).toBe(false);
  expect(applied.route_conditions).toBe(null); expect(applied.route_comparison).toBe(null);
  result.stages.push("reviewed_scratch_apply_invalidates_map_mission_comparison");
  await page.getByRole("button", { name: "Preview conservative map overlay", exact: true }).click();
  await expect(page.getByText(/0 freed/)).toBeVisible();
  const useMap = page.getByRole("button", { name: "Use reviewed map in scratch draft", exact: true });
  await expect(useMap).toBeDisabled();
  await page.getByRole("region", { name: "Conservative map review" }).screenshot({ path: path.join(output, "map-proposal-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("region", { name: "Conservative map review" }).screenshot({ path: path.join(output, "map-proposal-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.getByLabel("I reviewed this map overlay and these endpoints for offline comparison only.").check();
  await useMap.click();
  await expect(page.getByText(/Conservative overlay applied — unverified/)).toBeVisible();
  const refreshed = await snapshot("/v1/product/scan-review");
  expect(refreshed.route_conditions.revision).not.toBe(imported.route_conditions.revision);
  expect(refreshed.map_overlay.freed_cells).toBe(0); expect(refreshed.map_overlay.execution_authorized).toBe(false);
  await before.fill(JSON.stringify(read("baseline.json")));
  await after.fill(JSON.stringify(read("candidate.json")));
  await page.getByRole("button", { name: "Compare supplied routes", exact: true }).click();
  await expect(page.getByText(/candidate length reduction 39.64%/)).toBeVisible();
  const reCompared = await snapshot("/v1/product/scan-review");
  expect(reCompared.route_comparison.conditions.map_revision).toBe(refreshed.map_overlay.map_revision);
  await page.getByRole("region", { name: "Conservative map review" }).screenshot({ path: path.join(output, "map-overlay-review.png") });
  result.stages.push("explicit_map_mission_review_and_fresh_comparison");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export review record", exact: true }).click();
  const download = await downloadPromise;
  await download.saveAs(path.join(output, "browser-export.json"));
  const exported = read("browser-export.json");
  expect(exported.execution_authority).toBe(false); expect(exported.restore_supported).toBe(false);
  expect(exported.snapshot.scene.revision).toBe(applied.scene.revision);
  result.stages.push("real_download_inspection_record");
  if (process.env.TWINPULSE_REHEARSAL_ARCHIVE === "1") {
    const savedState = await snapshot("/v1/product/scan-review");
    const archiveDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "Save replay archive", exact: true }).click();
    await (await archiveDownload).saveAs(path.join(output, "browser-archive.json"));
    const archive = read("browser-archive.json");
    expect(archive.schema_version).toBe("scan-review-archive-1.0");
    expect(archive.actions.map(a => a.action)).toEqual(["correction", "map_overlay"]);
    expect(archive.execution_authority).toBe(false); expect(archive.source_verified).toBe(false);
    result.stages.push("archive_download_contains_replay_inputs_not_execution_authority");
    result.archive_checkpoint = "undo_before_restore";
    await review.check(); await page.getByRole("button", { name: "Undo last scratch edit", exact: true }).click();
    await expect(page.getByRole("button", { name: "Undo last scratch edit", exact: true })).toBeDisabled();
    await expect(page.getByText("3 applied actions in this archive. Files are unverified evidence, not execution authority.", { exact: true })).toBeVisible();
    result.archive_checkpoint = "undo_completed";
    await expect(page.getByLabel("Restore offline archive (JSON)")).toBeEnabled();
    const restoreResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/v1/product/scan-review/archive-import");
    await page.getByLabel("Restore offline archive (JSON)").setInputFiles(path.join(output, "browser-archive.json"));
    const archiveResponse = await restoreResponse;
    result.archive_checkpoint = "restore_response";
    result.archive_restore_status = archiveResponse.status();
    if (archiveResponse.status() !== 200) result.archive_restore_error = await archiveResponse.json();
    expect(archiveResponse.status()).toBe(200);
    result.archive_checkpoint = "restored_action_count";
    await expect(page.getByText("2 applied actions in this archive. Files are unverified evidence, not execution authority.", { exact: true })).toBeVisible();
    const restoredState = await snapshot("/v1/product/scan-review");
    result.archive_checkpoint = "restored_scene_equality";
    expect(restoredState.scene).toEqual(savedState.scene);
    result.archive_checkpoint = "restored_map_equality";
    expect(restoredState.map_overlay).toEqual(savedState.map_overlay);
    result.archive_checkpoint = "restored_revision_and_transients";
    expect(restoredState.workspace_revision).not.toBe(savedState.workspace_revision);
    expect(restoredState.route_comparison).toBeNull(); expect(restoredState.proposal).toBeNull();
    expect(restoredState.motion_authorized).toBe(false); expect(restoredState.active_project_changed).toBe(false);
    await expect(review).not.toBeChecked();
    result.stages.push("archive_restore_recomputes_geometry_and_clears_transient_reviews");
    const corrupt = { ...archive, execution_authority: true };
    fs.writeFileSync(path.join(output, "corrupt-archive.json"), JSON.stringify(corrupt), { flag: "wx" });
    await page.getByLabel("Restore offline archive (JSON)").setInputFiles(path.join(output, "corrupt-archive.json"));
    await expect(page.locator(".scan-review:not(.native-review)").getByRole("alert")).toBeVisible();
    expect(await snapshot("/v1/product/scan-review")).toEqual(restoredState);
    await page.locator(".scan-review:not(.native-review)").screenshot({ path: path.join(output, "archive-restored.png") });
    result.stages.push("corrupt_archive_rejected_previous_workspace_unchanged");
    delete result.archive_checkpoint;
  }
  await review.check(); await page.getByRole("button", { name: "Undo last scratch edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "Undo last scratch edit", exact: true })).toBeDisabled();
  const undone = await snapshot("/v1/product/scan-review");
  expect(undone.scene.objects).toEqual(imported.scene.objects);
  expect(undone.scene.revision).not.toBe(imported.scene.revision);
  expect(undone.map_present).toBe(false); expect(undone.mission_present).toBe(false);
  result.stages.push("undo_geometry_not_old_approvals");
  await page.reload();
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  await page.getByText("Scan review · Offline scratch draft", { exact: true }).click();
  await page.getByRole("button", { name: "Refresh offline review", exact: true }).click();
  await expect(page.getByText("SYNTHETIC — unverified saved evidence")).toBeVisible();
  expect((await snapshot("/v1/product/scan-review")).workspace_revision).toBe(undone.workspace_revision);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".scan-review:not(.native-review)").screenshot({ path: path.join(output, "mobile-review.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const product = await snapshot("/v1/product/state");
  expect(product.operations).toEqual([]); expect(product.artifacts).toEqual([]);
  expect(product.lease_owned).toBe(false); expect(product.engine_connected).toBe(false);
  expect(result.external_requests).toBe(0); expect(result.page_errors).toBe(0); expect(result.engine_commands).toBe(0);
  result.stages.push("reload_session_recovery_mobile_no_active_project_operations");
  result.status = "PASS";
} catch (error) {
  // Do not serialize Playwright call logs: navigation may contain bootstrap material.
  result.error_type = error.constructor.name;
  process.exitCode = 1;
} finally {
  await browser?.close();
  fs.writeFileSync(path.join(output, "browser-result.json"), JSON.stringify(result, null, 2));
}
