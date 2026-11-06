/** Capture a detail page by resolving the first matching id from an API list (review helper). */
import { chromium } from "playwright";

const base = process.env.APP_URL || "http://localhost:3000";
const outDir = process.env.OUT_DIR || "../.shots";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`), page.click("button[type=submit]")]);
await page.waitForLoadState("networkidle");

const targets = [];
const projects = await page.evaluate(async () => (await (await fetch("/api/proxy/content")).json()));
if (projects[0]) targets.push([`/content/${projects[0].id}`, "content-detail"]);
const workflows = await page.evaluate(async () => (await (await fetch("/api/proxy/workflows")).json()));
if (workflows[0]) targets.push([`/workflows/${workflows[0].id}`, "workflow-detail"]);
const channels = await page.evaluate(async () => (await (await fetch("/api/proxy/channels")).json()));
if (channels[0]) targets.push([`/channels/${channels[0].id}`, "channel-detail"]);
targets.push(["/settings/audit", "audit"]);

for (const [path, name] of targets) {
  await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true });
  console.log("captured", path);
}
console.log(errors.length ? `ERRORS:\n${errors.slice(0, 10).join("\n")}` : "no console errors");
await browser.close();
