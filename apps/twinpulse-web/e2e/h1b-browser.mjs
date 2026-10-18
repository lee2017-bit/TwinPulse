// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// No-call H1b browser check: HTTP acceptance is not engine completion.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const screenshotDir = process.env.TWINPULSE_H1B_SCREENSHOT_DIR ?? path.join(repoRoot, "artifacts", "runs", "h1b-browser-smoke");
const port = 47000 + (process.pid % 10000);
const baseUrl = `http://127.0.0.1:${port}`;
const viteBin = path.join(webRoot, "node_modules", "vite", "bin", "vite.js");
const chromePath = process.env.TWINPULSE_CHROME ?? path.join(process.env.PROGRAMFILES ?? "C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe");
const revision = "r".repeat(64);
const oldRevision = "o".repeat(64);
const draft = {
  artifact_id: "fixture", revision, input_revision: "i".repeat(64), plan_sha256: "p".repeat(64),
  request_id: "request", provider_name: "Fixture", model_id: "fixture", scene_id: "site",
  robot_profile_id: "2wd", task_id: "route", object_count: 1, tool_count: 1,
  objects: [{ id: "floor", kind: "floor", position_m: [0, 0, 0], dimensions_m: [4, 4, 0.1], provenance: "fixture" }],
  source: "fixture", approximate: true,
};
const workflow = {
  schema_version: "1.1", mode: "explicit_fixture", provider: { configured: false, connected: false, label: "fixture" },
  phase: "draft_ready", generation_id: null, input: { revision: draft.input_revision, input_kind: "photo" },
  draft, acknowledged_revision: revision, build_allowed: true, error: null,
};
const snapshot = {
  schema_version: "1.1", engine_session_id: "engine", stage_epoch: "stage", project_id: "default",
  applied_revision: oldRevision, run_id: null, sequence: 1, runtime_state: "built", safety_state: null,
  safety_reason: null, permitted_commands: ["get_state", "focus_scene"], capabilities: ["simulation"],
  sim_time_s: 0, sampled_at_utc: null, frame_id: "world", position_m: null, yaw_rad: null,
  roll_rad: null, pitch_rad: null, linear_speed_mps: null, distance_to_goal_m: null,
  cross_track_error_m: null, telemetry_available: false,
};
const product = {
  project_id: "default", engine_connected: true, engine_session_id: "engine", stage_epoch: "stage",
  lease_owned: false, control_lease_id: null, snapshot, operations: [], artifacts: [{ artifact_id: "fixture", revision }],
};
const operation = {
  command_id: "browser-build", command_type: "build_scene", project_id: "default",
  engine_session_id: "engine", stage_epoch: "stage", expected_applied_revision: revision,
  status: "accepted", receipt: null,
};
const providerSettings = {
  schema_version: "3.0", base_url: "https://api.openai.com/v1/", model_id: "fixture",
  reasoning_effort: "low", adapter_kind: "openai_responses", provider_profile: "openai",
  credential_configured: true, capability_checked: false, live_request_succeeded: false,
};
const runtime = {
  schema_version: "1.0", status: "ready", phase: "ready", message: "Ready",
  backend: { owned: false, state: "ready" }, engine: { owned: false, state: "ready" }, browser: { launched: false },
};

const server = spawn(process.execPath, [viteBin, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
  cwd: webRoot, stdio: "ignore", windowsHide: true,
});
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Preview exited: ${server.exitCode}`);
    try { ready = (await fetch(baseUrl)).ok; } catch { /* starting */ }
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error("Preview did not start");
  fs.mkdirSync(screenshotDir, { recursive: true });
  browser = await chromium.launch({ executablePath: fs.existsSync(chromePath) ? chromePath : undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  await page.route("**/v1/**", async (route) => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === "/v1/product/commands") product.operations = [{ ...operation }];
    const data = {
      "/v1/product/session": { csrf_token: "h1b" },
      "/v1/product/provider-settings": providerSettings,
      "/v1/product/workflow": workflow,
      "/v1/product/state": product,
      "/v1/product/runtime": runtime,
      "/v1/product/robot/report": {
        schema_version: "robot-report-review-1.0", session_id: "offline-fixture",
        connection: "NOT_CONNECTED", motion_authorized: false, demo_ready: false,
        notice: "Saved report fixture", blockers: [], record: {
          boot_id: "76d5f5c5-0a06-4720-aa6a-7b328d6d6265", release_id: null,
          report_sha256: "a".repeat(64), observed_at_utc: "2026-09-26T15:00:00Z",
          age_seconds: 3600, board_status: "OBSERVED", idle_at_observation: true,
          battery: { voltage_v: 11.21, estimated_percent: 39.4,
            observed_at_utc: "2026-09-26T15:00:00Z",
            charge_requested_at_observation: false, near_protection_at_observation: false },
        },
      },
      "/v1/product/lease": { control_lease_id: "lease", ttl_s: 3 },
      "/v1/product/lease/renew": { control_lease_id: "lease", ttl_s: 3 },
      "/v1/product/commands": operation,
    }[endpoint];
    await route.fulfill({ status: endpoint === "/v1/product/commands" ? 202 : data ? 200 : 404, contentType: "application/json", body: JSON.stringify(data ?? { error: { code: "not_found" } }) });
  });
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator('.robot-report summary').click();
  await page.getByRole('button', { name: 'Refresh saved report' }).click();
  await page.getByText('Historical measurement — not live').waitFor();
  await page.getByText('11.21 V · estimated 39.4% at observation').waitFor();
  await page.screenshot({ path: path.join(screenshotDir, 'robot-report-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) {
    throw new Error('Robot report has horizontal overflow');
  }
  await page.screenshot({ path: path.join(screenshotDir, 'robot-report-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.locator('.robot-report summary').click();
  await page.getByText("Previous scene remains", { exact: false }).waitFor();
  await page.getByRole("button", { name: "Review Twin" }).click();
  await page.getByRole("button", { name: "Build in Isaac Sim" }).click();
  await page.getByText("build_scene · Accepted · waiting for Isaac Sim").waitFor();
  if (await page.getByText("Simulation controls").count()) throw new Error("Accepted Build was shown as completed");
  await page.screenshot({ path: path.join(screenshotDir, "accepted.png"), fullPage: true });

  product.operations = [{ ...operation, status: "running" }];
  await page.getByText("build_scene · Running in Isaac Sim").waitFor();
  product.operations = [{ ...operation, status: "succeeded", receipt: {
    schema_version: "1.1", command_id: operation.command_id, command_type: "build_scene", project_id: "default",
    engine_session_id: "engine", stage_epoch: "stage", status: "succeeded", message: "built",
    error_code: null, applied_revision: revision, build_fingerprint: "f".repeat(64),
  } }];
  await page.getByText("build_scene · Engine reported success · waiting for matching scene state").waitFor();
  if (await page.getByText("Simulation controls").count()) throw new Error("Receipt was shown as applied before snapshot");
  product.snapshot = { ...snapshot, sequence: 2, applied_revision: revision, runtime_state: "built" };
  await page.getByText("Simulation controls").waitFor();
  await page.getByText("Status illustration · not the live 3D view").waitFor();
  await page.screenshot({ path: path.join(screenshotDir, "confirmed.png"), fullPage: true });

  product.stage_epoch = "replaced-stage";
  await page.getByText("Scene not confirmed · Isaac disconnected or changed", { exact: false }).first().waitFor();
  if (!(await page.getByRole("button", { name: /Run/ }).isDisabled())) throw new Error("Run enabled after stage replacement");
  process.stdout.write(`H1B_BROWSER_PASS screenshots=${screenshotDir}\n`);
} finally {
  if (browser) await browser.close();
  server.kill();
}
