# UI polish pass: removing generated-looking defaults

Source of the rules: the third-party **Hallmark** design skill (`npx skills add nutlope/hallmark -g`, installed to `~/.agents/skills/hallmark`). I read its SKILL.md, redesign.md and gates.md as data. **I did not run its scripts** (AGENTS.md rule 6: no executing third-party code), so there is no Hallmark stamp, log or sloplint verdict. Instead `scripts/ui_floor_check.mjs` (ours, needs the app running) re-checks the machine-checkable rules in a real browser. Depth used: *polish plus restyle of what the rules name*; the layout system and your brand choices stay (black, one green, one orange, the pixel-serif display face).

## Before (old build, 19 routes + mission page)
Repeated findings across every app page: tracked-caps sidebar labels (67), caps labels, middle-dot meta strings (63), no `overflow-x: clip` on html/body (34); on the landing page also an eyebrow line, a 23-word lede, 4 text blocks in the hero, 964 words, 253 words in one 900px window (58), gradient text and glow shadows (2a/29), icon-tile domain cards (3), decorative status dots (63), arrows in links (63).

## After
`node scripts/ui_floor_check.mjs` reports **0 FAIL**. Notes: densest 900px window is 83 words (rule: about 80); full-bleed section backgrounds are 1920px wide while their content stays capped.

## What changed
- Labels are sentence case, body face, untracked. No eyebrow. No middle-dot meta strings, arrows glued to links or decorative status dots.
- Colours go through tokens in `:root`; no gradient text, glows, blurred halos or `transition: all`; elevation by lightness and offset shadows. The progress bar scales with `transform`, not `width`.
- `overflow-x: clip` on `html` and `body`; headings `overflow-wrap: break-word`; content visible with scripting off (`noscript`) and with reduced motion.
- Landing page rebuilt from the same facts: headline 7 words, one 8-word sentence, two actions; about 400 words in total; domains as a hairline list instead of icon tiles; "What is real today" split into Works and Not yet.
- Copy tightened (English only; the Hindi, Tamil, Telugu and Hinglish strings were not re-translated): hero sentence, composer note and third example, scenario titles "A. Consumer super-agent", simulation labels. Tests that asserted the old wording were updated to the new wording, no assertion removed.

## Kept on purpose (your direction beats a generic rule)
The concentric green arcs from the Buildathon artwork (a decorative radial motif), the Gloock pixel display face, the 3D intro and the hero stage. Machine identifiers such as `PROVIDER_NOT_CONFIGURED` stay as written.

## Not done
Spacing tokens (`--space-*`), a `design.md` lock, a full app-screen recomposition, and the Hallmark hero/finish reviews (they need its scripts and a subagent).
