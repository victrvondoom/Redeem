import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

let n = 0;
const email = () => `live${Date.now()}${n++}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("OCR: a photo of a ticket is read by the real OCR engine, can be corrected, and facts update", async ({ page }) => {
  await register(page);
  await page.goto("/app/vault");
  await page.getByLabel("Choose a file").setInputFiles(path.join(__dirname, "fixtures", "ticket-photo.png"));
  await expect(page.getByRole("status").first()).toContainText("ticket-photo.png", { timeout: 30_000 });
  await page.getByRole("button", { name: /ticket-photo\.png/ }).first().click().catch(() => page.getByText("ticket-photo.png").first().click());
  await expect(page.getByText(/average confidence/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Corrected text")).toHaveValue(/FA2041/);
  await page.getByLabel("Corrected text").fill("Flight FA2041 cancelled. Refund Rs 8450 not received. Corrected by the user.");
  await page.getByRole("button", { name: "Save corrected text" }).click();
  await expect(page.getByText(/Facts and strength were recomputed/)).toBeVisible();
});

test("Brief to PDF: extract, edit, generate a real PDF stored in the vault", async ({ page }) => {
  await register(page);
  await page.goto("/app/studio");
  await page.getByLabel("Your brief").fill("# Refund follow-up\nFindings:\n- Refund of Rs 8,450 not received for FA2041\nWe should follow up by Friday.");
  await page.getByRole("button", { name: "Extract structure" }).click();
  await expect(page.locator("#b-title")).toHaveValue("Refund follow-up");
  await page.locator("#b-title").fill("Refund follow-up (edited)");
  await page.getByRole("button", { name: "Generate PDF" }).click();
  await expect(page.getByRole("status").filter({ hasText: "stored encrypted" })).toContainText("1 page(s)");
  const href = await page.getByRole("link", { name: "Download PDF" }).getAttribute("href");
  const res = await page.request.get(href!);
  expect((await res.body()).subarray(0, 5).toString()).toBe("%PDF-");
});

test("Connections Center is honest when Google is not configured and nothing can be connected", async ({ page }) => {
  await register(page);
  await page.goto("/app/connections");
  await expect(page.getByRole("heading", { name: "Live providers" })).toBeVisible();
  await expect(page.getByText("GOOGLE_OAUTH_CLIENT_ID").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Google" })).toBeDisabled();
  await expect(page.getByText("Not verified live yet.").first()).toBeVisible();
  await expect(page.getByText("BOLNA_API_KEY").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Demo fixtures" })).toBeVisible();
});
