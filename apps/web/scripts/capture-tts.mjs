import { chromium } from "playwright";

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL("http://localhost:3000/", { timeout: 30000 }), page.click("button[type=submit]")]);

for (const [path, name] of [["/settings", "settings"], ["/studio/audio", "studio-final"], ["/providers", "providers-final"]]) {
  await page.goto(`http://localhost:3000${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `../.shots/${name}.png`, fullPage: true });
  console.log("captured", name);
}

// mobile check
const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
const mp = await mobile.newPage();
await mp.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
await mp.fill("#email", "admin@factory.app");
await mp.fill("#password", "factory-admin-2026");
await Promise.all([mp.waitForURL("http://localhost:3000/", { timeout: 30000 }), mp.click("button[type=submit]")]);
await mp.goto("http://localhost:3000/studio/audio", { waitUntil: "networkidle" });
await mp.waitForTimeout(1000);
await mp.screenshot({ path: "../.shots/studio-mobile.png", fullPage: true });

console.log(errors.length ? `ERRORS: ${errors.join(" | ")}` : "no console errors");
await browser.close();
