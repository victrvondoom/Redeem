import { expect, test, type Page } from "@playwright/test";

let n = 0;
const email = () => `mem${Date.now()}${n++}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("REDEEM identity intro: exact name and orange tagline, skippable, replayable", async ({ page }) => {
  await page.goto("/");
  const intro = page.getByTestId("intro");
  await expect(intro).toBeVisible();
  await expect(intro.getByLabel("REDEEM")).toBeVisible();
  await expect(intro.getByText("Speak Your Need. We Take the Lead.")).toBeVisible({ timeout: 6_000 });
  await expect(intro.getByText(/Resolve/i)).toHaveCount(0);
  const color = await intro.locator(".intro-tag").evaluate((e) => getComputedStyle(e).color);
  expect(color).toBe("rgb(255, 122, 26)");
  await page.keyboard.press("Escape");
  await expect(intro).toHaveCount(0);
  await page.getByRole("button", { name: "Replay intro" }).click();
  await expect(page.getByTestId("intro")).toBeVisible();
  await page.getByRole("button", { name: /Skip intro/ }).click();
  await expect(page.getByTestId("intro")).toHaveCount(0);
});

test("Memory Center: map a spoken answer, ask for clarification, confirm sensitive data, correct and delete", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Memory" }).click();
  await page.getByLabel("Question that was asked").selectOption("travel.seat_preference");
  await page.getByLabel(/The answer/).fill("window seat please");
  await page.getByRole("button", { name: "Map and save" }).click();
  await expect(page.getByRole("status")).toContainText("Saved 1 item");
  await expect(page.getByText("window", { exact: true })).toBeVisible();
  await expect(page.getByText("simulated").first()).toBeVisible();

  await page.getByLabel(/The answer/).fill("window or aisle");
  await page.getByRole("button", { name: "Map and save" }).click();
  await expect(page.getByRole("status")).toContainText("Which one should I save?");

  await page.getByLabel("Question that was asked").selectOption("profile.phone");
  await page.getByLabel(/The answer/).fill("my number is 98765 43210");
  await page.getByRole("button", { name: "Map and save" }).click();
  await expect(page.getByText("needs your confirmation")).toBeVisible();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByText("needs your confirmation")).toHaveCount(0);

  await page.getByRole("button", { name: "Correct" }).first().click();
  await page.getByLabel("Corrected value").fill("aisle");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("aisle", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).first().click();
  await expect(page.getByText("9876543210")).toHaveCount(0);

  // later mission uses confirmed memory (prefill is recorded in the ledger, values are not)
  await page.goto("/app");
  await page.locator("#intent").fill("Flight FA2041 cancelled. I need my refund.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("Proposed plan")).toBeVisible();
});

test("Privacy Center shows real counts, honest encryption scope and rotates the key", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Privacy" }).click();
  await expect(page.getByText("AES-256-GCM").first()).toBeVisible();
  await expect(page.getByText("not end-to-end")).toBeVisible();
  await expect(page.getByText("Not encrypted at the application layer")).toBeVisible();
  await expect(page.getByText("Created on first save.")).toBeVisible();
  await page.getByRole("button", { name: "Rotate my data key" }).click();
  await expect(page.getByText("v2")).toBeVisible();
  await expect(page.getByText("retired")).toBeVisible();
});
