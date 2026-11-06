import { chromium } from "playwright";

const base = process.env.APP_URL || "http://localhost:3000";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));
page.on("response", async (res) => {
  if (res.url().includes("/tts/") && res.status() >= 400) {
    console.log("HTTP", res.status(), res.url(), (await res.text()).slice(0, 300));
  }
});

await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`, { timeout: 30000 }), page.click("button[type=submit]")]);

await page.goto(`${base}/studio/audio`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
const errorsOnPage = await page.locator("text=Request failed").count();
console.log("catalogue error messages:", errorsOnPage);
const modelOptions = await page.locator("select").nth(1).locator("option").allTextContents().catch(() => []);
const voiceOptions = await page.locator("select").nth(2).locator("option").allTextContents().catch(() => []);
const formatOptions = await page.locator("select").nth(3).locator("option").allTextContents().catch(() => []);
console.log("models:", modelOptions);
console.log("voices:", voiceOptions);
console.log("formats:", formatOptions);
await page.screenshot({ path: process.env.OUT_DIR ? `${process.env.OUT_DIR}/studio-check.png` : "../.shots/studio-check.png", fullPage: true });
console.log(errors.length ? `CONSOLE ERRORS: ${errors.join(" | ")}` : "no console errors");
await browser.close();
