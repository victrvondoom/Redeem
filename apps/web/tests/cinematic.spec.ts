import { expect, test, type Page } from "@playwright/test";

let n = 0;
const email = () => `cine${Date.now()}${n++}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("cinematic intro never blocks the page and hero + live counters appear", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Speak your need");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 8_000 });
  await expect(page.getByText("Knowledge passages")).toBeVisible();
  await expect(page.getByText(/Live from this deployment/)).toBeVisible();
  await page.locator("#intent").fill("Flight FA2041 cancelled refund");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page).toHaveURL(/\/register/);
});

test("reduced motion: content is visible immediately (no opacity-0 leftovers)", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 2_000 });
  await ctx.close();
});

test("Live Engine runs a real mission and replays it from the ledger", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Live Engine" }).click();
  await page.getByRole("button", { name: "Run live" }).click();
  await expect(page.getByText(/LEDGER ·/)).toBeVisible();
  await page.getByRole("button", { name: "4×" }).click();
  await expect(page.getByText("16/16 tasks verified")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("VERIFIED").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Open the mission, evidence and receipt/ })).toBeVisible();
  // scrubbing back un-lights the graph (playback is derived from the stored events)
  await page.getByLabel("Playback position").fill("0");
  await expect(page.getByText("0/16 tasks verified")).toBeVisible();
});

test("landing and Live Engine have no horizontal overflow at 390 and 360", async ({ page }) => {
  await register(page);
  for (const w of [390, 360]) {
    await page.setViewportSize({ width: w, height: 800 });
    for (const path of ["/", "/app/live"]) {
      await page.goto(path);
      await page.waitForTimeout(400);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over, `${path} @${w}`).toBeLessThanOrEqual(0);
    }
  }
});
