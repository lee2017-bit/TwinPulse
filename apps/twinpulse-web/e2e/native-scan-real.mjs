// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real React/HTTP round trip with already saved sensor samples and original photos.
// No robot, engine, paid provider, external request or active project changes.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const base = process.env.TWINPULSE_REHEARSAL_URL;
const bootstrap = process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output = process.env.TWINPULSE_REHEARSAL_OUTPUT;
const chrome = process.env.TWINPULSE_REHEARSAL_CHROME;
if (!base || new URL(base).hostname !== "127.0.0.1" || !bootstrap || !output || !chrome) throw new Error("Owned local rehearsal configuration required");
const bundle = JSON.parse(fs.readFileSync(path.join(output, "native-scan-bundle.json"), "utf8"));
const result = { status: "FAIL", data: "saved_sensor_recording", http: "actual_local_backend", stages: [],
  external_requests: 0, page_errors: 0, engine_commands: 0, physical_validation: "NOT_RUN" };
let browser;
let currentStage = "startup";
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
  await context.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base && !["blob:", "data:"].includes(url.protocol)) { result.external_requests++; return route.abort(); }
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
  currentStage = "native_import";
  await page.getByText("Native scan · Saved photo review", { exact: true }).click();
  const panel = page.locator(".native-review");
  await page.getByLabel("Import native scan bundle (JSON)").setInputFiles(path.join(output, "native-scan-bundle.json"));
  await expect(page.getByText("Saved sensor recording — imported provenance", { exact: true })).toBeVisible();
  const state = await snapshot("/v1/product/native-scan");
  expect(state.bundle.frame_count).toBe(74);
  expect(state.frame.points.length).toBe(389);
  expect(state.frame.invalid_returns).toBe(14);
  expect(state.source_bytes_verified).toBe(false);
  expect(state.world_tf).toBe(null);
  expect(state.motion_authorized).toBe(false);
  expect(state.analysis.clearance).toBe("UNKNOWN");
  expect(state.analysis.excluded_count).toBe(1025);
  result.bundle_digest = state.bundle.digest;
  result.stages.push("actual_74_frame_bundle_imported_native_angles_preserved");
  currentStage = "photo_hash_check";
  const room = page.getByLabel("Attach room original JPEG (local only)");
  await room.setInputFiles(path.join(output, "top-view-window-up.jpg"));
  await expect(panel.getByRole("alert")).toHaveText("Photo hash mismatch. Select the original bound photo.");
  await room.setInputFiles(path.join(output, "room.jpg"));
  await page.getByLabel("Attach top_view original JPEG (local only)").setInputFiles(path.join(output, "top-view-window-up.jpg"));
  for (const role of ["room", "top_view"]) {
    const photo = page.getByAltText(`${role} hash-matched source photo`);
    await expect(photo).toBeVisible();
    await expect.poll(() => photo.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  }
  await expect(panel.getByText(/Photo-up = window.*Not robot-forward/)).toBeVisible();
  result.stages.push("wrong_photo_rejected_both_original_hashes_and_jpeg_decode_passed");
  currentStage = "descriptive_quality";
  await page.getByText("Across-frame statistics (not clearance)", { exact: true }).click();
  await expect(panel.getByText(/1025 \/ 29538 returns excluded/)).toBeVisible();
  await expect(panel.getByText(/Clearance: UNKNOWN/)).toBeVisible();
  await expect(panel.locator(".native-quality tbody tr")).toHaveCount(72);
  await page.getByText("Across-frame statistics (not clearance)", { exact: true }).click();
  result.stages.push("server_computed_74_frame_quality_descriptive_only_unknown_clearance");
  currentStage = "display_and_frames";
  await page.getByLabel("Display orientation (not calibration)").selectOption("mirror1");
  await expect(page.getByText(/DISPLAY HYPOTHESIS ONLY/)).toBeVisible();
  for (const index of [0, 37, 73]) {
    currentStage = `display_frame_${index}`;
    await page.getByRole("combobox", { name: /^Saved frame/ }).selectOption(String(index));
    await expect(panel.getByText(new RegExp(`Frame ${index + 1}:`))).toBeVisible();
    const count = bundle.frames[index].beams.filter(b => b.distance_m > 0 && !(b.distance_m <= .15 && b.quality <= 65)).length;
    await expect(panel.locator("svg circle[fill='#5eead4']")).toHaveCount(count);
  }
  await panel.screenshot({ path: path.join(output, "native-photo-review-desktop.png") });
  result.stages.push("first_middle_last_frames_and_reflection_display_only");
  currentStage = "export_roundtrip";
  const downloadPromise = page.waitForEvent("download");
  await page.getByText("Export preserved native bundle", { exact: true }).click();
  const download = await downloadPromise;
  const downloadPath = path.join(output, "exported-native-scan-bundle.json");
  await download.saveAs(downloadPath);
  expect(JSON.parse(fs.readFileSync(downloadPath, "utf8"))).toEqual(bundle);
  result.stages.push("export_roundtrip_all_original_beams_and_photo_bindings_equal");
  currentStage = "native_3d_export";
  const usdPromise = page.waitForEvent("download");
  await page.getByText("Export selected frame to 3D (USD)", { exact: true }).click();
  const usdDownload = await usdPromise;
  expect(usdDownload.suggestedFilename()).toBe("native-frame-073.usda");
  const usdPath = path.join(output, "exported-native-frame-073.usda");
  await usdDownload.saveAs(usdPath);
  const usd = fs.readFileSync(usdPath, "utf8");
  expect(usd).toContain(state.bundle.digest);
  expect(usd).toContain('bool worldAlignmentVerified = false');
  expect(usd).toContain('sensor_native_unverified_axes');
  expect(usd).not.toContain('xformOp');
  result.native_3d_export = { sha256: crypto.createHash('sha256').update(usd).digest('hex'), frame_index: 73 };
  result.stages.push("selected_native_3d_download_hash_bound_no_display_reflection_or_world_tf");
  currentStage = "invalid_import";
  const forged = { ...bundle, motion_authorized: true };
  await page.getByLabel("Import native scan bundle (JSON)").setInputFiles({ name: "invalid.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(forged)) });
  await expect(panel.getByRole("alert")).toBeVisible();
  expect((await snapshot("/v1/product/native-scan")).bundle.digest).toBe(state.bundle.digest);
  result.stages.push("unsupported_authority_field_rejected_old_evidence_unchanged");
  currentStage = "mobile_and_isolation";
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: path.join(output, "native-photo-review-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  const product = await snapshot("/v1/product/state");
  expect(product.operations).toEqual([]);
  expect(product.lease_owned).toBe(false);
  expect(result.external_requests).toBe(0); expect(result.page_errors).toBe(0); expect(result.engine_commands).toBe(0);
  result.stages.push("mobile_no_horizontal_overflow_no_external_requests_no_engine_commands");
  result.status = "PASS";
} catch (error) {
  result.failed_stage = currentStage;
  result.error_type = error.constructor?.name ?? "Error";
  // Do not persist exception messages, navigation URLs or ephemeral credentials.
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(path.join(output, "browser-result.json"), JSON.stringify(result, null, 2));
}
process.exitCode = result.status === "PASS" ? 0 : 1;
