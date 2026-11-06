// Verify the Google OAuth client editor in the dashboard.
import {chromium} from "playwright";

const browser = await chromium.launch();
const page = await (await browser.newContext({viewport: {width: 1440, height: 1000}})).newPage();

await page.goto("http://localhost:3000/login", {waitUntil: "networkidle"});
await page.fill('input[type="email"]', "admin@factory.app");
await page.fill('input[type="password"]', "factory-admin-2026");
await page.getByRole("button", {name: /enter studio/i}).click();
await page.waitForURL("http://localhost:3000/", {timeout: 20000});

await page.goto("http://localhost:3000/providers", {waitUntil: "networkidle"});
const youtubeRow = page.locator("tr", {hasText: "YouTube"}).first();
await youtubeRow.getByRole("button", {name: /add key|manage key/i}).click();
await page.waitForTimeout(1500);

const panel = page.getByText("google oauth client").first();
console.log("panel visible:", await panel.isVisible());

const chip = () => page.locator("span", {hasText: /^(not configured|from dashboard|from environment)$/}).first().textContent();
console.log("configured chip:", (await chip())?.trim());

await page.fill('input[placeholder*="apps.googleusercontent.com"]', "123456789012-abcdefghijklmnop.apps.googleusercontent.com");
await page.fill('input[placeholder*="GOCSPX"]', "GOCSPX-ui-test-secret-123");
await page.getByRole("button", {name: /save client/i}).click();
await page.waitForTimeout(2500);
console.log("after save chip:", (await chip())?.trim());
console.log("banner still shown:", await page.getByText("Google OAuth is not configured").isVisible().catch(() => false));

await page.screenshot({path: "C:/Users/Asus/AppData/Local/Temp/opencode/google-client.png"});

// Remove it again so the workspace is left clean.
await page.getByRole("button", {name: /^remove$/i}).first().click();
await page.waitForTimeout(400);
await page.getByRole("button", {name: /^remove$/i}).last().click();
await page.waitForTimeout(2000);
console.log("after remove chip:", (await chip())?.trim());

await browser.close();
