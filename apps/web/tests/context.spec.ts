import { expect, test, type Page } from "@playwright/test";

let n = 0;
const email = () => `ctx${Date.now()}${n++}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("history timeline stores and searches everything; graph links it; context memory shows the conversation", async ({ page }) => {
  await register(page);
  await page.locator("#intent").fill("Flight FA2041 cancelled. I need my refund.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("Proposed plan")).toBeVisible();

  await page.goto("/app/memory");
  await page.getByLabel("Question that was asked").selectOption("travel.seat_preference");
  await page.getByLabel(/The answer/).fill("window seat");
  await page.getByRole("button", { name: "Map and save" }).click();
  await expect(page.getByRole("status")).toContainText("Saved 1 item");
  await expect(page.getByLabel("Conversation turns")).toContainText("Flight FA2041 cancelled");

  await page.goto("/app/history");
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  const tl = page.getByLabel("History timeline");
  await expect(tl).toContainText("Flight FA2041 cancelled");
  await expect(tl).toContainText("Seat preference: window");
  await page.getByLabel("Search your history").fill("seat");
  await expect(tl).toContainText("Seat preference");
  await expect(tl).not.toContainText("Flight FA2041 cancelled");
  await page.getByLabel("Type").selectOption("mission");
  await page.getByLabel("Search your history").fill("");
  await expect(tl).toContainText("Flight FA2041");

  await page.goto("/app/graph");
  await expect(page.getByLabel("Memory graph")).toBeVisible();
  await page.getByRole("button", { name: /memory: Seat preference: window/ }).click();
  await expect(page.getByText("prefers (from)")).toBeVisible();
  await page.getByRole("button", { name: /^mission:/ }).first().click();
  await expect(page.getByText("requested (from)")).toBeVisible();
});

test("black + green + orange identity with the readable Manrope display font", async ({ page }) => {
  await page.goto("/");
  const h1 = page.getByRole("heading", { level: 1 });
  await expect(h1).toContainText("Speak your need");
  expect(await h1.evaluate((e) => getComputedStyle(e).fontFamily)).toContain("Manrope");  // plain, readable headline font
  expect(await h1.evaluate((e) => getComputedStyle(e).filter)).toBe("none");  // no blur/pixel filter on the headline
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe("rgb(4, 6, 5)");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--green").trim())).toBe("52 211 102");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim())).toBe("255 122 26");
});
