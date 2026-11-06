/**
 * Interactive smoke test for the Audio Studio and the credential panel.
 * Usage: node scripts/smoke-tts.mjs [--real]
 *   --real  also tries a real Cartesia/ElevenLabs key if one is configured (spends credits!)
 */

import { chromium } from "playwright";

const base = process.env.APP_URL || "http://localhost:3000";
const out = process.env.OUT_DIR || "../.shots";
const real = process.argv.includes("--real");

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
page.on("pageerror", (e) => errors.push(String(e)));

// -- login
await page.goto(`${base}/login`, { waitUntil: "networkidle" });
await page.fill("#email", "admin@factory.app");
await page.fill("#password", "factory-admin-2026");
await Promise.all([page.waitForURL(`${base}/`, { timeout: 30000 }), page.click("button[type=submit]")]);

// -- providers: open the Cartesia key panel
await page.goto(`${base}/providers`, { waitUntil: "networkidle" });
const manage = page.getByRole("button", { name: /add key|manage key/i }).first();
if (await manage.count()) {
  await manage.click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${out}/providers-credentials.png`, fullPage: true });
  console.log("provider credential panel rendered");
}

// -- audio studio: single voice with the mock provider (free, deterministic)
await page.goto(`${base}/studio/audio`, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/studio-audio.png`, fullPage: true });

const hasStudio = await page.getByRole("tab", { name: /single voice/i }).count();
if (!hasStudio) {
  console.log("NOT CONFIGURED: studio shows the setup state");
  await page.screenshot({ path: `${out}/studio-audio-setup.png`, fullPage: true });
} else {
  // switch provider A to the mock adapter through the provider select
  const providerSelect = page.locator("select").first();
  const options = await providerSelect.locator("option").evaluateAll((os) =>
    os.map((o) => ({ value: o.value, label: o.textContent })),
  );
  console.log("providers:", options.map((o) => o.value).join(", "));
  const mock = options.find((o) => o.value === "mock");
  if (!real && mock) {
    await providerSelect.selectOption("mock");
    await page.waitForTimeout(600);
  }
  await page.getByRole("button", { name: /^generate$/i }).first().click();
  await page.waitForSelector("audio", { timeout: 60000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${out}/studio-audio-result.png`, fullPage: true });
  console.log("audio element rendered after generation");

  // A/B compare with two mock voices
  await page.getByRole("tab", { name: /A\/B compare/i }).click();
  await page.waitForTimeout(300);
  const selects = page.locator("select");
  const count = await selects.count();
  for (let i = 0; i < count; i += 1) {
    const sel = selects.nth(i);
    const opts = await sel.locator("option").evaluateAll((os) => os.map((o) => o.value));
    if (opts.includes("mock")) await sel.selectOption("mock");
  }
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: /generate both/i }).click();
  await page.getByText(/verdict/i).or(page.getByText(/wins/i)).first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/studio-audio-compare.png`, fullPage: true });
  console.log("comparison rendered");

  // history + usage
  await page.goto(`${base}/studio/audio#usage`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}/studio-audio-usage.png`, fullPage: true });
}

console.log(errors.length ? `CONSOLE ERRORS:\n - ${errors.slice(0, 15).join("\n - ")}` : "no console errors");
await browser.close();
