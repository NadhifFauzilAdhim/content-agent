/** Capture a page at three viewport widths for responsive review. */
import { chromium } from "playwright";

const base = process.env.APP_URL || "http://localhost:3000";
const path = process.argv[2] || "/";
const outDir = process.env.OUT_DIR || "../.shots";
const sizes = [
  { name: "tablet", width: 820, height: 1180 },
  { name: "mobile", width: 390, height: 844 },
];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`), page.click("button[type=submit]")]);
await page.waitForLoadState("networkidle");

for (const size of sizes) {
  await page.setViewportSize({ width: size.width, height: size.height });
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: `${outDir}/${size.name}${path === "/" ? "-overview" : path.replaceAll("/", "-")}.png`, fullPage: true });
  console.log("captured", size.name, path);
}
await browser.close();
