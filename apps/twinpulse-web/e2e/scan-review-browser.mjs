// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Synthetic UI rehearsal. HTTP responses are recorded local service snapshots,
// NOT a live robot or an end-to-end production backend/Isaac demonstration.
import { chromium, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "../..");
const folder = path.resolve(process.argv[2] ?? path.join(repoRoot, "artifacts/scan-review-rehearsal-20260927"));
const states = JSON.parse(fs.readFileSync(path.join(folder, "states.json"), "utf8"));
const pairs = JSON.parse(fs.readFileSync(path.join(folder, "pairs.json"), "utf8"));
const routeMode = process.argv.includes("--routes");
const port = 47000 + (process.pid % 10000);
const baseUrl = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, [path.join(webRoot, "node_modules/vite/bin/vite.js"), "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
  { cwd: webRoot, stdio: "ignore", windowsHide: true });
let browser;
try {
  let ready = false;
  for (let n = 0; n < 60; n++) {
    if (server.exitCode !== null) throw new Error("Local preview exited");
    try { ready = (await fetch(baseUrl)).ok; } catch { /* waiting for owned server */ }
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error("Preview unavailable");
  const chrome = path.join(process.env.PROGRAMFILES ?? "C:\\Program Files", "Google/Chrome/Application/chrome.exe");
  browser = await chromium.launch({ executablePath: fs.existsSync(chrome) ? chrome : undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  let current = states.empty;
  let actions = [];
  await page.route("**/v1/**", async route => {
    const request = route.request(), endpoint = new URL(request.url()).pathname;
    let result;
    if (endpoint.startsWith("/v1/product/scan-review")) {
      const body = request.method() === "POST" ? request.postDataJSON() : {};
      if (endpoint.endsWith("/import")) {
        expect(JSON.parse(body.bundle_text).recording.provenance).toBe("synthetic"); current = states.imported; actions.push("import");
      } else if (endpoint.endsWith("/propose")) {
        expect(body.workspace_revision).toBe(current.workspace_revision); expect(body.pairs).toEqual(pairs);
        current = states.proposed; actions.push("propose");
      } else if (endpoint.endsWith("/apply")) {
        expect(body.workspace_revision).toBe(current.workspace_revision); expect(body.proposal_revision).toBe(current.proposal.revision);
        current = states.applied; actions.push("apply");
      } else if (endpoint.endsWith("/undo")) {
        expect(body.workspace_revision).toBe(current.workspace_revision); expect(body.edit_revision).toBe(current.edit_revision);
        current = states.undone; actions.push("undo");
      } else if (endpoint.endsWith("/compare")) {
        expect(body.workspace_revision).toBe(current.workspace_revision);
        expect(body.conditions_revision).toBe(current.route_conditions.revision);
        expect(body.baseline.points_xy_m).toEqual(states.compared.route_comparison.baseline.points_xy_m);
        const blocked = body.candidate.points_xy_m.length === 2;
        expect(body.candidate.points_xy_m).toEqual((blocked ? states.blocked : states.compared).route_comparison.candidate.points_xy_m);
        expect(body.candidate.provenance).toBe("manual");
        current = structuredClone(blocked ? states.blocked : states.compared);
        current.route_comparison.baseline.provenance = current.route_comparison.candidate.provenance = "manual";
        actions.push("compare");
      }
      result = endpoint.endsWith("/export") ? states.exported : current;
    } else {
      result = {
        "/v1/product/session": { csrf_token: "synthetic-test" },
        "/v1/product/workflow": { schema_version: "1.1", mode: "explicit_fixture", provider: { configured: false, connected: false, label: "Fixture" }, phase: "empty", input: null, draft: null, build_allowed: false, error: null },
        "/v1/product/state": { project_id: "default", engine_connected: false, engine_session_id: null, stage_epoch: null, lease_owned: false, snapshot: null, operations: [], artifacts: [] },
        "/v1/product/provider-settings": { schema_version: "3.0", adapter_kind: "openai_responses", provider_profile: "openai", base_url: "https://api.openai.com/v1/", model_id: "fixture", credential_configured: false },
        "/v1/product/runtime": { schema_version: "1.0", status: "not_started", phase: "idle", message: "Offline fixture", backend: { owned: false, state: "ready" }, engine: { owned: false, state: "not_started" }, browser: { launched: false } },
      }[endpoint];
      if (!result) throw new Error(`Unexpected request ${endpoint}`);
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(result) });
  });
  await page.goto(baseUrl);
  await page.getByText("Scan review · Offline scratch draft", { exact: true }).click();
  await page.getByLabel("Import scan bundle (JSON)").setInputFiles(path.join(folder, "bundle.json"));
  await expect(page.getByText("SYNTHETIC — unverified saved evidence")).toBeVisible();
  if (routeMode) {
    const baseline = page.getByLabel("Baseline XY points (JSON)");
    const candidate = page.getByLabel("Candidate XY points (JSON)");
    await baseline.fill(JSON.stringify(states.compared.route_comparison.baseline.points_xy_m));
    await candidate.fill(JSON.stringify(states.compared.route_comparison.candidate.points_xy_m));
    await page.getByRole("button", { name: "Compare supplied routes", exact: true }).click();
    await expect(page.getByText(/candidate length reduction 39.64%/)).toBeVisible();
    await page.getByRole("region", { name: "Offline route comparison" }).screenshot({ path: path.join(folder, "route-comparison-desktop.png") });
    await candidate.fill('[[-2,0],[2,0]]');
    await expect(page.getByText(/candidate length reduction 39.64%/)).not.toBeVisible();
    await page.getByRole("button", { name: "Compare supplied routes", exact: true }).click();
    await expect(page.getByText(/Not comparable: no shorter-route winner/)).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("region", { name: "Offline route comparison" }).screenshot({ path: path.join(folder, "route-comparison-mobile.png") });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(actions).toEqual(["import", "compare", "compare"]);
  } else {
  await page.getByLabel("Landmark pairs (JSON)").fill(JSON.stringify(pairs, null, 2));
  await page.getByRole("button", { name: "Preview XY correction", exact: true }).click();
  await expect(page.getByText(/Proposed observed_box: ΔX 0.200 m, ΔY 0.100 m/)).toBeVisible();
  const check = page.getByLabel("I reviewed this exact scratch-draft change. It does not approve execution.");
  const apply = page.getByRole("button", { name: "Apply to scratch draft only", exact: true });
  await expect(apply).toBeDisabled();
  await check.check(); await apply.click();
  await expect(page.getByText(/Scene identity changed/)).toBeVisible();
  await expect(page.getByText(/Map: Absent — rebuild required/)).toBeVisible();
  await page.locator(".scan-review").screenshot({ path: path.join(folder, "scan-review-desktop.png") });
  await check.check();
  await page.getByRole("button", { name: "Undo last scratch edit", exact: true }).click();
  await expect(page.getByRole("button", { name: "Undo last scratch edit", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Preview XY correction", exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".scan-review").screenshot({ path: path.join(folder, "scan-review-mobile.png") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(actions).toEqual(["import", "propose", "apply", "undo"]);
  }
  expect(errors).toEqual([]);
  console.log(`${routeMode ? "ROUTE_COMPARISON" : "SCAN_REVIEW"}_BROWSER=PASS synthetic mocked HTTP desktop/mobile; actual robot/Isaac NOT_RUN`);
} finally {
  await browser?.close();
  server.kill(); // Only this script's own preview process.
}
