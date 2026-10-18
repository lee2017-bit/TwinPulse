// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// No-call browser smoke for H1a copy, input gates, and responsive layouts.
import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const screenshotDir = process.env.TWINPULSE_H1A_SCREENSHOT_DIR
  ?? path.join(repoRoot, "artifacts", "runs", "h1a-browser-smoke");
const port = 47000 + (process.pid % 10000);
const baseUrl = `http://127.0.0.1:${port}`;
const viteBin = path.join(webRoot, "node_modules", "vite", "bin", "vite.js");
const chromePath = process.env.TWINPULSE_CHROME
  ?? path.join(process.env.PROGRAMFILES ?? "C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe");

const workflow = {
  schema_version: "1.1", mode: "explicit_fixture", provider: { configured: true, connected: false, label: "fixture" },
  phase: "empty", generation_id: null, input: null, draft: null, acknowledged_revision: null,
  build_allowed: false, error: null,
};
const product = {
  project_id: "default", engine_connected: false, engine_session_id: null, stage_epoch: null,
  lease_owned: false, control_lease_id: null, snapshot: null, operations: [], artifacts: [],
};
const providerSettings = {
  schema_version: "3.0", base_url: "https://api.openai.com/v1/", model_id: "gpt-test",
  reasoning_effort: "low", adapter_kind: "openai_responses", provider_profile: "openai",
  credential_configured: true, capability_checked: true, live_request_succeeded: false,
};
const runtime = {
  schema_version: "1.0", status: "ready", phase: "ready", message: "Ready",
  backend: { owned: false, state: "ready" }, engine: { owned: false, state: "disconnected" },
  browser: { launched: false },
};

const server = spawn(process.execPath, [viteBin, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
  cwd: webRoot, stdio: "ignore", windowsHide: true,
});
let browser;
let generationRequests = 0;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Preview exited: ${server.exitCode}`);
    try { ready = (await fetch(baseUrl)).ok; } catch { /* Server still starting. */ }
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error("Preview did not start within 6 seconds");
  fs.mkdirSync(screenshotDir, { recursive: true });
  browser = await chromium.launch({ executablePath: fs.existsSync(chromePath) ? chromePath : undefined, headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 }, locale: "en-US" });
  const page = await context.newPage();
  await page.route("**/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/v1/product/generation") generationRequests += 1;
    const data = {
      "/v1/product/session": { csrf_token: "browser-smoke" },
      "/v1/product/provider-settings": providerSettings,
      "/v1/product/workflow": workflow,
      "/v1/product/state": product,
      "/v1/product/runtime": runtime,
    }[pathname];
    await route.fulfill({ status: data ? 200 : 404, contentType: "application/json", body: JSON.stringify(data ?? { error: { code: "not_found" } }) });
  });
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.getByText("Backend ready", { exact: true }).waitFor();
  if (await page.locator("html").getAttribute("lang") !== "en") throw new Error("HTML locale is not English");
  if (!(await page.getByRole("button", { name: "Create Draft" }).isDisabled())) throw new Error("Empty input enabled generation");
  if (generationRequests !== 0) throw new Error("The page generated without user input");
  if (await page.getByText(/warehouse/i).count()) throw new Error("Warehouse-specific default copy remains");
  await page.screenshot({ path: path.join(screenshotDir, "1366x768.png"), fullPage: true });

  await page.getByRole("button", { name: "AI settings" }).click();
  await page.getByText("Key stored in Windows Credential Manager").waitFor();
  if (await page.getByText(/Live request not tested or not successful/).count() !== 1) throw new Error("Saved key and live response are not distinct");
  await page.locator(".settings-panel").getByRole("button", { name: "Cancel" }).click();
  await page.getByLabel("Instructions (optional)").fill("현장 통로를 넓혀줘");
  if (await page.getByLabel("Instructions (optional)").inputValue() !== "현장 통로를 넓혀줘") throw new Error("Korean input changed");
  if (await page.getByRole("button", { name: "Create Draft" }).isDisabled()) throw new Error("Valid text input did not enable generation");

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.evaluate(() => { document.body.style.zoom = "1.25"; });
  await page.screenshot({ path: path.join(screenshotDir, "1920x1080-125.png"), fullPage: true });
  await page.evaluate(() => { document.body.style.zoom = ""; });
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) throw new Error(`Mobile viewport overflows by ${overflow}px`);
  await page.screenshot({ path: path.join(screenshotDir, "390x844.png"), fullPage: true });
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => ["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName ?? ""));
  if (!focused) throw new Error("Keyboard focus missed interactive controls");
  process.stdout.write(`H1A_BROWSER_PASS screenshots=${screenshotDir} mobile_overflow=${overflow} generation_requests=${generationRequests}\n`);
} finally {
  if (browser) await browser.close();
  server.kill();
}
