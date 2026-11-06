// Opens the add-provider form on the dashboard and reports which LLM adapters it offers.
import {chromium} from "playwright";

const browser = await chromium.launch();
const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
const page = await context.newPage();

await page.goto("http://localhost:3000/login", {waitUntil: "networkidle"});
await page.fill('input[type="email"], input[name="email"]', "admin@factory.app");
await page.fill('input[type="password"]', "factory-admin-2026");
await page.getByRole("button", {name: /enter studio/i}).click();
await page.waitForURL("http://localhost:3000/", {timeout: 20000});

await page.goto("http://localhost:3000/providers", {waitUntil: "networkidle"});
await page.getByRole("button", {name: /add provider/i}).click();
await page.waitForTimeout(800);

const llmOptions = await page.locator("select").nth(1).locator("option").allTextContents();
console.log("LLM adapter options:", llmOptions);

await page.locator("select").nth(1).selectOption("openai-compatible");
await page.waitForTimeout(500);
const hasBaseUrl = await page.locator('input[placeholder*="groq"], input[placeholder*="v1"]').count();
const hasListModels = await page.getByRole("button", {name: /list models/i}).count();
console.log("base url field:", hasBaseUrl, "| list models button:", hasListModels);

await page.screenshot({path: "C:/Users/Asus/AppData/Local/Temp/opencode/add-provider.png", fullPage: false});
await browser.close();
