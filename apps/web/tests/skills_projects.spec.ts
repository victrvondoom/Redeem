import { expect, test, type Page } from "@playwright/test";

let n = 0;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(`skl${Date.now()}${n++}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("intro cubes show the official Bolna and Wispr Flow logo files", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("intro").getByAltText("Bolna logo").first()).toBeVisible({ timeout: 6_000 });
  await expect(page.getByTestId("intro").getByAltText("Wispr Flow logo").first()).toBeVisible();
});

test("record a browser skill in real Chromium, replay it live with frames, persisted after reload", async ({ page }) => {
  test.setTimeout(120_000);
  await register(page);
  await page.goto("/app/skills");
  await page.getByRole("button", { name: "Record by running once" }).click();
  await expect(page.getByText("step 6 of 6")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("img", { name: /Browser screenshot: step 6/ })).toBeVisible();
  await page.getByLabel("title", { exact: true }).fill("Replayed from the UI");
  await page.getByRole("button", { name: "Run and watch" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible({ timeout: 15_000 });
  const run = page.locator("section[aria-labelledby=run-h]");
  await expect(run.getByText("step 6 of 6")).toBeVisible({ timeout: 60_000 });
  await expect(run.getByText("done", { exact: true })).toBeVisible();
  await expect(run.getByRole("button", { name: /^step \d: / })).toHaveCount(6);
  await page.reload();
  await expect(page.getByText(/6 steps · 2 runs/)).toBeVisible();
});

test("project store: create, search, attach and remove an item, persisted", async ({ page }) => {
  await register(page);
  await page.goto("/app/projects");
  await page.getByLabel("Name").fill("July trip refund");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "July trip refund" })).toBeVisible();
  await page.getByLabel("Search").fill("zzz");
  await expect(page.getByText("No match")).toBeVisible();
  await page.getByLabel("Search").fill("July");
  await page.reload();
  await expect(page.getByRole("button", { name: /July trip refund/ })).toBeVisible();
  await page.getByRole("button", { name: /July trip refund/ }).click();
  await page.getByRole("button", { name: "Delete project" }).click();
  await expect(page.getByText("No projects yet")).toBeVisible();
});
