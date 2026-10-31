// Design-floor checker (our own, derived from the Hallmark design-skill rules we adopted; not the skill's script).
// Usage: node scripts/ui_floor_check.mjs [baseUrl]   (needs the app running; exits 1 on any FAIL)
import { createRequire } from "node:module";
const require = createRequire(process.cwd() + "/apps/web/");
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:3000";
const fails = []; const notes = [];
const fail = (route, rule, detail) => fails.push(`${route}  [${rule}] ${detail}`);

const inspect = () => {
  const out = { caps: [], tracked: [], nested: [], transAll: [], under12: [], arrows: [], dots: [], words: 0 };
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const n = walker.currentNode; const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || seen.has(el) || !vis(el) || /^(SCRIPT|STYLE|NOSCRIPT|CODE|PRE|OPTION)$/.test(el.tagName)) continue;
    seen.add(el);
    const s = getComputedStyle(el); const px = parseFloat(s.fontSize); const ls = parseFloat(s.letterSpacing) || 0;
    const mono = /mono|code/i.test(s.fontFamily);
    if (px <= 15 && s.textTransform === "uppercase" && !el.closest("[data-wordmark]")) out.caps.push(t.slice(0, 30));
    if (px <= 15 && ls / px > 0.03 && !mono && !el.closest("[data-wordmark]")) out.tracked.push(`${t.slice(0, 24)} (${(ls / px).toFixed(2)}em)`);
    if (px < 11 || (px < 12 && el.children.length === 0 && t.length > 40)) out.under12.push(`${t.slice(0, 24)} ${px}px`);
    if (/ · /.test(t)) out.dots.push(t.slice(0, 40));
    if (el.closest("a,button") && /[→←]/.test(t)) out.arrows.push(t.slice(0, 40));
  }
  document.querySelectorAll(".card .card").forEach((c) => out.nested.push((c.textContent || "").trim().slice(0, 30)));
  document.querySelectorAll("*").forEach((e) => { const p = getComputedStyle(e).transitionProperty; if (p === "all" && parseFloat(getComputedStyle(e).transitionDuration) > 0) out.transAll.push(e.tagName + "." + String(e.className).slice(0, 30)); });
  out.overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
  out.htmlClip = getComputedStyle(document.documentElement).overflowX; out.bodyClip = getComputedStyle(document.body).overflowX;
  return out;
};
const wordsIn = (page, y0, y1) => page.evaluate(([a, b]) => { let n = 0; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) { const t = w.currentNode; const el = t.parentElement; if (!el || /^(SCRIPT|STYLE|NOSCRIPT|OPTION)$/.test(el.tagName)) continue; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || r.width === 0) continue; const top = r.top + window.scrollY; if (top >= a && top < b) n += t.textContent.trim().split(/\s+/).filter(Boolean).length; } return n; }, [y0, y1]);

(async () => {
  const b = await chromium.launch({ executablePath: process.env.PW_CHROMIUM_PATH || "/opt/pw-browsers/chromium" });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.addInitScript(() => sessionStorage.setItem("redeem-intro", "1"));
  const run = async (route, vw = 1440, vh = 900) => {
    await page.setViewportSize({ width: vw, height: vh }); await page.goto(base + route); await page.waitForTimeout(900);
    const r = await page.evaluate(inspect); const tag = `${route}@${vw}`;
    if (r.caps.length) fail(tag, "67 caps label", [...new Set(r.caps)].slice(0, 4).join(" | "));
    if (r.tracked.length) fail(tag, "67 tracked label", [...new Set(r.tracked)].slice(0, 4).join(" | "));
    if (r.dots.length) fail(tag, "63 middle-dot meta", [...new Set(r.dots)].slice(0, 3).join(" | "));
    if (r.arrows.length) fail(tag, "63 arrow in link", r.arrows.slice(0, 3).join(" | "));
    if (r.nested.length) fail(tag, "4 card in card", r.nested.slice(0, 3).join(" | "));
    if (r.transAll.length) fail(tag, "10a transition:all", r.transAll.slice(0, 3).join(" | "));
    if (r.overflow > 0) fail(tag, "34 horizontal scroll", `${r.overflow}px`);
    if (r.htmlClip !== "clip" || r.bodyClip !== "clip") fail(tag, "34 overflow-x clip", `html=${r.htmlClip} body=${r.bodyClip}`);
    if (r.under12.length) notes.push(`${tag} [75] small text: ${[...new Set(r.under12)].slice(0, 3).join(" | ")}`);
    return r;
  };
  await page.goto(base + "/register"); await page.getByLabel("Name").fill("Floor Check"); await page.getByLabel("Email").fill(`floor${Date.now()}@example.com`); await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click(); await page.waitForURL("**/app");
  await page.goto(base + "/app/demo"); await page.locator("li", { hasText: "A." }).getByRole("button", { name: "Run scenario" }).click().catch(() => {}); await page.waitForTimeout(2500);
  const ctxOut = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" }); const anon = await ctxOut.newPage(); await anon.addInitScript(() => sessionStorage.setItem("redeem-intro", "1"));
  // landing (anonymous)
  const L = async (vw, vh) => { await anon.setViewportSize({ width: vw, height: vh }); await anon.goto(base + "/"); await anon.waitForTimeout(900); return anon; };
  let a = await L(1440, 900); const lr = await a.evaluate(inspect); const tagL = "/@1440";
  for (const [k, rule, lbl] of [["caps", "67 caps label", ""], ["tracked", "67 tracked label", ""], ["dots", "63 middle-dot meta", ""], ["arrows", "63 arrow in link", ""], ["nested", "4 card in card", ""], ["transAll", "10a transition:all", ""]]) if (lr[k].length) fail(tagL, rule, [...new Set(lr[k])].slice(0, 4).join(" | "));
  if (lr.htmlClip !== "clip" || lr.bodyClip !== "clip") fail(tagL, "34 overflow-x clip", `html=${lr.htmlClip} body=${lr.bodyClip}`);
  const h1 = await a.evaluate(() => { const h = document.querySelector("h1"); const r = h.getBoundingClientRect(); return { words: h.textContent.trim().split(/\s+/).length, bottom: r.bottom, ff: getComputedStyle(h).fontFamily }; });
  if (h1.words > 7) fail("/", "hero headline", `${h1.words} words (max 7)`);
  const ledeWords = await a.evaluate(() => { const p = document.querySelector("h1").parentElement.querySelector("p:not(.h-eyebrow)"); return p ? p.textContent.trim().split(/\s+/).length : 0; });
  if (ledeWords > 12) fail("/", "hero lede", `${ledeWords} words (max 12)`);
  const heroTextBlocks = await a.evaluate(() => { const h = document.querySelector("h1").parentElement; return [...h.children].filter((c) => !c.querySelector("a,button") && c.tagName !== "DIV" && c.textContent.trim()).length; });
  if (heroTextBlocks > 3) fail("/", "58 hero text blocks", `${heroTextBlocks} before actions (max headline + lede)`);
  const total = await a.evaluate(() => document.body.innerText.trim().split(/\s+/).length);
  if (total > 450) fail("/", "landing word budget", `${total} visible words (max 450)`);
  const H = await a.evaluate(() => document.documentElement.scrollHeight); let worst = 0, at = 0;
  for (let y = 0; y < H - 200; y += 450) { const n = await wordsIn(a, y, y + 900); if (n > worst) { worst = n; at = y; } }
  if (worst > 85) fail("/", "58 words per 900px window", `${worst} words at y=${at} (rule is "about 80"; tolerance 85)`); else if (worst > 80) notes.push(`/ [58] densest 900px window ${worst} words (rule: about 80)`);
  await a.setViewportSize({ width: 1280, height: 800 }); await a.waitForTimeout(300);
  const fold = await a.evaluate(() => { const h = document.querySelector("h1"); const act = [...document.querySelectorAll("main a,main button")].find((e) => /voice|start/i.test(e.textContent)); return { h: h.getBoundingClientRect().bottom, act: act ? act.getBoundingClientRect().bottom : 9999 }; });
  if (fold.h > 800 || fold.act > 800) fail("/", "44b hero fold @1280x800", `headline bottom ${Math.round(fold.h)}, action bottom ${Math.round(fold.act)}`);
  for (const vw of [1920]) { await a.setViewportSize({ width: vw, height: 1080 }); await a.waitForTimeout(300); const w = await a.evaluate(() => Math.max(...[...document.querySelectorAll("main section > div, main section")].map((e) => e.getBoundingClientRect().width)).toFixed(0)); if (+w >= 1900) notes.push(`/@1920 [44d] widest section block ${w}px`); }
  // app routes (authenticated)
  for (const r of ["/app", "/app/cases", "/app/history", "/app/vault", "/app/domains", "/app/connections", "/app/voice", "/app/memory", "/app/graph", "/app/privacy", "/app/quality", "/app/live", "/app/demo", "/app/workflows", "/app/knowledge", "/app/files", "/app/studio", "/app/settings"]) await run(r);
  await page.goto(base + "/app/demo"); await page.getByRole("link", { name: /Open mission/ }).first().click().catch(() => {}); await page.waitForTimeout(1500); const mr = await page.evaluate(inspect); if (mr.caps.length) fail("mission page", "67 caps label", mr.caps.slice(0, 3).join(" | ")); if (mr.nested.length) fail("mission page", "4 card in card", mr.nested.slice(0, 3).join(" | ")); if (mr.dots.length) fail("mission page", "63 middle-dot", mr.dots.slice(0, 3).join(" | ")); if (mr.tracked.length) fail("mission page", "67 tracked", mr.tracked.slice(0, 3).join(" | "));
  await b.close();
  console.log(fails.length ? "FAIL\n" + fails.join("\n") : "Floor: 0 FAIL");
  if (notes.length) console.log("\nNOTES\n" + [...new Set(notes)].join("\n"));
  process.exit(fails.length ? 1 : 0);
})();
