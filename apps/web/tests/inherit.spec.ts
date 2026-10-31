import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const fx = (n: string) => path.join(__dirname, "fixtures", n);
const email = () => `inh-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
async function register(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Name").fill("Asha Rao");
  await page.getByLabel("Email").fill(email());
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("RECLAIM case lifecycle in the UI: open → evidence → sources → options → draft → approve → submit → track → verified outcome", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Cases", exact: true }).click();
  await page.getByRole("button", { name: "Travel" }).first().click().catch(() => undefined);
  await page.locator("#nc").fill("My IndiGo flight 6E-2134 on 15 January 2026 was cancelled and they refused a refund of Rs 8,500. PNR: ABC123");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page).toHaveURL(/\/app\/cases\/cse_/);
  await expect(page.getByRole("list", { name: "Case stages" })).toBeVisible();
  await expect(page.getByText("Airline & travel").first()).toBeVisible();
  // evidence: upload a ticket, see classification, strength and the checklist move
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByLabel("Upload evidence").setInputFiles(fx("ticket.txt"));
  await expect(page.getByText(/classified as ticket/)).toBeVisible();
  await expect(page.getByText("Booking confirmation / e-ticket with PNR")).toBeVisible();
  await expect(page.getByText(/ticket\.txt, strength/)).toBeVisible();
  await page.getByLabel("Upload evidence").setInputFiles(fx("reply.txt"));
  await expect(page.getByText("Evidence-to-claim mapping")).toBeVisible();
  await expect(page.getByText("supported").first()).toBeVisible();
  // sources carry provenance
  await page.getByRole("tab", { name: /Sources/ }).click();
  await expect(page.getByText(/authored guide \(not an official text\)/).first()).toBeVisible();
  // options with assumptions
  await page.getByRole("tab", { name: /Options/ }).click();
  await expect(page.getByText(/heuristic stage defaults/).first()).toBeVisible();
  await page.getByRole("button", { name: "Re-rank" }).click();
  await expect(page.getByText("Re-ranked.")).toBeVisible();
  // draft: edit → new version, approval cleared; then approve
  await page.getByRole("tab", { name: /Draft/ }).click();
  const box = page.locator("#dbody");
  await box.fill((await box.inputValue()) + "\n\nPlease also confirm the refund timeline in writing.");
  await page.getByRole("button", { name: "Save edits" }).click();
  await expect(page.getByText("v2").first()).toBeVisible();
  await page.getByRole("button", { name: "Approve this draft" }).click();
  await expect(page.getByText(/Approved action/)).toBeVisible();
  // submit: honest handoff
  await page.getByRole("tab", { name: /Submit/ }).click();
  await page.getByRole("button", { name: "Record and prepare handoff" }).click();
  await expect(page.getByText(/nothing has been sent/)).toBeVisible();
  await page.getByLabel("Update").selectOption("resolved");
  await page.getByRole("button", { name: "Log update" }).click();
  await expect(page.getByText("user reported unverified")).toBeVisible();      // outcome is not claimed as verified without a document
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Evidence bundle (.zip)" }).click();
  expect((await dl).suggestedFilename()).toMatch(/evidence-bundle-cse_.*\.zip/);
});

test("case that needs facts asks only for what is missing and resumes", async ({ page }) => {
  await register(page);
  await page.goto("/app/cases");
  await page.locator("#nc").fill("My flight was cancelled and I want a refund from the airline.");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page.getByText("I need a few facts")).toBeVisible();
  await page.getByLabel(/flight number/i).first().fill("AI-101");
  await page.getByLabel(/which date was the flight scheduled/i).fill("2026-02-02");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page.getByText("I need a few facts")).toHaveCount(0);
  await page.getByRole("tab", { name: /Draft/ }).click();
  await expect(page.locator("#dbody")).toContainText("AI-101");
});

test("RESOLVE browser mission in the UI: two Jordans, real Chromium, snapshots, task graph, commands", async ({ page }) => {
  test.setTimeout(120_000);
  await register(page);
  await page.locator("#intent").fill("Prepare a follow-up for Jordan Lee using the latest report, update the CRM and send it after I approve.");
  await page.getByRole("button", { name: "Start mission" }).click();
  await expect(page.getByText("I need one detail from you")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: /Jordan Lee · C-104/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Jordan Lee · C-208/ })).toBeVisible();
  await page.getByRole("button", { name: /Jordan Lee · C-104/ }).click();
  await expect(page.getByText("Create CRM follow-up task (in the browser)")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/SIMULATED delivery/i).first()).toBeVisible();
  await page.getByRole("button", { name: /Approve 2 actions/ }).click();
  await page.getByRole("button", { name: "Run approved actions" }).click();
  await expect(page.getByRole("heading", { name: /Receipt — Done and verified/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Browser sessions" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Task dependency graph" })).toBeVisible();
  await page.getByRole("button", { name: /before.*crm before task/i }).click();
  const img = page.getByRole("img", { name: /Screenshot: crm before task/ });
  await expect(img).toBeVisible();
  await expect.poll(async () => img.evaluate((e: HTMLImageElement) => e.naturalWidth)).toBeGreaterThan(100);   // a real screenshot rendered
  await page.getByLabel("Command").fill("what happened");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText(/independently verified an effect/)).toBeVisible();
});

test("command center shows real attention items and live counts; history has cases and missions", async ({ page }) => {
  await register(page);
  await page.goto("/app/cases");
  await page.locator("#nc").fill("My Jio postpaid bill shows Rs 1,299 of extra charges. Complaint no: CMP-8812 got no resolution.");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page).toHaveURL(/\/app\/cases\/cse_/);
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Needs your attention" })).toBeVisible();
  await expect(page.getByText("Review and approve the draft")).toBeVisible();
  await expect(page.getByText("Open cases")).toBeVisible();
  await page.getByRole("link", { name: "History" }).click();
  await page.getByRole("tab", { name: /Cases/ }).click();
  await expect(page.getByText(/Telecom: billing/).first()).toBeVisible();
});

test("knowledge search returns passages with provenance and scores", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Knowledge" }).click();
  await expect(page.getByText(/1,159 passages|1159 passages/)).toBeVisible();
  await page.getByRole("searchbox").or(page.locator("#kq")).fill("builder delayed possession complaint");
  await page.locator("#kd").selectOption("housing");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/authored guide \(not official\)/).first()).toBeVisible();
  await expect(page.getByText("confidence").first()).toBeVisible();
});

test("evidence vault: upload, filter, detail with facts and download", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Evidence Vault" }).click();
  await page.getByLabel("Choose a file").setInputFiles(fx("ticket.txt"));
  await expect(page.getByText(/Stored ticket\.txt: ticket/)).toBeVisible();
  await page.getByLabel("Choose a file").setInputFiles(fx("ticket.txt"));
  await expect(page.getByText(/already in your vault/)).toBeVisible();      // duplicate detection
  await page.getByRole("button", { name: /ticket\.txt/ }).click();
  await expect(page.getByText("Extracted facts → source")).toBeVisible();
  await expect(page.getByText("₹8,500.00").first().or(page.getByText("Rs 8,500").first())).toBeVisible();
  await page.locator("#vq").fill("zzz-no-match");
  await expect(page.getByText("No documents match")).toBeVisible();
});

test("files: duplicates → dry-run plan → apply (verified) → undo", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Files", exact: true }).click();
  await page.getByLabel("Add a file").setInputFiles(fx("dup-a.txt"));
  await expect(page.getByText(/Added dup-a\.txt/)).toBeVisible();
  await page.getByLabel("Add a file").setInputFiles(fx("dup-b.txt"));
  await expect(page.getByText(/2 identical files/)).toBeVisible();
  await page.getByRole("button", { name: "Create dry-run plan" }).click();
  await expect(page.getByText(/Nothing has moved/)).toBeVisible();
  await page.getByRole("button", { name: "Apply plan" }).click();
  await expect(page.getByText(/Applied and verified/)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText(/Undone; originals restored/)).toBeVisible();
});

test("pdf studio: create a report PDF and read its text back", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "PDF Studio" }).click();
  await page.locator("#rt").fill("Quarterly summary");
  await page.locator("#rx").fill("First line of the report.\n\nSecond paragraph.");
  await page.getByRole("button", { name: "Create PDF" }).click();
  await expect(page.getByText(/Report created as a real PDF/)).toBeVisible();
  await page.getByRole("button", { name: "Text", exact: true }).click();
  await expect(page.getByText(/First line of the report/)).toBeVisible();
});

test("domain explorer lists all eight workflows and starts a real case from one", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "Domains" }).click();
  for (const d of ["Airline & travel", "Banking & payment safety", "Insurance", "Telecom", "E-commerce & retail", "Housing & property", "Government grievances", "Healthcare administration"]) await expect(page.getByRole("heading", { name: d })).toBeVisible();
  await expect(page.getByText(/No knowledge corpus was inherited/).first().or(page.getByText(/Insurance/).first())).toBeVisible();
  await page.locator("li", { hasText: "Housing & property" }).getByRole("button", { name: "Start with an example case" }).click();
  await expect(page).toHaveURL(/\/app\/cases\/cse_/);
  await expect(page.getByText("Housing & property").first()).toBeVisible();
});

test("quality lab runs a real benchmark and lists the stored run", async ({ page }) => {
  test.setTimeout(120_000);
  await register(page);
  await page.getByRole("link", { name: "Quality Lab" }).click();
  await page.locator("#nn").fill("1");
  await page.getByRole("button", { name: "Run benchmark" }).click();
  await expect(page.getByRole("link", { name: "JSON" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/7\/7/).first()).toBeVisible();
});

test("new screens have no horizontal overflow in long-translation languages", async ({ page }) => {
  test.setTimeout(600_000);
  await register(page);
  await page.goto("/app/cases");
  await page.locator("#nc").fill("My Jio postpaid bill shows Rs 1,299 of extra charges. Complaint no: CMP-8812 got no resolution.");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page).toHaveURL(/\/app\/cases\/cse_/);
  const caseUrl = page.url();
  for (const lang of ["ta", "hi"]) {
    await page.locator('select[aria-label="Language"]:visible').first().selectOption(lang);
    for (const w of [768, 360]) {
      await page.setViewportSize({ width: w, height: 900 });
      for (const p of ["/app", "/app/cases", caseUrl.replace(/^https?:\/\/[^/]+/, ""), "/app/knowledge", "/app/vault", "/app/domains"]) {
        await page.goto(p); await page.waitForLoadState("domcontentloaded"); await page.waitForTimeout(150);
        const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(over, `${p} ${lang} @${w}`).toBeLessThanOrEqual(0);
      }
    }
  }
});
