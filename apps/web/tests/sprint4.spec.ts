import { expect, test, type Page } from "@playwright/test";

const email = () => `s4-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("demo scenario A: one request → one coordinated multi-domain mission with evidence", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Demo", exact: true }).click();
  await page.locator("li", { hasText: "A. Consumer super-agent" }).getByRole("button", { name: "Run scenario" }).click();
  await page.getByRole("link", { name: /Open mission, ledger and evidence/ }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Prepare family message (draft, not sent)")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alternative flights" })).toBeVisible();
  await expect(page.getByText("sold out")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence Center" })).toBeVisible();
  await expect(page.getByText("DATABASE VERIFIED").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Agent activity" })).toBeVisible();
  await page.getByRole("group", { name: "Filter by agent" }).getByRole("button", { name: "verifier" }).click();
  await expect(page.getByText("independent readback").first()).toBeVisible();
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Report (readable)" }).click();
  expect((await dl).suggestedFilename()).toMatch(/redeem-report-mis_.*\.md/);
});

test("demo scenario C: adversarial recovery proves one effect", async ({ page }) => {
  await register(page);
  await page.goto("/app/demo");
  await page.locator("li", { hasText: "C. Adversarial recovery" }).getByRole("button", { name: "Run scenario" }).click();
  await expect(page.getByText(/stale approval replay blocked: true/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/on intended booking: 1/)).toBeVisible();
  await expect(page.getByText(/on wrong booking: 0/)).toBeVisible();
});

test("demo scenario B: retail operator verifies stock and CRM", async ({ page }) => {
  await register(page);
  await page.goto("/app/demo");
  await page.locator("li", { hasText: "B. Indian retail operator" }).getByRole("button", { name: "Run scenario" }).click();
  await page.getByRole("link", { name: /Open mission/ }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/"stock_now": 2/)).toBeVisible();
});

test("mission control: pause blocks execution, resume allows it; reject cancels", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("Flight FA2041 cancelled. I need my refund and my hotel rescheduled.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("Proposed plan")).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByText("paused — nothing will run")).toBeVisible();
  await page.getByRole("button", { name: "Approve 2 actions" }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByText(/paused; resume it first/)).toBeVisible();
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
});

test("connections show manifests and honest conditions", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Connections" }).click();
  await expect(page.getByText("FIXTURE_VERIFIED").first()).toBeVisible();
  await expect(page.getByText("UNCONFIGURED").first()).toBeVisible();
  await expect(page.getByText("LIVE_VERIFIED")).toHaveCount(1); // only in the explanatory sentence
});

test("first-use checklist reflects real progress", async ({ page }) => {
  await register(page);
  await expect(page.getByRole("heading", { name: "Your first verified outcome" })).toBeVisible();
  await page.locator("#intent").fill("Flight FA2041 cancelled refund");
  await page.getByRole("button", { name: "Start mission" }).click();
  await page.getByRole("button", { name: /Approve \d+ action/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Your first verified outcome" })).toHaveCount(0);
});

test("mobile: mission page with evidence has no overflow at 390 and 360", async ({ page }) => {
  await register(page);
  await page.goto("/app/demo");
  await page.locator("li", { hasText: "A. Consumer super-agent" }).getByRole("button", { name: "Run scenario" }).click();
  await page.getByRole("link", { name: /Open mission/ }).click();
  await expect(page.getByRole("heading", { name: "Evidence Center" })).toBeVisible({ timeout: 15_000 });
  for (const w of [390, 360]) {
    await page.setViewportSize({ width: w, height: 800 });
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over, `overflow @${w}`).toBeLessThanOrEqual(0);
  }
});
