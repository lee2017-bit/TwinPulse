// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const baseUrl = required("TWINPULSE_R5_URL");
const bootstrap = required("TWINPULSE_PRODUCT_BOOTSTRAP");
const chromePath = required("TWINPULSE_CHROME");
const imagePath = required("TWINPULSE_R5_IMAGE");
const outputPath = required("TWINPULSE_R5_BROWSER_RESULT");
const screenshotDir = required("TWINPULSE_R5_SCREENSHOT_DIR");
fs.mkdirSync(screenshotDir, { recursive: true });

const result = {
  status: "FAIL",
  desktop_screenshot: null,
  mobile_screenshot: null,
  zoom_screenshot: null,
  keyboard_focus: false,
  mobile_overflow: null,
  stages: [],
};

let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "en-US" });
  await page.goto(`${baseUrl}/#bootstrap=${encodeURIComponent(bootstrap)}`, { waitUntil: "networkidle" });
  await page.getByText("Backend ready", { exact: true }).waitFor({ timeout: 15_000 });
  await page.getByText(/Isaac (idle|built|paused|completed)/).waitFor({ timeout: 15_000 });
  result.stages.push("authenticated_ready");

  await page.getByRole("combobox", { name: "Input type" }).selectOption("drawing");
  await page.getByLabel("Instructions (optional)").fill(
    "치수 도면을 바탕으로 중앙 통로와 2WD AGV 경로가 있는 밝은 창고를 구성하세요.",
  );
  await page.locator('input[type="file"]').first().setInputFiles(imagePath);
  await page.getByRole("button", { name: "Create Draft" }).click();
  await page.getByRole("heading", { name: "Review the draft" }).waitFor();
  const build = page.getByRole("button", { name: "Build in Isaac Sim" });
  if (!(await build.isDisabled())) throw new Error("Build was enabled before draft acknowledgement");
  // The checkbox is server-controlled: its checked state changes only after
  // the acknowledgement response returns, so click and wait on the real gate.
  await page.getByRole("checkbox", { name: "I reviewed the limits of this draft version." }).click();
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent?.includes("Build in Isaac Sim"));
    return button instanceof HTMLButtonElement && !button.disabled;
  });
  result.stages.push("draft_reviewed_acknowledged");

  await build.click();
  await page.getByText("Scene version matched", { exact: true }).waitFor({ timeout: 30_000 });
  result.stages.push("actual_revision_applied");
  result.desktop_screenshot = path.join(screenshotDir, "r5-desktop-applied.png");
  await page.screenshot({ path: result.desktop_screenshot, fullPage: true });

  const run = page.locator("button.run");
  await page.waitForFunction(() => {
    const button = document.querySelector("button.run");
    return button instanceof HTMLButtonElement && !button.disabled;
  }, undefined, { timeout: 15_000 });
  await run.click();
  await page.locator(".stage-caption strong").filter({ hasText: "running" }).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(1_200);
  await page.getByRole("button", { name: /Pause/ }).click();
  await page.locator(".stage-caption strong").filter({ hasText: "paused" }).waitFor({ timeout: 15_000 });
  result.stages.push("run_pause");

  await page.getByRole("button", { name: /Reset/ }).click();
  await page.locator(".stage-caption strong").filter({ hasText: "built" }).waitFor({ timeout: 15_000 });
  await page.getByRole("button", { name: "Show 3D View" }).click();
  await page.getByText("focus_scene · Completed and confirmed", { exact: true }).waitFor({ timeout: 15_000 });
  result.stages.push("reset_focus");

  await page.evaluate(() => { document.body.style.zoom = "1.25"; });
  result.zoom_screenshot = path.join(screenshotDir, "r5-zoom-125.png");
  await page.screenshot({ path: result.zoom_screenshot, fullPage: true });
  await page.evaluate(() => { document.body.style.zoom = ""; });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /Add Photo/ }).click();
  await page.keyboard.press("Home");
  await page.keyboard.press("Tab");
  result.keyboard_focus = await page.evaluate(() => {
    const element = document.activeElement;
    return Boolean(element && ["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(element.tagName));
  });
  result.mobile_overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  result.mobile_screenshot = path.join(screenshotDir, "r5-mobile-english.png");
  await page.screenshot({ path: result.mobile_screenshot, fullPage: true });
  if (!result.keyboard_focus) throw new Error("Keyboard focus did not reach an interactive control");
  if (result.mobile_overflow > 1) throw new Error(`Mobile layout overflows by ${result.mobile_overflow}px`);
  result.stages.push("responsive_zoom_keyboard");
  result.status = "PASS";
} catch (error) {
  result.error = `${error?.name ?? "Error"}: ${error?.message ?? String(error)}`;
  if (browser) {
    try {
      const pages = browser.contexts().flatMap((context) => context.pages());
      if (pages[0]) {
        const failure = path.join(screenshotDir, "r5-browser-failure.png");
        await pages[0].screenshot({ path: failure, fullPage: true });
        result.failure_screenshot = failure;
      }
    } catch { /* Preserve the primary failure. */ }
  }
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), "utf8");
  process.stdout.write(`TWINPULSE_BROWSER_RESULT=${JSON.stringify(result)}\n`);
}

process.exitCode = result.status === "PASS" ? 0 : 1;
