/**
 * Headless visual capture for review (not part of the app build).
 * Usage: node scripts/capture.mjs [path ...]
 */

import { chromium } from "playwright";

const base = process.env.APP_URL || "http://localhost:3000";
const paths = process.argv.slice(2).length ? process.argv.slice(2) : ["/", "/workflows", "/content", "/agents", "/providers", "/channels", "/costs", "/analytics", "/approvals", "/settings"];
const outDir = process.env.OUT_DIR || "../.shots";

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
const page = await context.newPage();

const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`, { timeout: 30000 }), page.click("button[type=submit]")]);
await page.waitForLoadState("networkidle");

for (const path of paths) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  const name = path === "/" ? "overview" : path.replaceAll("/", "-").replace(/^-/, "");
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true });
  console.log("captured", path);
}

if (errors.length) {
  console.log("CONSOLE ERRORS:");
  for (const e of errors.slice(0, 20)) console.log(" -", e);
} else {
  console.log("no console errors");
}
await browser.close();
