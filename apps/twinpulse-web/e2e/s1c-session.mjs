import { chromium } from "@playwright/test";
import fs from "node:fs";

const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const baseUrl = required("TWINPULSE_S1C_URL");
const bootstrap = required("TWINPULSE_PRODUCT_BOOTSTRAP");
const chromePath = required("TWINPULSE_CHROME");
const outputPath = required("TWINPULSE_S1C_RESULT");
const result = { status: "FAIL", stages: [] };

let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const context = await browser.newContext({ locale: "ko-KR" });
  const first = await context.newPage();
  await first.goto(`${baseUrl}/#bootstrap=${encodeURIComponent(bootstrap)}`, {
    waitUntil: "networkidle",
  });
  await first.getByText("Backend ready", { exact: true }).waitFor({ timeout: 15_000 });
  if (first.url().includes("bootstrap=")) throw new Error("Bootstrap secret remained in the page URL");
  result.stages.push("bootstrap_scrubbed");

  await first.reload({ waitUntil: "networkidle" });
  await first.getByText("Backend ready", { exact: true }).waitFor({ timeout: 15_000 });
  if (await first.getByText(/session_reopen_required/).count()) {
    throw new Error("Reload did not recover the authenticated browser session");
  }
  result.stages.push("reload_recovered");

  const second = await context.newPage();
  await second.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await second.getByText("Backend ready", { exact: true }).waitFor({ timeout: 15_000 });
  if (await second.getByText(/session_reopen_required/).count()) {
    throw new Error("New tab did not recover the authenticated browser session");
  }
  result.stages.push("new_tab_recovered");
  result.status = "PASS";
} catch (error) {
  result.error = `${error?.name ?? "Error"}: ${error?.message ?? String(error)}`;
} finally {
  if (browser) await browser.close();
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), "utf8");
  process.stdout.write(`TWINPULSE_S1C_RESULT=${JSON.stringify(result)}\n`);
}

process.exitCode = result.status === "PASS" ? 0 : 1;
