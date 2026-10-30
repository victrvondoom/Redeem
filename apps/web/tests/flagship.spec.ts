import { expect, test, type Page } from "@playwright/test";

const email = () => `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;

async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("landing page renders, prompt survives sign-up, flagship mission verifies", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Speak your need");
  await page.locator("#intent").fill("My flight was cancelled. Help me recover my refund.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page).toHaveURL(/\/register/);
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  // intended prompt was preserved through sign-up and became a real mission
  await expect(page).toHaveURL(/\/app\/missions\/mis_/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { level: 1 })).toContainText("My flight was cancelled");
  await expect(page.getByText("I need one detail from you")).toBeVisible();
  await page.getByRole("button", { name: /FA2041/ }).click();
  await expect(page.getByText("Proposed plan")).toBeVisible();
  await expect(page.getByText("₹8,450.00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Approve 2 actions/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("PROVIDER_NOT_CONFIGURED").first()).toBeVisible();
  // receipt persists after refresh
  await page.reload();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible();
});

test("ack loss is reconciled without duplicating", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("Flight FA2087 cancelled, refund not received");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("Proposed plan")).toBeVisible();
  await page.getByRole("button", { name: "Lose the provider’s acknowledgement" }).click();
  await page.getByRole("button", { name: /Approve 1 action/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("ACK_LOST", { exact: true })).toBeVisible();
  await expect(page.getByText("RECONCILED_FOUND", { exact: true })).toBeVisible();
});

test("business flagship: shop reservation with identity disambiguation", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("Customer Amit wants a keyboard reserved for Saturday");
  await page.getByRole("button", { name: "Start mission" }).click();
  await page.getByRole("button", { name: /Keylite K87/ }).click();
  await expect(page.getByRole("button", { name: /Amit Patil/ })).toBeVisible();
  await page.getByRole("button", { name: /Amit Patel/ }).click();
  await page.getByRole("button", { name: /Approve 1 action/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/"stock_now": 3/)).toBeVisible();
});

test("language switching changes the product UI", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Language").first().selectOption("hi");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("अपनी ज़रूरत बोलिए");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("अपनी ज़रूरत बोलिए");
});

test("voice studio is honest when Bolna is not configured", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Voice Studio" }).click();
  await expect(page.getByText("PROVIDER_NOT_CONFIGURED").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Start call" })).toBeDisabled();
  await expect(page.getByText("No calls yet")).toBeVisible();
});

test("no horizontal overflow at key widths", async ({ page }) => {
  for (const w of [1440, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto("/");
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over, `overflow at ${w}px`).toBeLessThanOrEqual(0);
  }
});
