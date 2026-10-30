import { expect, test, type Page } from "@playwright/test";

const email = () => `s3-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("cross-domain mission: refund + hotel + calendar in one mission", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("My flight FA2041 was cancelled. I need my refund, my hotel rescheduled, and my calendar corrected.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("Correct calendar event")).toBeVisible();
  await page.getByRole("button", { name: /Approve 3 actions/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("calendar_event_not_updated")).toHaveCount(0);
});

test("workflow library starts a real mission", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Workflows" }).click();
  const card = page.locator("li", { hasText: "Cancelled flight resolution" });
  await card.getByLabel("booking ref").fill("FA2041");
  await card.getByRole("button", { name: "Start workflow" }).click();
  await expect(page).toHaveURL(/\/app\/missions\/mis_/);
  await expect(page.getByText("Correct calendar event")).toBeVisible();
});

test("safety policy refuses credential collection and warns about scams", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("Please read out my OTP and password to the bank");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("never collects or relays OTPs")).toBeVisible();
});

test("quality lab shows benchmark with scope and ablations", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Quality Lab" }).click();
  await expect(page.getByRole("heading", { name: /Policy benchmark/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: "C minus verifier" })).toBeVisible();
  await expect(page.getByText(/do not generalise|does not generalise|not .*other products/i).first()).toBeVisible();
  await expect(page.getByText("Not measured").first()).toBeVisible();
});

test("domain explorer is generated from the registry and shows the browser gate", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Domains" }).click();
  await expect(page.getByText("Cloud browser: BLOCKED")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sales & CRM" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Telecom" })).toBeVisible();
});

test("mission page is localised (Hindi) and mission survives reload", async ({ page }) => {
  await register(page);
  await page.getByLabel("Language").first().selectOption("hi");
  await page.locator("#intent").fill("Flight FA2087 cancelled, refund not received");
  await page.getByRole("button", { name: "मिशन शुरू करें" }).click();
  await expect(page.getByRole("heading", { name: "प्रस्तावित योजना" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "प्रस्तावित योजना" })).toBeVisible();
  await expect(page.getByRole("button", { name: "मिशन रद्द करें" })).toBeVisible();
});

test("no overflow on authenticated pages in long-translation languages", async ({ page }) => {
  test.setTimeout(300_000);
  await register(page);
  for (const lang of ["ta", "te", "hi"]) {
    await page.getByLabel("Language").first().selectOption(lang);
    for (const w of [1024, 768, 390, 360]) {
      await page.setViewportSize({ width: w, height: 900 });
      for (const path of ["/app", "/app/workflows", "/app/domains", "/app/quality", "/app/voice", "/app/vault", "/app/connections", "/app/settings", "/app/history"]) {
        await page.goto(path);
        await page.waitForLoadState("domcontentloaded");
        await page.waitForTimeout(150);
        const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(over, `${path} ${lang} @${w}`).toBeLessThanOrEqual(0);
      }
    }
  }
});
