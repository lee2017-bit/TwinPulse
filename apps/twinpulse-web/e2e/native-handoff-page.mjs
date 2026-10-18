// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Local static artifact QA. No server, application controls or robot.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const output = path.resolve(process.argv[2] ?? "");
if (path.dirname(output) !== path.join(root, "artifacts")) throw new Error("Direct artifact directory required");
const pagePath = path.join(output, "index.html");
if (!fs.existsSync(pagePath)) throw new Error("Existing static handoff page required");
const resultPath = path.join(output, "page-qa.json");
if (fs.existsSync(resultPath)) throw new Error("Existing QA result will not be overwritten");
const chrome = path.join(process.env.PROGRAMFILES || "C:/Program Files", "Google/Chrome/Application/chrome.exe");
const result = { status: "FAIL", external_requests: 0, page_errors: 0, robot: "NOT_RUN", checks: [] };
let browser;
try {
  browser = await chromium.launch({ executablePath: chrome, headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  await context.route("**/*", async route => {
    if (new URL(route.request().url()).protocol !== "file:") { result.external_requests++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", () => result.page_errors++);
  await page.goto(pathToFileURL(pagePath).href);
  await expect(page.getByText("OFFLINE_EVIDENCE_PASS", { exact: true })).toBeVisible();
  for (const image of await page.locator("img").all()) {
    await expect.poll(() => image.evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  }
  for (const href of await page.locator("a").evaluateAll(anchors => anchors.map(a => a.href))) {
    const url = new URL(href);
    expect(url.protocol).toBe("file:");
    expect(fs.existsSync(fileURLToPath(url))).toBe(true);
  }
  result.checks.push("local_images_decode_and_links_resolve");
  await page.screenshot({ path: path.join(output, "page-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, "page-mobile.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(result.external_requests).toBe(0); expect(result.page_errors).toBe(0);
  result.checks.push("desktop_mobile_no_overflow_no_external_requests");
  result.status = "PASS";
} catch (error) { result.error_type = error.constructor?.name ?? "Error"; }
finally {
  if (browser) await browser.close();
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2), { flag: "wx" });
}
process.exitCode = result.status === "PASS" ? 0 : 1;
