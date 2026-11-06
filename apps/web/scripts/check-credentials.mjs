import { chromium } from "playwright";

const base = "http://localhost:3000";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`, { timeout: 30000 }), page.click("button[type=submit]")]);

await page.goto(`${base}/providers`, { waitUntil: "networkidle" });
// Cartesia row -> add key
const rows = page.locator("tbody tr", { hasText: "cartesia" });
await rows.first().getByRole("button", { name: /add key/i }).click();
await page.waitForTimeout(300);
const panel = page.locator("div", { hasText: "rotate api key" }).or(page.locator("div", { hasText: /^api key/ })).last();
await rows.first().screenshot({ path: "../.shots/credential-form.png" });

// Save a syntactically plausible key, verify it is masked, then remove it.
await rows.first().getByPlaceholder(/paste key|enter a new key/i).fill("sk_car_" + "t".repeat(32));
await rows.first().getByRole("button", { name: /save key/i }).click();
await page.waitForTimeout(1800);
await page.goto(`${base}/providers`, { waitUntil: "networkidle" });
const afterRows = page.locator("tbody tr", { hasText: "cartesia" });
const masked = await afterRows.first().innerText();
console.log("masked row:", masked.replace(/\s+/g, " ").slice(0, 200));
console.log("contains full key:", masked.includes("t".repeat(20)));

await afterRows.first().getByRole("button", { name: /manage key/i }).click();
await page.waitForTimeout(300);
await afterRows.first().getByRole("button", { name: /^remove$/i }).click();
await afterRows.first().getByRole("button", { name: /^confirm$/i }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: "../.shots/credential-removed.png", fullPage: true });
console.log("removed; audit check:", await page.locator("text=provider.credentials").count());

void panel;
console.log(errors.length ? `CONSOLE ERRORS: ${errors.join(" | ")}` : "no console errors");
await browser.close();
